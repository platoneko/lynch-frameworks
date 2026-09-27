#!/usr/bin/env python3
"""002532.SZ (Tianshan Aluminum) valuation eval.

frameworks/002532.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).

formula_id: tianshan_al_spread_gm_bridge_gordon_v5

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 128万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate.  Each tier's multiple is Gordon on the axis's shared
g rows (0% / 0% / 0% → flat 1/r) at the tier's own forward ROE (NP_x / 中报归母权益),
with r the basket the framework names for the single leg (篮 6 周期商品, 13% →
7.69×; valuation-rules「§r 篮子」, gordon.BASKET_R).
The L numerator (48.0亿, the level this company printed for FY2025) is the
axis's L rung — GS 2027E supply-glut 4,250 as a sustainable low regime, not a
trough that must revert, and not this company's own trough year (2023H1 归母
10.19亿 was far lower) — so g_L = 0% same as the platform; a v4 that ran the
谷底档 recovery stage, and a later g_L 3.3%「谷底回归中枢」pass, both overstated
recovery and were rolled back (valuation-rules「谷底档」适用范围; axis g_L→0).
IAI 3.3% is sensitivity / stretched only.  The printed 2023H1 trough x 1/r is
the deep_discount pressure coordinate.  The three-coordinate median that used
to be typed in as `pe` is only a cross coordinate, and the own 5-year TTM PE
band a guardrail (7.69× sits 0.47 turn above its 7.22 floor).  The PB floor is
disclosed, never max()'d into L.

Two guards here are specific to this ticker:

  * **Volume basis.**  The primary-aluminium segment's revenue only covers the
    56万吨 sold outright; another 8万吨 leaves as foil stock, high-purity ingot
    and battery foil.  Reverse-engineering volume from segment revenue gives
    ~99.7万吨 annualised and would understate both spread steps.  vol_al must
    therefore be the interim report's *total* 64万吨 x2, and the guard
    enforces that gap (priced at the axis's M-tier spot, since the framework
    no longer carries a price input of its own).
  * **Multiple.**  Generated, not typed: the 3-year own-PE median (12.10)
    covers the post-listing re-rating and is not allowed to reappear as any
    tier's multiple through the guardrail band.

The integration-shape ordering against Hongqiao lives in 1378.HK's eval, which
reads this table; it is not duplicated here.

Run:  python3 frameworks/eval/002532.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.al_bridge import (  # noqa: E402
    REQUIRED, anchors, bridge, check_gordon, check_regression, flat_ladder,
    multiples, pb_floor,
)
from lib.axes import check_al_mount, load_al_rungs  # noqa: E402
from lib.gordon import perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002532.SZ.md"
FORMULA_ID = "tianshan_al_spread_gm_bridge_gordon_v5"

GP_M_FILING = 131.9  # 亿 CNY, 2026H1 x2 at 37.66%
NP_M_FILING = 83.5   # 亿 CNY, 2026H1 归母 41.77 x2
SEG_SHARE_PRIMARY = 0.6874  # 原铝(不含高纯铝) share of 2026H1 revenue
PE_OWN_MEDIAN_3Y = 12.10  # window covers the post-listing re-rating; not used as pe
SHARES_STATIC = 46.29  # 亿股, LB static total_shares 4,628,737,415
NP_TROUGH_2023H1 = 20.38  # 亿 CNY, 2023H1 归母 10.19 x2 — pressure coordinate only (A14)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    errors += ladder("smelting spread", inp["spread_l"], inp["spread_m"], inp["spread_h"])
    errors += check_al_mount((inp["spread_l"], inp["spread_m"], inp["spread_h"]))
    errors += check_regression(inp, GP_M_FILING, NP_M_FILING)

    # A4: total sales, not the outright-sale slice implied by segment revenue.
    p_al_m = load_al_rungs()["price"]["M"]
    vol_from_segment = inp["rev_m"] * SEG_SHARE_PRIMARY / (p_al_m / 1e4)
    if inp["vol_al"] <= vol_from_segment:
        errors.append(
            f"vol_al {inp['vol_al']:.1f}万吨 <= segment-implied "
            f"{vol_from_segment:.1f}万吨 — must be the interim report's total "
            "sales (64万吨 x2), not the outright-sale slice (A4)"
        )

    # A16: r must be the basket the Inputs row names, not just any basket value.
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (AGENTS.md 篮子声明)")
    errors += check_gordon(inp, baskets.get("r_perp"))
    if abs(inp["shares"] - SHARES_STATIC) > 0.05:
        errors.append(f"shares {inp['shares']} != LB static total_shares {SHARES_STATIC}亿")
    (L, M, H), eps = anchors(inp)
    pes, roes = multiples(inp)
    errors += flat_ladder(eps)

    if max(pes) >= PE_OWN_MEDIAN_3Y:
        errors.append(
            f"generated PE {max(pes):.2f} >= own 3y median {PE_OWN_MEDIAN_3Y} — that window "
            "covers the post-listing re-rating and is not reproducible (§1 属性 E)"
        )

    # Floor is disclosed only (A10): scenario L must clear it, never max() with it.
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}
    )

    br = bridge(inp)
    r = inp["r_perp"]
    flat = [e * pes[1] for e in eps]
    print(f"002532.SZ  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"  r_perp {r:.1%} = 篮 {baskets['r_perp']}  "
          f"EPS {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"ROE {roes[0]:.1%}/{roes[1]:.1%}/{roes[2]:.1%}  "
          f"PE {pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f}  guardrail [{inp['pe_own_min']}, {inp['pe_own_max']}] OK")
    print(f"  Gordon g (axis rows) L {inp['g2_l']:.1%} | M {inp['g2_m']:.1%} | H {inp['g2_h']:.1%}; "
          f"L numerator {br['np'][0]:.1f}亿 = axis L rung (regime) = FY2025 printed 48.18; "
          f"printed 2023H1 trough {NP_TROUGH_2023H1:.1f}亿 far below (A14)")
    print(f"  L/M={L/M:.3f} = 分子比 {eps[0]/eps[1]:.3f} x 倍数比 {pes[0]/pes[1]:.3f} | "
          f"H/M={H/M:.3f} = 分子比 {eps[2]/eps[1]:.3f} x 倍数比 {pes[2]/pes[1]:.3f} | "
          f"width {(H-L)/(2*M):.1%} | V_opt/M 0")
    print(f"  flat-multiple ladder @PE_M {pes[1]:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"  vol_al {inp['vol_al']:.1f}万吨 vs 分部反推 {vol_from_segment:.1f}万吨 "
          "(差额=铝箔坯料/高纯铝/电池箔的间接销售)")
    print(f"  地板（只披露）floor={floor:.2f} (5y low PB x 报表 bps) < L {L:.2f} "
          f"(L 对应 PB {L/inp['bps']:.2f}); not max()'d")
    print(f"  deep_discount 压力坐标: 印过的 2023H1 x 1/r = "
          f"{NP_TROUGH_2023H1 / inp['shares'] / r:.2f}; "
          f"2025H1 参照 {inp['np_ref'] / inp['shares'] * pes[1]:.2f} @PE_M; "
          f"IAI 3.3% 敏感性 L = {eps[0] * perpetual_pe(0.033, roes[0], r):.2f}")
    print(f"  交叉尺 (A15): 锚点 PB {L/inp['bps']:.2f}/{M/inp['bps']:.2f}/{H/inp['bps']:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
