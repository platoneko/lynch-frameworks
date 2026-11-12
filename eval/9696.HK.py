#!/usr/bin/env python3
"""9696.HK (Tianqi Lithium H) valuation eval.

Inputs are in this script and the shared lithium axis module; the document carries sources and stated outputs.
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

import hashlib
import json
import math
import sys
from pathlib import Path

if __name__ == "__main__":
    raise SystemExit("Use the explicit valuation_runner with code and content roots")

from lib.gordon import check_g_cap, check_r, implied_g, payout, perpetual_pe, recovery_two_stage_pe
from lib.inputs import check_missing
DEPENDENCIES = {'libraries': ('gordon', 'inputs'), 'axes': {'lithium': 'lithium_carbonate'}}
FORMULA_ID = "tianqi_li2co3_twoleg_volplan_pe10_v2_gordon_v3"
MIN_R_MINUS_G = 0.02
# A9: the company's own realised trough→recovery path (Longbridge annual parent NI, HKD:
# FY2024 −85.57 亿 loss trough; FY2025 5.06 亿 → 2026H1 42.42 亿 CNY × 2 × fx ≈ 95.0 亿 HKD).
RECOVERY_MEASURED = {"FY2025→2026H1×2": (5.06, 42.42 * 2 * 1.119522, 1)}
TOL = 0.05
YI = 1e8
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"

# Inputs transcribed from the previous framework Inputs; sources remain in the document.
INPUTS = {
    # 总股本（H 股配售后）；2026H1 中报 | as-of 2026-06-30
    'shares': 1706244983.0,
    # 每股净资产 HKD；2026H1 中报 | as-of 2026-06-30
    'bps': 32.72,
    # 精矿 ASP 14231 ÷ 150000（旧轴 M，≈H1 平台）；ASP=段收入 105.03 亿/产量 73.8 万；2026H1 中报 | as-of 2026-06-30
    'realization_conc': 0.094874,
    # 16.3 万 ÷ 15.0 万（H1 电池级现货均价 ÷ 旧轴 M）；2026H1 中报 | as-of 2026-06-30
    'realization_chem': 1.086667,
    # 锂矿营业成本/外销估量；外销量=51.22 亿/ASP；2026H1 中报 | as-of 2026-06-30
    'cost_conc': 3672.6,
    # 化合物营业成本/（71.01 亿/16.3 万）；2026H1 中报 | as-of 2026-06-30
    'cost_chem': 69526.79,
    # 214 万×50% 外销权益安排；2026H1 中报产能/分销 | as-of 2026-06-30
    'vol_conc_plan': 1070000.0,
    # 锂化工建成产能 吨/年；2026H1 中报 | as-of 2026-06-30
    'vol_chem_plan': 122600.0,
    # H1 外销精矿对照（反推，不入公式） | as-of 2026-06-30
    'vol_conc_h1': 359891.0,
    # H1 化合物销量对照（反推，不入公式） | as-of 2026-06-30
    'vol_chem_h1': 43565.0,
    # 时点对齐折现率 = 经营腿的篮子 r（与 `r_perp` 同值，A10）；δ = 1.13^−0.5 = 0.941 | as-of 2026-09-20
    'r_disc': 0.13,
    # 时点对齐 τ（年）：估值基准日 2026-06-30（BPS 的资产负债表日）→ 分子年初 2027-01-01（2027 run-rate），取代原「爬坡折 1 年」；窗口利润折 τ/2（A11） | as-of 2026-10-16
    'n_disc': 0.5,
    # FY2026E 归母 EPS CNY（yfinance 4 家均值，区间 2.69–4.36）；窗口可分配利润的分子（A11） | as-of 2026-10-15
    'eps26e_cny': 3.62456,
    # 2026H1 已入账归母净利 亿 CNY；窗口 = FY2026E × 股本 − 本项 − H2 SQM 投资收益（A11）；2026H1 中报 | as-of 2026-06-30
    'np_h1': 42.42,
    # 所得税/税前利润；2026H1 中报 | as-of 2026-06-30
    'tax_rate': 0.24696,
    # 少数股东损益/净利润合计；2026H1 中报 | as-of 2026-06-30
    'nci_share': 0.390263,
    # parent_ops/GP（剔投资收益）；2026H1 中报 | as-of 2026-06-30
    'conv_ratio': 0.444888,
    # 2.81/2.51（H1 H/A EPS 隐含）；非 Longbridge 1.1465 口径，不在本次统一范围 | as-of 2026-06-30
    'fx_hkd_per_cny': 1.119522,
    # 2026H1 投资收益 亿 CNY（主要为 SQM 权益法），\(V_{opt}\) 的已实现单位（属性 E）；中报利润表 | as-of 2026-06-30
    'sqm_inv_income_h1': 15.0,
    # SQM 锂及衍生品分部收入 US$M，1Q2025；SQM 1Q25 业绩公告（6-K，SEC）；\(V_{opt}\) 弹性标定（A7） | as-of 2025-03-31
    'sqm_li_rev_1q25': 502.9,
    # 同期销量 千吨 LCE（智利 52.3 + 国际锂业 2.7）；同上 | as-of 2025-03-31
    'sqm_li_vol_1q25': 55.0,
    # 锂分部占合并毛利比例（公告原句「37.2% of SQM's consolidated gross profit」）；同上 | as-of 2025-03-31
    'sqm_li_gp_share_1q25': 0.372,
    # SQM 合并毛利 US$M；同上 | as-of 2025-03-31
    'sqm_gp_1q25': 304.7,
    # SQM 锂分部收入 US$M，FY2025；SQM 4Q25 业绩公告（6-K，SEC） | as-of 2025-12-31
    'sqm_li_rev_fy25': 2288.2,
    # 同期销量 千吨 LCE = Nova Andino 233.1 + 国际锂业氢氧化锂 1.6 + 锂精矿 156.4 千吨 SC6 ÷ 6.74（SQM 2Q26 公告所用折算系数；FY25 公告未给合计，本行为换算） | as-of 2025-12-31
    'sqm_li_vol_fy25': 257.9,
    # 锂分部占合并毛利比例（公告「45%」）；同上 | as-of 2025-12-31
    'sqm_li_gp_share_fy25': 0.45,
    # SQM 合并毛利 US$M；同上 | as-of 2025-12-31
    'sqm_gp_fy25': 1352.6,
    # SQM 锂分部收入 US$M，1H2026；SQM 2Q26 业绩公告（6-K，SEC，2026-08-19） | as-of 2026-06-30
    'sqm_li_rev_1h26': 2964.8,
    # 同期销量 千吨 LCE（Nova Andino 138.2 + 国际锂业 14.9，SC6 按 6.74 折算）；同上 | as-of 2026-06-30
    'sqm_li_vol_1h26': 153.1,
    # 锂分部占合并毛利比例（公告「78%」）；同上 | as-of 2026-06-30
    'sqm_li_gp_share_1h26': 0.78,
    # SQM 合并毛利 US$M；同上 | as-of 2026-06-30
    'sqm_gp_1h26': 2038.6,
    # SQM 合并税前利润 US$M（所得税 738.3，隐含税率 39.7%）；锂价降到 M 世界时的利润降幅按此口径扣；同上 | as-of 2026-06-30
    'sqm_pretax_1h26': 1860.4,
    # 篮 6 周期商品 / 小盘：整公司两腿同为锂价函数（A10）；零增长 → PE 1/r = 7.69× | as-of 2026-09-20
    'r_perp': 0.13,
    # 永续增速三档 flat；来源层级 = **商品腿 tier 默认**（锂长期实际价格漂移 ≤ −3%/yr → 0，不取负；商品腿不走同业反解，A4）；cap = min(6%, r − 4%) = 6% | as-of 2026-09-20
    'g2': 0.0,
    # 5 年 TTM PE 实测低点（2023-05，剔亏损期）；LB valuation history；**护栏** | as-of 2026-09-07
    'pe_own_min': 2.76,
    # 5 年 TTM PE 实测高点（2026-04，盈利谷底）；**护栏** | as-of 2026-09-07
    'pe_own_max': 197.33,
    # 资产地板倍数（H 股历史低 PB 邻域）；**只披露不 max()**（峰形区地板条款，A10）——L = 情景 L，地板值印在 Outputs 披露行 | as-of 2026-09-20
    'pb_floor': 0.7,
}
BASKETS = {"r_perp": 6}

OPTION_PROBABILITIES = (0.0, 0.5, 1.0)

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
# Original A7 mapping: the 2026H1 SQM observation was paired with the then-axis
# 150,000 CNY/t H reference. It is a calibration proxy, not an observed average.
SQM_H1_REFERENCE_CNY_PER_TONNE = 150_000


def sqm_elasticity(inp: dict[str, float]) -> dict:
    """A7 (2026-10-19): SQM lithium-segment profit vs realised price, from SQM's own releases.
    Per period: realised price P = segment revenue ÷ LCE volume, segment gross profit per tonne =
    (segment share of consolidated GP × consolidated GP) ÷ volume.  gp/t = s × P − c: s < 1 carries
    the price-linked CORFO lease, c the per-tonne cash cost.  M-world price = 1H26 realised ×
    current li2co3_m / the fixed historical 150,000 CNY/t reference;
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
    p_m = p_h * inp["li2co3_m"] / SQM_H1_REFERENCE_CNY_PER_TONNE
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


TICKER = '9696.HK'
# The explicit valuation runner binds code, content and shared inputs.
BASELINE_INPUT_FINGERPRINT = '45b0df3dff0ba66b269ed9cde1dc1f9e63a0879403862b85aa2104854bbb9648'
# These hashes only detect changes to these inputs; they are not approval or a
# complete dependency/version binding for publication.
BASELINE_AXIS_SOURCE = '240d2f3ac34a736b353220f3b0ff29be1c3ca9bb34bcf5411e0f2ec185bc0119'
BASELINE_LIBRARY_SOURCES = {
    'gordon.py': '375db9668f63d268de2b3c57d98582b249d476a647cfdb964fbde84d781cd090',
    'inputs.py': 'cc53372784cd1a02e80b012a9419dd301ba92102cd05e2da7d41679520b56545',
}

def _evaluate(inp: dict[str, float], axis: dict, axis_digest: str, libraries: dict, rate_inputs: dict[str, float] | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(inp[key] != value for key, value in axis.items()):
        raise ValueError("lithium axis inputs differ from the shared axis")
    if inp['li2co3_h'] != SQM_H1_REFERENCE_CNY_PER_TONNE:
        raise ValueError("BLOCKED: SQM first-year earnings at the changed H price lack an adopted calibration")

    r = inp["r_perp"]
    baskets = dict(BASKETS)
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    # valuation-rules「§r 篮子」: r is the basket's value, the framework names the basket;
    # the multiple is generated per tier from one flat g2 (commodity tier default) and the
    # tier ROE; the axis row is referenced verbatim.
    if "r_perp" not in baskets:
        errors.append("r_perp: no basket in BASKETS")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    # A10: the ramp-year discount is the operating leg's basket r, not a separate dial.
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} != r_perp={r} (A10: ramp discount = basket r)")
    errors += check_g_cap(inp["g2"], r, "g2")
    errors += check_g_cap(inp["axis_g2_li"], r, "axis_g2_li")
    if r - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {r - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")
    if errors:
        raise ValueError('; '.join(errors))

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
        raise ValueError(f'L<M<H violated: {L}, {M}, {H}')
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

    if errors:
        raise ValueError('; '.join(errors))
    p_tiers = OPTION_PROBABILITIES
    if (not isinstance(p_tiers, (tuple, list)) or len(p_tiers) != 3
            or any(isinstance(p, bool) or not isinstance(p, (int, float))
                   or not math.isfinite(p) or not 0 <= p <= 1 for p in p_tiers)):
        raise ValueError("option weights must be three finite values in [0, 1]")
    corrected = tuple(base + p * v_opt for base, p in zip((L, M, H), p_tiers))
    if not corrected[0] < corrected[1] < corrected[2]:
        raise ValueError("option-adjusted ladder must increase strictly")
    sensitivity = {}
    for dg in (-.01, .01):
        alt = dict(inp, g2=inp['g2'] + dg)
        sensitivity[str(dg)] = anchors(priced(alt, r), alt, r)
    edges = {str(edge): implied_g(edge, S['m']['roe'], r)
             for edge in (inp['pe_own_min'], inp['pe_own_max'])}
    recovery = {}
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g_measured = (np1 / np0) ** (1 / n) - 1
        g_lm = (S['m']['eps_hkd'] / S['l']['eps_hkd']) ** (1 / n) - 1
        pe_measured = recovery_two_stage_pe(g_measured, n, inp['g2'], S['m']['roe'], r)
        pe_lm = recovery_two_stage_pe(g_lm, n, inp['g2'], S['m']['roe'], r)
        recovery[label] = {'growth_measured': g_measured, 'pe_measured': pe_measured,
                           'value_measured': S['l']['eps_hkd'] * pe_measured,
                           'growth_lm': g_lm, 'pe_lm': pe_lm,
                           'value_lm': S['l']['eps_hkd'] * pe_lm}
    def band_rf(dr):
        shifted = dict(inp, r_disc=inp['r_disc'] + dr)
        a = anchors(priced(shifted, r + dr), shifted, r + dr)
        return tuple(a[t] for t in ('l', 'm', 'h'))
    # The rates axis has not migrated; callers may explicitly supply its inputs.
    rate = None
    if rate_inputs is not None:
        required_rate = ('rf_mid', 'rf_now', 'rf_cons', 'delta_cons', 'rf_step', 'rf_cap')
        missing_rate = [key for key in required_rate if key not in rate_inputs]
        if missing_rate:
            raise ValueError(f"missing rate inputs {missing_rate}")
        if any(isinstance(rate_inputs[key], bool) or not isinstance(rate_inputs[key], (int, float))
               or not math.isfinite(rate_inputs[key]) for key in required_rate):
            raise ValueError("rate inputs must be finite numbers")
        if rate_inputs['rf_step'] < 0 or rate_inputs['rf_cap'] < 0:
            raise ValueError("rate step and pressure cap must be non-negative")
        if abs(rate_inputs['rf_cons'] - rate_inputs['rf_mid'] - rate_inputs['delta_cons']) > 5e-5:
            raise ValueError("rates consensus delta does not match consensus minus midpoint")
        step, cap, delta = rate_inputs['rf_step'], rate_inputs['rf_cap'], rate_inputs['delta_cons']
        rate = {'inputs': dict(rate_inputs), 'low': band_rf(-step), 'high': band_rf(step),
                'consensus': band_rf(delta),
                'pressure': (band_rf(cap)[0], band_rf(0)[1], band_rf(-cap)[2])}
    input_changed = input_basis_changed(inp)
    basis_changed = input_changed or axis_digest != BASELINE_AXIS_SOURCE or libraries != BASELINE_LIBRARY_SOURCES
    return {'ticker': '9696.HK', 'currency': 'HKD', 'inp': inp,
            'valuation_as_of': None, 'historical_financial_basis_as_of': '2026-06-30',
            # Full source and runtime reconciliation is not yet available.
            'framework_as_of': None, 'historical_research_as_of': '2026-10-20',
            'anchors': dict(zip('LMH', (L, M, H))), 'candidate': None,
            'basis_changed': None, 'partial_basis_changed': basis_changed,
            'option': {'value': v_opt, 'weights': dict(zip('LMH', p_tiers)),
                       'anchors': dict(zip('LMH', corrected))},
            'S': S, 'floor': floor, 'AN': AN, 'L': L, 'M': M, 'H': H, 'A': A, 'B': B,
            'flat': flat, 'e_h': e_h, 'cal': cal, 'ratio_m': ratio_m,
            'v_opt_persist': v_opt_persist, 'v_m_sqm': v_m_sqm, 'v_opt': v_opt,
            'tianqi_mh': tianqi_mh, 'p_tiers': p_tiers, 'corrected': corrected,
            'sensitivity': sensitivity, 'band_edge_growth': edges, 'recovery': recovery,
            'option_ratio_2p': v_opt_pass(cal['ratio_2p']),
            'option_ratio_own': v_opt_pass(tianqi_mh),
            'rate': rate}


LITHIUM_INPUTS = ('li2co3_l', 'li2co3_m', 'li2co3_h', 'axis_g2_li')


def calculate(context):
    axis = {key: context['axes']['lithium'][key] for key in LITHIUM_INPUTS}
    return _evaluate({**INPUTS, **axis}, axis, context['axis_versions']['lithium'],
                     context['libraries'], context['rate_inputs'])


def input_basis_changed(inp):
    numeric = {key: float(value) for key, value in inp.items()}
    bundle = {'inputs': numeric, 'baskets': BASKETS, 'option_probabilities': OPTION_PROBABILITIES}
    digest = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return digest != BASELINE_INPUT_FINGERPRINT

# Historical assumptions and evidence retained from the original framework:
# - **属性 A — Greenbushes 成本曲线左侧**：溢价进 `cost_conc` / 毛利率，不进 NAV。
# - **属性 B — 精矿 + 化合物同挂锂轴**：精矿 `realization_conc≈0.095`（H1 段收入/产量反推 ASP ÷ 旧轴 M 15 万）；化合物 `realization_chem≈1.087`（H1 电池级现货均价 **16.3 万元/吨** ÷ 旧轴 M 15 万）。轴改为 2027–28 deck 后 M 不再等于 H1 平台，实现率仍按 H1 标定的比例外推。
# - **属性 C — 周期 PE 陷阱**：主尺倍数由 Gordon 在篮子 r 与商品腿 tier 默认 g2 = 0 下生成（三档 1/r flat），不用 TTM PE、不走同业反解。
# - **属性 D — 量用规划名牌**：精矿外销 = 产能 214 万 × **50%**（文菲尔德股东各 50% 采购权，中报分销安排）；化工 = 建成产能 **12.26 万吨/年**；分子是 2027 run-rate（CGP3 计划 2026 年内爬完），按时点对齐从 2027-01-01 折回 2026-06-30（τ 0.5 年，A11）。
# - **属性 E — SQM 21.9% 权益 = 期权（\(V_{opt}\)），不是腿也不是 NAV**（A2e-7b/7c）：分子**算得出**（权益法投资收益是已实测数：2026H1 15.00 亿）但**源不足以做腿**；按 7c-1「份数可以模糊、单位经济不可以」，单位 = k=1 × 自身已实现单位 = H1 投资收益年化 30 亿，经本票 A8 同一条 (1−t)(1−NCI) 桥 → 13.77 亿归母当量 → 0.90 HKD/股。这个单位是 2026 高价平台下印的，属 H 世界；H 世界按锂轴路过（2026-10-19，与主业 H 档同式）：第一年 0.90，之后回到 M 世界 SQM 收益 = 0.90 × **0.749**（SQM 对锂价的弹性按其三期锂分部数据标定，A7）× M 档倍数 7.69× = 5.21，合计折回一年 → **5.41 HKD**（H1 单位永续的旧读数 6.95）。**升级门槛**：≥2 家卖方给出可复算的 SQM 权益贡献（或 SQM 两期分部利润可标定弹性——2026-10-19 已用三期分部毛利份额完成弹性标定，但只用于期权的 M 世界读数；是否据此转成第三条腿进底牌待用户裁定）→ 做成第三条腿进底牌并从 \(V_{opt}\) 移出；**证伪**：SQM 转亏（2024–25 已发生过）或天齐减持。\(p\) 见表3；Greenbushes 已在精矿腿内（仅被 realization 折价），**MUST NOT** 再进期权（7c-4）。
# | A1 | 锂价真源 `_AXIS.lithium-carbonate` | `active` | 轴 §1 | `li2co3_*` |
# | A2 | 实现率按 H1 标定：精矿 ASP / 化合物现货均价 16.3 万 ÷ 15 万（旧轴 M）；轴 M 改 12.0 万后 M 档实现价 = H1 × 12.0/15 | `active` | 中报产品表 + 行业价格节 | `realization_*` |
# | A3 | 无 NAV（Greenbushes 不另开 NAV 尺；SQM 走 \(V_{opt}\)，见属性 E） | `active` | 对话 | 主尺 |
# | A4 | **倍数由 Gordon 生成：g2 = 0 三档 flat，来源层级 = 商品腿 tier 默认（锂 = 通胀 + 长期实际价格漂移 ≤ −3%/yr → 0，不取负；负增长走全派息萎缩分支或轴 L）；r = 篮 6 13%（A10）；ROE 按档 = EPS_HKD ÷ BPS → 三档皆 7.69× = 1/r** | `active` | **A2d 六维**（2026-09-14 取证，2026-09-20 按篮子 r 重读，2026-10-16 按时点对齐重算读数）：① **研报共识**：LB 15 家 TP 最低 33、MS / JPM 中性 36（2026-09-02，Outputs 实证坐标）；高盛卖出、TP 33 → **22**（2026-10-06，108662：2027 / 2028 锂价 $13.7k / $11.0k，含税约 10.6 / 8.5 万，低于本框架 M / L 轴价）；卖方分腿倍数 / SOTP **待补**。② **EPS**：M 档归母 65.8 亿 CNY（名牌 × 轴 M × δ，δ = 1.13^−0.5）vs yfinance 前瞻 EPS 3.685 HKD（≈ 归母 56 亿）——M 高 17%，差在名牌量 vs 当期量（第一大判断）；无 ≥2 家带区间的 FY27 → 无 g1。③ **ROE**：按档 9.8% / 13.2% / 19.1%；锂簇前瞻 ROE SQM 15.2 / PLS 18.3 / IGO 19.9 / 中矿 31.2——本票 L 档低于 r 3.2pp 落峰形区（g>0 压倍数，g=0 即峰值 1/r），M 档 +0.2pp 病态区（倍数 ≈ 1/r 对 g 不敏感），H 档单调区（g=0 是最低点）。④ **PEG**：不适用（价格事件）。⑤ **交叉约束（护栏）**：5 年 TTM PE 实测带 [2.76, 197.33]（LB 2026-09-07，剔亏损期）——三档在带内；带边反解 g（M 档 ROE 13.2%）2.76× ↔ −23%、197× ↔ +13%（超上限、不良条件）；该带对锂周期股几乎不约束。⑥ **档位可比性**：L/M 0.75 = 分子比 0.75（窗口利润三档同加，略抬 L/M）；H/M 1.05 由 H 档路过决定（Outputs）。**g2 来源**：商品腿不走同业反解（周期端点反解 g 是循环；锂生产商 4 家良态横截面在 10% 尺下反解出的 2.35% 换 r 不重解就是半把尺）→ tier 默认 0；cap = min(6%, 13% − 4%) = 6%。锂轴「永续 g2（2026-09-14）」行 6%（tier 3 截断）以 `axis_g2_li` 逐字引用并校验，**不采用**——6% 下 PE 5.57 / 7.79 / 9.80× → 18.3 / 34.0 / 35.9，峰形区 L 被 g 压掉近三成。g=0 下三档倍数恒等，档差全在分子；同业反解值 2.35% 作敏感区坐标（23.62 / 33.96 / 35.71）。±1pp → M 33.97 / 31.62 | `r_perp` / `g2` / `axis_g2_li` / `pe_own_min/max` |
# | A5 | 三档 = 规划量 × δ；δ=(1+r_disc)^{-τ}，r_disc = 经营腿篮子 r 13%、τ = `n_disc` 0.5 年（时点对齐，A11；原「爬坡折 1 年」δ 0.885 撤）→ 0.941 | `active` | 中报产能/分销；IR 爬坡年内完成 | `vol_*` / `r_disc` / `n_disc` |
# | A6 | 锚点 HKD；`fx` = 2.81/2.51 | `active` | H1 H/A EPS | `fx_hkd_per_cny` |
# | A7 | SQM 等投资收益不进主尺（`parent_ops/GP` 桥已剔除），改走 \(V_{opt}\)：单位 \(E_H\) = k=1 × H1 已实现投资收益 15.00 亿年化 × (1−t)(1−NCI) ÷ 股本 × fx = 0.904 HKD/股（属性 E；7c 复核：单位是已实测的权益法收益、份数 k=1、Greenbushes 已在精矿腿内不再计、无倍数溢价并存）。**H 世界路过（2026-10-19，用户认可）**：H1 单位印在 2026 高价平台，即锂轴 H 档；主业 H 档按「路过」只算一年（A11 ⑤），同一个 H 世界里 SQM 不能永续（商品腿「每档与世界状态一致」、同一公司内部一致）→ \(V_{opt}\) = [\(E_H\) + M 世界 SQM 收益 × PE_M] ÷ 1.13。**M 世界 SQM 收益 = \(E_H\) × 0.749**，按 SQM 自己的公开披露标定：三期锂及衍生品分部（1Q25 / FY2025 / 1H26）实现价 = 分部收入 ÷ LCE 销量 = 9.14 / 8.87 / 19.37 千美元/吨，每吨分部毛利 = 锂分部占合并毛利比例 × 合并毛利 ÷ 销量 = 2.06 / 2.36 / 10.39 → 最小二乘 **每吨毛利 = 0.788 × 价格 − 4.89**（斜率 < 1 是随价格走的 CORFO 租赁费，截距是吨现金成本）；M 世界价格 = 1H26 实现价 × 12.0 / 15（与本票两腿同一映射：H1 平台对轴 H 档）= 15.49 → 1H26 销量 153.1 千吨少赚 467.5 百万美元，占 1H26 税前利润 1,860.4 的 25.1%，税率不变 → SQM 净利润 M/H = **0.749** → \(V_M\) = 0.904 × 0.749 × 7.69 = 5.21 → \(V_{opt}\) = (0.904 + 5.21) ÷ 1.13 = **5.41 HKD**（原 H1 单位永续 6.95，−22.2%）。交叉：只用 FY2025 / 1H26 两期 → 0.756 / 5.45；过渡值（借天齐自身两腿 M/H 利润比 0.691）→ 5.05——SQM 弹性低于天齐（非锂业务碘 / 钾肥不随锂价、部分利润被 CORFO 分走），方向符合预期。**标定的假设**：锂分部毛利只有占比、无金额（公告原句，FY25 45% / 1H26 78% / 1Q25 37.2%）；FY2025 销量为换算（国际锂业锂精矿按 SQM 自己的 6.74 系数折 LCE）；SQM 美元实现价与中国碳酸锂含税价同比例变动；降价不改变税率与少数股东（Codelco）分成比例；天齐投资收益全部按 SQM 权益法处理。**复核**：SQM 披露锂分部毛利金额或吨成本 → 换掉占比推算；出现第四期读数 → 重做回归 | `active` | 中报投资收益 15.00 亿；A8 桥；SQM 业绩公告 1Q25 / 4Q25 / 2Q26（6-K，SEC EDGAR）；用户认可 2026-10-19；升级门槛与证伪见属性 E | `sqm_inv_income_h1` / `conv_ratio` / `sqm_*`；表3 |
# | A9 | **谷底档规则对本票的结果：L 世界是低位 regime，不走回归段**（valuation-rules「谷底档」）。本票自己走过的谷底→回归：Longbridge 年报归母（HKD）FY2024 **−85.57 亿**（2024–25 锂崩盘年，亏损）→ FY2025 **5.06 亿** → 2026H1 42.42 亿 CNY × 2 ≈ 95 亿 HKD（Longbridge 年报序列，2026-09-14 拉取；中报）。两种用法都不能作 L：(i) 亏损谷底 CAGR 无定义；从 FY2025 起算 n = 1、+1,777% 套在 L 分子 3.22 上 → 荒谬地越过 M（414.2）；(ii) 只取实测年数 n = 1、幅度取 L→M（g1 34.0%）→ 10.01× → **32.23 ≈ M（L/M 0.948，塌陷）**。裁决 ⑤→②：轴 L 10.3 万是 2028 底（BMI 11.3 / 高盛 8.5 万两源之间，轴「换算口径」2026-10-12）、高于 p90 成本 6.5 万，轴 §1 明示 2024–25 崩盘区（本票在那里印过 −79 亿归母）不进 L——L 是可持续 regime 而非「跌下去必弹回」的一年，故 L 分子配稳态 g2（同 M）。谷底 × 1/r = EPS_L ÷ 0.13 = **24.77**，g=0 下与 L 的经营价值恒等（L 另含窗口利润 0.80），作 `deep_discount` 压力坐标 | `active` | 年报序列如左；eval 打印两个坐标与 24.77 | L 档倍数 = `perpetual_pe(g2, ROE_L)`；`deep_discount` 行 |
# | A8 | `parent_ops/GP` = H1（归母 − 投资收益×(1−t)×(1−nci)）/ 毛利 | `active` | 中报利润表 | `conv_ratio` |
# | A10 | 归篮：整公司（精矿 + 化合物两腿同为锂价函数）→ 篮 6 周期商品 / 小盘 r = 13%（盈利是商品价函数；与 `1772.HK` / `000792.SZ` / `ALB.US` ES 腿 / `600499.SH` 蓝科腿同篮）；无备选篮；CAPM 粗筛：未取 β，以同簇唯一街 r 样本（UOB 对 1772 的 DCF WACC 12%）作粗筛替代，落篮 6 邻域。`r_disc` 同取篮子 r（时点对齐折现 = 篮子 r，δ 0.941）。**域判定**：ROE 三档 − 13% = −3.2 / +0.2 / +6.1pp → L 峰形区、M 病态区、H 单调区，g=0 下三档皆 1/r；**PB 0.70 地板只披露不 max()**（峰形区地板条款：不随 r 变的资产数不塞进随 r 缩的盈利尺）——地板 22.90 < 情景 L 25.56；g2 取同业反解 2.35% 时 L 23.62，仍在地板之上 | `active` | `gordon.BASKET_R`；`valuation-rules.md`「§r 篮子」；`eval/9696.HK.py` `check_r(r, "r_perp", 6)` | `r_perp` / `r_disc`；三档倍数；`floor` 披露行 |
# | A11 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」）与 H 档路过**：① **超额现金未触发单列**：净负债，利润、回报、历史反解全部用合并口径；分子经 `parent_ops/GP` 桥已是归母，归母份额不另调。② **增长期资金缺口 = 0**：名牌量（CGP3、奎纳纳）年内爬完，资本开支没有大到经营现金流付不起。③ **时点对齐**：分子是 2027 run-rate，Gordon 给的是分子年初 2027-01-01 的价值；估值基准日 = BPS 的资产负债表日 2026-06-30 → **τ = 0.5 年**，按篮子 r 13% 折（δ 0.941），取代原「爬坡折 1 年」（δ 0.885）。**窗口可分配利润** = 2026H2 尚未入账的共识归母（FY2026E 3.62 元 × 股本 − H1 已入账 42.42 亿 = 19.42 亿）按分子同口径剔掉 H2 的 SQM 投资收益（按 H1 15.00 亿 × (1 − 24.7%) × (1 − 39.0%) = 6.89 亿）= 12.54 亿，× (1 − b)，b = g2 ÷ RONIC = 0，按 τ/2 = 0.25 年折 → **+0.80 HKD/股**，三档同加。④ **稳态回报三段：不适用**——两腿分子由 `_AXIS.lithium-carbonate` 桥出，属商品腿豁免；且 g2 = 0，回报不进倍数（1/r）。⑤ **H 档路过（2026-10-16 裁定，锂价轴 H 档「2026 平台延续到 2027」按路过）**：15 万的价格只维持分子年 2027 一年，之后回到 M 档世界：H 经营价值 = [E_H × 派息(g2, ROE_H) + M 档经营价值 × (1 + g2)] ÷ (1 + r)，g2 = 0 时 = (0.13 × 48.07 + 33.20) ÷ 1.13 = 34.91，加窗口 0.80 → **H = 35.70**（长期化读数 48.87）。SQM 期权同按路过处理（2026-10-19）：第一年 H1 单位、之后回到 M 世界 SQM 收益，\(V_{opt}\) 6.95 → 5.41（A7，只进表3）。⑥ 无打折 k | `active` | 2026H1 中报；yfinance FY2026E 共识（4 家，2026-10-15）；2026-10-16 用户裁定（锂价轴 H 档路过） | `n_disc` / `eps26e_cny` / `np_h1`；L/M/H 23.30 / 33.56 / 45.22 → 25.56 / 36.47 / 37.90（M +8.7%；2026-10-20 锂轴 M 12.0 万后 25.56 / 33.99 / 35.70） |

# Historical method changes and prior research decisions:
#
#
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
#
# ### 2026-09-20
#
# - v2 切换（篮子 r）：L/M/H v1 30.62 / 48.53 / 68.89 → 23.30 / 33.56 / 45.22，zone `conservative` → `neutral`（切点 A 39.58 → 28.43 落到现价之下；zone+V `conservative` → `neutral`）；篮子：整公司 → 篮 6 周期商品 / 小盘（锂价函数，A10），`r_perp` / `r_disc` 0.10 → 0.13（δ 0.909 → 0.885）；g2 2.35%（锂生产商 4 家同业反解，tier 1）→ 0（商品腿 tier 默认，商品腿不走同业反解），倍数 9.84 / 10.83 / 11.41× → 三档 7.69× flat；M ×0.69（r 贡献 ×0.71、g 贡献 ×0.997、δ 贡献 ×0.974）；PB 0.70 地板 22.90 改只披露、不再 max()（v1 `L = max(情景, 地板)`）；\(V_{opt}\) 9.79 → 6.95；新增披露行：隐含 r(P) 13.7%、③ 不出带、敏感区 g2 ±1pp 内不翻转、地板只披露；v1 口径 g2 ±1pp → M 46.71 / 50.91，轴行 6% → 28.7 / 62.96 / 101.9，A9 谷底坐标 46.95 / 31.11 → 32.38 / 23.30。`eval/9696.HK.py` 改读篮子（`parse_baskets` + `check_r(r, "r_perp", 篮)` + `check_g_cap(g, r, where)`），地板打印不参与 L。
# - touched: [r 篮子, g2, 地板, 锚点, A4, A5, A7, A9, A10, eval]
#
# ### 2026-10-12
#
# - 碳酸锂期货 LC2701 午盘 10.88 万（日内跌超 10%，年内新低；现货 9 月 15.7 → 12 万）。锂轴分布按含税、USDCNY 6.8645 重算（轴「换算口径」）：2027 簇含税中位 12.0 万仍在 12–13 万带内，**三档 10.3 / 12.5 / 15 万不变，锚点不变**；L 的出处由「BMI 2028 底」单源改为 BMI 11.3 / 高盛 8.5 万两源夹逼、暂定。高盛（10-06）维持卖出、TP 33 → 22，低于 L。
# - touched: [A4 ①, A9 引用, 表1 实证坐标, 表2 deep_discount / neutral 场景文字, eval docstring]
#
# ### 2026-10-20
#
# - 锂价轴 M 12.5 → 12.0 万（9 月以后发布的 2027 均价中位 11.9 万跌破 12 万，`_AXIS.lithium-carbonate` §5；新增德银 2026-10-15）；L 10.3 / H 15 万不变。L/M/H 25.56 / 36.47 / 37.90 → **25.56 / 33.99 / 35.70**（M −6.8%；H 路过一年后回到 M 档，随 M 降）；切点 A / B 31.02 / 37.19 → 29.78 / 34.85；\(V_{opt}\) 5.66 → 5.41（SQM M 世界收益比 0.791 → 0.749）；表3 25.56 / 39.30 / 43.56 → 25.56 / 36.70 / 41.11，A′ / B′ 32.43 / 41.43 → 31.13 / 38.90。可比性 L/M 0.70 → 0.75、H/M 1.04 → 1.05、(H−L)/2M 17% → 15%。随之读数：MS / JPM 中性 TP 36 由 `neutral` 移到 H 之上（`stretched`）；「12 万 × H1 年化量」口径的 M 24.4 落到 L 之下。构造参数（g2、r、篮子、p、量、实现率）未动。
# - touched: [题头, §0 这张表怎么读 / 价带锚点, 属性 E, A2, A4, A7, A9, A10, A11, Inputs li2co3_m, 口径, Outputs 锚点 / 表1 / 实证坐标 / flat 阶梯 / 可比性 / 敏感区, 表2, 表3, 敏感性]
