"""Shared historical 2027 Brent price scenarios; USD per barrel."""
from math import isfinite

# 2025 full-year Brent was $68.2 (CNOOC 2025 annual report p.70),
# rounded to $68 in the old axis. The middle $75 is the historical median
# of EIA, Bank of America, HSBC and Goldman forecasts (2026-09-08 to 09-14).
# The high $85 is HSBC's 2027 forecast (2026-09-08), near 2026H1 actual
# $87.6. These old scenarios are not live prices or new market forecasts.
RUNGS = {'L': 68, 'M': 75, 'H': 85}
MOUNTS = ('0857.HK', '0883.HK')


def inputs(ticker):
    if ticker not in MOUNTS:
        raise ValueError(f'{ticker}: not a Brent scenario consumer')
    if set(RUNGS) != {'L', 'M', 'H'} or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
        for value in RUNGS.values()
    ) or not 0 < RUNGS['L'] < RUNGS['M'] < RUNGS['H']:
        raise ValueError('Brent scenarios must be finite, positive and increasing')
    return {'rungs': dict(RUNGS), 'role': 'scenario', 'axis_metadata': {
        'axis_id': 'brent-oil', 'logical_id': '_AXIS.brent-oil',
        'title': '布伦特原油 USD 价格情景轴（霍尔木兹中断后的 2027 油价 regime）', 'label': '布伦特原油价格', 'axis_type': 'shared_scenario_axis', 'historical_last_review_as_of': '2026-09-15',
        'role': 'priced', 'priced_mounts': list(MOUNTS), 'reference_mounts': [],
        'historical_consensus': {'band': 'M', 'as_of': '2026-09-10'}}}
