#!/usr/bin/env python3
"""603993.SH (CMOC) valuation eval — recompute anchors from frameworks/603993.SH.md.

frameworks/603993.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on any mismatch.  The doc
states no current price or zone (the digest and the app zone on live quotes).

formula_id: cmoc_fed_path_fwd2028_two_stage_v2

Scenario axis is the Fed rate path (L hiking / M hold / H cutting without
recession, A19); the recession-cut case is deliberately NOT an anchor.

Forward-capacity numerator (user ruling 2026-09-20/21, A4 / A9): copper FY28 =
2026 guidance mid + KFM Phase 2 (+100 kt/yr from 2027), gold FY28 = the 2029
">20 t" target interpolated to 2028, each × an achievement ladder (L = growth
stalls at the 2026 guidance / current gold run-rate, M = plan × measured
achievement, H = full).  Cobalt stays the quota leg (given per tier, no volume
growth); Mo-W-Nb-P, IXM and eliminations stay frozen.  Copper is priced as
volume × (unit revenue − unit COGS) rather than the old price-delta shift so
volume can move; at the base volumes the two are identical (M guard below).

FY28 P&L same-year: unit costs frozen at 2026H1 (A-share COGS carries D&A),
volume-linked opex (销售+管理+研发) scaled by a price-neutral volume index,
finance / levy base fixed, incremental DRC royalty 3.5% on incremental copper
revenue, NCI 12.46% on the base and 28.75% on the KFM increment (A6).

Multiple: per leg `gordon.two_stage_pe(g1_leg, 2, g2, ROE28, r)` — stage-1
payout 1 − g1/ROE28 (library form), ROE28 = NP28 / B27 with B27 = 2026H1
equity + b1 × (2026H2 + FY27 earnings), b1 = g1/ROE28 solved jointly.  Tail:
copper+gold 篮 4 g2 2.5%; cobalt / Mo-W-Nb-P 篮 6 and IXM 篮 5 at 1/r.
ROIC gate (A28): marginal ROIC ≥ r_perp or the tier keeps the same form with
growth switched off (g1 := g2 on 篮 4, 0 elsewhere).

Run:  python3 frameworks/eval/603993.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_AU_CU, check_au_cu_mount  # noqa: E402
from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "603993.SH.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "601899.SH.md"
FORMULA_ID = "cmoc_fed_path_fwd2028_two_stage_v2"
MIN_R_MINUS_G = 0.02
TOL = 0.05
YI = 1e8
TIERS = ("l", "m", "h")

LEGS = {"铜金": ("r_perp", "g2_aucu"), "钴": ("r_co", "g2_co"), "钼钨铌磷": ("r_other", "g2_other"), "IXM": ("r_ixm", "g2_ixm")}
BASKET4_LEGS = {"铜金"}
SHARED_LADDER = {"p_cu_l": "lme_cu_l", "p_cu_m": "lme_cu_m", "p_cu_h": "lme_cu_h",
                 "lme_au_l": "lme_au_l", "lme_au_m": "lme_au_m", "lme_au_h": "lme_au_h"}
BASE_NP_PARENT_YI = 323.0437
BASE_NP_TOL_YI = 0.5

REQUIRED = [
    "vol_au_2029_oz", "t_num", "t_opt",
    "shares", "fx_usd_cny", "vol_cu", "p_cu_base", "p_cu_l", "p_cu_m", "p_cu_h",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_oz", "cost_au_oz", "price_au_m_oz",
    "realization_cu", "royalty_cu", "cogs_cu", "gp_cu_base", "gp_co_l", "gp_co_m", "gp_co_h",
    "gp_other", "gp_ixm", "gp_misc", "opex", "opex_vol", "tax_rate", "mi_rate", "mi_kfm",
    "vol_cu_2028", "vol_au_2028_oz", "ach_l_cu", "ach_l_au", "ach_m_cu", "ach_m_au",
    "payout_actual", "n_transition", "growth_capex_26_28", "capex_kfm2", "net_debt",
    "k_l", "k_m", "k_h",
    "equity", "r_perp", "r_co", "r_other", "r_ixm", "g2_aucu", "g2_co", "g2_other", "g2_ixm",
    "axis_g2_aucu", "pe_own_min", "pe_own_max",
]
_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%\*\*", re.MULTILINE)


def axis_g2(path=AXIS_AU_CU) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def unit_rev_cu(inp: dict[str, float], tag: str) -> float:
    return inp[f"p_cu_{tag}"] * inp["realization_cu"] * inp["fx_usd_cny"]


def year(inp: dict[str, float], tag: str, v_cu: float, v_au: float, forward: bool) -> dict[str, float]:
    """One tier-year P&L (亿 CNY).  forward=False is the audited-base run-rate."""
    gp_cu = v_cu * (unit_rev_cu(inp, tag) - inp["cogs_cu"]) / YI
    p_au = inp["price_au_m_oz"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    gp_au = v_au * (p_au - inp["cost_au_oz"]) / YI
    gp_co = inp[f"gp_co_{tag}"]
    gp = gp_cu + gp_au + gp_co + inp["gp_other"] + inp["gp_ixm"] + inp["gp_misc"]
    # base royalty sits inside opex; the framework applies (1 − royalty) to the price move only (A13)
    roy_price = inp["royalty_cu"] * inp["vol_cu"] * (unit_rev_cu(inp, tag) - unit_rev_cu(inp, "m")) / YI
    if forward:
        base_rev = inp["vol_cu"] * unit_rev_cu(inp, "m") + inp["vol_au_oz"] * inp["price_au_m_oz"]
        vidx = (v_cu * unit_rev_cu(inp, "m") + v_au * inp["price_au_m_oz"]) / base_rev
        roy_vol = inp["royalty_cu"] * (v_cu - inp["vol_cu"]) * unit_rev_cu(inp, tag) / YI
        opex = (inp["opex"] - inp["opex_vol"]) + inp["opex_vol"] * vidx + roy_price + roy_vol
        pretax_kfm = max((v_cu - inp["vol_cu"]) * (unit_rev_cu(inp, tag) * (1 - inp["royalty_cu"]) - inp["cogs_cu"]) / YI, 0.0)
    else:
        vidx, opex, pretax_kfm = 1.0, inp["opex"] + roy_price, 0.0
    pretax = gp - opex
    np_ = ((pretax - pretax_kfm) * (1 - inp["mi_rate"]) + pretax_kfm * (1 - inp["mi_kfm"])) * (1 - inp["tax_rate"])
    legs = {"铜金": gp_cu + gp_au, "钴": gp_co, "钼钨铌磷": inp["gp_other"] + inp["gp_misc"], "IXM": inp["gp_ixm"]}
    return {"np": np_, "eps": np_ * YI / inp["shares"], "gp": gp, "gp_cu": gp_cu, "gp_au": gp_au, "p_au": p_au,
            "pretax": pretax, "vidx": vidx, "w": {k: legs[k] / gp for k in legs}}


def tier(inp: dict[str, float], tag: str, r_over: dict[str, float] | None = None) -> dict:
    ach = {"cu": 1.0, "au": 1.0} if tag == "h" else {"cu": inp[f"ach_{tag}_cu"], "au": inp[f"ach_{tag}_au"]}
    v_cu, v_au = inp["vol_cu_2028"] * ach["cu"], inp["vol_au_2028_oz"] * ach["au"]
    cur, fwd = year(inp, tag, inp["vol_cu"], inp["vol_au_oz"], False), year(inp, tag, v_cu, v_au, True)
    lc = {k: cur["eps"] * cur["w"][k] for k in LEGS}
    l28 = {k: fwd["eps"] * fwd["w"][k] for k in LEGS}
    n = int(inp["n_transition"])
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["np"] - cur["np"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"]
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    g1 = g1_raw if gate else {k: (g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"] / YI
    cum_win = cum_roll + fwd["np"]
    roe = fwd["np"] / inp["equity"]
    for _ in range(60):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["np"] / b27
        if abs(roe_new - roe) < 1e-10:
            break
        roe = roe_new
    r = {k: (r_over or {}).get(r_key, inp[r_key]) for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    anchor_pre_k = sum(contrib.values())
    # Retention beyond b1 was treated as distributed at face value; k is the
    # probability-weighted shortfall of reinvesting it below r (valuation-rules
    # 留存去向审计「打折 k」) and only ever subtracts.
    cash_ps = max((1 - inp["payout_actual"]) - b1, 0.0) * cum_win * YI / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash_ps
    anchor = anchor_pre_k - haircut
    return {"cur": cur, "fwd": fwd, "v_cu": v_cu, "v_au": v_au, "legs_cur": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co,
            "roic": roic, "gate": gate, "b1": b1, "b27": b27, "roe28": roe, "pe": pe, "p1": {k: 1 - g1[k] / roe for k in LEGS},
            "contrib": contrib, "anchor": anchor, "eq_pe": anchor_pre_k / cur["eps"],
            "cash_ps": cash_ps, "haircut": haircut, "anchor_pre_k": anchor_pre_k,
            "issue": b1 > (1 - inp["payout_actual"])}


# 表3 only — never Inputs, never the base band (A2e-7a).  p_M: no anchor (judgement).
P_K = (0.0, 0.25, 1.0)


def gold_target_option(inp: dict[str, float], th: dict) -> dict[str, float]:
    """V_opt — the part of the company's named 2029 gold target (>20 t) beyond the
    FY28 path already in the numerator (A33, valuation-rules「未建模期权」2026-10-03).
    Unit economics: this ticker's own gold leg at the M rung (2026H1 unit price
    and cost), own NCI and tax; ruler: own copper-gold leg steady-state Gordon at
    the H-tier ROE28 lifted by the increment; valued in 2029, discounted to the
    numerator year at the basket r.  No peer multiple."""
    d_oz = inp["vol_au_2029_oz"] - inp["vol_au_2028_oz"]
    d_np = d_oz * (inp["price_au_m_oz"] - inp["cost_au_oz"]) / YI * (1 - inp["mi_rate"]) * (1 - inp["tax_rate"])
    d_eps = d_np * YI / inp["shares"]
    roe_post = (th["fwd"]["np"] + d_np) / th["b27"]
    pe_post = perpetual_pe(inp["g2_aucu"], roe_post, inp["r_perp"])
    disc = (1 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    return {"d_oz": d_oz, "d_np": d_np, "d_eps": d_eps, "roe_post": roe_post, "pe_post": pe_post,
            "disc": disc, "v_opt": d_eps * pe_post * disc}


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    r = {leg: inp[rrow] for leg, (rrow, _) in LEGS.items()}
    g = {leg: inp[grow] for leg, (_, grow) in LEGS.items()}
    baskets = parse_baskets(md)
    for leg, (rrow, _) in LEGS.items():
        if rrow not in baskets:
            errors.append(f"{rrow}: Inputs source cell names no 篮 N")
        errors += check_r(r[leg], rrow, baskets.get(rrow))
    if errors:
        return report(errors, "FAIL (baskets)")
    if not (inp["p_cu_l"] < inp["p_cu_m"] < inp["p_cu_h"]) or not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]):
        errors.append("price ladder order violated")
    if not (inp["gp_co_l"] < inp["gp_co_m"] < inp["gp_co_h"]):
        errors.append("cobalt leg order violated")
    if inp["price_au_m_oz"] <= inp["cost_au_oz"]:
        errors.append("gold unit cost exceeds M price")
    for k in ("cu", "au"):
        if not (0 < inp[f"ach_l_{k}"] <= inp[f"ach_m_{k}"] <= 1.0):
            errors.append(f"achievement ladder {k} violated")
    for leg, (_, grow) in LEGS.items():
        errors += check_g_cap(g[leg], r[leg], grow)
        if g[leg] < 0:
            errors.append(f"{grow} < 0")
    errors += check_g_cap(inp["axis_g2_aucu"], r["铜金"], "axis_g2_aucu")
    if r["铜金"] - g["铜金"] < MIN_R_MINUS_G:
        errors.append("r_perp − g2_aucu below pole margin")
    if abs(inp["axis_g2_aucu"] - axis_g2()) > 1e-9:
        errors.append(f"axis_g2_aucu={inp['axis_g2_aucu']} vs axis 永续 g2 {axis_g2()}")
    if inp["equity"] <= 0 or not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2:
        errors.append("equity / payout_actual / n_transition invalid")
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    if abs(inp["p_cu_m"] - inp["p_cu_base"]) > 1e-6:
        errors.append("p_cu_m must equal p_cu_base (M = audited base)")
    for k in inp:
        if k.startswith("p_") and k not in ("p_cu_base", "p_cu_l", "p_cu_m", "p_cu_h"):
            errors.append(f"probability-style input {k}")
    if errors:
        return report(errors, "FAIL (guards)")
    errors += check_au_cu_mount((inp["lme_au_l"], inp["lme_au_m"], inp["lme_au_h"]), (inp["p_cu_l"], inp["p_cu_m"], inp["p_cu_h"]))
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer or abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(f"shared ladder drift: {ours} vs 601899.{theirs}")
    if errors:
        return report(errors, "FAIL (shared ladder)")

    T = {t: tier(inp, t) for t in TIERS}
    # M guard: base-volume M run-rate reproduces the audited interim ×2, and the
    # volume × (unit revenue − unit COGS) copper leg reproduces gp_cu_base.
    base_m = T["m"]["cur"]
    if abs(base_m["np"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(f"M base parent {base_m['np']:.4f}亿 vs audited {BASE_NP_PARENT_YI}")
    if abs(base_m["gp_cu"] - inp["gp_cu_base"]) > 0.5:
        errors.append(f"copper leg at base {base_m['gp_cu']:.2f} vs gp_cu_base {inp['gp_cu_base']}")
    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")
    if errors:
        return report(errors, "FAIL (M guard)")
    for t in TIERS:
        for label, pe in ((f"铜金 PE_{t.upper()}", T[t]["pe"]["铜金"]), (f"equivalent PE_{t.upper()}", T[t]["eq_pe"])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(f"guardrail: {label}={pe:.2f} outside own band — BLOCKED")
        if T[t]["issue"]:
            errors.append(f"{t.upper()}: b1 > actual retention (发股融资)")
        recomb = sum(T[t]["legs_cur"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["铜金"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder broken")
    A, B = (L + M) / 2, (M + H) / 2
    alt = [tier(inp, t, r_over={"r_perp": 0.11})["anchor"] for t in TIERS]
    kfm2_ret = {t: max((100_000 * (unit_rev_cu(inp, t) * (1 - inp["royalty_cu"]) - inp["cogs_cu"]) / YI) * (1 - inp["tax_rate"]), 0) / inp["capex_kfm2"] for t in TIERS}
    net_cash_ps = -inp["net_debt"] / inp["shares"]
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    for label, want, rx, tol in (("cash_M", T["m"]["cash_ps"], r"视同派出[^|]*?M 档 \*\*([0-9.]+)\*\*", TOL),
                                 ("haircut_H", T["h"]["haircut"], r"k 后[^|]*?H −\*\*([0-9.]+)\*\*", TOL)):
        got = first_float(rx, out_sec)
        if got is None or abs(got - want) > tol:
            errors.append(f"{label}: stated {got} vs recomputed {want:.4f}")
    opt = gold_target_option(inp, T["h"])
    if opt["d_oz"] <= 0 or inp["t_opt"] < inp["t_num"]:
        errors.append("gold option: target must exceed the FY28 path and t_opt ≥ t_num")
    band3 = tuple(base + P_K[i] * opt["v_opt"] for i, base in enumerate((L, M, H)))
    got = first_float(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if got is None or abs(got - opt["v_opt"]) > TOL:
        errors.append(f"V_opt: stated {got} vs recomputed {opt['v_opt']:.4f}")
    for k, v in zip("LMH", band3):
        m3 = re.search(rf"^\| {k} \| [0-9.]+ \| [^|]+\| [^|]+\| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - v) > TOL:
            errors.append(f"table3 {k}: stated {m3.group(1) if m3 else None} vs recomputed {v:.4f}")
    for label, want, rx in (("A′", (band3[0] + band3[1]) / 2, r"A′ = \*\*([0-9.]+)\*\*"),
                            ("B′", (band3[1] + band3[2]) / 2, r"B′ = \*\*([0-9.]+)\*\*")):
        got = first_float(rx, out_sec)
        if got is None or abs(got - want) > TOL:
            errors.append(f"{label}: stated {got} vs recomputed {want:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print("shared Au/Cu OK vs _AXIS.fed-path-gold-copper (+ peer 601899.SH)")
    print(f"{'档':<3}{'铜kt':>7}{'金koz':>7}{'ROIC':>7}{'门':>4}{'E_cur':>8}{'E28':>8}{'g1co':>8}{'b1':>6}{'B27亿':>8}{'ROE28':>8}{'PE铜金':>8}{'合并':>7}{'现金/股':>8}{'锚点':>8}")
    for t in TIERS:
        x = T[t]
        print(f"{t.upper():<3}{x['v_cu'] / 1e3:7.0f}{x['v_au'] / 1e3:7.0f}{x['roic']:7.0%}{'过' if x['gate'] else '关':>4}{x['cur']['eps']:8.3f}{x['fwd']['eps']:8.3f}"
              f"{x['g1_co']:8.1%}{x['b1']:6.0%}{x['b27']:8.0f}{x['roe28']:8.1%}{x['pe']['铜金']:8.2f}{x['eq_pe']:7.2f}{x['cash_ps']:8.2f}{x['anchor']:8.2f}")
    print("baskets: " + ", ".join(f"{rrow} 篮 {baskets[rrow]} r={inp[rrow]:g} g2={inp[grow]:g}" for rrow, grow in LEGS.values()))
    for t in TIERS:
        x = T[t]
        print(f"  {t.upper()}: g1 " + " / ".join(f"{k} {x['g1'][k]:+.1%}" for k in LEGS) + f" | p1 铜金 {x['p1']['铜金']:.0%} | PE "
              + " ".join(f"{k} {x['pe'][k]:.2f}" for k in LEGS) + " | $/股 " + " + ".join(f"{x['contrib'][k]:.2f}" for k in LEGS)
              + f" | KFM2 项目回报 {kfm2_ret[t]:.0%}")
    print(f"M guard OK: base parent {base_m['np']:.4f}亿 = audited {BASE_NP_PARENT_YI}; net cash/share {net_cash_ps:+.2f} (cross-note)")
    print("视同派出现金/股 k 前 → k 后: " + " | ".join(
        f"{t.upper()} {T[t]['cash_ps']:.2f} × k {inp[f'k_{t}']:g} = −{T[t]['haircut']:.2f} (锚点 {T[t]['anchor_pre_k']:.2f} → {T[t]['anchor']:.2f})"
        for t in TIERS))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"V_opt 金 2029 目标（A33）：{inp['vol_au_2029_oz']:,.0f} − FY28 路径 {inp['vol_au_2028_oz']:,.0f} = {opt['d_oz']:,.0f} oz × "
          f"({inp['price_au_m_oz']:,.0f} − {inp['cost_au_oz']:,.0f}) 元/oz × (1−MI)(1−t) = {opt['d_np']:.2f} 亿（ΔEPS {opt['d_eps']:.4f}）"
          f" × PE {opt['pe_post']:.2f}（g2 {inp['g2_aucu']:g}, ROE {opt['roe_post']:.1%}, r {inp['r_perp']:g}） × {opt['disc']:.4f}"
          f"（{inp['t_opt']:g}→{inp['t_num']:g}）= {opt['v_opt']:.2f}；V_opt/M {opt['v_opt'] / M:.1%}")
    print(f"表3 p_k={P_K[0]:g}/{P_K[1]:g}/{P_K[2]:g} → {band3[0]:.2f}/{band3[1]:.2f}/{band3[2]:.2f}  "
          f"A′={(band3[0] + band3[1]) / 2:.2f} B′={(band3[1] + band3[2]) / 2:.2f}")
    print(f"flat-multiple ladder @ 铜金 PE_M {T['m']['pe']['铜金']:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), tuple(T[t]["eq_pe"] for t in TIERS), tuple(T[t]["cur"]["eps"] for t in TIERS)):
        print(line)
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f}")
    print(f"alt 篮 5 铜金 11% -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
