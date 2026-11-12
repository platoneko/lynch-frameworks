#!/usr/bin/env python3
"""TER legacy valuation; migration does not update financial assumptions.

Amounts are USD millions, shares are absolute counts and output is USD/share.
Technoprobe fair value was estimated from a historical quarter-end price, pending 10-Q.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, g_cap, implied_g, payout
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'),
                'axes': {'capex': 'ai_capex', 'peer': 'burn_in_test'}}

FORMULA_ID = "ter_fy27_cons_gordon_opeq_v1"
LISTING_CCY = "USD"
TOL = 0.05
MILLION = 1e6
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")
CANDIDATE_TIERS = ("M", "H")
# A20: announced 2026-10-12, unclosed at the old research date.  Historical
# comparison only: 2,234,887 shares at the 2026-10-29 FORM close of $100.03,
# purchased for $300M cash; neither the scenario nor tax is in base anchors.
FORM_SHARES = 2_234_887
FORM_PRICE = 100.03
FORM_CASH_M = 300.0
# | A1 | 整公司单一尺，**不拆 SOTP**：半导体测试 1H26 占收入 85%、占分部税前利润约 98%（895.4 / (895.4 + 22.7 − 3.5)）；产品测试与机器人各 <10% 收入、利润近零，卖方无分部估值、共识不分部；分部启发式命中 1 条（机器人在亏）< 2。机器人亏损已在共识分子内，不单开期权或负值腿。2026Q3：半导体测试 1,072 / 1,306 = 82%，机器人转为单季盈利，拆分理由更弱 | active | 2026Q2 10-Q 分部附注（Segment Information）；FY2025 10-K；2026Q3 财报 | 主尺形态 |
# | A2 | **分子 = FY27 十六家共识 EPS 三点 9.00 / 11.430 / 14.187（裁决顺序 ②）**：2026-10-28 读数，尚未按 Q3 财报修正（FY26 年度共识 9.117 仍含财报前的 Q3 预期，可证）；较 2026-10-07 的十八家 9.00 / 11.652 / 16.53，均值 −1.9%，上沿换人（16.53 那家不在样本内）→ H 分子 −14%，是样本变化不是基本面；修正落地后重拉。FY27 是最远的 ≥2 家且带区间的共识年；FY28 只有 MarketScreener 点值（家数不明）→ 不作分子、不开 g1，进候选带（A13）。FY27 的 Gordon 值按时点对齐折回 0.5 年（A18）。**升级门槛**：FY28 出现 ≥2 家点估计 → 开 g1（n=1，框架纠正）；出现 ≥2 家带区间 → 分子换 FY28（折一年）。**证伪触发器**：两个季度内 FY27 共识均值下修 > 20% | active | yfinance `earnings_estimate` 2026-10-07（FY26 16 家、FY27 18 家）、2026-10-28（FY27 16 家）；MarketScreener finances 2026-10-07 | `eps_fy27_l/m/h` |
# | A3 | **`cyclical` 的 M 取前瞻共识而非历史周期中枢**：TER 是需求周期型制造（价格自定，周期来自客户产品导入与扩产），按 valuation-rules「周期票的中枢分子」适用范围（2026-10-04）M / H 取共识、周期风险由 L 与压力坐标承担；另有资产基数变动：计算测试份额从跟随者进入英伟达与两家超大规模云厂商、测试占资本开支从 4% 升到约 8%、2026Q1 起季度收入稳在 12.8 亿以上（2021 峰值年全年 37.0 亿）。按 2016–25 整轮周期 non-GAAP EPS 均值（约 3.6）取中枢，M 不到 100 美元。**复核触发**：FY27 共识均值跌到 FY26 实际以下，或行业下行期季度 non-GAAP EPS 跌回 1 美元以下 → 回对话重审中枢。2026Q3 加强：前三季 non-GAAP EPS 7.32 已超过上市以来任何完整年度，FY26 约 9.35 < FY27 均值 11.43，未触发；测试占资本开支 2025 年 6.4% → 2026 年前 8 个月 8.1% | active | 2016–2025 各年第四季度财报 non-GAAP EPS；2026Q2 / Q3 业绩会；SEC companyfacts | M 的分子；表2 `conservative` / `deep_discount` |
# | A4 | **调整后 EPS 含 SBC，不打折**：公司 non-GAAP 只剔「acquired intangible assets amortization, restructuring and other, ERP related expenses, inventory step-up, pension mark-to-market…」与 Technoprobe 投资基差摊销，SBC 留在里面（2026Q2 GAAP 2.38 vs non-GAAP 2.47，差 0.09 = 收购摊销 0.03 + 基差摊销约 0.05 + 重组 0.02 − 税 0.01）。收购摊销（约 20M / 年）是 MultiLane / Quantifi 等小额收购的会计项，不扣（扣则三档约 −0.11/股 × 倍数 ≈ −2.5）。2026Q3 复核：GAAP 2.17 vs non-GAAP 2.29，调整项仅基差摊销 0.05、收购摊销 0.03、ERP 0.02、重组 0.01，SBC 21.7M 未剔 | active | 2026Q2 / Q3 财报（8-K EX-99.1）non-GAAP 定义段与调节表 | 分子口径 |
# | A5 | **净现金闭合项**：2026-09-27 现金 460.7 + 有价证券 5.8（流动）+ 158.3（长期）= 624.9M，减经营租赁负债 17.1 + 120.1 = 137.1M → 487.8M = 3.10/股；有息债务 0。利息收入 3.182M / 季（2026Q2 10-Q；Q3 单项待 10-Q）× 4 × (1 − 15%) = 0.069/股从分子剔除。养老金负债 152.9M 是经营性负债、留在经营权益内 | active | 2026Q2 10-Q 利息收入行；2026Q3 财报资产负债表；有效税率 Q3 14.8% | `net_cash`、`int_q` |
# | A6 | **Technoprobe 股权按披露公允值扣增值税计入**：2026Q3 10-Q 未出，公允值按季末股价估算——Q2 披露 2,457.9M ÷（2026-06-26 收盘 €33.04 × 1.1362）= 6,547.6 万股 × 2026-09-25 收盘 €30.14 × 1.1375 = 2,244.7M；2,244.7 − (2,244.7 − 518.6) × 21% = 1,882.2M = 11.95/股（Q2 版 13.00）。其股价到 2026-10-28 收盘 €26.28，较季末再 −13%，下季 10-Q 会反映。non-GAAP 权益法收益 = GAAP 3.281M + 基差摊销 7.6M = 10.88M / 季（Q2 5.94M）→ 0.276/股从分子剔除。不计入时三档 190.73 / 250.05 / 312.37；按税前公允值 204.98 / 264.30 / 326.63（只披露）。**每季复核**：10-Q Note「Equity Method Investment」更新公允值即改 `tp_fv`（本季估算值届时替换）；减持或出售 → 按实际税后所得改为净现金 | active | 2026Q2 10-Q Note F（公允值 2,457.9M、2024-05-27 入股 524.1M）；2026Q3 财报（账面 518.559M、权益法收益与摊销）；yfinance TPRO.MI / EURUSD 收盘 | `tp_fv`、`tp_eq_q` |
# | A7 | **g2 = 6%（测试设备同业反解中位截顶）**：同一把 Gordon 尺（r 10%）、2026-10-02 收盘 yfinance 前瞻 PE × 前瞻 ROE 反解（老化 / SLT 同业尺轴 §2 的横截面读数，剔除本票自身）：爱德万 7.88% / 京元电子 6.09% / 致茂 7.17% / FormFactor 8.24%，中位 **7.53%** > \(G_{cap}\)(10%) = 6% → 截到 6%；Cohu 前瞻 ROE 11.3% 落病态区已剔。同业全部留存（派息 0–53%）且盈利上行 → 留存分支；同世界门：本票 FY26 → FY27 共识 EPS +28% 上行，g2 ≥ 0 可用。同业 `FORM.US` 同取 6%（测试设备簇） | active | `frameworks/axes/burn-in-test.md` §2（2026-10-02）；`FORM.US` A7 | `g2`、`g_peer_median` |
# | A8 | 归篮：整公司 → **篮 4 常规经营 10%**——测试机价格公司自定、盈利是客户产品导入与扩产周期的函数，不是商品价函数（非篮 6）；2025 年最大直接客户 19%、两家指定客户 12% / 10%、前五大 44%，未达篮 7（单一 ≥50% 或前两大 ≥70%）。CAPM 粗筛：4.0% + β 1.75（5 年月度 vs 标普 500）× 4.5% = 11.9%，与篮子差 1.9pp < 3pp。周期、客户集中、AI 叙事都不抬 r（valuation-rules 2026-09-28 / 10-03），风险进 L 分子与压力坐标。**证伪**：单一客户 ≥50% 或前两大 ≥70% → 改篮 7 | active | FY2025 10-K 客户集中度段；yfinance β 1.747（2026-10-07） | `r_perp` |
# | A9 | **ROE 分母 = FY27 年初经营权益**：2026-09-27 账面 3,687.9M − 净现金 487.8M − Technoprobe 账面 518.6M = 2,681.6M（17.03/股），按增长所需留存 \(b_1=g_2/ROE\) 滚过 FY26 未入账季度（`q_left` = 1）的核心 EPS（9.352 − 前三季实际 7.32 − 一季剔除项 0.086 = 1.95/股）→ 17.26 / 17.21 / 17.17。经营权益含商誉 663.8M 与收购无形资产 96.7M（收购是生意的一部分，不剔）。ROE 50.2% / 64.4% / 80.6% 全在单调区深处，倍数对 ROE 已不敏感（\(1-g/ROE\) ∈ 0.88–0.93）；用含现金与 Technoprobe 的账面压 ROE 是把同一笔资产罚两次（同 `FORM.US` A6 / `AEHR.US` A15） | active | 2026Q3 财报资产负债表；yfinance FY26 Q4 共识 2026-10-28；2026Q1 / Q2 / Q3 non-GAAP EPS 2.56 / 2.47 / 2.29 | `equity`、`eps_fy26_m`、`eps_ytd_26`、`q_left` |
# | A10 | **③ 带测试不适用**：M 档核心 EPS 11.09 从未实测——同等盈利月份 0 个。**L 档开始有同等盈利**：2026Q3 财报后 TTM non-GAAP EPS = 1.80 + 2.56 + 2.47 + 2.29 = 9.12（剔两项后约 8.8），首次达到 L 分子 9.00（核心 8.66）；截至 2026-10-28 不足 1 个月，样本不够，带测试仍不适用；下一季（2026Q4 财报后）按同等盈利月份重做 L 档的带测试。披露（valuation-rules 2026-10-06）：同口径 TTM EPS 最接近 L 档的三个年度——2026 年（TTM 3.97 → 7.68）non-GAAP TTM PE 月度 41.6 / 67.3 / 105.3（最低 / 中位 / 最高）、2021 年（TTM 约 4.6 → 6.0）20.2 / 26.4 / 32.0、2022 年（6.0 → 4.25）13.9 / 18.4 / 29.1，均为低于 L 档分子的盈利水平，倍数含回升预期，不构成同等盈利证据。生成倍数 22.0–22.8× 落在 2021 / 2022 年区间内。带有效性：无可比。纠正对账门坐标见 Outputs | active | `_local` 价格与 TTM EPS 序列（yfinance + 各季财报，2016-01 → 2026-10-06）；2026Q3 财报 | ③ 披露行 |
# | A11 | **留存去向审计 + 杠杆门**：2021–25 年留存（NI − 分红）2,919M，去向：回购 2,650M（91%）、收购与 Technoprobe 入股 681M、资本开支超折旧 283M，缺口由现金 1,500 → 448M 补；回购与分红是分配，资本开支连年高于折旧且无终点 → E 桶（稳态增长 capex，规模小）→ **完整式**，\(b=g_2/ROE\)。近三年（2023–25）分红 + 回购 ÷ 净利 = 98.3%。k 来源层级 ①：近 5–7 年唯一单笔 ≥ 权益 5% 的交易是 Technoprobe（524.1M → 公允值 2,457.9M，回报远高于 r）→ k = 0；Robotics 两笔大收购（2015 UR、2018 MiR）在 7 年窗口外，其亏损已在共识分子内。周期票 \(k_H\ge k_M\ge k_L\)：H 与 M 的差来自共识区间，不是价格轴，①b 不适用。**杠杆门未触发**：净债为负（净现金 487.8M）、FY2025 利息 / EBIT ≈ 0。2026 年读数（只记，年报时按窗口重算）：前三季分红 + 回购 234.5M ÷ 归母净利 1,115.8M = 21%，远低于近三年 98%；资本开支 241.8M ≈ 折旧 90.3M 的 2.7 倍，库存与预付款扩张——扩产期留存升高，FY2026 10-K 时复核分桶与 `payout_3y` | active | SEC companyfacts 2016–2025；2026Q2 10-Q；2026Q3 财报现金流量表 | 倍数形式、`k_*`、`payout_3y` |
# | A12 | **\(V_{opt}\) = 0**：① 管理层目标模型（收入 60 亿、调整后 EPS 9.50–11，不锚年份）已被 FY27 共识均值（收入 62.6 亿、EPS 11.65）覆盖，无「目标 − 共识已含」的份数；② CPO 测试「2027 约 2 亿、2028 年 3–7 亿美元」、ATE 市场「≥200 亿美元」是市场规模，按规则 **MUST NOT** TAM × 份额；③ 商用 GPU 首单约 5,000 万美元（2026）与第二家云厂商认证已在 FY27 共识的高端。**升级门槛**：2026 年第四季度业绩会（2027-01，2026Q3 业绩会确认）公布的新目标模型给出具名年份的收入 / EPS 且高于 FY27 共识上沿 → 超出部分作期权份数（单位经济取对齐年份共识核心净利率，兑现年估值折回） | active | 2026Q2 / Q3 业绩会；2025Q4 业绩会（2026-02-03） | `V_opt` |
# | A13 | **候选带（FY28 MarketScreener 单源）**：同一 `formula_id`，只把「FY28 待补」换成 MarketScreener 点值：g1 = 15.58 ÷ 11.74 − 1 = 32.7%、n = 1，**只在 M / H 档启用**（L 世界是消化年、不背过渡增长，L′ = L）；账面按 \(b_1=g_1/ROE\) 滚。**升级门槛**：FY28 出现 ≥2 家点估计（yfinance / Zacks / Visible Alpha 任一可见）→ 换成两家均值开 g1 升为底牌；≥2 家带区间 → 分子换 FY28；新目标模型（A12）先到且给出具名年份 → 按 A12 处理，本行删除 | active | MarketScreener finances 2026-10-07（FY27 EPS 11.74 / FY28 15.58，家数与口径未注明） | 候选带 |
# | A14 | **卖方 TP 只作交叉**：17 家均值 446.47、中位 450、350–550（Longbridge / S&P 2026-10-01）；2026-10-28 Longbridge 均值 445.47、350–550，LSEG 18 家中位 420（2026-10-27）；Argus 382（2026-10-21 下调）、UBS 500 → 485（2026-10-20）；美银 525 → 450（2026-06 / 08，口径待核）、高盛 465（2026-09-10）、Cantor 550、摩根大通 465、大摩 397（中性）、Baird 420（2026-08-21 下调中性）。各家倍数 × 年份待补（智堡只有摘要）。同一把尺上 TP 350 / 450 / 550 隐含的永续 g 见 Outputs 交叉备注；不反解进倍数 | active | Longbridge `institution-rating` 2026-10-01；智堡 93460 / 99052 / 104957 / 105044 | 交叉备注 |
# | A15 | **压力坐标：上一轮幅度的深度下行**（不是锚点）：2021 → 2023 年 non-GAAP EPS 比 0.49 施加到 FY26 9.35 → 4.58（核心 4.24）× \(1/r\) + 闭合项 = 57.38；此即 `deep_discount` 档「测试台阶整体塌回上一轮下行」的量级 | active | 2022-01-27 / 2024-01-31 财报 | 表2 `deep_discount` |
# | A16 | **计算测试订单在 2027 上半年回来**（2026Q2 管理层原话）：2026Q3 业绩会改口——计算「在 Q3 见底、Q4 开始回升」，第一家超大规模客户下一轮大放量在「2027 年年中」，第二家「2027 下半年」产能采购，定制 AI 芯片项目「更偏下半年」；由存储（Q3 3.01 亿创纪录、HBM 是 2027 年的「明星」）补位，管理层称 2027 年每个季度同比增长、2027Q1 高于 2026Q4。Q4 指引 12.5–13.5 亿 > 11 亿证伪线；放量落在 2027 下半年而非「以后」，**未证伪、削弱**：L 档「计算空档延续到下半年」的世界在计算测试上已部分成真，FY27 共识上半年季度（2027Q1 2.48 高于 Q4 指引中值 2.10 约 18%）先受下修压力，按 A2 触发器复核。**证伪**：2026Q4 实际或 2027Q1 指引低于 11 亿，或管理层把计算放量推到 2028 | weakened | 2026Q2 / Q3 业绩会（Investing.com 文字稿 2026-10-28）；2026Q3 财报；yfinance 季度共识 2026-10-28 | L 档场景 |
# | A17 | **机器人 2026 年盈亏平衡**：两轮重组（2025Q1 约 150 人、2025Q4 约 200 人）后分部亏损从 2025 年 −99.4M 收窄到 2026Q1 / Q2 −1.0 / −2.6M，2026Q3 收入 96M、单季盈利（财报与业绩会原话，分部利润数待 10-Q），电子与半导体客户成最大终端市场。**证伪**：2026 下半年分部亏损重回 −15M / 季以上 → 回对话评估是否单拆负值腿 | confirmed | 2026Q1 / Q2 10-Q 分部表；Robot Report 2026-07-30；2026Q3 财报 | A1 拆分判断 |
# | A18 | **超额现金、归母份额与时点对齐**（valuation-rules「经营价值与超额现金」① / ③）：扩展口径净现金 487.8M = 归母权益 13.2% < 15% 门槛，不另拆超额现金；现框架已把净现金按面值单列、利息已从分子剔除，按「保留原结构」不动。增长期资金缺口 0（2026Q3 资本开支 86.3M、经营现金流 313.6M）。归母比例 = 3,687.9 ÷ (3,687.9 + 可赎回少数股东 49.1) = **0.9869**，乘在净现金行与窗口利润上。时点对齐：τ = 2026-09-27 → 2027-01-01 = **0.25 年**（按实际月数），Gordon 值 ÷ 1.1^0.25；窗口可分配利润 = FY26 Q4 未入账核心 EPS 1.95 × (1 − b1) × 0.9869，按 τ/2 折今 = 1.67 / 1.72 / 1.76。原框架无折回，无可还原 | active | 2026Q3 财报（可赎回少数股东权益 49.065M、现金流量表）；框架纠正试算 2026-10-16 | `minority`、`tau`、`q_left` |
# | A19 | **稳态回报三段**（valuation-rules「经营价值与超额现金」②）：可见年 FY27 用前瞻 ROE（50.2 / 64.4 / 80.6%，2026-10-28 滚动后；M 已贴近稳态，回落段几乎不起作用）→ 高回报期到 **Y1 2030**（光通信链「封装、光电共测」环节，进入门槛高：测试机要随客户新品逐颗比对认证、双寡头格局多年未破）→ 2030–2035 线性回落 → **Y2 2035** 起稳态 **64.0%**。稳态取自身周期一层：FY2016–2025 十年均值，与前瞻同公式（调整后净利 − 税后利息 − Technoprobe 收益，÷ 年初（权益 − 净现金 − Technoprobe 账面））；同生意成熟同业层为空（FormFactor 12.1% 不收：用户 2026-10-19 裁定探针卡耗材与测试机不是同一门生意；京元电子、Cohu 近 5 年收入负增长剔除；爱德万不成熟；致茂样本不足 5 年不认）；兜底 = `_AXIS.ai-capex` 封装、光电共测环节的稳态兜底 **20%**（`ss_floor_ai_capex_package`，用户 2026-10-19 暂定，取代按资产形态的「设备」15%）——低于自身周期 64.0%，**不绑定**，锚点不变。每档稳态不超过该档前瞻：L 50.2% 封在前瞻、不回落。g2 6% 是同业反解后截顶，按同一路径重解只会更高，仍截在 6%。打折 k 三档本为 0 | active | 2016–2025 各年财报 non-GAAP EPS 与资产负债表（自身周期复核 2026-10-16）；`_AXIS.burn-in-test` §2 | `t0`、`y1`、`y2`、`ronic_ss` |
# | A20 | **FormFactor 约 9% 股权（待交割，未进 Inputs）**：2026-10-06 签约、10-12 公告，现金 300M 买 2,234,887 股（每股约 134.23），附光学测试等技术合作；财务长 2026Q3 业绩会：预计 Q4 交割（待监管批准）。交割前锚点不动（2026-09-27 资产负债表里还没有这笔）。交割后按 Technoprobe 同一思路处理：净现金减 300M（487.8 → 约 187.8M），持股按 FormFactor 收盘价（他物市价）作第三项闭合项，增值部分的税与核算口径（公允值或权益法、收益是否进 non-GAAP）以交割那期 10-Q / 10-K 为准。按 2026-10-29 FormFactor 收盘 100.03 粗估：持股 223.6M，三档约 −0.46/股（= (223.6 − 300 × 归母 0.9869) ÷ 157.502M；只记，不进锚点）。FormFactor 仍是 g2 同业簇成员（A7），入股不改其反解读数。**触发**：交割完成的那期 10-Q / 10-K → 改 Inputs、闭合项公式与 eval | active | Cleary Gottlieb 交易公告（2026-10）；RTTNews 2026-10-12；2026Q3 业绩会（Investing.com 文字稿 2026-10-28）；Longbridge FORM.US 报价 2026-10-29 | 闭合项（待建） |
# 原框架历史；本次迁移没有新增财务更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-10-29
# - **事件**：2026Q3 财报（2026-10-27 盘后）与业绩会（2026-10-28）。收入 1,306M（+70% YoY，超指引上限）、non-GAAP EPS 2.29（LSEG 预期 2.08）；SoC 676M（Q2 843M）、存储 301M 创纪录、IST 95M；机器人单季盈利。Q4 指引收入 1,250–1,350M、non-GAAP EPS 1.95–2.25、毛利率 57.5–58.5%。业绩会：计算在 Q3 见底，第一家超大规模客户下一轮放量在 2027 年中、第二家 2027 下半年产能采购，定制 AI 芯片项目偏下半年；2027 年每季同比增长、2027Q1 高于 2026Q4；新目标模型 2027-01 公布。盘后跌约 5–6%、10-28 盘前跌超 8%
# - **假设状态**：A16 `active` → `weakened`（计算放量由「2027 上半年」改为年中到下半年，未到「推迟到 2027 下半年以后」的证伪线）；A17 `active` → `confirmed`（机器人单季盈利）；A10 改写（TTM non-GAAP EPS 9.12 首次达到 L 分子，下季重做 L 档带测试）；A2 / A3 / A4 / A5 / A6 / A9 / A11 / A12 / A14 / A15 / A18 / A19 更新数字与证据
# - **Inputs 滚动到 2026-09-27**：资产负债表、稀释股数、可赎回少数股东、Technoprobe 账面与权益法收益（10.88M / 季）；Technoprobe 公允值按季末股价估算 2,244.7M（10-Q 未出，出后替换）；τ 0.5 → 0.25；FY26 窗口从下半年改为 Q4 一季（`eps_h1_26` → `eps_ytd_26` + `q_left`，eval 同步改为按剩余季度数摊剔除项）；FY27 共识换成 2026-10-28 的十六家 9.00 / 11.430 / 14.187（财报后修正尚未落地）
# - **锚点**：204.96 / 266.56 / 374.35 → **202.68 / 262.00 / 324.32**；切点 235.76 / 320.45 → 232.34 / 293.16；候选带 M′ / H′ 321.82 / 456.06 → 315.88 / 394.47。H −13.4% 几乎全部来自 FY27 共识上沿换人（16.53 那家不在十六家样本里），不是本季基本面；稳态回报 64.0%、高回报期 2030 / 2035、g2 6% 均未动（2026-10-16 / 10-19 已与用户对齐）
# - **待办**：Q3 10-Q 出后替换 `tp_fv`、`int_q`、`shares_out` 与机器人分部利润；财报后共识修正落地（预计 11 月第一周）后重拉 FY27 三点
# - **补记**：新增 A20——FormFactor 约 9% 股权（300M 现金，10-12 公告、预计 Q4 交割）此前未入框架；交割前不进锚点，按 2026-10-29 FormFactor 收盘粗估三档约 −0.46/股
# - touched: [§0, §1, A1, A2, A3, A4, A5, A6, A9, A10, A11, A12, A14, A15, A16, A17, A18, A19, A20, §3 Inputs, §3 Formula, §3 Outputs, 表1, 表2, 表2c, eval/TER.US.py]
HISTORICAL_PARTIAL_FINGERPRINT = '3b17ae396b86aacc14cd702432732a6b515db802da16b49864e2096de14c7c60'

INPUTS = {
    # 稀释加权股数；2026Q3 财报（8-K EX-99.1）157,502 千股；回购不前推（共识 EPS 已含回购节奏）; 来源：2026-09-27
    'shares': 1.57502e8,
    # 在外流通股；2026Q2 10-Q；只用于资产口径坐标（Q3 10-Q 出后更新）; 来源：2026-06-28
    'shares_out': 1.56378e8,
    # 归属泰瑞达股东权益 $M（2026Q3 财报资产负债表）；经营权益 = equity − net_cash − tp_book = 2,681.587 是 ROE 的起点，按 A9 滚到 FY27 年初再作分母; 来源：2026-09-27
    'equity': 3687.896,
    # 现金 460.742 + 有价证券 5.847（流动）+ 158.276（长期）（A5；2026Q3 财报）; 来源：2026-09-27
    'cash': 624.865,
    # 经营租赁负债 17.061 + 120.054（A5；2026Q3 财报）; 来源：2026-09-27
    'lease': 137.115,
    # cash − lease；有息债务 0（短期借款 —）；闭合项按 `shares` 折每股加回（A5）; 来源：2026-09-27
    'net_cash': 487.750,
    # 2026Q2 利息收入 $M（Q3 单项待 10-Q；Q3 财报只给「利息及其他收入」2.323）；× 4 × (1 − tax) ÷ shares = 剔除的税后利息/股（A5）; 来源：2026-06-28
    'int_q': 3.182,
    # 有效税率（2026Q3 14.8% = 59.833 / 404.291、1H 14.2%）；只用于利息税后; 来源：2026-09-27
    'tax': 0.15,
    # Technoprobe 10% 股权公允值 $M **估算**（10-Q 未出）：Q2 披露 2,457.9 ÷（2026-06-26 收盘 €33.04 × 欧元兑美元 1.1362）= 6,547.6 万股 × 2026-09-25 收盘 €30.14 × 1.1375（yfinance TPRO.MI / EURUSD；他物市价）；Q3 10-Q Note 披露后替换（A6）; 来源：2026-09-25
    'tp_fv': 2244.7,
    # Technoprobe 股权账面值 $M（权益法，2026Q3 财报「Equity method investment」），从经营权益中剔除（A6）; 来源：2026-09-27
    'tp_book': 518.559,
    # 美国联邦法定税率；增值部分 (tp_fv − tp_book) 的税（A6）; 来源：FY2025 10-K
    'tp_tax': 0.21,
    # Technoprobe non-GAAP 权益法收益 $M / 季 = GAAP 3.281 + 投资基差摊销 7.6（2026Q3 财报调节表）；× 4 ÷ shares 从分子剔除（A6）; 来源：2026-09-27
    'tp_eq_q': 10.881,
    # FY26 EPS = 前三季实际 7.32 + Q4 共识 2.03161（yfinance 2026-10-28，15 家，财报后未修正；Q4 指引 1.95–2.25）；A9 账面滚动的未入账利润 = 此值 − `eps_ytd_26`；同世界门; 来源：2026-10-28
    'eps_fy26_m': 9.35161,
    # FY26 已入账 non-GAAP EPS（Q1 2.56 + Q2 2.47 + Q3 2.29）; 来源：2026-09-27
    'eps_ytd_26': 7.32,
    # FY26 未入账季度数（Q4）；剔除项按 q_left / 4 年摊进窗口（A9 / A18）; 来源：2026-09-27
    'q_left': 1,
    # FY27 共识 EPS 下沿（16 家，调整后）= L 分子（A2）；yfinance 2026-10-28 仍为财报前口径，修正后复核; 来源：2026-10-28
    'eps_fy27_l': 9.00,
    # FY27 共识 EPS 均值 = M 分子（A2；同上）; 来源：2026-10-28
    'eps_fy27_m': 11.43035,
    # FY27 共识 EPS 上沿 = H 分子（A2；16 家，原上沿 16.53 那家不在样本内）; 来源：2026-10-28
    'eps_fy27_h': 14.18738,
    # MarketScreener FY27 EPS（家数不明）；只作候选带 g1 的同源分母（A13）; 来源：2026-10-07
    'eps_fy27_ms': 11.74,
    # MarketScreener FY28 EPS（家数不明）；候选带 g1 = 此值 ÷ `eps_fy27_ms` − 1（A13）; 来源：2026-10-07
    'eps_fy28_ms': 15.58,
    # 2023–25 分红 + 回购 ÷ 净利（1,518.5 / 1,545.2）；只进视同派出披露行（A11）; 来源：2025-12-31
    'payout_3y': 0.9827,
    # 永续折现率 = 篮 4 常规经营 10%：测试机价格公司自定，盈利随客户产品导入与扩产周期、不是商品价函数；最大直接客户 19%、前五大 44%，未达篮 7 阈值（A8）；`check_r`; 来源：2026-10-07
    'r_perp': 0.10,
    # 长期增长由 testing peer 轴排除自身后求中位并按折现率上限计算；
    # 历史参考为 7.525% → 截至 6%，四家明细与来源在轴脚本（2026-10-02）。
    # 视同派出现金打折（A11：来源层级 ①，Technoprobe 入股回报 ≫ r）; 来源：2026-10-07
    'k_l': 0,
    # 同上; 来源：2026-10-07
    'k_m': 0,
    # 同上; 来源：2026-10-07
    'k_h': 0,
    # 上一轮下行 non-GAAP EPS 比 2023 / 2021 = 2.93 / 5.98；只作压力坐标，不进锚点（A15）; 来源：2024-01-31
    'eps_trough_ratio': 0.49,
    # 可赎回少数股东权益 $M（2026Q3 财报）；归母比例 = equity ÷ (equity + minority) = 0.9869，乘在净现金行与窗口可分配利润上（A18）; 来源：2026-09-27
    'minority': 49.065,
    # 分子年（日历年）= 回报路径第 1 年（A19）; 来源：2026-10-16
    't0': 2027,
    # 高回报期止点与稳态起点从 AI 资本开支轴的封装、光电共测路径
    # 读取；历史路径 2030 / 2035，用户按环节裁定（2026-10-16）。
    # 稳态回报 = 自身周期十年均值 64.0%（FY2016–2025，与前瞻同公式：调整后净利 − 税后利息 − Technoprobe 收益，÷ 年初（权益 − 净现金 − Technoprobe 账面））；成熟同业层空（FormFactor 不是同一门生意，用户 2026-10-19），兜底 = `_AXIS.ai-capex` `ss_floor_ai_capex_package` 20%（引用，不绑定）；每档不超过该档前瞻 ROE（L 50.2% 封在前瞻）（A19）; 来源：2026-10-16
    'ronic_ss': 0.640,
    # 时点对齐年数：估值基准日 2026-09-27 → 分子年初 2027-01-01，按实际月数 3 个月（A18）; 来源：2026-09-27
    'tau': 0.25,
    # 自身 5 年实测 PB 低点（2025-03-30 季末账面 2,797.5M ÷ 160.674M 股 = 17.41/股 × 其后收盘低点 67.96，2025-04-08）；只作对账门资产坐标，不进公式; 来源：2025-04-08
    'pb_low': 3.90,
}
BASKETS = {"r_perp": 4}  # test-equipment leader, original A8
REQUIRED = frozenset(INPUTS) | {'g2', 'g_peer_median', 'y1', 'y2'}

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float,
            g1: float = 0.0, n: int = 0) -> float:
    """Gordon multiple on next-period earnings with the three-stage return path.

    Year t = 1 is calendar t0 (the numerator year).  n transition years at g1 keep
    the forward ROE and the unfloored b1 = g1/ROE (as `two_stage_pe`).  Then at g:
    the retention of calendar c earns ROE while c <= y1, fades linearly to the
    stable return by y2, and the stable return from y2 on (Gordon tail).  The stable
    return is capped at the tier's forward ROE and floored at r.  With ROE <= stable
    the path is flat and this equals `perpetual_pe` / `two_stage_pe`.
    """
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    rs = min(roe, max(rs, r))

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs
        return roe + (rs - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, rs) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A8: one leg, r is the basket's value; the basket is named in the Inputs source cell.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A8)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    # A7: g2 is the peer median truncated to g_cap(r).
    cap = g_cap(inp["r_perp"])
    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if abs(inp["g2"] - min(inp["g_peer_median"], cap)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {cap:.3f}) — A7")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {inp['r_perp'] - inp['g2']:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # 裁决顺序 ④ 同世界门: own consensus FY26 -> FY27 is up, so a g2 >= 0 source is admissible.
    if not inp["eps_fy26_m"] < inp["eps_fy27_m"]:
        errs.append("FY26 consensus not below FY27: the same-world gate for a g2 >= 0 source no longer holds (A7)")

    # A2e-2a: one consensus range, three points on it.
    errs += ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])

    # A5 / A6: closing items must be what the operating book is net of.
    if abs(inp["net_cash"] - (inp["cash"] - inp["lease"])) > 0.05:
        errs.append(f"net_cash {inp['net_cash']} != cash {inp['cash']} - lease {inp['lease']} (A5)")
    if not 0 < inp["net_cash"] <= inp["cash"]:
        errs.append(f"net_cash {inp['net_cash']} must be positive and <= cash {inp['cash']} (A5)")
    if not inp["tp_fv"] > inp["tp_book"] > 0:
        errs.append("Technoprobe fair value must exceed its carrying value (else the tax-on-gain leg flips sign, A6)")
    if inp["equity"] - inp["net_cash"] - inp["tp_book"] <= 0:
        errs.append("operating equity (equity - net_cash - tp_book) is not positive (A5/A6)")

    # A11: deemed-distributed discount k, per tier, cyclical ordering.
    ks = (inp["k_l"], inp["k_m"], inp["k_h"])
    if not all(0.0 <= k < 1.0 for k in ks) or not ks[0] <= ks[1] <= ks[2]:
        errs.append(f"k_l/k_m/k_h = {ks} must lie in [0,1) with k_H >= k_M >= k_L (A11)")

    # A13: the candidate's transition must point the same way as the base (FY27 -> FY28 up).
    if not inp["eps_fy28_ms"] > inp["eps_fy27_ms"] > 0:
        errs.append("candidate g1 source not upward (FY28 <= FY27 on MarketScreener) — drop the band (A13)")

    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    return errs



def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp, ('t0', 'y1', 'y2'))
    baskets = BASKETS
    errors = sanity_checks(inp, baskets)
    r, g2 = inp["r_perp"], inp["g2"]
    cap = g_cap(r)
    sh = inp["shares"]
    street = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    # ---- Step 1: core EPS — strip after-tax interest and the Technoprobe pick-up (A5, A6) ----
    int_ps = inp["int_q"] * 4 * (1.0 - inp["tax"]) * MILLION / sh
    tp_eps = inp["tp_eq_q"] * 4 * MILLION / sh
    strip = int_ps + tp_eps
    core = {t: street[t] - strip for t in TIERS}

    # ---- Step 2: closing items per share (net cash x parent share, ①「归母份额」) ----
    parent = inp["equity"] / (inp["equity"] + inp["minority"])
    cash_ps = inp["net_cash"] * MILLION / sh * parent
    tp_after = inp["tp_fv"] - (inp["tp_fv"] - inp["tp_book"]) * inp["tp_tax"]
    tp_ps = tp_after * MILLION / sh
    closing = cash_ps + tp_ps

    # ---- Step 3-5: tier ROE on the FY27 opening operating book, Gordon multiple ----
    # Operating book = equity - net cash - Technoprobe carrying value (balance-sheet
    # date), rolled over the q_left FY26 quarters not yet booked at b = g/ROE (A9).
    # Closed form BPS = BPS0 / (1 - g·N/core); a diverging roll stops.
    equity_op = inp["equity"] - inp["net_cash"] - inp["tp_book"]
    bps0 = equity_op * MILLION / sh
    q_left = inp["q_left"]
    if q_left not in (1, 2, 3, 4):
        errors.append(f"q_left {q_left:g} must be the whole number of FY26 quarters not yet booked (1-4)")
    n_unbooked = inp["eps_fy26_m"] - inp["eps_ytd_26"] - strip * q_left / 4

    def opening_bps(core_x: float, g: float) -> float:
        share = g * n_unbooked / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps0 / (1.0 - share)

    t0, y1, y2, rs, tau = int(inp["t0"]), int(inp["y1"]), int(inp["y2"]), inp["ronic_ss"], inp["tau"]

    def window(roe_x: float, g: float, rr: float) -> float:
        """Unbooked FY26 distributable profit N x (1 - b1) x parent, discounted tau/2 (③ 时点对齐)."""
        return n_unbooked * max(1.0 - g / roe_x, 0.0) * parent / (1 + rr) ** (tau / 2)

    def deck(g: float, rr: float, rs_: float | None = None) -> tuple[dict, dict, dict, dict]:
        rs_ = rs if rs_ is None else rs_
        bps = {t: opening_bps(core[t], g) for t in TIERS}
        roe_ = {t: core[t] / bps[t] for t in TIERS}
        pe_ = {t: path_pe(g, roe_[t], rr, t0, y1, y2, rs_) for t in TIERS}
        val = {t: core[t] * pe_[t] * (1.0 - k[t]) / (1 + rr) ** tau + window(roe_[t], g, rr) + closing
               for t in TIERS}
        return bps, roe_, pe_, val

    bps, roe, pes, scen = deck(g2, r)
    b1 = {t: g2 / roe[t] for t in TIERS}
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * n_unbooked for t in TIERS}  # disclosure only

    L, M, H = scen["L"], scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        raise ValueError("; ".join(errors))

    # ---- A2e-2c flat ladder + decomposition ----
    if not (core["L"] < core["M"] < core["H"]):
        errors.append(f"numerator ladder broken: core EPS {core['L']:.3f}/{core['M']:.3f}/{core['H']:.3f} (A2e-2c)")
    flat = [core[t] * pes["M"] / (1 + r) ** tau + window(roe[t], g2, r) + closing for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    ex_close = {t: scen[t] - closing for t in TIERS}

    # ---- ③ guardrail not applicable (no same-earnings months, A10): reconciliation coordinates ----
    e_over_r = core["M"] / r + closing
    bvps = inp["equity"] * MILLION / inp["shares_out"]
    asset_coord = inp["pb_low"] * bvps
    trough_core = (inp["eps_fy26_m"] * inp["eps_trough_ratio"]) - strip
    trough_coord = trough_core / r + closing

    # ---- g2 leverage: -1pp disclosed; +1pp breaks ① ----
    _, _, _, lo = deck(g2 - 0.01, r)

    # ---- Candidate band (A13): FY28 single-source point -> one transition year on M/H ----
    g1 = inp["eps_fy28_ms"] / inp["eps_fy27_ms"] - 1.0
    cand = {"L": L}
    cand_pe = {}
    for t in CANDIDATE_TIERS:
        share = g1 * n_unbooked / core[t]
        bps_c = bps0 / (1.0 - share)
        roe_c = core[t] / bps_c
        cand_pe[t] = path_pe(g2, roe_c, r, t0, y1, y2, rs, g1=g1, n=1)
        cand[t] = core[t] * cand_pe[t] * (1.0 - k[t]) / (1 + r) ** tau + window(roe[t], g2, r) + closing
    if not cand["L"] < cand["M"] < cand["H"]:
        errors.append(f"candidate band not ordered: {cand}")

    A, B = cut_points(L, M, H)
    no_tp = [scen[t] - tp_ps for t in TIERS]
    pre_tax = [scen[t] - tp_ps + inp["tp_fv"] * MILLION / sh for t in TIERS]
    # The old seller-target comparison is a historical coordinate, not an input to value.
    target_implied = {str(int(tp)): implied_g((tp - closing) / core["M"], roe["M"], r)
                      for tp in (350.0, 450.0, 550.0)}

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1 — the only priced r; the
    # rolled ROE, g2, core numerator and closing items stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        _, _, _, s = deck(g2, r + dr)
        return s["L"], s["M"], s["H"]

    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    result = {
        "ticker": "TER.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-09-27',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-29', 'historical_framework_as_of': '2026-10-29',
        "anchors": scen,
        "candidate": {"label": "MarketScreener 2028 单源预测", "anchors": cand},
        "option": None, "cut_points": [A, B],
        "street": street, "core": core, "int_ps": int_ps, "tp_eps": tp_eps, "strip": strip,
        "parent": parent, "cash_ps": cash_ps, "tp_after": tp_after, "tp_ps": tp_ps,
        "closing": closing, "equity_op": equity_op, "bps0": bps0, "n_unbooked": n_unbooked,
        "bps": bps, "roe": roe, "pes": pes, "b1": b1, "excess_cash": excess_cash,
        "flat": flat, "ex_close": ex_close, "e_over_r": e_over_r, "bvps": bvps,
        "asset_coord": asset_coord, "trough_core": trough_core, "trough_coord": trough_coord,
        "lo": lo, "g1": g1, "cand_pe": cand_pe, "no_tp": no_tp, "pre_tax": pre_tax,
        "contrast": [deck(g2, rr)[3] for rr in (0.13, 0.15)], "target_implied": target_implied,
        "formfactor_unclosed_impact": (FORM_SHARES * FORM_PRICE - FORM_CASH_M * MILLION * parent) / sh,
        "windows": [window(roe[t], g2, r) for t in TIERS],
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
    capex, peer = context['axes']['capex'], context['axes']['peer']
    if capex.get('role') != 'demand_reference' or peer.get('role') != 'peer_reference':
        raise ValueError('TER requires AI demand and testing-peer reference roles')
    capex_floor = capex['ss_floor_ai_capex_package']
    shared = {'g_peer_median': peer['g_peer_median'],
              'g2': min(peer['g_peer_median'], g_cap(INPUTS['r_perp'])),
              'y1': capex['y1_ai_capex_package'], 'y2': capex['y2_ai_capex_package'],
              'ronic_ss': max(INPUTS['ronic_ss'], capex_floor)}
    result = evaluate({**INPUTS, **shared}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'shared': shared, 'capex_floor': capex_floor, 'baskets': BASKETS,
         'million': MILLION, 'minimum_rate_gap': MIN_R_MINUS_G,
         'candidate_tiers': CANDIDATE_TIERS,
         'form_shares': FORM_SHARES, 'form_price': FORM_PRICE, 'form_cash_m': FORM_CASH_M},
        HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments'] = {
        'operating_business': {'unit': 'USD_PER_SHARE', 'values': result['ex_close']},
        'net_cash': {'unit': 'USD_PER_SHARE', 'values': dict.fromkeys('LMH', result['cash_ps'])},
        'technoprobe': {'unit': 'USD_PER_SHARE', 'values': dict.fromkeys('LMH', result['tp_ps'])},
    }
    parameters = result['parameters']
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['growth'])},
        'forward_return': {'unit': 'RATIO', 'values': parameters['forward']},
        'steady_return': {'unit': 'RATIO', 'values': parameters['mature'], 'reference_value': shared['ronic_ss']},
    }
    result['review_flags'] = ['historical_consensus_after_earnings_unverified',
                              'historical_technoprobe_fair_value_unverified',
                              'historical_formfactor_transaction_unclosed']
    return result
