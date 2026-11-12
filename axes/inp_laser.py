"""Historical indium-phosphide laser reference for AAOI's optical-source case."""

# See axes/inp-laser.md: the margin path uses Source Photonics' analyst
# EBIT/revenue and Lumentum's pre-shortage margin. Capital intensity is based
# on the latter's FY26 PP&E / annualised Q4 revenue and may be low for fabs.
# The reference return and years reflect the user's 2026-10-16 decision.
DATA = {'ebit_margin_inp_normal': .2732, 'g2_inp_laser_normal': .04,
        't_shortage_end': 2027, 'cap_intensity': .288,
        'ebit_margin_inp_peer': .4506, 'ss_return_opt': .275,
        'y1_opt': 2029, 'y2_opt': 2035}
SUPPORTED = frozenset({'AAOI.US', 'COHR.US'})
HISTORICAL_REFERENCES = ('LITE.US', 'AAOI.US', 'COHR.US')


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f'{ticker}: InP laser consumer not migrated')
    return {**DATA, 'axis_metadata': {'axis_id': 'inp-laser', 'logical_id': '_AXIS.inp-laser',
            'axis_type': 'peer_ruler_axis', 'role': 'reference', 'priced_mounts': [],
            'reference_mounts': sorted(set(HISTORICAL_REFERENCES) | set(SUPPORTED)),
            'historical_last_review_as_of': '2026-10-16', 'historical_consensus': None}}
