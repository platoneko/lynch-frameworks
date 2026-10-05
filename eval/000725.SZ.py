#!/usr/bin/env python3
"""000725.SZ (BOE) valuation eval — recompute anchors from frameworks/000725.SZ.md.

formula_id: boe_fy27_econdep_gordon_tail_v4

Economic-depreciation Gordon + depreciation-tail annuity (construction.md §5b
「经济折旧 Gordon」, 2026-10-05; this ticker is the rule's sample).  Panel lines
are booked over ~7-8 years but run 15-20+ (B1 Beijing Gen-5 since 2005, the
four Gen-8.5 lines since 2011-2017, all fully depreciated and still running),
so book profit swings with the accounting schedule, not with the business.
Two pieces, added:

  perpetual  — numerator = book NI + (accounting D - economic D) x (1 - t) x s,
               where accounting D is the SAME year's D as the book NI (so the
               depreciation roll-off inside later-year consensus never enters),
               economic D = gross cost by class / economic life; Gordon at
               basket 6 r = 13% with the payout-policy g (unchanged machinery).
  tail       — (economic D - maintenance capex) x (1 - t) x s for n years via
               annuity_factor (n = years until the Gen-8.5 cohort needs
               replacement); finite, never perpetuated.

Numerator year = FY2027 (nearest-year rule for commodity-type mid-cycle,
valuation-rules 2026-10-04: FY2026 carries ~39亿 of one-offs and is 3/4 gone).
FY2027 = current FY + 1 -> t = 1, no discount.  M / H = FY2027E consensus mean /
high (Eastmoney, 17 houses); L = FY2023 measured trough with its measured
two-year recovery (recovery_two_stage_pe), all three on the same economic-D
adjustment (each year with its own accounting D).

Entry-condition exclusion (construction.md §5b, 2026-10-05): the capex / D test
is run ex the two named expansion lines B16 / B20; their unspent capital is
then deducted from every tier at each line's own BOE ownership (B16 52.6%,
IR 2023-037; B20 79.31%, IR 2022-077), one year at r (spent over 2026H2-2027,
end-of-year like the tail).

V_opt = two items, summed at the H tier:
  B16    full-capacity increment above consensus (panel-options reading ①; its
         unspent capital is already in the deduction above, not deducted again)
  glass  glass-core substrate (valuation-rules「未建模期权」2026-10-05, peer-ruler
         axis _AXIS.glass-core-substrate): L / M quantity = Morgan Stanley
         2026-06-30 2028E revenue (single house); H = relayed full capacity x
         axis price; margins from the adjacent ABF layer; leg g2 from the axis;
         unspent line capital deducted; p_k = V_k / V_H.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here computes a zone or a market-implied r.

Run:  python3 frameworks/eval/000725.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import axis_path  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    annuity_factor, capped_payout_pe, check_branch, check_g_cap, check_r, g_cap, perpetual_pe,
    recovery_two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "000725.SZ.md"
GCS_AXIS = axis_path("_AXIS.glass-core-substrate")
GCS_SHARED = ("gcs_abs_rev_usd", "gcs_abs_cap_m2", "gcs_panel_m2", "gcs_price_h_usd",
              "gcs_opm_weak", "gcs_opm_strong", "gcs_yield_disc", "g2_gcs_src")
FORMULA_ID = "boe_fy27_econdep_gordon_tail_v4"
TIERS = ("l", "m", "h")
REQUIRED = [
    "shares", "bps", "ni_2026h1", "ni_ttm",
    "ni26_m", "ni26_h", "ni27_m", "ni27_h", "ni27_lo", "ni28_m",
    "ni_l", "ni_l_rec", "n_rec", "payout", "r_perp",
    "da_2023", "da_2025", "da_27", "da_nonfa",
    "gross_equip", "cip", "gross_bldg", "gross_other", "life_bldg", "life_other",
    "life_l", "life_m", "life_h", "tax", "parent_share",
    "maint_l", "maint_m", "maint_h", "cohort_year", "tail_start",
    "capex_ex_2025", "capex_ex_2026h1", "da_2026h1",
    "b16_units", "b16_asp_usd", "fx", "b16_margin_m", "b16_margin_h", "b16_interest", "b16_share",
    "b16_years", "v_opt",
    "b16_budget", "b16_progress", "b20_budget", "b20_progress", "b20_share", "unspent_years",
    "gcs_rev_ms", "gcs_wpm", "gcs_capex", "gcs_share", "gcs_years", *GCS_SHARED,
    "ocf_l", "ocf_m", "ocf_h", "interest", "band_lo", "band_hi", "pb_floor", "m_prev",
]


def policy_pe(roe: float, r: float, po: float, dg: float = 0.0) -> tuple[float, float, float]:
    """(PE, g used, g raw) at policy g = (1 - payout) x ROE (+ dg for the sensitivity row)."""
    g_raw = (1 - po) * roe + dg
    cap = g_cap(r)
    if g_raw <= cap:
        return perpetual_pe(g_raw, roe, r), g_raw, g_raw
    if roe <= r + 0.03:
        return capped_payout_pe(g_raw, roe, r, po), cap, g_raw
    return perpetual_pe(cap, roe, r), cap, g_raw


def econ_d(inp: dict[str, float], t: str) -> float:
    """Economic D (yuan/yr): gross cost by class / economic life; non-fixed-asset D&A kept at book."""
    return ((inp["gross_equip"] + inp["cip"]) / inp[f"life_{t}"]
            + inp["gross_bldg"] / inp["life_bldg"] + inp["gross_other"] / inp["life_other"]
            + inp["da_nonfa"])


def adj_ni(ni: float, da_same_year: float, ed: float, inp: dict[str, float]) -> float:
    """Perpetual numerator: book NI + (same-year accounting D - economic D) x (1 - t) x parent share."""
    return ni + (da_same_year - ed) * (1 - inp["tax"]) * inp["parent_share"]


def n_tail(inp: dict[str, float], t: str) -> int:
    """Years from tail_start until the Gen-8.5 cohort (mean in-service year) reaches its economic life."""
    return max(0, round(inp["cohort_year"] + inp[f"life_{t}"] - (inp["tail_start"] - 1)))


def tail(inp: dict[str, float], t: str, r: float) -> dict[str, float]:
    ed = econ_d(inp, t)
    gap = (ed - inp[f"maint_{t}"]) * (1 - inp["tax"]) * inp["parent_share"] / inp["shares"]
    n = n_tail(inp, t)
    af = annuity_factor(0.0, r, n)
    return dict(ed=ed, gap=gap, n=n, af=af, v=gap * af)


def unspent(x: dict[str, float]) -> float:
    """B16 + B20 budget not yet spent (yuan), from the 2026H1 progress ratios."""
    return x["b16_budget"] * (1 - x["b16_progress"]) + x["b20_budget"] * (1 - x["b20_progress"])


def unspent_owned(x: dict[str, float]) -> float:
    """BOE's own part of the unspent B16 + B20 capital (yuan): each line at its own BOE ownership."""
    return (x["b16_budget"] * (1 - x["b16_progress"]) * x["b16_share"]
            + x["b20_budget"] * (1 - x["b20_progress"]) * x["b20_share"])


def deduction(x: dict[str, float], r: float) -> float:
    """§5b entry-exclusion deduction, yuan/share: unspent B16 / B20 x each line's BOE share, discounted."""
    return unspent_owned(x) / (1 + r) ** x["unspent_years"] / x["shares"]


def deck(inp: dict[str, float], dg: float = 0.0, r: float | None = None,
         over: dict[str, float] | None = None) -> dict[str, dict[str, float]]:
    x = dict(inp, **(over or {}))
    sh, po = x["shares"], x["payout"]
    r = x["r_perp"] if r is None else r
    ded = deduction(x, r)
    out: dict[str, dict[str, float]] = {}
    for t in ("m", "h"):
        ed = econ_d(x, t)
        ni_adj = adj_ni(x[f"ni27_{t}"], x["da_27"], ed, x)
        eps = ni_adj / sh
        bps = x["bps"] + (1 - po) * (x[f"ni26_{t}"] - x["ni_2026h1"]) / sh
        roe = eps / bps
        pe, g, g_raw = policy_pe(roe, r, po, dg)
        tl = tail(x, t, r)
        perp = eps * pe
        out[t] = dict(ed=ed, ni_adj=ni_adj, eps=eps, eps_book=x[f"ni27_{t}"] / sh, bps=bps, roe=roe,
                      g=g, g_raw=g_raw, pe=pe, perp=perp, tail=tl, ded=ded, a=perp + tl["v"] - ded)
    ed = econ_d(x, "l")
    eps_l = adj_ni(x["ni_l"], x["da_2023"], ed, x) / sh
    eps_rec = adj_ni(x["ni_l_rec"], x["da_2025"], ed, x) / sh
    n = int(x["n_rec"])
    g1 = (eps_rec / eps_l) ** (1 / n) - 1
    pe_l = recovery_two_stage_pe(g1, n, out["m"]["g"], out["m"]["roe"], r)
    tl = tail(x, "l", r)
    out["l"] = dict(ed=ed, eps=eps_l, eps_rec=eps_rec, eps_book=x["ni_l"] / sh, g1=g1, pe=pe_l,
                    perp=eps_l * pe_l, tail=tl, ded=ded, a=eps_l * pe_l + tl["v"] - ded)
    return out


def book_deck(inp: dict[str, float]) -> tuple[float, float, float]:
    """Cross-check: the old ruler on the same FY2027 numerators — book NI, no economic D, no tail."""
    sh, po, r = inp["shares"], inp["payout"], inp["r_perp"]
    res = {}
    for t in ("m", "h"):
        eps = inp[f"ni27_{t}"] / sh
        bps = inp["bps"] + (1 - po) * (inp[f"ni26_{t}"] - inp["ni_2026h1"]) / sh
        pe, g, _ = policy_pe(eps / bps, r, po)
        res[t] = (eps * pe, g, eps / bps)
    eps_l = inp["ni_l"] / sh
    g1 = (inp["ni_l_rec"] / inp["ni_l"]) ** (1 / int(inp["n_rec"])) - 1
    lv = eps_l * recovery_two_stage_pe(g1, int(inp["n_rec"]), res["m"][1], res["m"][2], r)
    return lv, res["m"][0], res["h"][0]


def b16_option(inp: dict[str, float], margin: float, r: float) -> float:
    """B16 full-capacity increment, yuan/share: project NI x BOE share / r, discounted b16_years."""
    rev = inp["b16_units"] * inp["b16_asp_usd"] * inp["fx"]
    ni = (rev * margin - inp["b16_interest"]) * (1 - inp["tax"])
    return ni * inp["b16_share"] / r / (1 + r) ** inp["b16_years"] / inp["shares"]


def gcs_option(inp: dict[str, float], t: str, r: float, g2: float | None = None) -> dict[str, float]:
    """Glass-core substrate leg, yuan/share (floored at 0).

    L / M: Morgan Stanley 2028E revenue (single house).  H: relayed full capacity x axis
    price.  Margin: adjacent ABF layer — L weak, H strong minus discount, M midpoint.
    ROE on the line's own capital; ROE <= r -> 1/r, else perpetual_pe at the leg g2.
    Value at the realisation year, discounted gcs_years; unspent line capital
    discounted unspent_years; both at the BOE share of the line.
    """
    g2 = min(inp["g2_gcs_src"], g_cap(r)) if g2 is None else g2
    if t == "h":
        rev = inp["gcs_wpm"] * 12 * inp["gcs_price_h_usd"] * inp["fx"]
    else:
        rev = inp["gcs_rev_ms"]
    opm_h = inp["gcs_opm_strong"] - inp["gcs_yield_disc"]
    opm = {"l": inp["gcs_opm_weak"], "m": (inp["gcs_opm_weak"] + opm_h) / 2, "h": opm_h}[t]
    ni = rev * opm * (1 - inp["tax"])
    roe = ni / inp["gcs_capex"]
    pe = 1 / r if roe <= r else perpetual_pe(g2, roe, r)
    gross = ni * pe / (1 + r) ** inp["gcs_years"]
    cap = inp["gcs_capex"] / (1 + r) ** inp["unspent_years"]
    raw = (gross - cap) * inp["gcs_share"] / inp["shares"]
    return dict(rev=rev, opm=opm, ni=ni, roe=roe, pe=pe, g2=g2 if roe > r else 0.0,
                gross=gross * inp["gcs_share"] / inp["shares"], cap=cap * inp["gcs_share"] / inp["shares"],
                raw=raw, v=max(0.0, raw))


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
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    r, po, sh = inp["r_perp"], inp["payout"], inp["shares"]
    errors += check_r(r, "r_perp", baskets.get("r_perp"))

    d = deck(inp)
    L, M, H = (d[t]["a"] for t in TIERS)
    A, B = cut_points(L, M, H)
    errors += ladder("NI27 consensus", inp["ni27_lo"], inp["ni27_m"], inp["ni27_h"])
    errors += ladder("anchors", L, M, H)
    for t in ("m", "h"):
        errors += check_g_cap(d[t]["g"], r, f"g_{t}")
        errors += check_branch(d[t]["g"], d[t]["roe"], r, po, f"tier {t.upper()}") if d[t]["g"] == d[t]["g_raw"] else []
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- §5b guards --------------------------------------------------------------------------
    # Entry: capex (ex the two named expansion lines B16 / B20) / D&A < 0.6 for two periods.
    for name, cx, da in (("FY2025", inp["capex_ex_2025"], inp["da_2025"]),
                         ("2026H1", inp["capex_ex_2026h1"], inp["da_2026h1"])):
        if cx / da >= 0.6:
            errors.append(f"§5b entry: capex ex-B16/B20 / D&A {name} = {cx / da:.2f} >= 0.6")
    # Company: 2025 is the D&A peak; B16/B20 may add a little but not above it.
    if not inp["da_27"] <= inp["da_2025"]:
        errors.append("da_27 above the 2025 peak — contradicts company guidance (B12)")
    # No double count: the perpetual numerator is pre-D profit minus economic D, nothing else —
    # (i) recompute from first principles; (ii) it must not move when the tail inputs move.
    for t in ("m", "h"):
        pre_d = inp[f"ni27_{t}"] + inp["da_27"] * (1 - inp["tax"]) * inp["parent_share"]
        expect = (pre_d - d[t]["ed"] * (1 - inp["tax"]) * inp["parent_share"]) / sh
        if abs(expect - d[t]["eps"]) > 1e-9:
            errors.append(f"tier {t.upper()}: perpetual EPS != pre-D profit - economic D")
    bumped = deck(inp, over={"maint_l": 0.0, "maint_m": 0.0, "maint_h": 0.0, "tail_start": 2010})
    for t in TIERS:
        if abs(bumped[t]["perp"] - d[t]["perp"]) > 1e-9:
            errors.append(f"tier {t.upper()}: tail inputs leak into the perpetual segment")
        if not d[t]["tail"]["gap"] > 0:
            errors.append(f"tier {t.upper()}: economic D <= maintenance capex — no tail")
        if not d[t]["tail"]["v"] < d[t]["tail"]["gap"] / r:
            errors.append(f"tier {t.upper()}: tail is not finite (>= perpetuity)")
    # The FY2027->FY2028 consensus step is mostly roll-off; it must not sit in the perpetual numerator.
    roll_in_m = d["m"]["eps"] * sh - inp["ni27_m"]
    if abs(roll_in_m - (inp["da_27"] - d["m"]["ed"]) * (1 - inp["tax"]) * inp["parent_share"]) > 1:
        errors.append("M numerator carries an adjustment other than same-year (D - econ D)")

    # Entry exclusion: the deduction is the same in every tier and equals unspent B16 / B20 x line shares.
    ded = deduction(inp, r)
    for t in TIERS:
        if abs(d[t]["ded"] - ded) > 1e-12:
            errors.append(f"tier {t.upper()}: B16/B20 unspent deduction differs across tiers")
    if not 3.5e10 < unspent(inp) < 4.5e10:
        errors.append(f"B16/B20 unspent {unspent(inp) / 1e8:.1f}亿 outside the 350–450亿 sanity band")

    # --- peer-ruler axis (_AXIS.glass-core-substrate): shared rows must match the axis file --
    if GCS_AXIS.is_file():
        peer = parse_inputs(GCS_AXIS.read_text(encoding="utf-8"))
        for k in GCS_SHARED:
            if k not in peer or abs(peer[k] - inp[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.glass-core-substrate {peer.get(k)} — the leg ruler drifted")
    else:
        errors.append("frameworks/axes/glass-core-substrate.md missing — leg ruler unchecked")
    price_h = inp["gcs_abs_rev_usd"] / inp["gcs_abs_cap_m2"] * inp["gcs_panel_m2"]
    if abs(price_h - inp["gcs_price_h_usd"]) > 1.0:
        errors.append(f"gcs_price_h_usd {inp['gcs_price_h_usd']} != Absolics target / capacity x panel {price_h:.0f}")

    # --- option ------------------------------------------------------------------------------
    v_h = b16_option(inp, inp["b16_margin_h"], r)
    v_m = b16_option(inp, inp["b16_margin_m"], r)
    b16 = {"l": 0.0, "m": 0.5 * v_m, "h": v_h}          # p_M(B16) = 0.5 x V_M/V_H (B5)
    gcs = {t: gcs_option(inp, t, r) for t in TIERS}
    gcs_vh = gcs["h"]["v"]
    gcs_p = {t: (gcs[t]["v"] / gcs_vh if gcs_vh > 0 else 0.0) for t in TIERS}   # p_k = V_k / V_H
    v_tot = v_h + gcs_vh
    contrib = {t: b16[t] + gcs_p[t] * gcs_vh for t in TIERS}
    p_tot = {t: contrib[t] / v_tot for t in TIERS}
    if abs(v_tot - inp["v_opt"]) > 0.01:
        errors.append(f"v_opt: stated {inp['v_opt']} vs recomputed {v_tot:.3f} (B16 {v_h:.3f} + glass {gcs_vh:.3f})")
    fw = load_framework(FRAMEWORK)
    if fw.v_opt is None or abs(fw.v_opt - v_tot) > 0.01:
        errors.append(f"Outputs V_opt {fw.v_opt} vs recomputed {v_tot:.3f}")
    if fw.p_tiers is None or any(abs(a - p_tot[t]) > 0.005 for a, t in zip(fw.p_tiers, TIERS)):
        errors.append(f"Outputs p_L/p_M/p_H {fw.p_tiers} vs recomputed "
                      f"{p_tot['l']:.3f}/{p_tot['m']:.3f}/{p_tot['h']:.3f}")
    if not (0 <= p_tot["l"] <= p_tot["m"] <= p_tot["h"] == 1.0):
        errors.append("p_k ladder 0 <= p_L <= p_M <= p_H = 1 violated")

    # --- print -------------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    for t in TIERS:
        x, tl = d[t], d[t]["tail"]
        print(f"{t.upper()}: econ D {x['ed'] / 1e8:.1f}亿 (life {inp[f'life_{t}']}) "
              f"tail gap {tl['gap']:.4f}/sh x AF(n={tl['n']}) {tl['af']:.3f} = {tl['v']:.2f}")
    for t in ("m", "h"):
        x = d[t]
        note = f" (raw {x['g_raw']:.2%} capped → payout ruler)" if x["g"] != x["g_raw"] else ""
        print(f"{t.upper()}: NI27 book {inp[f'ni27_{t}'] / 1e8:.2f} → adj {x['ni_adj'] / 1e8:.2f}亿 EPS {x['eps']:.4f} "
              f"BPS(beg 2027) {x['bps']:.3f} ROE {x['roe']:.2%} g {x['g']:.2%}{note} PE {x['pe']:.2f} "
              f"perp {x['perp']:.2f} + tail {x['tail']['v']:.2f} = {x['a']:.2f}")
    x = d["l"]
    print(f"L: FY2023 adj EPS {x['eps']:.4f} → FY2025 adj {x['eps_rec']:.4f} g1 {x['g1']:.1%} n {int(inp['n_rec'])} "
          f"PE {x['pe']:.2f} perp {x['perp']:.2f} + tail {x['tail']['v']:.2f} = {x['a']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    em, eh, el = d["m"]["eps"], d["h"]["eps"], d["l"]["eps"]
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} width={(H - L) / (2 * M):.2f} V_opt/M={inp['v_opt'] / M:.2f}")
    print(f"  perpetual part: L/M {d['l']['perp'] / d['m']['perp']:.2f} (分子比 {el / em:.2f} x 倍数比 "
          f"{d['l']['pe'] / d['m']['pe']:.2f}); H/M {d['h']['perp'] / d['m']['perp']:.2f} (分子比 {eh / em:.2f} x "
          f"倍数比 {d['h']['pe'] / d['m']['pe']:.2f}); tail share of anchor L/M/H "
          f"{d['l']['tail']['v'] / L:.0%}/{d['m']['tail']['v'] / M:.0%}/{d['h']['tail']['v'] / H:.0%}")
    flat = [d[t]["eps"] * d["m"]["pe"] + d[t]["tail"]["v"] - d[t]["ded"] for t in TIERS]
    errors += ladder("flat-multiple", *flat)
    print(f"flat @ PE_M {d['m']['pe']:.2f} (+tails - deduction): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for dg in (-0.01, 0.01):
        s = deck(inp, dg)
        print(f"g ±1pp {dg:+.0%}: L {s['l']['a']:.2f} M {s['m']['a']:.2f} H {s['h']['a']:.2f}")
    sens = {
        "da_27 343 (draft line table)": {"da_27": 3.43e10},
        "da_27 386.7 (2025 peak)": {"da_27": inp["da_2025"]},
        "econ base ex CIP": {"cip": 0.0},
        "parent share 0.55": {"parent_share": 0.55},
        "life all 17.5": {"life_l": 17.5, "life_h": 17.5},
        "tail n -2 (cohort 2012.25)": {"cohort_year": inp["cohort_year"] - 2},
    }
    for name, over in sens.items():
        s = deck(inp, over=over)
        print(f"sens {name}: L {s['l']['a']:.2f} M {s['m']['a']:.2f} H {s['h']['a']:.2f}")
    b16u = inp["b16_budget"] * (1 - inp["b16_progress"])
    b20u = inp["b20_budget"] * (1 - inp["b20_progress"])
    print(f"B16/B20 unspent {unspent(inp) / 1e8:.1f}亿 = B16 {b16u / 1e8:.2f} x {inp['b16_share']} + "
          f"B20 {b20u / 1e8:.2f} x {inp['b20_share']} = {unspent_owned(inp) / 1e8:.2f}亿 / (1+r)^{inp['unspent_years']:g} "
          f"= -{ded:.4f}/sh (all tiers)")
    for name, over in {"deduction undiscounted": {"unspent_years": 0},
                       "unspent 436亿 (B16 630-315.9 + B20 122)": {"b16_progress": 1 - 3.141e10 / 6.3e10,
                                                                   "b20_progress": 1 - 1.22e10 / 2.9e10},
                       "deduction at group parent share": {"b16_share": inp["parent_share"],
                                                           "b20_share": inp["parent_share"]},
                       "no deduction": {"b16_progress": 1.0, "b20_progress": 1.0}}.items():
        s_ = deck(inp, over=over)
        print(f"sens {name}: L {s_['l']['a']:.2f} M {s_['m']['a']:.2f} H {s_['h']['a']:.2f}")

    # cross-checks and gate coordinates (disclosure only)
    bl, bm, bh = book_deck(inp)
    print(f"cross book Gordon FY2027 (old ruler, no econ D, no tail): {bl:.2f}/{bm:.2f}/{bh:.2f}")
    oe = [(inp[f"ocf_{t}"] - inp["interest"] - inp[f"maint_{t}"]) * inp["parent_share"] / sh / r - ded for t in TIERS]
    print(f"cross owner earnings (b) /r - B16/B20 deduction: {oe[0]:.2f}/{oe[1]:.2f}/{oe[2]:.2f}")
    eps27 = inp["ni27_m"] / sh
    print(f"③ M / FY2027E book EPS {eps27:.4f} = {M / eps27:.2f}x vs same-earnings band {inp['band_lo']}–{inp['band_hi']}x "
          f"({'inside' if inp['band_lo'] <= M / eps27 <= inp['band_hi'] else 'OUT'}; "
          f"{M / eps27 / inp['band_lo'] - 1:+.1%} vs band low)")
    print(f"③ M before deduction {M + ded:.2f} = {(M + ded) / eps27:.2f}x "
          f"({(M + ded) / eps27 / inp['band_lo'] - 1:+.1%} vs band low)")
    print(f"gate: M prev {inp['m_prev']} → {M:.2f} ({M / inp['m_prev'] - 1:+.1%}); book E_M/r {eps27 / r:.2f} "
          f"({eps27 / r / M - 1:+.0%}); econ E_M/r - ded {em / r - ded:.2f} ({(em / r - ded) / M - 1:+.0%}); "
          f"PB floor {inp['pb_floor'] * inp['bps']:.2f} ({inp['pb_floor'] * inp['bps'] / M - 1:+.0%}); "
          f"(b) M {oe[1]:.2f} ({oe[1] / M - 1:+.0%})")
    ttm, fy28 = inp["ni_ttm"] / sh, inp["ni28_m"] / sh
    for name, e in (("TTM", ttm), ("FY2027E mid (book)", eps27), ("FY2028E", fy28), ("FY2026E FY+0", inp["ni26_m"] / sh)):
        print(f"neutral band [A,B) on {name} EPS {e:.4f}: {A / e:.1f}x – {B / e:.1f}x")
    print(f"V_opt B16 increment: H-margin {v_h:.3f} M-margin {v_m:.3f} (p_M(B16) = {0.5 * v_m / v_h:.3f}; "
          f"credit L/M/H {b16['l']:.3f}/{b16['m']:.4f}/{b16['h']:.3f})")
    for t in TIERS:
        x = gcs[t]
        print(f"glass {t.upper()}: rev {x['rev'] / 1e8:.2f}亿 opm {x['opm']:.1%} NI {x['ni'] / 1e8:.2f}亿 "
              f"ROE {x['roe']:.1%} PE {x['pe']:.2f} (g {x['g2']:.1%}) value {x['gross']:.4f} - capital {x['cap']:.4f} "
              f"= {x['raw']:+.4f} → V {x['v']:.4f} p {gcs_p[t]:.3f}")
    print(f"glass H at g2 0: {gcs_option(inp, 'h', r, 0.0)['v']:.4f}; realisation 2029 (Citi): "
          f"{gcs_option(dict(inp, gcs_years=2), 'h', r)['v']:.4f}; share 0.641: "
          f"{gcs_option(dict(inp, gcs_share=inp['parent_share']), 'h', r)['v']:.4f}")
    be = inp["gcs_capex"] * r / ((1 - inp["tax"]) * inp["gcs_rev_ms"]) * (1 + r) ** (inp["gcs_years"] - inp["unspent_years"])
    print(f"glass break-even opm on MS 50亿 (ROE<=r branch): {be:.1%}")
    print(f"V_opt = B16 {v_h:.4f} + glass {gcs_vh:.4f} = {v_tot:.4f}; p_L/p_M/p_H = "
          f"{p_tot['l']:.4f}/{p_tot['m']:.4f}/{p_tot['h']:.4f}; corrected L/M/H "
          f"{L + contrib['l']:.2f}/{M + contrib['m']:.2f}/{H + contrib['h']:.2f}")
    print(f"PB floor {inp['pb_floor']}x BPS {inp['bps']} = {inp['pb_floor'] * inp['bps']:.2f} (disclosure only)")
    print(f"regime coordinate L: FY2023 adj EPS / r = {el / r:.2f}")
    print(f"§5b entry ratios: FY2025 {inp['capex_ex_2025'] / inp['da_2025']:.2f}, 2026H1 {inp['capex_ex_2026h1'] / inp['da_2026h1']:.2f}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
