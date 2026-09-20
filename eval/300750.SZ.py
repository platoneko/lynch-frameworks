#!/usr/bin/env python3
"""300750.SZ (CATL / Contemporary Amperex Technology) valuation eval.

frameworks/300750.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: catl_group_ni_fy27_consensus_perpetual_gordon_v2

Main ruler: one numerator (group EPS) and a Gordon multiple from a named
perpetual g, one stage, no transition:

  PE_x   = perpetual_pe(g2_x, ROE_x, r) = min(1, 1 - g2_x/ROE_x) / (r - g2_x)
  anchor = eps_x * PE_x

r is the basket the framework names for the single leg (篮 4 龙头制造, 10% ->
a no-growth business is worth 10x; valuation-rules「§r 篮子」, gordon.BASKET_R),
read from the Inputs row and checked against the 篮 N tag (A20).  The PB floor
and net cash per share are disclosed, never max()'d into L.

Numerator year (裁决顺序 ②): the furthest consensus year that still has >= 2
houses WITH a range is FY2027E (yfinance 13 houses, low / mean / high), so all
three tiers take the FY2027E three points and the +20% FY2026E -> FY2027E step
lives in the numerator.  There is no FY2028 consensus, so there is no year to
hang a g1 on: v1's three-year 20% / 27% transition segment (anchored on a
capacity ratio, not on consensus years) is withdrawn (A19).  FY2027 is the
current fiscal year + 1, so no discounting.

L is a consensus-low world (the most pessimistic house for FY2027), not the
ticker's own realised trough year, so it takes steady g2 on the L-tier ROE —
no recovery stage.  The realised pressure coordinates (freeze x consumption
tax 16.28, FY2025 15.61) are printed under the same ruler as deep_discount
markers only.

g2 source tier: 无同业锚 — no well-conditioned battery peer Gordon g2 to
reverse-solve from (300014.SZ ROE 12.9% ill-conditioned; the rest ROE ~ r or
< 0), so the 2% / 3% / 4% ladder is named per tier (A7) and the own-year band
[10.4, 40.0] is only a fence (A10); the M-tier band-edge implied-g range is
printed so ③ can be read off directly.

ROE (A21): tier EPS ÷ the numerator year's OPENING BPS (end-2026 = E_{n+1}/B_n,
valuation-rules 裁决表 ② as of 62c72a2, 2026-09-21).  The 2Q26 book is rolled
over the 2H26 earnings not yet booked (FY2026E consensus minus 1H26 actual) at
the growth-required retention b1 = g2/ROE (no g1 window, so each tier rolls at
its own g2), closed form BPS = BPS_2Q26 / (1 - g2·N/eps).  Actual retention
above b1 is the B bucket, printed as a disclosure only.

Run:  python3 eval/300750.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import (  # noqa: E402
    check_g_cap, check_r, g_cap, implied_g, payout, perpetual_pe, two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "300750.SZ.md"
FORMULA_ID = "catl_group_ni_fy27_consensus_perpetual_gordon_v2"

TIERS = ("l", "m", "h")
MIN_SPREAD = 0.02          # r - g2 floor (valuation-rules ①)
MIN_CONSENSUS_HOUSES = 2   # a numerator year needs >= 2 houses with a range (②)

# Fields the anchor path is allowed to touch.  Everything else in the Inputs
# table is cross-check material, and the guard below proves it stays out.
FORMULA_FIELDS = frozenset({
    "shares", "equity", "r_perp",
    "eps_l", "eps_m", "eps_h",
    "g2_l", "g2_m", "g2_h",
    "eps_fy26_mean", "ni_1h26",   # only via the 2H26 unbooked earnings in the book roll (A21)
})

REQUIRED = sorted(FORMULA_FIELDS | {
    "price", "bps", "consensus_n_fy27", "payout_3y",
    "eps_fy26_lo", "eps_fy26_hi", "eps_fy26_lb",
    "pe_own_hi_recent", "pe_own_hi", "pe_own_lo",
    "eps_ttm", "eps_fy2025", "eps_freeze", "eps_freeze_tax",
    "tp_street", "tp_consensus", "price_h", "fx_hkdcny",
    "net_cash", "unit_profit_h1", "unit_profit_fy2025",
    "px_low_2026", "px_low_2025", "gp_other_rate",
    "buyback_lo", "buyback_hi", "treasury_shares", "opt_outstanding",
})


def unbooked_eps(inp: dict[str, float]) -> float:
    """2H26 EPS not yet in the 2Q26 book: FY2026E consensus minus the 1H26 actual."""
    return inp["eps_fy26_mean"] - inp["ni_1h26"] * 1e8 / inp["shares"]


def bps_open_2027(inp: dict[str, float], eps: float, g: float) -> float:
    """Opening-2027 (= end-2026) BPS: the 2Q26 book rolled over the unbooked
    2H26 earnings at b1 = g/ROE, closed form since ROE = eps/BPS (A21)."""
    bps_2q26 = inp["equity"] * 1e8 / inp["shares"]
    return bps_2q26 / (1.0 - g * unbooked_eps(inp) / eps)


def forward_roe(inp: dict[str, float], eps: float, g: float) -> float:
    """E_{n+1}/B_n on reported group equity — net cash included, see A9 / A21."""
    return eps / bps_open_2027(inp, eps, g)


def multiple(inp: dict[str, float], eps: float, g2: float) -> float:
    return perpetual_pe(g2, forward_roe(inp, eps, g2), inp["r_perp"])


def anchor(inp: dict[str, float], tag: str) -> float:
    return inp[f"eps_{tag}"] * multiple(inp, inp[f"eps_{tag}"], inp[f"g2_{tag}"])


def same_ruler(inp: dict[str, float], eps: float, g2: float) -> float:
    """A different numerator under the same ruler (own ROE, same g2)."""
    return eps * multiple(inp, eps, g2)


def band_edge_g(inp: dict[str, float], roe: float, pe_edge: float) -> float:
    """Perpetual g that lands the Gordon multiple on a band edge (③)."""
    r = inp["r_perp"]
    lo, hi = -0.10, g_cap(r)
    for _ in range(200):
        mid = (lo + hi) / 2
        if perpetual_pe(mid, roe, r) < pe_edge:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = inp["r_perp"]

    # --- Step 1-2: ladders and the numerator-year qualification (②) ---------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    errors += ladder("g2", inp["g2_l"], inp["g2_m"], inp["g2_h"])
    if inp["consensus_n_fy27"] < MIN_CONSENSUS_HOUSES:
        errors.append(
            f"consensus_n_fy27={inp['consensus_n_fy27']:.0f} < {MIN_CONSENSUS_HOUSES} — "
            f"FY2027E no longer qualifies as the numerator year; fall back to FY2026E (A19)"
        )
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    # A21: the roll BPS = BPS0 / (1 - g·N/eps) diverges at g·N/eps >= 1.
    n_unbooked = unbooked_eps(inp)
    for t in TIERS:
        k = inp[f"g2_{t}"] * n_unbooked / inp[f"eps_{t}"]
        if k >= 1.0:
            errors.append(f"book roll diverges for {t}: g2·N/eps = {k:.3f} >= 1 (A21)")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    # ROE = E_{n+1} / B_n: FY2027E EPS over the OPENING-2027 book, i.e. the 2Q26
    # equity rolled over the 2H26 unbooked earnings at the growth-required
    # retention b1 = g2/ROE — not over today's book (v2 前身: 分母少半年留存)
    # and not to the year-end book (that charges retention 2027 has not yet
    # earned).  No g1 window here, so each tier rolls at its own g2 (A21).
    bps_open = {t: bps_open_2027(inp, inp[f"eps_{t}"], inp[f"g2_{t}"]) for t in TIERS}
    roe = {t: forward_roe(inp, inp[f"eps_{t}"], inp[f"g2_{t}"]) for t in TIERS}
    b1 = {t: inp[f"g2_{t}"] / roe[t] for t in TIERS}
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"b1_{t} = g2/ROE = {b1[t]:.3f} outside (0, 1) (A21)")
    # B bucket (A21 / 留存去向审计): actual retention beyond b1, disclosure only.
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * n_unbooked for t in TIERS}

    # --- Step 3-4: convergence and the retention cost of growth (A8) --------
    # A20: r must be the basket the Inputs row names, not just any basket value.
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for t in TIERS:
        g2 = inp[f"g2_{t}"]
        if roe[t] <= 0:
            errors.append(f"ROE_{t}={roe[t]:.4f} must be positive")
        errors += check_g_cap(g2, r, f"g2_{t}")
        if r - g2 < MIN_SPREAD - 1e-12:
            errors.append(f"r - g2_{t} = {r - g2:.2%} < {MIN_SPREAD:.0%} — perpetuity ill-conditioned")
        pay = payout(g2, roe[t])
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g2 <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g2={g2:.2%} <= 0 — cap not binding")
    if errors:
        return report(errors, "FAIL (convergence/payout)")

    pe = {t: multiple(inp, inp[f"eps_{t}"], inp[f"g2_{t}"]) for t in TIERS}

    # --- Step 5: the own-year fence (A10) and the ③ band-edge read-off --------
    for t in TIERS:
        if not inp["pe_own_lo"] - 1e-9 <= pe[t] <= inp["pe_own_hi"] + 1e-9:
            errors.append(
                f"PE_{t}={pe[t]:.2f} outside own-year band "
                f"[{inp['pe_own_lo']}, {inp['pe_own_hi']}] — ③ band-edge reverse-solve required"
            )
    if pe["h"] > inp["pe_own_hi_recent"] + 1e-9:
        errors.append(
            f"PE_H={pe['h']:.2f} above own-year high since 2023 "
            f"{inp['pe_own_hi_recent']} — H is no longer a modelled world"
        )

    # --- Step 8: the non-formula fields really are non-formula ---------------
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append("anchor path touches a non-formula field")
    if errors:
        return report(errors, "FAIL (guards)")

    # --- Step 9: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # Step 6: a flat multiple must still leave a ladder (A2e-2c).
    eps3 = (inp["eps_l"], inp["eps_m"], inp["eps_h"])
    flat_errs, flat = flat_multiple_ladder(eps3, pe["m"])
    errors += flat_errs
    errors += ladder("flat-multiple", *flat)

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  (r={r:.0%} = 篮 {baskets['r_perp']}, "
          f"零增长={1 / r:.1f}x, 单段永续，无过渡段)")
    print(f"{'档':<3}{'EPS FY27E':>10}{'归母(亿)':>11}{'前瞻ROE':>10}{'g2':>7}"
          f"{'派息率':>9}{'PE':>8}{'锚点CNY':>10}")
    for t in TIERS:
        g2 = inp[f"g2_{t}"]
        ni = inp[f"eps_{t}"] * inp["shares"] / 1e8
        print(f"{t.upper():<3}{inp[f'eps_{t}']:10.3f}{ni:11.2f}{roe[t]:10.2%}"
              f"{g2:7.1%}{payout(g2, roe[t]):9.3f}{pe[t]:8.2f}{anchor(inp, t):10.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    bps_2q26 = inp["equity"] * 1e8 / inp["shares"]
    print(
        f"ROE basis (A21): BPS_2027 年初 = {bps_open['l']:.2f}/{bps_open['m']:.2f}/{bps_open['h']:.2f} "
        f"(2Q26 book {bps_2q26:.2f} rolled over 2H26 unbooked EPS {n_unbooked:.2f} "
        f"= FY2026E {inp['eps_fy26_mean']:.2f} − 1H26 {inp['ni_1h26'] * 1e8 / inp['shares']:.2f} "
        f"at b1 = g2/ROE = {b1['l']:.3f}/{b1['m']:.3f}/{b1['h']:.3f}); "
        f"old basis (2Q26 equity) would read ROE "
        f"{inp['eps_l'] * inp['shares'] / (inp['equity'] * 1e8):.2%}/"
        f"{inp['eps_m'] * inp['shares'] / (inp['equity'] * 1e8):.2%}/"
        f"{inp['eps_h'] * inp['shares'] / (inp['equity'] * 1e8):.2%}"
    )
    print(
        f"B bucket (模型视同派出、实际留存的现金): actual retention {ret_actual:.0%} − b1 → "
        f"{excess_cash['l']:.2f}/{excess_cash['m']:.2f}/{excess_cash['h']:.2f} 元/股 over 2H26 "
        f"(disclosure only; not a leg, not in BPS)"
    )
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(f"分子比 L/M={inp['eps_l'] / inp['eps_m']:.3f} "
          f"H/M={inp['eps_h'] / inp['eps_m']:.3f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.3f} H/M={pe['h'] / pe['m']:.3f}"
          f"  — 两端同质（分子与倍数同向），非 A2e-5 的不对称红线")
    print(f"flat-multiple @PE_M={pe['m']:.2f}: {flat[0]:.2f} / {flat[1]:.2f} / "
          f"{flat[2]:.2f} — 阶梯成立，三档各有独立分子（A2e-2c）")

    # ③ read-off: which perpetual g would put the M multiple on the band edges.
    g_lo = band_edge_g(inp, roe["m"], inp["pe_own_lo"])
    g_hi = band_edge_g(inp, roe["m"], inp["pe_own_hi"])
    print(f"三档 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} ∈ own-year 带 "
          f"[{inp['pe_own_lo']:g}, {inp['pe_own_hi']:g}]；"
          f"PE_H ≤ 2023 年起上沿 {inp['pe_own_hi_recent']:g} ✓")
    print(f"  M 档带边反解 g（③）：[{g_lo:+.2%}, {g_hi:+.2%}"
          f"{'（截于上限）' if g_hi >= g_cap(r) - 1e-6 else ''}] 含 g2_m {inp['g2_m']:.0%} → ③ 不触发")

    # Step 7: the numerator-year magnitude (A19) and the pressure coordinates.
    fy26 = tuple(same_ruler(inp, inp[k], inp[f"g2_{t}"]) for k, t in
                 (("eps_fy26_lo", "l"), ("eps_fy26_mean", "m"), ("eps_fy26_hi", "h")))
    print(f"对照带（A19）FY2026E 三点 × 同一尺：{fy26[0]:.2f} / {fy26[1]:.2f} / {fy26[2]:.2f}"
          f"（Longbridge 合成 FY2026E {inp['eps_fy26_lb']:.2f} → "
          f"{same_ruler(inp, inp['eps_fy26_lb'], inp['g2_m']):.2f}）")
    freeze = same_ruler(inp, inp["eps_freeze_tax"], inp["g2_l"])
    fy25 = same_ruler(inp, inp["eps_fy2025"], inp["g2_l"])
    print(f"压力坐标（deep_discount）：冻结×消费税 {inp['eps_freeze_tax']:.2f} × 同一尺 = {freeze:.2f}；"
          f"FY2025 实测 {inp['eps_fy2025']:.2f} × 同一尺 = {fy25:.2f}")
    # v1 structures, printed as rejected variants: n=3 on capacity (no
    # consensus year to hang it on) and n=1 with g1 = the consensus step.
    roe26 = {t: forward_roe(inp, inp[k], inp[f"g2_{t}"]) for k, t in
             (("eps_fy26_mean", "m"), ("eps_fy26_hi", "h"))}
    g1_m = inp["eps_m"] / inp["eps_fy26_mean"] - 1
    g1_h = inp["eps_h"] / inp["eps_fy26_hi"] - 1
    v1_n1_m = two_stage_pe(g1_m, 1, inp["g2_m"], roe26["m"], r) * inp["eps_fy26_mean"]
    v1_n1_h = two_stage_pe(g1_h, 1, inp["g2_h"], roe26["h"], r) * inp["eps_fy26_hi"]
    v1_n3_m = two_stage_pe(0.20, 3, inp["g2_m"], roe26["m"], r) * inp["eps_fy26_mean"]
    v1_n3_h = two_stage_pe(0.27, 3, inp["g2_h"], roe26["h"], r) * inp["eps_fy26_hi"]
    print(f"v1 结构（已按 ② 收回）：n=1 两段式 g1 = 共识增速 {g1_m:+.1%} / {g1_h:+.1%} → "
          f"M {v1_n1_m:.0f} / H {v1_n1_h:.0f}；n=3 产能过渡 20% / 27% → "
          f"M {v1_n3_m:.2f} / H {v1_n3_h:.2f}（无共识年可挂 g1，不启用）")
    for dg in (-0.01, +0.01):
        alt = [same_ruler(inp, inp[f"eps_{t}"], inp[f"g2_{t}"] + dg) for t in TIERS]
        print(f"敏感性 g2 三档 {dg:+.0%}：{alt[0]:.2f} / {alt[1]:.2f} / {alt[2]:.2f}")

    # Disclosure lines (A20): implied r at the market price on the M-tier
    # world, and the floor references that are never max()'d into L.
    pe_px = inp["price"] / inp["eps_m"]
    print(f"隐含 r(P) = g2_m + payout_m / PE(P) = {inp['g2_m']:.0%} + "
          f"{payout(inp['g2_m'], roe['m']):.3f} / {pe_px:.2f} = "
          f"{inp['g2_m'] + payout(inp['g2_m'], roe['m']) / pe_px:.1%} vs 篮 {baskets['r_perp']} {r:.0%}")
    print(f"地板（只披露）：PB=1.0 → BPS {inp['bps']:.2f} < L {L:.2f}（比值 {inp['bps'] / L:.3f}）；"
          f"净现金 {inp['net_cash']:.2f} 亿 = {inp['net_cash'] * 1e8 / inp['shares']:.1f} 元/股（财务性桶，A9 不另加）；not max()'d")
    print(f"price={inp['price']} zone={zone}")
    for label, px in (
        ("A 股现价", inp["price"]),
        ("本框架 M", M),
        ("本框架 H", H),
        ("H 股折 CNY*", inp["price_h"] * inp["fx_hkdcny"]),
        ("高盛 TP", inp["tp_street"]),
        ("一致 TP", inp["tp_consensus"]),
    ):
        gi, ok = implied_g(px / inp["eps_m"], roe["m"], r)
        flag = "" if gi <= g_cap(r) else f"  （越 {g_cap(r):.0%} 上限）"
        print(f"  {label:<12} {px:7.2f}  隐含 FY2027E PE={px / inp['eps_m']:6.2f}"
              f"  隐含永续 g={gi:+.1%} well_conditioned={ok}{flag}")
    ha = inp["price_h"] * inp["fx_hkdcny"] / inp["price"]
    print(f"  * H 股那一行只作**机制读数**：3750.HK 自由流通仅占总股本 4.72%，"
          f"按 A12 判定为流通盘定价机制，非基本面；MUST NOT 当作市场对增长的看法引用")
    print(f"  A/H（A12，不进主公式、不作上行解释）：H/A={ha:.3f}；"
          f"PE(TTM) A={inp['price'] / inp['eps_ttm']:.2f} H={inp['price_h'] * inp['fx_hkdcny'] / inp['eps_ttm']:.2f}；"
          f"FY2026E 均值 A={inp['price'] / inp['eps_fy26_mean']:.2f}")
    print(f"  股本口径（A17，不进锚点）：回购 {inp['buyback_lo']:.0f}–"
          f"{inp['buyback_hi']:.0f} 亿注销 = "
          f"−{inp['buyback_lo'] * 1e8 / inp['price'] / inp['shares']:.3%}~"
          f"−{inp['buyback_hi'] * 1e8 / inp['price'] / inp['shares']:.3%}；"
          f"激励 +{inp['opt_outstanding'] / inp['shares']:.3%}；"
          f"库存股 {inp['treasury_shares'] / inp['shares']:.3%}")
    print(f"  单位净利 FY2025 {inp['unit_profit_fy2025']:.1f} → "
          f"2026H1 {inp['unit_profit_h1']:.2f} 元/kWh "
          f"({inp['unit_profit_h1'] / inp['unit_profit_fy2025'] - 1:+.1%})；"
          f"净现金 {inp['net_cash']:.0f} 亿不另扣（A9）")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
