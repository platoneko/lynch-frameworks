#!/usr/bin/env python3
"""AMKR legacy valuation; migration does not revise financial assumptions.

Monetary inputs use USD millions and shares are absolute counts. Arizona
phase-one investment and the phase-two scenarios are estimates, not guidance.
"""
from __future__ import annotations
from lib.gordon import check_branch, check_g_cap, check_r, g_cap, payout_gap
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

FORMULA_ID = "amkr_fy27_cons_gordon_opeq_v1"
LISTING_CCY = "USD"
TOL = 0.05
MILLION = 1e6
MIN_R_MINUS_G = 0.02
P_TIERS = (0.0, 0.25, 1.0)
PEER_PE_SAME_RULER = (18.65, 20.33)
TIERS = ("L", "M", "H")
# | A1 | 整公司单一尺，**不拆 SOTP**：10-K 只有一个报告分部；终端市场与产品口径只披露收入、不披露利润；四个终端市场共用工厂与客户，卖方无分部估值；分部启发式命中约 1 条（驱动不同：计算 vs 通信）< 2 | active | FY2025 10-K 分部附注；2026Q2 新闻稿终端市场表 | 主尺形态 |
# | A2 | **分子 = FY27 九家共识 EPS 三点 2.25 / 2.776 / 3.80（裁决顺序 ②；2026-10-28 财报后换数，原 2.32 / 2.806 / 3.69）**：FY27 是最远的 ≥2 家且带区间的共识年；FY28 已有卖方点值（美银 3.47，2026-10-28；另有报道称一致预期约 3.30），但 yfinance / Longbridge 无 ≥2 家带区间的 FY28 共识，**待核实**；管理层 2028 目标（EPS 2.50 ± 0.25）是公司单源、不作分子。FY27 年初的 Gordon 价值按时点对齐折回估值基准日（A18；原「当前财年 +1 不折现」撤回）。**升级门槛**：FY28 出现 ≥2 家带区间 → 分子换 FY28（框架纠正）。**证伪触发器**：两个季度内 FY27 共识均值下修 > 20%（以 2.806 计，线在 2.245；2026-10-28 读数 2.776，−1.1%） | active | yfinance `earnings_estimate` / `eps_trend` 2026-10-28；Wisburg 美银 2026-10-28；投资者日 8-K 2026-05-21 | `eps_fy27_l/m/h` |
# | A3 | **`cyclical` 的 M 取前瞻共识而非历史周期中枢**（valuation-rules「周期票的中枢分子」：需求周期型制造按共识取 M；另有资产基数变动——固定资产净值 2016 年 25.6 亿 → 2025 年 39.6 亿、2026 年起亚利桑那 70 亿美元工程）：十年 EPS 均值约 1.44，按整轮均值取中枢 M 约 15–20 美元。取 FY27 共识的理由：计算业务占比上升、台积电 / 英伟达长约、亚利桑那一期客户已全额承诺（苹果、英伟达、台积电）。**取样窗口的供给状态**：2016–2025 含两次下行（2018–19、2023–25）与一次紧平衡（2021–22），非单一状态。**复核触发**：开工率回落使年度 EPS 跌回 1.5 美元以下，或两个季度内 FY27 共识均值下修 > 20% → 回对话重审中枢（2026-10-28：FY26 实际 + Q4 指引中值约 2.49，FY27 均值 −1.1%，未触发） | active | Longbridge 年报 2016–2025；2026Q2 电话会（Wisburg 97831）；2026Q3 8-K | M 的分子；表2 `conservative` / `deep_discount` 解释 |
# | A4 | **共识即 GAAP 口径，不扣 SBC**：Amkor 只报 GAAP EPS，Longbridge 季度共识 GAAP 与「调整后」相差 < 1%（Q3'26 0.7816 vs 0.7766）；SBC FY2025 20.1M（约为净利的 5%）已在费用内。股本锁在 2026Q2 稀释加权 249.978M；可转债的稀释见 A11 | active | Longbridge `consensus` 2026-10-08；yfinance 现金流量表 | `shares` |
# | A5 | **ROE 按经营权益、净债作闭合项一次扣除（对齐 `FORM.US` A5 / `1810.HK` A15）**：经营权益 = 4,799.7 − (−292.2) = **5,091.9M**；分子剔除净利息收入（2026Q3 利息收入 22.728M − 利息支出 17.916M = 4.812M × 4 × (1 − 15.4%) ÷ 249.526M = **0.065/股**）；净债 **−1.17/股** 扣除。三处口径一致：利息不在分子、现金与债不在权益、净债只在闭合项计一次。少数股东权益 36.5M 不进；受限现金 201.7M（建设保证金等）不计入现金；客户预付款形成的合同负债 547.6M 按经营负债处理、不计入净债（是否按零息客户融资处理见 A10 待补） | active | 2026Q3 10-Q 资产负债表与损益表 | `equity`、`cash`、`debt`、`lease_*`、`net_cash`、`int_q` |
# | A6 | **ROE 口径 = 分子年盈利 ÷ 分子年年初经营权益（\(E_{n+1}/B_n\)，valuation-rules 裁决表 ② / 两段式过渡，2026-09-21）**：FY27 年初 = FY26 末；要滚的是 FY26 第四季度未入账利润 \(N\) = FY26 共识 2.504 − 前三季度实际 1.79 − 一季度利息 0.016 = **0.698/股**（2026-10-28 起估值基准日 2026-09-30，原为上半年口径 1.521），留存率 \(b_1=g_2/ROE\)；闭式解 \(BPS = 20.406/(1 - 0.06 \times 0.698/c_x)\) → **20.805 / 20.726 / 20.638**、ROE **10.5 / 13.1 / 18.1%**、\(b_1\) = 0.57 / 0.46 / 0.33。实付留存（近三年派息率 30.8%）超出 \(b_1\) 的部分 = (0.692 − \(b_1\)) × 0.698 = **+0.08 / +0.16 / +0.25 美元/股**（模型视同派出、实际留存；Outputs 披露行，不进锚点）。**已知偏差（待框架纠正）**：经营 BPS 含亚利桑那已投入但 FY27 不产出的资本（10-Q 未单列金额），压低 ROE_x，与 A10 的 D 桶罚项对同一笔资本计了两次；拟与 A10「逐年现金流」一并按规则处理 | active | 2026Q3 10-Q；yfinance FY26 共识 2026-10-28；2026Q1 / Q2 / Q3 EPS 0.33 / 0.70 / 0.76 | ROE_x、表1 |
# | A7 | **g2 = 6%，来源层级第一层（同业反解 · 截顶）**：台湾封测簇 2026-10-08 yfinance（FY27 共识 EPS ÷ 当前每股净资产作前瞻 ROE，现价 ÷ FY27 EPS 作倍数）→ `implied_g`（r=10%）：日月光 3711.TW 26.18× / 32.1% → 7.01%、京元电子 2449.TW 20.82× / 30.0% → 6.19%、力成 6239.TW 16.85× / 23.6% → 5.43% → 中位 **6.19%** → 截到 \(G_{cap}\) = 6%。三家同篮（篮 4）、同域（单调区）、留存分支（派息率 50–69%，均 < 80%）。**剔除**：长电 600584.SH（ROE 11.2%，病态区，反解不良态）、通富 002156.SZ（7.1%）、华天 002185.SZ（6.4%）——峰形区，与本票 M 档不同域；日月光 ADR 与 3711.TW 重复，只取后者。**同世界门**：本票 FY26 → FY27 共识 EPS +10.9%、收入 +14.1% 上行（2026-10-28；原 +9.1% / +12.7%） → g2 ≥ 0 可用（同 `FORM.US` A7 用法）；更远年无 ≥2 家点值；交叉：管理层 2028 EPS 目标 2.50 低于 FY27 共识（亚利桑那投产拖累）、2030 目标 5 美元上行；近三年现金分红 55.1M（2022）→ 81.9M（2025）上行。**证伪点**：≥2 家卖方 FY28 点值低于 FY27 → 同世界门翻转，g2 ≥ 0 不可用，回对话；簇中位跌破 6% → 取簇值 | active | yfinance 2026-10-08；投资者日 8-K | `g2`、`g_peer_median`、`g_peer_low` |
# | A8 | **g2 的杠杆与证据区间**：簇原值 5.43–7.01%，跨上限 → 证据区间 [5.43%, 6%]；低端 5.43% → **20.85 / 32.24 / 50.01**（研究当日检查：区间两端 zone 不变，不 BLOCKED；2026-10-28 复查同）。机械 −1pp（5%）→ **20.71 / 31.10 / 47.67**（两组均已含 A18 三段与时点对齐）；+1pp 越 ① 不可用 | active | `eval/AMKR.US.py` 打印 | 敏感区 |
# | A9 | **归篮：整公司一腿 → 篮 4 常规经营 10%**（valuation-rules「§r 篮子」2026-09-28）：盈利不是商品价函数——封测按件与客户议价，基板 / 金线等原料成本可部分转嫁；不命中篮 7——单一客户最高苹果 29.8%、前两大 40.9%（+ 高通 11.1%），低于 50% / 70% 阈值；国别：生产在韩国、菲律宾、越南、中国、日本、马来西亚、葡萄牙等，收入按客户分散，不是单一高风险国别；周期、客户集中与无在手订单进 L 分子与 \(p_k\)。**CAPM 粗筛**：5 年周频 β 1.90（对 SPY，2021-10 → 2026-10）→ 4.0% + 1.90 × 4.5% = **12.6%**，与篮子差 2.6pp（< 3pp）。**升档触发**：单一客户 ≥ 50% 或前两大 ≥ 70% → 篮 7 | active | FY2025 10-K 客户集中度；yfinance 周线 | `r_perp`；`check_r` |
# | A10 | **留存去向审计（valuation-rules「留存去向审计」2026-09-18）→ 完整式 Gordon + D 桶闭合项，k = 0**。Step 0（Longbridge 年报 2016–2025）：资本开支 6.50 / 5.51 / 5.47 / 4.72 / 5.53 / 7.80 / 9.08 / 7.49 / 7.44 / 9.05 亿美元，折旧（2022–25）6.13 / 6.32 / 5.95 / 6.42 亿 → **capex 年年 > 折旧**；NPPE 25.6 → 39.6 亿连升（NPPE / 权益 0.89）；净债 9.25 亿 → −3.25 亿；现金及短投 5.5 → 19.9 亿。Step 1 分桶（2021–25 累计净利约 25.0 亿、分红约 4.3 亿、留存约 20.7 亿）：E 桶（NPPE 净增约 12.5 亿，约 60%，产能随收入长）+ A / B 桶（净债改善约 7.9 亿，约 40%，还债与堆现金）；2026–28 年 **D 桶**（亚利桑那一期：2025-09 开工、2027 年装机、2028 年投产，窗口终点 2028 年末；窗口后触发 = 资本开支回落到 ≤ 1.5 × 折旧或公司宣布二期——**二期已于 2026-09-08 宣布，触发**，复核结论见本行末）。Step 2–3：NPPE 上升 → \(1/(r-g)\) 与 \(g=0\)+\(1/r\) 均不许 → **完整式**，\(b=g_2/ROE\)。**D 桶处理**：一期利润不在 FY27 分子里（2028 年才投产）；它的收入已作期权份数的一部分（A16），故不按「已花 × ROE/r」加回（双算防线）；未投产资本按 \((ROIC_{proj}/r-1)\) 罚：一期资本 = 原两期 70 亿的一半 **35 亿（推算；2026-10-28 复核维持，见本行末）** − 投资税收抵免 **10 亿**（两期约 20 亿的一半，推算）− CHIPS 补助 **4 亿** = 净 21 亿；稳态 ROIC = 10 亿收入 × (毛利率 30% − 费用率 6.26%) × (1 − 21%) ÷ 21 亿 = **8.93%**（管理层满产口径，取稳态不取首年）→ 罚 (0.893 − 1) × 21 亿 = **−2.25 亿 = −0.90/股**。已花部分按规则不应罚，此处把一期全额当未花，是偏保守的上界（已花金额 2026Q3 10-Q 仍未披露，`待补`）。**二期复核（2026-10-28）**：2026-09-08 园区扩为两期约 120 亿美元——一期洁净室 3.3 万平方米（规模未变，2027 年底完工、大客户约 2028 年底放量），二期 6 万平方米（2027 年底开工、2029 年底完工）。① 一期资本维持 35 亿：一期面积未变，按面积分摊 120 亿（42.6 亿）会把二期的单价摊回一期；按面积分摊且满产收入仍 10 亿 → −3.07/股，按面积分摊且收入同比例放大 → −1.44/股（只作对照）。② 二期**不进锚点、`待补`**：公司未披露二期收入 / 利润率；套一期单位经济粗估 +1.15/股（按 28.6% 比例拿到投资税收抵免）至 −7.73/股（拿不到；先进制造投资抵免要求 2026 年底前开工，二期 2027 年底才开工，资格未核实）；二期单位经济或 2027 资本开支指引（2027-02）披露后进锚点。③ **逐年现金流对照**（不进锚点）：一期按 2028 / 2029 / 2030 年 25% / 60% / 100% 爬坡、满产毛利率 30%（折旧后）、费用率与税同上、设备 6 年按原价重置、厂房 25 年后重建（均无补助）、r 10% 折现 → +2.12/股（毛利率 33% → +2.94；满产后年增 2% → +3.73；毛利率 25% → +0.77；无任何补助与抵免 → −3.49）；与现行 −0.90 的差来自会计折旧先扣而厂房重置在 25 年后——稳态 ROIC 口径对长寿命资产偏严；改用逐年现金流属规则层修订，待另议（厂房 / 设备 6:4 拆分、寿命为推算）。④ **客户预付款 `待补`**：合同负债 547.6M（2025 年末 390.8M）、相关备用信用证 200M；英伟达亚利桑那预付 15 亿 + 韩国 13 亿产能协议（条款未披露）；是否按零息客户融资抵减项目净资本，待条款披露后定。**k**：原 k_L / k_M / k_H = 0 乘在整个核心经营价值上，2026-10-16 框架纠正按规则去掉（乘错对象，A18），锚点不受影响；D 桶罚项是具名项目，保留。L 档 ROE 11.4% 落病态区，`check_branch` 幅度：模型派息 47.6% vs 实付 30.8%，差 16.8pp（< 20pp）通过。「禁止形态」七条逐条未命中 | active | Longbridge `financial-report --report af` 2026-10-08；yfinance 现金流量表；投资者日 8-K；2026Q2 电话会；亚利桑那二期公告 2026-09-08；2026Q3 10-Q 与电话会 | 倍数形式；`az_*`；`k_*`；A6 披露行 |
# | A11 | **杠杆门未触发**：净债 292.2M（2026-09-30）÷ TTM EBITDA 约 1,450M（按公司披露总债务 / EBITDA 1.7× 推得）= **约 0.20**；利息 / EBIT = TTM 利息支出约 70M ÷ TTM 营业利润 709.9M（2025Q4 185.0 + 2026Q1–Q3 100.3 / 199.9 / 224.7）= **约 10%**（< 1/3）；2025-12-31 读数为 0.11 / 16.1%。2027 年资本开支再升、自由现金流预计为负，净债会继续上升，下季复算。**可转债归类**：11.5 亿美元 0% 2031 年可转债，转股价约 67.99，深度价内门槛 = 67.99 × 1.3 = **88.39**——股价回到该价之上 → 改算股（按稀释后股数 + 不扣本金）并重跑本门；当前按债口径计入净债。两口径并列（每股价值取较低者）：债口径 L/M/H 21.08 / 34.11 / 53.88；稀释口径（不扣 11.5 亿本金、股数 + 1,691 万）粗算约 24.1 / 36.3 / 54.8，三档均更高，故债口径胜出。capped call（上限价未在摘录中披露）不计 | active | 2026Q3 10-Q 与 8-K；FY2025 10-K | 无 |
# | A12 | **③ 护栏：M 倍数高于自身同等盈利月份带，不出带；带不作上限 → 对账门**。同等盈利月份（TTM GAAP EPS 落在 2.81 ± 12% 即 2.47–3.15）：2022-02 → 2022-10、2023-02 → 2023-07 共 **15 个月**，月度 PE 5.48×（2022-07）– 11.51×（2023-07），中位 7.77×（2026-10-28 M 分子 2.776 的 ±12% 为 2.44–3.11，与原窗口基本重合，带沿用、未重抽）。M 今天的经营倍数 13.35× > 带上沿 → ③（M 低于带下沿）不触发。**带有效性**：那几个月的增长预期代理 = 其后两年实测 EPS（FY2022 3.11 → FY2024 1.43）年复合 **−32%**，现模型 g2 6%、FY26 → FY27 +11%；当时 ROE 23.2%（FY2022），现模型 M 13.1%——带印在「周期顶 + 预期下行」状态，**不作上限**（市场当时为随后的腰斩定价，不是今天的世界）。对账门（2026-10-28，M 37.08 → 34.11，−8%，< 25% 不触发纠正对账门；坐标照印）：② \(E_M/r\) + 闭合项 = **25.03**；③ 股息尺 0.334 ÷ (r − g) = 8.35（派息低，只印）；④ 同等盈利月份带上沿 11.51× × 核心 2.711 + 闭合项 = **29.13**；⑤ **同业同尺同日** 力成 / 日月光 Gordon 18.65 / 20.33×（京元 19.99× 在内，2026-10-08 读数）× 核心 2.711 + 闭合项 = **48.48–53.04**；⑥ 资产口径 BPS 19.35 × 自身 5 年 PB 低点 0.885 = **17.13**。M 34.11 落在坐标包络 [17.13, 53.04] 内、位于历史坐标与同业坐标之间 → 不 BLOCKED。中性带 [27.60, 44.00) 换算：TTM EPS 2.48 → 11.1–17.7×；FY26 共识 2.504 → 11.0–17.6×；FY27 共识 2.776 → 9.9–15.9× | active | yfinance 月线 2022–2023；Longbridge 季度 EPS；`eval/AMKR.US.py` | 护栏披露 |
# | A13 | **AI 封装是 M 的增量来源，不是 M 的主体**（属性 B）：计算业务 2026Q2 占收入 22% → **2026Q3 26%**（约 5.18 亿，QoQ +25%、YoY +37%，低于此前「近 +30%」，管理层归因于 300 多道工序的 HDFO 爬坡节奏、非供给受限）；超大规模客户 HDFO CPU 项目 Q3 开始放量，两个网络 / 数据中心 2.5D 项目 Q4 上线；Q4 计算指引环比增低双位数，管理层称 2027 年再增 30% 以上；英伟达 2026-10-21 签 13 亿美元韩国产能协议（中介层产能到 2028 年底扩 3 倍以上）。2.5D 收入仍未单列；共封装光学三个开发项目「生命周期各约十亿美元级」，无收入。**新增风险（单一来源）**：亚洲券商 2026-10-22 称英伟达把 Vera CPU 封装从 Amkor / 台积电部分分散到日月光——若即本票旗舰 HDFO CPU 项目，计算业务 2027 增速会低于管理层口径。**证伪触发器**：计算业务占比连续两季回落、或台积电 / 英伟达合作的 2.5D 量产推迟。**升级门槛**：公司单列 2.5D / HDFO / 共封装光学收入，且该部分毛利率可查证 > 25% → 回对话评估拆腿（AI 封装腿按亚利桑那单位经济） | active | 2026Q2 / Q3 新闻稿与电话会；投资者日 8-K；Wisburg 97746（摩根大通 2026-07-28）、111133（GTC 柏林后 2026-10-22）、112053（美银 2026-10-28） | M / H 分子；`stretched` 解释 |
# | A14 | **通信业务（苹果）是 L 档的主要风险**：通信占收入 2026Q2 42% → Q3 37%（约 7.37 亿，QoQ −8%、YoY 约 −27%：系统级封装迁越南、内存短缺、备货节奏）；Q4 指引通信环比再降高个位数（约 6.7–6.8 亿，对 2025Q4 9.25 亿 YoY 约 −27%）；苹果 29.8%（FY2025）。同期总收入 YoY 持平——计算（+37%）与汽车工业（+37%）补上了通信的缺口。**证伪触发器（2026-10-28 改写）**：总收入连续两个季度同比转负（计算与汽车的增量补不上通信），或苹果占比跌破 25% 而计算业务占比未升到 30% 以上。原触发器「2026Q4 通信收入同比下降 > 10%」按 Q4 指引必然触发，但下滑来自写入时已知的产线迁移与内存短缺，触发不携带新信息，故改写（原条件保留于此备查） | active | 2026Q2 电话会（Wisburg 97831）；摩根大通 2026-07-28；2026Q3 8-K 与电话会；2025Q4 8-K | L 分子 |
# | A15 | **2028 年管理层目标低于 FY27 共识**：投资者日 2028 EPS 2.50 ± 0.25 < FY27 共识均值 2.776，原因是亚利桑那一期投产初期折旧与低开工（电话会：2028 目标已计入该拖累）。本框架不把它当 FY28 分子（单源公司目标），D 桶罚项（A10）已从回报侧计入一期资本；**证伪 / 复核**：卖方 FY28 共识出现后若均值低于 FY27 > 10% → 同世界门复核（A7）。2026-10-28 读数：美银 FY28 3.47（> FY27 2.75）、另有报道称一致预期约 3.30，方向上行，同世界门不翻转 | active | 投资者日 8-K 2026-05-21；2026Q2 电话会；Wisburg 112053（美银 2026-10-28） | A7 同世界门；期权时点 |
# | A16 | **期权 = 管理层 2030 收入目标超出 FY27 共识上沿的部分（valuation-rules「未建模期权」2026-10-03）**：(`mgmt_rev_2030` 11,000 − `rev_fy27_h` 9,170.8) = **1,829.2M** 收入 × FY27 共识核心净利率 **7.87%**（核心 EPS 均值 2.711 × 249.526M ÷ 收入均值 8,593.1M）= 每股 +0.577 × H 档回报路径**在兑现年 2030** 的倍数（g2 6%、ROE_H 18.1% 到 FY27、2031 落到自身周期稳态 15.1%——2030 年时回落已走四分之三、回报约 15.9%，r 10%，折 τ 0.25，A18）14.73× ÷ 1.1³（2030 → FY27）= **6.38**（2026-10-28 换共识与 τ 前为 6.83）；2030 收入目标于 2026-09 高盛 Communacopia 大会重申（Wisburg 104957）。**2026-10-19 框架纠正（期权在兑现年按当年的回报路径估值）**：原用 FY27 年初的倍数（现 14.53×），等于把 2030 年的增量按 2027 年的回报定价（→ 6.89）；改为在 2030 年按同一条日历路径重算（−1.0%）。同日稳态按序取改为自身周期 15.1%（原封测兜底 15%，A18），6.80 → 6.83。增量是公司已在规模出货的封测业务（计算业务 2026Q2 已占收入 22%，A13），属同一环节，不另起高回报期。开关几乎不动价格：2031 年后两条路径都在稳态 15.1%，差别只在 2030 年一年的回报（16.0% 对 18.6%），价值主要落在「增量利润按稳态 15.1%、g2 6% 永续」上。扣除口径：减 H 档已含的 FY27 共识**上沿**收入。**交叉（不进公式）**：按管理层 EPS 目标 5.0 → (4.935 − 3.735) × 14.73 ÷ 1.1³ = 13.28（含管理层 22% 毛利率，单源）。管理层无历史长期目标的兑现纪录可查，不设推迟敏感性。\(p_L/p_M/p_H\) = **0 / 0.25 / 1.0**（\(p_M\) 无概率锚·拍值，属性 E） | active | 投资者日 8-K 2026-05-21；yfinance 收入共识 2026-10-28；Wisburg 104957（高盛 2026-09-10） | `mgmt_rev_2030`、`rev_fy27_m` / `rev_fy27_h`、`t_opt` / `t_num`、`mgmt_eps_2030`；表3 |
# | A17 | **卖方 TP 只进差额表，不定锚**：yfinance 2026-10-28（财报后）TP 均值 66.0 / 中位 66.5 / 41–92（2026-10-08 为 76.4 / 73.5 / 65–92）；财报后 Needham 90 → 55（买入，板块倍数收缩、手机与消费转弱）、摩根士丹利 70 → 63（中性）、B. Riley 46 → 41（中性；10-20 已从 65 降到 46）、美银维持 70（买入，FY28 EPS 3.47 × 20×，原 21×；其长期交易区间中位 14×）；摩根大通 85（2027-12，FY27 EPS 3.47 × 25×，2026-07-28）。同一把尺反解（扣闭合项后 ÷ 核心 M 2.711，ROE 13.1%）：TP 中位 66.5 → 隐含永续 g **8.7%**，最低 41 → 7.2%、最高 92 → 9.2%（同走 A18 三段与时点对齐、账面不随 g 重滚）——卖方把增长塞进倍数、超过 \(G_{cap}\)；财报后的下调主要在倍数，FY27 盈利预测只降 1%。**差额表（H 之上未建模项）**：① FY28 以后的增长——无 ≥2 家带区间共识年（A2 待核实）；2030 目标已落期权 6.38；② AI 封装按亚利桑那单位经济（毛利率 30%+）永续化——A13 升级门槛未满足；③ 共封装光学——无收入；④ 街倍数 20–25×（美银 / 摩根大通）↔ 永续 g 8.7%——市场判断，不入 g | active | yfinance / Wisburg / MarketBeat 2026-10-28 | `stretched` 解释 |
# | A18 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④，2026-10-16 框架纠正）**。① **超额现金**：不单列（净债 292.2M（2026-09-30；原 122.7M），无超额现金行；净债已按面值作闭合项，A5）；归母比例：少数股东 36.5M 不进经营权益，分子即归母，不另折；**增长期资金缺口**：亚利桑那一期 2028 年投产，产出落在分子年 FY27 之后，按规则不从主锚点扣——它的回报低于 r 的部分已由 D 桶闭合项 −0.90/股按 未投 × (1 − ROIC/r) 扣过（A10），收入进期权份数（A16），不重复。② **稳态回报三段**：可见年 FY27 用前瞻回报 10.5 / 13.1 / 18.1%（A6；2026-10-28 前为 11.4 / 14.0 / 18.6%）→ 维持到 **Y1 = FY2027**（默认路径：可见年末；本票不挂需求轴）→ 线性回落到 **Y2 = 2031** → 稳态永续。**门槛「中」→ 回落 4 年**，依据：先进封装（2.5D、高密度扇出）的客户认证 1–2 年；新厂建设约 2–3 年；台积电、日月光、中国大陆封测厂都在扩先进封装，份额可在几年内被分走；单位产能投资高。**稳态 15.1% = 自身周期（按序取，2026-10-19 框架纠正）**：Amkor 收入与经营利润的谷底年是 FY2019（收入 40.5 亿、经营利润 2.33 亿）与 FY2024（63.2 亿、4.38 亿），最近一轮完整谷到谷 FY2019–FY2024 的投入资本口径经营回报（税后经营利润 ÷ 年初（权益含少数股东 + 有息负债 + 租赁 + 税后养老金缺口 − 现金及短投））= 7.0 / 14.8 / 24.0 / 24.9 / 9.9 / 9.7%，均值 **15.1%**（SEC XBRL 10-K；对照：账面 ROE 同期均值 15.9%，FY2016–25 十年均值 13.4%）。原取封测生意模式兜底 15%（用户 2026-10-16 定的是兜底表数值），理由是「自身周期层与前瞻不同公式」——按新规则这不是弃用自身的理由，自身周期可用即取自身；兜底 15% 与成熟同业日月光 14.1%（近 5 年收入 +0.5%）只作对照、不进值。三档按「≤ 该档前瞻」封顶：L / M 前瞻 10.5% / 13.1% 本就低于 15.1%，路径不起作用；只有 H 档 18.1% 回落。不属商品腿豁免。g2 6% 是同业反解截顶值，按同一路径重解只会更高，仍被截住，不动。③ **时点对齐**：Gordon 给的是 FY27 年初（2027-01-01，RONIC 分母时点）的价值；今天 = \(V_{op}/(1+r)^{\tau}\) + 窗口可分配利润，τ = 估值基准日 → 2027-01-01（2026-10-28 起基准日 2026-09-30，τ = 0.25 年；原 2026-06-30、0.5 年；「FY27 = 当前财年 +1 不折现」已撤回）；窗口 = FY26 尚未入账核心利润（第四季度 0.698/股）× (1 − \(b_1\))，按 τ/2 折 → **0.30 / 0.37 / 0.46/股**（三档为正，无截断）；期权的 H 档倍数同走三段并折 τ。④ **k**：原 k_L / k_M / k_H 乘在整个核心经营价值上，属乘错对象，去掉（原值都是 0，锚点不受影响）；D 桶罚项是具名项目，保留。影响：L / M / H 25.69 / 38.07 / 60.40 → **25.14 / 37.08 / 52.40**（M −2.6%：全部来自时点对齐；H −13.3%：三段 −10.7%、时点对齐另计），\(V_{opt}\) 8.04 → 6.87（2026-10-19 改在兑现年按当年回报路径估值 → 6.80，A16），未触发纠正对账门；2026-10-19 稳态 15% → 15.1%（自身周期）：H 52.40 → **52.60**、\(V_{opt}\) 6.80 → **6.83**，L / M 不动；2026-10-28 财报后换共识、资产负债表与 τ → **21.08 / 34.11 / 53.88**、\(V_{opt}\) **6.38**（§4） | active | valuation-rules「经营价值与超额现金」；Longbridge 年报（日月光穿越周期）；2026Q2 / Q3 10-Q；投资者日 8-K；对话 2026-10-16 | `tau`、`y1`、`y2`、`rs_steady`；删 `k_*`；锚点、\(V_{opt}\) |
# 原框架历史，本次迁移没有新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-10-28
# touched: [A2, A3, A5, A6, A7, A8, A10, A11, A12, A13, A14, A15, A16, A17, A18, Inputs, Outputs, eval]
# - **事件**：2026Q3 财报（2026-10-26 盘后）与 10-Q（2026-10-27）。收入 19.91 亿（指引 19.5–20.5 亿、一致预期 20.39 亿）、毛利率 18.3%（低于指引下沿 18.5%；熊本地震与汇率约 −0.6pp）、EPS 0.76（预期 0.784）；Q4 指引收入 19–20 亿、毛利率 18–19%、EPS 0.65–0.75（预期 0.77）。2026-10-26 收盘 36.81（−6.3%），盘后约 38.3。财报后 Needham 90 → 55、摩根士丹利 70 → 63、B. Riley 46 → 41，美银维持 70。
# - **另补一项此前漏记的事件**：2026-09-08 亚利桑那园区扩为两期约 120 亿美元（框架 2026-10-19 版仍按 70 亿），触发 A10「公司宣布二期」复核条件。
# - **假设状态**：全部维持 `active`。A13（计算业务 26%、QoQ +25%）基本兑现，补「英伟达把部分 Vera CPU 封装分给日月光」的单一来源风险；A14 原证伪触发器「2026Q4 通信 YoY < −10%」按指引必然触发但不携带新信息，改写为「总收入连续两季 YoY 转负，或苹果 < 25% 而计算未升到 30%」；A16 2030 收入目标已于 2026-09 重申；A2 FY28 出现卖方点值（美银 3.47），无 ≥2 家带区间，待核实。
# - **输入**：FY27 共识 2.32 / 2.806 / 3.69 → 2.25 / 2.776 / 3.80；FY26 2.572 → 2.504；估值基准日 2026-06-30 → 2026-09-30（τ 0.5 → 0.25，前三季度 EPS 1.79 入账）；净债 122.7M → 292.2M；净利息 3.201M → 4.812M / 季；FY27 收入共识均值 / 上沿 8,640.7 / 9,025 → 8,593.1 / 9,170.8。亚利桑那一期资本维持 35 亿推算，二期与客户预付款列 `待补`，逐年现金流对照只披露。
# - **锚点**：L / M / H 25.14 / 37.08 / 52.60 → **21.08 / 34.11 / 53.88**；\(V_{opt}\) 6.83 → **6.38**。M −2.97 拆分：换共识 −0.74、Q3 入账与 τ ≈ 0、净债与利息 −2.24（闭合项 −0.68，经营账面扩大使 M 档 ROE 14.0% → 13.1%）。L 跌 16%、H 升 2% 来自卖方 FY27 区间两端外扩。稳态回报 15.1%、Y1 / Y2 = 2027 / 2031、g2 6% 未动（2026-10-16 / 10-19 已认可）。
# - **待办**：① 框架纠正——经营账面含亚利桑那已投入但 FY27 不产出的资本，与 D 桶罚项双计（A6 / A10）；② 规则层——新厂项目改按逐年现金流估值、客户预付款是否抵减净资本，需另议并经用户同意改 skill；③ FY28 共识 ≥2 家带区间核实（A2）。
HISTORICAL_PARTIAL_FINGERPRINT = '22e8758bd16001148d4b4e04110d615810b3b9d21db0e24cdf14bb79c42f594f'

INPUTS = {
    # 稀释加权股数；2026Q3 10-Q 249,526 千股（A4）; 来源：2026-09-30
    'shares': 2.49526e8,
    # 在外流通股 248.0M（2026-07-21）；只用于资产口径坐标（A12）; 来源：2026-07-21
    'shares_out': 2.48e8,
    # Amkor 股东权益 $M（不含少数股东 36.5）；经营权益 = equity − net_cash = 5,091.9 是 ROE 的起点（A5 / A6）; 来源：2026-09-30
    'equity': 4799.7,
    # 现金 1,603.0 + 短期投资 773.2；受限现金 201.7（建设保证金等）不计（A5）; 来源：2026-09-30
    'cash': 2376.2,
    # 有息债务（流动 149.5 + 长期 2,317.7，含 0% 2031 可转债 1,150 按债口径，A11）; 来源：2026-09-30
    'debt': 2467.2,
    # 融资租赁负债（10-Q「total long-term finance lease liabilities」117.7，含一年内到期部分的读法；2025-12-31 为 105.0）; 来源：2026-09-30
    'lease_fin': 117.7,
    # 经营租赁负债（流动 21.3 + 非流动 62.2），对齐 `FORM.US` A5; 来源：2026-09-30
    'lease_op': 83.5,
    # cash − debt − lease_fin − lease_op；负值 = 净债；闭合项按 `shares` 折每股（A5）；客户预付款形成的合同负债 547.6 不计入（A10 待补）; 来源：2026-09-30
    'net_cash': -292.2,
    # 2026Q3 净利息收入 $M（利息收入 22.728 − 利息支出 17.916）；× 4 × (1 − tax) ÷ shares = 剔除的税后利息/股（A5）; 来源：2026-09-30
    'int_q': 4.812,
    # FY2025 有效税率（yfinance）；只用于利息税后; 来源：2025-12-31
    'tax': 0.154,
    # FY26 共识 EPS 均值（8 家，财报后）；A6 账面滚动；同世界门; 来源：2026-10-28
    'eps_fy26_m': 2.5039,
    # FY26 前三季度实际 EPS（Q1 0.33 + Q2 0.70 + Q3 0.76）; 来源：2026-09-30
    'eps_ytd_26': 1.79,
    # FY27 共识 EPS 下沿（9 家，GAAP，财报后）= L 分子（A2）; 来源：2026-10-28
    'eps_fy27_l': 2.25,
    # FY27 共识 EPS 均值 = M 分子（A2）; 来源：2026-10-28
    'eps_fy27_m': 2.77583,
    # FY27 共识 EPS 上沿 = H 分子（A2）; 来源：2026-10-28
    'eps_fy27_h': 3.80,
    # 近三年实付派息率（FY2023–25 现金分红 335.2M ÷ 净利 1,087.7M）；进 `check_branch` 与 A6 披露行; 来源：2025-12-31
    'payout_3y': 0.308,
    # 永续折现率 = 篮 4 常规经营 10%：封测按件议价、盈利随客户出货量与开工率、不是商品价函数；苹果 29.8% + 高通 11.1% 未达篮 7 阈值（A9）；`check_r`; 来源：2026-10-08
    'r_perp': 0.10,
    # 永续增速 = 同业反解 · 截顶（台湾封测簇中位 6.19% → cap = min(6%, r−4%) = 6%；A7）；`check_g_cap`；三档共用; 来源：2026-10-08
    'g2': 0.06,
    # 同业簇反解中位（日月光 7.01 / 京元 6.19 / 力成 5.43）；记录与证伪点（A7）; 来源：2026-10-08
    'g_peer_median': 0.0619,
    # 同业簇低端（力成）；证据区间下沿，只进敏感性（A8）; 来源：2026-10-08
    'g_peer_low': 0.0543,
    # 亚利桑那一期满产收入 $M（投资者日「约 10 亿美元 / 期」）（A10）; 来源：2026-05-21
    'az_rev': 1000,
    # 一期满产毛利率下限（投资者日「> 30%」）（A10）; 来源：2026-05-21
    'az_gm': 0.30,
    # 公司费用率 = 2026Q2（毛利 318.6 − 营业利润 199.9）÷ 收入 1,898.0（A10）; 来源：2026-06-30
    'opex_ratio': 0.0626,
    # 美国联邦法定税率（一期在美国）（A10）; 来源：2026-05-21
    'az_tax': 0.21,
    # 一期资本 $M = 两期合计约 7,000 的一半（推算；公司未单列）（A10）; 来源：2026-05-21
    'az_capex': 3500,
    # 一期投资税收抵免 $M = 两期约 2,000 的一半（推算）（A10）; 来源：2026-05-21
    'az_itc': 1000,
    # CHIPS 法案补助约 $400M（投资者日）（A10）; 来源：2026-05-21
    'az_grant': 400,
    # 管理层 2030 目标收入 $M（「约 110 亿以上」取下沿）；期权份数 = 此值 − `rev_fy27_h`（A16）; 来源：2026-05-21
    'mgmt_rev_2030': 11000,
    # 管理层 2030 目标 EPS；只作期权交叉，不进公式（A16）; 来源：2026-05-21
    'mgmt_eps_2030': 5.0,
    # FY27 共识收入均值 $M（11 家，财报后）；期权单位经济的分母（A16）; 来源：2026-10-28
    'rev_fy27_m': 8593.1,
    # FY27 共识收入上沿 $M；期权份数从此之上起数（A16）; 来源：2026-10-28
    'rev_fy27_h': 9170.8,
    # 兑现年 = 管理层目标年（A16）; 来源：2026-05-21
    't_opt': 2030,
    # 分子年 FY27（A2）; 来源：2026-10-08
    't_num': 2027,
    # 自身 5 年实测 PB 低点（2024-12-31 每股净资产 16.82 × 其后最低收盘 14.88，2025-04-04）；只作对账门坐标 ⑥（A12）; 来源：2025-04-04
    'pb_low': 0.885,
    # 同等盈利月份带下沿（2022-07 月内最低收盘 ÷ TTM EPS 2.82）；③ 护栏（A12）; 来源：2022-07-29
    'band_pe_min': 5.48,
    # 同等盈利月份带上沿（2023-07 月内最高收盘 ÷ TTM EPS 2.59）；对账门坐标 ④（A12）; 来源：2023-07-31
    'band_pe_max': 11.51,
    # 时点对齐年数 = 估值基准日 2026-09-30（2026Q3 资产负债表日）→ 分子年 FY27 年初 2027-01-01；Gordon 经营价值按 `r_perp` 折 τ、窗口可分配利润折 τ/2；τ 同时是 FY26 尚未入账的年份比例，窗口剔利息按 τ 计（A18）; 来源：2026-10-28
    'tau': 0.25,
    # 高回报期止点 Y1 = 可见年末 FY27（默认路径，不挂需求轴；A18）; 来源：2026-10-16
    'y1': 2027,
    # 稳态起点 Y2 = Y1 + 4（进入门槛「中」：先进封装客户认证 1–2 年、新厂 2–3 年、台积电 / 日月光 / 大陆封测厂都在扩先进封装；A18）; 来源：2026-10-16
    'y2': 2031,
    # 稳态回报 = **自身周期** FY2019–FY2024（收入与经营利润两个谷底年之间，含谷）投入资本口径经营回报均值 15.1%（税后经营利润 ÷ 年初（权益含少数股东 + 有息负债 + 租赁 + 税后养老金缺口 − 现金及短投））；按序取（2026-10-19）：自身周期可用 → 取自身，同业（日月光 14.1%）与封测兜底 15%（用户 2026-10-16 定的兜底表值）只作对照；三档按「≤ 该档前瞻」封顶（A18）; 来源：SEC XBRL 10-K，2026-10-19
    'rs_steady': 0.151,
}
BASKETS = {"r_perp": 4}  # priced per contract; A9
REQUIRED = frozenset(INPUTS)

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


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A9: one leg, r is the basket's value; the basket is named in the Inputs source cell.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A9)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    # A7: g2 is the peer median truncated to g_cap(r); the cluster's low end is the evidence range.
    cap = g_cap(inp["r_perp"])
    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if abs(inp["g2"] - min(inp["g_peer_median"], cap)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {cap:.3f}) — A7")
    if not inp["g_peer_low"] <= inp["g2"]:
        errs.append("g_peer_low must not exceed g2 (A8 evidence range)")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {inp['r_perp'] - inp['g2']:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # 裁决顺序 ④ 同世界门 (A7): FY26 -> FY27 consensus up, so a g2 >= 0 source is admissible.
    if not inp["eps_fy26_m"] < inp["eps_fy27_m"]:
        errs.append("FY26 consensus not below FY27: the same-world gate for g2 >= 0 no longer holds (A7)")

    errs += ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])

    # A5 / A11: the closing item is what the book is grossed up by.
    nc = inp["cash"] - inp["debt"] - inp["lease_fin"] - inp["lease_op"]
    if abs(nc - inp["net_cash"]) > 0.05:
        errs.append(f"net_cash {inp['net_cash']} != cash - debt - leases {nc:.1f} (A5)")

    # A18: the steady-state-return path and the time alignment.
    if not int(inp["t_num"]) <= int(inp["y1"]) < int(inp["y2"]):
        errs.append("need t_num <= y1 < y2 (A18)")
    if not inp["r_perp"] <= inp["rs_steady"]:
        errs.append("rs_steady must not fall below r (A18)")
    if not 0.0 <= inp["tau"] < 2.0:
        errs.append(f"tau {inp['tau']} out of range (A18)")
    if any(k in inp for k in ("k_l", "k_m", "k_h")):
        errs.append("k_* rows present — the k on the whole operating value was dropped (A18)")

    # A10: Arizona capital nets positive after credits and grants.
    if not inp["az_capex"] > inp["az_itc"] + inp["az_grant"] > 0:
        errs.append("Arizona net capital must be positive (A10)")

    # A16: the option counts only what the target adds above consensus already in H.
    if not inp["mgmt_rev_2030"] > inp["rev_fy27_h"] >= inp["rev_fy27_m"] > 0:
        errs.append("mgmt_rev_2030 must exceed FY27 consensus revenue (H >= M > 0) (A16)")
    if not inp["t_opt"] > inp["t_num"]:
        errs.append("t_opt must fall after the numerator year t_num (A16)")

    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    return errs



def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp, ('t_num', 'y1', 'y2', 't_opt'))
    baskets = BASKETS
    errors = sanity_checks(inp, baskets)
    r, g2 = inp["r_perp"], inp["g2"]
    cap = g_cap(r)
    street = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}
    tau, t0 = inp["tau"], int(inp["t_num"])
    y1, y2, rs = int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]

    # ---- Step 1: core EPS with the after-tax net interest stripped (A5) ----
    int_ps = inp["int_q"] * 4 * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    core = {t: street[t] - int_ps for t in TIERS}

    # ---- Step 2: closing items — net debt and the Arizona D-bucket charge (A5, A10) ----
    cash_ps = inp["net_cash"] * MILLION / inp["shares"]
    az_capital = inp["az_capex"] - inp["az_itc"] - inp["az_grant"]
    az_roic = inp["az_rev"] * (inp["az_gm"] - inp["opex_ratio"]) * (1.0 - inp["az_tax"]) / az_capital
    az_ps = (az_roic / r - 1.0) * az_capital * MILLION / inp["shares"]
    closing = cash_ps + az_ps

    # ---- Step 3-5: tier ROE on the FY27 opening operating book, Gordon multiple ----
    equity_op = inp["equity"] - inp["net_cash"]
    bps0 = equity_op * MILLION / inp["shares"]
    # tau is also the share of FY26 still unbooked (valuation date -> year end), so the
    # interest stripped from the unbooked part scales with it (2026-10-28: Q3 booked, tau 0.25).
    n_unbooked = inp["eps_fy26_m"] - inp["eps_ytd_26"] - int_ps * tau

    def opening_bps(core_x: float, g: float) -> float:
        share = g * n_unbooked / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps0 / (1.0 - share)

    def gordon_today(g: float, roe_x: float, rr: float) -> float:
        """Path Gordon at the start of FY27 folded back tau years (no window)."""
        return path_pe(g, roe_x, rr, t0, y1, y2, rs) * (1.0 + rr) ** -tau

    def window(g: float, roe_x: float, rr: float) -> float:
        """FY26 unbooked core EPS x (1 - b1), floored at 0, at tau/2 (A18)."""
        return max(n_unbooked * (1.0 - g / roe_x), 0.0) * (1.0 + rr) ** -(tau / 2)

    def deck(g: float, rr: float) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
        bps_ = {t: opening_bps(core[t], g) for t in TIERS}
        roe_ = {t: core[t] / bps_[t] for t in TIERS}
        # today's operating multiple: path Gordon folded by tau + window per unit of core EPS
        pe_ = {t: gordon_today(g, roe_[t], rr) + window(g, roe_[t], rr) / core[t] for t in TIERS}
        val = {t: core[t] * pe_[t] + closing for t in TIERS}
        return bps_, roe_, pe_, val

    bps, roe, pes, scen = deck(g2, r)
    win = {t: window(g2, roe[t], r) for t in TIERS}
    b1 = {t: g2 / roe[t] for t in TIERS}
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * n_unbooked for t in TIERS}  # disclosure only

    # Branch guard: the L tier sits in the 病态区 (ROE within 3pp of r); D bucket named (A10).
    for t in TIERS:
        errors += check_branch(g2, roe[t], r, inp["payout_3y"], f"branch {t}")

    L, M, H = scen["L"], scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        raise ValueError("; ".join(errors))

    # ---- A2e-2c flat ladder + decomposition ----
    if not (core["L"] < core["M"] < core["H"]):
        errors.append(f"numerator ladder broken: core EPS {core['L']:.3f}/{core['M']:.3f}/{core['H']:.3f}")
    flat = [core[t] * pes["M"] + closing for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    ex_close = {t: core[t] * pes[t] for t in TIERS}

    # ---- ③ guardrail (A12): M multiple vs the same-earnings band, and the reconciliation coordinates ----
    if pes["M"] < inp["band_pe_min"]:
        errors.append(f"③ 出带: PE_M {pes['M']:.2f}x below own same-earnings band floor {inp['band_pe_min']:g}x — run the ③ flow")
    e_over_r = core["M"] / r + closing
    band_hi = core["M"] * inp["band_pe_max"] + closing
    peer_lo, peer_hi = (core["M"] * pe + closing for pe in PEER_PE_SAME_RULER)
    bvps = inp["equity"] * MILLION / inp["shares_out"]
    asset_coord = inp["pb_low"] * bvps
    coords = [e_over_r, band_hi, peer_lo, peer_hi, asset_coord]
    if not min(coords) * 0.8 <= M <= max(coords) * 1.2:
        errors.append(f"对账门: M {M:.2f} outside every coordinate by >20% {coords}")

    # ---- g2 leverage: -1pp and the evidence range's low end, L/M/H only ----
    _, _, _, lo = deck(g2 - 0.01, r)
    _, _, _, ev = deck(inp["g_peer_low"], r)

    # ---- Option ceiling and zone+V (probabilities only here) ----
    d_rev = inp["mgmt_rev_2030"] - inp["rev_fy27_h"]
    core_margin = core["M"] * inp["shares"] / (inp["rev_fy27_m"] * MILLION)
    d_core = d_rev * MILLION * core_margin / inp["shares"]
    years = inp["t_opt"] - inp["t_num"]
    # A16 (2026-10-19): the option is valued in its realisation year on that year's return path --
    # the H path is calendar (Y1 2027 / Y2 2031), so by 2030 three quarters of the fall is done.
    # The increment is the same packaging business already shipping at scale, so no fresh period.
    # Was gordon_today (the FY27-start multiple), which priced 2030 earnings at 2027 returns.
    t_opt = int(inp["t_opt"])
    pe_opt = path_pe(g2, roe["H"], r, t_opt, y1, y2, rs) * (1.0 + r) ** -tau
    pe_opt_fy27 = gordon_today(g2, roe["H"], r)
    v_opt = d_core * pe_opt / (1.0 + r) ** years
    v_opt_fy27 = d_core * pe_opt_fy27 / (1.0 + r) ** years
    if pe_opt > pe_opt_fy27 + 1e-12:
        errors.append("option multiple at t_opt above the FY27-start multiple -- the fall cannot restart")
    A, B = cut_points(L, M, H)
    opt = tuple(anchor + p * v_opt for anchor, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    payout_gaps = {t: payout_gap(g2, roe[t], inp["payout_3y"]) for t in TIERS}
    no_az = [scen[t] - az_ps for t in TIERS]
    c30 = inp["mgmt_eps_2030"] - int_ps
    target_implied = {}
    for tp in (41.0, 66.5, 92.0):  # yfinance low / median / high, 2026-10-28
        target = (tp - closing) / core["M"]
        lo_g, hi_g = -0.30, r - 1e-4
        for _ in range(200):
            mid = (lo_g + hi_g) / 2
            v = gordon_today(mid, roe["M"], r) + window(mid, roe["M"], r) / core["M"]
            lo_g, hi_g = (mid, hi_g) if v < target else (lo_g, mid)
        target_implied[str(tp)] = (lo_g + hi_g) / 2

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1; the Arizona charge is held at the basket r.
    def band_rf(dr: float) -> tuple[float, float, float]:
        s = [core[t] * (gordon_today(g2, roe[t], r + dr) + window(g2, roe[t], r + dr) / core[t]) + closing for t in TIERS]
        return s[0], s[1], s[2]

    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    result = {
        "ticker": "AMKR.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-09-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-28', 'historical_framework_as_of': '2026-10-28',
        "anchors": scen, "candidate": None,
        "option": {"value": v_opt, "fractions": band(P_TIERS), "anchors": band(opt)},
        "cut_points": [A, B], "option_cut_points": [a2, b2],
        "street": street, "core": core, "int_ps": int_ps, "cash_ps": cash_ps,
        "az_capital": az_capital, "az_roic": az_roic, "az_ps": az_ps, "closing": closing,
        "equity_op": equity_op, "bps0": bps0, "n_unbooked": n_unbooked, "bps": bps,
        "roe": roe, "pes": pes, "win": win, "b1": b1, "excess_cash": excess_cash,
        "flat": flat, "ex_close": ex_close, "e_over_r": e_over_r, "band_hi": band_hi,
        "peer_lo": peer_lo, "peer_hi": peer_hi, "bvps": bvps, "asset_coord": asset_coord,
        "coords": coords, "lo": lo, "ev": ev, "d_rev": d_rev, "core_margin": core_margin,
        "d_core": d_core, "years": years, "pe_opt": pe_opt, "pe_opt_fy27": pe_opt_fy27,
        "v_opt_fy27": v_opt_fy27, "no_az": no_az, "c30": c30,
        "contrast": [deck(g2, rr)[3] for rr in (0.13, 0.15)],
        "payout_gaps": payout_gaps, "target_implied": target_implied,
        "parameters": {"discount": r, "growth": g2, "forward": roe,
                       "mature": {t: min(roe[t], max(rs, r)) for t in TIERS}},
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if r + dr <= g2:
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': r}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'baskets': BASKETS, 'option_weights': P_TIERS,
         'peer_multiples': PEER_PE_SAME_RULER, 'million': MILLION,
         'minimum_rate_gap': MIN_R_MINUS_G}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments'] = {'company': {'unit': 'USD_PER_SHARE', 'values': dict(result['anchors'])}}
    if result['option']['value'] >= 0:
        result['option']['value_unit'] = 'USD_PER_SHARE'
        result['option']['weights'] = result['option'].pop('fractions')
    else:
        result['option'] = {'status': 'unavailable', 'label': '管理层收入目标', 'anchors': None}
        result.pop('option_cut_points', None)
        result['option_unavailable_reason'] = 'incremental_revenue_below_existing_baseline'
    parameters = result['parameters']
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['growth'])},
        'forward_return': {'unit': 'RATIO', 'values': parameters['forward']},
        'steady_return': {'unit': 'RATIO', 'values': parameters['mature'], 'reference_value': INPUTS['rs_steady']},
    }
    result['review_flags'] = ['historical_arizona_capital_may_be_double_counted',
                              'historical_arizona_cashflow_comparison_incomplete']
    return result
