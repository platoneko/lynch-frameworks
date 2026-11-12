"""历史中国 G.652.D 裸纤价格参考；不是实时价格或新研究。"""
import math

# CNY/芯公里，不含税。旧研究以 CRU 2024–25 谷底为 L、2018–25
# 八年均价为 M、2026 短缺报价为 H；原资料和历史不确定性见轴正文。
# 2021 只有 Q1 低点、2022 只有下半年、2023 为反推单点。
RUNG = {'L': 16.4, 'M': 27.3, 'H': 80.0}
SERIES = {2018: 60.4, 2019: 31.2, 2020: 20., 2021: 17.5,
          2022: 30.3, 2023: 26.1, 2024: 16.4, 2025: 16.4}
MEMBERS = {'600522.SH': 'priced', 'GLW.US': 'reference'}
# 卖方仅美银一家；中国移动招标反推裸纤约 72 元/芯公里是独立观察。
AXIS_METADATA = {'axis_id': 'optical-fiber', 'logical_id': '_AXIS.optical-fiber',
                 'title': '光纤价格情景轴（中国 G.652.D 裸纤现货年均价）', 'label': '中国裸纤价格', 'axis_type': 'shared_scenario_axis', 'historical_last_review_as_of': '2026-10-13',
                 'currency': 'CNY', 'unit': 'per_fiber_km',
                 'historical_consensus': {'band': 'H', 'as_of': '2026-09-07', 'kind': 'single_institution', 'institution': '美银',
                                          'source_note': '中国移动招标价反推是独立观察，并非第二家卖方预测'}}


def inputs(ticker):
    if ticker not in MEMBERS:
        raise ValueError(f'{ticker}: not an optical-fiber axis member')
    if set(RUNG) != {'L', 'M', 'H'} or set(SERIES) != set(range(2018, 2026)):
        raise ValueError('missing optical-fiber historical rungs or years')
    values = [*RUNG.values(), *SERIES.values()]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError('optical-fiber prices must be finite and positive')
    if not RUNG['L'] < RUNG['M'] < RUNG['H']:
        raise ValueError('optical-fiber tiers are not ordered')
    role = MEMBERS[ticker]
    metadata = {**AXIS_METADATA, 'role': role,
                'priced_mounts': sorted(name for name, item in MEMBERS.items() if item == 'priced'),
                'reference_mounts': sorted(name for name, item in MEMBERS.items() if item == 'reference')}
    if role != 'priced':
        metadata['historical_consensus'] = None
    return {'role': role,
            'stock_fields': {**{f'fiber_{tier.lower()}': RUNG[tier] for tier in 'LMH'},
                             **{f'fiber_fy{year}': value for year, value in SERIES.items()}},
            'axis_metadata': metadata}
