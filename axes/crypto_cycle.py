"""Historical 2028 Coinbase normalized EBITDA regimes, USD 100 million."""
from math import isfinite

# Morgan Stanley coverage, 2026-09-10, Wisburg 105136 / 105030: bear, base
# and bull normalized 2028 adjusted EBITDA $1.4bn / $3.0bn / $4.0bn.
# This is one institution, not a multi-house consensus. Its 2027 rebound
# forecast is not the normalized 2028 earnings used by the old framework.
# Bear and base BTC-price assumptions were not disclosed in the available
# summary; the bull $202k assumption is not a live or required input.
RUNGS = {'L':14,'M':30,'H':40}
PRICED = ('COIN.US',)
REFERENCES = ('HOOD.US',)


def inputs(ticker):
    if ticker not in (*PRICED,*REFERENCES):
        raise ValueError(f'{ticker}: not a crypto-cycle consumer')
    if set(RUNGS)!={'L','M','H'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in RUNGS.values()):
        raise ValueError('crypto-cycle rungs must be finite')
    if not 0 < RUNGS['L'] < RUNGS['M'] < RUNGS['H']:
        raise ValueError('crypto-cycle EBITDA rungs must increase')
    priced=ticker in PRICED
    selected=dict(RUNGS) if priced else {'L':RUNGS['L']}
    return {'rungs':selected,'axis_metadata':{'axis_id':'crypto-cycle','logical_id':'_AXIS.crypto-cycle',
        'title': '加密活跃度情景轴', 'label': '加密活跃度', 'axis_type':'shared_scenario_axis','role':'priced' if priced else 'reference',
        'priced_mounts':list(PRICED),'reference_mounts':list(REFERENCES),
        'historical_last_review_as_of':'2026-09-23',
        'historical_consensus':{'band':'M','as_of':'2026-09-10','kind':'single_institution','institution':'摩根士丹利'} if priced else None}}
