"""Historical shared ruler for solid-state cell manufacturing."""
from math import isfinite

# Dongwu Securities, 2026-09-24: full-solid-state forecasts 1.8 / 1.5 / .8
# CNY per Wh in 2029 / 2030 / 2035; the old framework uses the 2035 value
# as a steady price, not the launch premium. Liquid-cell FY2022–25 operating
# margins: Gotion mean 1.73%, CATL mean 14.13%; 3pp is an explicit entrant
# discount for uncertain yield and customer qualification (2026-10-05).
# CATL's 2026-09-30 peer reverse-solve 7.34% is a single adjacent-business
# observation; each stock applies its own growth cap. Samsung SDI FY2021–25
# invested-capital mean 6.9% is the mature reference, not the stock's rate.
DATA = {'ssb_px_2029': 1.8, 'ssb_px_2030': 1.5, 'ssb_px_ss': .8,
        'ssb_opm_weak': .0173, 'ssb_opm_strong': .1413, 'ssb_entrant_disc': .03,
        'g2_ssb_src': .0734, 't_align': 2027, 'ss_return_peer_ssb': .069,
        'fall_years_ssb': 4}
REFERENCES = ('1772.HK',)


def inputs(ticker):
    if ticker not in REFERENCES:
        raise ValueError(f'{ticker}: not a solid-state reference')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in DATA.values()):
        raise ValueError('solid-state reference data must be finite')
    if min(DATA[k] for k in ('ssb_px_2029', 'ssb_px_2030', 'ssb_px_ss')) <= 0:
        raise ValueError('solid-state reference prices must be positive')
    if not 0 <= DATA['ssb_opm_weak'] <= DATA['ssb_opm_strong'] <= 1:
        raise ValueError('solid-state reference margins must be ordered')
    if not 0 <= DATA['ssb_entrant_disc'] <= DATA['ssb_opm_strong']:
        raise ValueError('entrant discount outside reference margin')
    if any(isinstance(DATA[k], bool) or not isinstance(DATA[k], int) or DATA[k] <= 0
           for k in ('t_align', 'fall_years_ssb')):
        raise ValueError('alignment and fall period must be positive whole years')
    return {**DATA, 'axis_metadata': {'axis_id': 'solid-state-battery',
        'logical_id': '_AXIS.solid-state-battery', 'axis_type': 'peer_ruler_axis',
        'role': 'reference', 'priced_mounts': [], 'reference_mounts': list(REFERENCES),
        'historical_last_review_as_of': '2026-10-16', 'historical_consensus': None}}
