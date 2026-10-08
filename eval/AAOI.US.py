#!/usr/bin/env python3
"""AAOI.US (应用光电 / Applied Optoelectronics) valuation eval — recompute
anchors from frameworks/AAOI.US.md.

frameworks/AAOI.US.md is the source of truth; this script re-derives L/M/H,
A/B, the ELSFP option and the candidate band from the §3 Inputs table and exits
1 on mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」),
so nothing here reads a quote.

formula_id: aaoi_fy27_gordon_basket_pair_floor_elsfp_opt_v1

Whole-company ruler (one reportable segment, no segment profit or assets, so
the CATV leg cannot be split — valuation-rules「归篮触发分腿」keeps the whole-
company ruler at the largest leg's basket and discloses the bias; the CATV
split is printed as a cross only).  Numerator FY2027 = furthest year with a
>=2-house consensus range (yfinance +1y, 5 houses), non-GAAP less SBC/share.
No transition year (no FY28 with >=2 houses).

Basket PAIR (valuation-rules「篮子对」, A15): today 篮 7 15% (FY25 single
customer 53.1%, top two 81.9%), terminal 篮 4 10%; n = 0, so the journey rate
only sets G_cap, discounts the option and is the merge fallback, and the risk
of never reaching the diversified steady state lives in k (A17), recomputed
here as 0.5 x (1 - PE@r_journey / PE@r_terminal).  g2 is the peer-ruler axis
value `_AXIS.pluggable-module` (cross-file checked).

L is the asset floor (A3, user decision 2026-10-06): the FY18-style digestion
scenario prints a negative EPS, so L = FY27 opening book per share.  Every
anchor then takes the holder-optimal lower of the diluted and the debt reading
of the 2030 convertible (A20).

Option (A13): ELSFP named capacity x Raymond James low price x the
`_AXIS.inp-laser` normal-period margin and g (realised 2028 > shortage end
2027), valued on this ticker's ruler at H, discounted one year at the journey
rate, less full-capacity capital.  p_L / p_M / p_H are constants, never Inputs.

Run:  python3 frameworks/eval/AAOI.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_basket_pair,
    check_branch,
    check_g_cap,
    check_k_declared,
    check_transition_years,
    payout,
    payout_gap,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "AAOI.US.md"
AXIS_PLUG = REPO_ROOT / "frameworks" / "axes" / "pluggable-module.md"
AXIS_LASER = REPO_ROOT / "frameworks" / "axes" / "inp-laser.md"
FORMULA_ID = "aaoi_fy27_gordon_basket_pair_floor_elsfp_opt_v1"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
NUM_YEAR = 2027
N_STAGE = 0  # no FY28 with >=2 houses
FAIL_SHARE = 0.5  # A17: 无概率锚·拍值 — chance of never reaching the diversified steady state
K_TOL = 0.01
P_TIERS = (0.0, 0.0, 1.0)  # A13: no sell-side volume -> option only in H
MACRO_G = 0.04
TIERS = ("L", "M", "H")

REQUIRED = [
    "eps_fy27_l", "eps_fy27_m", "eps_fy27_h", "rev_fy26_cons", "rev_fy27_m", "rev_fy27_h",
    "nm_fy25", "rev_cut_l", "sbc_q2", "shares_dil", "equity_h1", "atm_post", "atm_fee",
    "warrant_vested", "warrant_strike", "conv_carry", "conv_principal", "conv_rate",
    "ni_h2_cons", "r_journey", "r_terminal", "r_catv_cross", "g2", "catv_rev_27",
    "k_l", "k_m", "k_h", "payout_obs", "elsfp_units_month", "elsfp_price", "t_opt",
    "tax_opt", "ebit_margin_inp_normal", "g2_inp_laser_normal", "t_shortage_end",
    "cap_intensity", "rj_eps_runrate", "rj_eps_runrate_hi",
]


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def axis_check(path: Path, pairs: dict[str, str], inp: dict[str, float], label: str) -> list[str]:
    """Peer-ruler axis rows (contracts.md「同业尺轴」): single source = the axis file."""
    if not path.is_file():
        return [f"{path.name} missing — {label} unchecked"]
    ax = parse_inputs(path.read_text(encoding="utf-8"))
    errs = []
    for mine, theirs in pairs.items():
        if theirs not in ax or abs(ax[theirs] - inp[mine]) > 1e-9:
            errs.append(f"{mine} {inp[mine]:g} != {label} {theirs} {ax.get(theirs)} — the ruler drifted")
    return errs


def sanity(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    for row in ("r_journey", "r_terminal"):
        if row not in baskets:
            e.append(f"{row}: Inputs source cell names no 篮 N (A15)")
    if "r_catv_cross" in baskets:
        e.append("r_catv_cross is a disclosure-only r and must not name a 篮 N")
    e += check_basket_pair(inp["r_journey"], inp["r_terminal"], "r",
                           baskets.get("r_journey"), baskets.get("r_terminal"))
    e += check_k_declared(inp["r_journey"], inp["r_terminal"],
                          (inp["k_l"], inp["k_m"], inp["k_h"]), "k")
    # G_cap stays keyed to the JOURNEY basket (篮子对 判据 3).
    e += check_g_cap(inp["g2"], inp["r_journey"], "g2")
    if inp["r_terminal"] - inp["g2"] < MIN_R_MINUS_G:
        e.append("r_terminal - g2 < 2%: at the pole")
    e += check_g_cap(inp["g2_inp_laser_normal"], inp["r_journey"], "g2_inp_laser_normal")
    e += check_transition_years(N_STAGE, 0, "n")
    if not (inp["eps_fy27_l"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]):
        e.append("FY27 consensus range must be ordered low < mean < high")
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (cyclical)")
    if inp["t_opt"] <= inp["t_shortage_end"]:
        e.append("t_opt inside the shortage period: the option must take the shortage margin, not the normal one")
    if inp["t_opt"] <= NUM_YEAR:
        e.append("option realisation year must lie after the numerator year")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


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
    errors = sanity(inp, baskets)
    errors += axis_check(AXIS_PLUG, {"g2": "g2_pluggable"}, inp, "_AXIS.pluggable-module")
    errors += axis_check(AXIS_LASER, {
        "ebit_margin_inp_normal": "ebit_margin_inp_normal",
        "g2_inp_laser_normal": "g2_inp_laser_normal",
        "t_shortage_end": "t_shortage_end",
    }, inp, "_AXIS.inp-laser")

    sh, g2 = inp["shares_dil"], inp["g2"]
    sbc_ps = 4 * inp["sbc_q2"] / sh
    conv_sh = inp["conv_principal"] * inp["conv_rate"] / 1000

    def lower_of(v: float) -> float:
        """A20: holder-optimal convertible — lower of diluted and debt per-share readings."""
        return min(v, (v * sh - inp["conv_principal"]) / (sh - conv_sh))

    eq0 = (inp["equity_h1"] + inp["atm_post"] * (1 - inp["atm_fee"])
           + inp["warrant_vested"] * inp["warrant_strike"] + inp["conv_carry"])

    def tier(e: float, g: float, r: float, eq_extra: float = 0.0, shares: float = sh):
        bps = (eq0 + eq_extra + inp["ni_h2_cons"]) / shares
        for _ in range(200):
            roe = e / bps
            nxt = (eq0 + eq_extra + inp["ni_h2_cons"] * min(1.0, g / roe)) / shares
            if abs(nxt - bps) < 1e-12:
                break
            bps = nxt
        roe = e / bps
        return bps, roe, perpetual_pe(g, roe, r)

    r_j, r_t = inp["r_journey"], inp["r_terminal"]
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    eps = {"M": inp["eps_fy27_m"] - sbc_ps, "H": inp["eps_fy27_h"] - sbc_ps}

    # ---- L: digestion scenario, then the asset floor (A3) ----
    eps_l_scn = inp["rev_fy26_cons"] * (1 - inp["rev_cut_l"]) * inp["nm_fy25"] / sh - sbc_ps
    floor = (eq0 + inp["ni_h2_cons"]) / sh
    if eps_l_scn >= 0:
        errors.append(f"L scenario EPS {eps_l_scn:.3f} >= 0 — the floor rule (A3) no longer applies; reprice L")

    def band(rj: float, rt: float, g: float = g2, ks: dict | None = None):
        ks = k if ks is None else ks
        out, info = {"L": lower_of(floor)}, {}
        for t in ("M", "H"):
            bps, roe, pe = tier(eps[t], g, rt)
            pre = eps[t] * pe
            out[t] = lower_of(pre * (1 - ks[t]))
            info[t] = (bps, roe, pe, perpetual_pe(g, roe, rj), pre)
        return out, info

    anchors, info = band(r_j, r_t)
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    for t in ("M", "H"):
        bps, roe, pe, pe_j, _ = info[t]
        if roe - r_t < 0.03:
            errors.append(f"{t}: ROE {roe:.3f} not in the monotone domain at r_terminal {r_t:g}")
        errors += check_branch(g2, roe, r_t, inp["payout_obs"], f"g2@{t}")
        k_derived = FAIL_SHARE * (1 - pe_j / pe)
        if abs(k_derived - k[t]) > K_TOL:
            errors.append(f"k_{t.lower()} {k[t]} vs derived {k_derived:.3f} (A17)")
    if not eps["M"] * info["M"][2] < eps["H"] * info["M"][2]:
        errors.append("flat ladder: M >= H at the M multiple (A2e-2c)")

    # ---- Option (A13) ----
    rev_opt = 12 * inp["elsfp_units_month"] * inp["elsfp_price"]  # 百万 USD (百万只 x USD)
    ni_opt = rev_opt * inp["ebit_margin_inp_normal"] * (1 - inp["tax_opt"])
    eps_opt = ni_opt / sh
    roe_h = info["H"][1]
    pe_opt = perpetual_pe(inp["g2_inp_laser_normal"], roe_h, r_t)
    val_t = eps_opt * pe_opt * (1 - k["H"])
    disc = (1 + r_j) ** (inp["t_opt"] - NUM_YEAR)
    capital = rev_opt * inp["cap_intensity"] / sh
    v_opt = val_t / disc - capital
    plus_v = tuple(x + p * v_opt for x, p in zip((L, M, H), P_TIERS))

    def v_at(price: float) -> float:
        rv = 12 * inp["elsfp_units_month"] * price
        return (rv * inp["ebit_margin_inp_normal"] * (1 - inp["tax_opt"]) / sh * pe_opt
                * (1 - k["H"]) / disc - rv * inp["cap_intensity"] / sh)

    # ---- Candidate band (A19): RJ run-rate as one FY28 transition year ----
    # A capacity run-rate is a level, not a growth rate: M′ reaches the midpoint, H′ is
    # capped at the source's top (construction §7h), so H's FY27 ramp is not counted twice.
    g1_by = {"M": inp["rj_eps_runrate"] / inp["eps_fy27_m"] - 1,
             "H": max(0.0, inp["rj_eps_runrate_hi"] / inp["eps_fy27_h"] - 1)}
    cand = {"L": L}
    for t in ("M", "H"):
        roe = info[t][1]
        cand[t] = lower_of(eps[t] * two_stage_pe(g1_by[t], 1, g2, roe, r_t) * (1 - k[t]))
    if not cand["L"] < cand["M"] < cand["H"]:
        errors.append("candidate band not ordered")

    # ---- Reconcile stated Outputs ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    said_v = first_float(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    p_line = re.search(r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec)
    if p_line is None or tuple(float(x) for x in p_line.groups()) != P_TIERS:
        errors.append(f"Outputs p_L/p_M/p_H must state {P_TIERS}")
    cl = re.search(r"L′ = \*\*([0-9.]+)\*\* · M′ = \*\*([0-9.]+)\*\* · H′ = \*\*([0-9.]+)\*\*", out_sec)
    if cl is None:
        errors.append("candidate band line not found")
    else:
        for t, said in zip(TIERS, (float(x) for x in cl.groups())):
            if abs(said - cand[t]) > TOL:
                errors.append(f"{t}′: stated {said} vs recomputed {cand[t]:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r pair: journey {r_j:g} (篮 {baskets.get('r_journey')}) -> terminal {r_t:g} (篮 {baskets.get('r_terminal')}); "
          f"g2 {g2:.2%} (_AXIS.pluggable-module; named macro {MACRO_G:.0%}); n = {N_STAGE}")
    print(f"FY27 opening equity {eq0 + inp['ni_h2_cons']:.1f} (eq0 {eq0:.1f} + H2 NI {inp['ni_h2_cons']}) / {sh} = floor {floor:.2f};"
          f" SBC/share {sbc_ps:.3f}; convertible {conv_sh:.3f}M shares")
    print(f"L: scenario EPS {eps_l_scn:.3f} (< 0) -> floor {floor:.2f} -> holder-optimal {L:.2f}")
    for t in ("M", "H"):
        bps, roe, pe, pe_j, pre = info[t]
        mod, gap = payout_gap(g2, roe, inp["payout_obs"])
        print(f"{t}: EPS {eps[t]:.4f} BPS {bps:.2f} ROE {roe:.3f} PE {pe:.2f} (PE@journey {pe_j:.2f}, "
              f"k derived {FAIL_SHARE * (1 - pe_j / pe):.3f}) -> {pre:.2f} x (1-k {k[t]}) = {pre * (1 - k[t]):.2f}"
              f" -> holder-optimal {anchors[t]:.2f}  [payout_gap: model {mod:.1%} vs paid {inp['payout_obs']:.0%}]")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat ladder @ M {info['M'][2]:.2f}x x (1-k_M): "
          f"{eps['M'] * info['M'][2] * (1 - k['M']):.2f}/{eps['H'] * info['M'][2] * (1 - k['M']):.2f} (L floor, n/a)")
    num_hm = eps["H"] / eps["M"]
    print(f"L/M {L / M:.3f} (num n/a, floor) | H/M {H / M:.3f} = num {num_hm:.3f} x rest {H / M / num_hm:.3f}"
          f" | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"ELSFP option: rev {rev_opt:.0f} x margin {inp['ebit_margin_inp_normal']} x (1-{inp['tax_opt']}) = NI {ni_opt:.1f}"
          f" -> EPS {eps_opt:.3f} x PE {pe_opt:.2f} (g {inp['g2_inp_laser_normal']:.0%}, ROE_H {roe_h:.3f},"
          f" payout {payout(inp['g2_inp_laser_normal'], roe_h):.3f}) x (1-k_H) = {val_t:.2f} / {disc:.2f} = {val_t / disc:.2f}"
          f" - capital {capital:.2f} = V_opt {v_opt:.2f}")
    print(f"  +V {plus_v[0]:.2f}/{plus_v[1]:.2f}/{plus_v[2]:.2f}  A' {(plus_v[0] + plus_v[1]) / 2:.2f}"
          f" B' {(plus_v[1] + plus_v[2]) / 2:.2f}; price $750 -> {v_at(750):.2f}, $1000 -> {v_at(1000):.2f}")
    print(f"candidate (RJ run-rate level: M -> {inp['rj_eps_runrate']} g1 {g1_by['M']:+.1%}, H capped at "
          f"{inp['rj_eps_runrate_hi']} g1 {g1_by['H']:+.1%}; n=1; stage-1 payout M {1 - g1_by['M'] / info['M'][1]:+.2f}"
          f" / H {1 - g1_by['H'] / info['H'][1]:+.2f}): {cand['L']:.2f}/{cand['M']:.2f}/{cand['H']:.2f}"
          f"  A' {(cand['L'] + cand['M']) / 2:.2f} B' {(cand['M'] + cand['H']) / 2:.2f}")
    single, _ = band(r_j, r_j, ks={"L": 0, "M": 0, "H": 0})
    print(f"basket-pair reference (single journey basket {r_j:g}, k = 0): "
          f"{single['L']:.2f}/{single['M']:.2f}/{single['H']:.2f}")
    t4, _ = band(r_t, r_t, ks={"L": 0, "M": 0, "H": 0})
    print(f"  single terminal basket {r_t:g}, k = 0: {t4['L']:.2f}/{t4['M']:.2f}/{t4['H']:.2f}")
    for g in (g2 - 0.01, g2 + 0.01, MACRO_G):
        b_, _ = band(r_j, r_t, g)
        print(f"  sens g2={g:.2%}: {b_['L']:.2f}/{b_['M']:.2f}/{b_['H']:.2f}")
    print("视同派出、实际留存 (D 桶, 窗口 FY27 一年; k 前 / k 后 equal, retention k 0): "
          + " ".join(f"{t} {(1 - inp['payout_obs'] - g2 / info[t][1]) * eps[t]:.2f}" for t in ("M", "H")))
    for t, rev in (("M", inp["rev_fy27_m"]), ("H", inp["rev_fy27_h"])):
        s = inp["catv_rev_27"] / rev
        bps, roe, pe, _, _ = info[t]
        sotp = (eps[t] * (1 - s) * pe * (1 - k[t])
                + eps[t] * s * perpetual_pe(0.0, roe, inp["r_catv_cross"]))
        v = lower_of(sotp)
        print(f"CATV split cross {t}: share {s:.3f} at r {inp['r_catv_cross']:g} g 0 -> {v:.2f} ({v / anchors[t] - 1:+.1%})")
    # Third ATM fully drawn (A1): ~$600M at ~$120 -> +5.0M shares; consensus EPS diluted pro rata.
    atm3, px = 600 * (1 - inp["atm_fee"]), 120.0
    sh3 = sh + 600 / px
    dil = {t: eps[t] * sh / sh3 for t in ("M", "H")}
    vals = []
    for t in ("M", "H"):
        bps, roe, pe = tier(dil[t], g2, r_t, atm3, sh3)
        vals.append(pe * dil[t] * (1 - k[t]))
    print(f"  sens 3rd ATM fully drawn (+{600 / px:.1f}M sh, +{atm3:.0f} equity): "
          f"floor {(eq0 + atm3 + inp['ni_h2_cons']) / sh3:.2f} M {vals[0]:.2f} H {vals[1]:.2f} (pre-convertible)")

    # ---- r_f readings (_AXIS.rates USD): both rates of the pair move 1:1; the floor stays ----
    def band_rf(dr: float) -> tuple[float, float, float]:
        b_, _ = band(r_j + dr, r_t + dr)
        return b_["L"], b_["M"], b_["H"]

    rf = rf_block(LISTING_CCY, {"r_journey": r_j, "r_terminal": r_t}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("AAOI.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
