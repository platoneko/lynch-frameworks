"""AEHR historical migration draft. No financial data was refreshed here.

The historical source has one reported business, a conditional funding-use
stress, an independent candidate, and three non-additive option tiers. Shared
axis inputs must come from the injected actual axis versions, not a local copy.
"""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, g_cap, implied_g, perpetual_pe
from lib.inputs import ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.zones import cut_points
from lib.valuation_guards import require_axis_alignment, option_reconciliation_status

# Provisional interfaces: both machine axes must be supplied by the joint axis
# migration and reconciled with their actual sources before use.
DEPENDENCIES = {"libraries": ("gordon", "inputs", "zones", "valuation_guards", "partial_basis"),
                "axes": {"burn_in": "burn_in_test", "capex": "ai_capex"}}
MILLION = 1e6
NUM_YEAR = 2028
CAND_DISC_YEARS = 2
FLOOR_RATIO_MIN = 0.3
HAIRCUT_ROUNDING = 0.01
MIN_R_MINUS_G = 0.02
NARRATIVE_CAP = 0.30
TIERS = ("L", "M", "H")
BASKETS = {"r_perp": 4}
# Original 2026-11-04 research explicitly says the FY30 single-broker path
# was not refreshed and whether new consensus includes the extra customer and
# SiC revenue is unknown. Research must substantiate both before changing.
OPTION_OVERLAP_RESOLVED = False
FY30_PATH_REFRESHED = False
INPUTS = {
    # FY27 Q1 稀释加权股数；实际基准刷新，SBC 已扣，不另叠未来股本增长; source/as-of: 2026-09-25
    'shares': 33520000.0,
    # FY27 Q1 期末在外股数；只用于有形账面参照; source/as-of: 2026-09-25
    'shares_basic': 32663000.0,
    # FY27 Q1 股东权益 $M；经营权益 = 222.112 − 95.098 = 127.014; source/as-of: 2026-09-25
    'equity': 222.112,
    # FY27 Q1 现金及等价物 $M；不含受限现金 0.150; source/as-of: 2026-09-25
    'cash': 104.902,
    # 现金 104.902 − 经营租赁负债 0.653 − 9.151；零借款，按原结构单列; source/as-of: 2026-09-25
    'net_cash': 95.098,
    # Q1 利息 0.899 ÷ 平均现金 (112.308 + 104.902)/2 × 4；年化估算，非收益率指引; source/as-of: 2026-09-25
    'cash_yield': 0.0331108144,
    # 权益 222.112 − 商誉 10.719 − 无形资产 9.157；$M; source/as-of: 2026-09-25
    'tangible_book': 202.236,
    # 资产地板倍数（作用于**有形** BPS）；只披露不 max()；近 5 年 PB 低位锚（A10）; source/as-of: 对话锁定
    'pb_floor': 1.89,
    # yfinance FY27 normalized EPS 均值（5 家，0.90–1.23）；期末 2027-06-30，模型只滚未入账部分; source/as-of: 2026-11-04
    'eps_fy27_m': 0.998,
    # 近三年实付派息率（无股利，实付留存 100%）；只进 A18 的 B 桶披露行，**不进** BPS 推演（主尺按 \(b_1 = g_2/ROE\) 滚）; source/as-of: 2026-05-29
    'payout_3y': 0.0,
    # yfinance FY28 normalized EPS 下沿（4 家，endDate 2028-06-30）; source/as-of: 2026-11-04
    'eps_fy28_l': 1.44,
    # 同源四家均值；7 日前 1.375，本期 +22.36%; source/as-of: 2026-11-04
    'eps_fy28_m': 1.6825,
    # 同源四家上沿; source/as-of: 2026-11-04
    'eps_fy28_h': 2.08,
    # 历史 GAAP 共识，仅与 haircut_ref_eps / haircut_ref_shares 配对验证旧折扣；不是新版 FY28 GAAP 预测; source/as-of: 2026-09-14
    'eps_fy28_gaap_m': 1.115,
    # yfinance FY28 四家收入下沿 $M; source/as-of: 2026-11-04
    'rev_fy28_l': 200.0,
    # 同源收入均值 $M; source/as-of: 2026-11-04
    'rev_fy28_m': 229.8965,
    # 同源收入上沿 $M; source/as-of: 2026-11-04
    'rev_fy28_h': 280.246,
    # FY30 收入 $M——**Freedom Broker 单家**（2026-07-16 上调评级时公布，Investing.com 转述；无 EPS / 利润率）；**进候选带（A19）与期权 H 档的量（卖方最高路径终点，A14），不进底牌**; source/as-of: 2026-07-16
    'rev_fy30_fb': 355.8,
    # Oppenheimer 2026-09-10历史单家FY28收入，仅保留历史参照，已被新四家区间取代、不作当前上沿校验; source/as-of: 2026-09-10
    'rev_fy28_opp': 218.0,
    # FY2026 SBC $M（现金流量表）；推导出的 FY28 SBC 须 ≥ 此值（A9 下界参照）; source/as-of: 2026-05-29
    'sbc_fy26': 6.761,
    # 收购无形资产摊销 $M（FY2026）；GAAP–normalized 差里先剔掉它，本框架不扣摊销（A9）; source/as-of: 2026-05-29
    'amort_fy26': 1.23,
    # 法定联邦税率；SBC 税后、利息税后与期权单位税后用; source/as-of: FY2026 10-K
    'tax': 0.21,
    # 保留已讨论的经济成本假设；由历史同日 normalized/GAAP 对推，不把新 normalized 与旧 GAAP 混算；新 GAAP 共识待更新（A9）; source/as-of: 2026-09-14
    'sbc_haircut': 0.18,
    # 永续折现率 = 篮 4 常规经营 10%：设备商，盈利随客户 capex 项目周期、不是商品价函数；小盘与客户集中不抬 r（A17）；备选篮 7 15% 只披露（A12）；`check_r`; source/as-of: 2026-09-30
    'r_perp': 0.1,
    # **护栏下沿**：自身 5 年日频当期财年前瞻 PE 带最低点（2022-07-01，收 6.94 ÷ FY23 共识 0.69）；与带同基的口径 = 锚点 ÷ `eps_fy27_m`（A8）; source/as-of: 2026-09-14
    'pe_own_min': 10.06,
    # 同带 p5；证据坐标，不入公式（A8）; source/as-of: 2026-09-14
    'pe_own_p5': 13.1,
    # 同带中位；证据坐标——H 档与带同基口径 32.7× 略低于此值；M 档在合法 g 内不可达（带边 g 6.9% 越 cap，A8）; source/as-of: 2026-09-14
    'pe_own_p50': 35.1,
    # FY2024 实测收入 $M（客户 D 单客户填充峰值年）；与 `sic_share_fy24` 合出 SiC 峰值收入（A14）；也是历史利润率下界的分母——**只披露，不作单位经济**; source/as-of: 2024-05-31
    'unit_rev': 66.218,
    # FY2024 实测毛利 $M（49.1%）；只进历史利润率下界披露（A14）; source/as-of: 2024-05-31
    'unit_gp': 32.543,
    # FY2024 实测 opex $M（含 SBC 2.5M）；只进历史利润率下界披露（A14）; source/as-of: 2024-05-31
    'unit_opex': 22.465,
    # FY2024 EV / 功率半导体占收入比（10-K 终端结构）；× `unit_rev` = SiC 峰值收入 60.92M（A14）; source/as-of: 2024-05-31
    'sic_share_fy24': 0.92,
    # FY2026 收入 $M（10-K）；与 `sic_share_fy26` 合出共识视同已含的 SiC 水平（A14）; source/as-of: 2026-05-29
    'rev_fy26': 50.0,
    # FY2026 EV / 功率半导体占收入比（10-K）；FY26 SiC 收入 8.5M 视同已在 FY28 共识内（共识真实所含 SiC 份额 `待补`；只扣这一层 → SiC 份数偏上限，A14）; source/as-of: 2026-05-29
    'sic_share_fy26': 0.17,
    # L 档份数（M / H 档亦含）：第二家 AI 处理器客户按 1 份领先 WLBI AI 处理器客户近 12 个月已签订单 $14M（2026-02-26）+ $22M（2026-08-12），各约 6 个月交付 ≈ 一年出货；无卖方的量 → 快照（A14）; source/as-of: 2026-08-12
    'opt_rev_ai': 36.0,
    # 期权兑现年 = H 档卖方最高路径终点年（Freedom Broker FY30）；L / M 无公司具名年，同年计；按篮子 r 折回 FY28 两年（A14）; source/as-of: 2026-10-05
    't_opt': 2030.0,
    # **理论产能读数，只披露、不作 H 的量**（轻资产，A14）：Fremont 一班可做约 20 台 / 月晶圆级 FOX 系统（CEO：「20 FOX-XPs here a month」，Sonoma 改由东南亚代工直发后 Fremont 可全做晶圆级；Q4 FY26 电话会）（A14）; source/as-of: 2026-07-14
    'fox_units_m': 20.0,
    # 晶圆级 FOX 系统单价 $M（含 WaferPak；CEO：「ASP closer with the WaferPaks of $5 million … $100 million a month」，另说「upwards of six」）；只进理论产能读数（A14）; source/as-of: 2026-07-14
    'fox_asp': 5.0,
    # **理论产能读数，只披露**：东南亚代工约 20 台 / 月 Sonoma（Q3 FY26 起量；10-K 称其「significantly increases the total manufacturing capacity」）（A14）; source/as-of: 2026-07-14
    'sonoma_units_m': 20.0,
    # Sonoma Ultra 单价 $M（CEO：「$20 million a month of Sonomas」；标准机 $0.6–0.7M）；只进理论产能读数；eval 校验 H 世界收入 ≤ 理论产能（A14）; source/as-of: 2026-07-14
    'sonoma_asp': 1.0,
    # FY2026 GAAP 营业利润 $M；加回 SBC / 收购摊销 / 重组得 non-GAAP 经营利润 −6.10M，作 H 档利润率两期推断的第一期（A14）; source/as-of: 2026-05-29
    'op_gaap_fy26': -14.1,
    # FY2026 重组费用 $M（加回项）（A14）; source/as-of: 2026-05-29
    'restr_fy26': 0.006,
    # 已承诺未投的扩产资本 $M：无具名扩产预算（FY26 资本开支 2.1M、「capital-light」）→ 0；期权只扣份数所需的新增经营资本（κ × 份数，主要是存货与应收；A14）; source/as-of: 2026-07-14
    'capex_committed': 0.0,
    # 2026-09-25 资产负债表日至 FY28 年初 2027-06-25，273/365；A21; source/as-of: 2026-09-25
    'tau': 0.7479452055,
    # 2026-09-14 normalized EPS 历史参照；仅复核 18% 折扣原推导; source/as-of: 2026-09-14
    'haircut_ref_eps': 1.3833,
    # 与两条历史 EPS 同期的股数，防跨期混算; source/as-of: 2026-09-14
    'haircut_ref_shares': 33170000.0,
    # FY27 Q1 non-GAAP 净利 $M；财报 EX-99.1; source/as-of: 2026-09-25
    'q1_non_gaap_ni': 9.357,
    # FY27 Q1 SBC $M；已报季度扣实际，不扣估算百分比; source/as-of: 2026-09-25
    'q1_sbc': 1.88,
    # FY27 Q1 净利息收入 $M；按 tax 同口径剔除; source/as-of: 2026-09-25
    'q1_interest': 0.899,
    # 条件压力：额外营运资本占用预算的条件压力；以三倍(Q1净CF流出3.054+capex0.049)参照量级，非净CF预测、非已承诺投入; source/as-of: 2026-09-25
    'cash_need_stress': 9.309,
}

def _lin(cal: int, y1: int, y2: int, a: float, b: float) -> float:
    """a through Y1, linear to b at Y2, b after (valuation-rules ② 稳态回报三段)."""
    if cal <= y1:
        return a
    if cal >= y2:
        return b
    return a + (b - a) * (cal - y1) / (y2 - y1)


def path_value(t0: int, y1: int, y2: int, r_s: float, g: float, roe: float, r: float) -> float:
    """Gordon multiple on next-period earnings with the three-segment RONIC path; t = 1 <->
    fiscal year t0; RONIC = forward through Y1, linear to min(forward, r_s) at Y2, tail after."""
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    rs = min(roe, r_s)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        pay = min(1.0, 1.0 - g / _lin(cal, y1, y2, roe, rs))
        if cal > y1 and cal >= y2:
            return pv + e * pay / ((r - g) * (1 + r) ** (t - 1))
        pv += e * pay / (1 + r) ** t
        e *= 1 + g
        t += 1

def derived_haircut(inp: dict[str, float]) -> tuple[float, float]:
    """A9: SBC share of FY28 normalized NI, from the GAAP-vs-normalized consensus gap.

    The gap is after tax and also carries acquisition amortisation, which the
    framework does not deduct, so that piece comes out first.  Returns
    (haircut, implied pre-tax FY28 SBC in $M) — the latter is printed against
    FY26 actual SBC as a plausibility read.
    """
    # Keep both reference EPS lines and their share count at the same vintage.
    # The refreshed normalized forecast cannot be paired with stale GAAP EPS.
    ni_norm = inp["haircut_ref_eps"] * inp["haircut_ref_shares"] / MILLION
    gap = (inp["haircut_ref_eps"] - inp["eps_fy28_gaap_m"]) * inp["haircut_ref_shares"] / MILLION
    sbc_after_tax = gap - inp["amort_fy26"] * (1.0 - inp["tax"])
    return sbc_after_tax / ni_norm, sbc_after_tax / (1.0 - inp["tax"])


def _local_basis_snapshot(axes):
    return {
        'inputs': INPUTS,
        'constants': {'million': MILLION, 'numerator_year': NUM_YEAR, 'candidate_years': CAND_DISC_YEARS,
                      'floor_ratio_min': FLOOR_RATIO_MIN, 'haircut_rounding': HAIRCUT_ROUNDING,
                      'min_r_minus_g': MIN_R_MINUS_G, 'narrative_cap': NARRATIVE_CAP,
                      'tiers': TIERS, 'baskets': BASKETS, 'option_overlap_resolved': OPTION_OVERLAP_RESOLVED,
                      'fy30_path_refreshed': FY30_PATH_REFRESHED},
        'shared': {
            'burn_in': {'growth_reference': axes['burn_in']['g2_bit_src'],
                        'weak_margin': axes['burn_in']['bit_opm_weak'],
                        'strong_margin': axes['burn_in']['bit_opm_strong'],
                        'alignment': axes['burn_in']['t_align'],
                        'return_cap': axes['burn_in']['ss_return_cap_bit'],
                        'return_reference': axes['burn_in']['ss_return_bit_ref'],
                        'start': axes['burn_in']['y1_bit'], 'end': axes['burn_in']['y2_bit']},
            'capex': {'role': axes['capex']['role'], 'rungs': axes['capex']['rungs'],
                      'return_reference': axes['capex']['ss_floor_ai_capex_package']},
        },
    }


# A local snapshot does not attest the formulas, sources or user approval.
LOCAL_BASIS_BASELINE = '1a846297ad0d2d292d71a39fc13a38f97b1fbe9ac8cb57f3f8303515f0713ff7'


def calculate(context):
    inp = dict(INPUTS)
    burn, capex = context["axes"]["burn_in"], context["axes"]["capex"]
    # The shared aligned year is FY28, the actual numerator in this model.
    # A different year means the forecasts and path need rebuilding.
    require_axis_alignment(burn, NUM_YEAR)
    inp.update({"g2_bit_src": burn["g2_bit_src"], "bit_opm_weak": burn["bit_opm_weak"],
                "bit_opm_strong": burn["bit_opm_strong"], "ss_return": burn["ss_return_cap_bit"],
                "y1": burn["y1_bit"], "y2": burn["y2_bit"],
                **{f"capex_{tier.lower()}": capex["rungs"][tier] for tier in TIERS}})
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("inputs must be finite numbers")
    inp["g2"] = min(inp["g2_bit_src"], g_cap(inp["r_perp"]))
    require_whole_years(inp, ("y1", "y2", "t_opt"))
    if inp["r_perp"] <= inp["g2"] or inp["r_perp"] <= -1:
        raise ValueError("perpetuity or discount factor is mathematically invalid")
    if inp["t_opt"] != NUM_YEAR + CAND_DISC_YEARS:
        raise ValueError("historical option and candidate observations require a rebuilt dated path")
    review_flags = ["cash_use_stress_is_not_a_verified_bound",
                    "gaap_consensus_refresh_missing"]
    if not FY30_PATH_REFRESHED:
        review_flags.append("fy30_broker_candidate_not_refreshed")
    if not OPTION_OVERLAP_RESOLVED:
        review_flags.append("option_customer_and_sic_may_overlap_consensus")
    if check_r(inp["r_perp"], "r_perp", 4):
        review_flags.append("discount_rate_basket_mismatch")
    if check_g_cap(inp["g2"], inp["r_perp"], "g2"):
        review_flags.append("terminal_growth_above_cap")
    if inp["ss_return"] > NARRATIVE_CAP + 1e-9:
        review_flags.append("steady_return_above_narrative_cap")
    if not NUM_YEAR <= inp["y1"] < inp["y2"]:
        review_flags.append("return_fade_years_invalid")
    if not 0 <= inp["tau"] < 3:
        review_flags.append("fractional_discount_period_outside_range")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        review_flags.append("terminal_growth_close_to_discount_rate")
    if not inp["eps_fy27_m"] < inp["eps_fy28_l"] or inp["g2"] < 0:
        review_flags.append("growth_incompatible_with_forecast_direction")
    if ladder("numerator", inp["eps_fy28_l"], inp["eps_fy28_m"], inp["eps_fy28_h"]):
        review_flags.append("forecast_eps_not_increasing")
    derived, implied_sbc = derived_haircut(inp)
    if not derived - 1e-9 <= inp["sbc_haircut"] <= derived + HAIRCUT_ROUNDING + 1e-9:
        review_flags.append("sbc_haircut_outside_historical_reference_range")
    if implied_sbc < inp["sbc_fy26"]:
        review_flags.append("implied_sbc_below_historical_actual")
    if not 0 < inp["net_cash"] <= inp["cash"]:
        review_flags.append("net_cash_outside_cash_balance")
    if inp["equity"] - inp["net_cash"] <= 0:
        review_flags.append("operating_equity_nonpositive")
    if inp["t_opt"] <= NUM_YEAR:
        review_flags.append("option_realization_not_after_numerator_year")
    if inp["unit_rev"] * inp["sic_share_fy24"] <= inp["rev_fy26"] * inp["sic_share_fy26"]:
        review_flags.append("sic_peak_not_above_consensus_baseline")
    if any(key.startswith("p_") for key in inp):
        review_flags.append("option_probability_inside_base_inputs")
    r, g2 = inp["r_perp"], inp["g2"]
    cap = g_cap(r)
    y1, y2, rs, tau = int(inp["y1"]), int(inp["y2"]), inp["ss_return"], inp["tau"]

    def pp(g: float, roe_: float, rr: float, t0: int = NUM_YEAR, rs_: float | None = None) -> float:  # A20 path multiple
        return path_value(t0, y1, y2, rs if rs_ is None else rs_, g, roe_, rr)
    street = {"L": inp["eps_fy28_l"], "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}

    # ---- Step 1-2: economic EPS, then core EPS with the cash interest stripped (A9, A15) ----
    eps = {t: street[t] * (1.0 - inp["sbc_haircut"]) for t in TIERS}
    int_ps = inp["cash"] * inp["cash_yield"] * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    core = {t: eps[t] - int_ps for t in TIERS}

    # ---- Step 3-4: tier ROE = E_FY28 / opening-FY28 operating book, Gordon multiple, cash added back ----
    # The latest-quarter operating book is rolled over remaining FY27
    # consensus on the same core basis
    # (haircut, interest stripped) — at the growth-required retention b1 =
    # g2/ROE (no g1 window, A18).  ROE and BPS depend on each other; closed form
    # BPS = BPS0 / (1 - g2·N/core).  A diverging roll (g2·N/core >= 1) stops.
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] * MILLION / inp["shares"]
    bps_op_fy26 = equity_op * MILLION / inp["shares"]
    # Q1 is already in September equity/cash; only the remaining fiscal-year
    # profit rolls into opening FY28 capital and the distributable-profit window.
    booked_core = (inp["q1_non_gaap_ni"] - inp["q1_sbc"] - inp["q1_interest"] * (1 - inp["tax"])) * MILLION / inp["shares"]
    unbooked = inp["eps_fy27_m"] * (1.0 - inp["sbc_haircut"]) - int_ps - booked_core

    def opening_bps(core_x: float, g: float) -> float:
        share = g * unbooked / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps_op_fy26 / (1.0 - share)

    def rolled_roe(g: float) -> dict[str, float]:
        return {t: core[t] / opening_bps(core[t], g) for t in TIERS}

    roe = rolled_roe(g2)
    b1 = {t: g2 / roe[t] for t in TIERS}
    roe_fy26 = {t: core[t] * inp["shares"] / (equity_op * MILLION) for t in TIERS}  # old basis, printed only
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in TIERS}  # disclosure only
    pes = {t: pp(g2, roe[t], r) for t in TIERS}
    ex_cash = {t: core[t] * pes[t] for t in TIERS}  # at the FY28 opening

    # Timing alignment (A21): FY28-opening value / (1+r)^tau + window profit; cash not discounted.
    def window(roe_: float, g: float, rr: float) -> float:
        return unbooked * max(0.0, 1.0 - g / roe_) * (1.0 + rr) ** (-tau / 2)

    df = (1.0 + r) ** (-tau)
    win = {t: window(roe[t], g2, r) for t in TIERS}
    scen = {t: ex_cash[t] * df + win[t] + cash_ps for t in TIERS}

    # ---- Step 5: anchors, cut points; the floor is disclosed only (A10) ----
    tbvps = inp["tangible_book"] * MILLION / inp["shares_basic"]
    floor = inp["pb_floor"] * tbvps
    below_floor = scen["L"] < floor
    L, M, H = scen["L"], scen["M"], scen["H"]
    if not (L < M < H):
        review_flags.append('base_anchors_not_increasing')
    floor_ratio = scen["L"] / M
    if below_floor and floor_ratio < FLOOR_RATIO_MIN:
        review_flags.append('low_anchor_below_floor_and_ratio_threshold')

    # ---- Guardrail (裁决顺序 ③), on the band's own basis ----
    # The band is close / current-FY (FY27) consensus, so the anchor is divided by
    # the same denominator; the FY28-numerator Gordon multiples are a different
    # basis and are only printed.  Only the lower edge binds (A8).
    band_basis = {t: scen[t] / inp["eps_fy27_m"] for t in TIERS}
    for t in TIERS:
        if band_basis[t] < inp["pe_own_min"]:
            review_flags.append('anchor_below_historical_multiple_floor' + "_" + t.lower())

    def band_edge_g(target_pe: float) -> tuple[float, bool]:
        """g at M-tier ROE that puts M / FY27 consensus on `target_pe` (evidence, never an input)."""
        pe_needed = (target_pe * inp["eps_fy27_m"] - cash_ps - win["M"]) / df / core["M"]
        return implied_g(pe_needed, roe["M"], r)

    edges = {k: band_edge_g(inp[f"pe_own_{k}"]) for k in ("min", "p5", "p50")}
    pe_m_cap = perpetual_pe(cap, roe["M"], r)

    # ---- A2e-2c flat ladder + A2e-5 decomposition (both on the ex-cash earnings term) ----
    if not (core["L"] < core["M"] < core["H"]):
        review_flags.append('core_earnings_not_increasing')
    flat = [core[t] * pes["M"] * df + win["M"] + cash_ps for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        review_flags.append('flat_ladder_not_increasing')
    num_lm, num_hm = core["L"] / core["M"], core["H"] / core["M"]
    pe_lm, pe_hm = pes["L"] / pes["M"], pes["H"] / pes["M"]

    # ---- g2 leverage (valuation-rules「g₂ 的杠杆 MUST 显式」): -1pp disclosed (L/M/H only); +1pp breaks ① ----
    def deck_at(g: float) -> tuple[float, float, float, bool]:
        roe_g = rolled_roe(g)  # the book rolls at the g being tested
        s = {t: core[t] * pp(g, roe_g[t], r) * df + window(roe_g[t], g, r) + cash_ps for t in TIERS}
        return s["L"], s["M"], s["H"], s["L"] < s["M"] < s["H"]

    lo_l, lo_m, lo_h, lo_ok = deck_at(g2 - 0.01)

    # ---- Option tiers and zone+V (probabilities only here; A14, _AXIS.burn-in-test) ----
    rev28 = {"L": inp["rev_fy28_l"], "M": inp["rev_fy28_m"], "H": inp["rev_fy28_h"]}
    margin = {t: core[t] * inp["shares"] / MILLION / rev28[t] for t in TIERS}
    sic_peak = inp["unit_rev"] * inp["sic_share_fy24"]
    sic_in = inp["rev_fy26"] * inp["sic_share_fy26"]
    sic_item = sic_peak - sic_in
    cap_rev = 12.0 * (inp["fox_units_m"] * inp["fox_asp"] + inp["sonoma_units_m"] * inp["sonoma_asp"])  # reading only
    disc_n = int(inp["t_opt"]) - NUM_YEAR
    grow = (1.0 + g2) ** disc_n  # the deck's H tier already carries FY28 x (1+g2)^n by the option year
    base_rev = rev28["H"] * grow
    if inp["rev_fy30_fb"] <= base_rev:
        review_flags.append('single_broker_path_not_above_high_consensus')
    path_xs = inp["rev_fy30_fb"] - base_rev
    path_fy29 = (rev28["H"] * inp["rev_fy30_fb"]) ** 0.5  # interpolated, disclosure only
    qty = {"L": inp["opt_rev_ai"], "M": inp["opt_rev_ai"] + sic_item, "H": path_xs + inp["opt_rev_ai"] + sic_item}
    scale = base_rev + qty["H"]
    if scale > cap_rev:
        review_flags.append('option_revenue_above_named_capacity')
    # Margin at the H-world scale: two-period fixed / variable split of non-GAAP
    # operating profit (ex SBC, amortisation, restructuring; ex cash interest),
    # FY26 actual vs FY28 M consensus; must sit inside the axis peer range.
    op26 = inp["op_gaap_fy26"] + inp["sbc_fy26"] + inp["amort_fy26"] + inp["restr_fy26"]
    op28 = inp["eps_fy28_m"] * inp["shares"] / MILLION / (1.0 - inp["tax"]) - inp["cash"] * inp["cash_yield"]
    var_m = (op28 - op26) / (inp["rev_fy28_m"] - inp["rev_fy26"])
    fixed = op26 - var_m * inp["rev_fy26"]
    opm_at = lambda rev: (var_m * rev + fixed) / rev  # noqa: E731
    opm_h = opm_at(scale)
    if not inp["bit_opm_weak"] <= opm_h <= inp["bit_opm_strong"]:
        review_flags.append('option_operating_margin_outside_peer_range')
    inc_core = var_m * (1.0 - inp["tax"]) * (1.0 - inp["sbc_haircut"])  # incremental core margin
    guide27 = (var_m * 150.0 + fixed + inp["cash"] * inp["cash_yield"]) * (1 - inp["tax"]) / 150.0  # non-GAAP net margin, disclosure only
    k_h = opening_bps(core["H"], g2) * inp["shares"] / MILLION  # FY28 opening operating capital, H
    kappa = k_h / rev28["H"]
    ni_h = core["H"] * inp["shares"] / MILLION
    unit = {"L": margin["M"], "M": margin["M"], "H": inc_core}
    if not (0 < qty["L"] < qty["M"] < qty["H"]):
        review_flags.append('option_quantity_not_increasing')

    def v_tier(dr: float, m: float, rr: float = r, kap: float = kappa, rs_: float | None = None) -> dict[str, float]:
        d_ni = dr * m
        k_s = k_h * grow + kap * dr
        roe_s = (ni_h * grow + d_ni) / k_s
        pe_s = pp(g2, roe_s, rr, int(inp["t_opt"]), rs_)  # success world rides the same path from FY30 (A14)
        gross = d_ni * pe_s / (1.0 + rr) ** disc_n
        capital = (kap * dr + inp["capex_committed"]) / (1.0 + rr) ** disc_n
        to_ps = MILLION / inp["shares"]
        # gross / capital are at FY28 (the deck's numerator year); v is today (tau, A21).
        return dict(d_ni=d_ni, roe=roe_s, pe=pe_s, gross=gross * to_ps, capital=capital * to_ps,
                    v=max(0.0, (gross - capital) * to_ps) * (1.0 + rr) ** (-tau))

    vt = {t: v_tier(qty[t], unit[t]) for t in TIERS}
    v_opt = vt["H"]["v"]
    if v_opt <= 0:
        raise ValueError("option weights are undefined for nonpositive option value")
    p_calc = tuple(vt[t]["v"] / v_opt for t in TIERS)
    hist_margin = (inp["unit_gp"] - inp["unit_opex"]) * (1.0 - inp["tax"]) / inp["unit_rev"]  # FY24 realised, floor only
    # ---- Candidate band (A19; AGENTS.md「共识升级候选带」): never a zone input ----
    # One house (Freedom Broker) prints FY30 revenue and nothing else, so each
    # tier's FY28 consensus net margin carries it to FY30: FY30 street EPS =
    # FY28 street EPS x FY30 revenue / that tier's FY28 revenue.  Same haircut,
    # interest strip, closing cash and g2 as the deck; the book rolls over
    # FY27-FY29 at b1 = g2/ROE (FY29 core is the geometric midpoint — the path
    # only moves the book), and FY30 is discounted two years.  The L world has
    # no second leg of growth, so L′ = L.
    if ladder("FY28 revenue", rev28["L"], rev28["M"], rev28["H"]):
        review_flags.append("forecast_revenue_not_increasing")

    # Freedom Broker's FY30 is an ordinary base forecast = growth type (construction §7h): its
    # FY28-mean -> FY30 growth is shared by M and H (each tier keeps its own FY28 margin).
    grow30 = inp["rev_fy30_fb"] / rev28["M"]

    def fy30_tier(t: str) -> tuple[float, float, float]:
        c30 = street[t] * grow30 * (1.0 - inp["sbc_haircut"]) - int_ps
        rolled = unbooked + core[t] + (core[t] * c30) ** 0.5
        share = g2 * rolled / c30
        if share >= 1.0:
            raise ValueError(f"candidate book roll diverges at {t}: g·ΣN/c = {share:.2f}")
        roe30 = c30 * (1.0 - share) / bps_op_fy26
        val28 = c30 * pp(g2, roe30, r, NUM_YEAR + CAND_DISC_YEARS) / (1.0 + r) ** CAND_DISC_YEARS
        return c30, roe30, val28 * df + win[t] + cash_ps

    cand_m, cand_h = fy30_tier("M"), fy30_tier("H")
    cand = (L, cand_m[2], cand_h[2])

    option = tuple(scen[t] + vt[t]["v"] for t in TIERS)
    # Historical comparisons isolate one changed assumption at a time and are
    # not independently adopted valuation bands. The peer midpoint was
    # excluded by the documented 2026-10-19 decision and remains a comparison.
    option_sensitivities = {
        "single_broker_path_only": v_tier(path_xs, inc_core)["v"],
        "weak_peer_margin": v_tier(qty["H"], inp["bit_opm_weak"] * (1 - inp["tax"]) * (1 - inp["sbc_haircut"]))["v"],
        "strong_peer_margin": v_tier(qty["H"], inp["bit_opm_strong"] * (1 - inp["tax"]) * (1 - inp["sbc_haircut"]))["v"],
        "half_incremental_capital": v_tier(qty["H"], inc_core, kap=kappa * 0.5)["v"],
        "middle_consensus_margin": v_tier(qty["H"], margin["M"])["v"],
        "discount_rate_13pct": v_tier(qty["H"], inc_core, rr=0.13)["v"],
        "discount_rate_15pct": v_tier(qty["H"], inc_core, rr=0.15)["v"],
    }
    steady_comparisons = {}
    for name, reference in (("excluded_peer_median", burn["ss_return_bit_ref"]),
                            ("packaging_fallback", capex["ss_floor_ai_capex_package"]),
                            ("equipment_fallback", 0.15)):
        steady_comparisons[name] = {
            "return_reference": reference, "return_unit": "RATIO", "price_unit": "USD_PER_SHARE",
            "anchors": {t: core[t] * pp(g2, roe[t], r, rs_=reference) * df + win[t] + cash_ps for t in TIERS},
            "option_value": v_tier(qty["H"], inc_core, rs_=reference)["v"],
        }
    cap_qty = cap_rev - base_rev
    theoretical_capacity = {"capacity_revenue": cap_rev, "incremental_revenue": cap_qty,
                            "revenue_unit": "USD_MILLION", "operating_margin": opm_at(cap_rev),
                            "operating_margin_unit": "RATIO", "option_value_unit": "USD_PER_SHARE",
                            "option_value": v_tier(cap_qty, inc_core)["v"]}
    discount_comparisons = {}
    for rr, label in ((0.13, "rate_13pct"), (0.15, "rate_15pct")):
        discount_comparisons[label] = {
            "discount_rate": rr, "discount_rate_unit": "RATIO", "price_unit": "USD_PER_SHARE",
            "anchors": {t: core[t] * pp(g2, roe[t], rr) * (1 + rr) ** (-tau)
                        + window(roe[t], g2, rr) + cash_ps for t in TIERS},
            "option_value": v_tier(qty["H"], inc_core, rr=rr)["v"],
        }
    # Stress varies cash used for additional operating capital; its historic
    # amount comes from the Q1 outflow proxy, not a new cash-flow forecast.
    funding = {}
    for fraction, label in ((0.0, "none"), (0.5, "half"), (1.0, "full")):
        need = fraction * inp["cash_need_stress"]
        cash_used_ps = need * MILLION / inp["shares"]
        interest_saved = cash_used_ps * inp["cash_yield"] * (1 - inp["tax"])
        remaining = unbooked + interest_saved * tau
        starting_bps = bps_op_fy26 + cash_used_ps
        vals = {}
        for t in TIERS:
            c = core[t] + interest_saved
            op_bps = starting_bps / (1 - g2 * remaining / c)
            ro = c / op_bps
            w = remaining * (1 - g2 / ro) * (1 + r) ** (-tau / 2)
            vals[t] = c * pp(g2, ro, r) * df + w + cash_ps - cash_used_ps
        funding[label] = vals
    return {
        "ticker": "AEHR.US", "currency": "USD", "valuation_as_of": None,
        "framework_as_of": None, "historical_valuation_as_of": "2026-09-25",
        "historical_framework_as_of": "2026-11-04", "basis_changed": None,
        "partial_basis_changed": local_basis_changed(_local_basis_snapshot(context['axes']), LOCAL_BASIS_BASELINE), "units": {"price": "USD_PER_SHARE"},
        "anchors": scen,
        "candidate": {"label": "FY30·Freedom Broker 单家", "anchors": dict(zip(TIERS, cand))},
        "option": {"value": v_opt, "value_unit": "USD_PER_SHARE", "weights": dict(zip(TIERS, p_calc)),
                   "status": option_reconciliation_status(path_xs, OPTION_OVERLAP_RESOLVED, FY30_PATH_REFRESHED),
                   "anchors": dict(zip(TIERS, option))},
        "segments": {"operating_and_window": {"unit": "USD_PER_SHARE",
                     "values": {t: ex_cash[t] * df + win[t] for t in TIERS}},
                     "net_cash": {"unit": "USD_PER_SHARE", "values": dict.fromkeys(TIERS, cash_ps)}},
        "key_parameters": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, r)},
                           "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, g2),
                                           "reference_value": inp["g2_bit_src"]},
                           "forward_return": {"unit": "RATIO", "values": roe},
                           "steady_return": {"unit": "RATIO",
                               "values": {t: min(roe[t], rs) for t in TIERS}, "reference_value": rs}},
        "diagnostics": {
            "forecast_eps": street, "earnings_after_sbc": eps, "operating_eps": core,
            "operating_bps": bps_op_fy26, "opening_operating_bps": {t: opening_bps(core[t], g2) for t in TIERS},
            "unrolled_return": roe_fy26, "required_retention": b1, "actual_retention": ret_actual,
            "cash_retained_not_added_again": excess_cash, "cash_per_share": cash_ps,
            "booked_q1_core_eps": booked_core, "unbooked_core_eps": unbooked,
            "window": win, "multiples": pes, "flat_ladder": dict(zip(TIERS, flat)),
            "tangible_book_floor": floor, "below_tangible_book_floor": below_floor,
            "low_to_middle": L / M, "high_to_middle": H / M,
            "earnings_ratio_low_middle": num_lm, "earnings_ratio_high_middle": num_hm,
            "multiple_ratio_low_middle": pe_lm, "multiple_ratio_high_middle": pe_hm,
            "band_multiples_on_fy27_basis": band_basis, "max_middle_multiple_at_growth_cap": pe_m_cap,
            "historical_band_edge_growth": edges, "option_tiers": vt,
            "option_revenue": qty, "option_broker_path_increment": path_xs,
            "option_fy29_interpolated_revenue": path_fy29, "option_h_world_revenue": scale,
            "option_h_margin": opm_h, "option_incremental_core_margin": inc_core,
            "option_capital_to_revenue": kappa, "option_h_opening_capital": k_h,
            "option_guide_check_margin": guide27, "option_sic_increment": sic_item,
            "historical_sbc_implied": implied_sbc, "historical_sbc_derived_haircut": derived,
            "capex_middle_share": inp["rev_fy28_m"] * MILLION / inp["capex_m"],
        },
        "sensitivity": {"growth_minus_1pp": dict(zip(TIERS, (lo_l, lo_m, lo_h))),
                        "funding_use": funding, "option_value": option_sensitivities,
                        "option_value_unit": "USD_PER_SHARE",
                        "steady_return": steady_comparisons, "discount_rate": discount_comparisons,
                        "theoretical_capacity": theoretical_capacity},
        "review_flags": review_flags,
    }
