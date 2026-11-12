"""ORCL historical SOTP migration draft; not a fresh financial analysis.

Original research attributes OCI residual profit and capital by estimation and
records a user decision to retain the 2026-09-27 out-of-band result. That
historical decision is not automatic approval of later changed inputs.
"""
from __future__ import annotations
import math
from typing import Callable
from lib.gordon import basket_r, check_basket_pair, check_g_cap, check_k_declared, check_r, payout, perpetual_pe
from lib.inputs import ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.historical_precision import historical_oci_reference, preserve_reference_residual

DEPENDENCIES = {"libraries": ("gordon", "inputs", "historical_precision", "partial_basis"),
                "axes": {"capex": "ai_capex", "funding": "frontier_lab_funding"}}
BN = 1e3
MIN_R_MINUS_G = 0.02
OCI_EBIT_MARGIN_CAP = 0.48
FY26_TOTAL_REVENUE = 67357.0
AWS_TURNOVER = 0.55
# Frozen AWS FY2024 reference used solely in the 2026-10-19 precision bridge;
# this is deliberately distinct from the editable current turnover above.
HISTORICAL_AWS_TURNOVER = 0.55
ROE_PROJ_TOL = 0.001
K_REMAIN_REL_TOL = 0.01
OPENAI_DOWNGRADE_BASKETS = (7, 6, 5, 4)
ROE_PROJ_H_AWS_2025 = 0.150
G_SW_PEER = 0.0544
INPUTS = {
    # **软件年金腿 r = 篮 4 龙头制造 10%**（license+support+SaaS 常规经营现金流，A22）；值 = `gordon.BASKET_R`，来源单元格篮号与值须一致（`check_r`）；OCI 两子腿另见 `r_oci_non` / `r_oci_open`; source/as-of: 2026-09-20
    'r_perp': 0.1,
    # **OCI · 非 OpenAI 订单子腿 r = 篮 4 龙头制造 10%**（已签约 RPO、对手方有自有资金 = 常规经营现金流、可见度高；A7 / A22）; source/as-of: 2026-09-20
    'r_oci_non': 0.1,
    # **OCI · OpenAI 订单子腿过渡篮 = 篮 7 单押 / 国别 / 故事 15%**（今天收入依赖对手方未落定融资；A7 / A22）；只用于把 FY29–31 窗口折回 FY28 起点；单篮对照 13 / 11 / 10% 见 Outputs; source/as-of: 2026-09-23
    'r_oci_open': 0.15,
    # **OCI · OpenAI 订单子腿终值篮 = 篮 4 龙头制造 10%**：OpenAI 做成了的世界里它是用自身收入付账的超大客户，与非 OpenAI 订单同类（`_AXIS.frontier-lab-funding` §3）；只用于资本化 \(K\times ROE_{proj}/r\) 与窗口每档的稳态价值；A22; source/as-of: 2026-09-23
    'r_oci_open_t': 0.1,
    # 正常化税率；Q1 FY27 non-GAAP ETR 16.9%（A3）; source/as-of: Ex-99.1 脚注 (5)
    'tax_rate': 0.17,
    # FY28E 稀释股数（百万）`估算`（A15）= 09-07 流通 3,023.7（10-Q 封面）+ 稀释效应 34（10-Q Q1 加权）+ RSU 净归属至 FY28 中点 ≈22；ATM 实际 141M 股已在 3,023.7 内; source/as-of: 10-Q 2026-08-31
    'shares_fy28': 3080.0,
    # FY26 Software 收入（license 4,737 + support 19,804）; source/as-of: Ex-99.1 表 10
    'rev_software_fy26': 24541.0,
    # FY26 Cloud applications 收入; source/as-of: Ex-99.1 表 10
    'rev_saas_fy26': 15888.0,
    # FY26 Hardware 收入; source/as-of: Ex-99.1 表 10
    'rev_hw_fy26': 3084.0,
    # FY26 Services 收入; source/as-of: Ex-99.1 表 10
    'rev_svc_fy26': 5743.0,
    # FY26 Cloud infrastructure 收入；Q1 FY27 7,388（+121%）; source/as-of: Ex-99.1 表 10
    'oci_rev_fy26': 18101.0,
    # Software 线 FY26→FY28 年增速 `估算`（Q1 −3%，license −15% / support −1%，A5）; source/as-of: 2026-09-12
    'g_software': -0.02,
    # SaaS 线年增速 `估算`（Q1 +10%）; source/as-of: 2026-09-12
    'g_saas': 0.1,
    # Hardware 线年增速 `估算`（Q1 +15%，FY26 +5%）; source/as-of: 2026-09-12
    'g_hw': 0.03,
    # Services 线年增速 `估算`（Q1 +5%）; source/as-of: 2026-09-12
    'g_svc': 0.05,
    # FY26 三分部 margin 合计（cloud&software 34,468 + hardware 2,017 + services 1,533）；**剔 SBC / 摊销 / R&D / G&A**; source/as-of: 10-K Note 13 表 70
    'seg_margin_fy26': 38018.0,
    # FY26 分部销售与市场费用合计（7,212 + 235），已在 `seg_margin_fy26` 内扣除；用于把 OCI 的 S&M 从软件腿剥出; source/as-of: 10-K Note 13 表 70
    'sm_total_fy26': 7447.0,
    # OCI 毛利率 `估算`（卖方 30–40%；Q1 成本线反推 ≈34%，A4）; source/as-of: JPM 100636 / Barclays 104792
    'oci_gm_est': 0.35,
    # 分部 S&M 中归 OCI 的比例 `估算`（A4）; source/as-of: 2026-09-12
    'oci_sm_share': 0.1,
    # FY26 分部以下经营成本 = R&D 10,272 + G&A 1,618 + 分部 SBC 1,618 + 分摊 395（不含摊销 1,671 与重组 1,838）; source/as-of: 10-K Note 13 表 71
    'below_seg_fy26': 13903.0,
    # 上述成本归软件腿的比例 `估算`（A4）；余 15% 归 OCI、已含在残差内; source/as-of: 2026-09-12
    'sw_share_below': 0.85,
    # 分部以下成本 FY26→FY28 年增速 `估算`; source/as-of: 2026-09-12
    'g_below': 0.03,
    # 软件腿永续增速（A5）；**无同业锚**（分线增速合成，未反解同业软件年金）；cap = min(6%, r − 4%) = 6%（篮 4）未收紧；\(r-g=7.5\%\) 远离极点; source/as-of: 2026-09-18
    'g2_sw': 0.025,
    # 股东权益 2026-08-31（含 ATM 19,909 与优先股 4,954）; source/as-of: 8-K 资产负债表
    'equity_aug': 67196.0,
    # 债务 2026-08-31 = 流动 7,625 + 非流动 117,712; source/as-of: 8-K 资产负债表
    'debt_aug': 125337.0,
    # 现金 36,369 + 有价证券 708; source/as-of: 8-K 资产负债表
    'cash_aug': 37077.0,
    # PP&E 净值 127,845 中归 OCI 的部分 `估算`（FY21 前公司 PP&E 仅 ~7B，A8）; source/as-of: 2026-09-12
    'oci_ppe_now': 120000.0,
    # FY28E non-GAAP EPS 共识**低端**（39 家）；L 档 ROE_proj 来源; source/as-of: yfinance 2026-09-11
    'eps_fy28_low': 9.0,
    # FY28E 共识**均值**；M 档 ROE_proj 来源、③ 同基分母; source/as-of: yfinance 2026-09-11
    'eps_fy28_mid': 11.02,
    # FY28E 共识**高端**；只作读数（H 档 ROE_proj 取 AWS 态，A18）; source/as-of: yfinance 2026-09-11
    'eps_fy28_high': 13.51,
    # FY28E 收入共识低端（38 家）；只用于反推各档 OCI 收入与隐含 margin（读数，不入锚点）; source/as-of: yfinance 2026-09-11
    'rev_fy28_low': 107657.0,
    # FY28E 收入共识均值；FY28 账面周转 = (rev − 软件线) ÷ `k_spent_gross`; source/as-of: yfinance 2026-09-11
    'rev_fy28_mid': 131127.0,
    # FY28E 收入共识高端; source/as-of: yfinance 2026-09-11
    'rev_fy28_high': 139642.0,
    # FY28E SBC `估算`（Q1 FY27 1,127/季 → 4.5B/年，微增）；从 non-GAAP 扣除（A3）; source/as-of: Ex-99.1 表 3
    'sbc_fy28': 4800.0,
    # FY28E 利息费用 `估算`（Q1 FY27 1,428/季 = 5.7B/年，债务续增）；加回成 NOPAT 后由闭合项统一扣净债; source/as-of: Ex-99.1 表 1
    'int_fy28': 7000.0,
    # OCI FY28 起点已花 gross 投入资本（= `oci_ppe_now` + `capex_rest_fy27` − `da_rest_fy27`，A8）；D 桶 \(K_{spent}\)，按 `rpo_share_openai` 拆两子腿 91,691 / 81,310；net-of-prepay 147,046 只作敏感性; source/as-of: 2026-09-20
    'k_spent_gross': 173001.0,
    # OpenAI 占 RPO 份额 `估算`（HSBC 99586 单家）；\(K_{spent}\)、\(K_{remain}\) 的子腿拆分权重（A19）; source/as-of: HSBC 2026-08-06
    'rpo_share_openai': 0.47,
    # H 档 ROE_proj = AWS-2024 态 0.55 × 0.37 × (1−0.17)（Amazon FY2025 10-K 分部数据）；敏感性 AWS-2025 态 0.150（A18）; source/as-of: AMZN 10-K FY2025
    'roe_proj_h': 0.169,
    # D 桶窗口年数 = FY29–31（管理层「约一半 RPO 36 个月内转化」）；窗口终点 FY2031（A19）; source/as-of: 电话会转述 ×4
    'window_years': 3.0,
    # FY27 余下三季毛 capex `估算` = 指引中值 92,500 − Q1 28,499; source/as-of: Ex-99.1 指引
    'capex_rest_fy27': 64001.0,
    # FY27 余下三季折旧 `估算`（Q1 3,156，逐季抬升）; source/as-of: 2026-09-12
    'da_rest_fy27': 11000.0,
    # 累计「含重大融资成分的客户预付款」`估算` = FY26Q4 4,592 + FY27Q1 11,363 + FY27 余下 10,000；作免息资本减 OCI IC，只作敏感性（A8）; source/as-of: Ex-99.1 表 9
    'prepay_cum': 25955.0,
    # FY27 余下三季 OCF `估算`（FY26 同期 23,838 + 净利/折旧抬升 + ~10,000 预付款；A11）; source/as-of: 2026-09-12
    'ocf_rest_fy27': 45000.0,
    # FY27 余下三季股息 = $0.50 × 3 × ~3,100M 股; source/as-of: Ex-99.1
    'div_rest_fy27': 4700.0,
    # 归母权益 2026-08-31（股东权益 67,196 − 少数股东权益 424）；归母比例 = 本项 ÷ `equity_aug` = 0.9937，乘在增长期资金缺口上（A24）; source/as-of: 8-K 资产负债表
    'equity_parent_aug': 66772.0,
    # 时点对齐：估值基准日 2026-08-31（Q1 资产负债表日）→ 分子年 FY2028 年初 2027-06-01 的年数；软件腿与 OCI 非 OpenAI 子腿按 10% 折、OpenAI 子腿按过渡篮 15% 折（A24）; source/as-of: 2026-08-31
    'tau': 0.75,
    # 回报路径第 1 年 = 分子年 FY2028（A25）; source/as-of: 2026-10-16
    't0': 2028.0,
    # 高回报期止点 = 可见年末 FY2028（默认路径，云厂商不继承 `_AXIS.ai-capex`；A25）; source/as-of: 2026-10-16
    'y1': 2028.0,
    # 稳态起点 = 可见年末 + 6（软件进入门槛「高」；A25）; source/as-of: 2026-10-16
    'y2': 2034.0,
    # 软件腿稳态回报 = 自身周期：FY2013–2022（上云投入前十年，非周期取 10 个完整财年）投入资本回报均值 20.7%（税后营业利润 ÷ 上年末权益 + 应付票据 + 租赁 − 现金与短期有价证券；SEC XBRL 10-K）；同业 / 兜底 30% 只作对照；≥ r、不超过前瞻 ROE（A25）; source/as-of: 2026-10-19
    'ronic_ss_sw': 0.207,
    # 6.50% Series D 强制可转优先股清偿额（50,000 股 × $100,000）；按负债扣、不计转股（A11）; source/as-of: 10-K Note 11
    'pref_liq': 4954.0,
    # FY27 收入指引下限「至少 $90B」；减软件线 FY27E 得 FY27E OCI ≈ 39,266（只作读数，A9）; source/as-of: Ex-99.1 指引
    'rev_guide_fy27': 90000.0,
    # RPO 2026-08-31；管理层「约一半 36 个月内转化」→ 110,667/年 = D 桶窗口的增量收入来源（`k_remain_yr_*`，A19）; source/as-of: Ex-99.1
    'rpo': 664000.0,
    # FY27Q1 capex；与 `dep_q1` 之比 = 折旧滞后倍数 9.0×（A10）; source/as-of: Ex-99.1 现金流量表
    'capex_q1': 28499.0,
    # FY27Q1 折旧; source/as-of: Ex-99.1 现金流量表
    'dep_q1': 3156.0,
    # FY27 capex 指引下沿 USD；`_AXIS.ai-capex.md` **构成方**校验用（A16）; source/as-of: Ex-99.1 / Cantor 转述
    'capex_guide_low': 90000000000.0,
    # FY27 capex 指引上沿 USD; source/as-of: Ex-99.1 / Cantor 转述
    'capex_guide_high': 95000000000.0,
    # trailing GAAP 稀释 EPS（含 FY26Q2 Ampere 一次性收益）；**只作披露分母，不入公式**（A12）; source/as-of: yfinance 2026-09-11
    'eps_ttm_gaap': 6.38,
    # **护栏（③）同基前瞻 PE 带实测底**（2022-09；月末价 ÷ 下一财年 non-GAAP EPS，2021-06→2026-09 n=64；FY23–26 事后实际、FY27–28 今日共识；A12）；`M / eps_fy28_mid ≥ pe_fwd_min` 不成立即 ③ 出带; source/as-of: `orcl_ev/fwdpe_ORCL_perfect_foresight.csv`
    'pe_fwd_min': 10.41,
    # 同一序列 p10; source/as-of: 同上
    'pe_fwd_p10': 13.32,
    # 同一序列中位; source/as-of: 同上
    'pe_fwd_med': 17.92,
    # 同一序列 p90; source/as-of: 同上
    'pe_fwd_p90': 24.33,
    # 同一序列实测顶（2025-09）；`H / eps_fy28_mid` 越出即红; source/as-of: 同上
    'pe_fwd_max': 34.16,
    # 自身 5 年 trailing GAAP PE 实测底（2021-09-20）；不同基、只披露（A12）; source/as-of: Longbridge 2026-09-07
    'pe_own_min': 17.24,
    # 同一序列实测中位；只披露; source/as-of: Longbridge 2026-09-07
    'pe_own_p50': 31.45,
    # 同一序列实测顶（2025-09-22）；只披露; source/as-of: Longbridge 2026-09-07
    'pe_own_max': 74.95,
    # **交叉校验专用**：JPM 13× EV / FY28E EBIT（105251）；不入底牌; source/as-of: Wisburg 105251
    'xchk_ev_ebit_low': 13.0,
    # **交叉校验专用**：HSBC Oracle 隐含 2028E EV/EBIT 14.0×（99586）；不入底牌; source/as-of: Wisburg 99586
    'xchk_ev_ebit_high': 14.0,
}

# Frozen reference inputs are exclusively for preserving the original rounded
# historical adopted values. They do not serve as current forecast inputs.
HISTORICAL_REFERENCE = {
    # Historical source: 正常化税率；Q1 FY27 non-GAAP ETR 16.9%（A3）; as-of: Ex-99.1 脚注 (5)
    'tax_rate': 0.17,
    # Historical source: FY28E 稀释股数（百万）`估算`（A15）= 09-07 流通 3,023.7（10-Q 封面）+ 稀释效应 34（10-Q Q1 加权）+ RSU 净归属至 FY28 中点 ≈22；ATM 实际 141M 股已在 3,023.7 内; as-of: 10-Q 2026-08-31
    'shares_fy28': 3080.0,
    # Historical source: FY26 Software 收入（license 4,737 + support 19,804）; as-of: Ex-99.1 表 10
    'rev_software_fy26': 24541.0,
    # Historical source: FY26 Cloud applications 收入; as-of: Ex-99.1 表 10
    'rev_saas_fy26': 15888.0,
    # Historical source: FY26 Hardware 收入; as-of: Ex-99.1 表 10
    'rev_hw_fy26': 3084.0,
    # Historical source: FY26 Services 收入; as-of: Ex-99.1 表 10
    'rev_svc_fy26': 5743.0,
    # Historical source: FY26 Cloud infrastructure 收入；Q1 FY27 7,388（+121%）; as-of: Ex-99.1 表 10
    'oci_rev_fy26': 18101.0,
    # Historical source: Software 线 FY26→FY28 年增速 `估算`（Q1 −3%，license −15% / support −1%，A5）; as-of: 2026-09-12
    'g_software': -0.02,
    # Historical source: SaaS 线年增速 `估算`（Q1 +10%）; as-of: 2026-09-12
    'g_saas': 0.1,
    # Historical source: Hardware 线年增速 `估算`（Q1 +15%，FY26 +5%）; as-of: 2026-09-12
    'g_hw': 0.03,
    # Historical source: Services 线年增速 `估算`（Q1 +5%）; as-of: 2026-09-12
    'g_svc': 0.05,
    # Historical source: FY26 三分部 margin 合计（cloud&software 34,468 + hardware 2,017 + services 1,533）；**剔 SBC / 摊销 / R&D / G&A**; as-of: 10-K Note 13 表 70
    'seg_margin_fy26': 38018.0,
    # Historical source: FY26 分部销售与市场费用合计（7,212 + 235），已在 `seg_margin_fy26` 内扣除；用于把 OCI 的 S&M 从软件腿剥出; as-of: 10-K Note 13 表 70
    'sm_total_fy26': 7447.0,
    # Historical source: OCI 毛利率 `估算`（卖方 30–40%；Q1 成本线反推 ≈34%，A4）; as-of: JPM 100636 / Barclays 104792
    'oci_gm_est': 0.35,
    # Historical source: 分部 S&M 中归 OCI 的比例 `估算`（A4）; as-of: 2026-09-12
    'oci_sm_share': 0.1,
    # Historical source: FY26 分部以下经营成本 = R&D 10,272 + G&A 1,618 + 分部 SBC 1,618 + 分摊 395（不含摊销 1,671 与重组 1,838）; as-of: 10-K Note 13 表 71
    'below_seg_fy26': 13903.0,
    # Historical source: 上述成本归软件腿的比例 `估算`（A4）；余 15% 归 OCI、已含在残差内; as-of: 2026-09-12
    'sw_share_below': 0.85,
    # Historical source: 分部以下成本 FY26→FY28 年增速 `估算`; as-of: 2026-09-12
    'g_below': 0.03,
    # Historical source: PP&E 净值 127,845 中归 OCI 的部分 `估算`（FY21 前公司 PP&E 仅 ~7B，A8）; as-of: 2026-09-12
    'oci_ppe_now': 120000.0,
    # Historical source: FY28E non-GAAP EPS 共识**低端**（39 家）；L 档 ROE_proj 来源; as-of: yfinance 2026-09-11
    'eps_fy28_low': 9.0,
    # Historical source: FY28E 共识**均值**；M 档 ROE_proj 来源、③ 同基分母; as-of: yfinance 2026-09-11
    'eps_fy28_mid': 11.02,
    # Historical source: FY28E 收入共识均值；FY28 账面周转 = (rev − 软件线) ÷ `k_spent_gross`; as-of: yfinance 2026-09-11
    'rev_fy28_mid': 131127.0,
    # Historical source: FY28E SBC `估算`（Q1 FY27 1,127/季 → 4.5B/年，微增）；从 non-GAAP 扣除（A3）; as-of: Ex-99.1 表 3
    'sbc_fy28': 4800.0,
    # Historical source: FY28E 利息费用 `估算`（Q1 FY27 1,428/季 = 5.7B/年，债务续增）；加回成 NOPAT 后由闭合项统一扣净债; as-of: Ex-99.1 表 1
    'int_fy28': 7000.0,
    # Historical source: FY27 余下三季毛 capex `估算` = 指引中值 92,500 − Q1 28,499; as-of: Ex-99.1 指引
    'capex_rest_fy27': 64001.0,
    # Historical source: FY27 余下三季折旧 `估算`（Q1 3,156，逐季抬升）; as-of: 2026-09-12
    'da_rest_fy27': 11000.0,
    # Historical source: RPO 2026-08-31；管理层「约一半 36 个月内转化」→ 110,667/年 = D 桶窗口的增量收入来源（`k_remain_yr_*`，A19）; as-of: Ex-99.1
    'rpo': 664000.0,
}
HISTORICAL_ADOPTED = {
    # Published historical adopted approximation; source: L 档 ROE_proj（gross 基）= `nopat_oci_L` 11,321 ÷ 173,001：共识低端、账面、无改善、OpenAI 半边未建（该子腿无窗口）（A18）; as-of: 2026-09-20
    'roe_proj_l': 0.065,
    # Published historical adopted approximation; source: M 档 ROE_proj = `nopat_oci_M` 17,543 ÷ 173,001：共识均值、账面、FY28 之后不改善（无共识来源）（A18）; as-of: 2026-09-20
    'roe_proj_m': 0.101,
    # Published historical adopted approximation; source: 窗口每年增量资本（L / M 档）= (rpo/2/3 − oci_rev_fy28_M) ÷ FY28 账面周转 0.455 = 31,937 ÷ 0.455；按份额拆 37,194 / 32,984（A19）; as-of: 2026-09-20
    'k_remain_yr_book': 70178.0,
    # Published historical adopted approximation; source: 窗口每年增量资本（H 档）= 31,937 ÷ AWS 周转 0.55；拆 30,776 / 27,291（A19）; as-of: 2026-09-20
    'k_remain_yr_aws': 58067.0,
}

# FY2026 GAAP 10-K, $M: EBITDA = 22,444 EBIT + 9,294 D&A;
# 97,647 net debt excludes lease; 124,295 includes lease; add 4,954
# preferred for the widest measure. Interest expense 4,599 / EBIT 22,444.
HISTORICAL_LEVERAGE = {"net_debt_ebitda_ex_lease": 3.1,
                       "net_debt_ebitda_including_lease": 3.9,
                       "net_debt_ebitda_lease_and_preferred": 4.1,
                       "interest_ebit": 0.205, "equity_multiplier": 6.2}

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on next-period earnings with the three-stage return path
    (valuation-rules「经营价值与超额现金」② 稳态回报三段).

    Year t = 1 is calendar t0.  The retention of calendar c earns the forward return
    while c <= y1, fades linearly to the stable return by y2, and the stable return
    from y2 on.  Stable return capped at the forward return and floored at r; a flat
    path equals `perpetual_pe`.
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
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, rs) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1


R_FIELDS = ("r_perp", "r_oci_non", "r_oci_open", "r_oci_open_t")

TIERS = ("l", "m", "h")
LINES = ("software", "saas", "hw", "svc")


def bisect(f: Callable[[float], float], lo: float, hi: float, iters: int = 100) -> float:
    """Root of a monotone f on [lo, hi]; the band is monotone in δ and in ROE_proj."""
    flo = f(lo)
    if flo * f(hi) > 0:
        raise ValueError(f"no sign change on [{lo}, {hi}]")
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2

def assert_flat_multiples(pe_sw: dict[str, float]) -> list[str]:
    """The software leg carries no per-tier multiple (A2e-2c); the OCI ladder is ROE_proj by design."""
    errs: list[str] = []
    for tier in ("l", "h"):
        if pe_sw[tier] != pe_sw["m"]:
            errs.append(
                f"software multiple ratio {tier}/m = {pe_sw[tier] / pe_sw['m']:.4f} != 1.000 "
                f"— multiples MUST be flat across tiers (A2e-2c)"
            )
    return errs


def _local_basis_snapshot(axes):
    return {
        'inputs': INPUTS,
        'constants': {'bn': BN, 'min_r_minus_g': MIN_R_MINUS_G, 'oci_margin_cap': OCI_EBIT_MARGIN_CAP,
                      'fy26_total_revenue': FY26_TOTAL_REVENUE, 'aws_turnover': AWS_TURNOVER,
                      'historical_aws_turnover': HISTORICAL_AWS_TURNOVER, 'roe_tolerance': ROE_PROJ_TOL,
                      'remaining_tolerance': K_REMAIN_REL_TOL, 'downgrade_baskets': OPENAI_DOWNGRADE_BASKETS,
                      'aws_2025_return': ROE_PROJ_H_AWS_2025, 'software_peer_growth': G_SW_PEER,
                      'historical_reference': HISTORICAL_REFERENCE, 'historical_adopted': HISTORICAL_ADOPTED,
                      'historical_leverage': HISTORICAL_LEVERAGE, 'rate_fields': R_FIELDS,
                      'tiers': TIERS, 'lines': LINES},
        'shared': {'capex': {'base': axes['capex']['base_2026_usd'], 'role': axes['capex']['role']},
                   'funding': {'haircut': axes['funding']['k_lab']}},
    }


# Historic numerical assumptions only; no claim of complete source provenance.
LOCAL_BASIS_BASELINE = '47f3f208a0c3bbf7e6f3e50ad29e14b7f5ff444939e5be1b3658f1688640b144'


def calculate(context):
    inp = dict(INPUTS)
    capex, funding = context["axes"]["capex"], context["axes"]["funding"]
    if capex["role"] != "constituent":
        raise ValueError("ORCL is a capital-spending pool constituent")
    inp["k_lab"] = funding["k_lab"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("inputs must be finite numbers")
    require_whole_years(inp, ("window_years", "t0", "y1", "y2"))
    if inp["r_perp"] <= inp["g2_sw"] or min(inp["r_perp"], inp["r_oci_non"],
            inp["r_oci_open"], inp["r_oci_open_t"]) <= 0:
        raise ValueError("discount or perpetual-growth rate is mathematically invalid")
    if inp["shares_fy28"] <= 0 or capex["base_2026_usd"] <= 0:
        raise ValueError("shares and shared capital-spending pool must be positive")
    review_flags = ["historical_out_of_band_user_decision_2026_09_27",
                    "oci_profit_and_assets_estimated_from_residual",
                    "funding_axis_haircut_evidence_pending",
                    "historical_approximation_residual_is_carried",
                    "fy2026_leverage_roe_multiplier_roic_reconciliation_incomplete",
                    "oci_ev_ebit_crosscheck_available_method_choice_pending"]
    if any(HISTORICAL_LEVERAGE[key] > 3 for key in
           ("net_debt_ebitda_ex_lease", "net_debt_ebitda_including_lease", "net_debt_ebitda_lease_and_preferred")):
        review_flags.append("fy2026_historical_leverage_threshold_triggered")
    baskets = {"r_perp": 4, "r_oci_non": 4, "r_oci_open": 7, "r_oci_open_t": 4}
    for field, basket in baskets.items():
        if check_r(inp[field], field, basket):
            review_flags.append("discount_basket_mismatch_" + field)
    if check_basket_pair(inp["r_oci_open"], inp["r_oci_open_t"], "oci_open", 7, 4):
        review_flags.append("openai_discount_pair_invalid")
    if check_k_declared(inp["r_oci_open"], inp["r_oci_open_t"], (inp["k_lab"],) * 3, "k_lab"):
        review_flags.append("shared_haircut_not_declared")
    if check_g_cap(inp["g2_sw"], inp["r_perp"], "g2_sw"):
        review_flags.append("software_growth_above_cap")
    if inp["r_perp"] - inp["g2_sw"] < MIN_R_MINUS_G:
        review_flags.append("software_growth_close_to_discount_rate")
    for label, keys in (("eps", ("eps_fy28_low", "eps_fy28_mid", "eps_fy28_high")),
                        ("revenue", ("rev_fy28_low", "rev_fy28_mid", "rev_fy28_high"))):
        if ladder(label, *(inp[key] for key in keys)):
            review_flags.append(label + "_not_increasing")
    if not 0 < inp["tax_rate"] < 0.5:
        review_flags.append("tax_rate_outside_historical_range")
    for key in ("oci_gm_est", "oci_sm_share", "sw_share_below", "rpo_share_openai"):
        if not 0 < inp[key] < 1:
            review_flags.append("input_ratio_outside_range_" + key)
    if not 0 < inp["oci_ppe_now"] < inp["equity_aug"] + inp["debt_aug"]:
        review_flags.append("oci_assets_outside_balance_sheet")
    if inp["window_years"] != 3:
        review_flags.append("rpo_window_differs_from_historical_three_year_assumption")
    if abs(sum(inp[f"rev_{ln}_fy26"] for ln in LINES) + inp["oci_rev_fy26"] - FY26_TOTAL_REVENUE) > 1:
        review_flags.append("fy2026_revenue_reconciliation_mismatch")
    if not inp["capex_guide_low"] <= inp["capex_guide_high"]:
        review_flags.append("capex_guidance_order_invalid")
    if not 0 < inp["capex_guide_high"] / capex["base_2026_usd"] < 1:
        review_flags.append("capex_constituent_share_outside_pool")
    if any(key.startswith("p_") for key in inp) or "v_opt" in inp:
        review_flags.append("option_double_counts_existing_project_window")
    r = inp["r_perp"]
    r_non, r_open, r_open_t = inp["r_oci_non"], inp["r_oci_open"], inp["r_oci_open_t"]
    k_lab = inp["k_lab"]
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_fy28"]
    n_win = int(inp["window_years"])
    share_open = inp["rpo_share_openai"]
    t0, y1, y2, tau = int(inp["t0"]), int(inp["y1"]), int(inp["y2"]), inp["tau"]
    sw_disc = (1 + r) ** tau  # ③ FY2028 opening -> 2026-08-31

    # ---- Step 1: software annuity leg, FY28E numerator (A4/A5) ----
    def rev_sw(years: int, source=None) -> float:
        data = inp if source is None else source
        return sum(data[f"rev_{ln}_fy26"] * (1 + data[f"g_{ln}"]) ** years for ln in LINES)

    def software_nopat(data, oci_gm):
        # This bridge is shared by current inputs and the frozen historical
        # input snapshot, so the rounding residual uses the identical formula.
        oci_contrib = data["oci_rev_fy26"] * oci_gm - data["sm_total_fy26"] * data["oci_sm_share"]
        margin_pct = (data["seg_margin_fy26"] - oci_contrib) / rev_sw(0, data)
        ebit = margin_pct * rev_sw(2, data) - data["below_seg_fy26"] * data["sw_share_below"] * (1 + data["g_below"]) ** 2
        return ebit * (1.0 - data["tax_rate"])

    rev_sw_fy26 = rev_sw(0)
    rev_sw_fy28 = rev_sw(2)

    def software_leg(oci_gm: float, g_sw: float) -> tuple[float, float, float, float]:
        """(NOPAT, IC, ROE, PE) of the software leg under a given OCI-GM bridge."""
        nopat = software_nopat(inp, oci_gm)
        ic = (inp["equity_aug"] + inp["debt_aug"] - inp["cash_aug"]) - inp["oci_ppe_now"]
        roe = nopat / ic
        # ② forward ROE through y1, fading to ronic_ss_sw (own cycle FY2013-22, 20.7%) by y2.
        return nopat, ic, roe, path_pe(g_sw, roe, r, t0, y1, y2, inp["ronic_ss_sw"])

    nopat_sw, ic_sw, roe_sw, pe_sw_m = software_leg(inp["oci_gm_est"], inp["g2_sw"])
    v_sw = nopat_sw * pe_sw_m / sw_disc
    pe_sw_flat = perpetual_pe(inp["g2_sw"], roe_sw, r)  # disclosure: no fade
    oci_contrib_fy26 = inp["oci_rev_fy26"] * inp["oci_gm_est"] - inp["sm_total_fy26"] * inp["oci_sm_share"]
    sw_margin_pct = (inp["seg_margin_fy26"] - oci_contrib_fy26) / rev_sw_fy26

    if ic_sw <= 0:
        review_flags.append('software_invested_capital_nonpositive')
    pay_sw = payout(inp["g2_sw"], roe_sw)
    if not (0.0 < pay_sw <= 1.0):
        review_flags.append('software_payout_outside_range')
    pe_sw = {t: pe_sw_m for t in TIERS}
    if assert_flat_multiples(pe_sw):
        review_flags.append("software_multiple_not_flat")

    # ---- Step 3: OCI residual of the consensus EPS range -> ROE_proj L / M (A2/A3/A18) ----
    eps = {"l": inp["eps_fy28_low"], "m": inp["eps_fy28_mid"], "h": inp["eps_fy28_high"]}
    rev_fy28 = {"l": inp["rev_fy28_low"], "m": inp["rev_fy28_mid"], "h": inp["rev_fy28_high"]}

    def nopat_total(e: float) -> float:
        ni_gaaplike = e * sh - inp["sbc_fy28"] * keep
        return ni_gaaplike + inp["int_fy28"] * keep

    nopat_oci = {t: nopat_total(eps[t]) - nopat_sw for t in TIERS}
    oci_rev_fy28 = {t: rev_fy28[t] - rev_sw_fy28 for t in TIERS}
    oci_margin = {t: nopat_oci[t] / keep / oci_rev_fy28[t] for t in TIERS}

    # A residual that turns negative means the software bridge has swallowed
    # the company; the implied margin must sit under the sell-side GM ceiling.
    for t in TIERS:
        if nopat_oci[t] <= 0:
            review_flags.append('oci_residual_profit_nonpositive' + "_" + t)
        if not (0.0 < oci_margin[t] <= OCI_EBIT_MARGIN_CAP):
            review_flags.append('oci_ebit_margin_outside_reference' + "_" + t)

    k_spent = inp["oci_ppe_now"] + inp["capex_rest_fy27"] - inp["da_rest_fy27"]
    if abs(k_spent - inp["k_spent_gross"]) > 1.0:
        review_flags.append('oci_spent_capital_reconciliation_mismatch')
    k_net = k_spent - inp["prepay_cum"]
    if k_net <= 0:
        review_flags.append('prepayment_adjusted_capital_nonpositive')
    # The 2026-10-19 research adopted project returns rounded to 6.5% /
    # 10.1%, and annual capital estimates 70,178 / 58,067 million. Their
    # underlying ratios are more precise than those adopted inputs. Carry the
    # difference between the historical adopted and historical unrounded
    # values unchanged, while applying every new change in the underlying
    # forecast, RPO, capital and software bridge immediately. The snapshot is
    # historical calibration evidence, not a second current-input source.
    # Historical software formula, leg list and AWS turnover are frozen in a
    # separate source-bound reference, so changes to today's model cannot move
    # the historical side and silently cancel their own effect.
    historical_raw = historical_oci_reference(HISTORICAL_REFERENCE, HISTORICAL_AWS_TURNOVER)
    hist_residual = {"l": historical_raw["roe_l"], "m": historical_raw["roe_m"]}
    roe_resid = {t: nopat_oci[t] / k_spent for t in TIERS}
    # H is AWS 2024 external benchmark, not the FY2028 high residual.
    roe_proj = {"l": preserve_reference_residual(roe_resid["l"], hist_residual["l"], HISTORICAL_ADOPTED["roe_proj_l"]),
                "m": preserve_reference_residual(roe_resid["m"], hist_residual["m"], HISTORICAL_ADOPTED["roe_proj_m"]),
                "h": inp["roe_proj_h"]}
    if ladder("roe_proj", *(roe_proj[t] for t in TIERS)):
        review_flags.append("project_return_not_increasing")
    turnover_book = oci_rev_fy28["m"] / k_spent
    rpo_run_rate = inp["rpo"] / 2.0 / 3.0
    incr_rev = rpo_run_rate - oci_rev_fy28["m"]
    hist_book = historical_raw["capital_book"]
    hist_aws = historical_raw["capital_aws"]
    raw_book, raw_aws = incr_rev / turnover_book, incr_rev / AWS_TURNOVER
    adopted_book = preserve_reference_residual(raw_book, hist_book, HISTORICAL_ADOPTED["k_remain_yr_book"])
    adopted_aws = preserve_reference_residual(raw_aws, hist_aws, HISTORICAL_ADOPTED["k_remain_yr_aws"])
    k_remain = {"l": adopted_book, "m": adopted_book, "h": adopted_aws}
    if min(adopted_book, adopted_aws) < 0:
        review_flags.append("estimated_remaining_project_capital_negative")
    # L world: the OpenAI half is never built, so its sub-leg has no window (A6).
    open_window = {"l": False, "m": True, "h": True}

    # ---- Step 4: OCI D-bucket project value, two sub-legs (A6/A7/A19) ----
    def sub_leg(
        k: float, r_cap: float, r_disc: float, roe: float, kr: float, window: bool, n: int, keep_k: float = 1.0
    ) -> tuple[float, float]:
        """(base, window) in $M.

        Capital is capitalised at r_cap (the steady state it earns in) and each
        window tranche is discounted back at r_disc (the road to it); keep_k is
        the certainty-equivalent haircut on the value.  A single-basket
        sub-leg passes r_cap == r_disc and keep_k == 1.
        """
        base = k * roe / r_cap
        win = sum(kr * (roe / r_cap - 1.0) / (1.0 + r_disc) ** t for t in range(1, n + 1)) if window else 0.0
        return base * keep_k, win * keep_k

    def oci_value(
        t: str,
        roe: float | None = None,
        r_n: float = r_non,
        r_o: float = r_open,
        r_ot: float = r_open_t,
        kl: float = k_lab,
        kr: float | None = None,
        share: float = share_open,
        n: int = n_win,
        k: float = k_spent,
    ) -> dict[str, float]:
        roe = roe_proj[t] if roe is None else roe
        kr = k_remain[t] if kr is None else kr
        bn, wn = sub_leg(k * (1 - share), r_n, r_n, roe, kr * (1 - share), True, n)
        bo, wo = sub_leg(k * share, r_ot, r_o, roe, kr * share, open_window[t], n, 1.0 - kl)
        # ③ valued at the FY2028 opening; tau back at each sub-leg's road rate.
        dn, do = (1 + r_n) ** tau, (1 + r_o) ** tau
        bn, wn, bo, wo = bn / dn, wn / dn, bo / do, wo / do
        return {"base_non": bn, "win_non": wn, "base_open": bo, "win_open": wo, "total": bn + wn + bo + wo}

    parts = {t: oci_value(t) for t in TIERS}
    v_oci = {t: parts[t]["total"] for t in TIERS}
    for t in TIERS:
        if v_oci[t] <= 0:
            review_flags.append('oci_project_value_nonpositive' + "_" + t)

    # ---- Step 5: closing item (A11) ----
    # Today's net debt and preferred (no roll to FY28); the rest-FY27 capex beyond
    # OCF is the ① growth-period funding gap x parent share, debt-like.  Dividends
    # paid after the valuation date are not added back (the price is ex-dividend).
    net_debt_aug = inp["debt_aug"] - inp["cash_aug"]
    burn_rest_fy27 = inp["capex_rest_fy27"] - inp["ocf_rest_fy27"] + inp["div_rest_fy27"]
    parent = inp["equity_parent_aug"] / inp["equity_aug"]
    gap = max(inp["capex_rest_fy27"] - inp["ocf_rest_fy27"], 0.0) * parent
    net_debt_fy28 = net_debt_aug + burn_rest_fy27  # old roll, disclosure only
    closure = -(net_debt_aug + inp["pref_liq"] + gap)

    def per_share(v_oci_leg: float, v_sw_leg: float = v_sw, close: float = closure, shares: float = sh) -> float:
        return (v_sw_leg + v_oci_leg + close) / shares

    def band_at(**kw) -> tuple[float, float, float]:
        return tuple(per_share(oci_value(t, **kw)["total"]) for t in TIERS)  # type: ignore[return-value]

    # ---- Step 6: anchors ----
    L, M, H = band_at()
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        review_flags.append("base_anchors_not_increasing")

    # ---- Step 7: ③ guardrail on the same-basis forward band, 降篮 path (A12/A20/A21) ----
    pe_fwd = {t: v / eps["m"] for t, v in zip(TIERS, (L, M, H))}
    out_of_band = pe_fwd["m"] < inp["pe_fwd_min"]
    downgrade = []
    # Reference coordinates: the OpenAI sub-leg as ONE basket b, no haircut
    # (the pre-pair reading).  The pair sits between 篮 7 and 篮 4 by
    # construction, so 篮 4 un-haircut is the most lenient rate reading.
    for b in OPENAI_DOWNGRADE_BASKETS:
        band_b = band_at(r_o=basket_r(b), r_ot=basket_r(b), kl=0.0)
        downgrade.append((b, basket_r(b), band_b, band_b[1] / eps["m"]))
    out_after_downgrade = out_of_band and all(pe_m < inp["pe_fwd_min"] for _, _, _, pe_m in downgrade)
    if pe_fwd["h"] > inp["pe_fwd_max"]:
        review_flags.append('high_anchor_above_historical_multiple_band')

    # 表2′: uniform δ on both OCI sub-legs (software leg untouched, ROE_proj M
    # unchanged) that lifts M exactly to the band floor; and its ROE_proj twin.
    m_floor = inp["pe_fwd_min"] * eps["m"]

    def m_at_delta(d: float) -> float:
        return per_share(oci_value("m", r_n=r_non + d, r_o=r_open + d, r_ot=r_open_t + d)["total"])

    def m_at_roe(z: float) -> float:
        return per_share(oci_value("m", roe=z)["total"])

    try:
        delta_floor = bisect(lambda d: m_at_delta(d) - m_floor, -0.09, 0.05)
    except ValueError:
        delta_floor = None
        review_flags.append("historical_band_edge_rate_shift_unavailable")
    try:
        roe_floor = bisect(lambda z: m_at_roe(z) - m_floor, 0.05, 0.6)
    except ValueError:
        roe_floor = None
        review_flags.append("historical_band_edge_project_return_unavailable")
    band_edge = (None if delta_floor is None else
                 band_at(r_n=r_non + delta_floor, r_o=r_open + delta_floor, r_ot=r_open_t + delta_floor))

    if out_of_band:
        review_flags.append("middle_multiple_below_historical_band")
    if out_after_downgrade:
        review_flags.append("middle_multiple_below_band_after_rate_comparison")
    def band_dict(values):
        return dict(zip(("L", "M", "H"), values))
    def oci_part(name, tier):
        return (parts[tier]["base_" + name] + parts[tier]["win_" + name]) / sh
    segments = {
        "software": {"unit": "USD_PER_SHARE", "values": dict.fromkeys(("L", "M", "H"), v_sw / sh)},
        "oci_non_openai": {"unit": "USD_PER_SHARE", "values": {t.upper(): oci_part("non", t) for t in TIERS}},
        "oci_openai": {"unit": "USD_PER_SHARE", "values": {t.upper(): oci_part("open", t) for t in TIERS}},
        "debt_preferred_and_funding": {"unit": "USD_PER_SHARE", "values": dict.fromkeys(("L", "M", "H"), closure / sh)},
    }
    project_returns = {t.upper(): roe_proj[t] for t in TIERS}
    sensitivity = {
        "shared_lab_haircut_zero": band_dict(band_at(kl=0.0)),
        "shared_lab_haircut_50pct": band_dict(band_at(kl=0.5)),
        "aws_2025_return_high": per_share(oci_value("h", roe=ROE_PROJ_H_AWS_2025)["total"]),
        "project_return_minus_2pp": band_dict(tuple(per_share(oci_value(t, roe=roe_proj[t] - 0.02)["total"]) for t in TIERS)),
        "project_return_plus_2pp": band_dict(tuple(per_share(oci_value(t, roe=roe_proj[t] + 0.02)["total"]) for t in TIERS)),
        "window_2_years": band_dict(band_at(n=2)), "window_4_years": band_dict(band_at(n=4)),
        "openai_share_40pct": band_dict(band_at(share=0.4)), "openai_share_60pct": band_dict(band_at(share=0.6)),
        "remaining_capital_80pct": band_dict(tuple(per_share(oci_value(t, kr=k_remain[t] * 0.8)["total"]) for t in TIERS)),
        "remaining_capital_120pct": band_dict(tuple(per_share(oci_value(t, kr=k_remain[t] * 1.2)["total"]) for t in TIERS)),
        "spent_capital_net_of_prepay": band_dict(band_at(k=k_net)),
        "net_debt_minus_20bn_middle": per_share(v_oci["m"], close=closure + 20000),
        "net_debt_plus_20bn_middle": per_share(v_oci["m"], close=closure - 20000),
        "one_year_extra_discount": band_dict(tuple(v / (1 + r) for v in (L, M, H))),
        "ev_ebit_13": band_dict(tuple(per_share(nopat_oci[t] / keep * inp["xchk_ev_ebit_low"]) for t in TIERS)),
        "ev_ebit_14": band_dict(tuple(per_share(nopat_oci[t] / keep * inp["xchk_ev_ebit_high"]) for t in TIERS)),
        "software_no_return_fade_middle": per_share(v_oci["m"], nopat_sw * pe_sw_flat / sw_disc),
    }
    for d, label in ((-0.01, "software_growth_minus_1pp"), (0.01, "software_growth_plus_1pp"),
                     (G_SW_PEER - inp["g2_sw"], "software_peer_growth_reference")):
        n_, _, _, p_ = software_leg(inp["oci_gm_est"], inp["g2_sw"] + d)
        sensitivity[label] = per_share(v_oci["m"], n_ * p_ / sw_disc)
    sensitivity["oci_without_alignment_discount_middle"] = per_share(
        v_oci["m"] + sum(parts["m"][key] * ((1 + (r_non if "non" in key else r_open)) ** tau - 1)
                          for key in ("base_non", "win_non", "base_open", "win_open")))
    return {
        "ticker": "ORCL.US", "currency": "USD", "valuation_as_of": None, "framework_as_of": None,
        "historical_valuation_as_of": "2026-08-31", "historical_framework_as_of": "2026-10-19",
        "basis_changed": None, "partial_basis_changed": local_basis_changed(_local_basis_snapshot(context['axes']), LOCAL_BASIS_BASELINE), "units": {"price": "USD_PER_SHARE"},
        "anchors": band_dict((L, M, H)), "candidate": None, "option": None,
        "segments": segments,
        "key_parameters": {
            "software": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r)},
                         "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["g2_sw"])},
                         "forward_return": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), roe_sw)},
                         "steady_return": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), min(roe_sw, max(inp["ronic_ss_sw"], r))),
                                           "reference_value": inp["ronic_ss_sw"]}},
            "oci_non_openai": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r_non)},
                               "forward_return": {"unit": "RATIO", "values": project_returns}},
            "oci_openai": {"transition_discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r_open)},
                            "terminal_discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r_open_t)},
                            "forward_return": {"unit": "RATIO", "values": project_returns}},
        },
        "diagnostics": {"software_value_usd_million": v_sw, "software_nopat_usd_million": nopat_sw,
                        "software_operating_capital_usd_million": ic_sw, "oci_parts_usd_million": parts,
                        "oci_residual_nopat_usd_million": nopat_oci, "oci_revenue_fy28_usd_million": oci_rev_fy28,
                        "oci_residual_margin": oci_margin, "spent_capital_usd_million": k_spent,
                        "remaining_capital_per_year_usd_million": k_remain, "funding_gap_usd_million": gap,
                        "project_return_before_historical_residual": roe_resid,
                        "remaining_capital_before_historical_residual_usd_million": {"book": raw_book, "aws": raw_aws},
                        "historical_rounded_residual": {
                            "roe_l": HISTORICAL_ADOPTED["roe_proj_l"] - hist_residual["l"],
                            "roe_m": HISTORICAL_ADOPTED["roe_proj_m"] - hist_residual["m"],
                            "capital_book_usd_million": HISTORICAL_ADOPTED["k_remain_yr_book"] - hist_book,
                            "capital_aws_usd_million": HISTORICAL_ADOPTED["k_remain_yr_aws"] - hist_aws},
                        "historical_fy2026_leverage": HISTORICAL_LEVERAGE,
                        "historic_interest_100bp_check_required": HISTORICAL_LEVERAGE["interest_ebit"] > 1 / 3,
                        "capex_guidance_share_low": inp["capex_guide_low"] / capex["base_2026_usd"],
                        "capex_guidance_share_high": inp["capex_guide_high"] / capex["base_2026_usd"],
                        "historical_band_multiple": pe_fwd,
                        "single_basket_comparisons": {str(b): band_dict(band) for b, _, band, _ in downgrade},
                        "band_edge": None if band_edge is None else band_dict(band_edge),
                        "band_edge_rate_shift": delta_floor, "band_edge_project_return": roe_floor},
        "sensitivity": sensitivity, "review_flags": review_flags,
    }
