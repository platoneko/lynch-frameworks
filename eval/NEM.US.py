#!/usr/bin/env python3
"""NEM.US (Newmont) valuation eval — recompute anchors from frameworks/NEM.US.md.

frameworks/NEM.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: nem_fed_gold_fwd6moz_two_stage_v1

Price axis: the shared Fed-path gold/copper USD ladder (_AXIS.fed-path-gold-copper),
checked cell by cell against the axis file and against the peer mount
601899.SH.  Silver rides the gold ladder; lead/zinc are a frozen sales block.

Forward-capacity numerator (user ruling 2026-09-20/21, A1): FY28 volumes =
2026H1 consolidated ounces sold × (6.0 Moz / 5.26 Moz guidance) for gold and
silver, × (150 kt / 104 kt) for copper — Newmont's "~6 Moz + 150 kt" outlook
(no year attached; treated as 2028) — times an achievement ladder (L = growth
stalls at the 2026 guidance, M = 0.95, H = full).  Volumes are not discounted;
the two years to FY28 are carried by a two-stage multiple.

FY28 P&L same-year: CAS and D&A scale with the gold volume index (US GAAP CAS
excludes D&A, so the two are separate lines, not a double count), reclamation /
exploration / R&D / G&A / other fixed, equity income of affiliates fixed, tax
rate and NCI at 2026H1.

Multiple: per leg `gordon.two_stage_pe(g1, 2, g2, ROE28, r)` with stage-1
payout 1 − g1/ROE28 (library form); ROE28 = NP28 / B27, B27 = 2026-06-30
parent equity + b1 × (2026H2 + FY27 earnings), b1 = g1/ROE28 fixed point.
Metal leg 篮 4 r 10% g2 2.5%; lead/zinc 篮 6 r 13% g2 0.  ROIC gate (A7):
marginal ROIC = (NP28 − NP_cur) ÷ growth capex 2026–28 ≥ r_perp, else the tier
keeps the form with g1 := g2 (metal) / 0 (lead/zinc).

Run:  python3 eval/NEM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_AU_CU, check_au_cu_mount  # noqa: E402
from lib.gordon import check_g_cap, check_r, two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "NEM.US.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
FORMULA_ID = "nem_fed_gold_fwd6moz_two_stage_v1"
MIN_R_MINUS_G = 0.02
TOL = 0.05
DELTA_TOL = 0.0005
TIERS = ("l", "m", "h")
LEGS = {"metal": ("r_perp", "g2_metal"), "pbzn": ("r_pbzn", "g2_pbzn")}
BASKET4_LEGS = {"metal"}
SHARED_LADDER = {"lme_cu_l": "lme_cu_l", "lme_cu_m": "lme_cu_m", "lme_cu_h": "lme_cu_h",
                 "lme_au_l": "lme_au_l", "lme_au_m": "lme_au_m", "lme_au_h": "lme_au_h"}
H1_2026_X2_PARENT = 5464.0 * 2   # $M, six months ended 2026-06-30 × 2 (M guard)
H1_TOL = 0.01

REQUIRED = [
    "price", "shares", "equity", "net_debt",
    "lme_au_l", "lme_au_m", "lme_au_h", "lme_cu_l", "lme_cu_m", "lme_cu_h",
    "realization_au", "realization_cu", "price_ag_m",
    "vol_au_oz", "vol_cu_t", "vol_ag_oz", "sales_pbzn",
    "fwd_au", "fwd_cu", "ach_l_au", "ach_l_cu", "ach_m_au", "ach_m_cu",
    "cas", "da", "opex_fixed", "nonop", "eq_income", "tax_rate", "nci_share",
    "payout_actual", "n_transition", "growth_capex_26_28",
    "k_l", "k_m", "k_h",
    "r_perp", "r_pbzn", "g2_metal", "g2_pbzn", "axis_g2_aucu", "pe_own_min", "pe_own_max",
]
_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%", re.MULTILINE)


def axis_g2(path: Path = AXIS_AU_CU) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError("axis: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def volumes(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    if not forward:
        return {"au": inp["vol_au_oz"], "cu": inp["vol_cu_t"], "ag": inp["vol_ag_oz"]}
    a_au = 1.0 if tag == "h" else inp[f"ach_{tag}_au"]
    a_cu = 1.0 if tag == "h" else inp[f"ach_{tag}_cu"]
    return {"au": inp["vol_au_oz"] * inp["fwd_au"] * a_au, "cu": inp["vol_cu_t"] * inp["fwd_cu"] * a_cu,
            "ag": inp["vol_ag_oz"] * inp["fwd_au"] * a_au}


def year(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    """One tier-year P&L in $M."""
    v = volumes(inp, tag, forward)
    s_au = v["au"] * inp[f"lme_au_{tag}"] * inp["realization_au"] / 1e6
    s_ag = v["ag"] * inp["price_ag_m"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"] / 1e6
    s_cu = v["cu"] * inp[f"lme_cu_{tag}"] * inp["realization_cu"] / 1e6
    sales = s_au + s_ag + s_cu + inp["sales_pbzn"]
    vidx = v["au"] / inp["vol_au_oz"]
    pbt = sales - (inp["cas"] + inp["da"]) * vidx - inp["opex_fixed"] + inp["nonop"]
    parent = (pbt * (1 - inp["tax_rate"]) + inp["eq_income"]) * (1 - inp["nci_share"])
    w6 = inp["sales_pbzn"] / sales
    return {"v": v, "sales": sales, "s_au": s_au, "s_cu": s_cu, "s_ag": s_ag, "parent": parent,
            "eps": parent / inp["shares"], "vidx": vidx, "w_metal": 1 - w6, "w_pbzn": w6}


def tier(inp: dict[str, float], tag: str, r_shift: float = 0.0) -> dict:
    cur, fwd = year(inp, tag, False), year(inp, tag, True)
    lc = {"metal": cur["eps"] * cur["w_metal"], "pbzn": cur["eps"] * cur["w_pbzn"]}
    l28 = {"metal": fwd["eps"] * fwd["w_metal"], "pbzn": fwd["eps"] * fwd["w_pbzn"]}
    n = int(inp["n_transition"])
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["parent"] - cur["parent"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"]
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    g1 = g1_raw if gate else {k: (g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"]
    cum_win = cum_roll + fwd["parent"]
    roe = fwd["parent"] / inp["equity"]
    for _ in range(60):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["parent"] / b27
        if abs(roe_new - roe) < 1e-10:
            break
        roe = roe_new
    r = {k: inp[r_key] + r_shift for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    anchor_pre_k = sum(contrib.values())
    # Retention beyond b1 was treated as distributed at face value; k is the
    # probability-weighted shortfall of reinvesting it below r (valuation-rules
    # 留存去向审计「打折 k」) and only ever subtracts.
    cash_ps = max((1 - inp["payout_actual"]) - b1, 0.0) * cum_win / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash_ps
    anchor = anchor_pre_k - haircut
    return {"cur": cur, "fwd": fwd, "legs_cur": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co, "roic": roic, "gate": gate,
            "b1": b1, "b27": b27, "roe28": roe, "pe": pe, "p1": {k: 1 - g1[k] / roe for k in LEGS}, "contrib": contrib,
            "anchor": anchor, "eq_pe": anchor_pre_k / cur["eps"],
            "cash_ps": cash_ps, "haircut": haircut, "anchor_pre_k": anchor_pre_k,
            "issue": b1 > (1 - inp["payout_actual"])}


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
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    for leg, (r_key, g_key) in LEGS.items():
        if r_key not in baskets:
            errors.append(f"{r_key}: Inputs source cell names no 篮 N")
        errors += check_r(inp[r_key], r_key, baskets.get(r_key))
        errors += check_g_cap(inp[g_key], inp[r_key], g_key)
        if inp[r_key] - inp[g_key] < MIN_R_MINUS_G:
            errors.append(f"{leg}: r − g below pole margin")
    errors += check_g_cap(inp["axis_g2_aucu"], inp["r_perp"], "axis_g2_aucu")
    if abs(inp["axis_g2_aucu"] - axis_g2()) > 1e-9:
        errors.append(f"axis_g2_aucu={inp['axis_g2_aucu']} vs axis 永续 g2 {axis_g2()}")
    if not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]) or not (inp["lme_cu_l"] < inp["lme_cu_m"] < inp["lme_cu_h"]):
        errors.append("price ladder order violated")
    for k in ("au", "cu"):
        if not (0 < inp[f"ach_l_{k}"] <= inp[f"ach_m_{k}"] <= 1.0):
            errors.append(f"achievement ladder {k} violated")
    if not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2 or inp["equity"] <= 0:
        errors.append("payout_actual / n_transition / equity invalid")
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k}")
    if errors:
        return report(errors, "FAIL (guards)")
    errors += check_au_cu_mount((inp["lme_au_l"], inp["lme_au_m"], inp["lme_au_h"]), (inp["lme_cu_l"], inp["lme_cu_m"], inp["lme_cu_h"]))
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer or abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(f"shared ladder drift: {ours} vs 601899.{theirs}")
    if errors:
        return report(errors, "FAIL (shared ladder)")

    T = {t: tier(inp, t) for t in TIERS}
    cur_m = T["m"]["cur"]
    if abs(cur_m["parent"] / H1_2026_X2_PARENT - 1) > H1_TOL:
        errors.append(f"M guard: current run-rate parent {cur_m['parent']:.0f} vs H1×2 {H1_2026_X2_PARENT:.0f}")
    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")
    if errors:
        return report(errors, "FAIL (M guard)")
    for t in TIERS:
        for label, pe in ((f"metal PE_{t.upper()}", T[t]["pe"]["metal"]), (f"equivalent PE_{t.upper()}", T[t]["eq_pe"])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(f"guardrail: {label}={pe:.2f} outside own band — BLOCKED")
        if T[t]["issue"]:
            errors.append(f"{t.upper()}: b1 > actual retention (发股融资)")
        recomb = sum(T[t]["legs_cur"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["metal"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder broken")
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    delta = implied_delta(inp)
    net_cash_ps = -inp["net_debt"] / inp["shares"]
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    for label, want, rx, tol in (("δ", delta * 100, r"δ = \*\*([+-]?[0-9.]+)%\*\*", DELTA_TOL * 100),
                                 ("cash_M", T["m"]["cash_ps"], r"视同派出[^|]*?M 档 \*\*([0-9.]+)\*\*", TOL),
                                 ("haircut_H", T["h"]["haircut"], r"k 后[^|]*?H −\*\*([0-9.]+)\*\*", TOL)):
        got = first_float(rx, out_sec)
        if got is None or abs(got - want) > tol:
            errors.append(f"{label}: stated {got} vs recomputed {want:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print("shared Au/Cu OK vs _AXIS.fed-path-gold-copper (+ peer 601899.SH)")
    print(f"{'档':<3}{'金Moz':>7}{'铜kt':>6}{'ROIC':>7}{'门':>4}{'E_cur':>8}{'E28':>8}{'g1co':>8}{'b1':>6}{'B27$M':>8}{'ROE28':>8}{'PE金':>7}{'合并':>7}{'现金/股':>8}{'锚点':>8}")
    for t in TIERS:
        x = T[t]; v = x["fwd"]["v"]
        print(f"{t.upper():<3}{v['au'] / 1e6:7.2f}{v['cu'] / 1e3:6.0f}{x['roic']:7.0%}{'过' if x['gate'] else '关':>4}{x['cur']['eps']:8.3f}{x['fwd']['eps']:8.3f}"
              f"{x['g1_co']:8.1%}{x['b1']:6.0%}{x['b27']:8.0f}{x['roe28']:8.1%}{x['pe']['metal']:7.2f}{x['eq_pe']:7.2f}{x['cash_ps']:8.2f}{x['anchor']:8.2f}")
    print("baskets: " + ", ".join(f"{r_key} 篮 {baskets[r_key]} r={inp[r_key]:g} g2={inp[g_key]:g}" for r_key, g_key in LEGS.values()))
    for t in TIERS:
        x = T[t]; c = x["cur"]
        print(f"  {t.upper()}: sales {c['sales']:,.0f} (金 {c['s_au'] / c['sales']:.1%} / 银 {c['s_ag'] / c['sales']:.1%} / 铜 {c['s_cu'] / c['sales']:.1%}) | "
              f"g1 metal {x['g1']['metal']:+.1%} pbzn {x['g1']['pbzn']:+.1%} | p1 metal {x['p1']['metal']:.0%} | PE metal {x['pe']['metal']:.2f} pbzn {x['pe']['pbzn']:.2f} | $/股 {x['contrib']['metal']:.2f} + {x['contrib']['pbzn']:.2f}")
    print(f"M guard OK: current run-rate parent {cur_m['parent']:,.0f} $M vs H1×2 {H1_2026_X2_PARENT:,.0f}; net cash/share {net_cash_ps:+.2f} (cross-note)")
    print("视同派出现金/股 k 前 → k 后: " + " | ".join(
        f"{t.upper()} {T[t]['cash_ps']:.2f} × k {inp[f'k_{t}']:g} = −{T[t]['haircut']:.2f} (锚点 {T[t]['anchor_pre_k']:.2f} → {T[t]['anchor']:.2f})"
        for t in TIERS))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ metal PE_M {T['m']['pe']['metal']:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), tuple(T[t]["eq_pe"] for t in TIERS), tuple(T[t]["cur"]["eps"] for t in TIERS)):
        print(line)
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f}")
    print(f"implied r: δ={delta:+.2%} (metal {inp['r_perp'] + delta:.1%})")
    print(f"price={inp['price']} zone={zone}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
