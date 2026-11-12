#!/usr/bin/env python3
"""AMZN valuation; legacy inputs and decisions preserved, no document parsing.

Amounts are USD millions except capex_guide (USD), shares are millions.  The
historical financial judgments and formula explanations follow the inputs and
legacy implementation; this migration does not update research or valuation.
"""
from __future__ import annotations
from lib.gordon import check_basket_pair, check_g_cap, check_k_declared, check_r, payout
from lib.inputs import require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'),
                'axes': {'lab': 'frontier_lab_funding', 'capex': 'ai_capex'}}

FORMULA_ID = "amzn_fwd_numerator_gordon_aws_retail_portfolio_v1"
LISTING_CCY = "USD"
TOL = 0.05
H1_TOTAL_OPERATING_INCOME = 51313.0  # 10-Q 2026-06-30 Note 8, USD millions
MIN_R_MINUS_G = 0.02
K_LADDER_TOL = 1e-4
IC_SENSITIVITY = (1.20, 1.40)
MAX_LEG_ROE = 0.60  # refuse capital-allocation artefact in retail leg

# Source and intent are preserved from the pre-migration framework.
# | A1 | 林奇主类 `fast_grower` + 次类 `stalwart`：经营利润 +36%、AWS +37%、零售利润率仍在扩张，三块都在增利润；次类提醒零售腿的倍数纪律 | active | 10-Q 2026-06-30；卖方 2026E 收入 +15.5% / 2027E +14.3%（yfinance） | 主尺骨架；L 按 `fast_grower` 退到实测过的坏（A5） |
# | A2 | **分子年份 = FY2027E 共识区间**：基座 = H1 2026 分部 OI ×2 × (1−税率) + 净利息，当期核心 EPS 7.61；\(k_{eps}\) = 8.69 / 10.47 / 15.04 ÷ 7.61 = 1.141 / 1.375 / 1.975。EBIT 侧交叉：Longbridge 季度 EBIT 共识 Q1'27 303.6 亿 vs Q1'26 实际 238.5 亿 = +27%，与 EPS 桥 +37.5%（含利息与税率）同向。FY2027 年初的值按时点对齐折回 0.5 年（A16） | active | yfinance earnings_estimate 2026-09-21（52 家）；Longbridge consensus 2026-09-21 | `k_eps_*`、`eps_fy27e_*` |
# | A3 | 正常化税率 **19.6%** = FY2025 10-K 有效税率；不用 H1 2026 的 23%（含 159 亿离散税，主要是 Anthropic 标记的递延税） | active | 10-K 2025；10-Q Note 7 | `tax_rate` |
# | A4 | **云腿留存回报率 = 新投资本的边际稳态 ROIC，不是平均 ROE**：Gordon 的 b = g/ROE 量的是「为增长留下的钱按什么回报率再投」，AWS 的增量资本是数据中心，回报率取投产后第 2–3 年的稳态（valuation-rules「ROE_proj 一律取稳态，不取首年」）。来源层级：① 汇丰 2027E AWS ROIC **18.9%**（99586，第二年口径）→ 底牌；② 自身均值口径实测 16.4% → 敏感行；③ 实测首年 FY2025 → 2026H1 年化 ΔNOPAT ÷ Δ资本 ≈ 13% → 下界披露。**FY2027 年初资本快照 ROE（M 档 19.0%）只披露**：FY2027 是扩张顶峰，快照不是稳态。年初资本按 b1 = g/ROE 滚未入账 2H26（与 GOOG A25 同口径）；capex 潮实际留存远大于此，+20% / +40% 敏感行见 Outputs（`ic_fy27_path` 待补） | active | Wisburg 99586（2026-08-06）；10-Q Note 8 分部资产 2025-12-31 / 2026-06-30；10-K 2025 | `roic_marg_aws`；AWS 两子腿倍数 |
# | A5 | **L 档 AWS 利润率退回 FY2025 实测 35.4%**（现 38.6%），分子 ×0.919，边际 ROIC 同比例缩（退坡不是免费的）；`fast_grower` 的 L 必须退到实测过的坏，不是想象的坏 | active | 10-K 2025：AWS OI 45,606 / 收入 128,725 | `aws_om_l` / `aws_om_now` |
# | A6 | **归篮**：AWS 非实验室子腿 → **篮 4 龙头制造 10%**（常规经营现金流、龙头、可见度高）；零售腿 → **篮 4**（消费零售龙头）；AWS 实验室子腿（OpenAI + Anthropic）→ **篮子对**（`valuation-rules`「篮子对」，2026-09-23）：**过渡篮 7 单押 / 故事 15%**（判据「收入依赖对手方未落定融资」：两家 RPO 占 48%，对手方的钱一半是亚马逊自己投的；单一客户 ≥50% 的收入判据不触发，触发的是融资判据，与 `ORCL.US` A7 同一条理由）→ **终值篮 4 10%**（实验室做成了的世界里是用自身收入付账的超大客户；稳态特征、共用 k_lab 0.30、合篮条件由 `_AXIS.frontier-lab-funding` §3 一次定义）。本腿单段 Gordon，过渡篮无算术作用点，**到达风险全部在 k_lab**。**本票第二层**：「亚马逊投钱 → 实验室付给 AWS」的循环在稳态世界里应当消失（实验室用自己的收入付账）；若循环结构性延续（AWS 实验室收入持续由亚马逊对同一对手方的新增投资覆盖），即轴 §3c 的合篮情形，回单篮。**禁双计声明**：投资组合腿的折价带（L 50% / M 30% / H 15%）定价的是**持股价值**，k_lab 定价的是**收入子腿**，同一个「实验室失败」事件打到两条不同的现金流上，各自计一次，不重复；L 档（共识低端 + AWS 利润率退坡）不含实验室失败情景，k_lab 不与之重叠。份额 **20%** = `估算`：RPO 48% × 4,960 亿 ÷ 加权剩余期 6.4 年 ≈ 每年 372 亿 vs FY2027E AWS 收入约 2,200 亿 → 17%，取 20%；下界 = 今天 AI ARR 250 亿 ÷ AWS 年化 1,690 亿 = 15%，上界 = RPO 份额 48%（两条敏感行）。CAPM 粗筛 = USD \(r_f\) 中枢 4.0% + β 1.443 × 4.5% = **10.5%**，与篮 4 偏离 +0.5pp，不进质疑清单 | active | 汇丰 99586；10-Q（RPO 4,960 亿、加权剩余期 6.4 年）；GS 98382（AI ARR 250 亿）；yfinance β；`_AXIS.frontier-lab-funding` §3 | `r_perp` / `r_aws_lab` / `r_aws_lab_t` / `k_lab` / `share_lab_aws` |
# | A7 | **永续 g**：AWS **6.0%** = 云同业市价反解（汇丰隐含 2028E EV/EBIT 经本仓 Gordon 单位反解：AWS 7.26% / Azure 7.02% / GCloud 3.97%）截到 \(G_{cap}\) = min(6%, r − 4%) = 6%；零售 **4.0%** 无同业锚·自定（±1pp 敏感行）。同世界门：分子年到更远年方向为上行（JPM 2028E 13.0 > 2027E 10.47），g > 0 合法 | active | GOOG.US A7 横截面；JPM 98441 | `g2_aws` / `g2_ret` |
# | A8 | **留存去向审计：E 桶**（capex 持续远大于折旧、无终点：FY2018 → FY2025 capex 134 → 1,318 亿，D&A 153 → 658 亿，NPPE 618 → 3,570 亿）→ 完整式；「模型视同派出、实际留存的现金」按前瞻分子形态只算未入账 2H26：(1 − 实付派息 0 − b1) × 未入账 NOPAT。**打折 k = 0 / 0 / 0**（来源 ①：近 5 年无单笔 ≥ 归母权益 5% 的现金收购（MGM 85 亿 / One Medical 39 亿 < 5%），无回购；capex 投 AWS 边际 ROIC 18.9% ≥ r；对 Anthropic 180 亿成本的投资已标记到 1,900 亿 ≥ r）。**杠杆门未触发**：净债（长期债务 1,289 + 经营租赁 943 + 融资义务 89 − 现金 782 − 债券 401）= 1,138 亿 / FY2025 EBITDA 1,458 亿 = **0.78**；利息 23 亿 / EBIT 800 亿 = **2.9%** | active | SEC XBRL companyfacts（2018–2025）；10-Q 2026-06-30 | `payout_3y` / `k_*`；`net_debt_ebitda` / `interest_ebit` |
# | A9 | **H 档分子 15.04 疑含 Anthropic 标记收益**：FY2026E 共识 12.88 明显含 H1 的 628 亿标记；卖方「干净」的 2027E 在 11–13（Citi 350 ÷ 31.5× = 11.1；JPM 2028E 13.0）。规则要求 L / H 取同一分布两端，照印；**敏感行**：H 分子换 13.0（`k_eps_h` = 13.0 ÷ 10.47 × `k_eps_m` = 1.7072，其余不动）→ H **201.20**（2026-10-16 新口径；旧尺 214.51）；原稿「H 219」按任何写明的映射都无法复现，已按此构造替换。**证伪 / 重算触发**：下次拉共识若高端跌破 13.0 → 重算 H | active | yfinance 2026-09-21；Citi 98490；JPM 98441 | `eps_fy27e_high`；Outputs 敏感行 |
# | A10 | **折旧滞后 — 采用前瞻分子的前提**：当期分部利润只背已投产资产的折旧（H1 D&A 约 375 亿 vs capex 约 1,190 亿，3.2×）；采用 FY2027E 共识分子的前提是卖方模型已建 capex（JPM 2027E 3,650 亿）、对应折旧在其 EPS 里。**证伪触发器**：capex 指引不变或上调、而 FY27E 共识 EPS 被下修 >10% → 前提证伪，退回 trailing 分子；AWS 分部 margin 连续两季 <30% → 处置 | active | 10-Q 现金流量表；JPM 98441 | `k_eps_*` 前提；`aws_om_now` |
# | A11 | **资产腿口径**：投资组合毛额 2,297 亿（10-Q Item 3：Anthropic 可转债 979 + 私募股权（Anthropic 优先股 925 + OpenAI C 轮 287）1,223 + 认股权证 43 + 上市权益 47 + 权益法 4）；成本基础 `估算` 500 亿（Anthropic 180 + OpenAI 287 + 其他 ~30）；递延税按内含收益 × 23%；折价带 L 50% / M 30% / H 15%（Anthropic 已递表 IPO、标记 9,650 亿 H 轮；OpenAI 3 月轮 8,520 亿、无 IPO 计划）。上市权益证券从净现金剔出并入组合，避免双计 | active | 10-Q 2026-06-30 Note 3 / Item 3；news 299051289 / 299551341 | `port_gross` / `port_cost` / `dtl_rate` / `d_port_*` / `mkt_equity_sec` |
# | A12 | **挂载 `_AXIS.ai-capex.md`，身份构成方**：2026 capex 指引 2,200 亿美元（Q2 call，上调自 2,000 亿）在轴的基数里；L 档不得比轴 L 档（2027 仍 +32%）更悲观；2027E 卖方 3,650 亿（JPM） | active | Barclays 98451；JPM 98441 | `capex_guide` |
# | A13 | **无期权（V_opt = 0），FY2027 之后的第二段增长只走候选带**：管理层「AWS 至少翻倍」、「2027 年底产能翻倍」、大摩「每年 8GW、2034–35 年万亿营收」都描述的是 **AWS 这条已在底牌里的腿**在 FY2027 之后的增长，不是「当前算不出分子的业务」——按 valuation-rules「数据优先级与同业同尺」（2026-10-03），已有分子的腿的远期增长走盈利分子层：≥2 家共识 → \(g_1\)；公司指引 / 模型 / 单家 → 候选带；**不进 \(V_{opt}\)**（V_opt 只收算不出分子的业务，否则与 AWS 腿的永续增长双计）。「2027 年底产能翻倍」是可换算成收入的具名产能，但它换算出的是 AWS 2028 收入，属于候选带的同一年——候选带已由 JPM 2028E 占位（一行），产能换算法待 AWS 披露单位产能收入后可作交叉；大摩「每年 8GW、万亿营收」是卖方远期模型，非本票具名的量；2028 年 EPS 明确给数的只有 JPM 一家（13.0）→ 候选带（单家）。**升级门槛**：出现第二家明确的 FY2028E 点估计 → 按裁决顺序 ② 把 2028 当一年过渡 g₁ 进底牌、删候选带行 | active | JPM 98441；MS 101028（只给 2027/28 均值） | `eps_fy28e_single` / `r_disc`；`v_opt` |
# | A14 | **股本**：`shares_diluted` = 10,903M（Q2 2026 稀释加权）；未建模 SBC 未来稀释 | active | 10-Q 2026-06-30 | `shares_diluted` |
# | A15 | **自身实测带失真，护栏不适用**：Longbridge 5 年月度 trailing PE [20.33, 292.98]、p50 49.4——2022 亏损年分母塌缩；带失真时不得用来降篮或反推（valuation-rules ③「带有效性核验」）；本框架三档 15.9 / 21.2 / 30.4× 当期核心 EPS 只作读数 | active | Longbridge valuation --history 2026-09-21 | `pe_own_top` / `pe_own_p50`（只披露） |
# | A16 | **超额现金、增长期资金缺口与时点对齐**（valuation-rules「经营价值与超额现金」① / ③，框架纠正 2026-10-16）：扩展口径净现金 −106 亿（现金 + 债券类有价证券 − 长期债务；若计经营租赁与融资义务更负），没有超额现金，不单列；归母比例 1.0（少数股东可忽略）。**增长期资金缺口** = 2026 下半年资本开支约 1,010 亿（全年指引 2,200 亿 − 上半年约 1,190 亿）− (同期经营现金流约 905 亿 − 股权激励约 100 亿（非现金加回，不是可用现金）) = **205 亿 = 1.88/股**；投产时点：服务器当年上线、数据中心土建约 12–18 个月，产出落在分子年 FY2027 内，全额计；没有超额现金行，作类债项从股权价值里扣。有缺口时窗口可分配利润记 0（经营现金流已含窗口利润，不双计）；「视同派出」行（2.62 / 2.85 / 2.92，A8）只作披露。**时点对齐**：τ = 2026-06-30 → FY2027 年初 = **0.5 年**；AWS 非实验室子腿与零售腿 ÷ 1.1^0.5，实验室子腿按篮子对的过渡篮 15% ÷ 1.15^0.5；资产腿与闭合项不折。候选带的经营腿在 FY2028 年初，折 τ + 1 = 1.5 年。原框架无折回 | active | 10-Q 2026-06-30；Q2 2026 capex 指引；框架纠正试算 2026-10-16 | `tau`、`capex_2h26`、`ocf_2h26`、`sbc_2h26`；闭合项 |
# | A17 | **稳态回报三段**（valuation-rules「经营价值与超额现金」②）：可见年 FY2027 用前瞻回报 → 默认路径 **Y1 = 可见年末 2027**（云厂商不继承 `_AXIS.ai-capex` 的高回报期）→ 线性回落 → **Y2 2031**（零售进入门槛判「中」，回落 4 年：物流网络单位投资大、建设期长，偏高；Temu / Shein / TikTok Shop 几年内抢到可观份额，偏低；两头折中）。**零售腿**（2026-10-19 按序取 + 三档各取各的，用户认可）：自身周期按腿重建（分部经营利润 ÷ 年初零售净资本，FY2017–22 谷到谷 5.3%、剔分母近零的 FY2017 为 10.4%）缺口太多——分部资产靠检索汇总、Rivian 股权未剔、2019 年前租赁未上表，且 2023 年起区域化物流与广告让零售利润率台阶式上移——只作对照，用户裁定取同业层；旧「GAAP 净利 ÷ 权益与腿口径不同」的弃用理由撤。同生意成熟同业（近 5 个完整财年收入复合 ≤ 10%、不负增长），投入资本口径 FY2016–25 均值：WMT 13.8% / TGT 22.4% / KR 9.6% / DG 13.6% / HD 39.5%（旧账面 598% 作废）；COST 收入复合 10.5% 不满足成熟判据剔除，LOW 负增长剔除 → 纯零售中位 **13.8%**（同业投入资本口径已扣应付账款等经营负债，与零售腿净口径一致）。**同业须同一门生意 → 按利润拆成两门生意再混合（用户 2026-10-19 认可）**：零售腿利润里埋着广告（Q2 广告收入 198 亿 × 4 ≈ 790 亿/年），纯零售商没有这门近零边际成本的生意；公司不披露广告利润率，公开估计约 40%（Forbes 2025-01 引分析师 Russ Dieringer）到约 50%（IG 2026 二季报预览），取保守的 40% → 广告利润约 316 亿，占零售腿年化经营利润约 410 亿（H1 北美 174 + 国际 31）的 **77%**（50% 利润率时 96%）。广告取「边际成本近零」兜底 30%，纯零售取同业 13.8%，按同一增速下各自要留的钱加权（\(1/R = 0.77/30\% + 0.23/13.8\%\)，比按利润直接加权保守）→ **23.6%**；广告占比 50% 时 18.9%、≥ 96% 时封顶到 M 前瞻 28.6%（只作敏感性）。**L / M = 23.6%**（L 前瞻 23.7% / M 28.6% 都回落；旧值 13.8% 把广告当超市算）；**H = min(H 前瞻 41.3%, 30%) = 30%**——拆不出周期的腿，高档是区域化物流与广告带来的利润率提升守住的世界。**AWS 两子腿**：留存回报本就是卖方的边际稳态 ROIC 18.9%（A4，L 档 17.4%），不是峰值快照，路径平。g 不重解：AWS 截在上限，零售是自定。不属于商品腿豁免。**k**：「视同派出」行 k 三档本为 0；**k_lab 0.30 保留**——它是篮子对规则强制的显式到达折扣，乘在具名的实验室收入子腿上，不是乘在整个经营价值上 | active | 同业 SEC companyfacts（投入资本口径，`_local/tmp/round9/sweep/AMZN/`）2026-10-19；广告利润率：Forbes 2025-01-30「Big Retailers Find Big Profits Imitating Amazon's Ad Business」、IG 2026-07-28 亚马逊二季报预览（`_local/tmp/round10/amzn_hood/`）；汇丰 99586；框架纠正试算 2026-10-16 | `t0`、`y1`、`y2`、`ronic_ss_ret`、`ronic_ss_ret_h`；零售倍数 |
# Legacy correction history (not a new financial update):
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-10-03
# - 迁移（valuation-rules「数据优先级与同业同尺」「未建模期权」2026-10-03）：复核 A13「无期权」——旧理由「不是已实测轨迹」已废止；新理由：管理层翻倍 / 产能目标描述的是已在底牌的 AWS 腿的远期增长，按数据优先级走候选带而非 \(V_{opt}\)。锚点、Inputs、eval 不变（L/M/H 128.73 / 170.94 / 247.56，\(V_{opt}\) 0，候选带不变）。
HISTORICAL_PARTIAL_FINGERPRINT = 'c8a3d7c9e20ad06b71ae889c79804659f6ea8bacfaf84d381bfb261e288b3791'

INPUTS = {
    # 稀释加权股数（百万）（A14）; 来源：10-Q 2026-06-30
    'shares_diluted': 10903,
    # 正常化税率 = FY2025 有效税率（A3）; 来源：10-K 2025
    'tax_rate': 0.196,
    # 北美 H1 2026 分部经营利润（$M）; 来源：10-Q Note 8
    'oi_na_h1': 17390,
    # 国际 H1 2026 分部经营利润（$M）; 来源：10-Q Note 8
    'oi_intl_h1': 3141,
    # AWS H1 2026 分部经营利润（$M）；Q2 单季 16,621、margin 39.4%; 来源：10-Q Note 8
    'oi_aws_h1': 30782,
    # AWS H1 2026 收入（$M）；H1 margin 38.6% = `aws_om_now` 的来源; 来源：10-Q Note 8
    'rev_aws_h1': 79819,
    # H1 净利息收入（$M）= 利息收入 2,430 − 利息支出 2,114；只进当期核心 EPS（桥的分母）; 来源：10-Q
    'net_interest_h1': 316,
    # AWS 非实验室子腿与零售腿的永续折现率 = **篮 4 龙头制造** 10%（A6）；值 = `gordon.BASKET_R`; 来源：2026-09-22
    'r_perp': 0.10,
    # AWS 实验室子腿**过渡篮** = **篮 7 单押 / 国别 / 故事** 15%（今天收入依赖对手方未落定融资，A6）；本腿为单段 Gordon，过渡篮无算术作用点，只记录今天的性质、定 \(G_{cap}\)、作合篮回退目标; 来源：2026-09-23
    'r_aws_lab': 0.15,
    # AWS 实验室子腿**终值篮** = **篮 4 龙头制造** 10%：实验室做成了的世界里 OpenAI / Anthropic 是用自身收入付账的超大客户，与非实验室 AWS 客户同类（`_AXIS.frontier-lab-funding` §3）；稳态按此资本化；A6; 来源：2026-09-23
    'r_aws_lab_t': 0.10,
    # 实验室子腿确定性等价折扣 = `_AXIS.frontier-lab-funding` §3b 共用值（eval 跨文件校验）；单段估值下承担**全部**到达风险；只乘实验室子腿；A6; 来源：2026-09-23
    # 集团经营投入资本 IC0（$M，2026-06-30）= 总资产 1,095,689 − 流动负债 241,274 − 现金 78,213 − 有价证券 44,775 − 非上市投资 224,895; 来源：10-Q
    'ic_group': 506532,
    # AWS 分部资产（$M，2026-06-30 期末）= AWS 腿 IC0；零售腿 IC0 = `ic_group` − 本项 = 156,362（净口径，属性 C）; 来源：10-Q Note 8
    'ic_aws': 350170,
    # **AWS 新投资本的边际稳态 ROIC**（A4）= 汇丰 2027E AWS ROIC；进两条 AWS 子腿的留存项 b = g/ROIC；L 档随利润率退坡同比例缩; 来源：Wisburg 99586
    'roic_marg_aws': 0.189,
    # OpenAI + Anthropic 占 FY2027E AWS 收入 / 利润的份额 `估算`（A6）；15% / 48% 敏感行; 来源：2026-09-22
    'share_lab_aws': 0.20,
    # AWS 两子腿永续增速，三档共用（A7）；= \(G_{cap}\)（按过渡篮 7 与篮 4 取的 cap 均为 6%）; 来源：2026-09-22
    'g2_aws': 0.06,
    # 零售腿永续增速，三档共用；无同业锚·自定（A7）; 来源：2026-09-22
    'g2_ret': 0.04,
    # L 档分子缩放系数 = 1.37503 × (8.69 / 10.47)（A2）；eval 强制与共识区间一致; 来源：yfinance 2026-09-21
    'k_eps_l': 1.14126,
    # M 档分子缩放系数 = FY2027E 共识均值 10.47 ÷ 当期核心 EPS 7.6144; 来源：yfinance 2026-09-21
    'k_eps_m': 1.37503,
    # H 档分子缩放系数 = 1.37503 × (15.04 / 10.47)（A2 / A9）; 来源：yfinance 2026-09-21
    'k_eps_h': 1.97519,
    # FY2027E 稀释 EPS 共识低端（52 家）；一致性校验，不入公式; 来源：yfinance 2026-09-21
    'eps_fy27e_low': 8.69,
    # FY2027E 共识均值；校验分母; 来源：yfinance 2026-09-21
    'eps_fy27e_consensus': 10.47,
    # FY2027E 共识高端（A9：疑含标记收益）; 来源：yfinance 2026-09-21
    'eps_fy27e_high': 15.04,
    # L 档 AWS 分部 OI margin = FY2025 实测（45,606 / 128,725）（A5）; 来源：10-K 2025
    'aws_om_l': 0.35429,
    # 当期 AWS 分部 OI margin（H1 2026：30,782 / 79,819）；A5 的分母; 来源：10-Q Note 8
    'aws_om_now': 0.38565,
    # 现金及现金等价物（$M）; 来源：10-Q 2026-06-30
    'cash': 78213,
    # 有价证券（$M），含下行的上市权益证券; 来源：10-Q 2026-06-30
    'mkt_sec': 44775,
    # 有价证券中的上市权益证券（$M，Level 1 + 2）；从闭合项剔出、已在 `port_gross` 内（A11）; 来源：10-Q Note 3
    'mkt_equity_sec': 4687,
    # 长期债务（$M）；2025-12-31 为 65,648; 来源：10-Q 2026-06-30
    'lt_debt': 128894,
    # 投资组合毛额（$M）：权益 / 认股权证 / 可转债合计（A11）; 来源：10-Q Item 3
    'port_gross': 229700,
    # 组合成本基础 `估算`（$M）（A11）; 来源：2026-09-22
    'port_cost': 50000,
    # 组合内含收益的递延税率（A11）; 来源：2026-09-22
    'dtl_rate': 0.23,
    # 组合 L 档折价：私募标记回撤 + Anthropic IPO 失败情景; 来源：2026-09-22
    'd_port_l': 0.50,
    # 中档折价：Anthropic 已递表、OpenAI 无 IPO 计划; 来源：2026-09-22
    'd_port_m': 0.30,
    # 上档折价：仅留流动性折价; 来源：2026-09-22
    'd_port_h': 0.15,
    # 近 3 年现金派息率（不派息）；只进「视同派出」披露行（A8）; 来源：10-K 2023–2025
    'payout_3y': 0,
    # L 档「视同派出现金」打折 k（A8，来源 ①）; 来源：2026-09-22
    'k_l': 0,
    # M 档 k（A8）; 来源：2026-09-22
    'k_m': 0,
    # H 档 k（A8；H/M 差不来自价格轴，①b 不适用）; 来源：2026-09-22
    'k_h': 0,
    # 自身 5 年月度 trailing PE 实测顶；**带失真，只披露**（A15）; 来源：Longbridge 2026-09-21
    'pe_own_top': 292.98,
    # 同一序列中位；只披露（A15）; 来源：Longbridge 2026-09-21
    'pe_own_p50': 49.43,
    # 2026 全年 capex 指引 USD；`_AXIS.ai-capex.md` 构成方（A12）; 来源：Q2 2026 call
    'capex_guide': 2.2e11,
    # 杠杆门读数（A8）; 来源：10-Q / 10-K 2025
    'net_debt_ebitda': 0.78,
    # 杠杆门读数（A8）; 来源：10-K 2025
    'interest_ebit': 0.029,
    # JPM FY2028E GAAP EPS（单家）；只进候选带（A13）; 来源：JPM 98441（2026-07-31）
    'eps_fy28e_single': 13.0,
    # 候选带折现率（FY2028 = 当前财年 +2，折一年）；只作披露的折现读数，不是篮子 r; 来源：2026-09-22
    'r_disc': 0.10,
    # 无期权（A13）; 来源：2026-09-22
    'v_opt': 0,
    # 时点对齐：估值基准日 2026-06-30（10-Q 资产负债表日）→ 分子年 FY2027 年初 2027-01-01 的年数；AWS 非实验室与零售按 `r_perp` 折、实验室子腿按过渡篮 `r_aws_lab` 折（A16）; 来源：2026-06-30
    'tau': 0.5,
    # 回报路径第 1 年 = 分子年 FY2027（A17）; 来源：2026-10-16
    't0': 2027,
    # 高回报期止点 = 可见年末（默认路径，云厂商不继承 `_AXIS.ai-capex`；A17）; 来源：2026-10-16
    'y1': 2027,
    # 稳态起点 = 可见年末 + 4（零售进入门槛「中」；A17）; 来源：2026-10-16
    'y2': 2031,
    # 零售腿 L / M 档稳态回报 = 广告与纯零售按留存需要混合：广告（估计占零售腿经营利润 77%，广告利润率取公开估计下沿 40%）取边际成本近零兜底 30%，纯零售取成熟零售同业投入资本口径 FY2016–25 均值的中位 13.8%（WMT 13.8 / TGT 22.4 / KR 9.6 / DG 13.6 / HD 39.5%）→ \(1/(0.77/0.30+0.23/0.138)\) = 23.6%（用户 2026-10-19 认可）；每档不超过该档前瞻（A17）; 来源：2026-10-19
    'ronic_ss_ret': 0.236,
    # 零售腿 H 档稳态回报 = min(H 前瞻 41.3%, 30%)（「三档各取各的稳态」：拆不出周期的腿，区域化物流与广告带来的利润率提升守住的世界；A17）; 来源：2026-10-19
    'ronic_ss_ret_h': 0.30,
    # 2026 下半年资本开支（$M）= 全年指引 2,200 亿 − 上半年约 1,190 亿（A16）; 来源：Q2 2026 call
    'capex_2h26': 101000,
    # 2026 下半年经营现金流估计（$M），由共识利润与近年经营现金流 ÷ 净利推（A16）; 来源：2026-10-16
    'ocf_2h26': 90500,
    # 2026 下半年股权激励（$M，经营现金流里的非现金加回，不是可用现金）（A16）; 来源：2026-06-30
    'sbc_2h26': 10000,
}
# Baskets are stable numeric declarations, not source-text parsing.
BASKETS = {"r_perp": 4, "r_aws_lab": 7, "r_aws_lab_t": 4}
REQUIRED = frozenset(INPUTS) | {'k_lab'}

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on next-period earnings with the three-stage return path
    (valuation-rules「经营价值与超额现金」② 稳态回报三段).

    Year t = 1 is calendar t0.  The retention of calendar c earns the forward return
    while c <= y1, fades linearly to the stable return by y2, and the stable return
    from y2 on.  Stable return capped at the forward return and floored at r; a flat
    path equals `perpetual_pe`.
    """
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    rs = min(roe, max(rs, r))

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
            return pv + e * payout(g, rs) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1



def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    missing = REQUIRED - inp.keys()
    if missing:
        raise ValueError(f"missing inputs: {sorted(missing)}")
    require_whole_years(inp, ('t0', 'y1', 'y2'))
    baskets = BASKETS
    errors: list[str] = []

    # --- r is a basket, not a dial (valuation-rules「§r 篮子」)
    r4, r7, r7t = inp["r_perp"], inp["r_aws_lab"], inp["r_aws_lab_t"]
    for field, r in (("r_perp", r4), ("r_aws_lab", r7), ("r_aws_lab_t", r7t)):
        if field not in baskets:
            errors.append(f"{field}: basket missing")
        errors += check_r(r, field, baskets.get(field))
    # The lab sub-leg is a basket PAIR (valuation-rules「篮子对」): 篮 7 is what the
    # customer is today, 篮 4 what it is if it makes it.  Every leg here is
    # single-stage, so the journey rate has no exponent to act in -- the steady
    # state capitalises at the terminal rate and the shared k_lab carries all of
    # the arrival risk (_AXIS.frontier-lab-funding §3).
    errors += check_basket_pair(r7, r7t, "lab", baskets.get("r_aws_lab"), baskets.get("r_aws_lab_t"))
    errors += check_k_declared(r7, r7t, (inp["k_lab"],) * 3, "k_lab")
    for field, g, r in (("g2_aws", inp["g2_aws"], r4), ("g2_ret", inp["g2_ret"], r4), ("g2_aws@lab", inp["g2_aws"], r7)):
        errors += check_g_cap(g, r, field)
        if r - g < MIN_R_MINUS_G:
            errors.append(f"{field}: r - g = {r - g:.2%} < {MIN_R_MINUS_G:.0%}")

    # --- tier ladder must be the consensus range itself (A2e-2a)
    if not (inp["k_eps_l"] < inp["k_eps_m"] < inp["k_eps_h"]):
        errors.append("k_eps_* ladder not increasing")
    mean = inp["eps_fy27e_consensus"]
    for tier, endpoint in (("l", "eps_fy27e_low"), ("h", "eps_fy27e_high")):
        want, got = inp[endpoint] / mean, inp[f"k_eps_{tier}"] / inp["k_eps_m"]
        if abs(got - want) > K_LADDER_TOL:
            errors.append(f"k_eps_{tier}/k_eps_m = {got:.5f} != {endpoint}/consensus = {want:.5f}")
    if not (1.0 >= inp["d_port_l"] > inp["d_port_m"] > inp["d_port_h"] >= 0.0):
        errors.append("d_port_* must be a decreasing band inside [0,1]")
    if not (0.0 <= inp["k_l"] <= 1.0 and 0.0 <= inp["k_m"] <= 1.0 and 0.0 <= inp["k_h"] <= 1.0):
        errors.append("k_* haircut outside [0,1]")
    if not (0.0 < inp["share_lab_aws"] < 1.0):
        errors.append("share_lab_aws outside (0,1)")
    seg_sum = inp["oi_na_h1"] + inp["oi_intl_h1"] + inp["oi_aws_h1"]
    if abs(seg_sum - H1_TOTAL_OPERATING_INCOME) > 1.0:
        errors.append(f"segment identity: {seg_sum:.0f} != H1 operating income {H1_TOTAL_OPERATING_INCOME:.0f}")
    if inp["net_debt_ebitda"] > 3.0 or inp["interest_ebit"] > 1.0 / 3.0:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition (valuation-rules「杠杆门」)")

    # --- Step 1: trailing base (H1 x2, normalised tax)
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_diluted"]
    nopat_aws = inp["oi_aws_h1"] * 2 * keep
    nopat_ret = (inp["oi_na_h1"] + inp["oi_intl_h1"]) * 2 * keep
    core_eps = (nopat_aws + nopat_ret + inp["net_interest_h1"] * 2 * keep) / sh
    ic_ret = inp["ic_group"] - inp["ic_aws"]
    aws_retreat = inp["aws_om_l"] / inp["aws_om_now"]

    # --- Step 4: asset legs
    net_cash = inp["cash"] + (inp["mkt_sec"] - inp["mkt_equity_sec"]) - inp["lt_debt"]
    port_net = inp["port_gross"] - (inp["port_gross"] - inp["port_cost"]) * inp["dtl_rate"]

    def roe_open(e: float, ic0: float, g: float, unbooked: float) -> float:
        if g * unbooked / e >= 1.0:
            raise ValueError("opening-capital roll diverges")
        return e / (ic0 / (1.0 - g * unbooked / e))

    t0, y1, y2, tau = int(inp["t0"]), int(inp["y1"]), int(inp["y2"]), inp["tau"]
    # ① growth-period funding gap: 2H26 capex beyond 2H26 OCF net of SBC (debt-like, parent 1.0)
    gap_ps = max(inp["capex_2h26"] - (inp["ocf_2h26"] - inp["sbc_2h26"]), 0.0) / sh

    def tier(t: str, k: float, ic_scale: float = 1.0, roic_marg: float | None = None,
             share_lab: float | None = None, r_lab: float | None = None, k_lab: float | None = None,
             g_aws: float | None = None, g_ret: float | None = None, flat: dict | None = None,
             retreat: bool = True, r_lab_tau: float | None = None, disc_years: float | None = None,
             rs_ret: float | None = None) -> dict:
        roic_marg = inp["roic_marg_aws"] if roic_marg is None else roic_marg
        share_lab = inp["share_lab_aws"] if share_lab is None else share_lab
        r_lab = r7t if r_lab is None else r_lab
        r_lab_tau = r7 if r_lab_tau is None else r_lab_tau
        k_lab = inp["k_lab"] if k_lab is None else k_lab
        g_aws = inp["g2_aws"] if g_aws is None else g_aws
        g_ret = inp["g2_ret"] if g_ret is None else g_ret
        # Steady return per tier (retention「三档各取各的稳态」): L / M = mature-retail peers, H = min(H forward, 30%).
        if rs_ret is None:
            rs_ret = inp["ronic_ss_ret_h"] if t == "h" else inp["ronic_ss_ret"]
        dy = tau if disc_years is None else disc_years
        scale = aws_retreat if (t == "l" and retreat) else 1.0
        n_aws = nopat_aws * scale
        out: dict = {}
        legs = (
            ("aws", n_aws * (1 - share_lab), inp["ic_aws"] * ic_scale * (1 - share_lab), g_aws, r4, roic_marg * scale, r4),
            ("lab", n_aws * share_lab, inp["ic_aws"] * ic_scale * share_lab, g_aws, r_lab, roic_marg * scale, r_lab_tau),
            ("ret", nopat_ret, ic_ret * ic_scale, g_ret, r4, None, r4),
        )
        for name, n, ic, g, r, rm, r_tau in legs:
            e, unb = n * k, n / 2.0                      # unbooked 2H26
            roe_avg = roe_open(e, ic, g, unb)
            roe_ret = roe_avg if rm is None else rm      # A4: cloud retains at the marginal ROIC
            # ② AWS retains at the marginal steady-state ROIC already -> flat path;
            # retail fades to the mature-retail through-cycle return.
            rs = rs_ret if name == "ret" else roe_ret
            pe = path_pe(g, roe_ret, r, t0, y1, y2, rs) if flat is None else flat[name]
            # k_lab leaves the lab sub-leg's value only, never its multiple (axis §3b).
            haircut = (1.0 - k_lab) if name == "lab" else 1.0
            out[name] = dict(e=e, roe=roe_avg, roe_ret=roe_ret, pe=pe, b1=g / roe_ret, unb=unb,
                             rs=min(roe_ret, max(rs, r)),
                             val=e * pe * haircut / sh / (1 + r_tau) ** dy)
        d = inp[f"d_port_{t}"]
        out["port"] = dict(val=port_net * (1 - d) / sh, d=d)
        out["cash"] = dict(val=net_cash / sh)
        out["gap"] = dict(val=-gap_ps)
        # With a funding gap the window's distributable profit is booked as 0 (OCF carries it);
        # the deemed-distributed row is a disclosure only (k = 0).
        deemed = sum(max(1 - inp["payout_3y"] - out[n]["b1"], 0.0) * out[n]["unb"] for n in ("aws", "lab", "ret")) / sh
        pre = sum(v["val"] for v in out.values())
        out["deemed"], out["pre"] = deemed, pre
        out["total"] = pre - inp[f"k_{t}"] * deemed
        return out

    def band(**kw) -> dict:
        return {t: tier(t, inp[f"k_eps_{t}"], **kw) for t in "lmh"}

    base = band()
    L, M, H = (base[t]["total"] for t in "lmh")
    if not (L < M < H):
        raise ValueError(f"L<M<H violated: {L}, {M}, {H}")
    A, B = cut_points(L, M, H)

    for t in "lmh":
        for name in ("aws", "lab", "ret"):
            b1 = base[t][name]["b1"]
            if not (0.0 < b1 < 1.0):
                errors.append(f"{name} {t}: b1 = g/ROE = {b1:.3f} outside (0,1)")
        if base[t]["ret"]["roe"] > MAX_LEG_ROE:
            errors.append(f"retail {t}: derived ROE {base[t]['ret']['roe']:.1%} > {MAX_LEG_ROE:.0%} — capital allocation artefact")
        # Per dollar of earnings the lab sub-leg must never be worth more than the
        # non-lab one: same terminal basket, so the haircut is what keeps it below.
        if base[t]["lab"]["pe"] * (1.0 - inp["k_lab"]) > base[t]["aws"]["pe"] + 1e-9:
            errors.append(f"tier {t}: lab sub-leg after k_lab out-values the non-lab sub-leg per unit of earnings")

    # A2e-2c: every tier at the M multiples — the ladder must still stand
    flat = {n: base["m"][n]["pe"] for n in ("aws", "lab", "ret")}
    fb = band(flat=flat)
    flat_l, flat_h = fb["l"]["total"], fb["h"]["total"]
    if not (flat_l < M < flat_h):
        raise ValueError(f"flat-multiple ladder collapsed: {flat_l:.2f}/{M:.2f}/{flat_h:.2f}")

    # Candidate band: single-house FY2028E point estimate swapped into the M
    # numerator, tier ratios kept; the operating legs sit at the FY2028 opening and
    # are discounted tau + 1 years at r_disc; asset legs and gap undiscounted.
    kk = {t: inp["eps_fy28e_single"] / core_eps * (inp[f"k_eps_{t}"] / inp["k_eps_m"]) for t in "lmh"}
    cand = {}
    for t in "lmh":
        c = tier(t, kk[t], disc_years=0.0)
        op = c["aws"]["val"] + c["lab"]["val"] + c["ret"]["val"]
        cand[t] = op / (1 + inp["r_disc"]) ** (tau + 1) + c["port"]["val"] + c["cash"]["val"] + c["gap"]["val"]
    if not cand["l"] < cand["m"] < cand["h"]:
        raise ValueError("candidate ladder collapsed")


    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0: no consensus-referenced option anchor")
    sens = [
        ("AWS marginal ROIC 16.4% (own realised avg-asset basis)", dict(roic_marg=0.164)),
        ("AWS marginal ROIC 13% (realised first-year lower bound)", dict(roic_marg=0.13)),
        ("lab share 48% (= RPO share)", dict(share_lab=0.48)),
        ("lab share 15% (= AI ARR share today)", dict(share_lab=0.15)),
        ("k_lab = 0 (no arrival haircut)", dict(k_lab=0.0)),
        ("single-basket lab (篮 7 15%, no k — the pre-pair ruler)", dict(r_lab=r7, k_lab=0.0)),
        ("g2_aws −1pp", dict(g_aws=inp["g2_aws"] - 0.01)),
        ("g2_ret −1pp", dict(g_ret=inp["g2_ret"] - 0.01)),
        ("g2_ret +1pp", dict(g_ret=inp["g2_ret"] + 0.01)),
        ("no AWS margin retreat in L", dict(retreat=False)),
    ] + [(f"opening IC x{s:.1f} (A4 待补 capital path)", dict(ic_scale=s)) for s in IC_SENSITIVITY]

    scenario_ids = (
        "aws_roic_164", "aws_roic_130", "lab_share_48", "lab_share_15",
        "lab_haircut_zero", "lab_single_basket", "aws_growth_down",
        "retail_growth_down", "retail_growth_up", "no_aws_retreat",
        "opening_capital_120", "opening_capital_140",
    )
    scenarios = {name: band(**kw) for name, (_, kw) in zip(scenario_ids, sens)}
    stable_off = band(rs_ret=1.0)
    # Legacy narrative-only comparisons: high EPS 13.0, and retail mature
    # returns using pure retail peers or a 50% advertising profit share.
    # The old document gave two different high-EPS results; compute from its
    # stated scaling and leave that discrepancy for review.
    high_eps_13 = tier("h", 13.0 / inp["eps_fy27e_consensus"] * inp["k_eps_m"])["total"]
    retail_peer = band(rs_ret=0.138)
    retail_advertising_50 = band(rs_ret=0.189)
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r4
        saved = r4
        r4 = r4 + dr
        try:
            b = band(r_lab=r7t + dr, r_lab_tau=r7 + dr)
            return b["l"]["total"], b["m"]["total"], b["h"]["total"]
        finally:
            r4 = saved

    if errors:
        raise ValueError("; ".join(errors))

    def band_values(values):
        return {t.upper(): values[t]["total"] for t in "lmh"}

    result = {
        "ticker": "AMZN.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-06-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of': '2026-10-19',
        "anchors": band_values(base),
        "candidate": {"label": "JPM FY2028E 单家预测", "anchors": {t.upper(): cand[t] for t in "lmh"}},
        "option": None,
        "cut_points": {"A": A, "B": B}, "base_detail": base,
        "flat": [flat_l, M, flat_h], "stable_return_off": stable_off,
        "sensitivity": scenarios,
        "narrative_sensitivity": {"high_eps_13": high_eps_13,
                                  "retail_peer": band_values(retail_peer),
                                  "retail_advertising_50": band_values(retail_advertising_50)},
        "parameters": {"discount": {"aws": r4, "lab_terminal": r7t, "lab_journey": r7, "retail": r4},
                       "growth": {"aws": inp["g2_aws"], "retail": inp["g2_ret"]},
                       "return_path": {t: {leg: {"forward": base[t][leg]["roe_ret"], "stable": base[t][leg]["rs"]}
                                           for leg in ("aws", "lab", "ret")} for t in "lmh"}}
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if min(r4 + dr, r7t + dr) <= max(inp[k] for k in ('g2_aws', 'g2_ret')):
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': r4, 'r_aws_lab_t': r7t}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    lab, capex = context['axes']['lab'], context['axes']['capex']
    if not lab.get('uses_shared_haircut') or capex.get('role') != 'constituent':
        raise ValueError('shared frontier-lab and AI capital roles are required')
    shared = {'k_lab': lab['k_lab']}
    result = evaluate({**INPUTS, **shared}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'shared': shared, 'capex': {'role': capex['role'], 'base_2026_usd': capex['base_2026_usd']},
         'baskets': BASKETS, 'minimum_rate_gap': MIN_R_MINUS_G, 'ladder_tolerance': K_LADDER_TOL,
         'ic_sensitivity': IC_SENSITIVITY, 'max_leg_roe': MAX_LEG_ROE, 'h1_operating_income': H1_TOTAL_OPERATING_INCOME}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    base = result['base_detail']
    result['segments'] = {name: {'unit': 'USD_PER_SHARE',
                                 'values': {t.upper(): base[t][name]['val'] for t in 'lmh'}}
                          for name in ('aws', 'lab', 'ret', 'port', 'cash', 'gap')}
    result['segments']['distribution_adjustment'] = {'unit': 'USD_PER_SHARE',
        'values': {t.upper(): -INPUTS[f'k_{t}'] * base[t]['deemed'] for t in 'lmh'}}
    parameters = result['parameters']
    growth_names, discount_names = {'aws': 'g2_aws', 'lab': 'g2_aws', 'ret': 'g2_ret'}, {'aws': 'aws', 'lab': 'lab_terminal', 'ret': 'retail'}
    result['key_parameters'] = {}
    for leg in growth_names:
        result['key_parameters'][leg] = {
            'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'][discount_names[leg]])},
            'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS[growth_names[leg]])},
            'forward_return': {'unit': 'RATIO', 'values': {t.upper(): parameters['return_path'][t][leg]['forward'] for t in 'lmh'}},
            'steady_return': {'unit': 'RATIO', 'values': {t.upper(): parameters['return_path'][t][leg]['stable'] for t in 'lmh'}},
        }
    result['review_flags'] = ['historical_lab_funding_discount_estimated',
                              'historical_cloud_invested_capital_path_unverified',
                              'historical_forecasts_and_asset_values_unverified']
    return result
