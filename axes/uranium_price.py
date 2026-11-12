"""Historical long-run U3O8 price regimes, USD per pound."""
from math import isfinite

# L $70: Jefferies previous long-run estimate, 2026-09; FY2025 spot mean
# $73.5 as a nearby historical point. M $95: median of seven seller long-run
# prices, reported 2026-10-06. H $120: Stifel long-run forecast from 2029,
# 2025-10-28. The old axis uses these as sustained regimes, not spot quotes.
RUNGS={'L':70,'M':95,'H':120}
PRICED=('CCJ.US',)


def inputs(ticker):
    if ticker not in PRICED:
        raise ValueError(f'{ticker}: not a uranium price consumer')
    if set(RUNGS)!={'L','M','H'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in RUNGS.values()):
        raise ValueError('uranium prices must be finite')
    if not 0<RUNGS['L']<RUNGS['M']<RUNGS['H']:
        raise ValueError('uranium regimes must be positive and increasing')
    return {'rungs':dict(RUNGS),'axis_metadata':{'axis_id':'uranium','logical_id':'_AXIS.uranium',
        'title': '铀 U3O8 长期均衡价情景轴（现货与长期合同价收敛后的价位）', 'label': '铀长期均衡价', 'axis_type':'shared_scenario_axis','role':'priced','priced_mounts':list(PRICED),
        'reference_mounts':[],'historical_last_review_as_of':'2026-10-06',
        'historical_consensus':{'band':'M','as_of':'2026-10-06',
                                'source_note':'七家预测均为新闻转述，未逐家核验'}}}
