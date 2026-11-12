"""Shared aluminium spread scenarios from the historical research axis.

This module supplies assumptions, not a stock result or its confirmation.
The cross-axis copper constraint and each company's use of the one-year H
scenario require the consumers to bind and validate both axes explicitly.
"""

from decimal import Decimal, ROUND_HALF_UP
from math import isfinite

# SHFE smelting spread in CNY/tonne, not aluminium price. L: Morgan Stanley
# 2027 annual LME price 2,800 USD/t, research 2026-09-21. The historical
# price ratio 7.191 is SHFE CNY/t divided by LME USD/t; multiplying the LME
# price by this ratio translates it to about 20,135 CNY/t before costs.
# M: 2026H1 actual smelting spread, Goldman Sachs, paired with the 24,141
# CNY/t actual aluminium price quoted by BOCI on 2026-08-24. H: Citi's
# 2026-07-10 later-in-the-year range upper end 3,500 USD/t, translated on
# the same 7.191 ratio.
MID_ALUMINIUM_PRICE_CNY_PER_TONNE = 24_141

# Axis research froze the 2026H1 cost basket for all three scenarios, including
# alumina at 2,704 CNY/t and 1.92 tonnes per tonne of aluminium. The 10,070.32
# remainder is inferred from 15,262 − 2,704 × 1.92; it aggregates power,
# anodes and other costs and is not a separately observed cost line. An agent
# editing these inputs is changing the same shared cost basket for all tiers.
# The historical SHFE CNY/t divided by LME USD/t price ratio converts LME
# to approximate SHFE prices; it is not a standalone FX rate or HKD/CNY rate.
OTHER_COST_CNY_PER_TONNE = 10_070.32
ALUMINA_CNY_PER_TONNE = 2_704
ALUMINA_TONNES_PER_TONNE_ALUMINIUM = 1.92
LME_TO_SHFE_PRICE_RATIO = 7.191
LME_REFERENCE_USD_PER_TONNE = {"L": 2_800, "M": 3_357, "H": 3_500}

# Original axis research 2026-09-14: Antaike's 2025-01-04 material described
# domestic demand as entering its peak plateau; 2026-07 production was near
# the domestic cap. IAI/CRU's 2020–2030 global-demand growth of about 3.3%
# is a sensitivity reference, not the adopted growth for any tier; the
# original axis does not specify that report's publication date.
PERPETUAL_GROWTH = {"L": 0.0, "M": 0.0, "H": 0.0}
GLOBAL_DEMAND_REFERENCE_GROWTH = 0.033

# User decision recorded on 2026-10-16: H spread lasts one year, then the
# aluminium spread returns to M; L/M are sustained scenarios. This concerns
# the aluminium spread, not a separate claim about every other business.
H_DURATION_YEARS = 1
H_AFTER = "M"
H_SCOPE = "aluminium_spread"

# The original text declares the same Fed-path labels as the gold/copper
# axis, while its separate 2x2 illustration labels the 4,873 L construction
# as hold-rate + supply release. Both historical statements need review;
# do not silently infer a reconciliation or introduce a fourth anchor.
MACRO_PATH = {"L": "rate_hike", "M": "rate_hold", "H": "rate_cut_without_recession"}
L_DECOMPOSITION_REFERENCE = "rate_hold_with_supply_release"
SUPPLY_PATH = {"L": "supply_release", "M": "supply_not_released", "H": "capacity_delayed"}

# Roles come from the original axis §2; they describe alumina exposure, not
# additional earnings assumptions or guaranteed future production levels.
ALUMINA_ROLE = {
    "1378.HK": "net_producer",
    "601600.SH": "major_producer",
    "002532.SZ": "self_sufficient",
    "000933.SZ": "mainly_external_purchases",
}

# Required joint check: aluminium's H/M *price* ratio must be strictly less
# than copper's H/M price ratio from the separately declared gold/copper axis.
# Copper prices are intentionally not duplicated here. This module alone
# cannot enforce the relation: consuming models/runner must bind both axes.
COPPER_AXIS_ID = "fed-path-gold-copper"
CONSENSUS = "L-M"
UNITS = {"spread": "CNY_PER_METRIC_TONNE", "translated_price": "CNY_PER_METRIC_TONNE",
         "lme_reference": "USD_PER_METRIC_TONNE", "growth": "FRACTION",
         "h_pass_years": "YEARS", "cost_basket": "CNY_PER_METRIC_TONNE_ALUMINIUM",
         "alumina_price": "CNY_PER_METRIC_TONNE_ALUMINA",
         "alumina_tonnes_per_tonne_aluminium": "METRIC_TONNE_ALUMINA_PER_METRIC_TONNE_ALUMINIUM",
         # This is a cross-market price ratio, not a standalone FX quotation.
         "lme_to_shfe_price_ratio": "CNY_SHFE_PRICE_PER_USD_LME_PRICE"}


def _finite(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def inputs(ticker):
    """Return the historical shared assumptions for a named axis member."""
    if ticker not in ALUMINA_ROLE:
        raise ValueError(f"{ticker}: not an aluminium-axis member")
    for name, tiers in (("growth", PERPETUAL_GROWTH),
                        ("LME reference", LME_REFERENCE_USD_PER_TONNE)):
        if not isinstance(tiers, dict) or set(tiers) != {"L", "M", "H"} or any(not _finite(tiers[t]) for t in "LMH"):
            raise ValueError(f"aluminium {name} requires finite L/M/H values")
    growth = PERPETUAL_GROWTH
    if not 0 < LME_REFERENCE_USD_PER_TONNE["L"] < LME_REFERENCE_USD_PER_TONNE["M"] < LME_REFERENCE_USD_PER_TONNE["H"]:
        raise ValueError("aluminium LME reference prices must be positive and increasing")
    if not growth["L"] >= growth["M"] >= growth["H"]:
        raise ValueError("aluminium perpetual growth tiers must be flat or reverse")
    for name, paths in (("macro", MACRO_PATH), ("supply", SUPPLY_PATH)):
        if not isinstance(paths, dict) or set(paths) != {"L", "M", "H"} or any(not isinstance(paths[t], str) or not paths[t] for t in "LMH"):
            raise ValueError(f"aluminium {name} path requires L/M/H roles")
    if MACRO_PATH != {"L": "rate_hike", "M": "rate_hold", "H": "rate_cut_without_recession"}:
        raise ValueError("aluminium macro path must retain its declared tier mapping")
    if SUPPLY_PATH != {"L": "supply_release", "M": "supply_not_released", "H": "capacity_delayed"}:
        raise ValueError("aluminium supply path must retain its declared tier mapping")
    if not isinstance(COPPER_AXIS_ID, str) or not COPPER_AXIS_ID:
        raise ValueError("aluminium axis must declare the copper comparison axis")
    if any(not _finite(value) or value <= 0 for value in
           (MID_ALUMINIUM_PRICE_CNY_PER_TONNE, OTHER_COST_CNY_PER_TONNE, ALUMINA_CNY_PER_TONNE,
            ALUMINA_TONNES_PER_TONNE_ALUMINIUM, LME_TO_SHFE_PRICE_RATIO)):
        raise ValueError("aluminium cost and conversion inputs must be finite and positive")
    # Inferred convention to reproduce historical displayed whole-yuan values:
    # 2,800 × 7.191
    # − 15,262 = 4,872.8 → 4,873; 3,500 × 7.191 − 15,262 = 9,906.5 →
    # 9,907. Decimal half-up is intentional; Python's default ties-to-even
    # would change the historical H tier. The source does not establish how
    # the original author would round future values. M is the observed SHFE
    # price minus the same cost basket, not the rounded LME reference.
    ratio = Decimal(str(LME_TO_SHFE_PRICE_RATIO))
    cost = (Decimal(str(ALUMINA_CNY_PER_TONNE)) * Decimal(str(ALUMINA_TONNES_PER_TONNE_ALUMINIUM))
            + Decimal(str(OTHER_COST_CNY_PER_TONNE)))
    def amount(value):
        return int(value) if value == value.to_integral_value() else float(value)
    derived = {tier: int((Decimal(str(LME_REFERENCE_USD_PER_TONNE[tier])) * ratio - cost)
                         .to_integral_value(rounding=ROUND_HALF_UP)) for tier in ("L", "H")}
    cost_basket = amount(cost)
    spread = {"L": derived["L"], "M": amount(Decimal(str(MID_ALUMINIUM_PRICE_CNY_PER_TONNE)) - cost),
              "H": derived["H"]}
    if not all(_finite(value) for value in spread.values()) or not spread["L"] < spread["M"] < spread["H"]:
        raise ValueError("aluminium spreads must be finite and strictly increasing")
    if not _finite(GLOBAL_DEMAND_REFERENCE_GROWTH):
        raise ValueError("global demand reference must be finite")
    if (not _finite(H_DURATION_YEARS) or H_DURATION_YEARS <= 0
            or H_DURATION_YEARS % 1 or H_AFTER != "M" or H_SCOPE != "aluminium_spread"):
        raise ValueError("aluminium H duration, return tier or scope is invalid")
    prices = {tier: spread[tier] + cost_basket for tier in "LMH"}
    if any(price <= 0 for price in prices.values()):
        raise ValueError("translated aluminium prices must be positive")
    return {
        **{f"spread_{tier.lower()}": spread[tier] for tier in "LMH"},
        **{f"g2_{tier.lower()}": growth[tier] for tier in "LMH"},
        "translated_price": prices,
        "cost_basket": cost_basket,
        "alumina_price": ALUMINA_CNY_PER_TONNE,
        "alumina_tonnes_per_tonne_aluminium": ALUMINA_TONNES_PER_TONNE_ALUMINIUM,
        "lme_to_shfe_price_ratio": LME_TO_SHFE_PRICE_RATIO,
        "lme_reference": dict(LME_REFERENCE_USD_PER_TONNE),
        "h_pass_years": H_DURATION_YEARS,
        "h_after": H_AFTER,
        "h_scope": H_SCOPE,
        "macro_path": dict(MACRO_PATH),
        "l_decomposition_reference": L_DECOMPOSITION_REFERENCE,
        "supply_path": dict(SUPPLY_PATH),
        "alumina_role": ALUMINA_ROLE[ticker],
        "copper_axis_id": COPPER_AXIS_ID,
        "global_demand_reference_growth": GLOBAL_DEMAND_REFERENCE_GROWTH,
        "consensus": CONSENSUS,
        # The 2026-10-01 sell-side consensus is historical; the old L-tier
        # 2x2 interpretation remains separately disclosed, not reconciled.
        "axis_metadata": {"axis_id": "fed-path-aluminium", "logical_id": "_AXIS.fed-path-aluminium",
                          'title': '电解铝价差情景轴（利率路径 × 铝供应潮）', 'label': '电解铝价差', "axis_type": "shared_scenario_axis", "role": "priced",
                          "macro_path": dict(MACRO_PATH), "priced_mounts": list(ALUMINA_ROLE),
                          "reference_mounts": [],
                          "historical_consensus": {"band": CONSENSUS, "as_of": "2026-10-01"},
                          "historical_last_review_as_of": "2026-10-16"},
        "units": dict(UNITS),
    }
