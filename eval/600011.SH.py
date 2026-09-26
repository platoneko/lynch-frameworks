#!/usr/bin/env python3
"""600011.SH (Huaneng Power International) valuation eval.

frameworks/600011.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price, A or H (AGENTS.md「现价 — 禁写契约」), so nothing here
computes a zone, a live H/A or a market-implied reading — the digest and the
app zone on live quotes.

formula_id: huaneng_forward_consensus_mid_pe_v6

Main ruler: whole-company PE on a FORWARD-CONSENSUS mid-cycle numerator.

    L = FY2023 realised world  (fuel 326.43 元/MWh, coal leg 4.33亿 ≈ 0)   EPS 0.3500
    M = FY2026 consensus mean  (11 houses; blended fuel ≈ coal-axis M 282,   EPS 0.562   <- 中枢
                                tariff 463, today's asset base; ROE 13.7%)
    H = FY2025 realised peak   (fuel 266.88, the cheap-coal end)             EPS 0.7400

all on the ordinary-shareholder basic EPS the annual reports print (A2).

Why the mid-cycle numerator is a consensus year and not the FY2024 print
(v5): the 2026H1 ROE decline decomposes into tariff (485 -> 463 元/MWh,
≈ -44亿), volume (-3%, ≈ -14亿) and a fuel TAILWIND (+12亿) — a structural
tariff step-down, not the coal cycle.  On the new tariff regime the FY2024
print (0.4594, printed on the 2024 asset base) sits next to the trough-year
reading (quarterly consensus sum 0.48), and a cyclical's mid-cycle numerator
must not sit on the trough.  FY2026's coal deck (800) cross-checks the coal
axis M (830), so the consensus is "mid-cycle coal + today's tariff + today's
asset base" (A5 / A19 / A22).

The multiple is GENERATED, r from the basket table (`gordon.BASKET_R`): the
whole company is 篮 4 龙头制造, r = 10%, cross-market fixed (方案 A).  g2 = 0:
its source is the MARGINAL RETURN ON GROWTH CAPEX the annual reports let us
compute — wind + solar capex 2024-25 of 833亿, capacity +60%, segment PBT
+5.3亿 → 0.64% pre-tax, far below the 5% threshold for a positive g2; the
tariff trend is negative and volume is losing share (A15).  Retention exists
(payout 54%) but buys no per-share growth, so g2 = 0 is the retention branch
with non-growth retention (§4.0; precedent 600111.SH).  b x ROE_M (6.3%) is
printed as the book upper bound the annual reports contradict.  Hence

    PE = (1 - g2/ROE_M) / (r - g2) = 1/r = 10.0x, flat for all tiers.

L's scenario value (0.35 x 10 = 3.50) sits below the FY2020 realised PB low
(1.04 x BPS = 4.27), so the A-share L is floored (A2e-1; both values printed).
On the H-share companion band (same r, southbound dividend-tax numerator
discount k = 1 - 20% x payout) the floor is disclosure only — it is a PB
observation printed on A-share prices.

A dividend-ruler PRESSURE line D_M / r = 3.03 is printed (not a deck value):
the world in which retention keeps earning 0.6% and only the payout is worth
anything.  The skill's dividend-ruler exception is checked and reported as
"not triggered, on the line" (ROE_M is 0.7pp above r + 3pp).

Guards: numerator ladder + consensus pin, coal-axis cross-check, basket r,
g cap, shared g2, marginal-return source rule, payout consistency, ROE domain
window (A22), own-band guardrail, flat-multiple ladder, dividend-ruler g under
the book bound + 3pp, floor recheck ratio, southbound mount contract, perp leverage and TTM anchoring on the run-rate cross band,
reference rows kept out of the formula, band-edge reverse-solve, A20 bridge
reproduction, stated-vs-recomputed anchors.

Run:  python3 frameworks/eval/600011.SH.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.frameworks import load_framework  # noqa: E402
from lib.gordon import (  # noqa: E402
    BASKET_R, annuity_factor, basket_r, check_g_cap, check_r, g_cap, implied_g, implied_g_retaining, payout_gap,
    perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report, reverse_ladder,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600011.SH.md"
FORMULA_ID = "huaneng_forward_consensus_mid_pe_v6"

TIERS = ("l", "m", "h")
PERP_LEVERAGE = 1.240       # 归母 / 普通股股东, TTM (cross band)
FLOOR_RECHECK_RATIO = 0.30  # A2e-1: below this the earnings ruler has failed at L
EPS_ANCHOR_TOL = 0.002      # A6: k_retain is calibrated so the cross-band M reproduces the TTM
BOOK_G_TOL = 0.03           # A17: the yield-implied g may sit this far above the book bound
PAYOUT_TOL = 0.002          # A15: stated payout vs dps x shares / ni_fy25
G2_TOL = 5e-5               # A15: g_policy_m vs (1 - payout) x ROE_M
EPS_TIER_TOL = 5e-4         # A5: eps tiers vs their source rows
MIDCYCLE_RATIO = 1.15       # 「周期票的中枢分子」: above this a print is a coordinate, not M
CONSENSUS_GAP = 0.20        # ②-b: M more than this below the FY+1 consensus mean would be a problem
LADDER_MEAN_TOL = 0.05      # A19: stated fuel_mid vs the recomputed 7-year mean
DECK_CROSS_TOL = 0.20       # A19: deck-mapped fuel cost vs the coal-axis M mapping must agree within this
PASS_THROUGH = 0.60         # A19: realised 2024->2025 QHD -18.4% <-> unit fuel cost -11.13%
QHD_FY24 = 703.0 / (1 - 0.184)
CHAIN_TOL = 0.05            # 校验步骤 7 / 17: FY2024 re-derived through the chain / the bridge vs realised
ROE_M_WINDOW = (0.13, 0.16)  # A22: the mid-cycle ROE judgement holds inside this window
DDM_EXCEPTION_MARGIN = 0.03  # valuation-rules DDM exception (b): 中枢 ROE <= r + 3pp
DDM_EXCEPTION_PAYOUT = 0.40  # ... and payout >= 40%
G2_V5 = 0.02                # v5: the sourceless "inflation tier", printed as a 对照
PE_M_V5 = 10.264            # v5: PE_M at ROE 11.18% / g2 2%
PE_H_V5 = 13.833            # v5: consensus-window multiple
EPS_M_V5 = 0.4594           # v5: FY2024 print as 中枢
G2_OLD_BRANCH = -0.0153     # v3: peer 100%-payout reading, printed as the wrong-branch coordinate
PE_V4 = 11.284              # v4: flat multiple, for the peak-numerator 对照带
GUIMU_GAP = 0.1417          # 属性 C: 归母 EPS minus ordinary-shareholder EPS (FY2025), coordinate only
# Seven-year ordinary-shareholder EPS path (annual reports; Longbridge IS `af` 每股收益).
# Printed with its mean and flagged regime-broken: two loss years make the
# cross-cycle mean meaningless (A19).
EPS_PATH = {2019: 0.0561, 2020: 0.1780, 2021: -0.7736, 2022: -0.6102, 2023: 0.3500, 2024: 0.4594, 2025: 0.7400}
LADDER_YEARS = (2019, 2020, 2021, 2022, 2023, 2024, 2025)
TARIFF_7Y_MEAN = statistics.mean((417.00, 413.63, 432.0, 509.92, 508.74, 494.26, 477.08))  # A20 coordinate only
# 2026H1 ROE-decline decomposition (interim reports; 属性 A / A22).  Printed, not asserted.
H1_TARIFF = (485.27, 463.02)          # 元/MWh, 2025H1 -> 2026H1
H1_VOLUME = (2056.83, 1995.78)        # 亿 kWh
H1_STD_COAL = (917.05, 891.02)        # 元/吨 standard coal
H1_STD_COAL_TONS = 4750.0             # 万吨 ≈ 1,650 亿 kWh coal output x 287.79 g/kWh (estimate)
H1_COAL_SPREAD = 228.0                # 元/MWh ≈ tariff - fuel, for the volume effect (estimate)
H1_SIX_LEG = (138.18, 113.50)         # 亿, six-leg PBT
H1_PBT = (147.62, 114.56)             # 亿, group PBT
H1_ORDINARY_NI = (78.48, 54.74)       # 亿, attributable to ordinary shareholders
RENEWABLE_H1_PBT = (57.33, 43.87)     # 亿, wind + solar PBT 2025H1 / 2026H1

REQUIRED = [
    "hkdcny", "shares", "bps", "equity",
    "eps_l", "eps_m", "eps_h", "eps_fy23", "eps_fy24", "eps_fy25", "eps_ttm", "eps_fy26_q",
    *[f"fuel_fy{y % 100}" for y in LADDER_YEARS], "fuel_mid", "fuel_axis_m",
    "qhd_fy25", "qhd_deck26", "lt_contract_mean",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_now", "coal_vol",
    "pbt_fy23", "pbt_fy24", "pbt_l", "pbt_m", "pbt_h", "k_retain", "perp",
    "r_perp", "r_perp_hkd", "cny_rf_gap", "hk_div_tax",
    "re_capex_fy24", "re_capex_fy25", "re_pbt_fy23", "re_pbt_fy25", "re_cap_fy23", "re_cap_fy25", "g_marginal_min",
    "re_capex_plan26", "fin_cost_h1", "re_assets_est", "tax_rate",
    "capex_fy25", "da_fy25", "debt_ib",
    "ni_fy25", "g2_l", "g2_m", "g2_h", "g_policy_m",
    "g_peer_min", "g_peer_max", "g_peer_cross",
    "pe_own_min", "pe_own_max", "pe_hk_own_mid",
    "payout", "req_yield_a", "req_yield_h", "bond10y",
    "dps", "perp_balance", "pb_lo", "pbt_h1x2",
    "cons_fy26_mean", "cons_fy26_lo", "cons_fy26_hi",
    "cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi",
    "eps_hk_fy27_lo", "eps_hk_fy27_hi",
]
# Reference-only rows: they must never enter a base-deck anchor (校验步骤 13).
NOT_FORMULA = (
    "pe_hk_own_mid", "pbt_h1x2", "bond10y", "req_yield_h",
    "pbt_l", "pbt_m", "pbt_h", "pbt_fy23", "pbt_fy24", "eps_hk_fy27_lo", "eps_hk_fy27_hi",
    "g_peer_min", "g_peer_max", "g_peer_cross", "g_policy_m",
    "cons_fy26_lo", "cons_fy26_hi", "cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi",
    "eps_ttm", "eps_fy24", "eps_fy26_q",
    "qhd_fy25", "qhd_deck26", "lt_contract_mean", "fuel_mid", "fuel_axis_m",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_now", "coal_vol",
    "cny_rf_gap", "capex_fy25", "da_fy25", "debt_ib",
    "re_capex_fy24", "re_capex_fy25", "re_pbt_fy23", "re_pbt_fy25", "re_cap_fy23", "re_cap_fy25", "g_marginal_min",
    "re_capex_plan26", "fin_cost_h1", "re_assets_est", "tax_rate",
)
CROSS_TOL = 0.05  # A18: recomputed run-rate cross band vs the Outputs line
_CROSS_LINE = re.compile(r"实测运行率交叉带.*?\*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*")


def eps_of(inp: dict[str, float], pbt: float) -> float:
    """PBT -> ordinary-shareholder EPS (cross band / chain coordinates).  perp is subtracted, never scaled."""
    return (pbt * inp["k_retain"] - inp["perp"]) / inp["shares"]


def bridge_eps(inp: dict[str, float], fuel: float, tariff: float) -> tuple[float, float]:
    """A20 linear spread bridge from the FY2025 six-leg base: (six-leg PBT, EPS).  Coordinates only."""
    base_spread = inp["tariff_fy25"] - inp["fuel_fy25"]
    six = inp["pbt_h"] + ((tariff - fuel) - base_spread) * inp["coal_vol"]
    return six, eps_of(inp, six)


def window_pe_v5(g1: float, n: int, pe_tail: float, r: float) -> float:
    """v5's consensus-window multiple, kept only to print the v5 对照带."""
    return annuity_factor(g1, r, n) + (1.0 + g1) ** n * pe_tail / (1.0 + r) ** n


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker is declared on the axis and reports
    both the A-share band and the H-share companion band.  The southbound axis
    locks no numerator and no multiple for this ticker (Gordon generates it,
    A13), so the reporting contract is the only thing left to enforce.  The
    live H/A is a function of today's two prices and no longer lives in the
    doc; the axis's cross-ticker direction check reads its own dated series."""
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "600011.SH" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append(
            "600011.SH is not declared on _AXIS.southbound-repricing.md — "
            "a mount has to exist on both sides"
        )
    if "H 股平行价带" not in md:
        errors.append("framework lacks the H-share companion band (axis §3 rule 3)")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    r = inp["r_perp"]

    # --- Step 1: numerators — realised L / H off the coal ladder, M = forward consensus
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    errors += ladder("eps (L realised / M consensus / H realised)", eps["l"], eps["m"], eps["h"])
    for t, key in (("l", "eps_fy23"), ("m", "cons_fy26_mean"), ("h", "eps_fy25")):
        if abs(eps[t] - inp[key]) > EPS_TIER_TOL:
            errors.append(f"eps_{t} {eps[t]} != {key} {inp[key]} — tiers are pinned to their source rows (A4/A5)")
    if inp["fuel_fy23"] <= inp["fuel_fy25"]:
        errors.append("coal ladder: L (FY2023) must be the dearer coal, H (FY2025) the cheaper (A1/A4)")
    if eps["h"] > inp["cons_fy27_hi"] + 1e-9:
        errors.append(f"eps_h {eps['h']} exceeds the consensus upper {inp['cons_fy27_hi']} (A5)")
    # 「周期票的中枢分子」: anything > 1.15 x 中枢 is a coordinate (or H), never M.
    ratios = {"TTM": inp["eps_ttm"] / eps["m"], "FY27 均值": inp["cons_fy27_mean"] / eps["m"], "FY2025": eps["h"] / eps["m"]}
    # Coal-axis cross-check (A19): the consensus year's coal deck maps onto the axis M.
    fuel = {y: inp[f"fuel_fy{y % 100}"] for y in LADDER_YEARS}
    fuel_mid = statistics.mean(fuel.values())
    if abs(fuel_mid - inp["fuel_mid"]) > LADDER_MEAN_TOL:
        errors.append(f"fuel_mid stated {inp['fuel_mid']} vs recomputed 7-year mean {fuel_mid:.2f} (A19)")
    fuel_deck = inp["fuel_fy25"] * (1 + PASS_THROUGH * (inp["qhd_deck26"] / inp["qhd_fy25"] - 1))
    if abs(fuel_deck / inp["fuel_axis_m"] - 1) > DECK_CROSS_TOL:
        errors.append(
            f"deck-mapped fuel cost {fuel_deck:.1f} is >{DECK_CROSS_TOL:.0%} from the coal-axis M mapping "
            f"{inp['fuel_axis_m']} — the consensus year is not on mid-cycle coal; back to the conversation (A19)"
        )
    # ②-b on M (A11): the FY+1 consensus mean sits inside [M, H] and M is not >20% under it.
    cons_in_band = eps["m"] <= inp["cons_fy27_mean"] <= eps["h"]
    cons_gap = eps["m"] / inp["cons_fy27_mean"] - 1
    if not cons_in_band:
        errors.append(f"FY2027 consensus mean {inp['cons_fy27_mean']} outside [M {eps['m']}, H {eps['h']}] (A11 ②-b)")
    if cons_gap < -CONSENSUS_GAP:
        errors.append(f"M sits {cons_gap:.1%} under the FY2027 consensus mean (>{CONSENSUS_GAP:.0%}) (A11 ②-b)")
    # Cross band (A18): the measured six-leg run-rates on the same ruler.
    eps_run = {t: eps_of(inp, inp[f"pbt_{t}"]) for t in TIERS}
    errors += ladder("pbt (cross band)", inp["pbt_l"], inp["pbt_m"], inp["pbt_h"])
    # A6: k_retain exists to make the cross-band M reproduce the realised TTM.
    if abs(eps_run["m"] - inp["eps_ttm"]) > EPS_ANCHOR_TOL:
        errors.append(
            f"cross-band M numerator {eps_run['m']:.4f} no longer reproduces realised TTM EPS "
            f"{inp['eps_ttm']} — recalibrate k_retain (A6)"
        )
    if errors:
        return report(errors, "FAIL (numerators)")

    # --- Step 2: basket r, tier ROE, ROE domain, g2 source, then the multiple
    roe = {t: eps[t] * inp["shares"] / inp["equity"] for t in TIERS}
    g2 = inp["g2_m"]
    for key in ("r_perp", "r_perp_hkd"):
        if key not in baskets:
            errors.append(f"{key}: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[key], key, baskets.get(key))
    if abs(inp["r_perp_hkd"] - r) > 1e-9:
        errors.append(f"r_perp_hkd {inp['r_perp_hkd']} != r_perp {r} — basket r is cross-market fixed (方案 A, A21)")
    r_ccy = r - inp["cny_rf_gap"]  # CNY r_f segment reading: disclosure only, never an r row
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], r, f"g2_{t}")
    if not (inp["g2_l"] == inp["g2_m"] == inp["g2_h"]):
        errors.append(f"g2 tiers {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} must be one shared value (A8 flat)")
    # A22: the mid-cycle ROE judgement (forward consensus between trough and peak) holds
    # only inside this window; outside it the domain and the g2 source are re-decided.
    if not (ROE_M_WINDOW[0] <= roe["m"] <= ROE_M_WINDOW[1]):
        errors.append(
            f"ROE_M {roe['m']:.2%} outside the mid-cycle window [{ROE_M_WINDOW[0]:.0%}, {ROE_M_WINDOW[1]:.0%}] — "
            "re-decide the 中枢 and the g2 source (A22)"
        )
    # Branch sign is pinned by the payout actually paid (A15): 54% < 80% retains.
    payout_fy25 = inp["dps"] * inp["shares"] / inp["ni_fy25"]
    if abs(payout_fy25 - inp["payout"]) > PAYOUT_TOL:
        errors.append(f"payout {inp['payout']} vs dps x shares / ni_fy25 = {payout_fy25:.4f} (A15)")
    # g2 SOURCE (A15): the marginal pre-tax return on growth capex the annual
    # reports let us compute.  Below the threshold, retention is non-growth and
    # g2 must be 0; at or above it the source has to be re-decided (a conversation).
    re_capex = inp["re_capex_fy24"] + inp["re_capex_fy25"]
    marginal_return = (inp["re_pbt_fy25"] - inp["re_pbt_fy23"]) / re_capex
    if inp["re_cap_fy25"] <= inp["re_cap_fy23"]:
        errors.append("renewable capacity did not grow FY2023 -> FY2025 — the marginal-return reading is meaningless (A15)")
    if marginal_return < inp["g_marginal_min"] and g2 != 0:
        errors.append(
            f"marginal pre-tax return on growth capex {marginal_return:.2%} < threshold {inp['g_marginal_min']:.0%} "
            f"but g2 = {g2:+.2%} — retention buys no per-share growth; g2 must be 0 (A15)"
        )
    if marginal_return >= inp["g_marginal_min"]:
        errors.append(
            f"marginal pre-tax return on growth capex {marginal_return:.2%} >= threshold {inp['g_marginal_min']:.0%} — "
            "a positive g2 is now arguable; re-decide the source in conversation (A15)"
        )
    g_policy = (1 - inp["payout"]) * roe["m"]
    if abs(inp["g_policy_m"] - g_policy) > G2_TOL:
        errors.append(f"g_policy_m {inp['g_policy_m']} vs (1 - payout) x ROE_M = {g_policy:.5f} (A15)")
    if g2 > inp["g_policy_m"] + 1e-9:
        errors.append(f"g2_m {g2} exceeds the book upper bound b x ROE_M = {inp['g_policy_m']} (A15)")
    retained = inp["ni_fy25"] * (1 - inp["payout"])
    build_excess = inp["capex_fy25"] - inp["da_fy25"]
    if build_excess <= retained:
        errors.append(
            f"capex − D&A = {build_excess:.0f} 亿 no longer exceeds retained earnings {retained:.0f} 亿 — "
            "the debt-funded build-window reading behind A15 is gone; re-check the g2 source"
        )
    for key in ("g_peer_max", "g_peer_cross"):
        if abs(inp[key] - g2) < 1e-9:
            errors.append(f"{key} leaked into g2 — peer readings are an upper reference only (A15)")
    if errors:
        return report(errors, "FAIL (growth 口径)")
    # A8: g2 = 0 makes the Gordon multiple 1/r, independent of ROE — flat by construction.
    pe_flat = perpetual_pe(g2, roe["m"], r)
    pe = {t: pe_flat for t in TIERS}
    pe_tier = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    if max(pe_tier.values()) - min(pe_tier.values()) > 1e-9:
        errors.append(f"tier-ROE multiples {pe_tier} differ although g2 = 0 — the flat construction broke (A8)")
    # Guardrail (A12, Phase 3 §A6): the generated multiple must sit inside the
    # ticker's own realised band, or the ticker stops rather than widens it.
    if not (inp["pe_own_min"] <= pe_flat <= inp["pe_own_max"]):
        errors.append(
            f"guardrail: generated PE {pe_flat:.2f} outside realised band "
            f"[{inp['pe_own_min']}, {inp['pe_own_max']}] (A12) — STOP, do not force g"
        )
    if errors:
        return report(errors, "FAIL (guardrail)")

    floor = inp["pb_lo"] * inp["bps"]
    k_hk = 1.0 - inp["hk_div_tax"] * inp["payout"]  # southbound dividend-tax numerator discount (A13)

    def band_at(g: float, r_: float = r, k: float = 1.0, floored: bool = True) -> tuple[tuple[float, float, float], float]:
        """((L, M, H), scenario_L) in CNY, one flat multiple on all three numerators.
        The A-share L is floored (A4); the H-share band passes floored=False."""
        p = k * perpetual_pe(g, roe["m"], r_)
        scen_l, M, H = eps["l"] * p, eps["m"] * p, eps["h"] * p
        return (max(scen_l, floor) if floored else scen_l, M, H), scen_l

    (L, M, H), scenario_l = band_at(g2)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    # H 股 companion band: same basket r, dividend-tax discount k on the numerator,
    # floor disclosure only, quoted HKD.
    (hk_l_cny, hk_m_cny, hk_h_cny), _ = band_at(g2, k=k_hk, floored=False)
    hk = {"l": hk_l_cny / inp["hkdcny"], "m": hk_m_cny / inp["hkdcny"], "h": hk_h_cny / inp["hkdcny"]}
    A_h, B_h = cut_points(hk["l"], hk["m"], hk["h"])

    # --- Step 3: the 口径 decisions, re-derived ------------------------------
    # A2e-2c — flat-multiple ladder on the three numerators.
    flat_errs, flat = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe["m"])
    errors += flat_errs

    # A14 / A17 — dividend ruler is a cross-ruler: no parameter shared with
    # Gordon.  Its reverse-solved g must stay under the book bound (+3pp).
    div = {t: eps[t] * inp["payout"] / inp["req_yield_a"] for t in TIERS}
    pe_div = inp["payout"] / inp["req_yield_a"]
    g_div, g_div_ok = implied_g_retaining(pe_div, roe["m"], r)
    if g_div > inp["g_policy_m"] + BOOK_G_TOL:
        errors.append(
            f"dividend-ruler implied g {g_div:+.4f} above the book bound {inp['g_policy_m']} + {BOOK_G_TOL:.0%} — "
            "yield-based pricing has left the own band (A17)"
        )
    # A14 — the dividend-ruler pressure line and the skill's DDM exception (b).
    dps_m = eps["m"] * inp["payout"]
    ddm_pressure = dps_m / r
    ddm_exception = (inp["payout"] >= DDM_EXCEPTION_PAYOUT) and (roe["m"] <= r + DDM_EXCEPTION_MARGIN)

    # A4 — floor backstop: the scenario value must still be a live earnings ruler.
    if scenario_l / M <= FLOOR_RECHECK_RATIO:
        errors.append(
            f"scenario_L/M = {scenario_l / M:.3f} <= {FLOOR_RECHECK_RATIO} — the earnings ruler "
            "has failed at L; A2e-1 requires going back to the conversation"
        )

    errors += check_southbound_mount(md)

    # 校验步骤 6: the perp leverage on the cross band is a calibrated fact.
    leverage = (inp["pbt_m"] * inp["k_retain"]) / (inp["pbt_m"] * inp["k_retain"] - inp["perp"])
    if abs(leverage / PERP_LEVERAGE - 1.0) > 0.02:
        errors.append(
            f"perp leverage {leverage:.3f} drifted >2% from {PERP_LEVERAGE} — "
            "k_retain or perp moved without recalibration (校验步骤 6)"
        )

    # 校验步骤 7: the six-leg chain reproduces FY2024 (mutual proof) and visibly
    # fails FY2023 — which is why L is the realised EPS, not a chain value.
    chain = {2023: eps_of(inp, inp["pbt_fy23"]), 2024: eps_of(inp, inp["pbt_fy24"]), 2025: eps_of(inp, inp["pbt_h"])}
    if abs(chain[2024] / inp["eps_fy24"] - 1) > CHAIN_TOL:
        errors.append(f"six-leg chain for FY2024 {chain[2024]:.4f} is >{CHAIN_TOL:.0%} from the realised {inp['eps_fy24']} (A4/A18)")

    # 校验步骤 13: reference rows must not leak into the formula.  The anchors
    # above were built without them; this only guards the Inputs contract.
    leaked = [k for k in NOT_FORMULA if k not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    # 校验步骤 15 (A18): the run-rate cross band rides the same flat multiple
    # and must match the Outputs line; never a zone input.
    cross = tuple(eps_run[t] * pe["m"] for t in TIERS)
    errors += ladder("实测运行率交叉带", *cross)
    m_cross = _CROSS_LINE.search(md.split("### Outputs", 1)[-1])
    if m_cross is None:
        errors.append("实测运行率交叉带 line missing from Outputs (A18)")
    else:
        for lab, said, got in zip(TIERS, m_cross.groups(), cross):
            if abs(float(said) - got) > CROSS_TOL:
                errors.append(f"交叉带 {lab}: stated {said} vs recomputed {got:.4f}")
    if load_framework(FRAMEWORK).candidate is not None:
        errors.append("a 候选带 line is still present — no 待补 input remains that would justify one (A11)")

    # 校验步骤 16 (裁决顺序 ③, retention branch, mid-cycle ROE): the lower band
    # edge reverse-solves negative (unreachable); only the capped upper edge bounds g2.
    g_edge_lo, edge_lo_ok = implied_g_retaining(inp["pe_own_min"], roe["m"], r)
    g_edge_lo_full, _ = implied_g(inp["pe_own_min"], roe["m"], r)
    if edge_lo_ok and g_edge_lo > 0:
        errors.append(
            f"band lower edge {inp['pe_own_min']}x reverse-solves to a positive conditioned g {g_edge_lo:+.2%} — "
            "the regime statement in A12 no longer holds"
        )
    g_edge_hi_raw, _ = implied_g_retaining(inp["pe_own_max"], roe["m"], r)
    g_edge_hi = min(g_edge_hi_raw, g_cap(r))
    if not (0.0 <= g2 <= g_edge_hi):
        errors.append(f"g2 {g2:+.4f} outside [0, band-edge implied g {g_edge_hi:+.4f}] — guardrail would bind (裁决顺序 ③)")

    # 校验步骤 17 (A20): the linear spread bridge must reproduce FY2024 from the
    # FY2025 base, or the pressure coordinates it prints are stories.
    _, eps_bridge_24 = bridge_eps(inp, inp["fuel_fy24"], inp["tariff_fy24"])
    if abs(eps_bridge_24 / inp["eps_fy24"] - 1) > CHAIN_TOL:
        errors.append(f"A20 bridge at (fuel_fy24, tariff_fy24) gives {eps_bridge_24:.4f}, >{CHAIN_TOL:.0%} from eps_fy24 {inp['eps_fy24']}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"篮子: {' · '.join(f'{k} 篮 {v} {basket_r_label(v)}' for k, v in baskets.items())}; r = {r:.1%} 跨市场固定 (方案 A); "
          f"CNY 段披露 r = r_perp − cny_rf_gap = {r_ccy:.1%} (不进底牌); cap g2 ≤ {g_cap(r):.1%}")
    print(f"{'档':<3}{'世界':>10}{'燃料成本':>9}{'电价':>8}{'EPS':>9}{'÷中枢':>7}{'ROE':>8}{'g2':>7}{'PE':>7}"
          f"{'情景值':>8}{'A股':>8}{'H股':>8}{'红利尺':>8}")
    worlds = {"l": ("FY2023", inp["fuel_fy23"], inp["tariff_fy23"]), "m": ("FY2026E", inp["fuel_axis_m"], inp["tariff_now"]),
              "h": ("FY2025", inp["fuel_fy25"], inp["tariff_fy25"])}
    for t, anchor_a, scen in zip(TIERS, (L, M, H), (scenario_l, M, H)):
        yr, f, tf = worlds[t]
        print(f"{t.upper():<3}{yr:>10}{f:9.2f}{tf:8.2f}{eps[t]:9.4f}{eps[t] / eps['m']:7.2f}"
              f"{roe[t]:8.1%}{inp[f'g2_{t}']:+7.1%}{pe[t]:7.2f}{scen:8.2f}{anchor_a:8.2f}{hk[t]:8.2f}{div[t]:8.2f}")
    print(f"  (M = FY2026 共识均值 {inp['cons_fy26_mean']} [{inp['cons_fy26_lo']}, {inp['cons_fy26_hi']}], 混合燃料 ≈ 轴 M 映射 {inp['fuel_axis_m']}; "
          f"FY2024 印数 {inp['eps_fy24']} × PE = {inp['eps_fy24'] * pe_flat:.2f} 与季度共识加总 {inp['eps_fy26_q']} × PE = {inp['eps_fy26_q'] * pe_flat:.2f} 是低谷侧坐标)")
    print(f"当期 ÷ 中枢: " + "; ".join(f"{k} {v:.2f}" for k, v in ratios.items())
          + f" — >{MIDCYCLE_RATIO} 者 (FY2025) 是 H, 不是 M ✓; ②-b: FY27 均值 ∈ [M, H] = {cons_in_band}, M 偏离 {cons_gap:+.1%} (≥ −{CONSENSUS_GAP:.0%} ✓)")
    print(f"煤价互证 (A19): 煤价梯 {' / '.join(f'FY{y} {v:.2f}' for y, v in fuel.items())} → 7y mean {fuel_mid:.2f}; "
          f"轴 M 830 映射 {inp['fuel_axis_m']}; 2026 deck {inp['qhd_deck26']:.0f} (QHD {QHD_FY24:.0f} → {inp['qhd_fy25']:.0f} 传导率 {PASS_THROUGH:.2f}) → fuel ≈ {fuel_deck:.1f} "
          f"({fuel_deck / inp['fuel_axis_m'] - 1:+.1%} vs 轴映射, tol {DECK_CROSS_TOL:.0%}); 长协 2022–25 mean {inp['lt_contract_mean']:.0f}")
    eps_mean_7y = statistics.mean(EPS_PATH.values())
    print(f"  7y EPS path {' / '.join(f'{v:+.4f}' for v in EPS_PATH.values())} → mean {eps_mean_7y:.4f} "
          f"— regime-broken ({sum(v < 0 for v in EPS_PATH.values())} loss years), NOT used (A19)")
    # ROE path and the 2026H1 decline decomposition (A22 / 属性 A) — printed, not asserted.
    roe_path = {y: v * inp["shares"] / inp["equity"] for y, v in EPS_PATH.items() if y >= 2023}
    roe_path["2026E(q)"] = inp["eps_fy26_q"] * inp["shares"] / inp["equity"]
    roe_path["2026E(cons)"] = roe["m"]
    roe_path["2027E"] = inp["cons_fy27_mean"] * inp["shares"] / inp["equity"]
    print(f"ROE 路径 (A22): " + " → ".join(f"{y} {v:.1%}" for y, v in roe_path.items())
          + f"; 中枢 ROE {roe['m']:.2%} ∈ [{ROE_M_WINDOW[0]:.0%}, {ROE_M_WINDOW[1]:.0%}] ✓ (低谷 {roe_path['2026E(q)']:.1%} < 中枢 < 峰值 {roe['h']:.1%})")
    tariff_eff = (H1_TARIFF[1] - H1_TARIFF[0]) * H1_VOLUME[1] * 1e8 / 1e3 / 1e8  # 元/MWh × 亿kWh → 亿元
    vol_eff = -(H1_VOLUME[0] - H1_VOLUME[1]) * H1_COAL_SPREAD * 1e8 / 1e3 / 1e8
    fuel_eff = (H1_STD_COAL[0] - H1_STD_COAL[1]) * H1_STD_COAL_TONS * 1e4 / 1e8
    print(f"2026H1 ROE 下降拆解 (税前, 亿): 电价 {H1_TARIFF[0]} → {H1_TARIFF[1]} ({H1_TARIFF[1] / H1_TARIFF[0] - 1:+.2%}) ≈ {tariff_eff:+.0f}; "
          f"电量 {H1_VOLUME[1] / H1_VOLUME[0] - 1:+.2%} ≈ {vol_eff:+.0f}; 标煤 {H1_STD_COAL[0]} → {H1_STD_COAL[1]} ({H1_STD_COAL[1] / H1_STD_COAL[0] - 1:+.2%}) ≈ {fuel_eff:+.0f} (顺风); "
          f"实测 六腿 {H1_SIX_LEG[1] - H1_SIX_LEG[0]:+.1f} / 利润总额 {H1_PBT[1] - H1_PBT[0]:+.1f} / 普通股 {H1_ORDINARY_NI[1] - H1_ORDINARY_NI[0]:+.1f}; "
          f"风光 {RENEWABLE_H1_PBT[0]} → {RENEWABLE_H1_PBT[1]} ({RENEWABLE_H1_PBT[1] / RENEWABLE_H1_PBT[0] - 1:+.0%}) — 下降来自电价, 不是煤价")
    modelled, gap = payout_gap(g2, roe["m"], payout_fy25)
    print(f"域: ROE_M {roe['m']:.2%} − r = {roe['m'] - r:+.2%} (≥ 3pp → 单调区; g2 = 0 使倍数不依赖 ROE); ROE_L {roe['l']:.1%} / ROE_H {roe['h']:.1%}; "
          f"含永续债权益口径 ROE {inp['ni_fy25'] / (inp['equity'] + inp['perp_balance']):.1%}")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = DPS {inp['dps']} × shares ÷ 普通股股东 {inp['ni_fy25']:.2f}亿), 留存非增长性 → g2 = 0 合法 (§4.0); "
          f"payout_gap 披露: g2 {g2:+.2%} 的模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}, 差 {gap:+.2%} (进了不挣钱的建设窗口的留存)")
    print(f"g2 来源 (A15, 增长 capex 边际回报): 风光 capex {inp['re_capex_fy24']:.2f} + {inp['re_capex_fy25']:.2f} = {re_capex:.2f} 亿, "
          f"装机 {inp['re_cap_fy23']:.1f} → {inp['re_cap_fy25']:.1f} GW ({inp['re_cap_fy25'] / inp['re_cap_fy23'] - 1:+.0%}), 税前利润 {inp['re_pbt_fy23']:.2f} → {inp['re_pbt_fy25']:.2f} "
          f"({inp['re_pbt_fy25'] - inp['re_pbt_fy23']:+.2f}) → 边际税前回报 {marginal_return:.2%} < 门槛 {inp['g_marginal_min']:.0%} ⇒ g2 = 0 ✓; "
          f"账面上限 b×ROE_M = (1 − {inp['payout']}) × {roe['m']:.4%} = {g_policy:+.2%} (年报否定); 同业上限参照 [{inp['g_peer_min']:+.2%}, {inp['g_peer_max']:+.2%}] 中位 {inp['g_peer_cross']:+.2%}; "
          f"三桶: capex {inp['capex_fy25']:.0f} − D&A {inp['da_fy25']:.0f} = {build_excess:.0f} 亿 > 留存 {retained:.0f} 亿 (有息债 {inp['debt_ib']:.0f} 亿)")
    # A15 ⑨ — retention bucket D (named build window): 1/r plus the project value
    # listed separately.  K_remain is debt-funded, so the equity NPV is
    # (ROE_proj − i) × (1 − tax) × K / r; the rule's own penalty assumes equity
    # funding and is printed beside it as the flagged alternative.
    debt_cost = inp["fin_cost_h1"] * 2 / inp["debt_ib"]
    roe_fleet = inp["re_pbt_fy25"] / inp["re_assets_est"]
    k_rem = inp["re_capex_plan26"]
    npv = {lab: (roe_p - debt_cost) * (1 - inp["tax_rate"]) * k_rem / r / inp["shares"]
           for lab, roe_p in (("边际", marginal_return), ("资产平均", roe_fleet))}
    penalty = {lab: (roe_p / r - 1) * k_rem / inp["shares"] for lab, roe_p in (("边际", marginal_return), ("资产平均", roe_fleet))}
    print(f"留存去向 D 增长窗口 (A15 ⑨, Step 3): 1/r + 项目价值单列 — K_remain 2026 计划 {k_rem:.0f} 亿, 债务成本 {debt_cost:.2%} (财务费用 {inp['fin_cost_h1']} × 2 ÷ 有息债 {inp['debt_ib']:.0f}), "
          f"ROE_proj 边际 {marginal_return:.2%} / 资产平均 {roe_fleet:.2%} ({inp['re_pbt_fy25']} ÷ 估算净资产 {inp['re_assets_est']:.0f}) → 等式 NPV {npv['边际']:+.2f} ～ {npv['资产平均']:+.2f} 元/股 ≈ 0 (披露, 不进底牌); "
          f"规则原文权益出资罚项 {penalty['边际']:+.2f} ～ {penalty['资产平均']:+.2f} 元/股 (与债务融资不符, 规则缺口)")
    print(f"倍数生成: r={r:.0%} 篮 4, g2 = 0 → PE = 1/r = {pe_flat:.3f} 三档 flat (A8); 各档 ROE 各自生成 = {pe_tier['l']:.2f}/{pe_tier['m']:.2f}/{pe_tier['h']:.2f} (同值); "
          f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓ (③ 不出带); M 档 Gordon PB {roe['m'] / r:.2f}")
    print(f"地板 (A4): scenario_L {scenario_l:.2f} vs floor {inp['pb_lo']} × BPS {inp['bps']} = {floor:.2f} → "
          f"{'地板胜出, L 读资产口径' if floor > scenario_l else '情景值胜出'}; scenario_L/M = {scenario_l / M:.3f} > {FLOOR_RECHECK_RATIO} ✓; "
          f"H 股带地板只披露 ({floor / inp['hkdcny']:.2f} HKD, 在 H 股 L 与 M 之间)")
    print(f"实测运行率交叉带 (A18, 不判定): 六腿 {inp['pbt_l']:.2f}/{inp['pbt_m']:.2f}/{inp['pbt_h']:.2f} -> "
          f"EPS {eps_run['l']:.4f}/{eps_run['m']:.4f}/{eps_run['h']:.4f} x {pe['m']:.3f} = "
          f"{cross[0]:.2f}/{cross[1]:.2f}/{cross[2]:.2f}")
    print(f"六腿链坐标 (今日 k_retain/perp): FY2023 {chain[2023]:.4f} (实测 0.35 的 {chain[2023] / eps['l']:.0%}, 失真) / "
          f"FY2024 {chain[2024]:.4f} ({chain[2024] / inp['eps_fy24'] - 1:+.1%} vs 实测, 互证) / FY2025 {chain[2025]:.4f} → "
          f"{chain[2023] * pe['m']:.2f}/{chain[2024] * pe['m']:.2f}/{chain[2025] * pe['m']:.2f}")
    print(f"被否决口径①  交叉带 M 用 2026H1x2 ({inp['pbt_h1x2']:.2f} 亿, EPS {eps_of(inp, inp['pbt_h1x2']):.4f}) -> "
          f"M={eps_of(inp, inp['pbt_h1x2']) * pe['m']:.2f}, 交叉带 H/M 塌到 {cross[2] / (eps_of(inp, inp['pbt_h1x2']) * pe['m']):.3f} (A3)")
    print(f"共识坐标 × PE: FY27 {inp['cons_fy27_lo'] * pe['m']:.2f}/{inp['cons_fy27_mean'] * pe['m']:.2f}/{inp['cons_fy27_hi'] * pe['m']:.2f}; "
          f"FY26 区间 {inp['cons_fy26_lo'] * pe['m']:.2f}/{inp['cons_fy26_hi'] * pe['m']:.2f}; 季度加总 {inp['eps_fy26_q'] * pe['m']:.2f}; FY2024 印数 {inp['eps_fy24'] * pe['m']:.2f}; "
          f"TTM {inp['eps_ttm'] * pe['m']:.2f}; H 股线 FY2027 {inp['eps_hk_fy27_lo'] * pe['m']:.2f}/{inp['eps_hk_fy27_hi'] * pe['m']:.2f}; "
          f"归母读法 (三档扣 perp) -> " + "/".join(f"{(eps[t] * inp['shares'] - inp['perp']) / inp['shares'] * pe[t]:.2f}" for t in TIERS))
    print(f"永续债杠杆 (交叉带): 归母/普通股 = {leverage:.3f} (框架称 {PERP_LEVERAGE}); "
          f"余额 {inp['perp_balance']:.0f} 亿; "
          f"盈亏平衡: 六腿跌至 {inp['perp'] / inp['k_retain']:.2f} 亿时普通股股东归零")
    dps_l = eps["l"] * inp["payout"]
    print(f"L 档分红: DPS {dps_l:.4f} vs 当前 {inp['dps']} ({dps_l / inp['dps'] - 1:+.1%}); L 隐含股息率 {dps_l / L:.2%}; "
          f"中枢 DPS {dps_m:.4f}, M 上股息率 {dps_m / M:.2%} — 股息不是地板 (A14)")
    print(f"红利尺交叉 (A17): 隐含倍数 payout/yield = {pe_div:.3f} (留存分支隐含 g {g_div:+.2%}, conditioned={g_div_ok}; ≤ 账面上限 {inp['g_policy_m']:+.2%} + 3pp ✓) "
          f"vs Gordon PE {pe['m']:.3f}; 三档分叉 (情景口径) "
          + " / ".join(f"{(div[t] - a) / a:+.1%}" for t, a in zip(TIERS, (scenario_l, M, H)))
          + f"; yield 分解 = 国债 {inp['bond10y']:.3%} + 风险溢价 {inp['req_yield_a'] - inp['bond10y']:.3%}")
    print(f"股息尺压力行 (A14/A15, 不入底牌): D_M / r = {dps_m:.4f} / {r:.0%} = {ddm_pressure:.2f} CNY = {ddm_pressure / inp['hkdcny']:.2f} HKD (税后 {k_hk * ddm_pressure / inp['hkdcny']:.2f}); "
          f"峰值 D0 {inp['dps']} / r = {inp['dps'] / r:.2f}")
    roe_mark = "✓" if roe["m"] <= r + DDM_EXCEPTION_MARGIN else f"✗ (差 {roe['m'] - r - DDM_EXCEPTION_MARGIN:+.2%})"
    print(f"  skill 股息尺例外 (b): 派息 {inp['payout']:.0%} ≥ {DDM_EXCEPTION_PAYOUT:.0%} {'✓' if inp['payout'] >= DDM_EXCEPTION_PAYOUT else '✗'}; "
          f"中枢 ROE {roe['m']:.2%} ≤ r + {DDM_EXCEPTION_MARGIN:.0%} = {r + DDM_EXCEPTION_MARGIN:.0%} {roe_mark} → "
          f"{'触发: 主尺应改股息尺 (回对话)' if ddm_exception else '未触发, 贴线'}")

    d = decompose((scenario_l, M, H), (pe["l"], pe["m"], pe["h"]))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  (scenario L {scenario_l:.2f}; 地板 {floor:.2f} 兜底)")
    print(f"L/M={L / M:.2f} (情景口径 {scenario_l / M:.2f}) H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%} (情景口径 {(H - scenario_l) / (2 * M):.1%})")
    print(f"分子比 L/M=n/a (地板胜出; 情景口径 {d['num_lm']:.3f}) H/M={d['num_hm']:.3f} | 倍数比 L/M={d['pe_lm']:.3f} H/M={d['pe_hm']:.3f} (flat 1/r)")
    print(f"flat-multiple ladder (A2e-2c, 三个分子 × PE={pe['m']:.3f}): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"H股 (k = 1 − {inp['hk_div_tax']:.0%} × {inp['payout']} = {k_hk:.3f}; PE {k_hk * pe_flat:.2f}) "
          f"L={hk['l']:.2f} M={hk['m']:.2f} H={hk['h']:.2f} A={A_h:.2f} B={B_h:.2f} | "
          f"(H 股 own-year 近两年中位 {inp['pe_hk_own_mid']} 仅参照); 不扣税 → {hk['l'] / k_hk:.2f}/{hk['m'] / k_hk:.2f}/{hk['h'] / k_hk:.2f}")
    div_h_m = eps["m"] * inp["payout"] / inp["req_yield_h"] / inp["hkdcny"]
    print(f"_AXIS.southbound-repricing: 双报契约 ✓; 两地 M 档倍数比 {k_hk:.3f} (= k); 红利尺 H {div_h_m:.2f} HKD 交叉")
    print(f"带边反解 g (裁决顺序 ③, 留存分支, 中枢 ROE {roe['m']:.1%}): 下沿 {inp['pe_own_min']}x → 留存 {g_edge_lo:+.2%} (负, 不可达; 全派息读法 {g_edge_lo_full:+.2%}); "
          f"上沿 {inp['pe_own_max']}x ↔ {g_edge_hi_raw:+.2%} → 截 {g_edge_hi:+.2%}; g2 {g2:+.2%} ∈ [0, {g_edge_hi:+.2%}] ✓")
    # 敏感区 (disclosure, not an assertion): g2 alternatives, r ±50bp, alternative baskets.
    for g, lab in ((inp["g_peer_cross"], "同业簇中位"), (G2_V5, "v5 值 2%"), (min(g_policy, g_cap(r)), "留存×ROE 账面")):
        b, _ = band_at(g)
        hb, _ = band_at(g, k=k_hk, floored=False)
        hb = tuple(v / inp["hkdcny"] for v in hb)
        print(f"敏感区 {lab} g2={g:+.2%} (PE {perpetual_pe(g, roe['m'], r):.2f}): A {'/'.join(f'{x:.2f}' for x in b)} A/B {cut_points(*b)[0]:.2f}/{cut_points(*b)[1]:.2f} "
              f"| H {'/'.join(f'{x:.2f}' for x in hb)}")
    for dr in (-0.005, 0.005):
        b, _ = band_at(g2, r_=r + dr)
        hb, _ = band_at(g2, r_=r + dr, k=k_hk, floored=False)
        hb = tuple(v / inp["hkdcny"] for v in hb)
        print(f"敏感区 r {dr:+.1%} ({r + dr:.1%}): A {'/'.join(f'{x:.2f}' for x in b)} | "
              f"H {'/'.join(f'{x:.2f}' for x in hb)}")
    # CNY r_f segment reading (方案 B): disclosure only, driven by cny_rf_gap, never an r row.
    b_ccy, scen_ccy = band_at(g2, r_=r_ccy)
    print(f"货币段披露 (r_perp − cny_rf_gap = {r_ccy:.1%}, 不进底牌, 待 _AXIS.rates): PE {perpetual_pe(g2, roe['m'], r_ccy):.2f} → "
          f"A {'/'.join(f'{x:.2f}' for x in b_ccy)} (情景 L {scen_ccy:.2f}) A/B {cut_points(*b_ccy)[0]:.2f}/{cut_points(*b_ccy)[1]:.2f}")
    # A7: L / H keep their year's own perpetual coupon; re-basing to today's is a coordinate (M is consensus already).
    perp_by_year = {"l": 29.52, "h": 27.74}
    rebased = {t: eps[t] + (perp_by_year[t] - inp["perp"]) / inp["shares"] for t in ("l", "h")}
    reb_band = (max(rebased["l"] * pe_flat, floor), M, rebased["h"] * pe_flat)
    print(f"敏感性: 永续债利息重设至 {inp['perp']} (A7) -> L/H EPS {rebased['l']:.4f}/{rebased['h']:.4f} -> "
          f"{'/'.join(f'{x:.2f}' for x in reb_band)}; "
          f"不兜底 -> {scenario_l:.2f}/{M:.2f}/{H:.2f} (切点 {'/'.join(f'{x:.2f}' for x in cut_points(scenario_l, M, H))})")
    gm_band = tuple((eps[t] - GUIMU_GAP) * pe_flat for t in TIERS)
    gm_band = (max(gm_band[0], floor), gm_band[1], gm_band[2])
    print(f"敏感性: 归母读法 (三档各减 {GUIMU_GAP}, 属性 C) -> {'/'.join(f'{x:.2f}' for x in gm_band)}")
    # 校验步骤 17 (A20): the tariff is the residual; these are pressure coordinates, not tiers.
    for lab, f, tf in (("FY2024 煤 + FY2024 电价 [复现 FY2024 印数]", inp["fuel_fy24"], inp["tariff_fy24"]),
                       ("FY2024 煤 + 2026H1 电价 463.02 [压力坐标]", inp["fuel_fy24"], inp["tariff_now"]),
                       ("轴 M 煤 282.2 + FY2025 电价", inp["fuel_axis_m"], inp["tariff_fy25"]),
                       ("轴 M 煤 282.2 + 2026H1 电价 [压力坐标]", inp["fuel_axis_m"], inp["tariff_now"]),
                       ("两驱动同取 7y 均值 [regime 混合]", fuel_mid, TARIFF_7Y_MEAN),
                       ("FY2022 亏损 regime", inp["fuel_fy22"], inp["tariff_fy22"])):
        six, e = bridge_eps(inp, f, tf)
        print(f"A20 线性桥 {lab}: 价差 {tf - f:.2f} → 六腿 {six:.1f} → EPS {e:.4f} → {e * pe['m']:.2f}")
    print("  (桥缺的项: 2026 容量电价抬价、2024 年后新增 ~10 GW 新能源、永续债利息下降 — 桥值系统性偏低约 10%, 共识中枢 5.62 与桥 3.19 的差是这些项, A20)")
    # 校验步骤 18: coordinates that are NOT the deck, each named for why not.
    v5 = (max(eps["l"] * PE_M_V5, floor), EPS_M_V5 * PE_M_V5, EPS_M_V5 * PE_H_V5)
    print(f"对照 v5 中枢带 (FY2024 印数 {EPS_M_V5} × {PE_M_V5}, g2 {G2_V5:+.0%}, 共识窗口 {PE_H_V5}): A {'/'.join(f'{x:.2f}' for x in v5)} "
          f"— 中枢落在低谷侧 + g2 无来源 (Changelog 2026-09-20 v6)")
    for lab, basket in (("备选篮 2 管制公用", 2), ("备选篮 6 周期商品", 6)):
        b, scen = band_at(g2, r_=basket_r(basket))
        print(f"对照 {lab} r={basket_r(basket):.1%}: A 情景 {scen:.2f}/{b[1]:.2f}/{b[2]:.2f} (L 兜底 {b[0]:.2f})")
    v4 = tuple(inp[k] * PE_V4 for k in ("cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi"))
    print(f"对照 v4 峰值分子带 (FY2027 共识三点 × {PE_V4}): A {'/'.join(f'{x:.2f}' for x in v4)} — 峰值分子的坐标 (A16)")
    pe_v3 = 1.0 / (r - G2_OLD_BRANCH)  # full-payout branch: payout capped at 100%
    v3 = tuple(inp[k] * pe_v3 for k in ("cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi"))
    print(f"对照 v3 全派息分支 {G2_OLD_BRANCH:+.2%} flat {pe_v3:.2f}x 于共识三点: A {'/'.join(f'{x:.2f}' for x in v3)} "
          f"— 分支错误的坐标 (A15/A16)")

    return report(errors)


def basket_r_label(basket: int) -> str:
    name, value = BASKET_R[basket]
    return f"{name} {value:.1%}"


if __name__ == "__main__":
    sys.exit(main())
