#!/usr/bin/env python3
"""GFS.US valuation eval — recompute anchors from frameworks/GFS.US.md.

formula_id: gfs_gordon_twoleg_2027_v3

Two-leg Gordon on the FY2027 consensus (21 houses; the furthest year with a
>=2-house *range*, valuation-rules 裁决顺序 ②), with the SiPho leg on the
peer-ruler axis `_AXIS.sipho-wafer` (frameworks/axes/sipho-wafer.md; valuation-
rules「数据优先级与同业同尺」, 2026-10-03).  Company numerators are the street
non-GAAP figures less after-tax SBC (A9) and after-tax net interest (A6); the
net cash comes back per share.  L = the digestion year (FY2027 held at the
FY2026 consensus mean, A3).

Leg split (group ruler, A21):
- SiPho profit share = SiPho revenue x (group SiPho gross margin, borrowed
  from TSEM's own inference - own opex ratio) / company pre-tax economic
  profit; the rest leg is the residual.  L uses FY2026 revenue, M the FY2027
  path; H keeps the M share.
- Capital share = SiPho share of revenue in the numerator year.
- Leg g1 (M/H, 2028): SiPho = its revenue growth; rest = the residual that
  closes to the company g1 (2028E / 2027E GAAP consensus).
- Leg g2: SiPho = optical cluster capped; rest = foundry cluster.
- Leg ROE = leg earnings / (opening-2027 operating book x capital share); the
  book is rolled the A20 way at the company g (L: share-weighted g2).

The own forward-PE band is the ③ guardrail on the company multiple; it was
judged distorted at step 1b (A18), so a breach WARNs.  V_opt = the company's
2030 SiPho target above the 2028 path, valued on the SiPho leg's ruler in 2030
and discounted to FY2027 (A10).  Candidate band swaps the consensus company g1
for the Analyst Day 2028 model (A17).  No current price is read here.

Run:  python3 frameworks/eval/GFS.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    check_transition_years,
    g_cap,
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
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "GFS.US.md"
PEER = REPO_ROOT / "frameworks" / "axes" / "sipho-wafer.md"
FORMULA_ID = "gfs_gordon_twoleg_2027_v3"
TOL = 0.05
MIN_R_MINUS_G = 0.02
NUM_YEAR = 2027
P_TIERS = (0.0, 0.25, 1.0)  # A10 — table 3 only, never an input
LISTING_CCY = "USD"
SHARED = ("g2_sipho_src", "gm_sipho", "t_align")

REQUIRED = [
    "shares", "equity", "net_cash", "nii_4q", "sbc_annual", "tax",
    "eps_2026_m", "eps_1h26_a", "payout_3y",
    "eps_2027_l", "eps_2027_m", "eps_2027_h", "eps_2027_gaap_m", "eps_2028_gaap_m",
    "n_stage", "n_consensus", "r_perp", "pe_own_min", "pe_own_max", "bvps", "pb_own_min",
    "rev_2025", "cagr_model", "cagr_model_hi", "opm_model_2028",
    "rev_2026", "rev_2027", "sipho_rev_2026", "sipho_rev_2027", "sipho_rev_2028", "opex_ratio",
    *SHARED, "opt_rev", "t_opt",
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


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A19)")
    r = inp["r_perp"]
    errs += check_r(r, "r_perp", baskets.get("r_perp"))
    for leg in ("sipho", "rest"):
        g = min(inp[f"g2_{leg}_src"], g_cap(r))
        errs += check_g_cap(g, r, f"g2_{leg}")
        if r - g < MIN_R_MINUS_G:
            errs.append(f"r - g2_{leg} = {r - g:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if not inp["eps_2027_gaap_m"] < inp["eps_2028_gaap_m"]:
        errs.append("2028E GAAP consensus not above 2027E: same-world gate for g2 > 0 no longer holds (A4/A5)")
    errs += ladder("consensus range", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    if not inp["eps_2026_m"] < inp["eps_2027_l"]:
        errs.append("digestion-year numerator is not below the FY27 consensus low (A3)")
    errs += ladder("SiPho revenue path", inp["sipho_rev_2026"], inp["sipho_rev_2027"], inp["sipho_rev_2028"])
    if inp["equity"] - inp["net_cash"] <= 0:
        errs.append("operating equity (equity - net_cash) is not positive (A6)")
    if inp["t_opt"] <= NUM_YEAR:
        errs.append("option year must lie after the numerator year (A10)")
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

    # ---- Peer-ruler axis (_AXIS.sipho-wafer): shared rows must match the axis file ----
    if PEER.is_file():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        for k in SHARED:
            if k not in peer or abs(peer[k] - inp[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.sipho-wafer {peer.get(k)} — the leg ruler drifted")
    else:
        errors.append("frameworks/axes/sipho-wafer.md missing — leg ruler unchecked")

    r, n = inp["r_perp"], int(inp["n_stage"])
    g2s, g2r = min(inp["g2_sipho_src"], g_cap(r)), min(inp["g2_rest_src"], g_cap(r))
    g1 = inp["eps_2028_gaap_m"] / inp["eps_2027_gaap_m"] - 1.0
    street = {"L": inp["eps_2026_m"], "M": inp["eps_2027_m"], "H": inp["eps_2027_h"]}

    # ---- Step 1: company economic EPS (A9, A6) ----
    sbc_ps = inp["sbc_annual"] * (1.0 - inp["tax"]) / inp["shares"]
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    bps_op_2q26 = equity_op / inp["shares"]
    unbooked = (inp["eps_2026_m"] - inp["eps_1h26_a"]) - 0.5 * sbc_ps - 0.5 * nii_ps

    def deck(num: dict[str, float] | None = None, gm: float = inp["gm_sipho"], g2s_: float = g2s, g2r_: float = g2r,
             cap_mult: float = 1.0, g1_: float = g1, rr: float | None = None, unb: float = unbooked):
        num = {t: street[t] - sbc_ps - nii_ps for t in TIERS} if num is None else num
        rr = r if rr is None else rr
        oi = {y: inp[f"sipho_rev_{y}"] * (gm - inp["opex_ratio"]) for y in (2026, 2027)}
        pre = {t: num[t] * inp["shares"] / (1.0 - inp["tax"]) for t in TIERS}
        sh = {"L": oi[2026] / pre["L"], "M": oi[2027] / pre["M"]}
        sh["H"] = sh["M"]
        cap = {"L": inp["sipho_rev_2026"] / inp["rev_2026"], "M": inp["sipho_rev_2027"] / inp["rev_2027"]}
        cap["H"] = cap["M"]
        cap = {t: min(cap[t] * cap_mult, 0.95) for t in TIERS}
        g1s = inp["sipho_rev_2028"] / inp["sipho_rev_2027"] - 1.0
        g1r = (g1_ - sh["M"] * g1s) / (1.0 - sh["M"])
        out = {}
        for t in TIERS:
            g_roll = sh[t] * g2s_ + (1.0 - sh[t]) * g2r_ if t == "L" else g1_
            frac = g_roll * unb / num[t]
            if frac >= 1.0:
                raise ValueError(f"{t}: book roll diverges, g·N/eps = {frac:.2f} >= 1 (BLOCKED-by-rule)")
            bps = bps_op_2q26 / (1.0 - frac)
            es, er = num[t] * sh[t], num[t] * (1.0 - sh[t])
            roe_s, roe_r = es / (bps * cap[t]), er / (bps * (1.0 - cap[t]))
            if t == "L":
                pe_s, pe_r = perpetual_pe(g2s_, roe_s, rr), perpetual_pe(g2r_, roe_r, rr)
            else:
                pe_s, pe_r = two_stage_pe(g1s, n, g2s_, roe_s, rr), two_stage_pe(g1r, n, g2r_, roe_r, rr)
            out[t] = dict(bps=bps, b1=g_roll / (num[t] / bps), sh=sh[t], cap=cap[t], es=es, er=er, roe_s=roe_s, roe_r=roe_r,
                          pe_s=pe_s, pe_r=pe_r, v_s=es * pe_s, v_r=er * pe_r, val=es * pe_s + er * pe_r + cash_ps)
        return out, g1s, g1r

    ops = {t: street[t] - sbc_ps - nii_ps for t in TIERS}
    base, g1s, g1r = deck()
    L, M, H = (base[t]["val"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)
    pe_co = {t: (base[t]["val"] - cash_ps) / ops[t] for t in TIERS}
    if not (ops["L"] < ops["M"] < ops["H"]):
        errors.append("numerator ladder broken (A2e-2c)")
    flat = [ops[t] * pe_co["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - base[t]["b1"]) * unbooked for t in TIERS}  # disclosure only

    # ---- ③ guardrail (A7) on the band's basis (anchor / street FY27 mean); breach WARNs (A18) ----
    band_basis = {t: base[t]["val"] / inp["eps_2027_m"] for t in TIERS}
    pb_low_coord = inp["pb_own_min"] * inp["bvps"]

    # ---- Option (A10): 2030 target above the 2028 path, SiPho leg ruler, discounted to FY2027 ----
    inc_ps = inp["opt_rev"] * (inp["gm_sipho"] - inp["opex_ratio"]) * (1.0 - inp["tax"]) / inp["shares"]
    v_opt = inc_ps * perpetual_pe(g2s, base["H"]["roe_s"], r) / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR)

    # ---- Candidate band (A17): Analyst Day 2028 model = a level range (construction §7h) ----
    # A company target is a ceiling: M′ goes to the range midpoint (CAGR 11%), H′ is capped at the
    # range top (CAGR 12%) — not the midpoint's growth multiplied onto H's higher FY27.
    def econ_at(cagr: float) -> float:
        rev_2028 = inp["rev_2025"] * (1.0 + cagr) ** 3
        return rev_2028 * inp["opm_model_2028"] * (1.0 - inp["tax"]) / inp["shares"] - sbc_ps - nii_ps
    econ_2028, econ_2028_hi = econ_at(inp["cagr_model"]), econ_at(inp["cagr_model_hi"])
    g1_cand = econ_2028 / ops["M"] - 1.0
    g1_cand_h = max(0.0, econ_2028_hi / ops["H"] - 1.0)
    cand = {"M": deck(g1_=g1_cand)[0]["M"], "H": deck(g1_=g1_cand_h)[0]["H"]}
    cand_band = (L, cand["M"]["val"], cand["H"]["val"])
    if not (cand_band[0] < cand_band[1] < cand_band[2]):
        errors.append(f"candidate band ladder broken: {cand_band}")

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
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

    # ---- Contrasts (printed only) ----
    def whole_company(g: float) -> tuple[float, ...]:
        res = []
        for t in TIERS:
            g_roll = g if t == "L" else g1
            roe = ops[t] / (bps_op_2q26 / (1.0 - g_roll * unbooked / ops[t]))
            pe = perpetual_pe(g, roe, r) if t == "L" else two_stage_pe(g1, n, g, roe, r)
            res.append(ops[t] * pe + cash_ps)
        return tuple(res)

    def trio(d: dict) -> str:
        return f"{d['L']['val']:.2f}/{d['M']['val']:.2f}/{d['H']['val']:.2f}"

    v2 = whole_company(g2r)
    nosbc = {t: street[t] - nii_ps for t in TIERS}
    nosbc_deck = deck(num=nosbc, unb=unbooked + 0.5 * sbc_ps)[0]
    r_contrast = {rr: deck(rr=rr)[0] for rr in (0.09, 0.08)}
    no_tr = deck(g1_=0.0)[0]
    rest_lo, rest_hi = deck(g2r_=g2r - 0.01)[0], deck(g2r_=g2r + 0.01)[0]
    sip_lo = deck(g2s_=g2s - 0.01)[0]
    cap_hi, cap_hi2 = deck(cap_mult=1.35)[0], deck(cap_mult=1.62)[0]
    gm_hi = deck(gm=0.555)[0]

    # Yield-lag haircut on the borrowed SiPho margin (A21): disclosure only, no source for its size.
    def v_opt_gm(gm: float, d: dict) -> float:
        inc = inp["opt_rev"] * (gm - inp["opex_ratio"]) * (1.0 - inp["tax"]) / inp["shares"]
        return inc * perpetual_pe(g2s, d["H"]["roe_s"], r) / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR)

    gm_lo = {gm: deck(gm=gm)[0] for gm in (0.45, 0.40)}
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)

    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 4, A19) g1 company {g1:.4f} -> SiPho {g1s:.4f} / rest {g1r:.4f} (residual) n={n}; g2 SiPho {g2s:.4f} (src {inp['g2_sipho_src']:.4f}) / rest {g2r:.4f}")
    print(f"econ EPS {ops['L']:.4f}/{ops['M']:.4f}/{ops['H']:.4f} (SBC {sbc_ps:.4f}, interest {nii_ps:.4f} stripped); cash {cash_ps:.4f}/sh; opex ratio {inp['opex_ratio']:g}; SiPho GM {inp['gm_sipho']:g}")
    for t in TIERS:
        d = base[t]
        print(f"{t}: BPS_op {d['bps']:.2f} (b1 {d['b1']:.2f}) share {d['sh']:.3f} cap {d['cap']:.3f} | SiPho E {d['es']:.4f} ROE {d['roe_s']:.4f} PE {d['pe_s']:.2f}x = {d['v_s']:.2f} | "
              f"rest E {d['er']:.4f} ROE {d['roe_r']:.4f} PE {d['pe_r']:.2f}x = {d['v_r']:.2f} | +cash = {d['val']:.2f} (company PE {pe_co[t]:.2f}x)")
    print(f"B bucket (actual retention {ret_actual:.0%} − b1) × 2H26 unbooked → {excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh (disclosure only)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat ladder @ PE_M {pe_co['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {L / M:.3f} (num {ops['L'] / ops['M']:.3f} x pe {pe_co['L'] / pe_co['M']:.3f}) | H/M {H / M:.3f} (num {ops['H'] / ops['M']:.3f} x pe {pe_co['H'] / pe_co['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"③ guardrail own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] on anchor/street-FY27 basis: L {band_basis['L']:.1f}x M {band_basis['M']:.2f}x H {band_basis['H']:.1f}x")
    if band_basis["M"] < inp["pe_own_min"]:
        print(f"WARN (A18): PE_M {band_basis['M']:.2f}x < pe_own_min {inp['pe_own_min']:g} — ③ breach, band judged distorted at step 1b → ③ indeterminate, anchors stand")
    print(f"FLOOR (disclosure only): PB low {inp['pb_own_min']:g}x x BVPS {inp['bvps']:g} = {pb_low_coord:.2f} {'ABOVE M' if pb_low_coord > M else 'below M'} (A8)")
    print(f"contrast whole-company v2 (g2 {g2r:.4f}): {v2[0]:.2f}/{v2[1]:.2f}/{v2[2]:.2f} | no transition {trio(no_tr)} | SBC not deducted {trio(nosbc_deck)}")
    print(f"contrast r 9% {trio(r_contrast[0.09])} / 8% {trio(r_contrast[0.08])}")
    print(f"g2 rest -1pp {trio(rest_lo)} / +1pp {trio(rest_hi)} | g2 SiPho -1pp {trio(sip_lo)}")
    print(f"capital share x1.35 {trio(cap_hi)} / x1.62 {trio(cap_hi2)} | SiPho GM 0.555 {trio(gm_hi)}")
    print("yield-lag haircut on the borrowed SiPho GM (A21, disclosure only): "
          + " | ".join(f"GM {gm:g} -> {trio(d)} V_opt {v_opt_gm(gm, d):.2f}" for gm, d in gm_lo.items()))
    print(f"V_opt={v_opt:.2f} ({inp['opt_rev'] / 1e9:.2f}B rev x (GM {inp['gm_sipho']:g} - opex {inp['opex_ratio']:g}) x (1-t) = {inc_ps:.4f}/sh x SiPho perp PE "
          f"{perpetual_pe(g2s, base['H']['roe_s'], r):.2f}x / 1.1^{int(inp['t_opt']) - NUM_YEAR}); zone+V {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f} A'={a2:.2f} B'={b2:.2f}")
    print(f"candidate (Analyst Day 2028 level: M econ {econ_2028:.3f} g1' {g1_cand:.4f}; H capped at econ"
          f" {econ_2028_hi:.3f} g1' {g1_cand_h:.4f}): L'/M'/H' {cand_band[0]:.2f}/{cand_band[1]:.2f}/{cand_band[2]:.2f}"
          f"  A' {(cand_band[0] + cand_band[1]) / 2:.2f} B' {(cand_band[1] + cand_band[2]) / 2:.2f}")

    def band_at(dr: float) -> tuple[float, float, float]:
        d = deck(rr=r + dr)[0]
        return d["L"]["val"], d["M"]["val"], d["H"]["val"]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    if any(abs(x - y) > TOL for x, y in zip(band_at(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("GFS.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
