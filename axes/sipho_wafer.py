"""Historical shared silicon-photonics and mature-foundry reference values."""
from math import isfinite

# SiPho margin is inferred from TSEM's two-period company disclosures; the
# wafer price is GFS 2025 cost per 300 mm equivalent wafer grossed up by that
# margin. Both are proxies, not measured SiPho sales prices.
DATA = {'g2_sipho_src': 0.0664, 'gm_sipho': 0.516, 't_align': 2028.0, 'asp_sipho_300': 4494.0, 'gf_cogs_2025': 5101000000.0, 'gf_wafers_2025': 2345000.0, 'ss_return_cap_sipho': 0.3, 'ss_return_sipho_ref': 0.169, 'y1_sipho': 2030.0, 'y2_sipho': 2035.0}

def inputs(ticker):
    if ticker not in ('GFS.US', 'TSEM.US'):
        raise ValueError('silicon-photonics axis consumer not migrated')
    if any(not isfinite(v) for v in DATA.values()):
        raise ValueError('axis inputs must be finite')
    return {**DATA, 'axis_metadata': {'axis_id': 'sipho-wafer',
            'logical_id': '_AXIS.sipho-wafer', 'axis_type': 'peer_ruler_axis',
            'role': 'reference', 'priced_mounts': [],
            'reference_mounts': ['GFS.US', 'TSEM.US'],
            'historical_last_review_as_of': '2026-10-16', 'historical_consensus': None}}
