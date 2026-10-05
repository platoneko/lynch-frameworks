#!/usr/bin/env python3
"""AEHR.US valuation eval — recompute anchors from frameworks/AEHR.US.md.

formula_id: aehr_fy28_cons_gordon_opeq_v7

One operating leg on the FY28 consensus EPS range (3 houses; the furthest year
with a >=2-house *range*, valuation-rules 裁决顺序 ②).  Street EPS is the
company's normalized (ex-SBC) figure, so every tier is haircut by the SBC
share of FY28 consensus NI before it becomes an economic EPS; the haircut is
derived from the GAAP-vs-normalized consensus gap net of acquisition
amortisation (A9).  Multiples are generated, not borrowed:
`perpetual_pe(g2, ROE_x, r)` with g2 = the test-equipment peer cluster's
reverse-solved median truncated to g_cap(r) (A5), r = 10% — the whole company
is one leg in basket 4 常规经营 (an equipment maker whose earnings follow its
customers' capex projects, not a commodity price; size and customer
concentration price into the L numerator and p_k, not r — valuation-rules
「§r 篮子」 2026-09-28, A17; basket 7 is the named alternative, its
single-customer threshold unmet, A12) — and tier ROE = FY28 core EPS over the FY28 OPENING
*operating* book: book equity less net cash at FY26 year-end (2026-05-29, the
latest balance sheet), rolled over the whole FY27 consensus not yet booked (no
FY27 quarter reported yet) at the growth-required retention b1 = g2/ROE — no
g1 window, so every tier rolls at g2 (valuation-rules 2026-09-21, A18).  The
after-tax interest the consensus EPS earns on that cash is stripped from the
numerator and the net cash added back per share as a closing item (A15, the
1810.HK A15 treatment).  FY29 has no >=2-house consensus anywhere, so there is
no g1 and no discount (FY28 = current FY + 1).

L is the scenario value; the tangible-book PB floor is only disclosed, never
max()'d in (A10).  The A2e-1 ratio scenario_L / M is printed and guarded
(>= 0.3) should the scenario ever drop below the floor.  Guardrail (③): the own realised band divides
close by the *current-FY* consensus, so anchors are compared to it on that
same basis (anchor / FY27 consensus) — only the lower edge binds, the upper
edge is meaningless (2025-26 consensus EPS ~ 0).

V_opt (valuation-rules「未建模期权」2026-10-05, A14; peer ruler _AXIS.burn-in-test):
tiered quantities.  No covering house sizes any of the excluded items, so L / M
fall back to named quantities — L = one snapshot of the lead wafer-level AI
customer (its signed orders over the last 12 months) for the unsigned second AI
processor customer; M = L + SiC back to its FY24 peak (FY24 EV/power revenue
less the FY26 level the consensus is taken to carry) — on the FY28 (aligned
year) M-tier consensus core net margin.  H is demand-side, NOT management's
theoretical capacity (the rule: full capacity caps H only when capacity is
capital-bound; AEHR is capital-light — FY26 capex $2.1M, contract-built
Sonoma): the highest sell-side path (Freedom Broker FY30 revenue; Oppenheimer
FY28 is the high FY28 point) less what the H-tier FY28 consensus already
carries by FY30 (grown at g2), plus the named items both covering houses
exclude (second AI customer snapshot, SiC peak).  Its unit economics are the
two-period incremental margin (FY26 actual vs FY28 M consensus non-GAAP
operating profit), the implied operating margin at that scale bounded by the
axis peer range.  Every tier is valued on this ticker's ruler in FY30 —
perpetual_pe(axis g2, success-world ROE, basket r), the base book and earnings
grown at g2 to FY30 and the denominator growing with the quantity at the
H-tier operating-capital / revenue ratio (mostly inventory and receivables) —
less that extra operating capital and any committed-unspent capex, discounted
back to FY28.  V_opt = V_H; p_k = V_k / V_H.  The CEO's theoretical capacity
($1,440M/yr) is printed as a reading only.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」): which zone a
quote falls in is derived live by the daily digest and the app, so nothing
here reads a price.

Run:  python3 frameworks/eval/AEHR.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import axis_path, check_capex_mount  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    g_cap,
    implied_g,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "AEHR.US.md"
FORMULA_ID = "aehr_fy28_cons_gordon_opeq_v7"
LISTING_CCY = "USD"
TOL = 0.05
MILLION = 1e6  # money inputs are in $M, share counts are absolute
MIN_R_MINUS_G = 0.02  # valuation-rules: below this the multiple sits at the pole
FLOOR_RATIO_MIN = 0.3  # A2e-1: scenario below the floor AND scenario_L / M below this -> back to dialogue
HAIRCUT_ROUNDING = 0.01  # A9: haircut may be rounded up by at most 1pp over the derived value
BIT_AXIS = axis_path("_AXIS.burn-in-test")
BIT_SHARED = ("g2_bit_src", "bit_opm_weak", "bit_opm_strong")  # rows that must equal the axis file
P_TOL = 5e-4  # stated p_k (4 dp) vs V_k / V_H
CAND_DISC_YEARS = 2  # A19: FY30 sits two years past the undiscounted FY28 numerator
NUM_YEAR = 2028  # FY28 numerator (t = 1, undiscounted); the option is discounted from t_opt back to here (A14)

REQUIRED = [
    "shares",
    "shares_basic",
    "equity",
    "cash",
    "net_cash",
    "cash_yield",
    "tangible_book",
    "pb_floor",
    "eps_fy27_m",
    "payout_3y",
    "eps_fy28_l",
    "eps_fy28_m",
    "eps_fy28_h",
    "eps_fy28_gaap_m",
    "rev_fy28_l",
    "rev_fy28_m",
    "rev_fy28_h",
    "rev_fy30_fb",
    "rev_fy28_opp",
    "sbc_fy26",
    "amort_fy26",
    "tax",
    "sbc_haircut",
    "r_perp",
    "g2",
    "g2_bit_src",
    "bit_opm_weak",
    "bit_opm_strong",
    "pe_own_min",
    "pe_own_p5",
    "pe_own_p50",
    "unit_rev",
    "unit_gp",
    "unit_opex",
    "opt_rev_ai",
    "sic_share_fy24",
    "rev_fy26",
    "sic_share_fy26",
    "t_opt",
    "fox_units_m",
    "fox_asp",
    "sonoma_units_m",
    "sonoma_asp",
    "op_gaap_fy26",
    "restr_fy26",
    "capex_committed",
    "capex_l",
    "capex_m",
    "capex_h",
]
TIERS = ("L", "M", "H")


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def derived_haircut(inp: dict[str, float]) -> tuple[float, float]:
    """A9: SBC share of FY28 normalized NI, from the GAAP-vs-normalized consensus gap.

    The gap is after tax and also carries acquisition amortisation, which the
    framework does not deduct, so that piece comes out first.  Returns
    (haircut, implied pre-tax FY28 SBC in $M) — the latter is printed against
    FY26 actual SBC as a plausibility read.
    """
    ni_norm = inp["eps_fy28_m"] * inp["shares"] / MILLION
    gap = (inp["eps_fy28_m"] - inp["eps_fy28_gaap_m"]) * inp["shares"] / MILLION
    sbc_after_tax = gap - inp["amort_fy26"] * (1.0 - inp["tax"])
    return sbc_after_tax / ni_norm, sbc_after_tax / (1.0 - inp["tax"])


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A17: one leg, r is the basket's value; the basket is named in the Inputs source cell.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A17)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    # A5: g2 is the peer median truncated to g_cap(r) — the truncation is a fact to check.
    cap = g_cap(inp["r_perp"])
    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if abs(inp["g2"] - min(inp["g2_bit_src"], cap)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(_AXIS.burn-in-test median {inp['g2_bit_src']:.4f}, cap {cap:.3f}) — A5")
    # _AXIS.burn-in-test: shared rows must equal the axis file (单改一边即红).
    if BIT_AXIS.is_file():
        peer = parse_inputs(BIT_AXIS.read_text(encoding="utf-8"))
        for k in BIT_SHARED:
            if k not in peer or abs(peer[k] - inp[k]) > 1e-9:
                errs.append(f"{k} {inp[k]:g} != _AXIS.burn-in-test {peer.get(k)} — the leg ruler drifted")
    else:
        errs.append("frameworks/axes/burn-in-test.md missing — leg ruler unchecked")
    gap = inp["r_perp"] - inp["g2"]
    if gap <= 0:
        errs.append("perpetuity diverges: g2 >= r")
    elif gap < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # 裁决顺序 ④ 同世界门: own consensus FY27 -> FY28 is up, so a g2 >= 0 source is admissible.
    if not inp["eps_fy27_m"] < inp["eps_fy28_l"]:
        errs.append("FY27 consensus not below FY28 low: the same-world gate for a g2 >= 0 source no longer holds (A5)")
    if inp["g2"] < 0:
        errs.append("g2 < 0 contradicts an upward FY27->FY28 consensus (同世界门)")

    # A2e-2a: one consensus range, three points on it.
    errs += ladder("numerator", inp["eps_fy28_l"], inp["eps_fy28_m"], inp["eps_fy28_h"])

    # A9: the haircut is derived from the GAAP consensus gap, then rounded up by at most 1pp.
    derived, sbc_fy28 = derived_haircut(inp)
    if not (derived - 1e-9 <= inp["sbc_haircut"] <= derived + HAIRCUT_ROUNDING + 1e-9):
        errs.append(f"sbc_haircut={inp['sbc_haircut']:.4f} outside [derived {derived:.4f}, +{HAIRCUT_ROUNDING:.2f}] (A9)")
    if sbc_fy28 < inp["sbc_fy26"]:
        errs.append(f"GAAP gap implies FY28 SBC {sbc_fy28:.2f}M below FY26 actual {inp['sbc_fy26']:g}M — consensus lines inconsistent, re-source (A9)")

    # A15: the closing item must be what the equity field is net of.
    if not 0 < inp["net_cash"] <= inp["cash"]:
        errs.append(f"net_cash {inp['net_cash']} must be positive and <= cash {inp['cash']} (A15)")
    if inp["equity"] - inp["net_cash"] <= 0:
        errs.append("operating equity (equity - net_cash) is not positive (A15)")

    # A14: the option is realised after the numerator year; the SiC item must be positive.
    if inp["t_opt"] <= NUM_YEAR:
        errs.append("option year must lie after the FY28 numerator year (A14)")
    if inp["unit_rev"] * inp["sic_share_fy24"] <= inp["rev_fy26"] * inp["sic_share_fy26"]:
        errs.append("SiC item: FY24 peak not above the FY26 level the consensus carries (A14)")

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
    # Demand-side mount on the AI-capex axis (share is immaterial, rungs still must match).
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))

    r, g2 = inp["r_perp"], inp["g2"]
    cap = g_cap(r)
    street = {"L": inp["eps_fy28_l"], "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}

    # ---- Step 1-2: economic EPS, then core EPS with the cash interest stripped (A9, A15) ----
    eps = {t: street[t] * (1.0 - inp["sbc_haircut"]) for t in TIERS}
    int_ps = inp["cash"] * inp["cash_yield"] * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    core = {t: eps[t] - int_ps for t in TIERS}

    # ---- Step 3-4: tier ROE = E_FY28 / opening-FY28 operating book, Gordon multiple, cash added back ----
    # The FY26 year-end operating book (latest balance sheet) is rolled over the
    # FY27 consensus not yet booked — the whole year, on the same core basis
    # (haircut, interest stripped) — at the growth-required retention b1 =
    # g2/ROE (no g1 window, A18).  ROE and BPS depend on each other; closed form
    # BPS = BPS0 / (1 - g2·N/core).  A diverging roll (g2·N/core >= 1) stops.
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] * MILLION / inp["shares"]
    bps_op_fy26 = equity_op * MILLION / inp["shares"]
    unbooked = inp["eps_fy27_m"] * (1.0 - inp["sbc_haircut"]) - int_ps  # FY27 core EPS, all of it still unbooked

    def opening_bps(core_x: float, g: float) -> float:
        share = g * unbooked / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps_op_fy26 / (1.0 - share)

    def rolled_roe(g: float) -> dict[str, float]:
        return {t: core[t] / opening_bps(core[t], g) for t in TIERS}

    roe = rolled_roe(g2)
    b1 = {t: g2 / roe[t] for t in TIERS}
    roe_fy26 = {t: core[t] * inp["shares"] / (equity_op * MILLION) for t in TIERS}  # old basis, printed only
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in TIERS}  # disclosure only
    pes = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    ex_cash = {t: core[t] * pes[t] for t in TIERS}
    scen = {t: ex_cash[t] + cash_ps for t in TIERS}

    # ---- Step 5: anchors, cut points; the floor is disclosed only (A10) ----
    tbvps = inp["tangible_book"] * MILLION / inp["shares_basic"]
    floor = inp["pb_floor"] * tbvps
    below_floor = scen["L"] < floor
    L, M, H = scen["L"], scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)
    floor_ratio = scen["L"] / M
    if below_floor and floor_ratio < FLOOR_RATIO_MIN:
        errors.append(f"A2e-1: scenario L below floor and scenario_L/M = {floor_ratio:.2f} < {FLOOR_RATIO_MIN} — earnings ruler failed at L, back to dialogue")

    # ---- Guardrail (裁决顺序 ③), on the band's own basis ----
    # The band is close / current-FY (FY27) consensus, so the anchor is divided by
    # the same denominator; the FY28-numerator Gordon multiples are a different
    # basis and are only printed.  Only the lower edge binds (A8).
    band_basis = {t: scen[t] / inp["eps_fy27_m"] for t in TIERS}
    for t in TIERS:
        if band_basis[t] < inp["pe_own_min"]:
            errors.append(f"{t} anchor / FY27 consensus = {band_basis[t]:.1f}x below own band lower edge {inp['pe_own_min']:g}")

    def band_edge_g(target_pe: float) -> tuple[float, bool]:
        """g at M-tier ROE that puts M / FY27 consensus on `target_pe` (evidence, never an input)."""
        pe_needed = (target_pe * inp["eps_fy27_m"] - cash_ps) / core["M"]
        return implied_g(pe_needed, roe["M"], r)

    edges = {k: band_edge_g(inp[f"pe_own_{k}"]) for k in ("min", "p5", "p50")}
    pe_m_cap = perpetual_pe(cap, roe["M"], r)

    # ---- A2e-2c flat ladder + A2e-5 decomposition (both on the ex-cash earnings term) ----
    if not (core["L"] < core["M"] < core["H"]):
        errors.append(f"numerator ladder broken: core EPS {core['L']:.3f}/{core['M']:.3f}/{core['H']:.3f} (A2e-2c)")
    flat = [core[t] * pes["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    num_lm, num_hm = core["L"] / core["M"], core["H"] / core["M"]
    pe_lm, pe_hm = pes["L"] / pes["M"], pes["H"] / pes["M"]

    # ---- g2 leverage (valuation-rules「g₂ 的杠杆 MUST 显式」): -1pp disclosed (L/M/H only); +1pp breaks ① ----
    def deck_at(g: float) -> tuple[float, float, float, bool]:
        roe_g = rolled_roe(g)  # the book rolls at the g being tested
        s = {t: core[t] * perpetual_pe(g, roe_g[t], r) + cash_ps for t in TIERS}
        return s["L"], s["M"], s["H"], s["L"] < s["M"] < s["H"]

    lo_l, lo_m, lo_h, lo_ok = deck_at(g2 - 0.01)

    # ---- Option tiers and zone+V (probabilities only here; A14, _AXIS.burn-in-test) ----
    rev28 = {"L": inp["rev_fy28_l"], "M": inp["rev_fy28_m"], "H": inp["rev_fy28_h"]}
    margin = {t: core[t] * inp["shares"] / MILLION / rev28[t] for t in TIERS}
    sic_peak = inp["unit_rev"] * inp["sic_share_fy24"]
    sic_in = inp["rev_fy26"] * inp["sic_share_fy26"]
    sic_item = sic_peak - sic_in
    cap_rev = 12.0 * (inp["fox_units_m"] * inp["fox_asp"] + inp["sonoma_units_m"] * inp["sonoma_asp"])  # reading only
    disc_n = int(inp["t_opt"]) - NUM_YEAR
    grow = (1.0 + g2) ** disc_n  # the deck's H tier already carries FY28 x (1+g2)^n by the option year
    base_rev = rev28["H"] * grow
    if inp["rev_fy28_opp"] < rev28["H"] or inp["rev_fy30_fb"] <= base_rev:
        errors.append("highest sell-side path must sit above the H-tier consensus (A14)")
    path_xs = inp["rev_fy30_fb"] - base_rev
    path_fy29 = (inp["rev_fy28_opp"] * inp["rev_fy30_fb"]) ** 0.5  # interpolated, disclosure only
    qty = {"L": inp["opt_rev_ai"], "M": inp["opt_rev_ai"] + sic_item, "H": path_xs + inp["opt_rev_ai"] + sic_item}
    scale = base_rev + qty["H"]
    if scale > cap_rev:
        errors.append(f"H-world revenue {scale:.1f}M exceeds the stated capacity {cap_rev:.0f}M — capacity binds, revisit (A14)")
    # Margin at the H-world scale: two-period fixed / variable split of non-GAAP
    # operating profit (ex SBC, amortisation, restructuring; ex cash interest),
    # FY26 actual vs FY28 M consensus; must sit inside the axis peer range.
    op26 = inp["op_gaap_fy26"] + inp["sbc_fy26"] + inp["amort_fy26"] + inp["restr_fy26"]
    op28 = inp["eps_fy28_m"] * inp["shares"] / MILLION / (1.0 - inp["tax"]) - inp["cash"] * inp["cash_yield"]
    var_m = (op28 - op26) / (inp["rev_fy28_m"] - inp["rev_fy26"])
    fixed = op26 - var_m * inp["rev_fy26"]
    opm_at = lambda rev: (var_m * rev + fixed) / rev  # noqa: E731
    opm_h = opm_at(scale)
    if not inp["bit_opm_weak"] <= opm_h <= inp["bit_opm_strong"]:
        errors.append(f"H-world op margin {opm_h:.4f} outside axis peer range "
                      f"[{inp['bit_opm_weak']}, {inp['bit_opm_strong']}] — clamp and say why (_AXIS.burn-in-test ⑤)")
    inc_core = var_m * (1.0 - inp["tax"]) * (1.0 - inp["sbc_haircut"])  # incremental core margin
    guide27 = (var_m * 140.0 + fixed + inp["cash"] * inp["cash_yield"]) / 140.0  # vs guided 18-22% pretax, printed only
    k_h = opening_bps(core["H"], g2) * inp["shares"] / MILLION  # FY28 opening operating capital, H
    kappa = k_h / rev28["H"]
    ni_h = core["H"] * inp["shares"] / MILLION
    unit = {"L": margin["M"], "M": margin["M"], "H": inc_core}
    if not (0 < qty["L"] < qty["M"] < qty["H"]):
        errors.append(f"option quantity ladder broken: {qty}")

    def v_tier(dr: float, m: float, rr: float = r, kap: float = kappa) -> dict[str, float]:
        d_ni = dr * m
        k_s = k_h * grow + kap * dr
        roe_s = (ni_h * grow + d_ni) / k_s
        pe_s = perpetual_pe(g2, roe_s, rr)
        gross = d_ni * pe_s / (1.0 + rr) ** disc_n
        capital = (kap * dr + inp["capex_committed"]) / (1.0 + rr) ** disc_n
        to_ps = MILLION / inp["shares"]
        return dict(d_ni=d_ni, roe=roe_s, pe=pe_s, gross=gross * to_ps, capital=capital * to_ps,
                    v=max(0.0, (gross - capital) * to_ps))

    vt = {t: v_tier(qty[t], unit[t]) for t in TIERS}
    v_opt = vt["H"]["v"]
    p_calc = tuple(vt[t]["v"] / v_opt for t in TIERS)
    hist_margin = (inp["unit_gp"] - inp["unit_opex"]) * (1.0 - inp["tax"]) / inp["unit_rev"]  # FY24 realised, floor only
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    p_tiers = stated_p_tiers(md)
    if p_tiers is None or any(abs(x - y) > P_TOL for x, y in zip(p_tiers, p_calc)):
        errors.append(f"p_L/p_M/p_H stated {p_tiers} vs V_k / V_H {tuple(round(x, 4) for x in p_calc)}")

    # ---- Candidate band (A19; AGENTS.md「共识升级候选带」): never a zone input ----
    # One house (Freedom Broker) prints FY30 revenue and nothing else, so each
    # tier's FY28 consensus net margin carries it to FY30: FY30 street EPS =
    # FY28 street EPS x FY30 revenue / that tier's FY28 revenue.  Same haircut,
    # interest strip, closing cash and g2 as the deck; the book rolls over
    # FY27-FY29 at b1 = g2/ROE (FY29 core is the geometric midpoint — the path
    # only moves the book), and FY30 is discounted two years.  The L world has
    # no second leg of growth, so L′ = L.
    errors += ladder("FY28 revenue", rev28["L"], rev28["M"], rev28["H"])

    def fy30_tier(t: str) -> tuple[float, float, float]:
        c30 = street[t] * inp["rev_fy30_fb"] / rev28[t] * (1.0 - inp["sbc_haircut"]) - int_ps
        rolled = unbooked + core[t] + (core[t] * c30) ** 0.5
        share = g2 * rolled / c30
        if share >= 1.0:
            raise ValueError(f"candidate book roll diverges at {t}: g·ΣN/c = {share:.2f}")
        roe30 = c30 * (1.0 - share) / bps_op_fy26
        return c30, roe30, c30 * perpetual_pe(g2, roe30, r) / (1.0 + r) ** CAND_DISC_YEARS + cash_ps

    cand_m, cand_h = fy30_tier("M"), fy30_tier("H")
    cand = (L, cand_m[2], cand_h[2])
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A19)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # ---- Report ----
    derived, sbc_fy28 = derived_haircut(inp)
    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 {baskets.get('r_perp')}) g2={g2:.4f} (_AXIS.burn-in-test median {inp['g2_bit_src']:.4f} truncated to g_cap(r) {cap:.3f})  "
          f"sbc haircut {inp['sbc_haircut']:.3f} (derived {derived:.4f} from GAAP gap; implied FY28 SBC {sbc_fy28:.2f}M vs FY26 {inp['sbc_fy26']:g}M; "
          f"FY26-based {inp['sbc_fy26'] * (1 - inp['tax']) / (inp['eps_fy28_m'] * inp['shares'] / MILLION):.4f})")
    print(f"operating equity {equity_op:.3f}M = book {inp['equity']:g} - net cash {inp['net_cash']:g}; "
          f"interest stripped {int_ps:.4f}/sh (cash {inp['cash']:g}M x {inp['cash_yield']:.1%} after tax); cash added back {cash_ps:.4f}/sh")
    for t in TIERS:
        print(f"{t}: street {street[t]:.4f} -> econ {eps[t]:.4f} -> core {core[t]:.4f}  ROE {roe[t]:.4f}  payout {1 - g2 / roe[t]:.3f}  "
              f"PE {pes[t]:.4f}x -> {ex_cash[t]:.4f} + cash = scenario {scen[t]:.4f}")
    print(f"ROE basis (A18): BPS_op opening-FY28 = {opening_bps(core['L'], g2):.3f}/{opening_bps(core['M'], g2):.3f}/{opening_bps(core['H'], g2):.3f} "
          f"(FY26-end op book {bps_op_fy26:.3f} rolled over FY27 unbooked core {unbooked:.3f}/sh at b1 = g2/ROE = {b1['L']:.2f}/{b1['M']:.2f}/{b1['H']:.2f}); "
          f"FY26-book basis would read ROE {roe_fy26['L']:.4f}/{roe_fy26['M']:.4f}/{roe_fy26['H']:.4f}")
    print(f"B bucket (actual retention {ret_actual:.0%} − b1) × FY27 unbooked → {excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh "
          f"(cash the model deems distributed but the company keeps; disclosure only, not a leg, not in BPS)")
    for rr, tag in ((0.13, "篮 6 13% (former basket)"), (0.15, "篮 7 15%")):
        alt = {t: core[t] * perpetual_pe(g2, roe[t], rr) + cash_ps for t in TIERS}
        print(f"contrast r {tag}: {alt['L']:.2f}/{alt['M']:.2f}/{alt['H']:.2f} (V_H {v_tier(qty['H'], inc_core, rr=rr)['v']:.2f})")
    print(f"floor (disclosed only, not max()'d): pb {inp['pb_floor']:g} x tbvps {tbvps:.4f} = {floor:.4f}  scenario_L={scen['L']:.2f} "
          f"{'BELOW' if below_floor else 'above'} floor by {abs(scen['L'] - floor):.2f}  "
          f"scenario_L/M={floor_ratio:.3f} (A2e-1 trigger < {FLOOR_RATIO_MIN} only if below floor)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pes['M']:.2f}x (+cash): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"guardrail on band basis (anchor / FY27 cons {inp['eps_fy27_m']:g}): "
          f"L {band_basis['L']:.1f}x M {band_basis['M']:.1f}x H {band_basis['H']:.1f}x vs own band lower edge {inp['pe_own_min']:g} "
          f"(FY28-core multiples {pes['L']:.2f}/{pes['M']:.2f}/{pes['H']:.2f}x are a different basis)")
    print("band-edge g @ M ROE: " + " | ".join(
        f"{k} {inp[f'pe_own_{k}']:g}x -> g {g:+.4f}{'' if cond else ' (ill-conditioned)'}{' (> cap, unreachable under ①)' if g > cap else ''}"
        for k, (g, cond) in edges.items()) + f"  | max PE_M under ① = {pe_m_cap:.2f}x")
    print(f"L/M {L / M:.3f} (ex-cash {ex_cash['L'] / ex_cash['M']:.3f} = num {num_lm:.3f} x pe {pe_lm:.3f}) | "
          f"H/M {H / M:.3f} (ex-cash {ex_cash['H'] / ex_cash['M']:.3f} = num {num_hm:.3f} x pe {pe_hm:.3f}) | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.2f}) -> {lo_l:.2f}/{lo_m:.2f}/{lo_h:.2f} "
          f"{'(ladder broken)' if not lo_ok else ''}; +1pp exceeds cap {cap:.3f} (①, unusable)")
    print(f"H quantity (demand side): Freedom FY30 {inp['rev_fy30_fb']:g} - H-tier FY28 {rev28['H']:g} x (1+g2)^{disc_n} {base_rev:.2f} = {path_xs:.2f}M "
          f"+ second AI {inp['opt_rev_ai']:g} + SiC {sic_item:.2f} = {qty['H']:.2f}M; high path FY28 Oppenheimer {inp['rev_fy28_opp']:g} -> "
          f"FY29 {path_fy29:.1f} (interpolated) -> FY30 {inp['rev_fy30_fb']:g}; H-world revenue {scale:.1f}M = {scale / cap_rev:.1%} of stated capacity {cap_rev:.0f}M")
    print(f"two-period op margin: FY26 {op26:.2f}M @ {inp['rev_fy26']:g} / FY28M {op28:.2f}M @ {inp['rev_fy28_m']:g} -> variable {var_m:.4f}, fixed {fixed:.2f}M; "
          f"at H-world scale {opm_h:.4f} (axis {inp['bit_opm_weak']}-{inp['bit_opm_strong']}); FY27 guide-check pretax {guide27:.4f} (guided 0.18-0.22); "
          f"incremental core margin {inc_core:.4f}; capital/revenue kappa {kappa:.4f} (K_H {k_h:.2f}M)")
    for t in TIERS:
        x = vt[t]
        print(f"V_{t}: qty {qty[t]:.2f}M x core margin {unit[t]:.4f} = dNI {x['d_ni']:.2f}M; success ROE {x['roe']:.4f} PE {x['pe']:.2f}x "
              f"-> {x['gross']:.2f}/sh - capital {x['capital']:.2f}/sh (FY{int(inp['t_opt']) % 100} -> FY28, /{1 + r:g}^{disc_n}) = {x['v']:.2f}  p={x['v'] / v_opt:.4f}")
    print(f"V_opt = V_H = {v_opt:.2f} | SiC item {sic_item:.2f}M (FY24 {sic_peak:.2f} - FY26 {sic_in:.2f}) | FY24 realised after-tax EBIT {hist_margin:.4f} (floor only)")
    cap_q = cap_rev - base_rev
    sens = {
        "path only (no named items)": v_tier(path_xs, inc_core)["v"],
        "margin weak": v_tier(qty["H"], inp["bit_opm_weak"] * (1 - inp["tax"]) * (1 - inp["sbc_haircut"]))["v"],
        "margin strong": v_tier(qty["H"], inp["bit_opm_strong"] * (1 - inp["tax"]) * (1 - inp["sbc_haircut"]))["v"],
        "kappa x0.5": v_tier(qty["H"], inc_core, kap=kappa * 0.5)["v"],
        "FY28M margin": v_tier(qty["H"], margin["M"])["v"],
        "r 13%": v_tier(qty["H"], inc_core, rr=0.13)["v"],
        "r 15%": v_tier(qty["H"], inc_core, rr=0.15)["v"],
    }
    print("V_H sensitivity: " + " | ".join(f"{k} {v:.2f}" for k, v in sens.items()))
    print(f"theoretical-capacity reading (disclosure only, MUST NOT be H): {cap_rev:.0f}M - {base_rev:.2f} = {cap_q:.1f}M, "
          f"op margin there {opm_at(cap_rev):.4f} -> V {v_tier(cap_q, inc_core)['v']:.2f}")
    opt = tuple(anchor + vt[t]["v"] for anchor, t in zip((L, M, H), TIERS))
    a2, b2 = cut_points(*opt)
    print(f"zone+V band: {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    print(f"候选带 (A19; Freedom Broker FY30 revenue {inp['rev_fy30_fb']:g}M x FY28 tier margin, g2, ÷(1+r)^{CAND_DISC_YEARS}; not a zone input): "
          f"core FY30 {cand_m[0]:.3f}/{cand_h[0]:.3f}  ROE {cand_m[1]:.3f}/{cand_h[1]:.3f}  "
          f"L′/M′/H′={cand[0]:.2f}/{cand[1]:.2f}/{cand[2]:.2f}")
    print(f"capex axis implied share: M {inp['rev_fy28_m'] * MILLION / inp['capex_m']:.3%} (not material)")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 — the only priced r; the rolled ROE, g2, the SBC-haircut core
    # numerator and the net-cash add-back stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        s = [core[t] * perpetual_pe(g2, roe[t], r + dr) + cash_ps for t in TIERS]
        return s[0], s[1], s[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("AEHR.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
