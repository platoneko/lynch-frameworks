#!/usr/bin/env python3
"""Dongfang Electric's historical incumbent and gas-turbine option valuation.

The 2026 inputs, consensus, capacity expenditure and southbound axis remain
as researched. Values are HKD/share; no new forecast or publication is implied.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, payout, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis', 'rf_report'),
                'axes': {'southbound': 'southbound_repricing'}}
HISTORICAL_PARTIAL_FINGERPRINT = '521c9a65574f36da7dd9983960f438071383cce15d030a97abb4fafb931dd249'

# Original inputs, their source, purpose and as-of.
INPUTS = {
    # 总股本（A+H）；2025 年报「股份总数」 | as-of 2025-12-31
    'shares': 3.458360326e9,
    # 每股归母净资产 CNY = `equity`/`shares` | as-of 2026-09-30
    'bps': 13.61,
    # HKD→CNY；yfinance `HKDCNY=X` | as-of 2026-11-01
    'fx_hkdcny': 0.8468,
    # 篮 4 龙头制造 r = 10%（A20：电力设备制造龙头（国企），三腿同篮；无备选）；零增长 = 10× | as-of 2026-09-20
    'r_perp': 0.10,
    # 归属于母公司所有者权益合计；**三季报原文** | as-of 2026-09-30
    'equity': 470.54,
    # **L** 归母 = FY2025 实测全年（最近完整年，稳态分子，A1）；FY2024 谷底 29.22 降为 `deep_discount` 压力坐标（`ni_trough_fy2024`） | as-of FY2025
    'ni_l': 38.31,
    # **M** 归母 = FY2028E 卖方共识均值（亿 CNY；东方财富 F10「机构预测明细」半年报后 4 家：长江 09-25 67.08 / 华鑫 09-24 73.38 / 东吴 11-03 68.10 / 光大 08-26 64.34；2026-11-05 复核仅东吴 FY2028 已刷新，华鑫上沿仍是财报前旧预测），折回 1.25 年（A1 / A22） | as-of 2026-11-05
    'ni_m': 68.225,
    # TTM 归母（Q4'25~Q3'26 四个已实现季度）；旧 M 分子，现只作 TTM 读数、卖方 TP / 账面反解与对账门中性带倍数，**不进公式** | as-of 2026-09-30
    'ni_ttm': 47.04,
    # **H** 归母 = FY2028E 共识上沿（华鑫 09-24；2026-11-05 复核仅东吴 FY2028 已刷新，华鑫上沿仍是财报前旧预测），折回 1.25 年（A1 / A22）；旧 H 2026H1×2 = 54.26 只作坐标 | as-of 2026-11-05
    'ni_h': 73.38,
    # FY2028E 共识下沿（光大 08-26）；**只作档内坐标，不进底牌**（L 用 FY2025 实测消化年） | as-of 2026-10-04
    'ni_cons_fy28_lo': 64.34,
    # 时点对齐年数 τ：估值基准日（三季报资产负债表日 2026-09-30）→ M / H 分子年初 2028-01-01（折现率同 `r_perp`）；L 为实测稳态年，不折；期权同折（A22） | as-of 2026-09-30
    'tau': 1.25,
    # FY2026E EPS 共识均值（东方财富 F10 半年报后 5 家，剔除财通 06-03；仅东吴、中金已在 Q3 后更新，其他 3 家待刷新）；只用于窗口可分配利润（A22） | as-of 2026-11-05
    'eps_fy26_m': 1.352,
    # FY2026E EPS 共识上沿（华鑫 09-24，同上 5 家）；H 档窗口（A22） | as-of 2026-11-05
    'eps_fy26_h': 1.47,
    # 2026 前三季归母净利（亿 CNY，三季报）；从 FY2026E 里扣掉已入账部分（A22） | as-of 2026-09-30
    'ni_9m_26': 38.387,
    # 自身五年（FY2021–25）归母均值 = (22.89 + 28.58 + 35.50 + 29.22 + 38.31) ÷ 5；周期位置披露（需求周期型，中枢规则不适用），**不进公式** | as-of FY2025
    'ni_mid5': 30.90,
    # FY2027E 共识下沿（中金 11-02；东方财富半年报后 5 家）；**交叉，不进公式** | as-of 2026-11-05
    'ni_cons_fy27_lo': 53.30,
    # FY2027E 共识均值（5 家各自最新：长江 56.74（09-25）/ 华鑫 61.61（09-24）/ 东吴 56.02（11-03）/ 中金 53.30（11-02）/ 光大 55.54（08-26））；交叉 + 对账门中性带 FY+1 读数 | as-of 2026-11-05
    'ni_cons_fy27_mean': 56.642,
    # FY2027E 共识上沿（华鑫）；交叉 | as-of 2026-11-05
    'ni_cons_fy27_hi': 61.61,
    # **L** 腿 A 毛利 = FY2025 全年（煤电 + 水电 + 核能 + 风电）；2025 年报原文附注（与 `gp_a_m` 的 FY2025 项同源） | as-of FY2025
    'gp_a_l': 74.22,
    # **L** 腿 B 毛利 = FY2025 全年（制造服务 + 新兴产业） | as-of FY2025
    'gp_b_l': 52.66,
    # **L** 腿 C 毛利 = FY2025 全年气电 | as-of FY2025
    'gp_c_l': 6.76,
    # **M** 腿 A 毛利 = FY2025 74.22 − H1'25 35.76 ＋ H1'26 38.47 | as-of TTM
    'gp_a_m': 76.94,
    # **M** 腿 B 毛利 = FY2025 52.66 − H1'25 24.29 ＋ H1'26 23.66 | as-of TTM
    'gp_b_m': 52.03,
    # **M** 腿 C 毛利 = FY2025 6.76 − H1'25 3.25 ＋ H1'26 2.98 | as-of TTM
    'gp_c_m': 6.48,
    # **H** 腿 A 毛利 = 煤电 29.75＋水电 2.66＋核能 4.12＋风电 1.94；中报原文 | as-of 2026H1
    'gp_a_h': 38.47,
    # **H** 腿 B 毛利 = 制造服务 20.46＋新兴产业 3.20 | as-of 2026H1
    'gp_b_h': 23.66,
    # **H** 腿 C 毛利 = 气电（34.81 − 31.84） | as-of 2026H1
    'gp_c_h': 2.98,
    # 持三菱重工东方燃气轮机（广州）比例；权益法（A14） | as-of 2026-06-30
    'jv_stake': 0.49,
    # **L** 该合资公司净利 亿 CNY = FY2025；2025 年报附注（与 `ni_l` 同窗口） | as-of FY2025
    'jv_ni_l': 1.836,
    # **M** = TTM（FY2025 1.836 − H1'25 0.5235 ＋ H1'26 1.263） | as-of TTM
    'jv_ni_m': 2.5755,
    # **H** = 2026H1 1.263 × 2（与 `ni_h` 同窗口） | as-of 2026H1
    'jv_ni_h': 2.526,
    # **L** 腿 A 永续 g：煤电洪峰后长坡下行（A5）；三档共用（`cyclical` flat，裁决顺序 ⑤）；**无同业锚**（核准序列自定）；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2025Q3 核准序列
    'g2_a_l': -0.04,
    # **M** 腿 A 永续 g；**无同业锚**；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2025Q3 核准序列
    'g2_a_m': -0.04,
    # **H** 腿 A 永续 g；三档共用；分档变体（−6% / −2%）只作敏感性（A5）；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2025Q3 核准序列
    'g2_a_h': -0.04,
    # **L** 腿 B 永续 g：装机基数扩大带动 after-market（A6）；三档共用；**无同业锚**；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2026-06-30 中报
    'g2_b_l': 0.03,
    # **M** 腿 B 永续 g；**无同业锚**；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2026-06-30 中报
    'g2_b_m': 0.03,
    # **H** 腿 B 永续 g；三档共用；分档变体（0 / +5%）只作敏感性；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2026-06-30 中报
    'g2_b_h': 0.03,
    # **L** 腿 C（**存量**燃机）永续 g（A7）：引进型 + LTSA 三年无趋势；三档共用；**无同业锚**；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2026-06-30 中报
    'g2_c_l': 0.00,
    # **M** 腿 C 永续 g；**无同业锚**；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2026-06-30 中报
    'g2_c_m': 0.00,
    # **H** 腿 C 永续 g；三档共用；**成长部分已剥离到腿 D**；篮 4 cap 6% 不触及，病态区取实测 / 政策来源（A20） | as-of 2026-06-30 中报
    'g2_c_h': 0.00,
    # **L** 腿 D 自主 G50 台数 = 期权不兑现（A16） | as-of 对话锁定
    'g50_units_l': 0,
    # **M** = 当前产能下沿（10–12 台/年） | as-of 2026
    'g50_units_m': 12,
    # **H** = UBS 转述管理层「2027 年底 25 台 G50」（**待补**） | as-of 2026-05
    'g50_units_h': 25,
    # 单价 亿元/台，三档不变；花旗 2026-03-04＝$596/kW，对 GEV 2027 报价 ~$600/kW ✓（A16） | as-of 2026-03
    'g50_price': 2.0,
    # **L** 毛利率（腿归零） | as-of —
    'g50_gm_l': 0.00,
    # **M** 毛利率 = 东吴口径下限 >30%（**待补**） | as-of 2026-02
    'g50_gm_m': 0.30,
    # **H** 毛利率 = 花旗口径下限 40–50%（**待补**） | as-of 2026-03
    'g50_gm_h': 0.40,
    # 毛利→归母转化率 = 2026H1 窗口 TTM 实测 46.35/135.45（与腿权重同期；三季报无分部，不滚），同 A3 | as-of TTM
    'g50_k': 0.3422,
    # **L** 腿 D 永续 g（期权腿，不进底牌；仍受 6% 上限） | as-of —
    'g50_g_l': 0.00,
    # **M** 腿 D 永续 g：产能建完即止；**无同业锚** | as-of 2026-08-28 首台发运
    'g50_g_m': 0.00,
    # **H** 腿 D 永续 g = 所在腿（腿 C 燃机）\(g_2\) 0%（valuation-rules「未建模期权」2026-10-03：按本票所在腿的尺估值，兑现后的继续增长只能进份数 \(k\)，不抬单份倍数；旧值 +5% 无同业锚，已撤） | as-of 2026-10-03
    'g50_g_h': 0.00,
    # **L** 折现年数（腿归零） | as-of —
    'g50_lag_l': 0,
    # **M** = 12 台≈当前产能，盈利自 FY2027 起，与 `perpetual_pe` 隐含时点一致（A17） | as-of —
    'g50_lag_m': 0,
    # **H** = 25 台为 2027 年底产能，FY2028 首个完整运行年，晚一期（A17） | as-of —
    'g50_lag_h': 1,
    # 腿 D 折现率 = 权益成本，与 `r_perp` 同源（A17 / A20），同为 10% | as-of 2026-09-20
    'r_disc': 0.10,
    # USD→CNY；用于腿 D 单价的 $/kW 护栏（校验 5c） | as-of 2026-11-01
    'usdcny': 6.654,
    # G50 单机功率 MW；$/kW 护栏用 | as-of 公司口径
    'g50_mw': 50,
    # 单价护栏下沿 $/kW（全球重型机报价簇） | as-of 2026
    'g50_usdkw_lo': 400,
    # 单价护栏上沿 $/kW；GEV 2027 报价 ~600 | as-of 2026
    'g50_usdkw_hi': 900,
    # G200 单机功率 MW；单价 = `g50_price × g200_mw / g50_mw`（A18） | as-of 公司口径
    'g200_mw': 200,
    # **L** G200 台数 = 不兑现 | as-of —
    'g200_units_l': 0,
    # **M** = 2027 年下线，当期不计价 | as-of —
    'g200_units_m': 0,
    # **H** = UBS 转述「3 台 G200」，与 G50 的 25 台同一句（A18，**待补**） | as-of 2026-05
    'g200_units_h': 3,
    # 自主燃机核心产能提升建设项目（一期）总投资 亿 CNY = 73,900 万元；董事会十一届十九次会议决议公告（2026-011，2026-04-30）第（十）项；目标年产 30 台、2027-12 建成（界面新闻 2026-09-07，非公司口径）。H 档 25 台 G50 + 3 台 G200 的产能来源（A16） | as-of 2026-04-29
    'cap_k': 7.39,
    # 一期已投 亿 CNY：2026 中报（2026-08-26）在建工程附注「重要在建工程」未列本项（所列最小项 0.151 亿）→ 期末余额 < 0.151 亿，按 0 计（偏差 ≤ 0.005 HKD/股） | as-of 2026-06-30
    'cap_spent': 0,
    # 本票在一期中的权益：实施主体东方汽轮机为全资子公司（同一公告） | as-of 2026-04-29
    'cap_eq': 1.0,
    # 已建成的自主燃机年产能（台）：当前 10–12 台/年（东吴 / 中信建投转述；2025 年报募投注释「已建成国内领先的自主燃机研发、生产、服务基地」）；G50 + G200 台数 ≤ 此值的档不扣未投资本（M 档） | as-of 2026
    'cap_now': 12,
    # 其余燃机相关在建工程未投 亿 CNY（**交叉，不扣**）：2026 中报「重要在建工程」——全重实验室大功率燃气轮机燃烧器试验平台 预算 3.314 / 累计 20.85% → 2.62；燃机无机喷涂与热喷涂数字化产线 2.197 / 12.98% → 1.91；全重实验室燃机喷涂产线 0.809 / 19.70% → 0.65（A16） | as-of 2026-06-30
    'gt_other_k': 5.18,
    # H 股 own-year PE 实测低点（2020）；**护栏，非主尺**（A8） | as-of 2019–2025
    'pe_own_lo': 7.04,
    # H 股 own-year PE 实测高点（2025） | as-of 2019–2025
    'pe_own_hi': 11.97,
    # H 股 own-year PE 中位；交叉对照 | as-of 2019–2025
    'pe_own_mid': 9.85,
    # A 股 own-year PE 中位（带 [15.56, 24.14]）；交叉对照 | as-of 2019–2025
    'pe_own_a_mid': 16.78,
    # 净债务的相反数 = 货币资金 + 交易性金融资产 − 短期借款 − 一年内到期的非流动负债 − 长期借款；三季报 BS | as-of 2026-09-30
    'net_cash': 205.97,
    # FY2024 实测谷底归母（风电亏损年，ROE 7.71% < r）；谷底 × 1/r = `deep_discount` 压力坐标，**不入主公式**（A1） | as-of FY2024
    'ni_trough_fy2024': 29.22,
    # 实付派息率 ≈ FY2025 H 股末期息 0.607 HKD（2026-06-25 派，yfinance；按派息日汇率）× 0.8552 ÷ FY2025 EPS 1.108（现股本口径）；对账门 ③，**不进公式** | as-of 2026-06-25
    'payout_obs': 0.469,
    # H 股自身 5 年月频 PB 低点（2023-12，Longbridge `valuation --history --indicator pb --range 5`）；对账门 ⑥，**不进公式** | as-of 2026-10-04
    'pb_own_min': 0.49,
    # 上一版 M（2026-11-01 版，基准日 2026-09-30）；对账门 ① | as-of 2026-11-01
    'm_prev': 21.00,
    # 机构一致目标价 HKD；Longbridge（A12，**待解释**） | as-of 2026-10-26
    'tp_street': 30.96,
    # 腿 C 毛利权重守卫上限：升破则主类可议（属性 F） | as-of 对话锁定
    'leg_c_weight_cap': 0.10,
}

# Original historical reasoning and financial evidence.
# - **业务地图摘要**：分部启发式命中 **6/7**——① 三个报告分部，能源装备制造 76.2% 收入、制造服务 16.2%，产品级还有五个子块；② 驱动因子完全不同（煤电＝火电核准周期、气电＝AIDC＋燃机国产化、风电＝招标价格战、核能＝核准节奏、制造服务＝存量机组 after-market、新兴产业＝补贴）；③ 林奇属性按块不同（煤电 `cyclical`、气电 `fast_grower`、制造服务 `stalwart`、风电近盈亏平衡）；④ 卖方已在单独讨论燃机腿；⑤ 风电毛利率 3.67%、FY2024 曾为 **−2.23%**（毛利 −2.74 亿），属投资期/亏损腿；⑥ capex 与叙事集中在一块（自主燃机核心产能提升项目 2026H1 正式开工）。**未命中的一条最关键**：公司**只披露到分产品毛利，不披露分产品净利**——报告分部里的「营业利润」实际等于对外毛利，往下的 33.15 亿期间费用没有分部口径。故分腿只能到毛利层，归母按毛利权重分配（A3，本框架最大的口径妥协）。
# - **属性 A — 燃机腿的份额在两种口径下都没有变大，这是本票不能按燃机定价的全部理由**：
# - **属性 B — 气电的增长是负毛利增长**：收入 2025H1 27.84 亿 → 2026H1 **34.81 亿（+25.0%）**，毛利 3.25 亿 → **2.98 亿（−8.4%）**，毛利率 11.67% → **8.55%（−3.13pp）**。拉长看更清楚：气电毛利 FY2024 **5.18 亿** → FY2025 **6.76 亿** → TTM **6.48 亿**——**三年在 5–7 亿之间平移，没有趋势**。同期收入 71.10 → 56.28 → 约 63 亿，也没有趋势。**「燃机放量」在合并报表里还没有发生。**
# - **属性 C — 气电腿最肥的利润池在表外，8.55% 系统性低估了这条腿**：**三菱重工东方燃气轮机（广州）有限公司**是 DEC 持股 **49%** 的**联营企业、权益法核算**，其利润落在**投资收益**行，**完全不进气电分部的收入与成本**。中报／年报附注「重要联营企业的主要财务信息」原文：
# - **属性 C′ — 自主 G50 的经济性目前 100% 建立在互相打架的卖方估计上**：单台售价与毛利率有两个冲突口径——花旗 2026-03-04 称 **2 亿元/台、毛利率 40–50%**（加拿大 20 台 / 40 亿），东吴 2026-02-24 称 **约 3 亿元/台、毛利率 >30%**（哈萨克斯坦联合循环）。**公司零确认**：2026-01-01~2026-10-30 沪市公告（A+H 同步义务下港交所亦同）**无任何相关重大合同公告**；2026 三季报亦无 G50 台数/单价更新。2026-10 行业新闻「全球燃机产能紧张、海外排产延至 2031」只作背景，不进模型。产能方面，公司口径有两处：2026 中报 MD&A「**自主燃机核心产能提升项目正式开工**」，以及董事会十一届十九次会议决议公告（2026-011，2026-04-30）第（十）项「同意东方汽轮机开展自主燃机核心产能提升建设项目（一期），项目总投资 **73,900 万元**」（2026-10-04 补正：此前写「一期 7.39 亿无出处」有误）；「2027-12 建成、目标年产 30 台」仍只见于媒体（界面新闻 2026-09-07），公司公告未载产能与时间表。**在建工程附注里的燃机热端资本开支**：2025 年报「G50 中心燃机高温透平叶片精铸产线」预算 **8,087 万元、进度 13.15%**（当年另有 4,250 万转固）——注意它挂在 **G50（自主机型）** 名下，**不支持「正在把三菱合作机型热端本地化从而抬升其毛利」的推论**。合理读法是自主线自建热端、合作线继续依赖三菱体系，**两条腿的成本结构短期不会收敛**。
# - **属性 C″ — 与多头叙事相反的当期证据必须并列**：2026H1 气电毛利率同比 **−3.13pp**，方向与「高毛利 G50 放量」**相反**，说明本期交付结构仍以合作型／低毛利订单为主，**G50 的收入贡献尚未形成拐点**。引进型存量盘则确认很大：「东方–三菱」国内外累计订单**超 160 台**、已投运百余台（东吴引公司公众号，截至 2025-10）。**这是本框架最敏感的单点，A4 与 A14 同时挂 `待补`。**
# - **属性 D — 真正的利润引擎是煤电，而煤电正走在交付高峰上**：煤电毛利 FY2024 33.26 亿 → FY2025 **50.68 亿（+52.4%）** → 2026H1 **29.75 亿**，毛利率 16.42% → 20.69% → 19.89%。驱动它的是核准洪峰：全国煤电核准 2021 约 18 GW → **2022 年 90.72 GW** → 2023 上半年即 50.4 GW → **2024 年 63.99 GW** → 2025 前三季 **41.77 GW**。设备交付滞后核准 2–3 年，故 2022–23 的洪峰对应 **2025–27 的交付高峰**，之后是长坡下行。**这既是 `cyclical` 主类的依据，也是腿 A 给负永续增长的依据**（A5）。**2026 前三季的交付量已见顶的早期证据**：汽轮发电机组产量 4,411.07 万千瓦（去年同期 4,517.70，−2.4%）、风力发电机组 433.41 万千瓦（去年同期 1,185.15，**−63.4%**）、水轮发电机组 572.64 万千瓦（+29.3%）；收入持平（营业总收入 +1.22%）而毛利率 17.24%（+1.86pp），利润靠毛利结构而不是靠交付量增长。三季报无分部，煤电毛利率待年报。
# - **属性 E — \(ROE \approx r\)，倍数被钉在 10× 附近，这是本票的结构性事实**：ROE(TTM) = 47.04 / 470.54 = **10.00%**，与全仓统一的 \(r = 10\%\) 几乎重合。按 `AGENTS.md`「永续增长口径」，此时**增长不创造价值**，倍数钉在 \(1/r\) 附近，且**从价格反解 \(g\) 不稳定**——`eval/lib/gordon.py` 的 `implied_g` 对卖方目标价 30.96（TTM 19.27×）返回 `well_conditioned=False`（反解出 +10.00%，紧贴 ROE、派息率趋近 0，是数字不是读数）。**歧义 MUST 显式陈述**：M 档 9.01× 既可读成「\(g=-1.10\%\)、\(r=10\%\)」，也可读成「\(g=0\)、\(r\approx11.1\%\)」。两个读法在本框架内不可区分（A9）。
# - **属性 H — 自主 G50 必须是分子里的一条腿，不能是分母里的一个增长率**：这是 skill A2e-2c-ex 第 3 条的直接要求（「任何一档的倍数 MUST NOT 承载未建模的业务故事。有新业务值钱 → 做成一条腿（分子），MUST NOT 糊进分母」）。此前版本把 G50 塞在 \(g_C=+10\%\) 里——那是把一个增长率乘在一条只占集团利润 6.8% 的**存量**腿上，结果是「把 G50 的永续增长从 0% 拉到 +20% 也只让 M 档动 +10.5%」。**这不是 G50 不值钱，是构造把它埋了**。改成加总式期权腿后，修正带 H′ 从底牌 H 22.15 抬到 **25.00**——被埋掉的正是这 2.85 HKD（G50 1.92 + G200 0.92，已扣产能一期未投资本）。仓库先例：`000338.SZ` 腿 C（大缸径 M 系列 = 台数 × 单价 × 净利率 × PE，L 档归零）就是同一形制。
# - **属性 F — 为什么 `fast_grower` 是次类而不是主类**：燃机腿的增速确实够（收入 +25.0%、G50 产能规划 10–12 台 → 30 台），但它只占集团毛利 4.6%，含表外权益收益的利润权重也只有 6.8–7.4% **且在下降**。让一条 7% 的腿定义整只票的主类，等于让新闻稿驱动尺子。次类的作用是**强制腿 C 独立成腿**（否则会被合并倍数埋掉），而不是抬整体倍数。**证伪点**：若腿 C 的 **M 档**利润权重连续两期升破 **10%**，主类可议（`eval` 有该守卫，口径见 A15）。
# - **属性 G — 净现金 205.97 亿不进主公式**：每股 5.96 CNY / 7.03 HKD（货币资金 + 交易性金融资产 − 短借 − 一年内到期非流动负债 − 长借，三季报 BS）。它已通过财务费用体现在归母里，再扣一次是重复计算；写在这里作 `deep_discount` 档的独立缓冲参照（A11）。
# | A1 | **分子：L = 自身实测消化年，M / H = FY2028E 卖方共识（2026-10-04 改）**：东方电气是**需求周期型制造**（煤电 / 水电 / 核能 / 燃机装备与电站服务，价格自己谈、周期来自核准与交付量，不是商品价函数，A20）——按 valuation-rules「周期票的中枢分子」适用范围（2026-10-04 定），中枢规则不适用，M / H 按「数据优先级」取 ≥2 家带区间的最远共识年：东方财富 F10 半年报（2026-08-26 公告）后 **FY2028E 4 家**——长江 09-25 67.08 / 华鑫 09-24 **73.38** / 东吴 11-03 **68.10** / 光大 08-26 **64.34** 亿（中金 11-02 仍无 FY2028）→ M = 均值 **68.23 亿**、H = 上沿 **73.38 亿**（东吴 11-03 已因费用率增加将 FY2028 从 71.94 下修至 68.10 亿，−5.3%；其余 3 家仍在财报前，H 的华鑫上沿未获 Q3 后验证；此为混合日期集合，非完整 Q3 后共识），FY2028 = 当前财年 + 2 → 折回 1.25 年（时点对齐基准日 2026-09-30，A22）；下沿 64.34 只作坐标。薄覆盖不命中（4 家 > 2 家）。L = **FY2025 归母 38.31 亿**（最近完整年，消化年格）不变；FY2024 谷底 29.22 亿**不作 L**——谷底分子配稳态 g₂ 是把周期算两遍（valuation-rules「谷底档」），只作 `deep_discount` 压力坐标（谷底 × 1/r = 9.98 HKD）。**周期位置披露（不改 M）**：FY2028E 均值是自身五年（FY2021–25）均值 30.90 亿的 **2.21 倍**；中枢坐标（五年均值 × M 档倍数，不折）= 9.51 HKD，只披露。**证伪触发器（触发后回对话，不自动回中枢）**：FY2027 年报归母低于 FY2027E 共识下沿 53.30 亿；或公司新生效订单同比连续两个半年度转负且全国煤电核准年度量回到 2021 年 18 GW 量级。旧口径（M = TTM 46.35、H = 2026H1×2 54.26，2026-09-14 按 ②-b 保留）随规则适用范围废止 | active | 东方财富 F10「盈利预测·机构预测明细」2026-11-05 复核（东吴 11-03、中金 11-02 晚于本期财报；FY2028 仅东吴刷新；[东吴 Q3 点评原文](https://pdf.dfcfw.com/pdf/H3_AP202611031831361990_1.pdf)）及 2026-10-04 拉取（历史本地缓存）：FY2027E 半年报后 5 家 53.30 / 56.64 / 61.61 亿；剔除半年报前 3 家（财通 06-03、兴业 04-28、华源 04-09）。归母序列（2025 年报原文 + Longbridge 季度）：FY2019 12.78 / FY2020 18.62 / FY2021 22.89 / FY2022 28.58 / FY2023 35.50 / **FY2024 29.22** / **FY2025 38.31** 亿；TTM 47.04；2026 前三季归母 38.39 亿（+29.40%，其中 Q3 11.25 亿 +6.51%）、扣非 34.94 亿（+28.17%）；前三季新增生效订单 934.75 亿（+5.5% vs 885.83 亿），证伪触发器未触发。**L 的实证坐标**：FY2025 基本 EPS 1.15（年报原文）、ROE 8.14%（按当前权益）、H 股 2025 年均价对应 own-year PE 11.97；FY2024 谷底：EPS 0.94、加权 ROE 7.71%、风电毛利 −2.74 亿、H 股年均价 9.65 HKD | `ni_l` / `ni_m` / `ni_h` / `ni_cons_fy28_lo` / `ni_mid5` / `ni_trough_fy2024` |
# | A2 | **腿权重取各档自身期间的实测分部毛利，不做估计**：L 用 FY2025、M 用 TTM（FY2025 − H1'25 + H1'26）、H 用 2026H1；**三季报不披露分部毛利，M 权重仍停在 TTM（至 2026H1），下一次可更新是 FY2026 年报；2026-11-05 13:43 复核时说明会尚未召开（官方安排当日 15:00–16:00），气电毛利率、煤电单独订单及 G50 经营数据待会后核实** | active | 全部取自定期报告原文附注「营业收入、营业成本按板块」：2025 年报（`AN202603311820923172`）给 FY2025/FY2024，2026 中报（`600875_20260826_E9SV`）给 H1'26/H1'25。逐格数字见 §1 属性 A | `gp_*`；**这是本框架的骨架**，权重不是判断而是实测 |
# | A3 | **已知归属的表外利润先指派，残差才按腿毛利权重分配**——即对残差部分假设三条腿的「毛利 → 归母」转化率相同 | active | 公司只披露到分产品毛利；报告分部的「营业利润」= 对外收入 − 对外成本 = 对外毛利（已逐格验算：能源装备制造 294.46 − 252.99 = 41.47 ✓、制造服务 62.71 − 42.25 = 20.46 ✓、新兴产业 29.07 − 25.86 = 3.20 ✓）；33.15 亿期间费用、减值与税负**无分部口径**。唯一有分腿归属证据的表外利润是三菱合资公司的权益收益（A14），故先指派 | **本框架最大的口径妥协**。方向性偏差：腿 B（毛利率 32.63%）大概率承担更低的费用率，被低估；腿 A 被高估。**已知的残余不一致**：2026H1 投资收益合计 2.21 亿，其中三菱合资 0.619 亿已指派，其余约 1.6 亿（昌吉皖新风电／木垒东新／四川东树等联营）仍按毛利权重摊——它们属腿 A、腿 B，摊法粗但方向无误。真实分部净利若披露，**MUST** 立即替换 |
# | A4 | **腿 C 分子用「气电」分部整体，不拆引进型 / 自主 G50** | active | **引进型 vs 自主的收入或台数拆分，公开市场不存在**——已逐字检索 2025 年报与 2026 中报全文、东财研报库 6 篇（东吴×3／华鑫／国信×2）、Wisburg 纪要库。可查到的两侧证据：自主 G50 已签「40 余台」海外订单、2026-08-28 首次整机成套出口发运（德阳→哈萨克斯坦），合作型 M701F4 供柬埔寨 2×450MW 共 2 套、国产化率 90%；而单台售价与毛利率的两个卖方口径互相打架且公司零确认（属性 C′） | `gp_c_*`；**本框架最敏感的单点，`待补`**。敏感性（`eval` 压力测试）：腿 C 的 \(g\) 由 0% 拉到 +20%，M 档仅从 20.72 升至 22.91（+10.5%）——腿太小，即使假设全错，锚点量级不变 |
# | A5 | **腿 A 永续 \(g_2\) = −4%，三档共用**：煤电核准洪峰已过，交付高峰在 2026–27，之后回到「存量替代 + 灵活性改造」。旧口径分档 −6% / −4% / −2% 会生成同向倍数（7.54 / 9.01 / 10.29），是 `cyclical` 不允许的形状（裁决顺序 ⑤：形状是结果检查，三档差别由分子承载）；分档值只作敏感性（M 档 −6% → 19.02、0% → 23.59，含时点对齐） | active | 核准序列：2021 约 18 GW → **2022 90.72 GW** → 2023H1 50.4 GW → **2024 63.99 GW** → 2025 前三季 41.77 GW（绿色和平／新浪财经汇总，见 §3 来源）。公司煤电收入 FY2024 202.57 → FY2025 244.92（+20.9%）→ 2026H1 149.56（+15.9%），正处上行段。腿 A 内煤电占 **77%**（H1'26 毛利 29.75 / 38.47） | `g2_a_*`；**全框架最重的杠杆**。核准滞后期的量化说法与三大集团在手订单序列 `待补` |
# | A6 | **腿 B 永续 \(g_2\) = +3%，三档共用**：存量机组基数扩大带动 after-market 自然增长（旧分档 0 / +3% / +5% 只作敏感性） | active | 电站服务 2026H1 收入 32.72 亿（+18.0%）、毛利率 **36.16%（+1.02pp）**；制造服务整体毛利率 32.63%（**+5.42pp**），是全公司毛利率最高的块。腿 B 内制造服务占 **86%**（23.66 中的 20.46），故 \(g_B\) 实质是电站服务的 \(g\)。**注意**：腿 B 含现代金融服务（财务公司）毛利 4.83 亿、毛利率 96.43%，是内部资金池而非装备生意，占集团毛利 7.4%。2026 前三季新增订单里制造服务占 21%（2025 报告口径现代制造服务 8.87%；2026 分类合并了工程与国际供应链，只作方向性参考） | `g2_b_*` |
# | A7 | **腿 C（存量燃机）永续 \(g_2\) = 0%，三档共用**——成长部分已剥离到腿 D（旧 H 档 +2% 只作敏感性） | active | 腿 C 现在只装引进型 M701F 机组销售 + 三菱合资的热部件与 LTSA 服务，是成熟业务：气电毛利 FY2024 5.18 / FY2025 6.76 / TTM 6.48 亿，三年无趋势；合资公司净利 FY2024 3.586 → FY2025 1.836 亿腰斩。给成熟业务 0~+2% 的永续增长 | `g2_c_*`；**此前版本给 H 档 +10% 是错的**——那是把 G50 的成长故事糊在存量腿的分母上（属性 H / A16） |
# | A8 | **倍数由 \(g\) 生成，MUST NOT 取历史 PE 分位**；own-year 实测带降级为护栏 | active | 按 `AGENTS.md`「永续增长口径」，本条优先于 skill A2e-2b。H 股 own-year PE（年均价 × 年均 HKDCNY ÷ 当年基本 EPS）：2019 11.01 / 2020 7.04 / 2021 9.99 / 2022 9.85 / 2023 8.21 / 2024 9.40 / 2025 11.97 → **带 [7.04, 11.97]，中位 9.85**。生成的三档 **9.08 / 9.01 / 8.89 全部落在带内 ✓**（≈ flat，微反向来自各档利润权重差；带边在 M 档 ROE 10.00% ≈ r 下反解 g [−4.2%, +6%→截] 含合成 g −1.10%），M 档贴近中位。EPS 用各年实际基本 EPS（2023–25 取年报原文 1.14 / 0.94 / 1.15；2019–22 用归母 ÷ 当年股本 31.175 亿股，2025 年定增后才变为 34.584 亿股） | `pe_own_*`；`eval` 强制护栏 |
# | A9 | **\(ROE \approx r\) 的歧义 MUST 双向陈述，MUST NOT 只报一个读数** | active | ROE(TTM) 10.00% vs \(r\) 10%，差 0.00pp，落在 `gordon.py` 的 `_ROE_NEAR_R = 3pp` 病态区内。卖方 TP 的反解 `well_conditioned=False` | §3「反解读数」；防止把不稳定的反解当结论 |
# | A10 | **不做四腿或五腿 SOTP**（只拆三腿） | active | ① 公司不披露分产品净利，腿越多主观分摊越重（A3）；② 水电／核能／风电三块合计毛利仅占 13.5%（H1'26 8.72 / 65.11），单列不改锚点量级；③ 新兴产业 4.6% 毛利且驱动因子（补贴）不可建模，与制造服务合并为「两翼」符合公司自身「一核两翼」口径 | 主尺形态 |
# | A11 | **不做「扣净现金 PE」修正** | active | 净现金 205.97 亿已通过财务费用体现在归母里，再扣一次是重复计算 | 防止双重计算；写进属性 G 与 `deep_discount` 解释 |
# | A12 | **未采用卖方目标价**：Longbridge 机构一致目标 **30.96 HKD**（2026-10-26，8 强烈买入 / 1 持有 / 1 卖出，区间 17.12–48.25），较本框架底牌 H 22.15 高 **40%**（较 H+V 上限 25.00 高 24%；2026-10-04 版为 38.01，对 H 21.73 高 75% / H+V 24.49 高 55%） | active | **`待补`（调研进行中，已部分收敛）。** 该目标价对 TTM 归母隐含 **19.27×**（对 FY2026E 共识 46.80 亿则为 19.4×），是 H 股 own-year 实测带顶（11.97×）的 **1.6 倍**，也是本框架 H 档 8.89× 的 **2.2 倍**。**已排除的方向**：分歧不在盈利年份的量级上——若卖方在给 FY2026 定价，差额几乎全部来自倍数。**尚未取得的**：逐机构目标价与方法。已确认美银用「基于 PE 的分部加总」，但中文转述稿未刊分部倍数；48.25 与 17.12 两个极值的机构归属查不到（Longbridge／富途／AASTOCKS／新浪均不给机构名）；同花顺该列经核实实为**归母净利润**而非目标价（申万 49.07 与其正文吻合可反证）。Wisburg **无东方电气个股覆盖** | **本框架当前最大的未解释项**。四个裁决方向中，(i) 更晚的盈利年份已弱化，(ii) 更高的倍数是当前最可能的解释，(iii) 由 A14 部分兑现但量级不足，(iv) 未验证。**MUST NOT** 在查清之前把分歧写成「卖方乐观」了事 |
# | A14 | **腿 C 的表外利润：三菱重工东方燃气轮机（广州）49% 权益法收益 MUST 直接指派腿 C**（它落在投资收益行，不进气电分部） | active | **构造已定（2026-09-09）；2026 前三季联营/合营投资收益 1.772 亿（+69.1%），该增速属于全部联营/合营企业投资收益，不能视作三菱合资净利增速；三菱单体 Q3 净利未披露，`jv_ni_*` 待年报附注再动。** 附注原文（2026 中报第 112 页、2025 年报同表）：该公司净利 FY2024 **3.586 亿** / FY2025 1.836 亿 / TTM 2.575 亿 / 2026H1 **1.263 亿**；DEC 按 49% 分别为 1.757 / 0.900 / 1.262 / 0.619 亿，**相当于同期气电分部毛利的 33.9% / 13.3% / 19.5% / 20.8%**。权益勾稽 17.107 → 18.370 亿（+1.263）完全吻合 ✓。业务实质＝ M701F 热部件与 LTSA 长协（12 台机组，中报「或有事项」附注） | `jv_stake` / `jv_ni_*` 进主公式。**采纳理由**：这是唯一有分腿归属证据的表外利润，量纲干净（先指派已知、再摊残差）；备选「并入毛利权重分子」把毛利与净利混进同一个分子，说不通。**代价**（v5 时）：L 档用 FY2024 时腿 C 权重曾升至 10.53%，故 `leg_c_weight_cap` 改为**只硬约束 M 档**（A15）；L 改 FY2025 后三档权重 7.29% / 7.38% / 6.75%，不再触发。三个构造的对照留在 §3 备查——锚点差 <1% |
# | A16 | **自主 G50 建成加总式期权腿（腿 D）**：\(NI^{G50}_x=units_x\times price\times gm_x\times k\)，L 档归零；台数 **0 / 12 / 25**，单价 **2.0 亿/台**三档不变，毛利率 **— / 30% / 40%**，\(k=0.3422\)（TTM 实测「毛利→归母」转化率，同 A3），永续 \(g\) **0 / 0 / 0**（= 燃机腿 C 的 \(g_2\)；兑现后的继续增长只进份数，2026-10-03 迁移），H 档折现 **1 年**。**升级门槛**：公司确认 G50 年产能 / 台数 / 单价 / 毛利，或 ≥2 家卖方给出可复算的 G50 收入 + 贡献利润 → 做成腿进底牌（同步折现口径）、从 \(V_{opt}\) 移出。**证伪触发器**：2027 年底产能远低于 25 台/年，或气电毛利率连续两期不升 → H 档台数退回当前产能 12 台。**与 FY2028 共识的重叠（2026-10-04，待对话）**：M / H 改用 FY2028E 共识后，G50 H 档的首个完整运行年 FY2028 与分子年相同；东吴 11-03 Q3 点评仍看好 G50 海外订单，但未拆分其收入及贡献利润；华鑫（09-24）亦未拆燃机，均未明说 2028 预测含多少台 G50——按「未建模期权」应扣共识已含部分，但扣多少无数可依，本版 \(V_{opt}\) 不动，披露可能部分双算 | active | **`待补`（台数与毛利率均无公司确认）。** **单价有硬标尺**：2 亿/台 ÷ 50MW = **$596/kW** vs GE Vernova 2027 报价 **~$600/kW**（2Q26 电话会）——同量级 ✓。东吴 3 亿/台 = $895/kW，口径不可比，未采用。**台数是最弱的一环**：H 档 25 台取 UBS 转述管理层的「2027 年底 25 台 G50」；同一句里的 3 台 G200 走 A18，不塞进这 25。另有互相冲突的口径——界面新闻「2027 年底 30 台/年」（**无署名机构、无公司出处**）、东吴引公司公众号「已签 40 余台海外订单」、China Daily 2026-08-28「2025-11 签约 **3 台**发运哈萨克斯坦」。公司自身口径：MD&A「自主燃机核心产能提升项目正式开工」；董事会决议（2026-04-30）一期总投资 7.39 亿；在建工程附注「G50 中心燃机高温透平叶片精铸产线」预算 8,087 万、进度 13.15%。**未投资本（2026-10-04，valuation-rules「未建模期权」新建产能型期权扣未投资本）**：H 档 25 台 G50 + 3 台 G200 = 从当前 10–12 台/年扩到 2027 年底产能，份数来自规划产能 → 在规则范围内，\(V_{opt}\) MUST 扣一期未投资本。预算 **7.39 亿**（董事会十一届十九次会议决议公告 2026-011，2026-04-30）；已投 **按 0**（2026 中报 2026-08-26 在建工程「重要在建工程」未列本项，期末余额 < 0.151 亿）；权益 100%（东方汽轮机全资）→ 扣 7.39 亿，在兑现时点（2027 年底）一次扣、随 H 档 \(lag=1\) 折回 = 6.72 亿 = **0.229 HKD/股**，按扣前价值比例摊到 G50 / G200（2.12 → 1.97、1.02 → 0.95）；\(V_{opt}\) 3.14 → 2.92，再随底牌时点对齐多折 0.25 年 → **2.85**（G50 1.92 + G200 0.92，A22）。M 档 12 台 ≤ 已建产能 12 台（`cap_now`），不扣。**偏差方向**：① 实际花费在 2026H2–2027 分摊，兑现时点一次扣少折了约半年，\(V_{opt}\) 偏高 ≤ 0.01；② 已投按 0 计，\(V_{opt}\) 偏低 ≤ 0.005；③ 其余燃机在建工程（2026 中报：全重实验室大功率燃气轮机燃烧器试验平台 预算 3.314 亿 / 累计 20.85%；燃机无机喷涂与热喷涂数字化产线 2.197 亿 / 12.98%；全重实验室燃机喷涂产线 0.809 亿 / 19.70%）未投合计 5.18 亿，属试验平台或引进型与自主机共用的涂层线、无法归到 25 台增量，**不扣**（`gt_other_k` 交叉）——若全计 \(V_{opt}\) 再降 0.16 至 2.69，故 \(V_{opt}\) 偏高方向；④ G200 的研制与专用产线投入公司零披露（`待补`），若一期不含 G200 能力，G200 部分偏高——升级门槛：公司披露一期产能构成或 G200 产线预算即扣 | `g50_*` / `cap_*`。加拿大买方采购 30 台的新报道已更新旧的 10–20 台口径（[智通 2026-11-02 援引新华财经](https://longbridge.cn/news/303905269)，买方 10-26 宣布）；本次未取得东方电气对金额、交付年份及履约条件的确认，总采购量不等于年交付量，**不加**进 \(V_{opt}\) |
# | A17 | **腿 D 的 H 档折现 1 年，不是 2 年**：\(r\_disc=10\%\)，\(lag\) = L 0 / M 0 / H 1 | active | `perpetual_pe` 返回的是**对下一期盈利**的倍数（见 `eval/lib/gordon.py` 的 `two_stage_pe` docstring），即 \(NI\times PE\) 已经是「盈利开始前一期」的现值。M 档 12 台约等于当前产能（10–12 台/年，首台整机 2026-08-28 已发运），盈利自 FY2027 起 → 与 `perpetual_pe` 的隐含时点一致，\(lag=0\)；H 档 25 台是 2027 年底产能、FY2028 才是首个完整运行年 → 比隐含时点晚一年，\(lag=1\)。G200 与 G50 H 档共用这一年折现（A18）。产能一期的未投资本（A16）同在兑现时点扣、随同一 \(lag\) 折回（同样板 `002895.SZ` 口径） | `g50_lag_*` / `r_disc` / `cap_*` |
# | A18 | **G200 并入 \(V_{opt}\)**：台数 L/M = **0**、H = **3**；单机 200 MW；单价 = `g50_price × g200_mw / g50_mw` = **8.0 亿/台**（同一 \(596/kW\)）；毛利率 / \(g\) / 折现年与 G50 的 H 档相同。M 世界不计价 | active | **`待补`（2027 年下线、零商用、零公司确认台数）。** 与 A16 **同一句** UBS 转述「2027 年底 25 台 G50 + **3 台 G200**」。公司口径：以 G50 为基础向上拓展 200 MW 级，计划 2027 年下线（新华社 / 东方电气公开介绍）。**证伪**：2027 年底未下线或始终零订单 → 本项置 0，G50 不受牵连。**升级门槛**：公司确认 G200 台数/单价/毛利，或 ≥2 家卖方给出可复算的收入+利润 → 做成腿、从 \(V_{opt}\) 移出。核电/抽蓄已在腿 A，不另开 | `g200_mw` / `g200_units_*`。H 档贡献 **0.95 HKD**（扣按价值分摊的一期未投资本；未扣 1.02）；表 3 整体隐含倍数 H = 10.02（含 G50 + G200）在 own-year 带内（v5 时曾越顶 12.07，倍数改 flat 后消失） |
# | A15 | **`leg_c_weight_cap` 只硬约束 M 档，其余档超限只告警不报错** | active | 采纳 A14 后腿 C 权重 = L **7.29%** / M 7.38% / H 6.75%（L 改 FY2025 后无超限；v5 用 FY2024 时 L 曾 10.53%——「DEC 自身归母谷底 29.22 亿 × 合资公司净利峰值 3.586 亿」撞在一起的构造性产物，**不是燃机腿变大的证据**） | 守卫语义：M 档是「当期已知事实长期化」，唯一适合承载「这条腿有多大」这个结构性断言的档；L/H 是情景档，腿的构成本就会因情景而摆动。`eval` 对 L/H 超限打 ⚠ 并照常打印，仅 M 档超限时报错 |
# | A13 | **本票挂 `_AXIS.southbound-repricing.md`**，但轴只解释 H/A 折价的方向，**不进分子也不改本票倍数** | active | H/A 逐日序列（Longbridge 日线 × yfinance `HKDCNY=X`）年度均值：2019 **0.457** / 2020 0.428 / 2021 0.508 / 2022 0.503 / 2023 0.519 / 2024 0.560 / 2025 **0.746** / 2026 **0.812**（截至 2026-09-11）。**方向与轴的其余四票一致：2024 见底、2025 起跳** | 轴的读数进 §3。**注意本票与轴 §3 第 1 条的关系**：该条要求 H 股倍数取 H 股自身 own-year 序列，但 `AGENTS.md`「永续增长口径」规定倍数由 \(g\) 生成且**优先**；本票按 `6655.HK` 的解法处理——走 Gordon，own-year 带降级为护栏（A8） |
# | A19 | **四个合法杠杆逐一交代；分子已换 FY2028E 共识（2026-10-04，A1）** | active | 卖方 TP 只有 Longbridge 10 家一致目标 30.96 HKD 一个聚合值（逐家 `待补`，A12）：H 22.15 / H+V 25.00 对 TP = 0.72 / 0.81（2026-10-04 版 H 21.73 / H+V 24.49 = 0.57 / 0.64；v7 为 16.32 / 19.43）。① Gordon 倍数已入位——每腿一个稳态 g₂ 三档共用（`cyclical` flat，⑤），来源层级「无同业锚」（三腿 g 自定：A5 / A6 / A7）；g₂ ±1pp（三腿同动）→ 三档 10.89 / 19.18 / 20.54（H+V 23.38）与 13.06 / 22.57 / 24.08（H+V 26.93）；L 是 FY2025 实测 38.31 亿（7.93 → 11.88）。② 共识已进分子（2026-10-04）：需求周期型按数据优先级取最远 ≥2 家带区间年 FY2028E（4 家，均值 / 上沿），折回 1.25 年（A22）；旧版（2026-09-14）按 ②-b 保留自身实测分子、FY2027 三点只作印证的裁定，随「周期票的中枢分子」适用范围废止；无 FY2029 → 无 g₁。③ V_opt 已入位（三菱合资进腿 C；G50 25 台 + G200 3 台 − 产能一期未投资本 = 2.85（时点对齐后））。④ 候选带不可用（无具名单家可复算候选值：A4 / A12 / A16 / A18 均为 `待补` 无数值）。**归篮复核**（① 归篮 ② 分子 ③ g）：存量装备没有给更低 r 的理由；分子为 FY2028E 共识；H 以上的差额落在未进报表的自主燃机（表3）与卖方倍数（A12）→ 维持篮 4。刻意不承销：卖方 19.3× 倍数、加拿大订单漏斗、核电/抽蓄（腿 A 内） | **复核条件**：A12 逐机构方法查清、或公司确认 G50 / G200 台数（A16 / A18）→ 重跑差额表；FY2029 ≥2 家出现 → 评估 g₁ |
# | A20 | 归篮：煤电 / 两翼 / 存量燃机三腿 → 篮 4 龙头制造（电力设备制造龙头（国企），非商品价函数；三腿同篮，合成 ḡ 在同一 r 下成立——只禁止各腿 r 不同时合成）；腿 D（G50 / G200 \(V_{opt}\)）折现率 `r_disc` 与 `r_perp` 同源，同为 10%；无备选篮；CAPM 粗筛未做（r 与全仓默认档同值，无需 CAPM 残差解释）。**g₂ 域判定**：ROE 8.1 / 14.5 / 15.6% − 10% = −1.9 / +4.5 / +5.6pp → L 病态区、M / H 单调区（M / H 为 FY2028E 共识 ÷ 今日权益），但本票走全派息 + 合成 ḡ < 0 分支（派息 100%，PE = 1/(r − ḡ) ≈ 9.0×），不是留存分支——「两分支都贴 1/r、对 g 不敏感」只对留存分支成立，全派息萎缩分支的 PE 仍随 ḡ 动（`g2_a` 0 / −6% → M 23.59 / 19.02，全框架最重杠杆），故三腿 g₂ −4% / +3% / 0% 必须来自实测 / 政策（核准序列 / 装机基数 / 三年无趋势，A5–A7）而非反解；cap = min(6%, 10% − 4%) = 6% 未触及。**留存三桶**：净现金 205.97 亿 CNY = 7.03 HKD/股，属财务性桶，只披露不进倍数（A11；与 `1766.HK` 同判：从不分配的现金按 0 计）；增长性 capex（G50 / G200 产能）已走腿 D 期权，不进永续 g | active | `gordon.BASKET_R`；`valuation-rules.md`「§r 篮子」；篮子归属决策记录无本票专属节（按「无变化的票」处理） | `r_perp` / `r_disc`；九个 `g2_*` 保留；L/M/H 11.88 / 20.72 / 22.15 |
# | A22 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」，2026-10-15）**：① **超额现金不单列**——净现金 206 亿的利息已在利润里，框架原本不单列 → 保留原结构；归母比例不涉及。**增长期资金缺口 0**：FY2023–25 经营现金流合计 85.7 亿 ≈ 资本开支 83.9 亿（yfinance 年报），现有业务付得起；燃机核心产能一期 7.39 亿只服务 G50 / G200（FY2028 起兑现），已在期权里按「价值 − 未投资本」扣，不进底牌。② **时点对齐**：M / H 分子 FY2028E → Gordon 值在 2028-01-01；估值基准日随最新资产负债表日滚到 2026-09-30，\(\tau\) = 1.25 年；L 是 FY2025 实测「消化年」当稳态，属不随日历漂移的常态年，不折。窗口（2026Q4 + FY2027）可分配利润 = 尚未入账的共识归母利润 ×（1 − b），b = 0（合成永续增长为负，倍数里派息封顶 100%，留存率取 0）：M（FY2026E 均值 1.352 × 34.58 亿股 − 前三季实测 38.39）+ FY2027E 均值 56.64 = 65.0 亿、H 用上沿 1.47 / 61.61 = 74.0 亿，按 τ/2 = 0.625 年折 → 2.09 / 2.38 港元/股；期权 G50 / G200 同折（在原兑现年折现上多折 0.25 年），3.14 → 2.92（2028-01-01 点），折到 2026-09-30 = 2.85。③ **稳态回报三段**：合成永续增长 −1.01 / −1.10 / −1.25% ≤ 0，回报不进倍数，不受影响。④ 无打折 k（0.3422 是 G50 腿折归母的系数）。2026-11-05 预测刷新后 M 21.00 → 20.72（−1.3%），H 22.15 不变；本表其余行里的旧锚点数字（如 A5 的分档 g 读数）已按新口径改写的以 Outputs 为准 | active | 2026 三季报；东方财富 F10 共识；valuation-rules「经营价值与超额现金」①②③ | `tau`、`eps_fy26_m/h`、`ni_9m_26`；M / H、期权 |

TIERS = ("l", "m", "h")
LEGS = ("a", "b", "c")
LEG_CN = {"a": "周期装备", "b": "两翼", "c": "燃机"}

REQUIRED = (
    ["ni_cons_fy27_lo", "ni_cons_fy27_mean", "ni_cons_fy27_hi", "ni_cons_fy28_lo", "ni_ttm",
     "ni_mid5", "tau", "eps_fy26_m", "eps_fy26_h", "ni_9m_26", "payout_obs", "pb_own_min", "m_prev", "shares", "bps", "fx_hkdcny", "r_perp", "equity",
     "net_cash", "tp_street", "leg_c_weight_cap", "ni_trough_fy2024",
     "pe_own_lo", "pe_own_hi", "pe_own_mid", "pe_own_a_mid", "jv_stake",
     "g50_price", "g50_k", "r_disc", "usdcny", "g50_mw",
     "g50_usdkw_lo", "g50_usdkw_hi",
     "g200_mw", "g200_units_l", "g200_units_m", "g200_units_h",
     "cap_k", "cap_spent", "cap_eq", "cap_now", "gt_other_k"]
    + [f"jv_ni_{t}" for t in TIERS]
    + [f"ni_{t}" for t in TIERS]
    + [f"gp_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"g2_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"g50_{f}_{t}" for f in ("units", "gm", "g", "lag") for t in TIERS]
)


def nondecreasing(name: str, *values: float) -> list[str]:
    """Assert a non-decreasing ladder.

    Several ladders here legitimately repeat a value: the mature gas leg's
    perpetual g is 0 at both L and M, and the G50 option leg's g is 0 until it
    has capacity to grow into.  A strict ladder would force a fake difference.
    """
    if all(a <= b + 1e-12 for a, b in zip(values, values[1:])):
        return []
    return [f"{name} non-decreasing ladder violated: "
            f"{' <= '.join(f'{v:g}' for v in values)} is false"]


def gross_weights(inp: dict[str, float], tag: str) -> dict[str, float]:
    """Leg share of that tier's own measured segment gross profit — the key the
    residual profit is spread on, not the ruler's leg weight."""
    gp = {leg: inp[f"gp_{leg}_{tag}"] for leg in LEGS}
    total = sum(gp.values())
    return {leg: v / total for leg, v in gp.items()}


def weights(inp: dict[str, float], tag: str) -> dict[str, float]:
    """Leg profit weight under the ruler: assign the JV, spread the residual."""
    return variant_weights(inp, tag, "assign")


def blended_g(inp: dict[str, float], tag: str) -> float:
    w = weights(inp, tag)
    return sum(w[leg] * inp[f"g2_{leg}_{tag}"] for leg in LEGS)


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_{tag}"] / inp["equity"]


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(blended_g(inp, tag), forward_roe(inp, tag), inp["r_perp"])


def g50_leg(inp: dict[str, float], tag: str) -> tuple[float, float, float]:
    """(net income, multiple, discounted value) of the domestic-G50 option leg.

    Additive, not a weight.  The leg earns ~nothing today — the first complete
    unit shipped 2026-08-28 — so a profit weight would round it to zero and the
    story would end up living in leg C's growth rate, which skill A2e-2c-ex
    forbids ("有新业务值钱 → 做成一条腿（分子）").  Same shape as 000338.SZ's
    M-series leg: units x price x margin, and zero at L.

    Only this leg is discounted.  `perpetual_pe` already prices next-period
    earnings, so a tier whose earnings start exactly next period needs no
    discount; H's 25 units/yr is end-2027 capacity, first full year FY2028,
    one period later — hence g50_lag_h = 1 (A17).
    """
    ni = inp[f"g50_units_{tag}"] * inp["g50_price"] * inp[f"g50_gm_{tag}"] * inp["g50_k"]
    if ni <= 0:
        return 0.0, 0.0, 0.0
    pe = perpetual_pe(inp[f"g50_g_{tag}"], forward_roe(inp, tag), inp["r_perp"])
    return ni, pe, ni * pe / (1.0 + inp["r_disc"]) ** inp[f"g50_lag_{tag}"]


def g50_usd_per_kw(inp: dict[str, float]) -> float:
    """Unit price translated to the global heavy-frame quoting convention."""
    return inp["g50_price"] * 1e8 / inp["g50_mw"] / inp["usdcny"] / 1e3


def to_hkd(inp: dict[str, float], cny: float) -> float:
    """CNY market value (亿元) -> HKD per share."""
    return cny * 1e8 / inp["shares"] / inp["fx_hkdcny"]


def disc(inp: dict[str, float], tag: str) -> float:
    """Discount factor of a tier's numerator (valuation-rules「经营价值与超额现金」③ 时点对齐,
    A22): M / H are FY2028E consensus -> the Gordon value sits at 2028-01-01, back tau years
    to the balance-sheet date 2026-09-30 at the basket r; L is the realised FY2025 year (a
    steady-state year that does not drift with the calendar) and is not discounted."""
    return 1.0 if tag == "l" else (1.0 + inp["r_perp"]) ** inp["tau"]


def window_cny(inp: dict[str, float], tag: str) -> float:
    """Window (2026Q4 + FY2027) distributable profit, 亿 CNY, M / H only (A22): unbooked
    consensus parent profit x (1 - b); b = 0 because the composite g is negative and the
    multiple caps the payout at 100%.  Discounted at tau/2."""
    if tag == "l":
        return 0.0
    fy26 = inp[f"eps_fy26_{tag}"] * inp["shares"] / 1e8 - inp["ni_9m_26"]
    fy27 = inp["ni_cons_fy27_mean"] if tag == "m" else inp["ni_cons_fy27_hi"]
    return (fy26 + fy27) / (1.0 + inp["r_perp"]) ** (inp["tau"] / 2)


def incumbent_cny(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    """存量三腿 CNY 市值（亿元，时点对齐到中报日，含窗口可分配利润）。G50 不进底牌（A2e-7）。"""
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return inp[f"ni_{tag}"] * pe / disc(inp, tag) + window_cny(inp, tag)


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    """底牌 HKD/股 = 存量三腿；G50 计 0."""
    return to_hkd(inp, incumbent_cny(inp, tag, flat_pe))


def g50_ps(inp: dict[str, float], tag: str) -> float:
    """G50 腿 HKD/股（未乘 p_k；已扣分摊的未投资本）。"""
    return to_hkd(inp, option_parts(inp, tag)[0])


def g200_price(inp: dict[str, float]) -> float:
    """亿元/台 = G50 单价按 MW 放大，同一 $/kW。"""
    return inp["g50_price"] * (inp["g200_mw"] / inp["g50_mw"])


def g200_leg(inp: dict[str, float], tag: str) -> tuple[float, float, float]:
    """G200 option: same $/kW and H-tier gm/g/lag as G50; units 0 at L and M.

    2027 下线, not a current run-rate — M-world credit is 0.  H-tier 3 units
    come from the same UBS sentence that set g50_units_h = 25.
    """
    units = inp[f"g200_units_{tag}"]
    if units <= 0:
        return 0.0, 0.0, 0.0
    ni = units * g200_price(inp) * inp[f"g50_gm_{tag}"] * inp["g50_k"]
    pe = perpetual_pe(inp[f"g50_g_{tag}"], forward_roe(inp, tag), inp["r_perp"])
    return ni, pe, ni * pe / (1.0 + inp["r_disc"]) ** inp[f"g50_lag_{tag}"]


def capex_k(inp: dict[str, float], tag: str) -> float:
    """Unspent capacity capital charged to a tier (亿 CNY, discounted).

    valuation-rules「未建模期权」(2026-10-04): an option whose units come from
    capacity still to be built is worth its realised value LESS the capital not
    yet spent.  Only tiers whose G50 + G200 units exceed the capacity already
    built (`cap_now`) need 一期 (7.39 亿, 30/yr by end-2027).  The charge sits at
    the realisation point and rides the option's own lag — spend actually runs
    2026H2-2027, so charging it at end-2027 slightly flatters V_opt (A16/A17).
    """
    units = inp[f"g50_units_{tag}"] + inp[f"g200_units_{tag}"]
    if units <= inp["cap_now"]:
        return 0.0
    remain = (inp["cap_k"] - inp["cap_spent"]) * inp["cap_eq"]
    return remain / (1.0 + inp["r_disc"]) ** inp[f"g50_lag_{tag}"]


def option_parts(inp: dict[str, float], tag: str) -> tuple[float, float]:
    """(G50, G200) CNY 市值 net of the unspent capital, split pro rata to gross."""
    g50, g200 = g50_leg(inp, tag)[2], g200_leg(inp, tag)[2]
    gross = g50 + g200
    if gross <= 0:
        return 0.0, 0.0
    k = capex_k(inp, tag)
    # Timing (A22): the option's lag puts it at the numerator year's opening like the deck
    # (lag 0 = 2027-01-01 world of the old t=1, lag 1 = 2028-01-01); the deck moved from a
    # whole year to tau years, so the option rides the same extra (tau - 1) years.
    shift = (1.0 + inp["r_disc"]) ** (inp["tau"] - 1.0)
    return (g50 - k * g50 / gross) / shift, (g200 - k * g200 / gross) / shift


def g200_ps(inp: dict[str, float], tag: str) -> float:
    return to_hkd(inp, option_parts(inp, tag)[1])


def option_mv(inp: dict[str, float], tag: str) -> float:
    """G50 + G200 CNY 市值（亿元），已扣未投资本。"""
    return sum(option_parts(inp, tag))


def variant_weights(inp: dict[str, float], tag: str, mode: str) -> dict[str, float]:
    """Leg weights under the three candidate treatments of the JV (A14).

    The gas-turbine leg's fattest profit pool — M701F hot parts and the LTSA
    service contracts — sits in a 49%-held associate carried at equity, so it
    lands in 投资收益 and never touches the 气电 segment's revenue or cost.
    Whether it belongs in leg C's weight is an open construction question; all
    three answers are priced here so the choice is made against numbers.

      base    leg weights are segment gross profit, full stop (rejected: the
              filings show the JV's profit exists and belongs to leg C)
      assign  the JV's equity income goes to leg C, the rest of group NI is
              split on gross-profit weights (THE RULER, A14)
      addw    the JV's equity income is added to leg C's weight numerator
              (rejected: mixes pre-tax gross profit with after-tax net income)
    """
    w = gross_weights(inp, tag)
    if mode == "base":
        return w
    equity_income = inp[f"jv_ni_{tag}"] * inp["jv_stake"]
    if mode == "assign":
        residual = inp[f"ni_{tag}"] - equity_income
        legs = {
            "a": residual * w["a"],
            "b": residual * w["b"],
            "c": equity_income + residual * w["c"],
        }
    elif mode == "addw":
        legs = {leg: inp[f"gp_{leg}_{tag}"] for leg in LEGS}
        legs["c"] += equity_income
    else:
        raise ValueError(f"unknown variant: {mode}")
    total = sum(legs.values())
    return {leg: v / total for leg, v in legs.items()}


def variant_band(inp: dict[str, float], mode: str) -> tuple[list[float], list[float]]:
    """(anchors, leg-C weights) for one JV treatment."""
    anchors, wc = [], []
    for t in TIERS:
        w = variant_weights(inp, t, mode)
        g = sum(w[leg] * inp[f"g2_{leg}_{t}"] for leg in LEGS)
        pe = perpetual_pe(g, forward_roe(inp, t), inp["r_perp"])
        anchors.append(to_hkd(inp, inp[f"ni_{t}"] * pe / disc(inp, t) + window_cny(inp, t)))
        wc.append(w["c"])
    return anchors, wc


def evaluate(inp: dict[str,float], rate_inputs=None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, tuple(f'g50_lag_{t}' for t in TIERS))

    r = inp["r_perp"]
    lo, hi = inp["pe_own_lo"], inp["pe_own_hi"]

    # --- Step 0: r is a basket value (valuation-rules「§r 篮子」) -------------
    # The three incumbent legs share one r, so the blended-g Gordon is legal
    # (A20); the framework names the basket on the r_perp row and r must be
    # that basket's value.  r_disc is the option leg's discount rate and has to
    # equal r_perp (A17) — it carries no basket tag of its own.
    baskets = {"r_perp": 4}
    if "r_perp" not in baskets:
        errors.append("r_perp row names no 篮 N in its source cell (A20)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_r(inp["r_disc"], "r_disc")
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal r_perp={r} (A17)")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 1: numerators and leg weights ---------------------------------
    errors += ladder("ni", *(inp[f"ni_{t}"] for t in TIERS))
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    for t in TIERS:
        total = sum(inp[f"gp_{leg}_{t}"] for leg in LEGS)
        if total <= 0:
            errors.append(f"tier {t.upper()}: segment gross profit sums to {total}")
    if errors:
        raise ValueError('; '.join(errors))

    w = {t: weights(inp, t) for t in TIERS}

    # --- Step 2: growth 口径 and convergence ---------------------------------
    # 裁决顺序 ⑤ (cyclical → flat or reversed) + valuation-rules「分子与 g 同世界」:
    # every incumbent leg carries ONE steady g2 shared by all three tiers; the
    # tiers differ in the numerator (FY2025 / TTM / 2026H1x2), not in g.  The
    # blend still moves a little with each tier's own leg weights — that is
    # weight mechanics, not a growth ladder, so it is printed, not laddered.
    for leg in LEGS:
        vals = [inp[f"g2_{leg}_{t}"] for t in TIERS]
        if max(vals) - min(vals) > 1e-12:
            errors.append(
                f"g2_{leg} ({LEG_CN[leg]}) differs across tiers {vals} — a cyclical's "
                "tiers separate on the numerator; a tiered g re-prices the cycle (裁决顺序 ⑤)"
            )
    for field in ("units", "gm", "g"):
        errors += nondecreasing(f"g50_{field}", *(inp[f"g50_{field}_{t}"] for t in TIERS))
    g = {t: blended_g(inp, t) for t in TIERS}
    for t in TIERS:
        if r - g[t] <= 0:
            errors.append(f"g_{t}={g[t]:.4f} >= r={r} — perpetuity diverges")
    # 永续上限 g_cap(r) = min(6%, r − 4%): every named perpetual g — the three
    # incumbent legs (`g2_*`, visible to calibration.py), the option leg, and
    # the blend.
    for leg in LEGS:
        for t in TIERS:
            errors += check_g_cap(inp[f"g2_{leg}_{t}"], r, f"g2_{leg}_{t}")
    for t in TIERS:
        errors += check_g_cap(inp[f"g50_g_{t}"], r, f"g50_g_{t}")
        errors += check_g_cap(g[t], r, f"g_blended_{t}")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 3: normative guards -------------------------------------------
    # A1: L is the latest complete year, a realised steady level — not the
    # FY2024 trough.  A trough numerator paired with a steady g2 counts the
    # cycle twice (valuation-rules「谷底档」); the trough only sets the
    # deep_discount pressure coordinate.
    if inp["ni_l"] <= inp["ni_trough_fy2024"]:
        errors.append(
            f"ni_l {inp['ni_l']} <= FY2024 trough {inp['ni_trough_fy2024']} — a trough numerator "
            "cannot carry a steady g2 (valuation-rules「谷底档」); L is the latest complete year"
        )
    # A8: generated multiples must stay inside prices this stock has printed.
    pe = {t: multiple(inp, t) for t in TIERS}
    for t in TIERS:
        if not (lo - 1e-9 <= pe[t] <= hi + 1e-9):
            errors.append(
                f"PE_{t.upper()}={pe[t]:.2f} outside H-share own-year band "
                f"[{lo}, {hi}] — the normative anchor left the ticker's history (A8)"
            )
    # A12: growth is paid for out of retained earnings; a shrinking business is
    # not assumed to hand back more than it earns.
    for t in TIERS:
        pay = payout(g[t], forward_roe(inp, t))
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g[t] <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g={g[t]:.2%} <= 0 — cap not binding")
    # §1 属性 F / A15: the gas-turbine leg is an option leg *because* it is
    # small.  Only the M tier can carry that structural claim — it is the tier
    # that states current known facts long-run.  L and H are scenario tiers, and
    # L in particular pairs DEC's own trough year with the associate's peak, so
    # its leg mix says something about FY2024's arithmetic, not about the leg.
    cap = inp["leg_c_weight_cap"]
    if w["m"]["c"] >= cap:
        errors.append(
            f"leg C weight {w['m']['c']:.2%} at the M tier >= cap {cap:.0%} — "
            "the gas-turbine leg is no longer an option leg; revisit lynch_primary"
        )
    over = [t.upper() for t in ("l", "h") if w[t]["c"] >= cap]
    # Leg C must remain the smallest leg at M, or the three-leg split is mislabelled.
    if not (w["m"]["c"] < w["m"]["a"] and w["m"]["c"] < w["m"]["b"]):
        errors.append("M tier: leg C is not the smallest leg")
    # A16: the option leg must vanish at L, or L stops being "the measured bad".
    if inp["g50_units_l"] != 0:
        errors.append(
            f"g50_units_l={inp['g50_units_l']} — the option leg MUST be zero at L"
        )
    if inp["g200_units_l"] != 0 or inp["g200_units_m"] != 0:
        errors.append(
            f"g200_units L/M = {inp['g200_units_l']:.0f}/{inp['g200_units_m']:.0f} "
            "— G200 2027 下线, MUST be zero until H"
        )
    if abs(inp["g200_mw"] / inp["g50_mw"] - 4.0) > 1e-9:
        errors.append(
            f"g200_mw/g50_mw = {inp['g200_mw'] / inp['g50_mw']:.3f} — "
            "the name is 200 MW vs 50 MW, ratio must be 4"
        )
    # A16: the unit price has to be comparable to what heavy frames actually
    # quote for.  Citi's CNY 2.0e8 per 50 MW is $596/kW against GEV's ~$600/kW
    # for 2027; a price outside the global cluster means the two口径 are not the
    # same thing and the leg is being fed a number from a different scope.
    usdkw = g50_usd_per_kw(inp)
    if not (inp["g50_usdkw_lo"] <= usdkw <= inp["g50_usdkw_hi"]):
        errors.append(
            f"g50 unit price = ${usdkw:.0f}/kW outside the global heavy-frame "
            f"cluster [{inp['g50_usdkw_lo']:.0f}, {inp['g50_usdkw_hi']:.0f}] — "
            "the price scope is not comparable (A16)"
        )
    # The option leg must not push the whole-company multiple outside anything
    # this stock has printed.  The incumbent legs are fenced above; this fences
    # the sum, which is what a reader actually compares to a market PE.
    # G50-only implied multiple must stay in the printed band.  G200 is a 2027
    # machine that is not in the 2019-2025 own-year PE history, so the combined
    # 表3 multiple may overshoot pe_own_hi — printed, not a fail (A18).
    for t in TIERS:
        implied_g50 = (inp[f"ni_{t}"] * pe[t] + option_parts(inp, t)[0]) / inp[f"ni_{t}"]
        if not (lo - 1e-9 <= implied_g50 <= hi + 1e-9):
            errors.append(
                f"G50-only implied multiple at {t.upper()} = {implied_g50:.2f} "
                f"outside own-year band [{lo}, {hi}]"
            )
    # Comparison-only fields must not have leaked into the multiple path.
    for key in ("pe_own_mid", "pe_own_a_mid"):
        if abs(inp[key] - pe["m"]) < 1e-9:
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        raise ValueError(f'L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}')
    A, B = cut_points(L, M, H)
    v_g50 = g50_ps(inp, "h")
    v_g200 = g200_ps(inp, "h")
    v_opt = v_g50 + v_g200
    p_m = (g50_ps(inp, "m") / v_opt) if v_opt else 0.0
    p_k = (0.0, p_m, 1.0)
    adj_band = [base + pk * v_opt for base, pk in zip((L, M, H), p_k)]

    flat = {t: anchor(inp, t, flat_pe=pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", *(flat[t] for t in TIERS))
    errors += ladder("base", L, M, H)
    if abs(adj_band[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L {adj_band[0]:.4f} != {L:.4f}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    if not inp['ni_cons_fy28_lo'] <= inp['ni_m'] < inp['ni_h']:
        errors.append('FY2028 consensus ladder invalid')
    if abs(inp['tau'] - 1.25) > 1e-9:
        errors.append('tau must preserve the 2026-09-30 to 2028-01-01 alignment')
    mid_ratio = inp['ni_m'] / inp['ni_mid5']
    coords = {'② E_M/r': to_hkd(inp, inp['ni_m']/r/disc(inp,'m')),
              '③ D_M/(r-0)': to_hkd(inp, inp['payout_obs']*inp['ni_m']/r/disc(inp,'m')),
              '⑥ BPS x PB低点': inp['bps']*inp['pb_own_min']/inp['fx_hkdcny']}
    inside = [k for k,v in coords.items() if abs(M/v-1)<=.20]
    if abs(M/inp['m_prev']-1)>.25 and not inside:
        errors.append('correction gate outside all independent coordinates')
    if errors:
        raise ValueError('; '.join(errors))
    fxa = inp['fx_hkdcny'] * inp['shares'] / 1e8
    ni200,pe200,mv200 = g200_leg(inp,'h')
    implied_all_h = (inp['ni_h']*pe['h']+option_mv(inp,'h'))/inp['ni_h']
    k_h = capex_k(inp,'h')
    gross_h = to_hkd(inp, g50_leg(inp,'h')[2]+g200_leg(inp,'h')[2])
    gw = {t:gross_weights(inp,t) for t in TIERS}
    stress = .20
    w_m = w['m']
    g_stress = w_m['a']*inp['g2_a_m']+w_m['b']*inp['g2_b_m']+w_m['c']*stress
    pe_stress = perpetual_pe(g_stress,forward_roe(inp,'m'),r)
    m_stress = to_hkd(inp,inp['ni_m']*pe_stress/disc(inp,'m')+window_cny(inp,'m'))
    tiered = {'a':(-.06,-.04,-.02),'b':(0.,.03,.05),'c':(0.,0.,.02)}
    pe_tier = [perpetual_pe(sum(w[t][leg]*tiered[leg][i] for leg in LEGS),forward_roe(inp,t),r)
               for i,t in enumerate(TIERS)]
    fx = inp['fx_hkdcny']
    roe_m = inp['ni_ttm']/inp['equity']
    tp_pe = inp['tp_street']*fx*inp['shares']/1e8/inp['ni_ttm']
    ni_ab = inp['ni_m']*(w_m['a']+w_m['b'])
    gas_framework = inp['ni_m']*w_m['c']*pe['m']/disc(inp,'m')+option_mv(inp,'m')
    option_sensitivity = {}
    for label,change in (('units_12',{'g50_units_h':12}),('margin_30',{'g50_gm_h':.30}),('no_g200',{'g200_units_h':0})):
        alt = dict(inp,**change)
        val = to_hkd(alt,option_mv(alt,'h'))
        option_sensitivity[label] = {'value':val,'adjusted_h':H+val}
    variant = {mode:variant_band(inp,mode) for mode in ('base','assign','addw')}
    g_sensitivity = {}
    for delta in (-.01,.01):
        vals = []
        for t in TIERS:
            gg = sum(w[t][leg]*(inp[f'g2_{leg}_{t}']+delta) for leg in LEGS)
            vals.append(to_hkd(inp,inp[f'ni_{t}']*perpetual_pe(gg,forward_roe(inp,t),r)/disc(inp,t)+window_cny(inp,t)))
        g_sensitivity[str(delta)] = vals
    def band_rf(dr):
        shifted = dict(inp,r_perp=r+dr)
        return tuple(anchor(shifted,t) for t in TIERS)
    if any(abs(x-y)>1e-9 for x,y in zip(band_rf(0),(L,M,H))):
        raise ValueError('rate sensitivity base differs from anchors')
    option = ({'value':v_opt,'weights':dict(zip('LMH',p_k)),'anchors':dict(zip('LMH',adj_band))}
              if v_opt > 0 and 0 <= p_m <= 1 and adj_band[0] < adj_band[1] < adj_band[2]
              else {'status':'unavailable','label':'自主燃机','anchors':None})
    result = {'ticker':'1072.HK','currency':'HKD',
            'valuation_as_of':None, 'historical_valuation_as_of': '2026-09-30',
            'framework_as_of':None, 'historical_research_as_of': '2026-11-05', 'historical_framework_as_of':'2026-11-05',
            'anchors':dict(zip('LMH',(L,M,H))),'candidate':None,
            'option':option,
            'w':w,'g':g,'pe':pe,'cap':cap,'over':over,'usdkw':usdkw,'L':L,'M':M,'H':H,'A':A,'B':B,
            'window': {t:to_hkd(inp,window_cny(inp,t)) for t in TIERS},
            'v_g50':v_g50,'v_g200':v_g200,'v_opt':v_opt,'p_m':p_m,'p_k':p_k,'adj_band':adj_band,
            'flat':flat,'mid_ratio':mid_ratio,'coords':coords,'inside':inside,'fxa':fxa,
            'ni200':ni200,'pe200':pe200,'mv200':mv200,'implied_all_h':implied_all_h,
            'k_h':k_h,'gross_h':gross_h,'gw':gw,'stress':stress,'g_stress':g_stress,
            'pe_stress':pe_stress,'m_stress':m_stress,'tiered':tiered,'pe_tier':pe_tier,
            'roe_m':roe_m,'tp_pe':tp_pe,'ni_ab':ni_ab,'gas_framework':gas_framework,
            'option_sensitivity':option_sensitivity,'variant':variant,'g_sensitivity':g_sensitivity,
            'a_share_anchors':dict(zip('LMH',(L*fx,M*fx,H*fx)))}
    if rate_inputs is not None:
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD',price_currency='HKD',price_unit='per_share',
            priced_r={'r_perp':r},band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs,base_anchors=(L,M,H)))
    return result


def calculate(context):
    if context['axes']['southbound']['role'] != 'reference':
        raise ValueError('southbound axis must be a reference')
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs':INPUTS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price':'HKD_PER_SHARE'}
    result['option']['value_unit'] = 'HKD_PER_SHARE'
    # The company ruler splits incumbent profits by the model's own weights;
    # the intervening distributable profit is a separate timing component.
    result['segments'] = {
        leg: {'unit':'HKD_PER_SHARE', 'values': {
            t.upper():(result['anchors'][t.upper()] - result['window'][t]) * result['w'][t][leg]
            for t in TIERS}} for leg in LEGS}
    result['segments']['window'] = {'unit':'HKD_PER_SHARE',
                                    'values':{t.upper():result['window'][t] for t in TIERS}}
    result['key_parameters'] = {
        'discount_rate': {'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_perp'])},
        'growth_rate': {'unit':'RATIO','values':{t.upper():result['g'][t] for t in TIERS}},
        'forward_return': {'unit':'RATIO','values':{t.upper():forward_roe(INPUTS,t) for t in TIERS}},
        'leg_growth_rate': {leg:{t.upper():INPUTS[f'g2_{leg}_{t}'] for t in TIERS} for leg in LEGS},
    }
    result['review_flags'] = ['historical_forecast_includes_unverified_g50_overlap',
                              'historical_consensus_mixed_dates',
                              'historical_capacity_and_capital_unverified']
    return result
