#!/usr/bin/env python3
"""1810.HK (Xiaomi) valuation on the 2026-10-19 research basis.

Inputs, their source dates, modelling judgments and the calculations live here.
The human-readable framework explains the results and is never an input.
The shared runner invokes calculate(context) and does not publish results.
The corrected model needs matching segment earnings and asset ownership inputs.
Until available, the runner returns the explicitly flagged legacy calculation
as a historical comparison, not as an updated or corrected valuation.

The A-number references in these notes refer to the historical framework before
the pilot rewrite; they identify original decisions, not a live document API.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing here
computes a zone for the price or a market-implied reading — the digest and the
app zone on live quotes.

formula_id: xiaomi_sotp_phone_eco_ev_ps_cash_v3_gordon_v4

gordon_v2 (valuation-rules「构造规则冲突的裁决顺序」②): the operating numerator is
the furthest fiscal year with a >=2-house RANGE -- FY2027E (calendar FY, FY+1,
no discounting), yfinance 19-house low/mean/high adjusted EPS in CNY x issued
shares, less run-rate SBC and the after-tax financial income attributable to
cash and investments separately valued in the closing item. Each tier must also
deduct the same-basis earnings of the separately valued EV / AI business.
The resulting core numerator is split phone / eco by the 1H26 gross-profit
weight (A16); that allocation remains an estimate.  The FY2028E group growth
estimate cannot be applied to core earnings after the split. A candidate is
available only with a separately sourced, same-basis core growth estimate.

Main ruler (four legs, summed — no hand-written total is ever consumed):
  1. phone leg  : ni_phone_k x perpetual_pe(g2_phone=0, ROE, r).  g2 = 0 pins
                  the multiple at 1/r, flat across tiers whatever the ROE (A7).
  2. eco leg    : ni_eco_k x perpetual_pe(g2_eco, ROE_eco_k, r); ROE on operating
                  net assets, not book equity (A15), at the OPENING of FY2027
                  (= end-2026, E_{n+1}/B_n): the 1H26 operating net assets
                  rolled over the 2H26 earnings not yet booked (FY2026E
                  consensus net of the same strip, minus 1H26 actual) at the
                  growth-required retention b1 = g/ROE -- the leg's g2 in the
                  deck, or core g1 in the candidate band -- closed form
                  B = B0 / (1 - g N / E) (valuation-rules 裁决表 ② as of
                  2026-09-21; A24).  Phone g2 = 0 so its book never rolls.
  3. EV leg     : FY26E segment revenue x peer enterprise-value/sales multiples.
  4. closing    : parent-owned net cash + parent-owned investments x (1 - d).
  Overlay (NOT in L/M/H):
  5. V_opt      : EV deliveries the company targets beyond what the FY26E
                  consensus carries (opt_units = 2026 target 550k - 450k), x
                  own ASP x own 1H26 EV-segment gross margin, after tax, valued
                  on the EV leg's own ruler (basket 4 r_ev, g2 = 0 -> 1/r; was basket 7
                  until 2026-10-03 -- single product is no basket-7 reason) and
                  discounted from the target year to FY2027 (exponent floored
                  at 0: the target year precedes the numerator year) (A18;
                  valuation-rules「未建模期权」2026-10-03: borrow quantity not
                  price, own named quantity, own ruler, timed).  MiMo has no own
                  revenue or target -> 待补, no V_opt.

The 1H26 segment recompute is a historical operating-level diagnostic, not a
forecast of segment net income or a justified add-back to group earnings.

Discount rate: r_perp is a basket value (gordon.BASKET_R); BASKETS declares the
basket (篮 4 龙头制造, A23) and `check_r` requires r to equal that basket's
value; both perpetual g2 are capped at g_cap(r).  The
EV leg is a PS ruler (no r in its bottom-card formula); its basket (篮 4 since
2026-10-03, was 篮 7) only prices V_opt via r_ev.

Guardrail: every tier's whole-ticker multiple (anchor / GAAP-TTM EPS) must sit
inside the realised 5-year band [pe_own_min, pe_own_max] (A21, weak band).

Money inputs are in 亿元人民币; per-share anchors are HKD via fx_cny_hkd.
Run through the shared valuation runner with explicitly selected roots.
"""

from __future__ import annotations

import math
import sys

from lib.gordon import check_g_cap, check_r, perpetual_pe, return_path_pe, two_stage_pe
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'rf_report', 'partial_basis'), 'axes': {}}
HISTORICAL_BASELINE = '2321b25ac1090e46c73178fa66e65a6bb49fc63bca3a74cecd7c3b831e71dbac'

FORMULA_ID = "xiaomi_sotp_phone_eco_ev_ps_cash_v3_gordon_v4"

TOL = 0.05  # Outputs are rounded to 2 decimals
YI = 1e8  # 亿 -> unit
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"

REQUIRED = (
    "shares", "fx_cny_hkd", "tax_rate",
    "eps27_l_cny", "eps27_m_cny", "eps27_h_cny",
    "ev_ai_h1_units", "ev_ai_h2_asp_cny", "ev_ai_h2_other_revenue", "ev_ai_h2_gross_margin",
    "ev_ai_h2_expenses", "ev_ai_fy27_units_l", "ev_ai_fy27_units_m", "ev_ai_fy27_units_h",
    "ev_ai_fy27_asp_l", "ev_ai_fy27_asp_m", "ev_ai_fy27_asp_h",
    "ev_ai_fy27_margin_l", "ev_ai_fy27_margin_m", "ev_ai_fy27_margin_h",
    "ev_ai_fy27_other_revenue", "ev_ai_fy27_expenses", "ev_ai_profit_tax_rate",
    "ev_ai_loss_tax_benefit", "ev_ai_parent_share",
    "ev_ai_operating_equity_h126", "net_cash_parent_cny", "invest_parent_cny",
    "adj_np_h1", "gp_core_h1", "gp_phone_h1", "gp_ev_h1",
    "rev_core_q1", "rev_core_q2", "opex_ratio_q1", "opex_ratio_q2",
    "opex_total_h1", "sbc_h1", "fin_net_h1", "nonoperating_finance_net_h1",
    "r_perp", "g2_phone", "g2_eco", "n_fy28_cand", "equity_cny", "eps26_m_cny", "payout_3y",
    "ev_units_fy26e", "ev_asp_cny", "ev_other_rev",
    "ev_sales_l", "ev_sales_m", "ev_sales_h",
    "cash_like", "debt", "invest_cny",
    "d_invest_l", "d_invest_m", "d_invest_h",
    "pe_own_min", "pe_own_max", "eps_ttm_gaap",
    "delivery_target_fy26", "rev_ev_h1", "r_ev", "g2_ev_opt", "t_opt", "t_num",
    "tau_yr", "nci_cny",
    "ss_return_eco", "t0_ret", "y1_ret", "y2_ret",
)

BANDS = ("l", "m", "h")

# This is an editable short display name, not a source or an approval flag.
# Update it when the candidate's underlying research changes.
CANDIDATE_LABEL = "FY2028E·核心业务"

# FY2027E non-GAAP EPS from 19 analysts, yfinance, 2026-09-14. Replacing
# these numbers requires recording the new source, sample and date in comments.
EPS_ESTIMATES = {"low": 0.98, "mean": 1.32653, "high": 2.08}
# Numeric references remain distinct from stock-specific adopted values; their
# original sources and reasons are recorded here rather than emitted as prose.
PARAMETER_REFERENCES = {
    "g2_eco": 0.0207,       # 港股互联网同业中位，2026-09-11，2026-09-18采用
    "ss_return_eco": 0.263, # 公司2019–2022回报均值，东财F10，2026-10-19采用
    "g2_phone": 0.0,        # 手机长期出货难增长的原研究判断，2026-09-18
    "d_invest_l": 0.40,     # 投资组合折价的保守情景判断，2026-09-06
    "d_invest_m": 0.25,     # 投资组合折价的中性情景判断，2026-09-06
    "d_invest_h": 0.10,     # 高盛控股公司折价参考，2026-08-19
    "g2_ev_opt": 0.0,       # 交付目标只针对2026年的原判断，2026-10-03
}
# Historical references only: 2026-09-11 peer equity price/sales were
# 0.555 / 0.758 / 0.813; a single analyst's 2028 group growth was 43.75%.
# Neither is an input to the revised core/enterprise-value model.
DELIVERY_TARGET = 550000     # 公司管理层公开目标，2026-01-03
DELIVERY_CONSENSUS = 450000  # 四家卖方交付预测，2026-08

# 2026-10-03 的历史口径纠正：汽车额外价值不再借用同业业务的收入和
# 倍数，而用公司交付目标超出卖方共识的部分及本公司汽车业务单位经济。
# 汽车业务折现率由 15% 改为 10%，原因是客户为分散个人、汽车价格由
# 公司自主决定；这是对风险归类的修正，不是公司新披露的经营数字。

# Frozen valuation inputs. Values and source descriptions originate from the
# previously reviewed 2026-10-19 framework; updating a value requires updating
# its provenance and reconsidering the dependent assumptions. Monetary amounts
# use CNY 100 million except shares, vehicle units, vehicle ASP, EPS and ratios.
# Eco growth 2.07% was the median of a 2026-09-11 internet peer cross-section:
# Tencent 2.96%, NetEase 2.07%, JD -4.03%; Xiaomi's own near-discount-rate ROE
# was excluded. It is an inferred market convention, not a company forecast.
# Eco steady return 26.3% is the company-level 2019–2022 cycle mean on operating
# capital (14.3%, 22.3%, 61.0%, 7.6%; Eastmoney F10), selected in 2026-10-19
# research. The original thesis treats the phone/IoT/internet business as the
# comparable cycle and cars as a separately valued business.
# 分部去重：本脚本另行估值汽车及部分 AI 业务，手机和生态的利润、
# 窗口利润与经营权益须先剔除同一业务；否则同一业务会出现在两处。
# 所有金额均为人民币亿元；分部损益为负表示亏损，减去负值会增加核心利润。
#
# 历史起点（旧研究引用小米 2026 中报附注 2、业务回顾及合并损益表；
# 本次未重验原文）：上半年核心分部费用按两季度收入分别乘 14.8%、
# 14.2% 估得 236.65；集团销售、管理和研发费用共 382.227，剩余
# 145.58 暂归汽车及 AI。该分部毛利 87.859 减估算费用，得到经营
# 亏损约 57.72。集团剩余费用全部归该分部是推算假设，不是公司披露
# 的分部净利润；旧研究引用德银报告 Wisburg 101291 作交叉，本次未核
# 报告原文。该历史计算保留在 compute() 中，只用于经营口径对照。
#
# 2026 年下半年：优先使用同口径分部预测；缺分部预测时，可用全年
# 交付预测减上半年实际交付，乘预计下半年平均售价，加同期 AI 等其他
# 收入，再按所选毛利率减销售、研发及管理等费用，估算下半年经营损益。
# 例如旧材料记录全年交付共识 45 万辆、上半年交付 185,055 辆、
# 2Q26 汽车均价 229,312 元、1H26 分部毛利率约 19.63%；这些只是历史
# 起点，售价、毛利率、其他收入和费用路径需另定并标明依据。全年分部
# 损益由同口径上半年及下半年相加，不能把上半年亏损直接年化当预测。
#
# 2027 年：可分别为保守、中性、乐观情景估算交付量、平均售价、AI 等
# 其他收入、分部毛利率及费用；各档收入 = 交付量 × 售价 + 其他收入，
# 经营损益 = 收入 × 毛利率 − 费用。交付与费用路径应互相一致，且须
# 与该档集团利润预测的业务世界相容；集团低/均/高与不同机构的分部
# 预测不是天然配对。旧稿所称核心约 320、汽车约亏 40 仅是粗略判断，
# 未留下足够的推导或机构原文，不得当作已核实的 2027 年分部共识。
#
# 口径桥：上述历史和未来推算先得到经营损益；集团每股盈利预测经
# 股权薪酬和净财务收入调整后，须把分部损益桥接至同一税后、归母及
# 调整口径才能相减。记录分部是否含股权薪酬、分摊的总部费用、内部
# 交易及财务项目，避免重复扣减；另说明亏损是否确认税收收益及税率
# 依据，再按分部实际股东权益归属折算。若缺直接披露，可用有理由的
# 代理并写明假设与影响，但不能把集团税率或归母比例冒称分部事实。
#
# 脚本由上述基础输入计算 2026 年上半年、下半年及 2027 年各档的
# 分部归母损益，再分别从对应集团利润中剔除；修改交付、售价、毛利
# 或费用会自动传导，不要手抄推算结果。当前尚未选定可采用的情景、
# 税务与归属假设，因此这些基础输入不设默认值。每次更新在此记录
# 原始来源、日期、计算假设及税务/归母桥，不得把研究估算写成共识。
#
# 资产口径：ev_ai_operating_equity_h126 是另估业务在资产负债表日、
# 已剔除单列现金与投资的归母经营权益。net_cash_parent_cny 和
# invest_parent_cny 是分别归母且单列估值的现金及投资。若分部未披露
# 净资产，可从已披露资产负债、经营资金和资本投入分摊推算，记录
# 归属、分摊方法和误差；不能把未查明的部分默认为零或重复扣现金。
# nonoperating_finance_net_h1 是上半年已经由单列现金和投资计价的
# 税后归母财务收益，须与集团调整后盈利同口径。fin_net_h1 保留公司
# 集团净财务收入的历史原值，不能覆盖成估算值；经营所需现金的收益
# 留在经营利润内。若按比例代理拆分，需说明数据、税务和局限。
#
# 汽车估值：ev_sales_{l,m,h} 取同口径可比公司的企业价值/收入倍数，
# 不用股权市值/收入替代；后者包含同业自身现金和负债，而本模型已
# 单列本公司净现金。可由同日市值、债务、现金及其他非经营资产推算
# 同业企业价值，统一币种、财年、少数股东和业务范围并记录来源。
# 旧股权市销率不是新倍数；缺数据时保留缺口，不把未经核实的数填成事实。
# g1_fy28_core 可选；应为剔除汽车及 AI 后手机/生态的同口径增长预测
# 或有依据的估算。旧集团增长率不自动等于核心增长率，不能直接沿用。
# Revisit inputs when phone gross margin / consensus changes, the 2026 delivery
# target and its consensus overlap change, MiMo revenue becomes measurable, or
# internet revenue decouples from phone sales for two consecutive quarters.
# The original research also calls for a review if Q3 2026 other income falls
# below CNY 500 million AND consensus is revised down, or if FY27 phone gross
# margin remains <=9.5% AND consensus falls. These are conditional triggers,
# not numeric rules that automatically change the forecast. For the car risk
# category, revisit it if one counterparty reaches >=50% of car revenue, the
# top two >=70%, or revenue becomes dependent on unsettled financing.
INPUTS = {
    'shares': 2.5759203687e10,  # 已发行总股本（**非摊薄**，口径理由见 A6）；港交所证券变动月报表；来源日期：2026-08-31
    'fx_cny_hkd': 1.1668,  # CNY→HKD **市场交叉汇率** = USDHKD 7.8400 ÷ USDCNY 6.7190（yfinance `HKD=X` / `CNY=X` 2026-09-04 收盘）。**MUST NOT 用 Longbridge `exchange-rate`**：其 HKD/USD 7.0001 越出联系汇率区间，旧值 1.1465 为 2026-04/05 水平（见 `9988.HK.md` 同字段）；来源日期：2026-09-04
    'eps27_l_cny': EPS_ESTIMATES['low'],  # 2027 年每股预测下沿，来源见 EPS_ESTIMATES
    'eps27_m_cny': EPS_ESTIMATES['mean'],  # 2027 年每股预测均值，来源见 EPS_ESTIMATES
    'eps27_h_cny': EPS_ESTIMATES['high'],  # 2027 年每股预测上沿，来源见 EPS_ESTIMATES
    'eps26_m_cny': 0.94813,  # FY2026E 经调整 EPS 共识均值 CNY/股（17 家）；× 股本、扣同一套 SBC / 净财务收入、减 1H26 实测 = 2H26 尚未入账的经营利润，滚进 2027 年初经营净资产（A24）；也做交叉（≈ 1H26 年化）；来源日期：2026-09-14
    'payout_3y': 0.0,  # 近三年实付派息率均值：小米 2023–25 无现金股利（yfinance 年报现金流量表；payoutRatio 0），留存 100%；**只进** A24 的 B 桶披露行，不进经营净资产推演；来源日期：2025-12-31
    'tax_rate': 0.179,  # 集团有效税率 = 所得税 30.96 ÷ 除所得税前利润 172.94（中报）；旧汽车额外交付试算使用，单列财务收益已税后、不再使用；来源日期：1H26
    'adj_np_h1': 122.912,  # 集团经调整净利润（Non-IFRS）；中报调节表 12,291,208 千元；只作对账与压力坐标；来源日期：1H26
    'gp_core_h1': 346.332,  # 手机×AIoT 分部毛利；中报附注 2 34,633,185 千元（权重分母，A16）；来源日期：1H26
    'gp_phone_h1': 80.345,  # 智能手机 1H 毛利 = (Q1 442.733 + Q2 421.187) × 1H GM 9.3%（摩通；A16）；来源日期：1H26
    'gp_ev_h1': 87.859,  # 智能电动汽车及 AI 分部毛利；中报附注 2 8,785,853 千元（A3 对账）；来源日期：1H26
    'rev_core_q1': 792.772,  # 手机×AIoT 1Q26 分部收入 = 1H 1,633.03 − 2Q 840.26（A3）；来源日期：1Q26
    'rev_core_q2': 840.258,  # 手机×AIoT 2Q26 分部收入；中报附注 2 84,025,773 千元；来源日期：2Q26
    'opex_ratio_q1': 0.148,  # 手机×AIoT 1Q26 分部营业费用率 = 14.2% + 环比 0.6pp（A3）；来源日期：1Q26
    'opex_ratio_q2': 0.142,  # 手机×AIoT 2Q26 分部营业费用率；中报业务回顾原文；来源日期：2Q26
    'opex_total_h1': 382.227,  # 集团三费合计 = 研发 181.857 + 销售推广 169.250 + 行政 31.121；来源日期：1H26
    'sbc_h1': 23.211,  # 以股份为基础的薪酬；中报 Non-IFRS 调节表 2,321,102 千元（A6，从共识分子扣回）；来源日期：1H26
    'fin_net_h1': 11.112,  # 集团财务收入 25.662 − 财务成本 14.549；实际原值，需另估属于单列资产的税后收益；来源日期：1H26
    'r_perp': 0.10,  # 篮 4 龙头制造 10%：手机腿 / 生态腿同篮（硬件周期龙头 / 常规经营，A23；无备选篮）；汽车腿 PS 尺、无 r 落点（其 \(V_{opt}\) 用 `r_ev`）；来源日期：2026-09-18
    'g2_phone': PARAMETER_REFERENCES['g2_phone'],  # 手机增长：无同业锚，原研究自定
    'g2_eco': 0.0207,  # 生态腿永续增长；**同业反解**（港股互联网横截面良态三点中位，A7）；cap = min(6%, r − 4%) = 6% 未收紧；来源日期：2026-09-18
    'n_fy28_cand': 1,  # **候选带**用的过渡年数（FY2028E 一年，A22）；来源日期：2026-08-20
    'equity_cny': 2697.0,  # 归母权益（中报）；扣归母净现金、归母投资及另估业务经营权益后，才是核心经营权益起点；来源日期：2026-06-30
    'ev_units_fy26e': DELIVERY_CONSENSUS,  # 2026年交付共识；来源见 DELIVERY_CONSENSUS
    'ev_asp_cny': 229312,  # 汽车 ASP（元/辆）；中报 2Q26 实际混合 ASP；来源日期：2Q26
    'ev_other_rev': 40.0,  # AI 等创新业务年化收入 = 2Q26 分部收入 − 交付×ASP ≈ 10 亿/季 ×4；来源日期：2Q26
    'cash_like': 2034.429,  # 现金类合计；受限制现金已排除（A11）；来源日期：2026-06-30
    'debt': 392.768,  # 借款：非流动 295.704 + 流动 97.064（A11）；来源日期：2026-06-30
    'invest_cny': 919.579,  # 投资组合 = FVTPL 长期投资 853.430 + 权益法 66.149（A11）；来源日期：2026-06-30
    'd_invest_l': PARAMETER_REFERENCES['d_invest_l'],  # 投资组合保守折价
    'd_invest_m': PARAMETER_REFERENCES['d_invest_m'],  # 投资组合中性折价
    'd_invest_h': PARAMETER_REFERENCES['d_invest_h'],  # 投资组合乐观折价
    'pe_own_min': 13.9,  # 自身 5 年 GAAP-TTM PE 实测带下沿；**护栏，不入主公式**（A21）；来源日期：2026-06-30
    'pe_own_max': 121.97,  # 自身 5 年 GAAP-TTM PE 实测带上沿；护栏（A21）；来源日期：2026-09-14
    'eps_ttm_gaap': 1.475,  # GAAP-TTM EPS HKD（Longbridge PE 口径的分母）；只用于护栏换算（A21）；来源日期：2026-09-11
    'delivery_target_fy26': DELIVERY_TARGET,  # 公司目标；潜在增量按目标减共识计算，来源见 DELIVERY_TARGET
    'rev_ev_h1': 447.60,  # 智能电动汽车及 AI 分部 1H26 收入（中报附注 2）；与 `gp_ev_h1` 合成期权单位经济（分部毛利率 19.6%）；A18；来源日期：1H26
    'r_ev': 0.10,  # 篮 4 常规经营 10%：汽车腿（整车价格自定、非商品价函数，客户为分散个人、未达篮 7 对手方阈值；初分篮 7「单产品、放量未证」2026-10-03 推翻，A23）；只进 \(V_{opt}\)（汽车腿底牌为 PS 尺、无 r 落点）；来源日期：2026-10-03
    'g2_ev_opt': PARAMETER_REFERENCES['g2_ev_opt'],  # 交付目标只有一年，长期增长为零
    't_opt': 2026,  # 兑现年 = 公司目标年；早于分子年 → 折现年数取 0；A18；来源日期：2026-01-03
    't_num': 2027,  # 分子年（FY2027E）；期权折现起点；来源日期：2026-09-14
    'tau_yr': 0.5,  # 时点对齐年数 τ = 估值基准日 2026-06-30 → 分子年初 2027-01-01；手机 / 生态两腿与 \(V_{opt}\) 按 r 折 τ，窗口可分配利润折 τ/2（A25）；来源日期：2026-06-30
    'nci_cny': 1.195,  # 少数股东权益（中报；yfinance 季报 119,490 千元）；旧研究据此估算集团归母比例 0.99956，不代表已核实各项资产的实际归属；来源日期：2026-06-30
    'ss_return_eco': 0.263,  # 生态腿新投资**稳态回报** = 自身周期：FY2019–22 谷到谷（汽车量产前最后一轮完整周期）公司级投入资本回报均值 26.3%（税后核心经营利润 ÷ 年初（总权益 + 借款 − 现金类 − 投资组合 + 经营所需现金 16.5% × 收入）；年读数 14.3 / 22.3 / 61.0 / 7.6%；东财 F10 港股年报）；低于三档前瞻 → 进值（A25 ③）；来源日期：2026-10-19
    't0_ret': 2027,  # 分子年（回报路径第 1 年，A25 ③）；来源日期：2026-10-19
    'y1_ret': 2027,  # 高回报期止点 = 可见年末（默认，A25 ③）；来源日期：2026-10-19
    'y2_ret': 2031,  # 回落止点 = Y1 + 4（进入门槛「中」，A25 ③）；来源日期：2026-10-19
}

# Both rates are basket 4. The vehicle rate applies only to the incremental
# delivery option; the vehicle baseline is valued using peer sales multiples.
BASKETS = {"r_perp": 4, "r_ev": 4}
# Subjective credit, not a statistically estimated probability. The 25% middle
# case was agreed 2026-09-11 because consensus delivery was below the target.
CREDIT_REFERENCE = {"L": 0.0, "M": 0.25, "H": 1.0}
OPTION_CREDITS = dict(CREDIT_REFERENCE)

# Historical 2026-10-19 valuation: car price/sales ratios from the 2026-09-11
# peer sample (Leapmotor, Li Auto, BYD); the 2028 group growth from one broker's
# 23/16-1 forecast (2026-08-20). These PS values are NOT EV/sales and cannot
# fill the corrected model's enterprise-value inputs. The old group earnings
# include the separately valued vehicle business, so the historical output is
# explicitly flagged and is not the corrected model's current valuation.
HISTORICAL_REFERENCE = {'g1_fy28_ms': .4375, 'ps_ev_l': .555,
                        'ps_ev_m': .758, 'ps_ev_h': .813}


# ---------------------------------------------------------------- computation

def path_pe(g1: float, n: int, g2: float, roe: float, r: float, r_s: float, v: dict[str, float]) -> float:
    """Return fade uses the shared model; shrinking business payouts cap at earnings.

    The prior implementation distributed more than earnings when g2 was
    negative.  The shared path corrects that sensitivity case; the adopted
    positive-growth scenarios are unchanged.  This is a formula correction,
    not a change in an externally sourced observation.
    """
    return return_path_pe(int(v["t0_ret"]), int(v["y1_ret"]), int(v["y2_ret"]),
                          r_s, g2, roe, r, growth_first=g1, transition_years=int(n))


def compute(v: dict[str, float], candidate: bool = False, flat_at_m: bool = False) -> dict:
    """Rebuild every leg from the model inputs on the chosen valuation basis."""
    r = v["r_perp"]
    # Step 1: historical segment operating-loss estimate for reconciliation.
    opex_core_h1 = v["rev_core_q1"] * v["opex_ratio_q1"] + v["rev_core_q2"] * v["opex_ratio_q2"]
    opex_ev_h1 = v["opex_total_h1"] - opex_core_h1
    op_core_h1 = v["gp_core_h1"] - opex_core_h1
    op_ev_h1 = v["gp_ev_h1"] - opex_ev_h1

    # Keep historical segment operations, modelled future economics and their
    # tax/ownership bridge together; none is a published segment forecast.
    def segment_net(operating_profit: float) -> float:
        rate = v["ev_ai_profit_tax_rate"] if operating_profit >= 0 else v["ev_ai_loss_tax_benefit"]
        return operating_profit * (1.0 - rate) * v["ev_ai_parent_share"]

    ev_h1 = segment_net(op_ev_h1)
    ev_h2_revenue = ((v["ev_units_fy26e"] - v["ev_ai_h1_units"]) * v["ev_ai_h2_asp_cny"] / YI
                     + v["ev_ai_h2_other_revenue"])
    ev_h2 = segment_net(ev_h2_revenue * v["ev_ai_h2_gross_margin"] - v["ev_ai_h2_expenses"])
    ev_fy27 = {}
    for tier in BANDS:
        revenue = (v[f"ev_ai_fy27_units_{tier}"] * v[f"ev_ai_fy27_asp_{tier}"] / YI
                   + v["ev_ai_fy27_other_revenue"])
        ev_fy27[tier] = segment_net(revenue * v[f"ev_ai_fy27_margin_{tier}"] - v["ev_ai_fy27_expenses"])

    strip_h1 = v["sbc_h1"] + v["nonoperating_finance_net_h1"]
    core_np_rr = 2.0 * (v["adj_np_h1"] - ev_h1 - strip_h1)
    np_rr = 2.0 * (v["adj_np_h1"] - strip_h1)  # run-rate whole company

    # Step 2: consensus numerator, split by gross-profit weight
    w_phone = v["gp_phone_h1"] / v["gp_core_h1"]
    ni = {b: v[f"eps27_{b}_cny"] * v["shares"] / YI - 2.0 * strip_h1
          - ev_fy27[b] for b in BANDS}

    # Step 3: operating net assets and Gordon multiples
    net_cash = v["cash_like"] - v["debt"]
    equity_op = (v["equity_cny"] - v["net_cash_parent_cny"] - v["invest_parent_cny"]
                 - v["ev_ai_operating_equity_h126"])
    eq_phone = equity_op * w_phone
    eq_eco = equity_op * (1.0 - w_phone)

    rev_ev = v["ev_units_fy26e"] * v["ev_asp_cny"] / YI + v["ev_other_rev"]
    per_share = v["fx_cny_hkd"] * YI / v["shares"]

    # ROE = E_{n+1} / B_n: each leg's FY27E numerator over its operating net
    # assets at the OPENING of FY2027 (= end-2026), not the 1H26 figure and not
    # the end-2027 one (valuation-rules 裁决表 ② as of 2026-09-21; A24).
    # The 1H26 operating net assets are rolled over the 2H26 earnings not yet
    # booked -- FY2026E consensus on the same SBC / net-financial strip, minus
    # the 1H26 actual -- split by the same gross-profit weight, at the
    # GROWTH-REQUIRED retention b1 = g/ROE (the leg's g2 in the deck, or the
    # separately sourced core-business g1 in the candidate band).  Closed
    # form B = B0 / (1 - g N / E); FY2027's own retention is NOT rolled.
    # Phone g2 = 0 => b1 = 0, its book does not move in the deck.
    group_unbooked = v["eps26_m_cny"] * v["shares"] / YI - 2.0 * strip_h1 - (v["adj_np_h1"] - strip_h1)
    unbooked = group_unbooked - ev_h2
    g_roll = {"phone": v["g1_fy28_core"] if candidate else v["g2_phone"],
              "eco": v["g1_fy28_core"] if candidate else v["g2_eco"]}
    # A shrinking business does not automatically release capital in the
    # pre-valuation window; any actual release requires separate evidence.
    retention_growth = {leg: max(0.0, growth) for leg, growth in g_roll.items()}

    def multiples(b: str) -> dict[str, float]:
        ni_ph, ni_ec = ni[b] * w_phone, ni[b] * (1.0 - w_phone)
        eq_ph_open = eq_phone / (1.0 - retention_growth["phone"] * unbooked * w_phone / ni_ph)
        eq_ec_open = eq_eco / (1.0 - retention_growth["eco"] * unbooked * (1.0 - w_phone) / ni_ec)
        roe_ph = ni_ph / eq_ph_open
        roe_ec = ni_ec / eq_ec_open
        if candidate:
            n = int(v["n_fy28_cand"])
            pe_ph = two_stage_pe(v["g1_fy28_core"], n, v["g2_phone"], roe_ph, r)
            pe_ec = path_pe(v["g1_fy28_core"], n, v["g2_eco"], roe_ec, r, max(v["ss_return_eco"], r), v)
        else:
            pe_ph = perpetual_pe(v["g2_phone"], roe_ph, r)
            # eco: steady return 按序取 = own cycle (A25 ③), path Y1 -> Y2
            pe_ec = path_pe(0.0, 0, v["g2_eco"], roe_ec, r, max(v["ss_return_eco"], r), v)
        b1_ec = retention_growth["eco"] / roe_ec
        return {"pe_phone": pe_ph, "pe_eco": pe_ec, "roe_eco": roe_ec, "roe_phone": roe_ph,
                "eq_eco_open": eq_ec_open, "b1_eco": b1_ec, "b1_phone": retention_growth["phone"] / roe_ph,
                # B bucket (disclosure only): actual retention beyond b1 on the eco share of 2H26
                "excess_eco": ((1.0 - v["payout_3y"]) - b1_ec) * unbooked * (1.0 - w_phone)}

    pe_m = multiples("m")
    # 时点对齐 (valuation-rules「经营价值与超额现金」③): both Gordon legs are values at the
    # opening of FY2027 (t_n); today = base date 2026-06-30 -> x (1+r)^-tau, plus the window
    # distributable profit = the 2H26 unbooked operating profit x (1 - b), b the roll's b1 per
    # leg, discounted (1+r)^-(tau/2).  The EV PS leg and the closing item are today's values.
    f_tau = (1.0 + r) ** -v["tau_yr"]
    f_win = (1.0 + r) ** (-v["tau_yr"] / 2.0)
    # 归母份额: net cash x equity / (equity + NCI) (no subsidiary-level cash disclosure)
    tiers: dict[str, dict[str, float]] = {}
    for b in BANDS:
        mult = multiples(b)
        pe_ph, pe_ec, roe_ec = mult["pe_phone"], mult["pe_eco"], mult["roe_eco"]
        if flat_at_m:
            pe_ph, pe_ec = pe_m["pe_phone"], pe_m["pe_eco"]
            ps, d = v["ev_sales_m"], v["d_invest_m"]
        else:
            ps, d = v[f"ev_sales_{b}"], v[f"d_invest_{b}"]
        ni_phone = ni[b] * w_phone
        ni_eco = ni[b] * (1.0 - w_phone)
        mb = multiples(b)
        win_ph = unbooked * w_phone * (1.0 - mb["b1_phone"])
        win_ec = unbooked * (1.0 - w_phone) * (1.0 - mb["b1_eco"])
        phone = ni_phone * pe_ph * f_tau + win_ph * f_win
        eco = ni_eco * pe_ec * f_tau + win_ec * f_win
        ev = rev_ev * ps
        closing = v["net_cash_parent_cny"] + v["invest_parent_cny"] * (1.0 - d)
        tiers[b] = {
            "ni": ni[b], "ni_phone": ni_phone, "ni_eco": ni_eco,
            "pe_phone": pe_ph, "pe_eco": pe_ec, "roe_eco": roe_ec,
            "eq_eco_open": mult["eq_eco_open"], "b1_eco": mult["b1_eco"], "b1_phone": mult["b1_phone"],
            "roe_eco_old": ni_eco / eq_eco, "excess_eco": mult["excess_eco"],
            "blend": w_phone * pe_ph + (1.0 - w_phone) * pe_ec,
            "phone": phone * per_share, "eco": eco * per_share, "ev": ev * per_share,
            "closing": closing * per_share,
            "total": (phone + eco + ev + closing) * per_share,
        }

    L, M, H = (tiers[b]["total"] for b in BANDS)
    # A18: own named quantity (2026 delivery target minus the consensus already
    # in the EV leg) x own unit economics (1H26 EV segment gross margin, taxed),
    # on the EV leg's own ruler (basket 4 since 2026-10-03, g2 = 0 -> 1/r), timed and discounted.
    gm_ev = v["gp_ev_h1"] / v["rev_ev_h1"]
    # Only deliveries above the consensus already in the car leg are additional.
    # The company's target is independent of changes in the analyst consensus.
    opt_units = max(0.0, v["delivery_target_fy26"] - v["ev_units_fy26e"])
    opt_rev = opt_units * v["ev_asp_cny"] / YI  # 亿 CNY / yr
    opt_np = opt_rev * gm_ev * (1.0 - v["tax_rate"])
    pe_opt = perpetual_pe(v["g2_ev_opt"], 1.0, v["r_ev"])  # g2 = 0 -> 1/r, ROE not consumed
    disc_years = max(0.0, v["t_opt"] - v["t_num"])
    # valued at the numerator year's opening -> same tau to the base date (时点对齐)
    v_opt = (opt_np * pe_opt / (1.0 + v["r_ev"]) ** disc_years * per_share
             * (1.0 + v["r_ev"]) ** -v["tau_yr"])

    return {
        "opex_core_h1": opex_core_h1, "opex_ev_h1": opex_ev_h1,
        "op_core_h1": op_core_h1, "op_ev_h1": op_ev_h1,
        "core_np_rr": core_np_rr, "np_rr": np_rr, "strip_h1": strip_h1,
        "ev_ai_h1_net": ev_h1, "ev_ai_h2_net": ev_h2,
        "ev_ai_fy27_net": {tier.upper(): ev_fy27[tier] for tier in BANDS},
        "w_phone": w_phone, "equity_op": equity_op, "eq_eco": eq_eco, "unbooked": unbooked, "g_roll": g_roll,
        "rev_ev": rev_ev, "net_cash": net_cash, "per_share": per_share,
        "tiers": tiers, "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
        "gm_ev": gm_ev, "opt_units": opt_units, "opt_rev": opt_rev, "opt_np": opt_np, "pe_opt": pe_opt,
        "disc_years": disc_years, "V_opt": v_opt,
    }


def historical_compute(v: dict[str, float], candidate: bool = False, flat_at_m: bool = False) -> dict:
    """Historical 2026-10-19 model; the overlapping valuation remains explicitly flagged."""
    r = v["r_perp"]
    # Step 1: 1H26 segment recompute (reconciliation, weights, A4' bound)
    opex_core_h1 = v["rev_core_q1"] * v["opex_ratio_q1"] + v["rev_core_q2"] * v["opex_ratio_q2"]
    opex_ev_h1 = v["opex_total_h1"] - opex_core_h1
    op_core_h1 = v["gp_core_h1"] - opex_core_h1
    op_ev_h1 = v["gp_ev_h1"] - opex_ev_h1
    strip_h1 = v["sbc_h1"] + v["fin_net_h1"] * (1.0 - v["tax_rate"])
    core_np_rr = 2.0 * (v["adj_np_h1"] - op_ev_h1 - strip_h1)  # run-rate core, EV loss added back
    np_rr = 2.0 * (v["adj_np_h1"] - strip_h1)  # run-rate whole company

    # Step 2: consensus numerator, split by gross-profit weight
    w_phone = v["gp_phone_h1"] / v["gp_core_h1"]
    ni = {b: v[f"eps27_{b}_cny"] * v["shares"] / YI - 2.0 * strip_h1 for b in BANDS}

    # Step 3: operating net assets and Gordon multiples
    net_cash = v["cash_like"] - v["debt"]
    equity_op = v["equity_cny"] - net_cash - v["invest_cny"]
    eq_phone = equity_op * w_phone
    eq_eco = equity_op * (1.0 - w_phone)

    rev_ev = v["ev_units_fy26e"] * v["ev_asp_cny"] / YI + v["ev_other_rev"]
    per_share = v["fx_cny_hkd"] * YI / v["shares"]

    # ROE = E_{n+1} / B_n: each leg's FY27E numerator over its operating net
    # assets at the OPENING of FY2027 (= end-2026), not the 1H26 figure and not
    # the end-2027 one (valuation-rules 裁决表 ② as of 2026-09-21; A24).
    # The 1H26 operating net assets are rolled over the 2H26 earnings not yet
    # booked -- FY2026E consensus on the same SBC / net-financial strip, minus
    # the 1H26 actual -- split by the same gross-profit weight, at the
    # GROWTH-REQUIRED retention b1 = g/ROE (the leg's g2 in the deck, the MS g1
    # in the candidate band), never at the actual payout complement.  Closed
    # form B = B0 / (1 - g N / E); FY2027's own retention is NOT rolled.
    # Phone g2 = 0 => b1 = 0, its book does not move in the deck.
    unbooked = v["eps26_m_cny"] * v["shares"] / YI - 2.0 * strip_h1 - (v["adj_np_h1"] - strip_h1)  # 亿, 2H26 only
    g_roll = {"phone": v["g1_fy28_ms"] if candidate else v["g2_phone"],
              "eco": v["g1_fy28_ms"] if candidate else v["g2_eco"]}

    def multiples(b: str) -> dict[str, float]:
        ni_ph, ni_ec = ni[b] * w_phone, ni[b] * (1.0 - w_phone)
        eq_ph_open = eq_phone / (1.0 - g_roll["phone"] * unbooked * w_phone / ni_ph)
        eq_ec_open = eq_eco / (1.0 - g_roll["eco"] * unbooked * (1.0 - w_phone) / ni_ec)
        roe_ph = ni_ph / eq_ph_open
        roe_ec = ni_ec / eq_ec_open
        if candidate:
            n = int(v["n_fy28_cand"])
            pe_ph = two_stage_pe(v["g1_fy28_ms"], n, v["g2_phone"], roe_ph, r)
            pe_ec = path_pe(v["g1_fy28_ms"], n, v["g2_eco"], roe_ec, r, max(v["ss_return_eco"], r), v)
        else:
            pe_ph = perpetual_pe(v["g2_phone"], roe_ph, r)
            # eco: steady return 按序取 = own cycle (A25 ③), path Y1 -> Y2
            pe_ec = path_pe(0.0, 0, v["g2_eco"], roe_ec, r, max(v["ss_return_eco"], r), v)
        b1_ec = g_roll["eco"] / roe_ec
        return {"pe_phone": pe_ph, "pe_eco": pe_ec, "roe_eco": roe_ec, "roe_phone": roe_ph,
                "eq_eco_open": eq_ec_open, "b1_eco": b1_ec, "b1_phone": g_roll["phone"] / roe_ph,
                # B bucket (disclosure only): actual retention beyond b1 on the eco share of 2H26
                "excess_eco": ((1.0 - v["payout_3y"]) - b1_ec) * unbooked * (1.0 - w_phone)}

    pe_m = multiples("m")
    # 时点对齐 (valuation-rules「经营价值与超额现金」③): both Gordon legs are values at the
    # opening of FY2027 (t_n); today = base date 2026-06-30 -> x (1+r)^-tau, plus the window
    # distributable profit = the 2H26 unbooked operating profit x (1 - b), b the roll's b1 per
    # leg, discounted (1+r)^-(tau/2).  The EV PS leg and the closing item are today's values.
    f_tau = (1.0 + r) ** -v["tau_yr"]
    f_win = (1.0 + r) ** (-v["tau_yr"] / 2.0)
    # 归母份额: net cash x equity / (equity + NCI) (no subsidiary-level cash disclosure)
    parent = v["equity_cny"] / (v["equity_cny"] + v["nci_cny"])
    tiers: dict[str, dict[str, float]] = {}
    for b in BANDS:
        mult = multiples(b)
        pe_ph, pe_ec, roe_ec = mult["pe_phone"], mult["pe_eco"], mult["roe_eco"]
        if flat_at_m:
            pe_ph, pe_ec = pe_m["pe_phone"], pe_m["pe_eco"]
            ps, d = v["ps_ev_m"], v["d_invest_m"]
        else:
            ps, d = v[f"ps_ev_{b}"], v[f"d_invest_{b}"]
        ni_phone = ni[b] * w_phone
        ni_eco = ni[b] * (1.0 - w_phone)
        mb = multiples(b)
        win_ph = unbooked * w_phone * (1.0 - mb["b1_phone"])
        win_ec = unbooked * (1.0 - w_phone) * (1.0 - mb["b1_eco"])
        phone = ni_phone * pe_ph * f_tau + win_ph * f_win
        eco = ni_eco * pe_ec * f_tau + win_ec * f_win
        ev = rev_ev * ps
        closing = net_cash * parent + v["invest_cny"] * (1.0 - d)
        tiers[b] = {
            "ni": ni[b], "ni_phone": ni_phone, "ni_eco": ni_eco,
            "pe_phone": pe_ph, "pe_eco": pe_ec, "roe_eco": roe_ec,
            "eq_eco_open": mult["eq_eco_open"], "b1_eco": mult["b1_eco"], "b1_phone": mult["b1_phone"],
            "roe_eco_old": ni_eco / eq_eco, "excess_eco": mult["excess_eco"],
            "blend": w_phone * pe_ph + (1.0 - w_phone) * pe_ec,
            "phone": phone * per_share, "eco": eco * per_share, "ev": ev * per_share,
            "closing": closing * per_share,
            "total": (phone + eco + ev + closing) * per_share,
        }

    L, M, H = (tiers[b]["total"] for b in BANDS)
    # A18: own named quantity (2026 delivery target minus the consensus already
    # in the EV leg) x own unit economics (1H26 EV segment gross margin, taxed),
    # on the EV leg's own ruler (basket 4 since 2026-10-03, g2 = 0 -> 1/r), timed and discounted.
    gm_ev = v["gp_ev_h1"] / v["rev_ev_h1"]
    opt_rev = v["opt_units"] * v["ev_asp_cny"] / YI  # 亿 CNY / yr
    opt_np = opt_rev * gm_ev * (1.0 - v["tax_rate"])
    pe_opt = perpetual_pe(v["g2_ev_opt"], 1.0, v["r_ev"])  # g2 = 0 -> 1/r, ROE not consumed
    disc_years = max(0.0, v["t_opt"] - v["t_num"])
    # valued at the numerator year's opening -> same tau to the base date (时点对齐)
    v_opt = (opt_np * pe_opt / (1.0 + v["r_ev"]) ** disc_years * per_share
             * (1.0 + v["r_ev"]) ** -v["tau_yr"])

    return {
        "opex_core_h1": opex_core_h1, "opex_ev_h1": opex_ev_h1,
        "op_core_h1": op_core_h1, "op_ev_h1": op_ev_h1,
        "core_np_rr": core_np_rr, "np_rr": np_rr, "strip_h1": strip_h1,
        "w_phone": w_phone, "equity_op": equity_op, "eq_eco": eq_eco, "unbooked": unbooked, "g_roll": g_roll,
        "rev_ev": rev_ev, "net_cash": net_cash, "per_share": per_share,
        "tiers": tiers, "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
        "gm_ev": gm_ev, "opt_rev": opt_rev, "opt_np": opt_np, "pe_opt": pe_opt,
        "disc_years": disc_years, "V_opt": v_opt,
    }


# ---------------------------------------------------------------- main

def evaluate(v: dict[str, float], rate_inputs: dict | None = None) -> tuple[int, dict | None]:
    missing = [key for key in REQUIRED if key not in v]
    def finite_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    invalid = [key for key, value in v.items() if not finite_number(value)]
    credit_keys = ("L", "M", "H")
    invalid_credits = [key for key in credit_keys if key not in OPTION_CREDITS
                       or not finite_number(OPTION_CREDITS[key])]
    if missing or invalid or invalid_credits:
        print(f"FAIL: missing inputs {missing}; invalid inputs {invalid}; "
              f"invalid option credits {invalid_credits}", file=sys.stderr)
        return 1, None
    derived_segment = {"ev_ai_h126", "ev_ai_fy26", "ev_ai_fy27_l", "ev_ai_fy27_m", "ev_ai_fy27_h"} & v.keys()
    if derived_segment:
        print(f"FAIL: derived segment profit must be calculated from assumptions: {sorted(derived_segment)}",
              file=sys.stderr)
        return 1, None
    segment_nonnegative = (
        "ev_ai_h1_units", "ev_ai_h2_asp_cny", "ev_ai_h2_other_revenue", "ev_ai_h2_expenses",
        "ev_ai_fy27_units_l", "ev_ai_fy27_units_m", "ev_ai_fy27_units_h",
        "ev_ai_fy27_asp_l", "ev_ai_fy27_asp_m", "ev_ai_fy27_asp_h",
        "ev_ai_fy27_other_revenue", "ev_ai_fy27_expenses",
    )
    bad_segment = [key for key in segment_nonnegative if v[key] < 0]
    margins = ("ev_ai_h2_gross_margin", "ev_ai_fy27_margin_l", "ev_ai_fy27_margin_m", "ev_ai_fy27_margin_h")
    # Gross margin can be negative when cost exceeds revenue; only the upper
    # bound follows from non-negative cost. The source still needs review.
    bad_segment += [key for key in margins if v[key] > 1]
    for key in ("ev_ai_profit_tax_rate", "ev_ai_loss_tax_benefit", "tax_rate"):
        if not 0 <= v[key] <= 1:
            bad_segment.append(key)
    if not 0 < v["ev_ai_parent_share"] <= 1:
        bad_segment.append("ev_ai_parent_share")
    if v["ev_ai_h1_units"] > v["ev_units_fy26e"]:
        bad_segment.append("ev_ai_h1_units")
    if bad_segment:
        print(f"FAIL: invalid segment assumptions {bad_segment}", file=sys.stderr)
        return 1, None
    fractional_years = [key for key in ("t0_ret", "y1_ret", "y2_ret", "n_fy28_cand")
                        if not float(v[key]).is_integer()]
    if fractional_years:
        print(f"FAIL: model years must be integers: {fractional_years}", file=sys.stderr)
        return 1, None
    has_candidate = "g1_fy28_core" in v
    if has_candidate and (not isinstance(CANDIDATE_LABEL, str) or not CANDIDATE_LABEL.strip()):
        print("FAIL: candidate label is required", file=sys.stderr)
        return 1, None
    c = compute(v)
    cand = compute(v, candidate=True) if has_candidate else None
    fc = compute(v, flat_at_m=True)
    T = c["tiers"]

    errors: list[str] = []
    baskets = BASKETS
    if "r_perp" not in baskets:
        errors.append("r_perp: no risk basket declared")
    errors += (check_r(v["r_perp"], "r_perp", baskets.get("r_perp"))
               + check_g_cap(v["g2_phone"], v["r_perp"], "g2_phone")
               + check_g_cap(v["g2_eco"], v["r_perp"], "g2_eco")
               + check_r(v["r_ev"], "r_ev", baskets.get("r_ev"))
               + check_g_cap(v["g2_ev_opt"], v["r_ev"], "g2_ev_opt"))

    def require(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    require(v["eps27_l_cny"] < v["eps27_m_cny"] < v["eps27_h_cny"], "EPS ladder not ordered")
    require(all(T[b]["ni"] > 0 for b in BANDS), "operating earnings must be positive")
    if v["g2_phone"] == 0:
        require(abs(T["l"]["pe_phone"] - T["m"]["pe_phone"]) < 1e-9
                and abs(T["m"]["pe_phone"] - T["h"]["pe_phone"]) < 1e-9,
                "zero-growth phone multiples must be equal")
    require(v["g2_ev_opt"] == 0, "nonzero option growth needs an explicit return assumption")
    require(v["ev_sales_l"] >= 0, "vehicle EV/sales must be non-negative")
    require(v["ev_sales_l"] <= v["ev_sales_m"] <= v["ev_sales_h"], "vehicle EV/sales ladder not ordered")
    require(v["d_invest_l"] > v["d_invest_m"] > v["d_invest_h"] >= 0,
            "investment discount ladder not ordered")
    require(0 < c["w_phone"] < 1, "phone allocation must be between 0 and 1")
    require(c["equity_op"] > 0, "operating net assets must be positive")
    require(c["unbooked"] > 0, "unbooked operating earnings must be positive")
    for b in BANDS:
        require(0.0 <= T[b]["b1_phone"] < 1.0 and 0.0 <= T[b]["b1_eco"] < 1.0
                and (cand is None or (0.0 <= cand["tiers"][b]["b1_eco"] < 1.0
                                      and 0.0 <= cand["tiers"][b]["b1_phone"] < 1.0)),
                f"retention outside range for {b.upper()}")
    require(c["L"] < c["M"] < c["H"], "base anchors not ordered")
    require(fc["L"] < fc["M"] < fc["H"], "flat-multiple anchors not ordered")
    for tier in ("L", "M", "H"):
        own = c[tier] / v["eps_ttm_gaap"]
        require(v["pe_own_min"] - 1e-9 <= own <= v["pe_own_max"] + 1e-9,
                f"historical PE guard failed for {tier}")
    require(OPTION_CREDITS["L"] == 0 and OPTION_CREDITS["H"] == 1, "option credit endpoints invalid")
    require(0 <= OPTION_CREDITS["M"] <= 1, "option middle credit outside range")
    require(math.isfinite(c["V_opt"]) and c["V_opt"] >= 0, "option value invalid")
    if cand is not None:
        require(cand["L"] < cand["M"] < cand["H"], "candidate anchors not ordered")
    require(not [key for key in v if key == "p" or key.startswith("p_")],
            "option credits cannot enter base inputs")

    # Preserve the original cross-checks numerically instead of printing them.
    lt = T["l"]
    ev_l = c["rev_ev"] * v["ev_sales_l"]
    cl_l = v["net_cash_parent_cny"] + v["invest_parent_cny"] * (1.0 - v["d_invest_l"])

    def band_rf(dr: float) -> tuple[float, float, float]:
        alt_rf = compute(dict(v, r_perp=v["r_perp"] + dr))
        return alt_rf["L"], alt_rf["M"], alt_rf["H"]

    rf = None
    if rate_inputs is not None:
        rf = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp': v['r_perp']}, band_at=band_rf,
            rates_loader=lambda currency: rate_inputs,
            base_anchors=(c['L'], c['M'], c['H'])))
    require(all(abs(x - y) <= TOL for x, y in zip(band_rf(0.0), (c["L"], c["M"], c["H"]))),
            "zero rate shift does not reproduce base anchors")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1, None

    def values(key: str) -> dict[str, float]:
        return {tier.upper(): T[tier][key] for tier in BANDS}

    def anchors(result: dict) -> dict[str, float]:
        return {tier: result[tier] for tier in ("L", "M", "H")}

    def repeated(value: float) -> dict[str, float]:
        return {tier: value for tier in ("L", "M", "H")}

    # The output contains numeric results and stable codes. Sources, reasons,
    # and historical decisions live in the input and model comments above;
    # the reader-facing framework is the agent's own explanation of these values.
    parameter_rows = {
        "eps_fy27": {"unit": "CNY_PER_SHARE",
                     "values": {tier.upper(): v[f"eps27_{tier}_cny"] for tier in BANDS},
                     "reference_values": {"L": EPS_ESTIMATES["low"], "M": EPS_ESTIMATES["mean"],
                                          "H": EPS_ESTIMATES["high"]}},
        "phone_growth_rate": {"unit": "RATIO", "values": repeated(v["g2_phone"]),
                              "selected_value": v["g2_phone"],
                              "reference_value": PARAMETER_REFERENCES["g2_phone"]},
        "ecosystem_growth_rate": {"unit": "RATIO", "values": repeated(v["g2_eco"]),
                                  "selected_value": v["g2_eco"],
                                  "reference_value": PARAMETER_REFERENCES["g2_eco"]},
        "discount_rate": {"unit": "RATIO", "values": repeated(v["r_perp"])},
        "ecosystem_forward_return": {"unit": "RATIO", "values": values("roe_eco")},
        "ecosystem_steady_return": {
            "unit": "RATIO", "values": {tier.upper(): min(T[tier]["roe_eco"], v["ss_return_eco"])
                                        for tier in BANDS},
            "selected_value": v["ss_return_eco"], "reference_value": PARAMETER_REFERENCES["ss_return_eco"]},
        "vehicle_ev_sales": {"unit": "MULTIPLE", "values": {tier.upper(): v[f"ev_sales_{tier}"] for tier in BANDS}},
        "investment_discount": {"unit": "RATIO", "values": {tier.upper(): v[f"d_invest_{tier}"] for tier in BANDS},
                                "reference_values": {tier.upper(): PARAMETER_REFERENCES[f"d_invest_{tier}"]
                                                     for tier in BANDS}},
        "candidate_growth_rate": {"unit": "RATIO", "selected_value": v.get("g1_fy28_core")},
    }
    # The +/- 1pp cases are deliberately hypothetical; -0.98% is the dated
    # peer result excluding Tencent. Neither alters the adopted estimate.
    growth_cases = [{"value": growth, "anchors": anchors(compute(dict(v, g2_eco=growth)))}
                    for growth in (v["g2_eco"] - 0.01, v["g2_eco"] + 0.01, -0.0098)]
    eps_case = compute(dict(v, eps27_m_cny=v["eps27_m_cny"] + 0.1))
    base_anchors = anchors(c)
    option_anchors = {tier: base_anchors[tier] + c["V_opt"] * OPTION_CREDITS[tier]
                      for tier in ("L", "M", "H")}
    post = (1.0 + v["g1_fy28_core"]) ** int(v["n_fy28_cand"]) if cand else None
    cross_checks = {
        "base_model": c,
        "candidate_model": cand,
        "flat_model": fc,
        "retained_cash_per_share": {b.upper(): T[b]["excess_eco"] * c["per_share"] for b in BANDS},
        "candidate_multiples": {
            leg: {"numerator_year": {b.upper(): cand["tiers"][b][leg] for b in BANDS},
                  "post_transition": {b.upper(): cand["tiers"][b][leg] / post for b in BANDS}}
            for leg in ("pe_phone", "pe_eco")
        } if cand else None,
        "flat_width": (fc["H"] - fc["L"]) / (2 * fc["M"]),
        "decomposition": {
            tier.upper(): {"anchor_ratio": c[tier.upper()] / c["M"],
                           "earnings_ratio": T[tier]["ni"] / T["m"]["ni"],
                           "blended_multiple_ratio": T[tier]["blend"] / T["m"]["blend"],
                           "vehicle_ev_sales_ratio": (v[f"ev_sales_{tier}"] / v["ev_sales_m"]
                                                      if v["ev_sales_m"] else None),
                           "investment_retained_ratio": (1 - v[f"d_invest_{tier}"]) / (1 - v["d_invest_m"])}
            for tier in ("l", "h")
        },
        "historical_pe": {tier: c[tier] / v["eps_ttm_gaap"] for tier in ("L", "M", "H")},
        "historical_pe_bounds": {"low": v["pe_own_min"], "high": v["pe_own_max"]},
        "option_to_middle": c["V_opt"] / c["M"],
        "pressure": {
            "core_l_multiple": c["core_np_rr"] * lt["blend"] * c["per_share"] + (ev_l + cl_l) * c["per_share"],
        },
    }
    result = {
        "ticker": "1810.HK", "currency": "HKD",
        "units": {"price": "HKD_PER_SHARE", "amount": "CNY_100M", "ratio": "RATIO",
                  "eps": "CNY_PER_SHARE", "shares": "SHARES", "delivery": "VEHICLES"},
        "valuation_as_of": None,
        "framework_as_of": None,
        "anchors": base_anchors,
        "candidate": {"label": CANDIDATE_LABEL, "anchors": anchors(cand)} if cand else None,
        "option": {
            "value": c["V_opt"], "value_unit": "HKD_PER_SHARE", "credits": dict(OPTION_CREDITS), "anchors": option_anchors,
            "parameters": {"discount_rate": v["r_ev"], "growth_rate": v["g2_ev_opt"], "return_rate": None},
            "delivery_target": v["delivery_target_fy26"], "delivery_consensus": v["ev_units_fy26e"],
            "additional_units": c["opt_units"],
        },
        "segments": {"phone": {"values": values("phone")}, "ecosystem": {"values": values("eco")},
                     "vehicle": {"values": values("ev")}, "assets": {"values": values("closing")}},
        "key_parameters": parameter_rows,
        "cross_checks": cross_checks,
        "sensitivity": {
            "ecosystem_growth_rate": growth_cases,
            "eps_mean_delta": {"value": 0.1, "anchors": anchors(eps_case)},
        },
        "rate_sensitivity": rf,
    }
    return 0, result


def historical_result(inputs, rate_inputs):
    # Rebuild the old model rather than hardcoding its resulting band. These
    # ratios and the group's 2028 growth are historical, not inputs to the
    # corrected separate-vehicle model above.
    v = dict(inputs)
    v.update(HISTORICAL_REFERENCE)
    v['opt_units'] = max(0, v['delivery_target_fy26'] - v['ev_units_fy26e'])
    base = historical_compute(v)
    candidate = historical_compute(v, candidate=True)
    anchors = {tier: base[tier] for tier in ('L', 'M', 'H')}
    band = lambda result: {tier: result[tier] for tier in ('L', 'M', 'H')}
    rf = None
    if rate_inputs is not None:
        def band_rf(dr):
            shifted = historical_compute(dict(v, r_perp=v['r_perp'] + dr))
            return tuple(shifted[tier] for tier in ('L', 'M', 'H'))
        rf = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp': v['r_perp']}, band_at=band_rf,
            rates_loader=lambda currency: rate_inputs,
            base_anchors=tuple(anchors[tier] for tier in ('L', 'M', 'H'))))
    repeat = lambda value: {tier: value for tier in ('L', 'M', 'H')}
    eco_return = {tier.upper(): base['tiers'][tier]['roe_eco'] for tier in BANDS}
    params = {
        'phone': {'discount_rate': {'unit': 'RATIO', 'values': repeat(v['r_perp'])},
                  'growth_rate': {'unit': 'RATIO', 'values': repeat(v['g2_phone'])}},
        'ecosystem': {'discount_rate': {'unit': 'RATIO', 'values': repeat(v['r_perp'])},
                      'growth_rate': {'unit': 'RATIO', 'values': repeat(v['g2_eco'])},
                      'forward_return': {'unit': 'RATIO', 'values': eco_return},
                      'steady_return': {'unit': 'RATIO',
                          'values': {tier: min(value, max(v['ss_return_eco'], v['r_perp']))
                                     for tier, value in eco_return.items()},
                          'reference_value': v['ss_return_eco']}},
        'vehicle': {'valuation_multiple': {'unit': 'MULTIPLE',
                     'values': {tier.upper(): v[f'ps_ev_{tier}'] for tier in BANDS}}},
    }
    result = {
        'ticker': '1810.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'framework_as_of': None,
        'historical_financial_statement_as_of': '2026-06-30',
        'historical_research_as_of': '2026-10-19',
        'units': {'price': 'HKD_PER_SHARE'}, 'anchors': anchors,
        'candidate': {'label': '2028年集团增长', 'anchors': band(candidate)},
        'option': {'value': base['V_opt'], 'value_unit': 'HKD_PER_SHARE',
                   'anchors': {tier: anchors[tier] + OPTION_CREDITS[tier] * base['V_opt']
                               for tier in ('L', 'M', 'H')}},
        'segments': {name: {'unit': 'HKD_PER_SHARE', 'values': {
            tier.upper(): base['tiers'][tier][field] for tier in BANDS}}
            for name, field in (('phone', 'phone'), ('ecosystem', 'eco'),
                                ('vehicle', 'ev'), ('assets', 'closing'))},
        'key_parameters': params,
        'rate_sensitivity': rf,
        'review_flags': ['historical_double_counting', 'historical_cash_ownership_unverified',
                         'historical_peer_ps_cash_overlap_unverified',
                         'historical_candidate_group_growth_not_core',
                         'corrected_model_inputs_missing'],
    }
    return result


def calculate(context):
    values = dict(INPUTS)
    # Missing corrected inputs must not be guessed; the old, explicitly marked
    # historical model remains useful as a comparison during migration.
    if any(key not in values for key in REQUIRED):
        result = historical_result(values, context.get('rate_inputs'))
    else:
        status, result = evaluate(values, context.get('rate_inputs'))
        if status != 0 or result is None:
            raise ValueError('corrected Xiaomi model cannot calculate with its present inputs')
        result['historical_financial_statement_as_of'] = '2026-06-30'
        result['historical_research_as_of'] = '2026-10-19'
        result['review_flags'] = ['corrected_assumptions_require_research_review']
        for segment in result['segments'].values():
            segment['unit'] = 'HKD_PER_SHARE'
        parameters = result['key_parameters']
        parameters['phone'] = {'discount_rate': parameters['discount_rate'],
                               'growth_rate': parameters['phone_growth_rate']}
        parameters['ecosystem'] = {'discount_rate': parameters['discount_rate'],
                                   'growth_rate': parameters['ecosystem_growth_rate'],
                                   'forward_return': parameters['ecosystem_forward_return'],
                                   'steady_return': parameters['ecosystem_steady_return']}
        parameters['vehicle'] = {'valuation_multiple': parameters['vehicle_ev_sales']}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': values, 'historical_reference': HISTORICAL_REFERENCE,
         'option_credits': OPTION_CREDITS}, HISTORICAL_BASELINE)
    return result
