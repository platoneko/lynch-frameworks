#!/usr/bin/env python3
"""HIMS.US (Hims & Hers Health) valuation eval — recompute anchors from frameworks/HIMS.US.md.

frameworks/HIMS.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: hims_fy28_consensus_gordon_b4_v3

Earnings scale on the FY2028E EPS consensus band (Zacks via Nasdaq, 4
estimates, 0.50 / 0.85 / 1.18; Zacks basis excludes non-recurring items and
keeps SBC — read as near-GAAP, A2), basket 4 r 10% (the basket-7 reasons were
supply dependence, regulation and no profits — none is a counterparty or
country test; A4), perpetual g2 = 4% US long-run nominal growth, 「无同业锚」
(A5).  FY2028 is the farthest year with >= 2 houses AND a range, so it is the
numerator (valuation-rules 裁决顺序 ②), discounted one year (FY2028 = current
FY + 2).  No stage-1 window: FY2029 has a single house (candidate band).  BPS
at the start of FY2028 rolls the unbooked consensus profit (2026H2, FY2027)
at the retention g2/ROE needs.  ROE is capped at 60%.

V_opt (valuation-rules「未建模期权」): count = the 2030 revenue target minus
the revenue the deck already holds in 2030 (FY2028 revenue grown at g2);
unit economics = FY2028 consensus net margin (farthest visible year); own
ruler in 2030, discounted to FY2027 (t = 1) at r.  p_k 0 / 0.25 / 1.0.

Candidate band: FY2029 single house as g1 (n = 1) on M/H; L carries no
transition.  Candidate coordinate (not a band): Barclays 2027E adjusted EPS.
Basket-7 comparison band, correction-gate coordinates and the neutral band's
PE readings are printed (disclosure).  Cross: EV/EBITDA per sell-side.

Run:  python3 frameworks/eval/HIMS.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import basket_r, check_branch, check_g_cap, check_r, perpetual_pe, two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.zones import cut_points  # noqa: E402
# rf_report imports `eval.lib.*`, so the repo root must be importable too.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "HIMS.US.md"
FORMULA_ID = "hims_fy28_consensus_gordon_b4_v3"
REQUIRED = [
    "shares", "equity", "eps_fy26e_consensus", "eps_h1_26_gaap", "eps_fy27e_consensus",
    "eps_fy28e_low", "eps_fy28e_consensus", "eps_fy28e_high", "eps_fy29e_single",
    "r_perp", "r_disc", "g2", "roe_cap",
    "rev_fy27e", "rev_growth_28", "rev_2030_target", "t_opt",
    "nm_2025_gaap", "adj_ebitda_2030_target", "adj_ebitda_margin_2025",
    "eps_adj_fy27_house", "ebitda_fy27_jpm", "ebitda_fy27_barc", "m_ev_jpm", "m_ev_barc",
    "ebitda_margin_house", "net_debt", "net_debt_ebitda", "interest_ebit",
    "m_prev", "pb_min_5y", "close_eq_lo", "close_eq_hi",
]
TOL = 0.05
NUM_YEAR = 2028        # numerator year; FY2027 = t=1, so FY2028 is discounted one year
T1_YEAR = 2027
INITIAL_BASKET = 7     # A4 — the overturned basket, comparison band only
P_TIERS = (0.0, 0.25, 1.0)  # A7 — table 3 only, never an input
LISTING_CCY = "USD"
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


def stated_candidate(md: str) -> tuple[float, float, float] | None:
    m = re.search(r"候选带（[^）]*）：L′ = \*\*([0-9.]+)\*\* · M′ = \*\*([0-9.]+)\*\* · H′ = \*\*([0-9.]+)\*\*", md)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2, cap = inp["r_perp"], inp["g2"], inp["roe_cap"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell")
    if "r_disc" in baskets:
        errors.append("r_disc is disclosure-only and must not carry 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if abs(inp["r_disc"] - r) > 1e-12:
        errors.append("r_disc must equal r_perp (year-drift discount at the basket r)")
    errors += check_g_cap(g2, r, "g2")
    eps28 = (inp["eps_fy28e_low"], inp["eps_fy28e_consensus"], inp["eps_fy28e_high"])
    errors += ladder("eps_fy28e", *eps28)
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition")

    shares = inp["shares"]
    bps0 = inp["equity"] / shares
    unbooked = (inp["eps_fy26e_consensus"] - inp["eps_h1_26_gaap"]) + inp["eps_fy27e_consensus"]

    def model(rr: float, gg: float) -> tuple[float, list[tuple[float, float, float, float]], tuple[float, float, float]]:
        """BPS at the start of FY2028 and per-tier (ROE raw, ROE, PE, anchor) at basket r = rr, g2 = gg."""
        bps = bps0
        for _ in range(50):  # retention b = g2 / ROE_M, ROE_M depends on the rolled BPS
            bps = bps0 + gg / min(eps28[1] / bps, cap) * unbooked
        disc = (1 + rr) ** (NUM_YEAR - T1_YEAR)
        rows = []
        for e in eps28:
            roe = min(e / bps, cap)
            pe = perpetual_pe(gg, roe, rr)
            rows.append((e / bps, roe, pe, e * pe / disc))
        return bps, rows, tuple(x[3] for x in rows)

    bps, rows, (L, M, H) = model(r, g2)
    floor = bps0
    if L < floor:
        errors.append(f"scenario L {L:.2f} below the BPS floor {floor:.2f} — floor rule applies, re-derive")
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    errors += check_branch(g2, rows[1][1], r, 0.0, "g2")
    pe_m = rows[1][2]
    flat = tuple(e * pe_m / (1 + r) for e in eps28)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder collapsed (construction §2c)")

    # V_opt chain.
    t_opt = int(inp["t_opt"])
    if t_opt <= NUM_YEAR:
        errors.append("t_opt must lie after the numerator year (A7)")
    rev28 = inp["rev_fy27e"] * inp["rev_growth_28"]
    nm28 = eps28[1] * shares / rev28

    def v_at(nm: float, rr: float = r, gg: float = g2, t: int = t_opt) -> tuple[float, float, float]:
        base30 = rev28 * (1 + gg) ** (t - NUM_YEAR)
        k_rev = inp["rev_2030_target"] - base30
        val = k_rev * nm / shares * perpetual_pe(gg, cap, rr) / (1 + rr) ** (t - T1_YEAR)
        return base30, k_rev, val

    base30, k_rev, v_opt = v_at(nm28)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs A7 {P_TIERS}")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    nm_infer = inp["adj_ebitda_2030_target"] / inp["rev_2030_target"] - (inp["adj_ebitda_margin_2025"] - inp["nm_2025_gaap"])
    nm29 = inp["eps_fy29e_single"] * shares / (rev28 * inp["rev_growth_28"])
    nm27 = inp["eps_fy27e_consensus"] * shares / inp["rev_fy27e"]

    # Candidate band: FY2029 single house as g1, n = 1, on M/H; L carries no transition.
    g1 = inp["eps_fy29e_single"] / eps28[1] - 1
    cand = (L,) + tuple(
        e * two_stage_pe(g1, 1, g2, roe, r) / (1 + r) for e, (_, roe, _, _) in zip(eps28[1:], rows[1:])
    )
    said_c = stated_candidate(md)
    if said_c is None or any(abs(a - b) > TOL for a, b in zip(said_c, cand)):
        errors.append(f"candidate band stated {said_c} vs recomputed {tuple(round(x, 4) for x in cand)}")
    if not (cand[0] < cand[1] < cand[2]):
        errors.append("candidate band needs L′ < M′ < H′")
    # Candidate coordinate: Barclays FY2027 adjusted EPS on the same ruler (FY2027 = t1, not discounted).
    pe_b = perpetual_pe(g2, min(inp["eps_adj_fy27_house"] / bps0, cap), r)
    m_barc = inp["eps_adj_fy27_house"] * pe_b

    # Basket-7 comparison band (initial basket, overturned; disclosure only).
    r7 = basket_r(INITIAL_BASKET)
    _, _, (L7, M7, H7) = model(r7, g2)
    v7 = v_at(nm28, rr=r7)[2]

    cross = {
        "JPM": (inp["m_ev_jpm"] * inp["ebitda_fy27_jpm"] - inp["net_debt"]) / shares,
        "Barclays": (inp["m_ev_barc"] * inp["ebitda_fy27_barc"] - inp["net_debt"]) / shares,
    }

    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g} (无同业锚)  ROE cap {cap:.0%}")
    print(f"BPS 2026-06-30 {bps0:.4f} → start FY2028 {bps:.4f} (unbooked consensus {unbooked:+.3f} × b = g2/ROE_M)")
    for t, e, (rr_, roe, pe, a) in zip("LMH", eps28, rows):
        print(f"{t}: EPS28 {e:.2f}  ROE {rr_:.1%}→{roe:.1%}  PE {pe:.2f} (payout {1 - g2 / roe:.1%})  ÷ {(1 + r):.2f} → {a:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  (floor BPS {floor:.2f} loses)")
    print(f"L/M={L / M:.3f} (分子比 {eps28[0] / eps28[1]:.3f} × 倍数比 {rows[0][2] / pe_m:.3f})  "
          f"H/M={H / M:.3f} (分子比 {eps28[2] / eps28[1]:.3f} × 倍数比 {rows[2][2] / pe_m:.3f})  width={(H - L) / (2 * M):.3f}  V_opt/M={v_opt / M:.2f}")
    print(f"flat pe_M: {flat[0]:.2f} / {flat[1]:.2f} / {flat[2]:.2f}")
    for gg in (g2 - 0.01, g2 + 0.01):
        print(f"  g2 {gg:.0%}: L/M/H " + " / ".join(f"{x:.2f}" for x in model(r, gg)[2]))
    print(
        f"V_opt chain: FY28 revenue {rev28:.0f}M (FY27 {inp['rev_fy27e']:.0f} × {inp['rev_growth_28']}) → deck 2030 {base30:.0f}M; "
        f"count {inp['rev_2030_target']:.0f} − {base30:.0f} = {k_rev:.0f}M × NM28 {nm28:.2%} ÷ {shares}M = EPS {k_rev * nm28 / shares:.3f} "
        f"× PE {perpetual_pe(g2, cap, r):.2f} @{t_opt} ÷ {(1 + r) ** (t_opt - T1_YEAR):.4f} → V_opt = {v_opt:.2f}"
    )
    print(f"  zone+V (p {P_TIERS}): {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    print(
        f"  V_opt sensitivity: FY29 single NM {nm29:.2%} → {v_at(nm29)[2]:.2f}; inferred 2030 NM {nm_infer:.2%} → {v_at(nm_infer)[2]:.2f}; "
        f"2025 GAAP {inp['nm_2025_gaap']:.2%} → {v_at(inp['nm_2025_gaap'])[2]:.2f}; FY27 consensus {nm27:.2%} → {v_at(nm27)[2]:.2f}; "
        f"realised 2031 → {v_at(nm28, t=t_opt + 1)[2]:.2f}"
    )
    print(f"candidate band (FY29 single {inp['eps_fy29e_single']}, g1 {g1:.1%}, n=1, M/H only): L′ {cand[0]:.2f} M′ {cand[1]:.2f} H′ {cand[2]:.2f}")
    print(f"candidate coordinate (Barclays FY27 adj EPS {inp['eps_adj_fy27_house']}): M′ = {m_barc:.2f} (PE {pe_b:.2f})")
    print(f"basket-{INITIAL_BASKET} comparison band (r {r7:g}): L/M/H {L7:.2f}/{M7:.2f}/{H7:.2f}  V_opt {v7:.2f}")
    print(f"EV/EBITDA cross: JPM {cross['JPM']:.2f}  Barclays {cross['Barclays']:.2f}  | FY27 EBITDA on consensus revenue × Barclays margin {inp['rev_fy27e'] * inp['ebitda_margin_house']:.0f}M")
    # Correction gate (valuation-rules「纠正对账门」): M moved > 25% → coordinates, disclosure (user ruled 2026-10-04).
    e_over_r = eps28[1] / r / (1 + r)
    coords = {
        "① previous M": inp["m_prev"],
        "② E_M/r (FY28, ÷1.10)": e_over_r,
        "④ same-earnings months low": inp["close_eq_lo"],
        "④ same-earnings months high": inp["close_eq_hi"],
        "⑥ BPS × own 5y min PB": bps0 * inp["pb_min_5y"],
    }
    print(f"correction gate: M {M:.2f} vs previous {inp['m_prev']} ({M / inp['m_prev'] - 1:+.0%})")
    for k, c in coords.items():
        print(f"  {k}: {c:.2f}  M {M / c - 1:+.0%}")
    inside = any(abs(M / c - 1) <= 0.20 for c in coords.values())
    print(f"  any coordinate within 20%: {inside} (disclosed in Outputs; user ruled to land)")
    print(f"neutral band [A,B) PE: FY28E {A / eps28[1]:.1f}–{B / eps28[1]:.1f}×  FY27E {A / inp['eps_fy27e_consensus']:.1f}–{B / inp['eps_fy27e_consensus']:.1f}×  TTM GAAP < 0 n/a")

    def band_at(dr: float) -> tuple[float, float, float]:
        return model(r + dr, g2)[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    if any(abs(x - y) > RF_TOL for x, y in zip(band_at(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("HIMS.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
