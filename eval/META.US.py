#!/usr/bin/env python3
"""META.US (Meta Platforms) valuation eval — recompute anchors from frameworks/META.US.md.

frameworks/META.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on any mismatch.

formula_id: meta_fwd_numerator_gordon_foa_rl_icpath_v1

Main ruler: two legs summed per tier k in {L, M, H} (one estimation date, FY2027 = t=1).

  FoA leg   NOPAT_k = eps_k + rl_loss_k(1-tax)/shares + interest(1-tax)/shares
            ROIC_k  = NOPAT_k * shares / ic_fy27        (invested-capital PATH, not equity)
            PE_k    = perpetual_pe(g2, ROIC_k, r_foa)  (Gordon, generated not borrowed)
  RL leg    -rl_loss_k(1-tax) / (shares * r_rl)        (loss capitalised, g = 0)
  closing   -(net_debt + settlement_npv) / shares
  V_k       = NOPAT_k * PE_k + RL_k + closing

The numerator is the FY2027E GAAP consensus at its low / mean / high (A3); the
tiers differ ONLY in that layer plus the RL loss path (A7).  The multiple is
told apart by tier ROIC, whose denominator is the FY27 invested-capital path
$425B (A6): capex is half debt-funded, so equity alone cannot see it.

r is not a per-ticker dial: every `r*` Inputs row names its basket (`篮 N`) and
the value must equal gordon.BASKET_R for that basket.  Both legs sit in basket 4
龙头制造 (10%, A2) -- the RL loss stream is paid out of group cash flow, and a
higher r on a negative stream would systematically raise the value.
`check_r(r, where, basket)` enforces the match; `check_g_cap(g2, r_foa, "g2")`
caps the perpetual g at g_cap(r) = min(6%, r - 4%).

Sanity checks beyond the anchor comparison:
  * numerator ladder NOPAT_L < NOPAT_M < NOPAT_H and the loss path
    rl_loss_l >= rl_loss_m >= rl_loss_h (L is the wider-loss world)
  * flat-multiple ladder: with every tier on the M multiple the band still orders
  * Gordon branch (check_branch on the observed dividend + buyback payout) and
    payout_gap printed as a disclosure
  * guardrail ③: M / reported TTM EPS inside the own 5-year band
    [pe_own_min, pe_own_max]; H / clean TTM EPS at or below the band top
  * implied r(P): |delta| <= 3pp (A13), printed with implied g2 and implied IC
  * constituent mount on _AXIS.ai-capex (share of the 2026 base is sane)
  * no p-class fields in Inputs; L < M < H; stated anchors / cut points / zone

Disclosures printed for the A2f record (never fed back into the anchors):
  r_f band and reverse-pressure row (rf_hub / rf_step / rf_cap), g2 +-1pp with
  the zone each lands in (the sensitivity zone), IC frozen / x1.58, RL = 0,
  contingent settlement 30%, tax 21%.

Run:  python3 eval/META.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import capex_constituent_share, check_capex_constituent  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    g_cap,
    payout_gap,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "META.US.md"
FORMULA_ID = "meta_fwd_numerator_gordon_foa_rl_icpath_v1"
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
IMPLIED_R_TOL = 0.03  # A13: |delta| above this triggers the basket review
# Observed payout for check_branch: dividend ~6% + buybacks ~55% of earnings
# (framework §3 step 3).  With ROIC >= r + 3pp the branch test is sign-only.
PAYOUT_OBSERVED = 0.61
# Contingent 30% of the state settlement (A8), pressure row only.
SETTLEMENT_CONTINGENT_B = 5.3
IC_STRESS_MULT = 1.58  # A9 upper IC stress

REQUIRED = [
    "price",
    "shares",
    "eps_l",
    "eps_m",
    "eps_h",
    "rl_loss_l",
    "rl_loss_m",
    "rl_loss_h",
    "interest",
    "tax",
    "equity",
    "net_debt",
    "ic_fy27",
    "settlement_npv",
    "r_foa",
    "r_rl",
    "g2",
    "eps_ttm_reported",
    "eps_ttm_clean",
    "pe_own_min",
    "pe_own_max",
    "rf_hub",
    "rf_step",
    "rf_cap",
    "capex_guide_low",
    "capex_guide_high",
]

TIERS = ("l", "m", "h")


def band(
    inp: dict[str, float],
    *,
    g2: float | None = None,
    ic: float | None = None,
    r_shift: float = 0.0,
    rl_scale: float = 1.0,
    tax: float | None = None,
    settlement_npv: float | None = None,
) -> dict[str, dict[str, float]]:
    """Per-tier {v, nopat, roic, pe, rl} for the base deck or one perturbation."""
    g2 = inp["g2"] if g2 is None else g2
    ic = inp["ic_fy27"] if ic is None else ic
    tax = inp["tax"] if tax is None else tax
    settlement_npv = inp["settlement_npv"] if settlement_npv is None else settlement_npv
    r_foa, r_rl = inp["r_foa"] + r_shift, inp["r_rl"] + r_shift
    shares = inp["shares"]
    closing = -(inp["net_debt"] + settlement_npv) / shares
    out: dict[str, dict[str, float]] = {}
    for k in TIERS:
        rl_ps = inp[f"rl_loss_{k}"] * rl_scale * (1.0 - tax) / shares
        nopat = inp[f"eps_{k}"] + rl_ps + inp["interest"] * (1.0 - tax) / shares
        roic = nopat * shares / ic
        pe = perpetual_pe(g2, roic, r_foa)
        rl_leg = -rl_ps / r_rl
        out[k] = {"v": nopat * pe + rl_leg + closing, "nopat": nopat, "roic": roic, "pe": pe, "rl": rl_leg}
    return out


def lmh(b: dict[str, dict[str, float]]) -> tuple[float, float, float]:
    return b["l"]["v"], b["m"]["v"], b["h"]["v"]


def fmt(b: dict[str, dict[str, float]]) -> str:
    return " / ".join(f"{v:.1f}" for v in lmh(b))


def solve(fn, lo: float, hi: float, target: float, increasing: bool) -> float:
    """Bisect fn(x) = target on [lo, hi]; fn monotone in the stated direction."""
    for _ in range(100):
        mid = (lo + hi) / 2
        if (fn(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        return report([f"formula_id {FORMULA_ID} missing from framework"])
    inp = parse_inputs(md)
    if missing := check_missing(inp, REQUIRED):
        return report(missing)

    errors: list[str] = []
    price, shares, g2 = inp["price"], inp["shares"], inp["g2"]

    # --- Step 1: r by basket, g2 under the cap, perpetuity away from the pole ---
    baskets = parse_baskets(md)
    for where in ("r_foa", "r_rl"):
        if where not in baskets:
            errors.append(f"{where}: Inputs source cell names no 篮 N (valuation-rules「§r 篮子」)")
        errors += check_r(inp[where], where, baskets.get(where))
    r = inp["r_foa"]
    errors += check_g_cap(g2, r, "g2")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"r - g2 = {r - g2:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    # --- Step 2: the two-leg deck ---
    base = band(inp)
    L, M, H = lmh(base)
    A, Bcut = cut_points(L, M, H)
    zone = zone_of(price, L, M, H)
    errors += ladder("L<M<H", L, M, H)
    errors += ladder("NOPAT", *(base[k]["nopat"] for k in TIERS))
    if not (inp["rl_loss_l"] >= inp["rl_loss_m"] >= inp["rl_loss_h"]):
        errors.append("RL loss path must be L >= M >= H (L is the wider-loss world, A7)")
    # Flat ladder: the numerator alone must separate the tiers.
    pe_m = base["m"]["pe"]
    closing = -(inp["net_debt"] + inp["settlement_npv"]) / shares
    flat = [base[k]["nopat"] * pe_m + base[k]["rl"] + closing for k in TIERS]
    errors += ladder("flat-multiple", *flat)
    # Gordon branch on the M-tier ROIC; the payout gap is a disclosure.
    errors += check_branch(g2, base["m"]["roic"], r, PAYOUT_OBSERVED, "M")
    payout_modelled, gap = payout_gap(g2, base["m"]["roic"], PAYOUT_OBSERVED)

    # --- Step 3: guardrail ③ on the own realised band (reported TTM basis) ---
    pe_m_ttm = M / inp["eps_ttm_reported"]
    pe_h_clean = H / inp["eps_ttm_clean"]
    if not (inp["pe_own_min"] <= pe_m_ttm <= inp["pe_own_max"]):
        errors.append(
            f"M / reported TTM = {pe_m_ttm:.1f}x outside own band "
            f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] (③ 出带)"
        )
    if pe_h_clean > inp["pe_own_max"]:
        errors.append(f"H / clean TTM = {pe_h_clean:.1f}x above band top {inp['pe_own_max']:g}")

    # --- Step 4: implied r(P) / g2 / IC — disclosure, with the A13 delta gate ---
    delta = solve(lambda d: band(inp, r_shift=d)["m"]["v"], -0.05, 0.05, price, increasing=False)
    g_implied = solve(lambda g: band(inp, g2=g)["m"]["v"], 0.0, r - 1e-3, price, increasing=True)
    ic_now = inp["equity"] + inp["net_debt"]
    ic_mult = solve(lambda x: band(inp, ic=ic_now * x)["m"]["v"], 1.0, 3.0, price, increasing=False)
    if abs(delta) > IMPLIED_R_TOL:
        errors.append(f"implied r(P) delta {delta:+.2%} beyond {IMPLIED_R_TOL:.0%} — basket review (A13)")

    # --- Step 5: constituent mount on _AXIS.ai-capex (A11) ---
    errors += check_capex_constituent(inp["capex_guide_low"], inp["capex_guide_high"])

    # --- Step 6: compare with the stated Outputs block ---
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": Bcut}, zone)

    print(f"formula_id={FORMULA_ID}")
    print(
        f"r={r:g} (r_foa 篮 {baskets.get('r_foa')}, r_rl 篮 {baskets.get('r_rl')})  "
        f"g2={g2:g}  g_cap={g_cap(r):.3f}  ic_fy27={inp['ic_fy27']:g}B (now {ic_now:.1f}B, x{inp['ic_fy27'] / ic_now:.2f})"
    )
    for k in TIERS:
        t = base[k]
        print(
            f"  {k.upper()}: NOPAT {t['nopat']:.2f} x PE {t['pe']:.2f} (ROIC {t['roic']:.1%}) "
            f"= {t['nopat'] * t['pe']:.1f}  RL {t['rl']:.1f}  closing {closing:.1f}  -> {t['v']:.1f}"
        )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={Bcut:.2f}  price={price} zone={zone}")
    print(f"flat (all {pe_m:.2f}x): " + " / ".join(f"{x:.1f}" for x in flat))
    print(f"L/M {L / M:.3f}  H/M {H / M:.3f}  (H-L)/2M {(H - L) / 2 / M:.3f}")
    print(
        f"payout: modelled {payout_modelled:.0%} at M ROIC vs observed {PAYOUT_OBSERVED:.0%} "
        f"(gap {gap:+.0%}; ROIC >= r + 3pp so sign test only — disclosure)"
    )
    print(
        f"guardrail ③: M / reported TTM {inp['eps_ttm_reported']:g} = {pe_m_ttm:.1f}x in "
        f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]; H / clean TTM {inp['eps_ttm_clean']:g} = {pe_h_clean:.1f}x"
    )
    print(
        f"implied r(P): delta {delta * 100:+.2f}pp (r {r + delta:.2%}) | implied g2 {g_implied:.2%} | "
        f"implied IC x{ic_mult:.2f} (path x{inp['ic_fy27'] / ic_now:.2f}) — disclosure only (A13)"
    )
    lo, hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(f"axis _AXIS.ai-capex constituent: FY26 capex guide share of 2026 base {lo:.1%}–{hi:.1%}")

    # Disclosures: r_f band, reverse pressure, g2 +-1pp (sensitivity zone), IC, RL, settlement, tax.
    rf_rows = []
    for dx in (-inp["rf_step"], 0.0, inp["rf_step"]):
        b = band(inp, r_shift=dx)
        rf_rows.append(f"r {r + dx:.1%}: {fmt(b)} {zone_of(price, *lmh(b))}")
    print("r_f band: " + " | ".join(rf_rows))
    rp_l = band(inp, r_shift=inp["rf_cap"])["l"]["v"]
    rp_h = band(inp, r_shift=-inp["rf_cap"])["h"]["v"]
    print(f"reverse pressure ±{inp['rf_cap'] * 1e4:.0f}bp: {rp_l:.1f} / {M:.1f} / {rp_h:.1f} {zone_of(price, rp_l, M, rp_h)}")
    for g in (g2 - 0.01, g2 + 0.01):
        b = band(inp, g2=g)
        z = zone_of(price, *lmh(b))
        over_cap = " (above g_cap, reference only)" if g > g_cap(r) + 1e-9 else ""
        flip = " — SENSITIVITY ZONE: zone flips" if z != zone else ""
        print(f"g2 {g:.1%}: {fmt(b)} {z}{over_cap}{flip}")
    for label, b in (
        ("IC frozen", band(inp, ic=ic_now)),
        (f"IC x{IC_STRESS_MULT}", band(inp, ic=ic_now * IC_STRESS_MULT)),
        ("RL = 0 (bull, not adopted)", band(inp, rl_scale=0.0)),
    ):
        print(f"{label}: {fmt(b)} {zone_of(price, *lmh(b))}")
    m_contingent = band(inp, settlement_npv=inp["settlement_npv"] + SETTLEMENT_CONTINGENT_B)["m"]["v"]
    m_tax21 = band(inp, tax=0.21)["m"]["v"]
    print(f"settlement contingent 30% (+{SETTLEMENT_CONTINGENT_B}B): M {m_contingent - M:+.1f} | tax 21%: M {m_tax21 / M - 1:+.1%}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
