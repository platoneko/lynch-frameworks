#!/usr/bin/env python3
"""000792.SZ (Salt Lake) valuation eval.

Inputs are in this script and the shared lithium axis module; this script computes
L/M/H / A/B independently of the explanatory document. The doc states
no current price or zone (the digest and the app zone on live quotes).
formula_id: saltlake_li_axis_kcl_ladder_pe_v2_gordon_v4

v4 H pass-by (2026-10-18, _AXIS.lithium-carbonate「H 档是路过」, framework correction, A12):
the lithium axis H rung (2026 platform carried into 2027) lasts one year, then the lithium leg
is back in the M world; the potash leg keeps its own H rung (its ladder is not the lithium axis).
H = [E_op,H × payout(g, RONIC_H) + E_op,mix × PE(g, RONIC_mix) × (1 + g)] / (1 + r) + cash +
window_H, where「mix」= lithium at the M rung, potash at the H rung (`passby_h`).  g = 0 makes
the potash leg's value identical to its persistent H value; only the lithium leg moves.  Every
L/M/H triple printed below (demoted-basket coordinate, g / r / numerator what-ifs) uses the same
pass-by H; the flat-multiple ladder stays on the persistent H as the A2e-2c diagnostic.

v4 time alignment (2026-10-16, valuation-rules「经营价值与超额现金」③, framework correction, A12):
the lithium leg's「2027 run-rate」value sits at t_n = 2027-01-01; the valuation date is the
2026-06-30 balance sheet, so `n_disc` is now τ = 0.5 (the old「one year until sales catch up
with nameplate」discount is replaced).  The not-yet-booked 2H26 consensus profit (FY26E EPS ×
shares − 1H26 parent − half a year of after-tax cash income), × (1 − b) with b = g2/RONIC = 0,
lithium leg's GP share only, discounted τ/2, is added per tier (`window_ps`).  Potash is a
current annualised half-year: τ 0.  Growth-period funding gap 0.  The step-1c project strip
keeps its 2026-10-04 one-year ramp δ (a band construction, not today's anchor).

v4 (2026-10-15, valuation-rules「经营价值与超额现金」, framework correction):
value per share = operating EPS × Gordon PE + excess cash per share (λ 1).
The extended net cash at 2026-06-30 (cash + trading FA + CDs / term deposits −
loans − leases − mining-right installment payables, no declared-unpaid
dividend) over an operating-cash anchor of 0 (post-restructuring cycle
FY2021–25 bottoms in net debt) is the excess cash; only the parent's share
counts, pro rata to equity (subsidiary cash split not disclosed), so the
minorities' share is taken out of the amount rather than through λ.  Every
tier's parent NP loses the after-tax income on that cash; the per-tier
operating return (E_op / (parent equity − C_ex)) replaces the book ROE.  g2 = 0
is kept (decided), so the multiple stays 1/r.  The same-earnings band points,
the step-1c project strip, the overturned basket-5 coordinate and the trough
coordinates are all re-read on the operating basis ((close − then C_ex per
share) ÷ (then EPS − then after-tax cash income per share)).

v3 (2026-10-04, valuation-rules「③ 出带处理流程」步 1c): the same-earnings band
floor is re-read on the base's basis.  The 2022-09→2023-10 band months priced the
4万吨 lithium-salt project (announced 2022-05-27, 公告 2022-038; not in their TTM
EPS) that today's nameplate numerator already holds, so the project's value on
this ticker's ruler -- M-tier lithium unit GP × conv_ratio, nameplate δ, 1/r,
discounted from the expected COD (2022 年报: 2024 年底) to the band point, net of
the announced capex -- comes off the band price before the band multiple is
taken.  At the initial basket 6 the adjusted floor sits under 1/r, so ③ never
fires: the 2026-09-20 demotion to basket 5 is overturned and printed only as the
「对照坐标（被推翻的降篮）」band.  On the v4 operating basis the raw floor is
already under 1/r; step 1c stays as the guardrail floor's construction.

Lithium volume is the commissioned nameplate (9.8 万吨/年) discounted one year
at the basket r, so the 2027-28 price deck of the shared axis meets a 2027
run-rate volume -- the same construction as 9696.HK.  Potash stays on the
annualised H1 volume without discounting (current capacity).

Multiples are Gordon-generated at the legs' basket r (both legs = 篮 6, the
initial basket; the 篮 5 demotion was overturned by step 1c, A10): RONIC per
tier = operating parent NP / operating equity, PE_x = perpetual_pe(g2, RONIC_x, r)
with ONE flat g2 = 0 (§13 commodity-leg tier default: lithium real price drift
≤ −3%/yr floored at 0, potash has no peer anchor), so every tier sits at 1/r.
The axis 永续 g2 row is referenced verbatim (`axis_g2_li`) and not adopted.

L tier (valuation-rules「谷底档」): the axis L world (Li2CO3 103k = 2028
surplus bottom between BMI 113k and Goldman 85k, above the p90 cost curve) is a regime, not the company's
realised trough (FY2024, lithium 6–8 万).  `recovery_two_stage_pe` on the
company's own measured operating path (FY2024 → FY2025, n = 1) is printed as a
coordinate and is not the anchor.  The PB floor is disclosure only (A4): L is
the scenario value, never max(scenario, floor).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    raise SystemExit("Use the explicit valuation_runner with code and content roots")

from lib.gordon import (basket_r, check_branch, check_g_cap, check_r, payout,
                        perpetual_pe, recovery_two_stage_pe, two_stage_pe)
DEPENDENCIES = {'libraries': ('gordon',), 'axes': {'lithium': 'lithium_carbonate'}}
FORMULA_ID = "saltlake_li_axis_kcl_ladder_pe_v2_gordon_v4"
MIN_R_MINUS_G = 0.02
C_EX_TRIGGER = 0.15
# A9: the company's own realised trough→recovery path on the operating basis
# (亿; parent NI − own-year after-tax income on own-year parent-share C_ex:
# FY2024 46.63 − 3.53 = 43.10 → FY2025 84.76 − 3.71 = 81.05; A11).
RECOVERY_MEASURED = {"FY2024→FY2025": (43.10, 81.05, 1)}
# A10: the initial basket (current ruler) and the overturned 2026-09-20 demotion
# target, printed as the「对照坐标（被推翻的降篮）」band, never a zone.
INITIAL_BASKET = 6
DEMOTED_BASKET = 5
# Same-earnings band points (A10): (tag, raw PE field, close, years-to-COD or None,
# then C_ex per share, then after-tax cash income per share).  The LB weekly low
# is the guardrail floor; the next two are disclosed variants; the last is the
# band top (project already in its EPS, no strip).
BAND_POINTS = (
    ("LB 周点 2023-03-26", "pe_same_min", "band_lb_close", "band_lb_cod_yrs", "band_lb_cex", "band_lb_cinc"),
    ("事实口径 2023-10", "band_fact_pe", "band_fact_close", "band_fact_cod_yrs", "band_fact_cex", "band_fact_cinc"),
    ("剔 FY22 预告月 2023-09-24", "band_ex_pe", "band_ex_close", "band_ex_cod_yrs", "band_ex_cex", "band_ex_cinc"),
)
BAND_TOP = ("LB 周点 2026-05-03", "pe_same_max", "band_max_close", None, "band_max_cex", "band_max_cinc")
TOL = 0.05
YI = 1e8

# Formula「校验」regression guard: H1 sales volume, no discount, lithium at the
# axis H rung (= the H1 platform) and potash at the H1 ASP must reproduce
# 2 × H1 parent net profit (中报 归母 61.685 亿).
H1_PARENT_X2 = 61.685e8 * 2
GUARD_TOL = 0.01

# Inputs transcribed from the previous framework Inputs; sources remain in the document.
INPUTS = {
    # 总股本；Longbridge | as-of 2026-09-11
    'shares': 5291570000.0,
    # 每股净资产；2026H1 中报 | as-of 2026-06-30
    'bps': 9.024,
    # 少数股东权益 51.54 亿；2026H1 中报合并资产负债表。归母份额 = `bps × shares` ÷ (`bps × shares` + 本行) = 90.26%，超额现金按此比例取归母部分（A11） | as-of 2026-06-30
    'equity_nci': 5153587837.0,
    # 扩展口径净现金 340.13 亿 = 现金类 369.47（货币资金 322.71 + 交易性金融资产 0.06 + 其他流动资产里的一年内大额存单 32.11 + 其他非流动资产里的一年以上定期存款 14.59）− 类债 29.35（短期借款 0.08 + 一年内到期非流动负债 11.58 + 长期借款 2.16 + 租赁负债 0.97 + 长期应付款即采矿权分期款 14.56）；2026H1 中报 + 东方财富 F10（A11） | as-of 2026-06-30
    'net_cash_ext_h1': 34012706572.0,
    # 已宣派未付股息（合并报表应付股利 11.56 亿，全是普通股股利；母公司报表应付股利只 0.08 亿 → 基本是子公司欠少数股东 / 原股东的）；类债项，从净现金里扣；2026H1 中报附注 | as-of 2026-06-30
    'div_declared': 1155600797.0,
    # 超额现金（归母份额）=（`net_cash_ext_h1` − `div_declared` − 经营所需现金锚 0）× 归母份额 90.26% = 296.56 亿；少数股东那部分 32.01 亿不计（A11） | as-of 2026-06-30
    'c_ex': 29656408500.0,
    # 现金收益率 FY2025 = 利息收入 + 大额存单利息 + 交易性金融资产收益 4.73 亿 ÷ 平均现金类资产 308.21 亿（FY2024 258.77 / FY2025 357.64）；年报 | as-of FY2025
    'cash_yield': 0.015347,
    # 实际所得税率：2026H1 所得税 12.01 ÷ 利润总额 84.52 亿。FY2025 所得税是一次性递延所得税收益（税率 −24.4%），不能用 | as-of 2026-06-30
    'tax_eff': 0.1422,
    # 经营口径派息率 =（分红 0 + 注销式回购 14.99 + 现金积累 282.13）÷ 经营利润合计 398.25 亿，FY2021–25 一个完整周期（A11）；只披露（g2 = 0 已拍板） | as-of FY2025
    'payout_op': 0.746,
    # 实付分配率 = 注销式回购 14.99 ÷ 经营利润合计 398.25 亿（FY2021–25 无现金分红）；多留部分用 | as-of FY2025
    'payout_paid': 0.0376,
    # H1 锂 ASP 143261 ÷ 150000（旧轴 M，≈H1 平台）；轴 M 改 12.0 万后 M 档实现价 = ASP × 12.0/15；2026H1 中报 | as-of 2026-06-30
    'realization_li': 0.955071,
    # 锂量 吨/年 = 已建成名牌（蓝科 4.1 + 4 万吨项目 + 五矿 1.8）；三档同量，折现见 `n_disc`（A5）；2026H1 中报 | as-of 2026-06-30
    'vol_li_plan': 98000.0,
    # H1 销量 3.91 万 × 2；仅作对照与敏感性，**不入主公式** | as-of 2026-06-30
    'vol_li_h1': 78200.0,
    # 锂名牌量折现率 = 经营腿的篮子 r（与 `r_perp` 同值，A10）；δ = 1.13^−τ = 0.9407（τ 见 `n_disc`，A12） | as-of 2026-10-04
    'r_disc': 0.13,
    # **时点对齐 τ**（年，A12）：估值基准日 2026-06-30（超额现金的资产负债表日）→ 锂腿分子「2027 run-rate」的年初 t_n 2027-01-01；原「销量追上名牌 ≈ 折 1 年」由 valuation-rules「经营价值与超额现金」③ 时点对齐取代（锂腿少折半年，δ = 1.13⁻⁰·⁵ = 0.9407）；钾腿当期年化，τ 0 | as-of 2026-10-16
    'n_disc': 0.5,
    # FY2026E 共识 EPS（LB 20 家，区间 1.62–2.48，A3）；**进窗口可分配利润**（× 股本 − `parent_h1_26` = 2H26 未入账共识利润，A12） | as-of 2026-09-18
    'eps_fy26_cons': 2.22,
    # 2026H1 归母净利润 61.685 亿（中报）；窗口可分配利润的已入账部分（A12） | as-of 2026-06-30
    'parent_h1_26': 6168500000.0,
    # ASP × (1 − 83.46%)；2026H1 中报 | as-of 2026-06-30
    'cost_li': 23695.32,
    # 钾 L：2025 初青海到站低位邻域（实证，观测月待补） | as-of 2025 初
    'kcl_price_l': 2500.0,
    # 钾 M：H1 段收入 71.373 ÷ 销量 224.74 万；2026H1 中报 | as-of 2026-06-30
    'kcl_price_m': 3175.81,
    # 钾 H：2025–26 春耕高位可复现（实证，观测月待补） | as-of 2025–26 春耕
    'kcl_price_h': 3500.0,
    # H1 销量 224.74 万 × 2；2026H1 中报 | as-of 2026-06-30
    'vol_k': 4494800.0,
    # ASP × (1 − 62.59%)；2026H1 中报 | as-of 2026-06-30
    'cost_k': 1188.07,
    # 归母 /（锂+钾毛利）；2026H1 中报 | as-of 2026-06-30
    'conv_ratio': 0.674728,
    # 篮 6 周期商品 / 小盘 13%：锂腿 + 钾腿同篮——初分篮，两腿盈利是商品价函数；2026-09-20 曾按「③ 出带降篮门」改到 11% 的那一篮，2026-10-04 按步 1c 同口径对带回带、降篮撤销（A10；真源 `eval/lib/gordon.py BASKET_R`）；零增长 → 1/r = 7.69×；被推翻的 11% 只作「对照坐标（被推翻的降篮）」行 | as-of 2026-10-04
    'r_perp': 0.13,
    # FY2027E 共识 EPS（LB 20 家，区间 1.92–2.80）；**只作交叉**（扣现金收益后经营 2.396 × 1/r + 现金 5.60 = 24.04）与对账门坐标；2026E → 27E 增速 11% < 20% → H 窗口不成立；共识量 ≤ 名牌（A5 核对） | as-of 2026-09-18
    'eps_fy27_cons': 2.47,
    # 同等盈利带原始下沿：TTM 归母 ∈ 118 亿 ±20% 的 14 个月（2022-09→2023-03 / 2023-09→10 / 2026-05→09）内 LB PE 周点最低（2023-03-26），整股口径；**护栏（③）用经营口径、步 1c 同口径值**：价扣当时每股超额现金、EPS 扣当时现金税后收益后 7.53，再扣除带期已公告、今天已进底牌的 4 万吨项目后 7.06（eval 由下方 `proj_*` / `band_*` 行复算）；13% 下 7.69× 入带（A10 / A11） | as-of 2026-09-20
    'pe_same_min': 7.91,
    # 同等盈利带上沿（2026-05-03 点），整股口径；经营口径 18.14（eval 由 `band_max_*` 复算）；整股中位 10.39、事实口径月末经营中位 9.90；**护栏，不入公式** | as-of 2026-09-20
    'pe_same_max': 20.16,
    # 步 1c：4 万吨/年基础锂盐一体化项目名牌（吨/年，已含在 `vol_li_plan` 内）；公告 2022-038（2022-05-27） | as-of 2022-05-27
    'proj_vol': 40000.0,
    # 步 1c：该项目公告总投资 708,157.40 万元（元）；2022 年末在建工程 0.044 亿，带期几乎全额待投；2026H1 修订预算 60.83 亿只作敏感性 | as-of 2022-05-27
    'proj_capex': 7081574000.0,
    # 步 1c：带期股本 = FY2022 归母 155.68 亿 ÷ EPS 2.9318（LB 年报，IS 隐含）；只用于把项目价值换成带期每股 | as-of 2022-12-31
    'shares_band': 5310183669.0,
    # 步 1c：LB 周点下沿（`pe_same_min`，2023-03-26 周）对应收盘，2023-03-24；本票带日期的历史价（Longbridge 日 K） | as-of 2023-03-24
    'band_lb_close': 22.75,
    # 步 1c：2023-03-26 → 预计投产日 2024-12-31（2022 年报「预计 2024 年底建成投产」）的年数 | as-of 2023-03-31
    'band_lb_cod_yrs': 1.769,
    # 步 1c 披露变体：事实口径下沿（2023-10 月收盘 ÷ 滞后 TTM EPS 2023Q2 2.162）；只披露 | as-of 2023-10
    'band_fact_pe': 7.83,
    # 步 1c 披露变体：2023-10 月收盘；本票带日期的历史价（Longbridge 月 K） | as-of 2023-10-31
    'band_fact_close': 16.93,
    # 步 1c 披露变体：2023-10-28 → 2024-12-31 的年数 | as-of 2023-10
    'band_fact_cod_yrs': 1.177,
    # 步 1c 披露变体：剔 FY22 预告月后 LB 周点下沿（2023-09-24）；只披露 | as-of 2023-09-24
    'band_ex_pe': 8.28,
    # 步 1c 披露变体：2023-09-22 收盘；本票带日期的历史价（Longbridge 日 K） | as-of 2023-09-22
    'band_ex_close': 17.48,
    # 步 1c 披露变体：2023-09-24 → 2024-12-31 的年数 | as-of 2023-09
    'band_ex_cod_yrs': 1.27,
    # 经营口径：LB 下沿点当时可见报告（2022Q3）的每股超额现金 =（净现金 83.04 − 应付股利 0.13 亿）× 当时归母份额 81.05% ÷ 带期股本 53.10 亿（A11） | as-of 2022-09-30
    'band_lb_cex': 1.2655,
    # 经营口径：同点每股现金税后收益 = `band_lb_cex` × FY2022 收益率 1.98% × (1 − 7.85%) | as-of FY2022
    'band_lb_cinc': 0.02307,
    # 经营口径：事实口径点（2023Q2 报告）每股超额现金 =（167.34 − 0.11）× 87.49% ÷ 53.10 亿 | as-of 2023-06-30
    'band_fact_cex': 2.7554,
    # 经营口径：同点每股现金税后收益 = × FY2023 收益率 2.60% × (1 − 12.03%) | as-of FY2023
    'band_fact_cinc': 0.06304,
    # 经营口径：剔预告月点（2023Q2 报告，同上） | as-of 2023-06-30
    'band_ex_cex': 2.7554,
    # 经营口径：同上 | as-of FY2023
    'band_ex_cinc': 0.06304,
    # 经营口径：同等盈利带上沿点（`pe_same_max`，LB 2026-05-03 周点）对应收盘，2026-04-30；本票带日期的历史价（Longbridge 周 K） | as-of 2026-04-30
    'band_max_close': 39.29,
    # 经营口径：上沿点（2026Q1 报告）每股超额现金 =（311.75 − 应付股利 10.59 亿）× 90.94% ÷ 52.92 亿 | as-of 2026-03-31
    'band_max_cex': 5.1754,
    # 经营口径：同点每股现金税后收益 = × FY2025 收益率 1.53% × (1 − 14.22%) | as-of FY2025
    'band_max_cinc': 0.06813,
    # 锂腿永续 g2；来源层级 = **§13 商品腿 tier 默认**——锂长期实际价格漂移 ≤ −3%/yr → 0，不取负；锂生产商 4 家同业反解 2.35% 是周期端点反解、商品腿不采用，只作敏感性坐标（A3） | as-of 2026-09-18
    'g2_li': 0.0,
    # 钾腿永续 g2；来源层级 = **无同业锚·自定 0**（钾肥簇无良态读数，产能建完即止，A3），与 §13 商品腿 tier 默认一致 | as-of 2026-09-18
    'g2_k': 0.0,
    # 永续 g2 三档 flat = `g2_li` × 锂腿 M 档毛利权重 48.4% + `g2_k` × 51.6% = **0**；eval 复算（A3）；cap = min(6%, 13% − 4%) = 6% | as-of 2026-10-04
    'g2': 0.0,
    # 自身 5 年 TTM PE 实测低点（2023-06）；LB valuation history；**与分子不同基**（印在 2023Q1 TTM 143 亿上），只披露，护栏改 `pe_same_*`（A3） | as-of 2026-09-01
    'pe_own_min': 7.24,
    # 自身 5 年 TTM PE 实测高点（2021-10，重整后 TTM 30 亿）；**只披露**，不入公式 | as-of 2026-09-01
    'pe_own_max': 43.5,
    # 资产地板倍数 = 自身 5 年实测 PB 谷底（LB PB 序列 2025-06 月点；A4）；**只披露不 max()**（§13）——L = 盈利情景 18.12，地板 20.03 落在 [L, M] 内作坐标进表2 | as-of 2026-09-18
    'pb_floor': 2.22,
}
BASKETS = {"r_perp": 6}

REQUIRED = [
    "shares", "bps", "equity_nci",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_li", "vol_li_plan", "vol_li_h1", "cost_li",
    "r_disc", "n_disc",
    "kcl_price_l", "kcl_price_m", "kcl_price_h",
    "vol_k", "cost_k",
    "conv_ratio",
    "eps_fy26_cons", "parent_h1_26",
    "net_cash_ext_h1", "div_declared", "c_ex", "cash_yield", "tax_eff", "payout_op", "payout_paid",
    "r_perp", "axis_g2_li", "g2_li", "g2_k", "g2",
    "pe_same_min", "pe_same_max", "pe_own_min", "pe_own_max", "pb_floor",
    "proj_vol", "proj_capex", "shares_band",
    "band_lb_close", "band_lb_cod_yrs", "band_lb_cex", "band_lb_cinc",
    "band_fact_pe", "band_fact_close", "band_fact_cod_yrs", "band_fact_cex", "band_fact_cinc",
    "band_ex_pe", "band_ex_close", "band_ex_cod_yrs", "band_ex_cex", "band_ex_cinc",
    "band_max_close", "band_max_cex", "band_max_cinc",
    "eps_fy27_cons",
]

def excess_cash(inp: dict[str, float]) -> tuple[float, float]:
    """(parent share, parent-share C_ex in 元): extended net cash − declared dividend − anchor 0."""
    equity = inp["bps"] * inp["shares"]
    share = equity / (equity + inp["equity_nci"])
    return share, (inp["net_cash_ext_h1"] - inp["div_declared"]) * share


def scenario(inp: dict[str, float], tag: str, c_inc: float, op_equity: float,
             r_disc: float | None = None, li_tag: str | None = None) -> dict[str, float]:
    """One tier; `li_tag` overrides the lithium rung only (the H pass-by's「mix」world)."""
    li = inp[f"li2co3_{li_tag or tag}"]
    kcl = inp[f"kcl_price_{tag}"]
    rd = inp["r_disc"] if r_disc is None else r_disc
    disc = (1.0 + rd) ** (-inp["n_disc"])
    gp_li = disc * inp["vol_li_plan"] * (li * inp["realization_li"] - inp["cost_li"])
    gp_k = inp["vol_k"] * (kcl - inp["cost_k"])
    gp = gp_li + gp_k
    parent = gp * inp["conv_ratio"]
    e_op = parent - c_inc  # A11: after-tax income on the excess cash comes off every tier
    return {
        "gp_li": gp_li,
        "gp_k": gp_k,
        "gp": gp,
        "parent": parent,
        "eps": parent / inp["shares"],
        "e_op": e_op,
        "eps_op": e_op / inp["shares"],
        "ronic": e_op / op_equity,
    }


def window_ps(inp: dict[str, float], s: dict[str, float], c_inc: float, r: float, g: float) -> float:
    """Window distributable profit per share for one tier (A12, valuation-rules「经营价值与超额现金」③).

    The lithium leg's Gordon value sits at t_n = 2027-01-01 (τ = `n_disc` years after the
    2026-06-30 balance sheet); the profit earned inside that window and not yet booked --
    FY2026E consensus parent profit − 1H26 actual − half a year of after-tax excess-cash
    income (numerator basis) -- × (1 − b), b = g / RONIC (0 for g ≤ 0), counts only for the
    lithium leg's share (M-tier-style GP weight at t_n; the potash leg runs from today and is
    not time-shifted, so adding its share would count it twice), discounted τ/2 at r.
    No window when τ = 0.
    """
    tau = inp["n_disc"]
    if tau <= 0:
        return 0.0
    prof = max(0.0, inp["eps_fy26_cons"] * inp["shares"] - inp["parent_h1_26"] - c_inc / 2.0)
    gp_li_tn = s["gp_li"] * (1.0 + r) ** tau  # lithium GP at t_n (undo the τ discount)
    w_li = gp_li_tn / (gp_li_tn + s["gp_k"])
    b = max(0.0, g / s["ronic"])
    return prof * w_li * (1.0 - b) / inp["shares"] / (1.0 + r) ** (tau / 2.0)


def value(inp: dict[str, float], s: dict[str, float], c_inc: float, cps: float, r: float, g: float,
          pe: float | None = None) -> float:
    """Per-share value today: operating EPS × PE + excess cash per share + window (A11 / A12)."""
    pe = perpetual_pe(g, s["ronic"], r) if pe is None else pe
    return s["eps_op"] * pe + cps + window_ps(inp, s, c_inc, r, g)


def passby_op(s_h: dict[str, float], s_mix: dict[str, float], r: float, g: float) -> float:
    """Operating value per share of the H tier with the lithium rung passing by (A12).

    One year of H-world operating earnings (× payout at g), then the「mix」world (lithium at
    the M rung, potash still at its H rung) valued one year on, all discounted one year at r.
    """
    after = s_mix["eps_op"] * perpetual_pe(g, s_mix["ronic"], r) * (1.0 + g)
    return (s_h["eps_op"] * payout(g, s_h["ronic"]) + after) / (1.0 + r)


def ladder(inp: dict[str, float], c_inc: float, cps: float, op_equity: float, r: float, g: float,
           r_disc: float | None = None) -> tuple[float, float, float]:
    """L / M / pass-by H (A12) for one (inputs, r, g) set; every printed triple goes through here."""
    s = {t: scenario(inp, t, c_inc, op_equity, r_disc=r_disc) for t in ("l", "m", "h")}
    mix = scenario(inp, "h", c_inc, op_equity, r_disc=r_disc, li_tag="m")
    h = passby_op(s["h"], mix, r, g) + cps + window_ps(inp, s["h"], c_inc, r, g)
    return value(inp, s["l"], c_inc, cps, r, g), value(inp, s["m"], c_inc, cps, r, g), h


def project_value(inp: dict[str, float], r: float, cod_yrs: float) -> float:
    """Step 1c: the 4万吨 project at a band point, on this ticker's ruler at basket r.

    M-tier lithium unit GP × conv_ratio, nameplate δ = (1+r)^-1 as in the base,
    capitalised at 1/r (g = 0) at the expected COD, discounted cod_yrs back to
    the band point; the announced capex, spread evenly to COD, comes off at its
    mid-point.
    """
    unit_np = (inp["li2co3_m"] * inp["realization_li"] - inp["cost_li"]) * inp["conv_ratio"]
    v_cod = inp["proj_vol"] * unit_np / r / (1.0 + r)
    return v_cod * (1.0 + r) ** -cod_yrs - inp["proj_capex"] * (1.0 + r) ** -(cod_yrs / 2.0)


def band_point_op(inp: dict[str, float], r: float, point: tuple) -> tuple[str, float, float, float]:
    """(tag, raw PE, operating PE, operating PE with the 4万吨 project stripped) at basket r.

    Operating PE = (close − then C_ex per share) ÷ (then EPS − then after-tax cash
    income per share); then EPS = close ÷ raw PE (the band's own earnings basis).
    """
    tag, pe_k, px_k, yrs_k, cex_k, cinc_k = point
    px, pe_raw = inp[px_k], inp[pe_k]
    e_op = px / pe_raw - inp[cinc_k]
    pe_op = (px - inp[cex_k]) / e_op
    v_ps = project_value(inp, r, inp[yrs_k]) / inp["shares_band"] if yrs_k else 0.0
    return tag, pe_raw, pe_op, (px - inp[cex_k] - v_ps) / e_op


TICKER = '000792.SZ'
# The explicit valuation runner binds code, content and shared inputs.
BASELINE_INPUT_FINGERPRINT = 'b684d4a4064e1af9f8fca0f865798f6bc8d2871ceba19778bb9ae0ebcf22612a'
# These hashes only detect changes to these inputs; they are not approval or a
# complete dependency/version binding for publication.
BASELINE_AXIS_SOURCE = '240d2f3ac34a736b353220f3b0ff29be1c3ca9bb34bcf5411e0f2ec185bc0119'
BASELINE_LIBRARY_SOURCES = {
    'gordon.py': '375db9668f63d268de2b3c57d98582b249d476a647cfdb964fbde84d781cd090',
}
# Original H1 calibration paired realised ASP with the then-axis 150,000 CNY/t
# reference; this fixed historical proxy does not follow future axis scenarios.
H1_LITHIUM_REFERENCE_CNY_PER_TONNE = 150_000

def _evaluate(inp: dict[str, float], axis: dict, axis_digest: str, libraries: dict) -> dict:
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        raise ValueError(f"missing inputs {missing}")
    if any(inp[key] != value for key, value in axis.items()):
        raise ValueError("lithium axis inputs differ from the shared axis")
    baskets = dict(BASKETS)
    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    if not (inp["kcl_price_l"] < inp["kcl_price_m"] < inp["kcl_price_h"]):
        errors.append("kcl ladder violated")
    # Gordon inputs (valuation-rules「§r 篮子」): r is the named basket's value,
    # the ramp discount is the same basket r (A10), every g under g_cap(r), r − g
    # off the pole, the axis row referenced verbatim (not adopted, A3), no p_* field.
    r = inp["r_perp"]
    if "r_perp" not in baskets:
        errors.append("r_perp: no basket in BASKETS (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} != r_perp={r} (A10: nameplate ramp discount = basket r)")
    for k in ("axis_g2_li", "g2_li", "g2_k", "g2"):
        errors += check_g_cap(inp[k], r, k)
    if r - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {r - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")

    # A11 excess cash: parent share of (extended net cash − declared dividend − anchor 0).
    equity = inp["bps"] * inp["shares"]
    share_p, c_ex = excess_cash(inp)
    if abs(c_ex - inp["c_ex"]) > 1e6:
        errors.append(f"c_ex {inp['c_ex']:.4e} != (net_cash_ext_h1 − div_declared) × parent share {c_ex:.4e}")
    if c_ex < C_EX_TRIGGER * equity:
        errors.append("c_ex below 15% of parent equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1.0 - inp["tax_eff"])
    cps = c_ex / inp["shares"]
    op_equity = equity - c_ex
    if errors:
        raise ValueError("; ".join(errors))

    # Regression guard (Formula「校验」): the bridge must reproduce the half-year
    # it was calibrated on before it is trusted on the axis deck.
    gp_guard = (
        inp["vol_li_h1"] * (H1_LITHIUM_REFERENCE_CNY_PER_TONNE * inp["realization_li"] - inp["cost_li"])
        + inp["vol_k"] * (inp["kcl_price_m"] - inp["cost_k"])
    )
    parent_guard = gp_guard * inp["conv_ratio"]
    if abs(parent_guard / H1_PARENT_X2 - 1.0) > GUARD_TOL:
        errors.append(
            f"regression guard: H1 vol × historical lithium reference × H1 ASP gives {parent_guard / YI:.2f}亿 "
            f"vs 2 × H1 parent {H1_PARENT_X2 / YI:.2f}亿"
        )

    S = {t: scenario(inp, t, c_inc, op_equity) for t in ("l", "m", "h")}

    # --- Gordon multiples ------------------------------------------------------
    # One flat g2 = lithium tier default × M-tier lithium GP weight + potash leg
    # × g2_k (both 0 under §13 commodity legs); g = 0 puts every tier at 1/r.
    w_li = S["m"]["gp_li"] / S["m"]["gp"]
    g2_blend = w_li * inp["g2_li"] + (1.0 - w_li) * inp["g2_k"]
    if abs(inp["g2"] - g2_blend) > 1e-4:
        errors.append(f"g2={inp['g2']} vs blended g2 {g2_blend:.5f}")
    for t in S:
        S[t]["pe"] = perpetual_pe(inp["g2"], S[t]["ronic"], r)
        S[t]["win"] = window_ps(inp, S[t], c_inc, r, inp["g2"])
        S[t]["px"] = S[t]["eps_op"] * S[t]["pe"] + cps + S[t]["win"]
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): operating PE_M against the operating same-earnings
    # band, floor = the LB low with the 4万吨 project stripped (step 1c).  Out of
    # band is the ③ out-of-band flow (A10), never fixed by twisting g or r.
    pts = [band_point_op(inp, r, p) for p in BAND_POINTS]
    top = band_point_op(inp, r, BAND_TOP)[2]
    floor_raw_op, floor_1c = pts[0][2], pts[0][3]
    if not (floor_1c <= pe_m <= top):
        errors.append(
            f"guardrail: PE_M={pe_m:.2f} outside operating same-earnings band [{floor_1c:.2f} (1c), {top:.2f}] "
            "— ③ 出带处理流程 (A10), do not twist g / r"
        )
    # The initial basket in band means ③ never fires, so the ruler MUST be the
    # initial basket (a demotion would count the project twice -- once in today's
    # nameplate, once through a lower r).
    r0 = basket_r(INITIAL_BASKET)
    s0 = scenario(inp, "m", c_inc, op_equity, r_disc=r0)
    pe_m0 = perpetual_pe(inp["g2"], s0["ronic"], r0)
    floor_1c0 = band_point_op(inp, r0, BAND_POINTS[0])[3]
    if floor_1c0 <= pe_m0 <= top and baskets.get("r_perp") != INITIAL_BASKET:
        errors.append(
            f"step 1c: initial 篮 {INITIAL_BASKET} PE_M {pe_m0:.2f} is inside [{floor_1c0:.2f}, {top:.2f}] "
            f"-> ③ not triggered, r_perp must stay 篮 {INITIAL_BASKET}"
        )
    # A4: the PB floor is disclosed, never max()-ed into L.
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["px"]
    L = scenario_L
    M = S["m"]["px"]
    # A12 H pass-by: lithium H rung one year, then the M rung; potash keeps its H rung.
    S_mix = scenario(inp, "h", c_inc, op_equity, li_tag="m")
    op_h = passby_op(S["h"], S_mix, r, inp["g2"])
    H_persist = S["h"]["px"]
    H = op_h + cps + S["h"]["win"]
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        raise ValueError(f"L<M<H violated ({L:.2f}/{M:.2f}/{H:.2f})")

    flat = [value(inp, S[t], c_inc, cps, r, inp["g2"], pe=pe_m) for t in ("l", "m", "h")]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")

    rd = basket_r(DEMOTED_BASKET)
    band_d = ladder(inp, c_inc, cps, op_equity, rd, inp["g2"], r_disc=rd)
    if any(abs(a - b) > 1e-9 for a, b in zip(ladder(inp, c_inc, cps, op_equity, r, inp["g2"]), (L, M, H))):
        errors.append("ladder() does not reproduce the base L / M / pass-by H")
    if errors:
        raise ValueError('; '.join(errors))
    sensitivity = {str(dg): ladder(inp, c_inc, cps, op_equity, r, inp['g2'] + dg) for dg in (-0.01, 0.01)}
    comparison_growth = {str(g): ladder(inp, c_inc, cps, op_equity, r, g) for g in (0.0115, 0.0135)}
    comparisons = {}
    for label, changes in (
        ('h1_volume', {'vol_li_plan': inp['vol_li_h1']}),
        ('no_timing', {'n_disc': 0}),
        ('potash_low', {'kcl_price_m': inp['kcl_price_l'], 'kcl_price_h': inp['kcl_price_l']}),
    ):
        comparisons[label] = ladder({**inp, **changes}, c_inc, cps, op_equity, r, inp['g2'])
    rate_sensitivity = {str(rr): ladder(inp, c_inc, cps, op_equity, rr, inp['g2'], r_disc=rr)
                        for rr in (r - 0.005, r + 0.005, 0.11, 0.15, 0.10)}
    recovery = {}
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g_measured = (np1 / np0) ** (1.0 / n) - 1.0
        g_lm = (S['m']['eps_op'] / S['l']['eps_op']) ** (1.0 / n) - 1.0
        pe_measured = recovery_two_stage_pe(g_measured, n, inp['g2'], S['m']['ronic'], r)
        pe_lm = recovery_two_stage_pe(g_lm, n, inp['g2'], S['m']['ronic'], r)
        recovery[label] = {'growth_measured': g_measured, 'pe_measured': pe_measured,
                           'value_measured': S['l']['eps_op'] * pe_measured,
                           'growth_lm': g_lm, 'pe_lm': pe_lm,
                           'value_lm': S['l']['eps_op'] * pe_lm}
    keep = 1.0 - inp['g2'] / S['m']['ronic'] - inp['payout_paid']
    retained_per_share = keep * S['m']['eps_op']
    window_pe = two_stage_pe(0.17, 3, inp['g2'], S['m']['ronic'], r)
    input_changed = input_basis_changed(inp)
    basis_changed = input_changed or axis_digest != BASELINE_AXIS_SOURCE or libraries != BASELINE_LIBRARY_SOURCES
    return {'ticker': TICKER, 'currency': 'CNY', 'inp': inp,
            'valuation_as_of': None, 'historical_financial_basis_as_of': '2026-06-30',
            # Full source and runtime reconciliation is not yet available.
            'framework_as_of': None, 'historical_research_as_of': '2026-10-20',
            'basis_changed': None, 'partial_basis_changed': basis_changed,
            'anchors': dict(zip('LMH', (L, M, H))),
            'candidate': None, 'option': None,
            'baskets': baskets, 'equity': equity, 'share_p': share_p, 'c_ex': c_ex,
            'c_inc': c_inc, 'cps': cps, 'op_equity': op_equity, 'parent_guard': parent_guard,
            'S': S, 'w_li': w_li, 'g2_blend': g2_blend, 'pts': pts, 'top': top,
            'floor_raw_op': floor_raw_op, 'floor_1c': floor_1c, 's0': s0, 'pe_m0': pe_m0,
            'floor_1c0': floor_1c0, 'floor': floor, 'scenario_L': scenario_L, 'S_mix': S_mix,
            'op_h': op_h, 'H_persist': H_persist, 'L': L, 'M': M, 'H': H, 'A': A, 'B': B,
            'flat': flat, 'rd': rd, 'band_d': band_d, 'sensitivity': sensitivity,
            'comparison_growth': comparison_growth, 'comparisons': comparisons,
            'rate_sensitivity': rate_sensitivity, 'recovery': recovery,
            'branch_notes': check_branch(inp['g2'], S['m']['ronic'], r, inp['payout_op'], 'g2'),
            'retained_ratio': keep, 'retained_per_share': retained_per_share,
            'retained_present_value': retained_per_share / (r - inp['g2']),
            'window_pe': window_pe,
            'window_value': S['m']['eps_op'] * window_pe + cps + S['m']['win']}

LITHIUM_INPUTS = ('li2co3_l', 'li2co3_m', 'li2co3_h', 'axis_g2_li')


def calculate(context):
    if context['rate_inputs'] is not None:
        raise ValueError('rate inputs not supported for this ticker')
    axis = {key: context['axes']['lithium'][key] for key in LITHIUM_INPUTS}
    return _evaluate({**INPUTS, **axis}, axis, context['axis_versions']['lithium'], context['libraries'])


def input_basis_changed(inp):
    numeric = {key: float(value) for key, value in inp.items()}
    bundle = {'inputs': numeric, 'baskets': BASKETS}
    digest = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return digest != BASELINE_INPUT_FINGERPRINT

# Historical assumptions and evidence retained from the original framework:
# - **属性 A — 双驱动分腿**：锂挂 `_AXIS.lithium-carbonate`；钾用票内 `kcl_price_l/m/h`（正交；直至另开钾轴）。
# - **属性 B — 成本曲线左侧**：低现金成本进 `cost_li` / `cost_k`，不加资产重估腿。
# - **属性 C — 周期陷阱**：H1 年化盈利抬高后 TTM PE 看似「便宜」；主尺倍数由 Gordon 生成，禁止用高峰年化 PE 再压倍数定「深度折价」。
# - **属性 D — 倍数由 Gordon 生成，三档 g flat = 0，三档倍数恒等 1/r**（A2e-5b，valuation-rules「永续增长口径」）：整公司单 Gordon（不分腿 SOTP），两腿同归篮 6 → r = 13%（A10）。每档 \(PE_x=(1-g2/RONIC_x)/(r-g2)\)，\(RONIC_x = E^{op}_x / (bps \times shares - C_{ex})\)（经营利润 ÷ 经营股权，A11）；g2 = **0** 三档共用 = §13 商品腿 tier 默认（锂长期实际价格漂移 ≤ −3%/yr 不取负；钾肥簇无良态读数 → 无同业锚·自定 0 =「产能建完即止」），锂同业横截面反解 2.35% 撤回、只作敏感性坐标（A3）；锂轴「永续 g2」行 6% 引用但不采用。**为什么 flat 而不是反向**：轴 L 10.3 万是 2028 过剩底（BMI 11.3 / 高盛 8.5 万两源之间，轴「换算口径」2026-10-12）、高于成本曲线 p90 6.5 万，轴 §1 明示 2024–25 崩盘区（6–8 万，本票 FY2024 归母 46.6 亿的谷底年）不进 L——L 是可持续的低位 regime 而非「跌下去必弹回」的谷底年；按 valuation-rules「谷底档」跑本票实测回归（FY2024 → FY2025，A9）反而把 L 推过 M 或塌进 M，说明 L 世界不含回归段；H 是 2026 平台延续，但按轴只维持一年、之后锂回 M 档（路过，A12）。故三档同 g2；g = 0 下 RONIC 不进倍数，三档皆 **7.69×**（RONIC 45.5% / 62.4% / 77.7% 全在 r 13% 之上，单调区），档差全部来自分子（锂轴价 + 钾票内价）。护栏是**经营口径同等盈利带** [7.06, 18.14]（TTM 归母 ∈ 118 亿 ±20% 的月份，与分子同基；每个带点的价扣当时每股超额现金、EPS 扣当时现金税后收益，经营口径原始下沿 7.53、整股原始 7.91；下沿再按步 1c 扣除带期已公告、今天已进底牌的 4 万吨项目），7.69× 在带内；越出走「③ 出带处理流程」，**MUST NOT** 调 g / 拧 r。自身 TTM PE 与盈利强反向的实证（2023 盈利峰 8.8× / 2024–25 盈利谷 13.9–18.7×）说的是市场把**真正的盈利谷底**当过渡——那是 `deep_discount` 世界的读法，与轴 L 的 regime 分子无关。
# - **属性 E — 账上现金多，单列为超额现金**（A11）：2021 年重整后净负债 28 亿 → 2026H1 扩展口径净现金 340 亿，主要是留存利润堆出来的（FY2021–25 无现金分红：母公司未分配利润为负、法定不能分配；能分时做过 14.99 亿回购并注销）。扣已宣派未付股息、按归母份额取 296.56 亿（每股 5.60）面值单列，经营利润与 RONIC 都扣掉这笔现金及其收益。
# | A1 | **锂价 = `_AXIS.lithium-carbonate`**（10.3/12.0/15 万，2027–28 deck；锂量按 A5 取 2027 run-rate 名牌 × δ，价量同年） | `active` | 轴挂载名单 | `li2co3_*` |
# | A2 | **钾价三档票内**：L **2500** / M **3175.81**（H1 ASP）/ H **3500** | `active` | M=段收入/销量；L≈2025 初青海 60% 粉到站低位邻域；H≈2025–26 春耕高位可复现（低于 ~3700 尖峰） | `kcl_price_*` |
# | A3 | **倍数由 Gordon 生成、三档 g flat = 0；护栏 = 经营口径同等盈利带 [7.06（步 1c 同口径）, 18.14]，自身 5 年 TTM PE 带 7.24–43.5 降为披露**（属性 D）：r = 篮 6 13%（A10）；g2 0（§13 商品腿 tier 默认）；RONIC 按档 = 经营利润 ÷（`bps × shares` − `c_ex`），g = 0 下不进倍数 | `active` | **A2d 六维**（2026-09-14 取证，2026-09-20 按篮子 r 重读）：① **研报共识**：LB 20 家 FY2026E 2.22（1.62–2.48）/ FY2027E 2.47（1.92–2.80）；卖方一致 TP 44.18（7 家，2026-09-11）↔ 隐含 r 5.0%，街按成长票给它；Wisburg 无盐湖个股倍数口径（**待补**）。② **EPS**：M 档 EPS 2.208 ≈ FY26E 共识 2.22（−1%）、低于 FY27E 中位 11%（M 已按 2027 run-rate × 2027–28 价格 deck 构造，差在价格 deck 与 δ，不是量，A5）；2026E → 27E 增速 11% < 20% 门槛 → 无 g1 窗口（强行按 2025–28 CAGR 17% / n 3 叠在 M 上 → 28.59，是价格 deck 双计，只进敏感性）。③ **RONIC（经营口径）**：按档 45.5% / 62.4% / 77.7%，三档 − 13% ≥ +32pp 全在单调区（账面 ROE 18.1% / 24.5% / 30.3% 只披露）；锂同业前瞻 ROE SQM 15.2 / PLS 18.3 / IGO 19.9 / 中矿 31.2。④ **PEG**：不适用（周期价格事件）。⑤ **交叉约束（护栏）**：5 年 TTM PE 带 7.24–43.5（LB `valuation --history pe --range 5`）与分子**不同基**——下沿 7.24（2023-06）印在 2023Q1 TTM 143 亿上、上沿 43.5 印在 2021-10 重整后 TTM 30 亿上；护栏改用同等盈利带 [`pe_same_min`, `pe_same_max`] = [7.91, 20.16]（TTM 归母 ∈ 118 亿 ±20% 的 14 个月，中位 10.39），步 1c 扣除带期已公告的 4 万吨项目后下沿 7.40、中位 9.80（A10），7.69× 在带内；同口径下沿 7.40× 在 g = 0 下对应 r 13.5%，只作阅读。**2026-10-15 改经营口径**（A11）：每个带点的价扣当时每股超额现金、EPS 扣当时现金税后收益 → 带 [7.53, 18.14]（事实口径月末中位 9.90），步 1c 后下沿 **7.06**，g = 0 下对应 r 14.2%，只作阅读；7.69× 在带内。⑥ **档位可比性**：L/M 0.80 / H/M 1.08（H 锂腿路过），见 Outputs。**g2 来源层级**：锂腿 = **§13 商品腿 tier 默认 0**——通胀 + 长期实际价格漂移（≤ −3%/yr）→ 0，不取负；锂生产商 4 家良态横截面反解 **2.35%**（SQM 1.05 / PLS 6.77 / IGO 3.64 / 中矿 −2.69，yfinance 2026-09-14，（历史本地资料，未在本次迁移重新核实））是周期端点反解、商品腿不采用，只作敏感性坐标（合成 1.15% → 18.94 / 23.77 / 25.66，H 按路过）；轴行 6% 截断值引用、不采用。钾腿 = **无同业锚·自定 0**——钾肥簇（NTR / MOS / IPI / K+S / ICL / 亚钾国际 / 东方铁塔，`potash_peer_g2_2026-09-14.json`）只有 MOS −8.8% / K+S −3.5% 两家良态且前瞻 ROE 3.7–4.3%（谷底年分母，读数病态），其余 ROE≈r 或 g ≥ ROE 不良条件，tier 1 不成立；Wisburg 亦无「钾肥长期需求增速」具名口径。M 档权重 48.4% / 51.6% → g2 **0**（eval 复算）。1pp 敏感性：M 21.34 / 23.59；钾腿若给 2.6%（借金铜簇量级，仅试算）→ g2 1.35%、M 24.01 | `r_perp` / `axis_g2_li` / `g2_li` / `g2_k` / `g2` / `pe_same_min/max` / `pe_own_min/max` |
# | A4 | **无 NAV / 不叠 asset_play；PB 地板 = 自身 5 年实测 PB 谷底 2.22，只披露不 max()**（地板 20.03 > 情景 L 18.12，落在 [L, M] 内、比 M 22.51 低 2.48） | `active` | 5 年 PB 实测谷底 2.22 仍远高于 1，市场已定价资源。地板来源：LB 5 年 PB 序列 min **2.22**（2025-06 月点；2024 min 2.24）→ floor 20.03；情景/M = 0.80 ≥ 0.3，盈利尺未失效。不随 r 变的资产数不塞进随 r 缩的盈利尺——超额现金单列后（A11），13% 尺下自身 PB 谷底落在 L 与 M 之间，读作「市场在账面谷底给的价低于 M 档经营价值加现金」（被推翻的篮 5 尺下它 ≈ L）。**L 的本票价格坐标**：2025-04-07 印过年内低 **14.84**（对应 PB ≈ 2.2、FY2024 归母谷底 × TTM PE ~17），落 `deep_discount`（低于 L 3.28；FY2024 年末每股超额现金约 4.1 元，今天 5.60）；L 18.12 的盈利情景是「2028 过剩底 10.3 万 × 名牌 9.8 万吨 + 钾 2500、零增长」，仍高于 FY2024 实际（锂 6–8 万崩盘区 × 蓝科 4.1 万吨）——那一年属 `deep_discount` 的解释材料，不是 L | `pb_floor`；Outputs `floor` 披露行；表2 `neutral` 行坐标 |
# | A5 | **锂量 = 已建成名牌 9.8 万吨 × δ，δ=(1+r)^{-τ}（r = 篮子 r；τ 0.5 = 时点对齐，A12，2026-10-16 取代原「折 1 年」）；钾量 = H1 销量 × 2，不折现**；名牌之外的扩产（20 万吨级愿景）不进底牌、不构成候选带 | `confirmed`（产能核对 2026-09-20） | 中报：4 万吨项目「全面量产」、五矿 1.8 万吨 2026Q1 并表（碳酸锂 1.5 + 磷酸锂 0.2 + 氢氧化锂 0.1）、总产能 9.8 万吨；H1 产量 4.94 万（年化 9.88 ≈ 名牌）、销量 3.91 万（库存 +1.03 万，IR 2026-08-07 称「产能释放后的正常库存」）。名牌是**已建成并在产**的物理产能，与 `9696.HK` CGP3 同构，原折 1 年等销量追上产量，2026-10-16 起按时点对齐只折到分子年初（τ 0.5，A12）；钾销 224.74 万（产 168.17，去库存），产能 530 万（察尔汗 500 + 五矿 30）作护栏。**产能核对（2026-09-20）**：① 2026 中报在建工程期末 **5.42 亿**（（历史本地资料，未在本次迁移重新核实） 附注 17）——锂相关只有 4 万吨项目尾款 0.73 亿、沉锂一车间蒸发浓缩改造 0.35 亿、一万吨碳酸锂装置改造 0.01 亿，**没有任何新建锂盐产能项目**，也无五矿盐湖二期；钾无新增（500 万吨工业盐项目 0.04 亿是盐不是钾）；② IR 记录 2026-06-16 原话：「公司现有在产锂盐产能包含新建 4 万吨锂盐项目、蓝科锂业、五矿盐湖板块，合计产能 9.8 万吨，**其余锂相关规划项目未建设**」；「到 2030 年逐步落地千万吨级钾肥、二十万吨级锂盐」是「**公司控股股东中国盐湖规划**」；比亚迪 3 万吨合资未建（同日问答）；刚果（布）BMB 钾盐一期 200 万吨「尚处于初级阶段」（IR 2026-04-20）；③ 公司「十五五」规划纲要（2026-08-25）只有「有序扩张锂盐产能」的方向句，无数字、无投产日；④ 卖方：开源 2026-01-07 产能表——碳酸锂现有设计 9.5 万吨（权益 6.82）、比亚迪 3 万吨「规划，尚未建设」、20 万吨 = 2030 规划，2026E → 27E 营收 +11.8%（（历史本地资料，未在本次迁移重新核实））；国信 2026-04-01 年报点评 2027E / 2028E 营收 +4.9% / +4.7%、归母 103.9 / 110.7 亿（`guoxin_2026-04-01.txt`）；华源 2025-05-29 首次覆盖 2025–27 锂销量 **4.3 / 6 / 8 万吨**（当时名牌 8.1，未含五矿，（历史本地资料，未在本次迁移重新核实））——三家没有一家把名牌外的量放进 2027 / 2028。**结论**：无已批 / 在建的名牌外锂产能 → 无候选带；共识 2027E 的量 ≤ 名牌，M 对 FY27E 共识的 −11% 是价格 deck 与 δ 的差、不是量。`待补`：开源 / 国信 2027–28 锂销量的明文数字（两份报告只印营收 / 归母，未拆量）；LB FY2028E 共识 EPS（CLI 只回当年 FY 序列） | `vol_li_plan` / `n_disc` / `vol_k` |
# | A6 | **`conv_ratio` = H1 归母 / 两腿毛利**（嵌税·NCI·费用） | `active` | 归母 61.685 /（锂毛利 46.750 + 钾毛利 44.673）；五矿 49% NCI 不单列 | `conv_ratio` |
# | A7 | **锂 realization = H1 ASP ÷ 旧轴 M 15 万**（比例外推，M 档实现价不再等于 H1 ASP） | `active` | 14.326 万 ÷ 15.0 万 | `realization_li` |
# | A8 | **单位成本钉 H1 毛利率反推** | `active` | 锂 cost=ASP×(1−83.46%)；钾 cost=ASP×(1−62.59%)≈1188（券商同口径） | `cost_*` |
# | A9 | **谷底档规则对本票的结果：L 世界是低位 regime，不走回归段**（valuation-rules「谷底档」）。本票自己走过的谷底→回归：Longbridge 年报归母 FY2024 **46.63 亿**（2024–25 锂崩盘年）→ FY2025 **84.76 亿**，n = 1、+81.8%（（历史本地资料，未在本次迁移重新核实），2026-09-14 拉取）；更早的 FY2019 −458.6 亿是破产重整年、不可比。两种用法都不能作 L（篮 6 13%、g2 0 下由 eval 复算；2026-10-15 起经营口径：两年各扣自己当年超额现金的税后收益 → FY2024 **43.10 亿** → FY2025 **81.05 亿**，+88.1%，坐标再加今天的每股超额现金 5.60 与 L 档锂腿窗口 0.55，A11 / A12）：(i) 实测 CAGR 套在 L 经营分子 1.556 上 → `recovery_two_stage_pe(88.1%, 1, 0, RONIC_M 62.4%, 13%)` = 13.69× → **27.45 > M 22.51**（那轮回归是锂价 V + 4 万吨项目投产，不是纯价格回归）；(ii) 只取实测年数、幅度取 L→M（g1 37.2%）→ 10.22× → **22.06 ≈ M（L/M 0.980，塌陷）**。裁决 ⑤→②：形状不对回分子——轴 L 10.3 万是 2028 底（两源夹逼）、高于 p90 成本，轴 §1 明示 2024–25 崩盘区不进 L，L 是可持续 regime 而非「跌下去必弹回」的一年，故 L 分子配稳态 g2（同 M），不配回归段；「谷底回归中枢 5%」的 Gordon 式复苏 g 不用。谷底 × 1/r + 现金 + 窗口 = 经营 EPS_L × 7.69 + 5.60 + 0.55 = **18.12 = L**（g = 0 下恒等），`deep_discount` 压力坐标退化为 L 本身 | `active` | 年报序列如左；eval 打印 (i)(ii) 两个坐标与谷底 × 1/r | L 档情景倍数 = `perpetual_pe(g2, RONIC_L)` = 1/r；`deep_discount` 行 |
# | A10 | **归篮：锂腿、钾腿 → 篮 6 周期商品 / 小盘 r = 13%（初分篮——两腿盈利都是碳酸锂 / 氯化钾价格的函数，判据正向成立）；2026-09-20 的「③ 出带降篮」（→ 篮 5 大行 / 优质股份行 11%）经步 1c 推翻、撤销**；两腿同篮，分腿加总与整公司尺等价；CAPM 粗筛未做（β 0.90 对商品价函数的盈利波动失真，valuation-rules「r 篮子」已知张力），以同等盈利带替代 | `active` | **同等盈利带**：以 LB `financial-report` 季度归母滚成滞后可见 TTM（Q1 → 5 月起、Q2 → 9 月起、Q3 → 11 月起、年报 → 4 月起），取 TTM ∈ 118 亿 ±20%（94–141 亿）的月份共 **14 个月**：2022-09→10（TTM 2022Q2 115 亿）、2022-11→2023-03（2022Q3 128 亿）、2023-09→10（2023Q2 115 亿）、2026-05→08（2026Q1 104 亿）、2026-09（2026Q2 121 亿）；±12% 的配对集完全相同。原始 LB PE 周点 **min 7.91（2023-03-26）/ 中位 10.39 / max 20.16（2026-05）**；事实口径（月收盘 ÷ 滞后 TTM EPS）min 7.83（2023-10）；剔除 2023-01→03（LB 该三月已按 FY22 业绩预告 155 亿计 TTM）则 min 8.28（2023-09）。**步 1c 同口径对带（2026-10-04，valuation-rules「③ 出带处理流程」步 1c）**：2022-09→2023-10 的 9 个带月（含全部三个下沿候选点）价里含着「4 万吨/年基础锂盐一体化项目」——**公告日 2022-05-27**（公告 2022-038《关于投资新建 4 万吨/年基础锂盐一体化项目的公告》，八届十五次董事会；总投资 70.82 亿、建设期 24 个月；巨潮资讯网）；2022 年报（2023-03-31）「预计 2024 年底建成投产」、2022 年末该项目在建工程仅 0.044 亿（2022 年报摘录（本次未重验））；带月 TTM EPS 不含它（2025 年起投产、2026H1 全面量产），今天的名牌分子 9.8 万吨含它。按本票尺估：M 档锂单位毛利（12.0 万 × 0.955 − 2.37 万）× `conv_ratio` × 4 万吨 = 归母 24.5 亿/年，按 2026-10-04 构造时底牌的 δ 折 1 年（投产后的爬坡年；2026-10-16 底牌改时点对齐后此项不动，带下沿照旧）、× 1/r 在预计投产日（2024-12-31）资本化，折到带点，再减公告总投资（按建设期中点折现）；13% 下 2023-03-26 净值 **71.0 亿（1.34 元/股，市值的 6.0%）**、2023-10 1.48 元/股（8.8%）。扣除后：LB 周点下沿 7.91 → **7.40**；事实口径 7.83 → 7.08；剔预告月 8.28 → 7.52；中位 10.39 → 9.80；2026-05→09 五个月项目已在 EPS 内、不调（五矿盐湖 2026Q1 才并表、TTM 只含一两个季度，同样会抬高这几个月的倍数，但它们 ≥ 10× 不定下沿，未调）。13% 下 1/r 7.69× **≥ 全部三个同口径下沿 → 回带，③ 不触发、不降篮**（eval 机械化）。稳健性：投产日推到 2025 年底 / 2026 年中（实际全面量产）→ LB 下沿 7.48 / 7.52；按今日修订预算 60.83 亿扣资本开支 → 7.34；不扣资本开支 → 6.94——都低于 7.69；最紧的组合「剔预告月 + 投产日 2026 年中」7.69 与 1/r 持平。**经营口径重读（2026-10-15，A11）**：每个带点的价扣当时可见报告的每股超额现金（扣应付股利、按当时归母份额）、EPS 扣当时现金税后收益（`band_*_cex` / `band_*_cinc`），同一 14 个月的 TTM 经营利润仍在 M 档经营利润 112.4 亿 ±20% 内（2026-10-16 时点对齐后 M 档经营利润 115.9 亿，±20% 为 92.7–139.1 亿；2026-10-20 锂轴 M 12.0 万后 112.9 亿，±20% 为 90.3–135.5 亿，14 个月仍全在内）。LB 下沿 7.91 → 经营 **7.53**、事实口径 7.83 → 6.75、剔预告月 8.28 → 7.19、上沿 20.16 → 18.14、事实口径月末中位 10.42 → 9.90；不扣项目，经营口径原始下沿就已低于 7.69× → **不降篮不再依赖步 1c**；按原定护栏构造再扣项目，步 1c 同口径下沿 7.06（变体 6.05 / 6.48）。上面的稳健性数字与「锂轴 M 降到约 9.4 万即回带临界」都是整股口径旧值，经营口径下项目价值归零时下沿也只回到 7.53，不再有临界。**被推翻的降篮（留痕）**：2026-09-20 以原始下沿 7.91 判「13% 下 7.69× 出带 0.14–0.59 turn」，② 分子（M ≈ FY26E 共识）与 g 截顶（0 ≪ 6%）排除、1b 干净（当时预期增速 FY23E 2.949 vs FY22 实测 2.932 = +0.6%；当时 TTM ROE 52% vs 现模型 24% 的差来自 2019 重整后的分母重建，且 g = 0 下 ROE 项不生效）→ 逐档降到篮 5 9.09× 入带即停。那 0.2–0.5 turn 的差额正是 4 万吨项目在带价里的份量（1.47 元/股 ÷ 当时 LB EPS 基数约 2.88 ≈ 0.5 turn）：拿底牌单独对带，项目被读成「r 太高」，经降篮二次计入了已含项目的名牌分子。1b 核验只在 ③ 触发后才需要，今保留为历史披露。配对阈值放宽到 ±25% 时原始下沿 7.18、13% 本就入带——与步 1c 同向，降篮结论对阈值不稳的问题随之消失。街 r：无可用样本（③ 出带调研：国信 / 开源 / 华源 / 华鑫 / 高盛均 PE，无券商 DCF）。**对账门**：2026-10-04 M 对上一版 20.15 −16% < 25%；2026-10-15 超额现金单列 M 16.90 → 21.94 +30% > 25%，六坐标见 Outputs；2026-10-16 时点对齐 M 21.94 → 22.96 +4.6% < 25%（A12） | `r_perp` / `r_disc`；全公式；**复核条件**：① 同等盈利带更新出现新月份，使经营口径带（步 1c 同口径下沿 7.06 / 上沿 18.14）不再包住 7.69×；② （经营口径下已不适用：项目价值归零时下沿 7.53 仍低于 7.69）；③ 季度篮级对账（§7 规则 2）A 股篮 6 中位系统性偏离 13%——任一触发 → 重走「③ 出带处理流程」（含步 1c）；被推翻的篮 5 对照 20.37 / 25.59 / 27.61 只作坐标；篮子值 **MUST NOT** 单票修改 |
# | A11 | **超额现金单列**（valuation-rules「经营价值与超额现金」，2026-10-15 框架纠正）：扩展口径净现金 2026H1 340.13 亿 − 已宣派未付股息 11.56 亿 − 经营所需现金锚 0 = 328.57 亿（合并）；× 归母份额 90.26%（按权益比例：归母权益 477.51 ÷（477.51 + 少数股东权益 51.54）；子公司与母公司的现金分布未披露）= **296.56 亿**（每股 5.604，占归母权益 62.1% ≥ 15%）。**少数股东那部分 32.01 亿不计**：这笔钱属于子公司的少数股东（λ 证据清单里的「归属少数股东」），直接从金额里剔掉，等价于对这部分按 λ 0；利润桥 `conv_ratio` 本就是归母口径，两边一致。锚：FY2021–25（重整后一个完整周期，峰 FY2022、谷 FY2024）「扩展口径净现金 ÷ 收入」最低值为负（FY2021 净负债 28.06 亿）→ 0；FY2019–20 是破产重整期，不进窗口。类债：采矿权分期款 14.56 亿计入；合同负债 8.02 亿（主要是钾肥经销商预收）是随交付消化的普通预收，不扣；合并报表应付股利 11.56 亿（母公司报表只 0.08 亿 → 是子公司已宣派未付的股利，可能含同一控制下并入的五矿盐湖）扣。现金收益率 1.53%（FY2025）、税率 14.22%（2026H1；FY2025 是一次性递延所得税收益、税率为负，不用）→ 税后收益 **3.90 亿/年**（0.0738 元/股），三档分子同扣；RONIC 分母同扣超额现金；同等盈利带、步 1c、谷底档坐标、对账门按当时超额现金改经营口径（A3 / A9 / A10）。**λ = 1**（作用在归母份额上）：资金未受限、不在海外；五矿盐湖收购 46.05 亿 < 归母权益 20%；无具名政策性投资；近 5 年不分红是法定原因（母公司未分配利润为负），长期囤积本身不算证据。**留存拆分**（FY2021–25，经营利润合计 398.25 亿；历史各年超额现金按当年归母份额、扣当年应付股利；FY2025 用同一控制下合并重述后的数）：分红与注销式回购 3.8% / 员工持股回购 0 / 还债 19.3%（FY2020 末净负债 76.9 亿还清，合并口径近似）/ 现金积累 70.8% / 经营再投资 15.7%；来源另有现金收益 12.74 亿与其他权益变动 25.56 亿，按构造闭合；经营口径派息率 = 分红 + 现金积累 = **74.6%**（`payout_op`），低于零增长的 80% 门槛——g2 = 0 已拍板保留（valuation-rules「零增长」：存量框架已落盘的 g = 0 视为已拍板），`check_branch` 的提示只披露。经营资本（权益合计 + 扩展口径净债务）FY2022 173.5 → FY2025 174.4 → 2026H1 188.9 亿（含五矿盐湖并表）。证伪 / 重看：λ 证据清单任一项出现；超额现金被大额收购或政策性投资消耗；母公司弥补亏损后开始分红 | `active` | 2026 中报合并 / 母公司资产负债表与附注（应付股利）；年报 2021–2025；东方财富 F10 三表；（历史本地资料，未在本次迁移重新核实）、（历史本地资料，未在本次迁移重新核实） | `equity_nci` / `net_cash_ext_h1` / `div_declared` / `c_ex` / `cash_yield` / `tax_eff` / `payout_op` / `payout_paid` / `band_*_cex` / `band_*_cinc`；三档各加 5.60 |
# | A12 | **时点对齐 / 窗口 / 资金缺口 / 稳态回报 / k（valuation-rules「经营价值与超额现金」①②③④，2026-10-16 框架纠正；锚点 17.17 / 21.94 / 25.40 → 18.12 / 22.96 / 26.56，M +4.6%；2026-10-18 H 锂腿路过 → H 24.65，见 ⑤）**：① **时点对齐**——锂腿分子是「2027 run-rate」（名牌量配轴 2027–28 价），值在分子年初 t_n 2027-01-01；估值基准日 = 超额现金的资产负债表日 2026-06-30 → **τ = 0.5**，锂腿按篮子 r 13% 折半年（δ 0.9407），取代原「销量追上名牌 ≈ 折 1 年」（先还原原 1 年折现，再折 τ）；钾腿是 2026H1 当期年化，属规则边界「当期年化」，τ = 0。② **窗口可分配利润**——窗口内尚未入账的共识利润 = FY2026E 共识 EPS 2.22（LB 20 家，A3）× 股本 − 1H26 实测归母 61.69 亿 − 半年超额现金税后收益 1.95 亿（与分子同口径）= **53.84 亿**；× (1 − b)，b = g2 / RONIC = 0；只取锂腿那份（按各档锂毛利占比 L 55.4% / M 49.9% / H 53.0%，钾腿从今天起算、再加即双计）；按 1.13⁻⁰·²⁵ 折 → 每股 **0.55 / 0.49 / 0.52**。窗口按锂毛利占比拆是本票读法（规则未写分腿怎么拆；整笔加则三档各再加约 0.5，只披露）。③ **增长期资金缺口 0**：名牌 9.8 万吨已建成在产，分子年之内没有要靠现有现金出的扩产（在建工程 5.42 亿，A5）。④ **归母份额**：超额现金已按归母份额 90.26% 取（A11）；窗口用的是归母利润，不再乘。⑤ **稳态回报三段不适用（商品腿豁免）**：两腿分子由锂轴 / 钾票内价梯桥出，g2 = 0，RONIC 不进倍数；L / M 是 regime。**H 档锂腿路过（2026-10-18 用户裁定，执行锂轴「H 档是路过」）**：锂 H 价（2026 平台延续到 2027）只维持一年，之后锂腿回到 M 档世界；钾腿的票内 H 档不在锂轴上、不路过。H = [第一年 H 世界经营利润 × 派息(g2, RONIC_H) + 一年后「锂 M、钾 H」世界的经营价值 × (1 + g2)] ÷ (1 + r) + 超额现金 + H 档锂腿窗口 =（2.657 + 2.320 × 7.69）÷ 1.13 + 5.60 + 0.52 = **24.27**（原长期化读数 26.56）；g2 = 0 下钾腿价值与长期化相同，只有锂腿 10.52 → 8.23；窗口是 2026 下半年的利润，在路过年之前，不变。敏感性、对照坐标的 H 同样按路过算。⑥ **k**：本框架没有打折 k。**对照读法**：锂腿分子年初若读成「销量追上名牌」的 2027-06-30（τ 1.0，窗口一年利润含 ½ × FY27E）→ 18.33 / 22.57 / 24.35，M 几乎相同 | `active` | valuation-rules「经营价值与超额现金」①②③；`_AXIS.lithium-carbonate`「H 档是路过」段；2026-10-18 用户裁定；LB 共识 2026-09-18；2026 中报 | `n_disc`（= τ）/ `eps_fy26_cons` / `parent_h1_26`；eval `window_ps` |

# Historical method changes and prior research decisions:
#
#
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
#
# ### 2026-09-20
#
# - v2 切换（篮子 r）：L/M/H v1 20.03（地板）/ 23.98 / 29.15 → 14.48 / 20.15 / 24.28，zone `neutral` → `stretched`（P/H 1.05；切点 A / B 22.01 / 26.57 → 17.31 / 22.22）；篮子：锂腿 + 钾腿同归篮 5 11%（初分篮 6 周期商品 13%，两腿盈利都是商品价函数、判据成立；13% 下 1/r 7.69× 低于自身同等盈利带下沿 7.91×，② 分子与 g 截顶排除、1b 核验干净 → 按「③ 出带降篮门」逐档降到第一个入带的篮 5 9.09× 即停，市场证据降篮、非纠正归篮，A10），`r_perp` / `r_disc` 0.10 → 0.11（δ 0.909 → 0.901）；g2 1.15%（锂同业反解 2.35% × 锂腿权重 + 钾 0）→ 0（§13 商品腿 tier 默认，商品腿不走同业反解），倍数 10.57 / 10.77 / 10.86×（ROE 机械档差）→ 三档 9.09× flat；PB 2.22 地板 20.03 改只披露、不再 max()（v1 `L = max(情景 16.91, 地板)` 由地板胜出；现 L = 情景 14.48，地板 ≈ M）；护栏由自身 5 年 TTM PE 带 [7.24, 43.5]（与分子不同基）改为同等盈利带 [7.91, 20.16]（`pe_same_min/max` 新增，`pe_own_*` 降为披露）；A5 产能核对 → `confirmed`（2026 中报在建工程 5.42 亿无新建锂盐项目、IR 2026-06-16「其余锂相关规划项目未建设」、20 万吨 / 千万吨为控股股东规划、比亚迪 3 万吨未建；开源 / 国信 / 华源 2027–28 预测均不含名牌外的量）→ 无候选带；A9 谷底坐标在篮 5 / g 0 下由 eval 重算 29.94 / 23.26 → 25.14 / 19.59，谷底 × 1/r 16.00 → 14.48 = L；H 档命名窗口经核不成立（2026E → 27E 共识增速 11% < 20%，2025–28 CAGR 已含在 M 的 2027 run-rate 里，叠加 = 价格 deck 双计）；新增披露行：隐含 r(P) 8.7%（对篮 5 −2.3pp）、③ 出带（篮 6 触发 → 降篮门，篮 5 不出带）、⚠敏感区（g2 +1pp 或 r −50bp 翻 `optimistic`）、地板（只披露）、对照坐标（降篮门路径）与对账门六坐标；Inputs 加 `eps_fy27_cons`。v1 口径 g2 ±1pp → M 22.46 / 25.89。`eval/000792.SZ.py` 改读篮子（`parse_baskets` + `check_r(r, "r_perp", 篮)` + `check_g_cap(g, r, where)`），护栏改 `pe_same_*`，地板打印不参与 L。
#   - 归篮路径（同日三稿并入）：草稿一 r 13%（篮 6 初分）→ 12.14 / 16.90 / 20.36 `stretched`；草稿二曾试 11.5%「CNY 段」（r_f 2.5 + 篮 6 溢价 9.0）→ 13.82 / 19.23 / 23.17，因不在篮子表作废；草稿三回到 13% 并建同等盈利带、判 ③ 出带，早稿按字面判 1b 失真「不可判定、尺留篮 6」，同日按规则句「1b 的 ROE 项只在 g > 0 时生效；ROE 差来自分母重建不算失真」改判带干净 → 降篮门 → 篮 5 14.48 / 20.15 / 24.28。ticker-decisions 专属节的「证据不足维持篮 6」早于本次改判，以本框架为准。
# - touched: [r 篮子, g2, 地板, 护栏, 锚点, A3, A4, A5, A9, A10, Inputs, Formula 校验, Outputs 披露行, eval]
#
# ### 2026-10-03
#
# - 迁移核对（valuation-rules「未建模期权」2026-10-03）：\(V_{opt}\) 维持 0，理由改写为「控股股东规划不是本票具名的量」；升级门槛去掉已废止的「已实现单位经济」（单位经济改取本票腿数据）。锚点、Inputs、eval 均不变。
# - touched: [Outputs V_opt 行, 表2 stretched 行]
#
# ### 2026-10-04
#
# - 规则落地（valuation-rules「③ 出带处理流程」步 1c，2026-10-03）：同等盈利带下沿月份 2022-09→2023-10 的价里含 2022-05-27 公告（2022-038）的 4 万吨锂盐项目——带期 EPS 不含、今天的名牌分子已含；按本票尺（M 档锂单位毛利 × `conv_ratio`、δ、1/r，预计投产日 2024 年底折到带点，减公告总投资 70.82 亿）13% 下净值 1.47 元/股（2023-03），带下沿 7.91 → 7.40×，篮 6 的 7.69× 回带、③ 不触发 → 2026-09-20 的篮 5 降篮撤销、回初分篮 6：L/M/H 14.48 / 20.15 / 24.28 → **12.14 / 16.90 / 20.36**（切点 A / B 17.31 / 22.22 → 14.52 / 18.63），`r_perp` / `r_disc` 0.11 → 0.13（δ 0.901 → 0.885）；按研究当日（2026-10-04）现价 23.83，zone `optimistic` → `stretched`（跨一档）；篮 5 带改印「对照坐标（被推翻的降篮）」；纠正对账门 M −16% < 25%、zone 跨一档，不强制，六坐标照列；Inputs 加 `proj_*` / `shares_band` / `band_*` 共 11 行；formula_id `…_gordon_v2` → `…_gordon_v3`（eval 机械化步 1c 并据此锁篮）。
# - touched: [r 篮子, 锚点, 护栏, A3, A4, A5, A9, A10, Inputs, Formula, Outputs 披露行, 表1, 表2, 敏感性, eval]
#
# ### 2026-10-12
#
# - 锂轴分布按含税、USDCNY 6.8645 重算（轴「换算口径」；碳酸锂期货 LC2701 当日午盘 10.88 万、现货 9 月 15.7 → 12 万）：2027 簇含税中位 12.0 万仍在 12–13 万带内，**锂轴三档不变，本票锚点不变**；L 的出处由「BMI 2028 底」单源改为 BMI 11.3 / 高盛 8.5 万两源夹逼、暂定；`neutral` 档的「激励价邻域」改为「2027 均价簇上沿」（JPM 长期价按新口径 14.0 万，已不贴 12.5 万）。高盛（10-06）对本票维持买入、TP 33 元。
# - touched: [属性 D, A9 引用, 表1 实证坐标, 表2 neutral 场景文字, eval docstring]
#
# ### 2026-10-20
#
# - 锂价轴 M 12.5 → 12.0 万（9 月以后发布的 2027 均价中位 11.9 万跌破 12 万，`_AXIS.lithium-carbonate` §5；新增德银 2026-10-15）；L 10.3 / H 15 万与钾梯不变。L/M/H 18.12 / 22.96 / 24.65 → **18.12 / 22.51 / 24.27**（M −1.9%；H 的锂腿路过一年后回到 M 档，随 M 降）；切点 A / B 20.54 / 23.81 → 20.32 / 23.39；锂腿窗口 0.51 → 0.49（M 档）；\(V_{opt}\) 0、无候选带不变。可比性 L/M 0.79 → 0.80、H/M 1.07 → 1.08、(H−L)/2M 14% 不变。步 1c 用 M 档锂单位毛利给项目估值，经营口径同口径下沿 7.02 → 7.06×（变体 5.98 / 6.41 → 6.05 / 6.48），7.69× 仍入带、③ 不触发；被推翻的篮 5 对照 20.37 / 26.12 / 28.08 → 20.37 / 25.59 / 27.61。构造参数（g2、r、篮子、钾梯、量、实现率）未动。
# - touched: [题头, §0 这张表怎么读 / 价带锚点 / 快照, 属性 D, A1, A3, A4, A5, A9, A10, A12, Inputs li2co3_m / realization_li / pe_same_min / g2 来源, 口径, Outputs 锚点 / 多留部分 / 对照坐标, 表1, 实证坐标, 步 1c, 对账门, H 窗口对照, flat 阶梯, 可比性, ③ 出带, 敏感区, 地板, 表2, 敏感性]
