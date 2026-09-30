#!/usr/bin/env python3
"""AAPL.US (Apple) valuation eval — recompute anchors from frameworks/AAPL.US.md.

frameworks/AAPL.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: aapl_fy27_consensus_two_stage_roic_v1

Whole-company scale; the hardware / services split is a cross-check only (no
segment operating income or assets are reported, A3).  Numerator = FY2027E EPS
consensus band (40 analysts, low / mean / high) — the furthest year with a
≥2-house band.  FY2028E has two house point estimates (BofA, Citi) → one
transition year g1 shared by all tiers (valuation-rules 裁决表 ②, 2026-09-14).
Perpetual g2 = gross-profit-weighted blend of the mega-hardware cap (4%) on
products and the macro cap (6%) on services — both legs sit in basket 4, so a
profit-weighted g is legal (valuation-rules「腿归篮」「巨型硬件上限」, 2026-09-27).

Retention enters through ROIC, not book ROE: buybacks have shrunk equity the
way leverage does (A13), and Apple holds net cash, so invested capital =
equity − net cash.  Book ROE and the LLY-style 60% cap are sensitivity rows.

Run:  python3 frameworks/eval/AAPL.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, check_transition_years, payout_gap, two_stage_pe,
)
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

# The r_f readings helpers import through the `eval.lib` package, so the repo root joins the path.
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "AAPL.US.md"
FORMULA_ID = "aapl_fy27_consensus_two_stage_roic_v1"
TIERS = ("l", "m", "h")
REQUIRED = [
    "shares_diluted", "eps_fy27e_low", "eps_fy27e_consensus", "eps_fy27e_high",
    "eps_fy28e_bofa", "eps_fy28e_citi", "n_stage", "consensus_years_beyond",
    "eps_fy26e", "eps_9m_26", "bps_q3_26", "net_cash_q3_26",
    "r_perp", "g2_hw", "g2_svc", "w_hw", "g2", "g2_cand", "payout_actual", "k_l", "k_m", "k_h",
    "eps_ttm", "pe_own_min", "pe_own_top", "net_debt_ebitda", "interest_ebit",
    "tac_eps", "v_opt",
]
FIXED_POINT_ITERS = 60
ROE_CAP_LLY = 0.60  # LLY.US A4 convention, shown only as a sensitivity row
LISTING_CCY = "USD"
RUNWAY_G = (0.06, 0.08, 0.10, 0.12, 0.15)
RUNWAY_N = (0, 5, 10, 15, 20)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # Step 1 — rate, growth and their caps.
    r = inp["r_perp"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    g2_blend = inp["w_hw"] * inp["g2_hw"] + (1 - inp["w_hw"]) * inp["g2_svc"]
    if abs(g2_blend - inp["g2"]) > 5e-4:
        errors.append(f"g2 {inp['g2']} ≠ gross-profit blend {g2_blend:.4f}")
    g2 = inp["g2"]
    errors += check_g_cap(inp["g2_hw"], r, "g2_hw", mega_hw=True)
    errors += check_g_cap(inp["g2_svc"], r, "g2_svc")
    errors += check_g_cap(g2, r, "g2")
    errors += check_g_cap(inp["g2_cand"], r, "g2_cand")
    n = int(inp["n_stage"])
    errors += check_transition_years(n, int(inp["consensus_years_beyond"]), "n_stage")
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition as a gate, not an election")

    eps = {"l": inp["eps_fy27e_low"], "m": inp["eps_fy27e_consensus"], "h": inp["eps_fy27e_high"]}
    errors += ladder("eps_fy27e", eps["l"], eps["m"], eps["h"])
    fy28 = (inp["eps_fy28e_bofa"] + inp["eps_fy28e_citi"]) / 2
    g1 = fy28 / eps["m"] - 1
    net_cash_ps = inp["net_cash_q3_26"] * 1e3 / inp["shares_diluted"]
    unbooked_26 = inp["eps_fy26e"] - inp["eps_9m_26"]

    # Step 2 — the return on reinvested capital: ROIC on equity − net cash (A13).
    def capital_base(e: float, cap_base: float, cap: float | None) -> tuple[float, float, float]:
        """(base at start of FY2027, return used, stage-1 b) — b = g1/return fixed point."""
        b = 0.0
        for _ in range(FIXED_POINT_ITERS):
            base = cap_base + b * unbooked_26
            ret = e / base if cap is None else min(e / base, cap)
            b = g1 / ret
        return base, ret, b

    ic0 = inp["bps_q3_26"] - net_cash_ps

    # Step 3 — two-stage Gordon on the FY2027E numerator, plus net cash, minus the
    # haircut on cash the model treats as paid but Apple spends on buybacks (A14):
    # two-stage form → (actual retention − b1) × window EPS (valuation-rules「视同派出」).
    def price(t: str, g2_: float, r_: float, ret: float, b: float) -> tuple[float, float, float]:
        e = eps[t]
        pe = two_stage_pe(g1, n, g2_, ret, r_)
        window_eps = sum(e * (1 + g1) ** j for j in range(n))
        deemed = max(1 - inp["payout_actual"] - b, 0.0) * window_eps
        return pe, deemed, e * pe + net_cash_ps - inp[f"k_{t}"] * deemed

    def tier(t: str, g2_: float = g2, r_: float = r) -> dict[str, float]:
        ic, roic, b = capital_base(eps[t], ic0, None)
        pe, deemed, anchor = price(t, g2_, r_, roic, b)
        return dict(ic=ic, roic=roic, b=b, pe=pe, deemed=deemed, anchor=anchor)

    rows = {t: tier(t) for t in TIERS}
    L, M, H = (rows[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    flat_errs, flat = flat_multiple_ladder(tuple(eps[t] for t in TIERS), rows["m"]["pe"])
    errors += flat_errs
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    errors += check_branch(g2, rows["m"]["roic"], r, inp["payout_actual"], "M")
    modelled, gap = payout_gap(g2, rows["m"]["roic"], inp["payout_actual"])
    if H / inp["eps_ttm"] > inp["pe_own_top"]:
        errors.append(f"H = {H / inp['eps_ttm']:.1f}× TTM EPS exceeds own band top {inp['pe_own_top']}× (2c-ex)")
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 (A10)")

    # Candidate band: g2 = 6% on the whole company (A12); same formula, one input swapped.
    cand = tuple(tier(t, g2_=inp["g2_cand"])["anchor"] for t in TIERS)
    if not (cand[0] < cand[1] < cand[2]):
        errors.append(f"candidate L′<M′<H′ violated: {cand}")
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A12)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > 0.05:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g1={g1:.4f} n={n}  "
          f"g2={g2:g} (= {inp['w_hw']:.4f}×{inp['g2_hw']:g} + {1 - inp['w_hw']:.4f}×{inp['g2_svc']:g})")
    print(f"net cash/share {net_cash_ps:.2f}  IC0/share {ic0:.3f}  FY2028E mean {fy28:.3f}")
    for t in TIERS:
        x = rows[t]
        print(f"{t.upper()}: EPS27 {eps[t]:.2f}  IC {x['ic']:.3f}  ROIC {x['roic']:.0%}  b1 {x['b']:.3f}  "
              f"PE {x['pe']:.2f}  deemed-paid {x['deemed']:.2f} × k {inp[f'k_{t}']:g}  anchor {x['anchor']:.2f}  "
              f"(FY28 post-transition EPS {eps[t] * (1 + g1):.2f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} (分子比 {eps['l'] / eps['m']:.3f} × 倍数比 {rows['l']['pe'] / rows['m']['pe']:.3f}) "
          f"H/M={H / M:.3f} (分子比 {eps['h'] / eps['m']:.3f} × 倍数比 {rows['h']['pe'] / rows['m']['pe']:.3f}) "
          f"width={(H - L) / (2 * M):.3f} V_opt/M=0")
    print(f"flat-multiple ladder @ {rows['m']['pe']:.2f}: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    print(f"candidate (g2 {inp['g2_cand']:g}): L′={cand[0]:.2f} M′={cand[1]:.2f} H′={cand[2]:.2f}")
    print(f"③ band: M = {M / inp['eps_ttm']:.1f}× TTM EPS {inp['eps_ttm']} vs own band 2020-01..2026-08 "
          f"[{inp['pe_own_min']}, {inp['pe_own_top']}] (trailing vs forward, <6 same-earnings months → not applicable)")
    print(f"payout_gap (M): modelled {modelled:.0%} vs actual {inp['payout_actual']:.0%} → {gap:+.0%} (单调区, sign only)")

    # Sensitivities (disclosure only).
    for label, gg in (("g2 −1pp", g2 - 0.01), ("g2 +1pp", g2 + 0.01)):
        s = tuple(tier(t, g2_=gg)["anchor"] for t in TIERS)
        print(f"  sens {label:8s} L/M/H {s[0]:.1f}/{s[1]:.1f}/{s[2]:.1f}")
    for label, cap_base, cap in (("book ROE", inp["bps_q3_26"], None), ("ROE cap 60% (LLY)", inp["bps_q3_26"], ROE_CAP_LLY)):
        s = []
        for t in TIERS:
            _, ret, b = capital_base(eps[t], cap_base, cap)
            s.append(price(t, g2, r, ret, b)[2])
        print(f"  sens {label:18s} L/M/H {s[0]:.1f}/{s[1]:.1f}/{s[2]:.1f}")
    print(f"  sens k = 0        M {rows['m']['anchor'] + inp['k_m'] * rows['m']['deemed']:.1f}")
    perp_deemed = max(1 - inp["payout_actual"] - g2 / rows["m"]["roic"], 0) * eps["m"] / (r - g2)
    print(f"  sens single-stage perpetual deemed-paid form (LLY): −{inp['k_m'] * perp_deemed:.1f} on M (disclosure)")
    tac = (eps["m"] - inp["tac_eps"]) * rows["m"]["pe"] + net_cash_ps - inp["k_m"] * rows["m"]["deemed"]
    print(f"  stress TAC loss (M world − {inp['tac_eps']} EPS): {tac:.1f}")
    print(f"  E_M/r + net cash = {eps['m'] / r + net_cash_ps:.1f}")

    # Runway table: EPS grows g_h for N years from FY2027E, then g2 (replaces the FY2028 transition).
    print("runway (value/share, r, g2 fixed; N=0 is single-stage):")
    print("  g_h   " + "  ".join(f"N={k:>2}" for k in RUNWAY_N))
    for gh in RUNWAY_G:
        vals = [eps["m"] * two_stage_pe(gh, k, g2, rows["m"]["roic"], r) + net_cash_ps for k in RUNWAY_N]
        print(f"  {gh:4.0%}  " + "  ".join(f"{v:5.0f}" for v in vals))

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1; EPS, g, ROIC stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(tier(t, r_=r + dr)["anchor"] for t in TIERS)  # type: ignore[return-value]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("AAPL.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
