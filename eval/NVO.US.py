#!/usr/bin/env python3
"""NVO.US (Novo Nordisk ADR) valuation eval — recompute anchors from frameworks/NVO.US.md.

frameworks/NVO.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: nvo_fy27_consensus_two_stage_gordon_v1

Whole-company scale (rare disease is ~6% of sales, A2c 0–1 hits).  Numerator =
FY2027E adjusted EPS consensus band (DKK, 8 analysts, low / mean / high), the
furthest year with a ≥2-house band.  M / H carry the company's 2030 target
("revenue CAGR in line with peers", consensus 5.5%, margin flat) as a 3-year
stage-1 g1 (FY2028–FY2030); L is the consensus-low world and does not carry the
window (a de-rate world does not also run the growth plan).  Terminal g2 = 1.1%
(Barclays 2028–32 EPS CAGR, single house, no peer anchor): the post-2030
pipeline slightly out-runs the semaglutide LoE erosion.  The company retains
~48% of earnings, so the Gordon retention branch applies and g2 <= 0 would fail
`check_branch`; g2 = 0 (pure offset) is printed as a sensitivity only.

ROE for each tier = tier FY2027E EPS ÷ BPS at the start of FY2027, rolled from
the 2026-06-30 BPS: minus the interim dividend paid after the balance-sheet
date, plus b1 × unbooked FY2026 EPS (b1 = g1/ROE fixed point; L has g1 = 0).

Retained-cash audit: E bucket (capex ≫ D&A, no named end) → full form; the
"modelled-as-paid, actually retained" cash = (actual retention − b1) × window
EPS (numerator year + 3 stage-1 years), haircut k and subtracted from each
anchor.  Anchors are computed in DKK and converted to USD at `fx_dkk_usd`
(1 ADR = 1 ordinary share).

Run:  python3 frameworks/eval/NVO.US.py
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
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "NVO.US.md"
FORMULA_ID = "nvo_fy27_consensus_two_stage_gordon_v1"
TIERS = ("l", "m", "h")
REQUIRED = [
    "fx_dkk_usd", "eps_fy27e_low", "eps_fy27e_consensus", "eps_fy27e_high",
    "eps_fy26e", "eps_h1_26_adj", "bps_h1_26", "dps_interim_26",
    "r_perp", "g1_window", "n_window", "g2", "payout_actual",
    "k_l", "k_m", "k_h", "pe_own_min", "pe_own_top", "eps_ttm_core",
    "net_debt_ebitda", "interest_ebit", "v_opt",
]
CONSENSUS_YEARS = 4     # FY2027 band + FY2028–2030 company target / GS consensus CAGR (A5)
ROE_CAP = 0.60          # valuation-rules「腿归篮」: ROE > 60% → back to dialogue
FIXED_POINT_ITERS = 60
LISTING_CCY = "USD"
RF_TOL = 1e-9


def tier_roe(inp: dict[str, float], eps: float, g1: float) -> tuple[float, float, float]:
    """(BPS at start of FY2027, ROE, b1) — b1 = g1/ROE solved as a fixed point."""
    b1 = 0.0
    unbooked_26 = inp["eps_fy26e"] - inp["eps_h1_26_adj"]
    for _ in range(FIXED_POINT_ITERS):
        bps0 = inp["bps_h1_26"] - inp["dps_interim_26"] + b1 * unbooked_26
        roe = eps / bps0
        b1 = g1 / roe
    return bps0, roe, b1


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
    g1, n, g2 = inp["g1_window"], int(inp["n_window"]), inp["g2"]
    errors += check_g_cap(g2, r, "g2")
    errors += check_transition_years(n, CONSENSUS_YEARS, "n_window")
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition (valuation-rules「杠杆门」)")
    errors += ladder("eps_fy27e", inp["eps_fy27e_low"], inp["eps_fy27e_consensus"], inp["eps_fy27e_high"])

    eps = {"l": inp["eps_fy27e_low"], "m": inp["eps_fy27e_consensus"], "h": inp["eps_fy27e_high"]}
    tier_g1 = {"l": 0.0, "m": g1, "h": g1}   # L = consensus-low world, no growth window (A5)
    fx = inp["fx_dkk_usd"]
    rows = {}
    for t in TIERS:
        bps0, roe, b1 = tier_roe(inp, eps[t], tier_g1[t])
        if roe > ROE_CAP:
            errors.append(f"{t.upper()}: ROE {roe:.1%} > {ROE_CAP:.0%} — back to dialogue")
        pe = two_stage_pe(tier_g1[t], n, g2, roe, r) if tier_g1[t] > 0 else perpetual_pe(g2, roe, r)
        gross = eps[t] * pe
        window_eps = sum(eps[t] * (1 + tier_g1[t]) ** i for i in range(n + 1))
        deemed = max(1 - inp["payout_actual"] - b1, 0.0) * window_eps
        k = inp[f"k_{t}"]
        anchor = gross - k * deemed
        rows[t] = dict(bps0=bps0, roe=roe, b1=b1, pe=pe, gross=gross, deemed=deemed, k=k, anchor=anchor)

    L, M, H = (rows[t]["anchor"] / fx for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    flat_errs, flat = flat_multiple_ladder(tuple(eps[t] / fx for t in TIERS), rows["m"]["pe"])
    errors += flat_errs
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # Branch / payout consistency on the M tier (monotone domain: sign only, gap disclosed).
    errors += check_branch(g2, rows["m"]["roe"], r, inp["payout_actual"], "M")
    modelled, gap = payout_gap(g2, rows["m"]["roe"], inp["payout_actual"])
    # H guard against the own 5-year trailing band top.
    h_pe_ttm = rows["h"]["anchor"] / inp["eps_ttm_core"]
    if h_pe_ttm > inp["pe_own_top"]:
        errors.append(f"H = {h_pe_ttm:.1f}× core TTM EPS exceeds own band top {inp['pe_own_top']}×")
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 (A9: no measured unit for the post-2030 pipeline)")

    print(f"formula_id={FORMULA_ID}  fx={fx}  r={r:g} (篮 {baskets.get('r_perp')})  g1={g1:g}×{n}y  g2={g2:g}")
    for t in TIERS:
        x = rows[t]
        print(
            f"{t.upper()}: EPS27 {eps[t]:.2f} DKK  B0 {x['bps0']:.2f}  ROE {x['roe']:.1%}  b1 {x['b1']:.3f}  "
            f"PE {x['pe']:.2f}  gross {x['gross']:.1f}  deemed-paid {x['deemed']:.1f} × k {x['k']:g} "
            f"= −{x['k'] * x['deemed']:.1f}  anchor {x['anchor']:.1f} DKK = {x['anchor'] / fx:.2f} USD"
        )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f} (USD)")
    print(
        f"L/M={L / M:.3f} (分子比 {eps['l'] / eps['m']:.3f} × 倍数比 {rows['l']['pe'] / rows['m']['pe']:.3f}) "
        f"H/M={H / M:.3f} (分子比 {eps['h'] / eps['m']:.3f} × 倍数比 {rows['h']['pe'] / rows['m']['pe']:.3f}) "
        f"width={(H - L) / (2 * M):.3f} V_opt/M=0"
    )
    print(f"flat-multiple ladder @ M PE {rows['m']['pe']:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f} USD")
    m_ttm = rows["m"]["anchor"] / inp["eps_ttm_core"]
    print(
        f"③ band: M = {m_ttm:.2f}× core TTM EPS vs own 5y trailing band [{inp['pe_own_min']}, {inp['pe_own_top']}] "
        f"(disclosure only); M = {rows['m']['anchor'] / eps['m']:.2f}× FY27E"
    )
    print(f"payout_gap (M): modelled {modelled:.0%} vs actual {inp['payout_actual']:.0%} → {gap:+.0%} (单调区, sign only)")
    # Sensitivities (M only; other inputs fixed).
    _, roe_m, _ = tier_roe(inp, eps["m"], g1)
    for label, gg1, nn, gg2 in (
        ("g2 −1pp", g1, n, g2 - 0.01), ("g2 +1pp", g1, n, g2 + 0.01), ("g2 = 0 (pure offset)", g1, n, 0.0), ("g2 −2pp (GS TGR)", g1, n, -0.02),
        ("g1 = 0 (no window)", 0.0, 0, g2), ("n = 5", g1, 5, g2),
    ):
        pe = two_stage_pe(gg1, nn, gg2, roe_m, r) if gg1 > 0 else perpetual_pe(gg2, roe_m, r)
        m_alt = (eps["m"] * pe - inp["k_m"] * rows["m"]["deemed"]) / fx
        print(f"  sens {label:20s} PE {pe:.2f} → M {m_alt:.2f} USD")
    print(f"  sens k = 0 / 0.4           → M {rows['m']['gross'] / fx:.2f} / {(rows['m']['gross'] - 0.4 * rows['m']['deemed']) / fx:.2f} USD")
    print(f"  篮 7 contrast (1/r, r 15%): {eps['l'] / 0.15 / fx:.2f} / {eps['m'] / 0.15 / fx:.2f} / {eps['h'] / 0.15 / fx:.2f} USD (disclosure only)")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 — the only r in the anchors — while EPS, ROE, b1 and the k row stay
    # put.  Disclosure only: the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        out = []
        for t in TIERS:
            x = rows[t]
            pe = two_stage_pe(tier_g1[t], n, g2, x["roe"], r + dr) if tier_g1[t] > 0 else perpetual_pe(g2, x["roe"], r + dr)
            out.append((eps[t] * pe - x["k"] * x["deemed"]) / fx)
        return out[0], out[1], out[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > RF_TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run feeds the daily digest (output/rates/).
    if not errors:
        write_rf_readings("NVO.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
