#!/usr/bin/env python3
"""000543.SZ (Anhui Wenergy) valuation eval.

frameworks/000543.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: wanneng_coal_scenario_runrate_pe_v1

Main ruler: whole-company PE.  The three tiers are *named* by coal price
(FY2022 1,268 / current ~840 / FY2025 703 per tonne) but *computed* from the
company's own realised run-rates at those coal prices — so no coal-to-earnings
elasticity has to be invented.  Coal only labels the scenario; the guard below
checks its direction runs opposite to the numerator, which is the one thing a
label still has to get right.

Two口径 choices decide the answer, so both are re-derived here rather than
asserted:

  * M uses TTM (four realised quarters), NOT 1H26 annualised.  Doubling a half
    year smuggles in "H2 equals H1"; FY2025 split 0.4808 / 0.4676, so the
    seasonality does not support it.  The script prints what the rejected 口径
    would have produced, because it changes the zone.
  * H does NOT compress the multiple to the 7.91 own-year low.  Lynch's reverse
    rule targets *peak* earnings, and FY2025's 0.9484 is a normal year, not a
    peak — compressing there collapses H/M to 1.011.  The script prints that
    collapse as the numeric justification.

Run:  python3 eval/000543.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "000543.SZ.md"
FORMULA_ID = "wanneng_coal_scenario_runrate_pe_v1"

PE_OWN_YEAR_LOW = 7.91      # FY2025 — what H would use under a naive reverse policy
FLOOR_RECHECK_RATIO = 0.30  # A2e-1: below this the earnings ruler has failed at L
MIN_L_DIV_YIELD = 0.06      # slow_grower secondary needs a real dividend floor

REQUIRED = [
    "price", "shares", "bps",
    "eps_l", "eps_m", "eps_h", "pe_l", "pe_m", "pe_h",
    "coal_l", "coal_m", "coal_h", "dps", "pb_lo", "eps_h1_x2",
]


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    return inp[f"eps_{tag}"] * (flat_pe if flat_pe is not None else inp[f"pe_{tag}"])


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: ladders, multiple policy, and the coal label's direction ----
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    # A2e-5 allows cyclical multiples to be reverse *or* flat, hence >= not >.
    if not (inp["pe_l"] >= inp["pe_m"] >= inp["pe_h"]):
        errors.append(
            f"cyclical multiple policy violated: pe {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} "
            "must be non-increasing (reverse or flat)"
        )
    # Coal is the scenario label; if it does not run opposite to earnings the
    # label has come unstuck from the numbers it is supposed to name.
    if not (inp["coal_l"] > inp["coal_m"] > inp["coal_h"]):
        errors.append(
            f"coal ladder {inp['coal_l']}/{inp['coal_m']}/{inp['coal_h']} must decrease "
            "as earnings rise — label and numerator disagree"
        )
    if errors:
        return report(errors, "FAIL (ladders)")

    # --- Step 2: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in ("l", "m", "h"))
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    flat = {t: anchor(inp, t, flat_pe=inp["pe_m"]) for t in ("l", "m", "h")}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    # --- Step 3: floor is a reference, not a backstop (A5) ------------------
    floor = inp["pb_lo"] * inp["bps"]
    if L / M <= FLOOR_RECHECK_RATIO:
        errors.append(
            f"scenario_L/M = {L / M:.3f} <= {FLOOR_RECHECK_RATIO} — the earnings ruler has "
            "failed at L; A2e-1 requires going back to the conversation"
        )
    div_yield_at_l = inp["dps"] / L
    if div_yield_at_l <= MIN_L_DIV_YIELD:
        errors.append(
            f"L implies only {div_yield_at_l:.2%} dividend yield — the slow_grower "
            "secondary's floor argument does not hold"
        )

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'煤价(元/吨)':>12}{'EPS':>9}{'PE':>8}{'锚点':>8}")
    for t in ("l", "m", "h"):
        print(f"{t.upper():<3}{inp[f'coal_{t}']:12.0f}{inp[f'eps_{t}']:9.4f}"
              f"{inp[f'pe_{t}']:8.2f}{anchor(inp, t):8.2f}")

    # The two口径 decisions, re-derived so they cannot drift into assertions.
    m_alt = inp["eps_h1_x2"] * inp["pe_m"]
    z_alt = zone_of(inp["price"], L, m_alt, H)
    print(f"被否决口径①  M 用 2026H1×2 ({inp['eps_h1_x2']:.4f}) -> M={m_alt:.2f}, "
          f"现价 zone 变 {z_alt}  (A2: H1×2 隐含 'H2=H1' 假设)")
    h_alt = inp["eps_h"] * PE_OWN_YEAR_LOW
    print(f"被否决口径②  H 压到 own-year 低沿 {PE_OWN_YEAR_LOW} -> H={h_alt:.2f}, "
          f"H/M={h_alt / M:.3f} 塌进 M  (A3: FY2025 是正常年景,不是周期峰值)")

    print(f"地板(参照,不兜底): PB {inp['pb_lo']} x BPS {inp['bps']} = {floor:.2f} "
          f"vs scenario_L {L:.2f}; scenario_L/M = {L / M:.3f} > {FLOOR_RECHECK_RATIO} ✓")
    print(f"股息地板交叉: DPS {inp['dps']} / L {L:.2f} = {div_yield_at_l:.2%} ✓")
    print(f"flat-multiple @PE={inp['pe_m']:g}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}")

    num_l, num_h = inp["eps_l"] / inp["eps_m"], inp["eps_h"] / inp["eps_m"]
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"分子比 L/M={num_l:.3f} H/M={num_h:.3f} | "
          f"倍数比 L/M={inp['pe_l'] / inp['pe_m']:.3f} H/M={inp['pe_h'] / inp['pe_m']:.3f}")
    print(f"price={inp['price']} zone={zone}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
