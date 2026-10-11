#!/usr/bin/env python3
"""TSM.US valuation eval — recompute anchors from frameworks/TSM.US.md.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」): which zone a
quote falls in is derived live by the daily digest and the app, so nothing
here reads a price.

formula_id: tsm_sotp_2027_two_stage_gordon_v10

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

ROE (v9): tier EPS ÷ the numerator year's OPENING BPS (end-2026), the 2Q26
book rolled over 2H26 unbooked earnings at the growth-required retention
b1 = g/ROE (company g1 for M/H, g2 for L; valuation-rules 裁决表 ② as of
2026-09-21), solved in closed form.  v8 divided 2027 earnings by the
mid-2026 book; year-end-book and actual-payout rolls are both wrong and kept
only as cross-check rows in the framework.

Cross band (A27, not the main ruler, not in _INDEX): the PB-ROIC "machine" —
book rolled to end-2028 on company capex guidance, new capital earning the
gross cash return net of its own 5-year depreciation (lagged one year), the
2028 book priced at the own 5-year PB quartiles and discounted two years.

r: every leg (advanced / mature wafer, B1 / B2) discounts at the basket it is
assigned to (valuation-rules「§r 篮子」) -- both legs sit in 篮 4 龙头制造, one
`r_perp` row whose source cell names the basket; `check_r` demands the row's
value equal that basket's, and `check_g_cap(g, r)` caps every perpetual g at
min(6%, r - 4%) (A25).

COUPE (v10, valuation-rules「未建模期权」2026-10-03): every tier values its
2028 axis volume (OE×$450×share×npm) in 2028 on the platform leg's steady
ruler perpetual_pe(g2, ROE_k, r) -- no stage-1 step at the realisation year --
and discounts (1+r)^-(t_coupe - 2027) to the numerator year.  V_opt = V_H;
p_k = V_k/V_H.

Run:  python3 frameworks/eval/TSM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
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
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "TSM.US.md"
FORMULA_ID = "tsm_sotp_2027_two_stage_gordon_v10"
LISTING_CCY = "USD"
TOL = 0.15
P_TOL = 0.0005
MIN_R_MINUS_G = 0.02
NUM_YEAR = 2027  # numerator year (A20 / A21)
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
    "t_coupe",
    "fx_twd",
    "eps_2026_m",
    "ni_1h26_twd",
    "payout_3y",
    "ic_2q26_twd",
    "capex_2026",
    "capex_2027",
    "capex_2028",
    "da_2026e",
    "da_2027e",
    "da_2028e",
    "cash_return_gross",
    "dep_life",
    "pb_5y_q1",
    "pb_5y_med",
    "pb_5y_q3",
    "n_disc",
]
TIERS = ("l", "m", "h")
_CROSS_BAND = re.compile(r"对照带（PB-ROIC 机器尺）：L′ ([0-9.]+) / M′ ([0-9.]+) / H′ ([0-9.]+)")


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
    # A15: the M margin is the one the consensus mean implies, not the 1H26 run-rate.
    npm_implied = inp["eps_2027_m"] * inp["shares_adr"] * inp["fx_twd"] / inp["rev_2027_twd"]
    if abs(npm_implied - inp["npm_2027e_m"]) > 0.005:
        errs.append(f"npm_2027e_m={inp['npm_2027e_m']:g} vs consensus-implied {npm_implied:.4f} (A15)")
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
    if inp["t_coupe"] <= NUM_YEAR:
        errs.append(f"t_coupe={inp['t_coupe']:g} must be after the numerator year {NUM_YEAR}")
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

    # ROE = E_{n+1} / B_n: the numerator year's earnings over its OPENING book
    # (= end-2026), not today's 2Q26 book and not the year-end book (that would
    # put retention the year has not yet earned into the denominator;
    # valuation-rules 裁决表 ② as of 2026-09-21).  The 2Q26 book is
    # rolled over the 2H26 earnings not yet booked (2026E consensus minus 1H26
    # actual) at the GROWTH-REQUIRED retention b1 = g/ROE -- the same b
    # two_stage_pe charges in stage 1 -- not at the actual payout complement.
    # With ROE = eps / BPS and BPS = E0 + b1·N the fixed point is closed-form:
    # BPS = E0 / (1 - g·N/eps).  M/H roll at the company g1 (the legs' g sum to
    # it); L has no window and rolls at g2.  Actual retention beyond b1 is the B
    # bucket, printed as a disclosure, not put into the book.
    ni_2h26 = inp["eps_2026_m"] * inp["shares_adr"] - inp["ni_1h26_twd"] / inp["fx_twd"]
    bps_2q26 = inp["equity"] / inp["shares_adr"]
    unbooked = {t: ni_2h26 / inp["shares_adr"] for t in TIERS}  # per ADR, 2H26 only (opening-2027 book)
    g_roll = {"l": g2, "m": g1, "h": g1}
    bps_open_2027 = {t: bps_2q26 / (1.0 - g_roll[t] * unbooked[t] / eps[t]) for t in TIERS}
    roe = {t: eps[t] / bps_open_2027[t] for t in TIERS}
    b1 = {t: g_roll[t] / roe[t] for t in TIERS}
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"{t.upper()}: growth-required retention b1={b1[t]:.2f} outside (0,1) — book roll needs external equity")
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * unbooked[t] for t in TIERS}  # USD/ADR, modelled-as-distributed
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

    # The axis tiers are all 2028 volume.  Every tier values its 2028 COUPE NI
    # in 2028 on the platform leg's steady ruler (g2, the tier's ROE, basket r)
    # and discounts to the 2027 numerator year (valuation-rules「未建模期权」,
    # construction §7c-1, 2026-10-03).  The platform PE would carry the
    # wafer business's +33% 2028 step into the realisation year -- a stage-1
    # opened at realisation, which the rule forbids (v9 did that for L and H).
    ni_per_adr = lambda oe, share: oe * inp["asp_oe"] * share * inp["npm_coupe"] / inp["shares_adr"]  # noqa: E731
    disc_coupe = (1.0 + r) ** (inp["t_coupe"] - NUM_YEAR)
    ni_coupe = {t: ni_per_adr(inp[f"oe_{t}"], inp[f"coupe_share_{t}"]) for t in TIERS}
    pe_coupe = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    v_k = {t: ni_coupe[t] * pe_coupe[t] / disc_coupe for t in TIERS}
    v_k_v9 = {
        "l": ni_coupe["l"] * pe["l"],
        "m": ni_coupe["m"] * pe_coupe["m"] / (1.0 + r),
        "h": ni_coupe["h"] * pe["h"],
    }
    v_opt = v_k["h"]
    p_k = {t: v_k[t] / v_opt for t in TIERS}

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
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
        return f"{b[0]:.1f}/{b[1]:.1f}/{b[2]:.1f} (A {a_x:.1f} / B {b_x:.1f})"

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
    print("g2 ±1pp (mw/B2 PE fixed): " + " | ".join(lever))
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves r_perp
    # 1:1 on every leg -- platform (aw / B1 floor), mature wafer and B2 multiples are
    # re-priced; EPS, ROE, g1_adv/g2 and the CoWoS capacity value stay put.
    # Disclosure only: the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r
        saved = r
        r = r + dr
        try:
            return tuple(
                legs_at(t, platform_pe(t, g2, t != "l"), perpetual_pe(g_mat, roe[t], r), perpetual_pe(g_b2, roe[t], r))["sum"]
                for t in TIERS
            )
        finally:
            r = saved

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    print(
        f"COUPE V_opt={v_opt:.2f} p_k={p_k['l']:.3f}/{p_k['m']:.3f}/{p_k['h']:.1f}  "
        f"zone+V={L + v_k['l']:.1f}/{M + v_k['m']:.1f}/{H + v_k['h']:.1f}  "
        f"A'={(L + v_k['l'] + M + v_k['m']) / 2:.1f} B'={(M + v_k['m'] + H + v_k['h']) / 2:.1f}"
    )
    print(
        f"COUPE chain: NI/ADR {ni_coupe['l']:.3f}/{ni_coupe['m']:.3f}/{ni_coupe['h']:.3f} x perpetual_pe(g2 {g2:.2%}, ROE_k) "
        f"{pe_coupe['l']:.2f}/{pe_coupe['m']:.2f}/{pe_coupe['h']:.2f}x / 1.1^{int(inp['t_coupe']) - NUM_YEAR} "
        f"= {v_k['l']:.2f}/{v_k['m']:.2f}/{v_k['h']:.2f} | v9 (L/H x platform PE, undiscounted) "
        f"{v_k_v9['l']:.2f}/{v_k_v9['m']:.2f}/{v_k_v9['h']:.2f}"
    )
    print(
        f"ROE basis: BPS_2027 = {bps_open_2027['l']:.1f}/{bps_open_2027['m']:.1f}/{bps_open_2027['h']:.1f} USD/ADR (opening 2027 = end-2026) "
        f"(2Q26 book {bps_2q26:.1f} rolled at b1 = g/ROE = {b1['l']:.2f}/{b1['m']:.2f}/{b1['h']:.2f}, "
        f"g_roll {g_roll['l']:.2%}/{g_roll['m']:.2%}/{g_roll['h']:.2%}); "
        f"v8 basis (2Q26 book) would read ROE {eps['l'] * inp['shares_adr'] / inp['equity']:.1%}/"
        f"{eps['m'] * inp['shares_adr'] / inp['equity']:.1%}/{eps['h'] * inp['shares_adr'] / inp['equity']:.1%}"
    )
    print(
        f"B bucket (modelled-as-distributed, actually retained): actual retention {ret_actual:.0%} − b1 → "
        f"{excess_cash['l']:.1f}/{excess_cash['m']:.1f}/{excess_cash['h']:.1f} USD/ADR over 2H26 "
        f"(disclosure only; not a leg, not in BPS)"
    )

    # --- A27 cross band: PB-ROIC machine (user ruler 2026-09-21; not the main ruler) ---
    # Capital: operating IC (equity + debt - cash) grows by company capex net of
    # D&A; new capital earns the gross cash return minus its own straight-line
    # depreciation, and only from the year after it is spent (fab lead time).
    # Earnings base = 1H26 annualised (existing capacity held, pricing power).
    # Book rolls at the 3-year mean retention; the 2028 book is priced at the
    # own 5-year PB quartiles and discounted n_disc years at the basket r.
    fx = inp["fx_twd"]
    ret = ret_actual  # the machine ruler projects the ACTUAL book (no ROE in its multiple)
    base_ni = 2.0 * inp["ni_1h26_twd"] / fx
    c_net = inp["cash_return_gross"] - 1.0 / inp["dep_life"]
    d_ic_2h26 = (inp["capex_2026"] - inp["da_2026e"]) / 2.0
    d_ic_2027 = d_ic_2h26 + (inp["capex_2027"] - inp["da_2027e"])
    d_ic_2028 = d_ic_2027 + (inp["capex_2028"] - inp["da_2028e"])
    ni_2027_mach = base_ni + c_net * d_ic_2h26          # capital spent in 2H26 productive in 2027
    ni_2028_mach = base_ni + c_net * d_ic_2027          # capital through 2027 productive in 2028
    equity_2028 = inp["equity"] + ret * (base_ni / 2.0 + ni_2027_mach + ni_2028_mach)
    bps_2028 = equity_2028 / inp["shares_adr"]
    eps_2028_mach = ni_2028_mach / inp["shares_adr"]
    roe_2028_mach = eps_2028_mach / bps_2028
    pb_q = (inp["pb_5y_q1"], inp["pb_5y_med"], inp["pb_5y_q3"])
    disc = (1.0 + r) ** inp["n_disc"]
    cross = tuple(bps_2028 * pb / disc for pb in pb_q)
    # PB at ROE_2028 read back as a perpetual g: PB = (ROE - g)/(r - g) → g = (ROE - r·PB)/(1 - PB).
    g_impl_pb = tuple((roe_2028_mach - r * pb) / (1.0 - pb) for pb in pb_q)
    cm = _CROSS_BAND.search(out_sec)
    if cm is None:
        errors.append("对照带（PB-ROIC 机器尺）L/M/H not stated in Outputs")
    else:
        for lab, said, got in zip("LMH", (float(x) for x in cm.groups()), cross):
            if abs(said - got) > TOL:
                errors.append(f"对照带 {lab}: stated {said} vs {got:.4f}")
    if not (cross[0] < cross[1] < cross[2]):
        errors.append(f"对照带 invariant L<M<H failed: {cross}")
    ca, cb = cut_points(*cross)
    print(
        f"A27 machine: base NI {base_ni / 1e9:.1f}B, new capital ΔIC 2H26/27/28 = {d_ic_2h26 / 1e9:.1f}/{d_ic_2027 / 1e9:.1f}/{d_ic_2028 / 1e9:.1f}B "
        f"× (c {inp['cash_return_gross']:.0%} − 1/{inp['dep_life']:g}) = {c_net:.0%} lagged → NI 2027/28 {ni_2027_mach / 1e9:.1f}/{ni_2028_mach / 1e9:.1f}B, "
        f"EPS28 {eps_2028_mach:.2f}, BPS28 {bps_2028:.1f}, ROE28 {roe_2028_mach:.1%}"
    )
    print(
        f"A27 cross band (PB 5y q1/med/q3 {pb_q[0]:g}/{pb_q[1]:g}/{pb_q[2]:g}, ÷(1+r)^{inp['n_disc']:g}): "
        f"{cross[0]:.1f}/{cross[1]:.1f}/{cross[2]:.1f} (A {ca:.1f} / B {cb:.1f}) | "
        f"implied perpetual g at ROE28: {g_impl_pb[0]:.1%}/{g_impl_pb[1]:.1%}/{g_impl_pb[2]:.1%} (cap 6%)"
    )

    # Only a clean run feeds the daily digest (output/rates/).
    if not errors:
        write_rf_readings("TSM.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
