#!/usr/bin/env python3
"""300750.SZ (CATL / Contemporary Amperex Technology) valuation eval.

frameworks/300750.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price, A or H (AGENTS.md「现价 — 禁写契约」), so nothing here
computes a zone, an A/H ratio or a market-implied reading — the digest and the
app zone on live quotes.

formula_id: catl_group_ni_fy27_consensus_perpetual_gordon_v5

Main ruler: operating value + excess cash (valuation-rules「经营价值与超额现金」,
2026-10-15 框架纠正), one leg, one stage, no transition:

  E_op_x  = eps_x − C_ex after-tax income per share   (same amount, all tiers)
  RONIC_x = E_op_x / opening-2027 operating BPS        (per tier, A21 roll)
  PE_x    = perpetual_pe(g2_x, RONIC_x, r)
  anchor  = E_op_x * PE_x + C_ex / shares               (lambda = 1)

Excess cash (A22): extended net cash at 2026-06-30 (cash + trading financial
assets − interest-bearing debt − lease liabilities) minus the 2026 interim
dividend (declared after the balance-sheet date, ex-dividend and paid in
August), minus the operating cash anchor = min(lowest「净现金 ÷ 收入」over the
listed years FY2018–25, 2 months of revenue) × FY2025 revenue.  Customer
prepayments (contract liabilities) are an operating liability, not netted.

r is the basket the framework names for the single leg (篮 4 龙头制造, 10%,
gordon.BASKET_R), read from the Inputs row and checked against the 篮 N tag
(A20).  Numerator year (裁决顺序 ②): FY2027E, the furthest consensus year with
>= 2 houses and a range; FY2027 = current fiscal year + 1, no discounting.

g2 source tier: 无同业锚 — named per tier 2% / 3% / 4% (A7, kept).  The
own-year band, converted to operating multiples with each year's own C_ex(t)
(A10), is only a fence; the M-tier band-edge implied-g range is printed.

RONIC (A21): tier operating EPS ÷ the numerator year's OPENING operating BPS.
The 2Q26 operating book (equity − interim dividend − C_ex) is rolled over the
2H26 operating earnings not yet booked at b1 = g2/RONIC, closed form
OBPS = OBPS_2Q26 / (1 − g2·N_op/E_op).  Actual retention above b1 is the
「多留部分」(it lands in excess cash, lambda = 1), printed as a disclosure.

2026-10-16 framework correction (valuation-rules「经营价值与超额现金」):
  * parent share: C_ex x (parent equity less the interim dividend) / (that +
    minority interest) = 91.51% (no subsidiary-level cash disclosure); the
    same share drives its income and the operating book.
  * growth-period funding gap 0: 1H26 capex 250.73 vs OCF 602.17亿, the
    in-construction budget is paid at ~250亿 a half-year.
  * time alignment: the Gordon value is at 2027-01-01 -> x (1+r)^-tau, tau 0.5
    from the 2026-06-30 balance sheet; plus the 2H26 window distributable
    profit (unbooked operating EPS x (1 - g2/RONIC)) at tau/2.  V_opt x tau.
  * three-stage return: forward RONIC through Y1 2027 (visible-year end),
    linear to the steady return by Y2 2031 (medium entry barrier: 4 years),
    perpetual after.  Steady 22.8% = own-cycle layer on PLAIN ROE (FY2019–25
    median of parent NI / average parent equity, excess cash NOT deducted — a
    different basis from the forward return; user ruling 2026-10-18).  The
    excess-cash-deducted own-cycle reading 39.0% is not used: stripping the
    cash shrinks the denominator and inflates the return.  Peer layer: only
    Samsung SDI passes the maturity test, 6.9% < r; floor 11% (comparison only,
    not a lower bound; the check is steady >= r).  g2 named, not
    re-solved; (1 − 50%) x 22.8% = 11.4% >= g2_h, no cap.

Run:  python3 frameworks/eval/300750.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, g_cap, implied_g, payout, perpetual_pe, two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "300750.SZ.md"
FORMULA_ID = "catl_group_ni_fy27_consensus_perpetual_gordon_v5"

TIERS = ("l", "m", "h")
MIN_SPREAD = 0.02          # r - g2 floor (valuation-rules ①)
MIN_CONSENSUS_HOUSES = 2   # a numerator year needs >= 2 houses with a range (②)
ANCHOR_CAP = 2 / 12        # operating cash anchor capped at 2 months of revenue
EXCESS_TRIGGER = 0.15      # C_ex >= 15% of parent equity → separate line
CASH_WINDOW = range(2018, 2026)   # listed years (IPO 2018-06), A22

# Year-end figures (亿元, Eastmoney F10 statements, frameworks/_local/tmp/recalc/
# 300750.SZ/raw/em): extended net cash (cash + trading financial assets −
# interest-bearing debt − lease − dividend payable), revenue; for the fence
# years also parent NI, cash yield ((interest income + fair-value gains) ÷
# average cash-like assets) and effective tax rate.  Pre-IPO 2016–17 are kept
# only for the window sensitivity.
EXT = {2016: 6.9, 2017: 93.4, 2018: 221.3, 2019: 239.6, 2020: 435.7, 2021: 363.8825,
       2022: 925.1919, 2023: 1391.2519, 2024: 1759.9249, 2025: 2728.4997}
REV = {2016: 148.8, 2017: 200.0, 2018: 296.1, 2019: 457.9, 2020: 503.2, 2021: 1303.5580,
       2022: 3285.9399, 2023: 4009.1705, 2024: 3620.1255, 2025: 4237.0183}
NI = {2022: 307.2916, 2023: 441.2125, 2024: 507.4468, 2025: 722.0128}
YLD = {2022: 0.030957, 2023: 0.036595, 2024: 0.034932, 2025: 0.032574}
TAX = {2022: 0.087686, 2023: 0.132674, 2024: 0.145219, 2025: 0.142307}
# own-year PE (前复权收盘 ÷ 复权 EPS, daily) low / high per year (A10)
PE_OWN = {2022: (25.2, 40.0), 2023: (12.6, 24.1), 2024: (10.4, 24.5), 2025: (12.2, 25.2)}

# Fields the anchor path is allowed to touch.  Everything else in the Inputs
# table is cross-check material, and the guard below proves it stays out.
FORMULA_FIELDS = frozenset({
    "shares", "equity", "r_perp",
    "eps_l", "eps_m", "eps_h",
    "g2_l", "g2_m", "g2_h",
    "eps_fy26_mean", "ni_1h26",   # only via the 2H26 unbooked earnings in the book roll (A21)
    "net_cash_ext_h1", "div_declared", "rev_fy2025", "cash_ratio_min",
    "cash_yield", "tax_eff",      # excess cash and its after-tax income (A22)
    "minority_h1",                # parent share of C_ex (A22)
    "tau", "y1", "y2", "ronic_ss",   # time alignment and the three-stage return (A23)
})

REQUIRED = sorted(FORMULA_FIELDS | {
    "bps", "consensus_n_fy27", "payout_3y", "payout_op", "c_ex", "cash_restricted",
    "eps_fy26_lo", "eps_fy26_hi", "eps_fy26_lb",
    "pe_own_hi_recent", "pe_own_hi", "pe_own_lo", "pe_op_hi_recent", "pe_op_hi", "pe_op_lo",
    "eps_ttm", "eps_fy2025", "eps_freeze", "eps_freeze_tax",
    "tp_street", "tp_consensus", "fx_hkdcny",
    "net_cash", "unit_profit_h1", "unit_profit_fy2025",
    "px_low_2026", "px_low_2025", "gp_other_rate",
    "buyback_lo", "buyback_hi", "treasury_shares", "opt_outstanding",
    "cap_now_ann", "cap_build", "util_h1", "t_num", "t_opt",
    "hu_gwh", "hu_budget", "hu_inv_pct", "dom_budget_gwh", "dom_inv_pct", "opt_eq",
    "parent_ratio", "ronic_ss_floor",
})
T0 = 2027                  # numerator year: the Gordon value sits at its start

# 表3 only — never Inputs, never the base band (A2e-7a).
P_K = (0.0, 0.25, 1.0)


# --- excess cash and the operating basis (A22) ------------------------------------
def cash_anchor(inp: dict[str, float]) -> float:
    """Operating cash anchor (亿): min(lowest listed-year ratio, 2 months) × FY2025 revenue."""
    return max(min(inp["cash_ratio_min"], ANCHOR_CAP), 0.0) * inp["rev_fy2025"]


def excess_cash_total(inp: dict[str, float]) -> float:
    """C_ex (亿, consolidated) = extended net cash − declared / ex-dividend unpaid dividend − anchor."""
    return inp["net_cash_ext_h1"] - inp["div_declared"] - cash_anchor(inp)


def parent_ratio(inp: dict[str, float]) -> float:
    """① 归母份额: no subsidiary-level cash disclosure -> parent equity / (parent + minority),
    the parent side net of the interim dividend (already out of the cash)."""
    eq = inp["equity"] - inp["div_declared"]
    return eq / (eq + inp["minority_h1"])


def excess_cash(inp: dict[str, float]) -> float:
    """Parent-share C_ex (亿) — what enters value, the numerator's cash income and the operating book."""
    return excess_cash_total(inp) * parent_ratio(inp)


def path_pe(inp: dict[str, float], g: float, roe: float, t0: int = T0, fresh: bool = False) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段), value at the start of t0 per
    unit of t0 earnings: RONIC = roe through y1, linear to min(roe, ronic_ss) by y2, perpetual on.
    y1 / y2 are calendar years (default t0 = T0).  `fresh=True` restarts the period at t0
    (y1 = t0, y2 = t0 + (y2 − y1)) -- the pre-2026-10-19 implicit read of the option, disclosure only."""
    r, y1, y2 = inp["r_perp"], int(inp["y1"]), int(inp["y2"])
    if fresh:
        y1, y2 = t0, t0 + (y2 - y1)
    ss = min(roe, inp["ronic_ss"])
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g, ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def cash_ps(inp: dict[str, float]) -> float:
    return excess_cash(inp) * 1e8 / inp["shares"]


def cash_income_ps(inp: dict[str, float]) -> float:
    """After-tax income of today's C_ex per share — taken out of every forward numerator."""
    return excess_cash(inp) * inp["cash_yield"] * (1.0 - inp["tax_eff"]) * 1e8 / inp["shares"]


def unbooked_op_eps(inp: dict[str, float]) -> float:
    """2H26 operating EPS not yet in the 2Q26 book: FY2026E consensus − 1H26 actual − half a year of cash income."""
    return inp["eps_fy26_mean"] - inp["ni_1h26"] * 1e8 / inp["shares"] - cash_income_ps(inp) / 2


def obps_2q26(inp: dict[str, float]) -> float:
    """2Q26 operating book per share: parent equity − interim dividend − C_ex."""
    return (inp["equity"] - inp["div_declared"] - excess_cash(inp)) * 1e8 / inp["shares"]


def obps_open_2027(inp: dict[str, float], e_op: float, g: float) -> float:
    """Opening-2027 operating BPS: rolled over 2H26 at b1 = g/RONIC, closed form (A21)."""
    return obps_2q26(inp) / (1.0 - g * unbooked_op_eps(inp) / e_op)


def ronic(inp: dict[str, float], e_op: float, g: float) -> float:
    return e_op / obps_open_2027(inp, e_op, g)


def op_value(inp: dict[str, float], e_op: float, g: float) -> float:
    """Operating value at the start of FY2027 per share + excess cash per share (lambda = 1); not aligned."""
    return e_op * path_pe(inp, g, ronic(inp, e_op, g)) + cash_ps(inp)


def window_ps(inp: dict[str, float], e_op: float, g: float) -> float:
    """2H26 window distributable profit per share: unbooked operating EPS x (1 − b), b = g/RONIC (③)."""
    return max(unbooked_op_eps(inp) * (1.0 - g / ronic(inp, e_op, g)), 0.0)


def aligned(inp: dict[str, float], e_op: float, g: float) -> float:
    """Today's value: operating value x (1+r)^-tau + window x (1+r)^-(tau/2) + excess cash (③ 时点对齐)."""
    r, tau = inp["r_perp"], inp["tau"]
    v = op_value(inp, e_op, g) - cash_ps(inp)
    return v * (1 + r) ** -tau + window_ps(inp, e_op, g) * (1 + r) ** -(tau / 2) + cash_ps(inp)


def e_op(inp: dict[str, float], eps: float) -> float:
    return eps - cash_income_ps(inp)


def anchor(inp: dict[str, float], tag: str) -> float:
    return aligned(inp, e_op(inp, inp[f"eps_{tag}"]), inp[f"g2_{tag}"])


# --- history on the operating basis (A10 / A22) -----------------------------------
def cex_hist(ratio: float) -> dict[int, float]:
    """C_ex(t) = max(extended net cash(t) − ratio × revenue(t), 0)."""
    return {y: max(EXT[y] - ratio * REV[y], 0.0) for y in EXT}


def op_band(ratio: float) -> dict[int, tuple[float, float, float]]:
    """Own-year PE → operating multiple (P − c_t) / E_op(t), c_t = average of the
    year's opening and closing C_ex (the reports visible during the year)."""
    cx = cex_hist(ratio)
    out = {}
    for y, (lo, hi) in PE_OWN.items():
        c_avg = (cx[y - 1] + cx[y]) / 2
        op = NI[y] - c_avg * YLD[y] * (1 - TAX[y])
        out[y] = ((lo * NI[y] - c_avg) / op, (hi * NI[y] - c_avg) / op, op / NI[y])
    return out


def capacity_option(inp: dict[str, float], base_h: float, fresh: bool = False) -> dict[str, float]:
    # base_h: the H tier's unaligned value at the start of FY2027 (op_value) -- printed for reference;
    # the option itself is valued in the realisation year on both sides (2026-10-19, A18).
    """V_opt — the named in-construction capacity beyond what the H tier already
    implies (A18, valuation-rules「未建模期权」2026-10-03), on the same operating
    Gordon ruler as the H tier (H-tier operating opening BPS, g2_h).

    Size: (today's annualised capacity + in-construction) x 2026H1 utilisation
    = volume once built; minus the volume the FY2027E consensus HIGH already
    implies at the 2026H1 unit net profit.  Less the unspent capital behind the
    option's share of the in-construction capacity (2026-10-04).
    """
    vol_full = (inp["cap_now_ann"] + inp["cap_build"]) * inp["util_h1"]          # GWh
    vol_in_h = inp["eps_h"] * inp["shares"] / (inp["unit_profit_h1"] * 1e6)    # GWh
    d_vol = vol_full - vol_in_h
    d_ni = d_vol * inp["unit_profit_h1"] / 100.0                               # 亿
    d_eps = d_ni * 1e8 / inp["shares"]
    eop_h = e_op(inp, inp["eps_h"])
    obps_h = obps_open_2027(inp, eop_h, inp["g2_h"])
    eop_post = eop_h + d_eps
    ronic_post = eop_post / obps_h
    # Product-stage check (A18, 2026-10-19): the capacity makes the batteries CATL already ships at
    # scale -- same product, same 环节 -- so it inherits the calendar high-return period Y1 2027 /
    # Y2 2031 and is valued in t_opt with the fall already under way.  Both sides (with and without
    # the increment) sit in t_opt on the same path; reusing the 2027-start multiples at t_opt (the
    # old construction) silently restarted the period at the capacity's start.
    t_opt = int(inp["t_opt"])
    pe_post = path_pe(inp, inp["g2_h"], ronic_post, t_opt, fresh)
    pe_base = path_pe(inp, inp["g2_h"], eop_h / obps_h, t_opt, fresh)
    anchor_post = eop_post * pe_post + cash_ps(inp)
    base_t = eop_h * pe_base + cash_ps(inp)
    # to the numerator year, then tau to the valuation date (③ 时点对齐: V_opt discounted to t_n is aligned too)
    disc = (1.0 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]) - inp["tau"])
    k_hu = inp["hu_budget"]
    k_dom = (inp["cap_build"] - inp["hu_gwh"]) * inp["dom_budget_gwh"]
    k_budget = k_hu + k_dom
    k_spent = k_hu * inp["hu_inv_pct"] + k_dom * inp["dom_inv_pct"]
    k_remain = k_budget - k_spent                                              # 亿
    share_opt = d_vol / (inp["cap_build"] * inp["util_h1"])
    k_opt = k_remain * share_opt * inp["opt_eq"]                               # 亿
    k_ps = k_opt * 1e8 / inp["shares"]
    return {"vol_full": vol_full, "vol_in_h": vol_in_h, "d_vol": d_vol, "d_ni": d_ni,
            "d_eps": d_eps, "ronic_post": ronic_post, "pe_post": pe_post,
            "anchor_post": anchor_post, "base_t": base_t, "pe_base": pe_base, "disc": disc,
            "k_budget": k_budget, "k_spent": k_spent, "k_remain": k_remain,
            "share_opt": share_opt, "k_opt": k_opt, "k_ps": k_ps,
            "v_gross": (anchor_post - base_t) * disc,
            "v_opt": (anchor_post - base_t - k_ps) * disc}


def band_edge_g(inp: dict[str, float], ron: float, pe_edge: float) -> float:
    """Perpetual g that lands the operating multiple (same three-stage path) on a band edge (③)."""
    r = inp["r_perp"]
    lo, hi = -0.10, g_cap(r)
    for _ in range(200):
        mid = (lo + hi) / 2
        if path_pe(inp, mid, ron) < pe_edge:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


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

    r, sh = inp["r_perp"], inp["shares"]

    # --- Step 0: excess cash (A22) -------------------------------------------
    ratio_obs = min(EXT[y] / REV[y] for y in CASH_WINDOW)
    if abs(ratio_obs - inp["cash_ratio_min"]) > 5e-5:
        errors.append(f"cash_ratio_min {inp['cash_ratio_min']} != FY2018–25 lowest {ratio_obs:.5f}")
    c_tot = excess_cash_total(inp)
    if abs(c_tot - inp["c_ex"]) > 0.05:
        errors.append(f"c_ex {inp['c_ex']} != net_cash_ext_h1 − div_declared − anchor {c_tot:.2f}")
    pr = parent_ratio(inp)
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = excess_cash(inp)
    tau_calc = ((T0 - 2026) * 12 - 6) / 12          # 2026-06-30 balance sheet -> 2027-01-01
    if abs(inp["tau"] - tau_calc) > 1e-9:
        errors.append(f"tau {inp['tau']} != {tau_calc}")
    if not (inp["y1"] == T0 and inp["y2"] == inp["y1"] + 4):
        errors.append("Y1 must be the visible-year end FY2027 and Y2 = Y1 + 4 (medium entry barrier, A23)")
    # The floor is a substitute, not a lower bound (ordered pick, 2026-10-19): only r binds.
    if inp["ronic_ss"] < inp["r_perp"]:
        errors.append("ronic_ss below r (A23)")
    eq_adj = inp["equity"] - inp["div_declared"]
    if c_ex < EXCESS_TRIGGER * eq_adj:
        errors.append("c_ex below 15% of parent equity: the excess-cash line should not exist")
    cps, inc_ps = cash_ps(inp), cash_income_ps(inp)

    # --- Step 1-2: ladders and the numerator-year qualification (②) ---------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    errors += ladder("g2", inp["g2_l"], inp["g2_m"], inp["g2_h"])
    if inp["consensus_n_fy27"] < MIN_CONSENSUS_HOUSES:
        errors.append(
            f"consensus_n_fy27={inp['consensus_n_fy27']:.0f} < {MIN_CONSENSUS_HOUSES} — "
            f"FY2027E no longer qualifies as the numerator year; fall back to FY2026E (A19)"
        )
    if obps_2q26(inp) <= 0:
        errors.append("operating equity (equity − interim dividend − C_ex) must be positive")
    n_op = unbooked_op_eps(inp)
    eop = {t: e_op(inp, inp[f"eps_{t}"]) for t in TIERS}
    for t in TIERS:
        k = inp[f"g2_{t}"] * n_op / eop[t]
        if k >= 1.0:
            errors.append(f"book roll diverges for {t}: g2·N/E_op = {k:.3f} >= 1 (A21)")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    obps_open = {t: obps_open_2027(inp, eop[t], inp[f"g2_{t}"]) for t in TIERS}
    ron = {t: ronic(inp, eop[t], inp[f"g2_{t}"]) for t in TIERS}
    b1 = {t: inp[f"g2_{t}"] / ron[t] for t in TIERS}
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"b1_{t} = g2/RONIC = {b1[t]:.3f} outside (0, 1) (A21)")

    # --- Step 3-4: convergence, retention cost, branch, constraint 2 ---------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for t in TIERS:
        g2 = inp[f"g2_{t}"]
        if ron[t] <= 0:
            errors.append(f"RONIC_{t}={ron[t]:.4f} must be positive")
        errors += check_g_cap(g2, r, f"g2_{t}")
        if r - g2 < MIN_SPREAD - 1e-12:
            errors.append(f"r - g2_{t} = {r - g2:.2%} < {MIN_SPREAD:.0%} — perpetuity ill-conditioned")
        pay = payout(g2, ron[t])
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        errors += check_branch(g2, ron[t], r, inp["payout_op"], f"g2_{t}")
        # ③ 约束 2: g <= (1 − d) × RONIC — what the company keeps caps the growth it can fund
        if g2 > (1.0 - inp["payout_3y"]) * ron[t] + 1e-12:
            errors.append(f"g2_{t} {g2:.2%} > (1 − d) × RONIC = {(1 - inp['payout_3y']) * ron[t]:.2%}")
    if errors:
        return report(errors, "FAIL (convergence/payout)")

    pe = {t: path_pe(inp, inp[f"g2_{t}"], ron[t]) for t in TIERS}
    win = {t: window_ps(inp, eop[t], inp[f"g2_{t}"]) for t in TIERS}
    dtau = (1 + r) ** -inp["tau"]

    # --- Step 5: the own-year fence on the operating basis (A10) -------------
    band = op_band(min(inp["cash_ratio_min"], ANCHOR_CAP))
    op_lo, op_hi = band[2024][0], band[2022][1]
    op_hi_recent = max(band[y][1] for y in (2023, 2024, 2025))
    for key, want in (("pe_op_lo", op_lo), ("pe_op_hi", op_hi), ("pe_op_hi_recent", op_hi_recent)):
        if abs(inp[key] - want) > 0.01:
            errors.append(f"{key} {inp[key]} != recomputed operating band edge {want:.2f}")
    for t in TIERS:
        if not inp["pe_op_lo"] - 1e-9 <= pe[t] <= inp["pe_op_hi"] + 1e-9:
            errors.append(f"PE_{t}={pe[t]:.2f} outside operating own-year band "
                          f"[{inp['pe_op_lo']}, {inp['pe_op_hi']}] — ③ band-edge reverse-solve required")
    if pe["h"] > inp["pe_op_hi_recent"] + 1e-9:
        errors.append(f"PE_H={pe['h']:.2f} above operating own-year high since 2023 {inp['pe_op_hi_recent']}")

    # --- Step 8: the non-formula fields really are non-formula ---------------
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append("anchor path touches a non-formula field")
    if errors:
        return report(errors, "FAIL (guards)")

    # --- Step 9: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    # Step 6: a flat multiple must still leave a ladder (A2e-2c), cash included.
    flat = [eop[t] * pe["m"] * dtau + win[t] * (1 + r) ** -(inp["tau"] / 2) + cps for t in TIERS]
    errors += ladder("flat-multiple", *flat)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # Step 7: V_opt (A18) — held outside the base band; stated values must reproduce.
    h_unal = op_value(inp, eop["h"], inp["g2_h"])
    opt = capacity_option(inp, h_unal)
    if opt["d_vol"] <= 0 or opt["v_opt"] < 0:
        errors.append(f"capacity option non-positive: d_vol={opt['d_vol']:.1f} V_opt={opt['v_opt']:.2f}")
    for key in ("hu_inv_pct", "dom_inv_pct", "opt_eq"):
        if not 0.0 <= inp[key] <= 1.0:
            errors.append(f"{key}={inp[key]} outside [0, 1]")
    if not 0.0 < opt["share_opt"] <= 1.0:
        errors.append(f"option share of in-construction volume {opt['share_opt']:.3f} outside (0, 1]")
    if inp["t_opt"] < inp["t_num"]:
        errors.append("t_opt must not precede the numerator year t_num")
    if any(k.startswith("p_") for k in inp):
        errors.append("probability fields present in §3 Inputs (A2e-7a)")
    band3 = tuple(base + P_K[i] * opt["v_opt"] for i, base in enumerate((L, M, H)))
    out_sec = outputs_section(md)
    vm = re.search(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if vm is None or abs(float(vm.group(1)) - opt["v_opt"]) > 0.05:
        errors.append(f"V_opt: stated {vm.group(1) if vm else None} vs recomputed {opt['v_opt']:.4f}")
    for k, v in zip("LMH", band3):
        m3 = re.search(rf"^\| {k} \| [0-9.]+ \| [^|]+\| [^|]+\| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - v) > 0.05:
            errors.append(f"table3 {k}: stated {m3.group(1) if m3 else None} vs recomputed {v:.4f}")
    a3, b3 = cut_points(*band3)
    for label, want, rx in (("A′", a3, r"A′ = \*\*([0-9.]+)\*\*"), ("B′", b3, r"B′ = \*\*([0-9.]+)\*\*")):
        mm = re.search(rx, out_sec)
        if mm is None or abs(float(mm.group(1)) - want) > 0.05:
            errors.append(f"{label}: stated {mm.group(1) if mm else None} vs recomputed {want:.4f}")

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  (r={r:.0%} = 篮 {baskets['r_perp']}, "
          f"零增长={1 / r:.1f}x, 无过渡段；回报三段 Y1 {inp['y1']:g} → Y2 {inp['y2']:g} 稳态 {inp['ronic_ss']:.1%}；"
          f"τ {inp['tau']:g} + 2H26 窗口利润；经营价值 + 超额现金，λ 1)")
    print(f"超额现金（A22）：扩展口径净现金 {inp['net_cash_ext_h1']:.2f} − 中期分红 {inp['div_declared']:.2f} "
          f"− 锚 {cash_anchor(inp):.2f}（min(FY2018–25 最低 {inp['cash_ratio_min']:.2%}, 2 个月 {ANCHOR_CAP:.2%}) "
          f"× FY2025 收入 {inp['rev_fy2025']:.2f}）− 增长期资金缺口 0 = {c_tot:.2f} × 归母比例 {pr:.4f} "
          f"= C_ex {c_ex:.2f} 亿 = {cps:.2f} 元/股，"
          f"占归母（扣中期分红）{c_ex / eq_adj:.1%}；税后收益 {c_ex * inp['cash_yield'] * (1 - inp['tax_eff']):.2f} 亿 "
          f"= {inc_ps:.3f} 元/股（收益率 {inp['cash_yield']:.2%}、税率 {inp['tax_eff']:.2%}）")
    print(f"{'档':<3}{'EPS':>8}{'E_op':>8}{'OBPS27':>8}{'RONIC':>8}{'g2':>6}{'PE三段':>8}"
          f"{'经营价值':>9}{'×折τ':>8}{'+窗口':>7}{'+现金':>7}{'锚点':>9}")
    for t in TIERS:
        g2 = inp[f"g2_{t}"]
        print(f"{t.upper():<3}{inp[f'eps_{t}']:8.3f}{eop[t]:8.3f}{obps_open[t]:8.2f}{ron[t]:8.2%}"
              f"{g2:6.1%}{pe[t]:8.2f}{eop[t] * pe[t]:9.2f}{eop[t] * pe[t] * dtau:8.2f}"
              f"{win[t] * (1 + r) ** -(inp['tau'] / 2):7.2f}{cps:7.2f}{anchor(inp, t):9.2f}"
              f"（单段 PE {perpetual_pe(g2, ron[t], r):.2f}；窗口 {unbooked_op_eps(inp):.2f}×(1−{g2 / ron[t]:.3f})）")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"RONIC basis (A21)：2Q26 经营 BPS {obps_2q26(inp):.2f}（归母 {inp['equity']:.2f} − 中期分红 "
          f"{inp['div_declared']:.2f} − C_ex {c_ex:.2f}）滚过 2H26 经营 EPS {n_op:.2f} @ b1 "
          f"{b1['l']:.3f}/{b1['m']:.3f}/{b1['h']:.3f} → {obps_open['l']:.2f}/{obps_open['m']:.2f}/{obps_open['h']:.2f}")
    print(f"约束 2：(1 − 实付 {inp['payout_3y']:.0%}) × RONIC = "
          f"{'/'.join(f'{(1 - inp['payout_3y']) * ron[t]:.1%}' for t in TIERS)} ≥ g2 ✓；"
          f"check_branch 用经营口径派息 {inp['payout_op']:.1%} ✓")
    keep = {t: (1.0 - inp["payout_3y"]) - b1[t] for t in TIERS}
    print(f"多留部分：比例 {'/'.join(f'{keep[t]:.1%}' for t in TIERS)}（1 − b1 − 实付 {inp['payout_3y']:.0%}）"
          f" × 2H26 经营 EPS {n_op:.2f} = {'/'.join(f'{keep[t] * n_op:.2f}' for t in TIERS)} 元/股（落在超额现金，λ 1，PV 不进锚点）")
    print(f"V_opt（A18）：建成后量 {opt['vol_full']:.1f} GWh − H 档共识隐含量 {opt['vol_in_h']:.1f} = "
          f"{opt['d_vol']:.1f} GWh × {inp['unit_profit_h1']:.2f} 元/kWh = {opt['d_ni']:.2f} 亿（ΔEPS {opt['d_eps']:.3f}）"
          f" → RONIC {opt['ronic_post']:.2%}、{inp['t_opt']:g} 年按日历路径 Y1 {inp['y1']:g} / Y2 {inp['y2']:g} 的 PE {opt['pe_post']:.3f}"
          f"（不含增量 {opt['pe_base']:.3f}）→ 兑现后锚点 {opt['anchor_post']:.2f} − 同年 H {opt['base_t']:.2f} "
          f"= {opt['anchor_post'] - opt['base_t']:.2f}（兑现年、未折）；未投资本 {opt['k_remain']:.2f} 亿 × {opt['share_opt']:.2%} × "
          f"{inp['opt_eq']:.2%} = {opt['k_ps']:.2f} 元/股 → ({opt['anchor_post'] - opt['base_t']:.2f} − {opt['k_ps']:.2f}) × "
          f"{opt['disc']:.4f} = {opt['v_opt']:.2f}；V_opt/M={opt['v_opt'] / M:.1%}")
    opt_fresh = capacity_option(inp, h_unal, fresh=True)
    print(f"  高回报期在兑现年重开（2026-10-19 前的隐含读法，只披露）：PE {opt_fresh['pe_post']:.3f} / {opt_fresh['pe_base']:.3f} "
          f"→ V_opt {opt_fresh['v_opt']:.2f}")
    if opt["pe_post"] > opt_fresh["pe_post"] + 1e-12:
        errors.append("calendar-path option multiple above the restarted one -- the fall cannot restart")
    print(f"表3 p_k={P_K[0]:g}/{P_K[1]:g}/{P_K[2]:g} → {band3[0]:.2f} / {band3[1]:.2f} / {band3[2]:.2f}  A′={a3:.2f} B′={b3:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(f"经营分子比 L/M={eop['l'] / eop['m']:.3f} H/M={eop['h'] / eop['m']:.3f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.3f} H/M={pe['h'] / pe['m']:.3f}")
    print(f"flat-multiple @PE_M={pe['m']:.2f}（含现金）: {flat[0]:.2f} / {flat[1]:.2f} / {flat[2]:.2f}")
    for y, (lo, hi, opr) in band.items():
        print(f"  经营倍数带 {y}: own-year PE {PE_OWN[y][0]}–{PE_OWN[y][1]} → {lo:.2f}–{hi:.2f}（经营利润/归母 {opr:.3f}）")
    g_lo = band_edge_g(inp, ron["m"], inp["pe_op_lo"])
    g_hi = band_edge_g(inp, ron["m"], inp["pe_op_hi"])
    print(f"三档经营 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} ∈ 经营带 [{inp['pe_op_lo']:g}, {inp['pe_op_hi']:g}]；"
          f"PE_H ≤ 2023 年起上沿 {inp['pe_op_hi_recent']:g} ✓；M 档带边反解 g [{g_lo:+.2%}, {g_hi:+.2%}"
          f"{'（截于上限）' if g_hi >= g_cap(r) - 1e-6 else ''}] 含 g2_m → ③ 不触发")
    cx = cex_hist(min(inp["cash_ratio_min"], ANCHOR_CAP))
    print(f"每股超额现金今昔：FY2022 末 {cx[2022]:.1f} 亿 / 今 {c_ex:.1f} 亿（差 > 1 倍，市场若对现金打折，历史经营倍数偏高）")

    def ruler(eop_x: float, g: float) -> float:
        return aligned(inp, eop_x, g)

    fy26 = tuple(ruler(e_op(inp, inp[k]), inp[f"g2_{t}"]) for k, t in
                 (("eps_fy26_lo", "l"), ("eps_fy26_mean", "m"), ("eps_fy26_hi", "h")))
    print(f"对照带（A19）FY2026E 三点 × 同一尺：{fy26[0]:.2f} / {fy26[1]:.2f} / {fy26[2]:.2f}"
          f"（Longbridge 合成 {inp['eps_fy26_lb']:.2f} → {ruler(e_op(inp, inp['eps_fy26_lb']), inp['g2_m']):.2f}）")
    freeze = ruler(e_op(inp, inp["eps_freeze_tax"]), inp["g2_l"])
    fy25_op = inp["eps_fy2025"] * band[2025][2]   # FY2025 actual net of ITS OWN C_ex(t) income
    fy25 = ruler(fy25_op, inp["g2_l"])
    print(f"压力坐标（deep_discount）：冻结×消费税 {inp['eps_freeze_tax']:.2f} → {freeze:.2f}；"
          f"FY2025 实测 {inp['eps_fy2025']:.2f}（经营 {fy25_op:.2f}）→ {fy25:.2f}")
    e26m, e26h = e_op(inp, inp["eps_fy26_mean"]), e_op(inp, inp["eps_fy26_hi"])
    r26m, r26h = ronic(inp, e26m, inp["g2_m"]), ronic(inp, e26h, inp["g2_h"])
    g1_m = inp["eps_m"] / inp["eps_fy26_mean"] - 1
    g1_h = inp["eps_h"] / inp["eps_fy26_hi"] - 1
    v1 = (two_stage_pe(g1_m, 1, inp["g2_m"], r26m, r) * e26m + cps,
          two_stage_pe(g1_h, 1, inp["g2_h"], r26h, r) * e26h + cps,
          two_stage_pe(0.20, 3, inp["g2_m"], r26m, r) * e26m + cps,
          two_stage_pe(0.27, 3, inp["g2_h"], r26h, r) * e26h + cps)
    print(f"v1 结构（已按 ② 收回）：n=1 g1 {g1_m:+.1%} / {g1_h:+.1%} → M {v1[0]:.0f} / H {v1[1]:.0f}；"
          f"n=3 20% / 27% → M {v1[2]:.2f} / H {v1[3]:.2f}")
    for dg in (-0.01, +0.01):
        alt = [ruler(eop[t], inp[f"g2_{t}"] + dg) for t in TIERS]
        print(f"敏感性 g2 三档 {dg:+.0%}：{alt[0]:.2f} / {alt[1]:.2f} / {alt[2]:.2f}"
              f"（A {(alt[0] + alt[1]) / 2:.1f} / B {(alt[1] + alt[2]) / 2:.1f}）")
    alt = [ruler(eop[t], inp["g2_m"]) for t in TIERS]
    print(f"敏感性 三档 g2 全置 {inp['g2_m']:.0%}：{alt[0]:.2f} / {alt[1]:.2f} / {alt[2]:.2f}")
    # window sensitivity: include pre-IPO FY2016–17 (ratio 4.6%, FY2016)
    for label, tweak in (
        ("锚窗口含上市前 FY2016–17", {"cash_ratio_min": min(EXT[y] / REV[y] for y in range(2016, 2026))}),
        ("受限资金代理全额按 λ=0", {"net_cash_ext_h1": inp["net_cash_ext_h1"] - inp["cash_restricted"]}),
    ):
        alt_inp = {**inp, **tweak}
        alt = [anchor(alt_inp, t) for t in TIERS]
        print(f"敏感性 {label}：C_ex {excess_cash(alt_inp):.1f} 亿 → {alt[0]:.2f} / {alt[1]:.2f} / {alt[2]:.2f}")
    print(f"地板（只披露）：PB=1.0 → BPS {inp['bps']:.2f} < L {L:.2f}（比值 {inp['bps'] / L:.3f}）；not max()'d")
    for label, px in (("本框架 M", M), ("本框架 H", H), ("高盛 TP", inp["tp_street"]), ("一致 TP", inp["tp_consensus"])):
        pe_op = (px - cps) / eop["m"]
        gi, ok = implied_g(pe_op, ron["m"], r)
        flag = "" if gi <= g_cap(r) else f"  （越 {g_cap(r):.0%} 上限）"
        print(f"  {label:<10} {px:7.2f}  FY2027E PE={px / inp['eps_m']:6.2f}  经营倍数={pe_op:6.2f}"
              f"  隐含永续 g={gi:+.1%} well_conditioned={ok}{flag}")
    print(f"  股本口径（A17，不进锚点）：回购 {inp['buyback_lo']:.0f}–{inp['buyback_hi']:.0f} 亿注销；"
          f"激励 +{inp['opt_outstanding'] / sh:.3%}；库存股 {inp['treasury_shares'] / sh:.3%}")
    print(f"  单位净利 FY2025 {inp['unit_profit_fy2025']:.1f} → 2026H1 {inp['unit_profit_h1']:.2f} 元/kWh "
          f"({inp['unit_profit_h1'] / inp['unit_profit_fy2025'] - 1:+.1%})")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
