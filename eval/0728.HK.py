#!/usr/bin/env python3
"""0728.HK (China Telecom) valuation eval.

frameworks/0728.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: ct_hk_gordon_peak_flat_v1

Main ruler: whole-company Gordon PE on the H share.  The company sits in
basket 2 (管制公用, A16) at r = 7.5%, fixed across markets: the A-share
cross band uses the same basket value.  The currency-segment reading
(CNY r_f 1.5pp lower → 6.0%) is not a basket value and is printed as a
disclosure only (A4).  Policy payout 75% is below the 80% near-full threshold, so the name is on
the retention branch: g2 = (1 - payout_policy) x ROE_M = 1.73% shared by
all tiers, and the multiple is the full form (1 - g2/ROE_x)/(r - g2).
ROE_x = FY27E EPS / BPS at the OPENING of 2027 (= end-2026, E_{n+1}/B_n):
the H1'26 book rolled over the 2H26 earnings not yet booked (FY2026E
consensus minus 1H26 actual) at the growth-required retention b1 = g2/ROE
(valuation-rules 裁决表 ② as of 62c72a2, 2026-09-21; A17).  g2 itself is
(1 - payout) x ROE_M, so the M tier's b1 is exactly 1 - payout and the
joint fixed point (ROE_M, BPS_M, g2) is closed-form: BPS_M = BPS0 +
(1 - payout) N, ROE_M = EPS_M / BPS_M, g2 = (1 - payout) ROE_M; L / H
then roll at that shared g2, BPS_x = BPS0 / (1 - g2 N / EPS_x).
Anchors are pre-tax fair value: the southbound dividend tax is the
holder's, not the asset's, and never enters the multiple (A3 / A14).
Numerators are FY2027E consensus
EPS low/mid/high in CNY; anchors are CNY value / fx_hkdcny.

Full-sample own PE band [9.27, 16.08] is the guardrail (A2).  The book
floor (BPS in HKD) is disclosed only, never max()-ed into L.
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
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs,
    report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "0728.HK.md"
FORMULA_ID = "ct_hk_gordon_peak_flat_v1"
TIERS = ("l", "m", "h")
YI = 1e8
R_LEGS = ("r_perp", "r_perp_a")

REQUIRED = [
    "price", "price_a", "shares", "bps", "equity", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h",
    "r_perp", "r_perp_a", "cny_rf_gap", "payout_policy", "payout_obs",
    "eps26_m", "ni_1h26", "payout_3y",
    "g2_l", "g2_m", "g2_h",
    "g_evid_min", "g_evid_max",
    "pe_own_min", "pe_own_max",
    "net_cash", "v_opt",
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
    r_a = inp["r_perp_a"]
    fx = inp["fx_hkdcny"]
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    g2 = {t: inp[f"g2_{t}"] for t in TIERS}
    payout_policy = inp["payout_policy"]
    payout_obs = inp["payout_obs"]
    payout_3y = inp["payout_3y"]

    # Each r leg must name its basket and carry that basket's value (A4 / A16).
    baskets = parse_baskets(md)
    for leg in R_LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in Inputs source cell")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    for t in TIERS:
        errors += check_g_cap(g2[t], r, f"g2_{t}")
        errors += check_g_cap(g2[t], r_a, f"g2_{t}@r_perp_a")
    if abs(g2["l"] - g2["m"]) > 1e-12 or abs(g2["h"] - g2["m"]) > 1e-12:
        errors.append("g2 tiers must be identical (policy-derived, shared)")
    if payout_policy + 1e-12 < payout_obs and g2["m"] <= 0:
        errors.append(
            f"payout_policy {payout_policy:.0%} < {payout_obs:.0%} threshold is the "
            "retention branch; g2 must be > 0 (A3)"
        )
    if errors:
        return report(errors, "FAIL (inputs)")

    # ROE = E_{n+1} / B_n: FY27E EPS over the OPENING-2027 book (= end-2026),
    # not the H1'26 book and not the end-2027 book (valuation-rules 裁决表 ②
    # as of 62c72a2, 2026-09-21; A17).  The H1'26 book is rolled over the 2H26
    # earnings not yet booked at the GROWTH-REQUIRED retention b1 = g2/ROE, never
    # at the actual payout complement.  Because g2 = (1 - payout) x ROE_M, the M
    # tier's b1 is exactly 1 - payout, so the joint fixed point (ROE_M, BPS_M,
    # g2) is closed-form; L / H then roll at that shared g2 with
    # BPS_x = BPS0 / (1 - g2 N / EPS_x).  FY2027's own retention is NOT rolled.
    bps0 = inp["equity"] * YI / inp["shares"]
    n_unbooked = inp["eps26_m"] - inp["ni_1h26"] * YI / inp["shares"]  # CNY/share, 2H26 only
    if n_unbooked <= 0:
        return report([f"2H26 unbooked EPS {n_unbooked:.4f} <= 0: roll is a no-op, check eps26_m / ni_1h26"])
    bps_open = {"m": bps0 + (1.0 - payout_policy) * n_unbooked}
    roe = {"m": eps["m"] / bps_open["m"]}
    g2_policy = (1.0 - payout_policy) * roe["m"]
    for t in ("l", "h"):
        bps_open[t] = bps0 / (1.0 - g2_policy * n_unbooked / eps[t])
        roe[t] = eps[t] / bps_open[t]
    b1 = {t: g2_policy / roe[t] for t in TIERS}
    roe_old = {t: eps[t] / bps0 for t in TIERS}  # H1'26 book as denominator (superseded basis)
    excess_cash = {t: ((1.0 - payout_3y) - b1[t]) * n_unbooked for t in TIERS}  # B bucket, disclosure only
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"ROE basis {t}: b1 = g2/ROE = {b1[t]:.3f} outside (0,1) — roll diverges")
    # g2 is pinned by policy: (1 - payout_policy) x ROE_M, to input rounding.
    if abs(g2_policy - g2["m"]) > 0.0005:
        errors.append(f"g2_m {g2['m']:.4f} != (1 - payout_policy) x ROE_M = {g2_policy:.4f}")
    for t in TIERS:
        errors += check_branch(g2[t], roe[t], r, payout_policy, f"tier_{t}")
    if errors:
        return report(errors, "FAIL (branch)")

    # Pre-tax fair value: no holder-tax haircut on the multiple (A14).
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

    # Evidence interval = payout policy 80% / 70% (A13).
    for g_ev in (inp["g_evid_min"], inp["g_evid_max"]):
        a_ev = {t: eps[t] * perpetual_pe(g_ev, roe[t], r) / fx for t in TIERS}
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
    dec = decompose(anc_t, pe_t)

    # A-share cross band at the same basket r, same multiple (A4 / A9).
    pe_a = {t: perpetual_pe(g2[t], roe[t], r_a) for t in TIERS}
    band_a = {t: eps[t] * pe_a[t] for t in TIERS}
    zone_a = zone_of(inp["price_a"], band_a["l"], band_a["m"], band_a["h"])
    # Currency-segment reading (r_f gap HKD → CNY) -- disclosure, not an anchor.
    r_ccy = r_a - inp["cny_rf_gap"]
    band_ccy = {t: eps[t] * perpetual_pe(g2[t], roe[t], r_ccy) for t in TIERS}
    zone_ccy = zone_of(inp["price_a"], band_ccy["l"], band_ccy["m"], band_ccy["h"])

    # Disclosure-only readings: implied r at market (full form, M tier),
    # book floor in HKD, net cash per share.
    pe_mkt = inp["price"] * fx / eps["m"]
    r_implied = g2["m"] + (1.0 - g2["m"] / roe["m"]) / pe_mkt
    pe_mkt_a = inp["price_a"] / eps["m"]
    r_implied_a = g2["m"] + (1.0 - g2["m"] / roe["m"]) / pe_mkt_a
    floor_hkd = inp["bps"] / fx
    net_cash_ps_hkd = inp["net_cash"] * YI / inp["shares"] / fx

    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.02
    )

    print(f"formula_id={FORMULA_ID}")
    print(f"baskets={baskets} r_perp={r} r_perp_a={r_a} (pre-tax fair value, A14)")
    print(f"ROE_l/m/h={[round(roe[t], 4) for t in TIERS]} g2={g2['m']} (policy {g2_policy:.4%})")
    print(f"ROE basis: BPS_open 2027 = {[round(bps_open[t], 4) for t in TIERS]} CNY "
          f"(H1'26 book {bps0:.4f} rolled over 2H26 unbooked {n_unbooked:.4f} CNY at b1 = g2/ROE = "
          f"{[round(b1[t], 3) for t in TIERS]}; M tier b1 = 1 - payout_policy by construction); "
          f"old basis (H1'26 book) would read ROE {[round(roe_old[t], 4) for t in TIERS]}")
    print(f"B bucket: (actual retention {1 - payout_3y:.0%} − b1) × unbooked = "
          f"{[round(excess_cash[t] / fx, 4) for t in TIERS]} HKD/share modelled-as-distributed, "
          f"actually retained (disclosure only; not a leg, not in BPS)")
    print(f"PE_l/m/h={[round(pe[t], 4) for t in TIERS]}")
    print(f"L/M/H={[round(anchor[t], 4) for t in TIERS]} A={A:.4f} B={B:.4f}")
    print(f"zone={zone} price={inp['price']}")
    print(f"implied_r(P) H={r_implied:.4f} A={r_implied_a:.4f} (disclosure only)")
    print(f"floor BPS HKD={floor_hkd:.4f} (disclosure only, not max()-ed)")
    print(f"net_cash HKD/share={net_cash_ps_hkd:.4f} (disclosure only)")
    print(f"flat_multiple HKD={[round(x, 4) for x in flat_hkd]}")
    print(
        f"decompose L/M={dec['lm']:.3f} (pe {dec['pe_lm']:.3f} x num {dec['num_lm']:.3f}) | "
        f"H/M={dec['hm']:.3f} (pe {dec['pe_hm']:.3f} x num {dec['num_hm']:.3f})"
    )
    print(f"neutral_width/M={(H - L) / (2 * M):.3f}")
    print(f"H/A={inp['price'] * fx / inp['price_a']:.3f}")
    print(
        f"A-share PE={[round(pe_a[t], 2) for t in TIERS]} "
        f"band CNY={[round(band_a[t], 2) for t in TIERS]} zone_a={zone_a}"
    )
    print(
        f"A-share currency-segment r={r_ccy:.3f} band CNY="
        f"{[round(band_ccy[t], 2) for t in TIERS]} zone={zone_ccy} (disclosure only)"
    )

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
