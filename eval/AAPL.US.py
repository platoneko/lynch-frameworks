#!/usr/bin/env python3
"""Apple's historical FY2027 consensus valuation; output is not publication.

USD/share unless noted, percentages as ratios. Formula: aapl_fy27_consensus_two_stage_roic_v1.
The 2026-10-16 framework retains the old cash, reinvestment and ROIC judgments.
"""
from __future__ import annotations

import math
from lib.gordon import check_branch, check_g_cap, check_r, check_transition_years, two_stage_pe
from lib.inputs import ladder
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.tiers import flat_multiple_ladder
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'rf_report', 'tiers', 'partial_basis'), 'axes': {}}

# 10-Q FY2026 Q3 (2026-06-27): diluted shares in millions, book value/share,
# cash net of debt in USD billions. Q3 book and cash are rolled through Q4.
# FY2027E diluted EPS low/mean/high: yfinance 40 analysts, 2026-09-29.
# FY2028E: BofA 10.91 (Wisburg 105000), Citi 11.06 (365/33, Wisburg 104939),
# both 2026-09-10. FY2026E 8.82 is yfinance 2026-09-29; nine-month 6.88 is 10-Q.
# One transition year is supported by the two FY2028 estimates.
HISTORICAL_PARTIAL_FINGERPRINT = 'c3f01cff91900818ec3d48b37d1792d11479a629fc17d6cd347a4f347539f738'

INPUTS = {
    'shares_diluted': 14714.676, 'eps_fy27e_low': 8.69,
    'eps_fy27e_consensus': 9.58, 'eps_fy27e_high': 10.67,
    'eps_fy28e_bofa': 10.91, 'eps_fy28e_citi': 11.06,
    'n_stage': 1, 'consensus_years_beyond': 1, 'eps_fy26e': 8.82,
    'eps_9m_26': 6.88, 'bps_q3_26': 7.36, 'net_cash_q3_26': 62.17,
    # Basket 4, ordinary operation; the historical framework's selected 10%.
    'r_perp': .10,
    # Products' gross profit share 108819/178782, 10-Q 2026-06-27;
    # hardware cap 4%, services cap 6%, blended and rounded to 4.78%.
    'g2_hw': .04, 'g2_svc': .06, 'w_hw': .6087, 'g2': .0478, 'g2_cand': .06,
    # FY2025 cash dividend 1.02 / diluted EPS 7.46, SEC XBRL; buybacks are retained.
    # The 18% haircut to all deemed distributions lacked a specific transaction and was removed 2026-10-16.
    'payout_actual': .137, 'k_l': 0., 'k_m': 0., 'k_h': 0.,
    # June 27 to FY2027 opening: 0.25 year. Steady return is FY2022–25 own
    # median GAAP net income / opening equity less all net cash, 635%; it is
    # capped at each forward return and therefore does not affect this model.
    'tau': .25, 'ronic_ss': 6.35,
    # TTM EPS: 10-Q 2026-06-27; observed monthly PE 2020-01 to 2026-08,
    # Longbridge. Leverage readings FY2025 and interest FY2023: SEC XBRL.
    'eps_ttm': 8.72, 'pe_own_min': 18.4, 'pe_own_p50': 29.5, 'pe_own_top': 40.4,
    'net_debt_ebitda': -.23, 'interest_ebit': .034,
    # Google search payment 2022 court testimony, after tax per share, stress only.
    # No option is included: no disclosed full-year unit economics, 2026-09-30.
    'tac_eps': 1.14, 'v_opt': 0.,
}
TIERS = ('l', 'm', 'h')


def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    missing = INPUTS.keys() - inp.keys()
    if missing:
        raise ValueError(f'missing inputs: {sorted(missing)}')
    if any(not math.isfinite(value) for value in inp.values()):
        raise ValueError('all inputs must be finite')
    if inp['shares_diluted'] <= 0 or inp['eps_ttm'] <= 0:
        raise ValueError('shares and TTM EPS must be positive')
    if inp['n_stage'] != int(inp['n_stage']) or inp['consensus_years_beyond'] != int(inp['consensus_years_beyond']):
        raise ValueError('transition years must be integers')
    r, g2 = inp['r_perp'], inp['g2']
    errors = check_r(r, 'r_perp', 4)
    errors += check_g_cap(inp['g2_hw'], r, 'g2_hw', mega_hw=True)
    errors += check_g_cap(inp['g2_svc'], r, 'g2_svc')
    errors += check_g_cap(g2, r, 'g2')
    errors += check_g_cap(inp['g2_cand'], r, 'g2_cand')
    n = int(inp['n_stage'])
    errors += check_transition_years(n, int(inp['consensus_years_beyond']), 'n_stage')
    if abs(inp['w_hw'] * inp['g2_hw'] + (1 - inp['w_hw']) * inp['g2_svc'] - g2) > 5e-4:
        errors.append('g2 does not match gross-profit weighted blend')
    if inp['net_debt_ebitda'] > 3 or inp['interest_ebit'] > 1 / 3:
        errors.append('leverage gate triggered; ROIC decomposition required')
    if inp['v_opt'] != 0:
        errors.append('unmodeled option must remain zero')
    eps = dict(zip(TIERS, (inp['eps_fy27e_low'], inp['eps_fy27e_consensus'], inp['eps_fy27e_high'])))
    errors += ladder('EPS', *(eps[t] for t in TIERS))
    if errors:
        raise ValueError('; '.join(errors))

    g1 = ((inp['eps_fy28e_bofa'] + inp['eps_fy28e_citi']) / 2) / eps['m'] - 1
    cash = inp['net_cash_q3_26'] * 1000 / inp['shares_diluted']
    unbooked = inp['eps_fy26e'] - inp['eps_9m_26']
    ic0 = inp['bps_q3_26'] - cash
    if ic0 <= 0 or any(value <= 0 for value in eps.values()):
        raise ValueError('positive operating capital and forecast EPS required')

    def capital_base(e: float, base: float, cap: float | None = None):
        b = 0.0
        for _ in range(60):
            ic = base + b * unbooked
            ret = e / ic if cap is None else min(e / ic, cap)
            b = g1 / ret
        return ic, ret, b

    def price(t: str, growth: float, rate: float, ret: float, b: float):
        e = eps[t]
        pe = two_stage_pe(g1, n, growth, ret, rate)
        deemed = max(1 - inp['payout_actual'] - b, 0.0) * sum(e * (1 + g1) ** j for j in range(n))
        window = unbooked * max(1 - b, 0.0) / (1 + rate) ** (inp['tau'] / 2)
        return pe, deemed, e * pe / (1 + rate) ** inp['tau'] + window + cash - inp[f'k_{t}'] * deemed

    def tier(t: str, growth: float = g2, rate: float = r):
        ic, ret, b = capital_base(eps[t], ic0)
        pe, deemed, anchor = price(t, growth, rate, ret, b)
        return dict(ic=ic, roic=ret, b=b, pe=pe, deemed=deemed, anchor=anchor)

    rows = {t: tier(t) for t in TIERS}
    anchors = tuple(rows[t]['anchor'] for t in TIERS)
    candidate = tuple(tier(t, growth=inp['g2_cand'])['anchor'] for t in TIERS)
    errors += ladder('anchor', *anchors)
    errors += ladder('candidate', *candidate)
    errors += flat_multiple_ladder(tuple(eps[t] for t in TIERS), rows['m']['pe'])[0]
    errors += check_branch(g2, rows['m']['roic'], r, inp['payout_actual'], 'M')
    if any(rows[t]['roic'] > inp['ronic_ss'] for t in TIERS):
        errors.append('steady return path binds and is not implemented')
    if anchors[2] / inp['eps_ttm'] > inp['pe_own_top']:
        errors.append('H exceeds own historical PE ceiling')
    if errors:
        raise ValueError('; '.join(errors))

    def band_rate(dr):
        return tuple(tier(t, rate=r + dr)['anchor'] for t in TIERS)

    as_band = lambda values: dict(zip(('L', 'M', 'H'), values))
    book = {}
    for name, cap in (('book_roe', None), ('capped_roe', .60)):
        book[name] = as_band(price(t, g2, r, *capital_base(eps[t], inp['bps_q3_26'], cap)[1:])[2] for t in TIERS)
    tac = ((eps['m'] - inp['tac_eps']) * rows['m']['pe'] / (1 + r) ** inp['tau']
           + anchors[1] - eps['m'] * rows['m']['pe'] / (1 + r) ** inp['tau'])
    runway = {str(gh): {str(years): eps['m'] * two_stage_pe(gh, years, g2, rows['m']['roic'], r) + cash
                        for years in (0, 5, 10, 15, 20)} for gh in (.06, .08, .10, .12, .15)}
    result = {
        # Historic inputs alone do not establish current confirmation.
        'ticker': 'AAPL.US', 'currency': 'USD', 'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-27',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of': '2026-10-16', 'basis_changed': None,
        'anchors': as_band(anchors),
        'candidate': {'label': '整公司平台上限', 'anchors': as_band(candidate)}, 'option': None,
        'segments': {'company': {'values': as_band(anchors)}},
        'key_parameters': {
            'forward_eps': as_band(eps[t] for t in TIERS),
            'discount_rate': as_band((r,) * 3), 'transition_growth': as_band((g1,) * 3),
            'perpetual_growth': as_band((g2,) * 3),
            'forward_return': as_band(rows[t]['roic'] for t in TIERS),
            'steady_return_used': as_band(rows[t]['roic'] for t in TIERS),
            'steady_return_reference': inp['ronic_ss'], 'net_cash_per_share': cash,
            'multiples': as_band(rows[t]['pe'] for t in TIERS),
        },
        'sensitivity': {
            'growth_low': as_band(tier(t, growth=g2 - .01)['anchor'] for t in TIERS),
            'growth_high': as_band(tier(t, growth=g2 + .01)['anchor'] for t in TIERS),
            'tac_loss_mid': tac, 'runway': runway,
            'zero_growth_mid_plus_cash': eps['m'] / r + cash,
            'old_buyback_haircut_mid': anchors[1] - .18 * rows['m']['deemed'],
            **book,
        },
    }


    if rate_inputs is not None:
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': r}, band_at=band_rate,
            rates_loader=lambda _currency: rate_inputs, base_anchors=anchors)
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['partial_basis_changed'] = local_basis_changed({'inputs': INPUTS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments']['company']['unit'] = 'USD_PER_SHARE'
    result['review_flags'] = ['historical_operating_capital_return_estimate_unverified',
                              'historical_cash_and_growth_funding_unverified',
                              'historical_comparable_earnings_band_unverified']
    return result
