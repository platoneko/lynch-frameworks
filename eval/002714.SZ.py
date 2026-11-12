#!/usr/bin/env python3
"""Historical Muyuan cycle and conditional clearing scenarios.

Profit per kg is CNY; head count is in 10,000; shares are individual shares.
2026Q3 report and monthly sales source links remain in the document. User
accepted the basket-4 judgment after the historical same-earnings band was
found distorted; its initial basket-6 comparison is retained. The annual
trough followed by recovery is a condition, not a guaranteed floor.

H is the 3 CNY/kg clearing-success center, not an observed new consensus.
The two-year high-price overlap is only a high-tier candidate. The 2024 sale
price and 2026 cost are separate historical observations, not an observed
joint outcome or a validated forecast, and the combination has no probability.
"""
# Historical model rationale retained from the document:
# Low margin -1.62 CNY/kg comes from parent losses of 93.05 CNY 100 million
# over 57.55 hundred-million kg in 2021Q3–2022Q2 (quarterly reports and
# monthly sales). A second trough lasted approximately five quarters;
# one-year recovery is a modeling condition, not an observed certainty.
# The two surplus-cycle samples produced parent profits of 1.15 and 1.13
# CNY/kg; the adopted 1.2 before minority interest uses FY2025 parent/total
# earnings 154.87/158.12. It is not a claim about current profitability.
# The 3.0 successful-clearing center refers to the 2014–2018 cycle's
# year-weighted approximation, not the 2.2–2.6 volume-weighted result.
# Company scale and competitors differed substantially; the treatment was
# explicitly accepted as the H condition on 2026-11-08, not a proven center.
# The 10% discount rate was retained by the user after disclosure that the
# matched historical valuation band was distorted and that the original
# commodity-cycle classification implies 13%; the latter remains a contrast.
# The candidate combines FY2024 realized price 16.32 with an approximate
# 2026-09 cost 11.5 CNY/kg. Neither their joint occurrence nor two-year
# persistence has been established; its gate requires two independent profit
# bridges, two matching quarters, and evidence against rapid restocking.
# FY2025 capex 95.3 versus depreciation 144.7 CNY 100 million and net debt
# reduction supported the old debt-repayment interpretation. The 2026Q3
# cash-flow deficit and borrowing weakened it; incurred shortfalls are not
# additionally deducted as an estimated future growth funding gap.
# Sources: 2026Q3 report, 2026-10-29 company IR, monthly sales reports,
# 2025 annual report, and historical annual/monthly records as linked in the
# document. Nationwide Q3 sow count was a media relay and lacks an independently
# verified primary release and four-quarter series.
from __future__ import annotations

import math
from lib.gordon import basket_r, check_g_cap, check_r, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = '67ab343563b3741d806ab29ed2eaf693d69e2e14d518ce3c8cdc218679f89e62'

INPUTS = {
    'shares_total': 5772996144,  # 总股本，含 H 股 310,223,100 股；Q3 可转债转股新增 69 股（[CB]、[Q3]）; as-of 2026-09-30
    'shares_treasury': 69586523,  # 回购专户持股数量不变；净股数 5,703,409,621，不用库存股账面金额反推（A17，[Q3]）; as-of 2026-09-30
    'heads_m': 7140,  # 稳态年出栏（万头）= `sows_cap` × `heads_per_sow` = 300 × 23.8（A2）；2026 年指引 7,500–8,100 由 2025 年约 336 万头母猪支撑，不是稳态; as-of 2026-09-27
    'sows_cap': 300,  # 模型母猪上限（万头）保留；9 月实际 297.4，目标已兑现，不把一个季末实际当永久上限（A2，[S9]）; as-of 2026-09-30
    'heads_per_sow': 23.8,  # 每头能繁母猪一年对应出栏 = 当年出栏 ÷ 上一年四个季末能繁母猪均值，2023 / 2024 / 2025 = 24.0 / 23.8 / 23.5 取均值（月度简报与定期报告；2026 指引中点对 2025 均值 23.2，逐年略降）; as-of FY2025
    'kg_per_head': 125,  # 稳态均重 kg 保留；1–9 月按月收入 ÷ 均价合计 73.6641 亿公斤 ÷ 5,873 万头 ≈ 125.43，不机械替换长期均重（A2，[S9]）; as-of 2026-09-30
    'm_l': -1.62,  # **L** 每公斤归母利润 = 取样窗口（2021Q3 起，A15）内实测最差连续 4 季 2021Q3–2022Q2（A3）; as-of 2022-06-30
    'np_l_4q': -93.05,  # 该 4 季归母合计：−8.22 − 18.0 − 51.8 − 15.03（季报）; as-of 2022-06-30
    'kg_l_4q': 57.55,  # 该 4 季销售公斤 = 月度销售简报收入 ÷ 商品猪均价逐月加总（2021-07 → 2022-06，收入 780.41 亿）; as-of 2022-06-30
    'm_center_total': 1.2,  # **M** 中枢每公斤净利（少数股东前）：2021Q3 起两个完整周期实测（归母）1.15 / 1.13 → 少数股东前 ≈ 1.17–1.18，取 1.2；交叉：5 年平均 ROE 15.2% × BPS ≈ 1.25、同业毛利差小且未扩大（A4）; as-of 2026-06-30
    'np_parent_fy25': 154.87,  # FY2025 归母净利；归母转化分子（A4）; as-of FY2025
    'np_total_fy25': 158.12,  # FY2025 全口径净利；归母转化分母 → 0.9794; as-of FY2025
    'm_h': 2.90,  # **峰值对照，不进 H** 每公斤归母利润 = 实测最好连续 4 季 2024Q3–2025Q2（A15）; as-of 2025-06-30
    'np_h_4q': 275.82,  # 该 4 季归母合计：96.52 + 74.0 + 44.91 + 60.39（季报）; as-of 2025-06-30
    'kg_h_4q': 95.0,  # 该 4 季销售公斤（销售简报）; as-of 2025-06-30
    'cost_full': 11.5,  # 9 月实际“略低于 11.5”，无精确小数；保留 11.5 为峰值对照成本的保守近似；底牌不直接进公式（[IR]，A1 / A16）; as-of 2026-09-30
    'm_center_clear': 3.0,  # H「出清·紧平衡」的中枢每公斤净利（少数股东前）：紧平衡时定价的是被政策挡在外面的高成本边际产能——边际产能现金成本 13.3–13.7（GS 94286）− 牧原 11.5 ≈ 2，加新产能 2–3 年回本的要求；与牧原非瘟前完整周期实测下沿（2014–18 约 3.0，2014–17 约 3.5–3.7，A4）一致；仅作为 A16 条件成功的 H 分子，不替换 M; as-of 2026-09-27
    'price_realized_2024': 16.32,  # 2024 年牧原商品猪实现均价元/kg（月度销售简报收入 ÷ 商品猪均价加权，A12）；只进 A21 峰值候选：双击情景的猪价，不进主锚点; as-of FY2024
    'bps': 13.5915,  # 归母权益 775.1789 亿 ÷ 净股数 57.0341 亿；含可转债权益成分，剔除对照 13.4132（A19，[Q3]）；只判单调区，不进 g=0 倍数; as-of 2026-09-30
    'r_perp': 0.10,  # 篮 4 龙头制造 ← 初分篮 6 周期商品（市场证据，③ 降篮门，A10）：全国第一、17 家覆盖；13% / 11% 下倍数仍低于同等盈利带下沿，降至下限；值 = `gordon.BASKET_R[4]`，`check_r` 按篮子强制; as-of 2026-09-27
    'g2': 0,  # 永续 g（自定，无同业锚）：政策锁量 + 猪肉需求平；≤ cap min(6%, r − 4%) = 6%；留存去向 A 桶（A6）; as-of 2026-09-27
    'pe_band_min': 20.88,  # 同等盈利月份带下沿（TTM EPS 落在 EPS_M ±12% 的 9 个月；2023-11）——**失真带**，不作降篮 / 带边证据（A11）；只校验 ③ 披露行; as-of 2026-09-26
    'pe_band_max': 26.54,  # 同等盈利月份带上沿（2020-02；失真，A11）; as-of 2026-09-26
    'm_consensus_2027': 2.75,  # 2027 历史共识每公斤利润；**共识待更新**（2026-11-02 未取得财报后同口径分布，见 A13）；仅历史比较与区间检验，不进公式; as-of 2026-09-22
    'payout_fy25': 0.48,  # FY2025 派息率 = 分红 74.38 ÷ 归母 154.87；对账门股息坐标用，**不进公式**; as-of FY2025
    'pb_low_5y': 2.47,  # 自身 5 年 PB 低点（2026-07，Longbridge 估值历史）；对账门资产坐标用，**不进公式**; as-of 2026-09-26
    'capex_fy25': 95.3,  # FY2025 capex 亿；跟踪项，**不进公式**；连续两年 > 折旧 → 回退留存完整式（A6）; as-of FY2025
    'da_fy25': 144.7,  # FY2025 折旧亿（固定资产 + 生产性生物资产）；**不进公式**; as-of FY2025
    'net_debt_h1': 597.9,  # 净债务亿（Longbridge）；杠杆门读数用，**不进公式**（A7）; as-of 2026-06-30
    'net_debt_q3': 559.7001,  # 本期净债务重建：短借 + 一年内到期非流动负债 + 长借 + 债券 + 非流动租赁 − 现金等价物 − 交易性金融资产；定义及类债压力对照见 A7; as-of 2026-09-30
    'net_debt_q3_stress': 571.8168,  # 再把其他权益工具 10.1713 亿与长期应付款 1.9454 亿全作现金兑付压力；杠杆门压力对照，不重复扣进 EPS 估值（A7）; as-of 2026-09-30
    'np_parent_9m26': -93.1875230525,  # 前三季度归母净利，亿；实际跟踪，不替换完整周期中枢（[Q3]）; as-of 2026-09-30
    'np_total_9m26': -93.3410608313,  # 前三季度全口径净利，亿；A12 近似利润桥用（[Q3]）; as-of 2026-09-30
    'np_parent_q326': -32.4109902631,  # Q3 单季归母，亿（[Q3]）; as-of 2026-09-30
    'np_parent_9m25': 147.7890495709,  # 上年同期归母，亿；本期比较数，A15 新增滚动四季窗口验证用（[Q3]）; as-of 2025-09-30
    'kg_9m26': 73.6640650752,  # 亿公斤，按 [S9] 1–9 月逐月商品猪收入 ÷ 均价相加，近似量，不是披露精确销量公斤; as-of 2026-09-30
    'ocf_9m26': 29.8329206922,  # 前三季度经营现金流净额，亿（[Q3]）; as-of 2026-09-30
    'capex_9m26': 87.1840588899,  # 前三季度购建固定资产、无形资产及其他长期资产支付现金，亿；不覆盖 FY2025 字段（[Q3]）; as-of 2026-09-30
    'tax_9m26': 4.0045663909,  # 前三季度所得税费用，亿；税项来源待附注，不能推定免税取消（[Q3]，A8）; as-of 2026-09-30
    'sows_actual_q3': 297.4,  # 期末实际能繁母猪，万头；与模型上限 sows_cap 分列（[S9]）; as-of 2026-09-30
}

YI = 1e8
WAN = 1e4
N_RECOVERY_L = 1
N_DECAY_H = 2
FROM_BASKET = 6

def band(eps: dict[str, float], roe_m: float, r: float, g2: float,
         peak_eps: float = 0.0, peak_years: int = 0) -> tuple[float, float, float, float]:
    """Trough recovery, observed center, and conditional clearing-success center."""
    pe_m = perpetual_pe(g2, roe_m, r)
    m = eps["M"] * pe_m
    # Trough: one year of the loss, then the business is worth M again.
    ell = (eps["L"] + m) / (1 + r) ** N_RECOVERY_L
    roe_h = roe_m * eps["H"] / eps["M"]
    steady_h = eps["H"] * perpetual_pe(g2, roe_h, r)
    h = (sum(peak_eps / (1 + r) ** t for t in range(1, peak_years + 1))
         + steady_h / (1 + r) ** peak_years)
    return ell, m, h, pe_m


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r = inp['r_perp']
    errors += check_r(r, 'r_perp', 4)
    errors += check_g_cap(inp['g2'], r, 'g2')
    if any(key in inp for key in ('k_l', 'k_m', 'k_h')):
        errors.append('discount k rows must not reappear')
    if abs(inp['heads_m'] - inp['sows_cap'] * inp['heads_per_sow']) > .01 * inp['heads_m']:
        errors.append('head count differs from sow cap times output')
    shares = inp['shares_total'] - inp['shares_treasury']
    if min(shares, inp['np_total_fy25'], inp['kg_l_4q'], inp['kg_h_4q'], inp['bps']) <= 0:
        errors.append('invalid model denominator')
    if errors:
        raise ValueError('; '.join(errors))
    kg = inp['heads_m'] * WAN * inp['kg_per_head']
    conv = inp['np_parent_fy25'] / inp['np_total_fy25']
    margin = {'L': inp['m_l'], 'M': inp['m_center_total'] * conv, 'H': inp['m_center_clear'] * conv}
    for tag, np4, kg4 in (('L', 'np_l_4q', 'kg_l_4q'), ('H', 'np_h_4q', 'kg_h_4q')):
        measured = inp[np4] / inp[kg4]
        if abs(measured - inp[f'm_{tag.lower()}']) > .01:
            errors.append(f'{tag} measured four-quarter margin differs from input')
    eps = {t: margin[t] * kg / shares for t in 'LMH'}
    errors += ladder('EPS', eps['L'], eps['M'], eps['H'])
    roe_m, roe_h = eps['M'] / inp['bps'], eps['H'] / inp['bps']
    if roe_m - r < .03 or roe_h - r < .03:
        errors.append('M or H return outside monotone zone')
    if errors:
        raise ValueError('; '.join(errors))

    L, M, H, pe_m = band(eps, roe_m, r, inp['g2'])
    errors += ladder('anchors', L, M, H)
    flat = tuple(eps[t] * pe_m for t in 'LMH')
    errors += ladder('flat-multiple anchors', *flat)
    historical_band_reentered = pe_m >= inp['pe_band_min']
    consensus_outside_scenarios = not (margin['M'] <= inp['m_consensus_2027'] <= margin['H'])
    if errors:
        raise ValueError('; '.join(errors))

    b6 = band(eps, roe_m, basket_r(FROM_BASKET), inp['g2'])[:3]
    eps_peak = inp['m_h'] * kg / shares
    peak = sum(eps_peak / (1 + r) ** t for t in range(1, N_DECAY_H + 1)) + M / (1 + r) ** N_DECAY_H
    eps_double = (inp['price_realized_2024'] - inp['cost_full']) * conv * kg / shares
    candidate = band(eps, roe_m, r, inp['g2'], eps_double, N_DECAY_H)[:3]
    errors += ladder('candidate anchors', *candidate)
    if errors:
        raise ValueError('; '.join(errors))
    g_up = band(eps, roe_m, r, inp['g2'] + .01)[:3]
    g_dn = band(eps, roe_m, r, inp['g2'] - .01)[:3]
    a, b = cut_points(L, M, H)
    ac, bc = cut_points(*candidate)
    as_band = lambda xs: dict(zip('LMH', xs))
    # L 一年谷底后回归; M 周期中枢永续; H 出清成功中枢永续.
    result = {'ticker': '002714.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-11-08', 'historical_framework_as_of': '2026-11-08',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b},
            'candidate': {'label': '出清叠加两年峰值', 'anchors': as_band(candidate), 'cut_points': {'A': ac, 'B': bc}},
            'option': None, 'segments': {'company': {'values': as_band((L, M, H))}},
            'key_parameters': {'method': {'L': 'one_year_trough_recovery', 'M': 'cyclical_midpoint_perpetuity', 'H': 'supply_clearance_success_perpetuity'},
                               'discount_rate': dict.fromkeys('LMH', r),
                               'growth_rate': {'L': None, 'M': inp['g2'], 'H': inp['g2']},
                               'forward_return': {'L': None, 'M': roe_m, 'H': roe_h},
                               'steady_return': {'L': None, 'M': roe_m, 'H': roe_h},
                               'multiple': {'L': None, 'M': pe_m, 'H': H / eps['H']}},
            'operating': {'shares_net': shares, 'kg': kg, 'parent_fraction': conv, 'margin': margin, 'eps': eps,
                          'consensus_deviation': 1 - margin['M'] / inp['m_consensus_2027'],
                          'basket_multiples': {str(b): perpetual_pe(inp['g2'], roe_m, basket_r(b)) for b in range(FROM_BASKET, 3, -1)},
                          'dividend_coordinate': inp['payout_fy25'] * eps['M'] / r,
                          'pb_coordinate': inp['bps'] * inp['pb_low_5y']},
            'sensitivity': {'basket_6': as_band(b6), 'growth_plus_1pp': as_band(g_up), 'growth_minus_1pp': as_band(g_dn),
                            'flat_multiple': as_band(flat), 'former_peak_reference': peak,
                            'peak_perpetuity_reference': eps_peak / r, 'candidate_peak_eps': eps_double}}

    result['historical_band_reentered'] = historical_band_reentered
    result['consensus_outside_scenarios'] = consensus_outside_scenarios
    return result


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'units_100m': YI, 'units_10k': WAN,
         'recovery_years': N_RECOVERY_L, 'peak_years': N_DECAY_H, 'comparison_basket': FROM_BASKET},
        HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'] = ['historical_recovery_duration_unverified',
                              'historical_supply_clearance_assumptions_unverified',
                              'historical_candidate_peak_requires_evidence']
    if result['historical_band_reentered']:
        result['review_flags'].append('historical_pe_distortion_needs_review')
    if result['consensus_outside_scenarios']:
        result['review_flags'].append('current_consensus_outside_model_scenarios')
    return result
