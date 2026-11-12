"""Draft shared phosphate-axis data; historical values are not confirmation."""

import math

# MAP 55% domestic average in CNY/tonne. L is 2025 measured, M is the
# 2026-08-10 reference; H is M plus the 1,000 CNY/tonne increment named by
# Goldman on 2026-06-13 (not a third measured point).
MAP_CNY_PER_TONNE = {"L": 3330, "M": 4450, "H": 5450}
# DAP 64% was a parallel observation, not a substitute input for either
# company's earnings. The original axis has the same 1,000 increment at H.
DAP_CNY_PER_TONNE = {"L": 3536, "M": 4850, "H": 5850}
SELLER_INCREMENT = 1000
# IFA P2O5 demand growth 1–2% per year, midpoint; 2025-06 source, axis 2026-09-14.
REFERENCE_GROWTH = 0.015
# Axis text dated 2026-09-14 also described H as 0%. Both later company
# frameworks state their own H adoption as 1.5%; this historical reference
# is not the adopted input and does not overwrite either company's value.
HISTORICAL_H_GROWTH = 0.0
# The original axis says that the 2026 monthly phosphate-rock series was missing.
PHOSPHATE_ROCK_2026 = None

# These are the documented roles of MAP in each later individual ruler, not
# claims that company earnings have no economic exposure to phosphate prices.
SCOPES = {
    "002895.SZ": "2025_low_regime_reference_and_historical_ladder_comparison",
    "600096.SH": "shared_regime_reference_with_historical_elasticity_guard",
}


def inputs(ticker):
    if ticker not in SCOPES:
        raise ValueError(f"{ticker}: not a phosphate-axis member")
    if not isinstance(SELLER_INCREMENT, (int, float)) or isinstance(SELLER_INCREMENT, bool) or not math.isfinite(SELLER_INCREMENT):
        raise ValueError("seller increment must be finite")
    for name, ladder in (("MAP", MAP_CNY_PER_TONNE), ("DAP", DAP_CNY_PER_TONNE)):
        if set(ladder) != {"L", "M", "H"}:
            raise ValueError(f"{name} axis must contain exactly L/M/H")
        values = [ladder[tier] for tier in "LMH"]
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in values):
            raise ValueError(f"{name} prices must be finite numbers")
        if not 0 < values[0] < values[1] < values[2]:
            raise ValueError(f"{name} prices must be positive and ordered")
        if values[2] - values[1] != SELLER_INCREMENT:
            raise ValueError(f"{name} H must equal M plus the named seller increment")
    for label, value in (("reference growth", REFERENCE_GROWTH),
                         ("historical H growth", HISTORICAL_H_GROWTH)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"phosphate {label} must be finite")
    return {**{f"map_{tier.lower()}": MAP_CNY_PER_TONNE[tier] for tier in "LMH"},
            **{f"dap_{tier.lower()}": DAP_CNY_PER_TONNE[tier] for tier in "LMH"},
            "axis_g2": REFERENCE_GROWTH,
            "historic_h_growth": HISTORICAL_H_GROWTH, "scope": SCOPES[ticker],
            # Historical axis header, not a current sell-side consensus.
            "axis_metadata": {
                "axis_id": "phosphate-chain", "logical_id": "_AXIS.phosphate-chain",
                "axis_type": "shared_scenario_axis",
                "title": "磷产业链价格情景轴（国内磷肥定价管理松紧）",
                "label": "磷产业链价格",
                "role": "priced" if ticker in ("002895.SZ",) else "reference",
                "priced_mounts": ["002895.SZ"], "reference_mounts": ["600096.SH"],
                "historical_last_review_as_of": "2026-09-14",
                "historical_consensus": {"band": "M-H", "as_of": "2026-06-13",
                                         "kind": "single_institution", "institution": "高盛"}
                if ticker in ("002895.SZ",) else None,
            }}
