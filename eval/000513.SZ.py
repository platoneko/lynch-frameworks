#!/usr/bin/env python3
"""000513.SZ (Livzon Pharmaceutical Group) valuation eval — recompute anchors from frameworks/000513.SZ.md.

frameworks/000513.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading for this ticker.

formula_id: livzon_fy27_consensus_peer_g2_gordon_v1

Main ruler: whole company (single operating segment in the annual report; no
sell-side SOTP), basket 4 r = 10%.  Consolidated basis: the excess cash at
2026-06-30 is below 15% of parent equity (valuation-rules「经营价值与超额现金」
trigger), so earnings, RONIC and the historical band all stay consolidated.

  numerator  FY2027 consensus EPS (yfinance 000513.SZ, 5 analysts): L = low,
             M = mean, H = high.  Value sits at 2027-01-01 → x (1+r)^-0.5 to the
             2026-06-30 balance sheet, plus the 2H26 unbooked consensus EPS x
             (1 − g/RONIC) at tau/2.
  g1         one transition year 2027→2028 on M and H (two FY2028 point
             estimates, Eastmoney: Donghai / Guosen); L carries no transition
             (a worsening world does not also carry the growth).
  g2         peer cross-section on the same ruler (Huadong / CR Sanjiu, same
             basket and domain; CR Double-Crane prices below the g = 0 value on
             a monotone RONIC → unreachable, dropped), median; then capped per
             tier at (1 − d) x RONIC (retention.md ③ constraint 2), d = 5-year
             dividends + cancelled buybacks / parent NP.
  RONIC      FY2027 EPS over the start-2027 BPS rolled from 2026-06-30 with
             b = g/RONIC; held through Y1 2028, linear to the steady return by
             Y2 2032 (entry barrier medium).  Steady (L / M) = own 10-year
             deducted weighted ROE mean; H keeps its forward return.
  ③          the M multiple (today's value / FY2027 EPS) sits below the
             same-earnings band → disclosed, not a failure: the user saw the
             BLOCKED reason and approved landing (2026-10-23).  The band-edge r
             and its parallel band are printed for table 2′.

V_opt = 0.  CNY segment of _AXIS.rates is [待建] → no r_f readings.

Run:  python3 frameworks/eval/000513.SZ.py
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_branch, check_g_cap, check_r, payout, payout_gap, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000513.SZ.md"
FORMULA_ID = "livzon_fy27_consensus_peer_g2_gordon_v1"
YI = 1e8
NUM_YEAR = 2027
PAIR_BAND = 0.12
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3

# Peer cross-section (valuation-rules g2 来源优先序 ②), same ruler as the M tier.
# (price as-of 2026-10-23 Longbridge; FY2026E / FY2027E / FY2028E Eastmoney F10
# consensus means; 2026H1 EPS and BPS from the interim reports; own FY2016–25
# deducted weighted ROE mean = steady return).  Other tickers' prices are allowed
# market data (contracts「现价 — 禁写契约」②).
PEERS = {
    "000963.SZ 华东医药": dict(price=26.38, e26=2.132, e27=2.297, e28=2.555, h1=1.061, bps=14.507, own=0.1801),
    "000999.SZ 华润三九": dict(price=24.78, e26=2.143, e27=2.381, e28=2.591, h1=1.000, bps=13.719, own=0.1303),
    "600062.SH 华润双鹤": dict(price=16.00, e26=1.710, e27=1.830, e28=2.040, h1=0.9163, bps=11.793, own=0.1147),
}

# Own monthly band (A-share month-end close, unadjusted; TTM parent NP 亿 and
# TTM EPS of the report visible at month end; Longbridge monthly klines +
# Eastmoney quarterly main indicators, 2026-10-23).  The as-of month is excluded.
MONTHS = [
    ("2021-01", 35.53, 16.85, 1.800), ("2021-02", 37.23, 16.85, 1.800), ("2021-03", 41.76, 17.15, 1.830),
    ("2021-04", 47.00, 18.35, 1.960), ("2021-05", 49.75, 18.35, 1.960), ("2021-06", 50.02, 18.35, 1.960),
    ("2021-07", 39.56, 18.35, 1.960), ("2021-08", 39.43, 17.73, 1.900), ("2021-09", 38.81, 17.73, 1.900),
    ("2021-10", 35.14, 17.46, 1.860), ("2021-11", 36.07, 17.46, 1.860), ("2021-12", 40.21, 17.46, 1.860),
    ("2022-01", 35.12, 17.46, 1.860), ("2022-02", 38.30, 17.46, 1.860), ("2022-03", 38.50, 17.76, 1.900),
    ("2022-04", 33.30, 18.09, 1.930), ("2022-05", 33.10, 18.09, 1.930), ("2022-06", 36.21, 18.09, 1.930),
    ("2022-07", 31.77, 18.09, 1.930), ("2022-08", 31.27, 17.31, 1.850), ("2022-09", 30.10, 17.31, 1.850),
    ("2022-10", 35.33, 18.30, 1.960), ("2022-11", 37.82, 18.30, 1.960), ("2022-12", 32.48, 18.30, 1.960),
    ("2023-01", 33.86, 18.30, 1.960), ("2023-02", 35.81, 18.30, 1.960), ("2023-03", 37.38, 19.09, 2.040),
    ("2023-04", 35.79, 19.38, 2.070), ("2023-05", 39.18, 19.38, 2.070), ("2023-06", 38.91, 19.38, 2.070),
    ("2023-07", 36.78, 19.38, 2.070), ("2023-08", 34.40, 20.26, 2.170), ("2023-09", 36.94, 20.26, 2.170),
    ("2023-10", 35.01, 20.04, 2.150), ("2023-11", 35.02, 20.04, 2.150), ("2023-12", 35.01, 20.04, 2.150),
    ("2024-01", 33.91, 20.04, 2.150), ("2024-02", 38.49, 20.04, 2.150), ("2024-03", 36.50, 19.54, 2.100),
    ("2024-04", 40.10, 19.80, 2.130), ("2024-05", 38.70, 19.80, 2.130), ("2024-06", 37.21, 19.80, 2.130),
    ("2024-07", 36.74, 19.80, 2.130), ("2024-08", 35.96, 19.90, 2.150), ("2024-09", 40.65, 19.90, 2.150),
    ("2024-10", 36.62, 20.25, 2.190), ("2024-11", 38.19, 20.25, 2.190), ("2024-12", 38.00, 20.25, 2.190),
    ("2025-01", 36.43, 20.25, 2.190), ("2025-02", 34.19, 20.25, 2.190), ("2025-03", 35.48, 20.61, 2.240),
    ("2025-04", 34.58, 20.90, 2.300), ("2025-05", 36.40, 20.90, 2.300), ("2025-06", 36.04, 20.90, 2.300),
    ("2025-07", 41.95, 20.90, 2.300), ("2025-08", 40.40, 21.71, 2.400), ("2025-09", 38.45, 21.71, 2.400),
    ("2025-10", 36.74, 21.42, 2.390), ("2025-11", 35.55, 21.42, 2.390), ("2025-12", 34.46, 21.42, 2.390),
    ("2026-01", 34.96, 21.42, 2.390), ("2026-02", 35.44, 21.42, 2.390), ("2026-03", 34.01, 20.23, 2.270),
    ("2026-04", 32.65, 19.63, 2.210), ("2026-05", 30.86, 19.63, 2.210), ("2026-06", 28.89, 19.63, 2.210),
    ("2026-07", 31.13, 19.63, 2.210), ("2026-08", 26.41, 16.74, 1.890), ("2026-09", 32.90, 16.74, 1.890),
]

REQUIRED = [
    "shares", "bps", "eps_h1", "eps26_l", "eps26_m", "eps26_h", "eps27_l", "eps27_m", "eps27_h",
    "eps27_dh", "eps28_dh", "eps27_gx", "eps28_gx", "g1", "r_perp", "g2_peer", "payout_d", "payout_op",
    "ronic_own", "y1", "y2", "tau", "k_l", "k_m", "k_h", "pe_band_min", "pe_band_max",
    "net_cash_ext_h1", "div_declared", "cash_anchor", "minority_h1", "equity",
    "net_debt", "ebitda", "ebit", "interest",
]


def path_pe(g1: float | None, g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Gordon at the start of NUM_YEAR per unit of NUM_YEAR earnings: year 1 grows into year 2 at g1
    (retaining g1/roe; g1 None = no transition, g from year 1), then g; RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after
    (retention.md ② 稳态回报三段 + growth.md 两段式过渡)."""
    if r - g <= 0:
        raise ValueError("r <= g")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = NUM_YEAR + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        gt = g1 if (t == 1 and g1 is not None) else g
        pv += e * (1 - gt / ro) / (1 + r) ** t
        e *= 1 + gt
        t += 1


def value(e26: float, e27: float, h1: float, bps: float, g1: float | None, g: float, r: float,
          tau: float, y1: int, y2: int, r_ss: float | None, k: float = 0.0) -> dict:
    """Today's value per share: FY2027 Gordon x (1+r)^-tau + 2H26 window distributable EPS x (1+r)^-(tau/2).
    r_ss None = the tier keeps its forward return (H world)."""
    u = e26 - h1
    roe = e27 / bps
    for _ in range(300):  # BPS roll to 2027-01-01, b = g/RONIC (③ 时点对齐)
        b27 = bps + g / roe * u
        roe = e27 / b27
    pe = path_pe(g1, g, roe, r, y1, y2, roe if r_ss is None else r_ss)
    w = max(u * (1 - g / roe), 0.0) / (1 + r) ** (tau / 2)
    v = e27 * pe * (1 - k) / (1 + r) ** tau + w
    return dict(roe=roe, b27=b27, pe=pe, w=w, u=u, anchor=v, mult=v / e27, pe_1=perpetual_pe(g, roe, r))


def solve_peer(p: dict, r: float, tau: float, y1: int, y2: int) -> tuple[float | None, float]:
    g1 = p["e28"] / p["e27"] - 1
    f = lambda g: value(p["e26"], p["e27"], p["h1"], p["bps"], g1, g, r, tau, y1, y2, p["own"])["anchor"]
    lo, hi = 0.0, r - 0.02
    if not f(lo) <= p["price"] <= f(hi):
        return None, g1   # retaining peer priced below the g = 0 value on a monotone RONIC → unreachable
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < p["price"] else (lo, mid)
    return (lo + hi) / 2, g1


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
    r, sh, tau = inp["r_perp"], inp["shares"], inp["tau"]
    y1, y2 = int(inp["y1"]), int(inp["y2"])

    # --- basket, timing, consensus ----------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if abs(tau - 0.5) > 1e-9:
        errors.append(f"tau {tau:g} != 2026-06-30 → 2027-01-01")
    if not (y1 == 2028 and y2 == y1 + 4):
        errors.append("Y1 must be the last visible year FY2028 and Y2 = Y1 + 4 (medium entry barrier)")
    errors += ladder("FY2027 consensus", inp["eps27_l"], inp["eps27_m"], inp["eps27_h"])
    errors += ladder("FY2026 consensus", inp["eps26_l"], inp["eps26_m"], inp["eps26_h"])
    g1 = (inp["eps28_dh"] + inp["eps28_gx"]) / (inp["eps27_dh"] + inp["eps27_gx"]) - 1
    if abs(g1 - inp["g1"]) > 5e-5:
        errors.append(f"g1 {inp['g1']} != two-house FY2028/FY2027 mean growth {g1:.5f}")
    if not (inp["k_h"] >= inp["k_m"] >= inp["k_l"] == 0):
        errors.append("k must be 0 on L and non-decreasing")

    # --- excess cash: below the 15% trigger → consolidated basis -------------------------
    c_tot = inp["net_cash_ext_h1"] - inp["div_declared"] - inp["cash_anchor"]
    pr = inp["equity"] / (inp["equity"] + inp["minority_h1"])
    c_ex = max(c_tot, 0.0) * pr
    if c_ex >= 0.15 * inp["equity"]:
        errors.append(f"C_ex {c_ex / YI:.2f}亿 >= 15% of parent equity: the excess-cash line must exist")

    # --- g2: peer cross-section on the same ruler ----------------------------------------
    peer_rows, good = [], []
    for name, p in PEERS.items():
        g, pg1 = solve_peer(p, r, tau, y1, y2)
        roe = p["e27"] / p["bps"]
        peer_rows.append((name, g, pg1, roe))
        if g is not None and roe - r >= 0.03:
            good.append(g)
    if len(good) < 2:
        errors.append("peer cluster has fewer than 2 usable members")
    else:
        med = statistics.median(good)
        if abs(med - inp["g2_peer"]) > 5e-5:
            errors.append(f"g2_peer {inp['g2_peer']} != peer median {med:.5f}")
    errors += check_g_cap(inp["g2_peer"], r, "g2_peer")
    if errors:
        return report(errors, "FAIL (basket / g)")

    # --- tiers ---------------------------------------------------------------------------
    d = inp["payout_d"]
    spec = {"l": (None, inp["ronic_own"]), "m": (inp["g1"], inp["ronic_own"]), "h": (inp["g1"], None)}
    rows = {}
    for t, (tg1, rss) in spec.items():
        e26, e27 = inp[f"eps26_{t}"], inp[f"eps27_{t}"]
        g = inp["g2_peer"]
        for _ in range(50):  # retention.md ③ constraint 2: g <= (1 − d) x RONIC
            x = value(e26, e27, inp["eps_h1"], inp["bps"], tg1, g, r, tau, y1, y2, rss)
            g = min(inp["g2_peer"], (1 - d) * x["roe"])
        x = value(e26, e27, inp["eps_h1"], inp["bps"], tg1, g, r, tau, y1, y2, rss, inp[f"k_{t}"])
        x.update(g=g, g1=g if tg1 is None else tg1, ss=min(x["roe"], x["roe"] if rss is None else rss), eps=e27)
        rows[t] = x
        if x["roe"] - r < 0.03 and t != "l":
            errors.append(f"{t.upper()}: RONIC {x['roe']:.1%} not in the monotone zone")
        if g / x["roe"] > 1 - d + 1e-9:
            errors.append(f"{t.upper()}: b {g / x['roe']:.3f} > 1 − d {1 - d:.3f}")
        errors += check_branch(g, x["roe"], r, inp["payout_op"], f"g2_{t}")
    if rows["h"]["ss"] < rows["m"]["ss"]:
        errors.append("H steady return below M")

    L, M, H = (rows[t]["anchor"] for t in "lmh")
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # flat ladder (2c): every tier on the M-tier multiple
    flat = [rows[t]["eps"] * rows["m"]["mult"] for t in "lmh"]
    errors += ladder("flat-multiple", *flat)

    # ③ same-earnings band (disclosed; landing approved by the user over the BLOCKED reason)
    np_m = inp["eps27_m"] * sh / YI
    sel = [(mo, c / e) for mo, c, npt, e in MONTHS if np_m * (1 - PAIR_BAND) <= npt <= np_m * (1 + PAIR_BAND)]
    pes = [pe for _, pe in sel]
    if abs(min(pes) - inp["pe_band_min"]) > 0.01 or abs(max(pes) - inp["pe_band_max"]) > 0.01:
        errors.append(f"pe_band_min/max {inp['pe_band_min']}/{inp['pe_band_max']} != M-window months "
                      f"{min(pes):.2f}/{max(pes):.2f}")
    low_month = min(sel, key=lambda s: s[1])[0]

    def tiers_at(rr: float, dg: float = 0.0, g_src: float | None = None) -> tuple[float, float, float]:
        out = []
        for t, (tg1, rss) in spec.items():
            e26, e27 = inp[f"eps26_{t}"], inp[f"eps27_{t}"]
            src = (inp["g2_peer"] if g_src is None else g_src) + dg
            g = src
            for _ in range(50):
                x = value(e26, e27, inp["eps_h1"], inp["bps"], tg1, g, rr, tau, y1, y2, rss)
                g = min(src, (1 - d) * x["roe"]) if dg == 0 else src
            out.append(value(e26, e27, inp["eps_h1"], inp["bps"], tg1, g, rr, tau, y1, y2, rss)["anchor"])
        return tuple(out)

    lo, hi = 0.05, r
    for _ in range(60):  # band-edge r: M multiple = band low
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tiers_at(mid)[1] / inp["eps27_m"] > inp["pe_band_min"] else (lo, mid)
    r_edge = (lo + hi) / 2
    be = tiers_at(r_edge)

    lev1, lev2 = inp["net_debt"] / inp["ebitda"], inp["interest"] / inp["ebit"]
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append("leverage gate triggered — ROE decomposition / ROIC branch required")

    # --- report ------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} r={r:g}; FY{NUM_YEAR} value ÷1.1^{tau:g} + 2H26 window ÷1.1^{tau / 2:g}; "
          f"Y1 {y1} → Y2 {y2}")
    print(f"excess cash: ext net cash {inp['net_cash_ext_h1'] / YI:.2f}亿 − declared {inp['div_declared'] / YI:.2f}亿 − anchor "
          f"{inp['cash_anchor'] / YI:.2f}亿 = {c_tot / YI:.2f}亿 x parent {pr:.4f} = {c_ex / YI:.2f}亿 "
          f"({c_ex / inp['equity']:.1%} of parent equity < 15% → consolidated basis)")
    for name, g, pg1, roe in peer_rows:
        print(f"peer {name}: fwd ROE {roe:.1%} g1 {pg1:+.1%} → g2 {'unreachable' if g is None else f'{g:.2%}'}")
    print(f"g2_peer median {inp['g2_peer']:.2%}; g1 (M/H) {inp['g1']:.2%}; d {d:.1%}")
    for t in "lmh":
        x = rows[t]
        print(f"{t.upper()}: EPS27 {x['eps']:.4f} BPS27 {x['b27']:.3f} RONIC {x['roe']:.2%} steady {x['ss']:.2%} "
              f"g1 {x['g1']:.2%} g2 {x['g']:.2%} (cap (1−d)·RONIC {(1 - d) * x['roe']:.2%}) PE {x['pe']:.2f} "
              f"| {x['eps'] * x['pe'] / (1 + r) ** tau:.2f} + window {x['w']:.2f} → {x['anchor']:.2f} (today/E27 {x['mult']:.2f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%} V_opt/M=0% | 分子比 L/M "
          f"{inp['eps27_l'] / inp['eps27_m']:.2f} H/M {inp['eps27_h'] / inp['eps27_m']:.2f} | 倍数 "
          f"{rows['l']['mult']:.2f}/{rows['m']['mult']:.2f}/{rows['h']['mult']:.2f}")
    print(f"flat-multiple: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"③ same-earnings band (FY27 M NP {np_m:.2f}亿 ±12%): {len(sel)} months, PE {min(pes):.2f}–{max(pes):.2f} "
          f"median {statistics.median(pes):.2f}; low {low_month}; M today/E27 {rows['m']['mult']:.2f} → "
          f"{'IN' if min(pes) <= rows['m']['mult'] <= max(pes) else 'OUT (disclosed, user-approved landing)'}")
    print(f"band-edge r {r_edge:.2%}: L {be[0]:.2f} / M {be[1]:.2f} / H {be[2]:.2f} / A {(be[0] + be[1]) / 2:.2f} / "
          f"B {(be[1] + be[2]) / 2:.2f}")
    for dg in (-0.01, 0.01):
        s = tiers_at(r, dg)
        print(f"sensitivity g2 {dg:+.0%} (cap off): {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f}")
    for gs in (min(good), max(good)):
        s = tiers_at(r, 0.0, gs)
        print(f"g2 peer-range end {gs:.2%}: {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f} A {(s[0] + s[1]) / 2:.2f} B {(s[1] + s[2]) / 2:.2f}")
    s = []
    for t, (tg1, _) in spec.items():
        s.append(value(inp[f"eps26_{t}"], inp[f"eps27_{t}"], inp["eps_h1"], inp["bps"], tg1, rows[t]["g"], r, tau,
                       y1, y2, None)["anchor"])
    print(f"sensitivity steady = forward on every tier: {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f}")
    s = [value(inp[f"eps26_{t}"], inp[f"eps27_{t}"], inp["eps_h1"], inp["bps"], None, rows[t]["g"], r, tau, y1, y2,
               spec[t][1])["anchor"] for t in "lmh"]
    print(f"sensitivity no g1 transition: {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f}")
    mod, gap = payout_gap(rows["m"]["g"], rows["m"]["roe"], inp["payout_op"])
    print(f"payout: model steady {mod:.1%} vs 经营口径 {inp['payout_op']:.1%} (gap {gap:+.1%}); d {d:.1%}; "
          f"segment-one 2027 model payout M {1 - inp['g1'] / rows['m']['roe']:.1%}")
    print(f"杠杆门: 净债/EBITDA {lev1:.2f}, 利息/EBIT {lev2:.1%} -> "
          f"{'triggered' if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT else 'not triggered'}")
    print("r_f: CNY segment of _AXIS.rates [待建] — no readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
