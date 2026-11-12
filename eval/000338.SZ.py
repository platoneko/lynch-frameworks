from __future__ import annotations

import math
import statistics

from lib.gordon import (
    check_branch, check_g_cap, check_r, g_cap, payout, payout_gap, recovery_two_stage_pe,
)
from lib.inputs import (
    check_missing, ladder, require_whole_years,
)
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'),
                'axes': {'southbound': 'southbound_repricing'}}
BASELINE_LOCAL = '8b021b14e0d9508c7f6de721fe164508b55d29443b0b9574ec279bd18a36b491'

INPUTS = {
    'shares': 8640220621.0,  # 总股本（A+H）；三季报资产负债表股本；2026-09-30
    'bps': 10.88,  # 每股净资产 CNY = 归母权益 940.12 亿 ÷ 股本；三季报（已扣应付中期股息 44.67 亿）；2026-09-30
    'dps_after_bs': 0.0,  # 资产负债表日之后才宣派、尚未从 BPS 扣除的每股股息；2026 中期 0.517 元 8-27 宣派，9-30 已计入其他应付款（应付股利 44.74 亿），BPS 已扣 → 0；2026-09-30
    'eps_h1': 0.8913,  # 2026H1 EPS（归母 77.01 亿 ÷ 股本）；**只作电力腿利润率公开数据交叉**（与 `power_np_share_h1` 同期）；2026-06-30
    'eps_ytd': 1.2336,  # 2026 前三季度 EPS = 归母 106.59 亿 ÷ 股本（三季报；报告基本 EPS 1.24 按加权股本）；窗口内已入账部分，从 FY2026E 中扣除；2026-09-30
    'fx_hkdcny': 0.8489,  # HKD→CNY；yfinance `HKDCNY=X`；2026-10-30
    'fx_eurcny': 7.4121,  # EUR→CNY；yfinance `EURCNY=X`；2026-10-30
    'cons_fy26_m': 1.7238,  # FY2026E 共识 EPS 均值（东方财富半年报后 13 家，招银国际取 08-31 更新版 1.70，A1）；BPS 滚动用；2026-10-04
    'cons_fy26_h': 1.84,  # FY2026E 上沿（华源）；2026-10-04
    'cons_fy27_m': 2.2208,  # FY2027E 均值（13 家，招银国际 08-31 版 2.00）；2026-10-04
    'cons_fy27_h': 2.6,  # FY2027E 上沿（长江）；2026-10-04
    'cons_fy28_l': 2.33,  # FY2028E 下沿（西南 09-08；招银国际 08-31 已由 2.22 上调到 2.37）；**只作敏感性，不进底牌**（L 用实测谷底）；2026-10-04
    'cons_fy28_m': 2.6869,  # **M** 分子 = FY2028E 共识均值（13 家，招银国际取 08-31 版 2.37，A1）；2026-10-04
    'cons_fy28_h': 3.18,  # **H** 分子 = FY2028E 共识上沿（长江 09-17）；2026-10-04
    'np_l': 4910000000.0,  # **L** 归母 = FY2022 实测谷底（上一轮重卡周期谷底）；经营口径由 eval 再扣当年自身超额现金税后收益 6.72 亿 → 42.38 亿（A18）；FY2022
    'np_ttm': 12711500000.0,  # TTM 归母（2025Q4~2026Q3）= FY2025 109.31 − 2025 前三季度 88.78 + 2026 前三季度 106.59 亿：L 档实测回归终点 + 凯傲占比校验 + ②-b 旧梯 M；2026-09-30
    'np_qx4': 11829000000.0,  # 2026Q3 单季归母 29.57 亿 × 4：只作 ②-b 旧梯 H，**不进公式**；2026Q3
    'np_mid5': 9148000000.0,  # 自身五年（FY2021–25）归母均值 = (94.9 + 49.1 + 90.1 + 114.0 + 109.3) ÷ 5；周期中枢核对（A1），**不进公式**；FY2025
    'n_rec_l': 3.75,  # **L** 谷底档段一年数 = FY2022 → TTM 实测回归年数（窗口中心 2022-07 → 2026-04）；g₁ 由 `np_ttm` / `np_l` 重算；FY2022–2026Q3
    'kion_np_rr_eur': 412130000.0,  # 凯傲运行率净利 EUR = 2026 前三季度 309.1 百万 × 4/3（KION Q3 2026 quarterly statement；Q3 单季 101.6，同比 −14.8%）；2026-09-30
    'kion_stake': 0.4652,  # 潍柴持凯傲比例；2026 半年度报告第八节附注原文；2026-06-30
    'kion_l_factor': 0.5,  # L 档凯傲权益净利折半系数（A6）；对话锁定
    'pe_kion': 8.09,  # 凯傲腿倍数 = KGX.DE 前瞻 PE（yfinance，FY2027E 11 家均值 4.2475 EUR，10-04 为 4.4865；A3）；2026-10-30
    'ms_units_l': 11000.0,  # **L** 电力腿台数 = 2025 实测约 1.1 万台；FY2025
    'ms_units_m': 13400.0,  # M 系列 2026H1 实测 6,700 台 × 2：售后期权的装机收入基数；2026H1
    'ms_price': 528000.0,  # 大缸径单价 元/台 = 2025 年报 58.1 亿 ÷ 1.1 万台；FY2025
    'lb_rev_fy28': 20943000000.0,  # 招银国际 FY2028E 大缸径收入 20,943 百万元（08-28 Figure 2；v6 的电力腿口径）；`pw_rev_cmbi` 的组成项与 AIDC 增量清零的依据，**不单独进公式**；2026-08-28
    'pw_rev_cmbi': 36943000000.0,  # 电力腿收入（大缸径 + 燃气机组 + SOFC）· 招银国际 = 大缸径 209.43 亿（08-28 Figure 2；08-31 版分部表未得）+ AIDC 燃气机组 160 亿（08-31 更新版首页，发现报告 5697743）；**报告表**（A4）；2026-08-31
    'pw_rev_ct': 55700000000.0,  # 电力腿收入 · 诚通 FY2028E「新兴业务」（大缸径 + 燃气机组 + SOFC）557 亿（东财 AP202609031828953596 表 11）；**报告表**（A4）；2026-09-03
    'pw_rev_yh': 64296400000.0,  # 电力腿收入 · 中国银河 = 「AI 发电 2028 年约占营收 20%」× 其 FY2028E 营收 3,214.82 亿（09-06 汽车会议纪要，发现报告 5686040；营收见新浪 841740075647）；**纪要口径**（A4）；2026-09-06
    'cj_main': 11000000000.0,  # **H** 电力腿拆分：长江 FY2027「主业 110 亿 + AIDC 电源 110 亿 = 220 亿」中的主业（含凯傲），按长江自己 2026→27 主业增速 0% 持平到 2028；H 电力腿 = `cons_fy28_h` × 股本 − 本值（**快评文字**，A4）；2026-09-16
    'seg_margin': 0.195,  # 招银国际柴油机分部 FY2028E 分部利润率（A5）；2026-08-28
    'seg_tax': 0.145,  # 招银国际 FY2027E 有效税率（A5）；2026-08-28
    'power_np_share_h1': 0.2,  # 电力能源对归母贡献占比 2026H1（西南 2026-09-08 引述）；利润率公开数据交叉；2026-09-08
    'power_rev_h1': 8611500000.0,  # 发电相关发动机收入半年代理 = 招银国际 2026E 17,223 百万元 ÷ 2；交叉用；2026-08-28
    'equity': 94011900000.0,  # 归母权益（三季报）；L 档段二中枢 RONIC = (`np_ttm` − 超额现金税后收益) ÷ (equity − `dps_after_bs` × 股本 − `c_ex`)；超额现金触发分母；2026-09-30
    'net_cash_ext': 43962800000.0,  # 扩展口径净现金 2026-09-30（**估计**：季报无附注）= 货币资金 716.80 − 受限货币资金 119.26（沿用 6-30 值）+ 交易性金融资产 157.04 − 有息负债与租赁负债 314.95 亿（短借 52.75 + 长借 80.58 + 应付债券 100.99 + 租赁负债 51.97 + 各自一年内到期部分与短融 28.67，后者沿用 6-30 值）；凯傲金融服务融资不计。较 6-30 的 514.60 亿少 75.0 亿，主要是三季度应付账款 −73.0 亿、应付票据 −22.0 亿的营运资金回落与短借 +37.3 亿（A18）；2026-09-30
    'div_declared': 4466990000.0,  # 9-30 尚未支付的 2026 中期股息 = 0.517 × 股本（8-27 宣派，9-30 应付股利 44.74 亿，10 月实施）；类债项；2026-09-30
    'ncx_min': 4225500000.0,  # 经营所需现金锚的最低年 FY2019 扩展口径净现金（同口径 467.37 − 425.11 亿）；FY2019–25「净现金 ÷ 收入」= 2.42% / 9.83% / 20.68% / 17.11% / 20.12% / 18.41% / 18.03%（A18）；FY2019
    'rev_min': 174360890000.0,  # FY2019 营业总收入 1,743.61 亿；锚比率 = `ncx_min` ÷ 本值 = 2.42%（< 2 个月收入 16.7%）；FY2019
    'rev_fy25': 231809280000.0,  # FY2025 营业总收入 2,318.09 亿；锚 = 2.42% × 本值 = 56.18 亿；FY2025
    'c_ex': 33878100000.0,  # 超额现金 = `net_cash_ext` − `div_declared` − 锚 56.18 亿（A18）；2026-09-30
    'cash_yield': 0.04588,  # 现金收益率 FY2025 = (利息收入 35.61 + 理财 / 交易性金融资产收益 3.86) ÷ 平均（货币资金 + 交易性金融资产）860.30 亿（年报附注 58 / 60 / 61）；FY2025
    'tax_eff': 0.15626,  # 实际所得税率 FY2025 = 所得税 ÷ 利润总额；FY2025
    'ncx_l': 29968000000.0,  # FY2022（L 谷底年）扩展口径净现金（同口径，受限 80.81 亿）；L 档扣当年自身超额现金收益；FY2022
    'rev_l': 175157540000.0,  # FY2022 营业总收入 1,751.58 亿；FY2022 锚 = 2.42% × 本值 = 42.45 亿 → C_ex(2022) 257.23 亿；FY2022
    'cash_yield_l': 0.02796,  # FY2022 现金收益率（利息收入 ÷ 年均现金类资产；理财收益未逐年拆，偏低方向）；FY2022
    'tax_eff_l': 0.06615,  # FY2022 实际所得税率；FY2022
    'cash_inc_mid5': 963200000.0,  # FY2021–25 各年自身超额现金税后收益均值 =（7.94 + 6.72 + 9.73 + 11.14 + 12.63）÷ 5；周期中枢核对用，**不进公式**；FY2025
    'payout_op': 0.905,  # 经营口径派息率 = 分红与注销式回购 48.4% + 现金积累 42.2%（ΔC_ex FY2019→25 361.7 亿 − 2021 定增 129.9 亿，÷ 归母利润合计 549.7 亿），FY2020–25（A18）；`check_branch` 用；FY2025
    'r_perp': 0.1,  # 篮 4 常规经营 10%（三腿同篮：重卡动力与发电设备制造，盈利不是商品价函数，未达篮 7 单客户阈值；A15）；`check_r`；2026-10-04
    'g2_core': 0.0,  # 核心盘稳态 g₂ = 同世界同业（中国重汽 A/H）在本尺上无解、隐含 ≤ 0 → 取 0（A14）；2026-10-04
    'g2_core_us': 0.0474,  # 美国同业（CMI 4.20% / PCAR 5.27%）中位；国别不同，**只作对照，不进公式**；2026-10-04
    'pe_sinotruk_a': 9.27,  # 中国重汽 A 000951 前瞻 PE（yfinance）；< 1/r → 留存分支无解（A14）；2026-10-30
    'pe_sinotruk_h': 7.27,  # 中国重汽 H 3808 前瞻 PE（yfinance）；< 1/r；2026-10-30
    'g2_pw_cmi': 0.04047,  # 康明斯反解 g（14.98× / 前瞻 ROE 37.3%，A17；10-04 为 4.20%）；2026-10-30
    'g2_pw_gnrc': 0.04649,  # Generac 反解 g（15.41× / 26.5%；10-04 为 5.50%）；2026-10-30
    'g2_pw_jereh': 0.027,  # 杰瑞股份反解 g（12.47× / 30.2%；前瞻 EPS 同为 FY2027E，倍数下降来自股价；10-04 为 4.41%）；2026-10-30
    'g2_pw_cat': 0.05386,  # 卡特彼勒反解 g（20.16× / 77.2%）；10-04 为 6.49% > cap 剔除，本期 < cap 6% → 回簇（剔除只因碰顶，A17）；2026-10-30
    'g2_power': 0.04348,  # 电力腿稳态 g₂ = 上四家中位（康明斯 / Generac 两中间值均值，A17）；≤ cap 6%；2026-10-30
    'payout_obs': 0.58,  # 实付派息率（2026 中期 58%；FY2025 全年 0.732 ÷ 1.265 = 57.9%）；2026-08-27
    'tau': 1.25,  # 时点对齐 τ = 估值基准日（超额现金的资产负债表日 2026-09-30）到分子年初 2028-01-01 = 15 个月；核心盘与电力腿 ÷ (1+r)^τ，窗口可分配利润 ÷ (1+r)^(τ/2)（折现率同 `r_perp`，不归篮；A9）；2026-09-30
    'parent_eq': 94011900000.0,  # 归属于母公司股东权益（三季报）；归母比例用（A18）；2026-09-30
    'minority': 39779400000.0,  # 少数股东权益（三季报）；归母比例用；2026-09-30
    'kion_nfd_eur': 1196000000.0,  # 凯傲自身净金融负债 EUR（KION Q3 2026 quarterly statement）；凯傲那块扩展净现金 = −(本值 × EURCNY + `lease_liab`)；2026-09-30
    'lease_liab': 5196700000.0,  # 合并租赁负债（三季报非流动部分；整条计入凯傲那块，上界读法）；2026-09-30
    'kion_eq_eur': 6562800000.0,  # 凯傲股东权益 EUR（KION Q3 2026 quarterly statement）；剔凯傲权益比用；2026-09-30
    'parent_ratio': 0.9932,  # 归母比例（子公司披露读法）= [（C_ex 总额 − 凯傲那块）× 剔凯傲权益比 + 凯傲那块 × 46.52%] ÷ C_ex 总额；eval 重算校验（A18；6-30 为 0.9822——C_ex 总额变小而凯傲那块净负债不变，比例上升）；2026-09-30
    'y1_power': 2028.0,  # 电力腿高回报期止点 Y₁ = 可见年末 FY2028（第 8 轮补充裁定的默认路径；本票无用户另定年份，A19）；2026-10-16
    'y2_power': 2032.0,  # 电力腿回落到稳态 Y₂ = Y₁ + 4（中门槛，A19）；2026-10-16
    'ronic_ss_wrt': 0.218,  # 瓦锡兰投入资本口径经营回报（仅 3 个完整财年读数，不足 5 年不认）；**只作敏感性，不进公式**（A19）；2026-10-19
    'ronic_ss_power': 0.15,  # 电力腿稳态回报 = 兜底：自身周期不可用（公式不同）、同业层为空（国内同业全部放量期或衰退期，美国同业按竞争场剔除）（A19；用户 2026-10-19 认可）；2026-10-19
    'ronic_ss_floor': 0.15,  # 生意模式兜底：有壁垒的重资产（设备）15%；2026-10-16
    'pe_own_min': 10.26,  # 自身 5 年月频 TTM PE 实测下沿（2024-09）；trailing 带，对 FY2028 分子不适用（A14），只披露；2026-09-14
    'pe_own_max': 25.82,  # 自身 5 年月频 TTM PE 实测上沿（2026-06）；只披露；2026-09-14
    'pe_ownyear_l': 15.27,  # own-year 经营倍数反向带 L = 2022：(18.42 × 当年归母 − 当年 C_ex 257.2 亿) ÷ (归母 − 当年现金税后收益 6.72 亿)（A2）；**交叉尺，不进公式**；FY2022
    'pe_ownyear_m': 9.66,  # own-year 经营倍数反向带 M = 2022–25 中位（15.27 / 9.48 / 9.36 / 9.84）；**交叉尺**；FY2022–25
    'pe_ownyear_h': 9.36,  # own-year 经营倍数反向带 H = 2024（原整体 11.47×）；**交叉尺**；FY2024
    'pb_own_min': 0.78,  # 自身 5 年周频 PB 低点（2022-10-31，Longbridge）；对账门 ⑥，**不进公式**；2026-09-28
    'aft_share_peer': 0.26,  # 售后期权上限比例 = 康明斯已实现发动机售后占收入比（属性 E 期权段）；A8
    't_align': 2028.0,  # 对齐年份 = 本票最远 ≥2 家带区间共识年 FY2028（A1）；2026-10-04
    't_aft': 2030.0,  # 售后兑现年 = 无具名年份 → `t_align` + 2，**无时点锚·拍值**；2026-10-04
}
FORMULA_ID = "weichai_consensus_fy28_three_leg_gordon_v8"
YI = 1e8
NUM_YEAR = 2028
TODAY_FY = 2026
P_TIERS = (0.0, 0.0, 1.0)
TOL = 0.05
KION_SHARE_BAND = (0.08, 0.12)   # 属性 A, on the measured TTM numerator
B2_MAX_DEV = 0.20                # ②-b (ii)
MID_MAX = 1.15                   # 周期票中枢 threshold; disclosure only here (demand-cycle, rule n/a)
GATE_BAND = 0.20
MARGIN_XCHK = 0.25               # sell-side leg margin vs public cross-check

REQUIRED = [
    "shares", "bps", "dps_after_bs", "eps_h1", "eps_ytd", "fx_hkdcny", "fx_eurcny",
    "cons_fy26_m", "cons_fy26_h", "cons_fy27_m", "cons_fy27_h",
    "cons_fy28_l", "cons_fy28_m", "cons_fy28_h",
    "np_l", "np_ttm", "np_qx4", "np_mid5", "n_rec_l",
    "kion_np_rr_eur", "kion_stake", "kion_l_factor", "pe_kion",
    "ms_units_l", "ms_units_m", "ms_price",
    "lb_rev_fy28", "pw_rev_cmbi", "pw_rev_ct", "pw_rev_yh", "cj_main", "seg_margin", "seg_tax", "power_np_share_h1", "power_rev_h1",
    "equity", "r_perp", "g2_core", "g2_core_us", "pe_sinotruk_a", "pe_sinotruk_h",
    "g2_pw_cmi", "g2_pw_gnrc", "g2_pw_jereh", "g2_pw_cat", "g2_power", "payout_obs", "tau",
    "parent_eq", "minority", "kion_nfd_eur", "lease_liab", "kion_eq_eur", "parent_ratio",
    "y1_power", "y2_power", "ronic_ss_wrt", "ronic_ss_power", "ronic_ss_floor",
    "pe_own_min", "pe_own_max", "pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h", "pb_own_min",
    "aft_share_peer", "t_align", "t_aft",
    "net_cash_ext", "div_declared", "ncx_min", "rev_min", "rev_fy25", "c_ex", "cash_yield", "tax_eff",
    "ncx_l", "rev_l", "cash_yield_l", "tax_eff_l", "cash_inc_mid5", "payout_op",
]
NOT_FORMULA = ("pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h", "g2_core_us", "lb_rev_fy28",
               "cons_fy28_l", "np_qx4", "pb_own_min", "cash_inc_mid5")
PREV_M = 31.51                   # M before the 2026-10-29 Q3 update, gate coordinate ①
EX_TRIGGER = 0.15                # C_ex >= 15% of parent equity -> own line
CASH_CAP = 2 / 12                # anchor ratio capped at two months of revenue
GATE_TRIGGER = 0.25              # gate is mandatory when |ΔM| > 25%
VAL_DATE = (2026, 9)             # balance-sheet date of the excess cash (month end)


def path_pe(g2: float, roe: float, r: float, t0: int, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段): RONIC = roe through calendar
    y1, linear to min(roe, r_ss) by y2, perpetual from y2 on.  Value at the start of year t0 per
    unit of year-t0 earnings; equals perpetual_pe when roe <= r_ss."""
    if r - g2 <= 0:
        raise ValueError("r <= g2")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g2, ss) / ((r - g2) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g2, ro) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def aftermarket_option(inp, npm, pe, rate, disc, base):
    unavailable = {'status': 'unavailable', 'label': '大缸径售后', 'anchors': None}
    if inp['shares'] <= 0 or rate <= -1 or disc <= 0 or inp['t_aft'] < NUM_YEAR:
        return unavailable
    try:
        value = (inp['ms_units_m'] * inp['ms_price'] * inp['aft_share_peer'] * npm * pe
                 / inp['shares'] / (1 + rate) ** (inp['t_aft'] - NUM_YEAR) / disc)
        prices = {tier: base[tier] + weight * value for tier, weight in zip('LMH', P_TIERS)}
    except (ArithmeticError, TypeError, ValueError):
        return unavailable
    if (not math.isfinite(value) or value < 0 or any(not math.isfinite(v) for v in prices.values())
            or not prices['L'] < prices['M'] < prices['H']):
        return unavailable
    return {'label': '大缸径售后', 'value': value, 'value_unit': 'CNY_PER_SHARE',
            'weights': dict(zip('LMH', P_TIERS)), 'anchors': prices}


def evaluate(inp, southbound):
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[key]) for key in REQUIRED):
        raise ValueError('all required inputs must be finite')
    require_whole_years(inp, ('y1_power', 'y2_power', 't_align', 't_aft'))
    warnings = []
    if not isinstance(southbound, dict) or southbound.get('role') != 'reference':
        warnings.append('historical_southbound_reference_unavailable')
    baskets = {'r_perp': 4}
    r = inp['r_perp']
    sh = inp['shares']
    if r <= 0 or r <= max(inp['g2_core'], inp['g2_power']) or sh <= 0:
        raise ValueError('invalid valuation discount or share denominator')

    # --- basket, g ------------------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for k in ("g2_core", "g2_power"):
        errors += check_g_cap(inp[k], r, k)
    if inp["g2_core"] != 0.0:
        errors.append("g2_core must be 0 (same-world Chinese truck peers have no retention-branch solution)")
    if not all(p < 1.0 / r for p in (inp["pe_sinotruk_a"], inp["pe_sinotruk_h"])):
        errors.append("a Sinotruk forward PE is now >= 1/r — the core g2 = 0 reading must be redone (A14)")
    peer_g = [inp["g2_pw_cmi"], inp["g2_pw_gnrc"], inp["g2_pw_jereh"], inp["g2_pw_cat"]]
    if any(g > g_cap(r) for g in peer_g):
        errors.append("a power peer g exceeds g_cap — it must be dropped, not capped")
    g_pw = statistics.median(peer_g)
    if abs(g_pw - inp["g2_power"]) > 5e-5:
        errors.append(f"g2_power {inp['g2_power']} != peer median {g_pw:.5f}")
    tau = inp["tau"]
    tau_calc = ((NUM_YEAR - VAL_DATE[0]) * 12 - VAL_DATE[1]) / 12     # balance-sheet date -> start of FY2028
    if abs(tau - tau_calc) > 1e-9:
        errors.append(f"tau {tau:g} != months from {VAL_DATE[0]}-{VAL_DATE[1]:02d} to {NUM_YEAR}-01 / 12 = {tau_calc:g}")
    if not (inp["y1_power"] == NUM_YEAR and inp["y2_power"] == inp["y1_power"] + 4):
        errors.append("power leg Y1 must be the visible year 2028 and Y2 = Y1 + 4 (medium entry barrier)")
    # steady return in order (retention.md 2026-10-19): own cycle unusable, peer layer empty -> floor
    if abs(inp["ronic_ss_power"] - inp["ronic_ss_floor"]) > 5e-4:
        errors.append(f"ronic_ss_power {inp['ronic_ss_power']} != floor {inp['ronic_ss_floor']} (own cycle unusable, peer layer empty)")
    if inp["t_aft"] != inp["t_align"] + 2 or inp["t_align"] != NUM_YEAR:
        errors.append("t_align must be the numerator year and t_aft = t_align + 2 (无时点锚)")
    errors += ladder("FY2028 consensus", inp["cons_fy28_l"], inp["cons_fy28_m"], inp["cons_fy28_h"])
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []

    # --- ②-b: the old run-rate ladder against the FY2028 mean -----------------
    eps_ttm, eps_q2 = inp["np_ttm"] / sh, inp["np_qx4"] / sh
    mean28 = inp["cons_fy28_m"]
    b2_i = eps_ttm <= mean28 <= eps_q2
    b2_dev = eps_ttm / mean28 - 1 if mean28 else None
    if b2_dev is None:
        warnings.append('historical_consensus_comparison_unavailable')
    if b2_i and b2_dev is not None and abs(b2_dev) <= B2_MAX_DEV:
        errors.append("②-b passes — the run-rate ladder would be admissible; numerator choice must be revisited")

    # --- excess cash (经营价值与超额现金 ①②) ------------------------------------------
    div_after = inp["dps_after_bs"] * sh                   # declared after the balance-sheet date: not yet out of BPS
    if inp["div_declared"] < div_after - 1e6:
        errors.append("div_declared (unpaid at the balance-sheet date) < dps_after_bs x shares")
    if inp['rev_min'] == 0:
        raise ValueError('historical operating-cash denominator is zero')
    rho = min(max(inp["ncx_min"] / inp["rev_min"], 0.0), CASH_CAP)   # lowest net-cash / revenue in FY2019–25
    anchor = rho * inp["rev_fy25"]
    c_ex_tot = inp["net_cash_ext"] - inp["div_declared"] - anchor
    if c_ex_tot == 0:
        raise ValueError('cash ownership ratio has a zero denominator')
    if abs(c_ex_tot - inp["c_ex"]) > 1e6:
        errors.append(f"c_ex {inp['c_ex']:.4e} != net_cash_ext − div_declared − anchor {c_ex_tot:.4e}")
    # parent share (① 归母份额), subsidiary-disclosure reading: KION's own extended net debt (its net
    # financial debt + the whole lease line, upper bound) at the 46.52% stake; the rest of the excess cash
    # at the ex-KION equity ratio.
    fx = inp["fx_eurcny"]
    kion_nc = -(inp["kion_nfd_eur"] * fx + inp["lease_liab"])
    kion_eq = inp["kion_eq_eur"] * fx
    eq_par = inp["parent_eq"] - div_after
    par_x = eq_par - inp["kion_stake"] * kion_eq
    min_x = inp["minority"] - (1 - inp["kion_stake"]) * kion_eq
    pr = ((c_ex_tot - kion_nc) * par_x / (par_x + min_x) + kion_nc * inp["kion_stake"]) / c_ex_tot
    pr_eqm = eq_par / (eq_par + inp["minority"])
    if abs(pr - inp["parent_ratio"]) > 5e-4:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = c_ex_tot * pr
    if c_ex < EX_TRIGGER * inp["equity"]:
        errors.append("parent-share c_ex below 15% of parent equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])   # after-tax income, out of every forward numerator
    cps = c_ex / sh
    c_ex_l = max(inp["ncx_l"] - rho * inp["rev_l"], 0.0) * pr  # FY2022's own excess cash, parent share
    c_inc_l = c_ex_l * inp["cash_yield_l"] * (1 - inp["tax_eff_l"])
    r_ss = inp["ronic_ss_power"]

    def pp(g2: float, roe: float) -> float:
        return path_pe(g2, roe, r, NUM_YEAR, int(inp["y1_power"]), int(inp["y2_power"]), r_ss)

    # --- legs -------------------------------------------------------------------
    disc = (1 + r) ** tau
    disc_w = (1 + r) ** (tau / 2)                             # window profit sits mid-window
    npm = inp["seg_margin"] * (1 - inp["seg_tax"])
    pw_revs = [inp["pw_rev_cmbi"], inp["pw_rev_ct"], inp["pw_rev_yh"]]
    if len(pw_revs) < 2:
        errors.append("power leg needs >= 2 houses with a same-scope FY2028 revenue")
    errors += ladder("power-leg FY2028 revenue (3 houses)", min(pw_revs), statistics.mean(pw_revs), max(pw_revs))
    pw_rev_m = statistics.mean(pw_revs)
    pw_ni = {"m": pw_rev_m * npm, "h": inp["cons_fy28_h"] * inp["shares"] - inp["cj_main"]}
    if not pw_ni["h"] >= pw_ni["m"]:
        errors.append("H power NI (长江 split) below the M power NI")
    if inp["pw_rev_cmbi"] < inp["lb_rev_fy28"]:
        errors.append("CMBI power-scope revenue must include its large-bore line")
    pw_ni_l = inp["ms_units_l"] * inp["ms_price"] * npm
    npm_pub = (inp['power_np_share_h1'] * inp['eps_h1'] * sh / inp['power_rev_h1']
               if inp['power_rev_h1'] else None)
    if not npm_pub:
        warnings.append('historical_public_margin_comparison_unavailable')
    if npm_pub and abs(npm / npm_pub - 1) > MARGIN_XCHK:
        errors.append(f"power-leg margin {npm:.1%} vs public cross-check {npm_pub:.1%} (> {MARGIN_XCHK:.0%})")
    kion = inp["kion_np_rr_eur"] * inp["kion_stake"] * inp["fx_eurcny"]
    kion_share = kion / inp['np_ttm'] if inp['np_ttm'] else None
    lo, hi = KION_SHARE_BAND
    if kion_share is None:
        warnings.append('historical_kion_share_comparison_unavailable')
    elif not (lo <= kion_share <= hi):
        errors.append(f"KION run-rate is {kion_share:.1%} of TTM NP, outside {lo:.0%}-{hi:.0%} (属性 A)")

    obps0 = inp["bps"] - inp["dps_after_bs"] - cps   # operating book: less any dividend declared after the BS date and the excess cash
    ci = c_inc / sh
    cons = {"m": (inp["cons_fy26_m"], inp["cons_fy27_m"], inp["cons_fy28_m"]),
            "h": (inp["cons_fy26_h"], inp["cons_fy27_h"], inp["cons_fy28_h"])}
    rows = {}
    for t, (e26, e27, e28) in cons.items():
        o26, o27, o28 = e26 - ci, e27 - ci, e28 - ci        # operating EPS (cash income out, all years)
        o_ytd = inp["eps_ytd"] - ci * VAL_DATE[1] / 12      # booked through the balance-sheet date
        np28 = o28 * sh
        roe = o28 / obps0
        unb = (o26 - o_ytd) + o27                            # unbooked operating EPS, rest of FY2026 + FY2027
        for _ in range(300):  # operating BPS roll, b = g/RONIC; only the power leg funds growth
            b = inp["g2_power"] * (pw_ni[t] / np28) / roe
            bps28 = obps0 + b * unb
            roe = o28 / bps28
        b = inp["g2_power"] * (pw_ni[t] / np28) / roe
        pe_c = pp(inp["g2_core"], roe)
        pe_p = pp(inp["g2_power"], roe)
        core = np28 - kion - pw_ni[t]
        w = max(unb * (1 - b), 0.0) / disc_w                 # window distributable profit (③ 时点对齐)
        parts = (core * pe_c / disc / sh, kion * inp["pe_kion"] / sh, pw_ni[t] * pe_p / disc / sh, cps, w)
        rows[t] = dict(np=np28, roe=roe, bps=bps28, b=b, pe_c=pe_c, pe_p=pe_p, core=core, parts=parts,
                       anchor=sum(parts), win=unb, w=w)
        errors += check_branch(inp["g2_power"], roe, r, inp["payout_op"], f"g2_power ({t.upper()})")
        if roe - r < 0.03:
            errors.append(f"{t.upper()}: RONIC {roe:.1%} not in the monotone zone")
        if b > 1 - inp["payout_obs"]:
            errors.append(f"{t.upper()}: b {b:.1%} > 1 − d (约束 1)")
        if inp["g2_power"] > (1 - inp["payout_obs"]) * roe:
            errors.append(f"{t.upper()}: g2_power above (1 − d) x RONIC (约束 2)")

    np_ttm_op = inp["np_ttm"] - c_inc
    eq_op = inp["equity"] - div_after - c_ex
    np_l_op = inp["np_l"] - c_inc_l
    if eq_op <= 0 or np_l_op <= 0 or np_ttm_op <= 0 or inp['n_rec_l'] <= 0:
        raise ValueError('trough recovery requires positive profit, equity and duration')
    roe_mid = np_ttm_op / eq_op
    if np_l_op / eq_op >= r:
        errors.append("RONIC_L >= r: L is not a trough tier (valuation-rules「谷底档」)")
    g1 = (np_ttm_op / np_l_op) ** (1 / inp["n_rec_l"]) - 1
    pe_l = recovery_two_stage_pe(g1, inp["n_rec_l"], inp["g2_core"], roe_mid, r)
    pe_p_l = pp(inp["g2_power"], roe_mid)
    kion_l = kion * inp["kion_l_factor"]
    core_l = np_l_op - kion_l - pw_ni_l
    if core_l <= 0:
        errors.append("L core profit <= 0")
    parts_l = (core_l * pe_l / sh, kion_l * inp["pe_kion"] / sh, pw_ni_l * pe_p_l / sh, cps)
    L = sum(parts_l)
    M, H = rows["m"]["anchor"], rows["h"]["anchor"]
    if not all(math.isfinite(value) for value in (L, M, H)) or not (L < M < H):
        raise ValueError(f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}")
    A, B = cut_points(L, M, H)

    # shape (裁决顺序 ⑤): the cyclical core leg must be reverse or flat
    if not (pe_l > rows["m"]["pe_c"] and abs(rows["h"]["pe_c"] - rows["m"]["pe_c"]) < 1e-9):
        errors.append("core multiple shape is not reverse/flat (cyclical, 裁决顺序 ⑤)")
    # flat-multiple ladder: every tier on the M-tier multiples
    flat_l = (core_l * rows["m"]["pe_c"] + kion_l * inp["pe_kion"] + pw_ni_l * rows["m"]["pe_p"]) / sh + cps
    flat = [flat_l] + [(rows[t]["core"] * rows["m"]["pe_c"] / disc + kion * inp["pe_kion"]
                        + pw_ni[t] * rows["m"]["pe_p"] / disc) / sh + cps + rows[t]["w"] for t in ("m", "h")]
    errors += ladder("flat-multiple", *flat)

    # --- V_opt: aftermarket only ------------------------------------------------
    option = aftermarket_option(inp, npm, rows['m']['pe_p'], r, disc, dict(zip('LMH', (L, M, H))))
    if option.get('status') == 'unavailable':
        warnings.append('historical_aftermarket_option_unavailable')
    if [k for k in inp if k == "p" or k.startswith("p_")]:
        errors.append("p-class fields must not appear in Inputs")

    # --- ③ band test: n/a without same-earnings months --------------------------
    same_eps_months = 0 if np_ttm_op / sh < 0.88 * (mean28 - ci) else None   # operating basis; TTM = all-time high
    if same_eps_months is None:
        errors.append("TTM EPS is now within 12% of the FY2028 numerator — run the ③ band test")

    # --- 周期票中枢 check on the core leg ---------------------------------------
    core_mid = inp["np_mid5"] - inp["cash_inc_mid5"] - kion - pw_ni_l   # each year less its own C_ex(t) income
    mid_ratio = rows['m']['core'] / core_mid if core_mid else None
    if mid_ratio is None:
        warnings.append('historical_midcycle_comparison_unavailable')
    m_mid = (core_mid * rows["m"]["pe_c"] + kion * inp["pe_kion"]) / sh + rows["m"]["parts"][2] + cps + rows["m"]["w"]

    # --- correction reconciliation gate ------------------------------------------
    e_m = mean28
    coords = {
        "① 上一版 M": PREV_M,
        "② E_op,M/r + c": (e_m - ci) / r / disc + cps,
        "③ D_M/(r-g)": inp["payout_obs"] * e_m / (r - inp["g2_core"]) / disc,
        "⑥ BPS x PB低点": inp["bps"] * inp["pb_own_min"],
    }
    inside = [k for k, v in coords.items() if not k.startswith("①") and v != 0 and abs(M / v - 1) <= GATE_BAND]
    gate_on = abs(M / PREV_M - 1) > GATE_TRIGGER
    if gate_on and not inside:
        errors.append("correction gate: new M is >20% away from every independent coordinate — BLOCKED")
    missing_ref = [k for k in NOT_FORMULA if k not in inp]
    if missing_ref:
        errors.append(f"reference rows missing: {missing_ref}")

    def band_at(g_pw: float | None = None, g_core: float | None = None, kion_pe: float | None = None,
                rs: float | None = None):
        gp = inp["g2_power"] if g_pw is None else g_pw
        gc = inp["g2_core"] if g_core is None else g_core
        kp = inp["pe_kion"] if kion_pe is None else kion_pe
        rss = r_ss if rs is None else rs
        y1, y2 = int(inp["y1_power"]), int(inp["y2_power"])
        out = []
        for t in ("m", "h"):
            x = rows[t]
            out.append((x["core"] * path_pe(gc, x["roe"], r, NUM_YEAR, y1, y2, rss) / disc + kion * kp
                        + pw_ni[t] * path_pe(gp, x["roe"], r, NUM_YEAR, y1, y2, rss) / disc) / sh + cps + x["w"])
        ll = (core_l * recovery_two_stage_pe(g1, inp["n_rec_l"], gc, roe_mid, r) + kion_l * kp
              + pw_ni_l * path_pe(gp, roe_mid, r, NUM_YEAR, y1, y2, rss)) / sh + cps
        return dict(zip("LMH", [ll] + out))

    own = [(core_l * inp["pe_ownyear_l"] + kion_l * inp["pe_kion"] + pw_ni_l * pe_p_l) / sh + cps] + [
        (rows[t]["core"] * inp[f"pe_ownyear_{t}"] / disc + kion * inp["pe_kion"] + pw_ni[t] * rows[t]["pe_p"] / disc) / sh
        + cps + rows[t]["w"] for t in ("m", "h")]
    def m_with_pw(ni_pw: float, t: str = "m") -> float:
        x = rows[t]
        return ((x["np"] - kion - ni_pw) * x["pe_c"] / disc + kion * inp["pe_kion"] + ni_pw * x["pe_p"] / disc) / sh + cps + x["w"]
    rep2 = statistics.mean(pw_revs[:2]) * npm
    if errors:
        warnings.append('historical_economic_guards_require_review')
    tiers = lambda v: dict(zip('LMH', v))
    def optional_value(fn):
        def finite(value):
            if isinstance(value, dict):
                return all(finite(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return all(finite(item) for item in value)
            return not isinstance(value, (int, float)) or math.isfinite(value)
        try:
            value = fn()
            if finite(value):
                return value
        except (ArithmeticError, TypeError, ValueError):
            pass
        warnings.append('historical_sensitivity_unavailable')
        return None
    h_share = None
    if inp['fx_hkdcny'] > 0:
        h_share = {'currency': 'HKD', 'anchors': tiers(x / inp['fx_hkdcny'] for x in (L, M, H)),
                   'cut_points': {'A': A / inp['fx_hkdcny'], 'B': B / inp['fx_hkdcny']}}
    else:
        warnings.append('historical_h_share_conversion_unavailable')
    # The historical study dates describe source material, not a confirmed
    # result: current dates are unknown until the complete basis is reviewed.
    return {
        'ticker': '000338.SZ', 'currency': 'CNY',
        'valuation_as_of': None, 'framework_as_of': None,
        'anchors': tiers((L, M, H)), 'candidate': None,
        'option': option,
        'review_flags': warnings,
        'segments': {
            'core': tiers((parts_l[0], rows['m']['parts'][0], rows['h']['parts'][0])),
            'kion': tiers((parts_l[1], rows['m']['parts'][1], rows['h']['parts'][1])),
            'power': tiers((parts_l[2], rows['m']['parts'][2], rows['h']['parts'][2])),
            'cash': tiers((cps, cps, cps)),
            'window': tiers((0.0, rows['m']['w'], rows['h']['w'])),
        },
        'key_parameters': {
            'core': {'discount_rate': tiers((r, r, r)), 'growth_rate': tiers((inp['g2_core'],)*3),
                     'forward_return': tiers((np_l_op / eq_op, rows['m']['roe'], rows['h']['roe'])),
                     'post_recovery_return': tiers((roe_mid, None, None)),
                     'steady_return': tiers((None, None, None))},
            'power': {'discount_rate': tiers((r, r, r)), 'growth_rate': tiers((inp['g2_power'],)*3),
                      'forward_return': tiers((roe_mid, rows['m']['roe'], rows['h']['roe'])),
                      'steady_return': tiers(tuple(min(v, r_ss) for v in (roe_mid, rows['m']['roe'], rows['h']['roe'])))},
        },
        'h_share': h_share,
        'operating': {'cash_per_share': cps, 'parent_ratio': pr, 'power_revenue_mean': pw_rev_m,
                      'power_profit': tiers((pw_ni_l, pw_ni['m'], pw_ni['h'])),
                      'kion_profit': tiers((kion_l, kion, kion)), 'core_profit': tiers((core_l, rows['m']['core'], rows['h']['core'])),
                      'recovery_growth': g1, 'recovery_years': inp['n_rec_l'], 'roe_trough': np_l_op / eq_op,
                      'recovery_multiple': pe_l, 'power_multiple': tiers((pe_p_l, rows['m']['pe_p'], rows['h']['pe_p'])),
                      'previous_coordinate': PREV_M, 'gate_triggered': gate_on, 'gate_inside_count': len(inside)},
        'sensitivity': {'power_growth_low': optional_value(lambda: band_at(g_pw=min(peer_g))),
                        'power_growth_high': optional_value(lambda: band_at(g_pw=max(peer_g))),
                        'power_growth_minus_1pp': optional_value(lambda: band_at(g_pw=inp['g2_power'] - .01)),
                        'power_growth_plus_1pp': optional_value(lambda: band_at(g_pw=inp['g2_power'] + .01)),
                        'core_growth_1pp': optional_value(lambda: band_at(g_core=.01)),
                        'core_growth_us': optional_value(lambda: band_at(g_core=inp['g2_core_us'])),
                        'kion_multiple_997': optional_value(lambda: band_at(kion_pe=9.97)),
                        'steady_return_wartsila': optional_value(lambda: band_at(rs=inp['ronic_ss_wrt'])),
                        'steady_return_forward': optional_value(lambda: band_at(rs=1.0)), 'ownyear': tiers(own),
                        'core_midcycle_m': m_mid,
                        'consensus_low_m': ((inp['cons_fy28_l']*sh-c_inc-kion-pw_ni['m'])*rows['m']['pe_c']/disc
                                            + kion*inp['pe_kion'] + pw_ni['m']*rows['m']['pe_p']/disc)/sh + cps + rows['m']['w'],
                        'trough_profit_flat': np_l_op/sh/r + cps, 'book_value_floor': inp['bps'],
                        'power_report_pair_m': m_with_pw(rep2), 'power_low_m': m_with_pw(min(pw_revs)*npm),
                        'power_high_m': m_with_pw(max(pw_revs)*npm), 'power_cmbi_large_bore_m': m_with_pw(inp['lb_rev_fy28']*npm),
                        'power_high_main_growth_h': m_with_pw(pw_ni['h'] - .05*inp['cj_main'], 'h'),
                        'power_high_three_house_h': m_with_pw(max(pw_revs)*npm, 'h')},
    }


def calculate(context):
    result = evaluate(dict(INPUTS), context['axes']['southbound'])
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments'] = {name: {'unit': 'CNY_PER_SHARE', 'values': values}
                          for name, values in result['segments'].items()}
    for leg in result['key_parameters'].values():
        for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return', 'post_recovery_return'):
            if name in leg:
                leg[name] = {'unit': 'RATIO', 'values': leg[name]}
    result['historical_financial_statement_as_of'] = '2026-09-30'
    result['historical_research_as_of'] = '2026-10-29'
    result['review_flags'].extend(['historical_cash_funding_and_kion_ownership_unverified',
                                   'historical_aftermarket_incremental_profit_unverified'])
    constants = {'unit_scale': YI, 'numerator_year': NUM_YEAR, 'today_year': TODAY_FY,
                 'option_weights': P_TIERS, 'kion_share_band': KION_SHARE_BAND,
                 'consensus_band': B2_MAX_DEV, 'midcycle_threshold': MID_MAX,
                 'gate_band': GATE_BAND, 'margin_comparison': MARGIN_XCHK,
                 'prior_middle': PREV_M, 'excess_cash_trigger': EX_TRIGGER, 'cash_cap': CASH_CAP,
                 'correction_gate': GATE_TRIGGER, 'balance_date': VAL_DATE, 'reference_fields': NOT_FORMULA}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed({'inputs': INPUTS, 'constants': constants}, BASELINE_LOCAL)
    return result
