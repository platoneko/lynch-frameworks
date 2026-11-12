#!/usr/bin/env python3
"""Historical CATL operating-earnings model and capacity option.

Amounts and shares follow the original input units; outputs are CNY/share.
The financial report basis, dated consensus and 2018–2025 history are kept
in input comments and below, not refreshed by this migration. Excess cash and
its income use the same attributable share, while unbooked earnings and
return paths retain the original timing. The user accepted the historical
plain-equity steady-return basis after the separate operating-equity reading.

The extra capacity option is outside the base, net of unspent capital and
priced on its actual calendar path. Option weights are original judgments,
not measured probabilities. The old product economics and capacity assumptions
remain conditions, not proof of future sales or margin.
"""
# Historical evidence and limitations retained from the document:
# The FY2027 EPS sample was collected before the 2026Q3 release. The low
# 18.75 CNY/share combines 9M actual 14.13 with a Q4 proxy equal to Q3 4.62;
# it is not a full-year consensus or a claim that future demand is fixed.
# The 22.8% steady return is the 2019–2025 ordinary equity-return median,
# accepted by the user on 2026-10-18/19. It includes excess cash, whereas the
# forward return excludes it; those bases differ and the historical interval
# did not contain a full significant downturn.
# Q3 2026 operating cash 14.08 versus capex 170.94 CNY 100 million and rising
# inventory and debt weaken the zero future funding gap assumption. The
# 364.16 difference between cash and cash equivalents combines restricted
# money and longer deposits; its split is unverified. Accumulated nine-month
# cash flow exceeded capex, but neither observation proves future funding.
# The 2026H1 764 GWh in construction is not demand. The incremental option
# subtracts the high forecast-implied volume, uses H1 margin and allocates
# remaining estimated capital by production share; budget and progress for
# individual sites are partly proxies. Year-2029 realization and end-of-period
# capital deductions are assumptions. Q3 inventory and lower unit economics
# weaken the incremental value despite the calculation's mechanical increase.
# Sources include 2026Q3 filing 2026-097, 2026 interim report production and
# construction notes, Hungary/Luoyang/Jining announcements, and pre-Q3
# yfinance forecasts; analyst commentary dated 2026-10-21 relays the call.
from __future__ import annotations

import math
from lib.gordon import check_branch, check_g_cap, check_r, g_cap, implied_g, payout, perpetual_pe, two_stage_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = '4a3f4a73198b628157b4c670c08df17e728787fbea16ba400c2ccc037eb3d3cf'

INPUTS = {
    'shares': 4627250000,  # 总股本（含 H 股 2.183 亿）；三季报资产负债表「股本」4,627,250 千元（中报 4,626,770,410 股）; as-of 2026-09-30
    'bps': 83.61,  # 每股净资产 CNY = 归母权益 3,868.81 亿 ÷ 股本 46.2725 亿股（三季报）; as-of 2026-09-30
    'equity': 3868.81,  # 归母权益（三季报「归属于母公司所有者权益合计」386,880,990 千元）；减已宣派未付股息 `div_declared` 与超额现金 `c_ex` 得 3Q26 经营股权，按增长所需留存 \(b_1=g_2/RONIC\) 滚过 4Q26 到 2027 年初再作 RONIC 分母（A21 / A22）; as-of 2026-09-30
    'net_cash_ext': 2426.68,  # 扩展口径净现金 = 货币资金 3,698.14 + 交易性金融资产 627.80 − 有息负债（短借 398.98 + 一年内到期非流动负债 168.71 + 长借 763.55 + 应付债券 527.38）− 租赁负债 40.65 亿（三季报）；应付股利 0；客户预付款（合同负债 406.69 亿）是经营负债，不扣（A22）。中报 2,911.83 → 一季 −485.15 亿：有息负债 +401.9 亿、货币资金 −22 亿，借款填了营运资金（存货 +140 亿）; as-of 2026-09-30
    'div_declared': 0,  # 2026-09-30 无已宣派未付股息：2026 中期分红 1.411 元/股（65.28 亿）已于 2026-08 除息支付，已在 9-30 的现金与归母权益里（中报版本此行 65.28，A22）; as-of 2026-09-30
    'rev_fy2025': 4237.02,  # FY2025 营业总收入（亿元）；经营所需现金锚的缩放基数（A22）; as-of 2025-12-31
    'minority': 363.36,  # 少数股东权益（三季报 36,335,776 千元）；归母比例用（A22）; as-of 2026-09-30
    'y1': 2027,  # 高回报期止点 Y₁ = 可见年末 FY2027（默认，用户未另议；不挂需求轴 / 同业尺轴）（A23）; as-of 2026-10-16
    'y2': 2031,  # 回落到稳态 Y₂ = Y₁ + 4（电池判中门槛，A23）; as-of 2026-10-16
    'ronic_ss': 0.228,  # 稳态回报 22.8% = 自身周期层，**普通 ROE 口径**（FY2019–25 归母利润 ÷ 平均归母权益的中位，不扣超额现金，与前瞻公式不同口径；用户 2026-10-18 裁定）；扣超额现金口径的 39.0% 不用（分母扣掉巨额现金后被放大）；成熟同业层仅三星 SDI 6.9%（< r），兜底 11% 更低（A23）; as-of 2026-10-18
    'ronic_ss_floor': 0.11,  # 生意模式兜底：商品化重资产（电池）11%；只作对照与敏感性——兜底是替补、不是下限，eval 只校验稳态 ≥ r（2026-10-19）; as-of 2026-10-19
    'cash_yield': 0.032574,  # 现金收益率 FY2025 = (利息收入 105.95 + 公允价值变动收益 9.74) ÷ 平均（货币资金 + 交易性金融资产）3,551.50 亿（A22）; as-of FY2025
    'tax_eff': 0.142307,  # 实际所得税率 FY2025 = 所得税 ÷ 利润总额（A22）; as-of FY2025
    'payout_op': 0.663,  # 经营口径派息率 FY2021–25 = 分红 28.3% + 现金积累 38.0%（超额现金增加 1,670.5 − 股权融资 858.4 亿，÷ 归母合计 2,137.3 亿）；`check_branch` 用（A22）; as-of FY2025
    'cash_restricted': 364.16,  # 货币资金 3,698.14 − 期末现金及现金等价物 3,333.98（受限资金与三个月以上定期混合，拆分不明；三季报）；λ 证据敏感性，**不入主公式**（A22）; as-of 2026-09-30
    'ni_ytd': 645.30,  # 2026 前三季度归母净利（亿元，三季报 64,530,063 千元；中报版本为 1H26 432.84）；已入账、从 FY2026 水平里扣掉得 4Q26 未入账利润，只用于把账面滚到 2027 年初（A21）; as-of 2026-09-30
    'payout_3y': 0.50,  # 近三年实付派息率均值（FY2023 5.028 元/股 ÷ EPS ≈ 50% / FY2024 5.783 ≈ 50% / FY2025 361.01 亿 ÷ 722.01 = 50%，Longbridge `dividend`）；实际留存 50% 只进「多留部分」披露行与 \(g\le(1-d)\times RONIC\) 校验，**不进** BPS 推演; as-of 2025-12-31
    'r_perp': 0.10,  # 篮 4 龙头制造 r = 10%（电池龙头，A20；无备选篮）；值 = `gordon.BASKET_R[4]`，`check_r` 按篮子强制；零增长 → 10×; as-of 2026-09-20
    'eps_fy26_l': 18.75,  # **L 档的 FY2026**：三季报前三季度基本 EPS 14.13 + 四季度按三季度单季 4.62 = 18.75（实测外推，非共识）；L 档的 4Q26 账面滚动与窗口利润用它（A1 / A21）; as-of 2026-09-30
    'eps_m': 25.65273,  # **M** FY2027E EPS = 共识均值（yfinance 11 家，A2）；≥2 家带区间的最远共识年；**三季报前的共识，待刷新**; as-of 2026-10-20
    'eps_h': 28.16,  # **H** FY2027E EPS = 共识区间上沿（yfinance 11 家，A3）；**三季报前，待刷新**; as-of 2026-10-20
    'consensus_n_fy27': 11,  # FY2027E 共识家数（yfinance `numberOfAnalysts +1y`）；≥2 才可作分子年（A2 / A19）; as-of 2026-10-20
    'eps_fy26_lo': 19.14,  # FY2026E 共识下沿（yfinance 10 家）；**对照带，不入主公式**（A19）; as-of 2026-10-20
    'eps_fy26_mean': 20.731,  # FY2026E 共识均值（10 家，三季报前）；对照带分子；**只经「4Q26 未入账利润 = 它 − 前三季度实测」进 M / H 档的账面滚动与窗口**（A21），不作锚点分子。它隐含四季度 EPS 6.60 vs 三季度实测 4.62，M / H 窗口利润因此偏高约 1.9 元/股（A2）; as-of 2026-10-20
    'eps_fy26_hi': 22.10,  # FY2026E 共识上沿（10 家）；**对照带，不入主公式**; as-of 2026-10-20
    'eps_fy26_lb': 21.430,  # Longbridge 季度共识合成 FY2026E（H1 实测 9.51 + Q3E 5.6707 + Q4E 6.2539）；**对照，不入主公式**; as-of 2026-09-08
    'g2_l': 0.02,  # **L** 永续增长（产能建完即止，只剩存量替换与通胀）（A7）；**来源层级：无同业锚**（仓库内无第二只动力电池票的 Gordon g2 可反解）；具名世界 g，非留存恒等式（A20）；≤ cap = min(6%, r − 4%) = 6% ✓; as-of 2026-09-18
    'g2_m': 0.03,  # **M** 永续增长（指引兑现后转名义低增长）（A7）；**来源层级：无同业锚**；具名世界 g（A20）；≤ cap 6% ✓; as-of 2026-09-18
    'g2_h': 0.04,  # **H** 永续增长（保有份额与海外溢价）（A7）；**来源层级：无同业锚**；具名世界 g（A20）；≤ cap 6% ✓; as-of 2026-09-18
    'pe_own_hi_recent': 25.2,  # own-year PE 实测上沿（2023 年起；2025 年高点）；整个股权的倍数，只作披露，**不入主公式**（A10）; as-of 2023~2026
    'pe_own_hi': 40.0,  # own-year PE 全期上沿（2022 赛道叙事顶点）；仅作对照，**不入主公式**; as-of 2022
    'pe_own_lo': 10.4,  # own-year PE 全期下沿（2024）；仅作对照，**不入主公式**; as-of 2024
    'eps_ttm': 18.9523,  # TTM EPS =（前三季度归母 645.30 + FY2025 722.01 − 2025 前三季度 490.34）÷ 46.2725 亿股；仅作 PE(TTM) 对照，**不入主公式**; as-of 2026Q3
    'eps_fy2025': 16.14,  # FY2025 实测 EPS（复权）；仅作 `deep_discount` 坐标，**不入主公式**; as-of FY2025
    'eps_freeze': 18.71,  # 纯冻结口径 EPS（未叠消费税）；A1 的中间量，**不入主公式**; as-of FY2026E
    'eps_freeze_tax': 16.28,  # 冻结口径 × 消费税无转嫁 −13%（v1 的 L 分子）；`deep_discount` 压力坐标，**不入主公式**（A1）; as-of FY2026E
    'tp_street': 559,  # 高盛 A 股目标价 CNY（2026-10-12 三季度预览，SOTP：动力 11× 2027E EBITDA、储能 16×；Wisburg 109323）；仅作交叉校验（A14），**不入主公式**; as-of 2026-10-12
    'tp_consensus': 540.33,  # 一致目标价 CNY（yfinance 均值，中位 535，区间 340–770）；仅作交叉校验，**不入主公式**; as-of 2026-10-20
    'fx_hkdcny': 0.8552,  # HKDCNY；与 `_AXIS.southbound-repricing.md` 同源取值，**不入主公式**; as-of 2026-09-11
    'net_cash': 2912.10,  # 净现金（Longbridge 净债务 −2,912.10 亿，与中报扩展口径 2,911.83 差 0.27 亿；三季报口径见 `net_cash_ext`）；快照对照，**不入主公式**（主公式走 A22 超额现金）; as-of 2026-06-30
    'unit_profit_h1': 86.92,  # 2026H1 单位净利 元/kWh（归母 432.84 亿 ÷ 产量 498 GWh）；A1 的实证坐标、\(V_{opt}\) 的单位经济（A18），**不入主公式**; as-of 2026H1
    'unit_profit_fy2025': 109.2,  # FY2025 单位净利 元/kWh（722.01 亿 ÷ 661 GWh，与高盛口径 109 吻合）；**不入主公式**; as-of FY2025
    'px_low_2026': 267.02,  # 2026 年内最低收盘（前复权，截至 2026-10-19；Longbridge 日 K）；A1 实证坐标，**不入主公式**（旧值 330.59 @ 2026-01-27）; as-of 2026-10-19
    'px_low_2025': 197.54,  # 2025 年内最低收盘（前复权）；**不入主公式**; as-of 2025-04-06
    'gp_other_rate': 0.6904,  # 「其他业务」毛利率（127.20 亿收入 / 87.82 亿毛利）；构成 `待补`（A13），**不入主公式**; as-of 2026H1
    'buyback_lo': 200,  # 新宣告 A 股回购下限（亿元，注销）；A17，**不入主公式**; as-of 2026-07-25
    'buyback_hi': 400,  # 新宣告 A 股回购上限（亿元，注销）；A17，**不入主公式**; as-of 2026-07-25
    'treasury_shares': 39264206,  # 回购专户库存股（0.85%；含 200–400 亿注销型回购已买入的 10,945,162 股 / 33.03 亿元，与激励用股同户，三季报）；A17，**不入主公式**; as-of 2026-09-30
    'opt_outstanding': 18108801,  # 在实施的三期激励授予合计（股/份，+0.391%）；A17，**不入主公式**; as-of 2026-06-30
    'cap_now_ann': 1050,  # 今日产能年化 GWh（2026 中报「产销情况」表：产能 525 GWh（半年）× 2）；**\(V_{opt}\) 输入，不入主公式**（A18）; as-of 2026-06-30
    'cap_build': 764,  # 在建产能 GWh（2026 中报同表；本票具名的量）；**\(V_{opt}\) 输入，不入主公式**（A18）; as-of 2026-06-30
    'util_h1': 0.9486,  # 2026H1 产能利用率（中报同表）；把建成后产能换成量；**\(V_{opt}\) 输入**; as-of 2026-06-30
    't_num': 2027,  # 分子年 = FY2027E；\(V_{opt}\) 折现终点; as-of 2026-10-03
    't_opt': 2029,  # 在建产能兑现年 = 对齐年份（本票最远共识年 FY2027）+ 2，**无时点锚·拍值**（中报未给分项目投产日）；**\(V_{opt}\) 输入**（A18）; as-of 2026-10-03
    'hu_gwh': 100,  # **期权·未投资本**：匈牙利德布勒森基地规划产能 GWh（公司 2022-08-12《关于投资建设匈牙利时代新能源电池产业基地项目的公告》：100 GWh 动力电池系统）；视为在建 764 GWh 的一部分（A18）; as-of 2022-08-12
    'hu_budget': 519.95,  # **期权·未投资本**：中报在建工程附注「重要在建工程项目」境外项目预算数（亿元，51,995,000 千元；= 公告上限 73.4 亿欧元按约 7.08 折人民币，故认定为匈牙利项目）; as-of 2026-06-30
    'hu_inv_pct': 0.3226,  # **期权·未投资本**：同表境外项目「工程累计投入占预算比例」32.26%（FY2025 年报同项 11.23%）; as-of 2026-06-30
    'dom_budget_gwh': 2.3333,  # **期权·未投资本**：匈牙利以外在建产能的单 GWh 预算（亿元/GWh）= 140 亿 ÷ 60 GWh——洛阳基地一期（公告 2022-09-28，投资不超过 140 亿元；规划 60 GWh）、济宁基地（公告 2022-07-21，不超过 140 亿元；环评 60 GWh）同值; as-of 2022-09-28
    'dom_inv_pct': 0.3397,  # **期权·未投资本**：中报同表西南地区项目（预算 240 亿）「工程累计投入占预算比例」33.97%，作为境内在建产能的已投比例代理（附注只列这一个境内重要项目）; as-of 2026-06-30
    'opt_eq': 0.9203,  # **期权·未投资本**：本票权益比例代理 = 2026H1 归母净利 432.84 ÷ 净利润 470.31 亿（中报利润表）；单位净利是归母口径，资本同按归母份额扣; as-of 2026-06-30
}

TIERS = ("l", "m", "h")
OPTION_FIELDS = frozenset({'unit_profit_h1', 'cap_now_ann', 'cap_build', 'util_h1', 't_opt',
                           'hu_gwh', 'hu_budget', 'hu_inv_pct', 'dom_budget_gwh', 'dom_inv_pct', 'opt_eq'})
MIN_SPREAD = 0.02          # r - g2 floor (valuation-rules ①)
MIN_CONSENSUS_HOUSES = 2   # a numerator year needs >= 2 houses with a range (②)
ANCHOR_CAP = 2 / 12        # operating cash anchor capped at 2 months of revenue
EXCESS_TRIGGER = 0.15      # C_ex >= 15% of parent equity → separate line
CASH_WINDOW = range(2018, 2026)   # listed years (IPO 2018-06), A22

# Year-end figures (亿元, Eastmoney F10 statements, the original financial statements): extended net cash (cash + trading financial assets −
# interest-bearing debt − lease − dividend payable), revenue; for the fence
# years also parent NI, cash yield ((interest income + fair-value gains) ÷
# average cash-like assets) and effective tax rate.  Pre-IPO 2016–17 are kept
# only for the window sensitivity.
EXT = {2016: 6.9, 2017: 93.4, 2018: 221.3, 2019: 239.6, 2020: 435.7, 2021: 363.8825,
       2022: 925.1919, 2023: 1391.2519, 2024: 1759.9249, 2025: 2728.4997}
REV = {2016: 148.8, 2017: 200.0, 2018: 296.1, 2019: 457.9, 2020: 503.2, 2021: 1303.5580,
       2022: 3285.9399, 2023: 4009.1705, 2024: 3620.1255, 2025: 4237.0183}
NI = {2022: 307.2916, 2023: 441.2125, 2024: 507.4468, 2025: 722.0128}
YLD = {2022: 0.030957, 2023: 0.036595, 2024: 0.034932, 2025: 0.032574}
TAX = {2022: 0.087686, 2023: 0.132674, 2024: 0.145219, 2025: 0.142307}
# own-year PE (前复权收盘 ÷ 复权 EPS, daily) low / high per year (A10)
PE_OWN = {2022: (25.2, 40.0), 2023: (12.6, 24.1), 2024: (10.4, 24.5), 2025: (12.2, 25.2)}

# Fields the anchor path is allowed to touch.  Everything else in the Inputs
# table is cross-check material, and the guard below proves it stays out.
FORMULA_FIELDS = frozenset({
    "shares", "equity", "r_perp",
    "eps_l", "eps_m", "eps_h",
    "g2_l", "g2_m", "g2_h",
    "eps_fy26_mean", "ni_ytd",    # only via the 4Q26 unbooked earnings in the book roll (A21)
    "eps_fy26_l",                 # L: digestion year, FY2027 = FY2026 run-rate (A1, user 2026-10-20)
    "net_cash_ext", "div_declared", "rev_fy2025", "cash_ratio_min",
    "cash_yield", "tax_eff",      # excess cash and its after-tax income (A22)
    "minority",                   # parent share of C_ex (A22)
    "tau", "y1", "y2", "ronic_ss",   # time alignment and the three-stage return (A23)
})

REQUIRED = sorted(FORMULA_FIELDS | {
    "bps", "consensus_n_fy27", "payout_3y", "payout_op", "c_ex", "cash_restricted",
    "eps_fy26_lo", "eps_fy26_hi", "eps_fy26_lb",
    "pe_own_hi_recent", "pe_own_hi", "pe_own_lo", "pe_op_hi_recent", "pe_op_hi", "pe_op_lo",
    "eps_ttm", "eps_fy2025", "eps_freeze", "eps_freeze_tax",
    "tp_street", "tp_consensus", "fx_hkdcny",
    "net_cash", "unit_profit_h1", "unit_profit_fy2025",
    "px_low_2026", "px_low_2025", "gp_other_rate",
    "buyback_lo", "buyback_hi", "treasury_shares", "opt_outstanding",
    "cap_now_ann", "cap_build", "util_h1", "t_num", "t_opt",
    "hu_gwh", "hu_budget", "hu_inv_pct", "dom_budget_gwh", "dom_inv_pct", "opt_eq",
    "parent_ratio", "ronic_ss_floor",
})
T0 = 2027                  # numerator year: the Gordon value sits at its start
BS_MONTH = 9               # balance-sheet date 2026-09-30 (3Q26 report): YTD = 9 months

# 表3 only — never Inputs, never the base band (A2e-7a).
P_K = (0.0, 0.25, 1.0)


# --- excess cash and the operating basis (A22) ------------------------------------
def cash_anchor(inp: dict[str, float]) -> float:
    """Operating cash anchor (亿): min(lowest listed-year ratio, 2 months) × FY2025 revenue."""
    return max(min(inp["cash_ratio_min"], ANCHOR_CAP), 0.0) * inp["rev_fy2025"]


def excess_cash_total(inp: dict[str, float]) -> float:
    """C_ex (亿, consolidated) = extended net cash − declared / ex-dividend unpaid dividend − anchor."""
    return inp["net_cash_ext"] - inp["div_declared"] - cash_anchor(inp)


def parent_ratio(inp: dict[str, float]) -> float:
    """① 归母份额: no subsidiary-level cash disclosure -> parent equity / (parent + minority),
    the parent side net of the interim dividend (already out of the cash)."""
    eq = inp["equity"] - inp["div_declared"]
    return eq / (eq + inp["minority"])


def excess_cash(inp: dict[str, float]) -> float:
    """Parent-share C_ex (亿) — what enters value, the numerator's cash income and the operating book."""
    return excess_cash_total(inp) * parent_ratio(inp)


def path_pe(inp: dict[str, float], g: float, roe: float, t0: int = T0, fresh: bool = False) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段), value at the start of t0 per
    unit of t0 earnings: RONIC = roe through y1, linear to min(roe, ronic_ss) by y2, perpetual on.
    y1 / y2 are calendar years (default t0 = T0).  `fresh=True` restarts the period at t0
    (y1 = t0, y2 = t0 + (y2 − y1)) -- the pre-2026-10-19 implicit read of the option, disclosure only."""
    r, y1, y2 = inp["r_perp"], int(inp["y1"]), int(inp["y2"])
    if fresh:
        y1, y2 = t0, t0 + (y2 - y1)
    ss = min(roe, inp["ronic_ss"])
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g, ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def cash_ps(inp: dict[str, float]) -> float:
    return excess_cash(inp) * 1e8 / inp["shares"]


def cash_income_ps(inp: dict[str, float]) -> float:
    """After-tax income of today's C_ex per share — taken out of every forward numerator."""
    return excess_cash(inp) * inp["cash_yield"] * (1.0 - inp["tax_eff"]) * 1e8 / inp["shares"]


def unbooked_op_eps(inp: dict[str, float]) -> float:
    """4Q26 operating EPS not yet in the 3Q26 book: FY2026 level − 9M actual − the unbooked quarter of cash income."""
    return (inp["eps_fy26_mean"] - inp["ni_ytd"] * 1e8 / inp["shares"]
            - cash_income_ps(inp) * (1 - BS_MONTH / 12))


def tier_inp(inp: dict[str, float], t: str) -> dict[str, float]:
    """L lives in its own FY2026: the digestion year holds FY2027 at the 3Q26 run-rate FY2026
    (eps_fy26_l), so its book roll and window use that, not the FY2026E consensus (A1)."""
    return {**inp, "eps_fy26_mean": inp["eps_fy26_l"]} if t == "l" else inp


def obps_2q26(inp: dict[str, float]) -> float:
    """Balance-sheet-date (3Q26) operating book per share: parent equity − declared unpaid dividend − C_ex."""
    return (inp["equity"] - inp["div_declared"] - excess_cash(inp)) * 1e8 / inp["shares"]


def obps_open_2027(inp: dict[str, float], e_op: float, g: float) -> float:
    """Opening-2027 operating BPS: rolled over 4Q26 at b1 = g/RONIC, closed form (A21)."""
    return obps_2q26(inp) / (1.0 - g * unbooked_op_eps(inp) / e_op)


def ronic(inp: dict[str, float], e_op: float, g: float) -> float:
    return e_op / obps_open_2027(inp, e_op, g)


def op_value(inp: dict[str, float], e_op: float, g: float) -> float:
    """Operating value at the start of FY2027 per share + excess cash per share (lambda = 1); not aligned."""
    return e_op * path_pe(inp, g, ronic(inp, e_op, g)) + cash_ps(inp)


def window_ps(inp: dict[str, float], e_op: float, g: float) -> float:
    """4Q26 window distributable profit per share: unbooked operating EPS x (1 − b), b = g/RONIC (③)."""
    return max(unbooked_op_eps(inp) * (1.0 - g / ronic(inp, e_op, g)), 0.0)


def aligned(inp: dict[str, float], e_op: float, g: float) -> float:
    """Today's value: operating value x (1+r)^-tau + window x (1+r)^-(tau/2) + excess cash (③ 时点对齐)."""
    r, tau = inp["r_perp"], inp["tau"]
    v = op_value(inp, e_op, g) - cash_ps(inp)
    return v * (1 + r) ** -tau + window_ps(inp, e_op, g) * (1 + r) ** -(tau / 2) + cash_ps(inp)


def e_op(inp: dict[str, float], eps: float) -> float:
    return eps - cash_income_ps(inp)


def anchor(inp: dict[str, float], tag: str) -> float:
    ti = tier_inp(inp, tag)
    return aligned(ti, e_op(ti, ti[f"eps_{tag}"]), ti[f"g2_{tag}"])


# --- history on the operating basis (A10 / A22) -----------------------------------
def cex_hist(ratio: float) -> dict[int, float]:
    """C_ex(t) = max(extended net cash(t) − ratio × revenue(t), 0)."""
    return {y: max(EXT[y] - ratio * REV[y], 0.0) for y in EXT}


def op_band(ratio: float) -> dict[int, tuple[float, float, float]]:
    """Own-year PE → operating multiple (P − c_t) / E_op(t), c_t = average of the
    year's opening and closing C_ex (the reports visible during the year)."""
    cx = cex_hist(ratio)
    out = {}
    for y, (lo, hi) in PE_OWN.items():
        c_avg = (cx[y - 1] + cx[y]) / 2
        op = NI[y] - c_avg * YLD[y] * (1 - TAX[y])
        out[y] = ((lo * NI[y] - c_avg) / op, (hi * NI[y] - c_avg) / op, op / NI[y])
    return out


def capacity_option(inp: dict[str, float], base_h: float, fresh: bool = False) -> dict[str, float]:
    # base_h: the H tier's unaligned value at the start of FY2027 (op_value) -- printed for reference;
    # the option itself is valued in the realisation year on both sides (2026-10-19, A18).
    """V_opt — the named in-construction capacity beyond what the H tier already
    implies (A18, valuation-rules「未建模期权」2026-10-03), on the same operating
    Gordon ruler as the H tier (H-tier operating opening BPS, g2_h).

    Size: (today's annualised capacity + in-construction) x 2026H1 utilisation
    = volume once built; minus the volume the FY2027E consensus HIGH already
    implies at the 2026H1 unit net profit.  Less the unspent capital behind the
    option's share of the in-construction capacity (2026-10-04).
    """
    vol_full = (inp["cap_now_ann"] + inp["cap_build"]) * inp["util_h1"]          # GWh
    vol_in_h = inp["eps_h"] * inp["shares"] / (inp["unit_profit_h1"] * 1e6)    # GWh
    d_vol = vol_full - vol_in_h
    d_ni = d_vol * inp["unit_profit_h1"] / 100.0                               # 亿
    d_eps = d_ni * 1e8 / inp["shares"]
    eop_h = e_op(inp, inp["eps_h"])
    obps_h = obps_open_2027(inp, eop_h, inp["g2_h"])
    eop_post = eop_h + d_eps
    ronic_post = eop_post / obps_h
    # Product-stage check (A18, 2026-10-19): the capacity makes the batteries CATL already ships at
    # scale -- same product, same 环节 -- so it inherits the calendar high-return period Y1 2027 /
    # Y2 2031 and is valued in t_opt with the fall already under way.  Both sides (with and without
    # the increment) sit in t_opt on the same path; reusing the 2027-start multiples at t_opt (the
    # old construction) silently restarted the period at the capacity's start.
    t_opt = int(inp["t_opt"])
    pe_post = path_pe(inp, inp["g2_h"], ronic_post, t_opt, fresh)
    pe_base = path_pe(inp, inp["g2_h"], eop_h / obps_h, t_opt, fresh)
    anchor_post = eop_post * pe_post + cash_ps(inp)
    base_t = eop_h * pe_base + cash_ps(inp)
    # to the numerator year, then tau to the valuation date (③ 时点对齐: V_opt discounted to t_n is aligned too)
    disc = (1.0 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]) - inp["tau"])
    k_hu = inp["hu_budget"]
    k_dom = (inp["cap_build"] - inp["hu_gwh"]) * inp["dom_budget_gwh"]
    k_budget = k_hu + k_dom
    k_spent = k_hu * inp["hu_inv_pct"] + k_dom * inp["dom_inv_pct"]
    k_remain = k_budget - k_spent                                              # 亿
    share_opt = d_vol / (inp["cap_build"] * inp["util_h1"])
    k_opt = k_remain * share_opt * inp["opt_eq"]                               # 亿
    k_ps = k_opt * 1e8 / inp["shares"]
    return {"vol_full": vol_full, "vol_in_h": vol_in_h, "d_vol": d_vol, "d_ni": d_ni,
            "d_eps": d_eps, "ronic_post": ronic_post, "pe_post": pe_post,
            "anchor_post": anchor_post, "base_t": base_t, "pe_base": pe_base, "disc": disc,
            "k_budget": k_budget, "k_spent": k_spent, "k_remain": k_remain,
            "share_opt": share_opt, "k_opt": k_opt, "k_ps": k_ps,
            "v_gross": (anchor_post - base_t) * disc,
            "v_opt": (anchor_post - base_t - k_ps) * disc}


def band_edge_g(inp: dict[str, float], ron: float, pe_edge: float) -> float:
    """Perpetual g that lands the operating multiple (same three-stage path) on a band edge (③)."""
    r = inp["r_perp"]
    lo, hi = -0.10, g_cap(r)
    for _ in range(200):
        mid = (lo + hi) / 2
        if path_pe(inp, mid, ron) < pe_edge:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2




def evaluate(inp):
    errors = check_missing(inp, list(INPUTS) + ['cash_ratio_min', 'c_ex', 'parent_ratio', 'pe_op_lo', 'pe_op_hi', 'pe_op_hi_recent', 'eps_l', 'tau'])
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('t_num', 'y1', 'y2'))
    if any(not math.isfinite(inp[k]) for k in INPUTS if k not in OPTION_FIELDS):
        raise ValueError('base model inputs must be finite')
    r, sh = inp['r_perp'], inp['shares']
    baskets = {'r_perp': 4}
    # --- Step 0: excess cash (A22) -------------------------------------------
    ratio_obs = min(EXT[y] / REV[y] for y in CASH_WINDOW)
    if abs(ratio_obs - inp["cash_ratio_min"]) > 5e-5:
        errors.append(f"cash_ratio_min {inp['cash_ratio_min']} != FY2018–25 lowest {ratio_obs:.5f}")
    c_tot = excess_cash_total(inp)
    if abs(c_tot - inp["c_ex"]) > 0.05:
        errors.append(f"c_ex {inp['c_ex']} != net_cash_ext − div_declared − anchor {c_tot:.2f}")
    pr = parent_ratio(inp)
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = excess_cash(inp)
    tau_calc = ((T0 - 2026) * 12 - BS_MONTH) / 12   # 2026-09-30 balance sheet -> 2027-01-01
    if abs(inp["tau"] - tau_calc) > 1e-9:
        errors.append(f"tau {inp['tau']} != {tau_calc}")
    if not (inp["y1"] == T0 and inp["y2"] == inp["y1"] + 4):
        errors.append("Y1 must be the visible-year end FY2027 and Y2 = Y1 + 4 (medium entry barrier, A23)")
    # The floor is a substitute, not a lower bound (ordered pick, 2026-10-19): only r binds.
    if inp["ronic_ss"] < inp["r_perp"]:
        errors.append("ronic_ss below r (A23)")
    eq_adj = inp["equity"] - inp["div_declared"]
    excess_cash_threshold_unmet = c_ex < EXCESS_TRIGGER * eq_adj
    cps, inc_ps = cash_ps(inp), cash_income_ps(inp)

    # --- Step 1-2: ladders and the numerator-year qualification (②) ---------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    # A1 (user 2026-10-20): L = digestion year -- FY2027 held at the FY2026 run-rate level.
    if abs(inp["eps_l"] - inp["eps_fy26_l"]) > 1e-9:
        errors.append(f"eps_l {inp['eps_l']} != eps_fy26_l {inp['eps_fy26_l']} (digestion year, A1)")
    errors += ladder("g2", inp["g2_l"], inp["g2_m"], inp["g2_h"])
    if inp["consensus_n_fy27"] < MIN_CONSENSUS_HOUSES:
        errors.append(
            f"consensus_n_fy27={inp['consensus_n_fy27']:.0f} < {MIN_CONSENSUS_HOUSES} — "
            f"FY2027E no longer qualifies as the numerator year; fall back to FY2026E (A19)"
        )
    if obps_2q26(inp) <= 0:
        errors.append("operating equity (equity − interim dividend − C_ex) must be positive")
    ti = {t: tier_inp(inp, t) for t in TIERS}
    n_op_t = {t: unbooked_op_eps(ti[t]) for t in TIERS}
    n_op = n_op_t["m"]
    eop = {t: e_op(inp, inp[f"eps_{t}"]) for t in TIERS}
    for t in TIERS:
        if n_op_t[t] <= 0:
            errors.append(f"unbooked 4Q26 operating EPS for {t} = {n_op_t[t]:.2f} <= 0")
        k = inp[f"g2_{t}"] * n_op_t[t] / eop[t]
        if k >= 1.0:
            errors.append(f"book roll diverges for {t}: g2·N/E_op = {k:.3f} >= 1 (A21)")
    if errors:
        raise ValueError('; '.join(errors))

    obps_open = {t: obps_open_2027(ti[t], eop[t], inp[f"g2_{t}"]) for t in TIERS}
    ron = {t: ronic(ti[t], eop[t], inp[f"g2_{t}"]) for t in TIERS}
    b1 = {t: inp[f"g2_{t}"] / ron[t] for t in TIERS}
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"b1_{t} = g2/RONIC = {b1[t]:.3f} outside (0, 1) (A21)")

    # --- Step 3-4: convergence, retention cost, branch, constraint 2 ---------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for t in TIERS:
        g2 = inp[f"g2_{t}"]
        if ron[t] <= 0:
            errors.append(f"RONIC_{t}={ron[t]:.4f} must be positive")
        errors += check_g_cap(g2, r, f"g2_{t}")
        if r - g2 < MIN_SPREAD - 1e-12:
            errors.append(f"r - g2_{t} = {r - g2:.2%} < {MIN_SPREAD:.0%} — perpetuity ill-conditioned")
        pay = payout(g2, ron[t])
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        errors += check_branch(g2, ron[t], r, inp["payout_op"], f"g2_{t}")
        # ③ 约束 2: g <= (1 − d) × RONIC — what the company keeps caps the growth it can fund
        if g2 > (1.0 - inp["payout_3y"]) * ron[t] + 1e-12:
            errors.append(f"g2_{t} {g2:.2%} > (1 − d) × RONIC = {(1 - inp['payout_3y']) * ron[t]:.2%}")
    if errors:
        raise ValueError('; '.join(errors))

    pe = {t: path_pe(inp, inp[f"g2_{t}"], ron[t]) for t in TIERS}
    win = {t: window_ps(ti[t], eop[t], inp[f"g2_{t}"]) for t in TIERS}
    dtau = (1 + r) ** -inp["tau"]

    # --- Step 5: the own-year fence on the operating basis (A10) -------------
    band = op_band(min(inp["cash_ratio_min"], ANCHOR_CAP))
    op_lo, op_hi = band[2024][0], band[2022][1]
    op_hi_recent = max(band[y][1] for y in (2023, 2024, 2025))
    for key, want in (("pe_op_lo", op_lo), ("pe_op_hi", op_hi), ("pe_op_hi_recent", op_hi_recent)):
        if abs(inp[key] - want) > 0.01:
            errors.append(f"{key} {inp[key]} != recomputed operating band edge {want:.2f}")
    historical_multiple_outside = any(
        not inp["pe_op_lo"] - 1e-9 <= pe[t] <= inp["pe_op_hi"] + 1e-9 for t in TIERS)
    historical_high_above_recent = pe["h"] > inp["pe_op_hi_recent"] + 1e-9

    # --- Step 8: the non-formula fields really are non-formula ---------------
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append("anchor path touches a non-formula field")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 9: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        raise ValueError(f'L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}')
    A, B = cut_points(L, M, H)

    # Step 6: a flat multiple must still leave a ladder (A2e-2c), cash included.
    flat = [eop[t] * pe["m"] * dtau + win[t] * (1 + r) ** -(inp["tau"] / 2) + cps for t in TIERS]
    errors += ladder("flat-multiple", *flat)

    # Step 7: V_opt (A18) — held outside the base band; stated values must reproduce.
    h_unal = op_value(inp, eop["h"], inp["g2_h"])
    # Decide whether the incremental project exists before evaluating its
    # profitability or allocating its capital: those calculations divide by
    # capacity/utilisation and assume a positive increment.
    option_unavailable_reason = None
    opt = opt_fresh = None
    if any(not math.isfinite(inp[key]) for key in OPTION_FIELDS):
        option_unavailable_reason = 'project_input_not_finite'
    elif inp['t_opt'] != int(inp['t_opt']) or inp['t_opt'] < inp['t_num']:
        option_unavailable_reason = 'project_date_invalid'
    elif any(not 0 <= inp[key] <= 1 for key in ('hu_inv_pct', 'dom_inv_pct', 'opt_eq')):
        option_unavailable_reason = 'project_fraction_invalid'
    elif inp['cap_build'] <= 0 or inp['util_h1'] <= 0 or inp['unit_profit_h1'] <= 0:
        option_unavailable_reason = 'capacity_or_unit_profit_not_positive'
    else:
        full_volume = (inp['cap_now_ann'] + inp['cap_build']) * inp['util_h1']
        high_volume = inp['eps_h'] * inp['shares'] / (inp['unit_profit_h1'] * 1e6)
        if full_volume <= high_volume:
            option_unavailable_reason = 'incremental_capacity_not_positive'
        else:
            # The optional project's arithmetic may be invalid while the base
            # business remains calculable. Keep the explicit failure state;
            # never apply this exception handling to the base calculation.
            try:
                opt = capacity_option(inp, h_unal)
                if any(not math.isfinite(value) for value in opt.values()):
                    option_unavailable_reason = 'project_result_not_finite'
                elif opt['v_opt'] <= 0:
                    option_unavailable_reason = 'incremental_value_not_positive'
                elif not 0 < opt['share_opt'] <= 1:
                    option_unavailable_reason = 'project_capacity_share_invalid'
                else:
                    opt_fresh = capacity_option(inp, h_unal, fresh=True)
                    if any(not math.isfinite(value) for value in opt_fresh.values()):
                        option_unavailable_reason = 'project_result_not_finite'
                    elif opt['pe_post'] > opt_fresh['pe_post'] + 1e-12:
                        option_unavailable_reason = 'project_return_path_invalid'
            except (ValueError, ZeroDivisionError, OverflowError):
                option_unavailable_reason = 'project_calculation_failed'
    if option_unavailable_reason:
        opt_fresh = None
    option_unavailable = option_unavailable_reason is not None
    if any(k.startswith("p_") for k in inp):
        errors.append("probability fields present in §3 Inputs (A2e-7a)")
    if errors:
        raise ValueError('; '.join(errors))
    as_band = lambda xs: dict(zip('LMH', xs))
    def ruler(eop_x, g):
        return aligned(inp, eop_x, g)
    fy26 = tuple(ruler(e_op(inp, inp[key]), inp[f'g2_{tier}']) for key, tier in
                 (('eps_fy26_lo', 'l'), ('eps_fy26_mean', 'm'), ('eps_fy26_hi', 'h')))
    freeze = ruler(e_op(inp, inp['eps_freeze_tax']), inp['g2_l'])
    fy25_op = inp['eps_fy2025'] * band[2025][2]
    fy25 = ruler(fy25_op, inp['g2_l'])
    e26m, e26h = e_op(inp, inp['eps_fy26_mean']), e_op(inp, inp['eps_fy26_hi'])
    r26m, r26h = ronic(inp, e26m, inp['g2_m']), ronic(inp, e26h, inp['g2_h'])
    g1_m = inp['eps_m'] / inp['eps_fy26_mean'] - 1
    g1_h = inp['eps_h'] / inp['eps_fy26_hi'] - 1
    v1 = (two_stage_pe(g1_m, 1, inp['g2_m'], r26m, r) * e26m + cps,
          two_stage_pe(g1_h, 1, inp['g2_h'], r26h, r) * e26h + cps,
          two_stage_pe(.20, 3, inp['g2_m'], r26m, r) * e26m + cps,
          two_stage_pe(.27, 3, inp['g2_h'], r26h, r) * e26h + cps)
    sensitivity = {
        'fy2026_forecast': as_band(fy26), 'fy2026_longbridge': ruler(e_op(inp, inp['eps_fy26_lb']), inp['g2_m']),
        'freeze_tax': freeze, 'fy2025_actual': fy25, 'old_two_stage': v1,
        'growth_minus_1pp': as_band(ruler(eop[t], inp[f'g2_{t}'] - .01) for t in TIERS),
        'growth_plus_1pp': as_band(ruler(eop[t], inp[f'g2_{t}'] + .01) for t in TIERS),
        'flat_growth': as_band(ruler(eop[t], inp['g2_m']) for t in TIERS),
        'flat_multiple': as_band(flat), 'option_restart': opt_fresh,
    }
    for name, tweak in (
        ('cash_window_preipo', {'cash_ratio_min': min(EXT[y] / REV[y] for y in range(2016, 2026))}),
        ('cash_restricted', {'net_cash_ext': inp['net_cash_ext'] - inp['cash_restricted']}),
    ):
        alt = {**inp, **tweak}
        sensitivity[name] = {'cash': excess_cash(alt), 'anchors': as_band(anchor(alt, t) for t in TIERS)}
    # 额外电池产能单列；经营价值用三段 Gordon，加超额现金。
    option = None
    if not option_unavailable:
        band3 = tuple(base + P_K[i] * opt['v_opt'] for i, base in enumerate((L, M, H)))
        a3, b3 = cut_points(*band3)
        option = {'label': 'additional_battery_capacity', 'value': opt['v_opt'],
                  'weights': as_band(P_K), 'anchors': as_band(band3),
                  'cut_points': {'A': a3, 'B': b3}, 'details': opt}
    result = {
        'ticker': '300750.SZ', 'currency': 'CNY',
        'valuation_as_of': None, 'historical_valuation_as_of': '2026-09-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-20', 'historical_framework_as_of': '2026-10-20',
        'anchors': as_band((L, M, H)), 'cut_points': {'A': A, 'B': B}, 'candidate': None,
        'option': option,
        'segments': {'operating': {'values': as_band(anchor(inp, t) - cps for t in TIERS)},
                     'excess_cash': {'values': dict.fromkeys('LMH', cps)}},
        'key_parameters': {'method': dict.fromkeys('LMH', 'operating_gordon_three_stage_plus_excess_cash'),
                           'discount_rate': dict.fromkeys('LMH', r),
                           'growth_rate': as_band(inp[f'g2_{t}'] for t in TIERS),
                           'forward_return': as_band(ron[t] for t in TIERS),
                           'steady_return': as_band(min(ron[t], max(inp['ronic_ss'], r)) for t in TIERS),
                           'multiple': as_band(pe[t] for t in TIERS)},
        'operating': {'cash_ratio': ratio_obs, 'excess_cash_total': c_tot, 'parent_ratio': pr,
                      'excess_cash': c_ex, 'cash_per_share': cps, 'cash_income_per_share': inc_ps,
                      'eps': as_band(eop[t] for t in TIERS), 'unbooked': as_band(n_op_t[t] for t in TIERS),
                      'opening_book': as_band(obps_open[t] for t in TIERS), 'retention': as_band(b1[t] for t in TIERS),
                      'window': as_band(win[t] for t in TIERS), 'historical_operating_band': band},
        'sensitivity': sensitivity,
    }

    result['excess_cash_threshold_unmet'] = excess_cash_threshold_unmet
    result['historical_multiple_outside'] = historical_multiple_outside
    result['historical_high_above_recent'] = historical_high_above_recent
    result['option_unavailable'] = option_unavailable
    result['option_unavailable_reason'] = option_unavailable_reason
    return result


def derived_inputs(inputs):
    # All eight rows were documented as calculations of these inputs or of
    # the frozen historical samples. Retain their original adopted precision.
    ratio = round(min(EXT[y] / REV[y] for y in CASH_WINDOW), 6)
    data = {**inputs, 'cash_ratio_min': ratio}
    band = op_band(min(ratio, ANCHOR_CAP))
    return {'cash_ratio_min': ratio, 'c_ex': round(excess_cash_total(data), 2),
            'parent_ratio': round(parent_ratio(data), 4),
            'pe_op_lo': round(band[2024][0], 2), 'pe_op_hi': round(band[2022][1], 2),
            'pe_op_hi_recent': round(max(band[y][1] for y in (2023, 2024, 2025)), 2),
            'eps_l': inputs['eps_fy26_l'], 'tau': ((T0 - 2026) * 12 - BS_MONTH) / 12}


def calculate(context):
    result = evaluate({**INPUTS, **derived_inputs(INPUTS)})
    result['basis_changed'] = None
    if any(not math.isfinite(INPUTS[key]) for key in OPTION_FIELDS if key in INPUTS):
        # Non-finite values are not valid JSON and cannot be fingerprinted;
        # they nevertheless represent a change to the historical basis.
        result['partial_basis_changed'] = True
    else:
        result['partial_basis_changed'] = local_basis_changed(
            {'inputs': INPUTS, 'tiers': TIERS, 'min_spread': MIN_SPREAD, 'minimum_houses': MIN_CONSENSUS_HOUSES,
             'anchor_cap': ANCHOR_CAP, 'excess_trigger': EXCESS_TRIGGER, 'cash_window': list(CASH_WINDOW),
             'ext': EXT, 'revenue': REV, 'income': NI, 'yield': YLD, 'tax': TAX, 'pe_own': PE_OWN,
             'numerator_year': T0, 'balance_month': BS_MONTH, 'option_weights': P_K}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    for segment in result['segments'].values():
        segment['unit'] = 'CNY_PER_SHARE'
    if result['option_unavailable']:
        result['option'] = {'status': 'unavailable', 'label': '新增产能', 'anchors': None}
    else:
        result['option']['value_unit'] = 'CNY_PER_SHARE'
    result['review_flags'] = ['historical_future_capex_and_restricted_cash_unverified',
                              'historical_capacity_demand_and_battery_overlap_unverified',
                              'historical_forecast_after_earnings_unverified']
    if result['excess_cash_threshold_unmet']:
        result['review_flags'].append('excess_cash_separation_threshold_unmet')
    if result['historical_multiple_outside'] or result['historical_high_above_recent']:
        result['review_flags'].append('historical_operating_multiple_needs_review')
    return result
