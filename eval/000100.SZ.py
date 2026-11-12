#!/usr/bin/env python3
"""000100.SZ (TCL科技) valuation eval — calculate anchors from the inputs below.

formula_id: tcl_sotp_fy27_econdep_roic_gordon_tail_v7

Four-leg SOTP, each leg at its own basket r, legs added (no blended r):

* display (TCL CSOT, attributable)  篮 5 value 11% borrowed via _AXIS.lcd-tv-panel
  (user ruling 2026-10-23; basket-6 13% kept as the axis review reference).
  Ruler = economic-depreciation Gordon + finite tail annuity (construction §5b,
  2026-10-05), the same ruler as 000725.SZ (user 2026-10-26):
    perpetual numerator = consensus attributable + (accounting D&A - economic D&A)
                          x (1 - t) x attributable share
    tail = (economic D&A - maintenance capex) x (1 - t) x share x annuity_factor(n)
    minus t8's unspent capital (named new line excluded from the entry test)
  Equipment life per tier comes from the axis (§2b), cross-checked here.
* PV / silicon (TCL Zhonghuan x 29.91%, inference)  篮 6 13%
* distribution (Highly, attributable)  篮 4 10%
* Bank of Shanghai 5.76% stake (equity-method income)  篮 5 11%

Mid-cycle numerator = FY2027 consensus (nearest qualifying forward year, A2);
FY2028 goes to H only.  Leverage gate read at FY2027 → every leg's retention
earns ROIC (g = (1 - payout) x ROIC, PE = payout / (r - g)); for display the ROIC
uses the economic-depreciation numerator.  Time alignment (valuation-rules
「经营价值与超额现金」③): display and PV values at the numerator year start
are discounted from the 2026-09-30 balance-sheet date (tau = 0.25 for FY2027,
1.25 for FY2028) and the Q4 window profit x payout is added back;
the tail (from 2027) is discounted tau = 0.25.  Distribution and the bank stake
are latest actuals (not aligned).  L replays the display segment's measured
2022-2025 profits on economic depreciation (today's assets, so conservative)
from FY2027, stays at the 2025 level with the M-tier multiple, plus the L tail.
V_opt = 0 (glass substrate / InP: no named quantity).

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here computes a zone or a market-implied r.

Run through eval.lib.valuation_runner with explicit code/content roots.
"""

from __future__ import annotations

import hashlib
import json
import io
import contextlib

from lib.gordon import (
    annuity_factor, capped_payout_pe, check_branch, check_g_cap, check_r, g_cap, perpetual_pe,
)
from lib.inputs import (
    check_missing, ladder, report, require_whole_years,
)
from lib.zones import cut_points

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones'), 'axes': {'panel': 'lcd_tv_panel'}}
# This identifies the frozen historical numerical inputs only; the runner
# separately records the source files and never treats this as confirmation.
HISTORICAL_INPUT_FINGERPRINT = 'de6d4c45760455cf270fe49a343681a05ec9e66c60910ab06437d05074b95eae'

INPUTS = {
    'shares': 2.1946416151e10,  # 三季报期末总股本（A1）; as-of 2026-09-30
    'bps': 3.09544466,  # 实际普通股权益 (689.3154669 − 永续债 9.9763) ÷ 219.46416151（A1）；只披露; as-of 2026-09-30
    'payout': 0.709,  # FY2023–25 实付（现金 + 回购）÷ 归母（A12）; as-of FY2025
    # Display rate and equipment lives are taken from the shared panel axis.
    'r_pv': 0.13,  # 篮 6 周期商品 13%：光伏腿盈利是硅片价函数（A8）; as-of 2026-10-04
    'r_dist': 0.10,  # 篮 4 常规经营 10%：薄利分销，非商品价函数（A8）; as-of 2026-10-04
    'r_shb': 0.11,  # 篮 5 大行 / 优质股份行 11%：上海银行股权（银行，A5 / A8）; as-of 2026-10-04
    'ni26_m': 70.77486,  # 东方财富 F10 近六月 10 家归母预测均值；直接取净利润，不用平均 EPS 反推（S3）; as-of 2026-11-05
    'ni27_m': 103.72008,  # 同源 10 家 FY2027E 均值 = **M 分子**（A2；S3）; as-of 2026-11-05
    'ni28_m': 134.25614,  # 同源 10 家 FY2028E 均值 = **H 分子**（A2；S3）; as-of 2026-11-05
    'ni27_h': 111.57,  # F10 可见 7 家明细最大值（华创）；非 10 家完整上沿，仅同年对照; as-of 2026-11-05
    'ni28_h': 139.84,  # 可见 7 家明细最大值（东方）；非完整上沿，仅披露; as-of 2026-11-05
    'ni27_lo': 96.21,  # 可见 7 家明细最小值（长江）；非完整下沿，仅披露; as-of 2026-11-05
    'ni28_lo': 127.7363,  # 可见 7 家明细最小值（财通）；非完整下沿，仅披露; as-of 2026-11-05
    'zh26_m': -52.608,  # 东方财富 F10 近六月 5 家中环归母均值（A3；S4）; as-of 2026-11-05
    'zh27_m': 20.49,  # 同源 5 家 FY2027E 中环均值（M）; as-of 2026-11-05
    'zh28_m': 42.296,  # 同源 5 家 FY2028E 中环均值（H）; as-of 2026-11-05
    'zh27_h': 23.86,  # 可见 3 家明细最大值（国金 11-02）；非 5 家完整上沿，仅对照; as-of 2026-11-05
    'zh28_h': 44.82,  # 可见 3 家明细最大值（长江）；非完整上沿，仅披露; as-of 2026-11-05
    'zh_share': 0.2991,  # TCL 对中环持股（A3）; as-of 2026-06-30
    'zh_roe27_m': 0.10096,  # 中环 2027E ROE 共识（东方财富 5 家）；只披露; as-of 2026-11-05
    'zh_roe28_m': 0.1728,  # 中环 2028E ROE 共识（东方财富 5 家）；只披露; as-of 2026-11-05
    'disp_share': 0.8414,  # 显示腿归母分享比例（A11）; as-of 2026-06-30
    'disp_na': 765.56,  # 半导体显示分部资产 1,940.06 − 分部负债 1,174.50; as-of 2026-06-30
    'disp_assets': 1940.06,  # 半导体显示分部资产；ROIC 粗读分母（A9）; as-of 2026-06-30
    'pv_assets': 1127.63,  # 新能源光伏及其他硅材料分部资产；光伏腿 ROIC 粗读分母（A9）; as-of 2026-06-30
    'disp_att_h1': 32.84,  # 中报华星归母贡献；只用于从中报分部净资产滚动至 FY2027 年初; as-of 2026-06-30
    'disp_att_ytd': 50.4,  # 三季报前三季度华星归母贡献（S1 第7页）；第四季度窗口扣除; as-of 2026-09-30
    'pv_att_ytd': -13.626996,  # 中环前三季归母 −45.56 × 持股 29.91%；推断，非母公司直接披露（S6）; as-of 2026-09-30
    'da_window26': 55.615,  # Q4 显示会计折旧代理 = 中报半年 111.23 ÷ 2；非 Q4 实际值（A15）; as-of 2026-06-30
    'window26_years': 0.25,  # 2026-09-30 至年末，经济折旧只扣四分之一全年; as-of 2026-09-30
    'seg_ni_2022': -76.25,  # 半导体显示分部净利 FY2022（L 路径第 1 年；2022 年报分部附注）; as-of FY2022
    'seg_ni_2023': -0.07,  # FY2023（2024 年报上年对比）; as-of FY2023
    'seg_ni_2024': 62.28,  # FY2024; as-of FY2024
    'seg_ni_2025': 87.13,  # FY2025（L 停留水平；2025 年报）; as-of FY2025
    'seg_da_2022': 155.15,  # 半导体显示分部折旧摊销 FY2022（2022 年报分部附注）; as-of FY2022
    'seg_da_2023': 185.18,  # FY2023（2024 年报上年对比；= 合并 255.89 − 中环 67.57 − 分销 0.64 − 其他 2.50 交叉吻合）; as-of FY2023
    'seg_da_2024': 222.57,  # FY2024; as-of FY2024
    'seg_da_2025': 241.29,  # FY2025（峰值；A14 进入条件分母）; as-of FY2025
    'da_2025': 241.29,  # 同 `seg_da_2025`，进入条件分母（A14）; as-of FY2025
    'da_2026h1': 111.23,  # H1显示分部折旧摊销，仅进入条件分母；Q4代理另见da_window26; as-of 2026-06-30
    'da_27': 168.5,  # FY2027E 显示分部会计折旧摊销 = 开源主设备 118（2026-08-18 表 9，含 t8 新增 28）+ 非主设备 50.5（2026H1 年化 222.46 − 开源 2026 主设备 172）（A15，待核）; as-of 2026-08-18
    'da_28': 168.5,  # FY2028E 同法（开源主设备 2028 年仍 118）（A15，待核）; as-of 2026-08-18
    'tax': 0.15,  # 所得税率（高新技术企业，2025 年报税项附注）; as-of FY2025
    'gross_equip': 2134.6,  # 显示业务机器设备原值 = TCL 合并 2,803.80 − 中环 669.18（2025 年报附注五·20；中环 2025 年报）（A15）; as-of 2025-12-31
    'd_bldg_other': 16.6,  # 房屋原值 515.9 ÷ 40 年 = 12.9 + 其他固定资产约 3.7（A15）; as-of 2025-12-31
    'da_nonfa': 49.9,  # 无形资产摊销 26.9 + 长期待摊摊销 21.6 + 使用权资产折旧 1.4（2025 年 TCL 合并减中环，现金流量表补充资料；按账面计入经济折旧）; as-of FY2025
    't8_budget': 295,  # t8 总投资（2026H1 在建工程附注预算 295.0 亿）; as-of 2026-06-30
    't8_eq_frac': 0.70,  # t8 总投资中设备占比（推断，待核；FY2027 会计折旧含 t8 新增 28 亿 ≈ 295 × 70% × 95% ÷ 7，同口径计入经济折旧）; as-of 2026-10-26
    't8_progress': 0.10,  # t8 工程累计投入占预算比例（2026H1 在建工程附注）; as-of 2026-06-30
    't8_share': 0.60,  # 华星占 t8 项目公司（注册资本 147.5 亿中华星 88.5 亿；TCL 科技公告 2025-09-12）；扣减再 × `disp_share`; as-of 2025-09-12
    'unspent_years': 1.25,  # 2026-09-30 至 2027 年末；保留期末支付近似，纠正旧年数与日期不符; as-of 2026-09-30
    'maint_l': 114.7,  # L 档维护开支 = 2026H1 显示分部资本开支 72.98 − t8 15.10 − t9 0.53（在建工程本期增加），年化（A16）; as-of 2026-06-30
    'maint_m': 99.4,  # M 档 = FY2025 与 2026H1 年化均值（A16）; as-of 2026-06-30
    'maint_h': 84.1,  # H 档 = FY2025 显示分部资本开支 99.19 − t9 15.12（A16）; as-of FY2025
    'capex_ex_2025': 84.1,  # FY2025 扣具名新线后资本开支（A14 进入条件）; as-of FY2025
    'capex_ex_2026h1': 57.35,  # 2026H1 扣具名新线后资本开支（A14 进入条件）; as-of 2026-06-30
    'cohort_year': 2013.97,  # 已提完折旧老线按投资额加权平均投产年：t1 2011.6 / 245、t2 2015.3 / 244、t3 2016.7 / 160、t10 2011 / 62.4、t11 2014 / 250.5（A15）; as-of 2026-10-26
    'tail_start': 2027,  # 尾巴首年（同 `000725.SZ`；维护开支已扣 t8，尾巴不等 t8 收尾）; as-of 2026-10-26
    'tau': 0.25,  # 时点对齐：估值基准日 2026-09-30 → FY2027 年初（A7）; as-of 2026-09-30
    'ni_dist': 0.98,  # 分销归母最近四季（A4）; as-of 2026-06-30
    'ni_dist_l': 0.14,  # 分销归母 FY2023（A4）; as-of FY2023
    'roe_dist': 0.0935,  # 分销分部 ROE FY2025（A4）；ROE 侧披露; as-of FY2025
    'roic_dist': 0.0196,  # 分销分部净利 1.60 ÷ 分部资产 81.69（A4 / A9）; as-of FY2025
    'ni_shb': 13.46,  # 上海银行权益法投资收益（A5）; as-of FY2025
    'roe_shb': 0.0924,  # 上海银行股权 ROE（A5）; as-of FY2025
    'payout_shb': 0.316,  # 上海银行派息率（收到股利 ÷ 投资收益，A5）; as-of FY2025
    'op27_m': 108.97197,  # 东方财富 10 家 FY2027E 报表营业利润均值；严格 EBIT 代理，与加回利息口径并列（A9）; as-of 2026-11-05
    'op28_m': 151.23607,  # 同源 FY2028E 报表营业利润均值；并列披露; as-of 2026-11-05
    'interest_ann': 41.53307397,  # 前三季财务利息费用 31.13076259 + 营业成本内利息支出 0.01904289，× 4/3（S1 第17页）; as-of 2026-09-30
    'net_debt': 1209.42056635,  # 基本净债 1147.6223 + 租赁 51.6505 + 永续债 9.9763 + 向央行借款 0.1715；未核实其他类债（A9）; as-of 2026-09-30
    'da_ann': 318.78,  # 折旧摊销 2026H1 159.39 × 2（A9）; as-of 2026-06-30
    'v_opt': 0,  # 玻璃基板 / InP 期权上限锚未闭合、待补（A6）; as-of 2026-10-04
    'm_prev': 3.176269,  # 上一正式版本M未取整值（v6，中报时点），本次事件对账; as-of 2026-10-26
    'release_years': 5,  # 资金用途研究区间的条件窗口FY2027–31；非公司指引、无终值释放，不进正式锚点; as-of 2026-11-05
}
BASKETS = {'r_display': 5, 'r_pv': 6, 'r_dist': 4, 'r_shb': 5}
FORMULA_ID = "tcl_sotp_fy27_econdep_roic_gordon_tail_v7"
R_LEGS = ("r_display", "r_pv", "r_dist", "r_shb")
SEG_YEARS = (2022, 2023, 2024, 2025)
REQUIRED = [
    "shares", "bps", "payout", *R_LEGS, "r_display_ref",
    "ni26_m", "ni27_m", "ni28_m", "ni27_h", "ni28_h", "ni27_lo", "ni28_lo",
    "zh26_m", "zh27_m", "zh28_m", "zh27_h", "zh28_h", "zh_share", "zh_roe27_m", "zh_roe28_m",
    "disp_share", "disp_na", "disp_assets", "pv_assets", "disp_att_ytd", "pv_att_ytd", "disp_att_h1",
    "da_window26", "window26_years",
    *(f"seg_ni_{y}" for y in SEG_YEARS), *(f"seg_da_{y}" for y in SEG_YEARS),
    "tax", "da_27", "da_28", "da_2026h1", "gross_equip", "d_bldg_other", "da_nonfa",
    "t8_budget", "t8_eq_frac", "t8_progress", "t8_share", "unspent_years",
    "life_l", "life_m", "life_h", "maint_l", "maint_m", "maint_h",
    "cohort_year", "tail_start", "tau", "capex_ex_2025", "da_2025", "capex_ex_2026h1",
    "ni_dist", "ni_dist_l", "roe_dist", "roic_dist", "ni_shb", "roe_shb", "payout_shb",
    "op27_m", "op28_m", "interest_ann", "net_debt", "da_ann", "v_opt", "m_prev", "release_years",
]
YI = 1e8
TIERS = ("l", "m", "h")


def retention_pe(ret: float, r: float, po: float, dg: float = 0.0) -> tuple[float, float]:
    """(PE, g) with retention earning `ret` (ROIC after the leverage gate): g = (1 - payout) x ret (+dg)."""
    g = min((1 - po) * ret + dg, g_cap(r))
    return perpetual_pe(g, ret, r), g


def econ_d(i: dict[str, float], t: str) -> float:
    """Economic D&A (亿): equipment incl. t8's equipment share / axis life + buildings & other + non-FA amortisation."""
    eq = i["gross_equip"] + i["t8_budget"] * i["t8_eq_frac"]
    return eq / i[f"life_{t}"] + i["d_bldg_other"] + i["da_nonfa"]


def tail_years(i: dict[str, float], t: str) -> int:
    return max(0, round(i["cohort_year"] + i[f"life_{t}"] - (i["tail_start"] - 1)))


def deck(i: dict[str, float], dg: float = 0.0, flat_pe: float | None = None) -> dict[str, dict]:
    sh = i["shares"] / YI
    po, tx, sd, zs = i["payout"], i["tax"], i["disp_share"], i["zh_share"]
    r6, r_pv, r4, r5 = i["r_display"], i["r_pv"], i["r_dist"], i["r_shb"]
    tau = i["tau"]
    k = (1 - tx) * sd   # pre-tax D&A → attributable after tax

    def disp_att(year: int, t: str) -> float:  # 亿, attributable, book (consensus remainder)
        return i[f"ni{year}_{t}"] - i[f"zh{year}_{t}"] * zs - i["ni_shb"] - i["ni_dist"]

    pe_d, g_d = retention_pe(i["roic_dist"], r4, po, dg)
    g_shb_raw = (1 - i["payout_shb"]) * i["roe_shb"]
    pe_s = capped_payout_pe(g_shb_raw, i["roe_shb"], r5, i["payout_shb"])
    v_shb, v_dist = i["ni_shb"] * pe_s, i["ni_dist"] * pe_d
    ded = i["t8_budget"] * (1 - i["t8_progress"]) * i["t8_share"] * sd / (1 + r6) ** i["unspent_years"] / sh
    out: dict[str, dict] = {"dist": dict(pe=pe_d, g=g_d, v=v_dist),
                            "shb": dict(pe=pe_s, g_raw=g_shb_raw, v=v_shb), "ded": ded}

    def tail(t: str) -> tuple[float, float, int]:
        per = (econ_d(i, t) - i[f"maint_{t}"]) * k / sh
        n = tail_years(i, t)
        return per * annuity_factor(0.0, r6, n), per, n

    def window26(t: str) -> float:  # Q4 display attributable profit on the economic ruler (亿)
        a = disp_att(26, "m") - i["disp_att_ytd"] + (i["da_window26"] - econ_d(i, t) * i["window26_years"]) * k
        return a * po

    def pv_leg(zh: float) -> tuple[float, float, float]:
        roic = zh / i["pv_assets"]
        pe, g = retention_pe(roic, r_pv, po, dg)
        return pe, g, roic

    def tier(year: int, t: str, life_t: str) -> dict:
        """Display + PV at numerator year `year` (consensus column t), economic ruler of tier life_t."""
        ed = econ_d(i, life_t)
        yy = year - 2000
        att = disp_att(yy, t) + (i[f"da_{yy}"] - ed) * k
        roic = att / sd / i["disp_assets"]
        pe, g = retention_pe(roic, r6, po, dg)
        if flat_pe is not None:
            pe = flat_pe
        tl, per, n = tail(life_t)
        yrs = tau + (year - 2027)          # balance-sheet date → numerator year start
        w = window26(life_t) / sh * (1 + r6) ** (-tau / 2)
        if year == 2028:                    # FY2027 sits inside the window
            a27 = disp_att(27, "m") + (i["da_27"] - ed) * k
            w += a27 * po / sh * (1 + r6) ** -(tau + 0.5)
        v_perp = att * pe / sh
        v_disp = v_perp * (1 + r6) ** -yrs + tl * (1 + r6) ** -tau + w - ded
        zh = i[f"zh{yy}_{t}"]
        pe_pv, g_pv, roic_pv = pv_leg(zh)
        w_pv = max(0.0, (i["zh26_m"] * zs - i["pv_att_ytd"]) * po) / sh * (1 + r_pv) ** (-tau / 2)
        if year == 2028:
            w_pv += max(0.0, i["zh27_m"] * zs * po) / sh * (1 + r_pv) ** -(tau + 0.5)
        v_pv = zh * zs * pe_pv / sh * (1 + r_pv) ** -yrs + w_pv
        return dict(ed=ed, att=att, roic=roic, g=g, pe=pe, perp=v_perp, tail=tl, per=per, n=n, w=w,
                    disp=v_disp, pv_att=zh * zs, pe_pv=pe_pv, g_pv=g_pv, roic_pv=roic_pv, pv=v_pv,
                    a=v_disp + v_pv + (v_dist + v_shb) / sh)

    out["m"] = tier(2027, "m", "m")
    out["h"] = tier(2028, "m", "h")
    out["h27hi"] = tier(2027, "h", "h")   # same-year (FY2027) counterpart of H
    out["h28hi"] = tier(2028, "h", "h")
    # ROE-side domain (disclosure): economic-ruler display ROE on segment net assets rolled to the year start
    # Segment equity is only available at H1; bridge all H2 profit, not just Q4.
    a26 = disp_att(26, "m") - i["disp_att_h1"]
    na27 = i["disp_na"] + (1 - po) * a26 / sd
    out["m"]["roe"] = (out["m"]["att"] / sd) / na27
    out["h"]["roe"] = (out["h"]["att"] / sd) / (na27 + (1 - po) * out["m"]["att"] / sd)
    # L: measured segment path on the economic ruler (today's assets), from FY2027, stays at 2025
    ed_l = econ_d(i, "l")
    e = [(i[f"seg_ni_{y}"] + (i[f"seg_da_{y}"] - ed_l) * (1 - tx)) * sd for y in SEG_YEARS]
    pe_tail = out["m"]["pe"] if flat_pe is None else flat_pe
    tl, per, n = tail("l")
    v_disp_l = (sum(x / (1 + r6) ** (j + 1) for j, x in enumerate(e[:3])) + e[3] * pe_tail / (1 + r6) ** 3) / sh
    v_dist_l = i["ni_dist_l"] * pe_d
    out["l"] = dict(ed=ed_l, e=e, tail=tl, per=per, n=n, perp=v_disp_l, disp=v_disp_l + tl - ded,
                    a=v_disp_l + tl - ded + (v_dist_l + v_shb) / sh)
    return out


def book_m_h(i: dict[str, float]) -> tuple[float, float]:
    """Old ruler cross (v5 book Gordon, no tail, no t8 deduction, no time alignment) — disclosure."""
    sh, po, zs, sd = i["shares"] / YI, i["payout"], i["zh_share"], i["disp_share"]
    vals = []
    for year, f in ((27, 1.0), (28, 1 + i["r_display"])):
        att = i[f"ni{year}_m"] - i[f"zh{year}_m"] * zs - i["ni_shb"] - i["ni_dist"]
        pe, _ = retention_pe(att / sd / i["disp_assets"], i["r_display"], po)
        zh = i[f"zh{year}_m"]
        pe_pv, _ = retention_pe(zh / i["pv_assets"], i["r_pv"], po)
        fpv = 1.0 if year == 27 else 1 + i["r_pv"]
        pe_d, _ = retention_pe(i["roic_dist"], i["r_dist"], po)
        pe_s = capped_payout_pe((1 - i["payout_shb"]) * i["roe_shb"], i["roe_shb"], i["r_shb"], i["payout_shb"])
        vals.append((att * pe / f + zh * zs * pe_pv / fpv + i["ni_dist"] * pe_d + i["ni_shb"] * pe_s) / sh)
    return vals[0], vals[1]


def validate_and_print(inp: dict[str, float]) -> int:
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = BASKETS
    for leg in R_LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[leg], leg, baskets.get(leg))

    # Keep the stricter operating-profit proxy at the boundary; disclose the add-back case.
    int_ebit27 = inp["interest_ann"] / inp["op27_m"]
    nd_ebitda27 = inp["net_debt"] / (inp["op27_m"] + inp["da_ann"])
    if not (int_ebit27 > 1 / 3 or nd_ebitda27 > 3):
        errors.append("leverage gate no longer triggered at FY2027 — the ROIC retention branch (A9) must be revisited")

    # §5b entry test: capex ex named new lines / D&A < 0.6 for two periods
    e25 = inp["capex_ex_2025"] / inp["da_2025"]
    e26 = inp["capex_ex_2026h1"] / inp["da_2026h1"]
    if not (e25 < 0.6 and e26 < 0.6):
        errors.append(f"§5b entry test failed: FY2025 {e25:.2f}, 2026H1 {e26:.2f} — economic-depreciation ruler not allowed")
    if inp["da_27"] > inp["da_2025"]:
        errors.append("FY2027 accounting D&A above the FY2025 peak — §5b trigger (A14)")

    d = deck(inp)
    L, M, H = (d[t]["a"] for t in TIERS)
    A, B = cut_points(L, M, H)
    po = inp["payout"]
    errors += ladder("NI27", inp["ni27_lo"], inp["ni27_m"], inp["ni27_h"])
    errors += ladder("NI28", inp["ni28_lo"], inp["ni28_m"], inp["ni28_h"])
    errors += ladder("anchors", L, M, H)
    for t in TIERS:
        x = d[t]
        if x["ed"] <= inp[f"maint_{t}"]:
            errors.append(f"{t.upper()}: economic D&A {x['ed']:.1f} not above maintenance {inp[f'maint_{t}']}")
    for t in ("m", "h"):
        x = d[t]
        errors += check_g_cap(x["g"], inp["r_display"], f"display g_{t}")
        errors += check_g_cap(x["g_pv"], inp["r_pv"], f"pv g_{t}")
        errors += check_branch(x["g"], x["roic"], inp["r_display"], po, f"display {t.upper()}")
        errors += check_branch(x["g_pv"], x["roic_pv"], inp["r_pv"], po, f"pv {t.upper()}")
    errors += check_g_cap(d["dist"]["g"], inp["r_dist"], "dist g")
    errors += check_branch(d["dist"]["g"], inp["roic_dist"], inp["r_dist"], po, "dist")
    # tail must not leak into the perpetual: maintenance changes leave the perpetual untouched
    alt = deck({**inp, "maint_m": inp["maint_m"] * 0.5})
    if abs(alt["m"]["perp"] - d["m"]["perp"]) > 1e-12:
        errors.append("perpetual segment moved with maintenance capex — tail leaked into the perpetual")
    flat = deck(inp, flat_pe=d["m"]["pe"])
    errors += ladder("flat-multiple anchors", *(flat[t]["a"] for t in TIERS))
    if inp["v_opt"] != 0:
        errors.append("V_opt must stay 0 (A6) until a named quantity exists")

    sh = inp["shares"] / YI
    print(f"formula_id={FORMULA_ID}")
    print(f"leverage gate @FY2027: interest/EBIT {int_ebit27:.1%} net debt/EBITDA {nd_ebitda27:.2f} → triggered; "
          f"@FY2028 {inp['interest_ann'] / inp['op28_m']:.1%} / {inp['net_debt'] / (inp['op28_m'] + inp['da_ann']):.2f}")
    print(f"leverage add-back case: interest/(OP+interest) "
          f"{inp['interest_ann'] / (inp['op27_m'] + inp['interest_ann']):.1%}; "
          f"net debt/(OP+interest+D&A) {inp['net_debt'] / (inp['op27_m'] + inp['interest_ann'] + inp['da_ann']):.2f}; "
          "proxy choice flips gate; retain triggered case")
    print(f"§5b entry ratios (ex t8 / t9): FY2025 {e25:.2f}, 2026H1 {e26:.2f}; t8 unspent deduction {d['ded']:.3f}/股")
    for t, lab in (("m", "M FY2027 mean"), ("h", "H FY2028 mean")):
        x = d[t]
        print(f"{lab}: econ D {x['ed']:.1f}亿 (life {inp[f'life_{t}']}) → display att {x['att']:.2f}亿 ROIC {x['roic']:.2%} "
              f"(ROE {x['roe']:.2%}) g {x['g']:.2%} PE {x['pe']:.2f} perp {x['perp']:.3f}/股 | tail "
              f"({x['ed']:.1f} - {inp[f'maint_{t}']}) → {x['per']:.3f}/yr x AF(n={x['n']}) = {x['tail']:.3f} | "
              f"window {x['w']:.3f} → display {x['disp']:.3f}/股")
        print(f"   PV att {x['pv_att']:.2f}亿 ROIC {x['roic_pv']:.2%} g {x['g_pv']:.2%} PE {x['pe_pv']:.2f} → {x['pv']:.3f}/股")
    x = d["l"]
    print(f"L: econ D {x['ed']:.1f}亿 path {', '.join(f'{v:.1f}' for v in x['e'])}亿 (stay at last, PE {d['m']['pe']:.2f}) "
          f"→ {x['perp']:.3f}/股; tail {x['per']:.3f} x AF(n={x['n']}) = {x['tail']:.3f}; display {x['disp']:.3f}/股")
    x = d["dist"]
    print(f"dist: {inp['ni_dist']:.2f}亿 ROIC {inp['roic_dist']:.2%} g {x['g']:.2%} PE {x['pe']:.2f} → {x['v'] / sh:.2f}/股")
    x = d["shb"]
    print(f"SHB: {inp['ni_shb']:.2f}亿 ROE {inp['roe_shb']:.2%} payout {inp['payout_shb']:.1%} g raw {x['g_raw']:.2%} "
          f"> cap {g_cap(inp['r_shb']):.0%} → PE {x['pe']:.2f} → {x['v'] / sh:.2f}/股")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} width={(H - L) / (2 * M):.2f} V_opt/M=0")
    print(f"flat (all PE {d['m']['pe']:.2f}): " + " / ".join(f"{flat[t]['a']:.2f}" for t in TIERS))
    print(f"same-year (FY2027) H' = visible-detail maxima, H ruler = {d['h27hi']['a']:.2f}; "
          f"FY2028 visible maxima = {d['h28hi']['a']:.2f} (not full-sample bounds; disclosure)")
    # Conditional cash-use research only: unchanged earnings/growth, no terminal release.
    # This is retained economic earnings, not the depreciation tail or the t8 budget.
    retained_per_share = d["m"]["att"] * (1 - po) / sh
    release_pv = retained_per_share * annuity_factor(0, inp["r_display"], int(inp["release_years"]))
    release_pv *= (1 + inp["r_display"]) ** -inp["tau"]
    print("cash-use conditional M (release fraction 0/25/50/75/100%, 2027-2031 only): "
          + " / ".join(f"{M + fraction * release_pv:.2f}" for fraction in (0, 0.25, 0.5, 0.75, 1)))
    for dg in (-0.01, 0.01):
        s = deck(inp, dg)
        print(f"g ±1pp {dg:+.0%}: L {s['l']['a']:.2f} M {s['m']['a']:.2f} H {s['h']['a']:.2f}")
    sens = {
        "FY2027/28 D&A 152.6 (non-main at FY2024)": {"da_27": 152.6, "da_28": 152.6},
        "FY2027/28 D&A 187.3 (non-main at FY2025)": {"da_27": 187.3, "da_28": 187.3},
        "maintenance 60/40/25 (management wording)": {"maint_l": 60, "maint_m": 40, "maint_h": 25},
        "life all 17.5": {"life_l": 17.5, "life_h": 17.5},
        "tail years -2": {"cohort_year": inp["cohort_year"] - 2},
        "no time alignment": {"tau": 0.0},
        "t8 30% spent": {"t8_progress": 0.30},
        "no t8 deduction": {"t8_progress": 1.0},
    }
    for lab, ov in sens.items():
        s = deck({**inp, **ov})
        print(f"sens {lab}: L {s['l']['a']:.2f} M {s['m']['a']:.2f} H {s['h']['a']:.2f}")
    ref = deck({**inp, "r_display": inp["r_display_ref"]})
    print(f"axis review base: same ruler at display r {inp['r_display_ref']:.0%} → L {ref['l']['a']:.2f} "
          f"M {ref['m']['a']:.2f} H {ref['h']['a']:.2f} (_AXIS.lcd-tv-panel §2 trigger)")
    bm, bh = book_m_h(inp)
    m = d["m"]
    eps27 = inp["ni27_m"] / sh
    e_over_r = (m["att"] / inp["r_display"] + m["pv_att"] / inp["r_pv"] + inp["ni_dist"] / inp["r_dist"]
                + inp["ni_shb"] / inp["r_shb"]) / sh - d["ded"]
    print(f"cross: book Gordon (v5 ruler) M {bm:.2f} H {bh:.2f}; E_M/r (econ, legwise, less t8) {e_over_r:.2f} "
          f"({M / e_over_r - 1:+.1%}); M vs previous {inp['m_prev']} = {M / inp['m_prev'] - 1:+.1%}; "
          f"company PE at M on FY2027E {M / eps27:.2f}x")
    return report(errors)



def evaluate(inp: dict[str, float]) -> dict:
    # These are calendar years/counts; tau, project discount time and 17.5-year
    # equipment life are continuous durations and remain fractional.
    require_whole_years(inp, ('release_years', 'tail_start'))
    if inp['release_years'] <= 0:
        raise ValueError('release_years must be positive')
    # Preserve all original model checks and keep their diagnostic messages.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as diagnostic:
        status = validate_and_print(inp)
    if status:
        raise ValueError(diagnostic.getvalue().strip())
    result = deck(inp)
    band = lambda d: {t.upper(): d[t]["a"] for t in TIERS}
    anchors = band(result)
    a, b = cut_points(*anchors.values())
    flat = deck(inp, flat_pe=result["m"]["pe"])
    reference = deck({**inp, "r_display": inp["r_display_ref"]})
    overrides = {
        "accounting_da_152_6": {"da_27": 152.6, "da_28": 152.6},
        "accounting_da_187_3": {"da_27": 187.3, "da_28": 187.3},
        "maintenance": {"maint_l": 60, "maint_m": 40, "maint_h": 25},
        "life_17_5": {"life_l": 17.5, "life_h": 17.5},
        "tail_minus_2": {"cohort_year": inp["cohort_year"] - 2},
        "no_alignment": {"tau": 0.0},
        "t8_30_percent_spent": {"t8_progress": 0.30},
        "no_t8_deduction": {"t8_progress": 1.0},
    }
    sensitivity = {name: band(deck({**inp, **value})) for name, value in overrides.items()}
    sensitivity.update({"growth_minus_1pp": band(deck(inp, -0.01)),
                        "growth_plus_1pp": band(deck(inp, 0.01)),
                        "basket_6": band(reference), "flat_pe": band(flat)})
    retained = result["m"]["att"] * (1 - inp["payout"]) / (inp["shares"] / YI)
    release = retained * annuity_factor(0, inp["r_display"], int(inp["release_years"]))
    release *= (1 + inp["r_display"]) ** -inp["tau"]
    sensitivity["cash_use_conditional_m"] = {str(f): anchors["M"] + f * release
                                              for f in (0, .25, .5, .75, 1)}
    # INPUTS is editable in this file; comparing it with itself cannot establish
    # that the original research still applies after an edit. Retain the old
    # dates as provenance and leave the current dates unknown until reviewed.
    sh = inp['shares'] / YI
    distribution = {'L': inp['ni_dist_l'] * result['dist']['pe'] / sh,
                    'M': result['dist']['v'] / sh, 'H': result['dist']['v'] / sh}
    bank = {tier: result['shb']['v'] / sh for tier in 'LMH'}
    ratio = lambda values: {'unit': 'RATIO', 'values': values}
    three = lambda value: dict.fromkeys('LMH', value)
    segments = {
        'display': {'label': '显示', 'unit': 'CNY_PER_SHARE',
                    'values': {t.upper(): result[t]['disp'] for t in TIERS}},
        'solar': {'label': '光伏及硅材料', 'unit': 'CNY_PER_SHARE',
                  'values': {'L': 0.0, 'M': result['m']['pv'], 'H': result['h']['pv']}},
        'distribution': {'label': '分销', 'unit': 'CNY_PER_SHARE', 'values': distribution},
        'bank': {'label': '上海银行股权', 'unit': 'CNY_PER_SHARE', 'values': bank},
    }
    parameters = {
        'display': {'discount_rate': ratio(three(inp['r_display'])),
                    'growth_rate': ratio({'L': result['m']['g'], 'M': result['m']['g'], 'H': result['h']['g']}),
                    'steady_return': ratio({'L': result['m']['roic'], 'M': result['m']['roic'], 'H': result['h']['roic']}),
                    'roe_forward': ratio({'L': None, 'M': result['m']['roe'], 'H': result['h']['roe']})},
        'solar': {'discount_rate': ratio(three(inp['r_pv'])),
                  'growth_rate': ratio({'L': None, 'M': result['m']['g_pv'], 'H': result['h']['g_pv']}),
                  'steady_return': ratio({'L': None, 'M': result['m']['roic_pv'], 'H': result['h']['roic_pv']})},
        'distribution': {'discount_rate': ratio(three(inp['r_dist'])),
                         'growth_rate': ratio(three(result['dist']['g'])),
                         'steady_return': ratio(three(inp['roic_dist']))},
        'bank': {'discount_rate': ratio(three(inp['r_shb'])),
                 'growth_rate': ratio(three(min(result['shb']['g_raw'], g_cap(inp['r_shb'])))),
                 'roe_forward': ratio(three(inp['roe_shb']))},
    }
    fingerprint_inputs = dict(inp)
    for key in ('life_l', 'life_m', 'life_h'):
        fingerprint_inputs[key] = float(fingerprint_inputs[key])
    fingerprint = hashlib.sha256(json.dumps(fingerprint_inputs, sort_keys=True, separators=(',', ':'),
                                            allow_nan=False).encode()).hexdigest()
    return {"ticker": "000100.SZ", "currency": "CNY",
            "valuation_as_of": None, "framework_as_of": None,
            "historical_financial_statement_as_of": "2026-09-30",
            "historical_research_as_of": "2026-11-05",
            "basis_changed": None, "partial_basis_changed": fingerprint != HISTORICAL_INPUT_FINGERPRINT,
            "units": {"price": "CNY_PER_SHARE"}, "anchors": anchors, "cut_points": {"A": a, "B": b},
            "candidate": None, "option": None,
            "segments": segments, "operating": result, "sensitivity": sensitivity,
            "key_parameters": parameters,
            "historical_book_m_h": book_m_h(inp)}


def calculate(context: dict) -> dict:
    panel = context['axes']['panel']
    fields = panel['stock_fields']
    required = {'r_display', 'r_display_ref', 'life_l', 'life_m', 'life_h'}
    if panel['scope'] != 'display' or set(fields) != required or required & INPUTS.keys():
        raise ValueError('panel axis scope or shared inputs are invalid')
    return evaluate({**INPUTS, **fields})
