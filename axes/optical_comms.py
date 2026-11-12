"""Historical 2028 optical-engine shipments for declared consumers."""
from math import isfinite

# Effective delivered optical engines, not nominal PIC dies: L borrows Morgan
# Stanley 2027 7.78m for a one-year delay (Wisburg 95433, 2026-07-10).
# The delay mechanism separately cites Jefferies on 2026-09-25;
# M Guangfa 2028 NPO 40m excludes scale-out CPO (2026-08-19);
# H Morgan Stanley 2028 48.6m (Wisburg 95433, 2026-07-10).
# M's omission and L's borrowed-year proxy remain visible limitations.
OE_UNITS = {"L": 7.78e6, "M": 4.0e7, "H": 4.86e7}
# Goldman Quantum-X optical-engine terminal BOM reference, $450 per engine;
# this is not a forecast of a given company's revenue or a 100% allocation.
OE_BOM_USD = 450.0
# NOK uses the same quantities as a direction reference, never as a direct
# revenue input. 300308 uses them for an explicit potential-value scenario.
SUPPORTED = frozenset({"300308.SZ", "NOK.US", "COHR.US", "AVGO.US", "TSM.US"})
HISTORICAL_REFERENCES = ('NOK.US', 'LITE.US', 'COHR.US', 'AVGO.US', 'TSM.US', '300308.SZ')


def inputs(ticker):
    if ticker not in SUPPORTED:
        raise ValueError(f"{ticker}: optical-comms machine snapshot not migrated for this consumer")
    if set(OE_UNITS) != {"L", "M", "H"}:
        raise ValueError("optical-engine rungs must contain L, M and H")
    values = [*OE_UNITS.values(), OE_BOM_USD]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) for x in values):
        raise ValueError("optical-engine inputs must be finite")
    if not 0 < OE_UNITS["L"] < OE_UNITS["M"] < OE_UNITS["H"] or OE_BOM_USD <= 0:
        raise ValueError("optical-engine inputs must be positive and ordered")
    return {"oe": dict(OE_UNITS), "oe_bom_usd": OE_BOM_USD,
            "axis_metadata": {"axis_id": "optical-comms", "logical_id": "_AXIS.optical-comms",
                              'title': '光通信 / CPO·NPO 光引擎出货情景轴', 'label': '光通信光引擎出货', "axis_type": "shared_scenario_axis", "role": "reference",
                              "priced_mounts": [],
                              "reference_mounts": sorted(set(HISTORICAL_REFERENCES) | set(SUPPORTED)),
                              "historical_last_review_as_of": "2026-10-02",
                              "historical_consensus": {"band": "M", "as_of": "2026-09-29"}}}
