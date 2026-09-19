#!/usr/bin/env python3
"""9696.HK (Tianqi Lithium H) valuation eval.

frameworks/9696.HK.md is the source of truth.
formula_id: tianqi_li2co3_twoleg_volplan_pe10_v2_gordon_v2

Multiples: Gordon at the leg's basket r (whole company = 篮 6 周期商品, both
legs are a lithium-price function; valuation-rules「§r 篮子」) with ONE flat
g2 = the commodity-leg tier default (lithium: inflation + long-run real price
drift ≤ −3%/yr → 0, never negative), tier ROE = EPS_HKD / BPS,
PE_x = perpetual_pe(g2, ROE_x, r).  At g2 = 0 all three tiers sit at 1/r.
The axis 永续 g2 row (6%, cap-truncated) is referenced verbatim (`axis_g2_li`)
and not adopted.

L tier (valuation-rules「谷底档」): the axis L world (Li2CO3 103k = BMI 2028
bottom, above the p90 cost curve) is a regime, not the company's realised
trough (FY2024 −85.57 亿 HKD, lithium 6–8 万).  `recovery_two_stage_pe` on the
measured path (FY2025 5.06 亿 → 2026H1 × 2, n = 1) is printed as a coordinate
only.  The PB floor is disclosure only (峰形区地板条款): L is the scenario
value, never max(scenario, floor).  The ticker's own 5-year TTM PE band is only
a guardrail.

V_opt: the SQM stake as k=1 × the realised 2026H1 investment income, run
through the framework's own (1-t)(1-NCI) bridge and the M-tier multiple
(A2e-7c).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_LI2CO3, check_li2co3_mount  # noqa: E402
from lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "9696.HK.md"
FORMULA_ID = "tianqi_li2co3_twoleg_volplan_pe10_v2_gordon_v2"
MIN_R_MINUS_G = 0.02
# A9: the company's own realised trough→recovery path (Longbridge annual parent NI, HKD:
# FY2024 −85.57 亿 loss trough; FY2025 5.06 亿 → 2026H1 42.42 亿 CNY × 2 × fx ≈ 95.0 亿 HKD).
RECOVERY_MEASURED = {"FY2025→2026H1×2": (5.06, 42.42 * 2 * 1.119522, 1)}
TOL = 0.05
YI = 1e8

REQUIRED = [
    "price", "shares", "bps",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_conc", "realization_chem",
    "cost_conc", "cost_chem",
    "vol_conc_plan", "vol_chem_plan",
    "r_disc", "n_disc",
    "conv_ratio", "fx_hkd_per_cny", "tax_rate", "nci_share",
    "sqm_inv_income_h1",
    "r_perp", "axis_g2_li", "g2",
    "pe_own_min", "pe_own_max",
    "pb_floor",
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

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    for t in S:
        S[t]["roe"] = S[t]["eps_hkd"] / inp["bps"]
        S[t]["pe"] = perpetual_pe(inp["g2"], S[t]["roe"], r)
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): a tier outside the own band is BLOCKED, never fixed by twisting g or r.
    for tag, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(f"guardrail: PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g")
    # 峰形区地板条款 (A10): the PB floor is disclosed, never max()-ed into L.
    floor = inp["pb_floor"] * inp["bps"]
    L = S["l"]["eps_hkd"] * pe_l
    M = S["m"]["eps_hkd"] * pe_m
    H = S["h"]["eps_hkd"] * pe_h
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    zone = zone_of(inp["price"], L, M, H)
    flat = (S["l"]["eps_hkd"] * pe_m, M, S["h"]["eps_hkd"] * pe_m)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")

    # V_opt (A2e-7c): k=1 × realised H1 investment income annualised, through the
    # same (1-t)(1-NCI) bridge A8 uses to strip it out of parent_ops, at the M-tier multiple.
    v_opt = (
        2.0 * inp["sqm_inv_income_h1"] * YI * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])
        / inp["shares"] * inp["fx_hkd_per_cny"] * pe_m
    )

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    pm = re.search(r"p_L/p_M/p_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*", out_sec)
    if pm is None:
        errors.append("p_L/p_M/p_H line not found in Outputs")
        p_tiers = (0.0, 0.0, 0.0)
    else:
        p_tiers = tuple(float(pm.group(i)) for i in (1, 2, 3))
    corrected = (L + p_tiers[0] * v_opt, M + p_tiers[1] * v_opt, H + p_tiers[2] * v_opt)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
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
          f"disc={(1+inp['r_disc'])**(-inp['n_disc']):.4f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}x (A2e-2c): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (S["l"]["eps_hkd"], S["m"]["eps_hkd"], S["h"]["eps_hkd"])):
        print(line)
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} "
        f"numerator L/M={S['l']['eps_hkd']/S['m']['eps_hkd']:.2f} H/M={S['h']['eps_hkd']/S['m']['eps_hkd']:.2f} "
        f"| multiple ratio L/M={pe_l/pe_m:.2f} H/M={pe_h/pe_m:.2f} (ROE term only, g flat)"
    )
    print(
        f"gordon: roe={S['l']['roe']:.3f}/{S['m']['roe']:.3f}/{S['h']['roe']:.3f} (ROE−r {S['l']['roe']-r:+.3f}/{S['m']['roe']-r:+.3f}/{S['h']['roe']-r:+.3f}) "
        f"-> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} inside own band [{inp['pe_own_min']}, {inp['pe_own_max']}]"
    )
    for dg in (-0.01, 0.01):
        band = tuple(S[t]["eps_hkd"] * perpetual_pe(inp["g2"] + dg, S[t]["roe"], r) for t in ("l", "m", "h"))
        print(f"  g2 {dg:+.0%} -> {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f} zone {zone_of(inp['price'], *band)}")
    g_lo, ok_lo = implied_g(inp["pe_own_min"], S["m"]["roe"], r)
    g_hi, ok_hi = implied_g(inp["pe_own_max"], S["m"]["roe"], r)
    print(f"guardrail band-edge g at ROE_M: {g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'}) / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'})")
    print(f"implied r(P) at g2={inp['g2']:g}: {S['m']['eps_hkd'] / inp['price']:.1%} vs basket {r:.1%} (disclosure only)")
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
    print(f"V_opt={v_opt:.2f} (SQM k=1 × H1 inv income {inp['sqm_inv_income_h1']:g}亿 ×2)  p={p_tiers}  "
          f"zone+V: L′={corrected[0]:.2f} M′={corrected[1]:.2f} H′={corrected[2]:.2f} -> {zone_of(inp['price'], *corrected)}  V_opt/M={v_opt/M:.1%}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
