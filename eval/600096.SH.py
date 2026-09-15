#!/usr/bin/env python3
"""600096.SH (Yuntianhua) valuation eval.

frameworks/600096.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: ytn_realized_earnings_regime_gordon_v4

Main ruler: three *already-printed or already-consensus* annual net profits,
each with a Gordon multiple generated from a named growth state and the tier's
own forward ROE (NP_x / 中报归母权益):

    L = FY2023 actual 45.22亿  (pricing management tightened, exports shrank)
        -> that regime persisting: perpetual g2 = axis row, at ROE_L.  FY2023
           is this company's own trough year, so the 谷底档 recovery form
           would apply — but the filings show the recovery took ONE year
           (FY2024 53.37 already above M), and recovery_two_stage_pe with
           n=1 degenerates to L >= M; a v3 that used n=3 (a calendar span,
           not a measured recovery) was rolled back.  A15 records the
           alternatives; this is the judgement most in need of review.
    M = FY2026E consensus       (EPS 2.875 x shares) -> perpetual g2 = axis row
    H = FY2022 actual 60.21亿  (management loosened, exports opened, global peak)
        -> post-peak normalisation, g = 0

Tier multiples therefore differ only by the ROE term and the H normalisation
(10.77 / 10.91 / 10.0): the g ladder 1.5% / 1.5% / 0% is flat-or-reverse, the
A2e-5 cyclical policy, and the multiples are not asserted to be reverse.

Why not a price scenario: this company's measured elasticity to the MAP ladder
is 0.049 — MAP rose 33.6% between 2025 and 2026 while net profit rose 1.6%.
Running a price scenario through that slope collapses the three tiers onto one
number, which is exactly the "分子比 ≈ 1.00" red line AGENTS.md draws for
cyclicals.  So the ticker still mounts _AXIS.phosphate-chain (the regime
definition and tier numbering are shared, and the ladder is cross-checked
against both the axis file and the peer mount 002895.SZ), but its numerator
comes from the other transmission path of the same regime.

The beta guard below is what keeps that honest: if the measured elasticity ever
climbs above 0.20, the "does not transmit" premise has failed and the ruler has
to be rebuilt rather than quietly re-fitted.

Run:  python3 eval/600096.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import (  # noqa: E402
    AXIS_PHOS, PHOS_INERT_BETA_CEILING, check_axis_g2_mount, check_phosphate_mount,
)
from lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600096.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "002895.SZ.md"
FORMULA_ID = "ytn_realized_earnings_regime_gordon_v4"
YI = 1e8

NP_PEAK_FY2022_YI = 60.21  # highest annual net profit the company has printed

REQUIRED = [
    "price", "shares", "np_l", "eps_m_consensus", "np_h",
    "equity", "r_perp", "g2_l", "g2_m", "g2_h",
    "pe_own_min", "pe_own_max", "map_l", "map_m", "map_h", "beta_map",
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

    errors += ladder("MAP", inp["map_l"], inp["map_m"], inp["map_h"])
    errors += check_phosphate_mount(
        (inp["map_l"], inp["map_m"], inp["map_h"]),
        peer_md=PEER.read_text(encoding="utf-8"),
    )
    # The numerator deliberately does NOT ride the ladder (A6).  That premise is
    # only valid while the measured elasticity stays near zero.
    if inp["beta_map"] >= PHOS_INERT_BETA_CEILING:
        errors.append(
            f"beta_map={inp['beta_map']:g} >= {PHOS_INERT_BETA_CEILING:g}: this "
            "ticker's numerator is not driven by the MAP ladder (A6) — if it now "
            "transmits, the main ruler must be rebuilt, not re-fitted"
        )
    errors += check_axis_g2_mount(AXIS_PHOS, inp["g2_m"])
    errors += check_r(inp["r_perp"], "r_perp")
    for k in ("g2_l", "g2_m", "g2_h"):
        errors += check_g_cap(inp[k], k)
    # A2e-5 cyclical: the g ladder is flat-or-reverse; L shares the axis row.
    if abs(inp["g2_l"] - inp["g2_m"]) > 1e-9:
        errors.append(f"g2_l {inp['g2_l']} must equal g2_m {inp['g2_m']} (axis 永续 g2, flat; A15)")
    if inp["g2_h"] > inp["g2_m"]:
        errors.append(f"g2_h {inp['g2_h']} > g2_m {inp['g2_m']} — H is post-peak normalisation (≤ g_M)")
    if abs(inp["np_h"] - NP_PEAK_FY2022_YI) > 0.01:
        errors.append(
            f"np_h={inp['np_h']:g}亿 must be the FY2022 realised peak "
            f"{NP_PEAK_FY2022_YI}亿 — H is that peak itself, not an extrapolation"
        )
    if errors:
        return report(errors)

    # --- the ruler -------------------------------------------------------------
    np_m = inp["eps_m_consensus"] * inp["shares"] / YI
    r = inp["r_perp"]
    roe = {"L": inp["np_l"] / inp["equity"], "M": np_m / inp["equity"], "H": inp["np_h"] / inp["equity"]}
    pe = {t: perpetual_pe(inp[f"g2_{t.lower()}"], roe[t], r) for t in ("L", "M", "H")}
    for tag, val in pe.items():
        if not (inp["pe_own_min"] <= val <= inp["pe_own_max"]):
            errors.append(
                f"{tag} generated PE {val:.2f} outside own realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — stop, do not force g (Phase 3 §A6)"
            )
    tiers = (("L", inp["np_l"], pe["L"]), ("M", np_m, pe["M"]), ("H", inp["np_h"], pe["H"]))
    computed = {}
    rows = []
    for tag, npp, mult in tiers:
        eps = npp * YI / inp["shares"]
        computed[tag] = eps * mult
        rows.append((tag, npp, eps, mult, eps * mult))

    errors += ladder("net profit", inp["np_l"], np_m, inp["np_h"])
    L, M, H = computed["L"], computed["M"], computed["H"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    flat = [row[2] * pe["M"] for row in rows]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder collapsed: {flat}")

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        f"axis OK vs _AXIS.phosphate-chain and peer 002895.SZ: MAP "
        f"{inp['map_l']:g}/{inp['map_m']:g}/{inp['map_h']:g} 元/吨 "
        f"(beta={inp['beta_map']:g} < {PHOS_INERT_BETA_CEILING:g}: numerator does not ride it)"
    )
    labels = {
        "L": "FY2023 actual  (regime)   ",
        "M": "FY2026E consensus         ",
        "H": "FY2022 actual  (loosened) ",
    }
    for tag, npp, eps, mult, anchor in rows:
        print(f"{tag}: {labels[tag]}  np={npp:6.2f}亿  eps={eps:.4f}  ROE={roe[tag]:.2%}  pe={mult:.3f}  anchor={anchor:.4f}")
    print(f"Gordon: r={r:g}  g ladder L {inp['g2_l']:g} / M {inp['g2_m']:g} / H {inp['g2_h']:g} (flat-or-reverse); "
          f"PE spread = ROE term + H normalisation only  guardrail [{inp['pe_own_min']}, {inp['pe_own_max']}] OK")
    g_px, ok_px = implied_g(inp["price"] / (np_m * YI / inp["shares"]), roe["M"], r)
    print(f"deep_discount 压力坐标: 谷底 x 1/r = {inp['np_l'] * YI / inp['shares'] / r:.2f}; "
          f"交叉尺 (A16): 现价 {inp['price'] / (np_m * YI / inp['shares']):.2f}x EPS_M → 市价隐含永续 g {g_px:+.2%} "
          f"({'well-conditioned' if ok_px else 'ill-conditioned'})")
    per_yi = YI / inp["shares"] * pe["M"]
    print(f"sensitivity: +1亿 net profit -> M anchor {per_yi:+.2f} CNY")
    print(f"flat-multiple ladder @PE_M {pe['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={rows[0][2] / rows[1][2]:.4f} H={rows[2][2] / rows[1][2]:.4f} "
        f"| 倍数比 L={pe['L'] / pe['M']:.4f} H={pe['H'] / pe['M']:.4f} | V_opt/M 0"
    )
    print(f"price={inp['price']} zone={zone}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
