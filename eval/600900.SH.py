#!/usr/bin/env python3
"""600900.SH (China Yangtze Power) valuation eval.

frameworks/600900.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The
framework carries no current price (AGENTS.md「现价 — 禁写契约」): this
script neither reads a price nor derives or checks a zone -- the daily
digest derives the zone from live quotes.

formula_id: cyp_gordon_retention_v1

Main ruler: whole-company Gordon PE, basket 2 (管制公用) r = 7.5%.
Numerator = FY2028E consensus EPS low / median / high (4 brokers), FY+2 so
discounted one year at r_disc (= r_perp, not a basket).  Policy payout 70%
(< 80%) puts the name on the retention branch.
  M / H: g2 = (1 - payout_policy) x ROE_M = 4.8% truncated to the basket-2
         cap 3.5% (the retain-then-inject cycle keeps compounding, A5).
  L:     g2 = (1 - payout_policy) x roe_marg_l = 30% x 6.5% (pumped-storage
         regulated capital IRR) -- the world with no further big injections (A6).
ROE_x = FY28E EPS / BPS at the OPENING of 2028 (= end-2027, E_{n+1}/B_n):
the 2026-06-30 book rolled over the unbooked 2H26 + FY27 consensus at the
growth-required retention b1 = g2 / ROE (valuation-rules 裁决表 ②, 2026-09-21).
Retention above b1 is the debt-repayment A bucket, k = 0 (A4).

Basket 2 is exempt from the leverage gate (valuation-rules「杠杆门」); the
readings and the +100bp interest line are printed as disclosure only (A7).

Run:  python3 frameworks/eval/600900.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, g_cap, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs,
    report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600900.SH.md"
FORMULA_ID = "cyp_gordon_retention_v1"
TIERS = ("l", "m", "h")
YI = 1e8

REQUIRED = [
    "shares", "bps0", "eps26_m", "eps_1h26", "eps27_m",
    "eps_l", "eps_m", "eps_h",
    "r_perp", "r_disc", "n_disc", "payout_policy", "roe_marg_l",
    "g2_l", "g2_m", "g2_h", "k_l", "k_m", "k_h",
    "pe_own_min", "pe_own_max", "pe_same_min", "pe_same_max",
    "cny_rf_gap", "dry_shock",
    "debt_fy25", "net_debt_fy25", "ebit_fy25", "ebitda_fy25", "interest_fy25", "tax_rate",
    "v_opt",
]


def roll(eps: float, g: float, bps0: float, unbooked: float) -> tuple[float, float, float]:
    """Fixed point of BPS_open = bps0 + b1 x unbooked, ROE = eps / BPS_open, b1 = g / ROE."""
    b1 = 0.0
    for _ in range(100):
        bps = bps0 + b1 * unbooked
        roe = eps / bps
        b1 = g / roe
    return bps, roe, b1


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
    payout = inp["payout_policy"]
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    g2 = {t: inp[f"g2_{t}"] for t in TIERS}
    k = {t: inp[f"k_{t}"] for t in TIERS}
    disc = (1.0 + inp["r_disc"]) ** -inp["n_disc"]

    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in Inputs source cell")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if "r_disc" in baskets:
        errors.append("r_disc is a disclosure-style drift discount and must not name a basket")
    if abs(inp["r_disc"] - r) > 1e-12:
        errors.append(f"r_disc {inp['r_disc']} must equal r_perp {r}")
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    for t in TIERS:
        errors += check_g_cap(g2[t], r, f"g2_{t}")
        if k[t] != 0:
            errors.append(f"k_{t} = {k[t]}: A bucket (debt repayment) carries k = 0 (A4)")
    if errors:
        return report(errors, "FAIL (inputs)")

    bps0 = inp["bps0"]
    unbooked = (inp["eps26_m"] - inp["eps_1h26"]) + inp["eps27_m"]  # 2H26 + FY27, CNY/share
    if unbooked <= 0:
        return report([f"unbooked EPS {unbooked:.4f} <= 0: check eps26_m / eps_1h26 / eps27_m"])

    # M / H: policy g = (1 - payout) x ROE_M, truncated to the basket cap (A5).
    _, roe_m_pol, _ = roll(eps["m"], (1.0 - payout) * 0.16, bps0, unbooked)
    for _ in range(50):  # self-consistent policy g on the opening-2028 book
        g_pol = (1.0 - payout) * roe_m_pol
        _, roe_m_pol, _ = roll(eps["m"], g_pol, bps0, unbooked)
    cap = g_cap(r)
    if g_pol <= cap:
        errors.append(f"policy g {g_pol:.4f} <= cap {cap:.4f}: cap no longer binds, g2_m must be policy g (A5)")
    for t in ("m", "h"):
        if abs(g2[t] - cap) > 1e-9:
            errors.append(f"g2_{t} {g2[t]} must be the truncated cap {cap:.4f} (A5)")
    # L: no further injections; retention earns the pumped-storage regulated IRR (A6).
    g_l = (1.0 - payout) * inp["roe_marg_l"]
    if abs(g2["l"] - g_l) > 0.0005:
        errors.append(f"g2_l {g2['l']} != (1 - payout) x roe_marg_l = {g_l:.4f} (A6)")
    if g2["l"] > g2["m"]:
        errors.append("g2_l must not exceed g2_m")

    bps, roe, b1 = {}, {}, {}
    for t in TIERS:
        bps[t], roe[t], b1[t] = roll(eps[t], g2[t], bps0, unbooked)
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"b1_{t} = {b1[t]:.3f} outside (0,1)")
        errors += check_branch(g2[t], roe[t], r, payout, f"tier_{t}")
    if errors:
        return report(errors, "FAIL (branch)")

    pe = {t: perpetual_pe(g2[t], roe[t], r) for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] - 1e-9 <= pe[t] <= inp["pe_own_max"] + 1e-9):
            errors.append(f"PE_{t} {pe[t]:.2f} outside 10y own band [{inp['pe_own_min']}, {inp['pe_own_max']}]")
    # ③ guardrail: the M multiple must sit in the same-earnings band (A12).
    if not (inp["pe_same_min"] - 1e-9 <= pe["m"] <= inp["pe_same_max"] + 1e-9):
        errors.append(f"③: PE_m {pe['m']:.2f} outside same-earnings band [{inp['pe_same_min']}, {inp['pe_same_max']}]")
    if errors:
        return report(errors, "FAIL (guardrail)")

    anchor = {t: eps[t] * pe[t] * disc * (1.0 - k[t]) for t in TIERS}
    L, M, H = anchor["l"], anchor["m"], anchor["h"]
    errors += ladder("anchor", L, M, H)
    A, B = cut_points(L, M, H)
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 (A11)")

    eps_t = tuple(eps[t] * disc for t in TIERS)
    pe_t = tuple(pe[t] for t in TIERS)
    flat_errs, flat = flat_multiple_ladder(eps_t, pe["m"])
    errors += flat_errs
    dec = decompose((L, M, H), pe_t)

    def band(gmap: dict[str, float], rr: float) -> list[float]:
        out = []
        for t in TIERS:
            g = min(gmap[t], g_cap(rr))
            _, ro, _ = roll(eps[t], g, bps0, unbooked)
            out.append(eps[t] * perpetual_pe(g, ro, rr) / (1.0 + rr) ** inp["n_disc"])
        return out

    excess = {t: (1.0 - payout - b1[t]) * eps[t] for t in TIERS}

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, tol=0.02)

    print(f"formula_id={FORMULA_ID}")
    print(f"baskets={baskets} r_perp={r} cap={cap:.4f} disc={disc:.4f} (FY28E, n={inp['n_disc']:.0f})")
    print(f"policy g (uncapped)={g_pol:.4%} -> g2_m/h={g2['m']:.4f}; g2_l={g2['l']:.4f}")
    print(f"BPS_open2028={[round(bps[t], 3) for t in TIERS]} ROE={[round(roe[t], 4) for t in TIERS]} "
          f"b1={[round(b1[t], 3) for t in TIERS]}")
    print(f"payout_gap={[tuple(round(x, 3) for x in payout_gap(g2[t], roe[t], payout)) for t in TIERS]}")
    print(f"PE_l/m/h={[round(pe[t], 2) for t in TIERS]}")
    print(f"L/M/H={[round(anchor[t], 2) for t in TIERS]} A={A:.2f} B={B:.2f}")
    print(f"A bucket excess retention/yr (k=0) CNY/share={[round(excess[t], 3) for t in TIERS]}")
    print(f"flat_multiple={[round(x, 2) for x in flat]}")
    print(f"decompose L/M={dec['lm']:.3f} (pe {dec['pe_lm']:.3f} x num {dec['num_lm']:.3f}) | "
          f"H/M={dec['hm']:.3f} (pe {dec['pe_hm']:.3f} x num {dec['num_hm']:.3f}) | (H-L)/2M={(H - L) / (2 * M):.3f}")
    for d in (-0.01, 0.01):
        print(f"g2 {d:+.0%} -> {[round(x, 2) for x in band({t: max(0.0, g2[t] + d) for t in TIERS}, r)]}")
    for dr in (-0.005, 0.005):
        print(f"r {r + dr:.3f} -> {[round(x, 2) for x in band(g2, r + dr)]}")
    print(f"g 0 (1/r) -> {[round(x, 2) for x in band({t: 0.0 for t in TIERS}, r)]}")
    print(f"basket 4 (10%) -> {[round(x, 2) for x in band(g2, 0.10)]}")
    r_ccy = r - inp["cny_rf_gap"]
    print(f"CNY segment r {r_ccy:.3f} (cap {g_cap(r_ccy):.3f}) -> "
          f"{[round(x, 2) for x in band(g2, r_ccy)]} (disclosure only)")
    dry = eps["m"] * (1.0 - inp["dry_shock"]) * pe["l"] * disc
    print(f"dry-year pressure coordinate = {dry:.2f}")
    print(f"leverage (basket 2 exempt, disclosure): net debt/EBITDA="
          f"{inp['net_debt_fy25'] / inp['ebitda_fy25']:.2f} interest/EBIT={inp['interest_fy25'] / inp['ebit_fy25']:.1%}; "
          f"+100bp -> EPS {-inp['debt_fy25'] * 0.01 * (1 - inp['tax_rate']) * YI / inp['shares']:+.3f} CNY")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
