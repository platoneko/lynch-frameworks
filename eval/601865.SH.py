#!/usr/bin/env python3
"""FLAT's historical conditional holding-period scenarios, not validated fair values.

The user requested saving the scenarios after their evidence gaps were disclosed.
Amounts are CNY 100 million, shares 100 million, area 100 million m².
Sources: https://static.cninfo.com.cn/finalpage/2026-03-27/1225035597.PDF
https://static.cninfo.com.cn/finalpage/2026-08-26/1225505691.PDF
https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1030/2026103001326_c.pdf
Historical sources and unverified financial judgments remain in the document.
"""
# Historical evidence retained from the document:
# The 2025 production 11.87 and sales 11.62 hundred-million m², at 70.69%
# utilization, imply about 16.79 hundred-million m² annualized capacity;
# it does not establish future utilization or demand. The 2021 annual report
# describes Q1 shortages followed by a Q2 supply-driven price fall. The 2020
# reported gross margin 49.41% is not a strictly comparable peak because its
# later comparative figure differs; the model does not use it as one.
# The 2023-04–09 raw PE 27.5–37.6 included announced capacity not yet in
# earnings. It does not validate 12x or justify a rate reduction. A July 2026
# HSBC H-share 2028 PE 12.7 lacks a complete A-share earnings/currency bridge;
# CICC 2026-11-05 FY2027 profit forecast of 4.3 CNY 100 million is distinct
# from the later successful-clearing assumptions, not corroboration of them.
# Candidate promotion requires two independent A-share models with compatible
# volume, margin and matched-earnings exit PE; two quarters of volume, margin
# and inventory evidence; sufficient post-sale duration with idle lines not
# materially returning; and a reconciled funding gap and convertible dilution.
# The 2025 intended payout of 35.64% is a historical annual figure, not the
# model's 0–30% cumulative dividend as a share of one year's earnings.
import math
from lib.gordon import check_r
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = '5ace80e9afd53ca4b589445978eab99d774f6c7e6458d4ff187bf389a032ce39'

# These are study conditions, not independent forecasts. The 2028-11 sale
# assumes the following 12 months of earnings can be sustained; neither the
# duration nor the 12x exit PE has two-source support. The user explicitly
# accepted saving those gaps on 2026-11-08, not their factual verification.
# PE already reflects existing leverage. The financing gap and conversion
# dilution remain unverified; the contracted capex is not the net gap.
# The 15.5 / 7 shortage case changes only the candidate high, not primary M.
INPUTS = {
    'shares_yi': 23.42743261,  # 总股本折亿股；Longbridge静态股本，沿用已查询值; as-of 2026-11-07
    'tax': 0.15,  # 所得税率条件；非统一实际税率; as-of 2026-11-08
    'minority_profit': 0,  # 少数损益近似假设；2025实测0.12034762亿，仅作误差披露; as-of 2026-11-08
    'r_hold': 0.13,  # 篮 6：光伏玻璃盈利主要受市场价差驱动；初分篮，尚未通过历史倍数净化认证; as-of 2026-11-08
    'hold_years': 2,  # 从研究基准2026-11-08到假设卖出日2028-11-08；约两年; as-of 2026-11-08
    'exit_pe': 12,  # 卖出时未来12个月盈利倍数的条件坐标，非实证中位; as-of 2026-11-08
    'pe_low': 10,  # 退出估值敏感性低端，非已验证下沿; as-of 2026-11-08
    'pe_high': 14,  # 退出估值敏感性高端，非已验证上沿; as-of 2026-11-08
    'pe_stress': 8,  # 额外倍数压力坐标，非历史底部认证; as-of 2026-11-08
    'dividend_fraction': 0.30,  # 累计窗口股息相当于一年EPS的比例上端；非每年分红率; as-of 2026-11-08
    'payout_ref': 0.3564,  # 2025年度拟现金分红比例，只供年度股息对照; as-of 2026-03-27
    'h1_pv_rev': 58.6159464896,  # 2026H1光伏分部收入；中报分部附注; as-of 2026-06-30
    'h1_pv_cost': 54.6716211732,  # 同期光伏分部成本; as-of 2026-06-30
    'h1_pbt': -4.2772688482,  # 同期合并利润总额; as-of 2026-06-30
    'v2025': 11.617581,  # 2025光伏销售面积; as-of 2025-12-31
    'rev2025': 139.8609,  # 2025光伏收入; as-of 2025-12-31
    'cost_2025': 117.3290,  # 2025光伏成本，含生产折旧; as-of 2025-12-31
    'volume_l': 13.5,  # 温和恢复销量条件; as-of 2026-11-08
    'volume_m': 14.5,  # 充分出清销量条件（主 H）; as-of 2026-11-08
    'volume_h': 15.5,  # 仅候选 H′ 的强短缺销量条件，非产能即需求; as-of 2026-11-08
    'margin_l': 3,  # 温和恢复单位毛利条件; as-of 2026-11-08
    'margin_m': 5,  # 充分出清单位毛利条件（主 H）; as-of 2026-11-08
    'margin_h': 7,  # 仅候选 H′ 的强短缺单位毛利条件; as-of 2026-11-08
    'volume_normal': 14.5,  # 主 M 正常修复销量条件，沿用原中档销量，不加额外份额; as-of 2026-11-08
    'margin_normal': 4,  # 主 M 正常修复单位毛利条件，沿用原调研已有4元条件；无新增共识背书; as-of 2026-11-08
    'equity': 211.9781166397,  # 2026Q3归母权益; as-of 2026-09-30
    'net_debt': 102.6334234845,  # 原研究现金等价物与有息负债/租赁合计口径；只用于资本/杠杆对照，不再从归母PE重复扣; as-of 2026-09-30
    'capital_proxy': 316.0252573074,  # 归母权益+少数权益+净债，旧新增回报代理分母; as-of 2026-09-30
    'interest2025': 5.1468830956,  # 2025合并利息费用; as-of 2025-12-31
    'cfo2025': 29.1111395632,  # 2025经营现金净流入; as-of 2025-12-31
    'capex2025': 28.7953778150,  # 2025购建固定/无形及其他长期资产现金; as-of 2025-12-31
    'capex_commit': 40.7558351438,  # 已签约未确认购建承诺，不直接作为净缺口; as-of 2026-06-30
    'legacy_g': 0.02,  # 旧稳态试算的长期增速条件，未认定为真实稳态; as-of 2026-11-07
    'legacy_margin_l': 3,  # 早期稳态低档毛利; as-of 2026-11-07
    'legacy_margin_m': 4,  # 早期稳态中档毛利; as-of 2026-11-07
    'legacy_margin_h': 4.5,  # 早期稳态高档毛利; as-of 2026-11-07
    'legacy_deduct_l': 13,  # 早期稳态低档净扣项; as-of 2026-11-07
    'legacy_deduct_m': 14,  # 早期稳态中档净扣项; as-of 2026-11-07
    'legacy_deduct_h': 15,  # 早期稳态高档净扣项; as-of 2026-11-07
}

TIERS = ('l', 'm', 'h')
# 温和恢复、正常修复、充分出清、强短缺；最后一档只用于候选 H。
CASE_NAMES = ('mild_recovery', 'normal_recovery', 'full_supply_clearance', 'severe_shortage')


def earnings(p, volume, margin, deductions):
    return ((volume * margin - deductions) * (1 - p['tax']) - p['minority_profit']) / p['shares_yi']


def holding(eps, pe, rate, years, dividend_fraction=0.0, gap_per_share=0.0):
    # The dividend is a fraction of one annual EPS, not an annual payout rate.
    return (eps * (pe + dividend_fraction) - gap_per_share) / (1 + rate) ** years


def evaluate(p):
    errors = check_missing(p, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(p[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    errors += check_r(p['r_hold'], 'r_hold', 6)
    if p['shares_yi'] <= 0 or p['hold_years'] <= 0 or p['r_hold'] <= -1:
        raise ValueError('invalid shares, discount factor or holding period')
    if not (0 <= p['tax'] < 1):
        errors.append('invalid shares/tax/holding period')
    if not (0 <= p['dividend_fraction'] <= 1 and 0 < p['pe_low'] < p['exit_pe'] < p['pe_high']):
        errors.append('invalid dividend/PE sensitivity ordering')
    warnings = []
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []

    # H1 net deductions already include other business and impairments; do not
    # subtract operating expenses a second time. Normal is the primary M;
    # l/m/h inputs retain their original meanings for the historical cases.
    deductions = 2 * (p['h1_pv_rev'] - p['h1_pv_cost'] - p['h1_pbt'])
    def optional_ratio(numerator, denominator):
        try:
            value = numerator / denominator
            return value if math.isfinite(value) else None
        except (ArithmeticError, TypeError, ValueError):
            return None
    cost = optional_ratio(p['cost_2025'], p['v2025'])
    if cost is None:
        warnings.append('historical_cost_reference_unavailable')
    volumes = [p['volume_l'], p['volume_normal'], p['volume_m'], p['volume_h']]
    margins = [p['margin_l'], p['margin_normal'], p['margin_m'], p['margin_h']]
    eps = [earnings(p, v, m, deductions) for v, m in zip(volumes, margins)]
    values = [holding(e, p['exit_pe'], p['r_hold'], p['hold_years']) for e in eps]
    anchors, candidate = values[:3], [*values[:2], values[3]]
    if not all(math.isfinite(value) for value in anchors) or ladder('flat PE anchors', *anchors):
        raise ValueError('base valuation tiers must be finite and ordered')
    if ladder('EPS', *eps[:3]):
        warnings.append('historical_eps_ladder_requires_review')
    if not all(math.isfinite(value) for value in candidate) or ladder('candidate anchors', *candidate):
        candidate = None
        warnings.append('historical_candidate_unavailable')

    bridge = {}
    for name, volume, margin, earning in zip(CASE_NAMES, volumes, margins, eps):
        price = cost + margin if cost is not None else None
        if price is not None and not math.isfinite(price):
            price = None
        margin_ratio = optional_ratio(margin, price) if price is not None else None
        if margin_ratio is not None and not math.isfinite(margin_ratio * 100):
            margin_ratio = None
        roe = optional_ratio(earning * p['shares_yi'], p['equity'])
        if price is None or margin_ratio is None or roe is None:
            warnings.append('historical_unit_or_return_reference_unavailable')
        bridge[name] = {'volume': volume, 'margin': margin, 'profit': earning * p['shares_yi'], 'eps': earning,
                        'required_price': price, 'gross_margin_percent': None if margin_ratio is None else margin_ratio * 100,
                        'static_roe': roe}
    pe_sensitivity = {name: {str(pe): holding(e, pe, p['r_hold'], p['hold_years'])
                             for pe in (p['pe_stress'], p['pe_low'], p['exit_pe'], p['pe_high'])}
                      for name, e in zip(CASE_NAMES, eps)}
    allocation = {name: [holding(e, p['pe_low'], p['r_hold'], p['hold_years']),
                         holding(e, p['pe_high'], p['r_hold'], p['hold_years'], p['dividend_fraction'])]
                  for name, e in zip(CASE_NAMES, eps)}
    years = {name: [holding(e, p['exit_pe'], p['r_hold'], n) for n in (1, 2, 3)]
             for name, e in zip(CASE_NAMES, eps)}
    annual_dividend = {name: e * p['payout_ref'] for name, e in zip(CASE_NAMES, eps)}

    # Preserve the earlier discussion separately; neither this old Gordon
    # comparison nor its net deductions replace the primary holding model.
    legacy, original_allocation = {}, {}
    # 原旧 Gordon 对照依次为温和、充分、短缺，并非主尺。
    for t, name in zip(TIERS, ('mild', 'full', 'shortage')):
        volume = p[f'volume_{t}']
        old_eps = earnings(p, volume, p[f'legacy_margin_{t}'], p[f'legacy_deduct_{t}'])
        pbt = volume * p[f'legacy_margin_{t}'] - p[f'legacy_deduct_{t}']
        ret = optional_ratio((pbt + p['interest2025']) * (1 - p['tax']), p['capital_proxy'])
        if ret is None or ret == 0 or any(r <= -1 or r <= p['legacy_g'] for r in (p['r_hold'], 0.10)):
            legacy[name] = None
            warnings.append('historical_legacy_return_unavailable')
        else:
            try:
                old_values = [old_eps * (1 - p['legacy_g'] / ret) / (r - p['legacy_g']) /
                              (1 + r) ** p['hold_years'] for r in (p['r_hold'], 0.10)]
                if not all(math.isfinite(value) for value in old_values):
                    raise ValueError('nonfinite historical comparison')
                legacy[name] = {'eps': old_eps, 'return_proxy': ret, 'values': old_values}
            except (ArithmeticError, TypeError, ValueError):
                legacy[name] = None
                warnings.append('historical_legacy_return_unavailable')
        e = earnings(p, volume, p[f'margin_{t}'], p[f'legacy_deduct_{t}'])
        original_allocation[name] = [e, holding(e, p['pe_low'], p['r_hold'], p['hold_years']),
                                     holding(e, p['pe_high'], p['r_hold'], p['hold_years'], p['dividend_fraction'])]

    # The release fraction applies to the same finite cash path. The unspent
    # fraction is not assumed permanently lost or added to the exit multiple.
    cash_window = {}
    for extra in (1, 3):
        extra_eps = p['volume_m'] * extra * (1 - p['tax']) / p['shares_yi']
        cash_window[str(extra)] = {str(fraction): [sum(extra_eps * fraction / (1 + p['r_hold']) ** t
                                                        for t in range(2, n + 2)) for n in (1, 2, 3)]
                                   for fraction in (0, 0.25, 0.5, 0.75, 1)}
        for fraction in (0, 0.25, 0.5, 0.75, 1):
            if abs(cash_window[str(extra)][str(fraction)][1] - cash_window[str(extra)]['1'][1] * fraction) > 1e-12:
                warnings.append('historical_cash_interpolation_requires_review')
    # Peak EPS is 1, followed by a stable zero-growth cash stream. This is a
    # comparison, not a forecast, and must not be added to the PE above.
    try:
        cash_path = {str(ratio): [sum(1 / (1 + p['r_hold']) ** t for t in range(1, n + 1)) +
                                  ratio / p['r_hold'] / (1 + p['r_hold']) ** n for n in (1, 2, 3)]
                     for ratio in (0.4, 0.6, 0.8)}
        if any(not math.isfinite(value) for values in cash_path.values() for value in values):
            cash_path = None
    except (ArithmeticError, TypeError, ValueError):
        cash_path = None
    if cash_path is None:
        warnings.append('historical_cash_path_unavailable')
    tax_sensitivity = {str(tax): [earnings({**p, 'tax': tax}, p[f'volume_{t}'], p[f'margin_{t}'], deductions)
                                  for t in TIERS] for tax in (0.10, 0.15, 0.25)}
    a, b = cut_points(*anchors)
    ca, cb = cut_points(*candidate) if candidate is not None else (None, None)
    band = lambda xs: dict(zip('LMH', xs))
    # 主尺为持有期退出倍数；候选带名称继续供首页展示。
    return {'ticker': '601865.SH', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-11-08',
            'framework_as_of': None, 'historical_research_as_of': '2026-11-08',
            'anchors': band(anchors), 'cut_points': {'A': a, 'B': b},
            'candidate': ({'label': '强短缺', 'anchors': band(candidate), 'cut_points': {'A': ca, 'B': cb}}
                          if candidate is not None else {'label': '强短缺', 'status': 'unavailable', 'anchors': None}),
            'option': None, 'segments': {'company': {'values': band(anchors)}},
            'review_flags': sorted(set(warnings)),
            'key_parameters': {'method': 'holding_period_exit_multiple', 'discount_rate': band([p['r_hold']] * 3),
                               'growth_rate': band([None] * 3), 'forward_return': band([None] * 3),
                               'steady_return': band([None] * 3), 'exit_pe': band([p['exit_pe']] * 3),
                               'hold_years': band([p['hold_years']] * 3), 'eps': band(eps[:3])},
            'bridge': bridge, 'net_deductions': deductions,
            'sensitivity': {'exit_pe': pe_sensitivity, 'allocation': allocation, 'holding_years': years,
                            'annual_dividend': annual_dividend, 'tax_eps': tax_sensitivity,
                            'funding_gap_10': [10 / p['shares_yi'], 10 / p['shares_yi'] / (1 + p['r_hold']) ** 2],
                            'cash_window': cash_window, 'cash_path': cash_path,
                            'legacy_gordon': legacy, 'original_allocation': original_allocation,
                            'cash_2025': [p['cfo2025'], p['capex2025'], p['cfo2025'] - p['capex2025']]}}


def calculate(context):
    result = evaluate(dict(INPUTS))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'].extend(['historical_exit_multiple_and_horizon_unverified',
                                   'historical_funding_and_convertible_dilution_unverified'])
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'case_names': CASE_NAMES}, BASELINE_LOCAL)
    return result
