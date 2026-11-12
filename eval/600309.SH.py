#!/usr/bin/env python3
"""Historical Wanhua realized-margin ladder; not updated research.

Amounts CNY 100 million, shares individual, outputs CNY/share. Three segment
gross-margin conditions and their filing source remain documented in input
comments and the framework. Revenue is fixed across cases; high spread lasts
one year rather than indefinitely. The historical matching and elasticity
are model evidence, not a verified forecast. The Fujian MDI expansion value
is separate, net of the project capital not yet spent; its weights are the
original judgment and not measured probabilities.
"""
# Historical source and unresolved judgment notes:
# H uses the observed 19% blended margin as an input. The original document
# calls its implied polyurethane margin 33.04%, while the original script
# with the same inputs computes about 32.13%; the cause remains unresolved.
# Neither assertion replaces the actual blended-margin input or anchor.
# H is one year of higher earnings followed by M, while its perpetual-peak
# comparison is retained only as a matching and calibration reference.
# The Fujian budget of 31.06 CNY 100 million is a single media relay of
# project filings; 8.9387 is an upper bound from a larger construction line,
# not project-specific spent capital. Cost is deducted at 51.2% ownership
# but value uses the group conversion rate: the unequal ownership basis can
# overstate the option and must be reconciled before treating it as verified.
# Actual production start, incremental sales, prices and margins are unknown;
# the 0/0.5/1 scenario credits are judgments rather than observed probabilities.
# FY2026H1 report, its segment and construction notes, 2025 annual report,
# UBS 2026-08-25 segment analysis, Changcheng 2026-09-03 MDI price and
# PROCESS 2025-11-10 project-budget relay are the historical sources.
from __future__ import annotations

import math
from lib.gordon import check_g_cap, check_r, g_cap, implied_g, perpetual_pe
from lib.inputs import check_missing
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = '41961a58018cc8c01fcc35073ba10504b1762358a6e52c0359c188c5fde7fbfc'

INPUTS = {
    'shares': 3.130471626e9,  # 总股本 3,130,471,626 股；LB static; as-of 2026-06-30
    'rev_h1': 1193.1586,  # 2026H1 营业收入（亿 CNY）；中报; as-of 2026H1
    'gm_rate_h1': 0.170842,  # 2026H1 综合毛利率；中报合并利润表：营业收入 1,193.1586 − 营业成本 989.3171 = 毛利 203.8415 亿（2026-10-28 核正：旧值 0.167205 / 毛利 203.84 与原文不符）; as-of 2026H1
    'op_h1': 140.9517,  # 2026H1 营业利润（亿 CNY）；中报合并利润表「三、营业利润」14,095,167,239.83 元（2026-10-28 核正：旧值 144.8554 与原文不符）; as-of 2026H1
    'np_h1': 100.6296,  # 2026H1 归母净利（亿 CNY）；中报; as-of 2026H1
    'rev_pu': 449.5659,  # 聚氨酯 2026H1 收入（亿 CNY）；中报附注七 61「营业收入、营业成本的分解信息」（含系列间内部收入）; as-of 2026H1
    'rev_pc': 477.3756,  # 石化 2026H1 收入（亿 CNY）；中报附注七 61; as-of 2026H1
    'rev_nm': 225.4770,  # 精细化学品及新材料 2026H1 收入（亿 CNY）；中报附注七 61; as-of 2026H1
    'gm_m_pu': 0.2705,  # **M 档**聚氨酯毛利率（2026H1 实测）= 1 − 成本 327.9589 ÷ 收入 449.5659；中报附注七 61; as-of 2026H1
    'gm_m_pc': 0.0680,  # **M 档**石化毛利率（2026H1 实测）= 1 − 444.8956 ÷ 477.3756；中报附注七 61; as-of 2026H1
    'gm_m_nm': 0.1628,  # **M 档**新材料毛利率（2026H1 实测）= 1 − 188.7783 ÷ 225.4770；中报附注七 61; as-of 2026H1
    'gm_l_pu': 0.2568,  # **L 档**聚氨酯毛利率 = 2025H1 实测 = 1 − 274.1576 ÷ 368.8779；中报附注七 61 上期列；见 A4; as-of 2025H1
    'gm_l_pc': -0.0037,  # **L 档**石化毛利率 = 2025H1 实测 = 1 − 350.6353 ÷ 349.3356（微亏）；中报附注七 61 上期列；见 A4/A8; as-of 2025H1
    'gm_l_nm': 0.0955,  # **L 档**新材料毛利率 = 2025H1 实测 = 1 − 141.3553 ÷ 156.2807；中报附注七 61 上期列；见 A4; as-of 2025H1
    'gm_h_blended': 0.19,  # **H 档**综合毛利率 = 2026Q2 实测单季值；隐含聚氨酯 33.04%；见 A5; as-of 2026Q2
    'conv': 0.713930,  # 营业利润 → 归母的综合系数（含所得税与少数股东）= 100.6296 ÷ 140.9517；见 A7; as-of 2026H1
    'equity': 1136.03,  # 归母净资产（亿 CNY）；中报；各档前瞻 ROE = 归母_x ÷ equity（valuation-rules「永续增长口径」）; as-of 2026-06-30
    'r_perp': 0.10,  # 篮 4 龙头制造 10%：整公司一条经营腿（化工龙头，常规经营现金流；无备选篮）；A16；`check_r`；零增长 → 10×; as-of 2026-09-20
    'pe_l_down': 14.00,  # **L 档倍数**（实测，不是生成的）= 市场在同等盈利月份（2025-05～2026-08，TTM EPS 3.81–4.20）实付 PE 区间的**下沿**（区间 14–19×；A6 / A10 / A15）；L 的隐含 g ≈ 8.6%，越 cap，只作坐标不进公式; as-of 2026-08
    'g2_m': 0.03598,  # **M** 永续 g；来源层级**自身实测带反解·盈利配对**（A15）：M 由 H 按实测弹性折回 \(H\,(EPS_M/EPS_H)^{1+\gamma}\) 后反解 = `implied_g(M/EPS_M, ROE_M 17.7%, r)`；靶是盈利配对值而非带边字段（A16）；≤ cap = min(6%, r − 4%) = 6% ✓; as-of 2026-09-20
    'g2_h': 0.0203,  # **H** 永续 g = `g_print_h`（盈利配对证据，A15）；< `g2_m`（峰值后归一）；≤ cap 6% ✓; as-of 2026-09-20
    'g_print_h': 0.0203,  # H 档盈利配对证据：可见 TTM EPS ∈ 7.4717 ±12% 的 12 个月（2021-11～2022-10）逐月反解 g 的中位（12/12 良态）；进 `g2_h`; as-of 2021-11~2022-10
    'g_print_m': 0.0477,  # M 档盈利配对证据：TTM ∈ 6.4290 ±12% 的 9 个月（2021-10、2022-09～2023-04）中位（9/9 良态）；生成 89.8 > H → **证据上沿，不进公式**（A15）; as-of 2021-10~2023-04
    'n_print_h': 12,  # H 档配对月份数（≥6 才算证据）; as-of 同上
    'n_print_m': 9,  # M 档配对月份数; as-of 同上
    'g_peer_median': -0.0041,  # A 股化工同业反解中位（良态五家，A15）；被同世界门挡为交叉，**不进公式**，只作记录与证伪点; as-of 2026-09-11
    'eps_cons_fy27_lo': 6.08,  # 共识 FY2027 EPS 区间下沿（yfinance 2 家，2026-09-11）；**②-b 判据与交叉，不进公式**; as-of 2026-09-11
    'eps_cons_fy27_mean': 6.675,  # 共识 FY2027 EPS 均值；②-b：须落在 [EPS_M, EPS_H] 内且 M 偏离 ≤ 20%; as-of 2026-09-11
    'eps_cons_fy27_hi': 7.27,  # 共识 FY2027 EPS 区间上沿；交叉; as-of 2026-09-11
    'pe_own_min': 10.45,  # 自身 5 年月频 TTM PE 实测下沿（2022-05）= A6 序列 min；**护栏**（裁决顺序 ③），不再是反解的靶; as-of 2021-09~2026-08
    'pe_own_max': 26.24,  # 自身 5 年月频 TTM PE 实测上沿（2026-03）= A6 序列 max；**护栏**; as-of 2021-09~2026-08
    'pe_own_p75': 18.59,  # own-year 反向带 L 档 = 自身 5 年月频 **p75**；**交叉尺，不进公式**（A6）; as-of 2021-09~2026-08
    'pe_own_med': 15.62,  # own-year 反向带 M 档 = 同一分布 **med**；**交叉尺，不进公式**; as-of 同上
    'pe_own_p25': 13.92,  # own-year 反向带 H 档 = 同一分布 **p25**；**交叉尺，不进公式**; as-of 同上
    'gamma_pe': -0.638,  # 实测 \(d\log PE/d\log EPS\)（= 价格弹性 \(b=0.362\) 减 1）；**进公式**：M 由 H 按 \(b=1+\gamma\) 折回（A15）；也是 H 侧形状检查的靶（A6）; as-of 2021-09~2026-08
    'gamma_pe_se': 0.138,  # `gamma_pe` 的标准误（n=11 窗口）；**不进公式**，见 A6; as-of 同上
    'mdi_spot': 17000,  # 聚合 MDI 现货（元/吨），交叉校验用，**不进公式**；2026 年内高点 20,700（4 月初）、2025 年均价约 15,500; as-of 2026-08-24
    'mdi_peak_season': 19000,  # 瑞银测算的旺季聚合 MDI（元/吨），H 档的独立交叉，**不进公式**; as-of 2026-08-25
    'opt_cap': 70,  # 期权份数：万华福建 MDI 技改 80 → 150 万吨/年的增量（万吨/年）；公司公告 / 环评（2025-10-11 批复）；A9; as-of 2025-10-11
    'opt_price': 16500,  # 2026H1 聚合 MDI 市场均价（元/吨，含税；公式 ÷ (1 + `vat`)）；长城证券 2026-09-03；A9; as-of 2026H1
    'vat': 0.13,  # 增值税率，把含税市场价换成收入口径；A9; as-of 2026
    't_opt': 2027,  # 兑现年：原定 2026Q2 投产、2026-07 报道延后 → 首个完整供货年；A9; as-of 2026-07-10
    'opt_budget': 31.06,  # **期权**·福建 MDI 技改扩能一体化项目总投资（亿，100% 口径）= 310,600 万元；PROCESS 流程工业 2025-11-10 转引项目备案 / 环评（闽工信备〔2024〕A060077 号，2024-07-08 备案）；环评报告书公示本（福州市生态环境局 2025-08-29 受理公示附件）投资额涂黑、建设期 12 个月；**单源·媒体转引**；A9; as-of 2025-11-10
    'opt_spent': 8.9387,  # **期权**·已投代理 = 2026 中报在建工程附注「异氰酸酯新建及配套项目」期末余额（亿；预算 199.67、累计投入占预算 93.14%）——整行未转固余额，本项目未投产其投入尚在此行，故为**已投上限**（该行另含福建 TDI 一期技改 / 36 万吨硝酸等配套，项目级已投未披露 `待补`）；A9; as-of 2026-06-30
    'opt_eq': 0.512,  # **期权**·本票对项目主体万华化学（福建）异氰酸酯有限公司的权益（间接 51.20%）；2026 中报「在子企业中的权益」表；A9; as-of 2026-06-30
    'eps_trough_fy2020': 3.2076,  # 上一轮谷底 FY2020 归母 100.41 亿 ÷ 现股本（Longbridge 年报序列）；谷底 × 1/r = `deep_discount` 压力坐标，**不进公式**; as-of FY2020
}

YI = 1e8
TIERS = ("L", "M", "H")

# Audited baseline: 2026H1 net profit to parent x 2 (100.6296亿 x 2).
BASE_NP_PARENT_YI = 201.2592
BASE_NP_TOL_YI = 0.5

EPS_PEAK_FY2021 = 7.85  # highest EPS the company has ever printed
# ...and what the market actually paid while that EPS was the visible TTM:
# average monthly close over 2022-05..2022-08, the window between the FY2021
# annual report and the 2022 interim.  The numerator guard alone is not enough
# (A5): an anchor can clear 7.85 and still price a multiple peak earnings has
# never been given.
PRICE_AT_EPS_PEAK = 88.34
H_ANCHOR_HEADROOM = 1.25  # 2026's balance sheet and capex carry the difference
SEG_RESIDUAL_MAX = 0.08  # segment table vs consolidated GP, as a share of GP; since 2026-10-28 the
# residual is the filing's own 其他 series + 产品间抵销 + 其他业务 (13.06亿 = 6.4% in 2026H1), not rounding

MIN_R_MINUS_G = 0.02      # 裁决顺序 ①: r - g >= 2%
G_TOL = 5e-5              # A15: stated g2_m must equal the reverse-solve of the elasticity-spaced M
GUARDRAIL_SLACK = 0.01    # 校验步骤 5: generated multiples inside the realised band
GAMMA_TOL = 1e-3          # 校验步骤 6: H-side implied gamma equals gamma_pe up to g2 rounding
MIN_PRINT_MONTHS = 6      # A15: an EPS-matched median needs at least this many months
PEER_G_H_STEP = -0.01     # tier-1 cross-print: H pairs the post-peak g (A15 / v1 §A7)
NUM_YEAR = 2026           # numerator year (2026H1 annualised)
P_TIERS = (0.0, 0.5, 1.0) # A9 — table 3 only, never an input

REQUIRED = [
    "shares", "rev_h1", "gm_rate_h1", "op_h1", "np_h1",
    "rev_pu", "rev_pc", "rev_nm",
    "gm_m_pu", "gm_m_pc", "gm_m_nm",
    "gm_l_pu", "gm_l_pc", "gm_l_nm",
    "gm_h_blended", "conv", "equity",
    "r_perp", "g2_m", "g2_h", "g_print_h", "g_print_m", "n_print_h", "n_print_m",
    "g_peer_median", "pe_own_min", "pe_own_max", "pe_l_down",
    "pe_own_p75", "pe_own_med", "pe_own_p25", "gamma_pe", "gamma_pe_se",
    "eps_trough_fy2020",
    "opt_cap", "opt_price", "vat", "t_opt", "opt_budget", "opt_spent", "opt_eq",
]
# Reference-only rows (校验步骤 11): present in Inputs, never in an anchor path.
NOT_FORMULA = (
    "pe_own_p75", "pe_own_med", "pe_own_p25", "gamma_pe_se",
    "mdi_spot", "mdi_peak_season", "g_peer_median", "g_print_m", "eps_trough_fy2020",
    "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi",
)



CONSENSUS_REASON_RECORDED = True  # Original assumptions disclose the ②-b deviation.


def fujian_option(inp, pe_h, r, opex, base):
    unavailable = {'status': 'unavailable', 'label': '福建MDI扩产', 'anchors': None}
    unspent = inp['opt_budget'] - inp['opt_spent']
    if (inp['t_opt'] <= NUM_YEAR or unspent < 0 or not 0 < inp['opt_eq'] <= 1
            or inp['rev_h1'] == 0 or inp['vat'] <= -1 or inp['shares'] <= 0 or r <= -1):
        return unavailable
    try:
        revenue = inp['opt_cap'] * 1e4 * inp['opt_price'] / (1 + inp['vat']) / YI
        profit = revenue * (inp['gm_m_pu'] - opex / inp['rev_h1']) * inp['conv']
        eps = profit * YI / inp['shares']
        capital_ps = unspent * inp['opt_eq'] * YI / inp['shares']
        disc = (1 + r) ** (inp['t_opt'] - NUM_YEAR)
        gross = eps * pe_h / disc
        value = (eps * pe_h - capital_ps) / disc
        values = {tier: base[tier] + weight * value for tier, weight in zip('LMH', P_TIERS)}
    except (ArithmeticError, TypeError, ValueError):
        return unavailable
    if (not all(math.isfinite(v) for v in (gross, value, profit, unspent, *values.values()))
            or value < 0 or not values['L'] < values['M'] < values['H']):
        return unavailable
    return {'label': '福建MDI扩产', 'value': value, 'value_unit': 'CNY_PER_SHARE',
            'weights': dict(zip('LMH', P_TIERS)), 'anchors': values,
            'gross_value': gross, 'unspent_capital': unspent, 'incremental_profit': profit}


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r = inp['r_perp']
    if r <= 0 or r <= max(inp['g2_m'], inp['g2_h']) or inp['shares'] <= 0 or inp['equity'] <= 0:
        raise ValueError('invalid discount or principal valuation denominator')
    warnings = []
    baskets = {'r_perp': 4}
    # --- Step 1: weld the bridge to the filing ------------------------------
    gp_h1_m = inp["rev_h1"] * inp["gm_rate_h1"]
    seg_gp_m = (
        inp["rev_pu"] * inp["gm_m_pu"]
        + inp["rev_pc"] * inp["gm_m_pc"]
        + inp["rev_nm"] * inp["gm_m_nm"]
    )
    gp_other = gp_h1_m - seg_gp_m
    opex = gp_h1_m - inp["op_h1"]

    # The sell-side segment table and the consolidated statement are two
    # different documents; a large residual means they stopped agreeing.
    if not (0.0 <= gp_other <= SEG_RESIDUAL_MAX * gp_h1_m):
        errors.append(
            f"segment residual {gp_other:.4f}亿 outside [0, {SEG_RESIDUAL_MAX:.0%}] "
            f"of gross profit {gp_h1_m:.4f}亿"
        )
    for leg, lo, hi in (
        ("pu", inp["gm_l_pu"], inp["gm_m_pu"]),
        ("pc", inp["gm_l_pc"], inp["gm_m_pc"]),
        ("nm", inp["gm_l_nm"], inp["gm_m_nm"]),
    ):
        if lo > hi:
            errors.append(f"L margin above M margin on leg {leg}: {lo} > {hi}")
    if inp["gm_h_blended"] <= inp["gm_rate_h1"]:
        errors.append(
            f"gm_h_blended {inp['gm_h_blended']} must exceed 2026H1 blended "
            f"{inp['gm_rate_h1']}"
        )
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if inp["gamma_pe"] >= 0.0:
        errors.append(f"gamma_pe={inp['gamma_pe']} must be negative (A6 measured inverse elasticity)")
    if errors:
        warnings.append('historical_financial_bridge_requires_review')
        errors = []

    # --- Step 2: numerators (spread only) -----------------------------------
    def numerator(gp_half: float):
        gp = gp_half * 2.0
        op = gp - opex * 2.0
        np_parent = op * inp["conv"]
        eps = np_parent * YI / inp["shares"]
        return gp, op, np_parent, eps

    gp_half = {
        "L": (
            inp["rev_pu"] * inp["gm_l_pu"]
            + inp["rev_pc"] * inp["gm_l_pc"]
            + inp["rev_nm"] * inp["gm_l_nm"]
            + gp_other
        ),
        "M": gp_h1_m,
        "H": inp["rev_h1"] * inp["gm_h_blended"],
    }
    num = {t: numerator(gp_half[t]) for t in TIERS}
    eps = {t: num[t][3] for t in TIERS}
    np_parent = {t: num[t][2] for t in TIERS}

    if abs(np_parent["M"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {np_parent['M']:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )
    if eps["H"] > EPS_PEAK_FY2021:
        errors.append(
            f"EPS_H {eps['H']:.4f} exceeds FY2021 peak {EPS_PEAK_FY2021} — "
            "no longer a modelled upper edge"
        )
    if errors:
        warnings.append('historical_profit_reference_requires_review')
        errors = []

    # --- Step 3: tier ROE from one equity field, then the Gordon multiple ----
    roe = {t: np_parent[t] / inp["equity"] for t in TIERS}
    # A10: L's multiple is what the market actually paid on this earnings level, not a generated one;
    # only M and H are Gordon-generated (g2).
    pe_l_down = inp["pe_l_down"]
    g2 = {t: inp[f"g2_{t.lower()}"] for t in ("M", "H")}
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for t in ("M", "H"):
        errors += check_g_cap(g2[t], r, f"g2_{t.lower()}")
        if r - g2[t] < MIN_R_MINUS_G:
            errors.append(f"g2_{t.lower()} {g2[t]:+.4f}: r-g {r - g2[t]:.4f} < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if errors:
        warnings.append('historical_basket_and_growth_require_review')
        errors = []

    # 校验步骤 4 (A15): g2 comes from EPS-matched prints, not from a band edge.
    #   H: the print median itself.  M: H spaced down by the measured elasticity,
    #   then reverse-solved.  L: the M world's g with no recovery.
    b_elastic = 1.0 + inp["gamma_pe"]
    for t in ("h", "m"):
        if inp[f"n_print_{t}"] < MIN_PRINT_MONTHS:
            errors.append(f"n_print_{t}={inp[f'n_print_{t}']:.0f} < {MIN_PRINT_MONTHS}: not enough EPS-matched months for a median (A15)")
    if abs(g2["H"] - inp["g_print_h"]) > G_TOL:
        errors.append(f"g2_h {g2['H']:+.5f} != g_print_h {inp['g_print_h']:+.5f} (A15: H carries its own print median)")
    pe_h = perpetual_pe(g2["H"], roe["H"], r)
    H_anchor = eps["H"] * pe_h
    M_anchor = g_m_derived = None
    try:
        if eps['M'] <= 0 or eps['H'] <= 0:
            raise ValueError('historical elasticity requires positive earnings')
        M_anchor = H_anchor * (eps['M'] / eps['H']) ** b_elastic
        pe_m = M_anchor / eps['M']
        g_m_derived, _ = implied_g(pe_m, roe['M'], r)
        if not math.isfinite(M_anchor) or not math.isfinite(g_m_derived):
            raise ValueError('nonfinite historical growth reference')
    except (ArithmeticError, TypeError, ValueError):
        M_anchor = g_m_derived = None
        warnings.append('historical_growth_reference_unavailable')
    if g_m_derived is not None and abs(g2["M"] - g_m_derived) > G_TOL:
        errors.append(
            f"g2_m {g2['M']:+.5f} != reverse-solve of M = H x (EPS_M/EPS_H)^{b_elastic:.3f} "
            f"-> PE_M {pe_m:.4f} -> g {g_m_derived:+.5f} (A15)"
        )
    # A10: L's multiple is the measured trough print (pe_l_down), so it has no g of its own. It must sit
    # inside the realised band and must not invert the cyclical ladder (L's implied g >= M's g, i.e. no
    # higher multiple than M). The implied g exceeds the cap by construction and is a coordinate only.
    if not (inp["pe_own_min"] <= pe_l_down <= inp["pe_own_max"]):
        errors.append(f"pe_l_down {pe_l_down} outside realised band [{inp['pe_own_min']}, {inp['pe_own_max']}] (A6)")
    try:
        g_l_implied, _ = implied_g(pe_l_down, roe['L'], r)
        if not math.isfinite(g_l_implied):
            raise ValueError('nonfinite historical low-growth reading')
    except (ArithmeticError, TypeError, ValueError):
        g_l_implied = None
        warnings.append('historical_low_growth_reference_unavailable')
    if g_l_implied is not None and g_l_implied < g2["M"] - G_TOL:
        errors.append(
            f"L implied g {g_l_implied:+.5f} < g2_m {g2['M']:+.5f} (裁决顺序 ⑤: 周期票倍数反向，"
            "L 的实测倍数不得高于 M 生成的倍数)"
        )
    try:
        if r <= inp['g_print_m']:
            raise ValueError('invalid historical comparison growth')
        m_print_cap = eps['M'] * perpetual_pe(inp['g_print_m'], roe['M'], r)
        if not math.isfinite(m_print_cap):
            raise ValueError('nonfinite historical comparison')
    except (ArithmeticError, TypeError, ValueError):
        m_print_cap = None
        warnings.append('historical_print_comparison_unavailable')
    if M_anchor is not None and m_print_cap is not None and M_anchor > m_print_cap + 0.05:
        errors.append(f"M {M_anchor:.2f} above its own print evidence {m_print_cap:.2f} (g_print_m {inp['g_print_m']:+.2%}) — A15")
    if errors:
        warnings.append('historical_growth_reference_requires_review')
        errors = []

    pe = {"L": pe_l_down, "M": perpetual_pe(g2["M"], roe["M"], r), "H": perpetual_pe(g2["H"], roe["H"], r)}
    # 校验步骤 5: guardrail — generated multiples inside the realised band.
    for t in TIERS:
        if not (inp["pe_own_min"] - GUARDRAIL_SLACK <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: generated PE_{t} {pe[t]:.3f} outside realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — STOP, do not force g"
            )
    if errors:
        warnings.append('historical_pe_band_requires_review')
        errors = []

    # 校验步骤 6: shape is a RESULT check (裁决顺序 ⑤ / A6).  g must run reversed
    # or flat across tiers; the H-side implied gamma equals the measured one by
    # construction; L enters through its implied g (its multiple is a measured
    # print, A10), so the ladder is checked as implied-g_L >= g_M >= g_H.
    if g_l_implied is not None and not (g_l_implied >= g2["M"] >= g2["H"]):
        errors.append(
            f"g tiers not reversed/flat: L(implied) {g_l_implied:+.4f}/{g2['M']:+.4f}/{g2['H']:+.4f} "
            "(cyclical, 裁决顺序 ⑤)"
        )
    try:
        gamma_band = {t: math.log(pe[t] / pe['M']) / math.log(eps[t] / eps['M']) for t in ('L', 'H')}
        if not all(math.isfinite(value) for value in gamma_band.values()):
            raise ValueError('nonfinite elasticity')
    except (ArithmeticError, TypeError, ValueError):
        gamma_band = None
        warnings.append('historical_elasticity_comparison_unavailable')
    if gamma_band is not None and abs(gamma_band["H"] - inp["gamma_pe"]) > GAMMA_TOL:
        errors.append(f"H-side implied gamma {gamma_band['H']:+.3f} != gamma_pe {inp['gamma_pe']:+.3f} (A6/A15 construction)")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H_persist = (eps[t] * pe[t] for t in TIERS)
    # A17 (valuation-rules「经营价值与超额现金」② 一致性 / 2026-10-16 裁定): the H tier is the
    # 2026Q2 peak spread read as passing through (A15 already prices it 峰值后归一).  The peak
    # holds for one year, then the M world: year-1 earnings EPS_H, retention only what the M
    # world's growth needs, then the M perpetuity -> H = M + (EPS_H - EPS_M) / (1 + r).  The
    # persistent-peak reading H_persist stays the construction that spaces M (elasticity, A15).
    H = M + (eps["H"] - eps["M"]) / (1.0 + r)
    if not all(math.isfinite(value) for value in (L, M, H)) or not (L < M < H):
        raise ValueError(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")
    # 校验步骤 7: H guarded on the anchor side too (A5).
    h_cap = H_ANCHOR_HEADROOM * PRICE_AT_EPS_PEAK
    if H > h_cap:
        errors.append(
            f"anchor H {H:.2f} exceeds {h_cap:.2f} = {H_ANCHOR_HEADROOM} x {PRICE_AT_EPS_PEAK} "
            f"(what the market paid at TTM EPS {EPS_PEAK_FY2021}) — the numerator cleared "
            "the peak but the multiple did not (A5)"
        )

    # 校验步骤 9 (A2e-2c): the tiers must already be a ladder in the numerator.
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # 校验步骤 11: reference rows must stay in Inputs and out of the formula.
    # The anchors above used none of them; this only guards the contract.
    leaked = [k for k in NOT_FORMULA if k not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    A, B = cut_points(L, M, H)

    # Fujian MDI option is independent of the base band and may be unavailable.
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errors.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    option = fujian_option(inp, pe['H'], r, opex, dict(zip('LMH', (L, M, H))))
    if option.get('status') == 'unavailable':
        warnings.append('fujian_project_option_unavailable')

    # 裁决顺序 ②-b (valuation-rules): the margin ladder may stand in for the
    # consensus three points only while the FY2027 consensus mean sits inside
    # [EPS_M, EPS_H] and M is within 20% of it (A9).
    if not (eps["M"] <= inp["eps_cons_fy27_mean"] <= eps["H"]):
        errors.append(f"②-b: consensus FY27 mean {inp['eps_cons_fy27_mean']} outside [EPS_M {eps['M']:.3f}, EPS_H {eps['H']:.3f}]")
    cons_dev = eps['M'] / inp['eps_cons_fy27_mean'] - 1.0 if inp['eps_cons_fy27_mean'] else None
    if cons_dev is None:
        warnings.append('historical_consensus_comparison_unavailable')
    if cons_dev is not None and abs(cons_dev) > 0.20 and not CONSENSUS_REASON_RECORDED:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus with no ②-b named-variable row")

    # 校验步骤 7b: g's leverage is disclosed (band printed at both ends).
    # Evidence range for g2_m: the H print median below, the largest g that
    # still keeps M < H above (past it the ladder collapses, A15).
    lever = None
    try:
        lo_g = inp['g_print_h']
        if lo_g >= r:
            raise ValueError('invalid evidence growth reference')
        lo, hi = lo_g, g_cap(r)
        for _ in range(60):
            mid = (lo + hi) / 2
            if eps['M'] * perpetual_pe(mid, roe['M'], r) < H_persist:
                lo = mid
            else:
                hi = mid
        h_excess = (eps['H'] - eps['M']) / (1.0 + r)
        lever = []
        for growth in (lo_g, .03, g2['M'], lo):
            if growth >= r:
                raise ValueError('invalid sensitivity growth')
            middle = eps['M'] * perpetual_pe(growth, roe['M'], r)
            low = eps['L'] * pe['L']
            a_g, b_g = cut_points(low, middle, middle + h_excess)
            lever.append((growth, low, middle, a_g, b_g))
        if any(not math.isfinite(value) for row in lever for value in row):
            raise ValueError('nonfinite sensitivity')
    except (ArithmeticError, TypeError, ValueError):
        lever = None
        warnings.append('historical_growth_sensitivity_unavailable')

    if errors:
        warnings.append('historical_result_guards_require_review')
    def optional_growth_case(growth):
        try:
            if growth >= r or eps['M'] <= 0 or eps['H'] <= 0:
                raise ValueError('invalid growth sensitivity')
            value = eps['H'] * perpetual_pe(growth, roe['H'], r) * (eps['M'] / eps['H']) ** b_elastic
            if math.isfinite(value):
                return value
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_growth_sensitivity_unavailable')
        return None

    growth_minus = optional_growth_case(g2['H'] - .01)
    growth_plus = optional_growth_case(g2['H'] + .01)
    implied_pu = ((gp_half['H'] - gp_other - inp['rev_pc'] * inp['gm_m_pc'] - inp['rev_nm'] * inp['gm_m_nm'])
                  / inp['rev_pu']) if inp['rev_pu'] else None
    if implied_pu is None:
        warnings.append('historical_pu_margin_comparison_unavailable')
    # 福建 MDI 扩产单列；L 同等盈利实付倍数，M Gordon，H 一年高利润后回中枢。
    return {
        'ticker': '600309.SH', 'currency': 'CNY',
        'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-31',
        'anchors': dict(zip('LMH', (L, M, H))), 'cut_points': {'A': A, 'B': B},
        'candidate': None,
        'option': option,
        'review_flags': warnings,
        'segments': {'company': {'values': dict(zip('LMH', (L, M, H)))}},
        'key_parameters': {'method': {'L': 'historical_equal_earnings_multiple', 'M': 'gordon', 'H': 'one_year_high_profit_then_midpoint'},
                           'discount_rate': dict.fromkeys('LMH', r),
                           'growth_rate': {'L': None, 'M': g2['M'], 'H': g2['H']},
                           'forward_return': roe, 'steady_return': {'L': None, 'M': roe['M'], 'H': roe['H']},
                           'multiple': pe},
        'operating': {'gross_profit': gp_half, 'numerators': num, 'eps': eps, 'segment_residual': gp_other,
                      'operating_expense': opex, 'elasticity': b_elastic, 'implied_low_growth': g_l_implied,
                      'implied_high_pu_margin': implied_pu,
                      'growth_mid_derived': g_m_derived, 'mid_print_cap': m_print_cap,
                      'persistent_high': H_persist, 'consensus_deviation': cons_dev, 'sensitivity_evidence': lever},
        'sensitivity': {
            'flat_multiple': dict(zip('LMH', flat)),
            'historical_own_year': dict(zip('LMH', (eps['L'] * inp['pe_own_p75'], eps['M'] * inp['pe_own_med'], eps['H'] * inp['pe_own_p25']))),
            'flat_own_year': dict(zip('LMH', (eps[t] * inp['pe_own_med'] for t in TIERS))),
            'trough_coordinate': inp['eps_trough_fy2020'] / r,
            'pb_floor': inp['equity'] * YI / inp['shares'],
            'margin_1pp': {leg: inp[f'rev_{leg}'] * .01 * 2 * inp['conv'] * YI / inp['shares'] * pe['M'] for leg in ('pu', 'pc', 'nm')},
            'growth_h_minus_1pp': growth_minus,
            'growth_h_plus_1pp': growth_plus,
        },
    }


def calculate(context):
    result = evaluate(dict(INPUTS))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'].extend(['fujian_project_capital_and_ownership_unverified',
                                   'historical_margin_breakdown_discrepancy'])
    constants = {'unit_scale': YI, 'tiers': TIERS, 'option_weights': P_TIERS, 'numerator_year': NUM_YEAR,
                 'historical_profit': BASE_NP_PARENT_YI, 'historical_profit_tolerance': BASE_NP_TOL_YI,
                 'historical_peak_eps': EPS_PEAK_FY2021, 'historical_peak_price': PRICE_AT_EPS_PEAK,
                 'high_anchor_headroom': H_ANCHOR_HEADROOM, 'segment_residual_max': SEG_RESIDUAL_MAX,
                 'rate_growth_margin': MIN_R_MINUS_G, 'growth_tolerance': G_TOL,
                 'guardrail_slack': GUARDRAIL_SLACK, 'gamma_tolerance': GAMMA_TOL,
                 'minimum_print_months': MIN_PRINT_MONTHS, 'excluded_reference_fields': NOT_FORMULA,
                 'consensus_reason_recorded': CONSENSUS_REASON_RECORDED}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed({'inputs': INPUTS, 'constants': constants}, BASELINE_LOCAL)
    return result
