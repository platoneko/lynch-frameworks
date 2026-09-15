#!/usr/bin/env python3
"""0728.HK (China Telecom) valuation eval.

frameworks/0728.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: ct_hk_gordon_peak_flat_v1

Main ruler: whole-company Gordon PE on the H share.  Peak-region ROE
(book ~6-9% < r=10%) plus near-full payout (payout_obs pinned at 80%)
puts the name on the full-payout branch with g2 = 0 → PE = 10x flat
(= 1/r).  Numerators are FY2027E consensus EPS low/mid/high in CNY;
anchors are CNY value / fx_hkdcny (company interim dividend conversion).

Why not DDM: a dividend-growth g_d that reproduces the ~12x market tape
(~3.8%) flips zone across ±1pp, so DDM stays a cross-check only (A11).
Why full-sample PE guardrail: the 3y band floor 11.27 sits above the
Gordon ceiling 10x and would BLOCK every legal g; the full-sample floor
9.27 lets 10x in (A2).

Cloud / AIDC has revenue but no segment EBIT → V_opt = 0 (A6).
Southbound axis is NOT mounted for multiples (A9); A/H is dual-reported.

Run:  python3 eval/0728.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "0728.HK.md"
FORMULA_ID = "ct_hk_gordon_peak_flat_v1"
TIERS = ("l", "m", "h")
YI = 1e8
NEAR_FULL = 0.80

REQUIRED = [
    "price", "price_a", "shares", "bps", "equity", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h",
    "r_perp", "payout_obs",
    "g2_l", "g2_m", "g2_h",
    "g_evid_min", "g_evid_max",
    "pe_own_min", "pe_own_max",
    "v_opt",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = inp["r_perp"]
    fx = inp["fx_hkdcny"]
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    g2 = {t: inp[f"g2_{t}"] for t in TIERS}
    payout_obs = inp["payout_obs"]

    errors += check_r(r, "r_perp")
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    for t in TIERS:
        errors += check_g_cap(g2[t], f"g2_{t}")
    if abs(g2["l"] - g2["m"]) > 1e-12 or abs(g2["h"] - g2["m"]) > 1e-12:
        errors.append("g2 tiers must be identical (peak-ceiling flat)")
    if payout_obs + 1e-12 < NEAR_FULL and g2["m"] <= 0:
        errors.append(
            f"payout_obs {payout_obs:.0%} < {NEAR_FULL:.0%} cannot pin g2=0 "
            "(full-payout branch)"
        )
    if errors:
        return report(errors, "FAIL (inputs)")

    roe = {t: eps[t] * inp["shares"] / (inp["equity"] * YI) for t in TIERS}
    for t in TIERS:
        errors += check_branch(g2[t], roe[t], r, payout_obs, f"tier_{t}")
    if errors:
        return report(errors, "FAIL (branch)")

    pe = {t: perpetual_pe(g2[t], roe[t], r) for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] - 1e-9 <= pe[t] <= inp["pe_own_max"] + 1e-9):
            errors.append(
                f"PE_{t} {pe[t]:.2f} outside own band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}]"
            )
    if errors:
        return report(errors, "FAIL (guardrail)")

    anchor = {t: eps[t] * pe[t] / fx for t in TIERS}
    L, M, H = anchor["l"], anchor["m"], anchor["h"]
    errors += ladder("anchor", L, M, H)
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # Evidence interval (degenerate {0} for structural g2=0) must keep zone.
    for g_ev in (inp["g_evid_min"], inp["g_evid_max"]):
        pe_ev = {t: perpetual_pe(g_ev, roe[t], r) for t in TIERS}
        a_ev = {t: eps[t] * pe_ev[t] / fx for t in TIERS}
        z_ev = zone_of(inp["price"], a_ev["l"], a_ev["m"], a_ev["h"])
        if z_ev != zone:
            errors.append(
                f"zone flips at g_evid={g_ev}: {zone} → {z_ev} "
                "(valuation-rules「g2 的杠杆」)"
            )

    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 until cloud contribution profit is sourced")

    eps_t = (eps["l"], eps["m"], eps["h"])
    pe_t = (pe["l"], pe["m"], pe["h"])
    anc_t = (L, M, H)
    flat_errs, flat_cny = flat_multiple_ladder(eps_t, pe["m"])
    errors += flat_errs
    flat_hkd = tuple(v / fx for v in flat_cny)
    if abs(flat_hkd[0] - L) > 0.02 or abs(flat_hkd[2] - H) > 0.02:
        errors.append(
            f"flat-multiple HKD {flat_hkd[0]:.2f}/{flat_hkd[1]:.2f}/{flat_hkd[2]:.2f} "
            f"diverges from main band (expected flat at g2=0)"
        )
    dec = decompose(anc_t, pe_t)

    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.02
    )

    print(f"formula_id={FORMULA_ID}")
    print(f"ROE_l/m/h={[round(roe[t], 4) for t in TIERS]}")
    print(f"PE_l/m/h={[round(pe[t], 4) for t in TIERS]}")
    print(f"L/M/H={[round(anchor[t], 4) for t in TIERS]} A={A:.4f} B={B:.4f}")
    print(f"zone={zone} price={inp['price']}")
    print(f"flat_multiple HKD={[round(x, 4) for x in flat_hkd]}")
    print(
        f"decompose L/M={dec['lm']:.3f} (pe {dec['pe_lm']:.3f} x num {dec['num_lm']:.3f}) | "
        f"H/M={dec['hm']:.3f} (pe {dec['pe_hm']:.3f} x num {dec['num_hm']:.3f})"
    )
    print(f"neutral_width/M={(H - L) / (2 * M):.3f}")
    print(f"H/A={inp['price'] * fx / inp['price_a']:.3f}")
    print(f"A-share band CNY={[round(eps[t] * pe[t], 2) for t in TIERS]}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
