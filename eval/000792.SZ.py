#!/usr/bin/env python3
"""000792.SZ (Salt Lake) valuation eval.

frameworks/000792.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).
formula_id: saltlake_li_axis_kcl_ladder_pe_v2_gordon_v3

v3 (2026-10-04, valuation-rules「③ 出带处理流程」步 1c): the same-earnings band
floor is re-read on the base's basis.  The 2022-09→2023-10 band months priced the
4万吨 lithium-salt project (announced 2022-05-27, 公告 2022-038; not in their TTM
EPS) that today's nameplate numerator already holds, so the project's value on
this ticker's ruler -- M-tier lithium unit GP × conv_ratio, nameplate δ, 1/r,
discounted from the expected COD (2022 年报: 2024 年底) to the band point, net of
the announced capex -- comes off the band price before the band multiple is
taken.  At the initial basket 6 the adjusted floor sits under 1/r, so ③ never
fires: the 2026-09-20 demotion to basket 5 is overturned and printed only as the
「对照坐标（被推翻的降篮）」band.

Lithium volume is the commissioned nameplate (9.8 万吨/年) discounted one year
at the basket r, so the 2027-28 price deck of the shared axis meets a 2027
run-rate volume -- the same construction as 9696.HK.  Potash stays on the
annualised H1 volume without discounting (current capacity).

Multiples are Gordon-generated at the legs' basket r (both legs = 篮 6, the
initial basket; the 篮 5 demotion was overturned by step 1c, A10): ROE per tier
from parent NP / equity (bps × shares), PE_x = perpetual_pe(g2, ROE_x, r) with
ONE flat g2 = 0 (§13 commodity-leg tier default: lithium real price drift
≤ −3%/yr floored at 0, potash has no peer anchor), so every tier sits at 1/r.
The axis 永续 g2 row is referenced verbatim (`axis_g2_li`) and not adopted.

Guardrail (③): PE_M against the same-earnings band [step-1c floor, pe_same_max]
(months whose lagged TTM parent NP sits within ±20% of the M numerator; the
floor point pe_same_min stripped of the 4万吨 project, see v3); the own 5-year
TTM PE band is on a different earnings basis and is only printed.

L tier (valuation-rules「谷底档」): the axis L world (Li2CO3 103k = BMI 2028
surplus bottom, above the p90 cost curve) is a regime, not the company's
realised trough (FY2024, lithium 6–8 万).  `recovery_two_stage_pe` on the
company's own measured path (FY2024 46.63 亿 → FY2025 84.76 亿, n = 1) is
printed as a coordinate — it overshoots M with the measured CAGR and collapses
into M with the model's L→M magnitude — and is not the anchor.  The PB floor
is disclosure only (A4): L is the scenario value, never max(scenario, floor).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import re  # noqa: E402

from lib.axes import AXIS_LI2CO3, check_li2co3_mount  # noqa: E402
from lib.gordon import basket_r, check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.inputs import check_against_stated, parse_baskets, parse_inputs  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000792.SZ.md"
FORMULA_ID = "saltlake_li_axis_kcl_ladder_pe_v2_gordon_v3"
MIN_R_MINUS_G = 0.02
# A9: the company's own realised trough→recovery path (Longbridge annual parent NI,
# FY2024 46.63 亿 — the 2024–25 lithium crash year — → FY2025 84.76 亿).
RECOVERY_MEASURED = {"FY2024→FY2025": (46.63, 84.76, 1)}
# A10: the initial basket (current ruler) and the overturned 2026-09-20 demotion
# target, printed as the「对照坐标（被推翻的降篮）」band, never a zone.
INITIAL_BASKET = 6
DEMOTED_BASKET = 5
# Step 1c floor points (A10): (tag, PE field, close field, years-to-COD field).
# The LB weekly point is the guardrail floor; the other two are disclosed variants.
BAND_POINTS = (
    ("LB 周点 2023-03-26", "pe_same_min", "band_lb_close", "band_lb_cod_yrs"),
    ("事实口径 2023-10", "band_fact_pe", "band_fact_close", "band_fact_cod_yrs"),
    ("剔 FY22 预告月 2023-09-24", "band_ex_pe", "band_ex_close", "band_ex_cod_yrs"),
)
STATED_1C = re.compile(r"步 1c 同口径带下沿 \*\*([0-9.]+)×\*\*")
STATED_DEMOTED = re.compile(r"对照坐标（被推翻的降篮）[^\n]*?→ ([0-9.]+) / ([0-9.]+) / ([0-9.]+)")
TOL = 0.05
YI = 1e8

# Formula「校验」regression guard: H1 sales volume, no discount, lithium at the
# axis H rung (= the H1 platform) and potash at the H1 ASP must reproduce
# 2 × H1 parent net profit (中报 归母 61.685 亿).
H1_PARENT_X2 = 61.685e8 * 2
GUARD_TOL = 0.01

REQUIRED = [
    "shares", "bps",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_li", "vol_li_plan", "vol_li_h1", "cost_li",
    "r_disc", "n_disc",
    "kcl_price_l", "kcl_price_m", "kcl_price_h",
    "vol_k", "cost_k",
    "conv_ratio",
    "r_perp", "axis_g2_li", "g2_li", "g2_k", "g2",
    "pe_same_min", "pe_same_max", "pe_own_min", "pe_own_max", "pb_floor",
    "proj_vol", "proj_capex", "shares_band",
    "band_lb_close", "band_lb_cod_yrs", "band_fact_pe", "band_fact_close", "band_fact_cod_yrs",
    "band_ex_pe", "band_ex_close", "band_ex_cod_yrs",
]

_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%", re.MULTILINE)


def axis_g2(path: Path) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def scenario(inp: dict[str, float], tag: str, r_disc: float | None = None) -> dict[str, float]:
    li = inp[f"li2co3_{tag}"]
    kcl = inp[f"kcl_price_{tag}"]
    rd = inp["r_disc"] if r_disc is None else r_disc
    disc = (1.0 + rd) ** (-inp["n_disc"])
    gp_li = disc * inp["vol_li_plan"] * (li * inp["realization_li"] - inp["cost_li"])
    gp_k = inp["vol_k"] * (kcl - inp["cost_k"])
    gp = gp_li + gp_k
    parent = gp * inp["conv_ratio"]
    eps = parent / inp["shares"]
    return {
        "gp_li": gp_li,
        "gp_k": gp_k,
        "gp": gp,
        "parent": parent,
        "eps": eps,
    }


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


def band_floors_1c(inp: dict[str, float], r: float) -> list[tuple[str, float, float]]:
    """[(tag, raw PE, PE with the project stripped from the band price)] at basket r."""
    out = []
    for tag, pe_k, px_k, yrs_k in BAND_POINTS:
        v_ps = project_value(inp, r, inp[yrs_k]) / inp["shares_band"]
        out.append((tag, inp[pe_k], inp[pe_k] * (1.0 - v_ps / inp[px_k])))
    return out


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

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}

    # --- Gordon multiples ------------------------------------------------------
    # One flat g2 = lithium tier default × M-tier lithium GP weight + potash leg
    # × g2_k (both 0 under §13 commodity legs); g = 0 puts every tier at 1/r.
    equity = inp["bps"] * inp["shares"]
    w_li = S["m"]["gp_li"] / S["m"]["gp"]
    g2_blend = w_li * inp["g2_li"] + (1.0 - w_li) * inp["g2_k"]
    if abs(inp["g2"] - g2_blend) > 1e-4:
        errors.append(f"g2={inp['g2']} vs blended g2 {g2_blend:.5f}")
    for t in S:
        S[t]["roe"] = S[t]["parent"] / equity
        S[t]["pe"] = perpetual_pe(inp["g2"], S[t]["roe"], r)
        S[t]["px"] = S[t]["eps"] * S[t]["pe"]
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): PE_M against the same-earnings band, floor on the
    # base's basis (step 1c).  Out of band is the ③ out-of-band flow (A10),
    # never fixed by twisting g or r.
    floors = band_floors_1c(inp, r)
    floor_1c = floors[0][2]
    if not (floor_1c <= pe_m <= inp["pe_same_max"]):
        errors.append(
            f"guardrail: PE_M={pe_m:.2f} outside same-earnings band [{floor_1c:.2f} (1c), {inp['pe_same_max']}] "
            "— ③ 出带处理流程 (A10), do not twist g / r"
        )
    # Step 1c decides the basket: the initial basket back in band means ③ never
    # fires, so the ruler MUST be the initial basket (a demotion would count the
    # project twice -- once in today's nameplate, once through a lower r).
    r0 = basket_r(INITIAL_BASKET)
    roe_m0 = scenario(inp, "m", r_disc=r0)["parent"] / (inp["bps"] * inp["shares"])
    pe_m0 = perpetual_pe(inp["g2"], roe_m0, r0)
    floor_1c0 = band_floors_1c(inp, r0)[0][2]
    if floor_1c0 <= pe_m0 <= inp["pe_same_max"] and baskets.get("r_perp") != INITIAL_BASKET:
        errors.append(
            f"step 1c: initial 篮 {INITIAL_BASKET} PE_M {pe_m0:.2f} is inside [{floor_1c0:.2f}, {inp['pe_same_max']}] "
            f"-> ③ not triggered, r_perp must stay 篮 {INITIAL_BASKET}"
        )
    m = STATED_1C.search(md)
    if not m or abs(float(m.group(1)) - floor_1c) > 0.01:
        errors.append(f"step 1c floor stated {m.group(1) if m else None} vs recomputed {floor_1c:.2f}")

    # A4: the PB floor is disclosed, never max()-ed into L.
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["px"]
    L = scenario_L
    M = S["m"]["px"]
    H = S["h"]["px"]
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated ({L:.2f}/{M:.2f}/{H:.2f})", file=sys.stderr)
        return 1

    flat = [S["l"]["eps"] * pe_m, S["m"]["eps"] * pe_m, S["h"]["eps"] * pe_m]
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
    Sd = {t: scenario(inp, t, r_disc=rd) for t in ("l", "m", "h")}
    band_d = [Sd[t]["eps"] * perpetual_pe(inp["g2"], Sd[t]["parent"] / equity, rd) for t in ("l", "m", "h")]
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
        f"roe={S['l']['roe']:.3f}/{S['m']['roe']:.3f}/{S['h']['roe']:.3f} -> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} "
        f"(g=0: every tier = 1/r); PE_M inside same-earnings band [{floor_1c:.2f} (step 1c; raw {inp['pe_same_min']}), {inp['pe_same_max']}]; "
        f"own 5y TTM band [{inp['pe_own_min']}, {inp['pe_own_max']}] printed only (different earnings basis)"
    )
    # Step 1c: raw vs base-basis floor points, and the basket ladder it settles.
    for tag, raw, adj in floors:
        print(f"step 1c {tag}: band PE {raw:.2f} -> {adj:.2f} with the 4万吨 project stripped (r={r:g})")
    for b in (INITIAL_BASKET, DEMOTED_BASKET):
        rb = basket_r(b)
        fb = band_floors_1c(inp, rb)[0][2]
        print(f"  篮 {b} r={rb:g}: PE_M {1 / rb:.2f}x vs 1c floor {fb:.2f} (raw {inp['pe_same_min']}) -> "
              f"{'入带' if 1 / rb >= fb else '出带'}")
    # A10: the overturned demotion's band, printed as a coordinate (never a zone).
    print(
        f"对照坐标（被推翻的降篮）篮 {DEMOTED_BASKET} r={rd:g}: "
        f"{band_d[0]:.2f}/{band_d[1]:.2f}/{band_d[2]:.2f} (not a zone)"
    )
    for dg in (-0.01, 0.01):
        alt = [S[t]["eps"] * perpetual_pe(inp["g2"] + dg, S[t]["roe"], r) for t in ("l", "m", "h")]
        print(f"  g2 {dg:+.0%} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}")
    for dr in (-0.005, 0.005):
        Sr = {t: scenario(inp, t, r_disc=r + dr) for t in ("l", "m", "h")}
        alt = [Sr[t]["eps"] * perpetual_pe(inp["g2"], Sr[t]["parent"] / equity, r + dr) for t in ("l", "m", "h")]
        print(f"  r {dr:+.1%} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}")
    # A9 谷底档 coordinates: (i) measured trough→recovery CAGR on the L numerator; (ii) measured
    # n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2"], S["m"]["roe"], r)
        g1_lm = (S["m"]["eps"] / S["l"]["eps"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2"], S["m"]["roe"], r)
        print(
            f"谷底档坐标（A9）{label} n={n}: (i) measured CAGR {g1_meas:.1%} -> {pe_i:.1f}x -> {S['l']['eps'] * pe_i:.2f} "
            f"(vs M {M:.2f}: {'overshoot' if S['l']['eps'] * pe_i > M else 'below M'}); "
            f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {S['l']['eps'] * pe_ii:.2f} (L/M {S['l']['eps'] * pe_ii / M:.3f}, collapsed)"
        )
    print(f"谷底 x 1/r = {S['l']['eps'] / r:.2f}  (= L at g=0; deep_discount pressure coordinate)")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}x (A2e-2c): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (S["l"]["eps"], S["m"]["eps"], S["h"]["eps"])):
        print(line)
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/(2*M):.2%} V_opt/M=0 "
        f"numerator L/M={S['l']['eps']/S['m']['eps']:.2f} H/M={S['h']['eps']/S['m']['eps']:.2f} "
        f"| multiple ratio L/M={pe_l/pe_m:.2f} H/M={pe_h/pe_m:.2f}"
    )
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
