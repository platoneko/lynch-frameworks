#!/usr/bin/env python3
"""China Coal's historical coal-price and finite project valuation.

Original 2026 sources and scenarios are retained. Inputs are CNY / units as
named; output values are HKD/share. This is a draft, not a new forecast.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, g_cap, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = 'e5fbe324a46f81caeba73ab3351d1d02d2dc1d9179582862f3fd0bedc603a751'

INPUTS = {
    # 总股本 13,258,663,400 股（H 股 4,106,663,000）；LB static | as-of 2026-06-30
    'shares': 1.325866340e10,
    # 1 CNY = 1.1668 HKD；市场交叉汇率，见 A8 | as-of 2026-09-04
    'fx_cny_hkd': 1.1668,
    # 2026H1 归母净利（亿 CNY，IFRS）；公司中期业绩，见 A1 | as-of 2026H1
    'np_h1': 81.92,
    # 2026H1 营业利润（亿 CNY）= LB 143.75 亿 HKD ÷ 1.1465（期间均值汇率）；见 A6 | as-of 2026H1
    'op_h1': 125.38,
    # 自产商品煤年化销量（亿吨）= 2026H1 产量 6,195 万吨 ×2；见 A4 | as-of 2026H1
    'vol_yr': 1.2390,
    # **桥的基线**：2026H1 实测自产动力煤售价（元/吨，2026 中报，+13.3%）；NP(px_base) = 2 × np_h1；**不是 M**，只作 `neutral` 内坐标（A3‴） | as-of 2026H1
    'px_base': 494.0,
    # **L（煤价回到 2025H1）**自产动力煤售价（元/吨）= 494 ÷ 1.133；本票自身实测，见 A3 | as-of 2025H1
    'px_l': 436.0,
    # **M（中枢）**自产动力煤售价（元/吨）= `asp_fy19..asp_fy25` 七年实测均值（A3‴）；eval 复算 ±0.5 | as-of FY2019–25
    'px_m': 499.0,
    # **H（港口价升至 ≥2 家 2026 全年簇中位 800）**自产售价（元/吨）= 494 × (1 + 5.96% × 0.5)；见 A3/A5 | as-of 2026-09-08
    'px_h': 508.7,
    # FY2019 自产动力煤内销价（元/吨）；2020 年报销售表 | as-of FY2019
    'asp_fy19': 432,
    # FY2020 自产动力煤内销价；2020 年报销售表；**旧 regime 谷底**，压力坐标（A3″） | as-of FY2020
    'asp_fy20': 402,
    # FY2021 自产动力煤内销价；2022 年报销售表（经重述） | as-of FY2021
    'asp_fy21': 570,
    # FY2022 自产动力煤内销价；2022 年报销售表；**峰值**（1.25 × 中枢） | as-of FY2022
    'asp_fy22': 622,
    # FY2023 自产动力煤内销价；2024 年报销售表 | as-of FY2023
    'asp_fy23': 532,
    # FY2024 自产动力煤内销价；2024 年报销售表 | as-of FY2024
    'asp_fy24': 499,
    # FY2025 坐标 = 2025H1 实测动力煤价；全年动力煤价未在 2025 年报摘要单列（综合价 485 = 562 − 77，反推约 440–455），取 H1 作保守坐标（A3‴） | as-of 2025H1
    'asp_fy25': 436,
    # FY2019 IFRS 归母（亿 CNY）；2020 年报「境内外会计准则差异」表国际准则栏（CAS 56.29） | as-of FY2019
    'ni_ifrs_fy19': 61.99,
    # FY2020 IFRS 归母；同上（CAS 59.04） | as-of FY2020
    'ni_ifrs_fy20': 53.51,
    # FY2021 IFRS 归母（经重述）；2022 年报差异表（CAS 137.39） | as-of FY2021
    'ni_ifrs_fy21': 151.72,
    # FY2022 IFRS 归母；2022 年报差异表（CAS 182.41） | as-of FY2022
    'ni_ifrs_fy22': 197.19,
    # FY2023 IFRS 归母；2024 年报差异表（CAS 195.34）；**盈利峰值** | as-of FY2023
    'ni_ifrs_fy23': 201.84,
    # FY2024 IFRS 归母；2024 年报差异表（CAS 193.23） | as-of FY2024
    'ni_ifrs_fy24': 181.56,
    # 营业利润 → 归母的综合系数 = 81.92 ÷ 125.38；见 A6 | as-of 2026H1
    'conv': 0.653365,
    # 永续贴现率 = **篮 6 周期商品 / 小盘**篮子 r（整公司单篮，归篮理由见 A16）；历史 own-year PE 2019–25 落在 13% 坐标上 | as-of 2026-09-20
    'r_perp': 0.13,
    # 2023–25 已投入的超额 capex（亿 CNY）= 176 / 181 / 218 各减维持水平 ~100（2016–22 七年 capex 86–110 ≈ D&A）= 76 + 81 + 118；沉没，按 \(ROE_{proj}/r\) 计未来利润 PV **加回**（A9） | as-of FY2023–25
    'capex_spent': 275,
    # 2026–27 每年剩余超额 capex（亿 CNY）；假设 capex 维持 ~200 至投产，**待补**公司指引；这部分按 \((ROE_{proj}/r - 1)\) 罚（A9） | as-of 2026–27
    'capex_remain_yr': 100,
    # 剩余建设年数（2026、2027；煤化工 2026-12、苇子沟 2026 底、里必 2027 底投产）；满产利润 PV 点取 2027 末（t = 1.3 年） | as-of 2026-09-18
    'capex_remain_n': 2,
    # 项目增量 ROE；**待补**（化工分部资产 + 在建工程；补不齐先用 IFRS 全公司 10.2% 并标明），三坐标 8% / 10% / ≥13% 并列，底牌取 10% 居中 case；决定项目价值 +0.60 / +1.14 / +1.97 HKD/股（A9） | as-of 待核
    'roe_proj': 0.10,
    # 净现金（亿 CNY）= 现金及短投 782 − 有息负债 716；财务性桶，按面值披露 ≈ 0.58 HKD/股，**不进倍数** | as-of 2026-06-30
    'net_cash': 66,
    # 归母权益**亿 CNY** = bps ÷ fx_cny_hkd × shares；分档前瞻 ROE_x = NP_x ÷ equity = 7.11 / 10.21 / 10.69%（valuation-rules「永续增长口径」，A9） | as-of 2026-06-30
    'equity': 1643.8,
    # FY2025 全年每股派息 **CNY**（中期 0.1658 + 末期 0.217，2025 年报摘要；H 股实付 0.1819 + 0.2495 = 0.4314 HKD，见 `dps_fy25_hkd`）；派息率分子（A9，只作留存去向审计与撤回的留存分支对照） | as-of FY2025
    'dps_fy25': 0.382,
    # 同一笔 FY2025 派息的 H 股实付 **HKD**（中期 0.1819 + 末期 0.2495，按宣派日汇率）；只进 DDM 对照与股息率，**不进公式** | as-of FY2025
    'dps_fy25_hkd': 0.4314,
    # FY2025 IFRS 归母净利润**亿 CNY**（H 股公告；A 股 CAS 口径 178.84）；派息率分母 = ni ÷ shares = EPS 1.093（A9）；亦是七年实测均值的第 7 年 | as-of FY2025
    'ni_fy25': 144.97,
    # FY2026E 共识 EPS 均值 **CNY**（yfinance 1898.HK，2 家，区间 1.170–1.33）；当期 ÷ 中枢 的共识读数（A3‴），**不进公式** | as-of 2026-09-07
    'eps_fy26e': 1.250,
    # FY2027E 共识 EPS 下沿 **CNY**（3 家）；②-b 对账与 ② 直读对照带，**不进公式** | as-of 2026-09-07
    'eps_fy27e_low': 1.088,
    # FY2027E 共识 EPS 均值 **CNY**（3 家）；②-b：须落 [M, H] 且与中枢偏离 ≤ 20%（A1） | as-of 2026-09-07
    'eps_fy27e_mean': 1.283,
    # FY2027E 共识 EPS 上沿 **CNY**（3 家）；H 档 EPS 须 ≤ 此值（A3） | as-of 2026-09-07
    'eps_fy27e_high': 1.41,
    # **永续增长 = 0**（留存去向审计桶 D：留存去向是一次性建设窗口，按有限 NPV 单列，不进永续 g；煤价漂移走轴，A9）；cap = min(6%, r − 4%) = 6% | as-of 2026-09-20
    'g2': 0.0,
    # 证据区间下沿 = 0（g 不再是读数，区间退化为点；A9） | as-of 2026-09-20
    'g_evid_min': 0.0,
    # 证据区间上沿 = 0；\(g_2\) ±1pp 敏感区见 Outputs | as-of 2026-09-20
    'g_evid_max': 0.0,
    # 兖矿能源 1171.HK 全派息分支反解（fPE 8.16 / ROE 11.13%，`implied_g`）；不同世界（派 62%、利润 −37%/yr、共识向下），**只作交叉，不入公式**（A9） | as-of 2026-09-11
    'g_peer_yankuang': -0.0225,
    # ROE TTM（Longbridge compare）；只作质量记录（A12），倍数用前瞻 ROE_中枢，**不进公式** | as-of 2026-09-11
    'roe_ttm': 0.1139,
    # 2025H1 归母净利（亿 CNY）= 81.92 ÷ 1.118（中报「+11.8%」反推）；自身实测谷底年 × 1/r 的压力坐标，与 TTM 归母（ni_fy25 − np_h1_prev + np_h1）的构成项（A3″ / A3‴），**不进公式** | as-of 2025H1
    'np_h1_prev': 73.27,
    # 自身 5 年月频 PE 实测带下沿；**护栏，不入主公式**（A9） | as-of 2026-09-14
    'pe_own_min': 3.17,
    # 自身近 1 年日频 PE 实测带上沿（5 年月频 max 11.91）；护栏（A9） | as-of 2026-09-14
    'pe_own_max': 11.95,
    # 港口价 → 自产售价的传导率；**本框架最弱单点**，见 A5。仅用于推导 `px_h` / `px_h_cand`，**不进主公式** | as-of 判断值
    'pass_through': 0.5,
    # 秦皇岛 5500 港口价 2026H1 均价（元/吨）；高盛 2026-06-09。只进 `px_h` 推导 | as-of 2026H1
    'qhd_m': 755,
    # 秦皇岛 5500 **2026 全年预测簇中位**（美银 800 / 汇丰 791 / 高盛 813–850）；只进 `px_h` 推导（A3） | as-of 2026-09-08
    'qhd_h': 800,
    # 秦皇岛 5500 高盛 2026H2 预测（单家）；只进候选带 `px_h_cand` 推导（A3′） | as-of 2026-06-09
    'qhd_h_cand': 950,
    # 秦皇岛 5500 现货（元/吨）；美银 2026-09-08。**不进公式** | as-of 2026-09-04
    'qhd_spot': 941,
    # 每股净资产 HKD；LB static。资产地板参照（A10）；亦是 `equity` 的来源 | as-of 2026-06-30
    'bps': 14.4661,
}

# Original historical reasoning and financial evidence.
# - **属性 A — 港口现货价不是这家公司的售价，差距是 1.9 倍**（本票最大的口径风险）：
# - **属性 B — 长协是削峰也是填谷**：中长期长协约 **60%**，加月度长协约 **70%**。这意味着：① 现货暴涨时中煤的盈利弹性显著小于兖矿；② 现货暴跌时中煤的盈利也远比纯现货企业稳。本框架的三档售价跨度只有 **436 → 508.7 元/吨（−13% / +2%，以中枢 499 计）**，而同期港口价梯的跨度是 719 → 800（+6%）——**跨度被长协压缩了约一半**，这就是 `pass_through` = 0.5 的经济含义（A5）。
# - **属性 C — 周期位置：当期在中枢，不在峰值**（valuation-rules「周期票的中枢分子」）：自产动力煤实测售价 FY2019–25 = 432 / 402 / 570 / 622 / 532 / 499 / 436，七年均值 **499**；2026H1 的 494 = 0.99 × 中枢，2022 峰 622 = 1.25×、2020 谷 402 = 0.81×。盈利同样：IFRS 归母 FY2023 峰 201.84 亿 = 1.20 × 轴桥中枢 167.89，FY2025 谷 144.97 = 0.86×，2026H1 运行率 163.84 = **0.976×**，TTM 153.62 = 0.915×，FY26E / FY27E 共识 165.7 / 170.1 = 0.99 / 1.01×。**结论：低于 \(1/r\) 的倍数不能读成「当期是峰值」**——峰值分子（FY2023）在 flat 7.69× + 项目价值下的坐标是 14.80，落 `stretched`；倍数读的是篮 6 的 r 13%（\(1/r\) = 7.69×）。这一条决定本框架不用当期分子去冒充中枢，也不用一个正 g 去「解释」低倍数；两者都写成坐标（A3‴）。
# - **属性 D — 净现金与破净是真的，但它不构成 L 档的地板**：净债务 **−198.08 亿 HKD**（含长期借款以外项的口径）、现金及短期投资 1,098.20 亿 HKD；按现金及短投 782 − 有息负债 716 的口径净现金只有 ≈ **66 亿 CNY**（0.58 HKD/股），ROE 不是被现金稀释的。BPS 14.4661 HKD。资产地板（PB = 1.0）= **14.4661 HKD**，**高于 H 13.04**，落在带外（`stretched`）。按 `AGENTS.md`「地板允许兜底 \(L=\max(\text{scenario},\ \text{floor})\)」在此兜底会得到 \(L = 14.47 > H\)，整条盈利尺被账面覆盖——那是把「回到账面」当成实测过的坏，不是情景。**结论：本票的 `lynch_primary` 是 `cyclical`、盈利尺是主尺，资产地板只披露不 max()**——r 13% > ROE_中枢 10.21% 时 Gordon 合理 PB = ROE/r = 0.79，M = PB 0.86、H = PB 0.90 是代数结果：ROE 低于要求回报的公司，盈利尺理应低于账面（valuation-rules「③ 出带处理流程」地板条）。`asset_play` 次类记录的是「盈利尺整段落在账面之下、净现金另计」这一耦合（A10）。
# - **属性 E — A/H 折价是本票最大的单一未建模变量**：A 股 601898.SH 与 H 股是**同一家公司、同样的分红权、同一份报表**，H 股相对 A 股折价交易。本框架的锚点是**按 H 股口径**给出的（H 股价、H 股实付 HKD 分红、锚点 HKD；归母按 H 股公告的 IFRS 口径，FY2025 144.97 亿——A 股 CAS 口径同年为 178.84 亿，两准则差异来自专项储备处理，派息政策按两准则孰低 × ≥30%）；r 是篮 6 的仓库级值、\(g_2\) = 0（A9 / A16），**与港股同业倍数无关，A/H 折价既不在 \(g_2\) 里、也不另设折价因子**——折价是市场结构而非生意状态。归篮时它有一个读法：篮 6 的 13% = 煤炭 A 股 ~10%（同业 A 股倍数，A16 证据列）+ 港股 / 国企附加 ~3pp（A16）。但须知道：本票的 `stretched` 档若被突破，最可能的解释不是盈利超预期，而是**南向资金或红利税政策使折价收敛**——那属于市场事件，按 A2e-2b **MUST NOT** 放进倍数或 g2。
# - **属性 F — 化工腿是自产煤的下游，不是独立业务**：2026H1 化学收入占 13.4%、毛利 **21.91 亿（+69.2%）**，是增速最快的一块。但它的原料就是自产煤，内部转移定价使「煤炭腿毛利 + 化工腿毛利」在合并层面对煤价的敏感度低于两者简单相加。本框架把化工腿与采煤设备、金融腿一并**固定在 2026H1 年化水平**，三档不变——这是一个**已知的保守偏差**（化工品价格与煤价通常同向）；目标形态是 H 档命名 \(g_1\) 窗口（n ≤ 3，随产能投产；共识 2025A→28E 化工 CAGR 7%、国信 3%），不进永续 g、不进 r，待分部数据后落（A7）。
# - **倍数怎么来（\(1/r\)，篮 6，留存去向 = 有限建设窗口）**：倍数 = \(1/r\) = 7.69×（r 13%、\(g_2\) = 0），三档 flat，不取历史 PE 分位。分档前瞻 ROE = 归母 ÷ 权益 1,643.8 亿 CNY = 7.11 / **10.21** / 10.69%，ROE_中枢 低于 r 2.8pp——valuation-rules「反解分支」三域表的**病态区**：\(PE_M(g)\) 对 \(g\in[0,6\%]\) 单调下降（7.69 → 5.89×），倍数反解出的 \(g\) 不是读数。**留存去向审计**（A9）：派息率 34.9%、留存 65%——2022 留存去还债（有息债 842 → 716，财务性）、2023 起是煤化工（2026-12 投产）+ 新矿（苇子沟 2026 底、里必 2027 底）的**一次性建设窗口**（capex 176 / 181 / 218 亿 vs D&A ≈ 105–112）——不是「留存持续、项目源源不断」的稳态复利，**不进永续 g**：\(g_2\) = 0、主尺 \(1/r\)、项目价值按有限 NPV 单列（已建按 \(ROE_{proj}/r\) 加、未建按 \((ROE_{proj}/r-1)\) 罚）。永续留存分支 \(b\times ROE\) = 6.65% → 截顶 6% 在 r 13% 下是惩罚（5.89× → 6.06 / 8.71 / 9.11）——它假设 65% 留存永远按 10.2% 复投，与命名窗口矛盾，撤回只作对照。**`cyclical` flat**：三档同用 \(1/r\)——周期只在售价梯里算一次；分档 ROE 不进倍数（A2e-5）。**PE < 1/r 的读法顺序**：先算当期 ÷ 中枢（0.98，≤ 1.15，属性 C），排除「分子在高位」后才轮到 r 的读法（A16）。L 档不走「谷底档」回归段：该规则只适用于分子是自身实测谷底**年**的情形，而本票 L 是售价梯档（2025H1 价 × 2026H1 销量与成本），世界 = 低位 regime 持续，故取同一 flat 7.69×（A3″）；自身实测谷底年 × \(1/r\) 只作压力坐标。护栏 = 自身 5 年 PE 实测带 [3.17, 11.95]（A9），7.69× 在带内（5 年 p90 8.71 之下、近 1 年下沿 7.49 之上）。
# | A1 | **桥的基线用 2026H1 归母 81.92 亿 CNY ×2 年化（对应实测售价 494）；M 分子不是基线，是中枢（A3‴）**；售价梯是主尺骨架（用户定），共识只作 ② 的对账 | `active` | 公司 2026 年中期业绩：营收 731.36 亿（−1.8%）、归母 **81.92 亿**（+11.8%）、煤炭板块毛利 114.65 亿、化工板块毛利 21.91 亿（+69.2%）、整体毛利率 21.9%、经营现金流 98.64 亿（+28.6%）。**共识交叉（裁决顺序 ②-b，以中枢 M 检验）**：≥2 家且有区间的最远年份 = **FY2027E**（yfinance 1898.HK `+1y` 3 家：1.088 / 1.283 / 1.41 CNY；FY2026E 2 家 1.170 / 1.250 / 1.33），均值 1.283 CNY = 1.4970 HKD **落在 [M, H] = [1.4775, 1.5466] 内**、比中枢 EPS 高 **1.3%**（两条件都过）；FY27E/FY26E +2.6%——没有被抹掉的可见增长，也没有「共识停在峰值」（共识 1.25–1.28 CNY 低于 FY2022–24 实测 1.49 / 1.52 / 1.37）；LB 一致 NTM **1.479 HKD** vs 中枢 1.4775，差 +0.1%。② 直读对照带（FY27E 三点 × 7.69 + 项目价值 1.14）= **10.91 / 12.66 / 13.80**，与售价梯的差在 L（共识最低一家的隐含售价 470 元/吨 vs 本框架 2025H1 实测 436）；本框架保留售价梯（L 取实测低位 regime 更苛刻，A3″）。**分子上修独立于 r**：同花顺 FY27E 28 家均值 1.58 CNY 比本仓 3 家 1.283 高 19%，只作披露行（§3 Outputs），repo 级分子修正待批 | 全部锚点；② 对账 |
# | A2 | **业务地图以煤炭腿为轴，不做 SOTP**：煤占收入 74.2%、煤炭板块毛利 114.65 亿 vs 化工 21.91 亿。化工腿的原料是自产煤（内部转移定价），分腿倍数会把同一吨煤算两次 | `active` | LB business-segments 2026H1：煤 74.15% / 化学 13.35% / 其他 6.25% / 采煤设备 5.07% / 金融 1.18%。公司未披露分部净利与分部资产 | 不给分腿倍数；化工/煤机/金融腿三档固定（A7）；整公司单篮（A16） |
# | A3 | **售价三档 = 自产动力煤售价梯：L 436 / M 499（中枢）/ H 508.7 元/吨**；L 是公司自身 2025H1 实测值，M 是公司自身七年实测均值，H 由 ≥2 家港口价预测簇经传导率折算 | `active` | **M = 499 = 中枢**（A3‴）。**L = 436**：由 2026H1 的 494 ÷ 1.133 反推的 **2025H1 实测售价**——本票自己一年前印过的价，也是当前长协 regime（2022 年起基准价 675）内的实测低位；旧 regime 谷底 FY2020 402 只作压力坐标（A3″）。**H = 508.7**：秦皇岛 5500 从 2026H1 均价 **755** 升至 **2026 全年预测簇中位 800**（美银 800，2026-09-08，Wisburg 104615；汇丰 791，2026-08-15，100904；高盛 813–850 中值 831.5，2026-09-03，103810；三家中位 800）× 传导率 0.5 → 基线售价 +2.98% → 494 × 1.0298 = 508.7；H 档归母 175.74 亿 ≤ FY27E 共识上沿 1.41 CNY（186.95 亿）、≤ 自身 IFRS 峰值 FY2023 201.84 亿——是「港口价回到 2026 全年簇」这个可独立命名的世界，不含峰值。**旧版 H 用高盛单家 2026H2 950**（单家输入进底牌，A2e-7h 违反）→ 降为候选带（A3′）。三档同为 flat 7.69（A3″） | `px_l/m/h`、`px_base`、`qhd_h` |
# | A3′ | **候选带（QHD 2026H2 950·高盛单家）**：`qhd_h_cand = 950`（高盛 2026-06-09，91769）经同一传导率 0.5 → `px_h′` 557.8 → L′/M′/H′ = 9.05 / 12.51 / 15.73（L′、M′ 原样复制底牌；H′ = EPS 1.8963 × 7.69 + 项目价值 1.14）。**升级门槛**：≥2 家给出 2026H2 或 2027 秦皇岛 5500 预测 ≥900 → `qhd_h` 换为该簇中位并删除本行 | `active` | 高盛 91769；2026-09-04 现货 941 已接近该值，但现货单日价不是半年均价 | 候选带一行 |
# | A3″ | **L 档不是「谷底档」**：valuation-rules「谷底档」（`recovery_two_stage_pe`）只适用于 L 分子 = 自身实测谷底**年**的票；本票 L 是**售价梯档**——2025H1 售价 436 叠在 2026H1 销量 1.239 亿吨与单位成本 343 元/吨上，得归母 116.89 亿，**低于**自身实测谷底半年 2025H1 的年化归母 **146.54 亿**（73.27 × 2；中报「归母 +11.8%」反推）——它是「低位 regime 持续」的情景，不是回归段的起点，故取同一 flat 倍数 7.69×（`cyclical` flat，分档 ROE 不进倍数，A9）。**两个压力坐标**（各 + 项目价值 1.14）：① 自身实测谷底年 × \(1/r\) = 1.2896 HKD × 7.69 + 1.14 = **11.06**，落 `neutral` 下部——它高于 L 9.05，差额全部来自分子：L 把谷底价叠在今天更高的成本上（116.89 vs 146.54 亿）；② **旧 regime 谷底价 FY2020 402**（2022 年长协基准价改为 675 之前的实测底）叠在今日成本上 → 归母 89.36 亿 → **7.19**，落 `deep_discount`——跌破 L 要么是长协基准价被下调回旧 regime，要么是销量塌陷 | `active` | 中报 2026H1（归母 +11.8%、单位销售成本 343.22）；FY2025 单位销售成本 328.80（经营回顾原文）；2020 年报销售表（动力煤 402 元/吨） | `np_h1_prev`、`asp_fy20`（压力坐标）；L 档倍数 = flat |
# | A3‴ | **M 分子 = 中枢盈利（valuation-rules「周期票的中枢分子」）**：轴 M 价 = 自产动力煤 **FY2019–25 七年实测均值 499 元/吨**，桥出归母 **167.89 亿**（EPS 1.2662 CNY / 1.4775 HKD）；当期 ÷ 中枢 **0.976**（运行率）/ 0.915（TTM）/ 0.987（FY26E）/ 1.013（FY27E），**全部 ≤ 1.15 → 当期不是上侧坐标**，M 取中枢即取当期附近；2026H1 实测 494 是桥的基线（差 1%）、只作 `neutral` 内坐标 12.24 | `active` | **轴 M 价来源**（年报销售表，自产动力煤内销价）：FY2019 **432** / FY2020 **402**（2020 年报）、FY2021 **570** / FY2022 **622**（2022 年报）、FY2023 **532** / FY2024 **499**（2024 年报）、FY2025 **436**（2025 年报摘要未单列动力煤价，综合价 485 = 562 − 77；按综合价与焦煤价反推约 440–455；取 2025H1 实测 436 作保守坐标，对均值影响 ≤ 0.3%）；七年均值 499.0。**窗口**：七年含 2020 谷（0.81×）与 2022 峰（1.25×）；谷底→谷底六年（FY2020–25）均值 510、五年（FY2021–25）532——两者都更高，七年是最保守的完整周期窗口；2023–25（675 基准价 regime）三年均值 489 ≈ 494。**≥2 家长期 deck**：无（美银 / 汇丰 / 高盛只给 2026 全年），故用实测均值。**第二读数（互相印证）**：自身七年 IFRS 归母均值 = (61.99 + 53.51 + 151.72 + 197.19 + 201.84 + 181.56 + 144.97) / 7 = **141.83 亿**（EPS 1.2481 HKD；数字取自各年年报「境内外会计准则差异」表的国际准则栏，FY2025 取 H 股公告 144.97），轴桥 167.89 比它高 **18.4%**（<20%，不回对话）；差值可归因：FY2019–20 自产销量 1.02–1.11 亿吨 vs 今日年化 1.24、化工腿毛利当时不足今日一半——不是价格。**取轴桥的理由**：同量、同成本、同非煤腿，只让价动，才是「今天这家公司在中枢价上挣多少」；实测均值把两次结构变化（大海则投产、化工扩产）当成周期。实测均值坐标 10.74 留在表 2 作 `conservative` 上沿参照。**PE < 1/r 的读法**：比值 ≤ 1.15 → 不是分子在高位 → 转 r 读法（篮 6 的 \(1/r\) 7.69×，A9 / A16）。**当期 = 0.98 × 中枢**是本票 2026-09-15 第二次纠正的核心发现：把当期当 M 分子在数值上只差 1%，但没有做这道检验 | `active` | 同上；`eval/1898.HK.py` 复算七年均值（±0.5 元/吨）、轴桥 vs 实测均值差 ≤ 20%、四个比值并打印所属读法 | `asp_fy19..25`、`ni_ifrs_fy19..24`、`px_m`；每期年报滚动重算七年均值（下一次 FY2026 年报后窗口改 FY2020–26） |
# | A4 | **年化销量 1.239 亿吨 = 2026H1 自产商品煤产量 6,195 万吨 ×2，不采公司全年指引** | `active` | 公司 2026 年计划自产商品煤产销 **13,100 万吨以上**——H1 产量年化 12,390 万吨落在指引下方 5.4%，也低于 FY2025 实测 13,636 万吨。指引不得直接作 Inputs，只作印证。**方向**：本框架销量偏保守（中枢也按这个量算） | `vol_yr` |
# | A5 | **港口价 → 自产售价的传导率 = 0.5——本框架最弱的单点** | `active` | 支持 <1 的实证：**70% 长协**，长协按「基准价 + 浮动」定价；2026Q1 自产商品煤售价同比仅 **+0.8%**。支持 >0 的实证：2026H1 自产动力煤售价 **+13.3%**。**待补且方向存疑**：**2025H1 秦皇岛 5500 的半年均价未取到**，无法用两点直接实测传导率——0.5 是基于 70% 长协比例的判断值。在补上之前，L 档一律用公司自身的实测售价给出，**MUST NOT** 由港口价反推。**敏感性见 §3** | `pass_through`；**只影响 H 档与候选带** |
# | A6 | **`conv` = 0.653365（营业利润 → 归母，含所得税与少数股东），三档不变** | `active` | 2026H1：LB 营业利润 143.75 亿 HKD ÷ 1.1465 = **125.38 亿 CNY**（期间均值汇率口径）；归母 81.92 ÷ 125.38 = 0.653365。**已知偏差**：子公司少数股东比例未披露 | `conv` |
# | A7 | **化工、采煤设备、金融腿与费用在三档中固定在 2026H1 年化水平** | `active` | 2026H1 化工毛利 21.91 亿（**+69.2%**）、采煤设备收入 39.60 亿（−16.9%）、金融 9.25 亿（−20.8%）。**已知保守偏差**：煤化工产品价格与煤价通常同向；共识 2025A→28E 化工 CAGR 7%（国信 3%）→ 目标形态是 H 档命名 \(g_1\) 窗口（n ≤ 3，随产能投产），不进永续 g、不进 r；需分部数据，本版未落，H 仍 = 售价梯 H × \(1/r\) | 三档不变；偏差方向已标 |
# | A8 | **汇率统一用 1 CNY = 1.1668 HKD（市场交叉汇率，仓库统一口径）** | `active` | 见 `9988.HK.md` / `0189.HK.md` `fx_cny_hkd` 来源注（yfinance `HKD=X`/`CNY=X` 2026-09-04）。旧值 1.1465 为 Longbridge `exchange-rate` 自相矛盾值（HKD/USD 7.0001 越出联系汇率），系统性低 1.8%。LB segment / 归母口径反推的 1.1438 / 1.1378 为期间均值，不能校验现汇。**敏感性**：汇率每 ±1% ≈ 锚点 M ±0.13 HKD（项目价值同向） | `fx_cny_hkd`；三档同向平移 |
# | A9 | **PE flat 7.69 = \(1/r\)（篮 6 r 13%，\(g_2\) = 0）+ 项目价值单列；留存去向 = 有限建设窗口（valuation-rules「留存去向审计」桶 D），不进永续 g；同业簇逐家判域后可用 n = 0** | `active` | **留存三桶**：capex 98 / 176 / 181 / 218 亿（2022–25）vs D&A ≈ 105–112；2022 留存去还债（有息债 842 → 716，桶 A）；2023 起是煤化工（2026-12 投产）+ 新矿（苇子沟 2026 底、里必 2027 底）的**一次性建设窗口**（超额 capex 76 / 81 / 118 = 275 亿，项目有名有投产日，桶 D）——不是稳态复利，**不进永续 g**，煤炭腿 \(g_2\) = 0（商品腿 g 来自价格漂移，量增走 vol）。**项目价值（沉没成本口径）**：① 已建 \(K_{spent}\) = 2023–25 超出维持水平（≈ 100 亿 = 2016–22 七年 capex 86–110 ≈ D&A）的 **275 亿**，钱已变成厂房矿井，2027 年起的利润**不在中枢 EPS 里**（分子是 2026H1 运行率，项目未投产）→ 值 = 未来利润 PV = \(K_{spent}\times ROE_{proj}/r\) 折到满产（2027 末，t = 1.3 年）；② 2026–27 剩余 capex ≈ 100 亿/年（假设 capex 维持 ~200 至投产，**待补**公司指引），这才是真正的留存惩罚：\(K_{remain}\times ROE_{proj}/r - PV(capex)\)。项目 ROE 10%（居中）：+180 − 50 = **+130 亿 CNY ≈ +1.14 HKD/股**（已建 +1.59、未建 −0.44）；8%：+0.60；≥13%：+1.97。对已花 capex 按 \((ROE_{proj}/r-1)\) 罚是「当初该不该投」的问题，不是「今天值多少」，禁止形态 (iii)。**永续留存分支撤回**：派息率 34.9%（FY2025 DPS 0.382 CNY / IFRS EPS 1.093）、留存 65% → \(b\times ROE_M\) = 6.65% → 截顶 6%——这是 \(b\times ROE\) 恒等式在 ROE ≈ r 时的「免费 g」，r 抬到 13% 就变成惩罚（7.69 → 5.89×，6.06 / 8.71 / 9.11），且它假设 65% 留存永远按账面 ROE 复投，与命名窗口矛盾——只作对照带。**域**：分档前瞻 ROE = 归母 ÷ 权益 1,643.8 亿 = 7.11 / 10.21 / 10.69%，ROE_中枢 − r = −2.8pp → 病态区，\(PE_M(g)\) 对 g 不敏感，g 不是读数。**同业逐家判域**（2026-09-11 收，fPE = 收盘 ÷ LB NTM EPS，ROE = LB TTM）：**兖矿能源** 1171.HK 8.16× / ROE 11.13%——派 62%、归母 FY22→25 −37%/yr、共识 FY26E→27E 向下，是兖矿自己的世界 → 只作交叉（`g_peer_yankuang`）；**兖煤澳大利亚** 3668.HK 12.62× / ROE 3.30% → 峰形区不可达 → 剔除；**中国神华** 1088.HK 13.75× / 12.69% → 不可达 → 剔除；首钢资源（焦煤、NTM 单估计）剔除。可用簇 **n = 0**。**双算防线**：项目投产进 EPS 后（FY2027 年报），中枢分子重新桥，项目价值撤——否则利润与资产 PV 算两遍。**2028 触发**：capex 回不到 D&A 附近（> 1.3 × D&A）且无新命名项目 → 留存改按永续 \(b\) 罚（桶 E）。**护栏**：自身 5 年月频 PE 实测带 [3.17, 11.91]、近 1 年日频 [7.49, 11.95]——7.69× 在带内。**为什么不是 5 年中位 5.22**：5.22 及以下分位形成于 2021–2023 港股煤炭深度破净期（PB 0.4–0.6），历史分位只作护栏不作来源（valuation-rules「永续增长口径」） | `g2`、`r_perp`、`capex_spent`、`capex_remain_yr`、`capex_remain_n`、`roe_proj`、`equity`、`dps_fy25`、`dps_fy25_hkd`、`ni_fy25`、`g_evid_min/max`、`g_peer_yankuang`、`pe_own_*`；eval 复算项目价值、三坐标并列、撤回的留存分支对照带；每期年报重拉派息率、capex 与 ROE_中枢；**MUST NOT** 为迁就现价改 \(g_2\) 或项目 ROE |
# | A10 | **资产地板不兜底 L，只披露**：PB = 1.0 → **14.4661 HKD**，高于 H 13.04，在 [L, H] 外、落 `stretched` | `active` | 本票 `lynch_primary` 为 `cyclical`、盈利尺是主尺，L **MUST** 是情景（valuation-rules「L 是情景，不是地板」）：若按 \(L=\max(\text{scenario},\ \text{floor})\) 兜底会得到 \(L = 14.47 > H\)，整条盈利尺被账面覆盖，把「回到账面」当成实测过的坏。**它的落点**：r 13% > ROE_中枢 10.21%，Gordon 合理 PB = ROE/r = 0.79；M = PB 0.86、H = 0.90——「盈利尺低于账面」是 ROE < r 的代数结果，不是资产尺接管主尺的信号（valuation-rules「③ 出带处理流程」地板条）。eval 打印地板与三档 PB，不 max()、不断言 \(L < bps < H\)；地板若反而落回带内（ROE_中枢 越过 r），A10 的读法须回对话 | `scenario_L` 胜出；`conservative` 档读**盈利口径** |
# | A11 | **A/H 折价不设独立折价因子**：锚点按 H 股口径（H 股价、H 股实付分红、HKD）给出；r 是篮 6 的仓库级值（A16）、\(g_2\) = 0（A9），与港股同业倍数无关——折价既不在 \(g_2\) 里、也不另设因子 | `active` | A 股 601898.SH 与 H 股同公司、同报表、同分红权。**方向**：折价收敛是市场事件，**MUST NOT** 放进 g2 或倍数，只作 `stretched` 的解释材料；归篮层面它对应篮 6 的港股 / 国企附加 ~3pp（A16） | 不进公式；`stretched` 档的第一解释 |
# | A12 | **质量（ROIC/ROE）与现金流支持不额外折价**：ROE FY2022 14.89% → FY2025 **11.46%** → TTM 11.39%（Longbridge）。ROIC 代理 ≈ **11.2%** | `active` | LB 财报序列。**现金流质量**：2026H1 经营现金流 98.64 亿 CNY（+28.6%）、自由现金流 82.80 亿 HKD（2025H1 为 **−71.87 亿**）。倍数用前瞻 ROE_中枢 = 归母 ÷ 权益 = 10.21%（A9）；TTM 11.39% 只作质量记录 | 交叉 |
# | A13 | **PEG 显式未采用**：FY2026E 共识 EPS 1.250 CNY vs FY2025 IFRS 实际 1.093 = +14%，但只是谷底年回到中枢（FY27E 再 +2.6%），不是增长 | `active` | 投资逻辑是**现金回报与资产折价收敛**，不是增长 | 不进公式 |
# | A14 | **三档均不折现**：三档变的只是**当期煤价 regime**，分子用的销量、成本、费用、股本全部是 2026H1 的当期值，倍数也是永续口径；项目价值按 r 13% 单独折现（满产利润 PV 点 2027 末 1.3 年、剩余 capex 按 2026 / 2027 各折） | `active` | H 档引用的「2026 全年预测簇 800」在本框架里的角色是**该 regime 对应的价格水平**，不是「下半年才会发生的事」；M 档的中枢 499 同理是价格水平。**边界条款**：一旦把在建矿井或资产注入放进分子，就 MUST 同时折现相应年数并撤项目价值（A9 双算防线） | 全公式 |
# | A15 | **未采用卖方目标价**：高盛 **HK$17.5 / RMB 22.0**（买入，2026-09-03，Wisburg 103810）、LB 一致 **15.49 HKD**（9 家，2026-09-07，区间 12.001–18.497）。以中枢 EPS 1.4775 计分别隐含 **11.84× / 10.48×** 前瞻 PE——高盛 TP 隐含的 11.84× 接近本票近 1 年 PE 的最高值 11.95 | `active` | LB institution-rating 2026-09-07；Wisburg 103810。分歧点：卖方在**上调后的煤价**上叠加 10× 以上的倍数——病态区里 g 不抬倍数，越过 \(1/r\) 7.69× 就是在买更低的 r（11.84× ↔ 8.4%、10.48× ↔ 9.5%，即煤炭 A 股的篮 4 附近而非 H 股的篮 6）；本框架在 ≥2 家煤价簇上叠篮 6 的 \(1/r\)（A9 / A16） | 防目标价绑架锚点；LB 一致 15.49 与高盛 17.5 都落 `stretched`（H 13.04） |
# | A16 | **归篮：整公司 → 篮 6 周期商品 / 小盘（r 13%）**——盈利是自产煤价的函数（三档分子只让售价动，A3）；13% 是 **H 股中煤**的 r，不是煤炭的 r：煤炭 A 股同业在篮 4 附近（证据列），篮 6 = 煤炭 A 股 ~10% + 港股 / 国企附加 ~3pp；H 股历史 own-year PE 2019–25 = 6.0 / 4.8 / 3.1 / 3.7 / 3.6 / 5.9 / 7.8（E/P 13–32%），七年没给过 10×——**r = 13% 与自身历史一致，r = 10% 从未兑现**。CAPM 粗筛未做（β 对煤炭的行业风险失真，valuation-rules「r 篮子」已知张力），以 own-year E/P 反解替代。分腿归篮（煤炭 6 / 煤化工 6 备选 5 / 采煤设备 4 / 金融 5）是目标形态；化工分部资产与在建工程未披露 → 整公司单尺，r 取利润权重最大腿（煤炭）的篮子；化工腿占毛利 16%，若归篮 5 对 M 约 +3%（系统性偏差方向：本尺略偏保守） | `active` | valuation-rules「r 篮子」篮 6 判据（盈利是商品价函数）；煤化工同业（2026-09-18 yfinance）：宝丰 PE 11.0 / ROE 30.7%（g 3% → 隐含 11.2%，g 6% → 13.3%）、华鲁 12.4 / 12.5%（g 5% → 9.8%）——纯化工票隐含 10–13%，不低于煤炭；陕煤 12.1× / ROE 22%（g 3% → 10.2%）、神华 17.2× / 12.7%（g 2% → 7%）——煤炭 A 股在篮 4 附近，H 股附加 3pp 落篮 6 | `r_perp` 篮 6；分部数据到位后改分腿 |
# | A17 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」）读数——锚点不变**：① 超额现金未触发单列：净现金（现金及短投 782 − 有息负债 716）≈ 66 亿 CNY ÷ 归母权益 1,643.8 亿 ≈ 4% < 15%，利润与回报用合并口径；`conv` 已扣少数股东，归母份额不另调。② 时点对齐不适用：M 分子是七年实测售价中枢、L / H 是售价梯上的 regime 水平（A14），属「跨周期中枢 / 不随日历漂移」的边界；项目价值已按 r 折到估值时点，不再折。③ 稳态回报三段不适用：分子由售价梯桥出，属商品腿豁免；且 g2 = 0，回报不进倍数（1/r）。④ 一致性：g2 = 0 下各档回报不进永续段。⑤ 增长期资金缺口：在建煤化工与新矿已作有限期项目价值单列（A9），不重复扣。⑥ 无打折 k | active | 2026H1 中报；A9 / A14 | 无 |

YI = 1e8

BASE_NP_PARENT_YI = 163.84  # 2026H1 归母 81.92亿 CNY x 2
BASE_NP_TOL_YI = 0.5
EQUITY_TOL_YI = 1.0
PX_H_TOL = 1.0  # 元/吨
PX_MID_TOL = 0.5  # 元/吨: px_m must be the filed-series mean
MID_CROSS_TOL = 0.20  # the two mid-cycle readings must agree within this (valuation-rules「周期票的中枢分子」)
PEAK_RATIO = 1.15  # 当期 ÷ 中枢 above this makes the current print an upper-side coordinate
CONSENSUS_DEV_TOL = 0.20  # ②-b: M within this of the furthest-year consensus mean
TOL = 0.05
YEAR_END_OFFSET = 0.3  # years from the 2026-09 as-of to end-2026: capex and full-production PV points sit on year ends
ROE_PROJ_COORDS = (0.08, 0.10, 0.13)  # A9: ROE_proj is 待补; the deck takes the middle case
V1_R, V1_G2 = 0.10, 0.06  # the pre-basket reading, printed as 对照带
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"
TIERS = ("l", "m", "h")
ASP_YEARS = ("asp_fy19", "asp_fy20", "asp_fy21", "asp_fy22", "asp_fy23", "asp_fy24", "asp_fy25")
NI_IFRS_YEARS = ("ni_ifrs_fy19", "ni_ifrs_fy20", "ni_ifrs_fy21", "ni_ifrs_fy22", "ni_ifrs_fy23", "ni_ifrs_fy24")

REQUIRED = [
    "shares", "fx_cny_hkd", "np_h1", "op_h1", "vol_yr",
    "px_base", "px_l", "px_m", "px_h", *ASP_YEARS, *NI_IFRS_YEARS,
    "conv", "r_perp", "g2", "equity",
    "capex_spent", "capex_remain_yr", "capex_remain_n", "roe_proj", "net_cash",
    "dps_fy25", "dps_fy25_hkd", "ni_fy25", "eps_fy26e", "eps_fy27e_low", "eps_fy27e_mean", "eps_fy27e_high",
    "g_evid_min", "g_evid_max", "g_peer_yankuang",
    "np_h1_prev", "pe_own_min", "pe_own_max",
    "pass_through", "qhd_m", "qhd_h", "qhd_h_cand", "bps",
]


def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))

    r, fx = inp["r_perp"], inp["fx_cny_hkd"]

    # --- Step 1: the ASP ladder and its provenance -----------------------------
    errors += ladder("self-mined ASP", inp["px_l"], inp["px_m"], inp["px_h"])
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if not (1.05 < fx < 1.25):
        errors.append(f"fx_cny_hkd={fx} outside plausible band")
    if inp["np_h1_prev"] <= 0:
        errors.append("np_h1_prev must be positive (own trough year for the pressure coordinate)")
    bad = [k for k in (*ASP_YEARS, *NI_IFRS_YEARS) if inp[k] <= 0]
    if bad:
        errors.append(f"non-positive history inputs {bad}")

    # H is derived, not chosen: weld it to the port cluster and the pass-through.
    def px_from_port(qhd: float, pass_through: float = inp["pass_through"]) -> float:
        return inp["px_base"] * (1.0 + (qhd - inp["qhd_m"]) / inp["qhd_m"] * pass_through)

    px_h_expected = px_from_port(inp["qhd_h"])
    if abs(inp["px_h"] - px_h_expected) > PX_H_TOL:
        errors.append(f"px_h={inp['px_h']:g} vs derived {px_h_expected:.1f} — H must follow the port ladder")
    # M is derived too: the seven-year mean of the filed ASP series (A3‴).
    px_mid = sum(inp[k] for k in ASP_YEARS) / len(ASP_YEARS)
    if abs(inp["px_m"] - px_mid) > PX_MID_TOL:
        errors.append(f"px_m={inp['px_m']:g} vs FY2019-25 filed mean {px_mid:.1f} — M must be the mid-cycle price (A3‴)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 2: numerator per tier (CNY net profit -> HKD EPS) ----------------
    def net_profit_yi(px: float, vol: float = inp["vol_yr"]) -> float:
        dgp = (px - inp["px_base"]) * vol  # 元/吨 x 亿吨 = 亿 CNY
        return 2.0 * inp["np_h1"] + dgp * inp["conv"]

    def per_share_hkd(yi_cny: float) -> float:
        return yi_cny * YI / inp["shares"] * fx

    px = {"l": inp["px_l"], "m": inp["px_m"], "h": inp["px_h"], "c": px_from_port(inp["qhd_h_cand"]), "base": inp["px_base"]}
    npp = {t: net_profit_yi(v) for t, v in px.items()}
    eps_cny = {t: v * YI / inp["shares"] for t, v in npp.items()}
    eps = {t: v * fx for t, v in eps_cny.items()}
    if abs(npp["base"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(f"baseline closure broken: NP at px_base {npp['base']:.4f}亿CNY vs filed {BASE_NP_PARENT_YI}亿")

    # --- Step 3: mid-cycle check (校验 3a) --------------------------------------
    # Two mid-cycle readings must agree; the current print, TTM and consensus are
    # then placed against the mid-cycle numerator (valuation-rules「周期票的中枢分子」).
    ni_hist = [inp[k] for k in NI_IFRS_YEARS] + [inp["ni_fy25"]]
    ni_mid_realised = sum(ni_hist) / len(ni_hist)
    mid_gap = npp["m"] / ni_mid_realised - 1.0
    if abs(mid_gap) > MID_CROSS_TOL:
        errors.append(f"bridged mid-cycle NI {npp['m']:.2f}亿 vs realised seven-year IFRS mean {ni_mid_realised:.2f}亿: "
                      f"{mid_gap:+.1%} beyond {MID_CROSS_TOL:.0%} — BLOCKED, back to the conversation (A3‴)")
    ttm = inp["ni_fy25"] - inp["np_h1_prev"] + inp["np_h1"]
    current = {
        "run-rate 2026H1x2": 2.0 * inp["np_h1"],
        "TTM": ttm,
        "FY26E consensus": inp["eps_fy26e"] * inp["shares"] / YI,
        "FY27E consensus": inp["eps_fy27e_mean"] * inp["shares"] / YI,
    }
    ratios = {k: v / npp["m"] for k, v in current.items()}
    peak_numerator = max(ratios["run-rate 2026H1x2"], ratios["TTM"], ratios["FY26E consensus"]) > PEAK_RATIO
    # Whatever the case, M must be the mid-cycle numerator, never the current print.
    if abs(eps["m"] - eps["base"]) < 1e-9 and abs(inp["px_m"] - px_mid) > PX_MID_TOL:
        errors.append("EPS_M equals the 2026H1 print — the M numerator must be the mid-cycle EPS (A3‴)")
    # ②-b on the mid-cycle M: furthest >=2-house range year's mean inside [M, H], M within 20% of it.
    c_low, c_mean, c_high = (inp[k] * fx for k in ("eps_fy27e_low", "eps_fy27e_mean", "eps_fy27e_high"))
    if not (eps["m"] - 1e-9 <= c_mean <= eps["h"] + 1e-9):
        errors.append(f"②-b: FY27E consensus mean {c_mean:.4f} HKD outside [EPS_M {eps['m']:.4f}, EPS_H {eps['h']:.4f}] (A1)")
    if abs(c_mean / eps["m"] - 1.0) > CONSENSUS_DEV_TOL:
        errors.append(f"②-b: EPS_M {eps['m']:.4f} deviates {c_mean / eps['m'] - 1:+.1%} from FY27E consensus mean {c_mean:.4f} (A1)")
    if eps["h"] > c_high + 1e-9:
        errors.append(f"EPS_H {eps['h']:.4f} exceeds FY27E consensus high {c_high:.4f} HKD — H must stay a modelled upper edge (A3)")

    # --- Step 4: basket r, g2 = 0, project value (A9 / A16) --------------------
    baskets = {"r_perp": 6}
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules「r 篮子」, A16)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    equity_derived = inp["bps"] / fx * inp["shares"] / YI
    if abs(inp["equity"] - equity_derived) > EQUITY_TOL_YI:
        errors.append(f"equity {inp['equity']} vs bps ÷ fx × shares = {equity_derived:.1f} 亿CNY")
    roe = {t: npp[t] / inp["equity"] for t in npp}
    g2 = inp["g2"]
    errors += check_g_cap(g2, r, "g2")
    # Retention goes into a named build window (bucket D), priced as V_proj below;
    # a perpetual g here would count the same capex twice (A9).
    if abs(g2) > 1e-9:
        errors.append(f"g2={g2:+.4f} must be 0 — retention is a finite build window priced as V_proj, not a perpetual g (A9)")
    if abs(inp["g_evid_min"]) > 1e-9 or abs(inp["g_evid_max"]) > 1e-9:
        errors.append(f"g_evid interval [{inp['g_evid_min']}, {inp['g_evid_max']}] must collapse to 0 — g is not a reading here (A9)")
    if abs(inp["g_peer_yankuang"] - g2) < 1e-9:
        errors.append("g_peer_yankuang leaked into g2 — it is a different-world cross, not the source (A9)")
    n_remain = inp["capex_remain_n"]
    if n_remain <= 0 or abs(n_remain - round(n_remain)) > 1e-9:
        errors.append(f"capex_remain_n={n_remain} must be a positive integer number of build years (A9)")
    if not (0.0 < inp["roe_proj"] < 1.0):
        errors.append(f"roe_proj={inp['roe_proj']} outside (0,1) (A9)")
    if inp["capex_spent"] < 0 or inp["capex_remain_yr"] < 0:
        errors.append("capex_spent / capex_remain_yr must be non-negative (A9)")
    if errors:
        raise ValueError('; '.join(errors))
    n_remain = int(round(n_remain))

    def project_value_yi(roe_proj: float, r_: float = r, remain_yr: float = inp["capex_remain_yr"]) -> tuple[float, float, float]:
        """(total, built, unbuilt) project value in 亿 CNY at the sunk-cost reading (A9).

        Built capex is sunk and its post-window profit is outside the mid-cycle
        numerator, so it is added as a profit PV; only the remaining build-years'
        capex is penalised against its own profit PV.
        """
        t_full = YEAR_END_OFFSET + (n_remain - 1)
        pv_profit = lambda k: k * roe_proj / r_ / (1.0 + r_) ** t_full  # noqa: E731
        pv_capex = sum(remain_yr / (1.0 + r_) ** (YEAR_END_OFFSET + k) for k in range(n_remain))
        built = pv_profit(inp["capex_spent"])
        unbuilt = pv_profit(remain_yr * n_remain) - pv_capex
        return built + unbuilt, built, unbuilt

    v_proj_yi, v_built_yi, v_unbuilt_yi = project_value_yi(inp["roe_proj"])
    v_proj = per_share_hkd(v_proj_yi)

    # --- Step 5: the flat multiple (cyclical: every tier at 1/r) ---------------
    pe = {t: perpetual_pe(g2, roe["m"], r) for t in TIERS}
    if not (pe["l"] == pe["m"] == pe["h"]):
        errors.append(f"multiple not flat: {pe} — cyclical policy (A9)")
    if abs(pe["m"] - 1.0 / r) > 1e-9:
        errors.append(f"PE {pe['m']:.4f} != 1/r {1 / r:.4f} — g2 = 0 must give exactly 1/r")
    if not (inp["pe_own_min"] - 1e-9 <= pe["m"] <= inp["pe_own_max"] + 1e-9):
        errors.append(
            f"guardrail (③ 出带): generated PE {pe['m']:.2f} outside own band "
            f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — stop, back to the conversation"
        )
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 6: anchors, floor (disclosure), candidate band -------------------
    def band(pe_: float, v: float, vol: float = inp["vol_yr"]) -> tuple[float, float, float]:
        return tuple(per_share_hkd(net_profit_yi(px[t], vol)) * pe_ + v for t in TIERS)  # type: ignore[return-value]

    L, M, H = band(pe["m"], v_proj)
    if not (L < M < H):
        raise ValueError('; '.join(errors + [f'L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}']))
    A, B = cut_points(L, M, H)
    cand_h = eps['c'] * pe['m'] + v_proj
    if not L < M < cand_h:
        errors.append('candidate band not ordered')
    if errors:
        raise ValueError('; '.join(errors))
    realised_coord = per_share_hkd(ni_mid_realised) * pe['m'] + v_proj
    coords = {'FY2023 IFRS peak': inp['ni_ifrs_fy23'], 'FY2025 trough': inp['ni_fy25'],
              'TTM': ttm, '2026H1 基线': npp['base'], 'FY26E consensus': current['FY26E consensus'],
              'FY27E consensus': current['FY27E consensus']}
    payout_fy25 = inp['dps_fy25'] * inp['shares'] / (inp['ni_fy25'] * YI)
    t_full = YEAR_END_OFFSET + (n_remain - 1)
    d0 = inp['dps_fy25_hkd']
    trough = per_share_hkd(2 * inp['np_h1_prev']) * pe['m'] + v_proj
    old_regime = net_profit_yi(inp['asp_fy20'])
    old_regime_px = per_share_hkd(old_regime) * pe['m'] + v_proj
    per_10 = per_share_hkd(10 * inp['vol_yr'] * inp['conv']) * pe['m']
    bare = band(pe['m'], 0.)
    g_ret = min((1 - payout_fy25) * roe['m'], g_cap(r))
    pe_ret = perpetual_pe(g_ret, roe['m'], r)
    ret = band(pe_ret, 0.)
    pe_v1 = perpetual_pe(V1_G2, roe['m'], V1_R)
    v1 = band(pe_v1, 0.)
    guide = band(pe['m'], v_proj, vol=1.31)
    project_sensitivity = {str(x): {'project': project_value_yi(x),
                                    'band': band(pe['m'], per_share_hkd(project_value_yi(x)[0]))}
                           for x in ROE_PROJ_COORDS}
    capital_sensitivity = {str(rem): project_value_yi(inp['roe_proj'], remain_yr=rem) for rem in (0., 150.)}
    pass_through_sensitivity = {str(pt): [px_from_port(inp['qhd_h'], pt), px_from_port(inp['qhd_h_cand'], pt)]
                                for pt in (.3, .7)}
    sensitivity = {str(dg): band(perpetual_pe(g2+dg, roe['m'], r), v_proj) for dg in (.01, -.01)}
    def band_rf(dr):
        rr = r + dr
        return band(perpetual_pe(g2, roe['m'], rr), per_share_hkd(project_value_yi(inp['roe_proj'], r_=rr)[0]))
    result = {'ticker': '1898.HK', 'currency': 'HKD', 'valuation_as_of': None,
            'framework_as_of': None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of': '2026-10-16',
            'anchors': dict(zip('LMH', (L, M, H))), 'option': None,
            'candidate': {'label': '高盛煤价预测', 'anchors': {'L': L, 'M': M, 'H': cand_h}},
            'px_h_expected': px_h_expected, 'px_mid': px_mid, 'px': px, 'npp': npp,
            'eps_cny': eps_cny, 'eps': eps, 'ni_hist': ni_hist, 'ni_mid_realised': ni_mid_realised,
            'mid_gap': mid_gap, 'ttm': ttm, 'current': current, 'ratios': ratios,
            'peak_numerator': peak_numerator, 'c_low': c_low, 'c_mean': c_mean, 'c_high': c_high,
            'equity_derived': equity_derived, 'roe': roe, 'v_proj_yi': v_proj_yi,
            'v_built_yi': v_built_yi, 'v_unbuilt_yi': v_unbuilt_yi, 'v_proj': v_proj,
            'pe': pe, 'L': L, 'M': M, 'H': H, 'A': A, 'B': B, 'cand_h': cand_h,
            'realised_coord': realised_coord, 'coords': coords, 'payout_fy25': payout_fy25,
            't_full': t_full, 'd0': d0, 'trough': trough, 'old_regime': old_regime,
            'old_regime_px': old_regime_px, 'per_10': per_10, 'bare': bare, 'g_ret': g_ret,
            'pe_ret': pe_ret, 'ret': ret, 'pe_v1': pe_v1, 'v1': v1, 'guide': guide,
            'project_sensitivity': project_sensitivity, 'capital_sensitivity': capital_sensitivity,
            'pass_through_sensitivity': pass_through_sensitivity, 'sensitivity': sensitivity,
            }
    if rate_inputs is not None:
        def checked_band(dr):
            if r + dr <= g2:
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp': r}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'units_100m': YI, 'year_end_offset': YEAR_END_OFFSET,
         'project_return_coordinates': ROE_PROJ_COORDS, 'prior_rate': V1_R, 'prior_growth': V1_G2,
         'mid_cross_tolerance': MID_CROSS_TOL, 'consensus_tolerance': CONSENSUS_DEV_TOL}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'HKD_PER_SHARE'}
    result['segments'] = {
        'operating_business': {'unit': 'HKD_PER_SHARE',
                               'values': {t.upper(): result['anchors'][t.upper()] - result['v_proj'] for t in TIERS}},
        'projects': {'unit': 'HKD_PER_SHARE', 'values': dict.fromkeys('LMH', result['v_proj'])},
    }
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['r_perp'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['g2'])},
        'forward_return': {'unit': 'RATIO', 'values': {t.upper(): result['roe'][t] for t in TIERS}},
        'steady_return': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', None)},
        'project_return': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['roe_proj'])},
    }
    result['review_flags'] = ['historical_project_return_assumed_and_capital_unverified',
                              'historical_coal_chemical_segment_not_separately_modelled']
    return result
