#!/usr/bin/env python3
"""6655.HK (Huaxin Cement / Huaxin Building Materials) valuation eval.

frameworks/6655.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: huaxin_dom_ovs_dual_leg_hk_anchored_v1

Main ruler: two legs sharing one multiple distribution but opposite policies.
  * domestic cement (66.61% of revenue, cyclical)  -> multiples run REVERSE
    (7.98 / 5.82 / 5.25): trough earnings get the high multiple
  * overseas (33.39%, fast_grower)                 -> multiples run FORWARD
    (4.27 / 5.82 / 12.78)
Both sets are quantiles of the same series — the H-share own-year PE band
[4.27, 12.78] — so the legs differ in policy, not in provenance.

Anchored on the H share.  That matters more here than anywhere else in the
repo: the A-share own-year PE median is 11.42 versus 5.82 for the H share, so
borrowing the A-share band would lift the whole range by 96% and turn today's
`optimistic` into `conservative`.  The guard below keeps `pe_a_mid` out of the
computation path entirely — it is present in Inputs only as a comparison.

The L numerator is FY2024's realised trough EPS, not the consensus low.  With
the consensus low (1.437) the L anchor becomes 11.32 against an M of 11.59 —
the two tiers collapse into each other.  A cyclical needs a measured trough.

Run:  python3 eval/6655.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report, reverse_ladder,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "6655.HK.md"
FORMULA_ID = "huaxin_dom_ovs_dual_leg_hk_anchored_v1"

# H-share own-year PE band (2022-2025). Every leg multiple must live inside it.
HK_PE_BAND = (4.27, 12.78)

REQUIRED = [
    "price", "price_a", "shares", "bps", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h", "w_dom", "w_ovs",
    "pe_dom_l", "pe_dom_m", "pe_dom_h",
    "pe_ovs_l", "pe_ovs_m", "pe_ovs_h",
    "eps_consensus_low", "pe_a_mid",
]


def blend(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    if flat_pe is not None:
        return flat_pe
    return inp["w_dom"] * inp[f"pe_dom_{tag}"] + inp["w_ovs"] * inp[f"pe_ovs_{tag}"]


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    return inp[f"eps_{tag}"] * blend(inp, tag, flat_pe) / inp["fx_hkdcny"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: ladders and the two opposite multiple policies -------------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    errors += reverse_ladder(
        "pe_dom (cyclical)", inp["pe_dom_l"], inp["pe_dom_m"], inp["pe_dom_h"]
    )
    errors += ladder(
        "pe_ovs (fast_grower)", inp["pe_ovs_l"], inp["pe_ovs_m"], inp["pe_ovs_h"]
    )

    # --- Step 2: both legs must draw from one distribution ------------------
    lo, hi = HK_PE_BAND
    for key in ("pe_dom_l", "pe_dom_m", "pe_dom_h", "pe_ovs_l", "pe_ovs_m", "pe_ovs_h"):
        if not (lo - 1e-9 <= inp[key] <= hi + 1e-9):
            errors.append(f"{key}={inp[key]} outside H-share own-year band [{lo}, {hi}]")
    if abs(inp["pe_dom_m"] - inp["pe_ovs_m"]) > 1e-9:
        errors.append(
            f"legs must share the median: pe_dom_m={inp['pe_dom_m']} "
            f"vs pe_ovs_m={inp['pe_ovs_m']}"
        )
    if abs(inp["w_dom"] + inp["w_ovs"] - 1.0) > 1e-6:
        errors.append(f"weights must sum to 1: {inp['w_dom']} + {inp['w_ovs']}")

    # --- Step 3: anchored on H, so the A-share band must stay out of it ------
    if abs(inp["pe_a_mid"] - inp["pe_dom_m"]) < 1e-9:
        errors.append(
            "pe_a_mid leaked into the multiple path — this ticker is H-anchored "
            "and the A-share band sits 96% higher"
        )
    if errors:
        return report(errors, "FAIL (ladders/provenance)")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in ("l", "m", "h"))
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    flat = {t: anchor(inp, t, flat_pe=inp["pe_dom_m"]) for t in ("l", "m", "h")}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'EPS(CNY)':>10}{'国内PE':>9}{'海外PE':>9}{'混合PE':>9}"
          f"{'CNY价值':>10}{'锚点HKD':>10}")
    for t in ("l", "m", "h"):
        b = blend(inp, t)
        print(f"{t.upper():<3}{inp[f'eps_{t}']:10.3f}{inp[f'pe_dom_{t}']:9.2f}"
              f"{inp[f'pe_ovs_{t}']:9.2f}{b:9.3f}{inp[f'eps_{t}'] * b:10.2f}{anchor(inp, t):10.2f}")
    alt_l = inp["eps_consensus_low"] * blend(inp, "l") / inp["fx_hkdcny"]
    print(f"L 用共识下沿 {inp['eps_consensus_low']} 会得到 {alt_l:.2f} HKD "
          f"(L/M={alt_l / M:.2f}) — 档位塌陷,故用 FY2024 实测谷底")
    num_l, num_h = inp["eps_l"] / inp["eps_m"], inp["eps_h"] / inp["eps_m"]
    print(f"flat-multiple @PE={inp['pe_dom_m']:g}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | "
          f"倍数比 L/M={(L / M) / num_l:.2f} H/M={(H / M) / num_h:.2f}")
    print(f"price(H)={inp['price']} zone={zone}")
    fx = inp["fx_hkdcny"]
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} "
          f"| price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)}")
    print(f"H/A = {inp['price'] * fx / inp['price_a']:.3f} "
          f"| BPS {inp['bps']:.2f} CNY = {inp['bps'] / fx:.2f} HKD "
          f"({'高于' if inp['bps'] / fx > H else '低于'} H 档)")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
