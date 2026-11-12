"""Historical reference ruler for specialty AI electronic glass fabric."""
from math import isfinite

# Citi 2026-08-14 specialty-fabric price range 30–40 CNY/m, midpoint 35;
# FY2027 weak margin 33.0% (Huayuan, 2026-03-27) and FY2028 midpoint/high
# 46.7%/49.9% (Guolian Minsheng and China Post, 2026-08-21). The reference
# gross margin 67.0% is the latter source's FY2028 estimate. 16,700 m/tonne
# derives from IPC-4412 fabric weight and width, excluding waste. Capex per
# annual meter 49.9 CNY from Sinoma's 35m-meter project (2026-09-21).
DATA = {'px_ai_gf_l':30,'px_ai_gf_m':35,'px_ai_gf_h':40,
        'nm_ai_gf_l':.330,'nm_ai_gf_m':.467,'nm_ai_gf_h':.499,
        'gm_ai_gf_ref':.670,'m_per_t_ai_gf':16700,'capex_per_m_ai_gf':49.9,'t_align':2028}
REFERENCES = ('0148.HK',)


def inputs(ticker):
    if ticker not in REFERENCES:
        raise ValueError(f'{ticker}: not an AI glass-fabric reference')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) for x in DATA.values()):
        raise ValueError('glass-fabric references must be finite')
    if not 0 < DATA['px_ai_gf_l'] <= DATA['px_ai_gf_m'] <= DATA['px_ai_gf_h']:
        raise ValueError('glass-fabric prices must be positive and ordered')
    if not 0 <= DATA['nm_ai_gf_l'] <= DATA['nm_ai_gf_m'] <= DATA['nm_ai_gf_h'] <= 1:
        raise ValueError('glass-fabric margins must be ordered ratios')
    if not 0 < DATA['gm_ai_gf_ref'] <= 1 or min(DATA['m_per_t_ai_gf'],DATA['capex_per_m_ai_gf']) <= 0:
        raise ValueError('glass-fabric gross margin and capacity inputs must be positive')
    if isinstance(DATA['t_align'],bool) or not isinstance(DATA['t_align'],int) or DATA['t_align'] <= 0:
        raise ValueError('glass-fabric alignment year must be a positive integer')
    return {**DATA,'axis_metadata':{'axis_id':'ai-glass-fabric','logical_id':'_AXIS.ai-glass-fabric',
        'axis_type':'peer_ruler_axis','role':'reference','priced_mounts':[],
        'reference_mounts':list(REFERENCES),'historical_last_review_as_of':'2026-10-05','historical_consensus':None}}
