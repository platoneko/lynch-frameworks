"""Historical pluggable-module peer-ruler snapshot; partial pilot interface."""
from math import isfinite

# 2% is the user's 2026-09-29 decision, below named 4% macro reference.
# Only one 2026-09-30 comparable enters the peer set (0.87%); it corroborates
# the direction but is not a sufficient peer consensus. Old axis §2.
DATA = {"g2_pluggable": 0.02, "t_align": 2028,
        # User 2026-10-19: prior cycle unavailable after structural change;
        # mature same-business peers absent, fall back to 18% light assembly.
        "ss_return_plug": 0.18,
        # Module assembly, medium barrier; user's 2026-10-16 decision.
        "y1_plug": 2028, "y2_plug": 2032}

# AAOI uses the growth and mature return as references, not forced inputs.
SUPPORTED = frozenset({"300308.SZ", "AAOI.US", "VIAV.US"})
HISTORICAL_REFERENCES = ('300308.SZ', 'AAOI.US')


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f"{ticker}: pluggable-module machine snapshot not migrated for this consumer")
    for key in ("g2_pluggable", "ss_return_plug"):
        value = DATA[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{key} must be a finite ratio")
    if not 0 <= DATA["g2_pluggable"] < 1 or not 0 < DATA["ss_return_plug"] < 1:
        raise ValueError("pluggable-module ratios outside domain")
    for key in ("t_align", "y1_plug", "y2_plug"):
        if isinstance(DATA[key], bool) or not isinstance(DATA[key], int):
            raise ValueError(f"{key} must be a whole year")
    if DATA["y1_plug"] >= DATA["y2_plug"]:
        raise ValueError("pluggable-module path endpoints must increase")
    return {**DATA, 'axis_metadata': {'axis_id': 'pluggable-module', 'logical_id': '_AXIS.pluggable-module',
            'axis_type': 'peer_ruler_axis', 'role': 'reference', 'priced_mounts': [],
            'reference_mounts': sorted(set(HISTORICAL_REFERENCES) | set(SUPPORTED)),
            'historical_last_review_as_of': '2026-10-16', 'historical_consensus': None}}
