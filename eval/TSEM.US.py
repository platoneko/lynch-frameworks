#!/usr/bin/env python3
"""TSEM.US valuation eval — recompute anchors from frameworks/TSEM.US.md.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」): which zone a
quote falls in is derived live by the daily digest and the app, so nothing
here reads a price.

formula_id: tsem_gordon_twoleg_2027_v3

Two-leg Gordon on the FY2027 consensus (the furthest year with a >=2-house
*range*, valuation-rules 裁决顺序 ②), with the SiPho leg on the peer-ruler axis
`_AXIS.sipho-wafer` (frameworks/axes/sipho-wafer.md; valuation-rules
「数据优先级与同业同尺」, 2026-10-03).  Company numerators are the street
adjusted figures less the GAAP-vs-adjusted gap (A8) and the after-tax interest
the cash pile earns (A6); the net cash comes back per share.  L = the
digestion year (FY2027 held at the FY2026 consensus mean).

Leg split (group ruler):
- SiPho profit share = SiPho revenue x (group SiPho gross margin - own opex
  ratio) / company pre-tax economic profit; the rest leg is the residual, so
  the legs close to consensus.  L uses FY2026 revenue, M the FY2027 path; H
  keeps the M share (the consensus spread is spread pro rata).
- Capital share = SiPho share of revenue in the numerator year (group rule).
- Leg g1 (M/H, 2028): SiPho = its own revenue growth at constant leg margin;
  rest = the residual that closes to the company g1 (2028E / 2027E).
- Leg g2: SiPho = optical cluster capped (group), rest = foundry cluster.
- Leg ROE = leg earnings / (opening-2027 operating book x capital share); the
  book is rolled the A16 way at the company g (L: share-weighted g2).

The SiPho gross margin is this ticker's own two-period inference (A17) and is
the group value GFS borrows.  V_opt = Track 2 sized as one own realised SiPho
leg (snapshot lower bound: the x4 Japan capacity has no revenue base), valued
on the SiPho leg's ruler at its year and discounted to FY2027 (A9).

Cross-file: shared rows must equal frameworks/axes/sipho-wafer.md.

Run:  python3 frameworks/eval/TSEM.US.py
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

FRAMEWORK = REPO_ROOT / "frameworks" / "TSEM.US.md"
PEER = REPO_ROOT / "frameworks" / "axes" / "sipho-wafer.md"
FORMULA_ID = "tsem_gordon_twoleg_2027_v3"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
NUM_YEAR = 2027
P_TIERS = (0.0, 0.25, 1.0)  # A9 — table 3 only, never an input
SHARED = ("g2_sipho_src", "gm_sipho", "t_align")

REQUIRED = [
    "shares", "equity", "net_cash", "nii_4q", "gaap_gap_ps", "tax",
    "eps_2026_m", "eps_1h26_a", "payout_3y",
    "eps_2027_l", "eps_2027_m", "eps_2027_h", "eps_2027_gaap_m", "eps_2028_gaap_m",
    "n_stage", "n_consensus", "r_perp", "pe_own_min", "pe_own_max", "bvps", "pb_floor",
    "rev_2026", "rev_2027", "sipho_rev_2026", "sipho_rev_2027", "sipho_rev_2028", "opex_ratio",
    *SHARED, "opt_rev", "t_opt",
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


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A15)")
    r = inp["r_perp"]
    errs += check_r(r, "r_perp", baskets.get("r_perp"))
    for leg in ("sipho", "rest"):
        g = min(inp[f"g2_{leg}_src"], g_cap(r))
        errs += check_g_cap(g, r, f"g2_{leg}")
        if r - g < MIN_R_MINUS_G:
            errs.append(f"r - g2_{leg} = {r - g:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if not inp["eps_2027_gaap_m"] < inp["eps_2028_gaap_m"]:
        errs.append("2028E consensus not above 2027E: same-world gate for g2 > 0 no longer holds (A4/A5)")
    errs += ladder("consensus range", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    if not inp["eps_2026_m"] < inp["eps_2027_l"]:
        errs.append("digestion-year numerator is not below the FY27 consensus low (A3)")
    errs += ladder("SiPho revenue path", inp["sipho_rev_2026"], inp["sipho_rev_2027"], inp["sipho_rev_2028"])
    if inp["equity"] - inp["net_cash"] <= 0:
        errs.append("operating equity (equity - net_cash) is not positive (A6)")
    if inp["t_opt"] <= NUM_YEAR:
        errs.append("option year must lie after the numerator year (A9)")
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

    # ---- Step 1: company economic EPS (A8, A6) ----
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    ops = {t: street[t] - inp["gaap_gap_ps"] - nii_ps for t in TIERS}
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    bps_op_2q26 = equity_op / inp["shares"]
    unbooked = (inp["eps_2026_m"] - inp["eps_1h26_a"]) - 0.5 * inp["gaap_gap_ps"] - 0.5 * nii_ps

    # ---- Step 2: leg split (group ruler) ----
    def split(gm: float, cap_mult: float = 1.0):
        oi = {y: inp[f"sipho_rev_{y}"] * (gm - inp["opex_ratio"]) for y in (2026, 2027, 2028)}
        pre = {t: ops[t] * inp["shares"] / (1.0 - inp["tax"]) for t in TIERS}
        sh = {"L": oi[2026] / pre["L"], "M": oi[2027] / pre["M"]}
        sh["H"] = sh["M"]
        cap = {"L": inp["sipho_rev_2026"] / inp["rev_2026"], "M": inp["sipho_rev_2027"] / inp["rev_2027"]}
        cap["H"] = cap["M"]
        cap = {t: min(cap[t] * cap_mult, 0.95) for t in TIERS}
        g1s = inp["sipho_rev_2028"] / inp["sipho_rev_2027"] - 1.0
        return sh, cap, g1s

    def deck(gm: float = inp["gm_sipho"], g2s_: float = g2s, g2r_: float = g2r, cap_mult: float = 1.0, g1_: float = g1, rr: float | None = None):
        rr = r if rr is None else rr
        sh, cap, g1s = split(gm, cap_mult)
        g1r = (g1_ - sh["M"] * g1s) / (1.0 - sh["M"])
        out = {}
        for t in TIERS:
            g_roll = sh[t] * g2s_ + (1.0 - sh[t]) * g2r_ if t == "L" else g1_
            frac = g_roll * unbooked / ops[t]
            if frac >= 1.0:
                raise ValueError(f"{t}: book roll diverges, g·N/eps = {frac:.2f} >= 1 (BLOCKED-by-rule)")
            bps = bps_op_2q26 / (1.0 - frac)
            es, er = ops[t] * sh[t], ops[t] * (1.0 - sh[t])
            roe_s, roe_r = es / (bps * cap[t]), er / (bps * (1.0 - cap[t]))
            if t == "L":
                pe_s, pe_r = perpetual_pe(g2s_, roe_s, rr), perpetual_pe(g2r_, roe_r, rr)
            else:
                pe_s, pe_r = two_stage_pe(g1s, n, g2s_, roe_s, rr), two_stage_pe(g1r, n, g2r_, roe_r, rr)
            out[t] = dict(bps=bps, sh=sh[t], cap=cap[t], es=es, er=er, roe_s=roe_s, roe_r=roe_r,
                          pe_s=pe_s, pe_r=pe_r, v_s=es * pe_s, v_r=er * pe_r, val=es * pe_s + er * pe_r + cash_ps)
        return out, g1s, g1r

    base, g1s, g1r = deck()
    L, M, H = (base[t]["val"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)
    pe_co = {t: (base[t]["val"] - cash_ps) / ops[t] for t in TIERS}
    for t in TIERS:
        if not inp["pe_own_min"] - TOL <= pe_co[t] <= inp["pe_own_max"] + TOL:
            errors.append(f"{t} company multiple {pe_co[t]:.2f}x outside own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] (③)")
    if not (ops["L"] < ops["M"] < ops["H"]):
        errors.append("numerator ladder broken (A2e-2c)")
    flat = [ops[t] * pe_co["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # ---- Option (A9): own realised SiPho leg at the SiPho leg's ruler, discounted to FY2027 ----
    def v_opt_at(d: dict) -> float:
        inc = inp["opt_rev"] * (inp["gm_sipho"] - inp["opex_ratio"]) * (1.0 - inp["tax"]) / inp["shares"]
        return inc * perpetual_pe(g2s, d["H"]["roe_s"], r) / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR)

    v_opt = v_opt_at(base)

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs A9 {P_TIERS}")

    # ---- Contrasts (printed only) ----
    def whole_company(g: float) -> tuple[float, ...]:
        res = []
        for t in TIERS:
            g_roll = g if t == "L" else g1
            roe = ops[t] / (bps_op_2q26 / (1.0 - g_roll * unbooked / ops[t]))
            pe = perpetual_pe(g, roe, r) if t == "L" else two_stage_pe(g1, n, g, roe, r)
            res.append(ops[t] * pe + cash_ps)
        return tuple(res)

    v2 = whole_company(g_cap(r))
    rest_lo = deck(g2r_=g2r - 0.01)[0]
    rest_hi = deck(g2r_=g2r + 0.01)[0]
    sip_lo = deck(g2s_=g2s - 0.01)[0]
    cap_hi = deck(cap_mult=1.35)[0]
    cap_hi2 = deck(cap_mult=1.62)[0]
    gm_hi = deck(gm=0.555)[0]
    no_tr = deck(g1_=0.0)[0]

    def trio(d: dict) -> str:
        return f"{d['L']['val']:.2f}/{d['M']['val']:.2f}/{d['H']['val']:.2f}"

    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 4, A15) g1 company {g1:.4f} -> SiPho {g1s:.4f} / rest {g1r:.4f} (residual) n={n}; g2 SiPho {g2s:.4f} (src {inp['g2_sipho_src']:.4f}) / rest {g2r:.4f}")
    print(f"econ EPS {ops['L']:.4f}/{ops['M']:.4f}/{ops['H']:.4f}; cash {cash_ps:.4f}/sh; opex ratio {inp['opex_ratio']:g}; SiPho GM {inp['gm_sipho']:g}")
    for t in TIERS:
        d = base[t]
        print(f"{t}: BPS_op {d['bps']:.2f} share {d['sh']:.3f} cap {d['cap']:.3f} | SiPho E {d['es']:.4f} ROE {d['roe_s']:.4f} PE {d['pe_s']:.2f}x = {d['v_s']:.2f} | "
              f"rest E {d['er']:.4f} ROE {d['roe_r']:.4f} PE {d['pe_r']:.2f}x = {d['v_r']:.2f} | +cash = {d['val']:.2f} (company PE {pe_co[t]:.2f}x)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] company multiples {pe_co['L']:.2f}/{pe_co['M']:.2f}/{pe_co['H']:.2f}x")
    print(f"flat ladder @ PE_M {pe_co['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {L / M:.3f} (num {ops['L'] / ops['M']:.3f} x pe {pe_co['L'] / pe_co['M']:.3f}) | H/M {H / M:.3f} (num {ops['H'] / ops['M']:.3f} x pe {pe_co['H'] / pe_co['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"contrast whole-company v2 (g2 6%): {v2[0]:.2f}/{v2[1]:.2f}/{v2[2]:.2f} | no transition: {trio(no_tr)}")
    print(f"g2 rest -1pp {trio(rest_lo)} / +1pp {trio(rest_hi)} | g2 SiPho -1pp {trio(sip_lo)}")
    print(f"capital share x1.35 {trio(cap_hi)} / x1.62 {trio(cap_hi2)} | SiPho GM 0.555 {trio(gm_hi)}")
    print(f"floor (disclosed only) PB {inp['pb_floor']:g} x BVPS {inp['bvps']:g} = {inp['pb_floor'] * inp['bvps']:.2f}")

    def band_rf(dr: float) -> tuple[float, float, float]:
        d = deck(rr=r + dr)[0]
        return d["L"]["val"], d["M"]["val"], d["H"]["val"]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    print(f"V_opt={v_opt:.2f} (Track 2 = {inp['opt_rev'] / 1e9:.2f}B rev x (GM {inp['gm_sipho']:g} - opex {inp['opex_ratio']:g}) x (1-t) -> "
          f"x SiPho perp PE {perpetual_pe(g2s, base['H']['roe_s'], r):.2f}x / 1.1^{int(inp['t_opt']) - NUM_YEAR}); zone+V {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f} A'={a2:.2f} B'={b2:.2f}")
    if not errors:
        write_rf_readings("TSEM.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
