#!/usr/bin/env python3
"""0189.HK (Dongyue Group) valuation eval — recompute anchors from frameworks/0189.HK.md.

frameworks/0189.HK.md is the source of truth; this script re-parses its §3 Inputs
table, recomputes L/M/H / A/B and exits 1 on mismatch.  The framework carries
no current price (AGENTS.md「现价 — 禁写契约」): this script neither reads a
price nor derives or checks a zone -- the daily digest derives the zone from
live quotes.

formula_id: dongyue_quota_sotp_actual_year_flat_v4

Main ruler: four-leg segment SOTP.  The refrigerant leg's three tiers are
**named price scenarios** (L = R32 45,000 / M = 2025 average 53,600 / H = Q3
contract 64,500 held flat, A4) mapped to a unit segment result per quota tonne
through a bridge `k * sum_i w_i (P_i - c_i)` (w_i = 2026 MEE quota by product,
c_i = cash cost implied by the 2026-04 per-tonne gross margins, k calibrated on
FY2025 + 26H1).  The other three legs take **three actually observed operating
years** (L=FY2024, M=FY2025, H=26H1 annualised, A22), every leg the *same* year
in a given tier so the inter-leg correlation structure is inherited from
history rather than assumed.  The by-product leg (A8) is rebuilt as
recurring + impairment-scenario because its reported FY2024/FY2025 losses were
majority one-off property impairments now near exhaustion.

Each segment result is taxed, scaled by the *leg-specific* attributable ownership
ratio (refrigerant + fluoropolymer sit in Dongyue Polymers, 74.06% owned;
organosilicone is the separately A-listed Dongyue Organosilicon, 44.40% owned),
multiplied by a **flat** per-leg Gordon multiple generated at the basket r
(all four legs sit in basket 6 周期商品, r 13%, A24); the after-tax interest on
the listed cash (which sits inside the segment results) is taken out of every
tier at 1/r, and attributable net cash less the declared-unpaid dividend is
added at face value (A11; the existing cash line is kept -- valuation-rules
「经营价值与超额现金」, 2026-10-15 framework correction).  The fluoropolymer
leg's RONIC strips the entity's allocated cash and its interest.  Multiples do not vary by tier: this is a `cyclical`
name whose numerators already carry the cycle, and two legs go negative in
some tier (organosilicone at M, the by-product leg at H), which would make
tiered multiples reward bigger losses.

Reporting currency is CNY, the listing currency is HKD: fx_cny_hkd is an
explicit Input and is applied once, at step 5.

H is the farthest >=2-house consensus year with a range (FY2027E high, 5
houses; valuation-rules「数据优先级与同业同尺」2026-10-03, A5): the H-world leg
mix (Q3 contract held flat + 26H1 annualised) is scaled pro rata so that
attributable EPS equals eps_2027_h -- the old consensus-2027E candidate band is
thereby upgraded into the deck and deleted.

The PB floor is disclosed only, never max()-ed into L (A16).  V_opt (PTFE-AI /
semiconductor grade, §1) = one snapshot share of today's fluoropolymer leg
(26H1 annualised revenue x reported segment margin), valued on this name's own
fluoropolymer multiple and discounted at the basket r from t_opt (aligned year
+ 2, no named date) back to t_num (valuation-rules「未建模期权」2026-10-03),
less the unspent capital of the named industrialisation projects (2026 interim
"additional investment of more than RMB1 billion": opt_k budget - opt_k_spent,
x own_poly, spread evenly over opt_k_y0..opt_k_y1 and discounted at the basket r
to t_num; valuation-rules「未建模期权」2026-10-04 new-capacity rule, v4); it
stays out of the deck.

Sanity checks beyond the anchor comparison:
  * r_perp must be the basket the Inputs row names (parse_baskets + check_r);
    every g2 must sit under g_cap(r); every pe_* must equal the Gordon multiple
    its named g2 / ROE / r generate
  * BRIDGE REPRODUCTION (A4): bridge_k on the FY2025 / 26H1 actual average
    prices must reproduce the reported unit result within BRIDGE_REPRO_TOL,
    bridge_k must equal the mean of those two calibration ratios, and every
    upt_x must equal the bridge at that tier's px_* (FY2024 is a regime break
    and is printed as the deep_discount pressure coordinate, not asserted)
  * SAME-SOURCE (A22) on the three actual-year legs: fluoropolymer,
    organosilicone and dichloromethane must equal the reported figure for that
    tier's year — silently swapping in an extrapolation fails
  * the same ownership/tax bridge must reproduce the FY2025 reported profit
    attributable to owners (RMB 1,641,812k) within OWNERSHIP_BRIDGE_TOL
  * PERFECT-CORRELATION GUARD: the L tier's segment total must not fall below
    FY2023's actual total (650,645); each leg's own historical minimum would
    sum to 55,421 — a world that never happened (A22)
  * L < M < H on the *total* only — individual legs may be non-monotonic

Run:  python3 frameworks/eval/0189.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import check_g_cap, check_r, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    outputs_section,
    parse_baskets,
    parse_inputs,
)
from eval.lib.zones import zone_of  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "0189.HK.md"
FORMULA_ID = "dongyue_quota_sotp_actual_year_flat_v4"
LISTING_CCY = "HKD"
TOL = 0.05  # outputs are rounded to 2 decimals
YI = 1e5  # 亿, from RMB thousand

# FY2025 audited reconciliation targets (2025 annual report, RMB thousand).
FY25 = {
    "res_ref": 2287697.0,
    "res_poly": 356642.0,
    "res_sil": -51711.0,
    "res_oth": -15794.0,  # 二氯甲烷及烧碱 + 其他业务 + 非分部项目
    "tax": 0.1526,  # 393,241 / 2,576,834
    "attributable": 1641812.0,
}
OWNERSHIP_BRIDGE_TOL = 0.03  # the framework claims -0.9%; fail if the bridge drifts past 3%

# A22 same-source anchors for the three actual-year legs (RMB thousand),
# straight from the FY2025 annual report / 2026 interim segment tables.
TIER_YEAR = {"l": "FY2024", "m": "FY2025", "h": "26H1 annualised"}
REPORTED = {
    "l": {"poly": 508088.0, "sil": 101668.0, "dcm": 372161.0},
    "m": {"poly": 356642.0, "sil": -51711.0, "dcm": 358053.0},
    "h": {"poly": 877146.0, "sil": 471612.0, "dcm": 119206.0},
}
SAME_SOURCE_TOL = 0.001

# V_opt one-share snapshot (A25): fluoropolymer leg, 2026 interim segment table.
POLY_26H1 = {"revenue": 2140549.0, "result": 438573.0}

# A4 price bridge.  Products in bridge order; 其他 HFC (152a etc.) has no price
# series and rides R125's price and cash cost.
PRODUCTS = ("r32", "r125", "r134a", "hfc_oth", "r22")
PRICE_KEY = {"r32": "r32", "r125": "r125", "r134a": "r134a", "hfc_oth": "r125", "r22": "r22"}
# Calibration points (annual average prices 元/吨 R32 / R125 / R134a / R22, and
# the reported unit segment result per quota tonne).  FY2024 is quota year 1
# with a different cost base — a regime break the bridge is documented NOT to
# reproduce (+64%), so it is printed, not asserted.
BRIDGE_CALIB = {
    "FY2025": ((53600, 45000, 49500, 27000), 17656.06),
    "26H1": ((63500, 55000, 60000, 20000), 19233.03),
}
BRIDGE_REGIME_BREAK = {"FY2024": ((33000, 36800, 33000, 31000), 6223.28)}
BRIDGE_REPRO_TOL = 0.20  # valuation-rules.md: ≥2 years within ±20%
BRIDGE_K_TOL = 0.001  # bridge_k is stated to 4 decimals
UPT_TOL = 1.0  # upt_* are stated to the 元/吨

# A22 perfect-correlation guard.
FY23_SEGMENT_TOTAL = 650645.0  # worst year actually observed
LEGWISE_MIN_SUM = 55421.0  # sum of each leg's own historical low — never happened

# Own post-quota PE band (A10), for the ③ 出带 disclosure only.
OWN_PE_BAND_MIN = 10.71

REQUIRED = [
    "shares", "fx_cny_hkd", "bvps_cny", "tax",
    "own_poly", "own_sil", "own_oth",
    "quota_t", "q_r32", "q_r125", "q_r134a", "q_hfc_oth", "q_r22",
    "upt_l", "upt_m", "upt_h",
    "px_r32_l", "px_r32_m", "px_r32_h", "px_r125_l", "px_r125_m", "px_r125_h",
    "px_r134a_l", "px_r134a_m", "px_r134a_h", "px_r22_l", "px_r22_m", "px_r22_h",
    "eps_2027_l", "eps_2027_m", "eps_2027_h",
    "opt_rev", "opt_margin", "t_opt", "t_num",
    "opt_k", "opt_k_spent", "opt_k_y0", "opt_k_y1",
    "c_r32", "c_r125", "c_r134a", "c_r22", "bridge_k",
    "res_poly_l", "res_poly_m", "res_poly_h",
    "res_sil_l", "res_sil_m", "res_sil_h",
    "dcm_l", "dcm_m", "dcm_h",
    "oth_recur", "oth_imp_l", "oth_imp_m", "oth_imp_h", "nonseg",
    "r_perp", "np_poly_fy25", "equity_poly_avg", "equity_sil_avg",
    "g2_ref", "g2_poly", "g2_sil", "g2_oth",
    "pe_ref", "pe_poly", "pe_sil", "pe_oth",
    "net_cash", "cash_attrib", "pb_floor",
    "div_declared", "c_ex", "cash_yield", "tax_eff", "cash_grp_avg", "equity_grp_avg",
    "rs_poly", "y1_poly", "y2_poly", "tau", "eps_2026_h", "ni_h1_2026",
]
CEX_TOL = 1.0  # RMB thousand


def path_pe(g2: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-stage return path Gordon (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    library three-stage function is not built yet, so it lives here).  Value per unit of t0 earnings:
    the forward return holds to calendar Y1, falls linearly to the steady return by Y2, steady after;
    retention b = g2 / return each year; tail Gordon at Y2 on the steady return."""
    rs = min(roe, r_s)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rs) / ((r - g2) * (1.0 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (rs - roe) * (cal - y1) / (y2 - y1)
        pv += e * min(1.0, 1.0 - g2 / ro) / (1.0 + r) ** t
        e *= 1.0 + g2
        t += 1


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def attributable_np(
    res_ref: float, res_poly: float, res_sil: float, res_oth: float,
    tax: float, own_poly: float, own_sil: float, own_oth: float,
) -> tuple[float, float, float, float]:
    """Per-leg after-tax profit attributable to owners of the Company (RMB'000)."""
    k = 1.0 - tax
    return (
        res_ref * own_poly * k,
        res_poly * own_poly * k,
        res_sil * own_sil * k,
        res_oth * own_oth * k,
    )


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- structural sanity on the inputs themselves -------------------------
    for name in ("own_poly", "own_sil", "own_oth", "cash_attrib"):
        if not 0.0 < inp[name] <= 1.0:
            errors.append(f"{name}={inp[name]} outside (0, 1]")
    if not 0.0 <= inp["tax"] < 0.5:
        errors.append(f"tax={inp['tax']} implausible")
    if inp["quota_t"] <= 0:
        errors.append(f"quota_t={inp['quota_t']} must be positive")
    quota = {p: inp[f"q_{p}"] for p in PRODUCTS}
    if abs(sum(quota.values()) - inp["quota_t"]) > 0.5:
        errors.append(f"q_* sum {sum(quota.values()):,.0f} != quota_t {inp['quota_t']:,.0f}")

    # Multiples are FLAT by construction (A9/A10). There is deliberately no
    # ordering check here: tiered multiples would double-count the cycle for a
    # `cyclical` name and would reward bigger losses on the legs that go
    # negative. Guard the invariant that actually matters instead.
    for leg in ("ref", "poly", "sil", "oth"):
        if inp[f"pe_{leg}"] <= 0:
            errors.append(f"pe_{leg}={inp[f'pe_{leg}']} must be positive")
    if "pe_ref_l" in inp or "pe_ref_h" in inp:
        errors.append("tiered pe_* inputs reintroduced — A10 requires flat multiples")

    # --- A24 / A10: basket r, and flat multiples Gordon-generated per leg ----
    # ROE per leg comes from the note-36 subsidiary accounts (Dongyue Polymers
    # carries refrigerants + fluoropolymers; Dongyue Organosilicon the silicone
    # leg); the by-product leg has no entity, and with g2 < 0 the payout cap
    # binds so its ROE is irrelevant.
    r = inp["r_perp"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for leg in ("ref", "poly", "sil", "oth"):
        errors += check_g_cap(inp[f"g2_{leg}"], r, f"g2_{leg}")
    # Excess cash (valuation-rules「经营价值与超额现金」①, framework correction
    # 2026-10-15): the framework already lists all net cash at face value, so the
    # structure stays (no operating-cash anchor is cut); the declared-unpaid FY2025
    # final dividend is a debt-like item and comes off, and the cash's after-tax
    # interest -- which A11 says sits inside the segment results -- comes out of
    # the numerators and out of the leg RONIC (numerator and denominator).
    c_ex = inp["net_cash"] - inp["div_declared"]
    if abs(c_ex - inp["c_ex"]) > CEX_TOL:
        errors.append(f"c_ex {inp['c_ex']:,.0f} != net_cash − div_declared {c_ex:,.0f}")
    cash_after_tax = 1.0 - inp["tax_eff"]
    # Dongyue Polymers' own cash is not disclosed: allocate the group's FY2025
    # average cash by the entity's share of average group equity (A11).
    cash_poly = inp["cash_grp_avg"] * inp["equity_poly_avg"] / inp["equity_grp_avg"]
    inc_poly = cash_poly * inp["cash_yield"] * cash_after_tax
    roe_poly_book = inp["np_poly_fy25"] / inp["equity_poly_avg"]
    roe_poly = (inp["np_poly_fy25"] - inc_poly) / (inp["equity_poly_avg"] - cash_poly)
    roe_sil = inp["res_sil_h"] * (1.0 - inp["tax"]) / inp["equity_sil_avg"]

    def gordon(r_: float) -> dict[str, float]:
        # Fluoropolymer leg (g2 > 0, not commodity-axis bridged) on the three-stage path: steady
        # return = max(layers, r) -- own cycle unusable (group basis != entity forward formula),
        # no >= 5-year mature same-business peer, fallback 11% < r -> the basket r (A10).
        rs = max(inp["rs_poly"], r_)
        return {
            "ref": perpetual_pe(inp["g2_ref"], roe_poly, r_),
            "poly": path_pe(inp["g2_poly"], roe_poly, r_, int(inp["t_num"]), int(inp["y1_poly"]),
                            int(inp["y2_poly"]), rs),
            "sil": perpetual_pe(inp["g2_sil"], roe_sil, r_),
            "oth": perpetual_pe(inp["g2_oth"], 0.139, r_),  # ROE drops out at g2 < 0
        }

    gen = gordon(r)
    for leg, val in gen.items():
        if abs(val - inp[f"pe_{leg}"]) > TOL:
            errors.append(
                f"pe_{leg}={inp[f'pe_{leg}']} is not the Gordon multiple {val:.3f} generated by "
                f"g2_{leg}={inp[f'g2_{leg}']} at r={r} — the multiple has come loose from its named g"
            )

    # --- A4 price bridge: unit segment result per quota tonne -----------------
    def bridge_unit(px: dict[str, float], k: float) -> float:
        """k × Σ w_i (P_i − c_i), weights = product quota / total quota."""
        margin = sum(quota[p] * (px[PRICE_KEY[p]] - inp[f"c_{PRICE_KEY[p]}"]) for p in PRODUCTS)
        return k * margin / inp["quota_t"]

    def px_of(r32: float, r125: float, r134a: float, r22: float) -> dict[str, float]:
        return {"r32": r32, "r125": r125, "r134a": r134a, "r22": r22}

    def tier_px(x: str) -> dict[str, float]:
        return px_of(*(inp[f"px_{p}_{x}"] for p in ("r32", "r125", "r134a", "r22")))

    calib_ratio = {y: unit / bridge_unit(px_of(*px), 1.0) for y, (px, unit) in BRIDGE_CALIB.items()}
    k_mean = sum(calib_ratio.values()) / len(calib_ratio)
    if abs(k_mean - inp["bridge_k"]) > BRIDGE_K_TOL:
        errors.append(f"bridge_k={inp['bridge_k']} is not the mean of the calibration ratios {k_mean:.4f}")
    for y, (px, unit) in BRIDGE_CALIB.items():
        est = bridge_unit(px_of(*px), inp["bridge_k"])
        if abs(est / unit - 1.0) > BRIDGE_REPRO_TOL:
            errors.append(f"bridge does not reproduce {y}: {est:,.0f} vs reported {unit:,.0f} ({est / unit - 1:+.1%})")
    for x in "lmh":
        est = bridge_unit(tier_px(x), inp["bridge_k"])
        if abs(est - inp[f"upt_{x}"]) > UPT_TOL:
            errors.append(f"upt_{x}={inp[f'upt_{x}']:,.0f} but bridge @ px_*_{x} gives {est:,.1f}")

    # The refrigerant leg is the one that IS monotonic (quota volume is fixed,
    # so the price scenario carries the tier). The other legs are allowed to invert.
    if not inp["upt_l"] < inp["upt_m"] < inp["upt_h"]:
        errors.append(f"upt not increasing: {inp['upt_l']}/{inp['upt_m']}/{inp['upt_h']}")

    # --- A22 same-source check on the three actual-year legs -------------------
    for x in "lmh":
        checks = {
            "poly": (inp[f"res_poly_{x}"], REPORTED[x]["poly"]),
            "sil": (inp[f"res_sil_{x}"], REPORTED[x]["sil"]),
            "dcm": (inp[f"dcm_{x}"], REPORTED[x]["dcm"]),
        }
        for leg, (got, want) in checks.items():
            if abs(got - want) / max(abs(want), 1.0) > SAME_SOURCE_TOL:
                errors.append(
                    f"A22 same-source: {x.upper()}/{leg} = {got:,.0f} but "
                    f"{TIER_YEAR[x]} reported {want:,.0f}"
                )

    # --- FY2025 bridge: does leg-ownership reproduce reported attributable? --
    bridge = sum(attributable_np(
        FY25["res_ref"], FY25["res_poly"], FY25["res_sil"], FY25["res_oth"],
        FY25["tax"], inp["own_poly"], inp["own_sil"], inp["own_oth"],
    ))
    bridge_err = bridge / FY25["attributable"] - 1.0
    if abs(bridge_err) > OWNERSHIP_BRIDGE_TOL:
        errors.append(
            f"FY2025 bridge {bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
            f"({bridge_err:+.2%}) exceeds {OWNERSHIP_BRIDGE_TOL:.0%}"
        )

    # --- scenarios ----------------------------------------------------------
    scale = inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)  # RMB'000 -> HKD/share
    cash_ps = c_ex * inp["cash_attrib"] * scale
    # After-tax attributable interest on the listed cash, removed from every tier's
    # numerator by the same amount (A11).  No segment attribution is disclosed;
    # it is capitalised at the refrigerant leg's g = 0 multiple 1/r.
    inc_attrib = c_ex * inp["cash_yield"] * cash_after_tax * inp["cash_attrib"]

    def res_oth_of(x: str) -> float:
        """By-product leg (A8): dichloromethane + recurring other ops + impairment."""
        return inp[f"dcm_{x}"] + inp["oth_recur"] + inp[f"oth_imp_{x}"] + inp["nonseg"]

    def scenario(x: str, upt: float, pe: dict[str, float], s: float = 1.0) -> dict[str, float]:
        """Tier x with refrigerant unit result `upt` and multiples `pe`; every leg's
        attributable profit scaled by `s` (H only: pro rata onto consensus, A5)."""
        res_ref = inp["quota_t"] * upt / 1000.0
        res_oth = res_oth_of(x)
        np_legs = tuple(s * n for n in attributable_np(
            res_ref, inp[f"res_poly_{x}"], inp[f"res_sil_{x}"], res_oth,
            inp["tax"], inp["own_poly"], inp["own_sil"], inp["own_oth"],
        ))
        ps = {leg: n * pe[leg] * scale for leg, n in zip(("ref", "poly", "sil", "oth"), np_legs)}
        ps["int"] = -inc_attrib * pe["ref"] * scale
        # Segment total excludes non-segment items, to compare with reported totals.
        seg_total = res_ref + inp[f"res_poly_{x}"] + inp[f"res_sil_{x}"] + inp[f"dcm_{x}"] \
            + inp["oth_recur"] + inp[f"oth_imp_{x}"]
        return {
            "res_ref": res_ref, "seg_total": seg_total, "np": sum(np_legs),
            "np_op": sum(np_legs) - inc_attrib,
            **ps, "cash": cash_ps, "value": sum(ps.values()) + cash_ps,
        }

    # H = FY2027E consensus high (A5): scale the H-world leg mix pro rata.
    hworld = scenario("h", inp["upt_h"], gen)
    eps_hworld = hworld["np"] * scale
    s_h = inp["eps_2027_h"] / eps_hworld
    scale_of = {"l": 1.0, "m": 1.0, "h": s_h}
    tiers = {x: scenario(x, inp[f"upt_{x}"], gen, scale_of[x]) for x in "lmh"}
    if not inp["eps_2027_l"] < inp["eps_2027_m"] < inp["eps_2027_h"]:
        errors.append("eps_2027 l/m/h not ascending")
    if s_h < 1.0:
        errors.append(f"H scale {s_h:.4f} < 1: consensus high below the H-world run-rate")

    # Time alignment (valuation-rules「经营价值与超额现金」③): only H has a forward numerator year
    # (FY2027E consensus high) -> its legs are values at 2027-01-01, x (1+r)^-tau, plus the 2H26
    # window distributable profit on the same (consensus-high) basis x (1+r)^-(tau/2).  L / M are
    # named price scenarios + actual operating years (not calendar-drifting) -> not aligned.
    eps_h1 = inp["ni_h1_2026"] * scale
    int_ps = inc_attrib * scale

    def value_of(x: str, t: dict[str, float], pe: dict[str, float], r_: float) -> tuple[float, float]:
        if x != "h":
            return t["value"], 0.0
        np_poly = t["poly"] / pe["poly"] / scale
        b = inp["g2_poly"] / roe_poly * np_poly / t["np"]
        win = max(0.0, inp["eps_2026_h"] - eps_h1 - int_ps / 2) * (1.0 - b)
        legs = t["value"] - t["cash"]
        return legs * (1.0 + r_) ** -inp["tau"] + win * (1.0 + r_) ** -(inp["tau"] / 2) + t["cash"], win

    for x in "lmh":
        tiers[x]["value"], tiers[x]["win"] = value_of(x, tiers[x], gen, r)
    L, M, H = (tiers[x]["value"] for x in "lmh")
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")

    # --- A22 perfect-correlation guard --------------------------------------
    if tiers["l"]["seg_total"] < FY23_SEGMENT_TOTAL:
        errors.append(
            f"A22 guard: L-tier segment total {tiers['l']['seg_total']:,.0f} < FY2023 actual "
            f"{FY23_SEGMENT_TOTAL:,.0f} — the L tier has drifted toward the "
            f"legwise-minimum world (sum {LEGWISE_MIN_SUM:,.0f}) that never happened"
        )

    # --- floor: disclosed only (A16) ------------------------------------------
    floor = inp["pb_floor"] * inp["bvps_cny"] * inp["fx_cny_hkd"]

    eps = {x: tiers[x]["np"] * scale for x in "lmh"}
    # ②-b: farthest band-consensus year mean must sit in [EPS_M, EPS_H].
    if not eps["m"] <= inp["eps_2027_m"] <= eps["h"] + 1e-9:
        errors.append(f"②-b: consensus FY2027E mean {inp['eps_2027_m']} outside [EPS_M {eps['m']:.3f}, EPS_H {eps['h']:.3f}]")

    # The consensus-2027E candidate band was upgraded into H (A5) and must be gone.
    meta = load_framework(FRAMEWORK)
    if meta.candidate is not None:
        errors.append("候选带 line still in Outputs — consensus FY2027E is now the H numerator (A5)")

    # --- V_opt (A25): one snapshot share of today's fluoropolymer leg -------------
    if abs(inp["opt_rev"] - 2 * POLY_26H1["revenue"]) > 1.0:
        errors.append(f"opt_rev {inp['opt_rev']:,.0f} != 26H1 fluoropolymer revenue x 2")
    if abs(inp["opt_margin"] - POLY_26H1["result"] / POLY_26H1["revenue"]) > 0.0005:
        errors.append(f"opt_margin {inp['opt_margin']} != 26H1 fluoropolymer segment margin")
    if inp["t_opt"] <= inp["t_num"]:
        errors.append("t_opt must be after t_num")
    opt_np = inp["opt_rev"] * inp["opt_margin"] * inp["own_poly"] * (1.0 - inp["tax"])
    v_at_t = opt_np * gen["poly"] * scale
    # Unspent capital (valuation-rules「未建模期权」2026-10-04): budget - spent,
    # attributable via own_poly, spread evenly over y0..y1, discounted to t_num.
    k_remain = inp["opt_k"] - inp["opt_k_spent"]
    if k_remain < 0:
        errors.append(f"opt_k_spent {inp['opt_k_spent']:,.0f} > budget opt_k {inp['opt_k']:,.0f}")
    k_years = range(int(inp["opt_k_y0"]), int(inp["opt_k_y1"]) + 1)
    if not k_years or k_years[-1] >= inp["t_opt"]:
        errors.append("opt_k_y0..opt_k_y1 must be non-empty and end before t_opt")
    k_df = sum((1.0 + r) ** -(y - inp["t_num"]) for y in k_years) / max(len(k_years), 1)
    k_pv = k_remain * inp["own_poly"] * k_df * scale  # HKD/share at t_num
    v_gross = v_at_t / (1.0 + r) ** (inp["t_opt"] - inp["t_num"])
    # The option is valued at the numerator year (t_num) -> same tau as H (time alignment); its
    # multiple is the fluoropolymer leg's three-stage pe_poly (option legs take the same path).
    v_opt = (v_gross - k_pv) * (1.0 + r) ** -inp["tau"]

    # --- compare against the stated Outputs ---------------------------------
    out_sec = outputs_section(md)
    triples = re.findall(r"L = \*\*[0-9.]+\*\* · M = \*\*[0-9.]+\*\* · H = \*\*[0-9.]+\*\*", out_sec)
    if len(triples) != 1:
        errors.append(f"### Outputs must state the L/M/H triple exactly once, found {len(triples)}")
    if meta.v_opt is None:
        errors.append("V_opt must be stated in Outputs (PTFE-AI option, §1)")
    elif abs(meta.v_opt - v_opt) > TOL:
        errors.append(f"V_opt stated {meta.v_opt} vs recomputed {v_opt:.4f}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"超额现金(保留原结构): net_cash {inp['net_cash'] / YI:.2f}亿 − 已宣派未付股息 {inp['div_declared'] / YI:.2f}亿 "
          f"= C_ex {c_ex / YI:.2f}亿 x 归母 {inp['cash_attrib']} = {c_ex * inp['cash_attrib'] / YI:.2f}亿 = {cash_ps:.3f} HKD/股 "
          f"(占归母权益 {c_ex * inp['cash_attrib'] / (inp['bvps_cny'] * inp['shares'] / 1000):.1%}); "
          f"税后归母利息 {c_ex:,.0f}k x {inp['cash_yield']:.4%} x (1−{inp['tax_eff']}) x {inp['cash_attrib']} = "
          f"{inc_attrib:,.0f}k -> x pe_ref = −{inc_attrib * gen['ref'] * scale:.3f} HKD/股 三档同扣")
    print(f"RONIC_poly: 东岳高分子 ({inp['np_poly_fy25']:,.0f} − 现金利息 {inc_poly:,.0f}) ÷ ({inp['equity_poly_avg']:,.0f} − 分摊现金 "
          f"{cash_poly:,.0f}) = {roe_poly:.4f} (账面 {roe_poly_book:.4f}; 现金按权益份额 "
          f"{inp['equity_poly_avg'] / inp['equity_grp_avg']:.2%} 分摊集团 FY2025 平均现金)")
    print(f"basket: r_perp={r} 篮 {baskets.get('r_perp')} (all four legs) | RONIC_poly {roe_poly:.4f} ROE_sil {roe_sil:.4f} | "
          + " ".join(f"{leg}: g2 {inp[f'g2_{leg}']:+.4f} -> {gen[leg]:.2f}x (stated {inp[f'pe_{leg}']:g})" for leg in gen))
    alt_poly = perpetual_pe(0.0376, roe_poly, r)
    print(f"  sens g2_poly=0.0376 (A-share cross-section median, cross-market): poly {alt_poly:.2f}x")
    print(f"tiers: refrigerant = price scenarios (A4); other legs L={TIER_YEAR['l']} M={TIER_YEAR['m']} H={TIER_YEAR['h']} (A22 same-source OK)")
    print(f"bridge: k={inp['bridge_k']} = mean(" + ", ".join(f"{y} {v:.4f}" for y, v in calib_ratio.items()) + ")")
    for y, (px, unit) in {**BRIDGE_CALIB, **BRIDGE_REGIME_BREAK}.items():
        est = bridge_unit(px_of(*px), inp["bridge_k"])
        tag = "regime break, not asserted" if y in BRIDGE_REGIME_BREAK else f"within ±{BRIDGE_REPRO_TOL:.0%}"
        print(f"  reproduce {y}: {est:,.0f} vs reported {unit:,.0f} ({est / unit - 1:+.1%}, {tag})")
    for x in "lmh":
        px = tier_px(x)
        print(f"  {x.upper()}: R32 {px['r32']:,.0f} / R125 {px['r125']:,.0f} / R134a {px['r134a']:,.0f} / R22 {px['r22']:,.0f}"
              f" -> upt {bridge_unit(px, inp['bridge_k']):,.0f} 元/吨 (stated {inp[f'upt_{x}']:,.0f})")
    print(f"own poly={inp['own_poly']:.4f} sil={inp['own_sil']:.4f} oth={inp['own_oth']:.2f}"
          f"  tax={inp['tax']:.0%}  quota_t={inp['quota_t']:,.0f}")
    print(f"FY2025 ownership bridge={bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
          f"({bridge_err:+.2%}, tol {OWNERSHIP_BRIDGE_TOL:.0%})")
    print(f"pe FLAT: ref={inp['pe_ref']:.2f} poly={inp['pe_poly']:.2f} sil={inp['pe_sil']:.2f} oth={inp['pe_oth']:.2f}"
          "  -> L/M/H below IS the flat-multiple ladder (A2e-2c); multiple ratio = 1.00")
    print(f"res_oth(亿CNY)={res_oth_of('l') / YI:.2f}/{res_oth_of('m') / YI:.2f}/{res_oth_of('h') / YI:.2f}"
          "  [non-monotonic by design, A8]")
    print("segment total(亿CNY)=" + "/".join(f"{tiers[x]['seg_total'] / YI:.2f}" for x in "lmh")
          + f"  guard: L >= FY2023 actual {FY23_SEGMENT_TOTAL / YI:.2f}亿 OK")
    print("res_ref(亿CNY)=" + "/".join(f"{tiers[x]['res_ref'] / YI:.2f}" for x in "lmh")
          + "  attribNP(亿CNY)=" + "/".join(f"{tiers[x]['np'] / YI:.2f}" for x in "lmh"))
    print(f"H = consensus FY2027E high {inp['eps_2027_h']} (mean {inp['eps_2027_m']}, low {inp['eps_2027_l']}): "
          f"H-world EPS {eps_hworld:.3f} (value {hworld['value']:.2f}) x scale {s_h:.4f}; "
          f"M vs consensus mean {inp['eps_2027_m'] / eps['m'] - 1:+.1%} (cyclical 中枢, A5 trigger)")
    print("attribEPS(HKD)=" + "/".join(f"{eps[x]:.3f}" for x in "lmh"))
    for x in "lmh":
        t = tiers[x]
        print(f"表1 {x.upper()}: 制冷剂={t['ref']:.2f} 高分子={t['poly']:.2f} 有机硅={t['sil']:.2f}"
              f" 副产品={t['oth']:.2f} 剔现金利息={t['int']:.2f} 净现金={t['cash']:.2f} 合计={t['value']:.2f}")
    print(f"V={L:.2f}/{M:.2f}/{H:.2f}  attrib cash line/share={cash_ps:.2f}")
    eps_op = {x: tiers[x]["np_op"] * scale for x in "lmh"}
    print("operating EPS(HKD, ex cash interest)=" + "/".join(f"{eps_op[x]:.3f}" for x in "lmh"))
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × bvps × fx, disclosed only, A16)  scenario_L={L:.2f}"
          f"  floor vs band: {zone_of(floor, L, M, H)}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"ratios: L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          "   [cyclical cohort L/M median 0.71, repo H/M median 1.25]")
    # Disclosure rows (Outputs): ③ 出带, sensitivity, candidate, option.
    print("implied PE incl cash: " + "/".join(f"{tiers[x]['value'] / eps[x]:.2f}x" for x in "lmh")
          + "  operating (ex cash / ex interest): " + "/".join(f"{(tiers[x]['value'] - cash_ps) / eps_op[x]:.2f}x" for x in "lmh")
          + f"  vs own post-quota band min {OWN_PE_BAND_MIN} (whole-equity band, operating band 待补) -> "
          + ("③ 出带 (M/H below band min, disclosed)" if M / eps["m"] < OWN_PE_BAND_MIN else "in band"))
    for label, r_alt in (("r +50bp", r + 0.005), ("r -50bp", r - 0.005), ("篮 7 15%", 0.15), ("篮 4 10%", 0.10)):
        pe_alt = gordon(r_alt)
        band = [value_of(x, scenario(x, inp[f"upt_{x}"], pe_alt, scale_of[x]), pe_alt, r_alt)[0] for x in "lmh"]
        print(f"  sens {label}: {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f}")
    pe_book = {**gen, "poly": path_pe(inp["g2_poly"], roe_poly_book, r, int(inp["t_num"]), int(inp["y1_poly"]),
                                      int(inp["y2_poly"]), max(inp["rs_poly"], r))}
    band = [value_of(x, scenario(x, inp[f"upt_{x}"], pe_book, scale_of[x]), pe_book, r)[0] for x in "lmh"]
    print(f"  sens RONIC_poly 账面 {roe_poly_book:.1%} (现金不分摊): {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f}")
    d_full = inp["div_declared"] * (1.0 - inp["cash_attrib"]) * scale
    print(f"  sens 已宣派股息全额由归母承担（不乘归母比例）: −{d_full:.2f} -> {L - d_full:.2f}/{M - d_full:.2f}/{H - d_full:.2f}")
    fy24_px, fy24_unit = BRIDGE_REGIME_BREAK["FY2024"]
    print(f"deep_discount pressure coordinate (FY2024 actual unit {fy24_unit:,.0f}, other legs FY2024): "
          f"{scenario('l', fy24_unit, gen)['value']:.2f}")
    print(f"V_opt: {inp['opt_rev']:,.0f}k x {inp['opt_margin']:.4f} = {inp['opt_rev'] * inp['opt_margin']:,.0f}k segment result"
          f" -> attrib {opt_np:,.0f}k x pe_poly {gen['poly']:.3f} = {v_at_t:.3f} HKD @ {inp['t_opt']:.0f}"
          f" / {1 + r}^{inp['t_opt'] - inp['t_num']:.0f} = {v_gross:.3f}")
    print(f"  less unspent capital: ({inp['opt_k']:,.0f}k - spent {inp['opt_k_spent']:,.0f}k) x own_poly {inp['own_poly']}"
          f" x mean DF {k_df:.4f} ({inp['opt_k_y0']:.0f}-{inp['opt_k_y1']:.0f} @ r to {inp['t_num']:.0f}) = {k_pv:.3f} HKD"
          f" -> V_opt {v_opt:.3f} (gross {v_gross:.3f}, V_opt/M {v_opt / M:.1%})")
    tf = (1.0 + r) ** -inp["tau"]
    for t_alt in (inp["t_opt"] - 1, inp["t_opt"] + 1):
        print(f"  sens t_opt {t_alt:.0f}: V_opt {(v_at_t / (1.0 + r) ** (t_alt - inp['t_num']) - k_pv) * tf:.2f}")
    print(f"  sens capital at t_opt in one lump (optimistic): V_opt "
          f"{(v_gross - k_remain * inp['own_poly'] * scale / (1.0 + r) ** (inp['t_opt'] - inp['t_num'])) * tf:.2f}")
    print(f"  H window distributable profit {tiers['h']['win']:.4f} HKD/sh x (1+r)^-{inp['tau'] / 2:g}; "
          f"H legs x (1+r)^-{inp['tau']:g}")
    if meta.v_opt is not None and meta.p_tiers:
        print(f"V_opt={meta.v_opt:.2f} (not in deck) p_tiers={meta.p_tiers}  zone+V: "
              + "/".join(f"{b + p * meta.v_opt:.2f}" for b, p in zip((L, M, H), meta.p_tiers)))
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # the one basket r all four legs share 1:1; price scenarios, g2, ROE, ownership
    # and fx stay put.  Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        pe_rf = gordon(r + dr)
        return tuple(value_of(x, scenario(x, inp[f"upt_{x}"], pe_rf, scale_of[x]), pe_rf, r + dr)[0] for x in "lmh")

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # Only a clean run feeds the daily digest.
    write_rf_readings("0189.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
