#!/usr/bin/env python3
"""Robinhood Q3 2026 historical whole-company valuation, USD/share."""
from lib.gordon import check_branch, check_g_cap, check_r, perpetual_pe
from lib.inputs import ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
import math

DEPENDENCIES={'libraries':('gordon','inputs','partial_basis','rf_report'),
              'axes':{'crypto':'crypto_cycle'}}
HISTORICAL_PARTIAL_FINGERPRINT='e12bd1735c2061534c2bb3a6c3544d061b7731ac74617eb0670f6f7dd4b44294'
NUM_YEAR=2027

# 2026Q3 10-Q, 2026-09-30:
# https://www.sec.gov/Archives/edgar/data/1783879/000178387926000167/hood-20260930.htm
# Corrected earnings release (GAAP unchanged):
# https://www.sec.gov/Archives/edgar/data/1783879/000178387926000170/q32026robinhoodamendedex991.htm
# Q3 data: 901m basic shares; parent equity 10,078m minus 77m non-controlling;
# Q3 consolidated profit 476m less 8m minority plus H1 parent 911m = YTD 1,379m.
# FY2027 EPS is 22-house yfinance consensus from 2026-09-22, before this report;
# FY2028 EPS is a single Morgan Stanley forecast (Wisburg 103637, 2026-09-01).
# Low-case options and equities use actual 2025Q2 annualized; crypto uses FY2023.
# Q3 event, other transaction, interest and Gold income are annualized. Proxy
# voting is FY25 minus 9M25 plus 9M26, because Q2 is seasonally high. Q3 other
# revenue excludes the 47m Trump Accounts service figure, an unverified media
# split (TradingKey/Longbridge 2026-10-28), without reducing corresponding costs.
# Annualized 9M costs subtract half marketing and add one more 9M credit
# provision. Q3 minority profit x4 is subtracted after tax as a fixed stress
# proxy, including the legal-event sensitivities; it is not an ownership rate.
# 2026-09-23 user decision retained the 10% discount rate despite no basket
# positively matching the company's economics. M steady return 21.5% is
# Schwab FY2016–25 tangible-equity average, user accepted 2026-10-19; high
# case uses 30% capped by its own forward return. No current data is implied.
INPUTS={
 'shares':901.,'total_equity':10078.,'minority_equity':77.,
 'eps_27_l':2.43316,'eps_27_m':2.79289,'eps_27_h':3.50,'eps_28_ms':3.28,
 'opt_q2_2025':265,'pred_q3_2026':173,'eq_q2_2025':66,'crypto_trough':135,
 'othtx_q3_2026':54,'nii_q3_2026':415,'nii_shock_100':366,
 'gold_q3_2026':62,'proxy_fy25':55,'proxy_9m25':52,'proxy_9m26':57,
 'other_q3_2026':73,'service_proxy_q3':47,'opex_9m_2026':2129,'marketing_9m':315,'credit_9m':163,
 'minority_profit_q3':8,'ni_h1_26':911,'ni_q3_consolidated':476,
 'buyback_fy25':653,'buyback_9m25':553,'buyback_9m26':689,'ni_q4_25':605,
 'tax':.24,'r_op':.10,'g2':.04,'g2_l':0.,
 'seller_tp_mean':130.67133,'seller_tp_lo':59.,'seller_tp_hi':170.,
 'tau':.25,'eps26_cons':2.088,'y1':2027,'y2':2031,
 'rs_steady':.215,'rs_steady_h':.30,
}

def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2; n stage-1 years at payout 1 - g1/roe.
    With rs >= roe this equals perpetual_pe / two_stage_pe.  (gordon.py helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def evaluate(inp, rate_inputs=None):
    require_whole_years(inp,('y1','y2'))
    if inp['y1'] < NUM_YEAR or inp['y2'] <= inp['y1']:
        raise ValueError('return path years invalid')
    equity=inp['total_equity']-inp['minority_equity']
    if inp['shares'] <= 0 or equity <= 0:
        raise ValueError('shares and equity must be positive')
    r,g,gl=inp['r_op'],inp['g2'],inp['g2_l']
    errors=check_r(r,'r_op',4)+check_g_cap(g,r,'g2')
    if errors:
        raise ValueError('; '.join(errors))
    shares,tax=inp['shares'],inp['tax']
    revenue=(inp['opt_q2_2025']*4+inp['pred_q3_2026']*4+inp['eq_q2_2025']*4
             +inp['crypto_trough']+inp['othtx_q3_2026']*4+inp['nii_q3_2026']*4
             -inp['nii_shock_100']+inp['gold_q3_2026']*4
             +inp['proxy_fy25']-inp['proxy_9m25']+inp['proxy_9m26']
             +(inp['other_q3_2026']-inp['service_proxy_q3'])*4)
    opex=(inp['opex_9m_2026']-inp['marketing_9m']*.5+inp['credit_9m'])*4/3
    nci=inp['minority_profit_q3']*4
    eps={'L':((revenue-opex)*(1-tax)-nci)/shares,'M':inp['eps_27_m'],'H':inp['eps_27_h']}
    roe={t:eps[t]*shares/equity for t in 'LMH'}
    if min(eps.values()) <= 0:
        raise ValueError('scenario earnings must be positive')
    y1,y2,tau=inp['y1'],inp['y2'],inp['tau']
    def multiples(rate):
        return {'L':1/rate if gl==0 else perpetual_pe(gl,roe['L'],rate),
                'M':three_segment_pe(NUM_YEAR,y1,y2,inp['rs_steady'],g,roe['M'],rate),
                'H':three_segment_pe(NUM_YEAR,y1,y2,inp['rs_steady_h'],g,roe['H'],rate)}
    ni_ytd=inp['ni_h1_26']+inp['ni_q3_consolidated']-inp['minority_profit_q3']
    payout_obs=round((inp['buyback_fy25']-inp['buyback_9m25']+inp['buyback_9m26'])/(inp['ni_q4_25']+ni_ytd),10)
    win_ni=inp['eps26_cons']*shares-ni_ytd
    win={t:max(win_ni*(1-g/roe[t]),0)/shares for t in 'MH'}
    def timed(pe,ep,t,rate):
        return ep*pe/(1+rate)**tau+win[t]/(1+rate)**(tau/2)
    def band_at(dr=0):
        rate=r+dr
        pe=multiples(rate)
        return (eps['L']*pe['L'],timed(pe['M'],eps['M'],'M',rate),timed(pe['H'],eps['H'],'H',rate))
    anchors=band_at()
    errors=ladder('eps',*(eps[t] for t in 'LMH'))+ladder('anchor',*anchors)
    if errors:
        raise ValueError('; '.join(errors))
    candidate={'status':'unavailable','label':'摩根士丹利FY2028','anchors':None}
    try:
        if inp['eps_28_ms'] > 0:
            g1=inp['eps_28_ms']/eps['M']-1
            values=(anchors[0],
                timed(three_segment_pe(NUM_YEAR,y1+1,y2+1,inp['rs_steady'],g,roe['M'],r,g1=g1,n=1),eps['M'],'M',r),
                timed(three_segment_pe(NUM_YEAR,y1+1,y2+1,inp['rs_steady_h'],g,roe['H'],r,g1=g1,n=1),eps['H'],'H',r))
            if all(math.isfinite(v) for v in values) and 0 <= values[0] < values[1] < values[2]:
                candidate={'label':'摩根士丹利FY2028','anchors':dict(zip('LMH',values))}
    except (ValueError,ZeroDivisionError,OverflowError):
        pass
    flags=['historical_basket_override','historical_crypto_low_qualitative_reference',
           'historical_convertible_dilution_assumptions',
           'historical_trump_service_breakdown_secondary_source']
    if check_branch(g,roe['M'],r,payout_obs,'M'):
        flags.append('historical_payout_branch_gap')
    if inp['rs_steady_h'] < inp['rs_steady']:
        flags.append('historical_steady_return_order')
    base=dict(zip('LMH',anchors))
    def prediction_reduction(share):
        return ((revenue-inp['pred_q3_2026']*4*share-opex)*(1-tax)-nci)/shares*multiples(r)['L']
    result={'ticker':'HOOD.US','currency':'USD','valuation_as_of':None,'framework_as_of':None,
        'historical_valuation_as_of':'2026-09-30','historical_framework_as_of':'2026-11-03',
        'basis_changed':None,'anchors':base,'candidate':candidate,'option':None,'review_flags':flags,
        'units':{'price':'USD_PER_SHARE'},
        'segments':{'company':{'unit':'USD_PER_SHARE','values':dict(base)}},
        'key_parameters':{'discount_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',r)},
          'growth_rate':{'unit':'RATIO','values':{'L':gl,'M':g,'H':g}},
          'forward_return':{'unit':'RATIO','values':roe},
          'steady_return':{'unit':'RATIO','values':{'L':None,'M':min(roe['M'],inp['rs_steady']),
                                                    'H':min(roe['H'],inp['rs_steady_h'])}}},
        'sensitivity':{'prediction_half':prediction_reduction(.5),
                       'prediction_70pct_activity_proxy':prediction_reduction(.7),
                       'prediction_zero':prediction_reduction(1.)}}
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',priced_r={'r_op':r},
            band_at=band_at,rates_loader=lambda _currency:rate_inputs,base_anchors=anchors))
    return result


def calculate(context):
    low=context['axes']['crypto']['rungs']['L']
    result=evaluate(INPUTS,context.get('rate_inputs'))
    # This reference is qualitative: an axis change needs research, but it is
    # not used as a numerical commission or allowed to alter the base bands.
    if not math.isfinite(INPUTS['eps_28_ms']):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'crypto_low_reference':low,'num_year':NUM_YEAR},HISTORICAL_PARTIAL_FINGERPRINT)
    return result
