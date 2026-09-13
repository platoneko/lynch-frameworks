#!/usr/bin/env python3
"""1898.HK (China Coal Energy) valuation eval.

frameworks/1898.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: chinacoal_selfmined_asp_ladder_flat_pe_hkd_v1

Main ruler: the company's own self-mined thermal coal ASP, not the port price.

    L = 436 元/吨  — 2025H1, reconstructed from the filed +13.3% YoY
    M = 494 元/吨  — 2026H1 filed
    H = 558 元/吨  — QHD 5,500 rising from 755 to Goldman's 2026H2 950,
                      passed through at 0.5 because ~70% of volume is contract

The gap between the two price series is the whole point: the port price was
941 元/吨 on 2026-09-04 while the company sold at 494.  A model that multiplies
the port move straight onto this company's earnings overstates its beta by
about 2x, which is why the pass-through is an explicit input and why guard 3
welds px_h to (qhd_h, qhd_m, pass_through) — so nobody can nudge px_h alone.

Numerator is computed in CNY and converted to HKD at the end; the anchors and
BPS are HKD because that is the listing.

The asset floor is deliberately NOT used to backstop L.  PB = 1.0 is 14.4661
HKD, which sits *above* M (12.48) — backstopping there would produce L > M and
destroy the ladder.  Guard 5 asserts the relationship the framework claims
(A10): the floor lands at the start of the optimistic band, so "earnings
recover" and "book value gets paid for" are the same event on this ticker.

Run:  python3 eval/1898.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1898.HK.md"
FORMULA_ID = "chinacoal_selfmined_asp_ladder_flat_pe_hkd_v1"
YI = 1e8

BASE_NP_PARENT_YI = 163.84  # 2026H1 归母 81.92亿 CNY x 2
BASE_NP_TOL_YI = 0.5
PX_H_TOL = 1.0  # 元/吨

REQUIRED = [
    "price", "shares", "fx_cny_hkd", "np_h1", "op_h1", "vol_yr",
    "px_l", "px_m", "px_h", "conv", "pe_l", "pe_m", "pe_h",
    "pass_through", "qhd_m", "qhd_h", "bps",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    errors += ladder("self-mined ASP", inp["px_l"], inp["px_m"], inp["px_h"])
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if not (1.05 < inp["fx_cny_hkd"] < 1.25):
        errors.append(f"fx_cny_hkd={inp['fx_cny_hkd']} outside plausible band")
    if not (inp["pe_l"] == inp["pe_m"] == inp["pe_h"]):
        errors.append(
            f"PE band must be flat (A9): {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}"
        )
    # H is derived, not chosen: weld it to the port ladder and the pass-through.
    px_h_expected = inp["px_m"] * (
        1.0 + (inp["qhd_h"] - inp["qhd_m"]) / inp["qhd_m"] * inp["pass_through"]
    )
    if abs(inp["px_h"] - px_h_expected) > PX_H_TOL:
        errors.append(
            f"px_h={inp['px_h']:g} vs derived {px_h_expected:.1f} "
            f"(= {inp['px_m']:g} x (1 + {(inp['qhd_h'] - inp['qhd_m']) / inp['qhd_m']:.4f} "
            f"x {inp['pass_through']:g})) — H must follow the port ladder, not be set alone"
        )
    if errors:
        return report(errors)

    # --- the ruler (numerator in CNY, anchors in HKD) ---------------------------
    def scenario(px: float, pe: float):
        dgp = (px - inp["px_m"]) * inp["vol_yr"]  # 元/吨 x 亿吨 = 亿 CNY
        npp = 2.0 * inp["np_h1"] + dgp * inp["conv"]
        eps_cny = npp * YI / inp["shares"]
        eps_hkd = eps_cny * inp["fx_cny_hkd"]
        return dgp, npp, eps_cny, eps_hkd, eps_hkd * pe

    sc_l = scenario(inp["px_l"], inp["pe_l"])
    sc_m = scenario(inp["px_m"], inp["pe_m"])
    sc_h = scenario(inp["px_h"], inp["pe_h"])

    if abs(sc_m[1] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {sc_m[1]:.4f}亿CNY vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    L, M, H = sc_l[4], sc_m[4], sc_h[4]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])

    A, B = cut_points(L, M, H)
    # A10: the asset floor does not backstop L on this ticker.  Assert the shape
    # the framework claims — floor above M, landing in the optimistic band — so a
    # future revision that drops BPS below scenario_L has to go back to the
    # conversation about which ruler is primary.
    if not (inp["bps"] > M):
        errors.append(
            f"asset floor PB=1.0 ({inp['bps']:g} HKD) no longer sits above M ({M:.2f}) — "
            "A10's 'floor does not backstop L' premise needs re-deciding"
        )
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        f"port ladder QHD5500 {inp['qhd_m']:g} -> {inp['qhd_h']:g} 元/吨 "
        f"x pass_through {inp['pass_through']:g} => px_h {inp['px_h']:g} 元/吨 "
        f"(derived {px_h_expected:.1f})"
    )
    for tag, sc, px in (("L", sc_l, inp["px_l"]), ("M", sc_m, inp["px_m"]), ("H", sc_h, inp["px_h"])):
        print(
            f"{tag}: asp={px:>6.1f}元/吨  Δgp={sc[0]:+7.2f}亿CNY  np={sc[1]:7.2f}亿CNY  "
            f"eps={sc[2]:.4f}CNY={sc[3]:.4f}HKD  anchor={sc[4]:.4f}HKD  "
            f"PB={sc[4] / inp['bps']:.3f}"
        )
    per_10 = 10.0 * inp["vol_yr"] * inp["conv"] * YI / inp["shares"] * inp["fx_cny_hkd"] * inp["pe_m"]
    print(
        f"sensitivity: +10元/吨 ASP -> anchor {per_10:+.2f} HKD; "
        f"floor PB=1.0 = {inp['bps']:g} HKD (in [{B:.2f}, {H:.2f}] = optimistic)"
    )
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} (flat)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={sc_l[3] / sc_m[3]:.4f} H={sc_h[3] / sc_m[3]:.4f}"
    )
    print(f"price={inp['price']} zone={zone}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
