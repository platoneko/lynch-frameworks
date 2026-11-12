"""Historical ETF look-through: prior constituent snapshots and values."""
from __future__ import annotations
import math
from lib.etf_lookthrough import scale
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('etf_lookthrough', 'zones', 'partial_basis'), 'axes': {},
                'peers': {'shenhua': '1088.HK', 'cnooc': '0883.HK', 'petrochina': '0857.HK'}}
BASELINE_LOCAL = '0483d74be9107eee65cd600467536a11c06eb39d84ae3f7eecde1a797b301c30'
BASE_FIELDS = ('nav_ref', 'fee_drag', 'r_ene', 'r_mk', 'fx_hkdcny', 'pe_now', 'pe_ind', 'pe_ann', 'w_ene', 'w_resc', 'w_ind', 'w_ann', 'sinopec_seg6', 'sinopec_seg4', 'shenhua_w', 'shenhua_px', 'cnooc_w', 'cnooc_px', 'petrochina_w', 'petrochina_px', 'sinopec_w', 'sinopec_px', 'shenhua_fw_l', 'shenhua_fw_m', 'shenhua_fw_h', 'cnooc_fw_l', 'cnooc_fw_m', 'cnooc_fw_h', 'petrochina_fw_l', 'petrochina_fw_m', 'petrochina_fw_h', 'sinopec_fy27_l', 'sinopec_fy27_m', 'sinopec_fy27_h', 'eps_ind_l', 'eps_ind_m', 'eps_ind_h', 'eps_ann_l', 'eps_ann_m', 'eps_ann_h')
ENE_NAMES = ('shenhua', 'cnooc', 'petrochina', 'sinopec')
FW_NAMES = {'shenhua': '1088.HK', 'cnooc': '0883.HK', 'petrochina': '0857.HK'}
# The old three constituent valuations and prices are historical snapshots;
# new peer results are compared, not retroactively inserted into the 2026 mix.
INPUTS = {
    'nav_ref': 1.011,  # 折算基准：2026-09-11 场内收盘（Longbridge）作 NAV 代理——透视盈利 = NAV × w ÷ `pe_now`（与 `pe_now` / `*_pe` 同日快照，Formula 口径）；通道对照 k = nav_ref ÷ idx_cur；与 idx_cur 同日（2026-09-17）的 ETF NAV `待补`（补齐前锚点沿用此值） 2026-09-11
    'fee_drag': 0.98,  # \(1-0.002/0.10\)（A7） 合同
    'pe_now': 9.72,  # **指数**滚动 PE（禁前十大），中证 `index-perf` 日频（A1；透视 TTM 盈利 = NAV ÷ 本值） 2026-09-11
    'r_ene': 0.13,  # 篮 6 周期商品 / 小盘：能源腿（四只油煤央企）与残余周期（代理能源）的 Gordon r——盈利是油价 / 煤价函数（A10）；值 = `gordon.BASKET_R[6]` 2026-09-20
    'r_ind': 0.13,  # 篮 6 周期商品 / 小盘：工业腿（集运，中远代理）的 Gordon r——运价周期（A10；另一口径篮 4 10% 待裁，只作对照） 2026-09-20
    'r_ann': 0.075,  # 篮 2 管制公用事业：年金腿（电信，移动代理）的 Gordon r——牌照管制、准公用资费（A10） 2026-09-20
    'g2_ann': 0.0,  # 年金腿永续 g → `perpetual_pe` = 1/r = 13.33×；来源层级：无同业锚（电信同业反解 −2.4% 只作交叉，A2） 仓规
    'payout_ene': 0.569,  # **能源腿实付派息率** = 四只 FY2025 DPS ÷ 基本 EPS 的盈利加权（\(w_k/PE_k\)，A2；eval 由 `*_dps25` / `*_eps25` 复算 ±0.005）；**共享腿，与 `513530.SH` 同值** FY2025
    'roe_ene': 0.126,  # **能源腿前瞻 ROE_M** = 四只 FY2027E 均值 EPS ÷ **2027 年初 BPS**（2Q26 `*_bps` 按 \(b_1 = g_2/ROE\) 滚过 2H26 未入账 EPS = `*_fy26_m` − `*_h1_26`，A11）的盈利加权（eval 由 `*_fy27_m` / `*_bps` / `*_fy26_m` / `*_h1_26` 在 g₂ 不动点上复算 ±0.005；旧口径 ÷ 2Q26 BPS 12.9%）；\ ROE−r\
    'g2_ene': 0.0543,  # 能源腿永续 g，**留存分支** = (1 − payout_ene) × roe_ene，roe_ene 又按 g₂ 滚账面 → eval 迭代到联立不动点 5.435%（±0.0005；旧口径 5.56%，A11）；`check_branch` 通过；cap = min(6%, r_ene − 4%) = 6% 未触；**与 `513530.SH` 同值**（同一腿的政策读数；倍数各按自身 r 生成）；旧版全派息萎缩 −1.11% 已废 A2
    'payout_ind': 0.503,  # 工业腿实付派息率 = 中远 FY2025 DPS 1.00 ÷ EPS 1.99（本票工业腿以中远为代理，A4）；< 80% → 留存 FY2025
    'roe_ind': 0.081,  # 工业腿前瞻 ROE_M = 中远 FY2027E 均值 1.259 ÷ BPS 15.551；在 r 13% 下峰形区 2026-09-13
    'g2_ind': 0.0,  # 工业腿永续 g，**BLOCKED 腿的具名零增长解**（留存 50% 却萎缩：共识 FY27E = TTM 的 0.64、中远 EPS / DPS FY22→25 −33%/yr → 两条分支皆否；留存分支 +4.03% 只作对照，A2）→ 1/r = 7.69×；与 `513530.SH` 同值；旧版 −1.36% 已废 A2
    'g_evid_min': 0.0451,  # 能源腿 \(g_2\) 证据区间下沿 = `930914` 指数派息率交叉（5.7% × 11.27 = 64.2% 派息）× roe_ene 12.6%（由 `513530.SH` 复算；本票与之同值）；两端对照带 eval 打印 2026-09-21
    'g_evid_max': 0.06,  # 证据区间上沿 = 上限 g_cap(r_ene) = min(6%, 13% − 4%) = 6%：本票指数派息率交叉（`idx_dy` × `pe_now` = 52.5% → 5.99%）与 513530 三名子集（6.27%）都截到此 2026-09-21
    'idx_dy': 0.054,  # `931722` 指数股息率（中证单张 08-31 区间 5.3–5.55% 取中值）；只进指数派息率交叉与 DDM 对照，不入锚点 2026-08-31
    'etf_dps_ttm': 0.0431,  # ETF 自身 TTM 每份实派 CNY（Longbridge 2026-09-15 `dps_rate` × 当日收盘反算的每份金额；含港股通 20% 红利税）；只进 DDM 对照 2026-09-15
    'w_ene': 0.443,  # 能源 2026-08-31
    'w_ind': 0.196,  # 工业（集运为主） 同上
    'w_resc': 0.087,  # 残余周期，分子代理能源 同上
    'w_ann': 0.274,  # 年金（通信+其余） 同上
    'pe_ene': 7.52,  # 能源 fair PE = `perpetual_pe(g2_ene, roe_ene, r_ene)` = (1 − 0.0543/0.126)/(0.13 − 0.0543)，flat（eval 复算 ±0.05；篮 6 13% 下生成，A10；A11 前 7.65） 2026-09-21
    'pe_ind': 7.69,  # 工业 fair PE = `perpetual_pe(g2_ind = 0, ·, r_ind)` = 1/r = 1/0.13，flat（eval 复算；篮 6） 2026-09-20
    'pe_ann': 13.33,  # 年金 = `perpetual_pe(g2_ann = 0, ·, r_ann)` = 1/r = 1/0.075，flat（eval 复算；篮 2） 2026-09-20
    'eps_ene_l': 0.873,  # 能源分子 / TTM：四只 FY2027E 共识**下沿**盈利加权（eval 复算 ±0.005，A3） 2026-09-13
    'eps_ene_m': 1.089,  # FY2027E 均值 2026-09-13
    'eps_ene_h': 1.327,  # FY2027E 上沿 2026-09-13
    'eps_ind_l': 0.395,  # 工业分子 / TTM：中远 FY2027E 下沿（A4） 2026-09-13
    'eps_ind_m': 0.637,  # 均值 2026-09-13
    'eps_ind_h': 0.751,  # 上沿 2026-09-13
    'eps_ann_l': 0.991,  # 年金分子 / TTM：中国移动 FY2027E 下沿（A5） 2026-09-13
    'eps_ann_m': 1.028,  # 均值 2026-09-13
    'eps_ann_h': 1.075,  # 上沿 2026-09-13
    'shenhua_fy27_l': 2.57,  # 中国神华 FY2027E EPS 下沿 CNY（yfinance 7 家） 2026-09-13
    'shenhua_fy27_m': 2.823,  # 均值 同上
    'shenhua_fy27_h': 3.139,  # 上沿 同上
    'shenhua_ttm': 2.694,  # TTM EPS CNY（3.15 HKD × 0.8552） 2026-09-11
    'shenhua_w': 0.114,  # 指数权重 2026-08-31
    'shenhua_pe': 15.852,  # 09-11 收盘 TTM PE（Longbridge） 2026-09-11
    'shenhua_dps25': 2.01,  # 神华 FY2025 全年 DPS CNY = 中期 0.98（除净 2025-11-10）+ 末期 1.03（2026-07-13）；Longbridge `dividend` 601088.SH FY2025
    'shenhua_eps25': 2.7288,  # 神华 FY2025 基本 EPS CNY；Longbridge IS af 601088.SH → 派息率 73.7% FY2025
    'shenhua_bps': 21.173,  # 神华 2Q26 BPS CNY；yfinance `bookValue` 601088.SS（= Longbridge BS saf 2026H1 21.1728）→ 账面滚动起点；旧口径 ROE 2.823/21.173 = 13.3%，2027 年初口径 13.0%（A11） 2026-06-30
    'shenhua_fy26_m': 2.93274,  # 神华 FY2026E 共识均值 EPS CNY（yfinance 5 家）；只用于 2H26 未入账 EPS = 2.933 − 1.448 = 1.485（A11） 2026-09-21
    'shenhua_h1_26': 1.4479,  # 神华 2026H1 基本 EPS CNY（已入账；Longbridge IS saf 601088.SH） 2026-06-30
    'cnooc_fy27_l': 2.51,  # 中海油 FY2027E EPS 下沿 CNY（13 家） 2026-09-13
    'cnooc_fy27_m': 3.07,  # 均值 同上
    'cnooc_fy27_h': 3.451,  # 上沿 同上
    'cnooc_ttm': 2.916,  # TTM EPS CNY（3.41 HKD × 0.8552） 2026-09-11
    'cnooc_w': 0.114,  # 指数权重 2026-08-31
    'cnooc_pe': 7.272,  # 09-11 TTM PE 2026-09-11
    'cnooc_dps25': 1.1449,  # 中海油 FY2025 DPS CNY（A 股口径）= 中期 0.6661（2025-10-17）+ 末期 0.4788（2026-07-10）；Longbridge 600938.SH FY2025
    'cnooc_eps25': 2.5685,  # 中海油 FY2025 基本 EPS CNY → 派息率 44.6%（公司 2025–27 承诺 ≥45%） FY2025
    'cnooc_bps': 18.011,  # 中海油 2Q26 BPS CNY（yfinance 600938.SS；= Longbridge BS saf 18.0108）→ 旧口径 ROE 17.0%，2027 年初口径 16.6%（A11） 2026-06-30
    'cnooc_fy26_m': 3.39294,  # 中海油 FY2026E 共识均值 EPS CNY（yfinance 4 家）；2H26 未入账 = 3.393 − 1.806 = 1.587（A11） 2026-09-21
    'cnooc_h1_26': 1.8056,  # 中海油 2026H1 基本 EPS CNY（Longbridge IS saf 600938.SH） 2026-06-30
    'petrochina_fy27_l': 0.72,  # 中石油 FY2027E EPS 下沿 CNY（12 家） 2026-09-13
    'petrochina_fy27_m': 0.953,  # 均值 同上
    'petrochina_fy27_h': 1.13,  # 上沿 同上
    'petrochina_ttm': 0.958,  # TTM EPS CNY（1.12 HKD × 0.8552） 2026-09-11
    'petrochina_w': 0.114,  # 指数权重 2026-08-31
    'petrochina_pe': 9.014,  # 09-11 TTM PE 2026-09-11
    'petrochina_dps25': 0.47,  # 中石油 FY2025 DPS CNY = 中期 0.22（2025-09-17）+ 末期 0.25（2026-06-26）；Longbridge 601857.SH FY2025
    'petrochina_eps25': 0.8596,  # 中石油 FY2025 基本 EPS CNY → 派息率 54.7% FY2025
    'petrochina_bps': 8.95,  # 中石油 2Q26 BPS CNY（yfinance 601857.SS；= Longbridge BS saf 8.9497）→ 旧口径 ROE 10.6%，2027 年初口径 10.4%（A11） 2026-06-30
    'petrochina_fy26_m': 0.91,  # 中石油 FY2026E 共识均值 EPS CNY（yfinance **1 家**，薄；2H26 未入账 = 0.91 − 0.568 = 0.342，A11） 2026-09-21
    'petrochina_h1_26': 0.5679,  # 中石油 2026H1 基本 EPS CNY（Longbridge IS saf 601857.SH） 2026-06-30
    'sinopec_fy27_l': 0.314,  # 中石化 FY2027E EPS 下沿 CNY（13 家） 2026-09-13
    'sinopec_fy27_m': 0.423,  # 均值 同上
    'sinopec_fy27_h': 0.66,  # 上沿 同上
    'sinopec_ttm': 0.291,  # TTM EPS CNY（0.34 HKD × 0.8552） 2026-09-11
    'sinopec_w': 0.08,  # 指数权重 2026-08-31
    'sinopec_pe': 14.215,  # 09-11 TTM PE 2026-09-11
    'sinopec_dps25': 0.2,  # 中石化 FY2025 DPS CNY = 中期 0.088（2025-09-12）+ 末期 0.112（2026-06-17）；Longbridge 600028.SH FY2025
    'sinopec_eps25': 0.268,  # 中石化 FY2025 基本 EPS CNY（2025 谷底）→ 派息率 74.6% FY2025
    'sinopec_bps': 6.959,  # 中石化 2Q26 BPS CNY（yfinance 600028.SS；= Longbridge BS saf 6.9586）→ 旧口径 ROE 6.1%，2027 年初口径 6.0%（峰形区，A11） 2026-06-30
    'sinopec_fy26_m': 0.35624,  # 中石化 FY2026E 共识均值 EPS CNY（yfinance 9 家）；2H26 未入账 = 0.356 − 0.220 = 0.137（A11） 2026-09-21
    'sinopec_h1_26': 0.2197,  # 中石化 2026H1 基本 EPS CNY（Longbridge IS saf 600028.SH） 2026-06-30
    'cosco_fy27_l': 0.78,  # 中远海控 FY2027E EPS 下沿 CNY（6 家） 2026-09-13
    'cosco_fy27_m': 1.259,  # 均值 同上
    'cosco_fy27_h': 1.484,  # 上沿 同上
    'cosco_ttm': 1.976,  # TTM EPS CNY（2.31 HKD × 0.8552） 2026-09-11
    'cosco_w': 0.069,  # 指数权重 2026-08-31
    'cosco_pe': 8.155,  # 09-11 TTM PE 2026-09-11
    'cosco_dps25': 1.0,  # 中远海控 FY2025 DPS CNY = 中期 0.56（2025-10-24）+ 末期 0.44（2026-06-26）；Longbridge 601919.SH FY2025
    'cosco_eps25': 1.99,  # 中远 FY2025 基本 EPS CNY → 派息率 50.3%（FY2023–25 恒 50%） FY2025
    'cosco_bps': 15.551,  # 中远 BPS CNY（yfinance 601919.SS）→ 前瞻 ROE 8.1% 2026-09-15
    'cosco_eps22': 6.78,  # 中远 FY2022 基本 EPS CNY（上一轮集运峰值）；实测方向用：FY22→25 CAGR −33%/yr（A2） FY2022
    'cosco_dps22': 3.4,  # 中远 FY2022 全年 DPS CNY = 中期 2.01 + 末期 1.39；FY22→25 CAGR −33%/yr（A2） FY2022
    'cmobile_fy27_l': 5.99,  # 中国移动 FY2027E EPS 下沿 CNY（9 家） 2026-09-13
    'cmobile_fy27_m': 6.215,  # 均值 同上
    'cmobile_fy27_h': 6.498,  # 上沿 同上
    'cmobile_ttm': 6.046,  # TTM EPS CNY（7.07 HKD × 0.8552） 2026-09-11
    'cmobile_w': 0.089,  # 指数权重 2026-08-31
    'cmobile_pe': 11.276,  # 09-11 TTM PE 2026-09-11
    'cnooc_ni_l': 249.56,  # 中海油 2020 净利（亿）；报表年 regime 只作压力坐标（A9） 年报
    'cnooc_ni_m': 1220.82,  # 2025 年报
    'cnooc_ni_h': 1416.77,  # 2022 年报
    'shenhua_ni_l': 391.7,  # 神华 2020 净利（亿） 年报
    'shenhua_ni_m': 528.49,  # 2025 年报
    'shenhua_ni_h': 696.26,  # 2022 年报
    'petrochina_ni_l': 190.06,  # 中石油 2020 归母净利（亿 CNY）；Longbridge af 2026-09-14
    'petrochina_ni_m': 1573.18,  # 2025 同上
    'petrochina_ni_h': 1487.43,  # 2022 同上
    'sinopec_ni_l': 334.43,  # 中石化 2020 归母净利（亿 CNY）；Longbridge af 2026-09-14
    'sinopec_ni_m': 324.76,  # 2025 同上
    'sinopec_ni_h': 669.33,  # 2022 同上
    'cosco_ni_l': 238.6,  # 中远 2023 净利（亿） 年报
    'cosco_ni_m': 308.7,  # 2025 年报
    'cosco_ni_h': 358.1,  # 1.16×2025（旧 H，只作压力坐标对照带） A4
    'chan_regime_start': 2021.0,  # **通道对照**：931722 价格指数 regime 起点（央企分红 / 市值管理新政；全窗 +2.2% vs 2021 起 +10.1% 差 ≥ 5pp） 2026-09-18
    'chan_slope': 0.101,  # 通道斜率（2021-01-01～2026-09-17，剔 2σ 重拟）；价格指数，含息约 +5.4pp 2026-09-17
    'chan_slope_full': 0.022,  # 全窗斜率（2015-12 起，含回填段 2016–20 指数 1000 → 749）；只对照 2026-09-17
    'chan_slope_2019': 0.066,  # 子窗斜率 2019 起 2026-09-17
    'chan_slope_2021': 0.102,  # 子窗斜率 2021 起（= 通道窗） 2026-09-17
    'chan_sigma': 0.066,  # 残差 σ（2021 起） 2026-09-17
    'chan_l_idx': 1267.0,  # 通道 L = 趋势 × exp(残差 p10)，指数点 2026-09-17
    'chan_m_idx': 1397.0,  # 通道 M = 趋势现值，指数点 2026-09-17
    'chan_h_idx': 1509.0,  # 通道 H = 趋势 × exp(残差 p90)，指数点 2026-09-17
    'idx_cur': 1336.63,  # 折算日指数值（价格）；k = nav_ref ÷ idx_cur → 通道对照带 0.958 / 1.056 / 1.141（`nav_ref` 取 09-11 收盘，与指数 09-17 不同日） 2026-09-17
    'r_mk': 0.1,  # 篮 4 常规经营：神华发电 / 铁路 / 港口腿与中石化营销及分销腿的 Gordon r——盈利跟量与管制 / 零售价差，不是商品价函数（发电沿用 `600011.SH` 归篮；A12） 2026-10-07
    'fx_hkdcny': 0.8552,  # HKD→CNY；与 A3 的 TTM 折算同值；中石化 FY27E CNY 折 HKD 用 2026-09-11
    'shenhua_px': 46.12,  # 中国神华 H 股 2026-09-11 收盘 HKD（Longbridge，他股）；v4 能源逐名分母（A12） 2026-09-11
    'cnooc_px': 24.38,  # 中国海洋石油 2026-09-11 收盘 HKD（Longbridge，他股） 2026-09-11
    'petrochina_px': 9.98,  # 中国石油股份 H 股 2026-09-11 收盘 HKD（Longbridge，他股） 2026-09-11
    'sinopec_px': 4.775,  # 中国石油化工股份 H 股 2026-09-11 收盘 HKD（Longbridge，他股） 2026-09-11
    'cnooc_fw_l': 27.24,  # `0883.HK` 框架底牌 L（HKD）；eval 与该文件逐格校验 ±0.01，成分框架改动即红（A12）；超额现金单列、经营口径 2026-10-16
    'cnooc_fw_m': 30.27,  # `0883.HK` 底牌 M 2026-10-16
    'cnooc_fw_h': 34.58,  # `0883.HK` 底牌 H 2026-10-16
    'petrochina_fw_l': 6.89,  # `0857.HK` 框架底牌 L（HKD；四腿分腿加总，时点对齐 τ 0.5 + 窗口可分配利润） 2026-10-16
    'petrochina_fw_m': 7.41,  # `0857.HK` 底牌 M 2026-10-16
    'petrochina_fw_h': 8.15,  # `0857.HK` 底牌 H 2026-10-16
    'shenhua_fw_l': 28.68,  # `1088.HK` 框架底牌 L（HKD；煤价轴矿商侧 + 分腿加总；H 档周期高年只维持 1 年、之后回到 M）；eval 与该文件逐格校验 ±0.01（A12） 2026-10-16
    'shenhua_fw_m': 30.9,  # `1088.HK` 底牌 M 2026-10-16
    'shenhua_fw_h': 31.18,  # `1088.HK` 底牌 H 2026-10-16
    'sinopec_seg6': 4035.0,  # 中石化 2018–25 八年分部经营收益合计（亿元）篮 6 腿：勘探及开发 1,880 + 炼油 1,941 + 化工 214（2019 / 2021 / 2023 / 2025 年报，各取当年与上年列）；份额 69.9%——2025 单年化工 −146 亿、勘探及开发占 94%，单年份额失真，取完整周期 2018–25
    'sinopec_seg4': 1736.0,  # 同上篮 4 腿：营销及分销 1,736（235 / 291 / 208 / 212 / 245 / 259 / 186 / 100） 2018–25
}

def pe_mix(inp: dict[str, float], n: str) -> float:
    """Leg-mix multiple: commodity segments at 1/r_ene (篮 6), the rest at 1/r_mk (篮 4)."""
    s6, s4 = inp[f"{n}_seg6"], inp[f"{n}_seg4"]
    return (s6 / inp["r_ene"] + s4 / inp["r_mk"]) / (s6 + s4)


def name_value(inp: dict[str, float], n: str, tier: str) -> float:
    """V_k,x in HKD: the constituent framework's anchor, or FY27E consensus x leg mix."""
    if n in FW_NAMES:
        return inp[f"{n}_fw_{tier}"]
    return inp[f"{n}_fy27_{tier}"] * pe_mix(inp, n) / inp["fx_hkdcny"]


def ene_ratios(inp: dict[str, float], tier: str) -> dict[str, float]:
    return {n: name_value(inp, n, tier) / inp[f"{n}_px"] for n in ENE_NAMES}


def legs_v4(inp: dict[str, float], tag: str) -> dict[str, float]:
    """v4 sleeves (pre NAV x fee): four energy names on own price, the uncovered
    energy weight + residual cyclical on the four names' weighted ratio,
    industrial / annuity as v3."""
    rat = ene_ratios(inp, tag)
    w4 = sum(inp[f"{n}_w"] for n in ENE_NAMES)
    avg = sum(inp[f"{n}_w"] * rat[n] for n in ENE_NAMES) / w4
    out = {n: inp[f"{n}_w"] * rat[n] for n in ENE_NAMES}
    out["ene_rest"] = (inp["w_ene"] - w4) * avg
    out["resc"] = inp["w_resc"] * avg
    out["ind"] = inp["w_ind"] * inp[f"eps_ind_{tag}"] * inp["pe_ind"] / inp["pe_now"]
    out["ann"] = inp["w_ann"] * inp[f"eps_ann_{tag}"] * inp["pe_ann"] / inp["pe_now"]
    return out



def calculate(context):
    inp = INPUTS
    if any(not math.isfinite(inp[k]) for k in BASE_FIELDS):
        raise ValueError('base inputs must be finite')
    if min(inp['nav_ref'], inp['fee_drag'], inp['r_ene'], inp['r_mk'], inp['fx_hkdcny'], inp['pe_now'],
           *(inp[f'{n}_px'] for n in ENE_NAMES)) <= 0:
        raise ValueError('invalid base denominator')
    parts = {t: legs_v4(inp, t) for t in 'lmh'}
    values = tuple(scale(inp['nav_ref'], inp['fee_drag'], sum(parts[t].values())) for t in 'lmh')
    if not all(math.isfinite(v) for v in values) or not values[0] < values[1] < values[2]:
        raise ValueError('look-through anchors must be finite and ordered')
    A, B = cut_points(*values)
    band = lambda values: dict(zip('LMH', values))
    warnings = ['historical_constituent_prices_and_estimates', 'historical_index_cache_conflict']
    peers = context.get('peers', {})
    for name, ticker in FW_NAMES.items():
        peer = peers.get(name)
        if not isinstance(peer, dict):
            warnings.append(f'{name}_historical_peer_unavailable')
            continue
        anchors = peer.get('anchors')
        if peer.get('ticker') != ticker or peer.get('currency') != 'HKD' or not isinstance(anchors, dict):
            warnings.append(f'{name}_historical_peer_unavailable')
            continue
        if any(not isinstance(anchors.get(t), (int, float)) or isinstance(anchors[t], bool)
               or not math.isfinite(anchors[t]) for t in 'LMH'):
            warnings.append(f'{name}_historical_peer_unavailable')
            continue
        if any(abs(anchors[t.upper()] - inp[f'{name}_fw_{t}']) > .01 for t in 'lmh'):
            warnings.append(f'{name}_historical_peer_changed')
    multiplier = inp['nav_ref'] * inp['fee_drag']
    return {'ticker': '520900.SH', 'currency': 'CNY', 'units': {'price': 'CNY_PER_FUND_UNIT'},
            'valuation_as_of': None, 'framework_as_of': None,
            'historical_valuation_as_of': None, 'historical_research_as_of': '2026-10-19',
            'historical_constituent_price_as_of': '2026-09-11',
            'anchors': band(values), 'cut_points': {'A': A, 'B': B}, 'candidate': None, 'option': None,
            'review_flags': warnings, 'fund_reference_status': 'historical_constituents_unverified',
            'segments': {name: {'unit': 'CNY_PER_FUND_UNIT', 'values': band(parts[t][name] * multiplier for t in 'lmh')}
                         for name in parts['l']},
            'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                {'base_inputs': {k: inp[k] for k in BASE_FIELDS}}, BASELINE_LOCAL)}
