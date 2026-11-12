"""Historical 2027 CoWoS supply and mutually exclusive allocations."""
from math import isfinite

# Morgan Stanley 2026-08-28, Wisburg 103203: 200k wafers/month supply;
# annual demand NVDA 1.222m, AMD .530m, AVGO .484m and others .458m.
# α assigns all shortage to NVDA, β shares it proportionally, γ supplies
# NVDA in full and shares the remaining shortage among the other customers.
# The old stock scripts used NVDA β rounded to 100 wafers and AVGO β/γ to
# 1,000; the other customer absorbs each rounding residual, so each state
# still sums exactly to supply and reproduces both old individual inputs.
SUPPLY=2_400_000
DEMAND={'NVDA':1_222_000,'AMD':530_000,'AVGO':484_000,'OTHER':458_000}
PRICED=('NVDA.US','AVGO.US')
REFERENCES=('TSM.US',)


def inputs(ticker):
    if ticker not in (*PRICED,*REFERENCES):
        raise ValueError(f'{ticker}: not a CoWoS axis consumer')
    if set(DEMAND)!={'NVDA','AMD','AVGO','OTHER'}:
        raise ValueError('CoWoS demand must identify all four customers')
    values=[SUPPLY,*DEMAND.values()]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<=0 for v in values):
        raise ValueError('CoWoS supply and demand must be positive and finite')
    demand=sum(DEMAND.values())
    if not DEMAND['NVDA'] <= SUPPLY < demand or demand-SUPPLY > DEMAND['NVDA']:
        raise ValueError('CoWoS shortage cannot be allocated under the historical three states')
    alpha={**DEMAND,'NVDA':DEMAND['NVDA']-(demand-SUPPLY)}
    beta={'NVDA':round(DEMAND['NVDA']*SUPPLY/demand,-2),
          'AMD':round(DEMAND['AMD']*SUPPLY/demand,-3),
          'AVGO':round(DEMAND['AVGO']*SUPPLY/demand,-3)}
    beta['OTHER']=SUPPLY-sum(beta.values())
    rest_supply=SUPPLY-DEMAND['NVDA']
    rest_demand=demand-DEMAND['NVDA']
    gamma={'NVDA':DEMAND['NVDA'],'AMD':round(DEMAND['AMD']*rest_supply/rest_demand,-3),
           'AVGO':round(DEMAND['AVGO']*rest_supply/rest_demand,-3)}
    gamma['OTHER']=SUPPLY-sum(gamma.values())
    states={'alpha':alpha,'beta':beta,'gamma':gamma}
    if any(any(value<0 for value in state.values()) or abs(sum(state.values())-SUPPLY)>1e-6
           for state in states.values()):
        raise ValueError('CoWoS allocations must be nonnegative and exhaust supply')
    priced=ticker in PRICED
    result={'states':states,'supply_wpm':SUPPLY/12,
        'axis_metadata':{'axis_id':'cowos-capacity','logical_id':'_AXIS.cowos-capacity',
        'title': 'CoWoS 产能与配额情景轴', 'label': 'CoWoS 产能与配额', 'axis_type':'shared_scenario_axis','role':'priced' if priced else 'reference',
        'priced_mounts':list(PRICED),'reference_mounts':list(REFERENCES),
        'historical_last_review_as_of':'2026-09-08',
        'historical_consensus':{'band':'M','as_of':'2026-09-17'} if priced else None}}
    if priced:
        player=ticker.split('.')[0]
        order=('alpha','beta','gamma') if player=='NVDA' else ('gamma','beta','alpha')
        result['quotas']={tier:states[state][player] for tier,state in zip('LMH',order)}
    return result
