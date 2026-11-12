#!/usr/bin/env python3
"""Historical Nanjing Tanker cycle model, not updated research.

Amounts CNY 100 million except shares_total; outputs CNY/share. Source dates,
reports and existing financial judgments remain in the framework and input
comments. M is the 2018–2025 observed cycle return, L is a one-year measured
trough followed by recovery, and H is the old consensus path before returning
to M. Newbuilding/ownership costs and a post-quarter acquisition have not been
fully bridged; quarter-end cash recognition is a condition, not proof that
the amount remains distributable after the acquisition.

The user accepted 11% after the clean historical earnings band ruled out the
initial 13%; this is a rate value borrowed from basket 5, not a bank label.
Candidate 19.1% cycle profitability represents 2022–2025 tight conditions,
not a statistical probability or already adopted sustainable center.
"""
# Historical context retained from the document: FY2018–2025 operating
# returns were 6.4, 14.8, 15.6, 5.1, 19.2, 20.0, 21.3 and 15.8 percent;
# the eight-year 14.8% average spans weak and tight supply but not the size
# of the then-current orderbook. The 2018 and 2021 troughs each recovered in
# about a year; that observation does not establish the next trough's length.
# The 2022–2025 average 19.1% is a conditional alternative center. Promotion
# requires 2027 and 2028 net tanker fleet growth at most 2%, sanctions not
# easing or vessels materially returning, and company ROIC at least 18% for
# two consecutive half-years from 2028; no statistical probability is used.
# A 2026-10-30 cash acquisition occurred after the 2026-09-30 cash basis.
# Its liabilities, assets, profits and cash require a single consolidated
# bridge; neither subtracting consideration alone nor treating quarter-end cash
# as confirmed distributable proceeds is justified. The original zero funding
# gap is unverified while newbuild payment schedules remain incomplete.
# Sources include 2026Q3 report, 2026-026 board and 2026-028 completion
# announcements, 2018–2025 reports, and the 2026-10-29 dated forecast cache.
from __future__ import annotations

import math
from lib.gordon import basket_r, check_g_cap, check_r
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = 'b76038f65f2b8595a69f2f9737040e7e1ef99088881b6d76655b02bf27127502'

INPUTS = {
    'shares_total': 4680344678,  # 总股本，无库存股（A18）；2026 三季报第 8 页; as-of 2026-09-30
    'equity_parent': 124.6645262443,  # 归母权益；2026 三季报第 8 页; as-of 2026-09-30
    'nci': 1.6234017734,  # 少数股东权益；2026 三季报第 8 页; as-of 2026-09-30
    'cash': 48.4212127959,  # 货币资金；现金等价物差额 0.1642 亿用途待补（A6）；季报第 6、13 页; as-of 2026-09-30
    'debt_cur': 2.1933171335,  # 一年内到期非流动负债，含当期租赁/借款部分，整体计债，不重复另加当期租赁；季报第 8 页; as-of 2026-09-30
    'debt_lt': 3.9391299112,  # 长期借款；不含单列非流动租赁负债，季报第 8 页; as-of 2026-09-30
    'debt_lease': 2.0292441345,  # 非流动租赁负债，季报第 8 页；一年内到期部分已含 debt_cur; as-of 2026-09-30
    'op_cash_anchor': 0,  # 经营所需现金锚 = max(0, min(FY2018–25「净现金 ÷ 收入」最低值, 2 个月收入)) × 收入；最低值为负（2018 −0.86）→ 0（A6）; as-of FY2025
    'np_parent_fy25': 13.11,  # FY2025 归母净利；归母转化分子; as-of FY2025
    'np_total_fy25': 13.23,  # FY2025 全口径净利；归母转化分母 → 0.991; as-of FY2025
    'tax_rate': 0.16,  # 有效税率：所得税 ÷ 利润总额 FY2023 / 2024 / 2025 = 15.6% / 16.0% / 16.0%; as-of FY2025
    'cash_yield': 0.0208,  # 超额现金税前收益率 = FY2025 利息收入 0.93 ÷ 平均货币资金（A6）; as-of FY2025
    'roic_center': 0.148,  # **M** 中枢 ROIC = FY2018–25 八年实测平均（年末经营资本口径，A1）; as-of FY2025
    'roic_center_soft': 0.105,  # FY2018–21 宽松期四年平均；只进多年低谷压力坐标（A13），**不进锚点**; as-of FY2021
    'roic_center_tight': 0.191,  # FY2022–25 紧平衡四年平均；只进 A16 候选带; as-of FY2025
    'kf_l_4q': 2.57,  # **L** 最差连续 4 季扣非合计 2020Q4–2021Q3：0.08 + 1.06 + 1.01 + 0.42（季报，A2）; as-of 2021-09-30
    'intexp_l_4q': 0.95,  # 该 12 个月利息费用代理（FY2021 年报利息费用）; as-of FY2021
    'ic_l_avg': 68.45,  # 该 12 个月平均经营资本 = (FY2020 66.2 + FY2021 70.7)/2; as-of FY2021
    'ronic_hist': 0.105,  # 自身谷到谷（2018–21）平均 ROIC；RONIC = max(本值, r)（A7）; as-of FY2021
    'r_perp': 0.11,  # 篮 5（值 11%）← 初分篮 6 周期商品：盈利是运价函数；同等盈利干净带 [8.71, 10.38] 下沿高于 13% 的 7.69×，③ 逐档降一档入带即停（市场证据，A4 / A5）; as-of 2026-10-26
    'g2': 0.025,  # 永续 g：宏观下限（具名理由：国内成品油需求萎缩，A7 / A15）；≤ cap min(6%, r − 4%) = 6%; as-of 2026-10-26
    'np_cons_2026': 18.23,  # 2026 归母共识，10 家，同花顺日期快照；共识待更新，非全体财报后刷新，本轮实时页 403（A3）; as-of 2026-10-29
    'np_cons_2027': 20.10,  # 2027 归母共识，9 家；同上，共识待更新; as-of 2026-10-29
    'np_cons_2028': 21.50,  # 2028 归母共识，8 家；同上，共识待更新; as-of 2026-10-29
    'np_ytd_2026': 11.3786984042,  # 前三季度已实现归母；H 只取 Q4 余量，2026 三季报第 1 页; as-of 2026-09-30
    'np_gh_2026': 19.07,  # 国海证券 2026 归母（2026-09-04）；只进披露坐标，**不进锚点**（A17）; as-of 2026-09-04
    'np_gh_2027': 26.87,  # 国海证券 2027 归母；同上; as-of 2026-09-04
    'np_gh_2028': 30.10,  # 国海证券 2028 归母；同上; as-of 2026-09-04
    'roic_best_fy': 0.213,  # 实测最好年份 ROIC（FY2024）；②-b 检验用，**不进公式**; as-of FY2024
    'pe_band_min': 8.71,  # 干净同等盈利带下沿（经营口径，2021-01，A5）; as-of 2026-10-26
    'pe_band_max': 10.38,  # 干净同等盈利带上沿（2020-09）; as-of 2026-10-26
    'pe_band_median': 9.94,  # 15 个同等盈利月份中位；对账坐标用，**不进公式**; as-of 2026-10-26
    'pb_low_5y': 1.18,  # 自身 5 年 PB 低点（2025-04，Longbridge 估值历史）；对账坐标用，**不进公式**; as-of 2026-10-26
    'newbuild_remaining': 56,  # 仅中报旧合同剩余款估计，Q3 未重报，不冒充季末实际；只进披露坐标，分年付款待补（A8）; as-of 2026-06-30
    'gp_dom_fy25': 7.72,  # FY2025 内贸毛利（24.06 − 16.33）；只进分腿交叉（A10）; as-of FY2025
    'gp_for_fy25': 9.06,  # FY2025 外贸毛利（34.08 − 25.02）；同上; as-of FY2025
}

YI = 1e8
N_RECOVERY_L = 1
T_PATH = (.25, 1.25, 2.25)
FROM_BASKET = 6
TO_BASKET = 5


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, g2 = inp['r_perp'], inp['g2']
    if r <= 0 or r <= g2:
        raise ValueError('invalid discount or perpetual-growth domain')
    warnings = []
    errors += check_r(r, 'r_perp', TO_BASKET)
    errors += check_g_cap(g2, r, 'g2')
    if min(inp['shares_total'], inp['equity_parent'] + inp['nci'], inp['np_total_fy25'], inp['ic_l_avg']) <= 0:
        raise ValueError('invalid model denominator')
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []

    shares = inp['shares_total'] / YI
    tax = inp['tax_rate']
    nc = inp['cash'] - inp['debt_cur'] - inp['debt_lt'] - inp['debt_lease']
    par = inp['equity_parent'] / (inp['equity_parent'] + inp['nci'])
    cex = max(nc - inp['op_cash_anchor'], 0) * par
    ic = inp['equity_parent'] + inp['nci'] - nc + inp['op_cash_anchor']
    if ic == 0:
        raise ValueError('operating capital must not be zero')
    conv = inp['np_parent_fy25'] / inp['np_total_fy25']
    cinc = cex * inp['cash_yield'] * (1 - tax)
    roic_l = (inp['kf_l_4q'] + inp['intexp_l_4q'] * (1 - tax)) / inp['ic_l_avg']
    e_l = roic_l * ic * conv
    e_m = inp['roic_center'] * ic * conv

    def path(c26, c27, c28):
        return list(zip(T_PATH, (c26 - inp['np_ytd_2026'] - cinc * T_PATH[0], c27 - cinc, c28 - cinc)))

    cons = path(inp['np_cons_2026'], inp['np_cons_2027'], inp['np_cons_2028'])
    gh = path(inp['np_gh_2026'], inp['np_gh_2027'], inp['np_gh_2028'])

    def band(r_, em=e_m, p=cons, g=g2):
        ronic = max(inp['ronic_hist'], r_)
        pe = (1 - g / ronic) / (r_ - g)
        vm = em * pe
        m = (vm + cex) / shares
        ell = ((e_l + vm) / (1 + r_) ** N_RECOVERY_L + cex) / shares
        h = (sum(e / (1 + r_) ** t for t, e in p) + vm / (1 + r_) ** T_PATH[-1] + cex) / shares
        return ell, m, h, pe

    L, M, H, pe = band(r)
    if not all(math.isfinite(value) for value in (L, M, H)) or not L < M < H:
        raise ValueError('base valuation tiers must be finite and ordered')
    if abs(pe - 1 / r) > 1e-9:
        errors.append('RONIC no longer equals r; 1/r disclosure needs review')
    eps_flat = (e_l / shares, e_m / shares, cons[-1][1] / shares)
    errors += ladder('operating EPS', *eps_flat)
    roic_cons28 = cons[-1][1] / conv / ic if conv else None
    if roic_cons28 is None:
        warnings.append('historical_consensus_return_unavailable')
    elif roic_cons28 <= inp['roic_best_fy']:
        errors.append('2028 consensus no longer above historical best; H must be rebuilt')
    if not (inp['pe_band_min'] <= pe <= inp['pe_band_max']):
        errors.append('PE outside clean equal-earnings band')
    pe_from = 1 / basket_r(FROM_BASKET)
    if pe_from >= inp['pe_band_min']:
        errors.append('initial basket PE back inside band; step-down record needs review')
    if errors:
        warnings.append('historical_economic_guards_require_review')
        errors = []
    def optional_band(rate, **kwargs):
        try:
            if rate <= 0 or rate <= kwargs.get('g', g2):
                raise ValueError('invalid sensitivity discount or perpetual growth')
            values = band(rate, **kwargs)[:3]
            if all(math.isfinite(value) for value in values):
                return values
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_sensitivity_unavailable')
        return None

    b6, b4 = optional_band(basket_r(FROM_BASKET)), optional_band(basket_r(4))
    cand = optional_band(r, em=inp['roic_center_tight'] * ic * conv)
    if cand is None or ladder('candidate anchors', *cand):
        warnings.append('historical_candidate_unavailable')
        cand = None
    g_up, g_dn = optional_band(r, g=g2 + .01), optional_band(r, g=g2 - .01)
    gh_band = optional_band(r, p=gh)
    soft_band = optional_band(r, em=inp['roic_center_soft'] * ic * conv)
    gh_h = gh_band[2] if gh_band is not None else None
    soft_m = soft_band[1] if soft_band is not None else None
    regime_l = (e_l / r + cex) / shares
    regime_h = (cons[-1][1] / r + cex) / shares
    gross_total = inp['gp_dom_fy25'] + inp['gp_for_fy25']
    w_dom = inp['gp_dom_fy25'] / gross_total if gross_total else None
    split_m = (e_m * w_dom / basket_r(4) + e_m * (1 - w_dom) / r + cex) / shares if w_dom is not None else None
    if split_m is None:
        warnings.append('historical_split_comparison_unavailable')
    nb_pen = inp['newbuild_remaining'] * (1 - inp['ronic_hist'] / r) * par / shares
    coord_min = inp['pe_band_min'] * e_m / shares + cex / shares
    coord_med = inp['pe_band_median'] * e_m / shares + cex / shares
    coord_pb = inp['pb_low_5y'] * inp['equity_parent'] / shares
    a, b = cut_points(L, M, H)
    ca, cb = cut_points(*cand) if cand is not None else (None, None)
    as_band = lambda xs: dict(zip('LMH', xs))
    maybe_band = lambda xs: as_band(xs) if xs is not None else None
    # L 一年低谷后回归；M 周期中枢 Gordon；H 预测窗口后回中枢。
    return {'ticker': '601975.SH', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-11-02',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b},
            'candidate': ({'label': '出清紧平衡', 'anchors': as_band(cand), 'cut_points': {'A': ca, 'B': cb}}
                          if cand is not None else {'label': '出清紧平衡', 'status': 'unavailable', 'anchors': None}),
            'option': None, 'segments': {'company': {'values': as_band((L, M, H))}},
            'review_flags': warnings,
            'key_parameters': {'method': {'L': 'one_year_trough_recovery', 'M': 'gordon_cyclical_midpoint', 'H': 'forecast_window_then_midpoint'},
                               'discount_rate': dict.fromkeys('LMH', r),
                               'growth_rate': {'L': None, 'M': g2, 'H': g2},
                               'forward_return': dict.fromkeys('LMH', None),
                               'steady_return': dict.fromkeys('LMH', max(inp['ronic_hist'], r)),
                               'multiple_m': pe},
            'operating': {'shares_yi': shares, 'netcash': nc, 'parent_ratio': par, 'excess_cash': cex,
                          'capital': ic, 'parent_conversion': conv, 'cash_income': cinc,
                          'roic_low': roic_l, 'earnings_low': e_l, 'earnings_middle': e_m,
                          'consensus_path': cons, 'guohai_path': gh, 'consensus_2028_roic': roic_cons28},
            'sensitivity': {'basket_6': maybe_band(b6), 'basket_4': maybe_band(b4),
                            'growth_plus_1pp': maybe_band(g_up), 'growth_minus_1pp': maybe_band(g_dn),
                            'guohai_high': gh_h, 'multi_year_trough_middle': soft_m,
                            'regime_low': regime_l, 'regime_high': regime_h, 'domestic_foreign_middle': split_m,
                            'newbuild_penalty': nb_pen, 'equal_earnings_coordinates': [coord_min, coord_med],
                            'pb_coordinate': coord_pb}}


def calculate(context):
    result = evaluate(dict(INPUTS))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'].extend(['historical_newbuild_funding_unverified',
                                   'historical_post_quarter_acquisition_cash_bridge_unverified'])
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'unit_scale': YI, 'recovery_years': N_RECOVERY_L,
         'cashflow_path': T_PATH, 'original_basket': FROM_BASKET, 'adopted_basket': TO_BASKET}, BASELINE_LOCAL)
    return result
