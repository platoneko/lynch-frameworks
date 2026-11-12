#!/usr/bin/env python3
"""Livzon's historical FY2027 peer-based valuation, not updated research.

Amounts follow the original inputs, with EPS and output in CNY/share. The
original source descriptions and as-of dates are retained beside the data.
Peer prices are dated historical comparison inputs, not current prices. The
user approved saving the existing model after the same-earnings band failure
was disclosed on 2026-10-23; that approval is not proof the band issue passed.

The forecast return uses a rolled beginning-of-year balance and historical
equity proxy, not proven incremental investment returns. Peer historical
comparisons and price/earnings months are fixed to the original research basis.
The peer-derived growth may differ from a subsequently updated peer framework;
such a change requires review rather than automatically altering this model.
"""
# Historical judgment retained from the document:
# The FY2027 EPS distribution comes from five yfinance estimates as of
# 2026-10-23; Donghai 2026-09-18 and Guoxin 2026-09-04 provide the two
# FY2028 estimates used for the one-year M/H transition, not a new range.
# In 2021–2025 dividends and canceled buybacks totaled about 82.6 versus
# 97.23 CNY 100 million parent earnings. The growth cap reflects this actual
# distribution record; the transition-year reinvestment assumption differs
# from that record and may understate growth funded by expensed R&D.
# The ten historical deducted weighted equity returns were 13.47, 9.48,
# 8.89, 11.00, 12.40, 13.12, 14.09, 13.48, 13.86, 14.57 percent. The
# FY2017 nonrecurring disposal gain is excluded. L/M fade to their mean by
# 2032; H retains its forward proxy. The proxy is not proven RONIC.
# Same-earnings band: 54 months from 2021-04 to 2026-07. At its 2026-06
# lower endpoint, contemporaneous forecast growth was about 11.3% and TTM
# ROE about 14.6%, comparable to the model's 10.93% transition and 15.26%
# M return. The user saw the shortfall and band-edge comparison and approved
# the original model on 2026-10-23; that approval does not make the band pass.
# Strategic asset-management equity investments of 13.58 CNY 100 million
# were not treated as cash; including them would bring the estimated excess
# cash ratio to roughly 16%, above the original 15% separate-cash threshold.
# The original excess-cash estimate was 9.29 CNY 100 million, 7% of parent
# equity, after dividends, operating cash requirements and parent share.
from __future__ import annotations

import math
import statistics
from lib.gordon import check_branch, check_g_cap, check_r, payout, payout_gap, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = '332353ee1651f195d43ccc2b47247ae2bb303c7ae1c146f142c5c5c7fa611a33'

INPUTS = {
    'shares': 887907171,  # 总股本（A + H）；2026 中报; as-of 2026-06-30
    'bps': 15.0532,  # 每股净资产 CNY（东方财富主要指标）; as-of 2026-06-30
    'eps_h1': 1.0499,  # 2026H1 归母 9.322 亿 ÷ 总股本；窗口扣已入账; as-of 2026-06-30
    'eps26_l': 1.98026,  # FY2026E 共识下沿（yfinance，5 家）；L 窗口; as-of 2026-10-23
    'eps26_m': 2.13347,  # FY2026E 共识均值；M 窗口; as-of 2026-10-23
    'eps26_h': 2.33,  # FY2026E 共识上沿；H 窗口; as-of 2026-10-23
    'eps27_l': 1.94,  # **L** 分子 = FY2027E 共识下沿（A1）; as-of 2026-10-23
    'eps27_m': 2.31315,  # **M** 分子 = FY2027E 共识均值（5 家）; as-of 2026-10-23
    'eps27_h': 2.70544,  # **H** 分子 = FY2027E 共识上沿; as-of 2026-10-23
    'eps27_dh': 2.62,  # 东海 FY2027E（09-18）；\(g_1\) 用; as-of 2026-10-23
    'eps28_dh': 2.82,  # 东海 FY2028E; as-of 2026-10-23
    'eps27_gx': 2.23,  # 国信 FY2027E（09-04）; as-of 2026-10-23
    'eps28_gx': 2.56,  # 国信 FY2028E; as-of 2026-10-23
    'g1': 0.109278,  # 一年过渡增速 2027→2028 = 两家 FY2028 合计 ÷ FY2027 合计 − 1（M / H；L 不用，A6）; as-of 2026-10-23
    'r_perp': 0.10,  # 篮 4 常规经营 10%：药价自谈 / 集采定、非商品价函数，无单一客户 / 国别依赖（A3）；`check_r`; as-of 2026-10-23
    'g2_peer': 0.014661,  # 稳态 \(g_2\) 源值 = 同业同尺反解中位（华东医药 / 华润三九，A5）；各档再取 min(源值, (1 − `payout_d`) × RONIC); as-of 2026-10-23
    'payout_d': 0.8495,  # 分红 + 注销式回购 ÷ 归母，FY2021–25（82.6 ÷ 97.23 亿，A8）；\(g\) 上限用; as-of FY2025
    'payout_op': 0.7765,  # 经营口径派息率 = d + c（c = −7.3%，A8）；`check_branch` 用; as-of FY2025
    'ronic_own': 0.12437,  # 稳态回报 = 自身 FY2016–25 扣非加权 ROE 均值（A7）；L / M 用，H 保持前瞻; as-of FY2025
    'y1': 2028,  # 高回报期止点 \(Y_1\) = 可见年末; as-of 2026-10-23
    'y2': 2032,  # 回落到稳态 \(Y_2\) = \(Y_1\) + 4（门槛「中」，A7）; as-of 2026-10-23
    'tau': 0.5,  # 时点对齐 τ = 2026-06-30 → 2027-01-01；价值 ÷ 1.1^τ、窗口 ÷ 1.1^(τ/2)（折现率同 `r_perp`，不归篮）; as-of 2026-06-30
    'k_l': 0,  # 具名交易打折：无（IMP 已付清、利润在共识内，A8）; as-of 2026-10-23
    'k_m': 0,  # 同上; as-of 2026-10-23
    'k_h': 0,  # 同上; as-of 2026-10-23
    'pe_band_min': 13.07,  # M 档同等盈利月份 TTM PE 下沿（2026-06）；③ 披露（A10）; as-of 2026-09-30
    'pe_band_max': 25.52,  # 同上 上沿（2021-06）; as-of 2026-09-30
    'net_cash_ext_h1': 4.3681e9,  # 扩展口径净现金（A4）; as-of 2026-06-30
    'div_declared': 1.34981e9,  # 应付股利 4.4414 亿 + 2026 中期股息 9.0567 亿（估值日后宣派、已除息）；类债项; as-of 2026-06-30
    'cash_anchor': 2.00339e9,  # 经营所需现金锚 = 2 个月收入（FY2025 收入 120.20 亿 ÷ 6；历史最低比率 27.0% 更高，A4）; as-of FY2025
    'minority_h1': 1.2319e9,  # 少数股东权益; as-of 2026-06-30
    'equity': 1.33658e10,  # 归母权益; as-of 2026-06-30
    'net_debt': -7.593e9,  # 净债务 FY2025 = 有息负债 30.60 − 货币资金 93.05 − 交易性金融资产 13.45 亿（A9）; as-of 2025-12-31
    'ebitda': 3.520e9,  # 营业利润 29.46 + 折旧摊销 5.74 亿; as-of FY2025
    'ebit': 2.946e9,  # 报表营业利润; as-of FY2025
    'interest': 5.72e7,  # 财务费用中利息支出; as-of FY2025
}

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


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('y1', 'y2'))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, sh, tau = inp['r_perp'], inp['shares'], inp['tau']
    y1, y2 = int(inp['y1']), int(inp['y2'])
    errors += check_r(r, 'r_perp', 4)
    if abs(tau - .5) > 1e-9:
        errors.append('tau must match 2026-06-30 to 2027-01-01')
    if not (y1 == 2028 and y2 == y1 + 4):
        errors.append('return fade must run 2028 to 2032')
    errors += ladder('FY2027 consensus', inp['eps27_l'], inp['eps27_m'], inp['eps27_h'])
    errors += ladder('FY2026 consensus', inp['eps26_l'], inp['eps26_m'], inp['eps26_h'])
    if min(sh, inp['bps'], inp['equity'] + inp['minority_h1'], inp['eps27_dh'] + inp['eps27_gx'],
           inp['ebitda'], inp['ebit']) <= 0:
        errors.append('invalid model denominator')
    if errors:
        raise ValueError('; '.join(errors))
    g1 = (inp['eps28_dh'] + inp['eps28_gx']) / (inp['eps27_dh'] + inp['eps27_gx']) - 1
    if abs(g1 - inp['g1']) > 5e-5:
        errors.append('g1 differs from two-house forecast growth')
    if not (inp['k_h'] >= inp['k_m'] >= inp['k_l'] == 0):
        errors.append('k must be 0 on L and non-decreasing')
    c_tot = inp['net_cash_ext_h1'] - inp['div_declared'] - inp['cash_anchor']
    pr = inp['equity'] / (inp['equity'] + inp['minority_h1'])
    c_ex = max(c_tot, 0) * pr
    if c_ex >= .15 * inp['equity']:
        errors.append('excess cash requires separate treatment')
    peer_rows, good = [], []
    for name, p in PEERS.items():
        g, pg1 = solve_peer(p, r, tau, y1, y2)
        roe = p['e27'] / p['bps']
        # PEERS retains company names and sources; machine output uses the ticker.
        peer_rows.append((name.split()[0], g, pg1, roe))
        if g is not None and roe - r >= .03:
            good.append(g)
    if len(good) < 2:
        errors.append('peer cluster has fewer than two usable members')
    elif abs(statistics.median(good) - inp['g2_peer']) > 5e-5:
        errors.append('peer growth differs from historical peer median')
    errors += check_g_cap(inp['g2_peer'], r, 'g2_peer')
    if errors:
        raise ValueError('; '.join(errors))

    d = inp['payout_d']
    spec = {'l': (None, inp['ronic_own']), 'm': (inp['g1'], inp['ronic_own']), 'h': (inp['g1'], None)}
    rows = {}
    for t, (tg1, rss) in spec.items():
        e26, e27, g = inp[f'eps26_{t}'], inp[f'eps27_{t}'], inp['g2_peer']
        for _ in range(50):
            x = value(e26, e27, inp['eps_h1'], inp['bps'], tg1, g, r, tau, y1, y2, rss)
            g = min(inp['g2_peer'], (1 - d) * x['roe'])
        x = value(e26, e27, inp['eps_h1'], inp['bps'], tg1, g, r, tau, y1, y2, rss, inp[f'k_{t}'])
        x.update(g=g, g1=g if tg1 is None else tg1, ss=min(x['roe'], x['roe'] if rss is None else rss), eps=e27)
        rows[t] = x
        if x['roe'] - r < .03 and t != 'l':
            errors.append(f'{t}: forward return outside monotone zone')
        if g / x['roe'] > 1 - d + 1e-9:
            errors.append(f'{t}: reinvestment exceeds retained portion')
        errors += check_branch(g, x['roe'], r, inp['payout_op'], f'g2_{t}')
    if rows['h']['ss'] < rows['m']['ss']:
        errors.append('H steady return below M')
    L, M, H = (rows[t]['anchor'] for t in 'lmh')
    errors += ladder('anchors', L, M, H)
    flat = [rows[t]['eps'] * rows['m']['mult'] for t in 'lmh']
    errors += ladder('flat-multiple', *flat)
    np_m = inp['eps27_m'] * sh / YI
    sel = [(mo, close / eps) for mo, close, npt, eps in MONTHS
           if np_m * (1 - PAIR_BAND) <= npt <= np_m * (1 + PAIR_BAND)]
    if not sel:
        raise ValueError('no matching historical earnings months')
    pes = [pe for _, pe in sel]
    if abs(min(pes) - inp['pe_band_min']) > .01 or abs(max(pes) - inp['pe_band_max']) > .01:
        errors.append('stated band endpoints differ from matched months')

    def tiers_at(rr, dg=0, g_src=None):
        out = []
        for t, (tg1, rss) in spec.items():
            e26, e27 = inp[f'eps26_{t}'], inp[f'eps27_{t}']
            src = (inp['g2_peer'] if g_src is None else g_src) + dg
            g = src
            for _ in range(50):
                x = value(e26, e27, inp['eps_h1'], inp['bps'], tg1, g, rr, tau, y1, y2, rss)
                g = min(src, (1 - d) * x['roe']) if dg == 0 else src
            out.append(value(e26, e27, inp['eps_h1'], inp['bps'], tg1, g, rr, tau, y1, y2, rss)['anchor'])
        return tuple(out)

    lo, hi = .05, r
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tiers_at(mid)[1] / inp['eps27_m'] > inp['pe_band_min'] else (lo, mid)
    r_edge = (lo + hi) / 2
    be = tiers_at(r_edge)
    lev1, lev2 = inp['net_debt'] / inp['ebitda'], inp['interest'] / inp['ebit']
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append('leverage gate triggered — ROIC branch required')
    if errors:
        raise ValueError('; '.join(errors))

    as_band = lambda xs: dict(zip('LMH', xs))
    sensitivity = {'band_edge': as_band(be), 'band_edge_rate': r_edge,
                   'growth_minus_1pp': as_band(tiers_at(r, -.01)),
                   'growth_plus_1pp': as_band(tiers_at(r, .01)),
                   'peer_min': as_band(tiers_at(r, 0, min(good))), 'peer_max': as_band(tiers_at(r, 0, max(good))),
                   'steady_forward': as_band(value(inp[f'eps26_{t}'], inp[f'eps27_{t}'], inp['eps_h1'], inp['bps'],
                                                    tg1, rows[t]['g'], r, tau, y1, y2, None)['anchor']
                                             for t, (tg1, _) in spec.items()),
                   'no_transition': as_band(value(inp[f'eps26_{t}'], inp[f'eps27_{t}'], inp['eps_h1'], inp['bps'],
                                                   None, rows[t]['g'], r, tau, y1, y2, spec[t][1])['anchor'] for t in 'lmh'),
                   'flat_multiple': as_band(flat)}
    a, b = cut_points(L, M, H)
    # L uses 无过渡 Gordon; M/H use 一年过渡 Gordon.
    return {'ticker': '000513.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-23', 'historical_framework_as_of': '2026-10-23',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b},
            'candidate': None, 'option': None, 'segments': {'company': {'values': as_band((L, M, H))}},
            'key_parameters': {'method': {'L': 'gordon_no_transition', 'M': 'gordon_one_year_transition', 'H': 'gordon_one_year_transition'},
                               'discount_rate': dict.fromkeys('LMH', r),
                               'growth_rate': as_band(rows[t]['g'] for t in 'lmh'),
                               'forward_return': as_band(rows[t]['roe'] for t in 'lmh'),
                               'steady_return': as_band(rows[t]['ss'] for t in 'lmh'),
                               'multiple': as_band(rows[t]['pe'] for t in 'lmh')},
            'operating': {'rows': rows, 'cash_total': c_tot, 'parent_ratio': pr, 'excess_cash': c_ex,
                          'peer_rows': peer_rows, 'matched_months': sel, 'band_outside': not (min(pes) <= rows['m']['mult'] <= max(pes)),
                          'band_min': min(pes), 'band_max': max(pes), 'band_median': statistics.median(pes),
                          'leverage': [lev1, lev2], 'payout_gap': payout_gap(rows['m']['g'], rows['m']['roe'], inp['payout_op'])},
            'sensitivity': sensitivity}


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'peers': PEERS, 'months': MONTHS, 'units_100m': YI,
         'numerator_year': NUM_YEAR, 'pairing_band': PAIR_BAND,
         'leverage_limit': LEV_DEBT_EBITDA, 'interest_limit': LEV_INT_EBIT}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    result['review_flags'] = ['historical_peer_comparability_unverified',
                              'historical_lower_edge_user_decision_2026_10_23',
                              'historical_growth_retention_and_cash_needs_unverified']
    return result
