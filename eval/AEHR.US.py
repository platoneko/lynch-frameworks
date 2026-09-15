#!/usr/bin/env python3
"""AEHR.US valuation eval — recompute anchors from frameworks/AEHR.US.md.

formula_id: aehr_fy28_cons_gordon_opeq_v5

One operating leg on the FY28 consensus EPS range (3 houses; the furthest year
with a >=2-house *range*, valuation-rules 裁决顺序 ②).  Street EPS is the
company's normalized (ex-SBC) figure, so every tier is haircut by the SBC
share of FY28 consensus NI before it becomes an economic EPS; the haircut is
derived from the GAAP-vs-normalized consensus gap net of acquisition
amortisation (A9).  Multiples are generated, not borrowed:
`perpetual_pe(g2, ROE_x, r)` with g2 = the test-equipment peer cluster's
reverse-solved median truncated to the repo cap (A5), r = 10% — the default
operating tier, the same tier every other operating leg in the pool sits on
(A12) — and tier ROE on *operating* equity: book equity less net cash, with
the after-tax interest the consensus EPS earns on that cash stripped from the
numerator and the net cash added back per share as a closing item (A15, the
1810.HK A15 treatment).  FY29 has no >=2-house consensus anywhere, so there is
no g1 and no discount (FY28 = current FY + 1).

L = max(scenario, tangible-book PB floor); the scenario wins at r = 10% and
the A2e-1 ratio scenario_L / M is printed and guarded (>= 0.3) in case the
floor ever takes over again.  Guardrail (③): the own realised band divides
close by the *current-FY* consensus, so anchors are compared to it on that
same basis (anchor / FY27 consensus) — only the lower edge binds, the upper
edge is meaningless (2025-26 consensus EPS ~ 0).

V_opt = k FY2024 realised single-customer fill units (k = 2: the unsigned
second AI processor customer and a return of SiC to its FY24 peak, both named
outside the consensus by the covering houses, A14), priced at the M-tier
multiple.  Probabilities live only in the zone+V table.

Run:  python3 eval/AEHR.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_capex_mount  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    G_CAP,
    R_OPERATING,
    check_g_cap,
    check_r,
    implied_g,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "AEHR.US.md"
FORMULA_ID = "aehr_fy28_cons_gordon_opeq_v5"
TOL = 0.05
MILLION = 1e6  # money inputs are in $M, share counts are absolute
MIN_R_MINUS_G = 0.02  # valuation-rules: below this the multiple sits at the pole
FLOOR_RATIO_MIN = 0.3  # A2e-1: floor wins AND scenario_L / M below this -> back to dialogue
HAIRCUT_ROUNDING = 0.01  # A9: haircut may be rounded up by at most 1pp over the derived value
P_TIERS = (0.0, 0.25, 1.0)  # A14 — table 3 only, never an input

REQUIRED = [
    "price",
    "shares",
    "shares_basic",
    "equity",
    "cash",
    "net_cash",
    "cash_yield",
    "tangible_book",
    "pb_floor",
    "eps_fy27_m",
    "eps_fy28_l",
    "eps_fy28_m",
    "eps_fy28_h",
    "eps_fy28_gaap_m",
    "rev_fy28_m",
    "sbc_fy26",
    "amort_fy26",
    "tax",
    "sbc_haircut",
    "r_perp",
    "g2",
    "g_peer_median",
    "pe_own_min",
    "pe_own_p5",
    "pe_own_p50",
    "unit_rev",
    "unit_gp",
    "unit_opex",
    "v_opt_units",
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


def sanity_checks(inp: dict[str, float]) -> list[str]:
    errs: list[str] = []

    # A12: the FY28 consensus numerator is ordinary operating cash flow -> default tier, like every peer leg.
    errs += check_r(inp["r_perp"], "r_perp")
    if abs(inp["r_perp"] - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={inp['r_perp']}: operating leg (A12), expected {R_OPERATING}")

    # A5: g2 is the peer median truncated to the cap — the truncation is a fact to check.
    errs += check_g_cap(inp["g2"], "g2")
    if abs(inp["g2"] - min(inp["g_peer_median"], G_CAP)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {G_CAP}) — A5")
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
    errors = sanity_checks(inp)
    # Demand-side mount on the AI-capex axis (share is immaterial, rungs still must match).
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))

    r, g2 = inp["r_perp"], inp["g2"]
    street = {"L": inp["eps_fy28_l"], "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}

    # ---- Step 1-2: economic EPS, then core EPS with the cash interest stripped (A9, A15) ----
    eps = {t: street[t] * (1.0 - inp["sbc_haircut"]) for t in TIERS}
    int_ps = inp["cash"] * inp["cash_yield"] * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    core = {t: eps[t] - int_ps for t in TIERS}

    # ---- Step 3-4: tier ROE on operating equity, Gordon multiple, cash added back ----
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] * MILLION / inp["shares"]
    roe = {t: core[t] * inp["shares"] / (equity_op * MILLION) for t in TIERS}
    pes = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    ex_cash = {t: core[t] * pes[t] for t in TIERS}
    scen = {t: ex_cash[t] + cash_ps for t in TIERS}

    # ---- Step 5: floor, anchors, cut points ----
    tbvps = inp["tangible_book"] * MILLION / inp["shares_basic"]
    floor = inp["pb_floor"] * tbvps
    floor_wins = scen["L"] < floor
    L = max(scen["L"], floor)
    M, H = scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)
    floor_ratio = scen["L"] / M
    if floor_wins and floor_ratio < FLOOR_RATIO_MIN:
        errors.append(f"A2e-1: floor wins and scenario_L/M = {floor_ratio:.2f} < {FLOOR_RATIO_MIN} — earnings ruler failed at L, back to dialogue")

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
    pe_m_cap = perpetual_pe(G_CAP, roe["M"], r)

    # ---- A2e-2c flat ladder + A2e-5 decomposition (both on the ex-cash earnings term) ----
    if not (core["L"] < core["M"] < core["H"]):
        errors.append(f"numerator ladder broken: core EPS {core['L']:.3f}/{core['M']:.3f}/{core['H']:.3f} (A2e-2c)")
    flat = [core[t] * pes["M"] + cash_ps for t in TIERS]
    flat[0] = max(flat[0], floor)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    num_lm, num_hm = core["L"] / core["M"], core["H"] / core["M"]
    pe_lm, pe_hm = pes["L"] / pes["M"], pes["H"] / pes["M"]

    # ---- g2 leverage (valuation-rules「g₂ 的杠杆 MUST 显式」): zone must survive -1pp; +1pp breaks ① ----
    def deck_at(g: float) -> tuple[float, float, float, bool]:
        s = {t: core[t] * perpetual_pe(g, roe[t], r) + cash_ps for t in TIERS}
        l_ = max(s["L"], floor)
        return l_, s["M"], s["H"], l_ < s["M"] < s["H"]

    lo_l, lo_m, lo_h, lo_ok = deck_at(g2 - 0.01)
    lo_zone = zone_of(inp["price"], lo_l, lo_m, lo_h) if lo_ok else ("stretched" if inp["price"] > lo_h else "ladder-broken")

    # ---- Option ceiling and zone+V (probabilities only here) ----
    d_eps = (inp["unit_gp"] - inp["unit_opex"]) * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    unit_value = d_eps * pes["M"]
    v_opt = inp["v_opt_units"] * unit_value
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    p_tiers = stated_p_tiers(md)
    if p_tiers != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {p_tiers} vs A14 {P_TIERS}")
    if lo_zone != zone:
        errors.append(f"g2 -1pp moves zone {zone} -> {lo_zone}: not settleable (valuation-rules g2 杠杆)")

    # ---- Report ----
    derived, sbc_fy28 = derived_haircut(inp)
    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (operating) g2={g2:.4f} (peer median {inp['g_peer_median']:.4f} truncated to cap {G_CAP})  "
          f"sbc haircut {inp['sbc_haircut']:.3f} (derived {derived:.4f} from GAAP gap; implied FY28 SBC {sbc_fy28:.2f}M vs FY26 {inp['sbc_fy26']:g}M; "
          f"FY26-based {inp['sbc_fy26'] * (1 - inp['tax']) / (inp['eps_fy28_m'] * inp['shares'] / MILLION):.4f})")
    print(f"operating equity {equity_op:.3f}M = book {inp['equity']:g} - net cash {inp['net_cash']:g}; "
          f"interest stripped {int_ps:.4f}/sh (cash {inp['cash']:g}M x {inp['cash_yield']:.1%} after tax); cash added back {cash_ps:.4f}/sh")
    for t in TIERS:
        print(f"{t}: street {street[t]:.4f} -> econ {eps[t]:.4f} -> core {core[t]:.4f}  ROE {roe[t]:.4f}  payout {1 - g2 / roe[t]:.3f}  "
              f"PE {pes[t]:.4f}x -> {ex_cash[t]:.4f} + cash = scenario {scen[t]:.4f}")
    print(f"tbvps={tbvps:.4f} floor(pb*tbvps)={floor:.4f}  scenario_L={scen['L']:.2f}  {'floor' if floor_wins else 'scenario'} wins  "
          f"scenario_L/M={floor_ratio:.3f} (A2e-1 trigger < {FLOOR_RATIO_MIN} only if floor wins)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pes['M']:.2f}x (+cash, L floored): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"guardrail on band basis (anchor / FY27 cons {inp['eps_fy27_m']:g}): "
          f"L {band_basis['L']:.1f}x M {band_basis['M']:.1f}x H {band_basis['H']:.1f}x vs own band lower edge {inp['pe_own_min']:g} "
          f"(FY28-core multiples {pes['L']:.2f}/{pes['M']:.2f}/{pes['H']:.2f}x are a different basis)")
    print("band-edge g @ M ROE: " + " | ".join(
        f"{k} {inp[f'pe_own_{k}']:g}x -> g {g:+.4f}{'' if cond else ' (ill-conditioned)'}{' (> cap, unreachable under ①)' if g > G_CAP else ''}"
        for k, (g, cond) in edges.items()) + f"  | max PE_M under ① = {pe_m_cap:.2f}x")
    print(f"L/M {L / M:.3f} (ex-cash {ex_cash['L'] / ex_cash['M']:.3f} = num {num_lm:.3f} x pe {pe_lm:.3f}) | "
          f"H/M {H / M:.3f} (ex-cash {ex_cash['H'] / ex_cash['M']:.3f} = num {num_hm:.3f} x pe {pe_hm:.3f}) | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.2f}) -> {lo_l:.2f}/{lo_m:.2f}/{lo_h:.2f} "
          f"{'(ladder broken)' if not lo_ok else ''} zone {lo_zone}; +1pp exceeds cap {G_CAP} (①, unusable)")
    print(f"V_opt={v_opt:.2f} (units {inp['v_opt_units']:g} x [dEPS {d_eps:.4f} (FY24 unit EBIT {inp['unit_gp'] - inp['unit_opex']:.3f}M after tax) x PE_M {pes['M']:.2f} = {unit_value:.2f}/unit])")
    opt = tuple(anchor + p * v_opt for anchor, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    print(f"zone+V band: {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}  zone+V={zone_of(inp['price'], *opt)}")
    print(f"capex axis implied share: M {inp['rev_fy28_m'] * MILLION / inp['capex_m']:.3%} (not material)")
    print(f"price={inp['price']:.2f} zone={zone}  P/H={inp['price'] / H:.2f}x  P/(H+V)={inp['price'] / opt[2]:.2f}x  "
          f"implied p=(P-H)/V_opt={(inp['price'] - H) / v_opt:.1f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
