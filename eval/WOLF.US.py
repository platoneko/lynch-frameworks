#!/usr/bin/env python3
"""WOLF.US (Wolfspeed) valuation eval — recompute anchors from frameworks/WOLF.US.md.

frameworks/WOLF.US.md is the source of truth; this script recomputes
L/M/H / A/B / zone and exits 1 on mismatch.

formula_id: wolf_revrecovery_evs_fd_v1

Main ruler: revenue-recovery scenario x EV/Sales, less net debt, divided by
FULLY DILUTED shares. Post-Chapter-11 the three converts are deep in the money,
so basic share count understates the equity base by ~2.3x — using it is the
single largest error available on this name (see A1).

Deliberately NO asset floor on L: equity sits behind $1.78bn of debt and book
value is already a fresh-start fair value, so L may approach zero (see A8).

Run:  python3 eval/WOLF.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "WOLF.US.md"
FORMULA_ID = "wolf_revrecovery_evs_fd_v1"
TOL = 0.05  # outputs rounded to 2 decimals
EVS_HARD_CAP = 3.9  # court-approved fresh-start anchor; see A3
MM = 1e6  # inputs are in $M


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
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, raw = cells[0], cells[1]
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
            continue  # header / separator row
        raw = raw.replace(",", "")
        m = re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", raw)
        if m:
            out[name] = float(raw)
    return out


def parse_stated(md: str) -> dict[str, float]:
    """Pull the stated L/M/H and A/B out of §3 Outputs."""
    out: dict[str, float] = {}
    m = re.search(r"- L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", md)
    if m:
        out["L"], out["M"], out["H"] = (float(g) for g in m.groups())
    m = re.search(r"- A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", md)
    if m:
        out["A"], out["B"] = (float(g) for g in m.groups())
    m = re.search(r"- zone = \*\*`(\w+)`\*\*", md)
    if m:
        out["zone"] = m.group(1)  # type: ignore[assignment]
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A, B = (L + M) / 2, (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")

    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} not found in framework", file=sys.stderr)
        return 1

    i = parse_inputs(md)
    required = [
        "price", "shares_fd", "cash", "debt",
        "rev_l", "rev_m", "rev_h", "evs_l", "evs_m", "evs_h",
    ]
    missing = [k for k in required if k not in i]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    for k in ("evs_l", "evs_m", "evs_h"):
        if i[k] > EVS_HARD_CAP + 1e-9:
            print(f"FAIL: {k}={i[k]} exceeds court fresh-start anchor {EVS_HARD_CAP}", file=sys.stderr)
            return 1

    # A1 counts converted shares, so A4 must exclude the debt those shares
    # replace. Deducting full principal alongside shares_fd double-counts it.
    if "debt_total" in i and i["debt"] >= i["debt_total"] - 1e-9:
        print(
            f"FAIL: debt={i['debt']} is the full principal ({i['debt_total']}); "
            "shares_fd already prices the converts, so debt must be the "
            "non-convertible balance only (see A1/A4)",
            file=sys.stderr,
        )
        return 1

    net_debt = i["debt"] - i["cash"]
    ev = {k: i[f"rev_{k}"] * i[f"evs_{k}"] for k in ("l", "m", "h")}
    eq = {k: v - net_debt for k, v in ev.items()}
    val = {k: v * MM / i["shares_fd"] for k, v in eq.items()}

    L, M, H = val["l"], val["m"], val["h"]
    if not (L < M < H):
        print(f"FAIL: need L<M<H, got {L:.2f}/{M:.2f}/{H:.2f}", file=sys.stderr)
        return 1

    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(i["price"], L, M, H)

    print(f"formula_id={FORMULA_ID}")
    print(f"EV($M)={ev['l']:.1f}/{ev['m']:.1f}/{ev['h']:.1f}  net_debt={net_debt:.1f}")
    print(f"Eq($M)={eq['l']:.1f}/{eq['m']:.1f}/{eq['h']:.1f}")
    print(f"evs={i['evs_l']}/{i['evs_m']}/{i['evs_h']}  shares_fd={i['shares_fd']:.0f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={i['price']} zone={zone}")

    stated = parse_stated(md)
    bad = []
    for key, got in (("L", L), ("M", M), ("H", H), ("A", A), ("B", B)):
        if key in stated and abs(stated[key] - got) > TOL:
            bad.append(f"{key}: stated {stated[key]} vs computed {got:.2f}")
    if "zone" in stated and stated["zone"] != zone:
        bad.append(f"zone: stated {stated['zone']} vs computed {zone}")

    if bad:
        print("MISMATCH:", "; ".join(bad), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
