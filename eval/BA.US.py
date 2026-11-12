#!/usr/bin/env python3
"""BA valuation migrated without updating its financial inputs or judgments.

Inputs are USD millions, shares millions, except per-share prices and ratios.
The 2027/2028 EPS and EBIT are dated sell-side predictions, not actual results.
"""
from __future__ import annotations
from lib.gordon import (check_branch, check_g_cap, check_r, check_transition_years,
                        g_cap, perpetual_pe, recovery_two_stage_pe, two_stage_pe)
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

FORMULA_ID = "ba_unlevered_fy27_recovery_gordon_v1"
LISTING_CCY = "USD"
NUM_YEAR = 2027
# | A1 | 林奇主类 `turnaround` / 次类 `cyclical`：盈利从 2019 起的事故、停产、质量整改与罢工中恢复；股价主要定价「能否回到正常利润」 | active | 用户 2026-09-23 选定 | 题头；L 按转机档（共识下沿）|
# | A2 | **分子 = FY2027E core EPS 共识三点**（yfinance 21 家：2.4675 / 4.18992 / 6.80，2026-09-23）——这是 ≥2 家且带区间的最远年份（裁决顺序 ②）。FY2028 只有点估计（MarketScreener 共识：收入 1,235 亿、EBIT 97.6 亿、净利 71.3 亿、EPS 9.06、FCF 97.8 亿；杰富瑞 FCF 88 亿、FCF/股 10.46）→ 进 \(g_1\)（n = 1）不作分子。stockanalysis 网页片段给的 FY2028 EPS 区间 4.44–13.44 未能核到原页（付费墙），不采。**升级门槛**：FY2028 带区间共识（≥2 家、低 / 中 / 高）可核 → 分子换 FY2028（折现一年）、\(g_1\) 窗口关闭 | active | yfinance `earnings_estimate` 2026-09-23；marketscreener.com/quote/stock/BOEING-4816/finances 2026-09-23；Wisburg 98844 / 106312 | `eps27_*`、`ebit27_ms`、`ebit28_ms` |
# | A3 | **整公司尺**：三分部同归篮 4（不触发「归篮触发分腿」）；卖方两家都按整公司 FCF yield；BGS 盈利、BCA 亏损的结构只用于解释分子，不拆腿。A2c 命中 3 条（分部清晰、驱动不同、一块亏一块赚），但分腿要求的分部净资产不披露（只有分部资产），按分腿 ROE 来源③会退回公司口径——拆了也只是用公司 ROIC 分摊，信息为零 | active | 10-K FY2025 分部附注；Wisburg 98844 / 97948 | 主尺骨架 |
# | A4 | **归篮：篮 4 龙头制造 r = 10%**：民机双寡头之一、积压 7,153 亿覆盖 ~6 年产量、27 家覆盖；收入不依赖未落定融资或未签约客户（非篮 7），盈利不是商品价函数、非小盘（M 档股权价值约 1,192 亿美元）（非篮 6），无照付不议 / 监管定价（非篮 1 / 2）。**CAPM 粗筛** = 4.0% + β 1.213 × 4.5% = **9.46%**，与篮子差 −0.54pp（< 3pp，不进篮子质疑清单） | active | yfinance β 2026-09-23；valuation-rules「§r 篮子」 | `r_perp` |
# | A5 | **L 世界 = 恢复停在 FY2027 共识下沿**：core EPS 2.47、不背 FY2028 过渡（「恶化世界不能同时背高速过渡增长」），ROIC 10.1%（投入资本含税后养老金缺口，A9）贴着 r 10%、落病态区（\|ROIC − r\| < 3pp）→ 倍数对 g 几乎不动（g2 0 → 10.0×、6% → 10.1×）。**L 世界的含义**：波音走不出困境——产率、777X、防务计提都没修好，公司只赚到资本成本，此后再投资的每一块钱只换回一块钱价值，增长不创造价值；薄股权把这一点放大：L 在 g2 = 0 时 7.7、6% 时 8.2（分子年初口径；时点对齐后 6.44，A15）。实证坐标：2023 年（737 产率 31–38、FCF 44 亿）与 2022 年（FCF 23 亿）都实印过比 L 分子更差的盈利；街最低 TP 246 远在 L 之上。**证伪 / 触发**：SPEEA 工程师罢工（合同 2026-10-06 到期，二次方案表决 09-24 → 10-01）或 FAA 冻结 47 产率 → 把 FY27 共识下沿往下拉，L 随共识更新 | active | yfinance；数据包 §4 FCF 表；Leeham 2026-09-21 | `eps27_low`；L |
# | A6 | **\(g_1\) = FY27 → FY28 共识 EBIT 增长 63.9%，n = 1，只给 M / H**：同源 MarketScreener 共识 EBIT 5,957 → 9,762（\$M）；用 EBIT 而非 EPS 增速（+87.7%），因为 EPS 增速含去杠杆省息，而分子是去杠杆口径（A10）。`check_transition_years(1, 1)` 通过 | active | MarketScreener 2026-09-23 | `ebit27_ms` / `ebit28_ms` / `n_stage` |
# | A7 | **恢复形态（段一全派）**：见 §1 属性 B。依据：FY2028 共识 FCF 97.8 亿 ≥ NOPAT 83.1 亿；2026 capex 指引 ~40 亿（含 Spirit）对 D&A ~23 亿的超额部分已具名（A8 D 桶），不是 +64% 的来源。**交叉**：标准 `two_stage_pe`（段一派息 1 − 63.9% / 13.8% = −364%，即按发股融资计）→ M **71.1**（分子年初口径，对 124.6；时点对齐后 67.0 对 118.0）。两者之差约 51–54 / 股 = 「增长要不要资本」这一判断的价格 | active | 数据包 §4；MarketScreener | M / H 倍数 |
# | A8 | **留存去向审计**（valuation-rules Step 0–5）：Step 0 —— NPPE 2017–2023 从 126.7 亿降到 106.6 亿（capex < D&A 连续 5 年：2019–2023 capex 9.8–18.3 亿 vs D&A 18.6–22.7 亿）；2024 114.1 亿、2025 153.6 亿（Spirit 并表 + capex 29.4 亿 > D&A 19.5 亿）、2026-06 166.9 亿；净债 2025 年末 277.1 亿 → 2026-06 258.8 亿；NI 2019–2024 连亏、2025 靠出售利得转正；股息 2020 年起暂停。Step 1 分桶 —— 近 3 年无正常盈利可留存；前瞻 FY27–FY28 的现金流去向：**A 桶还债**（共识净债 224 → 165 → 65 亿，2026 → 2028；评级 BBB- / Baa3，管理层首要用途为恢复投资级安全边际）+ **D 桶增长窗口**（787 查尔斯顿扩建到 14 架 / 月、737 埃弗里特 North Line 2026-07 开始低速试产、圣路易斯 F-47 厂房；窗口终点具名 = FY2028 年末，其后 capex 回到 ≈ D&A 为触发复核）。Step 2 / 3 —— 不用 \(1/(r-g)\) 也不用 g = 0 + 1/r：尾段用完整式，\(b = g_2/ROIC\)。D 桶项目的利润：787 10 架 / 月与 737 47 已在 FY2028 共识内（已花部分已进分子，不另加）；787 14 与 North Line 产能在 FY2028 之后，按「未花 × (ROIC_proj / r − 1)」应**加**而非罚（项目 ROIC 按 2018 年 BCA 13.6% 利润率量级 > r），保守计 0、不单列。禁止形态七条逐条未命中：(i)(ii) 未用；(iii) 已花 capex 未被罚；(iv) 分子加回利息、闭合项扣净债，现金只在净债里抵一次；(v) 无股息；(vi) 不适用（本文不落市价隐含 r）；(vii) 无「一次性」声称 | active | SEC XBRL companyfacts（NPPE、capex、D&A 2013–2025）；Q2'26 8-K；MarketScreener 净债共识 | 倍数形式；`k_*` |
# | A9 | **视同派出的打折 k = 0 / 0 / 0**（来源层级 ② 默认：A / D 桶，去向已具名、回报可查）：模型在段一（L 为首年）把 NOPAT 全额视同派出，公司实际派 0、用于还债与具名项目；去杠杆口径下还债是价值中性（闭合项按今天的净债扣，未提前抵扣将来的还债）。披露行（1 年窗口）：L 4.47 / M 6.11 / H 8.66 美元 / 股，k 后相同。**ROIC 口径偏宽**：投入资本 368 亿（权益 + 净债 + 税后养老金缺口）被 2019 年后累计亏损冲低，FY28 ROIC 22.6%（M）/ 31.7%（H）高于 2018 年实印量级；若把 2019 年后的累计亏损加回投入资本重建 ROIC，尾段派息会下降、倍数收窄——`待补` 精算，方向偏不利于 M / H。**部分已处理（用户 2026-10-19 认可）**：① 尾段稳态回报改读自身周期投入资本口径 18.7%（分母含税后养老金缺口），M / H 的前瞻 22.6% / 31.7% 2029–2034 年回落到 18.7%（A15）；② **前瞻回报的分母也计入税后养老金缺口**（权益 + 净债 319.9 亿 + 48.5 亿 = 368.4 亿），与稳态回报同口径——养老金缺口是公司为维持经营欠下、已在闭合项扣除的债，回报的分母同样要背；前瞻 ROIC27 11.6 / 15.9 / 22.3% → 10.1 / 13.8 / 19.4%，锚点 14.85 / 119.02 / 186.76 → 6.44 / 117.98 / 185.52。L 变动最大（−57%）：L 的 ROIC 贴着 r，落病态区，对分母极敏感；M / H 只动约 1%，因为它们在 2034 年后都落到同一个 18.7%，分母只改动回落前几年 | active | 10-Q / 8-K；valuation-rules「视同派出」 | `k_l/k_m/k_h`；`equity`、`debt`、`cash`、`pension_def`、`opeb_def`（ROIC 分母） |
# | A10 | **杠杆门触发**：FY2025 净债 / EBITDA = 277.1 ÷（42.81 + 19.53）= **4.45**（> 3）；利息 / EBIT = 27.71 ÷ 42.81 = **65%**（> 1/3；EBIT 含 95.7 亿出售利得，剔除后为负）。处置（分腿票条款同样适用于整公司去杠杆构造）：分子 = 去杠杆 NOPAT、净债作闭合项 → ROIC 侧判域（分母含税后养老金缺口，A9；ROIC 27：10.1 / 13.8 / 19.4%；FY28：16.5 / 22.6 / 31.7%；M / H 尾段单调区、L 病态区）、A 桶去杠杆分子由构造内建（省息不进 g）。**类债 / 类股工具**：6% 强制可转优先股（57.5 亿清算额，2027-10-15 必转，5.828–6.994 股 / 股）→ **股**，其股息 3.45 亿 / 年加回 NOPAT、每股按该档价值定转股比（L / M 830.6 / 830.4 百万股、H 823.9）；Spirit 可交换债计在总债务内，其潜在转股数 `待补`（10-Q 附注 3 排除的潜在股合计 36.7M 中扣掉优先股后 ≤ 3M，影响 < 0.4%）。**利率 +100bp**：按总债务 459 亿 → 税后 3.6 亿 / 年 = EPS −0.46（FY27 均值的 11%）；分子为去杠杆口径，只经闭合项与再融资成本传导。**§5b 换尺判定**：EBIT 不 ≈ 可分配现金（客户预付款与库存摆动大）、卖方用 FCF yield 而非 EV/EBIT → 不命中，Gordon 留主尺；EV 口径交叉：M EV / FY28 共识 EBITDA = 11.2×、H 16.0×（分子年初口径），对自身 2013–2018 年 EV/EBITDA 10–15× | active | 10-K FY2025；Q2'26 8-K；10-Q 附注 3 / 15 | 主尺形态；`pref_div`、`int_exp`、`int_inc`、`mcp_*` |
# | A11 | **\(g_2\) = 6%（同业簇反解中位 6.84% 截到 \(G_{cap}\)）**：yfinance 2026-09-23 同日 forwardPE × ROE、r = 10%、按各自派息率选分支，剔除不良条件与贴极点者：GE 7.62% / 洛马 4.07% / 通用动力 6.62% / 诺格 5.25% / 豪梅特 7.79% / 空客 7.06% → 中位 **6.84%**（n = 6）；剔除：RTX、L3Harris（r − g < 2%）、HII、德事隆、赛峰（ROE 贴 r 或 ADR 口径异常）、海科（贴极点）、TransDigm（ROE 缺）。同业与本票同域（单调区）、同篮（篮 4）。**簇定义敏感性（披露，不改锚）**：民机链三家（GE / 豪梅特 / 空客）7.62% → 截 6%，锚点不变；防务三家（洛马 / 通用动力 / 诺格）5.25% → L / M / H 6.3 / 101.9 / 161.8（时点对齐后）。**同世界门**：分子年到 FY2028 共识方向向上 → g2 > 0 可用。`check_branch`：g2 > 0、实付派息 0 < 95%，ROIC ≫ r + 3pp 不做幅度测试 | active | `_local/tmp/BA/peers_yf.json`（2026-09-23 拉取） | `g2`、`peer_g_median`、`peer_g_defense` |
# | A12 | **\(V_{opt}\) = 0**：唯一可能的实测锚是 2018 年自身单位经济（营业利润 119.9 亿，BCA 13.6% / BDS 6.4% / BGS 14.9%）；H 世界 FY2028 NOPAT 116.9 亿已高于其税后 94.7 亿 → 已在 H 内，按 construction §7c-4 不得再进期权。FY2028 之后的产率与 BDS 利润率修复无共识年份、无超出 2018 的实测单位 → `stretched` 解释。**无候选带**：FY2028 区间来源未核（A2），单家数据（杰富瑞 FCF）是 FCF 口径、与本尺分子不同基 | active | SEC XBRL `OperatingIncomeLoss` 2018；数据包 §1 | `V_opt = 0` |
# | A13 | **卖方差额**：卖方 TP 均值 273.7 高于 H 185.5 的来源：杰富瑞 3.5% FCF yield on 2028E（≈ 28.6× P/FCF，等价 r − g ≈ 3.5%）、高盛 3.0% on 2027E——两者的 r − g 都低于本仓 \(G_{cap}\) 规则保证的 4pp 下限；不是分子分歧（杰富瑞 2028E FCF 88 亿 < 共识 97.8 亿）。**③ 护栏**：自身同等盈利月份 = FY2010（EPS 4.45 落 FY27 均值 4.19 ±12%），价 61–73、trailing PE 13.7–16.3×；**带有效性核验**：当时 ROE = 33.1 亿 ÷ 均值权益 24.5 亿 ≈ 135% vs 现模型 ROIC 14–23%（高 ≥ 5pp）→ **失真**；当时预期增速（2010 → 2012 实测 EPS CAGR +7%）低于现模型 \(g_1\) 64% → 该项偏低；且 M 在 FY27 levered EPS 上是 28×、在带**上方**，③ 只拦 M 低于带下沿 → 不触发。P/FCF 交叉：自身 2013–2018 年末 13–17×；EV / FY28 共识 FCF：M 13.7×、H 19.6×（分子年初口径） | active | yfinance 月线 2010；SEC XBRL；数据包 §7；Wisburg 98844 / 97948 | 只披露 |
# | A14 | **近端事件**：① SPEEA 工程师合同 2026-10-06 到期（二次方案 4 年 +34% 薪酬，表决 09-24 → 10-01；否决并罢工 → 777X 认证停摆、737 产率下调，A5 L 触发）；② Q3'26 财报（日期未公布，历史为 10 月下旬）：交付（737 全年 ~500、787 90–100）、FCF 指引 10–30 亿中点 20 亿（含司法部 7 亿付款）；③ 737-7 / -10 认证（管理层指 2026 年内）；④ 中国订单（~200 架承诺，逐步落地）。①③ 任一明显落空 → 等 FY27 共识下修后事件增量；② 实际 FCF 低于指引下沿 → `weakened` | active | 数据包 §8；MS Laguna 2026-09-16 | A5 / A6 分子 |
# | A15 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④）**：**超额现金 = 0**——2019 年以来一直净负债（2026-06-30 现金及短投 200.2 亿 < 总债务 459 亿），经营所需现金锚下限 0，不单列，净债与税后养老金缺口照旧作闭合项；归母比例 0.9975（少数股东 15）只用于窗口。**增长期资金缺口：不计**——H1 经营现金流 11.85 亿 < 资本开支 20.08 亿，但 FY2026 共识（自由现金流 21.58 亿、资本开支 39.75 亿，MarketScreener 2026-10-15）隐含 H2 经营现金流约 49 亿 > H2 资本开支约 20 亿，窗口合计付得起。**时点对齐**：基准日 2026-06-30 → 分子年初 2027-01-01，τ = 0.5；原「FY2027 = 当前财年 +1 不折现」没有整年折回要还原。**窗口可分配利润**（2026H2，与分子同口径的去杠杆 NOPAT）= (FY26 core EPS 共识 −1.097 − H1 实测 −0.96) × 7.904 亿股 + 半年优先股股息与税后净利息 8.80 亿 = 7.72 亿；× (1 − b)：M / H 段一是恢复形态（段一全派，b = 0），L 不背过渡 b = g2 / ROIC27_L = 0.517；× 归母比例；按 τ/2 折。**稳态回报三段**（②）：前瞻（与稳态同一投入资本口径，分母含税后养老金缺口，A9；**用户 2026-10-19 认可**，锚点 L −57% / M −0.9% / H −0.7%）L 10.1% / M 22.6% / H 31.7%；高回报期 Y1 = 可见年末 2028，进入门槛判**高**（民机双寡头、适航认证十年级、产线投资百亿级）→ 回落 6 年，Y2 = 2034；稳态值取**自身完整周期**，按投入资本口径（valuation-rules「稳态回报三段」回报口径，2026-10-19；**用户 2026-10-19 认可**本档取值与 M −12.5%、H −18% 的变动）：SEC XBRL 2010–2025 营业利润 × (1 − 实际税率) ÷ 年初投入资本（权益含少数股东 + 债务 − 现金 − 短投 + 养老金与退休医疗缺口 × (1 − 21%)；一直净负债或净现金低于经营所需，超额现金锚 0），16 年中位 **18.7%**（2010–2018 年 17.5–53.4%，2019–2024 年为负，2025 年 11.2%；`_local/tmp/round9/netdebt/ic_cycle.py`）。前瞻 ROIC 用 core 口径、历史用 GAAP 营业利润，差在非经营性养老金项，量级小。成熟同业（近 5 年收入复合增速 0–10%、≥ 5 年穿越周期读数）只剩德事隆 12.4%（账面口径、未按新口径重算；不完全同生意，不认；空客只有 3 年读数不认，GE 收入负增长、豪梅特增速 > 10%）；兜底有壁垒重资产 15%。→ 稳态 = max(18.7%, 15%) = **18.7%**，≥ r：L 前瞻 10.1% 低于稳态、按「≤ 前瞻」留在前瞻不回落——它只比 r 高 0.07pp，按「持续失败只往下拉」读也是同一结果：维持前瞻、**不上抬**到稳态或 r，L 世界是走不出困境、只赚资本成本、增长不创造价值（A5）；M 22.6% / H 31.7% 2029 年起线性回落、2034 年起 18.7%，倍数 28.25 → 26.46× / 31.11 → 26.87×（t = 1）。**旧读数 60.8% 不认**：分母只算权益 + 净债时，养老金缺口与 2019 年后累计亏损把分母压薄（2019 年后权益转负，分母只剩净债），读数虚高——同期不含养老金缺口的中位 74.5%（`rs_own_cycle_ex_pension`，只披露）。若连自身周期层也不认 → 兜底 15% → 6.44 / 103.18 / 164.64（只披露）。k = 0 不变（A9） | active | SEC XBRL companyfacts 2010–2025；MarketScreener FY2026 共识；yfinance core EPS 共识与实测 2026-10-15；SEC XBRL 养老金 / 退休医疗负债 2010–2025（2026-10-19） | `tau`、`eps26_cons`、`eps_h1_26`、`parent_share`、`y1`、`y2`、`rs_own_cycle`、`rs_fallback`、`rs_own_cycle_ex_pension`；全部锚点 |
HISTORICAL_PARTIAL_FINGERPRINT = 'd8500a1bffd5e8e3a3ee22d7643354fd66f3022c1a0696d6eeddd425f5d3876b'

INPUTS = {
    # 普通股流通数（10-Q 封面）; 来源：2026-07-21
    'shares_basic': 790.37,
    # 6% 强制可转优先股股数（清算额 $1,000 / 股，57.5 亿）；2027-10-15 必转（A10）; 来源：10-Q 2026-06-30 附注 15
    'mcp_units': 5.75,
    # 最低转股比（VWAP ≥ 171.59 时）；介于两门槛之间 = 1,000 ÷ 价格; 来源：8-K Ex99.2 2024-10-28
    'mcp_rate_min': 5.8280,
    # 最高转股比（VWAP ≤ 142.98 时）; 来源：同上
    'mcp_rate_max': 6.9940,
    # FY2027E core EPS 共识低端（21 家）（A2 / A5）; 来源：yfinance 2026-09-23
    'eps27_low': 2.4675,
    # FY2027E core EPS 共识均值（21 家）; 来源：yfinance 2026-09-23
    'eps27_mean': 4.18992,
    # FY2027E core EPS 共识高端（21 家）; 来源：yfinance 2026-09-23
    'eps27_high': 6.80,
    # 强制可转优先股年股息（GAAP 归普通股利润已扣；按股处理故加回 NOPAT，A10）; 来源：FY2025 8-K 利润表
    'pref_div': 345,
    # 利息与债务费用年化 = Q2'26 600 × 4; 来源：Q2'26 8-K
    'int_exp': 2400,
    # 利息收入年化（推算）= (其他收益 79 + 非经营性养老金费用 73) × 4；core 口径已剔养老金项; 来源：Q2'26 8-K / 10-Q
    'int_inc': 608,
    # 美国法定税率（公司 core 调节表同口径）；用于利息加回与养老金缺口税后化; 来源：Q2'26 8-K 调节表脚注
    'tax_rate': 0.21,
    # FY2027E 共识 EBIT（\$M，MarketScreener 均值）；\(g_1\) 分母（A6）; 来源：2026-09-23
    'ebit27_ms': 5957,
    # FY2028E 共识 EBIT（\$M，MarketScreener 均值，点估计）；\(g_1\) 分子（A6）; 来源：2026-09-23
    'ebit28_ms': 9762,
    # 过渡年数 = FY2028 一年（有共识年数 1）; 来源：2026-09-23
    'n_stage': 1,
    # 总权益（含少数股东 15）；ROIC 分母之一; 来源：Q2'26 8-K 资产负债表
    'equity': 6115,
    # 总债务（短 4,565 + 长 41,335，含 Spirit 承接债）; 来源：Q2'26 8-K
    'debt': 45900,
    # 现金 7,239 + 短期及其他投资 12,783; 来源：Q2'26 8-K
    'cash': 20022,
    # 养老金净负债（资产负债表）；税后进闭合项与 ROIC 分母（A9）; 来源：Q2'26 8-K
    'pension_def': 4108,
    # 退休医疗净负债（资产负债表）；税后进闭合项与 ROIC 分母（A9）; 来源：Q2'26 8-K
    'opeb_def': 2027,
    # 整公司永续折现率 = **篮 4 龙头制造** 10%：民机双寡头、积压覆盖 ~6 年、27 家覆盖、非商品价函数（A4）; 来源：2026-09-23
    'r_perp': 0.10,
    # 永续增速 = min(同业簇中位, \(G_{cap}\)) = 6%（A11）; 来源：2026-09-23
    'g2': 0.06,
    # 同业簇反解中位（n = 6，原值；A11）; 来源：yfinance 2026-09-23
    'peer_g_median': 0.0684,
    # 防务三家子簇中位（敏感性，A11）; 来源：yfinance 2026-09-23
    'peer_g_defense': 0.0525,
    # 实付派息率（股息 2020 年起暂停）; 来源：10-K FY2025
    'payout_observed': 0,
    # 视同派出打折 L（来源 ② A 桶，A9）; 来源：2026-09-23
    'k_l': 0,
    # 同上 M; 来源：2026-09-23
    'k_m': 0,
    # 同上 H; 来源：2026-09-23
    'k_h': 0,
    # 时点对齐年数 = 估值基准日 2026-06-30（Q2'26 资产负债表）→ 分子年初 2027-01-01（A15）; 来源：2026-06-30
    'tau': 0.5,
    # FY2026E core EPS 共识均值（23 家）；只用于窗口可分配利润（A15）; 来源：yfinance 2026-10-15
    'eps26_cons': -1.09731,
    # 2026H1 core EPS 实测（Q1 −0.20 + Q2 −0.76）（A15）; 来源：yfinance earnings_history 2026-10-15
    'eps_h1_26': -0.96,
    # 归母比例 = (总权益 6,115 − 少数股东 15) ÷ 6,115（A15）; 来源：Q2'26 8-K
    'parent_share': 0.9975,
    # 高回报期止点 = 可见年末（FY2028 过渡年）（A15）; 来源：2026-10-16
    'y1': 2028,
    # 稳态落稳年 = Y1 + 6（进入门槛：高）（A15）; 来源：2026-10-16
    'y2': 2034,
    # 稳态回报 = 自身完整周期投入资本回报中位（2010–2025，税后营业利润 ÷ 年初投入资本；投入资本 = 权益含少数股东 + 债务 − 现金 − 短投 + 养老金与退休医疗缺口 × 0.79）（A15）; 来源：SEC XBRL 2026-10-19
    'rs_own_cycle': 0.187,
    # 生意模式兜底：有壁垒的重资产 15%；稳态回报 = max(自身周期, 成熟同业, 兜底)，同业层只剩德事隆、不同生意不认（A15）; 来源：2026-10-15
    'rs_fallback': 0.15,
    # 披露：同期分母不含养老金缺口的读数（74.5%）；2019 年后累计亏损把权益冲成负值、养老金缺口未计入时分母被压薄，不认（A15）; 来源：SEC XBRL 2026-10-19
    'rs_own_cycle_ex_pension': 0.745,
    # 杠杆门读数：净债 27,710 ÷ (EBIT 4,281 + D&A 1,953)（A10）; 来源：10-K FY2025
    'net_debt_ebitda_fy25': 4.45,
    # 杠杆门读数：利息 2,771 ÷ EBIT 4,281（A10）; 来源：10-K FY2025
    'interest_ebit_fy25': 0.647,
    # FY2028E 共识 EBITDA（EV 交叉，A10）; 来源：MarketScreener 2026-09-23
    'ebitda28_ms': 11996,
    # FY2028E 共识 FCF（P/FCF 交叉，A7 / A13）; 来源：MarketScreener 2026-09-23
    'fcf28_ms': 9784,
}
BASKETS = {"r_perp": 4}  # aerospace leader, original A4
REQUIRED = frozenset(INPUTS)

def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0, recovery: bool = False) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2.  Stage-1 years pay out in full when `recovery`
    (recovery_two_stage_pe form) else 1 - g1/roe.  With rs >= roe this equals
    perpetual_pe / recovery_two_stage_pe exactly.  (gordon.py three-segment helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 if recovery else 1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def mcp_shares(price: float, inp: dict[str, float]) -> float:
    """Common shares the mandatory convertible delivers at a given price (millions)."""
    # Between the two thresholds each $1,000 preferred delivers $1,000 of stock.
    rate = min(max(1000.0 / price, inp["mcp_rate_min"]), inp["mcp_rate_max"])
    return inp["mcp_units"] * rate


def per_share(equity_value: float, inp: dict[str, float]) -> tuple[float, float]:
    """Fixed point: the conversion rate depends on the per-share value it produces."""
    value = equity_value / inp["shares_basic"]
    for _ in range(50):
        shares = inp["shares_basic"] + mcp_shares(value, inp)
        value = equity_value / shares
    return value, shares



def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp, ('n_stage', 'y1', 'y2'))
    if inp['y1'] < NUM_YEAR or inp['y2'] <= inp['y1']:
        raise ValueError('invalid return path years')
    r, g2, t = inp["r_perp"], inp["g2"], inp["tax_rate"]
    baskets = BASKETS
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if abs(g2 - min(inp["peer_g_median"], g_cap(r))) > 1e-9:
        errors.append(f"g2 {g2} != min(peer median {inp['peer_g_median']}, cap {g_cap(r)})")
    n = int(inp["n_stage"])
    errors += check_transition_years(n, 1, "n_stage (FY2028 point consensus only)")
    errors += ladder("eps27", inp["eps27_low"], inp["eps27_mean"], inp["eps27_high"])

    # Step 1 — unlevered numerator (NOPAT, $M): core NI + MCP dividend + after-tax net interest.
    addback = inp["pref_div"] + (inp["int_exp"] - inp["int_inc"]) * (1 - t)
    nopat = {k: inp[f"eps27_{k}"] * inp["shares_basic"] + addback for k in ("low", "mean", "high")}
    g1 = inp["ebit28_ms"] / inp["ebit27_ms"] - 1

    # Step 2 — invested capital and ROIC (leverage gate: retention runs on ROIC, not ROE).
    # The forward denominator carries the after-tax pension / OPEB deficit too, the same
    # invested-capital basis as the own-cycle steady reading (retention「回报口径」, user
    # 2026-10-19), so forward and steady returns compare like for like.
    net_debt = inp["debt"] - inp["cash"]
    pension_at = (inp["pension_def"] + inp["opeb_def"]) * (1 - t)
    ic = inp["equity"] + net_debt + pension_at
    roic27 = {k: v / ic for k, v in nopat.items()}
    roic28 = {k: v * (1 + g1) / ic for k, v in nopat.items()}

    # Step 3 — multiples on FY2027 NOPAT, on the steady-return path (A15): forward ROIC
    # through Y1, linear to the steady return by Y2.  Steady = max(own full cycle, mature peers
    # (empty: Textron is not the same business), business-model fallback), read on invested
    # capital incl. the after-tax pension / OPEB deficit (retention「回报口径」2026-10-19);
    # each tier then takes min(forward, steady) — L (11.6%) stays at forward, M / H fade.
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    rs = max(inp["rs_own_cycle"], inp["rs_fallback"])
    if rs < r:
        errors.append(f"steady return {rs:.3f} < r {r}")
    if inp["rs_own_cycle"] >= inp["rs_own_cycle_ex_pension"]:
        errors.append("own-cycle reading with the pension deficit in capital must sit below the ex-pension one")

    def tier_pes(r_: float) -> dict[str, float]:
        return {
            "L": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roic27["low"], r_),
            "M": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roic28["mean"], r_, g1=g1, n=n, recovery=True),
            "H": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roic28["high"], r_, g1=g1, n=n, recovery=True),
        }

    pes = tier_pes(r)
    pe_l, pe_m, pe_h = pes["L"], pes["M"], pes["H"]
    return_path_binds = abs(pe_l - perpetual_pe(g2, roic27["low"], r)) > 1e-9 or abs(
        pe_m - recovery_two_stage_pe(g1, n, g2, roic28["mean"], r)) > 1e-9
    for tier, roic in (("M", roic28["mean"]), ("H", roic28["high"])):
        errors += check_branch(g2, roic, r, inp["payout_observed"], f"{tier} tail")

    # Step 4 — timing (A15): the Gordon value is at t_n = 2027-01-01; discount tau years to the
    # 2026-06-30 balance sheet and add the window's distributable NOPAT (2026H2 consensus,
    # x (1 - b): M / H stage 1 is the recovery form, b = 0; L b = g2 / ROIC27_L) at tau / 2.
    # EV → equity → per share; × (1 − k) (A bucket, k = 0 by source ②).
    tau = inp["tau"]
    win_nopat = (inp["eps26_cons"] - inp["eps_h1_26"]) * inp["shares_basic"] + addback / 2
    win_b = {"L": g2 / roic27["low"], "M": 0.0, "H": 0.0}
    claims = net_debt + pension_at
    ks = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    def tier_ev(pes_: dict[str, float], r_: float) -> dict[str, float]:
        return {k: nopat[j] * pes_[k] / (1 + r_) ** tau
                + max(win_nopat * (1 - win_b[k]), 0.0) * inp["parent_share"] / (1 + r_) ** (tau / 2)
                for k, j in (("L", "low"), ("M", "mean"), ("H", "high"))}

    ev = tier_ev(pes, r)
    anchors, shares = {}, {}
    for k, v in ev.items():
        value, shares[k] = per_share(v - claims, inp)
        anchors[k] = value * (1 - ks[k])
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")

    # construction §2c — flat multiple (M's) on every tier's numerator must still ladder.
    flat_ev = tier_ev({"L": pe_m, "M": pe_m, "H": pe_m}, r)
    flat = {k: per_share(flat_ev[k] - claims, inp)[0] for k in ("L", "M", "H")}
    errors += ladder("flat-multiple", flat["L"], flat["M"], flat["H"])

    A, B = cut_points(L, M, H)


    post = {"L": nopat["low"], "M": nopat["mean"] * (1 + g1), "H": nopat["high"] * (1 + g1)}

    # Disclosures (do not price).
    ys = {k: per_share(nopat[j] * pes[k] - claims, inp)[0] for k, j in (("L", "low"), ("M", "mean"), ("H", "high"))}
    pe_m_retain = two_stage_pe(g1, n, g2, roic27["mean"], r)
    m_retain = per_share(tier_ev({**pes, "M": pe_m_retain}, r)["M"] - claims, inp)[0]
    growth_sensitivity = {}
    for label, gg in (("growth_down", g2 - 0.01), ("defense_growth", inp["peer_g_defense"])):
        pes_g = {
            "L": three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roic27["low"], r),
            "M": three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roic28["mean"], r, g1=g1, n=n, recovery=True),
            "H": three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roic28["high"], r, g1=g1, n=n, recovery=True),
        }
        ev_g = tier_ev(pes_g, r)
        ll, mm, hh = (per_share(ev_g[k] - claims, inp)[0] for k in ("L", "M", "H"))
        growth_sensitivity[label] = dict(zip("LMH", (ll, mm, hh)))
    rs_alt = 0.15
    pes_s = {
        "L": three_segment_pe(NUM_YEAR, y1, y2, rs_alt, g2, roic27["low"], r),
        "M": three_segment_pe(NUM_YEAR, y1, y2, rs_alt, g2, roic28["mean"], r, g1=g1, n=n, recovery=True),
        "H": three_segment_pe(NUM_YEAR, y1, y2, rs_alt, g2, roic28["high"], r, g1=g1, n=n, recovery=True),
    }
    ev_s = tier_ev(pes_s, r)
    fallback_return = {k: per_share(ev_s[k] - claims, inp)[0] for k in "LMH"}
    ic_x = ic - pension_at  # old basis: forward denominator without the pension deficit (A9)
    pes_x = {
        "L": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, nopat["low"] / ic_x, r),
        "M": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, nopat["mean"] * (1 + g1) / ic_x, r, g1=g1, n=n, recovery=True),
        "H": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, nopat["high"] * (1 + g1) / ic_x, r, g1=g1, n=n, recovery=True),
    }
    ev_x = tier_ev(pes_x, r)
    # Stage 1 (or L's first year) pays out 100% in the model; the company pays 0.
    deemed = {k: nopat[j] / shares[k] for k, j in (("L", "low"), ("M", "mean"), ("H", "high"))}
    l_g0 = per_share(nopat["low"] * perpetual_pe(0.0, roic27["low"], r) - claims, inp)[0]
    rate_eps = inp["debt"] * 0.01 * (1 - t) / inp["shares_basic"]

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 — the only priced r; g1/g2, ROIC, NOPAT, claims and k stay put
    # (the conversion count still solves at each column's value).  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        rr = r + dr
        if rr <= g2:
            raise ValueError('rate scenario must exceed perpetual growth')
        ev_r = tier_ev(tier_pes(rr), rr)
        lmh = [per_share(ev_r[k] - claims, inp)[0] * (1 - ks[k]) for k in ("L", "M", "H")]
        return lmh[0], lmh[1], lmh[2]

    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if errors:
        raise ValueError("; ".join(errors))
    result = {
        "ticker": "BA.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-06-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of': '2026-10-19',
        "anchors": anchors, "candidate": None, "option": None,
        "cut_points": [A, B], "shares": shares, "nopat": nopat,
        "roic27": roic27, "roic28": roic28, "pes": pes, "ev": ev,
        "flat": flat, "ys": ys, "ic": ic, "net_debt": net_debt,
        "claims": claims, "g1": g1, "rs": rs, "post": post,
        "win_nopat": win_nopat, "win_b": win_b, "pe_m_retain": pe_m_retain,
        "l_g0": l_g0, "rate_eps": rate_eps, "ev_x": ev_x,
        "deemed_paid": deemed, "return_path_binds": return_path_binds,
        "parameters": {"discount": r, "growth": g2,
                       "forward": {"L": roic27["low"], "M": roic28["mean"], "H": roic28["high"]},
                       "mature": {"L": min(roic27["low"], rs), "M": min(roic28["mean"], rs), "H": min(roic28["high"], rs)}},
        "sensitivity": {**growth_sensitivity, "fallback_return": fallback_return,
                        "standard_transition_mid": m_retain,
                        "ex_pension": {k: per_share(ev_x[k] - claims, inp)[0] for k in "LMH"}},
    }

    if rate_inputs is not None:
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': r}, band_at=band_rf,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'baskets': BASKETS, 'numerator_year': NUM_YEAR}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments'] = {'company': {'unit': 'USD_PER_SHARE', 'values': dict(result['anchors'])}}
    parameters = result['parameters']
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['growth'])},
        'forward_return': {'unit': 'RATIO', 'values': parameters['forward']},
        'steady_return': {'unit': 'RATIO', 'values': parameters['mature'], 'reference_value': result['rs']},
    }
    result['review_flags'] = ['historical_high_leverage_and_pension_assumptions',
                              'historical_recovery_requires_capital_review',
                              'historical_invested_capital_depressed_by_losses']
    return result
