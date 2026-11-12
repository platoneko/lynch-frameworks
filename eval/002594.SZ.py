#!/usr/bin/env python3
"""Historical BYD 2028 forecast model with a separate battery option.

Amounts and share counts follow original inputs; outputs are CNY/share. The
document and input comments retain source names, dates and evidence gaps.
L freezes the original price-war earnings; M/H are historical analyst
forecasts, not updated consensus. The user-approved return path is distinct
from the forward-profit path. The external-battery growth option enters H only,
without an independently evidenced probability or duplication of vehicle
earnings, and depends on future production and independently assumed economics.
"""
# Historical evidence retained from the document:
# The 19 FY2028 estimates were collected after 2026H1 and before Q3; Guangfa
# 2026-10-08 supplies the high. They do not establish post-Q3 consensus.
# FY2025 earnings are L's continuing condition, not a forecast of actual
# future earnings. Its cap follows the original low-return-domain decision.
# M/H's 2026–2028 forecast growth implies modeled full retention through the
# window; no window distribution is added. The 2028–2030 return fade is
# an assumption; mature 10%/10%/15% values are not realized project returns.
# Q3 capex was about 426.76 CNY 100 million and inventory increased by
# about 832 versus year-end. The original zero future funding gap requires
# future capex, operating cash and financing forecasts; it is not verified.
# Battery extra value annualizes a single April 2026 external-installation
# snapshot, discounts another company's H1 unit profit by 30%, and deducts
# new capacity capital. The 2030 realization and future volume/margins are
# unverified; the separate value must not duplicate group forecast profits.
from __future__ import annotations

import math
from lib.gordon import check_branch, check_g_cap, check_r, g_cap, payout, payout_gap, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.tiers import flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = '35f9ebdabc7cc6912ac4639a15e8859f66caf09a0bf40daa749a495f38d00c74'

INPUTS = {
    'shares': 9117197565,  # 总股本（A 54.338 亿 + H 36.834 亿）；三季报股本 9,117,198 千元; as-of 2026-09-30
    'equity': 2489.72704,  # 普通股归母权益 = 归属于母公司所有者权益合计 2,660.53519 − 永续债 170.80815（三季报合并资产负债表，元换算）；A6; as-of 2026-09-30
    'dps_after': 0,  # 估值基准日之后待派股息：FY2025 股息 0.358 已于 2026-07-31 派、已在 3Q26 账面里 → 0；A6; as-of 2026-09-30
    'ni_booked': 223.44978,  # 2026 年已入账归母净利 = 1–3Q26（三季报「归属于母公司股东的净利润」22,344,978,000 元）；只用于把账面滚到分子年初; as-of 2026-09-30
    'r_perp': 0.10,  # 篮 4 常规经营：车价自定、盈利不是商品价函数，无单一客户、无单一国别依赖（A4）；值 = `gordon.BASKET_R[4]`; as-of 2026-10-09
    'g2': 0.03,  # 三档同一永续增长；**来源层级：无同业锚**（A5）；≤ 巨型硬件上限 min(4%, r−4%); as-of 2026-10-09
    'tau': 1.25,  # 时点对齐年数：估值基准日 2026-09-30（三季报资产负债表日）→ M / H 分子年初 2028-01-01；L（冻结的常态年）不对齐（A17）; as-of 2026-10-30
    'y1': 2028,  # 高回报期开始回落年 = 可见年末（FY2028 是最远 ≥2 家共识年）（A16）; as-of 2026-10-16
    'y2': 2030,  # 回落到稳态年 = Y1 + 2（进入门槛「低」：整车厂建成约 1.5–2 年、面向消费者无 B 端认证周期、小米 / 零跑等新进入者 2–3 年内拿到可观份额）（A16）; as-of 2026-10-16
    'rs_ss': 0.10,  # 稳态回报（三档，整车与外供电池同值）= 按序取：自身周期不可用（2022 年停燃油车、规模跳变后未走完一轮）→ 同业层：全球成熟整车（大众、通用、现代、Stellantis）穿越周期中位 4.9% < r → 取 r 10%；电芯同业三星 SDI 6.9% < r 同取 r；兜底 11% 不再托底（A16；用户 2026-10-19 认可）；按「三档各取各的稳态」本值管 L / M; as-of 2026-10-19
    'rs_ss_h': 0.15,  # H 档稳态回报（整车与外供电池期权同值）：三档各取各的稳态 + 上调看进入门槛——整车门槛「低」，高档最多升到兜底表上一格（商品化重资产 11% → 有壁垒的重资产 15%：高档世界里比亚迪靠垂直一体化与海外溢价自建壁垒）；卖方高档前瞻 23.1% 不按永续取（A16；用户 2026-10-19 认可）; as-of 2026-10-19
    'eps_l': 3.5777,  # **L** = FY2025 实测 EPS（归母 326.19 亿 ÷ 股本）冻结（A2）; as-of FY2025
    'eps_m': 6.7447,  # **M** = FY2028E 共识均值（东方财富 F10，半年报后 19 家，A1）; as-of 2026-10-09
    'eps_h': 8.16,  # **H** = FY2028E 共识最高一家（广发 2026-10-08，A1）; as-of 2026-10-08
    'consensus_n_fy28': 19,  # FY2028E 家数（≥2 才可作分子年）; as-of 2026-10-09
    'eps_fy28_lo': 4.40,  # FY2028E 最低一家（光大 2026-08-31）；压力坐标，**不入主公式**; as-of 2026-08-31
    'eps_fy26_m': 4.2243,  # FY2026E 共识均值（20 家）；只经 M 档账面滚动进 ROE; as-of 2026-10-09
    'eps_fy27_m': 5.5677,  # FY2027E 共识均值（20 家）；只经 M 档账面滚动进 ROE; as-of 2026-10-09
    'eps_fy26_h': 4.37,  # 广发 FY2026E；只经 H 档账面滚动进 ROE; as-of 2026-10-08
    'eps_fy27_h': 6.39,  # 广发 FY2027E；只经 H 档账面滚动进 ROE; as-of 2026-10-08
    'eps_ttm': 3.4694,  # TTM EPS（4Q25–3Q26 归母 316.31 亿 = 1–3Q26 223.45 + FY2025 326.19 − 1–3Q25 233.33）；压力坐标，**不入主公式**; as-of 2026-09-30
    'payout_fy25': 0.10,  # FY2025 实付派息率（0.358 × 91.17 亿股 ÷ 326.19 亿）；`check_branch` / `payout_gap`，**不入主公式**; as-of FY2025
    'payout_3y': 0.233,  # 近三年实付派息率均值（30.0% / 30.0% / 10.0%）；对账门股息尺坐标，**不入主公式**; as-of FY2023–25
    'pe_eq_lo': 19.68,  # L 档同等盈利月份（TTM EPS 3.15–4.01）最低 TTM PE（2024-03-31）；A9，**不入主公式**; as-of 2024-03-31
    'pe_eq_n': 15,  # 上述同等盈利月份数；A9; as-of 2026-09-30
    'roe_band': 0.216,  # 带下沿月份 TTM ROE；A9，**不入主公式**; as-of 2024-03-31
    'g_exp_band': 0.25,  # 带下沿月份点时共识 FY2024→FY2025 预期增速中位；A9，**不入主公式**; as-of 2024-02-06
    'pb_lo_5y': 3.13,  # 5 年月频 PB 下沿（2026-06-30 收盘 ÷ 2026Q1 BPS）；对账门坐标 ⑥，**不入主公式**; as-of 2026-06-30
    'pb_lo_all': 2.23,  # 2016 年起月频 PB 下沿（2019-10-31）；对账门坐标 ⑥′，**不入主公式**; as-of 2019-10-31
    'net_debt': 509.95,  # 净债务（含永续债）= 短借 186.70 + 一年内到期 34.93 + 长借 594.80 + 应付债券 149.94 + 租赁 90.00 + 永续债 170.81 − 货币资金 309.88 − 交易性金融资产 407.35（三季报）；A8，**不入主公式**; as-of 2026-09-30
    'ebit_fy25': 401.85,  # FY2025 营业利润（东方财富）；A8，**不入主公式**; as-of FY2025
    'da_1h26': 404.79,  # 2026H1 折旧摊销（固定资产 364.64 + 投资性房地产 0.01 + 使用权资产 12.96 + 无形资产 16.92 + 长期待摊 10.26）；三季报不披露折旧，沿用中报；A7 / A8，**不入主公式**; as-of 2026-06-30
    'int_9m26': 28.10841,  # 1–3Q26 利息费用（三季报利润表「其中：利息费用」2,810,841,000 元）；eval 按 ×4/3 年化；A8，**不入主公式**; as-of 2026-09-30
    'fd_install_apr': 11.133,  # 弗迪电池 2026 年 4 月国内装机 GWh；\(V_{opt}\) 输入（A10）; as-of 2026-04
    'fd_ext_share': 0.42,  # 同月外供占比（1 − 自用 58.0%）；\(V_{opt}\) 输入，单月快照; as-of 2026-04
    'unit_profit_catl': 86.92,  # 宁德 2026H1 单位净利 元/kWh（`300750.SZ`）；\(V_{opt}\) 单位经济; as-of 2026-06-30
    'unit_disc': 0.30,  # 单位经济折扣（品牌与规模差，拍值）；\(V_{opt}\) 输入; as-of 2026-10-09
    'capex_per_gwh': 2.3333,  # 新产能单 GWh 预算 亿元（宁德洛阳 140 亿 / 60 GWh，`300750.SZ` `dom_budget_gwh`）；\(V_{opt}\) 扣资本; as-of 2022-09-28
    't_num': 2028,  # 分子年；\(V_{opt}\) 折现终点; as-of 2026-10-09
    't_opt': 2030,  # 外供翻倍兑现年 = 对齐年份 + 2（无时点锚·拍值）；\(V_{opt}\) 输入；也是外供电池回报路径的起算年; as-of 2026-10-09
    'y1_opt': 2030,  # 外供电池高回报期止点 = 兑现年：外供在放量、要过整车厂认证，翻倍的量 2030 年才到规模，此前不属于成熟阶段（A10 / A16）；\(V_{opt}\) 输入; as-of 2026-10-19
    'y2_opt': 2034,  # 外供电池回落到稳态年 = `y1_opt` + 4（电池判中门槛：整车厂认证 1–2 年、需工艺积累；与 `300750.SZ` 电池同档）（A10 / A16）；\(V_{opt}\) 输入; as-of 2026-10-19
    'tp_hsbc': 121,  # 汇丰 A 股 TP（SOTP）；交叉，**不入主公式**; as-of 2026-09-15
    'tp_citi': 131,  # 花旗 A 股 TP（PEG）；交叉，**不入主公式**; as-of 2026-08-29
    'tp_ubs': 136,  # 瑞银 A 股 TP（SOTP）；交叉，**不入主公式**; as-of 2026-09-08
    'tp_consensus': 116.87,  # 一致 TP（Longbridge，23 家）；交叉，**不入主公式**; as-of 2026-10-08
}

TIERS = ("l", "m", "h")
MIN_SPREAD = 0.02           # r - g2 floor (valuation-rules ①)
MIN_CONSENSUS_HOUSES = 2    # a numerator year needs >= 2 houses with a range (②)
MONO_GAP = 0.03             # 域判定表: ROE − r ≥ 3pp is the monotone domain
DISTORTED_GAP = 0.10       # ③ step 1b: then-expected growth − model g >= 10pp/yr
RECONCILE_TOL = 0.20        # 纠正对账门: M within 20% of >= 1 independent coordinate
MEGA_HW = True              # A5: hardware, FY2028E revenue >= $150B, no proven pricing power
FY_NOW = 2026               # current fiscal year: the window segment's growth runs FY2026E -> numerator year

FORMULA_FIELDS = frozenset({
    "shares", "equity", "dps_after", "ni_booked", "r_perp", "g2", "tau", "y1", "y2", "rs_ss", "rs_ss_h", "t_num",
    "eps_l", "eps_m", "eps_h",
    "eps_fy26_m", "eps_fy26_h", "eps_fy27_m", "eps_fy27_h",
})

REQUIRED = sorted(FORMULA_FIELDS | {
    "consensus_n_fy28", "eps_fy28_lo", "eps_ttm", "payout_fy25", "payout_3y",
    "pe_eq_lo", "pe_eq_n", "roe_band", "g_exp_band", "pb_lo_5y", "pb_lo_all",
    "net_debt", "ebit_fy25", "da_1h26", "int_9m26",
    "fd_install_apr", "fd_ext_share", "unit_profit_catl", "unit_disc",
    "capex_per_gwh", "t_opt", "y1_opt", "y2_opt",
    "tp_hsbc", "tp_citi", "tp_ubs", "tp_consensus",
})

# 表3 only — never Inputs, never the base band (A2e-7a).  No sell-side volume
# for the external-battery leg → the option enters H only (A10).
P_K = (0.0, 0.0, 1.0)


def bps0(inp: dict[str, float]) -> float:
    """Common BPS at the latest balance sheet (perpetual bonds excluded) less any dividend paid after it."""
    return inp["equity"] * 1e8 / inp["shares"] - inp["dps_after"]


def eps_booked(inp: dict[str, float]) -> float:
    """FY2026 EPS already in the book (1-3Q26)."""
    return inp["ni_booked"] * 1e8 / inp["shares"]


def unbooked(inp: dict[str, float], tag: str) -> float:
    """EPS earned before the numerator year but not yet in the 3Q26 book."""
    if tag == "l":
        return inp["eps_l"] - eps_booked(inp)               # 4Q26 at the frozen FY2025 level
    return inp[f"eps_fy26_{tag}"] - eps_booked(inp) + inp[f"eps_fy27_{tag}"]


def g_win(inp: dict[str, float], tag: str) -> float:
    """Growth of this window segment (valuation-rules「经营价值与超额现金」③ 时点对齐: b = g/RONIC, g = the
    segment's own growth).  M / H: the tier's own consensus path from the current year FY2026E to the
    numerator year (mean / 广发), annualised -- the same path the window and the book roll read.  L: the
    frozen regime world grows at g2 from today (no transition, no window)."""
    if tag == "l":
        return inp["g2"]
    years = inp["t_num"] - FY_NOW
    return (inp[f"eps_{tag}"] / inp[f"eps_fy26_{tag}"]) ** (1.0 / years) - 1.0


def bps_open(inp: dict[str, float], tag: str) -> float:
    """Opening BPS of the numerator year: BPS0 + N x b, b = min(1, max(0, g_win/ROE)) -- fixed point
    (b above 1 is cut to 1: the window keeps every yuan, valuation-rules 第 8 轮裁定 5)."""
    g, n, e = g_win(inp, tag), unbooked(inp, tag), inp[f"eps_{tag}"]
    bps = bps0(inp)
    for _ in range(500):
        nxt = bps0(inp) + n * min(1.0, max(0.0, g * bps / e))
        if abs(nxt - bps) < 1e-13:
            break
        bps = nxt
    return bps


def roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"eps_{tag}"] / bps_open(inp, tag)


def b_win(inp: dict[str, float], tag: str) -> float:
    """Growth-required retention of the window, shared by the book roll and the window profit."""
    return min(1.0, max(0.0, g_win(inp, tag) / roe(inp, tag)))


def path_pe(g2: float, roe_: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-stage return path Gordon (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    library function is not built yet): forward return held to calendar Y1, linear to the steady
    return by Y2, steady after; per unit of t0 earnings."""
    rs = min(roe_, r_s)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g2, rs) / ((r - g2) * (1.0 + r) ** (t - 1))
        ro = roe_ if cal <= y1 else roe_ + (rs - roe_) * (cal - y1) / (y2 - y1)
        pv += e * payout(g2, ro) / (1.0 + r) ** t
        e *= 1.0 + g2
        t += 1


def rs_tier(inp: dict[str, float], tag: str) -> float:
    """Steady return by tier (retention「三档各取各的稳态」): L / M = the ordered value 10%
    (mature-peer layer below r -> r); H = 15% (low entry barrier: one notch up the fallback table)."""
    return max(inp["rs_ss_h"] if tag == "h" else inp["rs_ss"], inp["r_perp"])


def peak_domain(inp: dict[str, float], tag: str) -> bool:
    """ROE − r < 3pp: no longer in the monotone domain (valuation-rules 域判定表)."""
    return roe(inp, tag) - inp["r_perp"] < MONO_GAP


def multiple(inp: dict[str, float], tag: str) -> float:
    """A15: forward ROE to Y1 (2028, visible-year end), linear to the tier's steady return by Y2
    (2030, low entry barrier), steady after.  A tier in the peak domain is capped at 1/r (A6, 2026-10-30:
    the frozen L world's surplus retention goes into working capital and capacity without adding profit)."""
    pe = path_pe(inp["g2"], roe(inp, tag), inp["r_perp"], int(inp["t_num"]), int(inp["y1"]),
                 int(inp["y2"]), rs_tier(inp, tag))
    return min(pe, 1.0 / inp["r_perp"]) if peak_domain(inp, tag) else pe


def disc(inp: dict[str, float], tag: str) -> float:
    """Time alignment (valuation-rules「经营价值与超额现金」③): M / H are FY2028 values at
    2028-01-01 -> (1+r)^-tau from the 2026-09-30 balance sheet; L (frozen FY2025 regime year) is not aligned."""
    years = 0.0 if tag == "l" else inp["tau"]
    return (1.0 + inp["r_perp"]) ** (-years)


def window(inp: dict[str, float], tag: str) -> float:
    """Window distributable profit (4Q26 + FY2027 unbooked consensus EPS) x (1 - b), b = g_win/ROE cut to
    [0, 1], discounted tau/2; L none."""
    if tag == "l":
        return 0.0
    w = unbooked(inp, tag) * (1.0 - b_win(inp, tag))
    return w * (1.0 + inp["r_perp"]) ** (-inp["tau"] / 2)


def op_anchor(inp: dict[str, float], tag: str) -> float:
    return inp[f"eps_{tag}"] * multiple(inp, tag) * disc(inp, tag)


def anchor(inp: dict[str, float], tag: str) -> float:
    return op_anchor(inp, tag) + window(inp, tag)


def battery_option(inp: dict[str, float], base_h: float) -> dict[str, float]:
    """V_opt — one more unit of today's external battery supply (A10).

    Size: k = 1 × the April-2026 snapshot of external installs annualised
    (FinDreams domestic installs × external share × 12), 「快照·下限」.  Unit
    economics: CATL's 2026H1 unit net profit less a named haircut.  Ruler:
    this ticker's Gordon (same g2, same steady 10%), the return level = the H
    tier's ROE with the option added; only the INCREMENTAL battery EPS is valued,
    on the battery's own return path (2026-10-19 round 9, valuation-rules
    「稳态回报三段」高回报期对产品阶段): the path's calendar starts at the
    realisation year t_opt, high return held to y1_opt (= t_opt: the doubled
    volume reaches scale only then), linear to the steady return by y2_opt
    (medium barrier, OEM certification 1–2 years → 4 years).  The H base keeps
    the car path -- the option must not re-rate the car business on the battery's
    timeline.  Value at t_opt, discounted like H (tau) and back t_opt -> t_num.
    Less the capital for the new capacity at CATL's announced per-GWh budget,
    charged once in the realisation year.
    """
    gwh = inp["fd_install_apr"] * inp["fd_ext_share"] * 12.0
    unit = inp["unit_profit_catl"] * (1.0 - inp["unit_disc"])            # 元/kWh
    d_ni = gwh * unit / 100.0                                            # 亿
    d_eps = d_ni * 1e8 / inp["shares"]
    eps_post = inp["eps_h"] + d_eps
    roe_post = eps_post / bps_open(inp, "h")
    pe_post = path_pe(inp["g2"], roe_post, inp["r_perp"], int(inp["t_opt"]), int(inp["y1_opt"]),
                      int(inp["y2_opt"]), rs_tier(inp, "h"))   # the battery's own path, H world
    incr = d_eps * pe_post * disc(inp, "h")
    anchor_post = base_h + incr
    k_ps = gwh * inp["capex_per_gwh"] * 1e8 / inp["shares"] * disc(inp, "h")
    d_real = (1.0 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    return {"gwh": gwh, "unit": unit, "d_ni": d_ni, "d_eps": d_eps, "roe_post": roe_post,
            "pe_post": pe_post, "anchor_post": anchor_post, "k_ps": k_ps, "d_real": d_real,
            "incr": incr, "v_gross": incr * d_real,
            "v_opt": (incr - k_ps) * d_real}


def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('t_num', 'y1', 'y2', 't_opt', 'y1_opt', 'y2_opt'))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    r, g2 = inp['r_perp'], inp['g2']
    errors += ladder('eps', inp['eps_l'], inp['eps_m'], inp['eps_h'])
    errors += ladder('FY2028E range', inp['eps_fy28_lo'], inp['eps_m'], inp['eps_h'])
    if inp['consensus_n_fy28'] < MIN_CONSENSUS_HOUSES:
        errors.append('FY2028 consensus has too few houses')
    if abs(inp['tau'] - 1.25) > 1e-9:
        errors.append('tau must match 2026-09-30 to FY2028 opening')
    if inp['shares'] <= 0:
        errors.append('shares must be positive')
    if errors:
        raise ValueError('; '.join(errors))
    for t in TIERS:
        if unbooked(inp, t) <= 0:
            errors.append(f'{t}: unbooked EPS must be positive')
    errors += check_r(r, 'r_perp', 4)
    errors += check_g_cap(g2, r, 'g2', mega_hw=MEGA_HW)
    if r - g2 < MIN_SPREAD - 1e-12:
        errors.append('r minus growth is below the pole guard')
    if errors:
        raise ValueError('; '.join(errors))
    rho = {t: roe(inp, t) for t in TIERS}
    for t in TIERS:
        pay = payout(g2, rho[t])
        if not 0 < pay <= 1 + 1e-12:
            errors.append(f'{t}: payout outside (0,1]')
        if peak_domain(inp, t):
            if t != 'l':
                errors.append(f'{t}: forward return outside monotone domain')
            if g2 > 0 and inp['payout_fy25'] >= 1:
                errors.append('L retention branch but company retains nothing')
            continue
        errors += check_branch(g2, rho[t], r, inp['payout_fy25'], f'g2@{t}')
    if errors:
        raise ValueError('; '.join(errors))

    pe = {t: multiple(inp, t) for t in TIERS}
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append('anchor path touches a non-formula field')
    L, M, H = (anchor(inp, t) for t in TIERS)
    errors += ladder('anchors', L, M, H)
    eps_eff = tuple(inp[f'eps_{t}'] * disc(inp, t) for t in TIERS)
    flat_errors, flat = flat_multiple_ladder(eps_eff, pe['m'])
    errors += flat_errors + ladder('flat-multiple', *flat)
    l_out = pe['l'] < inp['pe_eq_lo']
    distorted = inp['g_exp_band'] - g2 >= DISTORTED_GAP
    bps_2q = inp['equity'] * 1e8 / inp['shares']
    coords = {'earnings_over_r': inp['eps_m'] / r * disc(inp, 'm'),
              'dividend_value': inp['payout_3y'] * inp['eps_m'] / (r - g2) * disc(inp, 'm'),
              'pb_5y_low': bps_2q * inp['pb_lo_5y'], 'pb_all_low': bps_2q * inp['pb_lo_all']}
    near = [k for k, v in coords.items() if abs(M / v - 1) <= RECONCILE_TOL]
    opt = battery_option(inp, op_anchor(inp, 'h'))
    if any(k.startswith('p_') for k in inp):
        errors.append('probability-style fields are not allowed in inputs')
    band3 = tuple(base + P_K[i] * opt['v_opt'] for i, base in enumerate((L, M, H)))
    if opt['v_opt'] > 0:
        errors += ladder('option-adjusted anchors', *band3)
    if errors:
        raise ValueError('; '.join(errors))

    as_band = lambda xs: dict(zip('LMH', xs))
    a, b = cut_points(L, M, H)
    ao, bo = cut_points(*band3)
    sensitivity = {}
    for label, dg in (('growth_minus_1pp', -.01), ('growth_plus_1pp', .01)):
        alt = {**inp, 'g2': g2 + dg}
        sensitivity[label] = as_band(anchor(alt, t) for t in TIERS)
    sensitivity['flat_multiple'] = as_band(flat)
    sensitivity['interest_over_ebit'] = (inp['int_9m26'] * 4 / 3) / inp['ebit_fy25']
    sensitivity['net_debt_over_ebitda'] = inp['net_debt'] / (inp['ebit_fy25'] + 2 * inp['da_1h26'])
    sensitivity['trailing_eps_over_r'] = inp['eps_ttm'] / r
    sensitivity['low_forecast_discounted'] = inp['eps_fy28_lo'] * pe['m'] * disc(inp, 'm')
    sensitivity['target_multiple'] = {name: inp[key] / (inp['eps_m'] * disc(inp, 'm')) for name, key in
                                      (('hsbc', 'tp_hsbc'), ('citi', 'tp_citi'), ('ubs', 'tp_ubs'), ('consensus', 'tp_consensus'))}
    # 外供电池是独立价值；L 冻结利润与峰形区倍数上限，M/H 取三段 Gordon。
    return {'ticker': '002594.SZ', 'currency': 'CNY',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-30', 'historical_framework_as_of': '2026-10-30',
            'anchors': as_band((L, M, H)), 'cut_points': {'A': a, 'B': b}, 'candidate': None,
            'option': {'label': 'external_battery_sales', 'value': opt['v_opt'], 'weights': as_band(P_K),
                       'anchors': as_band(band3), 'cut_points': {'A': ao, 'B': bo}, 'details': opt},
            'segments': {'company': {'values': as_band((L, M, H))}},
            'key_parameters': {'method': {'L': 'frozen_earnings_peak_multiple_cap', 'M': 'gordon_three_stage', 'H': 'gordon_three_stage'},
                               'discount_rate': dict.fromkeys('LMH', r), 'growth_rate': dict.fromkeys('LMH', g2),
                               'forward_return': as_band(rho[t] for t in TIERS),
                               'steady_return': as_band(min(rho[t], rs_tier(inp, t)) for t in TIERS),
                               'multiple': as_band(pe[t] for t in TIERS)},
            'operating': {'book_value_start': as_band(bps_open(inp, t) for t in TIERS),
                          'unbooked': as_band(unbooked(inp, t) for t in TIERS),
                          'window_growth': as_band(g_win(inp, t) for t in TIERS),
                          'window_retention': as_band(b_win(inp, t) for t in TIERS),
                          'window': as_band(window(inp, t) for t in TIERS),
                          'payout_gap': {t.upper(): payout_gap(g2, rho[t], inp['payout_fy25']) for t in TIERS},
                          'excess_retained': as_band((1 - inp['payout_fy25'] - b_win(inp, t)) * unbooked(inp, t) for t in TIERS),
                          'operating_anchor': as_band(op_anchor(inp, t) for t in TIERS),
                          'band_outside': l_out, 'band_distorted': distorted,
                          'reconciliation': coords, 'reconciliation_near': near},
            'sensitivity': sensitivity}


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'option_weights': P_K,
         'formula_fields': sorted(FORMULA_FIELDS), 'minimum_spread': MIN_SPREAD,
         'minimum_consensus_houses': MIN_CONSENSUS_HOUSES, 'monotone_gap': MONO_GAP,
         'distortion_gap': DISTORTED_GAP, 'reconcile_tolerance': RECONCILE_TOL,
         'mega_hardware': MEGA_HW, 'fiscal_year_now': FY_NOW}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    if result['option']['value'] > 0:
        result['option']['value_unit'] = 'CNY_PER_SHARE'
    else:
        result['option'] = {'status': 'unavailable', 'label': '电池外供', 'anchors': None}
        result['option_unavailable_reason'] = 'battery_increment_not_positive'
    result['review_flags'] = ['historical_growth_funding_gap_unverified',
                              'historical_external_battery_volume_and_overlap_unverified',
                              'historical_forecast_after_earnings_unverified']
    if result['operating']['band_outside'] and not result['operating']['band_distorted']:
        result['review_flags'].append('historical_low_multiple_below_clean_reference')
    if not result['operating']['reconciliation_near']:
        result['review_flags'].append('historical_reconciliation_requires_review')
    return result
