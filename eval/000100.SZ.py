#!/usr/bin/env python3
"""000100.SZ (TCL科技) valuation eval — recompute anchors from frameworks/000100.SZ.md.

formula_id: tcl_sotp_display_pv_flat_pe_v1

Asymmetric SOTP on flat multiples: display attributable-NI ladder x flat PE,
PV leg at a low multiple (0 in L/M), distribution at a thin multiple.  V_opt
(glass substrate / InP) is an explicit 拍值, never in the base.

Discount rate: no leg is Gordon-generated, so no basket r enters the formula.
The Inputs table still names each leg's basket (显示 / 光伏 篮 6, 分销 篮 4, A8)
as disclosure rows; `check_r` holds every r row to its basket's value and the
③ 出带 reference band (display leg at 1/r of 篮 6) is printed, not asserted.
There is no g2 row (flat multiples), so `check_g_cap` has nothing to check.

Run after every edit of frameworks/000100.SZ.md:   python3 eval/000100.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import check_r, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "000100.SZ.md"
FORMULA_ID = "tcl_sotp_display_pv_flat_pe_v1"
TICKER = "000100.SZ"

TIERS = ("l", "m", "h")
R_LEGS = ("r_display", "r_pv", "r_dist")
REQUIRED = (
    "price", "shares",
    "ni_display_l", "ni_display_m", "ni_display_h", "pe_display",
    "ni_pv_l", "ni_pv_m", "ni_pv_h", "pe_pv",
    "ni_dist", "pe_dist",
    *R_LEGS,
    "v_opt", "p_l", "p_m", "p_h",
)

# Disclosure coordinates from §0 / A8 (not Inputs: they drive no anchor).
ROE_GROUP = 0.11        # 2026H1 consolidated ROE; display-leg own ROE 待补
G_CAP_MACRO = 0.06
PB_FLOOR_MEDIAN = 0.84  # historical PB median
PB_NOW = 1.51           # current PB at `price`


def leg_ps(ni: float, pe: float, shares: float) -> float:
    return (ni / shares) * pe


def anchor(inp: dict[str, float], tier: str, pe_display: float) -> float:
    return (
        leg_ps(inp[f"ni_display_{tier}"], pe_display, inp["shares"])
        + leg_ps(inp[f"ni_pv_{tier}"], inp["pe_pv"], inp["shares"])
        + leg_ps(inp["ni_dist"], inp["pe_dist"], inp["shares"])
    )


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # Step 1: base deck on the flat display multiple.
    L, M, H = (anchor(inp, t, inp["pe_display"]) for t in TIERS)
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    print(f"{TICKER} {FORMULA_ID}")
    print(f"L/M/H = {L:.2f} / {M:.2f} / {H:.2f}   A/B = {A:.2f} / {B:.2f}")
    # A2e-2c / A2e-5: display is flat 14x on every tier, so the flat-multiple
    # ladder is the display leg itself; the tier spread is all numerator.
    flat = [leg_ps(inp[f"ni_display_{t}"], inp["pe_display"], inp["shares"]) for t in TIERS]
    print(f"flat-multiple ladder (display leg @ {inp['pe_display']:g}x): "
          f"{flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M={L/M:.2f} = num {inp['ni_display_l']/inp['ni_display_m']:.2f} x pe 1.00 | "
          f"H/M={H/M:.2f} = num {inp['ni_display_h']/inp['ni_display_m']:.2f} x pe 1.00 (+PV leg at H) | "
          f"width={(H-L)/(2*M):.2f} V_opt/M={inp['v_opt']/M:.2f}")
    print(f"price {inp['price']} → zone {zone}")
    p_k = {"l": inp["p_l"], "m": inp["p_m"], "h": inp["p_h"]}
    for t, a in zip(TIERS, (L, M, H)):
        print(f"  zone+V {t.upper()}: {a:.2f} + {p_k[t]}*{inp['v_opt']} = {a + p_k[t] * inp['v_opt']:.2f}")

    # Step 2: disclosure only (A8) — basket r never reaches the base.
    r_disp = inp["r_display"]
    pe_cap = 1.0 / r_disp                                   # Gordon reach at g = 0
    pe_retain = perpetual_pe(G_CAP_MACRO, ROE_GROUP, r_disp)  # retention branch at g cap
    ref = [anchor(inp, t, pe_cap) for t in TIERS]
    ref_zone = zone_of(inp["price"], *ref)
    print(f"③ 出带 (disclosure): display flat {inp['pe_display']:g}x vs 篮 {baskets.get('r_display')} "
          f"r={r_disp:.0%} reach 1/r={pe_cap:.2f}x (g=6% retain {pe_retain:.2f}x) → "
          f"reference band {ref[0]:.2f} / {ref[1]:.2f} / {ref[2]:.2f}, price → {ref_zone}")
    eps_disp_m = inp["ni_display_m"] / inp["shares"]
    pe_mkt = inp["price"] / eps_disp_m
    r_g0 = 1.0 / pe_mkt
    r_g6 = G_CAP_MACRO + (1.0 - G_CAP_MACRO / ROE_GROUP) / pe_mkt
    print(f"implied r(P) (disclosure): price = {pe_mkt:.1f}x M-tier display EPS {eps_disp_m:.3f} → "
          f"g=0 {r_g0:.1%} / g=6% {r_g6:.1%} (baskets 4 {inp['r_dist']:.0%} / 6 {r_disp:.0%})")
    floor = PB_FLOOR_MEDIAN * inp["price"] / PB_NOW
    print(f"floor (disclosure only, not max()): PB {PB_FLOOR_MEDIAN}x × BPS {inp['price']/PB_NOW:.2f} = "
          f"{floor:.2f} vs L {L:.2f} → {zone_of(floor, L, M, H)}")

    # Step 3: guards.
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.05)
    errors += ladder("base", L, M, H)
    errors += ladder("ni_display", inp["ni_display_l"], inp["ni_display_m"], inp["ni_display_h"])
    if not (inp["ni_pv_l"] <= inp["ni_pv_m"] <= inp["ni_pv_h"]):
        errors += ["ni_pv must be non-decreasing across tiers (A3)"]
    if not (inp["p_l"] <= inp["p_m"] <= inp["p_h"]):
        errors += ["p_k must be non-decreasing"]
    # valuation-rules「§r 篮子」: every r row must name a basket and equal that basket's r.
    for leg in R_LEGS:
        if leg not in baskets:
            errors += [f"{leg}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)"]
        errors += check_r(inp[leg], leg, baskets.get(leg))
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
