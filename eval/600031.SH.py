#!/usr/bin/env python3
"""Historical Sany forward earnings and matched-month valuation.

Amounts and shares follow original inputs; outputs are CNY/share. The
historical same-earnings monthly observations and cash assumptions are kept
below; original filing and forecast sources remain in input comments and the
document. The FY2028 forecasts, 2026H1 cash and historical return path are not
updated. Same-earnings growth is re-solved on the matching return path, not
silently substituted from a different peer or interest-rate environment.

Excess cash is separated and its own after-tax income removed from earnings.
L uses a historical trough and a measured recovery; M/H use forecasts with
return fade. Current cash ownership does not prove future distributions, and
already forecast electrification and overseas growth must not be added again.
"""
# Research rationale retained from the document:
# The 2028 mean is from 17 H1-report-era sell-side estimates, dated
# 2026-08-31 to 09-14; the high is Zheshang's 2026-09-14 forecast. L uses
# FY2022 parent profit 42.90 less 0.75 CNY 100 million cash income and a
# measured 3.5-year recovery toward the latest twelve-month operating profit.
# The 2016–2023 invested-capital return path is 2.1, 6.7, 19.3, 36.3,
# 35.4, 26.8, 8.5, 8.4 percent, mean 17.9%. Overseas mix rose materially;
# a complete cycle after that change is not yet observed. M/H historical
# growth estimates pair each eligible month's cash-adjusted earnings and
# price with the same discount timing and fade path, not a static peer rate.
# The FY2025 H-share proceeds have stated sales network, R&D, overseas
# manufacturing and working-capital uses. Their relationship to future capex
# and the cash separated in this model still needs review; ownership does not
# establish immediate distribution. FY2024–2026H1 capex/depreciation was
# below one; this was the basis of the original zero growth-funding gap, not
# proof that future capex or operating cash needs are fully funded.
# FY2025 reports also disclose customer financing and guarantees. Changes in
# credit losses or funding needs require reassessment of earnings and cash.
from __future__ import annotations

import math
import statistics
from lib.gordon import (check_branch, check_g_cap, check_r, implied_g_retaining, payout, payout_gap,
                        perpetual_pe, recovery_two_stage_pe)
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = '0c19affd6f4d72ddd337a272e0283dc1bc40c06b6cdaeb29fafe68ce1722f152'

INPUTS = {
    'shares': 9.195004437e9,  # 总股本（A 8,474,390,037 + H 720,614,400）；2025 年报 / 2026 中报; as-of 2026-06-30
    'bps': 10.015,  # 每股净资产 CNY（东方财富主要指标；FY2025 末期股息 0.18 已于 6/30 前宣告、计入应付股利，不再扣）; as-of 2026-06-30
    'np_h1': 5.690e9,  # 2026H1 归母；BPS 滚动时从 FY2026E 中扣除已入账部分; as-of 2026-06-30
    'cons_np26_m': 1.0434e10,  # FY2026E 共识归母均值（18 家，A1）；BPS 滚动用; as-of 2026-10-13
    'cons_np26_h': 1.0987e10,  # FY2026E 上沿（浙商）; as-of 2026-10-13
    'cons_np27_l': 1.3023e10,  # FY2027E 下沿（开源）；证伪触发线（A10），**不进公式**; as-of 2026-10-13
    'cons_np27_m': 1.3636e10,  # FY2027E 均值（18 家）; as-of 2026-10-13
    'cons_np27_h': 1.4640e10,  # FY2027E 上沿（湘财）; as-of 2026-10-13
    'cons_np28_l': 1.5471e10,  # FY2028E 下沿（国金）；**只作敏感性**; as-of 2026-10-13
    'cons_np28_m': 1.6483e10,  # **M** 分子 = FY2028E 共识归母均值（17 家，A1）; as-of 2026-10-13
    'cons_np28_h': 1.7895e10,  # **H** 分子 = FY2028E 上沿（浙商 09-14）; as-of 2026-10-13
    'np_l': 4.215e9,  # **L** 经营利润 = FY2022 实测谷底归母 42.90 亿 − 当年自身超额现金税后收益 0.75 亿（A9 / A15）; as-of FY2022
    'np_ttm': 8.884e9,  # TTM 归母（2025H2 + 2026H1）：L 回归终点; as-of 2026-06-30
    'equity': 9.2084e10,  # 归母权益；L 段二 ROE = `np_ttm` ÷ equity; as-of 2026-06-30
    'n_rec_l': 3.5,  # L 段一年数 = FY2022 → TTM 实测回归年数（A9）; as-of FY2022–2026H1
    'np_fy22': 4.290e9,  # FY2022 归母；同世界门的自身 3 年 CAGR 起点（A5）; as-of FY2022
    'np_fy25': 8.408e9,  # FY2025 归母；同世界门终点; as-of FY2025
    'np_mid10': 7.0386e9,  # 自身十年（FY2016–25）归母均值；周期位置披露（A10），**不进公式**; as-of FY2025
    'np_peak_own': 1.894e10,  # 自身可见 TTM 归母高点（2021-04～07，TTM EPS 2.2311 × 84.9 亿股）；H 坐标披露（A14），**不进公式**; as-of 2021-07
    'np_2016': 2.03e8,  # FY2016 归母；`deep_discount` 坐标，**不进公式**; as-of FY2016
    'r_perp': 0.10,  # 篮 4 常规经营 10%：工程机械价格自谈、非商品价函数，无单一客户 / 国别依赖（A3）；`check_r`; as-of 2026-10-13
    'g2_m': 0.043654,  # M 档稳态 g₂ = 自身同等盈利月份反解中位，经营口径，按同一时点对齐、同一条回报路径（稳态 17.9%）的尺重解（今天经营价值 ÷ 经营利润 = 三段 PE × 1.1^−τ + 窗口占比 ×（1 − g/当月回报）× 1.1^−τ/2；14 个月、13 个良态，A5）; as-of 2026-10-19
    'g2_h': 0.039711,  # H 档稳态 g₂ = 同法（13 个月、12 个良态，A5）; as-of 2026-10-19
    'payout_obs': 0.5068,  # 实付现金派息率 FY2025 = 42.61 ÷ 84.08（回购用于员工持股，不计，A7）；披露; as-of FY2025
    'payout_op': 0.464,  # 经营口径派息率 = 分红 + 现金积累（扣股权融资），FY2016–25 一个完整周期（A15）；`check_branch` 用; as-of FY2025
    'net_cash_ext_h1': 2.8994e10,  # 扩展口径净现金 2026H1 = 现金 + 交易性金融资产 495.80 − 有息负债（含拆入资金、质押式回购）205.86 亿（A15）; as-of 2026-06-30
    'div_declared': 1.6551e9,  # 已宣派未付 FY2025 末期股息 0.18 元 × 91.95 亿股（2026-07-17 除息）；类债项; as-of 2026-06-30
    'c_ex': 2.7339e10,  # 超额现金 = `net_cash_ext_h1` − `div_declared` − 经营所需现金锚 0（A15）; as-of 2026-06-30
    'cash_yield': 0.0394,  # 现金收益率 FY2025 = 利息收入 + 交易性金融资产持有收益 + 理财收益 16.87 ÷ 平均现金类资产 428.16 亿; as-of FY2025
    'tax_eff': 0.1433,  # 实际所得税率 FY2025 = 所得税 14.20 ÷ 利润总额 99.07 亿; as-of FY2025
    'k_l': 0,  # 视同派出打折 L：B 桶默认 0（去向具名：账上净现金，A7）; as-of 2026-10-13
    'k_m': 0,  # 同上 M; as-of 2026-10-13
    'k_h': 0,  # 同上 H（B 桶；H 与 M 之差来自共识分布、非价格轴，①b 不适用）; as-of 2026-10-13
    'tau': 1.5,  # 时点对齐 τ = 估值基准日 2026-06-30 → 分子年初 2028-01-01（18 个月）；经营价值 ÷ (1+r)^τ，窗口可分配利润 ÷ (1+r)^(τ/2)（折现率同 `r_perp`，不归篮；A11）; as-of 2026-06-30
    'minority_h1': 1.111e9,  # 少数股东权益（yfinance 季报资产负债表）；归母比例用（A15）; as-of 2026-06-30
    'parent_ratio': 0.9881,  # 归母比例 = `equity` ÷（`equity` + `minority_h1`）；无子公司级现金披露（A15）；eval 重算校验; as-of 2026-06-30
    'y1': 2028,  # 高回报期止点 Y₁ = 可见年末 FY2028（默认）（A16）; as-of 2026-10-16
    'y2': 2032,  # 回落到稳态 Y₂ = Y₁ + 4（门槛判中，不确定；本票路径不起作用，A16）; as-of 2026-10-16
    'ronic_own': 0.179,  # 自身最近一轮完整谷到谷周期 FY2016–23 经营回报均值，投入资本口径（税后经营利润 ÷ 期初权益 + 净有息负债 − 超额现金；8 年：2.1% / 6.7% / 19.3% / 36.3% / 35.4% / 26.8% / 8.5% / 8.4%）（A16）; as-of 2026-10-19
    'ronic_own_1925': 0.196,  # 自身 FY2019–25 均值（同口径）；**只作敏感性，不进公式**; as-of 2026-10-19
    'ronic_own_2125': 0.132,  # 自身 FY2021–25 均值（同口径，海外占比过半之后）；**只作敏感性，不进公式**; as-of 2026-10-19
    'ronic_ss_floor': 0.15,  # 生意模式兜底：有壁垒的重资产（设备）15%；本票只作对照（自身周期可用）; as-of 2026-10-16
    'ronic_ss': 0.179,  # 稳态回报 = 自身周期 `ronic_own`（按序取第一层；同业与兜底只作对照，A16；用户 2026-10-19 认可）; as-of 2026-10-19
    'pe_band_min': 9.18,  # M 档同等盈利月份经营倍数下沿（2022-03）；③ 护栏; as-of 2026-10-15
    'pe_band_max': 23.88,  # M 档同等盈利月份经营倍数上沿（2021-02）；③ 护栏; as-of 2026-10-15
    'pb_own_min': 1.636,  # 自身 10 年月频 PB 低点（2024-01）；地板披露，**不进公式**; as-of 2026-10-13
    'net_debt': -3.3112e10,  # 净债务 FY2025 = 有息负债 210.75 − 货币资金 384.51 − 交易性金融资产 157.36 亿（A8）; as-of 2025-12-31
    'net_debt_ext': -2.8315e10,  # 扩展口径（+ 拆入资金 36.47 + 其他流动负债有息部分 11.50 亿）; as-of 2025-12-31
    'ebitda': 1.3490e10,  # 营业利润 99.36 + 折旧摊销 35.54 亿; as-of FY2025
    'ebit': 9.936e9,  # 报表营业利润; as-of FY2025
    'interest': 7.33e8,  # 财务费用利息支出 5.69 + 金融业务利息支出 1.64 亿; as-of FY2025
}

YI = 1e8
NUM_YEAR = 2028
TODAY_FY = 2026
TOL = 0.05
PAIR_BAND = 0.12          # same-earnings window, valuation-rules 裁决顺序 ④
MIN_GOOD = 6
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3
G2_PREV = {"m": 0.034720, "h": 0.031965}   # g2 before the 2026-10-19 correction (switch-effect reading only)

# Same-earnings months (A-share monthly close, unadjusted; TTM EPS = the latest
# report visible at month end; BPS same report; shares then 84.9亿).  Built by
# frameworks/_local/tmp/600031/mkt/calc_hist.py from Longbridge monthly klines
# and Eastmoney quarterly EPS (2026-10-13).  Only these months fall within ±12%
# of the M or H numerator; the selection below re-checks that.
SHARES_THEN = 84.9e8
# Excess cash visible at each month end (extended net cash of the then-latest
# report, anchor 0; quarterly interest-bearing other current liabilities at the
# annual 0.72 share) and its after-tax yield then (cash yield ~4.5%, tax ~13%).
CEX_THEN = {"Q3-20": 63.9e8, "FY20": 82.37e8, "Q1-21": 74.3e8, "H1-21": 92.0e8, "Q3-21": 62.5e8}
YIELD_THEN = 0.045 * (1 - 0.13)
MONTHS = [  # (month, close, ttm_eps, bps, visible report)
    ("2020-10", 25.95, 1.7192, 6.2963, "Q3-20"), ("2020-11", 30.71, 1.7192, 6.2963, "Q3-20"),
    ("2020-12", 34.98, 1.7192, 6.2963, "Q3-20"), ("2021-01", 40.46, 1.7192, 6.2963, "Q3-20"),
    ("2021-02", 41.11, 1.7192, 6.2963, "Q3-20"), ("2021-03", 34.15, 1.8401, 6.6713, "FY20"),
    ("2021-04", 30.88, 2.2311, 7.3216, "Q1-21"), ("2021-05", 30.29, 2.2311, 7.3216, "Q1-21"),
    ("2021-06", 29.07, 2.2311, 7.3216, "Q1-21"), ("2021-07", 24.82, 2.2311, 7.3216, "Q1-21"),
    ("2021-08", 26.23, 2.0169, 7.2871, "H1-21"), ("2021-09", 25.44, 2.0169, 7.2871, "H1-21"),
    ("2021-10", 22.96, 1.8572, 7.5577, "Q3-21"), ("2021-11", 21.90, 1.8572, 7.5577, "Q3-21"),
    ("2021-12", 22.80, 1.8572, 7.5577, "Q3-21"), ("2022-01", 20.14, 1.8572, 7.5577, "Q3-21"),
    ("2022-02", 19.61, 1.8572, 7.5577, "Q3-21"), ("2022-03", 17.52, 1.8572, 7.5577, "Q3-21"),
]

REQUIRED = [
    "shares", "bps", "np_h1", "cons_np26_m", "cons_np26_h", "cons_np27_l", "cons_np27_m", "cons_np27_h",
    "cons_np28_l", "cons_np28_m", "cons_np28_h", "np_l", "np_ttm", "equity", "n_rec_l",
    "np_fy22", "np_fy25", "np_mid10", "np_peak_own", "np_2016",
    "r_perp", "g2_m", "g2_h", "payout_obs", "payout_op", "k_l", "k_m", "k_h", "tau",
    "minority_h1", "parent_ratio", "y1", "y2", "ronic_own", "ronic_own_1925", "ronic_own_2125", "ronic_ss_floor", "ronic_ss",
    "pe_band_min", "pe_band_max", "pb_own_min",
    "net_debt", "net_debt_ext", "ebitda", "ebit", "interest",
    "net_cash_ext_h1", "div_declared", "c_ex", "cash_yield", "tax_eff",
]


def path_pe(g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段) at the start of NUM_YEAR per unit
    of NUM_YEAR earnings: RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after."""
    if r - g <= 0:
        raise ValueError("r <= g")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = NUM_YEAR + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g, ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def aligned_solver(u: float, r: float, tau: float, y1: int, y2: int, r_ss: float):
    """g such that today's operating value / FY2028 operating earnings on this ruler (path PE x
    (1+r)^-tau + window share u x (1 − g/ROE) x (1+r)^-(tau/2)) equals a month's operating multiple
    (valuation-rules ②-3 历史反解同口径 + ③ 时点对齐)."""
    def f(g: float, roe: float) -> float:
        return path_pe(g, roe, r, y1, y2, r_ss) * (1 + r) ** -tau + u * (1 - g / roe) * (1 + r) ** -(tau / 2)

    def solve(pe: float, roe: float) -> tuple[float, bool]:
        lo, hi = -0.5, r - 1e-6
        if not (f(lo, roe) <= pe <= f(hi, roe)):
            return float("nan"), False
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid, roe) < pe:
                lo = mid
            else:
                hi = mid
        g = (lo + hi) / 2
        return g, 0.0 <= g < r
    return solve


def print_match(target_np: float, r: float, solve=None) -> tuple[list[tuple[str, float, float, float, bool]], float | None]:
    """Same-earnings months on the operating basis: price and EPS net of the
    excess cash visible then, ROE on equity net of it.  `solve(pe, roe)` reverse-solves
    g on the framework's ruler (default: the single-stage retention Gordon)."""
    lo, hi = target_np * (1 - PAIR_BAND), target_np * (1 + PAIR_BAND)
    rows = []
    for month, close, eps, bps, rep in MONTHS:
        cps = CEX_THEN[rep] / SHARES_THEN
        eps_op = eps - cps * YIELD_THEN
        if not lo <= eps_op * SHARES_THEN <= hi:
            continue
        pe, roe = (close - cps) / eps_op, eps_op / (bps - cps)
        g, ok = solve(pe, roe) if solve else implied_g_retaining(pe, roe, r)
        rows.append((month, pe, roe, g, ok))
    good = [g for *_, g, ok in rows if ok]
    return rows, (statistics.median(good) if len(good) >= MIN_GOOD else None)


def optional_ratio(numerator, denominator):
    try:
        value = numerator / denominator
        return value if math.isfinite(value) else None
    except (ArithmeticError, TypeError, ValueError):
        return None


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('y1', 'y2'))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, sh, tau = inp['r_perp'], inp['shares'], inp['tau']
    if r <= 0 or r <= max(inp['g2_m'], inp['g2_h']) or sh <= 0 or inp['equity'] + inp['minority_h1'] <= 0:
        raise ValueError('invalid discount or principal valuation denominator')
    if inp['np_l'] <= 0 or inp['n_rec_l'] <= 0:
        raise ValueError('trough profit and recovery period must be positive')
    warnings = []
    errors += check_r(r, 'r_perp', 4)
    for key in ('g2_m', 'g2_h'):
        errors += check_g_cap(inp[key], r, key)
    if abs(tau - ((NUM_YEAR - TODAY_FY) * 12 - 6) / 12) > 1e-9:
        errors.append('tau must match 2026-06-30 to numerator year')
    y1, y2 = int(inp['y1']), int(inp['y2'])
    if not (y1 == NUM_YEAR and y2 == y1 + 4):
        errors.append('return fade must run 2028 to 2032')
    if abs(inp['ronic_ss'] - inp['ronic_own']) > 5e-4:
        errors.append('steady return must match own trough-to-trough cycle')
    errors += ladder('FY2028 consensus', inp['cons_np28_l'], inp['cons_np28_m'], inp['cons_np28_h'])
    if not (inp['k_h'] >= inp['k_m'] >= inp['k_l']):
        errors.append('cyclical k must satisfy H >= M >= L')
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []

    c_tot = inp['net_cash_ext_h1'] - inp['div_declared']
    if abs(c_tot - inp['c_ex']) > 1e6:
        errors.append('excess cash differs from net cash minus declared dividend')
    pr = inp['equity'] / (inp['equity'] + inp['minority_h1'])
    if abs(pr - inp['parent_ratio']) > 5e-5:
        errors.append('parent equity ratio differs from balance sheet')
    c_ex = c_tot * pr
    if c_ex < .15 * inp['equity']:
        errors.append('excess cash below 15% threshold')
    c_inc = c_ex * inp['cash_yield'] * (1 - inp['tax_eff'])
    cps = c_ex / sh
    op = {t: tuple((inp[f'cons_np{y}_{t}'] - c_inc) / sh for y in (26, 27, 28)) for t in ('m', 'h')}
    if any(op[t][2] == 0 for t in ('m', 'h')):
        raise ValueError('forward operating earnings cannot be zero for the return calculation')
    eps_h1 = (inp['np_h1'] - c_inc / 2) / sh
    unb = {t: op[t][0] - eps_h1 + op[t][1] for t in ('m', 'h')}
    r_ss = inp['ronic_ss']
    pm = {}
    for t in ('m', 'h'):
        try:
            rows, med = print_match(op[t][2] * sh, r, aligned_solver(unb[t] / op[t][2], r, tau, y1, y2, r_ss))
        except (ArithmeticError, TypeError, ValueError):
            rows, med = [], None
            warnings.append('historical_matched_month_reference_unavailable')
        pm[t] = (rows, med)
        if med is None:
            errors.append(f'{t}: fewer than {MIN_GOOD} usable matched months')
        elif abs(med - inp[f'g2_{t}']) > 5e-5:
            errors.append(f'{t}: growth differs from matched-month median')
    if inp['g2_h'] > inp['g2_m']:
        errors.append('H growth exceeds M growth')
    m_pes = [pe for _, pe, *_ in pm['m'][0]]
    if not m_pes or abs(min(m_pes) - inp['pe_band_min']) > .01 or abs(max(m_pes) - inp['pe_band_max']) > .01:
        errors.append('stated earnings band differs from matched months')
    ratio = optional_ratio(inp['np_fy25'], inp['np_fy22'])
    cagr = ratio ** (1 / 3) - 1 if ratio is not None and ratio > 0 else None
    if cagr is None:
        warnings.append('historical_profit_growth_reference_unavailable')
    if cagr is not None and cagr > 0 and min(inp['g2_m'], inp['g2_h']) <= 0:
        errors.append('positive own profit growth conflicts with nonpositive terminal growth')
    if errors:
        warnings.append('historical_cash_and_evidence_require_review')
        errors = []

    disc, disc_w = (1 + r) ** tau, (1 + r) ** (tau / 2)
    obps = inp['bps'] - cps

    def tier(t, g, rs=None):
        e26, e27, e28 = op[t]
        roe = e28 / obps
        for _ in range(300):
            bps28 = obps + g / roe * unb[t]
            roe = e28 / bps28
        pe = path_pe(g, roe, r, y1, y2, r_ss if rs is None else rs)
        w = max(unb[t] * (1 - g / roe), 0) / disc_w
        return dict(eps=e28, roe=roe, bps=bps28, pe=pe, w=w, pe_1=perpetual_pe(g, roe, r),
                    anchor=e28 * pe * (1 - inp[f'k_{t}']) / disc + w + cps)

    rows = {t: tier(t, inp[f'g2_{t}']) for t in ('m', 'h')}
    for t in ('m', 'h'):
        if rows[t]['roe'] - r < .03:
            errors.append(f'{t}: forward return outside monotone zone')
        errors += check_branch(inp[f'g2_{t}'], rows[t]['roe'], r, inp['payout_op'], f'g2_{t}')
    np_ttm_op, eq_op = inp['np_ttm'] - c_inc, inp['equity'] - c_ex
    if np_ttm_op <= 0 or eq_op <= 0:
        raise ValueError('trough recovery requires positive operating profit and equity')
    roe_mid = np_ttm_op / eq_op
    if inp['np_l'] / eq_op >= r:
        errors.append('L is no longer a trough return')
    g1 = (np_ttm_op / inp['np_l']) ** (1 / inp['n_rec_l']) - 1
    pe_l = recovery_two_stage_pe(g1, inp['n_rec_l'], inp['g2_m'], roe_mid, r)
    tail_branch = check_branch(inp['g2_m'], roe_mid, r, inp['payout_op'], 'g2 (L tail)')
    if inp['g2_m'] <= 0 or inp['payout_op'] >= .95:
        errors += tail_branch
    tail_gap = payout_gap(inp['g2_m'], roe_mid, inp['payout_op'])
    L = inp['np_l'] / sh * pe_l * (1 - inp['k_l']) + cps
    M, H = rows['m']['anchor'], rows['h']['anchor']
    if not all(math.isfinite(value) for value in (L, M, H)) or not L < M < H:
        raise ValueError('base valuation tiers must be finite and ordered')
    if not (pe_l >= rows['m']['pe'] >= rows['h']['pe'] - 1e-9):
        errors.append('cyclical multiple shape is not reverse or flat')
    flat = [inp['np_l'] / sh * rows['m']['pe'] + cps] + [
        rows[t]['eps'] * rows['m']['pe'] / disc + rows[t]['w'] + cps for t in ('m', 'h')]
    errors += ladder('flat-multiple', *flat)
    mult_m = (M - cps) / rows['m']['eps']
    if not inp['pe_band_min'] <= mult_m <= inp['pe_band_max']:
        errors.append('M operating multiple outside same-earnings band')
    for t in ('m', 'h'):
        if abs(rows[t]['pe'] - rows[t]['pe_1']) > 1e-9 and rows[t]['roe'] <= r_ss:
            errors.append(f'{t}: path PE differs from single stage below steady return')
    lev1, lev2 = optional_ratio(inp['net_debt'], inp['ebitda']), optional_ratio(inp['interest'], inp['ebit'])
    if lev1 is None or lev2 is None:
        warnings.append('historical_leverage_reference_unavailable')
    if (lev1 is not None and lev1 > LEV_DEBT_EBITDA) or (lev2 is not None and lev2 > LEV_INT_EBIT):
        errors.append('leverage gate triggered — ROIC branch required')
    if errors:
        warnings.append('historical_economic_guards_require_review')

    def band(dg):
        ll = inp['np_l'] / sh * recovery_two_stage_pe(g1, inp['n_rec_l'], inp['g2_m'] + dg, roe_mid, r) + cps
        return (ll, tier('m', inp['g2_m'] + dg)['anchor'], tier('h', inp['g2_h'] + dg)['anchor'])

    def at_ss(rs):
        gs = {t: print_match(op[t][2] * sh, r, aligned_solver(unb[t] / op[t][2], r, tau, y1, y2, rs))[1]
              for t in ('m', 'h')}
        if None in gs.values() or max(gs.values()) > min(.06, r - .04):
            return {'growth': gs, 'anchors': None}
        ll = inp['np_l'] / sh * recovery_two_stage_pe(g1, inp['n_rec_l'], gs['m'], roe_mid, r) + cps
        return {'growth': gs, 'anchors': dict(zip('LMH', (ll, tier('m', gs['m'], rs)['anchor'], tier('h', gs['h'], rs)['anchor'])))}

    as_band = lambda xs: dict(zip('LMH', xs))
    def optional_value(fn):
        def finite(value):
            if isinstance(value, dict):
                return all(finite(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return all(finite(item) for item in value)
            return not isinstance(value, (int, float)) or math.isfinite(value)
        try:
            result = fn()
            if finite(result):
                return result
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_sensitivity_unavailable')
        return None
    def optional_growth(delta):
        if r <= max(inp['g2_m'] + delta, inp['g2_h'] + delta):
            warnings.append('historical_sensitivity_unavailable')
            return None
        return optional_value(lambda: as_band(band(delta)))
    def growth_interval():
        lo, hi = inp['g2_h'], min(.06, r - 1e-9)
        if lo > hi:
            raise ValueError('no valid growth comparison interval')
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if tier('m', mid)['anchor'] < H else (lo, mid)
        return [inp['g2_h'], lo], [tier('m', inp['g2_h'])['anchor'], tier('m', lo)['anchor']]
    interval = optional_value(growth_interval)
    if interval is None:
        interval = (None, None)
    sensitivity = {'growth_minus_1pp': optional_growth(-.01), 'growth_plus_1pp': optional_growth(.01),
                   'steady_floor': optional_value(lambda: at_ss(inp['ronic_ss_floor'])),
                   'steady_fy2021_25': optional_value(lambda: at_ss(inp['ronic_own_2125'])),
                   'steady_fy2019_25': optional_value(lambda: at_ss(inp['ronic_own_1925'])),
                   'old_growth_steady_base': optional_value(lambda: {'M': tier('m', G2_PREV['m'], r_ss)['anchor'], 'H': tier('h', G2_PREV['h'], r_ss)['anchor']}),
                   'old_growth_steady_floor': optional_value(lambda: {'M': tier('m', G2_PREV['m'], inp['ronic_ss_floor'])['anchor'], 'H': tier('h', G2_PREV['h'], inp['ronic_ss_floor'])['anchor']}),
                   'm_low_numerator': (inp['cons_np28_l'] - c_inc) / sh * rows['m']['pe'] / disc + rows['m']['w'] + cps,
                   'h_historical_peak': inp['np_peak_own'] / sh * rows['h']['pe'] / disc + rows['h']['w'] + cps,
                   'midcycle_coordinate': inp['np_mid10'] / sh / r, 'trough_coordinate': inp['np_l'] / sh / r,
                   'fy2016_coordinate': inp['np_2016'] / sh / r, 'pb_floor': inp['bps'] * inp['pb_own_min'],
                   'flat_multiple': as_band(flat), 'growth_m_interval': interval[0],
                   'growth_m_interval_values': interval[1]}
    safe_pm = {t: {'rows': [(mo, pe, roe, g if math.isfinite(g) else None, ok) for mo, pe, roe, g, ok in pm[t][0]],
                   'median': pm[t][1]} for t in ('m', 'h')}
    a, b = cut_points(L, M, H)
    # L 低谷回归 Gordon；M/H 前瞻回报回落 Gordon。
    return {'ticker': '600031.SH', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-19',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b}, 'candidate': None, 'option': None,
            'review_flags': warnings,
            'segments': {'company': {'values': as_band((L, M, H))}},
            'key_parameters': {'method': {'L': 'gordon_trough_recovery', 'M': 'gordon_forward_return_fade', 'H': 'gordon_forward_return_fade'},
                               'discount_rate': dict.fromkeys('LMH', r),
                               'growth_rate': {'L': inp['g2_m'], 'M': inp['g2_m'], 'H': inp['g2_h']},
                               'forward_return': {'L': roe_mid, 'M': rows['m']['roe'], 'H': rows['h']['roe']},
                               'steady_return': {'L': roe_mid, 'M': min(rows['m']['roe'], r_ss), 'H': min(rows['h']['roe'], r_ss)},
                               'multiple': {'L': pe_l, 'M': rows['m']['pe'], 'H': rows['h']['pe']}},
            'operating': {'cash_total': c_tot, 'parent_ratio': pr, 'excess_cash': c_ex, 'cash_income': c_inc,
                          'cash_per_share': cps, 'operating_profit': op, 'unbooked': unb, 'matched': safe_pm,
                          'rows': rows, 'roe_mid': roe_mid, 'low_recovery_growth': g1, 'tail_payout_gap': tail_gap,
                          'middle_multiple': mult_m, 'leverage': [lev1, lev2]}, 'sensitivity': sensitivity}


def calculate(context):
    result = evaluate(dict(INPUTS))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'].append('historical_cash_uses_and_funding_unverified')
    constants = {'unit_scale': YI, 'numerator_year': NUM_YEAR, 'today_year': TODAY_FY,
                 'matching_band': PAIR_BAND, 'minimum_good_months': MIN_GOOD,
                 'leverage_debt_limit': LEV_DEBT_EBITDA, 'leverage_interest_limit': LEV_INT_EBIT,
                 'historical_growth': G2_PREV, 'historical_shares': SHARES_THEN,
                 'historical_excess_cash': CEX_THEN, 'historical_cash_yield': YIELD_THEN,
                 'historical_months': MONTHS}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed({'inputs': INPUTS, 'constants': constants}, BASELINE_LOCAL)
    return result
