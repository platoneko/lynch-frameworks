#!/usr/bin/env python3
"""AVGO.US valuation eval — recompute anchors from frameworks/AVGO.US.md.

formula_id: avgo_sotp_xpu2tier_net_nonai_sw_fy27_gordon_v4

Five legs on FY27 numerators (XPU-underwritten / XPU-lab / AI networking /
non-AI semi / software).  The tier ladder lives in the numerator: the two
CoWoS-constrained legs (XPU, networking) scale with the shared quota axis
(_AXIS.cowos-capacity.md), L <- γ, M <- β, H <- α -- the mirror image of NVDA.
Multiples are generated, not borrowed: each leg names a perpetual g2 (peer
cross-section reverse-solve, capped at g_cap(r)), tier ROE = EPS_x / the FY27
OPENING book per share (FY26Q3 equity rolled over Q4 FY26 unbooked earnings at
the growth-required retention b1 = g/ROE, E_{n+1}/B_n, A24), and the two AI legs run ONE named transition year (FY28 sell-side
consensus EPS growth) through `two_stage_pe` in M/H only.  L is the digest
world -- FY28 gets no credit -- so it calls `perpetual_pe` directly.  r comes
from the basket each leg is assigned to (valuation-rules「§r 篮子」): the four
operating legs sit in 篮 4 龙头制造 (`r_perp`), the lab tier of XPU -- revenue
conditional on XPV financing closing and RVG contingent liabilities -- in 篮 7
单押 / 故事 (`r_lab`).  The Inputs source cell names the basket; `check_r`
demands the value match it.

Numerator year (valuation-rules 裁决顺序 ②, A21): FY27 is the furthest year with a
>=2-house consensus *range* (47 houses); FY28 is visible to three houses but only
as point estimates, so it is the g1 layer, not the numerator.  Guardrail (③,
A19): every blended tier multiple must sit inside the ticker's own realised
next-FY PE band (`pe_own_min/max`); the band-edge Δg printed below is the
uniform shift of all four legs' g2 that would take the M-tier blended multiple
to either edge -- evidence of what the market has paid for, not an input.
The AI legs' M/H two-stage multiple is on the FY27 numerator with FY27 = t=1
(same valuation date as L's `perpetual_pe`, valuation-rules「两段式过渡 · 估值时点」
2026-09-14): divided by (1 + g1) it is the multiple on FY28 (= steady-state
Gordon discounted one year) and must read below the steady-state cap
perpetual_pe(g2).  The AI legs' g2 shifted ±1pp is a disclosure (敏感区,
valuation-rules「g₂ 的杠杆 MUST 显式」): a zone flip is printed, not an error.
Implied r(P) -- one δ added to every leg's basket r until the M-tier sum meets
the price -- is printed for the same reason.

Run:  python3 eval/AVGO.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_cowos_mount, check_lab_mount, check_optical_oe_mount  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_basket_pair,
    check_g_cap,
    check_k_declared,
    check_r,
    check_transition_years,
    g_cap,
    implied_g,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "AVGO.US.md"
FORMULA_ID = "avgo_sotp_xpu2tier_net_nonai_sw_fy27_gordon_v4"
LISTING_CCY = "USD"
TOL = 0.15
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
BRIDGE_TOL = 0.15  # A8: guidance bridge vs consensus

REQUIRED = [
    "price",
    "shares",
    "equity",
    "tax_rate",
    "below_line_ps",
    "rev_ai_27",
    "rev_ai_28",
    "xpu_share_ai",
    "rev_nonai_27",
    "rev_nonai_28",
    "rev_sw_27",
    "rev_sw_28",
    "om_xpu",
    "om_net",
    "om_nonai",
    "om_sw",
    "xpu_uw_share",
    "eps_fy27_cons",
    "eps_fy28_cons",
    "n_stage",
    "n_consensus",
    "r_perp",
    "r_lab",
    "r_lab_t",
    "k_lab",
    "g2_xpu",
    "g2_net",
    "g2_nonai",
    "g2_sw",
    "g2_cand",
    "pe_own_min",
    "pe_own_max",
    "cowos_quota_l",
    "cowos_quota_m",
    "cowos_quota_h",
    "oe_l",
    "oe_m",
    "oe_h",
    "eps_fy26_cons",
    "eps_9m_fy26",
    "payout_3y",
]
TIERS = ("L", "M", "H")
LEGS = ("uw", "lab", "net", "nonai", "sw")
# Which g2 / r each leg reads.  uw and lab are the same business (XPU) split by
# customer quality, so they share g2 and differ only in the r tier.
LEG_G2 = {"uw": "g2_xpu", "lab": "g2_xpu", "net": "g2_net", "nonai": "g2_nonai", "sw": "g2_sw"}
LEG_R = {"uw": "r_perp", "lab": "r_lab", "net": "r_perp", "nonai": "r_perp", "sw": "r_perp"}
# Terminal rate per leg (valuation-rules「篮子对」): only the lab leg fades -- its
# 篮 7 is "the customer pays from funding rounds", a state that ends if the lab
# makes it; the other legs' single basket is already their steady state.
LEG_RT = {**LEG_R, "lab": "r_lab_t"}
TRANSITION_LEGS = ("uw", "lab", "net")  # FY28 consensus growth is an AI story (A4/A5 flat)


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\?\)?\s*=\s*\*\*([0-9.]+)\*\*", md.split("### Outputs", 1)[-1])
    return float(m.group(1)) if m else None


def eps_leg(rev: float, om: float, tax_rate: float, shares: float) -> float:
    return rev * om * (1.0 - tax_rate) / shares


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    # Each r row must name its basket and carry that basket's value (A23).
    for key in ("r_perp", "r_lab", "r_lab_t"):
        if key not in baskets:
            errs.append(f"{key}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
        errs += check_r(inp[key], key, baskets.get(key))
    # g2 is capped by the r of every leg that reads it; the lab leg reads g2_xpu at r_lab.
    for key in ("g2_xpu", "g2_net", "g2_nonai", "g2_sw", "g2_cand"):
        errs += check_g_cap(inp[key], inp["r_perp"], key)
        gap = inp["r_perp"] - inp[key]
        if gap <= 0:
            errs.append(f"perpetuity diverges on {key}: g2 >= r")
        elif gap < MIN_R_MINUS_G:
            errs.append(f"r - {key} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    # Lab leg = basket pair; its arrival haircut is the shared axis value (A23b).
    errs += check_basket_pair(inp["r_lab"], inp["r_lab_t"], "lab",
                              baskets.get("r_lab"), baskets.get("r_lab_t"))
    errs += check_k_declared(inp["r_lab"], inp["r_lab_t"], (inp["k_lab"],) * 3, "k_lab")
    errs += [f"axis: {e}" for e in check_lab_mount(inp["k_lab"])]
    # G_cap stays keyed to the JOURNEY basket (「篮子对」判据 3).
    errs += check_g_cap(inp["g2_xpu"], inp["r_lab"], "g2_xpu@r_lab")
    errs += check_g_cap(inp["g2_cand"], inp["r_lab"], "g2_cand@r_lab")
    # Only FY28 carries a >=2-house consensus (A8); FY29 is a story.
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if inp["eps_fy28_cons"] <= inp["eps_fy27_cons"]:
        errs.append("FY28 consensus below FY27: the transition year has no growth to name")
    # Quota states must be ordered the AVGO way (γ < β < α); the axis check confirms the values.
    errs += ladder("cowos quota (γ<β<α)", inp["cowos_quota_l"], inp["cowos_quota_m"], inp["cowos_quota_h"])
    p_fields = [k for k in inp if k == "p" or k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
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

    s, t, bl = inp["shares"], inp["tax_rate"], inp["below_line_ps"]
    xpu_s, uw = inp["xpu_share_ai"], inp["xpu_uw_share"]
    r, n = inp["r_perp"], int(inp["n_stage"])

    # ---- Step 1: FY27 gross leg EPS on the β (nominal guidance) world ----
    rev_xpu_27 = inp["rev_ai_27"] * xpu_s
    rev_net_27 = inp["rev_ai_27"] * (1.0 - xpu_s)
    gross_m = {
        "xpu": eps_leg(rev_xpu_27, inp["om_xpu"], t, s),
        "net": eps_leg(rev_net_27, inp["om_net"], t, s),
        "nonai": eps_leg(inp["rev_nonai_27"], inp["om_nonai"], t, s),
        "sw": eps_leg(inp["rev_sw_27"], inp["om_sw"], t, s),
    }

    # ---- Step 2: tier numerators from the shared quota axis (A16) ----
    # Only the CoWoS-constrained legs scale; software and non-AI are off-axis.
    # Below-the-line drag (A14) is spread pro-rata so leg sums = gross - bl.
    quota_scale = {
        "L": inp["cowos_quota_l"] / inp["cowos_quota_m"],
        "M": 1.0,
        "H": inp["cowos_quota_h"] / inp["cowos_quota_m"],
    }

    def tier_legs(scale: float) -> dict[str, float]:
        gross = dict(gross_m)
        gross["xpu"] *= scale
        gross["net"] *= scale
        f = (sum(gross.values()) - bl) / sum(gross.values())
        net = {k: v * f for k, v in gross.items()}
        # XPU two-tier split (A15): underwritten LTA vs lab-dependent, every tier.
        return {
            "uw": net["xpu"] * uw,
            "lab": net["xpu"] * (1.0 - uw),
            "net": net["net"],
            "nonai": net["nonai"],
            "sw": net["sw"],
        }

    eps = {tier: tier_legs(quota_scale[tier]) for tier in TIERS}
    eps_total = {tier: sum(eps[tier].values()) for tier in TIERS}
    errors += ladder("numerator (γ/β/α)", eps_total["L"], eps_total["M"], eps_total["H"])

    # ---- Step 3: the FY28 transition year, consensus-to-consensus, carried by the AI legs only ----
    g1_co = inp["eps_fy28_cons"] / inp["eps_fy27_cons"] - 1.0
    ai_m = eps["M"]["uw"] + eps["M"]["lab"] + eps["M"]["net"]
    flat_m = eps["M"]["nonai"] + eps["M"]["sw"]
    g1_ai = ((1.0 + g1_co) * eps_total["M"] - flat_m) / ai_m - 1.0

    # ---- Step 4: tier ROE on the FY27 OPENING book; company ROE for every leg (A3 SOTP rule) ----
    # ROE = E_{n+1} / B_n: FY27 EPS over the FY27 opening book (= end-FY26), not
    # today's FY26Q3 book (valuation-rules 裁决表 ② as of 62c72a2, 2026-09-21; A24).
    # The FY26Q3 book is rolled over the Q4 FY26 earnings not yet booked (FY26
    # consensus minus 9M actual, non-GAAP) at the GROWTH-REQUIRED retention
    # b1 = g/ROE -- the same b two_stage_pe charges in stage 1 -- not at the
    # actual payout complement.  M/H roll at the COMPANY g1 (the legs' g sum to
    # it); L has no window and rolls at its EPS-weighted leg g2.  Closed form:
    # BPS = BPS0 / (1 - g·N/eps).  Actual retention beyond b1 is the B bucket,
    # printed as a disclosure, not put into the book.
    unbooked = inp["eps_fy26_cons"] - inp["eps_9m_fy26"]  # per share, Q4 FY26 only
    bps_q3 = inp["equity"] / s
    g2_l = sum(eps["L"][leg] * inp[LEG_G2[leg]] for leg in LEGS) / eps_total["L"]
    g_roll = {"L": g2_l, "M": g1_co, "H": g1_co}
    bps_open = {tier: bps_q3 / (1.0 - g_roll[tier] * unbooked / eps_total[tier]) for tier in TIERS}
    roe = {tier: eps_total[tier] / bps_open[tier] for tier in TIERS}
    b1 = {tier: g_roll[tier] / roe[tier] for tier in TIERS}
    for tier in TIERS:
        if not (0.0 < b1[tier] < 1.0):
            errors.append(f"{tier} growth-required retention b1 = {b1[tier]:.3f} outside (0,1)")
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {tier: (ret_actual - b1[tier]) * unbooked for tier in TIERS}  # disclosure only

    # ---- Step 5: multiples per leg per tier; L runs no transition (digest world) ----
    # The lab leg is a basket PAIR (valuation-rules「篮子对」, _AXIS.frontier-lab-funding
    # §3): 篮 7 discounts the journey, 篮 4 capitalises the steady state -- a lab that
    # made it pays from its own revenue, like any hyperscaler.  With no transition
    # (L, and the no-transition cross-checks) the terminal rate is the only rate.
    # Every re-pricing below goes through this one function so the pair cannot
    # drift between the anchors and their sensitivities.
    def pe_at(leg: str, tier: str, g2: float, transition: bool, dr: float = 0.0) -> float:
        r_j, r_t = inp[LEG_R[leg]] + dr, inp[LEG_RT[leg]] + dr
        if transition and leg in TRANSITION_LEGS:
            return two_stage_pe(g1_ai, n, g2, roe[tier], r_j, r_terminal=r_t)
        return perpetual_pe(g2, roe[tier], r_t)

    def leg_pe(leg: str, tier: str, transition: bool) -> float:
        return pe_at(leg, tier, inp[LEG_G2[leg]], transition)

    # k_lab leaves the lab leg's value only -- never its multiple, never another
    # leg, whose customers carry their own balance sheets (axis §3b).
    keep = {leg: (1.0 - inp["k_lab"]) if leg == "lab" else 1.0 for leg in LEGS}

    pes = {tier: {leg: leg_pe(leg, tier, transition=(tier != "L")) for leg in LEGS} for tier in TIERS}
    legs_ps = {tier: {leg: eps[tier][leg] * pes[tier][leg] * keep[leg] for leg in LEGS} for tier in TIERS}
    anchors = {tier: sum(legs_ps[tier].values()) for tier in TIERS}
    blended = {tier: anchors[tier] / eps_total[tier] for tier in TIERS}
    L, M, H = (anchors[tier] for tier in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    # Guardrail (裁决顺序 ③, A19): every blended tier multiple inside the ticker's own
    # realised next-FY PE band.
    for tier in TIERS:
        if not (inp["pe_own_min"] <= blended[tier] <= inp["pe_own_max"]):
            errors.append(
                f"{tier} blended PE {blended[tier]:.1f}x outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
            )

    # Re-price one tier with a g2 shift on a subset of legs (same construction as above).
    def anchor_at(tier: str, delta: float, shifted: tuple[str, ...]) -> float:
        return sum(
            eps[tier][leg] * keep[leg]
            * pe_at(leg, tier, inp[LEG_G2[leg]] + (delta if leg in shifted else 0.0), tier != "L")
            for leg in LEGS
        )

    # Band-edge Δg (③ 带即证据): shift every leg's g2 by the same Δ until the M-tier
    # blended multiple reaches each edge of the own band.  Reported, never used.
    def blended_at(tier: str, delta: float) -> float:
        return anchor_at(tier, delta, LEGS) / eps_total[tier]

    def delta_to(target: float, tier: str) -> float:
        lo, hi = -0.20, r - max(inp[k] for k in ("g2_xpu", "g2_net", "g2_nonai", "g2_sw")) - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if blended_at(tier, mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_dg = (delta_to(inp["pe_own_min"], "M"), delta_to(inp["pe_own_max"], "M"))

    # ---- Step 6: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat = flat_multiple_ladder((eps_total["L"], eps_total["M"], eps_total["H"]), blended["M"])
    errors += flat_errs
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (blended["L"], blended["M"], blended["H"]))
    # Same split on the FY28 basis: L's digest world holds FY28 = FY27, M/H carry the AI
    # legs' g1.  On this basis the L gap is a numerator statement and the multiples sit
    # flat -- the FY27-basis "L gap is mostly multiple" is that same statement projected
    # onto the numerator year, not a multiple policy (A2e-2d does not fire).
    eps28 = {
        tier: sum(eps[tier][leg] * ((1.0 + g1_ai) if tier != "L" and leg in TRANSITION_LEGS else 1.0) for leg in LEGS)
        for tier in TIERS
    }
    dec28 = decompose((L, M, H), tuple(anchors[tier] / eps28[tier] for tier in TIERS))

    # ---- Step 7: A8 bridge guard — guidance bridge vs consensus, both years ----
    dev27 = eps_total["M"] / inp["eps_fy27_cons"] - 1.0
    eps28_guide = (
        eps_leg(inp["rev_ai_28"] * xpu_s, inp["om_xpu"], t, s)
        + eps_leg(inp["rev_ai_28"] * (1.0 - xpu_s), inp["om_net"], t, s)
        + eps_leg(inp["rev_nonai_28"], inp["om_nonai"], t, s)
        + eps_leg(inp["rev_sw_28"], inp["om_sw"], t, s)
        - bl
    )
    dev28 = eps28_guide / inp["eps_fy28_cons"] - 1.0
    if abs(dev27) > BRIDGE_TOL:
        errors.append(f"FY27 bridge deviates {dev27:+.1%} from consensus (> {BRIDGE_TOL:.0%})")
    if abs(dev28) > BRIDGE_TOL:
        errors.append(f"FY28 guidance bridge deviates {dev28:+.1%} from consensus (> {BRIDGE_TOL:.0%})")

    # ---- Step 8: zone, stated values, axis mounts ----
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v) > 1e-9:
        errors.append(f"V_opt must be stated as 0 (lab XPU is a basket-pair leg, not an option), got {said_v}")
    errors += [f"axis: {e}" for e in check_cowos_mount("AVGO", inp["cowos_quota_l"], inp["cowos_quota_m"], inp["cowos_quota_h"])]
    errors += [f"axis: {e}" for e in check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"]))]

    # ---- Step 9: g2 leverage (valuation-rules「g₂ 的杠杆 MUST 显式」), disclosure only ----
    # The AI legs' g2 shifted ±1pp together (lab reads g2_xpu too); +1pp sits above
    # g_cap and is not a legal state.  A zone flip is the 敏感区 line, not BLOCKED.
    lever = []
    for delta in (-0.01, +0.01):
        if inp["g2_xpu"] + delta > g_cap(r) + 1e-9:
            continue
        lmh = tuple(anchor_at(tier, delta, TRANSITION_LEGS) for tier in TIERS)
        lever.append((delta, *lmh, zone_of(inp["price"], *lmh)))
    sensitive = [f"{d:+.0%} -> {z}" for d, *_, z in lever if z != zone]

    # ---- Step 10: implied r(P) — one δ on every leg's basket r so the M-tier sum meets the price ----
    def m_at_r_shift(delta: float) -> float:
        return sum(eps["M"][leg] * keep[leg] * pe_at(leg, "M", inp[LEG_G2[leg]], True, dr=delta)
                   for leg in LEGS)

    lo, hi = -0.03, 0.30  # M falls as r rises; bisect the price crossing
    for _ in range(200):
        mid = (lo + hi) / 2
        if m_at_r_shift(mid) > inp["price"]:
            lo = mid
        else:
            hi = mid
    r_delta = (lo + hi) / 2

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(
        f"g1 company (FY28 cons {inp['eps_fy28_cons']:g} / FY27 cons {inp['eps_fy27_cons']:g} - 1) = {g1_co:.4f}"
        f" -> AI legs g1_ai = {g1_ai:.4f} (n={n}; software / non-AI flat)  r={r:g} / lab {inp['r_lab']:g}"
        f"->{inp['r_lab_t']:g} (basket pair) k_lab {inp['k_lab']:g}"
        f"  g2 xpu/net/nonai/sw = {inp['g2_xpu']:.4f}/{inp['g2_net']:.4f}/{inp['g2_nonai']:.4f}/{inp['g2_sw']:.4f}"
    )
    print(f"tier EPS (FY27, after below-line) L/M/H = {eps_total['L']:.3f}/{eps_total['M']:.3f}/{eps_total['H']:.3f}"
          f"  quota scale {quota_scale['L']:.4f}/1/{quota_scale['H']:.4f}")
    print(
        f"tier ROE L/M/H = {roe['L']:.3f}/{roe['M']:.3f}/{roe['H']:.3f} on the FY27 opening book "
        f"{bps_open['L']:.2f}/{bps_open['M']:.2f}/{bps_open['H']:.2f} USD/sh (FY26Q3 book {bps_q3:.2f} rolled over "
        f"Q4 FY26 unbooked {unbooked:.3f}/sh at b1 = g/ROE = {b1['L']:.3f}/{b1['M']:.3f}/{b1['H']:.3f}, "
        f"g_roll {g_roll['L']:.2%}/{g_roll['M']:.2%}/{g_roll['H']:.2%}); FY26Q3-book basis would read "
        f"{eps_total['L'] * s / inp['equity']:.1%}/{eps_total['M'] * s / inp['equity']:.1%}/{eps_total['H'] * s / inp['equity']:.1%}"
    )
    print(
        f"B bucket (modelled-as-distributed, actually retained): actual retention {ret_actual:.1%} − b1 → "
        f"{excess_cash['L']:.2f}/{excess_cash['M']:.2f}/{excess_cash['H']:.2f} USD/sh over Q4 FY26 "
        f"(disclosure only; not a leg, not in BPS)"
    )
    for tier in TIERS:
        p1 = 1.0 - g1_ai / roe[tier]
        tag = "no transition (digest)" if tier == "L" else ("issuance-funded" if p1 < 0 else "self-funded")
        cells = " / ".join(f"{leg} {legs_ps[tier][leg]:.1f} ({pes[tier][leg]:.1f}x)" for leg in LEGS)
        print(f"{tier}: eps {eps_total[tier]:.3f} x blended {blended[tier]:.2f}x = {anchors[tier]:.1f}  [{cells}]"
              f"  stage-1 payout {p1:+.3f} ({tag})")
    print(f"L={L:.1f} M={M:.1f} H={H:.1f} A={A:.1f} B={B:.1f}")
    print(f"flat-multiple ladder @ M {blended['M']:.2f}x: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    ai_cap_hit = inp["g2_xpu"] + band_edge_dg[1] > g_cap(r) + 1e-9
    print(
        f"own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] band-edge Δg @ M ROE (all legs shifted): "
        f"lower {band_edge_dg[0]:+.4f} / upper {band_edge_dg[1]:+.4f}"
        f"{' (upper edge needs AI g2 above the 6% cap — unreachable under ①)' if ai_cap_hit else ''}"
    )
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | "
        f"H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M 0"
    )
    print(
        f"FY28-basis (L: FY28 = FY27; M/H: AI legs x {1 + g1_ai:.3f}) EPS {eps28['L']:.2f}/{eps28['M']:.2f}/{eps28['H']:.2f}: "
        f"L/M = num {dec28['num_lm']:.3f} x pe {dec28['pe_lm']:.3f} | H/M = num {dec28['num_hm']:.3f} x pe {dec28['pe_hm']:.3f}"
    )
    for tier in ("M", "H"):
        print(
            f"AI legs {tier}: uw/net {pes[tier]['uw']:.1f}x FY27 = {pes[tier]['uw'] / (1 + g1_ai):.1f}x FY28"
            f" (steady-state cap {perpetual_pe(inp['g2_xpu'], roe[tier], r):.1f}x); "
            f"lab {pes[tier]['lab']:.1f}x FY27 = {pes[tier]['lab'] / (1 + g1_ai):.1f}x FY28"
        )
    print(
        "g2 leverage (AI legs ±1pp): "
        + " | ".join(f"{d:+.0%}: {l:.1f}/{m:.1f}/{h:.1f} zone={z}" for d, l, m, h, z in lever)
        + ("  (+1pp above the 6% cap, skipped)" if len(lever) == 1 else "")
        + (f"  ⚠敏感区: {', '.join(sensitive)} (disclosed, not BLOCKED)" if sensitive else "")
    )
    print(
        f"implied r(P): δ = {r_delta:+.4f} on every leg -> operating legs {r + r_delta:.4f} "
        f"(篮 {baskets.get('r_perp')}) / lab {inp['r_lab'] + r_delta:.4f} (篮 {baskets.get('r_lab')}); "
        f"M at δ = {m_at_r_shift(r_delta):.1f} = price — disclosure only"
    )
    l_with_transition = sum(eps["L"][leg] * keep[leg] * leg_pe(leg, "L", transition=True) for leg in LEGS)
    m_no_transition = sum(eps["M"][leg] * keep[leg] * leg_pe(leg, "M", transition=False) for leg in LEGS)
    h_no_transition = sum(eps["H"][leg] * keep[leg] * leg_pe(leg, "H", transition=False) for leg in LEGS)
    print(f"cross-check: L with FY28 transition = {l_with_transition:.1f}; M/H without transition = "
          f"{m_no_transition:.1f}/{h_no_transition:.1f}")
    print(f"A8 bridge: FY27 {eps_total['M']:.3f} vs cons {inp['eps_fy27_cons']:g} ({dev27:+.1%}) | "
          f"FY28 guidance bridge {eps28_guide:.3f} vs cons {inp['eps_fy28_cons']:g} ({dev28:+.1%}) | "
          f"FY28 implied by g1 = {eps_total['M'] * (1 + g1_co):.3f}")
    g_mkt, ok = implied_g(inp["price"] / eps_total["M"], roe["M"], r)
    print(f"market-implied (P / FY27 M-EPS = {inp['price'] / eps_total['M']:.1f}x, no transition): g = {g_mkt:.4f}"
          f" ({'well' if ok else 'ill'}-conditioned) — reference only")
    print(f"axis: quota L/M/H = {inp['cowos_quota_l'] / 1e4:.1f}/{inp['cowos_quota_m'] / 1e4:.1f}/"
          f"{inp['cowos_quota_h'] / 1e4:.1f}万片 (L γ / M β / H α); optical OE mount checked")
    print(f"price={inp['price']:.2f} zone={zone}  P/L={inp['price'] / L - 1:+.1%}  P/M={inp['price'] / M - 1:+.1%}")

    # A22 candidate band: same formula, only AI-leg g2 -> g2_cand (peak-normalized).
    def cand_leg_pe(leg: str, tier: str) -> float:
        g2 = inp["g2_cand"] if leg in TRANSITION_LEGS else inp[LEG_G2[leg]]
        return pe_at(leg, tier, g2, tier != "L")

    cand = tuple(
        sum(eps[tier][leg] * keep[leg] * cand_leg_pe(leg, tier) for leg in LEGS) for tier in TIERS
    )
    if not (cand[0] < cand[1] < cand[2]):
        errors.append(f"candidate band not a ladder: {cand}")
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A22)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")
    print(
        f"候选带（AI g2={inp['g2_cand']:g} 峰值后归一；sw/nonai 不动；不进底牌/zone 判定）: "
        f"L′/M′/H′={cand[0]:.1f}/{cand[1]:.1f}/{cand[2]:.1f}  "
        f"候选 zone={zone_of(inp['price'], *cand)}"
    )

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # every priced r 1:1 through pe_at's dr — r_perp (operating legs), the lab
    # pair's journey r_lab (M/H transition) and terminal r_lab_t; g1/g2, tier
    # ROE, numerators and k_lab stay put.  Base deck only.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        lmh = [
            sum(eps[tier][leg] * keep[leg] * pe_at(leg, tier, inp[LEG_G2[leg]], tier != "L", dr=dr) for leg in LEGS)
            for tier in TIERS
        ]
        return lmh[0], lmh[1], lmh[2]

    rf = rf_block(
        LISTING_CCY,
        {"r_perp": r, "r_lab": inp["r_lab"], "r_lab_t": inp["r_lab_t"]},
        band_rf,
        inp["price"],
    )
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("AVGO.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
