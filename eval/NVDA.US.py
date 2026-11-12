#!/usr/bin/env python3
"""NVDA legacy valuation; this migration does not update inputs or judgments.

Money and shares are absolute USD and absolute counts unless otherwise noted.
All forward revenue, margins and the China option are original conditional estimates.
"""
from __future__ import annotations
import math
from lib.gordon import MEGA_HW_REVENUE_USD, check_g_cap, check_r, g_cap, perpetual_pe
from lib.inputs import require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.tiers import flat_multiple_ladder

DEPENDENCIES={'libraries':('gordon','inputs','partial_basis','rf_report','tiers'),
              'axes':{'cowos':'cowos_capacity'}}
HISTORICAL_PARTIAL_FINGERPRINT='61cc02ba06ec998a800c27ec30179e33cbf18e6f7d3a633954d46a9568406c01'

FORMULA_ID = "nvda_fy28_scenario_rev_gm_gordon_v3"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
BRIDGE_TOL = 0.15
NUM_YEAR = 2028
B = 1e9
OPTION_FRACTIONS = (0.0, 0.25, 1.0)
# | A1 | 林奇主类 = `fast_grower`、次类 = `cyclical`。**判据（可证伪）**：即便在 L 消化档，FY2028 同口径运营 EPS **7.70 仍比 FY2026 实际 4.41 高 74%**——「谷底」高于上一个峰值 74% 是成长股的减速年，不是林奇意义上的周期底；故 cyclical 只作次类，用于解释倍数而非趋势。**若某一年同口径 EPS 实际低于前一年，本条降级为 `weakened` 并考虑主次互换** | active | FY2026 10-K（OP $1,303.87 亿 / 稀释股本 245.14 亿）；§3 桥 | 分类与倍数逻辑 |
# | A2 | FY2028 收入 base = **$6,735 亿**（共识均值，56 家）；区间 **$4,164–7,785 亿**。**离散度本身是本票最大的事实**：上下沿差 1.87 倍，任何单点收入预测都不可信，故用三情景而非点估计 | active | yfinance 分析师区间 2026-09-06；对照 FY2027E $4,113 亿 | `rev_m`；三档结构 |
# | A3 | FY2028 收入 H 档 = **$7,785 亿**（分析师区间**上沿**，56 家，与 `rev_l` 取自同一区间）。**改用上沿而非公司指引**：指引 $6,990 亿（= FY27 $4,113 亿 × +70%）公司明示为「**受供应限制、非需求限制**」——那是供给上限，不是需求上限，用它当 H 会让 H 的分子只比 M 高 3.8%，H 档随即只剩倍数扩张（见 A11）。公司指引改作**档内坐标**：$6,990 亿在同一套 Gordon 倍数下 = **257.99**，落在 M 与 H 之间 | active | 分析师区间 yfinance 2026-09-06；指引 FY27Q2 法说（Wisburg 103107） | `rev_h` |
# | A4 | FY2028 收入 L 档 = **$4,164 亿**（分析师区间下沿，56 家，≈ 与 FY2027 持平、零增长）。**锚点值本身有来源；命名机制按 `_AXIS.cowos-capacity.md` 分解为两条**：① **CoWoS 配额落 α 状态**——NVDA 承担全部 29.4 万片缺口，配额 108.9 万 → **92.8 万片（−14.75%）**，轴内收入 $343.8B → **$293.1B**；② **轴外 ACIE 收缩至 $74.2B**（较 M 档 $280.6B **−73.5%**），方向与 A13 证伪触发器一致但**未达**其「ACIE 全额剔除」的极端。**②是本档最弱的一环**：ACIE 当期同比 +138%，−73.5% 无任何卖方口径支持，属**框架自有判断**，靠 A13 触发器监控。**MUST NOT 再用「capex 增速失速」解释本档**——2027 capex 在全部卖方口径下仍是 +32%~+63% 的高增长（`_AXIS.ai-capex.md` 三档），capex 失速已不是可用机制 | active | 锚点：yfinance 分析师区间 2026-09-06；配额：大摩 103203（经 `_AXIS.cowos-capacity.md`）；ACIE 结构：FY27Q2 法说 + 巴克莱 102970 | `rev_l`；轴内/轴外拆分见 §3 |
# | A5 | FY2028 non-GAAP 毛利率 base = **72.5%**（公司电话会：Q4FY27 触底 71–72%、FY2028 稳定 **72–73%**，因内存/HBM 成本通胀，长期 75% 目标下修）；H 档取指引上沿 **73%** | active | 103107；Q3FY27 指引 74.0%±50bp（8-K 新闻稿）；FY27Q2 实际 GAAP 与 non-GAAP 同为 75.0% | `gm_m`、`gm_h` |
# | A6 | FY2028 毛利率 L 档 = **65%**。**机制不是成本而是定价与计提**：需求转弱 → 采购承诺转为超额库存计提 + ASIC/AMD 价格竞争。**历史标定**：NVDA 上一次真周期底 FY2023 毛利率 **56.9%**（前一年 64.9%）；FY2026 因 H20 计提 $45 亿使全年 GM 由 75.0% 降至 **71.1%**（计提对 GM 净影响 −2.6pt，1H FY26 单期 −5.9pt）。65% 落在「FY2026 已发生的 71.1%」与「FY2023 真周期底 56.9%」之间，**比上一次实际发生的还温和** | active | FY2026 10-K；10-Q Note 7 计提表；FY2023 三表（收入 $269.74 亿 / COGS $116.18 亿） | `gm_l` |
# | A7 | FY2028 non-GAAP opex = **$480 亿**，**三档共用**。FY2027 non-GAAP opex ≈ $345 亿（1H 实际 $156.81 亿 + Q3 指引 $90 亿 + Q4 外推），FY2028 按 **+39.1%** 推。共用一个 opex 是刻意的：**消化年费用不会同步收缩，经营杠杆反向正是 L 档 OM 掉到 53.5% 的原因**。**口径诚实声明**：FY2027 基数一手可考，**FY2028 的 +39.1% 没有任何一手披露背书，是外推**。对照重述后（含 SBC）口径 FY2026 non-GAAP opex **$228.19 亿** → FY2027 $345 亿是 **+51.2%**，故 FY2028 的 +39.1% 是**减速**，方向合理。**可证伪护栏（已写进 eval）**：`opex_fy27 < opex_fy28 ≤ opex_fy27 × (1 + 51.2%)`，即 opex_fy28 必须落在 **$345–521 亿**——旧版这个字段在 eval 里完全自由（仅受 ±15% 共识桥间接约束，可取值域约 $0–1,084 亿） | active | 8-K Ex-99.1 FY2026 汇总（GAAP opex 230.76 − 收购 2.04 − 其他 0.53 = 228.19 亿）；Q3FY27 opex 指引 GAAP/non-GAAP $92/$90 亿 | `opex_fy28`、`opex_fy26`（仅护栏基数） |
# | A8 | 税率 **17%**（公司 FY2027 全年 GAAP 与 non-GAAP 指引均为 **16–18%**，不含离散项；FY27Q2 non-GAAP 实际 16.0%、GAAP 16.5%） | active | 8-K 新闻稿；10-Q | `tax_rate` |
# | A9 | FY2028 平均稀释股本 = **240.0 亿**。FY27Q2 实际 242.85 亿，两个季度净退役 1.47 亿（−0.6%/半年）；1H FY27 回购 2.03 亿股 / $398 亿，剩余授权 **$993 亿**（2026-05 新增 $800 亿）。按当前节奏外推至 FY2028 中点 | active | 10-Q 权益表与回购披露 | `shares_fy28` |
# | A10 | **分子口径**：MUST 用公司 non-GAAP。FY27Q1 起公司非 GAAP **不再剔除 SBC**（历史已重述），但仍剔股权投资损益；故 FY27Q2 GAAP 2.46 > non-GAAP 2.22，差额为 **$78 亿投资净收益**。**GAAP EPS MUST NOT 进主尺** | confirmed | 8-K 新闻稿非 GAAP 对账原文；10-Q 其他收入净额 1H $241.40 亿 | 全部 `eps_i` |
# | A11 | **倍数由 Gordon 生成，不取卖方目标价倍数**：\(PE_x = \mathtt{perpetual\_pe}(g_2, ROE_x, r)\)，g2 三档共用（A18）、r 由归篮给出 = 篮 4 龙头制造 10%（A23）、\(ROE_x = eps_x / BPS_{FY28 年初,x}\)（FY27Q2 权益 $2,289.8 亿 = 9.54 美元/股，按 \(b_1=g_2/ROE\) 滚过 2H FY27 未入账利润到 FY2028 年初 = 9.81 / 9.68 / 9.65，A24）= 79% / 157% / 186%。域判定：ROE_x − r ≫ +3pp → 三档皆在单调区，留存分支唯一解；ROE ≫ r 使派息率 0.95–0.98，倍数几乎只由 r − g 决定、对 ROE 不敏感，三档倍数 **15.82 / 16.24 / 16.31** 几乎相同——**次类 `cyclical` 的 flat 政策由机械结果兑现**：峰值盈利不配更高倍数，L 与 H 的差别仍全在分子（倍数比 0.97 / 1.00）。旧版 20× 借自 JPM/MS 目标价倍数，按 A2e-2b 属市场判断，已撤；街头 FY 口径倍数簇 20–25× 与 5 年前瞻均值 21× 只进护栏与交叉。**结构验证不变**：flat 阶梯 125.1 / 247.3 / 292.3 成立 | active | AGENTS.md「永续增长口径」；10-Q 权益；HSBC 103035 / JPM 103029 / MS 103176（只作交叉） | `equity`、`r_perp`、`g2` |
# | A12 | **客户集中度极高且仍在集中**。直接客户：FY27Q2 **一家占收入 16%**；1H FY27 **三家占 16%/15%/13%（合计 44%）**；FY2026 全年一家 22%、另一家 14%。**应收更集中**：五大直接客户占 AR **22/14/13/11/10% = 70%**。间接客户：10-Q 原文承认「**一家 AI 研发与部署公司**通过向我们的客户购买云服务，贡献了可观收入」。JPM 投资者会：OpenAI + Anthropic 约占终端消费 **20%，FY2028 或升至 25%**；BofA 称 FY28 约 **25%** 销售来自「需要资产负债表支持的前沿实验室」。**证伪触发器**：任一名 >15% 客户的份额单季下降 ≥5pt，或 AR 前五占比继续上行同时 DSO >75 天 → 下修 `rev_m` 并把 A4 的 L 档概率上调 | active | 10-Q Note 7 / Note 13 / MD&A；10-K；JPM 103757；BofA 103031 | `rev_l`/`rev_m`；zone 归因 |
# | A13 | **循环需求与自有资本**：股权投资 $990 亿 + 承诺 $250 亿；担保 $1,085 亿；AI cloud 采购承诺 $360 亿（含「卖不掉则 NVDA 买回」条款）；与 Apollo/BlackRock/Blackstone/Brookfield/GS/KKR 拟建**规模超 $5,000 亿**的第三方资本平台（MOU，尚未最终签约）。MS 信用研究测算 2028 年底**全口径信用敞口约 $2,000 亿**（其中 ~$1,700 亿为调整项与或有负债），但全口径杠杆仅 ~0.4×、压力情景 0.7×；5Y CDS **84–89bp** vs GOOGL 56 / AMZN 63。**判断**：偿付风险低，但**这部分需求的质量低于 hyperscaler 直采**，故不给它额外倍数、也不把投资组合加回锚点。**证伪触发器**：CDS 站上 100bp，或任一被投/被担保对手方违约、或 $5,000 亿平台一年内未落地为最终协议 → 下修 `rev_m` 至 ACIE 剔除后的水平 | active | 10-Q MD&A + Note 6/10；MS 信用 102759；FY27Q2 新闻稿 | `rev_m`；不加回投资组合 |
# | A14 | **中国 DC 计算收入按 0 建模**（公司 Q3FY27 指引原文即如此假设）。H200 出货 <1% DC 收入且 1H FY27 计提 $4 亿；进口美国另征 25% 关税且无法转嫁。**方向不对称**：下行已实现，重开是上行期权，不进 L/M/H，走 \(V_{opt}\)（A2e-7b 中间分支：算不出分子——许可二元；有已实测上限锚）。**单位 = k=1 × H20 Q1 FY26 实测销售 $4.6B/季 × 4 = $18.4B/年**（8-K Ex.99 CFO Commentary 2025-05-28 原文；H20「主要为中国市场设计」，是产品口径而非开票地）——**快照·下限**（valuation-rules「未建模期权」2026-10-03：公司无中国 DC 收入目标 / 可换算产能 / 已披露合同，份数退到 1 份实测腿；升级门槛见 §1 中国条）。**单位经济取对齐年份 FY2028 该腿数据**：整公司一腿，中国 DC 计算就是 DC 腿的一块，无分部利润 → 用 H 档 FY2028 经营利润率 = `gm_h` 73.0% − `opex_fy28` ÷ `rev_h` 6.2% = **66.8%**（与样板 `GFS.US` / `TSEM.US`「毛利率 − 费用率」同式；期权叠在 H 之上，故取 H 档）× (1 − 17%) ÷ 24.0B 股 = ΔEPS **0.425** × 本票尺 `perpetual_pe(g2 4%, ROE_H 186.4%, r 10% 篮 4)` **16.31×**（不借任何同业倍数）= FY2030 兑现时 6.94 → **兑现年 FY2030 = 对齐年份 + 2，无时点锚·拍值**，按篮子 r 折回分子年 FY2028（÷ 1.1² = 1.21）→ 期权上限 **5.73 美元/股**（2.3% of M；**2026-10-16 框架纠正后**按同一回报路径从 FY2030 起算并折 τ → **4.77**；2026-10-19 期权走 H 档稳态 30% 后 **4.97**，A26，本行其余读数为纠正前口径）。按兑现后 ROE（191%）重估的精确值 5.86，差 0.13 只来自派息率微升，取样板口径（ΔEPS × H 档倍数）。兑现后的继续增长只能以 \(k>1\) 表达，不开两段式。旧口径（v2：× M 档毛利率 72.5%、不扣费用、× M 档倍数 16.24、不折现）= 7.49。**取实测而非需求**：同一原文另有「无法出货的 $2.5B」（全季需求 $7.1B/季，同口径 ≈ 8.8/股）与 Q2 FY26 指引「H20 收入损失约 $8.0B/季」（≈ 10.0/股）——两者是公司陈述的需求量级，未实现，只作坐标；利润率用 FY2028 H 档整公司口径而非 H20 实际（未披露，Q1 FY26 剔计提后混合 GM 71.3% 与 H 档 73% 相近）。升级门槛与证伪触发器见 §1 中国条 | active | EDGAR 0001045810-25-000115 `q1fy26cfocommentary.htm`（本地 `_local/tmp/phase3/NVDA.US/q1fy26cfocommentary.txt`）；8-K 新闻稿指引原文；10-Q MD&A；Citi 103039/103066；valuation-rules「未建模期权」/ construction §7c-1（2026-10-03） | `china_dc_rev_unit`、`v_opt_units`、`t_opt`；表3 |
# | A15 | **供给约束是量的上限、也是价的支撑，方向不唯一**。上限侧：NVDA 已预订台积电 **2026 年 63%、2027 年 52%** 的 CoWoS 产能（HSBC 102184）；HBM 前端产能 39 万→50/69 万片月（2025/2026/2027 年底），DRAM 到 2028Q2 前供不应求；基板/T-glass 有 10–15% 缺口（UBS 103054）。支撑侧：BofA/JPM 称约 $3,000 亿内存承诺**价格基本锁定**，故 FY2028 GM 下行风险有限。**框架处理**：把上限反映在 `rev_h` 只取公司指引（不取 UBS 的 >$7,100 亿），把支撑反映在 `gm_m/gm_h` 采信公司 72–73% 指引；**L 档不享受锁价保护**（A6 的机制是定价与计提，不是投入成本）。**交叉约束**：本仓 `frameworks/TSM.US.md` §1「先进封装」的 CoWoS 产能表 YE26/27/28 ≈ 130k/200k/260k wpm，按 63%/52% 折算 NVDA 可得约 82k/104k wpm——两份框架的产能口径必须同步修订 | active | HSBC 102184；UBS 103054；BofA 103031；JPM 103757；本仓 TSM.US 框架 | `rev_h`；`gm_m/h`；跨票一致性 |
# | A16 | **库存与采购承诺是 L 档的执行路径**：库存 $315.75 亿（原材料 $113.41 亿，两季前 $38.07 亿），供应承诺三季度内 $952 亿 → $2,790 亿。历史标定：FY2026 全年计提 $72 亿（含 H20 $45 亿），对 GM 净影响 −2.6pt；1H FY26 单期 −5.9pt。**证伪触发器**：单季计提 >$30 亿，或库存周转天数连续两季恶化 → 直接把 `gm_m` 下修至 `gm_l` 与 base 的中点，并把 zone 归因改写 | active | 10-Q Note 7 计提表与库存表；10-K Note 12 | `gm_l`；事件后修订 `gm_m` |
# | A17 | **FY2027 桥自洽校验（eval 强制）**：用同一公式回算 FY2027（收入 $4,111 亿、GM 73.68%、opex $345 亿、股本 243.0 亿）得 EPS **9.17**，vs 共识 9.307 偏离 **−1.5%**；M 档桥 EPS 15.23 vs FY28 共识 15.458 偏离 **−1.5%**。**任一偏离 >15% 即强制复核 A5/A7/A8/A9**，不得静默沿用 | active | 8-K 指引 + 共识（yfinance 2026-09-06） | 防脏分子 |
# | A18 | **g2 来源 = 同业横截面反解**（同一把 Gordon 尺、r=10%、yfinance 前瞻 PE × 账面 ROE，2026-09-11）。半导体横截面良态（自身排除）：NXPI 3.24% / QCOM 5.26% / AVGO 5.28% / TSM 5.66% / LRCX 6.48% / KLAC 6.57% / AMAT 6.61% / TXN 6.80% / ASML 6.92% / UMC 7.48%；剔除 AMD、ADI、MCHP、GFS（ROE≈r 或 ROE&lt;r）、MRVL、ARM、NOW（r−g&lt;2% 贴极点）、INTC（ROE&lt;0）、MU（派息封顶分支）。除自身外 10 家中位 **6.52% → 按巨型硬件上限截到 4.0%**（A25；普通上限 6% 的值进候选带 A22）。**严格 AI 加速器同业只剩 AVGO 一家良态（5.28%）**，不足两家。**4% → 3% 每 1pp g2 ≈ 34 美元/股（M）** | active | yfinance 2026-09-11；`eval/lib/gordon.implied_g` | `g2` |
# | A19 | **倍数护栏 = 自身实测次年 PE 带 [7.7, 28.9]**：月末价 ÷ 下一财年分析师口径 EPS（拆股调整后公司 non-GAAP：FY22 0.444 / FY23 0.334 / FY24 1.296 / FY25 2.99 / FY26 4.78（yfinance 季度 Reported EPS 加总，含 SBC 前口径；重述后 4.41）/ FY27 共识 9.307 / FY28 共识 15.458），财年止于 1 月，「下一财年」= 当前财年 + 1。**全窗** 2021-09→2026-09（n=61）为 [7.7, 97.4]、中位 15.6——其中 2021-09→2022-01 五个月的分母是 FY2023 谷底（EPS −25% YoY，加密 / 游戏库存重置），印出 62–97×，正是 valuation-rules 所指「周期底分母塌缩的年份自然给高 PE」，对 g 无信息；**护栏取盈利正常段**（分母 ≥ FY2024，2022-02→2026-09，n=56）：低点 **7.74×**（2023-02，价 23.14 ÷ FY25 2.99）、高点 **28.85×**（2024-11，价 137.88 ÷ FY26 4.78）、中位 14.8×；按次年：FY24 9.3–21.0、FY25 7.7–20.5、FY26 16.5–28.9、FY27 11.6–21.7、FY28 11.3–14.3。排除谷底段使带变窄，是保守方向。生成的 15.8 / 16.2 / 16.3 在带内、贴自身中位 14.8× → 通过。**带即证据**（裁决顺序 ③）：M 档 ROE 下 g2 到下沿需 −7.0pp（g ≈ −3%）、到上沿需 **+2.7pp**（g 6.69%，越 4% 巨型硬件上限与 6% 普通上限）——上沿在合法 g 下不可达，带内任何 ≤ 4% 的 g 都合法；横截面 6.52% 截 4% 后在带内，不触发带边反解。GS 30× normalized（103009）、HSBC 5 年前瞻均值 21×（103035）只作对照；Longbridge 5 年 TTM 带 27.4–217.7× 因盈利高速追赶不作前瞻护栏 | active | yfinance 月末价与季度 EPS（2026-09-14 拉取，数据 09-11 收）；`_local/tmp/phase3/NVDA.US/realised_next_fy_pe_band.txt` | `pe_own_min/max` |
# | A20 | **分子年份的裁决（构造规则冲突裁决顺序 ②）**：分子取 ≥2 家共识可见的最远年份且三点同源——**FY2028** 同时满足两条：收入 56 家区间（$4,164 / $6,735 / $7,785 亿）、EPS 52 家区间（9.80–18.75）；FY2029 只有 UBS 单家（CY2028E 22.08 ≈ FY29，103055），yfinance +1y 止于 FY28、Longbridge 季度共识止于 Q4 FY2027 → 无 ≥2 家点估计，不开过渡年（无 g1），也不进任何层。FY2028 = 当前财年 FY2027 + 1，不折现。**分子与 g 同世界**：三档都是 FY2028 前瞻稳态（L 7.70 高于最近完整年 FY2026 的 4.41），配同一稳态 g2；谷底只作 deep_discount 压力坐标（见口径）。本票与 `MRVL.US` / `AVGO.US` / `TSM.US` 不同之处：最远共识年本身就有区间，不存在「点共识年只进 g1」的读法问题 | active | yfinance 2026-09-06；Longbridge 共识 2026-09-14；UBS 103055 | `rev_*`；无 `n_stage` |
# | A21 | \(p_L/p_M/p_H\) = **0 / 0.25 / 1.0**（表3）；\(p_L\) = 0：消化年世界里许可不落地；\(p_H\) = 1.0：按实测上限满兑现（H20 运行率重现，默认档）；\(p_M\) = 0.25 **无概率锚·拍值**——量级依据：① 当前 H200 中国出货 <1% DC 收入（<$0.89B/季）相对单位 $4.6B/季 <0.19，M 世界的「涓流」按约四分之一个单位计；② 与 `GOOG.US` / `MRVL.US` M 档拍值同量级；可观测锚（升级后改为有锚）= 10-Q 披露的中国 DC 计算收入 / 许可公告 | active | A2e-7d；Citi 103066（少量 H200）；10-Q MD&A | 表3 |
# | A22 | **候选带（g2·可见期后跑道6%）**：同公式只把 `g2` 从巨型硬件上限 4% 换回同业反解截到普通上限的 **6%**——6% 比长期名义增速多出的约 2pp 是 FY2028 之后仍在高增长的一段跑道（r=10% 下约等于十年 10% 增长后回到 4%，valuation-rules「6% 的含义」）；本票的跑道取决于客户 2028 年后是否继续加码 AI 资本开支，没有 ≥2 家 FY2029 共识支撑，故不进底牌（A25）。L′/M′/H′ = **145.46 / 286.75 / 363.02**（账面仍按底牌 g2 滚，A24；同走三段回报与时点对齐，A26）。日报第三行 `候选(g2·可见期后跑道6%)` 独立归 zone，**不进**底牌 zone / 跨票比值 / `calibration.py`。**升级门槛**：≥2 家卖方给出 FY2029 EPS 且 FY28→FY29 增速 ≥ 10% → FY2029 按「增长的表达顺序」进分子或过渡年 \(g_1\)（跑道被命名），重算后删除本行；或定价权两条被证成（A25）→ 豁免巨型硬件上限，底牌 `g2` 回 6% 并删除本行 | active | A18 / A25；valuation-rules「6% 的含义」「巨型硬件上限」；与 `AVGO.US` A22 同尺 | `g2_cand`；候选带一行 |
# | A23 | **归篮**：整公司一腿 → **篮 4 龙头制造**（常规经营现金流、可见度高的行业龙头；无合约化 / 条件性腿）；**备选篮 6 周期商品 / 小盘 13% 撤销**——③ 出带调研（2026-09-17）可查街 WACC / Ke 中位 ≈ 11.4%（ValueInvesting.io 10.8 / SWS 10.5 / DeepViews 12.0 / Baratelli 13.0；GuruFocus 15.9 为 β 驱动异常值），在 10 与 13 之间偏 10，无一到 13%；**CAPM 粗筛 14.0%**（β 2.22 → 4.0% + 2.22 × 4.5%），与篮 4 残差 +4.0pp > 3pp 进「篮子质疑」清单只作观察，不改篮：β 是 AI 主题的市场 β，不是经营现金流风险（ROIC 80%、净现金）。AI 半导的高 g 走命名窗口 / 分子而非更高 r：FY28 共识（52 家区间）已是分子，FY29 无 ≥2 家共识 → 不开 g1 窗口（A20）；H 档若开窗口须每年有订单 / 产能 / 目标证据（$1T 订单至 CY27 是 GTC 口径，无 FY29 共识 EPS），暂不开。换篮 6 的锚点未落数字（定性）。证伪点：篮级季度对账显示隐含 r 持续 ≥ 13% → 复审备选篮 6 | active | `gordon.BASKET_R`；③ 出带街 WACC 调研 2026-09-17（AI 半导五票 MRVL / COHR / GFS / NVDA / TSEM 同批归篮 4）；CAPM β 2.22 | `r_perp` |
# | A24 | **ROE 口径 = 分子年盈利 ÷ 分子年年初净资产（\(E_{n+1}/B_n\)），账面按增长所需留存滚动（valuation-rules 裁决表 ② / 两段式过渡，2026-09-21 定）**：\(ROE_x = EPS_{FY28,x} ÷ BPS_{FY28 年初,x}\)，Gordon 的 \(g = b × ROE\) 里 ROE 是期初权益产出本期利润；旧版用 FY27Q2 权益直接作分母（少了 2H FY27 的留存），年末口径则会把 FY28 本年尚未产出的留存放进分母。FY2028 年初 = FY2027 末：从 FY27Q2 权益（9.54 美元/股，as-of 2026-07-26）起、只滚 **2H FY27 尚未入账**的利润 \(N\) = FY27 共识 9.307 − 1H FY27 实测 4.09（Q1 1.87 + Q2 2.22）= 5.217 × 24.30/24.00 = **5.28 美元/股**（换到 FY28 股本），**留存率 = \(b_1 = g_2/ROE\)**——本票无 g1 窗口（FY29 无 ≥2 家共识，A20），三档都按 \(g_2\) 4% 滚；ROE 与 BPS 互相依赖，闭式解 \(BPS = 9.54 / (1 − 4\% × 5.28 / EPS_x)\)。得 BPS_FY28 年初 = **9.81 / 9.68 / 9.65**、ROE **78.5 / 157.4 / 186.4%**、\(b_1\) = 0.051 / 0.025 / 0.021（旧口径 FY27Q2 权益 = 80.7 / 159.6 / 188.6%）。实付留存 98.9%（三年均值派息 1.1%，`payout_3y`；回购不是派息，是留存现金的去向）超出 \(b_1\) 的部分是 B 桶，走 Outputs 披露行「模型视同派出、实际留存的现金」= (98.9% − \(b_1\)) × 5.28 = **4.95 / 5.09 / 5.11 美元/股**（它是锚点的前提「不被烧掉」——本票实际去向是回购，不是锚点外的价值，MUST NOT 另作腿）。**影响极小**：ROE ≫ r 使派息率几乎不动（0.949 / 0.975 / 0.979），旧口径下倍数 15.84 / 16.25 / 16.31 → 本口径 15.82 / 16.24 / 16.31，L/M/H 121.97 / 247.42 / 293.54 → **121.80 / 247.33 / 293.46**（−0.1% / −0.04% / −0.03%）；ROE 在本票只进派息率系数，不进边际回报 | active | 8-K 新闻稿 Q1/Q2 FY27 non-GAAP EPS；FY27 共识 2026-09-06；yfinance 年报现金股利 / 归母 FY24–26；valuation-rules 2026-09-21 | `eps_1h_fy27`、`payout_3y`（只进披露行）；表1 ROE 列；A11 |
# | A25 | **巨型硬件上限适用（valuation-rules「巨型硬件上限」，2026-09-27 定）**：① **硬件**——收入来自交付 GPU / 系统 / 网络设备，多卖一单位要多一份台积电产能与 HBM（A15）；② **分子年收入 ≥ \$1,500 亿**——FY2028 收入 L / M / H = \$4,164 / 6,735 / 7,785 亿，三档都过（M 约美国名义 GDP 2%，再按 6% 永续即占比永远上升）；③ **未证明定价权**——两条须同时满足才豁免，第一条即不满足：谷歌 TPU、亚马逊 Trainium、Meta MTIA、AMD MI 系列均已量产在用（§1「竞争与地缘」；A6 的 L 档机制正是 ASIC / AMD 价格竞争），「无已量产的合格第二供应商」不成立，第二条（下行期维持价格）不再审。→ 底牌 `g2` ≤ min(4%, r−4%) = 4%，同业反解 6.52% 超出部分进候选带（A22）。**复核条件**：自研 ASIC 与 AMD 在两个财季内合计出货份额明显萎缩、客户回到单一供应商 → 重审定价权第一条；FY2028 收入实际跌破 \$1,500 亿 → 不再适用 | active | valuation-rules 2026-09-27；本框架 A2 / A6 / A15；§1 | `g2`、`g2_cand`；A18 / A22 |
# | A26 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④，2026-10-16 框架纠正）**。① **超额现金**：不单列（净现金约 0.96 美元/股，未达归母权益 15% 门槛），无少数股东，归母比例 1；**增长期资金缺口**：资本开支（季度约 $27 亿）远小于经营现金流，不计。② **稳态回报三段**：可见年 FY2028 用前瞻回报 78.5 / 157.4 / 186.4%（A24）→ 维持到 **Y1 = 2030** → 线性回落到 **Y2 = 2035** → 稳态永续；Y1 / Y2 取光通信链「光引擎规格所有者」环节（高门槛，用户 2026-10-16 定）。**稳态回报（2026-10-19 按序取 + 三档各取各的，用户认可）**：① **自身周期不可用**——最近一轮完整谷到谷是 FY2020–FY2023（投入资本口径均值 62.0%，SEC XBRL，`_local/tmp/round9/sweep/_lib/ic_cycle.py`），但 FY2024 起数据中心收入从约四成升到约九成、客户换成前五大云厂商（卖的东西与客户类型都变了，算结构变化），之后还没有一轮完整周期（旧理由「只有 GAAP、公式不同」不成立，作废）；② **成熟同业层空**——同一门生意、近 5 个年度区间收入复合增速 0–10%、≥ 5 个完整财年的芯片设计公司里只剩 Cirrus Logic（投入资本口径 FY2017–FY2026 均值 19.0%），它做手机音频 / 混合信号芯片，不是 GPU / 加速计算这门生意，单一非同生意同业剔除；Silicon Labs 2021 出售过半业务后不足 5 年读数，高通（+13.5%）、Semtech（+12.0%）近 5 年增速 > 10%；③ 落兜底「轻资产设计」**22%** → **L / M = 22%**（L 前瞻 78.5% 也回落）；**H = min(H 前瞻 186.4%, 30%) = 30%**——拆不出周期的高成长腿，高档是 CUDA 生态与系统级优势守住的世界；中国 DC 期权估在 H 档尺上，同取 30%。对照：若把自身 FY2020–FY2023 周期判为可用，稳态 62% → L / M / H 119.77 / 233.93 / 275.92。不属商品腿豁免。③ **时点对齐**：Gordon 给的是分子年初（FY2028 年初 2027-01-25，RONIC 分母时点）的价值；今天 = \(V_{op}/(1+r)^{\tau}\) + 窗口可分配利润，τ = 2026-07-26 → 2027-01-25 = 0.50 年（原「FY+1 不折现」口径撤回）；窗口 = 2H FY27 尚未入账 non-GAAP 利润 5.28 美元/股 × (1 − \(b_1\))（\(b_1 = g_2/ROE\)，同账面滚动），按 τ/2 折 → 约 5.0 美元/股；期权与候选带的 Gordon 尺同走三段与时点对齐。④ 不带打折 k。g2 4% 是同业反解截顶值，同业按同一路径重解只会更高，仍被截住，不动。影响：M 247.33 → 214.26（−13.4%：三段 −11.3%、时点对齐 −2.6%），未触发纠正对账门；2026-10-19 三档各取各的稳态：H 252.79 → 262.28（+3.8%，L / M 不变），\(V_{opt}\) 4.77 → 4.97，候选带 H′ 338.74 → 363.02 | active | valuation-rules「经营价值与超额现金」；SEC XBRL 年报（自身与同业，投入资本口径）；FY27Q2 10-Q；对话 2026-10-16 / 2026-10-19 | `tau`、`t0_cal`、`y1`、`y2`、`rs_steady`、`rs_steady_h`；锚点、\(V_{opt}\)、候选带 |
# 原框架历史，本次迁移没有新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-09-20
# - v2 切换（篮子 r）：L/M/H v1 178.20 / 366.35 / 435.54 → 178.20 / 366.35 / 435.54（无变化），zone `conservative` → `conservative`；篮子：整公司一腿篮 4 龙头制造 10%（与 v1 常规经营档同值；备选篮 6 13% 撤销——③ 出带调研街 WACC 中位 11.4%，无一到 13%；CAPM 14.0% 进质疑清单）；g2 6% 沿用横截面截顶（cap = min(6%, r−4%) 在篮 4 下仍 6%，未收紧），高 g 走命名窗口 / 分子而非 r（FY29 无共识故不开窗）；新增 A23 归篮与披露行：隐含 r(P) 12.7%、③ 不出带、g2 −1pp 贴边不翻转（A′ 219.8 vs 现价 218.29）、无地板；候选带 121.98 / 247.42 / 293.54 不变。分子、轴、期权不动；`eval/NVDA.US.py` 改读篮子（`parse_baskets` + `check_r(r, "r_perp", 篮)` + `check_g_cap(g, r)`）
# - touched: [A11, A23, r_perp, g2, 披露行]
# ### 2026-10-03
# - 迁移到 2026-10-03 规则（期权上限由公开数据闭合 / 增长表达顺序 / 数据优先级 / 同业同尺）：v2 → v3。只改 \(V_{opt}\)：份数无公司具名量（无中国 DC 收入目标、可换算产能或已披露合同）→ 维持 1 份实测腿 $18.4B/年，标「快照·下限」并补升级门槛；单位经济由「M 档毛利率、不扣费用」改为对齐年份 FY2028 H 档经营利润率 66.8%；倍数由 M 档 16.24× 改为本票 H 档 16.31×（借量不借价，未借同业倍数）；兑现年无具名 → FY2030（对齐年份 + 2，无时点锚·拍值），按篮 4 r 10% 折回两年。\(V_{opt}\) 7.49 → **5.73**，表3 修正带 121.80 / 249.20 / 300.96 → 121.80 / 248.76 / 299.19。底牌 L/M/H 121.80 / 247.33 / 293.46 不变、候选带不变。其余核对：g2 4% 未被抬高表达高增（6% 跑道按巨型硬件上限进候选带）；分子 FY2028 = ≥2 家带区间共识最远年；无同业组（`AVGO.US` AI 腿同为 4%，同腿同 g2，不建组）
# - touched: [A14, §1 中国条, t_opt, china_dc_rev_unit, Formula 步 7, 表3, Outputs, eval]
INPUTS = {
    # FY2028 平均稀释股本；A9; 来源：2026-08-26
    'shares_fy28': 2.400e10,
    # non-GAAP 税率，公司指引 16–18% 取中；A8; 来源：2026-08-26
    'tax_rate': 0.17,
    # FY2028 non-GAAP opex USD，三档共用。**无一手披露背书，是按 FY2027 基数 +39.1% 的外推**（A7）；由 eval 的 opex 增速护栏约束在 `opex_fy27 < opex_fy28 ≤ opex_fy27 × (1+g27)` 内; 来源：外推（基数 as-of 2026-08-26）
    'opex_fy28': 4.80e10,
    # FY2026 non-GAAP opex USD（重述后含 SBC 口径）= GAAP 230.76 亿 − 收购相关 2.04 亿 − 其他 0.53 亿。**只作 opex 增速护栏的基数，不进任何锚点**；由它得 FY26→FY27 增速 **+51.2%**; 来源：8-K Ex-99.1 FY2026 汇总
    'opex_fy26': 2.2819e10,
    # FY2028 收入消化档 USD = 分析师区间下沿（≈ 与 FY27 持平）；A4; 来源：2026-09-06
    'rev_l': 4.164e11,
    # FY2028 收入共识均值 USD（56 家）；A2; 来源：2026-09-06
    'rev_m': 6.735e11,
    # FY2028 收入 USD = **分析师区间上沿**（56 家，同 `rev_l` 同源）；A3; 来源：2026-09-06
    'rev_h': 7.785e11,
    # 消化档 non-GAAP 毛利率；A6（历史标定 FY2023 56.9%、FY2026 71.1%）; 来源：2026-09-06
    'gm_l': 0.650,
    # 公司 FY2028 指引 72–73% 取中；A5; 来源：2026-08-28
    'gm_m': 0.725,
    # 指引上沿；A5; 来源：2026-08-28
    'gm_h': 0.730,
    # 股东权益 USD，FY27Q2 10-Q（季末 2026-07-26；yfinance 资产负债表 2026-07-31 列）；三档 ROE 的**起点**——÷ shares_fy28 = 9.54 美元/股，按增长所需留存 \(b_1=g_2/ROE\) 滚过 2H FY27 到 FY2028 年初再作分母（A24），不直接作分母; 来源：2026-07-26
    'equity': 2.28984e11,
    # 整公司永续折现率 = **篮 4 龙头制造** 10%：常规经营现金流、无合约化 / 条件性腿（备选篮 6 13% 撤销：街 WACC 中位 11.4%，无一到 13%；CAPM 14.0% 进质疑清单）；值 = `gordon.BASKET_R`；A11 / A23; 来源：2026-09-20
    'r_perp': 0.10,
    # **同业反解·巨型硬件截顶**·永续增速，三档共用：半导体横截面除自身外 10 家良态中位 6.52% → 本票为巨型硬件（FY28 收入 ≥ $1,500 亿、未证明定价权：谷歌 TPU / 亚马逊 Trainium / Meta MTIA / AMD 均已量产，A25）→ cap = min(4%, r−4%) = 4%（valuation-rules「巨型硬件上限」）；超出部分进候选带（A22）；A18; 来源：2026-09-27
    'g2': 0.04,
    # **候选带**用：可见期后增长跑道 = 同业反解 6.52% 截到普通上限 6%（原底牌值）；同公式只换本字段（A22）；不进底牌; 来源：2026-09-27
    'g2_cand': 0.06,
    # 倍数护栏下沿 = 自身实测次年 PE 带（盈利正常段 2022-02→2026-09）低点 7.74×（2023-02 月末价 ÷ FY25 non-GAAP EPS）；A19; 来源：2026-09-14
    'pe_own_min': 7.7,
    # 倍数护栏上沿 = 同一带高点 28.85×（2024-11 月末价 ÷ FY26 分析师口径 EPS 4.78）；A19; 来源：2026-09-14
    'pe_own_max': 28.9,
    # 中国 DC 期权的已实现单位 USD/年 = H20 Q1 FY26 实测销售 $4.6B/季 × 4（8-K Ex.99 CFO Commentary 原文）；**快照·下限**（公司无中国 DC 收入目标 / 产能 / 合同可换算）；只进 \(V_{opt}\)，不进锚点；A14; 来源：2025-05-28
    'china_dc_rev_unit': 1.84e10,
    # \(V_{opt}\) 单位数（k=1 × 已实现单位）；A14; 来源：2026-09-14
    'v_opt_units': 1,
    # \(V_{opt}\) 兑现年（财年）= 对齐年份 FY2028 + 2，**无时点锚·拍值**（公司未给中国放量时点）；按 r_perp 折回 FY2028；A14; 来源：2026-10-03
    't_opt': 2030,
    # FY2027 收入 USD（Q1/Q2 实际 + Q3/Q4 共识）；A17 桥校验; 来源：2026-09-06
    'rev_fy27': 4.111e11,
    # FY2027 加权 GM（1H 实际 75.0%、Q3 指引 74.0%、Q4 电话会 71.5%）；A17; 来源：2026-08-28
    'gm_fy27': 0.7368,
    # FY2027 non-GAAP opex USD；A7; 来源：2026-08-26
    'opex_fy27': 3.45e10,
    # FY2027 平均稀释股本；A17; 来源：2026-08-26
    'shares_fy27': 2.430e10,
    # FY2027 non-GAAP EPS 共识（46 家）；A17 校验基准; 来源：2026-09-06
    'eps_fy27_cons': 9.307,
    # FY2028 non-GAAP EPS 共识（52 家，区间 9.80–18.75）；A17 校验基准; 来源：2026-09-06
    'eps_fy28_cons': 15.458,
    # 1H FY27 已入账 non-GAAP EPS = Q1 1.87 + Q2 2.22（8-K 新闻稿）；从 `eps_fy27_cons` 里扣掉，余下 2H FY27 未入账利润滚进 FY2028 年初净资产；A24; 来源：2026-08-26
    'eps_1h_fy27': 4.09,
    # 近三年实付派息率均值（FY24 1.3% / FY25 1.1% / FY26 0.8%，现金股利 ÷ 归母净利，yfinance 年报现金流）；只进 A24 的 B 桶披露行，**不进**主尺的 BPS 推演（主尺按 \(b_1=g_2/ROE\) 滚）；回购不算派息（它是留存现金的去向）; 来源：2026-01-31
    'payout_3y': 0.011,
    # CoWoS 配额 **α 状态**片数（NVDA 承担全部 29.4 万片缺口）；`_AXIS.cowos-capacity.md` §2。**不进锚点**，供轴内/轴外拆分与跨文件校验; 来源：2026-08-28
    # CoWoS 配额 **β 状态**片数（按需求等比例分摊）；同上; 来源：2026-08-28
    # CoWoS 配额 **γ 状态**片数（NVDA 足额）；同上; 来源：2026-08-28
    # DC 收入占总收入 = FY27Q2 实测 $890 亿 / $960 亿；轴内外拆分用; 来源：2026-08-26
    'dc_share_rev': 0.927083,
    # Hyperscale 占 DC 收入 = FY27Q2 实测 $490 亿 / $890 亿；轴内外拆分用; 来源：2026-08-26
    'hyper_share_dc': 0.550562,
    # 时点对齐年数 = 估值基准日 2026-07-26（FY27Q2 资产负债表日）→ 分子年 FY2028 年初 2027-01-25，183 天 ÷ 365；Gordon 经营价值按 `r_perp` 折 τ、窗口可分配利润折 τ/2；A26; 来源：2026-10-16
    'tau': 0.50137,
    # 稳态回报三段的日历起点 = 分子年 FY2028（t = 1）；A26; 来源：2026-10-16
    't0_cal': 2028,
    # 高回报期止点 Y1（RONIC 维持前瞻值到此年）= 光通信链「光引擎规格所有者」环节、高门槛；A26; 来源：2026-10-16
    'y1': 2030,
    # 稳态起点 Y2（Y1 → Y2 线性回落，Y2 起稳态永续）；同上；A26; 来源：2026-10-16
    'y2': 2035,
    # L / M 档稳态回报按序取（2026-10-19，用户认可）：自身周期不可用（数据中心收入约四成 → 约九成，客户类型变了，之后无完整周期）→ 同业层空：唯一合格样本 Cirrus Logic（投入资本口径 19.0%）做音频 / 混合信号芯片，不是同一门生意，剔除 → 兜底「轻资产设计」22%；三档按「≤ 该档前瞻」封顶；A26; 来源：2026-10-19
    'rs_steady': 0.22,
    # H 档（与中国 DC 期权，走 H 档尺）稳态回报 = min(H 前瞻 186%, 30%)（「三档各取各的稳态」：拆不出周期的高成长腿，CUDA 生态与系统级优势守住的世界；A26）; 来源：2026-10-19
    'rs_steady_h': 0.30,
}
BASKETS = {"r_perp": 4}
REQUIRED = frozenset(INPUTS) | {'cowos_quota_l','cowos_quota_m','cowos_quota_h'}

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the steady-state-return path (valuation-rules「经营价值与超额现金」②
    稳态回报三段; gordon.py's three-segment function is not built yet, so it lives here).

    Calendar years, t = 1 is the numerator year t0; the retention of year c earns from c+1.
    RONIC = the tier's forward value through Y1, falls linearly to the steady value R_s by Y2,
    and stays there (R_s capped at the tier's forward value).  With R_s >= forward this is
    exactly perpetual_pe(g, roe, r)."""
    rs_eff = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs_eff
        return roe + (rs_eff - roe) * (cal - y1) / (y2 - y1)

    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g / rs_eff) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g / ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1


def eps_of(rev: float, gm: float, opex: float, tax: float, shares: float) -> float:
    """Non-GAAP EPS bridge: revenue -> gross profit -> operating income -> per share."""
    return (rev * gm - opex) * (1.0 - tax) / shares



def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    inp=dict(inp)
    missing = REQUIRED - inp.keys()
    if missing:
        raise ValueError(f"missing inputs: {sorted(missing)}")
    errors: list[str] = []
    review_flags=[]
    require_whole_years(inp,('t0_cal','y1','y2'))

    # --- Step 1: scenario ordering (a scenario ladder must actually be a ladder) ---
    if not (inp["rev_l"] < inp["rev_m"] <= inp["rev_h"]):
        errors.append(
            f"revenue order: {inp['rev_l']:.3e}/{inp['rev_m']:.3e}/{inp['rev_h']:.3e}"
        )
    if not (inp["gm_l"] < inp["gm_m"] <= inp["gm_h"]):
        errors.append(f"gm order: {inp['gm_l']}/{inp['gm_m']}/{inp['gm_h']}")
    # Perpetual-growth 口径: one basket r for the whole-company leg (A23), one
    # g2 capped at that r, not at the pole.  A hardware leg whose numerator-year
    # revenue clears MEGA_HW_REVENUE_USD gets the 4% mega-hardware cap in the
    # base; the peer value above it lives only in the candidate band (A22).
    mega_hw = inp["rev_m"] >= MEGA_HW_REVENUE_USD
    r, g2 = inp["r_perp"], inp["g2"]
    baskets = BASKETS
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2", mega_hw=mega_hw)
    if r - g2 <= 0:
        errors.append("perpetuity diverges: g2 >= r")
    elif r - g2 < MIN_R_MINUS_G:
        errors.append(f"r - g2 = {r - g2:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # --- Step 2: the FY2028 bridge, run three times ---
    tax, shares, opex = inp["tax_rate"], inp["shares_fy28"], inp["opex_fy28"]
    eps_l = eps_of(inp["rev_l"], inp["gm_l"], opex, tax, shares)
    eps_m = eps_of(inp["rev_m"], inp["gm_m"], opex, tax, shares)
    eps_h = eps_of(inp["rev_h"], inp["gm_h"], opex, tax, shares)
    if not (eps_l < eps_m < eps_h):
        errors.append(f"eps order: {eps_l:.3f}/{eps_m:.3f}/{eps_h:.3f}")

    # --- Step 2b: multiples generated from g2 and tier ROE (AGENTS.md 永续增长口径) ---
    # ROE = E_{n+1} / B_n: FY2028 EPS over the FY2028 OPENING book (= end of
    # FY2027), not today's FY27Q2 book (valuation-rules 裁决表 ② as of
    # 2026-09-21; A24).  The FY27Q2 book is rolled over the 2H FY27 earnings not
    # yet booked (FY27 consensus minus 1H FY27 actual, non-GAAP) at the
    # GROWTH-REQUIRED retention b1 = g/ROE -- not the actual payout complement.
    # No g1 window here (FY29 has no consensus, A20), so every tier rolls at g2.
    # With ROE = eps / BPS and BPS = BPS0 + b1·N the fixed point is closed-form:
    # BPS = BPS0 / (1 - g2·N/eps).  Actual retention beyond b1 is the B bucket,
    # printed as a disclosure, not put into the book.
    unbooked = (inp["eps_fy27_cons"] - inp["eps_1h_fy27"]) * inp["shares_fy27"] / shares
    bps_q2 = inp["equity"] / shares
    bps_open = {}
    roe_t = {}
    b1 = {}
    for t, e in (("l", eps_l), ("m", eps_m), ("h", eps_h)):
        bps_open[t] = bps_q2 / (1.0 - g2 * unbooked / e)
        roe_t[t] = e / bps_open[t]
        b1[t] = g2 / roe_t[t]
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"{t.upper()} growth-required retention b1 = {b1[t]:.3f} outside (0,1)")
    roe_l, roe_m, roe_h = roe_t["l"], roe_t["m"], roe_t["h"]
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in b1}  # disclosure only
    # Operating value and time alignment (valuation-rules「经营价值与超额现金」② / ③, A26):
    # the Gordon value sits at the start of the numerator year FY2028; today's value =
    # V_op(t_n) / (1+r)^tau + window distributable profit (2H FY27 unbooked x (1 - b1), at
    # tau/2, floored at 0).  The multiples below are TODAY's operating multiples (anchor / eps).
    tau, t0 = inp["tau"], int(inp["t0_cal"])
    y1, y2, rs = int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]
    # Steady return per tier (retention「三档各取各的稳态」, A26): L / M = fallback, H (and the
    # China-DC option, valued on the H tier's ruler) = min(H forward, 30%).
    rs_t = {"l": rs, "m": rs, "h": inp["rs_steady_h"]}
    if rs_t["h"] < rs:
        errors.append(f"rs_steady_h {rs_t['h']} below the L / M steady {rs}")

    def today_pe(g: float, roe: float, rr: float, e: float, b1_: float, t: str = "m") -> float:
        win = max(unbooked * (1.0 - b1_), 0.0) * (1 + rr) ** -(tau / 2)
        return path_pe(g, roe, rr, t0, y1, y2, rs_t[t]) * (1 + rr) ** -tau + win / e

    eps_t = {"l": eps_l, "m": eps_m, "h": eps_h}
    pe_l, pe_m, pe_h = (today_pe(g2, roe_t[t], r, eps_t[t], b1[t], t) for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③, A19): today's operating multiple inside the own realised next-FY PE band.
    for label, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            review_flags.append('historical_multiple_outside_band')
            break

    # Band-edge g (③ 带即证据): the g2 that would put the M-tier multiple on each
    # edge of the own band.  Reported, never used.
    def g_at(target: float) -> float:
        lo, hi = -0.30, r - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if today_pe(mid, roe_m, r, eps_m, mid / roe_m) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_g = (g_at(inp["pe_own_min"]), g_at(inp["pe_own_max"]))

    L = eps_l * pe_l
    M = eps_m * pe_m
    H = eps_h * pe_h
    A = (L + M) / 2
    Bcut = (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")

    # --- Step 3: A17 two-sided consensus bridge (guards against a dirty numerator) ---
    eps_fy27 = eps_of(
        inp["rev_fy27"], inp["gm_fy27"], inp["opex_fy27"], tax, inp["shares_fy27"]
    )
    dev27 = eps_fy27 / inp["eps_fy27_cons"] - 1.0
    dev28 = eps_m / inp["eps_fy28_cons"] - 1.0
    if abs(dev27) > BRIDGE_TOL:
        review_flags.append('historical_fy27_consensus_bridge_difference')
    if abs(dev28) > BRIDGE_TOL:
        review_flags.append('historical_fy28_consensus_bridge_difference')

    # --- Step 3b: opex ramp guard -------------------------------------------
    # The consensus bridge alone leaves opex_fy28 free over roughly $0-108B,
    # and opex_fy28 is the one input with no first-party disclosure behind it.
    # Tie it to the realised FY26->FY27 ramp: opex must grow with a business
    # whose revenue grows ~60%, but not faster than it did last year.
    g27 = inp["opex_fy27"] / inp["opex_fy26"] - 1.0
    g28 = inp["opex_fy28"] / inp["opex_fy27"] - 1.0
    if not (inp["opex_fy26"] < inp["opex_fy27"] < inp["opex_fy28"]):
        review_flags.append('historical_opex_path_needs_review')
    elif g28 > g27:
        review_flags.append('historical_opex_path_needs_review')

    # --- Step 3b2: tier construction guards (A2e-2c / A2e-5) ----------------
    # The three tiers must be told apart by their numerators; if holding the
    # multiple flat collapses a tier into its neighbour, the multiple was doing
    # the separating -- and a higher multiple on higher earnings is the cycle-
    # peak error this framework exists to avoid.
    ladder_errors, _ = flat_multiple_ladder((eps_l, eps_m, eps_h), pe_m)
    errors.extend(ladder_errors)
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    # --- Step 3c: shared-axis guard vs _AXIS.cowos-capacity.md --------------
    # The quotas do not enter the anchors; they are what the anchors *mean*.
    # Reading them from the axis file is what stops NVDA and AVGO from both
    # assuming they lose share (their L/H map to opposite states, axis §3).

    # --- Step 4: diagnostics that must never feed back into the anchors ---
    implied_peak_pe = L / eps_m

    # On-axis revenue scales with the quota; ACIE is the residual. Printing the
    # implied ACIE move keeps L's weakest input (A4 ②) visible on every run.
    non_dc = inp["rev_m"] * (1.0 - inp["dc_share_rev"])
    on_axis_m = inp["rev_m"] * inp["dc_share_rev"] * inp["hyper_share_dc"]
    split: dict[str, tuple[float, float]] = {}
    for label, rev, quota in (
        ("L", inp["rev_l"], inp["cowos_quota_l"]),
        ("M", inp["rev_m"], inp["cowos_quota_m"]),
        ("H", inp["rev_h"], inp["cowos_quota_h"]),
    ):
        on_axis = on_axis_m * quota / inp["cowos_quota_m"]
        split[label] = (on_axis, rev - non_dc - on_axis)
    acie_m = split["M"][1]

    # --- Step 4b: option ceiling (A14) -- probabilities only in table 3 ---
    # V_opt = (post-realisation anchor - H) discounted from t_opt to the
    # numerator year; approximated as ΔEPS × H-tier multiple (TSEM / GFS form).
    option={'status':'unavailable','label':'中国数据中心','anchors':None}
    om_h = d_eps_opt = v_opt = opt = a2 = b2 = None
    try:
        require_whole_years(inp,('t_opt',))
        if inp['t_opt'] <= NUM_YEAR:
            raise ValueError('option realization must follow numerator year')
        om_h=inp['gm_h']-opex/inp['rev_h']
        d_eps_opt=inp['v_opt_units']*inp['china_dc_rev_unit']*om_h*(1-tax)/shares
        disc=(1+r)**(inp['t_opt']-NUM_YEAR)
        v_opt=d_eps_opt*path_pe(g2,roe_h,r,int(inp['t_opt']),y1,y2,rs_t['h'])/disc*(1+r)**-tau
        opt=tuple(a+p*v_opt for a,p in zip((L,M,H),OPTION_FRACTIONS))
        if all(math.isfinite(v) for v in (v_opt,*opt)) and v_opt>0 and 0<=opt[0]<opt[1]<opt[2]:
            a2,b2=(opt[0]+opt[1])/2,(opt[1]+opt[2])/2
            option={'value':v_opt,'weights':dict(zip('LMH',OPTION_FRACTIONS)),
                    'anchors':dict(zip('LMH',opt))}
        else:
            om_h=d_eps_opt=v_opt=opt=None
    except (ValueError,ZeroDivisionError,OverflowError):
        om_h=d_eps_opt=v_opt=opt=None

    p_tiers = OPTION_FRACTIONS
    cap_hit = band_edge_g[1] > g_cap(r, mega_hw) + 1e-9

    # A22 candidate band: same formula, only g2 -> g2_cand (the post-horizon
    # runway the mega-hardware cap keeps out of the base).
    candidate={'status':'unavailable','label':'长期增长候选','anchors':None}
    pe_c=cand=None
    try:
        g2c=inp['g2_cand']
        if check_g_cap(g2c,r,'g2_cand') or r-g2c < MIN_R_MINUS_G:
            raise ValueError('candidate growth outside model domain')
        pe_c=tuple(today_pe(g2c,roe_t[t],r,eps_t[t],b1[t],t) for t in ('l','m','h'))
        cand=(eps_l*pe_c[0],eps_m*pe_c[1],eps_h*pe_c[2])
        if all(math.isfinite(v) for v in cand) and 0<=cand[0]<cand[1]<cand[2]:
            candidate={'label':'长期增长候选','anchors':dict(zip('LMH',cand))}
        else:
            pe_c=cand=None
    except (ValueError,ZeroDivisionError,OverflowError):
        pe_c=cand=None
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): r_perp is the only
    # priced r; Δr_f moves it 1:1 in each tier's Gordon multiple while the FY28 EPS
    # bridge, tier ROE and g2 stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(eps_t[t] * today_pe(g2, roe_t[t], r + dr, eps_t[t], b1[t], t) for t in ("l", "m", "h"))

    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    result = {
        "ticker": "NVDA.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-07-26',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of':'2026-10-19',
        "anchors": band((L, M, H)),
        "candidate": candidate,
        "option": option,
        "cut_points": [A, Bcut], "option_cut_points": None if a2 is None else [a2,b2],
        'review_flags':review_flags + ['historical_single_source_cowos_allocation',
            'historical_opex_forecast_unverified','historical_china_recovery_not_company_guidance'],
        "mega_hw": mega_hw, "eps_l": eps_l, "eps_m": eps_m, "eps_h": eps_h,
        "unbooked": unbooked, "bps_q2": bps_q2, "bps_open": bps_open, "roe_t": roe_t,
        "b1": b1, "excess_cash": excess_cash, "pe_l": pe_l, "pe_m": pe_m, "pe_h": pe_h,
        "band_edge_g": band_edge_g, "band_upper_above_cap": cap_hit,
        "eps_fy27": eps_fy27, "dev27": dev27, "dev28": dev28,
        "g27": g27, "g28": g28, "split": split, "implied_peak_pe": implied_peak_pe,
        "om_h": om_h, "d_eps_opt": d_eps_opt, "pe_c": pe_c,
        "parameters": {"discount": r, "growth": g2,
                       "forward": band([roe_t[t] for t in ("l", "m", "h")]),
                       "mature": band([min(roe_t[t], rs_t[t]) for t in ("l", "m", "h")])},
    }
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',priced_r={'r_perp':r},
            band_at=band_rf,rates_loader=lambda _currency:rate_inputs,base_anchors=(L,M,H)))
    return result


def calculate(context):
    quotas=context['axes']['cowos']['quotas']
    selected={f'cowos_quota_{t}':quotas[t.upper()] for t in 'lmh'}
    result=evaluate({**INPUTS,**selected},context.get('rate_inputs'))
    result['basis_changed']=None
    optional=('g2_cand','v_opt_units','china_dc_rev_unit','t_opt')
    if any(not math.isfinite(INPUTS[k]) for k in optional):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'cowos':selected,'option_fractions':OPTION_FRACTIONS,'num_year':NUM_YEAR},
            HISTORICAL_PARTIAL_FINGERPRINT)
    result['units']={'price':'USD_PER_SHARE'}
    if result['option'] is not None:
        result['option']['value_unit']='USD_PER_SHARE'
    result['segments']={'company':{'unit':'USD_PER_SHARE','values':dict(result['anchors'])}}
    result['key_parameters']={
        'discount_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_perp'])},
        'growth_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g2'])},
        'forward_return':{'unit':'RATIO','values':{t.upper():result['roe_t'][t] for t in 'lmh'}},
        'steady_return':{'unit':'RATIO','values':{
            t.upper():min(result['roe_t'][t],INPUTS['rs_steady_h'] if t=='h' else INPUTS['rs_steady']) for t in 'lmh'}}}
    return result
