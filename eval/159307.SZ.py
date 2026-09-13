#!/usr/bin/env python3
"""159307.SZ (Bosera CSI Dividend Low-Vol 100 ETF) valuation eval.

formula_id: bosera_div_lowvol_gordon10_flat_v1

Whole-basket Gordon PE = 10× (r=10%, g=0; index ROE ~8.8% ≈ r so growth
does not lift the multiple). L/H move the look-through EPS only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf_lookthrough import scale  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "159307.SZ.md"
FORMULA_ID = "bosera_div_lowvol_gordon10_flat_v1"

REQUIRED = [
    "price", "pe_now", "pe_m", "fee_drag",
    "eps_k_l", "eps_k_m", "eps_k_h",
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
    errors += ladder("eps_k", inp["eps_k_l"], inp["eps_k_m"], inp["eps_k_h"])
    if inp["pe_m"] != 10.0:
        errors.append(f"pe_m={inp['pe_m']} must be 10 (g=0 Gordon)")
    if not (0.97 <= inp["fee_drag"] <= 0.99):
        errors.append(f"fee_drag={inp['fee_drag']} expected ~0.98 for 0.20% fee")
    if errors:
        return report(errors)

    eps = inp["price"] / inp["pe_now"]
    computed = {
        "L": scale(eps, inp["fee_drag"], inp["eps_k_l"] * inp["pe_m"]),
        "M": scale(eps, inp["fee_drag"], inp["eps_k_m"] * inp["pe_m"]),
        "H": scale(eps, inp["fee_drag"], inp["eps_k_h"] * inp["pe_m"]),
    }
    # flat-multiple ladder IS the reported ladder (pe constant)
    if not (computed["L"] < computed["M"] < computed["H"]):
        return report(["flat-multiple ladder collapsed"])
    A, B = cut_points(computed["L"], computed["M"], computed["H"])
    computed["A"], computed["B"] = A, B
    zone = zone_of(inp["price"], computed["L"], computed["M"], computed["H"])
    errors = check_against_stated(md, computed, zone, tol=0.01)
    if errors:
        return report(errors)
    print(
        f"OK  L={computed['L']:.4f} M={computed['M']:.4f} H={computed['H']:.4f}  "
        f"zone={zone}  price={inp['price']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
