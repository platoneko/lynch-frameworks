"""南向历史参考轴：提供历史事实和参考关系，不生成个股估值。"""

# 旧轴于 2026-09-27 更新；历史比值由 Longbridge 日线与 yfinance
# 汇率计算，日期和口径见同目录 southbound-repricing.md。原轴只用来
# 判断南向定价方向与要求 A/H 对照，不应替代企业盈利或倍数。
HISTORICAL_REVIEW_AS_OF = '2026-09-27'
MONTHLY_NET_INFLOW_HKD_100M = {'L': 271, 'M': 629, 'H': None}
FLOW_PERIODS = {'L': '2026-06', 'M': '2026-07', 'H': None}
DATED_HA = {
    '000338.SZ': (1.029, .92), '600036.SH': (1.081, .85),
    '6655.HK': (.582, .59), '1766.HK': (.742, .84), '1072.HK': (.694, .83),
}
HA_ANNUAL_MEAN = {
    '000338.SZ': [0.801, 0.843, 0.824, 0.953, 1.032],
    '600036.SH': [0.993, 0.965, 0.906, 1.035, 1.088],
    '6655.HK': [0.475, 0.483, 0.507, 0.690, 0.638],
    '1766.HK': [0.509, 0.595, 0.580, 0.683, 0.762],
    '1072.HK': [0.503, 0.519, 0.560, 0.746, 0.812],
}
# 600011 是旧轴表中的参考对象，但无完整逐年序列，不能虚构。
REFERENCE_TICKERS = (*HA_ANNUAL_MEAN, '600011.SH')
BANK_H_SHARES = {'600036.SH': '3968.HK'}


def inputs(ticker):
    if ticker not in REFERENCE_TICKERS:
        raise ValueError(f'{ticker}: not a southbound reference')
    values = HA_ANNUAL_MEAN.get(ticker)
    reading = DATED_HA.get(ticker)
    return {
        'role': 'reference',
        'h_share': BANK_H_SHARES.get(ticker),
        'annual_ha_mean': None if values is None else dict(zip(range(2022, 2027), values)),
        # The dates in the source label its separate spot reading; they do not
        # establish the observation end date for each annual mean.
        'annual_mean_as_of': None,
        'dated_reading_as_of': ('2026-09-09' if ticker == '1072.HK' else
                                '2026-09-08' if values is not None else None),
        'dated_ha': None if reading is None else reading[0],
        'dated_ha_percentile': None if reading is None else reading[1],
        'monthly_net_inflow_hkd_100m': dict(MONTHLY_NET_INFLOW_HKD_100M),
        'flow_periods': dict(FLOW_PERIODS),
        'axis_metadata': {
            'axis_id': 'southbound-repricing',
            'logical_id': '_AXIS.southbound-repricing',
            'axis_type': 'shared_scenario_axis',
            'title': '南向定价权情景轴',
            'label': '南向定价权',
            'role': 'reference',
            'priced_mounts': [],
            'reference_mounts': list(REFERENCE_TICKERS),
            'historical_last_review_as_of': HISTORICAL_REVIEW_AS_OF,
            'historical_consensus': None,
        },
    }
