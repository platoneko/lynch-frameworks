#!/usr/bin/env python3
"""CCJ legacy valuation; source data and judgments are unchanged in migration.

Fuel profits are CAD millions and WEC/AP1000 values USD millions, shares millions.
The retained uranium-price shared axis remains a machine-checked dependency.
"""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES={'libraries':('gordon','inputs','partial_basis','rf_report'),
              'axes':{'uranium':'uranium_price'}}
HISTORICAL_PARTIAL_FINGERPRINT='183b291a8d0abcb4fd20ebc20f092eb1cb67938c5d83ed32172948bc3eafb9ff'

FORMULA_ID = "ccj_uranium_axis_fuel_plus_wec_ev_sotp_v1"
LISTING_CCY = "USD"
TOL = 0.05
TIERS = ("l", "m", "h")
YEARS = (2027, 2028, 2029, 2030)
# Cameco realized-vs-spot table, Q2-2026 MD&A (US$/lb; committed contracts as of 2026-06-30).
REALIZED_TABLE = {
    2027: {40: 46, 60: 58, 80: 69, 100: 74, 120: 76, 140: 78, 160: 80},
    2028: {40: 49, 60: 60, 80: 72, 100: 80, 120: 84, 140: 89, 160: 92},
    2029: {40: 53, 60: 62, 80: 75, 100: 85, 120: 91, 140: 96, 160: 101},
    2030: {40: 53, 60: 63, 80: 76, 100: 88, 120: 94, 140: 100, 160: 106},
}

# | A1 | 林奇：主类 `cyclical`（燃料循环利润随铀价起落：营业利润 2022 年 0.16 亿 → 2025 年 6.18 亿加元），次类 `fast_grower`（合同量与西屋新建） | active | 2022–2025 年报 | 分档形状 |
# | A2 | 归篮：燃料循环腿 → 篮 6 周期商品 13%（利润是铀价与转化费的函数，价格不由公司定）。CAPM 粗筛 9.6%（β 1.25 为 5 年周频对 SPY，r_f 中枢 4.0%，ERP 4.5%），差 3.4pp：铀价周期由签约周期与供给决定，与美股大盘不同步（2011–2018 铀价下行 7 年而美股上行），β 测不到行业风险。**③ 护栏**：M 档与 L 档均无同口径同等盈利月份——2007–2009 年合并调整后每股收益 1.49–1.67 加元中金矿（Centerra）与发电（Bruce Power）占 19%–47%，剔除后燃料循环每股收益 2007 年 1.14–1.25、2008 年 1.12–1.22、2009 年 0.80–0.96，均低于 L 档比较窗口（L 档会计口径 1.32–1.55 加元 ±12%），判「不适用」。披露：上述三年按燃料循环口径的市盈率（月度最低 / 中位 / 最高）2007 年 28–31 / 36–40 / 48–53，2008 年 12–13 / 28–30 / 36–40，2009 年 17–20 / 31–37 / 36–43——均为低于 L 档分子的盈利水平，倍数含回升预期，不构成同等盈利证据。同一构造按 10% 折现的对照带见 Outputs，不进锚点 | active | MD&A 2007–2025；yfinance CCO.TO 月度 | r_fuel |
# | A3 | 归篮：西屋核心腿 → 篮 4 常规经营 10%（燃料组件加工费与在运机组服务，收入不随铀价，非监管定价，不命中篮 1/2/3/5/7）；CAPM 9.6%，差 0.4pp | active | 2025 MD&A 西屋分部 | r_wec |
# | A4 | 铀价三档 70 / 95 / 120 美元，均为 regime（`_AXIS.uranium` §1） | active | 轴文件 | u_l / u_m / u_h |
# | A5 | 合同映射稳定：公司实现价表在现货 80 时 2027 年实现价 ≥ 65（2026-06-30 表为 69）。证伪：季报同格下移 > 10% | active | 2026 Q2 MD&A | 2027–2030 实现价 |
# | A6 | 自产：L / M 取 2026 年指引中值 2,050 万磅（Cameco 份额），H 取 2,240 万磅（McArthur River 1,800 万磅 × 69.8% + Cigar Lake 1,800 万磅 × 54.5%；2024 年实测 2,340 万磅）；交付 3,000 万磅。证伪：产量指引两年内再下调 > 10% | active | 2025 MD&A；2024 年报 | prod_* |
# | A7 | 单位成本 =〔自产 × 50.7 + 外购 × 0.8 × 轴价 × 汇率〕÷ 交付（加元/磅）。50.7 由 2026 年指引反推（单位成本中值 65.25、外购约 950 万磅 × 95 加元）；回测 2025 年 62.08 对实测 62.71（−1%） | active | 2025 / 2026 Q2 MD&A | c_prod / buy_ratio |
# | A8 | 燃料服务毛利固定于 2025 年 1.74 亿加元（不挂铀价轴） | active | 2025 财报分部附注 | fs_gp |
# | A9 | 留存去向：派息率约 17%（2025 每股 0.24 加元对调整后每股 1.44）。2023 年留存与增发用于收购西屋（D 桶，已完成）；2024 年净债由 12.17 亿降至 6.81 亿（A 桶，还收购贷款）；2025 年再降至 −2.18 亿（A + B 桶）。2018–2024 年资本开支低于折旧、固定资产净值由 52.3 亿降至 32.9 亿；2026–2028 年资本开支指引 4.9 亿–5.4 亿 / 4.0 亿–4.5 亿 / 3.5 亿–4.0 亿，高于折旧约 2.9 亿，用途为维持与产能替代（Cigar Lake 延寿至 2036、McArthur River 冻结站与新采区、Key Lake 与 Blind River 老化设施），无具名扩产决定 → 超出折旧部分作为长期维持成本从燃料腿利润中扣减（`xs_capex` 税后 0.8 亿加元/年）。形式：完整式，\(b = g_2/ROE\)；模型派息约 80%–93% 对实付约 17%，差额为 B 桶（堆现金 / 还债），视同派出打折 k = 0（B 桶默认） | active | 2015–2025 年报；2025 MD&A 资本开支分类表 | xs_capex / 形式 |
# | A10 | 杠杆门：Cameco 合并口径未触发（净现金 2.18 亿加元；利息 0.55 亿 / 营业利润 6.18 亿 = 9%）。西屋腿按「权益法被投资方自带债务」单独判：净债 45.78 亿 / 核心调整后 EBITDA 约 11.0 亿加元（100%）= 4.2 倍 > 3 → 触发，EV 口径构造；扣息口径对照见 Outputs | active | 2025 年报；2026 Q2 财报附注 | WEC 构造 |
# | A11 | 西屋核心（49%，美元）：调整后 EBITDA L 3.40 亿（约 2024 年实测）/ M 3.86 亿（2025 年剔除 Dukovany 一次性款）/ H 4.20 亿（2026 年指引上沿 4.3 亿附近）；维持性资本开支 1.00 亿（2026 年指引 0.9 亿–1.1 亿）；税率 25%（美国联邦 21% + 州税，推算）；收购摊销税盾现值 3.15 亿（每年摊销约 1.8 亿 × 25% × 年金系数 7.0，摊销额为推算）；净债 15.73 亿（45.78 亿加元 × 49% ÷ 1.4256）；ROIC 15.8%（剔除收购商誉与收购无形资产，宽口径，2026 年指引中值，推算）。永续 g：L 0 / M 2.5%（美元通胀，无同业锚）/ H 4%（自定：核心 EBITDA 2024→2025 增 12%，2024 年曾给五年 6%–10% 指引、2025 年撤回）。无卖方覆盖，已实现 EBITDA 年度数据点不足 4 个，不设增长窗口 | active | Cameco 2024–2025 年报权益法附注；2026 Q2 MD&A | wec_* |
# | A12 | 独立成交价护栏：2023-11 交割，Cameco 支付 21.36 亿美元取得 49%，交割后收到分配 2.695 亿（2025-02 0.49 亿、2025-10 1.715 亿、2026H1 0.49 亿），无追加出资 → 调整后成交价 18.665 亿。归属清单 = 西屋核心腿 + AP1000 期权。H：17.29 亿 + 36.75 亿 = 54.05 亿 ≥ 18.665 亿；M：11.49 亿 + 0.70 × 36.75 亿 = 37.24 亿 ≥ 18.665 亿 → 通过。仅看核心腿，M 比成交价低 38%：成交价含当时的新建前景（波兰 2022-11 选定 AP1000、乌克兰最多 9 台备忘录），本框架将其计入 \(V_{opt}\)。复核触发：西屋上市后核心业务的市场 EV/EBITDA 持续高于 10 倍 | active | Cameco 2023–2026 公告与附注 | 护栏 |
# | A13 | AP1000 份数（Cameco 49%）：L = 波兰 3 台（2026-09-23 总包主要商务条款谈妥，预计 FID t = 1）；M = L + 保加利亚 2（t = 2）+ 乌克兰 2（t = 3）+ V.C. Summer 2（t = 2）+ Fermi 4（t = 3）= 13 台；H = M + 美韩框架 6 台（2026-09-30，t = 3）= 19 台。纯政策目标（能源部贷款最多 10 台、商务部 800 亿伙伴关系、2030 年前开工 10 座）不计，与美韩 6 台可能重叠。单位经济：每台西屋收入 47.5 亿美元（Cameco 示意区间 40 亿–55 亿中点）、EBITDA 率 20%、建设 10 年均匀确认、投运后每台每年燃料与服务收入 2,650 万美元 × 20%、寿命 80 年；r = 西屋腿 10%；新建资本由业主承担，无未投资本扣减。美国政府分红参与权与认股权证未建模（分配超过 175 亿美元的部分在可见期内不会发生；认股权证只在上市时生效） | active | Cameco 2026 Q2 MD&A；Bechtel、Fermi 10-Q、Cameco 6-K 2026-09-30 | V_opt |
# | A14 | 共识核对（裁决顺序 ②-b）：2027 年调整后每股收益共识 2.59 加元（18 家，区间 1.85–4.10，yfinance as-of 2026-10-05）；本框架 2027 年燃料循环会计口径每股 L 1.32 / M 1.61 / H 1.78，加西屋会计贡献约 0.1–0.4，共识均值高于 H 档 2027 年读数 → H 已改为具名「市场基准世界」（铀 120、自产 2,240 万磅、西屋核心增长 4%）。剩余差额主要来自共识隐含的单位成本下降与销量（MarketScreener 2027 年并表息税前利润 11.10 亿对 2026 年 6.18 亿加元，转述），本桥未纳入。按「周期票的中枢分子」：铀长期价处于 1996 年以来高位，共识高于中枢不改 M，挂证伪触发器：2027 年公司指引单位成本 ≤ 63 加元/磅，或 2027 年燃料循环调整后净利润 ≥ 9.5 亿加元 → 回对话重做单位成本与产量桥 | active | yfinance；MarketScreener；美银 2026-08（Wisburg 摘要） | 分子桥 |
# | A15 | 桥回测：调整后净利润桥 `ane_a` / `ane_b` 由 2022、2024、2025 三年拟合；2025 年 −0%、2024 年 +1%（拟合样本内），2023 年 −19%（样本外，±20% 内）；2022 年偏差 −37%（当年税项回拨，不可比） | active | 2022–2025 年报 | ane_a / ane_b |
# | A16 | 2031 年起实现价 = 0.95 × 轴价（新签合同按当时市场价，留 5% 给上下限与折扣） | active | 推算；RBC 2026-06 转述的新合同上下限 70–80 / 150–160 | k_conv |
# | A17 | Inkai（40%，哈萨克斯坦）交付不中断：权益收益 = 1.59 亿 + 4.2 × (轴价 − 73.5)（2024 / 2025 两点斜率）。证伪：年度交付低于计划一半 | active | 2024–2025 财报 | inkai_* |
# | A18 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」）**：① **超额现金未触发单列**：净现金 2.18 亿加元（2025-12-31）÷ 归母权益 69.03 亿 ≈ 3% < 15%，按面值单列在锚点里的 0.35/股保留原结构；少数股东约 0，归母份额不动。② **增长期资金缺口 = 0**：2026–28 资本开支指引 4.9–5.4 / 4.0–4.5 / 3.5–4.0 亿，经营现金流付得起（A9）。③ **时点对齐（燃料腿）**：显式流从 E2027 起记 t = 1，算出的是 2027-01-01 的价值；估值基准日按框架现有的现金行日期 2025-12-31 → **τ = 1.0 年**，按 `r_fuel` 13% 折；**窗口可分配利润** = FY2026E 调整后 EPS 1.45 加元 × 股本 × 燃料占比 0.831 × (1 − b) ÷ 1.13^0.5，b = g2/ROE2031（框架自己滚燃料净资产用的留存）→ +0.64 / +0.71 / +0.74 USD/股。西屋核心腿用 2024 / 2025 / 2026 指引的当期 EBITDA、AP1000 期权已按 FID 年折回今天，均不适用。④ **稳态回报三段**：燃料腿分子由 `_AXIS.uranium` 桥出，属商品腿豁免，永续段沿用该档 ROE2031；西屋核心腿（不豁免，杠杆门触发，用 ROIC）前瞻 15.8%，稳态 = max(成熟同业穿越周期中位 16.9%（Curtiss-Wright 16.9%、Flowserve 9.6%、BWXT 59.0%，FY2017–25 均值；近 5 年收入复合增速均 ≤ 10%；Mirion 14.1% 剔除）, 兜底「有壁垒重资产」15%) = 16.9%，被前瞻 15.8% 封顶 → 不变。⑤ **一致性**：三档世界「铀长期 70 / 95 / 120」都是持续世界，ROE2031 与之同世界。⑥ 无打折 k | `active` | 2026 Q2 MD&A；yfinance 共识 2026-10-15；Longbridge 年报（同业） | `tau_fuel` / `ane26_ps` / `fuel_share`；M 14.98 → 14.31（−4.5%） |
# 原框架历史；迁移没有新增财务更新：
# （初建日不写条目。）
INPUTS = {
    # `_AXIS.uranium` L（US$/lb）; 来源：2026-10-06
    # `_AXIS.uranium` M; 来源：2026-10-06
    # `_AXIS.uranium` H; 来源：2026-10-06
    # 美元兑加元（yfinance `CAD=X`）; 来源：2026-10-05
    'fx': 1.4256,
    # 年末流通股（百万股）; 来源：2025-12-31
    'shares': 435.5,
    # 现金及短投 12.15 亿 − 总债务 9.96 亿（加元百万）; 来源：2025-12-31
    'net_cash': 218,
    # 年交付量（百万磅；2026 年承诺 29–32）; 来源：2026 Q2
    'deliv': 30.0,
    # 自产（Cameco 份额，百万磅；A6）; 来源：2026 Q2
    'prod_l': 20.5,
    # 同上; 来源：2026 Q2
    'prod_m': 20.5,
    # 市场基准世界自产（A6）; 来源：2024 实测 / 推算
    'prod_h': 22.4,
    # 自产单位成本（加元/磅，含折旧、权利金、维护；A7 反推）; 来源：2026 指引
    'c_prod': 50.7,
    # 外购价 ÷（现货 × 汇率）；2026 指引外购 95 加元对现货约 85 美元; 来源：2026 Q2
    'buy_ratio': 0.80,
    # 2031 起实现价 ÷ 轴价（A16）; 来源：推算
    'k_conv': 0.95,
    # 燃料服务毛利（加元百万；A8）; 来源：FY2025
    'fs_gp': 174,
    # Inkai 权益收益（加元百万）; 来源：FY2025
    'inkai_base': 159,
    # 2025 年现货均价（US$/lb）; 来源：FY2025
    'inkai_spot0': 73.5,
    # Inkai 权益收益对现货斜率（加元百万 / 美元）; 来源：2024–2025
    'inkai_slope': 4.2,
    # 燃料循环调整后净利润桥斜率（A15）; 来源：2022–2025 拟合
    'ane_a': 0.55,
    # 桥截距：总部、利息、勘探等（加元百万）; 来源：2022–2025 拟合
    'ane_b': 105,
    # 超出折旧的维持 / 产能替代资本开支，税后（加元百万/年；A9）; 来源：2026–2028 指引
    'xs_capex': 80,
    # 燃料循环经营净资产 = 归母权益 69.03 亿 − 西屋账面 26.72 亿 − 净现金 2.18 亿（加元百万）; 来源：2025-12-31
    'eq_fuel': 4013,
    # 篮 6 周期商品：燃料循环利润是铀价与转化费的函数（A2）; 来源：2026-10-06
    'r_fuel': 0.13,
    # 商品腿默认：美元通胀 2.5% + 铀长期实际价格漂移 ≈ 0（无同业锚）；cap = min(6%, 13% − 4%) = 6%; 来源：2026-10-06
    'g2_fuel': 0.025,
    # 时点对齐年数（A18）：燃料腿显式流 E2027 起记 t = 1，原值是 2027-01-01 的价值；估值基准日 = 现金行的资产负债表日 2025-12-31 → τ = 1.0，按 `r_fuel` 折; 来源：2026-10-16
    'tau_fuel': 1.0,
    # FY2026E 调整后每股收益（加元，yfinance 18 家均值）；窗口可分配利润的分子（A18）; 来源：2026-10-15
    'ane26_ps': 1.45156,
    # 燃料循环占调整后净利的比例 = 2025 燃料 ANE 521 ÷ 全公司 ANE 627（Q1–Q4 2025：70 + 308 + 32 + 217；2026 Q2 MD&A 季度表）；把共识换成燃料腿同口径（A18）; 来源：2025
    'fuel_share': 0.831,
    # 西屋核心调整后 EBITDA，49%（US$ 百万；A11）; 来源：FY2024
    'wec_ebitda_l': 340,
    # 同上; 来源：FY2025 剔除 Dukovany
    'wec_ebitda_m': 386,
    # 同上; 来源：2026 指引
    'wec_ebitda_h': 420,
    # 维持性资本开支，49%（US$ 百万）; 来源：2026 指引
    'wec_maint': 100,
    # 长期税率（推算）; 来源：2026-10-06
    'wec_tax': 0.25,
    # 收购摊销税盾现值，49%（US$ 百万，推算）; 来源：2026-10-06
    'wec_shield': 315,
    # 西屋净债 × 49%（US$ 百万）; 来源：2026-06-30
    'wec_nd': 1573,
    # 西屋财务费用，49%（US$ 百万；仅扣息口径对照用）; 来源：2026 指引
    'wec_int': 128,
    # 西屋 ROIC，剔除收购商誉与无形资产（A11）; 来源：2026 指引
    'roic_wec': 0.158,
    # 篮 4 常规经营：燃料组件加工费与在运机组服务，收入不随铀价（A3）; 来源：2026-10-06
    'r_wec': 0.10,
    # L 核心零增长; 来源：2026-10-06
    'g2_wec_l': 0.0,
    # M 美元通胀，无同业锚; 来源：2026-10-06
    'g2_wec_m': 0.025,
    # H 自定（A11）; 来源：2026-10-06
    'g2_wec_h': 0.04,
    # 每台 AP1000 西屋收入（US$ 百万；A13）; 来源：2026 Q2
    'ap_rev': 4750,
    # 新建 EBITDA 率; 来源：2026 Q2
    'ap_margin': 0.20,
    # 建设期（年）; 来源：2026 Q2
    'ap_years': 10,
    # 投运后每台每年燃料与服务收入（US$ 百万）; 来源：2026 Q2
    'ap_om_rev': 26.5,
    # 核心业务利润率; 来源：2026 Q2
    'ap_om_margin': 0.20,
    # 机组寿命（年）; 来源：2026 Q2
    'ap_om_life': 80,
    # Cameco 持股比例; 来源：2026-10-06
    'ap_own': 0.49,
    # 波兰 Lubiatowo-Kopalino; 来源：2026-09-23
    'n_pol': 3,
    # 保加利亚 Kozloduy 7/8; 来源：2026-05
    'n_bul': 2,
    # 乌克兰 Khmelnytskyi 5/6; 来源：FY2025 AIF
    'n_ukr': 2,
    # 美国 V.C. Summer 2/3; 来源：2026 Q2
    'n_vcs': 2,
    # 美国 Fermi America; 来源：2026 Q2 10-Q
    'n_fermi': 4,
    # 美韩框架; 来源：2026-09-30
    'n_kor': 6,
    # 预计 FID 距今年数; 来源：推算
    't_pol': 1,
    # 同上; 来源：推算
    't_bul': 2,
    # 同上; 来源：推算
    't_ukr': 3,
    # 同上; 来源：推算
    't_vcs': 2,
    # 同上; 来源：推算
    't_fermi': 3,
    # 同上; 来源：推算
    't_kor': 3,
    # Cameco 为西屋 49% 支付的对价（US$ 百万）; 来源：2023-11-07
    'deal_paid': 2136,
    # 交割后收到的西屋分配累计（US$ 百万）; 来源：2026-06-30
    'deal_dist': 269.5,
}
BASKETS = {"r_fuel": 6, "r_wec": 4}
REQUIRED = frozenset(INPUTS)|{'u_l','u_m','u_h'}

def interp(table: dict[int, float], x: float) -> float:
    ks = sorted(table)
    if not ks[0] <= x <= ks[-1]:
        raise ValueError(f"price {x} outside the company table")
    for a, b in zip(ks, ks[1:]):
        if a <= x <= b:
            return table[a] + (table[b] - table[a]) * (x - a) / (b - a)
    raise AssertionError


def unit_cost(inp: dict, price: float, prod: float) -> float:
    buy = (inp["deliv"] - prod) * inp["buy_ratio"] * price * inp["fx"]
    return (prod * inp["c_prod"] + buy) / inp["deliv"]


def fuel_ane(inp: dict, price: float, prod: float, realized_usd: float) -> float:
    ugp = inp["deliv"] * (realized_usd * inp["fx"] - unit_cost(inp, price, prod))
    inkai = inp["inkai_base"] + inp["inkai_slope"] * (price - inp["inkai_spot0"])
    return inp["ane_a"] * (ugp + inp["fs_gp"] + inkai) - inp["ane_b"] - inp["xs_capex"]


def fuel_leg(inp: dict, t: str, r_shift: float = 0.0) -> dict:
    price, prod = inp[f"u_{t}"], inp[f"prod_{t}"]
    r, g = inp["r_fuel"] + r_shift, inp["g2_fuel"]
    E = {y: fuel_ane(inp, price, prod, interp(REALIZED_TABLE[y], price)) for y in YEARS}
    E[2031] = fuel_ane(inp, price, prod, inp["k_conv"] * price)
    # fuel equity rolled to 2031 with the model retention b = g/ROE (fixed point)
    eq = inp["eq_fuel"]
    for _ in range(50):
        roe = E[2031] / eq
        b = g / roe
        eq_new = inp["eq_fuel"] + b * sum(E[y] for y in YEARS)
        if abs(eq_new - eq) < 1e-6:
            break
        eq = eq_new
    roe = E[2031] / eq
    pe = perpetual_pe(g, roe, r)
    payout = 1 - g / roe
    pv_cad = sum(payout * E[y] / (1 + r) ** (i + 1) for i, y in enumerate(YEARS)) + pe * E[2031] / (1 + r) ** len(YEARS)
    # Time alignment (valuation-rules「经营价值与超额现金」③): pv_cad is the value at t_n = 2027-01-01
    # (E2027 at t = 1); discount tau to the cash balance-sheet date and add the window's distributable
    # fuel-cycle profit (FY2026 consensus ANE x fuel share x (1 - b), b = g2/ROE2031) at tau/2.
    tau = inp["tau_fuel"]
    window_cad = inp["ane26_ps"] * inp["shares"] * inp["fuel_share"] * max(payout, 0.0) / (1 + r) ** (tau / 2)
    pv_today = pv_cad / (1 + r) ** tau + window_cad
    return {"E": E, "roe": roe, "pe": pe, "payout": payout, "eq31": eq, "window_cad": window_cad,
            "pv_tn": pv_cad / inp["fx"] / inp["shares"],
            "ps": pv_today / inp["fx"] / inp["shares"]}


def wec_leg(inp: dict, t: str, r_shift: float = 0.0) -> dict:
    r, g = inp["r_wec"] + r_shift, inp[f"g2_wec_{t}"]
    e = inp[f"wec_ebitda_{t}"]
    pe = perpetual_pe(g, inp["roic_wec"], r)
    nopat = (e - inp["wec_maint"]) * (1 - inp["wec_tax"])
    ev = nopat * pe + inp["wec_shield"]
    eq = ev - inp["wec_nd"]
    levered = (e - inp["wec_maint"] - inp["wec_int"]) * (1 - inp["wec_tax"]) * pe + inp["wec_shield"]
    return {"pe": pe, "nopat": nopat, "ev": ev, "eq": eq, "ps": eq / inp["shares"],
            "levered": levered, "gap": levered - eq}


def ap_unit_pv(inp: dict, fid_t: float, r: float) -> float:
    """US$ mn PV at t0 of one AP1000 unit to Cameco (49% of WEC)."""
    own, tax = inp["ap_own"], inp["wec_tax"]
    n = int(inp["ap_years"])
    build = inp["ap_rev"] * inp["ap_margin"] * (1 - tax) * own / n
    pv_build = sum(build / (1 + r) ** (i + 1) for i in range(n))
    om = inp["ap_om_rev"] * inp["ap_om_margin"] * (1 - tax) * own
    life = inp["ap_om_life"]
    pv_om = om / r * (1 - (1 + r) ** -life) / (1 + r) ** n
    return (pv_build + pv_om) / (1 + r) ** (fid_t - 1)


PROJECTS = {
    "l": ("pol",),
    "m": ("pol", "bul", "ukr", "vcs", "fermi"),
    "h": ("pol", "bul", "ukr", "vcs", "fermi", "kor"),
}


def v_opt(inp: dict, t: str) -> float:
    r = inp["r_wec"]
    return sum(inp[f"n_{p}"] * ap_unit_pv(inp, inp[f"t_{p}"], r) for p in PROJECTS[t]) / inp["shares"]


def anchors(inp: dict, r_shift: float = 0.0) -> tuple[float, float, float]:
    cash = inp["net_cash"] / inp["fx"] / inp["shares"]
    return tuple(fuel_leg(inp, t, r_shift)["ps"] + wec_leg(inp, t, r_shift)["ps"] + cash for t in TIERS)


def bridge_backtest(inp: dict) -> list[str]:
    """valuation-rules「桥 MUST 复现实测年」: own segment inputs → fuel ANE, ±20%."""
    errors = []
    # (year, uranium GP, FS GP, Inkai equity, fuel ANE actual) — MD&A 2023–2025; fuel ANE = ANE − WEC ANE
    rows = [(2025, 803, 173.8, 158.9, 521), (2024, 681, 105.9, 207.6, 438), (2023, 444, 124, 178.8, 377)]
    for y, ugp, fs, ink, act in rows:
        est = inp["ane_a"] * (ugp + fs + ink) - inp["ane_b"]
        dev = est / act - 1
        if abs(dev) > 0.20:
            errors.append(f"bridge {y} off by {dev:+.0%}")
    # unit-cost back-test: 2025 (prod 21.0 / deliv 33.0, purchase price 82 CAD)
    uc25 = (21.0 * inp["c_prod"] + 12.0 * 82.0) / 33.0
    if abs(uc25 / 62.71 - 1) > 0.20:
        errors.append("unit cost back-test off")
    return errors


def evaluate(inp: dict[str, float],rate_inputs=None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    baskets = BASKETS
    errors += check_r(inp["r_fuel"], "r_fuel", baskets.get("r_fuel"))
    errors += check_r(inp["r_wec"], "r_wec", baskets.get("r_wec"))
    errors += check_g_cap(inp["g2_fuel"], inp["r_fuel"], "g2_fuel")
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_wec_{t}"], inp["r_wec"], f"g2_wec_{t}")
    bridge_warnings=bridge_backtest(inp)
    if errors:
        raise ValueError("; ".join(errors))

    F = {t: fuel_leg(inp, t) for t in TIERS}
    W = {t: wec_leg(inp, t) for t in TIERS}
    cash = inp["net_cash"] / inp["fx"] / inp["shares"]
    L, M, H = anchors(inp)
    A, B = (L + M) / 2, (M + H) / 2
    errors += ladder("anchors", L, M, H)
    errors += ladder("fuel E2031", *(F[t]["E"][2031] for t in TIERS))

    # flat-multiple ladder (construction §2c): fuel PE and WEC PE held at M
    flat = tuple(
        (F[t]["ps"] * F["m"]["pe"] / F[t]["pe"]) + (W[t]["nopat"] * W["m"]["pe"] + inp["wec_shield"] - inp["wec_nd"]) / inp["shares"] + cash
        for t in TIERS)
    errors += ladder("flat-multiple", *flat)

    # 独立成交价护栏 (equity basis, 49%, US$ mn)
    deal = inp["deal_paid"] - inp["deal_dist"]
    deal_values = {}
    option={'status':'unavailable','label':'AP1000项目','anchors':None}
    V=p=band3=None
    try:
        require_whole_years(inp,('ap_years',))
        if inp['ap_years'] <= 0 or inp['ap_om_life'] <= 0:
            raise ValueError('project construction and service life must be positive')
        V=v_opt(inp,'h')
        values=tuple(v_opt(inp,t) for t in TIERS)
        band3=tuple(base+v for base,v in zip((L,M,H),values))
        if not all(math.isfinite(v) for v in (V,*values,*band3)) or V<=0 or not 0<=band3[0]<band3[1]<band3[2]:
            raise ValueError('project value or adjusted band invalid')
        p=tuple(v/V for v in values)
        option={'value':V,'weights':dict(zip('LMH',p)),'anchors':dict(zip('LMH',band3))}
        deal_values={t:W[t]['eq']+pk*V*inp['shares'] for t,pk in (('h',1.),('m',p[1]))}
    except (ValueError,ZeroDivisionError,OverflowError):
        V=p=band3=None

    # 10% contrast (fuel leg at 篮 4, disclosure only)
    contrast = tuple(fuel_leg(dict(inp, r_fuel=0.10), t)["ps"] + W[t]["ps"] + cash for t in TIERS)
    def band_rf(dr: float) -> tuple[float, float, float]:
        return anchors(inp, dr)

    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: dr = 0 does not reproduce L/M/H")
    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    review_flags=['historical_mixed_financial_dates','historical_uranium_contract_and_project_assumptions',
                  'historical_government_rights_unmodelled']
    if bridge_warnings:
        review_flags.append('historical_fuel_bridge_backtest_needs_review')
    if deal_values and deal_values['h']<deal:
        review_flags.append('historical_westinghouse_transaction_reference_difference')
    growth=[]
    for d in (-.01,.01):
        try:
            values=[fuel_leg(dict(inp,g2_fuel=inp['g2_fuel']+d),t)['ps']+W[t]['ps']+cash for t in TIERS]
            growth.append(values if all(math.isfinite(v) for v in values) else None)
        except (ValueError,ZeroDivisionError,OverflowError):
            growth.append(None)
    result = {
        "ticker": "CCJ.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2025-12-31',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of':'2026-10-16',
        "anchors": band((L, M, H)), "candidate": None,
        "option": option, 'review_flags':review_flags,
        "cut_points": [A, B], "fuel": F, "westinghouse": W, "cash": cash,
        "flat": flat, "deal": deal, "deal_values": deal_values, "contrast": contrast,
        "fuel_eps_2027": band([(F[t]["E"][2027] + inp["xs_capex"]) / inp["shares"] for t in TIERS]),
        "growth": growth,
        "parameters": {"fuel_discount": inp["r_fuel"], "fuel_growth": inp["g2_fuel"],
                       "fuel_forward": band([F[t]["roe"] for t in TIERS]),
                       "wec_discount": inp["r_wec"], "wec_growth": band([inp[f"g2_wec_{t}"] for t in TIERS]),
                       "wec_forward": inp["roic_wec"]},
    }
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',
            priced_r={'r_fuel':inp['r_fuel'],'r_wec':inp['r_wec']},band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs,base_anchors=(L,M,H)))
    return result


def calculate(context):
    rungs=context['axes']['uranium']['rungs']
    selected={f'u_{t}':rungs[t.upper()] for t in TIERS}
    result=evaluate({**INPUTS,**selected},context.get('rate_inputs'))
    result['basis_changed']=None
    optional={k for k in INPUTS if k.startswith(('ap_','n_','t_'))}
    if any(not math.isfinite(INPUTS[k]) for k in optional):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'uranium':selected,'realized_table':REALIZED_TABLE,'projects':PROJECTS,
             'years':YEARS},HISTORICAL_PARTIAL_FINGERPRINT)
    result['units']={'price':'USD_PER_SHARE'}
    if result['option'] is not None:
        result['option']['value_unit']='USD_PER_SHARE'
    result['segments']={
        'fuel':{'unit':'USD_PER_SHARE','values':{t.upper():result['fuel'][t]['ps'] for t in TIERS}},
        'westinghouse':{'unit':'USD_PER_SHARE','values':{t.upper():result['westinghouse'][t]['ps'] for t in TIERS}},
        'cash':{'unit':'USD_PER_SHARE','values':dict.fromkeys('LMH',result['cash'])}}
    result['key_parameters']={
        'fuel_discount_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_fuel'])},
        'fuel_growth_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g2_fuel'])},
        'fuel_forward_return':{'unit':'RATIO','values':{t.upper():result['fuel'][t]['roe'] for t in TIERS}},
        'westinghouse_discount_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_wec'])},
        'westinghouse_growth_rate':{'unit':'RATIO','values':{t.upper():INPUTS[f'g2_wec_{t}'] for t in TIERS}},
        'westinghouse_forward_return':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['roic_wec'])}}
    return result
