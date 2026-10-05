#!/usr/bin/env python3
"""0148.HK (Kingboard Holdings) valuation eval — recompute anchors from frameworks/0148.HK.md.

frameworks/0148.HK.md is the source of truth; this script re-parses its §3 Inputs
table, recomputes L/M/H / A/B and the candidate band, and exits 1 on mismatch.
The framework carries no current price (AGENTS.md「现价 — 禁写契约」): this
script neither reads a price nor derives a zone.

formula_id: kingboard_holdco_sotp_point_v2

Main ruler: holding-company SOTP, legs added one by one (no blended r):

  1. KLHL (1888.HK) x stake -- KLHL equity = laminate operating value
     (NOPAT on the FY2025 segment net assets x a segment return, basket 6)
     + KLHL's own securities / investment property at a discount
     - KLHL net debt - KLHL dividend payable.  Valued on fundamentals, never on
     1888's market cap (0189.HK precedent: the sub's earnings are already in
     the consolidated accounts; a listed quote would move the anchors daily).
  2. PCB (basket 4), 3. chemicals (basket 6), 4. rental property (basket 6):
     after-tax earnings x Gordon multiple; all three sit in the peak-shaped
     domain (ROIC < r - 3pp) so the multiple is 1/r (valuation-rules 峰形区).
  5. properties under development, holdco securities, JV / associate:
     book or fair value x (1 - d).
  6. minus holdco net debt (group less KLHL), the declared-unpaid FY2025
     final+special dividend, and capitalised holdco overhead.

Cycle semantics (A1, point): the M tier is the laminate segment's 2017-2025 mean
return on opening segment net assets applied to today's base (asset base has
changed, valuation-rules「中枢…资产基数变动」).  L = the FY2023 trough return
plus the measured 2-year recovery (recovery_two_stage_pe).  H = the FY2026
consensus + FY2027 point estimates, then a linear 2-year fade to mid (the
decay_two_stage_pe mirror, implemented locally until the library has it).
The regime reading (peak / trough held forever at the steady multiple) is
printed as the comparison band and pressure coordinates, not the main band.

Candidate band (A10, AI shortage extended): same formula, the H path gains
Citi's single-source FY2028; L' = L, M' = M.

V_opt (A9, valuation-rules「未建模期权」2026-10-05): AI special glass fabric on
_AXIS.ai-glass-fabric and HVLP / RTF copper foil on _AXIS.hvlp-copper-foil; the
axis rows are checked value by value against the axis files.  See option_values().
V_opt = V_H; p_k = V_k / V_H.  Never enters L/M/H.

Sanity checks beyond the anchor comparison:
  * every r row names its basket and equals it (parse_baskets + check_r);
    g2 under g_cap; the laminate M multiple is the Gordon multiple of its
    named g2 at the mid ROIC; the other legs' ROIC really is < r - 3pp
  * SAME-SOURCE: the laminate / PCB / chemical returns equal the figures
    recomputed from the segment tables in HIST below (mean, trough, peak)
  * flat-multiple ladder (A2e-2c): the laminate numerators step L < M < H
  * k (視同派出, A12): k_l <= k_m <= k_h and k_h = 1 - V_M/V_H (pre-k)
  * L < M < H, candidate L' < M' < H'

Run:  python3 frameworks/eval/0148.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    perpetual_pe,
    recovery_two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    parse_baskets,
    parse_inputs,
)
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "0148.HK.md"
FORMULA_ID = "kingboard_holdco_sotp_point_v2"
LISTING_CCY = "HKD"
TOL = 0.05
RET_TOL = 0.0005  # returns are stated to 4 decimals

# Segment results and segment net assets (segment assets - segment liabilities),
# HK$ million, from the 0148 annual reports' note "Segment information" (b).
# Results: FY2016-2025; net assets: year-ends 2016-2024 (opening base for 2017-2025).
HIST_RESULT = {  # year: (laminates, PCBs, chemicals)
    2016: (2465, 378, 313), 2017: (3953, 693, 966), 2018: (2937, 474, 1378),
    2019: (2185, 487, 735), 2020: (3313, 1066, 1157), 2021: (8320, 1057, 3976),
    2022: (2307, 1059, 2465), 2023: (1572, 1316, 606), 2024: (2105, 1360, 595),
    2025: (2837, 1396, 468),
}
HIST_NET_ASSETS = {
    2016: (14001, 8497, 5679), 2017: (15545, 8857, 6103), 2018: (14528, 10395, 5593),
    2019: (13464, 11059, 5135), 2020: (16612, 11309, 2752), 2021: (19576, 13056, 2680),
    2022: (16026, 12835, 3431), 2023: (15395, 12949, 5727), 2024: (15412, 13478, 8522),
}
RET_YEARS = range(2017, 2026)

REQUIRED = [
    "shares", "stake_kl", "tax", "tax_prop",
    "na_lam", "na_pcb", "na_chem", "ip_hold",
    "ret_lam_l", "ret_lam_m", "g1_lam_rec", "n_rec", "e_lam_26", "e_lam_27", "e_lam_28c", "n_fade",
    "ret_pcb_l", "ret_pcb_m", "ret_pcb_h",
    "chem_l", "chem_m", "chem_h",
    "rent_l", "rent_m", "rent_h", "noi_margin",
    "r_lam", "r_pcb", "r_chem", "r_prop", "r_hq", "g2_lam", "pe_lam_m",
    "kl_sec", "kl_ip", "kl_netdebt", "kl_divpay",
    "pud", "sec_hold", "jv", "hold_netdebt", "divpay", "hq_cost",
    "d_sec_l", "d_sec_m", "d_sec_h", "d_prop_l", "d_prop_m", "d_prop_h",
    "payout_obs", "window", "k_l", "k_m", "k_h",
]


AXES = Path(__file__).resolve().parents[1] / "axes"
# Rows the framework copies from its peer-ruler axes (contracts.md「同业尺轴」): one source per field.
AXIS_ROWS = {
    "ai-glass-fabric": ["px_ai_gf_l", "px_ai_gf_m", "px_ai_gf_h", "nm_ai_gf_l", "nm_ai_gf_m", "nm_ai_gf_h",
                        "gm_ai_gf_ref", "m_per_t_ai_gf", "capex_per_m_ai_gf"],
    "hvlp-copper-foil": ["pt_hvlp_l", "pt_hvlp_m", "pt_hvlp_h", "capex_per_t_hvlp"],
}
OPT_REQUIRED = [
    "gf_citi_share", "np_gp_kl", "gf_kilns_total", "gf_kilns_new", "gf_kilns_unspent", "gf_t_per_kiln",
    "gf_yield", "gf_years", "cu_tons", "cu_yield", "cu_years", "fx_cny_hkd",
] + [k for ks in AXIS_ROWS.values() for k in ks]


def option_values(inp: dict[str, float]) -> dict:
    """V_opt per tier, HK$ per 0148 share (A9; valuation-rules「未建模期权」2026-10-05).

    Size: L / M = the ticker's own sell-side quantity (Citi's AI-cloth gross-profit share of
    its FY2028 KLHL forecast, gross profit -> revenue at the axis gross margin, scaled to the
    kilns not already in the base); H = the larger of that path and full capacity
    (new kilns x tons x m/t x yield x axis price).  HVLP has no own sell-side quantity:
    L / M = 0, H = capacity tons x yield x axis profit per ton.
    Value: the ticker's ruler -- laminate leg r (basket 6) and g2, ROE on the leg's own
    capital (capacity x axis capex), 1/r below r - 3pp; valued in the realisation year,
    discounted to the numerator year, minus the capital not yet spent (one year out),
    x stake / shares.  Net margins / per-ton profits on the axes are after tax.
    """
    r, g2, fx = inp["r_lam"], inp["g2_lam"], inp["fx_cny_hkd"]
    keep = inp["gf_kilns_new"] / inp["gf_kilns_total"]
    gp28 = inp["e_lam_28c"] / inp["np_gp_kl"]
    citi_rev = inp["gf_citi_share"] * gp28 / inp["gm_ai_gf_ref"] * keep
    cap_m = inp["gf_kilns_new"] * inp["gf_t_per_kiln"] * inp["m_per_t_ai_gf"]  # metres / yr
    k_gf = cap_m * inp["capex_per_m_ai_gf"] * fx / 1e9
    k_cu = inp["cu_tons"] * inp["capex_per_t_hvlp"] * 1e4 * fx / 1e9

    def leg(np_: float, k: float, years: float, unspent: float, rev: float) -> dict[str, float]:
        if np_ <= 0:
            return {"rev": rev, "np": 0.0, "k": k, "roe": 0.0, "pe": 0.0, "value": 0.0,
                    "years": years, "unspent": 0.0, "v1888": 0.0, "ps": 0.0}
        roe = np_ / k
        pe = perpetual_pe(g2, roe, r) if roe > r - 0.03 else 1.0 / r
        value = np_ * pe
        unspent_pv = unspent / (1 + r)
        v = value / (1 + r) ** years - unspent_pv
        return {"rev": rev, "np": np_, "k": k, "roe": roe, "pe": pe, "value": value, "years": years,
                "unspent": unspent_pv, "v1888": v, "ps": v * inp["stake_kl"] / inp["shares"]}

    out: dict = {}
    unspent_gf = k_gf * inp["gf_kilns_unspent"] / inp["gf_kilns_new"]
    for x in "lmh":
        rev = citi_rev
        if x == "h":
            cap_rev = cap_m * inp["gf_yield"] * inp["px_ai_gf_h"] * fx / 1e9
            out["cap_rev_h"], out["citi_rev"] = cap_rev, citi_rev
            out["citi_px"] = citi_rev / (cap_m * inp["gf_yield"] * fx / 1e9)
            rev = max(cap_rev, citi_rev)
        gf = leg(rev * inp[f"nm_ai_gf_{x}"], k_gf, inp["gf_years"], unspent_gf, rev)
        cu_np = inp["cu_tons"] * inp["cu_yield"] * inp[f"pt_hvlp_{x}"] * 1e4 * fx / 1e9 if x == "h" else 0.0
        cu = leg(cu_np, k_cu, inp["cu_years"], k_cu, 0.0)
        out[x] = {"gf": gf, "cu": cu, "total": gf["ps"] + cu["ps"]}
    return out


def seg_returns(i: int) -> list[float]:
    """Segment result / opening segment net assets for leg i, FY2017-2025."""
    return [HIST_RESULT[y][i] / HIST_NET_ASSETS[y - 1][i] for y in RET_YEARS]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED + OPT_REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    t, tp = inp["tax"], inp["tax_prop"]

    # --- baskets and g caps -------------------------------------------------
    baskets = parse_baskets(md)
    r_keys = ("r_lam", "r_pcb", "r_chem", "r_prop", "r_hq")
    for k in r_keys:
        if k not in baskets:
            errors.append(f"{k}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[k], k, baskets.get(k))
    errors += check_g_cap(inp["g2_lam"], inp["r_lam"], "g2_lam")

    # --- same-source: the returns are the segment tables, not a pick ---------
    lam_ret, pcb_ret = seg_returns(0), seg_returns(1)
    chem_res = [HIST_RESULT[y][2] / 1000 for y in range(2016, 2026)]
    same = {
        "ret_lam_m": sum(lam_ret) / len(lam_ret),
        "ret_lam_l": HIST_RESULT[2023][0] / HIST_NET_ASSETS[2022][0],
        "ret_pcb_l": min(pcb_ret),
        "ret_pcb_m": sum(pcb_ret) / len(pcb_ret),
        "ret_pcb_h": max(pcb_ret),
        "g1_lam_rec": (HIST_RESULT[2025][0] / HIST_RESULT[2023][0]) ** 0.5 - 1,
    }
    for k, v in same.items():
        if abs(inp[k] - v) > RET_TOL:
            errors.append(f"same-source: {k}={inp[k]} but the segment tables give {v:.4f}")
    for k, v in (("chem_l", min(chem_res)), ("chem_m", sum(chem_res) / len(chem_res)), ("chem_h", max(chem_res))):
        if abs(inp[k] - v) > 0.001:
            errors.append(f"same-source: {k}={inp[k]} but FY2016-2025 chemicals results give {v:.4f}")

    # --- leg earnings (HK$ bn, after tax) and domains ------------------------
    lam_mid = inp["na_lam"] * inp["ret_lam_m"] * (1 - t)
    roe_lam = lam_mid / inp["na_lam"]
    chem_mid = inp["chem_m"] * (1 - t)
    roe_chem = chem_mid / inp["na_chem"]

    def pe(g: float, roe: float, r: float) -> float:
        """Gordon multiple; peak-shaped domain (ROE <= r - 3pp) is capped at 1/r with g = 0."""
        return perpetual_pe(g, roe, r) if roe > r - 0.03 else 1.0 / r

    pe_lam = perpetual_pe(inp["g2_lam"], roe_lam, inp["r_lam"])
    if abs(pe_lam - inp["pe_lam_m"]) > TOL:
        errors.append(f"pe_lam_m={inp['pe_lam_m']} is not the Gordon multiple {pe_lam:.3f} of g2_lam at ROE {roe_lam:.4f}")
    if roe_lam < inp["r_lam"] + 0.03:
        errors.append(f"laminate mid ROIC {roe_lam:.4f} is not in the monotone domain the Formula claims")
    for name, roe, r in (("pcb", inp["ret_pcb_h"] * (1 - t), inp["r_pcb"]),
                         ("chem", roe_chem, inp["r_chem"]),
                         ("rent", inp["rent_h"] * inp["noi_margin"] * (1 - tp) / inp["ip_hold"], inp["r_prop"])):
        if roe > r:
            errors.append(f"{name}: ROIC {roe:.4f} > r {r} — the 1/r cap in the Formula no longer applies")

    def fade(path: list[float], mid: float, n: int, pe_mid: float, r: float) -> float:
        """Explicit path, then linear fade to mid over n years, tail at the mid multiple.
        Mirror of recovery_two_stage_pe: stage-1 payout 100%, tail valued at t = len+n-1."""
        es = list(path) + [path[-1] + (mid - path[-1]) * j / n for j in range(1, n)]
        pv = sum(e / (1 + r) ** (i + 1) for i, e in enumerate(es))
        return pv + mid * pe_mid / (1 + r) ** len(es)

    def lam_value(x: str, dr: float, h_path: list[float] | None = None) -> float:
        r = inp["r_lam"] + dr
        if x == "l":
            e_l = inp["na_lam"] * inp["ret_lam_l"] * (1 - t)
            return e_l * recovery_two_stage_pe(inp["g1_lam_rec"], int(inp["n_rec"]), inp["g2_lam"], roe_lam, r)
        if x == "m":
            return lam_mid * perpetual_pe(inp["g2_lam"], roe_lam, r)
        path = h_path or [inp["e_lam_26"], inp["e_lam_27"]]
        return fade(path, lam_mid, int(inp["n_fade"]), perpetual_pe(inp["g2_lam"], roe_lam, r), r)

    def chem_value(x: str, dr: float) -> float:
        r = inp["r_chem"] + dr
        pe_mid = pe(0.0, roe_chem, r)
        if x == "l":
            e = inp["chem_l"] * (1 - t)
            g1 = (inp["chem_m"] / inp["chem_l"]) ** 0.5 - 1
            return e * recovery_two_stage_pe(g1, int(inp["n_rec"]), 0.0, roe_chem, r)
        if x == "m":
            return chem_mid * pe_mid
        return fade([inp["chem_h"] * (1 - t)], chem_mid, int(inp["n_fade"]), pe_mid, r)

    def tier(x: str, dr: float = 0.0, lam_v: float | None = None) -> dict[str, float]:
        d_sec, d_prop = inp[f"d_sec_{x}"], inp[f"d_prop_{x}"]
        lv = lam_value(x, dr) if lam_v is None else lam_v
        klhl = lv + inp["kl_sec"] * (1 - d_sec) + inp["kl_ip"] * (1 - d_prop) - inp["kl_netdebt"] - inp["kl_divpay"]
        legs = {
            "klhl": inp["stake_kl"] * klhl,
            "pcb": inp["na_pcb"] * inp[f"ret_pcb_{x}"] * (1 - t) / (inp["r_pcb"] + dr),
            "chem": chem_value(x, dr),
            "rent": inp[f"rent_{x}"] * inp["noi_margin"] * (1 - tp) / (inp["r_prop"] + dr),
            "pud": inp["pud"] * (1 - d_prop),
            "sec": inp["sec_hold"] * (1 - d_sec),
            "jv": inp["jv"] * (1 - d_sec),
            "debt": -inp["hold_netdebt"] - inp["divpay"] - inp["hq_cost"] * (1 - t) / (inp["r_hq"] + dr),
        }
        ps = {k: v / inp["shares"] for k, v in legs.items()}
        # Attributable after-tax earnings for the 視同派出 line (securities income and
        # holdco interest roughly offset and are left out; A12).
        e_lam1 = {"l": inp["na_lam"] * inp["ret_lam_l"] * (1 - t), "m": lam_mid, "h": inp["e_lam_26"]}[x]
        eps = (inp["stake_kl"] * e_lam1 + inp["na_pcb"] * inp[f"ret_pcb_{x}"] * (1 - t)
               + inp[f"chem_{x}"] * (1 - t) + inp[f"rent_{x}"] * inp["noi_margin"] * (1 - tp)
               - inp["hq_cost"] * (1 - t)) / inp["shares"]
        return {**ps, "klhl_eq": klhl, "pre_k": sum(ps.values()), "eps": eps}

    def excess(x: str, eps: float) -> float:
        """Retained-but-deemed-paid cash per share over the D-bucket window (A12)."""
        return (1 - inp["payout_obs"]) * eps * inp["window"]

    def anchors(dr: float = 0.0, h_path: list[float] | None = None) -> tuple[float, float, float]:
        out = []
        for x in "lmh":
            tv = tier(x, dr, lam_value(x, dr, h_path) if x == "h" else None)
            out.append(tv["pre_k"] - inp[f"k_{x}"] * excess(x, tv["eps"]))
        return tuple(out)

    tiers = {x: tier(x) for x in "lmh"}
    L, M, H = anchors()
    A, B = (L + M) / 2, (M + H) / 2
    if not L < M < H:
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")

    # --- k: cyclical ordering and the ①b top discount -------------------------
    if not inp["k_l"] <= inp["k_m"] <= inp["k_h"]:
        errors.append("k must satisfy k_l <= k_m <= k_h (valuation-rules「視同派出」)")
    k_h_rule = 1 - tiers["m"]["pre_k"] / tiers["h"]["pre_k"]
    if abs(inp["k_h"] - k_h_rule) > 0.005:
        errors.append(f"k_h={inp['k_h']} but ①b 1 - V_M/V_H = {k_h_rule:.4f}")

    # --- flat-multiple ladder on the laminate numerators (A2e-2c) ------------
    e_lam = (inp["na_lam"] * inp["ret_lam_l"] * (1 - t), lam_mid, inp["e_lam_26"])
    if not e_lam[0] < e_lam[1] < e_lam[2]:
        errors.append(f"laminate numerators not a ladder: {e_lam}")
    flat = [tier(x, 0.0, e * inp["pe_lam_m"])["pre_k"] for x, e in zip("lmh", e_lam)]
    if not flat[0] < flat[1] < flat[2]:
        errors.append(f"flat-multiple ladder collapses: {flat}")

    # --- candidate band (A10): FY2028 single-source added to the H path ------
    cand = anchors(0.0, [inp["e_lam_26"], inp["e_lam_27"], inp["e_lam_28c"]])
    cand = (L, M, cand[2])
    meta = load_framework(FRAMEWORK)
    if meta.candidate is None:
        errors.append("候选带 line missing from Outputs (A10)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), meta.candidate, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")
    # --- V_opt (A9): AI glass fabric + HVLP copper foil, peer-ruler axes ------
    for axis, keys in AXIS_ROWS.items():
        path = AXES / f"{axis}.md"
        if not path.is_file():
            errors.append(f"frameworks/axes/{axis}.md missing — the leg ruler is unchecked")
            continue
        peer = parse_inputs(path.read_text(encoding="utf-8"))
        for k in keys:
            if k not in peer or abs(peer[k] - inp[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.{axis} {peer.get(k)} — the leg ruler drifted")
        if axis == "hvlp-copper-foil" and abs(peer.get("yield_hvlp3", -1) - inp["cu_yield"]) > 1e-9:
            errors.append(f"cu_yield {inp['cu_yield']:g} != _AXIS.hvlp-copper-foil yield_hvlp3 {peer.get('yield_hvlp3')}")
    opt = option_values(inp)
    v_l, v_m, v_h = (opt[x]["total"] for x in "lmh")
    if not 0 <= v_l <= v_m <= v_h:
        errors.append(f"V_opt tiers not ordered: {v_l:.2f}/{v_m:.2f}/{v_h:.2f}")
    p_rule = (v_l / v_h, v_m / v_h, 1.0)
    if meta.v_opt is None or abs(meta.v_opt - v_h) > TOL:
        errors.append(f"V_opt stated {meta.v_opt} vs recomputed V_H {v_h:.4f}")
    if meta.p_tiers is None or any(abs(a - b) > 0.005 for a, b in zip(meta.p_tiers, p_rule)):
        errors.append(f"p_L/p_M/p_H stated {meta.p_tiers} vs V_k/V_H {tuple(round(p, 3) for p in p_rule)}")

    # --- regime comparison band (A1) -----------------------------------------
    r0 = inp["r_lam"]
    reg_l_lam = e_lam[0] * pe(inp["g2_lam"], e_lam[0] / inp["na_lam"], r0)
    reg_h_lam = inp["e_lam_26"] * perpetual_pe(inp["g2_lam"], inp["e_lam_26"] / inp["na_lam"], r0)
    reg = (tier("l", 0.0, reg_l_lam)["pre_k"] - inp["k_l"] * excess("l", tiers["l"]["eps"]),
           M,
           tier("h", 0.0, reg_h_lam)["pre_k"] - inp["k_h"] * excess("h", tiers["h"]["eps"]))

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)

    # --- report ---------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print("baskets: " + " ".join(f"{k}={inp[k]} 篮 {baskets.get(k)}" for k in r_keys))
    print(f"laminate returns FY2017-25: " + " ".join(f"{v:.1%}" for v in lam_ret)
          + f"  mean {same['ret_lam_m']:.4f}  ROIC_mid {roe_lam:.4f}  PE_M {pe_lam:.3f}x (g2 {inp['g2_lam']})")
    print(f"PCB returns FY2017-25: " + " ".join(f"{v:.1%}" for v in pcb_ret)
          + f"  -> L/M/H {inp['ret_pcb_l']}/{inp['ret_pcb_m']}/{inp['ret_pcb_h']}, all x 1/r")
    print(f"chemicals FY2016-25 (bn): " + " ".join(f"{v:.2f}" for v in chem_res)
          + f"  ROIC_mid {roe_chem:.4f} -> 1/r")
    for x in "lmh":
        tv = tiers[x]
        print(f"表1 {x.upper()}: 1888×{inp['stake_kl']}={tv['klhl']:.2f} 线路板={tv['pcb']:.2f} 化工={tv['chem']:.2f}"
              f" 出租物业={tv['rent']:.2f} 待开发={tv['pud']:.2f} 证券={tv['sec']:.2f} 合营联营={tv['jv']:.2f}"
              f" 净债等={tv['debt']:.2f} | k前={tv['pre_k']:.2f} 視同派出={excess(x, tv['eps']):.2f}"
              f" ×k {inp[f'k_{x}']} -> {tv['pre_k'] - inp[f'k_{x}'] * excess(x, tv['eps']):.2f}"
              f" | KLHL eq {tv['klhl_eq']:.2f}bn EPS {tv['eps']:.2f}")
    print(f"k_h ①b = 1 - {tiers['m']['pre_k']:.2f}/{tiers['h']['pre_k']:.2f} = {k_h_rule:.4f}")
    print(f"flat-multiple ladder (PE_M on E_L/E_M/E_H): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"ratios: L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"regime comparison band (A1): L={reg[0]:.2f} M={reg[1]:.2f} H={reg[2]:.2f}")
    print(f"candidate (A10): L'={cand[0]:.2f} M'={cand[1]:.2f} H'={cand[2]:.2f}")
    for x in "lmh":
        o = opt[x]
        for leg in ("gf", "cu"):
            d = o[leg]
            print(f"V_opt {x.upper()} {leg}: rev {d['rev']:.2f}bn NP {d['np']:.2f}bn K {d['k']:.2f}bn ROE {d['roe']:.1%}"
                  f" PE {d['pe']:.2f}x value@t {d['value']:.2f} /(1+r)^{d['years']:g} - unspent {d['unspent']:.2f}"
                  f" = {d['v1888']:.2f}bn -> {d['ps']:.2f}/sh")
        print(f"V_opt {x.upper()} total {o['total']:.2f}/sh")
    if "cap_rev_h" in opt:
        print(f"glass fabric H: capacity rev {opt['cap_rev_h']:.2f}bn vs Citi-path rev {opt['citi_rev']:.2f}bn"
              f" -> Citi implies {opt['citi_px']:.1f} CNY/m on the new capacity")
    print(f"V_opt={v_h:.2f} p_L/p_M/p_H={p_rule[0]:.3f}/{p_rule[1]:.3f}/1.0 V_opt/M={v_h / M:.2f}")
    print(f"zone+V: {L + p_rule[0] * v_h:.2f}/{M + p_rule[1] * v_h:.2f}/{H + v_h:.2f}")
    for g in (inp["g2_lam"] - 0.01, inp["g2_lam"] + 0.01):
        saved = inp["g2_lam"]
        inp["g2_lam"] = g
        s = anchors()
        inp["g2_lam"] = saved
        print(f"  sens g2_lam {g:.2%}: L/M/H {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f}")
    for lab, key, alt in (("d_sec +10pp", "d_sec", 0.10), ("rent NOI 60%", "noi_margin", None)):
        if key == "noi_margin":
            saved = inp[key]
            inp[key] = 0.60
            s = anchors()
            inp[key] = saved
        else:
            saved = {x: inp[f"{key}_{x}"] for x in "lmh"}
            for x in "lmh":
                inp[f"{key}_{x}"] += alt
            s = anchors()
            for x in "lmh":
                inp[f"{key}_{x}"] = saved[x]
        print(f"  sens {lab}: L/M/H {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f}")

    # r_f readings (_AXIS.rates): every basket r moves 1:1; disclosure only.
    rf = rf_block(LISTING_CCY, {k: inp[k] for k in r_keys}, lambda dr: anchors(dr))
    if any(abs(x - y) > TOL for x, y in zip(anchors(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    write_rf_readings("0148.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
