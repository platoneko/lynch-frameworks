"""Shared old peer readings; this is not a silicon-photonics axis input."""
from math import isfinite

# The old studies used the same mature-foundry peer reading (2.48%) and
# path-adjusted re-solve (3.1265%); the peer sample includes advanced nodes,
# so the source itself flags it as imperfect and needing replacement.
DATA = {'g2_rest': 0.031265, 'g2_rest_src': 0.0248}

def inputs(ticker):
    if ticker not in ('GFS.US', 'TSEM.US', 'INTC.US'):
        raise ValueError('foundry peer consumer not migrated')
    if any(not isfinite(v) for v in DATA.values()):
        raise ValueError('foundry peer inputs must be finite')
    return dict(DATA)
