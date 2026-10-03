#!/usr/bin/env python3
"""600036.SH (China Merchants Bank) valuation eval — recompute anchors from frameworks/600036.SH.md.

frameworks/600036.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: cmb_gordon_pb_roe_v4

Main ruler: Gordon PB-ROE, less the discounted excess retention.
  full_x   = BPS_x × (ROE_x - g) / (r - g)
  excess_x = (1 - payout_obs - g / ROE_x) × ROE_x × BPS_x / (r - g)
  anchor_x = min( full_x - k_x × excess_x, BPS_x × pb_hist_hi )
  * r = basket r (篮 5 大行 / 优质股份行, 11%; gordon.BASKET_R), g = 3% shared
    across tiers (new-regime realized EPS/NI growth)
  * ROE_x = FY2027E consensus EPS (yfinance 20 analysts low / mean / high) over
    the common BPS at the start of 2027 (E_{n+1}/B_n).  That BPS rolls the 2Q26
    common BPS, less the 2025 final dividend paid 2026-07-10, through the 2H26
    consensus profit not yet booked, retained at b1 = g/ROE (closed form
    BPS = start / (1 - g N / eps_x); valuation-rules 裁决表 ② / 两段式过渡,
    2026-09-21).  The 2026H1 official ROAE is a snapshot only (data priority,
    2026-10-03); the provision-rebuild hit is kept as an L-side stress coordinate
  * Gordon at g = 3% assumes a payout of 1 - g/ROE (~78%); the bank pays ~35%.
    The gap is retained into an ever-growing balance sheet (retention audit
    bucket E) — `excess_x` is that stream capitalized at (r - g), and k_x is the
    haircut for it earning below r (valuation-rules「视同派出现金的打折 k」)
  * Historical own-year PB is a guardrail — H is clipped to the measured top;
    the PB=1.0 book floor is disclosed, never max()-ed

The provision identity is still recomputed from NPL × Δcoverage so the stress
coordinate cannot quietly become an unsourced number.

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
FORMULA_ID = "cmb_gordon_pb_roe_v4"
YI = 1e8
ROE_L_TOL = 5e-4
_ROE_NEAR_R = 0.03

# `g2` / `r_op` (not `g` / `r`) so scripts/calibration.py picks the perpetual g
# and the r tier up in its cross-ticker table (AGENTS.md「永续增长口径」).
REQUIRED = [
    "shares", "bps", "bps_prev", "fx_hkdcny",
    "eps_2027_l", "eps_2027_m", "eps_2027_h", "eps_2026_m", "eps_1h26_a", "div_2h26",
    "roe_snap", "g2", "r_op", "pb_hist_hi",
    "npl", "cov_now", "cov_l", "tax_rate",
    "payout_obs", "k_l", "k_m", "k_h",
]
TIERS = ("L", "M", "H")


def equity_avg(inp: dict[str, float]) -> float:
    return 0.5 * (inp["bps"] + inp["bps_prev"]) * inp["shares"]


def provision_hit_pp(inp: dict[str, float]) -> float:
    delta_ni = inp["npl"] * (inp["cov_l"] - inp["cov_now"]) * (1.0 - inp["tax_rate"])
    return delta_ni / equity_avg(inp)


def unbooked_2h26(inp: dict[str, float]) -> float:
    """2H26 consensus EPS not yet in the 2Q26 book (FY26E mean less 1H26 actual)."""
    return inp["eps_2026_m"] - inp["eps_1h26_a"]


def bps_2027(inp: dict[str, float], eps: float) -> float:
    """Common BPS at the start of 2027, retaining b1 = g/ROE of the 2H26 profit.

    start = 2Q26 BPS less the 2025 final dividend paid after the balance-sheet
    date; BPS = start + (g / ROE) N with ROE = eps / BPS → closed form.
    """
    start = inp["bps"] - inp["div_2h26"]
    gn = inp["g2"] * unbooked_2h26(inp) / eps
    if gn >= 1.0:
        raise ValueError(f"BPS roll diverges: g N / eps = {gn:.3f}")
    return start / (1.0 - gn)


def full_value(inp: dict[str, float], bps: float, roe: float) -> float:
    """Gordon PB-ROE value: the model pays out 1 - g/ROE of earnings."""
    return bps * justified_pb(inp["g2"], roe, inp["r_op"])


def excess_retention(inp: dict[str, float], bps: float, roe: float) -> float:
    """Retained beyond what g needs, which Gordon counts as paid out (bucket E).

    Per share, capitalized at (r - g): (1 - payout_obs - g/ROE) × EPS / (r - g).
    """
    g, r = inp["g2"], inp["r_op"]
    share = 1.0 - inp["payout_obs"] - g / roe
    return share * roe * bps / (r - g)


def anchor(inp: dict[str, float], bps: float, roe: float, k: float, clip: bool) -> float:
    value = full_value(inp, bps, roe) - k * excess_retention(inp, bps, roe)
    if clip:
        value = min(value, bps * inp["pb_hist_hi"])
    return value


def tiers(inp: dict[str, float]) -> dict[str, tuple[float, float]]:
    """{tier: (BPS at start of 2027, ROE_x = FY27E eps_x / that BPS)}."""
    out = {}
    for lab in TIERS:
        eps = inp[f"eps_2027_{lab.lower()}"]
        b = bps_2027(inp, eps)
        out[lab] = (b, eps / b)
    return out


def anchors(inp: dict[str, float]) -> tuple[float, float, float]:
    t = tiers(inp)
    return tuple(anchor(inp, *t[lab], inp[f"k_{lab.lower()}"], clip=lab == "H")
                 for lab in TIERS)


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

    g = inp["g2"]
    errors += ladder("eps_2027", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    if inp["cov_l"] <= inp["cov_now"]:
        errors.append("cov_l must exceed cov_now — the stress is a provision *rebuild*")
    if g >= inp["r_op"]:
        errors.append(f"g2={g} must be < r={inp['r_op']}")
    # Same-world gate: FY26E → FY27E consensus rises, so g > 0 is admissible.
    if inp["eps_2027_m"] <= inp["eps_2026_m"] and g > 0:
        errors.append("same-world gate: FY27E ≤ FY26E consensus but g > 0")
    try:
        t = tiers(inp)
    except ValueError as e:
        return report([str(e)], "FAIL (inputs/guards)")
    roe = {lab: t[lab][1] for lab in TIERS}
    bps = {lab: t[lab][0] for lab in TIERS}
    errors += ladder("roe", roe["L"], roe["M"], roe["H"])
    for lab in TIERS:
        if roe[lab] <= g:
            errors.append(f"ROE_{lab}={roe[lab]} must exceed g={g}")

    k = {lab: inp[f"k_{lab.lower()}"] for lab in TIERS}
    # Worse world, worse return on the retained capital: 0 ≤ k_H ≤ k_M ≤ k_L ≤ 1.
    if not (0.0 <= k["H"] <= k["M"] <= k["L"] <= 1.0):
        errors.append(f"k must satisfy 0 <= k_h <= k_m <= k_l <= 1, got {k}")
    if not (0.0 < inp["payout_obs"] < 1.0):
        errors.append(f"payout_obs={inp['payout_obs']} must be in (0, 1)")
    for lab in TIERS:
        if 1.0 - inp["payout_obs"] - g / roe[lab] <= 0:
            errors.append(f"ROE_{lab}: no excess retention — payout_obs already ≥ 1 - g/ROE")

    if errors:
        return report(errors, "FAIL (inputs/guards)")

    full = {lab: full_value(inp, bps[lab], roe[lab]) for lab in TIERS}
    excess = {lab: excess_retention(inp, bps[lab], roe[lab]) for lab in TIERS}
    L, M, H = anchors(inp)
    H_raw = anchor(inp, bps["H"], roe["H"], k["H"], clip=False)
    clipped = H_raw > H + 1e-9
    pb = {"L": L / bps["L"], "M": M / bps["M"], "H": H / bps["H"]}

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # A2e-2c flat-multiple ladder in PE space: every tier on PE_M = PB_M / ROE_M,
    # so the ladder that remains is the EPS (numerator) ladder alone.
    pe_m = pb["M"] / roe["M"]
    flat = tuple(inp[f"eps_2027_{lab.lower()}"] * pe_m for lab in TIERS)
    errors += ladder("flat-multiple", *flat)

    # DDM cross at g_d = g (retention audit Step 5): dividends only, i.e. k = 1.
    ddm = {lab: full[lab] - excess[lab] for lab in TIERS}

    near_r = abs(roe["M"] - inp["r_op"]) <= _ROE_NEAR_R

    # Provision-rebuild stress coordinate (the v3 L): ROE_M less the hit, at k_L.
    hit = provision_hit_pp(inp)
    stress = anchor(inp, bps["M"], roe["M"] - hit, k["L"], clip=False)
    # v3 construction (2026H1 official ROAE snapshot on the 2Q26 BPS) for the record.
    snap = anchor(inp, inp["bps"], inp["roe_snap"], k["M"], clip=False)

    seller_mean = inp.get("seller_tp_mean")
    seller_zone = (
        zone_of(seller_mean, L, M, H) if seller_mean is not None else None
    )

    print(f"formula_id={FORMULA_ID}")
    print(f"2H26 未入账 EPS N = {unbooked_2h26(inp):.4f}; 起点 BPS = "
          f"{inp['bps']:.4f} − {inp['div_2h26']:.3f} = {inp['bps'] - inp['div_2h26']:.4f}")
    print(f"{'档':<3}{'BPS27':>9}{'ROE':>8}{'b1':>7}{'k':>6}{'Gordon':>9}{'超额留存':>9}{'k后':>9}{'PB':>8}")
    for lab, a in (("L", L), ("M", M), ("H", H)):
        print(f"{lab:<3}{bps[lab]:9.4f}{roe[lab]:8.2%}{g / roe[lab]:7.3f}{k[lab]:6.2f}"
              f"{full[lab]:9.2f}{excess[lab]:9.2f}{a:9.2f}{pb[lab]:8.4f}")
    if clipped:
        print(f"H clipped to pb_hist_hi: {H_raw:.2f} → {H:.2f}")
    print(f"视同派出行 (k前/扣减): L {excess['L']:.2f}/-{k['L'] * excess['L']:.2f} "
          f"M {excess['M']:.2f}/-{k['M'] * excess['M']:.2f} H {excess['H']:.2f}/-{k['H'] * excess['H']:.2f}")
    print(f"DDM 对照 (g_d=g, ≡ k=1): L={ddm['L']:.2f} M={ddm['M']:.2f} H={ddm['H']:.2f}")
    print(f"③ 带内: PB {pb['L']:.3f}/{pb['M']:.3f}/{pb['H']:.3f} vs 顶 {inp['pb_hist_hi']}"
          f"（H 截前 {H_raw / bps['H']:.4f}）")
    print(f"地板 PB=1.0 → {bps['M']:.2f} (disclosure only, not max()-ed; L={L:.2f})")
    print(
        f"拨备回补压力坐标: NPL {inp['npl'] / YI:.1f}亿 × Δcov "
        f"→ 税后 {inp['npl'] * (inp['cov_l'] - inp['cov_now']) * (1 - inp['tax_rate']) / YI:.1f}亿 "
        f"/ 平均权益 {equity_avg(inp) / YI:.0f}亿 = {hit:.2%} → ROE {roe['M'] - hit:.2%} @k_L "
        f"= {stress:.2f}"
    )
    print(f"v3 口径（2026H1 官方 ROAE {inp['roe_snap']:.2%} × 2Q26 BPS，k_M）M = {snap:.2f}（只作对照）")
    print(
        f"ROE情景比 (ROE-g): L/M={(roe['L'] - g) / (roe['M'] - g):.3f} "
        f"H/M={(roe['H'] - g) / (roe['M'] - g):.3f}"
    )
    for dg in (-0.01, 0.01):
        alt = dict(inp, g2=g + dg)
        print(f"敏感 g={g + dg:.0%}: " + " / ".join(f"{v:.2f}" for v in anchors(alt)))
    for lab, kv in (("m", 0.63), ("m", 0.47), ("l", 0.91), ("h", 0.50)):
        alt = dict(inp, **{f"k_{lab}": kv})
        print(f"敏感 k_{lab}={kv}: " + " / ".join(f"{v:.2f}" for v in anchors(alt)))
    alt = dict(inp, payout_obs=0.50)
    print("敏感 payout 50%: " + " / ".join(f"{v:.2f}" for v in anchors(alt)))
    print(f"flat-multiple @PE_M={pe_m:.2f}x (PB_M/ROE_M): "
          f"L={flat[0]:.2f} M={flat[1]:.2f} H={flat[2]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(
        f"A11 |ROE_M-r|={abs(roe['M'] - inp['r_op']):.2%} "
        f"well_conditioned_for_implied_g={not near_r}"
    )
    if seller_mean is not None:
        print(
            f"卖方TP均值 {seller_mean:.2f} → zone={seller_zone} "
            f"(映射校验；不进公式)"
        )
    fx = inp["fx_hkdcny"]
    print(
        f"H股对照(HKD): L={L / fx:.2f} M={M / fx:.2f} H={H / fx:.2f} "
        f"A={A / fx:.2f} B={B / fx:.2f}"
    )

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
