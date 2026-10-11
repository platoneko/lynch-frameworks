#!/usr/bin/env python3
"""HPE.US (Hewlett Packard Enterprise) valuation eval — recompute anchors from
frameworks/HPE.US.md.

frameworks/HPE.US.md is the source of truth; this script re-derives L/M/H /
A/B and the candidate band from the §3 Inputs table and exits 1 on mismatch.
The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here reads a quote.

formula_id: hpe_fy27_owner_eps_gordon_roic_trough_v1

Main ruler: whole company, one leg (basket 4).  Numerator year FY2027 (fiscal
year ending 2027-10) — the furthest year with a >=2-house consensus range.
Numerator = consensus non-GAAP EPS minus after-tax SBC per diluted share
("owner EPS"); amortisation of acquired intangibles stays added back (A3).

Leverage gate triggered (A9): interest incl. the captive-finance interest
booked in cost of sales and the mandatory-convertible preferred dividend is
> 1/3 of TTM GAAP EBIT.  So the retention branch runs on ROIC, not ROE:
ROIC_x = (owner NI_x + after-tax interest on all debt) / (equity + net debt).

M / H = FY27 consensus mean / high at Gordon g2 4% (named macro).
L = measured trough: Cloud & AI back to its FY25 margin and Networking to its
measured low, revenue held at FY26; treated as a point that recovers to the
FY24 like-for-like Cloud & AI margin over two years (recovery_two_stage_pe).
The regime reading (trough forever) is printed as the deep_discount pressure
coordinate.

Candidate band (A13): the company's Networking FY26-FY29 target as a two-year
transition on M / H (growth type); L′ = L.

Run:  python3 frameworks/eval/HPE.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    g_cap,
    payout,
    perpetual_pe,
    recovery_two_stage_pe,
    two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    outputs_section,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "HPE.US.md"
FORMULA_ID = "hpe_fy27_owner_eps_gordon_roic_trough_v1"
TICKER = "HPE.US"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")

REQUIRED = [
    "eps_fy27_m", "eps_fy27_h", "eps_fy27_lo",
    "sbc", "tax_ng", "shares_dil",
    "rev_cai_fy26", "rev_nw_fy26", "m_cai_trough", "m_cai_mid", "m_nw_low",
    "corp_oi", "other_int", "n_recovery",
    "equity", "net_debt", "debt_total", "int_debt", "int_fin", "pref_div", "ebit_ttm", "ebitda_ttm",
    "r_perp", "g2", "k_l", "k_m", "k_h", "payout_obs",
    "nw_g27", "nw_cagr_26_29", "nw_margin",
    "pe_own_lo", "pe_own_hi",
]

_CANDIDATE = re.compile(
    r"候选带（[^）]+）[^\n]*?L′ = \*\*([0-9.]+)\*\*[^\n]*?M′ = \*\*([0-9.]+)\*\*[^\n]*?H′ = \*\*([0-9.]+)\*\*"
)


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N (A2)")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    e += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        e.append(f"r - g2 < {MIN_R_MINUS_G:.0%}: at the pole")
    e += ladder("FY27 consensus range", inp["eps_fy27_lo"], inp["eps_fy27_m"], inp["eps_fy27_h"])
    e += ladder("Cloud & AI margin trough < mid", inp["m_cai_trough"], inp["m_cai_mid"])
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (留存去向审计, A10)")
    if not (0 <= inp["tax_ng"] < 0.25):
        e.append("tax_ng out of range")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


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
    errors = check_inputs(inp, baskets)
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2"]
    sh = inp["shares_dil"]  # 百万股; money inputs are 百万 USD
    at = 1 - inp["tax_ng"]
    sbc_ps = inp["sbc"] * at / sh

    # ---- Leverage gate (A9): both interest readings; build on the triggering one ----
    int_strict = inp["int_debt"] + inp["int_fin"] + inp["pref_div"]
    int_loose = inp["int_debt"] + inp["pref_div"]
    nd_ebitda = inp["net_debt"] / inp["ebitda_ttm"]
    gate = int_strict / inp["ebit_ttm"]
    if not (gate > 1 / 3 or nd_ebitda > 3):
        errors.append(f"leverage gate no longer triggers ({gate:.1%}, {nd_ebitda:.2f}x): rebuild on ROE (A9)")

    # ---- Step 1: owner EPS per tier (A3 / A5) ----
    def owner_eps(cai_margin: float, nw_margin: float) -> float:
        oi = (inp["rev_cai_fy26"] * cai_margin + inp["rev_nw_fy26"] * nw_margin
              + inp["corp_oi"] + inp["other_int"])
        return (oi * at - inp["sbc"] * at) / sh

    eps = {"L": owner_eps(inp["m_cai_trough"], inp["m_nw_low"]),
           "M": inp["eps_fy27_m"] - sbc_ps,
           "H": inp["eps_fy27_h"] - sbc_ps}
    eps_mid = owner_eps(inp["m_cai_mid"], inp["m_nw_low"])

    # ---- Step 2: ROIC (gate branch) ----
    ic = inp["equity"] + inp["net_debt"]
    int_at = (inp["int_debt"] + inp["int_fin"]) * at

    def roic(e: float) -> float:
        return (e * sh + int_at) / ic

    n = int(inp["n_recovery"])
    g1_rec = (eps_mid / eps["L"]) ** (1 / n) - 1
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    def multiples(rr: float, g: float = g2) -> dict[str, float]:
        return {"L": recovery_two_stage_pe(g1_rec, n, g, roic(eps_mid), rr),
                "M": perpetual_pe(g, roic(eps["M"]), rr),
                "H": perpetual_pe(g, roic(eps["H"]), rr)}

    def anchors_at(rr: float, g: float = g2) -> tuple[float, float, float]:
        pe_ = multiples(rr, g)
        return tuple(eps[t] * pe_[t] * (1 - k[t]) for t in TIERS)

    pe = multiples(r)
    L, M, H = anchors_at(r)
    A, B = cut_points(L, M, H)
    errors += ladder("anchors", L, M, H)
    for t in ("M", "H"):
        if roic(eps[t]) - r < 0.03:
            errors.append(f"{t}: ROIC {roic(eps[t]):.3f} not in the monotone domain at r {r:g}")
        errors += check_branch(g2, roic(eps[t]), r, inp["payout_obs"], f"g2@{t}")

    # ---- A2e-2c flat ladder + decomposition ----
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    dec = decompose((L, M, H), tuple(pe[t] * (1 - k[t]) for t in TIERS))

    # ---- Candidate band (A13): company Networking FY26-FY29 target, growth type ----
    nw27 = inp["rev_nw_fy26"] * (1 + inp["nw_g27"])
    nw29 = inp["rev_nw_fy26"] * (1 + inp["nw_cagr_26_29"]) ** 3
    d_eps = (nw29 - nw27) * inp["nw_margin"] * at / sh
    g1c = ((eps["M"] + d_eps) / eps["M"]) ** 0.5 - 1
    cand = {"L": L}
    for t in ("M", "H"):
        cand[t] = eps[t] * two_stage_pe(g1c, 2, g2, roic(eps[t]), r) * (1 - k[t])
    errors += ladder("candidate band", cand["L"], cand["M"], cand["H"])

    # ---- Reconcile stated Outputs ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    cm = _CANDIDATE.search(outputs_section(md))
    if cm is None:
        errors.append("candidate band line not found in Outputs")
    else:
        for t, said in zip(TIERS, (float(x) for x in cm.groups())):
            if abs(said - cand[t]) > TOL:
                errors.append(f"candidate {t}′: stated {said} vs recomputed {cand[t]:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r {r:g} (篮 {baskets['r_perp']}) g2 {g2:.2%} (named macro; cap {g_cap(r):.0%})")
    print(f"leverage gate: interest/EBIT strict {gate:.1%} (debt {inp['int_debt']:g} + captive finance "
          f"{inp['int_fin']:g} + preferred {inp['pref_div']:g}) | loose {int_loose / inp['ebit_ttm']:.1%}"
          f" | net debt/EBITDA {nd_ebitda:.2f}x -> ROIC branch")
    print(f"SBC/sh {sbc_ps:.4f} (SBC {inp['sbc']:g} x {at:.2f} / {sh:g}M sh)")
    print(f"IC {ic:,.0f} = equity {inp['equity']:,.0f} + net debt {inp['net_debt']:,.0f}; after-tax interest {int_at:.0f}")
    for t in TIERS:
        print(f"{t}: owner EPS {eps[t]:.4f} | ROIC {roic(eps[t]):.3f} ROE(book) {eps[t] * sh / inp['equity']:.3f}"
              f" | PE {pe[t]:.3f} -> {eps[t] * pe[t]:.2f} x (1-k {k[t]:.2f})")
    print(f"L recovery: trough {eps['L']:.4f} -> mid {eps_mid:.4f} over n={n} (g1 {g1_rec:+.2%}),"
          f" mid ROIC {roic(eps_mid):.3f} (payout {payout(g2, roic(eps_mid)):.3f})")
    print(f"L/M/H = {L:.2f}/{M:.2f}/{H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"flat ladder @ M {pe['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | H/M {dec['hm']:.3f}"
          f" = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M 0")
    regime_l = eps["L"] * perpetual_pe(g2, roic(eps["L"]), r)
    print(f"pressure coordinate (trough as regime): {regime_l:.2f}; E_M/r {eps['M'] / r:.2f}")
    print(f"candidate (Networking FY27 {nw27:,.0f} -> FY29 {nw29:,.0f} at {inp['nw_margin']:.0%}:"
          f" +{d_eps:.3f}/sh, g1 {g1c:+.2%} n=2): L′ {cand['L']:.2f} M′ {cand['M']:.2f} H′ {cand['H']:.2f}"
          f"  A′ {(cand['L'] + cand['M']) / 2:.2f} B′ {(cand['M'] + cand['H']) / 2:.2f}")
    m_ng = M / inp["eps_fy27_m"]
    print(f"③ own forward band [{inp['pe_own_lo']:g}, {inp['pe_own_hi']:g}]x non-GAAP; M = {m_ng:.2f}x"
          f" -> {'below band' if m_ng < inp['pe_own_lo'] else 'not below band'}")
    for g in (g2 - 0.01, g2 + 0.01):
        v = anchors_at(r, g)
        print(f"  sens g2={g:.2%}: {v[0]:.2f}/{v[1]:.2f}/{v[2]:.2f}")
    loose_ic_roe = {t: eps[t] * sh / inp["equity"] for t in ("M", "H")}
    print("  ROE branch (gate read loosely): "
          + "/".join(f"{eps[t] * perpetual_pe(g2, loose_ic_roe[t], r):.2f}" for t in ("M", "H")))
    d100 = inp["debt_total"] * 0.01 * at / sh
    print(f"  +100bp on total debt: EPS -{d100:.3f}/sh -> M {(eps['M'] - d100) * pe['M']:.2f}")

    # r_f readings (_AXIS.rates USD): Δr_f moves r_perp 1:1; numerators, g2, ROIC stay put.
    rf = rf_block(LISTING_CCY, {"r_perp": r}, lambda dr: anchors_at(r + dr))
    if any(abs(x - y) > TOL for x, y in zip(anchors_at(r), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
