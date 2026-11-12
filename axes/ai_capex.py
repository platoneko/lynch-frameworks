"""Partial machine snapshot of the historical AI-capex axis for two pilots.

Source is the user's current `axes/ai-capex.md`, including its uncommitted
2026-10-21 SpaceX section. The old document remains in use until the complete
axis/consumer switch; this is not a claim that all axis mounts are migrated.
"""
from math import isfinite

# CY2027 top-five hyperscaler total capex, USD, derived from an approximate
# common 2026 $800bn base. Original forecasts use different populations:
# Goldman hyperscalers (+32%, 2026-08-21, Wisburg 102304); JPM top-four US
# data-center capex (+50%, 2026-05-27, Wisburg 90090); NVIDIA CFO top-five
# total capex $1.30tn (2026-08-27, Wisburg 102970). They are not identical
# scopes; the old axis explicitly calls this approximation out.
RUNGS_USD = {"L": 1.06e12, "M": 1.20e12, "H": 1.30e12}
# NVIDIA CFO's approximate CY2026 $800bn top-five baseline; ORCL is a
# constituent and its own guidance is compared with this pool, not added to it.
BASE_2026_USD = 8.0e11

# User decisions on high-return path, 2026-10-16; the 20% packaging fallback
# was provisionally selected on 2026-10-19, subject to mature peer evidence.
PATHS = {"y1_ai_capex": 2030, "y2_ai_capex": 2035,
         "y1_ai_capex_package": 2030, "y2_ai_capex_package": 2035,
         "ss_floor_ai_capex_package": 0.20,
         "y1_ai_capex_engine": 2030, "y2_ai_capex_engine": 2035}

# SpaceX is explicitly outside the top-five pool, not a component to add to
# its rungs. 2026-10-20 Q3 8-K/call: 2026 company capex approx $85bn;
# 9M $48.07bn of which AI $40bn; Q4 guidance $35-40bn; 9/30 installed 1.7GW,
# year-end 2.5-3GW; management expects ~10GW more in 2027. A mechanical
# ~$33bn/GW proxy gives ~$330bn AI capex, while Morgan Stanley/Deutsche Bank
# August company-wide estimates were $163-200bn. These are unlike scopes and
# are not company guidance. 9M operating cash $13.1bn vs capex $48.1bn,
# funded by IPO $85.7bn and debt $51.8bn; 9/30 net cash ~$51bn. The shared
# source does not establish either pilot's customer revenue share; do not
# invent one or claim that a stock-specific disclosure does not exist.
SPACEX_OUTSIDE_POOL = {
    "disclosure_as_of": "2026-10-20", "seller_reference_as_of": "2026-08",
    "self_consumed_fraction": 0.5, "third_party_rental_fraction": 0.5,
    "rental_refundable_days": 90, "pilot_customer_revenue_split_disclosed": None,
    "capex_2026_usd_bn_approx": 85.0, "capex_9m_usd_bn": 48.07,
    "ai_capex_9m_usd_bn": 40.0, "q4_guidance_usd_bn": (35.0, 40.0),
    "installed_gw_2026_09_30": 1.7, "year_end_installed_gw": (2.5, 3.0),
    "additional_gw_2027_management_approx": 10.0,
    "cost_per_gw_usd_bn_approx": 33.0,
    "capex_2027_proxy_usd_bn_approx": 330.0,
    "capex_2027_seller_usd_bn": (163.0, 200.0),
    "cash_flow_9m_usd_bn": 13.1, "capex_cash_9m_usd_bn": 48.1,
    "ipo_usd_bn": 85.7, "new_debt_usd_bn": 51.8,
    "net_cash_2026_09_30_usd_bn_approx": 51.0,
}

ROLES = {"GOOG.US": "constituent", "GLW.US": "demand_reference", "300308.SZ": "demand_reference", "AEHR.US": "demand_reference",
         "ORCL.US": "constituent", "META.US": "constituent", "TER.US": "demand_reference",
         "AMZN.US": "constituent", "MSFT.US": "constituent", "VIAV.US": "demand_reference",
         "COHR.US": "demand_reference",
         "2631.HK": "path_reference", "WOLF.US": "path_reference"}
# The old human axis recorded these reference relationships. Some members do
# not yet have a numeric adapter; listing them does not execute their models.
HISTORICAL_REFERENCES = ('COHR.US', 'GLW.US', 'LITE.US', 'AEHR.US', '300308.SZ',
                         'CRDO.US', 'VIAV.US', 'FN.US', 'GOOG.US', 'ORCL.US',
                         'META.US', 'MSFT.US', 'AMZN.US')


def inputs(ticker):
    if ticker not in ROLES:
        raise ValueError(f"{ticker}: AI-capex machine snapshot not migrated for this consumer")
    if set(RUNGS_USD) != {"L", "M", "H"}:
        raise ValueError("AI-capex rungs must contain L, M and H")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) for x in RUNGS_USD.values()):
        raise ValueError("AI-capex rungs must be finite numbers")
    if not 0 < RUNGS_USD["L"] < RUNGS_USD["M"] < RUNGS_USD["H"]:
        raise ValueError("AI-capex rungs must be positive and increasing")
    if isinstance(BASE_2026_USD, bool) or not isinstance(BASE_2026_USD, (int, float)) or not isfinite(BASE_2026_USD) or BASE_2026_USD <= 0:
        raise ValueError("AI-capex base must be positive and finite")
    if not 0 < PATHS["ss_floor_ai_capex_package"] < 1:
        raise ValueError("packaging fallback return must be a ratio")
    for start, end in (("y1_ai_capex", "y2_ai_capex"),
                       ("y1_ai_capex_package", "y2_ai_capex_package"),
                       ("y1_ai_capex_engine", "y2_ai_capex_engine")):
        if any(isinstance(PATHS[key], bool) or not isinstance(PATHS[key], int) for key in (start, end)):
            raise ValueError("AI-capex path dates must be whole years")
        if PATHS[start] >= PATHS[end]:
            raise ValueError("AI-capex path endpoints must increase")
    return {"rungs": dict(RUNGS_USD), "base_2026_usd": BASE_2026_USD, "role": ROLES[ticker], **PATHS,
            "spacex_outside_pool": dict(SPACEX_OUTSIDE_POOL),
            "axis_metadata": {"axis_id": "ai-capex", "logical_id": "_AXIS.ai-capex",
                              'title': 'AI 资本开支情景轴', 'label': 'AI 资本开支', "axis_type": "shared_scenario_axis", "role": "reference",
                              "priced_mounts": [],
                              "reference_mounts": sorted(set(HISTORICAL_REFERENCES) | set(ROLES)),
                              "historical_last_review_as_of": "2026-10-21",
                              "historical_consensus": {"band": "L-M", "as_of": "2026-09-25"}}}
