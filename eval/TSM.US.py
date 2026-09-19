#!/usr/bin/env python3
"""TSM.US valuation eval — recompute anchors from frameworks/TSM.US.md.

formula_id: tsm_sotp_2027_two_stage_gordon_v8

Numerators: 2027E consensus EPS range (low/mean/high, 13 houses, USD/ADR).

Legs:
  - Advanced wafer: share_wafer × (1 - mat_of_wafer) × platform PE
  - Mature wafer:   share_wafer × mat_of_wafer × perpetual_pe(g_mat_wafer)
    mat_of_wafer is NOT the trailing mix.  Mature wafer *revenue dollars* are
    pinned at the as-of run-rate (2Q26 × 4 × mat_of_wafer_asof), so
    mat_of_wafer = mat_of_wafer_asof × 4 × rev_2q26_twd / rev_2027_twd — all
    2026→2027 revenue growth accrues to advanced.  g_mat_wafer = own measured
    mature-$ CAGR ceiling (~2%).
  - B1 advanced packaging: max(CoWoS×UV, adv EPS × platform PE)
  - B2 other backend: share_other × perpetual_pe(g_b2), no 2028 transition

Platform PE (advanced wafer + B1): L = perpetual_pe(g2); M/H = two_stage_pe(
g1_adv, n=1, g2).  g1_adv is the platform growth that reproduces the company
2028E consensus growth once mature/B2 only grow at their own g — the
consensus year must be fully expressed, not diluted by the slow legs.

Guardrail: the own realised forward-PE band is measured on COMPANY EPS, so it
bounds each tier's blended PE (tier price ÷ tier EPS), not the platform leg on
its own.  g2 = the value at which the H tier's blended PE touches pe_own_max.

r: every leg (advanced / mature wafer, B1 / B2) discounts at the basket it is
assigned to (valuation-rules「§r 篮子」) -- both legs sit in 篮 4 龙头制造, one
`r_perp` row whose source cell names the basket; `check_r` demands the row's
value equal that basket's, and `check_g_cap(g, r)` caps every perpetual g at
min(6%, r - 4%) (A25).  Implied r(P) is printed as a disclosure only.

COUPE: V_opt = H-tier OE×$450×share×npm×platform PE; p_k = V_k/V_H.

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
    check_branch,
    check_g_cap,
    check_r,
    check_transition_years,
    implied_g,
    payout_gap,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "TSM.US.md"
FORMULA_ID = "tsm_sotp_2027_two_stage_gordon_v8"
TOL = 0.15
P_TOL = 0.0005
MIN_R_MINUS_G = 0.02
NPM_TOL = 0.03

_V_OPT = re.compile(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*")
_P_TIERS = re.compile(
    r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
    r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)"
)
_T3_ROW = re.compile(
    r"\|\s*([LMH])\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)[^|]*\|\s*([0-9.]+)\s*\|\s*\*\*([0-9.]+)\*\*"
)

REQUIRED = [
    "price",
    "shares_adr",
    "equity",
    "rev_2q26_twd",
    "rev_2027_twd",
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
    "mat_of_wafer_asof",
    "npm_2027e_l",
    "npm_2027e_m",
    "payout_ttm",
    "g2",
    "g_mat_wafer",
    "g_b2",
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


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    # r is a basket, not a dial: the r row must name its basket in the Inputs
    # source cell and carry that basket's value (A25, valuation-rules「§r 篮子」).
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    for key in ("g2", "g_mat_wafer", "g_b2"):
        errs += check_g_cap(inp[key], inp["r_perp"], key)
        gap = inp["r_perp"] - inp[key]
        if gap <= 0:
            errs.append(f"perpetuity diverges: {key} >= r")
        elif gap < MIN_R_MINUS_G:
            errs.append(f"r - {key} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if inp["eps_2028_cons_twd"] <= inp["eps_2027_cons_twd"]:
        errs.append("2028E consensus below 2027E: the transition year has no growth to name")
    if inp["rev_2027_twd"] <= 4.0 * inp["rev_2q26_twd"]:
        errs.append("rev_2027_twd <= 2Q26 run-rate: pin-bridge for mature wafer share would not shrink")
    errs += ladder("numerator (2027E low/mean/high)", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    mech = inp["eps_2027_m"] * inp["npm_2027e_l"] / inp["npm_2027e_m"]
    if abs(mech / inp["eps_2027_l"] - 1.0) > NPM_TOL:
        errs.append(
            f"A17 mechanism: mean × {inp['npm_2027e_l']:g}/{inp['npm_2027e_m']:g} = {mech:.2f} "
            f"vs consensus low {inp['eps_2027_l']:g} (> {NPM_TOL:.0%} apart)"
        )
    share_sum = inp["share_wafer"] + inp["share_adv"] + inp["share_other"]
    if abs(share_sum - 1.0) > 1e-6:
        errs.append(f"leg shares sum {share_sum} != 1")
    if not (0.0 < inp["mat_of_wafer_asof"] < 0.5):
        errs.append(f"mat_of_wafer_asof={inp['mat_of_wafer_asof']} expected in (0, 0.5)")
    if not (inp["cowos_wpm_l"] < inp["cowos_wpm_m"] <= inp["cowos_wpm_h"]):
        errs.append("cowos_wpm ladder: expected L < M <= H")
    if abs(inp["asp_oe"] - 450.0) > 1e-9:
        errs.append(f"asp_oe={inp['asp_oe']} must be 450 (GS CPO OE BoM)")
    if not (inp["coupe_share_l"] < inp["coupe_share_m"] < inp["coupe_share_h"] <= 1.0):
        errs.append("coupe_share ladder: expected L < M < H <= 100%")
    # Mature / B2 g must sit at or below platform g2.
    for key in ("g_mat_wafer", "g_b2"):
        if inp[key] > inp["g2"] + 1e-9:
            errs.append(f"{key}={inp[key]:.4f} > g2={inp['g2']:.4f} — non-bottleneck leg cannot outgrow platform")
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
    baskets = parse_baskets(md)
    errors = sanity_checks(inp, baskets)

    r = inp["r_perp"]
    g2, g_mat, g_b2 = inp["g2"], inp["g_mat_wafer"], inp["g_b2"]
    n = int(inp["n_stage"])
    g1 = inp["eps_2028_cons_twd"] / inp["eps_2027_cons_twd"] - 1.0
    eps = {"l": inp["eps_2027_l"], "m": inp["eps_2027_m"], "h": inp["eps_2027_h"]}

    # Pin mature wafer $ at the 2Q26 run-rate → 2027E mature share of wafer shrinks with revenue growth.
    mat = inp["mat_of_wafer_asof"] * 4.0 * inp["rev_2q26_twd"] / inp["rev_2027_twd"]
    share_aw = inp["share_wafer"] * (1.0 - mat)
    share_mw = inp["share_wafer"] * mat

    # 2028E consensus growth is company-level.  With mature/B2 held at their own
    # g, the platform legs must grow faster than g1 for the company to reach it.
    w_plat = share_aw + inp["share_adv"]
    g1_adv = (g1 - share_mw * g_mat - inp["share_other"] * g_b2) / w_plat

    roe = {t: eps[t] * inp["shares_adr"] / inp["equity"] for t in TIERS}
    # g2 comes from a reverse-solve, so the Gordon branch must match the payout policy.
    errors += check_branch(g2, roe["m"], r, inp["payout_ttm"], "g2")

    def platform_pe(t: str, g2_x: float, transition: bool) -> float:
        if transition:
            return two_stage_pe(g1_adv, n, g2_x, roe[t], r)
        return perpetual_pe(g2_x, roe[t], r)

    pe_mat = {t: perpetual_pe(g_mat, roe[t], r) for t in TIERS}
    pe_b2 = {t: perpetual_pe(g_b2, roe[t], r) for t in TIERS}

    def capacity(wpm: float) -> float:
        return (wpm / 10000.0) * inp["uv_per_10k_wpm"] / inp["shares_adr"]

    def legs_at(t: str, p_plat: float, p_mature: float, p_other: float, mat_share: float = mat) -> dict[str, float]:
        e = eps[t]
        s_aw = inp["share_wafer"] * (1.0 - mat_share)
        s_mw = inp["share_wafer"] * mat_share
        paw = e * s_aw * p_plat
        pmw = e * s_mw * p_mature
        floor = e * inp["share_adv"] * p_plat
        cap = capacity(inp[f"cowos_wpm_{t}"])
        pb1 = max(cap, floor)
        pb2 = e * inp["share_other"] * p_other
        return {
            "Paw": paw,
            "Pmw": pmw,
            "Pb1": pb1,
            "Pb2": pb2,
            "cap": cap,
            "floor": floor,
            "sum": paw + pmw + pb1 + pb2,
        }

    def blended_pe(t: str, g2_x: float) -> float:
        return legs_at(t, platform_pe(t, g2_x, t != "l"), pe_mat[t], pe_b2[t])["sum"] / eps[t]

    # The own band is measured on company EPS, so the band edge is where the
    # tier's blended PE (not the platform leg alone) touches it.
    def g2_at_edge(t: str, target: float) -> float:
        lo, hi = -0.05, r - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if blended_pe(t, mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_g2 = {t: g2_at_edge(t, inp["pe_own_max"]) for t in TIERS}
    pe = {t: platform_pe(t, g2, t != "l") for t in TIERS}
    legs = {t: legs_at(t, pe[t], pe_mat[t], pe_b2[t]) for t in TIERS}
    L, M, H = (legs[t]["sum"] for t in TIERS)
    pe_blend = {t: legs[t]["sum"] / eps[t] for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe_blend[t] <= inp["pe_own_max"] + 1e-6):
            errors.append(
                f"{t.upper()} blended PE {pe_blend[t]:.2f}x outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
            )
    if not (L < M < H):
        errors.append(f"invariant L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    eps_t = (eps["l"], eps["m"], eps["h"])
    flat_errs, _ = flat_multiple_ladder(eps_t, pe["m"])
    errors += flat_errs
    flat = tuple(legs_at(t, pe["m"], pe_mat["m"], pe_b2["m"])["sum"] for t in TIERS)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    dec = decompose((L, M, H), (pe["l"], pe["m"], pe["h"]))

    errors += [f"axis: {e}" for e in check_cowos_supply(inp["cowos_wpm_m"])]
    errors += [f"optical axis: {e}" for e in check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"]))]
    coupe_rev = {t: inp[f"oe_{t}"] * inp["asp_oe"] * inp[f"coupe_share_{t}"] for t in TIERS}
    errors += [f"COUPE narrow: {e}" for e in check_optical_narrow_attach({t.upper(): coupe_rev[t] for t in TIERS})]

    # COUPE follows its own axis trajectory, not the wafer platform's: the M
    # world pays out 2027 OE (oe_m) and then steps to the axis 2028 volume
    # (oe_h) at the M-tier share, valued at t=2 on the steady g2 -- applying
    # the platform PE to 2027 COUPE NI would let the platform's +33% stand in
    # for a leg whose own named 2028 step is +525%.  L has no transition; H
    # is the cap (2028 volume as the numerator, A19) and keeps the platform PE.
    ni_per_adr = lambda oe, share: oe * inp["asp_oe"] * share * inp["npm_coupe"] / inp["shares_adr"]  # noqa: E731
    v_k = {
        "l": ni_per_adr(inp["oe_l"], inp["coupe_share_l"]) * pe["l"],
        "m": (
            ni_per_adr(inp["oe_m"], inp["coupe_share_m"])
            + ni_per_adr(inp["oe_h"], inp["coupe_share_m"]) * perpetual_pe(g2, roe["m"], r)
        )
        / (1.0 + r),
        "h": ni_per_adr(inp["oe_h"], inp["coupe_share_h"]) * pe["h"],
    }
    v_opt = v_k["h"]
    p_k = {t: v_k[t] / v_opt for t in TIERS}

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

    print(f"formula_id={FORMULA_ID}")
    print(
        f"g1(company)={g1:.4f} g1_adv(platform)={g1_adv:.4f} n={n} g2={g2:g} "
        f"g_mat_wafer={g_mat:g} g_b2={g_b2:g} r={r:g} (篮 {baskets.get('r_perp')}, all legs)"
    )
    print(
        f"mature pin: asof={inp['mat_of_wafer_asof']:.0%} of wafer × 2Q26 run-rate {4 * inp['rev_2q26_twd'] / 1e9:.0f}B "
        f"/ 2027E rev {inp['rev_2027_twd'] / 1e9:.0f}B TWD → mat_of_wafer_2027={mat:.2%}  "
        f"EPS shares aw={share_aw:.2%} mw={share_mw:.2%} b1={inp['share_adv']:.0%} b2={inp['share_other']:.0%}"
    )
    print(
        f"tier EPS = {eps['l']:.2f}/{eps['m']:.2f}/{eps['h']:.2f}  "
        f"ROE = {roe['l']:.3f}/{roe['m']:.3f}/{roe['h']:.3f}"
    )
    for t in TIERS:
        lg = legs[t]
        print(
            f"{t.upper()}: plat {pe[t]:.2f}x mat {pe_mat[t]:.2f}x b2 {pe_b2[t]:.2f}x blended {pe_blend[t]:.2f}x  "
            f"aw {lg['Paw']:.1f} mw {lg['Pmw']:.1f} B1 {lg['Pb1']:.1f} "
            f"(cap {lg['cap']:.1f}/fl {lg['floor']:.1f}) B2 {lg['Pb2']:.1f} = {lg['sum']:.1f}"
        )
    print(f"L={L:.1f} M={M:.1f} H={H:.1f} A={A:.1f} B={B:.1f}")
    print(
        f"2028-basis aw M/H: {eps['m'] * share_aw * (1 + g1_adv):.2f} x {pe['m'] / (1 + g1_adv):.2f}x | "
        f"{eps['h'] * share_aw * (1 + g1_adv):.2f} x {pe['h'] / (1 + g1_adv):.2f}x | "
        f"mw M {eps['m'] * share_mw:.2f} x {pe_mat['m']:.2f}x (no g1)"
    )
    print(f"flat @ M: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    print(
        f"own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] on BLENDED PE, band-edge g2: "
        f"L {band_edge_g2['l']:.4%} / M {band_edge_g2['m']:.4%} / H {band_edge_g2['h']:.4%} "
        f"-> g2 {g2:.2%} {'<=' if g2 <= min(band_edge_g2.values()) + 1e-9 else '>'} binding"
    )
    modelled, gap = payout_gap(g2, roe["m"], inp["payout_ttm"])
    print(
        f"branch: g2 {g2:.2%} at ROE_M {roe['m']:.1%} implies payout {modelled:.0%} vs paid {inp['payout_ttm']:.0%} "
        f"(gap {gap:+.0%}; monotonic zone ROE>>r, sign only)"
    )
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | "
        f"H/M {dec['hm']:.3f} | width {(H - L) / (2 * M):.3f} | "
        f"V_opt/M {v_opt / M:.3f} | mw/M {legs['m']['Pmw'] / M:.3f} | B2/M {legs['m']['Pb2'] / M:.3f}"
    )

    def band_with(g2_x: float = g2, mat_share: float = mat, transition: bool = True) -> tuple[float, float, float]:
        return tuple(
            legs_at(t, platform_pe(t, g2_x, transition and t != "l"), pe_mat[t], pe_b2[t], mat_share)["sum"]
            for t in TIERS
        )

    def fmt(b: tuple[float, float, float]) -> str:
        a_x, b_x = cut_points(*b)
        return f"{b[0]:.1f}/{b[1]:.1f}/{b[2]:.1f} (A {a_x:.1f} / B {b_x:.1f}) zone={zone_of(inp['price'], *b)}"

    print(f"cross-check no transition (aw/B1): {fmt(band_with(transition=False))}")
    print(f"cross-check no pin (as-of {inp['mat_of_wafer_asof']:.0%} held into 2027E): {fmt(band_with(mat_share=inp['mat_of_wafer_asof']))}")
    n7 = inp.get("n7_of_wafer_asof")
    if n7 is not None:
        n7_mat = (inp["mat_of_wafer_asof"] + n7) * 4.0 * inp["rev_2q26_twd"] / inp["rev_2027_twd"]
        print(f"cross-check N7 reclassed to mature (pinned share {n7_mat:.2%}): {fmt(band_with(mat_share=n7_mat))}")
    # v7 read the band as a cap on the platform leg alone; kept as a coordinate.
    lo, hi = -0.05, r - 1e-4
    for _ in range(200):
        mid = (lo + hi) / 2
        if platform_pe("h", mid, True) < inp["pe_own_max"]:
            lo = mid
        else:
            hi = mid
    g2_leg = (lo + hi) / 2
    print(f"cross-check band capping platform leg (v7 reading): g2={g2_leg:.2%} -> {fmt(band_with(g2_x=g2_leg))}")
    lever = []
    for delta in (-0.01, +0.01):
        g2_d = g2 + delta
        legal = g2_d <= 0.06 + 1e-9 and all(
            inp["pe_own_min"] <= blended_pe(t, g2_d) <= inp["pe_own_max"] + 1e-6 for t in TIERS
        )
        lever.append(f"{g2_d:.2%}: {fmt(band_with(g2_x=g2_d))}{'' if legal else ' (illegal)'}")
    zone_down = zone_of(inp["price"], *band_with(g2_x=g2 - 0.01))
    flip_note = f"⚠敏感区 (-1pp -> {zone_down}, disclosure only)" if zone_down != zone else "(no flip: not a 敏感区)"
    print("g2 ±1pp (mw/B2 PE fixed): " + " | ".join(lever) + f" | base zone={zone}  {flip_note}")
    # Implied r(P): single-stage approximation r ≈ g2 + (r - g2)·M/P, a direction
    # reading against the basket r (SOTP carries the transition and mature legs,
    # so the structural reverse-solve below is the finer number).  Disclosure only.
    r_impl = g2 + (r - g2) * M / inp["price"]
    print(f"implied r(P) ≈ {r_impl:.1%} (single-stage approx) vs basket r {r:.1%} ({r_impl - r:+.1%}, disclosure only)")
    g_mkt, ok = implied_g(inp["price"] / eps["m"], roe["m"], r)
    lo, hi = -0.05, r - 1e-4
    for _ in range(200):
        mid = (lo + hi) / 2
        if band_with(g2_x=mid)[1] < inp["price"]:
            lo = mid
        else:
            hi = mid
    print(
        f"market-implied (P/2027E mean={inp['price'] / eps['m']:.1f}x): single-leg Gordon g={g_mkt:.4f} "
        f"({'well' if ok else 'ill'}-conditioned) | SOTP structure, platform g2 at M=price: {(lo + hi) / 2:.4f}"
    )
    print(
        f"COUPE V_opt={v_opt:.2f} p_k={p_k['l']:.3f}/{p_k['m']:.3f}/{p_k['h']:.1f}  "
        f"zone+V={L + v_k['l']:.1f}/{M + v_k['m']:.1f}/{H + v_k['h']:.1f}  "
        f"A'={(L + v_k['l'] + M + v_k['m']) / 2:.1f} B'={(M + v_k['m'] + H + v_k['h']) / 2:.1f}  "
        f"zone+V={zone_of(inp['price'], L + v_k['l'], M + v_k['m'], H + v_k['h'])}"
    )
    print(f"price={inp['price']:.2f} zone={zone} P/L={inp['price'] / L - 1:+.1%} P/M={inp['price'] / M - 1:+.1%}")
    if inp["price"] > H:
        print(f"  market-implied p=(P-H)/V_opt={(inp['price'] - H) / v_opt:.2f}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
