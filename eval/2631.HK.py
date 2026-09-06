#!/usr/bin/env python3
"""2631.HK (SICC) valuation eval — recompute anchors from frameworks/2631.HK.md.

frameworks/2631.HK.md is the source of truth; this script recomputes
L/M/H / A/B / zone and exits 1 on mismatch.

formula_id: sicc_fullcap_asp_margin_pe_disc_v2

Main ruler: full-capacity output x ASP x net margin (depreciation-dilution
bridge) x PE, discounted back from the full-capacity year; L additionally
floored at pb_floor x bps (the asset floor exists today, so it is not
discounted).

Run:  python3 eval/2631.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "2631.HK.md"
FORMULA_ID = "sicc_fullcap_asp_margin_pe_disc_v2"
TOL = 0.05  # outputs rounded to 2 decimals
PE_HARD_CAP = 28.0
KPCS = 1e4  # cap_kpcs is in 万片 (10k wafers)
YI = 1e8  # 亿, for reporting revenue / net profit


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | ... |"""
    out: dict[str, float] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, raw = cells[0], cells[1]
        if key in ("字段名", "--------", "---") or raw in ("取值",):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A = (L + M) / 2
    B = (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    if not m:
        return None
    return float(m.group(1))


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "price",
        "shares",
        "fx_cny_hkd",
        "bps",
        "cap_kpcs",
        "rev_basis_up",
        "asp_l",
        "asp_m",
        "asp_h",
        "m_l",
        "m_m",
        "m_h",
        "pe_l",
        "pe_m",
        "pe_h",
        "r_disc",
        "year_now",
        "t_fullcap",
        "pb_floor",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    if inp["pe_h"] > PE_HARD_CAP + 1e-9:
        print(f"FAIL: pe_h={inp['pe_h']} exceeds hard cap {PE_HARD_CAP}", file=sys.stderr)
        return 1
    if not (inp["pe_l"] < inp["pe_m"] < inp["pe_h"]):
        print(
            f"FAIL: pe order violated: {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}",
            file=sys.stderr,
        )
        return 1

    wafers = inp["cap_kpcs"] * KPCS  # full-capacity wafers per year

    def scenario(asp: float, margin: float, pe: float) -> tuple[float, float, float]:
        """(revenue CNY, net profit CNY, per-share value HKD at full-capacity year)."""
        rev = wafers * asp * inp["rev_basis_up"]
        np_ = rev * margin
        value_t = pe * np_ * inp["fx_cny_hkd"] / inp["shares"]
        return rev, np_, value_t

    rev_l, np_l, v_l = scenario(inp["asp_l"], inp["m_l"], inp["pe_l"])
    rev_m, np_m, v_m = scenario(inp["asp_m"], inp["m_m"], inp["pe_m"])
    rev_h, np_h, v_h = scenario(inp["asp_h"], inp["m_h"], inp["pe_h"])

    years = inp["t_fullcap"] - inp["year_now"]
    disc = (1.0 + inp["r_disc"]) ** (-years)

    floor = inp["pb_floor"] * inp["bps"]
    L = max(v_l * disc, floor)  # asset floor exists today -> not discounted
    M = v_m * disc
    H = v_h * disc
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }

    recomputed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    errors: list[str] = []
    for k, v in recomputed.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
            continue
        if abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        f"rev(亿CNY)={rev_l / YI:.2f}/{rev_m / YI:.2f}/{rev_h / YI:.2f}"
        f"  np(亿CNY)={np_l / YI:.2f}/{np_m / YI:.2f}/{np_h / YI:.2f}"
    )
    print(f"V@T={v_l:.2f}/{v_m:.2f}/{v_h:.2f}  disc={disc:.4f} ({years:.0f}y @ {inp['r_disc']:.0%})")
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}  floor(pb*bps)={floor:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
