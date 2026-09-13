#!/usr/bin/env python3
"""600096.SH (Yuntianhua) valuation eval.

frameworks/600096.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: ytn_realized_earnings_regime_flat_pe_v1

Main ruler: three *already-printed or already-consensus* annual net profits,
times one flat PE.

    L = FY2023 actual 45.22亿  (pricing management tightened, exports shrank)
    M = FY2026E consensus       (EPS 2.875 x shares)
    H = FY2022 actual 60.21亿  (management loosened, exports opened, global peak)

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
from lib.axes import PHOS_INERT_BETA_CEILING, check_phosphate_mount  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600096.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "002895.SZ.md"
FORMULA_ID = "ytn_realized_earnings_regime_flat_pe_v1"
YI = 1e8

NP_PEAK_FY2022_YI = 60.21  # highest annual net profit the company has printed

REQUIRED = [
    "price", "shares", "np_l", "eps_m_consensus", "np_h",
    "pe_l", "pe_m", "pe_h", "map_l", "map_m", "map_h", "beta_map",
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
    if not (inp["pe_l"] == inp["pe_m"] == inp["pe_h"]):
        errors.append(
            f"PE band must be flat (A5): {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}"
        )
    if abs(inp["np_h"] - NP_PEAK_FY2022_YI) > 0.01:
        errors.append(
            f"np_h={inp['np_h']:g}亿 must be the FY2022 realised peak "
            f"{NP_PEAK_FY2022_YI}亿 — H is that peak itself, not an extrapolation"
        )
    if errors:
        return report(errors)

    # --- the ruler -------------------------------------------------------------
    np_m = inp["eps_m_consensus"] * inp["shares"] / YI
    tiers = (("L", inp["np_l"], inp["pe_l"]), ("M", np_m, inp["pe_m"]), ("H", inp["np_h"], inp["pe_h"]))
    computed = {}
    rows = []
    for tag, npp, pe in tiers:
        eps = npp * YI / inp["shares"]
        computed[tag] = eps * pe
        rows.append((tag, npp, eps, pe, eps * pe))

    errors += ladder("net profit", inp["np_l"], np_m, inp["np_h"])
    L, M, H = computed["L"], computed["M"], computed["H"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])

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
        "L": "FY2023 actual  (tightened)",
        "M": "FY2026E consensus         ",
        "H": "FY2022 actual  (loosened) ",
    }
    for tag, npp, eps, pe, anchor in rows:
        print(f"{tag}: {labels[tag]}  np={npp:6.2f}亿  eps={eps:.4f}  pe={pe:g}  anchor={anchor:.4f}")
    per_yi = YI / inp["shares"] * inp["pe_m"]
    print(f"sensitivity: +1亿 net profit -> anchor {per_yi:+.2f} CNY; +0.5x PE -> M {0.5 * rows[1][2]:+.2f} CNY")
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} (flat)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={rows[0][2] / rows[1][2]:.4f} H={rows[2][2] / rows[1][2]:.4f}"
    )
    print(f"price={inp['price']} zone={zone}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
