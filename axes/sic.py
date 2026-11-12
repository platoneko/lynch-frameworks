"""历史碳化硅同业尺：只提供共同参考，不提供任一公司的盈利。"""

from math import isfinite

# 2026-10-02 功率半导体/碳化硅五家同尺反解增长中位数；
# 2026-10-03 两家公司最远可比预测对齐年；2026-10-19 成熟同业
# 数据不足，采用有壁垒重资产 15% 的兜底。回报路径年限由
# AI 资本开支轴提供，避免在这里重复存储另一份数据。
DATA = {'g2_sic_src': .0712, 't_align': 2028, 'ss_return_sic': .15}
SUPPORTED = frozenset({'2631.HK', 'WOLF.US'})


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f'{ticker}: not a SiC ruler consumer')
    if (isinstance(DATA['t_align'], bool) or not isinstance(DATA['t_align'], int) or
            any(isinstance(DATA[k], bool) or not isinstance(DATA[k], (int, float))
                or not isfinite(DATA[k]) for k in ('g2_sic_src', 'ss_return_sic')) or
            DATA['g2_sic_src'] < 0 or not 0 < DATA['ss_return_sic'] < 1):
        raise ValueError('invalid SiC peer reference')
    return {**DATA, 'axis_metadata': {
        'axis_id': 'sic', 'logical_id': '_AXIS.sic',
        'title': '碳化硅（衬底 → 外延 → 功率器件）同业尺轴', 'label': '碳化硅',
        'axis_type': 'peer_ruler_axis', 'role': 'reference',
        'priced_mounts': [], 'reference_mounts': ['WOLF.US', '2631.HK'],
        'historical_last_review_as_of': '2026-10-16', 'historical_consensus': None}}
