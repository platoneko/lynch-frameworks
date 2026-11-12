#!/usr/bin/env python3
"""Historical Yihua two-leg valuation; not updated financial research.

Amounts and shares follow the original inputs; output is CNY/share. The two
analyst forecasts are thinly covered: the historical rule places their upper
forecast only in H, while L/M use the company's observed segment trends. The
solar subgroup, connector residual and minority-interest assumptions retain
their original source and accounting limitations. The named solar project is
already inside the base and is not a separate unmodeled option.

Historical valuations use a distorted equal-earnings band and an independent
reconciliation gate. The historical inputs, dates and user decisions remain
disclosed; the calculations do not establish that the economic forecasts or
project return will be realized.
"""
# Historical evidence and limits retained from the document:
# Guojin 2026-08-30 and Guohai 2026-05-24 forecast FY2028 group profit;
# neither provided segment forecasts. The H connector profit is a residual
# after estimated solar profit, not a sell-side segment estimate. Q3 2026
# group profit was 0.50 CNY 100 million, below the original H evidence gate;
# the old high forecast was not recomputed after the report.
# Solar TTM profit combines H1 2026 subsidiaries with H1 2025 estimated from
# gross profit conversion; connector profit is a residual after group minority
# interests and the solar estimate. Different periods use different bases.
# A FY2026 recurring-profit upgrade can be mechanically met because a 2024
# bad-debt charge lowered the base, even though the old H path was falsified;
# resolve that evidence conflict before treating an upgrade as justified.
# The named Yueqing project has budget 3.74 and spent 2.20 CNY 100 million;
# existing 0.75 CNY/share project value is already included, net of remaining
# spending. Remove that separate value when the project's income enters the
# observed earnings, to avoid double counting.
# Original sources: FY2025 report, 2025 and 2026 interim reports, 2026Q3
# report, Yueqing New Energy appraisal 2026-04-29 and the two analyst reports.
from __future__ import annotations

import math
from lib.gordon import capped_payout_pe, check_g_cap, check_r, g_cap, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.tiers import decompose
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'), 'axes': {}}

HISTORICAL_PARTIAL_FINGERPRINT = '0822c3fdb417043d7bb3de4001fe86ebfcc8159107ee2b3452082bfb9b6b56f3'

INPUTS = {
    'shares': 1.9388e8,  # 总股本; as-of 半年报 193,880,696 股，2026-06-30
    'equity_total': 2.8236e9,  # 归属上市公司股东净资产 CNY; as-of 半年报 2,823,611,190.59，2026-06-30
    'equity_solar': 1.2853e9,  # 光伏子集团所有者权益（合并口径，100% 持股）CNY；不滚动; as-of 评估报告 1,285,337,731.91，2025-12-31
    'rev_conn_fy23': 1.784467e9,  # 连接器收入 FY2023; as-of FY2023 年报 1,784,467,423.28
    'rev_conn_fy25': 2.633861e9,  # 连接器收入 FY2025; as-of FY2025 年报 2,633,861,475.29
    'rev_conn_h1_23': 7.94475e8,  # 连接器收入 H1 2023; as-of 2024 半年报上年同期 794,475,264.41
    'rev_conn_h1_24': 1.113521e9,  # 连接器收入 H1 2024; as-of 2024 半年报 1,113,520,671.00
    'rev_conn_h1_25': 1.214393e9,  # 连接器收入 H1 2025; as-of 2025 半年报 1,214,392,755.92
    'rev_conn_h1_26': 1.474088e9,  # 连接器收入 H1 2026; as-of 2026 半年报 1,474,087,536.11
    'rev_solar_fy23': 3.136668e9,  # 太阳能支架收入 FY2023; as-of FY2023 年报 3,136,667,880.00
    'rev_solar_fy25': 3.496083e9,  # 太阳能支架收入 FY2025; as-of FY2025 年报 3,496,082,838.81
    'rev_solar_h1_23': 1.369101e9,  # 太阳能支架收入 H1 2023; as-of 2024 半年报上年同期 1,369,101,114.62
    'rev_solar_h1_24': 1.932153e9,  # 太阳能支架收入 H1 2024; as-of 2024 半年报 1,932,153,012.99
    'rev_solar_h1_25': 1.761128e9,  # 太阳能支架收入 H1 2025; as-of 2025 半年报 1,761,128,446.58
    'rev_solar_h1_26': 1.223389e9,  # 太阳能支架收入 H1 2026; as-of 2026 半年报 1,223,388,833.47
    'gm_solar_fy25': 0.1515,  # 支架毛利率 FY2025（H1'25 光伏净利换算，A18）; as-of FY2025 年报
    'gm_solar_h1_25': 0.1323,  # 支架毛利率 H1 2025; as-of 2025 半年报
    'ni_solar_h1_26': 0.27e8,  # 光伏腿 H1 2026 净利：子公司表直接加总（乐清 0.16 / 泰国 −0.17 / 香港 0.28；100% 持股即归母，A18）; as-of 2026 半年报
    'nr_ttm_2q26': 2.2777e8,  # 最近四季扣非归母 = FY2025 2.854 + H1'26 0.934 − H1'25 1.510 亿（升级门槛，A10）; as-of FY2025 年报 / 2025、2026 半年报
    'nr_ttm_2q24': 2.0919e8,  # 两年前滚动四季扣非 = 3Q23 0.323 + 4Q23 0.161 + 1Q24 0.816 + 2Q24 0.791 亿; as-of FY2023 / FY2024 年报分季度表
    'nr_ttm_3q24': 2.3193e8,  # 3Q2024 滚动四季扣非 = 4Q23 0.161 + 1Q24 0.816 + 2Q24 0.791 + 3Q24 0.551 亿（三季报读数基数）; as-of FY2023 / FY2024 年报分季度表
    'nr_fy24': 1.1307e8,  # FY2024 扣非归母（FY2026 年报读数基数；含 2024 坏账 1.85 亿，信用减值属经常性）; as-of FY2024 年报 113,070,619.64
    'nr_q4_25': 0.3360e8,  # 4Q2025 扣非; as-of FY2025 年报分季度表 33,604,318.09
    'nr_h1_26': 0.9341e8,  # H1 2026 扣非; as-of 2026 半年报 93,412,781.70
    'ni_group_fy25': 3.183e8,  # 归母净利 FY2025（共识隐含增速起点，A10）; as-of FY2025 年报 318,295,031.33
    'ni_ttm_2q26': 2.5712e8,  # 最近四季归母 = 3Q25 1.080 + 4Q25 0.488 + 1Q26 0.403 + 2Q26 0.601 亿; as-of Longbridge 季度利润表，2026-06-30
    'ni_ttm_2q24': 2.2939e8,  # 两年前滚动四季归母 = 3Q23 0.342 + 4Q23 0.218 + 1Q24 0.867 + 2Q24 0.867 亿; as-of Longbridge 季度利润表，2024-06-30
    'ni_solar_fy25r': 1.37e8,  # 光伏腿 FY2025 经常性净利 = 评估报告 1.67 − Alpha Steel 处置收益 0.30; as-of 评估报告 2026-04-29
    'disposal_fy25': 0.30e8,  # Alpha Steel 处置收益（2025-10，在最近四季内；从公司归母里剔除）; as-of FY2025 年报 / 评估报告
    'ni_solar_l': 0.54e8,  # L 档光伏分子：H1 2026 年化（子公司表拼 0.27 × 2；100% 持股即归母，A4）; as-of 2026 半年报
    'cons_fy27_m': 6.47e8,  # 卖方共识 FY2027E 归母均值（只作中性带 FY+1 读数）; as-of 同花顺 2 家，2026-10-03
    'cons_fy28_l': 7.46e8,  # 卖方共识 FY2028E 低端（触发校验）; as-of 国金 2026-08-30
    'cons_fy28_m': 8.19e8,  # 卖方共识 FY2028E 均值（触发与升级门槛）; as-of 同花顺 2 家，2026-10-03
    'cons_fy28_h': 8.92e8,  # 卖方共识 FY2028E 高端 = **H 分子**（A10）; as-of 国海 2026-05-24（同花顺记 05-23）
    'g2': 0.06,  # 连接器单调区档（H）的永续增长：同篮同域同业反解截顶；cap = min(6%, r − 4%) = 6%（A13）；L / M 档用派息政策 g，由 eval 按域生成; as-of 同业反解 2026-09-14
    'g2_solar': 0.0,  # 光伏腿永续增长：D 桶、项目单列（A22）; as-of 2026-10-04
    'r_conn': 0.10,  # 篮 4 常规经营 10%：连接器腿——器件制造，盈利不是商品价函数（贵金属 / 铜 / 塑胶是成本项、可价格传导）；未达单押门槛（华为系占连接器 ≤ 25%、前两大 ≤ 45.6%）；初分「周期商品 / 小盘」被推翻（A17）；值 = `gordon.BASKET_R[4]`; as-of 2026-10-04
    'r_solar': 0.10,  # 篮 4 常规经营 10%：光伏腿——跟踪支架零部件按订单加工、客户锁定原材料价、毛利率 10.7–15.2%，不是商品价函数；第一大客户占支架 41.5%、前两大 ≤ 60.5%，未达单押门槛（A17）；值 = `gordon.BASKET_R[4]`；折现同用此值; as-of 2026-10-04
    'r_ctl': 0.13,  # 对照：被推翻的初分档「周期商品 / 小盘 13%」（A17）；只出 Outputs 对照带，不进锚点、不进 zone; as-of 2026-10-04
    'years_to_fy28': 2.5,  # 外推年数：最近报告期末 2026-06-30 → FY2028 末; as-of 2026-10-04
    'tau': 1.5,  # 时点对齐 τ = 估值基准日 2026-06-30 → 分子年初 2028-01-01（18 个月）；三档 ÷ (1+r)^τ，窗口可分配利润 ÷ (1+r)^(τ/2)；项目值已是今天的值，不动（A23）; as-of 2026-06-30
    'y1': 2028,  # 高回报期止点 Y₁ = 可见年末 FY2028（默认）（A24）; as-of 2026-10-16
    'y2': 2032,  # 回落到稳态 Y₂ = Y₁ + 4（连接器判中门槛，A24）; as-of 2026-10-16
    'ronic_ss_cn': 0.156,  # 国内成熟连接器同业投入资本口径 FY2016–25 均值中位：航天电器 13.4%、合兴股份 17.8%（近 5 年收入 +6.6% / +9.2%/年）（A24）; as-of 2026-10-19
    'ronic_ss_te': 0.148,  # 对照：泰科（TE Connectivity）投入资本口径 FY2016–25 均值（报表税率；税率统一 20% 时 13.1%）；旧账面口径 18.6% 撤（A24）; as-of 2026-10-19
    'ronic_ss_floor': 0.18,  # 对照：生意模式兜底轻资产组装（连接器）18%（同业层非空，不用）; as-of 2026-10-16
    'ronic_ss': 0.156,  # 连接器稳态回报（三档）= 按序取：自身周期不可用 → 同业层 = 国内成熟同业 15.6%（竞争场：H 世界押国产超节点、客户集中在华为体系；用户 2026-10-19 认可）（A24）; as-of 2026-10-19
    'cons_fy26_m': 4.4156e8,  # 卖方共识 FY2026E 归母均值（EPS 2.2775 × 股本；东方财富）；只用于 H 档窗口利润（A23）; as-of 2026-10-16
    'ni_group_h1_26': 1.0036e8,  # 2026H1 归母净利（半年报）；H 档窗口利润扣已入账部分（A23）; as-of 2026-06-30
    'payout_fy25': 0.305,  # FY2025 实付派息率 = 每 10 股 5 元 × 1.9388 亿股 ÷ 归母 3.183 亿（病态区派息政策 g、股息尺、对账 ③；5 年平均 19% 作敏感，A13）; as-of FY2025 年报利润分配预案
    'proj_k_spent': 2.2046e8,  # 乐清光伏支架核心部件基地：截至 FY2025 已投募集资金（未投资本 = 预算 − 已投，A22）; as-of FY2025 年报募集资金使用表 22,045.95 万元
    'proj_k_total': 3.7371e8,  # 该项目承诺投资总额; as-of FY2025 年报 37,370.78 万元
    'proj_years_to_cod': 0.25,  # 估值日 → 达预定可使用状态（2026-12-01，2026-02-09 延期）; as-of 2026-10-04
    'k_l': 0,  # L 档视同派出打折：0——模型派息 = 实付（派息政策 g），无视同派出（A22）; as-of 2026-10-04
    'k_m': 0,  # M 档：0——股息尺不给超额留存任何 credit，无视同派出（A22）; as-of 2026-10-04
    'k_h': 0,  # H 档：0——原 0.3 乘在 H 档连接器整个经营价值上，是用错了对象（valuation-rules「经营价值与超额现金」④：经营价值的再投资回报已在回报率里，多留部分落在现金上），2026-10-16 框架纠正去掉；多留部分只披露（A22）; as-of 2026-10-16
    'm_prev': 11.00,  # 上一版 M（2026-10-04 v6，对账门 ①）; as-of 2026-10-16
    'bps': 14.56,  # 每股净资产 = equity_total ÷ shares（对账门 ⑥）; as-of 2026-06-30
    'pb_own_min': 2.46,  # 自身 3 年 PB 低点（对账门 ⑥）; as-of Longbridge valuation --history pb，2024-04-22
    'roe_peer_lo': 0.1179,  # 同业 FY2028E ROE 低：中航光电（对账门 ⑤）; as-of 同花顺 002179，2026-10-03
    'roe_peer_med': 0.218,  # 同业 FY2028E ROE 中位：立讯精密（5 家：中航 11.8 / 电连 14.8 / 立讯 21.8 / 瑞可达 25.7 / 华丰 35.3%）; as-of 同花顺 002475，2026-10-03
    'roe_peer_hi': 0.3526,  # 同业 FY2028E ROE 高：华丰科技（对账门 ⑤）; as-of 同花顺 688629，2026-10-03
    'ttm_eps': 1.33,  # 最近四季 EPS（快照；中性带读数用）; as-of 2.571 亿 ÷ 股本
    'band_pe_min': 27.59,  # 同等盈利周（TTM EPS 1.16–1.48）最低 PE（③ 带下沿，A12）; as-of Longbridge valuation --history pe，2024-09-16
    'band_eps': 1.182,  # 带下沿那周的 TTM EPS（2Q2024 滚动四季 2.294 亿 ÷ 1.9405 亿股；步 1c 扣项目用）; as-of Longbridge 季度利润表
    'band_fwd_growth': 0.298,  # 带下沿月份的点时预期增速：东方财富证券 FY2025E 4.83 → FY2026E 6.27 亿（③ 步 1b，A12）; as-of 东方财富证券 2024-09-12
    'equity_conn': 1.5383e9,  # 连接器腿权益起点 = equity_total − equity_solar（派生；含商誉 2.85 亿）; as-of eval 复算
    'rev_conn_ttm': 2.893556e9,  # 连接器最近四季收入 = FY2025 + H1'26 − H1'25（派生）; as-of eval 复算
    'rev_solar_ttm': 2.958344e9,  # 光伏最近四季收入（派生）; as-of eval 复算
    'g_conn': 0.1728,  # 连接器近 2 年滚动收入年复合 = (最近四季 ÷ 两年前四季)^0.5 − 1（派生）; as-of eval 复算
    'g_solar': -0.1058,  # 光伏近 2 年滚动收入年复合（派生）; as-of eval 复算
    'g_own_profit': 0.0587,  # 公司近 2 年滚动归母年复合（派生；薄覆盖触发分母）; as-of eval 复算
    'g_own_recurring': 0.0435,  # 公司近 2 年滚动扣非年复合（派生；升级门槛）; as-of eval 复算
    'ni_solar_ttm': 1.0373e8,  # 光伏最近四季归母（派生，A18）; as-of eval 复算
    'ni_conn_ttm': 1.2339e8,  # 连接器最近四季归母（派生，A18）; as-of eval 复算
    'ni_conn_l': 1.3363e8,  # L 连接器（派生）; as-of eval 复算
    'ni_conn_m': 1.8381e8,  # M 连接器（派生）; as-of eval 复算
    'ni_conn_h': 8.1356e8,  # H 连接器 = cons_fy28_h − ni_solar_m（派生）; as-of eval 复算
    'ni_solar_m': 0.7844e8,  # M / H 光伏（派生）; as-of eval 复算
    'n_conn': 2.2354e8,  # 连接器尚未入账的 M 路径利润 = 2H26 + FY2027（派生；三档共用）; as-of eval 复算
    'roe_conn_l': 0.0869,  # 连接器 L 档 ROE（2028 年初账面，按窗口留存率 b 滚动，派生）; as-of eval 复算
    'roe_conn_m': 0.1043,  # 连接器 M 档 ROE（派生）; as-of eval 复算
    'roe_conn_h': 0.4618,  # 连接器 H 档 ROE（派生）; as-of eval 复算
    'conn_fy26_h': 3.4347e8,  # H 档连接器 FY2026 = `cons_fy26_m` − 光伏 M 路径 FY2026（最近四季 × (1 + g_solar)^0.5）（派生；窗口段增速起点，A23）; as-of eval 复算
    'g_win_h': 0.5391,  # H 档连接器窗口段增速 = (`ni_conn_h` ÷ `conn_fy26_h`)^(1/2) − 1：共识路径 FY2026 → FY2028 年化（派生；L 段增速 0、M 段增速 = `g_conn`，A23）; as-of eval 复算
    'v_proj': 1.4487e8,  # 乐清项目单列价值 = (预算 × ROE_proj ÷ r − 未投资本) 折到今日（派生，A22）; as-of eval 复算
}

TOL = 0.05
DERIVED_TOL = 5e-4
AMT_TOL = 1e5
GATE_BAND = 0.20
THIN_RATIO = 2.0
ROE_NEAR_R = 0.03
CLIP_TOL = 0.02          # dividend-ruler threshold on the clipped amount
DIV_PAYOUT = 0.40        # ... or on the paid payout
BAND_EPS_BAND = 0.12
DISTORT_G = 0.10         # ③ step 1b: band-month expected growth − model >= 10pp/yr
TIERS = ("L", "M", "H")

REQUIRED = [
    "shares", "equity_total", "equity_solar",
    "rev_conn_fy23", "rev_conn_fy25", "rev_conn_h1_23", "rev_conn_h1_24", "rev_conn_h1_25", "rev_conn_h1_26",
    "rev_solar_fy23", "rev_solar_fy25", "rev_solar_h1_23", "rev_solar_h1_24", "rev_solar_h1_25", "rev_solar_h1_26",
    "gm_solar_fy25", "gm_solar_h1_25", "ni_solar_h1_26",
    "nr_ttm_2q26", "nr_ttm_2q24", "nr_ttm_3q24", "nr_fy24", "nr_q4_25", "nr_h1_26",
    "ni_group_fy25", "ni_ttm_2q26", "ni_ttm_2q24", "ni_solar_fy25r", "disposal_fy25", "ni_solar_l",
    "cons_fy27_m", "cons_fy28_l", "cons_fy28_m", "cons_fy28_h",
    "g2", "g2_solar", "r_conn", "r_solar", "r_ctl", "years_to_fy28", "tau", "payout_fy25",
    "y1", "y2", "ronic_ss", "ronic_ss_cn", "ronic_ss_te", "ronic_ss_floor", "cons_fy26_m", "ni_group_h1_26",
    "proj_k_spent", "proj_k_total", "proj_years_to_cod", "k_l", "k_m", "k_h",
    "m_prev", "bps", "pb_own_min", "roe_peer_lo", "roe_peer_med", "roe_peer_hi", "ttm_eps",
    "band_pe_min", "band_eps", "band_fwd_growth",
    # derived, recomputed below
    "equity_conn", "rev_conn_ttm", "rev_solar_ttm", "g_conn", "g_solar", "g_own_profit", "g_own_recurring",
    "ni_solar_ttm", "ni_conn_ttm", "ni_conn_l", "ni_conn_m", "ni_conn_h", "ni_solar_m", "n_conn",
    "roe_conn_l", "roe_conn_m", "roe_conn_h", "v_proj", "conn_fy26_h", "g_win_h",
]


def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段) at the start of t0 per unit of t0
    earnings: ROE through y1, linear to min(roe, r_ss) by y2, perpetual after."""
    if r - g <= 0:
        raise ValueError("r <= g")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g / ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * min(1.0, 1.0 - g / ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def domain(roe: float, r: float) -> str:
    if roe - r >= ROE_NEAR_R:
        return "单调区"
    if roe - r <= -ROE_NEAR_R:
        return "峰形区"
    return "病态区"



def evaluate(inp):
    errors = check_missing(inp, list(INPUTS))
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('y1', 'y2'))
    if any(not math.isfinite(inp[k]) for k in INPUTS):
        raise ValueError('all model inputs must be finite')
    baskets = {'r_conn': 4, 'r_solar': 4}
    def derived(key: str, value: float, tol: float = DERIVED_TOL) -> None:
        if abs(value - inp[key]) > tol:
            errors.append(f"{key}: stated {inp[key]:.6g} vs recomputed {value:.6g}")

    # ---- baskets (A17) ----
    for key in ("r_conn", "r_solar"):
        if key not in baskets:
            errors.append(f"{key}: Inputs source cell names no 篮 N (A17)")
        errors += check_r(inp[key], key, baskets.get(key))
    if "r_ctl" in baskets:
        errors.append("r_ctl is a control reading — its source cell must not name a 篮 N")
    errors += check_r(inp["r_ctl"], "r_ctl")
    r = inp["r_conn"]
    if abs(r - inp["r_solar"]) > 1e-12:
        errors.append("legs must share r (discounting uses one rate)")
    cap = g_cap(r)
    errors += check_g_cap(inp["g2"], r, "g2") + check_g_cap(inp["g2_solar"], r, "g2_solar")
    if any(k.startswith("p_") for k in inp):
        errors.append("Inputs carry probability fields — no option, no p")
    pay = inp["payout_fy25"]
    sh = inp["shares"]

    # ---- thin-coverage trigger (A10): profit vs profit, attributable ----
    g_own = (inp["ni_ttm_2q26"] / inp["ni_ttm_2q24"]) ** 0.5 - 1.0
    derived("g_own_profit", g_own)
    cons_cagr = {k: (inp[f"cons_fy28_{k}"] / inp["ni_group_fy25"]) ** (1 / 3) - 1 for k in ("l", "m", "h")}
    ratio = {k: (v / g_own if g_own > 0 else float("inf")) for k, v in cons_cagr.items()}
    if not ratio["l"] >= THIN_RATIO:
        errors.append(f"thin-coverage trigger no longer holds ({ratio['l']:.2f}x < {THIN_RATIO}) — consensus goes back into M")
    errors += ladder("FY2028 consensus", inp["cons_fy28_l"], inp["cons_fy28_m"], inp["cons_fy28_h"])
    upgrade_bar = cons_cagr["m"] / 2
    # Upgrade gate on recurring (扣非) profit (rule amended 2026-10-04): same window.
    g_rec = (inp["nr_ttm_2q26"] / inp["nr_ttm_2q24"]) ** 0.5 - 1.0
    derived("g_own_recurring", g_rec)
    upgraded = g_rec >= upgrade_bar
    if upgraded:
        errors.append(f"upgrade gate met: recurring profit CAGR {g_rec:.1%} >= {upgrade_bar:.1%} — consensus mean back into M")
    need_q3 = inp["nr_ttm_3q24"] * (1 + upgrade_bar) ** 2 - inp["nr_q4_25"] - inp["nr_h1_26"]
    need_fy26 = inp["nr_fy24"] * (1 + upgrade_bar) ** 2

    # ---- revenue windows to the latest period (TTM 2Q24 -> TTM 2Q26) ----
    def ttm(leg: str, fy: str, old: str, new: str) -> float:
        return inp[f"rev_{leg}_{fy}"] + inp[f"rev_{leg}_h1_{new}"] - inp[f"rev_{leg}_h1_{old}"]

    rc_now, rc_then = ttm("conn", "fy25", "25", "26"), ttm("conn", "fy23", "23", "24")
    rs_now, rs_then = ttm("solar", "fy25", "25", "26"), ttm("solar", "fy23", "23", "24")
    derived("rev_conn_ttm", rc_now, AMT_TOL)
    derived("rev_solar_ttm", rs_now, AMT_TOL)
    g_c = (rc_now / rc_then) ** 0.5 - 1
    g_s = (rs_now / rs_then) ** 0.5 - 1
    derived("g_conn", g_c)
    derived("g_solar", g_s)

    # ---- TTM attributable leg profits (A18 / A7) ----
    conv = inp["ni_solar_fy25r"] / (inp["rev_solar_fy25"] * inp["gm_solar_fy25"])
    gp_h25 = inp["rev_solar_h1_25"] * inp["gm_solar_h1_25"]
    s_ttm = inp["ni_solar_fy25r"] + inp["ni_solar_h1_26"] - conv * gp_h25
    c_ttm = inp["ni_ttm_2q26"] - inp["disposal_fy25"] - s_ttm
    derived("ni_solar_ttm", s_ttm, AMT_TOL)
    derived("ni_conn_ttm", c_ttm, AMT_TOL)
    m_c, m_s = c_ttm / rc_now, s_ttm / rs_now

    # ---- numerators (A14) ----
    n = inp["years_to_fy28"]
    conn = {"L": rc_now * (1 + g_c) ** (n - 2) * m_c, "M": rc_now * (1 + g_c) ** n * m_c}
    solar_m = rs_now * (1 + g_s) ** n * m_s
    solar = {"L": inp["ni_solar_l"], "M": solar_m, "H": solar_m}
    conn["H"] = inp["cons_fy28_h"] - solar["H"]
    for key, v in (("ni_conn_l", conn["L"]), ("ni_conn_m", conn["M"]), ("ni_conn_h", conn["H"]), ("ni_solar_m", solar_m)):
        derived(key, v, AMT_TOL)
    group = {t: conn[t] + solar[t] for t in TIERS}
    errors += ladder("connector numerator", conn["L"], conn["M"], conn["H"])
    errors += ladder("company numerator", group["L"], group["M"], group["H"])
    if not solar["L"] < solar["M"]:
        errors.append("solar L must sit below solar M")
    if not group["M"] < inp["cons_fy28_l"]:
        errors.append("thin coverage: M must sit below the consensus low")

    # ---- connector book and multiple form per tier (A13 / A22) ----
    eq_c0 = inp["equity_total"] - inp["equity_solar"]
    derived("equity_conn", eq_c0, AMT_TOL)
    c27 = rc_now * (1 + g_c) ** (n - 1) * m_c
    n_conn = 0.5 * conn["L"] + c27          # 2H26 + FY2027 on the M path
    derived("n_conn", n_conn, AMT_TOL)

    y1, y2, r_ss = int(inp["y1"]), int(inp["y2"]), inp["ronic_ss"]
    if not (y1 == 2028 and y2 == y1 + 4):
        errors.append("Y1 must be the visible-year end 2028 and Y2 = Y1 + 4 (medium entry barrier)")
    # Ordered pick (2026-10-19): own cycle unusable -> the domestic mature-peer layer is non-empty,
    # take it; TE (global, invested-capital basis) and the floor are comparisons only.
    if abs(r_ss - inp["ronic_ss_cn"]) > 5e-4:
        errors.append(f"ronic_ss {r_ss} != domestic mature-peer median {inp['ronic_ss_cn']} (ordered pick)")
    if any(inp[f"k_{x}"] != 0.0 for x in ("l", "m", "h")):
        errors.append("k must be 0: no named transaction for a k to sit on (k on the whole value removed 2026-10-16)")

    def conn_tier(c: float, r_: float, peer_g: float, gw: float) -> tuple[float, float, float, str, float, float | None, float | None]:
        """Return growth, ROE, PE, method, window retention and method parameters.

        The book rolls n_conn at the window retention
        b = g_win/ROE cut to [0, 1] -- the segment's own growth, the same b as the window profit
        (valuation-rules ③ 时点对齐; 2026-10-18 窗口留存口径改正: was the multiple's perpetual g).
        The multiple's g (peer g2 / payout-policy g) is then read at that ROE."""
        bps = eq_c0
        for _ in range(500):
            nxt = eq_c0 + min(1.0, max(0.0, gw * bps / c)) * n_conn
            if abs(nxt - bps) < 1e-3:
                break
            bps = nxt
        roe = c / bps
        bw = min(1.0, max(0.0, gw / roe))
        if roe - r_ >= ROE_NEAR_R:
            g, form = peer_g, "peer_return_fade"
            policy_growth, fade_target = None, r_ss
            pe = path_pe(g, roe, r_, 2028, y1, y2, r_ss)
        else:
            g_raw = (1.0 - pay) * roe
            g = min(g_raw, g_cap(r_))
            policy_growth, fade_target = g_raw, None
            if g_raw > g_cap(r_) and (pay >= DIV_PAYOUT or g_raw - g_cap(r_) <= CLIP_TOL):
                pe, form = capped_payout_pe(g_raw, roe, r_, pay), "policy_capped_payout"
            else:
                pe, form = perpetual_pe(g, roe, r_), "policy_perpetual"
        return g, roe, pe, form, bw, policy_growth, fade_target

    # ---- project value (D bucket, A22) ----
    roe_proj = s_ttm / inp["equity_solar"]

    def project(r_: float) -> float:
        # Capacity item: completed value less the unspent capital, both at the 2026 spend / COD point, to today.
        k_rem = inp["proj_k_total"] - inp["proj_k_spent"]
        return (inp["proj_k_total"] * roe_proj / r_ - k_rem) * (1 + r_) ** -inp["proj_years_to_cod"]

    v_proj = project(r)
    derived("v_proj", v_proj, AMT_TOL)
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    tau = inp["tau"]

    # Window distributable profit (③ 时点对齐), 2H26 + FY2027 unbooked, on each tier's numerator basis.
    solar_w = 0.5 * s_ttm * (1 + g_s) ** 0.5 + s_ttm * (1 + g_s) ** 1.5      # solar M path (b = 0: g = 0)
    cons_w = inp["cons_fy26_m"] - inp["ni_group_h1_26"] + inp["cons_fy27_m"]  # H: consensus path
    conn_unb = {"L": n_conn, "M": n_conn, "H": cons_w - solar_w}
    # Window segment growth per tier = the connector leg's own path from FY2026 to the FY2028 numerator,
    # annualised: L = the M path stopped at FY2026 -> flat, 0; M = the trend path's g_c (the eval's
    # carry growth); H = the consensus path (FY2026E mean less the solar M path) -> the H numerator.
    solar_26 = s_ttm * (1 + g_s) ** 0.5
    conn26_h = inp["cons_fy26_m"] - solar_26
    derived("conn_fy26_h", conn26_h, AMT_TOL)

    def g_win(cx: dict) -> dict:
        return {"L": 0.0, "M": g_c, "H": (cx["H"] / conn26_h) ** 0.5 - 1.0}

    derived("g_win_h", g_win(conn)["H"])

    def deck(r_: float, cx=conn, sx=solar, peer_g=None, solar_branch="D"):
        peer_g = inp["g2"] if peer_g is None else peer_g
        gws = g_win(cx)
        rows = {}
        for t in TIERS:
            g, roe, pe_a, form, bw, policy_growth, fade_target = conn_tier(cx[t], r_, peer_g, gws[t])
            roe_s = sx[t] / inp["equity_solar"]
            if solar_branch == "D":
                pe_b = perpetual_pe(inp["g2_solar"], roe_s, r_)
            else:  # E bucket alternative: retaining branch at the payout-policy g
                pe_b = perpetual_pe(min((1 - pay) * roe_s, g_cap(r_)), roe_s, r_)
            vp = project(r_) if solar_branch == "D" else 0.0
            win = conn_unb[t] * (1 - bw) + solar_w
            val = ((cx[t] * pe_a * (1 - k[t]) + sx[t] * pe_b) * (1 + r_) ** -tau
                   + win * (1 + r_) ** -(tau / 2) + vp)
            rows[t] = dict(px=val / sh, g=g, roe=roe, pe_a=pe_a, pe_b=pe_b, form=form, roe_s=roe_s, win=win,
                           gw=gws[t], bw=bw, policy_growth_rate=policy_growth, fade_target_return=fade_target)
        return rows

    base = deck(r)
    for t, key in zip(TIERS, ("roe_conn_l", "roe_conn_m", "roe_conn_h")):
        derived(key, base[t]["roe"])
    L, M, H = (base[t]["px"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)
    # The model's payout above the paid payout (H) is the 「多留部分」: no k any more (valuation-rules ④,
    # 2026-10-15/16: a k on the whole operating value is the wrong object); disclosed below.

    disc = (1 + r) ** tau
    disc_w = (1 + r) ** (tau / 2)
    pe_c = {t: (base[t]["px"] * sh - v_proj - base[t]["win"] / disc_w) * disc / group[t] for t in TIERS}
    dec = decompose((L, M, H), (pe_c["L"], pe_c["M"], pe_c["H"]))
    flat = tuple((conn[t] * base["M"]["pe_a"] * (1 - k[t]) + solar[t] * base[t]["pe_b"]) / disc / sh
                 + base[t]["win"] / disc_w / sh + v_proj / sh for t in TIERS)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    ctl = deck(inp["r_ctl"])
    # The two peer-growth cases are 5% and 3%; the solar alternative uses
    # retained earnings without the project; the 0.3 discount is an old control.
    # Steady-return controls are the fallback, TE's reported-tax return and
    # TE's tax-normalized return. Their old rounded names could collide.
    sens = {
        "peer_growth_5pct": ({"peer_growth_rate": 0.05}, deck(r, peer_g=0.05)),
        "peer_growth_3pct": ({"peer_growth_rate": 0.03}, deck(r, peer_g=0.03)),
        "solar_retained_no_project": ({"solar_method": "retained_no_project"}, deck(r, solar_branch="E")),
    }
    k_save = k["H"]
    k["H"] = 0.3
    sens["high_discount_30pct"] = ({"high_value_discount": 0.3}, deck(r))
    k["H"] = k_save
    rss_save = r_ss
    for name, rs_alt in (("steady_floor", inp["ronic_ss_floor"]),
                         ("steady_peer_te", inp["ronic_ss_te"]), ("steady_tax_normalized", 0.131)):
        r_ss = rs_alt
        sens[name] = ({"steady_return": rs_alt}, deck(r))
    r_ss = rss_save
    # Solar H1'26 by the gross-profit conversion instead of the subsidiary-table sum (the v5 basis).
    s_alt = inp["ni_solar_fy25r"] + conv * inp["rev_solar_h1_26"] * 0.1099 - conv * gp_h25
    c_alt = inp["ni_ttm_2q26"] - inp["disposal_fy25"] - s_alt
    cx_alt = {"L": rc_now * (1 + g_c) ** (n - 2) * c_alt / rc_now, "M": rc_now * (1 + g_c) ** n * c_alt / rc_now}
    sm_alt = rs_now * (1 + g_s) ** n * s_alt / rs_now
    cx_alt["H"] = inp["cons_fy28_h"] - sm_alt
    # The alternate H1 2026 solar profit uses 10.99% gross margin instead of
    # the subsidiary-table sum; its parameter is retained as a numeric field.
    sens["solar_gross_profit_conversion"] = (
        {"gross_margin": 0.1099}, deck(r, cx_alt, {"L": inp["ni_solar_l"], "M": sm_alt, "H": sm_alt})
    )

    # H-tier 视同派出 line (E bucket, single-stage perpetual): excess retention capitalised.
    b_h = base["H"]["g"] / base["H"]["roe"]
    line_h = (1 - pay - b_h) * conn["H"] / (r - base["H"]["g"]) / disc / sh

    # ---- ③ band (A12): same-earnings weeks exist; step 1c and 1b ----
    eps_m = group["M"] / sh
    pe_m_anchor = M / eps_m
    band_floor_1c = (inp["band_pe_min"] * inp["band_eps"] - v_proj / sh) / inp["band_eps"]
    model_growth = (group["M"] / (inp["ni_ttm_2q26"])) ** (1 / n) - 1
    distorted = inp["band_fwd_growth"] - model_growth >= DISTORT_G
    clean_band_outside = pe_m_anchor < band_floor_1c and not distorted

    # ---- correction reconciliation gate ----
    peer_pe = {kk: perpetual_pe(inp["g2"], inp[kk], r) for kk in ("roe_peer_lo", "roe_peer_med", "roe_peer_hi")}
    # These IDs correspond to the prior committed midpoint, E/r, same-formula
    # DDM, historical band floor, peer median and own PB floor, respectively.
    coords = {
        "previous_midpoint": inp["m_prev"],
        "earnings_over_rate": group["M"] / r / sh,
        "ddm_same_formula": pay * group["M"] / (r - base["M"]["g"]) / sh,
        "same_earnings_floor": inp["band_pe_min"] * eps_m,
        "peer_median": peer_pe["roe_peer_med"] * eps_m / disc,
        "book_value_floor": inp["bps"] * inp["pb_own_min"],
    }
    devs = {kk: M / v - 1.0 for kk, v in coords.items()}
    # Same-formula cells do not count (2026-10-04): the M connector leg is the dividend ruler at this payout.
    same_formula = {"ddm_same_formula"}
    inside = [kk for kk, d in devs.items() if abs(d) <= GATE_BAND and kk not in same_formula]

    if errors:
        raise ValueError('; '.join(errors))
    result = {
        'ticker': '002897.SZ', 'currency': 'CNY',
        'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-29', 'historical_framework_as_of': '2026-10-29',
        'anchors': dict(zip('LMH', (L, M, H))), 'cut_points': {'A': A, 'B': B},
        'candidate': None, 'option': None,
        'segments': {
            'connector': {'values': {t: conn[t] * base[t]['pe_a'] * (1-k[t]) / disc / sh for t in TIERS}},
            'solar': {'values': {t: solar[t] * base[t]['pe_b'] / disc / sh for t in TIERS}},
            'window': {'values': {t: base[t]['win'] / disc_w / sh for t in TIERS}},
            'existing_project': {'values': dict.fromkeys('LMH', v_proj / sh)},
        },
        'key_parameters': {
            'connector': {t: {'method': base[t]['form'], 'discount_rate': r, 'growth_rate': base[t]['g'],
                              'forward_return': base[t]['roe'], 'multiple': base[t]['pe_a'],
                              'policy_growth_rate': base[t]['policy_growth_rate'],
                              'fade_target_return': base[t]['fade_target_return'],
                              # The capped payout helper uses ROE only within its 1e-9 cap tolerance;
                              # otherwise the dividend multiple does not use any steady return.
                              'steady_return': (min(base[t]['roe'], r_ss) if base[t]['form'] == 'peer_return_fade'
                                                else None if base[t]['form'] == 'policy_capped_payout'
                                                and base[t]['policy_growth_rate'] > cap + 1e-9 else base[t]['roe'])}
                          for t in TIERS},
            'solar': {t: {'discount_rate': r, 'growth_rate': inp['g2_solar'], 'forward_return': base[t]['roe_s'],
                           'multiple': base[t]['pe_b'], 'steady_return': None} for t in TIERS},
        },
        'operating': {'thin_growth': g_own, 'consensus_growth': cons_cagr, 'thin_ratio': ratio,
                      'upgrade_bar': upgrade_bar, 'recurring_growth': g_rec, 'upgrade_met': upgraded,
                      'needed_q3': need_q3, 'needed_fy26': need_fy26, 'connector_growth': g_c, 'solar_growth': g_s,
                      'connector': conn, 'solar': solar, 'group': group, 'rows': base, 'project_value': v_proj,
                      'project_return': roe_proj, 'matched_band_distorted': distorted, 'band_floor_1c': band_floor_1c,
                      'coordinates': coords, 'coordinate_deviations': devs, 'independent_coordinates_inside': inside,
                      'extra_retention_h': line_h, 'decomposition': dec},
        'sensitivity': {'original': {name: {'parameters': params, 'anchors': {t: row[t]['px'] for t in TIERS}}
                                     for name, (params, row) in sens.items()},
                        'basket_6': {t: ctl[t]['px'] for t in TIERS}, 'flat_multiple': dict(zip('LMH', flat))},
    }

    result['clean_band_outside'] = clean_band_outside
    result['independent_coordinates_missing'] = not bool(inside)
    return result


def calculate(context):
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'derived_tolerance': DERIVED_TOL, 'amount_tolerance': AMT_TOL,
         'reconciliation_band': GATE_BAND, 'thin_ratio': THIN_RATIO, 'roe_near_rate': ROE_NEAR_R,
         'clip_tolerance': CLIP_TOL, 'dividend_payout': DIV_PAYOUT,
         'earnings_band': BAND_EPS_BAND, 'distortion_growth': DISTORT_G}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'CNY_PER_SHARE'}
    for segment in result['segments'].values():
        segment['unit'] = 'CNY_PER_SHARE'
    # The calculation stores one parameter record per tier; the confirmation
    # view consumes one unit-bearing set of tiers per parameter.
    for leg in ('connector', 'solar'):
        parameters = result['key_parameters'][leg]
        for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
            parameters[name] = {'unit': 'RATIO', 'values': {tier: parameters[tier][name] for tier in TIERS}}
    result['review_flags'] = ['historical_q3_weakened_high_forecast',
                              'historical_segment_profit_inference_and_capital_unverified',
                              'historical_high_forecast_single_source']
    if result['clean_band_outside']:
        result['review_flags'].append('historical_multiple_below_clean_reference')
    if result['independent_coordinates_missing']:
        result['review_flags'].append('historical_reconciliation_requires_review')
    return result
