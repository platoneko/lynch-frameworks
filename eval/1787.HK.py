#!/usr/bin/env python3
"""1787.HK (山东黄金 H) valuation eval — recompute anchors from frameworks/1787.HK.md.

frameworks/1787.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).

formula_id: sdg_fed_gold_fwd53t_two_stage_v1

Price axis: the shared Fed-path gold USD ladder (_AXIS.fed-path-gold-copper),
gold rungs only, checked cell by cell against the axis file and against the
peer mount 601899.SH.  Silver and other by-products ride the gold ladder; the
lead/zinc/copper/iron plus bought-in gold / bar / trading block is frozen.

Numerator (A1): current = 2026H1 run-rate (own gold sold × 2, P&L lines × 2,
Donghai Securities fair-value loss stripped).  FY28 volume = target 53.39 t
(2025 own gold sold 48.39 t + Twin Hills 5 t, the Shanjin project due 2027H1)
× an achievement ladder: L = stalls at the 2026 guidance 37 t, M = mean 2024–26
guidance attainment 0.905, H = full.  Unit cost (incl. D&A) scales with volume;
period costs, interest and the perpetual coupon are fixed.

Non-controlling interests (A4): Shanjin International (28.89%, consolidated)
keeps 74.1% of its own profit away from the parent; its profit moves with the
gold price on its own mining revenue and takes all of Twin Hills.  The rest of
the group pays 8.73% to minorities.

Multiple: per leg `gordon.two_stage_pe(g1, 2, g2, ROE28, r)`; gold leg 篮 4
r 10% g2 2.5% (same basket as 601899.SH's gold leg), rest block 篮 6 r 13%
g2 0.  ROE28 = FY28 common profit / B27 (common equity excl. perpetuals +
b1 × 2026H2–FY27 earnings).  ROIC gate: (FY28 − current common profit) ÷
2026–28 growth capex ≥ r_perp, else growth credit is withheld (g1 := min(raw, g2)).
Anchors are computed in CNY and quoted in HKD.

Run:  python3 frameworks/eval/1787.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_AU_CU, load_au_cu_rungs  # noqa: E402
from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402

sys.path.insert(1, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "1787.HK.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "601899.SH.md"
FORMULA_ID = "sdg_fed_gold_fwd53t_two_stage_v1"
OZ_TO_G = 31.1035
MIN_R_MINUS_G = 0.02
TOL = 0.05
TIERS = ("l", "m", "h")
LEGS = {"au": ("r_perp", "g2_au"), "rest": ("r_rest", "g2_rest")}
BASKET4_LEGS = {"au"}
H1_2026_X2_COMMON = 76.51   # 亿元: (6,260.76 − 2,188.90 − 246.38) 百万 × 2, Donghai stripped (M guard)
H1_TOL = 0.01
LISTING_CCY = "HKD"
# 表3 only — never Inputs, never the base band (construction §7a).  p_M: no production year, no anchor.
P_K = (0.0, 0.25, 1.0)

REQUIRED = [
    "shares", "equity", "net_debt", "perp_principal", "fx_usd_cny", "fx_hkd_cny",
    "lme_au_l", "lme_au_m", "lme_au_h", "realization_au",
    "vol_cur_t", "unit_cost", "gp_ag", "gp_rest", "rev_byp",
    "surch", "opex_fixed", "fin_cost", "nonop", "tax_rate",
    "np_sj", "rev_sj", "nci_sj", "nci_oth", "perp_coupon",
    "vol_target_t", "vol_l_t", "ach_m", "th_t",
    "growth_capex_26_28", "payout_actual", "n_transition", "k_l", "k_m", "k_h",
    "r_perp", "r_rest", "g2_au", "g2_rest", "axis_g2_aucu", "pe_own_min", "pe_own_max",
    "jj_cap_t", "jj_now_t", "xc_cap_t", "xc_now_t",
    "jj_budget", "jj_spent", "xc_budget", "xc_spent", "t_num", "t_opt", "t_build0",
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


def price(inp: dict[str, float], tag: str) -> float:
    """Realised gold 元/克 at the tier rung."""
    return inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]


def year(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    """One tier-year P&L in 亿元 (volumes in tonnes; 1 t × 1 元/克 = 0.01 亿)."""
    p = price(inp, tag)
    k = p / price(inp, "m")
    if forward:
        vol = inp["vol_l_t"] if tag == "l" else inp["vol_target_t"] * (inp["ach_m"] if tag == "m" else 1.0)
        th = 0.0 if tag == "l" else inp["th_t"]
    else:
        vol, th = inp["vol_cur_t"], 0.0
    gp_au = vol * (p - inp["unit_cost"]) / 100
    gp_ag = inp["gp_ag"] * k
    surch = inp["surch"] * (vol * p / 100 + inp["rev_byp"] * k)
    pbt = gp_au + gp_ag + inp["gp_rest"] - surch - inp["opex_fixed"] - inp["fin_cost"] + inp["nonop"]
    np_ = pbt * (1 - inp["tax_rate"])
    after = (1 - inp["surch"]) * (1 - inp["tax_rate"])
    np_sj = inp["np_sj"] + inp["rev_sj"] * (k - 1) * after + th * (p - inp["unit_cost"]) / 100 * after
    nci = inp["nci_sj"] * np_sj + inp["nci_oth"] * (np_ - np_sj)
    common = np_ - nci - inp["perp_coupon"]
    w_rest = inp["gp_rest"] / (gp_au + gp_ag + inp["gp_rest"])
    return {"vol": vol, "p": p, "pbt": pbt, "np": np_, "np_sj": np_sj, "nci": nci, "common": common,
            "eps": common / inp["shares"], "w_rest": w_rest}


def tier(inp: dict[str, float], tag: str, r_shift: float = 0.0) -> dict:
    cur, fwd = year(inp, tag, False), year(inp, tag, True)
    n = int(inp["n_transition"])
    lc = {"au": cur["eps"] * (1 - cur["w_rest"]), "rest": cur["eps"] * cur["w_rest"]}
    l28 = {"au": fwd["eps"] * (1 - fwd["w_rest"]), "rest": fwd["eps"] * fwd["w_rest"]}
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["common"] - cur["common"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"] + r_shift
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    # Gate closed withholds growth credit; a decline is not growth and passes through.
    g1 = g1_raw if gate else {k: min(g1_raw[k], g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"]
    roe = fwd["common"] / inp["equity"]
    for _ in range(80):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["common"] / b27
        if abs(roe_new - roe) < 1e-12:
            break
        roe = roe_new
    r = {k: inp[r_key] + r_shift for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    pre_k = sum(contrib.values())
    cash = max((1 - inp["payout_actual"]) - b1, 0.0) * (cum_roll + fwd["common"]) / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash
    fx = inp["fx_hkd_cny"]
    return {"cur": cur, "fwd": fwd, "lc": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co, "roic": roic, "gate": gate,
            "b1": b1, "b27": b27, "roe28": roe, "pe": pe, "contrib": contrib, "eq_pe": pre_k / cur["eps"],
            "cash": cash, "haircut": haircut, "pre_k": pre_k, "anchor_cny": pre_k - haircut,
            "anchor": (pre_k - haircut) / fx}


def integration_option(inp: dict[str, float], th: dict) -> dict[str, float]:
    """V_opt — 焦家 / 新城 integration increments (A15).

    Size: company-named design output less 2025 output, both mines 100% owned.
    Unit economics: own M-tier realised price less own 2026H1 unit cost, own
    resource-tax ratio and tax rate.  Ruler: own steady-state Gordon on the gold
    leg at the H-tier ROE28 lifted by the increment; valued in t_opt, discounted
    at the basket r to t_num; unspent budget spread over t_build0..t_opt.
    """
    p = price(inp, "m")
    per_t = ((p - inp["unit_cost"]) / 100 - inp["surch"] * p / 100) * (1 - inp["tax_rate"])
    inc = (inp["jj_cap_t"] - inp["jj_now_t"]) + (inp["xc_cap_t"] - inp["xc_now_t"])
    d_np = inc * per_t
    roe_post = (th["fwd"]["common"] + d_np) / th["b27"]
    pe_post = perpetual_pe(inp["g2_au"], roe_post, inp["r_perp"])
    disc = (1 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    gross = d_np / inp["shares"] * pe_post * disc
    k_unspent = (inp["jj_budget"] - inp["jj_spent"]) + (inp["xc_budget"] - inp["xc_spent"])
    years = range(int(inp["t_build0"]), int(inp["t_opt"]) + 1)
    pv_k = sum(k_unspent / len(years) * (1 + inp["r_perp"]) ** (-(t - inp["t_num"])) for t in years)
    fx = inp["fx_hkd_cny"]
    return {"per_t": per_t, "inc": inc, "d_np": d_np, "roe_post": roe_post, "pe_post": pe_post, "disc": disc,
            "gross": gross / fx, "k": k_unspent, "k_ps": pv_k / inp["shares"] / fx,
            "v_opt": (gross - pv_k / inp["shares"]) / fx}


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
    if baskets.get("r_perp") != 4:
        errors.append("r_perp must be 篮 4 (same as 601899.SH gold leg, A10)")
    if abs(inp["axis_g2_aucu"] - axis_g2()) > 1e-9:
        errors.append(f"axis_g2_aucu={inp['axis_g2_aucu']} vs axis 永续 g2 {axis_g2()}")
    if not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]):
        errors.append("gold ladder order violated")
    if not (0 < inp["vol_l_t"] < inp["vol_target_t"] * inp["ach_m"] < inp["vol_target_t"]):
        errors.append("volume ladder L < M < H violated")
    if not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2 or inp["equity"] <= 0:
        errors.append("payout_actual / n_transition / equity invalid")
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k}")
    if errors:
        return report(errors, "FAIL (guards)")
    rungs = load_au_cu_rungs()
    for t in TIERS:
        if abs(inp[f"lme_au_{t}"] - rungs["au"][t.upper()]) > 1e-6:
            errors.append(f"{t.upper()} gold rung: stated {inp[f'lme_au_{t}']:g} vs axis {rungs['au'][t.upper()]:g}")
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for key in ("lme_au_l", "lme_au_m", "lme_au_h", "fx_usd_cny"):
        if key not in peer or abs(inp[key] - peer[key]) > 1e-6:
            errors.append(f"shared input drift: {key} vs 601899.SH")
    if errors:
        return report(errors, "FAIL (shared ladder)")

    T = {t: tier(inp, t) for t in TIERS}
    cur_m = T["m"]["cur"]
    if abs(cur_m["common"] / H1_2026_X2_COMMON - 1) > H1_TOL:
        errors.append(f"M guard: run-rate common {cur_m['common']:.2f} vs H1×2 {H1_2026_X2_COMMON:.2f}")
    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")
    for t in TIERS:
        recomb = sum(T[t]["lc"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["au"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder broken")
    if errors:
        return report(errors, "FAIL (construction)")
    A, B = (L + M) / 2, (M + H) / 2
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    opt = integration_option(inp, T["h"])
    if not (inp["t_num"] < inp["t_build0"] <= inp["t_opt"]) or opt["v_opt"] < 0 or opt["k"] < 0:
        errors.append("V_opt: build/realisation years out of order, negative option, or spent > budget")
    band3 = tuple(base + P_K[i] * opt["v_opt"] for i, base in enumerate((L, M, H)))
    out_sec = md.split("### Outputs", 1)[-1]
    got = first_float(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if got is None or abs(got - opt["v_opt"]) > TOL:
        errors.append(f"V_opt: stated {got} vs recomputed {opt['v_opt']:.4f}")
    got = first_float(r"视同派出[^|]*?M 档 \*\*([0-9.]+)\*\*", out_sec)
    if got is None or abs(got - T["m"]["cash"] / inp["fx_hkd_cny"]) > TOL:
        errors.append(f"cash_M: stated {got} vs recomputed {T['m']['cash'] / inp['fx_hkd_cny']:.4f}")
    for k, v in zip("LMH", band3):
        m3 = re.search(rf"^\| {k} \| [0-9.]+ \| [^|]+\| [^|]+\| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - v) > TOL:
            errors.append(f"table3 {k}: stated {m3.group(1) if m3 else None} vs recomputed {v:.4f}")
    for label, want, rx in (("A′", (band3[0] + band3[1]) / 2, r"A′ = \*\*([0-9.]+)\*\*"),
                            ("B′", (band3[1] + band3[2]) / 2, r"B′ = \*\*([0-9.]+)\*\*")):
        got = first_float(rx, out_sec)
        if got is None or abs(got - want) > TOL:
            errors.append(f"{label}: stated {got} vs recomputed {want:.4f}")

    fx = inp["fx_hkd_cny"]
    print(f"formula_id={FORMULA_ID}")
    print("shared Au rungs OK vs _AXIS.fed-path-gold-copper (+ peer 601899.SH, fx_usd_cny)")
    print(f"realised 元/克: " + " ".join(f"{t.upper()} {price(inp, t):.1f}" for t in TIERS))
    print(f"{'档':<3}{'量t':>7}{'普通股利润':>10}{'FY28':>8}{'E_cur':>7}{'E28':>7}{'g1co':>7}{'ROIC':>6}{'门':>3}{'b1':>5}{'ROE28':>7}{'PE金':>7}{'PE余':>6}{'合并':>7}{'锚CNY':>8}{'锚HKD':>8}")
    for t in TIERS:
        x = T[t]
        print(f"{t.upper():<3}{x['fwd']['vol']:7.2f}{x['cur']['common']:10.2f}{x['fwd']['common']:8.2f}{x['cur']['eps']:7.3f}{x['fwd']['eps']:7.3f}"
              f"{x['g1_co']:7.1%}{x['roic']:6.1%}{'过' if x['gate'] else '关':>3}{x['b1']:5.0%}{x['roe28']:7.1%}{x['pe']['au']:7.2f}{x['pe']['rest']:6.2f}"
              f"{x['eq_pe']:7.2f}{x['anchor_cny']:8.2f}{x['anchor']:8.2f}")
    for t in TIERS:
        x = T[t]; c = x["cur"]
        print(f"  {t.upper()}: NP {c['np']:.1f} 山金 {c['np_sj']:.1f} NCI {c['nci']:.1f} | FY28 NP {x['fwd']['np']:.1f} 山金 {x['fwd']['np_sj']:.1f} NCI {x['fwd']['nci']:.1f} | "
              f"g1 au {x['g1']['au']:+.1%} rest {x['g1']['rest']:+.1%} | 金腿 {x['contrib']['au'] / fx:.2f} + 余 {x['contrib']['rest'] / fx:.2f} HKD | 模型派息 {1 - x['b1']:.0%}")
    print(f"M guard OK: run-rate common {cur_m['common']:.2f} 亿 vs H1×2 {H1_2026_X2_COMMON:.2f}")
    print("视同派出现金/股 (HKD) k 前 → k 后: " + " | ".join(
        f"{t.upper()} {T[t]['cash'] / fx:.2f} × k {inp[f'k_{t}']:g} = −{T[t]['haircut'] / fx:.2f}" for t in TIERS))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f} (HKD)")
    print(f"V_opt 焦家/新城整合（A15）：增量 {opt['inc']:.3f} t × {opt['per_t']:.4f} 亿/t = {opt['d_np']:.2f} 亿 × PE {opt['pe_post']:.2f}"
          f"（ROE {opt['roe_post']:.1%}）× {opt['disc']:.4f} = 毛值 {opt['gross']:.2f} − 未投 {opt['k']:.2f} 亿折回 {opt['k_ps']:.2f}"
          f" → V_opt {opt['v_opt']:.2f} HKD；V_opt/M {opt['v_opt'] / M:.1%}")
    print(f"表3 p_k={P_K[0]:g}/{P_K[1]:g}/{P_K[2]:g} → {band3[0]:.2f}/{band3[1]:.2f}/{band3[2]:.2f}  "
          f"A′={(band3[0] + band3[1]) / 2:.2f} B′={(band3[1] + band3[2]) / 2:.2f}")
    print(f"flat-multiple ladder @ gold PE_M {T['m']['pe']['au']:.2f}: " + "/".join(f"{v / fx:.2f}" for v in flat))
    print(f"③ 护栏（披露，不拦——带失真，A6）：合并等效 PE " + "/".join(f"{T[t]['eq_pe']:.2f}" for t in TIERS)
          + f" vs own-year 带 [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]")
    for line in tier_report((L, M, H), tuple(T[t]["eq_pe"] for t in TIERS), tuple(T[t]["cur"]["eps"] for t in TIERS)):
        print(line)
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f}")
    # Sensitivities (only L/M/H): g2 ±1pp, gold M ±$100, alternative basket 6 on the gold leg.
    def band_with(**over: float) -> tuple[float, float, float]:
        alt = dict(inp, **over)
        return tuple(tier(alt, t)["anchor"] for t in TIERS)
    for label, over in (("g2 −1pp", {"g2_au": inp["g2_au"] - 0.01}), ("g2 +1pp", {"g2_au": inp["g2_au"] + 0.01}),
                        ("金腿篮 6 对照", {"r_perp": 0.13}), ("ach_m 0.95", {"ach_m": 0.95}),
                        ("当期量 37 t", {"vol_cur_t": 37.0}), ("增长 capex 180", {"growth_capex_26_28": 180.0})):
        print(f"敏感 {label}: " + "/".join(f"{v:.2f}" for v in band_with(**over)))
    for d in (-100, 100):
        print(f"敏感 金 M {d:+d}: M {tier(dict(inp, lme_au_m=inp['lme_au_m'] + d), 'm')['anchor']:.2f}")

    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(tier(inp, t, r_shift=dr)["anchor"] for t in TIERS)

    rf = rf_block(LISTING_CCY, {"r_perp": inp["r_perp"], "r_rest": inp["r_rest"]}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("1787.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
