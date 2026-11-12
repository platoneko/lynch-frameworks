"""Partial historical direct-to-cell peer ruler for SPCX only."""
from math import isfinite

# Monthly wholesale USD per user. L $0.50 is the upper edge of an industry
# analyst's "tens of cents" estimate (TMF, 2026-07-27). M $1.50 comes from
# Bank of America on AST's 50/50 share (single house, 2025-06-25). H $5 is
# T-Satellite's $10 retail price multiplied by 50% (2026-10-05); it is not an
# independent SpaceX price or a claim that SpaceX retains 100% of retail.
# Full-scale EBIT margin 53.6% is a single-house Bank of America 2030 AST
# estimate, not an observed SpaceX margin. Its depreciation reflects AST's
# own constellation; SpaceX's prospectus says satellites last 3-5 years, so
# shorter lives than AST would bias this proxy high. Axis alignment is FY2030.
DATA = {"d2c_px_l": 0.5, "d2c_px_m": 1.5, "d2c_px_h": 5.0,
        "d2c_margin": 0.536, "t_align": 2030}
SUPPORTED = frozenset({"SPCX.US"})


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f"{ticker}: direct-to-cell axis not migrated for this consumer")
    values = [DATA[key] for key in ("d2c_px_l", "d2c_px_m", "d2c_px_h", "d2c_margin")]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError("direct-to-cell values must be finite numbers")
    if not 0 < DATA["d2c_px_l"] < DATA["d2c_px_m"] < DATA["d2c_px_h"] or not 0 < DATA["d2c_margin"] < 1:
        raise ValueError("direct-to-cell price ladder or margin invalid")
    if isinstance(DATA["t_align"], bool) or not isinstance(DATA["t_align"], int):
        raise ValueError("direct-to-cell alignment must be a whole year")
    return {**DATA, 'axis_metadata': {
        'axis_id': 'direct-to-cell', 'logical_id': '_AXIS.direct-to-cell',
        'title': '手机直连卫星（direct-to-cell / D2D）同业尺轴', 'label': '手机直连卫星',
        'axis_type': 'peer_ruler_axis', 'role': 'reference',
        'priced_mounts': [], 'reference_mounts': ['SPCX.US'],
        'historical_last_review_as_of': '2026-10-05', 'historical_consensus': None}}
