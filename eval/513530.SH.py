"""Historical 930914 total-return channel snapshot, not current NAV."""
from __future__ import annotations
import math
import pandas as pd
from lib.etf import channel
from lib.value100_inputs import normalize_index_history
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('etf', 'value100_inputs', 'zones', 'partial_basis'), 'axes': {}}
BASELINE_LOCAL = '3140490180c15425d71d43f39cfbc257918153697566ec5ca2ddb59994c06a94'
BASE_FIELDS = ('nav_ref', 'idx_cur', 'chan_l_idx', 'chan_m_idx', 'chan_h_idx')
# 2015-12-01 through 2026-09-17: log-linear fit after 2σ removal;
# the original external index cache disagreed with this documented snapshot.
# Values below retain the old stated, rounded index levels, not a new fit.
INPUTS = {
    'nav_ref': 1.587,  # 折算基准：2026-09-11 场内收盘（Longbridge）作 NAV 代理，k = nav_ref ÷ idx_cur；对账尺持股数 / 透视盈利也以它为同日快照（Formula 口径）；与 idx_cur 同日（2026-09-17）的 ETF NAV `待补`（补齐前锚点沿用此值；QDII 场内折溢价随之消除） 2026-09-11
    'fee_drag': 0.94,  # \(1-0.006/0.10\) 合同 0.60%
    'pe_now': 11.27,  # **指数**滚动 PE，中证 `index-perf` 日频（A1；透视 TTM 盈利 = NAV ÷ 本值） 2026-09-11
    'r_perp': 0.1,  # 篮 4 龙头制造：对账尺 SOTP 的 Gordon r（汇丰 / 中银香港 PB-ROE 与周期腿 flat 倍数在此 r 下生成；只披露，通道主尺无 r）；look-through P 加权 ≈11.7%（金融 → 篮 5、能源 / 工业 → 篮 6、残余 → 篮 4，A13）只作 hurdle 对照；利率轴按 HKD 仓规；2026-09-20
    'g2_bank': 0.03,  # 银行永续 g（汇丰 / 中银香港 PB-ROE）；来源层级：无同业锚，与 `600036.SH` 同档 A3
    'payout_ene': 0.569,  # **能源腿实付派息率**（共享腿：神华 / 中海油 / 中石油 / 中石化 四只 FY2025 DPS ÷ 基本 EPS 盈利加权，与 `520900.SH` 同一腿，eval 打印差异）；本票袖套三名子集自算 54.2%（eval 由 `*_dps25` / `*_eps25` 复算打印，作交叉，A2） FY2025
    'roe_ene': 0.126,  # **能源腿前瞻 ROE_M**（共享腿四只 FY2027E 均值 ÷ **2027 年初 BPS**——2Q26 账面按 \(b_1=g_2/ROE\) 滚过 2H26 未入账 EPS，与 g₂ 联立的不动点，`520900.SH` 复算、本票抄值，A14；旧口径 ÷ 2Q26 BPS 12.9%；\ ROE−r\
    'g2_ene': 0.0543,  # 能源腿永续 g，**留存分支** = (1 − payout_ene) × roe_ene，roe_ene 又按 g₂ 滚账面 → 联立不动点 5.435%（`520900.SH` 迭代；本票 eval ±0.0005；旧口径 5.56%，A14）；`check_branch` 通过；**与 `520900.SH` 同值**；三名子集自算 6.27% → 截顶 6% = `g_evid_max`；SOTP 旧版 v2 −1.11%（全派息萎缩）已废 A2
    'payout_ind': 0.618,  # 工业腿实付派息率 = 中远 50.3% / 海丰 85.5%（含 FY2025 特别息）/ 重汽 58.1% 盈利加权（eval 复算 ±0.005）；< 80% → 留存 FY2025
    'roe_ind': 0.21,  # 工业腿前瞻 ROE_M = 中远 8.1% / 海丰 43.5% / 重汽 21.5% 盈利加权；单调区 2026-09-13
    'g2_ind': 0.0,  # 工业腿永续 g，**BLOCKED 腿的具名零增长解**（留存 62% 却萎缩：共识 FY27E = TTM 的 0.92、中远 EPS / DPS FY22→25 −33%/yr → 两条分支皆否；留存分支 +8.0% → 截顶 6% → 17.9× 只作对照，A2）→ 10×；与 `520900.SH` 同值；SOTP 旧版 v2 −1.36% 已废 A2
    'g_evid_min': 0.0451,  # 能源腿 \(g_2\) 证据区间下沿 = `930914` 指数派息率交叉 (1 − `idx_dy` × `pe_now`) × roe_ene = (1 − 64.2%) × 12.6%（eval 复算 ±0.0005）；zone 在区间内须不变；与 `520900.SH` 同值 2026-09-21
    'g_evid_max': 0.06,  # 证据区间上沿 = 上限 6%：三名子集自算 6.27%（2027 年初口径 ROE 13.7%，A14）与 `931722` 指数派息率交叉 5.99% 都截到此（eval 复算子集值） 2026-09-21
    'idx_dy': 0.057,  # `930914` 指数股息率（中证单张 08-31）；只进指数派息率交叉与 DDM 对照，不入锚点 2026-08-31
    'etf_dps_ttm': 0.1301,  # ETF 自身 TTM 每份实派 CNY（Longbridge 2026-09-15 `dps_rate` × 当日收盘反算的每份金额；含 QDII 税率差与分红节奏，**不当分子**）；只进 DDM 对照 2026-09-15
    'g2_res': 0.0,  # 残余腿永续 g → `perpetual_pe` = 10×；无同业锚 仓规
    'w_hsbc': 0.0396,  # 汇丰 2026-08-31
    'pb_hsbc': 2.066,  # 汇丰现 PB（Longbridge，09-11 收盘 163.3） 2026-09-11
    'roe_hsbc': 0.133,  # FY2025 RoTE 年报
    'w_bochk': 0.0382,  # 中银香港 2026-08-31
    'pb_bochk': 1.535,  # 中银香港现 PB（Longbridge，09-11 收盘 52.30） 2026-09-11
    'roe_bochk': 0.12,  # 工作假设（Longbridge 2026H1 TTM 11.79% 相符，A4） A4
    'w_feh': 0.0398,  # 远东宏信 2026-08-31
    'w_fin_rest': 0.2474,  # 其余金融 0.365−上列
    'w_ind': 0.259,  # 工业 2026-08-31
    'w_ene_rest': 0.1523,  # 能源 − 中煤 0.191−0.0387
    'w_cc': 0.0387,  # 中煤 2026-08-31
    'w_res': 0.185,  # 残余（通信等） 1−上列
    'pe_ind': 10.0,  # 工业 fair = `perpetual_pe(g2_ind = 0, ·, r_perp)` = 1/r，flat（eval 复算；对账尺 r 10%，`520900.SH` 该腿按其篮子 r 生成、不再同值） A2
    'pe_ene': 12.46,  # 能源 fair = `perpetual_pe(g2_ene, roe_ene, r_perp)` = (1 − 0.0543/0.126)/(0.10 − 0.0543)，flat（eval 复算 ±0.05；对账尺 r 10%，`520900.SH` 同一腿按其篮子 r 生成、不再同值；A14 前 12.82） 2026-09-21
    'pe_res': 10.0,  # 残余 = `perpetual_pe(g2_res, ·, r_perp)`（eval 复算） 仓规
    'eps_ind_l': 0.731,  # 工业分子 / TTM：中远 / 海丰 / 重汽 FY2027E 共识**下沿**，盈利加权（eval 复算 ±0.005，A7） 2026-09-13
    'eps_ind_m': 0.916,  # FY2027E 共识均值，盈利加权 2026-09-13
    'eps_ind_h': 1.042,  # FY2027E 共识**上沿**，盈利加权 2026-09-13
    'eps_ene_l': 0.843,  # 能源其余分子 / TTM：神华 / 中海油 / 中石油 FY2027E 下沿，盈利加权（eval 复算） 2026-09-13
    'eps_ene_m': 1.032,  # FY2027E 均值 2026-09-13
    'eps_ene_h': 1.178,  # FY2027E 上沿 2026-09-13
    'cosco_fy27_l': 0.78,  # 中远海控 FY2027E EPS 下沿 CNY（yfinance 6 家） 2026-09-13
    'cosco_fy27_m': 1.259,  # 均值 同上
    'cosco_fy27_h': 1.484,  # 上沿 同上
    'cosco_ttm': 1.976,  # TTM EPS CNY（2.31 HKD × 0.8552） 2026-09-11
    'cosco_w': 0.069,  # 指数权重 2026-08-31
    'cosco_pe': 8.155,  # 09-11 收盘 TTM PE（Longbridge） 2026-09-11
    'cosco_dps25': 1.0,  # 中远海控 FY2025 DPS CNY = 中期 0.56（除净 2025-10-24）+ 末期 0.44（2026-06-26）；Longbridge `dividend` 601919.SH FY2025
    'cosco_eps25': 1.99,  # 中远 FY2025 基本 EPS CNY；Longbridge IS af → 派息率 50.3%（FY2023–25 恒 50%） FY2025
    'cosco_bps': 15.551,  # 中远 BPS CNY；yfinance `bookValue` 601919.SS → 前瞻 ROE = 1.259/15.551 = 8.1% 2026-09-15
    'cosco_eps22': 6.78,  # 中远 FY2022 基本 EPS CNY（上一轮集运峰值）；实测方向：FY22→25 CAGR −33%/yr（A2） FY2022
    'cosco_dps22': 3.4,  # 中远 FY2022 全年 DPS CNY = 中期 2.01 + 末期 1.39；FY22→25 CAGR −33%/yr（A2） FY2022
    'sitc_fy27_l': 0.41,  # 海丰国际 FY2027E EPS 下沿 USD（9 家） 2026-09-13
    'sitc_fy27_m': 0.457,  # 均值 同上
    'sitc_fy27_h': 0.5,  # 上沿 同上
    'sitc_ttm': 0.473,  # TTM EPS USD（3.69 HKD ÷ 7.8） 2026-09-11
    'sitc_w': 0.059,  # 指数权重 2026-08-31
    'sitc_pe': 12.353,  # 09-11 TTM PE 2026-09-11
    'sitc_dps25': 3.0,  # 海丰国际 FY2025 全年 DPS HKD = 中期 1.30（2025-08-28）+ 特别 0.70（2026-01-05）+ 末期 1.00（2026-04-24）；Longbridge 1308.HK FY2025
    'sitc_eps25': 3.509,  # 海丰 FY2025 基本 EPS HKD（Longbridge IS af，USD 报表折 HKD）→ 派息率 85.5%（不含特别息 65.5%） FY2025
    'sitc_bps': 1.0502,  # 海丰 BPS USD（yfinance 8.1915 HKD ÷ 7.8）→ 前瞻 ROE = 0.457/1.0502 = 43.5% 2026-09-15
    'sinotruk_fy27_l': 3.25,  # 中国重汽 FY2027E EPS 下沿 CNY（9 家） 2026-09-13
    'sinotruk_fy27_m': 3.672,  # 均值 同上
    'sinotruk_fy27_h': 4.16,  # 上沿 同上
    'sinotruk_ttm': 2.548,  # TTM EPS CNY（2.98 HKD × 0.8552） 2026-09-11
    'sinotruk_w': 0.05,  # 指数权重 2026-08-31
    'sinotruk_pe': 12.365,  # 09-11 TTM PE 2026-09-11
    'sinotruk_dps25': 1.62,  # 中国重汽 FY2025 全年 DPS HKD = 中期 0.74（2025-09-09）+ 末期 0.88（2026-07-09）；Longbridge 3808.HK FY2025
    'sinotruk_eps25': 2.787,  # 重汽 FY2025 基本 EPS HKD（Longbridge IS af，CNY 报表折 HKD）→ 派息率 58.1% FY2025
    'sinotruk_bps': 17.094,  # 重汽 BPS CNY（yfinance 19.988 HKD × 0.8552）→ 前瞻 ROE = 3.672/17.094 = 21.5% 2026-09-15
    'shenhua_fy27_l': 2.57,  # 中国神华 FY2027E EPS 下沿 CNY（7 家） 2026-09-13
    'shenhua_fy27_m': 2.823,  # 均值 同上
    'shenhua_fy27_h': 3.139,  # 上沿 同上
    'shenhua_ttm': 2.694,  # TTM EPS CNY（3.15 HKD × 0.8552） 2026-09-11
    'shenhua_w': 0.043,  # 指数权重 2026-08-31
    'shenhua_pe': 15.852,  # 09-11 TTM PE 2026-09-11
    'shenhua_dps25': 2.01,  # 神华 FY2025 全年 DPS CNY = 中期 0.98（2025-11-10）+ 末期 1.03（2026-07-13）；Longbridge 601088.SH FY2025
    'shenhua_eps25': 2.7288,  # 神华 FY2025 基本 EPS CNY → 派息率 73.7% FY2025
    'shenhua_bps': 21.173,  # 神华 2Q26 BPS CNY（yfinance 601088.SS；= Longbridge BS saf 2026H1）→ 账面滚动起点；旧口径 ROE 13.3%，2027 年初口径 13.0%（A14） 2026-06-30
    'shenhua_fy26_m': 2.93274,  # 神华 FY2026E 共识均值 EPS CNY（yfinance 5 家）；只用于 2H26 未入账 EPS = 2.933 − 1.448 = 1.485（A14；与 `520900.SH` 同值） 2026-09-21
    'shenhua_h1_26': 1.4479,  # 神华 2026H1 基本 EPS CNY（已入账；Longbridge IS saf 601088.SH） 2026-06-30
    'cnooc_fy27_l': 2.51,  # 中海油 FY2027E EPS 下沿 CNY（13 家） 2026-09-13
    'cnooc_fy27_m': 3.07,  # 均值 同上
    'cnooc_fy27_h': 3.451,  # 上沿 同上
    'cnooc_ttm': 2.916,  # TTM EPS CNY（3.41 HKD × 0.8552） 2026-09-11
    'cnooc_w': 0.041,  # 指数权重 2026-08-31
    'cnooc_pe': 7.272,  # 09-11 TTM PE 2026-09-11
    'cnooc_dps25': 1.1449,  # 中海油 FY2025 DPS CNY（A 股口径）= 中期 0.6661 + 末期 0.4788；Longbridge 600938.SH FY2025
    'cnooc_eps25': 2.5685,  # 中海油 FY2025 基本 EPS CNY → 派息率 44.6%（公司 2025–27 承诺 ≥45%） FY2025
    'cnooc_bps': 18.011,  # 中海油 2Q26 BPS CNY（yfinance 600938.SS；= Longbridge BS saf）→ 旧口径 ROE 17.0%，2027 年初口径 16.6%（A14） 2026-06-30
    'cnooc_fy26_m': 3.39294,  # 中海油 FY2026E 共识均值 EPS CNY（yfinance 4 家）；2H26 未入账 = 3.393 − 1.806 = 1.587（A14） 2026-09-21
    'cnooc_h1_26': 1.8056,  # 中海油 2026H1 基本 EPS CNY（Longbridge IS saf 600938.SH） 2026-06-30
    'petrochina_fy27_l': 0.72,  # 中石油 FY2027E EPS 下沿 CNY（12 家） 2026-09-13
    'petrochina_fy27_m': 0.953,  # 均值 同上
    'petrochina_fy27_h': 1.13,  # 上沿 同上
    'petrochina_ttm': 0.958,  # TTM EPS CNY（1.12 HKD × 0.8552） 2026-09-11
    'petrochina_w': 0.039,  # 指数权重 2026-08-31
    'petrochina_pe': 9.014,  # 09-11 TTM PE 2026-09-11
    'petrochina_dps25': 0.47,  # 中石油 FY2025 DPS CNY = 中期 0.22 + 末期 0.25；Longbridge 601857.SH FY2025
    'petrochina_eps25': 0.8596,  # 中石油 FY2025 基本 EPS CNY → 派息率 54.7% FY2025
    'petrochina_bps': 8.95,  # 中石油 2Q26 BPS CNY（yfinance 601857.SS；= Longbridge BS saf）→ 旧口径 ROE 10.6%，2027 年初口径 10.4%（A14） 2026-06-30
    'petrochina_fy26_m': 0.91,  # 中石油 FY2026E 共识均值 EPS CNY（yfinance **1 家**，薄；2H26 未入账 = 0.91 − 0.568 = 0.342，A14） 2026-09-21
    'petrochina_h1_26': 0.5679,  # 中石油 2026H1 基本 EPS CNY（Longbridge IS saf 601857.SH） 2026-06-30
    'eps_res_l': 0.95,
    'eps_res_m': 1.0,
    'eps_res_h': 1.05,
    'k_bank_l': 0.9,  # 银行分子
    'k_bank_m': 1.0,
    'k_bank_h': 1.05,
    'k_feh_l': 0.7,  # 租赁信贷 A5
    'k_feh_m': 1.0,
    'k_feh_h': 1.1,
    'px_cc': 11.14,  # 中煤 2026-09-11 收盘 HKD（同日快照） 2026-09-11
    'cc_l': 9.05,  # `1898.HK` L（该票 2026-09-20 现值：篮 6 周期商品 r 13%、flat 1/r 7.69× + 项目价值 1.14，L = 2025H1 实测售价 436；eval 逐格校验，源框架一动即红） 2026-09-20
    'cc_m': 12.51,  # M（= 中枢：FY2019–25 七年实测售价均值 499） 同上
    'cc_h': 13.04,  # H（≥2 家港口价簇 800 × 传导率 0.5 → 508.7） 同上
    'cc_h_cand': 15.73,  # `1898.HK` 候选带 H′（高盛单家港口价 950）；只进本票 SOTP 候选带（eval 打印，A8） 2026-09-20
    'cnooc_ni_l': 249.56,  # 中海油 2020 净利（亿）；报表年 regime 只作压力坐标（A11） 与 520900 同
    'cnooc_ni_m': 1220.82,  # 2025 同上
    'cnooc_ni_h': 1416.77,  # 2022 同上
    'shenhua_ni_l': 391.7,  # 神华 2020 净利（亿） 同上
    'shenhua_ni_m': 528.49,  # 2025 同上
    'shenhua_ni_h': 696.26,  # 2022 同上
    'petrochina_ni_l': 190.06,  # 中石油 2020 归母净利（亿 CNY）；Longbridge af 2026-09-14
    'petrochina_ni_m': 1573.18,  # 2025 同上
    'petrochina_ni_h': 1487.43,  # 2022 同上
    'sinopec_ni_l': 334.43,  # 中石化 2020 归母净利（亿 CNY）；Longbridge af 2026-09-14
    'sinopec_ni_m': 324.76,  # 2025 同上
    'sinopec_ni_h': 669.33,  # 2022 同上
    'cosco_ni_l': 238.6,  # 中远 2023 净利（亿 CNY）；报表年 regime 压力坐标（与 520900 同） 年报
    'cosco_ni_m': 308.7,  # 2025 年报
    'chan_slope': 0.105,  # **通道主尺**：930914 全收益（H20914）对数线性趋势斜率（通道窗 = 全窗 2015-12-01～2026-09-17，剔 2σ 重拟）= 实测中枢回报 2026-09-17
    'chan_slope_2019': 0.099,  # 子窗斜率 2019 起 2026-09-17
    'chan_slope_2021': 0.141,  # 子窗斜率 2021 起（与全窗差 3.6pp < 5pp，regime 断裂边缘不触发） 2026-09-17
    'chan_sigma': 0.173,  # 残差 σ（四只 ETF 里最宽） 2026-09-17
    'chan_l_idx': 8362.0,  # 通道 L = 趋势 × exp(残差 p10)，指数点 2026-09-17
    'chan_m_idx': 10135.0,  # 通道 M = 趋势现值，指数点 2026-09-17
    'chan_h_idx': 12909.0,  # 通道 H = 趋势 × exp(残差 p90)，指数点 2026-09-17
    'idx_cur': 11543.7,  # 折算日指数值（全收益 H20914）；k = nav_ref ÷ idx_cur（`nav_ref` 取 09-11 收盘，与指数 09-17 不同日；QDII 折溢价未剔除，见 Outputs 敏感性） 2026-09-17
    'pe_1y_lo': 9.42,  # E 侧护栏：指数滚动 PE 近一年带下沿 2025-09~2026-09
    'pe_1y_hi': 11.43,  # E 侧护栏：近一年带上沿；2026-09-11 PE 11.27 贴顶 = 偏贵 2025-09~2026-09
    'dy_10y_p25': 0.065,  # E 侧护栏：指数股息率十年 p25（篮子归属决策记录） 十年
    'dy_10y_med': 0.076,  # E 侧护栏：十年中位 十年
    'dy_10y_p75': 0.089,  # E 侧护栏：十年 p75；2023 特别息顶 10.8% 十年
    'beta_rate_prior': -18.0,  # 利率轴 β 先验 = −1/DY（−1/5.7%）；HKD 10Y 待 `_AXIS.rates.md` 先验
}

def calculate(context):
    if any(not math.isfinite(INPUTS[k]) or INPUTS[k] <= 0 for k in BASE_FIELDS):
        raise ValueError('channel reference fields must be finite and positive')
    flags = ['historical_index_fit_cache_conflict', 'historical_nav_index_dates_mismatch']
    status = 'historical_snapshot'
    scale = INPUTS['nav_ref'] / INPUTS['idx_cur']
    values = tuple(INPUTS[f'chan_{t}_idx'] * scale for t in 'lmh')
    if context.get('external_inputs') is None:
        flags.append('historical_index_observations_unavailable')
    else:
        try:
            data = normalize_index_history(context['external_inputs'], 'H20914')
            selected = {date: value for date, value in data.items() if '2015-12-01' <= date <= '2026-09-17'}
            if len(selected) < 2 or max(selected) != '2026-09-17':
                raise ValueError('historical index window incomplete')
            index = pd.Series(selected, dtype=float)
            index.index = pd.to_datetime(index.index)
            fitted = channel(index.sort_index())
            if not math.isfinite(fitted['cur']) or fitted['cur'] <= 0:
                raise ValueError('invalid fitted index level')
            recalculated = tuple(fitted[t] * INPUTS['nav_ref'] / fitted['cur'] for t in 'LMH')
            if not all(math.isfinite(v) for v in recalculated) or not recalculated[0] < recalculated[1] < recalculated[2]:
                raise ValueError('invalid fitted channel')
            values = recalculated
            status = 'recalculated_historical_index'
            if min(selected) > '2015-12-01':
                flags.append('historical_index_window_incomplete')
            if abs(fitted['cur'] - INPUTS['idx_cur']) > .5:
                flags.append('historical_index_level_differs')
        except (ValueError, TypeError, KeyError, IndexError, ArithmeticError):
            flags.append('historical_index_observations_invalid')
    if not values[0] < values[1] < values[2]:
        raise ValueError('channel anchors must be ordered')
    A, B = cut_points(*values)
    return {'ticker': '513530.SH', 'currency': 'CNY', 'units': {'price': 'CNY_PER_FUND_UNIT'},
            'valuation_as_of': None, 'framework_as_of': None,
            'historical_valuation_as_of': None, 'historical_research_as_of': '2026-09-27',
            'historical_index_as_of': '2026-09-17', 'historical_nav_proxy_as_of': '2026-09-11',
            'anchors': dict(zip('LMH', values)), 'cut_points': {'A': A, 'B': B},
            'candidate': None, 'option': None,
            'fund_reference_status': 'historical_index_cache_conflict', 'historical_index_source_status': status,
            'review_flags': flags,
            'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                {'base_inputs': {k: INPUTS[k] for k in BASE_FIELDS}}, BASELINE_LOCAL)}
