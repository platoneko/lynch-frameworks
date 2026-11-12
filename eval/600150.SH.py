#!/usr/bin/env python3
"""Historical finite shipbuilding supercycle; not a new forecast.

Amounts and share counts are in CNY and shares; outputs are CNY/share.
The FY2028 forecasts are from the original three analyst sources; source links
and financial evidence remain in the framework. The 2035 plateau and 2039
normalization are research assumptions, not a company commitment. Forward
investment returns follow the separate 2028–2030 path. Post-cycle earnings
use annualized reported profit, not a validated full-cycle average.

Existing cash is recognized as in the prior decision, while occupation and
release are sensitivity conditions, not proof of either immediate distribution
or permanent loss. The original FY2025 downside PE is policy, not validated
matched historical trading. The user authorized the existing scenario and its
disclosed gaps; no unannounced asset injection or extra option is valued.
"""
# Historical context and unresolved conditions retained from the document:
# FY2028 group forecasts: Dongwu 312.45, Shenwan 300.10 and Guojin 381.49
# CNY 100 million; Shenwan is a dated forecast-detail record without the full
# report. They are a partially refreshed sample, not full-market consensus.
# The 2035 plateau uses 2032–33 industry demand plus 2–3 years delivery lag;
# the four-year fade to 2039 is a research assumption, not a company promise.
# Cycle-normal profit uses 9M2026 annualized reported earnings less cash
# income; it retains seasonality and nonrecurring items and is not an observed
# full-cycle average. Forward capital returns are proxies, not proven RONIC.
# The low 10.700106 multiple was already chosen in the prior scenario; after
# the merger it is not backed by matched-earnings paid-price evidence.
# Existing 937.28 CNY 100 million attributable cash is recognized as before,
# but contract liabilities and delivery financing have not been reconciled
# year by year. A zero cash-release scenario keeps income and principal in
# operations; additional occupation is a separate condition, not a default.
# FY2025 reported tax rate 1.97%, H1 2026 10.00%; H1 losses and deferred tax
# cannot be transferred freely across entities or assumed to persist forever.
# Guojin FY2028 forecast tax around 1.9% remains a near-term forecast input,
# not an assumed permanent tax rate; report-profit reference uses its own
# observed tax. Q3 merger-related 6.92 CNY 100 million tax effect is subject
# to audit. Company reports and tax notes remain the source for those limits.
from __future__ import annotations

import math

from lib.gordon import check_g_cap, check_r
from lib.inputs import check_missing, ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.zones import cut_points

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis', 'zones'), 'axes': {}}
BASELINE_LOCAL = '02122595020fc5a1ec6604a81dcd05877bb8e3c5342910a526e3f3f90b521432'

INPUTS = {
    'shares': 7525621288,  # 三季报总股本; as-of 2026-09-30
    'equity': 153740402641.59,  # 归母权益，已反映中期股利，不重复扣；三季报; as-of 2026-09-30
    'minority': 7090043780.99,  # 少数股东权益；现金归母比例用; as-of 2026-09-30
    'net_cash_ext': 126897171793.24,  # 货币资金减有息债务与租赁；沿用扩展口径; as-of 2026-09-30
    'div_payable': 3516585022.87,  # 应付股利；只从候选现金扣一次; as-of 2026-09-30
    'np_9m': 13440070099.25,  # 已入账归母；三季报; as-of 2026-09-30
    'np_9m_core': 13540651100,  # 三季报扣非归母，公告万元精度；仅用于周期后参照敏感性，不改近端已入账归母; as-of 2026-09-30
    'np_ttm': 15436667884.33,  # FY2025 − 2025 年前三季度 + 本年前三季度归母; as-of 2026-09-30
    'cash_yield': 0.01602390887095388,  # 9M 利息收入简单年化 / 期初期末平均货币资金；是估值代理，非长期保证; as-of 2026-09-30
    'cash_tax': 0.1426234727157642,  # 9M 实际税率；只用于当前候选现金收益，非经营终值税率; as-of 2026-09-30
    'cash_release': 1,  # 沿用原超额现金单列认定；不是即刻派现承诺。0–1 为转为经营资本的条件敏感性（A12）; as-of 2026-11-05
    'extra_occupation': 0,  # 未来超出必要再投资的余款未被额外占用的条件；0–1 连续敏感性，不能由公式余数证明; as-of 2026-11-05
    'r_perp': 0.10,  # 篮 4 常规经营：逐单议价的设备制造，非商品价函数；周期进入利润路径（A3）; as-of 2026-11-05
    'g2': 0.04,  # 沿用已采用名义正常增长；平台金额仍增长，额外周期利润另由权重退出; as-of 2026-11-07
    'ronic_ss': 0.11,  # M 新投资稳态回报，沿用原商品化重资产兜底与已采用口径; as-of 2026-10-27
    'ronic_ss_h': 0.15,  # H 新投资稳态回报，沿用原低门槛高档上移一格；不是本次为配价上调; as-of 2026-10-27
    'y1': 2028,  # 最远共同预测年；原新投资回报收敛路径起点，不是周期平台终点; as-of 2026-11-07
    'y2': 2030,  # 原新投资回报收敛终点，与利润平台2035及回落终点2039分开; as-of 2026-11-07
    'tau': 1.25,  # 2026-09-30 至 2028-01-01；窗口为 Q4 + FY2027; as-of 2026-09-30
    'payout_obs': 0.35,  # FY2025 / 2026 中期实付比例约 35%；作资本约束及分配能力对照; as-of 2026-10-23
    'rev_25': 151978000000,  # FY2025收入；原经营现金锚按两个月收入，沿用既有口径; as-of FY2025
    'np_25': 7848400000,  # FY2025 实测归母；L 仅作历史消化年分子; as-of FY2025
    'equity_25': 143419000000,  # FY2025 归母权益；历史现金归属; as-of 2025-12-31
    'minority_25': 6171400000,  # FY2025 少数权益；历史现金归属; as-of 2025-12-31
    'net_cash_ext_25': 110269100000,  # FY2025 扩展净现金；L 历史收益用; as-of 2025-12-31
    'cash_yield_25': 0.02126,  # FY2025 自身现金收益率；不被本期参数覆盖; as-of FY2025
    'cash_tax_25': 0.0197,  # FY2025 自身实际税率；不外推到经营终值; as-of FY2025
    'dw_np26': 20034000000,  # 东吴归母预测；正文财务表，百万元转元; as-of 2026-11-02
    'dw_np27': 25720000000,  # 同上; as-of 2026-11-02
    'dw_np28': 31245000000,  # 同上；保留原值供归属桥; as-of 2026-11-02
    'gj_np26': 20849000000,  # 国金归母预测；原文财务表，百万元转元; as-of 2026-10-31
    'gj_np27': 30151000000,  # 同上; as-of 2026-10-31
    'gj_np28': 38149000000,  # 国金原归母预测，基准保留；税率提高仅压力测试; as-of 2026-10-31
    'annualization': 1.3333333333333333,  # 9M报告归母简单年化，存在季节性及非经常项目，不是全年指引; as-of 2026-11-07
    'normal_scale_years': 2,  # 2026报告利润参照换算至2028名义口径，不代表保留2028物理交付规模; as-of 2026-11-07
    'normal_profit_scale': 1,  # 周期后报告利润参照采用比例，另列±20%敏感性; as-of 2026-11-07
    'platform_scale': 1,  # 平台经营利润保留原预测，0.9为独立盈利敏感性; as-of 2026-11-07
    'cycle_plateau_end': 2035,  # 行业需求至2032–33年加2–3年交付滞后的研究推断，非公司承诺; as-of 2026-11-07
    'cycle_fade_end': 2039,  # 2035起四年线性退出额外周期盈利，研究假设; as-of 2026-11-07
    'low_pe': 10.7001061387363,  # 原已采用低档固定估值政策，不是历史市场实付倍数; as-of 2026-11-05
    'sw_np26': 21814000000,  # 申万财报后归母预测，东方财富明细，未取得完整原文; as-of 2026-11-01
    'sw_np27': 27460000000,  # 同一份申万预测明细; as-of 2026-11-01
    'sw_np28': 30010000000,  # 同一份申万预测明细; as-of 2026-11-01
}

HOUSES = ("dw", "sw", "gj")
REQUIRED = [
    "shares", "equity", "minority", "net_cash_ext", "div_payable", "rev_25",
    "np_9m", "np_9m_core", "cash_yield", "cash_tax", "tau", "r_perp", "g2", "ronic_ss",
    "ronic_ss_h", "y1", "y2", "cycle_plateau_end", "cycle_fade_end",
    "annualization", "normal_scale_years", "normal_profit_scale", "platform_scale",
    "cash_release", "extra_occupation", "payout_obs", "low_pe",
    "np_25", "equity_25", "minority_25", "net_cash_ext_25", "cash_yield_25", "cash_tax_25",
] + [f"{h}_np{year}" for h in HOUSES for year in (26, 27, 28)]


def cash_basis(p: dict) -> tuple[float, float]:
    parent = p["equity"] / (p["equity"] + p["minority"])
    cash = (p["net_cash_ext"] - p["div_payable"] - p["rev_25"] / 6) * parent
    interest = cash * p["cash_yield"] * (1 - p["cash_tax"])
    return cash / p["shares"], interest / p["shares"]


def distribution(p: dict, ronic: float) -> float:
    available = 1 - p["g2"] / ronic
    return available - p["extra_occupation"] * max(available - p["payout_obs"], 0)


def supercycle_value(p: dict, house: str, release: float, steady: float) -> dict:
    r, g, sh = p["r_perp"], p["g2"], p["shares"]
    cps, interest = cash_basis(p)
    peak = (p[f"{house}_np28"] / sh - release * interest) * p["platform_scale"]
    normal = (p["np_9m"] * p["annualization"] / sh - interest)
    normal *= (1 + g) ** p["normal_scale_years"] * p["normal_profit_scale"]
    # Existing cash kept in operations retains its income and capital.
    normal += (1 - release) * interest
    unbooked = (p[f"{house}_np26"] - p["np_9m"] + p[f"{house}_np27"]) / sh
    unbooked -= p["tau"] * release * interest
    book = p["equity"] / sh - release * cps
    occupied = p["extra_occupation"]
    forward = (peak - (1 - occupied) * g * unbooked)
    forward /= book + occupied * (1 - p["payout_obs"]) * unbooked
    steady = min(forward, steady)
    window = unbooked * distribution(p, forward) / (1 + r) ** (p["tau"] / 2)

    start, ron_end = int(p["y1"]), int(p["y2"])
    plateau, finish = int(p["cycle_plateau_end"]), int(p["cycle_fade_end"])
    plateau_pv = fade_pv = 0.0
    for year in range(start, finish):
        fade = max(0.0, min(1.0, (year - plateau) / (finish - plateau)))
        earnings = (peak + (normal - peak) * fade) * (1 + g) ** (year - start)
        ronic = forward + (steady - forward) * min(1.0, (year - start) / (ron_end - start))
        pv = earnings * distribution(p, ronic) / (1 + r) ** (p["tau"] + year - start + 1)
        if year <= plateau:
            plateau_pv += pv
        else:
            fade_pv += pv
    terminal = normal * (1 + g) ** (finish - start) * distribution(p, steady) / (r - g)
    terminal /= (1 + r) ** (p["tau"] + finish - start)
    return dict(value=window + plateau_pv + fade_pv + terminal + release * cps,
                window=window, plateau=plateau_pv, fade=fade_pv, terminal=terminal,
                peak=peak, normal=normal, forward=forward, cash=release * cps)


def evaluate(p: dict, release: float | None = None) -> dict:
    release = p["cash_release"] if release is None else release
    rows = [supercycle_value(p, h, release, p["ronic_ss"]) for h in HOUSES]
    mean = {k: sum(row[k] for row in rows) / len(rows) for k in rows[0]}
    upper_house = max(HOUSES, key=lambda h: p[f"{h}_np28"])
    upper = supercycle_value(p, upper_house, release, p["ronic_ss_h"])
    cps, interest = cash_basis(p)
    historic_cash = (p["net_cash_ext_25"] - p["rev_25"] / 6)
    historic_cash *= p["equity_25"] / (p["equity_25"] + p["minority_25"])
    historic_income = historic_cash * p["cash_yield_25"] * (1 - p["cash_tax_25"])
    low_eps = (p["np_25"] - historic_income) / p["shares"] + (1 - release) * interest
    # Preserve the adopted downside world independently of M's cycle duration.
    low = low_eps * p["low_pe"] + release * cps
    mid, high = mean["value"], upper["value"]
    a, b = cut_points(low, mid, high)
    effective = (mid - release * cps) / mean["peak"]
    return dict(L=low, M=mid, H=high, A=a, B=b, mean=mean, high=upper,
                rows=rows, upper_house=upper_house, effective=effective,
                low_eps=low_eps, release=release, cash=cps, interest=interest)


def calculate_historical(p: dict) -> dict:
    errors = check_missing(p, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(p[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    require_whole_years(p, ('y1', 'y2', 'cycle_plateau_end', 'cycle_fade_end', 'normal_scale_years'))
    errors += check_r(p['r_perp'], 'r_perp', 4)
    errors += check_g_cap(p['g2'], p['r_perp'], 'g2')
    dates = (p['y1'], p['y2'], p['cycle_plateau_end'], p['cycle_fade_end'])
    if not all(float(x).is_integer() for x in dates):
        errors.append('calendar years must be integers')
    if not (2028 == p['y1'] < p['y2'] <= p['cycle_plateau_end'] < p['cycle_fade_end']):
        errors.append('investment-return and profit-cycle dates inconsistent')
    if not (0 <= p['cash_release'] <= 1 and 0 <= p['extra_occupation'] <= 1):
        errors.append('funding proportions outside [0,1]')
    if not (p['g2'] < p['ronic_ss'] <= p['ronic_ss_h'] <= .15):
        errors.append('steady investment returns invalid')
    if not (p['tau'] == 1.25 and abs(p['annualization'] - 4 / 3) < 1e-12 and p['normal_scale_years'] == 2):
        errors.append('report date, annualization and nominal base must agree')
    if min(p['normal_profit_scale'], p['platform_scale'], p['low_pe'], p['shares']) <= 0:
        errors.append('profit scales, shares and downside multiple must be positive')
    if errors:
        raise ValueError('; '.join(errors))
    v = evaluate(p)
    errors += ladder('anchors', v['L'], v['M'], v['H'])
    flat = (v['low_eps'] * v['effective'] + v['release'] * v['cash'], v['M'],
            v['high']['peak'] * v['effective'] + v['release'] * v['cash'])
    errors += ladder('flat-multiple', *flat)
    for tier in ('mean', 'high'):
        row = v[tier]
        if row['normal'] > row['peak']:
            errors.append(f'{tier} profit path rises instead of normalizing')
        if abs(row['value'] - sum(row[k] for k in ('window', 'plateau', 'fade', 'terminal', 'cash'))) > 1e-10:
            errors.append(f'{tier} decomposition does not close')
    if errors:
        raise ValueError('; '.join(errors))

    cash_income = v['interest'] * p['shares']
    core_ratio = ((p['np_9m_core'] * p['annualization'] - cash_income) /
                  (p['np_9m'] * p['annualization'] - cash_income))
    changes = {
        'earlier_cycle': {'cycle_plateau_end': 2033, 'cycle_fade_end': 2037},
        'later_cycle': {'cycle_plateau_end': 2037, 'cycle_fade_end': 2041},
        'normal_profit_minus_20pct': {'normal_profit_scale': .8},
        'normal_profit_plus_20pct': {'normal_profit_scale': 1.2},
        'platform_profit_minus_10pct': {'platform_scale': .9},
        'core_earnings_reference': {'normal_profit_scale': p['normal_profit_scale'] * core_ratio},
        'growth_minus_1pp': {'g2': p['g2'] - .01},
        'growth_plus_1pp': {'g2': p['g2'] + .01},
        'extra_occupation_50pct': {'extra_occupation': .5},
        'extra_occupation_100pct': {'extra_occupation': 1},
    }
    band = lambda result: {tier: result[tier] for tier in 'LMH'}
    sensitivity = {name: band(evaluate(p | delta)) for name, delta in changes.items()}
    sensitivity['cash_separate'] = {str(q): band(evaluate(p, q)) for q in (0, .25, .5, .75, 1)}
    sensitivity['flat_multiple'] = dict(zip('LMH', flat))
    changed = p != INPUTS
    # L 消化年固定倍数及现金；M/H 有限周期现金流。
    return {'ticker': '600150.SH', 'currency': 'CNY',
            'valuation_as_of': None if changed else '2026-09-30',
            'framework_as_of': None if changed else '2026-11-07',
            'anchors': band(v), 'cut_points': {'A': v['A'], 'B': v['B']},
            'candidate': None, 'option': None, 'segments': {'company': {'values': band(v)}},
            'key_parameters': {'method': {'L': 'downturn_fixed_multiple_plus_cash', 'M': 'finite_cycle_cash_flow', 'H': 'finite_cycle_cash_flow'},
                               'discount_rate': {'L': None, 'M': p['r_perp'], 'H': p['r_perp']},
                               'growth_rate': {'L': None, 'M': p['g2'], 'H': p['g2']},
                               'forward_return': {'L': None, 'M': v['mean']['forward'], 'H': v['high']['forward']},
                               'steady_return': {'L': None, 'M': sum(min(row['forward'], p['ronic_ss']) for row in v['rows']) / len(v['rows']),
                                                 'H': min(v['high']['forward'], p['ronic_ss_h'])},
                               'low_multiple': p['low_pe'], 'effective_multiple_m': v['effective']},
            'components': {'M': v['mean'], 'H': v['high'], 'forecast_houses': dict(zip(HOUSES, v['rows'])),
                           'upper_house': v['upper_house'], 'low_eps': v['low_eps'],
                           'cash_per_share': v['cash'], 'cash_interest_per_share': v['interest']},
            'sensitivity': sensitivity}


def calculate(context):
    # The historical downside multiple lacks matched post-merger observations;
    # carry the chosen value and expose that gap rather than inventing evidence.
    result = calculate_historical(dict(INPUTS))
    result['valuation_as_of'] = result['framework_as_of'] = None
    result['historical_financial_statement_as_of'] = '2026-09-30'
    result['historical_research_as_of'] = '2026-11-07'
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'] = ['historical_low_multiple_evidence_unverified',
                              'historical_cash_release_and_funding_unverified',
                              'historical_cycle_and_tax_assumptions_require_review']
    local = {'inputs': INPUTS, 'forecast_houses': HOUSES}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(local, BASELINE_LOCAL)
    return result
