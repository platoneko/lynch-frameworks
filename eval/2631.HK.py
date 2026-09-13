#!/usr/bin/env python3
"""2631.HK (SICC) valuation eval — asset-PB bottom + ASP-fullcap V_opt.

frameworks/2631.HK.md is the source of truth; this script recomputes
bottom L/M/H / A/B / zone / V_opt and exits 1 on mismatch.

formula_id (bottom): sicc_asset_pb_bottom_v1
formula_id (option): sicc_asp_fullcap_success_vopt_v1

Bottom = PB 0.55/0.80/1.00 × BPS (no ASP repair).
V_opt  = undiscounted full-cap success V^T_H − bottom H.
表3   = bottom_k + p_k × V_opt; P_K is an eval constant (A2e-7a).

Run:  python3 eval/2631.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    outputs_section,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "2631.HK.md"
FORMULA_IDS = (
    "sicc_asset_pb_bottom_v1",
    "sicc_asp_fullcap_success_vopt_v1",
)
PE_HARD_CAP = 28.0
KPCS = 1e4
YI = 1e8

# 表3 only — never Inputs, never the bottom card (A12).
P_K = (0.0, 0.25, 1.0)

REQUIRED = [
    "price",
    "shares",
    "fx_cny_hkd",
    "bps",
    "pb_l",
    "pb_m",
    "pb_h",
    "cap_kpcs",
    "rev_basis_up",
    "asp_h",
    "m_h",
    "pe_h",
    "r_disc",
    "year_now",
    "t_fullcap",
]


def check_no_p_leak(base_l: float, row_l: float) -> list[str]:
    if abs(row_l - base_l) > 1e-9:
        return [f"p leaked into the base: 表3 L row {row_l:.4f} != base L {base_l:.4f}"]
    return []


def stated_v_opt(md: str) -> float | None:
    sec = outputs_section(md)
    m = re.search(r"V_\{opt\}\D{0,20}\*\*([0-9.]+)\*\*", sec)
    return float(m.group(1)) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    errors: list[str] = []
    for fid in FORMULA_IDS:
        if fid not in md:
            errors.append(f"formula_id {fid} missing from framework")

    inp = parse_inputs(md)
    errors += check_missing(inp, REQUIRED)
    if errors and any(e.startswith("missing") or "formula_id" in e for e in errors):
        return report(errors)

    if inp["pe_h"] > PE_HARD_CAP + 1e-9:
        errors.append(f"pe_h={inp['pe_h']} exceeds hard cap {PE_HARD_CAP}")
    if not (inp["pb_l"] < inp["pb_m"] < inp["pb_h"]):
        errors.append(
            f"pb order violated: {inp['pb_l']}/{inp['pb_m']}/{inp['pb_h']}"
        )

    L = inp["pb_l"] * inp["bps"]
    M = inp["pb_m"] * inp["bps"]
    H = inp["pb_h"] * inp["bps"]
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    wafers = inp["cap_kpcs"] * KPCS
    rev_h = wafers * inp["asp_h"] * inp["rev_basis_up"]
    np_h = rev_h * inp["m_h"]
    v_t_h = inp["pe_h"] * np_h * inp["fx_cny_hkd"] / inp["shares"]
    v_opt = v_t_h - H

    years = inp["t_fullcap"] - inp["year_now"]
    disc = (1.0 + inp["r_disc"]) ** (-years)
    v_t_h_disc = v_t_h * disc
    v_opt_disc = v_t_h_disc - H

    base = (L, M, H)
    adj_band = [base[i] + P_K[i] * v_opt for i in range(3)]
    p_implied = (inp["price"] - H) / v_opt if v_opt > 0 else float("nan")

    print(f"formula_id: {FORMULA_IDS[0]} + {FORMULA_IDS[1]}")
    print(
        f"bottom     PB={inp['pb_l']:g}/{inp['pb_m']:g}/{inp['pb_h']:g}"
        f" × bps {inp['bps']:.2f}"
    )
    print(
        f"success    rev={rev_h / YI:.2f}亿 np={np_h / YI:.2f}亿"
        f"  V^T_H={v_t_h:.2f} (undisc)  disc_cross={v_t_h_disc:.2f}"
    )
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(
        f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
        f" V_opt/M={v_opt / M:.1%}"
    )
    print(f"表2  price {inp['price']} -> zone = {zone}")
    print(
        f"表3  V_opt={v_opt:.2f}  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}  "
        + "  ".join(
            f"{n}:{base[i]:.2f}+{P_K[i]:.2f}xV={adj_band[i]:.2f}"
            for i, n in enumerate("LMH")
        )
    )
    print(f"     市价隐含 p = {p_implied:.2f}  V_opt_disc_cross={v_opt_disc:.2f}")

    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.05
    )
    errors += ladder("base", L, M, H)
    errors += check_no_p_leak(L, adj_band[0])
    if not P_K[0] <= P_K[1] <= P_K[2]:
        errors.append(f"p_k must be non-decreasing, got {P_K}")
    if v_opt <= 0:
        errors.append(f"V_opt must be > 0, got {v_opt:.2f}")
    said_v = stated_v_opt(md)
    if said_v is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(said_v - v_opt) > 0.05:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
