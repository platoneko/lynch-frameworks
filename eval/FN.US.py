#!/usr/bin/env python3
"""FN.US (Fabrinet) valuation eval — recompute anchors from frameworks/FN.US.md.

frameworks/FN.US.md is the source of truth; this script re-derives L/M/H /
A/B and the candidate band from the §3 Inputs table and exits 1 on mismatch.
The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here reads a quote.

formula_id: fn_sotp_ai_auto_fy28_econ_eps_gordon_disc_v1

Main ruler: two-leg SOTP on FY2028 (fiscal year ending ~2028-06).  The company
discloses revenue by end market only (one reportable segment, no segment
profit), so the economic EPS is split between the legs pro rata to revenue at
one margin (A1 / A5).
  - economic EPS = consensus non-GAAP EPS x (1 - Pillar Two share) - SBC/share
    (A6).  Pillar Two share = Q1 FY27 guided Pillar Two tax / guided non-GAAP
    EPS midpoint; SBC for the year = max(Q1 FY27 guided SBC/share x guided
    shares x 4, FY26 SBC/revenue x the tier's revenue).  No tax shield (A6).
  - L = FY28 digestion year (revenue and non-GAAP EPS stay at FY27 consensus);
    M / H = FY28 consensus mean / high (A7).
  - Auto & industrial leg revenue = FY26 x (1 + latest YoY)^2, flat across
    tiers; the rest is the AI-optical leg (A5).
Multiples: perpetual Gordon at r 10% (basket 4, both legs); AI-optical g2 from
the contract-manufacturer peer cross-section (A9), auto & industrial g2 =
named macro 4% (A10).  ROE = FY28 EPS / FY28 opening book, the FY26 book
rolled over the unbooked FY27 (consensus x (1 - Pillar Two share)) at the
growth-required retention b = g/ROE with g = the EPS-weighted company g,
closed form BPS = BPS0 / (1 - g N / EPS) (A11).  The FY28 sum sits at
2027-06-30 and is discounted t_disc years at r_disc, then net cash/share is
added.  k = 0 (A12).

Candidate band (A22, never a base anchor): Building 10 capacity as a one-year
FY29 transition on the AI leg of M / H, g1 = added capacity / the tier's FY28
AI-leg revenue; the book is rolled at the g1-weighted company g, uncapped
(retention > 1 = growth needs more capital than the year earns, charged as
external funding); L' = L.

Run:  python3 frameworks/eval/FN.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_capex_mount  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    g_cap,
    implied_g,
    payout,
    perpetual_pe,
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
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "FN.US.md"
FORMULA_ID = "fn_sotp_ai_auto_fy28_econ_eps_gordon_disc_v1"
TICKER = "FN.US"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")
WINDOW_YEARS = 2  # D-bucket window FY27-FY28 (Building 10 build + ramp, A12)

REQUIRED = [
    "eps_fy27_m", "rev_fy27_cons",
    "eps_fy28_l", "eps_fy28_m", "eps_fy28_h", "rev_fy28_l", "rev_fy28_m", "rev_fy28_h",
    "p2_q1_guide", "eps_ng_q1_guide", "sbc_q1_guide", "shares_guide",
    "sbc_ps_fy26", "shares_fy26", "rev_fy26", "warrant_unvested", "warrant_tsm",
    "equity_fy26", "cash_st", "debt", "rev_auto_fy26", "g_auto_yoy",
    "r_perp", "g2_ai", "g2_auto", "r_disc", "t_disc", "k_l", "k_m", "k_h", "payout_obs",
    "pe_own_min", "pe_own_max", "cap_add_m", "cap_add_h", "plug_share", "g2_plug",
    "capex_l", "capex_m", "capex_h",
]


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N (A4)")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    if "r_disc" in baskets:
        e.append("r_disc is a year-drift discount, its row MUST NOT name a basket")
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-12:
        e.append("r_disc must equal r_perp")
    for leg in ("g2_ai", "g2_auto"):
        e += check_g_cap(inp[leg], inp["r_perp"], leg)
        if inp["r_perp"] - inp[leg] < MIN_R_MINUS_G:
            e.append(f"r - {leg} < {MIN_R_MINUS_G:.0%}: at the pole")
        if inp[leg] <= 0:
            e.append(f"{leg} <= 0 barred: FY27 -> FY28 consensus rises (同世界门, A9/A10)")
    e += ladder("FY28 EPS consensus range", inp["eps_fy28_l"], inp["eps_fy28_m"], inp["eps_fy28_h"])
    e += ladder("FY28 revenue consensus range", inp["rev_fy28_l"], inp["rev_fy28_m"], inp["rev_fy28_h"])
    e += ladder("tier non-GAAP EPS", inp["eps_fy27_m"], inp["eps_fy28_m"], inp["eps_fy28_h"])
    e += ladder("tier revenue", inp["rev_fy27_cons"], inp["rev_fy28_m"], inp["rev_fy28_h"])
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (A12)")
    if not (0 < inp["warrant_tsm"] <= 1):
        e.append("warrant_tsm must be in (0, 1]")
    if inp["cash_st"] - inp["debt"] < 0:
        e.append("closing item is net cash by construction (A13); net debt would need the leverage gate")
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
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))
    if errors:
        return report(errors)

    r = inp["r_perp"]
    g_ai, g_au = inp["g2_ai"], inp["g2_auto"]
    p2 = inp["p2_q1_guide"] / inp["eps_ng_q1_guide"]
    sh = inp["shares_guide"] + inp["warrant_unvested"] * inp["warrant_tsm"]  # 百万股
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    # ---- Step 1: FY28 economic EPS and the leg split (A5 / A6 / A7) ----
    sbc_floor = inp["sbc_q1_guide"] * inp["shares_guide"] * 4
    sbc_ratio = inp["sbc_ps_fy26"] * inp["shares_fy26"] / inp["rev_fy26"]
    rev = {"L": inp["rev_fy27_cons"], "M": inp["rev_fy28_m"], "H": inp["rev_fy28_h"]}
    ng = {"L": inp["eps_fy27_m"], "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}
    sbc = {t: max(sbc_floor, sbc_ratio * rev[t]) for t in TIERS}
    eps = {t: ng[t] * (1 - p2) - sbc[t] / sh for t in TIERS}
    rev_auto = inp["rev_auto_fy26"] * (1 + inp["g_auto_yoy"]) ** 2
    eps_au = {t: eps[t] * rev_auto / rev[t] for t in TIERS}
    eps_ai = {t: eps[t] - eps_au[t] for t in TIERS}

    # ---- Step 2: FY28 opening book (A11) ----
    bps0 = inp["equity_fy26"] / sh
    unbooked = inp["eps_fy27_m"] * (1 - p2)
    disc = (1 + inp["r_disc"]) ** (-inp["t_disc"])
    net_cash = (inp["cash_st"] - inp["debt"]) / sh

    def book(e: float, g_co: float, capped: bool = False) -> tuple[float, float]:
        if capped:  # CRDO-style roll, retention capped at 1 (A22 unadopted reference)
            bps = bps0 + unbooked
            for _ in range(500):
                bps = bps0 + unbooked * min(1.0, g_co / (e / bps))
            return bps, e / bps
        x = g_co * unbooked / e
        if x >= 1:
            raise ValueError(f"opening-book roll diverges: g·N/EPS = {x:.3f} >= 1")
        bps = bps0 / (1 - x)
        return bps, e / bps

    def legs(t: str, rr: float, rd: float, gai: float = g_ai, gau: float = g_au) -> dict[str, float]:
        g_co = (eps_ai[t] * gai + eps_au[t] * gau) / eps[t]
        bps, roe = book(eps[t], g_co)
        pe_ai, pe_au = perpetual_pe(gai, roe, rr), perpetual_pe(gau, roe, rr)
        dsc = (1 + rd) ** (-inp["t_disc"])
        v_ai, v_au = eps_ai[t] * pe_ai * dsc, eps_au[t] * pe_au * dsc
        return {"g_co": g_co, "bps": bps, "roe": roe, "pe_ai": pe_ai, "pe_au": pe_au,
                "v_ai": v_ai, "v_au": v_au, "sum": eps_ai[t] * pe_ai + eps_au[t] * pe_au,
                "anchor": (v_ai + v_au) * (1 - k[t]) + net_cash}

    s = {t: legs(t, r, inp["r_disc"]) for t in TIERS}
    L, M, H = (s[t]["anchor"] for t in TIERS)
    A, B = cut_points(L, M, H)
    errors += ladder("anchors", L, M, H)
    for t in TIERS:
        if s[t]["roe"] - r < 0.03:
            errors.append(f"{t}: ROE {s[t]['roe']:.3f} not in the monotone domain at r {r:g}")
        errors += check_branch(g_ai, s[t]["roe"], r, inp["payout_obs"], f"g2_ai@{t}")
        errors += check_branch(g_au, s[t]["roe"], r, inp["payout_obs"], f"g2_auto@{t}")

    # ---- A2e-2c flat ladder (both legs held at their M multiples) + decomposition ----
    flat_errs, _ = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), s["M"]["sum"] / eps["M"])
    errors += flat_errs
    flat = tuple((eps_ai[t] * s["M"]["pe_ai"] + eps_au[t] * s["M"]["pe_au"]) * disc + net_cash for t in TIERS)
    errors += ladder("flat-multiple anchors", *flat)
    blend = tuple(s[t]["sum"] / eps[t] for t in TIERS)
    dec = decompose((L, M, H), blend)

    # ---- Candidate band (A22): Building 10 as a one-year FY29 transition on the AI leg ----
    g1 = {"M": inp["cap_add_m"] / (rev["M"] - rev_auto), "H": inp["cap_add_h"] / (rev["H"] - rev_auto)}
    cand = {"L": L}
    cand_info: dict[str, tuple[float, float, float]] = {}
    cand_capped = {"L": L}
    for t in ("M", "H"):
        g_co1 = (eps_ai[t] * g1[t] + eps_au[t] * g_au) / eps[t]
        for capped in (False, True):
            _, roe1 = book(eps[t], g_co1, capped)
            v = (eps_ai[t] * two_stage_pe(g1[t], 1, g_ai, roe1, r)
                 + eps_au[t] * perpetual_pe(g_au, roe1, r)) * disc * (1 - k[t]) + net_cash
            if capped:
                cand_capped[t] = v
            else:
                cand[t] = v
                cand_info[t] = (roe1, g1[t] / roe1, g_co1)
    errors += ladder("candidate band", cand["L"], cand["M"], cand["H"])

    # ---- Reconcile stated Outputs ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    meta = load_framework(FRAMEWORK)
    if meta.candidate is None:
        errors.append("candidate band line not found in Outputs")
    else:
        for t, said in zip(TIERS, meta.candidate):
            if abs(said - cand[t]) > TOL:
                errors.append(f"candidate {t}′: stated {said} vs recomputed {cand[t]:.4f}")
    if "候选带" not in outputs_section(md):
        errors.append("candidate band must be stated in Outputs")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r {r:g} (篮 {baskets['r_perp']}) | g2 AI {g_ai:.2%} (peer cross-section) | g2 auto {g_au:.2%}"
          f" (named macro) | cap {g_cap(r):.0%}")
    print(f"Pillar Two share {p2:.4%} | shares {sh:.4f}M | SBC = max(guide x4 {sbc_floor:.2f}, FY26 ratio"
          f" {sbc_ratio:.4%} x revenue): " + " ".join(f"{t} {sbc[t]:.2f}" for t in TIERS) + " $M")
    print(f"auto leg FY28 revenue {rev_auto:.2f} | BPS0 {bps0:.3f} | unbooked FY27 {unbooked:.4f}"
          f" | disc {disc:.4f} | net cash/sh {net_cash:.3f}")
    for t in TIERS:
        d = s[t]
        print(f"{t}: econ EPS {eps[t]:.4f} (AI {eps_ai[t]:.4f} / auto {eps_au[t]:.4f}) | g_co {d['g_co']:.4%}"
              f" BPS_open {d['bps']:.3f} ROE {d['roe']:.4f} | PE AI {d['pe_ai']:.3f} (payout"
              f" {payout(g_ai, d['roe']):.3f}) auto {d['pe_au']:.3f} | disc AI {d['v_ai']:.2f} auto"
              f" {d['v_au']:.2f} + cash {net_cash:.2f} = {d['anchor']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat ladder @ M leg multiples: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {dec['lm']:.3f} = num {eps['L'] / eps['M']:.3f} x pe {dec['pe_lm']:.3f} (residual num"
          f" {dec['num_lm']:.3f}, net cash folded in) | H/M {dec['hm']:.3f} = num {eps['H'] / eps['M']:.3f}"
          f" x pe {dec['pe_hm']:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M 0")
    print("candidate (Building 10, FY29 one-year transition, uncapped roll): "
          f"L′ {cand['L']:.2f} M′ {cand['M']:.2f} H′ {cand['H']:.2f}; "
          + " ".join(f"{t} g1 {g1[t]:.4%} ROE {cand_info[t][0]:.4f} b1 {cand_info[t][1]:.2f}" for t in ("M", "H"))
          + "  [b1 > 1: growth needs more capital than the year earns -> external funding charged]")
    print(f"  unadopted capped roll (CRDO style): M′ {cand_capped['M']:.2f} H′ {cand_capped['H']:.2f}")

    # ③ guardrail — own current-year forward PE band, same basis (A15).
    for t in TIERS:
        same = (s[t]["anchor"] - net_cash) / disc / ng[t]
        inside = inp["pe_own_min"] <= same <= inp["pe_own_max"]
        print(f"③ {t}: (anchor - net cash)/disc / non-GAAP {ng[t]:g} = {same:.2f}x"
              f" -> {'inside' if inside else 'OUTSIDE'} [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]")
        if t == "M" and not inside:
            errors.append(f"③: M same-basis multiple {same:.2f}x outside own band — BLOCKED path, not a disclosure")
    for t in TIERS:
        g_lo, ok = implied_g(inp["pe_own_min"] * ng[t] / eps[t], s[t]["roe"], r)
        print(f"  band-low edge implied g @ {t} (on econ EPS): {g_lo:+.2%}{'' if ok else ' (ill-conditioned)'}")
    print("视同派出、实际留存 (k 前 / k 后, $/股; per year on FY28 EPS, x window "
          f"{WINDOW_YEARS}y FY27-FY28): "
          + " ".join(f"{t} {(1 - inp['payout_obs'] - s[t]['g_co'] / s[t]['roe']) * eps[t]:.2f}"
                     f"/{(1 - inp['payout_obs'] - s[t]['g_co'] / s[t]['roe']) * eps[t] * (1 - k[t]):.2f}"
                     f" (window {(1 - inp['payout_obs'] - s[t]['g_co'] / s[t]['roe']) * eps[t] * WINDOW_YEARS:.2f})"
                     for t in TIERS))

    # Sensitivities the doc quotes (只报 L/M/H).
    def band(gai: float = g_ai, gau: float = g_au) -> tuple[float, ...]:
        return tuple(legs(t, r, inp["r_disc"], gai, gau)["anchor"] for t in TIERS)

    for label, g in (("-1pp", g_ai - 0.01), ("+1pp", g_ai + 0.01), ("evidence low (JBL)", 0.0286),
                     ("evidence high (CLS)", 0.0525), ("cap 6% (unadopted)", g_cap(r))):
        print(f"  sens g2_ai {label} {g:.2%}: " + "/".join(f"{x:.2f}" for x in band(g)))
    for label, g in (("-1pp", g_au - 0.01), ("+1pp", g_au + 0.01)):
        print(f"  sens g2_auto {label} {g:.2%}: " + "/".join(f"{x:.2f}" for x in band(g_ai, g)))

    # Street basis: no Pillar Two, no SBC deduction (A6).
    street = []
    for t in TIERS:
        e = ng[t]
        ea = e * rev_auto / rev[t]
        ei = e - ea
        gco = (ei * g_ai + ea * g_au) / e
        bps = bps0 / (1 - gco * inp["eps_fy27_m"] / e)
        roe = e / bps
        street.append((ei * perpetual_pe(g_ai, roe, r) + ea * perpetual_pe(g_au, roe, r)) * disc * (1 - k[t]) + net_cash)
    print("  street basis (no Pillar Two, no SBC): " + "/".join(f"{x:.2f}" for x in street))

    # Pluggable split (A21): plug_share of total revenue at g2_plug, rest of the AI leg at g2_ai.
    plug = []
    for t in TIERS:
        e_pl = eps[t] * inp["plug_share"]
        e_rest = eps_ai[t] - e_pl
        gco = (e_pl * inp["g2_plug"] + e_rest * g_ai + eps_au[t] * g_au) / eps[t]
        _, roe = book(eps[t], gco)
        v = (e_pl * perpetual_pe(inp["g2_plug"], roe, r) + e_rest * perpetual_pe(g_ai, roe, r)
             + eps_au[t] * perpetual_pe(g_au, roe, r)) * disc * (1 - k[t]) + net_cash
        plug.append(v)
    print(f"  pluggable {inp['plug_share']:.0%} of revenue at g2 {inp['g2_plug']:.0%}, rest of AI leg"
          f" {g_ai:.1%}: " + "/".join(f"{x:.2f}" for x in plug)
          + "  (AI-leg share " + "/".join(f"{inp['plug_share'] / ((rev[t] - rev_auto) / rev[t]):.1%}" for t in TIERS) + ")")

    # Cross-checks.
    peg = s["M"]["pe_ai"] / ((inp["eps_fy28_m"] / inp["eps_fy27_m"] - 1) * 100)
    print(f"PEG (M AI-leg PE / FY27->FY28 non-GAAP growth {inp['eps_fy28_m'] / inp['eps_fy27_m'] - 1:.2%}): {peg:.2f}")
    print("capex axis implied share (wide, AI leg FY28 revenue): "
          + " ".join(f"{t} {(rev[t] - rev_auto) * 1e6 / inp[f'capex_{t.lower()}']:.2%}" for t in TIERS))

    # r_f readings (_AXIS.rates USD): Δr_f moves r_perp and r_disc 1:1; numerators, g, book stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        out = [legs(t, r + dr, inp["r_disc"] + dr)["anchor"] for t in TIERS]
        return out[0], out[1], out[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r, "r_disc": inp["r_disc"]}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
