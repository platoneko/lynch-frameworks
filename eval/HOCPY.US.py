#!/usr/bin/env python3
"""HOCPY.US (HOYA Corporation ADR) valuation eval — recompute anchors from frameworks/HOCPY.US.md.

frameworks/HOCPY.US.md is the source of truth; this script re-derives
L/M/H / A/B and the candidate band from its §3 Inputs table and exits 1 on
mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so
nothing here reads a quote.

formula_id: hocpy_fy28_consensus_gordon_roic_v1

Whole-company scale: HOYA reports segment profit, D&A and capex but no segment
assets, so leg ROE has no source (valuation-rules「腿归篮」③) and the Life Care /
Information Technology split is reference only (A3).  Numerator = FY2028 (year
to 2028-03) EPS consensus band (JPY, 15 analysts), the furthest year with a
≥2-house band; FY2028 = current fiscal year + 1, not discounted.  No FY2029+
year with a verified ≥2-house count, so no stage-1 window: single-stage Gordon
with g2 = G_cap 6% (named macro cap, no peer anchor).

Retention is priced on ROIC, not book ROE: invested capital = equity − net
cash (net cash is ~half of equity), rolled from 2026-03-31 by b × FY2027E EPS
(b = g2/ROIC fixed point).  Net cash per share (after the final FY2026 dividend
paid in June 2026) is added as a closing item.  Retained-cash audit: C bucket
(capex ≈ D&A) with the retention after the cash dividend spent on buybacks →
full form; the "modelled-as-paid, actually retained" cash is capitalised as a
perpetuity (single-stage form) and haircut by k (source ①: FY2023–FY2026
buyback returns vs r).  Anchors are computed in JPY and converted to USD at
`fx_jpy_usd` (1 ADR = 1 ordinary share).

Run:  python3 frameworks/eval/HOCPY.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, check_transition_years, payout_gap, perpetual_pe, two_stage_pe,
)
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "HOCPY.US.md"
FORMULA_ID = "hocpy_fy28_consensus_gordon_roic_v1"
TIERS = ("l", "m", "h")
REQUIRED = [
    "fx_jpy_usd", "shares", "eps_fy28e_low", "eps_fy28e_consensus", "eps_fy28e_high", "eps_fy27e",
    "equity_mar26", "net_cash_mar26", "dps_final_fy26", "r_perp", "g2", "payout_actual",
    "k_l", "k_m", "k_h", "eps_fy29e_cand", "eps_fy26", "pe_own_min", "pe_own_top",
    "net_debt_ebitda", "interest_ebit", "v_opt",
]
CONSENSUS_YEARS = 0     # no year beyond FY2028 with a verified ≥2-house count (A11)
ROIC_CAP = 0.70         # guard: invested capital this thin would make b noise, back to dialogue
FIXED_POINT_ITERS = 60
LISTING_CCY = "USD"     # ADR listing currency (same as NVO.US); the JPY segment of _AXIS.rates is not built
RF_TOL = 1e-9
CAND_TOL = 0.05


def per_share(inp: dict[str, float]) -> tuple[float, float]:
    """(net cash / share after the June-2026 final dividend, invested capital / share at 2026-03-31)."""
    sh = inp["shares"]
    cash = inp["net_cash_mar26"] / sh - inp["dps_final_fy26"]
    ic = (inp["equity_mar26"] - inp["net_cash_mar26"]) / sh
    return cash, ic


def tier(inp: dict[str, float], eps: float, g1: float, n: int, r: float) -> dict[str, float]:
    """Price one tier: ROIC on invested capital at the start of FY2028, Gordon multiple, deemed-paid row."""
    g2 = inp["g2"]
    cash, ic_mar26 = per_share(inp)
    growth = g1 if n > 0 else g2
    b = 0.0
    for _ in range(FIXED_POINT_ITERS):
        ic0 = ic_mar26 + b * inp["eps_fy27e"]
        roic = eps / ic0
        b = growth / roic
    if n > 0:
        pe = two_stage_pe(g1, n, g2, roic, r)
        # Two-stage form: deemed-paid = (actual retention − b1) × window EPS (numerator year + n).
        deemed = max(1 - inp["payout_actual"] - b, 0.0) * sum(eps * (1 + g1) ** i for i in range(n + 1))
    else:
        pe = perpetual_pe(g2, roic, r)
        # Single-stage form: excess retention capitalised as a perpetuity ÷ (r − g2).
        deemed = max(1 - inp["payout_actual"] - b, 0.0) * eps / (r - g2)
    return dict(ic0=ic0, roic=roic, b=b, pe=pe, gross=eps * pe + cash, deemed=deemed, cash=cash)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = inp["r_perp"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    g2 = inp["g2"]
    errors += check_g_cap(g2, r, "g2")
    errors += check_transition_years(0, CONSENSUS_YEARS, "n (base)")
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition (valuation-rules「杠杆门」)")
    errors += ladder("eps_fy28e", inp["eps_fy28e_low"], inp["eps_fy28e_consensus"], inp["eps_fy28e_high"])

    eps = {"l": inp["eps_fy28e_low"], "m": inp["eps_fy28e_consensus"], "h": inp["eps_fy28e_high"]}
    fx = inp["fx_jpy_usd"]
    rows = {}
    for t in TIERS:
        x = tier(inp, eps[t], 0.0, 0, r)
        if x["roic"] > ROIC_CAP:
            errors.append(f"{t.upper()}: ROIC {x['roic']:.1%} > {ROIC_CAP:.0%} — back to dialogue")
        x["k"] = inp[f"k_{t}"]
        x["anchor"] = x["gross"] - x["k"] * x["deemed"]
        rows[t] = x

    Lj, Mj, Hj = (rows[t]["anchor"] for t in TIERS)
    L, M, H = Lj / fx, Mj / fx, Hj / fx
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    flat_errs, flat = flat_multiple_ladder(tuple(eps[t] for t in TIERS), rows["m"]["pe"])
    errors += flat_errs
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    errors += check_branch(g2, rows["m"]["roic"], r, inp["payout_actual"], "M")
    modelled, gap = payout_gap(g2, rows["m"]["roic"], inp["payout_actual"])
    h_pe = Hj / inp["eps_fy26"]
    if h_pe > inp["pe_own_top"]:
        errors.append(f"H = {h_pe:.1f}× FY2026 EPS exceeds own band top {inp['pe_own_top']}×")
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 (A12: HDD third customer / new plants have no disclosed unit)")

    # Candidate band (A11): FY2029E consensus mean as a one-year stage-1 g1; L′ = L
    # (the consensus-low world carries no transition).  Analyst count unverified.
    g1c = inp["eps_fy29e_cand"] / inp["eps_fy28e_consensus"] - 1
    errors += check_transition_years(1, 1, "n (candidate)")
    cand_rows = {t: tier(inp, eps[t], g1c, 1, r) for t in ("m", "h")}
    cand = (L,) + tuple((cand_rows[t]["gross"] - inp[f"k_{t}"] * cand_rows[t]["deemed"]) / fx for t in ("m", "h"))
    stated = load_framework(FRAMEWORK).candidate
    if stated is None:
        errors.append("候选带 line missing from Outputs (A11)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated, cand):
            if abs(said - got) > CAND_TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    print(f"formula_id={FORMULA_ID}  fx={fx}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g}  n=0")
    for t in TIERS:
        x = rows[t]
        print(
            f"{t.upper()}: EPS28 {eps[t]:.2f} JPY  IC0 {x['ic0']:.0f}  ROIC {x['roic']:.1%}  b {x['b']:.3f}  "
            f"PE {x['pe']:.2f}  +cash {x['cash']:.0f}  gross {x['gross']:.0f}  deemed-paid {x['deemed']:.0f} × k {x['k']:g} "
            f"= −{x['k'] * x['deemed']:.0f}  anchor {x['anchor']:.0f} JPY = {x['anchor'] / fx:.2f} USD"
        )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f} (USD)   JPY {Lj:.0f}/{Mj:.0f}/{Hj:.0f}  A/B {(Lj + Mj) / 2:.0f}/{(Mj + Hj) / 2:.0f}")
    print(
        f"L/M={L / M:.3f} (分子比 {eps['l'] / eps['m']:.3f} × 倍数比 {rows['l']['pe'] / rows['m']['pe']:.3f}) "
        f"H/M={H / M:.3f} (分子比 {eps['h'] / eps['m']:.3f} × 倍数比 {rows['h']['pe'] / rows['m']['pe']:.3f}) "
        f"width={(H - L) / (2 * M):.3f} V_opt/M=0"
    )
    print(f"flat-multiple ladder @ M PE {rows['m']['pe']:.2f}: {flat[0]:.0f}/{flat[1]:.0f}/{flat[2]:.0f} JPY (ex cash)")
    print(
        f"③ band: M = {Mj / inp['eps_fy26']:.2f}× FY2026 EPS vs own trailing band [{inp['pe_own_min']}, {inp['pe_own_top']}] "
        f"(no equal-earnings months → not applicable, disclosure only); M = {Mj / eps['m']:.2f}× FY28E"
    )
    print(f"payout_gap (M): modelled {modelled:.0%} vs cash dividend {inp['payout_actual']:.0%} → {gap:+.0%} (单调区, sign only; deemed-paid row)")
    cash = rows["m"]["cash"]
    print(f"coordinates: E_M/r + C = {eps['m'] / r + cash:.0f}  DDM g_d=g {inp['payout_actual'] * eps['m'] / (r - g2) + cash:.0f} JPY")
    print(
        f"候选带 (FY29E mean {inp['eps_fy29e_cand']:g}, g1 {g1c:.2%} n=1): "
        f"ROIC {cand_rows['m']['roic']:.1%}/{cand_rows['h']['roic']:.1%}  b1 {cand_rows['m']['b']:.3f}/{cand_rows['h']['b']:.3f}  "
        f"PE {cand_rows['m']['pe']:.2f}/{cand_rows['h']['pe']:.2f}  L′/M′/H′={cand[0]:.2f}/{cand[1]:.2f}/{cand[2]:.2f} USD"
    )

    def m_with(**kw: float) -> float:
        alt = dict(inp, **kw)
        rr = kw.get("r_perp", r)
        x = tier(alt, eps["m"], 0.0, 0, rr)
        return (x["gross"] - alt["k_m"] * x["deemed"]) / fx

    print(f"  sens g2 −1pp (5%)              → M {m_with(g2=g2 - 0.01):.2f} USD   (+1pp exceeds G_cap, not shown)")
    print(f"  sens k = 0 / 0.2               → M {m_with(k_m=0.0):.2f} / {m_with(k_m=0.2):.2f} USD")
    wc = inp["net_cash_wc"] / inp["shares"] / fx if "net_cash_wc" in inp else 0.0
    print(f"  sens net cash less 2-month working capital → M {M - wc:.2f} USD (−{wc:.2f})")
    print(f"  sens fx ±5%                    → M {Mj / (fx * 1.05):.2f} / {Mj / (fx * 0.95):.2f} USD")

    # Growth-runway table (M tier ROIC, then g2 forever; incl. cash, before the k row).
    roic_m = rows["m"]["roic"]
    print("runway (USD, M ROIC, cash incl., before k): g \\ years  0 / 5 / 10 / 15")
    for gg in (0.08, 0.10, 0.12, 0.15):
        vals = [eps["m"] * (two_stage_pe(gg, n, g2, roic_m, r) if n else perpetual_pe(g2, roic_m, r)) + cash for n in (0, 5, 10, 15)]
        print(f"  {gg:.0%}: " + " / ".join(f"{v / fx:.0f}" for v in vals))

    # r_f readings (_AXIS.rates USD segment, as for the NVO.US ADR): Δr_f moves r_perp 1:1;
    # EPS, ROIC, b, cash and k stay put.  Disclosure only — the anchors are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        out = []
        for t in TIERS:
            x = rows[t]
            rr = r + dr
            pe = perpetual_pe(g2, x["roic"], rr)
            deemed = max(1 - inp["payout_actual"] - x["b"], 0.0) * eps[t] / (rr - g2)
            out.append((eps[t] * pe + x["cash"] - x["k"] * deemed) / fx)
        return out[0], out[1], out[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > RF_TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("HOCPY.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
