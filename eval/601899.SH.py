#!/usr/bin/env python3
"""601899.SH (Zijin Mining) valuation eval — recompute anchors from frameworks/601899.SH.md.

frameworks/601899.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: zijin_fed_li_dual_axis_fwd2028_two_stage_v1

Two orthogonal price axes (unchanged):
  * Fed rate path → gold / copper USD ladder (_AXIS.fed-path-gold-copper)
  * Lithium supply regime → battery-grade Li2CO3 CNY (_AXIS.lithium-carbonate)

Forward-capacity numerator (user ruling 2026-09-20/21, A1): every tier prices
the 2028 plan volumes × an achievement ladder — L = growth stalls at the 2026
guidance (2026 guide ÷ 2028 plan), M = 2028 plan × the 2026H1 measured
achievement rate, H = plan in full.  Volumes are not discounted; the two years
between the current run-rate and FY28 are carried by a two-stage multiple.

FY28 P&L on the same year: unit costs frozen at 2026H1 (A-share COGS already
carries D&A), volume-linked opex scales with a price-neutral volume index,
finance cost fixed, levy on mine revenue, NCI 24.5% at both ends (A6).

Multiple (A7 / A11): per leg, `gordon.two_stage_pe(g1_leg, n=2, g2, ROE28, r)`
— stage-1 payout is the library form 1 − g1/ROE28 (valuation-rules 两段式过渡,
2026-09-21), g1_leg = two-year CAGR of the leg's EPS from the current run-rate
to FY28, tail g2 = 2.5% (metal, 篮 4) / 0 (lithium, residual, 篮 6).
ROE28 = NP28 / B27 where B27 = 2026H1 parent equity + b1 × (2026H2 + FY27
earnings) and b1 = g1_company / ROE28 (裁决表 ②: numerator-year EPS over
opening BPS; solved as a fixed point).  Anchor = Σ leg EPS_cur × leg PE.

ROIC gate (A29): marginal ROIC = (NP28 − NP_cur) ÷ growth capex 2026–28 must
clear the metal leg's basket r; a failing tier keeps the same two-stage form
with growth switched off (g1 := g2 on 篮 4 legs, 0 on 篮 6 legs).

Disclosure rows: 「模型视同派出、实际留存的现金/股」 = (actual retention − b1)
× window cumulative EPS (a premise of the anchor, never added), today's net
cash per share (cross-note), implied-r δ, alt 篮 5, PB floor.

Run:  python3 eval/601899.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_AU_CU, AXIS_LI2CO3, check_au_cu_mount, check_li2co3_mount  # noqa: E402
from lib.gordon import check_g_cap, check_r, two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, parse_baskets, parse_inputs  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "601899.SH.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "603993.SH.md"
FORMULA_ID = "zijin_fed_li_dual_axis_fwd2028_two_stage_v1"
MIN_R_MINUS_G = 0.02
TOL = 0.05
DELTA_TOL = 0.0005
YI = 1e8
OZ_TO_G = 31.1035
TIERS = ("l", "m", "h")

LEGS = {
    "metal": ("r_perp", "g2_aucu"),
    "li": ("r_li", "g2_li"),
    "rest": ("r_rest", "g2_rest"),
}
BASKET4_LEGS = {"metal"}
ALT_METAL_BASKET_R = 0.11  # 备选篮 5 (country premium), disclosure only

SHARED_LADDER = {
    "lme_cu_l": "p_cu_l", "lme_cu_m": "p_cu_m", "lme_cu_h": "p_cu_h",
    "lme_au_l": "lme_au_l", "lme_au_m": "lme_au_m", "lme_au_h": "lme_au_h",
}

# 1H2026×2 parent at the filing NCI (21.366%) — the M-tier current run-rate,
# restated at the forward NCI, must reproduce this bridge (M guard).
H1_2026_X2_PARENT = 39_169_807_243 * 2
H1_NCI = 0.21366
IDENTITY_TOL = 0.01
M_PRICE_REF = {"p_au": ("price_au_m", 1006.5), "p_cu": ("price_cu_m", 84466.0)}
M_PRICE_TOL = 0.005
LI_REV_H1 = (28.80 + 10.98) * 1e8
LI_GP_H1 = 732.97e8 * 0.034
LI_VOL_H1 = 4.4e4
LI_ASP_H1 = LI_REV_H1 / LI_VOL_H1
LI_COST_H1 = (LI_REV_H1 - LI_GP_H1) / LI_VOL_H1

REQUIRED = [
    "price", "shares", "bps", "fx_usd_cny", "realization_au", "realization_cu",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_g", "cost_au",
    "lme_cu_l", "lme_cu_m", "lme_cu_h", "vol_cu_t", "cost_cu",
    "vol_ag_g", "price_ag_m", "cost_ag",
    "li2co3_l", "li2co3_m", "li2co3_h", "realization_li", "vol_li_t", "cost_li",
    "vol_au_2028_g", "vol_cu_2028_t", "vol_ag_2028_g", "vol_li_2028_t",
    "ach_l_au", "ach_l_cu", "ach_l_ag", "ach_l_li", "ach_m_au", "ach_m_cu", "ach_m_ag", "ach_m_li",
    "gp_rest", "rev_other_mine", "levy_rate", "opex_fixed", "opex_fin", "inv_income",
    "tax_rate", "nci_share", "payout_actual", "n_transition", "growth_capex_26_28", "net_debt",
    "k_l", "k_m", "k_h",
    "equity", "r_perp", "r_li", "r_rest",
    "axis_g2_aucu", "axis_g2_li", "g2_aucu", "g2_li", "g2_rest",
    "pe_own_min", "pe_own_max", "pb_floor",
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


def prices(inp: dict[str, float], tag: str) -> tuple[float, float, float, float]:
    p_au = inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]
    p_cu = inp[f"lme_cu_{tag}"] * inp["fx_usd_cny"] * inp["realization_cu"]
    p_ag = inp["price_ag_m"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    p_li = inp[f"li2co3_{tag}"] * inp["realization_li"]
    return p_au, p_cu, p_ag, p_li


def volumes(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    if not forward:
        return {"au": inp["vol_au_g"], "cu": inp["vol_cu_t"], "ag": inp["vol_ag_g"], "li": inp["vol_li_t"]}
    ach = {k: (inp[f"ach_{tag}_{k}"] if tag != "h" else 1.0) for k in ("au", "cu", "ag", "li")}
    return {
        "au": inp["vol_au_2028_g"] * ach["au"], "cu": inp["vol_cu_2028_t"] * ach["cu"],
        "ag": inp["vol_ag_2028_g"] * ach["ag"], "li": inp["vol_li_2028_t"] * ach["li"],
    }


def mine_rev_at_m(inp: dict[str, float], v: dict[str, float]) -> float:
    """Mine revenue at M-tier prices — the price-neutral volume index base (A28)."""
    p_au, p_cu, _, p_li = prices(inp, "m")
    return v["au"] * p_au + v["cu"] * p_cu + inp["rev_other_mine"] + v["li"] * p_li


def scenario(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    p_au, p_cu, p_ag, p_li = prices(inp, tag)
    v = volumes(inp, tag, forward)
    gp_au = v["au"] * (p_au - inp["cost_au"])
    gp_cu = v["cu"] * (p_cu - inp["cost_cu"])
    gp_ag = v["ag"] * (p_ag - inp["cost_ag"])
    gp_li = v["li"] * (p_li - inp["cost_li"])
    gp = gp_au + gp_cu + gp_ag + inp["gp_rest"] + gp_li
    mine_rev = v["au"] * p_au + v["cu"] * p_cu + inp["rev_other_mine"] + v["li"] * p_li
    vidx = mine_rev_at_m(inp, v) / mine_rev_at_m(inp, volumes(inp, tag, False)) if forward else 1.0
    opex = (inp["opex_fixed"] - inp["opex_fin"]) * vidx + inp["opex_fin"]
    pretax = gp - mine_rev * inp["levy_rate"] - opex + inp["inv_income"]
    parent = pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])
    return {
        "v": v, "p_au": p_au, "p_cu": p_cu, "p_ag": p_ag, "p_li": p_li,
        "gp_au": gp_au, "gp_cu": gp_cu, "gp_ag": gp_ag, "gp_li": gp_li, "gp": gp,
        "vidx": vidx, "parent": parent, "eps": parent / inp["shares"],
        "w_metal": (gp_au + gp_cu + gp_ag) / gp, "w_li": gp_li / gp, "w_rest": inp["gp_rest"] / gp,
    }


def leg_eps(s: dict[str, float]) -> dict[str, float]:
    return {"metal": s["eps"] * s["w_metal"], "li": s["eps"] * s["w_li"], "rest": s["eps"] * s["w_rest"]}


def tier(inp: dict[str, float], tag: str, r_shift: float = 0.0, r_over: dict[str, float] | None = None) -> dict:
    """Forward two-stage tier: g1 per leg, ROIC gate, ROE28 on B27, anchor."""
    cur, fwd = scenario(inp, tag, False), scenario(inp, tag, True)
    lc, l28 = leg_eps(cur), leg_eps(fwd)
    n = int(inp["n_transition"])
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["parent"] - cur["parent"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"]
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    g1 = g1_raw if gate else {k: (g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"]     # 2026H2 + FY27 → B27
    cum_win = cum_roll + fwd["parent"]                                          # window earnings for the cash row
    roe = fwd["parent"] / inp["equity"]
    for _ in range(60):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["parent"] / b27
        if abs(roe_new - roe) < 1e-10:
            break
        roe = roe_new
    r = {k: (r_over or {}).get(r_key, inp[r_key]) + r_shift for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    anchor_pre_k = sum(contrib.values())
    # The stage-1 payout treated the retention beyond b1 as distributed at face
    # value.  k is the probability-weighted shortfall of reinvesting that cash
    # below r (valuation-rules 留存去向审计「打折 k」); it only ever subtracts.
    cash_ps = max((1 - inp["payout_actual"]) - b1, 0.0) * cum_win / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash_ps
    anchor = anchor_pre_k - haircut
    return {
        "cur": cur, "fwd": fwd, "legs_cur": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co,
        "roic": roic, "gate": gate, "b1": b1, "b27": b27, "roe28": roe, "pe": pe,
        "p1": {k: 1 - g1[k] / roe for k in LEGS}, "contrib": contrib, "anchor": anchor,
        "eq_pe": anchor_pre_k / cur["eps"],
        "cash_ps": cash_ps, "haircut": haircut, "anchor_pre_k": anchor_pre_k,
        "issue": b1 > (1 - inp["payout_actual"]),
    }


def implied_delta(inp: dict[str, float]) -> float:
    lo, hi = -0.08, 0.15
    for _ in range(100):
        mid = (lo + hi) / 2
        if tier(inp, "m", r_shift=mid)["anchor"] > inp["price"]:
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
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1
    baskets = parse_baskets(md)

    errors: list[str] = []
    for metal, keys in (("gold", ("lme_au_l", "lme_au_m", "lme_au_h")), ("copper", ("lme_cu_l", "lme_cu_m", "lme_cu_h")),
                        ("li2co3", ("li2co3_l", "li2co3_m", "li2co3_h"))):
        lo, mid, hi = (inp[k] for k in keys)
        if not (lo < mid < hi):
            errors.append(f"{metal} ladder violated: {lo}/{mid}/{hi}")
    for k in ("au", "cu", "ag", "li"):
        if not (0 < inp[f"ach_l_{k}"] <= inp[f"ach_m_{k}"] <= 1.0):
            errors.append(f"achievement ladder {k}: L {inp[f'ach_l_{k}']} ≤ M {inp[f'ach_m_{k}']} ≤ H 1 violated")
    for leg, (r_key, g_key) in LEGS.items():
        if r_key not in baskets:
            errors.append(f"{r_key}: no 篮 N in its Inputs source cell (A26)")
        errors += check_r(inp[r_key], r_key, baskets.get(r_key))
        errors += check_g_cap(inp[g_key], inp[r_key], g_key)
        if inp[r_key] - inp[g_key] < MIN_R_MINUS_G:
            errors.append(f"{leg}: r − g < {MIN_R_MINUS_G} (pole)")
    errors += check_g_cap(inp["axis_g2_aucu"], inp["r_perp"], "axis_g2_aucu")
    errors += check_g_cap(inp["axis_g2_li"], inp["r_li"], "axis_g2_li")
    for k, path in (("axis_g2_aucu", AXIS_AU_CU), ("axis_g2_li", AXIS_LI2CO3)):
        if abs(inp[k] - axis_g2(path)) > 1e-9:
            errors.append(f"{k}={inp[k]} vs {path.name} 永续 g2 {axis_g2(path)}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")
    if abs(inp["cost_li"] - LI_COST_H1) / LI_COST_H1 > 0.01:
        errors.append(f"cost_li {inp['cost_li']:.2f} vs H1-implied {LI_COST_H1:.2f}")
    if not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2:
        errors.append("payout_actual ∉ (0,1) or n_transition ≠ 2")
    # cyclical: the top-of-cycle tier's cash is the most likely to be spent on
    # expensive deals, so k must not fall as the tier rises.
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    errors += check_au_cu_mount((inp["lme_au_l"], inp["lme_au_m"], inp["lme_au_h"]),
                                (inp["lme_cu_l"], inp["lme_cu_m"], inp["lme_cu_h"]))
    errors += check_li2co3_mount((inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"]))
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors.append(f"peer 603993.SH missing {theirs}")
        elif abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(f"shared ladder drift: {ours}={inp[ours]} vs 603993.{theirs}={peer[theirs]}")
    if errors:
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

    T = {t: tier(inp, t) for t in TIERS}
    cur_m = T["m"]["cur"]
    if cur_m["p_au"] <= inp["cost_au"] or T["l"]["cur"]["p_cu"] <= inp["cost_cu"] or T["l"]["cur"]["p_li"] <= inp["cost_li"]:
        errors.append("unit cost exceeds L-scenario price")
    for key, (label, ref) in M_PRICE_REF.items():
        if abs(cur_m[key] / ref - 1.0) > M_PRICE_TOL:
            errors.append(f"{label} derived {cur_m[key]:.2f} vs filing-implied {ref}")
    li_m_ref = LI_ASP_H1 * inp["li2co3_m"] / 150_000
    if abs(cur_m["p_li"] / li_m_ref - 1.0) > M_PRICE_TOL:
        errors.append(f"price_li_m derived {cur_m['p_li']:.2f} vs H1 ASP × M/150k {li_m_ref:.2f}")
    # M guard: the current run-rate at the filing NCI = H1×2 − old-li + li at axis M.
    def li_parent(asp: float, vol: float) -> float:
        pbt = (asp - inp["cost_li"]) * vol - inp["levy_rate"] * asp * vol
        return pbt * (1.0 - inp["tax_rate"]) * (1.0 - H1_NCI)
    expected = H1_2026_X2_PARENT - li_parent(LI_ASP_H1, LI_VOL_H1 * 2) + li_parent(cur_m["p_li"], inp["vol_li_t"])
    got = cur_m["parent"] * (1 - H1_NCI) / (1 - inp["nci_share"])
    if abs(got / expected - 1.0) > IDENTITY_TOL:
        errors.append(f"M guard: current run-rate parent (filing NCI) {got / YI:.1f}亿 vs expected {expected / YI:.1f}亿")
    if errors:
        print("FAIL (M guard):", "; ".join(errors), file=sys.stderr)
        return 1

    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    for t in TIERS:
        for label, pe in ((f"metal PE_{t.upper()}", T[t]["pe"]["metal"]), (f"equivalent PE_{t.upper()}", T[t]["eq_pe"])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(f"guardrail: {label}={pe:.2f} outside own band — BLOCKED, do not twist g")
        if T[t]["issue"]:
            errors.append(f"{t.upper()}: b1 {T[t]['b1']:.2%} > actual retention {1 - inp['payout_actual']:.0%} (发股融资)")
        # recombination: Σ leg EPS_cur × (1+g1_raw)^n must reproduce E28
        recomb = sum(T[t]["legs_cur"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off by {recomb / T[t]['fwd']['eps'] - 1:+.2%}")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["metal"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    floor = inp["pb_floor"] * inp["bps"]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    delta = implied_delta(inp)
    alt = [tier(inp, t, r_over={"r_perp": ALT_METAL_BASKET_R})["anchor"] for t in TIERS]
    net_cash_ps = -inp["net_debt"] / inp["shares"]

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    for label, want, rx, tol in (
        ("floor", floor, r"`floor` = \*\*([0-9.]+)\*\*", TOL),
        ("δ", delta * 100, r"δ = \*\*([+-]?[0-9.]+)%\*\*", DELTA_TOL * 100),
        ("cash_M", T["m"]["cash_ps"], r"视同派出[^|]*?M 档 \*\*([0-9.]+)\*\*", TOL),
        ("haircut_M", T["m"]["haircut"], r"k 后[^|]*?M 档 −\*\*([0-9.]+)\*\*", TOL),
    ):
        got = first_float(rx, out_sec)
        if got is None or abs(got - want) > tol:
            errors.append(f"{label}: stated {got} vs recomputed {want:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print("shared Au/Cu OK vs _AXIS.fed-path-gold-copper (+ peer 603993.SH); Li2CO3 OK vs _AXIS.lithium-carbonate")
    print(f"{'档':<3}{'金t':>7}{'铜kt':>7}{'锂kt':>7}{'ROIC':>7}{'门':>4}{'E_cur':>8}{'E28':>8}{'g1co':>8}{'b1':>6}{'B27亿':>8}{'ROE28':>8}{'PE金':>7}{'合并':>7}{'现金/股':>8}{'锚点':>8}")
    for t in TIERS:
        x = T[t]; v = x["fwd"]["v"]
        print(f"{t.upper():<3}{v['au'] / 1e6:7.1f}{v['cu'] / 1e3:7.0f}{v['li'] / 1e3:7.0f}{x['roic']:7.0%}{'过' if x['gate'] else '关':>4}"
              f"{x['cur']['eps']:8.3f}{x['fwd']['eps']:8.3f}{x['g1_co']:8.1%}{x['b1']:6.0%}{x['b27'] / YI:8.0f}{x['roe28']:8.1%}"
              f"{x['pe']['metal']:7.2f}{x['eq_pe']:7.2f}{x['cash_ps']:8.2f}{x['anchor']:8.2f}")
    print("baskets: " + ", ".join(f"{r_key} 篮 {baskets[r_key]} r={inp[r_key]:g} g2={inp[g_key]:g}" for r_key, g_key in LEGS.values())
          + f"; axis rows {inp['axis_g2_aucu']:g} / {inp['axis_g2_li']:g} referenced, not adopted")
    for t in TIERS:
        x = T[t]
        print(f"  {t.upper()}: g1 metal {x['g1']['metal']:+.1%} / li {x['g1']['li']:+.1%} / rest {x['g1']['rest']:+.1%}"
              f" | p1 metal {x['p1']['metal']:.0%} | PE metal {x['pe']['metal']:.2f} li {x['pe']['li']:.2f} rest {x['pe']['rest']:.2f}"
              f" | $/股 {x['contrib']['metal']:.2f} + {x['contrib']['li']:.2f} + {x['contrib']['rest']:.2f}")
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × BPS; disclosure only); net cash/share {net_cash_ps:+.2f} (cross-note, not in anchor)")
    print("视同派出现金/股 k 前 → k 后: " + " | ".join(
        f"{t.upper()} {T[t]['cash_ps']:.2f} × k {inp[f'k_{t}']:g} = −{T[t]['haircut']:.2f} (锚点 {T[t]['anchor_pre_k']:.2f} → {T[t]['anchor']:.2f})"
        for t in TIERS))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ metal PE_M {T['m']['pe']['metal']:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), tuple(T[t]["eq_pe"] for t in TIERS), tuple(T[t]["cur"]["eps"] for t in TIERS)):
        print(line)
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f}")
    print(f"implied r: δ={delta:+.2%} (metal {inp['r_perp'] + delta:.1%} / li·rest {inp['r_li'] + delta:.1%}); "
          f"alt 篮 5 metal r {ALT_METAL_BASKET_R:g} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f} zone {zone_of(inp['price'], *alt)}")
    print(f"price={inp['price']} zone={zone}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
