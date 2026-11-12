"""Historical Huaneng base; 2026 Q3 invalidated the old middle earnings."""
from __future__ import annotations
import math
from lib.gordon import perpetual_pe
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'zones', 'partial_basis'),
                'axes': {'coal': 'coal_price', 'southbound': 'southbound_repricing'}}
BASELINE_LOCAL = '629fb3b5e24f80df00a73327c046fbcfc849d6ce9d01f640a3718b3d6d70b021'
TIERS = ('l', 'm', 'h')
BASE_FIELDS = ('eps_l', 'eps_m', 'eps_h', 'r_perp', 'g2_m', 'shares', 'equity', 'pb_lo', 'bps', 'hkdcny')
INPUTS = {
    'hkdcny': 0.8552,  # HKD→CNY 汇率；yfinance `HKDCNY=X` 2026-09-11
    'shares': 156.98093359,  # 总股本**亿股**；Longbridge static 2026-06-30
    'bps': 4.2054,  # 每股净资产 CNY（普通股口径）= (归母权益 1,434.66 − 永续债 774.49) ÷ shares；2026 三季报合并资产负债表 2026-09-30
    'equity': 660.17,  # 归属普通股股东权益**亿元** = bps × shares（永续债已在其他权益工具中剔除）；用于各档前瞻 ROE 2026-09-30
    'eps_l': 0.35,  # **L** = FY2023 实测普通股基本 EPS（CNY）；世界 = 煤价梯 L 档 326.43 元/MWh（A4） FY2023
    'eps_m': 0.562,  # **M = 前瞻共识中枢** = FY2026 共识均值（Longbridge 11 家，普通股口径读）；世界 = 混合燃料 ≈ 轴 M 282 + 电价 463 + 今天的资产基数（A5 / A19 / A22）；须 = `cons_fy26_mean` 2026-08-19
    'eps_h': 0.74,  # **H** = FY2025 实测普通股基本 EPS（煤价梯 H 档 266.88，有利端，历史最高）；须 ≤ `cons_fy27_hi`（A5） FY2025
    'eps_fy23': 0.35,  # FY2023 年报基本 EPS（普通股口径）；煤价梯年份表（A19） FY2023
    'eps_fy24': 0.4594,  # FY2024 年报基本 EPS；v5 曾作中枢，现只作坐标（A5 / A22） FY2024
    'eps_fy25': 0.74,  # FY2025 年报基本 EPS FY2025
    'eps_ttm': 0.32,  # 当期 TTM 普通股基本 EPS = FY2025 0.74 − 2025 前三季度 0.81 + 2026 前三季度 0.39（三季报基本 EPS，舍入 ±0.005）；「当期 ÷ 中枢」的分子（A5）；**不入底牌** 2026-09-30
    'eps_9m26': 0.39,  # 2026 前三季度基本 EPS（普通股口径；Q3 单季 0.04，同比 −87.1%）；三季报（A5 / A22）；**坐标，不入公式** 2026-09-30
    'eps_fy26_q': 0.21,  # FY2026 = 前三季度实测 0.39 + Q4 共识 −0.18（yfinance n=1）；旧值 0.48 里的「Q3 共识 0.31」实为 2025 Q3 实测值的重复，作废（A22）；**坐标，不入公式** 2026-10-28
    'cons_fy26_now': 0.46557,  # FY2026 共识均值重拉（yfinance 600011.SS n=1；Longbridge 共识接口当日返回空）；< 0.50 → A5 触发器已触发；**坐标，不入公式** 2026-10-28
    'cons_fy27_now': 0.48522,  # FY2027 共识均值重拉（yfinance 600011.SS n=1，7 日前 0.65761）；< `eps_m` → ②-b 在新共识上不过（A11）；**坐标，不入公式** 2026-10-28
    'fuel_fy19': 223.22,  # 境内火电厂售电单位燃料成本 元/MWh；2020 年报（A19 煤价梯） FY2019
    'fuel_fy20': 209.07,  # 同上；2020 年报 FY2020
    'fuel_fy21': 316.36,  # 同上（+51.32%）；2021 年报 FY2021
    'fuel_fy22': 372.56,  # 同上；2022 年报摘要（梯峰值） FY2022
    'fuel_fy23': 326.43,  # 同上（−12.38%）；2023 年报摘要 = 梯 L 档 FY2023
    'fuel_fy24': 300.31,  # 同上（−8.00%）；2024 年报 FY2024
    'fuel_fy25': 266.88,  # 同上（−11.13%）；2025 年报 = 梯 H 档 FY2025
    'fuel_mid': 287.83,  # 煤价梯 7 年实测均值（eval 复算，±0.05）；坐标（A19） FY2019–25
    'coal_fy2019': 588.0,  # 秦皇岛 5500 年均 元/吨；轴 §1 基准序列（eval 逐格对轴）（A19） FY2019
    'coal_fy2020': 577.0,  # 同上 FY2020
    'coal_fy2021': 1030.0,  # 同上 FY2021
    'coal_fy2022': 1268.0,  # 同上（尖峰年；电厂 `deep_discount` 压力坐标，不进 L） FY2022
    'coal_fy2023': 965.0,  # 同上 FY2023
    'coal_fy2024': 855.0,  # 同上 FY2024
    'coal_fy2025': 703.0,  # 同上 FY2025
    'fuel_lag_a': 78.865,  # 本票滞后传导线截距：`fuel_fy` = a + b × 当年煤价 + c × 上年煤价，FY2020–25 六年最小二乘（R² 0.978；FY2019 缺上年轴值不入拟合）；eval 重拟合校验（A19） FY2020–25
    'fuel_lag_b': 0.19947,  # 滞后线当年煤价系数（元/MWh 每 元/吨）（A19） FY2020–25
    'fuel_lag_c': 0.04574,  # 滞后线上年煤价系数——长协按上年煤价签，煤价下跌年实际成本在轴默认线之上、上涨年在其下（A19） FY2020–25
    'fuel_l': 315.5,  # 燃料档 L = 滞后线稳态 a + (b + c) × `coal_l`（元/MWh）；轴 §4a 具名修正（A19）；**不入公式** 2026-09-27
    'fuel_m': 282.4,  # 燃料档 M = 滞后线稳态 × `coal_m`；中枢煤价的互证基准、A20 桥的轴 M 坐标（A19）；**不入公式** 2026-09-27
    'fuel_h': 251.3,  # 燃料档 H = 滞后线稳态 × `coal_h`（A19）；**不入公式** 2026-09-27
    'qhd_fy25': 703.0,  # 秦皇岛 5500 大卡 2025 全年均价 元/吨（−18.4%）；Mysteel；**坐标，不入公式** FY2025
    'qhd_deck26': 800.0,  # 秦皇岛 5500 2026 全年预测簇中位（美银 800 / 汇丰 791 / 高盛 813–850）；经传导率 0.60 折算燃料成本 289 与 `fuel_m` 互证（A19）；**不入公式** 2026-09-08
    'lt_contract_mean': 704.0,  # 港口 5500 年度长协 2022–25 均价（722 / 714 / 701 / 680）；广发证券 2026-09-14；**坐标** 2022–2025
    'tariff_fy22': 509.92,  # 境内平均上网结算电价 元/MWh；2022 年报摘要 FY2022
    'tariff_fy23': 508.74,  # 同上；2023 年报摘要（L 世界） FY2023
    'tariff_fy24': 494.26,  # 同上；2024 年报（≈ 改革后均值 497.5） FY2024
    'tariff_fy25': 477.08,  # 同上；2025 年报（H 世界） FY2025
    'tariff_now': 463.02,  # 同上，2026H1（−4.58%；2025H1 485.27）；M 世界的电价、A20 压力坐标用；**不入底牌** 2026H1
    'coal_vol': 3.40159,  # FY2025 煤机上网电量**亿 MWh**（3,401.59 亿 kWh）；2025 年报电量电价表；只进 A20 线性桥 FY2025
    'pbt_fy23': 91.43,  # FY2023 境内六腿利润总额**亿元**（2024 年报板块表）；命名与六腿链坐标（A4） FY2023
    'pbt_fy24': 167.34,  # FY2024 境内六腿利润总额（2024 / 2025 年报）；六腿链坐标 FY2024
    'pbt_l': 115.91,  # **交叉带 L** 六腿利润总额**亿元** = 各腿 TTM 按 2026 前三季度实测同比倍数再走一期（生物质取 1.0）（A18）；**不进底牌** 构造
    'pbt_m': 153.47,  # **交叉带 M** = TTM 六腿 = FY2025 227.85 − 2025 前三季度 221.60 + 2026 前三季度 147.22（三季报板块利润表；A3 / A18）；**不进底牌** 2026-09-30
    'pbt_h': 227.85,  # **交叉带 H** = FY2025 境内六腿实测；2025 年报板块利润表；亦为 H 世界的六腿命名 FY2025
    'k_retain': 0.4722,  # 六腿利润总额 → 归母的留存率（税 + 少数股东 + 非六腿项后）；由 TTM 校准 = (`eps_ttm` × shares + perp) ÷ `pbt_m`；报表口径 归母 ÷ 利润总额 前三季度 0.552、Q3 单季 0.456，FY2024–25 0.5604–0.6094（A6）；只用于交叉带、六腿链坐标与 A20 桥 2026-09-30
    'k_bridge': 0.5653,  # 六腿链与 A20 线性桥用的**中周期**留存率 = 2026-06-30 的 TTM 校准值（落在 FY2024–25 实测 0.5604–0.6094 内）；三季报后 TTM 校准值 0.4722 是低谷读数，用它重推 FY2024 整年偏 −21%，故桥 / 链与交叉带分开（A6）；**不入底牌** 2026-06-30
    'perp': 22.24,  # 永续债利息**亿元/年** = 2026H1 的 11.12 年化（A7）；三季报未单列，前三季度倒推 78.22 − 0.39 × shares ≈ 17.0（±0.8）与之一致；只用于交叉带、六腿链坐标与 A20 桥 2026H1
    'r_perp': 0.1,  # 篮 4 龙头制造 10%：整公司一条经营腿（火电电价半管制 + 煤价周期；备选篮 6 撤销，A21）；跨市场固定（方案 A），A 股主锚；`check_r` 2026-09-20
    'r_perp_hkd': 0.1,  # 篮 4 龙头制造 10%，与 `r_perp` 同篮同值（方案 A，A21）；H 股平行价带用（税前公允值，不扣持有者税务，A13） 2026-09-20
    'cny_rf_gap': 0.015,  # 利率轴 r_f 货币段差 = HKD 中枢 4.0 − CNY 2.5（A21）；只用于货币段披露行（A 股 r_perp − gap = 8.5% 的对照带），**不进底牌**；待 `_AXIS.rates` 建成后复核 2026-09-20
    're_capex_fy24': 447.99,  # 2024 年风电 250.56 + 太阳能 197.43 资本支出（亿元；2024 年报「资本性支出情况」）；\(g_2\) 来源 = 增长 capex 边际回报（A15）；**不入公式** FY2024
    're_capex_fy25': 384.58,  # 2025 年风电 239.56 + 太阳能 145.02 资本支出（亿元；2025 年报）；2026 计划 305 + 72 = 377（A15）；**不入公式** FY2025
    're_pbt_fy23': 79.57,  # FY2023 风电 59.13 + 光伏 20.44 税前利润（亿元；2024 年报板块表）（A15） FY2023
    're_pbt_fy25': 84.91,  # FY2025 风电 56.08 + 光伏 28.83 税前利润（亿元；2025 年报）；2026H1 43.87 vs 2025H1 57.33（A15） FY2025
    're_cap_fy23': 28.527,  # 2023 末风电 15.463 + 太阳能 13.064 装机（GW）= 2024 末 18.109 / 19.836 − 2024 年新增 2.646 / 6.772（2024 年报）（A15） FY2023
    're_cap_fy25': 45.687,  # 2025 末风电 20.618 + 太阳能 25.069 装机（GW）；2025 年报（A15） FY2025
    'g_marginal_min': 0.05,  # 永续 \(g_2\) 转正门槛：增长 capex 边际税前回报 ≥ 5% 才允许 \(g_2 > 0\)（A15）；**规则参数，不入公式** 2026-09-20
    're_capex_plan26': 377.0,  # 2026 年风电 305 + 太阳能 72 资本支出计划（亿元；2025 年报）= D 桶未花 K_remain（A15 ⑨）；**不入公式** FY2025
    'fin_cost_h1': 35.29,  # 2026H1 财务费用（亿元；半年报），年化 ÷ `debt_ib` = 债务成本 2.3%（A15 ⑨）；**不入公式** 2026H1
    're_assets_est': 1900.0,  # 新能源净资产估算（亿元）：风电 20.6 GW × ~5,500 元/kW + 太阳能 25.1 GW × ~3,500 元/kW ≈ 2,010 亿毛值扣折旧；分母给资产平均回报 4.5%（A15 ⑨）；**估算，不入公式** 2025 末
    'tax_rate': 0.25,  # 所得税率假设（A15 ⑨ 项目价值）；**不入公式** —
    'capex_fy25': 583.0,  # FY2025 资本开支（亿元）；序列 407 / 594 / 637 / 583（2022–25）vs D&A 239 / 251 / 258 / 275 → 超出 300+ 亿 = 新能源建设窗口，债务融资（A15 三桶）；eval 断言 capex − D&A > 留存；**不入公式** FY2025
    'da_fy25': 275.0,  # FY2025 折旧摊销（亿元）（A15 三桶）；**不入公式** FY2025
    'debt_ib': 3161.0,  # 有息负债（亿元）= 短期借款 645.0 + 一年内到期非流动负债 252.6 + 长期借款 1,629.9 + 应付债券 553.8 + 租赁负债 80.0（三季报）vs 归属普通股权益 660 → 建设窗口靠债不靠留存（A15）；无净现金行；**不入公式** 2026-09-30
    'ni_fy25': 116.36,  # FY2025 归属普通股股东净利润**亿元**（已扣永续债利息）；派息率分母（A15） FY2025
    'g2_l': 0.0,  # **L 永续增长 = 0**（增长 capex 边际回报 0.6% < 门槛 5%，价负量负，A15）；三档共用、倍数 flat = 1/r（A8） 2026-09-20
    'g2_m': 0.0,  # **M 永续增长 = 0**；cap = min(6%, r − 4%) = 6%；\(PE\) = 1/0.10 = 10.0× 2026-09-20
    'g2_h': 0.0,  # **H 永续增长 = 0** 2026-09-20
    'g_policy_m': 0.06153,  # 派息政策 × 中枢 ROE = (1 − 0.5396) × 0.13364（普通股权益按 2026-09-30）；账面上限，被年报边际回报否定（A15）；eval 复算 ±5e-5；**不入公式** 2026-10-28
    'g_peer_min': 0.0113,  # 同业**留存分支**反解可用样本下沿（华电 600027，fPE 9.57 / ROE 7.47%，病态区）（A15 上限参照） 2026-09-11
    'g_peer_max': 0.0199,  # 同业留存分支反解可用样本上沿（浙能 600023，fPE 7.99 / ROE 5.53%，峰形区）（A15 上限参照） 2026-09-11
    'g_peer_cross': 0.0156,  # 同业留存分支簇中位（n=2；皖能 +8.44% 越 cap BLOCKED 剔除）；**只交叉，不入公式**（A15） 2026-09-11
    'pe_own_min': 7.61,  # A 股 5 年月频 TTM PE 实测下沿（2026-02）；**护栏，不入主公式**（A12） 2021-10~2026-09
    'pe_own_max': 26.12,  # A 股 5 年月频 TTM PE 实测上沿（2024-04）；**护栏，不入主公式**（A12） 2021-10~2026-09
    'pe_hk_own_mid': 7.7,  # H 股 own-year PE 近两年中位（6.46 / 8.93）；**仅参照，不入主公式**（A13） FY2025–2026
    'payout': 0.5396,  # FY2025 实测分红率（62.79 亿 ÷ 116.36 亿）；章程下限 0.50；进 `g_policy_m` FY2025
    'req_yield_a': 0.0493,  # A 股火电同业股息率中位（皖能/华电/浙能/大唐/国电） 2026-09-08
    'req_yield_h': 0.0627,  # H 股火电同业股息率中位（华电/大唐/华润电力） 2026-09-08
    'bond10y': 0.01681,  # 10 年期国债收益率；`req_yield_a` 的无风险分解基准 2026-08-25
    'dps': 0.4,  # FY2025 每股分红 CNY（2026-07 实施）；DDM 峰值坐标 D₀ 2026-07
    'perp_balance': 774.49,  # 永续债余额**亿元**（其他权益工具）；2026 三季报（2026-06-30 为 734.75；前三季度赎回 220 亿、新发约 222 亿，压降停止） 2026-09-30
    'pb_lo': 1.04,  # own-year PB 实测低沿（FY2020）；**A 股 L 地板兜底**：floor = pb_lo × bps = 4.27 > 情景值 3.50（A4）；H 股带只披露 FY2020
    'pbt_h1x2': 227.0,  # 2026H1×2 对照值 = 113.50 × 2；**不入主公式**（A3 的被否决口径） 2026H1
    'cons_fy26_mean': 0.562,  # FY2026 共识均值（Longbridge 11 家；区间 0.475–0.648）= **M**（A5 / A11） 2026-08-19
    'cons_fy26_lo': 0.475,  # FY2026 共识下沿；**坐标** 2026-08-19
    'cons_fy26_hi': 0.648,  # FY2026 共识上沿；**坐标** 2026-08-19
    'cons_fy27_lo': 0.48522,  # FY2027 共识 EPS 下沿（yfinance A 股线 n=2，普通股口径读）；**坐标，不入底牌**（A11） 2026-09-11
    'cons_fy27_mean': 0.65761,  # FY2027 共识均值；②-b 检验（A11）；**坐标** 2026-09-11
    'cons_fy27_hi': 0.83,  # FY2027 共识上沿；H MUST ≤ 此值；**坐标** 2026-09-11
    'eps_hk_fy27_lo': 0.51,  # H 股线（0902.HK）FY2027 共识下沿，n=5，CNY；**仅坐标** 2026-09-11
    'eps_hk_fy27_hi': 0.83,  # H 股线 FY2027 共识上沿；**仅坐标** 2026-09-11
}

def calculate(context):
    coal = context['axes']['coal']
    if coal['side'] != 'generator':
        raise ValueError('expected generator-side coal reference')
    inp = {**INPUTS, **{f'coal_{t}': coal['tier_prices'][t.upper()] for t in TIERS}}
    if any(not math.isfinite(inp[k]) for k in BASE_FIELDS):
        raise ValueError('base inputs must be finite')
    r, g = inp['r_perp'], inp['g2_m']
    if min(inp['shares'], inp['equity'], inp['hkdcny'], r) <= 0 or r <= g:
        raise ValueError('invalid base denominator or perpetual growth')
    eps = {t: inp[f'eps_{t}'] for t in TIERS}
    roe = {t: eps[t] * inp['shares'] / inp['equity'] for t in TIERS}
    pe = perpetual_pe(g, roe['m'], r)
    floor = inp['pb_lo'] * inp['bps']
    scenario_low = eps['l'] * pe
    values = (max(scenario_low, floor), eps['m'] * pe, eps['h'] * pe)
    if not all(math.isfinite(v) for v in values) or not values[0] < values[1] < values[2]:
        raise ValueError('base anchors must be finite and ordered')
    A, B = cut_points(*values)
    band = lambda values: dict(zip('LMH', values))
    # Historic coal scenarios describe the original earnings world; they do
    # not generate new EPS. The obsolete middle is explicit in both result
    # and document; do not mistake this migration for a fresh research update.
    warnings = ['historical_middle_earnings_falsified_by_2026q3',
                'historical_financial_evidence_requires_review']
    if any(not math.isfinite(inp[key]) or abs(inp[f'eps_{t}'] - inp[key]) > .0005 for t, key in
           (('l', 'eps_fy23'), ('m', 'cons_fy26_mean'), ('h', 'eps_fy25'))):
        warnings.append('historical_earnings_source_rows_differ')
    if any(not math.isfinite(inp[key]) or inp[key] != g for key in ('g2_l', 'g2_h')):
        warnings.append('historical_shared_growth_tiers_differ')
    return {'ticker': '600011.SH', 'currency': 'CNY', 'units': {'price': 'CNY_PER_SHARE'},
            'valuation_as_of': None, 'framework_as_of': None,
            'historical_financial_statement_as_of': '2026-09-30', 'historical_research_as_of': '2026-10-28',
            'anchors': band(values), 'cut_points': {'A': A, 'B': B}, 'candidate': None, 'option': None,
            'review_flags': warnings,
            'segments': {'company': {'unit': 'CNY_PER_SHARE', 'values': band(values)}},
            'key_parameters': {'company': {
                 'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', r)},
                 'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', g)},
                 'forward_return': {'unit': 'RATIO', 'values': band(roe[t] for t in TIERS)},
                 'steady_return': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', None) if g <= 0 else band(roe[t] for t in TIERS)}}},
            'historical_h_share_reference': {'currency': 'HKD',
                'anchors': band(eps[t] * pe / inp['hkdcny'] for t in TIERS)},
            'historical_coal_reference': {'unit': 'CNY_PER_TONNE', 'prices': band(inp[f'coal_{t}'] for t in TIERS)},
            'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                {'base_inputs': {k: inp[k] for k in BASE_FIELDS}}, BASELINE_LOCAL)}
