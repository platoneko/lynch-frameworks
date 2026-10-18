#!/usr/bin/env python3
"""000792.SZ (Salt Lake) valuation eval.

frameworks/000792.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).
formula_id: saltlake_li_axis_kcl_ladder_pe_v2_gordon_v4

v4 H pass-by (2026-10-18, _AXIS.lithium-carbonate「H 档是路过」, framework correction, A12):
the lithium axis H rung (2026 platform carried into 2027) lasts one year, then the lithium leg
is back in the M world; the potash leg keeps its own H rung (its ladder is not the lithium axis).
H = [E_op,H × payout(g, RONIC_H) + E_op,mix × PE(g, RONIC_mix) × (1 + g)] / (1 + r) + cash +
window_H, where「mix」= lithium at the M rung, potash at the H rung (`passby_h`).  g = 0 makes
the potash leg's value identical to its persistent H value; only the lithium leg moves.  Every
L/M/H triple printed below (demoted-basket coordinate, g / r / numerator what-ifs) uses the same
pass-by H; the flat-multiple ladder stays on the persistent H as the A2e-2c diagnostic.

v4 time alignment (2026-10-16, valuation-rules「经营价值与超额现金」③, framework correction, A12):
the lithium leg's「2027 run-rate」value sits at t_n = 2027-01-01; the valuation date is the
2026-06-30 balance sheet, so `n_disc` is now τ = 0.5 (the old「one year until sales catch up
with nameplate」discount is replaced).  The not-yet-booked 2H26 consensus profit (FY26E EPS ×
shares − 1H26 parent − half a year of after-tax cash income), × (1 − b) with b = g2/RONIC = 0,
lithium leg's GP share only, discounted τ/2, is added per tier (`window_ps`).  Potash is a
current annualised half-year: τ 0.  Growth-period funding gap 0.  The step-1c project strip
keeps its 2026-10-04 one-year ramp δ (a band construction, not today's anchor).

v4 (2026-10-15, valuation-rules「经营价值与超额现金」, framework correction):
value per share = operating EPS × Gordon PE + excess cash per share (λ 1).
The extended net cash at 2026-06-30 (cash + trading FA + CDs / term deposits −
loans − leases − mining-right installment payables, no declared-unpaid
dividend) over an operating-cash anchor of 0 (post-restructuring cycle
FY2021–25 bottoms in net debt) is the excess cash; only the parent's share
counts, pro rata to equity (subsidiary cash split not disclosed), so the
minorities' share is taken out of the amount rather than through λ.  Every
tier's parent NP loses the after-tax income on that cash; the per-tier
operating return (E_op / (parent equity − C_ex)) replaces the book ROE.  g2 = 0
is kept (decided), so the multiple stays 1/r.  The same-earnings band points,
the step-1c project strip, the overturned basket-5 coordinate and the trough
coordinates are all re-read on the operating basis ((close − then C_ex per
share) ÷ (then EPS − then after-tax cash income per share)).

v3 (2026-10-04, valuation-rules「③ 出带处理流程」步 1c): the same-earnings band
floor is re-read on the base's basis.  The 2022-09→2023-10 band months priced the
4万吨 lithium-salt project (announced 2022-05-27, 公告 2022-038; not in their TTM
EPS) that today's nameplate numerator already holds, so the project's value on
this ticker's ruler -- M-tier lithium unit GP × conv_ratio, nameplate δ, 1/r,
discounted from the expected COD (2022 年报: 2024 年底) to the band point, net of
the announced capex -- comes off the band price before the band multiple is
taken.  At the initial basket 6 the adjusted floor sits under 1/r, so ③ never
fires: the 2026-09-20 demotion to basket 5 is overturned and printed only as the
「对照坐标（被推翻的降篮）」band.  On the v4 operating basis the raw floor is
already under 1/r; step 1c stays as the guardrail floor's construction.

Lithium volume is the commissioned nameplate (9.8 万吨/年) discounted one year
at the basket r, so the 2027-28 price deck of the shared axis meets a 2027
run-rate volume -- the same construction as 9696.HK.  Potash stays on the
annualised H1 volume without discounting (current capacity).

Multiples are Gordon-generated at the legs' basket r (both legs = 篮 6, the
initial basket; the 篮 5 demotion was overturned by step 1c, A10): RONIC per
tier = operating parent NP / operating equity, PE_x = perpetual_pe(g2, RONIC_x, r)
with ONE flat g2 = 0 (§13 commodity-leg tier default: lithium real price drift
≤ −3%/yr floored at 0, potash has no peer anchor), so every tier sits at 1/r.
The axis 永续 g2 row is referenced verbatim (`axis_g2_li`) and not adopted.

L tier (valuation-rules「谷底档」): the axis L world (Li2CO3 103k = 2028
surplus bottom between BMI 113k and Goldman 85k, above the p90 cost curve) is a regime, not the company's
realised trough (FY2024, lithium 6–8 万).  `recovery_two_stage_pe` on the
company's own measured operating path (FY2024 → FY2025, n = 1) is printed as a
coordinate and is not the anchor.  The PB floor is disclosure only (A4): L is
the scenario value, never max(scenario, floor).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import re  # noqa: E402

from lib.axes import AXIS_LI2CO3, check_li2co3_mount  # noqa: E402
from lib.gordon import (  # noqa: E402
    basket_r, check_branch, check_g_cap, check_r, payout, perpetual_pe, recovery_two_stage_pe, two_stage_pe,
)
from lib.tiers import report as tier_report  # noqa: E402
from lib.inputs import check_against_stated, parse_baskets, parse_inputs  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000792.SZ.md"
FORMULA_ID = "saltlake_li_axis_kcl_ladder_pe_v2_gordon_v4"
MIN_R_MINUS_G = 0.02
C_EX_TRIGGER = 0.15
# A9: the company's own realised trough→recovery path on the operating basis
# (亿; parent NI − own-year after-tax income on own-year parent-share C_ex:
# FY2024 46.63 − 3.53 = 43.10 → FY2025 84.76 − 3.71 = 81.05; A11).
RECOVERY_MEASURED = {"FY2024→FY2025": (43.10, 81.05, 1)}
# A10: the initial basket (current ruler) and the overturned 2026-09-20 demotion
# target, printed as the「对照坐标（被推翻的降篮）」band, never a zone.
INITIAL_BASKET = 6
DEMOTED_BASKET = 5
# Same-earnings band points (A10): (tag, raw PE field, close, years-to-COD or None,
# then C_ex per share, then after-tax cash income per share).  The LB weekly low
# is the guardrail floor; the next two are disclosed variants; the last is the
# band top (project already in its EPS, no strip).
BAND_POINTS = (
    ("LB 周点 2023-03-26", "pe_same_min", "band_lb_close", "band_lb_cod_yrs", "band_lb_cex", "band_lb_cinc"),
    ("事实口径 2023-10", "band_fact_pe", "band_fact_close", "band_fact_cod_yrs", "band_fact_cex", "band_fact_cinc"),
    ("剔 FY22 预告月 2023-09-24", "band_ex_pe", "band_ex_close", "band_ex_cod_yrs", "band_ex_cex", "band_ex_cinc"),
)
BAND_TOP = ("LB 周点 2026-05-03", "pe_same_max", "band_max_close", None, "band_max_cex", "band_max_cinc")
STATED_1C = re.compile(r"步 1c 同口径带下沿 \*\*([0-9.]+)×\*\*")
STATED_OP_RAW = re.compile(r"经营口径原始下沿 \*\*([0-9.]+)×\*\*")
STATED_OP_BAND = re.compile(r"经营口径同等盈利带 \*\*\[([0-9.]+), ([0-9.]+)\]\*\*")
STATED_DEMOTED = re.compile(r"对照坐标（被推翻的降篮）[^\n]*?→ ([0-9.]+) / ([0-9.]+) / ([0-9.]+)")
TOL = 0.05
YI = 1e8

# Formula「校验」regression guard: H1 sales volume, no discount, lithium at the
# axis H rung (= the H1 platform) and potash at the H1 ASP must reproduce
# 2 × H1 parent net profit (中报 归母 61.685 亿).
H1_PARENT_X2 = 61.685e8 * 2
GUARD_TOL = 0.01

REQUIRED = [
    "shares", "bps", "equity_nci",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_li", "vol_li_plan", "vol_li_h1", "cost_li",
    "r_disc", "n_disc",
    "kcl_price_l", "kcl_price_m", "kcl_price_h",
    "vol_k", "cost_k",
    "conv_ratio",
    "eps_fy26_cons", "parent_h1_26",
    "net_cash_ext_h1", "div_declared", "c_ex", "cash_yield", "tax_eff", "payout_op", "payout_paid",
    "r_perp", "axis_g2_li", "g2_li", "g2_k", "g2",
    "pe_same_min", "pe_same_max", "pe_own_min", "pe_own_max", "pb_floor",
    "proj_vol", "proj_capex", "shares_band",
    "band_lb_close", "band_lb_cod_yrs", "band_lb_cex", "band_lb_cinc",
    "band_fact_pe", "band_fact_close", "band_fact_cod_yrs", "band_fact_cex", "band_fact_cinc",
    "band_ex_pe", "band_ex_close", "band_ex_cod_yrs", "band_ex_cex", "band_ex_cinc",
    "band_max_close", "band_max_cex", "band_max_cinc",
    "eps_fy27_cons",
]

_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%", re.MULTILINE)


def axis_g2(path: Path) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def excess_cash(inp: dict[str, float]) -> tuple[float, float]:
    """(parent share, parent-share C_ex in 元): extended net cash − declared dividend − anchor 0."""
    equity = inp["bps"] * inp["shares"]
    share = equity / (equity + inp["equity_nci"])
    return share, (inp["net_cash_ext_h1"] - inp["div_declared"]) * share


def scenario(inp: dict[str, float], tag: str, c_inc: float, op_equity: float,
             r_disc: float | None = None, li_tag: str | None = None) -> dict[str, float]:
    """One tier; `li_tag` overrides the lithium rung only (the H pass-by's「mix」world)."""
    li = inp[f"li2co3_{li_tag or tag}"]
    kcl = inp[f"kcl_price_{tag}"]
    rd = inp["r_disc"] if r_disc is None else r_disc
    disc = (1.0 + rd) ** (-inp["n_disc"])
    gp_li = disc * inp["vol_li_plan"] * (li * inp["realization_li"] - inp["cost_li"])
    gp_k = inp["vol_k"] * (kcl - inp["cost_k"])
    gp = gp_li + gp_k
    parent = gp * inp["conv_ratio"]
    e_op = parent - c_inc  # A11: after-tax income on the excess cash comes off every tier
    return {
        "gp_li": gp_li,
        "gp_k": gp_k,
        "gp": gp,
        "parent": parent,
        "eps": parent / inp["shares"],
        "e_op": e_op,
        "eps_op": e_op / inp["shares"],
        "ronic": e_op / op_equity,
    }


def window_ps(inp: dict[str, float], s: dict[str, float], c_inc: float, r: float, g: float) -> float:
    """Window distributable profit per share for one tier (A12, valuation-rules「经营价值与超额现金」③).

    The lithium leg's Gordon value sits at t_n = 2027-01-01 (τ = `n_disc` years after the
    2026-06-30 balance sheet); the profit earned inside that window and not yet booked --
    FY2026E consensus parent profit − 1H26 actual − half a year of after-tax excess-cash
    income (numerator basis) -- × (1 − b), b = g / RONIC (0 for g ≤ 0), counts only for the
    lithium leg's share (M-tier-style GP weight at t_n; the potash leg runs from today and is
    not time-shifted, so adding its share would count it twice), discounted τ/2 at r.
    No window when τ = 0.
    """
    tau = inp["n_disc"]
    if tau <= 0:
        return 0.0
    prof = max(0.0, inp["eps_fy26_cons"] * inp["shares"] - inp["parent_h1_26"] - c_inc / 2.0)
    gp_li_tn = s["gp_li"] * (1.0 + r) ** tau  # lithium GP at t_n (undo the τ discount)
    w_li = gp_li_tn / (gp_li_tn + s["gp_k"])
    b = max(0.0, g / s["ronic"])
    return prof * w_li * (1.0 - b) / inp["shares"] / (1.0 + r) ** (tau / 2.0)


def value(inp: dict[str, float], s: dict[str, float], c_inc: float, cps: float, r: float, g: float,
          pe: float | None = None) -> float:
    """Per-share value today: operating EPS × PE + excess cash per share + window (A11 / A12)."""
    pe = perpetual_pe(g, s["ronic"], r) if pe is None else pe
    return s["eps_op"] * pe + cps + window_ps(inp, s, c_inc, r, g)


def passby_op(s_h: dict[str, float], s_mix: dict[str, float], r: float, g: float) -> float:
    """Operating value per share of the H tier with the lithium rung passing by (A12).

    One year of H-world operating earnings (× payout at g), then the「mix」world (lithium at
    the M rung, potash still at its H rung) valued one year on, all discounted one year at r.
    """
    after = s_mix["eps_op"] * perpetual_pe(g, s_mix["ronic"], r) * (1.0 + g)
    return (s_h["eps_op"] * payout(g, s_h["ronic"]) + after) / (1.0 + r)


def ladder(inp: dict[str, float], c_inc: float, cps: float, op_equity: float, r: float, g: float,
           r_disc: float | None = None) -> tuple[float, float, float]:
    """L / M / pass-by H (A12) for one (inputs, r, g) set; every printed triple goes through here."""
    s = {t: scenario(inp, t, c_inc, op_equity, r_disc=r_disc) for t in ("l", "m", "h")}
    mix = scenario(inp, "h", c_inc, op_equity, r_disc=r_disc, li_tag="m")
    h = passby_op(s["h"], mix, r, g) + cps + window_ps(inp, s["h"], c_inc, r, g)
    return value(inp, s["l"], c_inc, cps, r, g), value(inp, s["m"], c_inc, cps, r, g), h


def project_value(inp: dict[str, float], r: float, cod_yrs: float) -> float:
    """Step 1c: the 4万吨 project at a band point, on this ticker's ruler at basket r.

    M-tier lithium unit GP × conv_ratio, nameplate δ = (1+r)^-1 as in the base,
    capitalised at 1/r (g = 0) at the expected COD, discounted cod_yrs back to
    the band point; the announced capex, spread evenly to COD, comes off at its
    mid-point.
    """
    unit_np = (inp["li2co3_m"] * inp["realization_li"] - inp["cost_li"]) * inp["conv_ratio"]
    v_cod = inp["proj_vol"] * unit_np / r / (1.0 + r)
    return v_cod * (1.0 + r) ** -cod_yrs - inp["proj_capex"] * (1.0 + r) ** -(cod_yrs / 2.0)


def band_point_op(inp: dict[str, float], r: float, point: tuple) -> tuple[str, float, float, float]:
    """(tag, raw PE, operating PE, operating PE with the 4万吨 project stripped) at basket r.

    Operating PE = (close − then C_ex per share) ÷ (then EPS − then after-tax cash
    income per share); then EPS = close ÷ raw PE (the band's own earnings basis).
    """
    tag, pe_k, px_k, yrs_k, cex_k, cinc_k = point
    px, pe_raw = inp[px_k], inp[pe_k]
    e_op = px / pe_raw - inp[cinc_k]
    pe_op = (px - inp[cex_k]) / e_op
    v_ps = project_value(inp, r, inp[yrs_k]) / inp["shares_band"] if yrs_k else 0.0
    return tag, pe_raw, pe_op, (px - inp[cex_k] - v_ps) / e_op


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1
    baskets = parse_baskets(md)

    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    if not (inp["kcl_price_l"] < inp["kcl_price_m"] < inp["kcl_price_h"]):
        errors.append("kcl ladder violated")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    # Gordon inputs (valuation-rules「§r 篮子」): r is the named basket's value,
    # the ramp discount is the same basket r (A10), every g under g_cap(r), r − g
    # off the pole, the axis row referenced verbatim (not adopted, A3), no p_* field.
    r = inp["r_perp"]
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} != r_perp={r} (A10: nameplate ramp discount = basket r)")
    for k in ("axis_g2_li", "g2_li", "g2_k", "g2"):
        errors += check_g_cap(inp[k], r, k)
    if r - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {r - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    want = axis_g2(AXIS_LI2CO3)
    if abs(inp["axis_g2_li"] - want) > 1e-9:
        errors.append(f"axis_g2_li={inp['axis_g2_li']} vs _AXIS.lithium-carbonate 永续 g2 {want}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")

    # A11 excess cash: parent share of (extended net cash − declared dividend − anchor 0).
    equity = inp["bps"] * inp["shares"]
    share_p, c_ex = excess_cash(inp)
    if abs(c_ex - inp["c_ex"]) > 1e6:
        errors.append(f"c_ex {inp['c_ex']:.4e} != (net_cash_ext_h1 − div_declared) × parent share {c_ex:.4e}")
    if c_ex < C_EX_TRIGGER * equity:
        errors.append("c_ex below 15% of parent equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1.0 - inp["tax_eff"])
    cps = c_ex / inp["shares"]
    op_equity = equity - c_ex
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # Regression guard (Formula「校验」): the bridge must reproduce the half-year
    # it was calibrated on before it is trusted on the axis deck.
    gp_guard = (
        inp["vol_li_h1"] * (inp["li2co3_h"] * inp["realization_li"] - inp["cost_li"])
        + inp["vol_k"] * (inp["kcl_price_m"] - inp["cost_k"])
    )
    parent_guard = gp_guard * inp["conv_ratio"]
    if abs(parent_guard / H1_PARENT_X2 - 1.0) > GUARD_TOL:
        errors.append(
            f"regression guard: H1 vol × axis H × H1 ASP gives {parent_guard / YI:.2f}亿 "
            f"vs 2 × H1 parent {H1_PARENT_X2 / YI:.2f}亿"
        )

    S = {t: scenario(inp, t, c_inc, op_equity) for t in ("l", "m", "h")}

    # --- Gordon multiples ------------------------------------------------------
    # One flat g2 = lithium tier default × M-tier lithium GP weight + potash leg
    # × g2_k (both 0 under §13 commodity legs); g = 0 puts every tier at 1/r.
    w_li = S["m"]["gp_li"] / S["m"]["gp"]
    g2_blend = w_li * inp["g2_li"] + (1.0 - w_li) * inp["g2_k"]
    if abs(inp["g2"] - g2_blend) > 1e-4:
        errors.append(f"g2={inp['g2']} vs blended g2 {g2_blend:.5f}")
    for t in S:
        S[t]["pe"] = perpetual_pe(inp["g2"], S[t]["ronic"], r)
        S[t]["win"] = window_ps(inp, S[t], c_inc, r, inp["g2"])
        S[t]["px"] = S[t]["eps_op"] * S[t]["pe"] + cps + S[t]["win"]
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): operating PE_M against the operating same-earnings
    # band, floor = the LB low with the 4万吨 project stripped (step 1c).  Out of
    # band is the ③ out-of-band flow (A10), never fixed by twisting g or r.
    pts = [band_point_op(inp, r, p) for p in BAND_POINTS]
    top = band_point_op(inp, r, BAND_TOP)[2]
    floor_raw_op, floor_1c = pts[0][2], pts[0][3]
    if not (floor_1c <= pe_m <= top):
        errors.append(
            f"guardrail: PE_M={pe_m:.2f} outside operating same-earnings band [{floor_1c:.2f} (1c), {top:.2f}] "
            "— ③ 出带处理流程 (A10), do not twist g / r"
        )
    # The initial basket in band means ③ never fires, so the ruler MUST be the
    # initial basket (a demotion would count the project twice -- once in today's
    # nameplate, once through a lower r).
    r0 = basket_r(INITIAL_BASKET)
    s0 = scenario(inp, "m", c_inc, op_equity, r_disc=r0)
    pe_m0 = perpetual_pe(inp["g2"], s0["ronic"], r0)
    floor_1c0 = band_point_op(inp, r0, BAND_POINTS[0])[3]
    if floor_1c0 <= pe_m0 <= top and baskets.get("r_perp") != INITIAL_BASKET:
        errors.append(
            f"step 1c: initial 篮 {INITIAL_BASKET} PE_M {pe_m0:.2f} is inside [{floor_1c0:.2f}, {top:.2f}] "
            f"-> ③ not triggered, r_perp must stay 篮 {INITIAL_BASKET}"
        )
    for rx, want_v, label in ((STATED_1C, floor_1c, "step 1c floor"), (STATED_OP_RAW, floor_raw_op, "operating raw floor")):
        m = rx.search(md)
        if not m or abs(float(m.group(1)) - want_v) > 0.01:
            errors.append(f"{label} stated {m.group(1) if m else None} vs recomputed {want_v:.2f}")
    m = STATED_OP_BAND.search(md)
    if not m or abs(float(m.group(1)) - floor_1c) > 0.01 or abs(float(m.group(2)) - top) > 0.01:
        errors.append(f"operating band stated {m.groups() if m else None} vs [{floor_1c:.2f}, {top:.2f}]")

    # A4: the PB floor is disclosed, never max()-ed into L.
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["px"]
    L = scenario_L
    M = S["m"]["px"]
    # A12 H pass-by: lithium H rung one year, then the M rung; potash keeps its H rung.
    S_mix = scenario(inp, "h", c_inc, op_equity, li_tag="m")
    op_h = passby_op(S["h"], S_mix, r, inp["g2"])
    H_persist = S["h"]["px"]
    H = op_h + cps + S["h"]["win"]
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated ({L:.2f}/{M:.2f}/{H:.2f})", file=sys.stderr)
        return 1

    flat = [value(inp, S[t], c_inc, cps, r, inp["g2"], pe=pe_m) for t in ("l", "m", "h")]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    for label, want_v, rx in (
        ("floor", floor, r"`floor` = [^*\n]*\*\*([0-9.]+)\*\*"),
        ("scenario_L", scenario_L, r"`scenario_L` = \*\*([0-9.]+)\*\*"),
    ):
        m = re.search(rx, out_sec)
        got = float(m.group(1)) if m else None
        if got is None or abs(got - want_v) > TOL:
            errors.append(f"{label}: stated {got} vs recomputed {want_v:.4f}")
    rd = basket_r(DEMOTED_BASKET)
    band_d = ladder(inp, c_inc, cps, op_equity, rd, inp["g2"], r_disc=rd)
    if any(abs(a - b) > 1e-9 for a, b in zip(ladder(inp, c_inc, cps, op_equity, r, inp["g2"]), (L, M, H))):
        errors.append("ladder() does not reproduce the base L / M / pass-by H")
    m = STATED_DEMOTED.search(out_sec)
    if not m or any(abs(float(a) - b) > TOL for a, b in zip(m.groups(), band_d)):
        errors.append(f"对照坐标（被推翻的降篮） stated {m.groups() if m else None} vs {[round(b, 2) for b in band_d]}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK vs _AXIS.lithium-carbonate: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
    )
    print(
        f"kcl ladder: {inp['kcl_price_l']:g}/{inp['kcl_price_m']:g}/{inp['kcl_price_h']:g}"
    )
    print(f"L/M/H = {L:.2f}/{M:.2f}/{H:.2f}  A/B = {A:.2f}/{B:.2f}")
    print(
        f"超额现金: 扩展口径净现金 {inp['net_cash_ext_h1'] / YI:.2f}亿 − 已宣派未付股息 {inp['div_declared'] / YI:.2f}亿 − 锚 0 "
        f"→ × 归母份额 {share_p:.4f}（少数股东 {(1 - share_p) * (inp['net_cash_ext_h1'] - inp['div_declared']) / YI:.2f}亿 不计）"
        f"= C_ex {c_ex / YI:.2f}亿"
        f"（每股 {cps:.3f}，占归母权益 {c_ex / equity:.1%}，λ 1）"
    )
    print(
        f"现金税后收益 {c_ex / YI:.2f}亿 × {inp['cash_yield']:.4%} × (1 − {inp['tax_eff']:.4f}) = {c_inc / YI:.2f}亿/年 "
        f"（{c_inc / inp['shares']:.4f} 元/股，三档同扣）；经营股权 {op_equity / YI:.2f}亿"
    )
    for t in ("l", "m", "h"):
        print(
            f"  {t.upper()}: 归母 {S[t]['parent'] / YI:.2f}亿 → 经营 {S[t]['e_op'] / YI:.2f}亿 · 经营 EPS {S[t]['eps_op']:.4f} "
            f"· RONIC {S[t]['ronic']:.1%}（账面 ROE {S[t]['parent'] / equity:.1%}）· 经营价值 {S[t]['eps_op'] * S[t]['pe']:.2f} + 现金 {cps:.2f}"
            f" + 窗口 {S[t]['win']:.2f}"
        )
        w = S[t]["gp_li"] / S[t]["gp"]  # 表1: operating value split by GP weight
        k_v = S[t]["eps_op"] * (1 - w) * S[t]["pe"]
        li_v = (op_h if t == "h" else S[t]["eps_op"] * S[t]["pe"]) - k_v  # H: lithium leg = pass-by op − potash
        tot = H if t == "h" else S[t]["px"]
        print(f"     表1 {t.upper()}: 锂 {li_v:.2f} · 钾 {k_v:.2f} "
              f"· 现金 {cps:.2f} · 锂腿窗口 {S[t]['win']:.2f} · 合计 {tot:.2f}")
    w_h = S["h"]["gp_li"] / S["h"]["gp"]
    print(f"H 路过 (A12): persistent H {H_persist:.2f} (锂 {S['h']['eps_op'] * w_h * pe_h:.2f}) -> "
          f"(E_op,H {S['h']['eps_op']:.4f} × payout + mix E_op {S_mix['eps_op']:.4f} × PE) / (1+r) = 经营 {op_h:.2f} "
          f"+ 现金 {cps:.2f} + 窗口 {S['h']['win']:.2f} = H {H:.2f}（锂回 M 档、钾留 H 档）")
    prof_2h = inp["eps_fy26_cons"] * inp["shares"] - inp["parent_h1_26"] - c_inc / 2.0
    print(
        f"时点对齐（A12）: 锂腿 τ {inp['n_disc']:g} 年（2026-06-30 → t_n 2027-01-01，δ {(1 + r) ** -inp['n_disc']:.4f}）；"
        f"钾腿当期年化 τ 0；窗口可分配利润 = FY26E {inp['eps_fy26_cons']} × 股本 − 1H26 {inp['parent_h1_26'] / YI:.2f}亿 "
        f"− 半年现金收益 {c_inc / 2 / YI:.2f}亿 = {prof_2h / YI:.2f}亿 × 锂腿毛利占比 × (1 − b 0) ÷ 1.13^{inp['n_disc'] / 2:g} "
        f"→ 每股 {S['l']['win']:.3f}/{S['m']['win']:.3f}/{S['h']['win']:.3f}；增长期资金缺口 0"
    )
    print(
        f"floor={floor:.2f} (PB {inp['pb_floor']:g} × BPS; disclosure only, not max()-ed; "
        f"L is the scenario value {scenario_L:.2f}; floor/M = {floor / M:.3f})"
    )
    print(
        f"li vol={inp['vol_li_plan']:g} x disc={(1 + inp['r_disc']) ** (-inp['n_disc']):.4f} "
        f"(H1 sales x2 = {inp['vol_li_h1']:g}, not in formula)"
    )
    print(
        f"M parent={S['m']['parent']/YI:.2f}亿 "
        f"(li GP {S['m']['gp_li']/YI:.2f} + k GP {S['m']['gp_k']/YI:.2f})"
    )
    print(
        f"regression guard OK: H1 vol × axis H × H1 ASP = {parent_guard / YI:.2f}亿 "
        f"≈ 2 × H1 parent {H1_PARENT_X2 / YI:.2f}亿"
    )
    print(
        f"baskets={baskets} gordon: r={r:g} g2={inp['g2']:g} flat "
        f"(blend {g2_blend:.4f} = li {w_li:.3f}×{inp['g2_li']:g} [§13 tier default] + k {1 - w_li:.3f}×{inp['g2_k']:g} [无同业锚]; "
        f"axis row {inp['axis_g2_li']:g} referenced, not adopted) "
        f"ronic={S['l']['ronic']:.3f}/{S['m']['ronic']:.3f}/{S['h']['ronic']:.3f} -> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} "
        f"(g=0: every tier = 1/r); PE_M inside operating same-earnings band [{floor_1c:.2f} (step 1c; raw op {floor_raw_op:.2f}; "
        f"whole-equity {inp['pe_same_min']}), {top:.2f}]; own 5y TTM band [{inp['pe_own_min']}, {inp['pe_own_max']}] printed only"
    )
    # ⑤ / check_branch: g2 = 0 is the decided value; the operating payout is disclosed.
    br = check_branch(inp["g2"], S["m"]["ronic"], r, inp["payout_op"], "g2")
    print(
        f"经营口径派息率 {inp['payout_op']:.1%}（分红与注销式回购 + 现金积累，FY2021–25）；"
        f"check_branch(g2 0): {'通过' if not br else '提示 — ' + br[0]}（g2 = 0 已拍板，保留，只披露）"
    )
    keep = 1.0 - inp["g2"] / S["m"]["ronic"] - inp["payout_paid"]
    q = keep * S["m"]["eps_op"]
    print(
        f"多留部分: 比例 {keep:.1%}（1 − b {inp['g2'] / S['m']['ronic']:.1%} − 实付 {inp['payout_paid']:.1%}）· 每股 {q:.2f}/年 "
        f"· PV {q / (r - inp['g2']):.2f} · λ 1，PV 不进锚点"
    )
    # Band points: whole-equity vs operating vs operating with the project stripped.
    for tag, raw, op, adj in pts:
        print(f"band {tag}: 整股 PE {raw:.2f} -> 经营 {op:.2f} -> 步 1c {adj:.2f} (r={r:g})")
    print(f"band top {BAND_TOP[0]}: 整股 PE {inp['pe_same_max']} -> 经营 {top:.2f}")
    for b in (INITIAL_BASKET, DEMOTED_BASKET):
        rb = basket_r(b)
        _, _, op_b, fb = band_point_op(inp, rb, BAND_POINTS[0])
        print(f"  篮 {b} r={rb:g}: PE_M {1 / rb:.2f}x vs 1c floor {fb:.2f} (经营原始 {op_b:.2f}) -> "
              f"{'入带' if 1 / rb >= fb else '出带'}")
    print(f"  1c floor {floor_1c:.2f}x at g = 0 reads r {1 / floor_1c:.1%}")
    # A10: the overturned demotion's band, printed as a coordinate (never a zone).
    print(
        f"对照坐标（被推翻的降篮）篮 {DEMOTED_BASKET} r={rd:g}: "
        f"{band_d[0]:.2f}/{band_d[1]:.2f}/{band_d[2]:.2f} (not a zone)"
    )
    for dg in (-0.01, 0.01):
        alt = ladder(inp, c_inc, cps, op_equity, r, inp["g2"] + dg)
        pes = [perpetual_pe(inp["g2"] + dg, S[t]["ronic"], r) for t in ("l", "m", "h")]
        print(f"  g2 {dg:+.0%} -> pe {pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f} (H 路过)")
    for g_alt, why in ((0.0115, "锂同业反解 2.35% × 锂腿权重"), (0.0135, "钾腿借 2.6% 试算")):
        alt = ladder(inp, c_inc, cps, op_equity, r, g_alt)
        print(f"  g2 {g_alt:.2%} ({why}) -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}")
    # Numerator what-ifs (A5 / A2): each swaps one input, everything else as the base.
    for label, over in (("vol_li_h1 替代名牌（仍时点对齐）", {"vol_li_plan": inp["vol_li_h1"]}),
                        ("不做时点对齐（τ 0、无窗口）", {"n_disc": 0}),
                        ("钾三档全钉 L", {"kcl_price_m": inp["kcl_price_l"], "kcl_price_h": inp["kcl_price_l"]})):
        alt_inp = {**inp, **over}
        alt = ladder(alt_inp, c_inc, cps, op_equity, r, inp["g2"])
        print(f"  {label} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}")
    print(f"  H 世界长期化（锂 H 价按永续，2026-10-18 前的读法） -> H {H_persist:.2f}")
    pe_hw = two_stage_pe(0.17, 3, inp["g2"], S["m"]["ronic"], r)
    print(f"  H 窗口对照 g1 17% n 3 -> {pe_hw:.2f}x -> {S['m']['eps_op'] * pe_hw + cps + S['m']['win']:.2f} (H {H:.2f})")
    for rr in (r - 0.005, r + 0.005, 0.11, 0.15, 0.10):
        alt = ladder(inp, c_inc, cps, op_equity, rr, inp["g2"], r_disc=rr)
        print(f"  r {rr:.3f} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}")
    # A9 谷底档 coordinates: (i) measured trough→recovery CAGR on the L numerator; (ii) measured
    # n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2"], S["m"]["ronic"], r)
        g1_lm = (S["m"]["eps_op"] / S["l"]["eps_op"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2"], S["m"]["ronic"], r)
        v_i, v_ii = (S["l"]["eps_op"] * pe_i + cps + S["l"]["win"], S["l"]["eps_op"] * pe_ii + cps + S["l"]["win"])
        print(
            f"谷底档坐标（A9，经营口径）{label} n={n}: (i) measured CAGR {g1_meas:.1%} -> {pe_i:.2f}x -> {v_i:.2f} "
            f"(vs M {M:.2f}: {'overshoot' if v_i > M else 'below M'}); "
            f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {v_ii:.2f} (L/M {v_ii / M:.3f}, collapsed)"
        )
    print(f"谷底 x 1/r + 现金 = {S['l']['eps_op'] / r + cps + S['l']['win']:.2f}  (+ window; = L at g=0; deep_discount pressure coordinate)")
    print(f"FY27 共识 EPS {inp['eps_fy27_cons']} − 现金收益 → 经营 {inp['eps_fy27_cons'] - c_inc / inp['shares']:.3f} "
          f"× 1/r + 现金 = {(inp['eps_fy27_cons'] - c_inc / inp['shares']) / r + cps:.2f}")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}x (A2e-2c, with cash, persistent H): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print("operating part only (anchors − cash − window; H = pass-by, blended multiple = value / EPS):")
    ops = (S["l"]["eps_op"] * pe_l, S["m"]["eps_op"] * pe_m, op_h)
    eps3 = (S["l"]["eps_op"], S["m"]["eps_op"], S["h"]["eps_op"])
    blended = tuple(v / e for v, e in zip(ops, eps3))
    for line in tier_report(ops, blended, eps3):
        print("  " + line)
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/(2*M):.2%} V_opt/M=0 C_ex/M={cps / M:.1%} "
        f"operating numerator L/M={S['l']['eps_op']/S['m']['eps_op']:.2f} H/M={S['h']['eps_op']/S['m']['eps_op']:.2f} "
        f"| blended multiple ratio L/M={blended[0]/blended[1]:.2f} H/M={blended[2]/blended[1]:.2f} — H's lithium rung lasts one year"
    )
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
