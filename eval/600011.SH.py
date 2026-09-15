#!/usr/bin/env python3
"""600011.SH (Huaneng Power International) valuation eval.

frameworks/600011.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: huaneng_midcycle_coal_ladder_pe_gordon_v5

Main ruler: whole-company PE on a MID-CYCLE numerator (valuation-rules.md
「周期票的中枢分子与 PE < 1/r 的读法」).  The three tiers are three years the
company actually printed, picked off a coal-cost ladder — the domestic
coal-fired unit fuel cost the annual reports disclose (元/MWh):

    FY2019 223 / FY2020 209 / FY2021 316 / FY2022 373 / FY2023 326 / FY2024 300 / FY2025 267

Seven years = one full cycle (2020 trough, 2022 peak); the mean is 287.83.
The realised year nearest that mean is FY2024 (300.31, +4.3%), and two
independent coal prints agree: the >= 2-house 2026 QHD-5500 deck (BofA 800 /
HSBC 791 / GS 813-850, median 800) maps to ~289 through the realised 2024->2025
pass-through (QHD -18.4% <-> fuel cost -11.1%), and the 2022-25 annual
long-term-contract price averages 704 vs FY2024's 701.  So

    L = FY2023 world  (fuel 326.43, coal leg 4.33亿 ≈ 0)        EPS 0.3500
    M = FY2024 world  (fuel 300.31 ≈ mid-cycle, tariff 494.26)  EPS 0.4594   <- 中枢
    H = FY2025 world  (fuel 266.88, cheapest since 2020)        EPS 0.7400

all on the ordinary-shareholder basic EPS the annual reports print (A2).  The
cross-cycle EPS mean itself (0.057 over seven years) is regime-broken — two
loss years — so the rule's "regime 断裂 -> 只用轴桥并注明" clause applies and it
is printed, not used.

The rule's test: current EPS ÷ 中枢.  TTM 0.59 / 0.4594 = 1.28, the FY2027
consensus mean 0.658 / 0.4594 = 1.43, FY2025 = 1.61 — all > 1.15, so M MUST be
the mid-cycle print and the consensus / TTM / FY2025 prints are
`optimistic`-side coordinates (v4 used the consensus mean as M; that read a
cheap-coal year as the steady state).  ②-b on the mid-cycle M: the FY2027 mean
sits inside [M, H] but 43% above M — per the rule that is "共识还停在峰值", so a
falsification trigger is hung (A11) and M is not moved.

The multiple is GENERATED, not picked from history (valuation-rules「永续增长口径」):

    PE = (1 - g2/ROE_M) / (r - g2),   r = 10%,   one flat multiple for all tiers

Regime: the mid-cycle ROE is 11.18% on the ordinary-shareholder book, 1.2pp
above r — the ILL-CONDITIONED regime (valuation-rules「反解分支」), where neither
Gordon branch's reverse-solved g is a reading and g2 has to come from the
payout policy.  Huaneng pays out 54% (retention branch), so g2 = (1 - 54%) x
ROE_M = 5.15%, below the 6% cap.  The own-band pairing at the mid-cycle EPS
window (10 months, 2024-05..2025-08) finds only ONE well-conditioned month —
the market paid 13.9-19.2x on mid-cycle earnings, buying the recovery that
FY2025 then delivered — so `n_print_m` < 6 and the script asserts the fallback
was taken, not the pairing median.  The same-regime peer (华电, ROE 7.5%,
+1.13%) is n=1 and corroborates only.  Because ROE_M ≈ r the answer is
insensitive to g: M sits in 4.59-5.32 for any g in [0, 6%], and the script
prints both ends (the A13-style statement).

L's scenario value (0.35 x 11.12 = 3.89) sits below the FY2020 realised PB low
(1.04 x BPS = 4.27), so L is floored (A2e-1 allows it; both values are printed
and `conservative` reads as the asset basis).

Guards kept from v4: numerator ladder, r tier, g cap, shared g2, payout
consistency, `check_branch`, flat policy with the tier-ROE variant printed as
rejected, own-band guardrail, evidence-interval zone stability, flat-multiple
ladder, dividend-ruler g inside the evidence interval ±3pp, floor recheck
ratio, live H/A, southbound mount contract, perp leverage and TTM anchoring on
the run-rate cross band, reference rows kept out of the formula, band-edge
reverse-solve, stated-vs-recomputed anchors.

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
    G_CAP, check_branch, check_g_cap, check_r, implied_g, implied_g_retaining, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report, reverse_ladder,
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
G2_TOL = 5e-5               # A15: g2 vs (1 - payout) x ROE_M
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
G2_OLD_BRANCH = -0.0153     # v3: peer 100%-payout reading, printed as the wrong-branch coordinate
G2_V4 = 0.0255              # v4: own-band median at the PEAK window, printed on the mid-cycle numerator
PE_V4 = 11.284              # v4: flat multiple, for the peak-numerator 对照带
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
    "r_perp", "ni_fy25", "g2_l", "g2_m", "g2_h", "g_policy_m",
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
    "g_peer_min", "g_peer_max", "g_peer_cross", "g_print_m", "pe_print_m_med",
    "cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi", "cons_fy26_mean", "eps_ttm",
    "qhd_fy25", "qhd_deck26", "lt_contract_mean",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_now", "coal_vol",
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
    r = inp["r_perp"]

    # --- Step 1: the coal-cost ladder, the mid-cycle year, and the three realised worlds
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
    errors += ladder("eps (realised-year worlds)", eps["l"], eps["m"], eps["h"])
    # Same source, same basis: the tiers ARE the annual-report prints of the ladder years.
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

    # --- Step 2: tier ROE, regime, branch, then the flat Gordon multiple ------
    roe = {t: eps[t] * inp["shares"] / inp["equity"] for t in TIERS}
    g2 = inp["g2_m"]
    errors += check_r(r, "r_perp")
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], f"g2_{t}")
    if not (inp["g2_l"] == inp["g2_m"] == inp["g2_h"]):
        errors.append(f"g2 tiers {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} must be one shared value (A8 flat)")
    # Regime (valuation-rules「反解分支」): the g2 source below (payout policy x
    # ROE_M) is the ILL-CONDITIONED regime's rule.  If the mid-cycle ROE ever
    # leaves |ROE - r| < 3pp the source rule changes with it — a conversation.
    if abs(roe["m"] - r) >= REGIME_MARGIN:
        errors.append(
            f"ROE_M {roe['m']:.2%} is >= {REGIME_MARGIN:.0%} from r — no longer the ill-conditioned regime; "
            "re-decide the g2 source (A15 / valuation-rules「反解分支」)"
        )
    # Branch is pinned by the payout actually paid (A15).  54% < 80% retains,
    # so g2 must be positive; its VALUE is the payout policy x ROE_M.
    payout_fy25 = inp["dps"] * inp["shares"] / inp["ni_fy25"]
    if abs(payout_fy25 - inp["payout"]) > PAYOUT_TOL:
        errors.append(f"payout {inp['payout']} vs dps x shares / ni_fy25 = {payout_fy25:.4f} (A15)")
    if g2 <= 0:
        errors.append(f"g2={g2:+.4f} <= 0 is the full-payout branch — Huaneng pays out {payout_fy25:.0%} and retains (A15)")
    errors += check_branch(g2, roe["m"], r, payout_fy25, "g2_m")
    g_policy = (1 - inp["payout"]) * roe["m"]
    if abs(inp["g_policy_m"] - g_policy) > G2_TOL:
        errors.append(f"g_policy_m {inp['g_policy_m']} vs (1 - payout) x ROE_M = {g_policy:.5f} (A15)")
    if abs(g2 - min(inp["g_policy_m"], G_CAP)) > G2_TOL:
        errors.append(f"g2_m {g2} vs payout-policy source g_policy_m {inp['g_policy_m']} (A15)")
    # The own-band pairing at the mid-cycle window is not evidence (n < 6): g2
    # must NOT be riding the pairing median.
    if inp["n_print_m"] < MIN_PRINT_MONTHS and abs(g2 - inp["g_print_m"]) <= G2_TOL:
        errors.append(
            f"n_print_m {inp['n_print_m']:.0f} < {MIN_PRINT_MONTHS} yet g2 equals the pairing value g_print_m "
            f"{inp['g_print_m']} — the own-band read is not evidence at the mid-cycle window (A15)"
        )
    if inp["n_print_m"] >= MIN_PRINT_MONTHS:
        errors.append(
            f"n_print_m {inp['n_print_m']:.0f} >= {MIN_PRINT_MONTHS}: the own-band pairing is usable again — "
            "switch the g2 source back to 自身实测带反解 via a framework correction (A15)"
        )
    if not (inp["g_evid_min"] - 1e-9 <= g2 <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2_m {g2} outside the evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A15)")
    for key in ("g_peer_max", "g_peer_cross"):
        if abs(inp[key] - g2) < 1e-9:
            errors.append(f"{key} leaked into g2 — cross-regime peer readings are cross-checks only (A15)")
    if errors:
        return report(errors, "FAIL (growth 口径)")
    # A8: flat by policy at the mid-cycle ROE.  Letting each tier's ROE set its
    # own payout gives a same-direction ladder (printed below as rejected).
    pe_flat = perpetual_pe(g2, roe["m"], r)
    pe = {t: pe_flat for t in TIERS}
    pe_tier = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    if not (pe["l"] == pe["m"] == pe["h"]):
        errors.append("multiples are not flat — A8 policy violated")
    if not (pe_tier["l"] < pe_tier["m"] < pe_tier["h"]):
        errors.append(
            f"tier-ROE variant {pe_tier['l']:.2f}/{pe_tier['m']:.2f}/{pe_tier['h']:.2f} is no longer same-direction — "
            "the reason A8 pins the multiple flat has changed; re-decide (A8)"
        )
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

    def band_at(g: float) -> tuple[tuple[float, float, float], float]:
        """((L, M, H), scenario_L) in CNY for one shared g2, flat at ROE_M, L floored (A4)."""
        p = perpetual_pe(g, roe["m"], r)
        scen_l, M, H = (eps[t] * p for t in TIERS)
        return (max(scen_l, floor), M, H), scen_l

    (L, M, H), scenario_l = band_at(g2)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # H股 rides the same anchors, quoted HKD.
    hk = {"l": L / inp["hkdcny"], "m": M / inp["hkdcny"], "h": H / inp["hkdcny"]}
    A_h, B_h = cut_points(hk["l"], hk["m"], hk["h"])
    zone_h = zone_of(inp["price_h"], hk["l"], hk["m"], hk["h"])

    # 校验步骤 2a: the ANCHOR zone must hold across the g2 evidence interval and,
    # in the ill-conditioned regime, across the whole [0, cap] (A13-style).
    probe = {inp["g_evid_min"]: "证据下沿", inp["g_evid_max"]: "证据上沿", 0.0: "g=0", G_CAP: "g=cap"}
    for g, lab in probe.items():
        b, _ = band_at(g)
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"A-share zone flips to {zone_of(inp['price'], *b)} at g2={g:+.2%} ({lab}) — BLOCKED (A15)")

    # --- Step 3: the 口径 decisions, re-derived ------------------------------
    # ②-b on the mid-cycle M (A11): the consensus mean inside [M, H] but > 20%
    # above M reads as "共识还停在峰值" — a trigger, not a reason to move M.
    cons_in_band = eps["m"] <= inp["cons_fy27_mean"] <= eps["h"]
    cons_gap = eps["m"] / inp["cons_fy27_mean"] - 1
    trigger_level = eps["m"] * (1 + CONSENSUS_GAP)

    # A2e-2c — flat-multiple ladder on the scenario numerators.
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
    ha_live = inp["price_h"] * inp["hkdcny"] / inp["price"]
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
    g_edge_hi = min(g_edge_hi_raw, G_CAP)
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
    print(f"{'档':<3}{'世界':>8}{'燃料成本':>9}{'电价':>8}{'EPS(实测)':>11}{'÷中枢':>7}{'ROE':>8}{'g2':>8}{'PE':>7}"
          f"{'情景值':>8}{'A股':>8}{'H股':>8}{'红利尺':>8}")
    worlds = {"l": (2023, inp["fuel_fy23"], inp["tariff_fy23"]), "m": (2024, inp["fuel_fy24"], inp["tariff_fy24"]),
              "h": (2025, inp["fuel_fy25"], inp["tariff_fy25"])}
    for t, anchor_a, scen in zip(TIERS, (L, M, H), (scenario_l, M, H)):
        yr, f, tf = worlds[t]
        print(f"{t.upper():<3}{f'FY{yr}':>8}{f:9.2f}{tf:8.2f}{eps[t]:11.4f}{eps[t] / eps['m']:7.2f}"
              f"{roe[t]:8.1%}{inp[f'g2_{t}']:+8.2%}{pe[t]:7.2f}{scen:8.2f}{anchor_a:8.2f}{hk[t]:8.2f}{div[t]:8.2f}")
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
    print(f"②-b (中枢 M 上): 共识均值 ∈ [M, H] = {cons_in_band}; M 偏离均值 {cons_gap:+.1%} "
          + (f"(超 −{CONSENSUS_GAP:.0%}) → 共识还停在峰值; 触发器: 下季 FY2027 均值 ≤ {trigger_level:.3f} 即确认 (A11)"
             if cons_gap < -CONSENSUS_GAP else "(在 ±20% 内)"))
    modelled, gap = payout_gap(g2, roe["m"], payout_fy25)
    print(f"域: ROE_M {roe['m']:.2%} − r = {roe['m'] - r:+.2%}, |·| < {REGIME_MARGIN:.0%} → 病态区 (两条分支的 g 都不是读数; PE(g∈[0,6%]) = "
          f"{perpetual_pe(0.0, roe['m'], r):.2f}–{perpetual_pe(G_CAP, roe['m'], r):.2f}); ROE_L {roe['l']:.1%} 病态 / ROE_H {roe['h']:.1%} 单调; "
          f"含永续债权益口径 ROE {inp['ni_fy25'] / (inp['equity'] + inp['perp_balance']):.1%}")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = DPS {inp['dps']} × shares ÷ 普通股股东 {inp['ni_fy25']:.2f}亿); "
          f"check_branch ✓ (符号+幅度); payout_gap: 模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}, 差 {gap:+.2%}")
    print(f"g2 来源: 病态区规则 → 派息政策 × 中枢 ROE = (1 − {inp['payout']}) × {roe['m']:.4%} = {g_policy:+.2%} → g2 {g2:+.2%} ✓ (cap {G_CAP:.0%}, 未截); "
          f"同域同业华电 {inp['g_peer_min']:+.2%} 互证 (n=1); 证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}]")
    print(f"  自身实测带反解 (中枢窗口 0.4594 ±12%): 落窗 {inp['n_match_m']:.0f} 月, 良态 {inp['n_print_m']:.0f} 月 (<{MIN_PRINT_MONTHS} → 不可用; "
          f"唯一良态月 {inp['g_print_m']:+.2%} 不入公式); 实付 PE 中位 {inp['pe_print_m_med']:.2f}× → 坐标 {inp['pe_print_m_med'] * eps['m']:.2f} (市场在中枢盈利上买回归)")
    print(f"  同世界门: 分子年 FY2024 → 最远共识年 FY2027 均值 {inp['cons_fy27_mean']} 上行 → g2 ≤ 0 不可用; "
          f"跨域簇 [{inp['g_peer_min']:+.2%}, {inp['g_peer_max']:+.2%}] 中位 {inp['g_peer_cross']:+.2%} 只交叉 (浙能峰形区)")
    print(f"倍数生成: r={r:.0%}, PE = (1−g2/ROE_M)/(r−g2) = {pe_flat:.3f} 三档 flat (A8); "
          f"各档 ROE 各自生成 = {pe_tier['l']:.2f}/{pe_tier['m']:.2f}/{pe_tier['h']:.2f} 同向 → 被否决口径④; "
          f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓; M 档 Gordon PB {(roe['m'] - g2) / (r - g2):.2f} vs 现价 PB {inp['price'] / inp['bps']:.2f} / H 股 PB {inp['price_h'] * inp['hkdcny'] / inp['bps']:.2f}")
    print(f"地板 (A4): scenario_L {scenario_l:.2f} vs floor {inp['pb_lo']} × BPS {inp['bps']} = {floor:.2f} → "
          f"{'地板胜出, L 读资产口径' if floor > scenario_l else '情景值胜出'}; scenario_L/M = {scenario_l / M:.3f} > {FLOOR_RECHECK_RATIO} ✓")
    print(f"实测运行率交叉带 (A18, 不判定): 六腿 {inp['pbt_l']:.2f}/{inp['pbt_m']:.2f}/{inp['pbt_h']:.2f} -> "
          f"EPS {eps_run['l']:.4f}/{eps_run['m']:.4f}/{eps_run['h']:.4f} x {pe['m']:.3f} = "
          f"{cross[0]:.2f}/{cross[1]:.2f}/{cross[2]:.2f}, 现价 zone={zone_of(inp['price'], *cross)}")
    print(f"六腿链坐标 (今日 k_retain/perp): FY2023 {chain[2023]:.4f} (实测 0.35 的 {chain[2023] / eps['l']:.0%}, 失真) / "
          f"FY2024 {chain[2024]:.4f} ({chain[2024] / eps['m'] - 1:+.1%} vs 实测, 互证) / FY2025 {chain[2025]:.4f} → "
          f"{chain[2023] * pe['m']:.2f}/{chain[2024] * pe['m']:.2f}/{chain[2025] * pe['m']:.2f}")
    print(f"被否决口径①  交叉带 M 用 2026H1x2 ({inp['pbt_h1x2']:.2f} 亿, EPS {eps_of(inp, inp['pbt_h1x2']):.4f}) -> "
          f"M={eps_of(inp, inp['pbt_h1x2']) * pe['m']:.2f}, 交叉带 H/M 塌到 {cross[2] / (eps_of(inp, inp['pbt_h1x2']) * pe['m']):.3f} (A3)")
    print(f"被否决口径③  零增长 10x -> {max(eps['l'] * 10, floor):.2f}/{eps['m'] * 10:.2f}/{eps['h'] * 10:.2f}")
    print(f"共识坐标 × PE_M: FY27 {inp['cons_fy27_lo'] * pe['m']:.2f}/{inp['cons_fy27_mean'] * pe['m']:.2f}/{inp['cons_fy27_hi'] * pe['m']:.2f}; "
          f"FY26 {inp['cons_fy26_mean'] * pe['m']:.2f}; TTM {inp['eps_ttm'] * pe['m']:.2f}; H 股线 FY2027 {inp['eps_hk_fy27_lo'] * pe['m']:.2f}/{inp['eps_hk_fy27_hi'] * pe['m']:.2f}; "
          f"归母读法 (三档扣 perp) -> " + "/".join(f"{(eps[t] * inp['shares'] - inp['perp']) / inp['shares'] * pe[t]:.2f}" for t in TIERS))
    print(f"永续债杠杆 (交叉带): 归母/普通股 = {leverage:.3f} (框架称 {PERP_LEVERAGE}); "
          f"余额 {inp['perp_balance']:.0f} 亿 = A股市值的 {inp['perp_balance'] / (inp['price'] * inp['shares']):.0%}; "
          f"盈亏平衡: 六腿跌至 {inp['perp'] / inp['k_retain']:.2f} 亿时普通股股东归零")
    dps_l, dps_m = eps["l"] * inp["payout"], eps["m"] * inp["payout"]
    print(f"L 档分红: DPS {dps_l:.4f} vs 当前 {inp['dps']} ({dps_l / inp['dps'] - 1:+.1%}); L 隐含股息率 {dps_l / L:.2%}; "
          f"中枢 DPS {dps_m:.4f}, M 上股息率 {dps_m / M:.2%} — 股息不是地板 (A14)")
    print(f"红利尺交叉 (A17): 隐含倍数 payout/yield = {pe_div:.3f} (留存分支隐含 g {g_div:+.2%}, conditioned={g_div_ok} 病态区读数, 在证据区间内) "
          f"vs Gordon {pe['m']:.3f}; 三档分叉 (情景口径) "
          + " / ".join(f"{(div[t] - a) / a:+.1%}" for t, a in zip(TIERS, (scenario_l, M, H)))
          + f"; yield 分解 = 国债 {inp['bond10y']:.3%} + 风险溢价 {inp['req_yield_a'] - inp['bond10y']:.3%}")
    ddm_mid = dps_m * (1 + g2) / (r - g2)
    ddm_peak = inp["dps"] * (1 + g2) / (r - g2)
    px_h_cny = inp["price_h"] * inp["hkdcny"]
    print(f"DDM 对照: 中枢 D0 {dps_m:.4f} → {ddm_mid:.2f} CNY = {ddm_mid / inp['hkdcny']:.2f} HKD ({ddm_mid / M - 1:+.1%} vs M); "
          f"峰值 D0 {inp['dps']} → {ddm_peak:.2f} CNY = {ddm_peak / inp['hkdcny']:.2f} HKD; "
          f"现价隐含股息增长 (中枢 D0 / 峰值 D0): A {(inp['price'] * r - dps_m) / (inp['price'] + dps_m):+.2%} / {(inp['price'] * r - inp['dps']) / (inp['price'] + inp['dps']):+.2%}, "
          f"H {(px_h_cny * r - dps_m) / (px_h_cny + dps_m):+.2%} / {(px_h_cny * r - inp['dps']) / (px_h_cny + inp['dps']):+.2%}")

    d = decompose((scenario_l, M, H), (pe["l"], pe["m"], pe["h"]))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  (scenario L {scenario_l:.2f})")
    print(f"L/M={L / M:.2f} (情景口径 {scenario_l / M:.2f}) H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%} (情景口径 {(H - scenario_l) / (2 * M):.1%})")
    print(f"分子比 L/M=n/a (地板胜出; 情景口径 {d['num_lm']:.3f}) H/M={d['num_hm']:.3f} | 倍数比 L/M={d['pe_lm']:.3f} H/M={d['pe_hm']:.3f} (flat)")
    print(f"flat-multiple ladder (A2e-2c, all tiers at PE_M={pe['m']:.3f}): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    pe_px_a = inp["price"] / eps["m"]
    g_px, g_px_ok = implied_g_retaining(pe_px_a, roe["m"], r)
    print(f"A股 price={inp['price']} zone={zone} | 现价 = {pe_px_a:.2f}x 中枢 EPS ({inp['price'] / inp['eps_ttm']:.2f}x TTM, {inp['price'] / inp['cons_fy27_mean']:.2f}x FY27 均值); "
          f"PE_M 下隐含 EPS {inp['price'] / pe['m']:.4f} = 中枢 × {inp['price'] / pe['m'] / eps['m']:.2f}; "
          f"留存分支反解 g {g_px:+.2%} ({'越 cap, 不可达' if g_px > G_CAP else 'conditioned=' + str(g_px_ok)})"
          + (f"; 溢价 (P-H)/H = {(inp['price'] - H) / H:+.1%}" if inp["price"] > H else ""))
    pe_px_h = px_h_cny / eps["m"]
    g_hk, g_hk_ok = implied_g_retaining(pe_px_h, roe["m"], r)
    print(f"H股 L={hk['l']:.2f} M={hk['m']:.2f} H={hk['h']:.2f} A={A_h:.2f} B={B_h:.2f} price={inp['price_h']} zone={zone_h} | "
          f"H 股现价 = {pe_px_h:.2f}x 中枢 ({px_h_cny / inp['eps_ttm']:.2f}x TTM, {px_h_cny / inp['cons_fy27_mean']:.2f}x FY27 均值); "
          f"PE_M 下隐含 EPS {px_h_cny / pe['m']:.4f} = 中枢 × {px_h_cny / pe['m'] / eps['m']:.2f}; 留存分支反解 g {g_hk:+.2%} (病态区读数, conditioned={g_hk_ok}) "
          f"(H 股 own-year 近两年中位 {inp['pe_hk_own_mid']} 仅参照)")
    div_h_m = eps["m"] * inp["payout"] / inp["req_yield_h"] / inp["hkdcny"]
    print(f"_AXIS.southbound-repricing: H/A={ha_live:.3f} (0.433 -> {ha_live:.3f}); 双报契约 ✓; 南向读法: H 股按中枢 × ~1/r, A 股按 1.36× 中枢的分子; "
          f"红利尺 H {div_h_m:.2f} HKD 交叉")
    print(f"带边反解 g (裁决顺序 ③, 留存分支, 中枢 ROE {roe['m']:.1%}): 下沿 {inp['pe_own_min']}x → BLOCKED "
          f"(留存 {g_edge_lo:+.1%} 越 r 不是读数; 全派息读法 {g_edge_lo_full:+.2%}); "
          f"上沿 {inp['pe_own_max']}x ↔ {g_edge_hi_raw:+.2%} → 截 {g_edge_hi:+.2%}; g2 {g2:+.2%} ∈ (0, {g_edge_hi:+.2%}] ✓")
    for g, lab in probe.items():
        b, _ = band_at(g)
        hb = tuple(v / inp["hkdcny"] for v in b)
        print(f"{lab} g2={g:+.2%} (PE {perpetual_pe(g, roe['m'], r):.2f}): A {'/'.join(f'{x:.2f}' for x in b)} A/B {cut_points(*b)[0]:.2f}/{cut_points(*b)[1]:.2f} "
              f"zone={zone_of(inp['price'], *b)} | H {'/'.join(f'{x:.2f}' for x in hb)} zone={zone_of(inp['price_h'], *hb)}")
    for dg in (-0.01, 0.01):
        g = min(g2 + dg, G_CAP)
        b, _ = band_at(g)
        hb = tuple(v / inp["hkdcny"] for v in b)
        print(f"敏感性 g2 {dg:+.0%} ({g:+.2%}{' 截 cap' if g2 + dg > G_CAP else ''}): A {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)} | "
              f"H zone={zone_of(inp['price_h'], *hb)}")
    # A7: the tiers keep each year's own perpetual coupon; re-basing to today's is a coordinate.
    perp_by_year = {2023: 29.52, 2024: 29.23, 2025: 27.74}
    rebased = [eps[t] + (perp_by_year[y] - inp["perp"]) / inp["shares"] for t, y in zip(TIERS, (2023, 2024, 2025))]
    print(f"敏感性: 永续债利息重设至 {inp['perp']} (A7) -> EPS {'/'.join(f'{x:.4f}' for x in rebased)} -> "
          f"{max(rebased[0] * pe['l'], floor):.2f}/{rebased[1] * pe['m']:.2f}/{rebased[2] * pe['h']:.2f} "
          f"zone={zone_of(inp['price'], max(rebased[0] * pe['l'], floor), rebased[1] * pe['m'], rebased[2] * pe['h'])}; "
          f"不兜底 -> {scenario_l:.2f}/{M:.2f}/{H:.2f} zone={zone_of(inp['price'], scenario_l, M, H)}")
    # 校验步骤 17 (A20): the tariff is the residual; these are pressure coordinates, not tiers.
    for lab, f, tf in (("中枢煤 (FY2024 fuel) + FY2024 电价 [复现 M]", inp["fuel_fy24"], inp["tariff_fy24"]),
                       ("中枢煤 + 2026H1 电价 463.02 [压力坐标]", inp["fuel_fy24"], inp["tariff_now"]),
                       ("两驱动同取 7y 均值 [regime 混合]", fuel_mid, TARIFF_7Y_MEAN),
                       ("FY2022 亏损 regime", inp["fuel_fy22"], inp["tariff_fy22"])):
        six, e = bridge_eps(inp, f, tf)
        print(f"A20 线性桥 {lab}: 价差 {tf - f:.2f} → 六腿 {six:.1f} → EPS {e:.4f} → {e * pe['m']:.2f}")
    # 校验步骤 18: coordinates that are NOT the deck, each named for why not.
    v4 = tuple(inp[k] * PE_V4 for k in ("cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi"))
    print(f"对照 v4 峰值分子带 (FY2027 共识三点 × {PE_V4}): A {'/'.join(f'{x:.2f}' for x in v4)} zone={zone_of(inp['price'], *v4)} | "
          f"H zone={zone_of(inp['price_h'], *(x / inp['hkdcny'] for x in v4))} — 峰值分子的坐标 (A16)")
    pe_v3 = 1.0 / (r - G2_OLD_BRANCH)  # full-payout branch: payout capped at 100%
    v3 = tuple(inp[k] * pe_v3 for k in ("cons_fy27_lo", "cons_fy27_mean", "cons_fy27_hi"))
    print(f"对照 v3 全派息分支 {G2_OLD_BRANCH:+.2%} flat {pe_v3:.2f}x 于共识三点: A {'/'.join(f'{x:.2f}' for x in v3)} "
          f"zone={zone_of(inp['price'], *v3)} — 分支错误的坐标 (A15/A16)")
    for label, g in (("对照 v4 的 +2.55% 套中枢分子", G2_V4),
                     ("对照 跨域交叉中位 g_peer_cross", inp["g_peer_cross"])):
        b, _ = band_at(g)
        hb = tuple(v / inp["hkdcny"] for v in b)
        print(f"{label}: g2={g:+.2%} A {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)} | "
              f"H {'/'.join(f'{x:.2f}' for x in hb)} zone={zone_of(inp['price_h'], *hb)}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
