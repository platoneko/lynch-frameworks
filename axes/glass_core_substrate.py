"""Glass-core peer ruler: historical shared inputs, not a revenue forecast.

The proxy unit price extrapolates an external company's target and capacity;
the actual company-specific volume and capex remain individual stock inputs.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from math import isfinite


DATA = {
    "references": ["000725.SZ"],
    "axis_metadata": {"axis_id": "glass-core-substrate", "logical_id": "_AXIS.glass-core-substrate",
                      "axis_type": "peer_ruler_axis", "historical_last_review_as_of": "2026-10-16"},
    "stock_fields": {
        # Absolics 2030 revenue target and phase 1+2 capacity, reported by
        # Meritz / Eugene Investment on 2024-10-14; target is not realized sales.
        "gcs_abs_rev_usd": 1.61e9, "gcs_abs_cap_m2": 7.2e4,
        # 510 × 515 mm. The old research adopted $5,874 per panel, but its
        # displayed target/capacity/area values imply $5,873.145833...; the
        # $0.854167 difference is unexplained precision, not ordinary rounding.
        # Preserve the adopted price. Changed upstream values require a human
        # to revise or validate it if the historical ±$1 tolerance is exceeded.
        "gcs_panel_m2": .26265, "gcs_price_h_usd": 5874.0,
        # Adjacent ABF margin proxies: 景硕 2022–25 average 9.2%, and 揖斐电
        # electronics FY2025 18.6% (yfinance 2026-10-05 / quartr FY2025 summary).
        # The 3 pp entrant deduction is a judgment; yield and certification
        # remain unproven, not a measured glass-core margin.
        "gcs_opm_weak": .092, "gcs_opm_strong": .186, "gcs_yield_disc": .03,
        # 2026-09-30 same-r cross section: 深南电路 gives 11.37%; only one
        # non-pure-business sample survives (兴森科技 excluded as peak-shaped).
        # This reference growth is subsequently capped by the model.
        "g2_gcs_src": .1137,
    },
    "t_align": 2028, "ss_return_cap_gcs": .30, "fall_years_gcs": 6,
}


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"invalid glass axis {label}")
    return float(value)


def inputs(ticker: str, *, data: dict = DATA) -> dict:
    """Return reference-only inputs; no actual stock value is synthesized."""
    try:
        if ticker not in data["references"]:
            raise ValueError(f"not a glass axis reference: {ticker}")
        meta = data["axis_metadata"]
        if (meta["axis_type"] != "peer_ruler_axis" or not meta["axis_id"]
                or meta["logical_id"] != f"_AXIS.{meta['axis_id']}"):
            raise ValueError("invalid glass axis metadata")
        date.fromisoformat(meta["historical_last_review_as_of"])
        fields = data["stock_fields"]
        expected = {"gcs_abs_rev_usd", "gcs_abs_cap_m2", "gcs_panel_m2", "gcs_price_h_usd",
                    "gcs_opm_weak", "gcs_opm_strong", "gcs_yield_disc", "g2_gcs_src"}
        if set(fields) != expected:
            raise ValueError("invalid glass axis fields")
        values = {key: _positive(value, key) for key, value in fields.items()}
        proxy = values["gcs_abs_rev_usd"] / values["gcs_abs_cap_m2"] * values["gcs_panel_m2"]
        if (not isfinite(proxy) or abs(proxy - values["gcs_price_h_usd"]) > 1.0
                or not 0 < values["gcs_opm_weak"] < values["gcs_opm_strong"] < 1
                or values["gcs_yield_disc"] >= values["gcs_opm_strong"]):
            raise ValueError("glass axis proxy or margins inconsistent")
        for name in ("t_align", "fall_years_gcs"):
            value = data[name]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"invalid glass axis {name}")
        if not 0 < _positive(data["ss_return_cap_gcs"], "steady return cap") <= 1:
            raise ValueError("invalid glass steady return cap")
        result = deepcopy(data)
        result["price_proxy"] = {"derived": proxy, "adopted": values["gcs_price_h_usd"],
                                 "difference": values["gcs_price_h_usd"] - proxy,
                                 "tolerance": 1.0}
        result["axis_metadata"]["role"] = "reference"
        result["axis_metadata"]["priced_mounts"] = []
        result["axis_metadata"]["reference_mounts"] = list(data["references"])
        result["axis_metadata"]["historical_consensus"] = None
        return result
    except (KeyError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f"missing glass axis inputs for {ticker}") from exc
