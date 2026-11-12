#!/usr/bin/env python3
"""Beibu Gulf Port's historical 2028 consensus model; not a new forecast.

Financial amounts are CNY 100 million except shares_total, which is shares;
outputs are CNY/share. Company reports, project notices and forecast sources
are retained in the original document and input comments.

The user selected basket 2 and 3.5% growth on 2026-10-29 after reviewing the
disclosed concern that most handling fees are market-priced, as well as the
basket-4 out-of-band issue. The median forecast is used for M; H is a single
analyst's canal case, not a statistically verified upper bound. Only H fades
to the historical return; L/M remain at their sub-discount-rate forward proxy.
Low-return projects reduce all scenarios. The Shawei project option is separate
and must not double count the canal growth already inside forecasts.
"""
from __future__ import annotations

import math
from lib.gordon import basket_r, check_branch, check_g_cap, check_r
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}

# 研究意图与限制（截至 2026-10-29；并非新的经营预测）：
# - 2026H1 收入约 94% 为装卸堆存，港区未披露可独立估值的分部利润；
#   整公司用同一经营模型。2019—2025 投入资本回报约由 10.3% 降至 5.0%，
#   因此增长需要结合新增投资回报，不直接按吞吐量增速增加股东价值。
# - 用户依据区域平台、需求与利润稳定裁定 7.5% 折现率和 3.5% 长期增长；
#   主要装卸收费实行市场调节价、并非全部受监管，属于保留的反向证据。
#   连续两年 ROE <5%、扣非净利连降两年或收费出现明显竞争时重审归类。
# - 同花顺 2026-10-28 的六家 2028 年预测：低 13.19、中位 14.93、均值
#   17.52、高 27.54 亿元；最高为天风 2026-06-25 单家运河情景。为避免
#   这家预测抬高中枢采用中位；均值仅作对照，不是额外一套正式预测。
# - 高档前瞻回报向 2019—2025 年平均 ROE 8.8% 回落至 2034；低/中档
#   前瞻回报低于折现率，原研究保留各自前瞻值而不人为上调。2019—2025
#   公司的投入与资本回报历史见各年报，2026 中报提供权益、股本与债务。
# - 防城港三牙 30 万吨级码头与钦州大榄坪 6—8 号泊位的公司测算回报率
#   分别为 6.28% 与 4.58%，低于 7.5%；原模型把总投资视为尚未投入而
#   按总额扣减，实际已投入金额待核。项目公告分别为 2026-01-14、
#   2026-04-28，不能把项目投资再重复扣。
# - 北海沙尾 4—5 号泊位公司测算回报率 8.07%（2026-01-14 公告），
#   同样把总投资视为尚未投入，实际已投入金额待核；各档 0/0.5/1 是
#   情景计入比例，0.5 没有统计概率依据。
#   平陆运河在预测期外的额外增长未另计：预测已含部分运河吞吐，
#   配套钦州 6—8 号泊位回报低于要求回报；新增项目不能与共识双计。
# - 2026-09-16 平陆运河通航；首月约 95 万吨（新华社、21 财经 2026-10），
#   天风转述的 2029/2035 增量为单一研究路径，非已实现货量。若 2027 年
#   公司受益吞吐低于 3000 万吨或公司总吞吐增速低于 10%，原研究要求
#   重审乐观预测，可参考财通次高预测 20.86 亿元，而非自动改写锚点。
# - 2026-10-11 恒港码头收购预案的估值与作价未定，尚未并入正式预测；
#   在获得作价、股本与标的利润之前不能直接追加价值。缺少卖方现金流
#   预测时，原研究将 FY2025 经营现金流 30.63 亿按一年半推为约 46 亿，
#   与窗口期项目余款约 25 亿及维护开支约 15 亿比较，估算资金缺口约零；
#   现金流或投资进度偏离时需重审，该历史外推不是未来资金保证。
# - 历史同等盈利月份 PE 带 10.9—19.4 倍仅作中档护栏；带内包含当时已
#   开工运河的预期，不能当成本模型以外已确定的新增价值。

HISTORICAL_PARTIAL_FINGERPRINT = '1548fbbe333dff408256c85f6c310fbcf2200c6223a69c8fd902047964d9588b'

INPUTS = {
    'shares_total': 2517084480,  # 总股本（转债已全部转股 / 赎回，A13）；2026 中报; as-of 2026-06-30
    'equity_parent': 205.52,  # 归母权益；2026 中报; as-of 2026-06-30
    'np_h1_2026': 5.58,  # 2026H1 已实现归母；窗口只取下半年; as-of 2026-06-30
    'np_cons_2026': 11.70,  # 2026 归母一致预期均值（6 家，同花顺）；窗口用; as-of 2026-10-28
    'np_cons_2027': 14.47,  # 2027 归母一致预期均值（6 家）；窗口用; as-of 2026-10-28
    'np_2028_l': 13.19,  # **L** 2028 归母一致预期最低（6 家，A2）; as-of 2026-10-28
    'np_2028_m': 14.93,  # **M** 2028 归母一致预期中位（6 家，A2）; as-of 2026-10-28
    'np_2028_h': 27.54,  # **H** 2028 归母一致预期最高（天风 2026-06-25，A2 / A9）; as-of 2026-10-28
    'np_2028_mean': 17.52,  # 2028 均值；只进披露坐标，**不进锚点**（A2）; as-of 2026-10-28
    'np_2028_h2': 20.86,  # 2028 次高家（财通 2026-08-18）；只进披露坐标（A2 / A9）; as-of 2026-10-28
    'r_perp': 0.075,  # 篮 2 管制公用事业：区域独家港口平台、需求刚性、利润稳定（用户裁定 2026-10-29；助手保留意见与篮 4 初判留痕见 A1）; as-of 2026-10-29
    'g2': 0.035,  # 永续 g：用户裁定（碰篮 2 上限 3.5%，A4）; as-of 2026-10-29
    'ret_ss': 0.088,  # H 档稳态回报 = 自身 FY2019–25 平均 ROE（A5）; as-of FY2025
    'ronic_roic_m': 0.056,  # M 档 2028 投入资本口径回报（杠杆门口径）；只进披露坐标，**不进锚点**（A3）; as-of 2026-10-29
    'payout_obs': 0.34,  # 经营口径派息率 = FY2023–25 分红率均值（无超额现金，c = 0；A6）; as-of FY2025
    'dps_fy25': 0.161,  # FY2025 每股现金分红（中期 0.081 + 年度 0.080）；DDM 对照用（A15）; as-of FY2025
    'capex_sanya': 114.03,  # 防城港 30 万吨级码头总投资（A7）; as-of 2026-01-14
    'irr_sanya': 0.0628,  # 同上，公司测项目投资税后 IRR; as-of 2026-01-14
    'capex_qz68': 30.95,  # 钦州大榄坪 6–8 号泊位总投资（A7）; as-of 2026-04-28
    'irr_qz68': 0.0458,  # 同上，公司测项目投资税后 IRR; as-of 2026-04-28
    'capex_shawei': 42.12,  # 北海沙尾 4–5 号泊位总投资（\(V_{opt}\)，A8）; as-of 2026-01-14
    'irr_shawei': 0.0807,  # 同上，公司测项目投资税后 IRR; as-of 2026-01-14
    'pe_band_min': 10.9,  # 同等盈利带下沿（M 档每股 ±12%，2022-09，A10）；护栏，**不进公式**; as-of 2026-10-28
    'pe_band_median': 13.0,  # 58 个同等盈利月份中位；护栏，**不进公式**; as-of 2026-10-28
    'pe_band_max': 19.4,  # 同等盈利带上沿；护栏，**不进公式**; as-of 2026-10-28
}

# Judgment, not measured probabilities: the 0.5 middle case reflects thin
# project IRR spread, and 0 / 1 are the existing conservative / full cases.
OPTION_WEIGHTS = {'L': 0.0, 'M': 0.5, 'H': 1.0}
TAU = 1.5  # 2026-06-30 balance sheet to 2028-01-01.
FADE_YEARS = 6  # 2028–2034, original high-barrier return fade.
YI = 1e8


def evaluate(inp, weights=None):
    if weights is None:
        weights = OPTION_WEIGHTS
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    if (not isinstance(weights, dict) or set(weights) != set('LMH')
            or any(type(weights[t]) not in (int, float) or not math.isfinite(weights[t])
                   or not 0 <= weights[t] <= 1 for t in 'LMH')):
        raise ValueError('invalid project option weights')
    r, g2 = inp['r_perp'], inp['g2']
    errors += check_r(r, 'r_perp', 2)
    errors += check_g_cap(g2, r, 'g2')
    if inp['shares_total'] <= 0 or inp['equity_parent'] <= 0 or inp['np_2028_m'] <= 0:
        errors.append('invalid shares, equity or median earnings')
    if errors:
        raise ValueError('; '.join(errors))

    sh = inp['shares_total'] / YI
    E = {'L': inp['np_2028_l'], 'M': inp['np_2028_m'], 'H': inp['np_2028_h']}
    win = inp['np_cons_2026'] - inp['np_h1_2026'] + inp['np_cons_2027']

    def band(r_=r, g=g2, e=E, deduct=True, ronic_m=None):
        b0 = inp['equity_parent'] / (1 - win * g / e['M'])
        ded = (inp['capex_sanya'] * max(0.0, 1 - inp['irr_sanya'] / r_) +
               inp['capex_qz68'] * max(0.0, 1 - inp['irr_qz68'] / r_)) / sh / (1 + r_) ** TAU
        out = {'b0': b0, 'ded': ded}
        for k, ek in e.items():
            ron = ronic_m if ronic_m is not None and k == 'M' else ek / b0
            b = g / ron
            if k == 'H' and ron > r_:
                def rt(t):
                    if t <= 1:
                        return ron
                    if t <= 1 + FADE_YEARS:
                        return ron + (inp['ret_ss'] - ron) * (t - 1) / FADE_YEARS
                    return inp['ret_ss']
                n = 1 + FADE_YEARS
                v = sum(ek * (1 + g) ** (t - 1) * (1 - g / rt(t)) / (1 + r_) ** t
                        for t in range(1, n + 1))
                v += ek * (1 + g) ** n * (1 - g / inp['ret_ss']) / ((r_ - g) * (1 + r_) ** n)
            else:
                v = ek * (1 - b) / (r_ - g)
            out[k] = (v / sh / (1 + r_) ** TAU + win * (1 - b) / sh / (1 + r_) ** (TAU / 2)
                      - (ded if deduct else 0.0))
            out[f'pe_{k}'] = v / ek
            out[f'ron_{k}'] = ron
        return out

    base = band()
    L, M, H = (base[t] for t in 'LMH')
    errors += ladder('anchors', L, M, H)
    ron_m = base['ron_M']
    errors += check_branch(g2, ron_m, r, inp['payout_obs'], 'M')
    if g2 / ron_m > 1 - inp['payout_obs']:
        errors.append('M reinvestment exceeds retained earnings')
    if base['ron_L'] >= r or ron_m >= r:
        errors.append('L / M RONIC no longer below r — persistent failure hold no longer applies')
    if not (r <= inp['ret_ss'] <= base['ron_H']):
        errors.append('steady return must sit between r and H forward return')
    errors += ladder('2028 numerator', E['L'], E['M'], E['H'])
    mean = inp['np_2028_mean']
    if not (E['M'] <= mean <= E['H']):
        errors.append('consensus mean outside M to H')
    if abs(E['M'] / mean - 1) > .20:
        errors.append('median deviates from mean by more than 20%')
    if not (inp['pe_band_min'] <= base['pe_M'] <= inp['pe_band_max']):
        errors.append('M PE outside equal-earnings band')
    if errors:
        raise ValueError('; '.join(errors))

    option = inp['capex_shawei'] * (inp['irr_shawei'] / r - 1) / sh / (1 + r) ** TAU
    plus = {tier: base[tier] + weights[tier] * option for tier in 'LMH'}
    option_errors = ladder('option-adjusted anchors', *(plus[t] for t in 'LMH'))
    if option >= 0 and option_errors:
        raise ValueError('; '.join(option_errors))
    a, b = cut_points(L, M, H)
    ao, bo = cut_points(*(plus[t] for t in 'LMH'))
    contrast = band(r_=basket_r(4))
    gdn = band(g=g2 - .01)
    # The option is 北海沙尾 4–5 号泊位; all three tiers use 集团 Gordon 完整式.
    return {'ticker': '000582.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-29', 'historical_framework_as_of': '2026-10-29',
            'anchors': {tier: base[tier] for tier in 'LMH'}, 'cut_points': {'A': a, 'B': b},
            'candidate': None,
            'option': {'label': 'beihai_shawei_berths_4_5', 'value': option, 'weights': dict(weights),
                       'anchors': plus, 'cut_points': {'A': ao, 'B': bo}},
            'segments': {'company': {'values': {tier: base[tier] for tier in 'LMH'}}},
            'key_parameters': {'method': dict.fromkeys('LMH', 'gordon_full'),
                               'discount_rate': dict.fromkeys('LMH', r), 'growth_rate': dict.fromkeys('LMH', g2),
                               'forward_return': {tier: base['ron_' + tier] for tier in 'LMH'},
                               'steady_return': {'L': base['ron_L'], 'M': base['ron_M'], 'H': inp['ret_ss']},
                               'multiple': {tier: base['pe_' + tier] for tier in 'LMH'}},
            'operating': {'window': win, 'opening_equity': base['b0'], 'project_deduction_per_share': base['ded'],
                          'profit': E},
            'sensitivity': {'basket_4': {tier: contrast[tier] for tier in 'LMH'},
                            'growth_minus_1pp': {tier: gdn[tier] for tier in 'LMH'},
                            'mean_numerator_M': band(e={**E, 'M': mean})['M'],
                            'second_highest_H': band(e={**E, 'H': inp['np_2028_h2']})['H'],
                            'high_no_deduction': band(deduct=False)['H'],
                            'roic_basis_M': band(ronic_m=inp['ronic_roic_m'])['M'],
                            'dividend_model': inp['dps_fy25'] * (1 + g2) / (r - g2)}}


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'option_weights': OPTION_WEIGHTS, 'tau': TAU,
         'fade_years': FADE_YEARS, 'units_100m': YI}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    if result['option']['value'] >= 0:
        result['option']['value_unit'] = 'CNY_PER_SHARE'
    else:
        result['option'] = {'status': 'unavailable', 'label': '沙尾泊位', 'anchors': None}
        result['option_unavailable_reason'] = 'project_return_below_required_return'
    result['review_flags'] = ['historical_project_capital_already_spent_unverified',
                              'historical_tariff_classification_and_cashflow_unverified',
                              'historical_optimistic_earnings_single_forecast']
    return result
