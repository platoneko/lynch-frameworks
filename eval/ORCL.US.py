#!/usr/bin/env python3
"""ORCL.US (Oracle) valuation eval — recompute anchors from frameworks/ORCL.US.md.

frameworks/ORCL.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: orcl_sotp_sw_gordon_oci_g0_rpo_vopt_v1

Main ruler: two-leg SOTP, each leg on its own Gordon multiple.

    Software annuity leg   FY28E NOPAT bridged from the FY26 segment margin
                           (10-K Note 13) net of an estimated OCI contribution,
                           rolled two years on named per-line growth; ROE is
                           derived from residual invested capital; g_sw = 2.5%
                           -> 12.68x, identical in every tier.
    OCI leg                FY28E NOPAT is the RESIDUAL of the sell-side EPS
                           range (9.00 / 11.02 / 13.51, 39 estimates) after
                           SBC, after adding back after-tax interest, minus the
                           software leg.  Priced at g = 0: the Gordon multiple
                           is then exactly 1/r = 10x regardless of ROE, so the
                           contested OCI return on capital never enters the
                           band — it decides only whether the option leg is
                           worth anything (A6 / A9).

The tier ladder therefore lives ENTIRELY in the consensus numerator: both
legs' multiples are flat across L/M/H (multiple ratio exactly 1.000), and
`assert_flat_multiples` fails loudly if any edit reintroduces a per-tier
multiple.  Growth beyond FY28E — the RPO-backed second ramp — is NOT in the
band: it is V_opt (k = 1 x today's OCI leg) and appears only in the zone+V
table, whose per-tier p_k never touch L/M/H (A2e-7a).

The street's EV/EBIT read (JPM 13x / HSBC 14x on OCI EBIT) is recomputed as a
cross-check only.  Net debt is taken at face at the start of FY28 and the
mandatory convertible preferred at its liquidation preference (A11).

Run:  python3 eval/ORCL.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    capex_constituent_share,
    check_capex_constituent,
)
from eval.lib.gordon import (  # noqa: E402
    R_CONDITIONAL,
    R_OPERATING,
    check_g_cap,
    check_r,
    payout,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_inputs,
    report,
)
from eval.lib.zones import zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "ORCL.US.md"
FORMULA_ID = "orcl_sotp_sw_gordon_oci_g0_rpo_vopt_v1"
TOL = 0.05
BN = 1e3  # inputs are in $M; report in $B
# AGENTS.md「永续增长口径」: inside 2pp of the pole the multiple/g map is
# ill-conditioned, so a g that close to r may not carry an anchor.
MIN_R_MINUS_G = 0.02
# Sell-side ceiling on OCI gross margin (JPM: BYOH contracts ~48%).  The
# residual numerator's implied EBIT margin must sit below it or the software
# bridge has taken too little.
OCI_EBIT_MARGIN_CAP = 0.48
# Ex-99.1 table 10: FY26 revenue by offering must add to consolidated revenue.
FY26_TOTAL_REVENUE = 67357.0
NET_DEBT_SENSITIVITY = 20000.0
SHARES_SENSITIVITY = (3000.0, 3100.0)
OCI_G_SENSITIVITY = (0.03, 0.05)
G_SW_SENSITIVITY = (-0.01, +0.01)
OCI_GM_SENSITIVITY = (0.30, 0.40)
# Sell-side coordinates for the market-implied-p read (A13: cross-check only).
STREET_TPS = (("Stephens", 175.0), ("median", 240.0), ("Citi", 330.0))
WEEK52_LOW = 114.50

REQUIRED = [
    "price",
    "r_perp",
    "tax_rate",
    "shares_fy28",
    "rev_software_fy26",
    "rev_saas_fy26",
    "rev_hw_fy26",
    "rev_svc_fy26",
    "oci_rev_fy26",
    "g_software",
    "g_saas",
    "g_hw",
    "g_svc",
    "seg_margin_fy26",
    "sm_total_fy26",
    "oci_gm_est",
    "oci_sm_share",
    "below_seg_fy26",
    "sw_share_below",
    "g_below",
    "g2_sw",
    "equity_aug",
    "debt_aug",
    "cash_aug",
    "oci_ppe_now",
    "eps_fy28_low",
    "eps_fy28_mid",
    "eps_fy28_high",
    "rev_fy28_low",
    "rev_fy28_mid",
    "rev_fy28_high",
    "sbc_fy28",
    "int_fy28",
    "g2_oci",
    "capex_rest_fy27",
    "da_rest_fy27",
    "prepay_cum",
    "ocf_rest_fy27",
    "div_rest_fy27",
    "pref_liq",
    "rev_guide_fy27",
    "v_opt",
    "rpo",
    "capex_q1",
    "dep_q1",
    "capex_guide_low",
    "capex_guide_high",
    "eps_ttm_gaap",
    "pe_own_min",
    "pe_own_p50",
    "pe_own_max",
    "xchk_ev_ebit_low",
    "xchk_ev_ebit_high",
]

TIERS = ("l", "m", "h")
LINES = ("software", "saas", "hw", "svc")


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def sanity_checks(inp: dict[str, float]) -> list[str]:
    """Ticker-specific guards on the inputs."""
    errs: list[str] = []

    # r is a tier, not a dial.  Both legs are ordinary operating cash flow: the
    # OCI leg's conditional-tier case (OpenAI ~47% of RPO) is half-met and was
    # ruled a sensitivity, not the anchor (A7).
    r = inp["r_perp"]
    errs += check_r(r, "r_perp")
    if abs(r - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={r}: both legs are operating cash flow, expected {R_OPERATING}")

    # OCI is priced at g = 0 so its multiple is 1/r whatever its ROE (A6).
    if abs(inp["g2_oci"]) > 1e-12:
        errs.append(f"g2_oci={inp['g2_oci']}: the OCI leg MUST be priced at g=0 (A6); growth beyond FY28E is V_opt")

    # AGENTS.md「永续增长口径」: both Gordon legs' perpetual g at or below the cap.
    errs += check_g_cap(inp["g2_sw"], "g2_sw")
    errs += check_g_cap(inp["g2_oci"], "g2_oci")

    g_sw = inp["g2_sw"]
    if r - g_sw <= 0:
        errs.append("perpetuity diverges on the software leg: g_sw >= r_perp")
    elif r - g_sw < MIN_R_MINUS_G:
        errs.append(f"r_perp - g_sw = {r - g_sw:.2%} < {MIN_R_MINUS_G:.0%} — g sits at the pole (AGENTS.md)")

    errs += ladder("eps_fy28", inp["eps_fy28_low"], inp["eps_fy28_mid"], inp["eps_fy28_high"])
    errs += ladder("rev_fy28", inp["rev_fy28_low"], inp["rev_fy28_mid"], inp["rev_fy28_high"])

    if not (0.0 < inp["tax_rate"] < 0.5):
        errs.append("tax_rate out of plausible range")
    for k in ("oci_gm_est", "oci_sm_share", "sw_share_below"):
        if not (0.0 < inp[k] < 1.0):
            errs.append(f"{k} must be inside (0,1)")
    if not (0.0 < inp["oci_ppe_now"] < inp["equity_aug"] + inp["debt_aug"]):
        errs.append("oci_ppe_now implausible against the balance sheet")

    # Ex-99.1 table 10 identity — guards a stale or miskeyed revenue row.
    rev_sum = sum(inp[f"rev_{ln}_fy26"] for ln in LINES) + inp["oci_rev_fy26"]
    if abs(rev_sum - FY26_TOTAL_REVENUE) > 1.0:
        errs.append(f"FY26 revenue identity: lines sum {rev_sum:.0f} != {FY26_TOTAL_REVENUE:.0f}")

    errs.extend(check_capex_constituent(inp["capex_guide_low"], inp["capex_guide_high"]))

    # A2e-7a: no probability may sit in the Inputs table.
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in the zone+V table only (A2e-7a)")

    return errs


def assert_flat_multiples(pe_sw: dict[str, float], pe_oci: dict[str, float]) -> list[str]:
    """The tier band MUST be pure numerator: no tier may carry its own multiple (A2e-2c)."""
    errs: list[str] = []
    for leg, pes in (("software", pe_sw), ("oci", pe_oci)):
        for tier in ("l", "h"):
            if pes[tier] != pes["m"]:
                errs.append(
                    f"{leg} multiple ratio {tier}/m = {pes[tier] / pes['m']:.4f} != 1.000 "
                    f"— multiples MUST be flat across tiers (A2e-2c)"
                )
    return errs


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    errors = sanity_checks(inp)

    r = inp["r_perp"]
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_fy28"]

    # ---- Step 1: software annuity leg, FY28E numerator (A4/A5) ----
    def rev_sw(years: int, oci_gm: float | None = None) -> float:
        return sum(inp[f"rev_{ln}_fy26"] * (1 + inp[f"g_{ln}"]) ** years for ln in LINES)

    rev_sw_fy26 = rev_sw(0)
    rev_sw_fy28 = rev_sw(2)

    def software_leg(oci_gm: float, g_sw: float) -> tuple[float, float, float, float]:
        """(NOPAT, IC, ROE, PE) of the software leg under a given OCI-GM bridge."""
        oci_contrib = inp["oci_rev_fy26"] * oci_gm - inp["sm_total_fy26"] * inp["oci_sm_share"]
        margin_pct = (inp["seg_margin_fy26"] - oci_contrib) / rev_sw_fy26
        ebit = margin_pct * rev_sw_fy28 - inp["below_seg_fy26"] * inp["sw_share_below"] * (1 + inp["g_below"]) ** 2
        nopat = ebit * keep
        ic = (inp["equity_aug"] + inp["debt_aug"] - inp["cash_aug"]) - inp["oci_ppe_now"]
        roe = nopat / ic
        return nopat, ic, roe, perpetual_pe(g_sw, roe, r)

    nopat_sw, ic_sw, roe_sw, pe_sw_m = software_leg(inp["oci_gm_est"], inp["g2_sw"])
    v_sw = nopat_sw * pe_sw_m
    oci_contrib_fy26 = inp["oci_rev_fy26"] * inp["oci_gm_est"] - inp["sm_total_fy26"] * inp["oci_sm_share"]
    sw_margin_pct = (inp["seg_margin_fy26"] - oci_contrib_fy26) / rev_sw_fy26

    if ic_sw <= 0:
        errors.append("ic_sw must be positive — software ROE is derived from it")
    pay_sw = payout(inp["g2_sw"], roe_sw)
    if not (0.0 < pay_sw <= 1.0):
        errors.append(f"software payout {pay_sw:.3f} outside (0, 1]")

    # ---- Step 3: OCI leg = residual of the consensus EPS range (A2/A3) ----
    eps = {"l": inp["eps_fy28_low"], "m": inp["eps_fy28_mid"], "h": inp["eps_fy28_high"]}
    rev_fy28 = {"l": inp["rev_fy28_low"], "m": inp["rev_fy28_mid"], "h": inp["rev_fy28_high"]}

    def nopat_total(e: float) -> float:
        ni_gaaplike = e * sh - inp["sbc_fy28"] * keep
        return ni_gaaplike + inp["int_fy28"] * keep

    nopat_oci = {t: nopat_total(eps[t]) - nopat_sw for t in TIERS}
    oci_rev_fy28 = {t: rev_fy28[t] - rev_sw_fy28 for t in TIERS}
    oci_margin = {t: nopat_oci[t] / keep / oci_rev_fy28[t] for t in TIERS}

    # The OCI leg may never be a negative leg (user constraint, A6): a residual
    # that turns negative means the software bridge has swallowed the company.
    for t in TIERS:
        if nopat_oci[t] <= 0:
            errors.append(f"OCI residual NOPAT {t.upper()} = {nopat_oci[t]:.0f} <= 0 — the OCI leg must not be negative (A6)")
        if not (0.0 < oci_margin[t] <= OCI_EBIT_MARGIN_CAP):
            errors.append(
                f"implied OCI EBIT margin {t.upper()} = {oci_margin[t]:.1%} outside (0, {OCI_EBIT_MARGIN_CAP:.0%}]"
                f" — the residual is inconsistent with the sell-side GM ceiling (A4/A5)"
            )

    # ---- Step 4: OCI multiple (g = 0 -> exactly 1/r) and ROE readings (A6/A8) ----
    ic_oci_gross = inp["oci_ppe_now"] + inp["capex_rest_fy27"] - inp["da_rest_fy27"]
    ic_oci_net = ic_oci_gross - inp["prepay_cum"]
    if ic_oci_net <= 0:
        errors.append("ic_oci_net must be positive")
    roe_oci_gross = {t: nopat_oci[t] / ic_oci_gross for t in TIERS}
    roe_oci_net = {t: nopat_oci[t] / ic_oci_net for t in TIERS}
    # ROE only feeds the multiple through payout(g/ROE); at g = 0 the payout is
    # 1 for any positive ROE, so we pass the M-tier reading and assert 1/r.
    pe_oci_m = perpetual_pe(inp["g2_oci"], roe_oci_gross["m"], r)
    if abs(pe_oci_m - 1.0 / r) > 1e-12:
        errors.append(f"OCI multiple {pe_oci_m:.6f} != 1/r = {1.0 / r:.6f} — g2_oci is not zero (A6)")

    pe_sw = {t: pe_sw_m for t in TIERS}
    pe_oci = {t: pe_oci_m for t in TIERS}
    errors.extend(assert_flat_multiples(pe_sw, pe_oci))

    v_oci = {t: nopat_oci[t] * pe_oci[t] for t in TIERS}

    # ---- Step 5: closing item (A11) ----
    net_debt_aug = inp["debt_aug"] - inp["cash_aug"]
    burn_rest_fy27 = inp["capex_rest_fy27"] - inp["ocf_rest_fy27"] + inp["div_rest_fy27"]
    net_debt_fy28 = net_debt_aug + burn_rest_fy27
    closure = -(net_debt_fy28 + inp["pref_liq"])

    def per_share(v_oci_leg: float, v_sw_leg: float = v_sw, close: float = closure, shares: float = sh) -> float:
        return (v_sw_leg + v_oci_leg + close) / shares

    # ---- Step 6: anchors ----
    band = {t: per_share(v_oci[t]) for t in TIERS}
    L, M, H = band["l"], band["m"], band["h"]
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    zone = zone_of(inp["price"], L, M, H)

    # ---- Step 7: V_opt = k=1 x today's OCI leg (A9); zone+V only ----
    rev_sw_fy27 = rev_sw(1)
    oci_rev_fy27 = inp["rev_guide_fy27"] - rev_sw_fy27
    v_opt_calc = oci_rev_fy27 * oci_margin["m"] * keep * pe_oci_m / sh
    if abs(v_opt_calc - inp["v_opt"]) > TOL:
        errors.append(f"v_opt: stated {inp['v_opt']} vs recomputed {v_opt_calc:.4f}")
    if inp["v_opt"] < 0:
        errors.append("v_opt must be >= 0")
    v_opt = inp["v_opt"]
    rpo_run_rate = inp["rpo"] / 2.0 / 3.0

    p_tiers = stated_p_tiers(md)
    if p_tiers is None:
        errors.append("p_L/p_M/p_H not stated in Outputs (A2e-7d)")
        p_tiers = (0.0, 0.0, 0.0)
    elif not all(0.0 <= p <= 1.0 for p in p_tiers):
        errors.append(f"p_L/p_M/p_H out of [0,1]: {p_tiers}")
    band_v = {t: band[t] + p * v_opt for t, p in zip(TIERS, p_tiers)}
    A2, B2 = (band_v["l"] + band_v["m"]) / 2, (band_v["m"] + band_v["h"]) / 2
    zone_v = zone_of(inp["price"], band_v["l"], band_v["m"], band_v["h"])

    # ---- Guardrail (A12): only H is bound; L/M breaching the floor is a known
    # distortion of a net-cash-era band and is printed, not failed. ----
    pe_ttm = {t: band[t] / inp["eps_ttm_gaap"] for t in TIERS}
    if pe_ttm["h"] > inp["pe_own_max"]:
        errors.append(
            f"生成的倍数越出自身实测带: H/eps_ttm = {pe_ttm['h']:.2f}x > pe_own_max {inp['pe_own_max']:.2f}x — 回对话"
        )

    # ---- Stated vs recomputed ----
    errors.extend(check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL))

    # ================= diagnostics =================
    num = {t: nopat_sw + nopat_oci[t] for t in TIERS}
    print(f"formula_id={FORMULA_ID}")
    print(
        f"software leg: rev FY26 {rev_sw_fy26 / BN:.1f}B -> FY28E {rev_sw_fy28 / BN:.1f}B"
        f" | seg margin {sw_margin_pct:.1%} (OCI contrib est {oci_contrib_fy26 / BN:.1f}B removed)"
        f" | EBIT {nopat_sw / keep / BN:.1f}B NOPAT {nopat_sw / BN:.1f}B"
        f" | IC {ic_sw / BN:.1f}B ROE {roe_sw:.1%} g {inp['g2_sw']:.1%} -> PE {pe_sw_m:.2f}x payout {pay_sw:.1%}"
        f" -> {v_sw / sh:.2f}/sh"
    )
    print(
        f"OCI leg: g={inp['g2_oci']:.0%} -> PE {pe_oci_m:.2f}x (= 1/r, ROE-independent)"
        f" | IC start-FY28 gross {ic_oci_gross / BN:.1f}B / net-of-prepay {ic_oci_net / BN:.1f}B"
    )
    print("  tier  EPS    NOPAT_total  NOPAT_oci  OCI rev FY28E  impl EBIT margin  ROE gross/net   V_oci/sh")
    for t in TIERS:
        print(
            f"    {t.upper()}  {eps[t]:5.2f} {nopat_total(eps[t]) / BN:10.1f}B {nopat_oci[t] / BN:8.1f}B"
            f" {oci_rev_fy28[t] / BN:10.1f}B {oci_margin[t]:13.1%}"
            f" {roe_oci_gross[t]:9.1%}/{roe_oci_net[t]:.1%} {v_oci[t] / sh:9.2f}"
        )
    print(
        f"closure: net debt 08-31 {net_debt_aug / BN:.1f}B + rest-FY27 burn {burn_rest_fy27 / BN:.1f}B"
        f" (capex {inp['capex_rest_fy27'] / BN:.1f} - OCF {inp['ocf_rest_fy27'] / BN:.1f} + div {inp['div_rest_fy27'] / BN:.1f})"
        f" = {net_debt_fy28 / BN:.1f}B; pref {inp['pref_liq'] / BN:.1f}B -> {closure / sh:.2f}/sh"
        f" | depreciation lag capex_q1/dep_q1 = {inp['capex_q1'] / inp['dep_q1']:.1f}x (A10)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print("  leg $/sh   software(PE)     oci(PE)   closure     total")
    for t in TIERS:
        print(
            f"    {t.upper()}   {v_sw / sh:7.2f}({pe_sw[t]:5.2f}x) {v_oci[t] / sh:7.2f}({pe_oci[t]:5.2f}x)"
            f" {closure / sh:9.2f} {band[t]:9.2f}"
        )
    print(
        f"tier decomposition (A2e-5): L/M {L / M:.3f} = numerator {num['l'] / num['m']:.3f}"
        f" x multiple {pe_oci['l'] / pe_oci['m']:.3f} x rest {(L / M) / (num['l'] / num['m']):.3f}"
        f" | H/M {H / M:.3f} = numerator {num['h'] / num['m']:.3f}"
        f" x multiple {pe_oci['h'] / pe_oci['m']:.3f} x rest {(H / M) / (num['h'] / num['m']):.3f}"
        f"   (rest = closure dilution)  | (H-L)/2M {(H - L) / (2 * M):.3f}"
    )
    print(
        f"flat-multiple ladder (A2e-2c): multiples are literally flat, so the ladder IS the numerator ladder:"
        f" {num['l'] / BN:.1f} < {num['m'] / BN:.1f} < {num['h'] / BN:.1f} ($B NOPAT)"
    )
    print(
        f"guardrail (A12): band / trailing GAAP EPS {inp['eps_ttm_gaap']} = "
        f"L {pe_ttm['l']:.1f}x M {pe_ttm['m']:.1f}x H {pe_ttm['h']:.1f}x"
        f" vs own 5y band {inp['pe_own_min']:.2f}-{inp['pe_own_max']:.2f}x (p50 {inp['pe_own_p50']:.2f})"
        f" — H {'OK' if pe_ttm['h'] <= inp['pe_own_max'] else '越出'};"
        f" L/M {'below floor: 护栏失真（净现金时代的带 + Ampere 污染），仅 H 受约束' if pe_ttm['m'] < inp['pe_own_min'] else 'inside'}"
    )
    print(
        f"implied PE on FY28E non-GAAP EPS: L {L / eps['l']:.1f}x (own) M {M / eps['m']:.1f}x H {H / eps['h']:.1f}x (own)"
        f" | price {inp['price']} = {inp['price'] / eps['m']:.1f}x FY28E mid"
    )
    _lo, _hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(
        f"capex axis (constituent, A16): FY27 guide ${inp['capex_guide_low'] / 1e9:.0f}-{inp['capex_guide_high'] / 1e9:.0f}B"
        f" = {_lo:.1%}-{_hi:.1%} of the axis 2026 base"
    )
    print(
        f"V_opt = +{v_opt:.2f}/sh = k=1 x FY27E OCI leg (rev {oci_rev_fy27 / BN:.1f}B x margin {oci_margin['m']:.1%}"
        f" x {keep:.2f} x {pe_oci_m:.0f}x) | V_opt/M {v_opt / M:.1%}"
        f"{' — 期权主导型' if v_opt > M else ''} | RPO cross: {inp['rpo'] / BN:.0f}B/2/3y = {rpo_run_rate / BN:.1f}B/yr"
        f" vs FY28E OCI M {oci_rev_fy28['m'] / BN:.1f}B"
    )
    print("  zone+V:  tier  底牌     p     +p*V    修正后")
    for t, p in zip(TIERS, p_tiers):
        print(f"           {t.upper()}  {band[t]:7.2f} {p:5.2f} {p * v_opt:7.2f} {band_v[t]:8.2f}")
    print(f"  A'={A2:.2f} B'={B2:.2f} -> zone+V zone={zone_v}")
    implied_p = (inp["price"] - H) / v_opt if inp["price"] > H else None
    print(
        f"market-implied p = (P-H)/V_opt: spot {inp['price']} -> "
        + (f"{implied_p:.2f}" if implied_p is not None else "inside H")
        + " | "
        + " | ".join(
            f"{lbl} {tp:.0f} -> {(tp - H) / v_opt:.2f}" if tp > H else f"{lbl} {tp:.0f} -> {zone_of(tp, L, M, H)}"
            for lbl, tp in STREET_TPS
        )
        + f" | 52w low {WEEK52_LOW} -> {zone_of(WEEK52_LOW, L, M, H)}"
    )
    ev = inp["price"] * sh + net_debt_aug + inp["pref_liq"]
    print(
        f"market read: mcap {inp['price'] * sh / BN:.0f}B EV {ev / BN:.0f}B"
        f" | EV/FY28E NOPAT(M) {ev / num['m']:.1f}x"
        f" | market OCI EV = EV - V_sw = {(ev - v_sw) / BN:.0f}B = {(ev - v_sw) / ic_oci_gross:.2f}x IC gross"
        f" = {(ev - v_sw) / nopat_oci['m']:.1f}x M NOPAT / {(ev - v_sw) / nopat_oci['h']:.1f}x H NOPAT"
    )

    # ---- sensitivities ----
    pe_cond = perpetual_pe(inp["g2_oci"], roe_oci_gross["m"], R_CONDITIONAL)
    print(
        f"sensitivity r_oci={R_CONDITIONAL:.0%} (A7 conditional tier, OCI PE {pe_cond:.2f}x):"
        f" L/M/H = {per_share(nopat_oci['l'] * pe_cond):.2f} / {per_share(nopat_oci['m'] * pe_cond):.2f}"
        f" / {per_share(nopat_oci['h'] * pe_cond):.2f}"
    )
    disc = 1.0 / (1.0 + r)
    print(f"sensitivity discount 1y at r: L/M/H = {L * disc:.2f} / {M * disc:.2f} / {H * disc:.2f}")
    for m in (inp["xchk_ev_ebit_low"], inp["xchk_ev_ebit_high"]):
        vals = [per_share(nopat_oci[t] / keep * m) for t in TIERS]
        print(
            f"cross-check OCI at EV/EBIT {m:.0f}x (street, NOT in the band): L/M/H = "
            f"{vals[0]:.2f} / {vals[1]:.2f} / {vals[2]:.2f}"
        )
    for g in OCI_G_SENSITIVITY:
        cells = []
        for t in TIERS:
            try:
                pe_g = perpetual_pe(g, roe_oci_net[t], r)
                cells.append(f"{t.upper()} {pe_g:.2f}x -> {per_share(nopat_oci[t] * pe_g):.2f}")
            except ValueError:
                cells.append(f"{t.upper()} diverges")
        print(f"sensitivity OCI g={g:.0%} (ROE net-of-prepay): " + " | ".join(cells))
    for dg in G_SW_SENSITIVITY:
        n_, _, _, pe_ = software_leg(inp["oci_gm_est"], inp["g2_sw"] + dg)
        print(f"sensitivity g_sw={inp['g2_sw'] + dg:.1%}: software PE {pe_:.2f}x -> M {per_share(v_oci['m'], n_ * pe_):.2f}")
    print(
        f"sensitivity net debt ±{NET_DEBT_SENSITIVITY / BN:.0f}B: M = "
        f"{per_share(v_oci['m'], close=closure + NET_DEBT_SENSITIVITY):.2f} / "
        f"{per_share(v_oci['m'], close=closure - NET_DEBT_SENSITIVITY):.2f}"
    )
    print(
        "sensitivity shares "
        + " / ".join(f"{s:.0f}M -> M {per_share(v_oci['m'], shares=s):.2f}" for s in SHARES_SENSITIVITY)
    )
    for gm in OCI_GM_SENSITIVITY:
        n_, _, roe_, pe_ = software_leg(gm, inp["g2_sw"])
        oci_m = nopat_total(eps["m"]) - n_
        print(
            f"sensitivity oci_gm_est={gm:.0%} (software bridge only; residual compensates): software NOPAT"
            f" {n_ / BN:.1f}B ROE {roe_:.1%} PE {pe_:.2f}x, OCI M NOPAT {oci_m / BN:.1f}B"
            f" -> M {per_share(oci_m * pe_oci_m, n_ * pe_):.2f}"
        )
    print(f"price={inp['price']} zone={zone}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
