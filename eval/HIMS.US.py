#!/usr/bin/env python3
"""HIMS.US (Hims & Hers Health) valuation eval — recompute anchors from frameworks/HIMS.US.md.

frameworks/HIMS.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: hims_fy27_gaap_consensus_gordon_b7_v2

Earnings scale on the FY2027E GAAP EPS consensus band (11 analysts, −0.09 /
0.42 / 1.44), basket 7 r 15%, perpetual g2 = G_cap 6% (the company's 2030
revenue target has no consensus year behind it, so no stage-1 window).  The
consensus-low world is a loss year, so the earnings-scale L does not exist:
L = asset floor (BPS), scenario_L = 0 reported beside it (construction §1).
ROE is capped at 60% (H tier: 1.44 ÷ BPS 1.39 = 104%).

V_opt (valuation-rules「未建模期权」, 2026-10-03): the count comes only from
the company's own named quantity — the 2030 revenue target minus the FY2027
revenue consensus already inside the deck; the unit economics are the FY2027
consensus net margin (company-level consensus, mean EPS × shares ÷ mean
revenue), not the FY2025 snapshot; valued on this ticker's own ruler
(perpetual PE at g2, ROE cap, basket r) in the target year and the increment
discounted back to FY2027 at r.  p_k 0 / 0.25 / 1.0 live in table 3 only.

Candidate band (A2e-7h): Barclays 2027E adjusted EPS (single house) on the
same multiple.  Cross (not a scale): EV/EBITDA per sell-side (Barclays 17×,
JPM 22×) and the 2027E EBITDA on consensus revenue × the Barclays margin
(printed only).

Run:  python3 frameworks/eval/HIMS.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_g_cap, check_r, perpetual_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.zones import cut_points  # noqa: E402
# rf_report imports `eval.lib.*`, so the repo root must be importable too.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "HIMS.US.md"
FORMULA_ID = "hims_fy27_gaap_consensus_gordon_b7_v2"
REQUIRED = [
    "shares", "equity", "eps_fy27e_low", "eps_fy27e_consensus", "eps_fy27e_high",
    "r_perp", "g2", "roe_cap", "rev_2030_target", "nm_2025_gaap", "t_opt",
    "eps_adj_fy27_house", "ebitda_fy27_jpm", "ebitda_fy27_barc", "m_ev_jpm", "m_ev_barc",
    "rev_fy27e", "ebitda_margin_house", "net_debt", "net_debt_ebitda", "interest_ebit",
]
CAND_TOL = 0.05
NUM_YEAR = 2027  # numerator year (FY2027 = t=1, not discounted)
P_TIERS = (0.0, 0.25, 1.0)  # A7 — table 3 only, never an input
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"
# band_at(0) must reproduce the anchors; they are compared unrounded.
RF_TOL = 1e-9


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"^- \\\(V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md, re.MULTILINE)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


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
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # V_opt chain (construction §7c-1 / §7c-7, 2026-10-03): count = named target − consensus already in the deck;
    # unit = FY2027 consensus net margin; own ruler at the target year; increment discounted to the numerator year.
    t_opt = int(inp["t_opt"])
    if t_opt <= NUM_YEAR:
        errors.append("t_opt must lie after the numerator year (A7)")
    opt_rev = inp["rev_2030_target"] - inp["rev_fy27e"]
    nm_cons = inp["eps_fy27e_consensus"] * inp["shares"] / inp["rev_fy27e"]
    pe_opt = perpetual_pe(g2, inp["roe_cap"], r)
    disc = (1 + r) ** (t_opt - NUM_YEAR)

    def v_at(nm: float) -> float:
        return opt_rev * nm / inp["shares"] * pe_opt / disc

    v_opt = v_at(nm_cons)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > CAND_TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs A7 {P_TIERS}")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)

    # Candidate band: same formula, adjusted-EPS single-house numerator (M′ only; L′/H′ copy the deck).
    pe_c, _, roe_c = tier_pe(inp["eps_adj_fy27_house"], bps, inp["roe_cap"], g2, r)
    M_c = inp["eps_adj_fy27_house"] * pe_c
    # EV/EBITDA cross.
    cross = {
        "JPM": (inp["m_ev_jpm"] * inp["ebitda_fy27_jpm"] - inp["net_debt"]) / inp["shares"],
        "Barclays": (inp["m_ev_barc"] * inp["ebitda_fy27_barc"] - inp["net_debt"]) / inp["shares"],
    }
    ebitda_cons = inp["rev_fy27e"] * inp["ebitda_margin_house"]

    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g}  BPS {bps:.3f}  ROE cap {inp['roe_cap']:.0%}")
    print(f"L: floor BPS {floor:.2f} (scenario_L = {scenario_l:.2f}: consensus low {inp['eps_fy27e_low']} is a loss) → {L:.2f}")
    print(f"M: EPS27 {inp['eps_fy27e_consensus']:.2f}  ROE {roe_m_raw:.0%}→{roe_m:.0%}  PE {pe_m:.2f} → {M:.2f}")
    print(f"H: EPS27 {inp['eps_fy27e_high']:.2f}  ROE {roe_h_raw:.0%}→{roe_h:.0%}  PE {pe_h:.2f} → {H:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  scenario_L/M = {scenario_l / M:.2f} (floor wins; <0.3 → construction §1 回对话)")
    print(f"L/M={L / M:.3f} (floor: 分子比 n/a) H/M={H / M:.3f} (分子比 {inp['eps_fy27e_high'] / inp['eps_fy27e_consensus']:.2f} × 倍数比 {pe_h / pe_m:.3f}) width={(H - L) / (2 * M):.3f}")
    print(
        f"V_opt chain: ({inp['rev_2030_target']:.0f} − FY27E {inp['rev_fy27e']:.0f})M = {opt_rev:.0f}M × FY27E consensus NM {nm_cons:.2%} "
        f"÷ {inp['shares']:.1f}M = EPS {opt_rev * nm_cons / inp['shares']:.3f} × PE {pe_opt:.2f} (g2 {g2:g}, ROE cap, r {r:g}) @{t_opt} "
        f"÷ {disc:.4f} → V_opt = {v_opt:.2f}"
    )
    print(f"  zone+V (p {P_TIERS}): {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    print(
        f"  V_opt sensitivity: unit = FY2025 GAAP snapshot NM {inp['nm_2025_gaap']:.2%} → {v_at(inp['nm_2025_gaap']):.2f}; "
        f"H-tier NM {inp['eps_fy27e_high'] * inp['shares'] / inp['rev_fy27e']:.2%} → {v_at(inp['eps_fy27e_high'] * inp['shares'] / inp['rev_fy27e']):.2f}; "
        f"realised 2031 → {v_opt * disc / (1 + r) ** (t_opt + 1 - NUM_YEAR):.2f}"
    )
    print(f"candidate band (Barclays adj EPS {inp['eps_adj_fy27_house']}): M′ = {M_c:.2f} (PE {pe_c:.2f}, ROE {roe_c:.0%}); L′ = {L:.2f}, H′ = {H:.2f} → check L′<M′: {L < M_c}")
    print(f"EV/EBITDA cross: JPM {cross['JPM']:.2f}  Barclays {cross['Barclays']:.2f}  | 2027E EBITDA on consensus revenue × Barclays margin {ebitda_cons:.0f}M")
    print(f"V_opt/M = {v_opt / M:.2f}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in the M/H multiples; EPS, ROE (cap) and g2 stay put, and L is
    # the BPS floor, which carries no r.  Disclosure only — base deck, no V_opt.
    def band_at(dr: float) -> tuple[float, float, float]:
        m_ = inp["eps_fy27e_consensus"] * tier_pe(inp["eps_fy27e_consensus"], bps, inp["roe_cap"], g2, r + dr)[0]
        h_ = inp["eps_fy27e_high"] * tier_pe(inp["eps_fy27e_high"], bps, inp["roe_cap"], g2, r + dr)[0]
        return L, m_, h_

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    if any(abs(x - y) > RF_TOL for x, y in zip(band_at(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings("HIMS.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
