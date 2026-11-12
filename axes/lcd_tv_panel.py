"""Shared LCD panel scenarios: frozen historical inputs, not live prices.

The original axis explicitly has no price-to-profit bridge. Consumers use
their own earnings inputs; these shared prices name scenarios and constrain
their interpretation, while the rate and equipment lives affect calculations.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from math import isfinite


DATA = {
    "members": {"000725.SZ": "company", "000100.SZ": "display"},
    # M consensus: Citi 2027 supply/demand balance (2026-07-08), BofA stable
    # near-term prices (2026-05-20), and TCL management's stable-price view.
    "axis_metadata": {"axis_id": "lcd-tv-panel", "logical_id": "_AXIS.lcd-tv-panel",
                      'title': 'LCD 电视面板价格情景轴（控产格局下的面板价位 + 面板腿折现率）', 'label': 'LCD 电视面板价格', "axis_type": "shared_scenario_axis", "historical_last_review_as_of": "2026-10-26",
                      "currency": "USD", "unit": "per_panel",
                      "historical_consensus": {"band": "M", "as_of": "2026-10-23"},
                      "consensus_source_ids": ["CITI_95175_2026-07-08", "BOFA_89372_2026-05-20", "TCL_IR_2026-005"]},
    "regimes": {"L": "supply_control_fails", "M": "stable", "H": "price_increase"},
    # These observations require research, not automatic re-pricing. A named
    # 2027 forecast updates H and M if it differs from spot by more than 3%;
    # fluctuations at or below 3% alone do not reset the price ladder.
    "observation_rules": {"reassess_discount_after_months": 12,
                          "discount_reassessment": "either_member_below_reference_m",
                          "named_2027_forecast_updates_high": True,
                          "new_forecast_reassess_mid_threshold": 0.03,
                          "monthly_fluctuation_no_reset_threshold": 0.03,
                          "full_production_revisit": True,
                          "breach_action": "revisit_historical_profit"},
    # User's 2026-10-23 shared panel decision: risk classification is basket 6,
    # but the actual discount rate borrows basket 5; 13% is comparison only.
    "discount_rate": 0.11,
    "reference_rate": 0.13,
    # 2026-10-26 life decision: L is supported by BOE Beijing Gen-8.5 and
    # TCL CSOT t1/t10, in operation about 15 years; TCL 2025 science and
    # technology bond prospectus and 2025 environmental disclosures. H uses
    # BOE Beijing Gen-5 (2005 commissioning, original source still to verify),
    # operating in 2025 per BOE IR 2025-009. M is the L/H midpoint.
    "equipment_life": {"L": 15.0, "M": 17.5, "H": 20.0},
    # TrendForce/WitsView USD per Open Cell panel: 55/65 inch 4K 60 Hz.
    # L September 2022, M October 2026 (TrendForce 2026-10-20), H April–June
    # 2026. H is a historical high, not a sell-side forecast. BofA/WitsView's
    # 65 inch 4K 120 Hz is a different product and must not be substituted.
    "prices": {"55": {"L": 80.0, "M": 123.0, "H": 126.0},
               "65": {"L": 106.0, "M": 173.0, "H": 177.0}},
    # 43 inch FHD / 32 inch HD are proportional references, with no H supplied;
    # 43 inch 4K quotations are not comparable to this FHD series.
    "reference_prices": {"43": {"L": 47.0, "M": 63.0},
                         "32": {"L": 26.0, "M": 35.0}},
    # 55-inch trigger is 50% below the historical 2026 average; 65-inch
    # equivalent is 87. Share data are unit shipments, not revenue share.
    "trigger": {"price_55": 62.0, "price_65": 87.0,
                "share_floor": 0.70, "observed_share_2026_h1": 0.724},
    "profit_bridge_built": False,
}


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"invalid {label}")
    return float(value)


def _ladder(values: object, label: str) -> None:
    if not isinstance(values, dict) or set(values) != {"L", "M", "H"}:
        raise ValueError(f"invalid {label} tiers")
    low, mid, high = (_number(values[tier], label) for tier in ("L", "M", "H"))
    if not low < mid < high:
        raise ValueError(f"invalid {label} ordering")


def inputs(ticker: str, *, data: dict = DATA) -> dict:
    """Supply a separate validated snapshot to each declared member."""
    try:
        scope = data["members"][ticker]
        if scope not in ("company", "display"):
            raise ValueError("invalid panel business scope")
        metadata = data["axis_metadata"]
        if (not isinstance(metadata["axis_id"], str) or not metadata["axis_id"]
                or metadata["logical_id"] != f"_AXIS.{metadata['axis_id']}"
                or metadata["axis_type"] != "shared_scenario_axis" or metadata["currency"] != "USD"
                or metadata["unit"] != "per_panel"):
            raise ValueError("invalid panel axis metadata")
        as_of = date.fromisoformat(metadata["historical_last_review_as_of"])
        consensus = metadata["historical_consensus"]
        if consensus["band"] != "M" or date.fromisoformat(consensus["as_of"]) > as_of:
            raise ValueError("invalid historical panel consensus")
        if data["regimes"] != {"L": "supply_control_fails", "M": "stable", "H": "price_increase"}:
            raise ValueError("panel scenario roles do not match their tiers")
        rules = data["observation_rules"]
        months = rules["reassess_discount_after_months"]
        if (isinstance(months, bool) or not isinstance(months, int) or months <= 0
                or rules["discount_reassessment"] != "either_member_below_reference_m"
                or rules["named_2027_forecast_updates_high"] is not True
                or _number(rules["new_forecast_reassess_mid_threshold"], "forecast threshold") >= 1
                or _number(rules["monthly_fluctuation_no_reset_threshold"], "monthly threshold") >= 1
                or rules["full_production_revisit"] is not True
                or rules["breach_action"] != "revisit_historical_profit"):
            raise ValueError("invalid panel observation rules")
        rate = _number(data["discount_rate"], "discount rate")
        reference = _number(data["reference_rate"], "reference rate")
        if rate >= 1 or reference >= 1:
            raise ValueError("invalid panel discount rate")
        _ladder(data["equipment_life"], "equipment life")
        if set(data["prices"]) != {"55", "65"}:
            raise ValueError("missing panel price series")
        for size, prices in data["prices"].items():
            _ladder(prices, f"{size}-inch price")
        references = data["reference_prices"]
        if set(references) != {"43", "32"}:
            raise ValueError("missing panel reference price series")
        for size, prices in references.items():
            if not {"L", "M"}.issubset(prices):
                raise ValueError(f"missing {size}-inch reference prices")
            for tier, price in prices.items():
                if tier not in ("L", "M", "H"):
                    raise ValueError(f"invalid {size}-inch reference tier")
                _number(price, f"{size}-inch {tier} reference price")
        trigger = data["trigger"]
        _number(trigger["price_55"], "55-inch trigger")
        _number(trigger["price_65"], "65-inch trigger")
        floor = _number(trigger["share_floor"], "share floor")
        observed = _number(trigger["observed_share_2026_h1"], "observed market share")
        if floor > 1 or observed > 1 or data["profit_bridge_built"] is not False:
            raise ValueError("invalid panel trigger or unbuilt profit bridge")
        result = {key: deepcopy(value) for key, value in data.items() if key != "members"}
        result["axis_metadata"]["priced_mounts"] = list(data["members"])
        result["axis_metadata"]["reference_mounts"] = []
        result["axis_metadata"]["role"] = "priced"
        result["scope"] = scope
        rate_key = "r_perp" if scope == "company" else "r_display"
        result["stock_fields"] = {
            rate_key: rate,
            f"{rate_key}_ref": reference,
            **{f"life_{tier.lower()}": data["equipment_life"][tier] for tier in ("L", "M", "H")},
        }
        return result
    except (KeyError, TypeError) as exc:
        raise ValueError(f"missing panel inputs for {ticker}") from exc
