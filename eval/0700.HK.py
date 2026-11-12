#!/usr/bin/env python3
"""Tencent's 2026 historical valuation; structured research output, not publication.

Input amounts are CNY or HKD as named; shares are whole shares, rates are
fractions, outputs are HKD/share. The original 2027 consensus model and 2028
single-house candidate are preserved without new research.
"""
from __future__ import annotations

from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'rf_report', 'partial_basis'), 'axes': {}}

# Shares: 9.103 billion (2026-09-03); HKD/CNY cross rate 1.1668 (2026-09-04).
# 2027 non-IFRS EPS low / mean / high: yfinance 33 analysts, CNY/share,
# retrieved 2026-10-21; 2026 mean is from the same source and date. H1 2026
# non-IFRS parent net income CNY 136.32bn and book HKD 145.63/share are from
# the 2026-06-30 interim; only the as-yet unbooked H2 income rolls into book.
# Three-year actual payout .17 is cash dividends divided by IFRS parent income
# for 2023–25 (yfinance annual cash flow); disclosure only, not book roll.
# Basket 4 for ordinary platform cash flow; g2 .0207 is 2026-09-11 peer reverse
# solution excluding Tencent. The candidate uses HSBC's single-house FY2026E
# 28.83 to FY2028E 32.87 CNY CAGR .0678 (2026-09-07), for one year.
# Five-year IFRS TTM PE guardrail 10.46–26.61 as of 2026-09-12; 29.79 HKD
# IFRS trailing EPS as of 2026-09-11 converts each price to the same basis.
# Segment revenue weights are for disclosure only (H1 2026). Long-term
# investments proxy 1.0596tn HKD at 2026-06-30; discounts 40/30/20%, middle
# from CMB International and others historical scenario assumptions (2026-09-04).
# JPM Q2 net cash CNY 58.2bn (2026-08-12), parent share 92.91% from H1 2026
# parent and minority equity; half-year timing aligns 2026-06-30 to 2027 start.
HISTORICAL_PARTIAL_FINGERPRINT = 'b3f0932d3670f5ea95560f8a8474b4accfaaa6a40354428f241a9ddc849b07df'

INPUTS = {
    'shares': 9.103e9, 'fx': 1.1668, 'eps27_l_cny': 25.818,
    'eps27_m_cny': 30.32538, 'eps27_h_cny': 34.19, 'bps_hkd': 145.63,
    'eps26_m_cny': 28.83765, 'ni_1h26_cny': 1.3632e11, 'payout_3y': .17,
    'r_perp': .10, 'g2': .0207, 'g1_fy28_hsbc': .0678, 'n_fy28_cand': 1.,
    'pe_own_min': 10.46, 'pe_own_max': 26.61, 'eps_ttm_ifrs': 29.79,
    'w_dom': .3946, 'w_intl': .092, 'w_ads': .2154, 'w_fbs': .2981,
    'nav_hkd': 1.0596e12, 'd_l': .4, 'd_m': .3, 'd_h': .2,
    'net_cash_cny': 5.82e10, 'tau': .5, 'parent_ratio': .9291,
}
LEGS = ('dom', 'intl', 'ads', 'fbs')
TIERS = ('l', 'm', 'h')
REQUIRED = tuple(INPUTS)

def eps_hkd(inp: dict[str, float], tag: str) -> float:
    """FY2027E consensus point in HKD (source is CNY, A1 / A8)."""
    return inp[f"eps27_{tag}_cny"] * inp["fx"]


def scenario(inp: dict[str, float], tag: str, pe_override: float | None = None,
             candidate: bool = False) -> dict[str, float]:
    """One tier -> Gordon multiple, per-leg HKD/share contributions and the anchor.

    `candidate` swaps the perpetual multiple for the A1c two-stage one (HSBC's
    single-house FY2028E year); nothing else in the chain moves.
    """
    eps = eps_hkd(inp, tag)
    # ROE = E_{n+1} / B_n: FY27 EPS over the OPENING-2027 book (= end-2026), not
    # the H1'26 book and not the end-2027 book (that would put retention the
    # year has not yet earned into the denominator; valuation-rules 裁决表 ②
    # as of 2026-09-21; A6b).  The H1'26 book is rolled over the 2H26
    # earnings not yet booked at the GROWTH-REQUIRED retention b1 = g/ROE --
    # g2 in the deck (no g1 window), the HSBC g1 in the candidate band (the
    # growth its stage 1 charges next) -- never at the actual payout
    # complement.  ROE and BPS depend on each other; closed form
    # BPS = BPS0 / (1 - g N / EPS).  FY2027's own retention is NOT rolled.
    g_roll = inp["g1_fy28_hsbc"] if candidate else inp["g2"]
    unbooked = (inp["eps26_m_cny"] - inp["ni_1h26_cny"] / inp["shares"]) * inp["fx"]  # HKD/share, 2H26 only
    bps_open = inp["bps_hkd"] / (1.0 - g_roll * unbooked / eps)
    roe = eps / bps_open
    b1 = g_roll / roe
    excess_cash = ((1.0 - inp["payout_3y"]) - b1) * unbooked  # B bucket: disclosure only, not in BPS
    if pe_override is not None:
        pe = pe_override
    elif candidate:
        pe = two_stage_pe(inp["g1_fy28_hsbc"], int(inp["n_fy28_cand"]), inp["g2"], roe, inp["r_perp"])
    else:
        pe = perpetual_pe(inp["g2"], roe, inp["r_perp"])
    # Timing (valuation-rules「经营价值与超额现金」③ 时点对齐, A15): eps x pe is the value at the
    # numerator year's opening (2027-01-01); discount tau years to the balance-sheet date and add
    # the window's distributable profit (2H26 unbooked x (1 - b1), the roll's own b1) at tau/2.
    # Non-IFRS numerator does not deduct SBC, so neither does the window.  NAV and net cash are
    # balance-sheet-date items and are not moved; net cash counts the parent share only.
    r, tau = inp["r_perp"], inp["tau"]
    gordon = eps * pe
    window = unbooked * (1.0 - b1)
    ops = gordon / (1 + r) ** tau + window / (1 + r) ** (tau / 2)
    legs = {leg: ops * inp[f"w_{leg}"] for leg in LEGS}
    nav = inp["nav_hkd"] * (1.0 - inp[f"d_{tag}"]) / inp["shares"]
    cash = inp["net_cash_cny"] * inp["fx"] / inp["shares"] * inp["parent_ratio"]
    out = dict(legs)
    out.update(eps=eps, roe=roe, pe=pe, gordon=gordon, window=window, ops=ops, nav=nav, cash=cash,
               anchor=ops + nav + cash,
               g_roll=g_roll, unbooked=unbooked, bps_open=bps_open, b1=b1, excess_cash=excess_cash)
    return out


def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('n_fy28_cand',))
    errors += check_r(inp['r_perp'], 'r_perp', 4)
    errors += check_g_cap(inp['g2'], inp['r_perp'], 'g2')
    if inp['r_perp'] - inp['g2'] < .02:
        errors.append('discount rate minus growth below 2 percentage points')
    errors += ladder('eps27', inp['eps27_l_cny'], inp['eps27_m_cny'], inp['eps27_h_cny'])
    if abs(sum(inp[f'w_{leg}'] for leg in LEGS) - 1) > .001:
        errors.append('segment weights do not sum to one')
    if not inp['d_l'] > inp['d_m'] > inp['d_h']:
        errors.append('NAV discounts must decrease from low to high')
    if any(k == 'p' or k.startswith('p_') for k in inp):
        errors.append('probability-like input is not permitted')
    if errors:
        raise ValueError('; '.join(errors))
    scenarios = {t: scenario(inp, t) for t in TIERS}
    if any(not 0 < scenarios[t]['b1'] < 1 for t in TIERS):
        errors.append('required retention is outside (0,1)')
    if not 0 < inp['ni_1h26_cny'] / inp['shares'] < inp['eps26_m_cny']:
        errors.append('booked H1 earnings must be within full-year earnings')
    values = [scenarios[t]['anchor'] for t in TIERS]
    errors += ladder('anchors', *values)
    historical_band_outside = any(
        not inp['pe_own_min'] - 1e-9 <= scenarios[t]['anchor'] / inp['eps_ttm_ifrs'] <= inp['pe_own_max'] + 1e-9
        for t in TIERS)
    flat = [scenario(inp, t, pe_override=scenarios['m']['pe'])['anchor'] for t in TIERS]
    errors += ladder('flat multiple', *flat)
    candidate = {t: scenario(inp, t, candidate=True) for t in TIERS}
    errors += ladder('candidate', *(candidate[t]['anchor'] for t in TIERS))
    if errors:
        raise ValueError('; '.join(errors))
    def band_rf(dr):
        shifted = dict(inp, r_perp=inp['r_perp'] + dr)
        return tuple(scenario(shifted, t)['anchor'] for t in TIERS)
    band = lambda vals: dict(zip('LMH', vals))
    alt_band = lambda **changes: band(scenario(dict(inp, **changes), t)['anchor'] for t in TIERS)
    result = {
        'ticker': '0700.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-22', 'historical_framework_as_of': '2026-10-22',
        'anchors': band(values),
        'candidate': {'label': '汇丰2028预测', 'anchors': band(candidate[t]['anchor'] for t in TIERS)},
        'option': None,
        'scenarios': {t.upper(): scenarios[t] for t in TIERS},
        'candidate_scenarios': {t.upper(): candidate[t] for t in TIERS},
        'flat_multiple': band(flat),
        'sensitivity': {'g_minus_1pp': alt_band(g2=inp['g2']-.01),
                        'g_plus_1pp': alt_band(g2=inp['g2']+.01),
                        'g_peer_median': alt_band(g2=-.0098), 'g_sellside': alt_band(g2=.03),
                        'nav_discount_minus_5pp': alt_band(d_m=inp['d_m']-.05),
                        'nav_discount_plus_5pp': alt_band(d_m=inp['d_m']+.05)},
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if inp['r_perp'] + dr <= inp['g2']:
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp': inp['r_perp']}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=values)
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    result['historical_band_outside'] = historical_band_outside
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'legs': LEGS, 'tiers': TIERS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'HKD_PER_SHARE'}
    scenarios = result['scenarios']
    result['segments'] = {name: {'unit': 'HKD_PER_SHARE',
                                'values': {t: scenarios[t][key] for t in 'LMH'}}
                          for name, key in (('operating_business', 'ops'), ('investments', 'nav'), ('net_cash', 'cash'))}
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['r_perp'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['g2'])},
        'forward_return': {'unit': 'RATIO', 'values': {t: scenarios[t]['roe'] for t in 'LMH'}},
        'steady_return': {'unit': 'RATIO', 'values': {t: scenarios[t]['roe'] for t in 'LMH'}},
    }
    result['review_flags'] = ['historical_ai_investment_cash_needs_unverified',
                              'historical_segment_weight_period_unverified',
                              'historical_investment_portfolio_book_value_proxy']
    if result['historical_band_outside']:
        result['review_flags'].append('historical_pe_outside_range')
    return result
