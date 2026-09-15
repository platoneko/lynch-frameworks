"""000100.SZ — TCL科技

formula_id: tcl_sotp_display_pv_flat_pe_v1

Illustrative v1: display attrib NI ladder × flat PE + PV low-PE + distribution.
V_opt magnitude is an explicit拍值 (glass/InP); not from realized unit economics yet.
"""

from __future__ import annotations

FORMULA_ID = "tcl_sotp_display_pv_flat_pe_v1"
TICKER = "000100.SZ"

# Inputs (mirror frameworks/000100.SZ.md §3)
PRICE = 4.64
SHARES = 21_946_416_151.0
NI_DISPLAY = {"L": 3.5e9, "M": 6.0e9, "H": 7.5e9}  # CNY, parent-attributable display
NI_PV = {"L": 0.0, "M": 0.0, "H": 5.0e8}
NI_DIST = 1.0322e8 * 2  # Highly Information H1 NI ×2
PE_DISPLAY = 14.0
PE_PV = 8.0
PE_DIST = 8.0
V_OPT = 0.80
P_K = {"L": 0.0, "M": 0.25, "H": 1.0}


def leg_ps(ni: float, pe: float) -> float:
    return (ni / SHARES) * pe


def anchors() -> dict[str, float]:
    dist = leg_ps(NI_DIST, PE_DIST)
    out = {}
    for x in ("L", "M", "H"):
        out[x] = (
            leg_ps(NI_DISPLAY[x], PE_DISPLAY)
            + leg_ps(NI_PV[x], PE_PV)
            + dist
        )
    return out


def main() -> None:
    a = anchors()
    L, M, H = a["L"], a["M"], a["H"]
    assert L < M < H, (L, M, H)
    # flat-multiple molecule ladder
    assert NI_DISPLAY["L"] < NI_DISPLAY["M"] < NI_DISPLAY["H"]
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
    print(f"L/M/H = {L:.2f} / {M:.2f} / {H:.2f}")
    print(f"A/B = {A:.2f} / {B:.2f}")
    # A2e-2c / A2e-5: the display leg is flat 14x on every tier, so the flat-multiple
    # ladder is the display-leg ladder itself; the tier spread is all numerator.
    flat = {x: leg_ps(NI_DISPLAY[x], PE_DISPLAY) for x in ("L", "M", "H")}
    print(f"flat-multiple ladder (display leg @ {PE_DISPLAY:g}x): {flat['L']:.2f}/{flat['M']:.2f}/{flat['H']:.2f}")
    print(
        f"L/M={L/M:.2f} = num {NI_DISPLAY['L']/NI_DISPLAY['M']:.2f} x pe 1.00 | "
        f"H/M={H/M:.2f} = num {NI_DISPLAY['H']/NI_DISPLAY['M']:.2f} x pe 1.00 (+PV leg at H) | "
        f"width={(H-L)/(2*M):.2f} V_opt/M={V_OPT/M:.2f}"
    )
    print(f"price {PRICE} → zone {zone}")
    for x in ("L", "M", "H"):
        adj = a[x] + P_K[x] * V_OPT
        print(f"  zone+V {x}: {a[x]:.2f} + {P_K[x]}*{V_OPT} = {adj:.2f}")
    print("OK")


if __name__ == "__main__":
    main()
