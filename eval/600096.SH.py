#!/usr/bin/env python3
"""600096.SH historical valuation, with inputs independent of the prose.

The 2026-10-30 framework records that the FY2026 forecast is weakened by Q3
results, and that the FY2027 single-broker candidate's premise is stale. The
calculation retains those historical inputs; it does not resolve either issue.
"""
from __future__ import annotations

import hashlib
import json
import math

from lib.gordon import check_g_cap, check_r, perpetual_pe

DEPENDENCIES = {"libraries": ("gordon",), "axes": {"phosphate": "phosphate_chain"}}
FORMULA_ID = "ytn_realized_earnings_regime_gordon_v6"
YI = 1e8
P_TIERS = (0.0, 0.25, 1.0)
# L and M follow the shared IFA reference unless company-specific evidence
# supports a different common value; record its source, date and reason here.
# H remains the 2026-09-20 decision below.
GROWTH_LM_OVERRIDE = None

# FY2023 and FY2022 actual parent profits (CNY 100m); FY2026E EPS is the
# eight-house mean as of 2026-08-20. H is the company's printed FY2022 peak.
# Shares and equity are from the 2026 interim report; the equity-derived returns
# are disclosure only, since this ruler uses 1/(r-g), not retained-profit PE.
INPUTS = {
    "shares": 1822990731.0, "np_l": 45.22, "eps_m_consensus": 2.875,
    "np_h": 60.21, "equity": 254.05, "r_perp": 0.11,
    # Adopted high-tier growth; the 2026-09-20 company decision changed it
    # from the axis's historic 0% reference. It may not exceed M growth.
    "g2_h": 0.015,
    "eps_fy27_single": 3.078, "pe_own_min": 8.83, "pe_own_max": 14.41,
    "beta_map": 0.049, "bps": 13.9358,
    # Original disclosure-only 2025 capex, depreciation, debt and dividend;
    # 2026Q3 and prior-year nine-month sulphur costs support the warning.
    "capex_fy25": 22.8, "da_fy25": 26.1, "debt_fy25": 114.0,
    "sulfur_9m": 3738.0, "sulfur_9m_prior": 1975.0, "dps": 1.4,
    # 35% of total project capex earns the stated unlevered IRR; 9.809 亿 CNY
    # was already paid and is sunk. The remainder includes project borrowing.
    "opt_capex": 81.69, "opt_spent": 9.809, "opt_stake": 0.35,
    "opt_irr": 0.1281, "t_opt": 2032,
}
REQUIRED_INPUTS = frozenset({
    "shares", "np_l", "eps_m_consensus", "np_h", "equity", "r_perp", "g2_h",
    "eps_fy27_single", "pe_own_min", "pe_own_max", "beta_map", "bps",
    "capex_fy25", "da_fy25", "debt_fy25", "sulfur_9m", "sulfur_9m_prior", "dps",
    "opt_capex", "opt_spent", "opt_stake", "opt_irr", "t_opt",
})
# Local input comparison only; the runner still requires source reconciliation.
BASELINE = "e437b2d90bc01fb7c8402ab90366e5951240c715b0313242de7cef8d76f26fab"


def calculate(context):
    inp = dict(INPUTS)
    if not REQUIRED_INPUTS <= inp.keys():
        raise ValueError(f"missing stock inputs: {sorted(REQUIRED_INPUTS - inp.keys())}")
    if inp.keys() - REQUIRED_INPUTS:
        raise ValueError(f"unexpected stock inputs: {sorted(inp.keys() - REQUIRED_INPUTS)}")
    # The runner captures axis metadata separately; keep the calculation and
    # its historical input fingerprint limited to the original axis inputs.
    axis = dict(context["axes"]["phosphate"])
    axis.pop("axis_metadata")
    required = {"map_l", "map_m", "map_h", "dap_l", "dap_m", "dap_h", "axis_g2", "historic_h_growth", "scope"}
    if set(axis) != required:
        raise ValueError("incomplete phosphate data")
    if axis["scope"] != "shared_regime_reference_with_historical_elasticity_guard":
        raise ValueError("phosphate scope incompatible with 600096.SH")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("stock inputs must be finite numbers")
    if any(name.startswith("p_") for name in inp):
        raise ValueError("option weights do not belong in the base inputs")
    if inp["shares"] <= 0 or inp["equity"] <= 0:
        raise ValueError("shares and equity must be positive")
    if inp["beta_map"] >= 0.20:
        raise ValueError("MAP elasticity guard: valuation method needs review")
    r = inp["r_perp"]
    if GROWTH_LM_OVERRIDE is not None and (isinstance(GROWTH_LM_OVERRIDE, bool) or not isinstance(GROWTH_LM_OVERRIDE, (int, float)) or not math.isfinite(GROWTH_LM_OVERRIDE)):
        raise ValueError("growth override must be finite")
    g = axis["axis_g2"] if GROWTH_LM_OVERRIDE is None else GROWTH_LM_OVERRIDE
    g_high = inp["g2_h"]
    errors = check_r(r, "r_perp", 5) + check_g_cap(g, r, "g2_m") + check_g_cap(g_high, r, "g2_h")
    if g_high > g:
        errors.append("high-tier growth must not exceed middle-tier growth")
    if errors:
        raise ValueError("; ".join(errors))
    if abs(inp["np_h"] - 60.21) > 0.01:
        raise ValueError("high profit must be the FY2022 realised peak")
    np_m = inp["eps_m_consensus"] * inp["shares"] / YI
    profits = (inp["np_l"], np_m, inp["np_h"])
    if not profits[0] < profits[1] < profits[2]:
        raise ValueError("profit ladder is not ordered")
    adopted_growth = {"L": g, "M": g, "H": g_high}
    multiples = {tier: 1 / (r - adopted_growth[tier]) for tier in "LMH"}
    if any(not inp["pe_own_min"] <= value <= inp["pe_own_max"] for value in multiples.values()):
        raise ValueError("multiple outside historical band; basket requires review")
    base = tuple(value * YI / inp["shares"] * multiples[tier] for tier, value in zip("LMH", profits))

    # A17: FY2027 single-house point as a growth candidate, never base value.
    growth_candidate = inp["eps_fy27_single"] / inp["eps_m_consensus"] - 1
    candidate = (base[0], inp["eps_fy27_single"] * multiples["M"],
                 base[2] * (1 + growth_candidate))
    if not candidate[0] < candidate[1] < candidate[2]:
        raise ValueError("candidate band is not ordered")

    # A9: the project matures in 2032, discounted to the FY2026 base year.
    if inp["t_opt"] <= 2026 or int(inp["t_opt"]) != inp["t_opt"]:
        raise ValueError("project completion year must be after 2026")
    if not 0 <= inp["opt_spent"] < inp["opt_capex"]:
        raise ValueError("project spending outside total capex")
    investment = inp["opt_stake"] * inp["opt_capex"]
    remaining = inp["opt_stake"] * (inp["opt_capex"] - inp["opt_spent"])
    project_profit = investment * inp["opt_irr"]
    discount = (1 + r) ** (inp["t_opt"] - 2026)
    option = (project_profit * multiples["M"] - remaining) * YI / inp["shares"] / discount
    build = range(2027, int(inp["t_opt"]))
    spread_capex = sum(remaining / len(build) / (1 + r) ** (year - 2026) for year in build)
    option_band = tuple(v + p * option for v, p in zip(base, P_TIERS))
    if not option_band[0] < option_band[1] < option_band[2]:
        raise ValueError("option band is not ordered")

    def band_at_growth(gg):
        return {t: p * YI / inp["shares"] / (r - gg) for t, p in zip("LMH", profits)}

    basis = {"inputs": inp, "axis": axis}
    if GROWTH_LM_OVERRIDE is not None:
        basis["growth_lm_override"] = GROWTH_LM_OVERRIDE
    fingerprint = hashlib.sha256(json.dumps(basis, sort_keys=True,
                                              allow_nan=False).encode()).hexdigest()
    return {
        # Neither a partial input comparison nor a digest proves that the
        # current source set is the one researched on the historical date.
        "ticker": "600096.SH", "currency": "CNY", "valuation_as_of": None,
        "framework_as_of": None, "historical_research_as_of": "2026-10-30",
        "historical_financial_statement_as_of": "2026-06-30", "forecast_source_as_of": None,
        "units": {"price": "CNY_PER_SHARE"},
        "formula_id": FORMULA_ID, "anchors": dict(zip("LMH", base)),
        "limitations": ["fy2026_consensus_weakened_after_q3", "fy2027_single_broker_candidate_outdated"],
        "candidate": {"label": "FY2027单家", "anchors": dict(zip("LMH", candidate))},
        "option": {"anchors": dict(zip("LMH", option_band)), "value": option,
                   "weights": dict(zip("LMH", P_TIERS))},
        "details": {
            "historical_map": {t: axis[f"map_{t.lower()}"] for t in "LMH"},
            "parallel_dap": {t: axis[f"dap_{t.lower()}"] for t in "LMH"},
            "growth_reference": axis["axis_g2"], "historical_axis_h_growth": axis["historic_h_growth"],
            "adopted_growth": adopted_growth,
            "discount_rate": dict.fromkeys("LMH", r),
            "return_on_equity": {t: p / inp["equity"] for t, p in zip("LMH", profits)},
            "multiple": multiples,
            "candidate_growth": growth_candidate,
            "retention_multiple": {t: perpetual_pe(adopted_growth[t], p / inp["equity"], r)
                                    for t, p in zip("LMH", profits)},
            "g_sensitivity": {"minus_0_5pp": band_at_growth(g - 0.005),
                              "plus_0_5pp": band_at_growth(g + 0.005),
                              "minus_1pp": band_at_growth(g - 0.01),
                              "plus_1pp": band_at_growth(g + 0.01),
                              "zero_growth": band_at_growth(0)},
            "profit_per_100m": YI / inp["shares"] * multiples["M"],
            "option_zero_growth": (project_profit / r - remaining) * YI / inp["shares"] / discount,
            "option_full_capex": (project_profit * multiples["M"] - investment) * YI / inp["shares"] / discount,
            "option_spread_capex": (project_profit * multiples["M"] / discount - spread_capex) * YI / inp["shares"],
            "profit_trough_at_zero_growth": profits[0] * YI / inp["shares"] / r,
            "book_value_floor": inp["bps"],
            "observed_capex_fy25": inp["capex_fy25"], "observed_depreciation_fy25": inp["da_fy25"],
            "observed_debt_fy25": inp["debt_fy25"], "observed_dividend": inp["dps"],
            "sulfur_9m": inp["sulfur_9m"], "sulfur_9m_prior": inp["sulfur_9m_prior"],
        },
        "basis_changed": None, "partial_basis_changed": fingerprint != BASELINE,
    }
