#!/usr/bin/env python3
"""Historical Coinbase mid-cycle operating value plus assets, not a publication.

Formula: coin_midcycle_gordon_plus_assets_v1. Amounts USD millions, shares millions,
EBITDA rungs USD 100 million, values USD/share, rates ratios.
"""
from __future__ import annotations

import math
from lib.gordon import check_branch, check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe
from lib.inputs import ladder
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES={'libraries':('gordon','inputs','partial_basis','rf_report'),'axes':{'crypto':'crypto_cycle'}}

# 10-Q 2026-06-30: ordinary shares, parent equity, investments, net cash;
# 2026Q2 interest 22.5M annualized. Net cash is disclosure only: interest earned
# is already inside EBITDA; adding principal again would double count.
# The 2028 EBITDA scenarios are Morgan Stanley 2026-09-10, Wisburg 105136,
# and must remain synchronized with _AXIS.crypto-cycle. They are regime values,
# not point-year estimates; the historical framework does not discount by year.
# EBITDA adjustments: L 188 D&A + 630 SBC + 200 other; M FY2025 actual
# calibration 188.4 + 839.4 + 315.7; H compensation rises with activity.
# FY2025 tax rate 261.7/1522.1 and observed repurchases 790.2/1260.3, 10-K.
# Asset discounts/uplifts and zero-growth L are historical scenarios 2026-09-23.
# Basket 4 at 10% was explicitly selected by the user; its written high-cash-
# visibility criterion does not positively hold for this volatile business.
# 4% perpetual growth follows the axis base case's 2025–28 revenue CAGR 4.09%.
# Seller targets: 35 analysts, Longbridge 2026-09-22, disclosure only.
INPUTS = {
    'shares': 263.8, 'equity': 13080.,
    'addback_l': 1018., 'addback_m': 1343., 'addback_h': 1500., 'interest': 90., 'tax': .172,
    'crypto_inv': 1468.4, 'strat_inv': 840.3, 'crypto_hair_l': .4, 'strat_hair_l': .25,
    'crypto_up_h': .6, 'strat_up_h': .4, 'r_op': .1, 'g2': .04, 'g2_l': 0.,
    'net_cash': 2121., 'payout_obs': .627, 'seller_tp_mean': 202.,
    'seller_tp_lo': 95., 'seller_tp_hi': 330.,
}
TIERS = ('l', 'm', 'h')
HISTORICAL_PARTIAL_FINGERPRINT = '0acefbefbb78f9a2fbc8ea0b6a43e61e8ba1be9de55a2bb6ea220f5b1edb8875'


def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    missing = (INPUTS.keys() | {f'ebitda_{t}' for t in TIERS}) - inp.keys()
    if missing:
        raise ValueError(f'missing inputs: {sorted(missing)}')
    if any(not math.isfinite(value) for value in inp.values()):
        raise ValueError('all inputs must be finite')
    if inp['shares'] <= 0 or inp['equity'] <= 0:
        raise ValueError('shares and equity must be positive')
    r, g2 = inp['r_op'], inp['g2']
    errors = check_r(r, 'r_op', 4) + check_g_cap(g2, r, 'g2')
    if errors:
        raise ValueError('; '.join(errors))
    ni = {t: (inp[f'ebitda_{t}'] * 100 - inp[f'addback_{t}'] - inp['interest']) * (1 - inp['tax']) for t in TIERS}
    eps = {t: ni[t] / inp['shares'] for t in TIERS}
    roe = {t: ni[t] / inp['equity'] for t in TIERS}

    def multiples(rate, growth=g2):
        low = 1 / rate if inp['g2_l'] == 0 else perpetual_pe(inp['g2_l'], roe['l'], rate)
        return low, perpetual_pe(growth, roe['m'], rate), perpetual_pe(growth, roe['h'], rate)

    pe = dict(zip(TIERS, multiples(r)))
    core = {t: eps[t] * pe[t] for t in TIERS}
    crypto, strategic, shares = inp['crypto_inv'], inp['strat_inv'], inp['shares']
    asset = dict(zip(TIERS, ((crypto * (1 - inp['crypto_hair_l']) + strategic * (1 - inp['strat_hair_l'])) / shares,
                             (crypto + strategic) / shares,
                             (crypto * (1 + inp['crypto_up_h']) + strategic * (1 + inp['strat_up_h'])) / shares)))
    anchors = tuple(core[t] + asset[t] for t in TIERS)
    errors += check_branch(g2, roe['m'], r, inp['payout_obs'], 'M')
    errors += ladder('eps', *(eps[t] for t in TIERS))
    errors += ladder('anchor', *anchors)
    errors += ladder('flat-multiple', *(eps[t] * pe['m'] + asset[t] for t in TIERS))
    if errors:
        raise ValueError('; '.join(errors))

    def band_rate(dr):
        mult = multiples(r + dr)
        return tuple(eps[t] * mult[i] + asset[t] for i, t in enumerate(TIERS))

    as_band = lambda values: dict(zip(('L', 'M', 'H'), values))
    point_g = (eps['m'] / eps['l']) ** .5 - 1
    point_l = eps['l'] * recovery_two_stage_pe(point_g, 2, g2, roe['m'], r) + asset['l']
    growth_low = tuple(eps[t] * p + asset[t] for t, p in zip(TIERS, multiples(r, g2 - .01)))
    growth_high = tuple(eps[t] * p + asset[t] for t, p in zip(TIERS, multiples(r, g2 + .01)))
    def mid_adjusted(factor):
        value = (inp['ebitda_m'] * 100 - inp['addback_m'] * factor - inp['interest']) * (1 - inp['tax'])
        return value / shares * pe['m'] + asset['m']
    result = {
        'ticker': 'COIN.US', 'currency': 'USD', 'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of':'2026-10-16',
        'basis_changed': None,
        'anchors': as_band(anchors), 'candidate': None, 'option': None,
        'segments': {'operating': {'values': as_band(core[t] for t in TIERS)},
                     'assets': {'values': as_band(asset[t] for t in TIERS)}},
        'key_parameters': {'discount_rate': as_band((r,) * 3),
                           'perpetual_growth': as_band((inp['g2_l'], g2, g2)),
                           'forward_return': as_band(roe[t] for t in TIERS),
                           'steady_return_used': as_band((None, roe['m'], roe['h'])),
                           'steady_return_reference_h': .30,
                           'net_income': as_band(ni[t] for t in TIERS),
                           'eps': as_band(eps[t] for t in TIERS),
                           'multiples': as_band(pe[t] for t in TIERS)},
        'sensitivity': {'point_l': point_l, 'point_growth': point_g,
                        'growth_low': as_band(growth_low), 'growth_high': as_band(growth_high),
                        'addback_mid_low': mid_adjusted(.9), 'addback_mid_high': mid_adjusted(1.1)},
    }
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',priced_r={'r_op':r},
            band_at=band_rate,rates_loader=lambda _currency:rate_inputs,base_anchors=anchors))
    return result


def calculate(context):
    rungs=context['axes']['crypto']['rungs']
    selected={f'ebitda_{t}':rungs[t.upper()] for t in TIERS}
    result=evaluate({**INPUTS,**selected},context.get('rate_inputs'))
    result['partial_basis_changed']=local_basis_changed(
        {'inputs':INPUTS,'ebitda':selected},HISTORICAL_PARTIAL_FINGERPRINT)
    result['units']={'price':'USD_PER_SHARE'}
    for segment in result['segments'].values():
        segment['unit']='USD_PER_SHARE'
    params = result['key_parameters']
    for name in ('discount_rate', 'perpetual_growth', 'forward_return'):
        params[name] = {'unit': 'RATIO', 'values': params[name]}
    params['steady_return'] = {'unit': 'RATIO', 'values': params['steady_return_used']}
    result['review_flags']=['historical_single_house_crypto_scenarios',
                            'historical_cash_visibility_basket_override',
                            'historical_ebitda_to_earnings_bridge_unverified']
    return result
