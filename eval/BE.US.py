#!/usr/bin/env python3
"""BE.US valuation eval — recompute anchors from frameworks/BE.US.md.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」): which zone a
quote falls in is derived live by the daily digest and the app, so nothing here
reads a price.

formula_id: be_fy2_eps_pe_order_gate_v1_gordon_v3

v3 (2026-10-03, valuation-rules「未建模期权」): V_opt is recomputed here.  Units =
the company's named contracts (Oracle MSA up to 2.8 GW + AEP up to 1 GW) minus
the ~2 GW the FY28 consensus bridge already carries; unit economics = FY28
consensus EPS per GW; valued on this ticker's own ruler (g2, H-tier ROE,
terminal basket, × (1 − k)) at t_opt, discounted to FY27 at the journey basket.

Single earnings ruler on the FY2027 Non-GAAP EPS consensus (28 houses): the
tier ladder lives in the numerator only — L = consensus low, M = mean, H = high,
three points of one distribution (A7).  Multiples are generated, not borrowed:
`two_stage_pe` runs one named transition year (FY28 FactSet aggregate, g1 =
+60.2%, n = 1 — FY29 has no ≥2-house consensus) and then the peer-cluster
reverse-solved perpetual g2 (GEV / VRT / ETN median 7.60%, capped at 6%, A13),
with a BASKET PAIR (valuation-rules「篮子对」, A18): 篮 7 单押 / 故事股 15% prices
the journey — stage-1 cash and the year the tail is discounted back over — while
篮 4 龙头制造 10% capitalises the steady state, because the world in which FY27
consensus lands is a proven power-equipment supplier, not a story stock.  The
split is worth only 4.3% on its own at n=1, so the arrival risk it stops
charging moves to an explicit numerator haircut k (A21), and tier
ROE = EPS_x ÷ the FY27 OPENING book per share (A8/A9/A19): the 2Q26
if-converted book rolled over the 2H26 earnings not yet booked (FY26 consensus
minus 1H26 actual) at the growth-required retention b1 = g1/ROE — the same b
`two_stage_pe` charges in stage 1 (valuation-rules 2026-09-21).  b1 >
1 here is the issuance the framework already prices as a negative stage-1
payout, so it is allowed and printed, not failed.  The L tier carries the
same transition: its world is "delay", not "deterioration" (A14); the
no-transition figure is printed as the deep_discount pressure coordinate, never
as an anchor.

Valuation date (valuation-rules「两段式过渡 · 估值时点」, 2026-09-14): FY27 is
t=1 for all three tiers, `two_stage_pe` and `perpetual_pe` share the date, and
the FY28-basis multiple (PE / (1 + g1)) is printed because 表1 reports the
post-transition numerator.

Guardrail: 裁决顺序 ③ stays inapplicable — the ticker has no own band (FY27's
4.92 has never been earned, so there are no same-earnings months), and step 1
of the ③ flow routes that case to the 纠正对账门 instead.  What the pair changes
is the peer cluster: GEV / VRT / ETN sit in 篮 4, which is now the TERMINAL
basket, so the cluster is same-basket and serves as reconciliation coordinate ⑤
rather than a cross-basket footnote.  M's 27.48x lands inside [26.37, 37.82]
(A8) — the −14.58-turn gap the single-basket ruler showed was the 5pp rate
difference, not a fundamental one.

Steady-return path (A22): forward tier ROE through Y1 2028, linear to rs_steady by
Y2 2032, tail at rs_steady.  rs_steady = 24.1% is the HIGHEST of the three mature
peers' through-cycle readings (Generac; Cummins 23.0%, Eaton 16.1%), not the
median the rule names — a user ruling of 2026-10-18, recorded in A22.

Option (A16): the beyond-consensus GW runway is priced as V_opt with per-tier
p_k; the script recomputes the corrected band and checks the stated V_opt /
p_k / A′ / B′.

g2 leverage must be explicit: the band at g2 − 1pp is printed next to the band
at the cap, L/M/H only (valuation-rules「g₂ 的杠杆 MUST 显式」).  Order-gate fields (cover, concentration) are recomputed / watched but
never enter the anchors.  No probability enters the base deck.

Run:  python3 frameworks/eval/BE.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    check_basket_pair,
    check_g_cap,
    check_k_declared,
    check_r,
    check_transition_years,
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
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "BE.US.md"
FORMULA_ID = "be_fy2_eps_pe_order_gate_v1_gordon_v3"
NUM_YEAR = 2027  # numerator year = t1
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02  # below this the multiple sits at the pole
DERIVED_TOL = 5e-4  # g1 / roe_* rows are derived; Inputs must agree with the recomputation
G2_LEVERAGE_STEP = 0.01  # band disclosed at g2 − 1pp (evidence range collapses onto the cap)

REQUIRED = [
    "shares",
    "equity",
    "eps_fy26_m",
    "eps_1h26_a",
    "payout_3y",
    "eps_fy27_l",
    "eps_fy27_m",
    "eps_fy27_h",
    "eps_fy28_cons",
    "g1",
    "n_g1",
    "g2",
    "r_journey",
    "r_terminal",
    "k_l",
    "k_m",
    "k_h",
    "roe_l",
    "roe_m",
    "roe_h",
    "pe_peer_lo",
    "pe_peer_hi",
    "rpo_product_install",
    "customer_deposits",
    "revenue_next_12m",
    "cover",
    "opt_gw_named",
    "opt_gw_cons",
    "t_opt",
    "tau",
    "parent_share",
    "y1",
    "y2",
    "rs_steady",
    "y1_opt",
    "y2_opt",
]
TIERS = ("L", "M", "H")


def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0, r_terminal: float | None = None) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2.  Basket pair: the n stage-1 years are discounted at
    the journey rate r, everything after at r_terminal (the structure of two_stage_pe).  With
    rs >= roe this equals two_stage_pe(g1, n, g2, roe, r, r_terminal) exactly.
    (gordon.py three-segment helper is [待建].)"""
    r_tv = r if r_terminal is None else r_terminal
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    def df(t: int) -> float:
        return (1 + r) ** (-min(t, n)) * (1 + r_tv) ** (-max(t - n, 0))

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) * df(t)
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / (r_tv - g2) * df(t - 1)
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) * df(t)
        e *= 1 + g2
        t += 1


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(r"p_L/p_M/p_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*", md)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def stated_option_cuts(md: str) -> tuple[float | None, float | None]:
    a = re.search(r"A′ = \*\*([0-9.]+)\*\*", md)
    b = re.search(r"B′ = \*\*([0-9.]+)\*\*", md)
    return (float(a.group(1)) if a else None, float(b.group(1)) if b else None)


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A basket PAIR (valuation-rules「篮子对」, A18): 篮 7 prices the journey to
    # the steady state, 篮 4 prices the steady state itself.  Both rows must name
    # their 篮 N; a missing tag is itself an error.
    for row in ("r_journey", "r_terminal"):
        if row not in baskets:
            errs.append(f"{row}: Inputs source cell names no 篮 N")
    errs += check_basket_pair(
        inp["r_journey"], inp["r_terminal"], "r",
        baskets.get("r_journey"), baskets.get("r_terminal"),
    )
    # A faded terminal MUST carry the arrival risk in the numerator (A21): one
    # transition year is too short an exponent to hold it.
    errs += check_k_declared(
        inp["r_journey"], inp["r_terminal"],
        (inp["k_l"], inp["k_m"], inp["k_h"]), "k",
    )

    # G_cap stays keyed to the JOURNEY basket — fading the terminal must not
    # widen the perpetual g (valuation-rules「篮子对」判据 3).
    errs += check_g_cap(inp["g2"], inp["r_journey"], "g2")
    gap = inp["r_terminal"] - inp["g2"]
    if gap <= 0:
        errs.append("perpetuity diverges: g2 >= r")
    elif gap < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # A2e-2a / 2c: three points of one FY27 distribution, and the transition year
    # must have growth to name above the H numerator.
    errs += ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])
    if inp["eps_fy28_cons"] <= inp["eps_fy27_h"]:
        errs.append("FY28 aggregate below FY27 high: the transition year has no growth to name")
    # Only FY28 carries a consensus (A15); FY29 has none.
    errs += check_transition_years(int(inp["n_g1"]), 1, "n_g1")

    # A2e-7a: probabilities stay out of the base deck.
    p_fields = [k for k in inp if k.startswith("p_")]
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

    r = inp["r_journey"]
    r_t = inp["r_terminal"]
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    n = int(inp["n_g1"])
    g2 = inp["g2"]
    eps = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}

    # ---- Step 1: derived inputs recomputed from their sources (A8 / A15) ----
    g1 = inp["eps_fy28_cons"] / inp["eps_fy27_m"] - 1.0
    if abs(g1 - inp["g1"]) > DERIVED_TOL:
        errors.append(f"g1: stated {inp['g1']:.4f} vs recomputed {g1:.4f}")

    # ROE = E_{n+1} / B_n: FY27 EPS over the FY27 OPENING book (= end-2026), not
    # the 2Q26 book (A19; valuation-rules 2026-09-21).  The 2Q26 if-converted book
    # is rolled over the 2H26 earnings not yet booked (FY26 consensus minus 1H26
    # actual) at the growth-required retention b1 = g1/ROE — all three tiers
    # carry the FY28 window, so all three roll at g1.  ROE and BPS depend on
    # each other; the fixed point is closed-form: BPS = BPS0 / (1 - g1·N/eps).
    # b1 > 1 is the equity issuance the negative stage-1 payout already prices,
    # so it is disclosed, not failed; only a diverging roll (g1·N/eps >= 1) stops.
    bps_2q26 = inp["equity"] / inp["shares"]
    unbooked = inp["eps_fy26_m"] - inp["eps_1h26_a"]  # per share, 2H26 only (opening-FY27 book)

    def opening_bps(eps_x: float) -> float:
        share = g1 * unbooked / eps_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g1·N/eps = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps_2q26 / (1.0 - share)

    bps_open = {t: opening_bps(eps[t]) for t in TIERS}
    roe = {t: eps[t] / bps_open[t] for t in TIERS}
    b1 = {t: g1 / roe[t] for t in TIERS}
    for t, key in zip(TIERS, ("roe_l", "roe_m", "roe_h")):
        if abs(roe[t] - inp[key]) > DERIVED_TOL:
            errors.append(f"{key}: stated {inp[key]:.4f} vs recomputed {roe[t]:.4f}")
    ret_actual = 1.0 - inp["payout_3y"]
    # (actual retention − b1) × N: negative here = the 2H26 issuance the model books (disclosure only)
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in TIERS}

    # ---- Step 2: multiples (g shared across tiers; only ROE varies) and anchors ----
    # Steady-return path (A22): forward ROE through Y1, linear to rs_steady by Y2, tail at rs_steady.
    y1, y2, rs = int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]

    def tier_pes(g2_: float, transition: bool = True) -> dict[str, float]:
        return {
            t: (three_segment_pe(NUM_YEAR, y1, y2, rs, g2_, roe[t], r, g1=g1, n=n, r_terminal=r_t)
                if transition else three_segment_pe(NUM_YEAR, y1, y2, rs, g2_, roe[t], r_t))
            for t in TIERS
        }

    # Timing (A22): the Gordon value sits at t_n = 2027-01-01; discount tau years at the journey
    # basket to the 2026-06-30 balance sheet, plus the 2H26 window's distributable earnings
    # (unbooked x (1 - b1), clipped at 0 — b1 > 1 in every tier, so the window is 0).
    tau = inp["tau"]
    window = {t: max(unbooked * (1.0 - b1[t]), 0.0) * inp["parent_share"] for t in TIERS}

    def value(pes_: dict[str, float], r_: float) -> dict[str, float]:
        return {t: eps[t] * pes_[t] * (1.0 - k[t]) / (1 + r_) ** tau + window[t] / (1 + r_) ** (tau / 2)
                for t in TIERS}

    # k leaves the anchors only — never the multiple, never b (A21; same
    # discipline as the「视同派出」k).  It is flat across tiers here, so the four
    # cross-ticker ratios are identical with and without it.
    pes = tier_pes(g2)
    anchors = value(pes, r)
    L, M, H = (anchors[t] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    # ---- Step 3: peer cluster — same basket as the TERMINAL, so it is
    # reconciliation coordinate ⑤, not a cross-basket footnote (A8/A18) ----
    # The peer FY+1 forward-PE cluster is 篮 4 (GEV / VRT / ETN); a ③ band must
    # share the leg's basket, so the cluster is only printed against the tiers.
    lo, hi = inp["pe_peer_lo"], inp["pe_peer_hi"]
    if not (0 < lo < hi):
        errors.append("pe_peer_lo/hi comparison band malformed")

    # ---- Step 4: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat = flat_multiple_ladder(
        tuple(eps[t] * (1.0 - k[t]) for t in TIERS), pes["M"])
    errors += flat_errs
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (pes["L"], pes["M"], pes["H"]))

    # ---- Step 5: cut points, g2 leverage, order-gate coordinates ----
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)

    # Option (A16): V_opt is a stated input of the framework (its four elements
    # live in A16, not in Inputs); the script checks the corrected band and its
    # cut-points reproduce.
    opt_gw = inp["opt_gw_named"] - inp["opt_gw_cons"]
    opt_eps = opt_gw * inp["eps_fy28_cons"] / inp["opt_gw_cons"]
    # Option high-return window on its own product stage (A16 / A22, user 2026-10-19): the 1.8 GW
    # ships nothing in 2028, so Y1 = its own full-output year t_opt, then the base's entry-barrier
    # fade length (medium, 4 years); steady return, g2 and tau are the base's.
    y1_opt, y2_opt = int(inp["y1_opt"]), int(inp["y2_opt"])
    if y1_opt != int(inp["t_opt"]):
        errors.append(f"y1_opt {y1_opt} != t_opt {int(inp['t_opt'])} (option Y1 = its full-output year, A16)")
    if y2_opt - y1_opt != y2 - y1:
        errors.append(f"option fade {y2_opt - y1_opt}y != base fade {y2 - y1}y (same entry barrier, A22)")
    opt_pe = three_segment_pe(int(inp["t_opt"]), y1_opt, y2_opt, rs, g2, roe["H"], r_t)
    v_opt = opt_eps * opt_pe * (1.0 - k["H"]) / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR) / (1.0 + r) ** tau
    said_v = stated_v_opt(md)
    p_tiers = stated_p_tiers(md)
    if said_v is None or p_tiers is None:
        errors.append("V_opt / p_L/p_M/p_H not found in Outputs (A16 option)")
        p_tiers = (0.0, 0.0, 0.0)
    elif abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt stated {said_v} vs recomputed {v_opt:.2f} (A16)")
    print(f"option (A16): {opt_gw:.1f} GW named beyond consensus x EPS {inp['eps_fy28_cons'] / inp['opt_gw_cons']:.3f}/GW "
          f"= {opt_eps:.3f} x PE {opt_pe:.2f} (g2 {g2:.0%}, ROE_H {roe['H']:.1%}, r_t {r_t:.0%}) x (1-k) "
          f"/ {1 + r:.2f}^{inp['t_opt'] - NUM_YEAR:.0f} = {v_opt:.2f}")
    band_v = tuple(a + p * v_opt for a, p in zip((L, M, H), p_tiers))
    A_v, B_v = cut_points(*band_v)
    said_a_v, said_b_v = stated_option_cuts(md)
    for name, said, got in (("A′", said_a_v, A_v), ("B′", said_b_v, B_v)):
        if said is None or abs(said - got) > TOL:
            errors.append(f"{name}: stated {said} vs recomputed {got:.4f}")

    # g2 leverage: every peer reverse-solves above the cap, so the evidence range
    # collapses onto it; the band one step below is disclosed (A13).
    pes_dn = tier_pes(g2 - G2_LEVERAGE_STEP)
    v_dn = value(pes_dn, r)
    band_dn = tuple(v_dn[t] for t in TIERS)

    cover = (inp["rpo_product_install"] + inp["customer_deposits"]) / inp["revenue_next_12m"]
    if abs(cover - inp["cover"]) > 0.01:
        errors.append(f"cover: stated {inp['cover']} vs recomputed {cover:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"g1(FY28 aggregate / FY27 mean - 1)={g1:.4f} n={n} g2={g2:.4f} "
          f"r_journey={r:g} (篮 {baskets.get('r_journey')}) -> r_terminal={r_t:g} "
          f"(篮 {baskets.get('r_terminal')})  k={k['L']:g}/{k['M']:g}/{k['H']:g}")
    print(f"tier ROE L/M/H = {roe['L']:.4f}/{roe['M']:.4f}/{roe['H']:.4f} (FY27 EPS / opening-FY27 if-converted book)")
    print(
        f"ROE basis: BPS_open_FY27 = {bps_open['L']:.2f}/{bps_open['M']:.2f}/{bps_open['H']:.2f} USD/sh "
        f"(2Q26 book {bps_2q26:.2f} rolled over 2H26 unbooked {unbooked:.3f}/sh at b1 = g1/ROE = "
        f"{b1['L']:.2f}/{b1['M']:.2f}/{b1['H']:.2f}; b1 > 1 = the issuance stage-1 payout < 0 already prices); "
        f"old basis (2Q26 book) would read ROE {eps['L'] * inp['shares'] / inp['equity']:.4f}/"
        f"{eps['M'] * inp['shares'] / inp['equity']:.4f}/{eps['H'] * inp['shares'] / inp['equity']:.4f}"
    )
    print(
        f"B bucket (actual retention {ret_actual:.0%} − b1) × 2H26 unbooked → "
        f"{excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh "
        f"(negative = equity the model books as raised over 2H26; disclosure only, not a leg, not in BPS)"
    )
    for t in TIERS:
        p1 = 1.0 - g1 / roe[t]
        p2 = min(1.0, 1.0 - g2 / roe[t])
        tag = "issuance-funded" if p1 < 0 else "self-funded"
        print(
            f"{t}: eps {eps[t]:.3f} x {pes[t]:.2f}x = {anchors[t]:.2f}  "
            f"stage-1 payout {p1:+.2f} ({tag}) stage-2 payout {p2:.2f}"
        )
    print(f"timing (A22): tau {tau:g}y at r_journey -> x {(1 + r) ** -tau:.4f}; window 2H26 "
          + "/".join(f"{window[t]:.2f}" for t in TIERS)
          + f" (unbooked {unbooked:.3f} x (1 - b1) clipped at 0); steady path Y1 {y1} -> Y2 {y2}, steady {rs:.1%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        "FY28-basis (post-transition numerator x multiple): "
        + " | ".join(f"{t} {eps[t] * (1 + g1):.3f} x {pes[t] / (1 + g1):.2f}x" for t in TIERS)
        + f"  (H / FY28 consensus {inp['eps_fy28_cons']:g} = {H / inp['eps_fy28_cons']:.1f}x)"
    )
    print(f"flat-multiple ladder @ M {pes['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(
        f"same-basket vs terminal (③ n/a, no own band): 篮 4 peer FY+1 fwd-PE cluster [{lo:g}, {hi:g}] vs "
        f"L {pes['L']:.2f}x / M {pes['M']:.2f}x / H {pes['H']:.2f}x "
        f"(M Δ lower edge {pes['M'] - lo:+.2f} turn; floor 1/r_terminal = {1 / r_t:.2f}x)"
    )
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | "
        f"H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}"
    )
    print(
        f"option (A16): V_opt={v_opt:.2f} p={p_tiers[0]:g}/{p_tiers[1]:g}/{p_tiers[2]:g} -> "
        f"{band_v[0]:.2f}/{band_v[1]:.2f}/{band_v[2]:.2f} A'={A_v:.2f} B'={B_v:.2f}"
    )
    no_tr = value(tier_pes(g2, transition=False), r)
    print(
        f"cross-check, no transition year (same timing): "
        f"{no_tr['L']:.2f}/{no_tr['M']:.2f}/{no_tr['H']:.2f}  (L no-transition "
        f"{no_tr['L']:.2f} = deep_discount pressure coordinate)"
    )
    roe26 = inp["eps_fy26_m"] / opening_bps(inp["eps_fy26_m"])
    pe26 = three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roe26, r, g1=g1, n=n, r_terminal=r_t)
    print(f"coordinate, L on FY26 mean {inp['eps_fy26_m']:.3f} (digest year): "
          f"{inp['eps_fy26_m'] * pe26 * (1 - k['L']) / (1 + r) ** tau:.2f} ({pe26:.2f}x, k-adjusted, timed)")
    print(
        f"g2 leverage: g2 {g2 - G2_LEVERAGE_STEP:.0%} -> {band_dn[0]:.2f}/{band_dn[1]:.2f}/{band_dn[2]:.2f} | "
        f"g2 {g2:.0%} (cap) -> {L:.2f}/{M:.2f}/{H:.2f}  (+1pp above cap, not listed)"
    )
    print(f"cover={cover:.4f}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # both rates of the basket pair 1:1 — r_journey (stage 1 + the discount year)
    # and r_terminal (the tail); g1/g2, tier ROE, EPS and k stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r, r_t
        saved = r, r_t
        r, r_t = r + dr, r_t + dr
        try:
            v_r = value(tier_pes(g2), r)
            return v_r["L"], v_r["M"], v_r["H"]
        finally:
            r, r_t = saved

    rf = rf_block(LISTING_CCY, {"r_journey": r, "r_terminal": r_t}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Gate watch (framework §3 G2): non-failing — trigger needs 2 consecutive quarters
    conc = inp.get("conc_q2_max")
    if conc is not None and conc > 0.40:
        print(f"WARN[G2-watch]: conc_q2_max={conc:.2f} > 0.40 quarterly threshold")
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("BE.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
