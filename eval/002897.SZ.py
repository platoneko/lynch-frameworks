#!/usr/bin/env python3
"""002897.SZ valuation eval — two-leg SOTP, thin coverage: consensus sets H only.

formula_id: yihua_base_sotp_gordon_v6

Thin coverage (valuation-rules 数据优先级表「盈利分子与过渡」行「薄覆盖」,
2026-10-04 as amended the same day: profit growth vs profit growth, window to
the latest reporting period, trailing-four-quarter margins, all tiers
attributable).  The furthest consensus year with a range, FY2028E, has two
houses (国金 2026-08-30 7.46 / 国海 2026-05-24 8.92 亿归母); the attributable
profit CAGR they imply (FY2025 actual -> FY2028) is >= 2x the company's own
two-year attributable profit CAGR (TTM to 2Q2024 -> TTM to 2Q2026).  So the
consensus only sets H (its high end); M = each leg's TTM revenue carried to
FY2028 (2.5 years) at its own two-year revenue CAGR (TTM 2Q24 -> TTM 2Q26) x its
TTM attributable margin; L = the digestion year (M path stops at FY2026).

Legs: solar = the appraisal subgroup, 100% owned, TTM profit = FY2025
recurring + H1'26 (subsidiary-table sum) - H1'25 (FY2025 net-to-gross-profit
ratio; the H1'25 table lacks the Thai / HK entities) (A18); connector = company TTM attributable (ex the
FY2025 Alpha Steel disposal gain, which sits in solar) - solar, so all minority
interest lands on the connector leg (A7).  Solar H = solar M.

Multiple form from the retention audit (A22): connector tiers whose ROE beats
r by >= 3pp take the same-domain peer g2 (6%); tiers in the flat / peaked
domain take the payout-policy g = (1 - payout) x ROE, clipped at the cap,
with the dividend ruler (`capped_payout_pe`) when the clip is <= 2pp.  The
connector book rolls at b = g/ROE through the not-yet-booked M-path earnings
(iterated to a fixed point per tier).  Solar: D bucket (named Yueqing core-parts
base, COD 2026-12) -> g = 0 + 1/r with the project valued separately as a
capacity item: completed value K_total x ROE_proj / r less the unspent
capital (budget - spent), both at the 2026 spend / COD year, discounted to
today (valuation-rules「未建模期权」capacity rule, 2026-10-04).  Where the model pays out
more than the company does (H tier connector, E bucket) the anchor is cut by
k_h; k_l = k_m = 0 because those tiers' model payout equals the paid payout.

Both legs basket 4 (A17); basket 6 (13%) printed as a control band.  FY2028 =
current FY + 2 -> tiers discounted one year; the project value is already
today's.  ③: same-earnings weeks exist, the band floor month is distorted
(step 1b) -> not decidable -> correction gate.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」).

Run:  python3 frameworks/eval/002897.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    capped_payout_pe,
    check_g_cap,
    check_r,
    g_cap,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.tiers import decompose  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "002897.SZ.md"
FORMULA_ID = "yihua_base_sotp_gordon_v6"
TOL = 0.05
DERIVED_TOL = 5e-4
AMT_TOL = 1e5
GATE_BAND = 0.20
THIN_RATIO = 2.0
ROE_NEAR_R = 0.03
CLIP_TOL = 0.02          # dividend-ruler threshold on the clipped amount
DIV_PAYOUT = 0.40        # ... or on the paid payout
BAND_EPS_BAND = 0.12
DISTORT_G = 0.10         # ③ step 1b: band-month expected growth − model >= 10pp/yr
TIERS = ("L", "M", "H")

REQUIRED = [
    "shares", "equity_total", "equity_solar",
    "rev_conn_fy23", "rev_conn_fy25", "rev_conn_h1_23", "rev_conn_h1_24", "rev_conn_h1_25", "rev_conn_h1_26",
    "rev_solar_fy23", "rev_solar_fy25", "rev_solar_h1_23", "rev_solar_h1_24", "rev_solar_h1_25", "rev_solar_h1_26",
    "gm_solar_fy25", "gm_solar_h1_25", "ni_solar_h1_26",
    "nr_ttm_2q26", "nr_ttm_2q24", "nr_ttm_3q24", "nr_fy24", "nr_q4_25", "nr_h1_26",
    "ni_group_fy25", "ni_ttm_2q26", "ni_ttm_2q24", "ni_solar_fy25r", "disposal_fy25", "ni_solar_l",
    "cons_fy27_m", "cons_fy28_l", "cons_fy28_m", "cons_fy28_h",
    "g2", "g2_solar", "r_conn", "r_solar", "r_ctl", "years_to_fy28", "disc_years", "payout_fy25",
    "proj_k_spent", "proj_k_total", "proj_years_to_cod", "k_l", "k_m", "k_h",
    "m_prev", "bps", "pb_own_min", "roe_peer_lo", "roe_peer_med", "roe_peer_hi", "ttm_eps",
    "band_pe_min", "band_eps", "band_fwd_growth",
    # derived, recomputed below
    "equity_conn", "rev_conn_ttm", "rev_solar_ttm", "g_conn", "g_solar", "g_own_profit", "g_own_recurring",
    "ni_solar_ttm", "ni_conn_ttm", "ni_conn_l", "ni_conn_m", "ni_conn_h", "ni_solar_m", "n_conn",
    "roe_conn_l", "roe_conn_m", "roe_conn_h", "v_proj",
]


def domain(roe: float, r: float) -> str:
    if roe - r >= ROE_NEAR_R:
        return "单调区"
    if roe - r <= -ROE_NEAR_R:
        return "峰形区"
    return "病态区"


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    def derived(key: str, value: float, tol: float = DERIVED_TOL) -> None:
        if abs(value - inp[key]) > tol:
            errors.append(f"{key}: stated {inp[key]:.6g} vs recomputed {value:.6g}")

    # ---- baskets (A17) ----
    for key in ("r_conn", "r_solar"):
        if key not in baskets:
            errors.append(f"{key}: Inputs source cell names no 篮 N (A17)")
        errors += check_r(inp[key], key, baskets.get(key))
    if "r_ctl" in baskets:
        errors.append("r_ctl is a control reading — its source cell must not name a 篮 N")
    errors += check_r(inp["r_ctl"], "r_ctl")
    r = inp["r_conn"]
    if abs(r - inp["r_solar"]) > 1e-12:
        errors.append("legs must share r (discounting uses one rate)")
    cap = g_cap(r)
    errors += check_g_cap(inp["g2"], r, "g2") + check_g_cap(inp["g2_solar"], r, "g2_solar")
    if any(k.startswith("p_") for k in inp):
        errors.append("Inputs carry probability fields — no option, no p")
    pay = inp["payout_fy25"]
    sh = inp["shares"]

    # ---- thin-coverage trigger (A10): profit vs profit, attributable ----
    g_own = (inp["ni_ttm_2q26"] / inp["ni_ttm_2q24"]) ** 0.5 - 1.0
    derived("g_own_profit", g_own)
    cons_cagr = {k: (inp[f"cons_fy28_{k}"] / inp["ni_group_fy25"]) ** (1 / 3) - 1 for k in ("l", "m", "h")}
    ratio = {k: (v / g_own if g_own > 0 else float("inf")) for k, v in cons_cagr.items()}
    if not ratio["l"] >= THIN_RATIO:
        errors.append(f"thin-coverage trigger no longer holds ({ratio['l']:.2f}x < {THIN_RATIO}) — consensus goes back into M")
    errors += ladder("FY2028 consensus", inp["cons_fy28_l"], inp["cons_fy28_m"], inp["cons_fy28_h"])
    upgrade_bar = cons_cagr["m"] / 2
    # Upgrade gate on recurring (扣非) profit (rule amended 2026-10-04): same window.
    g_rec = (inp["nr_ttm_2q26"] / inp["nr_ttm_2q24"]) ** 0.5 - 1.0
    derived("g_own_recurring", g_rec)
    upgraded = g_rec >= upgrade_bar
    if upgraded:
        errors.append(f"upgrade gate met: recurring profit CAGR {g_rec:.1%} >= {upgrade_bar:.1%} — consensus mean back into M")
    need_q3 = inp["nr_ttm_3q24"] * (1 + upgrade_bar) ** 2 - inp["nr_q4_25"] - inp["nr_h1_26"]
    need_fy26 = inp["nr_fy24"] * (1 + upgrade_bar) ** 2

    # ---- revenue windows to the latest period (TTM 2Q24 -> TTM 2Q26) ----
    def ttm(leg: str, fy: str, old: str, new: str) -> float:
        return inp[f"rev_{leg}_{fy}"] + inp[f"rev_{leg}_h1_{new}"] - inp[f"rev_{leg}_h1_{old}"]

    rc_now, rc_then = ttm("conn", "fy25", "25", "26"), ttm("conn", "fy23", "23", "24")
    rs_now, rs_then = ttm("solar", "fy25", "25", "26"), ttm("solar", "fy23", "23", "24")
    derived("rev_conn_ttm", rc_now, AMT_TOL)
    derived("rev_solar_ttm", rs_now, AMT_TOL)
    g_c = (rc_now / rc_then) ** 0.5 - 1
    g_s = (rs_now / rs_then) ** 0.5 - 1
    derived("g_conn", g_c)
    derived("g_solar", g_s)

    # ---- TTM attributable leg profits (A18 / A7) ----
    conv = inp["ni_solar_fy25r"] / (inp["rev_solar_fy25"] * inp["gm_solar_fy25"])
    gp_h25 = inp["rev_solar_h1_25"] * inp["gm_solar_h1_25"]
    s_ttm = inp["ni_solar_fy25r"] + inp["ni_solar_h1_26"] - conv * gp_h25
    c_ttm = inp["ni_ttm_2q26"] - inp["disposal_fy25"] - s_ttm
    derived("ni_solar_ttm", s_ttm, AMT_TOL)
    derived("ni_conn_ttm", c_ttm, AMT_TOL)
    m_c, m_s = c_ttm / rc_now, s_ttm / rs_now

    # ---- numerators (A14) ----
    n = inp["years_to_fy28"]
    conn = {"L": rc_now * (1 + g_c) ** (n - 2) * m_c, "M": rc_now * (1 + g_c) ** n * m_c}
    solar_m = rs_now * (1 + g_s) ** n * m_s
    solar = {"L": inp["ni_solar_l"], "M": solar_m, "H": solar_m}
    conn["H"] = inp["cons_fy28_h"] - solar["H"]
    for key, v in (("ni_conn_l", conn["L"]), ("ni_conn_m", conn["M"]), ("ni_conn_h", conn["H"]), ("ni_solar_m", solar_m)):
        derived(key, v, AMT_TOL)
    group = {t: conn[t] + solar[t] for t in TIERS}
    errors += ladder("connector numerator", conn["L"], conn["M"], conn["H"])
    errors += ladder("company numerator", group["L"], group["M"], group["H"])
    if not solar["L"] < solar["M"]:
        errors.append("solar L must sit below solar M")
    if not group["M"] < inp["cons_fy28_l"]:
        errors.append("thin coverage: M must sit below the consensus low")

    # ---- connector book and multiple form per tier (A13 / A22) ----
    eq_c0 = inp["equity_total"] - inp["equity_solar"]
    derived("equity_conn", eq_c0, AMT_TOL)
    c27 = rc_now * (1 + g_c) ** (n - 1) * m_c
    n_conn = 0.5 * conn["L"] + c27          # 2H26 + FY2027 on the M path
    derived("n_conn", n_conn, AMT_TOL)

    def conn_tier(c: float, r_: float, peer_g: float) -> tuple[float, float, float, str]:
        g = peer_g
        for _ in range(200):
            roe = c / (eq_c0 / (1.0 - g * n_conn / c))
            if roe - r_ >= ROE_NEAR_R:
                g_new, form = peer_g, "peer g2"
                pe = perpetual_pe(g_new, roe, r_)
            else:
                g_raw = (1.0 - pay) * roe
                g_new = min(g_raw, g_cap(r_))
                if g_raw > g_cap(r_) and (pay >= DIV_PAYOUT or g_raw - g_cap(r_) <= CLIP_TOL):
                    pe, form = capped_payout_pe(g_raw, roe, r_, pay), f"policy g {g_raw:.2%} clipped -> dividend ruler"
                else:
                    pe, form = perpetual_pe(g_new, roe, r_), f"policy g {g_new:.2%}"
            if abs(g_new - g) < 1e-12:
                return g_new, roe, pe, form
            g = g_new
        raise RuntimeError("book / g fixed point did not converge")

    # ---- project value (D bucket, A22) ----
    roe_proj = s_ttm / inp["equity_solar"]

    def project(r_: float) -> float:
        # Capacity item: completed value less the unspent capital, both at the 2026 spend / COD point, to today.
        k_rem = inp["proj_k_total"] - inp["proj_k_spent"]
        return (inp["proj_k_total"] * roe_proj / r_ - k_rem) * (1 + r_) ** -inp["proj_years_to_cod"]

    v_proj = project(r)
    derived("v_proj", v_proj, AMT_TOL)
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    def deck(r_: float, cx=conn, sx=solar, peer_g=None, solar_branch="D"):
        peer_g = inp["g2"] if peer_g is None else peer_g
        rows = {}
        for t in TIERS:
            g, roe, pe_a, form = conn_tier(cx[t], r_, peer_g)
            roe_s = sx[t] / inp["equity_solar"]
            if solar_branch == "D":
                pe_b = perpetual_pe(inp["g2_solar"], roe_s, r_)
            else:  # E bucket alternative: retaining branch at the payout-policy g
                pe_b = perpetual_pe(min((1 - pay) * roe_s, g_cap(r_)), roe_s, r_)
            vp = project(r_) if solar_branch == "D" else 0.0
            val = (cx[t] * pe_a * (1 - k[t]) + sx[t] * pe_b) / (1 + r_) ** inp["disc_years"] + vp
            rows[t] = dict(px=val / sh, g=g, roe=roe, pe_a=pe_a, pe_b=pe_b, form=form, roe_s=roe_s)
        return rows

    base = deck(r)
    for t, key in zip(TIERS, ("roe_conn_l", "roe_conn_m", "roe_conn_h")):
        derived(key, base[t]["roe"])
    L, M, H = (base[t]["px"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    # k must be declared where the model pays out more than the company (H here); 0 elsewhere with a reason.
    for t in TIERS:
        modelled = 1 - base[t]["g"] / base[t]["roe"]
        capped = "dividend ruler" in base[t]["form"]
        if not capped and modelled - pay > 0.20 and k[t] <= 0:
            errors.append(f"k_{t.lower()} = 0 but tier {t} models payout {modelled:.0%} vs paid {pay:.0%} (视同派出 needs k)")

    disc = (1 + r) ** inp["disc_years"]
    pe_c = {t: (base[t]["px"] * sh - v_proj) * disc / group[t] for t in TIERS}
    dec = decompose((L, M, H), (pe_c["L"], pe_c["M"], pe_c["H"]))
    flat = tuple((conn[t] * base["M"]["pe_a"] * (1 - k[t]) + solar[t] * base[t]["pe_b"]) / disc / sh + v_proj / sh for t in TIERS)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    ctl = deck(inp["r_ctl"])
    sens = {
        "g2 (单调区 peer) 5%": deck(r, peer_g=0.05),
        "g2 (单调区 peer) 3%": deck(r, peer_g=0.03),
        "solar E bucket (retaining branch, no project)": deck(r, solar_branch="E"),
        "k_h 0.5": None,
        "k_h 0": None,
    }
    for kh in (0.5, 0.0):
        k_save = k["H"]
        k["H"] = kh
        sens[f"k_h {kh:g}"] = deck(r)
        k["H"] = k_save
    # Solar H1'26 by the gross-profit conversion instead of the subsidiary-table sum (the v5 basis).
    s_alt = inp["ni_solar_fy25r"] + conv * inp["rev_solar_h1_26"] * 0.1099 - conv * gp_h25
    c_alt = inp["ni_ttm_2q26"] - inp["disposal_fy25"] - s_alt
    cx_alt = {"L": rc_now * (1 + g_c) ** (n - 2) * c_alt / rc_now, "M": rc_now * (1 + g_c) ** n * c_alt / rc_now}
    sm_alt = rs_now * (1 + g_s) ** n * s_alt / rs_now
    cx_alt["H"] = inp["cons_fy28_h"] - sm_alt
    sens["solar H1'26 by GP conversion (v5)"] = deck(r, cx_alt, {"L": inp["ni_solar_l"], "M": sm_alt, "H": sm_alt})

    # H-tier 视同派出 line (E bucket, single-stage perpetual): excess retention capitalised.
    b_h = base["H"]["g"] / base["H"]["roe"]
    line_h = (1 - pay - b_h) * conn["H"] / (r - base["H"]["g"]) / disc / sh

    # ---- ③ band (A12): same-earnings weeks exist; step 1c and 1b ----
    eps_m = group["M"] / sh
    pe_m_anchor = M / eps_m
    band_floor_1c = (inp["band_pe_min"] * inp["band_eps"] - v_proj / sh) / inp["band_eps"]
    model_growth = (group["M"] / (inp["ni_ttm_2q26"])) ** (1 / n) - 1
    distorted = inp["band_fwd_growth"] - model_growth >= DISTORT_G
    if pe_m_anchor < band_floor_1c and not distorted:
        errors.append("③ out of band on a clean band — run the ③ process (BLOCKED at basket 4)")

    # ---- correction reconciliation gate ----
    peer_pe = {kk: perpetual_pe(inp["g2"], inp[kk], r) for kk in ("roe_peer_lo", "roe_peer_med", "roe_peer_hi")}
    coords = {
        "① previous (committed) M": inp["m_prev"],
        "② E_M/r": group["M"] / r / sh,
        "③ DDM (payout FY25, g_d = M-tier g)": pay * group["M"] / (r - base["M"]["g"]) / sh,
        "④ same-earnings weeks floor (band_pe_min × E_M)": inp["band_pe_min"] * eps_m,
        "⑤ peers same ruler (2028E ROE median), discounted": peer_pe["roe_peer_med"] * eps_m / disc,
        "⑥ BPS × own PB low": inp["bps"] * inp["pb_own_min"],
    }
    devs = {kk: M / v - 1.0 for kk, v in coords.items()}
    # Same-formula cells do not count (2026-10-04): the M connector leg is the dividend ruler at this payout.
    same_formula = {"③ DDM (payout FY25, g_d = M-tier g)"}
    inside = [kk for kk, d in devs.items() if abs(d) <= GATE_BAND and kk not in same_formula]
    if not inside:
        errors.append("BLOCKED: new M is > 20% away from every reconciliation coordinate (纠正对账门)")

    # ---- report ----
    print(f"formula_id={FORMULA_ID}  (V_opt = 0, A15)  baskets={baskets} r={r:g} ctl={inp['r_ctl']:g} cap={cap:.0%}")
    print(f"thin coverage: own 2y 归母 CAGR (TTM 2Q24 {inp['ni_ttm_2q24'] / 1e8:.3f} -> TTM 2Q26 {inp['ni_ttm_2q26'] / 1e8:.3f}) = {g_own:.2%}")
    print("  consensus FY25->FY28 CAGR l/m/h " + " / ".join(f"{cons_cagr[x]:.1%} ({ratio[x]:.2f}x)" for x in ("l", "m", "h"))
          + f"; upgrade bar {upgrade_bar:.1%}")
    print(f"  recurring (扣非) 2y CAGR TTM 2Q24 {inp['nr_ttm_2q24'] / 1e8:.3f} -> 2Q26 {inp['nr_ttm_2q26'] / 1e8:.3f} = {g_rec:.2%} "
          f"(trigger read on 扣非: {cons_cagr['l'] / g_rec:.2f}–{cons_cagr['h'] / g_rec:.2f}x) -> upgrade {'MET' if upgraded else 'not met'}")
    print(f"  next readings: Q3'26 single-quarter 扣非 needs >= {need_q3 / 1e8:.2f}亿; FY2026 扣非 needs >= {need_fy26 / 1e8:.2f}亿 (vs FY2024 {inp['nr_fy24'] / 1e8:.2f})")
    print(f"  annual-window check FY23->FY25 归母 CAGR = {(inp['ni_group_fy25'] / 1.222e8) ** 0.5 - 1:.1%} (disclosure)")
    print(f"revenue TTM: connector {rc_then / 1e8:.3f} -> {rc_now / 1e8:.3f} ({g_c:.2%}/y); solar {rs_then / 1e8:.3f} -> {rs_now / 1e8:.3f} ({g_s:.2%}/y)")
    print(f"TTM 归母: solar {s_ttm / 1e8:.4f} (conv {conv:.4f}) margin {m_s:.2%}; connector {c_ttm / 1e8:.4f} margin {m_c:.2%}")
    print(f"equity_conn0={eq_c0:.4e} n_conn={n_conn / 1e8:.4f}亿 ROE_proj={roe_proj:.2%} V_proj={v_proj / 1e8:.4f}亿 ({v_proj / sh:.2f}/sh)")
    for t in TIERS:
        b = base[t]
        print(f"{t}: group {group[t] / 1e8:.4f}亿 = conn {conn[t] / 1e8:.4f} (ROE {b['roe']:.2%} {domain(b['roe'], r)}, g {b['g']:.2%}, "
              f"PE {b['pe_a']:.2f}x [{b['form']}], k {k[t]:g}) + solar {solar[t] / 1e8:.4f} (ROE {b['roe_s']:.1%} "
              f"{domain(b['roe_s'], r)}, PE {b['pe_b']:.2f}x) + proj -> {b['px']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"control band r_ctl {inp['r_ctl']:.0%}: {ctl['L']['px']:.2f} / {ctl['M']['px']:.2f} / {ctl['H']['px']:.2f}")
    print(f"flat-multiple ladder @ PE_A_M {base['M']['pe_a']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"composite PE (ex project, undiscounted) {pe_c['L']:.2f}/{pe_c['M']:.2f}/{pe_c['H']:.2f}")
    print(f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} "
          f"x pe {dec['pe_hm']:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M 0")
    for name, d in sens.items():
        print(f"sens {name}: {d['L']['px']:.2f}/{d['M']['px']:.2f}/{d['H']['px']:.2f}")
    print(f"H 视同派出 line (E bucket, k before): {line_h:.2f}/sh; k_h {k['H']:g} takes {base['H']['px'] - sens['k_h 0']['H']['px']:+.2f}/sh off H")
    print(f"③: M anchor / E_M = {pe_m_anchor:.2f}x vs same-earnings floor {inp['band_pe_min']:.2f}x (1c-adjusted {band_floor_1c:.2f}x); "
          f"band-month expected growth {inp['band_fwd_growth']:.1%} vs model {model_growth:.1%} -> {'distorted (1b), not decidable' if distorted else 'clean'}")
    print(f"PB 1.0 = {inp['bps']:.2f}; M/BPS = {M / inp['bps']:.2f}")
    print(f"reconciliation gate (M = {M:.2f}):")
    for kk, v in coords.items():
        tag = "  (same formula as M, printed not counted)" if kk in same_formula else ("  <- within 20%" if kk in inside else "")
        print(f"  {kk}: {v:.2f} ({devs[kk]:+.1%}){tag}")
    for name, e in (("TTM", inp["ttm_eps"]), ("M numerator FY2028", eps_m), ("FY+1 consensus FY2027E", inp["cons_fy27_m"] / sh)):
        print(f"  neutral band [A,B) on {name} ({e:.2f}): {A / e:.1f}–{B / e:.1f}x")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
