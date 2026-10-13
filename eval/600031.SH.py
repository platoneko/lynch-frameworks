#!/usr/bin/env python3
"""600031.SH (Sany Heavy Industry) valuation eval — recompute anchors from frameworks/600031.SH.md.

frameworks/600031.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading.

formula_id: sany_consensus_fy28_print_match_gordon_v1

Main ruler: whole company (construction machinery; segments share one driver,
no sell-side SOTP), basket 4 r = 10%.

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
             another country.  M 3.20% / H 2.85% — H <= M (the market does not
             pay up for peak earnings).
  ROE        FY2028 EPS over the start-of-2028 BPS rolled from the 2026-06-30
             book with b = g/ROE (valuation-rules ③ 步 2).
  L          FY2022 trough net profit on recovery_two_stage_pe: own realised
             recovery to the TTM level over 3.5 years, then the M-tier g2 at
             the TTM ROE.  Not discounted (trough year = t=1).
  ③          the M multiple must sit inside the same-earnings band (it is
             generated from that band, so this is a consistency check).

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
FORMULA_ID = "sany_consensus_fy28_print_match_gordon_v1"
YI = 1e8
NUM_YEAR = 2028
TODAY_FY = 2026
TOL = 0.05
PAIR_BAND = 0.12          # same-earnings window, valuation-rules 裁决顺序 ④
MIN_GOOD = 6
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3

# Same-earnings months (A-share monthly close, unadjusted; TTM EPS = the latest
# report visible at month end; BPS same report; shares then 84.9亿).  Built by
# frameworks/_local/tmp/600031/mkt/calc_hist.py from Longbridge monthly klines
# and Eastmoney quarterly EPS (2026-10-13).  Only these months fall within ±12%
# of the M or H numerator; the selection below re-checks that.
SHARES_THEN = 84.9e8
MONTHS = [  # (month, close, ttm_eps, bps)
    ("2020-10", 25.95, 1.7192, 6.2963), ("2020-11", 30.71, 1.7192, 6.2963),
    ("2020-12", 34.98, 1.7192, 6.2963), ("2021-01", 40.46, 1.7192, 6.2963),
    ("2021-02", 41.11, 1.7192, 6.2963), ("2021-03", 34.15, 1.8401, 6.6713),
    ("2021-04", 30.88, 2.2311, 7.3216), ("2021-05", 30.29, 2.2311, 7.3216),
    ("2021-06", 29.07, 2.2311, 7.3216), ("2021-07", 24.82, 2.2311, 7.3216),
    ("2021-08", 26.23, 2.0169, 7.2871), ("2021-09", 25.44, 2.0169, 7.2871),
    ("2021-10", 22.96, 1.8572, 7.5577), ("2021-11", 21.90, 1.8572, 7.5577),
    ("2021-12", 22.80, 1.8572, 7.5577), ("2022-01", 20.14, 1.8572, 7.5577),
    ("2022-02", 19.61, 1.8572, 7.5577), ("2022-03", 17.52, 1.8572, 7.5577),
]

REQUIRED = [
    "shares", "bps", "np_h1", "cons_np26_m", "cons_np26_h", "cons_np27_l", "cons_np27_m", "cons_np27_h",
    "cons_np28_l", "cons_np28_m", "cons_np28_h", "np_l", "np_ttm", "equity", "n_rec_l",
    "np_fy22", "np_fy25", "np_mid10", "np_peak_own", "np_2016",
    "r_perp", "g2_m", "g2_h", "payout_obs", "k_l", "k_m", "k_h", "disc_years",
    "pe_band_min", "pe_band_max", "pb_own_min",
    "net_debt", "net_debt_ext", "ebitda", "ebit", "interest",
]


def print_match(target_np: float, r: float) -> tuple[list[tuple[str, float, float, float, bool]], float | None]:
    lo, hi = target_np * (1 - PAIR_BAND), target_np * (1 + PAIR_BAND)
    rows = []
    for month, close, eps, bps in MONTHS:
        if not lo <= eps * SHARES_THEN <= hi:
            continue
        pe, roe = close / eps, eps / bps
        g, ok = implied_g_retaining(pe, roe, r)
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
    if int(inp["disc_years"]) != NUM_YEAR - TODAY_FY - 1:
        errors.append(f"disc_years {inp['disc_years']:g} != FY{NUM_YEAR} - (FY{TODAY_FY}+1)")
    errors += ladder("FY2028 consensus", inp["cons_np28_l"], inp["cons_np28_m"], inp["cons_np28_h"])
    if not (inp["k_h"] >= inp["k_m"] >= inp["k_l"]):
        errors.append("cyclical k must satisfy k_H >= k_M >= k_L")

    # --- g2 from same-earnings months (裁决顺序 ④ 第四层) ---------------------------
    pm = {}
    for t in ("m", "h"):
        rows, med = print_match(inp[f"cons_np28_{t}"], r)
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
    disc = (1 + r) ** inp["disc_years"]
    eps_h1 = inp["np_h1"] / sh
    cons = {t: tuple(inp[f"cons_np{y}_{t}"] / sh for y in (26, 27, 28)) for t in ("m", "h")}

    def tier(t: str, g: float) -> dict:
        e26, e27, e28 = cons[t]
        roe = e28 / inp["bps"]
        for _ in range(200):  # BPS roll, b = g/ROE (③ 步 2)
            bps28 = inp["bps"] + g / roe * ((e26 - eps_h1) + e27)
            roe = e28 / bps28
        pe = perpetual_pe(g, roe, r)
        return dict(eps=e28, roe=roe, bps=bps28, pe=pe, anchor=e28 * pe * (1 - inp[f"k_{t}"]) / disc)

    rows = {t: tier(t, inp[f"g2_{t}"]) for t in ("m", "h")}
    for t in ("m", "h"):
        if rows[t]["roe"] - r < 0.03:
            errors.append(f"{t.upper()}: ROE {rows[t]['roe']:.1%} not in the monotone zone — revisit the domain")
        errors += check_branch(inp[f"g2_{t}"], rows[t]["roe"], r, inp["payout_obs"], f"g2_{t}")

    # --- L: trough + own realised recovery -------------------------------------------
    roe_mid = inp["np_ttm"] / inp["equity"]
    if inp["np_l"] / inp["equity"] >= r:
        errors.append("ROE_L >= r: L is not a trough tier")
    g1 = (inp["np_ttm"] / inp["np_l"]) ** (1 / inp["n_rec_l"]) - 1
    pe_l = recovery_two_stage_pe(g1, inp["n_rec_l"], inp["g2_m"], roe_mid, r)
    errors += check_branch(inp["g2_m"], roe_mid, r, inp["payout_obs"], "g2 (L tail)")
    L = inp["np_l"] / sh * pe_l * (1 - inp["k_l"])
    M, H = rows["m"]["anchor"], rows["h"]["anchor"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # shape (裁决顺序 ⑤): cyclical multiples reverse or flat
    if not (pe_l >= rows["m"]["pe"] >= rows["h"]["pe"] - 1e-9):
        errors.append("multiple shape is not reverse/flat (cyclical, 裁决顺序 ⑤)")
    flat = [inp["np_l"] / sh * rows["m"]["pe"]] + [rows[t]["eps"] * rows["m"]["pe"] / disc for t in ("m", "h")]
    errors += ladder("flat-multiple", *flat)
    # ③ the generated M multiple must sit inside the same-earnings band
    if not inp["pe_band_min"] <= rows["m"]["pe"] <= inp["pe_band_max"]:
        errors.append(f"③ M multiple {rows['m']['pe']:.2f} outside same-earnings band "
                      f"[{inp['pe_band_min']}, {inp['pe_band_max']}]")
    # leverage gate
    lev1, lev2 = inp["net_debt"] / inp["ebitda"], inp["interest"] / inp["ebit"]
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append("leverage gate triggered — ROE decomposition / ROIC branch required")

    # --- report ------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} r={r:g}; FY{NUM_YEAR} consensus ÷{disc:.2f}; "
          f"同世界门 own FY22→25 NP CAGR {cagr:+.1%}")
    for t in ("m", "h"):
        rws, med = pm[t]
        good = [g for *_, g, ok in rws if ok]
        print(f"print-match {t.upper()} (NP {inp[f'cons_np28_{t}'] / YI:.2f}亿 ±12%): {len(good)}/{len(rws)} good, "
              f"median g {med:.4%} range [{min(good):.2%}, {max(good):.2%}]")
        for month, pe, roe, g, ok in rws:
            print(f"    {month} PE {pe:5.2f} ROE {roe:.1%} g {g:+.2%}{'' if ok else ' (ill)'}")
    for t in ("m", "h"):
        x = rows[t]
        print(f"{t.upper()}: EPS28 {x['eps']:.4f} BPS28 {x['bps']:.3f} ROE {x['roe']:.2%} g {inp[f'g2_{t}']:.2%} "
              f"PE {x['pe']:.2f} payout_model {payout(inp[f'g2_{t}'], x['roe']):.1%} -> {x['anchor']:.2f}")
    print(f"L: trough {inp['np_l'] / YI:.1f}亿 x recovery PE {pe_l:.2f} (g1 {g1:+.2%} n {inp['n_rec_l']:g}, "
          f"段二 ROE {roe_mid:.2%} g {inp['g2_m']:.2%}) -> {L:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    np_m = inp["cons_np28_m"]
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%} V_opt/M=0% | "
          f"分子比 L/M {inp['np_l'] / np_m:.2f} H/M {inp['cons_np28_h'] / np_m:.3f} | "
          f"倍数 L/M/H {pe_l:.2f}/{rows['m']['pe']:.2f}/{rows['h']['pe']:.2f}")
    print(f"flat-multiple (M-tier PE): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"③ M PE {rows['m']['pe']:.2f} in same-earnings band [{inp['pe_band_min']}, {inp['pe_band_max']}]")

    # evidence interval for g2_m: [g2_h, the g where M reaches H]
    lo, hi = inp["g2_h"], 0.06
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tier("m", mid)["anchor"] < H else (lo, mid)
    m_lo, m_hi = tier("m", inp["g2_h"])["anchor"], tier("m", lo)["anchor"]
    print(f"g2_m evidence interval [{inp['g2_h']:.2%}, {lo:.2%}] -> M {m_lo:.2f}–{m_hi:.2f}")

    def band(dg: float) -> str:
        ll = inp["np_l"] / sh * recovery_two_stage_pe(g1, inp["n_rec_l"], inp["g2_m"] + dg, roe_mid, r)
        return f"{ll:.2f}/{tier('m', inp['g2_m'] + dg)['anchor']:.2f}/{tier('h', inp['g2_h'] + dg)['anchor']:.2f}"
    print(f"敏感性 g2 −1pp {band(-0.01)} | +1pp {band(0.01)}")
    print(f"M 分子换 FY2028 下沿 {inp['cons_np28_l'] / YI:.2f}亿 -> M {inp['cons_np28_l'] / sh * rows['m']['pe'] / disc:.2f}")
    print(f"H 坐标·自身实测利润高点 {inp['np_peak_own'] / YI:.1f}亿 x H PE -> {inp['np_peak_own'] / sh * rows['h']['pe'] / disc:.2f}")
    mid_ratio = np_m / inp["np_mid10"]
    print(f"周期位置: FY28 M NP / 10y mean {inp['np_mid10'] / YI:.1f}亿 = {mid_ratio:.2f}x (demand-cycle, disclosure); "
          f"中枢坐标 10y mean x 1/r = {inp['np_mid10'] / sh / r:.2f}")
    print(f"压力坐标 谷底 x 1/r = {inp['np_l'] / sh / r:.2f}; FY2016 x 1/r = {inp['np_2016'] / sh / r:.2f}; "
          f"地板 PB {inp['pb_own_min']} x BPS = {inp['bps'] * inp['pb_own_min']:.2f}, PB 1.0 = {inp['bps']:.2f}")
    mod, gap = payout_gap(inp["g2_m"], rows["m"]["roe"], inp["payout_obs"])
    excess = (1 - inp["payout_obs"]) - inp["g2_m"] / rows["m"]["roe"]
    win = (cons["m"][0] - eps_h1) + cons["m"][1]
    print(f"payout: model {mod:.1%} vs observed {inp['payout_obs']:.1%} (gap {gap:+.1%}); 视同派出 = {excess:.1%} x window EPS "
          f"{win:.3f} = {excess * win:.2f}/sh (B 桶 net cash, k {inp['k_m']:g}; k 前 / k 后同值)")
    print(f"杠杆门: 净债/EBITDA {lev1:.2f} (扩展口径 {inp['net_debt_ext'] / inp['ebitda']:.2f}), "
          f"利息/EBIT {lev2:.1%} -> {'triggered' if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT else 'not triggered'}")
    print(f"证伪线 FY2027 NP 下沿 {inp['cons_np27_l'] / YI:.2f}亿")
    print("r_f: CNY segment of _AXIS.rates [待建] — no readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
