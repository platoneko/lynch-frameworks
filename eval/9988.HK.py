#!/usr/bin/env python3
"""Alibaba historical FY2028 valuation; draft research output, not publication.

Original 2026 inputs and calculations are retained. Amounts and currencies are
named in each input; result values are HKD/share. No new forecast is implied.
"""
from __future__ import annotations

import math
from lib.gordon import check_g_cap, check_r, payout
from lib.inputs import check_missing
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis'), 'axes': {}}
OPTION_WEIGHTS = {'L': 0., 'M': .25, 'H': 1.}

HISTORICAL_PARTIAL_FINGERPRINT = 'c3d6df1f342d76cba1baeb12e3ea470e746a18525fd245d6f6be035c16f7cc9f'

# Original Inputs table: value, original meaning/source and as-of retained.
INPUTS = {
    # 摊薄股本 = 6 月季摊薄加权 19,324mn + 配售新股 710mn（A11） | as-of 2026-08-26
    'shares': 2.0034e10,
    # CNY→HKD **市场交叉汇率** = USDHKD 7.8400 ÷ USDCNY 6.7190（yfinance `HKD=X` / `CNY=X` 2026-09-04 收盘；`CNYHKD=X` 同日 1.1668）。**MUST NOT 用 Longbridge `exchange-rate`**：其同一响应给出 HKD/USD 7.0001（在联系汇率 7.75–7.85 之外），旧值 1.1465 实为 2026-04/05 的水平、系统性低 1.8% | as-of 2026-09-04
    'fx_cny_hkd': 1.1668,
    # FY2028E（2028-03 止）非 GAAP EPS 共识**下沿** CNY/股（yfinance 9988.HK `+1y`，17 家，A1） | as-of 2026-09-14
    'eps28_l_cny': 6.35,
    # FY2028E 非 GAAP EPS 共识**均值** CNY/股（17 家） | as-of 2026-09-14
    'eps28_m_cny': 8.02364,
    # FY2028E 非 GAAP EPS 共识**上沿** CNY/股（17 家） | as-of 2026-09-14
    'eps28_h_cny': 11.67947,
    # 非 GAAP 净利里保留的非经营项税前，6 月季（利息及投资收益非 GAAP 部分 4,301 − 利息支出 2,352 + 其他收益 495 + 权益法 934，A9b） | as-of 2026-06-30
    'nonop_pretax_q_cny': 3.378e9,
    # 其中权益法收益（投资方已税后，不再计税），6 月季 | as-of 2026-06-30
    'eq_method_q_cny': 9.34e8,
    # 非经营应税部分的正常化税率（A9b）；6 月季 GAAP 实际税率因不可抵扣项远高于此，不采 | as-of 2026-06-30
    'tax_rate': 0.20,
    # 阿里巴巴电商集团 6 月季经调整 EBITA（收入 205,862，利润率 19.3%，YoY −1%）；**只作两腿权重**（A1b） | as-of 2026-06-30
    'ebita_aeg_q_cny': 3.9749e10,
    # AI 云与算力服务 6 月季经调整 EBITA（收入 48,437，利润率 11.6%）；**只作两腿权重** | as-of 2026-06-30
    'ebita_cloud_q_cny': 5.628e9,
    # AI Labs 6 月季收入 33.38 亿；\(V_{opt}\) 份数 = 1 份自身年化收入（快照·下限，A19） | as-of 2026-06-30
    'rev_ala_q_cny': 3.338e9,
    # 阿里巴巴电商集团 6 月季收入 2,058.62 亿；与 `ebita_aeg_q_cny` 合成 ALA 期权的单位经济（本票电商 EBITA 率 19.3%，共享规则·拍值，A19） | as-of 2026-06-30
    'rev_aeg_q_cny': 2.05862e11,
    # 篮 4 常规经营 10%：ALA to-C 腿（千问 App / 夸克；付款方为分散个人与广告主、未命中篮 7 对手方 / 国别判据；初分篮 7「当期大亏、变现未证」2026-10-03 推翻，A20）；只进 \(V_{opt}\)（A19） | as-of 2026-10-03
    'r_ala': 0.10,
    # ALA 兑现年 = 对齐年份 FY2028 + 2，**无时点锚·拍值**（公司无具名目标年）；A19 | as-of 2026-10-03
    't_opt': 2030,
    # 分子年（FY2028E）；期权折现起点 | as-of 2026-09-14
    't_num': 2028,
    # **云腿留存回报率 = 卖方腿级新投资本边际 ROIC**（A14）：摩通 ~20% 与摩根士丹利自建 IaaS 13.2% 的中点，三档共用；13.2% / 20% 两端作敏感行。替代旧口径「整公司 ROE」（腿级卖方数优先于「各腿经济性相同」规则，valuation-rules「数据优先级与同业同尺」） | as-of 2026-10-03
    'roic_cloud': 0.166,
    # 篮 4 龙头制造 10%：电商 / 云两腿同一 Gordon（平台龙头，常规经营现金流；无备选篮，A20）；`check_r` | as-of 2026-09-20
    'r_perp': 0.10,
    # 每股净资产 HKD（Longbridge `valuation` PB 基准，2026-06-30，配售前）；三档 ROE 的**起点**——按增长所需留存 \(b_1=g/ROE\) 滚过未入账的 2Q–4Q FY27 到 FY2028 年初再作分母（A21），不直接作分母 | as-of 2026-06-30
    'bps_hkd': 60.74,
    # 电商腿永续增长；**同业反解**（港股互联网横截面良态三点中位，A4）；cap = min(6%, r − 4%) = 6% 未收紧；L 档 ROE 12.0% 病态区、对 g 不敏感（A20） | as-of 2026-09-20
    'g2_ecom': 0.0207,
    # 云腿永续增长；**同业反解 → 截顶**（云横截面中位 7.02% > 6%，A5）；cap(篮 4 r 10%) = 6% 即上限本身 | as-of 2026-09-20
    'g2_cloud': 0.06,
    # **候选带**用：FY29E 云收入增速（美银单家，A6′）；不进底牌 | as-of 2026-09-07
    'g1_cloud_cand': 0.41,
    # **候选带**用的过渡年数（FY29E 一年，A6′） | as-of 2026-09-07
    'n_cloud_cand': 1,
    # 自身 5 年 GAAP-TTM PE 实测带下沿；**护栏，不入主公式**（A16） | as-of 2026-09-14
    'pe_own_min': 10.02,
    # 自身 5 年 GAAP-TTM PE 实测带上沿（2022 减值年）；护栏（A16） | as-of 2026-09-14
    'pe_own_max': 109.0,
    # GAAP-TTM EPS HKD（Longbridge PE 序列的分母口径，2026-09-11 读数）；只用于护栏换算 | as-of 2026-09-11
    'eps_ttm_gaap': 4.246,
    # 投资组合 NAV 账面 = 战略性股权证券 254,210 + 权益法投资 203,207；已剔除国库投资 176,938（A9）；**市值法 NAV 待补** | as-of 2026-06-30
    'nav_cny': 4.57417e11,
    # NAV L 档折价；严于野村隐含的 41% | as-of 2026-09-06
    'd_l': 0.50,
    # NAV M 档折价 | as-of 2026-09-06
    'd_m': 0.35,
    # NAV H 档折价 | as-of 2026-09-06
    'd_h': 0.20,
    # 净现金 = 现金及其他流动性投资 474,505 − 有息负债 266,530；受限现金 42,585 不计（A10） | as-of 2026-06-30
    'net_cash_cny': 2.07975e11,
    # 2026-08 配售净额 HKD；已在 `shares` 中同步计入新股（A11） | as-of 2026-08-26
    'placement_hkd': 7.97e10,
    # FY2027E（0y）非 GAAP EPS 共识均值 CNY/股（16 家）；扣掉已入账的 6 月季后 = FY2028 年初净资产要滚过的未入账利润（A21）；也做交叉校验 | as-of 2026-09-14
    'eps27_m_cny': 5.71155,
    # 1Q FY27（2026-06 季）非 GAAP 稀释 EPS，已在 2026-06-30 账面里，从 FY2027E 共识里扣掉（A21） | as-of 2026-06-30
    'eps_1q27_cny': 1.07,
    # 近三年实付派息率均值（现金股利 ÷ GAAP 归母净利：FY24 179.5/800.1 = 22%、FY25 290.8/1,301.1 = 22%、FY26 337.3/1,035.9 = 33%，亿 CNY；yfinance 年报现金流量表）；**只进** A21 的 B 桶披露行，不进 BPS 推演（主尺按 \(b_1 = g/ROE\) 滚） | as-of 2026-03-31
    'payout_3y': 0.26,
    # 时点对齐年数 τ = 估值基准日 2026-06-30 → 分子年初 2027-04-01（FY2028 年初）；两条 Gordon 腿与 \(V_{opt}\) 按 `r_perp` 折 τ；也是增长期资金缺口窗口（2Q–4Q FY27 三个季度）的长度（A22） | as-of 2026-06-30
    'tau_yr': 0.75,
    # 归母权益 10,490.38 亿 CNY（yfinance 1H26）；归母比例分子（A22） | as-of 2026-06-30
    'equity_parent_cny': 1.049038e12,
    # 少数股东权益 648.56 亿 CNY（yfinance 1H26）；归母比例 = 10,490.38 ÷ (10,490.38 + 648.56) = 0.9418，乘合并净现金与资金缺口；2026-08 配售由上市母公司募得、按 100%（A22） | as-of 2026-06-30
    'nci_cny': 6.4856e10,
    # 花旗 FY2027E 资本开支 2,580 亿 CNY（Wisburg 106714，2026-09-23）；× `tau_yr` = 窗口 2Q–4Q FY27 资本开支（A22） | as-of 2026-09-23
    'capex_fy27_cny': 2.58e11,
    # 近 3 年经营现金流 ÷ 净利 = (762.13 + 1,635.09 + 1,825.93) ÷ (1,059.04 + 1,294.70 + 797.41)（FY24–26 年报，亿 CNY）；× 窗口共识非 GAAP 利润 = 窗口经营现金流（A22） | as-of 2026-03-31
    'ocf_ni_3y': 1.340,
    # 估值基准日 2026-06-30（年份小数）；资金缺口投产份额起点（A22） | as-of 2026-06-30
    't_base': 2026.5,
    # 分子年 FY2028 年末 2028-03-31（年份小数）；只计这之前投产的扩产（A22） | as-of 2026-09-23
    't_fy28_end': 2028.25,
    # 20GW 算力规划止点 2032 年末（年份小数）；无分项目投产时间表 → 按规划期线性摊（valuation-rules「经营价值与超额现金」①）（A22） | as-of 2026-09-23
    't_plan_end': 2033.0,
    # 云腿新投资**稳态回报**：生意模式兜底「有壁垒的重资产」15%（成熟同业层为空：AWS / Azure / Google Cloud 近 5 年收入增速远高于 10%；自身周期无腿级回报史）（A22） | as-of 2026-10-16
    'ss_return_cloud': 0.15,
    # 电商腿与 ALA 期权的新投资**稳态回报**：自身周期（FY2022→FY2026 谷到谷，公司级投入资本口径剔投资组合与超额现金、加回减值）均值 23.9%（GAAP 不加回 19.4% 只作对照）；高于各档前瞻 ROE → 截在前瞻值，路径不回落（A22 ③） | as-of 2026-10-19
    'ss_return_ecom': 0.239,
    # 回报路径起点 = 分子年 FY2028（A22） | as-of 2026-10-16
    't0_ret': 2028,
    # 高回报期 Y1 = 可见年末（最远共识年 FY2028；云厂商不继承 ai-capex，走默认路径）（A22） | as-of 2026-10-16
    'y1_ret': 2028,
    # 高回报期 Y2 = Y1 + 6 年（云腿进入门槛「高」，依据见 A22） | as-of 2026-10-16
    'y2_ret': 2034,
    # 运行率非 GAAP EPS = 6 月季稀释 1.07 × 4（公告 p.24）；只作 `deep_discount` 压力坐标（A3） | as-of 2026-06-30
    'eps_rr_cny': 4.28,
}

# Market-value NAV was missing in the old inputs; book NAV remains the proxy.
# Historical rationale and supporting observations, copied from the old assumptions;
# these are research context, not additional numerical inputs to the model.
# - **业务地图摘要（为什么必须拆）**：对照 `AGENTS.md` / skill 的分部启发式，2026-06 季材料命中 **6 条**——①两块各自 ≥15% 收入（电商 71.7%、云 16.9%）；②驱动因子完全不同（电商看 CMR take-rate 与竞争，云看算力供给与 token 需求）；③林奇属性按块不同（电商 `stalwart`、云若单列会是 `fast_grower`）；④卖方**全部**在做 SOTP（野村给出绝对金额、摩通/花旗/巴克莱/美银给出分腿倍数）；⑤一块在赚（AEG 19.3% EBITA 率）另一块在大亏（ALA 单季 −138.61 亿）；⑥大额隐蔽资产集中在表外腿（蚂蚁在权益法投资 2,032.07 亿内、战略股权证券 2,542.10 亿）。反信号只有一条：地区披露 100% 记在「中国」，无地域拆分价值。→ **SOTP，不用整公司 PE**。
# - **属性 A — 分部口径在 2026-06 季断裂，这把尺被迫比一年前粗**：新「阿里巴巴电商集团」= 中国电商 + 国际电商 + 盒马 + 菜鸟部分商业业务，收入只按中国电商 / 中国即时零售 / 国际电商 / 全球批发四条线披露，**不再披露分线利润**。后果有三：①淘天的高质量利润与即时零售的巨额投入被压进同一个 397.49 亿 EBITA，**任何「给淘天 15×、给即时零售 0」的分腿写法都已无数据支撑**；②上年同期已按新口径重述（AEG EBITA 399.88 亿），故 YoY −1% 是可读的，但绝对水平的**构成**不可读；③分部级的远期共识同样拿不到——卖方摘要只给增速与利润率的单家路径，**分子只能取整公司共识三点再按运行率权重拆腿**（A1）；汇丰「淘宝天猫 7× PE」这类锚只能当**参照**。
# - **属性 B — 云腿的倍数由增长与 ROE 生成，而 ROE 正是它最脆弱的一环**：云分部当期经调整 EBITA 率仅 **11.6%**，卖方一致用 P/S（花旗 7×、摩通 6× CY26E、野村 7× FY28F、巴克莱 4× EV/Sales FY28、美银 6× FY27E）。旧版跟着用 PS，结果是把「云长期净利率 ≥16%」藏进倍数、又把 FY27E 的 +49.5% 放进分子——同一段增长算了两遍（已收口）。本版云腿 = 共识 FY28E 分子的云份额 × `perpetual_pe(6%, ROE_k)`：增长先进分子（FY28E 共识里已含云放量），永续只装 6% 上限，倍数由 ROE 决定。**要点（2026-10-03 起）**：云腿的留存回报率改用卖方腿级边际 ROIC 16.6%（摩通 ~20% / 大摩 13.2% 中点，A14），不再借整公司 ROE——腿级卖方数优先于「各腿经济性相同」规则；云腿 **11.8–22.6 港元/股**（2026-10-16 起新投资回报 2034 年回落到 15%、折回 τ，A22），等价运行率收入约 **2.1–4.0× PS**（M 档 2.7×），仍低于卖方 6–8×：卖方默认的增量回报在摩通 20% 一端（敏感行 M 124.25）。这是 `roic_cloud` / `g2_cloud` 的证伪落点。
# - **属性 C — AI 要拆两块，禁止混成一笔负价值**：① **AI 云与算力**（含 MaaS / 千问 API 变现）→ 云腿，**已是正贡献**；capex 收益已在共识 FY28E 分子里，**MUST NOT** 再给云开第二条期权（A8/A12）。② **AI Labs and Applications**（千问 App / 夸克 / QwenWork to-C）→ 当期大亏；原则仍是**战略投入不记成负股权**——但整公司共识分子**无法剔出** ALA 的 FY28E 亏损（≥2 家分部级数字不可得），底牌因此按 17 家共识里的 ALA 亏损水平永续，**比 A19 原意更保守**；上行仍进 \(V_{opt}\)（1 份自身已披露收入 × 本票电商利润率 × 本票尺，A19），期权是 ALA 变成正业务的世界，与底牌里的负数不双计。2026-08 配售净额进闭合项现金，**不**另增云腿分子（A11）。
# - **属性 D — 蚂蚁与投资组合只在 NAV 里出现一次**：蚂蚁在权益法投资 2,032.07 亿内（本季确认损益 15.63 亿），**不另计蚂蚁公允价值**；股权证券及其他投资 4,311.48 亿里有 **1,769.38 亿实为国库/流动性投资**（公司「现金及其他流动性投资」4,745.05 亿 减 现金 1,429.14 减 短投 1,546.53），这部分归净现金、**不归 NAV**——不做这道扣减就是把同一笔钱算两遍（A9）。分子端对称地剔除这些资产产生的利息与权益法收益（A9b）。
# - **属性 E — 港股/ADR 双平台与股本口径**：1 ADS = 8 股普通股；2026-08-26 完成配售 7.10 亿新股 @112.70 HKD（净额约 797 亿 HKD，公告明示 100% 投向 AI），HKEX 已发行股数由 191.75 亿升至 **198.85 亿**。本框架用**摊薄口径 200.34 亿股**（6 月季摊薄加权 193.24 亿 + 配售 7.10 亿），高于已发行数，因为库存股 / RSU 增量必须与 non-GAAP EPS 同口径；用已发行数会把 L/M/H 各抬高约 0.7%。
# - **为什么次类是 `turnaround` 而不是 `fast_grower`**：云 +45% 是真的，但它占集团收入 16.9%、集团收入只 +9%，用 `fast_grower` 描述整体是错的；云的成长性通过共识分子里的云份额与云腿 g2 进入主尺，不进林奇标签。真正让 FY2027E→FY2028E 共识 EPS 从 5.71 走到 8.02 人民币（+40%）的，是**自选亏损的收敛**（即时零售单季亏损 360 亿峰值 → 6 月季约 100 亿；ALA 单季 −138.61 亿见顶后卖方预期稳定在 110–120 亿），这是 Lynch `turnaround` 的定价机制——利润修复而非收入增长。该判断可证伪，见 A15。
# - **倍数怎么来（Gordon，篮 4 r=10%）**：两条经营腿的倍数由 `eval/lib/gordon.py` 生成，不取历史或卖方 PE/PS 分位。分子取 ≥2 家共识可见的最远年份 FY2028E（裁决顺序 ②，A1）；电商腿 Gordon（g2 = 同业反解 2.07%；稳态回报截在前瞻，等同 `perpetual_pe`）；云腿 Gordon + 稳态回报三段（g2 = 云同业反解截顶 6%，留存回报率 = 卖方腿级边际 ROIC 16.6%，A14，2034 年回落到 15%，A22）；两腿折回 τ = 0.75 年；电商腿 ROE 按档 = FY28E 共识 EPS 三点 ÷ FY2028 年初 BPS（整公司；分腿权益不可得，A4；年初口径与滚动见 A21）；无两段式（FY29E 单家）。护栏 = 自身 5 年 GAAP-TTM PE 实测带 [10.02, 109.0]（A16），三档整票 22.8 / 29.2 / 42.2× 在带内——但该带上沿是 2022 减值年的印记、下沿是分母塌缩前的印记，护栏很弱，故同时报出 Longbridge「合理区间」16.05–28.37：本版三档都高于其上沿，这是 `turnaround` 在被自选亏损压低的 GAAP-TTM 分母上的正常形态。
# | A1 | 主尺为**两腿 SOTP + 两项闭合**；分子 = **FY2028E 非 GAAP EPS 共识三点**（yfinance 9988.HK `+1y`，17 家：低 6.35 / 均 8.02364 / 高 11.67947 CNY/股），三档取自同一分布两端。**为何是 FY2028E**（裁决顺序 ②）：≥2 家共识可见的最远年份——FY2029E 只有美银单家（104416：云 +41%、无 EPS）→ 不进分子也不进 g1；阿里财年 3 月截止，FY2028（2027-04 ~ 2028-03）= 当前财年 FY2027 + 1，Gordon 给的是 FY2028 年初（2027-04-01）的价值，按 A22 时点对齐折回估值基准日（τ = 0.75 年；旧口径「FY+1 不折现」2026-10-16 撤）。分部级 FY28E EBITA 无 ≥2 家（美银只给云增速 × 利润率路径；高盛只给 9 月 / 12 月季云增速；摩通只给 FY26 中国电商 EBITA 1,075 亿）→ 整公司共识剔非经营收益后按运行率经调整 EBITA 权重拆腿（A1b），只决定各部分配哪个 g2。**印证**：FY28E 均值 8.02 − 非经营 0.58（A9b）= 7.45 CNY/股经营分子 vs 运行率 AEG+云税后 7.25（上一版分子）——共识 FY28E ≈ 「今天的 AEG+云再长一截、把收窄后的亏损腿吸收掉」；摩通 TP 205 = 16× FY28E 与本框架同年。旧版运行率分子把 FY27E→FY28E 的可见收敛全部抹掉，已按 ② 纠正 | active | yfinance `earnings_estimate`（2026-09-14 拉取；历史本地缓存）；6 月季公告 p.24 非 GAAP 稀释 EPS 1.07；Wisburg 104416 / 102243 / 104902 | eps28_l/m/h_cny |
# | A1b | **两腿权重 = 运行率经调整 EBITA**：AEG 39,749 / 云 5,628（6 月季）→ w_ecom **87.6%** / w_cloud **12.4%**。共识 FY28E 里云份额大概率更高（云 EBITA +133% YoY；美银 FY28 云 EBITA 率 15%），但分部级 FY28E 无 ≥2 家 → 用已实现权重（偏保守方向已知）。敏感性：w_cloud 25% → M +4.5 | active | 6 月季公告分部 EBITA 表 | w_ecom / w_cloud |
# | A2 | **分部口径断裂**：2026-06 季起重组为 阿里巴巴电商集团 / AI 云与算力服务 / AI Labs and Applications / 所有其他；AEG = 中国电商 + 国际电商 + 盒马 + 菜鸟部分商业业务，仅披露四条**收入**线、不披露分线利润；上年同期已重述。故电商腿**只能整段取**，不得给淘天单独倍数 | active | 6 月季业绩公告 Note (1)（HKEX 2026-08-20 公告全文，本地 历史本地缓存） | 权重取法；禁止更细分腿 |
# | A3 | **分子与 g 同世界**：FY2028E 共识是「亏损收敛后的稳态年」——即时零售亏损（美银：800 亿 → 400 亿）、ALA 亏损见顶（高盛）、云放量都在 17 家的分布里；配稳态 g2，不走回归段。**运行率不是分子**：6 月季非 GAAP EPS 1.07 × 4 = 4.28 CNY 是被自选亏损压住的谷底运行率（集团 EBITA −30%），用它配稳态 g2 = 把周期算两遍（裁决顺序 ②「MUST NOT 用当期 EPS × 稳态倍数覆盖共识明示的增长」）；运行率 × 同一套倍数（72.0 @L / 77.6 @M，同折 τ、同扣缺口）只作 `deep_discount` 压力坐标。AEG 6 月季 EBITA 39,749（YoY −1%，重述口径）与云 5,628 只作权重与桥 | active | 6 月季公告分部表与 p.24；yfinance FY27E→FY28E +40% | 分子口径；表2 压力坐标 |
# | A4 | **电商腿倍数 = `perpetual_pe(g2_ecom, ROE_k, 0.10)`**，g2_ecom = **2.07%，来源层级 = 同业反解**（港股互联网横截面，同一把尺、同日 2026-09-11 收：腾讯 forward 12.19× / ROE 20.93% → +2.96%；网易 11.34× / 20.53% → +2.07%；京东 7.13× / 6.63% → −4.03%；良态三点中位 2.07%——腾讯对本票不是自身，⑦ 不剔；阿里自身 ROE 7.11% 与 r 之差 <3% 属病态、不进中位，小米/联想同理，百度/美团亏损，快手口径不一致；明细见 历史本地缓存）。**括号**：同业务腿京东 −4.03%（下）、卖方 TP 隐含混合 g 6.0–7.4%（上，A16）。ROE 三档 = FY28E EPS 7.41 / 9.36 / 13.63 HKD ÷ **FY2028 年初** BPS 61.90 / 61.65 / 61.36（2026-06 账面 60.74 按 \(b_1=g/ROE\) 滚过未入账的 2Q–4Q FY27，A21）= **12.0% / 15.2% / 22.2%**（整公司 ROE，含投资组合与现金；AEG 分腿权益不可得，A2e 5b 允许并须写明；经营 BPS 22.0 的敏感性 M +8.3）→ 倍数 **10.43 / 10.89 / 11.43×**，派息率 0.83 / 0.86 / 0.91（稳态回报三段：自身周期 23.9% 高于三档前瞻 ROE → 截在前瞻，倍数不变，A22 ③）。±1pp → M 120.64 / 128.34 | active | Longbridge `compare` + `forecast-eps`（2026-09-14 拉取）；Longbridge `valuation` BPS 60.7395 | `g2_ecom`、`roe_*`、电商腿倍数 |
# | A5 | **云腿倍数 = `perpetual_pe(g2_cloud, roic_cloud, 0.10)` 作用于共识 FY28E 分子的云份额**（2026-10-03 起 ROE 改腿级边际 ROIC，A14），不再用 PS、不再两段式。g2_cloud = **6%，来源层级 = 同业反解 → 截顶**：云同业横截面（汇丰市场隐含 2028E EV/EBIT 经本仓 Gordon 单位反解，`GOOG.US` A7，2026-09-09）AWS +7.26% / Azure +7.02% / Google Cloud +3.97%，中位 7.02% > 上限 → 截到 6%（原值注明）。**横截面不是同日、不是港股**（港股无盈利云同业：金山云亏损、百度云不单列），是本票 g2 链条里最弱的一环；上限已绑定，同日重拉只要仍 ≥6% 结论不变。倍数 **15.12×** 三档同值（2026-10-16 起新投资回报走稳态回报三段：16.6% 到 2028，2034 年线性回落到 15%，A22；永续沿用 16.6% 时 15.96×）（ROIC 16.6%，派息率 0.64；旧整公司 ROE 口径 12.47 / 15.12 / 18.25× 撤销）；云腿等价运行率收入 **2.4 / 3.1 / 4.5× PS**，卖方 6–8× 的差来自「他们默认的增量资本回报在摩通 20% 一端以上」（属性 B）。敏感性：g2_cloud 5% → M 122.35 | active | `GOOG.US` A7 / A20（汇丰 99586）；`eval/lib/gordon.py` | `g2_cloud`；云腿倍数 |
# | A6 | **云腿过渡段撤销**：FY27E 云增速（高盛 50% / 美银 51% / 瑞银 50%）已被 FY2028E 共识分子吸收（增长先进分子，裁决顺序 ②）；FY28E 云增速（美银 56%）同理。底牌无 g1，直接 `perpetual_pe`（与 n=0 的两段式恒等——2026-09-14 起两把尺同一估值时点，分子 = 下一期盈利）。旧版「运行率云 EBITA × 1 年 50% 过渡、段一派息率 −3.0/−2.5/−1.9」撤销 | active | Wisburg 102243 / 104416 / 102241；valuation-rules「两段式过渡」 | 无 `g1_cloud` / `n_cloud` |
# | A6′ | **候选带（FY29E 云增速·美银单家）**：FY29E 云收入增速只有美银一家给出（41%），不够 ≥2 家；候选带让云腿在 FY28E 分子之上多跑 1 年 g1 = 41%（`two_stage_pe(0.41, 1, 6%, ROE_k)`，估值时点与底牌同：FY28E = t=1、FY29E 为过渡后年、尾段在 t=1 取值折一年，A2e-3；段一派息率 1 − 0.41/ROE_k = −2.54 / −1.77 / −0.88 即发股融资的增长；账面按候选带自己的公司级 g = 87.6%×2.07% + 12.4%×41% = 6.90% 滚（A21）→ ROE 11.6 / 14.8 / 21.8%、\(b_1\) 0.60 / 0.47 / 0.32；其余同公式）→ L′/M′/H′ = 98.73 / 126.65 / 183.12（2026-10-16 起同走稳态回报三段、时点对齐、归母份额与资金缺口，A22；此前 106.65 / 136.62 / 197.57）（2026-10-03 云腿段一 / 段二 ROE 改腿级 ROIC 16.6%，账面按各腿 b 滚：ROE 11.7 / 14.9 / 21.7%、\(b_1\) 0.46 / 0.43 / 0.39）。云腿倍数按**过渡后 FY29E 分子**读 = 12.77×（FY28E 分子读数 18.00× 含 g1，只作交叉；均为 FY2028 年初口径）——低于底牌云腿 15.12× 的部分是段一负派息（发股）加一年折现，高于的部分只是 FY29E 那一年的单家增速。**升级门槛**：≥2 家给出 FY29E 云收入增速 → 升级为底牌并删除本行。它不是「多一年复利」的伪装：缺失输入具名（FY29E 云增速第二家），且 `check_transition_years` 对候选带不适用（本就因单家而未进底牌） | active | 美银 104416（FY27/28/29 51% / 56% / 41%） | 候选带一行 |
# | A7 | **亏损腿撤销**：旧版按运行率残差（所有其他 + 未分摊 + 抵销 = −41.87 亿/季）× 3.0 / 1.5 / 0 年资本化。共识 FY2028E EPS 已含「所有其他 / 未分摊 / ALA」在各家模型里的亏损路径（17 家分布的 −21% / +46% 主要就是这条路径的分歧），再扣即双计。恒等式（AEG 39,749 + 云 5,628 + 残差 −18,048 = 集团 27,329，含 ALA −13,861）只作 A2 / A3 的口径核对，不入公式。即时零售亏损仍埋在 AEG 内，同样在共识里 | active | 6 月季公告分部 EBITA 表 | 无 `loss_years_*` |
# | A8 | **MaaS / 云内千问变现已在云腿分子内**（AI 相关产品收入 123.76 亿/季；共识 FY28E 含其增长），**MUST NOT** 再按汇丰 Anthropic 21× P/ARR 给云/MaaS 第二条期权。**ALA to-C**（千问 App / 夸克 / QwenWork）与 MaaS **分家**：上行走 \(V_{opt}\)（A19） | active | 6 月季公告（AI 相关产品收入 12,376）；汇丰 95277；对话 2026-09-11 | 防云腿与 \(V_{opt}\) 双计 |
# | A9 | **NAV = 战略性股权证券 2,542.10 亿 + 权益法投资 2,032.07 亿 = 4,574.17 亿 CNY**（2026-06-30）。战略性股权证券 = 股权证券及其他投资 4,311.48 − 其中计入公司「现金及其他流动性投资」的国库投资 1,769.38，**不做这道扣减即与净现金双计**。蚂蚁在权益法投资内，**不另计公允价值**。折价 d = **50% / 35% / 20%**：野村「非核心资产净值 $400 亿」= 账面的 **59%**（隐含折价 **41%**），落在 L 与 M 之间。**口径待补**：市值法 NAV（逐笔上市持股）未做，账面为代理 | active | 6 月季公告资产负债表；野村 102510；美银 102215 | `nav_cny`、`d_l/m/h` |
# | A9b | **分子剔除非经营收益（防与 NAV / 净现金双计）**：非 GAAP 净利里保留的非经营项（6 月季，公告 p.12 与 p.22–23）= 利息及投资收益净额 9,004 − 剔出非 GAAP 的投资处置/重估收益 5,364 + 投资减值 661（= 减值合计 9,202 − 经营内商誉减值 8,541） − 利息支出 2,352 + 其他收益 495 + 权益法收益 934（蚂蚁 1,563 + 其他 605 − 基差等 −1,234）= **3,378 百万税前**；核对：经调整 EBITA 27,329 + 3,378 − 非 GAAP 税（12,798 − 税务影响 2,806 = 9,992）= 非 GAAP 净利 20,715 ✓。税后：应税部分 (3,378 − 934) × (1 − 20%) + 权益法 934 = **2,889 百万/季** → 年化 ÷ 股本 = **0.577 CNY/股**，从 FY28E 共识三点同额剔除（共识的 FY28E 利息 / 权益法收益不可得，以运行率代理；配售后现金增加的利息约 +0.06 港元/股，忽略）。ROE 仍用全口径 EPS（资产在分母里）。敏感性：不剔 → 三档 +6.9 / +7.2 / +7.5 | active | 6 月季公告 p.12、p.22–23 原文 | `nonop_pretax_q_cny`、`eq_method_q_cny`、`tax_rate` |
# | A10 | **净现金 = 4,745.05 − 有息负债 2,665.30 = 2,079.75 亿 CNY**（现金 1,429.14 + 短投 1,546.53 + 国库投资 1,769.38；有息负债 = 流动银行借款 306.14 + 非流动银行借款 560.07 + 无抵押优先票据 1,157.16 + 可转债 549.05 + 可交换债 92.88）。**受限现金 425.85 亿不计入**。与高盛 2,080 亿一致 | active | 6 月季公告资产负债表；高盛 102198、美银 102215 | `net_cash_cny` |
# | A11 | **配售**：2026-08-26 完成 7.10 亿新股 @112.70 HKD，净额约 **797 亿 HKD**，公告明示 100% 投向全栈 AI。计入闭合项现金；分子锁定共识 FY28E，不因这笔钱另给增量。股本用**摊薄 200.34 亿股** | active | 配售完成公告 2026-08-26；HKEX 月报表 2026-08-31 | `placement_hkd`、`shares` |
# | A12 | **云/capex 只计一次**：capex 收益在共识 FY28E 分子的云份额与云腿 g2；代价在 FCF（本年为负，交叉尺失效）与观察项；**MUST NOT** 再给云开期权，也 **MUST NOT** 因 FCF 转负在电商/云各扣一次。**ALA \(V_{opt}\) 不在本条禁止范围内** | active | 6 月季现金流量表；摩通 102280、摩士 102308 | 防云双计；为 A19 让路 |
# | A13 | **禁止用现价倒推 L/M/H**。现价不进本文，zone 由日报 / app 用实时报价从底牌派生 | active | 用户约束；仓库惯例（`0700.HK` A11） | 定锚纪律 |
# | A14 | **ROIC 质量**：集团 ROE TTM 仅 **7.11%**（被自选亏损压制）；FY28E 共识口径 12.0–22.2%（FY2028 年初净资产，A21）。AI capex 项目级回报（卖方口径）：摩通税后 IRR **22.1%**、ROIC ~20%；摩根士丹利自建 IaaS ROIC **13.2%**（美国同类 31.1%）；美银 15–20%（管理层目标，3 年现金回收期）。**2026-10-03 起云腿留存回报率取这些腿级卖方数**（valuation-rules「数据优先级与同业同尺」：腿级卖方预测优先于「各腿经济性相同」的共享规则，旧版用整公司 ROE 违反此序）：摩通 ~20% 与摩根士丹利 13.2% 的中点 **16.6%**（`roic_cloud`，三档共用；美银 15–20% 为管理层目标、不入点值），两端作敏感行 13.2% → 95.60 / 122.54 / 176.86、20% → 96.93 / 124.25 / 179.41（稳态回报三段下 20% 一端也在 2034 年回落到 15%，两端差收窄）；与 `GOOG.US` A26 / `AMZN.US` A4 / `MSFT.US` A4「云腿留存回报率 = 卖方腿级新投资本 ROIC」同一取法。证伪 / 复核：阿里披露云分部资产或 ≥2 家卖方给出同口径云 ROIC → 替换 | active | Longbridge financial-report（ROE TTM 7.1095）；摩通 102280、摩根士丹利 101176/102308、美银 104416 | 云腿倍数上限；观察项 |
# | A15 | **次类 `turnaround` 的可证伪条件**：FY2027E→FY2028E 共识 EPS **5.71→8.02 CNY（+40%，yfinance 同源）**的兑现路径**主要来自亏损收敛**，而非收入增长（收入共识 +12.7%）。**证伪触发器**：若某季 AEG 收入增速回到双位数且 CMR 同口径 >+8%，而亏损腿收敛慢于卖方路径 → 次类改回纯 `stalwart`。**反向触发器**：若非 ALA 亏损腿两季不再收窄（残差连续两季 ≤ −180 亿）→ 本条改 `weakened`，并检查 FY28E 共识是否随之下修（分子会自动跟随） | active | yfinance 2026-09-14；6 月季公告 | 林奇次类；分子跟随共识 |
# | A16 | **护栏**：自身 5 年 GAAP-TTM PE 实测带 [10.02, 109.0]（Longbridge 60 点月频；上沿为 2022 减值年印记）；Longbridge「合理区间」16.05–28.37 作参照。整票倍数 = 锚点 ÷ GAAP-TTM EPS 4.246 HKD（Longbridge PE 序列的分母口径，2026-09-11 读数）= 22.8 / 29.2 / 42.2×，在实测带内。**带即证据**（裁决顺序 ③）：M 档 ROE 15.2% 下带边反解 g = [−64%（病态：下沿是 GAAP 分母塌缩前的印记）, +9.3%]——本票护栏几乎无信息，如实标弱。**TP 隐含**（交叉，不作锚）：TP 166–205 ÷ FY28E 均值全口径 EPS 9.36 HKD = 17.7–21.9×；扣 NAV(65%) + 现金后经营腿 15.3–19.7× → 混合 g 6.0–7.4%（全部 ≥ 上限）。PEG 不作定锚 | active | Longbridge `valuation 9988.HK --history --indicator pe --range 5`（2026-09-14）；yfinance TP 2026-09-14 | `pe_own_min/max`、`eps_ttm_gaap` |
# | A17′ | **观察项**：① 即时零售补贴战时长（摩通：监管限制降低重演 >800 亿支出周期的可能，但支出可能转移到 AI 代理免费派单等未被规则覆盖的类别）；② ALA 单季 −139 亿且无多年减亏计划（摩通 104902）——共识 FY28E 里的 ALA 路径若下修，分子跟随下移；③ AI capex ROIC 低于美国同类（A14）；④ 蚂蚁监管；⑤ 配售稀释（A11）；⑥ NCI（A18）；⑦ FY28E 共识本身的修正（90 天内 +1y 均值 8.29 → 8.02） | active | Wisburg；yfinance eps_trend | zone 解释 |
# | A19 | **AI Labs \(V_{opt}\)（2026-10-03 按 valuation-rules「未建模期权」重建：份数来自本票的量、借量不借价、按兑现年折回）**：**份数** = 1 份自身已披露 ALA 分部收入（6 月季 33.38 亿 × 4 = 133.52 亿 CNY），公司无 ALA 收入目标 → 标「快照·下限」；**单位经济** = 本票电商集团 EBITA 率 397.49 ÷ 2,058.62 = **19.3%**（ALA 当期大亏、无卖方 ALA 利润率、无法公开推断 → 取数序末级「共享规则·拍值」：to-C 互联网业务做成后的利润率按本票自己的消费互联网腿），× (1 − 20%) = 20.62 亿 CNY 税后；**尺** = ALA 腿篮 4 常规经营 **10%**（`r_ala`，A20；2026-10-03 前为篮 7 15%、倍数 7.01×、期权 0.64）、g2 = 电商腿的港股互联网反解 2.07%、ROE = H 档整公司 22.2% → `perpetual_pe` **11.43×**；**时点** = 无具名年份 → 对齐年份 FY2028 + 2 = **FY2030**，标「无时点锚·拍值」，÷ 1.10² = 1.14，再随底牌折 τ（× 0.9310，A22）→ **1.06** 港元/股。**旧版撤销**：133.52 亿 × 港 A 股 AI 公司实测 PS 6× = 4.67——借同业倍数定价，违反「借量不借价」。**底牌里 ALA 的处理**不变：整公司共识分子含 ALA 的 FY28E 亏损（分部级 ≥2 家不可得）→ 底牌按共识内的亏损水平永续，比原意更保守；**待补**：≥2 家 FY28E ALA EBITA 到齐后从分子加回（走框架纠正）。期权与底牌不双计（底牌里 ALA 为负，期权是 ALA 变成正业务的世界）。\(p_L/p_M/p_H=0/0.25/1.00\)，\(p_M\) 无概率锚·拍值。**升级门槛**：公司给出 ALA 收入目标 → 份数 = 目标 − 共识已含；ALA 分部 EBITA 转正或 ≥2 家卖方给出可复算贡献利润 → 换掉拍值利润率 / 迁出 \(V_{opt}\) 做成腿。**证伪**：连续两季 ALA 收入同比转负且无产品 DAU/MAU 披露支撑 → \(V_{opt}\) 置 0 | active | 6 月季分部收入 3,338 / AEG 收入 205,862、EBITA 39,749；valuation-rules「未建模期权」2026-10-03 | `rev_ala_q_cny`、`rev_aeg_q_cny`、`r_ala`、`t_opt`、`t_num`、`v_opt` |
# | A18 | **少数股东权益（NCI）不单列为闭合项，判定为不重大，但方向须写明**：2026-06 季少数股东损益 **1.70 亿 CNY** ÷ 净利润 106.14 亿 = **1.6%**。共识 EPS 已是归属普通股股东口径，NCI 天然在分子外。**证伪触发**：若某季少数股东损益占净利润 >5%，须复核共识口径 | active | yfinance `BABA.quarterly_income_stmt`（2026-09-07）；6 月季公告 p.23（non-GAAP 归属普通股股东 20,583） | 闭合项（当前不计） |
# | A20 | 归篮：电商腿 / 云腿 → 篮 4 龙头制造（平台龙头，两条经营腿都是常规经营现金流；NAV 与净现金按折价 / 面值，无 r；无备选篮；两腿同篮 → 分腿 r 相同，SOTP 加总不变）；**ALA to-C 期权腿 → 篮 4 常规经营**（`r_ala`，只进 \(V_{opt}\)；2026-10-03 改归，**初分篮 7 单押 / 故事被推翻，留痕**：初分判据「当期大亏、变现未证」按 valuation-rules「§r 篮子」2026-10-03 不再是篮 7 理由——篮 7 只认对手方与国别，本腿是千问 App / 夸克的 to-C 订阅与流量变现，付款方是分散的个人用户与广告主，无单一客户 ≥50% / 前两大 ≥70%，收入不依赖未落定融资、未签约客户或或有负债，经营在中国本土、与电商 / 云两腿同国别、无单列的高国别风险；**篮 4 判据正向成立**：消费互联网服务、价格由公司自定，盈利不是商品价函数（非篮 6），无照付不议合约（非篮 1），非监管定价（非篮 2），非专利许可（非篮 3），非银行（非篮 5）；变现成败进 \(V_{opt}\) 的 \(p_k\)，不进 r。不取篮子对：篮 7 判据今天就不成立，无过渡篮可言。**证伪点**：ALA 收入转为依赖单一或两家对手方（单一 ≥50% / 前两大 ≥70%）或依赖未落定融资 → 回篮 7）；CAPM 粗筛：未取（无专属节，归篮按业务性质）。g2 cap = min(6%, r − 4%) = 6%，未收紧：\(g_{ecom}\) 2.07% 同业反解沿用（A4），\(g_{cloud}\) 6% 截顶沿用（A5）。域判定：ROE 12.0 / 15.2 / 22.2% − 10% = **+2.0pp（L 病态区）** / +5.2pp / +12.2pp（M、H 单调区）；病态区规则要求显式陈述：L 对 g 不敏感——\(g_{ecom}\) ±1pp 下 L 95.51 / 98.29（−1.3% / +1.6%），L 档电商倍数 10.43× 贴 1/r（云腿按腿级 ROIC 16.6%，单调区）；M/H 留存分支合法。r 只归篮、不拧：港股流动性折价与亏损收敛可信度不进本票 r；港股附加是否进篮子主值属仓库级议题，单票不动 | active | `gordon.BASKET_R`；`valuation-rules.md`「§r 篮子」 | r_perp；两腿倍数 |
# | A21 | **ROE 口径 = 分子年盈利 ÷ 分子年年初净资产（\(E_{n+1}/B_n\)），账面按增长所需留存滚动（valuation-rules 裁决表 ② / 两段式过渡，2026-09-21 定）**：\(ROE_k = EPS_{FY28,k} ÷ BPS_{FY28 年初,k}\)，Gordon 的 \(g = b × ROE\) 里 ROE 是期初权益产出本期利润；年末口径会把本年尚未产出的留存放进分母，2026-06 账面直接作分母则少了三个季度的留存。FY2028 年初 = 2027-03-31：从 2026-06-30 账面（1Q FY27 末，BPS 60.74）起、只滚 **2Q–4Q FY27 尚未入账**的利润 N = FY2027E 共识 5.71 − 1Q FY27 实测 1.07 = 4.64 CNY = **5.42 港元/股**，**留存率 = \(b_1 = g/ROE\)**——底牌无 g1 窗口，三档按两腿各自 `perpetual_pe` 收的 b 加权：电商 87.6% × 2.07% ÷ ROE_k + 云 12.4% × 6% ÷ 腿级 ROIC 16.6%（2026-10-03 起云腿 b 按 `roic_cloud`，A14）；候选带的云腿背 g1 41%，其公司级 g = 6.90%、自己滚（A6′）。ROE 与 BPS 互相依赖，闭式解 \(BPS = (60.74 + 5.42 × w_c g_c / ROIC_c) / (1 − w_e g_e × 5.42 / EPS_k)\)。得 BPS_FY28 年初 = **61.80 / 61.63 / 61.43**、ROE **12.0 / 15.2 / 22.2%**、\(b_1\) = 0.20 / 0.16 / 0.13（候选带 0.46 / 0.43 / 0.39）。实付留存（74%，`payout_3y`）超出 \(b_1\) 的部分是留存去向审计的 B 桶，走 Outputs 披露行「模型视同派出、实际留存的现金」= (74% − \(b_1\)) × 5.42 = **2.95 / 3.12 / 3.32 港元/股**（它是锚点的前提「不被烧掉」，不是锚点外的价值，MUST NOT 另作腿；阿里实际靠回购而非派息返还，故实付派息率偏低、B 桶偏大，只披露）。旧口径留痕：2026-06 账面直接作分母 = 12.2 / 15.4 / 22.4%（底牌 101.81 / 132.95 / 196.73）。v2（整公司 ROE 两腿共用）101.37 / 132.60 / 196.48 与旧口径差 −0.4% / −0.3% / −0.1%：分母只多了三个季度的增长所需留存，zone `conservative` 不动。已知方向：N 取非 GAAP 口径（与 ROE 分子同口径），高于 GAAP 入账利润，滚多了一点 → ROE 偏低（保守）；配售 797 亿港元不在 60.74 内（`bps_hkd` 沿用配售前口径，构造选择不改） | active | 6 月季公告 p.24 非 GAAP 稀释 EPS 1.07；FY2027E 共识 yfinance 2026-09-14；yfinance 年报现金股利 / 归母净利 FY24–26；valuation-rules 2026-09-21 | `eps27_m_cny`、`eps_1q27_cny`、`payout_3y`（只进披露行）；表1 ROE 列；A4 / A5 / A6′ 倍数 |
# | A22 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④，2026-10-16 框架纠正）**：① **超额现金**：本框架已把净现金按面值单列在闭合项、分子已剔利息等非经营收益（A9b）→ 保留原结构，不重切现金行；**归母比例** = 10,490.38 ÷ (10,490.38 + 少数股东 648.56) = **0.9418**（无子公司级现金披露，按权益比例），乘合并净现金 2,079.75 亿；2026-08 配售由上市母公司募得，按 100%。**增长期资金缺口**：窗口 = 2Q–4Q FY27（2026-07 至 2027-03，三个季度）；资本开支取花旗 FY27E 2,580 亿 × 0.75 = 1,935 亿；经营现金流无卖方预测 → 窗口共识非 GAAP 利润 929.9 亿 × 近 3 年实测经营现金流 ÷ 净利 1.340 = 1,246 亿 → 缺口 689 亿；**只计 FY2028 年末（2028-03-31）前投产的部分**：公司无分项目投产时间表，20GW 算力规划到 2032 年末 → 从估值基准日线性摊，(2028.25 − 2026.5) ÷ (2033.0 − 2026.5) = **26.9%** → **185.5 亿** × 归母比例 → 每股 **1.02 港元**从净现金扣；其余 73% 的产出落在分子年之后，没有可单列的收入与回报，不建期权。**有缺口 → 窗口可分配利润记 0**（用户 2026-10-16 裁定：缺口摊到只剩 1.02 港元也照此处理；「窗口照计、只扣缺口」那一读 M 128.00 不采用）。② **时点对齐**：两条经营腿是 FY2028 年初（2027-04-01）的价值，估值基准日 2026-06-30 → τ = **0.75 年**，按 r 10% 折 **0.9310**；NAV 与净现金是今天的值，不折；\(V_{opt}\) 先折到 FY2028、再同折 τ；候选带同。③ **稳态回报三段**：高回报期 \(Y_1\) = **2028**（默认：可见年末；云厂商不继承 `_AXIS.ai-capex` 的高回报期）、\(Y_2\) = **2034**（云腿进入门槛判「高」→ 回落 6 年；依据：数据中心建设与供电 2–3 年、企业客户迁移与认证周期长、国内新进入者十年未撼动前三格局、单位算力投资额极高）。**云腿**：前瞻 16.6%（腿级 ROIC，A14）→ 稳态 **15%**，取自生意模式兜底「有壁垒的重资产」——成熟同业层为空（AWS / Azure / Google Cloud 近 5 年收入增速远高于 10%，不是成熟同业）、自身周期层无腿级回报史（分部资本不披露）；倍数 15.96 → **15.12×**。**不按叙事换代处理**（用户 2026-10-16 裁定）：阿里云有十多年分部利润史，自身周期取不到是数据缺口、不是业务模式变化，判据①不成立；若按叙事换代（稳态 = min(前瞻, 30%) 不回落）→ 97.42 / 124.88 / 180.36，只作对照。**电商腿与 ALA 期权（按序取，2026-10-19 规则）**：**自身周期可用**——平台生意模式未变（即时零售是腿内新业务、远不到腿收入 30%，补贴战是周期的一部分），取最近一轮完整谷到谷 FY2022（监管谷）→ FY2026（即时零售补贴谷）的公司级投入资本回报均值（分部资本不披露，与电商腿用整公司 ROE 同口径）：分子 = 经营利润（GAAP）加回商誉 / 资产减值 × (1 − 税率)，分母 = 年初总权益（含少数股东）+ 借款 + 票据（含可转债）+ 经营租赁 − 现金与短期投资 − 投资组合与长期投资（证券投资 + 其他投资）+ 经营所需现金锚（窗口内最低净现金 / 收入 9.7% × 收入）→ 年读数 21.7 / 23.2 / 28.8 / 33.3 / 12.6%，均值 **23.9%**（不加回减值的 GAAP 读数 19.4%，只作对照；摊销与股权激励未加回，非 GAAP 同口径会更高；东财 F10 港股年报 + 20-F 经营租赁）。三档前瞻 12.0 / 15.2 / 22.2% 均低于自身 → 稳态截在前瞻，倍数不变（旧版「平台兜底 30%」的来源改为自身周期，值不变）；g2_ecom 的同业腾讯 / 网易自身投入资本回报远高于其前瞻（`0700.HK` A15 ③），京东前瞻 6.63% 已低于 r（持续失败维持前瞻），三家都取前瞻，重解不变；g2_cloud 6% 是截顶值，回报降则反解 g 只升，仍截 6%。不属商品腿豁免。④ **打折 k**：本框架无 k | active | 6 月季公告资产负债表；yfinance 1H26 少数股东权益与 FY24–26 年报现金流；花旗 FY27E 资本开支（Wisburg 106714，2026-09-23）；valuation-rules「经营价值与超额现金」①–④ | `tau_yr`、`equity_parent_cny`、`nci_cny`、`capex_fy27_cny`、`ocf_ni_3y`、`t_base`、`t_fy28_end`、`t_plan_end`、`ss_return_cloud`、`ss_return_ecom`、`t0_ret`、`y1_ret`、`y2_ret`；两条经营腿、净现金、\(V_{opt}\)、候选带 |

REQUIRED = (
    "shares", "fx_cny_hkd",
    "eps28_l_cny", "eps28_m_cny", "eps28_h_cny",
    "nonop_pretax_q_cny", "eq_method_q_cny", "tax_rate",
    "ebita_aeg_q_cny", "ebita_cloud_q_cny",
    "rev_ala_q_cny", "rev_aeg_q_cny", "r_ala", "t_opt", "t_num", "roic_cloud",
    "r_perp", "bps_hkd", "g2_ecom", "g2_cloud", "g1_cloud_cand", "n_cloud_cand",
    "pe_own_min", "pe_own_max", "eps_ttm_gaap",
    "nav_cny", "d_l", "d_m", "d_h",
    "net_cash_cny", "placement_hkd",
    "eps27_m_cny", "eps_1q27_cny", "payout_3y",
    "tau_yr", "equity_parent_cny", "nci_cny", "capex_fy27_cny", "ocf_ni_3y",
    "t_base", "t_fy28_end", "t_plan_end",
    "ss_return_cloud", "ss_return_ecom", "t0_ret", "y1_ret", "y2_ret",
)

SCENARIOS = ("l", "m", "h")


def path_pe(g1: float, n: int, g2: float, roe: float, r: float, r_s: float, v: dict[str, float]) -> float:
    """Three-segment RONIC path (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    gordon.py helper is not built yet).  Multiple on the numerator year (t = 1 <-> calendar
    t0_ret), same convention as two_stage_pe: n transition years at g1 earn the forward
    return; then at g2 the retention of calendar year c earns the forward return while
    c <= y1_ret, falls linearly to the steady return by y2_ret, and the steady return holds
    in a Gordon tail from y2_ret.  The steady return is capped at the forward return.
    With n = 0 and r_s >= roe this equals perpetual_pe(g2, roe, r)."""
    t0, y1, y2 = int(v["t0_ret"]), int(v["y1_ret"]), int(v["y2_ret"])
    rs = min(roe, r_s)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs
        return roe + (rs - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(int(n)):  # stage-1 payout deliberately not floored (two_stage_pe convention)
        pv += e * (1.0 - g1 / roe) / (1.0 + r) ** t
        e *= 1.0 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g2, rs) / ((r - g2) * (1.0 + r) ** (t - 1))
        pv += e * payout(g2, ron(cal)) / (1.0 + r) ** t
        e *= 1.0 + g2
        t += 1


def compute(v: dict[str, float], candidate: bool = False, flat_at_m: bool = False) -> dict:
    """Recompute the historical chain from the inputs in this script."""
    fx = v["fx_cny_hkd"]
    r = v["r_perp"]
    # A9b: run-rate non-operating income retained in non-GAAP NI, taxed except the equity-method share
    nonop_q = (v["nonop_pretax_q_cny"] - v["eq_method_q_cny"]) * (1 - v["tax_rate"]) + v["eq_method_q_cny"]
    nonop_ps = nonop_q * 4 / v["shares"]
    w_ecom = v["ebita_aeg_q_cny"] / (v["ebita_aeg_q_cny"] + v["ebita_cloud_q_cny"])
    w_cloud = 1.0 - w_ecom
    nav_ps = v["nav_cny"] * fx / v["shares"]
    cash_ps = (v["net_cash_cny"] * fx + v["placement_hkd"]) / v["shares"]

    e_full = {k: v[f"eps28_{k}_cny"] * fx for k in SCENARIOS}
    e_ops = {k: (v[f"eps28_{k}_cny"] - nonop_ps) * fx for k in SCENARIOS}
    # ROE = E_{n+1} / B_n: FY28E EPS over the book at the OPENING of FY2028
    # (= end-FY2027), not the June-2026 book and not the FY2028 year-end book
    # (valuation-rules 裁决表 ② as of 2026-09-21; A21).  The June-2026
    # book (end of 1Q FY27) is rolled over the FY2027E earnings not yet booked
    # (consensus minus the June quarter) at the GROWTH-REQUIRED retention
    # b1 = g/ROE, g = the company-level g the multiples charge next: the
    # EBITA-weighted blend of the two legs' g2 in the deck (no g1 window), or
    # of g2_ecom and g1_cloud_cand in the candidate band.  ROE and BPS depend
    # on each other; closed form BPS = BPS0 / (1 - g N / EPS).  FY2028's own
    # retention is NOT rolled (that would be the year-end error).  Actual
    # retention beyond b1 is the B bucket: disclosure only, not in BPS.
    g_cloud_roll = v["g1_cloud_cand"] if candidate else v["g2_cloud"]
    g_roll = w_ecom * v["g2_ecom"] + w_cloud * g_cloud_roll
    unbooked = (v["eps27_m_cny"] - v["eps_1q27_cny"]) * fx  # HKD/share, 2Q–4Q FY27 only
    # each leg charged its own b: e-com g/ROE (ROE = E/B_open, solved), cloud
    # g/roic_cloud (sell-side leg-level marginal ROIC, constant; A14)
    b_cloud = w_cloud * g_cloud_roll / v["roic_cloud"]
    bps_open = {k: (v["bps_hkd"] + unbooked * b_cloud) / (1.0 - w_ecom * v["g2_ecom"] * unbooked / e_full[k])
                for k in SCENARIOS}
    roe = {k: e_full[k] / bps_open[k] for k in SCENARIOS}
    b1 = {k: w_ecom * v["g2_ecom"] / roe[k] + b_cloud for k in SCENARIOS}
    excess_cash = {k: ((1.0 - v["payout_3y"]) - b1[k]) * unbooked for k in SCENARIOS}  # B bucket, disclosure only
    # 稳态回报三段 (A22): e-com / ALA steady = own-cycle 23.9% (capped at the forward
    # ROE -> flat path); cloud steady = fallback 15% 有壁垒的重资产 (floored at r).
    rs_ecom = max(v["ss_return_ecom"], r)
    rs_cloud = max(v["ss_return_cloud"], r)
    pe_ecom = {k: path_pe(0.0, 0, v["g2_ecom"], roe[k], r, rs_ecom, v) for k in SCENARIOS}
    if candidate:
        pe_cloud = {k: path_pe(v["g1_cloud_cand"], int(v["n_cloud_cand"]), v["g2_cloud"], v["roic_cloud"], r,
                               rs_cloud, v) for k in SCENARIOS}
    else:
        pe_cloud = {k: path_pe(0.0, 0, v["g2_cloud"], v["roic_cloud"], r, rs_cloud, v) for k in SCENARIOS}

    # 时点对齐 (A22): the Gordon legs are the value at the opening of FY2028; V_opt is
    # discounted to FY2028 first, then by the same tau.
    f_tau = (1.0 + r) ** -v["tau_yr"]
    # V_opt (A19): one own realised ALA leg (snapshot lower bound) x own AEG
    # EBITA margin (shared rule, 拍值) x (1 - t), own ruler, timed + discounted.
    margin_ala = v["ebita_aeg_q_cny"] / v["rev_aeg_q_cny"]
    ala_np = v["rev_ala_q_cny"] * 4 * margin_ala * (1.0 - v["tax_rate"])
    pe_ala = path_pe(0.0, 0, v["g2_ecom"], roe["h"], v["r_ala"], max(v["ss_return_ecom"], v["r_ala"]), v)
    v_opt = (ala_np * pe_ala / (1.0 + v["r_ala"]) ** (v["t_opt"] - v["t_num"]) * fx / v["shares"]) * f_tau

    # 增长期资金缺口 (A22): Citi FY27E capex over the tau window (2Q-4Q FY27) minus OCF
    # (window consensus NI x 3y OCF/NI), only the share online by the end of FY2028
    # (20GW plan, linear from the base date to end-2032); deducted from net cash at the
    # parent share.  Parent share also scales the consolidated net cash.
    parent = v["equity_parent_cny"] / (v["equity_parent_cny"] + v["nci_cny"])
    ocf_window = (v["eps27_m_cny"] - v["eps_1q27_cny"]) * v["shares"] * v["ocf_ni_3y"]
    gap_full = max(0.0, v["capex_fy27_cny"] * v["tau_yr"] - ocf_window)
    online = (v["t_fy28_end"] - v["t_base"]) / (v["t_plan_end"] - v["t_base"])
    gap = gap_full * online
    cash_adj_ps = cash_ps - (v["net_cash_cny"] * fx * (1.0 - parent) + gap * parent * fx) / v["shares"]
    # window distributable profit: 0 while a gap exists (OCF already carries it)
    unbooked_op = (v["eps27_m_cny"] - v["eps_1q27_cny"] - nonop_ps * v["tau_yr"]) * fx

    legs: dict[str, dict[str, float]] = {}
    anchors: dict[str, float] = {}
    for k in SCENARIOS:
        pe_e = pe_ecom["m"] if flat_at_m else pe_ecom[k]
        pe_c = pe_cloud["m"] if flat_at_m else pe_cloud[k]
        d = v["d_m"] if flat_at_m else v[f"d_{k}"]
        window = 0.0 if gap > 0 else unbooked_op * (1.0 - b1[k]) * (1.0 + r) ** (-v["tau_yr"] / 2.0)
        legs[k] = {
            "ecom": e_ops[k] * w_ecom * pe_e * f_tau,
            "cloud": e_ops[k] * w_cloud * pe_c * f_tau,
            "window": window,
            "nav": nav_ps * (1 - d),
            "cash": cash_adj_ps,
        }
        anchors[k.upper()] = sum(legs[k].values())

    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    return {
        "nonop_ps": nonop_ps, "w_ecom": w_ecom, "w_cloud": w_cloud,
        "nav_ps": nav_ps, "cash_ps": cash_ps, "legs": legs, "V_opt": v_opt,
        "f_tau": f_tau, "parent": parent, "ocf_window": ocf_window, "gap_full": gap_full,
        "online": online, "gap": gap, "cash_adj_ps": cash_adj_ps, "unbooked_op": unbooked_op,
        "margin_ala": margin_ala, "ala_np": ala_np, "pe_ala": pe_ala,
        "e_full": e_full, "e_ops": e_ops, "roe": roe, "pe_ecom": pe_ecom, "pe_cloud": pe_cloud,
        "g_roll": g_roll, "unbooked": unbooked, "bps_open": bps_open, "b1": b1, "excess_cash": excess_cash,
        "blend": {k: w_ecom * pe_ecom[k] + w_cloud * pe_cloud[k] for k in SCENARIOS},
        "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
    }



def evaluate(v: dict[str, float]) -> dict:
    errors = check_missing(v, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    errors += check_r(v['r_perp'], 'r_perp', 4)
    errors += check_r(v['r_ala'], 'r_ala', 4)
    errors += check_g_cap(v['g2_ecom'], v['r_perp'], 'g2_ecom')
    errors += check_g_cap(v['g2_cloud'], v['r_perp'], 'g2_cloud')
    errors += check_g_cap(v['g2_ecom'], v['r_ala'], 'g2_ecom@r_ala')
    checks = [
        (0 < v['eq_method_q_cny'] < v['nonop_pretax_q_cny'], 'equity-method share'),
        (v['eps28_l_cny'] < v['eps28_m_cny'] < v['eps28_h_cny'], 'EPS order'),
        (v['ebita_cloud_q_cny'] > 0 and v['ebita_aeg_q_cny'] > 0, 'positive EBITA'),
        (all(v['r_perp'] - v[k] >= .02 - 1e-9 for k in ('g2_ecom', 'g2_cloud')), 'rate-growth gap'),
        (0 < v['eps_1q27_cny'] < v['eps27_m_cny'], 'booked EPS'),
        (all(.10 <= v[f'd_{k}'] <= .60 for k in SCENARIOS), 'NAV discount band'),
        (v['d_l'] > v['d_m'] > v['d_h'], 'NAV discount order'),
        (0 < v['tax_rate'] < .5, 'tax rate'),
        (not any(k == 'p' or k.startswith('p_') for k in v), 'probability input'),
    ]
    errors += [label for ok, label in checks if not ok]
    for field in ('n_cloud_cand', 't0_ret', 'y1_ret', 'y2_ret', 't_opt', 't_num'):
        value = v[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
            errors.append(f'{field} must be a finite whole year')
    if not errors and not (0 <= v['n_cloud_cand'] <= 100 and v['t0_ret'] <= v['y1_ret'] < v['y2_ret'] <= v['t0_ret'] + 100):
        errors.append('invalid candidate duration or return path')
    if not errors and not (v['roic_cloud'] > 0 and v['ss_return_cloud'] > 0 and v['t_base'] < v['t_plan_end']):
        errors.append('invalid return or capital plan timing')
    if errors:
        raise ValueError('; '.join(errors))
    c = compute(v)
    cand = compute(v, candidate=True)
    flat = compute(v, flat_at_m=True)
    checks = [
        (all(c['e_ops'][k] > 0 for k in SCENARIOS), 'positive operating EPS'),
        (all(c['pe_ecom'][k] > 0 and c['pe_cloud'][k] > 0 for k in SCENARIOS), 'positive multiples'),
        (all(0 < result['b1'][k] < 1 for result in (c, cand) for k in SCENARIOS), 'required retention'),
        (all(result['L'] < result['M'] < result['H'] for result in (c, cand, flat)), 'ordered bands'),
    ]
    errors += [label for ok, label in checks if not ok]
    if errors:
        raise ValueError('; '.join(errors))
    band = lambda result: {k: result[k] for k in 'LMH'}
    legs = {leg: {'unit': 'HKD_PER_SHARE', 'values': {t.upper(): c['legs'][t][leg] for t in SCENARIOS}}
            for leg in ('ecom', 'cloud', 'nav', 'cash', 'window')}
    rates = dict.fromkeys('LMH', v['r_perp'])
    returns = {t.upper(): c['roe'][t] for t in SCENARIOS}
    ecom_steady = {t.upper(): min(c['roe'][t], max(v['ss_return_ecom'], v['r_perp'])) for t in SCENARIOS}
    cloud_steady = min(v['roic_cloud'], max(v['ss_return_cloud'], v['r_perp']))
    flags = ['historical_candidate_funding_unverified', 'historical_ai_labs_overlap_unverified',
             'historical_cloud_ps_crosscheck_disagreement', 'historical_operating_bps_sensitivity_disagreement']
    if any(not v['pe_own_min'] <= c[k] / v['eps_ttm_gaap'] <= v['pe_own_max'] for k in 'LMH'):
        flags.append('historical_pe_outside_range')
    # The candidate's one-year 41% revenue-growth proxy and 16.6% return
    # imply negative distribution on the cloud leg. The old research did not
    # establish funding or dilution. Preserve the historical candidate while
    # disclosing that condition; it does not enter the base band.
    return {
        'ticker': '9988.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'framework_as_of': None,
        'historical_valuation_as_of': '2026-06-30', 'historical_framework_as_of': '2026-10-19',
        'units': {'price': 'HKD_PER_SHARE'},
        'anchors': band(c),
        'candidate': {'label': '美银FY2029云增长预测', 'anchors': band(cand)},
        'option': {'value': c['V_opt'], 'value_unit': 'HKD_PER_SHARE', 'weights': dict(OPTION_WEIGHTS),
                   'anchors': {tier: c[tier] + OPTION_WEIGHTS[tier] * c['V_opt'] for tier in 'LMH'}},
        'segments': legs,
        'key_parameters': {
            'ecom': {'discount_rate': {'unit': 'RATIO', 'values': rates},
                     'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', v['g2_ecom'])},
                     'forward_return': {'unit': 'RATIO', 'values': returns},
                     'steady_return': {'unit': 'RATIO', 'values': ecom_steady,
                                       'reference_value': v['ss_return_ecom']}},
            'cloud': {'discount_rate': {'unit': 'RATIO', 'values': rates},
                      'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', v['g2_cloud'])},
                      'forward_return': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', v['roic_cloud'])},
                      'steady_return': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', cloud_steady),
                                        'reference_value': v['ss_return_cloud']}},
        },
        'candidate_cloud_distribution_ratio': 1 - v['g1_cloud_cand'] / v['roic_cloud'],
        'review_flags': flags,
        'diagnostics': {'cash_gap_cny': c['gap'], 'cash_parent_share': c['parent'],
                        'investment_discounts': {t.upper(): v[f'd_{t}'] for t in SCENARIOS},
                        'operating_weights': {'ecom': c['w_ecom'], 'cloud': c['w_cloud']},
                        'roe': returns, 'model_retention': {t.upper(): c['b1'][t] for t in SCENARIOS}},
    }


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'option_weights': OPTION_WEIGHTS}, HISTORICAL_PARTIAL_FINGERPRINT)
    return result
