#!/usr/bin/env python3
"""TER.US valuation eval — recompute anchors from frameworks/TER.US.md.

formula_id: ter_fy27_cons_gordon_opeq_v1

One operating leg (Semiconductor Test is ~98% of segment pre-tax profit in
1H26; Product Test and Robotics ride inside the consensus, A1) on the FY27
consensus EPS range (18 houses — the furthest year with a >=2-house *range*,
valuation-rules 裁决顺序 ②).  Teradyne's non-GAAP EPS keeps stock comp in
(it strips only acquired-intangible and Technoprobe basis amortisation,
restructuring and similar, A4), so no SBC haircut.  Two closing items are
added back per share: net cash (cash and marketable securities less lease
liabilities; debt is nil) and the 10% Technoprobe stake at the fair value the
10-Q discloses, less US federal tax on the unrealised gain (A6).  Their
earnings — after-tax interest income and the non-GAAP Technoprobe equity
pick-up — are stripped from the numerator first so nothing is counted twice.

Multiples are generated, not borrowed: `perpetual_pe(g2, ROE_x, r)` with
g2 = the test-equipment peer cluster's reverse-solved median truncated to
g_cap(r) (A7), r = 10% basket 4 常规经营 (A8), and tier ROE = FY27 core EPS
over the FY27 OPENING operating book: book equity less net cash and the
Technoprobe carrying value at 2026-06-28, rolled over the FY26 second half
not yet booked at the growth-required retention b1 = g2/ROE (A9).
FY27 = current FY + 1: no discount.

V_opt = 0 (A12: management's undated target model sits inside FY27
consensus; market sizes are TAM, not named quantities).  One candidate band
(A13): MarketScreener's FY28 point (house count unknown) opens a one-year
transition g1 on the M and H tiers only; L' = L.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here reads one.

Run:  python3 frameworks/eval/TER.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    g_cap,
    implied_g,
    perpetual_pe,
    two_stage_pe,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "TER.US.md"
FORMULA_ID = "ter_fy27_cons_gordon_opeq_v1"
LISTING_CCY = "USD"
TOL = 0.05
MILLION = 1e6  # money inputs are in $M, share counts are absolute
MIN_R_MINUS_G = 0.02

REQUIRED = [
    "shares", "shares_out", "equity", "cash", "lease", "net_cash", "int_q", "tax",
    "tp_fv", "tp_book", "tp_tax", "tp_eq_q",
    "eps_fy26_m", "eps_h1_26", "eps_fy27_l", "eps_fy27_m", "eps_fy27_h",
    "eps_fy27_ms", "eps_fy28_ms",
    "payout_3y", "r_perp", "g2", "g_peer_median", "k_l", "k_m", "k_h",
    "eps_trough_ratio", "pb_low",
]
TIERS = ("L", "M", "H")
CANDIDATE_TIERS = ("M", "H")  # A13: the L world carries no transition growth


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A8: one leg, r is the basket's value; the basket is named in the Inputs source cell.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A8)")
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

    # A2e-2a: one consensus range, three points on it.
    errs += ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])

    # A5 / A6: closing items must be what the operating book is net of.
    if abs(inp["net_cash"] - (inp["cash"] - inp["lease"])) > 0.05:
        errs.append(f"net_cash {inp['net_cash']} != cash {inp['cash']} - lease {inp['lease']} (A5)")
    if not 0 < inp["net_cash"] <= inp["cash"]:
        errs.append(f"net_cash {inp['net_cash']} must be positive and <= cash {inp['cash']} (A5)")
    if not inp["tp_fv"] > inp["tp_book"] > 0:
        errs.append("Technoprobe fair value must exceed its carrying value (else the tax-on-gain leg flips sign, A6)")
    if inp["equity"] - inp["net_cash"] - inp["tp_book"] <= 0:
        errs.append("operating equity (equity - net_cash - tp_book) is not positive (A5/A6)")

    # A11: deemed-distributed discount k, per tier, cyclical ordering.
    ks = (inp["k_l"], inp["k_m"], inp["k_h"])
    if not all(0.0 <= k < 1.0 for k in ks) or not ks[0] <= ks[1] <= ks[2]:
        errs.append(f"k_l/k_m/k_h = {ks} must lie in [0,1) with k_H >= k_M >= k_L (A11)")

    # A13: the candidate's transition must point the same way as the base (FY27 -> FY28 up).
    if not inp["eps_fy28_ms"] > inp["eps_fy27_ms"] > 0:
        errs.append("candidate g1 source not upward (FY28 <= FY27 on MarketScreener) — drop the band (A13)")

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
    sh = inp["shares"]
    street = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    # ---- Step 1: core EPS — strip after-tax interest and the Technoprobe pick-up (A5, A6) ----
    int_ps = inp["int_q"] * 4 * (1.0 - inp["tax"]) * MILLION / sh
    tp_eps = inp["tp_eq_q"] * 4 * MILLION / sh
    strip = int_ps + tp_eps
    core = {t: street[t] - strip for t in TIERS}

    # ---- Step 2: closing items per share ----
    cash_ps = inp["net_cash"] * MILLION / sh
    tp_after = inp["tp_fv"] - (inp["tp_fv"] - inp["tp_book"]) * inp["tp_tax"]
    tp_ps = tp_after * MILLION / sh
    closing = cash_ps + tp_ps

    # ---- Step 3-5: tier ROE on the FY27 opening operating book, Gordon multiple ----
    # Operating book = equity - net cash - Technoprobe carrying value (2026-06-28),
    # rolled over the FY26 second half not yet booked at b = g/ROE (A9).
    # Closed form BPS = BPS0 / (1 - g·N/core); a diverging roll stops.
    equity_op = inp["equity"] - inp["net_cash"] - inp["tp_book"]
    bps0 = equity_op * MILLION / sh
    n_unbooked = inp["eps_fy26_m"] - inp["eps_h1_26"] - strip / 2

    def opening_bps(core_x: float, g: float) -> float:
        share = g * n_unbooked / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps0 / (1.0 - share)

    def deck(g: float, rr: float) -> tuple[dict, dict, dict, dict]:
        bps = {t: opening_bps(core[t], g) for t in TIERS}
        roe_ = {t: core[t] / bps[t] for t in TIERS}
        pe_ = {t: perpetual_pe(g, roe_[t], rr) for t in TIERS}
        val = {t: core[t] * pe_[t] * (1.0 - k[t]) + closing for t in TIERS}
        return bps, roe_, pe_, val

    bps, roe, pes, scen = deck(g2, r)
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
    flat = [core[t] * pes["M"] + closing for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    ex_close = {t: core[t] * pes[t] for t in TIERS}

    # ---- ③ guardrail not applicable (no same-earnings months, A10): reconciliation coordinates ----
    e_over_r = core["M"] / r + closing
    bvps = inp["equity"] * MILLION / inp["shares_out"]
    asset_coord = inp["pb_low"] * bvps
    trough_core = (inp["eps_fy26_m"] * inp["eps_trough_ratio"]) - strip
    trough_coord = trough_core / r + closing

    # ---- g2 leverage: -1pp disclosed; +1pp breaks ① ----
    _, _, _, lo = deck(g2 - 0.01, r)

    # ---- Candidate band (A13): FY28 single-source point -> one transition year on M/H ----
    g1 = inp["eps_fy28_ms"] / inp["eps_fy27_ms"] - 1.0
    cand = {"L": L}
    cand_pe = {}
    for t in CANDIDATE_TIERS:
        share = g1 * n_unbooked / core[t]
        bps_c = bps0 / (1.0 - share)
        roe_c = core[t] / bps_c
        cand_pe[t] = two_stage_pe(g1, 1, g2, roe_c, r)
        cand[t] = core[t] * cand_pe[t] * (1.0 - k[t]) + closing
    if not cand["L"] < cand["M"] < cand["H"]:
        errors.append(f"candidate band not ordered: {cand}")

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    meta = load_framework(FRAMEWORK)
    if meta.v_opt not in (None, 0.0):
        errors.append(f"V_opt stated {meta.v_opt} but A12 sets it to 0")
    if meta.candidate is None:
        errors.append("候选带 line missing (A13)")
    else:
        for got, want, tag in zip(meta.candidate, (cand["L"], cand["M"], cand["H"]), ("L′", "M′", "H′")):
            if abs(got - want) > TOL:
                errors.append(f"candidate {tag}: stated {got} vs recomputed {want:.4f}")
        if meta.candidate_gate != "A13":
            errors.append(f"candidate gate {meta.candidate_gate} != A13")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 {baskets.get('r_perp')}) g2={g2:.4f} (peer median {inp['g_peer_median']:.4f} truncated to g_cap(r) {cap:.3f})")
    print(f"strip from street EPS: interest {int_ps:.4f} + Technoprobe pick-up {tp_eps:.4f} = {strip:.4f}/sh")
    print(f"closing: net cash {cash_ps:.4f} + Technoprobe after tax {tp_ps:.4f} "
          f"(fv {inp['tp_fv']:g}M - ({inp['tp_fv']:g} - {inp['tp_book']:g}) x {inp['tp_tax']:g} = {tp_after:.1f}M) = {closing:.4f}/sh")
    print(f"operating equity {equity_op:.3f}M -> BPS0 {bps0:.4f}; FY26H2 unbooked core {n_unbooked:.4f}/sh")
    for t in TIERS:
        print(f"{t}: street {street[t]:.4f} -> core {core[t]:.4f}  BPS_op {bps[t]:.3f}  ROE {roe[t]:.4f}  "
              f"payout {1 - b1[t]:.3f}  PE {pes[t]:.4f}x -> {ex_close[t]:.4f} x (1-k {k[t]:g}) + closing = {scen[t]:.4f}")
    print(f"deemed-distributed cash (actual retention {ret_actual:.1%} − b1) × FY26H2 unbooked → "
          f"{excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh (k = 0; disclosure only)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pes['M']:.2f}x (+closing): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"③ band not applicable (A10) — coordinates: E_M/r + closing {e_over_r:.2f}; "
          f"asset pb_low {inp['pb_low']:g} x BVPS {bvps:.2f} = {asset_coord:.2f}; "
          f"last-cycle trough (FY26 x {inp['eps_trough_ratio']:g} -> core {trough_core:.3f}) / r + closing = {trough_coord:.2f}")
    print(f"L/M {L / M:.3f} (ex-closing {ex_close['L'] / ex_close['M']:.3f}) | H/M {H / M:.3f} "
          f"(ex-closing {ex_close['H'] / ex_close['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M 0")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.2f}) -> {lo['L']:.2f}/{lo['M']:.2f}/{lo['H']:.2f}; +1pp exceeds cap {cap:.3f}")
    no_tp = [scen[t] - tp_ps for t in TIERS]
    pre_tax = [scen[t] - tp_ps + inp["tp_fv"] * MILLION / sh for t in TIERS]
    print(f"sensitivity Technoprobe excluded: {no_tp[0]:.2f}/{no_tp[1]:.2f}/{no_tp[2]:.2f}; "
          f"at pre-tax fair value: {pre_tax[0]:.2f}/{pre_tax[1]:.2f}/{pre_tax[2]:.2f}")
    for rr, tag in ((0.13, "篮 6 13% (not adopted)"), (0.15, "篮 7 15% (not adopted)")):
        _, _, _, s = deck(g2, rr)
        print(f"contrast r {tag}: {s['L']:.2f}/{s['M']:.2f}/{s['H']:.2f}")
    print(f"candidate (A13): g1 {g1:.4f} n=1 on M/H -> PE {cand_pe['M']:.2f}/{cand_pe['H']:.2f}x; "
          f"L′ {cand['L']:.2f} M′ {cand['M']:.2f} H′ {cand['H']:.2f}")
    for tp in (350.0, 450.0, 550.0):
        g_tp, ok = implied_g((tp - closing) / core["M"], roe["M"], r)
        print(f"street TP {tp:g} on this ruler (A14): implied perpetual g {g_tp:.4f}{'' if ok else ' (ill-conditioned)'}")

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1 — the only priced r; the
    # rolled ROE, g2, core numerator and closing items stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        s = [core[t] * perpetual_pe(g2, roe[t], r + dr) * (1.0 - k[t]) + closing for t in TIERS]
        return s[0], s[1], s[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("TER.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
