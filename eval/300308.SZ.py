"""300308 historical migration draft; no document is a calculation input.

Historical sources and modelling intent were transcribed from the prior
framework and script. This is a draft; shared-axis field contracts and
same-input numerical equivalence have not been verified. Axis snapshots must
be supplied by the runner and must reflect the actual selected source version.
"""
from __future__ import annotations

import math
from lib.gordon import check_branch, check_g_cap, check_r, check_transition_years, implied_g, payout
from lib.inputs import require_whole_years
from lib.partial_basis import local_basis_changed
from lib.tiers import decompose, flat_multiple_ladder
from lib.valuation_guards import require_axis_alignment

# Provisional names, to be reconciled with the shared-axis migration; these
# modules do not exist yet, so the ordinary entry must fail closed until then.
DEPENDENCIES = {"libraries": ("gordon", "inputs", "tiers", "valuation_guards", "partial_basis"), "axes": {
    "pluggable": "pluggable_module", "capex": "ai_capex", "optical": "optical_comms"}}
NPO_INTERP_YEAR = 2029
NPO_LAST_NAMED = 2030
NUM_YEAR = 2027
N_STAGE = 1
CONSENSUS_YEARS_BEYOND = 1
MIN_R_MINUS_G = 0.02
P_TIERS = (0.3, 0.6, 1.0)
TIERS = ("L", "M", "H")
BASKETS = {"r_perp": 4}  # Original decision: non-commodity, unconcentrated module business.

INPUTS = {
    # FY2026 EPS 共识均值（yfinance `0y`，4 家 28.10–30.90；三季报当日重拉未变）；只作对照; source/as-of: 2026-10-29
    'eps_fy26_cons': 29.9435,
    # FY2026 收入共识均值（yfinance `0y`，15 家；三季报当日重拉未变）= L 消化年的收入起点；隐含 Q4 约 406 亿（前三季度实测 695.47 亿），财报后若下修 L 随之下移；A3; source/as-of: 2026-10-29
    'rev_fy26_cons': 110122.98,
    # FY2025 实测净利率 = 归母净利 10,797.25 ÷ 收入 38,239.94（年报）；L 净利率；NPO 单位经济只作下界披露（A3 / A13）; source/as-of: 2025-12-31
    'nm_fy25': 0.2824,
    # L 消化年收入较 FY26 共识回落幅度；A3; source/as-of: 派生
    'rev_cut_l': 0.3,
    # FY2027 EPS 共识下沿（yfinance `+1y`，4 家；三季报当日重拉未变）；档内坐标，不入锚; source/as-of: 2026-10-29
    'eps_fy27_l': 49.38,
    # FY2027 EPS 共识均值 = M 分子来源（A 股股本口径；三季报当日重拉未变）；A2; source/as-of: 2026-10-29
    'eps_fy27_m': 66.49575,
    # FY2027 EPS 共识上沿 = H 分子来源（同一记录两端）；A2; source/as-of: 2026-10-29
    'eps_fy27_h': 84.333,
    # A 股股本 = 卖方 EPS 的股本口径（卖方尚未按注销更新）；A1; source/as-of: 2026-06-30
    'shares_a': 1115.234641,
    # 总股本 1,177.909641 − 9 月回购股份 5.653063（2026-10-29 董事会决议改为注销，待临时股东会审议；回购现金已出、股份不再流通）；A1; source/as-of: 2026-10-29
    'shares_total': 1172.256578,
    # UBS FY2027 EPS（Wisburg 100474）；A4; source/as-of: 2026-08-12
    'ubs_eps27': 60.69,
    # UBS FY2028 EPS；A4; source/as-of: 2026-08-12
    'ubs_eps28': 84.96,
    # 花旗 FY2027 归母净利（Wisburg 96363）；A4; source/as-of: 2026-07-17
    'citi_ni27': 97000.0,
    # 花旗 FY2028 归母净利；A4; source/as-of: 2026-07-17
    'citi_ni28': 167000.0,
    # FY2028 NPO 占收入（UBS；花旗按同比例，A11）; source/as-of: 2026-08-12
    'npo_share_28': 0.1,
    # UBS FY2028 收入 3,293 亿；A13; source/as-of: 2026-08-12
    'ubs_rev28': 329300.0,
    # 花旗 FY2028 净利率（明示，Wisburg 96363）；与 UBS FY28 净利率（`ubs_eps28` × `shares_a` ÷ `ubs_rev28`，A1 股本口径）均值 = 对齐年份公司级共识净利率，作 NPO 单位经济共享拍值；A13; source/as-of: 2026-07-17
    'citi_nm28': 0.365,
    # NPO 兑现年 = 公司具名「2027 年下半年量产、2028 年更大规模出货」（投资者关系活动记录 2026-08-24）；A13; source/as-of: 2026-08-24
    't_opt': 2028.0,
    # 归母权益（三季报资产负债表；H 股募资、9 月回购（库存股 4,998.65）、中期股息均已在内）；A5; source/as-of: 2026-09-30
    'equity_q3': 94363.02,
    # 应付股利（三季报「其他应付款」下；2026 中期股息，2026-10-12 除息）：类债项从现金扣（A25）; source/as-of: 2026-09-30
    'div_payable': 1033.05,
    # FY26 第四季度未入账净利 = 长桥季度共识 Q4（三季报当日重拉为空，沿用 2026-09-29 值）；A5; source/as-of: 2026-09-29
    'ni_q4_cons': 12340.18,
    # 扩展口径净现金 2026-09-30 = 货币资金 53,532.49 − 短期借款 336.18 − 一年内到期非流动负债 870.49 − 长期借款 485.93 − 租赁负债 163.56 − 长期应付款 5,063.00（三季报注明为「子公司增资事项涉及的回购义务」，类债扣，A25）；**不含**交易性金融资产 2,279.64（主要是上游核心供应商上市公司股票的战略持股，非现金，A25）; source/as-of: 2026-09-30
    'net_cash_ext_q3': 46613.33,
    # 超额现金（合并口径）= `net_cash_ext_q3` − `div_payable` − 经营所需现金锚 0 − 增长期资金缺口 0（A25）；进估值的是 × `parent_ratio`; source/as-of: 2026-09-30
    'c_ex': 45580.28,
    # 少数股东权益（百万 CNY，三季报）；归母比例用（A25）; source/as-of: 2026-09-30
    'minority_q3': 4951.08,
    # 归母比例 = `equity_q3` ÷（`equity_q3` + `minority_q3`）；无子公司级现金披露（A25）；eval 重算校验; source/as-of: 2026-09-30
    'parent_ratio': 0.9501,
    # 时点对齐 τ = 估值基准日 2026-09-30 → 分子年初 2027-01-01（3 个月）；经营价值 ÷ (1+r)^τ，2026 第四季度窗口可分配利润 ÷ (1+r)^(τ/2)（A26）; source/as-of: 2026-09-30
    'tau': 0.25,
    # M 档稳态回报（三档各取各的稳态，用户 2026-10-19 认可）= 去周期的中档前瞻：常态净利率 `nm_norm_main` 20% × AI 之前（2018–23）资产周转约 1.05 = 21%；利润率台阶 FY2024–25 已入财报、门槛判中 → 中档较按序值 18% 上调（差 ≥ 2pp）；同时消掉「常态净利率 20% 只配 18% 回报要求周转 0.9、低于任何一年」的矛盾（A26）; source/as-of: 2026-10-19
    'ss_return_m': 0.21,
    # H 档稳态回报（三档各取各的稳态，2026-10-19）= 去周期的高档前瞻：短缺期净利率先换常态 `nm_norm_main` 20% × 自身 2018–25 平均周转（收入 ÷ 年初经营股权）1.33 = 26.6%；≥ 中档 18%、≤ 30%、≤ 高档前瞻 209.8%；L / M 取按序值 `ss_return`（A26）; source/as-of: 2026-10-19
    'ss_return_h': 0.266,
    # 自身一轮周期经营回报 14.4%（2018–2025 GAAP 净利扣年初超额现金收益 ÷ 年初经营股权，与前瞻同口径）；老模块时代读数，结构变化后自身不可用，只作对照、不进稳态（A26）; source/as-of: 2026-10-16
    'own_cycle': 0.144,
    # 主业常态净利率 20%（用户 2026-10-19 裁定）：各档起点净利率（L = FY2025 实测 28.24%，M / H = FY2028 公司级共识 32.64%）持有到 `y1` 2028、线性回落、`y2` 2032 到位，此后永续；回落理由 = CPO 在 scale-out 替代可插拔 + 竞争（A26）; source/as-of: 2026-10-19
    'nm_norm_main': 0.2,
    # 近封装期权腿前瞻回报 = 旧账面口径 H 档 ROE 94.3%（主线 2026-10-15 裁定期权腿沿用）；`y1_npo` 2030 → `y2_npo` 2035 回落到 `ss_return` 18%（A13）; source/as-of: 2026-10-19
    'npo_roe': 0.943,
    # 近封装期权常态净利率 = `nm_norm_main` 20%（同一公司同一常态，用户 2026-10-19 裁定；eval 校验相等）；FY2028 净利率 32.64% 持有到 `y1_npo` 2030、2035 回落到本值（A13）; source/as-of: 2026-10-19
    'npo_nm_norm': 0.2,
    # UBS 2030 年 NPO 占收入 30%（Wisburg 100474；单家路径）：2030 NPO 收入 = UBS FY28 可插拔 × (1 + g2)² × 0.30 / 0.70 ≈ 1,322 亿（按增量处理，可插拔另计）；2029 为 2028 与 2030 的几何插值年（A13）; source/as-of: 2026-08-12
    'npo_share_30': 0.3,
    # 现金收益率 = H 股募资（约 525 亿元人民币，占超额现金大头）2026 第三季度利息收入 1.36 亿（三季报业绩变动说明）÷ 7-30 至 9-30 共 62 天、年化；原 FY2025 全公司 2.94% 已不代表以港币为主的现金（A25）; source/as-of: 2026-09-30
    'cash_yield': 0.0152,
    # 实际所得税率 2026 前三季度 = 所得税 37.42 ÷ 利润总额 278.38 亿（三季报；管理层指引 13–14%）（A25）; source/as-of: 2026-09-30
    'tax_eff': 0.1344,
    # 经营口径派息率 = 分红 10.8% + 现金积累 17.5%（Δ超额现金 84.27 亿扣股权融资 45.38 亿），FY2018–25 归母利润合计 222.44 亿为分母（A25）；`check_branch` 用; source/as-of: FY2025
    'payout_op': 0.282,
    # 篮 4 常规经营：光模块器件，盈利非商品价函数，客户集中未达篮 7 阈值（A15）；`check_r`; source/as-of: 2026-09-28
    'r_perp': 0.1,
    # NPO 2030 年之后的增速 2%（用户 2026-10-19 认可，与主业 g2 同值）：2030 年已按 UBS 路径到占收入 30%，此后不再给额外跑道；原光通信同业横截面 6%（`LITE.US` A16 旧混簇读数截顶）只作敏感（A13）; source/as-of: 2026-10-19
    'g_npo': 0.02,
    # L「视同派出现金」打折（消化世界增长关掉）；来源 ②；A20; source/as-of: 2026-09-29
    'k_l': 0.0,
    # M：原 0.20 乘在整个经营价值上，2026-10-16 框架纠正去掉（A20）; source/as-of: 2026-10-16
    'k_m': 0.0,
    # H：原 0.30 同上去掉（A20）; source/as-of: 2026-10-16
    'k_h': 0.0,
    # 实付派息率（2025 年 14%、2026 中期 10%）；只进分支校验与披露; source/as-of: 2026-08-22
    'payout_obs': 0.12,
    # 自身当期财年前瞻**经营** PE 带下沿（2025-04-23；整股权口径 9.09）；A17; source/as-of: 2026-09-27
    'pe_own_min': 8.92,
    # 同序列上沿（2026-06-21；整股权口径 45.59）；A17; source/as-of: 2026-09-27
    'pe_own_max': 45.63,
    # FY2027 收入共识均值（yfinance `+1y`）；只算 ai-capex 宽口径份额; source/as-of: 2026-09-29
    'rev_fy27_cons': 219648.45,
    # USD/CNY（yfinance `CNY=X` 收盘）；轴份额换算; source/as-of: 2026-09-28
    'usdcny': 6.7128,
    # UBS 2027 年 3.2T NPO 出货（只）；A18; source/as-of: 2026-08-12
    'npo_units_27': 50000.0,
    # UBS 2028 年 NPO 出货（只）；A18; source/as-of: 2026-08-12
    'npo_units_28': 2500000.0,
}


def optical_narrow_checks(narrow, optical):
    # Original check: narrow OE revenue may not exceed the OE BOM pool.
    return ["optical_attachment_exceeds_pool_" + tier.lower()
            for tier in TIERS
            if narrow[tier] > optical["oe"][tier] * optical["oe_bom_usd"] * (1 + 1e-9)]


def check_inputs(inp, baskets):
    flags = []
    if "r_perp" not in baskets or check_r(inp["r_perp"], "r_perp", baskets.get("r_perp")):
        flags.append("discount_rate_basket_mismatch")
    for key in ("g2", "g_npo"):
        if check_g_cap(inp[key], inp["r_perp"], key):
            flags.append(key + "_above_growth_cap")
        if inp["r_perp"] - inp[key] < MIN_R_MINUS_G:
            flags.append(key + "_too_close_to_discount_rate")
    if inp["g2"] <= 0:
        flags.append("growth_incompatible_with_rising_consensus")
    if check_transition_years(N_STAGE, CONSENSUS_YEARS_BEYOND, "g1"):
        flags.append("transition_year_not_supported_by_consensus")
    if not inp["eps_fy27_l"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]:
        flags.append("forecast_eps_not_increasing")
    if not (0 < inp["rev_cut_l"] < 1 and 0 < inp["nm_fy25"] < 1 and 0 < inp["npo_share_28"] < 1):
        flags.append("revenue_margin_or_npo_share_outside_range")
    if any(inp[f"k_{key}"] != 0 for key in "lmh"):
        flags.append("removed_legacy_value_haircut_reintroduced")
    if inp["shares_a"] >= inp["shares_total"]:
        flags.append("a_share_count_not_below_total")
    if inp["t_opt"] <= NUM_YEAR:
        flags.append("npo_realization_not_after_numerator_year")
    if not 0 < inp["citi_nm28"] < 1:
        flags.append("citi_margin_outside_range")
    if not inp["npo_share_28"] < inp["npo_share_30"] < 1:
        flags.append("npo_share_path_not_increasing")
    if abs(inp["npo_nm_norm"] - inp["nm_norm_main"]) > 1e-9:
        flags.append("main_and_npo_normal_margins_differ")
    if not inp["t_opt"] <= inp["y1_npo"] < inp["y2_npo"]:
        flags.append("npo_return_fade_years_invalid")
    if not 0 < inp["nm_norm_main"] < 1:
        flags.append("normal_margin_outside_range")
    if any(key == "p" or key.startswith("p_") for key in inp):
        flags.append("option_probability_inside_base_inputs")
    return flags


def lin_path(cal: int, a: float, b: float, y1: int, y2: int) -> float:
    """a through y1, linear to b by y2, b after (稳态回报三段 / 未建模期权 单位经济回落)."""
    return a if cal <= y1 else (b if cal >= y2 else a + (b - a) * (cal - y1) / (y2 - y1))


def path_value(g1: float, n: int, g2: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float,
               m_ratio: float = 1.0) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段) per unit of t0 earnings at the start of
    t0: n transition years at g1 (retention g1/roe), then g2 with RONIC = roe through y1, linear to
    min(roe, r_s) by y2, perpetual after.  The profit stream is scaled by the margin path: 1 through y1,
    linear to min(1, m_ratio) = normal / starting net margin by y2, that ratio after (A26, 2026-10-19)."""
    ss = min(roe, r_s)
    mr = min(1.0, m_ratio)
    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        cal = t0 + t - 1
        pv += e * lin_path(cal, 1.0, mr, y1, y2) * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * mr * payout(g2, ss) / ((r - g2) * (1 + r) ** (t - 1))
        ro = lin_path(cal, roe, ss, y1, y2)
        pv += e * lin_path(cal, 1.0, mr, y1, y2) * payout(g2, ro) / (1 + r) ** t
        e *= 1 + g2
        t += 1



def _local_basis_snapshot(axes):
    return {
        'inputs': INPUTS,
        'constants': {'npo_interpolation_year': NPO_INTERP_YEAR, 'npo_last_named': NPO_LAST_NAMED,
                      'numerator_year': NUM_YEAR, 'stage_years': N_STAGE,
                      'consensus_years_beyond': CONSENSUS_YEARS_BEYOND, 'min_r_minus_g': MIN_R_MINUS_G,
                      'option_weights': P_TIERS, 'tiers': TIERS, 'baskets': BASKETS},
        'shared': {
            'pluggable': {'growth': axes['pluggable']['g2_pluggable'], 'alignment': axes['pluggable']['t_align'],
                          'return': axes['pluggable']['ss_return_plug'], 'start': axes['pluggable']['y1_plug'],
                          'end': axes['pluggable']['y2_plug']},
            'capex': {'role': axes['capex']['role'], 'rungs': axes['capex']['rungs'],
                      'start': axes['capex']['y1_ai_capex_package'],
                      'end': axes['capex']['y2_ai_capex_package'],
                      'floor': axes['capex']['ss_floor_ai_capex_package']},
            'optical': {'engines': axes['optical']['oe'], 'bom': axes['optical']['oe_bom_usd']},
        },
    }


# Local inputs and specifically used shared values only. Source versions,
# formulas, full basis and user confirmation are tracked independently.
LOCAL_BASIS_BASELINE = '1b6dbb8e41d952d832560d3147e5735d64b16a5747a8fe76f7a6ac0d40eb7821'


def calculate(context):
    inp = dict(INPUTS)
    shared = context["axes"]
    plug, capex, optical = shared["pluggable"], shared["capex"], shared["optical"]
    # This peer-ruler's alignment year is the FY28 transition observation;
    # a changed shared year requires a new earnings path, not a silent splice.
    require_axis_alignment(plug, NUM_YEAR + N_STAGE)
    # All shared facts used by this ticker come exclusively from the three
    # injected axis snapshots. No ticker-local duplicate can override them.
    inp.update({"g2": plug["g2_pluggable"], "ss_return": plug["ss_return_plug"],
                "y1": plug["y1_plug"], "y2": plug["y2_plug"],
                "y1_npo": capex["y1_ai_capex_package"], "y2_npo": capex["y2_ai_capex_package"],
                "ss_return_npo": capex["ss_floor_ai_capex_package"],
                **{f"capex_{tier.lower()}": capex["rungs"][tier] for tier in TIERS},
                **{f"oe_{tier.lower()}": optical["oe"][tier] for tier in TIERS}})
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in inp.values()):
        raise ValueError("inputs must be finite numbers")
    require_whole_years(inp, ("t_opt", "y1", "y2", "y1_npo", "y2_npo"))
    # The source has two named observations, 2028 and 2030, and 2029 is the
    # intervening interpolation. Reusing them for a changed first year would
    # overwrite an observation or invent a different path.
    if int(inp["t_opt"]) + 1 != NPO_INTERP_YEAR or int(inp["t_opt"]) + 2 != NPO_LAST_NAMED:
        raise ValueError("NPO dated observation path must be rebuilt for the changed first year")
    if inp["r_perp"] <= max(inp["g2"], inp["g_npo"]) or inp["r_perp"] <= -1:
        raise ValueError("perpetuity or discount factor is mathematically invalid")
    if any(optical["oe"][tier] <= 0 for tier in TIERS) or optical["oe_bom_usd"] <= 0:
        raise ValueError("optical axis OE pool must be positive")
    # Historical user decisions and evidence gaps remain visible in the result;
    # they are not waived merely because this is a migration.
    review_flags = ["growth_reference_single_comparable",
                    "npo_single_broker_volume_path",
                    "cyclical_middle_uses_forward_consensus"]
    review_flags.extend(check_inputs(inp, BASKETS))
    r, g2 = inp["r_perp"], inp["g2"]
    sh = inp["shares_total"]  # 百万股; money inputs are 百万 CNY
    adj = inp["shares_a"] / sh

    # ---- Step 1: numerators (FY27, per total share) ----
    eps = {
        "L": inp["rev_fy26_cons"] * (1 - inp["rev_cut_l"]) * inp["nm_fy25"] / sh,
        "M": inp["eps_fy27_m"] * adj,
        "H": inp["eps_fy27_h"] * adj,
    }
    # ---- Step 2: FY28 transition, NPO stripped (A4 / A11) ----
    g_total = (inp["ubs_eps28"] / inp["ubs_eps27"] + inp["citi_ni28"] / inp["citi_ni27"]) / 2
    g1 = g_total * (1 - inp["npo_share_28"]) - 1
    stage = {"L": False, "M": True, "H": True}

    # ---- Step 3: FY27 opening book, excess cash, fixed point on b = g/RONIC (A5 / A25) ----
    # 2026-09-30 balance sheet (Q3 report): H-share proceeds and the September buyback are inside it.
    div = inp["div_payable"]  # 应付股利 on the Q3 balance sheet (interim, ex 2026-10-12): debt-like
    eq0 = inp["equity_q3"]
    c_tot = inp["net_cash_ext_q3"] - div  # operating-cash anchor 0 (A25)
    if abs(c_tot - inp["c_ex"]) > 1.0:
        review_flags.append('excess_cash_reconciliation_mismatch')
    pr = eq0 / (eq0 + inp["minority_q3"])          # ① 归母份额: no subsidiary cash disclosure
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        review_flags.append('parent_share_reconciliation_mismatch')
    c_ex = c_tot * pr
    if c_ex < 0.15 * eq0:
        review_flags.append('excess_cash_below_materiality_threshold')
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])  # after-tax, out of every numerator
    cps = c_ex / sh
    eop = {t: eps[t] - c_inc / sh for t in TIERS}
    tau = inp["tau"]
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    r_s = inp["ss_return"]
    # M steady: de-cycled M forward (normal margin x pre-AI turnover 1.05; the margin step is in the
    # FY2024-25 reports, medium barrier -> raised, A26); H: normal margin x own mean turnover 1.33.
    if abs(inp["ss_return_m"] - round(inp["nm_norm_main"] * 1.05, 3)) > 5e-4:
        review_flags.append('middle_steady_return_turnover_mismatch')
    if not r_s + 0.02 - 1e-9 <= inp["ss_return_m"] <= inp["ss_return_h"] + 1e-9:
        review_flags.append('middle_steady_return_outside_ruling_range')
    if not inp["ss_return_m"] - 1e-9 <= inp["ss_return_h"] <= 0.30 + 1e-9:
        review_flags.append('high_steady_return_outside_ruling_range')
    if abs(inp["ss_return_h"] - round(inp["nm_norm_main"] * 1.33, 3)) > 5e-4:
        review_flags.append('high_steady_return_turnover_mismatch')
    # Ordered pick (2026-10-19): own cycle unusable (no full cycle after the structural change), so the
    # steady return is the axis value as-is (checked against the axis above); own_cycle is display only.

    # Margin path (A26, 2026-10-19): each tier's starting net margin (L: FY25 realised; M / H: FY2028
    # company-level consensus = the shortage-period margin) held through y1, linear to nm_norm_main by y2.
    nm_ubs28 = inp["ubs_eps28"] * inp["shares_a"] / inp["ubs_rev28"]
    nm_opt = (nm_ubs28 + inp["citi_nm28"]) / 2
    nm0 = {"L": inp["nm_fy25"], "M": nm_opt, "H": nm_opt}

    def mratio(t: str, norm: float | None = None) -> float:
        return (inp["nm_norm_main"] if norm is None else norm) / nm0[t]

    def tier(e: float, with_g1: bool, g: float = g2, cash: float = cps, rs: float | None = None,
             yy: tuple[int, int] | None = None, mr: float = 1.0) -> tuple[float, float, float, float]:
        """(operating BPS_open, RONIC, three-stage multiple, b) for one FY27 numerator."""
        grow = g1 if with_g1 else g
        bps = (eq0 + inp["ni_q4_cons"]) / sh - cash
        for _ in range(300):
            roe = e / bps
            nxt = (eq0 + inp["ni_q4_cons"] * min(1.0, grow / roe)) / sh - cash
            if abs(nxt - bps) < 1e-12:
                break
            bps = nxt
        roe = e / bps
        a1, a2 = yy or (y1, y2)
        pe = path_value(g1 if with_g1 else 0.0, N_STAGE if with_g1 else 0, g, roe, r, NUM_YEAR, a1, a2,
                        r_s if rs is None else rs, m_ratio=mr)
        return bps, roe, pe, min(1.0, grow / roe)

    def window(b: float) -> float:
        """4Q26 window distributable profit per share (③ 时点对齐), discounted tau/2."""
        return max(inp["ni_q4_cons"] - tau * c_inc, 0.0) * (1 - b) / sh * (1 + r) ** -(tau / 2)

    bps, roe, pe, bb_ = {}, {}, {}, {}
    # Per-tier steady (retention「三档各取各的稳态」2026-10-19): L = the ordered value (axis 18%);
    # M = normal margin 20% x pre-AI turnover 1.05 = 21%; H = normal margin 20% x own mean turnover
    # 1.33 = 26.6% (A26).
    rs_tier = {"L": r_s, "M": inp["ss_return_m"], "H": inp["ss_return_h"]}
    for t in TIERS:
        bps[t], roe[t], pe[t], bb_[t] = tier(eop[t], stage[t], mr=mratio(t), rs=rs_tier[t])
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    pre = {t: eop[t] * pe[t] * (1 + r) ** -tau for t in TIERS}  # operating value, aligned to today
    win = {t: window(bb_[t]) for t in TIERS}
    L, M, H = (pre[t] * (1 - k[t]) + win[t] + cps for t in TIERS)
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        review_flags.append('base_anchors_not_increasing')
    ret_obs = 1 - inp["payout_obs"]
    for t in TIERS:
        if roe[t] - r < 0.03:
            review_flags.append('return_outside_monotone_domain' + "_" + t.lower())
        if check_branch(g2, roe[t], r, inp["payout_op"], f"g2@{t}"):
            review_flags.append("retention_branch_incompatible_" + t.lower())
        if g2 > ret_obs * roe[t]:  # ③ constraint 2: g <= (1 - d) x RONIC
            review_flags.append('growth_exceeds_observed_retention_capacity' + "_" + t.lower())
    for t in ("M", "H"):
        if not (0 < g1 / roe[t] < 1):
            review_flags.append('transition_reinvestment_outside_range' + "_" + t.lower())

    # ③ guardrail: M operating multiple inside own realised operating forward-PE band (A17).
    if not (inp["pe_own_min"] <= pe["M"] <= inp["pe_own_max"]):
        review_flags.append('middle_multiple_outside_historical_band')

    # ---- Step 5: NPO option (A13): aligned-year margin, own ruler, timed discount ----
    # Count (A13, 2026-10-19): UBS single-house path — 2028 NPO = 10% of FY28 revenue; 2030 NPO = 30% of
    # total revenue with NPO on top of the pluggable main business (FY28 pluggable x (1+g2)^2: incremental,
    # scale-up takes copper's share); 2029 geometric interpolation (插值年); after 2030 g_npo.
    t_opt = int(inp["t_opt"])
    y1n, y2n = int(inp["y1_npo"]), int(inp["y2_npo"])
    rev28_npo = inp["ubs_rev28"] * inp["npo_share_28"]
    plug28 = inp["ubs_rev28"] * (1 - inp["npo_share_28"])
    plug30 = plug28 * (1 + g2) ** (NPO_LAST_NAMED - t_opt)

    def npo_path(share30: float = inp["npo_share_30"], after: float = inp["g_npo"], end: int = 2100) -> dict[int, float]:
        rev30 = plug30 * share30 / (1 - share30)
        path = {t_opt: rev28_npo, NPO_INTERP_YEAR: (rev28_npo * rev30) ** 0.5, NPO_LAST_NAMED: rev30}
        for yr in range(NPO_LAST_NAMED + 1, end + 1):
            path[yr] = path[yr - 1] * (1 + after)
        return path

    npo_ni = rev28_npo * nm_opt
    eps_npo = npo_ni / sh
    roe_book_h = inp["npo_roe"]  # option leg's forward return: the old H-tier book ROE (ruling 2026-10-15)

    def npo_value(nm_norm: float, path: dict[int, float] | None = None, g_term: float | None = None,
                  a1: int = y1n, a2: int = y2n) -> float:
        """NPO stream per share at the start of t_opt: margin (nm_opt) and return (npo_roe) held to a1,
        linear to nm_norm / the steady return by a2, normal after; payout 1 - g_t/ROE_t (negative = the
        capital the ramp needs); Gordon at g_term once past a2 and the last named jump."""
        p = path or npo_path()
        gt = inp["g_npo"] if g_term is None else g_term
        # The NPO leg sits on the packaging link: its steady is that link's axis floor (A13), not the
        # pluggable-module 18% of the main leg.
        ss = min(roe_book_h, inp["ss_return_npo"])
        pv, yr = 0.0, t_opt
        while True:
            t = yr - t_opt + 1
            e = p[yr] * lin_path(yr, nm_opt, nm_norm, a1, a2) / sh
            if yr >= a2 and yr > NPO_LAST_NAMED:
                return pv + e * payout(gt, ss) / ((r - gt) * (1 + r) ** (t - 1))
            g_t = p[yr + 1] / p[yr] - 1
            pv += e * payout(g_t, lin_path(yr, roe_book_h, ss, a1, a2)) / (1 + r) ** t
            yr += 1

    disc = (1 + r) ** (inp["t_opt"] - NUM_YEAR + tau)
    v_opt_t = npo_value(inp["npo_nm_norm"])
    pe_npo = v_opt_t / eps_npo
    v_opt = v_opt_t / disc
    plus_v = tuple(x + p * v_opt for x, p in zip((L, M, H), P_TIERS))

    # ---- A2e-2c flat ladder + decomposition ----
    flat_errs, flat_op = flat_multiple_ladder((eop["L"], eop["M"], eop["H"]), pe["M"] * (1 - k["M"]))
    if flat_errs:
        review_flags.append("flat_numerator_ladder_invalid")
    flat = tuple(x * (1 + r) ** -tau + win[t] + cps for x, t in zip(flat_op, TIERS))
    # Decomposition on the operating part (anchor - C_ex per share); full L/M, H/M printed beside it.
    dec = decompose((L - cps, M - cps, H - cps),
                    (pe["L"] * (1 - k["L"]), pe["M"] * (1 - k["M"]), pe["H"] * (1 - k["H"])))

    # ---- Axes (A18) ----
    npo_asp_cny = inp["ubs_rev28"] * inp["npo_share_28"] / inp["npo_units_28"]  # 百万 CNY / unit
    narrow = {
        # Axis tiers are one year (2028): L = delayed a year (2027 volume), M = H = UBS 2028.
        "L": inp["npo_units_27"] * npo_asp_cny * 1e6 / inp["usdcny"],
        "M": inp["ubs_rev28"] * inp["npo_share_28"] * 1e6 / inp["usdcny"],
        "H": inp["ubs_rev28"] * inp["npo_share_28"] * 1e6 / inp["usdcny"],
    }
    review_flags.extend(optical_narrow_checks(narrow, optical))
    oe = {"L": inp["oe_l"], "M": inp["oe_m"], "H": inp["oe_h"]}


    def anchor(t, g=g2, g1_override=None, steady=None, norm=None):
        _, forward, multiple, retained = tier(eop[t], stage[t], g,
            rs=rs_tier[t] if steady is None else steady, mr=mratio(t, norm))
        if stage[t] and g1_override is not None:
            multiple = path_value(g1_override, N_STAGE, g, forward, r, NUM_YEAR,
                                  y1, y2, rs_tier[t] if steady is None else steady,
                                  m_ratio=mratio(t, norm))
        return eop[t] * multiple * (1 - k[t]) * (1 + r) ** -tau + window(retained) + cps

    def margin_band(norm):
        return {tier: anchor(tier, norm=norm) for tier in TIERS}

    # Original sensitivity inputs and interpolation are retained; these are
    # comparison cases only, not additional official bands.
    alt_total = (84.96 / 60.69 + 1670 / 970 + 79 / 59.89 + 82.4 / 59.67) / 4
    alt_g1 = alt_total * (1 - inp["npo_share_28"]) - 1
    sensitivity = {
        "normal_margin_12pct": {"anchors": margin_band(0.12), "option": npo_value(0.12) / disc},
        "normal_margin_15pct": {"anchors": margin_band(0.15), "option": npo_value(0.15) / disc},
        "normal_margin_28pct": {"anchors": margin_band(0.28), "option": npo_value(0.28) / disc},
        "no_margin_fade": {"anchors": {t: anchor(t, norm=nm0[t]) for t in TIERS},
                           "option": npo_value(nm_opt) / disc},
        "growth_minus_1pp": {t: anchor(t, g=g2 - 0.01) for t in TIERS},
        "growth_plus_1pp": {t: anchor(t, g=g2 + 0.01) for t in TIERS},
        "growth_4pct": {t: anchor(t, g=0.04) for t in TIERS},
        "four_house_growth": {t: anchor(t, g1_override=alt_g1) for t in TIERS},
        "forward_return_no_fade": {t: anchor(t, steady=1.0) for t in TIERS},
        "capex_default_window": {
            t: eop[t] * tier(eop[t], stage[t], yy=(2030, 2035), mr=mratio(t),
                             rs=rs_tier[t])[2] * (1 + r) ** -tau + win[t] + cps
            for t in TIERS},
        "option_growth_6pct": npo_value(inp["npo_nm_norm"], path=npo_path(after=0.06), g_term=0.06) / disc,
        "option_growth_0pct": npo_value(inp["npo_nm_norm"], path=npo_path(after=0), g_term=0) / disc,
        "option_fixed_2028_volume": npo_value(inp["npo_nm_norm"],
            path={year: rev28_npo * (1 + inp["g_npo"]) ** (year - t_opt)
                  for year in range(t_opt, 2101)}) / disc,
        "option_cannibalization": v_opt - npo_value(inp["npo_nm_norm"], a1=y1, a2=y2) / disc,
        "option_cannibalization_growth_6pct": (
            npo_value(inp["npo_nm_norm"], path=npo_path(after=0.06), g_term=0.06)
            - npo_value(inp["npo_nm_norm"], path=npo_path(after=0.06), g_term=0.06,
                        a1=y1, a2=y2)) / disc,
    }
    for cut, key in ((0.2, "revenue_decline_20pct"), (0.4, "revenue_decline_40pct")):
        earnings = inp["rev_fy26_cons"] * (1 - cut) * inp["nm_fy25"] / sh - c_inc / sh
        _, _, multiple, retained = tier(earnings, False, mr=mratio("L"))
        sensitivity[key] = earnings * multiple * (1 + r) ** -tau + window(retained) + cps

    # Each business's actual terminal return is capped by its forward return.
    # An option is an independent conditional result; its weights are not
    # statistical probabilities and must not be added again elsewhere.
    return {
        "ticker": "300308.SZ", "currency": "CNY",
        "valuation_as_of": None, "framework_as_of": None,
        "historical_valuation_as_of": "2026-09-30", "historical_framework_as_of": "2026-10-29",
        "basis_changed": None, "partial_basis_changed": local_basis_changed(_local_basis_snapshot(context['axes']), LOCAL_BASIS_BASELINE),
        "units": {"price": "CNY_PER_SHARE"},
        "anchors": dict(zip(TIERS, (L, M, H))), "candidate": None,
        "option": {"value": v_opt, "value_unit": "CNY_PER_SHARE", "weights": dict(zip(TIERS, P_TIERS)),
                   "anchors": dict(zip(TIERS, plus_v))},
        "segments": {
            "pluggable_module_and_window": {"unit": "CNY_PER_SHARE",
                "values": {t: pre[t] * (1 - k[t]) + win[t] for t in TIERS}},
            "excess_cash": {"unit": "CNY_PER_SHARE", "values": dict.fromkeys(TIERS, cps)}},
        "key_parameters": {
            "discount_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, r)},
            "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, g2)},
            "forward_return": {"unit": "RATIO", "values": roe},
            "steady_return": {"unit": "RATIO", "values": {tier: min(roe[tier], rs_tier[tier]) for tier in TIERS},
                              "reference_value": r_s},
            "option_discount_rate": r, "option_terminal_growth": inp["g_npo"],
            "option_forward_return": roe_book_h,
            "option_steady_return": min(roe_book_h, inp["ss_return_npo"]),
            "normal_margin": inp["nm_norm_main"],
        },
        "cash_bridge": {"per_share": cps, "parent_share": pr, "taxed_income": c_inc},
        "diagnostics": {"operating_eps": eop, "opening_operating_bps": bps,
                        "multiples": pe, "window": win, "flat": dict(zip(TIERS, flat)),
                        "decomposition": dec, "npo_revenue_path": npo_path(end=2032),
                        "npo_2028_income": npo_ni, "npo_2028_eps": eps_npo,
                        "npo_2028_value": v_opt_t,
                        "optical_narrow_revenue_usd": narrow,
                        "optical_attachment": {t: narrow[t] / (optical["oe"][t] * optical["oe_bom_usd"]) for t in TIERS},
                        "capex_share_middle": inp["rev_fy27_cons"] * 1e6 / inp["usdcny"] / inp["capex_m"],
                        "observed_retention": ret_obs,
                        "retention_after_required_growth": {t: ret_obs - (g1 if stage[t] else g2) / roe[t] for t in TIERS},
                        "band_edge_implied_growth": {t: {"low": implied_g(inp["pe_own_min"], roe[t], r),
                                                         "high": implied_g(inp["pe_own_max"], roe[t], r)} for t in TIERS}},
        "review_flags": review_flags, "sensitivity": sensitivity,
    }
