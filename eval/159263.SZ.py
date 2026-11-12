"""Historical 159263 value-100 model; all runtime data is explicit.

The 480081 total-return trend channel is the main ruler. Three stocks are
used solely in the separate look-through comparison. The 2026-09-11 exchange
close was a proxy for NAV and is not a same-day NAV for the 2026-09-17 index.
"""
from __future__ import annotations

import math
from statistics import median
import pandas as pd

from lib.etf import REGIME_GAP, SUBWINDOWS, channel, slope_since
from lib.etf_lookthrough import scale
from lib.fund_history import normalize_fund_reference
from lib.gordon import implied_g, implied_g_retaining, justified_pb, payout_gap, perpetual_pe
from lib.partial_basis import local_basis_changed
from lib.value100_inputs import normalize_index_history, select_peer_bands

DEPENDENCIES = {'libraries': ('etf', 'etf_lookthrough', 'fund_history', 'gordon',
                              'partial_basis', 'value100_inputs'), 'axes': {},
                'peers': {'cmb': '600036.SH', 'yth': '600096.SH', 'alc': '601600.SH'}}
INDEX_CODE = '480081'
CHANNEL_START = '2015-12-01'
CHANNEL_END = '2026-09-17'
HISTORICAL_RESEARCH_AS_OF = '2026-11-05'
HISTORICAL_INDEX_REFERENCE = {'date': '2026-09-17', 'level': 8100.56}
# The old study used a traded close from a different date. This is not a NAV
# observation and must not be relabelled by editing only the type or date.
FUND_REFERENCE = {'security': '159263.SZ', 'kind': 'exchange_close_proxy', 'value': 1.152,
                  'date': '2026-09-11', 'unit': 'CNY_PER_UNIT', 'source_ref': 'longbridge_2026_09_11_close'}
WHITE = ('gree', 'midea', 'haier')
BLOCKED_WHITE = ('gree',)  # Original 7.71x is unreachable on the retaining branch; excluded, not clipped.
PEER_TICKERS = {'cmb': '600036.SH', 'yth': '600096.SH', 'alc': '601600.SH'}
HISTORICAL_CROSSCHECK = {'L': 1.0452, 'M': 1.2475, 'H': 1.3382}
BASELINE_FINGERPRINT = 'bbf328111aa4c55e71e34f907be475bbca872e9c1a83ac5adc7b326bacdc7e33'

INPUTS = {
    'fee_drag': 0.98,  # (1-0.002/0.10)（按 `r_perp` 折算） 合同
    'r_perp': 0.1,  # 篮 4 龙头制造：白电 19.5% + 残余 54.5% 的常规经营现金流（A10）；只进对照尺（白电 / 残余 Gordon）与 `fee_drag` 折算，通道尺无 r；`check_r` 2026-09-20
    'r_bank': 0.11,  # 篮 5 大行 / 优质股份行：兴业 PB-ROE 腿（A4 / A10）；招行 look-through 读源框架、其余金融只乘系数，不用本行；只进对照尺；`check_r` 2026-09-20
    'chan_slope': 0.148,  # 通道尺：480081 价值100 全收益对数线性趋势斜率（通道窗 = 全窗 2015-12-01～2026-09-17，剔 2σ 重拟）= 实测中枢回报；eval 由 `eval/lib/etf.py` 复算 2026-09-17
    'chan_slope_2019': 0.161,  # 子窗斜率 2019 起（起点敏感性；与全窗差 < 5pp，不触发 regime 断裂） 2026-09-17
    'chan_slope_2021': 0.178,  # 子窗斜率 2021 起 2026-09-17
    'chan_sigma': 0.094,  # 残差 σ 2026-09-17
    'chan_l_idx': 7174.0,  # 通道 L = 趋势 × exp(残差 p10)，指数点 2026-09-17
    'chan_m_idx': 7942.0,  # 通道 M = 趋势现值，指数点 2026-09-17
    'chan_h_idx': 9263.0,  # 通道 H = 趋势 × exp(残差 p90)，指数点 2026-09-17
    'idx_cur': 8100.56,  # 折算日指数值（全收益 480081）；k = nav_ref ÷ idx_cur（`nav_ref` 取 09-11 收盘，与指数 09-17 不同日，A9） 2026-09-17
    'eps_pt_from_peak': -0.063,  # E 侧护栏：透视 EPS/点 自 2026-03-04 峰 519.3 回落至 486.7 2026-09
    'eps_pt_yoy': 0.108,  # E 侧护栏：透视 EPS/点 同比（2026-09-01 vs 2025-09-01） 2026-09
    'beta_rate_prior': -20.0,  # 利率轴 β 先验 = −1/DY（−1/5.0%）；待建 `_AXIS.rates.md` 先验
    'w_white': 0.1945,  # 格力 8.59% + 美的 7.37% + 海尔 3.49%；基金二季报 2026-06-30
    'pe_white_now': 10.14,  # 三只现 PE 的**盈利加权（调和）**：格力 7.78 / 美的 14.83 / 海尔 10.96（09-11 收盘；Longbridge TTM PE）→ (w/sum(w_k/PE_k)) 2026-09-11
    'roe_white': 0.194,  # 白电 M 档 ROE = FY2027E 共识 EPS ÷ **2027 年初 BPS**（2Q26 账面按 (b_1=g_2/ROE) 滚过 2H26 未入账 EPS，A11），盈利加权（格力 18.7 / 美的 23.2 / 海尔 16.0%；eval 由 `*_roe` × 盈利权重复算 ±0.005）；L/H 档 ROE 按分子比派生（eval） 2026-09-21
    'g2_white': 0.0179,  # 白电永续 g，三档共用；**留存分支反解**中位（美的 +3.40% / 海尔 +0.18%，n=2；格力 7.71× 不可达 BLOCKED 剔除，A5）；反解用的 ROE 是 2027 年初口径、账面又按 (g_2) 滚——eval 迭代到联立不动点 0.01790 并比对 ±0.0005（A11）；≤ cap 6%（r 10%） 2026-09-21
    'payout_white': 0.617,  # 白电腿实付派息率 = 三只 FY2025 DPS ÷ 基本 EPS 的盈利加权（eval 由 `*_dps25` / `*_eps25` 复算 ±0.005；A5）；< 80% → 留存 FY2025
    'g_evid_white_min': 0.0018,  # 白电 (g_2) 证据区间下沿 = 海尔留存分支反解（A5） 2026-09-11
    'g_evid_white_max': 0.0339,  # 上沿 = 美的留存分支反解（A5） 2026-09-11
    'eps_white_l': 0.9,  # 白电分子 / TTM：FY2027E 共识**下沿**盈利加权（格力 3.87/4.98 · 美的 6.34/5.85 · 海尔 1.98/1.93） 2026-09-13
    'eps_white_m': 1.05,  # FY2027E 共识均值盈利加权（5.02/4.98 · 6.67/5.85 · 2.09/1.93） 2026-09-13
    'eps_white_h': 1.14,  # FY2027E 共识**上沿**盈利加权（5.51/4.98 · 7.05/5.85 · 2.23/1.93） 2026-09-13
    'gree_w': 0.0859,  # 格力基金权重（盈利权重分子）；基金二季报 2026-06-30
    'gree_pe': 7.78,  # 格力 09-11 TTM PE（盈利权重分母 (w_k/PE_k)）；Longbridge 2026-09-11
    'gree_fpe': 7.71,  # 格力前瞻 PE = 09-11 收盘 38.74 ÷ FY2027E 均值 5.02（反解用，A5） 2026-09-11
    'gree_roe': 0.187,  # 格力 ROE_M = FY27E EPS_M ÷ 2027 年初 BPS 26.86（= (fy27 − g2_white × (fy26 − h1_26)) / bps_2q26，A11；单调区；旧口径 ÷ 中报 BPS 18.9%） 2026-09-21
    'gree_h1_26': 2.38,  # 格力 2026H1 基本 EPS CNY（已入账，从 FY26E 里扣掉得 2H26 未入账 2.417；Longbridge IS saf） 2026-06-30
    'gree_bps_2q26': 26.6254,  # 格力 2Q26 每股净资产 CNY（账面滚动起点；Longbridge BS saf） 2026-06-30
    'gree_dps25': 3.0,  # 格力 FY2025 DPS CNY = 中期 1.00（除息 2026-01-23）+ 末期 2.00（2026-08-27）；Longbridge `dividend` 000651.SZ FY2025
    'gree_eps25': 5.2,  # 格力 FY2025 基本 EPS CNY；Longbridge IS af → 派息率 57.7% FY2025
    'gree_fy26': 4.797,  # 格力 FY2026E 共识均值 CNY（6 家，yfinance）；同世界门 2026-09-15
    'gree_fy27': 5.023,  # 格力 FY2027E 共识均值（6 家） 2026-09-15
    'midea_w': 0.0737,  # 美的基金权重 2026-06-30
    'midea_pe': 14.83,  # 美的 09-11 TTM PE 2026-09-11
    'midea_fpe': 12.93,  # 美的前瞻 PE = 86.26 ÷ 6.67 2026-09-11
    'midea_roe': 0.232,  # 美的 ROE_M = FY27E ÷ 2027 年初 BPS 28.72（A11；单调区；旧口径 23.4%） 2026-09-21
    'midea_h1_26': 3.4988,  # 美的 2026H1 基本 EPS CNY（2H26 未入账 2.563）；Longbridge IS saf 2026-06-30
    'midea_bps_2q26': 28.517,  # 美的 2Q26 每股净资产 CNY；Longbridge BS saf 2026-06-30
    'midea_dps25': 4.3,  # 美的 FY2025 DPS CNY = 中期 0.50（2025-11-18）+ 末期 3.80（2026-06-29）；Longbridge 000333.SZ FY2025
    'midea_eps25': 5.7609,  # 美的 FY2025 基本 EPS CNY → 派息率 74.6% FY2025
    'midea_fy26': 6.062,  # 美的 FY2026E 共识均值（5 家） 2026-09-15
    'midea_fy27': 6.671,  # 美的 FY2027E 共识均值（21 家） 2026-09-15
    'haier_w': 0.0349,  # 海尔基金权重 2026-06-30
    'haier_pe': 10.96,  # 海尔 09-11 TTM PE 2026-09-11
    'haier_fpe': 10.07,  # 海尔前瞻 PE = 21.01 ÷ 2.087 2026-09-11
    'haier_roe': 0.16,  # 海尔 ROE_M = FY27E ÷ 2027 年初 BPS 13.06（A11；单调区；旧口径 16.1%） 2026-09-21
    'haier_h1_26': 1.12,  # 海尔 2026H1 基本 EPS CNY（2H26 未入账 0.870）；Longbridge IS saf 2026-06-30
    'haier_bps_2q26': 12.9646,  # 海尔 2Q26 每股净资产 CNY；Longbridge BS saf 2026-06-30
    'haier_dps25': 1.1607,  # 海尔 FY2025 DPS CNY = 中期 0.2692（2025-11-07）+ 末期 0.8915（2026-08-21）；Longbridge 600690.SH FY2025
    'haier_eps25': 2.1,  # 海尔 FY2025 基本 EPS CNY → 派息率 55.3% FY2025
    'haier_fy26': 1.99,  # 海尔 FY2026E 共识均值（3 家） 2026-09-15
    'haier_fy27': 2.087,  # 海尔 FY2027E 共识均值（5 家） 2026-09-15
    'w_cmb': 0.0659,  # 招行权重；基金二季报 2026-06-30
    'px_cmb': 41.35,  # 招行 2026-09-11 收盘 CNY（A9 同日快照） 2026-09-11
    'w_xyb': 0.0779,  # 兴业银行；基金二季报 2026-06-30
    'pb_xyb': 0.461,  # 兴业现 PB = 收盘 18.13 / 中报 BPS 39.63 2026-09-11
    'roe_xyb': 0.0819,  # 兴业 TTM ROE（Longbridge 2026H1 报表口径，与招行同源） 2026-06-30
    'g2_bank': 0.03,  # 银行永续 g（兴业 PB-ROE，r = `r_bank`）；来源层级：无同业锚，与 `600036.SH` 同档 A4
    'k_bank_l': 0.9,  # 银行分子系数（兴业 fair PB 与其余金融共用；`513530.SH` 同构） A4
    'k_bank_m': 1.0,
    'k_bank_h': 1.05,
    'w_obank': 0.0549,  # 金融业其余（19.87% − 招行 − 兴业），无仓内框架，只乘 `k_bank_x` 2026-06-30
    'w_yth': 0.032,  # 云天化；基金二季报 2026-06-30
    'px_yth': 29.31,  # 云天化 09-11 收盘 CNY（A9 同日快照；源框架之后的价格读数本票不跟） 2026-09-11
    'w_alc': 0.0298,  # 中铝；基金二季报 2026-06-30
    'px_alc': 9.44,  # 中铝 2026-09-11 收盘 CNY（A9 同日快照） 2026-09-11
    'w_res': 0.545,  # 其余 1−上列
    'pe_res_now': 10.26,  # 指数 PE：国证 08-14 10.15 × 指数点位 4509.06 / 4462.40 同日化（980081 是价格指数，ETF 净值含股息累积，按净值缩放会系统性偏高约 +0.4%/月，A6）；官方 09-11 值待补 2026-09-11
    'roe_idx': 0.108,  # 残余腿 Gordon 用 ROE = 指数 PB 1.10 / PE 10.15（比值不随同日化变）； ROE − r = 0.8pp 病态区（A6） 2026-08-14
    'idx_dy_lo': 0.047,  # 透视股息率区间下沿（快照）；只进 `payout_res` 与证据区间（A6） 2026-09-11
    'idx_dy_hi': 0.053,  # 透视股息率区间上沿 2026-09-11
    'payout_res': 0.513,  # 残余腿透视派息率 = 透视股息率中值 5.0% × `pe_res_now` 10.26（A6；eval ±0.005）；< 80% → 留存 2026-09-11
    'g2_res_l': 0.0,  # 残余 L 档 g：具名「增长故事到此为止」世界（留存资本只挣 r，倍数 1/r）；不是分支读数，`check_branch` 只在 M 档做 —
    'g2_res_m': 0.0526,  # 残余 M 档 g，**留存分支** = (1 − payout_res) × roe_idx（eval ±0.0005）；`check_branch` 幅度通过（模型派息率 = 实付）；SOTP 早期版本自定 2% 已废 2026-09-11
    'g2_res_h': 0.0526,  # 残余 H 档 g = M 档（病态区 H 不高于 M，A6）；≤ cap 6% 2026-09-11
    'g_evid_res_min': 0.0493,  # 残余 (g_2) 证据区间下沿 = (1 − idx_dy_hi × pe_res_now) × roe_idx —
    'g_evid_res_max': 0.0559,  # 上沿 = (1 − idx_dy_lo × pe_res_now) × roe_idx —
    'pe_res_l': 10.0,  # = `perpetual_pe(g2_res_l, roe_idx, r_perp)`（eval 复算） —
    'pe_res_m': 10.82,  # 同上
    'pe_res_h': 10.82,  # 同上
    'eps_res_l': 0.9,  # 残余分子 / TTM；**部分证据**：成份透视隐含 EPS 谷 / 当前 2024-12 起 0.846、换手修正 0.901，0.90 取观测窗上沿；[0.846, 0.901] **不作证据区间**（A6）；2022–23 真坏年不可无偏观测 待补坏年（官方估值历史可得时重定，A6）
    'eps_res_m': 1.0,
    'eps_res_h': 1.05,  #  待补
}

HISTORICAL_PEER_BANDS = {
    'cmb': {'L': 38.03, 'M': 43.93, 'H': 54.63},
    'yth': {'L': 26.11, 'M': 30.26, 'H': 34.77},
    'alc': {'L': 7.25, 'M': 12.66, 'H': 12.8},
}

def white_roe(inp: dict[str, float], n: str, g2: float) -> float:
    """E_{2027}/B_{2026 末}: FY27E EPS over the 2Q26 book rolled over the 2H26
    unbooked EPS (FY26E − 1H26 actual) at b1 = g2/ROE.  With ROE = eps/BPS and
    BPS = BPS0 + b1·N the fixed point is BPS = BPS0 / (1 − g2·N/eps), i.e.
    ROE = (eps − g2·N) / BPS0 (A11; valuation-rules 裁决表 ② as of 2026-09-21)."""
    n_unbooked = inp[f"{n}_fy26"] - inp[f"{n}_h1_26"]
    return (inp[f"{n}_fy27"] - g2 * n_unbooked) / inp[f"{n}_bps_2q26"]


def solve_g2_white(inp: dict[str, float], r: float) -> tuple[float, dict[str, float]]:
    """Joint fixed point of g2_white (cluster median of the retention-branch
    reverse-solve) and the per-name ROE that the roll at g2 produces (A11)."""
    g2 = inp["g2_white"]
    for _ in range(100):
        cluster = {n: implied_g_retaining(inp[f"{n}_fpe"], white_roe(inp, n, g2), r)[0]
                   for n in WHITE if n not in BLOCKED_WHITE}
        g2_next = median(cluster.values())
        if abs(g2_next - g2) < 1e-10:
            break
        g2 = g2_next
    return g2, cluster


def white_weights(inp: dict[str, float]) -> dict[str, float]:
    """Earnings share w_k / PE_k inside the white-goods sleeve, normalised."""
    raw = {n: inp[f"{n}_w"] / inp[f"{n}_pe"] for n in WHITE}
    total = sum(raw.values())
    return {n: v / total for n, v in raw.items()}

def _crosscheck(original, snapshots):
    """Existing look-through model; unavailable peers never erase the main band."""
    bands, flags = select_peer_bands(snapshots, PEER_TICKERS)
    missing = sorted(set(PEER_TICKERS) - set(bands))
    if missing:
        return {'status': 'unavailable', 'missing_peers': missing,
                'historical_reference_anchors': dict(HISTORICAL_CROSSCHECK)}, flags
    inp = dict(original)
    for alias, values in bands.items():
        for tier in 'LMH':
            inp[f'{alias}_{tier.lower()}'] = values[tier]
            if abs(values[tier] - HISTORICAL_PEER_BANDS[alias][tier]) > .01:
                flags.append(f'peer_{alias}_differs_from_historical_reference')
    try:
        weights = white_weights(inp)
        r, r_bank = inp['r_perp'], inp['r_bank']
        fixed_growth, cluster = solve_g2_white(inp, r)
        weighted_pe = sum(inp[f'{n}_w'] for n in WHITE) / sum(inp[f'{n}_w'] / inp[f'{n}_pe'] for n in WHITE)
        weighted_payout = sum(weights[n] * inp[f'{n}_dps25'] / inp[f'{n}_eps25'] for n in WHITE)
        weighted_roe = sum(weights[n] * inp[f'{n}_roe'] for n in WHITE)
        if abs(fixed_growth - inp['g2_white']) > .0005:
            flags.append('white_goods_growth_differs_from_joint_fixed_point')
        if abs(weighted_pe - inp['pe_white_now']) > .05:
            flags.append('white_goods_pe_reference_differs')
        if abs(weighted_payout - inp['payout_white']) > .005 or abs(weighted_roe - inp['roe_white']) > .005:
            flags.append('white_goods_payout_or_return_reference_differs')
        if any(abs(white_roe(inp, n, inp['g2_white']) - inp[f'{n}_roe']) > .0005 for n in WHITE):
            flags.append('white_goods_opening_book_return_differs')
        if any(inp[f'{n}_fy27'] <= inp[f'{n}_fy26'] for n in WHITE):
            flags.append('white_goods_forward_earnings_no_longer_rising')
        if abs(min(cluster.values()) - inp['g_evid_white_min']) > .0005 or abs(max(cluster.values()) - inp['g_evid_white_max']) > .0005:
            flags.append('white_goods_growth_evidence_differs')
        residual_payout = (inp['idx_dy_lo'] + inp['idx_dy_hi']) / 2 * inp['pe_res_now']
        residual_growth = (1 - inp['payout_res']) * inp['roe_idx']
        residual_evidence = ((1 - inp['idx_dy_hi'] * inp['pe_res_now']) * inp['roe_idx'],
                             (1 - inp['idx_dy_lo'] * inp['pe_res_now']) * inp['roe_idx'])
        if (abs(residual_payout - inp['payout_res']) > .005
                or abs(residual_growth - inp['g2_res_m']) > .0005
                or inp['g2_res_h'] != inp['g2_res_m'] or inp['g2_res_l'] != 0
                or any(abs(a - b) > .0005 for a, b in zip(residual_evidence,
                    (inp['g_evid_res_min'], inp['g_evid_res_max'])))):
            flags.append('residual_growth_or_payout_reference_differs')
        # Historical clipping/exclusion is disclosed as a business judgment,
        # not silently changed to a different valuation branch.
        for name in WHITE:
            _, eligible = implied_g_retaining(inp[f'{name}_fpe'], inp[f'{name}_roe'], r)
            if name in BLOCKED_WHITE and eligible:
                flags.append('historical_white_goods_exclusion_needs_review')

        def pe_white(tier, growth):
            roe = inp['roe_white'] * inp[f'eps_white_{tier}'] / inp['eps_white_m']
            return perpetual_pe(growth, roe, r)

        k_xyb = justified_pb(inp['g2_bank'], inp['roe_xyb'], r_bank) / inp['pb_xyb']

        def legs(tier, growth, pe_res, flat=False):
            pw = pe_white('m' if flat else tier, growth)
            pr = pe_res['m'] if flat else pe_res[tier]
            kb = inp[f'k_bank_{tier}']
            return {
                'white': inp['w_white'] * inp[f'eps_white_{tier}'] * pw / inp['pe_white_now'],
                'cmb': inp['w_cmb'] * inp[f'cmb_{tier}'] / inp['px_cmb'],
                'xyb': inp['w_xyb'] * k_xyb * kb,
                'obank': inp['w_obank'] * kb,
                'yth': inp['w_yth'] * inp[f'yth_{tier}'] / inp['px_yth'],
                'alc': inp['w_alc'] * inp[f'alc_{tier}'] / inp['px_alc'],
                'res': inp['w_res'] * inp[f'eps_res_{tier}'] * pr / inp['pe_res_now'],
            }

        def anchor(tier, growth, pe_res, flat=False):
            return scale(inp['nav_ref'], inp['fee_drag'], sum(legs(tier, growth, pe_res, flat).values()))

        def band(growth, pe_res):
            return tuple(anchor(tier, growth, pe_res) for tier in 'lmh')

        def res_pe(growth):
            value = perpetual_pe(growth, inp['roe_idx'], r)
            return {'l': inp['pe_res_l'], 'm': value, 'h': value}

        base_res = {tier: inp[f'pe_res_{tier}'] for tier in 'lmh'}
        sotp = band(inp['g2_white'], base_res)
        flat = tuple(anchor(tier, inp['g2_white'], base_res, flat=True) for tier in 'lmh')
        if not sotp[0] < sotp[1] < sotp[2] or not flat[0] < flat[1] < flat[2]:
            flags.append('crosscheck_ladder_needs_review')
        sensitivity = {}
        for gw in (inp['g_evid_white_min'], inp['g_evid_white_max']):
            for gr in (inp['g_evid_res_min'], inp['g_evid_res_max']):
                sensitivity[f'white_{gw:g}_residual_{gr:g}'] = dict(zip('LMH', band(gw, res_pe(gr))))
        nav = inp['nav_ref'] * inp['fee_drag']
        middle_legs = legs('m', inp['g2_white'], base_res)
        # Contributions are denominated in fund units; the historical market
        # snapshot is a reference for attribution, not a current quote.
        tier_contributions = {
            tier.upper(): {name: value * nav for name, value in
                           legs(tier, inp['g2_white'], base_res).items()}
            for tier in 'lmh'
        }
        middle_snapshot_delta = {name: (value - inp[f'w_{name}']) * nav
                                 for name, value in middle_legs.items()}
        white_components = {}
        for name in WHITE:
            retaining_growth, retaining_eligible = implied_g_retaining(inp[f'{name}_fpe'], inp[f'{name}_roe'], r)
            full_payout_growth, full_payout_eligible = implied_g(inp[f'{name}_fpe'], inp[f'{name}_roe'], r)
            white_components[name] = {'earnings_weight': weights[name],
                                      'payout': inp[f'{name}_dps25'] / inp[f'{name}_eps25'],
                                      'roe': inp[f'{name}_roe'],
                                      'retaining_growth': retaining_growth,
                                      'retaining_eligible': retaining_eligible,
                                      'full_payout_growth': full_payout_growth,
                                      'full_payout_eligible': full_payout_eligible,
                                      'excluded_from_cluster': name in BLOCKED_WHITE}
        # The original model separately disclosed cash retained in reality but
        # treated as distributed by the growth-based opening-book roll. This is
        # a diagnostic, not an extra asset to add to the valuation.
        retained_cash = {n: ((1 - inp[f'{n}_dps25'] / inp[f'{n}_eps25'])
                             - inp['g2_white'] / inp[f'{n}_roe'])
                         * (inp[f'{n}_fy26'] - inp[f'{n}_h1_26']) for n in WHITE}
        white_payout_model, white_payout_gap = payout_gap(inp['g2_white'], inp['roe_white'], inp['payout_white'])
        residual_payout_model, residual_payout_gap = payout_gap(inp['g2_res_m'], inp['roe_idx'], inp['payout_res'])
        sensitivity['bank_at_market_middle'] = sotp[1] - (middle_legs['xyb'] - inp['w_xyb']) * nav
        sensitivity['bank_roe_9pct_middle'] = (sotp[1] + inp['w_xyb'] *
            (justified_pb(inp['g2_bank'], .09, r_bank) / inp['pb_xyb'] - k_xyb) * nav)
        return {'status': 'available', 'anchors': dict(zip('LMH', sotp)),
                'flat_multiple': dict(zip('LMH', flat)),
                'historical_reference_anchors': dict(HISTORICAL_CROSSCHECK),
                'middle_legs': middle_legs, 'white_growth_fixed_point': fixed_growth,
                'white_growth_cluster': cluster, 'white_retained_cash_per_share': retained_cash,
                'white_components': white_components, 'tier_contributions': tier_contributions,
                'middle_snapshot_delta': middle_snapshot_delta,
                'payout_diagnostics': {'white': {'model': white_payout_model, 'gap': white_payout_gap},
                                       'residual': {'model': residual_payout_model, 'gap': residual_payout_gap}},
                'sensitivity': sensitivity}, sorted(set(flags))
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        flags.append('lookthrough_comparison_requires_reconciliation')
        return {'status': 'unavailable', 'historical_reference_anchors': dict(HISTORICAL_CROSSCHECK)}, sorted(set(flags))


def calculate(context):
    history = normalize_index_history(context.get('external_inputs'), INDEX_CODE)
    # The historical ruler used this fixed research window. Never let earlier
    # or later observations silently change the selected comparison period.
    selected = {day: value for day, value in history.items() if CHANNEL_START <= day <= CHANNEL_END}
    if len(selected) < 2 or max(selected) != CHANNEL_END:
        raise ValueError('index history must contain the explicit historical end date')
    index = pd.Series(selected, dtype=float)
    index.index = pd.to_datetime(index.index)
    index = index.sort_index()
    for start in SUBWINDOWS:
        if len(index[index.index >= start]) < 2:
            raise ValueError('index history is incomplete for the disclosed windows')
    flags = normalize_fund_reference(FUND_REFERENCE, '159263.SZ', CHANNEL_END)
    flags.append('historical_fund_reference_not_same_day_nav')
    if min(selected) > CHANNEL_START:
        flags.append('historical_index_window_incomplete_not_verified_against_reference')
    ch = channel(index)
    sub_slopes = {start[:4]: slope_since(index, start) for start in SUBWINDOWS}
    if max(abs(value - ch['slope']) for value in sub_slopes.values()) >= REGIME_GAP:
        flags.append('index_window_regime_change_requires_review')
    if abs(ch['cur'] - HISTORICAL_INDEX_REFERENCE['level']) > 1:
        flags.append('index_current_level_differs_from_historical_reference')
    factor = FUND_REFERENCE['value'] / ch['cur']
    anchors = {tier: ch[tier] * factor for tier in 'LMH'}
    if not anchors['L'] < anchors['M'] < anchors['H']:
        raise ValueError('fund channel tier order is invalid')
    window_bands = {}
    for start in SUBWINDOWS:
        sample = channel(index[index.index >= start])
        window_bands[start[:4]] = {tier: sample[tier] * factor for tier in 'LMH'}
    wide = channel(index, residual_quantiles=(.05, .95))
    percentile_bands = {tier: wide[tier] * factor for tier in 'LMH'}
    inp = {**INPUTS, 'nav_ref': FUND_REFERENCE['value']}
    crosscheck, peer_flags = _crosscheck(inp, context.get('peers', {}))
    flags.extend(peer_flags)
    # The local comparison is intentionally scoped to stock inputs and stated
    # historical references. Actual external data and peer results have their
    # own digests bound by the runner and cannot be declared confirmed here.
    local = {'inputs': INPUTS, 'fund_reference': FUND_REFERENCE, 'channel_start': CHANNEL_START,
             'channel_end': CHANNEL_END,
             'index_reference': HISTORICAL_INDEX_REFERENCE, 'peer_references': HISTORICAL_PEER_BANDS}
    return {
        'ticker': '159263.SZ', 'currency': 'CNY', 'units': {'price': 'CNY_PER_FUND_UNIT'},
        'valuation_as_of': None, 'framework_as_of': None,
        'historical_financial_basis_as_of': CHANNEL_END,
        'historical_research_as_of': HISTORICAL_RESEARCH_AS_OF,
        'basis_changed': None, 'partial_basis_changed': local_basis_changed(local, BASELINE_FINGERPRINT),
        'anchors': anchors, 'candidate': None, 'option': None,
        'fund_reference_status': 'requires_reconciliation', 'fund_reference': dict(FUND_REFERENCE),
        'segments': {'fund': {'unit': 'CNY_PER_FUND_UNIT', 'values': anchors}},
        'key_parameters': {'method': 'total_return_trend_channel'},
        'operating': {'index_instrument': INDEX_CODE, 'index_start': ch['start'], 'index_end': ch['end'],
                      'index_level': ch['cur'], 'index_slope': ch['slope'], 'index_sigma': ch['sigma'],
                      'subwindow_slopes': sub_slopes, 'reference_factor': factor,
                      'historical_fundamentals': {
                          'pe_2026_09_11': inp['pe_res_now'],
                          # The source disclosed PB 1.10 on 2026-08-14; it is
                          # a historical observation, not recalculated today.
                          'pb_2026_08_14': 1.10, 'roe_2026_08_14': inp['roe_idx'],
                          'dividend_yield_range_2026_09_11': [inp['idx_dy_lo'], inp['idx_dy_hi']],
                          'payout_range_2026_09_11': [inp['idx_dy_lo'] * inp['pe_res_now'],
                                                       inp['idx_dy_hi'] * inp['pe_res_now']],
                          'earnings_yoy': inp['eps_pt_yoy'], 'earnings_from_peak': inp['eps_pt_from_peak'],
                          'weighted_discount_rate_historical_approx': .104},
                      'lookthrough': crosscheck},
        'sensitivity': {'channel_windows': window_bands, 'residual_p05_p95': percentile_bands},
        'review_flags': sorted(set(flags)),
    }
