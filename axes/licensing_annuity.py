"""历史授权业务税前 EV/EBIT 倍数共同参考。"""

# 低档为美银 other businesses 税前 EV/EBIT（2026-07-24）；中档为
# QTL 卖方 SOTP 税前换算中值（2026-09-14）；高档以 InterDigital
# EV/EBITDA 作小折旧近似（2026-09-04）。两家公司税前口径一致，但
# 业务差异和高档代理误差仍须后续研究核对。
LADDER = {
    'id': 'patent_licensing_annuity_evebit', 'version': '2026-09-14', 'measure': 'pre_tax_ev_ebit',
    'businesses': {'QCOM.US': 'qtl', 'NOK.US': 'technology_standards'},
    'tiers': {'l': 10., 'm': 12.4, 'h': 18.9},
}


def inputs(ticker):
    if ticker not in LADDER['businesses']:
        raise ValueError(f'{ticker}: not a licensing ladder consumer')
    return {**LADDER, 'businesses': dict(LADDER['businesses']), 'tiers': dict(LADDER['tiers'])}
