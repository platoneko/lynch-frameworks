#!/usr/bin/env python3
"""Enjie's historical FY2028 forecast scenarios; not updated research.

Amounts are CNY and shares, outputs CNY/share. The financial report and
analyst source descriptions and historical evidence are retained in the
document. The user selected basket 4 and the 3% growth assumption on
2026-10-28/29; 3% also reflects the same battery-demand chain as 300750.SZ
and must be reviewed if that framework changes. The previous basket 6 is a
disclosed contrast, not the adopted value.

L applies the historical 2023/2022 profit ratio to FY2028 consensus as a
persistent price-war regime, not a certain trough. Its three-year recovery
is only a point comparison. M is the mean of five forecasts and H is their
high; the 2028–2032 fade is the original judgment. All require review when
the supporting evidence or source estimates change. Solid-state electrolyte
has no independently quantifiable economics and is not added as an option.
"""
# Research details retained with the model:
# The 2026-10-28 forecast sample was Guojin 6.10, Shanxi 6.26,
# Dongwu 6.29, Guoxin 6.11, and AVIC 5.12 CNY/share for FY2028.
# The low scenario uses 2023/2022 profit 25.27/40.00 CNY 100 million;
# FY2024 was loss-making and is not represented by the low anchor.
# The FY2020–2024 invested-capital returns were 12.0%, 18.1%, 17.8%,
# 8.7%, -1.1%; their 11.10% mean is converted using 1.90% after-tax debt
# cost and net debt / total equity of about 0.440. The resulting 15.15%
# is a reference capped at each tier's forward return, not an automatic
# claim that future incremental investments earn that return.
# Funding gap from Guoxin 2026-10-16: Q4 2026–2027 expected capex 68.77
# minus operating cash flow 61.66, in CNY 100 million. The full shortfall
# is included because the Zigong project's production schedule was unknown.
# FY2021–2025 dividends totaled 21.35 against parent profits 88.33 CNY
# 100 million. Fixed assets plus construction rose from 79.8 to 297.9,
# supporting operating reinvestment rather than extra cash distribution.
# Low-tier comparable-earnings months in 2022–2023 had PE 17.3–42.2;
# contemporaneous FY2023–2025 forecast growth of 28–32% (Shanxi, BOC,
# Minsheng, August 2023) differed materially from the model's 3%, so that
# band was not treated as a valid constraint. FY2028 high earnings had no
# corresponding historical months. Independent coordinates remain checked.
# The 2028 forecast leverage and FY2025 actual leverage are distinct: the
# original decision applies the forecast year while retaining the actual
# downturn comparison. User-selected 10% and 3% do not resolve the economic
# question of whether the next cycle resembles a commodity price war.
from __future__ import annotations

import math
from lib.gordon import (check_branch, check_g_cap, check_r, payout, perpetual_pe, recovery_two_stage_pe)
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {},
                'peers': {'catl': '300750.SZ'}}

HISTORICAL_PARTIAL_FINGERPRINT = '2664e28c73197257477100c07b26039af4eafbbbbe0d0384a51ea4466ad18afa'

INPUTS = {
    'shares': 9.81017118e8,  # 总股本，注销 301,400 股回购股后（公告 2026-173）；每股价值的分母; as-of 2026-10-10
    'shares_cons': 9.81318518e8,  # 卖方 EPS 所用总股本（注销前）；EPS → 归母; as-of 2026-09-30
    'eps26_m': 2.7764,  # FY2026E EPS 5 家均值（国金 2.572 / 山西 2.99 / 东吴 2.99 / 国信 2.92 / 中航 2.41）; as-of 2026-10-28
    'eps27_m': 4.8154,  # FY2027E EPS 5 家均值（4.867 / 5.00 / 5.14 / 5.12 / 3.95）; as-of 2026-10-28
    'eps28_l': 5.12,  # FY2028E 下沿（中航 2026-10-12）；只作分子下沿披露; as-of 2026-10-28
    'eps28_m': 5.976,  # FY2028E 5 家均值（6.10 / 6.26 / 6.29 / 6.11 / 5.12）; as-of 2026-10-28
    'eps28_h': 6.29,  # FY2028E 上沿（东吴 2026-10-27）; as-of 2026-10-28
    'np_9m': 17.94484503e8,  # 2026 前三季度归母（三季报）; as-of 2026-09-30
    'np_fy22': 40.00461964e8,  # FY2022 归母（年报）; as-of 2022-12-31
    'np_fy23': 25.26688571e8,  # FY2023 归母（年报）; as-of 2023-12-31
    'equity': 264.0714143e8,  # 归母权益（三季报）; as-of 2026-09-30
    'minority': 11.60053855e8,  # 少数股东权益（三季报）; as-of 2026-09-30
    'cash': 38.99662903e8,  # 货币资金（无交易性金融资产）; as-of 2026-09-30
    'st_loan': 74.03665766e8,  # 短期借款; as-of 2026-09-30
    'ncl_1y': 17.91996267e8,  # 一年内到期的非流动负债; as-of 2026-09-30
    'lt_loan': 64.33852670e8,  # 长期借款（无应付债券、无租赁负债）; as-of 2026-09-30
    'div_declared': 4.01478977e8,  # 2026 中期分红（每 10 股 4.10 元，基准日后派发；类债项）; as-of 2026-10-14
    'gap_g': 7.11e8,  # 增长期资金缺口：国信现金流预测扣前三季度实测（A7）; as-of 2026-10-16
    'tau': 1.25,  # 2026-09-30 → 2028-01-01 年数; as-of 2026-09-30
    'r_perp': 0.10,  # 篮 4 常规经营：需求周期型制造，用户 2026-10-28 裁定（A1；初分篮对照见 §0）; as-of 2026-10-28
    'g2': 0.03,  # 永续增长，三档同值；用户判断（与 `300750.SZ` 同需求链，A4）; as-of 2026-10-29
    'ronic_roic_cycle': 0.1110,  # 自身 FY2020–24 谷到谷 ROIC 均值（A5）; as-of 2025-12-31
    'kd_at': 0.0190,  # 税后债务成本 = FY2025 利息 3.42 亿 ÷ 平均有息负债约 153 亿 × (1 − 15%); as-of 2025-12-31
    'ronic_ss_floor': 0.11,  # 生意模式兜底（商品化重资产），只作对照; as-of 2026-10-15
    'y1': 2028,  # 高回报维持到（可见年末）; as-of 2026-10-28
    'y2': 2032,  # 回落完成年（中门槛 4 年）; as-of 2026-10-28
    'payout_op': 0.242,  # 经营口径派息率 FY2021–25（A8）; as-of 2025-12-31
    'ebitda_28': 116.51e8,  # FY2028E EBITDA（国信：EBIT 81.59 + 折旧摊销 34.92）; as-of 2026-10-16
    'ebit_28': 81.59e8,  # FY2028E EBIT（国信 EBIT margin 27.7% × 收入 294.52）; as-of 2026-10-16
    'interest_28': 5.06e8,  # FY2028E 财务费用（国信）; as-of 2026-10-16
    'ebitda_fy25': 29.62e8,  # FY2025 EBITDA（对照口径）; as-of 2025-12-31
    'ebit_fy25': 7.79e8,  # FY2025 EBIT = 利润总额 + 利息; as-of 2025-12-31
    'interest_fy25': 3.42e8,  # FY2025 利息支出; as-of 2025-12-31
    'pb_trough': 1.05,  # FY2024–25 谷底 PB（月收盘 / 当期 BPS 约 25.1–25.9），资产口径坐标; as-of 2025-06-30
    'pe_band_l_min': 17.3,  # L 档同等盈利月份 PE 最低（2023-08）; as-of 2023-08-31
    'pe_band_l_max': 42.2,  # L 档同等盈利月份 PE 最高（2022-08）; as-of 2022-08-31
}

YI = 1e8
NUM_YEAR = 2028
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3
RECON_GATE = .20
N_REC_POINT = 3


def path_pe(g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (retention.md ② 稳态回报三段) at the start of NUM_YEAR per unit of
    NUM_YEAR earnings: RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after."""
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


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS) + ['l_factor', 'parent_ratio', 'net_debt_ext', 'ronic_ss', 'bps_now'])
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('y1', 'y2'))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, g2, sh, shc = inp['r_perp'], inp['g2'], inp['shares'], inp['shares_cons']
    errors += check_r(r, 'r_perp', 4)
    errors += check_g_cap(g2, r, 'g2')
    if abs(inp['tau'] - 1.25) > 1e-9:
        errors.append('tau must match the 2026-09-30 to 2028-01-01 window')
    y1, y2 = int(inp['y1']), int(inp['y2'])
    if not (y1 == NUM_YEAR and y2 == y1 + 4):
        errors.append('return fade must run 2028 to 2032')
    if min(sh, shc, inp['np_fy22'], inp['equity'] + inp['minority'], inp['ebitda_28'], inp['ebit_28'],
           inp['ebitda_fy25'], inp['ebit_fy25']) <= 0:
        errors.append('invalid model denominator')
    errors += ladder('FY2028 consensus', inp['eps28_l'], inp['eps28_m'], inp['eps28_h'])
    if errors:
        raise ValueError('; '.join(errors))
    if abs(inp['np_fy23'] / inp['np_fy22'] - inp['l_factor']) > 5e-4:
        errors.append('price-war factor differs from historical profit ratio')
    pr = inp['equity'] / (inp['equity'] + inp['minority'])
    if abs(pr - inp['parent_ratio']) > 5e-5:
        errors.append('parent ratio differs from balance sheet')
    debt = inp['st_loan'] + inp['ncl_1y'] + inp['lt_loan']
    nd = debt + inp['div_declared'] - inp['cash']
    if abs(nd - inp['net_debt_ext']) > .01 * YI:
        errors.append('extended net debt differs from balance sheet')
    if nd <= 0:
        errors.append('extended net cash is positive: excess-cash test required')
    ss = inp['ronic_roic_cycle'] + (inp['ronic_roic_cycle'] - inp['kd_at']) * nd / (inp['equity'] + inp['minority'])
    if abs(ss - inp['ronic_ss']) > 5e-4:
        errors.append('steady return differs from equity-basis conversion')
    if inp['ronic_ss'] < r:
        errors.append('steady return below r')
    if abs(inp['equity'] / sh - inp['bps_now']) > .01:
        errors.append('book value per share differs from balance sheet')
    if errors:
        raise ValueError('; '.join(errors))

    tau = inp['tau']
    disc, disc_w = (1 + r) ** tau, (1 + r) ** (tau / 2)
    unb = inp['eps26_m'] * shc - inp['np_9m'] + inp['eps27_m'] * shc
    b0 = inp['equity'] - inp['div_declared']
    deduct = inp['gap_g'] * pr / sh + inp['div_declared'] / shc
    e_tier = {'m': inp['eps28_m'] * shc, 'h': inp['eps28_h'] * shc}
    e_tier['l'] = inp['l_factor'] * e_tier['m']

    def tier(e, g, rs, y2_=y2):
        roe = .2
        for _ in range(300):
            book = b0 + g / roe * unb
            roe = e / book
        pe = path_pe(g, roe, r, y1, y2_, rs)
        w = unb * (1 - g / roe) / disc_w
        val = (e * pe / disc + w) / sh - deduct
        return dict(e=e, roe=roe, book=book, pe=pe, w=w / sh, val=val, pe_1=perpetual_pe(g, roe, r))

    rows = {t: tier(e_tier[t], g2, inp['ronic_ss']) for t in ('l', 'm', 'h')}
    L, M, H = (rows[t]['val'] for t in ('l', 'm', 'h'))
    errors += ladder('anchors', L, M, H)
    for t in ('m', 'h'):
        if rows[t]['roe'] - r < .03:
            errors.append(f'{t}: forward return outside monotone zone')
        errors += check_branch(g2, rows[t]['roe'], r, inp['payout_op'], f'g2 ({t})')
    b_ss = g2 / inp['ronic_ss']
    if b_ss > 1 - inp['payout_op'] or g2 > (1 - inp['payout_op']) * inp['ronic_ss']:
        errors.append('steady-state retention exceeds what company keeps')
    flat = [(rows[t]['e'] * rows['m']['pe'] / disc + rows['m']['w'] * sh) / sh - deduct for t in ('l', 'm', 'h')]
    errors += ladder('flat-multiple', *flat)
    c_er = (e_tier['m'] / r / disc + unb * (1 - g2 / rows['m']['roe']) / disc_w) / sh - deduct
    c_ddm = .40 * inp['eps28_m'] / (r - g2) / disc
    c_pb = inp['bps_now'] * inp['pb_trough']
    near = min(abs(M / c - 1) for c in (c_er, c_ddm, c_pb))
    if near > RECON_GATE:
        errors.append('M differs by more than 20% from every reconciliation coordinate')
    lev1, lev2 = nd / inp['ebitda_28'], inp['interest_28'] / inp['ebit_28']
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append('leverage gate triggered on FY2028 — ROIC branch required')
    if errors:
        raise ValueError('; '.join(errors))

    g1 = (e_tier['m'] / e_tier['l']) ** (1 / N_REC_POINT) - 1
    pe_pt = recovery_two_stage_pe(g1, N_REC_POINT, g2, rows['m']['roe'], r)
    l_pt = (e_tier['l'] * pe_pt / disc + rows['l']['w'] * sh) / sh - deduct
    cases = {'growth_minus_1pp': {'g': g2 - .01}, 'growth_plus_1pp': {'g': g2 + .01},
             'steady_return_floor': {'rs': inp['ronic_ss_floor']}, 'fade_2030': {'y2_': y1 + 2}}
    sensitivity = {}
    for label, changes in cases.items():
        g, rs, yy = changes.get('g', g2), changes.get('rs', inp['ronic_ss']), changes.get('y2_', y2)
        sensitivity[label] = {t.upper(): tier(e_tier[t], g, rs, yy)['val'] for t in ('l', 'm', 'h')}
    sensitivity['low_recovery_point'] = l_pt
    sensitivity['mean_low_forecast'] = (inp['eps28_l'] * shc * rows['m']['pe'] / disc + rows['m']['w'] * sh) / sh - deduct
    sensitivity['flat_multiple'] = dict(zip('LMH', flat))
    a, b = cut_points(L, M, H)
    # 三档均采用三段 Gordon。
    return {'ticker': '002812.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-29', 'historical_framework_as_of': '2026-10-29',
            'anchors': dict(zip('LMH', (L, M, H))), 'cut_points': {'A': a, 'B': b},
            'candidate': None, 'option': None,
            'segments': {'company': {'values': dict(zip('LMH', (L, M, H)))}},
            'key_parameters': {'method': dict.fromkeys('LMH', 'gordon_three_stage'),
                               'discount_rate': dict.fromkeys('LMH', r), 'growth_rate': dict.fromkeys('LMH', g2),
                               'forward_return': {t.upper(): rows[t]['roe'] for t in ('l', 'm', 'h')},
                               'steady_return': {t.upper(): min(rows[t]['roe'], inp['ronic_ss']) for t in ('l', 'm', 'h')},
                               'multiple': {t.upper(): rows[t]['pe'] for t in ('l', 'm', 'h')}},
            'operating': {'rows': rows, 'net_debt': nd, 'window_profit': unb, 'deduction_per_share': deduct,
                          'steady_return_conversion': ss,
                          'low_value_multiple': (L + deduct) / (e_tier['l'] / sh),
                          'reconciliation': [c_er, c_ddm, c_pb], 'reconciliation_nearest': near,
                          'leverage_2028': [lev1, lev2],
                          'leverage_2025': [nd / inp['ebitda_fy25'], inp['interest_fy25'] / inp['ebit_fy25']]},
            'sensitivity': {**sensitivity, 'low_recovery_pe': pe_pt}}


def derived_inputs(inputs):
    # The historic model explicitly recorded these as derived values. Preserve
    # its displayed precision while deriving them from the editable source
    # numbers, so changed financial inputs do not require duplicate edits.
    pr = inputs['equity'] / (inputs['equity'] + inputs['minority'])
    debt = inputs['st_loan'] + inputs['ncl_1y'] + inputs['lt_loan'] + inputs['div_declared'] - inputs['cash']
    ss = inputs['ronic_roic_cycle'] + (inputs['ronic_roic_cycle'] - inputs['kd_at']) * debt / (inputs['equity'] + inputs['minority'])
    return {'l_factor': round(inputs['np_fy23'] / inputs['np_fy22'], 4), 'parent_ratio': round(pr, 4),
            'net_debt_ext': round(debt / YI, 2) * YI, 'ronic_ss': round(ss, 4),
            'bps_now': round(inputs['equity'] / inputs['shares'], 2)}


def calculate(context):
    derived = derived_inputs(INPUTS)
    result = evaluate({**INPUTS, **derived})
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'units_100m': YI, 'numerator_year': NUM_YEAR,
         'leverage_limit': LEV_DEBT_EBITDA, 'interest_limit': LEV_INT_EBIT,
         'reconciliation_gate': RECON_GATE, 'recovery_years': N_REC_POINT}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    result['review_flags'] = ['historical_growth_funding_and_future_return_unverified',
                              'historical_forecast_after_earnings_unverified']
    # Same battery-demand chain, not a claim that the companies must always
    # share an identical rate. Missing or different peer data calls for review.
    peer = context.get('peers', {}).get('catl')
    params = peer.get('key_parameters') if isinstance(peer, dict) else None
    growth = params.get('growth_rate') if isinstance(params, dict) else None
    if isinstance(growth, dict) and isinstance(growth.get('values'), dict):
        growth = growth['values']
    peer_mid = growth.get('M') if isinstance(growth, dict) else None
    try:
        valid_peer = not isinstance(peer_mid, bool) and isinstance(peer_mid, (int, float)) and math.isfinite(peer_mid)
    except OverflowError:
        valid_peer = False
    if not valid_peer:
        result['review_flags'].append('historical_battery_peer_growth_unverified')
    elif abs(peer_mid - INPUTS['g2']) > 1e-9:
        result['review_flags'].append('historical_battery_peer_growth_differs_review')
    return result
