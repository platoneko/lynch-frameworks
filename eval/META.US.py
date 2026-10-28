#!/usr/bin/env python3
"""META.US (Meta Platforms) valuation eval — recompute anchors from frameworks/META.US.md.

frameworks/META.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on any mismatch.  The doc
carries no current META price (AGENTS.md「现价 — 禁写契约」): which zone a quote
falls in is derived live by the daily digest and the app, so nothing here reads
it.  amd_price is another company's market price (the warrant's unit economics).

formula_id: meta_fwd_numerator_gordon_foa_rl_icpath_v1

Main ruler: two legs summed per tier k in {L, M, H} (one estimation date, FY2027 = t=1).

  FoA leg   NOPAT_k = eps_k + rl_addback(1-tax)/shares + interest(1-tax)/shares
            ROIC_k  = NOPAT_k * shares / ic_fy27        (invested-capital PATH, not equity)
            PE_k    = perpetual_pe(g2, ROIC_k, r_foa)  (Gordon, generated not borrowed)
  RL leg    -rl_loss_k(1-tax) / (shares * r_rl)        (loss capitalised, g = 0)

The RL add-back is the loss the consensus EPS already carries (one value for
all tiers); the RL leg runs the loss path (A7).  Wiring one number into both
made a smaller RL loss lower the value (the add-back is multiplied by the FoA
multiple, the leg only by 1/r) -- split 2026-10-28.
  closing   -(net_debt + settlement_npv + nm_penalty) / shares
  gap       growth-period funding gap (valuation-rules「经营价值与超额现金」①):
            Q4'26 capex + SBC - Q4'26 OCF (window EPS x shares x OCF/NI), per share,
            deducted as a debt-like item (no excess-cash row; parent share 1.0)
  V_k       = (NOPAT_k * PE_k + RL_k) / (1 + r)^tau + closing - gap
  equity    V_k' = (V_k * shares + offering_proceeds - pref_div_pv) / (shares + new_shares)
            (Oct-2026 offering: 40M forward-sale shares + mandatory convertible
            preferred at its maximum 20M conversion shares; EPS stays on the
            pre-offering share basis, so dilution is applied once, here)

Time alignment (③): the Gordon value sits at the FY27 opening (2027-01-01);
discounted tau = 0.25 years to the 2026-09-30 balance sheet.  With a funding gap
the window's distributable profit is booked as 0 (OCF already carries it).
Stable-return path (②): the FoA leg's forward ROIC (22.3 / 25.2 / 29.8%) sits
below the stable return ronic_ss (41.9%: own trough-to-trough cycle 2019-2022 on
invested capital, taken first under the 2026-10-19 order), so the path is flat and the
multiple is the plain perpetual_pe; the eval asserts ROIC <= ronic_ss.

The numerator is the FY2027E GAAP consensus at its low / mean / high (A3); the
tiers differ ONLY in that layer plus the RL loss path (A7).  The multiple is
told apart by tier ROIC, whose denominator is the FY27 invested-capital path
$421.1B (A6): capex is half debt-funded, so equity alone cannot see it.

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
    [pe_own_min, pe_own_max] (within M_BAND_TOL below the floor: disclosed --
    a trailing band against a forward numerator, user 2026-10-29);
    H / clean TTM EPS at or below the band top
    (within H_BAND_TOL: an overshoot up to 1% is printed as a disclosure,
    user 2026-10-22)
  * constituent mount on _AXIS.ai-capex (share of the 2026 base is sane)
  * no p-class fields in Inputs; L < M < H; stated anchors / cut points

Disclosures printed (never fed back into the anchors; L/M/H only):
  r_f readings from _AXIS.rates (rf_report.rf_block), g2 +-1pp,
  IC frozen / 2027 capex at $249B, RL leg = 0, contingent settlement 30%, tax 21%.

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
# Observed payout for check_branch, 9M26: dividends 4.06B + tax paid on net share
# settlement 12.77B over NI 52.48B; no buybacks in 2026 (framework §3 step 3).
# With ROIC >= r + 3pp the branch test is sign-only.
PAYOUT_OBSERVED = 0.32
# Contingent 30% of the state settlement (A8), pressure row only.
SETTLEMENT_CONTINGENT_B = 5.3
# A9 upper IC stress: 2027 capex at Wedbush $249B instead of GS $223.4B (same path otherwise).
IC_HIGH_CAPEX_DELTA = 249.0 - 223.4
# A14: per-tier credit on the AMD warrant -- M = first 1 GW tranche of 6 GW
# (tranche sizes undisclosed, linear in GW), H = full vesting.
P_TIERS = (0.0, 1.0 / 6.0, 1.0)
V_OPT_TOL = 0.05
# Guardrail ③ H side: overshoot of the band top up to this share is disclosed,
# not failed (user 2026-10-22: strict clean TTM 30.61, H 28.7x vs top 28.7x).
H_BAND_TOL = 0.01
# Guardrail ③ M side: the realised band is trailing reported PE, the numerator is
# FY27 forward, and no month has carried TTM EPS near the M numerator, so the
# band test does not bind (out-of-band rule step 1); a shortfall up to this share
# is disclosed (user 2026-10-29 accepted the revision with the L-tier band breach).
M_BAND_TOL = 0.02

REQUIRED = [
    "shares",
    "eps_l",
    "eps_m",
    "eps_h",
    "rl_loss_l",
    "rl_loss_m",
    "rl_loss_h",
    "rl_addback",
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
    "tau",
    "ronic_ss",
    "eps_fy26",
    "eps_9m_26",
    "ocf_ni",
    "capex_q4_26",
    "sbc_q4_26",
    "nm_penalty",
    "new_shares",
    "offering_proceeds",
    "pref_div_pv",
]


def to_equity(v: float, inp: dict[str, float]) -> float:
    """Spread the per-share deck over the post-offering count, cash in, preferred dividends out."""
    shares = inp["shares"]
    return (v * shares + inp["offering_proceeds"] - inp["pref_div_pv"]) / (shares + inp["new_shares"])


def funding_gap(inp: dict[str, float]) -> float:
    """① growth-period funding gap per share: Q4'26 capex + SBC beyond Q4'26 OCF."""
    ocf = (inp["eps_fy26"] - inp["eps_9m_26"]) * inp["shares"] * inp["ocf_ni"]
    return max(inp["capex_q4_26"] + inp["sbc_q4_26"] - ocf, 0.0) / inp["shares"]

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
    per = inp["shares"] + inp["new_shares"]
    return inp["amd_warrant_shares"] * (px - inp["amd_warrant_strike"]) * (1.0 - inp["tax"]) / per


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
    closing = -(inp["net_debt"] + settlement_npv + inp["nm_penalty"]) / shares - funding_gap(inp)
    disc = (1.0 + r_foa) ** inp["tau"]
    out: dict[str, dict[str, float]] = {}
    for k in TIERS:
        rl_ps = inp[f"rl_loss_{k}"] * rl_scale * (1.0 - tax) / shares
        add_ps = inp["rl_addback"] * (1.0 - tax) / shares
        nopat = inp[f"eps_{k}"] + add_ps + inp["interest"] * (1.0 - tax) / shares
        roic = nopat * shares / ic
        pe = perpetual_pe(g2, roic, r_foa)
        rl_leg = -rl_ps / r_rl
        out[k] = {"v": to_equity((nopat * pe + rl_leg) / disc + closing, inp), "nopat": nopat, "roic": roic, "pe": pe,
                  "rl": rl_leg, "disc": disc}
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
    gap_ps = funding_gap(inp)
    closing = -(inp["net_debt"] + inp["settlement_npv"] + inp["nm_penalty"]) / shares - gap_ps
    disc = base["m"]["disc"]
    flat = [to_equity((base[k]["nopat"] * pe_m + base[k]["rl"]) / disc + closing, inp) for k in TIERS]
    errors += ladder("flat-multiple", *flat)
    # ② stable-return path: flat only while every tier's forward ROIC <= ronic_ss.
    for k in TIERS:
        if base[k]["roic"] > inp["ronic_ss"] + 1e-12:
            errors.append(f"{k.upper()} ROIC {base[k]['roic']:.1%} > ronic_ss {inp['ronic_ss']:.0%}: "
                          "the return path bites -- implement the three-stage multiple")
    # Gordon branch on the M-tier ROIC; the payout gap is a disclosure.
    errors += check_branch(g2, base["m"]["roic"], r, PAYOUT_OBSERVED, "M")
    payout_modelled, gap = payout_gap(g2, base["m"]["roic"], PAYOUT_OBSERVED)

    # --- Step 3: guardrail ③ on the own realised band (reported TTM basis) ---
    pe_m_ttm = M / inp["eps_ttm_reported"]
    pe_h_clean = H / inp["eps_ttm_clean"]
    m_short = 1.0 - pe_m_ttm / inp["pe_own_min"]
    if pe_m_ttm > inp["pe_own_max"] or m_short > M_BAND_TOL:
        errors.append(
            f"M / reported TTM = {pe_m_ttm:.1f}x outside own band "
            f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] (③ 出带)"
        )
    h_over = pe_h_clean / inp["pe_own_max"] - 1.0
    if h_over > H_BAND_TOL:
        errors.append(f"H / clean TTM = {pe_h_clean:.1f}x above band top {inp['pe_own_max']:g} by {h_over:.1%}")

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
            f"= {t['nopat'] * t['pe']:.1f}  RL {t['rl']:.1f}  / 1.1^tau {disc:.4f}  closing {closing:.1f}  -> {t['v']:.1f}"
        )
    print(f"tau {inp['tau']} (2026-09-30 -> FY27 opening); window profit 0 (funding gap present); "
          f"gap {gap_ps:.2f}/sh = (Q4'26 capex {inp['capex_q4_26']:g}B + SBC {inp['sbc_q4_26']:g}B - OCF "
          f"{(inp['eps_fy26'] - inp['eps_9m_26']) * shares * inp['ocf_ni']:.2f}B) / {shares}B; "
          f"stable return {inp['ronic_ss']:.0%} >= every tier ROIC -> path flat")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={Bcut:.2f}")
    print(f"flat (all {pe_m:.2f}x): " + " / ".join(f"{x:.1f}" for x in flat))
    print(f"L/M {L / M:.3f}  H/M {H / M:.3f}  (H-L)/2M {(H - L) / 2 / M:.3f}  V_opt/M {v_opt / M:.1%}")
    print(
        f"V_opt (A14 AMD warrant) = {inp['amd_warrant_shares']:g}B sh x (AMD {inp['amd_price']:g} - {inp['amd_warrant_strike']:g}) "
        f"x (1-{inp['tax']:g}) / {shares + inp['new_shares']:.3f}B = {v_opt:.2f}/sh  p_k {P_TIERS[0]:g}/{P_TIERS[1]:.3f}/{P_TIERS[2]:g}"
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
        f"guardrail ③: M / reported TTM {inp['eps_ttm_reported']:g} = {pe_m_ttm:.2f}x vs "
        f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
        + (f" — below the floor by {m_short:.1%}, disclosed (M_BAND_TOL {M_BAND_TOL:.0%}, user 2026-10-29)" if m_short > 0 else "")
        + f"; H / clean TTM {inp['eps_ttm_clean']:g} = {pe_h_clean:.2f}x"
        + (f" — above band top by {h_over:.1%}, disclosed (H_BAND_TOL {H_BAND_TOL:.0%}, user 2026-10-22)" if h_over > 0 else "")
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
        ("IC at 2027 capex $249B", band(inp, ic=inp["ic_fy27"] + IC_HIGH_CAPEX_DELTA)),
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
