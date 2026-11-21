"""ChiNext TRI duration channel, mapped to the same-day ETF unit NAV."""

DEPENDENCIES = {
    'libraries': ('etf', 'fund_history', 'value100_inputs'),
    'axes': {'etf_duration': 'etf_duration'},
}
TICKER = '159915.SZ'
INDEX = '399606'
INDEX_START = '2010-05-31'
REFERENCE_DATE = '2026-11-20'
FRAMEWORK_DATE = '2026-11-21'


def calculate(context):
    # The two native 399606 series from CNI meet on 2015-12-01. The
    # 2026-11-20 published unit NAV of 2.2269 is from Eastmoney's fund archive.
    snapshot = context['external_inputs']
    fund_channel = context['axes']['etf_duration']['fund_channel']
    channel, _, scale, reference, flags = fund_channel(snapshot, TICKER, INDEX, REFERENCE_DATE)
    if channel['start'] != INDEX_START:
        raise ValueError('ChiNext TRI must cover the declared full history from 2010-05-31')
    anchors = channel['anchors']
    return {
        'ticker': TICKER,
        'currency': 'CNY',
        'valuation_as_of': REFERENCE_DATE,
        'framework_as_of': FRAMEWORK_DATE,
        'anchors': anchors,
        'candidate': None,
        'option': None,
        'basis_changed': None,
        'partial_basis_changed': False,
        'segments': {'fund': {'values': anchors, 'unit': 'CNY_PER_UNIT'}},
        'units': {'price': 'CNY_PER_UNIT'},
        'key_parameters': {'method': 'etf_duration_trend_channel'},
        'operating': {'duration_channel': channel, 'nav_index_factor': scale},
        'fund_reference': reference,
        'fund_reference_status': 'same_day_fund_nav',
        'review_flags': flags,
    }
