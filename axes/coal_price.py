"""Qinhuangdao Q5500 annual-average coal scenario in CNY per tonne.

Frozen from _AXIS.coal-price, updated 2026-10-07. This data does not by
itself establish a stock valuation or authorization to publish one.
"""
from math import isfinite

# L: FY2025 annual average, Mysteel and China Shenhua 2025 annual report p.17.
# M: rounded FY2023-2026 YTD average (965, 855, 703, approximately 796),
# excluding the FY2022 spike; as of 2026-09-14.
# H: FY2023 annual average, Mysteel, cross-checked against Shenhua 2023 annual
# report p.15; the 2026-09 platform must last a year, not just one day.
RUNG_CNY_PER_TONNE = {'L': 703, 'M': 830, 'H': 965}

# FY2019 Mysteel, single source; FY2020 Fitch Bohua reverses 1030.4 / 1.787;
# FY2021 Fitch Bohua; FY2022 Mysteel, FY2023-25 Mysteel cross-checked against
# Shenhua and Huaneng annual reports. Each value is an annual average, not spot.
ANNUAL_SERIES = {2019: 588, 2020: 577, 2021: 1030, 2022: 1268,
                 2023: 965, 2024: 855, 2025: 703}

# The old axis states priced vs reference mounts; candidate names are not mounts.
# Shenhua self-produced coal price fit: FY2022-25 annual reports. Huaneng's
# FY2020-25 lagged fit is the adopted correction to the default line; as of
# 2026-09-27. These are disclosure/validation coordinates, not extra forecasts.
COORDINATES = {'1088.HK': {'asp_a': 330.99, 'asp_b': 0.2147},
               '600011.SH': {'fuel_lag_a': 78.865, 'fuel_lag_b': 0.19947, 'fuel_lag_c': 0.04574},
               # 000543: 2021–25 fuel-cost fit, original axis §4a. These
               # reference coordinates are in raw coal-axis price order
               # (703 / 830 / 965), not the generator's reversed tier order.
               # The stated three points have slightly higher precision than
               # the displayed line; preserve the ±0.0005 validation.
               '000543.SZ': {'uf_a': 0.0932, 'uf_b': 0.000193,
                             'uf_reference_prices': (703, 830, 965),
                             'uf_reference': (0.2292, 0.2537, 0.2799)}}

# Axis §4c-5, window stability, CNY/tonne; the endpoints are independent
# historical window choices and must not be inferred from the center.
MID_WINDOW_CNY_PER_TONNE = {'low': 821, 'high': 855}

MOUNTS = {'1088.HK': ('miner', 'priced'), '600011.SH': ('generator', 'reference'),
          '000543.SZ': ('generator', 'reference')}


def axis_metadata(role):
    # The old axis dated its consensus 2026-09-15, separately from its
    # 2026-10-07 review. Reference mounts do not inherit a consensus band.
    return {'axis_id': 'coal-price', 'logical_id': '_AXIS.coal-price',
            'title': '秦皇岛 5500 动力煤价格情景轴（长协 regime 下的煤价周期位置）',
            'label': '秦皇岛 5500 动力煤价格',
            'axis_type': 'shared_scenario_axis', 'role': role,
            'priced_mounts': [ticker for ticker, (_, mount) in MOUNTS.items() if mount == 'priced'],
            'reference_mounts': [ticker for ticker, (_, mount) in MOUNTS.items() if mount == 'reference'],
            'historical_last_review_as_of': '2026-10-07',
            'historical_consensus': {'band': 'M-H', 'as_of': '2026-09-15',
                                     'source_note': '高盛及另一家未具名外资机构'} if role == 'priced' else None}


def inputs(ticker, *, rungs=None):
    if ticker not in MOUNTS:
        raise ValueError(f'{ticker}: not a coal-axis mount')
    values = dict(RUNG_CNY_PER_TONNE if rungs is None else rungs)
    if set(values) != {'L', 'M', 'H'} or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
        for v in values.values()
    ) or not 0 < values['L'] < values['M'] < values['H']:
        raise ValueError('coal axis requires finite, positive increasing L/M/H')
    side, mount = MOUNTS[ticker]
    tiers = ('L', 'M', 'H') if side == 'miner' else ('H', 'M', 'L')
    coordinates = COORDINATES.get(ticker, {})
    if ticker == '000543.SZ':
        if (set(MID_WINDOW_CNY_PER_TONNE) != {'low', 'high'} or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
                    for v in MID_WINDOW_CNY_PER_TONNE.values()) or
                not 0 < MID_WINDOW_CNY_PER_TONNE['low'] <= MID_WINDOW_CNY_PER_TONNE['high']):
            raise ValueError('coal axis window must have positive ordered bounds')
        if not isinstance(coordinates, dict) or not {'uf_a', 'uf_b', 'uf_reference', 'uf_reference_prices'} <= coordinates.keys():
            raise ValueError('generator fuel-cost coordinates are missing')
        reference = coordinates['uf_reference']
        reference_prices = coordinates['uf_reference_prices']
        if (not isinstance(reference, (list, tuple)) or len(reference) != 3 or
                not isinstance(reference_prices, (list, tuple)) or len(reference_prices) != 3):
            raise ValueError('generator fuel-cost reference requires three values and three historical prices')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
               for v in (coordinates['uf_a'], coordinates['uf_b'], *reference, *reference_prices)):
            raise ValueError('generator fuel-cost coordinates must be finite')
    result = {'side': side, 'mount': mount,
              'tier_prices': {tier: values[source] for tier, source in zip(('L', 'M', 'H'), tiers)},
              'series': dict(ANNUAL_SERIES), 'coordinates': dict(coordinates)}
    # Preserve the original miner's numerical fields; metadata is versioned
    # separately by the runner and may change the full-input fingerprint.
    if ticker == '000543.SZ':
        result['mid_window'] = dict(MID_WINDOW_CNY_PER_TONNE)
    result['axis_metadata'] = axis_metadata(mount)
    return result
