#!/usr/bin/env python3
"""000725.SZ (BOE) valuation eval — recompute anchors from frameworks/000725.SZ.md.

formula_id: boe_midcycle_eps_flat_pe_v1

Illustrative v1: consolidated mid-cycle NI ladder x flat PE.  V_opt is read
from the framework and priced tier by tier in 表3 only; probabilities never
enter the base deck.

Known Class B debt (the ticker is queued for a rebuild, not patched here):
the §3 Inputs table still carries p_l / p_m / p_h rows, which A2e-7a forbids.
That is reported as a warning below rather than a failure so the anchor
recomputation stays runnable until the rebuild lands.

Run:  python3 eval/000725.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "000725.SZ.md"
FORMULA_ID = "boe_midcycle_eps_flat_pe_v1"
REQUIRED = ["price", "shares", "bps", "ni_l", "ni_m", "ni_h", "pe", "v_opt", "pb_floor"]
TIERS = ("l", "m", "h")


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # A2e-7a: probabilities belong in 表3 only.  Warning, not failure — see
    # the module docstring; the Inputs cleanup is part of the Class B rebuild.
    leaked = sorted(k for k in inp if k.startswith("p_"))

    eps = {t: inp[f"ni_{t}"] / inp["shares"] for t in TIERS}
    errors += ladder("NI", inp["ni_l"], inp["ni_m"], inp["ni_h"])
    L, M, H = (eps[t] * inp["pe"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    flat_errs, flat = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), inp["pe"])
    errors += flat_errs
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    floor = inp["pb_floor"] * inp["bps"]
    p = stated_p_tiers(md)
    if p is None:
        errors.append("p_L/p_M/p_H not stated in Outputs")

    print(f"formula_id={FORMULA_ID}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper()}: NI {inp[f'ni_{t}'] / 1e8:.1f}亿 eps {eps[t]:.4f} x {inp['pe']:g} = {a:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  floor(PB ref)={floor:.2f}")
    print(
        f"L/M={L / M:.2f} (分子比 {eps['l'] / eps['m']:.2f} x 倍数比 1.00) "
        f"H/M={H / M:.2f} (分子比 {eps['h'] / eps['m']:.2f}) "
        f"width={(H - L) / (2 * M):.2f} V_opt/M={inp['v_opt'] / M:.2f}"
    )
    print(f"flat-multiple ladder @ {inp['pe']:g}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"price={inp['price']} zone={zone}")
    if p:
        band = tuple(a + pk * inp["v_opt"] for a, pk in zip((L, M, H), p))
        a2, b2 = cut_points(*band)
        print(
            f"zone+V: {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f} A'={a2:.2f} B'={b2:.2f} "
            f"zone+V={zone_of(inp['price'], *band)}"
        )
    if inp["price"] > H:
        print(f"implied p=(P-H)/V_opt={(inp['price'] - H) / inp['v_opt']:.2f}")
    if leaked:
        print(f"WARN: probability fields in §3 Inputs {leaked} — A2e-7a, pending Class B rebuild")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
