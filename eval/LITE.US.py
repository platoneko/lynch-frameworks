#!/usr/bin/env python3
"""LITE.US (Lumentum) valuation eval — recompute anchors from frameworks/LITE.US.md.

frameworks/LITE.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: lite_cycle_normalized_nongaap_eps_pe_v1

Main ruler: consensus FY2027 company-non-GAAP diluted EPS, haircut by after-tax
stock-based compensation, scaled by one of three named cycle-state factors
(digestion / consensus-as-center / in-rack optics delivered), then multiplied by
a cycle PE band whose rungs move in the same direction as the scenario growth —
so growth is priced once, in the numerator, never twice.

Run:  python3 eval/LITE.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "LITE.US.md"
FORMULA_ID = "lite_cycle_normalized_nongaap_eps_pe_v1"
TOL = 0.05  # outputs are rounded to 2 decimals

# Sell-side anchors the framework deliberately refuses to adopt (A5/A9).
# Kept as an upper guard so a later edit cannot quietly slide the band onto them.
PE_STREET = 35.0
SBC_HAIRCUT_MAX = 0.5


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | meaning | as-of |."""
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
        if key in ("字段名", "--------", "---") or raw == "取值":
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


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def check_inputs(inp: dict[str, float]) -> list[str]:
    """Ticker-specific sanity gates — see §3 step 4 and A1/A5."""
    errors: list[str] = []
    if not (0.0 <= inp["sbc_haircut"] < SBC_HAIRCUT_MAX):
        errors.append(f"sbc_haircut={inp['sbc_haircut']} outside [0, {SBC_HAIRCUT_MAX})")
    if not (inp["pe_l"] < inp["pe_m"] < inp["pe_h"]):
        errors.append(f"pe order violated: {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}")
    if not (inp["k_l"] < inp["k_m"] < inp["k_h"]):
        errors.append(f"k order violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    if inp["pe_h"] >= PE_STREET:
        errors.append(f"pe_h={inp['pe_h']} reached the sell-side {PE_STREET}x the framework rejects (A9)")
    if inp["k_m"] != 1.0:
        errors.append(f"k_m={inp['k_m']} must stay 1.0 — the mid rung is the consensus year by definition")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "price",
        "eps_fy27",
        "sbc_haircut",
        "k_l",
        "k_m",
        "k_h",
        "pe_l",
        "pe_m",
        "pe_h",
        "shares_dil",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    errors = check_inputs(inp)

    # Step 1-3: normalized non-GAAP EPS per cycle state, then the cycle PE band.
    eps_adj = inp["eps_fy27"] * (1.0 - inp["sbc_haircut"])
    eps_l = eps_adj * inp["k_l"]
    eps_m = eps_adj * inp["k_m"]
    eps_h = eps_adj * inp["k_h"]

    L = eps_l * inp["pe_l"]
    M = eps_m * inp["pe_m"]
    H = eps_h * inp["pe_h"]
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
    for k, v in recomputed.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found in Outputs")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    mcap = lambda v: v * inp["shares_dil"] / 1000.0  # noqa: E731 — 十亿 USD
    print(f"formula_id={FORMULA_ID}")
    print(
        f"eps_fy27={inp['eps_fy27']} sbc_haircut={inp['sbc_haircut']:.0%}"
        f" -> eps_adj={eps_adj:.4f}"
    )
    print(f"k={inp['k_l']}/{inp['k_m']}/{inp['k_h']}  EPS={eps_l:.2f}/{eps_m:.2f}/{eps_h:.2f}")
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} (street-equivalent on unadjusted EPS: "
          f"{inp['pe_l'] * (1 - inp['sbc_haircut']):.1f}/{inp['pe_m'] * (1 - inp['sbc_haircut']):.1f}/"
          f"{inp['pe_h'] * (1 - inp['sbc_haircut']):.1f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"implied mcap (bn USD) L/M/H = {mcap(L):.1f}/{mcap(M):.1f}/{mcap(H):.1f}"
          f"  price={mcap(inp['price']):.1f}")
    print(f"price={inp['price']} -> fwd PE on consensus {inp['price'] / inp['eps_fy27']:.1f}x,"
          f" on eps_adj {inp['price'] / eps_adj:.1f}x, zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
