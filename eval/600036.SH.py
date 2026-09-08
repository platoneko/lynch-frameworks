#!/usr/bin/env python3
"""600036.SH (China Merchants Bank) valuation eval — recompute anchors from frameworks/600036.SH.md.

frameworks/600036.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: cmb_pb_roe_provision_reversal_v1

Main ruler: PB-ROE.  anchor = BPS x PB_tier x (EPS_tier / EPS_M).
  * PB tiers are the bank's own-year PB low / median / high (0.6653 / 0.9648 /
    1.2332) — one distribution, three quantiles.
  * EPS tiers are the consensus range, except L, which subtracts the cost of
    putting provision coverage back where it stood one year ago (407.94%).

That L is the whole point of the framework.  CMB grew profit 2% while NPLs rose
five quarters straight and coverage fell 26pp — some of that growth was bought
by releasing provisions.  The guard below recomputes the buy-back cost from the
raw NPL balance so `eps_l` cannot quietly become an unsourced number.

This ticker takes the A2e-2c-ex `slow_grower` exemption: the spread is
de-rate driven (numerator ratios 0.885 / 1.017).  The exemption obliges the
framework to *state* that and to report the flat-multiple width, so this script
prints the flat band rather than merely asserting the ladder.

Run:  python3 eval/600036.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600036.SH.md"
FORMULA_ID = "cmb_pb_roe_provision_reversal_v1"
YI = 1e8

# own-year PB high, 2022 — A2e-2c-ex forbids H from exceeding the measured top.
PB_MEASURED_TOP = 1.2332
EPS_L_TOL = 0.005

REQUIRED = [
    "price", "price_h", "shares", "bps", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h", "pb_lo", "pb_mid", "pb_hi",
    "npl", "cov_now", "cov_l", "tax_rate", "eps_consensus_low",
]


def anchor(inp: dict[str, float], tag: str, flat_pb: float | None = None) -> float:
    pb = flat_pb if flat_pb is not None else inp[{"l": "pb_lo", "m": "pb_mid", "h": "pb_hi"}[tag]]
    return inp["bps"] * pb * inp[f"eps_{tag}"] / inp["eps_m"]


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
    errors += ladder("pb", inp["pb_lo"], inp["pb_mid"], inp["pb_hi"])
    if inp["pb_hi"] > PB_MEASURED_TOP + 1e-9:
        errors.append(
            f"pb_hi {inp['pb_hi']} exceeds own-year measured top {PB_MEASURED_TOP} "
            "— A2e-2c-ex forbids H from going above what the market has actually paid"
        )
    if errors:
        return report(errors, "FAIL (ladders)")

    # --- Step 2: provision identity — L must be derivable, not asserted ------
    extra = inp["npl"] * (inp["cov_l"] - inp["cov_now"])
    d_eps = extra * (1.0 - inp["tax_rate"]) / inp["shares"]
    eps_l_derived = inp["eps_consensus_low"] - d_eps
    if abs(eps_l_derived - inp["eps_l"]) > EPS_L_TOL:
        errors.append(
            f"eps_l {inp['eps_l']} vs provision-identity {eps_l_derived:.4f} "
            f"(consensus low {inp['eps_consensus_low']} - {d_eps:.4f})"
        )
    if inp["cov_l"] <= inp["cov_now"]:
        errors.append("cov_l must exceed cov_now — L is a provision *rebuild*")

    # --- Step 3: anchors and the flat-multiple width -------------------------
    L, M, H = (anchor(inp, t) for t in ("l", "m", "h"))
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    flat = {t: anchor(inp, t, flat_pb=inp["pb_mid"]) for t in ("l", "m", "h")}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])
    flat_width = (flat["h"] - flat["l"]) / (2 * flat["m"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'EPS':>8}{'情景ROE':>10}{'PB':>9}{'锚点':>9}")
    for t, pb_key in (("l", "pb_lo"), ("m", "pb_mid"), ("h", "pb_hi")):
        eps = inp[f"eps_{t}"]
        print(f"{t.upper():<3}{eps:8.3f}{eps / inp['bps']:9.2%}{inp[pb_key]:9.4f}{anchor(inp, t):9.2f}")
    print(f"拨备回补: NPL {inp['npl'] / YI:.1f}亿 x ({inp['cov_l']:.4f}-{inp['cov_now']:.4f}) "
          f"= {extra / YI:.1f}亿, 税后每股 {d_eps:.4f} -> eps_l {eps_l_derived:.4f} ✓")
    print(f"⚠ de-rate 主导: 分子比 {inp['eps_l'] / inp['eps_m']:.3f}/{inp['eps_h'] / inp['eps_m']:.3f}, "
          f"倍数比 {inp['pb_lo'] / inp['pb_mid']:.3f}/{inp['pb_hi'] / inp['pb_mid']:.3f}")
    print(f"flat-multiple @PB={inp['pb_mid']:.4f}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {flat_width:.1%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"price={inp['price']} zone={zone}")
    fx = inp["fx_hkdcny"]
    print(f"H股对照(HKD): L={L / fx:.2f} M={M / fx:.2f} H={H / fx:.2f} "
          f"| price_h={inp['price_h']} zone_h={zone_of(inp['price_h'], L / fx, M / fx, H / fx)}")
    print(f"H/A = {inp['price_h'] * fx / inp['price']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
