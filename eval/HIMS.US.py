#!/usr/bin/env python3
"""HIMS legacy valuation, migrated without updating financial judgments.

Amounts are USD millions and per-share USD. Zacks figures exclude non-recurring
items while including stock compensation; the single-house candidate is not consensus.
"""
from __future__ import annotations
from lib.gordon import basket_r, check_branch, check_g_cap, check_r, perpetual_pe, two_stage_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

FORMULA_ID = "hims_fy28_consensus_gordon_b4_v3"
TOL = 0.05
NUM_YEAR = 2028
T1_YEAR = 2027
# | A1 | 林奇主类 `fast_grower`：2026E / 2027E 收入 +37% / +25%；L 退到 FY2028 共识下沿（Zacks 最悲观一家，净利率 2.6%）；实证坐标：2026-02 月内低 13.74（Longbridge 月 K） | active | yfinance / Zacks 2026-10-04 | 主尺骨架 |
# | A2 | **分子年份 = FY2028E EPS 共识区间**（Zacks 经 Nasdaq，4 家，0.50 / 0.85 / 1.18，2026-10-04）：FY2028 是最远「≥2 家且带区间」年 → 按裁决顺序 ② 进分子、折一年；FY2029 只有 1 家（1.37）→ 候选带（A8）；FY2030 无逐家预测。**口径**：Zacks EPS 剔除非经常项、保留 SBC（2026Q1 / Q2 实际 −0.18 / −0.10 vs GAAP −0.40 / −0.37，差在一次性并购 / 重组费用）；2027 年起无已知一次性项，两源 FY2027 均值 0.44（Zacks 5 家）vs 0.42（yfinance 11 家，GAAP）差 5% → **视同近 GAAP**。互证：WallStreetZen FY2028 0.49 / 0.81 / 1.24。证伪 / 复核：FY2028 两源均值差 >15%，或 Zacks 区间内出现明确的调整后口径 → 回对话 | active | `api.nasdaq.com` earnings-forecast / earnings-surprise；yfinance；WallStreetZen | `eps_fy28e_*` |
# | A3 | **整公司尺**：单一分部 | active | Longbridge business-segments | 主尺骨架 |
# | A4 | **归篮：篮 4 常规经营 10%（初分篮 7 已推翻，2026-10-04）**。初分篮 7 的判据是「GLP-1 依赖 Novo / Lilly 供货且两者是竞争者、复方制剂 FDA 执法、肽类合法化未落定、共识跨零」——按 2026-10-03 篮 7 判据（只认对手方与国别）逐条不成立：付钱的是约 290 万分散订户，无单一客户 ≥50% 或前两大 ≥70%；无高国别风险；收入不依赖未落定融资或未签约客户；供应依赖、监管、未盈利不是归篮理由。篮 4 判据正向成立：常规经营现金流；盈利不是商品价函数（订阅价公司自定）；不命中篮 1 / 2 / 3 / 5 / 7。篮子对不适用（今天就不满足篮 7）。CAPM 粗筛 = 4.0% + β 2.41 × 4.5% = **14.8%**，与篮 4 偏离 +4.8pp（> 3pp）：β 来自 2024–2026 股价随 GLP-1 监管与合作新闻的大幅波动，是价格波动不是要求回报（篮 7「高 β 不是归篮理由」同源）。初分篮对照带见 Outputs。证伪点：出现单一合作方占收入 ≥50%（例：Novo 品牌药渠道成为主要收入且合同可单方终止）→ 回篮 7 审 | active | yfinance β；Wisburg 92949 / 85749；valuation-rules「r 篮子」2026-10-03 | `r_perp` |
# | A5 | **永续 \(g_2\) = 4%，无同业锚**（美国长期名义增速：FOMC 2026-09 SEP 长期实际 2.0% + 通胀 2%；CBO 2026 潜在实际 1.7%；同 `_AXIS.rates` USD \(r_f\) 中枢）。同业横截面（2026-10-04 收盘 ÷ 下一财年共识 EPS，各按自己篮 4 r 10% 判域，均不分红 → 留存分支）：LifeMD 7.2×、ROE 230% 单调区不可达；Chewy 9.7×、ROE 114% 不可达；Talkspace 23.9×、ROE 33% → 6.67%（2 家覆盖）；Warby Parker 44.0×、ROE 17% → 8.92% 与 LifeStance 22.3×、ROE 14% → 8.21% 均 \(r-g<2\%\) 病态、不作锚；GoodRx 9.3×、ROE 6% 峰形区（跨域，只交叉，0.97%）；Hinge / Omada / Progyny / Doximity 为 B2B 数字医疗或医生网络，不同生意；Teladoc / Amwell / DocMorris 亏损；Redcare / 平安好医生峰形区不可达；京东健康 / 阿里健康国别不同。剩 Talkspace 1 家 → 只作互证。方向门：分子年已是最远带区间年、更远年无 ≥2 家点估计 → 取自身实测：2023 → 2025 归母净利由负转正，方向为正，\(g_2>0\) 可用 | active | yfinance 2026-10-04；valuation-rules「6% 的含义」「\(g_2\) 来源优先序」 | `g2` |
# | A6 | **ROE 口径与上限**：起点 BPS = 2026-06-30 权益 3.24 亿 ÷ 2.33 亿股 = 1.389；滚入未入账共识利润（2026H2 = FY2026 共识 −0.56 − H1 实测 −0.775 = +0.215；FY2027 0.42）× 留存 \(g_2/ROE_M\) → FY2028 年初 BPS 1.432；L / M / H 档 ROE 35% / 59% / 82% → 截到 60%（同 LLY A4 的处理）；不含回购 / SBC 增股 | active | yfinance 季度资产负债表 | `equity` / `roe_cap` |
# | A7 | **\(V_{opt}\) 链（construction §7c-1 / §7c-7）**：份数 = 公司 2030 收入目标 65 亿 − 底牌已含 2030 收入（FY2028 收入 44.90 亿 × 1.04² = 48.56 亿）= **16.44 亿**（k = 1；2030 后继续增长只落 \(p_k\)）。FY2028 收入 = yfinance FY2027 收入共识 39.97 亿 × WallStreetZen FY2027 → FY2028 比值 1.123（该站绝对值单位错乱、只取比值；**来源偏弱**，9 家聚合 44.69 亿互证）。单位经济 = 最远可见年 FY2028 公司级共识净利率 4.42%（0.85 × 2.333 亿股 ÷ 44.90 亿）→ 增量 EPS 0.311 → 本票尺 `perpetual_pe(4%, 60%, 10%)` = 15.56× → 2030 年 4.84 → ÷ 1.10³（2030 → FY2027）= 3.64（旧口径）；同走稳态回报路径并同底牌时点对齐（再 ÷ 1.10^0.5）= **\(V_{opt}\) 3.22**（A17）。兑现年 = 公司目标年 2030（具名）。\(p_k\) 0 / 0.25 / 1.0：\(p_L\) = 0（共识低端世界不背 2030 目标）；\(p_M\) **无概率锚·拍值**（取 `GOOG.US` / `TSEM.US` 同量级）。敏感：FY2029 单家推得 6.34% → 5.22；公开数据推断（2030 调整后 EBITDA 13 亿 ÷ 65 亿 = 20% − 2025 年调整后 EBITDA 率与 GAAP 净利率之差 8.07pp ≈ 11.97%）→ 9.86；2025 实测 5.47% → 4.50；FY2027 共识 2.45% → 2.02；兑现推迟一年（底牌已含收入同步多长一年）→ 2.92。注意：选用的 4.42% 低于 2025 实测 5.47%——卖方共识认为 2028 年 GAAP 净利率还回不到 2025 年。升级门槛：≥2 家卖方给出 FY2029+ 收入 / EPS → 做成过渡年并同步缩减份数；更好的 FY2028 收入共识来源 → 替换 `rev_growth_28`；证伪：公司下调或撤回 2030 目标 | active | JPM 85749（2030 目标）；yfinance / WallStreetZen 2026-10-04；valuation-rules「未建模期权」 | `rev_2030_target` / `rev_fy27e` / `rev_growth_28` / `t_opt` |
# | A8 | **候选带与候选坐标**：① 候选带 = 同公式，FY2029 Zacks 单家 1.37 作过渡增速 \(g_1\) = 1.37 ÷ 0.85 − 1 = 61%、n = 1，只 M / H 背过渡（共识低端世界不背高速过渡），L′ = L → M′ 14.79、H′ 22.33（同走各档回报路径与时点对齐，A17）；升级门槛：FY2029 出现第二家点估计 → 升级为底牌 \(g_1\)。② 候选坐标（不成带）= 巴克莱 2027 调整后 EPS 2.48（单家）× 同一把尺（M 档回报路径、分子年初 2027-01-01 折 0.5 年）= 31.23；升级门槛：第二家调整后 2027E EPS，或公司给出 non-GAAP EPS 指引 → 主尺分子口径改为调整后并在 §1 写明 SBC 处理 | active | Zacks 2026-10-04；Wisburg 92949 | `eps_fy29e_single` / `eps_adj_fy27_house` |
# | A9 | **EV/EBITDA 交叉（用户指定的 A 路径，只交叉不定 zone）**：JPM 22× 2027E EBITDA 4.14 亿 → 36.0；巴克莱 17× 4.76 亿 → 31.7；共识收入 40.0 亿 × 巴克莱 14.5% = 2027E EBITDA 5.8 亿（只作口径参照）。不作主尺的理由：EBITDA 不扣 SBC（1.35 亿 / 年）与 capex（2.4 亿 / 年），现金转化率低 | active | Wisburg 92949 / 85749 | `ebitda_fy27_*` / `m_ev_*` |
# | A10 | **杠杆门**：净债 7.05 亿 / 2025 调整后 EBITDA 3.18 亿 = **2.2**（GAAP EBITDA 1.60 亿口径 4.4 → 触发；两口径并列）；利息 `待补`（可转债票息低）。按调整后口径未触发；GAAP 口径触发但本票 ROE 已按 60% 截顶、留存只进 \(g_2\) 4%，ROIC 拆解对倍数影响 < 1 turn，写明不另拆。可转债 10 亿（2030 年到期，转股价 `待补`）按债计 | active | yfinance 三表 | `net_debt` / `net_debt_ebitda` |
# | A11 | **卖方差额表**：本仓 H 15.43 vs 卖方 TP 中位 31.5（2026-09-21）= 0.49；差额来源：① 调整后 vs GAAP 分子（候选坐标 31.23 已入位）② EV/EBITDA 口径（交叉已入位）③ 2030 目标（\(V_{opt}\) 3.64，A7）④ FY2029 继续高增（候选带 H′ 24.43，A8）；其中 ① ④ 有可升级的门槛 | active | 2026-10-04 | §0「这张表怎么读」 |
# | A12 | **Q3'26 指引兑现**：管理层指引收入 **8.80–9.00 亿**、调整后 EBITDA **0.75–0.95 亿**（利润率约 9%–11%）。三季报实际落在区间内 → `confirmed`；收入或调整后 EBITDA 任一低于下沿、或同时下调全年收入 31–33 亿 / 调整后 EBITDA 2.75–3.25 亿 → `weakened`；收入同比增速明显掉出「仍是快增长」叙事（粗判：指引隐含约 +47%～50%，若实际个位数或负增）→ 回对话是否改 A1 | active | Q2'26 8-K / 电话会指引；待 Q3'26 实测 | 支撑 A1 增速；间接托住 FY2028 共识分子（A2） |
# | A13 | **减重订阅仍在放量**：品牌 GLP-1（Wegovy 等）路径下，减重向净新增维持管理层曾表述的量级——**约每月 ≥10 万**（或以季报披露的减重/体重管理订阅净增折算等价）。连续两个完整季显著低于该量级、且无「客单价 / 留存抬升」对冲 → `weakened`（GLP-1 增长主力叙事松动，L 情景权重上升）；单季波动不改状态 | active | Q1'26 电话会「每月 >10 万」表述；Q2 末总订阅约 290 万；待 Q3 订阅 / 品类披露 | 支撑 A1 |
# | A14 | **毛利率企稳**：品牌药切配后，合并毛利率以 Q2'26 约 **64%** 为近端锚，**不再出现连续两季 ≥3pp 的下行**（相对该锚或环比）。再下一台阶 → `weakened`（单位经济差于共识路径，A7 的净利率锚更难兑现；FY2027 GAAP 转正时间后移风险 ↑）；单季噪音或国际并表一次性拖累需在证据列注明后再判 | active | Q2'26 毛利率约 64%（上年同期约 76%）；专属属性 A | 影响 A2 分子可信度与 A7 单位经济 |
# | A15 | **国际：规模优先、利润不拖垮**：FY2026 国际收入 **≥6 亿**（公司口径），且国际调整后 EBITDA **接近盈亏平衡**（公司表述：at or near breakeven）。规模达标但明显亏损拖累合并调整后利润率 → `weakened`；规模显著不及（无并表口径解释）→ `weakened` 并回看 A1 收入指引 | active | Q2'26 8-K / 电话会（国际 Q2 约 1.31 亿；Eucalyptus 2026-06 已并；全年 ≥6 亿指引） | 支撑 A1 收入 |
# | A16 | **纠正对账门未过，用户拍板落盘（2026-10-04）**：M 3.74 → 12.01（+221%）触发对账门；坐标分两组、相差约十倍——账面 / 盈利÷r 一组（3.50–7.73）与市场在同等盈利月份付过的价一组（42–57）；新 M 落在两组之间、离每个坐标都 >20%。\(E_M/r\) 是 \(g=0\) 的尺，与新 M（\(g_2\) 4% Gordon）不同式，计为独立坐标。同等盈利月份只有 3 个（2025-08 → 10，TTM EPS 0.80 含 2024Q3 一次性税收利得），③ 带测试不适用。判断：两组参照本身互相差一个数量级，门在本票判不了。复核条件（任一触发即重跑对账门）：(a) 出现 ≥6 个 TTM EPS 落在 \(E_M\) ±12% 的月份；(b) FY2028 共识均值变动 >25%；(c) 篮子表或 \(g_2\) 来源变化 | active | Outputs「纠正对账门」行；valuation-rules「纠正对账门」2026-10-04 | Outputs 披露行 |
# | A17 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④，2026-10-16 纠正）**：**超额现金未单列**——净债 7.05 亿（债务 15.46 亿含可转债 − 现金 8.41 亿），\(C_{ex}\) = 0；无少数股东，归母比例 1。**增长期资金缺口：不计**——实测经营现金流（2024 / 2025 年 2.51 / 3.00 亿）付得起资本开支（2.43 亿 / 2026H1 0.69 亿），没有经营现金流付不起、且产出落在 FY2028 之内的扩产。**时点对齐**：基准日 2026-06-30（10-Q 账面 = BPS 起点）→ 分子年初 2028-01-01，τ = 1.5；原「FY2028 = 当前财年 +2，折一年」先还原再按 τ 重做（净多折 0.5 年）。**窗口可分配利润**（2026H2 + FY2027，与分子同口径的近 GAAP 利润、已扣股权激励）= (−0.56 − (−0.775) + 0.42) = 0.635/股 × (1 − b)，b = g2 / ROE_M = 0.067（框架滚账面用的留存率）→ 0.59/股，按 τ/2 折。**稳态回报三段**（②）：前瞻 ROE 34.9 / 59.4 / 60.0%（截顶）；不挂需求轴，默认路径 Y1 = 可见年末 2028；进入门槛判**低** → 回落 2 年，Y2 = 2030——依据：DTC 远程处方没有产能壁垒（新平台数月可上线）、客户无认证周期、复方 GLP-1 时期新进入者一两年内就抢到份额、单位投资额很低。稳态值（2026-10-19 按序取 + 三档各取各的，用户认可）：自身周期——2023 年前亏损、无一轮完整周期，不可用；同业层空——满足成熟判据（近 5 年收入复合 ≤ 10%、≥ 5 年读数）的只剩 GoodRx（收入复合 7.7%，投入资本口径 FY2021–25 均值 2.4%），但它是处方比价 / 优惠券平台，不是 DTC 处方订阅 + 自营药房这门生意，单一非同生意同业剔除；Teladoc 收入复合 18.3% 不满足成熟判据，剔除；Doximity 增速 17% 不算成熟 → 落兜底。兜底档取**「轻资产组装」18%**：HIMS 有药品成本（毛利率约 64–75%）、自营药房与复方产能，不是「边际成本近零（平台）」（旧取 30%）。**L / M = 18%**；**H = min(H 前瞻 60%, 30%) = 30%**——拆不出周期的高成长腿，高档是订阅品牌与交叉销售优势守住的世界。期权（A7）的成功世界是公司 2030 目标兑现，取 H 档的 30%；候选带（A8，可见年末顺延到 2029）M′ / H′ 各走 M / H 档路径；巴克莱候选坐标走 M 档路径。g2 4% 是具名宏观值，不重解。无 k | active | Longbridge 年报 2026-10-16；10-Q 2026-06-30；yfinance 现金流；GoodRx / Teladoc SEC companyfacts（`_local/tmp/round9/sweep/HIMS.US/`） | `tau`、`y1`、`y2`、`rs_steady`、`rs_steady_h`、`r_disc`；全部锚点、V_opt、候选带 |
# 历史规则调整（本次迁移没有新增数据更新）：
# （初建日不写条目。）
# ### 2026-10-03
# - 规则迁移（valuation-rules「未建模期权」2026-10-03）：\(V_{opt}\) 0 → 1.72——份数改为 2030 收入目标减 FY2027 收入共识（25.0 亿，原为整份 65 亿）、单位经济改为 FY2027 共识净利率 2.45%（原为 2025 实测快照 5.47%）、按兑现年 2030 把增量折回 FY2027（原为折锚点再减 H）；新增 \(p_k\) 0 / 0.25 / 1.0 与表3。底牌 L/M/H 1.39 / 3.74 / 14.40 不变。`formula_id` → `_v2`。
# - touched: [题头, §0, 属性 B, A7, A11, Inputs `t_opt`（替 `n_opt_years` / `v_opt`）, Formula 步 4, Outputs, 表3, eval]
# ### 2026-10-04
# - 重做：篮 7 → 篮 4（10%，初分篮留痕 A4 + 对照带）；\(g_2\) 6% → 4%（无同业锚，A5）；分子 FY2027 yfinance → FY2028 Zacks 4 家区间（折一年，A2）；FY2029 单家进候选带；\(V_{opt}\) 1.72 → 3.64（份数扣底牌已含 2030 收入、单位 FY2028 共识净利率 4.42%）；L/M/H 1.39 / 3.74 / 14.40 → 6.71 / 12.01 / 16.69；纠正对账门未过、用户拍板落盘（A16）；`formula_id` → `hims_fy28_consensus_gordon_b4_v3`。touched: [全文, eval]
HISTORICAL_PARTIAL_FINGERPRINT = 'e2ea10a767dc97773d793d794d8e9f6cb01760ea22d51eb4ff28de258da75b6c'

INPUTS = {
    # 流通股数（百万）; 来源：2026-06-30
    'shares': 233.3,
    # 归母权益（$M）；起点 BPS = 本项 ÷ shares（A6）; 来源：2026-06-30
    'equity': 324.1,
    # FY2026E GAAP EPS 共识均值（yfinance 11 家）；只用于 BPS 滚动（A6）; 来源：yfinance 2026-10-04
    'eps_fy26e_consensus': -0.56,
    # 2026H1 GAAP EPS 实测（Q1 −0.403 + Q2 −0.372）（A6）; 来源：10-Q 2026-06-30
    'eps_h1_26_gaap': -0.775,
    # FY2027E GAAP EPS 共识均值（yfinance 11 家）；BPS 滚动、口径对照（A2 / A6）; 来源：yfinance 2026-10-04
    'eps_fy27e_consensus': 0.42,
    # FY2028E EPS 共识低端（Zacks 4 家，近 GAAP，A2）; 来源：Nasdaq / Zacks 2026-10-04
    'eps_fy28e_low': 0.50,
    # FY2028E EPS 共识均值（Zacks 4 家，A2）; 来源：Nasdaq / Zacks 2026-10-04
    'eps_fy28e_consensus': 0.85,
    # FY2028E EPS 共识高端（Zacks 4 家，A2）; 来源：Nasdaq / Zacks 2026-10-04
    'eps_fy28e_high': 1.18,
    # FY2029E EPS（Zacks 1 家）；候选带 \(g_1\)（A8）; 来源：Nasdaq / Zacks 2026-10-04
    'eps_fy29e_single': 1.37,
    # 整公司永续折现率 = **篮 4 常规经营** 10%（A4，初分篮推翻留痕）；值 = `gordon.BASKET_R`; 来源：2026-10-04
    'r_perp': 0.10,
    # 时点对齐折现率（分子年初 2028-01-01 → 2026-06-30，`tau` 年），同 `r_perp`，不归篮; 来源：2026-10-16
    'r_disc': 0.10,
    # 时点对齐年数 = 估值基准日 2026-06-30（10-Q 账面，BPS 起点）→ 分子年初 2028-01-01（A17）; 来源：2026-06-30
    'tau': 1.5,
    # 高回报期止点 = 可见年末（分子年 FY2028）（A17）; 来源：2026-10-16
    'y1': 2028,
    # 稳态落稳年 = Y1 + 2（进入门槛：低）（A17）; 来源：2026-10-16
    'y2': 2030,
    # L / M 档稳态回报 = 兜底「轻资产组装」18%（自身无完整周期；唯一成熟同业 GoodRx 是处方比价平台、不是同一门生意，剔除 → 同业层空 → 兜底；有药品成本、自营药房与复方产能，不是「边际成本近零」；用户 2026-10-19 认可，A17）; 来源：2026-10-19
    'rs_steady': 0.18,
    # H 档（与 \(V_{opt}\) 的成功世界）稳态回报 = min(H 前瞻 60%, 30%)（「三档各取各的稳态」：拆不出周期的高成长腿，订阅品牌优势守住的世界；A17）; 来源：2026-10-19
    'rs_steady_h': 0.30,
    # 永续增速 = 美国长期名义增速，无同业锚（A5）; 来源：2026-10-04
    'g2': 0.04,
    # ROE 进公式的上限（A6）; 来源：valuation-rules
    'roe_cap': 0.60,
    # FY2027E 收入共识（$M，yfinance）；FY2028 收入的基数（A7）; 来源：yfinance 2026-10-04
    'rev_fy27e': 3997,
    # FY2027 → FY2028 收入比值（WallStreetZen 共识，绝对值单位错乱只取比值；来源偏弱，A7）; 来源：WallStreetZen 2026-10-04
    'rev_growth_28': 1.12329,
    # 公司 2030 收入目标（$M）；\(V_{opt}\) 份数（A7）; 来源：JPM 85749
    'rev_2030_target': 6500,
    # \(V_{opt}\) 兑现年 = 公司目标年（具名）；增量折回 FY2027（A7）; 来源：2026-10-04
    't_opt': 2030,
    # FY2025 实测 GAAP 净利率；只作 \(V_{opt}\) 单位交叉（A7）; 来源：yfinance FY2025
    'nm_2025_gaap': 0.0547,
    # 公司 2030 调整后 EBITDA 目标（$M）；只作 \(V_{opt}\) 单位敏感（A7）; 来源：公司 2030 目标（公开报道）
    'adj_ebitda_2030_target': 1300,
    # FY2025 调整后 EBITDA 率；与 GAAP 净利率之差用于推断（A7）; 来源：FY2025 8-K
    'adj_ebitda_margin_2025': 0.135,
    # 巴克莱 2027 调整后 EPS（单家）；候选坐标（A8）; 来源：Wisburg 92949
    'eps_adj_fy27_house': 2.48,
    # JPM 2027E 调整后 EBITDA（$M）（A9）; 来源：Wisburg 85749
    'ebitda_fy27_jpm': 414,
    # 巴克莱 2027E EBITDA（$M）= 14.5% × 其 2027 收入 3,281（A9）; 来源：Wisburg 92949
    'ebitda_fy27_barc': 476,
    # JPM 目标倍数（A9）; 来源：Wisburg 85749
    'm_ev_jpm': 22,
    # 巴克莱目标倍数（A9）; 来源：Wisburg 92949
    'm_ev_barc': 17,
    # 巴克莱 2027 EBITDA 利润率（A9）; 来源：Wisburg 92949
    'ebitda_margin_house': 0.145,
    # 净债（$M）= 债务 1,546（含可转债）− 现金 841（A10）; 来源：2026-06-30
    'net_debt': 705,
    # 杠杆门读数（调整后 EBITDA 口径；GAAP 口径 4.4 并列，A10）; 来源：FY2025
    'net_debt_ebitda': 2.2,
    # 利息 / EBIT `待补`（可转债低息；暂按 0 通过门，A10）; 来源：—
    'interest_ebit': 0.0,
    # 上一版 M（篮 7 / FY2027 分子 / \(g_2\) 6%）；对账门坐标 ①（A16）; 来源：2026-10-03 版
    'm_prev': 3.74,
    # 自身 5 年最低市净率（2022-06）；对账门坐标 ⑥（A16）; 来源：Longbridge
    'pb_min_5y': 2.52,
    # 同等盈利月份（TTM EPS 0.80，2025-08 → 10）月收盘低（2025-08）；对账门坐标 ④（A16）; 来源：Longbridge 月 K
    'close_eq_lo': 42.35,
    # 同上月收盘高（2025-09）; 来源：Longbridge 月 K
    'close_eq_hi': 56.72,
}
BASKETS = {"r_perp": 4}  # normal operating business; r_disc is disclosure only
REQUIRED = frozenset(INPUTS)

def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2; n stage-1 years at payout 1 - g1/roe.
    With rs >= roe this equals perpetual_pe / two_stage_pe.  (gordon.py helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1
INITIAL_BASKET = 7     # A4 — the overturned basket, comparison band only
P_TIERS = (0.0, 0.25, 1.0)  # A7 — table 3 only, never an input
LISTING_CCY = "USD"
RF_TOL = 1e-9




def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp, ('y1', 'y2', 't_opt'))
    if inp['y1'] < NUM_YEAR or inp['y2'] <= inp['y1']:
        raise ValueError('invalid return path years')
    r, g2, cap = inp["r_perp"], inp["g2"], inp["roe_cap"]
    baskets = BASKETS
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell")
    if "r_disc" in baskets:
        errors.append("r_disc is disclosure-only and must not carry 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if abs(inp["r_disc"] - r) > 1e-12:
        errors.append("r_disc must equal r_perp (year-drift discount at the basket r)")
    errors += check_g_cap(g2, r, "g2")
    eps28 = (inp["eps_fy28e_low"], inp["eps_fy28e_consensus"], inp["eps_fy28e_high"])
    errors += ladder("eps_fy28e", *eps28)
    if inp["net_debt_ebitda"] > 3 or inp["interest_ebit"] > 1 / 3:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition")

    shares = inp["shares"]
    bps0 = inp["equity"] / shares
    unbooked = (inp["eps_fy26e_consensus"] - inp["eps_h1_26_gaap"]) + inp["eps_fy27e_consensus"]

    # Steady return per tier (retention「三档各取各的稳态」): L / M = fallback, H (and the V_opt
    # success world, the company's 2030 target met) = min(H forward, 30%).
    tau, y1, y2, rs, rs_h = inp["tau"], int(inp["y1"]), int(inp["y2"]), inp["rs_steady"], inp["rs_steady_h"]
    if rs_h < rs:
        errors.append(f"rs_steady_h {rs_h} below the L / M steady {rs}")
    rs_t = (rs, rs, rs_h)

    def window_ps(bps: float, gg: float) -> float:
        """2026H2 + FY2027 unbooked consensus EPS x (1 - b), b = the book-roll retention g2/ROE_M (A17)."""
        return max(unbooked * (1 - gg / min(eps28[1] / bps, cap)), 0.0)

    def model(rr: float, gg: float) -> tuple[float, list[tuple[float, float, float, float]], tuple[float, float, float]]:
        """BPS at the start of FY2028 and per-tier (ROE raw, ROE, PE, anchor) at basket r = rr, g2 = gg.
        Anchor = EPS28 x PE (steady-return path) / (1+r)^tau + window / (1+r)^(tau/2)  (A17)."""
        bps = bps0
        for _ in range(50):  # retention b = g2 / ROE_M, ROE_M depends on the rolled BPS
            bps = bps0 + gg / min(eps28[1] / bps, cap) * unbooked
        win = window_ps(bps, gg) / (1 + rr) ** (tau / 2)
        rows = []
        for e, rs_x in zip(eps28, rs_t):
            roe = min(e / bps, cap)
            pe = three_segment_pe(NUM_YEAR, y1, y2, rs_x, gg, roe, rr)
            rows.append((e / bps, roe, pe, e * pe / (1 + rr) ** tau + win))
        return bps, rows, tuple(x[3] for x in rows)

    bps, rows, (L, M, H) = model(r, g2)
    floor = bps0
    if L < floor:
        errors.append(f"scenario L {L:.2f} below the BPS floor {floor:.2f} — floor rule applies, re-derive")
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)

    errors += check_branch(g2, rows[1][1], r, 0.0, "g2")
    pe_m = rows[1][2]
    win_m = window_ps(bps, g2) / (1 + r) ** (tau / 2)
    flat = tuple(e * pe_m / (1 + r) ** tau + win_m for e in eps28)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder collapsed (construction §2c)")

    # V_opt chain.
    t_opt = int(inp["t_opt"])
    if t_opt <= NUM_YEAR:
        errors.append("t_opt must lie after the numerator year (A7)")
    rev28 = inp["rev_fy27e"] * inp["rev_growth_28"]
    nm28 = eps28[1] * shares / rev28

    def v_at(nm: float, rr: float = r, gg: float = g2, t: int = t_opt) -> tuple[float, float, float]:
        base30 = rev28 * (1 + gg) ** (t - NUM_YEAR)
        k_rev = inp["rev_2030_target"] - base30
        # own ruler on the same calendar steady-return path (A17), then the same timing as the deck:
        # t_opt -> FY2027 (t - 2027 years) and the extra tau - 1 years to the 2026-06-30 book
        val = (k_rev * nm / shares * three_segment_pe(t, y1, y2, rs_h, gg, cap, rr)
               / (1 + rr) ** (t - T1_YEAR) / (1 + rr) ** (tau - 1))
        return base30, k_rev, val

    base30, k_rev, v_opt = v_at(nm28)
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    nm_infer = inp["adj_ebitda_2030_target"] / inp["rev_2030_target"] - (inp["adj_ebitda_margin_2025"] - inp["nm_2025_gaap"])
    nm29 = inp["eps_fy29e_single"] * shares / (rev28 * inp["rev_growth_28"])
    nm27 = inp["eps_fy27e_consensus"] * shares / inp["rev_fy27e"]

    # Candidate band: FY2029 single house as g1, n = 1, on M/H; L carries no transition.
    g1 = inp["eps_fy29e_single"] / eps28[1] - 1
    # same path shifted one visible year (FY2029 single house -> Y1 2029, same fall length) + same timing
    y1c, y2c = y1 + 1, y2 + 1
    cand = (L,) + tuple(
        e * three_segment_pe(NUM_YEAR, y1c, y2c, rs_x, g2, roe, r, g1=g1, n=1) / (1 + r) ** tau + win_m
        for e, (_, roe, _, _), rs_x in zip(eps28[1:], rows[1:], rs_t[1:])
    )
    if not (cand[0] < cand[1] < cand[2]):
        errors.append("candidate band needs L′ < M′ < H′")
    # Candidate coordinate: Barclays FY2027 adjusted EPS on the same ruler (FY2027 = t1, not discounted).
    pe_b = three_segment_pe(T1_YEAR, T1_YEAR, T1_YEAR + (y2 - y1), rs, g2, min(inp["eps_adj_fy27_house"] / bps0, cap), r)
    m_barc = inp["eps_adj_fy27_house"] * pe_b / (1 + r) ** (tau - 1)  # FY2027 numerator: t_n 2027-01-01, 0.5y

    # Basket-7 comparison band (initial basket, overturned; disclosure only).
    r7 = basket_r(INITIAL_BASKET)
    _, _, (L7, M7, H7) = model(r7, g2)
    v7 = v_at(nm28, rr=r7)[2]

    cross = {
        "JPM": (inp["m_ev_jpm"] * inp["ebitda_fy27_jpm"] - inp["net_debt"]) / shares,
        "Barclays": (inp["m_ev_barc"] * inp["ebitda_fy27_barc"] - inp["net_debt"]) / shares,
    }

    # Correction gate (valuation-rules「纠正对账门」): M moved > 25% → coordinates, disclosure (user ruled 2026-10-04).
    e_over_r = eps28[1] / r / (1 + r)
    coords = {
        "previous_mid": inp["m_prev"],
        "no_growth": e_over_r,
        "historical_low": inp["close_eq_lo"],
        "historical_high": inp["close_eq_hi"],
        "book_min_multiple": bps0 * inp["pb_min_5y"],
    }
    inside = any(abs(M / c - 1) <= 0.20 for c in coords.values())

    def band_at(dr: float) -> tuple[float, float, float]:
        return model(r + dr, g2)[2]

    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    result = {
        "ticker": "HIMS.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-06-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of': '2026-10-19',
        "anchors": band((L, M, H)),
        "candidate": {"label": "2029 年单家盈利预测", "anchors": band(cand)},
        "option": {"value": v_opt, "anchors": band(opt), "fractions": band(P_TIERS)},
        "cut_points": [A, B], "option_cut_points": [a2, b2],
        "bps0": bps0, "bps": bps, "rows": rows, "flat": flat,
        "floor": floor, "unbooked": unbooked, "win_m": win_m,
        "rev28": rev28, "base30": base30, "k_rev": k_rev, "nm28": nm28,
        "nm_infer": nm_infer, "nm29": nm29, "nm27": nm27, "g1": g1,
        "barclays_coordinate": m_barc, "pe_b": pe_b,
        "initial_basket": [L7, M7, H7], "initial_basket_option": v7,
        "cross": cross, "coords": coords, "inside": inside,
        "parameters": {"discount": r, "growth": g2,
                       "forward": band([row[1] for row in rows]),
                       "mature": band([min(row[1], ref) for row, ref in zip(rows, rs_t)])},
        "sensitivity": {"growth_low": model(r, g2-0.01)[2], "growth_high": model(r, g2+0.01)[2],
                        "option": [v_at(nm29)[2], v_at(nm_infer)[2], v_at(inp["nm_2025_gaap"])[2],
                                   v_at(nm27)[2], v_at(nm28, t=t_opt+1)[2]]},
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if r + dr <= g2:
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_at(dr)
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
        {'inputs': INPUTS, 'baskets': BASKETS, 'numerator_year': NUM_YEAR, 'option_reference_year': T1_YEAR,
         'option_weights': P_TIERS, 'comparison_basket': INITIAL_BASKET}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments'] = {'company': {'unit': 'USD_PER_SHARE', 'values': dict(result['anchors'])}}
    if result['option']['value'] >= 0:
        result['option']['value_unit'] = 'USD_PER_SHARE'
        result['option']['weights'] = result['option'].pop('fractions')
    else:
        result['option'] = {'status': 'unavailable', 'label': '收入目标', 'anchors': None}
        result.pop('option_cut_points', None)
        result['option_unavailable_reason'] = 'incremental_revenue_below_existing_baseline'
    parameters = result['parameters']
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['growth'])},
        'forward_return': {'unit': 'RATIO', 'values': parameters['forward']},
        'steady_return': {'unit': 'RATIO', 'values': parameters['mature']},
    }
    result['review_flags'] = ['historical_leverage_interest_and_convertible_unverified',
                              'historical_reconciliation_user_decision_2026_10_04',
                              'historical_extra_value_sensitivity_disagreement']
    return result
