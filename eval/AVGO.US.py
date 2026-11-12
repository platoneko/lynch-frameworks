#!/usr/bin/env python3
"""AVGO legacy valuation; migration does not update estimates or judgments.

Amounts and shares are absolute USD and absolute counts. Segment margins are
estimated from reported aggregates, not disclosed stand-alone segment margins.
"""
from __future__ import annotations
import math
from lib.gordon import (check_basket_pair, MEGA_HW_REVENUE_USD, check_g_cap, check_k_declared,
                             check_r, check_transition_years, g_cap, perpetual_pe, two_stage_pe)
from lib.inputs import check_missing, ladder, require_whole_years
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES={'libraries':('gordon','inputs','tiers','zones','partial_basis','rf_report'),
              'axes':{'cowos':'cowos_capacity','optical':'optical_comms','lab':'frontier_lab_funding'}}
HISTORICAL_PARTIAL_FINGERPRINT='e129b6030ffad06d2640733455a0402e87e25fe5f28b113aceb92a32acdfb395'

FORMULA_ID = "avgo_sotp_xpu2tier_net_nonai_sw_fy27_gordon_v5"
LISTING_CCY = "USD"
TOL = 0.15
MIN_R_MINUS_G = 0.02
BRIDGE_TOL = 0.15
OM_INFER_TOL = 0.005
TIERS = ("L", "M", "H")
LEGS = ("uw", "lab", "net", "nonai", "sw")
# Which g2 / r each leg reads.  uw and lab are the same business (XPU) split by
# customer quality, so they share g2 and differ only in the r tier.
LEG_G2 = {"uw": "g2_xpu", "lab": "g2_xpu", "net": "g2_net", "nonai": "g2_nonai", "sw": "g2_sw"}
LEG_R = {"uw": "r_perp", "lab": "r_lab", "net": "r_perp", "nonai": "r_perp", "sw": "r_perp"}
# Terminal rate per leg (valuation-rules「篮子对」): only the lab leg fades -- its
# 篮 7 is "the customer pays from funding rounds", a state that ends if the lab
# makes it; the other legs' single basket is already their steady state.
LEG_RT = {**LEG_R, "lab": "r_lab_t"}
TRANSITION_LEGS = ("uw", "lab", "net")  # FY28 consensus growth is an AI story (A4/A5 flat)
# Hardware g2 keys under the mega-hardware cap (A25); software is a platform leg.
MEGA_HW_KEYS = ("g2_xpu", "g2_net", "g2_nonai")


# | A1 | FY27 AI 收入 base = **$115B**（公司指引；管理层明示按已锁定供应给出、需求高于此） | active | FY26Q3 法说 2026-09-02；JPM 103966 | XPU/网络收入桥 |
# | A2 | FY28 AI 收入 **$230B** 指引**不进分子**，只作 A8 桥校验（指引桥 FY28 EPS 29.43 vs 卖方中位 30.48，−3.5%）；FY28 进锚点的唯一通道是 A6 的共识过渡年 | active | 同上；Citi 104001 / BofA 103961 | 桥校验 |
# | A3 | AI 内 XPU/网络收入比 = **73/27**（F3Q 实际；网络与 XPU 同速增长 → 前瞻持稳） | active | JPM 103966 / Jefferies 103915：F3Q XPU≈73%；花旗纪要 104004 的 70/30 为整数示意 | 两腿拆分 |
# | A4 | 软件年收入 FY27/28 ≈ **$35B**（Q3 $8.752B/季年化；**不是**误读的「87B 年收入」）。零增长是收入侧保守假设；倍数改由 Gordon 生成后，软件腿的「质量」只体现在 g2_sw 5.38%（同业反解），不再另给 28× 溢价，故软件腿不背 FY28 过渡 | active | MS 103950：Q3 软件 $8.752B（+29% YoY）；Citi 104004：趋稳 ~$8.7B/季 | 软件腿 |
# | A5 | 非 AI 半导年化 ≈ **$17B**（Q3 ~$4.2B×4），增速低个位数、两年持平；不背 FY28 过渡 | active | Q3 法说/纪要 | 非 AI 腿 |
# | A6 | **FY28 共识过渡年（两段式 opt-in，n=1，仅 M/H，仅 AI 两腿）**：g1 公司口径 = FY28 卖方中位 30.48 ÷ FY27 共识 19.38 − 1 = **+57.2%**；因软件/非 AI 持平（A4/A5），全部增量落在 AI 两腿 → g1_ai = **+85.7%**（与指引 $115B → $230B 的 +100% 同量级，略低）。n 锚 = 只有 FY28 有 ≥2 家共识；FY29 只有单家叙事。段一派息率 M 档 −0.052、H 档 +0.039（= `two_stage_pe` 原形态 1 − 85.7%/ROE，ROE 按 FY27 年初净资产 A24；M 档靠发股/外部融资、H 档自筹——2026-10-03 腿利润率改推断前为 −0.167 / −0.070；MUST NOT 用实付派息率替代） | active | Citi 104001（30.48）/ BofA 103961（31.12）/ Jefferies 103915（CY28E 27.21）；yfinance FY27 共识 2026-09-11 | `eps_fy28_cons`、`n_stage` |
# | A7 | **r 按腿的现金流质地分腿，值由归篮给出（A23）**：已承销 XPU（Google/Meta LTA）、网络、非 AI、软件 = 常规经营现金流（LTA 有量承诺但付款方/费率/期限未公开，不是合约年金）；XPU 实验室腿的收入依赖 XPV 融资平台实际 close（第三方投资者承销部署）与 RVG 残值担保，命中「收入依赖尚未落定的融资 / 由或有负债支撑」判据，卖方原文即「实验室依赖型 ASIC 订单」——这是它单独设**过渡篮 7** 的理由；稳态性质与终值篮 4 见 A23。分腿有独立 r 字段（`r_perp` / `r_lab`），按字段分腿；单票 SOTP 不合成 r̄，逐腿相加。三档同一 r（r 不随情景变） | active | Jefferies 103915：XPV 融资安排；BofA 103961：RVG 为博通主要承诺形式 | `r_perp`、`r_lab` |
# | A8 | 指引桥 vs 共识（eval 强制，偏离 &gt;15% 复核）：FY27 桥 18.65 vs 47 家共识 19.38 **−3.8%**（核心簇 MS 18.27 / Citi 18.50 / BofA 18.61 均值的 +1.0%；HSBC ~20.0 为上尾）；FY28 指引桥 31.37 vs 卖方中位 30.48 **+2.9%**（全距 27.2–31.1；MS 只建模 $248B 收入未给 EPS） | active | yfinance 2026-09-11；Wisburg 103950 / 104001 / 103961 / 103915 | 防脏分子 |
# | A9 | **腿利润率来源层级（valuation-rules「数据优先级与同业同尺」腿级行 + 「公开数据推断」，2026-10-03）**：公司披露两个分部的营业利润（10-Q 分部附注，口径不含 SBC / 摊销 / 重组，与 non-GAAP EPS 同口径）——**软件 84%** = FY26Q3 分部实测 7,325 / 8,752 = 83.7%（有来源，直接用）；半导体分部内的 XPU / 网络 / 非 AI 无分部利润、无卖方腿级预测（Wisburg 九家 2026-09 研报只有定性「网络是商用产品、利润率更高」「XPU mix 稀释毛利」），按层级走**公开数据推断**：FY25Q3 / FY26Q3 两期联立（半导体分部收入 9,166 / 20,839、营业利润 5,217 / 12,770；AI 收入 5.2B / 16.7B，非 AI 为残差 3.97B / 4.14B），两个未知数 → **AI 64.98% / 非 AI 46.34%**；交叉：增量利润率（增量几乎全是 AI）64.70%；FY26Q4 指引（收入 34.8B、OM ~66%、AI 21.7B / 非 AI 4.3B / 软件 8.7B）在软件 84%、非 AI 46% 下隐含 AI **63.0%**（低侧）→ AI 区间 **[63.0%, 65.0%]**，取两期联立点 65.0%。**推断假设**：两期间各腿利润率不变——两年间半导体研发只增 18%、收入 +127%，经营杠杆按此假设全归 AI，**AI 偏高、非 AI 偏低**（非 AI 的 46% 低于 AI 起量前的半导体分部水平，方向即此偏差）；XPU 占 AI 比例从 FY25Q3 升到 73%（XPU 毛利更低）亦使 FY27 的 AI margin 偏向区间下沿（低侧敏感见 Outputs）。**AI 内拆分 = 拍值**：XPU / 网络无任何分拆利润披露，沿用对话锁定的 15pp 腿间差（原 55 / 70），定位到推断的 AI 均值 → **XPU 61% / 网络 76%**（eval 校验 0.73 × XPU + 0.27 × 网络 与推断差 ≤ 0.5pp、非 AI 与推断差 ≤ 0.5pp）。此前四腿 55 / 70 / 60 / 84 为对话锁定的示意值（AI 均值 59%、非 AI 60%，与推断不符），2026-10-03 按「不准拍值覆盖有来源的数」替换；FY27 公司口径 OM 67.1% vs FY26Q4 指引 ~66%。**若公司 OM 指引持续 < 64% 或 AI margin 跌出区间下沿 → 重做推断** | active | 10-Q FY26Q3 分部附注（2026-09-11）；法说 2026-09-02（Wisburg 104074）；GS 103909（Q3 AI +221%）；Citi 104004 / Jefferies 103915（定性） | `om_*`；`semi_*`、`ai_rev_q3_*`、`*_q4_guide`；EPS 桥 |
# | A10 | Google 仍为重要 XPU 客户且 TPU 主导份额不崩至少数 | active | 法说 LTA；卖方「仍主导」表述 | XPU 已承销档 |
# | A11 | FY28 增量中实验室（Anthropic/OpenAI）GW 可部分兑现；若 ARR/XPV 融资明显恶化，**或 GW 部署（土地/电力/机房）明显落后指引隐含 ~20GW** → weakened A6 并下修 g1；物理侧是第一顺位约束（六大客户名义 ~30GW &gt; 实际可部署）；**RVG 或有负债**：实验室失败 ≠ 只丢收入，残值担保变现为损失——盯 10-Q 披露的担保敞口规模 | active | Jefferies 103915：名义 30GW 受土地/电力限制；JPM 103966：指引按供应保守给出；BofA 103961：RVG 为博通承担的主要承诺形式 | A6 / 实验室档 |
# | A12 | 非 GAAP 税率桥接 = **16%**（Q4 指引口径） | active | FY26Q3 法说 | EPS 桥 |
# | A13 | 稀释股本 = **4.94e9**（Q4 指引量级） | active | FY26Q3 法说；Q3 反推 16.37B/3.32 = 4.93e9 | 每股 |
# | A14 | below-the-line 每股拖累 = **$0.40**（净利息等；FY27/28 持平，不建模去杠杆，偏保守） | active | Q3 实际：EBIT×(1−16%) − 调整后净利 ≈ $0.5B/季 ≈ $2B/年 | EPS 桥 |
# | A15 | XPU 客户两档拆分：已承销（Google/Meta，LTA）**39%** vs 实验室依赖（Anthropic/OpenAI）**61%**——FY27 GW 代理（3+1 vs 5+1.3，共 10.3GW）；**GW 代理为粗口径**：TPU v8i ASP 更高，Google 收入占比或高于 GW 占比，得收入级披露后替换；**三档都拆档**（r 是腿的性质，不随情景变）。**方向坐标（不入公式）**：Citi 104004 估 Google 占公司销售 35–40% = FY27 $58–67B，已高于本票已承销 XPU 桶 $33B（$84B × 39%）——但该数含网络附着、且未给 Meta，换不成同公式的 `xpu_uw_share`，故不落候选带（A2e-7h 要求同公式只换输入）；只说明 GW 代理偏保守（每 +10pp ≈ +7.5 美元/股，Outputs 敏感性） | active | JPM 103966 / GS 103909 部署表；Citi 104004：Google 占公司销售 35–40% | XPU 两档 EPS |
# | A16 | **挂载零和情景轴** `_AXIS.cowos-capacity.md`：XPU 与网络腿的收入受 2027 CoWoS 配额约束（需求 269.4 万片 > 供应 240 万片）。本票映射 **L←γ · M←β · H←α**，**与 `NVDA.US` 严格相反**——一票的坏即对手票的好，两侧 MUST NOT 同时假设自己被抢份额。L 档配额 38.7 万片较 β 的 43.1 万片 **−10.2%**、H 档 48.4 万片 **+12.3%**，直接缩放 XPU/网络收入；这是三档分子的唯一来源（同一条轴的两端，A2e-2a） | active | 大摩 103203（2027 CoWoS 需求四方拆分 + 台积 200k wpm）；映射与校验见 `eval/lib/axes.py` | `cowos_quota_*`；三档分子 |
# | A17 | **三档 ROE = FY27 分子 ÷ FY27 年初净资产**（起点 FY26Q3 权益 $99.69B = 20.18 美元/股，10-Q；含商誉 $97.8B、无形资产 $26.3B；按增长所需留存 \(b_1=g/ROE\) 滚过 Q4 FY26 到 FY27 年初 = 20.38 / 22.88 / 22.65，A24）：**85% / 81% / 89%**（旧口径 FY26Q3 权益直接作分母 = 86% / 92% / 100%）。SOTP 各腿无分腿权益，五腿共用公司 ROE（Phase 3 A3）。高 ROE 下派息率 ≈ 0.95，倍数对 ROE 不敏感、对 r−g 极敏感 | active | 10-Q FY26Q3（yfinance 资产负债表拉取 2026-09-14） | `equity` |
# | A18 | **g2 来源 = 同业横截面反解**（同一把 Gordon 尺、r=10%、yfinance 前瞻 PE × 账面 ROE，2026-09-11）。半导体横截面 11 家良态：NVDA 3.05% / NXPI 3.24% / QCOM 5.26% / AVGO 5.28%（自身，排除）/ TSM 5.66% / LRCX 6.48% / KLAC 6.57% / AMAT 6.61% / TXN 6.80% / ASML 6.92% / UMC 7.48%；剔除 AMD、ADI、MCHP、GFS（ROE≈r 或 ROE&lt;r，不良态）、MRVL、ARM、NOW（r−g&lt;2% 贴极点）、INTC（ROE&lt;0）、MU（派息封顶分支，周期顶）。AI 两腿取除自身外 10 家中位 **6.52% → 按巨型硬件上限截到 4.0%**（A25；普通上限 6% 的值进候选带 A22；严格 AI 加速器同业只剩 NVDA 一家良态 3.05%，不足两家，作对照）；非 AI 取模拟/射频三家中位 5.26% → 同样截到 4.0%（原值进候选带）；软件取 MSFT 6.10% / IBM 5.44% / CRM 5.31% / ORCL 3.26% 中位 5.38%。硬件腿 cap = min(4%, r − 4%)（巨型硬件上限）：篮 4 与篮 7 下都是 4%，截顶值不因归篮变动；软件腿按普通 cap 6%；AI 半导的高增长按命名 g1 窗口（A6 的 FY28 过渡年）表达，不抬 r、不进永续。**AI 腿 4% → 3% 每 1pp g2 值约 38 美元/股（M）**，是本框架最大的判断 | active | yfinance `forwardPE` / `returnOnEquity` 2026-09-11；`eval/lib/gordon.implied_g` | `g2_*` |
# | A19 | **倍数护栏 = 自身实测次年 PE 带 [9.9, 34.4]**：月末价 ÷ 下一财年分析师口径 EPS，2021-09→2026-09（n=61）；FY22–FY26 EPS = 各财年 non-GAAP EPS（拆股调整：3.77 / 4.22 / 4.86 / 6.82 / 11.66 共识），FY27 用当前共识 19.38；低点 **9.94×**（2022-09，价 41.95 ÷ FY23 4.22）、高点 **34.37×**（2025-11，价 400.71 ÷ FY26 11.66）、中位 17.0×；按次年分：FY25 口径 16.0–24.9、FY26 14.2–34.4、FY27 15.9–23.0。生成的三档混合倍数 15.8 / 21.8 / 22.0 全部在带内 → 通过；M/H 高于自身中位，来自 FY28 过渡年（段一）而非永续。**带即证据**（裁决顺序 ③）：M 档 ROE 下四腿 g2 同移到下沿需 −7.4pp（AI 腿 ≈ −3.4%），到上沿需 **+2.1pp**（AI 腿 6.1%，越 4% 巨型硬件上限）——上沿在合法 g 下不可达，带内任何 ≤ 4% 的 g 都合法；同业横截面 6.52% 截 4% 后落在带内，不触发带边反解。花旗「近期 20–40× 前瞻交易区间」（104001）与 BofA「前瞻 PE 历史中位 24×」（103961）只作对照；TTM 5 年带 17.0–184×（VMware 摊销扭曲 GAAP）不作护栏 | active | yfinance 月末价与各财年 EPS（2026-09-14 拉取，数据 09-11 收）；`_local/tmp/phase3/AVGO.US/realised_next_fy_pe_band.txt` | `pe_own_min/max` |
# | A20 | **哪些档启用过渡**：M/H 的 AI 两腿启用 FY28 过渡；L 全部腿、以及所有档的软件/非 AI 腿不启用（直接 `perpetual_pe`，不用 n=0 两段式）。L 的世界 = 「FY27 按 γ 配额交付、FY28 零 credit、此后永续」——A2e-1 的消化年。**分子与 g 同一世界**（Phase 3 A7）：L 的分子 17.35 是 FY27 这个前瞻稳态水平（高于最近已实现完整年 FY26 共识 11.66，略低于 FY27 共识低端 17.47），不是谷底，配稳态 g2 不算把周期算两遍；真正的谷底（XPU 冻结在 FY26 运行率 / 全年）只作 deep_discount 压力坐标。实证坐标：52 周低 289.96（2026-03-30 盘中）在 L 之下（deep_discount 坐标），街最低 TP 215.88（2026-09-11）亦然 | active | AGENTS.md「两段式过渡」；yfinance 52 周区间 / TP 2026-09-11 | L 档倍数 |
# | A21 | **分子年份的裁决（构造规则冲突裁决顺序 ②）**：分子取 ≥2 家共识可见的最远年份且三点同源——**FY27** 是最远一个有共识**区间**的年份（47 家，17.47 / 19.38 / 22.44；本票用指引桥 18.65 与之对账，三档差由轴配额给出；共识均值 19.38 落在本票 [M 18.65, H 20.21] 内，M 偏离 −3.8%，裁决表 ②-b 两条都过——腿利润率改推断前 H 19.30 低于均值、(i) 不过）；**FY28 虽是 ≥2 家可见的最远年份，但只有三家点估计**（Citi 30.48 / BofA 31.12 / Jefferies CY28 27.21；MS 只给收入；yfinance +1y 止于 FY27），凑不出三点同源的区间，故只进 g1 层（A6），FY28 = 当前财年 +2 的折现由 `two_stage_pe` 内部承担；FY29 无任何卖方 EPS，不进任何层。信息坐标（不入锚）：把三家点估计强作 FY28 三点分子（27.21 / 29.60 / 31.12，永续 g2、无过渡、折一年，各腿按自己的篮子 r）得 **367.5 / 399.8 / 420.3**（2026-10-03 腿利润率改推断后重算；构造写死：各腿按 M 档 FY28 腿间占比分摊点估计 → 各腿 `perpetual_pe`（实验室腿按终值篮 10% 资本化、乘 1−k_lab）→ 按各腿过渡篮 r 折一年；原值 472.4 / 515.7 / 543.3 无存档脚本、按文字描述无法复现，已按本构造替换，同构造的单篮读数为 348.4 / 379.0 / 398.5）——L/M 0.92、消化年消失（A2e-1 的 L 失效），中枢 400 低于底牌 M 406 约 2%（差在三家点均值 29.60 vs g1 隐含 29.32 的分子差与折现口径），两种构造讲的是同一量级的中枢。读法与 `MRVL.US` A3 / `TSM.US` A20 一致 | active | yfinance 2026-09-11；Wisburg 104001 / 103961 / 103915 / 103950 | `eps_fy27_cons`、`eps_fy28_cons`、`n_stage` |
# | A22 | **候选带（g2·可见期后跑道6%）**：同公式只把三条硬件腿的 g2 从巨型硬件上限 4% 换回同业值——AI 两腿（含实验室腿）`g2_cand` **6%**（横截面 6.52% 截普通上限）、非 AI `g2_nonai_cand` **5.26%**；软件腿不动 → L′/M′/H′ = **296.2 / 447.6 / 521.8**（同走三段回报与时点对齐，芯片腿 H 稳态 30%，A27）。6% 比长期名义增速多出的约 2pp 是可见期之后仍在高增长的跑道（valuation-rules「6% 的含义」）；本票的跑道取决于 AI 客户 FY29 之后是否继续加码，没有 ≥2 家 FY29 共识，故不进底牌（A25）。日报第三行 `候选(g2·可见期后跑道6%)` 独立归 zone，**不进**底牌 zone / 跨票比值 / `calibration.py`。**升级门槛**：≥2 家卖方给出 FY29 EPS 且 FY28→FY29 增速 ≥ 10% → FY29 按「增长的表达顺序」进过渡年（n 加一年，跑道被命名），重算后删除本行；或定价权两条被证成（A25）→ 豁免巨型硬件上限，底牌硬件腿 g2 回同业值并删除本行。`MRVL.US` 的同业务腿对照本行两个字段（同业值），不对照底牌。与 `NVDA.US` A22 同尺 | active | A18 / A25；valuation-rules「6% 的含义」「巨型硬件上限」；与 `NVDA.US` A22 | `g2_cand`、`g2_nonai_cand`；候选带一行 |
# | A23 | **归篮**：已承销 XPU / AI 网络 / 非 AI / 软件四腿 → **篮 4 龙头制造**（常规经营现金流：软件年金 + LTA 承销，可见度高；备选篮 6 周期商品 / 小盘 13%，只作对照带）；XPU 实验室腿 → **篮子对**（`valuation-rules`「篮子对」，2026-09-23）：**过渡篮 7 单押 / 故事**（今天收入依赖 XPV 融资 close 与 RVG 或有负债，A7 判据）→ **终值篮 4 龙头制造**（实验室做成了的世界里 Anthropic / OpenAI 用自身收入付账，与已承销的 Google / Meta 同类；稳态特征、共用 k_lab 0.30 与合篮条件由 `_AXIS.frontier-lab-funding` §3 一次定义，本票只引用）。**本票的第二层**：k_lab 只覆盖实验室腿**收入端**的到达风险；**RVG 残值担保**在实验室失败时是收入归零之外的**额外损失**，敞口规模 10-Q 未单独披露（`待补`），不进锚点，落在 `deep_discount` 档的场景解释。**禁双计声明**：L 档（消化年）已定价的是「FY28 实验室增量不兑现」，k_lab 收的是 FY27 基数部分「实验室付不起」的风险，两者不重叠；CAPM 粗筛 **12.1%**（β 1.8）——与篮 4 残差 +2.1pp < 3pp，但 β 是 AI 主题的市场 β，不是经营现金流的行业风险，进「篮子质疑」清单只作观察，不改篮。证伪点：篮级季度对账显示经营腿隐含 r 持续 ≥ 13% → 复审备选篮 6 | active | `gordon.BASKET_R`；CAPM β 1.8（yfinance 2026-09-11）；`_AXIS.frontier-lab-funding` §3 | `r_perp`、`r_lab`、`r_lab_t`、`k_lab` |
# | A24 | **ROE 口径 = 分子年盈利 ÷ 分子年年初净资产（\(E_{n+1}/B_n\)），账面按增长所需留存滚动（valuation-rules 裁决表 ② / 两段式过渡，2026-09-21 定）**：\(ROE_x = E_{FY27,x} ÷ BPS_{FY27 年初,x}\)，Gordon 的 \(g = b × ROE\) 里 ROE 是期初权益产出本期利润；旧版用 FY26Q3 权益直接作分母（少了 Q4 FY26 的留存），年末口径则会把 FY27 本年尚未产出的留存放进分母。FY27 年初 = FY26 末：从 FY26Q3 权益（20.18 美元/股，as-of 2026-08-02）起、只滚 **Q4 FY26 尚未入账**的利润 \(N\) = FY26 共识 11.658 − 9M FY26 实测 7.81（2.05 + 2.44 + 3.32）= **3.85 美元/股**，**留存率 = \(b_1 = g/ROE\)**——M/H 用公司 \(g_1\) 57.2%（五腿 g 按权重加总即它，与 `two_stage_pe` 段一同一个 b），L 无窗口用各腿 g2 的 EPS 加权 4.39%；ROE 与 BPS 互相依赖，闭式解 \(BPS = 20.18 / (1 − g × 3.85 / E_x)\)。得 BPS_FY27 年初 = **20.38 / 22.88 / 22.65**、ROE **85.1 / 81.5 / 89.2%**、\(b_1\) = 0.05 / 0.70 / 0.64（2026-10-03 腿利润率改推断后；旧口径 FY26Q3 权益 = 86.0 / 92.4 / 100.2%）。**L 的 ROE 反而高于 M**：M 按公司 g1 滚账面、留存更多，是口径的机械结果，不是政策。实付留存 59.5%（三年均值派息 40.5%，`payout_3y`）与 \(b_1\) 的差走 Outputs 披露行「模型视同派出、实际留存的现金」= (59.5% − \(b_1\)) × 3.85 = **+2.09 / −0.41 / −0.18 美元/股**——M/H 为负：模型按 g1 要求的留存高于实付留存，差额即段一派息率为负的「发股融资的增长」（A6），MUST NOT 另作腿。**影响**：ROE 下降使 M/H 的段一派息率从 −0.023 / +0.052 降到 −0.167 / −0.070（H 由自筹转为发股融资），倍数 18.7 / 26.9 / 27.3 → 18.7 / 26.5 / 27.0×，L/M/H 313.0 / 480.3 / 527.4 → **312.6 / 474.1 / 521.6**（−0.1% / −1.3% / −1.1%）（以上为 2026-09-21 ROE 纠正时的读数；2026-09-23 实验室腿改篮子对后的现行底牌见 §3 Outputs） | active | 8-K 新闻稿 Q1–Q3 FY26 non-GAAP EPS；FY26 共识 yfinance 2026-09-11；DPS / non-GAAP EPS FY23–25；valuation-rules 2026-09-21 | `eps_fy26_cons`、`eps_9m_fy26`、`payout_3y`（只进披露行）；表1 ROE 列；A6 / A17 |
# | A25 | **巨型硬件上限适用（valuation-rules「巨型硬件上限」，2026-09-27 定）**：逐腿判。**硬件腿** = 已承销 XPU / 实验室 XPU / AI 网络 / 非 AI 半导（收入来自交付芯片，多卖一单位要多一份 CoWoS 配额与晶圆，A16）；**软件腿**（VMware 订阅，$35B）是平台腿，不适用。② **分子年收入 ≥ \$1,500 亿**——FY27 = AI \$1,150 亿 + 非 AI \$170 亿 + 软件 \$350 亿 ≈ **\$1,670 亿**（FY28 指引 AI \$2,300 亿，只会更高；门槛按公司收入判，不按腿）；③ **未证明定价权**——第一条「无已量产的合格第二供应商」不成立：XPU 客户可换设计伙伴或自研（Google 已把 TPU 部分份额给联发科，§3 deep_discount 场景；Marvell 同做定制 ASIC），AI 网络面对英伟达 Spectrum-X / NVLink 与 Marvell，非 AI 半导有多家同类供应商；第二条不再审。→ 三条硬件腿底牌 g2 ≤ min(4%, r−4%) = 4%（篮 4 与实验室过渡篮 7 下同值），同业值进候选带（A22）。**复核条件**：大客户在两个财季内把定制 ASIC 份额从联发科 / 自研收回、只剩博通一家 → 重审定价权第一条；FY27 收入实际跌破 \$1,500 亿 → 不再适用 | active | valuation-rules 2026-09-27；本框架 A1 / A4 / A5 / A16；§3 表2 | `g2_xpu`、`g2_net`、`g2_nonai`、`g2_cand`、`g2_nonai_cand`；A18 / A22 |
# | A26 | **未建模期权 = 0 的理由（valuation-rules「未建模期权」，2026-10-03：份数只来自本票具名的量、扣掉共识已含部分）**：逐项盘点本票具名的量——① FY27 AI $115B / FY28 AI $230B 指引（≈10GW / ≈20GW，法说 2026-09-02）：FY27 在分子、FY28 在 g1 过渡年，且 FY28 卖方中位 30.48 与本票指引桥 31.37 只差 −2.8%（A8），视为已含；② XPV 平台「到 2028 年 >20GW」（10-Q FY26Q3）：与 ① 的 FY28 同一批量，已含；③ 六家 XPU 客户 FY27 + FY28 名义 ~30GW（Jefferies 103915）= 10.3 + ~20GW，已含；④ Anthropic FY28 增量 10GW、OpenAI FY28 5GW、Meta FY28 累计 3GW（GS 103909 / HSBC 103944）：都在 FY28 指引内；⑤ OpenAI 10GW 合作「2029 年底完成」（双方公告 2025-10-13）：FY27 1.3 + FY28 5 之后剩 ~3.7GW 落在 FY29——**低于** FY28 当年 5GW 的交付流量，而底牌在 FY28 之后按 4% 永续增长，已覆盖，不构成份数；⑥ Google 下两代 TPU（2028 / 2029 出货，UBS 108092）无量；⑦ 汇丰「到 2028 年非 Google 管线 1,800 亿美元」是 FY28 之内的单家估计；⑧ 10-Q 采购承诺 FY2029 仅 $85M。→ 没有超出「FY28 共识 + 底牌永续」的具名量，份数为 0，\(V_{opt}=0\)（不是因为无卖方台数）。CPO / 光学附着挂 `_AXIS.optical-comms` 只作宽口径诊断、不进锚点也不进期权（不存在「轴池子 × 本票份额」的期权）。**升级门槛**：公司给出 FY29 收入 / GW 目标、或新签具名客户的 FY29 量，超出 FY28 × 1.04 的部分按本票尺（篮子 r、本票 ROE、该腿 g2 4%）在兑现年估值、折回 FY27 进 \(V_{opt}\)；**证伪触发器**：OpenAI / Anthropic 的 FY28 GW 实际低于上表 → 回头审 A6 / A11，而不是期权 | active | 法说 2026-09-02（Wisburg 104074）；10-Q FY26Q3（XPV、采购承诺）；Jefferies 103915；GS 103909；HSBC 103944；UBS 108092；OpenAI–Broadcom 公告 2025-10-13 | \(V_{opt}\) 行；表2 `stretched` |
# | A27 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④，2026-10-16 框架纠正）**。① **超额现金**：不单列（净负债），无少数股东，归母比例 1；**增长期资金缺口**：资本开支季度约 $5 亿，经营现金流付得起，不计。② **稳态回报三段**：可见年 FY27（分子年）与 FY28（M/H 的 AI 两腿过渡年）用前瞻回报 85.1 / 81.5 / 89.2%（A24，五腿共用）。**芯片四腿**（已承销 XPU / 实验室 XPU / AI 网络 / 非 AI）：维持到 **Y1 = 2030** → 线性回落到 **Y2 = 2035**（光通信链「光引擎规格所有者」环节、高门槛，用户 2026-10-16 定）→ 稳态 **L / M 22% · H 30%**（2026-10-19 按序取 + 三档各取各的，用户 2026-10-19 认可）：同业层空——Silicon Labs 19.7 / Cirrus Logic 22.1 / 高通 112.9（回购失真）/ Semtech −8.9% 都是通用芯片设计，不是定制 XPU 与 AI 网络这门生意，按「同业须同一门生意」剔除（只作对照）→ L / M 取生意模式兜底「轻资产设计」22%；H = min(H 前瞻 89%, 30%) = 30%——拆不出周期的高成长腿，高档是定制芯片与网络优势守住的世界（四条芯片腿共用；非 AI 腿随同）。**VMware 软件腿**：不在光通信链上，走默认路径——Y1 = 可见年末 FY2028，企业基础软件判高门槛（迁移成本高、客户认证周期长）→ 回落 6 年，**Y2 = FY2034** → 稳态 **30%**（三档同）= 兜底「边际成本近零」：IBM 33.2%（含咨询与基础设施）/ SAP 13.5%（应用软件）都不是 VMware 这门基础设施软件生意，剔除、同业层空；H 档 min(H 前瞻, 30%) 也是 30%。自身周期层不可用：VMware 并入与 AI 定制芯片放量是结构变化（卖的东西与客户都变了），变化后未走完一轮（旧「只有 GAAP 序列、与前瞻不同公式」的弃用理由撤）。不属商品腿豁免。**g2 配对**：三条硬件腿 4% 是同业反解截顶值，按同一路径重解只会更高，仍被截住；软件腿 5.38%（微软 / IBM / Salesforce / 甲骨文中位）定性判断不变（只有甲骨文账面回报高于 30%，重解后仍是四家最低），未逐家精算。③ **时点对齐**：τ = 2026-08-02 → 2026-11-02 = 0.25 年（原「FY27 = t=1 不折现」撤回）；各腿按自己的过渡篮 r 折（实验室腿 15%）；窗口 = Q4 FY26 尚未入账 non-GAAP 利润 3.848 美元/股 × (1 − \(b_1\))，按 τ/2 折 → L 3.61 / M 1.14 / H 1.37；候选带的 Gordon 尺同走三段与时点对齐。④ **k**：k_lab 0.30 是篮子对规则强制的「走不到稳态」显式折扣，乘在实验室腿全部经营价值上，属具名规则对象，**保留**（不是视同派出的 k）；无其它 k。影响：M 406.3 → 357.7（−12.0%：三段约 −10%、时点对齐 −2.3%），未触发纠正对账门；2026-10-19 芯片腿 H 稳态 22% → 30%：H 391.1 → 403.0（+3.0%）；k_lab = 0 的对照 264.9 / 392.3 / 443.7 | active | valuation-rules「经营价值与超额现金」；Longbridge 年报（同业穿越周期）；FY26Q3 10-Q；对话 2026-10-16 | `tau`、`t0_cal`、`y1`、`y2`、`rs_semi`、`rs_semi_h`、`y1_sw`、`y2_sw`、`rs_sw`；锚点、候选带 |
# 原框架历史；本次迁移没有新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-09-20
# - v2 切换（篮子 r）：L/M/H v1 325.3 / 505.1 / 555.4 → 313.0 / 480.3 / 527.4（M ×0.95，只有实验室腿在动），zone `conservative` → `conservative`（但落敏感区：AI 腿 g2 −1pp → `neutral`，v1 在 −1pp 下仍 `conservative`）；篮子：经营四腿篮 4 龙头制造 10%（与 v1 `r_perp` 同值，备选篮 6 只作对照带）、XPU 实验室腿篮 7 单押 / 故事 15%（取代 v1 13% 条件性现金流档）；g2 四腿沿用同业反解值（cap = min(6%, r−4%) 在篮 4 / 篮 7 下均为 6%，未收紧）；v1 的「g2 杠杆 ±1pp 翻 zone 即 BLOCKED」改为敏感区披露；新增隐含 r(P) 行（δ +1.47%）与 A23 归篮；候选带 270.7 / 399.0 / 434.9 → 262.6 / 382.5 / 416.4。分子（FY27 五腿桥、FY28 过渡、CoWoS 轴）不动
# - touched: [A7, A18, A19, A21, A22, A23, r_perp, r_lab, 锚点, 候选带, 对照带, 敏感性]
# ### 2026-10-03
# - 迁移到 2026-10-03 规则（数据优先级与同业同尺 / 未建模期权由公开数据闭合）：**腿级经济性**——半导体分部内 XPU / 网络 / 非 AI 的利润率原为对话锁定的拍值 55 / 70 / 60%，改按层级用公开数据推断（FY25Q3 / FY26Q3 分部两期联立：AI 65.0%、非 AI 46.3%；AI 内 15pp 腿间差仍为拍值 → XPU 61% / 网络 76%；软件 84% 为分部实测不变，A9）；L/M/H 266.1 / 390.9 / 427.2 → **274.8 / 406.3 / 445.5**（M +3.9%，未触发纠正对账门），候选带 337.6 / 520.0 / 573.5 → 351.8 / 543.9 / 601.4；FY27 桥 17.88 → 18.65（vs 共识 −7.8% → −3.8%），裁决表 ②-b 由不过转为两条都过。**\(V_{opt}\)** 仍为 0，理由由「FY29 无已实现单位」改为逐项盘点具名量（A26）。增长表达（FY28 本票共识 n=1、无借用年、硬件 g2 截 4%）、分子年份（FY27 带区间共识最远年）核对合规不改；formula_id v4 → v5，eval 加推断复算校验
# - touched: [A6, A8, A9, A17, A20, A21, A22, A24, A26, om_xpu, om_net, om_nonai, 推断输入行, 锚点, 候选带, 对照带, 敏感性, 交叉校验, eval]
INPUTS = {
    # Q4 指引稀释股本量级; 来源：2026-09-02
    'shares': 4.94e9,
    # 股东权益 USD，FY26Q3 10-Q（季末 2026-08-02；yfinance 资产负债表 2026-07-31 列）；含商誉 $97.8B；三档 ROE 的**起点**——÷ shares = 20.18 美元/股，按增长所需留存 \(b_1=g/ROE\) 滚过 Q4 FY26 到 FY27 年初再作分母（A17 / A24），不直接作分母; 来源：2026-08-02
    'equity': 9.969e10,
    # 非 GAAP 税率; 来源：2026-09-02
    'tax_rate': 0.16,
    # below-the-line 每股拖累 USD；A14; 来源：2026-09-04
    'below_line_ps': 0.40,
    # FY27 AI 半导体 USD；A1; 来源：2026-09-02
    'rev_ai_27': 1.15e11,
    # FY28 AI 半导体 USD 指引；**只作 A8 桥校验，不进锚点**；A2; 来源：2026-09-02
    'rev_ai_28': 2.30e11,
    # AI 内 XPU 收入占比；A3; 来源：2026-09-04
    'xpu_share_ai': 0.73,
    # 非 AI 半导年化；A5; 来源：2026-09-02
    'rev_nonai_27': 1.7e10,
    # 同上持平；只作 A8 桥校验; 来源：2026-09-02
    'rev_nonai_28': 1.7e10,
    # 软件年化 ~$8.75B×4；A4; 来源：2026-09-02
    'rev_sw_27': 3.5e10,
    # 趋稳；只作 A8 桥校验; 来源：2026-09-02
    'rev_sw_28': 3.5e10,
    # XPU 腿 OP margin = AI 腿推断 64.99%（A9 两期联立）− 0.27 × 15pp 腿间差（**拍值**：AI 内 XPU / 网络无分拆利润披露、无卖方腿预测；15pp 差沿用对话锁定的 55 / 70）；eval 校验 0.73 × om_xpu + 0.27 × om_net 与推断值差 ≤ 0.5pp；A9; 来源：2026-10-03
    'om_xpu': 0.61,
    # AI 网络腿 OP margin = om_xpu + 15pp（拍值，同上）；A9; 来源：2026-10-03
    'om_net': 0.76,
    # 非 AI 半导 OP margin = 两期联立推断 46.34%（A9）；eval 校验差 ≤ 0.5pp; 来源：2026-10-03
    'om_nonai': 0.46,
    # 软件分部 OP margin：FY26Q3 10-Q 分部附注 7,325 / 8,752 = 83.7%（分部口径不含 SBC 与摊销，与 non-GAAP EPS 同口径）；A9; 来源：2026-09-02
    'om_sw': 0.84,
    # 半导体分部收入 FY26Q3（季末 2026-08-02），10-Q 分部附注；A9 两期联立第 2 期; 来源：2026-08-02
    'semi_rev_q3_26': 2.0839e10,
    # 半导体分部营业利润 FY26Q3（不含 SBC / 摊销 / 重组，分部口径），10-Q 分部附注；A9; 来源：2026-08-02
    'semi_oi_q3_26': 1.277e10,
    # AI 半导体收入 FY26Q3（法说 2026-09-02，Wisburg 104074）；A9; 来源：2026-09-02
    'ai_rev_q3_26': 1.67e10,
    # 半导体分部收入 FY25Q3（季末 2025-08-03），FY26Q3 10-Q 比较列；A9 两期联立第 1 期; 来源：2025-08-03
    'semi_rev_q3_25': 9.166e9,
    # 半导体分部营业利润 FY25Q3，同上；A9; 来源：2025-08-03
    'semi_oi_q3_25': 5.217e9,
    # AI 半导体收入 FY25Q3（公司 FY25Q3 披露 $5.2B；与 FY26Q3 16.7 ÷ (1 + 221%) = 5.20 吻合，高盛 103909）；A9; 来源：2025-09-04
    'ai_rev_q3_25': 5.2e9,
    # FY26Q4 收入指引（法说 2026-09-02）；只用于 A9 低侧敏感（指引隐含 AI 腿 margin）; 来源：2026-09-02
    'rev_q4_guide': 3.48e10,
    # FY26Q4 non-GAAP 营业利润率指引 ~66%；同上; 来源：2026-09-02
    'om_q4_guide': 0.66,
    # FY26Q4 AI 收入指引；同上; 来源：2026-09-02
    'ai_rev_q4_guide': 2.17e10,
    # FY26Q4 非 AI 半导收入指引；同上; 来源：2026-09-02
    'nonai_rev_q4_guide': 4.3e9,
    # FY26Q4 软件收入指引；同上; 来源：2026-09-02
    'sw_rev_q4_guide': 8.7e9,
    # XPU 内已承销客户（Google/Meta）占比；GW 代理，待补收入口径；A15; 来源：2026-09-04
    'xpu_uw_share': 0.39,
    # FY27 共识 EPS 均值（47 家，低 17.47 / 高 22.44）；g1 的分母、A8 桥校验基准；yfinance; 来源：2026-09-11
    'eps_fy27_cons': 19.38391,
    # FY28 卖方 EPS 中位：Citi 30.48（104001）/ BofA 31.12（103961）/ Jefferies CY28E 27.21（103915）；g1 的分子；A6; 来源：2026-09-03
    'eps_fy28_cons': 30.48,
    # 过渡年数（仅 FY28），只在 M/H 档、只作用于 AI 两腿；A6; 来源：2026-09-14
    'n_stage': 1,
    # 有 ≥2 家共识的远期年数（FY28）；FY29 无共识；`check_transition_years`; 来源：2026-09-14
    'n_consensus': 1,
    # 经营四腿（uw / 网络 / 非 AI / 软件）永续折现率 = **篮 4 龙头制造** 10%：常规经营现金流（备选篮 6 13%，只作对照带）；值 = `gordon.BASKET_R`；A7 / A23; 来源：2026-09-20
    'r_perp': 0.10,
    # XPU 实验室腿**过渡篮** = **篮 7 单押 / 故事** 15%：今天的收入依赖 XPV 融资 close + RVG 或有负债；用于 FY28 过渡段与把终值折回今天；值 = `gordon.BASKET_R`；A7 / A23; 来源：2026-09-23
    'r_lab': 0.15,
    # XPU 实验室腿**终值篮** = **篮 4 龙头制造** 10%：实验室做成了的世界里，Anthropic / OpenAI 是用自身收入付账的超大客户，与已承销的 Google / Meta 同类（`_AXIS.frontier-lab-funding` §3）；只用于终值资本化；A23; 来源：2026-09-23
    'r_lab_t': 0.10,
    # 实验室腿确定性等价折扣 = `_AXIS.frontier-lab-funding` §3b 共用值（eval 跨文件校验，单改本票即红）；三档共用，只乘实验室腿；A23; 来源：2026-09-23
    # **同业反解·巨型硬件截顶**·XPU 两档共用永续增速：半导体横截面 10 家良态中位 6.52% → 本票为巨型硬件（FY27 收入 ≥ $1,500 亿、未证明定价权，A25）→ cap = min(4%, r−4%) = 4%（valuation-rules「巨型硬件上限」；篮 4 / 篮 7 同为 4%）；超出部分进候选带（A22）；A18; 来源：2026-09-27
    'g2_xpu': 0.04,
    # **同业反解·巨型硬件截顶**·AI 网络永续增速：同一横截面（网络无独立良态同业）6.52% → 巨型硬件 cap 4%（A25）；A18; 来源：2026-09-27
    'g2_net': 0.04,
    # **同业反解·巨型硬件截顶**·非 AI 半导永续增速：中位(QCOM 5.26% / TXN 6.80% / NXPI 3.24%) = 5.26% → 巨型硬件 cap 4%（A25；原值进候选带 `g2_nonai_cand`）；A18; 来源：2026-09-27
    'g2_nonai': 0.04,
    # **同业反解**·软件永续增速 = 中位(MSFT 6.10% / IBM 5.44% / CRM 5.31% / ORCL 3.26%)；未触顶（cap 6%）；A18; 来源：2026-09-11
    'g2_sw': 0.0538,
    # **候选带**用：AI 三腿（已承销 XPU / 实验室 XPU / 网络）可见期后跑道 = 同业反解 6.52% 截到普通上限 6%（原底牌值）；同公式只换本字段与 `g2_nonai_cand`（A22）；不进底牌；`MRVL.US` 同业务腿对照本值; 来源：2026-09-27
    'g2_cand': 0.06,
    # **候选带**用：非 AI 半导同业反解原值 5.26%（未触普通上限 6%）；A22；`MRVL.US` comm 腿对照本值; 来源：2026-09-27
    'g2_nonai_cand': 0.0526,
    # 倍数护栏下沿 = 自身实测次年 PE 带低点 9.94×（2022-09 月末价 ÷ FY23 non-GAAP EPS）；A19; 来源：2026-09-14
    'pe_own_min': 9.9,
    # 倍数护栏上沿 = 自身实测次年 PE 带高点 34.37×（2025-11 月末价 ÷ FY26 共识）；A19; 来源：2026-09-14
    'pe_own_max': 34.4,
    # CoWoS 配额 **γ 状态**片数（NVDA 足额 → 本票被挤）；`_AXIS.cowos-capacity.md` §2。**映射与 NVDA 相反**：本票 L←γ; 来源：2026-08-28
    # CoWoS 配额 **β 状态**片数（等比例分摊）；同上; 来源：2026-08-28
    # CoWoS 配额 **α 状态**片数（ASIC 长约优先，本票足额）；同上；H 档 XPU/网络分子 = β × α/β = **+12.3%**; 来源：2026-08-28
    # CPO/NPO 实际 OE 出货 L；`_AXIS.optical-comms.md` §1。约束 AI 网络光学附着；**不**替代 CoWoS 配额; 来源：2026-10-02
    # 同上 M（广发证券（香港）2028E scale-up NPO）; 来源：2026-10-02
    # 同上 H（大摩 2028E）; 来源：2026-07-10
    # FY26 共识 non-GAAP EPS 均值（46 家，yfinance `0y`）；只用于把 Q4 FY26 尚未入账的利润滚进 FY27 年初净资产；A24; 来源：2026-09-11
    'eps_fy26_cons': 11.658,
    # 9M FY26 已入账 non-GAAP EPS = Q1 2.05 + Q2 2.44 + Q3 3.32（8-K 新闻稿 / yfinance Reported EPS）；从 `eps_fy26_cons` 里扣掉；A24; 来源：2026-09-02
    'eps_9m_fy26': 7.81,
    # 近三年实付派息率均值（DPS ÷ non-GAAP EPS：FY23 1.84/4.22 = 43.6% / FY24 2.11/4.86 = 43.4% / FY25 2.36/6.82 = 34.6%）；只进 A24 的 B 桶披露行，**不进**主尺的 BPS 推演（主尺按 \(b_1=g/ROE\) 滚）; 来源：2025-10-31
    'payout_3y': 0.405,
    # 时点对齐年数 = 估值基准日 2026-08-02（FY26Q3 10-Q 资产负债表日）→ 分子年 FY27 年初 2026-11-02，按实际月数 3 个月；各腿按自己的过渡篮 r 折（实验室腿 15%），窗口可分配利润按 `r_perp` 折 τ/2；A27; 来源：2026-10-16
    'tau': 0.25,
    # 稳态回报三段的日历起点 = 分子年 FY27（t = 1）；A27; 来源：2026-10-16
    't0_cal': 2027,
    # 四条芯片腿高回报期止点 Y1 = 光通信链「光引擎规格所有者」环节、高门槛；A27; 来源：2026-10-16
    'y1': 2030,
    # 四条芯片腿稳态起点 Y2；同上；A27; 来源：2026-10-16
    'y2': 2035,
    # 四条芯片腿 L / M 档稳态回报 = 生意模式兜底「轻资产设计」22%：自身周期因 VMware 并入与 AI 定制芯片放量（结构变化后未走完一轮）不可用；芯片设计成熟同业（Cirrus / Silicon Labs / 高通 / Semtech）都不是定制 XPU 与 AI 网络这门生意，按「同业须同一门生意」剔除，同业层空 → 兜底；用户 2026-10-19 认可；A27; 来源：2026-10-19
    'rs_semi': 0.22,
    # 四条芯片腿 H 档稳态回报 = min(H 前瞻, 30%)（「三档各取各的稳态」：拆不出周期的高成长腿，高档是定制芯片与网络优势守住的世界）；用户 2026-10-19 认可；A27; 来源：2026-10-19
    'rs_semi_h': 0.30,
    # VMware 软件腿高回报期止点 Y1 = 可见年末 FY2028（默认路径，不跟光通信链）；A27; 来源：2026-10-16
    'y1_sw': 2028,
    # 软件腿稳态起点 Y2 = Y1 + 6（企业基础软件判高门槛：迁移成本高、客户认证周期长）；A27; 来源：2026-10-16
    'y2_sw': 2034,
    # 软件腿稳态回报（三档同）= 生意模式兜底「边际成本近零」30%：SAP（应用软件）、IBM（含咨询与基础设施）都不是 VMware 这门基础设施软件生意，按「同业须同一门生意」剔除，同业层空 → 兜底（与旧值同）；H 档 min(H 前瞻, 30%) 也是 30%；用户 2026-10-19 认可；A27; 来源：2026-10-19
    'rs_sw': 0.30,
}
BASKETS = {"r_perp": 4, "r_lab": 7, "r_lab_t": 4}
REQUIRED = frozenset(INPUTS) | {'k_lab','cowos_quota_l','cowos_quota_m','cowos_quota_h','oe_l','oe_m','oe_h'}

def path_value(g1: float, n: int, g2: float, roe: float, r: float, r_terminal: float,
               t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the steady-state-return path (valuation-rules「经营价值与超额现金」②
    稳态回报三段; gordon.py's three-segment function is not built yet, so it lives here).

    Calendar years; t = 1 is the numerator year t0, the retention of year c earns from c+1.
    n stage-1 years at g1, payout 1 - g1/roe (not floored, as two_stage_pe), discounted at r
    (the journey basket); the post-transition stream is valued at r_terminal from year n on:
    g2 with RONIC = roe through Y1, linear to min(rs, roe) by Y2, steady after.  With
    rs >= roe this equals two_stage_pe(g1, n, g2, roe, r, r_terminal=...) / perpetual_pe."""
    rs_eff = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs_eff
        return roe + (rs_eff - roe) * (cal - y1) / (y2 - y1)

    if r_terminal - g2 <= 0:
        raise ValueError(f"perpetuity diverges: g2={g2} >= r_terminal={r_terminal}")
    pv, e = 0.0, 1.0
    for t in range(1, n + 1):
        pv += e * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
    post, k = 0.0, 1
    while True:
        cal = t0 + n + k - 1
        if cal > y1 and cal >= y2:
            post += e * min(1.0, 1.0 - g2 / rs_eff) / ((r_terminal - g2) * (1 + r_terminal) ** (k - 1))
            break
        post += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r_terminal) ** k
        e *= 1 + g2
        k += 1
    return pv + post / (1 + r) ** n


def is_mega_hw(inp: dict[str, float]) -> bool:
    """Numerator-year (FY27) revenue at or above the mega-hardware line (A25)."""
    return inp["rev_ai_27"] + inp["rev_nonai_27"] + inp["rev_sw_27"] >= MEGA_HW_REVENUE_USD


def eps_leg(rev: float, om: float, tax_rate: float, shares: float) -> float:
    return rev * om * (1.0 - tax_rate) / shares


def infer_leg_margins(inp: dict[str, float]) -> dict[str, float]:
    """A9 public-data inference (valuation-rules「公开数据推断」, 2026-10-03).

    Two periods (FY25Q3 / FY26Q3), two unknowns: the semiconductor segment
    operating income = AI revenue x m_ai + non-AI revenue x m_nonai, margins held
    constant across the two periods (operating leverage on the growing AI leg is
    then attributed to AI -- m_ai biased up, m_nonai down).  Cross-checks: the
    incremental margin (the delta is ~all AI) and the FY26Q4 guide-implied AI
    margin (company OM guide, software and non-AI at their inferred margins) as
    the low side.
    """
    a1, n1 = inp["ai_rev_q3_25"], inp["semi_rev_q3_25"] - inp["ai_rev_q3_25"]
    a2, n2 = inp["ai_rev_q3_26"], inp["semi_rev_q3_26"] - inp["ai_rev_q3_26"]
    o1, o2 = inp["semi_oi_q3_25"], inp["semi_oi_q3_26"]
    det = a1 * n2 - a2 * n1
    m_ai = (o1 * n2 - o2 * n1) / det
    m_nonai = (a1 * o2 - a2 * o1) / det
    incr = (o2 - o1) / (inp["semi_rev_q3_26"] - inp["semi_rev_q3_25"])
    oi_q4 = inp["om_q4_guide"] * inp["rev_q4_guide"]
    ai_q4 = (oi_q4 - inp["sw_rev_q4_guide"] * inp["om_sw"] - inp["nonai_rev_q4_guide"] * m_nonai) / inp["ai_rev_q4_guide"]
    return {"ai": m_ai, "nonai": m_nonai, "incr": incr, "ai_q4": ai_q4}


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    # Each r row must name its basket and carry that basket's value (A23).
    for key in ("r_perp", "r_lab", "r_lab_t"):
        if key not in baskets:
            errs.append(f"{key}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
        errs += check_r(inp[key], key, baskets.get(key))
    # g2 is capped by the r of every leg that reads it; the lab leg reads g2_xpu at r_lab.
    mega_hw = is_mega_hw(inp)
    for key in ("g2_xpu", "g2_net", "g2_nonai", "g2_sw"):
        errs += check_g_cap(inp[key], inp["r_perp"], key, mega_hw=mega_hw and key in MEGA_HW_KEYS)
        gap = inp["r_perp"] - inp[key]
        if gap <= 0:
            errs.append(f"perpetuity diverges on {key}: g2 >= r")
        elif gap < MIN_R_MINUS_G:
            errs.append(f"r - {key} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    # Lab leg = basket pair; its arrival haircut is the shared axis value (A23b).
    errs += check_basket_pair(inp["r_lab"], inp["r_lab_t"], "lab",
                              baskets.get("r_lab"), baskets.get("r_lab_t"))
    errs += check_k_declared(inp["r_lab"], inp["r_lab_t"], (inp["k_lab"],) * 3, "k_lab")
    # G_cap stays keyed to the JOURNEY basket (「篮子对」判据 3).
    errs += check_g_cap(inp["g2_xpu"], inp["r_lab"], "g2_xpu@r_lab", mega_hw=mega_hw)
    # Only FY28 carries a >=2-house consensus (A8); FY29 is a story.
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if inp["eps_fy28_cons"] <= inp["eps_fy27_cons"]:
        errs.append("FY28 consensus below FY27: the transition year has no growth to name")
    # Quota states must be ordered the AVGO way (γ < β < α); the axis check confirms the values.
    errs += ladder("cowos quota (γ<β<α)", inp["cowos_quota_l"], inp["cowos_quota_m"], inp["cowos_quota_h"])
    # Leg OM inputs must sit on the public-data inference (A9; R4 不准拍值覆盖有来源的数).
    inf = infer_leg_margins(inp)
    om_ai = inp["xpu_share_ai"] * inp["om_xpu"] + (1.0 - inp["xpu_share_ai"]) * inp["om_net"]
    if abs(om_ai - inf["ai"]) > OM_INFER_TOL:
        errs.append(f"AI-leg OM blend {om_ai:.4f} off the inferred {inf['ai']:.4f} (> {OM_INFER_TOL:.1%})")
    if abs(inp["om_nonai"] - inf["nonai"]) > OM_INFER_TOL:
        errs.append(f"om_nonai {inp['om_nonai']:.4f} off the inferred {inf['nonai']:.4f} (> {OM_INFER_TOL:.1%})")
    p_fields = [k for k in inp if k == "p" or k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    return errs



def evaluate(inp: dict[str, float],rate_inputs=None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp,('n_stage','n_consensus','t0_cal','y1','y2','y1_sw','y2_sw'))
    baskets = BASKETS
    errors = sanity_checks(inp, baskets)
    review_flags=[]
    s, t, bl = inp["shares"], inp["tax_rate"], inp["below_line_ps"]
    xpu_s, uw = inp["xpu_share_ai"], inp["xpu_uw_share"]
    r, n = inp["r_perp"], int(inp["n_stage"])

    # ---- Step 1: FY27 gross leg EPS on the β (nominal guidance) world ----
    rev_xpu_27 = inp["rev_ai_27"] * xpu_s
    rev_net_27 = inp["rev_ai_27"] * (1.0 - xpu_s)
    gross_m = {
        "xpu": eps_leg(rev_xpu_27, inp["om_xpu"], t, s),
        "net": eps_leg(rev_net_27, inp["om_net"], t, s),
        "nonai": eps_leg(inp["rev_nonai_27"], inp["om_nonai"], t, s),
        "sw": eps_leg(inp["rev_sw_27"], inp["om_sw"], t, s),
    }

    # ---- Step 2: tier numerators from the shared quota axis (A16) ----
    # Only the CoWoS-constrained legs scale; software and non-AI are off-axis.
    # Below-the-line drag (A14) is spread pro-rata so leg sums = gross - bl.
    quota_scale = {
        "L": inp["cowos_quota_l"] / inp["cowos_quota_m"],
        "M": 1.0,
        "H": inp["cowos_quota_h"] / inp["cowos_quota_m"],
    }

    def tier_legs(scale: float) -> dict[str, float]:
        gross = dict(gross_m)
        gross["xpu"] *= scale
        gross["net"] *= scale
        f = (sum(gross.values()) - bl) / sum(gross.values())
        net = {k: v * f for k, v in gross.items()}
        # XPU two-tier split (A15): underwritten LTA vs lab-dependent, every tier.
        return {
            "uw": net["xpu"] * uw,
            "lab": net["xpu"] * (1.0 - uw),
            "net": net["net"],
            "nonai": net["nonai"],
            "sw": net["sw"],
        }

    eps = {tier: tier_legs(quota_scale[tier]) for tier in TIERS}
    eps_total = {tier: sum(eps[tier].values()) for tier in TIERS}
    errors += ladder("numerator (γ/β/α)", eps_total["L"], eps_total["M"], eps_total["H"])

    # ---- Step 3: the FY28 transition year, consensus-to-consensus, carried by the AI legs only ----
    g1_co = inp["eps_fy28_cons"] / inp["eps_fy27_cons"] - 1.0
    ai_m = eps["M"]["uw"] + eps["M"]["lab"] + eps["M"]["net"]
    flat_m = eps["M"]["nonai"] + eps["M"]["sw"]
    g1_ai = ((1.0 + g1_co) * eps_total["M"] - flat_m) / ai_m - 1.0

    # ---- Step 4: tier ROE on the FY27 OPENING book; company ROE for every leg (A3 SOTP rule) ----
    # ROE = E_{n+1} / B_n: FY27 EPS over the FY27 opening book (= end-FY26), not
    # today's FY26Q3 book (valuation-rules 裁决表 ② as of 2026-09-21; A24).
    # The FY26Q3 book is rolled over the Q4 FY26 earnings not yet booked (FY26
    # consensus minus 9M actual, non-GAAP) at the GROWTH-REQUIRED retention
    # b1 = g/ROE -- the same b two_stage_pe charges in stage 1 -- not at the
    # actual payout complement.  M/H roll at the COMPANY g1 (the legs' g sum to
    # it); L has no window and rolls at its EPS-weighted leg g2.  Closed form:
    # BPS = BPS0 / (1 - g·N/eps).  Actual retention beyond b1 is the B bucket,
    # printed as a disclosure, not put into the book.
    unbooked = inp["eps_fy26_cons"] - inp["eps_9m_fy26"]  # per share, Q4 FY26 only
    bps_q3 = inp["equity"] / s
    g2_l = sum(eps["L"][leg] * inp[LEG_G2[leg]] for leg in LEGS) / eps_total["L"]
    g_roll = {"L": g2_l, "M": g1_co, "H": g1_co}
    bps_open = {tier: bps_q3 / (1.0 - g_roll[tier] * unbooked / eps_total[tier]) for tier in TIERS}
    roe = {tier: eps_total[tier] / bps_open[tier] for tier in TIERS}
    b1 = {tier: g_roll[tier] / roe[tier] for tier in TIERS}
    for tier in TIERS:
        if not (0.0 < b1[tier] < 1.0):
            errors.append(f"{tier} growth-required retention b1 = {b1[tier]:.3f} outside (0,1)")
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {tier: (ret_actual - b1[tier]) * unbooked for tier in TIERS}  # disclosure only

    # ---- Step 5: multiples per leg per tier; L runs no transition (digest world) ----
    # The lab leg is a basket PAIR (valuation-rules「篮子对」, _AXIS.frontier-lab-funding
    # §3): 篮 7 discounts the journey, 篮 4 capitalises the steady state -- a lab that
    # made it pays from its own revenue, like any hyperscaler.  With no transition
    # (L, and the no-transition cross-checks) the terminal rate is the only rate.
    # Every re-pricing below goes through this one function so the pair cannot
    # drift between the anchors and their sensitivities.
    # Operating value and time alignment (A27; valuation-rules「经营价值与超额现金」② 稳态回报
    # 三段 / ③ 时点对齐, framework correction 2026-10-16): every leg's Gordon runs on the
    # steady-state-return path -- chip legs Y1 2030 / Y2 2035 at the light-design steady (H tier 30%)
    # return, the VMware leg on the default path (Y1 FY2028 / Y2 FY2034) at the near-zero-
    # marginal-cost steady return -- and is discounted from the FY27 opening (t_n) to the
    # balance-sheet date by tau at the leg's journey basket.  The window (Q4 FY26 unbooked x
    # (1 - b1), floored at 0) is added to each tier at tau/2 on r_perp.
    tau, t0 = inp["tau"], int(inp["t0_cal"])

    def pe_at(leg: str, tier: str, g2: float, transition: bool, dr: float = 0.0) -> float:
        r_j, r_t = inp[LEG_R[leg]] + dr, inp[LEG_RT[leg]] + dr
        if leg == "sw":
            y1_, y2_, rs_ = int(inp["y1_sw"]), int(inp["y2_sw"]), inp["rs_sw"]
        else:
            # per-tier steady (三档各取各的稳态): H = min(H forward, 30%) for a chip leg
            # whose cycle cannot be stripped; L / M = the ordered value (fallback 22%).
            y1_, y2_ = int(inp["y1"]), int(inp["y2"])
            rs_ = inp["rs_semi_h"] if tier == "H" else inp["rs_semi"]
        if transition and leg in TRANSITION_LEGS:
            v = path_value(g1_ai, n, g2, roe[tier], r_j, r_t, t0, y1_, y2_, rs_)
        else:
            v = path_value(0.0, 0, g2, roe[tier], r_t, r_t, t0, y1_, y2_, rs_)
        return v * (1 + r_j) ** -tau

    win = {tier: max(unbooked * (1.0 - b1[tier]), 0.0) * (1 + r) ** -(tau / 2) for tier in TIERS}

    def leg_pe(leg: str, tier: str, transition: bool) -> float:
        return pe_at(leg, tier, inp[LEG_G2[leg]], transition)

    # k_lab leaves the lab leg's value only -- never its multiple, never another
    # leg, whose customers carry their own balance sheets (axis §3b).
    keep = {leg: (1.0 - inp["k_lab"]) if leg == "lab" else 1.0 for leg in LEGS}

    pes = {tier: {leg: leg_pe(leg, tier, transition=(tier != "L")) for leg in LEGS} for tier in TIERS}
    legs_ps = {tier: {leg: eps[tier][leg] * pes[tier][leg] * keep[leg] for leg in LEGS} for tier in TIERS}
    anchors = {tier: sum(legs_ps[tier].values()) + win[tier] for tier in TIERS}
    blended = {tier: anchors[tier] / eps_total[tier] for tier in TIERS}
    L, M, H = (anchors[tier] for tier in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    # Guardrail (裁决顺序 ③, A19): every blended tier multiple inside the ticker's own
    # realised next-FY PE band.
    for tier in TIERS:
        if not (inp["pe_own_min"] <= blended[tier] <= inp["pe_own_max"]):
            review_flags.append('historical_multiple_outside_band')
            break

    # Re-price one tier with a g2 shift on a subset of legs (same construction as above).
    def anchor_at(tier: str, delta: float, shifted: tuple[str, ...]) -> float:
        return sum(
            eps[tier][leg] * keep[leg]
            * pe_at(leg, tier, inp[LEG_G2[leg]] + (delta if leg in shifted else 0.0), tier != "L")
            for leg in LEGS
        ) + win[tier]

    # Band-edge Δg (③ 带即证据): shift every leg's g2 by the same Δ until the M-tier
    # blended multiple reaches each edge of the own band.  Reported, never used.
    def blended_at(tier: str, delta: float) -> float:
        return anchor_at(tier, delta, LEGS) / eps_total[tier]

    def delta_to(target: float, tier: str) -> float:
        lo, hi = -0.20, r - max(inp[k] for k in ("g2_xpu", "g2_net", "g2_nonai", "g2_sw")) - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if blended_at(tier, mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_dg = (delta_to(inp["pe_own_min"], "M"), delta_to(inp["pe_own_max"], "M"))

    # ---- Step 6: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat = flat_multiple_ladder((eps_total["L"], eps_total["M"], eps_total["H"]), blended["M"])
    errors += flat_errs
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (blended["L"], blended["M"], blended["H"]))
    # Same split on the FY28 basis: L's digest world holds FY28 = FY27, M/H carry the AI
    # legs' g1.  On this basis the L gap is a numerator statement and the multiples sit
    # flat -- the FY27-basis "L gap is mostly multiple" is that same statement projected
    # onto the numerator year, not a multiple policy (A2e-2d does not fire).
    eps28 = {
        tier: sum(eps[tier][leg] * ((1.0 + g1_ai) if tier != "L" and leg in TRANSITION_LEGS else 1.0) for leg in LEGS)
        for tier in TIERS
    }
    dec28 = decompose((L, M, H), tuple(anchors[tier] / eps28[tier] for tier in TIERS))

    # ---- Step 7: A8 bridge guard — guidance bridge vs consensus, both years ----
    dev27 = eps_total["M"] / inp["eps_fy27_cons"] - 1.0
    eps28_guide = (
        eps_leg(inp["rev_ai_28"] * xpu_s, inp["om_xpu"], t, s)
        + eps_leg(inp["rev_ai_28"] * (1.0 - xpu_s), inp["om_net"], t, s)
        + eps_leg(inp["rev_nonai_28"], inp["om_nonai"], t, s)
        + eps_leg(inp["rev_sw_28"], inp["om_sw"], t, s)
        - bl
    )
    dev28 = eps28_guide / inp["eps_fy28_cons"] - 1.0
    if abs(dev27) > BRIDGE_TOL:
        review_flags.append('historical_fy27_consensus_bridge_difference')
    if abs(dev28) > BRIDGE_TOL:
        review_flags.append('historical_fy28_consensus_bridge_difference')

    # ---- Step 8: stated values, axis mounts ----
    A, B = cut_points(L, M, H)

    # ---- Step 9: g2 leverage (valuation-rules「g₂ 的杠杆 MUST 显式」), disclosure only ----
    # The AI legs' g2 shifted ±1pp together (lab reads g2_xpu too); +1pp sits above
    # g_cap and is not a legal state.
    lever = []
    for delta in (-0.01, +0.01):
        if inp["g2_xpu"] + delta > g_cap(r, is_mega_hw(inp)) + 1e-9:
            continue
        lmh = tuple(anchor_at(tier, delta, TRANSITION_LEGS) for tier in TIERS)
        lever.append((delta, *lmh))

    inf = infer_leg_margins(inp)
    ai_cap_hit = inp["g2_xpu"] + band_edge_dg[1] > g_cap(r, is_mega_hw(inp)) + 1e-9
    l_with_transition = sum(eps["L"][leg] * keep[leg] * leg_pe(leg, "L", transition=True) for leg in LEGS)
    m_no_transition = sum(eps["M"][leg] * keep[leg] * leg_pe(leg, "M", transition=False) for leg in LEGS)
    h_no_transition = sum(eps["H"][leg] * keep[leg] * leg_pe(leg, "H", transition=False) for leg in LEGS)

    # A22 candidate band: same formula, the hardware legs' g2 back to their peer
    # values (the post-horizon runway the mega-hardware cap keeps out of the base).
    def cand_leg_pe(leg: str, tier: str) -> float:
        if leg in TRANSITION_LEGS:
            g2 = inp["g2_cand"]
        elif leg == "nonai":
            g2 = inp["g2_nonai_cand"]
        else:
            g2 = inp[LEG_G2[leg]]
        return pe_at(leg, tier, g2, tier != "L")

    candidate={'status':'unavailable','label':'硬件长期增长候选','anchors':None}
    try:
        if (check_g_cap(inp['g2_cand'],r,'g2_cand') or
                check_g_cap(inp['g2_nonai_cand'],r,'g2_nonai_cand') or
                r-max(inp['g2_cand'],inp['g2_nonai_cand'])<MIN_R_MINUS_G):
            raise ValueError('candidate growth outside model domain')
        cand=tuple(sum(eps[tier][leg]*keep[leg]*cand_leg_pe(leg,tier) for leg in LEGS)+win[tier] for tier in TIERS)
        if all(math.isfinite(x) for x in cand) and 0<=cand[0]<cand[1]<cand[2]:
            candidate={'label':'硬件长期增长候选','anchors':dict(zip('LMH',cand))}
    except (ValueError,ZeroDivisionError,OverflowError):
        pass

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # every priced r 1:1 through pe_at's dr — r_perp (operating legs), the lab
    # pair's journey r_lab (M/H transition) and terminal r_lab_t; g1/g2, tier
    # ROE, numerators and k_lab stay put.  Base deck only.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        lmh = [
            sum(eps[tier][leg] * keep[leg] * pe_at(leg, tier, inp[LEG_G2[leg]], tier != "L", dr=dr) for leg in LEGS)
            + win[tier]
            for tier in TIERS
        ]
        return lmh[0], lmh[1], lmh[2]

    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    result = {
        "ticker": "AVGO.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-08-02',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of':'2026-10-16',
        "anchors": anchors,
        "candidate": candidate, "option": None,
        'review_flags':review_flags+['historical_single_source_cowos_allocation',
            'historical_inferred_segment_margins','historical_frontier_funding_haircut_unverified'],
        "cut_points": [A, B], "rev_xpu_27": rev_xpu_27, "rev_net_27": rev_net_27,
        "gross_m": gross_m, "quota_scale": quota_scale, "eps": eps, "eps_total": eps_total,
        "g1_co": g1_co, "g1_ai": g1_ai, "unbooked": unbooked, "bps_q3": bps_q3,
        "g2_l": g2_l, "g_roll": g_roll, "bps_open": bps_open, "roe": roe, "b1": b1,
        "excess_cash": excess_cash, "win": win, "keep": keep, "pes": pes, "legs_ps": legs_ps,
        "blended": blended, "band_edge_dg": band_edge_dg, "flat": flat, "dec": dec,
        "eps28": eps28, "dec28": dec28, "dev27": dev27, "eps28_guide": eps28_guide, "dev28": dev28,
        "lever": lever, "inf": inf, "ai_cap_hit": ai_cap_hit, "l_with_transition": l_with_transition,
        "m_no_transition": m_no_transition, "h_no_transition": h_no_transition,
        "parameters": {"discount": {"operating": r, "lab_journey": inp["r_lab"], "lab_terminal": inp["r_lab_t"]},
                       "growth": {leg: inp[LEG_G2[leg]] for leg in LEGS}, "forward": roe,
                       "mature": {tier: {leg: min(roe[tier], inp["rs_sw"] if leg == "sw" else
                           (inp["rs_semi_h"] if tier == "H" else inp["rs_semi"])) for leg in LEGS} for tier in TIERS}},
    }
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',
            priced_r={'r_perp':r,'r_lab':inp['r_lab'],'r_lab_t':inp['r_lab_t']},band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs,base_anchors=(L,M,H)))
    return result


def calculate(context):
    cowos=context['axes']['cowos']['quotas']
    optical=context['axes']['optical']['oe']
    selected={f'cowos_quota_{t}':cowos[t.upper()] for t in 'lmh'}
    selected.update({f'oe_{t}':optical[t.upper()] for t in 'lmh'})
    selected['k_lab']=context['axes']['lab']['k_lab']
    result=evaluate({**INPUTS,**selected},context.get('rate_inputs'))
    result['basis_changed']=None
    if any(not math.isfinite(INPUTS[k]) for k in ('g2_cand','g2_nonai_cand')):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'shared':selected},HISTORICAL_PARTIAL_FINGERPRINT)
    result['units']={'price':'USD_PER_SHARE'}
    result['segments']={leg:{'unit':'USD_PER_SHARE','values':{
        tier:result['legs_ps'][tier][leg] for tier in TIERS}} for leg in LEGS}
    result['segments']['window']={'unit':'USD_PER_SHARE','values':dict(result['win'])}
    result['key_parameters']={
        'discount_rate':{'operating':INPUTS['r_perp'],'lab_transition':INPUTS['r_lab'],
                         'lab_terminal':INPUTS['r_lab_t']},
        'growth_rate':{leg:INPUTS[LEG_G2[leg]] for leg in LEGS},
        'forward_return':dict(result['roe']),
        'steady_return':{tier:{leg:min(result['roe'][tier],INPUTS['rs_sw'] if leg=='sw' else
            (INPUTS['rs_semi_h'] if tier=='H' else INPUTS['rs_semi'])) for leg in LEGS} for tier in TIERS}}
    return result
