"""Rates-axis pilot: data as recorded on 2026-09-25, not live rates.

Pass ``load_segment`` explicitly to a pilot consumer.  The existing Markdown
consumer remains in place until the complete migration; this module alone is
the machine source for the pilot and does not set any valuation anchors.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from math import isfinite
import re
from statistics import median


DATA = {
    "USD": {
        "status": "built",
        "currency": "USD",
        "as_of": "2026-09-25",
        # Long-term baseline is valuation-rules' plan A, not today's yield.
        "rf_mid": "4.00%",
        # Trading Economics: 2026-09-24 close of the UST 10Y.
        "rf_now": "5.12%",
        "current_source": {"reference": "Trading Economics", "date": "2026-09-24", "currency": "USD"},
        # Median of the two 2027 year-end sell-side points; thin sample, three
        # months later than the intended 12-month horizon, with a known
        # downward bias described in rates.md.  No financial refresh here.
        "consensus_horizon": "2027 年末",
        "horizon_reason": "距 as-of 约 15 个月，最接近已发布点；比 12 个月长，方向偏低",
        "sources": [
            {"reference": "Wisburg 106928", "institution": "美银", "date": "2026-09-24", "forecast": "4.75%", "horizon": "2027 年末", "currency": "USD"},
            {"reference": "Wisburg 103858", "institution": "汇丰", "date": "2026-09-03", "forecast": "4.75%", "horizon": "2027 年末", "currency": "USD"},
        ],
        "rf_step": "50bp",
        "rf_cap": "50bp",
    },
    # Listing currency relationship, not an exchange rate or FX conversion.
    "HKD": {"status": "linked", "linked_to": "USD"},
    # Only the plan-A CNY baseline exists; no sensitivity segment is built.
    "CNY": {"status": "unbuilt", "rf_mid": "2.50%"},
    "TWD": {"status": "unbuilt", "rf_mid": None},
}


def _rate(value: str, unit: str) -> float:
    """Explicit percent/basis-point labels disambiguate display and decimal units."""
    if not isinstance(value, str) or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)" + re.escape(unit), value):
        raise ValueError(f"rate requires explicit {unit} unit")
    exact = Decimal(value[:-len(unit)]) / (100 if unit == "%" else 10000)
    number = float(exact)
    if not isfinite(number) or (exact != 0 and number == 0):
        raise ValueError("rate cannot be represented as a finite float")
    return number


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_segment(ccy: str, *, data: dict = DATA) -> dict[str, float]:
    """Return validated sensitivity inputs in decimal units; fail closed."""
    if ccy not in data:
        raise ValueError(f"rates axis has no {ccy} segment")
    if ccy == "HKD":
        if data[ccy] != {"status": "linked", "linked_to": "USD"}:
            raise ValueError("rates axis HKD link is invalid")
        ccy = "USD"
    try:
        segment = data[ccy]
        if segment["status"] != "built" or ccy != "USD":
            raise ValueError(f"rates axis {ccy} segment not built")
        if segment["currency"] != ccy:
            raise ValueError("segment currency mismatch")
        values = {key: _rate(segment[key], "%") for key in ("rf_mid", "rf_now")}
        values.update({key: _rate(segment[key], "bp") for key in ("rf_step", "rf_cap")})
        if values["rf_step"] not in (0.0025, 0.005) or values["rf_cap"] <= 0:
            raise ValueError("step must be 25bp or 50bp; cap must be positive")
        as_of = date.fromisoformat(segment["as_of"])
        current = segment["current_source"]
        if not _has_text(current["reference"]) or current["currency"] != ccy or date.fromisoformat(current["date"]) > as_of:
            raise ValueError("invalid current source currency or date")
        horizon = segment["consensus_horizon"]
        if not _has_text(horizon) or not _has_text(segment["horizon_reason"]):
            raise ValueError("missing consensus horizon or reason")
        if not segment["sources"]:
            raise ValueError("missing consensus sources")
        forecasts = []
        for source in segment["sources"]:
            if (not _has_text(source["reference"]) or not _has_text(source["institution"])
                    or not _has_text(source["horizon"]) or source["horizon"] != horizon):
                raise ValueError("incomplete consensus source")
            if source["currency"] != ccy or date.fromisoformat(source["date"]) > as_of:
                raise ValueError("invalid consensus source currency or date")
            forecasts.append(_rate(source["forecast"], "%"))
        values["rf_cons"] = median(forecasts)
        # Δ is a derivation, not another editable copy of the same fact.
        values["delta_cons"] = float(Decimal(str(values["rf_cons"])) - Decimal(str(values["rf_mid"])))
        if not isfinite(values["rf_cons"]) or not isfinite(values["delta_cons"]):
            raise ValueError("non-finite consensus or difference")
        return values
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid or unbuilt rates axis {ccy}: {exc}") from exc


def inputs(ticker: str, *, currencies=None) -> dict:
    """Return the currency segments, not a ticker-to-currency guess."""
    if currencies == ('CNY',) or currencies == ['CNY']:
        cny = DATA['CNY']
        return {'segments': {'CNY': {**cny, 'baseline': (None if cny.get('rf_mid') is None
                                                         else _rate(cny['rf_mid'], '%'))}}}
    if currencies is not None:
        raise ValueError('unsupported requested rates segments')
    return {
        "as_of": DATA["USD"]["as_of"],
        "provenance": {
            "current_source": dict(DATA["USD"]["current_source"]),
            "consensus_horizon": DATA["USD"]["consensus_horizon"],
            "horizon_reason": DATA["USD"]["horizon_reason"],
            "sources": [dict(source) for source in DATA["USD"]["sources"]],
        },
        "segments": {
            "USD": {"status": "built", "values": load_segment("USD")},
            "HKD": {"status": "linked", "linked_to": "USD", "values": load_segment("HKD")},
            # The long-run CNY baseline exists independently of its unbuilt
            # current / consensus sensitivity segment; expose a numeric
            # derived value while retaining the original segment status.
            "CNY": {**DATA["CNY"], "baseline": (None if DATA["CNY"].get("rf_mid") is None
                                                  else _rate(DATA["CNY"]["rf_mid"], "%"))},
            "TWD": dict(DATA["TWD"]),
        },
    }
