#!/usr/bin/env python3
"""VST.US (Vistra) valuation eval — recompute anchors from frameworks/VST.US.md.

frameworks/VST.US.md is the source of truth; this script re-derives L/M/H, the
cut points, the option credit, the candidate band and the 表2′ band-edge band
from the §3 Inputs table and exits 1 on mismatch.  The doc carries no current
price (AGENTS.md「现价 — 禁写契约」), so nothing here reads one.

formula_id: vst_sotp_retail_gen_mfcf_gordon_v3

v3 (2026-10-04, valuation-rules「③ 出带处理流程」步 1c): ③ compares the band
with the base on the same footing.  ① The PPA premia public at the band floor
(Comanche Peak 8-K 2025-09-29, Meta 8-K 2026-01-09) are in the band price, so
the generated M multiple carries V_opt at p = 1.  ② The increments in today's
2027 numerator that the band's 2027 EBITDA (management target, ex Cogentrix /
Meta) leaves out -- Cogentrix (8-K 2026-01-05) and the Meta 2027 part,
incr_2027_ebitda -- are priced on the generation-leg ruler, less the
consideration still owed at the band floor, discounted to the floor date and
taken off the band EV before the band multiple is formed.  Each basket on the
ladder is tested this way; the 表2′ band-edge r solves the same equality.

v2 (2026-10-03, valuation-rules「未建模期权」时点折现): the PPA premia are an
annuity at basket 1 from the realisation year t_opt (2028, first contracted
delivery year), valued one period before its first flow, then carried back to
the numerator year at the base basket r (r_gen), not at the contract rate.

Main ruler: two-leg SOTP on 2027 unlevered maintenance free cash flow
(Ongoing Ops adjusted EBITDA − maintenance capex incl. nuclear fuel − tax at a
normalised rate on EBITDA − D&A), each leg × Gordon multiple
(1 − g2/ROIC)/(r − g2) — ROIC, not ROE, because the leverage gate fires (A10).
Leg EVs are summed, then the closure (net debt, preferred, Cogentrix
consideration, Cogentrix tax-benefit NPV) is subtracted and the result divided
by post-Cogentrix shares.  The H tier carries the ①b top discount k_H on the
deemed-paid-out window retention (A11).

    Retail leg      basket 4 (r 10%): TXU sets its own retail price.
    Generation leg  initial basket 6 (13%, commodity function); ③ steps it to
                    basket 4 on the forward EV/EBITDA band, and it is still
                    below the band there — the user saw that and landed it
                    (A12), so 13% survives only as the 对照坐标 band.

V_opt: data-centre PPA premia (Comanche Peak from the company's own FCFbG
accretion disclosure; Meta's existing-unit MW at the same per-MW premium),
basket 1 finite annuities.  Candidate band: GS single-house FY2028 EBITDA
in H′, discounted one year.

Run:  python3 frameworks/eval/VST.US.py
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
    basket_r,
    check_g_cap,
    check_r,
    perpetual_pe,
    recovery_two_stage_pe,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "VST.US.md"
FORMULA_ID = "vst_sotp_retail_gen_mfcf_gordon_v3"
NUM_YEAR = 2027  # numerator year = t1
TOL = 0.05
TIERS = ("l", "m", "h")
MIN_R_MINUS_G = 0.02

STATED_V_OPT = re.compile(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*")
STATED_P = re.compile(r"p_L/p_M/p_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*")
STATED_CAND = re.compile(r"L′ = \*\*([0-9.]+)\*\* · M′ = \*\*([0-9.]+)\*\* · H′ = \*\*([0-9.]+)\*\*")
STATED_EDGE = re.compile(r"带边带\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)")
STATED_INIT = re.compile(r"初分篮对照带\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)")
STATED_EDGE_R = re.compile(r"并列价带（非主尺：带边 r ([0-9.]+)%")
STATED_1C_X = re.compile(r"底牌 \+ 期权（p = 1）\*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)×\*\*")
STATED_1C_FLOOR = re.compile(r"同口径带下沿 \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)×\*\*")
LADDER = (6, 5, 4)  # basket ladder walked by ③ for the generation leg

REQUIRED = [
    "r_retail", "r_gen", "r_gen_init", "r_contract", "r_disc", "g2", "tax_rate",
    "ebitda_l", "ebitda_m", "ebitda_h", "retail_l", "retail_m", "retail_h",
    "da_total", "da_retail", "maint_retail", "maint_gen", "invested_capital",
    "net_debt", "pref", "cog_cash", "cog_debt", "cog_tax_npv", "shares", "cog_shares",
    "growth_capex", "window_years", "k_l", "k_m", "k_h",
    "fwd_band_min", "ebitda_2028_gs",
    "cp_fcfbg_base", "cp_accretion", "cp_mw", "cp_term", "meta_mw", "meta_2027_ebitda",
    "meta_term", "p_l", "p_m", "p_h", "t_opt",
    "band_ebitda", "band_floor_close", "incr_2027_ebitda", "band_t",
]
CP_RAMP = (0.0, 0.25, 0.50, 0.70, 0.85)  # 2027..2031 share of 1.2 GW, then 1.0 (A13)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    if FORMULA_ID not in md:
        errors.append(f"formula_id {FORMULA_ID} not in framework")

    baskets = parse_baskets(md)
    for key in ("r_retail", "r_gen", "r_contract"):
        if key not in baskets:
            errors.append(f"{key}: Inputs source cell must name 篮 N")
        else:
            errors += check_r(inp[key], key, baskets[key])
    for key in ("r_gen_init", "r_disc"):
        if key in baskets:
            errors.append(f"{key} is a disclosure r and must not carry 篮 N")

    t, g2 = inp["tax_rate"], inp["g2"]
    sh = inp["shares"] + inp["cog_shares"]
    closure = -(inp["net_debt"] + inp["pref"] + inp["cog_cash"] + inp["cog_debt"]) + inp["cog_tax_npv"]
    for key in ("r_retail", "r_gen", "r_gen_init"):
        errors += check_g_cap(g2, inp[key], key)
        if inp[key] - g2 < MIN_R_MINUS_G:
            errors.append(f"{key} − g2 < 2pp")

    def legs(ebitda: float, retail: float) -> tuple[float, float, float]:
        gen = ebitda - retail
        f_ret = retail - inp["maint_retail"] - t * (retail - inp["da_retail"])
        f_gen = gen - inp["maint_gen"] - t * (gen - (inp["da_total"] - inp["da_retail"]))
        roic = (ebitda - inp["da_total"]) * (1 - t) / inp["invested_capital"]
        return f_ret, f_gen, roic

    def ev_at(ebitda: float, retail: float, r_ret: float, r_gen: float, g: float = g2) -> float:
        f_ret, f_gen, roic = legs(ebitda, retail)
        return f_ret * perpetual_pe(g, roic, r_ret) + f_gen * perpetual_pe(g, roic, r_gen)

    # A11: deemed-paid-out window retention, priced only through k.
    f_ret_m, f_gen_m, roic_m = legs(inp["ebitda_m"], inp["retail_m"])
    excess_ps = (inp["growth_capex"] - g2 / roic_m * (f_ret_m + f_gen_m)) * inp["window_years"] / sh
    ks = tuple(inp[f"k_{x}"] for x in TIERS)
    if not ks[2] >= ks[1] >= ks[0] >= 0:
        errors.append(f"cyclical k must satisfy k_H ≥ k_M ≥ k_L ≥ 0, got {ks}")

    def band(r_ret: float, r_gen: float, g: float = g2, dr: float = 0.0) -> tuple[float, float, float]:
        out = []
        for x, k in zip(TIERS, ks):
            ev = ev_at(inp[f"ebitda_{x}"], inp[f"retail_{x}"], r_ret + dr, r_gen + dr, g)
            out.append((ev + closure) / sh - k * excess_ps)
        return tuple(out)

    L, M, H = band(inp["r_retail"], inp["r_gen"])
    A, B = (L + M) / 2, (M + H) / 2
    errors += ladder("L<M<H", L, M, H)

    # ①b check: k_H must cover the M/H top discount on the pre-k anchors.
    pre_m = (ev_at(inp["ebitda_m"], inp["retail_m"], inp["r_retail"], inp["r_gen"]) + closure) / sh
    pre_h = (ev_at(inp["ebitda_h"], inp["retail_h"], inp["r_retail"], inp["r_gen"]) + closure) / sh
    k_top = 1 - pre_m / pre_h
    if inp["k_h"] + 0.005 < k_top:
        errors.append(f"k_h {inp['k_h']} below ①b top discount {k_top:.3f}")

    # 2c flat-multiple ladder on the M generation multiple.
    pe_flat = perpetual_pe(g2, roic_m, inp["r_gen"])
    flat = [((sum(legs(inp[f"ebitda_{x}"], inp[f"retail_{x}"])[:2]) * pe_flat) + closure) / sh for x in TIERS]
    errors += ladder("flat-multiple L<M<H", *flat)

    # V_opt (A13): basket-1 annuities of the PPA premia over the forward world.
    r1 = inp["r_contract"]
    cp_full = inp["cp_accretion"] * inp["cp_fcfbg_base"] * (1 - t)
    term = int(inp["cp_term"])
    ramp = list(CP_RAMP) + [1.0] * (term + 1 - len(CP_RAMP))
    # ramp[i] is year NUM_YEAR + i; flows start at t_opt.  Annuity valued at
    # t_opt − 1 on basket 1, then discounted (t_opt − NUM_YEAR) years at the
    # base basket r (r_gen for the anchors; the tested r inside ③).
    t_opt = int(inp["t_opt"])
    lag = t_opt - NUM_YEAR
    if any(ramp[i] for i in range(lag)):
        errors.append("CP ramp has flows before t_opt")
    meta_full = cp_full / inp["cp_mw"] * inp["meta_mw"] - inp["meta_2027_ebitda"] * (1 - t)

    def opt_pv(r_back: float) -> tuple[float, float]:
        back = (1 + r_back) ** lag
        cp = sum(cp_full * ramp[i] / (1 + r1) ** (i - lag + 1) for i in range(lag, len(ramp))) / back
        meta = sum(meta_full / (1 + r1) ** k for k in range(1, 1 + int(inp["meta_term"]))) / back
        return cp, meta

    cp_pv, meta_pv = opt_pv(inp["r_gen"])
    v_opt = (cp_pv + meta_pv) / sh

    # ③ with step 1c.  ① model side: base M EV + V_opt (p = 1) over the M EBITDA.
    # ② band side: band EV less the increments' value net of what was still owed.
    owed = inp["cog_cash"] + inp["cog_debt"] - inp["cog_tax_npv"] + inp["cog_shares"] * inp["band_floor_close"]
    if abs(inp["ebitda_m"] - inp["incr_2027_ebitda"] - 7400) > 1e-6:
        errors.append("ebitda_m must be the 2027 target low end 7,400 + incr_2027_ebitda (A5 / A6)")

    def x_model(r_gen: float) -> float:
        return (ev_at(inp["ebitda_m"], inp["retail_m"], inp["r_retail"], r_gen) + sum(opt_pv(r_gen))) / inp["ebitda_m"]

    def incr_net(r_gen: float) -> float:
        gross = inp["incr_2027_ebitda"] * (1 - t) * perpetual_pe(g2, roic_m, r_gen)
        return (gross - owed) / (1 + r_gen) ** inp["band_t"]

    def floor_1c(r_gen: float) -> float:
        return (inp["fwd_band_min"] * inp["band_ebitda"] - incr_net(r_gen)) / inp["band_ebitda"]

    ladder_rows = [(b, x_model(basket_r(b)), floor_1c(basket_r(b))) for b in LADDER]
    x_m = (ev_at(inp["ebitda_m"], inp["retail_m"], inp["r_retail"], inp["r_gen"])) / inp["ebitda_m"]
    x_m_init = ev_at(inp["ebitda_m"], inp["retail_m"], inp["r_retail"], inp["r_gen_init"]) / inp["ebitda_m"]
    out_of_band = x_model(inp["r_gen"]) < floor_1c(inp["r_gen"])
    # The basket ladder decides r_gen: the first basket back in band is where ③
    # stops; only if none is (the user-landed state, A12) may r_gen sit at 篮 4.
    first_in = next((b for b, x, f in ladder_rows if x >= f), None)
    if first_in is not None and baskets.get("r_gen") != first_in:
        errors.append(f"step 1c: 篮 {first_in} is back in band, r_gen must be 篮 {first_in}")
    if first_in is None and baskets.get("r_gen") != LADDER[-1]:
        errors.append(f"③ still out of band at 篮 {LADDER[-1]}: r_gen must be 篮 {LADDER[-1]} (user-landed, A12)")

    # 表2′: band-edge r on the generation leg (retail stays at its basket),
    # solving the same step-1c equality.
    lo, hi = 0.03, inp["r_gen_init"]
    for _ in range(80):
        mid = (lo + hi) / 2
        if x_model(mid) > floor_1c(mid):
            lo = mid
        else:
            hi = mid
    r_edge = (lo + hi) / 2
    edge = band(inp["r_retail"], r_edge)
    init = band(inp["r_retail"], inp["r_gen_init"])

    ps = (inp["p_l"], inp["p_m"], inp["p_h"])
    plus_v = [x + p * v_opt for x, p in zip((L, M, H), ps)]

    # Candidate band (A14): GS FY2028 EBITDA in H′ only, discounted one year.
    ev28 = ev_at(inp["ebitda_2028_gs"], inp["retail_h"], inp["r_retail"], inp["r_gen"])
    h_prime = (ev28 + closure) / sh / (1 + inp["r_disc"]) - ks[2] * excess_ps
    cand = (L, M, h_prime)
    errors += ladder("candidate L′<M′<H′", *cand)

    # Point reading of L (comparison only): 2025 world recovers to M over 2 years.
    f_ret_l, f_gen_l, _ = legs(inp["ebitda_l"], inp["retail_l"])
    g1 = (f_gen_m / f_gen_l) ** 0.5 - 1
    pe_pt = recovery_two_stage_pe(g1, 2, g2, roic_m, inp["r_gen"])
    roic_l = legs(inp["ebitda_l"], inp["retail_l"])[2]
    l_point = (f_ret_l * perpetual_pe(g2, roic_l, inp["r_retail"]) + f_gen_l * pe_pt + closure) / sh - ks[0] * excess_ps

    print(f"VST.US {FORMULA_ID}")
    print(f"  shares {sh:.1f}M  closure {closure:,.0f}M  excess retention/share {excess_ps:.2f}  k {ks}")
    for x in TIERS:
        f_r, f_g, roic = legs(inp[f"ebitda_{x}"], inp[f"retail_{x}"])
        print(f"  {x.upper()}: retail FCF {f_r:,.0f} × {perpetual_pe(g2, roic, inp['r_retail']):.2f}"
              f"  gen FCF {f_g:,.0f} × {perpetual_pe(g2, roic, inp['r_gen']):.2f}  ROIC {roic:.1%}")
    print(f"  L/M/H {L:.2f} / {M:.2f} / {H:.2f}   A {A:.2f}  B {B:.2f}")
    print(f"  L/M {L / M:.3f}  H/M {H / M:.3f}  (H−L)/2M {(H - L) / 2 / M:.3f}  V_opt/M {v_opt / M:.3f}")
    print(f"  flat-multiple {flat[0]:.2f} / {flat[1]:.2f} / {flat[2]:.2f}")
    print(f"  ③ base alone: M EV/EBITDA {x_m:.2f}× (basket-6 {x_m_init:.2f}×) vs raw floor {inp['fwd_band_min']:.2f}×")
    print(f"  ③ step 1c (① base + V_opt p=1 vs ② floor less increments net of consideration owed {owed:,.0f}):")
    for b, x, f in ladder_rows:
        print(f"    篮 {b} r={basket_r(b):g}: {x:.2f}× vs {f:.2f}× → " + ("入带" if x >= f else "出带"))
    print("    → " + ("出带（用户拍板照用，A12）" if out_of_band else "入带"))
    print(f"  初分篮 13% band {init[0]:.2f} / {init[1]:.2f} / {init[2]:.2f}")
    print(f"  band-edge r_gen {r_edge:.2%} (step 1c) → {edge[0]:.2f} / {edge[1]:.2f} / {edge[2]:.2f}")
    print(f"  V_opt {v_opt:.2f} (CP {cp_pv / sh:.2f} + Meta {meta_pv / sh:.2f}); +V {plus_v[0]:.2f} / {plus_v[1]:.2f} / {plus_v[2]:.2f}")
    print(f"  candidate H′ {h_prime:.2f}   L point {l_point:.2f} (g1 {g1:.1%})")
    for d in (-0.01, 0.01):
        s = band(inp["r_retail"], inp["r_gen"], g2 + d)
        print(f"  g2 {g2 + d:.0%}: {s[0]:.2f} / {s[1]:.2f} / {s[2]:.2f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    for rx, vals, name in ((STATED_CAND, cand, "candidate"), (STATED_EDGE, edge, "band-edge"),
                           (STATED_INIT, init, "初分篮对照带")):
        m = rx.search(md)
        if not m:
            errors.append(f"{name} band not stated")
        elif any(abs(float(a) - b) > TOL for a, b in zip(m.groups(), vals)):
            errors.append(f"{name} stated {m.groups()} ≠ computed {tuple(round(v, 2) for v in vals)}")
    m = STATED_EDGE_R.search(md)
    if not m or abs(float(m.group(1)) / 100 - r_edge) > 5e-5:
        errors.append(f"band-edge r stated {m.group(1) if m else None}% ≠ computed {r_edge:.2%}")
    for rx, vals, name in ((STATED_1C_X, [x for _, x, _ in ladder_rows], "step 1c model multiples"),
                           (STATED_1C_FLOOR, [f for _, _, f in ladder_rows], "step 1c band floors")):
        m = rx.search(md)
        if not m or any(abs(float(a) - b) > 0.01 for a, b in zip(m.groups(), vals)):
            errors.append(f"{name} stated {m.groups() if m else None} ≠ computed {[round(v, 2) for v in vals]}")
    m = STATED_V_OPT.search(md)
    if not m or abs(float(m.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt stated {m.group(1) if m else None} ≠ computed {v_opt:.2f}")
    m = STATED_P.search(md)
    if not m or tuple(float(v) for v in m.groups()) != ps:
        errors.append("p_L/p_M/p_H stated ≠ Inputs")

    rf = rf_block("USD", {"r_retail": inp["r_retail"], "r_gen": inp["r_gen"]},
                  lambda dr: band(inp["r_retail"], inp["r_gen"], g2, dr))
    if abs(band(inp["r_retail"], inp["r_gen"], g2, 0.0)[1] - M) > 1e-9:
        errors.append("rf block dr=0 does not reproduce M")
    if not errors:
        write_rf_readings("VST.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
