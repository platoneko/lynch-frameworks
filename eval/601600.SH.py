#!/usr/bin/env python3
"""601600.SH (Chalco) valuation eval.

frameworks/601600.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: chalco_al_spread_gm_bridge_gordon_v5

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 753.3万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate.  Each tier's multiple is Gordon on the axis's shared
g rows (flat 0% / 0% / 0%) at the tier's own forward ROE (NP_x / 中报归母权益)
→ PE 10×/10×/10×.  The axis L rung 4,250 is a GS 2027E supply-glut *level*
that may persist, not a trough that mean-reverts; IAI 3.3% is sensitivity /
stretched only.  The L numerator is that regime, not this company's own trough
year (2023H1 归母 33.66亿 was far lower) — so it takes steady g_L=0; a v4 that
ran the 谷底档 recovery stage on it let L converge on M and was rolled back
(valuation-rules「谷底档」适用范围); g_L 3.3%「谷底回归中枢」was likewise
retired.  The printed 2023H1 trough x 1/r is only the deep_discount pressure
coordinate.  The A-share cluster median that used to be typed in as `pe` is
only a cross coordinate, and the own 5-year TTM PE band a guardrail (very wide
here — the 2023 earnings trough printed 35.7x).

The one thing that makes Chalco different from the other three mounts is where
the profit stops.  2026H1 operating profit was 269.4亿 but only 118.7亿 reached
the parent — listed subsidiaries (Yunnan Aluminium and others) take roughly
41%, up from about 31% in 2025H1, because their earnings are the more
leveraged ones.  That drain is not modelled explicitly; it is carried by the
marginal conversion rate, which is why k must stay far below the other mounts'.
The guard below asserts exactly that, so a future revision cannot quietly
recover the missing four-tenths.

Run:  python3 eval/601600.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.al_bridge import (  # noqa: E402
    REQUIRED, anchors, bridge, check_gordon, check_regression, flat_ladder,
    multiples, pb_floor,
)
from lib.axes import check_al_mount  # noqa: E402
from lib.gordon import implied_g  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "601600.SH.md"
FORMULA_ID = "chalco_al_spread_gm_bridge_gordon_v5"

GP_M_FILING = 670.5  # 亿 CNY, 2026H1 x2 at 26.73%
NP_M_FILING = 237.4  # 亿 CNY, 2026H1 归母 118.71 x2
K_MINORITY_CEILING = 0.50  # §1 属性 A: minorities take ~41% of the margin
SHARES_STATIC = 171.55  # 亿股, LB static total_shares 17,154,971,327
NP_TROUGH_2023H1 = 67.33  # 亿 CNY, 2023H1 归母 33.66 x2 — pressure coordinate only (A13)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    errors += ladder("smelting spread", inp["spread_l"], inp["spread_m"], inp["spread_h"])
    errors += check_al_mount((inp["spread_l"], inp["spread_m"], inp["spread_h"]))
    errors += check_regression(inp, GP_M_FILING, NP_M_FILING)
    errors += check_gordon(inp)
    if abs(inp["shares"] - SHARES_STATIC) > 0.05:
        errors.append(f"shares {inp['shares']} != LB static total_shares {SHARES_STATIC}亿")

    (L, M, H), eps = anchors(inp)
    pes, roes = multiples(inp)
    errors += flat_ladder(eps)

    br = bridge(inp)
    if br["k"] >= K_MINORITY_CEILING:
        errors.append(
            f"marginal conversion k={br['k']:.4f} >= {K_MINORITY_CEILING} — "
            "minorities take ~41% of profit (§1 属性 A); a k this high means "
            "the drain has been modelled away"
        )

    # The asset ruler and the earnings ruler read differently here, and the
    # framework says so (A9).  Print the PB at each anchor rather than assert
    # on it: PB in the upper half of the realised band is a real tension, not
    # an input error.  The floor itself is asserted (A2e-1).
    pb = [x / inp["bps"] for x in (L, M, H)]
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone
    )

    flat = [e * pes[1] for e in eps]
    print(f"601600.SH  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}  "
          f"price={inp['price']:.2f} -> {zone}")
    print(f"  EPS {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"ROE {roes[0]:.1%}/{roes[1]:.1%}/{roes[2]:.1%}  "
          f"PE {pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f}  guardrail [{inp['pe_own_min']}, {inp['pe_own_max']}] OK")
    print(f"  Gordon g (axis rows) L {inp['g2_l']:.1%} | M {inp['g2_m']:.1%} | H {inp['g2_h']:.1%}; "
          f"L numerator {br['np'][0]:.1f}亿 = axis L rung (regime), printed 2023H1 trough {NP_TROUGH_2023H1:.1f}亿 far below (A13)")
    print(f"  L/M={L/M:.3f} = 分子比 {eps[0]/eps[1]:.3f} x 倍数比 {pes[0]/pes[1]:.3f} | "
          f"H/M={H/M:.3f} = 分子比 {eps[2]/eps[1]:.3f} x 倍数比 {pes[2]/pes[1]:.3f} | "
          f"width {(H-L)/(2*M):.1%} | V_opt/M 0")
    print(f"  flat-multiple ladder @PE_M {pes[1]:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"  锚点对应 PB {pb[0]:.2f}/{pb[1]:.2f}/{pb[2]:.2f}  "
          f"(floor {floor:.2f} = pb_low x 报表 bps, 现价 PB {inp['price']/inp['bps']:.2f}) "
          f"→ scenario_L 胜出")
    g_px, ok_px = implied_g(inp["price"] / eps[1], roes[1], inp["r_perp"])
    print(f"  deep_discount 压力坐标: 印过的 2023H1 x 1/r = "
          f"{NP_TROUGH_2023H1 / inp['shares'] / inp['r_perp']:.2f}; "
          f"2025H1 参照 {inp['np_ref'] / inp['shares'] * pes[1]:.2f} @PE_M (conservative 带内坐标)")
    print(f"  交叉尺 (A14): 现价 {inp['price']/eps[1]:.2f}x EPS_M → 市价隐含永续 g {g_px:+.2%} "
          f"({'well-conditioned' if ok_px else 'ill-conditioned'})")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
