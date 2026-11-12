"""Historical reference ruler for advanced logic foundry businesses."""
from math import isfinite

# TSMC FY2016–25 operating margin mean 42.4%, 2019 low 35.2%; Samsung
# non-memory 2021/22 estimates 5%/9% from Daishin Securities, 2021-10-22.
# The 12.4pp yield/scale discount is the original research judgment.
# Foundry peer median g 2.48% and TSMC high-world g 5.66% were reverse-solved
# on 2026-09-14; they are references, not a new forecast or actual return.
# Mature foundries' historical return median 16.9% (Tower 19.4%, UMC 16.9%,
# GlobalFoundries 3.0%) was selected 2026-10-16. The user set the common
# TSMC-based return-path minimum years 2030 / 2035 on 2026-10-18.
DATA = {'opm_strong_peer':.424, 'opm_strong_peer_min':.352, 'opm_weak_peer':.07,
        'yield_discount':.124, 'g2_foundry_src':.0248, 'g2_foundry_h_src':.0566,
        't_align':2030, 'ss_return_foundry':.169, 'fall_years_foundry':6,
        'y1_floor_foundry':2030, 'y2_floor_foundry':2035}
REFERENCES = ('INTC.US', '0981.HK')


def inputs(ticker):
    if ticker not in REFERENCES:
        raise ValueError(f'{ticker}: not an advanced-foundry reference')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in DATA.values()):
        raise ValueError('foundry reference data must be finite')
    if not 0 <= DATA['opm_weak_peer'] <= DATA['opm_strong_peer'] <= 1:
        raise ValueError('foundry margins must be ordered')
    if not 0 <= DATA['yield_discount'] <= DATA['opm_strong_peer']:
        raise ValueError('foundry yield discount outside margin')
    for key in ('t_align','fall_years_foundry','y1_floor_foundry','y2_floor_foundry'):
        if isinstance(DATA[key],bool) or not isinstance(DATA[key],int) or DATA[key] <= 0:
            raise ValueError(f'{key} must be a positive whole number')
    if DATA['y1_floor_foundry'] >= DATA['y2_floor_foundry']:
        raise ValueError('return path floors must increase')
    return {**DATA, 'axis_metadata': {'axis_id':'leading-edge-foundry',
        'logical_id':'_AXIS.leading-edge-foundry', 'axis_type':'peer_ruler_axis',
        'role':'reference', 'priced_mounts':[], 'reference_mounts':list(REFERENCES),
        'historical_last_review_as_of':'2026-10-18', 'historical_consensus':None}}
