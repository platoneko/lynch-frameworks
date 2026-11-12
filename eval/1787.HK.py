#!/usr/bin/env python3
"""Shandong Gold's historical valuation; inputs retain the 2026 research.

This draft reads the shared gold axis and 601899.SH for the original checks.
Amounts are CNY or HKD as named; anchors and option are HKD per share.
"""
from __future__ import annotations
from math import isfinite
from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe
from lib.inputs import check_missing, require_whole_years
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'rf_report', 'partial_basis'),
                'axes': {'gold': 'fed_path_gold_copper'}, 'peers': {'zijin': '601899.SH'}}

# Original Inputs table: each value retains its source and as-of.
HISTORICAL_PARTIAL_FINGERPRINT = 'fea7a79184de07cb8df1915fd1e4d3711519dbfdd689b56bfa140505c77c3b95'

INPUTS = {
    # 总股本（A 36.144 + H 9.955 亿股）；AR25 / H26 | as-of 2026-06-30
    'shares': 46.099295,
    # 归母权益**不含永续债**（471.37 − 其他权益工具 140.05）；H26 资产负债表 | as-of 2026-06-30
    'equity': 331.317,
    # 净债务（不含永续债）= 有息负债 672.68 − 货币资金 173.26 − 交易性金融资产 26.81 − 大额存单约 42.4；只作披露（A12） | as-of 2026-06-30
    'net_debt': 429.9,
    # 永续债本金；杠杆门按债计入（A12），只作披露 | as-of 2026-06-30
    'perp_principal': 139.2,
    # USD→CNY，2026H1 平均；与 `601899.SH` 同值（eval 校验） | as-of 2026H1
    'fx_usd_cny': 6.8645,
    # HKD→CNY；yfinance `HKDCNY=X` | as-of 2026-10-08
    'fx_hkd_cny': 0.8543,
    # 金腿篮子 r：**篮 4 常规经营 10%**（A10）——与 `601899.SH` 金腿同篮（用户裁定）；金铜簇隐含 r 10.0% | as-of 2026-10-09
    'r_perp': 0.10,
    # 其余块（铅锌铜铁 + 外购金 / 小金条 / 贸易）篮子 r：**篮 6 周期商品 13%**（A10；同紫金其余块） | as-of 2026-10-09
    'r_rest': 0.13,
    # 金腿尾段 g2 = 商品腿 tier 默认 2.5%（A11）；cap = 6% | as-of 2026-10-09
    'g2_au': 0.025,
    # 其余块尾段 g2 = 0（A11） | as-of 2026-10-09
    'g2_rest': 0.0,
    # 金铜轴「永续 g2（2026-09-14）」行；**引用、不采用**（A11）；eval 校验与轴行相等 | as-of 2026-09-13
    # own-year PE（H 股）实测下沿（2024：年均价 15.38 港元 × 0.921 ÷ EPS 0.57 元）；**护栏、判失真只披露**（A6） | as-of 2026-10
    'pe_own_min': 24.8,
    # own-year PE 实测上沿（2022：13.92 × 0.859 ÷ 0.20）；**护栏、只披露**（A6） | as-of 2026-10
    'pe_own_max': 59.8,
    # **L（加息）**伦金 $/oz；真源 `_AXIS.fed-path-gold-copper`（A2） | as-of 轴 §1
    # **M（维持）**伦金 $/oz；真源同上 | as-of 轴 §1
    # **H（降息不衰退）**伦金 $/oz；真源同上 | as-of 轴 §1
    # 金实现率 = 2026H1 自产金实现价 1,029.98 元/克 ÷ (4,693 ÷ 31.1035 × 6.8645 = 1,035.74)；全档统一（A2） | as-of 2026H1
    'realization_au': 0.994437,
    # 当期自产金销量 = 2026H1 19.96 吨 × 2（H26 p.12） | as-of 2026H1
    'vol_cur_t': 39.92,
    # 自产金每克营业成本（含折旧）= 89.79 亿 ÷ 19.96 吨；按量变动（A3） | as-of 2026H1
    'unit_cost': 449.85,
    # 银等随金梯副产品毛利（亿 / 年 @M）=（其他收入毛利 13.456 − 铅锌铜铁毛利 2.079）× 2；随金价缩放 | as-of 2026H1
    'gp_ag': 22.754,
    # 其余块毛利（亿 / 年，三档固定）= 铅锌铜铁 2.079 × 2 + 外购金 / 小金条 / 贸易 1.683 × 2 | as-of 2026H1
    'gp_rest': 7.526,
    # 副产品收入（亿 / 年 @M；税金及附加基数）= 22.642 × 2 | as-of 2026H1
    'rev_byp': 45.283,
    # 税金及附加 ÷ 采选收入 = 12.92 ÷ (205.58 + 22.64) | as-of 2026H1
    'surch': 0.056611,
    # 期间费用（销售 1.607 + 管理 15.286 + 研发 3.730）× 2；固定 | as-of 2026H1
    'opex_fixed': 41.248,
    # 财务费用 8.461 × 2；固定 | as-of 2026H1
    'fin_cost': 16.921,
    # 非经营净额（其他收益 + 投资收益 + 公允价值变动剔除东海证券 7.05 亿 + 信用 / 资产减值 + 营业外）× 2 | as-of 2026H1
    'nonop': -0.635,
    # 有效税率 =（所得税 24.24 + 东海证券税盾 1.76）÷（利润总额 81.56 + 7.05） | as-of 2026H1
    'tax_rate': 0.293455,
    # 山金国际净利（100%）= 25.121 × 2（A4） | as-of 2026H1
    'np_sj': 50.242,
    # 山金国际采选收入（亿 / 年 @M）= 51.31 × 2；Longbridge `business-segments 000975.SZ` | as-of 2026H1
    'rev_sj': 102.62,
    # 山金国际块少数股东占比 = 18.615 ÷ 25.121（A4） | as-of 2026H1
    'nci_sj': 0.741015,
    # 其余子公司少数股东占比 =（21.889 − 18.615）÷（62.608 − 25.121） | as-of 2026H1
    'nci_oth': 0.08734,
    # 永续债利息（亿 / 年）= 2.464 × 2；在归母之后、普通股之前扣除（属性 B） | as-of 2026H1
    'perp_coupon': 4.928,
    # FY28 目标量 = 2025 自产金销量 48.386 + 双子山 5.0（A1） | as-of AR25 / H26
    'vol_target_t': 53.386,
    # L 档 FY28 量 = 2026 下调后指引中值（临2026-052） | as-of 2026-09-25
    'vol_l_t': 37.0,
    # M 档兑现率 = 2024–26 实际 ÷ 年初指引均值（0.982 / 0.978 / 0.755）（A1） | as-of 2026-09-25
    'ach_m': 0.905,
    # 双子山年产金（吨，归山金国际块）；M / H 计入、L 不计（A1） | as-of H26 p.18
    'th_t': 5.0,
    # 2026–28 增长性 capex（亿元；区间 120–215）；只作 ROIC 门分母（A7） | as-of 2026-10-09
    'growth_capex_26_28': 150,
    # 实付派息率 = FY2025 现金分红 16.35 亿 ÷ 普通股净利 42.32 亿；不进倍数（A5） | as-of 2025
    'payout_actual': 0.386,
    # **L** 视同派出打折 k；来源 ①：银泰收购 ROIC 10.8% ≥ r（A16） | as-of 2026-10-09
    'k_l': 0,
    # **M** 打折 k；来源 ① 同上 | as-of 2026-10-09
    'k_m': 0,
    # **H** 打折 k：原 0.27（1 − M/H）乘在多留部分上，按 valuation-rules「经营价值与超额现金」④ 去掉（A16）；H 档多留部分为 0，锚点不变 | as-of 2026-10-16
    'k_h': 0,
    # 两段式过渡年数：2026H1 年化 → FY28（A1） | as-of —
    'n_transition': 2,
    # 焦家矿区整合达产年产金（吨）；**\(V_{opt}\) 输入**（A15） | as-of AR25 p.34
    'jj_cap_t': 18.854,
    # 焦家金矿 2025 年产金（吨）；**\(V_{opt}\) 输入** | as-of AR25 p.15
    'jj_now_t': 5.55,
    # 新城整合达产年产金（吨）；**\(V_{opt}\) 输入** | as-of AR25 p.34
    'xc_cap_t': 7.771,
    # 新城金矿 2025 年产金（吨）；**\(V_{opt}\) 输入** | as-of AR25 p.15
    'xc_now_t': 4.70,
    # 焦家整合总投资（亿元）；**\(V_{opt}\) 未投资本输入** | as-of H26 p.18
    'jj_budget': 82.73,
    # 焦家整合截至 2026-06 累计投入（亿元） | as-of H26 p.18
    'jj_spent': 18.99,
    # 新城整合总投资（亿元） | as-of H26 p.18
    'xc_budget': 39.50,
    # 新城整合截至 2026-06 累计投入（亿元） | as-of H26 p.18
    'xc_spent': 18.49,
    # 分子起点年（2026H1 年化）；\(V_{opt}\) 折现终点 | as-of 2026-10-09
    't_num': 2026,
    # 整合增量兑现年 = 2028 + 2（无时点锚·拍值，A15） | as-of 2026-10-09
    't_opt': 2030,
    # 未投资本均摊起始年（2027–2030 均摊、按 `r_perp` 折回 `t_num`） | as-of 2026-10-09
    't_build0': 2027,
}

# Original historical rationale and evidence; comments are not extra model inputs.
# - **业务地图摘要**：对照分部启发式，命中 1 条（山金国际是独立上市子公司、少数股东份额 71%）；不命中「两块各 ≥20% 利润且驱动不同」——所有矿都是金价函数，外购金 / 小金条 / 贸易虽占收入一半以上，毛利只占 2%。卖方全部用整公司 PE（汇丰 9×、此前 18×）。故整公司一条利润桥，只在两处拆：① 山金国际单列少数股东口径（它的利润 74% 不归本票）；② 按篮子把铅锌铜铁 + 外购金 / 贸易块（年毛利 7.5 亿）单列篮 6，与紫金「其余块」同法。
# - **属性 A — 2026 是停产低谷，不是新常态的证据也不是一次性的证据**：公司指引 36–38 吨，H2 隐含约 17.9 吨（H1 19.10 吨）；原因一半是外部（同行事故后国内矿山停产自查），一半是自己选择（「主动统筹基建与生产」，整合工程加大建设、采矿作业面减少）。后一半意味着越是推进焦家 / 新城 / 三山岛整合，短期产量越受压——三档的兑现率阶梯就是在押这个张力（L 停在 37 吨、M 回到约 48 吨、H 53.39 吨）。历史先例：2021 年山东省内矿山停产整顿，矿产金 24.78 吨（−36%），2022 年恢复到 38.67 吨。
# - **属性 B — 三层摊薄：少数股东、永续债、黄金租赁**：① 山金国际（原银泰黄金，2023-07 以现金 125.97 亿取得控制，持股 28.89%）全额并表，2026H1 净利 25.12 亿中 18.61 亿归少数股东；② 永续债 140 亿计入权益，利息 4.93 亿 / 年在归母之后、普通股之前扣除——公司口径 EPS 已扣（附注原句：「扣除永续债利息后，本报告期归属于上市公司普通股股东的净利润为 3,296,738,618.34 元」）；本框架的权益、ROE、每股价值一律用**不含永续债**的普通股口径；③ 黄金租赁 163 亿记在借款里（年利率 1.85–2.4%），本框架计入有息负债。
# - **属性 C — 单位成本无披露，靠自算**：公司不披露克金完全成本 / AISC。本框架用「自产金营业成本 ÷ 自产金销量」：2024 约 293、2025 约 392、2026H1 约 450 元/克（含折旧、不含资源税与期间费用）；2026H1 同比 +30%（汇丰同数）一半是产量下降摊薄固定成本，一半是外包与深部开采。冻结在 450 对 M / H（量回升）偏保守、对 L 偏乐观（A3）。
# - **属性 D — 为什么是 `cyclical`**：普通股净利 2021 年 −3.99 亿 → 2022 年 8.93 亿 → 2025 年 42.32 亿；own-year PE（H 股）2022 年 59.8×、2024 年 24.8×；盈利随金价与产量两段 regime。扩产（焦家 / 新城 / 三山岛—西岭整合）是叙事，不是副类。
# - **属性 E — 与 `601899.SH` / `NEM.US` 同轴同篮同构**：同一条金梯（3,942 / 4,693 / 5,000）、同一个 `fx_usd_cny` 6.8645（与紫金逐格校验）、金腿同归篮 4、尾段 g2 同为 2.5%、同一套两段式 + ROIC 门。差别只在输入：本票单位成本高、杠杆与少数股东重，故下行最深（L/M 0.42 vs 紫金 0.60、NEM 0.68）、上行最宽（H/M 1.36 vs 1.29 / 1.17）。轴的第四情景（衰退式降息：金涨铜跌）对本票是纯利好（无铜腿）。
# | A1 | **分子 = 前瞻产量 53.39 吨 × 兑现率阶梯**：目标 = 2025 自产金实测销量 48.39 吨 + 纳米比亚双子山 5 吨（山金国际，「建成后年产金 5 吨」、预计 2027 年上半年投产，预算 36.54 亿、已投 11.85 亿）；按 2028 处理（n = 2）。L = 停在 2026 下调后指引中值 37 吨（兑现率 0.693）；M = 2024–26 三年「实际 ÷ 年初指引」均值 0.905（46.17/47 = 0.982、48.89/50 = 0.978、37/49 = 0.755）→ 48.31 吨；H = 1。公司无「十五五」产量目标（「编制完成后适时披露」），目标是自下而上拼的；汇丰 2025–28E 产量 CAGR 约 4%（≈ 55 吨）作印证。焦家 / 新城整合增量无投产年份，不进分子（→ A15） | active | 临2026-052（2026-09-25）；AR25 p.12/18、产销量表；H26 p.12/18（双子山）；汇丰 2026-10-07（Wisburg 108814）；摩根大通 2026-10-09（109053：影响延续到 2027） | `vol_target_t` / `vol_l_t` / `ach_m` / `th_t`；**证伪**：2027 年指引 < 44 吨 → M 兑现率下调；公司披露「十五五」目标 → 目标改公司口径 |
# | A2 | **金价三档 = `_AXIS.fed-path-gold-copper.md` 金梯**（3,942 / 4,693 / 5,000），`fx_usd_cny` 6.8645 与 `601899.SH` 同值，eval 对轴与紫金逐格校验；实现率 = 2026H1 自产金实现价 1,029.98 元/克 ÷ 轴 M 折人民币 1,035.74 = 0.9944，全档统一；银等副产品毛利按金价同比例缩放 | active | 轴 §1；H26 附注七.61（自产金收入 205.58 亿 ÷ 销量 19.96 吨） | `lme_au_*` / `realization_au` / `fx_usd_cny`；改梯先改轴 |
# | A3 | **成本：自产金营业成本（含折旧）按量变动、每克冻结 449.85 元**；期间费用 41.25 亿、财务费用 16.92 亿、非经营净额 −0.63 亿固定；税金及附加按采选收入 5.66%；税率 29.35%（剔除东海证券后口径）。2026H1 每克成本含停产摊薄，量回升时偏保守、L 档偏乐观 | active | H26 合并利润表 p.72–73；附注七.61；东海证券 7.05 亿与 25% 税盾：公司口径剔除后归母 40.72 亿（H26 p.7） | `unit_cost` / `opex_fixed` / `fin_cost` / `nonop` / `surch` / `tax_rate` |
# | A4 | **少数股东两块**：山金国际块 = 2026H1 净利 25.12 亿 × 2，按自身采选收入 102.62 亿 / 年随金价变动、双子山 5 吨归它，其中 **74.10%** 归少数股东（H26 主要子公司少数股东表：本期归属少数股东 18.61 亿 ÷ 25.12 亿）；其余各子公司（Namdini 15%、归来庄、西和中宝、赤峰等）合计 **8.73%** | active | H26 附注九（山金国际少数股东持股 71.06%、本期损益 1,861.49 百万）；Longbridge `business-segments 000975.SZ`（2026H1 采选 51.31 亿） | `np_sj` / `rev_sj` / `nci_sj` / `nci_oth` |
# | A5 | **年初权益 B27 = 331.32 亿（归母权益不含永续债）+ b1 ×（2026H2 + FY27 普通股利润）（b1 = g1/ROE28 联立：L 0% / M 40% / H 62%）；ROE28 = 10.5% / 24.2% / 29.9%**。实付派息 38.6%（FY2025 现金分红 16.35 亿 ÷ 普通股净利 42.32 亿）；「模型视同派出、实际留存的现金/股」= (61.4% − b1) × 窗口累计 EPS，只作披露，是锚点前提（留存不被高价并购烧掉）而非额外价值；H 档 b1 62% 略高于实付留存 61.4%，模型派息 38% ≈ 实付，差 0.6pp 只披露 | active | AR25 p.2/67（2025 全年每股 0.35467 元、派息率 38.63%）；H26 资产负债表 | `equity` / `payout_actual` |
# | A6 | **倍数 = 两腿两段式（n = 2，段一派息 1 − g1/ROE28）+ 尾段 Gordon**；**③ 护栏判「不可判定」（带失真），不拦**：own-year PE（H 股，年均价 ÷ 当年 EPS，转增调整）2019–25：33.0 / 32.8 / 亏损 / 59.8 / 32.8 / 24.8 / 25.4 → 带 [24.8, 59.8]，生成倍数 9.95 / 12.87 / 14.79 全在下沿之下。逐步核验：步 0 无 FY2027+ 共识可换分子；步 1 M 档当期 EPS 1.66 元从未实测（TTM 最高 1.09）→ 无同等盈利月份，改查 L 档：L 当期 EPS 0.90 元 ±12% 的月份 = 2025-09 至 2026-08（TTM 1.03–1.15 港元），月度最低 PE 14.5×（2026-06）、中位 16.6–37.4×，L 档 9.95× 在其下；步 1b 那几个月市场看到的 FY2026 共识 EPS 1.6–2.0 元，对 TTM 约 1.0 元隐含 +60–100%，现模型 L 档 g1 −8.7% → 差远超 10pp/年 → **带失真**（市场按后来落空的翻倍预期定价）；故不据带降篮、不带边反推，走纠正对账门（下行 A13）。**A2d**：① 研报：汇丰 9× 目标 PE（原 18×）、TP H 22 港元；Longbridge 6 家 H 股 TP 均值 30.39（21.20–46.18，2026-10-06，未完全反映 10 月下调）；② EPS 桥：当期 M 档 1.66 元 vs FY2026E 共识 1.585 元 → +4.7%（当期 = H1 年化，H2 指引更低，共识将继续下修）；③ ROE28 单调区（M 24.2% ≥ r + 3pp），L 10.5% 病态区；④ 股息交叉：M 模型派息 60% vs 实付 39%；⑤ PEG 12.87 ÷ 9.7 = 1.3（周期票只记录）；⑥ 同业同尺：NEM 合并等效 12.58×、紫金 13.32× | active | `_local` 价格序列（Longbridge kline，转增调整）；Longbridge consensus / institution-rating 2026-10-06；Wisburg 108814 / 109053 | `pe_own_min` / `pe_own_max`（护栏、只披露） |
# | A7 | **ROIC 门**：增长性 capex 2026–28 = 150 亿（区间 120–215：资本开支 2025 年 129.3 亿、2026H1 58.7 亿，减折旧约 65 亿 / 年；具名剩余预算：焦家整合 63.7、新城整合 21.0、三山岛扩界扩能 99.7、双子山 24.7、东风 5.1 亿）；边际 ROIC L −4.6% / **M 10.4%（贴门）** / H 24.5%。L 不过门且利润下行 → g1 取实测 −8.7%（关门只扣增长 credit，不把下行抬成增长）；M 在 capex ≥ 157 亿时不过门 → M 23.25。分母含 2028 年后才产出的焦家 / 三山岛资本，使门偏严（同 `NEM.US` A7） | active | AR25 p.34 / H26 p.18 重大非股权投资表；AR25 附注七.22 在建工程预算表；Longbridge 现金流量表 | `growth_capex_26_28`；**待补**：公司分年资本开支计划 |
# | A8 | **桥回代**（valuation-rules「桥 MUST 复现实测年」）：用该年自己的量、实现价与每克成本，其余项按 2026H1 结构：2024 普通股利润模型 23.7 亿 vs 实测 25.5 亿（−7%）；2025 模型 60.7 亿 vs 实测 42.3 亿（+43%），剔除东海证券公允价值损失 11.73 亿、资产减值 7.99 亿、营业外支出 3.74 亿（滞纳金 / 报废）后实测约 59 亿（+2%）——2025 年还含黄金期货 / T+D 套保亏损 8.82 亿（2026-07 起改用套期会计） | active | AR25 利润表与附注七.70 / p.16–17 | 桥成立；套保损益不进模型 |
# | A9 | **卖方 2027E / 2028E 产量与 EPS 共识 `待补`**（Longbridge 只给当前财年；Wisburg 2026 年仅汇丰、摩根大通两篇摘要） | active | `_local` 取数记录 | 取到 ≥2 家后：兑现率改共识、FY28 分子对账 |
# | A10 | **归篮：金腿（自产金 + 银等副产品）→ 篮 4 常规经营 r 10%**，与 `601899.SH` 金铜银腿、`NEM.US` 金银铜腿同篮（用户 2026-10-09 裁定：与紫金一致）。依据：① 同一门生意同一把尺——金铜簇 25 家固定 g 反解隐含 r 10.0%（`601899.SH` A21 / A26）；② 本票自身带失真（A6），不能单独证明 r 高于或低于篮 4。**初分篮留痕**：按「盈利是商品价函数」本应归篮 6（13%），对照带 L/M/H = 8.10 / 16.73 / 23.68 港元（Outputs 对照行）。**其余块（铅锌铜铁 + 外购金 / 小金条 / 贸易）→ 篮 6 r 13%**（同紫金其余块）。CAPM 粗筛未做（β 对商品价函数的盈利失真，同 `601899.SH` A26），以金铜簇隐含 r 对账替代 | active | valuation-rules「§r 篮子」；`601899.SH` A21 / A26；用户裁定 2026-10-09 | `r_perp` / `r_rest`；**证伪**：季度篮级对账把金铜簇隐含 r 推回 13% 邻域 → 金腿回篮 6（随紫金一起动） |
# | A11 | **尾段 g2：金腿 2.5%（商品腿 tier 默认：通胀 + 金价长期实际漂移 ≈ 0），其余块 0；轴「永续 g2」行 2.6% 引用不采用**（同 `NEM.US` A11 / `601899.SH` A21） | active | 轴 §1「永续 g2」行 | `g2_au` / `g2_rest` / `axis_g2_aucu` |
# | A12 | **杠杆门未触发（按中枢口径），实测年触发并披露**：净债务 = 有息负债 672.7 亿（含黄金租赁）+ 永续债 140.1 亿（归类为债）− 货币资金 173.3 − 交易性金融资产 26.8 − 大额存单约 42.4 ≈ 570 亿；M 档当期 EBITDA（报表营业利润剔除东海证券 177.7 + 折旧摊销 65.4）≈ 243 亿 → **2.35 倍**；利息（财务费用利息 17.39 + 永续债息 4.93）÷ EBIT 177.7 = **12.6%**——未触发。实测 FY2025：净债务 594 亿 ÷ EBITDA 166.8 亿 = **3.56 倍（> 3，触发）**、利息 24.4 ÷ EBIT 93.9 = 26%。不改尺，但报利率 +100bp：有息负债 + 永续债 812.8 亿 × 1% × (1 − 29.35%) × (1 − 8.73%) ≈ 5.2 亿 → 普通股 EPS −0.11 元（M 当期 −6.8%） | active | H26 借款附注七.32/45、其他权益工具附注七.54；AR25 利润表；现金流量表补充资料 | 敏感行；`net_debt` / `perp_principal` 只作披露 |
# | A13 | **纠正对账门（初建、③ 判不可判定时 MUST）**：M = 25.00 港元（21.36 元）对照独立坐标——② E_M / r = 1.66 / 0.10 = 16.6 元（−22%）；③ 股息尺 D_M/(r − g2) = 0.386 × 1.66 / 0.075 = 8.5 元（M 不是股息尺，只印）；④ 同等盈利月份：无（M 档 EPS 未实测）；⑤ **同业同尺同日**：NEM 合并等效 12.58× / 紫金 13.32× × 本票 1.66 元 = 20.9–22.1 元（落在内）；⑥ 资产口径：普通股每股净资产 7.19 元，own PB 带 `待补`。M 落在 ⑤ 之内 → 对账通过。中性带 [17.75, 29.55) 港元折 [15.17, 25.24) 元：对 TTM EPS 1.09 元 = 13.9–23.2×；对 M 当期 1.66 元 = 9.1–15.2×；对 FY2026E 共识 1.585 元 = 9.6–15.9× | active | 同 A6 / A10 | Outputs「③ 出带」行 |
# | A14 | **②-b**：FY2026E 共识均值 1.585 元落在 [当期 L 0.90, 当期 H 1.97] ✓；M 当期 1.66 元偏离 +4.7% ✓ → 情景梯保留。汇丰下调 54% 尚未完全进入共识；若共识跌到 1.33 元以下（M 偏离 > 20%），已实测的解释变量 = H2 指引隐含 17.9 吨 + 金价回落，属 A1 停产低谷，不改 M 但 MUST 复核 | active | Longbridge forecast-eps 2026-10-06 | 下期财报重跑「M 档当期 ≡ H1×2」（±1%） |
# | A15 | **\(V_{opt}\) = 11.46 港元：焦家 + 新城整合达产增量**（valuation-rules「未建模期权」：份数只来自本票具名的量；单位经济取本票；新建产能 MUST 扣未投资本）。**份数**：焦家矿区整合「达产后采矿 660 万吨/年，年产金 18,854 kg」− 2025 焦家 5,550 kg = 13.30 吨；新城整合「年产金 7,771 kg」− 2025 新城 4,700 kg = 3.07 吨；合计 16.38 吨，两矿 100% 持有。**无投产年份 → 兑现年 = 2028 + 2 = 2030（无时点锚·拍值）**。**单位经济**：M 档实现价 1,030 元/克 − 每克成本 449.85 − 税金及附加 5.66% → 税后 3.687 亿/吨 → 增量普通股利润 60.37 亿。**本票的尺**：金腿稳态 Gordon（g2 2.5%、篮 4 10%），H 档 ROE28 加增量 = 44.1% → 12.58×；2030 估值折回 2026（× 0.683）= 毛值 13.17 港元。**未投资本**：焦家预算 82.73 − 已投 18.99 + 新城 39.50 − 18.49 = 84.75 亿，2027–30 均摊、按 10% 折回 2026 = 1.71 港元/股 → \(V_{opt}\) = **11.46**。\(p_k\) = 0 / 0.25 / 1.0，\(p_M\) **无概率锚·拍值**。**偏差方向**：① 焦家「18,854 kg」含浮选精矿 29.06 吨含金，整合范围若含 2025 年已计入其他矿的产量，份数偏高；② 深部开采成本可能高于 2026H1 均值，偏高；③ 整合期挤占现有作业面（属性 A），其损失已在 L / M 兑现率里，不在本项。**三山岛—西岭 15,000 吨/日扩建（预算 120.52 亿，核准批复预计 2026-09 底）无设计产量、无投产日 → 份数 `待补`、不入 \(V_{opt}\)**，只作 `stretched` 解释。**升级门槛**：公司披露投产年 / 「十五五」产量 → 兑现年与份数按公司口径；≥2 家卖方给出覆盖该年的产量 → 并入底牌分子；单家 → 候选带。**证伪**：项目延期公告或预算上调 > 30% → 重算 | active | AR25 p.34 / H26 p.18 重大非股权投资表（焦家 82.73 亿 / 累计 18.99 亿；新城 39.5 亿 / 累计 18.49 亿）；AR25 p.15–16 分矿产量 | Outputs `V_opt` 行；表3；`jj_*` / `xc_*` / `t_*` |
# | A16 | **「视同派出现金」打折 k = 0 / 0 / 0（H 档原 0.27 去掉，锚点不变）**：原 k 乘在「多留部分」（模型视同派出、实际留存的现金）上——按 valuation-rules「经营价值与超额现金」④，多留部分落在现金上归 λ（默认 1，无「钱回不到股东」的具名证据），k 只留给具名交易；本票 H 档多留部分本为 0，去掉不改任何锚点。以下为原审计记录（留存去向审计「打折 k」）。**留存去向审计**：capex 2019–25 = 41.7 / 48.8 / 35.6 / 42.1 / 91.8 / 201.0（含西岭探矿权 103 亿分期）/ 129.3 亿，固定资产净值 234.6（2018）→ 661.9 亿（2025），净债务（不含永续债）37 → 477 亿——**D 桶增长窗口**（具名项目：焦家 / 新城 / 三山岛整合、双子山，预算与进度见 A7 / A15），窗口终点 2030（A15 兑现年），窗口后触发：capex 回落到折旧 ±20% 连续两年 → 转 C 桶；双算防线：焦家 / 新城的产出只在 \(V_{opt}\)，其未投资本已在 \(V_{opt}\) 里扣。**k 来源 ①**：近 5 年大额现金收购——银泰黄金（2023-07，125.97 亿现金 + 原持股 8.18 亿 → 28.89%）：山金国际 2026H1 年化净利 50.24 亿 × 28.89% = 14.5 亿 ÷ 134.15 亿 = 10.8% ≥ 10% → 0；西岭探矿权 103.34 亿（关联交易、尚未产出）不可算、同属三山岛整合 D 桶 → L / M 0。**①b**：H 档 k = 1 − M/H = 1 − 25.00 / 34.10 = 0.27；H 档实付留存 61.4% < b1 62%，视同派出 = 0，k 不起作用 | active | AR21–25 现金流量表；AR23 合并成本表；AR25 p.95 重大合同表 | `k_l/k_m/k_h`；eval 校验 \(0 \le k_L \le k_M \le k_H \le 1\) |
# | A17 | **独立成交价护栏**：山金国际不是本框架的独立腿（并在金腿与少数股东块里），按适用条件不触发；读数：本票 M 档对山金国际的权益价值 ≈ 当期净利 50.24 × 25.9% × 12.87 = 167 亿 ≥ 调整后成交价 134.15 亿（未扣交割后分红）。Cardinal（Namdini，2021-03 交割）超 5 年；西岭为关联方资产收购 → 不适用 | active | AR23 合并成本表 | 读数，只披露 |
# | A18 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」，2026-10-16 框架纠正，锚点不变）**：① **超额现金未单列**——净债务（不含永续债）477 亿（2025 年末），2026-06-30 合并有息负债 672.7 亿、现金类 200.1 亿（yfinance），扩展口径净现金为负 → \(C_{ex}\) = 0，低于归母权益 15% 门槛，利润与 RONIC 用合并口径；归母比例不涉及（无现金行），山金国际 74.1% 少数股东已在利润桥里扣；② **增长期资金缺口 0**：时点对齐不适用 → 无窗口；焦家 / 新城整合的产出在分子年之后，未投资本已在 \(V_{opt}\) 里扣（A15）；③ **时点对齐不适用**：两段式起点 = 2026H1 年化当期（规则边界「当期年化 / 金铜两段式起点」），τ = 0；\(V_{opt}\) 已折到 `t_num`，不动；④ **稳态回报三段不适用（商品腿豁免）**：g2 > 0 的只有金腿，分子由 `_AXIS.fed-path-gold-copper` 金梯桥出，永续段沿用该档 ROE28；三档世界都写成持续（M「2026H1 金价延续」、H「降息但不衰退」），不属「路过」；余腿 g2 = 0 不受影响；⑤ **k**：见 A16（H 档 k 去掉，无保留的 k） | active | 2026 中报；valuation-rules「经营价值与超额现金」①②③④ | 披露；锚点不变 |

OZ_TO_G = 31.1035
MIN_R_MINUS_G = 0.02
TOL = 0.05
TIERS = ("l", "m", "h")
LEGS = {"au": ("r_perp", "g2_au"), "rest": ("r_rest", "g2_rest")}
BASKET4_LEGS = {"au"}
H1_2026_X2_COMMON = 76.51   # 亿元: (6,260.76 − 2,188.90 − 246.38) 百万 × 2, Donghai stripped (M guard)
H1_TOL = 0.01
LISTING_CCY = "HKD"
# 表3 only — never Inputs, never the base band (construction §7a).  p_M: no production year, no anchor.
P_K = (0.0, 0.25, 1.0)

REQUIRED = [
    "shares", "equity", "net_debt", "perp_principal", "fx_usd_cny", "fx_hkd_cny",
    "lme_au_l", "lme_au_m", "lme_au_h", "realization_au",
    "vol_cur_t", "unit_cost", "gp_ag", "gp_rest", "rev_byp",
    "surch", "opex_fixed", "fin_cost", "nonop", "tax_rate",
    "np_sj", "rev_sj", "nci_sj", "nci_oth", "perp_coupon",
    "vol_target_t", "vol_l_t", "ach_m", "th_t",
    "growth_capex_26_28", "payout_actual", "n_transition", "k_l", "k_m", "k_h",
    "r_perp", "r_rest", "g2_au", "g2_rest", "axis_g2_aucu", "pe_own_min", "pe_own_max",
    "jj_cap_t", "jj_now_t", "xc_cap_t", "xc_now_t",
    "jj_budget", "jj_spent", "xc_budget", "xc_spent", "t_num", "t_opt", "t_build0",
]

def price(inp: dict[str, float], tag: str) -> float:
    """Realised gold 元/克 at the tier rung."""
    return inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]


def year(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    """One tier-year P&L in 亿元 (volumes in tonnes; 1 t × 1 元/克 = 0.01 亿)."""
    p = price(inp, tag)
    k = p / price(inp, "m")
    if forward:
        vol = inp["vol_l_t"] if tag == "l" else inp["vol_target_t"] * (inp["ach_m"] if tag == "m" else 1.0)
        th = 0.0 if tag == "l" else inp["th_t"]
    else:
        vol, th = inp["vol_cur_t"], 0.0
    gp_au = vol * (p - inp["unit_cost"]) / 100
    gp_ag = inp["gp_ag"] * k
    surch = inp["surch"] * (vol * p / 100 + inp["rev_byp"] * k)
    pbt = gp_au + gp_ag + inp["gp_rest"] - surch - inp["opex_fixed"] - inp["fin_cost"] + inp["nonop"]
    np_ = pbt * (1 - inp["tax_rate"])
    after = (1 - inp["surch"]) * (1 - inp["tax_rate"])
    np_sj = inp["np_sj"] + inp["rev_sj"] * (k - 1) * after + th * (p - inp["unit_cost"]) / 100 * after
    nci = inp["nci_sj"] * np_sj + inp["nci_oth"] * (np_ - np_sj)
    common = np_ - nci - inp["perp_coupon"]
    w_rest = inp["gp_rest"] / (gp_au + gp_ag + inp["gp_rest"])
    return {"vol": vol, "p": p, "pbt": pbt, "np": np_, "np_sj": np_sj, "nci": nci, "common": common,
            "eps": common / inp["shares"], "w_rest": w_rest}


def tier(inp: dict[str, float], tag: str, r_shift: float = 0.0) -> dict:
    cur, fwd = year(inp, tag, False), year(inp, tag, True)
    n = int(inp["n_transition"])
    lc = {"au": cur["eps"] * (1 - cur["w_rest"]), "rest": cur["eps"] * cur["w_rest"]}
    l28 = {"au": fwd["eps"] * (1 - fwd["w_rest"]), "rest": fwd["eps"] * fwd["w_rest"]}
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["common"] - cur["common"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"] + r_shift
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    # Gate closed withholds growth credit; a decline is not growth and passes through.
    g1 = g1_raw if gate else {k: min(g1_raw[k], g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"]
    roe = fwd["common"] / inp["equity"]
    for _ in range(80):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["common"] / b27
        if abs(roe_new - roe) < 1e-12:
            break
        roe = roe_new
    r = {k: inp[r_key] + r_shift for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    pre_k = sum(contrib.values())
    cash = max((1 - inp["payout_actual"]) - b1, 0.0) * (cum_roll + fwd["common"]) / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash
    fx = inp["fx_hkd_cny"]
    return {"cur": cur, "fwd": fwd, "lc": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co, "roic": roic, "gate": gate,
            "b1": b1, "b27": b27, "roe28": roe, "pe": pe, "contrib": contrib, "eq_pe": pre_k / cur["eps"],
            "cash": cash, "haircut": haircut, "pre_k": pre_k, "anchor_cny": pre_k - haircut,
            "anchor": (pre_k - haircut) / fx}


def integration_option(inp: dict[str, float], th: dict) -> dict[str, float]:
    """V_opt — 焦家 / 新城 integration increments (A15).

    Size: company-named design output less 2025 output, both mines 100% owned.
    Unit economics: own M-tier realised price less own 2026H1 unit cost, own
    resource-tax ratio and tax rate.  Ruler: own steady-state Gordon on the gold
    leg at the H-tier ROE28 lifted by the increment; valued in t_opt, discounted
    at the basket r to t_num; unspent budget spread over t_build0..t_opt.
    """
    p = price(inp, "m")
    per_t = ((p - inp["unit_cost"]) / 100 - inp["surch"] * p / 100) * (1 - inp["tax_rate"])
    inc = (inp["jj_cap_t"] - inp["jj_now_t"]) + (inp["xc_cap_t"] - inp["xc_now_t"])
    d_np = inc * per_t
    roe_post = (th["fwd"]["common"] + d_np) / th["b27"]
    pe_post = perpetual_pe(inp["g2_au"], roe_post, inp["r_perp"])
    disc = (1 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    gross = d_np / inp["shares"] * pe_post * disc
    k_unspent = (inp["jj_budget"] - inp["jj_spent"]) + (inp["xc_budget"] - inp["xc_spent"])
    years = range(int(inp["t_build0"]), int(inp["t_opt"]) + 1)
    pv_k = sum(k_unspent / len(years) * (1 + inp["r_perp"]) ** (-(t - inp["t_num"])) for t in years)
    fx = inp["fx_hkd_cny"]
    return {"per_t": per_t, "inc": inc, "d_np": d_np, "roe_post": roe_post, "pe_post": pe_post, "disc": disc,
            "gross": gross / fx, "k": k_unspent, "k_ps": pv_k / inp["shares"] / fx,
            "v_opt": (gross - pv_k / inp["shares"]) / fx}


def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('n_transition', 't_num', 't_opt', 't_build0'))

    baskets = {"r_perp": 4, "r_rest": 6}
    for leg, (r_key, g_key) in LEGS.items():
        if r_key not in baskets:
            errors.append(f"{r_key}: Inputs source cell names no 篮 N")
        errors += check_r(inp[r_key], r_key, baskets.get(r_key))
        errors += check_g_cap(inp[g_key], inp[r_key], g_key)
        if inp[r_key] - inp[g_key] < MIN_R_MINUS_G:
            errors.append(f"{leg}: r − g below pole margin")
    if baskets.get("r_perp") != 4:
        errors.append("r_perp must be 篮 4 (same as 601899.SH gold leg, A10)")
    if not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]):
        errors.append("gold ladder order violated")
    if not (0 < inp["vol_l_t"] < inp["vol_target_t"] * inp["ach_m"] < inp["vol_target_t"]):
        errors.append("volume ladder L < M < H violated")
    if not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2 or inp["equity"] <= 0:
        errors.append("payout_actual / n_transition / equity invalid")
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k}")
    if errors:
        raise ValueError('; '.join(errors))
    # Gold prices and common growth reference come from the bound machine axis.
    rungs = {'au': {t.upper(): inp[f'lme_au_{t}'] for t in TIERS}}

    T = {t: tier(inp, t) for t in TIERS}
    cur_m = T["m"]["cur"]
    if abs(cur_m["common"] / H1_2026_X2_COMMON - 1) > H1_TOL:
        errors.append(f"M guard: run-rate common {cur_m['common']:.2f} vs H1×2 {H1_2026_X2_COMMON:.2f}")
    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")
    for t in TIERS:
        recomb = sum(T[t]["lc"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["au"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder broken")
    if errors:
        raise ValueError('; '.join(errors))
    A, B = (L + M) / 2, (M + H) / 2
    opt = integration_option(inp, T['h'])
    if not (inp['t_num'] < inp['t_build0'] <= inp['t_opt']) or opt['k'] < 0:
        raise ValueError('option build years, value or remaining capex invalid')
    band3 = tuple(base + P_K[i] * opt['v_opt'] for i, base in enumerate((L, M, H)))
    def band_with(**over):
        alt = dict(inp, **over)
        return tuple(tier(alt, t)['anchor'] for t in TIERS)
    cases = {'growth_low': {'g2_au': inp['g2_au'] - .01},
             'growth_high': {'g2_au': inp['g2_au'] + .01},
             'basket6': {'r_perp': .13}, 'ach_m_95': {'ach_m': .95},
             'volume_37': {'vol_cur_t': 37.}, 'capex_180': {'growth_capex_26_28': 180.}}
    sensitivities = {key: band_with(**change) for key, change in cases.items()}
    sensitivities['gold_mid_minus_100'] = tier(dict(inp, lme_au_m=inp['lme_au_m']-100), 'm')['anchor']
    sensitivities['gold_mid_plus_100'] = tier(dict(inp, lme_au_m=inp['lme_au_m']+100), 'm')['anchor']
    def band_rf(dr):
        return tuple(tier(inp, t, r_shift=dr)['anchor'] for t in TIERS)
    result = {'ticker': '1787.HK', 'currency': 'HKD',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of': '2026-10-16',
            'anchors': dict(zip('LMH', (L, M, H))), 'candidate': None,
            'option': {'value': opt['v_opt'], 'weights': dict(zip('LMH', P_K)),
                       'anchors': dict(zip('LMH', band3))},
            'rungs': rungs, 'T': T, 'flat': flat, 'L': L, 'M': M, 'H': H, 'A': A, 'B': B,
            'opt': opt, 'band3': band3, 'sensitivities': sensitivities,
            }
    if rate_inputs is not None:
        def checked_band(dr):
            if min(inp['r_perp'], inp['r_rest']) + dr <= max(inp['g2_au'], inp['g2_rest']):
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp': inp['r_perp'], 'r_rest': inp['r_rest']}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    gold = context['axes']['gold']
    if gold.get('role') != 'priced':
        raise ValueError('Shandong Gold requires the priced gold-axis role')
    fields = gold['stock_fields']
    shared = {key: fields[key] for key in ('lme_au_l', 'lme_au_m', 'lme_au_h', 'axis_g2_aucu')}
    result = evaluate({**INPUTS, **shared}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'shared': shared, 'tiers': TIERS, 'legs': LEGS,
         'basket4_legs': sorted(BASKET4_LEGS), 'option_weights': P_K,
         'ounce_to_grams': OZ_TO_G, 'minimum_rate_gap': MIN_R_MINUS_G,
         'historical_profit': H1_2026_X2_COMMON, 'historical_tolerance': H1_TOL}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'HKD_PER_SHARE'}
    tiers, fx = result['T'], INPUTS['fx_hkd_cny']
    result['segments'] = {
        'gold': {'unit': 'HKD_PER_SHARE', 'values': {t.upper(): tiers[t]['contrib']['au'] / fx for t in TIERS}},
        'other': {'unit': 'HKD_PER_SHARE', 'values': {t.upper(): tiers[t]['contrib']['rest'] / fx for t in TIERS}},
        'retained_cash_adjustment': {'unit': 'HKD_PER_SHARE', 'values': {t.upper(): -tiers[t]['haircut'] / fx for t in TIERS}},
    }
    if result['option']['value'] >= 0:
        result['option']['value_unit'] = 'HKD_PER_SHARE'
    else:
        result['option'] = None
        result['option_unavailable_reason'] = 'project_increment_below_unspent_capital'
    result['key_parameters'] = {
        'gold_discount': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['r_perp'])},
        'other_discount': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['r_rest'])},
        'gold_growth': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['g2_au'])},
        'other_growth': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['g2_rest'])},
        'forward_return': {'unit': 'RATIO', 'values': {t.upper(): tiers[t]['roe28'] for t in TIERS}},
    }
    result['review_flags'] = ['historical_project_overlap_and_cost_unverified',
                              'historical_incremental_capex_and_production_assumptions']
    # The peer's numeric FX field is optional during staged migration.  Do not
    # parse its prose or claim alignment when the saved peer result lacks it.
    peer = context.get('peers', {}).get('zijin')
    peer_currency = peer.get('currency_inputs') if isinstance(peer, dict) else None
    peer_fx = peer_currency.get('usd_cny') if isinstance(peer_currency, dict) else None
    result['currency_inputs'] = {'usd_cny': INPUTS['fx_usd_cny']}
    if isinstance(peer_fx, bool) or not isinstance(peer_fx, (int, float)) or not isfinite(peer_fx):
        result['review_flags'].append('historical_cross_stock_exchange_rate_unverified')
    elif abs(peer_fx - INPUTS['fx_usd_cny']) > 1e-9:
        result['review_flags'].append('historical_cross_stock_exchange_rate_mismatch')
    return result
