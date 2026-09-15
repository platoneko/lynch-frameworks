#!/usr/bin/env python3
"""MRVL.US valuation eval — recompute anchors from frameworks/MRVL.US.md.

formula_id: mrvl_sotp_gordon_two_stage_fy28_v3

Three legs (Custom / Connectivity / Comm) on the FY28 consensus EPS split by
revenue weight.  Multiples are generated, not borrowed: each leg reads the
perpetual g2 AVGO names for the same business (AVGO's Gordon legs: XPU /
networking / non-AI, peer cross-section reverse-solved and capped), so the two
tickers share a growth axis rather than a PE number, and the two AI legs run
one named transition year (FY29 consensus EPS growth) through `two_stage_pe`
on the same valuation date as the Comm leg's `perpetual_pe` (FY28 = t=1,
valuation-rules「两段式过渡 · 估值时点」2026-09-14); the FY29-basis multiple
(PE / (1 + g1)) is printed because 表1 reports the post-transition numerator.
The tier ladder lives in the numerator only: L = FY27
consensus (FY28 as a digest year), M = FY28 consensus mean, H = FY28 consensus
high.  Tier ROE = EPS_x * shares / equity, so the L multiple falls out lower
mechanically, not by policy.

Numerator year (valuation-rules 裁决顺序 ②, A3): FY28 is the furthest year with a
>=2-house consensus *range* (41 houses); FY29 is visible to three houses but only
as point estimates (two of them identical), so it is the g1 layer, not the
numerator.  Guardrail (③): every blended tier multiple must sit inside the
ticker's own realised next-FY PE band (`pe_own_min/max`, A11); the band-edge
Δg printed below is the uniform shift of all three legs' g2 that would take the
M-tier blended multiple to either edge -- evidence of what the market has paid
for, not an input.

V_opt = one $1B/yr custom-silicon unit beyond consensus (two Google warrant
tranches), priced with BofA's +EPS-per-$1B sensitivity and the Custom M-tier
multiple.  Probabilities never enter the base deck.

Run:  python3 eval/MRVL.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    G_CAP,
    R_OPERATING,
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
    parse_inputs,
    report,
)
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "MRVL.US.md"
AVGO_FRAMEWORK = REPO_ROOT / "frameworks" / "AVGO.US.md"
FORMULA_ID = "mrvl_sotp_gordon_two_stage_fy28_v3"
TOL = 0.05
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole

REQUIRED = [
    "price",
    "shares",
    "equity",
    "eps_fy27_m",
    "eps_fy28_m",
    "eps_fy28_h",
    "eps_fy29_cons",
    "n_stage",
    "r_perp",
    "g2_cu",
    "g2_conn",
    "g2_comm",
    "w_custom",
    "w_conn",
    "w_comm",
    "d_eps_per_bn",
    "v_opt_units",
    "pe_own_min",
    "pe_own_max",
]

# AVGO leg -> MRVL leg: each MRVL leg reads the perpetual g2 AVGO names for the
# same business.  Reading AVGO's Inputs here is what makes "同轴" a checked
# fact rather than a sentence.
AVGO_LEG_FOR = {"g2_cu": "g2_xpu", "g2_conn": "g2_net", "g2_comm": "g2_nonai"}
TIERS = ("L", "M", "H")
LEGS = ("cu", "conn", "comm")


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def check_coaxial_with_avgo(inp: dict[str, float]) -> list[str]:
    """Each g2 must equal the g2 AVGO's same-business leg names (A2)."""
    avgo = parse_inputs(AVGO_FRAMEWORK.read_text(encoding="utf-8"))
    errs: list[str] = []
    for g_key, avgo_key in AVGO_LEG_FOR.items():
        if avgo_key not in avgo:
            errs.append(f"AVGO.US.md lacks {avgo_key}; cannot verify {g_key}")
            continue
        if abs(avgo[avgo_key] - inp[g_key]) > 5e-5:
            errs.append(
                f"{g_key}={inp[g_key]:.4f} != AVGO {avgo_key}={avgo[avgo_key]:.4f} — AVGO's g2 moved, re-sync"
            )
    return errs


def sanity_checks(inp: dict[str, float]) -> list[str]:
    errs: list[str] = []

    # All three legs are ordinary operating cash flow; hyperscaler programs are
    # not the conditional 13% tier (no unclosed financing behind the revenue).
    errs += check_r(inp["r_perp"], "r_perp")
    if abs(inp["r_perp"] - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={inp['r_perp']}: operating legs, expected {R_OPERATING}")

    for leg in LEGS:
        errs += check_g_cap(inp[f"g2_{leg}"], f"g2_{leg}")
        gap = inp["r_perp"] - inp[f"g2_{leg}"]
        if gap <= 0:
            errs.append(f"perpetuity diverges on {leg}: g2 >= r")
        elif gap < MIN_R_MINUS_G:
            errs.append(f"r - g2_{leg} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # A2e-2a: one growth axis (FY28 vs FY27), three points on it.
    errs += ladder("numerator", inp["eps_fy27_m"], inp["eps_fy28_m"], inp["eps_fy28_h"])
    if inp["eps_fy29_cons"] <= inp["eps_fy28_h"]:
        errs.append("FY29 consensus below FY28 high: the transition year has no growth to name")
    # Only FY29 carries a consensus (A4); FY30+ is single-house.
    errs += check_transition_years(int(inp["n_stage"]), 1, "n_stage")

    wsum = inp["w_custom"] + inp["w_conn"] + inp["w_comm"]
    if abs(wsum - 1.0) > 1e-6:
        errs.append(f"weights sum != 1: {wsum}")

    # A2e-7a: probabilities stay in the zone+V table.
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
    errors = sanity_checks(inp) + check_coaxial_with_avgo(inp)

    r = inp["r_perp"]
    n = int(inp["n_stage"])
    g1 = inp["eps_fy29_cons"] / inp["eps_fy28_m"] - 1.0
    eps = {"L": inp["eps_fy27_m"], "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}
    weights = {"cu": inp["w_custom"], "conn": inp["w_conn"], "comm": inp["w_comm"]}

    # ---- Step 1: tier ROE from one equity field (AGENTS.md 永续增长口径) ----
    roe = {t: eps[t] * inp["shares"] / inp["equity"] for t in TIERS}

    # ---- Step 2: multiples per leg per tier (g shared across tiers) ----
    def leg_pes(tier: str, transition: bool = True) -> dict[str, float]:
        out = {}
        for leg in ("cu", "conn"):
            out[leg] = (
                two_stage_pe(g1, n, inp[f"g2_{leg}"], roe[tier], r)
                if transition
                else perpetual_pe(inp[f"g2_{leg}"], roe[tier], r)
            )
        out["comm"] = perpetual_pe(inp["g2_comm"], roe[tier], r)
        return out

    pes = {t: leg_pes(t) for t in TIERS}
    blended = {t: sum(weights[k] * pes[t][k] for k in LEGS) for t in TIERS}
    legs_ps = {t: {k: eps[t] * weights[k] * pes[t][k] for k in LEGS} for t in TIERS}
    anchors = {t: eps[t] * blended[t] for t in TIERS}
    L, M, H = (anchors[t] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    # Guardrail: a generated multiple outside the ticker's own realized band is red.
    for t in TIERS:
        if not (inp["pe_own_min"] <= blended[t] <= inp["pe_own_max"]):
            errors.append(
                f"{t} blended PE {blended[t]:.1f}x outside own realized band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
            )

    # Band-edge Δg (裁决顺序 ③ 带即证据): shift every leg's g2 by the same Δ until the
    # M-tier blended multiple reaches each edge of the own band.  Reported, never used.
    def blended_at(tier: str, delta: float) -> float:
        out = 0.0
        for leg in LEGS:
            g2 = inp[f"g2_{leg}"] + delta
            pe = (
                two_stage_pe(g1, n, g2, roe[tier], r)
                if leg in ("cu", "conn")
                else perpetual_pe(g2, roe[tier], r)
            )
            out += weights[leg] * pe
        return out

    def delta_to(target: float, tier: str) -> float:
        lo, hi = -0.15, r - max(inp[f"g2_{leg}"] for leg in LEGS) - 1e-4  # stay below the pole
        for _ in range(200):
            mid = (lo + hi) / 2
            if blended_at(tier, mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_dg = (delta_to(inp["pe_own_min"], "M"), delta_to(inp["pe_own_max"], "M"))

    # ---- Step 3: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), blended["M"])
    errors += flat_errs
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (blended["L"], blended["M"], blended["H"]))

    # ---- Step 4: option ceiling and zone+V (probabilities only here) ----
    v_opt = inp["v_opt_units"] * inp["d_eps_per_bn"] * pes["M"]["cu"]
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    p_tiers = stated_p_tiers(md)
    if p_tiers is None:
        errors.append("p_L/p_M/p_H not stated")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"g1(FY29 cons / FY28 cons - 1)={g1:.4f} n={n} r={r:g}  g2 cu/conn/comm="
          f"{inp['g2_cu']:.4f}/{inp['g2_conn']:.4f}/{inp['g2_comm']:.4f}")
    print(f"tier ROE L/M/H = {roe['L']:.3f}/{roe['M']:.3f}/{roe['H']:.3f} (equity-based)")
    for t in TIERS:
        p1 = 1.0 - g1 / roe[t]
        tag = "issuance-funded" if p1 < 0 else "self-funded"
        print(
            f"{t}: eps {eps[t]:.4f} x blended {blended[t]:.2f}x = {anchors[t]:.2f}  "
            f"[cu {legs_ps[t]['cu']:.2f} ({pes[t]['cu']:.2f}x) / conn {legs_ps[t]['conn']:.2f} "
            f"({pes[t]['conn']:.2f}x) / comm {legs_ps[t]['comm']:.2f} ({pes[t]['comm']:.2f}x)]  "
            f"stage-1 payout {p1:+.3f} ({tag})"
        )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    # 表1 basis: AI legs on the post-transition FY29 numerator (x (1 + g1)), Comm flat.
    eps29 = {t: eps[t] * (weights["cu"] + weights["conn"]) * (1.0 + g1) + eps[t] * weights["comm"] for t in TIERS}
    print(
        "FY29-basis: AI legs "
        + "/".join(f"{pes[t]['cu'] / (1 + g1):.2f}x" for t in TIERS)
        + " (FY28-basis " + "/".join(f"{pes[t]['cu']:.2f}x" for t in TIERS) + "); blended "
        + "/".join(f"{anchors[t] / eps29[t]:.2f}x" for t in TIERS)
        + f"; M / FY29 consensus {inp['eps_fy29_cons']:g} = {M / inp['eps_fy29_cons']:.2f}x"
    )
    print(f"flat-multiple ladder @ M {blended['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    ai_cap_hit = inp["g2_cu"] + band_edge_dg[1] > G_CAP + 1e-9
    print(
        f"own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] band-edge Δg @ M ROE (all legs shifted): "
        f"lower {band_edge_dg[0]:+.4f} / upper {band_edge_dg[1]:+.4f}"
        f"{' (upper edge needs AI g2 above the 6% cap — unreachable under ①)' if ai_cap_hit else ''}"
    )
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | "
        f"H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}"
    )
    no_tr = {t: eps[t] * sum(weights[k] * leg_pes(t, transition=False)[k] for k in LEGS) for t in TIERS}
    print(f"cross-check, no transition year: {no_tr['L']:.2f}/{no_tr['M']:.2f}/{no_tr['H']:.2f}")
    print(f"V_opt={v_opt:.2f} (units {inp['v_opt_units']:g} x dEPS {inp['d_eps_per_bn']:g} x cu M-PE {pes['M']['cu']:.2f})")
    if p_tiers:
        opt = tuple(anchors[t] + p * v_opt for t, p in zip(TIERS, p_tiers))
        a2, b2 = cut_points(*opt)
        print(f"zone+V band: {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}  "
              f"zone+V={zone_of(inp['price'], *opt)}")
    print(f"price={inp['price']:.2f} zone={zone}  P/H={inp['price'] / H - 1:+.1%}  "
          f"implied p=(P-H)/V_opt={(inp['price'] - H) / v_opt:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
