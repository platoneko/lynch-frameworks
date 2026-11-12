#!/usr/bin/env python3
"""PetroChina's historical oil-axis valuation, output in HKD per share.

Original 2026 inputs, four legs, timing and shared oil axis are retained.
This is a draft research result, not a new forecast or publication.
"""
from __future__ import annotations
from lib.gordon import FULL_PAYOUT, check_g_cap, check_r, recovery_two_stage_pe
from lib.inputs import check_missing, ladder
from lib.tiers import decompose
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis', 'rf_report'),
                'axes': {'brent': 'brent_oil'}}
HISTORICAL_PARTIAL_FINGERPRINT = '1c86199a2617c0b13929a3bd10fef17d7228532f6b37a110151f364f4db84b8c'

TICKER = '0857.HK'

# Original input values, intent, sources and as-of.
INPUTS = {
    # 总股本（A+H）183,020,977,818 股；2026 中期报告 | as-of 2026-06-30
    'shares': 1.83020977818e11,
    # 归母权益 RMB 百万（IFRS，追溯调整后）；各档前瞻 ROE = NI_x ÷ equity，**只披露不进倍数** | as-of 2026-06-30
    'equity': 1637974,
    # HKD→CNY；yfinance `HKDCNY=X` | as-of 2026-09-14
    'fx_hkdcny': 0.8548,
    # FY2025 归母净利润 RMB 百万（IFRS）；分子基点与切腿基数（A1 / A4） | as-of FY2025
    'ni_fy25': 157318,
    # FY2025 基本 EPS CNY；中性带 TTM PE 读数用 | as-of FY2025
    'eps_fy25': 0.8596,
    # FY2025 现金分红总额 RMB 百万（中期 0.22 + 末期 0.25 CNY/股）；派息率分子（A7 分支）与 DDM 坐标 | as-of FY2025
    'div_fy25': 86020,
    # FY2025 每股派息 CNY | as-of FY2025
    'dps_fy25': 0.47,
    # 2025 年布伦特全年均价 US$/bbl（中海油 2025 年报 p.70）；传导基点（A1） | as-of FY2025
    'brent_2025': 68.2,
    # **L** Brent US$/bbl = `_AXIS.brent-oil.md` L 档；eval 逐格对轴校验 | as-of 2026-09-15
    # **M** Brent = 轴 M 档 | as-of 2026-09-15
    # **H** Brent = 轴 H 档 | as-of 2026-09-15
    # FY2025 E&P 分部营业利润 RMB 百万（年报分部附注）；= `seg_ep`，v2 两点法对照 | as-of FY2025
    'ep_op_fy25': 136065,
    # 2026H1 E&P 分部营业利润 RMB 百万（2026 中期报告分部附注）；β 半年同比（A2） | as-of 2026H1
    'ep_op_h1_26': 100448,
    # 2025H1 E&P 分部营业利润 RMB 百万（2026 中期报告重述比较列）；β 半年同比（A2） | as-of 2025H1
    'ep_op_h1_25': 87151,
    # FY2025 平均实现原油价格 US$/bbl（年报）；实现价/Brent 比 | as-of FY2025
    'real_2025': 64.11,
    # 2026H1 平均实现原油价格 US$/bbl（2026 中期报告） | as-of 2026H1
    'real_h1_26': 76.53,
    # 2025H1 平均实现原油价格 US$/bbl（2025 中期报告） | as-of 2025H1
    'real_h1_25': 66.21,
    # 企业所得税率（β 由营业利润折归母，A2） | as-of 法定
    'cit': 0.25,
    # FY2025 原油产量 mmbbl；β 理论交叉，**不进公式**（A2） | as-of FY2025
    'crude_fy25': 948.0,
    # 2018–25 E&P 分部营业利润对实现油价回归斜率（剔 2020）RMB 百万 / US$1；β 互证，**不进公式**（A2、§1 八年表） | as-of 2018–25
    'ep_slope_reg_lo': 2680,
    # 同上，含 2020 全样本；**不进公式** | as-of 2018–25
    'ep_slope_reg_hi': 2930,
    # E&P 腿 → **篮 6 周期商品**（盈利是 Brent 函数；A16）；E&P 腿 \((1-b_g)/(r-g_2)\) 用此 r | as-of 2026-10-05
    'r_perp': 0.13,
    # 天然气销售腿 → **篮 6 周期商品**（进口气价差，城市燃气不到一成；A16）；\(1/r\) | as-of 2026-10-05
    'r_ng': 0.13,
    # 炼油化工腿 → **篮 6 周期商品**（价差周期；A16）；\(1/r\) | as-of 2026-10-05
    'r_rc': 0.13,
    # 销售腿 → **篮 4 常规经营**（量与零售价差，非商品价函数；A16）；\(1/r\) | as-of 2026-10-05
    'r_mk': 0.10,
    # 维持性 capex 超出 D&A 的部分 RMB 百万（A7）；全落 E&P 腿，三档同扣；**待按分部口径重审** | as-of FY2022–25
    'capex_maint_excess': 11000,
    # 增长 capex RMB 百万/年（A7）；只进 \(g_2\) 与 \(b_g\) 的推导校验 | as-of FY2022–25
    'capex_growth': 48000,
    # 增长 capex 的项目 ROE（A7）；\(g_2\) = capex_growth × roe_proj ÷ \(E_{owner,M}\) | as-of 判断值
    'roe_proj': 0.09,
    # 增长留存率 = capex_growth ÷ \(E_{owner,M}\)（158,672 百万）= 30.3%（A7）；E&P 腿 \(PE = (1 - b\_growth)/(r\_perp - g_2)\) | as-of 2026-10-05
    # 净负债 RMB 百万 ≈ 1,087 亿（财务性桶）；≈ **0.69 HKD/股**，按面值另行披露，**不进倍数** | as-of 2026-06-30
    'net_debt': 108700,
    # **L 永续 g = `g2_m`**（三档同用，A7） | as-of 2026-10-05
    # **M 永续 g** = capex_growth × roe_proj ÷ \(E_{owner,M}\) = 2.72%（只进 E&P 腿，A7）；cap = min(6%, 13% − 4%) = 6% ✓ | as-of 2026-10-05
    # **H 永续 g = `g2_m`** | as-of 2026-10-05
    # 美国大型油企同日留存分支反解中位（XOM 4.68 / CVX 4.47 / COP 3.78；单调区，不同域）；**交叉，不进公式** | as-of 2026-09-14
    'g_peer_us': 0.0447,
    # H 股 5 年月频 TTM PE 实测下沿（2022-10）；**护栏**（A8） | as-of 2021-09~2026-08
    'pe_own_min': 3.44,
    # H 股 5 年月频 TTM PE 实测上沿（2026-04）；**护栏**（A8） | as-of 2021-09~2026-08
    'pe_own_max': 12.29,
    # 5 年月频中位；**交叉尺，不进公式** | as-of 同上
    'pe_own_med': 6.24,
    # 共识 FY2026E EPS 均值 CNY（yfinance 13 家，0.91–1.15）；**进窗口可分配利润**（× 股本 − `ni_h1_26` = 2H26 未入账共识利润，A17）；中性带 PE 读数 | as-of 2026-09-14
    'eps_cons_fy26_mean': 1.02659,
    # 共识 FY2027E EPS 区间下沿（yfinance 12 家）；**②-b 判据与交叉，不进公式**（A6） | as-of 2026-09-14
    'eps_cons_fy27_lo': 0.72,
    # 共识 FY2027E EPS 均值；②-b | as-of 2026-09-14
    'eps_cons_fy27_mean': 0.95267,
    # 共识 FY2027E EPS 区间上沿；交叉 | as-of 2026-09-14
    'eps_cons_fy27_hi': 1.13,
    # Longbridge H 股 18 家目标价均值 HKD（4.82–13.86）；**交叉，不进公式**（A11） | as-of 2026-09-13
    'tp_cons_h': 11.71,
    # FY2025 E&P 分部营业利润 RMB 百万（= ep_op_fy25）；切腿份额（A4） | as-of FY2025
    'seg_ep': 136065,
    # FY2025 天然气销售分部营业利润；切腿份额 | as-of FY2025
    'seg_ng': 60802,
    # FY2025 炼油化工和新材料分部营业利润；切腿份额 | as-of FY2025
    'seg_rc': 24247,
    # FY2025 销售分部营业利润；切腿份额 | as-of FY2025
    'seg_mk': 17547,
    # FY2025 集团营业利润；四分部之和 − 总部与抵销 | as-of FY2025
    'op_group_fy25': 219241,
    # 2026H1 归母净利润 RMB 百万；**进窗口可分配利润**（已入账部分，A17）；属性 D 对照 | as-of 2026H1
    'ni_h1_26': 103936,
    # **时点对齐 τ**（年）：估值基准日 2026-06-30（中报资产负债表日）→ 分子年 FY2027 年初 2027-01-01；`_AXIS.brent-oil` 是按日历标定的「2027 油价 regime」，不是周期中枢，故适用（A17） | as-of 2026-10-16
    'tau': 0.5,
    # FY2025 自由现金流 RMB 百万；P/FCF 10× 交叉，**不进公式** | as-of FY2025
    'fcf_fy25': 120189,
    # 上一轮谷底 FY2020 EPS CNY（Brent ~42）；× 1/r = `deep_discount` 压力坐标，**不进公式**（A3） | as-of FY2020
    'eps_trough_fy2020': 0.10,
    # FY2022 EPS CNY；回归段坐标用，**不进公式** | as-of FY2022
    'eps_fy2022': 0.81,
    # 同等盈利月份（TTM EPS 落中枢归母 EPS 0.927 ±12%，2022-10~2026-08，32 个月）H 股月末收盘 p25 HKD；纠正对账门坐标 ④，**不进公式** | as-of 2022-10~2026-08
    'px_same_p25': 5.65,
    # 同上中位 HKD；坐标 ④ | as-of 2022-10~2026-08
    'px_same_med': 6.72,
    # 同上 p75 HKD；坐标 ④ | as-of 2022-10~2026-08
    'px_same_p75': 8.02,
    # H 股 5 年月频 PB 中位（Longbridge `valuation --history`）；坐标 ⑥，**不进公式** | as-of 2021-09~2026-08
    'pb_own_med': 0.625,
    # H 股 5 年月频 PB 下沿（2022-10）；地板披露，**不进公式** | as-of 2021-09~2026-08
    'pb_own_min': 0.34,
}

# Historical reasoning and observations; not additional model inputs.
# - **业务地图摘要**：四个 operating segment 的营业利润、折旧、减值、资本开支、分部资产与负债全部披露（2025 年报分部附注 p.255、2026 中期报告分部附注）。**2018–25 八年分部营业利润**（亿元；天然气 2020 / 2021 扣管道重组收益 469.46 / 183.20）：
# - **属性 A — 纯上游弹性远低于中海油，原因是股本摊薄与下游垫子，不是对冲**：每 US$1 Brent 对本票归母 EPS 是 0.0099 CNY，对中海油是 0.0487 CNY（轴文件 §3）；原油产量 948 mmbbl（中海油液体销量 589 mmbbl），差在股本 1,830 亿股摊薄与占四成利润的下游腿不随油价走。八年数据不支持「油价下行时下游反向补回」（属性 A 旧表述已撤）。2020 年型需求塌陷是唯一上下游同跌的情形，只作 `deep_discount` 压力坐标，不进锚点。
# - **属性 B — E&P 腿倍数承载的是具名增长 capex，不是账面 ROE**：前瞻 ROE 9.6 / 10.4 / 11.5%（只披露）在篮 6 的 13% 下落峰形区（\(ROE < r\)），留存 × 账面 ROE 的 Gordon 不是读数。本框架用所有者盈利 + 增长留存率：分子先扣维持 capex 超额 110 亿，\(g_2\) = 增长 capex 480 亿 × 项目 ROE 9% ÷ 所有者盈利 1,587 亿 = **2.72%**，\(b_g\) = **30.3%**，\(PE = 0.697/(13\% - 2.72\%) = 6.78×\)——**低于 1/r 7.69×**：项目 ROE 9% < r 13%，增长 capex 在本篮下毁值（\(g\) 0 \(b\) 0 对照 8.00 港元高于 M，A9）。
# - **属性 C — 派息率一路抬升，钉定留存分支；留存分两桶**：章程下限 30%，实付 FY2023 50.0% → FY2024 52.2% → FY2025 **54.7%**（86,020 / 157,318）；DPS（CNY）FY2020 0.1748 → FY2021 0.2266 → FY2022 0.4225 → FY2023 0.44 → FY2024 0.47 → FY2025 0.47，2026 中期 **0.26**。留存里**增长留存 30.3%**（480 亿具名增长 capex）进 E&P 腿倍数，其余是财务性留存（还债 / 现金），不进倍数——净负债 1,087 亿另行披露。
# - **属性 D — 2026H1 是历史最好的半年，但本框架没有把它年化**：归母 1,039 亿（+22%）、E&P 分部营业利润 1,004 亿（+15%）。E&P 利润下半年系统性低于上半年（四季度集中减值与年末成本：H2 / H1 = 0.74 / 0.74 / 0.59，2023–25），**上半年 ×2 不是全年**——v2 的 β 两点法正是把这条季节性读成了油价弹性（A2）。2026H1 年化 2,079 亿对应本尺 Brent ≈ 96 的世界，只是坐标。
# - **属性 E — 无永续债、无优先股**：2025 年报权益表只有股本、储备、留存收益与少数股东权益，2026 中报同；归母 = 归属普通股股东。少数股东权益 2,102 亿（2026-06-30）。
# - **属性 F — 为什么不叠 `slow_grower` 次类**：天然气销售 FY2025 占四分部 25.5%、2026H1 16%，低于 30% 门槛；且其利润随进口气成本与管制气价在 130–608 亿之间波动（2018–25），不是稳定年金。
# | A1 | **三档归母 = 轴三档 Brent 经自身弹性桥到 FY2027**：\(NI_x = ni\_fy25 + \beta\,(brent_x - 68.2)\) = 156,955 / 169,672 / 187,840 百万；分子年份 FY2027（≥2 家带区间的最远共识年，12 家）；各腿 Gordon 值在分子年初，按时点对齐折回估值基准日（A17） | active | FY2025 归母 157,318（年报，IFRS）；Brent 2025 均价 68.2（中海油年报 p.70）；轴三档 68 / 75 / 85（`_AXIS.brent-oil.md` §1）。原油产量按 FY2025 948.0 mmbbl 持平 | `ni_fy25`、`brent_l/m/h`、`brent_2025`；eval 逐格对轴校验，轴 §3 本票归母 / EPS / ROE 跨文件校验 |
# | A2 | **β = 1,817 RMB 百万 / US$1 Brent，半年同比实测**：E&P 分部营业利润 2026H1 100,448 @ 实现油价 76.53 对 2025H1 87,151 @ 66.21（2026 中期报告重述列）→ 每 US$1 实现价 1,288.5 百万 / 半年 × 2 = **2,577** 百万营业利润 × (1−25%) × 实现价/Brent 0.940。**互证**：2018–25 八年分部回归每 US$1 实现价 2,680（剔 2020）–2,930（全样本）百万 → β 1,889–2,066；本值落回归下沿之下 4%（2026H1 已越过特别收益金 65 美元起征点，高油价段边际弹性递减）。**v2 两点法已废**：2026H1 ×2 对 FY2025 全年 = 5,220 → β 3,680——E&P 下半年系统性低于上半年（H2/H1 0.74 / 0.74 / 0.59，2023–25；FY2025 E&P 计提 PP&E 减值 87.20 亿集中于四季度），上半年 ×2 把季节性读成了油价弹性，β 高估约一倍 | active | 2025 年报分部附注（136,065；减值 8,720）；2026 / 2025 / 2024 / 2023 中期报告分部附注与实现油价（76.53 / 66.21 / 77.45 / 74.15）；八年表见 §1。理论交叉 = 原油产量 948 × 0.94 × (1−SOG 30%)(1−25%) × 7.0 ≈ 3,275（未扣特别收益金、未计成本随油价，只作上限）| `ep_op_h1_26`、`ep_op_h1_25`、`real_h1_26`、`real_h1_25`、`real_2025`、`cit`、`ep_slope_reg_lo/hi`；eval 校验半年同比斜率落回归带 ±20% |
# | A3 | **本票挂 `_AXIS.brent-oil.md`**，三档 Brent 逐格引用；L = 2025 实测年均 68，M = 2027 卖方 / 官方中枢 75，H = 汇丰 2027 高位 85。**L 分子是轴 L 档梯值，不是本票实测谷底** → 配稳态 \(g_2\)；FY2020 EPS 0.100（Brent ~42）× 1/r = 0.90 港元只作 `deep_discount` 压力坐标 | active | 轴文件 §1–§3；valuation-rules「谷底档」 | `brent_*`；eval 打印回归坐标与压力坐标 |
# | A4 | **主尺 = 四腿分腿加总**（valuation-rules「归篮触发分腿」：分部落不同篮子 MUST 分腿，只需年报分部利润，不再要求卖方 SOTP ≥2 家）。切腿：FY2025 归母按 FY2025 四分部营业利润份额（57.0 / 25.5 / 10.2 / 7.4%）切，总部与抵销 −19,420 按份额摊入；β 增量与维持 capex 超额全落 E&P 腿。**已知简化**：切腿用营业利润份额而非分部税后利润（各腿税负与少数股东占比不同）；分腿 ROE 未接（分部资产 − 分部负债已在附注，valuation-rules 来源优先序 ①，下一次框架纠正接入）。v2「整公司 PE + 分腿加总对照」已撤（其门槛「≥2 家卖方 SOTP」规则已删） | active | 2025 年报分部附注 p.255；分部资产 / 负债 E&P 1,676,621 / 762,520、炼化 512,767 / 235,742、销售 591,358 / 328,556、天然气 238,191 / 133,474（含分部间往来，待抵销口径） | 主尺形态；`seg_*`、`op_group_fy25`、`r_perp/r_ng/r_rc/r_mk` |
# | A5 | **下游三腿与总部项固定于 FY2025 实测，不随油价档变动** | active | 2018–25 八年表（§1）：下游合计对实现油价剔 2020 每 US$1 +2.6 亿、相关 0.12——油价档之间不动是数据支持的近似，**不是**「两向抵消」；炼化与销售对油价同向、天然气反向。**已知偏差**：① 2021 年后下游台阶（天然气价格改革）使 FY2025 1,026 亿已在台阶上，M 不偏低；② 2020 型需求塌陷时下游与上游同跌（207 亿），L 不含此情景（压力坐标） | `ni_fy25` 作基点；H 档不叠下游 2026H1 年化 |
# | A6 | **②-b 判据：共识 FY2027 均值 0.953 落归母口径 [M 0.927, H 1.026]，M 偏离 −2.7%（≤ 20%）**；情景梯保留，共识三点只作印证。均值按本票 β 对应 Brent **77.6**——与轴 M 75 及 9 月 8 日上调后的簇（EIA 74 / 美银 75 / 汇丰 LT 75 / 高盛 80）同一世界；v2 时读成「72.8 = 旧 deck」是 β 高估一倍的副产品，已撤 | active | yfinance 2026-09-14：FY2027 12 家 0.72 / 0.953 / 1.13；FY2026 13 家 0.91 / 1.027 / 1.15。**证伪触发器**：下一次共识刷新（≥ 2026-11-15）若均值 > H → H 换市场基准世界；若 < M 且偏离 > 20% → 分子改共识三点 | `eps_cons_fy27_lo/mean/hi`（不进公式）；eval 机械化 |
# | A7 | **留存三桶 → 所有者盈利分子 + 具名增长 capex 的 \(g_2\)（只进 E&P 腿）**：capex 2,438 / 2,825 / 3,027 / 2,928 亿（2022–25）vs D&A，超出 ≈ 600 亿；拆成 **增长 capex ≈ 480 亿**（产量 +2–3%/yr、储量替代 >100%）与 **维持性超额 110 亿**。① \(E_{owner,x} = NI_x - 110\) 亿 = 0.7975 / 0.8670 / 0.9662 CNY；② \(g_2\) = 480 × 9% ÷ \(E_{owner,M}\) 1,587 亿 = **2.72%**，\(b_g\) = 480 / 1,587 = **30.3%**，三档同用 → E&P 腿 \(PE = 0.697/(13\% - 2.72\%) = 6.78×\)；项目 ROE 9% < r 13% → 增长 capex 毁值、PE < 1/r（峰形区，属性 B）；③ 财务性：净负债 ≈ 1,087 亿 ≈ 0.69 HKD/股，另行披露。分支：派息 54.7% < 95% → 留存分支。**待核（下一次框架纠正）**：2025 分部附注 capex 205,094（E&P）/ 47,772 / 8,216 / 4,987 vs 折旧 194,958 / 28,382 / 17,759 / 5,450 → 分部口径 capex 超出折旧只 ≈ 210 亿（E&P ≈ 101 亿），与现金流口径 600 亿差距大，480 / 110 的拆分与「增长 capex 全在 E&P」需按分部口径重审 | active | 年报（capex、D&A、产量、储量替代率）；2025 分部附注；`gordon.g_cap`：cap = min(6%, 13% − 4%) = 6% ✓ | `capex_maint_excess`、`capex_growth`、`roe_proj`、`b_growth`、`g2_l/m/h`；eval 复算 \(g_2\)（±0.05pp）与 \(b_g\)（±0.5pp） |
# | A8 | **护栏（裁决顺序 ③）**：有效倍数（锚点 ÷ \(E_{owner}\)）7.39 / 7.31 / 7.21× 落自身 5 年月频 TTM PE 带 [3.44, 12.29] 内，③ 不触发。**带有效性核验**：带下沿 2022-10（PE 3.44）当时 ROE = FY2022 归母 148,743 ÷ 年初归母权益 1,260,742 = 11.8%（现模型 ROE_M 10.4%，差 1.4pp）；当时预期增速代理 = 其后两年实测 EPS CAGR 0.81 → 0.90（FY2022 → FY2024）= +5.4%/yr（现模型 \(g_2\) 2.72%，差 2.7pp）→ **干净** | active | Longbridge `valuation --history` 5 年月频（2021-09~2026-08）：min 3.44 / med 6.24 / max 12.29；own-year PE FY2021–25 5.55 / 3.97 / 5.35 / 6.76 / 7.84；2023 年报（权益、EPS） | `pe_own_min/max`；eval 校验有效 PE 在带内 |
# | A9 | **敏感区披露**（均已时点对齐，A17）：\(g_2\) ±1pp → 6.61 / 7.08 / 7.76 与 7.24 / 7.81 / 8.63；\(g\) 0 \(b\) 0（E&P 腿也取 1/r）→ 7.41 / 8.00 / 8.84——高于底牌，因为 9% 项目 ROE 的增长 capex 在 13% 下毁值；维持 capex 0 / 590 亿 → 7.37 / 7.88 / 8.62 与 4.83 / 5.35 / 6.09（A7 待核是分子侧最大单点）；只披露，不 BLOCKED | active | eval 打印 | — |
# | A10 | **归篮排查（隐含 r 对账第 3 条）结论**：市价与本尺之差在 r 层而非分子层——② 分子：共识均值落 [M, H]（A6），β 有八年回归互证（A2），分子不低估；③ g：\(g_2\) 来自具名 capex，±1pp 只动 M ±6%；① 归篮：E&P / 天然气 / 炼化三腿盈利是商品价（Brent、进口气价、成品油价差）函数，篮 6 判据正向成立，篮 4「盈利不是商品价函数」不成立。差额 = 市场给中国油企的要求回报低于篮 6——2023 年起国资委市值管理考核、派息承诺、南向与险资配置；**这是「央企标签」的篮子地板样本，走仓库级篮级对账（`calibration.py` 按篮子 × 货币 × 标签），MUST NOT 在本票拧 r**。2021–25 own-year PE 3.97–7.84（盈利收益率 13–25%）说明市场在多数年份要的回报高于 13%；**卖方 TP 反解 r 不作归篮依据**（v2 以 TP 反解 9.2% 归篮 4，违反「篮子 > 隐含 r」，已撤） | active | valuation-rules「隐含 r 对账」「③ 出带处理流程」篮子地板样本清单；own-year PE 序列（A8） | `r_perp`；**MUST NOT** 把 r 拧去贴现价 |
# | A11 | **未采用卖方目标价**：摩根大通 H **13.50**（SOTP，2026-07-30，98113）、汇丰 **12.80**（2026-08-06，99355）、美银 **11.50**（2026-09-08，104615）；Longbridge H 股 18 家均值 **11.71**（4.82–13.86，2026-09-13） | active | H / TP 均值 = 0.70、M / TP = 0.63；TP 均值落本框架 `stretched`。卖方在 FY2026E 1.027 CNY 上给约 9.7×；差额 = r（全腿篮 4 对照 9.10 / 9.84 / 10.90）+ 下游 2026H1 年化 | 交叉校验；TP 不反解进倍数 |
# | A12 | **\(V_{opt}\) = 0；无候选带** | active | LNG Canada 15% 股权出售（未经确认）是已在腿内的资产变现，不是新单位；FY2028 ≥2 家带区间共识 `待补` | Outputs 无表3、无候选带行 |
# | A13 | **`deep_discount` 观察项**：① 减值（FY2025 E&P PP&E 减值 87.20 亿，集团 100.98 亿；2026E 卖方预留 150 亿）；② LNG 进口亏损；③ **需求塌陷**（2020 型：E&P 231 亿、下游合计 207 亿同跌，FY2020 EPS 0.10）；④ A/H 折价走阔。任一项被财报证实 → 事件增量，重估 A5 的下游固定值而非倍数 | active | 中期报告；Wisburg 98113 / 102636 / 99355；§1 八年表 | `deep_discount` 行排查顺序 |
# | A14 | **同世界门（裁决顺序 ④）**：分子年 FY2027 = 最远带区间共识年；FY2028 ≥2 家点估计 `待补`；改取自身 ≥3 年实测 CAGR 方向：归母 FY2022 148,743 → FY2025 157,318（+1.9%/yr）、DPS 0.4225 → 0.47（+3.6%/yr），方向为正 → \(g_2>0\) 可用 | active | 年报五年摘要；Longbridge dividend | A7 分支；FY2028 共识出现后重判 |
# | A15 | **分子口径 = 归属母公司股东 = 归属普通股股东**：无永续债、无优先股 | active | 权益表只有股本 183,021 / 储备 / 留存收益 / 少数股东权益 210,158 | `ni_fy25`、`equity` 口径 |
# | A16 | **归篮（2026-10-05 纠正）**：**E&P 腿 → 篮 6 周期商品**（盈利是 Brent 函数，价格不由公司定；八年回归相关 0.69–0.84）；**天然气销售腿 → 篮 6**（利润 = 管制 / 半市场化售价 − 挂钩油价的进口气与 LNG 成本，2018–25 在 130–608 亿间波动；昆仑能源城市燃气归母约 54 亿 × 本票约 54% 持股 ≈ 29 亿，不到本腿一成，城市燃气部分的篮 2 性质不改整腿）；**炼化腿 → 篮 6**（价差周期）；**销售腿 → 篮 4**（成品油零售与批发，盈利跟量与零售价差，不是商品价函数）。v2 的「E&P 篮 4 / 天然气篮 4」归篮依据是卖方 TP 反解 r（9.2%），按「篮子 > 隐含 r > CAPM」不成立，撤销。**CAPM 粗筛**：5 年周频 β 对恒指 **0.49**（Longbridge 2021-09~2026-09，n=266，相关 0.35）→ 4% + 0.49 × 5.5 + 港股 1 ≈ 7.7%，对篮 6 −5.3pp；扣 HKD 段中位偏移 −3pp 后残差 −2.3pp（≤ 3pp）；β 低是因为盈利是 Brent 的函数而非恒指的函数（与 CVX 同一条已知张力）。**国别**：本票不在 NS-CMIC 名单，不归篮 7（对照 `0883.HK` A17；篮 7 15% 只作敏感性） | active | valuation-rules「§r 篮子」篮 6 判据、「归篮触发分腿」（规则正文以本票 E&P → 篮 6 为例）；2025 年报分部附注；Longbridge 0135.HK（昆仑能源 TTM EPS 0.733 HKD × 86.2 亿股，2026-10-05） | `r_perp` / `r_ng` / `r_rc` / `r_mk`；篮子变动 → 整条价带重算 |
# | A17 | **经营价值与超额现金：时点对齐 / 窗口 / 资金缺口 / 稳态回报 / k（valuation-rules「经营价值与超额现金」①②③④，2026-10-16 框架纠正；锚点 6.89 / 7.44 / 8.23 → 6.89 / 7.41 / 8.15）**：① **超额现金未触发**：扩展口径净现金为负（净负债 ≈ 1,087 亿），无超额现金行；分子已是归母利润，归母比例无须另乘（少数股东权益 2,102 亿不进）；**增长期资金缺口 0**——2H26 资本开支超出半年经营现金流约 587 亿（中银 FY26E 隐含）是本票资本开支集中在下半年的季节性维持 / 在产开支（全年经营现金流 3,721 亿 > 资本开支 2,920 亿；2025 全年自由现金流 1,202 亿），不是为分子年产出扩产，按 ① 只计产出落在分子年内的扩产 → 记 0；若照计（作类债项 × 归母比例 88.63%）→ 6.56 / 7.08 / 7.82，只披露。② **时点对齐 τ = 0.5**：`_AXIS.brent-oil` 是按日历标定的「2027 油价 regime」（不是跨周期中枢），分子年 FY2027 → 分子年初 2027-01-01，估值基准日 2026-06-30（中报资产负债表日）；各腿按自己的 r 折回（13% 腿 × 0.9407、10% 腿 × 0.9535）。**窗口可分配利润**：FY26E 共识 EPS 1.02659（13 家）× 股本 = 1,878.9 亿 − 1H26 实测归母 1,039.4 亿 = 2H26 839.5 亿，与分子同口径再扣半年维持性超额资本开支 55 亿；按 M 档腿利润切腿，E&P 腿 × (1 − \(b_g\) 30.3%)，下游三腿 g = 0 → b = 0；各按 τ/2 折 → 每股 **0.40 港元**。③ **稳态回报三段不适用**：E&P 腿分子由 Brent 轴桥出（商品腿豁免），三档都是持续 regime（L「回到 2025 的 68 并长期化」、M 中枢、H「中断成为新常态」），不属「路过」；\(g_2\) 2.72% 是具名增长 capex × 项目 ROE 9%，不是价格反解，不重解；下游三腿 g = 0，回报不进倍数。④ **k**：本框架没有打折 k | active | valuation-rules「经营价值与超额现金」①②③；2026 中期报告；yfinance 2026-09-14 FY26E 共识；中银 FY26E 现金流预测 | `tau`、`eps_cons_fy26_mean`、`ni_h1_26`；eval 时点对齐与窗口 |

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-4                # g2 stated to 0.01pp
B_TOL = 5e-3                # b_growth stated to 0.1pp
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
GATE_OUT = 0.20             # 纠正对账门: new M outside every coordinate by > 20% -> BLOCKED
SOG_RETENTION = 0.525       # (1 - SOG 30%) x (1 - CIT 25%) for the theoretical beta cross-check
USDCNY_CROSS = 7.0
MAINT_ALL = 59000.0         # A9: the whole capex-above-D&A gap read as maintenance (RMB mn)

LEGS = ("r_perp", "r_ng", "r_rc", "r_mk")   # E&P / gas / refining / marketing
SEGS = ("seg_ep", "seg_ng", "seg_rc", "seg_mk")

REQUIRED = [
    "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "div_fy25", "dps_fy25",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "ep_op_fy25", "ep_op_h1_26", "ep_op_h1_25", "real_2025", "real_h1_26", "real_h1_25", "cit",
    "crude_fy25", "ep_slope_reg_lo", "ep_slope_reg_hi",
    *LEGS, "capex_maint_excess", "capex_growth", "roe_proj", "net_debt",
    "g_peer_us",
    "pe_own_min", "pe_own_max", "pe_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    *SEGS, "op_group_fy25",
    "ni_h1_26", "fcf_fy25", "eps_trough_fy2020", "eps_fy2022",
    "px_same_p25", "px_same_med", "px_same_p75", "pb_own_med", "pb_own_min",
    "tau",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 11).
# eps_cons_fy26_mean and ni_h1_26 now feed the window distributable profit (A17) and are out of this list.
NOT_FORMULA = (
    "crude_fy25", "ep_slope_reg_lo", "ep_slope_reg_hi", "pe_own_med", "g_peer_us",
    "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "fcf_fy25", "eps_trough_fy2020", "eps_fy2022",
    "px_same_p25", "px_same_med", "px_same_p75", "pb_own_med", "pb_own_min",
)

def ep_pe(b_growth: float, r: float, g: float) -> float:
    """E&P leg: retention-adjusted perpetuity, retention named by growth capex (A7)."""
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    return (1.0 - b_growth) / (r - g)


def derived_growth(capex, project_return, owner_earnings):
    """Historical precision: four decimals for growth, three for retention."""
    if owner_earnings <= 0:
        raise ValueError('middle-scenario owner earnings must be positive')
    return round(capex * project_return / owner_earnings, 4), round(capex / owner_earnings, 3)


def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    inp = dict(inp)
    review_flags = []
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))

    leaked_p = [k for k in inp if k.startswith("p_")]
    if leaked_p:
        errors.append(f"probability fields in Inputs {leaked_p} (A2e-7a)")
    fx, shares = inp["fx_hkdcny"], inp["shares"]
    r_leg = {leg: inp[leg] for leg in LEGS}

    # --- Step 1: axis mount, beta (half against half), numerator ladder ---------
    brent = {"l": inp["brent_l"], "m": inp["brent_m"], "h": inp["brent_h"]}
    rho = inp["real_2025"] / inp["brent_2025"]
    slope_op = 2.0 * (inp["ep_op_h1_26"] - inp["ep_op_h1_25"]) / (inp["real_h1_26"] - inp["real_h1_25"])
    beta = slope_op * (1.0 - inp["cit"]) * rho
    slope_v2 = (2.0 * inp["ep_op_h1_26"] - inp["ep_op_fy25"]) / (inp["real_h1_26"] - inp["real_2025"])
    beta_v2 = slope_v2 * (1.0 - inp["cit"]) * rho
    beta_theory = inp["crude_fy25"] * rho * SOG_RETENTION * USDCNY_CROSS
    beta_reg = tuple(s * (1.0 - inp["cit"]) * rho for s in (inp["ep_slope_reg_lo"], inp["ep_slope_reg_hi"]))
    if not (inp["ep_slope_reg_lo"] * 0.8 <= slope_op <= inp["ep_slope_reg_hi"] * 1.2):
        review_flags.append('oil_sensitivity_outside_historical_regression')
    ni = {t: inp["ni_fy25"] + beta * (brent[t] - inp["brent_2025"]) for t in TIERS}
    eps = {t: ni[t] * MN / shares for t in TIERS}                                   # reported-NI EPS (②-b, ROE)
    e_owner = {t: (ni[t] - inp["capex_maint_excess"]) * MN / shares for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}                                # disclosed only
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    errors += ladder("e_owner", e_owner["l"], e_owner["m"], e_owner["h"])

    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 2: baskets, g2 from named growth capex (A7), cap ----------------
    baskets = {"r_perp": 6, "r_ng": 6, "r_rc": 6, "r_mk": 4}
    for leg in LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in its Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    r_ep = r_leg["r_perp"]
    e_owner_m_mn = ni["m"] - inp["capex_maint_excess"]
    g_used, inp['b_growth'] = derived_growth(inp['capex_growth'], inp['roe_proj'], e_owner_m_mn)
    g2_derived = inp["capex_growth"] * inp["roe_proj"] / e_owner_m_mn
    b_derived = inp["capex_growth"] / e_owner_m_mn
    for t in TIERS:
        inp[f'g2_{t}'] = g_used
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], r_ep, f"g2_{t}")
        if r_ep - inp[f"g2_{t}"] < MIN_R_MINUS_G:
            errors.append(f"g2_{t} {inp[f'g2_{t}']:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if not (abs(inp["g2_l"] - inp["g2_m"]) <= G_TOL and abs(inp["g2_h"] - inp["g2_m"]) <= G_TOL):
        errors.append(f"g2 tiers must be flat: {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} (A7: growth is carried by named capex)")
    if inp["g2_m"] <= 0:
        errors.append(f"g2_m {inp['g2_m']:+.4f} <= 0 is the full-payout branch — PetroChina retains (A7)")
    payout_fy25 = inp["div_fy25"] / inp["ni_fy25"]
    if payout_fy25 >= FULL_PAYOUT:
        errors.append(f"payout {payout_fy25:.0%} >= {FULL_PAYOUT:.0%}: nothing retained to fund g2 > 0 (A7 分支)")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 3: leg sum -----------------------------------------------------
    seg_sum = sum(inp[k] for k in SEGS)
    if abs(inp["seg_ep"] - inp["ep_op_fy25"]) > 1e-6:
        errors.append("seg_ep must equal ep_op_fy25 (same filed number)")
    share = {k: inp[k] / seg_sum for k in SEGS}
    per_share = lambda v: v * MN / shares / fx  # noqa: E731

    def legs_at(t: str, r: dict[str, float], g: float, b: float, beta_x: float = beta,
                maint: float = inp["capex_maint_excess"]) -> tuple[float, float, float, float]:
        base = inp["ni_fy25"]
        ep_ni = base * share["seg_ep"] + beta_x * (brent[t] - inp["brent_2025"]) - maint
        return (per_share(ep_ni) * ep_pe(b, r["r_perp"], g),
                per_share(base * share["seg_ng"]) / r["r_ng"],
                per_share(base * share["seg_rc"]) / r["r_rc"],
                per_share(base * share["seg_mk"]) / r["r_mk"])

    # Time alignment (valuation-rules「经营价值与超额现金」③, A17): the numerator is FY2027 on the
    # calendar-tagged「2027 油价 regime」axis -> each leg's Gordon value sits at t_n = 2027-01-01;
    # valuation date = the 2026-06-30 balance sheet, tau = 0.5 year; each leg discounted at its own r.
    # Window distributable profit: not-yet-booked 2H26 consensus parent profit (FY26E mean x shares
    # − 1H26 actual), numerator basis (less half a year of capex_maint_excess), split by M-tier leg
    # earnings, x (1 − b_leg) (E&P b = b_growth, downstream b = 0), at tau/2.  No growth-period gap.
    tau = inp["tau"]
    leg_keys = ("r_perp", "r_ng", "r_rc", "r_mk")

    def window(r: dict[str, float], b: float, beta_x: float = beta, maint: float = inp["capex_maint_excess"]) -> float:
        base = inp["ni_fy25"]
        e = (base * share["seg_ep"] + beta_x * (brent["m"] - inp["brent_2025"]) - maint,
             base * share["seg_ng"], base * share["seg_rc"], base * share["seg_mk"])
        es = sum(e)
        prof = inp["eps_cons_fy26_mean"] * shares / MN - inp["ni_h1_26"] - maint / 2
        bl = (b, 0.0, 0.0, 0.0)
        return sum(per_share(prof * ek / es) * (1 - bk) / (1 + r[rk]) ** (tau / 2)
                   for ek, bk, rk in zip(e, bl, leg_keys))

    def band(r: dict[str, float] = r_leg, g: float = inp["g2_m"], b: float = inp["b_growth"], **kw) -> tuple[float, float, float]:
        w = window(r, b, **kw)
        return tuple(sum(v / (1 + r[rk]) ** tau for v, rk in zip(legs_at(t, r, g, b, **kw), leg_keys)) + w
                     for t in TIERS)  # type: ignore[return-value]

    legs = {t: tuple(v / (1 + r_leg[rk]) ** tau for v, rk in zip(legs_at(t, r_leg, inp["g2_m"], inp["b_growth"]), leg_keys))
            for t in TIERS}
    win_ps = window(r_leg, inp["b_growth"])
    L, M, H = band()
    if not (L < M < H):
        raise ValueError('; '.join(errors + [f'L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}']))
    A, B = cut_points(L, M, H)
    pe_eff = {t: a * fx / e_owner[t] for t, a in zip(TIERS, (L, M, H))}
    pe_e = ep_pe(inp["b_growth"], r_ep, inp["g2_m"])

    # --- Step 4: guardrail ③ on the effective multiple, ②-b ------------------
    in_band = all(inp["pe_own_min"] - 1e-9 <= pe_eff[t] <= inp["pe_own_max"] + 1e-9 for t in TIERS)
    cons_mean = inp["eps_cons_fy27_mean"]
    cons_dev = eps["m"] / cons_mean - 1.0
    if cons_mean > eps["h"]:
        review_flags.append('historical_consensus_above_high_case')
    if abs(cons_dev) > CONS_DEV_MAX:
        review_flags.append('historical_consensus_differs_from_middle')
    consensus_below_mid = cons_mean < eps["m"]
    brent_cons = inp["brent_2025"] + (cons_mean * shares / MN - inp["ni_fy25"]) / beta

    # --- Step 5: 纠正对账门 coordinates (M moved > 25% from v2 10.51) ----------
    zero_g = band(g=0.0, b=0.0)
    r_vw = sum(v * r_leg[leg] for v, leg in zip(legs["m"], LEGS)) / sum(legs["m"])  # leg weights only, window excluded
    d1 = payout_fy25 * eps["m"] / fx * (1.0 + inp["g2_m"])
    ddm = d1 / (r_vw - inp["g2_m"])
    bps_hkd = inp["equity"] * MN / shares / fx
    coords = {
        "② E_M/r (逐腿 g 0)": zero_g[1],
        "③ D_M/(r̄−g)": ddm,
        "④ 同等盈利月份中位": inp["px_same_med"],
        "⑥ BPS × 5 年 PB 中位": bps_hkd * inp["pb_own_med"],
    }
    if all(abs(M / v - 1.0) > GATE_OUT for v in coords.values()):
        review_flags.append('historical_reference_coordinates_differ')

    for k in NOT_FORMULA:
        if k not in inp:
            errors.append(f"reference row missing from Inputs: {k}")
    if errors:
        raise ValueError('; '.join(errors))
    d = decompose((L, M, H), (pe_eff['l'], pe_eff['m'], pe_eff['h']))
    cases = {'gas_basket4': {'r': {**r_leg, 'r_ng': .10}}, 'g_low': {'g': inp['g2_m']-.01},
             'g_high': {'g': inp['g2_m']+.01}, 'zero_g': {'g': 0., 'b': 0.},
             'ep_basket7': {'r': {**r_leg, 'r_perp': .15}}, 'all_basket4': {'r': {k: .10 for k in r_leg}},
             'beta_lo': {'beta_x': beta_reg[0]}, 'beta_hi': {'beta_x': beta_reg[1]},
             'beta_v2': {'beta_x': beta_v2}, 'maint_zero': {'maint': 0.}, 'maint_all': {'maint': MAINT_ALL}}
    sensitivity = {key: band(**change) for key, change in cases.items()}
    g1 = (inp['eps_fy2022'] / inp['eps_trough_fy2020']) ** .5 - 1
    recovery = {'growth': g1, 'pe': recovery_two_stage_pe(g1, 2, inp['g2_m'], roe['m'], r_ep)}
    def band_rf(dr):
        return band(r={leg: value + dr for leg, value in r_leg.items()})
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0), (L, M, H))):
        raise ValueError('rate sensitivity base differs from anchors')
    result = {'ticker': '0857.HK', 'currency': 'HKD',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of': '2026-10-16',
            'anchors': dict(zip('LMH', (L, M, H))), 'option': None, 'candidate': None,
            'review_flags': review_flags,
            'r_leg': r_leg, 'brent': brent, 'rho': rho, 'slope_op': slope_op, 'beta': beta,
            'slope_v2': slope_v2, 'beta_v2': beta_v2, 'beta_theory': beta_theory,
            'beta_reg': beta_reg, 'ni': ni, 'eps': eps, 'e_owner': e_owner, 'roe': roe,
            'e_owner_m_mn': e_owner_m_mn, 'g2_derived': g2_derived, 'growth_used': g_used,
            'b_derived': b_derived, 'payout_fy25': payout_fy25, 'seg_sum': seg_sum,
            'share': share, 'legs': legs, 'win_ps': win_ps, 'L': L, 'M': M, 'H': H,
            'A': A, 'B': B, 'pe_eff': pe_eff, 'pe_e': pe_e, 'in_band': in_band,
            'cons_mean': cons_mean, 'cons_dev': cons_dev, 'consensus_below_mid': consensus_below_mid,
            'brent_cons': brent_cons, 'zero_g': zero_g, 'r_vw': r_vw, 'd1': d1, 'ddm': ddm,
            'bps_hkd': bps_hkd, 'coords': coords, 'd': d, 'sensitivity': sensitivity,
            'recovery': recovery}
    if rate_inputs is not None:
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r=dict(r_leg), band_at=band_rf,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H)))
    return result


def calculate(context):
    rungs = context['axes']['brent']['rungs']
    selected = {f'brent_{t}': rungs[t.upper()] for t in TIERS}
    result = evaluate({**INPUTS, **selected}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'brent': selected}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'HKD_PER_SHARE'}
    result['segments'] = {name: {'unit': 'HKD_PER_SHARE', 'values': {
        t.upper(): result['legs'][t][i] for t in TIERS}}
        for i, name in enumerate(('ep', 'gas', 'refining', 'marketing'))}
    result['segments']['window'] = {'unit': 'HKD_PER_SHARE',
                                    'values': dict.fromkeys('LMH', result['win_ps'])}
    result['key_parameters'] = {
        'ep': {'discount_rate': INPUTS['r_perp'], 'growth_rate': result['growth_used'],
               'project_return': INPUTS['roe_proj']},
        'gas': {'discount_rate': INPUTS['r_ng'], 'growth_rate': 0},
        'refining': {'discount_rate': INPUTS['r_rc'], 'growth_rate': 0},
        'marketing': {'discount_rate': INPUTS['r_mk'], 'growth_rate': 0},
        'forward_return': {t.upper():result['roe'][t] for t in TIERS},
    }
    result['review_flags'] += ['historical_capex_classification_unverified',
                               'historical_restated_and_unrestated_basis_mixed',
                               'historical_oil_sensitivity_and_constant_downstream_unverified']
    if not result['in_band']:
        result['review_flags'].append('historical_multiple_needs_review')
    if result['consensus_below_mid']:
        result['review_flags'].append('historical_consensus_below_middle')
    return result
