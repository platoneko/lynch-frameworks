#!/usr/bin/env python3
"""TSM.US valuation eval — recompute anchors from frameworks/TSM.US.md.

formula_id: tsm_sotp_2027_two_stage_gordon_v5

Numerators are the three points of the 2027E consensus EPS range (low / mean /
high, 13 houses, USD per ADR); L is the digest world (2028 does not grow) and
calls `perpetual_pe`, M/H carry ONE named transition year -- 2028E sell-side
consensus growth over 2027E consensus, both in TWD so FX cancels -- through
`two_stage_pe`, then the perpetual g2.  Both rulers price 2027E as t=1 on the
same date (valuation-rules「两段式过渡 · 估值时点」, 2026-09-14); the 2028-basis
multiple (PE / (1 + g1)) is printed because 表1 reports the post-transition
numerator.  Tier ROE = EPS_x × ADR shares / book equity.  Three legs share the
multiple: A wafer, B1 advanced packaging as max(CoWoS capacity × UV, adv EPS ×
PE), B2 other back-end.  No discounting: 2027E is the current year + 1.

COUPE (silicon photonics) is stated in the repo's 7d form: V_opt = the H-tier
ceiling V_H from _AXIS.optical-comms OE × $450 × share × npm × same-tier PE,
and p_k = V_k / V_H for the lower tiers (mechanical, no probability).  表3
rows are base_k + p_k × V_opt and must reproduce the per-tier V_k exactly.

Guardrail: every generated multiple must sit inside the ticker's own realised
next-FY PE band (`pe_own_min/max`).  g2 is the band-edge reverse-solve
(valuation-rules 裁决顺序 ③, A7): the semiconductor cross-section's 6.52% would
generate multiples the market has never paid TSM, so g2 is solved to the value
at which the first tier to touch the band (H, the highest ROE) sits exactly on
the upper edge, on the same valuation date as the anchors (re-solved to 5.04%
on 2026-09-14 when the date convention switched); the check is `g2 <= binding
tier's band-edge g`, and the per-tier band-edge g printed below is evidence,
not an input.  The g2 ±1pp zone line is PRINT ONLY: g2 is pinned by the band
edge (not a free choice), so a zone flip inside ±1pp is a fact about the price
sitting on a cut, and this ticker deliberately carries no hard check for it.  Numerator year (②, A20): 2027E is the furthest year with a >=2-house
consensus range; 2028E is two point estimates and therefore the g1 layer.

Run:  python3 eval/TSM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    check_cowos_supply,
    check_optical_narrow_attach,
    check_optical_oe_mount,
)
from eval.lib.gordon import (  # noqa: E402
    R_OPERATING,
    check_g_cap,
    check_r,
    check_transition_years,
    implied_g,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "TSM.US.md"
FORMULA_ID = "tsm_sotp_2027_two_stage_gordon_v5"
TOL = 0.15
P_TOL = 0.0005  # p_k are stated to 3 decimals
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
NPM_TOL = 0.03  # A17: the margin-retreat mechanism must reproduce the consensus low

_V_OPT = re.compile(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*")
_P_TIERS = re.compile(
    r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
    r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)"
)
# 表3 rows: | L | 297.6 | 0.003 *(有锚…)* | 0.05 | **297.7** | …
_T3_ROW = re.compile(
    r"\|\s*([LMH])\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)[^|]*\|\s*([0-9.]+)\s*\|\s*\*\*([0-9.]+)\*\*"
)

REQUIRED = [
    "price",
    "shares_adr",
    "equity",
    "eps_2027_l",
    "eps_2027_m",
    "eps_2027_h",
    "eps_2027_cons_twd",
    "eps_2028_cons_twd",
    "n_stage",
    "n_consensus",
    "share_wafer",
    "share_adv",
    "share_other",
    "npm_2027e_l",
    "npm_2027e_m",
    "g2",
    "r_perp",
    "pe_own_min",
    "pe_own_max",
    "cowos_wpm_l",
    "cowos_wpm_m",
    "cowos_wpm_h",
    "uv_per_10k_wpm",
    "oe_l",
    "oe_m",
    "oe_h",
    "asp_oe",
    "coupe_share_l",
    "coupe_share_m",
    "coupe_share_h",
    "npm_coupe",
]
TIERS = ("l", "m", "h")


def sanity_checks(inp: dict[str, float]) -> list[str]:
    errs: list[str] = []
    errs += check_r(inp["r_perp"], "r_perp")
    if abs(inp["r_perp"] - R_OPERATING) > 1e-9:
        errs.append(f"r_perp={inp['r_perp']}: operating legs, expected {R_OPERATING}")
    errs += check_g_cap(inp["g2"], "g2")
    gap = inp["r_perp"] - inp["g2"]
    if gap <= 0:
        errs.append("perpetuity diverges: g2 >= r")
    elif gap < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    # Only 2028E carries a >=2-house consensus (A6); 2029E is a story.
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if inp["eps_2028_cons_twd"] <= inp["eps_2027_cons_twd"]:
        errs.append("2028E consensus below 2027E: the transition year has no growth to name")
    # A2e-2a: three points of one 13-house 2027E range.
    errs += ladder("numerator (2027E low/mean/high)", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    # A17: the named margin-retreat mechanism reproduces the consensus low.
    mech = inp["eps_2027_m"] * inp["npm_2027e_l"] / inp["npm_2027e_m"]
    if abs(mech / inp["eps_2027_l"] - 1.0) > NPM_TOL:
        errs.append(
            f"A17 mechanism: mean × {inp['npm_2027e_l']:g}/{inp['npm_2027e_m']:g} = {mech:.2f} "
            f"vs consensus low {inp['eps_2027_l']:g} (> {NPM_TOL:.0%} apart) — L is no longer the named world"
        )
    share_sum = inp["share_wafer"] + inp["share_adv"] + inp["share_other"]
    if abs(share_sum - 1.0) > 1e-6:
        errs.append(f"leg shares sum {share_sum} != 1")
    if not (inp["cowos_wpm_l"] < inp["cowos_wpm_m"] <= inp["cowos_wpm_h"]):
        errs.append("cowos_wpm ladder: expected L < M <= H")
    if abs(inp["asp_oe"] - 450.0) > 1e-9:
        errs.append(f"asp_oe={inp['asp_oe']} must be 450 (GS CPO OE BoM)")
    if not (inp["coupe_share_l"] < inp["coupe_share_m"] < inp["coupe_share_h"] <= 1.0):
        errs.append("coupe_share ladder: expected L < M < H <= 100%")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errs.append(f"p-class fields must not appear in Inputs: {leaked}")
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

    r, g2, n = inp["r_perp"], inp["g2"], int(inp["n_stage"])
    g1 = inp["eps_2028_cons_twd"] / inp["eps_2027_cons_twd"] - 1.0
    eps = {"l": inp["eps_2027_l"], "m": inp["eps_2027_m"], "h": inp["eps_2027_h"]}

    # ---- Step 1: tier ROE from one equity field ----
    roe = {t: eps[t] * inp["shares_adr"] / inp["equity"] for t in TIERS}

    # ---- Step 2: multiples — L digest (perpetual), M/H one transition year ----
    def tier_pe(t: str, transition: bool) -> float:
        if transition:
            return two_stage_pe(g1, n, g2, roe[t], r)
        return perpetual_pe(g2, roe[t], r)

    pe = {t: tier_pe(t, transition=(t != "l")) for t in TIERS}

    # Band-edge g2 per tier (裁决顺序 ③ 带即证据): the g2 at which this tier's own
    # multiple would sit on the band's upper edge.  Reported only.
    def g2_at_edge(t: str, target: float) -> float:
        lo, hi = -0.05, r - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if (perpetual_pe(mid, roe[t], r) if t == "l" else two_stage_pe(g1, n, mid, roe[t], r)) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_g2 = {t: g2_at_edge(t, inp["pe_own_max"]) for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"{t.upper()} generated PE {pe[t]:.2f}x outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
            )

    # ---- Step 3: three legs; B1 = max(capacity × UV, adv EPS × PE) ----
    def capacity(wpm: float) -> float:
        return (wpm / 10000.0) * inp["uv_per_10k_wpm"] / inp["shares_adr"]

    def legs_at(t: str, p: float) -> dict[str, float]:
        e = eps[t]
        floor = e * inp["share_adv"] * p
        cap = capacity(inp[f"cowos_wpm_{t}"])
        pa, pb1, pb2 = e * inp["share_wafer"] * p, max(cap, floor), e * inp["share_other"] * p
        return {"Pa": pa, "Pb1": pb1, "Pb2": pb2, "cap": cap, "floor": floor, "sum": pa + pb1 + pb2}

    legs = {t: legs_at(t, pe[t]) for t in TIERS}
    L, M, H = (legs[t]["sum"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"invariant L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    # ---- Step 4: A2e-2c flat ladder + A2e-5 decomposition ----
    eps_t = (eps["l"], eps["m"], eps["h"])
    flat_errs, _ = flat_multiple_ladder(eps_t, pe["m"])
    errors += flat_errs
    flat = tuple(legs_at(t, pe["m"])["sum"] for t in TIERS)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    dec = decompose((L, M, H), (pe["l"], pe["m"], pe["h"]))

    # ---- Step 5: axes ----
    errors += [f"axis: {e}" for e in check_cowos_supply(inp["cowos_wpm_m"])]
    errors += [f"optical axis: {e}" for e in check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"]))]
    coupe_rev = {t: inp[f"oe_{t}"] * inp["asp_oe"] * inp[f"coupe_share_{t}"] for t in TIERS}
    errors += [f"COUPE narrow: {e}" for e in check_optical_narrow_attach({t.upper(): coupe_rev[t] for t in TIERS})]

    # ---- Step 6: COUPE option in 7d form (V_opt = V_H, p_k = V_k / V_H) ----
    v_k = {t: (coupe_rev[t] * inp["npm_coupe"] / inp["shares_adr"]) * pe[t] for t in TIERS}
    v_opt = v_k["h"]
    p_k = {t: v_k[t] / v_opt for t in TIERS}

    # ---- Step 7: zone and stated values ----
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    vm = _V_OPT.search(out_sec)
    if vm is None:
        errors.append("V_opt not stated in Outputs")
    elif abs(float(vm.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt: stated {vm.group(1)} vs {v_opt:.4f}")
    pm = _P_TIERS.search(out_sec)
    if pm is None:
        errors.append("p_L/p_M/p_H not stated in Outputs")
    else:
        for t, said in zip(TIERS, (float(x) for x in pm.groups())):
            if abs(said - p_k[t]) > P_TOL:
                errors.append(f"p_{t.upper()}: stated {said} vs {p_k[t]:.4f}")
    rows = _T3_ROW.findall(out_sec)
    if len(rows) != 3:
        errors.append(f"表3 must have 3 rows, found {len(rows)}")
    else:
        for (lab, base_s, p_s, pv_s, adj_s), t in zip(rows, TIERS):
            base = legs[t]["sum"]
            if lab != t.upper():
                errors.append(f"表3 row order: expected {t.upper()}, got {lab}")
            if abs(float(base_s) - base) > TOL:
                errors.append(f"表3 base_{t}: {base_s} vs {base:.4f}")
            if abs(float(p_s) - p_k[t]) > P_TOL:
                errors.append(f"表3 p_{t}: {p_s} vs {p_k[t]:.4f}")
            if abs(float(pv_s) - v_k[t]) > TOL:
                errors.append(f"表3 p·V_{t}: {pv_s} vs {v_k[t]:.4f}")
            if abs(float(adj_s) - (base + v_k[t])) > TOL:
                errors.append(f"表3 adj_{t}: {adj_s} vs {base + v_k[t]:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"g1 (2028E cons {inp['eps_2028_cons_twd']:g} / 2027E cons {inp['eps_2027_cons_twd']:g} TWD - 1) = {g1:.4f}"
          f"  n={n}  g2={g2:g}  r={r:g}")
    print(f"tier EPS (2027E, USD/ADR) = {eps['l']:.2f}/{eps['m']:.2f}/{eps['h']:.2f}  ROE = {roe['l']:.3f}/{roe['m']:.3f}/{roe['h']:.3f}"
          f"  (equity {inp['equity']:.4g} USD)")
    for t in TIERS:
        lg = legs[t]
        p1 = 1.0 - g1 / roe[t]
        tag = "no transition (digest)" if t == "l" else ("issuance-funded" if p1 < 0 else "self-funded")
        print(
            f"{t.upper()}: eps {eps[t]:.2f} x PE {pe[t]:.2f}x  wafer {lg['Pa']:.1f}  B1 {lg['Pb1']:.1f} "
            f"(max cap {lg['cap']:.1f} / floor {lg['floor']:.1f})  B2 {lg['Pb2']:.1f}  = {lg['sum']:.1f}"
            f"  stage-1 payout {p1:+.3f} ({tag})"
        )
    print(f"L={L:.1f} M={M:.1f} H={H:.1f} A={A:.1f} B={B:.1f}")
    # 表1 basis: M/H on the post-transition 2028 numerator (x (1 + g1)); L's 2028 = 2027E.
    print(
        "2028-basis (post-transition numerator x multiple): "
        f"L {eps['l']:.2f} x {pe['l']:.2f}x | M {eps['m'] * (1 + g1):.2f} x {pe['m'] / (1 + g1):.2f}x | "
        f"H {eps['h'] * (1 + g1):.2f} x {pe['h'] / (1 + g1):.2f}x"
    )
    print(f"flat-multiple ladder @ M {pe['m']:.2f}x: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    print(
        f"own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] band-edge g2 (upper edge, per tier ROE): "
        f"L {band_edge_g2['l']:.4%} / M {band_edge_g2['m']:.4%} / H {band_edge_g2['h']:.4%}"
        f"  -> shared g2 {g2:.2%} {'<=' if g2 <= min(band_edge_g2.values()) + 1e-9 else '>'} binding tier"
    )
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | "
        f"H/M {dec['hm']:.3f} = num {eps_t[2] / eps_t[1]:.3f} x pe {dec['pe_hm']:.3f} "
        f"x rest(B1 max) {dec['hm'] / (eps_t[2] / eps_t[1]) / dec['pe_hm']:.3f} | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}"
    )
    no_tr = {t: legs_at(t, tier_pe(t, transition=False))["sum"] for t in TIERS}
    print(f"cross-check, no transition year: {no_tr['l']:.1f}/{no_tr['m']:.1f}/{no_tr['h']:.1f}"
          f"  (L with transition: {legs_at('l', tier_pe('l', transition=True))['sum']:.1f})")
    # g2 leverage (valuation-rules「g₂ 的杠杆 MUST 显式」), print only — see docstring: g2 is
    # pinned by the band edge, so a zone flip inside ±1pp reports the price sitting on a cut,
    # not a free g; +1pp above G_CAP / the band is shown as an illegal state, never a candidate.
    lever = []
    for delta in (-0.01, +0.01):
        g2_d = g2 + delta
        pe_d = {t: (perpetual_pe(g2_d, roe[t], r) if t == "l" else two_stage_pe(g1, n, g2_d, roe[t], r)) for t in TIERS}
        band_d = tuple(legs_at(t, pe_d[t])["sum"] for t in TIERS)
        legal = g2_d <= 0.06 + 1e-9 and all(inp["pe_own_min"] <= pe_d[t] <= inp["pe_own_max"] for t in TIERS)
        lever.append(f"{g2_d:.2%}: {band_d[0]:.1f}/{band_d[1]:.1f}/{band_d[2]:.1f} PE28 M/H "
                     f"{pe_d['m'] / (1 + g1):.2f}/{pe_d['h'] / (1 + g1):.2f}x zone={zone_of(inp['price'], *band_d)}"
                     f"{'' if legal else ' (above cap / band — not a legal state)'}")
    print("g2 leverage ±1pp (print only): " + " | ".join(lever) + f" | base {g2:.2%}: zone={zone}")
    g_mkt, ok = implied_g(inp["price"] / eps["m"], roe["m"], r)
    print(f"market-implied (P / 2027E mean = {inp['price'] / eps['m']:.1f}x, no transition): g = {g_mkt:.4f}"
          f" ({'well' if ok else 'ill'}-conditioned) — reference only")
    print(
        f"COUPE V_opt={v_opt:.2f} (H tier)  p_k={p_k['l']:.3f}/{p_k['m']:.3f}/{p_k['h']:.1f}  "
        f"p·V = {v_k['l']:.2f}/{v_k['m']:.2f}/{v_k['h']:.2f}  "
        f"zone+V = {L + v_k['l']:.1f}/{M + v_k['m']:.1f}/{H + v_k['h']:.1f}  "
        f"A'={(L + v_k['l'] + M + v_k['m']) / 2:.1f} B'={(M + v_k['m'] + H + v_k['h']) / 2:.1f}  "
        f"zone+V={zone_of(inp['price'], L + v_k['l'], M + v_k['m'], H + v_k['h'])}"
    )
    print(f"price={inp['price']:.2f} zone={zone}  P/L={inp['price'] / L - 1:+.1%}  P/M={inp['price'] / M - 1:+.1%}")
    if inp["price"] > H:
        print(f"  market-implied p=(P-H)/V_opt={(inp['price'] - H) / v_opt:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
