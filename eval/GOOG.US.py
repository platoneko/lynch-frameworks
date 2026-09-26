#!/usr/bin/env python3
"""GOOG.US (Alphabet) valuation eval — recompute anchors from frameworks/GOOG.US.md.

frameworks/GOOG.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: goog_fwd_numerator_gordon_services_cloud_assets_v3

Main ruler: SOTP on a FORWARD numerator — the FY2027E sell-side EPS range
(13.50 / 14.83 / 17.21, 51 estimates) carried onto the three segment legs by
one scalar per tier — priced at ONE growth rate per leg.  Every multiple is
GENERATED from a named growth rate rather than lifted off a historical PE
percentile (AGENTS.md「永续增长口径」), and each leg carries its own invested
capital, so its ROE — and therefore the retention its growth costs — is
derived, not chosen.  ROE is E_{n+1}/B_n (valuation-rules 62c72a2, A25): the
tier's FY2027E leg NOPAT over the leg's FY2027 OPENING invested capital = the
2026-06-30 capital rolled over the unbooked 2H26 run-rate NOPAT at the
growth-required retention b1 = g/ROE, closed form IC_open = IC0 / (1 - g*N/E).  r comes from the basket each leg is assigned
to (valuation-rules「§r 篮子」): both Gordon legs sit in 篮 4 龙头制造
(`r_perp`, A24); the Inputs source cell names the basket and `check_r` demands
the value match it.  g2 is capped at g_cap(r) = min(6%, r - 4%).

    Services + Alphabet-level   ROE 54.6 / 60.1 / 69.9%   (IC0 247.8B, residual)
    Google Cloud                ROE 10.5 / 20.3 / 23.6%   (IC0 160.0B, from HSBC 2027E ROIC)

No tier names its own growth rate: g2_svc = 5.5% (median of the META / RDDT /
TTD market-implied cross-section, GOOG excluded; A21) and g2_cld = 6.0% (6.5%
capped) are single inputs shared by L, M and H.  The multiples still differ by
tier, mechanically: a bigger FY2027E numerator on the same opening capital is a
higher ROE, which needs less retention for the same g.  The L tier's cloud
multiple additionally carries A18's margin retreat (realised 20.7%) on the same
g2_cld.  The A2e-2c proof that the tiers are numerator, not multiple, is the
flat-multiple ladder: priced at the M multiples the ladder must still stand.

Consequence worth stating: the cloud leg still trades at a LOWER multiple than
the services leg (lambda 0.796). At its own growth an ROE-16% leg is worth less
than an ROE-47% leg, because the same growth costs it roughly three times the
retained capital. The retired lambda = 1.2727 asserted the opposite and could
only be true if cloud grew ~2.2pp faster forever — an assumption that was
hidden inside a multiple rather than named as a rate.

Why GAAP EPS is not used: H1 2026 other income carries $135.9B of unrealized
equity-securities gains (SpaceX and a private company), so trailing EPS - and
every screen PE built on it - is meaningless for this name.

Disclosures (printed, never errors): the band with g2_svc shifted -1pp / -0.5pp
and the zone it lands in (敏感区, valuation-rules「g₂ 的杠杆 MUST 显式」), and the
single-stage implied r(P) against the basket r.

Run:  python3 frameworks/eval/GOOG.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    capex_constituent_share,
    check_capex_constituent,
    check_lab_mount,
)
from eval.lib.gordon import (  # noqa: E402
    check_basket_pair,
    check_g_cap,
    check_k_declared,
    check_r,
    payout,
    perpetual_pe,
)
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "GOOG.US.md"
FORMULA_ID = "goog_fwd_numerator_gordon_services_cloud_assets_v3"
TOL = 0.05
BN = 1e3  # inputs are in $M; report in $B
# 10-Q 2026-06-30 Note 15: H1 consolidated income from operations ($M)
H1_TOTAL_OPERATING_INCOME = 80466.0
# AGENTS.md「永续增长口径」: inside 2pp of the pole at r the multiple/g map is
# ill-conditioned — a whole turn of PE moves g by a rounding error — so a g that
# close to r may not carry an anchor.
MIN_R_MINUS_G = 0.02
# The trailing run-rate no longer feeds the anchors, but it is still the base
# the forward scalars are applied to, so a large gap means it went stale.
MAX_CONSENSUS_GAP = 0.10
# The tier scalars must be the consensus range itself, not three free numbers.
K_LADDER_TOL = 1e-4
# The opening-book roll retains only b1 = g/ROE of the unbooked 2H26 (A25); the
# capex wave retains far more (A23 待补), so report the band under a materially
# larger FY2027 opening capital base.
EQUITY_SENSITIVITY = (1.20, 1.40)
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | ... |"""
    out: dict[str, float] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, raw = cells[0], cells[1]
        if key in ("字段名", "--------", "---") or raw in ("取值",):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


# zone_of lives in eval/lib/zones.py — the daily digest maps every ticker with
# that same function, so a local copy here would be a second source of truth for
# the one thing that must stay comparable across the whole repo.


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


REQUIRED = [
    "price",
    "shares_diluted",
    "tax_rate",
    "oi_services_h1",
    "oi_cloud_h1",
    "oi_corp_h1",
    "corp_oneoff_h1",
    "oi_other_bets_h1",
    "r_perp",
    "r_cld_lab",
    "r_cld_lab_t",
    "k_lab",
    "roic_marg_cld",
    "share_lab_cld",
    "equity_services",
    "equity_cloud",
    "payout_3y",
    "k_eps_l",
    "k_eps_m",
    "k_eps_h",
    "g2_svc",
    "g2_cld",
    "eps_fy27e_low",
    "eps_fy27e_high",
    "pe_own_top",
    "pe_own_p50",
    "cash_and_securities",
    "mkt_equity_sec",
    "other_mkt_equity_sec",
    "nonmkt_sec",
    "lt_debt",
    "pref_liq",
    "dtl_noncurrent",
    "d_port_l",
    "d_port_m",
    "d_port_h",
    "waymo_post_money",
    "waymo_stake",
    "d_ob_l",
    "d_ob_m",
    "d_ob_h",
    "capex_h1",
    "dep_h1",
    "ebit_fy26e_consensus",
    "eps_fy27e_consensus",
    "cloud_om_l",
    "cloud_om_now",
    "capex_guide_low",
    "capex_guide_high",
    "v_opt",
]

# V_opt is a parallel dimension, never part of L/M/H.  It only splits the region
# above H into "the market is paying for a named option" and "beyond every
# option we can name".  Its share of M is a disclosure, never a failure
# (skill A2e-7e): past this share the ticker is 期权主导型 and §0 must say so,
# but the eval only reports it.
OPTION_DOMINANT_SHARE = 1.00


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    """Ticker-specific guards on the inputs: growth band, numerator ladder, identity."""
    errs: list[str] = []

    # r is a basket, not a dial: the r row must name its basket in the Inputs
    # source cell and carry that basket's value (A24, valuation-rules「§r 篮子」).
    r = inp["r_perp"]
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errs += check_r(r, "r_perp", baskets.get("r_perp"))
    if "r_cld_lab" not in baskets:
        errs.append("r_cld_lab: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errs += check_r(inp["r_cld_lab"], "r_cld_lab", baskets.get("r_cld_lab"))
    # The lab sub-leg is a basket PAIR (valuation-rules「篮子对」, A27): 篮 7 is what
    # Anthropic is as a payer today, 篮 4 what it is if it makes it.  Every leg is
    # single-stage, so the steady state capitalises at the terminal rate and the
    # shared k_lab carries all of the arrival risk (_AXIS.frontier-lab-funding §3).
    if "r_cld_lab_t" not in baskets:
        errs.append("r_cld_lab_t: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errs += check_basket_pair(inp["r_cld_lab"], inp["r_cld_lab_t"], "lab",
                              baskets.get("r_cld_lab"), baskets.get("r_cld_lab_t"))
    errs += check_k_declared(inp["r_cld_lab"], inp["r_cld_lab_t"], (inp["k_lab"],) * 3, "k_lab")
    errs += [f"axis: {e}" for e in check_lab_mount(inp["k_lab"])]
    # G_cap stays keyed to the JOURNEY basket (「篮子对」判据 3).
    errs += check_g_cap(inp["g2_cld"], inp["r_cld_lab"], "g2_cld@lab")
    if not (0.0 < inp["share_lab_cld"] < 1.0):
        errs.append("share_lab_cld outside (0,1)")
    if not (0.0 < inp["roic_marg_cld"] < 1.0):
        errs.append("roic_marg_cld outside (0,1)")

    # Growth: one rate per leg, shared by every tier. Both must sit under the
    # cap set by the legs' basket r (valuation-rules「永续增长口径」) and clear the pole.
    for leg in ("svc", "cld"):
        g = inp[f"g2_{leg}"]
        errs += check_g_cap(g, r, f"g2_{leg}")
        if r - g <= 0:
            errs.append(f"perpetuity diverges on the {leg} leg: g2 >= r_perp")
        elif r - g < MIN_R_MINUS_G:
            errs.append(
                f"r_perp - g2_{leg} = {r - g:.2%} < {MIN_R_MINUS_G:.0%} — g sits at the pole "
                f"where a turn of PE is a rounding error in g (AGENTS.md)"
            )

    # The tier ladder is the numerator, so IT is what must be monotone — and it
    # must be the sell-side FY2027E range itself, not three chosen scalars
    # (A2e-2a: L and H are the two ends of one consensus distribution).
    if not (inp["k_eps_l"] < inp["k_eps_m"] < inp["k_eps_h"]):
        errs.append("k_eps_* numerator ladder not increasing")
    if inp["k_eps_l"] <= 0:
        errs.append("k_eps_l must be positive")
    mean = inp["eps_fy27e_consensus"]
    for tier, endpoint in (("l", "eps_fy27e_low"), ("h", "eps_fy27e_high")):
        want = inp[endpoint] / mean
        got = inp[f"k_eps_{tier}"] / inp["k_eps_m"]
        if abs(got - want) > K_LADDER_TOL:
            errs.append(
                f"k_eps_{tier}/k_eps_m = {got:.5f} != {endpoint}/eps_fy27e_consensus "
                f"= {want:.5f} — the tier ladder is not the consensus range (A2e-2a)"
            )

    for leg in ("equity_services", "equity_cloud"):
        if inp[leg] <= 0:
            errs.append(f"{leg} must be positive — ROE is derived from it")

    errs.extend(check_capex_constituent(inp["capex_guide_low"], inp["capex_guide_high"]))

    for name in ("d_port", "d_ob"):
        l, m, h = (inp[f"{name}_{k}"] for k in "lmh")
        if not (1.0 >= l > m > h >= 0.0):
            errs.append(f"{name}_* must be a decreasing band inside [0,1]")

    if not (0.0 < inp["tax_rate"] < 0.5):
        errs.append("tax_rate out of plausible range")

    # 10-Q Note 15 segment identity — guards against a stale/miskeyed segment row.
    seg_sum = (
        inp["oi_services_h1"]
        + inp["oi_cloud_h1"]
        + inp["oi_other_bets_h1"]
        + inp["oi_corp_h1"]
    )
    if abs(seg_sum - H1_TOTAL_OPERATING_INCOME) > 1.0:
        errs.append(
            f"segment identity: sum {seg_sum:.0f} != H1 operating income "
            f"{H1_TOTAL_OPERATING_INCOME:.0f}"
        )

    # Other Bets losses stay out of the earnings legs (A2/A15 no-double-count).
    if inp["oi_other_bets_h1"] >= 0:
        errs.append("oi_other_bets_h1 expected negative; recheck A15 handling")

    return errs


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    baskets = parse_baskets(md)
    errors = sanity_checks(inp, baskets)

    # Step 1 — trailing base: H1 x2 segment OI, after normalized tax. This is
    # the base the forward scalars ride on, and the denominator of the A6
    # guardrail; it is no longer itself the numerator.
    keep = 1.0 - inp["tax_rate"]
    nopat_services = inp["oi_services_h1"] * 2 * keep
    nopat_cloud = inp["oi_cloud_h1"] * 2 * keep
    nopat_corp = (inp["oi_corp_h1"] + inp["corp_oneoff_h1"]) * 2 * keep
    svc_leg = nopat_services + nopat_corp
    core_eps = (nopat_services + nopat_cloud + nopat_corp) / inp["shares_diluted"]

    # Step 4 — asset legs and closing item (listed equities moved out of net cash).
    net_cash = (
        inp["cash_and_securities"]
        - inp["mkt_equity_sec"]
        - inp["lt_debt"]
        - inp["pref_liq"]
    )
    # other_mkt_equity_sec sits under Other non-current assets, so it is in
    # neither cash_and_securities nor nonmkt_sec — without this term the
    # restricted SpaceX stake is in no leg at all.
    portfolio_gross = (
        inp["mkt_equity_sec"]
        + inp["other_mkt_equity_sec"]
        + inp["nonmkt_sec"]
        - inp["dtl_noncurrent"]
    )
    waymo_gross = inp["waymo_post_money"] * inp["waymo_stake"]

    # The L tier retreats the Cloud numerator to a margin this segment actually
    # printed a year ago (A18) — Alphabet gives no EPS guidance, but a realised
    # segment margin is evidence, not a forecast (skill A2e-2c).
    cloud_retreat = inp["cloud_om_l"] / inp["cloud_om_now"]

    # Step 3 — ONE growth rate per leg; ROE per tier on the leg's FY2027
    # OPENING invested capital (A25): IC0 (2026-06-30) rolled over the unbooked
    # 2H26 run-rate NOPAT at b1 = g/ROE, closed form IC_open = IC0/(1 - g*N/E).
    # No multiple can move without a capital base, a numerator or a growth rate
    # moving first.  The L tier's margin retreat scales the cloud numerator, so
    # the same capital earns less: the retreat costs ROE too, it is not free.
    r = inp["r_perp"]
    unbooked_svc = svc_leg / 2.0
    unbooked_cld = nopat_cloud / 2.0

    def roe_open(e_fy27: float, ic0: float, g: float, unbooked: float) -> float:
        if g * unbooked / e_fy27 >= 1.0:
            raise ValueError(f"opening-capital roll diverges: g*N/E = {g * unbooked / e_fy27:.3f}")
        return e_fy27 / (ic0 / (1.0 - g * unbooked / e_fy27))

    r_lab = inp["r_cld_lab_t"]  # the steady state capitalises at the terminal basket
    k_lab = inp["k_lab"]

    def tier_multiples(g_svc: float, g_cld: float, ic_scale: float = 1.0,
                       roic_marg: float | None = None, r_lab_: float | None = None) -> dict[str, dict[str, float]]:
        """Per-tier ROE and multiple for both legs; `ic_scale` is the A23 sensitivity.

        The cloud leg's snapshot ROE (FY2027E NOPAT / FY2027 opening capital) is
        computed and printed, but the retention that funds g_cld is priced at
        the MARGINAL steady-state ROIC of the capex wave (A26), scaled by the
        A18 margin retreat in the L tier.  The lab sub-leg (A27) shares that
        retention rate and capitalises at its terminal basket (篮子对).
        """
        rm = inp["roic_marg_cld"] if roic_marg is None else roic_marg
        rl = r_lab if r_lab_ is None else r_lab_
        out: dict[str, dict[str, float]] = {"roe_svc": {}, "roe_cld": {}, "ret_cld": {}, "pe_svc": {}, "pe_cld": {}, "pe_lab": {}}
        for tier, k_field, scale in (("l", "k_eps_l", cloud_retreat), ("m", "k_eps_m", 1.0), ("h", "k_eps_h", 1.0)):
            k = inp[k_field]
            out["roe_svc"][tier] = roe_open(svc_leg * k, inp["equity_services"] * ic_scale, g_svc, unbooked_svc)
            out["roe_cld"][tier] = roe_open(nopat_cloud * scale * k, inp["equity_cloud"] * ic_scale, g_cld, unbooked_cld)
            out["ret_cld"][tier] = rm * scale
            out["pe_svc"][tier] = perpetual_pe(g_svc, out["roe_svc"][tier], r)
            out["pe_cld"][tier] = perpetual_pe(g_cld, out["ret_cld"][tier], r)
            out["pe_lab"][tier] = perpetual_pe(g_cld, out["ret_cld"][tier], rl)
        return out

    tm = tier_multiples(inp["g2_svc"], inp["g2_cld"])
    roe_svc, roe_cld, pe_svc, pe_cld, pe_lab, ret_cld = tm["roe_svc"], tm["roe_cld"], tm["pe_svc"], tm["pe_cld"], tm["pe_lab"], tm["ret_cld"]
    b1_svc = {t: inp["g2_svc"] / roe_svc[t] for t in "lmh"}
    b1_cld = {t: inp["g2_cld"] / ret_cld[t] for t in "lmh"}
    share_lab = inp["share_lab_cld"]

    # The cloud leg MUST come out cheaper than the services leg. This is the
    # reversal of the retired lambda = 1.2727: even a percentage point of extra
    # growth cannot make an ROE-20% leg out-multiple an ROE-60% leg, because
    # that growth costs it ~3x the retained capital.
    for tier in ("l", "m", "h"):
        # Same terminal basket as the rest of cloud, so only the haircut keeps the
        # lab sub-leg below it per dollar of earnings.
        if pe_lab[tier] * (1.0 - k_lab) > pe_cld[tier] + 1e-9:
            errors.append(f"tier {tier}: lab sub-leg after k_lab out-values the non-lab cloud sub-leg")
        lam = pe_cld[tier] / pe_svc[tier]
        if lam >= 1.0:
            errors.append(
                f"tier {tier}: cloud/services multiple {lam:.3f} >= 1 — an ROE "
                f"{roe_cld[tier]:.1%} leg cannot out-multiple an ROE {roe_svc[tier]:.1%} "
                f"leg; the premium is unnamed"
            )
    # Perpetual state: every leg must fund its own growth out of its own earnings
    # (b1 = g/ROE in (0,1) — a stage payout priced negative is 发股融资, not this name).
    for tier in ("l", "m", "h"):
        for label, b1 in (("services", b1_svc[tier]), ("cloud", b1_cld[tier])):
            if not (0.0 < b1 < 1.0):
                errors.append(f"{label} {tier}: b1 = g/ROE = {b1:.3f} outside (0,1)")

    def legs(
        k_eps: float,
        mult_cld: float,
        d_port: float,
        d_ob: float,
        cloud_scale: float,
        mult_svc: float,
        mult_lab: float,
    ) -> dict[str, float]:
        """Per-share contribution of each leg; the anchor is their sum.

        The cloud numerator is split (A27): (1 - share_lab_cld) at the 篮 4
        multiple, share_lab_cld (Anthropic) at the same terminal multiple times
        (1 - k_lab) -- the haircut leaves the value, never the multiple.
        """
        sh = inp["shares_diluted"]
        cld_num = nopat_cloud * cloud_scale * k_eps
        return {
            "svc": svc_leg * k_eps * mult_svc / sh,
            "cld": cld_num * (1 - share_lab) * mult_cld / sh,
            "lab": cld_num * share_lab * mult_lab * (1.0 - k_lab) / sh,
            "cash": net_cash / sh,
            "port": portfolio_gross * (1 - d_port) / sh,
            "ob": waymo_gross * (1 - d_ob) / sh,
        }

    def anchor(
        k_eps: float,
        mult_cld: float,
        d_port: float,
        d_ob: float,
        cloud_scale: float,
        mult_svc: float,
        mult_lab: float,
    ) -> float:
        """Tier value: the FY2027E consensus scalar rides the whole numerator."""
        return sum(legs(k_eps, mult_cld, d_port, d_ob, cloud_scale, mult_svc, mult_lab).values())

    def anchor_from(t_: dict[str, dict[str, float]], tier: str) -> float:
        scale = cloud_retreat if tier == "l" else 1.0
        return anchor(inp[f"k_eps_{tier}"], t_["pe_cld"][tier], inp[f"d_port_{tier}"], inp[f"d_ob_{tier}"],
                      scale, t_["pe_svc"][tier], t_["pe_lab"][tier])

    L = anchor_from(tm, "l")
    M = anchor_from(tm, "m")
    H = anchor_from(tm, "h")
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    # V_opt deliberately does NOT enter zone_of: `stretched` stays P > H, and the
    # option delta is reported alongside the band rather than moving its edges.
    zone = zone_of(inp["price"], L, M, H)

    # Guardrail, not an input (AGENTS.md:74): the historical PE band no longer
    # generates the multiples, but a generated multiple that leaves the band the
    # name has actually printed means the growth rates went past the evidence.
    if H / core_eps > inp["pe_own_top"]:
        errors.append(
            f"生成的倍数越出自身实测带: H/core_eps = {H / core_eps:.2f}x > pe_own_top "
            f"{inp['pe_own_top']:.2f}x (AGENTS.md:74) — 回对话，勿调倍数"
        )

    # A2e-2c: price every tier at the M multiples (both legs) and the ladder
    # must still stand — proof the tiers are numerator, not multiple.
    flat_l = anchor(inp["k_eps_l"], pe_cld["m"], inp["d_port_l"], inp["d_ob_l"], cloud_retreat, pe_svc["m"], pe_lab["m"])
    flat_h = anchor(inp["k_eps_h"], pe_cld["m"], inp["d_port_h"], inp["d_ob_h"], 1.0, pe_svc["m"], pe_lab["m"])
    if not (flat_l < M < flat_h):
        print(
            f"FAIL: flat-multiple ladder collapsed: "
            f"{flat_l:.2f}/{M:.2f}/{flat_h:.2f} — tiers have no content "
            f"outside the multiples (A2e-2c)",
            file=sys.stderr,
        )
        return 1

    # Diagnostics: the trailing base the forward scalars ride on, and the
    # depreciation lag the FY27E consensus is assumed to already carry (A5).
    ebit_runrate = (
        inp["oi_services_h1"]
        + inp["oi_cloud_h1"]
        + inp["oi_corp_h1"]
        + inp["oi_other_bets_h1"]
    ) * 2
    consensus_gap = ebit_runrate / inp["ebit_fy26e_consensus"] - 1.0
    if abs(consensus_gap) > MAX_CONSENSUS_GAP:
        errors.append(
            f"run-rate EBIT {ebit_runrate:.0f} deviates {consensus_gap:+.1%} "
            f"from FY26E consensus (>{MAX_CONSENSUS_GAP:.0%})"
        )
    capex_lag = inp["capex_h1"] / inp["dep_h1"]

    # The roll retains only b1 = g/ROE; the capex wave retains far more, so the
    # true FY2027 opening capital is larger and these multiples too high (A23).
    def band_at(g_svc: float, g_cld: float, ic_scale: float = 1.0, roic_marg: float | None = None,
                r_lab_: float | None = None) -> tuple[float, float, float, dict[str, dict[str, float]]]:
        t_ = tier_multiples(g_svc, g_cld, ic_scale, roic_marg, r_lab_)
        return anchor_from(t_, "l"), anchor_from(t_, "m"), anchor_from(t_, "h"), t_

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        f"run-rate OI($B) services={nopat_services / keep / BN:.1f}"
        f" cloud={nopat_cloud / keep / BN:.1f}"
        f" corp={nopat_corp / keep / BN:.1f}"
        f" | total incl OtherBets={ebit_runrate / BN:.1f}"
        f" vs FY26E consensus {inp['ebit_fy26e_consensus'] / BN:.1f} ({consensus_gap:+.1%})"
    )
    print(
        f"trailing core EPS={core_eps:.2f} (guardrail denominator only)"
        f"  price/core={inp['price'] / core_eps:.2f}x"
        f"  net_cash/sh={net_cash / inp['shares_diluted']:.2f}"
        f"  portfolio/sh(gross)={portfolio_gross / inp['shares_diluted']:.2f}"
        f"  waymo/sh(gross)={waymo_gross / inp['shares_diluted']:.2f}"
    )
    print(
        f"depreciation lag: capex_h1/dep_h1={capex_lag:.1f}x"
        f" — the FORWARD numerator is assumed to already carry the 2026-27 capex"
        f" wave's D&A (A5 falsifier: FY27E EPS cut >10% on unchanged capex guidance)"
    )
    ret_actual = 1.0 - inp["payout_3y"]
    print(
        f"invested capital IC0($B, 2026-06-30): services+corp={inp['equity_services'] / BN:.1f}"
        f" cloud={inp['equity_cloud'] / BN:.1f}"
        f" | ROE basis (A25) = FY2027E leg NOPAT / FY2027 opening IC = IC0 rolled over unbooked 2H26"
        f" (svc {unbooked_svc / BN:.1f}B, cld {unbooked_cld / BN:.1f}B) at b1 = g/ROE"
        f" | on IC0 (old basis): svc {svc_leg / inp['equity_services']:.1%} cld {nopat_cloud / inp['equity_cloud']:.1%}"
    )
    print(
        f"one g per leg: g2_svc={inp['g2_svc']:.1%} g2_cld={inp['g2_cld']:.1%}; multiples differ by tier only through ROE"
        f"  (lambda M {pe_cld['m'] / pe_svc['m']:.3f}; L cloud also carries A18 margin retreat x{cloud_retreat:.4f})"
    )
    print("  tier  k_eps   numerator EPS   ROE svc/cld(snapshot)  cld ret@   svc PE   cld PE  lab PE   b1 svc/cld    payout svc/cld")
    tier_rows = (("l", "k_eps_l", cloud_retreat), ("m", "k_eps_m", 1.0), ("h", "k_eps_h", 1.0))
    for tier, k_field, scale in tier_rows:
        k = inp[k_field]
        num_eps = (svc_leg * k + nopat_cloud * scale * k) / inp["shares_diluted"]
        print(
            f"    {tier.upper()}  {k:.5f} {num_eps:14.2f}   {roe_svc[tier]:6.1%}/{roe_cld[tier]:6.1%}"
            f"   {ret_cld[tier]:6.1%} {pe_svc[tier]:8.2f} {pe_cld[tier]:8.2f} {pe_lab[tier]:6.2f}   {b1_svc[tier]:.3f}/{b1_cld[tier]:.3f}"
            f"   {payout(inp['g2_svc'], roe_svc[tier]):+.1%} / {payout(inp['g2_cld'], ret_cld[tier]):+.1%}"
        )
    print(
        "模型视同派出、实际留存的现金 ($/sh, B bucket, disclosure only; cash dividends only, buybacks = retained-cash use):  "
        + "  ".join(
            f"{t.upper()} {((ret_actual - b1_svc[t]) * unbooked_svc + (ret_actual - b1_cld[t]) * unbooked_cld) / inp['shares_diluted']:.2f}"
            for t in "lmh"
        )
        + f"   [(1 - payout_3y {inp['payout_3y']:.2f} - b1) x unbooked 2H26 per leg]"
    )
    print(
        f"numerator ladder = FY2027E consensus range {inp['eps_fy27e_low']}"
        f" / {inp['eps_fy27e_consensus']} / {inp['eps_fy27e_high']} (A2e-2a):"
        f" ratio L/M {inp['k_eps_l'] / inp['k_eps_m']:.3f} H/M"
        f" {inp['k_eps_h'] / inp['k_eps_m']:.3f}  |  svc multiple ratio"
        f" {pe_svc['l'] / pe_svc['m']:.3f} / {pe_svc['h'] / pe_svc['m']:.3f} (ROE-mechanical, one g)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print("  leg $/sh   services(PE)      cloud-non(PE)  lab(PE)   net_cash   portfolio(d)     waymo(d)     total")
    for tier, k_field, scale, dp_field, do_field in (
        ("L", "k_eps_l", cloud_retreat, "d_port_l", "d_ob_l"),
        ("M", "k_eps_m", 1.0, "d_port_m", "d_ob_m"),
        ("H", "k_eps_h", 1.0, "d_port_h", "d_ob_h"),
    ):
        t = tier.lower()
        lg = legs(inp[k_field], pe_cld[t], inp[dp_field], inp[do_field], scale, pe_svc[t], pe_lab[t])
        print(
            f"    {tier}   {lg['svc']:7.2f}({pe_svc[t]:5.2f}x)"
            f" {lg['cld']:7.2f}({pe_cld[t]:5.2f}x)"
            f" {lg['lab']:6.2f}({pe_lab[t]:4.2f}x)"
            f" {lg['cash']:9.2f}"
            f" {lg['port']:9.2f}(-{inp[dp_field]:.0%})"
            f" {lg['ob']:9.2f}(-{inp[do_field]:.0%})"
            f" {sum(lg.values()):9.2f}"
        )
    print(
        f"guardrail (AGENTS.md:74): H/core_eps={H / core_eps:.2f}x vs own measured top"
        f" {inp['pe_own_top']:.2f}x (p50 {inp['pe_own_p50']:.2f}x) —"
        f" {'OK' if H / core_eps <= inp['pe_own_top'] else '越出自身实测带'}"
    )
    print(
        f"implied PE on trailing core EPS: L={L / core_eps:.1f}x M={M / core_eps:.1f}x"
        f" H={H / core_eps:.1f}x | on FY27E consensus EPS {inp['eps_fy27e_consensus']}:"
        f" L={L / inp['eps_fy27e_consensus']:.1f}x M={M / inp['eps_fy27e_consensus']:.1f}x"
        f" H={H / inp['eps_fy27e_consensus']:.1f}x"
    )
    print(
        f"cloud L retreat: OI margin {inp['cloud_om_l']:.1%} (realised, a year ago)"
        f" vs {inp['cloud_om_now']:.1%} now -> x{cloud_retreat:.4f}"
        f" -> L-tier cloud retention ROIC {inp['roic_marg_cld']:.1%} -> {ret_cld['l']:.1%}"
        f" -> PE {pe_cld['m']:.2f}x -> {pe_cld['l']:.2f}x (A26: marginal ROIC, snapshot ROE {roe_cld['l']:.1%} only printed)"
    )
    print(
        f"cloud lab sub-leg (A27): share {share_lab:.0%} of the cloud numerator, basket pair "
        f"{inp['r_cld_lab']:.0%}->{r_lab:.0%} x (1 - k_lab {k_lab:g}) -> PE {pe_lab['m']:.2f}x vs 篮 4 {pe_cld['m']:.2f}x"
    )
    for label, kw in (
        ("cloud marginal ROIC 13%", dict(roic_marg=0.13)),
        ("cloud marginal ROIC 20%", dict(roic_marg=0.20)),
    ):
        sL, sM, sH, _ = band_at(inp["g2_svc"], inp["g2_cld"], **kw)
        sz = zone_of(inp["price"], sL, sM, sH)
        print(f"敏感区 {label}: L/M/H {sL:.2f}/{sM:.2f}/{sH:.2f} zone={sz}" + ("  ⚠ zone flips" if sz != zone else ""))
    for label, k_alt, r_alt in (("k_lab = 0 (no arrival haircut)", 0.0, None),
                                ("single-basket lab (篮 7 15%, no k — the pre-pair ruler)", 0.0, inp["r_cld_lab"])):
        k_saved, k_lab = k_lab, k_alt
        sL, sM, sH, _ = band_at(inp["g2_svc"], inp["g2_cld"], r_lab_=r_alt)
        k_lab = k_saved
        sz = zone_of(inp["price"], sL, sM, sH)
        print(f"敏感区 {label}: L/M/H {sL:.2f}/{sM:.2f}/{sH:.2f} zone={sz}" + ("  ⚠ zone flips" if sz != zone else ""))
    for sl in (0.15, 0.50):
        share_lab_saved = share_lab
        share_lab = sl
        sL, sM, sH = anchor_from(tm, "l"), anchor_from(tm, "m"), anchor_from(tm, "h")
        share_lab = share_lab_saved
        sz = zone_of(inp["price"], sL, sM, sH)
        print(f"敏感区 lab share {sl:.0%}: L/M/H {sL:.2f}/{sM:.2f}/{sH:.2f} zone={sz}" + ("  ⚠ zone flips" if sz != zone else ""))
    print(
        f"flat-multiple ladder (A2e-2c, every tier at the M multiples):"
        f" {flat_l:.2f}/{M:.2f}/{flat_h:.2f}  width {(flat_h - flat_l) / M:.1%}"
    )
    num_l, num_h = inp["k_eps_l"] / inp["k_eps_m"], inp["k_eps_h"] / inp["k_eps_m"]
    mult_l, mult_h = pe_svc["l"] / pe_svc["m"], pe_svc["h"] / pe_svc["m"]
    print(
        f"tier decomposition (A2e-5):  L/M {L / M:.3f} = numerator {num_l:.3f}"
        f" x svc multiple {mult_l:.3f} x rest {(L / M) / num_l / mult_l:.3f}"
        f"  |  H/M {H / M:.3f} = numerator {num_h:.3f}"
        f" x svc multiple {mult_h:.3f} x rest {(H / M) / num_h / mult_h:.3f}"
        f"   (rest = cloud ROE/A18 retreat + asset discounts)"
    )
    for scale in EQUITY_SENSITIVITY:
        sL, sM, sH, t_ = band_at(inp["g2_svc"], inp["g2_cld"], scale)
        print(
            f"equity sensitivity (待补 FY2027 capital path, A23): opening IC0"
            f" x{scale:.1f} -> M-tier svc {t_['pe_svc']['m']:.2f}x cld {t_['pe_cld']['m']:.2f}x (L cloud {t_['pe_cld']['l']:.2f}x)"
            f" -> L={sL:.2f} M={sM:.2f} H={sH:.2f} ({sM / M - 1:+.1%} on M)"
        )
    _lo, _hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(
        f"capex axis (constituent, A19): 2026 guide"
        f" ${inp['capex_guide_low'] / 1e9:.0f}-{inp['capex_guide_high'] / 1e9:.0f}B"
        f" = {_lo:.1%}-{_hi:.1%} of the axis 2026 base"
    )
    # 敏感区 (valuation-rules「g₂ 的杠杆 MUST 显式」): the band with g2_svc shifted
    # down, disclosed not asserted -- a zone flip is a warning line for the digest.
    # +1pp would breach g_cap(r) and is not a legal state, so only the downside.
    for delta in (-0.01, -0.005):
        sL, sM, sH, t_ = band_at(inp["g2_svc"] + delta, inp["g2_cld"])
        sz = zone_of(inp["price"], sL, sM, sH)
        print(
            f"敏感区 g2_svc {delta:+.1%} -> svc M {t_['pe_svc']['m']:.2f}x -> L={sL:.2f} M={sM:.2f} H={sH:.2f}"
            f" zone={sz}" + ("  ⚠敏感区 (zone flips, disclosure only)" if sz != zone else "")
        )
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # every priced r 1:1 — r_perp and the lab sub-leg's terminal basket — while
    # g, ROE and the numerator stay put.  Disclosure only: the anchors above are
    # the 中枢 column, and g_cap is keyed to the basket r, not re-checked per column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r, r_lab
        saved = r, r_lab
        r, r_lab = r + dr, r_lab + dr
        try:
            return band_at(inp["g2_svc"], inp["g2_cld"])[:3]
        finally:
            r, r_lab = saved

    rf = rf_block(LISTING_CCY, {"r_perp": r, "r_cld_lab_t": r_lab}, band_rf, inp["price"])
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # The daily digest cannot re-price a model, so the two reading bands go to
    # output/rates/ for it; only a clean run writes, so a FAIL never feeds it.
    # Implied r(P), single-stage approximation g + (r - g) * M / P on the services
    # leg's g (the structural read is the market-implied g_svc in §3 交叉校验).
    implied_r = inp["g2_svc"] + (r - inp["g2_svc"]) * M / inp["price"]
    print(
        f"implied r(P) ≈ {implied_r:.1%} (single-stage approx) vs basket r {r:.1%}"
        f" ({implied_r - r:+.1%}, disclosure only)"
    )
    # V_opt: parallel to the band, never inside it.  Reported so the region
    # above H stops being unbounded — it splits into "paying for a named
    # option" and "beyond every option we can name".
    v_opt = inp["v_opt"]
    if v_opt != 0:
        errors.append(f"v_opt must be 0 — A17 has no consensus-referenced anchor (A28); got {v_opt}")
    if v_opt > OPTION_DOMINANT_SHARE * M:
        print(
            f"NOTE: V_opt/M = {v_opt / M:.0%} > {OPTION_DOMINANT_SHARE:.0%} — 期权主导型，"
            f"§0 MUST 标明并指向升级门槛（A2e-7e）；占比本身不是错误"
        )
    # Reported as a delta on H, not as an absolute per-share number: every other
    # comparability read in this repo is a ratio (L/M, H/M, (H-L)/2M), and an
    # absolute figure cannot be compared across tickers.  The *input* stays
    # absolute because the anchor is absolute (a realised trajectory); pinning
    # the delta instead would let the implied absolute drift off that anchor as
    # H moves.
    # Reported in absolute price, because that is what a reader compares against
    # the quote.  The ratios are for scripts/calibration.py, so they ride along
    # in parentheses rather than taking the headline.
    if v_opt > 0:
        print(f"V_opt = +{v_opt:.2f}/sh on H {H:.2f} -> {H + v_opt:.2f} ({v_opt / M:.1%} of M)")
    else:
        print("V_opt = 0 (A28): no consensus-referenced option anchor; the region above H is narrative, not option")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    write_rf_readings("GOOG.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
