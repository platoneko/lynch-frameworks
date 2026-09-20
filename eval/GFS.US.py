#!/usr/bin/env python3
"""GFS.US valuation eval — recompute anchors from frameworks/GFS.US.md.

formula_id: gfs_gordon_two_stage_2027_opeq_v2

Whole-company Gordon PE on the FY2027 consensus (21 houses; the furthest year
with a >=2-house *range*, valuation-rules 裁决顺序 ②).  Numerators are the
street non-GAAP figures less after-tax SBC (the AEHR.US / LITE.US economic-EPS
convention, A9) and less the after-tax interest the cash pile earns (A6); the
net cash comes back per share as a closing item.  The L numerator is the
digestion year — FY2027 held at the FY2026 consensus mean — because for a
`cyclical` the consensus low is too narrow to be "the measured bad" (②-b);
M/H are the consensus mean / high.

Multiples are generated, not borrowed: tier ROE = FY2027 economic EPS over
the FY2027 OPENING *operating* book (book less net cash, A6): the 2Q26
operating book rolled over the 2H26 earnings not yet booked (FY26 consensus
minus 1H26 actual, on the same economic basis) at the growth-required
retention b1 = g/ROE — g1 for M/H (the FY2028 window), g2 for L (no window);
valuation-rules 62c72a2, A20.  b1 > 1 on M/H is the cash-pool / external
funding the negative stage-1 payout already prices, so it is printed, not
failed; only a diverging roll stops.  r = the basket rate — the whole company is one leg in
basket 4 龙头制造 (10%, A19; the Inputs row names the basket and `check_r`
holds the value to it), M/H carry the FY2028 consensus year as a one-year
transition (`two_stage_pe`, g1 = 2028E / 2027E on the same GAAP consensus
line, n = 1; A4) and L does not.  g2 = the foundry cluster's reverse-solved
median (tier-1 source, A5), capped at g_cap(r) — NOT reverse-solved to the own
band.  The own realised forward-PE band [15.6, 46.2] is the 裁决顺序 ③
guardrail (A7): M sits below its floor, but the band was judged *distorted* at
step 1b (its floor is the IPO month over FY22 *realised* EPS, and 2022 priced
multi-year growth that never came), so ③ is indeterminate — the ruler stays in
basket 4 (already the floor), no band-edge r is solved, the zone is read as is
(A18).  This eval therefore WARNs on the band breach instead of failing.  The
realised PB low is printed as a floor coordinate, never max()'d in (A8).  The
g2 +-1pp zones are printed and a flip warns; the price-implied r is printed as
a disclosure.

V_opt = 1 x a Tower-sized silicon-photonics leg (peer realised unit, A10) at
the H-tier perpetual multiple.  Candidate band swaps the consensus 2028 g1 for
the company's Analyst Day 2028 model (single source, A17).  Probabilities live
only in the zone+V table.

Cross-file: `sipho_unit_rev` must equal the same field in TSEM.US.md — the
one realised unit both frameworks price against (A12).

Run:  python3 eval/GFS.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    check_transition_years,
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
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "GFS.US.md"
MIRROR = REPO_ROOT / "frameworks" / "TSEM.US.md"
FORMULA_ID = "gfs_gordon_two_stage_2027_opeq_v2"
TOL = 0.05
MIN_R_MINUS_G = 0.02
P_TIERS = (0.0, 0.25, 1.0)  # A10 — table 3 only, never an input

REQUIRED = [
    "price",
    "shares",
    "equity",
    "net_cash",
    "nii_4q",
    "sbc_annual",
    "tax",
    "eps_2026_m",
    "eps_1h26_a",
    "payout_3y",
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
    "pb_own_min",
    "rev_2025",
    "cagr_model",
    "opm_model_2028",
    "sipho_unit_rev",
    "npm_unit",
    "v_opt_units",
]
TIERS = ("L", "M", "H")

_CANDIDATE = re.compile(
    r"候选带（[^）]+）[^\n]*?L′\s*=\s*\*\*([0-9.]+)\*\*[^\n]*?M′\s*=\s*\*\*([0-9.]+)\*\*[^\n]*?H′\s*=\s*\*\*([0-9.]+)\*\*"
)


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


def stated_candidate(md: str) -> tuple[float, float, float] | None:
    ms = list(_CANDIDATE.finditer(md))
    if len(ms) != 1:
        return None
    return tuple(float(ms[0].group(i)) for i in (1, 2, 3))  # type: ignore[return-value]


def _implied_r(price: float, eps_m: float, roe_m: float, g1: float, n: int, g2: float, cash_ps: float) -> float:
    """r at which the M-tier two-stage deck equals the price (disclosure only, A18)."""
    lo, hi = g2 + 1e-4, 0.50
    for _ in range(80):
        mid = (lo + hi) / 2
        if eps_m * two_stage_pe(g1, n, g2, roe_m, mid) + cash_ps > price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    # A19: the leg names its basket in the Inputs row; the value must be that basket's.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A19)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    # A5: g2 is the peer cluster median (tier-1 source) truncated to the cap — no band reverse-solve.
    cap = g_cap(inp["r_perp"])
    if abs(inp["g2"] - min(inp["g_peer_median"], cap)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {cap:.3f}) — A5")
    gap = inp["r_perp"] - inp["g2"]
    if gap <= 0:
        errs.append("perpetuity diverges: g2 >= r")
    elif gap < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    # 裁决顺序 ④ 同世界门: the 2028 consensus year is up, so a g2 > 0 source is admissible.
    if not inp["eps_2027_gaap_m"] < inp["eps_2028_gaap_m"]:
        errs.append("2028E GAAP consensus not above 2027E: same-world gate for g2 > 0 no longer holds (A4/A5)")
    if inp["g_peer_median"] < 0:
        errs.append("peer median < 0 contradicts an upward 2027->2028 consensus (同世界门)")
    # A3: one consensus range (2.40 / 2.62 / 3.63) with the digestion year below its low end.
    errs += ladder("consensus range", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    if not inp["eps_2026_m"] < inp["eps_2027_l"]:
        errs.append("digestion-year numerator is not below the FY27 consensus low — L is no longer the measured-bad tier (A3)")
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
    errors = sanity_checks(inp, parse_baskets(md))

    r, g2, n = inp["r_perp"], inp["g2"], int(inp["n_stage"])
    g1 = inp["eps_2028_gaap_m"] / inp["eps_2027_gaap_m"] - 1.0
    street = {"L": inp["eps_2026_m"], "M": inp["eps_2027_m"], "H": inp["eps_2027_h"]}

    # ---- Step 1: economic EPS = street non-GAAP less after-tax SBC and after-tax net interest (A9, A6) ----
    sbc_ps = inp["sbc_annual"] * (1.0 - inp["tax"]) / inp["shares"]
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    ops = {t: street[t] - sbc_ps - nii_ps for t in TIERS}

    # ---- Step 2: tier ROE = E_{2027} / opening-2027 operating book; Gordon (L) / two-stage (M, H) ----
    # The 2Q26 operating book is rolled over the 2H26 earnings not yet booked
    # (FY26 consensus less 1H26 actual, less the 2H26 half of SBC and interest
    # so it is on the numerator's economic basis) at the growth-required
    # retention b1 = g/ROE: g1 for M/H, g2 for L (A20).  ROE and BPS depend on
    # each other; closed form BPS = BPS0 / (1 - g·N/eps).  b1 > 1 (M/H) is the
    # external funding stage-1 payout < 0 already prices.  Every contrast band
    # below rolls the same way with its own g and numerator.
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    bps_op_2q26 = equity_op / inp["shares"]
    unbooked = (inp["eps_2026_m"] - inp["eps_1h26_a"]) - 0.5 * sbc_ps - 0.5 * nii_ps

    def opening_bps(eps_x: float, g: float, n_unbooked: float = unbooked) -> float:
        share = g * n_unbooked / eps_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/eps = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps_op_2q26 / (1.0 - share)

    def rolled_roe(num: dict[str, float], g: float, g1_: float, n_unbooked: float = unbooked) -> dict[str, float]:
        g_roll = {"L": g, "M": g1_, "H": g1_}
        return {t: num[t] / opening_bps(num[t], g_roll[t], n_unbooked) for t in TIERS}

    roe = rolled_roe(ops, g2, g1)
    b1 = {t: g / roe[t] for t, g in zip(TIERS, (g2, g1, g1))}
    roe_2q26 = {t: ops[t] * inp["shares"] / equity_op for t in TIERS}  # old basis, printed only
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in TIERS}  # disclosure only

    def deck(g: float, g1_: float) -> tuple[dict[str, float], dict[str, float]]:
        roe_ = rolled_roe(ops, g, g1_)
        pe = {
            "L": perpetual_pe(g, roe_["L"], r),
            "M": two_stage_pe(g1_, n, g, roe_["M"], r),
            "H": two_stage_pe(g1_, n, g, roe_["H"], r),
        }
        return pe, {t: ops[t] * pe[t] + cash_ps for t in TIERS}

    pes, anchors = deck(g2, g1)
    p1 = {t: 1.0 - g1 / roe[t] for t in ("M", "H")}
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)

    # ---- A2e-2c flat ladder + A2e-5 decomposition ----
    if not (ops["L"] < ops["M"] < ops["H"]):
        errors.append("numerator ladder broken (A2e-2c)")
    flat = [ops[t] * pes["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # ---- ③ guardrail (A7) on the band's own basis (anchor / street FY27 mean); breach WARNs, not fails (A18) ----
    band_basis = {t: anchors[t] / inp["eps_2027_m"] for t in TIERS}
    # ---- Floor disclosure (A8): realised PB low is a coordinate, never max()'d into L ----
    pb_low_coord = inp["pb_own_min"] * inp["bvps"]

    # ---- g2 leverage: both ends printed; a flip is disclosed, not failed (A5, price sits on H) ----
    lo = deck(g2 - 0.01, g1)[1]
    hi = deck(g2 + 0.01, g1)[1] if g2 + 0.01 <= g_cap(r) + 1e-9 else None
    lo_zone = zone_of(inp["price"], lo["L"], lo["M"], lo["H"])
    hi_zone = zone_of(inp["price"], hi["L"], hi["M"], hi["H"]) if hi else None

    # ---- Option ceiling (A10): one Tower-sized SiPho leg at the H-tier perpetual multiple ----
    unit_ni_ps = inp["sipho_unit_rev"] * inp["npm_unit"] / inp["shares"]
    v_opt = inp["v_opt_units"] * unit_ni_ps * perpetual_pe(g2, roe["H"], r)

    # ---- Candidate band (A17): company Analyst Day 2028 model swapped into g1 (single source) ----
    rev_2028 = inp["rev_2025"] * (1.0 + inp["cagr_model"]) ** 3
    ni_2028 = rev_2028 * inp["opm_model_2028"] * (1.0 - inp["tax"])
    econ_2028 = ni_2028 / inp["shares"] - sbc_ps - nii_ps
    g1_cand = econ_2028 / ops["M"] - 1.0
    cand = deck(g2, g1_cand)[1]
    cand_band = (L, cand["M"], cand["H"])  # L carries no transition, copied from the base deck
    if not (cand_band[0] < cand_band[1] < cand_band[2]):
        errors.append(f"candidate band ladder broken: {cand_band}")

    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs A10 {P_TIERS}")
    said_c = stated_candidate(md)
    if said_c is None:
        errors.append("candidate band line missing or ambiguous (A17)")
    elif any(abs(s - c) > TOL for s, c in zip(said_c, cand_band)):
        errors.append(f"candidate band: stated {said_c} vs recomputed {tuple(round(x, 2) for x in cand_band)}")

    # ---- Cross-file (A12): both frameworks price against the same realised SiPho unit ----
    if MIRROR.is_file():
        mirror = parse_inputs(MIRROR.read_text(encoding="utf-8"))
        if abs(mirror.get("sipho_unit_rev", -1) - inp["sipho_unit_rev"]) > 1.0:
            errors.append(f"sipho_unit_rev {inp['sipho_unit_rev']:g} != TSEM.US {mirror.get('sipho_unit_rev')} — the shared realised unit drifted (A12)")
    else:
        errors.append("frameworks/TSEM.US.md missing — mirror-state check impossible (A12)")

    # ---- Contrast bands (printed only; each rolls its own book the A20 way) ----
    roe_no_tr = rolled_roe(ops, g2, g2)  # no window anywhere -> every tier rolls at g2
    no_tr = tuple(ops[t] * perpetual_pe(g2, roe_no_tr[t], r) + cash_ps for t in TIERS)
    roe_tot = {t: (street[t] - sbc_ps) * inp["shares"] / inp["equity"] for t in TIERS}  # 2Q26 total book, not rolled (A15)
    tot = ((street["L"] - sbc_ps) * perpetual_pe(g2, roe_tot["L"], r), (street["M"] - sbc_ps) * two_stage_pe(g1, n, g2, roe_tot["M"], r), (street["H"] - sbc_ps) * two_stage_pe(g1, n, g2, roe_tot["H"], r))
    nosbc = {t: street[t] - nii_ps for t in TIERS}
    roe_nosbc = rolled_roe(nosbc, g2, g1, unbooked + 0.5 * sbc_ps)
    nosbc_deck = (nosbc["L"] * perpetual_pe(g2, roe_nosbc["L"], r) + cash_ps, nosbc["M"] * two_stage_pe(g1, n, g2, roe_nosbc["M"], r) + cash_ps, nosbc["H"] * two_stage_pe(g1, n, g2, roe_nosbc["H"], r) + cash_ps)
    r_contrast = {rr: tuple(ops[t] * (perpetual_pe(g2, roe[t], rr) if t == "L" else two_stage_pe(g1, n, g2, roe[t], rr)) + cash_ps for t in TIERS) for rr in (0.09, 0.08)}
    cap_deck = deck(g_cap(r), g1)[1]
    mkt_g, mkt_ok = implied_g((inp["price"] - cash_ps) / ops["M"], roe["M"], r)
    implied_r = _implied_r(inp["price"], ops["M"], roe["M"], g1, n, g2, cash_ps)
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)

    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 4 龙头制造, A19) g1(2028)={g1:.4f} n={n} g2={g2:.4f} (foundry cluster median {inp['g_peer_median']:.4f}, tier-1 source, cap {g_cap(r):.3f}; own band NOT used to solve g2)")
    print(f"operating equity {equity_op / 1e9:.3f}B = book {inp['equity'] / 1e9:.3f}B - net cash {inp['net_cash'] / 1e9:.3f}B; SBC stripped {sbc_ps:.4f}/sh; interest stripped {nii_ps:.4f}/sh; cash added back {cash_ps:.4f}/sh")
    for t in TIERS:
        extra = f"  stage-1 payout {p1[t]:+.2f} (cash/external-funded growth)" if t in p1 else ""
        print(f"{t}: street {street[t]:.4f} -> econ {ops[t]:.4f}  ROE_op {roe[t]:.4f}  PE {pes[t]:.4f}x -> {ops[t] * pes[t]:.4f} + cash = {anchors[t]:.4f}{extra}")
    print(f"ROE basis (A20): BPS_op opening-2027 = {opening_bps(ops['L'], g2):.2f}/{opening_bps(ops['M'], g1):.2f}/{opening_bps(ops['H'], g1):.2f} "
          f"(2Q26 op book {bps_op_2q26:.2f} rolled over 2H26 unbooked {unbooked:.3f}/sh at b1 = g/ROE = {b1['L']:.2f}/{b1['M']:.2f}/{b1['H']:.2f}, "
          f"g_roll {g2:.2%}/{g1:.2%}/{g1:.2%}); 2Q26-book basis would read ROE {roe_2q26['L']:.4f}/{roe_2q26['M']:.4f}/{roe_2q26['H']:.4f}; "
          f"ROE_M - r = {roe['M'] - r:+.4f} (病态区, multiple pinned near 1/r)")
    print(f"B bucket (actual retention {ret_actual:.0%} − b1) × 2H26 unbooked → {excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh "
          f"(L positive = cash the model deems distributed but the company keeps; M/H negative = external/cash-pool funding the model books; disclosure only, not a leg, not in BPS)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  zone={zone}  price={inp['price']:.2f}  P/M={inp['price'] / M:.3f} P/H={inp['price'] / H:.3f}")
    print(f"flat ladder @ PE_M {pes['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {L / M:.3f} (= num {ops['L'] / ops['M']:.3f} x pe {pes['L'] / pes['M']:.3f}) | H/M {H / M:.3f} (num {ops['H'] / ops['M']:.3f} x pe {pes['H'] / pes['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"③ guardrail own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] on anchor/street-FY27 basis: L {band_basis['L']:.1f}x M {band_basis['M']:.2f}x H {band_basis['H']:.1f}x "
          f"({sum(1 for t in TIERS if band_basis[t] < inp['pe_own_min'])} of 3 below the floor; A7)")
    if band_basis["M"] < inp["pe_own_min"]:
        print(f"WARN (A18): PE_M {band_basis['M']:.2f}x < pe_own_min {inp['pe_own_min']:g} — ③ breach, but the band was judged distorted at step 1b "
              f"(IPO-month perfect-foresight floor; 2022 priced growth that never came) → ③ indeterminate: ruler stays in 篮 4 (already the floor), no band-edge r, zone read as is")
    print(f"FLOOR (disclosure only, not max()'d): realised PB low {inp['pb_own_min']:g}x x BVPS {inp['bvps']:g} = {pb_low_coord:.2f} {'ABOVE M' if pb_low_coord > M else 'below M'} (A8)")
    print(f"DISCLOSURE price-implied r (two-stage, M numerator) = {implied_r:.4f} vs 篮 4 {r:g} ({implied_r - r:+.4f})")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.4f}) -> {lo['L']:.2f}/{lo['M']:.2f}/{lo['H']:.2f} zone {lo_zone}; "
          + (f"+1pp ({g2 + 0.01:.4f}) -> {hi['L']:.2f}/{hi['M']:.2f}/{hi['H']:.2f} zone {hi_zone}" if hi else "+1pp exceeds cap"))
    if lo_zone != zone or (hi_zone is not None and hi_zone != zone):
        print(f"WARN (A5): zone moves within g2 +-1pp ({lo_zone} / {zone} / {hi_zone}) — the price sits on H (P/H {inp['price'] / H:.3f}); g2 is the cluster median, not a free choice; disclosed, not failed")
    print(f"contrast no-transition: {no_tr[0]:.2f}/{no_tr[1]:.2f}/{no_tr[2]:.2f} | SBC not deducted: {nosbc_deck[0]:.2f}/{nosbc_deck[1]:.2f}/{nosbc_deck[2]:.2f} | total-equity ROE {roe_tot['L']:.3f}/{roe_tot['M']:.3f}/{roe_tot['H']:.3f} (2Q26, not rolled) no cash add-back: {tot[0]:.2f}/{tot[1]:.2f}/{tot[2]:.2f}")
    print(f"contrast r 9% / 8% (not a path, A18): {r_contrast[0.09][0]:.2f}/{r_contrast[0.09][1]:.2f}/{r_contrast[0.09][2]:.2f} | {r_contrast[0.08][0]:.2f}/{r_contrast[0.08][1]:.2f}/{r_contrast[0.08][2]:.2f}; "
          f"g2 at cap {g_cap(r):.0%}: {cap_deck['L']:.2f}/{cap_deck['M']:.2f}/{cap_deck['H']:.2f} (M/FY27 street {cap_deck['M'] / inp['eps_2027_m']:.2f}x)")
    print(f"market-implied perpetual g (no transition, econ M) {mkt_g:.4f} well_conditioned={mkt_ok}")
    print(f"V_opt={v_opt:.2f} (1 x Tower-sized SiPho leg: NI/sh {unit_ni_ps:.4f} x PE_H perp {perpetual_pe(g2, roe['H'], r):.2f}x); zone+V {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f} A'={a2:.2f} B'={b2:.2f} zone+V={zone_of(inp['price'], *opt)}")
    print(f"A2f endpoint: P {inp['price']:.2f} {'<=' if inp['price'] <= H + v_opt else '>'} H+V_opt {H + v_opt:.2f}; implied p=(P-H)/V_opt={(inp['price'] - H) / v_opt:.2f}")
    print(f"candidate (Analyst Day 2028 model: rev {rev_2028 / 1e9:.3f}B x OpM {inp['opm_model_2028']:g} -> NI {ni_2028 / 1e9:.3f}B -> econ EPS {econ_2028:.3f} -> g1' {g1_cand:.4f} vs consensus {g1:.4f}): "
          f"L'/M'/H' {cand_band[0]:.2f}/{cand_band[1]:.2f}/{cand_band[2]:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
