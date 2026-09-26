#!/usr/bin/env python3
"""HIMS.US (Hims & Hers Health) valuation eval — recompute anchors from frameworks/HIMS.US.md.

frameworks/HIMS.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: hims_fy27_gaap_consensus_gordon_b7_v1

Earnings scale on the FY2027E GAAP EPS consensus band (11 analysts, −0.09 /
0.42 / 1.44), basket 7 r 15%, perpetual g2 = G_cap 6% (the company's 2030
revenue target has no consensus year behind it, so no stage-1 window).  The
consensus-low world is a loss year, so the earnings-scale L does not exist:
L = asset floor (BPS), scenario_L = 0 reported beside it (construction §1).
ROE is capped at 60% (H tier: 1.44 ÷ BPS 1.39 = 104%).

V_opt is computed, not assumed: 2030 revenue target × the company's own
measured FY2025 GAAP net margin → 2030 EPS → perpetual PE at the ROE cap →
discounted 3 years at r → minus H.  It comes out ≤ 0 because the consensus
high already prices a margin above anything Hims has printed, so 表3 is not
printed and v_opt must be 0.

Candidate band (A2e-7h): Barclays 2027E adjusted EPS (single house) on the
same multiple.  Cross (not a scale): EV/EBITDA per sell-side (Barclays 17×,
JPM 22×) and the multiple the current price pays on consensus-revenue EBITDA.

Run:  python3 eval/HIMS.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_g_cap, check_r, perpetual_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402
# rf_report imports `eval.lib.*`, so the repo root must be importable too.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "HIMS.US.md"
FORMULA_ID = "hims_fy27_gaap_consensus_gordon_b7_v1"
REQUIRED = [
    "price", "shares", "equity", "eps_fy27e_low", "eps_fy27e_consensus", "eps_fy27e_high",
    "r_perp", "g2", "roe_cap", "rev_2030_target", "nm_2025_gaap", "n_opt_years",
    "eps_adj_fy27_house", "ebitda_fy27_jpm", "ebitda_fy27_barc", "m_ev_jpm", "m_ev_barc",
    "rev_fy27e", "ebitda_margin_house", "net_debt", "net_debt_ebitda", "interest_ebit", "v_opt",
]
CAND_TOL = 0.05
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"
# band_at(0) must reproduce the anchors; they are compared unrounded.
RF_TOL = 1e-9


def tier_pe(eps: float, bps: float, roe_cap: float, g2: float, r: float) -> tuple[float, float, float]:
    roe_raw = eps / bps
    roe = min(roe_raw, roe_cap)
    return perpetual_pe(g2, roe, r), roe_raw, roe


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    errors += ladder("eps_fy27e", inp["eps_fy27e_low"], inp["eps_fy27e_consensus"], inp["eps_fy27e_high"])
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition")

    bps = inp["equity"] / inp["shares"]
    # Earnings-scale L does not exist (consensus low is a loss); L = asset floor, scenario reported.
    scenario_l = max(inp["eps_fy27e_low"], 0.0) * 0.0
    floor = bps
    L = max(scenario_l, floor)
    pe_m, roe_m_raw, roe_m = tier_pe(inp["eps_fy27e_consensus"], bps, inp["roe_cap"], g2, r)
    pe_h, roe_h_raw, roe_h = tier_pe(inp["eps_fy27e_high"], bps, inp["roe_cap"], g2, r)
    M = inp["eps_fy27e_consensus"] * pe_m
    H = inp["eps_fy27e_high"] * pe_h
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # V_opt chain (construction §7c-7): 2030 target × measured margin → EPS → PE at cap → PV → − H.
    eps_2030 = inp["rev_2030_target"] * inp["nm_2025_gaap"] / inp["shares"]
    pe_2030 = perpetual_pe(g2, inp["roe_cap"], r)
    pv_opt = eps_2030 * pe_2030 / (1 + r) ** int(inp["n_opt_years"])
    v_opt = max(pv_opt - H, 0.0)
    if abs(inp["v_opt"] - v_opt) > 0.01:
        errors.append(f"v_opt stated {inp['v_opt']} vs computed {v_opt:.2f}")

    # Candidate band: same formula, adjusted-EPS single-house numerator (M′ only; L′/H′ copy the deck).
    pe_c, _, roe_c = tier_pe(inp["eps_adj_fy27_house"], bps, inp["roe_cap"], g2, r)
    M_c = inp["eps_adj_fy27_house"] * pe_c
    # EV/EBITDA cross.
    cross = {
        "JPM": (inp["m_ev_jpm"] * inp["ebitda_fy27_jpm"] - inp["net_debt"]) / inp["shares"],
        "Barclays": (inp["m_ev_barc"] * inp["ebitda_fy27_barc"] - inp["net_debt"]) / inp["shares"],
    }
    ebitda_cons = inp["rev_fy27e"] * inp["ebitda_margin_house"]
    ev_mult_now = (inp["price"] * inp["shares"] + inp["net_debt"]) / ebitda_cons

    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g}  BPS {bps:.3f}  ROE cap {inp['roe_cap']:.0%}")
    print(f"L: floor BPS {floor:.2f} (scenario_L = {scenario_l:.2f}: consensus low {inp['eps_fy27e_low']} is a loss) → {L:.2f}")
    print(f"M: EPS27 {inp['eps_fy27e_consensus']:.2f}  ROE {roe_m_raw:.0%}→{roe_m:.0%}  PE {pe_m:.2f} → {M:.2f}")
    print(f"H: EPS27 {inp['eps_fy27e_high']:.2f}  ROE {roe_h_raw:.0%}→{roe_h:.0%}  PE {pe_h:.2f} → {H:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  scenario_L/M = {scenario_l / M:.2f} (floor wins; <0.3 → construction §1 回对话)")
    print(f"L/M={L / M:.3f} (floor: 分子比 n/a) H/M={H / M:.3f} (分子比 {inp['eps_fy27e_high'] / inp['eps_fy27e_consensus']:.2f} × 倍数比 {pe_h / pe_m:.3f}) width={(H - L) / (2 * M):.3f}")
    print(
        f"V_opt chain: 2030 rev {inp['rev_2030_target']:.0f}M × NM {inp['nm_2025_gaap']:.2%} ÷ {inp['shares']:.1f}M = EPS {eps_2030:.2f} "
        f"× PE {pe_2030:.2f} (g2 {g2:g}, ROE cap, r {r:g}) = {eps_2030 * pe_2030:.2f} @2029 → PV {pv_opt:.2f} − H {H:.2f} → V_opt = {v_opt:.2f}"
    )
    print(f"candidate band (Barclays adj EPS {inp['eps_adj_fy27_house']}): M′ = {M_c:.2f} (PE {pe_c:.2f}, ROE {roe_c:.0%}); L′ = {L:.2f}, H′ = {H:.2f} → check L′<M′: {L < M_c}")
    print(f"EV/EBITDA cross: JPM {cross['JPM']:.2f}  Barclays {cross['Barclays']:.2f}  | price pays {ev_mult_now:.1f}× 2027E EBITDA {ebitda_cons:.0f}M")
    lo, hi = g2 + 0.001, 0.60
    for _ in range(80):
        mid = (lo + hi) / 2
        val = inp["eps_fy27e_consensus"] * perpetual_pe(g2, roe_m, mid)
        lo, hi = (mid, hi) if val > inp["price"] else (lo, mid)
    print(f"implied r(P) on M = {mid:.2%} (δ {(mid - r) * 100:+.1f}pp) ; implied r on candidate M′ = ", end="")
    lo, hi = g2 + 0.001, 0.60
    for _ in range(80):
        mid = (lo + hi) / 2
        val = inp["eps_adj_fy27_house"] * perpetual_pe(g2, roe_c, mid)
        lo, hi = (mid, hi) if val > inp["price"] else (lo, mid)
    print(f"{mid:.2%}")
    print(f"price={inp['price']} zone={zone}  P/H = {inp['price'] / H:.2f}  V_opt/M = {v_opt / M:.2f}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in the M/H multiples; EPS, ROE (cap) and g2 stay put, and L is
    # the BPS floor, which carries no r.  Disclosure only — base deck, no V_opt.
    def band_at(dr: float) -> tuple[float, float, float]:
        m_ = inp["eps_fy27e_consensus"] * tier_pe(inp["eps_fy27e_consensus"], bps, inp["roe_cap"], g2, r + dr)[0]
        h_ = inp["eps_fy27e_high"] * tier_pe(inp["eps_fy27e_high"], bps, inp["roe_cap"], g2, r + dr)[0]
        return L, m_, h_

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at, inp["price"])
    if any(abs(x - y) > RF_TOL for x, y in zip(band_at(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings("HIMS.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
