#!/usr/bin/env python3
"""Ganfeng Lithium historical valuation with volume and solid-state options.

Inputs, shared axes and one-year high-price world retain 2026 research; results
are HKD/share. This draft is not a fresh forecast or publication confirmation.
"""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, g_cap, implied_g, payout, perpetual_pe, recovery_two_stage_pe
from lib.inputs import require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis', 'rf_report'),
                'axes': {'lithium': 'lithium_carbonate', 'solid': 'solid_state_battery'}}
HISTORICAL_PARTIAL_FINGERPRINT = 'ea8dd78db9fcae0f28843e6a7b4fda2a8cd2aa1aa661bb12b863704d1822aad3'

# Original Inputs values, sources, intent and as-of.
INPUTS = {
    # 总股本（百万，A+H；Longbridge 总市值与同日收盘价反推） | as-of 2026-09-11
    'shares': 2096.7,
    # 每股净资产 HKD | as-of 2026H1
    'bps': 26.67,
    # USDHKD 7.80 ÷ USDCNY 6.8645（2026H1 均汇） | as-of 2026H1
    'fx_hkd_per_cny': 1.136,
    # 轴 L（2028 过剩底） | as-of 轴 §1
    # 轴 M（2027 共识中枢；2026-10-20 由 12.5 万下调） | as-of 2026-10-20
    # 轴 H（2026 平台延续） | as-of 轴 §1
    # 标定点 0：2025H1 均价 元/吨（≈，精确值待补 SMM；A3） | as-of 2025H1
    'cal_p0': 70000,
    # 标定点 0：锂腿税前年化 亿 CNY =（0.35 − 5.88）× 2 | as-of 2025H1
    'cal_li_pretax_0': -11.06,
    # 标定点 1：2026H1 均价 元/吨（A3） | as-of 2026H1
    'cal_p1': 163000,
    # 标定点 1：锂腿税前年化 亿 CNY =（58.17 + 4.63）× 2 | as-of 2026H1
    'cal_li_pretax_1': 125.60,
    # 2026E 锂盐销量 万吨 LCE（大华继显 = 东吴，两家共识；两点线的量结构所在年 = 底牌，A11） | as-of 2026-05-03
    'vol_2026e': 23,
    # 2027E 锂盐销量 万吨 LCE（大华继显，**单家**；**只进候选带**，A11） | as-of 2026-01-26
    'vol_2027e': 27,
    # 今日锂盐名牌产能 万吨/年（≈30，Cauchari 4 万按 100%；2026H1 中报，属性 B）；V_opt 量增份数的分母（A12） | as-of 2026H1
    'cap_now': 30,
    # 公司具名目标：2030 年或之前形成不低于 60 万吨锂产品设计产能（2025 年报）；V_opt 量增份数 =（60 − 30）÷ 30 = 1 份 2026 结构（A12） | as-of FY2025
    'cap_2030': 60,
    # 分子年 = 2026 量结构（候选带 2027 量折 1 年回到此年）；V_opt 折现终点（A12） | as-of 2026-10-03
    't_num': 2026,
    # 固态兑现年 = 对齐年份（本票最远共识年 2027）+ 2，**无时点锚·拍值**（A9） | as-of 2026-10-03
    # 量增兑现年 = 公司 60 万吨设计产能目标年（A12） | as-of FY2025
    't_opt_vol': 2030,
    # **期权·未投资本（固态，A9）**：重庆赣锋锂电科技「年产 20GWh 新型锂电池研发及生产基地项目」（2022-08 立项的固态电池基地）预算 96.00 亿 × (1 − 工程累计投入占预算 12.50%) = 84.00 亿 CNY（100%）；2026 中报在建工程附注「重要在建工程项目本期变动情况」 | as-of 2026-06-30
    # 本票对赣锋锂电持股 64.52%（赣锋锂电 20 亿增资完成公告，2026-06-29） | as-of 2026-06-29
    'ss_eq': 0.6452,
    # **期权·份数（固态，A9）**：重庆基地具名产能 20 GWh/年（「年产 20GWh 新型锂电池研发及生产基地项目」，2022-08 立项、公司定位固态电池基地；2026-08-05 互动问答：前期规划阶段）；H 档满产量 | as-of 2026-08-05
    'ss_cap_gwh': 20,
    # 重庆基地投资预算 亿 CNY（100%；2026 中报在建工程附注）= 固态项目 ROE 的分母（经营资本） | as-of 2026-06-30
    'ss_budget': 96.00,
    # 固态稳态单价 元/Wh（`_AXIS.solid-state-battery`；东吴证券 天华新能深度 2026-09-24 表 12 全固态路径远端 2035E） | as-of 2026-09-24
    # 全固态单价 2029E 元/Wh（`_AXIS.solid-state-battery`，同上；兑现年单价，敏感性） | as-of 2026-09-24
    # 全固态单价 2030E 元/Wh（`_AXIS.solid-state-battery`，同上；敏感性） | as-of 2026-09-24
    # 固态满产营业利润率弱者读数（`_AXIS.solid-state-battery`：国轩高科 2022–25 实测均值，相邻液态电芯层）；只作 L / M 读数 | as-of 2026-10-05
    # 强者读数（`_AXIS.solid-state-battery`：宁德时代 2022–25 实测营业利润率均值，相邻液态电芯层） | as-of 2026-10-05
    # H 新进入者折扣（`_AXIS.solid-state-battery`；良率 / 认证未完成、规模小；拍值）→ H 利润率 11.13% | as-of 2026-10-05
    # 固态腿 g2 来源（`_AXIS.solid-state-battery`：电池制造横截面在 r 13% 下反解，宁德时代单样本） | as-of 2026-09-30
    # 固态腿稳态回报 = 按序取：自身无历史 → 电芯成熟同业三星 SDI 6.9%（`_AXIS.solid-state-battery` `ss_return_peer_ssb`）< r → 取本票 r 13%；兑现起新投资即按此（A16；用户 2026-10-19 认可） | as-of 2026-10-19
    # 固态腿 g2 = `g2_ssb_src` 截到 G_cap 6%；只在项目 ROE > r 时起作用（同 `r_perp`，不归篮） | as-of 2026-10-05
    # **期权·未投资本（量增，A12）**：PPGS 一期 = 「PPG 采矿项目」预算 80.47 亿 × (1 − 工程累计投入占预算 18.13%) = 65.88 亿 CNY（100%；2026 中报在建工程附注；预算 ≈ LAR / 赣锋 2025-11-10 范围研究 Stage 1 US$1,124M） | as-of 2026-06-30
    'ppg_k': 65.88,
    # 整合后本票持 PPGS 67%（临2025-133；中报「整合后将持有」） | as-of 2025-11-11
    'ppg_eq': 0.67,
    # Cauchari 二期 4.5 万吨 LCE 的 RIGI 获批投资额 US$ 百万（阿根廷经济部第 825/2026 号决议，2026-06-04；主管部门对外口径 1,241）；已投按 0（二期在工程设计阶段，LAR 2026Q2 MD&A） | as-of 2026-06-04
    'cau_k_usd': 1166.68,
    # 本票持 Minera Exar 46.67%（2026 中报） | as-of 2026H1
    'cau_eq': 0.4667,
    # USDCNY（2026H1 均汇，与 `fx_hkd_per_cny` 同源） | as-of 2026H1
    'fx_cny_per_usd': 6.8645,
    # PPGS 一期 5 万吨 LCE/年（三期共 15 万；临2025-133） | as-of 2025-11-11
    'cap_ppg1': 5,
    # Cauchari 二期 4.5 万吨 LCE/年（2026 中报） | as-of 2026H1
    'cap_cau2': 4.5,
    # 30 万吨增量里未具名的 20.5 万吨（30 − 5 − 4.5）的单吨资本 亿 CNY/万吨 = 本票丰城「年产 5 万吨锂电新能源材料项目」投资上限 20 亿 ÷ 5 万吨 LCE（临2022-048，2022-05-26；矿石提锂、含营运资金）；**推断** | as-of 2022-05-26
    'conv_k_per_wt': 4.0,
    # **敏感性**：PPGS 二、三期 = 全项目 US$3,301M − 一期 1,124M（LAR / 赣锋范围研究，100%）；不进主值 | as-of 2025-11-10
    'ppg23_k_usd': 2177,
    # 候选带 2027 量与 V_opt 量增的折现率 = 锂腿篮子 r（与 `r_perp` 同值，A14）；δ = 1.13⁻¹ | as-of 2026-09-20
    # 候选带时点对齐 τ（年）：估值基准日 2026-06-30 → 2027E 量的分子年初 2027-01-01，取代原「折 1 年」；窗口利润折 τ/2（A11 / A16）。V_opt 的折现按兑现年 − `t_num`，不用本行 | as-of 2026-10-16
    'n_disc': 0.5,
    # FY2026E EPS HKD（yfinance 3 家均值）；候选带窗口可分配利润的分子（A16） | as-of 2026-10-15
    'eps26e_hkd': 3.46,
    # 2026H1 已入账 EPS HKD（中报）；候选带窗口 = `eps26e_hkd` − 本项（A16） | as-of 2026-06-30
    'eps_h1_hkd': 2.32,
    # 电池腿板块业绩年化 亿 CNY = 3.97 × 2；当期量，不折现 | as-of 2026H1
    'batt_pretax': 7.94,
    # 净财务费用年化 亿 CNY =（6.42 − 1.68）× 2 | as-of 2026H1
    'net_finance': 9.48,
    # 所得税 / 税前 | as-of 2026H1
    'tax_rate': 0.2854,
    # 少数股东损益 / 净利润 | as-of 2026H1
    'nci_share': 0.0394,
    # 永续贴现率 = **篮 6 周期商品 / 小盘 13%**（锂价函数，两腿同篮，无备选篮；A14；真源 `eval/lib/gordon.py BASKET_R`）；零增长 → PE 1/r = 7.69× | as-of 2026-09-20
    'r_perp': 0.13,
    # 永续增速三档 flat；来源 = **§13 商品腿 tier 默认**——锂长期实际价格漂移 ≤ −3%/yr → g2 = 0，不取负（同业反解 2.35% 不采用，只作对照，A7）；cap = min(6%, r − 4%) = 6% | as-of 2026-09-20
    'g2': 0.0,
    # 锂轴「永续 g2（2026-09-14）」行（上限截断值，tier 3）；**引用、被 tier 0 取代**（A7）；eval 校验与轴行逐字相等 | as-of 2026-09-14
    # 自身 5 年 TTM PE 实测低点（2023-09，剔亏损期）；LB valuation history；**护栏**，不入公式（A7） | as-of 2026-09-01
    'pe_own_min': 3.57,
    # 自身 5 年 TTM PE 实测高点（2026-04，盈利谷底）；**护栏**（A7） | as-of 2026-09-01
    'pe_own_max': 81.97,
    # 资产地板倍数 = 2025-04-08 低点实测 PB（A8）；**只作披露行**（`floor` vs L），不进 L | as-of 2026-09-20
    'pb_floor': 0.70,
}

# Historical rationale and financial evidence; comments are not extra inputs.
# - **属性 A — 转化商杠杆**：2025H1（锂价 ~7 万）锂盐板块业绩 0.35 亿、锂矿 −5.88 亿；2026H1（16.3 万）分别 58.2 / 4.63 亿。同一家公司一年内从亏到 125 亿年化，弹性 ~14.7 亿/万元——比天齐（26% 穿透泰利森）陡得多，\(H/M\) 因此是锂票里最宽的。
# - **属性 B — 自供比例未披露，半年量也未披露**：中报只给产能（锂盐名牌 ≈ 30 万吨/年，Cauchari 4 万按 100%）与矿端产量（Goulamina H1 精矿 23.4 万吨、Cauchari H1 碳酸锂 1.9 万吨），不给锂盐销量与自供比例；年报才给全年销量（2025 **18.48 万吨 LCE**）。故锂腿**不自建量 × 价差**，用自身两期实测两点标定（A2e-2c「自身已实现极值」）。两点之间混着 2025→26 的量增与 2026H1 涨价滞后红利，M 档偏乐观。锂盐名牌 30 万吨**不作**量锚——边际吨靠外购矿，两点线的混合边际乘上去会高估；2027 量走卖方销量比、只进候选带（A11）。
# - **属性 C — 电池腿薄利、统一倍数**：储能放量但板块业绩率 4.9%；与锂腿同一 Gordon 倍数（同篮、同 g2、同档 ROE），不单给成长倍数，也不单独归篮（占税前 10%，A14）。
# - **属性 D — 固态电池：没有卖方的量，按同业尺轴把具名产能换算成收入（valuation-rules「未建模期权」2026-10-05：未投产业务不得记 0 或快照）**：里程碑 = 400Wh/kg 循环 1,100 次工程验证、500Wh/kg 10Ah 小批量、无人机 / 机器人小批量供货；公司从未披露固态出货量、收入或单价，**没有任何卖方给本票固态的量或利润率**（2026-10-05 查：大华继显、东吴、摩根大通等只给整个电池板块）。具名的量 = 重庆赣锋锂电科技「年产 20GWh 新型锂电池研发及生产基地」（2022-08 立项、定位固态电池基地；2026-08-05 互动问答：前期规划阶段，无分期与投产日）；2022 年「三大基地 66 GWh 含固态 12 GWh」是旧规划，不再用。单价与利润率取 `_AXIS.solid-state-battery`（本票参照挂载）：同业唯一的卖方单价路径是东吴证券 2026-09-24 全固态 5 / 3 / 1.8 / 1.5 / 0.8 元/Wh（2027–30、2035E），估值取远端 **0.8 元/Wh 作稳态单价**（兑现年单价是逐年下滑的首发溢价，资本化成永续会把溢价读成永久）；利润率同业无卖方预测、无可用实测（清陶固液混合在爬坡亏损期），退到相邻业务液态电芯：H = 宁德时代 2022–25 实测营业利润率均值 14.13% − 新进入者折扣 3pp（良率 / 认证未完成、规模小，拍值）= **11.13%**。**H 档**：20 GWh × 0.8 = 160 亿元收入 × 11.13% = 17.8 亿税前 × (1 − 28.5%) = 12.7 亿；项目 ROE = 12.7 ÷ 预算 96 亿 = 13.3%，略高于 r 13%；新投资稳态回报取本票 r 13%（2026-10-19 按序取：电芯成熟同业三星 SDI 6.9% < r，`_AXIS.solid-state-battery`；原「叙事换代 13.3% 不回落」撤）→ Gordon 倍数 = \(1/r\) **7.69×**；× 本票持股 64.52% → 0.445 HKD/股 × 7.69 在 2029 估值（对齐年份 2027 + 2，**无时点锚·拍值**），÷ 1.13³ = **2.37**；扣本票应担未投资本（预算 96.00 亿 × (1 − 12.50%) = 84.00 亿 × 64.52% = 54.20 亿，2027–2029 均摊折回）**2.31** → **净 +0.06 HKD/股**。**L / M 不另造量、记 0**（无卖方的量；valuation-rules「未建模期权」分档 2026-10-05：本票没有任何卖方的量 → 只进 H，\(p_L = p_M = 0\)）；同一满产量在轴 M 利润率 6.43%（弱者国轩 1.73% 与 H 的中点）下净值 **−0.94**、在 L 利润率下 **−1.94**——只作读数：中低利润率世界里这座基地在 13% 尺下毁值，盈亏平衡利润率 **10.9%**。**正负**：规则原文是「兑现后价值 − 尚未投入的资本」，未设 0 下限，负值照记（本次 H 为正，问题未触发）。敏感性：按兑现年单价 2029E 1.8 元/Wh → 3.02、2030E 1.5 → 2.14；不打新进入者折扣 → 0.70；g2 取 0 → 0.06。升级门槛：任一卖方给出本票固态出货 / 收入（含单家）→ 进 L / M 档的量；公司披露重庆基地分期与投产日 → 兑现年改投产日；同业出现固态单价或利润率的卖方预测 → 替换轴的取法。证伪：2027 年报前重庆基地仍无开工 / 投资进度，或公司撤回该项目 → \(p^{ss}\) 置 0
# - **属性 E — NCI 结构与天齐相反**：H1 少数股东损益仅 3.9%，Mt Marion / Cauchari 走权益法进板块业绩，没有 26% 穿透那一刀；桥简单，弹性全在锂腿本身。
# - **属性 F — 底牌停在 2026 量结构，2027 量增是候选带，2028 之后的是期权**：底牌锂腿 = 两点线自带的 2026H1 结构（2026E 23 万吨为大华 + 东吴两家共识、与之一致），不缩放、不折现——按 valuation-rules 增长表达顺序，2027E 27 万吨只有大华一家（单家）→ **候选带**（同公式 × 27/23 × δ，A11），覆盖邦巴利 2027 投产爬坡、Goulamina/Cauchari 一期满产、Mariana 放量；Mt Marion 2028 升级至 60 万吨 SC6、Goulamina 二期（可研完成、未定期）、Cauchari 二期 4.5 万（RIGI、未定期）都是 2030 年 60 万吨设计产能目标的组成部分，**不进底牌也不进候选带，按属性 G 以该目标落 \(V_{opt}\)**。与共识的剩余偏离：共识 Q1'27E 年化 4.48 HKD vs 本框架 M EPS 2.26（−50%），来自轴 M 12.0 万 < 卖方 2027 价（大华 20 万）与 2027 量不在底牌。
# - **属性 G — 底牌之外的量增是期权，不是 `stretched` 解释**：具名的量有四个——Mt Marion 升级至 60 万吨 SC6（2028 前完成，50%）、Goulamina 二期（可研完成、未定期，65%）、Cauchari 二期 4.5 万 LCE（入选 RIGI、未定期，46.67%），以及把它们收在一起的公司目标「2030 年或之前形成不低于 60 万吨锂产品设计产能」（2025 年报）。公司不给分项目投产时间、产量与成本，**算不出分子**；按 valuation-rules「未建模期权」（2026-10-03：份数只来自本票具名的量、单位经济取本票该腿、借量不借价、按兑现年估值折回），份数取**公司 2030 目标超出今日名牌的部分**：(60 − 30) ÷ 30 = **1.0 份 2026 结构**（名牌对名牌换算，等于按今日利用率 23 ÷ 30 把增量名牌换成销量 23 万吨；共识已含部分 = 底牌的 2026E 23 万吨，大华单家的 2027E 27 万吨只在候选带、不扣）；单位经济 = 本票锂腿两点线在**轴 M 价**的税前 62.4 亿（轴 M 12.0 万；混合边际含外购矿，偏保守）；按本票的尺在 2030 估值（g=0 → 兑现后倍数 1/r = 7.69×），按篮子 r 折回 2026 分子年（÷ 1.13⁴ = 0.613）→ 10.95 HKD/股；**扣本票应担未投资本**（2026-10-04 规则）163.52 亿 CNY = PPGS 一期 44.14 + Cauchari 二期 37.38 + 其余 20.5 万吨转化产能 82.00（按本票丰城项目单吨资本推断），2027–2030 均摊折回（平均 0.744）→ 6.59 → **净 4.36 HKD/股**，模糊落在按档 \(p_k\)（A9 / A12）。旧口径「k=1 × 自身已实现的 2024→2025 一步 +42.5%」按「已实测轨迹」取单位，2026-10-03 规则改为具名的量后撤销。价钉轴 M（中枢）而非各档价，档间差异只走 \(p_k\)。升级门槛：公司给出分项目投产时间与产量，或 ≥2 家卖方给出 2028E 销量 → 做成 `vol_2028e` 进腿、从 \(V_{opt}\) 移出相应份数；证伪：2027 年报前无一个二期开工，或公司下修 / 撤回 60 万吨目标 → 份数按新目标重算或 \(p\) 置 0。
# | A1 | 锂价真源 `_AXIS.lithium-carbonate`（10.3/12.0/15 万；M 2026-10-20 由 12.5 万下调） | `active` | 轴 §1 | `li2co3_*` |
# | A2 | 锂腿税前对锂价为线性，两点 = 自身 2025H1 / 2026H1 实测（板块业绩：锂盐 + 锂矿，JV 已含） | `weakened` | 中期业绩公告分部表（2026H1 与 2025H1 对照）。**2026Q3 削弱（2026-10-20）**：三季度单季税前 15.45 亿（三季报，前三季度 − 中报），两点线在当季锂价约 14.0–14.5 万（SMM 9 月均价 13.8 万、8 月约 14.9 万由 Mysteel 9 月环比反推、7 月无均价，**估算**）下预测 22.6–24.4 亿 → 实测只有 **63–68%**；倒推锂腿年化税前约 64 亿（**推断**：季报不分部，电池腿按 H1 年化、净财务费用按 Q3 实际）。方向与属性 B 所警告的一致——H1 是涨价期滞后红利，Q3 是跌价期外购高价矿入成本的反向滞后，单点都不是稳态。用前三季度累计点（均价约 15.5–15.7 万 / 锂腿年化约 105 亿，斜率 13.4–13.6）+ 前三季度税率 29.0% / NCI 8.9% / 净财务费用 9.8 亿重标定，在锂轴 12.0 万下 L/M/H = **8.40 / 14.52 / 15.76**（Q3 价取 14.5 万；取 14.0 万为 8.63 / 14.87 / 16.14；只换标定点、桥不换为 9.01 / 15.51 / 16.82）。**纠正对账门未过**（M 变动 −26%）：上一版 M 19.52；股息尺（FY2025 派息率约 20%）≈ 3.3；同等盈利月份（TTM EPS 在 2.12 HKD ±12%，LB 月度 PE × 收盘反推，仅 4 个月 < 6）2023-12 收 20.9（PB 1.03）、2026-07 40.9、2021-07 / 11 更高；同业同尺同日 `待补`；资产口径 BPS 26.07 × 实测 PB 谷底 0.70 = 18.25——14.52 落在全部坐标之外 > 20%（最近的资产口径 −20.4%，对应 PB 0.56，本票从未印过）。**2026-10-20 用户裁定**：主锚点只随锂轴同步，三季报重标定不进主锚点、只作敏感性行；FY2026 年报给出 H2 分部后正式重标定，并单独讨论「盈利尺低于资产地板」的尺问题（A8） | `cal_*` |
# | A3 | 标定价：2025H1 电池级碳酸锂均价 ≈ **7.0 万**（区间 6.0–7.7 万中值；精确均价 `待补` SMM）；2026H1 ≈ **16.3 万**（与 `9696.HK` A2 同源） | `active` | 中报价格叙述 | `cal_p0` / `cal_p1` |
# | A4 | 电池腿 = 板块业绩年化 7.94 亿，三档同值 | `active` | 分部表。2026Q3 季报不分部、无法核对（公司称锂电池销量增加），年报再核 | `batt_pretax` |
# | A5 | 净财务费用 9.48 亿/年（融资成本 6.42 − 利息收入 1.68，×2），三档同值 | `active` | 分部表对账。2026Q3 单季净利息约 2.61 亿（前三季度利息费用 9.83 − 利息收入 2.48 − H1 4.74），年化约 10.4 亿、前三季度年化 9.8 亿——略高，影响 < 0.1 HKD/股，暂不改 | `net_finance` |
# | A6 | 税率 28.5%（17.70/62.02）、NCI 3.9%（1.75/44.32），三档冻结 | `weakened` | 损益表。**2026Q3 削弱（2026-10-20）**：三季度单季税率 30.9%、少数股东分走 **29.3%**（3.12 / 10.68 亿），前三季度合计 29.0% / 8.9%。推测（`待核`，年报分部）：锂价下行时全资的锂盐利润缩得最多，少数股东所在的电池子公司（赣锋锂电外部股东约 35%）与矿山子公司占比上升——NCI 随锂价反向变动，冻结在 H1 的 3.9% 对 L / M 档偏低。只换前三季度桥：M 17.42 → 约 16.3（锂轴 12.0 万下）；随三季报重标定一并处理（A2），本次不改 | `tax_rate` / `nci_share` |
# | A7 | **倍数由 Gordon 生成：g2 = 0 三档 flat，来源 = §13 商品腿 tier 默认；r = 篮 6 13%（A14）；ROE 按档 = EPS_HKD ÷ BPS = 5.0% / 8.5% / 14.6% → 三档皆 1/r = 7.69×；锂腿与电池腿同倍数** | `active` | **g2 来源（§13 商品腿规则）**：锂 = 通胀 + 长期实际价格漂移（≤ −3%/yr）→ tier 默认 **0**，不取负；量增（26E→28E CAGR 22%）走候选带 / \(V_{opt}\)，不进 g。锂生产商同业横截面反解（SQM 1.05 / PLS 6.77 / IGO 3.64 / 中矿 −2.69 → 中位 2.35%，与 `ALB.US` A7 同源）**不采用**：商品腿不走同业反解——周期端点反解是循环、且该簇是在 10% 尺下反解的，换 r 不重解就是半把尺；只作对照坐标（敏感性行）。锂轴「永续 g2（2026-09-14）」行 6%（tier 3 截断）以 `axis_g2_li` 逐字引用并校验，**被 tier 0 取代**——6% 在 L 档 ROE 5% 下派息为负、不可用。cap = min(6%, 13% − 4%) = 6%。**域判定（§4）**：ROE 三档 5.0% / 8.5% / 14.6% vs r 13%——L、M 档峰形区（−8pp / −4.5pp）：g>0 压倍数、g=0 是峰值 = 1/r；H 档病态区（+1.6pp）；三档皆 7.69×，档差只来自锂轴价（裁决顺序 ⑤）。**A2d 六维**（2026-09-14）：① **研报共识**：JPM TP 70、大华 TP 90（2027 均价 20 万）、街上最低 TP 31.5（19 家）；yfinance 09-14 前瞻 EPS 4.00 HKD；卖方分腿倍数 **待补**。② **EPS**：M 档 EPS 2.26 HKD（锂轴 M 12.0 万，2026-10-20）vs 共识 Q1'27E 年化 4.48（−50%，差在轴 M 价 < 卖方 20 万 + 2027 量不在底牌）；2026E 销量 23 万吨两家共识 = 底牌结构；2027E 单家 → 候选带、无 g1。③ **ROE**：锂簇前瞻 ROE 15–31%——本票 L 档远低于 r（转化商谷底）。④ **PEG**：不适用。⑤ **交叉约束（护栏）**：5 年 TTM PE 实测带 [3.57, 81.97]（LB 2026-09-01，剔亏损期，中位 10.91）——7.69× 在带内；带边反解在 M 档为不良条件，只报不作锚。⑥ **档位可比性**：L/M 0.59 / H/M 1.72 全在分子，见 Outputs。**g2 ±1pp**：峰形区里 L/M 随 g **反向**（+1pp → 8.90 / 16.64 / 18.09；−1pp → 9.53 / 16.17 / 17.62；H 按路过） | `r_perp` / `g2` / `axis_g2_li` / `pe_own_min/max` |
# | A8 | **PB 0.70 × BPS 地板 = 18.67，只作披露行，不进 L**（2025-04-08 低点 16.98 对应当时 PB ≈ 0.7 = 本票实测过的 PB 谷底；A2e-1「已实测过的坏」，不再在实测之下另打折）。地板是不随 r 变的资产数，塞进随 r 缩的盈利尺会在峰形区把 L 推到 M 之上（锂轴 M 下调到 12.0 万后地板 18.67 > M 17.42，落 `optimistic` 档 [18.14, 18.87]，只比 H 低 0.20）；§13 峰形区地板条款下 L 取情景值 10.27，地板落在 [L, H] 内的哪一档由 Outputs 披露。情景/M = 0.59 ≥ 0.3，盈利尺未失效。**开放问题（2026-10-20）**：2026Q3 BPS 降到约 26.07 HKD（汇兑折算 −14 亿）→ 地板 18.25；若按三季报重标定（A2），H 15.76 会整段低于地板——盈利尺在 13% / g = 0 / 中枢 ROE < r 的读法下系统性低于本票实测过的 PB 谷底，地板是否托底、主尺是否该换，待 FY2026 年报重标定时单独讨论 | `active` | K 线 + 2025H1 BPS；2026Q3 归母权益 481.2 亿 | `pb_floor`；`floor` 披露行；表2 `neutral` 行读资产口径坐标 |
# | A9 | \(V_{opt}\) 两项（valuation-rules「未建模期权」，2026-10-03；2026-10-04 起扣未投资本；2026-10-05 起未投产业务走同业尺轴）：**固态**（属性 D，尺在 `_AXIS.solid-state-battery`）= 重庆 20 GWh 基地满产 × 稳态单价 0.8 元/Wh（东吴 2026-09-24 全固态路径远端，卖方层）× H 利润率 11.13%（相邻液态电芯层：宁德 2022–25 实测 14.13% − 新进入者折扣 3pp 拍值），项目 ROE 13.3%（÷ 预算 96 亿），新投资稳态回报取本票 r 13%（A16 ④）→ Gordon \(1/r\) 7.69×，× 64.52%，2029 兑现（对齐年份 + 2，无时点锚·拍值）折回 → 毛值 **2.37**，扣本票应担未投资本（84.00 亿 × 64.52% = 54.20 亿，2027–2029 均摊折回 → 2.31；出处：2026 中报在建工程附注、赣锋锂电增资公告 2026-06-29）→ **+0.06**。**分档**：本票无卖方的固态量（2026-10-05 查无）→ 按分档规则只进 H，\(p^{ss}\) = 0 / 0 / 1.0（L / M 不另造量；同一满产量在轴 M 利润率 6.43% 下净值 −0.94，M 记 0 不偏高）。**正负**：规则原文 \(V_{opt}\) = 兑现后价值 − 未投资本、不设 0 下限 → 负值照记（本次为正，未触发）。**偏差方向**：稳态单价 0.8 而非兑现年 1.8（2029E）→ 偏低（按 1.8 为 3.02）；利润率借液态相邻层、不给固态首发溢价 → 偏低；均摊假设（2022 立项至今只投 12.5%、仍在前期规划）→ 若投入后移则扣得偏多、兑现年 2029 偏早则毛值偏高，两者部分抵消；**量增** = 公司 2030 年 60 万吨设计产能目标超出今日名牌的 1 份 2026 结构、2030 兑现折回（毛值 10.95，轴 M 12.0 万），扣本票应担未投资本 6.59（A12）→ **4.36**，\(p^{vol}\) = 0 / 0.25 / 1.0——**分档核对**：锂腿有卖方对本票的远期量（2026E 23 万吨两家、2027E 27 万吨大华单家），不属「无卖方的量」，保留 L / M（规则「公司目标高出卖方高路径的部分只进 H」对本项的逐档拆分 `待核`）；\(p_L\)=0 是轴 L 世界的定义（增量项目推迟）；\(p_M\)=0.25 **无概率锚·拍值**（分项目投产日未披露；旧锚「东吴 2028E/2027E +12.5% ÷ 一步 42.5%」随份数改为 2030 目标而失效）；\(p_H\)=1.0 为 7d 默认（2030 目标按时满额兑现） | `active` | 属性 D / 属性 G；2025 年报 60 万吨目标；`_AXIS.solid-state-battery`（东吴证券 天华新能深度 2026-09-24 表 12；Longbridge 宁德 / 国轩年报利润表）；2026 中报在建工程附注（重庆 20GWh 预算 / 进度）；互动问答 2026-08-05（前期规划阶段）；赣锋锂电增资公告 2026-06-29（64.52%） | `ss_*` / `ssb_*` / `g2_ssb*`；表3 |
# | A10 | 两点线的量结构 = 2026H1 = 底牌；2027E 量增走候选带（A11）；2028 之后的量增（Mt Marion 60 万吨升级、Goulamina 二期、Cauchari 二期，统一以 2030 年 60 万吨设计产能目标计）不进底牌也不进候选带，按属性 G 落 \(V_{opt}\) | `active` | 中报项目进展；2025 年报「2030 年或之前形成不低于 60 万吨设计产能」 | 表3 |
# | A11 | **候选带升级门槛（A2e-7h）**：`候选带（2027E 量·大华单家）` = 同公式只把锂腿量系数 1.0 换成 `vol_2027e/vol_2026e` = 27/23 × δ=(1.13)^{-0.5}（轴为 2027–28 价格 deck，量推到 2027，按时点对齐从 2027-01-01 折回 2026-06-30 共 τ = 0.5 年、折现率 = 篮子 r，与 `9696.HK` 同构），再加 2026H2 窗口可分配利润 1.11（A16）；H′ 同底牌按路过；g2 / r / 桥不变，L′ 同为情景值。**判为增长型**（construction §7h，2026-10-08 定）：大华的 27 万吨是卖方对公司全年出货的普通年度预测，不由产能折算、不是公司目标也不是乐观情景 → 按增长换算成 27/23 的量系数，三档共用（价格档不同、量的增长相同；H′ = 轴上沿 15 万价 × 27 万吨，量本身有来源，不超出大华）。**升级条件**：第二家卖方给出 2027E 锂盐销量（≥ 25 万吨量级）→ 框架纠正：候选带升级为底牌并删除该行与 `vol_2027e`；**证伪**：卖方 2027E 下修至 ≤ 2026E → 删候选带。底牌为何停在 2026 结构：2026E 23 万吨为大华（2026-01-26）+ 东吴（2026-05-03「出货量有望达到 23 万吨，同比 +24%」）两家共识、基数 2025 实际 18.48 万吻合、与两点线的 2026H1 结构一致；**2027E 27 万吨仅大华一家**（东吴给 2027 自有权益资源 15–16 万作方向印证），按 valuation-rules 增长表达顺序（单家年份 → 候选带）不进底牌 | `weakened` | 同左。**2026-10 削弱**：唯一来源大华继显把评级降为持有、目标价 75 → 28 港元、下调平均售价假设，FY2026 盈利预测下调 22% 至 72.14 亿（富途转述，2026-10 中旬）；2027E 销量是否下调**未知**（`待核`）。窗口利润的分子 `eps26e_hkd` 3.46 对应四季度需赚约 14 亿，与 2026Q3 归母 7.55 亿、10 月现货约 10–11 万不符，待共识更新（按四季度 3–8 亿估，窗口约 0.55–0.82） | Outputs 候选带一行：12.49 / 20.38 / 21.99 |
# | A12 | **量增期权的值**（2026-10-03 按「份数只来自本票具名的量」重算）：份数 = (`cap_2030` − `cap_now`) ÷ `cap_now` = (60 − 30) ÷ 30 = **1.0 份 2026 结构**（公司 2030 年设计产能目标，2025 年报；今日名牌 ≈30 万吨，属性 B；名牌对名牌换算即按今日利用率把增量名牌换成销量，不按 60 − 23 直接相减——那会把名牌与销量混用）；单位经济 = 两点线在**轴 M 价**的锂腿税前（62.4 亿，轴 M 12.0 万；本票锂腿）；税/NCI/股本/汇率与底牌同；倍数 = 本票兑现后 Gordon（g=0 → 1/r 7.69×，**不借同业倍数**）；兑现年 `t_opt_vol` = 2030（公司目标年），按篮子 r 折回分子年 `t_num` 2026（÷ 1.13⁴）→ 毛值 10.95 HKD/股，扣未投资本后 **4.36**（见本行后段）。价不随档变（\(V_{opt}\) 须是单一数，7d），档间差异只走 \(p^{vol}_k\)；轴 L/H 价下同一份数值（扣资本后）−0.02 / 12.10，作敏感性。不按今日利用率换算（60 − 23 = 37 万吨 ≈ 1.6 份）作上沿敏感性，不进表3。**扣未投资本（valuation-rules「未建模期权」2026-10-04：规划产能型期权 = 兑现后价值 − 尚未投入的资本）**：公司不给 30 万吨增量的分项目构成；电话会（投资者关系活动记录表 2026-001，2026-03-31）点名未来资本开支重点 = Goulamina 二期、Cauchari 二期、PPGS。按「产出锂产品设计产能」的项目取数（与名牌口径一致——Cauchari / Mariana 按 100% 进名牌表）：① **PPGS 一期 5 万吨 LCE**：「PPG 采矿项目」预算 80.47 亿、累计投入 18.13%（2026 中报在建工程附注；≈ 范围研究 Stage 1 US$1,124M，LAR / 赣锋 2025-11-10）→ 未投 65.88 亿 × 67%（临2025-133 整合后权益）= **44.14 亿**；② **Cauchari 二期 4.5 万吨**：RIGI 获批投资额 US$1,166.7M（阿根廷经济部第 825/2026 号决议，2026-06-04；投资完成期限 2030-07-01）、已投按 0（二期在工程设计阶段，LAR 2026Q2 MD&A）× 6.8645 × 46.67% = **37.38 亿**；③ **其余 20.5 万吨未具名**：按本票自己的转化项目单吨资本——丰城「年产 5 万吨锂电新能源材料项目」投资上限 20 亿 ÷ 5 万吨 = 4.0 亿/万吨（临2022-048，2022-05-26；矿石提锂、含营运资金），× 100% = **82.00 亿**（**推断**：用外购矿的转化厂补满增量，与单位经济「两点线混合边际含外购矿」同口径）。合计 **163.52 亿 CNY**，投入分年未知 → 按工期 2027–2030 均摊，各年按篮子 r 折回 2026（平均 0.744）→ **6.59 HKD/股**；量增净值 10.95 − 6.59 = **4.36**。**不扣的项与理由**：Mt Marion 浮选 / 地下升级（50%）、Goulamina 二期（65%）、邦巴利（73%）产的是精矿、不是锂产品设计产能，它们压低的原料成本不在单位经济里，资本也不扣（投资额未披露，`待补`；若计入则份值与资本同时上调）；Mariana 一期（预算 80 亿、累计 81.04%，未投 15.2 亿）已在今日名牌 2 万吨氯化锂里，属底牌不属期权。**偏差方向**：① PPGS 二、三期（10 万吨，US$2,177M）若在 2030 前建成并替代 10 万吨转化产能 → 净值 **1.94**（`ppg23_k_usd` 敏感行）；② 只扣具名两项、不扣其余 → 7.67（偏高）；③ 兑现年一次扣（样板口径）→ 5.52；④ 价值侧按集团口径（NCI 3.9%）计满 30 万吨，而 PPGS 33% / Cauchari 53.33% 不归本票，约 7.35 万吨（≈ 1/4 份）的价值被多计 → 净值偏高，`待改`（升级门槛：公司给出增量分项目构成 → 份数按权益重算）；⑤ Cauchari 二期按 RIGI 决议额而非主管部门对外口径 1,241 → 扣得略少。升级门槛：公司或合作方披露增量各项目的预算与进度 → 逐项替换推断项 | `active` | 属性 G；valuation-rules「未建模期权」（2026-10-03 / 2026-10-04）；construction §7c-1；2026 中报在建工程附注；临2025-133；临2022-048；阿根廷经济部第 825/2026 号决议；LAR 2026Q2 MD&A；投资者关系活动记录表 2026-001 | `ppg_k` / `ppg_eq` / `cau_k_usd` / `cau_eq` / `fx_cny_per_usd` / `cap_ppg1` / `cap_cau2` / `conv_k_per_wt` / `ppg23_k_usd`；表3；**MUST NOT** 进 Inputs（\(p\) 类字段）|
# | A13 | **谷底档规则对本票的结果：L 世界是低位 regime，不走回归段**（valuation-rules「谷底档」）。本票自己走过的谷底→回归：Longbridge 年报归母（HKD）FY2024 **−22.45 亿**（2024–25 锂崩盘年，亏损）→ FY2025 **17.63 亿** → 2026H1 42.6 亿 CNY × 2 ≈ 97 亿 HKD（2026-09-14 拉取；中报）。两种用法都不能作 L：(i) 亏损谷底 CAGR 无定义；从 FY2025 起算 n = 1、+449% 套在 L 分子 1.34 上 → 荒谬地越过 M（51.1）；(ii) 只取实测年数 n = 1、幅度取 L→M（g1 69.6%，锂轴 M 12.0 万）→ 12.43× → **16.59 ≈ M（L/M 0.953，塌陷）**。裁决 ⑤→②：轴 L 10.3 万是 2028 底（BMI 11.3 / 高盛 8.5 万两源之间，轴「换算口径」2026-10-12）、高于 p90 成本 6.5 万，轴 §1 明示 2024–25 崩盘区（本票 2025H1 在那里亏损）不进 L——L 是可持续 regime 而非「跌下去必弹回」的一年，故 L 情景配稳态 g2（同 M）→ 7.69× → 10.27。谷底 × 1/r = EPS_L ÷ 13% = **10.27**，在 g=0 下与 L 恒等，`deep_discount` 压力坐标即 L 本身 | `active` | 年报序列如左；eval 打印两个坐标与 谷底 × 1/r | L 档情景倍数 = `perpetual_pe(g2, ROE_L)`；`deep_discount` 行 |
# | A14 | **归篮：锂腿 → 篮 6 周期商品 / 小盘 r = 13%（盈利是锂价函数，与 `ALB.US` ES 腿 / `000792.SZ` 锂腿同源）；电池腿（板块业绩 7.9 亿，占税前 10%）随锂腿同篮不拆；无备选篮；CAPM 粗筛不适用（β 0.79 系 H 股流动性折价，与锂价函数的盈利波动不匹配，以街 r 校验）**。候选带 / 量增期权折现 `r_disc` 同用篮子 r（候选带 δ = 1.13^−0.5，时点对齐）。街 r 样本：UOB 大华继显 10y DCF WACC **12%**、g 4%（2026-09-01，TP 75）——唯一贴 13% 的 A/H 锂样本，支持篮 6。共识 EPS 2026E 3.37 / 2027E 4.36 HKD 高于 M 档 2.26——卖方与本框架的分歧在锂轴档位（现货平台 16 万一线 ≈ H 档 EPS 3.90）与 2027 量增（候选带 / 表3），26E→28E CAGR 22% 是量增、不进 g；不在归篮 | `active` | ticker-decisions 专属节（13% 下 L 折现问题，议「point 口径 L 折现修正」统一处理）与 ③ 出带调研表 1772 行；`gordon.BASKET_R`；`eval/1772.HK.py` `check_r(r, 腿, 篮)` | `r_perp` / `r_disc`；三档倍数 |
# | A15 | **杠杆门触发**（`valuation-rules.md`「杠杆门」，2026-09-21）：净债 / EBITDA **6.8**、利息 / EBIT **124%**（FY2025，报表营业利润口径，CNY 合并报表）。`cyclical`：门按**中枢年 EBIT** 判，中枢读数 `待补`（M 档税前 ≈ 68 亿 CNY 暗示中枢读数可能落回阈值之下，`待核`，不作结论）；FY2025 为锂价谷底后的实测年读数并列 | `active` | 净债务 **253 亿 CNY** = 短期借款 91.9 + 一年内到期非流动负债 73.2 + 长期借款 161.4 + 应付债券 11.5 + 租赁负债 0.5 − 货币资金 84.2 − 交易性金融资产 1.4（合并资产负债表 2025-12-31，A/H 同一套报表；无永续债 / 优先股；长期应付款 30.0 亿未计）；EBIT = 报表**营业利润 11.9 亿**（含投资收益 18.1 / 公允价值变动 1.1 / 其他收益 3.6 亿；Longbridge 标准化营业利润 8.3 亿 HKD 剔除这些项 → 193%，**不用**）；EBITDA = 11.9 + 折旧摊销 25.3 亿 = 37.2 亿；利息 = 财务费用中的利息支出 **14.7 亿**（A5 的净财务费用 9.48 亿是 2026H1 年化、净额口径，两者不同年不同口径）；权益乘数 = 总资产 1,133 / 归母权益 451 = **2.5** | 三条待补：① ROE 拆解（ROE / 权益乘数 / ROIC 并列，ROIC 侧判域）② A 桶去杠杆分子（若成立）+ 利率 +100bp 敏感行（触发即必做）③ §5b 换尺判定与 EV 口径交叉。既有覆盖：② 部分——A5 已把净财务费用 9.48 亿作闭合项从三档分子扣除（利息进分子、不进 g），但未判 A 桶（还债路径）成立与否、无 +100bp 敏感行；① 部分——A7 已按档报 ROE 对 r 的域判定，未拆权益乘数、未算 ROIC 侧；③ 无。中枢 EBIT 与其余 `待补`，下一事件增量落 |
# | A16 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」）与 H 档路过**：① **超额现金未触发单列**：2025 年末净债务 253 亿 CNY（A15），利润、回报、历史反解全部用合并口径；NCI 3.9% 已在桥里扣，归母份额不另调。② **增长期资金缺口 = 0**：底牌是 2026 当期结构，分子年已开始，没有窗口；新建产能（PPGS、Cauchari 二期、重庆固态基地）投产在分子年之后，按「只计产出落在分子年之内的扩产」不从主锚点扣，已在 \(V_{opt}\) 里按「价值 − 未投资本」扣（A9 / A12）。③ **时点对齐**：底牌分子 = 两点线自带的 2026 结构，分子年 2026 已开始（τ < 0 取 0），不折、无窗口；**候选带**的 2027E 量按 τ = 0.5 年（2026-06-30 → 2027-01-01）折回、取代原「折 1 年」，再加**窗口可分配利润** = 2026H2 尚未入账的共识（FY2026E 3.46 − H1 已入账 2.32 = 1.14 HKD/股）× (1 − b)，b = g2 ÷ RONIC = 0，按 τ/2 折 → +1.11；两项期权按兑现年折回分子年 2026、τ = 0，不动。④ **稳态回报三段**：锂腿分子由 `_AXIS.lithium-carbonate` 桥出，属商品腿豁免；电池腿与锂腿共用 1/r（g2 = 0，回报不进倍数），不受影响。**固态电池期权：不是叙事换代，按序取 + 三档各取各的稳态**（2026-10-19 改，用户认可；取代 2026-10-16「叙事换代」）：判据 ① 自身周期不可用——固态业务未投产，没有本票自身历史，成立；② 「没有 ≥ 5 年读数的同一门生意成熟同业」**不成立**——三星 SDI 按 5 个年度区间 FY2020 → 25 收入 +3.3%/年，属成熟（旧判「负增长」是只取 4 个区间的误判），有 FY2021–25 五年读数（均值 6.9%）；欣旺达、鹏辉补齐 10 年年报后 FY2020 → 25 收入 +16.3% / +26.8%，不成熟（不是「只有 3 年读数」）→ 电芯成熟同业层 = 三星 SDI 6.9% < r → **稳态 = 本票 r 13%**（`_AXIS.solid-state-battery` 稳态行「取各票 r」，`rs_ssb`）；兑现起新投资即按 13%（项目前瞻 13.3% 与 r 只差 0.3pp，不另设高回报期）→ 倍数 \(1/r\) 7.69×、毛值 2.37、净值 **+0.06**（只进表3；原叙事换代读法 7.82× / 2.41 / +0.10 撤）。三档：本期权只进 H；三档各取各的稳态下高档可读高档前瞻 13.3%（≤ 30%），与 13% 差 < 2pp，按噪声取按序值。⑤ **H 档路过（2026-10-16 裁定，锂价轴 H 档「2026 平台延续到 2027」按路过）**：H 价只维持一年，之后回到 M 档世界；g2 = 0、锂腿与电池腿同用 r 13% → **H = (0.13 × 30.03 + 17.42) ÷ 1.13 = 18.87**（锂轴 M 12.0 万，2026-10-20；12.5 万时为 20.73；原 30.03 = 长期化读数）；候选带同样处理 → H′ 21.99（长期化 34.31）。两项期权的倍数在 g2 = 0 下与档位无关，不变。⑥ 无打折 k | `active` | 2026H1 中报；yfinance FY2026E 共识（3 家，2026-10-15）；`_AXIS.solid-state-battery`；2026-10-16 用户裁定（锂价轴 H 档路过、叙事换代的腿） | `n_disc` / `eps26e_hkd` / `eps_h1_hkd`；H 30.03 → 20.73、B 24.77 → 20.12；候选带 10.68 / 20.29 / 31.21 → 12.49 / 22.71 / 24.04；M 不变；锂轴 M 12.0 万（2026-10-20）后 M 19.52 → 17.42、H → 18.87、B → 18.14、候选带 → 12.49 / 20.38 / 21.99 |

TOL = 0.05
MIN_R_MINUS_G = 0.02
# The single perpetual r leg (both business legs share the basket, A14); r_disc
# is the same number by construction but is a discount input, not a leg.
LEG_R = ("r_perp",)
# Peer-ruler axis for the solid-state leg: shared rows must match it verbatim.
SSB_SHARED = ("ssb_px_ss", "ssb_px_2029", "ssb_px_2030", "ssb_opm_weak", "ssb_opm_strong",
              "ssb_entrant_disc", "g2_ssb_src")
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"

# Per-tier option credits (A9).  valuation-rules「未建模期权」分档 (2026-10-05):
# an item with no sell-side quantity for this ticker enters H only, p_L = p_M = 0.
# Solid-state has none (no house sizes Ganfeng's solid-state) -> 0 / 0 / 1.
# Volume keeps its L/M: the lithium leg does carry sell-side volume (大华 2027E,
# single house); its p_M 0.25 is a judgement call (no probability anchor).
P_SS = {"l": 0.0, "m": 0.0, "h": 1.0}
P_VOL = {"l": 0.0, "m": 0.25, "h": 1.0}
# Chongqing project, 2026 interim construction note: 12.5% spent.
SOLID_SPENT_FRACTION = .125
OPTIONAL_INPUTS = frozenset({'vol_2026e','vol_2027e','cap_now','cap_2030','t_opt_vol','ss_eq',
    'ss_cap_gwh','ss_budget','ppg_k','ppg_eq','cau_k_usd','cau_eq','fx_cny_per_usd',
    'cap_ppg1','cap_cau2','conv_k_per_wt','ppg23_k_usd','n_disc','eps26e_hkd','eps_h1_hkd'})
# A13: the company's own realised trough→recovery path (Longbridge annual parent NI,
# HKD: FY2024 −22.45 亿 loss trough; FY2025 17.63 亿 → 2026H1 42.6 亿 CNY × 2 × fx).
RECOVERY_MEASURED = {"FY2025→2026H1×2": (17.63, 42.6 * 2 * 1.136, 1)}

REQUIRED = [
    "shares", "bps", "fx_hkd_per_cny",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "cal_p0", "cal_li_pretax_0", "cal_p1", "cal_li_pretax_1",
    "vol_2026e", "vol_2027e", "cap_now", "cap_2030", "r_disc", "n_disc", "eps26e_hkd", "eps_h1_hkd",
    "t_num", "t_opt_ss", "t_opt_vol",
    "ss_k", "ss_eq", "ss_cap_gwh", "ss_budget", "g2_ssb", "rs_ssb", *SSB_SHARED, "ppg_k", "ppg_eq", "cau_k_usd", "cau_eq", "fx_cny_per_usd",
    "cap_ppg1", "cap_cau2", "conv_k_per_wt", "ppg23_k_usd",
    "batt_pretax", "net_finance",
    "tax_rate", "nci_share",
    "r_perp", "g2", "axis_g2_li",
    "pe_own_min", "pe_own_max", "pb_floor",
]


def parent_from_pretax(pretax: float, inp: dict[str, float]) -> float:
    return pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])


def per_share_hkd(parent_yi: float, inp: dict[str, float]) -> float:
    """亿 CNY → HKD per share (shares in millions)."""
    return parent_yi * 100.0 / inp["shares"] * inp["fx_hkd_per_cny"]


def vol_scale(inp: dict[str, float]) -> float:
    """Candidate band only: 2027E/2026E sales ratio (single house), discounted τ = n_disc (A11 / A16)."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    return inp["vol_2027e"] / inp["vol_2026e"] * disc


def window(inp: dict[str, float], roe: float) -> float:
    """Candidate band only (A16): 2026H2 unbooked consensus EPS × (1 − b), b = g2/ROE, discounted τ/2."""
    b = max(inp["g2"], 0.0) / roe
    return (inp["eps26e_hkd"] - inp["eps_h1_hkd"]) * (1.0 - b) / (1.0 + inp["r_disc"]) ** (inp["n_disc"] / 2)


def passby(S: dict[str, dict[str, float]], inp: dict[str, float]) -> float:
    """A16: lithium axis H passes by — one H year, then the M world, at the basket r."""
    g2 = inp["g2"]
    return (S["h"]["eps"] * payout(g2, S["h"]["roe"]) + S["m"]["px"] * (1.0 + g2)) / (1.0 + inp["r_perp"])


def band(S: dict[str, dict[str, float]], inp: dict[str, float], win: bool = False) -> tuple[float, float, float]:
    """L / M / H with the H pass-by; the candidate band adds the window profit per tier."""
    w = {t: window(inp, S[t]["roe"]) if win else 0.0 for t in ("l", "m", "h")}
    return S["l"]["px"] + w["l"], S["m"]["px"] + w["m"], passby(S, inp) + w["h"]


def li_2026(inp: dict[str, float], li2co3: float) -> float:
    """Lithium-leg pre-tax at 2026H1 volume structure, 亿 CNY (the raw two-point line)."""
    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (
        inp["cal_p1"] - inp["cal_p0"]
    )
    return inp["cal_li_pretax_0"] + (li2co3 - inp["cal_p0"]) * slope


def option_share(inp: dict[str, float]) -> float:
    """Shares of the 2026 structure in the named 2030 design-capacity target (A12, 7c-1)."""
    return (inp["cap_2030"] - inp["cap_now"]) / inp["cap_now"]


def disc_to_num(inp: dict[str, float], t_opt: float) -> float:
    """Realisation year -> numerator year (2026 structure) at the basket r (7c-1 时点)."""
    return (1.0 + inp["r_disc"]) ** (-(t_opt - inp["t_num"]))


def post_pe(inp: dict[str, float], eps_h: float, d_eps: float) -> float:
    """This ticker's own ruler after realisation: Gordon at the H-tier ROE plus the increment."""
    return perpetual_pe(inp["g2"], (eps_h + d_eps) / inp["bps"], inp["r_perp"])


def disc_spread(inp: dict[str, float], t_opt: float) -> float:
    """Unspent capital spread evenly over t_num+1 .. t_opt, each tranche discounted to t_num (A9 / A12)."""
    years = range(int(inp["t_num"]) + 1, int(t_opt) + 1)
    return sum((1.0 + inp["r_disc"]) ** (-(t - inp["t_num"])) for t in years) / len(years)


def ss_tier(inp: dict[str, float], opm: float, px: float | None = None, g2: float | None = None) -> dict[str, float]:
    """Solid-state option at full capacity (A9): 20 GWh x price x margin, project ROE on the budget,
    valued in t_opt_ss on this ticker's r (ROE <= r -> 1/r; else Gordon at the axis g2),
    discounted to t_num, less the equity share of unspent capital spread 2027..t_opt_ss."""
    px = inp["ssb_px_ss"] if px is None else px
    g = inp["g2_ssb"] if g2 is None else g2
    rev = inp["ss_cap_gwh"] * px * 10.0  # GWh x 元/Wh -> 亿 CNY
    pretax = rev * opm
    ni = pretax * (1.0 - inp["tax_rate"])
    roe = ni / inp["ss_budget"]
    # Steady return (2026-10-19 ordered pick, _AXIS.solid-state-battery): own cycle none -> mature
    # cell peer Samsung SDI 6.9% < r -> this ticker's r; new investment earns it from realisation.
    rs = max(min(roe, inp["rs_ssb"]), inp["r_perp"])
    pe = perpetual_pe(g, rs, inp["r_perp"]) if roe > inp["r_perp"] else 1.0 / inp["r_perp"]
    eps = per_share_hkd(ni * inp["ss_eq"], inp)
    gross = eps * pe * disc_to_num(inp, inp["t_opt_ss"])
    net = gross - k_ps(inp, inp["ss_k"] * inp["ss_eq"], inp["t_opt_ss"])
    return {"rev": rev, "pretax": pretax, "roe": roe, "pe": pe, "eps": eps, "gross": gross, "net": net}


def k_vol_parts(inp: dict[str, float]) -> dict[str, float]:
    """Equity share of unspent capital behind the 30 万吨 increment, 亿 CNY (A12)."""
    rest = inp["cap_2030"] - inp["cap_now"] - inp["cap_ppg1"] - inp["cap_cau2"]
    return {
        "ppg1": inp["ppg_k"] * inp["ppg_eq"],
        "cau2": inp["cau_k_usd"] / 100.0 * inp["fx_cny_per_usd"] * inp["cau_eq"],
        "rest": rest * inp["conv_k_per_wt"],
    }


def k_ps(inp: dict[str, float], k_yi: float, t_opt: float, spread: bool = True) -> float:
    """Unspent capital 亿 CNY -> HKD/share at the numerator year."""
    d = disc_spread(inp, t_opt) if spread else disc_to_num(inp, t_opt)
    return per_share_hkd(k_yi * d, inp)


def v_opt_vol_gross(inp: dict[str, float], li2co3: float, eps_h: float) -> float:
    """Named 2030 capacity target beyond today's nameplate, read at the given rung, discounted (A12)."""
    d_eps = per_share_hkd(parent_from_pretax(li_2026(inp, li2co3) * option_share(inp), inp), inp)
    return d_eps * post_pe(inp, eps_h, d_eps) * disc_to_num(inp, inp["t_opt_vol"])


def v_opt_vol(inp: dict[str, float], li2co3: float, eps_h: float) -> float:
    """Gross volume option less the equity share of unspent capital (2026-10-04 rule)."""
    return v_opt_vol_gross(inp, li2co3, eps_h) - k_ps(inp, sum(k_vol_parts(inp).values()), inp["t_opt_vol"])


def scenario(inp: dict[str, float], tag: str, scale: float = 1.0, g2: float | None = None) -> dict[str, float]:
    """Base deck: scale = 1.0 (the line's own 2026 volume structure).  Candidate: vol_scale."""
    g = inp["g2"] if g2 is None else g2
    li = li_2026(inp, inp[f"li2co3_{tag}"]) * scale
    pretax = li + inp["batt_pretax"] - inp["net_finance"]
    parent = parent_from_pretax(pretax, inp)
    eps = per_share_hkd(parent, inp)
    roe = eps / inp["bps"]
    pe = perpetual_pe(g, roe, inp["r_perp"])
    return {"li": li, "pretax": pretax, "parent": parent, "eps": eps, "roe": roe, "pe": pe, "px": eps * pe}


def candidate_result(inp):
    unavailable = {'status':'unavailable','label':'大华2027年销量','anchors':None}
    try:
        if inp['vol_2026e'] <= 0 or inp['vol_2027e'] <= inp['vol_2026e']:
            return unavailable, {}
        cases = {t:scenario(inp, t, vol_scale(inp)) for t in 'lmh'}
        values = band(cases, inp, win=True)
        if not all(math.isfinite(v) for v in values) or not 0 <= values[0] < values[1] < values[2]:
            return unavailable, {}
        return {'label':'大华2027年销量','anchors':dict(zip('LMH',values))}, {
            'C':cases,'Lc':values[0],'Mc':values[1],'Hc':values[2],'win_c':window(inp,cases['m']['roe'])}
    except (ValueError, ZeroDivisionError, OverflowError):
        return unavailable, {}


def option_result(inp, S, base):
    unavailable = {'status':'unavailable','label':'固态及产能扩张','anchors':None}
    try:
        require_whole_years(inp, ('t_opt_ss','t_opt_vol'))
        if (inp['ss_budget'] <= 0 or inp['cap_now'] <= 0 or inp['cap_2030'] <= inp['cap_now']
                or inp['cap_2030'] - inp['cap_now'] < inp['cap_ppg1'] + inp['cap_cau2']
                or not all(0 < inp[k] <= 1 for k in ('ss_eq','ppg_eq','cau_eq'))
                or not (inp['t_opt_ss'] > inp['t_num'] and inp['t_opt_vol'] > inp['t_num'])):
            return unavailable, {}
        opm_h = inp['ssb_opm_strong'] - inp['ssb_entrant_disc']
        opm_m = (inp['ssb_opm_weak'] + opm_h) / 2
        SS = {'h':ss_tier(inp,opm_h), 'm':ss_tier(inp,opm_m), 'l':ss_tier(inp,inp['ssb_opm_weak'])}
        v_ss_gross, v_ss = SS['h']['gross'], SS['h']['net']
        k_ss_ps = k_ps(inp, inp['ss_k'] * inp['ss_eq'], inp['t_opt_ss'])
        v_vol_gross = v_opt_vol_gross(inp, inp['li2co3_m'], S['h']['eps'])
        kv = k_vol_parts(inp)
        k_vol_ps = k_ps(inp, sum(kv.values()), inp['t_opt_vol'])
        v_vol, v_opt = v_vol_gross - k_vol_ps, v_ss + v_vol_gross - k_vol_ps
        adj = {k:base[k] + P_SS[t] * v_ss + P_VOL[t] * v_vol for k,t in zip('LMH','lmh')}
        if not all(math.isfinite(v) for v in (*adj.values(),v_ss,v_vol,v_opt)):
            return unavailable, {}
        named_only = v_vol_gross - k_ps(inp,kv['ppg1'] + kv['cau2'],inp['t_opt_vol'])
        ppg23 = inp['ppg23_k_usd'] / 100 * inp['fx_cny_per_usd'] * inp['ppg_eq']
        rest_less = kv['rest'] - 10 * inp['conv_k_per_wt']
        ppgs_full = v_vol_gross - k_ps(inp,kv['ppg1'] + kv['cau2'] + ppg23 + rest_less,inp['t_opt_vol'])
        oneshot_vol = v_vol_gross - k_ps(inp,sum(kv.values()),inp['t_opt_vol'],spread=False)
        oneshot_ss = v_ss_gross - k_ps(inp,inp['ss_k'] * inp['ss_eq'],inp['t_opt_ss'],spread=False)
        r10 = dict(inp,r_disc=.10)
        v10 = (v_opt_vol(r10,inp['li2co3_m'],S['h']['eps']),ss_tier(r10,opm_h)['net'])
        option_sensitivity = {
            'volume_low_price':v_opt_vol(inp,inp['li2co3_l'],S['h']['eps']),
            'volume_high_price':v_opt_vol(inp,inp['li2co3_h'],S['h']['eps']),
            'solid_price_2029':ss_tier(inp,opm_h,inp['ssb_px_2029'])['net'],
            'solid_price_2030':ss_tier(inp,opm_h,inp['ssb_px_2030'])['net'],
            'solid_no_entrant_discount':ss_tier(inp,inp['ssb_opm_strong'])['net'],
            'solid_zero_growth':ss_tier(inp,opm_h,g2=0.)['net'],
            'solid_break_even_margin':next((o/1000 for o in range(1,400) if ss_tier(inp,o/1000)['net'] >= 0),None)}
        option = {'value':v_opt,'components':{'solid_state':v_ss,'volume':v_vol},
                  'solid_state_weights':{t.upper():P_SS[t] for t in 'lmh'},
                  'volume_weights':{t.upper():P_VOL[t] for t in 'lmh'},'anchors':adj}
        details = {'opm_h':opm_h,'opm_m':opm_m,'SS':SS,'v_ss_gross':v_ss_gross,'k_ss_ps':k_ss_ps,
                   'v_ss':v_ss,'v_vol_gross':v_vol_gross,'kv':kv,'k_vol_ps':k_vol_ps,'v_vol':v_vol,
                   'v_opt':v_opt,'adj':adj,'named_only':named_only,'ppg23':ppg23,'rest_less':rest_less,
                   'ppgs_full':ppgs_full,'oneshot_vol':oneshot_vol,'oneshot_ss':oneshot_ss,'v10':v10,
                   'option_sensitivity':option_sensitivity,'p_ss':P_SS,'p_vol':P_VOL}
        def finite(value):
            if value is None or isinstance(value, str):
                return True
            if isinstance(value, dict):
                return all(finite(v) for v in value.values())
            if isinstance(value, (tuple, list)):
                return all(finite(v) for v in value)
            return isinstance(value, (int, float)) and math.isfinite(value)
        if not finite(details):
            return unavailable, {}
        return (option if 0 <= adj['L'] < adj['M'] < adj['H'] else unavailable), details
    except (ValueError,ZeroDivisionError,OverflowError):
        return unavailable, {}


def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        raise ValueError(f'missing inputs {missing}')
    require_whole_years(inp, ('t_num',))

    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    # valuation-rules「§r 篮子」/「永续增长口径」: r is the named basket's value, one
    # flat g2 ≤ cap(r); the axis row is referenced verbatim and superseded.
    baskets = {"r_perp": 6}
    for field in LEG_R:
        if field not in baskets:
            errors.append(f"{field}: no 篮 N in Inputs source cell (A14)")
        errors += check_r(inp[field], field, baskets.get(field))
        errors += check_g_cap(inp["g2"], inp[field], f"g2@{field}")
        errors += check_g_cap(inp["axis_g2_li"], inp[field], f"axis_g2_li@{field}")
        if inp[field] - inp["g2"] < MIN_R_MINUS_G:
            errors.append(f"{field} − g2 = {inp[field] - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    # The candidate band / volume option discount at the same basket r as the leg (A14).
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal the leg's basket r r_perp={inp['r_perp']} (A14)")
    want_axis = inp['axis_g2_li']
    if not (inp["cal_p0"] < inp["cal_p1"] and inp["cal_li_pretax_0"] < inp["cal_li_pretax_1"]):
        errors.append("calibration points must be ordered (trough below platform)")
    peer = {key: inp[key] for key in SSB_SHARED}
    if errors:
        raise ValueError('; '.join(errors))

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): a tier outside the own band is BLOCKED, never fixed by twisting g or r.
    outside_history = any(not inp['pe_own_min'] <= pe <= inp['pe_own_max'] for pe in (pe_l, pe_m, pe_h))
    # A8: the floor is disclosed only; L is the scenario value.
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["px"]
    L, M, H = band(S, inp)
    H_persist = S["h"]["px"]
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        raise ValueError(f'L<M<H violated: {L}, {M}, {H}')
    flat = (S['l']['eps'] * pe_m, S['m']['eps'] * pe_m, S['h']['eps'] * pe_m)
    if not flat[0] < flat[1] < flat[2]:
        raise ValueError('flat-multiple base ladder is invalid')
    base = dict(zip('LMH', (L, M, H)))
    # Candidate and projects are optional computations: a failure here must
    # not suppress the already-calculated base or the other optional result.
    candidate, candidate_details = candidate_result(inp)
    option, option_details = option_result(inp, S, base)
    slope = (inp['cal_li_pretax_1'] - inp['cal_li_pretax_0']) / (inp['cal_p1'] - inp['cal_p0'])
    g_lo, ok_lo = implied_g(inp['pe_own_min'], S['m']['roe'], inp['r_perp'])
    g_hi, ok_hi = implied_g(inp['pe_own_max'], S['m']['roe'], inp['r_perp'])
    sensitivity = {}
    for dg in (-.01, .01):
        alt = dict(inp, g2=inp['g2'] + dg)
        sensitivity[str(dg)] = band({t: scenario(alt, t) for t in 'lmh'}, alt)
    # One measured trough-to-recovery period, as in the original disclosure.
    np0, np1, n = next(iter(RECOVERY_MEASURED.values()))
    g1_meas = (np1 / np0) ** (1 / n) - 1
    pe_i = recovery_two_stage_pe(g1_meas, n, inp['g2'], S['m']['roe'], inp['r_perp'])
    g1_lm = (S['m']['eps'] / S['l']['eps']) ** (1 / n) - 1
    pe_ii = recovery_two_stage_pe(g1_lm, n, inp['g2'], S['m']['roe'], inp['r_perp'])
    eps3 = tuple(S[t]['eps'] for t in 'lmh')
    blended = tuple(v / e for v, e in zip((L, M, H), eps3))
    def band_rf(dr):
        shifted = dict(inp, r_perp=inp['r_perp'] + dr)
        return band({t: scenario(shifted, t) for t in 'lmh'}, shifted)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0), (L, M, H))):
        raise ValueError('rate sensitivity base differs from anchors')
    result = {'ticker': '1772.HK', 'currency': 'HKD',
            'valuation_as_of': None, 'framework_as_of': None, 'historical_research_as_of': '2026-10-20',
            'historical_framework_as_of': '2026-10-20',
            'anchors':base, 'candidate':candidate, 'option':option,
            'review_flags':['historical_half_year_price_profit_bridge_unverified',
                            'historical_solid_capacity_and_volume_funding_unverified',
                            'historical_single_house_sales_forecast'],
            'peer':peer, 'want_axis':want_axis, 'S':S, 'floor':floor, 'scenario_L':scenario_L,
            'L':L, 'M':M, 'H':H, 'H_persist':H_persist, 'A':A, 'B':B, 'flat':flat, 'base':base,
            'slope':slope, 'g_lo':g_lo, 'ok_lo':ok_lo, 'g_hi':g_hi, 'ok_hi':ok_hi,
            'g1_meas':g1_meas, 'pe_i':pe_i, 'g1_lm':g1_lm, 'pe_ii':pe_ii,
            'eps3':eps3, 'blended':blended, 'sensitivity':sensitivity}
    result.update(candidate_details)
    result.update(option_details)
    if outside_history:
        result['review_flags'].append('historical_multiple_outside_band')
    if rate_inputs is not None:
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp':inp['r_perp']}, band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs, base_anchors=(L,M,H)))
    return result


def calculate(context):
    lithium = context['axes']['lithium']
    solid = context['axes']['solid']
    shared = {key:lithium[key] for key in ('li2co3_l','li2co3_m','li2co3_h','axis_g2_li')}
    shared.update({key:solid[key] for key in SSB_SHARED})
    # Company-specific rate and optional project's original one-period +2
    # convention are derived from the shared references, not copied values.
    shared['rs_ssb'] = max(solid['ss_return_peer_ssb'], INPUTS['r_perp'])
    shared['g2_ssb'] = min(solid['g2_ssb_src'], g_cap(INPUTS['r_perp']))
    shared['t_opt_ss'] = solid['t_align'] + 2
    shared['ss_k'] = INPUTS['ss_budget'] * (1 - SOLID_SPENT_FRACTION)
    shared['r_disc'] = INPUTS['r_perp']
    result = evaluate({**INPUTS, **shared}, context.get('rate_inputs'))
    result['basis_changed'] = None
    if any(not math.isfinite(INPUTS[key]) for key in OPTIONAL_INPUTS if key in INPUTS):
        result['partial_basis_changed'] = True
    else:
        result['partial_basis_changed'] = local_basis_changed(
            {'inputs':INPUTS, 'shared':shared, 'solid_spent_fraction':SOLID_SPENT_FRACTION,
             'p_solid':P_SS, 'p_volume':P_VOL, 'recovery':RECOVERY_MEASURED}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price':'HKD_PER_SHARE'}
    result['option']['value_unit'] = 'HKD_PER_SHARE'
    result['segments'] = {'company': {'unit':'HKD_PER_SHARE','values':dict(result['anchors'])}}
    result['key_parameters'] = {
        'discount_rate': {'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_perp'])},
        'growth_rate': {'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g2'])},
        'forward_return': {'unit':'RATIO','values':{t.upper():result['S'][t]['roe'] for t in 'lmh'}},
        'solid_steady_reference':solid['ss_return_peer_ssb'],
        'solid_steady_used':shared['rs_ssb'],
    }
    return result
