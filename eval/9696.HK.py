#!/usr/bin/env python3
"""9696.HK (Tianqi Lithium H) valuation eval.

frameworks/9696.HK.md is the source of truth.
formula_id: tianqi_li2co3_twoleg_volplan_pe10_v2_gordon_v3

Multiples: Gordon at the leg's basket r (whole company = 篮 6 周期商品, both
legs are a lithium-price function; valuation-rules「§r 篮子」) with ONE flat
g2 = the commodity-leg tier default (lithium: inflation + long-run real price
drift ≤ −3%/yr → 0, never negative), tier ROE = EPS_HKD / BPS,
PE_x = perpetual_pe(g2, ROE_x, r).  At g2 = 0 all three tiers sit at 1/r.
The axis 永续 g2 row (6%, cap-truncated) is referenced verbatim (`axis_g2_li`)
and not adopted.

L tier (valuation-rules「谷底档」): the axis L world (Li2CO3 103k = 2028
bottom between BMI 113k and Goldman 85k, above the p90 cost curve) is a regime, not the company's realised
trough (FY2024 −85.57 亿 HKD, lithium 6–8 万).  `recovery_two_stage_pe` on the
measured path (FY2025 5.06 亿 → 2026H1 × 2, n = 1) is printed as a coordinate
only.  The PB floor is disclosure only (峰形区地板条款): L is the scenario
value, never max(scenario, floor).  The ticker's own 5-year TTM PE band is only
a guardrail.

V_opt: the SQM stake as k=1 × the realised 2026H1 investment income, run
through the framework's own (1-t)(1-NCI) bridge (A2e-7c).  v3 (2026-10-19):
the H1 unit is an H-world reading and the H world passes by like the base H —
one H year, then the M-world SQM income (ratio from SQM's own lithium segment,
three published periods, sqm_elasticity) at the M-tier multiple.

Operating value and excess cash (valuation-rules「经营价值与超额现金」, A11):
no excess-cash line (net debt).  Time alignment: the 2027 run-rate numerator is
worth its value at t_n = 2027-01-01; discounted τ = `n_disc` = 0.5 y at the
basket r to the 2026-06-30 book date, plus the window distributable profit
(2026H2 unbooked consensus parent NI, SQM income stripped as in the numerator,
× (1 − b), b = g2/ROE) discounted τ/2.  H tier passes by (lithium axis H =
「2026 平台延续到 2027」read as a pass-through, 2026-10-16): the H world holds
for one year, then the M world —
H_op = [E_H × payout(g2, ROE_H) + M_op × (1 + g2)] / (1 + r).

The framework carries no current price (AGENTS.md「现价 — 禁写契约」): this
script neither reads a price nor derives or checks a zone -- the daily digest
derives the zone from live quotes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_LI2CO3, check_li2co3_mount  # noqa: E402
from lib.gordon import check_g_cap, check_r, implied_g, payout, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402

# rf_report / bands_io import through the `eval.lib` package, so the repo root
# must be importable too; appended so `lib.*` above still resolves first.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "9696.HK.md"
FORMULA_ID = "tianqi_li2co3_twoleg_volplan_pe10_v2_gordon_v3"
MIN_R_MINUS_G = 0.02
# A9: the company's own realised trough→recovery path (Longbridge annual parent NI, HKD:
# FY2024 −85.57 亿 loss trough; FY2025 5.06 亿 → 2026H1 42.42 亿 CNY × 2 × fx ≈ 95.0 亿 HKD).
RECOVERY_MEASURED = {"FY2025→2026H1×2": (5.06, 42.42 * 2 * 1.119522, 1)}
TOL = 0.05
YI = 1e8
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"

REQUIRED = [
    "shares", "bps",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_conc", "realization_chem",
    "cost_conc", "cost_chem",
    "vol_conc_plan", "vol_chem_plan",
    "r_disc", "n_disc",
    "conv_ratio", "fx_hkd_per_cny", "tax_rate", "nci_share",
    "sqm_inv_income_h1", "eps26e_cny", "np_h1",
    "r_perp", "axis_g2_li", "g2",
    "pe_own_min", "pe_own_max",
    "pb_floor",
    *(f"sqm_{f}_{k}" for k in ("1q25", "fy25", "1h26")
      for f in ("li_rev", "li_vol", "li_gp_share", "gp")),
    "sqm_pretax_1h26",
]

_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%", re.MULTILINE)


def axis_g2(path: Path) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    li = inp[f"li2co3_{tag}"]
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    gp = disc * (
        inp["vol_conc_plan"] * (li * inp["realization_conc"] - inp["cost_conc"])
        + inp["vol_chem_plan"] * (li * inp["realization_chem"] - inp["cost_chem"])
    )
    parent = gp * inp["conv_ratio"]
    eps_hkd = parent / inp["shares"] * inp["fx_hkd_per_cny"]
    return {"gp": gp, "parent": parent, "eps_hkd": eps_hkd}


def window_profit(inp: dict[str, float], r: float, roe: float) -> float:
    """A11: window distributable profit per share (HKD) at the book date.  2026H2 unbooked
    consensus parent NI (FY2026E × shares − H1 booked), with the SQM investment income stripped
    at the H1 run-rate through the A8 bridge (same basis as the numerator), × (1 − b),
    b = g2 / ROE (0 at g2 = 0), discounted τ/2 at the basket r."""
    rem = (inp["eps26e_cny"] * inp["shares"] / YI - inp["np_h1"]
           - inp["sqm_inv_income_h1"] * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"]))
    b = max(inp["g2"], 0.0) / roe
    return rem * YI / inp["shares"] * inp["fx_hkd_per_cny"] * (1.0 - b) / (1.0 + r) ** (inp["n_disc"] / 2)


SQM_PERIODS = ("1q25", "fy25", "1h26")


def sqm_elasticity(inp: dict[str, float]) -> dict:
    """A7 (2026-10-19): SQM lithium-segment profit vs realised price, from SQM's own releases.
    Per period: realised price P = segment revenue ÷ LCE volume, segment gross profit per tonne =
    (segment share of consolidated GP × consolidated GP) ÷ volume.  gp/t = s × P − c: s < 1 carries
    the price-linked CORFO lease, c the per-tonne cash cost.  M-world price = 1H26 realised ×
    li2co3_m / li2co3_h (the same axis mapping the Tianqi legs use: the H1 regime is the H rung);
    the profit drop vol_1H26 × s × ΔP is taken off 1H26 pre-tax profit at an unchanged tax rate,
    so ratio = SQM net profit (M world) ÷ 1H26."""
    pts = {}
    for k in SQM_PERIODS:
        v = inp[f"sqm_li_vol_{k}"]
        pts[k] = (inp[f"sqm_li_rev_{k}"] / v, inp[f"sqm_li_gp_share_{k}"] * inp[f"sqm_gp_{k}"] / v)
    xs = [p for p, _ in pts.values()]
    ys = [g for _, g in pts.values()]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    s_ols = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    (p0, g0), (p1, g1) = pts["fy25"], pts["1h26"]
    s_2p = (g1 - g0) / (p1 - p0)
    p_h = pts["1h26"][0]
    p_m = p_h * inp["li2co3_m"] / inp["li2co3_h"]
    vol = inp["sqm_li_vol_1h26"]
    pretax = inp["sqm_pretax_1h26"]
    d_ols, d_2p = vol * s_ols * (p_h - p_m), vol * s_2p * (p_h - p_m)
    return {"points": pts, "slope_ols": s_ols, "cost_ols": s_ols * mx - my, "slope_2p": s_2p,
            "cost_2p": s_2p * p0 - g0, "p_h": p_h, "p_m": p_m, "dgp_ols": d_ols,
            "ratio_ols": 1.0 - d_ols / pretax, "ratio_2p": 1.0 - d_2p / pretax}


def anchors(S: dict[str, dict[str, float]], inp: dict[str, float], r: float) -> dict[str, float]:
    """Operating value per tier + window profit; H passes by (one H year, then the M world)."""
    g2 = inp["g2"]
    op = {t: S[t]["eps_hkd"] * S[t]["pe"] for t in ("l", "m", "h")}
    h_op = (S["h"]["eps_hkd"] * payout(g2, S["h"]["roe"]) + op["m"] * (1.0 + g2)) / (1.0 + r)
    win = {t: window_profit(inp, r, S[t]["roe"]) for t in ("l", "m", "h")}
    return {"l": op["l"] + win["l"], "m": op["m"] + win["m"], "h": h_op + win["h"],
            "op_l": op["l"], "op_m": op["m"], "op_h_persist": op["h"], "op_h": h_op,
            "win": win["m"]}


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors: list[str] = check_missing(inp, REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    r = inp["r_perp"]
    baskets = parse_baskets(md)
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    # valuation-rules「§r 篮子」: r is the basket's value, the framework names the basket;
    # the multiple is generated per tier from one flat g2 (commodity tier default) and the
    # tier ROE; the axis row is referenced verbatim.
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    # A10: the ramp-year discount is the operating leg's basket r, not a separate dial.
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} != r_perp={r} (A10: ramp discount = basket r)")
    errors += check_g_cap(inp["g2"], r, "g2")
    errors += check_g_cap(inp["axis_g2_li"], r, "axis_g2_li")
    if r - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {r - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    want = axis_g2(AXIS_LI2CO3)
    if abs(inp["axis_g2_li"] - want) > 1e-9:
        errors.append(f"axis_g2_li={inp['axis_g2_li']} vs _AXIS.lithium-carbonate 永续 g2 {want}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    def priced(inp_: dict[str, float], r_: float) -> dict[str, dict[str, float]]:
        S_ = {t: scenario(inp_, t) for t in ("l", "m", "h")}
        for t in S_:
            S_[t]["roe"] = S_[t]["eps_hkd"] / inp_["bps"]
            S_[t]["pe"] = perpetual_pe(inp_["g2"], S_[t]["roe"], r_)
        return S_

    S = priced(inp, r)
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): a tier outside the own band is BLOCKED, never fixed by twisting g or r.
    for tag, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(f"guardrail: PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g")
    # 峰形区地板条款 (A10): the PB floor is disclosed, never max()-ed into L.
    floor = inp["pb_floor"] * inp["bps"]
    AN = anchors(S, inp, r)
    L, M, H = AN["l"], AN["m"], AN["h"]
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    flat = (S["l"]["eps_hkd"] * pe_m, S["m"]["eps_hkd"] * pe_m, S["h"]["eps_hkd"] * pe_m)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")

    # V_opt (A2e-7c, A7): unit = k=1 × realised H1 investment income annualised, through the
    # same (1-t)(1-NCI) bridge A8 uses to strip it out of parent_ops.  The H1 unit was earned
    # in the H world (2026 platform); the H world passes by (2026-10-19, same as the base H):
    # one H year, then the M world for ever —
    #   V_opt = [E_H + V_M × (1 + g2)] / (1 + r),  V_M = ratio_M × E_H × PE_M,
    # ratio_M = SQM pre-tax profit in the M world ÷ 1H26 actual, from SQM's own lithium
    # segment calibrated over three published periods (sqm_elasticity).
    e_h = (2.0 * inp["sqm_inv_income_h1"] * YI * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])
           / inp["shares"] * inp["fx_hkd_per_cny"])
    cal = sqm_elasticity(inp)
    ratio_m = cal["ratio_ols"]
    v_opt_persist = e_h * pe_m
    v_m_sqm = ratio_m * e_h * pe_m

    def v_opt_pass(ratio: float) -> float:
        return (e_h + ratio * e_h * pe_m * (1.0 + inp["g2"])) / (1.0 + r)

    v_opt = v_opt_pass(ratio_m)
    tianqi_mh = S["m"]["parent"] / S["h"]["parent"]

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    pm = re.search(r"p_L/p_M/p_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*", out_sec)
    if pm is None:
        errors.append("p_L/p_M/p_H line not found in Outputs")
        p_tiers = (0.0, 0.0, 0.0)
    else:
        p_tiers = tuple(float(pm.group(i)) for i in (1, 2, 3))
    corrected = (L + p_tiers[0] * v_opt, M + p_tiers[1] * v_opt, H + p_tiers[2] * v_opt)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    for label, want_v, rx in (
        ("floor", floor, r"`floor` = [^*\n]*\*\*([0-9.]+)\*\*"),
        ("V_opt", v_opt, r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*"),
        ("A′", (corrected[0] + corrected[1]) / 2, r"A′ = \*\*([0-9.]+)\*\*"),
        ("B′", (corrected[1] + corrected[2]) / 2, r"B′ = \*\*([0-9.]+)\*\*"),
    ):
        s = first_float(rx, out_sec)
        if s is None or abs(s - want_v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {want_v:.4f}")
    # Table 3 rows: | L | 23.30 | 0 | 0 | **23.30** |
    for tag, want_v in zip(("L", "M", "H"), corrected):
        m3 = re.search(rf"^\| {tag} \| [0-9.]+ \| [^|]+\| [0-9.]+ \| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - want_v) > TOL:
            errors.append(f"table3 {tag}: stated {m3.group(1) if m3 else None} vs recomputed {want_v:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print(f"baskets={baskets} r_perp={r:g} r_disc={inp['r_disc']:g} g2={inp['g2']:g} (commodity tier default; axis 永续 g2 {inp['axis_g2_li']:g} referenced, not adopted — A4)")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
    )
    print(
        f"{'档':<3}{'毛利亿':>8}{'归母亿':>8}{'EPS_HKD':>10}{'ROE':>8}{'PE':>7}{'锚点':>8}"
    )
    for t in ("l", "m", "h"):
        s = S[t]
        print(
            f"{t.upper():<3}{s['gp']/YI:8.1f}{s['parent']/YI:8.1f}"
            f"{s['eps_hkd']:10.3f}{s['roe']:8.1%}{s['pe']:7.2f}{s['eps_hkd']*s['pe']:8.2f}"
        )
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × BPS; disclosure only, not max()-ed; L is the scenario value)  "
          f"disc={(1+inp['r_disc'])**(-inp['n_disc']):.4f} (time alignment tau {inp['n_disc']:g} y, A11)")
    print(f"window profit (A11) +{AN['win']:.3f} HKD/股 (2026H2 consensus {inp['eps26e_cny']:g} × shares − H1 {inp['np_h1']:g}亿 − SQM; "
          f"/1.13^{inp['n_disc'] / 2:g})")
    print(f"H 路过 (A11): persistent H op {AN['op_h_persist']:.2f} -> (E_H × payout + M op {AN['op_m']:.2f}) / (1+r) = {AN['op_h']:.2f}; "
          f"+ window -> H {H:.2f} (persistent reading {AN['op_h_persist'] + AN['win']:.2f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}x (A2e-2c, operating value, no window / pass-by): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    eps3 = (S["l"]["eps_hkd"], S["m"]["eps_hkd"], S["h"]["eps_hkd"])
    blended = tuple(v / e for v, e in zip((L, M, H), eps3))
    for line in tier_report((L, M, H), blended, eps3):
        print(line)
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} "
        f"numerator L/M={S['l']['eps_hkd']/S['m']['eps_hkd']:.2f} H/M={S['h']['eps_hkd']/S['m']['eps_hkd']:.2f} "
        f"| blended multiple (anchor / EPS) {blended[0]:.2f}/{blended[1]:.2f}/{blended[2]:.2f} — H's numerator lasts one year"
    )
    print(
        f"gordon: roe={S['l']['roe']:.3f}/{S['m']['roe']:.3f}/{S['h']['roe']:.3f} (ROE−r {S['l']['roe']-r:+.3f}/{S['m']['roe']-r:+.3f}/{S['h']['roe']-r:+.3f}) "
        f"-> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} inside own band [{inp['pe_own_min']}, {inp['pe_own_max']}]"
    )
    for dg in (-0.01, 0.01):
        inp_g = {**inp, "g2": inp["g2"] + dg}
        an_g = anchors(priced(inp_g, r), inp_g, r)
        print(f"  g2 {dg:+.0%} -> {an_g['l']:.2f}/{an_g['m']:.2f}/{an_g['h']:.2f}")
    g_lo, ok_lo = implied_g(inp["pe_own_min"], S["m"]["roe"], r)
    g_hi, ok_hi = implied_g(inp["pe_own_max"], S["m"]["roe"], r)
    print(f"guardrail band-edge g at ROE_M: {g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'}) / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'})")
    # A9 谷底档 coordinates: (i) measured trough→recovery CAGR on the L numerator; (ii) the
    # measured n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2"], S["m"]["roe"], r)
        g1_lm = (S["m"]["eps_hkd"] / S["l"]["eps_hkd"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2"], S["m"]["roe"], r)
        print(f"谷底档坐标（A9）{label} n={n}: (i) measured CAGR {g1_meas:.0%} -> {pe_i:.1f}x -> {S['l']['eps_hkd'] * pe_i:.1f} "
              f"(vs M {M:.2f}: {'overshoot' if S['l']['eps_hkd'] * pe_i > M else 'below M'}); "
              f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {S['l']['eps_hkd'] * pe_ii:.2f} (L/M {S['l']['eps_hkd'] * pe_ii / M:.3f}, collapsed)")
    print(f"谷底 x 1/r = {S['l']['eps_hkd'] / r:.2f}  (deep_discount pressure coordinate; = L at g2 0)")
    print("SQM lithium calibration (A7; US$k/t LCE, segment GP = share x consolidated GP): "
          + " | ".join(f"{k} P {p:.3f} gp/t {g:.3f}" for k, (p, g) in cal["points"].items()))
    print(f"  OLS gp/t = {cal['slope_ols']:.4f} x P - {cal['cost_ols']:.3f} (3 periods) | 2-point FY25/1H26: "
          f"{cal['slope_2p']:.4f} x P - {cal['cost_2p']:.3f}")
    print(f"  M world price = 1H26 {cal['p_h']:.3f} x {inp['li2co3_m']:g}/{inp['li2co3_h']:g} = {cal['p_m']:.3f}; "
          f"dGP {cal['dgp_ols']:.1f} $M on 1H26 pre-tax {inp['sqm_pretax_1h26']:g} -> SQM M/H ratio {ratio_m:.3f} "
          f"(2-point {cal['ratio_2p']:.3f}; transitional Tianqi own M/H {tianqi_mh:.3f})")
    print(f"V_opt={v_opt:.2f} = (E_H {e_h:.3f} + M-world SQM value {v_m_sqm:.2f}) / (1+r)  "
          f"[pass-by; persistent H reading {v_opt_persist:.2f}; 2-point {v_opt_pass(cal['ratio_2p']):.2f}; "
          f"Tianqi-ratio transitional {v_opt_pass(tianqi_mh):.2f}]  p={p_tiers}  "
          f"zone+V: L′={corrected[0]:.2f} M′={corrected[1]:.2f} H′={corrected[2]:.2f}  V_opt/M={v_opt/M:.1%}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): r_perp sets
    # the multiple and r_disc discounts the ramp year inside the base numerator,
    # so both move 1:1.  The Li2CO3 rungs, realization, cost, volumes and g2 stay
    # put.  Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        inp_ = {**inp, "r_disc": inp["r_disc"] + dr}
        an = anchors(priced(inp_, r + dr), inp_, r + dr)
        return an["l"], an["m"], an["h"]

    rf = rf_block(LISTING_CCY, {"r_perp": r, "r_disc": inp["r_disc"]}, band_rf)

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("9696.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
