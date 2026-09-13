#!/usr/bin/env python3
"""000933.SZ (Shenhuo Coal & Power) valuation eval.

frameworks/000933.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: shenhuo_al_spread_gm_bridge_flat_pe_v2

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 151.9万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate, with the coal leg frozen at M in both directions.

Shenhuo carries a coal segment, and 2025H1 was a trough in *both* coal and
aluminium, on top of a high-alumina half for a company that buys its alumina —
its five-year H1 margin series runs 36.17 / 19.86 / 24.44 / 27.07 / 35.61, so
2023H1 and 2022H1 both sit *above* 2025H1 despite lower aluminium prices.  The
axis's L world moves only the smelting spread and freezes alumina low, so that
half-year is *worse* than L and is read back as the deep_discount reference,
not as the anchor.  The guard below asserts that ordering: if the k fitting
point ever stops being the worse corner, A4's story has changed and the
reference must be re-opened, not silently kept.

Run:  python3 eval/000933.SZ.py
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

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "000933.SZ.md"
FORMULA_ID = "shenhuo_al_spread_gm_bridge_flat_pe_v2"

GP_M_FILING = 179.3  # 亿 CNY, 2026H1 x2 at 36.17%
NP_M_FILING = 95.6   # 亿 CNY, 2026H1 归母 47.81 x2
CONSENSUS_TP = 32.05  # 一致目标价; lands on the axis's 7,000 mid-path coordinate (A8)


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

    # A4: the coal-and-alumina double trough must sit below the spread-only L
    # world.  Read straight from the bridge so a rolled fitting point is caught.
    br = bridge(inp)
    np_l = br["np"][0]
    if inp["np_ref"] >= np_l:
        errors.append(
            f"k fitting point {inp['np_ref']:.1f}亿 >= scenario L {np_l:.1f}亿 — "
            "2025H1 (coal + aluminium trough, high alumina) must be the worse "
            "corner; if it is not, A4's reference story must be re-opened"
        )

    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone
    )

    print(f"000933.SZ  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}  "
          f"price={inp['price']:.2f} -> {zone}")
    print(f"  EPS {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"L/M={L/M:.2f} H/M={H/M:.2f}  分子比L={eps[0]/eps[1]:.2f}")
    print(f"  2025H1 参照: 归母 {inp['np_ref']:.1f}亿 → {inp['np_ref']/inp['shares']*inp['pe']:.2f} "
          f"(< L, deep_discount)  L 对应 PB {L/inp['bps']:.2f} (floor {floor:.2f}) → scenario_L 胜出")
    print(f"  M/TP={M/CONSENSUS_TP:.2f} — TP 落在轴 7,000 路径中点坐标上 (A8)")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
