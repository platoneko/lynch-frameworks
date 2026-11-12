"""Historical reference ruler for high-speed electronic copper foil."""
from math import isfinite

# Dongwu Securities copper foil report, 2026-06-10: HVLP1/2/3 net profit
# per tonne ranges 1–2 / 3–4 / 5–7 (ten thousand CNY), using midpoints;
# estimated capex is 6 per tonne of annual capacity and HVLP3 yield 70%.
# The 2028 alignment is the peer ruler's reference year, 2026-10-05.
DATA = {'pt_hvlp_l':1.5,'pt_hvlp_m':3.5,'pt_hvlp_h':6,
        'capex_per_t_hvlp':6,'yield_hvlp3':.7,'t_align':2028}
REFERENCES = ('0148.HK',)


def inputs(ticker):
    if ticker not in REFERENCES:
        raise ValueError(f'{ticker}: not a high-speed copper-foil reference')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) for x in DATA.values()):
        raise ValueError('copper-foil references must be finite')
    if not 0 < DATA['pt_hvlp_l'] <= DATA['pt_hvlp_m'] <= DATA['pt_hvlp_h']:
        raise ValueError('copper-foil profits must be positive and ordered')
    if not 0 < DATA['yield_hvlp3'] <= 1:
        raise ValueError('copper-foil yield must be a positive ratio')
    if DATA['capex_per_t_hvlp'] <= 0:
        raise ValueError('copper-foil capacity cost must be positive')
    if isinstance(DATA['t_align'],bool) or not isinstance(DATA['t_align'],int) or DATA['t_align'] <= 0:
        raise ValueError('copper-foil alignment year must be a positive integer')
    return {**DATA,'axis_metadata':{'axis_id':'hvlp-copper-foil','logical_id':'_AXIS.hvlp-copper-foil',
        'axis_type':'peer_ruler_axis','role':'reference','priced_mounts':[],
        'reference_mounts':list(REFERENCES),'historical_last_review_as_of':'2026-10-05','historical_consensus':None}}
