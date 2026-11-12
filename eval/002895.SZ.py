#!/usr/bin/env python3
"""002895.SZ historical consensus ruler; the 2026Q3 forecast warning remains."""
from __future__ import annotations

import hashlib
import json
import math

from lib.gordon import BASKET_R, check_g_cap, check_r, payout_gap, perpetual_pe

DEPENDENCIES = {"libraries": ("gordon",), "axes": {"phosphate": "phosphate_chain"}}
FORMULA_ID = "chuanheng_consensus_fy28_gordon_mines_opt_v4"
YI = 1e8
NUM_YEAR = 2028
P_TIERS = (0.0, 0.25, 1.0)
# Follow the shared IFA reference unless company-specific research supports
# another common L/M/H growth rate; record the source, date and reason here.
GROWTH_OVERRIDE = None

# FY2028 M/H: six brokers after 2026H1; L: realised FY2025 parent profit
# converted to the 2026H1 share count. Q3 weakened the 2026 consensus path;
# the 2027/28 estimates await post-Q3 updates, not supplied by this migration.
INPUTS = {
    "shares": 605868383.0, "bps_h1": 12.2116, "dps_after_h1": 0.3,
    "eps_h1": 0.9218, "np_fy25": 12.6024,
    "cons_fy26_m": 2.453333, "cons_fy26_h": 2.59,
    "cons_fy27_m": 2.968333, "cons_fy27_h": 3.14,
    "cons_fy28_l": 3.36, "cons_fy28_m": 3.581667, "cons_fy28_h": 3.77,
    # These are the old MAP model's recorded M/H EPS, used only in the
    # comparison against the FY2028 consensus, not as new predictions.
    "ladder_eps_m": 2.1669, "ladder_eps_h": 3.1551,
    # Independently recorded observation identifying the FY2025 earnings year;
    # it is a historical fact, not a second copy of the current axis ladder.
    "map_fy25_observed": 3330,
    "r_perp": 0.13, "r_ctl": 0.1, "tau": 1.5,
    "ronic_y1": 2028, "ronic_y2": 2032, "ronic_ss": 0.146,
    "payout_obs": 0.865, "ttm_eps": 2.117,
    "pe_own_min": 10.45, "pe_own_med": 15.34, "pe_own_p75": 20.31,
    "pe_same_min_l": 11.9, "pe_same_max_l": 21.3,
    "band_l_start": 202412, "band_own_low": 202401, "pb_own_min": 1.17,
    "same_eps_weeks_m": 0,
    # 2026H1 own ore price and operating costs, taxes, equity capacity and
    # unspent capital of each announced mine; see the original framework A9.
    "opt_price": 683.7, "opt_cost": 135.1, "opt_price_mid5": 651.3,
    "opt_cost_fy25": 150.0, "opt_restax": 0.075, "opt_tax": 0.25,
    "lhd_cap": 500.0, "lhd_eq": 0.40009, "lhd_k": 26.0, "lhd_t": 2029, "lhd_pub": 202212,
    "lzz_cap": 180.0, "lzz_eq": 0.585, "lzz_k": 5.6988, "lzz_t": 2029, "lzz_pub": 202409,
    "jgl_cap": 250.0, "jgl_eq": 0.9, "jgl_k": 8.879, "jgl_t": 2030, "jgl_pub": 202204,
}
REQUIRED_INPUTS = frozenset({
    "shares", "bps_h1", "dps_after_h1", "eps_h1", "np_fy25",
    "cons_fy26_m", "cons_fy26_h", "cons_fy27_m", "cons_fy27_h",
    "cons_fy28_l", "cons_fy28_m", "cons_fy28_h", "ladder_eps_m", "ladder_eps_h",
    "map_fy25_observed", "r_perp", "r_ctl", "tau", "ronic_y1", "ronic_y2", "ronic_ss",
    "payout_obs", "ttm_eps", "pe_own_min", "pe_own_med", "pe_own_p75", "same_eps_weeks_m",
    "pe_same_min_l", "pe_same_max_l", "band_l_start", "band_own_low", "pb_own_min",
    "opt_price", "opt_cost", "opt_restax", "opt_tax", "opt_price_mid5", "opt_cost_fy25",
    *(f"{mine}_{field}" for mine in ("lhd", "lzz", "jgl") for field in ("cap", "eq", "k", "t", "pub")),
})
# Local comparison only; the runner still requires source reconciliation.
BASELINE = "6cbf1ce24ab1fceefed8cc56ee0df9f72b0e10a8674c8b4562116cda8ab8338d"


def path_pe(g, roe, r, t0, y1, y2, steady):
    """The original calendar-based three-stage return path, not restarted at each mine."""
    rs = min(roe, steady)

    def payout(ron):
        return min(1.0, 1.0 - g / ron) if g > 0 else 1.0

    pv, earnings, year = 0.0, 1.0, 1
    while True:
        calendar_year = t0 + year - 1
        if calendar_year > y1 and calendar_year >= y2:
            return pv + earnings * payout(rs) / ((r - g) * (1 + r) ** (year - 1))
        ron = roe if calendar_year <= y1 else roe + (rs - roe) * (calendar_year - y1) / (y2 - y1)
        pv += earnings * payout(ron) / (1 + r) ** year
        earnings *= 1 + g
        year += 1


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
    if axis["scope"] != "2025_low_regime_reference_and_historical_ladder_comparison":
        raise ValueError("phosphate scope incompatible with 002895.SZ")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("stock inputs must be finite numbers")
    if any(name.startswith("p_") for name in inp):
        raise ValueError("option weights do not belong in the base inputs")
    if inp["shares"] <= 0:
        raise ValueError("shares must be positive")
    if abs(axis["map_l"] - inp["map_fy25_observed"]) > 0.5:
        raise ValueError("low axis regime no longer matches the FY2025 realised earnings year")
    if GROWTH_OVERRIDE is not None and (isinstance(GROWTH_OVERRIDE, bool) or not isinstance(GROWTH_OVERRIDE, (int, float)) or not math.isfinite(GROWTH_OVERRIDE)):
        raise ValueError("growth override must be finite")
    r, r_ctl = inp["r_perp"], inp["r_ctl"]
    g = axis["axis_g2"] if GROWTH_OVERRIDE is None else GROWTH_OVERRIDE
    errors = check_r(r, "r_perp", 6) + check_g_cap(g, r, "g2")
    if abs(r_ctl - BASKET_R[4][1]) > 1e-12:
        errors.append("control rate must be basket 4")
    if abs(inp["tau"] - 1.5) > 1e-9:
        errors.append("tau must match 2026-06-30 to FY2028 opening")
    if not (int(inp["ronic_y1"]) == NUM_YEAR and int(inp["ronic_y2"]) > int(inp["ronic_y1"])):
        errors.append("return path years are invalid")
    if inp["ronic_ss"] < r:
        errors.append("steady return below discount rate")
    if not inp["cons_fy28_l"] < inp["cons_fy28_m"] < inp["cons_fy28_h"]:
        errors.append("FY2028 consensus ladder is not ordered")
    shares_yi = inp["shares"] / YI
    eps_l = inp["np_fy25"] / shares_yi
    if eps_l >= inp["cons_fy28_l"]:
        errors.append("actual low must be below consensus low")
    mean28 = inp["cons_fy28_m"]
    in_old_range = inp["ladder_eps_m"] <= mean28 <= inp["ladder_eps_h"]
    old_dev = inp["ladder_eps_m"] / mean28 - 1
    if in_old_range and abs(old_dev) <= 0.20:
        errors.append("old price ladder now passes consensus gate; revisit numerator")
    if errors:
        raise ValueError("; ".join(errors))

    bps0 = inp["bps_h1"] - inp["dps_after_h1"]
    tiers = {
        "L": (eps_l, eps_l, eps_l),
        "M": (mean28, inp["cons_fy26_m"], inp["cons_fy27_m"]),
        "H": (inp["cons_fy28_h"], inp["cons_fy26_h"], inp["cons_fy27_h"]),
    }

    def ruler(rate, growth=g, low_eps=None):
        out = {}
        for tier, (e28, e26, e27) in tiers.items():
            if tier == "L" and low_eps is not None:
                e28 = e26 = e27 = low_eps
            gw = (e28 / e26) ** 0.5 - 1.0
            unbooked = e26 - inp["eps_h1"] + e27
            bps = bps0
            for _ in range(500):
                next_bps = bps0 + min(1.0, max(0.0, gw * bps / e28)) * unbooked
                if abs(next_bps - bps) < 1e-13:
                    break
                bps = next_bps
            roe = e28 / bps
            retained = min(1.0, max(0.0, gw / roe))
            multiple = path_pe(growth, roe, rate, NUM_YEAR, int(inp["ronic_y1"]),
                               int(inp["ronic_y2"]), inp["ronic_ss"])
            window = unbooked * (1 - retained)
            value = e28 * multiple / (1 + rate) ** inp["tau"] + window / (1 + rate) ** (inp["tau"] / 2)
            out[tier] = {"eps": e28, "bps": bps, "roe": roe, "multiple": multiple,
                         "window": window, "unbooked": unbooked, "retained": retained,
                         "window_growth": gw, "anchor": value}
        return out

    rows = ruler(r)
    L, M, H = (rows[t]["anchor"] for t in "LMH")
    if not L < M < H:
        raise ValueError("anchor ladder is not ordered")
    mines = (("lhd", "老虎洞"), ("lzz", "老寨子"), ("jgl", "鸡公岭"))
    for key, name in mines:
        if inp[f"{key}_t"] <= NUM_YEAR:
            raise ValueError(f"{name}: realisation year must be after FY2028")

    def mine_pe(rate, year, fresh=False):
        roe = ruler(rate)["M"]["roe"]
        y1 = year if fresh else int(inp["ronic_y1"])
        y2 = year + int(inp["ronic_y2"] - inp["ronic_y1"]) if fresh else int(inp["ronic_y2"])
        return path_pe(g, roe, rate, year, y1, y2, inp["ronic_ss"])

    def vopt(unit_profit, rate, keys=None, fresh=False):
        total, detail = 0.0, {}
        for key, name in mines:
            if keys is not None and key not in keys:
                continue
            year = inp[f"{key}_t"]
            tons = inp[f"{key}_cap"] * inp[f"{key}_eq"]
            profit = tons * unit_profit / 1e4
            capital = inp[f"{key}_k"] * inp[f"{key}_eq"]
            multiple = mine_pe(rate, int(year), fresh)
            pv = (profit * multiple - capital) / (1 + rate) ** (year - NUM_YEAR + inp["tau"])
            total += pv
            detail[name] = {"tons_10k": tons, "profit_yi": profit, "capital_yi": capital,
                            "multiple": multiple, "value_per_share": pv / shares_yi}
        return total / shares_yi, detail

    def unit_profit(price, cost=None, tax=None):
        cost = inp["opt_cost"] if cost is None else cost
        tax = inp["opt_tax"] if tax is None else tax
        return (price * (1 - inp["opt_restax"]) - cost) * (1 - tax)

    nit = unit_profit(inp["opt_price"])
    option, mine_details = vopt(nit, r)
    option_band = tuple(value + weight * option for value, weight in zip((L, M, H), P_TIERS))
    control = ruler(r_ctl)
    control_option, _ = vopt(nit, r_ctl)

    # The same-earnings band included mines announced before the window; only
    # those mines belong in its comparison. This is a financial blocking gate.
    known = [key for key, _ in mines if int(inp[f"{key}_pub"]) < int(inp["band_l_start"])]
    known_value, _ = vopt(nit, r, keys=known)
    early = [key for key, _ in mines if int(inp[f"{key}_pub"]) < int(inp["band_own_low"])]
    band_multiple = (L + known_value) / eps_l
    same_band = inp["pe_same_min_l"] <= band_multiple <= inp["pe_same_max_l"]
    if not same_band:
        errors.append("same-earnings band fails; rerun step 2")
    if int(inp["same_eps_weeks_m"]) >= 6:
        errors.append("FY2028 same-earnings observations require a band test")
    discount = (1 + r) ** inp["tau"]
    window_pv = rows["M"]["window"] / (1 + r) ** (inp["tau"] / 2)
    coordinates = {"earnings_over_r": mean28 / r / discount + window_pv,
                   "dividend_gordon": inp["payout_obs"] * mean28 / (r - g) / discount + window_pv,
                   "book_floor": inp["bps_h1"] * inp["pb_own_min"]}
    gate = any(abs(M / value - 1) <= 0.20 for value in coordinates.values())
    if not gate:
        errors.append("correction gate fails all independent coordinates")
    for key, name in mines:
        if mine_pe(r, int(inp[f"{key}_t"])) > rows["M"]["multiple"] + 1e-12:
            errors.append(f"{name}: calendar return path cannot restart")
    if errors:
        raise ValueError("; ".join(errors))

    sensitivity_units = {
        "yuntianhua_irr": 104.6, "fulin_internal": 252.7,
        "income_tax_15pct": unit_profit(inp["opt_price"], tax=0.15),
        "ore_500_including_tax": unit_profit(500 / 1.13),
        "own_five_year_mean": unit_profit(inp["opt_price_mid5"]),
        "fy2025_cost": unit_profit(inp["opt_price"], cost=inp["opt_cost_fy25"]),
        "ore_1025_including_tax": unit_profit(1025 / 1.13),
    }
    def anchors_at(rate, growth=g, low=None):
        return {t: item["anchor"] for t, item in ruler(rate, growth, low).items()}

    basis = {"inputs": inp, "axis": axis}
    if GROWTH_OVERRIDE is not None:
        basis["growth_override"] = GROWTH_OVERRIDE
    fingerprint = hashlib.sha256(json.dumps(basis, sort_keys=True,
                                              allow_nan=False).encode()).hexdigest()
    return {
        # No current date can be inferred from a partial input fingerprint or
        # a digest. Keep original report/research dates only as history until
        # the complete sources and a new valuation date are reconciled.
        "ticker": "002895.SZ", "currency": "CNY", "valuation_as_of": None,
        "framework_as_of": None, "historical_research_as_of": "2026-10-25",
        "historical_financial_statement_as_of": "2026-06-30", "forecast_source_as_of": None,
        "units": {"price": "CNY_PER_SHARE"},
        "formula_id": FORMULA_ID, "anchors": dict(zip("LMH", (L, M, H))),
        "limitations": ["fy2026_consensus_weakened_after_q3", "fy2027_2028_post_q3_forecasts_pending"],
        "candidate": None,
        "option": {"anchors": dict(zip("LMH", option_band)), "value": option,
                   "weights": dict(zip("LMH", P_TIERS))},
        "details": {
            "historical_map": {t: axis[f"map_{t.lower()}"] for t in "LMH"},
            "parallel_dap": {t: axis[f"dap_{t.lower()}"] for t in "LMH"},
            "growth_reference": axis["axis_g2"], "historical_axis_h_growth": axis["historic_h_growth"],
            "adopted_growth": dict.fromkeys("LMH", g), "discount_rate": dict.fromkeys("LMH", r),
            "tier_calculations": rows, "steady_return": inp["ronic_ss"],
            "old_ladder_consensus_deviation": old_dev, "old_ladder_contains_consensus": in_old_range,
            "same_earnings_band_passes": same_band, "same_earnings_multiple": band_multiple,
            "same_earnings_included_mines": known, "early_band_mines": early,
            "early_band_option": vopt(nit, r, keys=early)[0],
            "ttm_earnings": inp["ttm_eps"],
            "historical_pe_band": {"min": inp["pe_own_min"], "median": inp["pe_own_med"],
                                   "p75": inp["pe_own_p75"]},
            "gate_passes": gate, "gate_coordinates": coordinates,
            "mines": mine_details, "option_unit_profit": nit,
            "option_fresh_return_path": vopt(nit, r, fresh=True)[0],
            "option_sensitivity": {name: vopt(unit, r)[0] for name, unit in sensitivity_units.items()},
            "control_anchors": {t: row["anchor"] for t, row in control.items()},
            "control_option": control_option,
            "sensitivity": {"growth_0_5pct": anchors_at(r, 0.005),
                            "growth_2_5pct": anchors_at(r, 0.025),
                            "growth_zero": anchors_at(r, 0),
                            "rate_minus_0_5pp": anchors_at(r - 0.005),
                            "rate_plus_0_5pp": anchors_at(r + 0.005),
                            "low_consensus": anchors_at(r, low=inp["cons_fy28_l"]),
                            "low_fy26_consensus": anchors_at(r, low=inp["cons_fy26_m"])},
            "payout": dict(zip(("model", "gap"), payout_gap(g, rows["M"]["roe"], inp["payout_obs"]))),
            "old_perpetual_multiple": {t: perpetual_pe(g, rows[t]["roe"], r) for t in "LMH"},
        },
        "basis_changed": None, "partial_basis_changed": fingerprint != BASELINE,
    }
