#!/usr/bin/env python3
"""1772.HK (Ganfeng Lithium H) valuation eval.

frameworks/1772.HK.md is the source of truth.
formula_id: ganfeng_li2co3_twopoint_batt_pe10_v3_gordon_v1

Ganfeng does not disclose lithium sales volumes or its self-supplied feed
share, so the lithium leg (salts + mining + JV share, all inside the reported
segment results) is not built bottom-up.  Its pre-tax profit is a straight
line through two of the company's own realised half-years -- 2025H1 at the
cycle trough and 2026H1 on the 2026 platform -- read at the shared Li2CO3 axis
rungs.  The base deck keeps the line's own 2026H1 volume structure (2026E
23 万吨 is a two-house consensus and matches it); the sell-side 2027E volume
(27 万吨, single house) is NOT in the base deck -- it is the candidate band
(A2e-7h): the same formula with the leg scaled by vol_2027e/vol_2026e and
discounted one year.  The battery leg is its annualised segment result
(current, undiscounted) and also supplies the first V_opt component,
solid-state (k=1 x today's battery leg, A2e-7c).  The second component is
volume growth beyond the base: no per-project unit economics, so it is valued
as k=1 x the company's own REALISED step (2024 -> 2025 sales, +42.5%, 2025
annual report) read on the two-point line at the axis M rung, discounted two
years (A12).  Per-tier credits for both components are hard-coded here and
never enter Inputs (A2e-7a); a value-weighted blend is also stated in the doc
for the daily digest, which only reads one p triple.

Multiples: Gordon at the leg's basket r (篮 6 周期商品, both legs share it,
A14) with ONE flat g2 = the commodity-leg tier default 0 (§13: lithium's
long-run real price drift is negative, not taken below zero; the peer
cross-section value is withdrawn, A7), tier ROE = EPS_HKD / BPS; at g = 0 the
multiple is 1/r on every tier.  The axis 永续 g2 row is referenced verbatim
(`axis_g2_li`) and superseded.  The L tier is the axis L regime, not the
company's realised trough (FY2024 loss); `recovery_two_stage_pe` on the
measured path (FY2025 17.63 亿 HKD -> 2026H1 x 2) is printed as a coordinate
only.  The PB 0.70 floor (realised at the 2025-04-08 low) is DISCLOSED, never
max()-ed into L: an asset number that does not move with r has no place inside
an earnings ruler that shrinks with it (A8).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_LI2CO3, check_li2co3_mount, load_axis_g2  # noqa: E402
from lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, outputs_section, parse_baskets, parse_inputs  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1772.HK.md"
FORMULA_ID = "ganfeng_li2co3_twopoint_batt_pe10_v3_gordon_v1"
TOL = 0.05
MIN_R_MINUS_G = 0.02
# The single perpetual r leg (both business legs share the basket, A14); r_disc
# is the same number by construction but is a discount input, not a leg.
LEG_R = ("r_perp",)

# Per-tier option credits (A9): solid-state is a judgement call, the volume step
# is anchored on Dongwu's 2028E/2027E (+12.5% / one realised 42.5% step ~ 0.29).
P_SS = {"l": 0.0, "m": 0.25, "h": 1.0}
P_VOL = {"l": 0.0, "m": 0.29, "h": 1.0}
# A13: the company's own realised trough→recovery path (Longbridge annual parent NI,
# HKD: FY2024 −22.45 亿 loss trough; FY2025 17.63 亿 → 2026H1 42.6 亿 CNY × 2 × fx).
RECOVERY_MEASURED = {"FY2025→2026H1×2": (17.63, 42.6 * 2 * 1.136, 1)}

REQUIRED = [
    "price", "shares", "bps", "fx_hkd_per_cny",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "cal_p0", "cal_li_pretax_0", "cal_p1", "cal_li_pretax_1",
    "vol_2026e", "vol_2027e", "vol_2024a", "vol_2025a", "r_disc", "n_disc",
    "batt_pretax", "net_finance",
    "tax_rate", "nci_share",
    "r_perp", "g2", "axis_g2_li",
    "pe_own_min", "pe_own_max", "pb_floor",
]


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def parent_from_pretax(pretax: float, inp: dict[str, float]) -> float:
    return pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])


def per_share_hkd(parent_yi: float, inp: dict[str, float]) -> float:
    """亿 CNY → HKD per share (shares in millions)."""
    return parent_yi * 100.0 / inp["shares"] * inp["fx_hkd_per_cny"]


def vol_scale(inp: dict[str, float]) -> float:
    """Candidate band only: 2027E/2026E sales ratio (single house), discounted one year (A11)."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    return inp["vol_2027e"] / inp["vol_2026e"] * disc


def li_2026(inp: dict[str, float], li2co3: float) -> float:
    """Lithium-leg pre-tax at 2026H1 volume structure, 亿 CNY (the raw two-point line)."""
    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (
        inp["cal_p1"] - inp["cal_p0"]
    )
    return inp["cal_li_pretax_0"] + (li2co3 - inp["cal_p0"]) * slope


def realised_step(inp: dict[str, float]) -> float:
    """The company's own last realised volume step: 2024 -> 2025 sales (A12, 7c-1)."""
    return (inp["vol_2025a"] - inp["vol_2024a"]) / inp["vol_2024a"]


def v_opt_vol(inp: dict[str, float], li2co3: float, pe_m: float) -> float:
    """One more realised-sized volume step at the given rung, 2028 run-rate, at the M-tier multiple (A12)."""
    disc2 = (1.0 + inp["r_disc"]) ** (-2 * inp["n_disc"])
    pretax = li_2026(inp, li2co3) * realised_step(inp) * disc2
    return per_share_hkd(parent_from_pretax(pretax, inp), inp) * pe_m


def scenario(inp: dict[str, float], tag: str, scale: float = 1.0, g2: float | None = None) -> dict[str, float]:
    """Base deck: scale = 1.0 (the line's own 2026 volume structure).  Candidate: vol_scale."""
    g = inp["g2"] if g2 is None else g2
    li = li_2026(inp, inp[f"li2co3_{tag}"]) * scale
    pretax = li + inp["batt_pretax"] - inp["net_finance"]
    parent = parent_from_pretax(pretax, inp)
    eps = per_share_hkd(parent, inp)
    roe = eps / inp["bps"]
    pe = perpetual_pe(g, roe, inp["r_perp"])
    return {"li": li, "pretax": pretax, "parent": parent, "eps": eps, "roe": roe, "pe": pe, "px": eps * pe}


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

    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    # valuation-rules「§r 篮子」/「永续增长口径」: r is the named basket's value, one
    # flat g2 ≤ cap(r); the axis row is referenced verbatim and superseded.
    baskets = parse_baskets(md)
    for field in LEG_R:
        if field not in baskets:
            errors.append(f"{field}: no 篮 N in Inputs source cell (A14)")
        errors += check_r(inp[field], field, baskets.get(field))
        errors += check_g_cap(inp["g2"], inp[field], f"g2@{field}")
        errors += check_g_cap(inp["axis_g2_li"], inp[field], f"axis_g2_li@{field}")
        if inp[field] - inp["g2"] < MIN_R_MINUS_G:
            errors.append(f"{field} − g2 = {inp[field] - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    # The candidate band / volume option discount at the same basket r as the leg (A14).
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal the leg's basket r r_perp={inp['r_perp']} (A14)")
    want_axis = load_axis_g2(AXIS_LI2CO3)
    if abs(inp["axis_g2_li"] - want_axis) > 1e-9:
        errors.append(f"axis_g2_li={inp['axis_g2_li']} vs _AXIS.lithium-carbonate 永续 g2 {want_axis}")
    if not (inp["cal_p0"] < inp["cal_p1"] and inp["cal_li_pretax_0"] < inp["cal_li_pretax_1"]):
        errors.append("calibration points must be ordered (trough below platform)")
    if not inp["vol_2027e"] > inp["vol_2026e"]:
        errors.append("2027E volume must exceed 2026E (the candidate scale is a growth factor)")
    if not inp["vol_2025a"] > inp["vol_2024a"]:
        errors.append("realised 2024->2025 step must be positive (V_opt unit)")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): a tier outside the own band is BLOCKED, never fixed by twisting g or r.
    for tag, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(f"guardrail: PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g")
    # A8: the floor is disclosed only; L is the scenario value.
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["px"]
    L = scenario_L
    M = S["m"]["px"]
    H = S["h"]["px"]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    # Option components: solid-state (k=1 x today's battery leg) and one more
    # realised-sized volume step at the axis M rung (A12).  Both at the M-tier multiple.
    v_ss = per_share_hkd(parent_from_pretax(inp["batt_pretax"], inp), inp) * pe_m
    v_vol = v_opt_vol(inp, inp["li2co3_m"], pe_m)
    v_opt = v_ss + v_vol

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    # A2e-2c flat-multiple ladder at PE_M.
    flat = (S["l"]["eps"] * pe_m, M, S["h"]["eps"] * pe_m)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")
    # Candidate band (A2e-7h): same formula, only the single-house 2027E volume
    # scale (× δ) swapped in; g2 / r / bridge untouched; L′ is the scenario value like L.
    C = {t: scenario(inp, t, vol_scale(inp)) for t in ("l", "m", "h")}
    Lc, Mc, Hc = (C[t]["px"] for t in ("l", "m", "h"))
    if not (Lc < Mc < Hc):
        errors.append(f"candidate band not ordered: {Lc:.2f}/{Mc:.2f}/{Hc:.2f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = outputs_section(md)
    for label, want_v, rx in (
        ("scenario_L", scenario_L, r"`scenario_L` = \*\*([0-9.]+)\*\*"),
        ("floor", floor, r"`floor` = \*\*([0-9.]+)\*\*"),
        ("L′", Lc, r"候选带（[^）]+）[^\n]*?L′ = \*\*([0-9.]+)\*\*"),
        ("M′", Mc, r"候选带（[^）]+）[^\n]*?M′ = \*\*([0-9.]+)\*\*"),
        ("H′", Hc, r"候选带（[^）]+）[^\n]*?H′ = \*\*([0-9.]+)\*\*"),
    ):
        s = first_float(rx, out_sec)
        if s is None or abs(s - want_v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {want_v:.4f}")
    vm = re.search(
        r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*（固态 \*\*([0-9.]+)\*\* \+ 量增 \*\*([0-9.]+)\*\*）",
        out_sec,
    )
    if vm is None:
        errors.append("stated V_opt line (total + two components) not found")
    else:
        for label, stated, want in (
            ("V_opt", float(vm.group(1)), v_opt),
            ("V_opt^ss", float(vm.group(2)), v_ss),
            ("V_opt^vol", float(vm.group(3)), v_vol),
        ):
            if abs(stated - want) > TOL:
                errors.append(f"{label}: stated {stated} vs recomputed {want:.4f}")

    # zone+V table: the two per-tier credit triples are hard-coded above; the
    # doc must restate them verbatim and the corrected band must reproduce.
    for name, table, rx in (
        ("p^ss", P_SS, r"p\^\{ss\}_\{L/M/H\}\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*"),
        ("p^vol", P_VOL, r"p\^\{vol\}_\{L/M/H\}\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*"),
    ):
        pm = re.search(rx, out_sec)
        if pm is None:
            errors.append(f"{name} triple not stated")
            continue
        for k, got in zip("lmh", pm.groups()):
            if abs(float(got) - table[k]) > 1e-9:
                errors.append(f"{name}_{k}: stated {got} vs eval constant {table[k]}")
    base = {"L": L, "M": M, "H": H}
    adj = {k: base[k] + P_SS[t] * v_ss + P_VOL[t] * v_vol for k, t in zip("LMH", "lmh")}
    # Table 3 rows: | L | 10.27 | 0 | 0.00 | 0 | 0.00 | **10.27** | ...
    for k, v in adj.items():
        m3 = re.search(rf"^\| {k} \| [0-9.]+ \| [^|]+\| [0-9.]+ \| [^|]+\| [0-9.]+ \| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - v) > TOL:
            errors.append(f"table3 {k}: stated {m3.group(1) if m3 else None} vs recomputed {v:.4f}")
    for label, want_v, rx in (("A′", (adj["L"] + adj["M"]) / 2, r"A′ = \*\*([0-9.]+)\*\*"),
                              ("B′", (adj["M"] + adj["H"]) / 2, r"B′ = \*\*([0-9.]+)\*\*")):
        s = first_float(rx, out_sec)
        if s is None or abs(s - want_v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {want_v:.4f}")
    # The daily digest reads a single p triple applied to the total: the stated
    # blend must land on the same corrected band.
    pm = re.search(
        r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec
    )
    if pm is None:
        errors.append("blended p_L/p_M/p_H (digest) not stated")
    else:
        for k, t, got in zip("LMH", "lmh", pm.groups()):
            blended = base[k] + float(got) * v_opt
            if abs(blended - adj[k]) > TOL:
                errors.append(
                    f"blended p_{t}={got} gives {k}′={blended:.4f}, components give {adj[k]:.4f}"
                )

    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (inp["cal_p1"] - inp["cal_p0"])
    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  slope={slope*1e4:.2f} 亿/万元"
        + f"  base scale 1.0 (2026 structure); candidate scale={inp['vol_2027e']:g}/{inp['vol_2026e']:g} x disc = {vol_scale(inp):.4f}"
    )
    print("baskets: " + ", ".join(f"{k} 篮 {baskets[k]} r={inp[k]:g}" for k in LEG_R) + f"; r_disc={inp['r_disc']:g}")
    print(f"{'档':<3}{'锂腿税前':>9}{'税前':>8}{'归母':>8}{'EPS_HKD':>9}{'ROE':>7}{'PE':>7}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s_ = S[t]
        print(
            f"{t.upper():<3}{s_['li']:9.1f}{s_['pretax']:8.1f}{s_['parent']:8.1f}"
            f"{s_['eps']:9.3f}{s_['roe']:7.1%}{s_['pe']:7.2f}{s_['px']:8.2f}"
        )
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × bps, disclosed only, A8)  scenario_L={scenario_L:.2f} = L  "
          f"scenario_L/M={scenario_L / M:.3f}  floor vs band: {zone_of(floor, L, M, H)}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  "
          f"V_opt={v_opt:.2f} = ss {v_ss:.2f} + vol {v_vol:.2f} "
          f"(one realised step {realised_step(inp):.1%} = {inp['vol_2024a']:g}→{inp['vol_2025a']:g} 万吨 @axis M, δ², PE_M)")
    print("zone+V: " + "  ".join(
        f"{k}={adj[k]:.2f}(p_ss={P_SS[t]:g},p_vol={P_VOL[t]:g})" for k, t in zip("LMH", "lmh")
    ) + f"  A′={(adj['L'] + adj['M']) / 2:.2f} B′={(adj['M'] + adj['H']) / 2:.2f}"
        f"  vol step @L/H rung = {v_opt_vol(inp, inp['li2co3_l'], pe_m):.2f}/{v_opt_vol(inp, inp['li2co3_h'], pe_m):.2f}")
    print(f"candidate (2027E 量·大华单家, scale {vol_scale(inp):.4f}): L′={Lc:.2f} M′={Mc:.2f} H′={Hc:.2f}  -> {zone_of(inp['price'], Lc, Mc, Hc)}")
    print(f"gordon: r={inp['r_perp']:g} (篮 {baskets['r_perp']}) g2={inp['g2']:g} flat [§13 commodity-leg tier default] "
          f"(axis 永续 g2 {inp['axis_g2_li']:g} referenced, superseded — A7) "
          f"roe={S['l']['roe']:.3f}/{S['m']['roe']:.3f}/{S['h']['roe']:.3f} -> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} "
          f"inside own band [{inp['pe_own_min']}, {inp['pe_own_max']}]")
    g_lo, ok_lo = implied_g(inp["pe_own_min"], S["m"]["roe"], inp["r_perp"])
    g_hi, ok_hi = implied_g(inp["pe_own_max"], S["m"]["roe"], inp["r_perp"])
    print(f"guardrail band-edge g at ROE_M: {g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'}) / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'}) — reported only (A7)")
    for dg in (-0.01, 0.01):
        alt = {t: scenario(inp, t, g2=inp["g2"] + dg) for t in ("l", "m", "h")}
        print(f"  g2 {dg:+.0%} -> PE {alt['l']['pe']:.2f}/{alt['m']['pe']:.2f}/{alt['h']['pe']:.2f}, "
              f"band {alt['l']['px']:.2f}/{alt['m']['px']:.2f}/{alt['h']['px']:.2f} "
              f"zone={zone_of(inp['price'], alt['l']['px'], alt['m']['px'], alt['h']['px'])}")
    # Implied r(P): single-stage Gordon at g = 0 on the M-tier EPS (§7 rule 3 disclosure).
    print(f"implied r(P) = E_M / P = {S['m']['eps']:.3f} / {inp['price']:g} = {S['m']['eps'] / inp['price']:.2%} "
          f"(vs basket r {inp['r_perp']:.0%}: {S['m']['eps'] / inp['price'] - inp['r_perp']:+.1%})")
    if inp["price"] > H:
        print(f"market-implied p = (P − H) / V_opt = {(inp['price'] - H) / v_opt:.2f}")
    # A13 谷底档 coordinates: (i) measured trough→recovery CAGR on the L numerator; (ii) the
    # measured n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2"], S["m"]["roe"], inp["r_perp"])
        g1_lm = (S["m"]["eps"] / S["l"]["eps"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2"], S["m"]["roe"], inp["r_perp"])
        print(f"谷底档坐标（A13）{label} n={n}: (i) measured CAGR {g1_meas:.0%} -> {pe_i:.1f}x -> {S['l']['eps'] * pe_i:.1f} "
              f"(vs M {M:.2f}: {'overshoot' if S['l']['eps'] * pe_i > M else 'below M'}); "
              f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {S['l']['eps'] * pe_ii:.2f} (L/M {S['l']['eps'] * pe_ii / M:.3f}, collapsed)")
    print(f"谷底 x 1/r = {S['l']['eps'] / inp['r_perp']:.2f}  (deep_discount pressure coordinate; = L at g = 0)")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}x (A2e-2c): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (S["l"]["eps"], S["m"]["eps"], S["h"]["eps"])):
        print(line)
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} V_opt/M={v_opt/M:.1%} "
        f"numerator L/M={S['l']['eps']/S['m']['eps']:.2f} H/M={S['h']['eps']/S['m']['eps']:.2f} "
        f"| multiple ratio L/M={pe_l/pe_m:.2f} H/M={pe_h/pe_m:.2f} (ROE term only, g flat)"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
