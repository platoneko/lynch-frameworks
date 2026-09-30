#!/usr/bin/env python3
"""600036.SH (China Merchants Bank) valuation eval — recompute anchors from frameworks/600036.SH.md.

frameworks/600036.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: cmb_gordon_pb_roe_v3

Main ruler: Gordon PB-ROE, less the discounted excess retention.
  full_x   = BPS × (ROE_x - g) / (r - g)
  excess_x = (1 - payout_obs - g / ROE_x) × ROE_x × BPS / (r - g)
  anchor_x = min( full_x - k_x × excess_x, BPS × pb_hist_hi )
  * r = basket r (篮 5 大行 / 优质股份行, 11%; gordon.BASKET_R), g = 3% shared
    across tiers (new-regime realized EPS/NI growth)
  * ROE_M = official common-shareholder ROAE (annualized) on the same common BPS;
    ROE_L = ROE_M minus provision-rebuild hit; ROE_H = ROE_M + 0.5pp (NIM flat)
  * Gordon at g = 3% assumes a payout of 1 - g/ROE (~78%); the bank pays ~35%.
    The gap is retained into an ever-growing balance sheet (retention audit
    bucket E) — `excess_x` is that stream capitalized at (r - g), and k_x is the
    haircut for it earning below r (valuation-rules「视同派出现金的打折 k」)
  * Historical own-year PB is a guardrail only — H is clipped to the measured top
    (not binding); the PB=1.0 book floor is disclosed, never max()-ed

The provision identity is recomputed from NPL × Δcoverage so ROE_L cannot
quietly become an unsourced number.

Run:  python3 frameworks/eval/600036.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.gordon import check_g_cap, check_r, justified_pb  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600036.SH.md"
FORMULA_ID = "cmb_gordon_pb_roe_v3"
YI = 1e8
ROE_L_TOL = 5e-4
_ROE_NEAR_R = 0.03

# `g2` / `r_op` (not `g` / `r`) so scripts/calibration.py picks the perpetual g
# and the r tier up in its cross-ticker table (AGENTS.md「永续增长口径」).
REQUIRED = [
    "shares", "bps", "bps_prev", "fx_hkdcny",
    "roe_m", "roe_h", "g2", "r_op", "pb_hist_hi",
    "npl", "cov_now", "cov_l", "tax_rate",
    "payout_obs", "k_l", "k_m", "k_h",
]


def equity_avg(inp: dict[str, float]) -> float:
    return 0.5 * (inp["bps"] + inp["bps_prev"]) * inp["shares"]


def provision_hit_pp(inp: dict[str, float]) -> float:
    delta_ni = inp["npl"] * (inp["cov_l"] - inp["cov_now"]) * (1.0 - inp["tax_rate"])
    return delta_ni / equity_avg(inp)


def roe_l_of(inp: dict[str, float]) -> float:
    return inp["roe_m"] - provision_hit_pp(inp)


def full_value(inp: dict[str, float], roe: float) -> float:
    """Gordon PB-ROE value: the model pays out 1 - g/ROE of earnings."""
    return inp["bps"] * justified_pb(inp["g2"], roe, inp["r_op"])


def excess_retention(inp: dict[str, float], roe: float) -> float:
    """Retained beyond what g needs, which Gordon counts as paid out (bucket E).

    Per share, capitalized at (r - g): (1 - payout_obs - g/ROE) × EPS / (r - g).
    """
    g, r = inp["g2"], inp["r_op"]
    share = 1.0 - inp["payout_obs"] - g / roe
    return share * roe * inp["bps"] / (r - g)


def anchor(inp: dict[str, float], roe: float, k: float, clip: bool) -> float:
    value = full_value(inp, roe) - k * excess_retention(inp, roe)
    if clip:
        value = min(value, inp["bps"] * inp["pb_hist_hi"])
    return value


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
    # Snap to 4dp so the Outputs ROE_L and the provision identity stay in lockstep.
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

    k_l, k_m, k_h = inp["k_l"], inp["k_m"], inp["k_h"]
    # Worse world, worse return on the retained capital: 0 ≤ k_H ≤ k_M ≤ k_L ≤ 1.
    if not (0.0 <= k_h <= k_m <= k_l <= 1.0):
        errors.append(f"k must satisfy 0 <= k_h <= k_m <= k_l <= 1, got {k_l}/{k_m}/{k_h}")
    if not (0.0 < inp["payout_obs"] < 1.0):
        errors.append(f"payout_obs={inp['payout_obs']} must be in (0, 1)")
    for lab, roe in (("L", roe_l), ("M", roe_m), ("H", roe_h)):
        if 1.0 - inp["payout_obs"] - g / roe <= 0:
            errors.append(f"ROE_{lab}: no excess retention — payout_obs already ≥ 1 - g/ROE")

    if errors:
        return report(errors, "FAIL (inputs/guards)")

    full = {lab: full_value(inp, roe) for lab, roe in (("L", roe_l), ("M", roe_m), ("H", roe_h))}
    excess = {lab: excess_retention(inp, roe)
              for lab, roe in (("L", roe_l), ("M", roe_m), ("H", roe_h))}
    L = anchor(inp, roe_l, k_l, clip=False)
    M = anchor(inp, roe_m, k_m, clip=False)
    H_raw = anchor(inp, roe_h, k_h, clip=False)
    H = anchor(inp, roe_h, k_h, clip=True)
    clipped = H_raw > H + 1e-9
    pb_l, pb_m, pb_h = L / inp["bps"], M / inp["bps"], H / inp["bps"]

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # A2e-2c flat-multiple ladder in PE space: every tier on PE_M = PB_M / ROE_M,
    # so the ladder that remains is the ROE (numerator) ladder alone.
    pe_m = pb_m / roe_m
    flat = tuple(roe * inp["bps"] * pe_m for roe in (roe_l, roe_m, roe_h))
    errors += ladder("flat-multiple", *flat)

    # DDM cross at g_d = g (retention audit Step 5): dividends only, i.e. k = 1.
    ddm = {lab: full[lab] - excess[lab] for lab in full}

    near_r = abs(roe_m - inp["r_op"]) <= _ROE_NEAR_R

    # Seller mapping sanity (non-fatal prints)
    seller_mean = inp.get("seller_tp_mean")
    seller_zone = (
        zone_of(seller_mean, L, M, H) if seller_mean is not None else None
    )

    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'ROE':>8}{'k':>6}{'Gordon':>9}{'超额留存':>9}{'k后':>9}{'PB':>8}")
    for lab, roe, k, a, pb in (("L", roe_l, k_l, L, pb_l), ("M", roe_m, k_m, M, pb_m),
                               ("H", roe_h, k_h, H, pb_h)):
        print(f"{lab:<3}{roe:8.2%}{k:6.2f}{full[lab]:9.2f}{excess[lab]:9.2f}{a:9.2f}{pb:8.4f}")
    if clipped:
        print(f"H clipped to pb_hist_hi: {H_raw:.2f} → {H:.2f}")
    print(f"视同派出行 (k前/扣减): L {excess['L']:.2f}/-{k_l * excess['L']:.2f} "
          f"M {excess['M']:.2f}/-{k_m * excess['M']:.2f} H {excess['H']:.2f}/-{k_h * excess['H']:.2f}")
    print(f"DDM 对照 (g_d=g, ≡ k=1): L={ddm['L']:.2f} M={ddm['M']:.2f} H={ddm['H']:.2f}")
    print(f"③ 带内: PB {pb_l:.3f}/{pb_m:.3f}/{pb_h:.3f} vs 顶 {inp['pb_hist_hi']}")
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
    for dg in (-0.01, 0.01):
        alt = dict(inp, g2=g + dg)
        print(f"敏感 g={g + dg:.0%}: " + " / ".join(
            f"{anchor(alt, roe, k, clip=lab == 'H'):.2f}"
            for lab, roe, k in (("L", roe_l, k_l), ("M", roe_m, k_m), ("H", roe_h, k_h))))
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
