#!/usr/bin/env python3
"""Historical Tianshan aluminium spread model, retained for migration review.

The old aluminium axis supplies three spreads, growth and a one-year high-price
period; a separate copper axis limits aluminium's upside. The two-point
gross-to-parent-profit bridge combines price and volume effects; the lower
2025H1 observation is a fit, not an independent forecast. Total aluminium
sales include both direct and internally processed product, so revenue from
the primary-aluminium segment alone is not an appropriate volume numerator.
Current model dates are not independently certified.
"""
from __future__ import annotations

import math

from lib.al_bridge import (REQUIRED, anchors, bridge, check_gordon,
                           check_regression, flat_ladder, multiples, pb_floor)
from lib.gordon import perpetual_pe
from lib.inputs import check_missing, ladder
from lib.metal_axis_checks import axis_basis_snapshot, check_aluminium_price_upside
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('al_bridge', 'axes', 'gordon', 'inputs', 'metal_axis_checks', 'partial_basis'),
                'axes': {'aluminium': 'fed_path_aluminium', 'gold_copper': 'fed_path_gold_copper'}}

INPUTS = {
    'shares': 46.29,  # 总股本（亿股）＝ LB static total_shares 4,628,737,415；与 `bps` 分母同源（旧值 45.9 由 H1 EPS 0.91 反推，已废）；2026-09-14
    'rev_m': 350.2,  # **M 档**年化营收 ＝ 2026H1 175.11 × 2；2026H1
    'gm_m': 0.3766,  # **M 档**毛利率；Longbridge 财报；2026H1
    'rev_ref': 306.6,  # **k 拟合点**年化营收 ＝ 2025H1 153.3 × 2（A3；不是 L）；2025H1
    'gm_ref': 0.2022,  # **k 拟合点**毛利率；Longbridge 财报五年序列；2025H1
    'np_m': 83.5,  # **M 档**年化归母 ＝ 2026H1 41.77 × 2；**回归护栏基准**；2026H1
    'np_ref': 41.6,  # **k 拟合点**年化归母 ＝ 2025H1 20.8 × 2（A3）；2025H1
    'vol_al': 128.0,  # 电解铝年化销量万吨 ＝ 中报合计总销量 64 × 2（A4）；三档冻结；2026H1
    'equity': 321.09,  # 归母权益（亿 CNY）＝ 中报「普通股权益总计」32,109,252,666 元（LB 财报 BS）；三档前瞻 ROE 的分母（属性 G）；2026-06-30
    'r_perp': 0.13,  # 永续贴现率 ＝ **篮 6 周期商品 / 小盘**（电解铝价差，A16；真源 `eval/lib/gordon.py BASKET_R`）；零增长 → PE 1/r = 7.69×；2026-09-20
    'pe_own_min': 7.22,  # 自身 5 年 TTM PE 月频实测低点（2025-04）；**护栏，不入主公式**（A13）；LB `valuation --history pe --range 5`；2026-09-11
    'pe_own_max': 19.6,  # 自身 5 年 TTM PE 月频实测高点（2023-07，盈利谷底）；**护栏，不入主公式**（A13）；2026-09-11
    'bps': 6.937,  # 每股净资产 CNY ＝ 报表值（`equity` 321.09 亿 ÷ 46.29 亿股；LB static 6.9369）；仅用于地板（A10），不入主公式；2026-06-30
    'pb_low': 0.95,  # 5 年 PB 低点（2024-02-05）；地板 ＝ pb_low × bps（A10，只披露）；2026-09-07
}

# Independent filing cross-checks from the original 2026H1 study, in CNY 100m.
# Update these observations together with the underlying inputs when researching
# a later filing; they are not inferred from the model's target result.
GROSS_PROFIT_FILING = 131.9
NET_PROFIT_FILING = 83.5
SHARES_STATIC = 46.29  # 2026-09-14 Longbridge static, 100m shares.
NP_TROUGH_2023H1 = 20.38  # 2023H1 parent earnings annualised, disclosure only.
PRIMARY_REVENUE_SHARE = .6874  # 2026H1 primary aluminium revenue share.
OWN_MEDIAN_3Y = 12.10  # Three-year repricing window, not adopted as a multiple.
BASELINE_LOCAL = '9625fa0e68961a22f3e846585d4cf38e2c47a0b81624ffc5d8f3049ecc8f361b'


def calculate(context):
    aluminium = context['axes']['aluminium']
    copper = context['axes']['gold_copper']
    inp = dict(INPUTS)
    for name in ('spread_l', 'spread_m', 'spread_h', 'g2_l', 'g2_m', 'g2_h', 'h_pass_years'):
        inp[name] = aluminium[name]
    errors = check_missing(inp, REQUIRED + ['h_pass_years'])
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in REQUIRED + ['h_pass_years']):
        raise ValueError('all required inputs must be finite')
    errors += ladder('smelting spread', inp['spread_l'], inp['spread_m'], inp['spread_h'])
    cross_axis_valid = check_aluminium_price_upside(aluminium_axis=aluminium, gold_copper_axis=copper)
    errors += check_regression(inp, GROSS_PROFIT_FILING, NET_PROFIT_FILING)
    p_al_m = aluminium['translated_price']['M']
    vol_direct = inp['rev_m']*PRIMARY_REVENUE_SHARE/(p_al_m/1e4)
    if inp['vol_al'] <= vol_direct:
        errors.append('aluminium volume excludes part of the processed products; reassess total sales')
    errors += check_gordon(inp, 6, shared_growth={tier: aluminium[f'g2_{tier.lower()}'] for tier in 'LMH'})
    if abs(inp['shares'] - SHARES_STATIC) > .05:
        errors.append('shares differ from the historical source; recheck the current share count')
    if aluminium['h_after'] != 'M' or aluminium['h_scope'] != 'aluminium_spread':
        errors.append('the high-spread return path is incompatible with this model')
    if errors:
        raise ValueError('; '.join(errors))

    (L, M, high_regime), eps = anchors(inp)
    pes, roes = multiples(inp)
    if max(pes) >= OWN_MEDIAN_3Y:
        errors.append('generated multiple reaches the historical repricing-window median; reassess')
    errors += flat_ladder(eps)
    n = inp['h_pass_years']
    H = M + (high_regime - M) * (1 - (1 + inp['r_perp']) ** -n)
    br = bridge(inp)
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors
    if not L < M < H:
        errors.append('L/M/H anchors are not strictly ordered')
    if errors:
        raise ValueError('; '.join(errors))
    tiers = lambda values: dict(zip('LMH', values))
    local = {'inputs': INPUTS, 'aluminium': axis_basis_snapshot(aluminium), 'gold_copper': axis_basis_snapshot(copper),
             'historical_checks': {'gross_profit_filing': GROSS_PROFIT_FILING,
                                   'net_profit_filing': NET_PROFIT_FILING,
                                   'shares_static': SHARES_STATIC, 'trough_2023h1': NP_TROUGH_2023H1,
                                   'primary_revenue_share': PRIMARY_REVENUE_SHARE, 'own_median_3y': OWN_MEDIAN_3Y}}
    return {
        'ticker': '002532.SZ', 'currency': 'CNY', 'valuation_as_of': None, 'framework_as_of': None,
        'historical_financial_statement_as_of': '2026-06-30', 'historical_research_as_of': '2026-10-07',
        'anchors': tiers((L,M,H)), 'candidate': None, 'option': None,
        'units': {'price': 'CNY_PER_SHARE'},
        'segments': {'company': {'unit': 'CNY_PER_SHARE', 'values': tiers((L,M,H))}},
        'key_parameters': {'discount_rate': {'unit': 'RATIO', 'values': tiers((inp['r_perp'],)*3)},
                           'growth_rate': {'unit': 'RATIO', 'values': tiers(inp[f'g2_{t}'] for t in 'lmh')},
                           'forward_return': {'unit': 'RATIO', 'values': tiers(roes)},
                           'steady_return': {'unit': 'RATIO', 'values': tiers((None,None,None))}},
        'basis_changed': None, 'partial_basis_changed': local_basis_changed(local, BASELINE_LOCAL),
        'review_flags': ['aluminium_low_macro_path_conflict'] + ([] if cross_axis_valid else ['aluminium_copper_price_upside_not_met']),
        'operating': {'net_profit': tiers(br['np']), 'gross_profit': tiers(br['gp']),
                      'roe': tiers(roes), 'multiple': tiers(pes), 'eps': tiers(eps),
                      'conversion': br['k'], 'high_regime_value': high_regime,
                      'floor': floor, 'fit_profit': inp['np_ref'], 'volume_from_primary_revenue': vol_direct,
                      'low_profit_ratio': br['np'][0] / br['np'][1], 'high_spread_years': n},
        'sensitivity': {'historical_fit_reference': inp['np_ref']/inp['shares']*pes[1],
                        'historical_trough': NP_TROUGH_2023H1/inp['shares']/inp['r_perp'],
                        'low_growth_iai': eps[0]*perpetual_pe(.033,roes[0],inp['r_perp']),
                        'flat_regime': tiers(e*pes[1] for e in eps)},
    }
