#!/usr/bin/env python3
"""159263.SZ (E Fund CNI Value 100 ETF) valuation eval.

formula_id: efund_cni_value100_sotp_lookthrough_v1

Snapshot SOTP: white-goods Gordon + CMB look-through + other banks frozen
at market + Yuntianhua/Chalco look-through + residual Gordon.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf_lookthrough import scale  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_inputs, report  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "159263.SZ.md"
FORMULA_ID = "efund_cni_value100_sotp_lookthrough_v1"

REQUIRED = [
    "price", "fee_drag",
    "w_white", "pe_white_now", "pe_white_l", "pe_white_m", "pe_white_h",
    "eps_white_l", "eps_white_m", "eps_white_h",
    "w_cmb", "p_cmb", "cmb_l", "cmb_m", "cmb_h",
    "w_obank",
    "w_yth", "p_yth", "yth_l", "yth_m", "yth_h",
    "w_alc", "p_alc", "alc_l", "alc_m", "alc_h",
    "w_res", "pe_res_now", "pe_res_l", "pe_res_m", "pe_res_h",
    "eps_res_l", "eps_res_m", "eps_res_h",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    wsum = (
        inp.get("w_white", 0) + inp.get("w_cmb", 0) + inp.get("w_obank", 0)
        + inp.get("w_yth", 0) + inp.get("w_alc", 0) + inp.get("w_res", 0)
    )
    if abs(wsum - 1.0) > 0.002:
        errors.append(f"weights sum {wsum:.4f} != 1")
    if errors:
        return report(errors)

    def s(tag: str) -> float:
        white = (
            inp["w_white"] * inp[f"eps_white_{tag}"]
            * inp[f"pe_white_{tag}"] / inp["pe_white_now"]
        )
        cmb = inp["w_cmb"] * inp[f"cmb_{tag}"] / inp["p_cmb"]
        obank = inp["w_obank"] * 1.0
        yth = inp["w_yth"] * inp[f"yth_{tag}"] / inp["p_yth"]
        alc = inp["w_alc"] * inp[f"alc_{tag}"] / inp["p_alc"]
        res = (
            inp["w_res"] * inp[f"eps_res_{tag}"]
            * inp[f"pe_res_{tag}"] / inp["pe_res_now"]
        )
        return white + cmb + obank + yth + alc + res

    computed = {t: scale(inp["price"], inp["fee_drag"], s(t.lower())) for t in "LMH"}
    # s() uses l/m/h keys
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
