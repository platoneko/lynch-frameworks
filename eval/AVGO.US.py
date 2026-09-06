#!/usr/bin/env python3
"""AVGO.US valuation eval — recompute anchors from frameworks/AVGO.US.md.

frameworks/AVGO.US.md is the source of truth for inputs; this script recomputes
L/M/H / A/B / zone and exits 1 on mismatch with stated Outputs.

formula_id: avgo_sotp_xpu2tier_net_nonai_sw_fy27_28_v3

Run:  python3 eval/AVGO.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "AVGO.US.md"
TOL = 0.15


def parse_inputs(md: str) -> dict[str, float]:
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
        if raw in ("待补", ""):
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


def eps_leg(rev: float, om: float, tax_rate: float, shares: float) -> float:
    return rev * om * (1.0 - tax_rate) / shares


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    required = [
        "price",
        "shares",
        "tax_rate",
        "rev_ai_27",
        "rev_ai_28",
        "xpu_share_ai",
        "rev_nonai_27",
        "rev_nonai_28",
        "rev_sw_27",
        "rev_sw_28",
        "below_line_ps",
        "om_xpu",
        "om_net",
        "om_nonai",
        "om_sw",
        "xpu_uw_share",
        "pe_xpu_uw_l",
        "pe_xpu_uw_m",
        "pe_xpu_lab_l",
        "pe_xpu_lab_m",
        "pe_net_l",
        "pe_net_m",
        "pe_nonai_l",
        "pe_nonai_m",
        "pe_sw_l",
        "pe_sw_m",
        "pe_h_fy28",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"missing inputs: {missing}", file=sys.stderr)
        return 1

    s, t = inp["shares"], inp["tax_rate"]
    xpu_s = inp["xpu_share_ai"]

    rev_xpu_27 = inp["rev_ai_27"] * xpu_s
    rev_net_27 = inp["rev_ai_27"] * (1.0 - xpu_s)
    rev_xpu_28 = inp["rev_ai_28"] * xpu_s
    rev_net_28 = inp["rev_ai_28"] * (1.0 - xpu_s)

    e27 = {
        "xpu": eps_leg(rev_xpu_27, inp["om_xpu"], t, s),
        "net": eps_leg(rev_net_27, inp["om_net"], t, s),
        "nonai": eps_leg(inp["rev_nonai_27"], inp["om_nonai"], t, s),
        "sw": eps_leg(inp["rev_sw_27"], inp["om_sw"], t, s),
    }
    e28 = {
        "xpu": eps_leg(rev_xpu_28, inp["om_xpu"], t, s),
        "net": eps_leg(rev_net_28, inp["om_net"], t, s),
        "nonai": eps_leg(inp["rev_nonai_28"], inp["om_nonai"], t, s),
        "sw": eps_leg(inp["rev_sw_28"], inp["om_sw"], t, s),
    }

    # below-the-line drag (A14): pro-rata across legs; preserves leg sums = gross - bl
    bl = inp["below_line_ps"]
    f27 = (sum(e27.values()) - bl) / sum(e27.values())
    f28 = (sum(e28.values()) - bl) / sum(e28.values())
    e27 = {k: v * f27 for k, v in e27.items()}
    e28 = {k: v * f28 for k, v in e28.items()}

    # XPU two-tier split (A15): underwritten (LTA) vs lab-dependent; FY27 L/M only, H stays untiered
    uw = inp["xpu_uw_share"]
    e27_uw = e27["xpu"] * uw
    e27_lab = e27["xpu"] * (1.0 - uw)

    L = (
        e27_uw * inp["pe_xpu_uw_l"]
        + e27_lab * inp["pe_xpu_lab_l"]
        + e27["net"] * inp["pe_net_l"]
        + e27["nonai"] * inp["pe_nonai_l"]
        + e27["sw"] * inp["pe_sw_l"]
    )
    M = (
        e27_uw * inp["pe_xpu_uw_m"]
        + e27_lab * inp["pe_xpu_lab_m"]
        + e27["net"] * inp["pe_net_m"]
        + e27["nonai"] * inp["pe_nonai_m"]
        + e27["sw"] * inp["pe_sw_m"]
    )
    eps28 = sum(e28.values())
    H = eps28 * inp["pe_h_fy28"]
    A = (L + M) / 2
    B = (M + H) / 2
    z = zone_of(inp["price"], L, M, H)

    stated = {}
    for key, pat in [
        ("L", r"L = \*\*([0-9.]+)\*\*"),
        ("M", r"M = \*\*([0-9.]+)\*\*"),
        ("H", r"H = \*\*([0-9.]+)\*\*"),
    ]:
        m = re.search(pat, md)
        if m:
            stated[key] = float(m.group(1))

    print(f"formula_id: avgo_sotp_xpu2tier_net_nonai_sw_fy27_28_v3")
    print(f"eps27={sum(e27.values()):.3f} eps28={eps28:.3f}")
    print(f"L={L:.1f} M={M:.1f} H={H:.1f} A={A:.1f} B={B:.1f}")
    print(f"zone={z} price={inp['price']}")
    for leg in ("xpu", "net", "nonai", "sw"):
        print(f"  {leg}: eps27={e27[leg]:.3f} eps28={e28[leg]:.3f}")
    print(f"  xpu split: uw={e27_uw:.3f} lab={e27_lab:.3f} (uw_share={uw:.2f})")

    ok = True
    for key, val in [("L", L), ("M", M), ("H", H)]:
        if key in stated and abs(val - stated[key]) > TOL:
            print(f"MISMATCH {key}: computed={val:.1f} stated={stated[key]}", file=sys.stderr)
            ok = False

    zone_m = re.search(r"zone = \*\*`([a-z_]+)`\*\*", md)
    if zone_m and zone_m.group(1) != z:
        print(f"MISMATCH zone: computed={z} stated={zone_m.group(1)}", file=sys.stderr)
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
