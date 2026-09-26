#!/usr/bin/env python3
"""000725.SZ (BOE) valuation eval — recompute anchors from frameworks/000725.SZ.md.

formula_id: boe_midcycle_eps_flat_pe_v1

Illustrative: consolidated mid-cycle NI ladder x flat PE.  V_opt is read
from the framework and priced tier by tier in 表3 only; probabilities never
enter the base deck.

The basket r (篮 6, 13%) does not enter the flat-PE deck (B8).  It is a
disclosure-only `r_perp` row: the script checks the basket tag and value agree
(`check_r`), prints the 篮 6 peak-zone contrast band at 1/r and the PB floor
(never max()-ed into L).

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here computes a zone or a market-implied r / p — the digest and the app zone
on live quotes.

Known Class B debt (the ticker is queued for a rebuild, not patched here):
the §3 Inputs table still carries p_l / p_m / p_h rows, which A2e-7a forbids.
That is reported as a warning below rather than a failure so the anchor
recomputation stays runnable until the rebuild lands.

Run:  python3 frameworks/eval/000725.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_r, g_cap  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000725.SZ.md"
FORMULA_ID = "boe_midcycle_eps_flat_pe_v1"
REQUIRED = ["shares", "bps", "ni_l", "ni_m", "ni_h", "pe", "v_opt", "pb_floor", "r_perp"]
TIERS = ("l", "m", "h")


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # A2e-7a: probabilities belong in 表3 only.  Warning, not failure — see
    # the module docstring; the Inputs cleanup is part of the Class B rebuild.
    leaked = sorted(k for k in inp if k.startswith("p_"))

    # B8: r is disclosure only (flat PE deck), but the basket tag and the value must agree.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    r = inp["r_perp"]
    errors += check_r(r, "r_perp", baskets.get("r_perp"))

    eps = {t: inp[f"ni_{t}"] / inp["shares"] for t in TIERS}
    errors += ladder("NI", inp["ni_l"], inp["ni_m"], inp["ni_h"])
    L, M, H = (eps[t] * inp["pe"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    flat_errs, flat = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), inp["pe"])
    errors += flat_errs
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None)

    floor = inp["pb_floor"] * inp["bps"]
    p = stated_p_tiers(md)
    if p is None:
        errors.append("p_L/p_M/p_H not stated in Outputs")

    print(f"formula_id={FORMULA_ID}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper()}: NI {inp[f'ni_{t}'] / 1e8:.1f}亿 eps {eps[t]:.4f} x {inp['pe']:g} = {a:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    # B6: the PB floor is disclosed, never max()-ed into L.
    print(f"floor(PB ref)={floor:.2f} (disclosure only, L stays {L:.2f})")
    # B8: 篮 6 contrast band at the peak-zone ceiling 1/r; ROE < r - 3pp on every tier.
    peak_pe = 1 / r
    roe = {t: eps[t] / inp["bps"] for t in TIERS}
    print(
        f"r_perp {r:g} (篮 {baskets.get('r_perp')}), disclosure only; g_cap={g_cap(r):.2f} (no g2 row); "
        f"1/r={peak_pe:.2f}x contrast band "
        f"{eps['l'] * peak_pe:.2f}/{eps['m'] * peak_pe:.2f}/{eps['h'] * peak_pe:.2f} "
        f"ROE {roe['l']:.1%}/{roe['m']:.1%}/{roe['h']:.1%}"
    )
    print(
        f"L/M={L / M:.2f} (分子比 {eps['l'] / eps['m']:.2f} x 倍数比 1.00) "
        f"H/M={H / M:.2f} (分子比 {eps['h'] / eps['m']:.2f}) "
        f"width={(H - L) / (2 * M):.2f} V_opt/M={inp['v_opt'] / M:.2f}"
    )
    print(f"flat-multiple ladder @ {inp['pe']:g}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    if p:
        band = tuple(a + pk * inp["v_opt"] for a, pk in zip((L, M, H), p))
        a2, b2 = cut_points(*band)
        print(
            f"zone+V: {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f} A'={a2:.2f} B'={b2:.2f}"
        )
    if leaked:
        print(f"WARN: probability fields in §3 Inputs {leaked} — A2e-7a, pending Class B rebuild")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
