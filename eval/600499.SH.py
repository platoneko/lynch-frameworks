#!/usr/bin/env python3
"""600499.SH (Keda Industrial Group) valuation eval.

frameworks/600499.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).

formula_id: keda_lanke_axis_afr_mac_perpetual_g_vopt_named_v5

Three legs, each on its own basket r, added per share (SOTP):

  Lanke leg    NI_lk  = delta * stake * vol_plan * (li2co3 * realization - cost) * (1 - tax)
               PE_lk  = min(1, 1 - g2_li/ROE) / (r_li - g2_li)     (g2_li = 0 -> 1/r_li, flat)
  Africa leg   NI_afr = ni_exli * w_afr
               PE_afr = min(1, 1 - g2_afr/ROE) / (r_afr - g2_afr)  (g2_afr = Africa axis ladder)
  machinery    NI_mac = ni_exli * w_mac
               PE_mac = min(1, 1 - g2_mac/ROE) / (r_mac - g2_mac)  (g2_mac = own ladder, A7)
  ROE          = (ni_exli + NI_lk) / equity                        (company-wide, shared by all legs)
  anode K_remain  P_x = capex_anode * stake_anode * max(0, 1 - roic_anode_x / r_mac)   (A20)
  anchor       = (sum_i NI_i * PE_i - P_x) * 1e8 / shares

r comes from the basket each leg is assigned to (valuation-rules.md「§r 篮子」,
values in gordon.BASKET_R); the Inputs rows `r_li` / `r_afr` / `r_mac` name the
basket in their source cell and `check_r` enforces that the value is that
basket's.  Lanke and Africa sit in 篮 6 (13%, zero growth = 7.69x), the
machinery leg in 篮 4 (10%, zero growth = 10x).  Legs with different r cannot
share one blended g, so the non-Li numerator is split by w_afr / w_mac and each
part gets its own multiple; the Lanke nameplate-volume discount `r_disc` follows
the Lanke leg's basket r (A3).

Keda's 43.58% of Lanke Lithium runs through equity-method investment income
and swung group net income 10.06 -> 42.51 -> 10.06亿 in four years.  The Lanke
leg reads the shared Li2CO3 axis directly, with nameplate volume discounted one
year — the same "2027 volume x delta" construction as 9696.HK / 000792.SZ /
1772.HK.  Both axes are checked against their files, so Keda can invent neither
its own lithium deck nor its own Africa case.

Why the multiples are generated rather than sampled from history: the stock
printed its LOWEST annual PE (7.7x) at the lithium peak and its HIGHEST (17.2x)
at the trough — the historical band measures where the cycle stood, not what
the business is worth.  It survives here only as a fence (`pe_own_lo/hi`) on
the company-level implied multiple (anchor / total EPS).

Lanke leg g2 (valuation-rules「§13 商品腿」): a commodity leg's perpetual g is
inflation plus the commodity's long-run real price drift; lithium's real drift
is <= -3%, so g2_li = 0 (never negative).  The peer cross-section value 2.35%
is a cycle-endpoint reading and is printed as a sensitivity only; the axis 永续
g2 row (6%, cap-truncated) is referenced verbatim (`axis_g2_li`) and not used.
The Lanke L tier is the axis L regime, not the company's realised trough; the
recovery form `recovery_two_stage_pe` on the measured paths is printed as a
coordinate only (A18).  Book value is disclosed, never max()'d into L.

Anode expansion (A20, retention audit D bucket): the 45亿 Baotou graphite
project (announced 2026-09-21) is unspent capital whose output is not in any
numerator, so it is charged K_remain x (1 - ROIC_proj / r_mac) per tier, with
ROIC_proj read off steady-state peer years (L = 2026H1 price-war reading, M =
peer FY2024-25 median, H = best integrated peer through-cycle).  The charge
floors at 0: unspent money earns no credit above r.

V_opt (2026-10-04, valuation-rules「未建模期权」): the named overseas building-
materials projects not yet in the 2026H1-annualised numerator — the Africa
axis no longer carries them in its g.  Units = capacity x unit revenue
(ceramics: FY2024 segment revenue / FY2024 tile sales; glass: the FY2025
segment residual / glass output — a public-data inference with its biases
named in A22) x the Africa leg's own 归母 margin (stake already inside),
priced on the Africa leg's H multiple and discounted from the start-up year
to the numerator year at r_afr.  p_k = 0 / 0.25 / 1.0 lives in table 3 only.

Run:  python3 frameworks/eval/600499.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_LI2CO3, check_africa_mount, check_li2co3_mount, load_axis_g2  # noqa: E402
from lib.gordon import (  # noqa: E402
    basket_r, check_g_cap, check_r, implied_g, payout, perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600499.SH.md"
FORMULA_ID = "keda_lanke_axis_afr_mac_perpetual_g_vopt_named_v5"
MIN_R_MINUS_G = 0.02
# A18: realised trough→recovery paths — the company's (Longbridge annual parent NI,
# FY2024 10.06 亿 → FY2025 13.09 亿, mostly Africa growth) and Lanke's own (net profit
# FY2025 7.30 亿 → 2026H1 14.11 亿 × 2, the lithium price V; 科达 interim / annual report).
RECOVERY_MEASURED = {"公司 FY2024→FY2025": (10.06, 13.09, 1), "蓝科 FY2025→2026H1×2": (7.30, 28.22, 1)}
# A6 sensitivity: the lithium-producer cross-section g2 that the framework does not use.
G2_LI_PEER = 0.0235
# A20 sensitivity: anode ROIC with every tier on 2026H1 price-war readings —
# 中科电气 3.8% / two-peer mean 5.7% / 尚太科技 7.6% (annualised, Longbridge).
ANODE_ROIC_STRESS = (0.038, 0.057, 0.076)

TIERS = ("l", "m", "h")
LEGS = ("lk", "afr", "mac")
R_ROWS = {"lk": "r_li", "afr": "r_afr", "mac": "r_mac"}
YI = 1e8

REQUIRED = [
    "shares", "bps", "equity",
    "r_li", "r_afr", "r_mac",
    "ni_exli",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_lk", "cost_lk", "vol_lk_plan", "vol_lk_h1",
    "r_disc", "n_disc", "stake_lk", "tax_lk", "g2_li", "axis_g2_li",
    "w_afr", "w_mac",
    "g2_afr_l", "g2_afr_m", "g2_afr_h",
    "g2_mac_l", "g2_mac_m", "g2_mac_h",
    "ni_ttm", "ni_fy2024", "ni_exli_fy2025", "ni_2026e_street", "tp_street",
    "pe_own_hi", "pe_own_lo",
    "capex_anode", "stake_anode", "roic_anode_l", "roic_anode_m", "roic_anode_h",
    "afr_rev_fy2025", "afr_cogs_fy2025", "afr_rev_h1", "afr_cogs_h1",
    "tf_np_fy2025", "tf_uplift_fy2025", "stake_tf", "nci_fy2025", "nci_h1",
    "afr_rev_yoy_fy2025", "tile_sales_fy2025", "tile_sales_yoy_fy2025", "glass_out_fy2025",
    "tile_cap_now", "tile_cap_after", "glass_peru", "glass_ghana", "t_tile", "t_peru", "t_ghana",
]
NUM_YEAR = 2026            # Africa / machinery numerator = 2026H1 annualised
P_TIERS = (0.0, 0.25, 1.0)  # A22 — table 3 only, never an input
TOL = 0.05


def opt_units(inp: dict[str, float]) -> dict[str, float]:
    """A22: tile 元/m² and glass 元/t from public segment data (inference, biases in A22)."""
    rev24 = inp["afr_rev_fy2025"] / (1.0 + inp["afr_rev_yoy_fy2025"])
    tile24 = inp["tile_sales_fy2025"] / (1.0 + inp["tile_sales_yoy_fy2025"])
    p_tile = rev24 / tile24                                     # 亿元 / 亿㎡ = 元/㎡
    glass_rev = inp["afr_rev_fy2025"] - inp["tile_sales_fy2025"] * p_tile   # 亿元
    p_glass = glass_rev / inp["glass_out_fy2025"] * 1e4         # 亿元 / 万吨 → 元/吨
    margin = inp["w_afr"] * inp["ni_exli"] / (2.0 * inp["afr_rev_h1"])
    return {"p_tile": p_tile, "p_glass": p_glass, "margin": margin}


def opt_items(inp: dict[str, float], pe_afr_h: float, glass_scale: float = 1.0) -> list[tuple[str, float, float, float]]:
    """[(label, revenue 亿, ΔNI 亿, V per share)] for the named projects (A22)."""
    u = opt_units(inp)
    items = [
        ("瓷砖 科特迪瓦二期 + 基苏木二期 + 几内亚", (inp["tile_cap_after"] - inp["tile_cap_now"]) * u["p_tile"], inp["t_tile"]),
        ("秘鲁玻璃 20 万吨", inp["glass_peru"] * u["p_glass"] * glass_scale / 1e4, inp["t_peru"]),
        ("加纳玻璃 20 万吨", inp["glass_ghana"] * u["p_glass"] * glass_scale / 1e4, inp["t_ghana"]),
    ]
    out = []
    for label, rev, t in items:
        dni = rev * u["margin"]
        v = dni * pe_afr_h / (1.0 + inp["r_afr"]) ** (t - NUM_YEAR) * YI / inp["shares"]
        out.append((label, rev, dni, v))
    return out
# A5 (valuation-rules「公开数据推断」, 2026-10-03): w_afr is inferred, not a placeholder.
W_TOL = 1e-5


def afr_weight(inp: dict[str, float]) -> dict[str, float]:
    """A5 Africa-leg share of the ex-Lanke numerator, from disclosed numbers only.

    Point (gross-profit route, two periods): Twyford's FY2025 net profit / segment
    gross profit, applied to the 2026H1 segment gross profit; Twyford's parent
    share from the restructuring pro forma (uplift / 51.55%); Keda's share 48.45%.
    Assumption: net / gross ratio unchanged FY2025 -> 2026H1 (operating leverage
    makes this the low side).  Bracket (NCI route): consolidated minority P&L less
    the non-Africa minority share (FY2025 residual, at full-year or half-year level).
    """
    out: dict[str, float] = {}
    gp25 = inp["afr_rev_fy2025"] - inp["afr_cogs_fy2025"]
    gph1 = inp["afr_rev_h1"] - inp["afr_cogs_h1"]
    s = inp["stake_tf"]
    tf_attr25 = inp["tf_uplift_fy2025"] / (1.0 - s)
    attr = tf_attr25 / inp["tf_np_fy2025"]
    exli_h1 = inp["ni_exli"] / 2.0
    out["FY2025 披露"] = tf_attr25 * s / inp["ni_exli_fy2025"]
    out["2026H1 毛利路径"] = gph1 * inp["tf_np_fy2025"] / gp25 * attr * s / exli_h1
    local25 = inp["tf_np_fy2025"] - tf_attr25
    other25 = inp["nci_fy2025"] - inp["tf_uplift_fy2025"] - local25
    for label, other in (("2026H1 少数股东路径·其余按全年", other25), ("2026H1 少数股东路径·其余按半年", other25 / 2.0)):
        out[label] = (inp["nci_h1"] - other - local25 / 2.0) * s / (1.0 - s) / exli_h1
    return out


def lanke_ni(inp: dict[str, float], tag: str) -> float:
    """Keda's share of Lanke net profit, 亿 CNY, nameplate volume discounted."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    margin = inp[f"li2co3_{tag}"] * inp["realization_lk"] - inp["cost_lk"]
    return disc * inp["stake_lk"] * inp["vol_lk_plan"] * margin * (1.0 - inp["tax_lk"]) / YI


def legs(inp: dict[str, float], tag: str) -> dict[str, float]:
    """{leg: net income} for one tier, 亿 CNY."""
    return {"lk": lanke_ni(inp, tag), "afr": inp["ni_exli"] * inp["w_afr"], "mac": inp["ni_exli"] * inp["w_mac"]}


def leg_g(inp: dict[str, float], leg: str, tag: str) -> float:
    return inp["g2_li"] if leg == "lk" else inp[f"g2_{leg}_{tag}"]


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return (inp["ni_exli"] + lanke_ni(inp, tag)) / inp["equity"]


def leg_pe(inp: dict[str, float], leg: str, tag: str, r_shift: float = 0.0,
           g_override: float | None = None) -> float:
    g = leg_g(inp, leg, tag) if g_override is None else g_override
    return perpetual_pe(g, forward_roe(inp, tag), inp[R_ROWS[leg]] + r_shift)


def anode_penalty(inp: dict[str, float], tag: str) -> float:
    """A20: unspent anode capex charged at (1 - ROIC_proj / r_mac), 亿 CNY; no credit above r."""
    shortfall = max(0.0, 1.0 - inp[f"roic_anode_{tag}"] / inp["r_mac"])
    return inp["capex_anode"] * inp["stake_anode"] * shortfall


def value(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None) -> float:
    """Sum of legs less the anode K_remain charge, 亿 CNY.  `pes` overrides the per-leg multiples."""
    ni = legs(inp, tag)
    pe = pes or {leg: leg_pe(inp, leg, tag) for leg in LEGS}
    return sum(ni[leg] * pe[leg] for leg in LEGS) - anode_penalty(inp, tag)


def anchor(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None) -> float:
    return value(inp, tag, pes) * YI / inp["shares"]


def implied_r_shift(inp: dict[str, float], target: float) -> float:
    """δ such that the M-tier SOTP with every leg at r_leg + δ equals `target`
    (the street target or book value — never the current quote).

    All three basket r move together (the volume discount r_disc stays put); the
    answer is the parallel shift the target implies for the basket table, not a
    per-leg r.  Bisection on δ ∈ [-8%, +20%]: the SOTP is monotone decreasing in δ.
    """
    lo, hi = -0.08, 0.20

    def f(delta: float) -> float:
        pes = {leg: leg_pe(inp, leg, "m", r_shift=delta) for leg in LEGS}
        return anchor(inp, "m", pes) - target

    if f(lo) < 0 or f(hi) > 0:
        raise ValueError("implied r shift outside bisection bracket")
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = {leg: inp[R_ROWS[leg]] for leg in LEGS}

    # --- Step 1: baskets — each leg's r must be the basket it names -----------
    baskets = parse_baskets(md)
    for leg in LEGS:
        row = R_ROWS[leg]
        if row not in baskets:
            errors.append(f"{row}: Inputs source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errors += check_r(r[leg], row, baskets.get(row))
    # A3: the nameplate-volume discount follows the Lanke leg's basket r.
    if abs(inp["r_disc"] - r["lk"]) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal r_li={r['lk']} (A3)")
    if errors:
        return report(errors, "FAIL (baskets)")

    # --- Step 2: Lanke leg reads the shared lithium axis ------------------------
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    # Lanke g2: commodity-leg default (0) under the Lanke basket's cap and off the
    # pole; the axis row is referenced verbatim and not used (A6).
    for k in ("g2_li", "axis_g2_li"):
        errors += check_g_cap(inp[k], r["lk"], k)
    if inp["g2_li"] < 0:
        errors.append(f"g2_li={inp['g2_li']} < 0 — commodity-leg g2 floors at 0 (valuation-rules §13)")
    if r["lk"] - inp["g2_li"] < MIN_R_MINUS_G:
        errors.append(f"r_li − g2_li = {r['lk'] - inp['g2_li']:.4f} < {MIN_R_MINUS_G} (pole)")
    want_axis = load_axis_g2(AXIS_LI2CO3)
    if abs(inp["axis_g2_li"] - want_axis) > 1e-9:
        errors.append(f"axis_g2_li={inp['axis_g2_li']} vs _AXIS.lithium-carbonate 永续 g2 {want_axis}")
    for key, lo, hi in (
        ("realization_lk", 0.0, 1.0), ("stake_lk", 0.0, 1.0), ("tax_lk", -1e-12, 1.0),
    ):
        if not lo < inp[key] < hi:
            errors.append(f"{key}={inp[key]} outside ({lo}, {hi})")
    if inp["cost_lk"] <= 0 or inp["vol_lk_plan"] <= 0:
        errors.append("cost_lk and vol_lk_plan must be positive")
    ni = {t: legs(inp, t) for t in TIERS}
    errors += ladder("Lanke NI", *(ni[t]["lk"] for t in TIERS))
    if ni["l"]["lk"] <= 0:
        errors.append(f"Lanke NI_L={ni['l']['lk']:.2f} <= 0 — leg does not clear cost at axis L")

    # --- Step 3: non-Li legs — weights, growth ladders, Africa axis ------------
    w_inf = afr_weight(inp)
    if abs(inp["w_afr"] - w_inf["2026H1 毛利路径"]) > W_TOL:
        errors.append(f"w_afr={inp['w_afr']} vs A5 inference {w_inf['2026H1 毛利路径']:.6f}")
    w_sum = inp["w_afr"] + inp["w_mac"]
    if abs(w_sum - 1.0) > 1e-6:
        errors.append(f"leg weights must sum to 1: {w_sum}")
    for leg in ("afr", "mac"):
        if not 0.0 < inp[f"w_{leg}"] < 1.0:
            errors.append(f"w_{leg}={inp[f'w_{leg}']} outside (0, 1)")
        errors += ladder(f"g2_{leg}", *(inp[f"g2_{leg}_{t}"] for t in TIERS))
        for t in TIERS:
            g = inp[f"g2_{leg}_{t}"]
            if r[leg] - g <= 0:
                errors.append(f"g2_{leg}_{t}={g:.4f} >= r_{leg}={r[leg]} — perpetuity diverges")
            # valuation-rules.md 永续上限: min(6%, r − 4%) per leg.
            errors += check_g_cap(g, r[leg], f"g2_{leg}_{t}")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    # Growth is paid for out of retained earnings; a shrinking business is not
    # assumed to hand back more than it earns — per leg.
    for t in TIERS:
        roe = forward_roe(inp, t)
        if roe <= 0:
            errors.append(f"ROE_{t}={roe:.4f} must be positive")
            continue
        for leg in LEGS:
            g = leg_g(inp, leg, t)
            pay = payout(g, roe)
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
    errors += check_africa_mount(
        (inp["g2_afr_l"], inp["g2_afr_m"], inp["g2_afr_h"])
    )
    # A20: the anode charge sits on the machinery leg's basket and eases toward H.
    if inp["capex_anode"] <= 0 or not 0.0 < inp["stake_anode"] < 1.0:
        errors.append("capex_anode must be positive and stake_anode in (0, 1)")
    errors += ladder("roic_anode", *(inp[f"roic_anode_{t}"] for t in TIERS))
    if errors:
        return report(errors, "FAIL (guards/axis)")

    pe = {t: {leg: leg_pe(inp, leg, t) for leg in LEGS} for t in TIERS}
    total = {t: inp["ni_exli"] + ni[t]["lk"] for t in TIERS}
    # Guardrail (裁决顺序 ③): the company-level implied multiple (SOTP value /
    # total NI) inside the own-year band; outside is BLOCKED, never fixed by
    # twisting g or r.
    pe_company = {t: value(inp, t) / total[t] for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_lo"] - 1e-9 <= pe_company[t] <= inp["pe_own_hi"] + 1e-9):
            errors.append(
                f"guardrail: PE_company_{t.upper()}={pe_company[t]:.2f} outside own-year band "
                f"[{inp['pe_own_lo']}, {inp['pe_own_hi']}] — BLOCKED, do not twist g"
            )
    if errors:
        return report(errors, "FAIL (guardrail)")

    # --- Step 4: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    # flat-multiple: each leg held at its own PE_M across the three tiers — the
    # ladder must survive on the Lanke leg's axis price alone.
    flat = {t: anchor(inp, t, pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- Step 5: V_opt (A22) — named projects, own ruler, start-up year → numerator year
    items = opt_items(inp, pe["h"]["afr"])
    v_opt = sum(x[3] for x in items)
    for t_key in ("t_tile", "t_peru", "t_ghana"):
        if inp[t_key] < NUM_YEAR:
            errors.append(f"{t_key} before the numerator year")
    if not inp["tile_cap_after"] > inp["tile_cap_now"] > 0:
        errors.append("tile capacity must step up")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs: {leaked}")
    outs = md.split("### Outputs", 1)[-1]
    vm = re.search(r"V_\{?opt\}?\\?\)?\s*[≈=]\s*\*{0,2}\s*\+?([0-9]+(?:\.[0-9]+)?)", outs)
    if vm is None or abs(float(vm.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt: stated {vm.group(1) if vm else None} vs recomputed {v_opt:.4f}")
    pm_ = re.search(r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)", outs)
    if pm_ is None or tuple(float(x) for x in pm_.groups()) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {pm_.groups() if pm_ else None} vs {P_TIERS}")
    adj = [a + p_ * v_opt for a, p_ in zip((L, M, H), P_TIERS)]

    # --- report --------------------------------------------------------------
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    v = {t: {leg: ni[t][leg] * pe[t][leg] for leg in LEGS} for t in TIERS}
    print(f"formula_id={FORMULA_ID}")
    print("篮子: " + "; ".join(
        f"{R_ROWS[leg]} 篮 {baskets[R_ROWS[leg]]} {basket_r(baskets[R_ROWS[leg]]):.0%}"
        f" (零增长 {1 / r[leg]:.2f}x)" for leg in LEGS))
    print(f"蓝科腿 g2_li {inp['g2_li']:g} flat（商品腿默认）→ PE {pe['l']['lk']:.2f}/{pe['m']['lk']:.2f}/{pe['h']['lk']:.2f}; "
          f"axis row {inp['axis_g2_li']:g} referenced, not used")
    print(
        "li2co3 OK vs _AXIS.lithium-carbonate: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  蓝科量={inp['vol_lk_plan']:g} x disc={disc:.4f} (r_disc = r_li)"
        f" (H1 sales x2 = {inp['vol_lk_h1']:g}, not in formula)"
    )
    print(f"{'档':<3}{'蓝科归母':>9}{'非洲NI':>8}{'机械NI':>8}"
          f"{'g_afr':>7}{'g_mac':>7}{'ROE':>8}{'派息afr':>8}{'PE蓝科':>7}{'PE非洲':>7}{'PE机械':>7}"
          f"{'蓝科亿':>8}{'非洲亿':>8}{'机械亿':>8}{'公司PE':>7}{'锚点CNY':>9}")
    for t in TIERS:
        roe = forward_roe(inp, t)
        print(f"{t.upper():<3}{ni[t]['lk']:9.2f}{ni[t]['afr']:8.2f}{ni[t]['mac']:8.2f}"
              f"{inp[f'g2_afr_{t}']:7.0%}{inp[f'g2_mac_{t}']:7.0%}{roe:8.2%}"
              f"{payout(inp[f'g2_afr_{t}'], roe):8.1%}{pe[t]['lk']:7.2f}{pe[t]['afr']:7.2f}{pe[t]['mac']:7.2f}"
              f"{v[t]['lk']:8.1f}{v[t]['afr']:8.1f}{v[t]['mac']:8.1f}{pe_company[t]:7.2f}{anchor(inp, t):9.2f}")
    naive = {t: sum(ni[t][leg] / (r[leg] - leg_g(inp, leg, t)) for leg in ("afr", "mac")) for t in TIERS}
    real = {t: v[t]["afr"] + v[t]["mac"] for t in TIERS}
    print(f"非锂两腿若按 100% 派息的 1/(r-g)：{naive['l']:.1f} / {naive['m']:.1f} / {naive['h']:.1f} 亿"
          f" — H 档高估 {naive['h'] / real['h'] - 1:.0%}（留存成本，A16）")
    print(f"非洲腿 g 取自 _AXIS.africa-corridor.md ✓ "
          f"({inp['g2_afr_l']:.0%}/{inp['g2_afr_m']:.0%}/{inp['g2_afr_h']:.0%}，本票按永续落地)")
    print("非洲腿权重 A5 公开数据推断: " + " · ".join(f"{k} {v:.1%}" for k, v in w_inf.items())
          + f" → 取毛利路径 {inp['w_afr']:.4f}")
    for label, w in w_inf.items():
        alt = {**inp, "w_afr": w, "w_mac": 1.0 - w}
        print(f"敏感区 w_afr {label}: " + " / ".join(f"{anchor(alt, t):.2f}" for t in TIERS))
    print(f"③ 出带: 整公司隐含 PE {pe_company['l']:.2f}/{pe_company['m']:.2f}/{pe_company['h']:.2f} "
          f"落在 own-year 实测带 [{inp['pe_own_lo']:g}, {inp['pe_own_hi']:g}] 内 ✓")
    roe_m = forward_roe(inp, "m")
    for leg in ("afr", "mac"):
        g_lo, ok_lo = implied_g(inp["pe_own_lo"], roe_m, r[leg])
        g_hi, ok_hi = implied_g(inp["pe_own_hi"], roe_m, r[leg])
        print(f"guardrail band-edge g at ROE_M, r={r[leg]:.0%}: {g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'})"
              f" / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'})")
    # A18 谷底档 coordinates for the Lanke leg: (i) measured trough→recovery CAGR on the L
    # numerator; (ii) the measured n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2_li"], roe_m, r["lk"])
        g1_lm = (ni["m"]["lk"] / ni["l"]["lk"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2_li"], roe_m, r["lk"])
        print(f"蓝科腿谷底档坐标（A18）{label} n={n}: (i) measured CAGR {g1_meas:.1%} -> {pe_i:.1f}x -> {ni['l']['lk'] * pe_i:.1f} 亿 "
              f"(vs M leg {v['m']['lk']:.1f}: {'overshoot' if ni['l']['lk'] * pe_i > v['m']['lk'] else 'below M'}); "
              f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {ni['l']['lk'] * pe_ii:.1f} 亿 (leg L/M {ni['l']['lk'] * pe_ii / v['m']['lk']:.3f}, collapsed)")
    print(f"蓝科腿谷底 x 1/r = {ni['l']['lk'] / r['lk']:.1f} 亿  (deep_discount pressure coordinate)")
    print(f"flat-multiple @PE_M (蓝科 {pe['m']['lk']:.2f} / 非洲 {pe['m']['afr']:.2f} / 机械 {pe['m']['mac']:.2f}): "
          f"L={flat['l']:.2f} M={flat['m']:.2f} H={flat['h']:.2f} — 带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}（阶梯由蓝科腿轴价承载）")
    pen = {t: anode_penalty(inp, t) for t in TIERS}
    print(f"负极 K_remain 罚项（A20）: {inp['capex_anode']:g} 亿 × {inp['stake_anode']:.2%} × max(0, 1 − ROIC/{r['mac']:.0%}) "
          f"@ROIC {inp['roic_anode_l']:.1%}/{inp['roic_anode_m']:.1%}/{inp['roic_anode_h']:.1%} → "
          + " / ".join(f"{pen[t]:.2f} 亿 ({pen[t] * YI / inp['shares']:.2f} CNY)" for t in TIERS))
    no_pen = [(value(inp, t) + pen[t]) * YI / inp["shares"] for t in TIERS]
    print(f"罚项前（事件前底牌）: {no_pen[0]:.2f} / {no_pen[1]:.2f} / {no_pen[2]:.2f}")
    for label, roics in (("单值 M 档 ROIC", (inp["roic_anode_m"],) * 3), ("2026H1 价格战读数", ANODE_ROIC_STRESS)):
        alt = {**inp, **{f"roic_anode_{t}": x for t, x in zip(TIERS, roics)}}
        band = [anchor(alt, t) for t in TIERS]
        print(f"敏感区 负极 {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%} V_opt/M={v_opt / M:.1%}")
    u = opt_units(inp)
    print(f"V_opt 单位（A22 公开数据推断）: 瓷砖 {u['p_tile']:.2f} 元/㎡ · 玻璃 {u['p_glass']:,.0f} 元/吨 · "
          f"非洲腿归母利润率 {u['margin']:.2%} · PE_afr_H {pe['h']['afr']:.2f}")
    for label, rev, dni, v_ in items:
        print(f"  {label:<22} 收入 {rev:6.2f} 亿 → ΔNI {dni:5.2f} 亿 → {v_:.2f} 元/股")
    a2, b2 = cut_points(*adj)
    print(f"V_opt={v_opt:.2f}  表3 (p {P_TIERS[0]:g}/{P_TIERS[1]:g}/{P_TIERS[2]:g}): "
          f"{adj[0]:.2f} / {adj[1]:.2f} / {adj[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    v_half = sum(x[3] for x in opt_items(inp, pe["h"]["afr"], glass_scale=0.5))
    print(f"敏感 V_opt: 玻璃单价减半 → {v_half:.2f}")
    print(f"分子比（两腿合计 {total['l']:.2f}/{total['m']:.2f}/{total['h']:.2f} 亿）"
          f"L/M={total['l'] / total['m']:.2f} H/M={total['h'] / total['m']:.2f} | "
          f"倍数比 L/M={pe_company['l'] / pe_company['m']:.2f} H/M={pe_company['h'] / pe_company['m']:.2f}")

    # Disclosure rows (never max()'d into the deck).
    print(f"地板（只披露）: BPS {inp['bps']:.2f} CNY {'<' if inp['bps'] < L else '>='} L {L:.2f}; "
          f"锚点隐含 PB {L / inp['bps']:.2f} / {M / inp['bps']:.2f} / {H / inp['bps']:.2f}")
    for label, g_li in (("g2_li +1pp", inp["g2_li"] + 0.01), (f"g2_li 同业反解 {G2_LI_PEER:.2%}", G2_LI_PEER)):
        band = [anchor(inp, t, {**pe[t], "lk": leg_pe(inp, "lk", t, g_override=g_li)}) for t in TIERS]
        print(f"敏感区 {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")
    # Basket-table shift: every r row moves, r_disc (= r_li) included.
    for dr, label in ((-0.005, "−50bp"), (0.005, "+50bp")):
        shifted = {**inp, **{k: inp[k] + dr for k in ("r_li", "r_afr", "r_mac", "r_disc")}}
        band = [anchor(shifted, t) for t in TIERS]
        print(f"敏感区 三腿 r {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")
    for dg, label in ((0.01, "+1pp"), (-0.01, "−1pp")):
        pes = dict(pe["m"]); pes["afr"] = leg_pe(inp, "afr", "m", g_override=inp["g2_afr_m"] + dg)
        print(f"敏感区 g2_afr_m {label}: M={anchor(inp, 'm', pes):.2f}")
    no_axis = [anchor(inp, t, {**pe[t], "afr": leg_pe(inp, "afr", t, g_override=0.0)}) for t in TIERS]
    print(f"非洲腿三档 g=0（不给轴 credit）: {no_axis[0]:.2f} / {no_axis[1]:.2f} / {no_axis[2]:.2f}")

    # What the street and book value each require in r terms: a parallel shift δ
    # of all three baskets that makes the M-tier SOTP equal the target, plus the
    # single-segment g=0 approximation E_M / P.
    eps_m = total["m"] * YI / inp["shares"]
    for label, px in (("卖方 TP", inp["tp_street"]), ("账面 PB=1.0", inp["bps"])):
        delta = implied_r_shift(inp, px)
        print(f"  {label:<10} 隐含公司 PE={px / eps_m:5.2f} → δ={delta:+.2%} "
              f"(蓝科/非洲 {r['lk'] + delta:.1%}, 机械 {r['mac'] + delta:.1%}) | g=0 近似 E_M/P={eps_m / px:.1%}")
    # 属性 D: strip the M-tier Lanke and machinery legs, read the residual on the
    # Africa numerator, invert for the Africa-leg g at its basket r.
    for label, px in (("本框架 M", M), ("卖方 TP", inp["tp_street"]), ("账面 PB=1.0", inp["bps"])):
        # The market cap is net of the anode charge, so the Africa residual adds it back.
        resid = px * inp["shares"] / YI - v["m"]["lk"] - v["m"]["mac"] + anode_penalty(inp, "m")
        p = resid / ni["m"]["afr"]
        gi, ok = implied_g(p, roe_m, r["afr"])
        flag = "" if ok else "  ⚠ 反解只能当方向读"
        print(f"  {label:<10} 扣 M 档蓝科腿 {v['m']['lk']:.1f} + 机械腿 {v['m']['mac']:.1f} 亿后 残差 {resid:6.1f} 亿 → "
              f"隐含 PE非洲={p:6.2f} → g={gi:+.2%}{flag}")
    print(f"  TTM 归母 {inp['ni_ttm']:.2f} 亿"
          f" | FY2024 锂谷底归母 {inp['ni_fy2024']:.2f} 亿 | FY2025 ex-蓝科 {inp['ni_exli_fy2025']:.2f} 亿")
    print(f"  国金 2026E 归母 {inp['ni_2026e_street']:.2f} 亿（锂价按 2026 平台）"
          f" vs 本框架 H 档两腿合计 {total['h']:.2f} 亿 — 仅交叉")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
