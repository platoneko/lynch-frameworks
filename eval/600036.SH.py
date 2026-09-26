#!/usr/bin/env python3
"""600036.SH (China Merchants Bank) valuation eval — recompute anchors from frameworks/600036.SH.md.

frameworks/600036.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: cmb_gordon_pb_roe_v2

Main ruler: Gordon PB-ROE.
  anchor_x = BPS × min( (ROE_x - g) / (r - g), pb_hist_hi )
  * r = basket r (篮 5 大行 / 优质股份行, 11%; gordon.BASKET_R), g = 3% shared
    across tiers (new-regime realized EPS/NI growth)
  * ROE_M = reported TTM weighted ROE; ROE_L = ROE_M minus provision-rebuild hit;
    ROE_H = ROE_M + 0.5pp (NIM flat)
  * Historical own-year PB is a guardrail only — H is clipped to the measured top
    (not binding at the basket r); the PB=1.0 book floor is disclosed, never max()-ed

The provision identity is recomputed from NPL × Δcoverage so ROE_L cannot
quietly become an unsourced number.

Run:  python3 frameworks/eval/600036.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.gordon import check_g_cap, check_r, g_cap, justified_pb  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600036.SH.md"
FORMULA_ID = "cmb_gordon_pb_roe_v2"
YI = 1e8
ROE_L_TOL = 5e-4
_ROE_NEAR_R = 0.03

# `g2` / `r_op` (not `g` / `r`) so scripts/calibration.py picks the perpetual g
# and the r tier up in its cross-ticker table (AGENTS.md「永续增长口径」).
REQUIRED = [
    "shares", "bps", "bps_prev", "fx_hkdcny",
    "roe_m", "roe_h", "g2", "r_op", "pb_hist_hi",
    "npl", "cov_now", "cov_l", "tax_rate",
]


def equity_avg(inp: dict[str, float]) -> float:
    return 0.5 * (inp["bps"] + inp["bps_prev"]) * inp["shares"]


def provision_hit_pp(inp: dict[str, float]) -> float:
    delta_ni = inp["npl"] * (inp["cov_l"] - inp["cov_now"]) * (1.0 - inp["tax_rate"])
    return delta_ni / equity_avg(inp)


def roe_l_of(inp: dict[str, float]) -> float:
    return inp["roe_m"] - provision_hit_pp(inp)


def fair_pb(inp: dict[str, float], roe: float, clip: bool) -> float:
    pb = justified_pb(inp["g2"], roe, inp["r_op"])
    if clip:
        pb = min(pb, inp["pb_hist_hi"])
    return pb


def anchor(inp: dict[str, float], roe: float, clip: bool) -> float:
    return inp["bps"] * fair_pb(inp, roe, clip)


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports the H-share companion band.

    The southbound axis only supplies the AH-premium context here (A9); what it
    still locks is the reporting contract its own §4 direction check depends on.
    The live H/A is a function of today's two prices and no longer lives in the
    doc; the axis's cross-ticker direction check reads its own dated series.
    """
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "600036.SH" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append("600036.SH is not declared on _AXIS.southbound-repricing.md — "
                      "a mount has to exist on both sides")
    if "H 股对照带" not in md:
        errors.append("framework lacks the H-share companion band (axis §3 rule 3)")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # The r leg must name its basket and carry that basket's value (A5 / A13).
    baskets = parse_baskets(md)
    if "r_op" not in baskets:
        errors.append("r_op: no 篮 N in Inputs source cell")
    errors += check_r(inp["r_op"], "r_op", baskets.get("r_op"))
    errors += check_g_cap(inp["g2"], inp["r_op"], "g2")  # cap = min(6%, r - 4%)
    errors += check_southbound_mount(md)

    hit = provision_hit_pp(inp)
    roe_l_raw = roe_l_of(inp)
    # Snap to 4dp so Outputs "ROE 10.00%" and the provision identity stay in lockstep.
    roe_l = round(roe_l_raw, 4)
    if abs(roe_l_raw - roe_l) > ROE_L_TOL:
        errors.append(
            f"roe_l raw {roe_l_raw:.6f} rounds to {roe_l} beyond tol {ROE_L_TOL}"
        )
    roe_m = inp["roe_m"]
    roe_h = inp["roe_h"]
    g = inp["g2"]

    errors += ladder("roe", roe_l, roe_m, roe_h)
    if inp["cov_l"] <= inp["cov_now"]:
        errors.append("cov_l must exceed cov_now — L is a provision *rebuild*")
    if g >= inp["r_op"]:
        errors.append(f"g2={g} must be < r={inp['r_op']}")
    for lab, roe in (("L", roe_l), ("M", roe_m), ("H", roe_h)):
        if roe <= g:
            errors.append(f"ROE_{lab}={roe} must exceed g={g}")

    if errors:
        return report(errors, "FAIL (inputs/guards)")

    pb_l = fair_pb(inp, roe_l, clip=False)
    pb_m = fair_pb(inp, roe_m, clip=False)
    pb_h_raw = fair_pb(inp, roe_h, clip=False)
    pb_h = fair_pb(inp, roe_h, clip=True)
    clipped = pb_h_raw > inp["pb_hist_hi"] + 1e-12

    L = anchor(inp, roe_l, clip=False)
    M = anchor(inp, roe_m, clip=False)
    H = anchor(inp, roe_h, clip=True)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None)

    # A2e-2c flat-multiple ladder in PE space: every tier on PE_M = PB_M / ROE_M,
    # so the ladder that remains is the ROE (numerator) ladder alone.
    pe_m = pb_m / roe_m
    flat = tuple(roe * inp["bps"] * pe_m for roe in (roe_l, roe_m, roe_h))
    errors += ladder("flat-multiple", *flat)

    near_r = abs(roe_m - inp["r_op"]) <= _ROE_NEAR_R

    # Seller mapping sanity (non-fatal prints)
    seller_mean = inp.get("seller_tp_mean")
    seller_zone = (
        zone_of(seller_mean, L, M, H) if seller_mean is not None else None
    )

    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'ROE':>8}{'g':>6}{'PB_raw':>9}{'PB':>9}{'锚点':>9}")
    print(f"{'L':<3}{roe_l:8.2%}{g:6.0%}{pb_l:9.4f}{pb_l:9.4f}{L:9.2f}")
    print(f"{'M':<3}{roe_m:8.2%}{g:6.0%}{pb_m:9.4f}{pb_m:9.4f}{M:9.2f}")
    print(f"{'H':<3}{roe_h:8.2%}{g:6.0%}{pb_h_raw:9.4f}{pb_h:9.4f}{H:9.2f}"
          + ("  (clipped to pb_hist_hi)" if clipped else ""))
    if clipped:
        # valuation-rules 裁决顺序 ③: the clip is the same number as solving
        # (ROE_H - g)/(r - g) = pb_hist_hi for g — report that band-edge g (A6).
        g_h_edge = (roe_h - inp["pb_hist_hi"] * inp["r_op"]) / (1.0 - inp["pb_hist_hi"])
        cap = g_cap(inp["r_op"])
        print(f"H 带边反解 g_H={g_h_edge:.2%} (≡ clip; ≤ cap {cap:.1%}: {g_h_edge <= cap})")
    # Book floor (PB = 1.0): disclosure only, never max()-ed into L — at the basket r
    # ROE_L < r, so L is a discount to book by construction.
    print(f"地板 PB=1.0 → {inp['bps']:.2f} (disclosure only, not max()-ed; L={L:.2f})")
    print(
        f"拨备冲击: NPL {inp['npl'] / YI:.1f}亿 × Δcov "
        f"→ 税后 {inp['npl'] * (inp['cov_l'] - inp['cov_now']) * (1 - inp['tax_rate']) / YI:.1f}亿 "
        f"/ 平均权益 {equity_avg(inp) / YI:.0f}亿 = {hit:.2%} → ROE_L {roe_l:.2%} ✓"
    )
    print(
        f"ROE情景比 (ROE-g): L/M={(roe_l - g) / (roe_m - g):.3f} "
        f"H/M={(roe_h - g) / (roe_m - g):.3f}"
    )
    print(f"flat-multiple @PE_M={pe_m:.2f}x (PB_M/ROE_M): "
          f"L={flat[0]:.2f} M={flat[1]:.2f} H={flat[2]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(
        f"A11 |ROE_M-r|={abs(roe_m - inp['r_op']):.2%} "
        f"well_conditioned_for_implied_g={not near_r}"
    )
    if seller_mean is not None:
        print(
            f"卖方TP均值 {seller_mean:.2f} → zone={seller_zone} "
            f"(映射校验；不进公式)"
        )
    fx = inp["fx_hkdcny"]
    print(
        f"H股对照(HKD): L={L / fx:.2f} M={M / fx:.2f} H={H / fx:.2f}"
    )

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
