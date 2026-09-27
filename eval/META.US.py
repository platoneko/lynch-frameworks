#!/usr/bin/env python3
"""META.US (Meta Platforms) valuation eval — recompute anchors from frameworks/META.US.md.

frameworks/META.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on any mismatch.  The doc
carries no current META price (AGENTS.md「现价 — 禁写契约」): which zone a quote
falls in is derived live by the daily digest and the app, so nothing here reads
it.  amd_price is another company's market price (the warrant's unit economics).

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

Option (meta_amd_warrant_option_v1, A14) -- table 3 only, never the deck:
  V_opt = amd_warrant_shares * (amd_price - amd_warrant_strike) * (1-tax) / shares
The AMD performance warrant is a one-off asset (a purchase rebate paid in AMD
stock), not an earnings stream, so it is taken at after-tax face value like a
closing item -- no multiple, no discount; outcome risk sits in p_k = 0 / 1/6 / 1
(first 1 GW tranche of 6 GW for M, full vesting at AMD >= $600 for H).

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
  * constituent mount on _AXIS.ai-capex (share of the 2026 base is sane)
  * no p-class fields in Inputs; L < M < H; stated anchors / cut points

Disclosures printed (never fed back into the anchors; L/M/H only):
  r_f readings from _AXIS.rates (rf_report.rf_block), g2 +-1pp,
  IC frozen / x1.58, RL = 0, contingent settlement 30%, tax 21%.

Run:  python3 frameworks/eval/META.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import capex_constituent_share, check_capex_constituent  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
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
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "META.US.md"
FORMULA_ID = "meta_fwd_numerator_gordon_foa_rl_icpath_v1"
LISTING_CCY = "USD"
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
# Observed payout for check_branch: dividend ~6% + buybacks ~55% of earnings
# (framework §3 step 3).  With ROIC >= r + 3pp the branch test is sign-only.
PAYOUT_OBSERVED = 0.61
# Contingent 30% of the state settlement (A8), pressure row only.
SETTLEMENT_CONTINGENT_B = 5.3
IC_STRESS_MULT = 1.58  # A9 upper IC stress
# A14: per-tier credit on the AMD warrant -- M = first 1 GW tranche of 6 GW
# (tranche sizes undisclosed, linear in GW), H = full vesting.
P_TIERS = (0.0, 1.0 / 6.0, 1.0)
V_OPT_TOL = 0.05

REQUIRED = [
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
    "capex_guide_low",
    "capex_guide_high",
    "amd_warrant_shares",
    "amd_warrant_strike",
    "amd_price",
]

TIERS = ("l", "m", "h")


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(r"p_L/p_M/p_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*", md)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def warrant_value(inp: dict[str, float], amd_price: float | None = None) -> float:
    """A14: after-tax face value per META share of the AMD warrant at full vesting."""
    px = inp["amd_price"] if amd_price is None else amd_price
    return inp["amd_warrant_shares"] * (px - inp["amd_warrant_strike"]) * (1.0 - inp["tax"]) / inp["shares"]


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


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        return report([f"formula_id {FORMULA_ID} missing from framework"])
    inp = parse_inputs(md)
    if missing := check_missing(inp, REQUIRED):
        return report(missing)

    errors: list[str] = []
    shares, g2 = inp["shares"], inp["g2"]

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

    # --- Step 4: current invested capital, the base of the IC-path disclosures ---
    ic_now = inp["equity"] + inp["net_debt"]

    # --- Step 5: constituent mount on _AXIS.ai-capex (A11) ---
    errors += check_capex_constituent(inp["capex_guide_low"], inp["capex_guide_high"])

    # --- Step 6: compare with the stated Outputs block ---
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": Bcut})

    # --- Step 7: option leg (A14) -- table 3 only; the deck above never sees it ---
    v_opt = warrant_value(inp)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > V_OPT_TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    said_p = stated_p_tiers(md)
    if said_p is None or any(abs(a - b) > 0.01 for a, b in zip(said_p, P_TIERS)):
        errors.append(f"p_L/p_M/p_H: stated {said_p} vs expected {tuple(round(p, 3) for p in P_TIERS)}")
    adj = tuple(v + p * v_opt for v, p in zip((L, M, H), P_TIERS))
    if abs(adj[0] - L) > 1e-9:
        errors.append("table 3 L row must equal base L (p_L = 0, check_no_p_leak)")
    a_adj, b_adj = cut_points(*adj)

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
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={Bcut:.2f}")
    print(f"flat (all {pe_m:.2f}x): " + " / ".join(f"{x:.1f}" for x in flat))
    print(f"L/M {L / M:.3f}  H/M {H / M:.3f}  (H-L)/2M {(H - L) / 2 / M:.3f}  V_opt/M {v_opt / M:.1%}")
    print(
        f"V_opt (A14 AMD warrant) = {inp['amd_warrant_shares']:g}B sh x (AMD {inp['amd_price']:g} - {inp['amd_warrant_strike']:g}) "
        f"x (1-{inp['tax']:g}) / {shares}B = {v_opt:.2f}/sh  p_k {P_TIERS[0]:g}/{P_TIERS[1]:.3f}/{P_TIERS[2]:g}"
    )
    print(f"表3: {adj[0]:.1f} / {adj[1]:.1f} / {adj[2]:.1f}  A'={a_adj:.1f} B'={b_adj:.1f}")
    print(
        "AMD $400/$600/$800 -> V_opt "
        + " / ".join(f"{warrant_value(inp, x):.1f}" for x in (400.0, 600.0, 800.0))
        + f"; p_M 0.5 -> M' {M + 0.5 * v_opt:.1f}"
    )
    print(
        f"payout: modelled {payout_modelled:.0%} at M ROIC vs observed {PAYOUT_OBSERVED:.0%} "
        f"(gap {gap:+.0%}; ROIC >= r + 3pp so sign test only — disclosure)"
    )
    print(
        f"guardrail ③: M / reported TTM {inp['eps_ttm_reported']:g} = {pe_m_ttm:.1f}x in "
        f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]; H / clean TTM {inp['eps_ttm_clean']:g} = {pe_h_clean:.1f}x"
    )
    lo, hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(f"axis _AXIS.ai-capex constituent: FY26 capex guide share of 2026 base {lo:.1%}–{hi:.1%}")

    # Disclosures: g2 +-1pp, IC, RL, settlement, tax; r_f readings below.
    for g in (g2 - 0.01, g2 + 0.01):
        b = band(inp, g2=g)
        over_cap = " (above g_cap, reference only)" if g > g_cap(r) + 1e-9 else ""
        print(f"g2 {g:.1%}: {fmt(b)}{over_cap}")
    for label, b in (
        ("IC frozen", band(inp, ic=ic_now)),
        (f"IC x{IC_STRESS_MULT}", band(inp, ic=ic_now * IC_STRESS_MULT)),
        ("RL = 0 (bull, not adopted)", band(inp, rl_scale=0.0)),
    ):
        print(f"{label}: {fmt(b)}")
    m_contingent = band(inp, settlement_npv=inp["settlement_npv"] + SETTLEMENT_CONTINGENT_B)["m"]["v"]
    m_tax21 = band(inp, tax=0.21)["m"]["v"]
    print(f"settlement contingent 30% (+{SETTLEMENT_CONTINGENT_B}B): M {m_contingent - M:+.1f} | tax 21%: M {m_tax21 / M - 1:+.1%}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves both
    # priced r 1:1 — r_foa (Gordon multiple) and r_rl (RL loss capitalisation) — via
    # band()'s r_shift; numerator, g2, IC path, closing items stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return lmh(band(inp, r_shift=dr))

    rf = rf_block(LISTING_CCY, {"r_foa": inp["r_foa"], "r_rl": inp["r_rl"]}, band_rf)

    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("META.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
