#!/usr/bin/env python3
"""Historical Zhongtian fiber-axis and operating-earnings model.

Amounts are CNY 100 million, shares 100 million, outputs CNY/share. The
shared optical-fiber axis remains the single reference for prices and its
stored rungs and history are checked against the original model snapshot.
Company report, forecast and axis sources remain in the framework and comments.

L is a glut regime and H a two-year excess window, not a perpetual peak.
Cash and investment are separately accounted for with parent-share interest
removed from earnings. The 1.36 AI volume multiplier is a conditional candidate
based on one source, not part of the adopted primary valuation or a probability.

Earlier document comparisons using a 2021 axis alternative, 2022–25 non-fiber
growth, payable-as-debt, interest-only cash and consensus-price ruler were
explicitly not recomputed after the 2026-10-16 basis correction. They remain
historical disclosure, not current calculated scenarios.
The original document also gave 11.51 / 13.47 / 16.48 when discounting the
fiber leg; this script did not calculate that comparison. Its H figure has
not been reconciled to the adopted zero-k basis, so it remains historical.
"""
from __future__ import annotations

import math

import numpy as np

from lib.gordon import basket_r, check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'),
                'axes': {'fiber': 'optical_fiber'}}
BASELINE_LOCAL = '5ad4a19632f4b1db25b55ac808271669768a4d165b36753f8058818938cf1a04'

INPUTS = {
    'shares': 34.1294965,  # 总股本（亿股）：2026 中报; as-of 2026-06-30
    'eq_h1': 384.45,  # 归母权益（亿元）：2026 中报; as-of 2026-06-30
    'cash_h1': 170.43,  # 货币资金（亿元）：2026 中报; as-of 2026-06-30
    'cash_restricted': 9.46,  # 受限资金（亿元）：2026 中报「保证金及资金冻结」; as-of 2026-06-30
    'debt_h1': 32.79,  # 有息负债 + 租赁（亿元）：短借 16.32 + 长借 11.18 + 一年内到期 3.83 + 租赁 1.47; as-of 2026-06-30
    'div_declared': 8.864,  # 已宣派未付股息（亿元，类债项，从净现金扣）：2026 中报「应付股利」886,410,083.52 元（≈ 2025 年度每股 0.26 元 × 股本）; as-of 2026-06-30
    'inv_h1': 31.48,  # 对外投资（亿元）：长期股权投资 21.65 + 其他权益工具 8.55 + 其他非流动金融资产 1.02 + 交易性 0.26; as-of 2026-06-30
    'r_perp': 0.10,  # 折现率：篮 4 常规经营：分部无资产数据退整公司尺，M 世界利润最大腿为电网（非商品价函数）；初分 13% 周期商品经同等盈利月份带降档（A6）; as-of 2026-10-13
    'g2': 0,  # 永续增速：留存去向审计 B 桶（A8），非同业反解; as-of 2026-10-13
    'payout_obs': 0.306,  # 实付派息率：2025 年度每股 0.26 元 ÷ EPS 0.850; as-of FY2025
    'k_l': 0,  # 视同派出打折 L：B 桶（A12）; as-of 2026-10-13
    'k_m': 0,  # 视同派出打折 M：B 桶（A12）; as-of 2026-10-13
    'k_h': 0,  # 视同派出打折 H：已去掉——k 只许乘具名交易，H 世界留存是多留部分，由 λ = 1 承担（A12）; as-of 2026-10-16
    'minority_h1': 9.839,  # 少数股东权益（亿元）：2026 中报；归母比例 = eq_h1 ÷ (eq_h1 + minority_h1) = 97.51%（A7）; as-of 2026-06-30
    'int_fy2025': 2.13,  # FY2025 利息收入（亿元，税前）：2025 年报；分子只剔归母那份（A7）; as-of FY2025
    'int_fy2024': 2.09,  # FY2024 利息收入（亿元，税前）：2024 年报；L 档同上; as-of FY2024
    'tau': 0.5,  # 时点对齐年数：现金行资产负债表日 2026-06-30 → 分子年初 2027-01-01（A14）; as-of 2026-06-30
    'cons26_mean': 65.32,  # FY2026E 归母共识均值（亿元）：东方财富 11 家 EPS 1.914 × 股本；窗口可分配利润用（A14）; as-of 2026-10-15
    'ni_h1_2026': 23.87,  # 2026H1 归母（亿元）：2026 中报；窗口 = FY2026E − 已入账（A14）; as-of 2026-06-30
    'ai_vol': 1.36,  # 候选带光纤销量结构系数：CRU AI 需求占比 5% → 30%（A9，单源）; as-of 2026-08-28
    'fib_gp_fy2016': 19.27,  # 光通信分部毛利（亿元）：2016 年报分产品（56.26 × 34.26%）; as-of FY2016
    'fib_gp_fy2017': 25.22,  # 同上：2017 年报（70.18 × 35.93%）; as-of FY2017
    'fib_gp_fy2018': 30.88,  # 同上：2018 年报（75.39 × 40.95%）; as-of FY2018
    'fib_gp_fy2019': 22.14,  # 同上：2019 年报（70.36 × 31.47%）; as-of FY2019
    'fib_gp_fy2020': 19.36,  # 同上：2020 年报（80.60 × 24.02%）; as-of FY2020
    'fib_gp_fy2021': 16.80,  # 同上：2021 年报（74.76 × 22.47%）; as-of FY2021
    'fib_gp_fy2022': 22.04,  # 同上：2022 年报（91.38 × 24.12%）; as-of FY2022
    'fib_gp_fy2023': 24.72,  # 同上：2023 年报（91.14 × 27.12%）; as-of FY2023
    'fib_gp_fy2024': 20.35,  # 同上：2024 年报（80.94 × 25.14%）; as-of FY2024
    'fib_gp_fy2025': 16.64,  # 同上：2025 年报（73.70 × 22.58%）; as-of FY2025
    'gp_fy2016': 34.58,  # 公司毛利（营业收入 − 营业成本，亿元）：2016 年报; as-of FY2016
    'gp_fy2017': 41.91,  # 同上：2017 年报; as-of FY2017
    'gp_fy2018': 49.78,  # 同上：2018 年报; as-of FY2018
    'gp_fy2019': 49.69,  # 同上：2019 年报; as-of FY2019
    'gp_fy2020': 58.49,  # 同上：2020 年报（修订版）; as-of FY2020
    'gp_fy2021': 73.91,  # 同上：2021 年报; as-of FY2021
    'gp_fy2022': 73.62,  # 同上：2022 年报; as-of FY2022
    'gp_fy2023': 73.08,  # 同上：2023 年报; as-of FY2023
    'gp_fy2024': 69.16,  # 同上：2024 年报; as-of FY2024
    'gp_fy2025': 72.85,  # 同上：2025 年报; as-of FY2025
    'ni_fy2016': 15.88,  # 归母净利（亿元）：2016 年报; as-of FY2016
    'ni_fy2017': 17.88,  # 同上：2017 年报; as-of FY2017
    'ni_fy2018': 21.22,  # 同上：2018 年报分季度合计; as-of FY2018
    'ni_fy2019': 19.60,  # 同上：2021 年报三年表; as-of FY2019
    'ni_fy2020': 22.75,  # 同上：2021 年报三年表（调整后）; as-of FY2020
    'ni_fy2022': 32.14,  # 同上：2022 年报; as-of FY2022
    'ni_fy2023': 31.17,  # 同上：2023 年报; as-of FY2023
    'ni_fy2024': 28.38,  # 同上：2024 年报; as-of FY2024
    'ni_fy2025': 29.02,  # 同上：2025 年报; as-of FY2025
    'nonop_fy2016': 3.87,  # 非经营项（利息收入 × 0.85 + 投资收益，亿元）：2016 年报（0.35 / 3.57）; as-of FY2016
    'nonop_fy2017': 3.85,  # 同上：2017 年报（0.44 / 3.48）; as-of FY2017
    'nonop_fy2018': 1.28,  # 同上：2018 年报（0.68 / 0.70）; as-of FY2018
    'nonop_fy2019': 0.75,  # 同上：2019 年报（0.68 / 0.17）; as-of FY2019
    'nonop_fy2020': 1.31,  # 同上：2020 年报（0.74 / 0.68）; as-of FY2020
    'nonop_fy2022': 2.44,  # 同上：2022 年报（1.07 / 1.53）; as-of FY2022
    'nonop_fy2023': 8.44,  # 同上：2023 年报（1.88 / 6.84）; as-of FY2023
    'nonop_fy2024': 6.48,  # 同上：2024 年报（2.09 / 4.71）; as-of FY2024
    'nonop_fy2025': 5.74,  # 同上：2025 年报（2.13 / 3.93）; as-of FY2025
    'cons27_lo': 67.79,  # FY2027E 归母下沿（亿元）：同花顺 10 家（招商）; as-of 2026-10-13
    'cons27_mean': 82.42,  # FY2027E 归母均值：同花顺 10 家; as-of 2026-10-13
    'cons27_hi': 110.89,  # FY2027E 归母上沿：华泰 2026-09-03; as-of 2026-10-13
    'cons28_mean': 94.04,  # FY2028E 归母均值：同花顺 9 家; as-of 2026-10-13
    'cons28_hi': 133.87,  # FY2028E 归母上沿：华泰 2026-09-03; as-of 2026-10-13
    'pe_same_min': 11.59,  # 同等盈利月份 TTM PE 最低：2024-01（TTM 归母 34.03 亿；月末收盘 × 股本 ÷ 当时可见 TTM）; as-of 2024-01-31
    'pe_same_n': 15,  # 同等盈利月份数：TTM 归母 30.3–38.6 亿（中枢分子 ±12%）：2023-08 – 2024-03、2026-04 – 2026-10; as-of 2026-10-13
    'pb_own_min': 1.16,  # 自身 PB 下沿：2018-10（月末收盘 7.30 ÷ 当时每股净资产 6.29）; as-of 2018-10-31
    'ebitda_fy25': 48.95,  # FY2025 EBITDA（亿元）：EBIT 34.99 + 折旧摊销 13.96; as-of FY2025
    'ebit_fy25': 34.99,  # FY2025 EBIT：yfinance; as-of FY2025
    'interest_fy25': 0.97,  # FY2025 利息支出：2025 年报财务费用; as-of FY2025
}

TIERS = ('l', 'm', 'h')
FIT_YEARS = range(2018, 2026)
RATIO_YEARS = (2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025)
REPLAY_TOL = .20

def fit_fiber_bridge(prices, profits):
    """Old 2018–25 price-to-profit linear fit; optional diagnostics may be unavailable."""
    x, yv = np.asarray(prices, dtype=float), np.asarray(profits, dtype=float)
    if len(x) != len(FIT_YEARS) or len(yv) != len(FIT_YEARS) or np.ptp(x) == 0:
        raise ValueError('fiber bridge needs eight distinct-year observations and varying prices')
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(yv)):
        raise ValueError('fiber bridge observations must be finite')
    b, a = np.polyfit(x, yv, 1)
    pred = a + b * x
    variation = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1 - float(((yv - pred) ** 2).sum()) / variation if variation else None
    if r2 is not None and not math.isfinite(r2):
        r2 = None
    replay = {year: (float(predicted / actual - 1) if actual else None)
              for year, predicted, actual in zip(FIT_YEARS, pred, yv)}
    if any(value is not None and not math.isfinite(value) for value in replay.values()):
        raise ValueError('fiber bridge replay is nonfinite')
    return float(a), float(b), r2, replay


def evaluate(inp):
    required = list(INPUTS) + [f'fiber_{t}' for t in TIERS] + [f'fiber_fy{y}' for y in FIT_YEARS]
    errors = check_missing(inp, required)
    if errors:
        raise ValueError('; '.join(errors))
    if any(isinstance(inp[k], bool) or not isinstance(inp[k], (int, float)) or not math.isfinite(inp[k]) for k in required):
        raise ValueError('all model inputs must be finite')
    if inp['r_perp'] <= 0 or inp['r_perp'] <= inp['g2']:
        raise ValueError('invalid discount or perpetual-growth domain')
    warnings = []
    errors += [f'probability-looking input {k}' for k in inp if k.startswith('p_')]
    m_window = float(np.mean([inp[f'fiber_fy{y}'] for y in FIT_YEARS]))
    if abs(m_window - inp['fiber_m']) > .05:
        errors.append('axis M differs from FY2018–25 mean')
    errors += check_r(inp['r_perp'], 'r_perp', 4)
    errors += check_g_cap(inp['g2'], inp['r_perp'], 'g2')
    if inp['shares'] <= 0 or inp['eq_h1'] + inp['minority_h1'] <= 0:
        raise ValueError('invalid shares or parent equity ratio denominator')
    if errors:
        warnings.append('historical_axis_or_input_guards_require_review')
        errors = []

    ratio = {y: (inp[f'ni_fy{y}'] - inp[f'nonop_fy{y}']) / inp[f'gp_fy{y}'] for y in RATIO_YEARS}
    ratio[2021] = (ratio[2019] + ratio[2020] + ratio[2022]) / 3
    fib = {y: inp[f'fib_gp_fy{y}'] * ratio[y] for y in range(2016, 2026)}
    a, b, r2, replay = fit_fiber_bridge([inp[f'fiber_fy{y}'] for y in FIT_YEARS],
                                        [fib[y] for y in FIT_YEARS])
    if r2 is None:
        warnings.append('historical_fiber_fit_quality_unavailable')
    if sum(e is not None and abs(e) <= REPLAY_TOL for e in replay.values()) < 2:
        warnings.append('historical_fiber_bridge_replay_requires_review')
    fiber = {t: a + b * inp[f'fiber_{t}'] for t in TIERS}
    self_mid = float(np.mean([fib[y] for y in range(2016, 2026)]))

    r, sh = inp['r_perp'], inp['shares']
    netcash = inp['cash_h1'] - inp['cash_restricted'] - inp['debt_h1'] - inp['div_declared']
    pr = inp['eq_h1'] / (inp['eq_h1'] + inp['minority_h1'])
    cash_inv = netcash * pr + inp['inv_h1']
    op_eq = inp['eq_h1'] - (netcash + inp['inv_h1'])
    if op_eq == 0:
        raise ValueError('operating-equity denominator is zero')
    int_minor25 = (1 - pr) * inp['int_fy2025'] * .85
    nonop = inp['nonop_fy2025'] - int_minor25
    nf25 = inp['ni_fy2025'] - nonop - fib[2025]
    g_nf = ((inp['gp_fy2025'] - inp['fib_gp_fy2025']) / (inp['gp_fy2023'] - inp['fib_gp_fy2023'])) ** .5 - 1
    nf = {2027: nf25 * (1 + g_nf) ** 2, 2028: nf25 * (1 + g_nf) ** 3}
    nf_l = inp['ni_fy2024'] - (inp['nonop_fy2024'] - (1 - pr) * inp['int_fy2024'] * .85) - fib[2024]
    g2, tau = inp['g2'], inp['tau']
    win = max(0, inp['cons26_mean'] - inp['ni_h1_2026'] - .5 * inp['nonop_fy2025']) / sh

    def anchors(rr, vol=1.0, growth=g2):
        # The axis regime leg is timeless, while dated non-fiber earnings and
        # the two-year high-scenario excess are discounted back by tau.
        f = {t: fiber[t] * vol for t in TIERS}
        d = (1 + rr) ** -tau
        w = win * (1 + rr) ** -(tau / 2)
        e_m, e_l = nf[2027] + f['m'], nf_l + f['l']
        roe_m, roe_l = e_m / op_eq, e_l / op_eq
        pe_m, pe_l = perpetual_pe(growth, roe_m, rr), perpetual_pe(growth, roe_l, rr)
        v_m = f['m'] * pe_m + nf[2027] * pe_m * d + cash_inv
        v_l = f['l'] * pe_l + nf_l * pe_l * d + cash_inv
        ex = {2027: inp['cons27_hi'] - nonop - nf[2027] - f['m'],
              2028: inp['cons28_hi'] - nonop - nf[2028] - f['m']}
        pv_ex = (ex[2027] / (1 + rr) + ex[2028] / (1 + rr) ** 2) * d
        h_pre = (v_m + pv_ex) / sh + w
        deemed_h = (1 - inp['payout_obs']) * (inp['cons27_hi'] + inp['cons28_hi']) / sh
        low_point = high_regime = None
        try:
            if e_l == 0 or e_m / e_l <= 0:
                raise ValueError('invalid recovery-growth comparison')
            g1 = (e_m / e_l) ** .5 - 1
            low_point = (e_l * recovery_two_stage_pe(g1, 2, growth, roe_m, rr) + cash_inv) / sh
            if not math.isfinite(low_point):
                raise ValueError('nonfinite low-point reference')
        except (ArithmeticError, TypeError, ValueError):
            low_point = None
            warnings.append('historical_low_recovery_comparison_unavailable')
        try:
            high_regime = ((inp['cons27_hi'] - nonop) * perpetual_pe(
                growth, (inp['cons27_hi'] - nonop) / op_eq, rr) + cash_inv) / sh
            if not math.isfinite(high_regime):
                raise ValueError('nonfinite high-regime reference')
        except (ArithmeticError, TypeError, ValueError):
            high_regime = None
            warnings.append('historical_high_regime_comparison_unavailable')
        return {'L': v_l / sh + w, 'M': v_m / sh + w, 'H_pre': h_pre, 'H': h_pre - inp['k_h'] * deemed_h,
                'deemed_h': deemed_h, 'e_m': e_m, 'e_l': e_l, 'roe_m': roe_m, 'roe_l': roe_l,
                'ex27': ex[2027], 'ex28': ex[2028],
                'L_point': low_point, 'H_regime': high_regime}

    base = anchors(r)
    L, M, H = (base[t] for t in 'LMH')
    if not all(math.isfinite(value) for value in (L, M, H)) or not L < M < H:
        raise ValueError('base valuation tiers must be finite and ordered')
    eps = {'l': (base['e_l'] + nonop) / sh, 'm': (base['e_m'] + nonop) / sh, 'h': inp['cons27_hi'] / sh}
    errors += ladder('eps', eps['l'], eps['m'], eps['h'])
    if not (0 <= inp['k_l'] <= inp['k_m'] <= inp['k_h'] <= 1):
        errors.append('k ladder invalid')
    if any(inp[k] != 0 for k in ('k_l', 'k_m', 'k_h')):
        errors.append('k must be zero without a named transaction')
    pe_m_equiv = M / eps['m'] if eps['m'] else None
    if pe_m_equiv is None:
        warnings.append('historical_pe_comparison_unavailable')
    elif pe_m_equiv < inp['pe_same_min']:
        errors.append('M equivalent PE below same-earnings band')
    c27 = inp['cons27_mean'] / sh
    if not (eps['m'] <= c27 <= eps['h']):
        errors.append('FY2027 mean outside M to H')
    errors += ladder('flat', L, M, H)
    try:
        contrast13 = anchors(basket_r(6))
        if not all(math.isfinite(contrast13[tier]) for tier in 'LMH'):
            raise ValueError('nonfinite basket comparison')
    except (ArithmeticError, TypeError, ValueError):
        contrast13 = None
        warnings.append('historical_basket_comparison_unavailable')
    if contrast13 is not None and eps['m'] and contrast13['M'] / eps['m'] >= inp['pe_same_min']:
        errors.append('initial basket no longer fails history band; downgrade record needs review')
    try:
        cand = anchors(r, inp['ai_vol'])
        if not all(math.isfinite(cand[tier]) for tier in 'LMH') or not cand['L'] < cand['M'] < cand['H']:
            raise ValueError('candidate valuation is not finite and ordered')
    except (ArithmeticError, TypeError, ValueError):
        cand = None
        warnings.append('historical_candidate_unavailable')
    if errors:
        warnings.append('historical_economic_guards_require_review')
    a_cut, b_cut = cut_points(L, M, H)
    ca, cb = cut_points(cand['L'], cand['M'], cand['H']) if cand is not None else (None, None)
    as_band = lambda x: {tier: x[tier] for tier in 'LMH'}
    def optional_growth(growth):
        try:
            if growth >= r:
                raise ValueError('invalid growth sensitivity')
            result = anchors(r, growth=growth)
            if all(math.isfinite(result[tier]) for tier in 'LMH'):
                return as_band(result)
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_growth_sensitivity_unavailable')
        return None
    def optional_ratio(numerator, denominator):
        try:
            value = numerator / denominator
            if math.isfinite(value):
                return value
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_leverage_comparison_unavailable')
        return None
    debt_ratio = optional_ratio(-netcash, inp['ebitda_fy25'])
    interest_ratio = optional_ratio(inp['interest_fy25'], inp['ebit_fy25'])
    # Historical sources include a 2026-06-30 balance-sheet date and a
    # 2026-10-16 study date; neither certifies the current model basis.
    return {'ticker': '600522.SH', 'currency': 'CNY',
            'valuation_as_of': None, 'framework_as_of': None,
            'anchors': as_band(base), 'cut_points': {'A': a_cut, 'B': b_cut},
            'candidate': ({'label': 'AI 销量结构', 'anchors': as_band(cand), 'cut_points': {'A': ca, 'B': cb}}
                          if cand is not None else {'label': 'AI 销量结构', 'status': 'unavailable', 'anchors': None}),
            'option': None, 'segments': {'company': {'values': as_band(base)}},
            'review_flags': warnings,
            'key_parameters': {'method': {'L': 'fiber_glut_and_nonfiber', 'M': 'fiber_midcycle_and_nonfiber', 'H': 'midcycle_plus_two_year_excess'},
                               'discount_rate': dict.fromkeys('LMH', r), 'growth_rate': dict.fromkeys('LMH', g2),
                               'forward_return': {'L': base['roe_l'], 'M': base['roe_m'], 'H': None},
                               'steady_return': dict.fromkeys('LMH', None)},
            'operating': {'bridge_intercept': float(a), 'bridge_slope': float(b), 'r2': r2, 'replay': replay,
                          'fiber': fiber, 'fiber_historical_mean': self_mid, 'nf25': nf25, 'nf_growth': g_nf,
                          'nf': nf, 'nf_l': nf_l, 'netcash': netcash, 'parent_ratio': pr, 'cash_and_investments': cash_inv,
                          'operating_equity': op_eq, 'window_per_share': win, 'nonoperating': nonop,
                          'base': base, 'eps': eps},
            'sensitivity': {'basket_6': as_band(contrast13) if contrast13 is not None else None,
                            'growth_minus_1pp': optional_growth(g2 - .01),
                            'growth_plus_1pp': optional_growth(g2 + .01),
                            'low_recovery_point': base['L_point'], 'high_perpetual_regime': base['H_regime'],
                            'asset_coordinate': inp['eq_h1'] / sh * inp['pb_own_min'],
                            'leverage': [debt_ratio, interest_ratio]}}


def calculate(context):
    shared = context['axes']['fiber']['stock_fields']
    selected = {key: shared[key] for key in ([f'fiber_{t}' for t in TIERS]
                                             + [f'fiber_fy{year}' for year in FIT_YEARS])}
    result = evaluate({**INPUTS, **selected})
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['historical_financial_statement_as_of'] = '2026-06-30'
    result['historical_research_as_of'] = '2026-10-16'
    result['review_flags'].extend(['historical_fiber_series_thin_years',
                                   'historical_ai_mix_and_funding_unverified'])
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'fiber': selected, 'tiers': TIERS, 'fit_years': list(FIT_YEARS),
         'ratio_years': RATIO_YEARS, 'replay_tolerance': REPLAY_TOL}, BASELINE_LOCAL)
    return result
