#!/usr/bin/env python3
"""TSEM.US valuation eval — recompute anchors from frameworks/TSEM.US.md.

formula_id: tsem_gordon_two_stage_2027_opeq_v2

Whole-company Gordon PE on the FY2027 consensus (8 houses, adjusted EPS; the
furthest year with a >=2-house *range*, valuation-rules 裁决顺序 ②).  Numerators
are the street adjusted figures less the GAAP-vs-adjusted consensus gap (SBC +
acquisition amortisation, the AEHR.US A9 convention; A8) and less the after-tax
interest the cash pile earns (A6); the net cash comes back per share as a
closing item.  The
L numerator is the digestion year — FY2027 held at the FY2026 consensus mean
(the silicon-photonics ramp pauses for a year); M/H are the consensus mean /
high.

Multiples are generated, not borrowed: tier ROE on *operating* equity (book
less net cash, A6), r = 10% (operating tier), M/H carry the FY2028 consensus
year as a one-year transition (`two_stage_pe`, g1 = 2028E / 2027E on the same
consensus line, n = 1; A4) and L does not.  g2 = the semiconductor / optical
cross-section reverse-solved median truncated to the repo cap (A5).  All three
generated multiples must sit inside the own realised forward-PE band [9.2,
39.9] (③); the tangible floor is printed but never wins.

g2 leverage (A5): at g2 - 1pp the price crosses H, so the zone flips
neutral -> stretched.  valuation-rules calls that BLOCKED; the framework was
settled at the cap by user decision on 2026-09-14 because every g2 source
(6.52% / 6.64% / market-implied 6.26%) sits above the cap, so -1pp lies below
all evidence.  This eval prints both ends and warns; it does not fail.

V_opt = Japan Track 2 priced as 1 x the own realised silicon-photonics leg
(Q2'26 annualised revenue x realised net margin) at the H-tier perpetual
multiple (A9).  Probabilities live only in the zone+V table.

Cross-file: `sipho_unit_rev` must equal the same field in GFS.US.md — the one
realised unit both frameworks price against (A14).

Run:  python3 eval/TSEM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    G_CAP,
    R_OPERATING,
    check_g_cap,
    check_r,
    check_transition_years,
    implied_g,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "TSEM.US.md"
MIRROR = REPO_ROOT / "frameworks" / "GFS.US.md"
FORMULA_ID = "tsem_gordon_two_stage_2027_opeq_v2"
TOL = 0.05
MIN_R_MINUS_G = 0.02
P_TIERS = (0.0, 0.25, 1.0)  # A9 — table 3 only, never an input

REQUIRED = [
    "price",
    "shares",
    "equity",
    "net_cash",
    "nii_4q",
    "gaap_gap_ps",
    "tax",
    "eps_2026_m",
    "eps_2027_l",
    "eps_2027_m",
    "eps_2027_h",
    "eps_2027_gaap_m",
    "eps_2028_gaap_m",
    "n_stage",
    "n_consensus",
    "g2",
    "g_peer_median",
    "r_perp",
    "pe_own_min",
    "pe_own_max",
    "bvps",
    "pb_floor",
    "sipho_unit_rev",
    "npm_unit",
    "v_opt_units",
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


def solve_g(target_pe: float, fn, lo: float = -0.05, hi: float = 0.0999) -> float | None:
    if fn(hi) < target_pe:
        return None
    if fn(lo) >= target_pe:
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2
        if fn(mid) >= target_pe:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def sanity_checks(inp: dict[str, float]) -> list[str]:
    errs: list[str] = []
    errs += check_r(inp["r_perp"], "r_perp")
    if abs(inp["r_perp"] - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={inp['r_perp']}: operating leg, expected {R_OPERATING}")
    errs += check_g_cap(inp["g2"], "g2")
    if abs(inp["g2"] - min(inp["g_peer_median"], G_CAP)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(source {inp['g_peer_median']:.4f}, cap {G_CAP}) — A5")
    gap = inp["r_perp"] - inp["g2"]
    if gap <= 0:
        errs.append("perpetuity diverges: g2 >= r")
    elif gap < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if not inp["eps_2027_gaap_m"] < inp["eps_2028_gaap_m"]:
        errs.append("2028E consensus not above 2027E: same-world gate for g2 > 0 no longer holds (A4/A5)")
    errs += ladder("consensus range", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    if not inp["eps_2026_m"] < inp["eps_2027_l"]:
        errs.append("digestion-year numerator is not below the FY27 consensus low (A3)")
    if inp["equity"] - inp["net_cash"] <= 0:
        errs.append("operating equity (equity - net_cash) is not positive (A6)")
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

    r, g2, n = inp["r_perp"], inp["g2"], int(inp["n_stage"])
    g1 = inp["eps_2028_gaap_m"] / inp["eps_2027_gaap_m"] - 1.0
    street = {"L": inp["eps_2026_m"], "M": inp["eps_2027_m"], "H": inp["eps_2027_h"]}

    # ---- Step 1: economic EPS = street adjusted less the GAAP-adjusted gap (SBC + amortisation, A8) and after-tax net interest (A6) ----
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    ops = {t: street[t] - inp["gaap_gap_ps"] - nii_ps for t in TIERS}

    # ---- Step 2: tier ROE on operating equity; Gordon (L) / two-stage (M, H) ----
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    roe = {t: ops[t] * inp["shares"] / equity_op for t in TIERS}
    pes = {
        "L": perpetual_pe(g2, roe["L"], r),
        "M": two_stage_pe(g1, n, g2, roe["M"], r),
        "H": two_stage_pe(g1, n, g2, roe["H"], r),
    }
    p1 = {t: 1.0 - g1 / roe[t] for t in ("M", "H")}
    ex_cash = {t: ops[t] * pes[t] for t in TIERS}
    scen = {t: ex_cash[t] + cash_ps for t in TIERS}

    # ---- Step 3: floor (never wins here), anchors, cut points ----
    floor = inp["pb_floor"] * inp["bvps"]
    L = max(scen["L"], floor)
    M, H = scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)
    for t in TIERS:
        if not inp["pe_own_min"] - TOL <= pes[t] <= inp["pe_own_max"] + TOL:
            errors.append(f"{t} multiple {pes[t]:.2f}x outside own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] (③)")

    # ---- A2e-2c flat ladder ----
    if not (ops["L"] < ops["M"] < ops["H"]):
        errors.append("numerator ladder broken (A2e-2c)")
    flat = [ops[t] * pes["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # ---- g2 leverage: both ends printed; the flip is a documented user decision (A5) ----
    def deck_at(g: float) -> tuple[float, float, float]:
        return (
            max(ops["L"] * perpetual_pe(g, roe["L"], r) + cash_ps, floor),
            ops["M"] * two_stage_pe(g1, n, g, roe["M"], r) + cash_ps,
            ops["H"] * two_stage_pe(g1, n, g, roe["H"], r) + cash_ps,
        )

    lo_l, lo_m, lo_h = deck_at(g2 - 0.01)
    lo_zone = zone_of(inp["price"], lo_l, lo_m, lo_h)

    # ---- Option ceiling (A9): Track 2 = one own SiPho leg at the H-tier perpetual multiple ----
    unit_ni_ps = inp["sipho_unit_rev"] * inp["npm_unit"] / inp["shares"]
    v_opt = inp["v_opt_units"] * unit_ni_ps * perpetual_pe(g2, roe["H"], r)

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs A9 {P_TIERS}")

    # ---- Cross-file (A14): both frameworks price against the same realised SiPho unit ----
    if MIRROR.is_file():
        mirror = parse_inputs(MIRROR.read_text(encoding="utf-8"))
        if abs(mirror.get("sipho_unit_rev", -1) - inp["sipho_unit_rev"]) > 1.0:
            errors.append(f"sipho_unit_rev {inp['sipho_unit_rev']:g} != GFS.US {mirror.get('sipho_unit_rev')} — the shared realised unit drifted (A14)")
    else:
        errors.append("frameworks/GFS.US.md missing — mirror-state check impossible (A14)")

    # ---- Contrast bands (printed only) ----
    econ_tot = {t: street[t] - inp["gaap_gap_ps"] for t in TIERS}
    roe_tot = {t: econ_tot[t] * inp["shares"] / inp["equity"] for t in TIERS}
    tot = (econ_tot["L"] * perpetual_pe(g2, roe_tot["L"], r), econ_tot["M"] * two_stage_pe(g1, n, g2, roe_tot["M"], r), econ_tot["H"] * two_stage_pe(g1, n, g2, roe_tot["H"], r))
    no_tr = tuple(ops[t] * perpetual_pe(g2, roe[t], r) + cash_ps for t in TIERS)
    mkt_g, mkt_ok = implied_g((inp["price"] - cash_ps) / ops["M"], roe["M"], r)
    mkt_g2 = solve_g((inp["price"] - cash_ps) / ops["M"], lambda g: two_stage_pe(g1, n, g, roe["M"], r))

    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} g1(2028)={g1:.4f} n={n} g2={g2:.4f} (source {inp['g_peer_median']:.4f} truncated to cap {G_CAP:g})")
    print(f"operating equity {equity_op / 1e9:.3f}B = book {inp['equity'] / 1e9:.3f}B - net cash {inp['net_cash'] / 1e9:.3f}B; GAAP-adjusted gap stripped {inp['gaap_gap_ps']:.4f}/sh; interest stripped {nii_ps:.4f}/sh; cash added back {cash_ps:.4f}/sh")
    for t in TIERS:
        extra = f"  stage-1 payout {p1[t]:+.2f} (cash/external-funded growth)" if t in p1 else ""
        print(f"{t}: street {street[t]:.4f} -> op {ops[t]:.4f}  ROE_op {roe[t]:.4f}  PE {pes[t]:.4f}x -> {ex_cash[t]:.4f} + cash = {scen[t]:.4f}{extra}")
    print(f"floor = PB {inp['pb_floor']:g} x BVPS {inp['bvps']:g} = {floor:.2f} (scenario wins: {scen['L']:.2f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  zone={zone}  price={inp['price']:.2f}  P/M={inp['price'] / M:.3f} P/H={inp['price'] / H:.3f} P/B={inp['price'] / B:.3f}")
    print(f"band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]: L {pes['L']:.2f}x | M {pes['M']:.2f}x | H {pes['H']:.2f}x (all inside)")
    print(f"flat ladder @ PE_M {pes['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {L / M:.3f} (= num {ops['L'] / ops['M']:.3f} x pe {pes['L'] / pes['M']:.3f}) | H/M {H / M:.3f} (num {ops['H'] / ops['M']:.3f} x pe {pes['H'] / pes['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.2f}) -> {lo_l:.2f}/{lo_m:.2f}/{lo_h:.2f} zone {lo_zone}; +1pp exceeds cap {G_CAP:g} (unusable)")
    if lo_zone != zone:
        print(f"WARN (A5): g2 -1pp flips zone {zone} -> {lo_zone}; all g2 evidence sits above the cap, settled at {g2:.2%} by user decision 2026-09-14 — price sits against H")
    print(f"contrast no-transition: {no_tr[0]:.2f}/{no_tr[1]:.2f}/{no_tr[2]:.2f} | total-equity ROE {roe_tot['L']:.3f}/{roe_tot['M']:.3f}/{roe_tot['H']:.3f} no cash add-back: {tot[0]:.2f}/{tot[1]:.2f}/{tot[2]:.2f} zone {zone_of(inp['price'], *tot)}")
    print(f"market-implied perpetual g (no transition) {mkt_g:.4f} well_conditioned={mkt_ok}; with 2028 transition g2 {mkt_g2 if mkt_g2 is None else round(mkt_g2, 4)}")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    print(f"V_opt={v_opt:.2f} (Track 2 = 1 x own SiPho leg: NI/sh {unit_ni_ps:.4f} x PE_H perp {perpetual_pe(g2, roe['H'], r):.2f}x); zone+V {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f} A'={a2:.2f} B'={b2:.2f} zone+V={zone_of(inp['price'], *opt)}; at g2-1pp H+V={lo_h + v_opt:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
