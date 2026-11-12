#!/usr/bin/env python3
"""Coherent FY2028 segment valuation; historical inputs, USD/share."""
import math
from lib.gordon import check_g_cap, check_r, perpetual_pe
from lib.inputs import ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES={'libraries':('gordon','inputs','partial_basis','rf_report'),
              'axes':{'laser':'inp_laser','optical':'optical_comms','capex':'ai_capex'}}
HISTORICAL_PARTIAL_FINGERPRINT='673aa6a4a1a99d0110bfbd5f626a72b103677215595b6f94c41b2ff401d7229b'
P_K=(0.,.25,1.)

# FY27 Q1 report, balance sheet and note 13, 2026-09-30, released 2026-11-04:
# latest 196.958669m shares plus 5.813m quarter-equivalents; parent equity
# $11,330.017m; debt $4,000.598m less cash $1,552.929m and short investments
# $200m, excluding $583.414m restricted cash. The remaining FY27 consensus
# profit excludes the already reported non-GAAP EPS of $2.09.
# FY2027 revenue $10,618m and FY2028 revenue mean/high $14,675m/$18,714m
# are pre-earnings consensus (2026-09-11); they have not been refreshed.
# Low industrial reference $1,800m is separately taken from the FY2027
# construction; low datacom $8,818m is rounded to the old $8,820m precision.
# FY2026 industrial revenue $1,843.6m informs the $1,900m flat estimate.
# The 19% tax is management's normalized rate, FY27 release table 6 note 7.
# Long-run 6% datacom growth is the capped 6.06% peer median; industrial
# growth is zero, with no two-company peer reference (2026-09-11/14).
# The $4bn SiC transaction was implied by 2023-12-04 minority investments;
# 2026-09-30 NCI trailing loss is $20.019m. This is an old potential-value
# ceiling, not a current transaction or proven price. Growth funding gap of
# zero is an unquantified placeholder, not verified cash sufficiency.
INPUTS={
 'shares_basic':196958669,'shares_equiv':5813000,'equity':11330017000,
 'eps_cons_fy27':10.418,'eps_booked_fy27':2.09,'growth_gap':0.,
 'rev_fy27_cons':10618.,'rev_ind_low_reference':1800.,'rev_fy28_mean':14675.,'rev_fy28_high':18714.,
 'rev_ind':1900.,'m_dcc_l':.23,'m_dcc_m':.275,'m_dcc_h':.30,
 'm_ind_l':.20,'m_ind_m':.23,'m_ind_h':.26,'corp_pct':.05,'tax_rate':.19,
 'r_perp':.10,'g2_dcc':.06,'g2_ind':0.,'t_disc':.75,
 'debt_total':4000.598,'cash':1552.929,'short_investments':200.,
 'eps_cons_fy28':13.96,'sic_stake':.75,'sic_deal_value':4000.,'sic_nci_loss':20.019,
 'num_year':2028}
TIERS=('L','M','H')

def _lin(cal: int, y1: int, y2: int, a: float, b: float) -> float:
    """a through Y1, linear to b at Y2, b after (valuation-rules ② 稳态回报三段)."""
    if cal <= y1:
        return a
    if cal >= y2:
        return b
    return a + (b - a) * (cal - y1) / (y2 - y1)


def path_value(t0: int, y1: int, y2: int, r_s: float, g: float, roe: float, r: float) -> float:
    """Gordon multiple on next-period earnings with the three-segment RONIC path; t = 1 <->
    fiscal year t0; RONIC = forward through Y1, linear to min(forward, r_s) at Y2, tail after."""
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    rs = min(roe, r_s)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        pay = min(1.0, 1.0 - g / _lin(cal, y1, y2, roe, rs))
        if cal > y1 and cal >= y2:
            return pv + e * pay / ((r - g) * (1 + r) ** (t - 1))
        pv += e * pay / (1 + r) ** t
        e *= 1 + g
        t += 1



def evaluate(inp, rate_inputs=None):
    require_whole_years(inp,('num_year','y1','y2'))
    if not inp['num_year'] <= inp['y1'] < inp['y2']:
        raise ValueError('return-path years invalid')
    shares=inp['shares_basic']+inp['shares_equiv']
    if shares <= 0 or inp['equity'] <= 0:
        raise ValueError('shares and equity must be positive')
    r=inp['r_perp']
    errors=check_r(r,'r_perp',4)
    for leg in ('dcc','ind'):
        errors+=check_g_cap(inp[f'g2_{leg}'],r,f'g2_{leg}')
    if errors:
        raise ValueError('; '.join(errors))
    revenue={'L':round(inp['rev_fy27_cons']-inp['rev_ind_low_reference'],-1),
             'M':inp['rev_fy28_mean']-inp['rev_ind'],
             'H':inp['rev_fy28_high']-inp['rev_ind']}
    unbooked=inp['eps_cons_fy27']-inp['eps_booked_fy27']
    if unbooked < 0 or inp['growth_gap'] < 0:
        raise ValueError('unbooked profit or funding gap invalid')
    bps0=(inp['equity']+inp['growth_gap']*1e6)/shares
    debt_ps=-(inp['debt_total']-inp['cash']-inp['short_investments'])*1e6/shares
    gap_ps=inp['growth_gap']*1e6/shares
    def scenario(t,rate):
        rev_dcc=revenue[t]
        total=rev_dcc+inp['rev_ind']
        corporate=inp['corp_pct']*total
        ep_dcc=(rev_dcc*inp[f'm_dcc_{t.lower()}']-corporate*rev_dcc/total)*(1-inp['tax_rate'])*1e6/shares
        ep_ind=(inp['rev_ind']*inp[f'm_ind_{t.lower()}']-corporate*inp['rev_ind']/total)*(1-inp['tax_rate'])*1e6/shares
        eps=ep_dcc+ep_ind
        if eps <= 0:
            raise ValueError('scenario operating earnings must be positive')
        growth=(ep_dcc*inp['g2_dcc']+ep_ind*inp['g2_ind'])/eps
        roll=growth*unbooked/eps
        if roll>=1:
            raise ValueError('opening book roll diverges')
        book=bps0/(1-roll)
        roe=eps/book
        p_dcc=path_value(inp['num_year'],inp['y1'],inp['y2'],inp['ss_return'],inp['g2_dcc'],roe,rate)
        p_ind=path_value(inp['num_year'],inp['y1'],inp['y2'],inp['ss_return'],inp['g2_ind'],roe,rate)
        return {'eps_dcc':ep_dcc,'eps_ind':ep_ind,'eps':eps,'roe':roe,'g_co':growth,
                'bps_open':book,'b1':growth/roe,'pe_dcc':p_dcc,'pe_ind':p_ind,
                'v_dcc':ep_dcc*p_dcc,'v_ind':ep_ind*p_ind,
                'sum':ep_dcc*p_dcc+ep_ind*p_ind,'blend':(ep_dcc*p_dcc+ep_ind*p_ind)/eps}
    def calculate_at(rate):
        s={t:scenario(t,rate) for t in TIERS}
        disc=(1+rate)**(-inp['t_disc'])
        win_eps=unbooked*s['M']['eps']/inp['eps_cons_fy28']
        win={t:0. if inp['growth_gap']>0 else
             win_eps*(1-min(1,max(0,s[t]['b1'])))*(1+rate)**(-inp['t_disc']/2) for t in TIERS}
        result={t:s[t]['sum']*disc+win[t]+debt_ps-gap_ps for t in TIERS}
        return s,disc,win,result
    s,disc,win,anchors=calculate_at(r)
    errors=ladder('anchor',*(anchors[t] for t in TIERS))
    if errors:
        raise ValueError('; '.join(errors))
    option={'status':'unavailable','label':'碳化硅业务','anchors':None}
    try:
        stake=inp['sic_stake']
        if 0 <= stake < 1 and inp['sic_deal_value'] >= 0 and inp['sic_nci_loss'] >= 0:
            deal=stake*inp['sic_deal_value']*1e6/shares
            drag=inp['sic_nci_loss']/(1-stake)*1e6/shares*perpetual_pe(inp['g2_ind'],s['M']['roe'],r)*disc
            value=deal+drag
            plus=tuple(anchors[t]+p*value for t,p in zip(TIERS,P_K))
            if all(math.isfinite(x) for x in (value,*plus)) and value>0 and 0<=plus[0]<plus[1]<plus[2]:
                option={'value':value,'weights':dict(zip(TIERS,P_K)),'anchors':dict(zip(TIERS,plus))}
    except (ValueError,ZeroDivisionError,OverflowError):
        pass
    flags=['historical_consensus_pre_earnings',
           'historical_segment_capital_allocation_unverified','historical_sic_transaction_ceiling']
    if inp['growth_gap']==0:
        flags.append('historical_funding_gap_unquantified')
    if abs(s['M']['eps']/inp['eps_cons_fy28']-1)>.20 or not s['M']['eps']<=inp['eps_cons_fy28']<=s['H']['eps']:
        flags.append('historical_consensus_differs_from_segment_estimate')
    result={'ticker':'COHR.US','currency':'USD','valuation_as_of':None,'framework_as_of':None,
        'historical_valuation_as_of':'2026-09-30','historical_framework_as_of':'2026-11-05',
        'basis_changed':None,'anchors':anchors,'candidate':None,'option':option,'review_flags':flags,
        'units':{'price':'USD_PER_SHARE'},
        'segments':{
            'datacom':{'unit':'USD_PER_SHARE','values':{t:s[t]['v_dcc']*disc for t in TIERS}},
            'industrial':{'unit':'USD_PER_SHARE','values':{t:s[t]['v_ind']*disc for t in TIERS}},
            'window':{'unit':'USD_PER_SHARE','values':win},
            'debt_and_gap':{'unit':'USD_PER_SHARE','values':dict.fromkeys(TIERS,debt_ps-gap_ps)}},
        'key_parameters':{
            'discount_rate':{'unit':'RATIO','values':dict.fromkeys(TIERS,r)},
            'datacom_growth':{'unit':'RATIO','values':dict.fromkeys(TIERS,inp['g2_dcc'])},
            'industrial_growth':{'unit':'RATIO','values':dict.fromkeys(TIERS,inp['g2_ind'])},
            'forward_return':{'unit':'RATIO','values':{t:s[t]['roe'] for t in TIERS}},
            'datacom_steady_return':{'unit':'RATIO','values':{t:min(s[t]['roe'],inp['ss_return']) for t in TIERS}}},
        'scenario':s,
        'sensitivity':{'window_fully_retained':{t:anchors[t]-win[t] for t in TIERS}}}
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',priced_r={'r_perp':r,'r_disc':r},
            band_at=lambda dr:tuple(calculate_at(r+dr)[3][t] for t in TIERS),
            rates_loader=lambda _currency:rate_inputs,base_anchors=tuple(anchors[t] for t in TIERS)))
    return result


def calculate(context):
    laser=context['axes']['laser']; optical=context['axes']['optical']; capex=context['axes']['capex']
    selected={'ss_return':laser['ss_return_opt'],'y1':laser['y1_opt'],'y2':laser['y2_opt']}
    refs={'optical':dict(optical['oe']),'capex':dict(capex['rungs'])}
    result=evaluate({**INPUTS,**selected},context.get('rate_inputs'))
    optional=('sic_stake','sic_deal_value','sic_nci_loss')
    if any(not math.isfinite(INPUTS[k]) for k in optional):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'laser':selected,'references':refs,'option_weights':P_K},HISTORICAL_PARTIAL_FINGERPRINT)
    # Both businesses share the same company return path; expose their own
    # adopted growth alongside that common return and discount assumption.
    params = result['key_parameters']
    for leg, growth in (('datacom', 'datacom_growth'), ('industrial', 'industrial_growth')):
        params[leg] = {'discount_rate': params['discount_rate'], 'growth_rate': params[growth],
                       'forward_return': params['forward_return'],
                       'steady_return': params['datacom_steady_return']}
    result['option']['value_unit']='USD_PER_SHARE'
    return result
