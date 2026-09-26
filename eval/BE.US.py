#!/usr/bin/env python3
"""BE.US valuation eval — recompute anchors from frameworks/BE.US.md.

formula_id: be_fy2_eps_pe_order_gate_v1_gordon_v2

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

Option (A16): the beyond-consensus GW runway is priced as V_opt with per-tier
p_k; the script recomputes the corrected band and the market-implied p and
checks the stated V_opt / p_k / A′ / B′.

g2 leverage must be explicit: the zone is recomputed at g2 − 1pp and the eval
fails if it differs from the zone at the cap (valuation-rules「g₂ 的杠杆 MUST
显式」).  Order-gate fields (cover, concentration) are recomputed / watched but
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
from eval.lib.zones import cut_points, zone_of  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "BE.US.md"
FORMULA_ID = "be_fy2_eps_pe_order_gate_v1_gordon_v2"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02  # below this the multiple sits at the pole
DERIVED_TOL = 5e-4  # g1 / roe_* rows are derived; Inputs must agree with the recomputation
G2_LEVERAGE_STEP = 0.01  # zone must survive g2 − 1pp (evidence range collapses onto the cap)

REQUIRED = [
    "price",
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
]
TIERS = ("L", "M", "H")


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
    def tier_pes(g2_: float, transition: bool = True) -> dict[str, float]:
        return {
            t: (two_stage_pe(g1, n, g2_, roe[t], r, r_terminal=r_t) if transition
                else perpetual_pe(g2_, roe[t], r_t))
            for t in TIERS
        }

    # k leaves the anchors only — never the multiple, never b (A21; same
    # discipline as the「视同派出」k).  It is flat across tiers here, so the four
    # cross-ticker ratios are identical with and without it.
    pes = tier_pes(g2)
    anchors = {t: eps[t] * pes[t] * (1.0 - k[t]) for t in TIERS}
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

    # ---- Step 5: zone, g2 leverage, order-gate coordinates ----
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)

    # Option (A16): V_opt is a stated input of the framework (its four elements
    # live in A16, not in Inputs); the script checks the corrected band and its
    # cut-points reproduce, and reads the market-implied p from the ceiling.
    said_v = stated_v_opt(md)
    p_tiers = stated_p_tiers(md)
    if said_v is None or p_tiers is None:
        errors.append("V_opt / p_L/p_M/p_H not found in Outputs (A16 option)")
        v_opt, p_tiers = 0.0, (0.0, 0.0, 0.0)
    else:
        v_opt = said_v
    band_v = tuple(a + p * v_opt for a, p in zip((L, M, H), p_tiers))
    A_v, B_v = cut_points(*band_v)
    said_a_v, said_b_v = stated_option_cuts(md)
    for name, said, got in (("A′", said_a_v, A_v), ("B′", said_b_v, B_v)):
        if said is None or abs(said - got) > TOL:
            errors.append(f"{name}: stated {said} vs recomputed {got:.4f}")
    zone_v = zone_of(inp["price"], *band_v)
    implied_p = (inp["price"] - H) / v_opt if v_opt else float("nan")

    # g2 leverage: every peer reverse-solves above the cap, so the evidence range
    # collapses onto it; the zone must be the same one step below (A13).
    pes_dn = tier_pes(g2 - G2_LEVERAGE_STEP)
    band_dn = tuple(eps[t] * pes_dn[t] * (1.0 - k[t]) for t in TIERS)
    zone_dn = zone_of(inp["price"], *band_dn)
    if zone_dn != zone:
        errors.append(f"zone moves within g2 evidence range: {zone} at cap vs {zone_dn} at g2-1pp — BLOCKED")

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
        f"{band_v[0]:.2f}/{band_v[1]:.2f}/{band_v[2]:.2f} A'={A_v:.2f} B'={B_v:.2f} zone={zone_v} | "
        f"market-implied p=(P-H)/V_opt={implied_p:.2f}"
    )
    print(f"implied r(P), single-stage approx g2+(r_t-g2)*M/P = "
          f"{g2 + (r_t - g2) * M / inp['price']:.4f} vs r_terminal {r_t:g} (journey {r:g})")
    no_tr = tier_pes(g2, transition=False)
    print(
        f"cross-check, no transition year: "
        f"{eps['L'] * no_tr['L'] * (1 - k['L']):.2f}/{eps['M'] * no_tr['M'] * (1 - k['M']):.2f}/"
        f"{eps['H'] * no_tr['H'] * (1 - k['H']):.2f}  (L no-transition "
        f"{eps['L'] * no_tr['L'] * (1 - k['L']):.2f} = deep_discount pressure coordinate)"
    )
    roe26 = inp["eps_fy26_m"] / opening_bps(inp["eps_fy26_m"])
    pe26 = two_stage_pe(g1, n, g2, roe26, r, r_terminal=r_t)
    print(f"coordinate, L on FY26 mean {inp['eps_fy26_m']:.3f} (digest year): "
          f"{inp['eps_fy26_m'] * pe26 * (1 - k['L']):.2f} ({pe26:.2f}x, k-adjusted)")
    print(
        f"g2 leverage: g2 {g2 - G2_LEVERAGE_STEP:.0%} -> {band_dn[0]:.2f}/{band_dn[1]:.2f}/{band_dn[2]:.2f} zone={zone_dn} | "
        f"g2 {g2:.0%} (cap) -> {L:.2f}/{M:.2f}/{H:.2f} zone={zone}  (+1pp above cap, not listed)"
    )
    print(f"cover={cover:.4f}  price={inp['price']:.2f} zone={zone}  P/H={inp['price'] / H - 1:+.1%}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # both rates of the basket pair 1:1 — r_journey (stage 1 + the discount year)
    # and r_terminal (the tail); g1/g2, tier ROE, EPS and k stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r, r_t
        saved = r, r_t
        r, r_t = r + dr, r_t + dr
        try:
            pes_r = tier_pes(g2)
            lmh = [eps[t] * pes_r[t] * (1.0 - k[t]) for t in TIERS]
            return lmh[0], lmh[1], lmh[2]
        finally:
            r, r_t = saved

    rf = rf_block(LISTING_CCY, {"r_journey": r, "r_terminal": r_t}, band_rf, inp["price"])
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
