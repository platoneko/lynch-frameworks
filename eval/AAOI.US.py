#!/usr/bin/env python3
"""AAOI.US valuation calculation using the dated inputs in this script.

The historical reference anchors remain at the 2026-10-19 baseline. The
separate Q3 funding cases are unadopted research conditions, not revised anchors.
The human document is an explanation, not an input. Nothing here reads a quote.

formula_id: aaoi_fy27_gordon_basket_pair_floor_elsfp_opt_v1

Whole-company ruler (one reportable segment, no segment profit or assets, so
the CATV leg cannot be split — valuation-rules「归篮触发分腿」keeps the whole-
company ruler at the largest leg's basket and discloses the bias; the CATV
split is printed as a cross only).  Numerator FY2027 = furthest year with a
>=2-house consensus range (yfinance +1y, 5 houses), non-GAAP less SBC/share.
No transition year (no FY28 with >=2 houses).

Basket PAIR (valuation-rules「篮子对」, A15): today 篮 7 15% (FY25 single
customer 53.1%, top two 81.9%), terminal 篮 4 10%; n = 0, so the journey rate
only sets G_cap, discounts the option and is the merge fallback, and the risk
of never reaching the diversified steady state lives in k (A17), recomputed
here as 0.5 x (1 - PE@r_journey / PE@r_terminal).  g2 is the peer-ruler axis
value `_AXIS.pluggable-module` (cross-file checked).

L is the asset floor (A3, user decision 2026-10-06): the FY18-style digestion
scenario prints a negative EPS, so L = FY27 opening book per share.  Every
anchor then takes the holder-optimal lower of the diluted and the debt reading
of the 2030 convertible (A20).

Steady return three segments (valuation-rules「经营价值与超额现金」② 稳态回报三段,
2026-10-16 框架纠正, A23): the whole company rides `_AXIS.pluggable-module`'s
ss_return_plug / y1_plug / y2_plug (module assembly, medium barrier): forward
ROE through Y1 2028, linear to min(forward, 18%) at Y2 2032, Gordon tail after;
the shared return path in gordon.py supplies the calculation.
k 0.19 stays (user 2026-10-16: the basket-pair rule's mandatory "never arrives"
discount on the whole operating value is a named rule object) and is re-derived
on the path multiples.

Timing alignment (valuation-rules ③, A24): the Gordon value sits at the FY27
opening (2027-01-01); tau = balance-sheet date 2026-06-30 -> 0.5 year,
discounted at the JOURNEY rate (basket pair: the tau leg uses r_j).  L is the
asset floor (book at the FY27 opening) and is not moved.

Growth-period funding gap (valuation-rules ①, A25; user 2026-10-18 delegated
the reading to the assistant): G = H2-2026 capex (H1 PP&E purchases repeated)
+ the H1 equipment prepayment once - H2 operating cash flow read as H2
consensus NI + D&A (H1 actual D&A).  With a gap the window distributable profit
is 0 (OCF already holds the window profit).  Cash is not carried at face value
(C_ex < 0, no separate row), so only the part of G the usable cash cannot pay
(G - (extended net cash ex-convertible - operating cash anchor 0), floored at
0) is deducted per share as a debt-like item from M / H (and the candidate
band), before the holder-optimal convertible step.

Option (A13): ELSFP named capacity x Raymond James low price x a margin that
fades along the `_AXIS.inp-laser` laser-chip high-return window (shortage
margin through y1_inp 2029, linear to the normal margin at y2_inp 2035; user
2026-10-16, no step at t_shortage_end) with g2_inp_laser_normal and the
new-investment return fading from ROE_H to ss_return_inp, valued on this
ticker's ruler at H, discounted one year at the journey rate, less
full-capacity capital, then tau to today.  p_L / p_M / p_H are constants,
never Inputs.

Run through the shared valuation runner with explicitly selected roots.
"""

from __future__ import annotations

import math

from lib.gordon import (
    check_basket_pair,
    check_branch,
    check_g_cap,
    check_k_declared,
    check_transition_years,
    payout_gap,
    perpetual_pe,
    return_path_pe,
)
from lib.inputs import (
    check_missing,
)
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {"libraries": ("gordon", "inputs", "rf_report", "partial_basis"),
                "axes": {"pluggable": "pluggable_module", "inp_laser": "inp_laser"}}
BASELINE_LOCAL = "c7865e713de619d4afde32df68c84b023c989093fa47727dcdabecccb7423472"

FORMULA_ID = "aaoi_fy27_gordon_basket_pair_floor_elsfp_opt_v1"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
NUM_YEAR = 2027
N_STAGE = 0  # no FY28 with >=2 houses
FAIL_SHARE = 0.5  # A17: 无概率锚·拍值 — chance of never reaching the diversified steady state
K_TOL = 0.01
P_TIERS = (0.0, 0.0, 1.0)  # A13: no sell-side volume -> option only in H
MACRO_G = 0.04
TIERS = ("L", "M", "H")

# 2027 年调整后每股利润：yfinance，五家机构，2026-10-06；2026-11-06
# 查询仍未反映新财报。低值只作参考，保守估值采用账面价值。
EPS_ESTIMATES = {"low": 3.52, "mean": 4.60, "high": 8.08}
# 外置光源月产能（百万只）：公司 2026Q1 电话会要点稿转述，2026-05-07；
# 每只单价：Raymond James，经 Investing.com 转述的下沿，2026-06-10。
CAPACITY_AND_PRICE = {"units_month": 0.4, "price": 500.0}
# Raymond James 2026-06-10 单家产能年化估计，并非全年利润预测。
CANDIDATE_ESTIMATE = {"mean": 11.5, "high": 12.0}

# The historical reference is 2026-10-19; q3_* are separate unadopted
# post-earnings conditions. Amounts USD millions, shares millions.
INPUTS = {
    'eps_fy27_l': EPS_ESTIMATES['low'],  # FY2027 non-GAAP EPS 下沿；L 为资产地板，不入正式锚点。
    'eps_fy27_m': EPS_ESTIMATES['mean'],  # FY2027 non-GAAP EPS 均值，M 利润来源。
    'eps_fy27_h': EPS_ESTIMATES['high'],  # FY2027 non-GAAP EPS 上沿，H 利润来源。
    'rev_fy26_cons': 1038.4256,  # FY2026 收入共识均值（yfinance `0y`）= L 消化年的收入起点；A3 ；旧正式基准冻结，**共识待更新**；as-of 2026-10-06
    'rev_fy27_m': 2663.3365,  # FY2027 收入共识均值（yfinance `+1y`，4 家）；只算 CATV 交叉占比 ；旧正式基准冻结，**共识待更新**；as-of 2026-10-06
    'rev_fy27_h': 3526.3,  # FY2027 收入共识上沿；只算 CATV 交叉占比 ；旧正式基准冻结，**共识待更新**；as-of 2026-10-06
    'nm_fy25': -0.03434,  # FY2025 non-GAAP 净利率 = −0.26 × 60.184 ÷ 455.715（新闻稿 2026-02-26 / 10-K 加权股本）；L 情景（A3）；as-of 2025-12-31
    'rev_cut_l': 0.3,  # L 消化年收入回落 = FY18 实测 −30.04%（267.465 ÷ 382.329 − 1，10-K）；A3；as-of 2018-12-31
    'sbc_q2': 4.863,  # 2026Q2 股权激励（10-Q 现金流量表），× 4 年化；A1；as-of 2026-06-30
    'shares_dil': 92.8,  # 稀释股本（Q3 指引口径，含可转债 / 已归属认股权证）；A1；as-of 2026-08-06
    'equity_h1': 1668.025,  # 股东权益（10-Q 资产负债表）；as-of 2026-06-30
    'atm_post': 49.2,  # 6-30 后 ATM 增发毛额（332,428 股，424B5 Dilution 节）；as-of 2026-08-20
    'atm_fee': 0.02,  # ATM 佣金上限 2%（估计，实数 `待补`）；as-of 2026-08-21
    'warrant_vested': 1.324233,  # Amazon 认股权证已归属股数（百万股）；A20；as-of 2026-06-30
    'warrant_strike': 23.6956,  # 认股权证行权价（USD/股）；A20；as-of 2025-03-13
    'conv_carry': 129.1,  # 2030 可转债账面值（按股口径并入账面）；A20；as-of 2026-06-30
    'conv_principal': 124.925,  # 可转债本金；A20；as-of 2026-06-30
    'conv_rate': 23.0884,  # 转股比例（股 / $1,000 本金；转股价 $43.31）；A20；as-of 2026-06-30
    'ni_h2_cons': 39.9,  # FY26 下半年 GAAP 净利共识 = 长桥 `consensus` Q3 0.85 + Q4 39.05；滚账面 ；旧正式基准冻结，**共识待更新**；as-of 2026-10-06
    'r_journey': 0.15,  # 篮 7 单押：最近财年单一客户 Digicomm 53.1%、前两大 81.9%（10-K FY25）；今天的性质，决定 G_cap 与期权折现（A15）；as-of 2026-10-06
    'r_terminal': 0.1,  # 篮 4 常规经营：稳态客户分散后的光模块器件生意，盈利非商品价函数；资本化稳态（A15）；as-of 2026-10-06
    'r_catv_cross': 0.15,  # CATV 单列交叉读数用的 r（同 `r_journey`，不归篮；不进锚点）；as-of 2026-10-06
    'g2': 0.02,  # `_AXIS.pluggable-module`·可插拔模块腿永续增速（轴值：用户拍板 2%，低于具名宏观 4%，规则偏离随轴；A9）；三档 flat（`cyclical`）；as-of 2026-09-30
    'catv_rev_27': 325.0,  # CATV 年收入（公司口径「>$325M」，Q2'26 电话会）；只算交叉占比；as-of 2026-08-06
    'k_l': 0.0,  # L 是地板，k 不适用；A17；as-of 2026-10-06
    'k_m': 0.19,  # 篮子对「走不到稳态」= 0.5（拍值）× 38.5%；留存 k 为 0（D 桶）；A16 / A17；as-of 2026-10-06
    'k_h': 0.19,  # 同 M（H 档 38.5%）；A17；as-of 2026-10-06
    'payout_obs': 0.0,  # 实付派息率（从未分红）；只进分支校验与披露；as-of 2025-12-31
    'elsfp_units_month': CAPACITY_AND_PRICE['units_month'],  # 百万只/月，来源与日期在 CAPACITY_AND_PRICE。
    'elsfp_price': CAPACITY_AND_PRICE['price'],  # USD/只，来源与日期在 CAPACITY_AND_PRICE。
    't_opt': 2028.0,  # ELSFP 兑现年 = 2027 年底产能的首个满年；A13；as-of 2026-05-07
    'tax_opt': 0.21,  # 期权腿税率（美国联邦 21%，德州无州所得税）；A13；as-of 派生
    'ebit_margin_inp_normal': 0.2732,  # `_AXIS.inp-laser` 常态营业利润率（兑现年 > 短缺期止点）；A13；as-of 2026-10-05
    'g2_inp_laser_normal': 0.04,  # `_AXIS.inp-laser` 非瓶颈期永续增速；A13；as-of 2026-10-05
    't_shortage_end': 2027.0,  # `_AXIS.inp-laser` 短缺期最后一年；A13；as-of 2026-10-05
    'cap_intensity': 0.288,  # 满产所需资本 / 年收入（`_AXIS.inp-laser` §1b 表，`LITE.US` A22 实测）；A13；as-of 2026-10-05
    'rj_eps_runrate': CANDIDATE_ESTIMATE['mean'],  # 单家 2027H2 产能年化中点，非全年预测。
    'rj_eps_runrate_hi': CANDIDATE_ESTIMATE['high'],  # 同一来源的上沿，避免 H 档重复计算增长。
    'ss_return': 0.18,  # 主尺稳态回报 = `_AXIS.pluggable-module` `ss_return_plug`（同一门生意成熟同业为空 → 兜底「轻资产组装」18%）；本票自身周期层不可用（FY18–FY25 连亏）；各档 min(ROE, 本值)；A23；as-of 2026-10-16
    'y1': 2028.0,  # 主尺高回报期 Y1 = `_AXIS.pluggable-module` `y1_plug`（模块组装环节，中门槛）；A23；as-of 2026-10-16
    'y2': 2032.0,  # 主尺高回报期 Y2 = `_AXIS.pluggable-module` `y2_plug`；Y1 → Y2 线性回落；A23；as-of 2026-10-16
    'tau': 0.5,  # 时点对齐 τ = 资产负债表日 2026-06-30 → 分子年初 FY27 年初 2027-01-01；篮子对下 τ 段按过渡篮 `r_journey` 折；A24；as-of 2026-10-16
    'cash_h1': 499.737,  # 现金及等价物，不含受限现金 $9.021M（10-Q 资产负债表；XBRL `CashAndCashEquivalentsAtCarryingValue`）；可动用现金起点，A25；as-of 2026-06-30
    'bank_debt': 58.915,  # 银行借款 = 一年内到期 57.258 + 长期 1.657（10-Q Note 11）；A25；as-of 2026-06-30
    'bank_accept': 33.9,  # 银行承兑汇票（10-Q Note 11；同 A18）；A25；as-of 2026-06-30
    'lease_liab': 78.143,  # 经营租赁负债 = 流动 4.223 + 非流动 73.920（10-Q）；A25；as-of 2026-06-30
    'cash_anchor': 0.0,  # 经营所需现金锚：FY2021–FY2025 扩展口径净现金 ÷ 收入的最低值为负（FY22–FY24 净负债）→ 下限 0；A25；as-of 2025-12-31
    'capex_h1': 335.132,  # 2026 上半年购置固定资产（10-Q 现金流量表）= 下半年资本开支按同节奏；A25；as-of 2026-06-30
    'prepay_h1': 289.744,  # 2026 上半年设备预付款（10-Q 现金流量表「Prepayment for equipment and others」，投资活动；Note 8：扩产项目的设备与厂房预付，将转入固定资产）；计一次、不外推；A25；as-of 2026-06-30
    'da_h1': 19.729,  # 2026 上半年折旧摊销（10-Q 现金流量表）= 下半年折旧摊销读数；A25；as-of 2026-06-30
    'ocf_h1': -73.781,  # 2026 上半年实测经营现金流（10-Q）；只进敏感性（另外读法），A25；as-of 2026-06-30
    'fab4_contract': 94.1,  # Houston OMD 3（FAB4）洁净厂房设计施工合同总额（8-K 2026-07-01；按进度付款，报道称 2027-01-10 基本完工；产品未披露）；只进与期权资本重叠的敏感性，A25；as-of 2026-07-01
    'ebit_margin_inp_peer': 0.4506,  # `_AXIS.inp-laser` 短缺期营业利润率：期权利润率路径的起点（`y1_opt` 前），`y1_opt` → `y2_opt` 线性回落到 `ebit_margin_inp_normal`；A13；as-of 2026-10-16
    'ss_return_opt': 0.275,  # 期权腿稳态回报 = `_AXIS.inp-laser` `ss_return_inp`；新投资回报从 H 档 ROE 沿 `y1_opt` → `y2_opt` 落到本值；A13；as-of 2026-10-16
    'y1_opt': 2029.0,  # 期权腿高回报期 Y1 = `_AXIS.inp-laser` `y1_inp`（磷化铟激光芯片环节，高门槛）；A13；as-of 2026-10-16
    'y2_opt': 2035.0,  # 期权腿高回报期 Y2 = `_AXIS.inp-laser` `y2_inp`；A13；as-of 2026-10-16
    'q3_equity': 2241.348,  # Q3 10-Q 归母权益；9 月增发已含，不重复加；as-of 2026-09-30
    'q3_atm_post_net': 74.39,  # 第三轮 ATM 净额约588减9月净额513.610；近似季后增量，附注19 / MD&A增发表；不是再加588；as-of 2026-10-01
    'q3_sbc': 5.684,  # Q3 股权激励，附注15；按季度年化扣减；as-of 2026-09-30
    'q3_shares': 96.0,  # Q4指引稀释股本；不用Q3加权股数87.835替代前瞻口径；as-of 2026-11-05
    'q3_conv_carry': 128.836,  # 2030可转债账面；本金124.925与转股比例不变，附注12；as-of 2026-09-30
    'q3_cash': 605.413,  # 现金及等价物；另有受限现金16.044，不计可动用；as-of 2026-09-30
    'q3_bank_debt': 96.576,  # 长短期借款总计，附注11；含表内融资安排；as-of 2026-09-30
    'q3_bank_accept': 51.509,  # 银行承兑，附注11；as-of 2026-09-30
    'q3_lease': 73.284,  # 经营租赁负债5.182+68.102；融资安排已在借款中，勿重扣；as-of 2026-09-30
    'q3_capex_ytd': 702.149,  # 前三季购置固定资产现金流；Q3单季367.017；as-of 2026-09-30
    'q3_prepay_ytd': 406.943,  # 前三季设备等预付款现金流；Q3单季117.199；转固不再付一次；as-of 2026-09-30
    'q3_da_ytd': 34.45,  # 前三季折旧摊销；Q3差额14.721作Q4代理，非Q4实际；as-of 2026-09-30
    'q3_ocf_ytd': -76.653,  # 前三季经营现金流；Q3差额-2.872，不能拿来冒充Q4预测；as-of 2026-09-30
    'q3_commitments': 928.8,  # 设备及施工采购承诺总额，附注18；支付日、投产年、与期权资本重叠待补；非已确定的Q4支出；as-of 2026-09-30
    'q4_raw_prepay': 20.0,  # 新原料合同2026年预付款；全约预付上限40，年度采购上限194.4，附注19；as-of 2026-11-02
    'q4_ni_cons': 39.05,  # Q4 GAAP净利旧共识；**共识待更新**，不能把公司non-GAAP指引直接当GAAP；as-of 2026-11-06
    'q3_eps_m': 4.602,  # FY27 non-GAAP EPS现查询均值（5家，3.52–8.08）；**共识待更新**；保留每股预测，不无依据再按股本摊薄；as-of 2026-11-06
    'q3_tau': 0.25,  # 2026-09-30到2027-01-01约一季；条件试算，未替换旧正式tau；as-of 2026-09-30
}

REQUIRED = [
    "eps_fy27_l", "eps_fy27_m", "eps_fy27_h", "rev_fy26_cons", "rev_fy27_m", "rev_fy27_h",
    "nm_fy25", "rev_cut_l", "sbc_q2", "shares_dil", "equity_h1", "atm_post", "atm_fee",
    "warrant_vested", "warrant_strike", "conv_carry", "conv_principal", "conv_rate",
    "ni_h2_cons", "r_journey", "r_terminal", "r_catv_cross", "g2", "catv_rev_27",
    "k_l", "k_m", "k_h", "payout_obs", "elsfp_units_month", "elsfp_price", "t_opt",
    "tax_opt", "ebit_margin_inp_normal", "g2_inp_laser_normal", "t_shortage_end",
    "cap_intensity", "rj_eps_runrate", "rj_eps_runrate_hi",
    "ss_return", "y1", "y2", "tau", "ebit_margin_inp_peer", "ss_return_opt", "y1_opt", "y2_opt",
    "cash_h1", "bank_debt", "bank_accept", "lease_liab", "cash_anchor",
    "capex_h1", "prepay_h1", "da_h1", "ocf_h1", "fab4_contract",
]


def _lin(cal: int, y1: int, y2: int, a: float, b: float) -> float:
    """a through Y1, linear to b at Y2, b after (valuation-rules ② 稳态回报三段)."""
    if cal <= y1:
        return a
    if cal >= y2:
        return b
    return a + (b - a) * (cal - y1) / (y2 - y1)


def path_value(t0: int, y1: int, y2: int, r_s: float, g: float, roe: float, r: float,
               g1: float = 0.0, n: int = 0, m_from: float = 1.0, m_to: float = 1.0) -> float:
    """Use the shared return path; the option also fades its unit margin."""
    return return_path_pe(t0, y1, y2, r_s, g, roe, r,
                          growth_first=g1, transition_years=int(n),
                          margin_start=m_from, margin_end=m_to)



# 旧基准的建模意图，供后续研究对照；来源和日期另见各项输入。
# A1/A2：2027 年每股利润用五家卖方的低/均/高值，扣股权激励；
# 2028 年仅有单家产能年化估计，不冒充多家全年预测。
# A3：消化年参照 2018 年收入下滑约 30%，盈利为负时采用账面参考；
# 账面不是清算保证，可转债比较转股和偿债，取对现有股东较低的值。
# A4/A6/A7/A11：产能、1.6T 交付、毛利及扩产回报在 2026Q3 后转弱；
# 原复核线包括 2026Q4 的 1.6T 收入低于 3500 万美元或年底月产能低于
# 40 万只、2027 年某季调整后毛利率低于 28%、产能利用率低于 60%。
# A5：有线电视全年收入目标 3.25 亿美元；连续两季低于 6000 万复核。
# A8/A9/A10：2027 是最远有区间共识的年份；长期增长率按用户确定的
# 同业参考 2%，历史找不到同等盈利月份，历史倍数只可作旁证。
# A12/A14：监管既可能限制中国同行、也可能影响自身原料进口；共封装
# 可能替代可插拔产品，客户采用路径与公司是否进入供货名单仍待核实。
# A13：外置光源按公司口径产能与单家售价估算；产能单位、销量、收入
# 尚未验证。高回报和利润率按激光芯片环节逐步回落，并扣满产资本。
# A15/A17：客户集中使现阶段要求回报为 15%，分散后的长期参考为 10%；
# 未能分散的 50% 是基于 2018 年流失主力客户的判断，不是统计概率。
# 2026 年报若最大客户低于 35% 且前两大低于 60%，复核该风险判断。
# A16/A18：扩产窗口仍在进行，留存资金用途需区分投资和偿债；负债与
# 现金按相同归母口径处理，银行授信额度不是已到账的现金。
# A19：单家预测仅作候选；至少两家卖方给出 2028 年带区间预测后重议。
# A20：可转债比较转股与按债务处理两种口径；已归属和未归属权证分开。
# A21/A22：多年亏损使自身周期中枢不可用；未发现已交割的大额收购。
# A23/A24：高回报持续到 2028 年，2032 年回落至成熟水平；从 2027 年初
# 折回报表基准，期间利润不得与经营现金流重复计算。
# A25：只扣本期扩产现金无法覆盖、且服务于分子年盈利的缺口；设备
# 预付款转固定资产不能再扣，外置光源已计的投入也不能重复扣除。
# A26：2026 年原料预付 2000 万美元；出口审批和退款条件需后续核实。


def sanity(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    for row in ("r_journey", "r_terminal"):
        if row not in baskets:
            e.append(f"{row}: Inputs source cell names no 篮 N (A15)")
    if "r_catv_cross" in baskets:
        e.append("r_catv_cross is a disclosure-only r and must not name a 篮 N")
    e += check_basket_pair(inp["r_journey"], inp["r_terminal"], "r",
                           baskets.get("r_journey"), baskets.get("r_terminal"))
    e += check_k_declared(inp["r_journey"], inp["r_terminal"],
                          (inp["k_l"], inp["k_m"], inp["k_h"]), "k")
    # G_cap stays keyed to the JOURNEY basket (篮子对 判据 3).
    e += check_g_cap(inp["g2"], inp["r_journey"], "g2")
    if inp["r_terminal"] - inp["g2"] < MIN_R_MINUS_G:
        e.append("r_terminal - g2 < 2%: at the pole")
    e += check_g_cap(inp["g2_inp_laser_normal"], inp["r_journey"], "g2_inp_laser_normal")
    e += check_transition_years(N_STAGE, 0, "n")
    if not (inp["eps_fy27_l"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]):
        e.append("FY27 consensus range must be ordered low < mean < high")
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (cyclical)")
    if not (NUM_YEAR <= inp["y1"] < inp["y2"]):
        e.append("main-ruler high-return window must satisfy numerator year <= Y1 < Y2 (A23)")
    if not (inp["y1_opt"] < inp["y2_opt"]):
        e.append("option high-return window must satisfy Y1 < Y2 (A13)")
    if inp["ebit_margin_inp_normal"] >= inp["ebit_margin_inp_peer"]:
        e.append("normal margin must sit below the shortage-era margin (_AXIS.inp-laser §1b)")
    if not (0.0 <= inp["tau"] < 3.0):
        e.append("tau out of range (A24)")
    if inp["t_opt"] <= NUM_YEAR:
        e.append("option realisation year must lie after the numerator year")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


def q3_conditions(inp: dict[str, float], references: dict) -> tuple[list[str], dict]:
    """Keep Q3 cash-use conditions separate from the frozen formal anchors."""
    names = [
        "q3_equity", "q3_atm_post_net", "q3_sbc", "q3_shares", "q3_conv_carry",
        "q3_cash", "q3_bank_debt", "q3_bank_accept", "q3_lease",
        "q3_capex_ytd", "q3_prepay_ytd", "q3_da_ytd", "q3_ocf_ytd",
        "q3_commitments", "q4_raw_prepay", "q4_ni_cons", "q3_eps_m", "q3_tau",
    ]
    errors = check_missing(inp, names)
    if errors:
        return errors, {}
    sh, g = inp["q3_shares"], inp["g2"]
    sbc = 4 * inp["q3_sbc"] / sh
    eq = (inp["q3_equity"] + inp["q3_atm_post_net"]
          + inp["warrant_vested"] * inp["warrant_strike"] + inp["q3_conv_carry"])
    conv_sh = inp["conv_principal"] * inp["conv_rate"] / 1000

    def lower(v: float) -> float:
        return min(v, (v * sh - inp["conv_principal"]) / (sh - conv_sh))

    da_q3 = inp["q3_da_ytd"] - inp["da_h1"]
    ocf = inp["q4_ni_cons"] + da_q3  # Q4 estimate, not observed Q4 cash flow.
    cash = (inp["q3_cash"] + inp["q3_atm_post_net"] - inp["q3_bank_debt"]
            - inp["q3_bank_accept"] - inp["q3_lease"] - inp["cash_anchor"])
    limit = cash + ocf - inp["q4_raw_prepay"]
    debt_like = max(0, inp["q3_commitments"] - limit)
    floor = lower((eq + inp["q4_ni_cons"]) / sh)
    discount = (1 + inp["r_journey"]) ** (-inp["q3_tau"])
    values, cand, returns = {}, {}, {}
    for t, key in (("M", "q3_eps_m"), ("H", "eps_fy27_h")):
        eps = inp[key] - sbc
        bps = (eq + inp["q4_ni_cons"]) / sh
        for _ in range(200):
            roe = eps / bps
            nxt = (eq + inp["q4_ni_cons"] * min(1, g / roe)) / sh
            if abs(nxt - bps) < 1e-12:
                break
            bps = nxt
        roe = eps / bps
        returns[t] = roe
        pe = path_value(NUM_YEAR, int(inp["y1"]), int(inp["y2"]),
                        inp["ss_return"], g, roe, inp["r_terminal"])
        pe_j = path_value(NUM_YEAR, int(inp["y1"]), int(inp["y2"]),
                          inp["ss_return"], g, roe, inp["r_journey"])
        if roe - inp["r_terminal"] < 0.03:
            errors.append(f"Q3 {t}: return leaves the monotone domain")
        if abs(FAIL_SHARE * (1 - pe_j / pe) - inp[f"k_{t.lower()}"]) > K_TOL:
            errors.append(f"Q3 {t}: basket-pair k no longer reconciles")
        value = eps * pe * (1 - inp[f"k_{t.lower()}"]) * discount
        values[t] = (lower(value - debt_like / sh), lower(value))
        target = inp["rj_eps_runrate" if t == "M" else "rj_eps_runrate_hi"]
        g1 = max(0, target / inp[key] - 1)
        pe_c = path_value(NUM_YEAR, int(inp["y1"]), int(inp["y2"]),
                          inp["ss_return"], g, roe, inp["r_terminal"], g1=g1, n=1)
        cv = eps * pe_c * (1 - inp[f"k_{t.lower()}"]) * discount
        cand[t] = (lower(cv - debt_like / sh), lower(cv))
    rv = 12 * inp["elsfp_units_month"] * inp["elsfp_price"]
    po = path_value(int(inp["t_opt"]), int(inp["y1_opt"]), int(inp["y2_opt"]),
                    inp["ss_return_opt"], inp["g2_inp_laser_normal"], returns["H"],
                    inp["r_terminal"], m_from=inp["ebit_margin_inp_peer"],
                    m_to=inp["ebit_margin_inp_normal"])
    option = (rv * (1 - inp["tax_opt"]) / sh * po * (1 - inp["k_h"])
              / (1 + inp["r_journey"]) ** (inp["t_opt"] - NUM_YEAR)
              - rv * inp["cap_intensity"] / sh) * discount
    rows = {
        "cash_fully_committed": (floor, values["M"][0], values["H"][0]),
        "cash_no_extra_gap": (floor, values["M"][1], values["H"][1]),
        "candidate_fully_committed": (floor, cand["M"][0], cand["H"][0]),
        "candidate_no_extra_gap": (floor, cand["M"][1], cand["H"][1]),
    }
    for label, nums in rows.items():
        if not nums[0] < nums[1] < nums[2]:
            errors.append(f"{label}: tiers not ordered")
    # Same cash expression across the release threshold: no branch-induced jump.
    def unfunded(payment: float) -> float:
        return max(0, payment + inp["q4_raw_prepay"] - ocf - cash)
    if unfunded(limit) > 1e-8 or abs(unfunded(limit + 1) - 1) > 1e-8:
        errors.append("Q3 cash-use threshold is not continuous")
    return errors, {**{key: dict(zip(TIERS, vals)) for key, vals in rows.items()},
                    "option_value": option, "valuation_as_of": "2026-09-30", "is_trial": True,
                    "roe": returns,
                    "steady_return": {"unit": "RATIO",
                                      "values": {tier: min(roe, inp["ss_return"])
                                                 for tier, roe in returns.items()},
                                      "selected_value": inp["ss_return"],
                                      "reference_value": references["ss_return"]},
                    "funding": {"available_cash": cash, "ocf_proxy": ocf,
                                "payment_without_gap": limit, "unfunded": debt_like,
                                "unfunded_per_share": [unfunded(limit + fraction * debt_like) / sh
                                                       for fraction in (0, .25, .5, .75, 1)]}}


def _evaluate(inp: dict[str, float], references: dict, rate_inputs: dict | None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    invalid = [key for key, value in inp.items()
               if not isinstance(value, (int, float)) or not math.isfinite(value)]
    if invalid:
        raise ValueError(f"inputs must be finite numbers: {invalid}")
    fractional_years = [key for key in ("y1", "y2", "y1_opt", "y2_opt", "t_opt")
                        if isinstance(inp[key], bool) or not float(inp[key]).is_integer()]
    if fractional_years:
        raise ValueError(f"model years must be integers: {fractional_years}")
    if (len(P_TIERS) != 3 or any(not isinstance(p, (int, float)) or not math.isfinite(p)
                                 or not 0 <= p <= 1 for p in P_TIERS)
            or not P_TIERS[0] <= P_TIERS[1] <= P_TIERS[2]):
        raise ValueError("期权兑现比例必须为 0–1 的有限数字，且按情景递增")
    # The two basket assignments describe the frozen 2026-10-19 baseline.
    # Each company's own input values are authoritative; peer axis values are
    # dated references, not a live dependency that overrides this calculation.
    baskets = {"r_journey": 7, "r_terminal": 4}
    errors = sanity(inp, baskets)
    y0, y1, y2, rs = NUM_YEAR, int(inp["y1"]), int(inp["y2"]), inp["ss_return"]

    def pp(g: float, roe: float, r: float) -> float:  # main-ruler path multiple (A23)
        return path_value(y0, y1, y2, rs, g, roe, r)

    sh, g2 = inp["shares_dil"], inp["g2"]
    sbc_ps = 4 * inp["sbc_q2"] / sh
    conv_sh = inp["conv_principal"] * inp["conv_rate"] / 1000

    def lower_of(v: float) -> float:
        """A20: holder-optimal convertible — lower of diluted and debt per-share readings."""
        return min(v, (v * sh - inp["conv_principal"]) / (sh - conv_sh))

    eq0 = (inp["equity_h1"] + inp["atm_post"] * (1 - inp["atm_fee"])
           + inp["warrant_vested"] * inp["warrant_strike"] + inp["conv_carry"])

    def tier(e: float, g: float, r: float, eq_extra: float = 0.0, shares: float = sh):
        bps = (eq0 + eq_extra + inp["ni_h2_cons"]) / shares
        for _ in range(200):
            roe = e / bps
            nxt = (eq0 + eq_extra + inp["ni_h2_cons"] * min(1.0, g / roe)) / shares
            if abs(nxt - bps) < 1e-12:
                break
            bps = nxt
        roe = e / bps
        return bps, roe, pp(g, roe, r)

    r_j, r_t = inp["r_journey"], inp["r_terminal"]
    tau = inp["tau"]
    w_ps = inp["ni_h2_cons"] / sh  # H2-2026 consensus NI not yet booked (A24)

    # ---- Growth-period funding gap (A25) ----
    # Extended net cash ex-convertible (the convertible is handled by lower_of); restricted cash out.
    cash_free = (inp["cash_h1"] + inp["atm_post"] * (1 - inp["atm_fee"]) - inp["bank_debt"]
                 - inp["bank_accept"] - inp["lease_liab"] - inp["cash_anchor"])
    # 上半年经营现金流受到存货与应收增加拖累；增长所需营运资金已在
    # 留存成本中考虑，直接重复扣除可能双计。2023–2025 净利均为负，
    # 常用的经营现金流/净利历史比例不可用，因此旧基准暂用预测净利
    # 加折旧作代理；直接外推上半年现金流保留为独立敏感性。
    ocf_h2 = inp["ni_h2_cons"] + inp["da_h1"]
    capex_h2 = inp["capex_h1"] + inp["prepay_h1"]  # H1 pace repeated + the prepayment once

    def short_ps(g_gap: float, cash: float = cash_free, shares: float = sh) -> float:
        return max(0.0, g_gap - cash) / shares

    gap = max(0.0, capex_h2 - ocf_h2)
    gap_ps = short_ps(gap)
    c_ex = cash_free - gap
    if c_ex >= 0.15 * eq0:
        errors.append(f"C_ex {c_ex:.1f} >= 15% of equity — excess cash must be listed (A25)")
    if gap_ps > 0 and c_ex >= 0:
        errors.append("gap deduction while C_ex >= 0 — cash pays the gap, deduct nothing")

    def timed(pre_k: float, g: float, roe: float, rj: float, gps: float | None = None) -> float:
        """A24 / A25: FY27-opening value -> today at the journey rate; window profit only when
        there is no funding gap (OCF already holds it); less the unfunded gap per share."""
        gps = gap_ps if gps is None else gps
        win = 0.0 if gap > 0 else w_ps * (1 - min(1.0, max(0.0, g / roe))) * (1 + rj) ** (-tau / 2)
        return pre_k * (1 + rj) ** (-tau) + win - gps
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    eps = {"M": inp["eps_fy27_m"] - sbc_ps, "H": inp["eps_fy27_h"] - sbc_ps}

    # ---- L: digestion scenario, then the asset floor (A3) ----
    eps_l_scn = inp["rev_fy26_cons"] * (1 - inp["rev_cut_l"]) * inp["nm_fy25"] / sh - sbc_ps
    floor = (eq0 + inp["ni_h2_cons"]) / sh
    if eps_l_scn >= 0:
        errors.append(f"L scenario EPS {eps_l_scn:.3f} >= 0 — the floor rule (A3) no longer applies; reprice L")

    def band(rj: float, rt: float, g: float = g2, ks: dict | None = None):
        ks = k if ks is None else ks
        out, info = {"L": lower_of(floor)}, {}
        for t in ("M", "H"):
            bps, roe, pe = tier(eps[t], g, rt)
            pre = eps[t] * pe
            out[t] = lower_of(timed(pre * (1 - ks[t]), g, roe, rj))
            info[t] = (bps, roe, pe, pp(g, roe, rj), pre)
        return out, info

    anchors, info = band(r_j, r_t)
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    for t in ("M", "H"):
        bps, roe, pe, pe_j, _ = info[t]
        if roe - r_t < 0.03:
            errors.append(f"{t}: ROE {roe:.3f} not in the monotone domain at r_terminal {r_t:g}")
        errors += check_branch(g2, roe, r_t, inp["payout_obs"], f"g2@{t}")
        k_derived = FAIL_SHARE * (1 - pe_j / pe)
        if abs(k_derived - k[t]) > K_TOL:
            errors.append(f"k_{t.lower()} {k[t]} vs derived {k_derived:.3f}; "
                          "采用新的增长或回报假设时须同步复核客户集中风险折扣 (A17)")
    if not eps["M"] * info["M"][2] < eps["H"] * info["M"][2]:
        errors.append("flat ladder: M >= H at the M multiple (A2e-2c)")

    # ---- Option (A13) ----
    # Unit margin and new-investment return fade along the laser-chip window (A13, user 2026-10-16).
    rev_opt = 12 * inp["elsfp_units_month"] * inp["elsfp_price"]  # 百万 USD (百万只 x USD)
    roe_h = info["H"][1]
    t_o = int(inp["t_opt"])
    m0 = _lin(t_o, int(inp["y1_opt"]), int(inp["y2_opt"]), inp["ebit_margin_inp_peer"], inp["ebit_margin_inp_normal"])
    ni_opt = rev_opt * m0 * (1 - inp["tax_opt"])  # first-year NI on the path
    eps_opt = ni_opt / sh
    path_opt = path_value(t_o, int(inp["y1_opt"]), int(inp["y2_opt"]), inp["ss_return_opt"],
                          inp["g2_inp_laser_normal"], roe_h, r_t,
                          m_from=inp["ebit_margin_inp_peer"], m_to=inp["ebit_margin_inp_normal"])
    pe_opt = path_opt / m0  # multiple on the first-year EPS, for the printout
    val_t = rev_opt * (1 - inp["tax_opt"]) / sh * path_opt * (1 - k["H"])
    disc = (1 + r_j) ** (inp["t_opt"] - NUM_YEAR)
    capital = rev_opt * inp["cap_intensity"] / sh
    v_opt = (val_t / disc - capital) * (1 + r_j) ** (-tau)  # FY27 opening -> today (A24)
    plus_v = tuple(x + p * v_opt for x, p in zip((L, M, H), P_TIERS))
    if not math.isfinite(v_opt) or v_opt < 0 or not plus_v[0] < plus_v[1] < plus_v[2]:
        errors.append("期权价值及修正后的估值区间必须有效且按情景递增")

    def v_at(price: float) -> float:
        rv = 12 * inp["elsfp_units_month"] * price
        return ((rv * (1 - inp["tax_opt"]) / sh * path_opt * (1 - k["H"]) / disc
                 - rv * inp["cap_intensity"] / sh) * (1 + r_j) ** (-tau))

    # ---- Candidate band (A19): RJ run-rate as one FY28 transition year ----
    # A capacity run-rate is a level, not a growth rate: M′ reaches the midpoint, H′ is
    # capped at the source's top (construction §7h), so H's FY27 ramp is not counted twice.
    g1_by = {"M": inp["rj_eps_runrate"] / inp["eps_fy27_m"] - 1,
             "H": max(0.0, inp["rj_eps_runrate_hi"] / inp["eps_fy27_h"] - 1)}
    cand = {"L": L}
    for t in ("M", "H"):
        roe = info[t][1]
        pe_c = path_value(y0, y1, y2, rs, g2, roe, r_t, g1=g1_by[t], n=1)
        cand[t] = lower_of(timed(eps[t] * pe_c * (1 - k[t]), g1_by[t], roe, r_j))  # b = g1/ROE > 1 -> window 0
    if not cand["L"] < cand["M"] < cand["H"]:
        errors.append("candidate band not ordered")

    # 同一模型的风险与资金用途敏感性；只输出数字，解释留给文档。
    single, _ = band(r_j, r_j, ks={"L": 0, "M": 0, "H": 0})
    t4, _ = band(r_t, r_t, ks={"L": 0, "M": 0, "H": 0})

    def gap_band(gps: float) -> dict[str, float]:
        return {"L": L, **{t: lower_of(timed(eps[t] * info[t][2] * (1 - k[t]),
                                            g2, info[t][1], r_j, gps)) for t in ("M", "H")}}

    ocf_obs = inp["ocf_h1"]
    gap_sensitivity = {
        "repeat_h1_ocf": gap_band(short_ps(capex_h2 - ocf_obs)),
        "exclude_prepayment": gap_band(short_ps(inp["capex_h1"] - ocf_h2)),
        "without_cash_offset": gap_band(gap / sh),
        "factory_assigned_to_option": gap_band(short_ps(gap - inp["fab4_contract"])),
    }
    catv_cross = {}
    for t, rev in (("M", inp["rev_fy27_m"]), ("H", inp["rev_fy27_h"])):
        share = inp["catv_rev_27"] / rev
        _, roe, pe, _, _ = info[t]
        value = (eps[t] * (1 - share) * pe * (1 - k[t])
                 + eps[t] * share * perpetual_pe(0.0, roe, inp["r_catv_cross"]))
        catv_cross[t] = lower_of(timed(value, g2, roe, r_j))

    # 第三轮增发用满的历史试算；这组数在可转债择优之前。
    atm3, px = 600 * (1 - inp["atm_fee"]), 120.0
    sh3 = sh + 600 / px
    diluted = {t: eps[t] * sh / sh3 for t in ("M", "H")}
    atm_values = {}
    for t in ("M", "H"):
        _, roe, pe = tier(diluted[t], g2, r_t, atm3, sh3)
        atm_values[t] = timed(pe * diluted[t] * (1 - k[t]), g2, roe, r_j,
                              short_ps(gap, cash_free + atm3, sh3))
    atm_values["L"] = (eq0 + atm3 + inp["ni_h2_cons"]) / sh3

    # ---- r_f readings (_AXIS.rates USD): both rates of the pair move 1:1; the floor stays ----
    def band_rf(dr: float) -> tuple[float, float, float]:
        b_, _ = band(r_j + dr, r_t + dr)
        return b_["L"], b_["M"], b_["H"]

    rf = None
    if rate_inputs is not None:
        rf = result_rate_sensitivity(calculate_rf_readings(
            rate_currency=LISTING_CCY, price_currency=LISTING_CCY, price_unit="per_share",
            priced_r={"r_journey": r_j, "r_terminal": r_t}, band_at=band_rf,
            rates_loader=lambda currency: rate_inputs, base_anchors=(L, M, H)))
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    q3_errors, conditional = q3_conditions(inp, references)
    errors += q3_errors
    if errors:
        raise ValueError("; ".join(errors))
    base = dict(anchors)
    return {
        "ticker": "AAOI.US", "currency": "USD",
        "valuation_as_of": None,
        "framework_as_of": None,
        "units": {"price": "USD_PER_SHARE", "amount": "USD_MILLION", "ratio": "RATIO"},
        "anchors": base,
        "candidate": {"label": "RJ 产能年化", "anchors": cand},
        "option": {"value": v_opt, "value_unit": "USD_PER_SHARE", "credits": dict(zip(TIERS, P_TIERS)),
                   "anchors": dict(zip(TIERS, plus_v)),
                   "details": {"revenue": rev_opt, "margin": m0, "net_income": ni_opt,
                               "eps": eps_opt, "multiple": pe_opt, "capital_per_share": capital},
                   "parameters": {"r_terminal": r_t, "r_journey": r_j,
                                  "growth": inp["g2_inp_laser_normal"],
                                  "growth_reference": references["g2_inp_laser_normal"],
                                  "roe_forward": roe_h,
                                  "steady_return": min(roe_h, inp["ss_return_opt"]),
                                  "steady_return_reference": references["ss_return_opt"],
                                  "fade_from": int(inp["y1_opt"]), "fade_to": int(inp["y2_opt"])}},
        "segments": {"company": {"values": base}},
        "key_parameters": {
            "eps_fy27": {"unit": "USD_PER_SHARE", "values": {"L": None, "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}},
            "roe_forward": {"unit": "RATIO", "values": {"L": None, "M": info["M"][1], "H": info["H"][1]}},
            "steady_return": {"unit": "RATIO", "values": {"L": None, "M": min(info["M"][1], rs),
                                         "H": min(info["H"][1], rs)},
                              "selected_value": rs, "reference_value": references["ss_return"]},
            "growth_rate": {"unit": "RATIO", "values": {"L": None, "M": g2, "H": g2},
                            "selected_value": g2, "reference_value": references["g2"]},
            "terminal_discount_rate": {"unit": "RATIO", "values": {"L": None, "M": r_t, "H": r_t}},
            "transition_discount_rate": {"unit": "RATIO", "values": {"L": None, "M": r_j, "H": r_j}},
            "risk_discount": {"unit": "RATIO", "values": k},
            "failure_share": {"unit": "RATIO", "selected_value": FAIL_SHARE},
        },
        "sensitivity": {
            "growth": [{"value": g, "anchors": band(r_j, r_t, g)[0]}
                       for g in (g2 - 0.01, g2, g2 + 0.01, MACRO_G)],
            "option_price": [{"value": price, "unit": "USD_PER_UNIT", "option_value": v_at(price)}
                             for price in (750, 1000)],
            "funding": gap_sensitivity,
            "atm_fully_drawn_pre_convertible": atm_values,
        },
        "risk_sensitivity": {"current_risk_persists": single, "diversified_without_discount": t4},
        "cross_checks": {"catv_split": catv_cross},
        "funding": {"capex": capex_h2, "ocf_proxy": ocf_h2, "gap": gap,
                    "available_cash": cash_free, "unfunded": max(0.0, gap - cash_free),
                    "unfunded_per_share": gap_ps},
        "payout": {"actual": inp["payout_obs"],
                   "model": {t: payout_gap(g2, info[t][1], inp["payout_obs"])[0] for t in ("M", "H")},
                   "retained_per_share": {t: (1 - inp["payout_obs"] - g2 / info[t][1]) * eps[t]
                                          for t in ("M", "H")}},
        "rate_sensitivity": rf,
        "conditional": conditional,
    }


def calculate(context):
    inp = dict(INPUTS)
    plug, laser = context['axes']['pluggable'], context['axes']['inp_laser']
    # Company-specific growth and returns are explicitly permitted; shared
    # references are presented alongside the selected values, never imposed.
    references = {'g2': plug['g2_pluggable'], 'ss_return': plug['ss_return_plug'],
                  'g2_inp_laser_normal': laser['g2_inp_laser_normal'],
                  'ss_return_opt': laser['ss_return_opt']}
    inp.update({'y1': plug['y1_plug'], 'y2': plug['y2_plug'],
                **{key: laser[key] for key in ('ebit_margin_inp_normal', 't_shortage_end',
                   'cap_intensity', 'ebit_margin_inp_peer', 'y1_opt', 'y2_opt')}})
    result = _evaluate(inp, references, context.get('rate_inputs'))
    result['segments']['company']['unit'] = 'USD_PER_SHARE'
    result['valuation_as_of'] = result['framework_as_of'] = None
    result['historical_financial_statement_as_of'] = '2026-06-30'
    result['historical_research_as_of'] = '2026-10-19'
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': inp, 'references': references, 'option_credits': P_TIERS,
         'failure_share': FAIL_SHARE, 'numerator_year': NUM_YEAR,
         'transition_years': N_STAGE, 'macro_g': MACRO_G}, BASELINE_LOCAL)
    result['review_flags'] = ['historical_funding_unverified',
                              'q3_funding_cases_not_adopted',
                              'option_revenue_and_capital_overlap_unverified']
    return result
