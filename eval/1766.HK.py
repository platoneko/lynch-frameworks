#!/usr/bin/env python3
"""1766.HK (CRRC Corporation) valuation eval.

frameworks/1766.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: crrc_hk_anchored_consensus_pe_v1

Main ruler: whole-company PE on the H share.  EPS tiers rescale one consensus
range (2026-04-20: low .514 / mean .554 / high .594) onto the latest mean
(.538), so both ends stay same-source even though the newest print has
degenerated to a point estimate.  PE tiers are the H-share own-year low /
median / high (5.49 / 9.20 / 13.19).

Two things this script deliberately does NOT do, both recorded in the
framework as `待补`:

  * It does not split the two legs into the numerator.  CRRC's segment table
    sums to 778.6亿 against 1,316.8亿 of revenue — a 41% gap.  Valuing legs off
    an unreconciled disclosure would put an unverified 口径 into the anchor
    path, so the legs stay in the check layer.  The guard prints the gap.
  * It does not give 新产业 a growth multiple.  Times Electric (3898.HK), the
    listed crown jewel of that segment, trades at PE 8.48 — *below* CRRC's own
    9.68.  There is no market evidence for a segment premium.

Like 600036.SH this ticker takes the A2e-2c-ex `slow_grower` exemption
(numerator ratios 0.928 / 1.072), so the flat-multiple width is printed rather
than merely asserted.

Run:  python3 eval/1766.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1766.HK.md"
FORMULA_ID = "crrc_hk_anchored_consensus_pe_v1"

# The 2026-04-20 consensus range the tiers are rescaled from (A1).
CONSENSUS_LOW, CONSENSUS_MEAN, CONSENSUS_HIGH = 0.514, 0.554, 0.594
EPS_TOL = 0.001
PE_MEASURED_TOP = 13.19  # H-share own-year high, 2025
SEGMENT_GAP_WARN = 0.20

REQUIRED = [
    "price", "price_a", "shares", "bps", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h", "pe_l", "pe_m", "pe_h",
    "w_rail", "w_new", "emu_2026", "emu_2025",
    "pe_a_mid", "seg_total_h1", "rev_h1",
]


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else inp[f"pe_{tag}"]
    return inp[f"eps_{tag}"] * pe / inp["fx_hkdcny"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: ladders -----------------------------------------------------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    errors += ladder("pe", inp["pe_l"], inp["pe_m"], inp["pe_h"])
    if inp["pe_h"] > PE_MEASURED_TOP + 1e-9:
        errors.append(
            f"pe_h {inp['pe_h']} exceeds own-year measured top {PE_MEASURED_TOP}"
        )

    # --- Step 2: both EPS ends must come from the same consensus range ------
    for tag, ref in (("l", CONSENSUS_LOW), ("h", CONSENSUS_HIGH)):
        derived = inp["eps_m"] * ref / CONSENSUS_MEAN
        if abs(derived - inp[f"eps_{tag}"]) > EPS_TOL:
            errors.append(
                f"eps_{tag} {inp[f'eps_{tag}']} vs rescaled {derived:.4f} "
                f"(mean {inp['eps_m']} x {ref}/{CONSENSUS_MEAN}) — ends not same-source"
            )

    # --- Step 3: check-layer only (legs never enter the anchor path) --------
    if abs(inp["w_rail"] + inp["w_new"] - 1.0) > 1e-6:
        errors.append(f"leg weights must sum to 1: {inp['w_rail']} + {inp['w_new']}")
    gap = 1.0 - inp["seg_total_h1"] / inp["rev_h1"]
    if inp["emu_2026"] >= inp["emu_2025"]:
        errors.append(
            f"EMU tender {inp['emu_2026']:.0f} >= prior {inp['emu_2025']:.0f} — "
            "§1 属性 C assumes a declining-but-better-than-feared tender; rerun the narrative"
        )
    if abs(inp["pe_a_mid"] - inp["pe_m"]) < 1e-9:
        errors.append("pe_a_mid leaked into the multiple path — this ticker is H-anchored")
    if errors:
        return report(errors, "FAIL (ladders/provenance)")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in ("l", "m", "h"))
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    flat = {t: anchor(inp, t, flat_pe=inp["pe_m"]) for t in ("l", "m", "h")}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])
    flat_width = (flat["h"] - flat["l"]) / (2 * flat["m"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'EPS(CNY)':>10}{'PE':>8}{'CNY价值':>10}{'锚点HKD':>10}")
    for t in ("l", "m", "h"):
        print(f"{t.upper():<3}{inp[f'eps_{t}']:10.4f}{inp[f'pe_{t}']:8.2f}"
              f"{inp[f'eps_{t}'] * inp[f'pe_{t}']:10.3f}{anchor(inp, t):10.2f}")
    print(f"共识区间同源 ✓ ({CONSENSUS_LOW}/{CONSENSUS_MEAN}/{CONSENSUS_HIGH} "
          f"缩放至最新 mean {inp['eps_m']})")
    marker = "⚠" if gap > SEGMENT_GAP_WARN else " "
    print(f"{marker} 分部缺口 {gap:.0%} (分部合计 {inp['seg_total_h1'] / 1e8:.0f}亿 vs "
          f"营收 {inp['rev_h1'] / 1e8:.0f}亿) — 两腿仅在校验层, 未入分子路径 (A5)")
    print(f"  两腿权重(仅校验): 铁路系 {inp['w_rail']:.4f} / 新产业 {inp['w_new']:.4f}; "
          f"M 档 EPS 分解 {inp['eps_m'] * inp['w_rail']:.3f} / {inp['eps_m'] * inp['w_new']:.3f}")
    print(f"  动车组招标 {inp['emu_2026']:.0f} 列 vs 上年 {inp['emu_2025']:.0f} 列 "
          f"({inp['emu_2026'] / inp['emu_2025'] - 1:+.1%})")
    num_l, num_h = inp["eps_l"] / inp["eps_m"], inp["eps_h"] / inp["eps_m"]
    print(f"⚠ de-rate 主导: 分子比 {num_l:.3f}/{num_h:.3f}, "
          f"倍数比 {inp['pe_l'] / inp['pe_m']:.3f}/{inp['pe_h'] / inp['pe_m']:.3f}")
    print(f"flat-multiple @PE={inp['pe_m']:g}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {flat_width:.1%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"price(H)={inp['price']} zone={zone}")
    fx = inp["fx_hkdcny"]
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} "
          f"| price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)}")
    print(f"H/A = {inp['price'] * fx / inp['price_a']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
