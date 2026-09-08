#!/usr/bin/env python3
"""600011.SH (Huaneng Power International) valuation eval.

frameworks/600011.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: huaneng_tariff_scenario_sixleg_perp_pe_v1

Main ruler: whole-company PE, but the numerator is *built* rather than picked.
Huaneng lost money in both FY2021 and FY2022, so unlike 000543.SZ there is no
"worst year the PE ruler still works on" to hand L.  Instead all three tiers
come from the six domestic generation legs the company discloses (coal / gas /
wind / solar / hydro / biomass), reconciled to the only numerator worth valuing:

    profit before tax (six legs)
      x k_retain          -> profit attributable to the parent
      - perp              -> attributable to ORDINARY shareholders

`perp` is a FIXED amount, not a rate — CNY 73,475m of perpetual bonds sit in
equity and their coupon is paid before ordinary holders see anything.  That is
why the formula subtracts rather than scales, and it is what gives the stock an
earnings elasticity of 1.240: PBT falling 1% costs ordinary EPS 1.240%.

Three口径 decisions drive the answer, so each is re-derived here, not asserted:

  * M uses TTM (four realised quarters), NOT 1H26 annualised.  Q4 has lost
    money three years running (-70.3 / -32.0 / -32.1 CNY 100m), so H2 is worth
    only 11.8%-32.6% of the year and doubling H1 overstates it by 35%-77%.
    The script prints what the rejected口径 does to H/M.
  * Multiples are FLAT, not reverse.  Lynch's reverse rule normally applies to
    cyclicals, but here the numerator spread is narrow (0.796-1.151) while
    own-year PE spans 2.45x — any分位-based reverse ladder inverts the tiers.
    The script proves this by recomputing L with the FY2024 own-year PE.
  * The dividend ruler runs in parallel as an independent check.  Its implied
    multiple (payout / required yield) comes from the charter's >=50% payout
    and peer yields, sharing no parameter with own-year PE, yet lands within
    1.4% — which is what offsets A12's thin two-observation PE band.

Run:  python3 eval/600011.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600011.SH.md"
FORMULA_ID = "huaneng_tariff_scenario_sixleg_perp_pe_v1"

TTM_ORDINARY_EPS = 0.5900   # realised: (116.36 - 78.48 + 54.74) / 156.98
PE_OWN_YEAR_FY24 = 17.89    # what a分位-based reverse policy would hand pe_l
PERP_LEVERAGE = 1.240       # 归母 / 普通股股东, TTM
FLOOR_RECHECK_RATIO = 0.30  # A2e-1: below this the earnings ruler has failed at L
DIV_RULER_TOL = 0.05        # A14: the two parameter systems must not diverge
EPS_ANCHOR_TOL = 0.002      # A6: k_retain is calibrated so M reproduces the TTM

REQUIRED = [
    "price", "price_h", "hkdcny", "shares", "bps",
    "pbt_l", "pbt_m", "pbt_h", "k_retain", "perp",
    "pe_l", "pe_m", "pe_h", "pe_hk", "payout", "req_yield_a", "req_yield_h", "bond10y",
    "dps", "perp_balance", "pb_lo", "ha_ratio", "pbt_h1x2",
]


def eps_of(inp: dict[str, float], pbt: float) -> float:
    """PBT -> ordinary-shareholder EPS.  perp is subtracted, never scaled."""
    return (pbt * inp["k_retain"] - inp["perp"]) / inp["shares"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: numerators, and the tariff label's direction ----------------
    eps = {t: eps_of(inp, inp[f"pbt_{t}"]) for t in ("l", "m", "h")}
    errors += ladder("pbt", inp["pbt_l"], inp["pbt_m"], inp["pbt_h"])
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])

    # A6: k_retain exists to make M reproduce the realised TTM.  If it no longer
    # does, an input has moved without the calibration being redone.
    if abs(eps["m"] - TTM_ORDINARY_EPS) > EPS_ANCHOR_TOL:
        errors.append(
            f"M numerator {eps['m']:.4f} no longer reproduces realised TTM EPS "
            f"{TTM_ORDINARY_EPS} — recalibrate k_retain (A6)"
        )
    if errors:
        return report(errors, "FAIL (numerators)")

    # --- Step 2: anchors.  Multiples are flat; A股 is the primary anchor -----
    # A8: flat is not a stylistic choice here — it is forced by the narrow
    # numerator spread, so the three multiples must actually be equal.
    if not (inp["pe_l"] == inp["pe_m"] == inp["pe_h"]):
        errors.append(
            f"multiple policy violated: pe {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} must be flat (A8)"
        )
        return report(errors, "FAIL (multiples)")
    L, M, H = (eps[t] * inp[f"pe_{t}"] for t in ("l", "m", "h"))
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # H股 rides the same numerator but its own own-year band (A13), quoted HKD.
    hk = {t: eps[t] * inp["pe_hk"] / inp["hkdcny"] for t in ("l", "m", "h")}
    A_h, B_h = cut_points(hk["l"], hk["m"], hk["h"])
    zone_h = zone_of(inp["price_h"], hk["l"], hk["m"], hk["h"])

    # --- Step 3: the three口径 decisions, re-derived -------------------------
    # A8 — why the multiple cannot be reverse: the numerator spread is too narrow.
    l_reverse = eps["l"] * PE_OWN_YEAR_FY24
    if l_reverse / M <= 1.0:
        errors.append(
            f"reverse-multiple guard stale: pe_l={PE_OWN_YEAR_FY24} gives L/M="
            f"{l_reverse / M:.3f} <= 1, so flat is no longer the forced choice (A8)"
        )

    # A14 — dividend ruler shares no parameter with the PE band; must still agree.
    div = {t: eps[t] * inp["payout"] / inp["req_yield_a"] for t in ("l", "m", "h")}
    for tag, anchor_a in zip(("l", "m", "h"), (L, M, H)):
        gap = abs(div[tag] - anchor_a) / anchor_a
        if gap > DIV_RULER_TOL:
            errors.append(
                f"dividend ruler {tag.upper()}={div[tag]:.2f} vs PE ruler {anchor_a:.2f} "
                f"({gap:.1%} > {DIV_RULER_TOL:.0%}) — the two parameter systems have forked"
            )

    # A5/A9 — floor is a reference, never a backstop.
    floor = inp["pb_lo"] * inp["bps"]
    if L / M <= FLOOR_RECHECK_RATIO:
        errors.append(
            f"scenario_L/M = {L / M:.3f} <= {FLOOR_RECHECK_RATIO} — the earnings ruler "
            "has failed at L; A2e-1 requires going back to the conversation"
        )

    # A13 — the axis reads H/A off the two live prices; a stale input shows here.
    ha_live = inp["price_h"] * inp["hkdcny"] / inp["price"]
    if abs(ha_live - inp["ha_ratio"]) > 0.005:
        errors.append(
            f"ha_ratio stated {inp['ha_ratio']} vs live {ha_live:.3f} — "
            "_AXIS.southbound-repricing cross-check would use a stale value"
        )

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'六腿PBT(亿)':>12}{'归母':>9}{'普通股':>9}{'EPS':>9}"
          f"{'A股':>8}{'H股':>8}{'红利尺':>8}")
    for t, anchor_a in zip(("l", "m", "h"), (L, M, H)):
        parent = inp[f"pbt_{t}"] * inp["k_retain"]
        print(f"{t.upper():<3}{inp[f'pbt_{t}']:12.2f}{parent:9.2f}"
              f"{parent - inp['perp']:9.2f}{eps[t]:9.4f}"
              f"{anchor_a:8.2f}{hk[t]:8.2f}{div[t]:8.2f}")

    leverage = (inp["pbt_m"] * inp["k_retain"]) / (inp["pbt_m"] * inp["k_retain"] - inp["perp"])
    print(f"永续债杠杆: 归母/普通股 = {leverage:.3f} (框架称 {PERP_LEVERAGE}); "
          f"余额 {inp['perp_balance']:.0f} 亿 = A股市值的 "
          f"{inp['perp_balance'] / (inp['price'] * inp['shares']):.0%}")
    breakeven = inp["perp"] / inp["k_retain"]
    print(f"盈亏平衡: 六腿跌至 {breakeven:.2f} 亿 (较 M 的 {inp['pbt_m']:.2f} 跌 "
          f"{1 - breakeven / inp['pbt_m']:.1%}) 时普通股股东归零, 分红同步归零")

    eps_alt = eps_of(inp, inp["pbt_h1x2"])
    m_alt = eps_alt * inp["pe_m"]
    print(f"被否决口径①  M 用 2026H1x2 ({inp['pbt_h1x2']:.2f} 亿, EPS {eps_alt:.4f}) -> "
          f"M={m_alt:.2f}, H/M 塌到 {H / m_alt:.3f} — H 与 M 无法区分 (A3)")
    print(f"被否决口径②  倍数按分位反向 pe_l={PE_OWN_YEAR_FY24} -> L={l_reverse:.2f}, "
          f"L/M={l_reverse / M:.3f} > 1 阶梯翻转 (A8)")

    dps_l = eps["l"] * inp["payout"]
    print(f"L 档分红: DPS {dps_l:.4f} vs 当前 {inp['dps']} ({dps_l / inp['dps'] - 1:+.1%}); "
          f"L 隐含股息率 {dps_l / L:.2%} — 股息不是地板 (A14)")
    print(f"红利尺隐含倍数 = payout {inp['payout']} / yield {inp['req_yield_a']} = "
          f"{inp['payout'] / inp['req_yield_a']:.3f} vs pe_m {inp['pe_m']:g}; "
          f"yield 分解 = 国债 {inp['bond10y']:.3%} + 风险溢价 "
          f"{inp['req_yield_a'] - inp['bond10y']:.3%}")

    print(f"地板(参照,不兜底): PB {inp['pb_lo']} x BPS {inp['bps']} = {floor:.2f} "
          f"vs scenario_L {L:.2f}; scenario_L/M = {L / M:.3f} > {FLOOR_RECHECK_RATIO} ✓")

    num_l, num_h = eps["l"] / eps["m"], eps["h"] / eps["m"]
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(f"分子比 L/M={num_l:.3f} H/M={num_h:.3f} | 倍数比 L/M=1.000 H/M=1.000 (flat)")
    print(f"A股 price={inp['price']} zone={zone}")
    print(f"H股 L={hk['l']:.2f} M={hk['m']:.2f} H={hk['h']:.2f} "
          f"A={A_h:.2f} B={B_h:.2f} price={inp['price_h']} zone={zone_h}")
    print(f"_AXIS.southbound-repricing: H/A={ha_live:.3f} (五票中收敛幅度最大: 0.433->0.715)")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
