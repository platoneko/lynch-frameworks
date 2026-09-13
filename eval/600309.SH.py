#!/usr/bin/env python3
"""600309.SH (Wanhua Chemical) valuation eval.

frameworks/600309.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: wanhua_segment_margin_ladder_gp_bridge_inverse_pe_v2

The scenario variable is the *spread*, not volume.  Revenue is frozen at the
2026H1 level in all three scenarios; only the three segment gross margins move,
and all three sets are numbers the company itself has already printed:

    L = 2025H1 actuals   (PU 26% / petchem  0% / new materials  9%)
    M = 2026H1 actuals   (PU 27% / petchem  7% / new materials 16%)
    H = 2026Q2 actual blended margin 19%, which implies PU 33.04%

Gross profit -> annualise -> less opex (the gross-to-operating gap, held flat)
-> operating profit -> x conv (tax + minority, measured on 2026H1) -> net
profit to parent -> / shares -> x that tier's PE (an *inverse* band: trough
earnings get the high multiple, peak earnings the low one — A2e-5's default for
`cyclical`, and here backed by a measured price elasticity, A6).

Why freezing revenue matters enough to guard: nine years of this company's
history say volume growth did not reach the bottom line (revenue +283%, net
profit +12%, gross margin 39.70% -> 13.42%).  Putting volume into the scenarios
would reintroduce a logic the filings already falsified — so the guards below
assert the margins move and nothing else does.

The H tier is guarded on *both* sides, because checking only the numerator is
what let the previous flat band through.  The company did print EPS 7.85
(FY2021); over the four months the market could see it, the average close was
88.34.  A flat 15.62x put H at 119.28 — 35% above a price that earnings level
has never fetched.  So H is capped against that print, not only against 7.85.

Run:  python3 eval/600309.SH.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600309.SH.md"
FORMULA_ID = "wanhua_segment_margin_ladder_gp_bridge_inverse_pe_v2"
YI = 1e8

# Audited baseline: 2026H1 net profit to parent x 2 (100.6296亿 x 2).
BASE_NP_PARENT_YI = 201.2592
BASE_NP_TOL_YI = 0.5

EPS_PEAK_FY2021 = 7.85  # highest EPS the company has ever printed
# ...and what the market actually paid while that EPS was the visible TTM:
# average monthly close over 2022-05..2022-08, the window between the FY2021
# annual report and the 2022 interim.  The numerator guard alone is not enough
# (A5): an anchor can clear 7.85 and still price a multiple peak earnings has
# never been given.
PRICE_AT_EPS_PEAK = 88.34
H_ANCHOR_HEADROOM = 1.25  # 2026's balance sheet and capex carry the difference
SEG_RESIDUAL_MAX = 0.05  # segment table vs consolidated GP, as a share of GP

REQUIRED = [
    "price", "shares", "rev_h1", "gm_rate_h1", "op_h1", "np_h1",
    "rev_pu", "rev_pc", "rev_nm",
    "gm_m_pu", "gm_m_pc", "gm_m_nm",
    "gm_l_pu", "gm_l_pc", "gm_l_nm",
    "gm_h_blended", "conv", "pe_l", "pe_m", "pe_h", "gamma_pe", "gamma_pe_se",
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

    # Step 1 — weld the bridge to the filing.
    gp_h1_m = inp["rev_h1"] * inp["gm_rate_h1"]
    seg_gp_m = (
        inp["rev_pu"] * inp["gm_m_pu"]
        + inp["rev_pc"] * inp["gm_m_pc"]
        + inp["rev_nm"] * inp["gm_m_nm"]
    )
    gp_other = gp_h1_m - seg_gp_m
    opex = gp_h1_m - inp["op_h1"]

    # The sell-side segment table and the consolidated statement are two
    # different documents; a large residual means they stopped agreeing.
    if not (0.0 <= gp_other <= SEG_RESIDUAL_MAX * gp_h1_m):
        errors.append(
            f"segment residual {gp_other:.4f}亿 outside [0, {SEG_RESIDUAL_MAX:.0%}] "
            f"of gross profit {gp_h1_m:.4f}亿"
        )
    for leg, lo, hi in (
        ("pu", inp["gm_l_pu"], inp["gm_m_pu"]),
        ("pc", inp["gm_l_pc"], inp["gm_m_pc"]),
        ("nm", inp["gm_l_nm"], inp["gm_m_nm"]),
    ):
        if lo > hi:
            errors.append(f"L margin above M margin on leg {leg}: {lo} > {hi}")
    if inp["gm_h_blended"] <= inp["gm_rate_h1"]:
        errors.append(
            f"gm_h_blended {inp['gm_h_blended']} must exceed 2026H1 blended "
            f"{inp['gm_rate_h1']}"
        )
    # Inverse is this ticker's stated multiple policy (A6); changing it here
    # without changing A6 would swap the policy silently.
    if not (inp["pe_l"] > inp["pe_m"] > inp["pe_h"]):
        errors.append(
            f"PE band must be inverse (A6): {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}"
        )
    if inp["gamma_pe"] >= 0.0:
        errors.append(
            f"gamma_pe={inp['gamma_pe']} must be negative for an inverse band (A6)"
        )
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if errors:
        return report(errors)

    # Step 2 — the ruler.
    def scenario(gp_half: float, pe: float):
        gp = gp_half * 2.0
        op = gp - opex * 2.0
        np_parent = op * inp["conv"]
        eps = np_parent * YI / inp["shares"]
        return gp, op, np_parent, eps, eps * pe

    gp_l_half = (
        inp["rev_pu"] * inp["gm_l_pu"]
        + inp["rev_pc"] * inp["gm_l_pc"]
        + inp["rev_nm"] * inp["gm_l_nm"]
        + gp_other
    )
    gp_h_half = inp["rev_h1"] * inp["gm_h_blended"]

    sc_l = scenario(gp_l_half, inp["pe_l"])
    sc_m = scenario(gp_h1_m, inp["pe_m"])
    sc_h = scenario(gp_h_half, inp["pe_h"])

    if abs(sc_m[2] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {sc_m[2]:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )
    if sc_h[3] > EPS_PEAK_FY2021:
        errors.append(
            f"EPS_H {sc_h[3]:.4f} exceeds FY2021 peak {EPS_PEAK_FY2021} — "
            "no longer a modelled upper edge"
        )
    h_cap = H_ANCHOR_HEADROOM * PRICE_AT_EPS_PEAK
    if sc_h[4] > h_cap:
        errors.append(
            f"anchor H {sc_h[4]:.2f} exceeds {h_cap:.2f} = {H_ANCHOR_HEADROOM} x "
            f"{PRICE_AT_EPS_PEAK} (what the market paid at TTM EPS "
            f"{EPS_PEAK_FY2021}) — the numerator cleared the peak but the "
            "multiple did not (A5)"
        )

    # The band's own gamma must agree with the measured one: same sign, and not
    # steeper than the measurement allows.  A band more inverse than the evidence
    # is construction, not measurement (A2e-5「散布 MUST NOT 来自构造手法」).
    # The floor is gamma_pe minus one standard error, not the point estimate —
    # gamma_pe is an estimate off 11 windows, and treating it as exact would
    # reject bands the data cannot distinguish from it.
    gamma_floor = inp["gamma_pe"] - inp["gamma_pe_se"]
    for tag, pe, eps in (("L", inp["pe_l"], sc_l[3]), ("H", inp["pe_h"], sc_h[3])):
        implied = math.log(pe / inp["pe_m"]) / math.log(eps / sc_m[3])
        if not (gamma_floor <= implied < 0.0):
            errors.append(
                f"band-implied gamma on {tag} = {implied:+.3f} outside "
                f"[{gamma_floor:+.3f}, 0) = gamma_pe {inp['gamma_pe']:+.3f} "
                f"-1se {inp['gamma_pe_se']:.3f} (A6)"
            )

    L, M, H = sc_l[4], sc_m[4], sc_h[4]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # Step 3 — report.
    pu_h_implied = (
        gp_h_half - gp_other
        - inp["rev_pc"] * inp["gm_m_pc"]
        - inp["rev_nm"] * inp["gm_m_nm"]
    ) / inp["rev_pu"]
    print(f"formula_id={FORMULA_ID}")
    print(
        f"segment residual gp_other={gp_other:.4f}亿 ({gp_other / gp_h1_m:.2%} of GP), "
        f"opex={opex:.4f}亿/half"
    )
    for tag, sc, desc in (
        ("L", sc_l, f"PU {inp['gm_l_pu']:.0%} / PC {inp['gm_l_pc']:.0%} / NM {inp['gm_l_nm']:.0%}"),
        ("M", sc_m, f"PU {inp['gm_m_pu']:.0%} / PC {inp['gm_m_pc']:.0%} / NM {inp['gm_m_nm']:.0%}"),
        ("H", sc_h, f"blended {inp['gm_h_blended']:.0%} -> PU {pu_h_implied:.2%} implied"),
    ):
        print(
            f"{tag}: {desc:<44} gp={sc[0]:7.2f}  op={sc[1]:7.2f}  np={sc[2]:7.2f}亿  "
            f"eps={sc[3]:.4f}  anchor={sc[4]:.4f}"
        )
    per_pct_pu = inp["rev_pu"] * 0.01 * 2.0 * inp["conv"] * YI / inp["shares"] * inp["pe_m"]
    print(
        f"sensitivity: +1pct PU margin -> anchor {per_pct_pu:+.2f} CNY; "
        f"EPS_H {sc_h[3]:.4f} vs FY2021 peak {EPS_PEAK_FY2021}"
    )
    g_l = math.log(inp["pe_l"] / inp["pe_m"]) / math.log(sc_l[3] / sc_m[3])
    g_h = math.log(inp["pe_h"] / inp["pe_m"]) / math.log(sc_h[3] / sc_m[3])
    print(
        f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} (inverse) | "
        f"gamma implied L={g_l:+.3f} H={g_h:+.3f} vs measured {inp['gamma_pe']:+.3f}"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={sc_l[3] / sc_m[3]:.4f} H={sc_h[3] / sc_m[3]:.4f}"
    )
    print(f"price={inp['price']} zone={zone}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
