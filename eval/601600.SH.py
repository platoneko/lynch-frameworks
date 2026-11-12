#!/usr/bin/env python3
"""Historical Chalco aluminium spread model, retained for migration review.

The old aluminium axis supplies three spreads, growth and a one-year high-price
period; a separate copper axis limits aluminium's upside. The two-point
gross-to-parent-profit bridge includes changes in subsidiary minority claims.
The 2025H1 observation is a fit, not an independent forecast. Current model
dates are not independently certified.
"""
from __future__ import annotations

import math

from lib.al_bridge import (REQUIRED, anchors, bridge, check_gordon,
                           check_regression, flat_ladder, multiples, pb_floor)
from lib.gordon import basket_r
from lib.inputs import check_missing, ladder
from lib.metal_axis_checks import axis_basis_snapshot, check_aluminium_price_upside
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('al_bridge', 'axes', 'gordon', 'inputs', 'metal_axis_checks', 'partial_basis'),
                'axes': {'aluminium': 'fed_path_aluminium', 'gold_copper': 'fed_path_gold_copper'}}

INPUTS = {
    'shares': 171.55,  # 总股本（亿股）＝ LB static total_shares 17,154,971,327；与 `bps` 分母同源（旧值 171.3 由 H1 EPS 0.693 反推，已废）；2026-09-14
    'rev_m': 2487.9,  # **M 档**年化营收 ＝ 2026 前三季度 1,865.94 × 4/3（2026 年第三季度报告）；2026Q3
    'gm_m': 0.269,  # **M 档**毛利率 ＝ 1 − 营业成本 1,363.97 ÷ 营收 1,865.94（2026 前三季度，三季报合并利润表）；2026H1 0.2673；2026Q3
    'rev_ref': 2328.2,  # **k 拟合点**年化营收 ＝ 2025H1 1,164.1 × 2（A3；不是 L）；2025H1
    'gm_ref': 0.1632,  # **k 拟合点**毛利率；Longbridge 财报五年序列；2025H1
    'np_m': 238.9,  # **M 档**年化归母 ＝ 2026 前三季度 179.16 × 4/3（三季报；Q3 单季 60.44 ×4 = 241.8）；**回归护栏基准**；2026Q3
    'np_ref': 141.0,  # **k 拟合点**年化归母 ＝ 2025H1 70.5 × 2（A3）；2025H1
    'vol_al': 753.3,  # 电解铝等效年化销量万吨 ＝ 原铝分部**绝对值**年化 1,818.6 亿（909.31 × 2）÷ 24,141 元/吨（A4）；三档冻结；2026H1
    'equity': 857.98,  # 归母权益（亿 CNY）＝ 三季报「归属于母公司股东权益合计」85,797,989 千元；三档前瞻 ROE 的分母（属性 G）；2026-09-30
    'r_perp': 0.11,  # 永续贴现率 ＝ **篮 5 大行 / 优质股份行**（只借 r 值：市场证据、③出带降篮门；初分篮 6 周期商品 13% 下 1/r 7.69× 出自身带，A15；真源 `eval/lib/gordon.py BASKET_R`）；零增长 → PE 1/r = 9.09× ∈ 自身带 [8.01, 35.71]；初分 13% 只作「对照坐标（降篮门路径）」；2026-09-20
    'pe_own_min': 8.01,  # 自身 5 年 TTM PE 月频实测低点（2025-04）；**护栏，不入主公式**（A12）；LB `valuation --history pe --range 5`；2026-09-11
    'pe_own_max': 35.71,  # 自身 5 年 TTM PE 月频实测高点（2023-07，盈利谷底）；**护栏，不入主公式**（A12）；2026-09-11
    'bps': 5.001,  # 每股净资产 CNY ＝ 报表值（`equity` 857.98 亿 ÷ 171.55 亿股，三季报股本 17,154,759 千股）；仅用于地板与 A9 的 PB 交叉，不入主公式；2026-09-30
    'pb_low': 1.04,  # LB 5 年 PB 合理区间下沿（实测月频最低 0.85，2022-10）；地板 ＝ pb_low × bps（A9），只披露；2026-09-11
}

# Independent filing cross-checks from the 2026 first nine months, annualised.
# Update these observations together with the underlying inputs when researching
# a later filing; they are not inferred from the model's target result.
GROSS_PROFIT_FILING = 669.3
NET_PROFIT_FILING = 238.9
SHARES_STATIC = 171.55  # 2026-09-14 Longbridge static, 100m shares.
NP_TROUGH_2023H1 = 67.33  # 2023H1 parent earnings annualised, disclosure only.
MINORITY_CONVERSION_CEILING = .50
BASELINE_LOCAL = 'f843e8e58e5027cc8897d5960ef701e764259b2a16e05584dbb5b20bab4e1fa1'


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
    errors += check_gordon(inp, 5, shared_growth={tier: aluminium[f'g2_{tier.lower()}'] for tier in 'LMH'})
    if 1/basket_r(6) >= inp['pe_own_min']:
        errors.append('initial basket multiple no longer falls below the historical band; reassess basket choice')
    if abs(inp['shares'] - SHARES_STATIC) > .05:
        errors.append('shares differ from the historical source; recheck the current share count')
    if aluminium['h_after'] != 'M' or aluminium['h_scope'] != 'aluminium_spread':
        errors.append('the high-spread return path is incompatible with this model')
    if errors:
        raise ValueError('; '.join(errors))

    (L, M, high_regime), eps = anchors(inp)
    pes, roes = multiples(inp)
    errors += flat_ladder(eps)
    n = inp['h_pass_years']
    H = M + (high_regime - M) * (1 - (1 + inp['r_perp']) ** -n)
    br = bridge(inp)
    if br['k'] >= MINORITY_CONVERSION_CEILING:
        errors.append('gross-to-parent-profit conversion no longer reflects the minority claim; reassess')
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors
    if not L < M < H:
        errors.append('L/M/H anchors are not strictly ordered')
    if errors:
        raise ValueError('; '.join(errors))
    tiers = lambda values: dict(zip('LMH', values))
    local = {'inputs': INPUTS, 'aluminium': axis_basis_snapshot(aluminium), 'gold_copper': axis_basis_snapshot(copper),
             'historical_checks': {'gross_profit_filing': GROSS_PROFIT_FILING,
                                   'net_profit_filing': NET_PROFIT_FILING, 'shares_static': SHARES_STATIC,
                                   'trough_2023h1': NP_TROUGH_2023H1,
                                   'minority_conversion_ceiling': MINORITY_CONVERSION_CEILING}}
    return {
        'ticker': '601600.SH', 'currency': 'CNY', 'valuation_as_of': None, 'framework_as_of': None,
        'historical_financial_statement_as_of': '2026-09-30', 'historical_research_as_of': '2026-10-30',
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
                      'floor': floor, 'fit_profit': inp['np_ref'], 'high_spread_years': n},
        'sensitivity': {'historical_fit_reference': inp['np_ref']/inp['shares']*pes[1],
                        'historical_trough': NP_TROUGH_2023H1/inp['shares']/inp['r_perp'],
                        'flat_regime': tiers(e*pes[1] for e in eps)},
    }
