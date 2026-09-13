#!/usr/bin/env python3
"""601600.SH (Chalco) valuation eval.

frameworks/601600.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: chalco_al_spread_gm_bridge_flat_pe_v2

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 753.3万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate.

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
    REQUIRED, anchors, bridge, check_regression, flat_ladder, pb_floor,
)
from lib.axes import check_al_mount  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "601600.SH.md"
FORMULA_ID = "chalco_al_spread_gm_bridge_flat_pe_v2"

GP_M_FILING = 670.5  # 亿 CNY, 2026H1 x2 at 26.73%
NP_M_FILING = 237.4  # 亿 CNY, 2026H1 归母 118.71 x2
K_MINORITY_CEILING = 0.50  # §1 属性 A: minorities take ~41% of the margin


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

    (L, M, H), eps = anchors(inp)
    errors += flat_ladder(eps)

    br = bridge(inp)
    if br["k"] >= K_MINORITY_CEILING:
        errors.append(
            f"marginal conversion k={br['k']:.4f} >= {K_MINORITY_CEILING} — "
            "minorities take ~41% of profit (§1 属性 A); a k this high means "
            "the drain has been modelled away"
        )

    # The asset ruler disagrees with the earnings ruler here, and the framework
    # says so (A9).  Print the PB at each anchor rather than assert on it: PB
    # above the 5-year high is a real tension, not an input error.  The floor
    # itself is asserted (A2e-1).
    pb = [x / inp["bps"] for x in (L, M, H)]
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone
    )

    print(f"601600.SH  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}  "
          f"price={inp['price']:.2f} -> {zone}")
    print(f"  EPS {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"L/M={L/M:.2f} H/M={H/M:.2f}  分子比L={eps[0]/eps[1]:.2f}")
    print(f"  锚点对应 PB {pb[0]:.2f}/{pb[1]:.2f}/{pb[2]:.2f}  "
          f"(floor {floor:.2f} = 5y low PB x bps, 现价 PB {inp['price']/inp['bps']:.2f}) "
          f"→ scenario_L 胜出")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
