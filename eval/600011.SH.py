#!/usr/bin/env python3
"""600011.SH (Huaneng Power International) valuation eval.

frameworks/600011.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: huaneng_midcycle_coal_ladder_pe_gordon_v5

Main ruler: whole-company PE on a MID-CYCLE numerator (valuation-rules.md
「周期票的中枢分子与 PE < 1/r 的读法」).  L and M are two years the company
actually printed, picked off a coal-cost ladder — the domestic coal-fired unit
fuel cost the annual reports disclose (元/MWh):

    FY2019 223 / FY2020 209 / FY2021 316 / FY2022 373 / FY2023 326 / FY2024 300 / FY2025 267

Seven years = one full cycle (2020 trough, 2022 peak); the mean is 287.83.
The realised year nearest that mean is FY2024 (300.31, +4.3%), and two
independent coal prints agree: the >= 2-house 2026 QHD-5500 deck (BofA 800 /
HSBC 791 / GS 813-850, median 800) maps to ~289 through the realised 2024->2025
pass-through (QHD -18.4% <-> fuel cost -11.1%), and the 2022-25 annual
long-term-contract price averages 704 vs FY2024's 701.  So

    L = FY2023 world  (fuel 326.43, coal leg 4.33亿 ≈ 0)        EPS 0.3500
    M = FY2024 world  (fuel 300.31 ≈ mid-cycle, tariff 494.26)  EPS 0.4594   <- 中枢
    H = 中枢 + named g1 window: E1 = 0.4594 -> E4 = FY27E consensus mean 0.658
        (g1 12.7%, n = 3), then the g2 tail

all on the ordinary-shareholder basic EPS the annual reports print (A2).  The
FY2025 peak print (0.74, 1.61x 中枢) is a `stretched` coordinate, not H: per
「周期票的中枢分子」a realised year 61% above mid-cycle is the upper-side
coordinate, and the consensus window is the only nameable, falsifiable upper
edge.  The cross-cycle EPS mean (0.057 over seven years) is regime-broken —
two loss years — so it is printed, not used.

The multiple is GENERATED (valuation-rules「永续增长口径」), r from the basket
table (`gordon.BASKET_R`): the whole company is 篮 4 龙头制造, r = 10%,
cross-market fixed (方案 A) — the H-share companion band uses the same r and
only adds the southbound dividend-tax numerator discount k = 1 - 20% x payout.
The CNY r_f segment reading (r - `cny_rf_gap` = 8.5%) is a DISCLOSURE line,
never an r row (controller ruling: `r*` rows hold basket-table values only).

    PE_M = (1 - g2/ROE_M) / (r - g2),  flat for L and M (`cyclical` policy)
    PE_H = sum_{t=1..n} (1+g1)^(t-1)/(1+r)^t + (1+g1)^n PE_M/(1+r)^n

g2 = 2% comes from the retention three-bucket review (§4.0): capex 583 vs D&A
275 — the 300+ 亿 excess is the renewables build window, debt-financed
(有息债 3,089 亿 vs ordinary equity 645), so b x ROE_M (5.15%, `g_policy_m`) is
only the sustainable UPPER BOUND on g2, not its source; the perpetuity gets the
tariff-regulated inflation tier and the volume growth goes into the named
window.  Stage 1 of the window is priced at full E (the build is debt-funded,
it does not consume retention), which is why `annuity_factor` is used rather
than `two_stage_pe`'s 1 - g1/ROE stage-1 payout.

Regime: ROE_M 11.18% sits 1.2pp above r — the ill-conditioned regime, where
neither Gordon branch's reverse-solved g is a reading; the script keeps the
regime assertion because the g2 source rule changes with it.

L's scenario value (0.35 x 10.26 = 3.59) sits below the FY2020 realised PB low
(1.04 x BPS = 4.27), so the A-share L is floored (A2e-1; both values printed).
On the H-share companion band the floor is disclosure only — after the tax
discount both L and M scenario values sit below it and max() would give L > M.

Guards kept from v1: numerator ladder, basket r, g cap, shared g2, payout
consistency (sign + three-bucket upper bound), flat policy with the tier-ROE
variant printed as rejected, own-band guardrail, flat-multiple ladder,
dividend-ruler g inside the evidence interval ±3pp, floor recheck ratio, live
H/A, southbound mount contract, perp leverage and TTM anchoring on the run-rate
cross band, reference rows kept out of the formula, band-edge reverse-solve,
stated-vs-recomputed anchors.

Run:  python3 eval/600011.SH.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600011.SH.md"
FORMULA_ID = "huaneng_midcycle_coal_ladder_pe_gordon_v5"

TIERS = ("l", "m", "h")
PERP_LEVERAGE = 1.240       # 归母 / 普通股股东, TTM (cross band)
FLOOR_RECHECK_RATIO = 0.30  # A2e-1: below this the earnings ruler has failed at L
EPS_ANCHOR_TOL = 0.002      # A6: k_retain is calibrated so the cross-band M reproduces the TTM
EVID_G_TOL = 0.03           # A17: the yield-implied g may sit this far outside the evidence interval
PAYOUT_TOL = 0.002          # A15: stated payout vs dps x shares / ni_fy25
G2_TOL = 5e-5               # A15: g_policy_m vs (1 - payout) x ROE_M
G1_TOL = 5e-4               # A5: g1_h vs (cons_fy27_mean / eps_m)^(1/n_h) - 1
MAX_WINDOW_YEARS = 3        # §13 rule 3: a named g1 window runs at most three years
EPS_TIER_TOL = 5e-4         # A19: eps_m vs the mid-cycle year's realised EPS
MIN_PRINT_MONTHS = 6        # 裁决顺序 ④: fewer well-conditioned months is not evidence
REGIME_MARGIN = 0.03        # valuation-rules「反解分支」: |ROE_M - r| < 3pp is the ill-conditioned regime
MIDCYCLE_RATIO = 1.15       # 「周期票的中枢分子」: above this the current print is a coordinate, not M
CONSENSUS_GAP = 0.20        # ②-b: M more than this below the consensus mean -> "共识还停在峰值"
LADDER_MEAN_TOL = 0.05      # A19: stated fuel_mid vs the recomputed 7-year mean
DECK_CROSS_TOL = 0.20       # A19: deck-mapped fuel cost vs the realised mean must agree within this
PASS_THROUGH = 0.60         # A19: realised 2024->2025 QHD -18.4% <-> unit fuel cost -11.13%
QHD_FY24 = 703.0 / (1 - 0.184)
CHAIN_TOL = 0.05            # 校验步骤 7 / 17: mid-cycle year re-derived through the chain / the bridge vs realised
G2_V1 = 0.0515              # v1: retention branch b x ROE_M, now the upper bound (Changelog 2026-09-20)
G2_OLD_BRANCH = -0.0153     # v3: peer 100%-payout reading, printed as the wrong-branch coordinate
PE_V4 = 11.284              # v4: flat multiple, for the peak-numerator 对照带
GUIMU_GAP = 0.1417          # 属性 C: 归母 EPS minus ordinary-shareholder EPS (FY2025), coordinate only
# Seven-year ordinary-shareholder EPS path (annual reports; Longbridge IS `af` 每股收益).
# Printed with its mean and flagged regime-broken: two loss years make the
# cross-cycle mean meaningless, which is why the ladder bridge is used instead.
EPS_PATH = {2019: 0.0561, 2020: 0.1780, 2021: -0.7736, 2022: -0.6102, 2023: 0.3500, 2024: 0.4594, 2025: 0.7400}
LADDER_YEARS = (2019, 2020, 2021, 2022, 2023, 2024, 2025)
MIDCYCLE_YEAR = 2024
TARIFF_7Y_MEAN = statistics.mean((417.00, 413.63, 432.0, 509.92, 508.74, 494.26, 477.08))  # A20 coordinate only

REQUIRED = [
    "price", "price_h", "hkdcny", "shares", "bps", "equity",
    "eps_l", "eps_m", "eps_h", "eps_fy23", "eps_fy24", "eps_fy25", "eps_ttm",
    *[f"fuel_fy{y % 100}" for y in LADDER_YEARS], "fuel_mid",
    "qhd_fy25", "qhd_deck26", "lt_contract_mean",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_now", "coal_vol",
    "pbt_fy23", "pbt_fy24", "pbt_l", "pbt_m", "pbt_h", "k_retain", "perp",
    "r_perp", "r_perp_hkd", "cny_rf_gap", "hk_div_tax",
    "capex_fy25", "da_fy25", "debt_ib", "g1_h", "n_h",
    "ni_fy25", "g2_l", "g2_m", "g2_h", "g_policy_m",
    "g_print_m", "n_print_m", "n_match_m", "pe_print_m_med", "g_evid_min", "g_evid_max",
    "g_peer_min", "g_peer_max", "g_peer_cross",
    "pe_own_min", "pe_own_max", "pe_hk_own_mid",
    "payout", "req_yield_a", "req_yield_h", "bond10y",
    "dps", "perp_balance", "pb_lo", "ha_ratio", "pbt_h1x2",
    "cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi", "cons_fy26_mean",
    "eps_hk_fy27_lo", "eps_hk_fy27_hi",
]
# Reference-only rows: they must never enter a base-deck anchor (校验步骤 13).
NOT_FORMULA = (
    "pe_hk_own_mid", "pbt_h1x2", "bond10y", "req_yield_h",
    "pbt_l", "pbt_m", "pbt_h", "pbt_fy23", "pbt_fy24", "eps_hk_fy27_lo", "eps_hk_fy27_hi",
    "g_peer_min", "g_peer_max", "g_peer_cross", "g_print_m", "pe_print_m_med", "g_policy_m",
    "cons_fy27_lo", "cons_fy27_hi", "cons_fy26_mean", "eps_ttm", "eps_h",
    "qhd_fy25", "qhd_deck26", "lt_contract_mean",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_now", "coal_vol",
    "cny_rf_gap", "capex_fy25", "da_fy25", "debt_ib",
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


def window_pe(g1: float, n: int, pe_tail: float, r: float) -> float:
    """H multiple on E1 = 中枢: n years at g1 priced at FULL E (the build window is
    debt-funded and consumes no retention, A5), then the Gordon tail at t = n.
    `two_stage_pe` is not used because its stage-1 payout is 1 - g1/ROE."""
    return annuity_factor(g1, r, n) + (1.0 + g1) ** n * pe_tail / (1.0 + r) ** n


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker is declared on the axis and reports
    both bands plus the live H/A.  The southbound axis locks no numerator and
    no multiple for this ticker (Gordon generates it, A13), so the reporting
    contract is the only thing left to enforce."""
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
    if not re.search(r"H/A\s*=\s*\*{0,2}0\.\d+", md):
        errors.append("framework does not state the current H/A reading (axis §3 rule 3)")
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

    # --- Step 1: the coal-cost ladder, the mid-cycle year, and the realised worlds
    fuel = {y: inp[f"fuel_fy{y % 100}"] for y in LADDER_YEARS}
    fuel_mid = statistics.mean(fuel.values())
    if abs(fuel_mid - inp["fuel_mid"]) > LADDER_MEAN_TOL:
        errors.append(f"fuel_mid stated {inp['fuel_mid']} vs recomputed 7-year mean {fuel_mid:.2f} (A19)")
    nearest = min(fuel, key=lambda y: abs(fuel[y] - fuel_mid))
    if nearest != MIDCYCLE_YEAR:
        errors.append(
            f"the realised year nearest the ladder mean is FY{nearest}, not FY{MIDCYCLE_YEAR} — "
            "the mid-cycle numerator has to be re-decided (A19)"
        )
    # The >= 2-house deck must land near the realised mean, or one of the two 中枢 readings is wrong.
    fuel_deck = inp["fuel_fy25"] * (1 + PASS_THROUGH * (inp["qhd_deck26"] / inp["qhd_fy25"] - 1))
    if abs(fuel_deck / fuel_mid - 1) > DECK_CROSS_TOL:
        errors.append(
            f"deck-mapped fuel cost {fuel_deck:.1f} is >{DECK_CROSS_TOL:.0%} from the realised mean {fuel_mid:.1f} — "
            "the two 中枢 readings disagree; back to the conversation (A19)"
        )
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    errors += ladder("eps (realised-year prints)", eps["l"], eps["m"], eps["h"])
    # Same source, same basis: the prints ARE the annual-report EPS of the ladder years
    # (eps_h = FY2025 stays as the `stretched` coordinate; H itself is the window on eps_m).
    for t, key in (("l", "eps_fy23"), ("m", "eps_fy24"), ("h", "eps_fy25")):
        if abs(eps[t] - inp[key]) > EPS_TIER_TOL:
            errors.append(f"eps_{t} {eps[t]} != {key} {inp[key]} — tiers must be the ladder years' realised EPS (A4/A5)")
    errors += reverse_ladder("coal-cost ladder (L = dearest coal)", inp["fuel_fy23"], inp["fuel_fy24"], inp["fuel_fy25"])
    if eps["h"] > inp["cons_fy27_hi"] + 1e-9:
        errors.append(f"eps_h {eps['h']} exceeds the consensus upper {inp['cons_fy27_hi']} (A5)")
    # 「周期票的中枢分子」: current ÷ 中枢 > 1.15 -> M MUST be the mid-cycle print.
    ratio_ttm = inp["eps_ttm"] / inp["eps_fy24"]
    ratio_cons = inp["cons_fy27_mean"] / inp["eps_fy24"]
    if max(ratio_ttm, ratio_cons) > MIDCYCLE_RATIO and abs(eps["m"] - inp["eps_fy24"]) > EPS_TIER_TOL:
        errors.append(
            f"current ÷ 中枢 = {ratio_ttm:.2f} / {ratio_cons:.2f} > {MIDCYCLE_RATIO} but eps_m {eps['m']} is not the "
            f"mid-cycle print {inp['eps_fy24']} — the numerator is at a cycle high (valuation-rules「周期票的中枢分子」)"
        )
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

    # --- Step 2: basket r, tier ROE, regime, g2 source, g1 window, then the multiples
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
    # Regime (valuation-rules「反解分支」): if the mid-cycle ROE ever leaves
    # |ROE - r| < 3pp the g2 source rule changes with it — a conversation.
    if abs(roe["m"] - r) >= REGIME_MARGIN:
        errors.append(
            f"ROE_M {roe['m']:.2%} is >= {REGIME_MARGIN:.0%} from r — no longer the ill-conditioned regime; "
            "re-decide the g2 source (A15 / valuation-rules「反解分支」)"
        )
    # Branch sign is pinned by the payout actually paid (A15): 54% < 80% retains, so g2 > 0.
    payout_fy25 = inp["dps"] * inp["shares"] / inp["ni_fy25"]
    if abs(payout_fy25 - inp["payout"]) > PAYOUT_TOL:
        errors.append(f"payout {inp['payout']} vs dps x shares / ni_fy25 = {payout_fy25:.4f} (A15)")
    if g2 <= 0:
        errors.append(f"g2={g2:+.4f} <= 0 is the full-payout branch — Huaneng pays out {payout_fy25:.0%} and retains (A15)")
    # g2 VALUE: the three-bucket rule (§4.0, A15).  b x ROE_M is the sustainable
    # upper bound; the perpetuity takes the tariff-regulated inflation tier
    # because the build window is debt-funded, not retention-funded.
    g_policy = (1 - inp["payout"]) * roe["m"]
    if abs(inp["g_policy_m"] - g_policy) > G2_TOL:
        errors.append(f"g_policy_m {inp['g_policy_m']} vs (1 - payout) x ROE_M = {g_policy:.5f} (A15)")
    if g2 > inp["g_policy_m"] + 1e-9:
        errors.append(f"g2_m {g2} exceeds the sustainable upper bound b x ROE_M = {inp['g_policy_m']} (A15)")
    retained = inp["ni_fy25"] * (1 - inp["payout"])
    build_excess = inp["capex_fy25"] - inp["da_fy25"]
    if build_excess <= retained:
        errors.append(
            f"capex − D&A = {build_excess:.0f} 亿 no longer exceeds retained earnings {retained:.0f} 亿 — "
            "the build-window premise behind g2 = 2% (not b x ROE) is gone; re-decide the g2 source (A15)"
        )
    # The own-band pairing at the mid-cycle window is not evidence (n < 6).
    if inp["n_print_m"] < MIN_PRINT_MONTHS and abs(g2 - inp["g_print_m"]) <= G2_TOL:
        errors.append(
            f"n_print_m {inp['n_print_m']:.0f} < {MIN_PRINT_MONTHS} yet g2 equals the pairing value g_print_m "
            f"{inp['g_print_m']} — the own-band read is not evidence at the mid-cycle window (A15)"
        )
    if inp["n_print_m"] >= MIN_PRINT_MONTHS:
        errors.append(
            f"n_print_m {inp['n_print_m']:.0f} >= {MIN_PRINT_MONTHS}: the own-band pairing is usable again — "
            "re-decide the g2 source via a framework correction (A15)"
        )
    if not (inp["g_evid_min"] - 1e-9 <= g2 <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2_m {g2} outside the evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A15)")
    for key in ("g_peer_max", "g_peer_cross"):
        if abs(inp[key] - g2) < 1e-9:
            errors.append(f"{key} leaked into g2 — cross-regime peer readings are cross-checks only (A15)")
    # H window (A5): g1 is the consensus bridge from 中枢 to FY27E, n bounded by §13 rule 3.
    n_h = int(inp["n_h"])
    if n_h < 1 or n_h > MAX_WINDOW_YEARS or n_h != inp["n_h"]:
        errors.append(f"n_h {inp['n_h']} must be an integer in [1, {MAX_WINDOW_YEARS}] (A5 / §13 rule 3)")
    g1 = (inp["cons_fy27_mean"] / eps["m"]) ** (1.0 / max(n_h, 1)) - 1
    if abs(g1 - inp["g1_h"]) > G1_TOL:
        errors.append(f"g1_h {inp['g1_h']} vs (cons_fy27_mean / eps_m)^(1/n_h) − 1 = {g1:.4f} (A5)")
    if errors:
        return report(errors, "FAIL (growth 口径)")
    # A8: flat by policy at the mid-cycle ROE for L / M.  Letting each tier's
    # ROE set its own payout gives a same-direction ladder (printed below as rejected).
    pe_flat = perpetual_pe(g2, roe["m"], r)
    pe_win = window_pe(g1, n_h, pe_flat, r)
    pe = {"l": pe_flat, "m": pe_flat, "h": pe_win}
    pe_tier = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    if not (pe_tier["l"] < pe_tier["m"] < pe_tier["h"]):
        errors.append(
            f"tier-ROE variant {pe_tier['l']:.2f}/{pe_tier['m']:.2f}/{pe_tier['h']:.2f} is no longer same-direction — "
            "the reason A8 pins the multiple flat has changed; re-decide (A8)"
        )
    # Guardrail (A12, Phase 3 §A6): both generated multiples must sit inside the
    # ticker's own realised band, or the ticker stops rather than widens it.
    for lab, p in (("PE_M", pe_flat), ("窗口 PE_H", pe_win)):
        if not (inp["pe_own_min"] <= p <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: generated {lab} {p:.2f} outside realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] (A12) — STOP, do not force g"
            )
    if errors:
        return report(errors, "FAIL (guardrail)")

    floor = inp["pb_lo"] * inp["bps"]
    k_hk = 1.0 - inp["hk_div_tax"] * inp["payout"]  # southbound dividend-tax numerator discount (A13)

    def band_at(g: float, r_: float = r, g1_: float = g1, n_: int = n_h, k: float = 1.0,
                floored: bool = True) -> tuple[tuple[float, float, float], float]:
        """((L, M, H), scenario_L) in CNY: L / M flat at ROE_M, H = 中枢 x window.
        The A-share L is floored (A4); the H-share band passes floored=False."""
        p = k * perpetual_pe(g, roe["m"], r_)
        w = k * window_pe(g1_, n_, perpetual_pe(g, roe["m"], r_), r_)
        scen_l, M, H = eps["l"] * p, eps["m"] * p, eps["m"] * w
        return (max(scen_l, floor) if floored else scen_l, M, H), scen_l

    (L, M, H), scenario_l = band_at(g2)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # H 股 companion band: same basket r, dividend-tax discount k on the numerator,
    # floor disclosure only (both L and M scenario values sit under it), quoted HKD.
    (hk_l_cny, hk_m_cny, hk_h_cny), _ = band_at(g2, k=k_hk, floored=False)
    hk = {"l": hk_l_cny / inp["hkdcny"], "m": hk_m_cny / inp["hkdcny"], "h": hk_h_cny / inp["hkdcny"]}
    A_h, B_h = cut_points(hk["l"], hk["m"], hk["h"])
    zone_h = zone_of(inp["price_h"], hk["l"], hk["m"], hk["h"])
    px_h_cny = inp["price_h"] * inp["hkdcny"]

    def zone_or_na(price: float, b: tuple[float, float, float]) -> str:
        try:
            return zone_of(price, *b)
        except ValueError:
            return "n/a (M < 地板, 不出 zone)"

    # --- Step 3: the 口径 decisions, re-derived ------------------------------
    # ②-b on the mid-cycle M (A11): the consensus mean inside [M, eps_h] but > 20%
    # above M reads as "共识还停在峰值" — a trigger, not a reason to move M.
    cons_in_band = eps["m"] <= inp["cons_fy27_mean"] <= eps["h"]
    cons_gap = eps["m"] / inp["cons_fy27_mean"] - 1
    trigger_level = eps["m"] * (1 + CONSENSUS_GAP)

    # A2e-2c — flat-multiple ladder on the three realised prints (FY2025 x PE_M is the `stretched` coordinate).
    flat_errs, flat = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe["m"])
    errors += flat_errs

    # A14 / A17 — dividend ruler is a cross-ruler: no parameter shared with
    # Gordon.  In the ill-conditioned regime its reverse-solved g is not a
    # precise reading, but it must still sit near the evidence interval.
    div = {t: eps[t] * inp["payout"] / inp["req_yield_a"] for t in TIERS}
    pe_div = inp["payout"] / inp["req_yield_a"]
    g_div, g_div_ok = implied_g_retaining(pe_div, roe["m"], r)
    if not (inp["g_evid_min"] - EVID_G_TOL <= g_div <= inp["g_evid_max"] + EVID_G_TOL):
        errors.append(
            f"dividend-ruler implied g {g_div:+.4f} outside the evidence interval ±{EVID_G_TOL:.0%} "
            f"[{inp['g_evid_min']}, {inp['g_evid_max']}] — yield-based pricing has left the own band (A17)"
        )

    # A4 — floor backstop: the scenario value must still be a live earnings ruler.
    if scenario_l / M <= FLOOR_RECHECK_RATIO:
        errors.append(
            f"scenario_L/M = {scenario_l / M:.3f} <= {FLOOR_RECHECK_RATIO} — the earnings ruler "
            "has failed at L; A2e-1 requires going back to the conversation"
        )

    # A13 — the axis reads H/A off the two live prices; a stale input shows here.
    ha_live = px_h_cny / inp["price"]
    if abs(ha_live - inp["ha_ratio"]) > 0.005:
        errors.append(
            f"ha_ratio stated {inp['ha_ratio']} vs live {ha_live:.3f} — "
            "_AXIS.southbound-repricing cross-check would use a stale value"
        )
    errors += check_southbound_mount(md)

    # 校验步骤 6: the perp leverage on the cross band is a calibrated fact.
    leverage = (inp["pbt_m"] * inp["k_retain"]) / (inp["pbt_m"] * inp["k_retain"] - inp["perp"])
    if abs(leverage / PERP_LEVERAGE - 1.0) > 0.02:
        errors.append(
            f"perp leverage {leverage:.3f} drifted >2% from {PERP_LEVERAGE} — "
            "k_retain or perp moved without recalibration (校验步骤 6)"
        )

    # 校验步骤 7: the six-leg chain reproduces the mid-cycle year (mutual proof)
    # and visibly fails FY2023 — which is why the tiers are realised EPS, not chain values.
    chain = {2023: eps_of(inp, inp["pbt_fy23"]), 2024: eps_of(inp, inp["pbt_fy24"]), 2025: eps_of(inp, inp["pbt_h"])}
    if abs(chain[2024] / eps["m"] - 1) > CHAIN_TOL:
        errors.append(f"six-leg chain for FY2024 {chain[2024]:.4f} is >{CHAIN_TOL:.0%} from the realised {eps['m']} (A4/A18)")

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
    # edge is not a g on this ROE; only the upper edge (capped) bounds g2.
    g_edge_lo, edge_lo_ok = implied_g_retaining(inp["pe_own_min"], roe["m"], r)
    g_edge_lo_full, _ = implied_g(inp["pe_own_min"], roe["m"], r)
    if edge_lo_ok:
        errors.append(
            f"band lower edge {inp['pe_own_min']}x reverse-solves to a conditioned g {g_edge_lo:+.2%} — "
            "it should be unreachable on this ROE; the regime statement in A12 no longer holds"
        )
    g_edge_hi_raw, _ = implied_g_retaining(inp["pe_own_max"], roe["m"], r)
    g_edge_hi = min(g_edge_hi_raw, g_cap(r))
    if not (0.0 < g2 <= g_edge_hi):
        errors.append(
            f"g2 {g2:+.4f} outside (0, band-edge implied g {g_edge_hi:+.4f}] — guardrail would bind (裁决顺序 ③)"
        )

    # 校验步骤 17 (A20): the linear spread bridge must reproduce the mid-cycle
    # year from the FY2025 base, or the pressure coordinates it prints are stories.
    _, eps_bridge_m = bridge_eps(inp, inp["fuel_fy24"], inp["tariff_fy24"])
    if abs(eps_bridge_m / eps["m"] - 1) > CHAIN_TOL:
        errors.append(f"A20 bridge at (fuel_fy24, tariff_fy24) gives {eps_bridge_m:.4f}, >{CHAIN_TOL:.0%} from eps_m {eps['m']}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"篮子: {' · '.join(f'{k} 篮 {v} {basket_r_label(v)}' for k, v in baskets.items())}; r = {r:.1%} 跨市场固定 (方案 A); "
          f"CNY 段披露 r = r_perp − cny_rf_gap = {r_ccy:.1%} (不进底牌); cap g2 ≤ {g_cap(r):.1%} (段 {g_cap(r_ccy):.1%})")
    print(f"{'档':<3}{'世界':>8}{'燃料成本':>9}{'电价':>8}{'EPS(实测)':>11}{'÷中枢':>7}{'ROE':>8}{'g2':>8}{'PE':>7}"
          f"{'情景值':>8}{'A股':>8}{'H股':>8}{'红利尺':>8}")
    worlds = {"l": (2023, inp["fuel_fy23"], inp["tariff_fy23"]), "m": (2024, inp["fuel_fy24"], inp["tariff_fy24"]),
              "h": (2025, inp["fuel_fy25"], inp["tariff_fy25"])}
    for t, anchor_a, scen in zip(TIERS, (L, M, H), (scenario_l, M, H)):
        yr, f, tf = worlds[t]
        print(f"{t.upper():<3}{f'FY{yr}':>8}{f:9.2f}{tf:8.2f}{eps[t]:11.4f}{eps[t] / eps['m']:7.2f}"
              f"{roe[t]:8.1%}{inp[f'g2_{t}']:+8.2%}{pe[t]:7.2f}{scen:8.2f}{anchor_a:8.2f}{hk[t]:8.2f}{div[t]:8.2f}")
    print(f"  (H 行: 分子 = 中枢 {eps['m']} × 窗口 {pe_win:.3f}; FY2025 实测 0.74 × PE_M = {eps['h'] * pe_flat:.2f} 是 `stretched` 坐标, 不是 H)")
    print(f"煤价梯 (A19): {' / '.join(f'FY{y} {v:.2f}' for y, v in fuel.items())} → 7y mean {fuel_mid:.2f} (median {statistics.median(fuel.values()):.2f}); "
          f"nearest realised year FY{nearest} ({fuel[nearest] / fuel_mid - 1:+.1%}); FY2025 {fuel[2025] / fuel_mid - 1:+.1%}, FY2023 {fuel[2023] / fuel_mid - 1:+.1%}")
    print(f"  ≥2 家 deck 互证: QHD {QHD_FY24:.0f} → {inp['qhd_fy25']:.0f} (−18.4%) ↔ fuel −11.13% → pass-through {PASS_THROUGH:.2f}; "
          f"2026 deck {inp['qhd_deck26']:.0f} → fuel ≈ {fuel_deck:.1f} ({fuel_deck / fuel_mid - 1:+.1%} vs mean, tol {DECK_CROSS_TOL:.0%}); "
          f"长协 2022–25 mean {inp['lt_contract_mean']:.0f} ≈ FY2024 701")
    eps_mean_7y = statistics.mean(EPS_PATH.values())
    print(f"  7y EPS path {' / '.join(f'{v:+.4f}' for v in EPS_PATH.values())} → mean {eps_mean_7y:.4f} "
          f"— regime-broken ({sum(v < 0 for v in EPS_PATH.values())} loss years), NOT used (只用轴桥, A19)")
    print(f"当期 ÷ 中枢: TTM {inp['eps_ttm']} / {inp['eps_fy24']} = {ratio_ttm:.2f}; FY27 共识均值 {inp['cons_fy27_mean']} → {ratio_cons:.2f}; "
          f"FY2025 {eps['h'] / eps['m']:.2f}; FY27 lo/hi {inp['cons_fy27_lo'] / eps['m']:.2f}/{inp['cons_fy27_hi'] / eps['m']:.2f}; "
          f"FY26 共识 {inp['cons_fy26_mean']} → {inp['cons_fy26_mean'] / eps['m']:.2f} — >{MIDCYCLE_RATIO} ⇒ M = 中枢 ✓, 其余只作上侧坐标")
    print(f"②-b (中枢 M 上): 共识均值 ∈ [M, FY2025] = {cons_in_band}; M 偏离均值 {cons_gap:+.1%} "
          + (f"(超 −{CONSENSUS_GAP:.0%}) → 共识还停在峰值; 触发器: 下季 FY2027 均值 ≤ {trigger_level:.3f} 即确认 (A11)"
             if cons_gap < -CONSENSUS_GAP else "(在 ±20% 内)"))
    modelled, gap = payout_gap(g2, roe["m"], payout_fy25)
    print(f"域: ROE_M {roe['m']:.2%} − r = {roe['m'] - r:+.2%}, |·| < {REGIME_MARGIN:.0%} → 病态区 (两条分支的 g 都不是读数; PE(g∈[0,cap]) = "
          f"{perpetual_pe(0.0, roe['m'], r):.2f}–{perpetual_pe(g_cap(r), roe['m'], r):.2f}); ROE_L {roe['l']:.1%} 病态 / ROE_H {roe['h']:.1%} 单调; "
          f"含永续债权益口径 ROE {inp['ni_fy25'] / (inp['equity'] + inp['perp_balance']):.1%}")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = DPS {inp['dps']} × shares ÷ 普通股股东 {inp['ni_fy25']:.2f}亿) → g2 > 0 ✓; "
          f"payout_gap 披露: g2 {g2:+.2%} 的模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}, 差 {gap:+.2%} "
          f"(建设窗口债务融资, 留存不全进 g — 不作分支错误读)")
    print(f"g2 来源 (§4.0 留存三桶, A15): capex {inp['capex_fy25']:.0f} − D&A {inp['da_fy25']:.0f} = {build_excess:.0f} 亿 > 留存 {retained:.0f} 亿 "
          f"(有息债 {inp['debt_ib']:.0f} 亿 vs 普通股权益 {inp['equity']:.0f}) → 建设窗口债务融资, b×ROE_M = (1 − {inp['payout']}) × {roe['m']:.4%} = {g_policy:+.2%} 只作上限; "
          f"永续 g2 {g2:+.2%} (电价管制下的通胀档) ≤ 上限 ✓, cap {g_cap(r):.0%} ✓; 同域同业华电 {inp['g_peer_min']:+.2%} 互证 (n=1); "
          f"证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}] 含 g2 ✓")
    print(f"  自身实测带反解 (中枢窗口 0.4594 ±12%): 落窗 {inp['n_match_m']:.0f} 月, 良态 {inp['n_print_m']:.0f} 月 (<{MIN_PRINT_MONTHS} → 不可用; "
          f"唯一良态月 {inp['g_print_m']:+.2%} 不入公式); 实付 PE 中位 {inp['pe_print_m_med']:.2f}× → 坐标 {inp['pe_print_m_med'] * eps['m']:.2f} (市场在中枢盈利上买回归)")
    print(f"  同世界门: 分子年 FY2024 → 最远共识年 FY2027 均值 {inp['cons_fy27_mean']} 上行 → g2 ≤ 0 不可用; "
          f"跨域簇 [{inp['g_peer_min']:+.2%}, {inp['g_peer_max']:+.2%}] 中位 {inp['g_peer_cross']:+.2%} 只交叉 (浙能峰形区)")
    print(f"倍数生成: r={r:.0%} 篮 4, PE_M = (1−g2/ROE_M)/(r−g2) = {pe_flat:.3f} (L / M flat, A8); "
          f"H 窗口 = Σ(1+g1)^(t−1)/(1+r)^t [t=1..{n_h}] + (1+g1)^{n_h} PE_M/(1+r)^{n_h} = {pe_win:.3f} (g1 {g1:+.2%} = ({inp['cons_fy27_mean']}/{eps['m']})^(1/{n_h}) − 1, 段一全额 E); "
          f"各档 ROE 各自生成 = {pe_tier['l']:.2f}/{pe_tier['m']:.2f}/{pe_tier['h']:.2f} 同向 → 被否决口径④; "
          f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓ (③ 不出带); M 档 Gordon PB {(roe['m'] - g2) / (r - g2):.2f} vs 现价 PB {inp['price'] / inp['bps']:.2f} / H 股 PB {px_h_cny / inp['bps']:.2f}")
    print(f"地板 (A4): scenario_L {scenario_l:.2f} vs floor {inp['pb_lo']} × BPS {inp['bps']} = {floor:.2f} → "
          f"{'地板胜出, L 读资产口径' if floor > scenario_l else '情景值胜出'}; scenario_L/M = {scenario_l / M:.3f} > {FLOOR_RECHECK_RATIO} ✓; "
          f"H 股带地板只披露 ({floor / inp['hkdcny']:.2f} HKD, 在 H 股 L / M 之上)")
    print(f"实测运行率交叉带 (A18, 不判定): 六腿 {inp['pbt_l']:.2f}/{inp['pbt_m']:.2f}/{inp['pbt_h']:.2f} -> "
          f"EPS {eps_run['l']:.4f}/{eps_run['m']:.4f}/{eps_run['h']:.4f} x {pe['m']:.3f} = "
          f"{cross[0]:.2f}/{cross[1]:.2f}/{cross[2]:.2f}, 现价 zone={zone_of(inp['price'], *cross)}")
    print(f"六腿链坐标 (今日 k_retain/perp): FY2023 {chain[2023]:.4f} (实测 0.35 的 {chain[2023] / eps['l']:.0%}, 失真) / "
          f"FY2024 {chain[2024]:.4f} ({chain[2024] / eps['m'] - 1:+.1%} vs 实测, 互证) / FY2025 {chain[2025]:.4f} → "
          f"{chain[2023] * pe['m']:.2f}/{chain[2024] * pe['m']:.2f}/{chain[2025] * pe['m']:.2f}")
    print(f"被否决口径①  交叉带 M 用 2026H1x2 ({inp['pbt_h1x2']:.2f} 亿, EPS {eps_of(inp, inp['pbt_h1x2']):.4f}) -> "
          f"M={eps_of(inp, inp['pbt_h1x2']) * pe['m']:.2f}, 交叉带 H/M 塌到 {cross[2] / (eps_of(inp, inp['pbt_h1x2']) * pe['m']):.3f} (A3)")
    print(f"被否决口径③  零增长 10x -> {max(eps['l'] * 10, floor):.2f}/{eps['m'] * 10:.2f}/{eps['h'] * 10:.2f}")
    print(f"共识坐标 × PE_M: FY27 {inp['cons_fy27_lo'] * pe['m']:.2f}/{inp['cons_fy27_mean'] * pe['m']:.2f}/{inp['cons_fy27_hi'] * pe['m']:.2f} "
          f"(均值直接乘倍数 {inp['cons_fy27_mean'] * pe['m']:.2f} 在 H {H:.2f} 之上 — H 是把均值折三年后的今值); "
          f"FY26 {inp['cons_fy26_mean'] * pe['m']:.2f}; TTM {inp['eps_ttm'] * pe['m']:.2f}; H 股线 FY2027 {inp['eps_hk_fy27_lo'] * pe['m']:.2f}/{inp['eps_hk_fy27_hi'] * pe['m']:.2f}; "
          f"归母读法 (三档扣 perp) -> " + "/".join(f"{(eps[t] * inp['shares'] - inp['perp']) / inp['shares'] * pe[t]:.2f}" for t in TIERS))
    print(f"永续债杠杆 (交叉带): 归母/普通股 = {leverage:.3f} (框架称 {PERP_LEVERAGE}); "
          f"余额 {inp['perp_balance']:.0f} 亿 = A股市值的 {inp['perp_balance'] / (inp['price'] * inp['shares']):.0%}; "
          f"盈亏平衡: 六腿跌至 {inp['perp'] / inp['k_retain']:.2f} 亿时普通股股东归零")
    dps_l, dps_m = eps["l"] * inp["payout"], eps["m"] * inp["payout"]
    print(f"L 档分红: DPS {dps_l:.4f} vs 当前 {inp['dps']} ({dps_l / inp['dps'] - 1:+.1%}); L 隐含股息率 {dps_l / L:.2%}; "
          f"中枢 DPS {dps_m:.4f}, M 上股息率 {dps_m / M:.2%} — 股息不是地板 (A14)")
    print(f"红利尺交叉 (A17): 隐含倍数 payout/yield = {pe_div:.3f} (留存分支隐含 g {g_div:+.2%}, conditioned={g_div_ok} 病态区读数, 在证据区间内) "
          f"vs Gordon PE_M {pe['m']:.3f}; L / M 分叉 (情景口径) "
          + " / ".join(f"{(div[t] - a) / a:+.1%}" for t, a in zip(("l", "m"), (scenario_l, M)))
          + f"; H 不可比 (红利尺 FY2025 峰值股息 {div['h']:.2f} vs 窗口 H {H:.2f})"
          + f"; yield 分解 = 国债 {inp['bond10y']:.3%} + 风险溢价 {inp['req_yield_a'] - inp['bond10y']:.3%}")
    ddm_mid = dps_m * (1 + g2) / (r - g2)
    ddm_peak = inp["dps"] * (1 + g2) / (r - g2)
    print(f"DDM 对照: 中枢 D0 {dps_m:.4f} → {ddm_mid:.2f} CNY = {ddm_mid / inp['hkdcny']:.2f} HKD ({ddm_mid / M - 1:+.1%} vs M); "
          f"峰值 D0 {inp['dps']} → {ddm_peak:.2f} CNY = {ddm_peak / inp['hkdcny']:.2f} HKD; "
          f"现价隐含股息增长 (中枢 D0 / 峰值 D0): A {(inp['price'] * r - dps_m) / (inp['price'] + dps_m):+.2%} / {(inp['price'] * r - inp['dps']) / (inp['price'] + inp['dps']):+.2%}, "
          f"H {(px_h_cny * r - dps_m) / (px_h_cny + dps_m):+.2%} / {(px_h_cny * r - inp['dps']) / (px_h_cny + inp['dps']):+.2%}")

    d = decompose((scenario_l, M, H), (pe["l"], pe["m"], pe["h"]))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  (scenario L {scenario_l:.2f}; 地板 {floor:.2f} 兜底)")
    print(f"L/M={L / M:.2f} (情景口径 {scenario_l / M:.2f}) H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%} (情景口径 {(H - scenario_l) / (2 * M):.1%})")
    print(f"分子比 L/M=n/a (地板胜出; 情景口径 {d['num_lm']:.3f}) H/M={d['num_hm']:.3f} (H 与 M 同用中枢分子) | 倍数比 L/M={d['pe_lm']:.3f} H/M={d['pe_hm']:.3f} (窗口/flat)")
    print(f"flat-multiple ladder (A2e-2c, 三个实测年 × PE_M={pe['m']:.3f}): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f} (FY2025 项 = `stretched` 坐标)")
    pe_px_a = inp["price"] / eps["m"]
    g_px, g_px_ok = implied_g_retaining(pe_px_a, roe["m"], r)
    r_impl_a = eps["m"] / inp["price"] + g2
    print(f"A股 price={inp['price']} zone={zone} | 现价 = {pe_px_a:.2f}x 中枢 EPS ({inp['price'] / inp['eps_ttm']:.2f}x TTM, {inp['price'] / inp['cons_fy27_mean']:.2f}x FY27 均值); "
          f"PE_M 下隐含 EPS {inp['price'] / pe['m']:.4f} = 中枢 × {inp['price'] / pe['m'] / eps['m']:.2f}; "
          f"留存分支反解 g {g_px:+.2%} ({'越 cap, 不可达' if g_px > g_cap(r) else 'conditioned=' + str(g_px_ok)})"
          + (f"; 溢价 (P-H)/H = {(inp['price'] - H) / H:+.1%}" if inp["price"] > H else ""))
    r_impl_h = k_hk * eps["m"] / px_h_cny + g2
    pe_px_h = px_h_cny / eps["m"]
    g_hk, g_hk_ok = implied_g_retaining(pe_px_h, roe["m"], r)
    print(f"隐含 r(P) (g = {g2:.0%}, E/P + g): A {r_impl_a:.2%} (篮 4 {r_impl_a - r:+.1%}; 对 CNY 段披露 {r_ccy:.1%} {r_impl_a - r_ccy:+.1%}); "
          f"H 税后 {r_impl_h:.2%} (篮 4 {r_impl_h - r:+.1%}; 税前 {eps['m'] / px_h_cny + g2:.2%}); "
          f"A/H 税后差 {r_impl_h - r_impl_a:+.2%} vs r_f 段差 {inp['cny_rf_gap']:+.2%} (余 = 红利税 + 残差)")
    print(f"H股 (k = 1 − {inp['hk_div_tax']:.0%} × {inp['payout']} = {k_hk:.3f}; PE_M {k_hk * pe_flat:.2f}, 窗口 {k_hk * pe_win:.2f}) "
          f"L={hk['l']:.2f} M={hk['m']:.2f} H={hk['h']:.2f} A={A_h:.2f} B={B_h:.2f} price={inp['price_h']} zone={zone_h} | "
          f"H 股现价 = {pe_px_h:.2f}x 中枢 ({px_h_cny / inp['eps_ttm']:.2f}x TTM, {px_h_cny / inp['cons_fy27_mean']:.2f}x FY27 均值); "
          f"税后 PE_M 下隐含 EPS {px_h_cny / (k_hk * pe['m']):.4f} = 中枢 × {px_h_cny / (k_hk * pe['m']) / eps['m']:.2f}; 留存分支反解 g {g_hk:+.2%} (病态区读数, conditioned={g_hk_ok}) "
          f"(H 股 own-year 近两年中位 {inp['pe_hk_own_mid']} 仅参照); 不扣税 → {hk['l'] / k_hk:.2f}/{hk['m'] / k_hk:.2f}/{hk['h'] / k_hk:.2f} zone={zone_of(inp['price_h'], hk['l'] / k_hk, hk['m'] / k_hk, hk['h'] / k_hk)}")
    div_h_m = eps["m"] * inp["payout"] / inp["req_yield_h"] / inp["hkdcny"]
    print(f"_AXIS.southbound-repricing: H/A={ha_live:.3f} (0.433 -> {ha_live:.3f}); 双报契约 ✓; "
          f"两地 M 档倍数比 {k_hk * pe_flat / pe_flat:.3f} (= k) vs 实测 H/A {ha_live:.3f}; 红利尺 H {div_h_m:.2f} HKD, 税后 DDM 中枢股息 {k_hk * ddm_mid / inp['hkdcny']:.2f} HKD 交叉")
    print(f"带边反解 g (裁决顺序 ③, 留存分支, 中枢 ROE {roe['m']:.1%}): 下沿 {inp['pe_own_min']}x → BLOCKED "
          f"(留存 {g_edge_lo:+.1%} 越 r 不是读数; 全派息读法 {g_edge_lo_full:+.2%}); "
          f"上沿 {inp['pe_own_max']}x ↔ {g_edge_hi_raw:+.2%} → 截 {g_edge_hi:+.2%}; g2 {g2:+.2%} ∈ (0, {g_edge_hi:+.2%}] ✓")
    # 敏感区 (disclosure, not an assertion): g2 evidence ends / [0, cap] / ±1pp, r ±50bp.
    probe = {inp["g_evid_min"]: "证据下沿", inp["g_evid_max"]: "证据上沿", 0.0: "g=0", g_cap(r): "g=cap"}
    for g, lab in probe.items():
        b, _ = band_at(g)
        hb, _ = band_at(g, k=k_hk, floored=False)
        hb = tuple(v / inp["hkdcny"] for v in hb)
        print(f"敏感区 {lab} g2={g:+.2%} (PE_M {perpetual_pe(g, roe['m'], r):.2f}): A {'/'.join(f'{x:.2f}' for x in b)} A/B {cut_points(*b)[0]:.2f}/{cut_points(*b)[1]:.2f} "
              f"zone={zone_of(inp['price'], *b)} | H {'/'.join(f'{x:.2f}' for x in hb)} zone={zone_of(inp['price_h'], *hb)}")
    for dg in (-0.01, 0.01):
        g = min(g2 + dg, g_cap(r))
        b, _ = band_at(g)
        hb, _ = band_at(g, k=k_hk, floored=False)
        hb = tuple(v / inp["hkdcny"] for v in hb)
        print(f"敏感区 g2 {dg:+.0%} ({g:+.2%}): A {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)} | "
              f"H {'/'.join(f'{x:.2f}' for x in hb)} zone={zone_of(inp['price_h'], *hb)}")
    for dr in (-0.005, 0.005):
        b, _ = band_at(g2, r_=r + dr)
        hb, _ = band_at(g2, r_=r + dr, k=k_hk, floored=False)
        hb = tuple(v / inp["hkdcny"] for v in hb)
        print(f"敏感区 r {dr:+.1%} ({r + dr:.1%}): A {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)} | "
              f"H {'/'.join(f'{x:.2f}' for x in hb)} zone={zone_of(inp['price_h'], *hb)}")
    # CNY r_f segment reading (方案 B): disclosure only, driven by cny_rf_gap, never an r row.
    b_ccy, scen_ccy = band_at(g2, r_=r_ccy)
    print(f"货币段披露 (r_perp − cny_rf_gap = {r_ccy:.1%}, 不进底牌, 待 _AXIS.rates): PE_M {perpetual_pe(g2, roe['m'], r_ccy):.2f} / 窗口 {window_pe(g1, n_h, perpetual_pe(g2, roe['m'], r_ccy), r_ccy):.2f} → "
          f"A {'/'.join(f'{x:.2f}' for x in b_ccy)} (情景 L {scen_ccy:.2f} > 地板) A/B {cut_points(*b_ccy)[0]:.2f}/{cut_points(*b_ccy)[1]:.2f} zone={zone_of(inp['price'], *b_ccy)} (P/M {inp['price'] / b_ccy[1]:.2f}); "
          f"隐含 r A {r_impl_a:.2%} 对段 {r_impl_a - r_ccy:+.1%}")
    # Window construction alternatives (A5): endpoint lo / hi, n = 2 / 1, g1 = 0.
    for lab, e4 in (("共识下沿", inp["cons_fy27_lo"]), ("共识上沿", inp["cons_fy27_hi"])):
        g1_alt = (e4 / eps["m"]) ** (1.0 / n_h) - 1
        b, _ = band_at(g2, g1_=g1_alt)
        print(f"窗口终点 {lab} {e4}: g1 {g1_alt:+.2%} → 窗口 {window_pe(g1_alt, n_h, pe_flat, r):.2f} → H {b[2]:.2f} zone={zone_of(inp['price'], *b)}")
    for n_alt in (2, 1):
        b, _ = band_at(g2, n_=n_alt)
        print(f"窗口 n = {n_alt}: 窗口 {window_pe(g1, n_alt, pe_flat, r):.2f} → H {b[2]:.2f} zone={zone_of(inp['price'], *b)}")
    # A7: the tiers keep each year's own perpetual coupon; re-basing to today's is a coordinate.
    perp_by_year = {2023: 29.52, 2024: 29.23, 2025: 27.74}
    rebased = [eps[t] + (perp_by_year[y] - inp["perp"]) / inp["shares"] for t, y in zip(TIERS, (2023, 2024, 2025))]
    reb_band = (max(rebased[0] * pe_flat, floor), rebased[1] * pe_flat, rebased[1] * pe_win)
    print(f"敏感性: 永续债利息重设至 {inp['perp']} (A7) -> EPS {'/'.join(f'{x:.4f}' for x in rebased)} -> "
          f"{'/'.join(f'{x:.2f}' for x in reb_band)} zone={zone_of(inp['price'], *reb_band)}; "
          f"不兜底 -> {scenario_l:.2f}/{M:.2f}/{H:.2f} zone={zone_of(inp['price'], scenario_l, M, H)}")
    gm_band = (max((eps["l"] - GUIMU_GAP) * pe_flat, floor), (eps["m"] - GUIMU_GAP) * pe_flat, (eps["m"] - GUIMU_GAP) * pe_win)
    print(f"敏感性: 归母读法 (三档各减 {GUIMU_GAP}, 属性 C) -> {'/'.join(f'{x:.2f}' for x in gm_band)} zone={zone_or_na(inp['price'], gm_band)}")
    # 校验步骤 17 (A20): the tariff is the residual; these are pressure coordinates, not tiers.
    for lab, f, tf in (("中枢煤 (FY2024 fuel) + FY2024 电价 [复现 M]", inp["fuel_fy24"], inp["tariff_fy24"]),
                       ("中枢煤 + 2026H1 电价 463.02 [压力坐标]", inp["fuel_fy24"], inp["tariff_now"]),
                       ("两驱动同取 7y 均值 [regime 混合]", fuel_mid, TARIFF_7Y_MEAN),
                       ("FY2022 亏损 regime", inp["fuel_fy22"], inp["tariff_fy22"])):
        six, e = bridge_eps(inp, f, tf)
        print(f"A20 线性桥 {lab}: 价差 {tf - f:.2f} → 六腿 {six:.1f} → EPS {e:.4f} → {e * pe['m']:.2f}")
    # 校验步骤 18: coordinates that are NOT the deck, each named for why not.
    b_v1 = (max(eps["l"] * perpetual_pe(G2_V1, roe["m"], r), floor), eps["m"] * perpetual_pe(G2_V1, roe["m"], r), eps["h"] * perpetual_pe(G2_V1, roe["m"], r))
    print(f"对照 派息政策口径 (g2 {G2_V1:+.2%} 留存 × ROE, flat {perpetual_pe(G2_V1, roe['m'], r):.2f}×, H = FY2025 峰值年): A {'/'.join(f'{x:.2f}' for x in b_v1)} "
          f"zone={zone_of(inp['price'], *b_v1)} — 峰值年长期化 + 建设窗口留存当永续 (Changelog 2026-09-20)")
    for lab, basket in (("备选篮 2 管制公用", 2), ("备选篮 6 周期商品", 6)):
        b, scen = band_at(g2, r_=basket_r(basket))
        print(f"对照 {lab} r={basket_r(basket):.1%}: A 情景 {scen:.2f}/{b[1]:.2f}/{b[2]:.2f} (L 兜底 {b[0]:.2f}) zone={zone_or_na(inp['price'], b)}")
    v4 = tuple(inp[k] * PE_V4 for k in ("cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi"))
    print(f"对照 v4 峰值分子带 (FY2027 共识三点 × {PE_V4}): A {'/'.join(f'{x:.2f}' for x in v4)} zone={zone_of(inp['price'], *v4)} | "
          f"H zone={zone_of(inp['price_h'], *(x / inp['hkdcny'] for x in v4))} — 峰值分子的坐标 (A16)")
    pe_v3 = 1.0 / (r - G2_OLD_BRANCH)  # full-payout branch: payout capped at 100%
    v3 = tuple(inp[k] * pe_v3 for k in ("cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi"))
    print(f"对照 v3 全派息分支 {G2_OLD_BRANCH:+.2%} flat {pe_v3:.2f}x 于共识三点: A {'/'.join(f'{x:.2f}' for x in v3)} "
          f"zone={zone_of(inp['price'], *v3)} — 分支错误的坐标 (A15/A16)")
    b, _ = band_at(inp["g_peer_cross"])
    print(f"对照 跨域交叉中位 g_peer_cross: g2={inp['g_peer_cross']:+.2%} A {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")

    return report(errors)


def basket_r_label(basket: int) -> str:
    name, value = BASKET_R[basket]
    return f"{name} {value:.1%}"


if __name__ == "__main__":
    sys.exit(main())
