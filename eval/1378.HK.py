#!/usr/bin/env python3
"""1378.HK (China Hongqiao) valuation eval.

frameworks/1378.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: hongqiao_al_spread_gm_bridge_flat_pe_v2

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 562.2万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate.

What is specific to this ticker is the shape of its integration.  Hongqiao's
alumina is *sold outward*, so a high-alumina year pays the upstream leg while
it squeezes the smelter — 2026H1 ran +88亿 on aluminium against **-49亿** on
alumina.  But the axis's L world is the supply-glut one, with alumina frozen
low: there is nothing for the upstream leg to catch, and Hongqiao's k (0.72)
is the highest of the four mounts, so its L/M is the *deepest*, not the
shallowest.  The guard below asserts that ordering against Tianshan, whose
alumina is captive: if the two ever invert, one framework has treated the
L world's alumina differently from the axis.

Run:  python3 eval/1378.HK.py
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

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1378.HK.md"
PEER_CAPTIVE = Path(__file__).resolve().parent.parent / "frameworks" / "002532.SZ.md"
FORMULA_ID = "hongqiao_al_spread_gm_bridge_flat_pe_v2"

GP_M_FILING = 551.3  # 亿 CNY, 2026H1 x2 at the stated 31.5% margin
NP_M_FILING = 344.2  # 亿 CNY, 2026H1 归母 172.1 x2
PE_MEASURED_TOP = 9.79  # own 5-year PE high — H must not price above it


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED + ["fx_hkd_cny"])
    if errors:
        return report(errors)

    errors += ladder("smelting spread", inp["spread_l"], inp["spread_m"], inp["spread_h"])
    errors += check_al_mount((inp["spread_l"], inp["spread_m"], inp["spread_h"]))
    errors += check_regression(inp, GP_M_FILING, NP_M_FILING)

    (L, M, H), eps = anchors(inp, fx=inp["fx_hkd_cny"])
    errors += flat_ladder(eps)

    # Same L world for both mounts (alumina frozen), so the ordering is set by
    # k and by tonnes per yuan of profit — both higher here.  Tianshan's ratio
    # is recomputed from its own Inputs table so the two cannot drift apart.
    peer = parse_inputs(PEER_CAPTIVE.read_text(encoding="utf-8"))
    if REQUIRED_PEER <= peer.keys():
        peer_eps = anchors(peer)[1]
        mine, theirs = eps[0] / eps[1], peer_eps[0] / peer_eps[1]
        if mine >= theirs:
            errors.append(
                f"numerator ratio L {mine:.3f} >= 002532.SZ's {theirs:.3f} — "
                "in the frozen-alumina L world the outward alumina leg has no "
                "cushion and Hongqiao's higher k makes its downside the deeper "
                "one (§1 属性 A)"
            )

    # H is a price scenario, not a re-rating: the multiple it implies must stay
    # inside the multiple this stock has actually printed.
    pe_at_h = H / (eps[1] / inp["fx_hkd_cny"])
    if pe_at_h > PE_MEASURED_TOP:
        errors.append(f"H implies {pe_at_h:.2f}x on M EPS, above own 5y high {PE_MEASURED_TOP}")

    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone
    )

    br = bridge(inp)
    print(f"1378.HK  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}  "
          f"price={inp['price']:.2f} -> {zone}")
    print(f"  EPS(CNY) {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"L/M={L/M:.2f} H/M={H/M:.2f}  分子比L={eps[0]/eps[1]:.2f}")
    print(f"  L 对应 PB {L/inp['bps']:.2f} (floor {floor:.2f} = 5y low PB x bps) "
          f"→ scenario_L 胜出")
    return report(errors)


REQUIRED_PEER = frozenset(REQUIRED)

if __name__ == "__main__":
    raise SystemExit(main())
