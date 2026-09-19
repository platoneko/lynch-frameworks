#!/usr/bin/env python3
"""BE.US valuation eval — recompute anchors from frameworks/BE.US.md.

formula_id: be_fy2_eps_pe_order_gate_v1_gordon_v2

Single earnings ruler on the FY2027 Non-GAAP EPS consensus (28 houses): the
tier ladder lives in the numerator only — L = consensus low, M = mean, H = high,
three points of one distribution (A7).  Multiples are generated, not borrowed:
`two_stage_pe` runs one named transition year (FY28 FactSet aggregate, g1 =
+60.2%, n = 1 — FY29 has no ≥2-house consensus) and then the peer-cluster
reverse-solved perpetual g2 (GEV / VRT / ETN median 7.60%, capped at 6%, A13),
with r = the basket the Inputs row names (篮 7 单押 / 故事股, 15%, A18) and tier
ROE = EPS_x × shares ÷ if-converted equity (A8/A9).  The L tier carries the
same transition: its world is "delay", not "deterioration" (A14); the
no-transition figure is printed as the deep_discount pressure coordinate, never
as an anchor.

Valuation date (valuation-rules「两段式过渡 · 估值时点」, 2026-09-14): FY27 is
t=1 for all three tiers, `two_stage_pe` and `perpetual_pe` share the date, and
the FY28-basis multiple (PE / (1 + g1)) is printed because 表1 reports the
post-transition numerator.

Guardrail: none (裁决顺序 ③ has no band).  The ticker's own 12-month P/NTM band
[47.4, 199] is non-representative (super-ramp, NTM basis ≠ FY27 anchor), and
the peer forward-PE cluster (`pe_peer_lo/hi`, GEV / VRT / ETN) sits in 篮 4 --
a guardrail band must share the leg's basket, so the cluster is printed as a
cross-basket comparison only and never blocks (A8).

Option (A16): the beyond-consensus GW runway is priced as V_opt with per-tier
p_k; the script recomputes the corrected band and the market-implied p and
checks the stated V_opt / p_k / A′ / B′.

g2 leverage must be explicit: the zone is recomputed at g2 − 1pp and the eval
fails if it differs from the zone at the cap (valuation-rules「g₂ 的杠杆 MUST
显式」).  Order-gate fields (cover, concentration) are recomputed / watched but
never enter the anchors.  No probability enters the base deck.

Run:  python3 eval/BE.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "BE.US.md"
FORMULA_ID = "be_fy2_eps_pe_order_gate_v1_gordon_v2"
TOL = 0.05
MIN_R_MINUS_G = 0.02  # below this the multiple sits at the pole
DERIVED_TOL = 5e-4  # g1 / roe_* rows are derived; Inputs must agree with the recomputation
G2_LEVERAGE_STEP = 0.01  # zone must survive g2 − 1pp (evidence range collapses onto the cap)

REQUIRED = [
    "price",
    "shares",
    "equity",
    "eps_fy26_m",
    "eps_fy27_l",
    "eps_fy27_m",
    "eps_fy27_h",
    "eps_fy28_cons",
    "g1",
    "n_g1",
    "g2",
    "r_perp",
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

    # r is the basket value the Inputs row names (篮 7 single-product / story
    # stock, A18); a missing basket tag is itself an error.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    gap = inp["r_perp"] - inp["g2"]
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

    r = inp["r_perp"]
    n = int(inp["n_g1"])
    g2 = inp["g2"]
    eps = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}

    # ---- Step 1: derived inputs recomputed from their sources (A8 / A15) ----
    g1 = inp["eps_fy28_cons"] / inp["eps_fy27_m"] - 1.0
    if abs(g1 - inp["g1"]) > DERIVED_TOL:
        errors.append(f"g1: stated {inp['g1']:.4f} vs recomputed {g1:.4f}")
    roe = {t: eps[t] * inp["shares"] / inp["equity"] for t in TIERS}
    for t, key in zip(TIERS, ("roe_l", "roe_m", "roe_h")):
        if abs(roe[t] - inp[key]) > DERIVED_TOL:
            errors.append(f"{key}: stated {inp[key]:.4f} vs recomputed {roe[t]:.4f}")

    # ---- Step 2: multiples (g shared across tiers; only ROE varies) and anchors ----
    def tier_pes(g2_: float, transition: bool = True) -> dict[str, float]:
        return {
            t: (two_stage_pe(g1, n, g2_, roe[t], r) if transition else perpetual_pe(g2_, roe[t], r))
            for t in TIERS
        }

    pes = tier_pes(g2)
    anchors = {t: eps[t] * pes[t] for t in TIERS}
    L, M, H = (anchors[t] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    # ---- Step 3: cross-basket comparison, not a guardrail (A8) ----
    # The peer FY+1 forward-PE cluster is 篮 4 (GEV / VRT / ETN); a ③ band must
    # share the leg's basket, so the cluster is only printed against the tiers.
    lo, hi = inp["pe_peer_lo"], inp["pe_peer_hi"]
    if not (0 < lo < hi):
        errors.append("pe_peer_lo/hi comparison band malformed")

    # ---- Step 4: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pes["M"])
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
    band_dn = tuple(eps[t] * pes_dn[t] for t in TIERS)
    zone_dn = zone_of(inp["price"], *band_dn)
    if zone_dn != zone:
        errors.append(f"zone moves within g2 evidence range: {zone} at cap vs {zone_dn} at g2-1pp — BLOCKED")

    cover = (inp["rpo_product_install"] + inp["customer_deposits"]) / inp["revenue_next_12m"]
    if abs(cover - inp["cover"]) > 0.01:
        errors.append(f"cover: stated {inp['cover']} vs recomputed {cover:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"g1(FY28 aggregate / FY27 mean - 1)={g1:.4f} n={n} g2={g2:.4f} r={r:g} (篮 {baskets.get('r_perp')})")
    print(f"tier ROE L/M/H = {roe['L']:.4f}/{roe['M']:.4f}/{roe['H']:.4f} (if-converted equity)")
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
        f"cross-basket comparison (no ③): 篮 4 peer FY+1 fwd-PE cluster [{lo:g}, {hi:g}] vs "
        f"L {pes['L']:.2f}x / M {pes['M']:.2f}x / H {pes['H']:.2f}x "
        f"(M Δ lower edge {pes['M'] - lo:+.2f} turn; floor 1/r = {1 / r:.2f}x)"
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
    print(f"implied r(P), single-stage approx g2+(r-g2)*M/P = {g2 + (r - g2) * M / inp['price']:.4f} vs basket r {r:g}")
    no_tr = tier_pes(g2, transition=False)
    print(
        f"cross-check, no transition year: {eps['L'] * no_tr['L']:.2f}/{eps['M'] * no_tr['M']:.2f}/"
        f"{eps['H'] * no_tr['H']:.2f}  (L no-transition {eps['L'] * no_tr['L']:.2f} = deep_discount pressure coordinate)"
    )
    roe26 = inp["eps_fy26_m"] * inp["shares"] / inp["equity"]
    pe26 = two_stage_pe(g1, n, g2, roe26, r)
    print(f"coordinate, L on FY26 mean {inp['eps_fy26_m']:.3f} (digest year): {inp['eps_fy26_m'] * pe26:.2f} ({pe26:.2f}x)")
    print(
        f"g2 leverage: g2 {g2 - G2_LEVERAGE_STEP:.0%} -> {band_dn[0]:.2f}/{band_dn[1]:.2f}/{band_dn[2]:.2f} zone={zone_dn} | "
        f"g2 {g2:.0%} (cap) -> {L:.2f}/{M:.2f}/{H:.2f} zone={zone}  (+1pp above cap, not listed)"
    )
    print(f"cover={cover:.4f}  price={inp['price']:.2f} zone={zone}  P/H={inp['price'] / H - 1:+.1%}")

    # Gate watch (framework §3 G2): non-failing — trigger needs 2 consecutive quarters
    conc = inp.get("conc_q2_max")
    if conc is not None and conc > 0.40:
        print(f"WARN[G2-watch]: conc_q2_max={conc:.2f} > 0.40 quarterly threshold")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
