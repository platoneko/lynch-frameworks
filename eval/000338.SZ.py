#!/usr/bin/env python3
"""000338.SZ (Weichai Power) valuation eval — recompute anchors from frameworks/000338.SZ.md.

frameworks/000338.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: weichai_asymmetric_sotp_runrate_gordon_v4

Main ruler: an asymmetric three-leg SOTP.
  * core     = attributable NP - KION equity NP - large-bore engine NP,
               on a GENERATED multiple (valuation-rules「永续增长口径」), not an
               own-year quantile
  * KION     = KION's own net income x 46.52% (2026 interim, note to the
               subsidiaries table) x KION's own forward PE, because that leg
               is priced in Frankfurt, not by China's truck cycle
  * M-series = measured units x realized unit price x net margin, on the core
               M-tier multiple — at 3% of group revenue it is a product line in
               the base, not a growth business

How the core multiple is generated (A14):
  * ROE_x = np_x / equity (no leg equity is disclosed; company ROE stands in).
  * r is the basket rate the framework names on the r_perp row (篮 4 龙头制造
    10%, A15); the script reads the basket tag and refuses a value that is not
    that basket's.  g2 is capped at g_cap(r) = min(6%, r - 4%).
  * M / H: perpetual_pe(g2_x, ROE_x, r).  The tier-1 g2 source — the
    truck/engine peer cross-section reverse-solved on the same ruler, median
    +0.37% — generates 10.10 / 10.18x, BELOW the lowest monthly TTM PE this
    ticker printed in five years (10.26, 2024-09).  裁决顺序 ③ therefore
    replaces it with the g that reverse-solves to that band edge at each
    tier's ROE (0.90% / 0.51%, labelled 自身实测带反解), so M and H both sit on
    the edge: flat 10.26x, g reversed with ROE — the cyclical shape check (⑤)
    passes as a result.  The script re-derives both edge g's and refuses a
    stated g2 that disagrees, and proves the tier-1 peer g still lands below
    the band (otherwise ③ no longer applies and the ticker goes back to tier 1).
  * L is the FY2022 TROUGH (ROE 5.1% < r).  A trough numerator paired with the
    steady g2 prices the trough as permanent (the cycle counted twice), and a
    Gordon recovery g gets eaten by the retention term at a 5% ROE — the exact
    failure that blocked the v1 migration.  valuation-rules「谷底档」 instead:
    recovery_two_stage_pe(g1, n, g2, ROE_mid, r) with g1 = the ticker's OWN
    realised trough-to-mid CAGR ((np_m / np_l)^(1/n) - 1 = 32.0%) over the
    realised n = 3.5 years (FY2022 window centre -> TTM window centre), stage 1
    paid out 100%, stage 2 = mid-cycle ROE + the same steady g2.  Both g1 and n
    are facts in the filings, so check_transition_years does not apply.  The
    trough year is t=1 (same valuation date as the perpetual_pe tiers, A2e-3);
    the script also prints the multiple on the post-recovery (mid-cycle)
    numerator, which is how 表1 reports a two-stage leg.

V_opt is three named options, none of which enters the base:
  * the 2,600 M-series units beyond the measured 13.4k run-rate (JPM's 2027
    capacity extrapolation), on the core M multiple.  The 13.4k units already
    in the leg are NOT re-rated (A2e-7c-4/5).
  * SOFC at the 2027 200 MW capacity ceiling x Bloom's realised NI/MW x the
    steady-state Gordon on BE.US's own g2 / roe_m (re-derived cross-file from
    BE's Inputs) at THIS ticker's basket r — the option is Weichai's own 200 MW
    plant, so it carries Weichai's 篮 4 rate, not BE's 篮 7 15% — discounted one
    year.  BE's own M multiple is two_stage_pe and carries Bloom's FY28 +60%
    transition year; a capacity CEILING does not grow a further 60%, so only
    the stage-2 Gordon is borrowed.  The 篮 7 reading (9.40x) is printed as a
    disclosure line only.
  * M-series aftermarket at k=1 x own realised M-series revenue x Cummins'
    realised aftermarket share (26%), on the core M multiple.

The former own-year inverse band (18.42 / 12.34 / 11.47, A2) is a cross-ruler:
printed, never an anchor.  Consensus is deliberately unused in the base: no
year has >= 2 named houses (A13).

Guards beyond the anchor comparison: band-edge re-derivation, tier-1-still-
outside proof, guardrail, trough-tier precondition (ROE_L < r), shape check,
flat-multiple ladder, KION-share band, SOFC cross-check against BE.US, p-leak
scan, southbound-axis mount.

Run:  python3 eval/000338.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.gordon import (  # noqa: E402
    check_g_cap, check_r, g_cap, implied_g, perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000338.SZ.md"
BE_FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "BE.US.md"
FORMULA_ID = "weichai_asymmetric_sotp_runrate_gordon_v4"
YI = 1e8
TIERS = ("l", "m", "h")

# The KION leg is the reason this ticker is not valued on a group PE.
# If it stops being ~10% of profit, §1 属性 A has to be rewritten.
KION_SHARE_BAND = (0.08, 0.12)
BLOOM_NI_TOL = 0.10
MIN_R_MINUS_G = 0.02      # 裁决顺序 ①
G_EDGE_TOL = 5e-5         # A14: stated g2_x must equal implied_g(pe_own_min, ROE_x, r)
GUARDRAIL_SLACK = 0.01    # band-edge multiples sit on the edge by construction
SHAPE_TOL = 0.03          # 校验步骤 5: M->H same-direction only by ROE mechanics

REQUIRED = [
    "price", "price_h", "shares", "bps", "fx_hkdcny", "fx_eurcny",
    "np_l", "np_m", "np_h",
    "kion_np_h1_eur", "kion_stake", "kion_l_factor", "pe_kion",
    "ms_units_l", "ms_units_m", "ms_units_h", "ms_price", "ms_npm",
    "equity", "r_perp", "g2_core_peer", "g2_m", "g2_h", "n_rec_l",
    "pe_own_min", "pe_own_max", "pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h",
    "pe_sofc", "sofc_mw_h", "bloom_ni_fy26", "bloom_cap_mw", "fx_usdcny",
    "r_disc", "sofc_lag", "aft_share_peer",
]
# Reference-only rows (校验步骤 11): in Inputs, never in an anchor path.
NOT_FORMULA = ("pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h", "g2_core_peer")


def legs(inp: dict[str, float], tag: str, pe_core: float, pe_ms: float) -> dict[str, float]:
    """One scenario -> three legs -> market value -> per-share anchor.

    M-series units are the measured run-rate only: L = FY2025 actual, M/H
    frozen at the 2026H1 annualised 13,400.  The unverified 16k lives in
    V_opt.  The KION leg keeps its own multiple because it is an external
    market price, not a policy choice of this framework.
    """
    kion = (
        inp["kion_np_h1_eur"] * 2.0 * inp["kion_stake"] * inp["fx_eurcny"]
        * (inp["kion_l_factor"] if tag == "l" else 1.0)
    )
    units = inp["ms_units_l"] if tag == "l" else inp["ms_units_m"]
    ms_np = units * inp["ms_price"] * inp["ms_npm"]
    core = inp[f"np_{tag}"] - kion - ms_np
    mv = core * pe_core + kion * inp["pe_kion"] + ms_np * pe_ms
    return {"kion": kion, "ms_np": ms_np, "core": core, "mv": mv,
            "anchor": mv / inp["shares"], "units": units,
            "core_ps": core * pe_core / inp["shares"],
            "kion_ps": kion * inp["pe_kion"] / inp["shares"],
            "ms_ps": ms_np * pe_ms / inp["shares"]}


def ms_increment_v_opt(inp: dict[str, float], pe_m: float) -> float:
    """Units beyond the measured run-rate, on the core M multiple (A4)."""
    extra = inp["ms_units_h"] - inp["ms_units_m"]
    return extra * inp["ms_price"] * inp["ms_npm"] * pe_m / inp["shares"]


def aftermarket_v_opt(inp: dict[str, float], pe_m: float) -> float:
    """k=1 x own measured M-series revenue x Cummins' realised aftermarket share (A8)."""
    rev = inp["ms_units_m"] * inp["ms_price"]
    return rev * inp["aft_share_peer"] * inp["ms_npm"] * pe_m / inp["shares"]


def sofc_v_opt(inp: dict[str, float]) -> float:
    """2027 200 MW ceiling x Bloom FY26 NI/MW x BE.US pe_m, discounted sofc_lag years."""
    ni_usd = inp["sofc_mw_h"] * (inp["bloom_ni_fy26"] / inp["bloom_cap_mw"])
    v_t = ni_usd * inp["fx_usdcny"] * inp["pe_sofc"] / inp["shares"]
    return v_t / (1.0 + inp["r_disc"]) ** inp["sofc_lag"]


def bloom_crosscheck(inp: dict[str, float], r: float) -> tuple[list[str], dict[str, float]]:
    """SOFC unit economics and multiple both come from BE.US's framework (A12).

    BE's Inputs carry no multiple (its tiers are Gordon-generated), so the
    borrowed multiple is re-derived from BE's own g2 / roe_m with the repo's
    perpetual_pe at this ticker's basket r — BE's stage-2 steady state on
    Weichai's own plant, stated to 2 dp in `pe_sofc`.  Reading BE's Outputs
    anchor instead would import BE's FY28 transition year and BE's 篮 7 rate,
    and go stale whenever BE republishes.  Returns BE's inputs too, so the
    caller can print the 篮 7 reading as a disclosure.
    """
    if not BE_FRAMEWORK.exists():
        return [f"missing {BE_FRAMEWORK.name} — SOFC ceiling has no peer trajectory"], {}
    be = parse_inputs(BE_FRAMEWORK.read_text(encoding="utf-8"))
    missing = [k for k in ("eps_fy26_m", "shares", "g2", "roe_m", "r_perp") if k not in be]
    if missing:
        return [f"BE.US missing {missing} — cannot cross-check the SOFC option"], {}
    errors: list[str] = []
    peer = be["eps_fy26_m"] * be["shares"]
    if abs(peer - inp["bloom_ni_fy26"]) > BLOOM_NI_TOL * inp["bloom_ni_fy26"]:
        errors.append(
            f"bloom_ni_fy26 {inp['bloom_ni_fy26']:.3e} vs BE.US "
            f"eps_fy26_m×shares {peer:.3e} (>{BLOOM_NI_TOL:.0%})"
        )
    be_pe_m = round(perpetual_pe(be["g2"], be["roe_m"], r), 2)
    if abs(be_pe_m - inp["pe_sofc"]) > 1e-9:
        errors.append(
            f"pe_sofc {inp['pe_sofc']} != BE.US steady-state M Gordon at this ticker's r {be_pe_m} "
            f"(perpetual_pe(g2 {be['g2']:.2%}, roe_m {be['roe_m']:.2%}, r {r:.0%})) — re-read the source framework (A12)"
        )
    return errors, be


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports the H-share companion band and live H/A.

    The southbound axis locks no numerator and no g here (A11: the Gordon
    mechanism overrides its tier hint); what it still locks is the reporting
    contract its own §4 direction check depends on.
    """
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "000338.SZ" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append("000338.SZ is not declared on _AXIS.southbound-repricing.md — "
                      "a mount has to exist on both sides")
    if "H 股对照带" not in md:
        errors.append("framework lacks the H-share companion band (axis §3 rule 3)")
    if not re.search(r"H/A\s*=\s*\*{0,2}[01]\.\d+", md):
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
    errors += check_southbound_mount(md)
    r = inp["r_perp"]
    baskets = parse_baskets(md)

    # --- Step 1: numerator ladders ------------------------------------------
    errors += ladder("numerator (np)", inp["np_l"], inp["np_m"], inp["np_h"])
    if not (inp["ms_units_l"] <= inp["ms_units_m"] <= inp["ms_units_h"]):
        errors.append("M-series unit ladder violated")
    if errors:
        return report(errors, "FAIL (ladders)")

    # --- Step 2: tier ROE, then the generated core multiple (A14) -----------
    roe = {t: inp[f"np_{t}"] / inp["equity"] for t in TIERS}
    # The core leg is one operating basket (篮 4 龙头制造, A15): the framework
    # names it on the r_perp row and r must be that basket's value.  r_disc
    # only bridges the SOFC option one year: untagged (not a leg), same value.
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (A15)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc {inp['r_disc']} != r_perp {r} (A15: 同值)")
    for t in ("m", "h"):
        errors += check_g_cap(inp[f"g2_{t}"], r, f"g2_{t}")
        if r - inp[f"g2_{t}"] < MIN_R_MINUS_G:
            errors.append(f"g2_{t} {inp[f'g2_{t}']:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    # 校验步骤 2: g2 of M / H must be the band-edge reverse-solve at that
    # tier's ROE, and rule ③ applies only while the tier-1 peer g still
    # generates a multiple below the band.
    g_edge = {t: implied_g(inp["pe_own_min"], roe[t], r)[0] for t in ("m", "h")}
    for t in ("m", "h"):
        if abs(g_edge[t] - inp[f"g2_{t}"]) > G_EDGE_TOL:
            errors.append(
                f"g2_{t} {inp[f'g2_{t}']:+.5f} != band-edge implied g {g_edge[t]:+.5f} at ROE {roe[t]:.2%} "
                "(A14: 自身实测带反解 must be re-derived, not carried)"
            )
    pe_peer = {t: perpetual_pe(inp["g2_core_peer"], roe[t], r) for t in ("m", "h")}
    if all(p >= inp["pe_own_min"] for p in pe_peer.values()):
        errors.append(
            f"tier-1 peer g {inp['g2_core_peer']:+.2%} now generates in-band multiples "
            f"{pe_peer['m']:.2f}/{pe_peer['h']:.2f} >= {inp['pe_own_min']} — "
            "裁决顺序 ③ no longer applies; go back to 同业反解 (A14 证伪点)"
        )
    # 校验步骤 3: the trough-tier template only applies to a trough.
    if roe["l"] >= r:
        errors.append(
            f"ROE_L {roe['l']:.1%} >= r {r:.0%}: L is not a trough tier — recovery_two_stage_pe "
            "no longer the right template (valuation-rules「谷底档」), back to the conversation"
        )
    if errors:
        return report(errors, "FAIL (band-edge g / trough tier)")

    n_rec = inp["n_rec_l"]
    g1 = (inp["np_m"] / inp["np_l"]) ** (1.0 / n_rec) - 1.0
    pe_core = {
        "l": recovery_two_stage_pe(g1, n_rec, inp["g2_m"], roe["m"], r),
        "m": perpetual_pe(inp["g2_m"], roe["m"], r),
        "h": perpetual_pe(inp["g2_h"], roe["h"], r),
    }
    # 校验步骤 4: guardrail.
    for t in TIERS:
        if not (inp["pe_own_min"] - GUARDRAIL_SLACK <= pe_core[t] <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: generated core PE_{t.upper()} {pe_core[t]:.3f} outside realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — STOP, do not force g"
            )
    if errors:
        return report(errors, "FAIL (guardrail)")
    # 校验步骤 5: shape is a RESULT (裁决顺序 ⑤): g reversed across M/H, PE
    # reversed-or-flat with the trough tier above the mid.
    if inp["g2_m"] < inp["g2_h"]:
        errors.append(f"g2_m {inp['g2_m']:+.4f} < g2_h {inp['g2_h']:+.4f}: g not reversed (cyclical, 裁决顺序 ⑤)")
    if not (pe_core["l"] > pe_core["m"]):
        errors.append(f"trough-tier PE {pe_core['l']:.2f} <= mid {pe_core['m']:.2f}: recovery segment adds nothing (A14)")
    if pe_core["h"] > pe_core["m"] * (1.0 + SHAPE_TOL):
        errors.append(
            f"PE_H {pe_core['h']:.2f} exceeds PE_M {pe_core['m']:.2f} by more than ROE mechanics allow "
            f"({SHAPE_TOL:.0%}) — same-direction multiple on a cyclical (裁决顺序 ⑤)"
        )

    S = {t: legs(inp, t, pe_core[t], pe_core["m"]) for t in TIERS}

    # --- Step 3: the asymmetry claim must still hold -------------------------
    kion_share = S["m"]["kion"] / inp["np_m"]
    lo, hi = KION_SHARE_BAND
    if not (lo <= kion_share <= hi):
        errors.append(
            f"KION leg is {kion_share:.1%} of M numerator, outside {lo:.0%}-{hi:.0%} "
            "— §1 属性 A (35% revenue / ~10% profit) no longer holds"
        )
    if S["l"]["core"] <= 0:
        errors.append("L-scenario core profit <= 0 — check 口径")

    # --- Step 4: flat-multiple ladder (校验步骤 6) ----------------------------
    flat = {t: legs(inp, t, pe_core["m"], pe_core["m"])["anchor"] for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    # --- Step 5: anchors ------------------------------------------------------
    L, M, H = (S[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    v_ms = ms_increment_v_opt(inp, pe_core["m"])
    v_sofc = sofc_v_opt(inp)
    v_aft = aftermarket_v_opt(inp, pe_core["m"])
    v_opt = v_ms + v_sofc + v_aft
    # M world: units frozen at the measured 13,400 (anchor = the interim
    # report) and SOFC still at MW-scale verification -> nothing vests.
    p_k = (0.0, 0.0, 1.0)
    adj_band = [S[t]["anchor"] + pk * v_opt for t, pk in zip(TIERS, p_k)]
    if abs(adj_band[0] - L) > 1e-9 or abs(adj_band[1] - M) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L/M {adj_band[0]:.4f}/{adj_band[1]:.4f} != {L:.4f}/{M:.4f}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    if inp["bloom_cap_mw"] <= 0 or inp["sofc_mw_h"] <= 0:
        errors.append("SOFC capacity inputs must be positive")
    if inp["sofc_mw_h"] >= inp["bloom_cap_mw"]:
        errors.append(
            f"sofc_mw_h {inp['sofc_mw_h']:.0f} MW is not below Bloom's "
            f"{inp['bloom_cap_mw']:.0f} MW plant — the ceiling is no longer a "
            "fraction of a realised trajectory"
        )
    be_errors, be = bloom_crosscheck(inp, r)
    errors += be_errors
    missing_ref = [k for k in NOT_FORMULA if k not in inp]
    if missing_ref:
        errors.append(f"reference rows missing from Inputs: {missing_ref}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'归母':>10}{'凯傲腿':>9}{'大缸径台数':>12}{'大缸径净利':>11}"
          f"{'核心盘':>10}{'ROE':>8}{'核心PE':>8}{'市值':>11}{'锚点':>8}")
    for t in TIERS:
        s = S[t]
        print(f"{t.upper():<3}{inp[f'np_{t}'] / YI:10.1f}{s['kion'] / YI:9.2f}"
              f"{s['units']:12.0f}{s['ms_np'] / YI:11.2f}{s['core'] / YI:10.1f}"
              f"{roe[t]:8.1%}{pe_core[t]:8.2f}{s['mv'] / YI:11.0f}{s['anchor']:8.2f}")
    print(f"表1 per-share: " + " | ".join(
        f"{t.upper()} core {S[t]['core_ps']:.2f} + KION {S[t]['kion_ps']:.2f} + MS {S[t]['ms_ps']:.2f}" for t in TIERS))
    cap = g_cap(r)
    print(f"倍数生成 (A14): r={r:.0%} (篮 {baskets['r_perp']}); 同业反解 g2_core_peer={inp['g2_core_peer']:+.2%} -> PE_M/H "
          f"{pe_peer['m']:.2f}/{pe_peer['h']:.2f} < 护栏下沿 {inp['pe_own_min']} -> 裁决顺序 ③ 带边反解 "
          f"g2 M {g_edge['m']:+.2%} / H {g_edge['h']:+.2%} (自身实测带反解, cap {cap:.0%}) -> "
          f"PE_M/H {pe_core['m']:.2f}/{pe_core['h']:.2f}; 护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓")
    g_hi = {t: min(implied_g(inp["pe_own_max"], roe[t], r)[0], cap) for t in ("m", "h")}
    print(f"带即证据: 带边 g 区间 M [{g_edge['m']:+.2%}, {g_hi['m']:+.2%}] | H [{g_edge['h']:+.2%}, {g_hi['h']:+.2%}] (上沿反解截 cap)")
    print(f"谷底档 L (valuation-rules「谷底档」): ROE_L {roe['l']:.1%} < r; g1 = ({inp['np_m'] / YI:.2f}/{inp['np_l'] / YI:.1f})^(1/{n_rec:g}) - 1 = {g1:+.2%}, "
          f"n = {n_rec:g}, 段二 ROE_M {roe['m']:.1%} + g2 {inp['g2_m']:+.2%} -> recovery_two_stage_pe = {pe_core['l']:.2f}x "
          f"(谷底 x 1/r = {inp['np_l'] / inp['shares'] * 10:.2f}/股 压力坐标)")
    # A2e-3: trough year = t=1; 表1 reports the leg on the post-recovery numerator.
    grown = (1.0 + g1) ** n_rec
    print(f"  估值时点 t=1 = 谷底年; 回归后中枢分子口径: 核心盘 {S['l']['core'] * grown / YI:.2f}亿 x {pe_core['l'] / grown:.2f}x "
          f"(= 中枢 Gordon {pe_core['m']:.2f}x 折 {n_rec:g} 年 {pe_core['m'] / (1 + r) ** n_rec:.2f} + 回归路径派息 {(pe_core['l'] - pe_core['m'] * grown / (1 + r) ** n_rec) / grown:.2f}); "
          f"谷底分子口径 {pe_core['l']:.2f}x 只对护栏 (TTM 带同基)")
    print(f"形状结果检查 (裁决顺序 ⑤): PE {pe_core['l']:.2f} > {pe_core['m']:.2f} ≈ {pe_core['h']:.2f} (M->H {pe_core['h'] / pe_core['m'] - 1:+.2%} ROE 机械); "
          f"g M {inp['g2_m']:+.2%} >= H {inp['g2_h']:+.2%} ✓")
    print(f"KION leg = {kion_share:.1%} of M numerator (band {lo:.0%}-{hi:.0%}) — "
          f"35% of revenue, so the SOTP is warranted")
    print(f"flat-multiple @PE_M={pe_core['m']:.2f}: L={flat['l']:.2f} M={flat['m']:.2f} H={flat['h']:.2f}")

    num_l, num_h = inp["np_l"] / inp["np_m"], inp["np_h"] / inp["np_m"]
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    ni_usd = inp["sofc_mw_h"] * (inp["bloom_ni_fy26"] / inp["bloom_cap_mw"])
    print(f"SOFC  {inp['sofc_mw_h']:.0f} MW x ${inp['bloom_ni_fy26'] / inp['bloom_cap_mw']:,.0f}/MW"
          f" = ${ni_usd / 1e6:.0f}M NI  ->  V_sofc={v_sofc:.2f}  (lag {inp['sofc_lag']:.0f}y)")
    print(f"表3  V_opt={v_opt:.2f} (ms {v_ms:.2f} = {inp['ms_units_h'] - inp['ms_units_m']:.0f} 台 x {pe_core['m']:.2f}x + sofc {v_sofc:.2f} @ BE.US 稳态 M Gordon {inp['pe_sofc']:g}x + aftermarket {v_aft:.2f} @ {inp['aft_share_peer']:.0%} of M-series rev)"
          f"  p_k={p_k[0]:.2f}/{p_k[1]:.2f}/{p_k[2]:.2f}  "
          + "  ".join(
              f"{n}:{S[t]['anchor']:.2f}+{pk:.2f}xV={a:.2f}"
              for n, t, pk, a in zip("LMH", TIERS, p_k, adj_band)))
    if v_opt > 0 and inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}; H+V={H + v_opt:.2f} "
              f"+V zone={zone_of(inp['price'], L, M, H + v_opt)}"
              + (f"; 溢价 (P-H-V)/(H+V) = {(inp['price'] - H - v_opt) / (H + v_opt):+.1%}" if inp["price"] > H + v_opt else ""))
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | "
          f"倍数比 L/M={(L / M) / num_l:.2f} H/M={(H / M) / num_h:.2f}")
    g_px, g_px_ok = implied_g(inp["price"] / (inp["np_m"] / inp["shares"]), roe["m"], r)
    print(f"price={inp['price']} zone={zone} | 现价 = {inp['price'] / (inp['np_m'] / inp['shares']):.2f}x TTM, "
          f"隐含永续 g {g_px:+.2%} (conditioned={g_px_ok}{', > cap' if g_px > cap else ''})")

    # 校验步骤 11: cross-rulers, printed and never anchored.
    own = {t: legs(inp, t, inp[f"pe_ownyear_{t}"], inp["pe_ownyear_m"])["anchor"] for t in TIERS}
    print(f"交叉尺① own-year 反向带 {inp['pe_ownyear_l']}/{inp['pe_ownyear_m']}/{inp['pe_ownyear_h']} (A2): "
          f"{own['l']:.2f}/{own['m']:.2f}/{own['h']:.2f}, 现价 zone={zone_of(inp['price'], own['l'], own['m'], own['h'])}")
    zero = {t: legs(inp, t, 1.0 / r, 1.0 / r)["anchor"] for t in TIERS}
    print(f"交叉尺② 零增长 1/r={1 / r:.0f}x (L = 谷底永续): {zero['l']:.2f}/{zero['m']:.2f}/{zero['h']:.2f}")
    sens = {}
    for dg in (-0.01, 0.01):
        pe2 = {
            "l": recovery_two_stage_pe(g1, n_rec, inp["g2_m"] + dg, roe["m"], r),
            "m": perpetual_pe(inp["g2_m"] + dg, roe["m"], r),
            "h": perpetual_pe(inp["g2_h"] + dg, roe["h"], r),
        }
        band2 = [legs(inp, t, pe2[t], pe2["m"])["anchor"] for t in TIERS]
        v2 = (v_ms + v_aft) * pe2["m"] / pe_core["m"] + v_sofc
        sens[dg] = (band2, band2[2] + v2)
    print("敏感性: g2 ±1pp -> "
          + " | ".join(f"{dg:+.0%}: {b[0]:.2f}/{b[1]:.2f}/{b[2]:.2f} (H+V {hv:.2f})" for dg, (b, hv) in sens.items()))
    fx = inp["fx_hkdcny"]
    print(f"H股对照(HKD): L={L / fx:.2f} M={M / fx:.2f} H={H / fx:.2f} "
          f"| price_h={inp['price_h']} zone_h={zone_of(inp['price_h'], L / fx, M / fx, H / fx)}")
    print(f"H/A = {inp['price_h'] * fx / inp['price']:.3f}")

    # Disclosure lines (never anchors): implied r at the price on the M-tier
    # single-stage Gordon, the PB floor (disclosed, not max()'d into L), and
    # the SOFC option re-read at BE.US's own 篮 7 rate.
    r_implied = inp["g2_m"] + (r - inp["g2_m"]) * M / inp["price"]
    print(f"隐含 r(P) = g2_m + (r - g2_m) x M/P = {r_implied:.1%} (篮 {baskets['r_perp']} r {r:.0%})")
    print(f"地板 (只披露, 不 max): PB 1.0 x BPS = {inp['bps']:.2f} vs L {L:.2f}")
    if be:
        pe_sofc_be = perpetual_pe(be["g2"], be["roe_m"], be["r_perp"])
        v_sofc_be = v_sofc * pe_sofc_be / inp["pe_sofc"]
        v_opt_be = v_ms + v_sofc_be + v_aft
        print(f"对照 BE.US 篮 r {be['r_perp']:.0%}: pe_sofc {pe_sofc_be:.2f}x -> SOFC {v_sofc_be:.2f}, V_opt {v_opt_be:.2f}, "
              f"H+V {H + v_opt_be:.2f}, 市价隐含 p {(inp['price'] - H) / v_opt_be:.2f} (只披露, 表3 按 pe_sofc {inp['pe_sofc']:g}x)")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
