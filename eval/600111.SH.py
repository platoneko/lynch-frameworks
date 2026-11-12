#!/usr/bin/env python3
"""Historical Northern Rare Earth two-stage forecast model.

Amounts are CNY/share unless otherwise stated; sources and input dates are
retained in comments and the framework. 2028's two-house forecast is the
original fallback when the historical midcycle bridge failed to explain the
full forecast gap. The price-to-earnings bridge names worlds and validates
history; it is not the numerator in the adopted valuation.

Original research deemed the historical equal-earnings PE band distorted by
the high growth and ROE forecasts in 2023 that later failed. This explicit
judgment keeps the original basket; if the model re-enters the band it needs
review rather than silently changing the judgment. FY2025 retained payout is
one low-profit year, earlier dividends and forward book-value roll remain
unverified. The commodity leg kept its own forecast return instead of an
unverified separate fade; no overseas option is added without economics.

Earlier text reports a non-exempt return-fade contrast (10.76 / 12.42 /
14.08) and an approximate financing-cost shock, but the old script contains
no calculation or full assumptions for either. They remain historical
disclosures and must not be mistaken for reproduced values.
"""
from __future__ import annotations

import math

from lib.gordon import basket_r, check_branch, check_g_cap, check_r, payout, payout_gap, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.tiers import flat_multiple_ladder
from lib.zones import zone_of

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis', 'tiers', 'zones'), 'axes': {}}
BASELINE_LOCAL = '81f64ab3a26f52a84862d27fec8a4cf339319dfdb55367011ebef5ea832f5cda'

INPUTS = {
    'shares': 3615065842,  # 总股本；Longbridge static; as-of 2026-09-16
    'bps': 7.2626,  # 每股净资产 = 归母净资产 262.55 亿 ÷ 股本；2026H1 中报; as-of 2026-06-30
    'bps_fwd': 10.203,  # 前瞻 BPS（2028 末）= bps 7.2626 + 0.79 × ((2026E 1.12 − 2026H1 已入账 0.5679) + 2027E 1.47 + 2028E 1.70)；起点 2026-06-30 BPS 已含 H1 EPS，2026E 只滚 H2 尚未入账部分（H1 去重）；留存 0.79 = FY2025 单年（低利润年），近 3 年实测分红率均值 `待补`；FY2025 DPS 0.13 若在 2026-06-30 后支付须从起点扣除 `待补`；无增发 / 回购 / 转股; as-of 2026-09-19
    'eps28_l': 1.476,  # FY2028 共识下沿 = 国投 53.35 亿 ÷ 股本（A1）; as-of 2026-08
    'eps28_m': 1.698,  # FY2028 共识均值 = (1.476 + 1.92) / 2（两家）; as-of 2026-08
    'eps28_h': 1.92,  # FY2028 共识上沿 = 西部证券; as-of 2026-08-21
    'tau': 1.5,  # 时点对齐年数 τ = 估值基准日 2026-06-30（BPS 的资产负债表日）→ 分子年初 2028-01-01；按 `r_perp` 折（无篮子对），取代原「折 1 年 @10%」（A11）; as-of 2026-10-16
    'eps26_rem': 0.5521,  # 窗口内尚未入账的 2026 共识归母 EPS = 2026E 1.12 − 2026H1 已入账 0.5679（与 `bps_fwd` 同一组共识数；A11）; as-of 2026-10-16
    'eps27_win': 1.47,  # 窗口内 FY2027 共识 EPS（国投 1.35 / 西部 1.70 口径，与 `bps_fwd` 同；A11）; as-of 2026-10-16
    'r_perp': 0.13,  # 篮 6 周期商品 / 小盘 13%：整公司单腿，盈利是镨钕价 × 配额量的商品价函数（A10；真源 `eval/lib/gordon.py BASKET_R`）；13 / 11 / 10% 下 M 倍数 8.2 / 10.3 / 11.7× 均低于 `pe_band_lo` 13.8，但该带经 1b 核验失真，不能据它降篮 → ③ 不可判定，尺子留初分篮; as-of 2026-09-19
    'capex_fy25': 13,  # FY2025 资本开支（亿元）；序列 10 / 11 / 17 / 13（2022–25）vs D&A 5 / 5 / 7 / 10 → 增长 capex 3–10 亿可忽略（§4.0 三桶，属性 D）; as-of FY2025
    'cash': 52.8,  # 现金（亿元）vs 有息债 71–84 → 无净现金；留存进库存与现金为财务性桶，不进倍数; as-of 2026-06-30
    'g1_window': 0.044,  # 窗口增长率 \(g_1\) = GS NdPrO 需求 2026 97.7 kt → 2035 144.6 kt 区间 CAGR（Wisburg 90834；tier 3 具名宏观）；这是两端点的 9 年平均，不是永续；量的宏观锚（配额随需求），价不进 g；cap = 6%; as-of 2026-06-02
    'n_window': 7,  # 窗口年数 = 2029–2035（分子年 FY2028 之后到 GS 预测期末）；窗口后转 `g2`; as-of 2026-09-19
    'pe_band_lo': 13.8,  # 同等盈利实测带下沿：TTM EPS 1.48–1.83 的 8 个月（2023-01→08）最低 PE（2023-03，TTM 1.829）；LB PE 月序列 × 自建 TTM；带经 1b 核验失真（A10），只作护栏坐标; as-of 2026-09-16
    'pe_band_hi': 16.7,  # 同上带上沿（2023-08，TTM 1.479）；中位 15.3; as-of 2026-09-16
    'g2': 0.025,  # 窗口后永续 \(g_2\) = 2.5%（§13 商品腿 tier 默认 = CNY 通胀；稀土实际价格漂移走轴不进 g；§4.0 留存财务性，A3 / 属性 D）；cap = min(6%, r − 4%) = 6%; as-of 2026-09-19
    'eps28_ths': 1.83,  # 同花顺 2028E 均值（9 家，区间 1.48–1.98），vs 本仓 1.698 +8%；分子上修坐标 13.9，**不进公式**（A1）; as-of 2026-09-18
    'payout_obs': 0.21,  # 实付派息率 = FY2025 DPS 0.13 ÷ EPS 0.6227；`check_branch`；**单年且为低利润年**，`bps_fwd` 用的留存 0.79 = 1 − 0.21 只是过渡取值，近 3 年（FY2023–25）实测分红率均值 `待补` 后替换; as-of 2026-06-11
    'pb_floor': 2.4,  # 资产地板倍数 = 自身 5 年实测 PB 谷底（2024-02 月点；A5）；只披露不 max()（§13）——地板 17.43 > H 14.92，在 [L, H] 外; as-of 2026-09-18
    'bridge_a': -0.6906,  # 桥截距（A2）；不入主公式; as-of 2026-09-16
    'bridge_b': 0.02493,  # 桥斜率 EPS / (万元/吨)（A2）；不入主公式; as-of 2026-09-16
    'ndpr_mid': 57.2,  # 5 年（2021–25）氧化镨钕年均价均值 万/吨；对照坐标（A8）; as-of 2026-09-16
    'ndpr_now': 72.75,  # 氧化镨钕现货 万/吨；生意社；坐标; as-of 2026-09-16
    'eps_trough': 0.2778,  # FY2024 实测谷底 EPS；`deep_discount` 压力坐标（A8）; as-of 2025-04
}

MIN_R_MINUS_G = .02
RECONCILE_TOL = .20
BRIDGE_GATE = {'FY2023': (53.0, .6558), 'FY2025': (51.45, .6227)}
BRIDGE_EXTRA = {'FY2024': (40.3, .2778), 'FY2026H1_annualized': (74.05, 1.1358)}
BRIDGE_TOL = .20
PHASE2_VOLUME_X = 1.55
PRE_CONTROL_PRICE = 21.0
NDPR_REGIME_MID = 70.0
BAND_DISTORTED = True  # Original 2023 high expectations failed; see A10.

def window_pe(g1: float, n: int, g2: float, roe: float, r: float) -> float:
    """Two-stage multiple on next-period earnings, as the framework writes it.

    Numerator year is t=1.  E_1..E_n grow at g1 (E_t = E_1 (1+g1)^(t-1)) and
    pay out 1 - g1/ROE; E_{n+1} = E_n (1+g2) starts the Gordon tail, valued at
    t=n.  This differs from lib.gordon.two_stage_pe only in the first tail
    year growing at g2 rather than g1 — the framework's stated construction,
    which the deck numbers reproduce.
    """
    if r - g2 <= 0:
        raise ValueError(f"perpetuity diverges: g2={g2} >= r={r}")
    p1, p2 = payout(g1, roe), payout(g2, roe)
    stage1 = sum(p1 * (1.0 + g1) ** (t - 1) / (1.0 + r) ** t for t in range(1, n + 1))
    tail = p2 * (1.0 + g1) ** (n - 1) * (1.0 + g2) / ((r - g2) * (1.0 + r) ** n)
    return stage1 + tail


def evaluate(inp, band_distorted=BAND_DISTORTED):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    require_whole_years(inp, ('n_window',))
    r = inp['r_perp']
    errors += check_r(r, 'r_perp', 6)
    g1, n_win, g2 = inp['g1_window'], int(inp['n_window']), inp['g2']
    errors += check_g_cap(g2, r, 'g2')
    errors += check_g_cap(g1, r, 'g1_window')
    if r - g2 < MIN_R_MINUS_G:
        errors.append('r minus terminal growth below pole guard')
    eps28 = (inp['eps28_l'], inp['eps28_m'], inp['eps28_h'])
    errors += ladder('eps28', *eps28)
    errors += [f'probability-style input {k}' for k in inp if k.startswith('p_')]
    if inp['bps_fwd'] <= 0 or inp['shares'] <= 0:
        errors.append('invalid forward book value or shares')
    tau = inp['tau']
    if tau < 0:
        errors.append('tau must not be negative')
    if errors:
        raise ValueError('; '.join(errors))

    roe = tuple(e / inp['bps_fwd'] for e in eps28)
    errors += check_branch(g2, roe[1], r, inp['payout_obs'], 'M')
    pes = tuple(window_pe(g1, n_win, g2, value, r) for value in roe)
    out_of_band = any(not (inp['pe_band_lo'] - 1e-6 <= pe <= inp['pe_band_hi'] + 1e-6) for pe in pes[1:])
    if out_of_band != band_distorted:
        errors.append('historical band status changed; reassess distortion and basket')
    disc = (1 + r) ** -tau
    eps_d = tuple(e * disc for e in eps28)
    win_eps = inp['eps26_rem'] + inp['eps27_win']

    def window(roe_x, g1_=g1, r_=r, tau_=tau):
        return max(win_eps * (1 - g1_ / roe_x), 0) / (1 + r_) ** (tau_ / 2)

    win = tuple(window(value) for value in roe)
    L, M, H = (e * pe + w for e, pe, w in zip(eps_d, pes, win))
    errors += ladder('anchors', L, M, H)
    flat_errors, flat = flat_multiple_ladder(eps_d, pes[1])
    errors += flat_errors
    if not (flat[0] < flat[1] < flat[2]):
        errors.append('flat-multiple ladder broken')
    em_over_r = eps_d[1] / r
    if abs(M / em_over_r - 1) > RECONCILE_TOL:
        errors.append('M differs by more than 20% from E_M/r reconciliation')
    a, b = inp['bridge_a'], inp['bridge_b']
    for year, (price, earnings) in BRIDGE_GATE.items():
        if abs((a + b * price) / earnings - 1) > BRIDGE_TOL:
            errors.append(f'bridge {year} differs by more than 20%')
    if errors:
        raise ValueError('; '.join(errors))

    def band(g1_=g1, n_=n_win, g2_=g2, r_=r, tau_=tau):
        return [e * (1 + r_) ** -tau_ * window_pe(g1_, n_, g2_, x, r_) + window(x, g1_, r_, tau_)
                for e, x in zip(eps28, roe)]

    as_band = lambda xs: dict(zip('LMH', xs))
    sensitivity = {name: as_band(band(**change)) for name, change in (
        ('growth_terminal_zero', {'g2_': 0}), ('growth_terminal_3pct', {'g2_': .03}),
        ('window_10_years', {'n_': 10}), ('window_growth_cap', {'g1_': .06}),
        ('basket_5', {'r_': basket_r(5)}), ('basket_4', {'r_': basket_r(4)}),
        ('no_time_alignment', {'tau_': 0}))}
    bridge = {name: {'price': price, 'earnings': earnings, 'modeled': a + b * price,
                     'relative_error': (a + b * price) / earnings - 1}
              for name, (price, earnings) in (BRIDGE_GATE | BRIDGE_EXTRA).items()}
    worlds = {tier: {'present_volume_price': (e - a) / b,
                     'phase2_volume_price': (e / PHASE2_VOLUME_X - a) / b}
              for tier, e in zip('LMH', eps28)}
    coordinates = {}
    for label, price in (('5y_mid', inp['ndpr_mid']), ('regime_mid', NDPR_REGIME_MID)):
        e = a + b * price
        ro = e / inp['bps_fwd']
        pe = window_pe(g1, n_win, g2, ro, r)
        coordinates[label] = {'price': price, 'eps': e, 'return_proxy': ro, 'multiple': pe,
                              'value': e * disc * pe + window(ro)}
    ths = inp['eps28_ths'] * disc * window_pe(g1, n_win, g2, inp['eps28_ths'] / inp['bps_fwd'], r) + window(inp['eps28_ths'] / inp['bps_fwd'])
    sensitivity['forecast_upgrade'] = ths
    sensitivity['forecast_upgrade_zone'] = zone_of(ths, L, M, H)
    # The document's older 8.94% coordinate was already recorded before the
    # 2023 band was judged distorted. It is a historical comparison, not a
    # newly inferred rate or a permitted route to reset the basket.
    sensitivity['historical_0894_rate'] = as_band(band(r_=.0894))
    sensitivity['observed_retention_window_m'] = eps_d[1] * pes[1] + win_eps * inp['payout_obs'] / (1 + r) ** (tau / 2)
    sensitivity['flat_multiple'] = as_band(flat)
    a_cut, b_cut = (L + M) / 2, (M + H) / 2
    changed = inp != INPUTS or band_distorted != BAND_DISTORTED
    return {'ticker': '600111.SH', 'currency': 'CNY',
            'valuation_as_of': None if changed else '2026-06-30',
            'framework_as_of': None if changed else '2026-10-16',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a_cut, 'B': b_cut},
            'candidate': None, 'option': None, 'segments': {'company': {'values': as_band((L, M, H))}},
            'key_parameters': {'method': dict.fromkeys('LMH', 'two_stage_gordon'),
                               'discount_rate': dict.fromkeys('LMH', r),
                               'growth_rate': dict.fromkeys('LMH', g2),
                               'window_growth': dict.fromkeys('LMH', g1), 'window_years': n_win,
                               'forward_return': as_band(roe), 'steady_return': as_band(roe), 'multiple': as_band(pes)},
            'operating': {'eps': as_band(eps28), 'window': as_band(win), 'window_eps': win_eps,
                          'band_outside': out_of_band, 'band_distorted': band_distorted,
                          'pb_floor': inp['pb_floor'] * inp['bps'], 'em_over_r': em_over_r,
                          'payout_gap': payout_gap(g2, roe[1], inp['payout_obs']),
                          'bridge': bridge, 'worlds': worlds, 'coordinates': coordinates,
                          'trough_coordinate': inp['eps_trough'] / r,
                          'precontrol_earnings_yield': (a + b * inp['ndpr_mid']) / PRE_CONTROL_PRICE},
            'sensitivity': sensitivity}


def calculate(context):
    # The recorded midcycle-earnings check failed before the original research
    # adopted the two-analyst forecast. Retain that historical decision and
    # disclose its uncertainty, instead of reclassifying it as a new approval.
    result = evaluate(dict(INPUTS), BAND_DISTORTED)
    result['valuation_as_of'] = result['framework_as_of'] = None
    result['historical_financial_statement_as_of'] = '2026-06-30'
    result['historical_research_as_of'] = '2026-10-16'
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['review_flags'] = ['historical_midcycle_forecast_fallback_requires_review',
                              'forward_book_retention_and_dividend_unverified',
                              'historical_fade_and_financing_contrasts_not_reconstructed']
    local = {'inputs': INPUTS, 'constants': {
        'min_r_minus_g': MIN_R_MINUS_G, 'reconcile_tol': RECONCILE_TOL,
        'bridge_gate': BRIDGE_GATE, 'bridge_extra': BRIDGE_EXTRA, 'bridge_tol': BRIDGE_TOL,
        'phase2_volume_x': PHASE2_VOLUME_X, 'pre_control_price': PRE_CONTROL_PRICE,
        'ndpr_regime_mid': NDPR_REGIME_MID, 'band_distorted': BAND_DISTORTED,
    }}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(local, BASELINE_LOCAL)
    return result
