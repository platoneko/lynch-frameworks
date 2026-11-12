#!/usr/bin/env python3
"""PYPL historical conditional cash valuation; calculation is not publication.

formula_id: pypl_conditional_equity_cash_dcf_v1
Amounts are USD billions, shares billions, EPS and output USD/share; rates are ratios.
The 2026-11-05 model remains conditional on cash, reinvestment and historical
multiple gaps disclosed in the accompanying document. No newer data is implied.
"""
from __future__ import annotations

import math
from lib.gordon import check_g_cap, check_r
from lib.inputs import ladder
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis', 'rf_report'), 'axes': {}}

# FY2025 10-K cash flow: https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm
# 2026Q3 10-Q cash flow: https://www.sec.gov/Archives/edgar/data/1633917/000163391726000088/pypl-20260930.htm
# All outflows are positive. FY2025 + 9M2026 - 9M2025 yields trailing cash;
# held-loan purchases less repayments/sales are deducted once, not assumed released.
# The adopted conditional reading assumes these historical deductions support
# each growth scenario; future additional funding and its timing remain unknown.
# The 2026Q3 10-Q reports approximately $1.5bn of Japanese loans reclassified
# as held for sale, not cash already recovered; external funding targets are
# not guaranteed. Neither item is an extra release in the model.
HISTORICAL_PARTIAL_FINGERPRINT = '7fb57c94c2a90db31c6a5fb408598eeeb5f800553e1060707bdb2f3e9170ddcf'

INPUTS = {
    "cfo25": 6.416, "capex25": 0.852, "sbc25": 1.002,  # FY2025
    "cfo9m26": 4.709, "capex9m26": 0.600, "sbc9m26": 0.767,  # 2026-09-30
    "cfo9m25": 4.032, "capex9m25": 0.658, "sbc9m25": 0.792,  # 2025-09-30
    "loan_out25": 20.190, "loan_in25": 19.688,  # FY2025
    "loan_out9m26": 12.322, "loan_in9m26": 11.662,  # 2026-09-30
    "loan_out9m25": 15.904, "loan_in9m25": 15.945,  # 2025-09-30
    # Longbridge consensus, accessed 2026-11-05: adjusted net income, after tax,
    # 2026H1 actual versus 2027H1 forecast. Annual cash scaling is a model proxy.
    "ni1q26": 1.234, "ni2q26": 1.219,
    "ni1q27": 1.176744320, "ni2q27": 1.189544340,
    # Yahoo 2027 adjusted EPS consensus, 43 analysts, accessed 2026-11-05.
    # The ratios scale total cash scenarios; they are not a cash consensus.
    "eps_low": 5.31, "eps_mean": 5.89838, "eps_high": 6.08,
    # Q3 2026 announcement ordinary shares outstanding, 2026-09-30.
    "shares": 0.837,
    # Basket 4, ordinary operating business; payment and related financial services.
    "r_perp": 0.10,
    # User-accepted conditional pressure / recovery scenarios, not sell-side forecasts.
    "g_l": 0.0, "g_m": 0.025, "g_h": 0.04,
    # Explicit 2027–2031; same growth after year 5, so no extra growth period.
    "n_years": 5,
}
TIERS = ("L", "M", "H")


def cash_value(first_cash: float, growth: float, rate: float, years: int) -> tuple[float, float]:
    """Return explicit cash PV and terminal PV in billions of USD."""
    flows = [first_cash * (1 + growth) ** year for year in range(years)]
    explicit = sum(cash / (1 + rate) ** (year + 1) for year, cash in enumerate(flows))
    terminal = flows[-1] * (1 + growth) / (rate - growth) / (1 + rate) ** years
    return explicit, terminal


def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    missing = INPUTS.keys() - inp.keys()
    if missing:
        raise ValueError(f"missing inputs: {sorted(missing)}")
    errors = [f"{key}: must be finite and positive" for key in INPUTS
              if key not in ("g_l", "g_m", "g_h")
              and (not math.isfinite(inp[key]) or inp[key] <= 0)]
    if math.isfinite(inp["n_years"]) and inp["n_years"] != int(inp["n_years"]):
        errors.append("n_years must be an integer")
    errors += check_r(inp["r_perp"], "r_perp", 4)
    for key in ("g_l", "g_m", "g_h"):
        if not math.isfinite(inp[key]) or inp[key] <= -1:
            errors.append(f"{key}: invalid cash growth")
        else:
            errors += check_g_cap(inp[key], inp["r_perp"], key)
    errors += ladder("EPS consensus", inp["eps_low"], inp["eps_mean"], inp["eps_high"])
    if errors:
        raise ValueError("; ".join(errors))

    cash = (inp["cfo25"] - inp["capex25"] - inp["sbc25"]
            + inp["cfo9m26"] - inp["capex9m26"] - inp["sbc9m26"]
            - inp["cfo9m25"] + inp["capex9m25"] + inp["sbc9m25"])
    loan_outflow = (inp["loan_out25"] - inp["loan_in25"]
                    + inp["loan_out9m26"] - inp["loan_in9m26"]
                    - inp["loan_out9m25"] + inp["loan_in9m25"])
    cash -= loan_outflow
    base_cash = cash * (inp["ni1q27"] + inp["ni2q27"]) / (inp["ni1q26"] + inp["ni2q26"])
    first_cash = (base_cash * inp["eps_low"] / inp["eps_mean"], base_cash,
                  base_cash * inp["eps_high"] / inp["eps_mean"])
    growth = tuple(inp[key] for key in ("g_l", "g_m", "g_h"))
    years = int(inp["n_years"])
    errors += ladder("starting cash", *first_cash)
    if cash <= 0:
        errors.append("TTM cash after modeled deductions must be positive")
    if errors:
        raise ValueError("; ".join(errors))

    def band_at(dr: float = 0.0, dg: float = 0.0) -> tuple[float, float, float]:
        if inp['r_perp'] + dr <= max(growth) + dg:
            raise ValueError('discount rate must exceed each cash-growth rate')
        return tuple(sum(cash_value(f, g + dg, inp["r_perp"] + dr, years)) / inp["shares"]
                     for f, g in zip(first_cash, growth))

    anchors = band_at()
    errors += ladder("anchors", *anchors)
    flat = tuple(sum(cash_value(f, inp["g_m"], inp["r_perp"], years)) / inp["shares"]
                 for f in first_cash)
    errors += ladder("common-growth starting-cash ladder", *flat)
    for f, g, value in zip(first_cash, growth, anchors):
        if not math.isclose(value, f / (inp["r_perp"] - g) / inp["shares"], rel_tol=1e-12):
            errors.append("explicit cash + terminal must equal constant-growth cash identity")
    if errors:
        raise ValueError("; ".join(errors))
    as_band = lambda values: dict(zip(TIERS, values))
    parts = [cash_value(f, g, inp["r_perp"], years) for f, g in zip(first_cash, growth)]
    result = {
        "ticker": "PYPL.US", "currency": "USD", "valuation_as_of": None,
        "framework_as_of": None, "historical_valuation_as_of": "2026-11-05",
        "historical_framework_as_of": "2026-11-05", "basis_changed": None,
        "anchors": as_band(anchors),
        "candidate": None, "option": None,
        "units": {"price": "USD_PER_SHARE", "amount": "USD_BILLION", "ratio": "RATIO"},
        "segments": {"company": {"values": as_band(anchors)}},
        "key_parameters": {
            "starting_cash": {"unit": "USD_BILLION", "values": as_band(first_cash)},
            "growth_rate": {"unit": "RATIO", "values": as_band(growth)},
            "discount_rate": {"unit": "RATIO", "values": as_band((inp["r_perp"],) * 3)},
        },
        "cash_bridge": {"ttm": cash, "loan_outflow": loan_outflow, "annual_proxy": base_cash},
        "cash_pv": {"explicit": as_band([p[0] for p in parts]),
                    "terminal": as_band([p[1] for p in parts])},
        "sensitivity": {"growth_minus_1pp": as_band(band_at(dg=-.01)),
                        "growth_plus_1pp": as_band(band_at(dg=.01)),
                        "common_growth": as_band(flat),
                        "zero_growth": as_band(tuple(sum(cash_value(f, 0, inp["r_perp"], years)) / inp["shares"] for f in first_cash))},
    }
    if rate_inputs is not None:
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': inp['r_perp']}, band_at=band_at,
            rates_loader=lambda _currency: rate_inputs, base_anchors=anchors)
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result



def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['partial_basis_changed'] = local_basis_changed({'inputs': INPUTS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['segments']['company']['unit'] = 'USD_PER_SHARE'
    result['review_flags'] = ['historical_cash_proxy_and_future_funding_unverified',
                              'historical_comparable_earnings_band_unverified',
                              'historical_forward_return_unverified']
    return result
