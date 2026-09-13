#!/usr/bin/env python3
"""513530.SH (Huatai-PB CSI HK Connect High Dividend QDII ETF) eval.

formula_id: huatai_hk_hdy_qdi_sotp_index_pe_v1

Index PE is the current blend. HSBC/BOCHK use Gordon PB-ROE (own ROE, not
CMB's). China Coal is look-through 1898.HK. Energy/shipping years shared
with 520900.SH.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import justified_pb  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "513530.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "520900.SH.md"
FORMULA_ID = "huatai_hk_hdy_qdi_sotp_index_pe_v1"

REQUIRED = [
    "price", "fee_drag", "pe_now", "r", "g_bank",
    "w_hsbc", "pb_hsbc", "roe_hsbc",
    "w_bochk", "pb_bochk", "roe_bochk",
    "w_feh", "w_fin_rest",
    "w_ind", "w_ene_rest", "w_cc", "w_res",
    "pe_ind", "pe_ene", "pe_res",
    "eps_ind_l", "eps_ind_m", "eps_ind_h",
    "eps_ene_l", "eps_ene_m", "eps_ene_h",
    "eps_res_l", "eps_res_m", "eps_res_h",
    "k_bank_l", "k_bank_m", "k_bank_h",
    "k_feh_l", "k_feh_m", "k_feh_h",
    "p_cc", "cc_l", "cc_m", "cc_h",
    "cnooc_ni_l", "cnooc_ni_m", "cnooc_ni_h",
    "shenhua_ni_l", "shenhua_ni_m", "shenhua_ni_h",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    wsum = (
        inp.get("w_hsbc", 0) + inp.get("w_bochk", 0) + inp.get("w_feh", 0)
        + inp.get("w_fin_rest", 0) + inp.get("w_ind", 0)
        + inp.get("w_ene_rest", 0) + inp.get("w_cc", 0) + inp.get("w_res", 0)
    )
    if abs(wsum - 1.0) > 0.003:
        errors.append(f"weights sum {wsum:.4f} != 1")
    if abs(inp.get("fee_drag", 0) - 0.94) > 0.005:
        errors.append("QDII fee_drag must be 0.94 (0.60%/10%)")
    if inp.get("r") != 0.10:
        errors.append("r must be 0.10")
    pb_h = justified_pb(inp["g_bank"], inp["roe_hsbc"], inp["r"])
    pb_b = justified_pb(inp["g_bank"], inp["roe_bochk"], inp["r"])
    if PEER.exists():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        for k in ("cnooc_ni_l", "cnooc_ni_m", "cnooc_ni_h",
                  "shenhua_ni_l", "shenhua_ni_m", "shenhua_ni_h"):
            if k in peer and abs(peer[k] - inp[k]) > 0.2:
                errors.append(f"shared {k}: 513530={inp[k]} 520900={peer[k]}")
    errors += ladder("cc", inp.get("cc_l", 0), inp.get("cc_m", 1), inp.get("cc_h", 2))
    if errors:
        return report(errors)

    k_hsbc = pb_h / inp["pb_hsbc"]
    k_bochk = pb_b / inp["pb_bochk"]

    def fin(tag: str) -> float:
        kb = inp[f"k_bank_{tag}"]
        kf = inp[f"k_feh_{tag}"]
        return (
            inp["w_hsbc"] * k_hsbc * kb
            + inp["w_bochk"] * k_bochk * kb
            + inp["w_feh"] * kf
            + inp["w_fin_rest"] * kb
        )

    def s(tag: str) -> float:
        pe_now = inp["pe_now"]
        return (
            fin(tag)
            + inp["w_ind"] * inp[f"eps_ind_{tag}"] * inp["pe_ind"] / pe_now
            + inp["w_ene_rest"] * inp[f"eps_ene_{tag}"] * inp["pe_ene"] / pe_now
            + inp["w_cc"] * inp[f"cc_{tag}"] / inp["p_cc"]
            + inp["w_res"] * inp[f"eps_res_{tag}"] * inp["pe_res"] / pe_now
        )

    computed = {
        "L": scale(inp["price"], inp["fee_drag"], s("l")),
        "M": scale(inp["price"], inp["fee_drag"], s("m")),
        "H": scale(inp["price"], inp["fee_drag"], s("h")),
    }
    if not (computed["L"] < computed["M"] < computed["H"]):
        return report(["ladder collapsed"])
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
