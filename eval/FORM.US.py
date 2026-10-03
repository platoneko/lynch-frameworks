#!/usr/bin/env python3
"""FORM.US valuation eval — recompute anchors from frameworks/FORM.US.md.

formula_id: form_fy27_cons_gordon_opeq_v2

One operating leg on the FY27 consensus EPS range (8 houses; the furthest year
with a >=2-house *range*, valuation-rules 裁决顺序 ②; FY28 exists only as
point values of unknown house count, A2).  Street EPS is the company's adjusted
(ex-SBC) figure, so every tier is haircut by the SBC share derived from the
GAAP-vs-adjusted quarterly consensus gap net of acquisition amortisation (A4).
Multiples are generated, not borrowed: `perpetual_pe(g2, ROE_x, r)` with g2 =
the test-equipment peer cluster's reverse-solved median truncated to g_cap(r)
(A7), r = 10% — basket 4 常规经营 (probe cards are custom consumables priced by
the company; the cycle is customers' design starts and wafer mix, not a
commodity price; no customer near the basket-7 threshold, A9) — and tier ROE =
FY27 core EPS over the FY27 OPENING *operating* book: book equity less net cash
at 2026-06-27, rolled over the FY26 second half not yet booked at the
growth-required retention b1 = g2/ROE (A6).  The after-tax net interest is
stripped from the numerator and the net cash added back per share as a closing
item (A5, the 1810.HK A15 treatment).  FY27 = current FY + 1: no discount.

V_opt (v2, 2026-10-03 rules — valuation-rules「未建模期权」): the size comes
only from a quantity FORM itself named — the management 2030 revenue target
less the FY27 consensus revenue already priced in H (A16).  Unit economics are
the aligned year's own consensus: FY27 core earnings per dollar of FY27 mean
consensus revenue (borrow quantity, never price).  The increment is valued on
this ticker's ruler at the H-tier multiple in the target year and discounted
back to the numerator year at the basket r.  GPU probe cards and CPO are the
named drivers inside that increment, no longer separate units (A15 / A19).
No candidate band: the 2030 target is the option's count and may not be
written twice.  Probabilities live only in the zone+V table.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here reads one.

Run:  python3 frameworks/eval/FORM.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import check_g_cap, check_r, g_cap, implied_g, perpetual_pe  # noqa: E402
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

FRAMEWORK = REPO_ROOT / "frameworks" / "FORM.US.md"
FORMULA_ID = "form_fy27_cons_gordon_opeq_v2"
LISTING_CCY = "USD"
TOL = 0.05
MILLION = 1e6  # money inputs are in $M, share counts are absolute
MIN_R_MINUS_G = 0.02
HAIRCUT_ROUNDING = 0.01  # A4: haircut may be rounded up by at most 1pp over the derived value
QUARTERS_IN_GAP = 3  # A4: the GAAP-vs-adjusted gap spans three consensus quarters
P_TIERS = (0.0, 0.25, 1.0)  # A16 — table 3 only, never an input

REQUIRED = [
    "shares", "shares_out", "equity", "cash", "net_cash", "int_q", "tax",
    "eps_fy26_m", "eps_h1_26", "eps_fy27_l", "eps_fy27_m", "eps_fy27_h",
    "cons_q_adj", "cons_q_gaap", "amort_fy25", "sbc_fy25", "sbc_haircut",
    "payout_3y", "r_perp", "g2", "g_peer_median", "k_l", "k_m", "k_h",
    "mgmt_rev_2030", "mgmt_eps_2030", "rev_fy27_m", "rev_fy27_h", "t_opt", "t_num", "mgmt_delay",
    "pb_low",
]
TIERS = ("L", "M", "H")


def derived_haircut(inp: dict[str, float]) -> tuple[float, float]:
    """A4: SBC share of adjusted EPS from the three-quarter GAAP gap, amortisation removed.

    Returns (haircut, implied annual pre-tax SBC in $M) — the latter is printed
    against FY25 actual SBC as a plausibility read.
    """
    amort_ps = inp["amort_fy25"] * QUARTERS_IN_GAP / 4 * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    gap = inp["cons_q_adj"] - inp["cons_q_gaap"] - amort_ps
    sbc_annual = gap * 4 / QUARTERS_IN_GAP * inp["shares"] / MILLION / (1.0 - inp["tax"])
    return gap / inp["cons_q_adj"], sbc_annual


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A9: one leg, r is the basket's value; the basket is named in the Inputs source cell.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A9)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    # A7: g2 is the peer median truncated to g_cap(r).
    cap = g_cap(inp["r_perp"])
    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if abs(inp["g2"] - min(inp["g_peer_median"], cap)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {cap:.3f}) — A7")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {inp['r_perp'] - inp['g2']:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # 裁决顺序 ④ 同世界门: own consensus FY26 -> FY27 is up, so a g2 >= 0 source is admissible.
    if not inp["eps_fy26_m"] < inp["eps_fy27_m"]:
        errs.append("FY26 consensus not below FY27: the same-world gate for a g2 >= 0 source no longer holds (A7)")
    if inp["g2"] < 0:
        errs.append("g2 < 0 contradicts an upward FY26->FY27 consensus (同世界门)")

    # A2e-2a: one consensus range, three points on it.
    errs += ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])

    # A4: haircut derived from the GAAP gap, rounded up by at most 1pp.
    derived, sbc_annual = derived_haircut(inp)
    if not (derived - 1e-9 <= inp["sbc_haircut"] <= derived + HAIRCUT_ROUNDING + 1e-9):
        errs.append(f"sbc_haircut={inp['sbc_haircut']:.4f} outside [derived {derived:.4f}, +{HAIRCUT_ROUNDING:.2f}] (A4)")
    if sbc_annual < inp["sbc_fy25"]:
        errs.append(f"GAAP gap implies annual SBC {sbc_annual:.1f}M below FY25 actual {inp['sbc_fy25']:g}M — re-source (A4)")

    # A5: the closing item must be what the equity field is net of.
    if not 0 < inp["net_cash"] <= inp["cash"]:
        errs.append(f"net_cash {inp['net_cash']} must be positive and <= cash {inp['cash']} (A5)")
    if inp["equity"] - inp["net_cash"] <= 0:
        errs.append("operating equity (equity - net_cash) is not positive (A5)")

    # A10: deemed-distributed discount k, per tier, cyclical ordering.
    ks = (inp["k_l"], inp["k_m"], inp["k_h"])
    if not all(0.0 <= k < 1.0 for k in ks) or not ks[0] <= ks[1] <= ks[2]:
        errs.append(f"k_l/k_m/k_h = {ks} must lie in [0,1) with k_H >= k_M >= k_L (A10)")

    # A16: the option counts only what the target adds above consensus already in H.
    if not inp["mgmt_rev_2030"] > inp["rev_fy27_h"] >= inp["rev_fy27_m"] > 0:
        errs.append("mgmt_rev_2030 must exceed FY27 consensus revenue (H >= M > 0) — nothing left to count (A16)")
    if not inp["t_opt"] > inp["t_num"]:
        errs.append("t_opt must fall after the numerator year t_num (A16)")

    # A2e-7a: probabilities stay in the zone+V table.
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    return errs


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    errors = sanity_checks(inp, baskets)

    r, g2 = inp["r_perp"], inp["g2"]
    cap = g_cap(r)
    street = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    # ---- Step 1-2: economic EPS, then core EPS with the net interest stripped (A4, A5) ----
    int_ps = inp["int_q"] * 4 * (1.0 - inp["tax"]) * MILLION / inp["shares"]

    def core_at(haircut: float) -> dict[str, float]:
        return {t: street[t] * (1.0 - haircut) - int_ps for t in TIERS}

    core = core_at(inp["sbc_haircut"])

    # ---- Step 3-5: tier ROE on the FY27 opening operating book, Gordon multiple, cash added back ----
    # The 2026-06-27 operating book is rolled over the FY26 second half not yet
    # booked (consensus less H1 actual, same core basis) at b1 = g2/ROE (A6).
    # Closed form BPS = BPS0 / (1 - g·N/core); a diverging roll stops.
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] * MILLION / inp["shares"]
    bps0 = equity_op * MILLION / inp["shares"]

    def unbooked(haircut: float) -> float:
        return (inp["eps_fy26_m"] - inp["eps_h1_26"]) * (1.0 - haircut) - int_ps / 2

    def opening_bps(core_x: float, g: float, n: float) -> float:
        share = g * n / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps0 / (1.0 - share)

    def deck(g: float, rr: float, haircut: float) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
        c = core_at(haircut)
        n = unbooked(haircut)
        bps = {t: opening_bps(c[t], g, n) for t in TIERS}
        roe_ = {t: c[t] / bps[t] for t in TIERS}
        pe_ = {t: perpetual_pe(g, roe_[t], rr) for t in TIERS}
        val = {t: c[t] * pe_[t] * (1.0 - k[t]) + cash_ps for t in TIERS}
        return bps, roe_, pe_, val

    bps, roe, pes, scen = deck(g2, r, inp["sbc_haircut"])
    n_unbooked = unbooked(inp["sbc_haircut"])
    b1 = {t: g2 / roe[t] for t in TIERS}
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * n_unbooked for t in TIERS}  # disclosure only

    L, M, H = scen["L"], scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)

    # ---- A2e-2c flat ladder + decomposition ----
    if not (core["L"] < core["M"] < core["H"]):
        errors.append(f"numerator ladder broken: core EPS {core['L']:.3f}/{core['M']:.3f}/{core['H']:.3f} (A2e-2c)")
    flat = [core[t] * pes["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    ex_cash = {t: core[t] * pes[t] for t in TIERS}

    # ---- ③ guardrail is not applicable (numerator never realised, A12): print the reconciliation coordinates ----
    e_over_r = core["M"] / r + cash_ps
    bvps = inp["equity"] * MILLION / inp["shares_out"]
    asset_coord = inp["pb_low"] * bvps

    # ---- g2 leverage: -1pp disclosed (L/M/H only); +1pp breaks ① ----
    _, _, _, lo = deck(g2 - 0.01, r, inp["sbc_haircut"])
    lo_ok = lo["L"] < lo["M"] < lo["H"]

    # ---- Option ceiling and zone+V (probabilities only here) ----
    # A16: count = 2030 revenue target - FY27 consensus revenue already in H;
    # unit economics = FY27 mean-consensus core earnings per revenue dollar;
    # valued at the H multiple in the target year, discounted to the numerator year.
    d_rev = inp["mgmt_rev_2030"] - inp["rev_fy27_h"]
    core_margin = core["M"] * inp["shares"] / (inp["rev_fy27_m"] * MILLION)
    d_core = d_rev * MILLION * core_margin / inp["shares"]
    years = inp["t_opt"] - inp["t_num"]

    def option_at(t: float) -> float:
        return d_core * pes["H"] / (1.0 + r) ** t

    v_opt = option_at(years)
    v_opt_late = option_at(years + inp["mgmt_delay"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    meta = load_framework(FRAMEWORK)
    if meta.v_opt is None or abs(meta.v_opt - v_opt) > TOL:
        errors.append(f"V_opt: stated {meta.v_opt} vs recomputed {v_opt:.4f}")
    if meta.p_tiers != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {meta.p_tiers} vs A15 {P_TIERS}")
    opt = tuple(anchor + p * v_opt for anchor, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)

    # The 2030 target is the option's count (A16); a candidate band on it would count it twice.
    if meta.candidate is not None:
        errors.append("候选带 line present — the 2030 target now sizes V_opt and may not be written twice (A16)")

    # ---- Report ----
    derived, sbc_annual = derived_haircut(inp)
    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 {baskets.get('r_perp')}) g2={g2:.4f} (peer median {inp['g_peer_median']:.4f} truncated to g_cap(r) {cap:.3f})  "
          f"sbc haircut {inp['sbc_haircut']:.3f} (derived {derived:.4f}; implied annual SBC {sbc_annual:.1f}M vs FY25 {inp['sbc_fy25']:g}M)")
    print(f"operating equity {equity_op:.3f}M = book {inp['equity']:g} - net cash {inp['net_cash']:g}; "
          f"interest stripped {int_ps:.4f}/sh; cash added back {cash_ps:.4f}/sh")
    for t in TIERS:
        print(f"{t}: street {street[t]:.4f} -> core {core[t]:.4f}  BPS_op {bps[t]:.3f}  ROE {roe[t]:.4f}  payout {1 - b1[t]:.3f}  "
              f"PE {pes[t]:.4f}x -> {ex_cash[t]:.4f} x (1-k {k[t]:g}) + cash = {scen[t]:.4f}")
    print(f"ROE basis (A6): op BPS 2026-06-27 {bps0:.3f} rolled over FY26H2 unbooked core {n_unbooked:.4f}/sh at b1 "
          f"{b1['L']:.2f}/{b1['M']:.2f}/{b1['H']:.2f}")
    print(f"deemed-distributed cash (actual retention {ret_actual:.0%} − b1) × FY26H2 unbooked → "
          f"{excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh (k before = after, k = 0; disclosure only)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pes['M']:.2f}x (+cash): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"③ band not applicable (A12) — reconciliation coordinates: E_M/r + cash {e_over_r:.2f}; "
          f"asset pb_low {inp['pb_low']:g} x BVPS {bvps:.2f} = {asset_coord:.2f}; M multiple {pes['M']:.2f}x vs peer same-ruler 20.0–22.2x")
    print(f"L/M {L / M:.3f} (ex-cash {ex_cash['L'] / ex_cash['M']:.3f}) | H/M {H / M:.3f} (ex-cash {ex_cash['H'] / ex_cash['M']:.3f}) | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.2f}) -> {lo['L']:.2f}/{lo['M']:.2f}/{lo['H']:.2f} "
          f"{'(ladder broken)' if not lo_ok else ''}; +1pp exceeds cap {cap:.3f} (①, unusable)")
    for hc, tag in ((0.0, "street (no SBC haircut)"), (derived, f"derived haircut {derived:.4f}")):
        _, _, _, s = deck(g2, r, hc)
        print(f"sensitivity {tag}: {s['L']:.2f}/{s['M']:.2f}/{s['H']:.2f}")
    for rr, tag in ((0.13, "篮 6 13% (not adopted)"), (0.15, "篮 7 15% (not adopted)")):
        _, _, _, s = deck(g2, rr, inp["sbc_haircut"])
        print(f"contrast r {tag}: {s['L']:.2f}/{s['M']:.2f}/{s['H']:.2f}")
    print(f"V_opt={v_opt:.2f} = (target {inp['mgmt_rev_2030']:g}M - FY27 H consensus {inp['rev_fy27_h']:g}M = {d_rev:g}M) "
          f"x core margin {core_margin:.2%} (FY27 core M {core['M']:.4f} x shares / mean revenue {inp['rev_fy27_m']:g}M) "
          f"= dEPS {d_core:.4f} x PE_H {pes['H']:.2f}x = {d_core * pes['H']:.2f} / {1 + r:g}^{years:g}")
    print(f"V_opt timing sensitivity: target {inp['mgmt_delay']:g}y late like the 2020 model -> {v_opt_late:.2f}; "
          f"post-realisation core EPS H + dEPS = {core['H'] + d_core:.4f}")
    c30 = inp["mgmt_eps_2030"] * (1.0 - inp["sbc_haircut"]) - int_ps
    print(f"V_opt cross-check on the target EPS (company margin, not used): core {c30:.4f} - H {core['H']:.4f} "
          f"= {c30 - core['H']:.4f} x PE_H / {1 + r:g}^{years:g} = {(c30 - core['H']) * pes['H'] / (1.0 + r) ** years:.2f}")
    print(f"zone+V band: {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    for tp in (64.0, 157.5, 175.0, 200.0):
        g_tp, ok = implied_g((tp - cash_ps) / core["M"], roe["M"], r)
        print(f"street TP {tp:g} on this ruler (A17): implied perpetual g {g_tp:.4f}{'' if ok else ' (ill-conditioned)'}")

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1 — the only priced r; the
    # rolled ROE, g2, the haircut core numerator and the net-cash add-back stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        s = [core[t] * perpetual_pe(g2, roe[t], r + dr) * (1.0 - k[t]) + cash_ps for t in TIERS]
        return s[0], s[1], s[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("FORM.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
