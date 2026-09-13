#!/usr/bin/env python3
"""520900.SH (GF CSI China Reform HK Connect SOE Dividend ETF) eval.

formula_id: gf_soe_hk_div_sotp_index_pe_flat_v1

Current multiple MUST be the index PE, not a top-holder PE average.
Energy/shipping numerators are named report years; multiples flat.
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

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "520900.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "513530.SH.md"
FORMULA_ID = "gf_soe_hk_div_sotp_index_pe_flat_v1"

REQUIRED = [
    "price", "fee_drag", "pe_now",
    "w_ene", "w_ind", "w_resc", "w_ann",
    "pe_ene", "pe_ind", "pe_ann",
    "eps_ene_l", "eps_ene_m", "eps_ene_h",
    "eps_ind_l", "eps_ind_m", "eps_ind_h",
    "eps_ann_l", "eps_ann_m", "eps_ann_h",
    "cnooc_ni_l", "cnooc_ni_m", "cnooc_ni_h",
    "shenhua_ni_l", "shenhua_ni_m", "shenhua_ni_h",
    "cosco_ni_l", "cosco_ni_m", "cosco_ni_h",
]


def _s(inp: dict[str, float], tag: str) -> float:
    pe_now = inp["pe_now"]
    return (
        inp["w_ene"] * inp[f"eps_ene_{tag}"] * inp["pe_ene"] / pe_now
        + inp["w_ind"] * inp[f"eps_ind_{tag}"] * inp["pe_ind"] / pe_now
        + inp["w_resc"] * inp[f"eps_ene_{tag}"] * inp["pe_ene"] / pe_now
        + inp["w_ann"] * inp[f"eps_ann_{tag}"] * inp["pe_ann"] / pe_now
    )


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    wsum = inp.get("w_ene", 0) + inp.get("w_ind", 0) + inp.get("w_resc", 0) + inp.get("w_ann", 0)
    if abs(wsum - 1.0) > 0.002:
        errors.append(f"weights sum {wsum:.4f} != 1")
    errors += ladder("ene ni", inp.get("cnooc_ni_l", 0), inp.get("cnooc_ni_m", 1), inp.get("cnooc_ni_h", 2))
    errors += ladder("shenhua ni", inp.get("shenhua_ni_l", 0), inp.get("shenhua_ni_m", 1), inp.get("shenhua_ni_h", 2))
    errors += ladder("cosco ni", inp.get("cosco_ni_l", 0), inp.get("cosco_ni_m", 1), inp.get("cosco_ni_h", 2))
    # CNOOC 2020/2025 and Shenhua 2020/2025 must match the energy L blend ingredients
    if abs(inp["cnooc_ni_l"] / inp["cnooc_ni_m"] - 0.205) > 0.01:
        errors.append("cnooc L/M ratio drifted from 2020/2025 = 0.205")
    if abs(inp["shenhua_ni_l"] / inp["shenhua_ni_m"] - 0.742) > 0.01:
        errors.append("shenhua L/M ratio drifted from 2020/2025 = 0.742")
    if abs(inp["cosco_ni_l"] / inp["cosco_ni_m"] - 0.773) > 0.01:
        errors.append("cosco L/M ratio drifted from 2023/2025 = 0.773")
    if PEER.exists():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        for k in ("cnooc_ni_l", "cnooc_ni_m", "cnooc_ni_h",
                  "shenhua_ni_l", "shenhua_ni_m", "shenhua_ni_h"):
            if k in peer and abs(peer[k] - inp[k]) > 0.2:
                errors.append(f"shared {k}: 520900={inp[k]} 513530={peer[k]}")
    if errors:
        return report(errors)

    computed = {
        "L": scale(inp["price"], inp["fee_drag"], _s(inp, "l")),
        "M": scale(inp["price"], inp["fee_drag"], _s(inp, "m")),
        "H": scale(inp["price"], inp["fee_drag"], _s(inp, "h")),
    }
    if not (computed["L"] < computed["M"] < computed["H"]):
        return report(["ladder collapsed"])
    # flat-multiple: same pe_* across L/M/H so the ladder is 100% numerator
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
