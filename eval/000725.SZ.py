from __future__ import annotations

import json
import hashlib
import math

from lib.gordon import (
    annuity_factor, capped_payout_pe, check_branch, check_g_cap, check_r, g_cap, perpetual_pe,
    recovery_two_stage_pe,
)
from lib.inputs import (
    check_missing, ladder,
)
from lib.zones import cut_points
from lib.glass_ruler_rules import check_glass_ruler

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'glass_ruler_rules'),
                'axes': {'panel': 'lcd_tv_panel', 'glass': 'glass_core_substrate'}}
# Partial numerical-input comparison only: source identity, current validity,
# and the user's actual confirmation are owned by the runner and review store.
HISTORICAL_INPUT_FINGERPRINT = '7bda3f3e9bbd1f4746a08e57eecbfe5ae73b96c98f43ffe7b7eacdca4a18bd30'

INPUTS = {
    'shares': 37044328064.0,  # 总股本；Q1 三季报，数值与中报相同；2026-09-30
    'bps': 3.594,  # 归母权益 1,331.36 亿 ÷ 370.44 亿股；2026H1 半年报；2026-06-30
    'ni_2026h1': 5248000000.0,  # 2026H1 归母（已入账，BPS 滚动时扣除）；2026-06-30
    'ni_ttm': 5506815563.0,  # 约数：FY2025 58.57 亿 − 2025年前三季 46.01497094 亿 + 2026年前三季 42.51312657 亿；Q1，只作对账门读数；2026-09-30
    'ni26_m': 8427000000.0,  # 2026E 共识均值（东方财富 17 家），BPS 滚动用；**共识待更新，未取得财报后可核验样本**；2026-09-09
    'ni26_h': 9716000000.0,  # 2026E 共识上沿（国盛），BPS 滚动用；**共识待更新，未取得财报后可核验样本**；2026-09-09
    'ni27_m': 11892000000.0,  # 2027E 共识均值（B2）；**共识待更新，未取得财报后可核验样本**；2026-09-09
    'ni27_h': 13833000000.0,  # 2027E 共识上沿（国海，B2）；**共识待更新，未取得财报后可核验样本**；2026-09-09
    'ni27_lo': 10170000000.0,  # 2027E 共识下沿（长江）；只披露；**共识待更新，未取得财报后可核验样本**；2026-09-09
    'ni28_m': 16052000000.0,  # 2028E 共识均值；只作对账门读数（含折旧回落，不进分子）；**共识待更新，未取得财报后可核验样本**；2026-09-09
    'ni_l': 2547000000.0,  # FY2023 归母（实测谷底，B1）；FY2023
    'ni_l_rec': 5857000000.0,  # FY2025 归母（实测回升终点，B1）；FY2025
    'n_rec': 2.0,  # 实测回升年数 FY2023 → FY2025；FY2025
    'payout': 0.479,  # FY2023–25 实付（现金 + 回购）÷ 归母（B4）；FY2025
    # The panel axis provides the adopted and reference rates and lifetimes.
    'da_2023': 34840000000.0,  # FY2023 折旧摊销（现金流量表补充资料，B1）；FY2023
    'da_2025': 38670000000.0,  # FY2025 折旧摊销（峰值，B1 / B12）；FY2025
    'da_27': 36740000000.0,  # FY2027E 会计折旧摊销（金元 2026-07-10，B15）；2026-07-10
    'da_nonfa': 1862000000.0,  # 非固定资产折旧摊销（使用权 / 无形 / 长期待摊）= 2026H1 (179.9 − 170.59) × 2，按账面计入经济折旧；2026-06-30
    'gross_equip': 359950000000.0,  # 设备原值（B13）；2026-06-30
    'cip': 58925000000.0,  # 在建工程（B16 / B20 等，计入设备类，B13）；2026-06-30
    'gross_bldg': 82481000000.0,  # 房屋及建筑物原值；2026-06-30
    'gross_other': 21424000000.0,  # 其他固定资产原值；2026-06-30
    'life_bldg': 40.0,  # 房屋经济寿命（年）；2026-10-05
    'life_other': 8.0,  # 其他固定资产经济寿命（年）；2026-10-05
    'tax': 0.15,  # 所得税率（高新技术企业，B15）；FY2025
    'parent_share': 0.641,  # 归母份额 = 归母权益 ÷ 所有者权益（B15）；2026-06-30
    'maint_l': 18420000000.0,  # L 档维护开支 = 2026H1 扣具名扩产后年化（B14）；2026-06-30
    'maint_m': 16000000000.0,  # M 档维护开支 = FY2025 与 2026H1 年化均值（B14）；2026-06-30
    'maint_h': 13560000000.0,  # H 档维护开支 = FY2025 扣具名扩产后（B14）；FY2025
    'cohort_year': 2014.25,  # 四条 8.5 代线平均投产年（B13）；2026-10-05
    'tail_start': 2027.0,  # 尾巴首年 = 资本开支大幅下降起点（IR 2025-10-31）；2025-10-31
    'capex_ex_2025': 13560000000.0,  # FY2025 扣 B16 / B20 后资本开支（B12 进入条件）；FY2025
    'capex_ex_2026h1': 9210000000.0,  # 2026H1 扣 B16 / B20 后资本开支（B12 进入条件）；2026-06-30
    'da_2026h1': 17990000000.0,  # 2026H1 折旧摊销；2026-06-30
    'b16_units': 21300000.0,  # B16 满产年产量（块，B5）；2026-10-04
    'b16_asp_usd': 150.0,  # B16 单价（美元 / 块，待核，B5）；2026-10-04
    'fx': 7.1,  # 美元兑人民币（panel-options 取值）；2026-10-04
    'b16_margin_m': 0.065,  # B16 满产营业利润率 M 档（同业中点，B5）；2026-10-04
    'b16_margin_h': 0.13,  # B16 满产营业利润率 H 档（三星显示 − 3pp，B5）；2026-10-04
    'b16_interest': 750000000.0,  # B16 项目利息 = 250 亿 × 3%（待核）；2023-11-28
    'b16_share': 0.526,  # 京东方持 B16 项目公司比例（IR 2023-037）；2023-11-28
    'b16_years': 2.0,  # 兑现年 FY2029 − 分子年 FY2027（无时点锚·拍值）；2026-10-05
    'b16_budget': 63000000000.0,  # B16 总投资（IR 2023-037）；2023-11-28
    'b16_progress': 0.519,  # B16 投入进度（2026H1 半年报在建工程附注，B12）；2026-06-30
    'b20_budget': 29000000000.0,  # B20 预算（「第 6 代新型半导体显示器件」，2026H1 在建工程附注）；2026-06-30
    'b20_progress': 0.701,  # B20 投入进度（2026H1 半年报，B12）；2026-06-30
    'b20_share': 0.7931,  # 京东方持 B20 项目公司（北京京东方创元科技）比例：注册资本 145 亿中京东方筹 115 亿、亦庄国投牵头 30 亿（公告 2022-077；股权结构「京东方持股 79.31%」）；2022-10-28
    'unspent_years': 1.0,  # 未投资本折现年数：2026H2–2027 投入，按 2027 年末计（与尾巴同为年末）；2026-10-05
    'gcs_rev_ms': 5000000000.0,  # 玻璃基载板 2028E 收入（摩根士丹利 2026-06-30，单家；L / M 份数，B5b）；2026-06-30
    'gcs_wpm': 15000.0,  # 量产线月产能（510×515 片；摩根士丹利 2026-06-30 转述的公司计划，转述；H 份数）；2026-06-30
    'gcs_capex': 5000000000.0,  # 量产线投资（摩根士丹利 2026-06-30 转述，2027 年投入；扣未投 + ROE 分母）；2026-06-30
    'gcs_share': 1.0,  # 京东方占量产线比例（主体未定，按 100%，待核）；2026-10-05
    'gcs_years': 1.0,  # 兑现年 2028（转述的量产目标）− 分子年 FY2027；2026-10-05
    # Shared glass price, comparable margin and growth inputs come from the
    # glass peer ruler; company volume, project capex and timing remain above.
    'ocf_l': 44470000000.0,  # 经营现金流 FY2022–25 均值（所有者盈余交叉）；FY2025
    'ocf_m': 48820000000.0,  # 经营现金流 FY2025（所有者盈余交叉）；FY2025
    'ocf_h': 57500000000.0,  # 经营现金流 2026E（金元，所有者盈余交叉）；2026-07-10
    'interest': 3290000000.0,  # FY2025 利息支出（所有者盈余交叉）；FY2025
    'band_lo': 11.61,  # 同等盈利月份 TTM PE 带下沿（2022-10 收盘 3.34 ÷ TTM EPS 0.2865 = 11.66×，步 1c 扣华灿后），只作 ③ 对带；2026-10-04
    'band_hi': 22.92,  # 同等盈利月份 TTM PE 带上沿（2021-04..07 段）；2026-10-04
    'pb_floor': 0.976,  # 归母口径 PB 实测最低（2022-09），只披露（B6）；2022-09
    'm_prev': 2.94,  # 上一版 M（`boe_fy27_econdep_gordon_tail_v4`，r 13%），对账门用；2026-10-16
    'tau': 0.5,  # 时点对齐年数：估值基准日 2026-06-30（中报资产负债表日）→ 分子年初 2027-01-01（B7）；2026-06-30
    'ni_2026ytd_actual': 4251312657.0,  # Q1 前三季度归母，待滚动采用；独立实际披露；2026-09-30
    'ni_2026q3_actual': -996347420.0,  # Q1 Q3单季归母；独立实际披露；2026-09-30
    'ni_core_ytd_actual': 3040311631.0,  # Q1 前三季度扣非归母；独立实际披露；2026-09-30
    'ni_core_q3_actual': 32059775.0,  # Q1 Q3单季扣非归母；独立实际披露；2026-09-30
    'revenue_ytd_actual': 151808907767.0,  # Q1 前三季度收入；独立实际披露；2026-09-30
    'bps_q3_actual': 3.55224377744567,  # Q1 归母权益除总股本；不混换旧模型；独立实际披露；2026-09-30
    'parent_share_q3_actual': 0.661555442106793,  # Q1 归母权益除全部权益；非实际利润分配比；独立实际披露；2026-09-30
    'cip_q3_actual': 59943521290.0,  # Q1 在建工程；原值等附注未更新；独立实际披露；2026-09-30
    'ocf_ytd_actual': 32211637855.0,  # Q1 前三季度经营现金流，不年化替换全年预测；独立实际披露；2026-09-30
    'capex_ytd_actual': 21364790838.0,  # Q1 前三季度购建长期资产支出，非维护支出；独立实际披露；2026-09-30
    'interest_ytd_actual': 2220736119.0,  # Q1 前三季度利息费用；独立实际披露；2026-09-30
    'operating_profit_ytd_actual': 5559226688.0,  # Q1 报表营业利润，实测杠杆门分母；独立实际披露；2026-09-30
    'pretax_ytd_actual': 5575480630.0,  # Q1 利润总额；独立实际披露；2026-09-30
    'income_tax_ytd_actual': 2192279422.0,  # Q1 所得税费用，实际税负不直接永续化；独立实际披露；2026-09-30
    'cash_growth_h': 0.06,  # 资金用途两端共同长期增长，沿用旧高档上限；不是新财报确认的增长指引（B17）；2026-11-05
    'cash_tau_q3': 0.25,  # Q3 基准 2026-09-30 至分子年初 2027-01-01，仅用于研究区间；2026-09-30
    'cash_release_years': 6.0,  # 2027–2032 释放、2033 起重新占用的期限敏感性；情景示意，不是公司指引；2026-11-05
}
GCS_SHARED = ("gcs_abs_rev_usd", "gcs_abs_cap_m2", "gcs_panel_m2", "gcs_price_h_usd",
              "gcs_opm_weak", "gcs_opm_strong", "gcs_yield_disc", "g2_gcs_src")
FORMULA_ID = "boe_fy27_econdep_gordon_tail_v5"
NUMERATOR_YEAR = 2027
TIERS = ("l", "m", "h")
REQUIRED = [
    "shares", "bps", "ni_2026h1", "ni_ttm",
    "ni26_m", "ni26_h", "ni27_m", "ni27_h", "ni27_lo", "ni28_m",
    "ni_l", "ni_l_rec", "n_rec", "payout", "r_perp", "r_perp_ref",
    "da_2023", "da_2025", "da_27", "da_nonfa",
    "gross_equip", "cip", "gross_bldg", "gross_other", "life_bldg", "life_other",
    "life_l", "life_m", "life_h", "tax", "parent_share",
    "maint_l", "maint_m", "maint_h", "cohort_year", "tail_start",
    "capex_ex_2025", "capex_ex_2026h1", "da_2026h1",
    "b16_units", "b16_asp_usd", "fx", "b16_margin_m", "b16_margin_h", "b16_interest", "b16_share",
    "b16_years",
    "b16_budget", "b16_progress", "b20_budget", "b20_progress", "b20_share", "unspent_years",
    "gcs_rev_ms", "gcs_wpm", "gcs_capex", "gcs_share", "gcs_years", *GCS_SHARED,
    "ocf_l", "ocf_m", "ocf_h", "interest", "band_lo", "band_hi", "pb_floor", "m_prev", "tau",
    "bps_q3_actual", "parent_share_q3_actual", "cip_q3_actual", "ni_2026ytd_actual",
    "cash_growth_h", "cash_tau_q3", "cash_release_years",
]


def policy_pe(roe: float, r: float, po: float, dg: float = 0.0) -> tuple[float, float, float]:
    """Legacy formal deck only; cash ownership is explicit in the research range."""
    g_raw = (1 - po) * roe + dg
    cap = g_cap(r)
    if g_raw <= cap:
        return perpetual_pe(g_raw, roe, r), g_raw, g_raw
    if roe <= r + 0.03:
        return capped_payout_pe(g_raw, roe, r, po), cap, g_raw
    return perpetual_pe(cap, roe, r), cap, g_raw


def cash_use_pe(roe: float, r: float, g: float, po: float, release: float,
                years: int | None = None) -> float:
    """Same cash expression at both endpoints; release is an amount share, not probability.

    The upper endpoint assumes the return proxy really measures investment needs.
    No domain threshold changes ownership. A finite release reverts to baseline.
    """
    if not (roe > 0 and 0 <= g < r and 0 <= po <= 1 and 0 <= release <= 1):
        raise ValueError("invalid cash-use scenario")
    if years is not None and (not isinstance(years, int) or years < 0):
        raise ValueError("release years must be a nonnegative integer")
    gap = max(0.0, 1 - g / roe - po)
    duration = 1 / (r - g) if years is None else annuity_factor(g, r, years)
    return po / (r - g) + release * gap * duration


def econ_d(inp: dict[str, float], t: str) -> float:
    """Economic D (yuan/yr): gross cost by class / economic life; non-fixed-asset D&A kept at book."""
    return ((inp["gross_equip"] + inp["cip"]) / inp[f"life_{t}"]
            + inp["gross_bldg"] / inp["life_bldg"] + inp["gross_other"] / inp["life_other"]
            + inp["da_nonfa"])


def adj_ni(ni: float, da_same_year: float, ed: float, inp: dict[str, float]) -> float:
    """Perpetual numerator: book NI + (same-year accounting D - economic D) x (1 - t) x parent share."""
    return ni + (da_same_year - ed) * (1 - inp["tax"]) * inp["parent_share"]


def n_tail(inp: dict[str, float], t: str) -> int:
    """Years from tail_start until the Gen-8.5 cohort (mean in-service year) reaches its economic life."""
    return max(0, round(inp["cohort_year"] + inp[f"life_{t}"] - (inp["tail_start"] - 1)))


def tail(inp: dict[str, float], t: str, r: float) -> dict[str, float]:
    ed = econ_d(inp, t)
    gap = (ed - inp[f"maint_{t}"]) * (1 - inp["tax"]) * inp["parent_share"] / inp["shares"]
    n = n_tail(inp, t)
    af = annuity_factor(0.0, r, n)
    return dict(ed=ed, gap=gap, n=n, af=af, v=gap * af)


def unspent(x: dict[str, float]) -> float:
    """B16 + B20 budget not yet spent (yuan), from the 2026H1 progress ratios."""
    return x["b16_budget"] * (1 - x["b16_progress"]) + x["b20_budget"] * (1 - x["b20_progress"])


def unspent_owned(x: dict[str, float]) -> float:
    """BOE's own part of the unspent B16 + B20 capital (yuan): each line at its own BOE ownership."""
    return (x["b16_budget"] * (1 - x["b16_progress"]) * x["b16_share"]
            + x["b20_budget"] * (1 - x["b20_progress"]) * x["b20_share"])


def deduction(x: dict[str, float], r: float) -> float:
    """§5b entry-exclusion deduction, yuan/share: unspent B16 / B20 x each line's BOE share, discounted."""
    return unspent_owned(x) / (1 + r) ** x["unspent_years"] / x["shares"]


def window_profit(x: dict[str, float], t: str, ed: float) -> float:
    """Window distributable profit, yuan/share (valuation-rules「经营价值与超额现金」③ 时点对齐):
    2H26 unbooked consensus 归母 on the numerator basis (+ half a year of (accounting D - economic D)
    x (1 - t) x s, FY2025 D as the FY2026 proxy) x (1 - b), b = the book-roll retention 1 - payout.
    Floored at 0 (DECISIONS: b > 1 cases belong to the funding-gap line)."""
    unb = x[f"ni26_{t}"] - x["ni_2026h1"] + x["tau"] * (x["da_2025"] - ed) * (1 - x["tax"]) * x["parent_share"]
    return max(0.0, unb * x["payout"] / x["shares"])


def deck(inp: dict[str, float], dg: float = 0.0, r: float | None = None,
         over: dict[str, float] | None = None, *, h_release: float | None = None,
         h_release_years: int | None = None) -> dict[str, dict[str, float]]:
    x = dict(inp, **(over or {}))
    sh, po = x["shares"], x["payout"]
    r = x["r_perp"] if r is None else r
    ded = deduction(x, r)
    out: dict[str, dict[str, float]] = {}
    for t in ("m", "h"):
        ed = econ_d(x, t)
        ni_adj = adj_ni(x[f"ni27_{t}"], x["da_27"], ed, x)
        eps = ni_adj / sh
        bps = x["bps"] + (1 - po) * (x[f"ni26_{t}"] - x["ni_2026h1"]) / sh
        roe = eps / bps
        pe, g, g_raw = policy_pe(roe, r, po, dg)
        if t == "h" and h_release is not None:
            g = x["cash_growth_h"]
            pe = cash_use_pe(roe, r, g, po, h_release, h_release_years)
        tl = tail(x, t, r)
        perp = eps * pe
        win = window_profit(x, t, ed)
        a = (perp + tl["v"]) * (1 + r) ** -x["tau"] + win * (1 + r) ** -(x["tau"] / 2) - ded
        out[t] = dict(ed=ed, ni_adj=ni_adj, eps=eps, eps_book=x[f"ni27_{t}"] / sh, bps=bps, roe=roe,
                      g=g, g_raw=g_raw, pe=pe, perp=perp, tail=tl, ded=ded, win=win, a=a)
    ed = econ_d(x, "l")
    eps_l = adj_ni(x["ni_l"], x["da_2023"], ed, x) / sh
    eps_rec = adj_ni(x["ni_l_rec"], x["da_2025"], ed, x) / sh
    n = int(x["n_rec"])
    g1 = (eps_rec / eps_l) ** (1 / n) - 1
    pe_l = recovery_two_stage_pe(g1, n, out["m"]["g"], out["m"]["roe"], r)
    tl = tail(x, "l", r)
    out["l"] = dict(ed=ed, eps=eps_l, eps_rec=eps_rec, eps_book=x["ni_l"] / sh, g1=g1, pe=pe_l,
                    perp=eps_l * pe_l, tail=tl, ded=ded, a=eps_l * pe_l + tl["v"] - ded)
    return out


def cash_use_candidates(inp: dict[str, float]) -> dict[str, dict[str, dict[str, float]]]:
    """Q3 research only: no mutation of the formal deck, no App candidate band.

    ni_2026h1 is the legacy slot for already-booked profit; here it receives YTD.
    Missing project progress/payment timing and asset gross costs stay dated H1.
    """
    x = dict(inp, bps=inp["bps_q3_actual"], parent_share=inp["parent_share_q3_actual"],
             cip=inp["cip_q3_actual"], ni_2026h1=inp["ni_2026ytd_actual"],
             tau=inp["cash_tau_q3"])
    return {
        "occupied": deck(x, h_release=0),
        "released": deck(x, h_release=1),
        "six_years": deck(x, h_release=1, h_release_years=int(inp["cash_release_years"])),
    }


def book_deck(inp: dict[str, float]) -> tuple[float, float, float]:
    """Cross-check: the old ruler on the same FY2027 numerators — book NI, no economic D, no tail."""
    sh, po, r = inp["shares"], inp["payout"], inp["r_perp"]
    res = {}
    for t in ("m", "h"):
        eps = inp[f"ni27_{t}"] / sh
        bps = inp["bps"] + (1 - po) * (inp[f"ni26_{t}"] - inp["ni_2026h1"]) / sh
        pe, g, _ = policy_pe(eps / bps, r, po)
        res[t] = (eps * pe, g, eps / bps)
    eps_l = inp["ni_l"] / sh
    g1 = (inp["ni_l_rec"] / inp["ni_l"]) ** (1 / int(inp["n_rec"])) - 1
    lv = eps_l * recovery_two_stage_pe(g1, int(inp["n_rec"]), res["m"][1], res["m"][2], r)
    return lv, res["m"][0], res["h"][0]


def b16_option(inp: dict[str, float], margin: float, r: float) -> float:
    """B16 full-capacity increment, yuan/share: project NI x BOE share / r, discounted b16_years."""
    rev = inp["b16_units"] * inp["b16_asp_usd"] * inp["fx"]
    ni = (rev * margin - inp["b16_interest"]) * (1 - inp["tax"])
    return ni * inp["b16_share"] / r / (1 + r) ** inp["b16_years"] / inp["shares"]


def gcs_option(inp: dict[str, float], t: str, r: float, g2: float | None = None) -> dict[str, float]:
    """Glass-core substrate leg, yuan/share (floored at 0).

    L / M: Morgan Stanley 2028E revenue (single house).  H: relayed full capacity x axis
    price.  Margin: adjacent ABF layer — L weak, H strong minus discount, M midpoint.
    ROE on the line's own capital; ROE <= r -> 1/r, else perpetual_pe at the leg g2.
    Value at the realisation year, discounted gcs_years; unspent line capital
    discounted unspent_years; both at the BOE share of the line.
    """
    g2 = min(inp["g2_gcs_src"], g_cap(r)) if g2 is None else g2
    if t == "h":
        rev = inp["gcs_wpm"] * 12 * inp["gcs_price_h_usd"] * inp["fx"]
    else:
        rev = inp["gcs_rev_ms"]
    opm_h = inp["gcs_opm_strong"] - inp["gcs_yield_disc"]
    opm = {"l": inp["gcs_opm_weak"], "m": (inp["gcs_opm_weak"] + opm_h) / 2, "h": opm_h}[t]
    ni = rev * opm * (1 - inp["tax"])
    roe = ni / inp["gcs_capex"]
    pe = 1 / r if roe <= r else perpetual_pe(g2, roe, r)
    gross = ni * pe / (1 + r) ** inp["gcs_years"]
    cap = inp["gcs_capex"] / (1 + r) ** inp["unspent_years"]
    raw = (gross - cap) * inp["gcs_share"] / inp["shares"]
    return dict(rev=rev, opm=opm, ni=ni, roe=roe, pe=pe, g2=g2 if roe > r else 0.0,
                gross=gross * inp["gcs_share"] / inp["shares"], cap=cap * inp["gcs_share"] / inp["shares"],
                raw=raw, v=max(0.0, raw))


def evaluate(inp, glass_rules):
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[key]) for key in REQUIRED):
        raise ValueError('all required inputs must be finite')
    for key in ('n_rec', 'cash_release_years', 'tail_start'):
        if isinstance(inp[key], bool) or not float(inp[key]).is_integer():
            raise ValueError(f'{key} must be a whole number')
    baskets = {'r_perp': 5}  # Borrowed axis value by the 2026-10-23 ruling.
    r, po, sh = inp['r_perp'], inp['payout'], inp['shares']
    errors += check_r(r, 'r_perp', baskets['r_perp'])
    d = deck(inp)
    candidates = cash_use_candidates(inp)
    cash_low = candidates["occupied"]["h"]["a"]
    cash_high = candidates["released"]["h"]["a"]
    cash_finite = candidates["six_years"]["h"]["a"]
    if not cash_low < cash_finite < cash_high:
        errors.append("finite cash release must lie strictly between occupied and perpetual release")
    for t in ("l", "m"):
        if candidates["occupied"][t] != candidates["released"][t]:
            errors.append(f"cash ownership uncertainty leaked into tier {t}")
    for release in (0, 0.5, 1):
        near = [cash_use_pe(r + 0.03 + delta, r, inp["cash_growth_h"], po, release)
                for delta in (-1e-6, 1e-6)]
        if abs(near[1] - near[0]) > 0.001:
            errors.append("cash ownership jumps at the legacy return boundary")
    h_candidate = candidates["released"]["h"]
    gap = max(0, 1 - inp["cash_growth_h"] / h_candidate["roe"] - po)
    years = int(inp["cash_release_years"])
    yearly_pv = sum(gap * (1 + inp["cash_growth_h"]) ** (t - 1) / (1 + r) ** t
                    for t in range(1, years + 1))
    expected_finite = cash_low + h_candidate["eps"] * yearly_pv * (1 + r) ** -inp["cash_tau_q3"]
    if abs(cash_finite - expected_finite) > 1e-9:
        errors.append("finite cash release differs from independently discounted annual cash")
    L, M, H = (d[t]["a"] for t in TIERS)
    A, B = cut_points(L, M, H)
    errors += ladder("NI27 consensus", inp["ni27_lo"], inp["ni27_m"], inp["ni27_h"])
    errors += ladder("anchors", L, M, H)
    for t in ("m", "h"):
        errors += check_g_cap(d[t]["g"], r, f"g_{t}")
        errors += check_branch(d[t]["g"], d[t]["roe"], r, po, f"tier {t.upper()}") if d[t]["g"] == d[t]["g_raw"] else []

    # --- §5b guards --------------------------------------------------------------------------
    # Entry: capex (ex the two named expansion lines B16 / B20) / D&A < 0.6 for two periods.
    for name, cx, da in (("FY2025", inp["capex_ex_2025"], inp["da_2025"]),
                         ("2026H1", inp["capex_ex_2026h1"], inp["da_2026h1"])):
        if cx / da >= 0.6:
            errors.append(f"§5b entry: capex ex-B16/B20 / D&A {name} = {cx / da:.2f} >= 0.6")
    # Company: 2025 is the D&A peak; B16/B20 may add a little but not above it.
    if not inp["da_27"] <= inp["da_2025"]:
        errors.append("da_27 above the 2025 peak — contradicts company guidance (B12)")
    # No double count: the perpetual numerator is pre-D profit minus economic D, nothing else —
    # (i) recompute from first principles; (ii) it must not move when the tail inputs move.
    for t in ("m", "h"):
        pre_d = inp[f"ni27_{t}"] + inp["da_27"] * (1 - inp["tax"]) * inp["parent_share"]
        expect = (pre_d - d[t]["ed"] * (1 - inp["tax"]) * inp["parent_share"]) / sh
        if abs(expect - d[t]["eps"]) > 1e-9:
            errors.append(f"tier {t.upper()}: perpetual EPS != pre-D profit - economic D")
    bumped = deck(inp, over={"maint_l": 0.0, "maint_m": 0.0, "maint_h": 0.0, "tail_start": 2010})
    for t in TIERS:
        if abs(bumped[t]["perp"] - d[t]["perp"]) > 1e-9:
            errors.append(f"tier {t.upper()}: tail inputs leak into the perpetual segment")
        if not d[t]["tail"]["gap"] > 0:
            errors.append(f"tier {t.upper()}: economic D <= maintenance capex — no tail")
        if not d[t]["tail"]["v"] < d[t]["tail"]["gap"] / r:
            errors.append(f"tier {t.upper()}: tail is not finite (>= perpetuity)")
    # The FY2027->FY2028 consensus step is mostly roll-off; it must not sit in the perpetual numerator.
    roll_in_m = d["m"]["eps"] * sh - inp["ni27_m"]
    if abs(roll_in_m - (inp["da_27"] - d["m"]["ed"]) * (1 - inp["tax"]) * inp["parent_share"]) > 1:
        errors.append("M numerator carries an adjustment other than same-year (D - econ D)")

    # Entry exclusion: the deduction is the same in every tier and equals unspent B16 / B20 x line shares.
    ded = deduction(inp, r)
    for t in TIERS:
        if abs(d[t]["ded"] - ded) > 1e-12:
            errors.append(f"tier {t.upper()}: B16/B20 unspent deduction differs across tiers")
    if not 3.5e10 < unspent(inp) < 4.5e10:
        errors.append(f"B16/B20 unspent {unspent(inp) / 1e8:.1f}亿 outside the 350–450亿 sanity band")

    # Shared glass inputs already come from the frozen peer-axis snapshot.
    price_h = inp["gcs_abs_rev_usd"] / inp["gcs_abs_cap_m2"] * inp["gcs_panel_m2"]
    if abs(price_h - inp["gcs_price_h_usd"]) > 1.0:
        errors.append(f"gcs_price_h_usd {inp['gcs_price_h_usd']} != Absolics target / capacity x panel {price_h:.0f}")

    # --- option ------------------------------------------------------------------------------
    # Both option values sit at the numerator year (FY2027 basis) -> same tau as the base (time alignment).
    # Glass-core leg = 叙事换代 (B5b): no own history, no >= 5-year mature peer -> steady = min(fwd, 30%),
    # no fade, so the leg keeps the plain Gordon multiple.
    tf = (1 + r) ** -inp["tau"]
    v_h = b16_option(inp, inp["b16_margin_h"], r) * tf
    v_m = b16_option(inp, inp["b16_margin_m"], r) * tf
    b16 = {"l": 0.0, "m": 0.5 * v_m, "h": v_h}          # p_M(B16) = 0.5 x V_M/V_H (B5)
    gcs = {t: gcs_option(inp, t, r) for t in TIERS}
    # The historic formula has no return fade. Enforce the shared visible-year
    # alignment and only retain that formula when every forward ROE is at or
    # below the axis's steady cap; a higher-return case needs a model rebuild.
    glass_adoption = check_glass_ruler(glass_rules, numerator_year=NUMERATOR_YEAR,
                                       realization_offset=inp['gcs_years'],
                                       projected_returns=tuple(gcs[t]['roe'] for t in TIERS))
    for t in TIERS:
        gcs[t]["v"] *= tf
    gcs_vh = gcs["h"]["v"]
    gcs_p = {t: (gcs[t]["v"] / gcs_vh if gcs_vh > 0 else 0.0) for t in TIERS}   # p_k = V_k / V_H
    v_tot = v_h + gcs_vh
    contrib = {t: b16[t] + gcs_p[t] * gcs_vh for t in TIERS}
    p_tot = {t: contrib[t] / v_tot for t in TIERS}
    if not (0 <= p_tot["l"] <= p_tot["m"] <= p_tot["h"] == 1.0):
        errors.append("p_k ladder 0 <= p_L <= p_M <= p_H = 1 violated")

    flat = [d[t]['eps'] * d['m']['pe'] + d[t]['tail']['v'] - d[t]['ded'] for t in TIERS]
    errors += ladder('flat-multiple', *flat)
    if errors:
        raise ValueError('; '.join(errors))
    tiers = lambda values: dict(zip('LMH', values))
    base = tiers(d[t]['a'] for t in TIERS)
    option = tiers(d[t]['a'] + contrib[t] for t in TIERS)
    sensitivity = {
        'growth_minus_1pp': tiers(deck(inp, -.01)[t]['a'] for t in TIERS),
        'growth_plus_1pp': tiers(deck(inp, .01)[t]['a'] for t in TIERS),
        'da27_343': tiers(deck(inp, over={'da_27': 3.43e10})[t]['a'] for t in TIERS),
        'da27_peak': tiers(deck(inp, over={'da_27': inp['da_2025']})[t]['a'] for t in TIERS),
        'economic_ex_cip': tiers(deck(inp, over={'cip': 0.0})[t]['a'] for t in TIERS),
        'parent_share_55': tiers(deck(inp, over={'parent_share': .55})[t]['a'] for t in TIERS),
        'life_all_175': tiers(deck(inp, over={'life_l': 17.5, 'life_h': 17.5})[t]['a'] for t in TIERS),
        'cohort_earlier_2y': tiers(deck(inp, over={'cohort_year': inp['cohort_year'] - 2})[t]['a'] for t in TIERS),
        'deduction_undiscounted': tiers(deck(inp, over={'unspent_years': 0})[t]['a'] for t in TIERS),
        'deduction_none': tiers(deck(inp, over={'b16_progress': 1., 'b20_progress': 1.})[t]['a'] for t in TIERS),
        'r_reference': tiers(deck(inp, r=inp['r_perp_ref'])[t]['a'] for t in TIERS),
        'book_deck': tiers(book_deck(inp)), 'cash_release': {
            key: tiers(candidates[key][t]['a'] for t in TIERS) for key in ('occupied', 'six_years', 'released')},
    }
    # H uses actual policy payout because raw policy growth hits the cap;
    # its uncapped economic return does not enter that multiple.
    fingerprint_inputs = dict(inp)
    for key in ('life_l', 'life_m', 'life_h'):
        fingerprint_inputs[key] = float(fingerprint_inputs[key])
    fingerprint_context = {'inputs': fingerprint_inputs,
                           'glass_ruler': {key: glass_rules[key] for key in
                                           ('t_align', 'ss_return_cap_gcs', 'fall_years_gcs')}}
    fingerprint = hashlib.sha256(json.dumps(fingerprint_context, sort_keys=True, separators=(',', ':'),
                                            allow_nan=False).encode()).hexdigest()
    ratio = lambda values: {'unit': 'RATIO', 'values': values}
    return {'ticker': '000725.SZ', 'currency': 'CNY', 'valuation_as_of': None, 'framework_as_of': None,
            'historical_financial_statement_as_of': '2026-06-30', 'historical_research_as_of': '2026-11-05',
            'basis_changed': None, 'partial_basis_changed': fingerprint != HISTORICAL_INPUT_FINGERPRINT,
            'units': {'price': 'CNY_PER_SHARE'},
            'anchors': base, 'candidate': None,
            'option': {'label': 'B16 与玻璃基板', 'value': v_tot, 'value_unit': 'CNY_PER_SHARE',
                       'weights': tiers(p_tot[t] for t in TIERS),
                       'anchors': option, 'components': {'b16': tiers(b16[t] for t in TIERS),
                                                         'glass': tiers(gcs[t]['v'] for t in TIERS)}},
            'segments': {'company': {'label': '整公司', 'unit': 'CNY_PER_SHARE', 'values': base}},
            'key_parameters': {'company': {
                'discount_rate': ratio(tiers((r, r, r))),
                'growth_rate': ratio(tiers((d['m']['g'], d['m']['g'], d['h']['g']))),
                'forward_return': ratio(tiers((None, d['m']['roe'], d['h']['roe']))),
                'steady_return': ratio(tiers((d['m']['roe'], d['m']['roe'], None)))}},
            'operating': {'deck': {t.upper(): d[t] for t in TIERS}, 'glass': {t.upper(): gcs[t] for t in TIERS},
                          'glass_ruler_adoption': glass_adoption,
                          'deduction': ded, 'unspent': unspent(inp), 'flat': tiers(flat),
                          'economic_life': tiers(inp[f'life_{t}'] for t in TIERS),
                          'recovery_growth': d['l']['g1'], 'recovery_years': inp['n_rec']},
            'sensitivity': sensitivity}


def calculate(context: dict) -> dict:
    panel, glass = context['axes']['panel'], context['axes']['glass']
    panel_fields, glass_fields = panel['stock_fields'], glass['stock_fields']
    required_panel = {'r_perp', 'r_perp_ref', 'life_l', 'life_m', 'life_h'}
    if (panel['scope'] != 'company' or set(panel_fields) != required_panel
            or glass['axis_metadata']['role'] != 'reference' or set(glass_fields) != set(GCS_SHARED)
            or (required_panel | set(GCS_SHARED)) & INPUTS.keys()):
        raise ValueError('panel or glass axis scope and shared inputs are invalid')
    return evaluate({**INPUTS, **panel_fields, **glass_fields}, glass)
