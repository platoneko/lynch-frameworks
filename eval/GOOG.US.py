#!/usr/bin/env python3
"""GOOG.US (Alphabet) valuation eval — recompute anchors from frameworks/GOOG.US.md.

frameworks/GOOG.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: goog_fwd_numerator_gordon_services_cloud_assets_v3

Main ruler: SOTP on a FORWARD numerator — the FY2027E sell-side EPS range
(13.50 / 14.83 / 17.21, 51 estimates) carried onto the three segment legs by
one scalar per tier — priced at a SINGLE, FLAT set of perpetuity multiples.
Every multiple is GENERATED from a named growth rate rather than lifted off a
historical PE percentile (AGENTS.md「永续增长口径」), and each leg carries its
own invested capital, so its ROE — and therefore the retention its growth
costs — is derived, not chosen:

    Services + Alphabet-level   ROE 47.2%   (equity 247.8B, residual)
    Google Cloud                ROE 16.0%   (equity 160.0B, from HSBC 2027E ROIC)

The tier ladder lives ENTIRELY in the numerator: g2_svc = 5.5% and
g2_cld = 6.5% are identical in L, M and H, so the multiple ratio across tiers
is exactly 1.000 and every point of tier spread is a consensus-EPS point
(A2e-2a / A2e-2c). The one derived exception is the L tier's cloud multiple:
A18 retreats that segment's OI margin to a realised 20.7%, which shrinks the
same capital's ROE to 9.3% and therefore its multiple to 8.60x — the SAME
g2_cld, a different ROE. `assert_flat_multiples` fails loudly if any future
edit reintroduces a per-tier growth rate and turns the band back into a
multiple band.

Consequence worth stating: the cloud leg still trades at a LOWER multiple than
the services leg (lambda 0.864). At its own growth an ROE-16% leg is worth less
than an ROE-47% leg, because the same growth costs it roughly three times the
retained capital. The retired lambda = 1.2727 asserted the opposite and could
only be true if cloud grew ~2.2pp faster forever — an assumption that was
hidden inside a multiple rather than named as a rate.

Why GAAP EPS is not used: H1 2026 other income carries $135.9B of unrealized
equity-securities gains (SpaceX and a private company), so trailing EPS - and
every screen PE built on it - is meaningless for this name.

Run:  python3 eval/GOOG.US.py
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
from eval.lib.gordon import R_OPERATING, check_r, payout, perpetual_pe  # noqa: E402
from eval.lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "GOOG.US.md"
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
# Equity is NOT rolled forward with the numerator (see 「equity 未随分子滚动」);
# report the band under a materially larger FY2027 capital base.
EQUITY_SENSITIVITY = (1.20, 1.40)


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
    "equity_services",
    "equity_cloud",
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
# option we can name".  Above this share of M the option has grown too large to
# be left as a ceiling — it has to be modelled as a leg, or the Lynch class is
# wrong (pending the AGENTS.md option-tier clause).
MAX_V_OPT_SHARE = 0.30


def sanity_checks(inp: dict[str, float]) -> list[str]:
    """Ticker-specific guards on the inputs: growth band, numerator ladder, identity."""
    errs: list[str] = []

    # r is a tier, not a dial: both legs here are ordinary operating cash flow,
    # so they sit in the default tier. Moving either to `contracted` needs a
    # signed-contract citation in Assumptions (AGENTS.md「永续增长口径」).
    r = inp["r_perp"]
    errs += check_r(r, "r_perp")
    if abs(r - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={r}: Services/Cloud are operating cash flow, expected {R_OPERATING}")

    # Growth: one rate per leg, shared by every tier. Both must clear the pole.
    for leg in ("svc", "cld"):
        g = inp[f"g2_{leg}"]
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


def assert_flat_multiples(
    pe_svc: dict[str, float], pe_cld: dict[str, float], pe_cld_l_expected: float
) -> list[str]:
    """The tier band MUST be pure numerator: no tier may name its own growth rate.

    Services is flat in all three tiers and cloud is flat in M/H, so both ratios
    are exactly 1.000. The L tier's cloud multiple is the single allowed
    exception and it is DERIVED, not set: same g2_cld, an ROE that A18's margin
    retreat shrank. Anything else means a multiple band crept back in and the
    tiers stopped being three readings of one consensus distribution (A2e-2c).
    """
    errs: list[str] = []
    for tier in ("l", "h"):
        if pe_svc[tier] != pe_svc["m"]:
            errs.append(
                f"services multiple ratio {tier}/m = {pe_svc[tier] / pe_svc['m']:.4f} != 1.000 "
                f"— multiples MUST be flat across tiers (A2e-2c)"
            )
    if pe_cld["h"] != pe_cld["m"]:
        errs.append(
            f"cloud multiple ratio h/m = {pe_cld['h'] / pe_cld['m']:.4f} != 1.000 "
            f"— multiples MUST be flat across tiers (A2e-2c)"
        )
    if pe_cld["l"] != pe_cld_l_expected:
        errs.append(
            "L-tier cloud multiple is not the A18-derived one (same g2_cld, retreated ROE) "
            "— a second growth rate has been introduced"
        )
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

    errors = sanity_checks(inp)

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

    # Step 3 — ONE multiple per leg, shared by every tier. ROE is derived from
    # each leg's invested capital (AGENTS.md:83), so no multiple can move
    # without a capital base or a growth rate moving first.
    r = inp["r_perp"]
    roe_services = svc_leg / inp["equity_services"]
    roe_cloud = nopat_cloud / inp["equity_cloud"]
    # The L tier's margin retreat scales the cloud numerator, so the same
    # capital earns less: the retreat costs ROE too, it is not free.
    roe_cloud_l = roe_cloud * cloud_retreat

    pe_services = perpetual_pe(inp["g2_svc"], roe_services, r)
    pe_cloud = perpetual_pe(inp["g2_cld"], roe_cloud, r)
    pe_cloud_l = perpetual_pe(inp["g2_cld"], roe_cloud_l, r)

    pe_svc = {"l": pe_services, "m": pe_services, "h": pe_services}
    pe_cld = {"l": pe_cloud_l, "m": pe_cloud, "h": pe_cloud}
    errors.extend(assert_flat_multiples(pe_svc, pe_cld, pe_cloud_l))

    # The cloud leg MUST come out cheaper than the services leg. This is the
    # reversal of the retired lambda = 1.2727: even a percentage point of extra
    # growth cannot make an ROE-16% leg out-multiple an ROE-47% leg, because
    # that growth costs it ~3x the retained capital.
    for tier in ("l", "m", "h"):
        lam = pe_cld[tier] / pe_svc[tier]
        if lam >= 1.0:
            errors.append(
                f"tier {tier}: cloud/services multiple {lam:.3f} >= 1 — an ROE "
                f"{roe_cloud:.1%} leg cannot out-multiple an ROE {roe_services:.1%} "
                f"leg; the premium is unnamed"
            )
    # Perpetual state: every leg must fund its own growth out of its own earnings.
    for label, roe_leg, g_leg in (
        ("services", roe_services, inp["g2_svc"]),
        ("cloud", roe_cloud, inp["g2_cld"]),
        ("cloud_L", roe_cloud_l, inp["g2_cld"]),
    ):
        pay = payout(g_leg, roe_leg)
        if not (0.0 < pay <= 1.0):
            errors.append(f"payout {label}={pay:.3f} outside (0, 1]")

    def legs(
        k_eps: float,
        mult_cld: float,
        d_port: float,
        d_ob: float,
        cloud_scale: float = 1.0,
        mult_svc: float = pe_services,
    ) -> dict[str, float]:
        """Per-share contribution of each leg; the anchor is their sum."""
        sh = inp["shares_diluted"]
        return {
            "svc": svc_leg * k_eps * mult_svc / sh,
            "cld": nopat_cloud * cloud_scale * k_eps * mult_cld / sh,
            "cash": net_cash / sh,
            "port": portfolio_gross * (1 - d_port) / sh,
            "ob": waymo_gross * (1 - d_ob) / sh,
        }

    def anchor(
        k_eps: float,
        mult_cld: float,
        d_port: float,
        d_ob: float,
        cloud_scale: float = 1.0,
        mult_svc: float = pe_services,
    ) -> float:
        """Tier value: the FY2027E consensus scalar rides the whole numerator."""
        return sum(legs(k_eps, mult_cld, d_port, d_ob, cloud_scale, mult_svc).values())

    L = anchor(inp["k_eps_l"], pe_cld["l"], inp["d_port_l"], inp["d_ob_l"], cloud_retreat)
    M = anchor(inp["k_eps_m"], pe_cld["m"], inp["d_port_m"], inp["d_ob_m"])
    H = anchor(inp["k_eps_h"], pe_cld["h"], inp["d_port_h"], inp["d_ob_h"])
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

    # A2e-2c: strip the one derived multiple difference too (price L's cloud leg
    # at the M multiple) and the ladder must still stand — proof the tiers are
    # numerator, not multiple.
    flat_l = anchor(
        inp["k_eps_l"], pe_cld["m"], inp["d_port_l"], inp["d_ob_l"], cloud_retreat
    )
    if not (flat_l < M < H):
        print(
            f"FAIL: flat-multiple ladder collapsed: "
            f"{flat_l:.2f}/{M:.2f}/{H:.2f} — tiers have no content "
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

    # ROE uses CURRENT invested capital against a FY2027E numerator, which is
    # directionally optimistic: FY2027 capital will be materially larger, so the
    # true FY2027 ROE is lower and these multiples are too high. Size it.
    def band_at_equity(scale: float) -> tuple[float, float, float, float, float, float]:
        roe_s = svc_leg / (inp["equity_services"] * scale)
        roe_c = nopat_cloud / (inp["equity_cloud"] * scale)
        m_svc = perpetual_pe(inp["g2_svc"], roe_s, r)
        m_cld = perpetual_pe(inp["g2_cld"], roe_c, r)
        m_cld_l = perpetual_pe(inp["g2_cld"], roe_c * cloud_retreat, r)
        return (
            anchor(inp["k_eps_l"], m_cld_l, inp["d_port_l"], inp["d_ob_l"], cloud_retreat, m_svc),
            anchor(inp["k_eps_m"], m_cld, inp["d_port_m"], inp["d_ob_m"], 1.0, m_svc),
            anchor(inp["k_eps_h"], m_cld, inp["d_port_h"], inp["d_ob_h"], 1.0, m_svc),
            m_svc,
            m_cld,
            m_cld_l,
        )

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
    print(
        f"invested capital($B): services+corp={inp['equity_services'] / BN:.1f}"
        f" cloud={inp['equity_cloud'] / BN:.1f}"
        f" | ROE services={roe_services:.1%} cloud={roe_cloud:.1%}"
        f" cloud_L(after margin retreat)={roe_cloud_l:.1%}"
    )
    print(
        f"multiples FLAT across tiers: g2_svc={inp['g2_svc']:.1%} -> {pe_services:.2f}x"
        f"  g2_cld={inp['g2_cld']:.1%} -> {pe_cloud:.2f}x  (lambda {pe_cloud / pe_services:.3f})"
        f"  | L cloud {pe_cloud_l:.2f}x = same g2_cld at A18 ROE {roe_cloud_l:.1%}"
    )
    print("  tier  k_eps   numerator EPS   svc PE   cld PE   payout svc/cld")
    tier_rows = (("l", "k_eps_l", cloud_retreat), ("m", "k_eps_m", 1.0), ("h", "k_eps_h", 1.0))
    for tier, k_field, scale in tier_rows:
        k = inp[k_field]
        num_eps = (svc_leg * k + nopat_cloud * scale * k) / inp["shares_diluted"]
        roe_c_tier = roe_cloud_l if tier == "l" else roe_cloud
        print(
            f"    {tier.upper()}  {k:.5f} {num_eps:14.2f} {pe_svc[tier]:8.2f} {pe_cld[tier]:8.2f}"
            f"   {payout(inp['g2_svc'], roe_services):+.1%} / "
            f"{payout(inp['g2_cld'], roe_c_tier):+.1%}"
        )
    print(
        f"numerator ladder = FY2027E consensus range {inp['eps_fy27e_low']}"
        f" / {inp['eps_fy27e_consensus']} / {inp['eps_fy27e_high']} (A2e-2a):"
        f" ratio L/M {inp['k_eps_l'] / inp['k_eps_m']:.3f} H/M"
        f" {inp['k_eps_h'] / inp['k_eps_m']:.3f}  |  multiple ratio"
        f" {pe_svc['l'] / pe_svc['m']:.3f} / {pe_svc['h'] / pe_svc['m']:.3f} (flat by construction)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print("  leg $/sh   services(PE)      cloud(PE)   net_cash   portfolio(d)     waymo(d)     total")
    for tier, k_field, scale, dp_field, do_field in (
        ("L", "k_eps_l", cloud_retreat, "d_port_l", "d_ob_l"),
        ("M", "k_eps_m", 1.0, "d_port_m", "d_ob_m"),
        ("H", "k_eps_h", 1.0, "d_port_h", "d_ob_h"),
    ):
        t = tier.lower()
        lg = legs(inp[k_field], pe_cld[t], inp[dp_field], inp[do_field], scale)
        print(
            f"    {tier}   {lg['svc']:7.2f}({pe_svc[t]:5.2f}x)"
            f" {lg['cld']:7.2f}({pe_cld[t]:5.2f}x)"
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
        f" -> ROE {roe_cloud:.1%} -> {roe_cloud_l:.1%} -> PE {pe_cloud:.2f}x -> {pe_cloud_l:.2f}x"
    )
    print(
        f"flat-multiple ladder (A2e-2c, L's cloud leg also at the M multiple):"
        f" {flat_l:.2f}/{M:.2f}/{H:.2f}  width {(H - flat_l) / M:.1%}"
    )
    num_l, num_h = inp["k_eps_l"] / inp["k_eps_m"], inp["k_eps_h"] / inp["k_eps_m"]
    print(
        f"tier decomposition (A2e-5):  L/M {L / M:.3f} = numerator {num_l:.3f}"
        f" x multiple 1.000 x rest {(L / M) / num_l:.3f}"
        f"  |  H/M {H / M:.3f} = numerator {num_h:.3f}"
        f" x multiple 1.000 x rest {(H / M) / num_h:.3f}"
        f"   (rest = A18 cloud retreat + asset discounts)"
    )
    for scale in EQUITY_SENSITIVITY:
        sL, sM, sH, m_svc, m_cld, m_cld_l = band_at_equity(scale)
        print(
            f"equity sensitivity (待补 FY2027 capital path): invested capital"
            f" x{scale:.1f} -> svc {m_svc:.2f}x cld {m_cld:.2f}x (L cloud {m_cld_l:.2f}x)"
            f" -> L={sL:.2f} M={sM:.2f} H={sH:.2f} ({sM / M - 1:+.1%} on M)"
        )
    _lo, _hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(
        f"capex axis (constituent, A19): 2026 guide"
        f" ${inp['capex_guide_low'] / 1e9:.0f}-{inp['capex_guide_high'] / 1e9:.0f}B"
        f" = {_lo:.1%}-{_hi:.1%} of the axis 2026 base"
    )
    # V_opt: parallel to the band, never inside it.  Reported so the region
    # above H stops being unbounded — it splits into "paying for a named
    # option" and "beyond every option we can name".
    v_opt = inp["v_opt"]
    if v_opt < 0:
        errors.append(f"v_opt must be >= 0, got {v_opt}")
    if v_opt > MAX_V_OPT_SHARE * M:
        errors.append(
            f"v_opt {v_opt:.2f} exceeds {MAX_V_OPT_SHARE:.0%} of M ({M:.2f}) — an"
            f" option this large must be modelled as a leg, not left as a ceiling"
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
    print(
        f"V_opt = +{v_opt:.2f}/sh on H {H:.2f} -> {H + v_opt:.2f}"
        f"  ({v_opt / H:+.1%} on H, {v_opt / M:.1%} of M, cap {MAX_V_OPT_SHARE:.0%})"
        f"  — reported ALONGSIDE the band; zone edges untouched, `stretched` stays P > {H:.2f}"
    )
    print(
        f"premium over H {H:.2f} vs the +{v_opt:.2f} the named option can carry: "
        + " | ".join(
            f"{lbl} {p:.2f} -> "
            + (
                "inside H"
                if p <= H
                else f"+{p - H:.2f} ({(p - H) / v_opt:.0%} of it)"
                if p <= H + v_opt
                else f"+{p - H:.2f} EXCEEDS it"
            )
            for lbl, p in (("spot", inp["price"]), ("BRK VWAP", 359.69), ("TP mean", 422.34))
        )
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
