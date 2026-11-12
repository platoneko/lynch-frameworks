#!/usr/bin/env python3
"""Huadong FY2028 historical operating scenarios; not a new forecast.

Amounts CNY 100 million, shares 100 million, prices CNY/share. [R1]–[R10]
refer to the original sources retained in the framework document, including:
2026Q3 https://static.cninfo.com.cn/finalpage/2026-10-29/1225637393.PDF
2025 annual https://static.cninfo.com.cn/finalpage/2026-04-24/1225168701.PDF
H1 forecasts https://pdf.dfcfw.com/pdf/H3_AP202609011828877392_1.pdf
https://pdf.dfcfw.com/pdf/H3_AP202609011828846434_1.pdf
strong recovery https://pdf.dfcfw.com/pdf/H3_AP202604241821526856_1.pdf

L maps a past stressed margin onto forecast revenue; its multiple is the
historical paid lower edge. M is the mean of H1 analyst forecasts; H is an
older, stronger forecast, not current consensus. M/H forward return proxies
are not demonstrated steady investment returns; unknown additional occupation
and pre-2028 distributions stay conditional. No standalone new-drug value is
added without a profit bridge that removes overlap. The user authorized saving
the framework with these gaps on 2026-11-08, not certifying the evidence.
"""
# Original source key retained for input comments:
# R1: 2026Q3 report https://static.cninfo.com.cn/finalpage/2026-10-29/1225637393.PDF
# R2: 2026H1 report https://static.cninfo.com.cn/finalpage/2026-08-27/1225511869.PDF
# R3: 2026-10-29/30 IR https://static.cninfo.com.cn/finalpage/2026-10-30/1225646794.PDF
# R4: annual reports 2025 https://static.cninfo.com.cn/finalpage/2026-04-24/1225168701.PDF
# 2023 https://static.cninfo.com.cn/finalpage/2024-04-18/1219652512.PDF
# 2021 https://static.cninfo.com.cn/finalpage/2022-04-28/1213170749.PDF
# 2020 https://static.cninfo.com.cn/finalpage/2021-04-21/1209739679.PDF
# 2019 https://static.cninfo.com.cn/finalpage/2020-04-28/1207643134.PDF
# R5: Southwest 2026-08-28 https://pdf.dfcfw.com/pdf/H3_AP202609011828877392_1.pdf
# R6: Guojin H1 https://pdf.dfcfw.com/pdf/H3_AP202609011828846434_1.pdf
# R7: drug application https://longbridge.cn/news/304108742
# R8: Guojin April https://pdf.dfcfw.com/pdf/H3_AP202604241821526856_1.pdf
# R9: Longbridge unadjusted monthly closes 2023-01 through 2026-10 paired
# with then-published earnings (Q1/Q2/Q3 reports, not later revisions).
# R10: 2021 annual report above, for the historical stress margin.
# Q3 cash, capital and licensing payment bridges remain incomplete. The
# extra occupation cases are conditional, not observed expenses; no standalone
# drug value or pre-2028 distribution is inserted without a non-overlap bridge.
# The 2026-11-08 authorization acknowledged these limits rather than proving
# that the forward equity proxy is a demonstrated steady investment return.
from __future__ import annotations

import math
from lib.gordon import check_g_cap, check_r, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = '0f64a6b2c4f5d46d029c3947f9423a8347b5182764bc2ce2cb819f3bbea6310b'

INPUTS = {
    'shares': 17.53736848,  # Q3 总股本 [R1]; as-of 2026-09-30
    'revenue9m24': 314.776547505,  # 2024前三季度收入，2025Q3比较列 [R9]; as-of 2024-09-30
    'revenue9m26': 330.1910560931,  # 2026前三季度收入 [R1]; as-of 2026-09-30
    'revenue21': 345.6330123367,  # FY2021收入，集采/转型压力年度 [R10]; as-of 2021-12-31
    'np21': 23.0163134764,  # FY2021集团归母，映射同口径净利率而非照搬当年规模 [R10]; as-of 2021-12-31
    'np28_gj': 43.06,  # 国金H1 FY2028归母基准 [R6]; as-of 2026-09-01 收录
    'np28_sw': 44.3186,  # 西南H1 FY2028归母基准 [R5]; as-of 2026-08-28
    'np_h': 50.27,  # 国金4月FY2028较强盈利恢复条件 [R8]; as-of 2026-04-24
    'revenue_h': 516.23,  # H同源集团收入 [R8]; as-of 2026-04-24
    'equity27_h': 294.47,  # H同源FY2027末归母权益，避免高利润与低资本拼接 [R8]; as-of 2026-04-24
    'gross_gj': 164.75,  # 国金H1版FY2028集团毛利 [R6]; as-of 2026-09-01 收录
    'gross_h': 178.10,  # 国金4月版FY2028集团毛利 [R8]; as-of 2026-04-24
    'fees_delta_h': 4.55,  # H相对国金H1销售/管理/研发/税附加增加，成本填正值 [R6][R8]; as-of 同上
    'residual_delta_h': -0.01,  # 两摘要未列项目残差1.09减1.10，不编作独立收入科目 [R6][R8]; as-of 同上
    'pbt_gj': 52.51,  # 国金H1版FY2028税前利润 [R6]; as-of 2026-09-01 收录
    'pbt_h': 61.30,  # 国金4月版FY2028税前利润 [R8]; as-of 2026-04-24
    'forecast_tax': 0.18,  # 两版相同预测所得税率，少数损益近零 [R6][R8]; as-of 同上
    'pe_l': 13.5777940492,  # L配对实付下沿，2026-10收盘与当时已公布TTM同口径 [R9]; as-of 2026-10-30
    'equity27_gj': 286.80,  # 国金 FY2027 末归母权益 [R6]; as-of 2026-09-01 收录
    'equity27_sw': 291.7558,  # 西南 FY2027 末归母权益 [R5]; as-of 2026-08-28
    'assets27': 429.6188,  # 两家 FY2027 末总资产均值：439.37、419.8676; as-of 同上
    'revenue28': 498.0461,  # 两家 FY2028 收入均值：496.23、499.8622; as-of 同上
    'r_perp': 0.10,  # 篮 4 常规经营：集团多产品经营，盈利不构成商品报价函数; as-of 2026-11-08
    'r_disc': 0.10,  # 同经营要求回报的年份漂移折现，不另归篮; as-of 2026-11-08
    'discount_years': 1,  # FY2028 相对 FY2027 下一期口径后移一年；采用框架年度 convention，不是日计精确现值; as-of 2026-11-08
    'g2': 0.04,  # 宏观兜底；同生意反解簇与本票同等盈利证据未建立，不借历史高增当永续; as-of 2026-11-08
    'y1': 2028,  # 无额外高回报维持段，直接使用已明示的稳态代理; as-of 2026-11-08
    'y2': 2028,  # 无另设回落段；稳态代理未验证，见 A5; as-of 2026-11-08
    'np25': 34.1433532641,  # FY2025 归母净利润 [R4]; as-of 2025-12-31
    'div25': 16.3127205464,  # FY2025 实付母公司普通股现金股息；不含少数分配及利息 [R4]; as-of 2025-12-31
    'cfo25': 42.4560437117,  # FY2025 合并经营现金 [R4]; as-of 2025-12-31
    'capex25': 15.7445400841,  # FY2025 购建固定/无形/其他长期资产现金 [R4]; as-of 2025-12-31
    'net_debt25': -26.668805639,  # FY2025 有息债及租赁 20.690411 减现金等价物 47.359216639 [R4]; as-of 2025-12-31
    'debt25': 20.690411,  # FY2025 有息债及租赁；一年内到期部分不重复加 [R4]; as-of 2025-12-31
    'ebit25': 41.0789289083,  # 报表营业利润，按杠杆门口径 [R4]; as-of 2025-12-31
    'da25': 10.4002135533,  # 固定/使用权折旧、无形/长期待摊摊销合计 [R4]; as-of 2025-12-31
    'interest25': 0.9473409360,  # 利润表利息费用；附注另列 0.8377 亿元，采用较高口径 [R4]; as-of 2025-12-31
    'tax25': 0.1507833484,  # 所得税 6.0561553779 / 利润总额 40.1646231024 [R4]; as-of 2025-12-31
    'equity25': 248.1133999299,  # 归母权益 [R4]; as-of 2025-12-31
    'nci25': 3.5966568719,  # 少数权益 [R4]; as-of 2025-12-31
    'parent_equity': 257.4987053455,  # Q3 归母权益 [R1]; as-of 2026-09-30
    'total_equity': 260.7187229982,  # Q3 合并权益 [R1]; as-of 2026-09-30
    'cash_eq': 39.3820712922,  # Q3 现金等价物，不直接用货币资金 [R1]; as-of 2026-09-30
    'debt_q3': 20.7448,  # Q3 短借、长借、当前到期整项、非流动租赁的保守合计 [R1]; as-of 2026-09-30
    'dividend_payable': 0.7181021960,  # Q3 整项应付股利，未拆普通股/少数股东，保守全扣 [R1]; as-of 2026-09-30
    'revenue25': 436.1200989102,  # FY2025 收入 [R4]; as-of 2025-12-31
    'cash_ratio_low': 0.0134,  # 2019 历史净现金/收入候选，含递延对价；七年类债完全统一仍待补; as-of FY2019–FY2025
    'cash_ratio_high': 0.0155,  # 历史比率候选另一口径；只作门槛区间，不任取中点; as-of 同上
    'window_cash': 0,  # 本版不加未闭合的分子年前分配窗口；是估值处理，不是现金事实; as-of 2026-11-08
    'V_opt': 0,  # 未单独计量的新增药品价值；不表示经济价值为零; as-of 2026-11-08
}

# Point-in-time reported TTM profit and month-end price, not retrospective annual PE.
# The original review compared the 2026-10 lower-edge 7.33% forecast growth
# and ~14% forward equity return against 4% and M's ~15.10%, judged neither
# above the distortion thresholds, and did not use this history to lower r.
MATCHED_MONTHS = [
    ('2024-04', '2024-03-31', 29.4598712729, 32.94),
    ('2024-05', '2024-03-31', 29.4598712729, 31.63),
    ('2024-06', '2024-03-31', 29.4598712729, 27.81),
    ('2024-07', '2024-03-31', 29.4598712729, 29.19),
    ('2024-08', '2024-06-30', 31.0105650244, 29.48),
    ('2024-09', '2024-06-30', 31.0105650244, 34.99),
    ('2024-10', '2024-09-30', 32.1214038663, 33.01),
    ('2024-11', '2024-09-30', 32.1214038663, 38.98),
    ('2024-12', '2024-09-30', 32.1214038663, 34.60),
    ('2025-01', '2024-09-30', 32.1214038663, 34.80),
    ('2025-02', '2024-09-30', 32.1214038663, 34.63),
    ('2025-03', '2024-09-30', 32.1214038663, 36.70),
    ('2026-08', '2026-06-30', 34.6026572797, 27.26),
    ('2026-09', '2026-06-30', 34.6026572797, 27.69),
    ('2026-10', '2026-09-30', 34.3829599453, 26.62),
]


def evaluate(x, matched_months=None):
    if matched_months is None:
        matched_months = MATCHED_MONTHS
    errors = check_missing(x, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(x[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, g = x['r_perp'], x['g2']
    errors += check_r(r, 'group', 4)
    errors += check_g_cap(g, r, 'group')
    if x['y1'] != 2028 or x['y2'] != 2028:
        errors.append('changed return timeline requires a new return-path model')
    if x['V_opt'] != 0:
        errors.append('new option value requires an independently modeled profit bridge')
    if min(x['shares'], x['revenue9m24'], x['revenue21'], x['equity27_gj'] + x['equity27_sw'],
           x['equity27_h'], x['np25'], x['total_equity'], x['ebit25'], x['assets27']) <= 0:
        errors.append('invalid model denominator')
    if x['r_disc'] <= -1:
        errors.append('invalid discount rate')
    profit_bridge = x['gross_h'] - x['gross_gj'] - x['fees_delta_h'] + x['residual_delta_h']
    if abs(profit_bridge - (x['pbt_h'] - x['pbt_gj'])) > .02:
        errors.append('H gross-profit/expense bridge does not reconcile')
    for profit, pbt in ((x['np_h'], x['pbt_h']), (x['np28_gj'], x['pbt_gj'])):
        if abs(profit - pbt * (1 - x['forecast_tax'])) > .01:
            errors.append('forecast after-tax profit differs from the source bridge')
    if errors:
        raise ValueError('; '.join(errors))

    discount = (1 + x['r_disc']) ** x['discount_years']
    equity = (x['equity27_gj'] + x['equity27_sw']) / 2
    revenue_growth = (x['revenue9m26'] / x['revenue9m24']) ** .5 - 1
    revenue_l = x['revenue25'] * (1 + revenue_growth) ** 3
    margin_l = x['np21'] / x['revenue21']
    profits = {'l': revenue_l * margin_l, 'm': (x['np28_gj'] + x['np28_sw']) / 2, 'h': x['np_h']}
    dividend_fraction = x['div25'] / x['np25']
    rows = []
    for tier in 'lmh':
        profit = profits[tier]
        capital = x['equity27_h'] if tier == 'h' else equity
        eps, return_proxy = profit / x['shares'], profit / capital
        if return_proxy <= 0:
            raise ValueError(f'{tier}: nonpositive return proxy')
        reinvestment = g / return_proxy
        pe = x['pe_l'] if tier == 'l' else perpetual_pe(g, return_proxy, r)
        value = eps * pe / discount + x['window_cash']
        occupation = None if tier == 'l' else profit * (1 - reinvestment - dividend_fraction)
        if tier != 'l' and not (0 < reinvestment <= 1 - dividend_fraction):
            errors.append(f'{tier}: reinvestment exceeds retained earnings')
        if occupation is not None and occupation < 0:
            errors.append(f'{tier}: conditional occupation is negative')
        rows.append((eps, return_proxy, pe, value, occupation))

    anchors = [row[3] for row in rows]
    errors += ladder('anchors', *anchors)
    errors += ladder('flat', *(row[0] * rows[1][2] / discount for row in rows))
    pairs = []
    for month, quarter, earnings, close in matched_months:
        eps_hist = earnings / x['shares']
        if abs(eps_hist / rows[0][0] - 1) > .12:
            errors.append(f'{month} outside L earnings pairing window; resample history')
        pairs.append((month, quarter, close / eps_hist))
    if len(pairs) < 6:
        errors.append('L needs at least six matched historical months')
    if pairs and not math.isclose(min(p[2] for p in pairs), x['pe_l'], abs_tol=1e-7):
        errors.append('L multiple differs from the matched-month paid lower edge')

    def occupation_pv(amount, years):
        if years is None:
            return amount / x['shares'] / (r - g) / discount
        return sum(amount * (1 + g) ** i / x['shares'] /
                   (1 + r) ** (i + 1) / discount for i in range(years))

    cash_use = {}
    for tier, row in zip('MH', rows[1:]):
        amount = row[4]
        if not (occupation_pv(amount, 1) < occupation_pv(amount, 5) <
                occupation_pv(amount, 10) < occupation_pv(amount, None)):
            errors.append('occupation duration monotonicity failed')
        if not math.isclose(occupation_pv(amount, 1000), occupation_pv(amount, None), abs_tol=1e-9):
            errors.append('finite occupation does not converge to perpetuity')
        if not math.isclose(occupation_pv(2 * amount, 5), 2 * occupation_pv(amount, 5), abs_tol=1e-9):
            errors.append('occupation amount continuity/linearity failed')
        cash_use[tier] = {'annual_amount': amount, '5_years': row[3] - occupation_pv(amount, 5),
                          '10_years': row[3] - occupation_pv(amount, 10),
                          'permanent': row[3] - occupation_pv(amount, None), 'baseline': row[3]}
    if occupation_pv(0, 5) != 0:
        errors.append('zero occupation changes value')

    cash = [(x['cash_eq'] - x['debt_q3'] - x['dividend_payable'] - x['revenue25'] * x[key]) *
            x['parent_equity'] / x['total_equity'] for key in ('cash_ratio_high', 'cash_ratio_low')]
    if max(cash) >= .15 * x['parent_equity']:
        errors.append('excess cash now triggers separate treatment')
    leverage = x['net_debt25'] / (x['ebit25'] + x['da25'])
    interest_ratio = x['interest25'] / x['ebit25']
    if leverage > 3 or interest_ratio > 1 / 3:
        errors.append('leverage gate now requires reconstruction')
    margin = profits['m'] / x['revenue28']
    turnover = x['revenue28'] / x['assets27']
    multiplier = x['assets27'] / equity
    if not math.isclose(margin * turnover * multiplier, rows[1][1], abs_tol=1e-12):
        errors.append('DuPont bridge failed')
    if errors:
        raise ValueError('; '.join(errors))

    band = lambda values: dict(zip('LMH', values))
    sensitivity = {name: band([anchors[0]] + [row[0] * perpetual_pe(g + delta, row[1], r) / discount + x['window_cash']
                                               for row in rows[1:]])
                   for name, delta in (('growth_minus_1pp', -.01), ('growth_plus_1pp', .01))}
    a, b = cut_points(*anchors)
    # L uses 历史同等盈利实付倍数; M/H use 集团 Gordon.
    return {'ticker': '000963.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-11-08',
            'framework_as_of': None, 'historical_research_as_of': '2026-11-08', 'historical_framework_as_of': '2026-11-08',
            'anchors': band(anchors), 'cut_points': {'A': a, 'B': b},
            'candidate': None, 'option': None, 'segments': {'company': {'values': band(anchors)}},
            'key_parameters': {'method': band(['historical_equal_earnings_multiple', 'gordon_group', 'gordon_group']),
                               'discount_rate': band([x['r_disc']] * 3),
                               'growth_rate': band([None, g, g]),
                               'forward_return': band([None, rows[1][1], rows[2][1]]),
                               'steady_return': band([None, rows[1][1], rows[2][1]]),
                               'multiple': band([row[2] for row in rows]),
                               'eps': band([row[0] for row in rows])},
            'operating': {'profits': band(profits[t] for t in 'lmh'), 'revenue_growth': revenue_growth,
                          'revenue_l': revenue_l, 'margin_l': margin_l, 'profit_bridge': profit_bridge,
                          'dividend_fraction': dividend_fraction, 'du_pont': [margin, turnover, multiplier],
                          'roic_2025': x['ebit25'] * (1 - x['tax25']) / (x['equity25'] + x['nci25'] + x['net_debt25']),
                          'cash_gate': cash, 'leverage': leverage, 'interest_ratio': interest_ratio,
                          'matched_months': pairs},
            'sensitivity': {**sensitivity, 'cash_use': cash_use,
                            'unit_occupation': [occupation_pv(1, n) for n in (1, 5, 10, None)],
                            'pressure_margin_plus_1pp': revenue_l * .01 / x['shares'] * x['pe_l'] / discount,
                            'flat_multiple': band(row[0] * rows[1][2] / discount for row in rows)}}


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'matched_months': MATCHED_MONTHS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    result['review_flags'] = ['historical_future_cash_occupation_unverified',
                              'historical_licensing_costs_and_capital_bridge_unverified',
                              'historical_investment_return_proxy_unverified']
    return result
