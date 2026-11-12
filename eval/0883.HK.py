#!/usr/bin/env python3
"""CNOOC's historical operating valuation and excess cash, HKD per share.

Retains original 2026 inputs, dividend and cash judgments, and shared oil axis;
this is a draft research result, not a new forecast or publication.
"""
from __future__ import annotations
import statistics
from lib.gordon import (NEAR_FULL_PAYOUT, basket_r, check_branch, check_g_cap, check_r,
                             g_cap, implied_g_retaining, perpetual_pe, recovery_two_stage_pe)
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis', 'rf_report'),
                'axes': {'brent': 'brent_oil'}}
HISTORICAL_PARTIAL_FINGERPRINT = '78e62032cc176ab40fe2b7c290dfeeee06ad906f9f30698d1e650327cfd5d7d7'

TICKER = '0883.HK'

# Original inputs, with purpose, source and as-of.
INPUTS = {
    # 总股本（A+H）47,529,953,984 股；Longbridge static | as-of 2026-06-30
    'shares': 4.7529953984e10,
    # 归母权益 RMB 百万；中报 p.30；经营股权 = equity − `div_exdiv` − `c_ex`（RONIC 分母，A19）；账面 ROE = NI_x ÷ equity 只进轴 §3 表与披露 | as-of 2026-06-30
    'equity': 856054,
    # HKD→CNY；yfinance `HKDCNY=X` | as-of 2026-09-14
    'fx_hkdcny': 0.8548,
    # FY2025 归母净利润 RMB 百万（年报 p.11）；每桶盈利基点（A1） | as-of FY2025
    'ni_fy25': 122082,
    # FY2025 基本 EPS CNY（Longbridge 年报序列）；周期均值成员 | as-of FY2025
    'eps_fy25': 2.5685,
    # 2025H1 归母 RMB 百万（中报 p.9 财务摘要）；TTM 用（A4） | as-of 2025H1
    'ni_h1_25': 69533,
    # 2026H1 归母 RMB 百万（中报 p.9 / p.30）；k 两点法与 TTM（A2 / A4） | as-of 2026H1
    'ni_h1_26': 85818,
    # FY2025 原油及液体销量 mmbbl（年报 p.17） | as-of FY2025
    'liq_fy25': 589.2,
    # FY2025 实现油价 US$/bbl（年报 p.11） | as-of FY2025
    'real_fy25': 66.47,
    # 2026H1 液体销量 mmbbl（中报 p.29） | as-of 2026H1
    'liq_h1_26': 303.6,
    # 2026H1 实现油价 US$/bbl（中报 p.29） | as-of 2026H1
    'real_h1_26': 85.49,
    # 2026 产量目标中值 mmboe（780–800，年报 p.74）；2027 指引 `待补`（A2） | as-of FY2026 目标
    'prod_2026_mid': 790,
    # FY2025 液体 / 总产量 = 599.7 / 777.3（年报 p.9） | as-of FY2025
    'liq_share': 0.7715,
    # FY2025 液体销量 / 产量 = 589.2 / 599.7 | as-of FY2025
    'sales_ratio': 0.9825,
    # 2025 年布伦特全年均价 US$/bbl（年报 p.70）；ρ 分母（A1） | as-of FY2025
    'brent_2025': 68.2,
    # **L** Brent US$/bbl = `_AXIS.brent-oil.md` L 档（2025 实测均价回归）；eval 逐格对轴校验 | as-of 2026-09-15
    # **M** Brent = 轴 M 档（2027 卖方 / 官方中枢 = 中枢分子，A4） | as-of 2026-09-15
    # **H** Brent = 轴 H 档（汇丰 2027 高位持续 ≈ 2026H1 实测 87.6） | as-of 2026-09-15
    # **书面派息下限**「2025–2027 年度派息率不低于 45%」（年报 p.50 / p.74）；DDM 对照 \(D_1 = payout\_policy \times EPS_x\) 与可持续上限（A7），**不进主公式** | as-of FY2025 年报
    'payout_policy': 0.45,
    # FY2025 DPS（A 股 CNY 口径 0.6661 + 0.4788 = HK$0.73 + 0.55）；实付派息率 → 可持续上限 \((1-payout)\times ROE_M\)（A7） | as-of FY2025
    'dps_fy25_cny': 1.1449,
    # FY2025 DPS HKD（年报 p.3）；跨周期 DPS CAGR 终点（A11） | as-of FY2025
    'dps_fy25_hkd': 1.28,
    # FY2019 DPS HKD（中期 0.33 + 末期 0.45，Longbridge `dividend`）；CAGR 起点，剔除特别股息 | as-of FY2019
    'dps_fy19_hkd': 0.78,
    # FY2025 末期股息 HKD（年报 p.3）；D₀(TTM) = 末期 0.55 + 2026 中期 0.94 = 1.49，交叉，**不进公式** | as-of FY2025
    'dps_fy25_final_hkd': 0.55,
    # 2026 中期股息 HKD（中报 p.3）；D₀ 交叉，**不进公式** | as-of 2026H1
    'dps_h1_26_hkd': 0.94,
    # 整公司 E&P 腿 → **篮 7 国别重** 篮子 r（美国 NS-CMIC 投资禁令 = 高国别风险；生意本身篮 6，对照带 r = 0.13 = 制裁折价消失，A17）；Gordon 主尺与 DDM 对照共用 | as-of 2026-09-22
    'r_perp': 0.15,
    # **永续增长 = 产量驱动 4.5%**（用户判断，2026-10-15 框架纠正时确认保留：capex 超出 D&A 是具名增长项目，产量 +5–8%/yr；与同业 DDM 反解中位 4.58% 同量级，A8 / A18）；三档共用；cap = min(6%, r − 4%) = 6% ✓；上限 (1 − d) × RONIC 见 A19 | as-of 2026-10-15
    'g2': 0.045,
    # FY2025 资本开支付现 RMB 百万（年报 p.73）；留存去向依据（A18），**不进公式** | as-of FY2025
    'capex_fy25': 111555,
    # FY2025 折旧摊销 RMB 百万（≈ 811 亿）；留存去向依据（A18），**不进公式** | as-of FY2025
    'da_fy25': 81100,
    # 扩展口径净现金 = 货币资金 314,378 + 交易性金融资产 11,892 − 有息负债（长期借款 4,578 + 应付债券 51,547 + 一年内到期非流动负债 4,049）− 租赁负债 7,914（RMB 百万；东方财富 F10 `600938` 合并资产负债表，A19） | as-of 2026-06-30
    'net_cash_ext_h1': 258182,
    # 类债项：已宣派、6/30 未付的 FY2025 末期股息 0.4788 元 × 475.30 亿股（其他应付款 2025 末 83.0 → 6 月末 318.0 亿印证已挂负债，A19） | as-of 2026-06-30
    'div_declared': 22757,
    # 类债项：2026 中期股息 HK$0.94 × 475.30 亿股（2026-09-10 除息、10-16 派付；按 2026-08 月末 HKDCNY 0.8579 折，近似）；6/30 归母权益未扣，经营股权同扣（A19） | as-of 2026-09-10
    'div_exdiv': 38330,
    # 少数股东权益 RMB 百万（中报 p.30）；归母比例 = (`equity` − `div_exdiv`) ÷ (同 + 本值) = 99.69%（无子公司级现金披露，按权益比例；A19） | as-of 2026-06-30
    'minority_equity': 2505,
    # **超额现金（归母份额）** =（`net_cash_ext_h1` − `div_declared` − `div_exdiv` − 经营所需现金锚 0）× 归母比例 99.69% = 197,095 × 0.99695（锚：「扩展口径净现金 ÷ 收入」2016–25 最低 −46.0%（2016）为负 → 取下限 0）；少数股东那份 6.0 亿不计；占归母权益 23.0% ≥ 15% → 单列（A19） | as-of 2026-06-30
    # 现金收益率 FY2025 = （利息收入 + 投资收益扣联营合营 + 公允价值变动收益）52.73 亿 ÷ 平均货币资金与交易性金融资产 2,203.3 亿（A19） | as-of FY2025
    'cash_yield': 0.02393,
    # 实际所得税率 FY2025 = 所得税 ÷ 利润总额（东方财富利润表） | as-of FY2025
    'tax_eff': 0.27995,
    # 留存拆分 FY2020–24（分母 = 经营利润合计 4,919.8 亿）：分红 d（宣派口径）；约束 1 / 2 的 d 取它与 FY2025 实付 44.6% 的较大者（A19） | as-of FY2020–24
    'ret_d': 0.518,
    # 同窗口现金积累 c = Δ超额现金 1,012.8 − 现金自身税后收益 67.7 亿（A19） | as-of FY2020–24
    'ret_c': 0.192,
    # 同窗口经营再投资 i = Δ经营股权（归母权益 − 超额现金）4,413.9 → 6,394.7 亿；只披露（A18 / A19） | as-of FY2020–24
    'ret_i': 0.403,
    # 经营口径派息率 = d + c；`check_branch` 用（A19） | as-of FY2020–24
    # FY2023 经营回报 = 经营利润 ÷ 平均经营股权（商誉留在分母）；「持续失败」检验，**不进公式** | as-of FY2023
    'op_ret_fy23': 0.2186,
    # FY2024 同上 | as-of FY2024
    'op_ret_fy24': 0.2187,
    # FY2025 同上 | as-of FY2025
    'op_ret_fy25': 0.1883,
    # DDM 对照的股息永续增速 \(g_d\)（同业 DDM 反解中位，A8）；**只进 DDM 对照，不进主尺** | as-of 2026-09-14/15
    # \(g_2\) 证据区间下沿 = 点（g2 来自实测产量增速，区间退化）；敏感区 ±1pp 见 Outputs（A9） | as-of 2026-09-18
    'g_evid_min': 0.045,
    # 同上 | as-of 2026-09-18
    'g_evid_max': 0.045,
    # CVX 同尺 DDM 反解 = 10% − 67.2% / 15.85（价 213.59 / FY2027E 13.47）；单调区（A8，对照） | as-of 2026-09-14
    'gd_peer_cvx': 0.05763,
    # TTE 同尺 DDM 反解 = 10% − 49.3% / 8.86（价 91.78 / FY2027E 10.36）；单调区（对照） | as-of 2026-09-14
    'gd_peer_tte': 0.04434,
    # 中国神华 1088.HK 同尺 DDM 反解 = 10% − 74.5% / 13.76（价 45.44 HKD / FY2027E 2.823 CNY）；单调区（对照） | as-of 2026-09-15
    'gd_peer_1088': 0.04583,
    # H 股 5 年月频**经营** TTM PE 实测下沿（2022-09）= (月收盘 × 当月 HKDCNY − 当时每股超额现金) ÷ 当时可见 TTM 经营 EPS（月 K Longbridge，财务东方财富 / Longbridge，按披露时限取月末已公告报告）；**护栏**（A9） | as-of 2021-09~2026-08
    'pe_op_min': 2.85,
    # 同口径实测上沿（2026-04）；**护栏**；生成经营倍数须 ≤ 此值；\(1/r\) ≤ 此值是 Gordon 可达的条件（A6） | as-of 2021-09~2026-08
    'pe_op_max': 8.79,
    # 同口径 5 年月频中位（n = 60）；**交叉尺，不进公式** | as-of 同上
    'pe_op_med': 5.46,
    # M 档同等盈利月份（可见 TTM 经营 EPS 落在 M 档经营 EPS 2.870 ±12% 的 36 个月，2023-04～2026-03）的经营倍数中位（区间 2.97–8.31）；**交叉，不进公式**（A9） | as-of 2023-04~2026-03
    'pe_same_med': 5.16,
    # 共识 FY2026E EPS 均值 CNY（yfinance 12 家，3.17–3.61）；中枢比值交叉 | as-of 2026-09-14
    'eps_cons_fy26_mean': 3.37863,
    # 共识 FY2027E EPS 区间下沿（yfinance 13 家）；**②-b 判据与交叉，不进公式**（A5） | as-of 2026-09-14
    'eps_cons_fy27_lo': 2.50953,
    # 共识 FY2027E EPS 均值；②-b：均值 > H 即红；< M 时须 | as-of 偏离
    'eps_cons_fy27_mean': 3.05925,
    # 共识 FY2027E EPS 区间上沿；交叉 | as-of 2026-09-14
    'eps_cons_fy27_hi': 3.45065,
    # Longbridge H 股 16 家目标价均值 HKD（17.54–42.48）；**交叉，不进公式**（A12） | as-of 2026-09-13
    'tp_cons_h': 31.63,
    # FY2025 自由现金流 RMB 百万 = OCF 209,042 − 资本开支付现 111,555（年报 p.85 / p.73）；P/FCF 10× 交叉，**不进公式** | as-of FY2025
    'fcf_fy25': 97487,
    # FY2020 EPS CNY（谷底，Brent ~42；Longbridge 年报序列）；压力坐标 + 周期均值成员（A3 / A4） | as-of FY2020
    'eps_fy2020': 0.5590,
    # FY2021 EPS CNY；周期均值成员（A4） | as-of FY2021
    'eps_fy2021': 1.5700,
    # FY2022 EPS CNY（峰值）；周期均值成员 + 回归段坐标（A3 / A4） | as-of FY2022
    'eps_fy2022': 3.0300,
    # FY2023 EPS CNY；周期均值成员 | as-of FY2023
    'eps_fy2023': 2.6000,
    # FY2024 EPS CNY；周期均值成员 | as-of FY2024
    'eps_fy2024': 2.9000,
    # FY2020 净产量 mmboe（2020 年度业绩公告）；产量归一（A4，**不进公式**） | as-of FY2020
    'prod_fy2020': 528.1,
    # FY2021 净产量 mmboe | as-of FY2021
    'prod_fy2021': 572.9,
    # FY2022 净产量 mmboe | as-of FY2022
    'prod_fy2022': 623.9,
    # FY2023 净产量 mmboe | as-of FY2023
    'prod_fy2023': 678.0,
    # FY2024 净产量 mmboe（年报 p.9） | as-of FY2024
    'prod_fy2024': 726.8,
    # FY2025 净产量 mmboe（年报 p.9） | as-of FY2025
    'prod_fy25': 777.3,
}

# Original historical reasoning; comments are not additional model inputs.
# - **业务地图摘要**：单一 operating segment（油气勘探开发生产），年报按中国 / 海外分地区披露产量与资产（2025 年报 p.13–17、2026 中报 p.12）。分部启发式命中 0 条（地区拆分不是业务拆分；驱动因子同为 Brent；卖方无 SOTP）→ 整公司尺。
# - **属性 A — 桶油全成本 US$27.9–29.7 是本票的生意底色**：FY2025 全成本 27.90（年报 p.11），2026H1 29.7（中报 p.10）；实现油价 66.47 / 85.49 → 每桶归母 207 / 283 元。2020 年（Brent ~42、实现 40.96）仍盈利 249.56 亿（EPS 0.559）——谷底不亏损，是 `deep_discount` 压力坐标（0.559 × 1/r ÷ 0.8548 = **5.03 港元**）。
# - **属性 B — 每桶盈利对实现油价的弹性 k = 3.968 RMB/bbl/US$1（两点实测）**：FY2025 → 2026H1 每桶归母从 207.20 升到 282.67，实现价 +19.02 → k 3.968；理论值 (1 − SOG 特别收益金边际 ~30%)(1 − 25%) × 7.0 ≈ 3.7 同量级（SOG 五级累进 20–40%，起征 US$65，年报 p.117）。ρ = 实现价 / Brent = 0.9746（FY2025）、0.9759（2026H1）。**已知偏差**：两点实测落在 66→85 区间，Brent >85 后 SOG 边际税率上一档（40%），H 档以上弹性偏高——留在 `stretched` 解释。
# - **属性 C — 市场实付带在 Gordon 尺上说的是 r，不是 g；与欧洲同业的差主要是 H 股折价，不是美国投资禁令**：M 档前瞻经营回报（RONIC）22.0%（L / H 档 19.4 / 25.7%），在篮 4 的 10% 下 \(PE(g)\) 单调上升、\(g=0\) 处 10× > 经营倍数带顶 8.79——任何 \(g\in[0,6\%]\) 都到不了市场五年实付的经营倍数带（中位 5.46×），读法只有一种：r 高于篮 4。r 拆两层：欧洲同业（SHEL / TTE / BP）同尺隐含 12.5–13%（2026-09-14）= 篮 6 周期商品；本票与欧洲同业的回报要求差约 5 个百分点，**主要是 H 股折价**（同一家公司的 A 股长期比 H 股贵；港股流动性与持有人结构），**不是美国投资禁令**。禁令本身——**NS-CMIC 名单**（2021-06-03 上榜、2021-08-02 禁买、2022-06-03 前美资清仓；MSCI / FTSE 同步剔除；2025-11-07 续期一年、FY2026 NDAA 加了连续七年逐年审议追加制裁的条款——方向是加码）——是可命名、可核的国别风险，是归篮 7 的依据，但解释不了这段差的大头。按篮子表「高国别风险 → 篮 7」归篮（A17）：15% 下 \(1/r\) 6.67× 落进经营倍数带内、留存分支可达。篮 7 的默认形状「\(1/r\) 地板 + 价值差进 \(V_{opt}\)」是为增长不可命名的故事股写的，本票增长由具名 capex 承载（A18），故保留留存式（A17 写明）。`0857.HK`（病态区、不在禁令名单）用派息政策 × ROE 生成倍数；本票的倍数由产量增长 \(g_2\) 与 M 档 RONIC 生成，三档同一倍数（A19）。
# - **属性 D — 派息政策有书面下限，且实付贴着下限**：年报 p.74 原文「the annual dividend payout ratio will be no less than 45% from 2025 to 2027」；p.50 原文「From 2025 to 2027, the expected annual payout ratio of the Company will be no less than 45%」。FY2025 实付 44.6%（DPS HK$1.28 = 1.1449 元 × 47.53 亿股 ÷ 归母 1,220.82 亿；年报 p.13 印「45%」）。DPS（HKD）：FY2018 0.70 · FY2019 **0.78** · FY2020 0.45 · FY2022 1.45 · FY2023 1.25 · FY2024 1.40 · FY2025 **1.28** · 2026 中期 **0.94**（中报 p.3）；FY2021 序列不完整（Longbridge 只列中期 0.30 与 A 股上市纪念特别股息 1.18，末期常规股息 `待补` 核对；特别股息一律剔除，且 FY2021 不是 CAGR 端点）。跨周期 FY2019→FY2025（Brent 64.8 → 68.2，端点油价相当）DPS CAGR **+8.6%**（HKD；折人民币 ≈ +9.3%），归母 CAGR +12.2%——增长来自产量 528→777 mmboe（+47%），不是油价。派息下限进 DDM 对照与可持续上限检验（A7），不进主公式。
# - **属性 E — 无永续债 / 优先股**；归母 = 归属普通股股东；少数股东权益仅 25.05 亿（中报 p.30）。
# - **属性 F — A/H 双挂，A 股不受禁令影响**：A 股不受美国禁令影响（美资本就不经沪股通持有本票），也没有 H 股股息税（H 股股息预扣税 10%，内地个人经港股通 20%；A 股持有 >1 年免税）；A 股对照带仍按 H 股主尺同倍数印，两地价差里的「制裁折价 + 港股附加 + H 股股息税」只作解释，不进锚点。本票不挂 `_AXIS.southbound-repricing.md`，A/H 只双报（A16）。
# | A1 | **三档分子 = 轴三档 Brent 经自身每桶盈利弹性桥到 FY2027 归母**：\(NI_x = liq\_2027\times[NI/bbl_{FY25} + k(\rho\,brent_x - real\_fy25)]\) → 123,612 / 139,822 / 162,980 百万 → EPS **2.6007 / 2.9418 / 3.4290**；分子年份 FY2027（≥2 家带区间的最远共识年，13 家），不折现 | active | FY2025 归母 122,082、液体销量 589.2 mmbbl、实现油价 66.47（年报 p.11 / p.17）；2026H1 归母 85,818、液体销量 303.6、实现油价 85.49（中报 p.29–30）；Brent 2025 均价 68.2（年报 p.70）；轴三档 68 / 75 / 85（`_AXIS.brent-oil.md` §1）。页码为 PDF 页 | `ni_fy25`、`liq_fy25`、`real_fy25`、`ni_h1_26`、`liq_h1_26`、`real_h1_26`、`brent_*`；eval 逐格对轴校验（含轴 §3 表本票 NI / EPS / ROE） |
# | A2 | **k = 3.968 RMB/bbl/US$1、ρ = 0.9746（FY2025 → 2026H1 两点实测）；液体销量 598.8 mmbbl = 2026 产量目标中值 790 mmboe × 液体占比 0.7715 × 销量/产量 0.9825**；**2027 产量指引 `待补`**（摩根士丹利 103139：2026 增速 5%→3%、Whiptail 2027 上线） | active | 年报 p.74（2026 目标 780–800 mmboe）；液体占比 = 599.7 / 777.3（年报 p.9）；销量/产量 = 589.2 / 599.7。**已知偏差**：2027 产量若按公司「2025–2027」三年目标上沿 810–830 计，液体销量 +3–5%、三档同比例上移 → M +0.9–1.5 港元；本框架用 2026 中值，不预支 2027 爬坡 | `prod_2026_mid`、`liq_share`、`sales_ratio`；2027 指引公布后重设 |
# | A3 | **本票挂 `_AXIS.brent-oil.md`**，三档 Brent 逐格引用；L = 2025 实测年均 68（上一轮周期除 2020 外的价格谷底），M = 2027 卖方 / 官方中枢 75，H = 汇丰 2027 高位 85 ≈ 2026H1 实测 87.6。**L 分子是轴 L 档梯值，不是本票实测谷底** → 配同一稳态 \(g_2\)，不走 `recovery_two_stage_pe`；本票实测谷底 FY2020 EPS 0.559（Brent ~42）× 1/r = 5.03 港元只作 `deep_discount` 压力坐标 | active | 轴文件 §1–§3；valuation-rules「谷底档」适用范围（轴梯值 = 可命名的世界状态）。回归段坐标（2020→2022 实测 EPS 0.559 → 3.03，g₁ 132.8%、n=2）作坐标打印，不作锚 | `brent_*`；eval 打印回归坐标与压力坐标 |
# | A4 | **中枢分子（valuation-rules「周期票的中枢分子」）：M = 轴 M 档 Brent 75 = 2027 卖方 / EIA 中枢（5 点中位），不是当前有利价位**；两条印证：① 上一轮完整周期 2020–2025（含 2020 谷底、2022 峰值）Brent 实测均价 **74.1** ≈ 75；② 自身同期 EPS 实测均值 **2.205**（0.559 / 1.57 / 3.03 / 2.60 / 2.90 / 2.5685），按产量归一到 790 mmboe 后 **2.605**，M 2.942 高出 13%（≤ 20% ✓）——未归一的 2.205 低 25% 是产量基数（528 → 777 mmboe，+47%）而非油价 regime。**当期 ÷ 中枢**：TTM EPS 2.911（2025H2 52,549 + 2026H1 85,818）÷ 2.942 = **0.99** ≤ 1.15 → 当期不在周期高位，M 不换；2026H1 年化 3.611 ÷ 中枢 = **1.23** > 1.15 → `optimistic` 侧坐标（Brent 87.6 ≈ H 世界）；FY2026E 共识 3.379 ÷ 中枢 = 1.15（贴线）。**「市场 PE < 篮 4 的 1/r」的第一读法（分子在高位）不成立**（0.99），故读法落到第二层：说的是 r（属性 C / A17） | active | yfinance `BZ=F` 月收盘均值（轴文件 §1）；Longbridge 年报 EPS 序列（CNY）；产量：历年业绩公告（2020 528.1 / 2021 572.9 / 2022 623.9 / 2023 678.0 / 2024 726.8 / 2025 777.3，2024–2025 于 2025 年报 p.9 核对）。**证伪触发器**：轴 M 移位 ≥ US$5（轴 §5）→ 先改轴 | `eps_fy20xx`、`prod_fy20xx`（印证，**不进公式**）；eval 校验 TTM ÷ 中枢 ≤ 1.15、产量归一均值与 M 差 ≤ 20% |
# | A5 | **②-b 判据：共识 FY2027 均值 3.059 落在 [M 2.942, H 3.429] 内、M 偏离 −3.8%（≤ 20%）→ 情景梯保留，共识三点只作印证坐标** | active | yfinance 2026-09-14：FY2027 13 家 2.51 / 3.059 / 3.45；FY2026 12 家 3.17 / 3.379 / 3.61。按本票弹性，均值 3.059 ↔ Brent **77.4**。**证伪触发器**：下一次共识刷新（2026 三季报后）若均值 > H → H 换市场基准世界；若均值 < M 且偏离 > 20% → 分子改共识三点 | `eps_cons_fy27_lo/mean/hi`（不进公式）；eval 机械化 |
# | A6 | **主尺形态 = Gordon 留存分支；「DDM 主尺例外」不适用**：三前提中 (a)「留存分支 Gordon 生成倍数落自身实测带外、任何 \(g\in[0,6\%]\) 都到不了带」在篮 7 的 15% 下不成立——\(1/r\) = **6.67×** ≤ 经营倍数带顶 **8.79**（2026-04；2026-10-15 改经营口径，整股口径带顶为 9.89），带边反解 `implied_g_retaining(8.79, RONIC_M 21.96%)` = 7.5%（> cap，只打印）→ 裁决顺序 ③ 不触发；(b) 书面派息下限 45%（A7）与 (c) 域判定（RONIC − r = +4.37 / +6.98 / +10.71pp：三档单调区）仍在，但只在 (a) 成立时才把主尺切到 DDM。DDM 因此退为对照（Outputs「DDM 对照」行） | active | 月 K `kline_m_883`（Longbridge 2021-09~2026-08，n = 60）× 当时可见报告的 TTM 经营 EPS 与超额现金（东方财富 `600938` / Longbridge 半年报）；年报原文；`gordon.py` `_ROE_NEAR_R` | 主尺形态；eval 机械化：\(1/r \le\) `pe_op_max`；经营带顶跌破 \(1/r\)（< 6.67×）→ (a) 重新成立 → 回对话切 DDM 主尺 |
# | A7 | **书面派息下限 45%**（`payout_policy`）进两处：① DDM 对照 \(D_1 = 45\% \times EPS_x\)；② 实付分配 d 进 ③ 约束 1 / 2（取 FY2025 实付 44.6% 与 FY2020–24 窗口分红 51.8% 的较大者）：\(g_2\) 4.5% ≤ (1 − 51.8%) × RONIC 21.96% = 10.60% ✓（公司实际留下的钱撑得起这个增长，A19） | active | 年报 p.50：「From 2025 to 2027, the expected annual payout ratio of the Company will be no less than 45%. By adhering to the principle of returning to shareholders, the Company will adjust the dividend policy as needed.」；p.74：「subject to the approval by the general meeting on the proposed dividends for each year, the annual dividend payout ratio will be no less than 45% from 2025 to 2027.」；FY2025 DPS HK$1.28（年报 p.3：中期 0.73 + 末期 0.55）= A 股 1.1449 元 → 1.1449 × 47.53 亿 ÷ 122,082 = **44.57%**（年报 p.13 印 45%） | `payout_policy`、`dps_fy25_cny`；**政策 2027 到期**：2027 年报若未续（回到章程 / 历史 40%）→ 事件增量重设 DDM 对照与可持续上限 |
# | A8 | **DDM 对照的 \(g_d\) = 同业 DDM 同尺同日反解中位 +4.58%**（只进对照，不进主尺）。同尺 = \(g_d = r_{同尺} - payout/fPE\)（同尺 r 取 10%，与同业簇口径一致），fPE 取价 / FY2027E 共识均值（与本票分子同年），派息率取 yfinance TTM（中石油取年报 54.7%）；逐家判域（ROE_fwd = FY2026E EPS ÷ BPS）：**可用（单调区、0 < g_d ≤ 6%）**：CVX 15.85× / 派 67.2% / ROE 16.7% → **+5.76%**；TTE 8.86× / 49.3% / 19.1% → **+4.43%**；神华 1088.HK 13.76× / 74.5% / 13.8% → **+4.58%**（跨商品，同为国企 H 股高派息；09-15 数据）→ 中位 **4.58%**（n=3）。**剔除、不截顶**：XOM +6.57%、SHEL +6.46%（> cap；回购为主要返还渠道，派息口径 g_d 天然偏高）；BP −0.17%（TTM 派息 95% 是谷底 EPS 基数，与股息逐年上调矛盾）；COP +6.93% / EQNR +6.33%（同为 > cap）。**不同域只作交叉**：中石油 0857.HK +3.86%（病态区）；中石化 0386.HK +2.87%（峰形区）。主尺的 \(g_2\) 4.5% 来自自身实测产量增速（A18），与同业中位 4.58% 同量级——两条独立来源互相印证 | active | 历史本地缓存、`peer_1088_yf_2026-09-15.json`；`dividend_h.json`；`pe_monthly_5y.json` | `g2_d`、`gd_peer_cvx/tte/1088`；eval 复算中位 ±5e-5、各同业 ∈ (0, cap]；每季度同日重拉同业 |
# | A9 | **护栏 + \(g_2\) 杠杆显式（经营口径，2026-10-15）**：生成经营倍数 \((1-g/RONIC)/(r-g)\) = **7.57×**（三档同一）∈ 自身 5 年月频经营 TTM PE 带 [2.85, 8.79] ✓（③ 不出带）。**同等盈利交叉**：可见 TTM 经营 EPS 落在 M 档 2.870 ±12% 的 36 个月（2023-04～2026-03）经营倍数 2.97–8.31、中位 **5.16×**，模型 M 7.57× 高出 47%（> 20%）：差额与 g 无关（\(g=0\) 时仍为 6.67×，高出 29%），指向 r 或市场对现金的折价；g 已由用户确认、λ 只认财报证据（A19），只披露不改锚。⚠ **两向敏感区**：\(g_2\) −1pp（3.5%）→ 26.47 / 29.38 / 33.55；+1pp（5.5%）→ 28.18 / 31.33 / 35.83（倍数仍在带内）；1pp ≈ M **1.0 港元（3.3%）**；`r_perp` ±50bp → 28.36 / 31.54 / 36.07 与 26.23 / 29.11 / 33.23。大摩「2026 增速 5%→3%」的下调方向是 −1pp 一侧 | active | Inputs `g2`、`pe_op_min/max`、`pe_same_med`；月度表见 A6 来源 | eval 校验三档倍数在带内并打印敏感区；**MUST NOT** 在 [3.5%, 5.5%] 里挑 \(g_2\) 让 zone 好看 |
# | A10 | **r 的横截面对照（同尺 \(0.75/fPE + 4.5\%\)，2026-09-14）**：SHEL / TTE / BP 12.5–13.0% = 篮 6，XOM / CVX / COP 9.2–9.8% = 篮 4——本票篮 7 的 15% 高于欧洲同业；本票与欧洲同业约 5 个百分点的回报要求差主要是 H 股折价，不是禁令（属性 C），禁令只是归篮 7 的可命名依据（A17）。（同业读数是 2026-09-14 的整股口径，未扣同业现金，只作归篮背景，不进锚点。）**篮 6 对照带（13%，经营倍数 9.36× 三档同一 + 现金）32.52 / 36.25 / 41.58**——两带之差 = 篮 7 与篮 6 一档 r 的价格（M 6.0 港元 / 20%）；它主要随 H 股折价收敛，不是单靠禁令解除就能收回（属性 C）。卖方 TP 均值 31.63 扣现金后 = 7.98× M 档经营 EPS ↔ 同尺 r 14.5%（A12）。**归篮不是拧 r**：篮 7 由「高国别风险」判据归入；**MUST NOT** 用 \(g_2\) 把 M 推到市价 | active | `gordon.py` 单调区行；历史本地缓存；Longbridge TP 2026-09-13 | `r_perp`；篮 6 对照带；eval 打印 |
# | A11 | **同世界门（裁决顺序 ④「门不许空转」）**：分子年 FY2027 = 最远带区间共识年，「分子年 → 最远共识年」无从比较；FY2028 ≥2 家点估计 `待补`（Longbridge / yfinance 都没有）→ 改取自身实测 CAGR 方向：**跨周期 FY2019→FY2025**（Brent 64.8 → 68.2，端点相当）归母 61,045 → 122,082（**+12.2%/yr**）、DPS 0.78 → 1.28 港元（**+8.6%/yr**），方向为正 → \(g_2>0\) 可用。**未取的两个方向**：① 3 年 FY2022→2025 归母 −4.8% / DPS −4.1%——起点是 Brent 98.6 的峰值年，符号是油价 regime 不是增长；② 共识 FY2026 3.379 → FY2027 3.059（−9.5%）——这是 deck 从 2026 的 88 归一到 2027 的 75，已由分子（轴 M）承载（裁决顺序 ②「分子与 g 同世界」），若再拿它当门就是把油价算两遍 | active | Longbridge 年报序列（`is_af_a.json`）；`dividend_h.json`；yfinance 2026-09-14 | `g2` 符号；FY2028 ≥2 家共识出现后按其方向重判 |
# | A12 | **未采用卖方目标价**：Longbridge H 股 16 家均值 **31.63**（17.54–42.48，2026-09-13）；汇丰 **29.30**（2026-08-06，99355）；摩根士丹利 **30**（2026-08-28，103139） | active | H / TP 均值 = 1.09、M / TP = 0.96；TP 均值扣每股超额现金 4.15 元后 = 7.98× M 档经营 EPS，落本尺 `neutral`（A 28.75 – B 32.42）、篮 6 对照带 `deep_discount` | 交叉校验；TP 不反解进倍数 |
# | A13 | **\(V_{opt}\) = 0；无候选带** | active | 圭亚那 Stabroek（Yellowtail 2025 投产、Uaru / Whiptail 2026–27）与巴西 Buzios 都在 E&P 腿内（产量目标已含），不是新单位（A2e-7c-4）；FY2028 单家共识未在 Longbridge / yfinance / Wisburg 摘要中找到 → 无候选带输入 | Outputs 无表3、无候选带行 |
# | A14 | **`deep_discount` 观察项**：① 2027 后派息政策不续（45% 下限到期，回到 2022–2024 的政策下限 40% → DDM 对照与可持续上限重设）；② SOG 特别收益金：Brent >US$85 边际税率 40%，H 档以上弹性偏高（属性 B）；③ 产量指引下调（摩根士丹利 2026 增速 5%→3%）与圭亚那 PSC 分成变化——直接打在 \(g_2\) 上（敏感区，A9）；④ H 股股息预扣税与 A/H 折价走阔；⑤ 减值（年报 p.73「Impairment and provision」）；⑥ 制裁升级（NS-CMIC 之外追加 SDN 级制裁 / 港股通剔除）——篮 7 已是最高篮，再升级只能进 `deep_discount` 解释，**MUST NOT** 拧 r。任一项被财报证实 → 事件增量改 A2 / A7 / A18，**MUST NOT** 压 L 去贴现价 | active | 年报 p.117（SOG）；Wisburg 103139 / 99355 | `deep_discount` 行排查顺序 |
# | A15 | **分子口径 = 归属母公司股东 = 归属普通股股东**：无永续债、无优先股（中报 p.30 权益表：股本 / 储备 / 留存收益 / 少数股东权益 2,505 百万） | active | 中报权益变动表（p.30）；年报 p.4 财务摘要 | `ni_fy25`、`equity` 口径 |
# | A16 | **A/H 双报，不挂 `_AXIS.southbound-repricing.md`**：A 股对照带 = CNY 档（同经营倍数、同超额现金；A 股不受美国禁令影响，属性 F） | active | 属性 F | A 股对照带；eval 打印 |
# | A17 | **归篮：整公司 E&P 腿 → 篮 7 国别重（r = 15%）**（2026-09-22 由篮 6 改归；篮 6 13% 降为「制裁折价消失」对照带）。判据：篮子表篮 7「高国别风险」——本票自 2021-06-03 在美国财政部 NS-CMIC 名单（14032 号行政令：美国人不得买入其公开证券，2022-06-03 前清仓；纽交所 2021 强制摘牌；MSCI / FTSE 剔除），国家紧急状态 2025-11-07 续期至 2026-11-12，FY2026 NDAA 加「连续七年逐年审议对已上榜公司追加法定制裁」条款——禁令可命名、可核、方向加码，把港股最大一类外资整体排除在买方外；10 年 PB 从未 >1.5（美股龙头 2.2–2.6）。生意本身是篮 6（纯上游、盈利是 Brent 函数）；篮 7 = 篮 6 + 国别风险。**形状**：篮 7 默认「\(1/r\) 地板 + 价值差进 \(V_{opt}\)」针对增长不可命名的故事股；本票增长由具名 capex 承载（A18），保留留存式 \((1-g_2/RONIC)/(r-g_2)\)，\(1/r\) 6.67× + 现金带 24.56 / 27.22 / 31.02 作对照。**CAPM 粗筛**：5 年周频 β 对恒指 **0.46**（yfinance 2021-09~2026-09，n=260）→ 4% + 0.46 × 5.5 + 港股 1 + 国别重 2 ≈ **9.5%**；扣 HKD 段中位偏移 −3pp 后与篮 7 差 2.5pp（≤ 3pp）；β 低是因为盈利是 Brent 的函数而非恒指的函数（与 CVX 同一条已知张力）。**解封触发**：NS-CMIC 除名 / 14032 撤销 → 回归篮 6，篮 6 对照带接管底牌 | active | 篮子复审 2026-09-18（留存三桶）；`gordon.BASKET_R`；Federal Register 2025-11-07（2025-19832）；OFAC NS-CMIC 名单 | `r_perp`；eval `check_r(r, "r_perp", 篮 7)`；篮子值变动是仓级决定，不在本票内改 |
# | A18 | **留存去向 → \(g_2\) = 4.5%（产量驱动，用户判断，2026-10-15 确认保留）**：capex 1,116 / 1,234 / 1,209 / 948 亿（2025–22）vs D&A 811 / 758 / 703 / 631；产量 528 → 777 mmboe（+5–8%/yr）→ ① 维持性 ≈ D&A；② 超出 D&A 的 305–500 亿是**增长性**（具名项目——圭亚那 Stabroek / 巴西 Buzios / 国内增储上产，2026 目标 780–800、十四五末 800+）→ \(g_2\) ≈ **4.5%**；③ 其余留存进超额现金（A19，按面值单列）。**2026-10-15 框架纠正**：旧版拍定的「增长留存率 25%」换成 \(b = g_2/RONIC\) = 20.5%（M 档 RONIC 21.96%，三档同用，见 A19）；旧版「现金 2,407 亿（毛口径）从不分配的国企现金市场按 0 计」撤销，改为扣债与已宣派 / 已除息股息后的超额现金按 λ 1 加回（A19）。cap = min(6%, 15% − 4%) = 6% ✓；\(r-g_2\) = 10.5% ≥ 2% ✓；③ 约束 2：\(g_2\) ≤ (1 − d) × RONIC = 10.60% ✓。**证伪**：2027 产量指引或实测产量增速移出 [3.5%, 5.5%] → 回对话 | active | 年报 p.73（capex）、现金流量表；历年业绩公告产量 | `g2`、`capex_fy25`、`da_fy25`；eval `check_g_cap(g2, r)`、约束 1 / 2、`check_branch` |
# | A19 | **超额现金单列 + 经营口径**（valuation-rules「经营价值与超额现金」，2026-10-15 框架纠正）：扩展口径净现金 2026-06-30 **2,581.8 亿**（货币资金 3,143.8 + 交易性金融资产 118.9 − 有息负债 601.7 − 租赁负债 79.1）− 类债项：已宣派未付 FY2025 末期股息 **227.6 亿** − 已除息（09-10）未付 2026 中期股息 **383.3 亿** − 经营所需现金锚 **0**（「扩展口径净现金 ÷ 收入」2016–25 最低 2016 年 −46.0%、2020 年 −10.3%，为负取下限 0）= 1,971.0 亿，× **归母比例 99.69%**（valuation-rules「经营价值与超额现金」① 归母份额：无子公司级现金披露 → 归母权益（扣已除息中期股息）8,177.2 ÷（+ 少数股东 25.05 亿），2026-10-16 框架纠正）= **超额现金 1,964.9 亿**（每股 4.134 元 = **4.84 港元**；占归母权益 23.0% ≥ 15% → 单列）。合同负债 6.1 亿是卖油预收，不扣。**经营利润**：税后收益 = 1,971.0 × 现金收益率 2.39%（FY2025）× (1 − 实际税率 28.0%) = **33.9 亿**，三档同扣 → 1,202.2 / 1,364.3 / 1,595.8 亿。**RONIC**（无卖方腿级回报 → 公司整体前瞻经营回报；分子年 FY2027、分母时点沿用现框架的 2026-06-30 权益、商誉保留在分母）：经营股权 = 归母权益 8,560.5 − 中期股息 383.3 − 超额现金（归母份额）1,964.9 = **6,212.3 亿** → M 档 **21.96%**，三档同用（沿用定稿的三档同一倍数，`cyclical` flat；L / H 档自身经营回报 19.35 / 25.69% 只披露，若按档取则倍数随油价上升、与周期股「反向或持平」形状相悖）。**不做防峰值**：分子是 `_AXIS.brent-oil` 机构前瞻油价三档（含 L 档 68）桥出的商品腿，周期风险已在轴里。持续失败不触发：FY2023–25 经营回报 21.86 / 21.87 / 18.83% 均 > r。**λ = 1**（用户确认）：资金受限——资产负债表无大额受限资金；困在海外子公司——香港注册、派息即用这些现金，无汇出受限证据；归属少数股东——少数股东权益 25.1 亿（0.3%）；近 5 年现金并购——2020–25 无「取得子公司支付的现金」，远低于归母权益 20%；具名政策性投资回报 < r——无（新能源无分部数据，无具名证据）。上周期留存主要投进增产（下行 i），长期囤积本身不构成证据。**留存拆分**（FY2020–24，分母经营利润合计 4,919.8 亿；来源含 2022 年 A 股 IPO 归母募资 321.0 亿）：分红 d **51.8%** / 现金积累 c **19.2%** / 经营再投资 i **40.3%** / 员工持股回购 0 / 还债 0（两端扩展口径净现金均在锚上）/ 现金并购 0；闭合差 −4.7pp（≤ 10pp）。经营口径派息率 = d + c = **71.0%**（`check_branch` 用）。|i − b_M| = 19.8pp > 10pp：窗口内产量年增 8.3%、经营利润从谷底回升，属扩张期，只披露。FY2020–25 对照：d 50.5% / c 25.3% / i 31.1%——2025 年与 2026H1 留存基本全进现金（经营股权 6,394.7 → 6,318.6 → 6,206.3 亿，未乘归母比例的旧口径）。**今昔**：M 档同等盈利月份的每股超额现金 1.37–3.37 元，今天 4.15 元，差异 > 1 倍——市场若对现金打折，历史经营倍数被高估、现模型偏乐观。**证伪 / 重看**：λ 证据清单任一项出现；超额现金被大额收购、政策性投资或特别分配消耗；派息政策 2027 年到期后改写 | active | 东方财富 F10 `600938` 合并资产负债表 / 利润表 / 现金流量表（2016–2026H1）；2025 年报、2026 中报（股息公告）；历史本地缓存 留存拆分 | `net_cash_ext_h1` / `div_declared` / `div_exdiv` / `c_ex` / `cash_yield` / `tax_eff` / `ret_*` / `payout_op` / `op_ret_fy*`；三档各加 4.84 港元 |
# | A20 | **经营价值与超额现金：时点对齐 / 窗口 / 稳态回报 / k（valuation-rules「经营价值与超额现金」②③④，2026-10-16 框架纠正；锚点 27.26 / 30.28 / 34.60 → 27.24 / 30.27 / 34.58，全部来自 A19 的归母比例 99.69%）**：① **时点对齐不折**：M 档分子是油价**周期中枢**（A4：Brent 75 = 2027 卖方 / EIA 中枢 = 上一轮周期 2020–2025 实测均价 74.1），属规则边界「分子是跨周期中枢不适用」，τ = 0——分子年与估值基准日 2026-06-30 重合，没有窗口期，窗口可分配利润随之为 0（不是另扣）；三档同用一个倍数，L / H 随 M 同处理；② **增长期资金缺口 0**：无窗口，且 2H26 剩余资本开支 500–600 亿远低于半年经营现金流（西南 / 东吴 2026 预测）；③ **稳态回报三段不适用（商品腿豁免）**：分子由 `_AXIS.brent-oil` 三档 Brent 桥出，永续段沿用前瞻 RONIC 21.96%；三档世界都写成持续（L「回到 2025 的 68 并长期化」、M 中枢、H「中断成为新常态」），不属「路过」；g2 4.5% 为用户确认值，不重解；④ **k**：本框架没有打折 k；多留部分 λ 1（A19） | active | A4 / A19；valuation-rules「经营价值与超额现金」②③ | 披露；τ = 0 |

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-5
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
MID_CYCLE_MAX = 1.15        # 中枢: current / mid-cycle above this makes the current print an upper-side coordinate
CYCLE_MEAN_DEV_MAX = 0.20   # 中枢: axis-bridged M vs own full-cycle (production-normalised) EPS mean
MONOTONIC_GAP = 0.03        # RONIC - r >= this is the monotonic regime (gordon._ROE_NEAR_R)
EXCESS_CASH_GATE = 0.15     # C_ex >= 15% of equity → excess-cash line exists (valuation-rules ①)
LAMBDA = 1.0                # A19: no named evidence that the cash cannot reach shareholders
FALLBACK_BASKET = 6         # A17: 篮 6 13% = 制裁折价消失 world, printed as a cross band
CYCLE_YEARS = ("2020", "2021", "2022", "2023", "2024")

REQUIRED = [
    "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "ni_h1_25", "ni_h1_26",
    "liq_fy25", "real_fy25", "liq_h1_26", "real_h1_26",
    "prod_2026_mid", "liq_share", "sales_ratio",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "payout_policy", "dps_fy25_cny", "dps_fy25_hkd", "dps_fy19_hkd", "dps_fy25_final_hkd", "dps_h1_26_hkd",
    "r_perp", "g2", "capex_fy25", "da_fy25",
    "net_cash_ext_h1", "div_declared", "div_exdiv", "minority_equity", "cash_yield", "tax_eff",
    "ret_d", "ret_c", "ret_i", "op_ret_fy23", "op_ret_fy24", "op_ret_fy25",
    "g_evid_min", "g_evid_max", "gd_peer_cvx", "gd_peer_tte", "gd_peer_1088",
    "pe_op_min", "pe_op_max", "pe_op_med", "pe_same_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "fcf_fy25",
    *[f"eps_fy{y}" for y in CYCLE_YEARS], *[f"prod_fy{y}" for y in CYCLE_YEARS], "prod_fy25",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 13).
NOT_FORMULA = (
    "pe_op_med", "pe_same_med", "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi",
    "tp_cons_h", "fcf_fy25", "dps_fy25_final_hkd", "dps_h1_26_hkd", "capex_fy25", "da_fy25",
    "ret_i", "op_ret_fy23", "op_ret_fy24", "op_ret_fy25",
    *[f"eps_fy{y}" for y in CYCLE_YEARS], *[f"prod_fy{y}" for y in CYCLE_YEARS], "prod_fy25",
)

def excess_cash(net_cash, declared, ex_dividend, equity, minority):
    parent = equity - ex_dividend
    parent_share = parent / (parent + minority)
    return (net_cash - declared - ex_dividend) * parent_share, parent_share


def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    inp = dict(inp)
    review_flags = []
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))

    leaked_p = [k for k in inp if k.startswith("p_")]
    if leaked_p:
        errors.append(f"probability fields in Inputs {leaked_p} (A2e-7a)")
    r, fx, pay, sh = inp["r_perp"], inp["fx_hkdcny"], inp["payout_policy"], inp["shares"]
    g2 = inp["g2"]
    baskets = {"r_perp": 7}

    # --- Step 1: numerators through the measured per-barrel elasticity, axis mount --
    brent = {"l": inp["brent_l"], "m": inp["brent_m"], "h": inp["brent_h"]}
    nib_fy25 = inp["ni_fy25"] / inp["liq_fy25"]
    nib_h1 = inp["ni_h1_26"] / inp["liq_h1_26"]
    k = (nib_h1 - nib_fy25) / (inp["real_h1_26"] - inp["real_fy25"])
    rho = inp["real_fy25"] / inp["brent_2025"]
    liq_2027 = inp["prod_2026_mid"] * inp["liq_share"] * inp["sales_ratio"]
    real = {t: rho * brent[t] for t in TIERS}
    ni = {t: liq_2027 * (nib_fy25 + k * (real[t] - inp["real_fy25"])) for t in TIERS}
    eps = {t: ni[t] * MN / sh for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}   # book ROE: axis §3 table + disclosure only
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 2: excess cash and the operating basis (A19) ---------------------------
    # Parent share (valuation-rules「经营价值与超额现金」① 归母份额): no subsidiary-level cash disclosure
    # -> parent equity / (parent + minority); the excess cash that enters the value, the numerator's
    # after-tax income and the RONIC base is the parent share only.
    eq_parent = inp["equity"] - inp["div_exdiv"]
    c_ex, parent_share = excess_cash(inp['net_cash_ext_h1'], inp['div_declared'], inp['div_exdiv'],
                                     inp['equity'], inp['minority_equity'])
    c_ex_all = inp["net_cash_ext_h1"] - inp["div_declared"] - inp["div_exdiv"]   # anchor 0
    if c_ex < EXCESS_CASH_GATE * inp["equity"]:
        review_flags.append('excess_cash_separation_threshold_unmet')
    c_inc = c_ex * inp["cash_yield"] * (1.0 - inp["tax_eff"])     # after-tax income, out of every numerator
    e_op = {t: ni[t] - c_inc for t in TIERS}
    eps_op = {t: e_op[t] * MN / sh for t in TIERS}
    op_eq = inp["equity"] - inp["div_exdiv"] - c_ex                 # 2026-06-30 book after the ex-div interim
    ronic_tier = {t: e_op[t] / op_eq for t in TIERS}       # per-tier returns: disclosure only
    ronic = {t: ronic_tier["m"] for t in TIERS}            # settled flat form: M-tier RONIC on every tier
    cps_hkd = c_ex * MN / sh / fx * LAMBDA

    # --- Step 3: mid-cycle numerator (A4) -----------------------------------------
    eps_ttm = (inp["ni_fy25"] - inp["ni_h1_25"] + inp["ni_h1_26"]) * MN / sh
    mid_ratio = eps_ttm / eps["m"]
    if mid_ratio > MID_CYCLE_MAX:
        review_flags.append('historical_middle_below_recent_earnings')
    h1_ann_ratio = 2.0 * inp["ni_h1_26"] * MN / sh / eps["m"]
    cycle_eps = [inp[f"eps_fy{y}"] for y in CYCLE_YEARS] + [inp["eps_fy25"]]
    cycle_prod = [inp[f"prod_fy{y}"] for y in CYCLE_YEARS] + [inp["prod_fy25"]]
    cycle_mean_raw = sum(cycle_eps) / len(cycle_eps)
    cycle_mean_norm = sum(e * inp["prod_2026_mid"] / p for e, p in zip(cycle_eps, cycle_prod)) / len(cycle_eps)
    cycle_dev = eps["m"] / cycle_mean_norm - 1.0
    if abs(cycle_dev) > CYCLE_MEAN_DEV_MAX:
        review_flags.append('historical_middle_differs_from_cycle_mean')

    # --- Step 4: ruler-form gate (A6) — Gordon reachable at the basket r ------------
    if 1.0 / r > inp["pe_op_max"] + 1e-9:
        review_flags.append('historical_operating_multiple_above_band')
    # The original written 45% minimum is documented with the payout input;
    # its source wording is not treated as a numeric computation interface.
    if not (0.0 < pay <= 1.0):
        errors.append(f"payout_policy {pay} outside (0, 1]")
    payout_fy25 = inp["dps_fy25_cny"] * sh / (inp["ni_fy25"] * MN)
    if abs(payout_fy25 - pay) > 0.02:
        review_flags.append('historical_payout_differs_from_policy')
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 5: growth 口径 — basket r, g cap, RONIC, constraint 2, branch ----------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"g2 {g2:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if not (inp["g_evid_min"] - 1e-9 <= g2 <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2 {g2} outside evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A9)")
    d_paid = max(payout_fy25, inp["ret_d"])
    for t in TIERS:
        if ronic[t] - r < MONOTONIC_GAP - 1e-12:
            errors.append(f"{t.upper()}: RONIC {ronic[t]:.2%} not in the monotone zone (RONIC − r < {MONOTONIC_GAP:.0%}) — revisit the domain")
        g_ceiling = (1.0 - d_paid) * ronic[t]
        if g2 > g_ceiling + 1e-9:
            errors.append(f"{t.upper()}: g2 {g2:.2%} > (1 − d {d_paid:.1%}) × RONIC {ronic[t]:.2%} = {g_ceiling:.2%} (③ 约束 2)")
        if g2 / ronic[t] > 1.0 - d_paid + 1e-9:
            errors.append(f"{t.upper()}: b = g/RONIC {g2 / ronic[t]:.1%} > 1 − d {1.0 - d_paid:.1%} (③ 约束 1)")
    if all(inp[f"op_ret_fy{y}"] < r for y in (23, 24, 25)) and ronic["m"] > r:
        errors.append("持续失败: FY2023–25 operating returns all < r — RONIC must stay at the forward value, never above it")
    inp['payout_op'] = round(inp['ret_d'] + inp['ret_c'], 3)
    if payout_fy25 >= NEAR_FULL_PAYOUT and g2 > 0.0:
        errors.append(f"g2 {g2:+.2%} is the retention branch but the company pays out {payout_fy25:.0%} (反解分支)")
    for t in TIERS:
        errors += check_branch(g2, ronic[t], r, inp["payout_op"], f"g2 ({t.upper()}, 经营口径派息率)")
    dps_cagr = (inp["dps_fy25_hkd"] / inp["dps_fy19_hkd"]) ** (1.0 / 6.0) - 1.0
    if dps_cagr <= 0.0 and g2 > 0.0:
        errors.append(f"same-world gate: own cross-cycle DPS CAGR {dps_cagr:+.2%} is not positive, a positive g2 is not usable (A11)")
    # DDM cross-check inputs stay internally consistent (A8) even though they never touch the anchors.
    peers = {"cvx": inp["gd_peer_cvx"], "tte": inp["gd_peer_tte"], "1088": inp["gd_peer_1088"]}
    for name, g in peers.items():
        if not (0.0 < g <= g_cap(r) + 1e-9):
            errors.append(f"gd_peer_{name} {g:+.4%} is not a usable same-regime sample (must be in (0, {g_cap(r):.0%}]) — drop it, never clip (A8)")
    peer_median = statistics.median(peers.values())
    g_d = round(peer_median, 4)

    # Guardrail: each generated operating multiple sits inside the realised operating band.
    pe = {t: perpetual_pe(g2, ronic[t], r) for t in TIERS}
    if not (pe["l"] >= pe["m"] - 1e-9 and pe["m"] >= pe["h"] - 1e-9):
        errors.append(f"multiple shape {pe['l']:.3f}/{pe['m']:.3f}/{pe['h']:.3f} is not reverse/flat (cyclical, 裁决顺序 ⑤)")
    for t in TIERS:
        if not (inp["pe_op_min"] - 1e-9 <= pe[t] <= inp["pe_op_max"] + 1e-9):
            review_flags.append('historical_operating_multiple_outside_band')
            break
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 6: anchors, ②-b ------------------------------------------------------
    def band(g: float = g2, rr: float = r) -> tuple[float, float, float]:
        return tuple(eps_op[t] * perpetual_pe(g, ronic[t], rr) / fx + cps_hkd for t in TIERS)  # type: ignore[return-value]

    L, M, H = band()
    if not (L < M < H):
        raise ValueError('; '.join(errors + [f'L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}']))
    A, B = cut_points(L, M, H)

    cons_mean = inp["eps_cons_fy27_mean"]
    cons_dev = eps["m"] / cons_mean - 1.0
    if cons_mean > eps["h"]:
        review_flags.append('historical_consensus_above_high_case')
    if abs(cons_dev) > CONS_DEV_MAX:
        review_flags.append('historical_consensus_differs_from_middle')
    consensus_below_mid = cons_mean < eps["m"]
    nib_cons = cons_mean * sh / MN / liq_2027
    brent_cons = (inp["real_fy25"] + (nib_cons - nib_fy25) / k) / rho

    # flat ladder (A2e-2c): all tiers at the M multiple, the numerator ladder must survive
    flat = tuple(eps_op[t] * pe["m"] / fx + cps_hkd for t in TIERS)
    errors += ladder("flat-multiple", *flat)

    if abs(inp["pe_op_med"] - pe["m"]) < 1e-9 or abs(inp["pe_same_med"] - pe["m"]) < 1e-9:
        errors.append("pe_op_med / pe_same_med leaked into the multiple path — they are comparison fields")
    leaked = [key for key in NOT_FORMULA if key not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    if errors:
        raise ValueError('; '.join(errors))
    ddm = tuple(pay * eps[t] / (r - g_d) / fx for t in TIERS)
    zero_g = tuple(eps_op[t] / r / fx + cps_hkd for t in TIERS)
    fallback = band(rr=basket_r(FALLBACK_BASKET))
    own_med = tuple(eps_op[t] * inp['pe_op_med'] / fx + cps_hkd for t in TIERS)
    same_med = tuple(eps_op[t] * inp['pe_same_med'] / fx + cps_hkd for t in TIERS)
    g_edge, well = implied_g_retaining(inp['pe_op_max'], ronic['m'], r)
    b = {t: g2 / ronic[t] for t in TIERS}
    excess = 1.0 - b['m'] - payout_fy25
    bps = inp['equity'] * MN / sh
    tp_pe_op = (inp['tp_cons_h'] * fx - c_ex * MN / sh) / eps_op['m']
    tp_r = g2 + (1.0 - g2 / ronic['m']) / tp_pe_op
    g1 = (inp['eps_fy2022'] / inp['eps_fy2020']) ** .5 - 1
    pe_rec = recovery_two_stage_pe(g1, 2, g2, ronic['m'], r)
    la, ma, ha = L * fx, M * fx, H * fx
    fa, fb = cut_points(la, ma, ha)
    sensitivity = {'growth_low': band(g=g2-.01), 'growth_high': band(g=g2+.01),
                   'basket4': band(rr=basket_r(4)),
                   'cash_zero': tuple(x - cps_hkd for x in (L, M, H)),
                   'cash_half': tuple(x - cps_hkd/2 for x in (L, M, H))}
    def band_rf(dr):
        return band(rr=r + dr)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0), (L, M, H))):
        raise ValueError('rate sensitivity base differs from anchors')
    result = {'ticker': '0883.HK', 'currency': 'HKD',
            'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
            'framework_as_of': None, 'historical_research_as_of': '2026-10-16', 'historical_framework_as_of':'2026-10-16',
            'anchors': dict(zip('LMH', (L, M, H))), 'option': None, 'candidate': None,
            'review_flags': review_flags,
            'brent': brent, 'nib_fy25': nib_fy25, 'nib_h1': nib_h1, 'k': k, 'rho': rho,
            'liq_2027': liq_2027, 'real': real, 'ni': ni, 'eps': eps, 'roe': roe,
            'eq_parent': eq_parent, 'parent_share': parent_share, 'c_ex_all': c_ex_all,
            'c_ex': c_ex, 'c_inc': c_inc, 'e_op': e_op, 'eps_op': eps_op, 'op_eq': op_eq,
            'ronic_tier': ronic_tier, 'ronic': ronic, 'cps_hkd': cps_hkd, 'eps_ttm': eps_ttm,
            'mid_ratio': mid_ratio, 'h1_ann_ratio': h1_ann_ratio, 'cycle_eps': cycle_eps,
            'cycle_prod': cycle_prod, 'cycle_mean_raw': cycle_mean_raw, 'cycle_mean_norm': cycle_mean_norm,
            'cycle_dev': cycle_dev, 'payout_fy25': payout_fy25, 'd_paid': d_paid, 'dps_cagr': dps_cagr,
            'g_d': g_d, 'peers': peers, 'peer_median': peer_median, 'pe': pe,
            'L': L, 'M': M, 'H': H, 'A': A, 'B': B, 'cons_mean': cons_mean,
            'cons_dev': cons_dev, 'consensus_below_mid': consensus_below_mid,
            'nib_cons': nib_cons, 'brent_cons': brent_cons, 'flat': flat,
            'ddm': ddm, 'zero_g': zero_g, 'fallback': fallback, 'own_med': own_med,
            'same_med': same_med, 'g_edge': g_edge, 'well': well, 'b': b, 'excess': excess,
            'bps': bps, 'tp_pe_op': tp_pe_op, 'tp_r': tp_r, 'g1': g1, 'pe_rec': pe_rec,
            'la': la, 'ma': ma, 'ha': ha, 'fa': fa, 'fb': fb, 'sensitivity': sensitivity}
    if rate_inputs is not None:
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp':r}, band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs, base_anchors=(L,M,H)))
    return result


def calculate(context):
    rungs = context['axes']['brent']['rungs']
    selected = {f'brent_{t}':rungs[t.upper()] for t in TIERS}
    result = evaluate({**INPUTS, **selected}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs':INPUTS, 'brent':selected, 'cycle_years':CYCLE_YEARS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price':'HKD_PER_SHARE'}
    result['segments'] = {
        'operating': {'unit':'HKD_PER_SHARE', 'values': {t:result['anchors'][t] - result['cps_hkd'] for t in 'LMH'}},
        'cash': {'unit':'HKD_PER_SHARE', 'values':dict.fromkeys('LMH',result['cps_hkd'])}}
    result['key_parameters'] = {
        'discount_rate': {'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_perp'])},
        'growth_rate': {'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g2'])},
        'forward_return': {'unit':'RATIO','values':{t.upper():result['ronic'][t] for t in TIERS}},
    }
    result['review_flags'] += ['historical_cash_availability_unverified',
                               'historical_oil_sensitivity_and_production_unverified',
                               'historical_dividend_policy_and_country_risk_unverified']
    if result['consensus_below_mid']:
        result['review_flags'].append('historical_consensus_below_middle')
    return result
