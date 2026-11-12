#!/usr/bin/env python3
"""SMIC's historical core, advanced-node and mature-return scenarios.

Original 2026 inputs and the shared foundry ruler are retained; values are HKD
per share. This is a research draft, not a new forecast or publication.
"""
from __future__ import annotations
from lib.gordon import check_branch, check_g_cap, check_r, payout_gap, perpetual_pe
from lib.inputs import check_missing, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries':('gordon','inputs','partial_basis','rf_report'),
                'axes':{'foundry':'leading_edge_foundry'}}
HISTORICAL_PARTIAL_FINGERPRINT = '1bd35457b5f16363195befc76a1eacb24218615165f035fb62bdddf94ecc7a15'

# Original inputs, each with its source, intent and as-of.
INPUTS = {
    # 整公司永续折现率 · 篮 4 常规经营：盈利不是商品价函数，客户不集中（第一大 8.0%），不命中篮 7（A5） | as-of 2026-10-08
    'r_perp': 0.10,
    # 永续增速：具名 g = 0（三档 ROE ≤ r + 3pp，增长不创造价值；A4） | as-of 2026-10-08
    'g2': 0.0,
    # 总股本（百万股；H 6,014.06 + A 2,546.74；2026 半年报） | as-of 2026-06-30
    'shares': 8560.805995,
    # 归母权益（百万元；2026 半年报合并资产负债表） | as-of 2026-06-30
    'eq_h1_cny': 171456.605,
    # 2026H1 归母净利润（百万元；2026 半年报主要会计数据） | as-of 2026-06-30
    'ni_h1_cny': 4467.431,
    # 港元 / 美元（联系汇率中值；2Q26 港元收入 23,566 ÷ 美元收入 3,005.6 = 7.84 交叉） | as-of 2026-10-08
    'fx_usdhkd': 7.80,
    # 人民币 / 港元（Longbridge `ah-premium` currency_rate） | as-of 2026-10-07
    'fx_hkdcny': 0.8544,
    # FY2026E 归母净利润共识（百万美元；MarketScreener 23 家），用于滚 2H26 未入账利润 | as-of 2026-10-08
    'ni_fy26_usd': 1384,
    # L：FY2024 加权平均 ROE（2024 年报原文 2.5%；FY2023 3.5%、FY2025 3.4%） | as-of 2025-03-28
    'roe_trough': 0.025,
    # FY2027E EPS 共识下沿（美元；yfinance 18 家）——只作 L 交叉 | as-of 2026-10-08
    'eps_fy27_lo': 0.1186,
    # FY2027E EPS 共识均值（美元；yfinance 18 家） | as-of 2026-10-08
    'eps_fy27_m': 0.229,
    # FY2027E EPS 共识上沿（美元；yfinance 18 家） | as-of 2026-10-08
    'eps_fy27_h': 0.32,
    # FY2027E 收入共识均值（百万美元；MarketScreener 23 家），用于档净利率 | as-of 2026-10-08
    'rev_fy27_m': 14309,
    # 实付派息率（不派息） | as-of 2026-10-08
    'payout_obs': 0.0,
    # D 桶窗口年数（2027–2030；A9） | as-of 2026-10-08
    'window_years': 4,
    # 2025 年先进逻辑收入（百万美元；瑞银） | as-of 2026-08-10
    'adv_rev_25': 1600,
    # 先进逻辑收入 2025–28 年复合增速（瑞银） | as-of 2026-08-10
    'adv_cagr': 0.55,
    # 已建先进产能（千片 / 月，12 英寸；摩根士丹利 2026 年 7nm 及以下） | as-of 2025-10-21
    'cap_built_k': 42,
    # 满产先进产能（千片 / 月；瑞银 14nm 及以下 2030 年） | as-of 2026-08-10
    'cap_full_k': 166,
    # 先进晶圆单价（美元 / 片；用瑞银收入 ÷ 产能推算，A13） | as-of 2026-10-08
    'asp_wafer': 6500,
    # 先进产线利用率（推算单价与满产收入同一假设；A13） | as-of 2026-10-08
    'util': 0.95,
    # L 档利润率（`_AXIS.leading-edge-foundry`） | as-of 2026-10-05
    # H 档稀缺期利润率 = 台积电十年均值（`_AXIS.leading-edge-foundry`） | as-of 2026-10-04
    # H 档常态利润率 = 强者 − 本折扣（`_AXIS.leading-edge-foundry`） | as-of 2026-10-04
    # 腿 g（L / M，腿 ROIC > r 时用；`_AXIS.leading-edge-foundry`） | as-of 2026-09-14
    # 腿 g（H，台积电自身反解；`_AXIS.leading-edge-foundry`） | as-of 2026-09-14
    # 腿稳态年（`_AXIS.leading-edge-foundry` 对齐年 = 本票满产年） | as-of 2026-10-04
    # M 稀缺溢价年数（用户「5–10 年供不应求」下沿；A14） | as-of 2026-10-08
    'n_rent_m': 5,
    # H 稀缺溢价年数（同上，上沿；A14） | as-of 2026-10-08
    'n_rent_h': 10,
    # 腿税率（高新技术企业 15%；2025 年报税项附注） | as-of 2026-03-27
    'tax_opt': 0.15,
    # L 单位产能投入（十亿美元 / 千片月产能；推算区间上限，A15） | as-of 2026-10-08
    'kpk_l': 0.24,
    # M 单位产能投入（推算区间中点，A15） | as-of 2026-10-08
    'kpk_m': 0.165,
    # H 单位产能投入（推算区间下限，A15） | as-of 2026-10-08
    'kpk_h': 0.09,
    # 未投资本均匀投入年数（2027–2030；A12） | as-of 2026-10-08
    'capex_years': 4,
    # M 窗口后成熟制程常态 ROE = 联电 2016–2025 十年平均（Longbridge `financial-report UMC.US` ROE 3.96 / 4.59 / 3.70 / 3.99 / 10.44 / 20.51 / 30.51 / 17.89 / 12.81 / 11.01%；A22） | as-of 2026-10-08
    'roe_ss_m': 0.1194,
    # H 窗口后常态 ROE = 联电 2023–2025 平均（缺货结束后；A22） | as-of 2026-10-08
    'roe_ss_h': 0.1390,
    # H 缺货期 ROE = 联电 2021–2022 平均（A23） | as-of 2026-10-08
    'roe_short': 0.2551,
    # 时点对齐年数 τ：估值基准日（中报资产负债表日 2026-06-30）→ 分子年初 2027-01-01；底牌与期权同折（A25） | as-of 2026-06-30
    'tau': 0.5,
    # 增长期资金缺口（十亿美元）：2026H2 资本开支超出经营现金流的部分 = FY2025 实测（资本开支 84.0 − 经营现金流 31.9 亿美元，yfinance 年报）的一半；按框架 A15「资本开支领先产能约一年」，这批产能在 FY2027 内投产（A25） | as-of 2025-12-31
    'gap_h2_usd': 2.605,
    # 归母比例 = 归母权益 1,714.6 ÷（归母 + 少数股东 866.4）亿元（2026 半年报）；资金缺口按归母份额扣（A25） | as-of 2026-06-30
    'parent_ratio': 0.6643,
    # 先进制程腿稳态回报 = `_AXIS.leading-edge-foundry` 轴值（成熟代工同业穿越周期中位 16.9%）——自身周期不可用（新产品线无独立历史，A25）才落轴；腿稳态 = min(腿常态 ROIC, 本值)（A25） | as-of 2026-10-19
    # 先进制程腿回落年数 = `_AXIS.leading-edge-foundry`（进入门槛「高」）；用户「M 5 / H 10 年供不应求」是满额缺货年数、回落排在之后：Y1 = max(2030 + n − 1, `y1_floor_foundry`)，Y2 = max(Y1 + 6, `y2_floor_foundry`) → M 2034 / 2040、H 2039 / 2045（A25） | as-of 2026-10-18
    # 先进制程腿 Y1 下限 = `_AXIS.leading-edge-foundry`（台积电高回报期 Y1；用户 2026-10-18「和台积电同轴」，A25） | as-of 2026-10-18
    # 先进制程腿 Y2 下限 = `_AXIS.leading-edge-foundry`（台积电高回报期 Y2；同上，A25） | as-of 2026-10-18
    # 成熟制程缺货回落年数（本票判门槛「中」：扩产 1–2 年、2023–24 国内价格战显示新进入者抢份额快）；2031–2035 满额 5 年后回落：Y1 = 2035，Y2 = 2039（A25） | as-of 2026-10-18
    'fall_years_mature': 4,
    # H 成熟制程缺货期年数（用户裁决；A23） | as-of 2026-10-08
    'n_short': 5,
}

# Historical rationale and financial observations; comments are not extra inputs.
# - **业务地图摘要**：一个分部，制程收入不披露。概念上两块驱动不同——成熟制程（28nm 及以上，看利用率与价格周期）、先进制程（14nm 及以下 FinFET，看国产 AI 芯片放量）——但公开数据拆不开：卖方无分部估值（摩根大通 / 野村 / 杰富瑞用整公司 PB，高盛用整公司 2028 PE），分腿 ROE 来源优先序落到第三层（共用公司 ROE），故主尺退回整公司尺；先进制程超出底牌的部分由期权腿承担（A12）。
# - **属性 A — 折旧浪潮压住利润率**：2025 年折旧摊销 273.1 亿元，资本开支是折旧的 2.2 倍；管理层指引 2026 年折旧 +30%（约 49–50 亿美元），可能 2027 年见顶；摩根大通预计 2027 年再 +20%，长期毛利率 24–26%（2026-08-16）。设备折完后的利润释放不进底牌——「经济折旧 Gordon」要求资本开支 ÷ 折旧连续 ≥2 年 < 0.6，本票 2.2，不适用；窗口后回报率的提升只进期权：新投资本在先进制程腿里，2027 年初已有的成熟账面在「成熟制程回报回升」那块（A22）。
# - **属性 B — 国资合资结构**：五家非全资子公司（中芯北方、京城、东方、南方、深圳）2025 年合计净利润 27.0 亿元、净资产约 1,933 亿元（ROE 约 1.4%），归少数股东 21.7 亿元。2026-06-12 发行 5.47 亿股 A 股（74.20 元 / 股，合计 406.0 亿元）收购中芯北方 49%，对价是所购净资产份额 203.4 亿元的 2.0 倍（中报附注）。只按归母口径估值；股本与稀释单独跟踪（A7 / A8）。
# - **属性 C — 政策托底需求、制裁卡住供给**：收入 90% 来自中国；前五大客户 35.8%、第一大 8.0%（2025 年报）。实体清单限制先进设备——无 EUV，7nm 级靠 DUV 多重曝光，单位产能投入高、良率低（高盛估 2026 年先进制程良率 23%）。这些风险进 L 情景与期权腿的单位经济，不进 r（A5 / A6）。
# - **属性 D — 不派息、全部留存**：实付派息 0，模型 g = 0 时视同 100% 派出；差额由 D 桶窗口定价（A9）。
# - **属性 E — A / H 两地**：本框架只估 H 股；A 股价格不作参照，两地价差不进 r（A19）。
# - **期权（\(V_{opt}\)）理由**：先进制程「追上台积电回报」的世界今天没有本票具名的分子——公司不披露制程收入，卖方只有瑞银给出先进逻辑收入路径（2025 年 16 亿 → 2028 年 60 亿美元）。按「未建模期权」取法：份数 = 卖方产能路径（瑞银 2030 年 16.6 万片 / 月），单位经济 = 推算单价 × 同业利润率尺。升级门槛：A13 / A15；证伪：A14。第二块「成熟制程回报回升」：底牌把 FY2027（折旧高峰年）的 ROE 当永续，而窗口结束后的回报没有任何卖方预测年覆盖（共识只到 FY2028）——算不出分子、但有同业实测上限锚（联电停止大扩产后的 ROE），故进期权；份数 = 本票 2027 年初成熟账面，单位经济 = 联电实测 ROE（A22–A24）。
# | A1 | **周期位置 = 上行期**：2Q26 产能利用率 93.7%、毛利率 25.3%，3Q26 毛利率指引 26–28%；AI 周边（电源管理 / BCD）与本土化推动涨价。**证伪**：连续两个季度利用率 < 85% 或毛利率 < 20% → 周期掉头，回对话复核三档 | active | 杰富瑞 / 野村 / 摩根大通 2Q26 点评（Wisburg 100998 / 101540 / 100984，2026-08） | L / M 情景 |
# | A2 | **分子 = FY2027E 归母 EPS 共识区间**（最远的 ≥2 家带区间共识年；FY+1，不折现）：yfinance 18 家 0.1186 / 0.229 / 0.32 美元；MarketScreener 23 家均值 0.218（−4.8%，交叉）。本票是**需求周期型制造**（价格与客户谈、盈利不是商品价函数），M / H 取共识，不取周期中枢；周期风险由 L 承担。**L = 实测谷底**：FY2024 加权平均 ROE 2.5%（2024 年报「主要会计数据」原文）× 2027 年初 BPS = 0.0772 美元；共识下沿 0.1186（ROE 3.8%）只作交叉（9.25 港元）。FY2028E（MarketScreener 0.2678，+22.8%）**不作过渡年**：ROE < r 时过渡增长靠留存换、倍数反降（两段式 M 9.35× < 10×），只作披露 | active | yfinance `earnings_estimate` 2026-10-08；MarketScreener 2026-10-08；2024 年报「主要会计数据和财务指标」加权平均净资产收益率 2.5% | `eps_fy27_*`、`roe_trough` |
# | A3 | **2027 年初 BPS = 3.0886 美元（24.09 港元）**：中报归母权益 171,456.6 百万元 ÷ 8,560.8 百万股 ÷ 汇率（USD/HKD 7.80 × HKD/CNY 0.8544 = 6.664）= 3.0053，加 2H26 未入账共识利润（MarketScreener FY26E 13.84 亿美元 − H1 实测 44.67 亿元）÷ 股本；留存率 \(b_1\) = 1（不派息、g1/ROE > 1）。ROE = 2.50 / 7.41 / 10.36% | active | 2026 半年报合并资产负债表、主要会计数据；Longbridge `ah-premium` 汇率 2026-10-07 | `eq_h1_cny`、`ni_h1_cny`、`ni_fy26_usd`、`fx_*` |
# | A4 | **g2 = 0（具名）**：三档 ROE 2.5 / 7.4 / 10.4% 对 r 10% 分别落峰形 / 病态 / 病态区（\|ROE − r\| < 3pp 或更低），增长不创造价值，Gordon 在 g = 0 处取 1/r；同 `_AXIS.leading-edge-foundry` ②「ROE < r 时落 1/r」。代工簇 2.48% 是单调区同业的反解，跨域不入簇。留存去向审计 Step 3「g = 0 + 1/r」的适用条件 = D 桶且项目价值已单列（A9 / A12），成立。g2 ±1pp 只作披露（L 档峰形区，g 越高越低） | active | valuation-rules 域判定表、峰形区处理；`_AXIS.leading-edge-foundry` ② | `g2` |
# | A5 | **归篮：整公司 → 篮 4 常规经营 10%**。盈利不是商品价函数（晶圆价与客户谈；同业 `TSM.US` / `GFS.US` / `TSEM.US` 同篮）；不命中篮 7——2025 年第一大客户 8.0%、前五大 35.8%（2025 年报「主要销售客户」原文），国别风险为中国（ERP 5.14%，与港台同量级）。CAPM 粗筛 4.0% + β 1.04（对恒指 5 年周频）× 5.5% + 港股 1% = **10.7%**，偏离 +0.7pp。制裁、周期不抬 r（进 L 与期权腿单位经济）。证伪：单一客户 ≥50% 或前两大 ≥70% → 复议篮 7 | active | 2025 年报；Longbridge 周 K 2021-10 → 2026-10 | `r_perp` |
# | A6 | **制裁不再升级**：先进设备受实体清单限制，但现有产线可运转。证伪：美国扩大设备 / 材料管制并直接影响在建先进产线 → L 情景生效、期权腿 M / H 产能路径下调 | active | 高盛 2026-09-21（风险项：实体清单限制设备 / 材料） | L；期权腿 |
# | A7 | **股本 8,560.8 百万股、不再大规模稀释**：基准 = 2026-06-30（含 6 月为收购中芯北方 49% 发行的 547.18 百万股 A 股）。证伪：一年内股本增加 > 3% → 按新股本重算每股盈利与 BPS | active | 2026 半年报股本变动表 | `shares` |
# | A8 | **少数股东分利稳定**：中报少数股东权益占总权益 33.6%（2025 年末 38.8%，中芯北方收购后下降）。共识 EPS 已是归母口径。证伪：占比变动 > 5pp → 复核归母 EPS 口径 | active | 2026 半年报 / 2025 年报合并资产负债表、重要非全资子公司表 | 分子口径 |
# | A9 | **留存去向审计 = D 桶（增长窗口 2027–2030），不打折 k**（原 k = 0 / 0 / 0，2026-10-16 按 A25 去掉行，锚点不变）。Step 0（A 股年报口径，亿元）：资本开支 2019–2025 = 129 / 362 / 266 / 419 / 544 / 552 / 599；固定资产净值 567 → 2,304；净债务由 2022 年 −260 转为 2025 年 +153；2025 年折旧摊销 273.1；实付派息 0。Step 1：留存 100% 全部进固定资产（NPPE 年年升），非还债、非堆现金；资本开支较 2015–2019 基线（120–150 亿）跳升到 2020 年后 270–600 亿，项目具名（中芯南方 14nm 及以下目标 3.5 万片、京城 / 东方 / 西青 12 英寸厂；管理层 2026 年新增约 4 万片 / 月）→ D 桶。**窗口终点 = 2030**（与期权腿满产年、`_AXIS.leading-edge-foundry` 对齐年同年；瑞银 2030 年产能 16.6 万片 / 月）。**双算防线**：窗口内留存（每股约 4 年 × EPS ≈ 0.92 美元）小于期权腿要投的未投资本（M 档约 20 亿美元 / 年），即窗口留存全部进了期权腿，而期权腿已按全额扣未投资本（A12）；底牌再扣 k = 同一笔投入扣两次，故 k = 0。`check_branch` 的全派息分支红灯因此降为 `payout_gap` 披露。**窗口后触发**：2030 年后资本开支仍持续 > 1.5 × 折旧且新增产能没有对应收入 → 改 E 桶，回对话按现行规则重判（打折 k 不再用于一般经营资本，A25）；**2028 年中报复核**：卖方若已预测 2031 年后仍有大规模扩产 → 窗口终点后移、重算期权腿未投资本。禁止形态七条逐条未命中 | active | A 股年报 2019–2025（Longbridge `financial-report 688981.SH --report af`）；2025 年报现金流量表补充资料；管理层 2026-02 / 2026-08 电话会；用户裁决 2026-10-08（「低回报扩产不是常态，不进稳态」） | `window_years`、`payout_obs` |
# | A10 | **杠杆门未触发**：FY2025 净债务（短期借款 34.5 + 一年内到期非流动负债 148.4 + 长期借款 703.1 + 租赁 0.1 − 货币资金 436.4 − 交易性金融资产 6.1 − 一年内到期非流动资产（定期存款）289.4，亿元）= 154.2 亿 / EBITDA 377.6 亿 = **0.41**；利息费用 26.6 / 营业利润 83.0 = **32.1%**（贴 1/3；FY2024 21.1 / 63.0 = 33.6% 略超，谷底年塌缩）；按中枢分子年 FY2027E（EBIT 共识 23.67 亿美元、利息按 FY2025 约 4.0 亿美元）约 17%；2026H1 净债 83.7 亿、利息 / 营业利润 17.4%。其他非流动资产中的长期定期存款未计入现金（保守） | active | 2025 年报 / 2026 半年报合并资产负债表、利润表、EBITDA 调节表；MarketScreener EBIT 共识 | — |
# | A11 | **③ 护栏通过，带干净**：同等盈利月份（Longbridge 月频，TTM EPS 落在 M 分子 1.786 港元 ±12%）共 10 个：2022-01 / 04 / 06 / 08 / 09 / 11、2023-01 / 02 / 04 / 09，TTM PE **8.64–13.40×**、PB 0.58–0.74。生成的 M 倍数 10.00× 在带内（扣窗口毁损、折 τ 与资金缺口后的有效倍数 12.69 ÷ 1.786 = 7.11×，低于带下沿，只披露）。**带有效性核验**：带下沿月份 2022-11，当时 ROE（FY2022 加权 10.0%）− 现模型 ROE_M 7.4% = 2.6pp < 5pp；当时预期增速代理 = 其后两年实测 EPS 年复合 −47%（FY2022 1.5528 → FY2024 0.4321 元），低于现模型 → **干净** | active | Longbridge `valuation --history`（PE / PB）+ 月 K 2016-11 → 2026-10；A 股年报 EPS | 护栏 |
# | A12 | **先进制程腿（期权）的份数**：已建 4.2 万片 / 月（摩根士丹利：7nm 及以下 2025 年 2.2 万 → 2026 年 4.2 万，2025-10-21）；满产 16.6 万片 / 月（瑞银 14nm 及以下 2030 年，2026-08-10）。L 世界不再扩产（只按已建）；M / H 建满，未投资本按 2027–2030 四年均匀投入、年中折现。**底牌已含**：FY2027 先进收入 = 瑞银 2025 年 16 亿美元 × 1.55²（2025–28 年复合 55%）= 38.4 亿美元 × 该档公司净利率（档 EPS × 股本 ÷ FY27 收入共识均值 143.1 亿：4.6 / 13.7 / 19.1%）× 底牌倍数 10× → 从腿价值中扣除。**负值进底牌**：腿价值 < 0 = 窗口扩产赚不到 r、价值毁损，计入该档底牌（同 `INTC.US` A21 把代工盈亏平衡前亏损放进底牌）；正值为期权，\(p_k = V_k / V_H\)。卖方产能口径分歧：2025 年末 2.2 万（摩根士丹利）/ 2.6 万（瑞银）/ 4.5 万（SemiAnalysis 转引，未核） | active | 摩根士丹利 2025-10-21；瑞银 2026-08-10（Wisburg 100073）；用户裁决 2026-10-08 | `cap_built_k`、`cap_full_k`、`adv_rev_25`、`adv_cagr`、`capex_years`；表3 |
# | A13 | **晶圆单价 6,500 美元 = 用瑞银数字推算**（非任何一家直接给出）：先进逻辑收入 ÷（全年平均月产能 × 12 × 利用率 95%）——2025 年 16 亿 ÷（约 2.2 万 × 12 × 0.95）≈ 6,400；2028 年 60 亿 ÷（约 8.6 万 × 12 × 0.95）≈ 6,100；期初产能为线性插值。**已知偏低**：口径是 14nm 及以下平均价，含便宜的 14nm；产品组合向 7 / 5nm 走会抬平均价。《金融时报》2024-02 称中芯 5 / 7nm 报价比台积电贵 40–50%（单一媒体、口径为报价，约合 1.3 万美元以上）。三档同用 6,500（无同源区间）。**升级门槛**：≥2 家卖方或公司给出 7nm / FinFET 晶圆价格，或先进制程收入 + 片数 → 替换并按档取；公司重新按制程披露收入或卖方单列先进制程利润率 → 腿改用实际利润 | active | 瑞银 2026-08-10；《金融时报》2024-02（亚洲时报转载）；对话 2026-10-08 | `asp_wafer`、`util` |
# | A14 | **单位利润率借 `_AXIS.leading-edge-foundry`**：L = 弱者 7.0%、H = 台积电十年均值 42.4% − 良率 / 规模折扣 12.4pp = 30.0%、M = 中点 18.5%。**口径差（已知）**：轴锁 ≤3nm，本腿是 7nm 级 DUV 多重曝光——工序更多、良率更低，方向上借来的利润率偏高；本票不是轴组员，只借尺。**稀缺溢价有期限**（construction §5b「短缺租金有期限」；用户「5–10 年供不应求」，2026-10-08；2026-10-18 裁定：5–10 年是满额缺货本身的年数，回落排在之后，且先进制程与台积电同轴、不早于台积电的 2030 / 2035 回落）：M 2030–2034 按 30.0%、2035–2040 线性回落到常态；H 2030–2039 按 42.4%、2040–2045 线性回落到常态；不永续（A25）。**稀缺结束信号（证伪）**：国内出现第二家量产 7nm 级的代工厂（《金融时报》2025-08-27 报道华为自建 AI 芯片厂 2025 年底起投产）；先进产线利用率连续两个季度 < 90%；先进制程降价；美国放松设备管制。「中国唯一能做 AI 代工」只作本条假设，不作事实 | active | `_AXIS.leading-edge-foundry` Inputs；《金融时报》2025-08-27；日经 2026-02-25（中国 7 / 5nm 产能目标 1–2 年内 10 万片） | `opm_*`、`yield_discount`、`n_rent_*` |
# | A15 | **单位产能投入（十亿美元 / 千片月产能）= 推算区间两端 + 中点**：高盛口径（年资本开支 81.7 亿 × 先进占比 54–71% ÷ 年新增 3–5 万片）0.088–0.193；瑞银产能路径 + 共识资本开支（2026–28 年合计 239.8 亿 × 54–71% ÷ 新增 7.2 万片）0.180–0.236 → 全区间 0.088–0.236；**H 0.09 / M 0.165 / L 0.24**（用户裁决 2026-10-08：乐观取上限、中性取中间）。两种推法都用同年投入 ÷ 同年新增，资本开支领先产能约一年 → 方向偏高。中芯南方注册资本 65 → 约 101 亿美元、目标 3.5 万片（约 0.29）只作参考（注册资本 ≠ 设备投资）。税率 15%（高新技术企业，2025 年报税项附注）。**升级门槛**：卖方或公司给出先进产能单位投资额、或具名项目的投资额与片数 | active | 高盛 2026-09-21（Wisburg 106324）；瑞银 2026-08-10；MarketScreener 资本开支共识；2025 年报 | `kpk_*`、`tax_opt` |
# | A16 | **腿估值**：稳态（2030）NOPAT × 腿倍数——腿 ROIC ≤ r 时 1/r，> r 时 Gordon（g：L / M 轴 `g2_foundry_src` 2.48%、H 轴 `g2_foundry_h_src` 5.66%，「追上台积电」世界取台积电自身反解）；稀缺溢价与新投资回报按高回报期路径回落（A25）；÷ 1.1³ 折回 FY2027；减未投资本现值与底牌已含。结果 L −0.35 / M −2.90 / H +27.12 港元（FY2027 时点，再同折 τ，A25）→ 底牌 L、M 各计入负值，H 的 27.12 进期权（与 A22 合计为 \(V_{opt}\)） | active | 对话 2026-10-08；`INTC.US` A21 / A7 | 底牌；表3 |
# | A17 | **分类翻转**：连续三年毛利率 ≥ 30%、加权 ROE > 10%、每股盈利年增 > 20% → 主类改 `fast_grower`（同时 ROE > r + 3pp，g2 改走代工簇） | active | 对话 2026-10-08 | 题头 |
# | A18 | **折旧增速快过收入**（摩根大通 2026 / 2027 年 +30% / +20% vs 收入 +27% / +10–15%）。证伪（利润率提前释放）：2027 年折旧增速 < 收入增速且全年毛利率 ≥ 28% → 回对话复核 M / H 的 ROE 与期权腿 M 档利润率 | active | 摩根大通 2026-08-16（Wisburg 100984） | M / H |
# | A19 | **国家战略与 A / H 价差不进 r、不进锚点**：战略地位体现在 A1（需求托底）与 A14（稀缺溢价期限）；A 股按 2024-01 以来平均约 196% 溢价交易（高盛 2026-09-21），只在研究对话里解读 | active | 高盛 2026-09-21 | — |
# | A20 | **四个合法杠杆逐一交代（卖方差额）**：卖方 TP（Wisburg / Longbridge，2026-08 → 09）：摩根大通 78（2.8× FY27–28 BVPS）、野村 75（3.5× FY26 BVPS）、杰富瑞 88（3.6× FY27 BVPS）、瑞银 96.2、花旗 100、汇丰 106、高盛 153（80.7× FY2028 PE，15% 折回）；Longbridge 23 家均值 95.98（2026-09-29）。H + \(V_{opt}\) 61.19 / 均值 95.98 = 0.64。① Gordon 倍数——已入位（g = 0，A4）；② 有共识年份的过渡——FY2028 试过，ROE < r 下倍数反降，不用（A2）；③ 期权——已入位（先进制程腿 A12–A16、成熟制程回报回升 A22–A24）；④ 候选带——无（单价 1.3 万美元的来源是单一媒体的报价口径，与推算值不同口径，只作敏感性）。与卖方的差 = 卖方的 PB 倍数（2.8–3.6×，隐含长期 ROE 约 20%+）与高盛的远年 PE，即「7nm 单价远高于推算并长期维持」——今天公开数据闭合不了 | active | Wisburg 100984 / 101540 / 100998 / 100073 / 100821 / 100907 / 106324；Longbridge `institution-rating` 2026-09-29 | 交叉 |
# | A21 | **独立成交价护栏不适用**：中芯北方 49% 的卖方（国家集成电路基金等）与本公司为关联方（中报「关联交易」披露），条件 ③ 不满足 | active | 2026 半年报 | — |
# | A22 | **成熟制程回报回升（期权第二块）**：底牌把 FY2027 的 ROE（折旧高峰年，A18）当永续；用户裁决「ROE 不会一直这么低，病态区不是长久状态」（2026-10-08）。窗口结束后的回报没有卖方年份覆盖，按「未建模期权」进 \(V_{opt}\)，不进底牌。上限锚 = 联电（成熟代工、2017 年前后停止大扩产）实测 ROE：2016–2025 年 3.96 / 4.59 / 3.70 / 3.99 / 10.44 / 20.51 / 30.51 / 17.89 / 12.81 / 11.01%。**L 不回升**（停在谷底 2.5%；中芯自身十年平均 5.7% 只作参照）；**M = 联电十年平均 11.94%**；**H = 联电 2023–2025 平均 13.90%**（缺货结束后的常态）。2031 年起生效、永续 g = 0（窗口后成熟制程不再扩产；H 的 13.9% 略过 r + 3pp，留存增长本可加值，g = 0 偏保守），倍数 1/r，折回 FY2027（÷ 1.1³）。结果 M **6.04** / H 5.49 港元（H 起点 ROE 10.4% 更高，故常态增量小于 M）。格芯 2023–2025 年 9.7 / −2.4 / 7.8% 只作交叉。**证伪**：2031–2032 年加权 ROE 仍 < 8%，或成熟制程连续四个季度降价 → 本块 M 归零复核；**升级门槛**：≥2 家卖方给出 2030 年后的 ROE / EPS → 改用卖方路径 | active | Longbridge `financial-report UMC.US / GFS.US / 688981.SH --report af`（2026-10-08）；用户裁决 2026-10-08 | `roe_ss_m`、`roe_ss_h`；表3 |
# | A23 | **成熟制程缺货期 5 年、之后回落（只在 H）**：超出常态 13.90% 的缺货回报按联电缺货年份 2021–2022 平均 ROE 25.51% 计，2031–2035 年满额、2036–2039 年线性回落到常态（门槛「中」回落 4 年，用户 2026-10-18 定 Y2 = 2039，A25），不永续，= 8.26 港元（FY2027 时点；原 5 年满额年金不回落 6.83）。年数为用户裁决（2026-10-08，「5 年」）；联电上一轮缺货实际约 3 年（3 年满额加回落时本块 H 折 τ 后 11.16、\(V_{opt}\) 37.02）。中国成熟制程 2023–2024 年曾价格战，今日利用率 93.7%、涨价靠 AI 周边与国产替代（A1）。**证伪**同 A22 | active | Longbridge `financial-report UMC.US`；用户裁决 2026-10-08 | `roe_short`、`n_short` |
# | A24 | **防双计**：① 成熟账面 = 2027 年初 BPS 3.0886 − 已建先进产能 4.2 万片 × 该档单位产能投入 ÷ 股本（L / M / H 1.91 / 2.28 / 2.65 美元）——已建先进产能的回报已在先进制程腿里（腿按满产 16.6 万片含已建部分估值），不再回升一次；用毛投入扣账面是近似（未扣折旧、未分债务），方向上多扣、偏保守。② 2027–2030 年新投资本只在先进制程腿。③ **本块不抵底牌**：M 档先进制程腿 −2.90（窗口新投资本赚不够 r）留在底牌，不拿本块 +6.04 去冲——一个是新钱毁值、一个是旧钱回升，概率不同 | active | 对话 2026-10-08 | 表3 |
# | A25 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」；2026-10-16 / 10-18 框架纠正：M 13.93 → 12.69，−8.9%，未达 25% 对账门）**。① **超额现金不单列**：净债务（A10），\(C_{ex}\) = 0。**增长期资金缺口 1.58 港元 / 股**：FY2025 资本开支 84.0 亿美元远超经营现金流 31.9 亿（yfinance 年报；A 股年报资本开支 599 亿元互证），2026H2 缺口按 FY2025 的一半 = 26.05 亿美元；按「资本开支领先产能约一年」（A15），这批产能在分子年 FY2027 内投产，产出在分子里 → 计入；2027–2030 的先进产能扩建已在先进制程腿里扣未投资本，不重复。本票无现金行，缺口作类债项按**归母比例 0.664**（归母权益 1,714.6 ÷（归母 + 少数股东 866.4）亿元，2026 半年报）从每档底牌扣；有缺口时窗口可分配利润记 0（本来也是 0：不派息，滚动留存率 \(b_1\) = 1）。② **时点对齐 τ = 0.5**：分子 FY2027E、回报分母 2027 年初账面 → 分子年初 2027-01-01；估值基准日 = 中报资产负债表日 2026-06-30。底牌（含进底牌的先进制程腿负值）与期权两块都是 2027 年初的值，同折 ÷1.1^0.5。**L 档同样折**：L 的分子是「FY2024 谷底 ROE × 2027 年初账面」，与 M / H 同一时点（若视为不随日历漂移的常态年不折，L 为 4.09）。③ **稳态回报三段**：底牌永续增长 0、回报不进倍数；成熟制程回升块增长 0。**先进制程腿**参照 `_AXIS.leading-edge-foundry`：稳态回报 = min(腿常态 ROIC, 轴值 16.9%)（2026-10-19 按序取：**自身周期不可用**——先进制程是新产品线、无独立历史（2021 年起不按制程披露，2025 年先进收入约 16 亿美元〔瑞银，A12〕，亚规模），客户与需求（国产 AI 芯片、手机 SoC）与成熟制程不同，结构变化之后没有一轮完整周期；整公司自身周期是成熟制程的读数（十年平均 ROE 5.7%，净债务公司，投入资本口径更低），不代表这条腿，只作对照 → 取轴稳态行 16.9%（成熟代工同业穿越周期中位，高塔 19.4 / 联电 16.9 / 格芯 3.0%；半导体按全球同业））——H 腿常态 ROIC 21.0% → 16.9%，L / M 腿 ROIC < r 落 1/r 不受影响；**高回报期**：腿首年 2030（满产年），进入门槛「高」回落 6 年（轴；依据：新产线建成到量产 2–3 年、客户导入认证 1–2 年、单位产能投资 0.09–0.24 亿美元每千片是链上最高一档、国内第二家 7nm 量产迟迟未出现）。**用户 2026-10-18 裁定**：「先进制程应该是和台积电同轴的，不可能说中芯国际提前回落」——① 下限：台积电的高回报期（`TSM.US` A31 的 2030 / 2035）是先进代工的共同下限，挂轴腿 Y1 ≥ 2030、Y2 ≥ 2035（轴 `y1_floor_foundry` / `y2_floor_foundry`）；② 叠加中芯本土缺货：「5–10 年供不应求」是满额缺货本身的年数，回落排在之后、不含在内，从腿首年 2030 起算——M 档 2030–2034 满额（Y1 = 2034）、回落 6 年到 Y2 = 2040；H 档 2030–2039 满额（Y1 = 2039）、Y2 = 2045；两档都在下限之上。稀缺利润率与新投资回报（短缺期 29.7%）在 Y1 前取短缺值、Y1 → Y2 线性回落、Y2 后取常态利润率与稳态回报。结果腿 M −3.93 → −2.90、腿 H +26.43 → +27.12（FY2027 时点）。**成熟制程缺货块**（A23，只在 H）：2031–2035 满额 5 年，门槛判「中」回落 4 年（扩产 1–2 年；2023–24 国内价格战显示新进入者抢份额快）→ Y1 = 2035、Y2 = 2039（用户 2026-10-18 定），缺货溢价 6.83 → 8.26。④ **去掉的 k**：原 k = 0 / 0 / 0 乘在 D 桶「视同派出、实际留存」上，即多留部分；规则把多留部分归现金可信度 λ（本票无钱回不到股东的具名证据，λ = 1），乘在多留部分上的 k 属乘错对象 → 去掉行，锚点不变。**合计**（M 档，对上一版）：腿 M 回落路径 +7.4%（−3.93 → −2.90）、时点对齐 −4.65%、资金缺口 −11.3% → 13.93 → **12.69**；\(V_{opt}\) 38.75 → 38.97、\(p_M\) 0.156 → 0.148 | active | 2026 半年报；yfinance 0981.HK 年报现金流（2025）；`_AXIS.leading-edge-foundry` §1b；`TSM.US` A31；用户裁定 2026-10-08 / 2026-10-18；valuation-rules「经营价值与超额现金」①②③④ | `tau`、`gap_h2_usd`、`parent_ratio`、`ss_return_foundry`、`fall_years_foundry`、`y1_floor_foundry`、`y2_floor_foundry`、`fall_years_mature`；锚点、\(V_{opt}\) |

LISTING_CCY = "HKD"
TOL = 0.05
NUM_YEAR = 2027
MATURE_FIRST = 2031  # mature re-ROE / shortage block starts after the 2027–2030 window (A22)
TIERS = ("L", "M", "H")

REQUIRED = [
    "r_perp", "g2", "shares", "eq_h1_cny", "ni_h1_cny", "fx_usdhkd", "fx_hkdcny",
    "ni_fy26_usd", "roe_trough", "eps_fy27_lo", "eps_fy27_m", "eps_fy27_h", "rev_fy27_m",
    "payout_obs", "window_years",
    "adv_rev_25", "adv_cagr", "cap_built_k", "cap_full_k", "asp_wafer", "util",
    "opm_weak_peer", "opm_strong_peer", "yield_discount", "g2_foundry_src", "g2_foundry_h_src",
    "t_align", "n_rent_m", "n_rent_h", "tax_opt", "kpk_l", "kpk_m", "kpk_h", "capex_years",
    "roe_ss_m", "roe_ss_h", "roe_short", "n_short",
    "tau", "gap_h2_usd", "parent_ratio", "ss_return_foundry", "fall_years_foundry", "fall_years_mature",
    "y1_floor_foundry", "y2_floor_foundry",
]
AXIS_ROWS = ("opm_weak_peer", "opm_strong_peer", "yield_discount",
             "g2_foundry_src", "g2_foundry_h_src", "t_align", "ss_return_foundry", "fall_years_foundry",
             "y1_floor_foundry", "y2_floor_foundry")


def path_counts(first: int, n_full: int, fade: int, y1_floor: int | None = None,
                y2_floor: int | None = None) -> tuple[int, int, int, int]:
    """High-return path (A25, user 2026-10-18): the user's shortage years n_full are years at
    the full shortage value from `first` (the fade comes after, not inside); Y1 = first +
    n_full - 1, Y2 = Y1 + fade, each lifted to the axis floor when given (TSMC's 2030 / 2035
    for the advanced-node leg).  Returns (years at full incl. Y1, fade years, Y1, Y2)."""
    y1 = first + n_full - 1
    if y1_floor is not None:
        y1 = max(y1, y1_floor)
    y2 = y1 + fade
    if y2_floor is not None:
        y2 = max(y2, y2_floor)
    return y1 - first + 1, y2 - y1, y1, y2


def fade_weights(n_short: int, n_dec: int):
    """Weight of the shortage premium in year k (k = 1 is the first year): 1 through Y1,
    linear to 0 at Y2, 0 after."""
    def w(k: int) -> float:
        if k <= n_short:
            return 1.0
        if k < n_short + n_dec:
            return 1.0 - (k - n_short) / n_dec
        return 0.0
    return w


def sanity(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    e += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    e += check_g_cap(inp["g2_foundry_src"], inp["r_perp"], "g2_foundry_src")
    e += check_g_cap(inp["g2_foundry_h_src"], inp["r_perp"], "g2_foundry_h_src")
    if not inp["eps_fy27_lo"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]:
        e.append("FY27 consensus range must be ordered low < mean < high")
    if not inp["kpk_h"] < inp["kpk_m"] < inp["kpk_l"]:
        e.append("capital per 1k wpm must fall from L to H (same range, two ends + middle)")
    leaked_k = sorted(k for k in inp if k in ("k_l", "k_m", "k_h"))
    if leaked_k:  # A25: the k = 0 on the D-bucket retention sat on the 多留部分 -> removed
        e.append(f"discount k rows must not reappear (A25): {leaked_k}")
    if inp["t_align"] <= NUM_YEAR:
        e.append("option alignment year must lie after the numerator year")
    if not inp["roe_ss_m"] < inp["roe_ss_h"] < inp["roe_short"]:
        e.append("mature ROE ladder must be steady M < steady H < shortage")
    if inp["roe_ss_m"] <= inp["r_perp"]:
        e.append("roe_ss_m must exceed r — a steady ROE at or below r adds no value over the 1/r base")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    baskets = {'r_perp': 4}

    require_whole_years(inp, ('window_years','t_align','n_rent_m','n_rent_h','capex_years',
                               'n_short','fall_years_foundry','fall_years_mature',
                               'y1_floor_foundry','y2_floor_foundry'))
    errors = sanity(inp, baskets)
    if errors:
        raise ValueError('; '.join(errors))

    r, g2, sh = inp["r_perp"], inp["g2"], inp["shares"] * 1e6
    hkd = inp["fx_usdhkd"]
    usdcny = hkd * inp["fx_hkdcny"]

    # ---- FY2027 opening book (USD/share): H1'26 book + unbooked 2H26 consensus, b = 1 ----
    bps0 = inp["eq_h1_cny"] * 1e6 / usdcny / sh
    ni_h2 = inp["ni_fy26_usd"] * 1e6 - inp["ni_h1_cny"] * 1e6 / usdcny
    bps27 = bps0 + ni_h2 / sh

    eps = {"L": inp["roe_trough"] * bps27, "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}

    def base_band(g: float = g2, rr: float = r) -> tuple[dict, dict]:
        pre, info = {}, {}
        for t in TIERS:
            roe = eps[t] / bps27
            pe = perpetual_pe(g, roe, rr) if roe > g else float("nan")
            pre[t] = eps[t] * pe * hkd
            info[t] = (roe, pe)
        return pre, info

    pre, info = base_band()

    # ---- Advanced-node leg per tier (A12–A15), HKD/share ----
    m_l = inp["opm_weak_peer"]
    m_h = inp["opm_strong_peer"] - inp["yield_discount"]
    m_m = (m_l + m_h) / 2
    leg = {  # capacity k wpm, normal margin, rent margin, rent years, leg g2, capital per 1k wpm ($B)
        "L": (inp["cap_built_k"], m_l, m_l, 0, inp["g2_foundry_src"], inp["kpk_l"]),
        "M": (inp["cap_full_k"], m_m, m_h, int(inp["n_rent_m"]), inp["g2_foundry_src"], inp["kpk_m"]),
        "H": (inp["cap_full_k"], m_h, inp["opm_strong_peer"], int(inp["n_rent_h"]),
              inp["g2_foundry_h_src"], inp["kpk_h"]),
    }
    adv27 = inp["adv_rev_25"] * 1e6 * (1 + inp["adv_cagr"]) ** 2
    yrs_disc = inp["t_align"] - NUM_YEAR
    n_cap = int(inp["capex_years"])

    def leg_value(t: str, asp: float | None = None, kpk: float | None = None,
                  rr: float | None = None) -> tuple[float, dict]:
        """Leg value at FY2027 (HKD/share).  The scarcity margin no longer steps down
        (A14 / A25, valuation-rules「未建模期权」+「经营价值与超额现金」② 稳态回报三段): the user's
        5 / 10 years are full-shortage years from 2030, the axis fade comes after, and Y1 / Y2 are
        lifted to the axis floor (TSMC 2030 / 2035; user 2026-10-18);
        margin and new-investment return stay at the shortage values to Y1, fade linearly to Y2,
        then normal margin and the steady return min(normal ROIC, axis 16.9%)."""
        rr = r if rr is None else rr
        cap, mn, mr, n, gl, kk = leg[t]
        asp = inp["asp_wafer"] if asp is None else asp
        kk = kk if kpk is None else kpk
        rev = cap * 1e3 * 12 * asp * inp["util"]
        capital = cap * kk * 1e9
        tax = inp["tax_opt"]
        nopat = rev * mn * (1 - tax)
        roic = nopat / capital
        gg = gl if roic > rr else 0.0          # ROIC <= r: growth creates no value -> 1/r
        pe_leg = perpetual_pe(gl, roic, rr) if roic > rr else 1 / rr
        if n:
            n_short, n_dec, _, _ = path_counts(int(inp["t_align"]), n, int(inp["fall_years_foundry"]),
                                               int(inp["y1_floor_foundry"]), int(inp["y2_floor_foundry"]))
            ron_short = rev * mr * (1 - tax) / capital
            ron_ss = min(roic, inp["ss_return_foundry"])
            w = fade_weights(n_short, n_dec)
            pv, e, k_ = 0.0, 1.0, 1
            while True:
                wt = w(k_)
                e_t = rev * (1 + gg) ** (k_ - 1) * (mn + (mr - mn) * wt) * (1 - tax)
                ron = ron_ss + (ron_short - ron_ss) * wt
                pay = (1 - gg / ron) if gg > 0 else 1.0
                if wt == 0.0:
                    pv += e_t * pay / ((rr - gg) * (1 + rr) ** (k_ - 1))
                    break
                pv += e_t * pay / (1 + rr) ** k_
                k_ += 1
            stream = pv
        else:
            stream = nopat * pe_leg
        rent = stream - nopat * pe_leg      # value of the shortage path over the normal perpetuity
        unspent = (cap - inp["cap_built_k"]) * kk * 1e9
        pv_unspent = sum(unspent / n_cap / (1 + rr) ** (i + 0.5) for i in range(n_cap))
        npm = eps[t] * sh / (inp["rev_fy27_m"] * 1e6)
        pe_base = perpetual_pe(g2, eps[t] / bps27, rr) if eps[t] / bps27 > g2 else float("nan")
        overlap = adv27 * npm * pe_base
        v = stream / (1 + rr) ** yrs_disc - pv_unspent - overlap
        return v / sh * hkd, dict(rev=rev, roic=roic, pe=pe_leg, nopat=nopat, rent=rent,
                                   pv_unspent=pv_unspent, overlap=overlap, npm=npm, mn=mn, mr=mr, n=n, gl=gl)

    vraw, legs = {}, {}
    for t in TIERS:
        vraw[t], legs[t] = leg_value(t)

    # ---- Mature re-ROE component (A22–A24), HKD/share; option only ----
    roe_ss = {"L": None, "M": inp["roe_ss_m"], "H": inp["roe_ss_h"]}

    def mature_value(t: str, n_short: int | None = None) -> tuple[float, dict]:
        n_short = int(inp["n_short"]) if n_short is None else n_short
        book = bps27 - inp["cap_built_k"] * leg[t][5] * 1e9 / sh
        if roe_ss[t] is None:
            return 0.0, dict(book=book, up=0.0, rent=0.0)
        pe_ss = perpetual_pe(g2, roe_ss[t], r)
        up = max(roe_ss[t] - info[t][0], 0.0) * book * pe_ss
        # shortage premium fades along the high-return path (A25): user's n_short years at full
        # from 2031, then mature node barrier 中 -> fall_years_mature years of fade (no TSMC floor:
        # that floor belongs to the advanced-node axis)
        ns, nd, _, _ = path_counts(MATURE_FIRST, n_short, int(inp["fall_years_mature"]))
        w = fade_weights(ns, nd)
        rent = ((inp["roe_short"] - roe_ss[t]) * book * sum(w(k) / (1 + r) ** k for k in range(1, ns + nd + 1))
                if t == "H" else 0.0)
        d = (1 + r) ** yrs_disc
        return (up + rent) / d * hkd, dict(book=book, up=up / d * hkd, rent=rent / d * hkd, pe=pe_ss)

    vmat, mats = {}, {}
    for t in TIERS:
        vmat[t], mats[t] = mature_value(t)
    carry = {t: min(vraw[t], 0.0) for t in TIERS}
    # Timing (A25, valuation-rules「经营价值与超额现金」③): everything above sits at the numerator
    # year's opening 2027-01-01 -> back tau years to the balance-sheet date; the window's
    # distributable profit is 0 (roll b1 = 1, nothing paid).  Funding gap 2026H2 (capex beyond
    # OCF, capacity online inside FY2027) is a debt-like item x parent ratio (no cash line).
    tdisc = (1 + r) ** inp["tau"]
    gap_ps = inp["gap_h2_usd"] * 1e9 / sh * hkd * inp["parent_ratio"]
    pos = {t: (max(vraw[t], 0.0) + vmat[t]) / tdisc for t in TIERS}
    base = {t: (pre[t] + carry[t]) / tdisc - gap_ps for t in TIERS}
    L, M, H = base["L"], base["M"], base["H"]
    A, B = (L + M) / 2, (M + H) / 2
    v_opt = pos["H"]
    p = {t: (pos[t] / v_opt if v_opt > 0 else 0.0) for t in TIERS}
    plus_v = tuple(base[t] + p[t] * v_opt for t in TIERS)

    if not L < M < H:
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    if not pre["L"] < pre["M"] < pre["H"]:
        errors.append("flat ladder (A2e-2c): pre-carry anchors not ordered at the shared 1/r multiple")

    # D bucket (A9): the full-payout branch's red light is priced by the window, so disclose it.
    branch_gaps = {}
    for t in TIERS:
        if check_branch(g2, info[t][0], r, inp["payout_obs"], f"g2@{t}"):
            mod, gap = payout_gap(g2, info[t][0], inp["payout_obs"])
            branch_gaps[t] = {'model_payout':mod, 'observed_payout':inp['payout_obs'], 'gap':gap}

    if errors:
        raise ValueError('; '.join(errors))
    sensitivity = {'growth_low': base_band(g2-.01)[0], 'growth_high': base_band(g2+.01)[0],
                   'wafer_10000': {t: leg_value(t, asp=10000.) for t in TIERS},
                   'wafer_13000': {t: leg_value(t, asp=13000.) for t in TIERS},
                   'capital_low': {t: leg_value(t, kpk=inp['kpk_h']) for t in ('M','H')},
                   'capital_high': {t: leg_value(t, kpk=inp['kpk_l']) for t in ('M','H')}}
    vm3 = mature_value('H', n_short=3)[0]
    wafer_results = {}
    for label in ('wafer_10000', 'wafer_13000'):
        vs = {t: sensitivity[label][t][0] for t in TIERS}
        bb = {t: (pre[t] + min(vs[t], 0)) / tdisc - gap_ps for t in TIERS}
        option_h = (max(vs['H'], 0) + vmat['H']) / tdisc
        adjusted = {t: bb[t] + (max(vs[t], 0) + vmat[t]) / tdisc for t in TIERS}
        wafer_results[label] = {'base': bb, 'option': option_h, 'adjusted': adjusted}
    short_mature_option = pos['H'] + (vm3 - vmat['H']) / tdisc
    fl = (int(inp['y1_floor_foundry']), int(inp['y2_floor_foundry']))
    paths = {t: path_counts(int(inp['t_align']), int(inp[f'n_rent_{t.lower()}']),
                            int(inp['fall_years_foundry']), *fl) for t in ('M', 'H')}
    mp = path_counts(MATURE_FIRST, int(inp['n_short']), int(inp['fall_years_mature']))
    def band_rf(dr):
        rr = r + dr
        pre_r, _ = base_band(g2, rr)
        return tuple((pre_r[t] + min(leg_value(t, rr=rr)[0], 0.0)) / (1+rr) ** inp['tau'] - gap_ps for t in TIERS)
    if any(abs(x-y) > TOL for x,y in zip(band_rf(0), (L, M, H))):
        raise ValueError('rate sensitivity base differs from anchors')
    option = ({'value':v_opt, 'weights':p, 'anchors':dict(zip('LMH',plus_v))}
              if v_opt > 0 and 0 <= plus_v[0] < plus_v[1] < plus_v[2] else
              {'status':'unavailable','label':'先进及成熟制程','anchors':None})
    result = {'ticker': '0981.HK', 'currency': 'HKD',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of':'2026-10-19',
            'anchors': dict(zip('LMH', (L, M, H))), 'candidate': None,
            'option': option,
            'review_flags':['historical_foundry_peer_node_comparability_unverified',
                            'historical_capacity_pricing_and_funding_unverified'],
            'bps0': bps0, 'ni_h2': ni_h2, 'bps27': bps27, 'eps': eps, 'pre': pre, 'info': info,
            'leg': leg, 'adv27': adv27, 'yrs_disc': yrs_disc, 'n_cap': n_cap, 'vraw': vraw,
            'legs': legs, 'roe_ss': roe_ss, 'vmat': vmat, 'mats': mats, 'carry': carry,
            'tdisc': tdisc, 'gap_ps': gap_ps, 'pos': pos, 'base': base, 'L': L, 'M': M, 'H': H,
            'A': A, 'B': B, 'v_opt': v_opt, 'p': p, 'plus_v': plus_v, 'branch_gaps': branch_gaps,
            'vm3': vm3, 'fl': fl, 'paths': paths, 'mp': mp, 'sensitivity': sensitivity,
            'wafer_results': wafer_results,
            'mature_shortage_3y': {'option': short_mature_option, 'adjusted_h': H + short_mature_option}}
    if branch_gaps:
        result['review_flags'].append('historical_payout_branch_gap')
    if rate_inputs is not None:
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp':r}, band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs, base_anchors=(L,M,H)))
    return result


def calculate(context):
    axis = context['axes']['foundry']
    shared = {key:axis[key] for key in AXIS_ROWS}
    result = evaluate({**INPUTS, **shared}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs':INPUTS,'foundry':shared,'numerator_year':NUM_YEAR,'mature_first':MATURE_FIRST},
        HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price':'HKD_PER_SHARE'}
    result['option']['value_unit'] = 'HKD_PER_SHARE'
    result['segments'] = {
        'core': {'unit':'HKD_PER_SHARE','values':{t:result['pre'][t] / result['tdisc'] for t in TIERS}},
        'advanced_negative': {'unit':'HKD_PER_SHARE','values':{t:result['carry'][t] / result['tdisc'] for t in TIERS}},
        'funding_gap': {'unit':'HKD_PER_SHARE','values':dict.fromkeys(TIERS,-result['gap_ps'])}}
    result['key_parameters'] = {
        'discount_rate': {'unit':'RATIO','values':dict.fromkeys(TIERS,INPUTS['r_perp'])},
        'growth_rate': {'unit':'RATIO','values':dict.fromkeys(TIERS,INPUTS['g2'])},
        'forward_return': {'unit':'RATIO','values':{t:result['info'][t][0] for t in TIERS}},
        'foundry_steady_reference':shared['ss_return_foundry']}
    return result
