#!/usr/bin/env python3
"""603799.SH (Huayou Cobalt) valuation eval — recompute anchors from frameworks/603799.SH.md.

frameworks/603799.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on any mismatch.

formula_id: huayou_eight_leg_gp_bridge_conv_ladder_pe_v1

What makes this ticker's ruler different from the other two A-share cyclicals:
the scenario ladder does NOT live in the multiple, and it does not live in a
single commodity price either.  Eight legs each ride their own measured
half-year series (only copper is shifted by a price ladder), and the step that
actually moves the anchors is `conv` — the pretax-to-parent conversion rate,
which fell from 73.4% (FY2025) to 55.7% (2026H1) to 38.8% (2026Q2) because the
fastest-growing assets are the ones with the largest minority stakes
(Chengdu BAMO 63.14%, Huafei 49%, Huayue 40%).  Holding `conv` constant would
hide the single biggest variable in the story, so it is laddered from the 2026
quarterly prints — same year, same source, three quantiles (skill A2e-2b).

The L anchor is an asset floor, not an earnings scenario: every plausible opex
treatment puts the earnings scenario below the measured PB floor of 1.0228
(printed at the 2024-06 low of 20.82).  Guard 6 below is the skill A2e-1 test —
if the earnings scenario drops below 30% of M, the earnings ruler has failed at
L and the framework must go back to conversation rather than quietly ship.

Gross-profit style inputs are in 亿 CNY and already annualised (2026H1 x 2).

Run:  python3 eval/603799.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_inputs,
    reverse_ladder,
)
from eval.lib.zones import zone_of  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO / "frameworks" / "603799.SH.md"
PEER = REPO / "frameworks" / "601899.SH.md"
FORMULA_ID = "huayou_eight_leg_gp_bridge_conv_ladder_pe_v1"
YI = 1e8

# Audited baseline: 2026 interim net profit to parent x 2 (35.074054亿 x 2).
# The M scenario re-uses the interim segment table verbatim, so its recomputed
# net profit must land back on this number — that is what welds the eight-leg
# bridge to the filing.
BASE_NP_PARENT_YI = 70.1481
BASE_NP_TOL_YI = 0.5

# skill A2e-1: floor may win, but if the earnings scenario falls below this
# share of M the earnings ruler has failed at L and must be re-opened.
SCENARIO_L_MIN_RATIO = 0.30

# The shared USD copper ladder: our field -> the peer framework's field.
SHARED_LADDER = {"p_cu_l": "lme_cu_l", "p_cu_m": "lme_cu_m", "p_cu_h": "lme_cu_h"}

REQUIRED = [
    "price", "shares", "bps", "pb_floor",
    "gp_ni_prod_m", "gp_ni_prod_h",
    "gp_ni_mhp_m", "gp_ni_mhp_h",
    "gp_co_m", "gp_li_m", "gp_cam_m",
    "gp_pcam_m", "gp_pcam_h",
    "gp_trade_m",
    "rev_cu_base", "cost_cu_base",
    "p_cu_l", "p_cu_m", "p_cu_h",
    "opex", "pretax_l",
    "conv_l", "conv_m", "conv_h",
    "pe_l", "pe_m", "pe_h",
]

# Legs that are already at their measured peak in the interim print, so the H
# scenario leaves them where they are (see A7 / A8 / A9 / A5).
FLAT_LEGS = ("gp_co_m", "gp_li_m", "gp_cam_m", "gp_trade_m")


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- sanity guards (see §3 校验步骤) -------------------------------------
    errors += ladder("copper price", inp["p_cu_l"], inp["p_cu_m"], inp["p_cu_h"])
    errors += ladder("conv", inp["conv_l"], inp["conv_m"], inp["conv_h"])
    # Counter-cyclical PE (A13): a rising multiple across improving scenarios
    # would price the same optimism twice, on top of the conv ladder.
    errors += reverse_ladder("PE band", inp["pe_l"], inp["pe_m"], inp["pe_h"])
    for leg in ("gp_ni_prod", "gp_ni_mhp", "gp_pcam"):
        if inp[f"{leg}_h"] < inp[f"{leg}_m"]:
            errors.append(f"{leg}: H ({inp[f'{leg}_h']}) below M ({inp[f'{leg}_m']})")
    for k in ("conv_l", "conv_m", "conv_h"):
        if not (0.0 < inp[k] < 1.0):
            errors.append(f"{k}={inp[k]} outside (0,1)")
    if inp["cost_cu_base"] >= inp["rev_cu_base"]:
        errors.append("copper leg: cost exceeds revenue at base — check 口径")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- shared-ladder guard vs 601899.SH ------------------------------------
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors.append(f"peer 601899.SH missing {theirs}")
        elif abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(
                f"shared ladder drift: {ours}={inp[ours]} vs 601899.{theirs}={peer[theirs]}"
            )
    if errors:
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

    # --- the ruler -----------------------------------------------------------
    def copper_leg(price_usd_t: float) -> float:
        """Annualised copper gross profit, 亿 CNY — the only price-shifted leg."""
        return inp["rev_cu_base"] * price_usd_t / inp["p_cu_m"] - inp["cost_cu_base"]

    def gross_profit(suffix: str, p_cu: float) -> float:
        legs = sum(inp[k] for k in FLAT_LEGS)
        legs += sum(inp[f"{leg}_{suffix}"] for leg in ("gp_ni_prod", "gp_ni_mhp", "gp_pcam"))
        return legs + copper_leg(p_cu)

    def anchor(pretax: float, conv: float, pe: float) -> tuple[float, float, float]:
        np_parent = pretax * conv
        eps = np_parent * YI / inp["shares"]
        return np_parent, eps, eps * pe

    gp_m = gross_profit("m", inp["p_cu_m"])
    gp_h = gross_profit("h", inp["p_cu_h"])
    pretax_m, pretax_h = gp_m - inp["opex"], gp_h - inp["opex"]

    np_l, eps_l, scenario_l = anchor(inp["pretax_l"], inp["conv_l"], inp["pe_l"])
    np_m, eps_m, M = anchor(pretax_m, inp["conv_m"], inp["pe_m"])
    np_h, eps_h, H = anchor(pretax_h, inp["conv_h"], inp["pe_h"])

    floor = inp["pb_floor"] * inp["bps"]
    L = max(scenario_l, floor)
    floor_wins = floor > scenario_l

    # Baseline closure: M must reproduce the filed net profit to parent.
    if abs(np_m - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {np_m:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    # skill A2e-1: an earnings scenario this far below M means the earnings
    # ruler no longer describes the downside — that is a conversation, not a
    # number to ship.
    ratio = scenario_l / M if M else 0.0
    if floor_wins and ratio < SCENARIO_L_MIN_RATIO:
        errors.append(
            f"A2e-1: floor wins and scenario_L/M={ratio:.3f} < {SCENARIO_L_MIN_RATIO} "
            "— earnings ruler has failed at L, reopen the framework"
        )

    # skill A2e-2c: the three tiers must already be a ladder in the numerator,
    # so re-run them all at pe_m and check the ordering survives.
    flat = (eps_l * inp["pe_m"], eps_m * inp["pe_m"], eps_h * inp["pe_m"])
    errors += ladder("flat-multiple", *flat)

    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        "shared ladder OK vs 601899.SH: cu "
        + "/".join(f"{inp[k]:g}" for k in ("p_cu_l", "p_cu_m", "p_cu_h"))
        + " $/t"
    )
    print(
        f"L: pretax={inp['pretax_l']:7.2f} conv={inp['conv_l']:.4f} np={np_l:7.2f}亿 "
        f"eps={eps_l:.4f} pe={inp['pe_l']:g} scenario_L={scenario_l:.4f}"
    )
    print(
        f"   floor={floor:.4f} (pb {inp['pb_floor']:g} x bps {inp['bps']:g}) "
        f"-> L={L:.4f} ({'floor' if floor_wins else 'scenario'} wins), "
        f"scenario_L/M={ratio:.3f}"
    )
    for tag, gp, pretax, conv, np_, eps, pe, anc in (
        ("M", gp_m, pretax_m, inp["conv_m"], np_m, eps_m, inp["pe_m"], M),
        ("H", gp_h, pretax_h, inp["conv_h"], np_h, eps_h, inp["pe_h"], H),
    ):
        print(
            f"{tag}: gp={gp:7.2f} cu_leg={copper_leg(inp['p_cu_m'] if tag == 'M' else inp['p_cu_h']):6.2f} "
            f"pretax={pretax:7.2f} conv={conv:.4f} np={np_:7.2f}亿 eps={eps:.4f} "
            f"pe={pe:g} anchor={anc:.4f}"
        )
    print(f"flat-multiple ladder @pe_m={inp['pe_m']:g}: " + " < ".join(f"{v:.2f}" for v in flat))
    conv_pp = pretax_m * 0.01 * YI / inp["shares"] * inp["pe_m"]
    print(f"sensitivity: conv +1pp -> np {pretax_m * 0.01:.2f}亿, anchor {conv_pp:.2f} CNY (pe_m)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M) * 100:.2f}%")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
