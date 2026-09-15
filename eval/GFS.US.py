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

Multiples are generated, not borrowed: tier ROE on *operating* equity (book
less net cash, A6), r = 10% (operating tier), M/H carry the FY2028 consensus
year as a one-year transition (`two_stage_pe`, g1 = 2028E / 2027E on the same
GAAP consensus line, n = 1; A4) and L does not.  g2 = the foundry cluster's
reverse-solved median (tier-1 source, A5) — NOT reverse-solved to the own
band: on 2026-09-14 the user ruled the own realised forward-PE band [15.6,
46.2] down from a hard guardrail (裁决顺序 ③) to a disclosure for this ticker,
because no g <= 6% can lift a ~12% operating-ROE business into a band the
market printed while pricing something Gordon-on-average-ROE cannot express
(A7).  For the same reason the realised PB low is printed as a coordinate,
not used as a floor (A8).  This eval prints the band comparison and the g2
+-1pp zones and warns on a flip; it does not fail on either.

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


def sanity_checks(inp: dict[str, float]) -> list[str]:
    errs: list[str] = []
    errs += check_r(inp["r_perp"], "r_perp")
    if abs(inp["r_perp"] - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={inp['r_perp']}: operating leg, expected {R_OPERATING}")
    errs += check_g_cap(inp["g2"], "g2")
    # A5: g2 is the peer cluster median (tier-1 source) truncated to the cap — no band reverse-solve.
    if abs(inp["g2"] - min(inp["g_peer_median"], G_CAP)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {G_CAP}) — A5")
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
    errors = sanity_checks(inp)

    r, g2, n = inp["r_perp"], inp["g2"], int(inp["n_stage"])
    g1 = inp["eps_2028_gaap_m"] / inp["eps_2027_gaap_m"] - 1.0
    street = {"L": inp["eps_2026_m"], "M": inp["eps_2027_m"], "H": inp["eps_2027_h"]}

    # ---- Step 1: economic EPS = street non-GAAP less after-tax SBC and after-tax net interest (A9, A6) ----
    sbc_ps = inp["sbc_annual"] * (1.0 - inp["tax"]) / inp["shares"]
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    ops = {t: street[t] - sbc_ps - nii_ps for t in TIERS}

    # ---- Step 2: tier ROE on operating equity; Gordon (L) / two-stage (M, H) ----
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    roe = {t: ops[t] * inp["shares"] / equity_op for t in TIERS}

    def deck(g: float, g1_: float) -> tuple[dict[str, float], dict[str, float]]:
        pe = {
            "L": perpetual_pe(g, roe["L"], r),
            "M": two_stage_pe(g1_, n, g, roe["M"], r),
            "H": two_stage_pe(g1_, n, g, roe["H"], r),
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

    # ---- Disclosure only (A7/A8): own band on the band's own basis (anchor / street FY27 mean), realised PB low ----
    band_basis = {t: anchors[t] / inp["eps_2027_m"] for t in TIERS}
    pb_low_coord = inp["pb_own_min"] * inp["bvps"]

    # ---- g2 leverage: both ends printed; a flip is disclosed, not failed (A5, price sits on H) ----
    lo = deck(g2 - 0.01, g1)[1]
    hi = deck(g2 + 0.01, g1)[1] if g2 + 0.01 <= G_CAP + 1e-9 else None
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

    # ---- Contrast bands (printed only) ----
    no_tr = tuple(ops[t] * perpetual_pe(g2, roe[t], r) + cash_ps for t in TIERS)
    roe_tot = {t: (street[t] - sbc_ps) * inp["shares"] / inp["equity"] for t in TIERS}
    tot = ((street["L"] - sbc_ps) * perpetual_pe(g2, roe_tot["L"], r), (street["M"] - sbc_ps) * two_stage_pe(g1, n, g2, roe_tot["M"], r), (street["H"] - sbc_ps) * two_stage_pe(g1, n, g2, roe_tot["H"], r))
    nosbc = {t: street[t] - nii_ps for t in TIERS}
    roe_nosbc = {t: nosbc[t] * inp["shares"] / equity_op for t in TIERS}
    nosbc_deck = (nosbc["L"] * perpetual_pe(g2, roe_nosbc["L"], r) + cash_ps, nosbc["M"] * two_stage_pe(g1, n, g2, roe_nosbc["M"], r) + cash_ps, nosbc["H"] * two_stage_pe(g1, n, g2, roe_nosbc["H"], r) + cash_ps)
    mkt_g, mkt_ok = implied_g((inp["price"] - cash_ps) / ops["M"], roe["M"], r)
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)

    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} g1(2028)={g1:.4f} n={n} g2={g2:.4f} (foundry cluster median {inp['g_peer_median']:.4f}, tier-1 source; own band NOT used to solve g2)")
    print(f"operating equity {equity_op / 1e9:.3f}B = book {inp['equity'] / 1e9:.3f}B - net cash {inp['net_cash'] / 1e9:.3f}B; SBC stripped {sbc_ps:.4f}/sh; interest stripped {nii_ps:.4f}/sh; cash added back {cash_ps:.4f}/sh")
    for t in TIERS:
        extra = f"  stage-1 payout {p1[t]:+.2f} (cash/external-funded growth)" if t in p1 else ""
        print(f"{t}: street {street[t]:.4f} -> econ {ops[t]:.4f}  ROE_op {roe[t]:.4f}  PE {pes[t]:.4f}x -> {ops[t] * pes[t]:.4f} + cash = {anchors[t]:.4f}{extra}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  zone={zone}  price={inp['price']:.2f}  P/M={inp['price'] / M:.3f} P/H={inp['price'] / H:.3f}")
    print(f"flat ladder @ PE_M {pes['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {L / M:.3f} (= num {ops['L'] / ops['M']:.3f} x pe {pes['L'] / pes['M']:.3f}) | H/M {H / M:.3f} (num {ops['H'] / ops['M']:.3f} x pe {pes['H'] / pes['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"DISCLOSURE own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] on anchor/street-FY27 basis: L {band_basis['L']:.1f}x M {band_basis['M']:.1f}x H {band_basis['H']:.1f}x "
          f"({sum(1 for t in TIERS if band_basis[t] < inp['pe_own_min'])} of 3 below the floor; guardrail ruled down to disclosure 2026-09-14, A7)")
    print(f"DISCLOSURE realised PB low {inp['pb_own_min']:g}x x BVPS {inp['bvps']:g} = {pb_low_coord:.2f} {'ABOVE M' if pb_low_coord > M else 'below M'} — coordinate only, not a floor (A8)")
    print(f"g2 leverage: -1pp ({g2 - 0.01:.4f}) -> {lo['L']:.2f}/{lo['M']:.2f}/{lo['H']:.2f} zone {lo_zone}; "
          + (f"+1pp ({g2 + 0.01:.4f}) -> {hi['L']:.2f}/{hi['M']:.2f}/{hi['H']:.2f} zone {hi_zone}" if hi else "+1pp exceeds cap"))
    if lo_zone != zone or (hi_zone is not None and hi_zone != zone):
        print(f"WARN (A5): zone moves within g2 +-1pp ({lo_zone} / {zone} / {hi_zone}) — the price sits on H (P/H {inp['price'] / H:.3f}); g2 is the cluster median, not a free choice; disclosed, not failed")
    print(f"contrast no-transition: {no_tr[0]:.2f}/{no_tr[1]:.2f}/{no_tr[2]:.2f} | SBC not deducted: {nosbc_deck[0]:.2f}/{nosbc_deck[1]:.2f}/{nosbc_deck[2]:.2f} | total-equity ROE {roe_tot['L']:.3f}/{roe_tot['M']:.3f}/{roe_tot['H']:.3f} no cash add-back: {tot[0]:.2f}/{tot[1]:.2f}/{tot[2]:.2f}")
    print(f"market-implied perpetual g (no transition, econ M) {mkt_g:.4f} well_conditioned={mkt_ok}")
    print(f"V_opt={v_opt:.2f} (1 x Tower-sized SiPho leg: NI/sh {unit_ni_ps:.4f} x PE_H perp {perpetual_pe(g2, roe['H'], r):.2f}x); zone+V {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f} A'={a2:.2f} B'={b2:.2f} zone+V={zone_of(inp['price'], *opt)}")
    print(f"A2f endpoint: P {inp['price']:.2f} {'<=' if inp['price'] <= H + v_opt else '>'} H+V_opt {H + v_opt:.2f}; implied p=(P-H)/V_opt={(inp['price'] - H) / v_opt:.2f}")
    print(f"candidate (Analyst Day 2028 model: rev {rev_2028 / 1e9:.3f}B x OpM {inp['opm_model_2028']:g} -> NI {ni_2028 / 1e9:.3f}B -> econ EPS {econ_2028:.3f} -> g1' {g1_cand:.4f} vs consensus {g1:.4f}): "
          f"L'/M'/H' {cand_band[0]:.2f}/{cand_band[1]:.2f}/{cand_band[2]:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
