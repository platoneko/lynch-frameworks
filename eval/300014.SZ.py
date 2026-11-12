#!/usr/bin/env python3
"""Historical EVE Energy core and listed-stake model, not updated research.

Amounts CNY 100 million, shares individual, outputs CNY/share. Historical
Smoore market value is a dated source for the stake, not this stock's quote.
Core earnings exclude Smoore investment income; the stake is valued separately
to prevent double counting. Core M/H and funding-gap assumptions remain the
original historical forecasts, not independently verified future cash flows.

The power-cell convergence option is outside the main band and values the
incremental earnings and corresponding change in the core multiple. The 10%
middle-tier weight is the original judgment with negative current evidence,
not a measured statistical probability; energy-storage economics are excluded.
"""
from __future__ import annotations

import math
from lib.gordon import check_g_cap, check_r, g_cap, payout, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.tiers import flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = 'a7e0fd09c84059089a3d172358a1bd114a0b373f4a27df8af7ef26a5946386a0'

INPUTS = {
    'shares': 2173296935,  # 总股本（转债已全部转股，B9；激励价外不计稀释，B13）；中报; as-of 2026-06-30
    'bps': 23.08,  # 每股净资产 CNY；Longbridge static; as-of 2026-06-30
    'equity_core': 433.96,  # 核心权益 = 归母权益 501.67 − 思摩尔账面 67.71（B3）；**L 档 ROE 分母**（起点，实测）; as-of 2026-06-30
    'equity_core_fwd': 500.94,  # **M/H 档 ROE 分母** = 2027 末核心权益推演：433.96 − 2026 中期股息 0.23 × 股本（2026-09-17 支付，5.0 亿）+ 0.75 × (FY2026H2 核心扣非 27.43 + FY2027E 核心扣非 68.55)；留存 75% = 1 − 近 3 年实付分红率均值 ≈ 25%（FY2023 0.50 / FY2024 0.50+0.245 / FY2025 0.234，yfinance）；不含转股 / 激励稀释; as-of 2026-09-19
    'r_perp': 0.10,  # 篮 4 龙头制造（B17，纠正归篮：初分篮 6 不符合判据——「商品价函数或小盘」对非小盘、盈利 = 出货 × 单位毛利的亿纬不成立；篮 4「常规经营 + 可见度高的行业龙头」成立：17 家 TP 覆盖、FY2027E n=7 带区间、行业排名 `待补`）；不经带（同基带无同等盈利月份，1b 无可比）；零增长 → 1/r 10×；`check_r` → 篮号与值一致；13% / 11% 只作 Outputs 对照带; as-of 2026-09-19
    'nic_l': 27.91,  # **L** 核心扣非 = FY2025 实测扣非 30.96 − 思摩尔权益法 3.05（B1，思摩尔分项 `待补`）; as-of FY2025
    'nic_m': 68.55,  # **M** 核心扣非 = FY2027E 共识均值 EPS 4.571 × 股本 × 26H1 实测核心扣非率 69.0%（裁决顺序 ②，B16）; as-of FY2027E
    'nic_h': 79.48,  # **H** 核心扣非 = FY2027E 共识上沿 EPS 5.30 × 股本 × 69.0%（与 M 三点同源）; as-of FY2027E
    'g2_l': 0.00,  # **L** 永续增长（turnaround 未兑现，回到三年停滞）；g2 来源层级：**无同业锚**·自定；10% 下 ROE_L 6.43% 峰形区，全派息 g=0 = 1/r；cap = 6%; as-of 2026-09-19
    'g2_m': 0.02,  # **M** 永续增长；g2 来源层级：**无同业锚**·自定；10% 下 ROE_M 13.68%（FY2027E ÷ 2027 末权益）单调区 +3.7pp，留存 15% 换 2%；新投资回报走稳态回报三段（B18）→ 倍数 10.12×; as-of 2026-09-19
    'g2_h': 0.035,  # **H** 永续增长；g2 来源层级：**无同业锚**·自定；10% 下 ROE_H 15.87% 单调区 +5.9pp；新投资回报走稳态回报三段（B18）→ 倍数 10.31×; as-of 2026-09-19
    'smoore_book': 67.71,  # 思摩尔 30.25% 长期股权投资账面（6,770,845,832.27 元）；**L 档 \(V^B\)**（B4）; as-of 2026-06-30
    'smoore_mv': 154.72,  # 思摩尔 30.25% 市值口径 = 9.65 HKD × 6,196,185,950 股 × 0.8554 × 30.25%（B4）; as-of 2026-09-08
    'disc_m': 0.70,  # **M** 档思摩尔折价率（非控股 / 减持受限与税负 / 6969.HK 流动性）（B4）; as-of —
    'disc_h': 0.90,  # **H** 档思摩尔折价率（B4）; as-of —
    'pe_own_hi': 63.5,  # own-year PE 实测上沿（2022）；**护栏，不入主公式**（B10）; as-of 2022
    'pe_own_lo': 15.0,  # own-year PE 实测下沿（2026 年内）；**不入主公式**，见 B16（不同基、只披露）; as-of 2026
    'pe_own_ttm_lo': 16.26,  # 自身 5 年月频 TTM PE 实测下沿（2024-01）；Longbridge `valuation --history`；裁决顺序 ③ 参照（B16，与 FY2027E 分子不同基、只披露），**不入主公式**; as-of 2026-09-14
    'pe_own_ttm_hi': 92.78,  # 自身 5 年月频 TTM PE 实测上沿（2021-11）；**不入主公式**; as-of 2026-09-14
    'eps_fy2027e': 4.571,  # FY2027E 归母 EPS 共识均值（yfinance n=7，3.33–5.30）；裁决顺序 ② 的最远带区间年，`nic_m` / `nic_h` 的来源；本行只作同基 PE 参照，锚点路径读 `nic_*`，**不入主公式**; as-of 2026-09-11
    'ni_group_fy2025': 41.34,  # FY2025 归母；三年停滞的实证坐标，**不入主公式**; as-of FY2025
    'ni_excl_fy2025': 30.96,  # FY2025 扣非；`nic_l` 的原始口径，**不入主公式**; as-of FY2025
    'smoore_equity_fy2025': 3.05,  # FY2025 思摩尔权益法收益**估算**（思摩尔 FY2025 净利 ≈10.07 亿 CNY × 30.25%）；`待补` 精确值，**不入主公式**; as-of FY2025
    'smoore_equity_h1': 1.74,  # 2026H1 思摩尔权益法收益（173,757,004.03 元）；**不入主公式**; as-of 2026H1
    'eps_fy2026e': 3.348,  # FY2026E 归母 EPS 共识（H1 实测 1.55 + Q3E 0.8787 + Q4E 0.9190）；**不入主公式**; as-of FY2026E
    'tp_street': 82.74,  # Longbridge 一致目标价 CNY（17 家，49–109）；仅作交叉校验（B11），**不入主公式**; as-of 2026-09-01
    'net_debt': 176.49,  # 净债务（正值 = 净负债）；**不入主公式**; as-of 2026-06-30
    'ocf_h1': -3.88,  # 2026H1 经营现金流（亿元，去年 +23.73）；B8 的观察项，**不入主公式**; as-of 2026H1
    'opt_outstanding': 150000000,  # 股权激励在外份数（期权 147,079,000 + 限制性股票 2,921,000 = 总股本的 6.902%）；B13，**不入主公式**; as-of 2026-06-30
    'opt_strike': 64.86,  # 第七期期权行权价 CNY/份（限制性股票授予价 62.95）；B13，**不入主公式**; as-of 2026-03-03
    'sbc_h1': 4.35,  # 2026H1 计提股权激励成本（434,678,225.76 元 = H1 归母的 13.2%）；已含在扣非分子内（B14），**不入主公式**; as-of 2026H1
    'px_low_2025': 38.42,  # 2025 年内最低收盘（前复权）；L 档实证坐标，**不入主公式**; as-of 2025-04-06
    'px_low_2024': 30.35,  # 2024 年内最低收盘（前复权）；**不入主公式**; as-of 2024-02-04
    'vol_power_fy2025': 50.15,  # 亿纬动力 FY2025 出货 GWh（与收入同源）；**\(V_{opt}\) 输入，不进底牌**（B15）; as-of FY2025
    'ugm_catl_power': 139.5,  # **宁德**动力单位毛利 元/kWh（FY2025 实测）；\(V_{opt}\) 的**上限锚**（B15）; as-of FY2025
    'ugm_eve_power': 80.0,  # 亿纬动力单位毛利 元/kWh（FY2025 实测 = 258.58 × 15.50% ÷ 50.15）；**\(V_{opt}\) 输入**（B15）; as-of FY2025
    'tax_conv': 0.15,  # \(V_{opt}\) 增量毛利适用税率（实际税率 9.68% 不可外推，取常规档）；**\(V_{opt}\) 输入**（B15）; as-of —
    'tau_yr': 0.5,  # 时点对齐年数 τ = 估值基准日 2026-06-30 → 分子年初 2027-01-01；M / H 的 A 腿按 r 折 τ（B18）; as-of 2026-06-30
    'capex_2h26': 53.43,  # 2H26 窗口资本开支（亿）= 1H26 实测节奏（Q1 29.93 + Q2 23.50，yfinance；中报「购建固定资产、无形资产和其他长期资产支付的现金」53.43）；公司无资本开支指引；中报重要在建工程剩余预算约 133.8 亿（五个地区项目，无分年时间表）高于本值、不构成约束（B18）; as-of 2026-06-30
    'ni_2h26_cons': 39.07,  # 2H26 共识归母利润（亿）= Q3E 0.8787 + Q4E 0.9190 EPS × 股本（`eps_fy2026e` 同源）；缺口的经营现金流估计用（B18）; as-of 2026-09-11
    'ocf_ni_3y': 1.5795,  # 近 3 年实测经营现金流 ÷ 净利 = (86.76 + 44.34 + 74.92) ÷ (45.20 + 42.21 + 43.02)（FY2023–25，合并口径，yfinance）; as-of FY2025
    'gap_online_share': 0.833,  # 缺口里产出落在分子年 FY2027 内的份额（电芯产线常规建设期 18 个月、支出均匀：2H26 支出在 2026.75–2028.25 内均匀完工，2027 年末前 1.25 / 1.5）；缺口为 0 时不起作用（B18）; as-of 2026-10-16
    'core_2h26': 27.43,  # 2H26 尚未入账的核心扣非（亿，与分子同口径；`equity_core_fwd` 行同值）；窗口可分配利润 = 本值 × (1 − g2 ÷ 该档前瞻 ROE)，折 τ/2（B18）; as-of 2026-09-19
    'equity_parent': 501.67,  # 归母权益（中报）；归母比例分子（B18）; as-of 2026-06-30
    'nci_cny': 2.32,  # 少数股东权益（yfinance 季报）；归母比例 = 501.67 ÷ (501.67 + 2.32) = 0.9954（B18）; as-of 2026-06-30
    'ss_return': 0.10,  # A 腿新投资**稳态回报**（按序取，2026-10-19）：自身周期不可用（2021 起转动力 / 储能、规模变了，之后还没走完一轮谷到谷）→ 成熟同业层：电芯同业里过成熟判据、≥ 5 年读数的只有三星 SDI（穿越周期 6.9% < r）→ 取 r 10%；兜底 11% 只是替补、不再托底（B18）; as-of 2026-10-19
    't0_ret': 2027,  # 回报路径起点 = M / H 分子年 FY2027（B18）; as-of 2026-10-16
    'y1_ret': 2027,  # 高回报期 Y1 = 可见年末（最远共识年 FY2027）；之后线性回落（B18）; as-of 2026-10-16
    'y2_ret': 2031,  # 高回报期 Y2 = Y1 + 4 年（进入门槛「中」，依据见 B18）; as-of 2026-10-16
    't_num': 2027,  # 分子年 = FY2027E（M/H 共识年）；\(V_{opt}\) 折现终点（B15）；**\(V_{opt}\) 输入**; as-of 2026-10-03
    't_opt': 2029,  # 收敛兑现年 = 对齐年份（本票最远共识年 FY2027）+ 2，**无时点锚·拍值**（公司无单位毛利目标年）；**\(V_{opt}\) 输入**（B15）; as-of 2026-10-03
    'ugm_eve_power_h1': 78.24,  # 2026H1 动力单位毛利 元/kWh（27.98 亿 ÷ 35.76 GWh），**低于 FY2025 的 80.0**；表3 \(p_M\) 的反向锚，**不入主公式、不入 \(V_{opt}\) 公式**（B15）; as-of 2026H1
}

TIERS = ("l", "m", "h")

FORMULA_FIELDS = frozenset({
    "shares", "equity_core", "equity_core_fwd", "r_perp",
    "nic_l", "nic_m", "nic_h",
    "g2_l", "g2_m", "g2_h",
    "smoore_book", "smoore_mv", "disc_m", "disc_h",
    # valuation-rules「经营价值与超额现金」: timing, growth-period funding gap, parent share,
    # steady-return path (B18)
    "tau_yr", "capex_2h26", "ni_2h26_cons", "ocf_ni_3y", "gap_online_share", "core_2h26",
    "equity_parent", "nci_cny", "ss_return", "t0_ret", "y1_ret", "y2_ret",
})

# V_opt's own inputs (B15).  Disjoint from FORMULA_FIELDS on purpose: the
# convergence option MUST NOT reach the base band or any zone boundary.
VOPT_FIELDS = frozenset({
    "vol_power_fy2025", "ugm_catl_power", "ugm_eve_power", "tax_conv",
    "t_num", "t_opt",
})

# 表3 only — never Inputs, never the base band (A2e-7a).
P_K = (0.0, 0.10, 1.0)

REQUIRED = sorted(FORMULA_FIELDS | VOPT_FIELDS | {
    "bps",
    "pe_own_hi", "pe_own_lo", "pe_own_ttm_lo", "pe_own_ttm_hi", "eps_fy2027e",
    "ni_group_fy2025", "ni_excl_fy2025",
    "smoore_equity_fy2025", "smoore_equity_h1", "eps_fy2026e",
    "tp_street", "net_debt", "ocf_h1",
    "opt_outstanding", "opt_strike", "sbc_h1",
    "px_low_2025", "px_low_2024",
    "ugm_eve_power_h1",
})


def core_equity(inp: dict[str, float], tag: str) -> float:
    """L has no incremental retention (turnaround unrealised) so it reads the
    2026-06-30 book; M/H read the book rolled to end-2027 (B3)."""
    return inp["equity_core"] if tag == "l" else inp["equity_core_fwd"]


def core_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"nic_{tag}"] / core_equity(inp, tag)


def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-segment RONIC path (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    gordon.py helper is not built yet).  Multiple on the numerator year t0 (t = 1): the
    retention of calendar year c earns the forward roe while c <= y1, falls linearly to the
    steady return by y2, and from y2 on the steady return holds in a Gordon tail.  r_s is
    capped at the forward roe.  g <= 0 never consumes RONIC -> plain perpetuity."""
    if g <= 0:
        return perpetual_pe(g, roe, r)
    rs = min(roe, r_s)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs
        return roe + (rs - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1


def leg_pe(inp: dict[str, float], g: float, roe: float) -> float:
    """A-leg multiple on the FY2027E numerator: steady return = max(ss_return, r) (B18)."""
    return path_pe(g, roe, inp["r_perp"], int(inp["t0_ret"]), int(inp["y1_ret"]), int(inp["y2_ret"]),
                   max(inp["ss_return"], inp["r_perp"]))


def multiple(inp: dict[str, float], tag: str) -> float:
    return leg_pe(inp, inp[f"g2_{tag}"], core_roe(inp, tag))


def parent_ratio(inp: dict[str, float]) -> float:
    return inp["equity_parent"] / (inp["equity_parent"] + inp["nci_cny"])


def funding_gap(inp: dict[str, float]) -> tuple[float, float, float]:
    """Growth-period funding gap (valuation-rules「经营价值与超额现金」① 增长期资金缺口, B18).
    Window 2H26.  取数序 tier 2 (no sell-side cash-flow forecast, no company capex guidance):
    capex = 1H26 measured pace (in-construction budget remaining well above it); operating
    cash flow = window consensus profit x the 3-year measured OCF / net income — NOT the 1H26
    OCF, whose -3.88亿 is the inventory build (B8), a timing item.  Only the share producing
    inside FY2027 counts.  Returns (raw capex - OCF, OCF estimate, gap)."""
    ocf = inp["ni_2h26_cons"] * inp["ocf_ni_3y"]
    raw = inp["capex_2h26"] - ocf
    return raw, ocf, max(0.0, raw) * inp["gap_online_share"]


def window_profit(inp: dict[str, float], tag: str) -> float:
    """Window distributable profit (③ 时点对齐): 2H26 core profit not yet booked x (1 - b),
    b = g / forward ROE, discounted tau/2.  Recorded as 0 whenever a funding gap exists."""
    if funding_gap(inp)[2] > 0:
        return 0.0
    b = min(1.0, max(0.0, inp[f"g2_{tag}"] / core_roe(inp, tag)))
    return inp["core_2h26"] * (1.0 - b) * (1.0 + inp["r_perp"]) ** (-inp["tau_yr"] / 2)


def timed(inp: dict[str, float], tag: str, value_tn: float) -> float:
    """时点对齐 (B18): the M/H A leg is a value at the opening of FY2027 -> today = x (1+r)^-tau,
    plus the window distributable profit, less any funding gap (debt-like, x parent ratio).
    L reads FY2025 on today's book: numerator year already past -> tau 0, no window, no gap."""
    if tag == "l":
        return value_tn
    return (value_tn * (1.0 + inp["r_perp"]) ** -inp["tau_yr"] + window_profit(inp, tag)
            - funding_gap(inp)[2] * parent_ratio(inp))


def leg_a(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return timed(inp, tag, inp[f"nic_{tag}"] * pe)


def leg_b(inp: dict[str, float], tag: str) -> float:
    """L reads EVE's own carrying value; M/H read 6969.HK at a discount."""
    if tag == "l":
        return inp["smoore_book"]
    return inp["smoore_mv"] * inp[f"disc_{tag}"]


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    return (leg_a(inp, tag, flat_pe) + leg_b(inp, tag)) * 1e8 / inp["shares"]


def convergence_option(inp: dict[str, float], base_h: float) -> dict[str, float]:
    """V_opt — EVE's power cells earning what CATL's already earn (B15).

    Runs the converged numerator back through the SAME Gordon ruler rather than
    multiplying the delta by PE_H: the extra profit lifts core ROE from 15.87%
    to 20.93%, and at the basket r that lifts the multiple too.  Pricing the
    delta at the old multiple would understate the option by about a fifth.
    """
    gap = inp["ugm_catl_power"] - inp["ugm_eve_power"]      # CNY/kWh
    delta_gp = inp["vol_power_fy2025"] * gap / 100.0        # GWh x CNY/kWh -> 亿
    delta_ni = delta_gp * (1.0 - inp["tax_conv"])
    nic_conv = inp["nic_h"] + delta_ni
    roe_conv = nic_conv / core_equity(inp, "h")
    pe_conv = leg_pe(inp, inp["g2_h"], roe_conv)
    # same timing as H: the difference to H is then F x (converged - H) on the t_n basis
    anchor_conv = (timed(inp, "h", nic_conv * pe_conv) + leg_b(inp, "h")) * 1e8 / inp["shares"]
    return {
        "gap": gap, "delta_gp": delta_gp, "delta_ni": delta_ni,
        "nic_conv": nic_conv, "roe_conv": roe_conv, "pe_conv": pe_conv,
        "anchor_conv": anchor_conv, "v_undisc": anchor_conv - base_h,
        # valuation-rules「未建模期权」2026-10-03 时点: value in the realisation
        # year, discounted back to the numerator year at the basket r.
        "disc": (1.0 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"])),
        "v_opt": (anchor_conv - base_h) * (1.0 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"])),
    }


def safe_convergence_option(inp, base):
    unavailable = {'status': 'unavailable', 'label': '动力电芯毛利收敛', 'anchors': None}
    if inp['t_opt'] < inp['t_num']:
        return unavailable, None
    try:
        details = convergence_option(inp, base['H'])
        if any(not math.isfinite(value) for value in details.values()) or details['v_opt'] < 0:
            raise ValueError('invalid convergence option')
        prices = {tier: base[tier] + credit * details['v_opt'] for tier, credit in zip('LMH', P_K)}
        if not all(math.isfinite(v) for v in prices.values()) or not prices['L'] < prices['M'] < prices['H']:
            raise ValueError('invalid convergence option band')
    except (ArithmeticError, TypeError, ValueError):
        return unavailable, None
    return {'label': '动力电芯毛利收敛', 'value': details['v_opt'], 'value_unit': 'CNY_PER_SHARE',
            'weights': dict(zip('LMH', P_K)), 'anchors': prices, 'details': details}, details


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    # These fields name calendar years, unlike tau_yr, which is a duration.
    for key in ('t0_ret', 'y1_ret', 'y2_ret', 't_num', 't_opt'):
        if isinstance(inp[key], bool) or not float(inp[key]).is_integer():
            raise ValueError(f'{key} must be a whole calendar year')
    r = inp['r_perp']
    if (r <= 0 or r <= max(inp[f'g2_{tier}'] for tier in TIERS)
            or min(inp['equity_core'], inp['equity_core_fwd'], inp['shares']) <= 0
            or inp['equity_parent'] + inp['nci_cny'] == 0):
        raise ValueError('invalid base valuation discount or denominator')
    warnings = []
    errors += ladder('nic', inp['nic_l'], inp['nic_m'], inp['nic_h'])
    errors += ladder('g2', inp['g2_l'], inp['g2_m'], inp['g2_h'])
    errors += check_r(r, 'r_perp', 4)
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []
    roe = {t: core_roe(inp, t) for t in TIERS}
    for t in TIERS:
        if roe[t] == 0 and inp[f'g2_{t}'] != 0:
            raise ValueError(f'{t}: nonzero growth needs a nonzero return')
        g = inp[f'g2_{t}']
        errors += check_g_cap(g, r, f'g2_{t}')
        if r - g <= 0:
            errors.append(f'{t}: perpetuity diverges')
        pay = payout(g, roe[t])
        if not 0 < pay <= 1 + 1e-12:
            errors.append(f'{t}: payout outside (0,1]')
        if g <= 0 and abs(pay - 1) > 1e-12:
            errors.append(f'{t}: zero growth does not pay out fully')
    if errors:
        warnings.append('historical_growth_and_return_guards_require_review')
        errors = []
    vb = {t: leg_b(inp, t) for t in TIERS}
    errors += ladder('listed stake', vb['l'], vb['m'], vb['h'])
    if not 0 < inp['disc_m'] < inp['disc_h'] <= 1:
        errors.append('listed-stake discount ordering invalid')
    if inp['smoore_book'] >= inp['smoore_mv']:
        errors.append('listed stake no longer above carrying value')
    pe = {t: multiple(inp, t) for t in TIERS}
    if pe['h'] > inp['pe_own_hi'] + 1e-9:
        errors.append('H PE above own-year historical high')
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append('base anchor uses a non-formula field')
    if errors:
        warnings.append('historical_stake_and_pe_guards_require_review')
        errors = []
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not all(math.isfinite(value) for value in (L, M, H)) or not L < M < H:
        raise ValueError('base valuation tiers must be finite and ordered')
    nic3 = (inp['nic_l'], inp['nic_m'], inp['nic_h'])
    flat_errors, flat_va = flat_multiple_ladder(nic3, pe['m'])
    errors += flat_errors + ladder('flat core', *flat_va)
    flat_anchor = tuple(anchor(inp, t, flat_pe=pe['m']) for t in TIERS)
    errors += ladder('flat anchor', *flat_anchor)
    if inp['opt_strike'] <= H:
        errors.append('incentive strike is inside the band; share dilution must be re-evaluated')
    if FORMULA_FIELDS & VOPT_FIELDS:
        errors.append('option inputs leaked into base formula')
    if any(k.startswith('p_') for k in inp):
        errors.append('probability-style fields are not allowed in inputs')
    option, opt = safe_convergence_option(inp, dict(zip('LMH', (L, M, H))))
    if opt is None:
        warnings.append('historical_convergence_option_unavailable')
    if errors:
        warnings.append('historical_economic_guards_require_review')

    raw, ocf, gap = funding_gap(inp)
    alt = ({**inp, 'ni_2h26_cons': inp['ocf_h1'] / inp['ocf_ni_3y']}
           if inp['ocf_ni_3y'] else None)
    if alt is None:
        warnings.append('historical_ocf_comparison_unavailable')
    def optional_value(fn, *, nonnegative=False):
        def finite(value):
            if isinstance(value, dict):
                return all(finite(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return all(finite(item) for item in value)
            return not isinstance(value, (int, float)) or (math.isfinite(value) and (not nonnegative or value >= 0))
        try:
            value = fn()
            if finite(value):
                return value
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_sensitivity_unavailable')
        return None
    # Original document comparisons, kept separate from the adopted model.
    sensitivity = {
        'historical_ocf_funding_gap': optional_value(lambda: funding_gap(alt)[2]) if alt is not None else None,
        'historical_ocf': optional_value(lambda: dict(zip('LMH', (anchor(alt, t) for t in TIERS)))) if alt is not None else None,
        'flat_multiple': dict(zip('LMH', flat_anchor)),
        'middle_growth_minus_1pp': optional_value(lambda: anchor({**inp, 'g2_m': inp['g2_m'] - .01}, 'm')),
        'middle_growth_plus_1pp': optional_value(lambda: anchor({**inp, 'g2_m': inp['g2_m'] + .01}, 'm')),
        'rate_minus_05pp': optional_value(lambda: dict(zip('LMH', (anchor({**inp, 'r_perp': r - .005}, t) for t in TIERS)))),
        'rate_plus_05pp': optional_value(lambda: dict(zip('LMH', (anchor({**inp, 'r_perp': r + .005}, t) for t in TIERS)))),
        'basket_6': optional_value(lambda: dict(zip('LMH', (anchor({**inp, 'r_perp': .13}, t) for t in TIERS)))),
        'basket_5': optional_value(lambda: dict(zip('LMH', (anchor({**inp, 'r_perp': .11}, t) for t in TIERS)))),
        'steady_11pct_middle': optional_value(lambda: anchor({**inp, 'ss_return': .11}, 'm')),
        'steady_12pct_middle': optional_value(lambda: anchor({**inp, 'ss_return': .12}, 'm')),
        'steady_forward': optional_value(lambda: dict(zip('LMH', (anchor({**inp, 'ss_return': 1}, t) for t in TIERS)))),
        'option_middle_weight_0': M,
        'option_middle_weight_030': M + .30 * opt['v_opt'] if opt is not None else None,
        'option_unit_margin_120': optional_value(lambda: convergence_option({**inp, 'ugm_catl_power': 120}, H)['v_opt']),
        'option_unit_margin_150': optional_value(lambda: convergence_option({**inp, 'ugm_catl_power': 150}, H)['v_opt']),
        'option_realization_2028': optional_value(lambda: convergence_option({**inp, 't_opt': 2028}, H)['v_opt']),
        'option_realization_2030': optional_value(lambda: convergence_option({**inp, 't_opt': 2030}, H)['v_opt']),
    }
    a, b = cut_points(L, M, H)
    as_band = lambda values: dict(zip('LMH', values))
    # Historical sources include a 2026-06-30 balance-sheet date and a
    # 2026-10-19 study date. They do not certify the current model basis.
    return {'ticker': '300014.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'framework_as_of': None,
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b}, 'candidate': None,
            'option': option,
            'review_flags': warnings,
            'segments': {'core': {'values': as_band(leg_a(inp, t) * 1e8 / inp['shares'] for t in TIERS)},
                         'smoore': {'values': as_band(leg_b(inp, t) * 1e8 / inp['shares'] for t in TIERS)}},
            'key_parameters': {'core': {'discount_rate': dict.fromkeys('LMH', r),
                                        'growth_rate': as_band(inp[f'g2_{t}'] for t in TIERS),
                                        'forward_return': as_band(roe[t] for t in TIERS),
                                        # At zero growth the low tier distributes all earnings;
                                        # its multiple does not use any steady investment return.
                                        'steady_return': as_band(None if inp[f'g2_{t}'] <= 0 else min(roe[t], max(inp['ss_return'], r)) for t in TIERS),
                                        'multiple': as_band(pe[t] for t in TIERS)},
                               'smoore': {'method': {'L': 'book_value', 'M': 'market_value', 'H': 'market_value'},
                                          'market_value_weight': {'L': None, 'M': inp['disc_m'], 'H': inp['disc_h']}}},
            'operating': {'raw_funding_gap': raw, 'forecast_ocf': ocf, 'funding_gap': gap,
                          'window': as_band(window_profit(inp, t) if t != 'l' else 0 for t in TIERS),
                          'parent_ratio': parent_ratio(inp), 'core_return': roe, 'listed_stake': vb},
            'sensitivity': sensitivity}


def calculate(context):
    result = evaluate(dict(INPUTS))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    for segment in result['segments'].values():
        segment['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        values = result['key_parameters']['core'][name]
        result['key_parameters']['core'][name] = {'unit': 'RATIO', 'values': values}
    result['key_parameters']['core']['steady_return']['reference_value'] = INPUTS['ss_return']
    result['historical_financial_statement_as_of'] = '2026-06-30'
    result['historical_research_as_of'] = '2026-10-19'
    result['review_flags'].extend(['historical_funding_and_stake_value_unverified',
                                   'historical_power_margin_convergence_unverified'])
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'option_weights': P_K,
         'formula_fields': sorted(FORMULA_FIELDS), 'option_fields': sorted(VOPT_FIELDS)}, BASELINE_LOCAL)
    return result
