#!/usr/bin/env python3
"""Historical LONGi recovery model; JSON is a calculation, not publication.

Amounts: CNY 100 million; shares: 100 million; prices: CNY/share.
Profit forecasts are attributable after tax. Actuals are not forecasts.
Sources: 2026Q3 https://pdf.dfcfw.com/pdf/H2_AN202610301831232498_1.pdf
Guojin https://pdf.dfcfw.com/pdf/H3_AP202611011831293917_1.pdf
Zhongyou https://pdf.dfcfw.com/pdf/H3_AP202609121829316734_1.pdf
Pacific https://pdf.dfcfw.com/pdf/H3_AP202609211829729587_1.pdf
Historical filings and return-proxy limitations are documented in 601012.SH.md.
2018: https://pdf.dfcfw.com/pdf/H2_AN201904291323960541_1.pdf
2020: https://pdf.dfcfw.com/pdf/H2_AN202104201486642974_1.pdf
2021: https://pdf.dfcfw.com/pdf/H2_AN202204271561950208_1.pdf
2025: https://pdf.dfcfw.com/pdf/H2_AN202604281821711124_1.pdf
"""
from __future__ import annotations

import math

from lib import gordon, inputs
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis'), 'axes': {}}

# 建模意图（2026-11-05，以下为研究判断而非新的预测）：
# - 公司中报将硅片与组件合并披露，缺乏可靠分部资本；整公司主尺暂用
#   组件/电池主要业务的篮 4，硅片单独使用篮 6 的估算仅作交叉，不能
#   将内部供货毛利重复相加。储能已并入集团预测，未取得可剥离的新增
#   利润桥，因此不另加期权；不等于储能资产价值为零。
# - 低档利润采用 2018 年实际弱盈利重现，倍数是 2017 年相近盈利月份
#   的实付下沿，包含市场当时的修复预期；并不假设永久亏损，也不把它
#   冒充 2028 年卖方预测。2017 年样本的业务、股本及增长预期与今天不同。
# - 2028 年中性和乐观利润分别取中邮和太平洋预测；2026 年第四季度亏损
#   及 2027 年窗口利润均按各档计算。两家机构预测经营现金流扣资本开支
#   后高于归母利润，支持窗口利润可分配的条件判断，但不等于承诺分红或
#   证明未来资本需求为零；若现金流或资本开支偏离，应重新判断资金用途。
# - 2028 利润除最新权益经窗口调整的资本，仅作前瞻回报代理，不是实测
#   RONIC。历史 2018—2024 回报代理折成经营资本口径后作为成熟上限；
#   与中邮原表 2027 期初权益不同，导致中档代理约 11.29% 而非 10.25%。
#   历年一年内到期项目的预计负债未逐年完整拆分，因此这一历史序列
#   只是回报代理，不是审计后、同口径的新增投资回报。
#   长期名义增长 4% 为原研究的宏观默认，不延长恢复期的高增速。
# - 已识别净现金扣除两个月经营现金需求后未达单列门槛；整公司利润中
#   的利息保留，因此不再加一次现金。其他非流动负债 36.55 亿元全视为
#   类债只是压力比较；转债本金已计债，偿债和转股需比较，不能重复扣。
# - 历史强盈利候选取 2020/2021 年已实现利润，不等于跨周期中枢；
#   2028 回报向 2032 成熟参考回落，不恢复当年高增长或历史高倍数。
#   支持升级的原研究条件是可比库存持续去化并接近约 30 万吨目标、
#   至少连续两个季度扣非盈利及经营现金流为正、至少两家同年预测
#   上调至约 80 亿元，须重新核实。
#   花旗 2026-10-13 的约 60 万吨降至 30 万吨去库目标有自身库存口径，
#   不与其他机构生产商库存直接拼接。2021-12-31 前复权收盘约 60.82 元
#   （Longbridge，复权基准 2026-11-05）仅为历史坐标，不和未归一 EPS 相除。
# - 隆基精控在 2026-01-07 取得 32.6189% 经济权益，并因表决权委托取得
#   63.8795% 控制权；购买日至 2026H1 收入 4.9768 亿、净亏损 1.2726 亿，
#   已计入合并口径。电站分部 2026H1 净利 1.7762 亿并非归母净利润。
# - 资金释放仅为改变增长投资可释放份额的条件敏感性；模型隐含的
#   18.55 亿元不是已证明能释放的现金，永久释放不并入正式价值。
# - 美国清洁能源支持与公司具体准入、订单、毛利、回款是不同条件；
#   USTR 2024-09-13 对华关税公告是历史参照，并不证明任何未来政策或
#   公司可取得补贴。没有可归属隆基的增量利润桥时不加政策期权。
# 历史与业务口径资料：2026H1 https://pdf.dfcfw.com/pdf/H2_AN202608301828733975_1.pdf
# 西南分业务研究（2025-09-14）：https://pdf.dfcfw.com/pdf/H3_AP202509161744846231_1.pdf
# 美国贸易政策历史：https://ustr.gov/about-us/policy-offices/press-office/press-releases/2024/september/ustr-finalizes-action-china-tariffs-following-statutory-four-year-review

INPUTS = {
    'shares': 75.78069833,  # 股本；2026Q3合并资产负债表；as-of 2026-09-30
    'equity_0': 467.2126896221,  # 归母权益；2026Q3合并报表；as-of 2026-09-30
    'ni_9m': -47.1327077266,  # 已入账前三季度归母利润；as-of 2026-09-30
    'r_perp': 0.1,  # 篮4常规经营：主要腿为组件及电池制造，按整公司主尺暂用主要腿篮子；硅片风险不消失；as-of 2026-11-05
    'g2': 0.04,  # 正常名义增长的契约宏观层；非恢复期CAGR；as-of 2026-11-05
    'tau': 1.25,  # 财报基准日至2028年初；按15个月；as-of 2026-09-30
    'q4_t': 0.125,  # 2026Q4利润中点折现；as-of 2026-09-30
    'fy27_t': 0.75,  # 2027利润中点折现；as-of 2026-09-30
    'ni26_l': -59.15,  # 2026低端预测；国金；as-of 2026-11-01
    'ni27_l': 17.45,  # 2027低端预测；太平洋；as-of 2026-09-19
    'ni28_l': 25.5796408973,  # 2018实测弱盈利在2028复现的情景输入；不是当前预测；as-of 2018-12-31
    'pe_l': 17.15767012661012,  # 相近归一EPS月份实付倍数下沿，2017-05；as-of 2017-05-31
    'ni26_m': -50.5396,  # 中邮2026预测；as-of 2026-09-11
    'ni27_m': 23.0084,  # 中邮2027预测；as-of 2026-09-11
    'ni28_m': 52.3734,  # 中邮2028预测，三家中位；as-of 2026-09-11
    'ni26_h': -55.57,  # 太平洋2026预测；as-of 2026-09-19
    'ni27_h': 17.45,  # 太平洋2027预测；as-of 2026-09-19
    'ni28_h': 58.15,  # 太平洋2028预测，三家上沿；as-of 2026-09-19
    'hist_return_proxy': 0.22849653531488442,  # 2018—2024整公司投入资本回报代理均值；含公司层面投资收益，非纯组件边际回报；as-of 2024-12-31
    'total_equity': 488.0898804384,  # 合并权益，含少数股东；as-of 2026-09-30
    'identified_net_cash': 120.5240880043,  # 已识别净现金；未扣经营现金需求，不是可分配现金；as-of 2026-09-30
    'candidate_profit_low': 85.5236916081,  # 2020实测归母利润，仅作条件情景水平；as-of 2020-12-31
    'candidate_profit_high': 90.858805133,  # 2021实测归母利润，仅作条件情景水平；as-of 2021-12-31
    'return_visible_year': 2028.0,  # 可见预测终点，不额外延长高回报期；as-of 2026-11-05
    'return_steady_year': 2032.0,  # 中等进入门槛的4年回落审计；基础前瞻低于上限，因此基础倍数无额外回落层；as-of 2026-11-05
    'op_profit_28': 64.0,  # 中邮2028报表营业利润预测；不是剔除投资及其他收益的标准化EBIT；as-of 2026-09-11
    'tax_28': 8.6,  # 中邮2028所得税预测，表内舍入数；as-of 2026-09-11
    'pretax_28': 61.5,  # 中邮2028利润总额预测，表内舍入数；as-of 2026-09-11
    'needed_cash': 117.2450832507,  # FY25收入两个月的经营现金锚；非额外股权价值；as-of 2025-12-31
    'release_years': 3.0,  # 资金用途有限期对照为2028—2030，非已承诺释放；as-of 2026-11-05
    'convertible_principal': 69.94696,  # 隆22转债2025年末本金，债口径已含在识别债务；as-of 2025-12-31
    'convertible_strike': 17.5,  # 已核实转股价，后续下修须更新；as-of 2026-11-05
    'v_opt': 0.0,  # 未找到可与整公司预测明确剥离的新增利润单位；非储能零价值；as-of 2026-11-05
}

TIERS = ('l', 'm', 'h')
HISTORICAL_PARTIAL_FINGERPRINT = '531cf5cc30a8641efb8af06be428d2764e86e951e24eca801de6a6ff57d200bf'


def economic_multiple(p: dict[str, float], growth: float, forward_return: float) -> float:
    cap = p['hist_return_proxy'] * (p['total_equity'] - p['identified_net_cash']) / p['total_equity']
    steady = min(forward_return, cap)
    if steady == forward_return:
        return gordon.perpetual_pe(growth, forward_return, p['r_perp'])
    years = int(p['return_steady_year'] - p['return_visible_year'])
    value = 0.0
    for step in range(years):
        investment_return = forward_return + (steady - forward_return) * step / years
        value += ((1 + growth) ** step * (1 - growth / investment_return) /
                  (1 + p['r_perp']) ** (step + 1))
    return value + ((1 + growth) ** years * gordon.perpetual_pe(growth, steady, p['r_perp']) /
                    (1 + p['r_perp']) ** years)


def value(p: dict[str, float], tier: str, *, profit: float | None = None,
          growth: float | None = None, fixed_multiple: float | None = None) -> tuple[float, float]:
    profit = p[f'ni28_{tier}'] if profit is None else profit
    growth = p['g2'] if growth is None else growth
    q4 = p[f'ni26_{tier}'] - p['ni_9m']
    equity = p['equity_0'] + q4
    window = (q4 / (1 + p['r_perp']) ** p['q4_t'] +
              p[f'ni27_{tier}'] / (1 + p['r_perp']) ** p['fy27_t'])
    multiple = economic_multiple(p, growth, profit / equity) if fixed_multiple is None else fixed_multiple
    return (profit * multiple / (1 + p['r_perp']) ** p['tau'] + window) / p['shares'], multiple


def released_value(p: dict[str, float], fraction: float, years: int | None) -> float:
    equity = p['equity_0'] + p['ni26_m'] - p['ni_9m']
    annual = fraction * p['g2'] * equity
    if years is None:
        return annual / (p['r_perp'] - p['g2']) / (1 + p['r_perp']) ** p['tau'] / p['shares']
    return sum(annual * (1 + p['g2']) ** step /
               (1 + p['r_perp']) ** (p['tau'] + 1 + step)
               for step in range(years)) / p['shares']


def evaluate(p: dict[str, float]) -> dict:
    missing = inputs.check_missing(p, list(INPUTS))
    if missing:
        raise ValueError('; '.join(missing))
    if any(not math.isfinite(p[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    errors = gordon.check_r(p['r_perp'], 'whole company', 4)
    errors += gordon.check_g_cap(p['g2'], p['r_perp'], 'whole company')
    if p['shares'] <= 0 or p['total_equity'] <= p['identified_net_cash'] or p['convertible_strike'] <= 0:
        errors.append('invalid shares, capital or convertible strike')
    if any(p['equity_0'] + p[f'ni26_{t}'] - p['ni_9m'] <= 0 for t in TIERS):
        errors.append('model equity must be positive')
    if p['return_steady_year'] <= p['return_visible_year'] or p['return_steady_year'] - p['return_visible_year'] != int(p['return_steady_year'] - p['return_visible_year']):
        errors.append('return fade must end after its visible year on a whole year')
    if p['v_opt'] != 0:
        errors.append('separate option requires an independently modeled profit bridge')
    if errors:
        raise ValueError('; '.join(errors))

    rows = {t: value(p, t, fixed_multiple=p['pe_l'] if t == 'l' else None) for t in TIERS}
    band = lambda vals: dict(zip('LMH', vals))
    anchors = [rows[t][0] for t in TIERS]
    # An unusable historical-profit scenario must not suppress the base band.
    try:
        candidate = [anchors[0], value(p, 'm', profit=(p['candidate_profit_low'] + p['candidate_profit_high']) / 2)[0],
                     value(p, 'h', profit=p['candidate_profit_high'])[0]]
    except (ValueError, ZeroDivisionError, OverflowError):
        candidate = None
    if candidate is not None and (not all(math.isfinite(v) for v in candidate)
                                  or inputs.ladder('historical profit candidate', *candidate)):
        candidate = None
    errors += inputs.ladder('base', *anchors)
    errors += inputs.ladder('earnings', *(p[f'ni28_{t}'] for t in TIERS))
    flat = [value(p, t, fixed_multiple=rows['m'][1])[0] for t in TIERS]
    errors += inputs.ladder('flat multiple', *flat)
    def conversion_is_more_dilutive(price):
        converted = ((price * p['shares'] + p['convertible_principal']) /
                     (p['shares'] + p['convertible_principal'] / p['convertible_strike']))
        return price > converted + 1e-9
    if any(conversion_is_more_dilutive(price) for price in anchors):
        errors.append('conversion is more dilutive than the adopted debt case')
    if candidate is not None and any(conversion_is_more_dilutive(price) for price in candidate):
        candidate = None
    release = None
    if (not isinstance(p['release_years'], bool) and p['release_years'] > 0
            and p['release_years'] == int(p['release_years'])):
        release = {}
        for fraction in (0.0, 0.5, 1.0):
            try:
                finite = released_value(p, fraction, int(p['release_years']))
                permanent = released_value(p, fraction, None)
                half = released_value(p, fraction / 2, int(p['release_years']))
            except (ValueError, ZeroDivisionError, OverflowError):
                release = None
                break
            if (not all(math.isfinite(value) for value in (finite, permanent, half))
                    or not 0 <= finite <= permanent + 1e-9
                    or abs(finite - 2 * half) > 1e-9):
                release = None
                break
            release[str(fraction)] = {'finite': anchors[1] + finite, 'permanent': anchors[1] + permanent}
    if errors:
        raise ValueError('; '.join(errors))
    equity = [p['equity_0'] + p[f'ni26_{t}'] - p['ni_9m'] for t in TIERS]
    forward = [p[f'ni28_{t}'] / e for t, e in zip(TIERS, equity)]
    cap = p['hist_return_proxy'] * (p['total_equity'] - p['identified_net_cash']) / p['total_equity']
    candidate_forward = [(p['candidate_profit_low'] + p['candidate_profit_high']) / 2 / equity[1],
                         p['candidate_profit_high'] / equity[2]]
    capital = p['total_equity'] - p['identified_net_cash']
    # These two return ratios are historical cross-checks, not inputs to the
    # primary valuation. Missing denominators do not erase the computed band.
    after_tax = None if p['pretax_28'] == 0 else p['op_profit_28'] * (1 - p['tax_28'] / p['pretax_28'])
    if after_tax is not None and not math.isfinite(after_tax):
        after_tax = None
    roic_without_cash = None if after_tax is None else after_tax / capital
    roic_with_cash = None if after_tax is None or capital + p['needed_cash'] <= 0 else after_tax / (capital + p['needed_cash'])
    if roic_without_cash is not None and not math.isfinite(roic_without_cash):
        roic_without_cash = None
    if roic_with_cash is not None and not math.isfinite(roic_with_cash):
        roic_with_cash = None
    sensitivity = {name: band([value(p, t, growth=p['g2'] + delta,
                                    fixed_multiple=p['pe_l'] if t == 'l' else None)[0] for t in TIERS])
                   for name, delta in (('growth_minus_1pp', -.01), ('growth_plus_1pp', .01))}
    return {'ticker': '601012.SH', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-11-05',
            'anchors': band(anchors), 'candidate': (
                {'label': '历史盈利水平复现', 'status': 'unavailable', 'anchors': None}
                if candidate is None else
                {'label': '历史盈利水平复现', 'anchors': band(candidate),
                 'parameters': {'forward_return': band([None, *candidate_forward]),
                                'steady_return': band([None, *(min(f, cap) for f in candidate_forward)])}}),
            'option': None,
            'roic_static_proxies': {'excluding_needed_cash': roic_without_cash,
                                    'including_needed_cash': roic_with_cash},
            'segments': {'company': {'unit': 'CNY_PER_SHARE', 'values': band(anchors)}},
            'key_parameters': {'discount_rate': {'unit': 'RATIO', 'values': band([None, p['r_perp'], p['r_perp']])},
                               'growth_rate': {'unit': 'RATIO', 'values': band([None, p['g2'], p['g2']])},
                               'forward_return': {'unit': 'RATIO', 'values': band([None, *forward[1:]])},
                               'steady_return': {'unit': 'RATIO', 'values': band([None, *(min(f, cap) for f in forward[1:])]),
                                                 'reference_value': cap},
                               'multiple': band([rows[t][1] for t in TIERS]),
                               'shared_return_reference': cap},
            'sensitivity': {**sensitivity, 'flat_multiple': band(flat), 'cash_release': release}}


def calculate(context):
    result = evaluate(INPUTS)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['review_flags'] = ['historical_cash_and_funding_unverified',
                              'historical_return_proxy_and_peer_basis_unverified',
                              'historical_company_forecasts_unverified']
    if any(value is None for value in result['roic_static_proxies'].values()):
        result['review_flags'].append('historical_return_crosscheck_unavailable')
    if result.get('sensitivity', {}).get('cash_release') is None:
        result['review_flags'].append('historical_cash_release_comparison_unavailable')
    return result
