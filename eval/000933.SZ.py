#!/usr/bin/env python3
"""Historical Shenhuo aluminium spread model, retained for migration review.

The old aluminium axis supplies three spreads, growth and a one-year high-price
period; a separate copper axis limits aluminium's upside. The lower-tier
profit still contains unseparated coal/trading earnings, not measured coal at
the middle tier. The two-point gross-to-parent-profit bridge mixes aluminium,
coal and alumina effects; the lower observed 2025H1 point remains its fit,
not a standalone forecast. Current model dates are not independently certified.
"""
from __future__ import annotations

import hashlib
import json
import math

from lib.al_bridge import (REQUIRED, anchors, bridge, check_gordon,
                           check_regression, flat_ladder, multiples, pb_floor)
from lib.inputs import check_missing, ladder
from lib.metal_axis_checks import axis_basis_snapshot, check_aluminium_price_upside

DEPENDENCIES = {'libraries': ('al_bridge', 'axes', 'gordon', 'inputs', 'metal_axis_checks'),
                'axes': {'aluminium': 'fed_path_aluminium', 'gold_copper': 'fed_path_gold_copper'}}

INPUTS = {
    'shares': 22.49,  # 总股本（亿股）＝ LB static total_shares 2,249,004,399；与 `bps` 分母同源（旧值 22.1 由 H1 EPS 2.16 反推，已废，A14 (d)）；2026-09-14
    'rev_m': 495.8,  # **M 档**年化营收 ＝ 2026H1 247.91 × 2；2026H1
    'gm_m': 0.3617,  # **M 档**毛利率；Longbridge 财报；2026H1
    'rev_ref': 408.6,  # **k 拟合点**年化营收 ＝ 2025H1 204.3 × 2（A3；不是 L）；2025H1
    'gm_ref': 0.1986,  # **k 拟合点**毛利率；Longbridge 财报五年序列；2025H1
    'np_m': 95.6,  # **M 档**年化归母 ＝ 2026H1 47.81 × 2；**回归护栏基准**；2026H1
    'np_ref': 38.0,  # **k 拟合点**年化归母 ＝ 2025H1 19.0 × 2（A3，五年 H1 最低；作 `deep_discount` 参照）；2025H1
    'vol_al': 151.9,  # 电解铝等效年化销量万吨 ＝ 电解铝事业部**绝对值**年化 366.8 亿（183.41 × 2）÷ 24,141 元/吨（A5）；三档冻结；2026H1
    'equity': 276.79,  # 归母权益（亿 CNY）＝ 中报「普通股权益总计」27,679,232,677 元（LB 财报 BS）；三档前瞻 ROE 的分母（属性 G）；2026-06-30
    'r_perp': 0.13,  # 永续贴现率 ＝ **篮 6 周期商品 / 小盘**（电解铝 + 煤，A16；真源 `eval/lib/gordon.py BASKET_R`）；零增长 → PE 1/r = 7.69×；2026-09-20
    'pe_own_min': 4.03,  # 自身 5 年 TTM PE 月频实测低点（2023-05）；**护栏，不入主公式**（A13）；LB `valuation --history pe --range 5`；2026-09-11
    'pe_own_max': 17.45,  # 自身 5 年 TTM PE 月频实测高点（2026-03）；**护栏，不入主公式**（A13）；2026-09-11
    'bps': 12.307,  # 每股净资产 CNY ＝ 报表值（`equity` 276.79 亿 ÷ 22.49 亿股；LB static 12.3073）；仅用于地板（A10）与 A14 交叉，不入主公式；2026-06-30
    'pb_low': 1.24,  # 5 年 PB 低点（2023-06-26）；地板 ＝ pb_low × bps（A10）；2026-09-07
}

# Independent filing cross-checks from the original 2026H1 study, in CNY 100m.
# Update these observations together with the underlying inputs when researching
# a later filing; they are not inferred from the model's target result.
GROSS_PROFIT_FILING = 179.3
NET_PROFIT_FILING = 95.6
SHARES_STATIC = 22.49  # 2026-09-14 Longbridge static, 100m shares.
NP_TROUGH_2023H1 = 54.78  # 2023H1 parent earnings annualised, disclosure only.
# Historical 2025H1→2026H1 gross-profit bridge in CNY 100m: 98.2 increase
# less 59.5 aluminium-price effect and 22.4 alumina-cost effect. The 16.3
# residual also includes other costs; it is not measured coal-segment profit.
COAL_AND_OTHER_GROSS_RESIDUAL = 16.3
# Local input and axis snapshot only, not formula provenance or confirmation.
BASELINE_FINGERPRINT = 'ac6b4e1d034cf19fc6b2789e377cacedc79b7383915047bd647a3919ceaf9337'


def calculate(context):
    aluminium = context['axes']['aluminium']
    copper = context['axes']['gold_copper']
    # Shared tiers, growth and duration come from one bound axis snapshot.
    # The old bridge fitted these inputs against 2025H1 and 2026H1 combined
    # group profit, so it cannot be read as a measured standalone coal profit.
    inp = dict(INPUTS)
    for name in ('spread_l', 'spread_m', 'spread_h', 'g2_l', 'g2_m', 'g2_h', 'h_pass_years'):
        inp[name] = aluminium[name]
    errors = check_missing(inp, REQUIRED + ['h_pass_years'])
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in REQUIRED + ['h_pass_years']):
        raise ValueError('all required inputs must be finite')
    errors += ladder('smelting spread', inp['spread_l'], inp['spread_m'], inp['spread_h'])
    # This compares full SHFE aluminium prices with LME copper prices; the
    # dimensionless ratios are comparable, unlike spread vs price levels.
    cross_axis_valid = check_aluminium_price_upside(aluminium_axis=aluminium, gold_copper_axis=copper)
    errors += check_regression(inp, GROSS_PROFIT_FILING, NET_PROFIT_FILING)
    errors += check_gordon(inp, 6, shared_growth={tier: aluminium[f'g2_{tier.lower()}'] for tier in 'LMH'})
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
    if inp['np_ref'] >= br['np'][0]:
        errors.append('fit year is no longer worse than the low scenario; reassess the fitting point')
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors
    if not L < M < H:
        errors.append('L/M/H anchors are not strictly ordered')
    if errors:
        raise ValueError('; '.join(errors))
    tiers = lambda values: dict(zip('LMH', values))
    # These constants are historical source observations: the filing guards
    # influence validity and the trough is returned as a pressure coordinate.
    historical_checks = {'gross_profit_filing': GROSS_PROFIT_FILING, 'net_profit_filing': NET_PROFIT_FILING,
                         'shares_static': SHARES_STATIC, 'np_trough_2023h1': NP_TROUGH_2023H1,
                         'coal_and_other_gross_residual': COAL_AND_OTHER_GROSS_RESIDUAL}
    fingerprint = hashlib.sha256(json.dumps({'inputs': INPUTS, 'axis': axis_basis_snapshot(aluminium), 'copper': axis_basis_snapshot(copper),
                                             'historical_checks': historical_checks},
                                            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return {
        'ticker': '000933.SZ', 'currency': 'CNY', 'valuation_as_of': None, 'framework_as_of': None,
        'historical_financial_statement_as_of': '2026-06-30',
        'historical_research_as_of': '2026-10-16',
        'anchors': tiers((L,M,H)), 'candidate': None, 'option': None,
        'units': {'price': 'CNY_PER_SHARE'},
        'segments': {'company': {'unit': 'CNY_PER_SHARE', 'values': tiers((L,M,H))}},
        'key_parameters': {'discount_rate': {'unit': 'RATIO', 'values': tiers((inp['r_perp'],)*3)},
                           'growth_rate': {'unit': 'RATIO', 'values': tiers(inp[f'g2_{t}'] for t in 'lmh')},
                           'forward_return': {'unit': 'RATIO', 'values': tiers(roes)},
                           'steady_return': {'unit': 'RATIO', 'values': tiers((None,None,None))}},
        'basis_changed': None, 'partial_basis_changed': fingerprint != BASELINE_FINGERPRINT,
        'review_flags': (['aluminium_low_macro_path_conflict']
                         + ([] if cross_axis_valid else ['aluminium_copper_price_upside_not_met'])),
        'operating': {'net_profit': tiers(br['np']), 'gross_profit': tiers(br['gp']),
                      'roe': tiers(roes), 'multiple': tiers(pes), 'eps': tiers(eps),
                      'conversion': br['k'], 'high_regime_value': high_regime, 'high_spread_years': n,
                      'floor': floor, 'fit_profit': inp['np_ref']},
        'sensitivity': {'coal_alumina_reference': inp['np_ref']/inp['shares']*pes[1],
                        'coal_residual_illustration': (br['np'][0]-COAL_AND_OTHER_GROSS_RESIDUAL*br['k'])/inp['shares']*pes[1],
                        'historical_trough': NP_TROUGH_2023H1/inp['shares']/inp['r_perp'],
                        'flat_regime': tiers(e*pes[1] for e in eps)},
    }
