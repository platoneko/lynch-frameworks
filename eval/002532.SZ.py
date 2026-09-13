#!/usr/bin/env python3
"""002532.SZ (Tianshan Aluminum) valuation eval.

frameworks/002532.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: tianshan_al_spread_gm_bridge_flat_pe_v2

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 128万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate.

Two guards here are specific to this ticker:

  * **Volume basis.**  The primary-aluminium segment's revenue only covers the
    56万吨 sold outright; another 8万吨 leaves as foil stock, high-purity ingot
    and battery foil.  Reverse-engineering volume from segment revenue gives
    ~99.7万吨 annualised and would understate both spread steps.  vol_al must
    therefore be the interim report's *total* 64万吨 x2, and the guard
    enforces that gap (priced at the axis's M-tier spot, since the framework
    no longer carries a price input of its own).
  * **Multiple.**  The 3-year own-PE median (12.10) covers the post-listing
    re-rating and must not be what `pe` is set to.

The integration-shape ordering against Hongqiao lives in 1378.HK's eval, which
reads this table; it is not duplicated here.

Run:  python3 eval/002532.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.al_bridge import (  # noqa: E402
    REQUIRED, anchors, bridge, check_regression, flat_ladder, pb_floor,
)
from lib.axes import check_al_mount, load_al_rungs  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "002532.SZ.md"
FORMULA_ID = "tianshan_al_spread_gm_bridge_flat_pe_v2"

GP_M_FILING = 131.9  # 亿 CNY, 2026H1 x2 at 37.66%
NP_M_FILING = 83.5   # 亿 CNY, 2026H1 归母 41.77 x2
SEG_SHARE_PRIMARY = 0.6874  # 原铝(不含高纯铝) share of 2026H1 revenue
PE_OWN_MEDIAN_3Y = 12.10  # window covers the post-listing re-rating; not used as pe


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

    # A4: total sales, not the outright-sale slice implied by segment revenue.
    p_al_m = load_al_rungs()["price"]["M"]
    vol_from_segment = inp["rev_m"] * SEG_SHARE_PRIMARY / (p_al_m / 1e4)
    if inp["vol_al"] <= vol_from_segment:
        errors.append(
            f"vol_al {inp['vol_al']:.1f}万吨 <= segment-implied "
            f"{vol_from_segment:.1f}万吨 — must be the interim report's total "
            "sales (64万吨 x2), not the outright-sale slice (A4)"
        )

    (L, M, H), eps = anchors(inp)
    errors += flat_ladder(eps)

    if inp["pe"] >= PE_OWN_MEDIAN_3Y:
        errors.append(
            f"pe {inp['pe']} >= own 3y median {PE_OWN_MEDIAN_3Y} — that window "
            "covers the post-listing re-rating and is not reproducible (§1 属性 E)"
        )

    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone
    )

    br = bridge(inp)
    print(f"002532.SZ  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}  "
          f"price={inp['price']:.2f} -> {zone}")
    print(f"  EPS {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"L/M={L/M:.2f} H/M={H/M:.2f}  分子比L={eps[0]/eps[1]:.2f}")
    print(f"  vol_al {inp['vol_al']:.1f}万吨 vs 分部反推 {vol_from_segment:.1f}万吨 "
          "(差额=铝箔坯料/高纯铝/电池箔的间接销售)")
    print(f"  L 对应 PB {L/inp['bps']:.2f} (floor {floor:.2f} = 5y low PB x bps) "
          f"→ scenario_L 胜出")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
