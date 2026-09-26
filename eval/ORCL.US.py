#!/usr/bin/env python3
"""ORCL.US (Oracle) valuation eval — recompute anchors from frameworks/ORCL.US.md.

frameworks/ORCL.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on mismatch.

formula_id: orcl_sotp_sw_gordon_oci_dbucket_split_v2

Main ruler: two-leg SOTP; each leg discounts at its own basket r
(valuation-rules.md「§r 篮子」, named in the Inputs source cells as `篮 N`).

    Software annuity leg   FY28E NOPAT bridged from the FY26 segment margin
                           (10-K Note 13) net of an estimated OCI contribution,
                           rolled two years on named per-line growth; ROE is
                           derived from residual invested capital; g_sw = 2.5%
                           at basket 4 (r 10%) -> 12.68x, identical in every
                           tier.
    OCI leg                留存去向审计 D-bucket project value, split into two
                           sub-legs by RPO share: non-OpenAI orders (basket 4,
                           r 10%) and OpenAI orders (basket 7, r 15%).  Each
                           sub-leg = K_spent x ROE_proj / r  +  a three-year
                           window (FY29-31) of K_remain x (ROE_proj / r - 1)
                           discounted at its own r.  The tier ladder lives in
                           ROE_proj: L / M are the FY28E consensus low / mean
                           residual NOPAT over K_spent (book, no improvement),
                           H is the AWS-2024 state; in L the OpenAI sub-leg
                           has no window (never built).  The FY28E consensus
                           residual therefore feeds ROE_proj and is NOT
                           multiplied by a multiple (double-count guard, A6 /
                           A9); there is no V_opt.

Guardrail (③): the band is compared to the same-basis forward PE band
(price / next-FY non-GAAP consensus).  M sits below the measured floor, the
floor month passed the 1b validity check, and stepping the OpenAI sub-leg
down 7 -> 6 -> 5 -> 4 still leaves M below the floor, so the framework is
BLOCKED: the deck line is printed as a reference band and NO zone is
asserted.  This script recomputes the reference band, the 降篮 path, the
band-edge δ (表2′) and the market-implied δ / ROE_proj, and checks the header
BLOCKED line agrees with the recomputed verdict.

The street's EV/EBIT read (JPM 13x / HSBC 14x on OCI EBIT) is recomputed as a
cross-check only.  Net debt is taken at face at the start of FY28 and the
mandatory convertible preferred at its liquidation preference (A11).

Run:  python3 eval/ORCL.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    capex_constituent_share,
    check_capex_constituent,
    check_lab_mount,
)
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    basket_r,
    check_basket_pair,
    check_g_cap,
    check_k_declared,
    check_r,
    payout,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
    stated_zone,
)
from eval.lib.zones import zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "ORCL.US.md"
FORMULA_ID = "orcl_sotp_sw_gordon_oci_dbucket_split_v2"
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
# A18 / A19: AWS FY2024 segment asset turnover, the H-tier K_remain denominator.
AWS_TURNOVER = 0.55
ROE_PROJ_TOL = 0.001
K_REMAIN_REL_TOL = 0.01
# ③ 降篮 path (A21): only the OpenAI sub-leg may step down, 篮 7 -> 6 -> 5 -> 4.
OPENAI_DOWNGRADE_BASKETS = (7, 6, 5, 4)
# 表2′ band-edge band as stated in Outputs: `带边带 78.17 / 114.72 / 195.81`.
STATED_BAND_EDGE = re.compile(r"带边带\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)")
NET_DEBT_SENSITIVITY = 20000.0
G_SW_SENSITIVITY = (-0.01, +0.01)
ROE_PROJ_SENSITIVITY = (-0.02, +0.02)
WINDOW_SENSITIVITY = (2, 4)
SHARE_SENSITIVITY = (0.40, 0.60)
K_REMAIN_SENSITIVITY = (0.8, 1.2)
ROE_PROJ_H_AWS_2025 = 0.150
# A5: peer-implied g_sw (MSFT / IBM / CRM median), disclosed, not adopted.
G_SW_PEER = 0.0544
# Sell-side coordinates (A13: cross-check only).
STREET_TPS = (("Stephens", 175.0), ("median", 240.0), ("Citi", 330.0))
WEEK52_LOW = 114.50

REQUIRED = [
    "price",
    "r_perp",
    "r_oci_non",
    "r_oci_open",
    "r_oci_open_t",
    "k_lab",
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
    "k_spent_gross",
    "rpo_share_openai",
    "roe_proj_l",
    "roe_proj_m",
    "roe_proj_h",
    "k_remain_yr_book",
    "k_remain_yr_aws",
    "window_years",
    "capex_rest_fy27",
    "da_rest_fy27",
    "prepay_cum",
    "ocf_rest_fy27",
    "div_rest_fy27",
    "pref_liq",
    "rev_guide_fy27",
    "rpo",
    "capex_q1",
    "dep_q1",
    "capex_guide_low",
    "capex_guide_high",
    "eps_ttm_gaap",
    "pe_fwd_min",
    "pe_fwd_p10",
    "pe_fwd_med",
    "pe_fwd_p90",
    "pe_fwd_max",
    "pe_own_min",
    "pe_own_p50",
    "pe_own_max",
    "xchk_ev_ebit_low",
    "xchk_ev_ebit_high",
]
R_FIELDS = ("r_perp", "r_oci_non", "r_oci_open", "r_oci_open_t")

TIERS = ("l", "m", "h")
LINES = ("software", "saas", "hw", "svc")


def bisect(f: Callable[[float], float], lo: float, hi: float, iters: int = 100) -> float:
    """Root of a monotone f on [lo, hi]; the band is monotone in δ and in ROE_proj."""
    flo = f(lo)
    if flo * f(hi) > 0:
        raise ValueError(f"no sign change on [{lo}, {hi}]")
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    """Ticker-specific guards on the inputs."""
    errs: list[str] = []

    # Each leg's r is a basket value and the basket named in its source cell
    # must be the one that carries that value (AGENTS.md「篮子声明」).
    for field in R_FIELDS:
        if field not in baskets:
            errs.append(f"{field}: source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errs += check_r(inp[field], field, baskets.get(field))
    # The OpenAI sub-leg is a basket pair on the frontier-lab axis: journey
    # basket for the window's discounting, terminal basket for capitalising,
    # arrival risk in the shared k_lab (valuation-rules.md「篮子对」).
    errs += check_basket_pair(inp["r_oci_open"], inp["r_oci_open_t"], "oci_open",
                              baskets.get("r_oci_open"), baskets.get("r_oci_open_t"))
    errs += check_k_declared(inp["r_oci_open"], inp["r_oci_open_t"], (inp["k_lab"],) * 3, "k_lab")
    errs += [f"axis: {e}" for e in check_lab_mount(inp["k_lab"])]

    # AGENTS.md「永续增长口径」: the software leg's perpetual g at or below the
    # cap of ITS basket r.  The OCI leg has no perpetual g (D-bucket, A6).
    r = inp["r_perp"]
    errs += check_g_cap(inp["g2_sw"], r, "g2_sw")
    g_sw = inp["g2_sw"]
    if r - g_sw <= 0:
        errs.append("perpetuity diverges on the software leg: g_sw >= r_perp")
    elif r - g_sw < MIN_R_MINUS_G:
        errs.append(f"r_perp - g_sw = {r - g_sw:.2%} < {MIN_R_MINUS_G:.0%} — g sits at the pole (AGENTS.md)")

    errs += ladder("eps_fy28", inp["eps_fy28_low"], inp["eps_fy28_mid"], inp["eps_fy28_high"])
    errs += ladder("rev_fy28", inp["rev_fy28_low"], inp["rev_fy28_mid"], inp["rev_fy28_high"])
    errs += ladder("roe_proj", inp["roe_proj_l"], inp["roe_proj_m"], inp["roe_proj_h"])

    if not (0.0 < inp["tax_rate"] < 0.5):
        errs.append("tax_rate out of plausible range")
    for k in ("oci_gm_est", "oci_sm_share", "sw_share_below", "rpo_share_openai"):
        if not (0.0 < inp[k] < 1.0):
            errs.append(f"{k} must be inside (0,1)")
    if not (0.0 < inp["oci_ppe_now"] < inp["equity_aug"] + inp["debt_aug"]):
        errs.append("oci_ppe_now implausible against the balance sheet")
    if inp["window_years"] != 3:
        errs.append(f"window_years={inp['window_years']:g}: A19 names a three-year window (FY29-31, ends FY2031)")

    # Ex-99.1 table 10 identity — guards a stale or miskeyed revenue row.
    rev_sum = sum(inp[f"rev_{ln}_fy26"] for ln in LINES) + inp["oci_rev_fy26"]
    if abs(rev_sum - FY26_TOTAL_REVENUE) > 1.0:
        errs.append(f"FY26 revenue identity: lines sum {rev_sum:.0f} != {FY26_TOTAL_REVENUE:.0f}")

    errs.extend(check_capex_constituent(inp["capex_guide_low"], inp["capex_guide_high"]))

    # A2e-7a: no probability may sit in the Inputs table; and the double-count
    # guard (A9): no option row may come back.
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in the zone+V table only (A2e-7a)")
    if "v_opt" in inp:
        errs.append("Inputs carry v_opt — the FY29-31 ramp is the D-bucket window, not an option (A9)")

    return errs


def assert_flat_multiples(pe_sw: dict[str, float]) -> list[str]:
    """The software leg carries no per-tier multiple (A2e-2c); the OCI ladder is ROE_proj by design."""
    errs: list[str] = []
    for tier in ("l", "h"):
        if pe_sw[tier] != pe_sw["m"]:
            errs.append(
                f"software multiple ratio {tier}/m = {pe_sw[tier] / pe_sw['m']:.4f} != 1.000 "
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
    baskets = parse_baskets(md)
    errors = sanity_checks(inp, baskets)

    r = inp["r_perp"]
    r_non, r_open, r_open_t = inp["r_oci_non"], inp["r_oci_open"], inp["r_oci_open_t"]
    k_lab = inp["k_lab"]
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_fy28"]
    n_win = int(inp["window_years"])
    share_open = inp["rpo_share_openai"]

    # ---- Step 1: software annuity leg, FY28E numerator (A4/A5) ----
    def rev_sw(years: int) -> float:
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
    pe_sw = {t: pe_sw_m for t in TIERS}
    errors.extend(assert_flat_multiples(pe_sw))

    # ---- Step 3: OCI residual of the consensus EPS range -> ROE_proj L / M (A2/A3/A18) ----
    eps = {"l": inp["eps_fy28_low"], "m": inp["eps_fy28_mid"], "h": inp["eps_fy28_high"]}
    rev_fy28 = {"l": inp["rev_fy28_low"], "m": inp["rev_fy28_mid"], "h": inp["rev_fy28_high"]}

    def nopat_total(e: float) -> float:
        ni_gaaplike = e * sh - inp["sbc_fy28"] * keep
        return ni_gaaplike + inp["int_fy28"] * keep

    nopat_oci = {t: nopat_total(eps[t]) - nopat_sw for t in TIERS}
    oci_rev_fy28 = {t: rev_fy28[t] - rev_sw_fy28 for t in TIERS}
    oci_margin = {t: nopat_oci[t] / keep / oci_rev_fy28[t] for t in TIERS}

    # A residual that turns negative means the software bridge has swallowed
    # the company; the implied margin must sit under the sell-side GM ceiling.
    for t in TIERS:
        if nopat_oci[t] <= 0:
            errors.append(f"OCI residual NOPAT {t.upper()} = {nopat_oci[t]:.0f} <= 0 — the OCI leg must not be negative (A6)")
        if not (0.0 < oci_margin[t] <= OCI_EBIT_MARGIN_CAP):
            errors.append(
                f"implied OCI EBIT margin {t.upper()} = {oci_margin[t]:.1%} outside (0, {OCI_EBIT_MARGIN_CAP:.0%}]"
                f" — the residual is inconsistent with the sell-side GM ceiling (A4/A5)"
            )

    k_spent = inp["oci_ppe_now"] + inp["capex_rest_fy27"] - inp["da_rest_fy27"]
    if abs(k_spent - inp["k_spent_gross"]) > 1.0:
        errors.append(f"k_spent_gross: stated {inp['k_spent_gross']:.0f} vs recomputed {k_spent:.0f} (A8)")
    k_net = k_spent - inp["prepay_cum"]
    if k_net <= 0:
        errors.append("K_spent net-of-prepay must be positive")
    # D-bucket consistency (校验步骤 4): the L / M ROE_proj ARE the consensus
    # residuals over K_spent; H is an external benchmark and is not derived.
    roe_resid = {t: nopat_oci[t] / k_spent for t in TIERS}
    for t in ("l", "m"):
        if abs(roe_resid[t] - inp[f"roe_proj_{t}"]) > ROE_PROJ_TOL:
            errors.append(f"roe_proj_{t}: stated {inp[f'roe_proj_{t}']} vs residual {roe_resid[t]:.4f} (A18)")
    roe_proj = {t: inp[f"roe_proj_{t}"] for t in TIERS}

    # K_remain per year = (RPO half over three years - FY28E OCI revenue) / turnover.
    turnover_book = oci_rev_fy28["m"] / k_spent
    rpo_run_rate = inp["rpo"] / 2.0 / 3.0
    incr_rev = rpo_run_rate - oci_rev_fy28["m"]
    for field, turn in (("k_remain_yr_book", turnover_book), ("k_remain_yr_aws", AWS_TURNOVER)):
        calc = incr_rev / turn
        if abs(calc - inp[field]) > K_REMAIN_REL_TOL * inp[field]:
            errors.append(f"{field}: stated {inp[field]:.0f} vs recomputed {calc:.0f} (A19)")
    k_remain = {"l": inp["k_remain_yr_book"], "m": inp["k_remain_yr_book"], "h": inp["k_remain_yr_aws"]}
    # L world: the OpenAI half is never built, so its sub-leg has no window (A6).
    open_window = {"l": False, "m": True, "h": True}

    # ---- Step 4: OCI D-bucket project value, two sub-legs (A6/A7/A19) ----
    def sub_leg(
        k: float, r_cap: float, r_disc: float, roe: float, kr: float, window: bool, n: int, keep_k: float = 1.0
    ) -> tuple[float, float]:
        """(base, window) in $M.

        Capital is capitalised at r_cap (the steady state it earns in) and each
        window tranche is discounted back at r_disc (the road to it); keep_k is
        the certainty-equivalent haircut on the value.  A single-basket
        sub-leg passes r_cap == r_disc and keep_k == 1.
        """
        base = k * roe / r_cap
        win = sum(kr * (roe / r_cap - 1.0) / (1.0 + r_disc) ** t for t in range(1, n + 1)) if window else 0.0
        return base * keep_k, win * keep_k

    def oci_value(
        t: str,
        roe: float | None = None,
        r_n: float = r_non,
        r_o: float = r_open,
        r_ot: float = r_open_t,
        kl: float = k_lab,
        kr: float | None = None,
        share: float = share_open,
        n: int = n_win,
        k: float = k_spent,
    ) -> dict[str, float]:
        roe = roe_proj[t] if roe is None else roe
        kr = k_remain[t] if kr is None else kr
        bn, wn = sub_leg(k * (1 - share), r_n, r_n, roe, kr * (1 - share), True, n)
        bo, wo = sub_leg(k * share, r_ot, r_o, roe, kr * share, open_window[t], n, 1.0 - kl)
        return {"base_non": bn, "win_non": wn, "base_open": bo, "win_open": wo, "total": bn + wn + bo + wo}

    parts = {t: oci_value(t) for t in TIERS}
    v_oci = {t: parts[t]["total"] for t in TIERS}
    for t in TIERS:
        if v_oci[t] <= 0:
            errors.append(f"OCI value {t.upper()} = {v_oci[t]:.0f} <= 0 — the OCI leg must not be negative (A6)")

    # ---- Step 5: closing item (A11) ----
    net_debt_aug = inp["debt_aug"] - inp["cash_aug"]
    burn_rest_fy27 = inp["capex_rest_fy27"] - inp["ocf_rest_fy27"] + inp["div_rest_fy27"]
    net_debt_fy28 = net_debt_aug + burn_rest_fy27
    closure = -(net_debt_fy28 + inp["pref_liq"])

    def per_share(v_oci_leg: float, v_sw_leg: float = v_sw, close: float = closure, shares: float = sh) -> float:
        return (v_sw_leg + v_oci_leg + close) / shares

    def band_at(**kw) -> tuple[float, float, float]:
        return tuple(per_share(oci_value(t, **kw)["total"]) for t in TIERS)  # type: ignore[return-value]

    # ---- Step 6: reference band (BLOCKED: no zone) ----
    L, M, H = band_at()
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    # ---- Step 7: ③ guardrail on the same-basis forward band, 降篮 path, BLOCKED (A12/A20/A21) ----
    pe_fwd = {t: v / eps["m"] for t, v in zip(TIERS, (L, M, H))}
    out_of_band = pe_fwd["m"] < inp["pe_fwd_min"]
    downgrade = []
    # Reference coordinates: the OpenAI sub-leg as ONE basket b, no haircut
    # (the pre-pair reading).  The pair sits between 篮 7 and 篮 4 by
    # construction, so 篮 4 un-haircut is the most lenient rate reading.
    for b in OPENAI_DOWNGRADE_BASKETS:
        band_b = band_at(r_o=basket_r(b), r_ot=basket_r(b), kl=0.0)
        downgrade.append((b, basket_r(b), band_b, band_b[1] / eps["m"]))
    blocked = out_of_band and all(pe_m < inp["pe_fwd_min"] for _, _, _, pe_m in downgrade)
    # Header contract (AGENTS.md「BLOCKED — 题头契约」): same parser as the digest.
    header_blocked = load_framework(FRAMEWORK).blocked is not None
    if blocked != header_blocked:
        errors.append(
            f"③ verdict: recomputed {'BLOCKED' if blocked else 'in band after 降篮'} but header "
            f"{'has' if header_blocked else 'lacks'} the `> **状态：BLOCKED**` line (A21)"
        )
    if pe_fwd["h"] > inp["pe_fwd_max"]:
        errors.append(f"H / eps_fy28_mid = {pe_fwd['h']:.2f}x > pe_fwd_max {inp['pe_fwd_max']:.2f}x (A12)")

    # 表2′: uniform δ on both OCI sub-legs (software leg untouched, ROE_proj M
    # unchanged) that lifts M exactly to the band floor; and its ROE_proj twin.
    m_floor = inp["pe_fwd_min"] * eps["m"]

    def m_at_delta(d: float) -> float:
        return per_share(oci_value("m", r_n=r_non + d, r_o=r_open + d, r_ot=r_open_t + d)["total"])

    def m_at_roe(z: float) -> float:
        return per_share(oci_value("m", roe=z)["total"])

    delta_floor = bisect(lambda d: m_at_delta(d) - m_floor, -0.09, 0.05)
    roe_floor = bisect(lambda z: m_at_roe(z) - m_floor, 0.05, 0.6)
    band_edge = band_at(r_n=r_non + delta_floor, r_o=r_open + delta_floor, r_ot=r_open_t + delta_floor)
    a_edge, b_edge = (band_edge[0] + band_edge[1]) / 2, (band_edge[1] + band_edge[2]) / 2
    zone_edge = zone_of(inp["price"], *band_edge)
    delta_price = bisect(lambda d: m_at_delta(d) - inp["price"], -0.09, 0.05)
    roe_price = bisect(lambda z: m_at_roe(z) - inp["price"], 0.05, 0.8)
    mkt_oci = inp["price"] * sh + net_debt_fy28 + inp["pref_liq"] - v_sw
    sm = STATED_BAND_EDGE.search(md)
    if sm is None:
        errors.append("表2′ 带边带 not stated in Outputs (A21 step 4 ②)")
    else:
        for lbl, said, calc in zip(("L′", "M′", "H′"), (float(g) for g in sm.groups()), band_edge):
            if abs(said - calc) > TOL:
                errors.append(f"表2′ {lbl}: stated {said} vs recomputed {calc:.4f}")

    # ---- Stated vs recomputed ----
    # BLOCKED: the deck line is a reference band, so L/M/H/A/B must reproduce
    # but no zone is asserted.  The doc states no zone (stated_zone -> None);
    # handing that same value back makes the library's zone comparison a no-op
    # without touching eval/lib.  If a zone ever gets written into a BLOCKED
    # doc, the header check above and this line disagree loudly.
    said_zone = stated_zone(md)
    if blocked and said_zone is not None:
        errors.append(f"BLOCKED framework states zone `{said_zone}` — a BLOCKED ticker MUST NOT carry a zone (A21)")
    zone_ref = zone_of(inp["price"], L, M, H)
    errors.extend(check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, said_zone if blocked else zone_ref, TOL))

    # ================= diagnostics =================
    print(f"formula_id={FORMULA_ID}")
    print(
        f"baskets: " + ", ".join(f"{k} 篮 {baskets.get(k)} r {inp[k]:.1%}" for k in R_FIELDS)
        + f" | g2_sw {inp['g2_sw']:.1%} cap {min(0.06, r - 0.04):.1%} | OCI perpetual g: none (D-bucket)"
    )
    print(
        f"software leg: rev FY26 {rev_sw_fy26 / BN:.1f}B -> FY28E {rev_sw_fy28 / BN:.1f}B"
        f" | seg margin {sw_margin_pct:.1%} (OCI contrib est {oci_contrib_fy26 / BN:.1f}B removed)"
        f" | EBIT {nopat_sw / keep / BN:.1f}B NOPAT {nopat_sw / BN:.1f}B"
        f" | IC {ic_sw / BN:.1f}B ROE {roe_sw:.1%} g {inp['g2_sw']:.1%} -> PE {pe_sw_m:.2f}x payout {pay_sw:.1%}"
        f" -> {v_sw / sh:.2f}/sh (flat)"
    )
    print(
        f"OCI residual (ROE_proj source): K_spent gross {k_spent / BN:.1f}B / net-of-prepay {k_net / BN:.1f}B"
        f" | FY28 book turnover {turnover_book:.3f} | RPO/2/3y {rpo_run_rate / BN:.1f}B/yr - FY28E OCI M {oci_rev_fy28['m'] / BN:.1f}B"
        f" = incremental {incr_rev / BN:.1f}B/yr -> K_remain {inp['k_remain_yr_book'] / BN:.1f}B (book) / {inp['k_remain_yr_aws'] / BN:.1f}B (AWS {AWS_TURNOVER})"
        f" x {n_win}y window"
    )
    print("  tier  EPS    NOPAT_total  NOPAT_oci  OCI rev FY28E  impl EBIT margin  resid/K   ROE_proj")
    for t in TIERS:
        print(
            f"    {t.upper()}  {eps[t]:5.2f} {nopat_total(eps[t]) / BN:10.1f}B {nopat_oci[t] / BN:8.1f}B"
            f" {oci_rev_fy28[t] / BN:10.1f}B {oci_margin[t]:13.1%} {roe_resid[t]:9.1%} {roe_proj[t]:9.1%}"
            f"{'' if t != 'h' else '  (AWS-2024 state, external; residual 14.6% is a reading only)'}"
        )
    print(
        f"OCI D-bucket sub-legs ($M): K non-OpenAI {k_spent * (1 - share_open) / BN:.1f}B @ r {r_non:.0%}"
        f" | K OpenAI {k_spent * share_open / BN:.1f}B @ pair r {r_open:.0%}->{r_open_t:.0%} x (1-k_lab {k_lab:g})"
        f" | L: OpenAI window off"
    )
    print("  tier   nonOpenAI base / window      OpenAI base / window      OCI total   x K    $/sh")
    for t in TIERS:
        p = parts[t]
        print(
            f"    {t.upper()}  {p['base_non'] / BN:9.1f}B / {p['win_non'] / BN:+8.1f}B"
            f"   {p['base_open'] / BN:9.1f}B / {p['win_open'] / BN:+8.1f}B"
            f"   {v_oci[t] / BN:8.1f}B {v_oci[t] / k_spent:5.2f}x {v_oci[t] / sh:7.2f}"
        )
    print(
        f"closure: net debt 08-31 {net_debt_aug / BN:.1f}B + rest-FY27 burn {burn_rest_fy27 / BN:.1f}B"
        f" (capex {inp['capex_rest_fy27'] / BN:.1f} - OCF {inp['ocf_rest_fy27'] / BN:.1f} + div {inp['div_rest_fy27'] / BN:.1f})"
        f" = {net_debt_fy28 / BN:.1f}B; pref {inp['pref_liq'] / BN:.1f}B -> {closure / sh:.2f}/sh"
        f" | depreciation lag capex_q1/dep_q1 = {inp['capex_q1'] / inp['dep_q1']:.1f}x (A10)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  (reference band; BLOCKED -> no zone)")
    print("  leg $/sh   software(PE)   oci nonOpenAI   oci OpenAI   closure     total")
    for t, v in zip(TIERS, (L, M, H)):
        p = parts[t]
        print(
            f"    {t.upper()}   {v_sw / sh:7.2f}({pe_sw[t]:5.2f}x) {(p['base_non'] + p['win_non']) / sh:12.2f}"
            f" {(p['base_open'] + p['win_open']) / sh:12.2f} {closure / sh:9.2f} {v:9.2f}"
        )
    print(
        f"tier decomposition (A2e-5): L/M {L / M:.3f} | H/M {H / M:.3f} | OCI value ratio L/M {v_oci['l'] / v_oci['m']:.3f}"
        f" H/M {v_oci['h'] / v_oci['m']:.3f} | software flat 1.000 | (H-L)/2M {(H - L) / (2 * M):.3f}"
        f" — the ladder is ROE_proj {roe_proj['l']:.1%} / {roe_proj['m']:.1%} / {roe_proj['h']:.1%}"
    )
    print(
        f"③ guardrail (A12, same-basis forward PE on FY28E mid {eps['m']}): band {inp['pe_fwd_min']:.2f}-{inp['pe_fwd_max']:.2f}x"
        f" (p10 {inp['pe_fwd_p10']:.2f} / med {inp['pe_fwd_med']:.2f} / p90 {inp['pe_fwd_p90']:.2f})"
        f" | L {pe_fwd['l']:.2f}x M {pe_fwd['m']:.2f}x H {pe_fwd['h']:.2f}x"
        f" | price {inp['price'] / eps['m']:.1f}x"
        f" -> M {'OUT OF BAND' if out_of_band else 'inside'}"
    )
    print("  single-basket reference path (OpenAI sub-leg as one basket, no k_lab; non-OpenAI already 篮 4):")
    for b, rb, band_b, pe_m in downgrade:
        print(f"    篮 {b} r {rb:.0%}: L/M/H = {band_b[0]:.2f} / {band_b[1]:.2f} / {band_b[2]:.2f}  M fwd {pe_m:.2f}x"
              f" {'<' if pe_m < inp['pe_fwd_min'] else '>='} {inp['pe_fwd_min']}")
    print(f"  verdict: {'BLOCKED — 篮 4 still out of band; no zone' if blocked else 'in band'} | header {'BLOCKED' if header_blocked else '(no BLOCKED line)'}")
    print(
        f"  表2′ band-edge δ = {delta_floor:+.2%} (r {r_non + delta_floor:.2%} / {r_open + delta_floor:.2%}->{r_open_t + delta_floor:.2%}):"
        f" L/M/H = {band_edge[0]:.2f} / {band_edge[1]:.2f} / {band_edge[2]:.2f}  A′ {a_edge:.2f} B′ {b_edge:.2f}"
        f" -> zone@band-edge r = {zone_edge} | equivalent ROE_proj {roe_floor:.1%}"
    )
    print(
        f"  implied r(P): uniform δ = {delta_price:+.2%} (r {r_non + delta_price:.2%} / {r_open + delta_price:.2%}->{r_open_t + delta_price:.2%})"
        f" | equivalent ROE_proj {roe_price:.1%} | market OCI = {mkt_oci / BN:.1f}B = {mkt_oci / k_spent:.2f}x K_spent"
        f" = {mkt_oci / nopat_oci['m']:.1f}x M NOPAT"
    )
    print(
        f"  reference-band reading only: price {inp['price']} -> {zone_ref} (P/H {inp['price'] / H:.2f}); "
        + " | ".join(f"{lbl} {tp:.0f} -> {zone_of(tp, L, M, H)}" for lbl, tp in STREET_TPS)
        + f" | 52w low {WEEK52_LOW} -> {zone_of(WEEK52_LOW, L, M, H)}"
    )
    pe_ttm = {t: v / inp["eps_ttm_gaap"] for t, v in zip(TIERS, (L, M, H))}
    print(
        f"disclosure: trailing GAAP band {inp['pe_own_min']:.2f}-{inp['pe_own_max']:.2f}x (p50 {inp['pe_own_p50']:.2f}, denominator {inp['eps_ttm_gaap']})"
        f" not same-basis — band reads L {pe_ttm['l']:.1f}x M {pe_ttm['m']:.1f}x H {pe_ttm['h']:.1f}x"
    )
    _lo, _hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(
        f"capex axis (constituent, A16): FY27 guide ${inp['capex_guide_low'] / 1e9:.0f}-{inp['capex_guide_high'] / 1e9:.0f}B"
        f" = {_lo:.1%}-{_hi:.1%} of the axis 2026 base"
    )
    print("floor: none (PP&E is debt- and prepay-funded; no hidden asset) — nothing max()'d")
    ev = inp["price"] * sh + net_debt_aug + inp["pref_liq"]
    print(
        f"market read: mcap {inp['price'] * sh / BN:.0f}B EV {ev / BN:.0f}B"
        f" | EV/FY28E NOPAT(M) {ev / (nopat_sw + nopat_oci['m']):.1f}x"
    )

    # ---- sensitivities (all disclosure; none changes BLOCKED) ----
    def fmt(b: tuple[float, float, float]) -> str:
        return f"{b[0]:.2f} / {b[1]:.2f} / {b[2]:.2f}"

    for kl in (0.0, 0.5):
        b = band_at(kl=kl)
        print(f"sensitivity k_lab={kl:g} (axis value {k_lab:g}): {fmt(b)}  M fwd {b[1] / eps['m']:.2f}x")
    print(f"sensitivity H @ AWS-2025 state ROE_proj {ROE_PROJ_H_AWS_2025:.1%}: H = {per_share(oci_value('h', roe=ROE_PROJ_H_AWS_2025)['total']):.2f}")
    for dp in ROE_PROJ_SENSITIVITY:
        b = tuple(per_share(oci_value(t, roe=roe_proj[t] + dp)["total"]) for t in TIERS)
        print(f"sensitivity ROE_proj {dp:+.0%} all tiers: {fmt(b)}  M fwd {b[1] / eps['m']:.2f}x")
    for n in WINDOW_SENSITIVITY:
        print(f"sensitivity window n={n}: {fmt(band_at(n=n))}")
    for so in SHARE_SENSITIVITY:
        print(f"sensitivity OpenAI RPO share {so:.0%}: {fmt(band_at(share=so))}")
    for f in K_REMAIN_SENSITIVITY:
        b = tuple(per_share(oci_value(t, kr=k_remain[t] * f)["total"]) for t in TIERS)
        print(f"sensitivity K_remain x{f:.1f}: {fmt(b)}")
    print(f"sensitivity K_spent net-of-prepay {k_net / BN:.1f}B (x{k_net / k_spent:.2f}, ROE_proj unchanged): {fmt(band_at(k=k_net))}")
    for dg in G_SW_SENSITIVITY:
        n_, _, _, pe_ = software_leg(inp["oci_gm_est"], inp["g2_sw"] + dg)
        print(f"sensitivity g_sw={inp['g2_sw'] + dg:.1%}: software PE {pe_:.2f}x -> M {per_share(v_oci['m'], n_ * pe_):.2f}")
    n_, _, _, pe_ = software_leg(inp["oci_gm_est"], G_SW_PEER)
    print(f"sensitivity g_sw peer-implied {G_SW_PEER:.2%} (A5, not adopted): software PE {pe_:.2f}x -> M {per_share(v_oci['m'], n_ * pe_):.2f}")
    print(
        f"sensitivity net debt ±{NET_DEBT_SENSITIVITY / BN:.0f}B: M = "
        f"{per_share(v_oci['m'], close=closure + NET_DEBT_SENSITIVITY):.2f} / "
        f"{per_share(v_oci['m'], close=closure - NET_DEBT_SENSITIVITY):.2f}"
    )
    for m in (inp["xchk_ev_ebit_low"], inp["xchk_ev_ebit_high"]):
        vals = [per_share(nopat_oci[t] / keep * m) for t in TIERS]
        print(
            f"cross-check OCI at EV/EBIT {m:.0f}x on the FY28E residual (street, NOT in the band): L/M/H = "
            f"{vals[0]:.2f} / {vals[1]:.2f} / {vals[2]:.2f}"
        )
    disc = 1.0 / (1.0 + r)
    print(f"sensitivity discount 1y at r_perp: L/M/H = {L * disc:.2f} / {M * disc:.2f} / {H * disc:.2f}")
    print(f"price={inp['price']} status={'BLOCKED' if blocked else 'ok'} zone={'n/a (BLOCKED)' if blocked else zone_ref}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
