#!/usr/bin/env python3
"""BE.US valuation eval — recompute anchors from frameworks/BE.US.md.

frameworks/BE.US.md is the human-facing source of truth for inputs; this script
recomputes L/M/H / A/B / zone / cover and exits 1 on mismatch.

formula_id: be_fy2_eps_pe_order_gate_v1

Run:  python3 eval/BE.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "BE.US.md"
FORMULA_ID = "be_fy2_eps_pe_order_gate_v1"
TOL = 0.15  # stated outputs rounded to 1 decimal


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
        if raw in ("待补", ""):
            continue
        try:
            out[key] = float(raw.replace(",", "").replace("e", "E"))
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
        "eps_fy2",
        "pe_l",
        "pe_m",
        "pe_h",
        "rpo_product_install",
        "customer_deposits",
        "revenue_next_12m",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    if inp["pe_h"] > 30 + 1e-9:
        print(f"FAIL: pe_h={inp['pe_h']} exceeds hard cap 30", file=sys.stderr)
        return 1

    L = inp["eps_fy2"] * inp["pe_l"]
    M = inp["eps_fy2"] * inp["pe_m"]
    H = inp["eps_fy2"] * inp["pe_h"]
    A = (L + M) / 2
    B = (M + H) / 2
    cover = (inp["rpo_product_install"] + inp["customer_deposits"]) / inp["revenue_next_12m"]
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", md),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", md),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", md),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", md) or first_float(r"\\?A = ([0-9.]+)", md),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", md) or first_float(r"\\?B = ([0-9.]+)", md),
    }
    # Outputs block uses "A = **165.5**" style with LaTeX A sometimes
    if stated["A"] is None:
        stated["A"] = first_float(r"A = \*\*([0-9.]+)\*\*", md)
    if stated["B"] is None:
        stated["B"] = first_float(r"B = \*\*([0-9.]+)\*\*", md)

    # Prefer the Outputs section anchors (first L/M/H after Outputs)
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated["L"] = first_float(r"L = \*\*([0-9.]+)\*\*", out_sec) or stated["L"]
    stated["M"] = first_float(r"M = \*\*([0-9.]+)\*\*", out_sec) or stated["M"]
    stated["H"] = first_float(r"H = \*\*([0-9.]+)\*\*", out_sec) or stated["H"]
    stated["A"] = first_float(r"A = \*\*([0-9.]+)\*\*", out_sec) or stated["A"]
    stated["B"] = first_float(r"B = \*\*([0-9.]+)\*\*", out_sec) or stated["B"]

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

    cover_stated = first_float(r"cover \| ([0-9.]+)", md) or inp.get("cover")
    if cover_stated is not None and abs(cover_stated - cover) > 0.01:
        errors.append(f"cover: stated {cover_stated} vs recomputed {cover:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print(f"eps_fy2={inp['eps_fy2']} pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"cover={cover:.4f} price={inp['price']} zone={zone}")

    # Gate watch (framework §3 G2): non-failing — trigger needs 2 consecutive quarters
    conc = inp.get("conc_q2_max")
    if conc is not None and conc > 0.40:
        print(f"WARN[G2-watch]: conc_q2_max={conc:.2f} > 0.40 quarterly threshold")

    if errors:
        print("FAIL:", file=sys.stderr)
        for e in errors:
            print(" ", e, file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
