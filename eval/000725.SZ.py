"""000725.SZ — 京东方A

formula_id: boe_midcycle_eps_flat_pe_v1

Illustrative v1: consolidated mid-cycle EPS ladder × flat PE.
V_opt is an explicit拍值 from narrative-PB gap (glass substrate); not realized unit NI.
"""

from __future__ import annotations

FORMULA_ID = "boe_midcycle_eps_flat_pe_v1"
TICKER = "000725.SZ"

PRICE = 5.33
SHARES = 37_044_328_064.0
# L = FY2023 parent NI; M = Citi 2026E NI 75.6亿; H = 2026H1 parent ×2
NI = {"L": 2.55e9, "M": 7.56e9, "H": 5.248e9 * 2}
PE = 14.0
V_OPT = 4.00
P_K = {"L": 0.0, "M": 0.25, "H": 1.0}
BPS = 3.594
PB_FLOOR = 0.70  # deep_discount reference only; does not replace scenario L


def anchors() -> dict[str, float]:
    return {x: (NI[x] / SHARES) * PE for x in ("L", "M", "H")}


def main() -> None:
    a = anchors()
    L, M, H = a["L"], a["M"], a["H"]
    assert L < M < H, (L, M, H)
    assert NI["L"] < NI["M"] < NI["H"]
    floor = PB_FLOOR * BPS
    A = (L + M) / 2
    B = (M + H) / 2
    zone = (
        "deep_discount"
        if PRICE < L
        else "conservative"
        if PRICE < A
        else "neutral"
        if PRICE < B
        else "optimistic"
        if PRICE <= H
        else "stretched"
    )
    print(f"{TICKER} {FORMULA_ID}")
    print(f"L/M/H = {L:.2f} / {M:.2f} / {H:.2f}  (scenario; floor PB ref={floor:.2f})")
    print(f"A/B = {A:.2f} / {B:.2f}")
    print(
        f"L/M={L/M:.2f} (mol={NI['L']/NI['M']:.2f}×pe=1.00) "
        f"H/M={H/M:.2f} (mol={NI['H']/NI['M']:.2f}) "
        f"width={(H-L)/(2*M):.2f} V_opt/M={V_OPT/M:.2f}"
    )
    print(f"price {PRICE} → zone {zone}")
    if PRICE > H:
        print(f"  implied p vs V_opt = {(PRICE - H) / V_OPT:.2f}")
    for x in ("L", "M", "H"):
        adj = a[x] + P_K[x] * V_OPT
        print(f"  zone+V {x}: {a[x]:.2f} + {P_K[x]}*{V_OPT} = {adj:.2f}")


if __name__ == "__main__":
    main()
