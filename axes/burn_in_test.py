"""Historical burn-in / SLT peer ruler for AEHR; partial pilot interface."""
from math import isfinite
from statistics import median

# Five-member 2026-10-02 peer median; cap only when a stock applies its own r.
# Weak: Cohu 2021 peak non-GAAP margin (2022-02-10). Strong: Advantest Test
# System FY2025 margin (2026-05, secondary report; primary filing not checked).
DATA = {"g2_bit_src": 0.0779, "bit_opm_weak": 0.205, "bit_opm_strong": 0.509,
        "t_align": 2028,
        # User 2026-10-19: changed business, no mature same-business peers.
        # 38.45% prior TER/FORM midpoint is a contrast, not the adopted value.
        "ss_return_cap_bit": 0.30, "ss_return_bit_ref": 0.3845,
        # Packaging / optical test, high barrier, user 2026-10-16.
        "y1_bit": 2030, "y2_bit": 2035}
SUPPORTED = frozenset({"AEHR.US", "TER.US"})

# 2026-10-02 same-ruler peer growth rates, excluding TER itself; the median
# of these four is 7.525%, while AEHR's five-peer median above is 7.79%.
TER_PEER_GROWTH = {"6857.T": .0788, "2449.TW": .0609, "2360.TW": .0717, "FORM.US": .0824}


def axis_metadata(ticker):
    # The historical header mounts AEHR; TER is a candidate/source, even
    # though TER now consumes the peer median as a separate reference.
    return {'axis_id': 'burn-in-test', 'logical_id': '_AXIS.burn-in-test',
            'title': '老化 / 可靠性测试与系统级测试（SLT）同业尺轴', 'label': '老化与可靠性测试',
            'axis_type': 'peer_ruler_axis',
            'role': 'reference' if ticker == 'AEHR.US' else 'candidate_provider',
            'priced_mounts': [], 'reference_mounts': ['AEHR.US'], 'candidate_providers': ['TER.US'],
            'historical_last_review_as_of': '2026-11-04', 'historical_consensus': None}


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f"{ticker}: burn-in machine snapshot not migrated for this consumer")
    if ticker == "TER.US":
        values = tuple(TER_PEER_GROWTH.values())
        if len(values) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                   or not isfinite(x) for x in values):
            raise ValueError("TER peer growth data must contain four finite values")
        return {"role": "peer_reference", "g_peer_median": median(values), "axis_metadata": axis_metadata(ticker)}
    ratios = ("g2_bit_src", "bit_opm_weak", "bit_opm_strong", "ss_return_cap_bit", "ss_return_bit_ref")
    if any(isinstance(DATA[key], bool) or not isinstance(DATA[key], (int, float))
           or not isfinite(DATA[key]) for key in ratios):
        raise ValueError("burn-in ratios must be finite")
    if not 0 <= DATA["g2_bit_src"] < 1 or not 0 < DATA["bit_opm_weak"] < DATA["bit_opm_strong"] < 1:
        raise ValueError("burn-in growth or peer margin domain invalid")
    if not 0 < DATA["ss_return_cap_bit"] < 1 or not 0 < DATA["ss_return_bit_ref"] < 1:
        raise ValueError("burn-in return reference outside domain")
    for key in ("t_align", "y1_bit", "y2_bit"):
        if isinstance(DATA[key], bool) or not isinstance(DATA[key], int):
            raise ValueError(f"{key} must be a whole year")
    if DATA["y1_bit"] >= DATA["y2_bit"]:
        raise ValueError("burn-in path endpoints must increase")
    return {**DATA, 'axis_metadata': axis_metadata(ticker)}
