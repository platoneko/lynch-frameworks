"""159307 historical ETF draft using explicit offline history snapshots.

The 2026-09-11 close is a proxy, not an actual NAV, and is paired with a
2026-09-17 index reference. That historical mismatch remains disclosed rather
than erased. Inputs and source identifiers must be supplied by the caller.
"""
from __future__ import annotations
import math
import pandas as pd
from lib.etf import REGIME_GAP, SUBWINDOWS, channel, rate_neutral, slope_since
from lib.etf_lookthrough import scale
from lib.gordon import NEAR_FULL_PAYOUT, check_g_cap, check_r, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.fund_history import normalize_fund_reference, normalize_histories
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('etf', 'etf_lookthrough', 'gordon', 'inputs', 'fund_history', 'partial_basis'),
                'axes': {'rates': 'rates'}, 'axis_options': {'rates': {'currencies': ['CNY']}}}
INPUTS = {
    'pe_now': 8.99,  # 指数滚动 PE（中证日频；带日期的历史读数，护栏与对照尺用）；2026-09-11
    'r_perp': 0.1,  # 篮 4 龙头制造 r = 10%：整篮 look-through 归篮加权 ≈10.3–10.8% 落篮 4（A11）；**只披露、不入主尺**（通道无 r），作公司尺对照（\(1/r\) 10× 截带顶）；值 = `gordon.BASKET_R[4]`，`check_r` 按篮子强制；2026-09-20
    'roe_idx': 0.088,  # 指数 ROE = PB 0.78 / PE 8.85；\；ROE−r\；1.2pp，披露用；2026-08-31
    'dps_ttm': 0.0486,  # 近四次派息之和；2025-12~2026-09
    'dps_ttm_prev': 0.0496,  # 前一 TTM：2024-12 0.0120 + 2025-03 0.0120 + 06 0.0126 + 09 0.0130；A10；2024-12~2025-09
    'payout_evid_max': 0.449,  # 最高一季 TTM 派息口径 ÷ 透视盈利；2026-06-30
    'g2_l': 0.0,  # **具名零增长**；三档同；公司尺对照用，通道无 g₂（斜率 +8.2% 是实测中枢回报，不是永续 g）；cap = min(6%, r − 4%) = 6% ≥ 0 ✓；A8 / A11
    'g2_m': 0.0,  # ；
    'g2_h': 0.0,  # ；
    'pe_own_min': 5.27,  # 自身 5 年日频 PE 带下沿；护栏；2026-09-11
    'pe_own_max': 9.71,  # 带顶（2025-11-20）；活倍数截于此；2026-09-11
    'pe_v4': 8.63,  # v4 留存分支 M 档倍数；**对照，不入公式**；—
    'pe_same_min': 7.96,  # 同等盈利月份实测 PE 下沿（TTM EPS ±12%，241 个交易日 / 13 个月 2025-09～2026-09）；对账 ④ 与护栏；2026-09-11
    'pe_same_med': 8.89,  # 同上中位；2026-09-11
    'pe_same_max': 9.71,  # 同上上沿 = 自身带顶；2026-09-11
    'idx_dy': 0.046,  # 指数股息率（三年均值口径）；只进证据区间下沿；2026-08-31
    'fee_drag': 0.98,  # \(1-0.002/0.10\)；合同
    'idx_eps_2023': 1720.8,  # 隐含 EPS = 点位 ÷ 滚动 PE，2023-09-11；2023-09-11
    'idx_eps_2025': 1432.0,  # 同上，2025-09-11；A9 最近一年方向；2025-09-11
    'idx_eps_now': 1253.0,  # 同上，2026-09-11；2026-09-11
    'g_cov_fwd': 0.0731,  # 覆盖名字 FY26E→FY27E 加权；2026-09-15
    'cov_w': 0.199,  # 覆盖合计指数权重；2026-08-31
    'pe_band_2018_23_lo': 5.8,  # E 侧护栏：指数 PE 2018–23 带下沿（2026-09-18 证据链，A11）；2018–23
    'pe_band_2018_23_hi': 8.3,  # E 侧护栏：2018–23 带上沿；2026-09-11 PE 8.99 在其上 = 偏贵；2018–23
    'eps_pt_from_peak': -0.27,  # E 侧护栏：透视 EPS/点 自 2023 顶累计变动；2026-09
    'dps_pt_2025_yoy': -0.11,  # E 侧护栏：指数每点分红 2025 同比；2025
}

# Legacy document explicitly identifies this as a traded close, but does not
# name an independently retrievable provider. Do not relabel this observation
# as NAV merely by changing its type or date; verified new evidence must be a
# separate observation and still requires human source reconciliation.
FUND_REFERENCE = {'security': '159307.SZ', 'kind': 'exchange_close_proxy',
                  'value': 1.013, 'date': '2026-09-11', 'unit': 'CNY_PER_UNIT',
                  'source_ref': 'legacy_close_proxy'}
INDEX_REFERENCE = {'instrument': 'H20955', 'value': 22380.52, 'date': '2026-09-17',
                   'unit': 'INDEX_POINTS'}
RATE_INSTRUMENT = 'CNY_10Y'
# Filled from the pre-existing historical series, dated reference objects,
# current ticker inputs and the chosen rate-axis source version. This detects
# only those recorded local facts; full valuation basis remains unknown.
HISTORICAL_PARTIAL_FINGERPRINT = 'f606f905c5722c7d0a765aabbbc231a306c5db4685431dd3f9c33a4b9b19f5ba'
DIVIDEND_YIELD_PRIOR = .048
DPS_CUT_TRIGGER = -.05
PAYOUT_TRIGGER = .50
HISTORICAL_FRAMEWORK_AS_OF = '2026-09-27'
FUND_REFERENCE_STATUS = 'requires_reconciliation'

def _historical_calculation(inp, index, rates):
    required = [*INPUTS, 'nav_ref', 'idx_cur', 'rf_ccy_mid']
    errors = check_missing(inp, required)
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in required):
        raise ValueError('all numeric inputs must be finite')
    r, roe, nav, fee = inp['r_perp'], inp['roe_idx'], inp['nav_ref'], inp['fee_drag']
    errors += check_r(r, 'r_perp', 4)
    for t in 'lmh':
        errors += check_g_cap(inp[f'g2_{t}'], r, f'g2_{t}')
        if abs(inp[f'g2_{t}']) > .0005:
            errors.append('named-zero company comparison requires zero growth')
    if nav <= 0 or roe <= 0 or inp['pe_now'] <= 0 or inp['dps_ttm_prev'] <= 0:
        errors.append('NAV reference, return, earnings multiple and previous dividend must be positive')
    if errors:
        raise ValueError('; '.join(errors))

    if len(index) < 2 or any(len(index[index.index >= start]) < 2 for start in SUBWINDOWS):
        raise ValueError('index history does not cover the required subwindows')
    ch = channel(index)
    sub = {w[:4]: slope_since(index, w) for w in SUBWINDOWS}
    if any(abs(value-ch['slope']) >= REGIME_GAP for value in sub.values()):
        errors.append('a subwindow indicates a possible regime change; reassess the fit')
    if abs(ch['cur']-inp['idx_cur']) > .002*inp['idx_cur']:
        errors.append('index history does not match the documented historical reference')
    k = nav/ch['cur']
    main = tuple(ch[t]*k for t in 'LMH')
    errors += ladder('channel', *main)
    rn = rate_neutral(index, rates, inp['rf_ccy_mid'], DIVIDEND_YIELD_PRIOR)

    eps = nav/inp['pe_now']
    payout = inp['dps_ttm']/eps
    if payout >= NEAR_FULL_PAYOUT:
        errors.append('dividend payout suggests no retained earnings; reassess')
    if payout > PAYOUT_TRIGGER:
        errors.append('dividend payout exceeds 50%; reassess')
    if not inp['idx_dy']*inp['pe_now'] <= payout <= inp['payout_evid_max']:
        errors.append('dividend payout outside observed evidence range')
    if inp['dps_ttm']/inp['dps_ttm_prev']-1 < DPS_CUT_TRIGGER:
        errors.append('dividend reduction exceeds 5%; reassess the low tier')
    if not .97 <= fee <= .99:
        errors.append('fee adjustment outside the prior model range')
    if min(inp['idx_eps_2023'], inp['idx_eps_2025'], inp['idx_eps_now']) <= 0:
        errors.append('index earnings observations must be positive')
    if errors:
        raise ValueError('; '.join(errors))

    factor3 = (inp['idx_eps_now']/inp['idx_eps_2023'])**(1/3)
    factor1 = inp['idx_eps_now']/inp['idx_eps_2025']
    if factor3 >= 1 or factor1 >= 1:
        errors.append('observed index earnings no longer decline; reassess named-zero premise')
    if inp['g_cov_fwd'] <= 0:
        errors.append('covered earnings forecast is not positive; reassess the high tier')
    factors = (round(factor3,2), 1.0, round(1+inp['g_cov_fwd']*inp['cov_w'],4))
    errors += ladder('company earnings factors', *factors)
    pe_zero = perpetual_pe(0, roe, r)
    pe_edge = min(pe_zero, inp['pe_own_max'])
    if not inp['pe_own_min']-.05 <= pe_edge <= inp['pe_own_max']+.05:
        errors.append('company comparison multiple is outside the historical band')
    if not inp['pe_same_min']-.05 <= pe_edge <= inp['pe_same_max']+.05:
        errors.append('company comparison multiple is outside the same-earnings range')
    if abs(inp['pe_v4']-pe_edge) < 1e-9:
        errors.append('historical retention comparison leaked into the selected comparison')
    company = tuple(scale(eps, fee, factor*pe_edge) for factor in factors)
    errors += ladder('company comparison', *company)
    if errors:
        raise ValueError('; '.join(errors))

    c19 = channel(index[index.index >= SUBWINDOWS[0]])
    tiers = lambda values: dict(zip('LMH', values))
    return {'ticker':'159307.SZ', 'currency':'CNY', 'valuation_as_of':None, 'framework_as_of':None,
            'anchors':tiers(main), 'candidate':None, 'option':None,
            'segments':{'fund':{'values':tiers(main)}},
            'key_parameters':{'method':'total_return_trend_channel'},
            'operating':{'index_start':ch['start'], 'index_end':ch['end'], 'index_close':ch['cur'],
                         'index_channel':tiers(ch[t] for t in 'LMH'), 'annual_slope':ch['slope'],
                         'subwindow_slopes':sub, 'residual_sigma':ch['sigma'], 'nav_index_factor':k,
                         'company_eps':eps, 'company_payout':payout, 'company_multiple':pe_edge,
                         'company_earnings_factors':tiers(factors)},
            'sensitivity':{'rate_neutral':tiers(rn[t]*k for t in 'LMH'),
                           'rate_neutral_slope':rn['slope'], 'rate_beta':rn['beta'],
                           'rate_beta_diff':rn['beta_diff'], 'rate_beta_prior':rn['beta_prior'],
                           'rate_start':rn['rf_start'], 'rate_last':rn['rf_now'],
                           'company_comparison':tiers(company),
                           'channel_from_2019':tiers(c19[t]*k for t in 'LMH')}}



def calculate(context):
    snapshot = context.get('external_inputs')
    cny = context['axes']['rates']['segments']['CNY']
    # CNY's long-run baseline exists even though current/consensus rate
    # sensitivity scenarios are not built. Use the shared numeric value.
    cny_baseline = cny.get('baseline')
    if isinstance(cny_baseline, bool) or not isinstance(cny_baseline, (int, float)) or not math.isfinite(cny_baseline):
        raise ValueError('shared CNY long-run rate baseline is unavailable')
    index_data, rates_data = normalize_histories(snapshot, INDEX_REFERENCE['instrument'], RATE_INSTRUMENT)
    if max(index_data) != INDEX_REFERENCE['date']:
        raise ValueError('provided index history end differs from the dated index reference')
    flags = normalize_fund_reference(FUND_REFERENCE, '159307.SZ', INDEX_REFERENCE['date'])
    actual_index_close = index_data[INDEX_REFERENCE['date']]
    if actual_index_close != INDEX_REFERENCE['value']:
        # The old model permits a 0.2% source tolerance; expose both the
        # reference and the actual point rather than pretending equality.
        flags.append('index_reference_and_actual_observation_differ')
    # External rate history is provided in percent, as in the old JSON cache;
    # use the same /100 conversion. Neither fetch functions nor caches are used.
    index = pd.Series(index_data, dtype=float)
    index.index = pd.to_datetime(index.index, errors='raise')
    rates = pd.Series(rates_data, dtype=float) / 100
    rates.index = pd.to_datetime(rates.index, errors='raise')
    inp = {**INPUTS, 'nav_ref': FUND_REFERENCE['value'], 'idx_cur': INDEX_REFERENCE['value'],
           'rf_ccy_mid': cny_baseline}
    result = _historical_calculation(inp, index, rates)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'fund_reference': FUND_REFERENCE, 'index_reference': INDEX_REFERENCE,
         'cny_baseline': cny_baseline, 'rates_axis_version': context['axis_versions']['rates'],
         'external_inputs': snapshot, 'rate_instrument': RATE_INSTRUMENT,
         'dividend_yield_prior': DIVIDEND_YIELD_PRIOR, 'dps_cut_trigger': DPS_CUT_TRIGGER,
         'payout_trigger': PAYOUT_TRIGGER, 'historical_framework_as_of': HISTORICAL_FRAMEWORK_AS_OF,
         'fund_reference_status': FUND_REFERENCE_STATUS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['historical_valuation_as_of'] = None  # Mixed dates; neither is the full valuation date.
    result['historical_framework_as_of'] = HISTORICAL_FRAMEWORK_AS_OF
    result['units'] = {'price': 'CNY_PER_UNIT'}
    result['segments']['fund']['unit'] = 'CNY_PER_UNIT'
    result['review_flags'] = flags
    # Source identifiers are assertions, not proof. Never let a relabeled or
    # newly supplied observation claim it has been independently verified.
    result['fund_reference_status'] = FUND_REFERENCE_STATUS
    result['fund_reference'] = dict(FUND_REFERENCE)
    result['index_reference'] = dict(INDEX_REFERENCE)
    result['index_actual'] = {'instrument': INDEX_REFERENCE['instrument'], 'date': INDEX_REFERENCE['date'],
                              'value': actual_index_close, 'unit': 'INDEX_POINTS',
                              'source_ref': snapshot['index_history']['source_ref']}
    result['history_sources'] = {
        'index': snapshot['index_history']['source_ref'],
        'rates': snapshot['rates_history']['source_ref'],
    }
    return result
