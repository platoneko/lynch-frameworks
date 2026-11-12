#!/usr/bin/env python3
"""1378.HK historical aluminium spread valuation; not a publication.

Amounts are CNY hundred million, volume ten thousand tonnes, spreads CNY/tonne,
shares hundred million, and values HKD/share. Rates are fractions. Inputs and
method reproduce the 2026-10-16 framework; they are not fresh research.
formula_id: hongqiao_al_spread_gm_bridge_gordon_v5
"""
from __future__ import annotations

import math

from lib.al_bridge import (REQUIRED, anchors, bridge, check_gordon,
                           check_regression, flat_ladder, multiples, pb_floor)
from lib.inputs import check_missing, ladder
from lib.metal_axis_checks import axis_basis_snapshot, check_aluminium_price_upside
from lib.partial_basis import local_basis_changed
from lib.rf_report import axis_loader, calculate_rf_readings

DEPENDENCIES = {'libraries': ('al_bridge', 'axes', 'gordon', 'inputs', 'metal_axis_checks', 'partial_basis', 'rf_report'),
                'axes': {'aluminium': 'fed_path_aluminium', 'gold_copper': 'fed_path_gold_copper', 'rates': 'rates'},
                'peers': {'tianshan': '002532.SZ'}}

# 2026-06-30 interim report, note 16: 9,819,397,841 shares; rounded to
# 98.194 hundred million. BPS HKD 15.82 uses the interim parent equity and
# 1.1668 CNY-to-HKD; 0.43 is the 2024-01-22 five-year PB low (LB, 2026-09-07).
# 2026-09-04 market cross rate, HKD to CNY 0.8570 (1 / 1.1668).
# The 2026H1 interim: revenue 875.1, parent net income 172.1, equity 1331.08;
# annualised revenue and net income below are each twice the half-year amount.
# Gross margin 31.5% (BOCI, 2026-08-24); annualised sales 562.2 from 281.1
# ten thousand tonnes (CICC, 2026-08-26). The 2025H1 comparison is annualised
# revenue 1620.6, margin 25.7%, parent net profit 247.2, and fits conversion
# from gross profit to net profit; it is not the low-tier scenario.
# Shared aluminium axis: spreads 4873 / 8879 / 9907 CNY/t, from Morgan Stanley
# 2027 scenario (2026-09-21), 2026H1, and 2026-07-10 respectively; perpetuity
# growth 0% in all tiers (2026-09-20). The 13% rate is basket 6 for a cyclical
# commodity business. LB five-year monthly TTM PE range 3.59–20.16 as of
# 2026-09-11 is a guardrail only, not an input to the value calculation.
INPUTS = {
    'shares': 98.194, 'fx_hkd_cny': .8570,
    'rev_m': 1750.2, 'gm_m': .315, 'rev_ref': 1620.6, 'gm_ref': .257,
    'np_m': 344.2, 'np_ref': 247.2, 'vol_al': 562.2,
    'equity': 1331.08, 'r_perp': .13,
    'pe_own_min': 3.59, 'pe_own_max': 20.16, 'bps': 15.82, 'pb_low': .43,
}
TIERS = 'LMH'
GROSS_PROFIT_FILING = 551.3
NET_PROFIT_FILING = 344.2
SHARES_STATIC = 98.194
# Existing 002532 same-input audit: parent profit L/M in CNY 100m; used only
# to report whether a supplied peer ratio differs from that historical basis.
HISTORICAL_TIANSHAN_LOW = 52.75921694987036
HISTORICAL_TIANSHAN_MID = 83.5
BASELINE_LOCAL = 'a53a8545f61a3d04e5ded17c9cf423c64e0f00310341ddf1f39c5c6173bb4eed'


def calculate(context):
    aluminium = context['axes']['aluminium']
    copper = context['axes']['gold_copper']
    rates = context['axes']['rates']
    peer = context['peers'].get('tianshan')
    inp = dict(INPUTS)
    for name in ('spread_l', 'spread_m', 'spread_h', 'g2_l', 'g2_m', 'g2_h'):
        inp[name] = aluminium[name]
    errors = check_missing(inp, REQUIRED + ['fx_hkd_cny'])
    if errors:
        raise ValueError('; '.join(errors))
    errors += ladder('smelting spread', inp['spread_l'], inp['spread_m'], inp['spread_h'])
    cross_axis_valid = check_aluminium_price_upside(aluminium_axis=aluminium, gold_copper_axis=copper)
    errors += check_regression(inp, GROSS_PROFIT_FILING, NET_PROFIT_FILING)
    errors += check_gordon(inp, 6, shared_growth={tier: aluminium[f'g2_{tier.lower()}'] for tier in TIERS})
    if abs(inp['shares'] - SHARES_STATIC) > .05:
        errors.append('shares differ from the 2026 interim issued count')
    values, eps = anchors(inp, fx=inp['fx_hkd_cny'])
    pes, roes = multiples(inp)
    errors += flat_ladder(eps)
    peer_ratio = None
    review_flags = ['aluminium_low_macro_path_conflict', 'historical_high_spread_perpetual_vs_one_year_axis']
    if not cross_axis_valid:
        review_flags.append('aluminium_copper_price_upside_not_met')
    if peer is None:
        review_flags.append('tianshan_comparison_unavailable')
    else:
        # A version-bound draft is not evidence that the peer result was
        # independently confirmed; the consumer must retain this status.
        if peer.get('confirmation_status') == 'unconfirmed':
            review_flags.append('tianshan_comparison_unconfirmed')
        if peer.get('ticker') != '002532.SZ' or peer.get('currency') != 'CNY':
            raise ValueError('Tianshan comparison has the wrong ticker or currency')
        for alias in ('aluminium', 'gold_copper'):
            if peer['source_versions'].get(f'axis:{alias}') != context['axis_versions'][alias]:
                raise ValueError(f'Tianshan comparison uses another {alias} axis version')
        profits = peer['operating']['net_profit']
        if not all(isinstance(profits.get(t), (int, float)) and not isinstance(profits[t], bool)
                   and math.isfinite(profits[t]) and profits[t] > 0 for t in ('L', 'M')):
            raise ValueError('Tianshan low and middle profit must be finite and positive')
        peer_ratio = profits['L'] / profits['M']
        if not math.isclose(peer_ratio, peer['operating']['low_profit_ratio'], rel_tol=1e-12):
            raise ValueError('Tianshan profit ratio does not match its underlying profits')
        if eps[0] / eps[1] >= peer_ratio:
            review_flags.append('tianshan_low_profit_ratio_comparison_not_met')
    if values[2] / (eps[1] / inp['fx_hkd_cny']) > inp['pe_own_max']:
        errors.append('high-tier value exceeds the historical PE guardrail on middle EPS')
    floor, floor_errors = pb_floor(inp, values[0])
    errors += floor_errors
    errors += ladder('anchors', *values)
    if errors:
        raise ValueError('; '.join(errors))

    def band_rf(dr):
        return tuple(anchors(dict(inp, r_perp=inp['r_perp'] + dr), fx=inp['fx_hkd_cny'])[0])

    rf = calculate_rf_readings(rate_currency='HKD', price_currency='HKD', price_unit='per_share',
                               priced_r={'r_perp': inp['r_perp']}, band_at=band_rf,
                               rates_loader=axis_loader(rates), base_anchors=tuple(values))
    as_band = lambda series: dict(zip(TIERS, series))
    br = bridge(inp)
    def sensitivity(**changes):
        return as_band(anchors(dict(inp, **changes), fx=changes.get('fx_hkd_cny', inp['fx_hkd_cny']))[0])
    gp_delta = inp['rev_m'] * inp['gm_m'] - inp['rev_ref'] * inp['gm_ref']
    # HKD is linked to USD in this axis. Exclude unrelated unbuilt currency
    # segments so changes unrelated to this stock do not claim input drift.
    relevant_rates = {'segment': rates['segments']['HKD'], 'as_of': rates['as_of'], 'provenance': rates['provenance']}
    local = {'inputs': INPUTS, 'aluminium': axis_basis_snapshot(aluminium), 'gold_copper': axis_basis_snapshot(copper), 'rates_hkd': relevant_rates,
             'historical_checks': {'gross_profit_filing': GROSS_PROFIT_FILING,
                                   'net_profit_filing': NET_PROFIT_FILING, 'shares_static': SHARES_STATIC,
                                   'peer_low': HISTORICAL_TIANSHAN_LOW, 'peer_mid': HISTORICAL_TIANSHAN_MID}}
    peer_changed = (peer_ratio is not None and not math.isclose(
        peer_ratio, HISTORICAL_TIANSHAN_LOW / HISTORICAL_TIANSHAN_MID, rel_tol=1e-12))
    return {
        'ticker': '1378.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-16',
        'anchors': as_band(values), 'candidate': None, 'option': None,
        'units': {'price': 'HKD_PER_SHARE'},
        'segments': {'company': {'unit': 'HKD_PER_SHARE', 'values': as_band(values)}},
        'basis_changed': None, 'partial_basis_changed': local_basis_changed(local, BASELINE_LOCAL) or peer_changed,
        'review_flags': review_flags,
        'bridge': {'gross_profit_cny_100m': as_band(br['gp']),
                   'net_profit_cny_100m': as_band(br['np']), 'conversion_rate': br['k']},
        'key_parameters': {'discount_rate': {'unit': 'RATIO', 'values': as_band([inp['r_perp']]*3)},
                           'growth_rate': {'unit': 'RATIO', 'values': as_band([inp[f'g2_{t}'] for t in 'lmh'])},
                           'forward_return': {'unit': 'RATIO', 'values': as_band(roes)},
                           'steady_return': {'unit': 'RATIO', 'values': as_band([None]*3)}},
        'operating': {'eps_cny': as_band(eps), 'multiple': as_band(pes), 'pb_floor_hkd': floor,
                      'tianshan_low_profit_ratio': peer_ratio},
        'sensitivity': {
            'g_minus_1pp': sensitivity(g2_l=-.01, g2_m=-.01, g2_h=-.01),
            'g_plus_1pp': sensitivity(g2_l=.01, g2_m=.01, g2_h=.01),
            'spread_l_minus_1000': sensitivity(spread_l=inp['spread_l']-1000),
            'spread_l_plus_1000': sensitivity(spread_l=inp['spread_l']+1000),
            'spread_h_plus_1000': sensitivity(spread_h=inp['spread_h']+1000),
            'spread_l_4250': sensitivity(spread_l=4250),
            'g_mh_3_3pct': sensitivity(g2_m=.033, g2_h=.033),
            'g_l_3_3pct': sensitivity(g2_l=.033), 'g_l_5pct': sensitivity(g2_l=.05),
            'g_all_minus_3_5pct': sensitivity(g2_l=-.035, g2_m=-.035, g2_h=-.035),
            'r_10pct': sensitivity(r_perp=.10), 'r_15pct': sensitivity(r_perp=.15),
            'k_minus_0_1': sensitivity(np_ref=inp['np_m']-(br['k']-.1)*gp_delta),
            'k_plus_0_1': sensitivity(np_ref=inp['np_m']-(br['k']+.1)*gp_delta),
            'old_shares': sensitivity(shares=107.9), 'old_fx': sensitivity(fx_hkd_cny=1/1.1465),
        },
        # Historical 1378 calculation capitalizes H indefinitely. The shared
        # axis instead says H lasts one year; keep both facts and the old value.
        'rate': {'inputs': rf['segment'], 'low': rf['step_down'], 'high': rf['step_up'],
                 'consensus': rf['consensus'], 'pressure': rf['pressure']},
    }
