"""Historical frontier-lab funding reference for two pilot consumers.

The old 2026-09-23 axis has no built CY2028 scenario ladder. That missing
ladder is not an estimate of zero and cannot be supplied by this module.
"""
from math import isfinite

# Shared arrival-risk haircut: original source hierarchy fell back to 0.30
# because actual private-company investment returns and retained-earnings
# allocation were unavailable; explicitly marked pending in axis §3b.
K_LAB = 0.30
SUPPORTED = frozenset({"ORCL.US", "SPCX.US", "AMZN.US", "MSFT.US", "GOOG.US", "AVGO.US"})


def axis_metadata():
    # The old axis has no scenario ladder and no consensus band. SPCX is a
    # reference member even though it does not use the common haircut.
    return {"axis_id": "frontier-lab-funding", "logical_id": "_AXIS.frontier-lab-funding",
            "title": "前沿实验室付款能力情景轴", "label": "前沿实验室付款能力",
            "axis_type": "shared_scenario_axis", "role": "reference",
            "priced_mounts": [], "reference_mounts": sorted(SUPPORTED),
            "historical_last_review_as_of": "2026-09-23", "historical_consensus": None}


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f"{ticker}: frontier funding snapshot not migrated for this consumer")
    if ticker == "SPCX.US":
        # The original SPCX research uses a single high-risk basket; the
        # shared dual-basket haircut is neither read nor applied to it.
        return {"scenario_rungs": None, "scenario_status": "unbuilt", "uses_shared_haircut": False,
                "axis_metadata": axis_metadata()}
    if isinstance(K_LAB, bool) or not isinstance(K_LAB, (int, float)) or not isfinite(K_LAB) or not 0 <= K_LAB < 1:
        raise ValueError("frontier-lab haircut must be a finite ratio in [0, 1)")
    return {"k_lab": K_LAB, "scenario_rungs": None, "scenario_status": "unbuilt",
            "haircut_evidence_status": "pending", "uses_shared_haircut": True,
            "axis_metadata": axis_metadata()}
