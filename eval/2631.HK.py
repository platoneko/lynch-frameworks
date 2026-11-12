#!/usr/bin/env python3
"""SICC's historical asset band and full-capacity option; draft research output.

Original 2026 inputs, assumptions and shared SiC axis are retained. Amounts
are CNY or HKD as indicated, results HKD/share. No new forecast is implied.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, g_cap, perpetual_pe, two_stage_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'),
                'axes': {'sic': 'sic', 'capex': 'ai_capex'}}

HISTORICAL_PARTIAL_FINGERPRINT = '27b31c86a5173bc7cdbcda40bfaf0630ff169d298475ba3edf0bae451857a7e3'

INPUTS = {
    # 总股本；中报 484,618,544 股 | as-of 2026-06-30
    'shares': 4.84618544e8,
    # CNY→HKD 市场交叉汇率（仓库统一口径，源见 `9988.HK.md` 同字段） | as-of 2026-09-04
    'fx_cny_hkd': 1.1668,
    # 归母权益 亿 CNY（三季报 2026-09-30 归属于母公司所有者权益 7,194,816,628.67）；BPS = equity × fx ÷ shares；ROE_H 分母（A6） | as-of 2026-09-30
    'equity_cny': 71.9482,
    # 底牌 L；清算/作废压力；A7 | as-of 对话锁定
    'pb_l': 0.55,
    # 底牌 M；产能不作废；A7 | as-of 对话锁定
    'pb_m': 0.80,
    # 底牌 H；值一个账面；A7 | as-of 对话锁定
    'pb_h': 1.00,
    # H 股 IPO 发售价 HKD（2025-08-20 上市）；**交叉坐标，不入公式**（2026-10-03 起不再作期权上限锚，A11） | as-of 2025-08-20
    'ipo_price_hkd': 42.80,
    # 上市以来最低收盘 HKD（2025-09-01；Longbridge 日 K）；**证据，不入公式** | as-of 2026-09-14
    'close_own_min': 42.02,
    # 上市以来收盘中位 HKD（262 个交易日）；**证据，不入公式** | as-of 2026-09-14
    'close_own_median': 59.85,
    # 期权份数 = 满产 万片/年 = 2025 实测产量 69.04 + 招股书具名上海扩产约 50（A1） | as-of 2026-10-03
    'cap_kpcs': 119.0,
    # 放量前份数 = 2025 实测销量 万片（A1）；**只作敏感性** | as-of FY2025
    'vol_unit_kpcs': 63.33,
    # 其他业务收入补正（合并 ÷ 主营，2024）；A5 | as-of 2024
    'rev_basis_up': 1.20,
    # 同口径 H1'26 读数；**只作敏感性**（A5） | as-of 2026-06-30
    'rev_basis_now': 1.066,
    # 成功上限 ASP 元/片（2024 主营实测；A3）；期权单价 | as-of 2024
    'asp_h': 4080,
    # 期权单位经济 = 满产净利率点值：高盛 2028E 营收 63.83 亿 / 归母 18.06 亿（单家点估计，收入规模与满产同量级）；成本拆分中枢 28.6% 互证（A4） | as-of 2026-09-24
    'm_full': 0.283,
    # 满产净利率区间下端：≥2 家 2028E 共识最高（东吴国际 17.05%）；**只作敏感性**（A4） | as-of 2026-07-15
    'm_full_lo': 0.170,
    # 满产净利率区间上端：成本拆分外推上沿（2024 单位成本 × 119 万片 × 4,080，费用 3.82 亿）；**只作敏感性**（A4） | as-of 2026-10-03
    'm_full_hi': 0.306,
    # 2028E 共识净利率均值（东方财富 11 家 3.986 ÷ 33.17 亿）：低价世界的数，**只作敏感性**（上一轮误作单位经济，A4） | as-of 2026-10-03
    'm_align': 0.1202,
    # 净利率实测 = FY2024（A4）；**只作敏感性 / 下限** | as-of FY2024
    'm_h': 0.101,
    # 净现金 亿 CNY = 货币资金 33.01 − 有息负债 15.82（短借 11.97 + 一年内到期 1.84 + 长借 2.00 + 租赁 0.10）；三季报合并资产负债表（A6） | as-of 2026-09-30
    'net_cash_cny': 17.08,
    # 只按可随时支付现金（剔受限保证金 25.28）的净现金 亿 CNY；中报数，三季报未披露受限保证金；**只作敏感性**（A6） | as-of 2026-06-30
    'net_cash_free_cny': -10.35,
    # 满产份数所需扩产投入 亿 HKD = H 股国内产线扩张所得款项（未动用）；成功世界计入经营资本、同额从加回现金扣除（A6） | as-of 2026-06-30
    'capex_named_hkd': 12.307,
    # `sic` 腿 g2 来源 = 功率半导体 / 碳化硅横截面反解中位；`_AXIS.sic`；用时截到 G_cap 6% | as-of 2026-10-02
    # 对齐年份；`_AXIS.sic` | as-of 2026-10-03
    # 成功世界稳态回报；`_AXIS.sic`（同生意成熟同业为空 → 兜底「有壁垒的重资产」15%）；按序取：本票自身周期不可用（亏损 / 微利期、放量前，A6）→ 同业空 → 兜底 | as-of 2026-10-19
    # 成功世界高回报期 Y1（回报开始回落）；`_AXIS.sic`（继承 `_AXIS.ai-capex`）（A6） | as-of 2026-10-16
    # 成功世界高回报期 Y2（落稳）；`_AXIS.sic`（A6） | as-of 2026-10-16
    # 篮 4 常规经营 r = 10%（A14：器件与材料制造；客户 / 国别不命中篮 7、无公开报价不命中篮 6）；进期权与盈利尺参照，不进底牌；`gordon.BASKET_R`、`check_r` | as-of 2026-10-03
    'r_perp': 0.10,
    # 兑现年折现率（A2）；与 `r_perp` 同值（折 3 年 0.751） | as-of 2026-10-03
    'r_disc': 0.10,
    # 折现基准年 | as-of —
    'year_now': 2026,
    # 期权兑现年（具名：H 股 2026 中报扩产所得款项「至 2028 年底或之前」用毕 → 首个满产年）；A2 | as-of 2026-08-31
    't_opt': 2029,
    # 共识 2026E 归母 亿 CNY（同花顺 10 家均值，三季报前预测；盈利尺参照 A9） | as-of 2026-10-21
    'np26e_cny': 0.65,
    # 共识 2027E 归母 亿 CNY（参照） | as-of 2026-10-21
    'np27e_cny': 2.50,
    # 共识 2028E 归母 亿 CNY（参照；FY+2 → 折现） | as-of 2026-10-21
    'np28e_cny': 4.03,
    # 自身 H 股 PB 实测带下沿（Longbridge 2025-08 起日频）；**证据，不入公式**（A7） | as-of 2026-09-14
    'pb_own_min': 2.66,
    # 自身 H 股 PB 实测带上沿（同上） | as-of 2026-09-14
    'pb_own_max': 7.74,
}

# Original historical rationale and evidence; comments are not extra model inputs.
# - **业务地图摘要**：财报分部仅「半导体材料」100%（中报）。H1'26 起 8 寸主营收入占比已超 50%；导电型为主，半绝缘亦能量产；12 寸已完成全系列技术攻关、尚未成规模。境内外毛利率差大（H1'26 境内约 10%、境外约 42%）。同一产线、同一 P&L → 整公司尺，不用分部加总。
# - **属性 A — 上游衬底，利润跟 ASP/产能利用率走**：器件厂能讲 AIDC 电源叙事，天岳卖的是导电衬底商品层。可以量增、份额第一，仍因价格战亏损。**禁止**套器件 PE、主题倍数或卖方 20–30× PS。
# - **属性 B — 盈利弹性有两条腿，第二条依据薄弱**：H1'26 固定资产折旧 1.85 亿 = 收入的 20.3%；固定资产 36.96 亿、在建工程 2.26 亿。产能已建成，收入增长不带动同比例折旧 → 第一条腿。经营杠杆兑现后的满产净利率不进底牌，只进期权的单位经济（A4：卖方规模匹配的单家估计 + 成本拆分外推，以区间报出；A6 / A11）。
# - **属性 C — ASP 是成功路径的真正维度**：ASP 5,110（2022）→ 4,798（2023）→ 4,080（2024）→ **1,934**（2025 主营口径）；销量 6.38 → 22.63 → 36.12 → 63.33 万片。量在暴涨、价在腰斩。董事长公开表示价格将继续下降。**底牌不吃 ASP 修复**；修复至 2024 实测 4,080 是成功路径的单价——成功世界按具名产能 × 该单价 × 满产净利率（与该单价同一世界）、本票 Gordon 估值（A11）。
# - **属性 D — AIDC 不单列第二条期权（防双算）**：AIDC / 800V·SST 只作为「ASP/满产成功」同一条路径的需求叙事，**MUST NOT** 再加 \(\Delta Rev\times m\) 桥或第二条 \(V_{opt}\)。旧版 10 亿×12% 桥已删除。**叙事解剖（非公式）**：共识说的「瓶颈」是链条——机架功耗 → 800V DC / SST → 高压端 SiC（近端常配 GaN）→ 器件共用同一条**导电衬底漏斗**；天岳是漏斗股权代理（8 寸导电份额第一），不是器件 BOM 本身。量级坐标（卖方，不定锚）：中金测算单 MW SiC 含量随架构从 ~1.6k 颗升至全链路 SST 近万颗；五矿等折 6" 当量 AIDC 衬底 2030E ~73 万片（仍远小于同口径车用）。**「未来瓶颈」≠「今日缺货」**：Yole 已写供应链相对此前数年有所缓解；本票 2025 ASP 腰斩至 1,934 是价格战实证。部分 SST 走低压 GaN（例 Enphase），AIDC≠必然吃爆 SiC 衬底。观察项见 A13；细节草稿 历史本地缓存（不进 Inputs）。
# - **属性 E — A/H 双平台**：688234.SH 与 2631.HK 同一经营叙事，H 股相对 A 股折价交易；H 股流通盘仅 5,490 万股（占总股本 11.3%），流动性薄。核心预测可交叉 A 股共识；目标价不照搬 A 股 PS 锚；A 股溢价是市场事件，本框架刻意不承销（A13）。与 `WOLF.US` 同构：两票都是「底牌资产尺 + 成功路径 \(V_{opt}\)」，期权同挂同业尺轴 `_AXIS.sic`（同一把尺：满产利润率取数序、经营资本 ROE、轴 g2、篮 4），外部估值事件只作交叉。
# - **属性 F — 成功世界按本票尺估值，价值全在满产净利率**：无类似 INTC CPU 的当期稳态盈利腿；底牌 = 资产 PB 带。成功世界（满产 × ASP 回到 2024）按同业尺轴闭合：份数 = 具名产能，单位经济 = 满产净利率 28.3%（区间 17.0–30.6%，A4），ROE 只算经营资本（25.2%，单调区），Gordon g2 6%、回报按稳态回报三段在 2030–2035 回落到 15%、满产净利率同路回落到常态 16.8%（稳态回报 × 经营资本 ÷ 满产收入，推导值，A4）→ 10.31×，值 32.32 港元。ROE 过 r 的门槛是满产净利率 ≥ 11.2%（经营资本口径）；共识均值 12% 恰在门边、倍数约 11.0×，成功世界只值 15.49 < 账面。IPO 定价 42.80 只作交叉。
# - **倍数怎么来**：底牌 = 资产 PB 三档（具名情景：清算 / 不作废 / 一个账面；非分位，A7），自身 PB 实测带只作证据（三档全在带下）。期权上限锚 = 具名产能 × 实测 ASP × 满产净利率 × Gordon 稳态回报三段（g2=6%、ROE_经营、r=10%；回报与净利率同路 2030→2035 回落到 15% / 16.8%）（篮 4，A14；g2 取 `_AXIS.sic`）× 折现 + 加回现金（A6 / A11）；IPO 定价只作交叉；盈利尺参照 = 共识归母 × Gordon（g=0，A9）。
# | A1 | 成功路径的份数：**满产 119 万片/年** = 2025 实测产量 **69.04 万片**（年报「折合」口径；2026 中报称上半年「处于满产运行状态」）+ 招股书具名上海扩产**约 50 万片**（「以於 2027 年底前將我們在上海的大尺寸碳化硅襯底年產能增加約 50 萬片」）；东南亚基地未给量，不计。官方「合计设计年产能超过 50 万片」（2025 年报）与「折合 69.04 万片」口径不一致，待补。三季报期（2026-10-20）媒体转述：济南、上海临港工厂满负荷运转，二期扩产按计划推进（未给量，份数不动）。用于期权份数（具名的量；底牌是资产尺、不含共识，故无「共识已含」可扣）；2025 实测销量 63.33 万片（主营 12.25 亿 ÷ 1,934）只作敏感性。旧写法「临港一期 30 + 二期 50 + 济南约 39」同数（济南为倒推）；旧写「60% 投向临港二期」与招股书不符（国内扩产 55% + 海外 15%） | active | 2025 年报产销量表；2026 中报；H 股招股书（2025-08-11）所得款项用途 | `cap_kpcs`（期权份数）、`vol_unit_kpcs`（敏感性） |
# | A2 | 兑现年 **T = 2029**（具名）：H 股 2026 中报所得款项用途表——国内产线扩张 1,230.70 百万港元截至 2026-06-30 **未动用**，全部用途「悉數動用的預期時間」为「**至 2028 年底或之前**」（招股书原写 2027 年底前，已落后）→ 扩产在 2028 年底前完成，2029 为首个满产年。2029 = 当前财年 + 3 → 期权按篮 4 r 10% 折回 3 年（折 0.751）。对照：对齐年份 + 2 = 2030（−3.69 港元，敏感性）。**待核（2026-10-21）**：三季报不更新 H 股所得款项用途；2026-09-30 在建工程 3.37 亿（6-30 为 2.26 亿）、固定资产 39.30 亿（36.96 亿），货币资金反升至 33.01 亿——扩产资金动用进度待 2026 年报核 | active | H 股 2026 中报（2026-08-31）所得款项用途；招股书 | `t_opt`、`r_disc` |
# | A3 | ASP：不修复锚 **1,934**（2025 主营）；成功上限 **4,080**（2024 主营实测）。中间 3,000 ≈ 2025 车规级成交（表2 场景叙述用，不进底牌） | active | 招股书 2022–24 ASP；2025 主营 12.25 亿 ÷ 63.33 万片 = 1,934 | `asp_h`（交叉） |
# | A4 | **单位经济 = 满产净利率 28.3%，区间 17.0% – 30.6%**（valuation-rules「未建模期权」2026-10-03：份数按满产计时单位经济 MUST 配满产；同业尺轴 `_AXIS.sic` 取数序）。① **最远可见年卖方**：最远年 2028E（2029E / 2030E 无任何卖方公开点估计，待补；高盛 2026-09-24 用 2029E 34.6× PE 定价但未披露 2029E 净利）。2028E ≥2 家共识（同花顺 / 东方财富 11 家）净利率均值 12.0%、区间 7.6–17.0%，营收均值 32.15 亿——按 2025 ASP 折算约 138–143 万片，是「接近满产 × 低价」的世界，与成功世界的 ASP 4,080 不同世界，**不作单位经济**（上一轮的错：12% × 58.26 亿）；与满产份数收入同量级的只有**高盛 2028E 营收 63.83 亿 / 归母 18.06 亿 = 28.3%、毛利率 43.3%**（单家点估计，智堡摘要 106844，原文未见）→ 取作点值。② **公开数据推断**（≥2 期，历史本地缓存）：年报同年成本构成（2024：变动 1,615 元/片 + 固定制造费用 4.05 亿；2025：993 元/片 + 3.87 亿）外推到 119 万片 × 4,080（价格与成本取同一年 2024、自洽），销售+管理+研发 3.82–4.97 亿、新增折旧 1.34 亿、税 15%、其他业务毛利 0 → 净利率 **15.3% – 30.6%，中枢 28.6%**，与 ① 互证；按 2025 价格 1,934 满产只有约 −5% – 10%（中枢 6%，与 Q2'26 现有产能满产实测核心净利率约 6.9% 吻合）——那是低价世界，不是成功世界。**Q3'26 读数（三季报 2026-10-20）**：单季毛利率 27.46%、扣非净利率 14.9%（归母 13.3%），已高于按 2025 价格满产推断的上沿 10%——现有产能已离开 1,934 的低价世界，方向上支持成功路径；公司归因规模效应与产品结构（8 寸收入占比 >50%）、衬底成本显著下降，未披露单价与销量，且未满产，**不替换** `m_full`，状态仍 active。③ **实测下限**：FY2024 净利率 10.1%（ASP 4,080、36.12 万片、未满产）；FY2021 18.2% 系营业外，不算。区间下端取 ≥2 家 2028E 最高 17.0%（东吴国际），上端取推断上沿 30.6%。**推断假设**：利用率回升全部归到增长；费用率随规模摊薄；ASP 4,080 能与 119 万片同时成立（成功世界的定义，属性 C）；数据中心 800V / 固态变压器使高功率产品占比高于历史（历史年只作下限）。**满产净利率不永续——常态净利率 16.8%，与回报同路回落（用户 2026-10-19 认可）**：28.3% 是 AI 数据中心电源带来的短缺 / 涨价期读数，回报已按稳态回报三段在 2030→2035 回落到 15%（A6），同一种短缺不能在回报上回落、在利润率上永续（valuation-rules「稳态回报三段」同一公司内部 MUST 一致；「未建模期权」兑现年的利润率与回报沿高回报期走）。`_AXIS.sic` 与本票都没有成熟期碳化硅衬底净利率的卖方或同业读数（轴 §2b 同生意成熟同业为空），常态值按**推导**取：常态时现有产能也只赚稳态回报 → 常态净利率 = 稳态回报 15% × 成功世界经营资本 65.42 亿 ÷ 满产收入 58.26 亿 = **16.8%**（eval 由 `ss_return_sic` × 经营资本 ÷ 收入派生，不另设 Inputs 行；**推导值，非独立来源**）。交叉：≥2 家 2028E 共识最高一家东吴国际 17.0%，同量级，但那是爬坡年读数，不单独作常态来源。路径：兑现年 2029 起 28.3% 维持到 Y1 2030，2030→2035 线性回落，Y2 2035 起 16.8% 永续（与回报同一日历）。复核：出现成熟期碳化硅衬底净利率的卖方或同业读数（≥5 年）→ 换掉推导值 | active | 同花顺 F10 业绩预测（截至 2026-09-30）；2026 三季报；东方财富 F10（2026-10-03）；智堡 106844（高盛 2026-09-24）；2024 / 2025 年报成本分析表与产销量表；2026 中报；常态净利率：`_AXIS.sic` §2b 稳态回报 15% × A6 经营资本 ÷ A11 满产收入，用户认可 2026-10-19 | `m_full`（期权）、常态净利率（eval 派生）、`m_full_lo` / `m_full_hi` / `m_align` / `m_h`（敏感性） |
# | A5 | 其他业务收入补正系数 **1.20**（2024 合并营收 ÷ 主营营收；2025 1.196、H1'26 1.066）。多出的是报表「其他业务」，毛利率 −9% – +5%，基本不赚钱；主营 ASP 已含半绝缘型（旧写「非导电型补正」有误）。满产净利率取自合并口径（卖方与推断都按合并营收算），故收入保留 × 1.2；按 1.07 的敏感性见 Outputs | active | 2023–2025 年报、2026 中报合并 / 主营营收 | `rev_basis_up` |
# | A6 | **Gordon 生成期权上限锚（本票尺，同业尺轴 `_AXIS.sic`）**：\(PE\) = 留存形态 Gordon，新投资回报走 valuation-rules「经营价值与超额现金」② 稳态回报三段：兑现年 2029 起回报 = 成功世界经营 ROE，到 Y1 2030 后线性回落，Y2 2035 起落稳到稳态回报 15%（`_AXIS.sic` `ss_return_sic`：2026-10-19 按序取：① 自身周期不可用——当期在盈亏线附近（共识 2026E ROE 0.9%）、历史为亏损 / 微利期，满产导电型 8 寸是结构变化之后的生意、还没有一轮完整周期 → ② 同生意成熟同业为空 → ③ 兜底「有壁垒的重资产」（轴 `ss_return_sic`）；Y1 / Y2 继承 `_AXIS.ai-capex`，门槛档「高」）。**ROE 只算经营资本**：经营资本 = 归母权益 71.95 − 净现金 17.08（货币资金 33.01 − 有息负债 15.82：短借 11.97 + 一年内到期 1.84 + 长借 2.00 + 租赁 0.10，三季报 2026-09-30）= 54.87 亿；满产份数里的上海 50 万片扩产仍需投入，具名资金 = H 股国内扩产所得款项 1,230.70 百万港元 ÷ 1.1668 = **10.55 亿元**（未动用，已在货币资金里）→ 成功世界经营资本 **65.42 亿**，同额从加回现金里扣掉（加回 17.08 − 10.55 = **6.53 亿**，不折现）。ROE = 16.49 ÷ 65.42 = **25.2%** > r 10%（单调区）。g2 = 6.0%（`_AXIS.sic` 功率半导体横截面中位 7.12% 截到 \(G_{cap}\)）。**满产净利率走同一条日历路径**（A4，2026-10-19）：2030 前 28.3%，2030→2035 线性回落，2035 起常态 16.8%（= 15% × 65.42 ÷ 58.26）→ **10.31×**（对 2029 满产利润；只回落回报、净利率永续时 15.61×，回报也永续沿用 25.2% 时 19.05×）。**口径提醒**：货币资金里 25.28 亿是受限保证金（票据 / 信用证；中报数，三季报未披露），只按可随时支付的现金算则净负债 10.35 亿（中报）、经营资本 92.85 亿、ROE 17.8% → \(V^{G}_{H}\) 34.34（敏感性；常态净利率随经营资本升到 23.9%）。旧口径（ROE 分母用全部权益 71.09、g2 = 0 无同业锚、篮 7 1/r 6.67×）撤销 | active | 2026 三季报合并资产负债表（权益、净现金，2026-09-30）；2026 中报（受限保证金）、H 股中报所得款项用途；`_AXIS.sic` §2 | `equity_cny`、`net_cash_cny`、`capex_named_hkd`、`g2_sic_src`、`r_perp` |
# | A7 | 底牌 = PB **0.55 / 0.80 / 1.00** × BPS：**L** 专用设备清算/作废压力；**M** 产能不作废但盈利未稳；**H** 值一个账面、仍不修复 ASP。三档是具名情景，非分布分位；**自身 PB 实测带**（H 股 2.66–7.74×、A 股 3.5–15.55×）只作证据——市场从未印过带内的价（③ 出带，只披露）。盈利尺参照三年（1.56 / 6.02 / 8.02）全低于 L：资产尺是上限而非地板（A2e-1 `asset_play` 行；scenario_L/M 0.13 < 0.3 的回问已由 2026-09-10 换资产尺裁定） | active | 中报 BPS；Longbridge `valuation --history --indicator pb`（688234.SH / 2631.HK，2026-09-14）；对话锁定期权主导重拆 2026-09-10 | `pb_l`/`pb_m`/`pb_h`；底牌 |
# | A8 | **未采用**卖方 20–30× 前瞻 PS（及三位数目标价）：A 股 TP 均值 97.70 CNY ≈ 114 HKD ≈ 2028E 118× PE；yfinance 2 家 108.9–110.8 HKD。刻意不承销（A13） | active | 同花顺 F10；yfinance 2026-09-14 | 防尺子被 TP 绑架 |
# | A9 | 共识主采同花顺 F10 A 股 10 家（均值，区间未披露）；yfinance 仅 1 家（0.567 / 0.892 CNY）；**盈利尺参照** = 共识归母 × Gordon（g = 0；ROE 0.9 / 3.5 / 5.6% < r → 1/r = 10×）= 1.56 / 6.02 / 9.70（2028E 折现 0.826 → 8.02）港元，只作 A2e-1 要求的参照与杠杆 ①（A13）；两段式（2027→28 +61%，ROE 3.5%）段一派息率 −16.6 退化（杠杆 ②） | active | 同花顺 2026-10-21；yfinance 2026-09-14 | 参照；A2f |
# | A10 | 公司锚点 = **底牌 + \(V_{opt}\)**；zone 只读底牌（A2e-7）；表3 按档 \(p_k\) 修正，不参与判定（现行 \(V_{opt}\) = 15.00） | active | 对话锁定 2026-09-10；2026-09-14 重开期权；2026-10-03 同业尺轴 | §3 |
# | A11 | **\(V_{opt}\) = max(0, \(V^{G}_{H}\) − 底牌 H) = 32.32 − 17.32 = 15.00**（同业尺轴 `_AXIS.sic`：上限锚由公开数据闭合、借量不借价、单位经济配满产、按本票尺在兑现年估值折回）。链：具名产能 119 万片（A1）× 2024 实测 ASP 4,080 × 1.2（A5）= 58.26 亿元 × 满产净利率 28.3%（A4）= 归母 **16.49 亿**（税后，税 15% 已含在净利率里）→ ROE_经营 25.2%（A6）→ 稳态回报三段且净利率同路回落（g2 6%，回报 25.2% 与净利率 28.3% 维持到 2030，2035 落稳到 15% 与常态 16.8%，A4 / A6）= **10.31×**（2029–30 派息 1 − 6%/25.2% = 76%，落稳后 60%）→ 2029 经营价值 170.0 亿 ÷ 1.1³ = 127.7 亿 + 加回现金 6.53 亿 = 134.3 亿 × 1.1668 ÷ 4.846 亿股 = **32.32** 港元。≠「增量利润 × H 档倍数」：底牌是资产尺、没有 H 档盈利倍数，成功世界倍数全部由经营 ROE 与轴 g2 生成。**敏感性（区间两端与口径；常态净利率按各组自己的经营资本 ÷ 收入派生，满产净利率 ≤ 常态时不回落）**：净利率 17.0% → 28.25（\(V_{opt}\) 10.93，ROE 15.1% 略高于 15%、常态 16.8%，回落极小）/ 30.6% → 33.15（15.82；常态同为 16.8%，上端几乎不加价）/ 共识均值 12.0% → 15.49（0）/ FY2024 实测 10.1% → 10.43（0）；只算可随时支付现金 → 34.34（17.02）；不扣扩产投入 → 31.54（14.22；经营资本小、常态净利率随之降到 14.5%，故反而略低）；补正 1.066 → 31.18；兑现 2030 → 28.63；g2 5% / 无增长 → 见 Outputs；满产净利率永续（10-19 前口径，只回落回报）→ 48.12（30.80）。**撤销**：上一轮「2028E 共识 12.0% × 满产收入、ROE 分母用全部权益、篮 7 1/r」= 6.43 → 0（爬坡中段 / 低价世界的利润率乘满产 × 修复价收入，且把净现金与未投募资算进 ROE 分母）；更早的 IPO 定价上限锚 42.80（借价）只作交叉。**升级门槛**：出现 ≥2 家 2029E+ 共识（或 ≥2 家满产规模的利润率估计）→ 换掉单家点值；放量后年份 ≥2 家正共识且覆盖到满产 → 盈利尺进底牌（框架纠正）。**证伪**：ASP 新低且结构性涨价未延续、份额崩、上海扩产资金到 2028 年底仍未动用（兑现年后移）、满产年实测净利率 < 11.2%（ROE_经营 < r） | active | A1 / A2 / A4 / A6；`_AXIS.sic` | \(V_{opt}\) |
# | A12 | 表3 \(p_k\) = **0 / 0.25 / 1.0**（eval 常量，不进 Inputs；`_AXIS.sic` 同值）。\(p_M\) **无概率锚·拍值**（无 INTC 式外部代工营收硬锚）；观测代理（只改 \(p_M\)）：季度 ASP vs 1,934（2026 年 5–6 月对部分订单「小双位数」结构性涨价，东吴国际 2026-07-15）、单季毛利率（Q2'26 25.4% → Q3'26 27.46%，升；单价与扩产资金动用三季报均未披露，\(p_M\) 2026-10-21 不动）、上海扩产资金动用进度 | active | A2e-7d；对话 2026-09-14 | 表3 |
# | A13 | **四个合法杠杆逐一交代 + 观察项**：① Gordon 倍数——底牌为资产尺；盈利尺参照（共识 × Gordon，ROE<r → 1/r）1.56 / 6.02 / 8.02 港元全低于 L，只能拉低不能抬；② 有共识年份的过渡——2027E→2028E +60%（n=1）只对盈利尺有意义，且分子仍是低价世界；两段式在 ROE 3.5% 下派息率退化；③ \(V_{opt}\)——成功世界按具名产能 × 满产净利率（2030→2035 回落到常态 16.8%）× 本票 Gordon 值 32.32，期权 15.00（表3）；IPO 定价 42.80 只作交叉；④ 候选带——底牌无单家 / 待补输入，不可用。H + V 之上刻意不承销：A 股溢价（属性 E）、街的 20–30× 前瞻 PS（A8）。**观察项**：① 季度 ASP 与境内毛利率（A3）；② 固定资产 39.30 亿（2026-09-30）减值风险（底牌 L 世界）；③ 产能口径「折合 69.04」vs「设计 >50」（A1）；④ A 股溢价与 H 股流通盘薄（属性 E）；⑤ 满产利润率的第二家来源（A11 升级门槛） | active | 对话 2026-09-14；2026-10-03 同业尺轴 | §0；表3；`stretched` 行 |
# | A14 | 归篮：整公司 → **篮 4 常规经营 10%**（2026-10-03 篮 7 收窄后改归）。篮 7 判据逐条不命中：单一客户 2025 第一大 **20.17%**（< 50%）、前两大 **32.82%**（< 70%；2024 为 19.01% / 36.48%；年报「单个客户超 50% / 严重依赖」勾「不适用」）；国别——中国上市公司在本仓按篮 4 / 6 归（`300750.SZ`、`1810.HK`），境外收入占 40–55%，不算高国别风险；收入不依赖未落定融资或未签约客户。单产品、未盈利、小流通盘、故事属性**不**再入篮 7。篮 6 不成立：碳化硅衬底无交易所或合同引用的公开报价（上海有色网只有 4/6 寸会员调查价、无 8 寸；集邦为付费报告），龙头成交为一对一议价 + 长协（英飞凌长期供应协议、公司「坚持价值定价」、2026 年按单结构性涨价）——盈利不是商品价函数，价格战压价属行业周期，进 L 情景与 \(p_k\)。篮 4 判据：常规经营现金流、不命中其余篮子。无篮子对（不留篮 7）。CAPM 粗筛未做（无正 E）。**r = 10% 不进底牌**：`r_perp` / `r_disc` 只进期权（A6 / A11）与盈利尺参照（A9）。旧篮 7 15% 下的期权读数（同一新口径）作对照见 Outputs | active | 2024 / 2025 年报前五名客户表；`_AXIS.sic` §1；`gordon.BASKET_R`；`valuation-rules.md`「§r 篮子」（2026-10-03） | `r_perp`、`r_disc`；锚点与 zone 不受篮子影响 |
# | A15 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」）读数**：底牌是资产 PB 尺（当期账面 × PB），本节不适用——没有前瞻分子、不单列超额现金、不做时点对齐；**归母比例 1**（少数股东权益 0，2026-06-30），期权加回的净现金不打比例；**增长期资金缺口**只在期权世界里：上海 50 万片扩产的具名投入 10.55 亿已进成功世界经营资本、同额从加回现金扣掉（A6），底牌不扣。期权已从兑现年 2029 按整年 3 年折回估值基准年 2026（`year_now`），属「已折到估值基准日」，本轮不动。稳态回报三段只作用于期权（A6：Y1 2030 / Y2 2035 继承 `_AXIS.ai-capex`，稳态 15% 取自 `_AXIS.sic`；满产净利率同路回落到常态 16.8%，A4，2026-10-19）；碳化硅衬底不是商品腿（ASP 是本票实测价，不是商品价情景），也不属叙事换代（自身周期不可用是因亏损 / 微利与放量前规模，不是业务模式变化——衬底生意没换，同业层为空时落兜底）。**本框架无打折 k** | active | 2026 中报（yfinance 少数股东权益）；valuation-rules「经营价值与超额现金」①–④ | 只影响 \(V_{opt}\)；底牌不变 |

SHARED = ("g2_sic_src", "t_align", "ss_return_sic", "y1_sic", "y2_sic")  # rows that must equal _AXIS.sic
FORMULA_IDS = (
    "sicc_asset_pb_bottom_v1",
    "sicc_fullcap_sic_axis_vopt_v6",
)
# 表3 per-tier credit (A12, _AXIS.sic): 拍值, no external anchor. Never an Input, never the base.
P_K = (0.0, 0.25, 1.0)
KPCS = 1e4
YI = 1e8
TOL = 0.05

REQUIRED = [
    "shares", "fx_cny_hkd", "equity_cny",
    "pb_l", "pb_m", "pb_h",
    "ipo_price_hkd", "close_own_min", "close_own_median",
    "cap_kpcs", "vol_unit_kpcs", "rev_basis_up", "rev_basis_now", "asp_h",
    "m_full", "m_full_lo", "m_full_hi", "m_align", "m_h",
    "net_cash_cny", "net_cash_free_cny", "capex_named_hkd",
    "g2_sic_src", "t_align", "ss_return_sic", "y1_sic", "y2_sic", "r_perp", "r_disc", "year_now", "t_opt",
    "np26e_cny", "np27e_cny", "np28e_cny",
    "pb_own_min", "pb_own_max",
]


def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float,
            fade_margin: bool = True) -> float:
    """Three-segment RONIC path (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    gordon.py helper is not built yet).  Multiple on the numerator year t0 (t = 1) full-margin
    earnings: the retention of calendar year c earns RONIC = forward roe while c <= y1, falls
    linearly to the steady return between y1 and y2, and from y2 on the steady return holds
    in a Gordon tail.  r_s is capped at the forward roe and floored at r by the caller.

    fade_margin (2026-10-19, user; retention.md「同一公司内部 MUST 一致」, options.md
    「兑现年的利润率与回报沿该环节的高回报期走」): the full-capacity margin walks the same
    calendar path — held to y1, linear to the normal margin by y2, normal thereafter.  The
    normal margin = steady return × operating capital ÷ full-capacity revenue, i.e. the
    margin at which the existing capital also earns the steady return, so its ratio to the
    full margin is rs / roe.  g <= 0 never consumes RONIC; the margin path still applies."""
    rs = min(roe, r_s)
    m_ss = rs / roe if fade_margin else 1.0

    def lin(cal: int, a: float, b: float) -> float:
        if cal <= y1:
            return a
        if cal >= y2:
            return b
        return a + (b - a) * (cal - y1) / (y2 - y1)

    def payout(ron: float) -> float:
        return 1.0 if g <= 0 else min(1.0, 1.0 - g / ron)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * m_ss * payout(rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * lin(cal, 1.0, m_ss) * payout(lin(cal, roe, rs)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1


def success(inp: dict[str, float], *, margin: float | None = None, kpcs: float | None = None,
            net_cash: float | None = None, capex: bool = True, basis: float | None = None,
            t_opt: float | None = None, g2: float | None = None, r: float | None = None,
            fade_margin: bool = True) -> dict[str, float]:
    """Full-capacity world on the own ruler (A4 / A6 / A11): operating-capital ROE, axis g2, basket r;
    the full margin fades with the return to the derived normal margin (A4 / A6)."""
    r = inp["r_perp"] if r is None else r
    g2 = min(inp["g2_sic_src"], g_cap(r)) if g2 is None else g2
    rev = (inp["cap_kpcs"] if kpcs is None else kpcs) * KPCS * inp["asp_h"] * (inp["rev_basis_up"] if basis is None else basis) / YI
    np_h = rev * (inp["m_full"] if margin is None else margin)
    nc = inp["net_cash_cny"] if net_cash is None else net_cash
    k = inp["capex_named_hkd"] / inp["fx_cny_hkd"] if capex else 0.0
    cap_op = inp["equity_cny"] - nc + k
    roe = np_h / cap_op
    t_o = inp["t_opt"] if t_opt is None else t_opt
    # 稳态回报三段: success-world RONIC holds to y1_sic, fades to max(ss_return_sic, r) by y2_sic
    # (_AXIS.sic §2b; own-cycle floor: none -- SICC's own record is loss-making, below r).
    rs = max(inp["ss_return_sic"], r)
    pe = (path_pe(g2, roe, r, int(t_o), int(inp["y1_sic"]), int(inp["y2_sic"]), rs, fade_margin)
          if roe > 0 else 0.0)
    m_norm = min(roe, rs) * cap_op / rev if roe > 0 else 0.0  # normal net margin (derived, A4)
    years = t_o - inp["year_now"]
    disc = (1.0 + r) ** (-years)
    op_value = pe * max(0.0, np_h) * disc
    v = (op_value + nc - k) * YI * inp["fx_cny_hkd"] / inp["shares"]
    return {"rev": rev, "np": np_h, "cap_op": cap_op, "roe": roe, "pe": pe, "g2": g2, "disc": disc,
            "m_norm": m_norm, "op_undisc": pe * max(0.0, np_h), "addback": nc - k, "v": v}


def evaluate(inp: dict[str, float]) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('t_align', 't_opt', 'year_now', 'y1_sic', 'y2_sic'))
    if inp['y2_sic'] <= inp['y1_sic']:
        raise ValueError('invalid return path years')

    # r must be the basket value named in the Inputs source cell (A14); r_disc
    # carries no basket tag and only has to be a basket-table value.
    baskets = {"r_perp": 4}
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (A14)")
    errors += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    errors += check_r(inp["r_disc"], "r_disc", baskets.get("r_disc"))
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        errors.append(f"r_disc {inp['r_disc']} != r_perp {inp['r_perp']}: the discount year uses the same basket r (A2 / A14)")
    g2 = min(inp["g2_sic_src"], g_cap(inp["r_perp"]))
    errors += check_g_cap(g2, inp["r_perp"], "g2 (_AXIS.sic)")
    if not (inp["pb_l"] < inp["pb_m"] < inp["pb_h"]):
        errors.append(f"pb order violated: {inp['pb_l']}/{inp['pb_m']}/{inp['pb_h']}")
    if not (inp["m_full_lo"] <= inp["m_full"] <= inp["m_full_hi"]):
        errors.append(f"m_full {inp['m_full']} outside its stated range [{inp['m_full_lo']}, {inp['m_full_hi']}] (A4)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")

    axis = {key: inp[key] for key in SHARED}

    if errors:
        raise ValueError('; '.join(errors))

    # --- bottom card: asset PB ------------------------------------------------
    bps = inp["equity_cny"] * YI * inp["fx_cny_hkd"] / inp["shares"]
    L = inp["pb_l"] * bps
    M = inp["pb_m"] * bps
    H = inp["pb_h"] * bps
    A, B = cut_points(L, M, H)

    # --- option: full-capacity world on the own ruler (A4 / A6 / A11) ---------
    post = success(inp)
    v_top = post["v"]
    v_opt = max(0.0, v_top - H)
    adj = [x + p * v_opt for x, p in zip((L, M, H), P_K)]
    adj_a, adj_b = cut_points(*adj)
    sens = {
        "margin lo (2028E cons top)": success(inp, margin=inp["m_full_lo"]),
        "margin hi (cost split top)": success(inp, margin=inp["m_full_hi"]),
        "margin 2028E cons mean": success(inp, margin=inp["m_align"]),
        "margin FY2024 measured": success(inp, margin=inp["m_h"]),
        "free cash only": success(inp, net_cash=inp["net_cash_free_cny"]),
        "no expansion capex": success(inp, capex=False),
        "other-business 1.066": success(inp, basis=inp["rev_basis_now"]),
        "t_opt = t_align + 2": success(inp, t_opt=inp["t_align"] + 2),
        "g2 -1pp": success(inp, g2=g2 - 0.01),
        "g2 0": success(inp, g2=0.0),
        "pre-ramp volume": success(inp, kpcs=inp["vol_unit_kpcs"]),
        "old 篮 7 r 15%": success(inp, r=0.15),
        "margin perpetual (pre-10-19)": success(inp, fade_margin=False),
    }

    # --- earnings-ruler reference (A2e-1 asset_play row) ----------------------
    ref = {}
    for label, key, years in (("2026E", "np26e_cny", 0), ("2027E", "np27e_cny", 0), ("2028E", "np28e_cny", 2)):
        np_y = inp[key] * YI
        roe = np_y / (inp["equity_cny"] * YI)
        pe = perpetual_pe(0.0, roe, inp["r_perp"])
        disc = (1.0 + inp["r_disc"]) ** (-years)
        ref[label] = {"roe": roe, "pe": pe, "v": pe * np_y * inp["fx_cny_hkd"] / inp["shares"] * disc}
    g1 = inp["np28e_cny"] / inp["np27e_cny"] - 1.0
    roe27 = ref["2027E"]["roe"]
    two_stage = two_stage_pe(g1, 1, 0.0, roe27, inp["r_perp"])

    if inp['t_opt'] <= inp['year_now']:
        errors.append('option year must be later than base year')
    errors += ladder('base', L, M, H)
    if abs(adj[0] - L) > 1e-9:
        errors.append('option probability leaked into base')
    if not all(x['v'] < L for x in ref.values()):
        errors.append('earnings reference exceeds asset floor')
    if errors:
        raise ValueError('; '.join(errors))
    return {'ticker': '2631.HK', 'currency': 'HKD',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-21', 'historical_framework_as_of': '2026-10-21',
            'anchors': dict(zip('LMH', (L, M, H))), 'candidate': None,
            'option': {'value': v_opt, 'weights': dict(zip('LMH', P_K)),
                       'anchors': dict(zip('LMH', adj))},
            'axis': axis, 'g2': g2, 'bps': bps, 'L': L, 'M': M, 'H': H, 'A': A, 'B': B,
            'post': post, 'v_top': v_top, 'v_opt': v_opt, 'adj': adj,
            'adj_a': adj_a, 'adj_b': adj_b, 'sens': sens, 'ref': ref,
            'g1': g1, 'roe27': roe27, 'two_stage': two_stage}


def calculate(context):
    sic, capex = context['axes']['sic'], context['axes']['capex']
    if capex.get('role') != 'path_reference':
        raise ValueError('SICC requires the AI return-path reference role')
    shared = {key: sic[key] for key in ('g2_sic_src', 't_align', 'ss_return_sic')}
    shared.update(y1_sic=capex['y1_ai_capex'], y2_sic=capex['y2_ai_capex'])
    result = evaluate({**INPUTS, **shared})
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'shared': shared, 'option_weights': P_K,
         'units_10k': KPCS, 'units_100m': YI}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'HKD_PER_SHARE'}
    result['segments'] = {'assets': {'unit': 'HKD_PER_SHARE', 'values': dict(result['anchors'])}}
    result['option']['value_unit'] = 'HKD_PER_SHARE'
    result['key_parameters'] = {
        'asset_book_multiple': {'unit': 'MULTIPLE', 'values': {t.upper(): INPUTS[f'pb_{t}'] for t in 'lmh'}},
        'success_discount_rate': INPUTS['r_perp'], 'success_growth_rate': result['g2'],
        'success_forward_return': result['post']['roe'],
        'success_steady_return': min(result['post']['roe'], max(shared['ss_return_sic'], INPUTS['r_perp'])),
    }
    result['review_flags'] = ['historical_capacity_and_volume_basis_mismatch',
                              'historical_success_margin_single_source',
                              'historical_expansion_capital_and_timing_unverified']
    return result
