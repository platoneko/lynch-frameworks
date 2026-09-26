#!/usr/bin/env python3
"""600309.SH (Wanhua Chemical) valuation eval.

frameworks/600309.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: wanhua_segment_margin_ladder_gp_bridge_gordon_v3

The scenario variable is the *spread*, not volume.  Revenue is frozen at the
2026H1 level in all three scenarios; only the three segment gross margins move,
and all three sets are numbers the company itself has already printed:

    L = 2025H1 actuals   (PU 26% / petchem  0% / new materials  9%)
    M = 2026H1 actuals   (PU 27% / petchem  7% / new materials 16%)
    H = 2026Q2 actual blended margin 19%, which implies PU 33.04%

Gross profit -> annualise -> less opex (the gross-to-operating gap, held flat)
-> operating profit -> x conv (tax + minority, measured on 2026H1) -> net
profit to parent -> / shares -> x that tier's Gordon multiple.

The multiple is GENERATED, not picked from history (valuation-rules「永续增长
口径」): PE_x = min(1, 1 - g_x/ROE_x) / (r - g_x), r = the basket r of the single
operating leg (篮 4 龙头制造 10%, read from Inputs and checked against the `篮 N`
tag via parse_baskets / check_r), ROE_x = tier net profit / one `equity` field.  The tier-1 g2 source — the A-share chemicals
cross-section reverse-solved on the same ruler, median -0.41% — generates
9.61 / 9.61 / 8.76x, all BELOW the lowest monthly PE this ticker has printed in
five years (10.45, 2022-05).  Under the 2026-09-14 裁决顺序 that is no longer a
stop: rule ③ says a peer g that lands outside the own band is replaced by the g
that reverse-solves to the nearest band edge at that tier's ROE — that was
v3.  v4 (A15, 2026-09-14): the peer cluster fails the same-world gate (its
implied g is <= 0 while this ticker's >=2-house consensus rises), and PE
quantiles are not a valid target either (each quantile was printed at a
different earnings level: the median on trough years, the minimum on peak
earnings).  g2 is therefore reverse-solved from EPS-MATCHED realised prints:

  H  g2_h = g_print_h, the median implied g over the 12 months whose visible
     TTM EPS sat within ±12% of EPS_H (2021-11..2022-10), each month solved at
     the ROE visible then.  PE_H = perpetual_pe(g2_h, ROE_H today).
  M  the market paid about the same for EPS 6.4 as for 7.6 (elasticity
     b = 1 + gamma_pe = 0.362), so the M tier's own print median (g_print_m,
     4.77%) lands ABOVE H.  M is set from H by the measured elasticity,
     M = H x (EPS_M/EPS_H)^b, and g2_m is the reverse-solve of that M —
     stated in Inputs, re-derived here.
  L  the L world has no recovery, so it carries g2_m; ROE_L ≈ r pins its
     multiple near 1/r (A10).  What the market paid at trough EPS (14-19x)
     was buying the recovery — a `neutral` coordinate, not L's multiple.

The former inverse own-year band (p75 / med / p25 = 18.59 / 15.62 / 13.92,
A6) stays a cross-ruler: printed, never an anchor.  gamma_pe now enters the
formula (the H-side implied gamma equals it by construction); on the L side
the multiple is ROE-gated and only has to clear the guardrail floor.

g's leverage is disclosed rather than hidden (valuation-rules「g2 的杠杆 MUST
显式」): the script re-runs the band at both ends of the evidence range for
g2_m — g_print_h below, the largest g keeping M < H above — and prints the
band at both ends.

Why freezing revenue matters enough to guard: nine years of this company's
history say volume growth did not reach the bottom line (revenue +283%, net
profit +12%, gross margin 39.70% -> 13.42%).  The guards below assert the
margins move and nothing else does.

The H tier is guarded on *both* sides: the company did print EPS 7.85
(FY2021) and the market paid an average 88.34 while that EPS was visible.  H
must stay under 7.85 in the numerator AND under 1.25 x 88.34 as an anchor
(with v4 H is itself generated from those prints, so this is a tautology kept
as a tripwire for future edits).

No two-stage transition is run (the FY2027 consensus sits inside [L, H], A9 /
口径), so `check_transition_years` does not apply.  No shared axis.

Run:  python3 frameworks/eval/600309.SH.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_g_cap, check_r, g_cap, implied_g, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600309.SH.md"
FORMULA_ID = "wanhua_segment_margin_ladder_gp_bridge_gordon_v4_print"
YI = 1e8
TIERS = ("L", "M", "H")

# Audited baseline: 2026H1 net profit to parent x 2 (100.6296亿 x 2).
BASE_NP_PARENT_YI = 201.2592
BASE_NP_TOL_YI = 0.5

EPS_PEAK_FY2021 = 7.85  # highest EPS the company has ever printed
# ...and what the market actually paid while that EPS was the visible TTM:
# average monthly close over 2022-05..2022-08, the window between the FY2021
# annual report and the 2022 interim.  The numerator guard alone is not enough
# (A5): an anchor can clear 7.85 and still price a multiple peak earnings has
# never been given.
PRICE_AT_EPS_PEAK = 88.34
H_ANCHOR_HEADROOM = 1.25  # 2026's balance sheet and capex carry the difference
SEG_RESIDUAL_MAX = 0.05  # segment table vs consolidated GP, as a share of GP

MIN_R_MINUS_G = 0.02      # 裁决顺序 ①: r - g >= 2%
G_TOL = 5e-5              # A15: stated g2_m must equal the reverse-solve of the elasticity-spaced M
GUARDRAIL_SLACK = 0.01    # 校验步骤 5: generated multiples inside the realised band
GAMMA_TOL = 1e-3          # 校验步骤 6: H-side implied gamma equals gamma_pe up to g2 rounding
MIN_PRINT_MONTHS = 6      # A15: an EPS-matched median needs at least this many months
PEER_G_H_STEP = -0.01     # tier-1 cross-print: H pairs the post-peak g (A15 / v1 §A7)

REQUIRED = [
    "shares", "rev_h1", "gm_rate_h1", "op_h1", "np_h1",
    "rev_pu", "rev_pc", "rev_nm",
    "gm_m_pu", "gm_m_pc", "gm_m_nm",
    "gm_l_pu", "gm_l_pc", "gm_l_nm",
    "gm_h_blended", "conv", "equity",
    "r_perp", "g2_l", "g2_m", "g2_h", "g_print_h", "g_print_m", "n_print_h", "n_print_m",
    "g_peer_median", "pe_own_min", "pe_own_max",
    "pe_own_p75", "pe_own_med", "pe_own_p25", "gamma_pe", "gamma_pe_se",
    "eps_trough_fy2020",
]
# Reference-only rows (校验步骤 11): present in Inputs, never in an anchor path.
NOT_FORMULA = (
    "pe_own_p75", "pe_own_med", "pe_own_p25", "gamma_pe_se",
    "mdi_spot", "mdi_peak_season", "g_peer_median", "g_print_m", "eps_trough_fy2020",
    "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi",
)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    r = inp["r_perp"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")

    # --- Step 1: weld the bridge to the filing ------------------------------
    gp_h1_m = inp["rev_h1"] * inp["gm_rate_h1"]
    seg_gp_m = (
        inp["rev_pu"] * inp["gm_m_pu"]
        + inp["rev_pc"] * inp["gm_m_pc"]
        + inp["rev_nm"] * inp["gm_m_nm"]
    )
    gp_other = gp_h1_m - seg_gp_m
    opex = gp_h1_m - inp["op_h1"]

    # The sell-side segment table and the consolidated statement are two
    # different documents; a large residual means they stopped agreeing.
    if not (0.0 <= gp_other <= SEG_RESIDUAL_MAX * gp_h1_m):
        errors.append(
            f"segment residual {gp_other:.4f}亿 outside [0, {SEG_RESIDUAL_MAX:.0%}] "
            f"of gross profit {gp_h1_m:.4f}亿"
        )
    for leg, lo, hi in (
        ("pu", inp["gm_l_pu"], inp["gm_m_pu"]),
        ("pc", inp["gm_l_pc"], inp["gm_m_pc"]),
        ("nm", inp["gm_l_nm"], inp["gm_m_nm"]),
    ):
        if lo > hi:
            errors.append(f"L margin above M margin on leg {leg}: {lo} > {hi}")
    if inp["gm_h_blended"] <= inp["gm_rate_h1"]:
        errors.append(
            f"gm_h_blended {inp['gm_h_blended']} must exceed 2026H1 blended "
            f"{inp['gm_rate_h1']}"
        )
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if inp["gamma_pe"] >= 0.0:
        errors.append(f"gamma_pe={inp['gamma_pe']} must be negative (A6 measured inverse elasticity)")
    if errors:
        return report(errors, "FAIL (bridge)")

    # --- Step 2: numerators (spread only) -----------------------------------
    def numerator(gp_half: float):
        gp = gp_half * 2.0
        op = gp - opex * 2.0
        np_parent = op * inp["conv"]
        eps = np_parent * YI / inp["shares"]
        return gp, op, np_parent, eps

    gp_half = {
        "L": (
            inp["rev_pu"] * inp["gm_l_pu"]
            + inp["rev_pc"] * inp["gm_l_pc"]
            + inp["rev_nm"] * inp["gm_l_nm"]
            + gp_other
        ),
        "M": gp_h1_m,
        "H": inp["rev_h1"] * inp["gm_h_blended"],
    }
    num = {t: numerator(gp_half[t]) for t in TIERS}
    eps = {t: num[t][3] for t in TIERS}
    np_parent = {t: num[t][2] for t in TIERS}

    if abs(np_parent["M"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {np_parent['M']:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )
    if eps["H"] > EPS_PEAK_FY2021:
        errors.append(
            f"EPS_H {eps['H']:.4f} exceeds FY2021 peak {EPS_PEAK_FY2021} — "
            "no longer a modelled upper edge"
        )
    if errors:
        return report(errors, "FAIL (numerators)")

    # --- Step 3: tier ROE from one equity field, then the Gordon multiple ----
    roe = {t: np_parent[t] / inp["equity"] for t in TIERS}
    g2 = {t: inp[f"g2_{t.lower()}"] for t in TIERS}
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for t in TIERS:
        errors += check_g_cap(g2[t], r, f"g2_{t.lower()}")
        if r - g2[t] < MIN_R_MINUS_G:
            errors.append(f"g2_{t.lower()} {g2[t]:+.4f}: r-g {r - g2[t]:.4f} < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    # 校验步骤 4 (A15): g2 comes from EPS-matched prints, not from a band edge.
    #   H: the print median itself.  M: H spaced down by the measured elasticity,
    #   then reverse-solved.  L: the M world's g with no recovery.
    b_elastic = 1.0 + inp["gamma_pe"]
    for t in ("h", "m"):
        if inp[f"n_print_{t}"] < MIN_PRINT_MONTHS:
            errors.append(f"n_print_{t}={inp[f'n_print_{t}']:.0f} < {MIN_PRINT_MONTHS}: not enough EPS-matched months for a median (A15)")
    if abs(g2["H"] - inp["g_print_h"]) > G_TOL:
        errors.append(f"g2_h {g2['H']:+.5f} != g_print_h {inp['g_print_h']:+.5f} (A15: H carries its own print median)")
    pe_h = perpetual_pe(g2["H"], roe["H"], r)
    H_anchor = eps["H"] * pe_h
    M_anchor = H_anchor * (eps["M"] / eps["H"]) ** b_elastic
    pe_m = M_anchor / eps["M"]
    g_m_derived, m_conditioned = implied_g(pe_m, roe["M"], r)
    if abs(g2["M"] - g_m_derived) > G_TOL:
        errors.append(
            f"g2_m {g2['M']:+.5f} != reverse-solve of M = H x (EPS_M/EPS_H)^{b_elastic:.3f} "
            f"-> PE_M {pe_m:.4f} -> g {g_m_derived:+.5f} (A15)"
        )
    if abs(g2["L"] - g2["M"]) > G_TOL:
        errors.append(f"g2_l {g2['L']:+.5f} != g2_m {g2['M']:+.5f} (A15: L carries the M world's g, no recovery)")
    m_print_cap = eps["M"] * perpetual_pe(inp["g_print_m"], roe["M"], r)
    if M_anchor > m_print_cap + 0.05:
        errors.append(f"M {M_anchor:.2f} above its own print evidence {m_print_cap:.2f} (g_print_m {inp['g_print_m']:+.2%}) — A15")
    # Same-world gate record: the peer cluster is printed as a cross-check only.
    pe_peer = {
        t: perpetual_pe(inp["g_peer_median"] + (PEER_G_H_STEP if t == "H" else 0.0), roe[t], r)
        for t in TIERS
    }
    if errors:
        return report(errors, "FAIL (print-matched g)")

    pe = {t: perpetual_pe(g2[t], roe[t], r) for t in TIERS}
    # 校验步骤 5: guardrail — generated multiples inside the realised band.
    for t in TIERS:
        if not (inp["pe_own_min"] - GUARDRAIL_SLACK <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: generated PE_{t} {pe[t]:.3f} outside realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — STOP, do not force g"
            )
    if errors:
        return report(errors, "FAIL (guardrail)")

    # 校验步骤 6: shape is a RESULT check (裁决顺序 ⑤ / A6).  g must run reversed
    # or flat across tiers; the H-side implied gamma equals the measured one by
    # construction; the L side is ROE-gated (A10) and only has to clear the floor.
    if not (g2["L"] >= g2["M"] >= g2["H"]):
        errors.append(f"g tiers not reversed/flat: {g2['L']:+.4f}/{g2['M']:+.4f}/{g2['H']:+.4f} (cyclical, 裁决顺序 ⑤)")
    gamma_band = {t: math.log(pe[t] / pe["M"]) / math.log(eps[t] / eps["M"]) for t in ("L", "H")}
    if abs(gamma_band["H"] - inp["gamma_pe"]) > GAMMA_TOL:
        errors.append(f"H-side implied gamma {gamma_band['H']:+.3f} != gamma_pe {inp['gamma_pe']:+.3f} (A6/A15 construction)")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = (eps[t] * pe[t] for t in TIERS)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    # 校验步骤 7: H guarded on the anchor side too (A5).
    h_cap = H_ANCHOR_HEADROOM * PRICE_AT_EPS_PEAK
    if H > h_cap:
        errors.append(
            f"anchor H {H:.2f} exceeds {h_cap:.2f} = {H_ANCHOR_HEADROOM} x {PRICE_AT_EPS_PEAK} "
            f"(what the market paid at TTM EPS {EPS_PEAK_FY2021}) — the numerator cleared "
            "the peak but the multiple did not (A5)"
        )

    # 校验步骤 9 (A2e-2c): the tiers must already be a ladder in the numerator.
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # 校验步骤 11: reference rows must stay in Inputs and out of the formula.
    # The anchors above used none of them; this only guards the contract.
    leaked = [k for k in NOT_FORMULA if k not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None)

    # 裁决顺序 ②-b (valuation-rules): the margin ladder may stand in for the
    # consensus three points only while the FY2027 consensus mean sits inside
    # [EPS_M, EPS_H] and M is within 20% of it (A9).
    if not (eps["M"] <= inp["eps_cons_fy27_mean"] <= eps["H"]):
        errors.append(f"②-b: consensus FY27 mean {inp['eps_cons_fy27_mean']} outside [EPS_M {eps['M']:.3f}, EPS_H {eps['H']:.3f}]")
    cons_dev = eps["M"] / inp["eps_cons_fy27_mean"] - 1.0
    if abs(cons_dev) > 0.20 and "②-b" not in md:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus with no ②-b named-variable row")
    print(f"②-b: consensus FY27 {inp['eps_cons_fy27_lo']}/{inp['eps_cons_fy27_mean']}/{inp['eps_cons_fy27_hi']} vs EPS {eps['L']:.3f}/{eps['M']:.3f}/{eps['H']:.3f}; M dev {cons_dev:+.1%}")

    # 校验步骤 7b: g's leverage is disclosed (band printed at both ends).
    # Evidence range for g2_m: the H print median below, the largest g that
    # still keeps M < H above (past it the ladder collapses, A15).
    lo_g, hi_g = inp["g_print_h"], 0.0
    lo, hi = inp["g_print_h"], g_cap(r)
    for _ in range(60):
        mid = (lo + hi) / 2
        if eps["M"] * perpetual_pe(mid, roe["M"], r) < H:
            lo = mid
        else:
            hi = mid
    hi_g = lo
    lever = []
    for g in (lo_g, 0.03, g2["M"], hi_g):
        m_g = eps["M"] * perpetual_pe(g, roe["M"], r)
        l_g = eps["L"] * perpetual_pe(g, roe["L"], r)
        a_g, b_g = cut_points(l_g, m_g, H)
        lever.append((g, l_g, m_g, a_g, b_g))

    # --- report --------------------------------------------------------------
    pu_h_implied = (
        gp_half["H"] - gp_other
        - inp["rev_pc"] * inp["gm_m_pc"]
        - inp["rev_nm"] * inp["gm_m_nm"]
    ) / inp["rev_pu"]
    print(f"formula_id={FORMULA_ID}")
    print(f"r_perp={r:.1%} 篮 {baskets['r_perp']} (single operating leg); g cap={g_cap(r):.1%}")
    print(
        f"segment residual gp_other={gp_other:.4f}亿 ({gp_other / gp_h1_m:.2%} of GP), "
        f"opex={opex:.4f}亿/half"
    )
    desc = {
        "L": f"PU {inp['gm_l_pu']:.0%} / PC {inp['gm_l_pc']:.0%} / NM {inp['gm_l_nm']:.0%}",
        "M": f"PU {inp['gm_m_pu']:.0%} / PC {inp['gm_m_pc']:.0%} / NM {inp['gm_m_nm']:.0%}",
        "H": f"blended {inp['gm_h_blended']:.0%} -> PU {pu_h_implied:.2%} implied",
    }
    for t, anchor in zip(TIERS, (L, M, H)):
        gp, op, np_, e = num[t]
        print(
            f"{t}: {desc[t]:<44} gp={gp:7.2f}  op={op:7.2f}  np={np_:7.2f}亿  eps={e:.4f}  "
            f"ROE={roe[t]:.1%}  g2={g2[t]:+.2%}{'(ROE≈r 门)' if abs(roe[t] - r) < 0.03 else ''}  "
            f"payout={1 - g2[t] / roe[t]:.3f}  PE={pe[t]:.3f}  anchor={anchor:.2f}"
        )
    print(
        f"倍数生成 (A15 盈利配对): H g_print_h {inp['g_print_h']:+.2%} ({inp['n_print_h']:.0f} 个月) @ROE {roe['H']:.1%} -> PE_H {pe_h:.3f} -> H {H_anchor:.2f}; "
        f"M = H x (EPS_M/EPS_H)^{b_elastic:.3f} = {M_anchor:.2f} -> PE_M {pe_m:.3f} -> g_M {g_m_derived:+.2%} (conditioned={m_conditioned}); "
        f"M 档自身配对 g_print_m {inp['g_print_m']:+.2%} ({inp['n_print_m']:.0f} 个月) -> {m_print_cap:.2f} (证据上沿, > H); "
        f"L 配 g_M -> PE_L {pe['L']:.3f}"
    )
    print(
        f"同世界门 (交叉): 同业反解 g_peer={inp['g_peer_median']:+.2%} -> PE "
        f"{pe_peer['L']:.2f}/{pe_peer['M']:.2f}/{pe_peer['H']:.2f} (H 配峰后 {PEER_G_H_STEP:+.0%}) -> "
        f"{eps['L'] * pe_peer['L']:.2f}/{eps['M'] * pe_peer['M']:.2f}/{eps['H'] * pe_peer['H']:.2f} — 簇 g<=0 vs 本票共识上行, 不同世界, 不用; "
        f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓"
    )
    print(
        f"形状结果检查 (裁决顺序 ⑤ / A6): g {g2['L']:+.2%} >= {g2['M']:+.2%} >= {g2['H']:+.2%} ✓; "
        f"带隐含 gamma H={gamma_band['H']:+.3f} (= 实测 {inp['gamma_pe']:+.3f}), L={gamma_band['L']:+.3f} (ROE 门, 同向)"
    )
    d = decompose((L, M, H), (pe["L"], pe["M"], pe["H"]))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder (A2e-2c, all tiers at PE_M={pe['M']:.3f}): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={d['num_lm']:.4f} H={d['num_hm']:.4f} "
        f"| 倍数比 L={d['pe_lm']:.4f} H={d['pe_hm']:.4f}"
    )
    print("g 杠杆 (7b): " + " | ".join(
        f"g_M {g:+.2%}: {l_g:.1f}/{m_g:.1f}/{H:.1f} A {a_g:.1f} B {b_g:.1f}" for g, l_g, m_g, a_g, b_g in lever
    ))
    print(f"H 两侧越顶: EPS_H {eps['H']:.4f} <= {EPS_PEAK_FY2021} ✓; H {H:.2f} <= {h_cap:.2f} ✓")

    # 校验步骤 10: cross-rulers, printed and never anchored.
    own = (eps["L"] * inp["pe_own_p75"], eps["M"] * inp["pe_own_med"], eps["H"] * inp["pe_own_p25"])
    print(
        f"交叉尺① 反向 own-year p75/med/p25 {inp['pe_own_p75']}/{inp['pe_own_med']}/{inp['pe_own_p25']} "
        f"(A6, 实测 gamma {inp['gamma_pe']:+.3f}): {own[0]:.2f}/{own[1]:.2f}/{own[2]:.2f}"
    )
    flat_med = tuple(eps[t] * inp["pe_own_med"] for t in TIERS)
    print(
        f"交叉尺② flat own-year med {inp['pe_own_med']}: {flat_med[0]:.2f}/{flat_med[1]:.2f}/{flat_med[2]:.2f}"
    )
    print(
        f"谷底压力坐标 (deep_discount 行): FY2020 EPS {inp['eps_trough_fy2020']} x 1/r = "
        f"{inp['eps_trough_fy2020'] / r:.1f}"
    )
    # 地板 (disclosure only, never max()'d into L): PB = 1.0 on the same equity field.
    bps = inp["equity"] * YI / inp["shares"]
    print(f"地板 (只披露, 不进 L): PB 1.0 = BPS {bps:.2f} CNY; L {L:.2f} / 地板 = {L / bps:.3f}")
    per_pct = {
        leg: inp[f"rev_{leg}"] * 0.01 * 2.0 * inp["conv"] * YI / inp["shares"] * pe["M"]
        for leg in ("pu", "pc", "nm")
    }
    sens_h = [eps["H"] * perpetual_pe(g2["H"] + dg, roe["H"], r) for dg in (-0.01, 0.01)]
    print(
        f"敏感性 (@PE_M): +1pct PU/PC/NM margin -> anchor {per_pct['pu']:+.2f}/{per_pct['pc']:+.2f}/{per_pct['nm']:+.2f} CNY; "
        f"g_H ±1pp -> H {sens_h[0]:.2f}/{sens_h[1]:.2f} (M 随 H 折回同步)"
    )
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
