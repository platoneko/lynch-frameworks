#!/usr/bin/env python3
"""600031.SH (Sany Heavy Industry) valuation eval — recompute anchors from frameworks/600031.SH.md.

frameworks/600031.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading.

formula_id: sany_consensus_fy28_print_match_gordon_v2

Main ruler: whole company (construction machinery; segments share one driver,
no sell-side SOTP), basket 4 r = 10%.  Operating value + excess cash
(valuation-rules「经营价值与超额现金」, 2026-10-15): every earnings figure, ROE
and historical multiple below is on the operating basis (excess cash and its
after-tax income taken out); the excess cash is added back per share at face
value (lambda = 1) on every tier.

  numerator  FY2028 company consensus (Eastmoney / 10jqka F10, 17 houses
             published after the 2026-08-31 interim report): M = mean,
             H = high.  Demand-cycle manufacturing → the commodity「中枢」rule
             does not apply; M / H stay on consensus and the cycle risk sits in
             L.  FY2028 = current FY2026 + 2 → discounted one year at r.
  g2         source layer = own same-earnings months (valuation-rules 裁决顺序
             ④, cyclical): months whose visible TTM net profit sits within
             ±12% of the tier's FY2028 net profit, each month's trailing PE
             reverse-solved on the retention branch at that month's ROE, median
             of the well-conditioned months.  The peer layer is empty: XCMG
             prices below 1/r on a monotone-zone ROE (unreachable), Zoomlion /
             Liugong / Komatsu sit in the flat zone (cross-domain), CAT is
             another country.  Operating basis: price and EPS net of the excess
             cash visible then.  M 2.85% / H 2.55% — H <= M (the market does
             not pay up for peak earnings).
  RONIC      FY2028 operating EPS over the start-of-2028 operating BPS
             (book − excess cash) rolled from 2026-06-30 with b = g/RONIC.
  L          FY2022 trough operating profit on recovery_two_stage_pe: own
             realised recovery to the TTM operating level over 3.5 years, then
             the M-tier g2 at the TTM operating ROE.  Not discounted.
  cash       excess cash = extended net cash − declared unpaid dividend −
             anchor 0, added per share to every tier.
  ③          the M multiple must sit inside the same-earnings band (it is
             generated from that band, so this is a consistency check).

2026-10-16 framework correction (valuation-rules「经营价值与超额现金」):
  * parent share of the excess cash 98.81% (parent / (parent + minority), no
    subsidiary cash disclosure); it scales C_ex, its income and the book.
  * time alignment: the Gordon value sits at 2028-01-01 -> x (1+r)^-tau,
    tau 1.5 from the 2026-06-30 balance sheet (replaces the whole-year
    discount), plus the window distributable profit (2H26 + FY2027 unbooked
    operating EPS x (1 - g/RONIC)) at tau/2.  L (trough from today) n/a.
  * three-stage return: forward RONIC through Y1 2028, linear to the steady
    return by Y2 2032, perpetual after.
  * g2 pairing: the same-earnings months are re-solved on the same aligned
    ruler — each month's operating multiple = path_PE(g, month ROE) x
    1.1^-tau + u x (1 - g/ROE) x 1.1^-(tau/2), u = the tier's unbooked
    window EPS / FY2028 operating EPS — median of the well-posed months.
  * k = 0 on every tier (no k on this ticker).

2026-10-19 framework correction (retention.md「稳态回报三段」taken in order,
user-approved 2026-10-19): steady = own cycle, the latest complete
trough-to-trough cycle FY2016-23 on the invested-capital basis, mean 17.9%.
Caterpillar / Deere dropped (competitive arena is domestic); domestic peers
XCMG 9.3-11.5% / Liugong 6.8% (Zoomlion in decline) and the floor 15% are
comparisons only.  The path now bites (forward M 22.8% / H 25.0% > 17.9%), so
g2 is re-solved on the same path (pairing): M 4.37% / H 3.97%.

V_opt = 0: electrification, mining and overseas expansion are inside the
consensus years.  CNY segment of _AXIS.rates is [待建] → no r_f readings.

Run:  python3 frameworks/eval/600031.SH.py
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, implied_g_retaining, payout, payout_gap,
    perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600031.SH.md"
FORMULA_ID = "sany_consensus_fy28_print_match_gordon_v2"
YI = 1e8
NUM_YEAR = 2028
TODAY_FY = 2026
TOL = 0.05
PAIR_BAND = 0.12          # same-earnings window, valuation-rules 裁决顺序 ④
MIN_GOOD = 6
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3
G2_PREV = {"m": 0.034720, "h": 0.031965}   # g2 before the 2026-10-19 correction (switch-effect reading only)

# Same-earnings months (A-share monthly close, unadjusted; TTM EPS = the latest
# report visible at month end; BPS same report; shares then 84.9亿).  Built by
# frameworks/_local/tmp/600031/mkt/calc_hist.py from Longbridge monthly klines
# and Eastmoney quarterly EPS (2026-10-13).  Only these months fall within ±12%
# of the M or H numerator; the selection below re-checks that.
SHARES_THEN = 84.9e8
# Excess cash visible at each month end (extended net cash of the then-latest
# report, anchor 0; quarterly interest-bearing other current liabilities at the
# annual 0.72 share) and its after-tax yield then (cash yield ~4.5%, tax ~13%).
CEX_THEN = {"Q3-20": 63.9e8, "FY20": 82.37e8, "Q1-21": 74.3e8, "H1-21": 92.0e8, "Q3-21": 62.5e8}
YIELD_THEN = 0.045 * (1 - 0.13)
MONTHS = [  # (month, close, ttm_eps, bps, visible report)
    ("2020-10", 25.95, 1.7192, 6.2963, "Q3-20"), ("2020-11", 30.71, 1.7192, 6.2963, "Q3-20"),
    ("2020-12", 34.98, 1.7192, 6.2963, "Q3-20"), ("2021-01", 40.46, 1.7192, 6.2963, "Q3-20"),
    ("2021-02", 41.11, 1.7192, 6.2963, "Q3-20"), ("2021-03", 34.15, 1.8401, 6.6713, "FY20"),
    ("2021-04", 30.88, 2.2311, 7.3216, "Q1-21"), ("2021-05", 30.29, 2.2311, 7.3216, "Q1-21"),
    ("2021-06", 29.07, 2.2311, 7.3216, "Q1-21"), ("2021-07", 24.82, 2.2311, 7.3216, "Q1-21"),
    ("2021-08", 26.23, 2.0169, 7.2871, "H1-21"), ("2021-09", 25.44, 2.0169, 7.2871, "H1-21"),
    ("2021-10", 22.96, 1.8572, 7.5577, "Q3-21"), ("2021-11", 21.90, 1.8572, 7.5577, "Q3-21"),
    ("2021-12", 22.80, 1.8572, 7.5577, "Q3-21"), ("2022-01", 20.14, 1.8572, 7.5577, "Q3-21"),
    ("2022-02", 19.61, 1.8572, 7.5577, "Q3-21"), ("2022-03", 17.52, 1.8572, 7.5577, "Q3-21"),
]

REQUIRED = [
    "shares", "bps", "np_h1", "cons_np26_m", "cons_np26_h", "cons_np27_l", "cons_np27_m", "cons_np27_h",
    "cons_np28_l", "cons_np28_m", "cons_np28_h", "np_l", "np_ttm", "equity", "n_rec_l",
    "np_fy22", "np_fy25", "np_mid10", "np_peak_own", "np_2016",
    "r_perp", "g2_m", "g2_h", "payout_obs", "payout_op", "k_l", "k_m", "k_h", "tau",
    "minority_h1", "parent_ratio", "y1", "y2", "ronic_own", "ronic_own_1925", "ronic_own_2125", "ronic_ss_floor", "ronic_ss",
    "pe_band_min", "pe_band_max", "pb_own_min",
    "net_debt", "net_debt_ext", "ebitda", "ebit", "interest",
    "net_cash_ext_h1", "div_declared", "c_ex", "cash_yield", "tax_eff",
]


def path_pe(g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段) at the start of NUM_YEAR per unit
    of NUM_YEAR earnings: RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after."""
    if r - g <= 0:
        raise ValueError("r <= g")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = NUM_YEAR + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g, ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def aligned_solver(u: float, r: float, tau: float, y1: int, y2: int, r_ss: float):
    """g such that today's operating value / FY2028 operating earnings on this ruler (path PE x
    (1+r)^-tau + window share u x (1 − g/ROE) x (1+r)^-(tau/2)) equals a month's operating multiple
    (valuation-rules ②-3 历史反解同口径 + ③ 时点对齐)."""
    def f(g: float, roe: float) -> float:
        return path_pe(g, roe, r, y1, y2, r_ss) * (1 + r) ** -tau + u * (1 - g / roe) * (1 + r) ** -(tau / 2)

    def solve(pe: float, roe: float) -> tuple[float, bool]:
        lo, hi = -0.5, r - 1e-6
        if not (f(lo, roe) <= pe <= f(hi, roe)):
            return float("nan"), False
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid, roe) < pe:
                lo = mid
            else:
                hi = mid
        g = (lo + hi) / 2
        return g, 0.0 <= g < r
    return solve


def print_match(target_np: float, r: float, solve=None) -> tuple[list[tuple[str, float, float, float, bool]], float | None]:
    """Same-earnings months on the operating basis: price and EPS net of the
    excess cash visible then, ROE on equity net of it.  `solve(pe, roe)` reverse-solves
    g on the framework's ruler (default: the single-stage retention Gordon)."""
    lo, hi = target_np * (1 - PAIR_BAND), target_np * (1 + PAIR_BAND)
    rows = []
    for month, close, eps, bps, rep in MONTHS:
        cps = CEX_THEN[rep] / SHARES_THEN
        eps_op = eps - cps * YIELD_THEN
        if not lo <= eps_op * SHARES_THEN <= hi:
            continue
        pe, roe = (close - cps) / eps_op, eps_op / (bps - cps)
        g, ok = solve(pe, roe) if solve else implied_g_retaining(pe, roe, r)
        rows.append((month, pe, roe, g, ok))
    good = [g for *_, g, ok in rows if ok]
    return rows, (statistics.median(good) if len(good) >= MIN_GOOD else None)


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
    r, sh = inp["r_perp"], inp["shares"]

    # --- basket, g ----------------------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for k in ("g2_m", "g2_h"):
        errors += check_g_cap(inp[k], r, k)
    tau = inp["tau"]
    if abs(tau - ((NUM_YEAR - TODAY_FY) * 12 - 6) / 12) > 1e-9:
        errors.append(f"tau {tau:g} != 2026-06-30 → {NUM_YEAR}-01-01 in years")
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    if not (y1 == NUM_YEAR and y2 == y1 + 4):
        errors.append("Y1 must be the visible-year end FY2028 and Y2 = Y1 + 4 (medium entry barrier)")
    # steady return in order (retention.md 2026-10-19): own cycle usable -> own; peers / floor are comparisons
    if abs(inp["ronic_ss"] - inp["ronic_own"]) > 5e-4:
        errors.append(f"ronic_ss {inp['ronic_ss']} != own trough-to-trough cycle {inp['ronic_own']}")
    r_ss = inp["ronic_ss"]
    errors += ladder("FY2028 consensus", inp["cons_np28_l"], inp["cons_np28_m"], inp["cons_np28_h"])
    if not (inp["k_h"] >= inp["k_m"] >= inp["k_l"]):
        errors.append("cyclical k must satisfy k_H >= k_M >= k_L")

    # --- excess cash (经营价值与超额现金 ①②) ------------------------------------------
    c_tot = inp["net_cash_ext_h1"] - inp["div_declared"]  # anchor 0 (A15)
    if abs(c_tot - inp["c_ex"]) > 1e6:
        errors.append(f"c_ex {inp['c_ex']:.4e} != net_cash_ext_h1 − div_declared {c_tot:.4e}")
    pr = inp["equity"] / (inp["equity"] + inp["minority_h1"])   # ① 归母份额: no subsidiary cash disclosure
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = c_tot * pr
    if c_ex < 0.15 * inp["equity"]:
        errors.append("c_ex below 15% of equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])  # after-tax income, taken out of every numerator
    cps = c_ex / sh
    op = {t: tuple((inp[f"cons_np{y}_{t}"] - c_inc) / sh for y in (26, 27, 28)) for t in ("m", "h")}
    eps_h1 = (inp["np_h1"] - c_inc / 2) / sh
    unb = {t: (op[t][0] - eps_h1) + op[t][1] for t in ("m", "h")}   # unbooked window EPS, 2H26 + FY2027

    # --- g2 from same-earnings months (自身市场读数，经营口径，同一时点对齐的尺) ---------------
    pm = {}
    for t in ("m", "h"):
        rows, med = print_match(op[t][2] * sh, r, aligned_solver(unb[t] / op[t][2], r, tau, y1, y2, r_ss))
        pm[t] = (rows, med)
        if med is None:
            errors.append(f"{t.upper()}: fewer than {MIN_GOOD} well-conditioned same-earnings months")
        elif abs(med - inp[f"g2_{t}"]) > 5e-5:
            errors.append(f"g2_{t} {inp[f'g2_{t}']} != same-earnings median {med:.5f}")
    if not inp["g2_h"] <= inp["g2_m"]:
        errors.append("g2_h must be <= g2_m (裁决顺序 ④: H 档 g <= M 档)")
    m_pes = [pe for _, pe, *_ in pm["m"][0]]
    if abs(min(m_pes) - inp["pe_band_min"]) > 0.01 or abs(max(m_pes) - inp["pe_band_max"]) > 0.01:
        errors.append(f"pe_band_min/max {inp['pe_band_min']}/{inp['pe_band_max']} != M-window months "
                      f"{min(m_pes):.2f}/{max(m_pes):.2f}")
    # same-world gate: numerator year is the furthest consensus year → own >= 3y NP CAGR
    cagr = (inp["np_fy25"] / inp["np_fy22"]) ** (1 / 3) - 1
    if cagr > 0 and min(inp["g2_m"], inp["g2_h"]) <= 0:
        errors.append("同世界门: own FY2022→25 NP rises but a g2 <= 0")
    if errors:
        return report(errors, "FAIL (basket / g)")

    # --- M / H ---------------------------------------------------------------------
    disc = (1 + r) ** tau
    disc_w = (1 + r) ** (tau / 2)
    obps = inp["bps"] - cps  # operating book per share (equity − excess cash)

    def tier(t: str, g: float, rs: float | None = None) -> dict:
        e26, e27, e28 = op[t]
        roe = e28 / obps
        for _ in range(300):  # operating BPS roll, b = g/RONIC (③ 步 2)
            bps28 = obps + g / roe * unb[t]
            roe = e28 / bps28
        pe = path_pe(g, roe, r, y1, y2, r_ss if rs is None else rs)
        w = max(unb[t] * (1 - g / roe), 0.0) / disc_w   # window distributable profit (③ 时点对齐)
        return dict(eps=e28, roe=roe, bps=bps28, pe=pe, w=w, pe_1=perpetual_pe(g, roe, r),
                    anchor=e28 * pe * (1 - inp[f"k_{t}"]) / disc + w + cps)

    rows = {t: tier(t, inp[f"g2_{t}"]) for t in ("m", "h")}
    for t in ("m", "h"):
        if rows[t]["roe"] - r < 0.03:
            errors.append(f"{t.upper()}: RONIC {rows[t]['roe']:.1%} not in the monotone zone — revisit the domain")
        errors += check_branch(inp[f"g2_{t}"], rows[t]["roe"], r, inp["payout_op"], f"g2_{t}")

    # --- L: trough + own realised recovery (operating basis) ---------------------------
    np_ttm_op, eq_op = inp["np_ttm"] - c_inc, inp["equity"] - c_ex
    roe_mid = np_ttm_op / eq_op
    if inp["np_l"] / eq_op >= r:
        errors.append("ROE_L >= r: L is not a trough tier")
    g1 = (np_ttm_op / inp["np_l"]) ** (1 / inp["n_rec_l"]) - 1
    pe_l = recovery_two_stage_pe(g1, inp["n_rec_l"], inp["g2_m"], roe_mid, r)
    # RONIC_mid sits within r + 3pp, so check_branch also tests the payout gap.
    # The gap is the retained-over-b share, and it lands in the excess cash already
    # split out (λ = 1, A15) → valuation-rules「分支差的合法解释」: report, do not fail.
    # The sign test (g > 0 while the company retains) still applies.
    tail_branch = check_branch(inp["g2_m"], roe_mid, r, inp["payout_op"], "g2 (L tail)")
    if inp["g2_m"] <= 0 or inp["payout_op"] >= 0.95:
        errors += tail_branch
    tail_gap = payout_gap(inp["g2_m"], roe_mid, inp["payout_op"])
    L = inp["np_l"] / sh * pe_l * (1 - inp["k_l"]) + cps
    M, H = rows["m"]["anchor"], rows["h"]["anchor"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # shape (裁决顺序 ⑤): cyclical multiples reverse or flat
    if not (pe_l >= rows["m"]["pe"] >= rows["h"]["pe"] - 1e-9):
        errors.append("multiple shape is not reverse/flat (cyclical, 裁决顺序 ⑤)")
    flat = [inp["np_l"] / sh * rows["m"]["pe"] + cps] + [rows[t]["eps"] * rows["m"]["pe"] / disc + rows[t]["w"] + cps
                                                          for t in ("m", "h")]
    errors += ladder("flat-multiple", *flat)
    # ③ today's operating value / operating earnings (the guard's reading) must sit inside the band
    mult_m = (M - cps) / rows["m"]["eps"]
    if not inp["pe_band_min"] <= mult_m <= inp["pe_band_max"]:
        errors.append(f"③ M operating value / E28 {mult_m:.2f} outside same-earnings band "
                      f"[{inp['pe_band_min']}, {inp['pe_band_max']}]")
    for t in ("m", "h"):
        if abs(rows[t]["pe"] - rows[t]["pe_1"]) > 1e-9 and rows[t]["roe"] <= r_ss:
            errors.append(f"{t.upper()}: path PE differs from single-stage although RONIC <= steady")
    # leverage gate
    lev1, lev2 = inp["net_debt"] / inp["ebitda"], inp["interest"] / inp["ebit"]
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append("leverage gate triggered — ROE decomposition / ROIC branch required")

    # --- report ------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} r={r:g}; FY{NUM_YEAR} consensus ÷1.1^{tau:g} = ÷{disc:.3f} + window ÷1.1^{tau / 2:g}; "
          f"同世界门 own FY22→25 NP CAGR {cagr:+.1%}")
    print(f"三段回报: 前瞻 M {rows['m']['roe']:.1%} / H {rows['h']['roe']:.1%} 维持到 Y1 {y1}，Y2 {y2} 线性回落到稳态 {r_ss:.1%}"
          f"（自身最近一轮谷到谷 FY2016–23 投入资本口径均值；兜底 {inp['ronic_ss_floor']:.0%} 只作对照）"
          f"；倍数 M {rows['m']['pe']:.2f}（单段 {rows['m']['pe_1']:.2f}）/ H {rows['h']['pe']:.2f}（单段 {rows['h']['pe_1']:.2f}）")
    print(f"超额现金: 扩展口径净现金 {inp['net_cash_ext_h1'] / YI:.2f}亿 − 已宣派未付股息 {inp['div_declared'] / YI:.2f}亿 "
          f"− 锚 0 − 增长期资金缺口 0 = {c_tot / YI:.2f}亿 × 归母比例 {pr:.4f} = C_ex {c_ex / YI:.2f}亿（每股 {cps:.3f}，占归母权益 {c_ex / inp['equity']:.1%}，λ 1）；"
          f"税后收益 {c_inc / YI:.2f}亿 从各档分子扣除")
    for t in ("m", "h"):
        rws, med = pm[t]
        good = [g for *_, g, ok in rws if ok]
        print(f"print-match {t.upper()} (经营利润 {op[t][2] * sh / YI:.2f}亿 ±12%): {len(good)}/{len(rws)} good, "
              f"median g {med:.4%} range [{min(good):.2%}, {max(good):.2%}]")
        for month, pe, roe, g, ok in rws:
            print(f"    {month} PE {pe:5.2f} ROE {roe:.1%} g {g:+.2%}{'' if ok else ' (ill)'}")
    for t in ("m", "h"):
        x = rows[t]
        print(f"{t.upper()}: 经营EPS28 {x['eps']:.4f} 经营BPS28 {x['bps']:.3f} RONIC {x['roe']:.2%} g {inp[f'g2_{t}']:.2%} "
              f"PE {x['pe']:.2f} payout_model {payout(inp[f'g2_{t}'], x['roe']):.1%} | 经营价值 {x['eps'] * x['pe'] / disc:.2f} "
              f"+ 窗口 {unb[t]:.3f}x(1−{inp[f'g2_{t}'] / x['roe']:.3f})÷1.1^{tau / 2:g} {x['w']:.2f} + 现金 {cps:.2f} -> {x['anchor']:.2f}"
              f"（今天经营价值/E28 {(x['anchor'] - cps) / x['eps']:.2f}）")
    print(f"L: trough 经营利润 {inp['np_l'] / YI:.2f}亿 x recovery PE {pe_l:.2f} (g1 {g1:+.2%} n {inp['n_rec_l']:g}, "
          f"段二 RONIC {roe_mid:.2%} g {inp['g2_m']:.2%}) + 现金 {cps:.2f} -> {L:.2f}")
    print(f"L 段二分支差（披露）: 模型派息 {tail_gap[0]:.1%} vs 经营口径 {inp['payout_op']:.1%}（差 {tail_gap[1]:+.1%}；"
          f"多留部分落在已单列超额现金，λ 1）")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    np_m = inp["cons_np28_m"]
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%} V_opt/M=0% | "
          f"分子比 L/M {inp['np_l'] / np_m:.2f} H/M {inp['cons_np28_h'] / np_m:.3f} | "
          f"倍数 L/M/H {pe_l:.2f}/{rows['m']['pe']:.2f}/{rows['h']['pe']:.2f}")
    print(f"flat-multiple (M-tier PE): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"③ M 今天经营价值/E28 {mult_m:.2f} in same-earnings band [{inp['pe_band_min']}, {inp['pe_band_max']}]")

    # evidence interval for g2_m: [g2_h, the g where M reaches H]
    lo, hi = inp["g2_h"], 0.06
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tier("m", mid)["anchor"] < H else (lo, mid)
    m_lo, m_hi = tier("m", inp["g2_h"])["anchor"], tier("m", lo)["anchor"]
    print(f"g2_m evidence interval [{inp['g2_h']:.2%}, {lo:.2%}] -> M {m_lo:.2f}–{m_hi:.2f}")

    def band(dg: float) -> str:
        ll = inp["np_l"] / sh * recovery_two_stage_pe(g1, inp["n_rec_l"], inp["g2_m"] + dg, roe_mid, r) + cps
        return f"{ll:.2f}/{tier('m', inp['g2_m'] + dg)['anchor']:.2f}/{tier('h', inp['g2_h'] + dg)['anchor']:.2f}"
    print(f"敏感性 g2 −1pp {band(-0.01)} | +1pp {band(0.01)}")

    # steady-return sensitivity: g2 re-solved on the same path (配对), L takes the re-solved M-tier g2
    def at_ss(rs: float) -> str:
        gs = {t: print_match(op[t][2] * sh, r, aligned_solver(unb[t] / op[t][2], r, tau, y1, y2, rs))[1] for t in ("m", "h")}
        if None in gs.values() or max(gs.values()) > min(0.06, r - 0.04):
            return f"g2 无解或超上限（M {gs['m']} / H {gs['h']}）"
        ll = inp["np_l"] / sh * recovery_two_stage_pe(g1, inp["n_rec_l"], gs["m"], roe_mid, r) + cps
        return (f"g2 {gs['m']:.2%}/{gs['h']:.2%} -> {ll:.2f}/{tier('m', gs['m'], rs)['anchor']:.2f}/"
                f"{tier('h', gs['h'], rs)['anchor']:.2f}")
    for lab, rs in (("兜底 15%", inp["ronic_ss_floor"]), ("自身 FY2021–25", inp["ronic_own_2125"]),
                    ("自身 FY2019–25", inp["ronic_own_1925"])):
        print(f"敏感性 稳态 {lab} {rs:.1%}（g2 重解）: {at_ss(rs)}")
    # switch effect without re-pairing: g2 held at the pre-2026-10-19 values (steady 36.8% did not bite)
    for rs in (r_ss, inp["ronic_ss_floor"]):
        print(f"敏感性 g2 不重解（停在 {G2_PREV['m']:.2%} / {G2_PREV['h']:.2%}）稳态 {rs:.1%}: "
              f"M {tier('m', G2_PREV['m'], rs)['anchor']:.2f} / H {tier('h', G2_PREV['h'], rs)['anchor']:.2f}")
    print(f"M 分子换 FY2028 下沿 {inp['cons_np28_l'] / YI:.2f}亿 -> M "
          f"{(inp['cons_np28_l'] - c_inc) / sh * rows['m']['pe'] / disc + rows['m']['w'] + cps:.2f}")
    print(f"H 坐标·自身实测利润高点 {inp['np_peak_own'] / YI:.1f}亿 x H PE -> "
          f"{inp['np_peak_own'] / sh * rows['h']['pe'] / disc + rows['h']['w'] + cps:.2f}")
    mid_ratio = np_m / inp["np_mid10"]
    print(f"周期位置: FY28 M NP / 10y mean {inp['np_mid10'] / YI:.1f}亿 = {mid_ratio:.2f}x (demand-cycle, disclosure); "
          f"中枢坐标 10y mean x 1/r = {inp['np_mid10'] / sh / r:.2f}")
    print(f"压力坐标 谷底 x 1/r = {inp['np_l'] / sh / r:.2f}; FY2016 x 1/r = {inp['np_2016'] / sh / r:.2f}; "
          f"地板 PB {inp['pb_own_min']} x BPS = {inp['bps'] * inp['pb_own_min']:.2f}, PB 1.0 = {inp['bps']:.2f}")
    mod, gap = payout_gap(inp["g2_m"], rows["m"]["roe"], inp["payout_op"])
    excess = (1 - inp["payout_obs"]) - inp["g2_m"] / rows["m"]["roe"]
    win = unb["m"]
    print(f"payout: model {mod:.1%} vs 经营口径 {inp['payout_op']:.1%} (gap {gap:+.1%}); 实付现金派息 {inp['payout_obs']:.1%}; "
          f"多留部分 = {excess:.1%} x 窗口经营 EPS {win:.3f} = {excess * win:.2f}/sh（落在超额现金，λ 1，PV 不进锚点）")
    print(f"杠杆门: 净债/EBITDA {lev1:.2f} (扩展口径 {inp['net_debt_ext'] / inp['ebitda']:.2f}), "
          f"利息/EBIT {lev2:.1%} -> {'triggered' if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT else 'not triggered'}")
    print(f"证伪线 FY2027 NP 下沿 {inp['cons_np27_l'] / YI:.2f}亿")
    print("r_f: CNY segment of _AXIS.rates [待建] — no readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
