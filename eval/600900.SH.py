#!/usr/bin/env python3
"""Historical Yangtze Power earnings and retention scenarios.

EPS and outputs are CNY/share; debt/EBIT figures are CNY 100 million;
shares are individual shares. Sources and forecast dates remain described in
the document and next to inputs. M/H policy growth is capped to basket 2;
L instead assumes only regulated pumped-storage reinvestment. The 2028–2034
fade to the historical return adjusted to equity basis was user accepted on
2026-10-19; it is a modeled path, not proof of future return. The window and
debt-repayment retention are included once, without separate option value.
"""
# Historical research context retained from the document:
# The FY2028 EPS range comes from Dongwu 2026-09-02 (1.50), Guojin
# 2026-08-30 (1.554), Kaiyuan 2026-07-07 (1.48), and Guoxin 2026-05-18
# (1.53). The 2026–2030 dividend floor is 70% of parent earnings (2025
# annual report); actual 2023–2025 payouts were 73.6%, 71.0%, 70.9%.
# The low scenario assumes no large plant acquisition: retained 30% earns
# the 6.5% regulated pumped-storage capital return (NDRC 2021 notice 633).
# The middle/high policy-growth calculation is capped at 3.5%; it does not
# treat the uncapped policy-growth diagnostic as the adopted growth rate.
# The 14.4% equity-basis steady return converts post-Yunchuan 2023–2025
# invested-capital returns (7.4%, 8.2%, 8.4%, rounded to 8%) using debt/equity
# of 1.23 and an after-tax debt cost of 2.8%. The six-year fade reflects
# scarce sites, 8–10-year construction and regulated tariffs. It is an
# assumption, not proof of future incremental investment returns.
# Annual-report retention review: 2019–2025 capex was 27.2, 36.3, 34.7,
# 48.7, 122.3, 144.2, 184.9 in CNY 100 million; 2023–2025 net debt was
# 3074, 2911, 2834 in the same units. Retention above modeled reinvestment is attributed to debt
# repayment; acquired Yunchuan's FY2025 net profit 80.0 / consideration
# 804.84 in CNY 100 million is historical support for not discounting that amount.
# The company is net indebted, so cash is not separately added; the original
# model assumes no window funding gap, comparing FY2025 capex 185 with
# operating cash flow 606 CNY 100 million and no cash acquisition in that window.
# Historical comparison: same-earnings months 2024-11–2026-09 had PE range
# 18.06–21.92; the 2026-07 lower endpoint had expected growth around 1–3%
# and TTM ROE around 16%. Ten-year PE range was 13.35–28.9 (Longbridge).
# The 2022 dry-year EPS fall of 16% is a pressure readout, not the L anchor.
# The document date 2026-10-16 predates the accepted 2026-10-19 steady-return
# judgment; preserve both historical dates pending the date-policy decision.
from __future__ import annotations

import math
from lib.gordon import check_branch, check_g_cap, check_r, g_cap, payout_gap, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = '0797976b0e0290ca79bef2601e711136b2a366ebf1be0716e4257d08db66d6b7'

INPUTS = {
    'shares': 24468217716,  # 总股本（Longbridge static）; as-of 2026-10
    'bps0': 8.833,  # 每股归母净资产 CNY，2026-06-30（已扣 2025 末期股息，A10）; as-of 2026-06-30
    'eps26_m': 1.49,  # FY2026E 共识中位（Longbridge forecast-eps）；只用于滚 2028 年初 BPS; as-of 2026-10
    'eps_1h26': 0.6031,  # 1H26 实测 EPS（中报）；已在 bps0 里; as-of 2026-06-30
    'eps27_m': 1.50,  # FY2027E 共识中位（东吴 1.49 / 国金 1.513 / 开源 1.42 / 国信 1.51）；只用于滚 BPS; as-of 2026-09
    'eps_l': 1.48,  # FY2028E 共识下沿（A1）; as-of 2026-09
    'eps_m': 1.515,  # FY2028E 共识中位（A1）; as-of 2026-09
    'eps_h': 1.554,  # FY2028E 共识上沿（A1）; as-of 2026-09
    'r_perp': 0.075,  # 篮 2 管制公用：电价核定 / 倒推、水电优先调度、永续、必须留存投资，利润非商品价函数（A3）；cap = min(6%, r − 4%) = 3.5%; as-of 2026-10-10
    'r_disc': 0.075,  # 分子年初价值折回估值基准日的折现率，同 `r_perp`，不另归篮; as-of 2026-10-10
    'n_disc': 1.5,  # 时点对齐年数 τ = 估值基准日 2026-06-30 → 分子年初 2028-01-01（按实际月数）；窗口可分配利润折 τ/2（A16）; as-of 2026-06-30
    'payout_policy': 0.70,  # 派息政策下限（A2）; as-of 2026-04-30
    'roe_marg_l': 0.065,  # L 世界留存回报 = 抽蓄核定资本金内部收益率（A6）; as-of 2021-04
    'g2_l': 0.0195,  # L：30% × 6.5%（A6）; as-of 2026-10-10
    'g2_m': 0.035,  # M：政策 g 4.8% 截到篮 2 上限（A5）; as-of 2026-10-10
    'g2_h': 0.035,  # H：同 M（H 的 g 不高于 M）; as-of 2026-10-10
    'k_l': 0,  # 视同派出留存打折：A 桶（还债）默认 0，收购实测回报 ≥ r（A4 / A13）; as-of 2026-10-10
    'k_m': 0,  # 同上; as-of 2026-10-10
    'k_h': 0,  # 同上; as-of 2026-10-10
    'pe_own_min': 13.35,  # 十年月频 PE 最低（2017-01，A12）; as-of 2016-11~2026-09
    'pe_own_max': 28.9,  # 十年月频 PE 最高（2023 年，2022 枯水年 EPS 压低所致）; as-of 2016-11~2026-09
    'pe_same_min': 18.06,  # 同等盈利月份 PE 下沿（2026-07，A12）; as-of 2024-11~2026-09
    'pe_same_max': 21.92,  # 同等盈利月份 PE 上沿（2025-06，A12）; as-of 2024-11~2026-09
    'cny_rf_gap': 0.015,  # 利率轴货币段差 USD/HKD 中枢 4.0 − CNY 2.5；只用于人民币口径披露行，不进底牌（同 `0728.HK` A4）; as-of 2026-09-18
    'dry_shock': 0.16,  # 特枯年 EPS 冲击，2022 年实测（A8）；只用于压力坐标; as-of FY2022
    'debt_fy25': 2880,  # 有息负债亿 CNY（A7）；只进 +100bp 披露; as-of 2025-12-31
    'net_debt_fy25': 2834,  # 净债务亿 CNY（A7）；只披露; as-of 2025-12-31
    'ebit_fy25': 426.0,  # 营业利润亿 CNY（A7）；只披露; as-of FY2025
    'ebitda_fy25': 620,  # 营业利润 + 折旧摊销亿 CNY（A7）；只披露; as-of FY2025
    'interest_fy25': 95.1,  # 利息费用亿 CNY（A7）；只披露; as-of FY2025
    'tax_rate': 0.16,  # 实际所得税率（所得税 67.9 ÷ 利润总额）；只进 +100bp 披露; as-of FY2025
    'v_opt': 0,  # A11; as-of 2026-10-10
    'ss_return': 0.144,  # 新投资**稳态回报**（三档同值）= 自身投入资本回报按现行杠杆折回股东口径：云川注入后 FY2023–25 投入资本回报约 8.0% + 有息负债 / 权益 1.23 ×（8.0% − 税后债务成本 2.8%）≈ 14.4%，与前瞻、\(g_2\)、r 同一把权益尺（A16；用户 2026-10-19 认可）; as-of 2026-10-19
    't0_ret': 2028,  # 回报路径起点 = 分子年 FY2028（A16）; as-of 2026-10-16
    'y1_ret': 2028,  # 高回报期 Y1 = 可见年末（最远共识年 FY2028）（A16）; as-of 2026-10-16
    'y2_ret': 2034,  # 高回报期 Y2 = Y1 + 6 年（进入门槛「高」，依据见 A16）; as-of 2026-10-16
}

TIERS = ("l", "m", "h")
YI = 1e8

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-segment RONIC path (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    gordon.py helper is not built yet).  Multiple on the numerator year t0 (t = 1): retention
    of calendar year c earns the forward roe while c <= y1, falls linearly to the steady
    return by y2, and from y2 on the steady return holds in a Gordon tail (r_s capped at the
    forward roe).  g <= 0 never consumes RONIC -> plain perpetuity."""
    if g <= 0:
        return perpetual_pe(g, roe, r)
    rs = min(roe, r_s)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs
        return roe + (rs - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g / rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g / ron(cal)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1


def roll(eps: float, g: float, bps0: float, unbooked: float) -> tuple[float, float, float]:
    """Fixed point of BPS_open = bps0 + b1 x unbooked, ROE = eps / BPS_open, b1 = g / ROE."""
    b1 = 0.0
    for _ in range(100):
        bps = bps0 + b1 * unbooked
        roe = eps / bps
        b1 = g / roe
    return bps, roe, b1


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('t0_ret', 'y1_ret', 'y2_ret'))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, payout = inp['r_perp'], inp['payout_policy']
    if r <= -1 or inp['r_disc'] <= -1 or any(r <= inp[f'g2_{tier}'] for tier in TIERS):
        raise ValueError('invalid discount or perpetual-growth domain')
    warnings = []
    eps = {t: inp[f'eps_{t}'] for t in TIERS}
    g2 = {t: inp[f'g2_{t}'] for t in TIERS}
    k = {t: inp[f'k_{t}'] for t in TIERS}
    errors += check_r(r, 'r_perp', 2)
    if abs(inp['r_disc'] - r) > 1e-12:
        errors.append('drift discount rate must equal r_perp')
    errors += ladder('eps', eps['l'], eps['m'], eps['h'])
    for t in TIERS:
        errors += check_g_cap(g2[t], r, f'g2_{t}')
        if k[t] != 0:
            errors.append(f'{t}: debt-repayment retention must have zero discount')
    if inp['bps0'] <= 0 or inp['shares'] <= 0:
        raise ValueError('book value and shares must be positive')
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []
    disc = (1 + inp['r_disc']) ** -inp['n_disc']
    bps0 = inp['bps0']
    unbooked = inp['eps26_m'] - inp['eps_1h26'] + inp['eps27_m']
    if unbooked <= 0:
        warnings.append('historical_window_earnings_nonpositive')

    _, roe_m_pol, _ = roll(eps['m'], (1 - payout) * .16, bps0, unbooked)
    for _ in range(50):
        g_pol = (1 - payout) * roe_m_pol
        _, roe_m_pol, _ = roll(eps['m'], g_pol, bps0, unbooked)
    cap = g_cap(r)
    if g_pol <= cap:
        errors.append('policy growth no longer exceeds cap')
    for t in ('m', 'h'):
        if abs(g2[t] - cap) > 1e-9:
            errors.append(f'{t} growth must equal basket cap')
    if abs(g2['l'] - (1 - payout) * inp['roe_marg_l']) > .0005:
        errors.append('L growth differs from policy retention times regulated return')
    if g2['l'] > g2['m']:
        errors.append('L growth exceeds M growth')
    bps, roe, b1 = {}, {}, {}
    for t in TIERS:
        bps[t], roe[t], b1[t] = roll(eps[t], g2[t], bps0, unbooked)
        if not (0 < b1[t] < 1):
            errors.append(f'{t} reinvestment outside (0,1)')
        errors += check_branch(g2[t], roe[t], r, payout, f'tier_{t}')
    if errors:
        warnings.append('historical_growth_and_retention_require_review')
        errors = []

    def leg_pe(g, ro, rr, steady=None):
        steady = inp['ss_return'] if steady is None else steady
        return path_pe(g, ro, rr, int(inp['t0_ret']), int(inp['y1_ret']), int(inp['y2_ret']),
                       max(steady, rr))

    pe = {t: leg_pe(g2[t], roe[t], r) for t in TIERS}
    for t in TIERS:
        if not (inp['pe_own_min'] - 1e-9 <= pe[t] <= inp['pe_own_max'] + 1e-9):
            errors.append(f'{t} PE outside own history')
    if not (inp['pe_same_min'] - 1e-9 <= pe['m'] <= inp['pe_same_max'] + 1e-9):
        errors.append('M PE outside same-earnings band')
    if errors:
        warnings.append('historical_pe_band_unverified')
        errors = []
    f_win = (1 + inp['r_disc']) ** (-inp['n_disc'] / 2)
    window = {t: (1 - b1[t]) * unbooked * f_win for t in TIERS}
    anchor = {t: eps[t] * pe[t] * disc * (1 - k[t]) + window[t] for t in TIERS}
    L, M, H = anchor['l'], anchor['m'], anchor['h']
    if not all(math.isfinite(v) for v in (L, M, H)) or not L < M < H:
        raise ValueError('base valuation tiers must be finite and ordered')
    if inp['v_opt'] != 0:
        errors.append('separate option must remain zero without a profit bridge')
    flat_errors, flat = flat_multiple_ladder(tuple(eps[t] * disc for t in TIERS), pe['m'])
    errors += flat_errors
    if errors:
        warnings.append('historical_flat_ladder_or_option_requires_review')
    try:
        dec = decompose((L, M, H), tuple(pe[t] for t in TIERS))
    except (ArithmeticError, ValueError):
        dec = None
        warnings.append('historical_decomposition_unavailable')

    def band(gmap, rr, steady=None):
        out = []
        for t in TIERS:
            g = min(gmap[t], g_cap(rr))
            _, ro, bb = roll(eps[t], g, bps0, unbooked)
            out.append(eps[t] * leg_pe(g, ro, rr, steady) / (1 + rr) ** inp['n_disc'] +
                       (1 - bb) * unbooked / (1 + rr) ** (inp['n_disc'] / 2))
        return out

    as_band = lambda values: dict(zip('LMH', values))
    def optional_band(gmap, rate, steady=None):
        try:
            values = band(gmap, rate, steady)
            if all(math.isfinite(value) for value in values):
                return as_band(values)
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_sensitivity_unavailable')
        return None
    sensitivity = {}
    for name, delta in (('growth_minus_1pp', -.01), ('growth_plus_1pp', .01)):
        sensitivity[name] = optional_band({t: max(0, g2[t] + delta) for t in TIERS}, r)
    for name, delta in (('rate_minus_05pp', -.005), ('rate_plus_05pp', .005)):
        sensitivity[name] = optional_band(g2, r + delta)
    sensitivity['zero_growth'] = optional_band(dict.fromkeys(TIERS, 0), r)
    sensitivity['basket_4'] = optional_band(g2, .10)
    sensitivity['currency_rate_contrast'] = optional_band(g2, r - inp['cny_rf_gap'])
    # These three original document comparisons use alternative steady-return
    # assumptions as readouts, including the unlevered-basis contrast that
    # fails the stated M history band; none replaces the adopted model.
    for name, steady in (('old_equity_return', .157), ('fallback_return', .15), ('unlevered_return', .0798)):
        sensitivity[name] = optional_band(g2, r, steady)
    sensitivity['dry_year'] = eps['m'] * (1 - inp['dry_shock']) * pe['l'] * disc
    sensitivity['interest_plus_1pp_eps'] = -inp['debt_fy25'] * .01 * (1 - inp['tax_rate']) * YI / inp['shares']
    sensitivity['flat_multiple'] = as_band(flat)
    a, b = cut_points(L, M, H)
    # 三档均采用三段 Gordon。
    def optional_ratio(numerator, denominator):
        try:
            value = numerator / denominator
            return value if math.isfinite(value) else None
        except (ArithmeticError, TypeError, ValueError):
            return None
    debt_ratio = optional_ratio(inp['net_debt_fy25'], inp['ebitda_fy25'])
    interest_ratio = optional_ratio(inp['interest_fy25'], inp['ebit_fy25'])
    if debt_ratio is None or interest_ratio is None:
        warnings.append('historical_leverage_reference_unavailable')
    return {'ticker': '600900.SH', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-16',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b},
            'candidate': None, 'option': None, 'segments': {'company': {'values': as_band((L, M, H))}},
            'review_flags': warnings,
            'key_parameters': {'method': dict.fromkeys('LMH', 'gordon_three_stage'),
                               'discount_rate': dict.fromkeys('LMH', r),
                               'growth_rate': as_band(g2[t] for t in TIERS),
                               'forward_return': as_band(roe[t] for t in TIERS),
                               'steady_return': as_band(min(roe[t], max(inp['ss_return'], r)) for t in TIERS),
                               'multiple': as_band(pe[t] for t in TIERS)},
            'operating': {'eps': as_band(eps[t] for t in TIERS), 'opening_bps': as_band(bps[t] for t in TIERS),
                          'reinvestment': as_band(b1[t] for t in TIERS), 'window': as_band(window[t] for t in TIERS),
                          'unbooked': unbooked, 'policy_growth': g_pol, 'decomposition': dec,
                          'extra_retention': as_band((1 - payout - b1[t]) * eps[t] for t in TIERS),
                          'payout_gap': {t.upper(): payout_gap(g2[t], roe[t], payout) for t in TIERS},
                          'leverage': [debt_ratio, interest_ratio]},
            'sensitivity': sensitivity}


def calculate(context):
    result = evaluate(dict(INPUTS))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'unit_scale': YI}, BASELINE_LOCAL)
    return result
