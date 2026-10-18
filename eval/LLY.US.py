#!/usr/bin/env python3
"""LLY.US (Eli Lilly) valuation eval — recompute anchors from frameworks/LLY.US.md.

frameworks/LLY.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: lly_fy27_consensus_gordon_gcap_v1

Whole-company scale (one reported segment).  Numerator = FY2027E EPS consensus
band (USD, 27 analysts, low / mean / high) — the furthest year with a ≥2-house
band; no FY2028+ consensus band exists, so no stage-1 window: the perpetual
g2 sits at the repo cap G_cap = 6% (the named macro ceiling; the GLP-1 market
grows faster than that, and the excess is the `stretched` explanation, not a
tier).  Basket 4, r 10%.

ROE: FY2027E EPS ÷ BPS at the start of FY2027 rolled from 2026-06-30 gives
110–150% because buybacks have shrunk the equity base; the repo's 60% ceiling
(valuation-rules「腿归篮」) is applied as a cap — ROE only enters the multiple
through b = g/ROE, so the cap costs ~1 turn (A4, disclosed).

Retained-cash audit: E bucket (capex 10.8bn vs D&A 2.0bn, no named end) with a
single-stage perpetual form → the "modelled-as-paid, actually retained" cash =
(1 − actual payout − g2/ROE) × E ÷ (r − g2) is disclosure only: the k that used
to haircut it was on the wrong object and is gone (valuation-rules「经营价值与超额现金」④,
A12); λ = 1 with no excess cash, so nothing is subtracted.

Steady-return path and timing (A12): RONIC = the tier ROE (capped 60%) through
y1, linear to rs_steady by y2, Gordon tail after; the FY2027 value sits at
t_n 2027-01-01 and is discounted tau years to the 2026-06-30 book, plus the
2026H2 window's distributable EPS (unbooked × (1 − b)) at tau/2.

Run:  python3 frameworks/eval/LLY.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_branch, check_g_cap, check_r, payout_gap, perpetual_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

# The r_f readings helpers import through the `eval.lib` package, so the repo root joins the path.
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "LLY.US.md"
FORMULA_ID = "lly_fy27_consensus_gordon_gcap_v1"
TIERS = ("l", "m", "h")
REQUIRED = [
    "eps_fy27e_low", "eps_fy27e_consensus", "eps_fy27e_high",
    "eps_fy26e", "eps_h1_26", "bps_h1_26", "dps_post_h1_26",
    "r_perp", "g2", "roe_cap", "payout_actual",
    "pe_own_min", "pe_own_top", "eps_ttm", "net_debt_ebitda", "interest_ebit", "v_opt",
    "tau", "y1", "y2", "rs_steady",
]
FIXED_POINT_ITERS = 60
LISTING_CCY = "USD"
NUM_YEAR = 2027  # numerator year; t_n = 2027-01-01


def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float) -> float:
    """Single-stage multiple on numerator-year earnings with the steady-return path
    (valuation-rules「经营价值与超额现金」② 稳态回报三段): RONIC = forward through
    calendar y1, linear to min(roe, rs) by y2, Gordon tail from y2.  With rs >= roe
    this equals perpetual_pe.  (gordon.py helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def tier_roe(inp: dict[str, float], eps: float, g: float) -> tuple[float, float, float, float]:
    """(BPS at start of FY2027, raw ROE, ROE used (capped), b) — b = g/ROE_used fixed point."""
    b = 0.0
    unbooked_26 = inp["eps_fy26e"] - inp["eps_h1_26"]
    for _ in range(FIXED_POINT_ITERS):
        bps0 = inp["bps_h1_26"] - inp["dps_post_h1_26"] + b * unbooked_26
        roe_raw = eps / bps0
        roe = min(roe_raw, inp["roe_cap"])
        b = g / roe
    return bps0, roe_raw, roe, b


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
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition")
    errors += ladder("eps_fy27e", inp["eps_fy27e_low"], inp["eps_fy27e_consensus"], inp["eps_fy27e_high"])

    eps = {"l": inp["eps_fy27e_low"], "m": inp["eps_fy27e_consensus"], "h": inp["eps_fy27e_high"]}
    tau, y1, y2, rs = inp["tau"], int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]
    unbooked_26 = inp["eps_fy26e"] - inp["eps_h1_26"]

    def price_tier(t: str, r_: float, gg: float = g2) -> dict[str, float]:
        bps0, roe_raw, roe, b = tier_roe(inp, eps[t], gg)
        pe = three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roe, r_)
        gross = eps[t] * pe
        # Timing (A12): value at t_n discounted tau years; 2026H2 window distributable EPS at tau/2.
        window = max(unbooked_26 * (1 - b), 0.0)
        # E bucket, single-stage form: excess retention every year, capitalised as a perpetuity —
        # the 多留部分 (disclosure only; λ = 1, no k).
        excess = max(1 - inp["payout_actual"] - b, 0.0)
        deemed = excess * eps[t] / (r_ - gg)
        anchor = gross * (1 + r_) ** (-tau) + window * (1 + r_) ** (-tau / 2)
        return dict(bps0=bps0, roe_raw=roe_raw, roe=roe, b=b, pe=pe, gross=gross, deemed=deemed,
                    window=window, anchor=anchor)

    rows = {t: price_tier(t, r) for t in TIERS}

    L, M, H = (rows[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    flat_errs, flat = flat_multiple_ladder(tuple(eps[t] for t in TIERS), rows["m"]["pe"])
    errors += flat_errs
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    errors += check_branch(g2, rows["m"]["roe"], r, inp["payout_actual"], "M")
    modelled, gap = payout_gap(g2, rows["m"]["roe"], inp["payout_actual"])
    if H / inp["eps_ttm"] > inp["pe_own_top"]:
        errors.append(f"H = {H / inp['eps_ttm']:.1f}× TTM EPS exceeds own band top {inp['pe_own_top']}×")
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 (A9)")

    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g} (=G_cap)  ROE cap {inp['roe_cap']:.0%}")
    print(f"steady path: ROE to {y1}, linear to {rs:.0%} by {y2}; timing ÷ {(1 + r) ** tau:.4f} (tau {tau:g}y) + window at tau/2")
    for t in TIERS:
        x = rows[t]
        print(
            f"{t.upper()}: EPS27 {eps[t]:.2f}  B0 {x['bps0']:.1f}  ROE raw {x['roe_raw']:.0%} → used {x['roe']:.0%}  "
            f"b {x['b']:.3f}  PE {x['pe']:.2f}  gross {x['gross']:.2f}  window {x['window']:.2f}  "
            f"多留部分(perp, disclosure, λ=1) {x['deemed']:.0f}  anchor {x['anchor']:.2f}"
        )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"L/M={L / M:.3f} (分子比 {eps['l'] / eps['m']:.3f} × 倍数比 1.000) H/M={H / M:.3f} (分子比 {eps['h'] / eps['m']:.3f}) "
        f"width={(H - L) / (2 * M):.3f} V_opt/M=0"
    )
    print(f"flat-multiple ladder @ {rows['m']['pe']:.2f} (gross, before timing): {flat[0]:.0f}/{flat[1]:.0f}/{flat[2]:.0f}")
    print(
        f"③ band: M = {M / inp['eps_ttm']:.1f}× TTM EPS {inp['eps_ttm']} vs own 5y band [{inp['pe_own_min']}, {inp['pe_own_top']}]; "
        f"M = {M / eps['m']:.1f}× FY27E (band is on trailing EPS during +50%/yr growth → not the same base, disclosure only)"
    )
    print(f"payout_gap (M): modelled {modelled:.0%} vs actual {inp['payout_actual']:.0%} → {gap:+.0%} (单调区, sign only)")
    for label, gg in (("g2 5%", 0.05), ("g2 4%", 0.04)):
        x = price_tier("m", r, gg)
        print(f"  sens {label:8s} PE {x['pe']:.2f} → M {x['anchor']:.0f}")
    print(f"  sens steady = forward (no fade, old form) → PE {perpetual_pe(g2, rows['m']['roe'], r):.2f}, "
          f"M {eps['m'] * perpetual_pe(g2, rows['m']['roe'], r) * (1 + r) ** (-tau) + rows['m']['window'] * (1 + r) ** (-tau / 2):.0f}")
    print(f"  sens ROE uncapped  → PE {perpetual_pe(g2, rows['m']['roe_raw'], r):.2f} (b {g2 / rows['m']['roe_raw']:.3f}; old form, no fade)")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves r_perp
    # 1:1 in the Gordon multiple and the timing discount; EPS, g2, ROE (hence b), the
    # steady-return path stay put.  Disclosure only: the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(price_tier(t, r + dr)["anchor"] for t in TIERS)  # type: ignore[return-value]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("LLY.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
