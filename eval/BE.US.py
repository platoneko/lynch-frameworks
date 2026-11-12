"""BE historical valuation migration draft; financial issues remain disclosed.

Inputs and historical decisions are preserved from the 2026-10-23 research;
this draft has not been numerically reconciled or confirmed. FY2025 leverage
rules were triggered and required follow-ups remained incomplete; see flags.
"""
from __future__ import annotations
import math
from lib.gordon import check_basket_pair, check_g_cap, check_k_declared, check_transition_years
from lib.inputs import ladder
from lib.partial_basis import local_basis_changed
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points

DEPENDENCIES = {"libraries": ("gordon", "inputs", "tiers", "zones", "partial_basis"), "axes": {}}
NUM_YEAR = 2027
DERIVED_TOL = 5e-4
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")
# A16: optional business value weights are scenario settings, not frequencies.
P_TIERS = (0.0, 0.25, 1.0)
INPUTS = {
    # 加权摊薄股本（if-converted，已含价内转债 + SBC）= 10-Q Q3'26 三个月稀释加权 324,289K（基本 294,757K + 转债 13,922K + 期权与奖励 15,610K）；ROE 分子口径与 G7 基线（Q2'26 323.3M → +0.3%）；A9; source/as-of: 2026-09-30
    'shares': 324289000.0,
    # if-converted 股东权益 USD = 归属普通股权益 1,932,877K + 可转债账面 2,473,499K（0% 2030 2,450,891 / 3% Green 2029 22,608；3% 2028 已清）；10-Q Q3'26；A9。三档 ROE 的**起点**——按 \(b_1 = g_1/ROE\) 滚过 4Q26 到 FY27 年初再作分母（A19），不直接作分母; source/as-of: 2026-09-30
    'equity': 4406376000.0,
    # FY2026 Non-GAAP EPS = 公司指引 \$3.10–3.40 中值（2026-10-22 第三次上调）；与 4Q26 共识 1.093（yfinance 6 家）+ 前三季实测 2.16 = 3.25 一致；yfinance FY26 共识 3.144 只有 8 家更新，未取（取 3.144 → 47.41 / 102.28 / 156.29，较严的读法是 3.25）；消化年坐标（FY27 = FY26），不入锚点；A14。也是 A19 账面滚动的 4Q26 未入账利润的来源（扣 `eps_ytd26_a`）; source/as-of: 2026-10-22
    'eps_fy26_m': 3.25,
    # 前三季实测 Non-GAAP 摊薄 EPS = 1Q26 0.44 + 2Q26 0.78 + 3Q26 0.94（8-K 2026-10-22 新闻稿 / yfinance `earnings_history`）；已入 3Q26 账面，从 FY26 里扣掉；A19; source/as-of: 2026-09-30
    'eps_ytd26_a': 2.16,
    # 近三年实付派息率（无股利，实付留存 100%）；只进 A19 的 B 桶披露行，**不进** BPS 推演（主尺按 \(b_1 = g_1/ROE\) 滚）; source/as-of: 2026-06-30
    'payout_3y': 0.0,
    # FY2027 Non-GAAP EPS 共识低端（yfinance 25 家，原始值 2.95482；Q3 财报后这一家未更新，已低于 FY26 指引中值 3.25）= L 分子；A7 / A14; source/as-of: 2026-10-23
    'eps_fy27_l': 2.955,
    # FY2027 共识均值（yfinance 25 家 5.06279；FactSet 聚合同为 5.06）= M 分子；A7; source/as-of: 2026-10-23
    'eps_fy27_m': 5.063,
    # FY2027 共识高端（yfinance 25 家）= H 分子；A7; source/as-of: 2026-10-23
    'eps_fy27_h': 7.49,
    # FY2028 Non-GAAP EPS FactSet 聚合均值（Markets Insider；家数未披露、无区间；该表 FY26 仍为 2.75、未吸收 Q3 财报）→ 只作 g1 的锚，不作分子；A7 / A15; source/as-of: 2026-10-23
    'eps_fy28_cons': 8.3,
    # 过渡年增速 = `eps_fy28_cons` / `eps_fy27_m` − 1；派生值，eval 复算比对；A15; source/as-of: 2026-10-23
    'g1': 0.6393,
    # 过渡年数（仅 FY28）。FactSet 聚合 2026-10-23 首次出现 FY29 10.96 / FY30 12.94，但家数未披露，不满足 ≥2 家 → 仍为 1（n = 2 读数见 Outputs 敏感性）；A15; source/as-of: 2026-10-23
    'n_g1': 1.0,
    # **同业反解·截顶**·永续增速，三档共用：GEV 7.60% / VRT 7.02% / ETN 7.69%（各按其篮 4 r 10% 反解）中位 7.60% → 仓库上限 6%；篮 7 下 cap = min(6%, 15% − 4%) = 6% 未收紧；三档 ROE − r ≥ +8pp 单调区；A13; source/as-of: 2026-09-18
    'g2': 0.06,
    # **过渡篮 = 篮 7 单押 / 国别 / 故事 15%**：今天的性质——对手方：最大客户为关联方融资 SPV / 基金（FY2025 43%），收入依赖未落定的项目融资（单产品 2026-10-03 起不是篮 7 理由，已删）；用于段一与把终值折回今天 \((1+r_j)^n\)；A18; source/as-of: 2026-09-23
    'r_journey': 0.15,
    # **终值篮 = 篮 4 龙头制造 10%**：稳态性质——FY27 共识兑现的世界里是已验证、可月级交付的现场发电设备商，与 GEV / VRT / ETN 同类；只用于终值资本化 \((r_t-g_2)\)；A18; source/as-of: 2026-09-23
    'r_terminal': 0.1,
    # 确定性等价折扣（L 档）= 「走不到稳态」的概率；三档共用（flat，四个跨票比值不受影响）；来源 = `valuation-rules` k 优先序 ③ 兜底 0.3，经纠正对账门上界收紧到 ≤0.232；`待补`；Q3'26 财报重钉：稳态四特征一项达到（关联方收入 26%）、一项变差（剔定金经营现金流），维持 0.20；A21; source/as-of: 2026-10-22
    'k_l': 0.2,
    # 同上（M 档）; source/as-of: 2026-09-23
    'k_m': 0.2,
    # 同上（H 档）; source/as-of: 2026-09-23
    'k_h': 0.2,
    # L 档前瞻 ROE = `eps_fy27_l` ÷ FY27 年初 BPS 17.78（3Q26 账面 13.59 按 \(b_1 = g_1/ROE\) 滚过 4Q26 未入账 1.090/股）；派生值，eval 复算比对；A8 / A19; source/as-of: 2026-10-23
    'roe_l': 0.1662,
    # M 档前瞻 ROE，同上（FY27 年初 BPS 15.76）; source/as-of: 2026-10-23
    'roe_m': 0.3213,
    # H 档前瞻 ROE，同上（FY27 年初 BPS 14.98）; source/as-of: 2026-10-23
    'roe_h': 0.4999,
    # 篮 4 同业 FY+1 前瞻 PE 簇低点（ETN 26.37×；VRT 28.18×）；跨篮只作对照披露、不作 ③ 阻断；自身 NTM 带不可用；A8; source/as-of: 2026-09-18
    'pe_peer_lo': 26.37,
    # 同一簇高点（GEV 37.82×）；同上，只对照；A8; source/as-of: 2026-09-18
    'pe_peer_hi': 37.82,
    # FY28 共识收入 USD（FactSet 聚合）；A7 隐含桥；**不**进主锚点公式; source/as-of: 2026-10-23
    'rev_fy2': 10309000000.0,
    # FY28 共识 EBIT USD；隐含 margin ≈22.1%; source/as-of: 2026-10-23
    'ebit_fy2': 2283000000.0,
    # FY28 共识 Adj. Net Income USD；`adj_ni_fy2 / eps_fy28_cons` ≈ 320M 股; source/as-of: 2026-10-23
    'adj_ni_fy2': 2652000000.0,
    # 未履约义务（主要为产品+安装，预计 1–2 年内确认）USD；10-Q Q3'26 Note 3（Q2'26 4.42e8）; source/as-of: 2026-09-30
    'rpo_product_install': 661200000.0,
    # Customer deposits USD；10-Q Q3'26 Note 3（Q2'26 3.606e8；前三季 +5.831 亿）; source/as-of: 2026-09-30
    'customer_deposits': 661354000.0,
    # 覆盖分母 = 未来 12 个月收入估算：4Q26 共识 1.4242e9 + 0.75 × FY27 共识 6.8162e9（yfinance 2026-10-23）。上一版以 FY26 全年共识作 proxy（读 0.302），本年已过四分之三、会虚高，改按真正的未来 12 个月（较严的读法）；闸门只看方向; source/as-of: 2026-10-23
    'revenue_next_12m': 6536000000.0,
    # `(rpo_product_install + customer_deposits) / revenue_next_12m`；派生值（Q2'26 0.195 为旧 proxy 口径）; source/as-of: 2026-10-23
    'cover': 0.2023,
    # 最近一季（Q3'26）单季最大客户收入占比（非关联方；第二大 26% 为关联方）；Q2'26 0.44；A3 阈值口径（>0.40 触发警惕）；10-Q Note 2; source/as-of: 2026-09-30
    'conc_q_max': 0.43,
    # 前三季累计最大客户收入占比（第二大 23%，关联方）；H1'26 口径曾为 0.73；A3 辅助观察；10-Q; source/as-of: 2026-09-30
    'conc_h1_max': 0.43,
    # Q3'26 产品 Non-GAAP 毛利率（GAAP 37.9%；Q2'26 0.372）；G5「ASP/GM 系统性下修」条款的基线；8-K 2026-10-22 新闻稿; source/as-of: 2026-09-30
    'product_gm': 0.384,
    # Q3'26 相关方收入占比 = 321.6 ÷ 1,235.8（前三季 697.7M）；Q1'26 0.50、Q4'25 0.74；A3 对手方性质观察；10-Q 损益表脚注; source/as-of: 2026-09-30
    'rp_rev_share': 0.26,
    # 期权份数上沿 GW = 公司已签框架合同：Oracle MSA 至多 2.8 GW（其中 1.2 GW firm）+ AEP 至多 1 GW；本票具名的量（valuation-rules「未建模期权」2026-10-03）；A16; source/as-of: 2026-04
    'opt_gw_named': 3.8,
    # 共识已含 GW = FY28 共识桥对应的 2 GW 满载（公司 2026 年底产能 2 GW 目标）；期权份数 = `opt_gw_named` − 本值；单位经济 = `eps_fy28_cons` ÷ 本值 = 每 GW EPS；A16; source/as-of: 2026-09-04
    'opt_gw_cons': 2.0,
    # 期权兑现年 = 对齐年份 FY2028 + 2（Oracle 余量无具名交付年）——**无时点锚·拍值**；按过渡篮 r 折回 FY2027，再同底牌折 τ；A16 / A22; source/as-of: 2026-10-03
    't_opt': 2030.0,
    # 时点对齐年数 = 估值基准日 2026-09-30（3Q26 账面）→ 分子年初 2027-01-01；按过渡篮 r 折（A22）; source/as-of: 2026-09-30
    'tau': 0.25,
    # 归母比例 = 归属普通股权益 1,932.9 ÷ (1,932.9 + 少数股东 30.2)；只用于窗口（A22）; source/as-of: 10-Q 2026-09-30
    'parent_share': 0.985,
    # 高回报期止点 = 可见年末（FY2028 过渡年）（A22）; source/as-of: 2026-10-16
    'y1': 2028.0,
    # 稳态落稳年 = Y1 + 4（进入门槛：中）（A22）; source/as-of: 2026-10-16
    'y2': 2032.0,
    # 稳态回报 = 同生意成熟同业穿越周期**最高**（Generac 24.1%；康明斯 23.0% / 伊顿 16.1%，近 9 个完整财年均值）；规则写中位 23.0%，用户 2026-10-18 裁定取最高（A22）; source/as-of: Longbridge 年报 2026-10-18
    'rs_steady': 0.241,
    # 期权高回报期止点 = 期权满产年 `t_opt`（这 1.8 GW 在 2028 年尚未出货，不随底牌的可见年末 2028；期权世界本身即「2030 年仍供不应求」）；用户 2026-10-19 认可（A16 / A22）; source/as-of: 2026-10-19
    'y1_opt': 2030.0,
    # 期权稳态落稳年 = `y1_opt` + 4（进入门槛：中，同底牌）；用户 2026-10-19 认可（A16 / A22）; source/as-of: 2026-10-19
    'y2_opt': 2034.0,
}

# FY2025 GAAP leverage audit: debt ~$538M / EBITDA ~$124M, interest $54M /
# EBIT $73M (2025 10-K and notes). This is a disclosure and rule finding;
# the existing EPS model uses if-converted equity and is not silently changed.
LEV_2025 = {"net_debt_ebitda": 4.3, "interest_ebit": 0.74}
# Q3 2026 trailing comparison, not a substitute for the fiscal-year gate.
LEV_2026_TTM = {"net_debt_ebitda": 0.5, "interest_ebit": 0.063}

def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0, r_terminal: float | None = None) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2.  Basket pair: the n stage-1 years are discounted at
    the journey rate r, everything after at r_terminal (the structure of two_stage_pe).  With
    rs >= roe this equals two_stage_pe(g1, n, g2, roe, r, r_terminal) exactly.
    (gordon.py three-segment helper is [待建].)"""
    r_tv = r if r_terminal is None else r_terminal
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    def df(t: int) -> float:
        return (1 + r) ** (-min(t, n)) * (1 + r_tv) ** (-max(t - n, 0))

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) * df(t)
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / (r_tv - g2) * df(t - 1)
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) * df(t)
        e *= 1 + g2
        t += 1


def _local_basis_snapshot(axes):
    return {'inputs': INPUTS,
            'constants': {'numerator_year': NUM_YEAR, 'derived_tolerance': DERIVED_TOL,
                          'min_r_minus_g': MIN_R_MINUS_G, 'tiers': TIERS, 'option_weights': P_TIERS,
                          'leverage_2025': LEV_2025, 'leverage_2026_ttm': LEV_2026_TTM}}


# This detects only the listed inputs and historical comparison values.
LOCAL_BASIS_BASELINE = 'ab3bde6d8f9f1efee387ce883e9e78e85cba067ac3cf9bedb54248046e972ad9'


def calculate(context):
    inp = dict(INPUTS)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("inputs must be finite numbers")
    if inp["r_terminal"] <= inp["g2"] or min(inp["r_journey"], inp["r_terminal"]) <= -1:
        raise ValueError("perpetuity or discount factor is mathematically invalid")
    if inp["opt_gw_cons"] <= 0:
        raise ValueError("the consensus quantity must be positive to define per-GW economics")
    if inp["opt_gw_named"] < inp["opt_gw_cons"]:
        raise ValueError("named capacity is below capacity already included in consensus; additional capacity is undefined")
    if any(inp[key] != int(inp[key]) for key in ("n_g1", "t_opt", "y1", "y2", "y1_opt", "y2_opt")):
        raise ValueError("full-year inputs must be whole years")
    if inp["y2"] < inp["y1"] or inp["y2_opt"] < inp["y1_opt"]:
        raise ValueError("return-fade endpoints are inverted")
    # Original latest full-year GAAP checks are triggered; the if-converted
    # model uses a different debt/equity basis. These three rule follow-ups
    # were not completed in the historical research and are not waived here.
    review_flags = ["fy2028_consensus_aggregator_house_count_unknown",
                    "option_completion_year_unanchored"]
    if LEV_2025["net_debt_ebitda"] > 3:
        review_flags.append("fy2025_net_debt_ebitda_threshold_triggered")
    if LEV_2025["interest_ebit"] > 1 / 3:
        review_flags.append("fy2025_interest_ebit_threshold_triggered")
    if LEV_2025["net_debt_ebitda"] > 3 or LEV_2025["interest_ebit"] > 1 / 3:
        review_flags.extend(["leverage_roe_roic_reconciliation_missing",
                             "leverage_unlevered_profit_and_rate_sensitivity_missing",
                             "leverage_ev_peer_crosscheck_missing"])
    baskets = {"r_journey": 7, "r_terminal": 4}
    if check_basket_pair(inp["r_journey"], inp["r_terminal"], "r", 7, 4):
        review_flags.append("discount_basket_pair_invalid")
    if check_k_declared(inp["r_journey"], inp["r_terminal"],
                        (inp["k_l"], inp["k_m"], inp["k_h"]), "k"):
        review_flags.append("required_arrival_haircut_invalid")
    if check_g_cap(inp["g2"], inp["r_journey"], "g2"):
        review_flags.append("terminal_growth_above_cap")
    if inp["r_terminal"] - inp["g2"] < MIN_R_MINUS_G:
        review_flags.append("terminal_growth_close_to_discount_rate")
    if ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"]):
        review_flags.append("forecast_eps_not_increasing")
    if inp["eps_fy28_cons"] <= inp["eps_fy27_h"]:
        review_flags.append("transition_earnings_below_high_forecast")
    if check_transition_years(int(inp["n_g1"]), 1, "n_g1"):
        review_flags.append("transition_year_not_supported_by_consensus")
    if any(key.startswith("p_") for key in inp):
        review_flags.append("option_probability_inside_base_inputs")
    r = inp["r_journey"]
    r_t = inp["r_terminal"]
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    n = int(inp["n_g1"])
    g2 = inp["g2"]
    eps = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}

    # ---- Step 1: derived inputs recomputed from their sources (A8 / A15) ----
    g1 = inp["eps_fy28_cons"] / inp["eps_fy27_m"] - 1.0
    if abs(g1 - inp["g1"]) > DERIVED_TOL:
        review_flags.append('forecast_transition_growth_reconciliation_mismatch')

    # ROE = E_{n+1} / B_n: FY27 EPS over the FY27 OPENING book (= end-2026), not
    # the latest 10-Q book (A19; valuation-rules 2026-09-21).  That if-converted book
    # is rolled over the FY26 earnings not yet booked (FY26 estimate minus year-to-date
    # actual) at the growth-required retention b1 = g1/ROE — all three tiers
    # carry the FY28 window, so all three roll at g1.  ROE and BPS depend on
    # each other; the fixed point is closed-form: BPS = BPS0 / (1 - g1·N/eps).
    # b1 > 1 is the equity issuance the negative stage-1 payout already prices,
    # so it is disclosed, not failed; only a diverging roll (g1·N/eps >= 1) stops.
    bps_2q26 = inp["equity"] / inp["shares"]
    unbooked = inp["eps_fy26_m"] - inp["eps_ytd26_a"]  # per share, rest of FY26 only (opening-FY27 book)

    def opening_bps(eps_x: float) -> float:
        share = g1 * unbooked / eps_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g1·N/eps = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps_2q26 / (1.0 - share)

    bps_open = {t: opening_bps(eps[t]) for t in TIERS}
    roe = {t: eps[t] / bps_open[t] for t in TIERS}
    b1 = {t: g1 / roe[t] for t in TIERS}
    for t, key in zip(TIERS, ("roe_l", "roe_m", "roe_h")):
        if abs(roe[t] - inp[key]) > DERIVED_TOL:
            review_flags.append('forward_return_reconciliation_mismatch' + "_" + t.lower())
    ret_actual = 1.0 - inp["payout_3y"]
    # (actual retention − b1) × N: negative here = the rest-of-FY26 issuance the model books (disclosure only)
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in TIERS}

    # ---- Step 2: multiples (g shared across tiers; only ROE varies) and anchors ----
    # Steady-return path (A22): forward ROE through Y1, linear to rs_steady by Y2, tail at rs_steady.
    y1, y2, rs = int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]

    def tier_pes(g2_: float, transition: bool = True) -> dict[str, float]:
        return {
            t: (three_segment_pe(NUM_YEAR, y1, y2, rs, g2_, roe[t], r, g1=g1, n=n, r_terminal=r_t)
                if transition else three_segment_pe(NUM_YEAR, y1, y2, rs, g2_, roe[t], r_t))
            for t in TIERS
        }

    # Timing (A22): the Gordon value sits at t_n = 2027-01-01; discount tau years at the journey
    # basket to the latest 10-Q balance sheet, plus the rest-of-FY26 window's distributable earnings
    # (unbooked x (1 - b1), clipped at 0 — b1 > 1 in every tier, so the window is 0).
    tau = inp["tau"]
    window = {t: max(unbooked * (1.0 - b1[t]), 0.0) * inp["parent_share"] for t in TIERS}

    def value(pes_: dict[str, float], r_: float) -> dict[str, float]:
        return {t: eps[t] * pes_[t] * (1.0 - k[t]) / (1 + r_) ** tau + window[t] / (1 + r_) ** (tau / 2)
                for t in TIERS}

    # k leaves the anchors only — never the multiple, never b (A21; same
    # discipline as the「视同派出」k).  It is flat across tiers here, so the four
    # cross-ticker ratios are identical with and without it.
    pes = tier_pes(g2)
    anchors = value(pes, r)
    L, M, H = (anchors[t] for t in TIERS)
    if not (L < M < H):
        review_flags.append('base_anchors_not_increasing')

    # ---- Step 3: peer cluster — same basket as the TERMINAL, so it is
    # reconciliation coordinate ⑤, not a cross-basket footnote (A8/A18) ----
    # The peer FY+1 forward-PE cluster is 篮 4 (GEV / VRT / ETN); a ③ band must
    # share the leg's basket, so the cluster is only printed against the tiers.
    lo, hi = inp["pe_peer_lo"], inp["pe_peer_hi"]
    if not (0 < lo < hi):
        review_flags.append('peer_band_invalid')

    # ---- Step 4: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat = flat_multiple_ladder(
        tuple(eps[t] * (1.0 - k[t]) for t in TIERS), pes["M"])
    if flat_errs:
        review_flags.append("flat_numerator_ladder_invalid")
    if not (flat[0] < flat[1] < flat[2]):
        review_flags.append('flat_ladder_not_increasing')
    dec = decompose((L, M, H), (pes["L"], pes["M"], pes["H"]))

    # ---- Step 5: cut points, g2 leverage, order-gate coordinates ----
    A, B = cut_points(L, M, H)

    # Option (A16): V_opt is a stated input of the framework (its four elements
    # live in A16, not in Inputs); the script checks the corrected band and its
    # cut-points reproduce.
    opt_gw = inp["opt_gw_named"] - inp["opt_gw_cons"]
    opt_eps = opt_gw * inp["eps_fy28_cons"] / inp["opt_gw_cons"]
    # Option high-return window on its own product stage (A16 / A22, user 2026-10-19): the 1.8 GW
    # ships nothing in 2028, so Y1 = its own full-output year t_opt, then the base's entry-barrier
    # fade length (medium, 4 years); steady return, g2 and tau are the base's.
    y1_opt, y2_opt = int(inp["y1_opt"]), int(inp["y2_opt"])
    if y1_opt != int(inp["t_opt"]):
        review_flags.append('option_first_year_differs_from_realization')
    if y2_opt - y1_opt != y2 - y1:
        review_flags.append('option_return_fade_length_differs_from_main')
    opt_pe = three_segment_pe(int(inp["t_opt"]), y1_opt, y2_opt, rs, g2, roe["H"], r_t)
    v_opt = opt_eps * opt_pe * (1.0 - k["H"]) / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR) / (1.0 + r) ** tau

    p_tiers = P_TIERS
    band_v = tuple(a + p * v_opt for a, p in zip((L, M, H), p_tiers))
    pes_dn = tier_pes(g2 - 0.01)
    v_dn = value(pes_dn, r)
    cover = (inp["rpo_product_install"] + inp["customer_deposits"]) / inp["revenue_next_12m"]
    if abs(cover - inp["cover"]) > 0.01:
        review_flags.append("order_coverage_reconciliation_mismatch")
    if inp["conc_q_max"] > 0.4:
        # Q3 43%, Q2 44%: this is a watch, not the two-quarter non-improvement trigger.
        review_flags.append("largest_customer_over_40pct_single_quarter_watch")
    no_transition = value(tier_pes(g2, transition=False), r)
    roe26 = inp["eps_fy26_m"] / opening_bps(inp["eps_fy26_m"])
    pe26 = three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roe26, r, g1=g1, n=n, r_terminal=r_t)
    def alternative_steady(steady, end_year=y2):
        return value({tier: three_segment_pe(NUM_YEAR, y1, end_year, steady, g2,
                     roe[tier], r, g1=g1, n=n, r_terminal=r_t) for tier in TIERS}, r)
    no_haircut = {tier: eps[tier] * pes[tier] / (1 + r) ** tau
                  + window[tier] / (1 + r) ** (tau / 2) for tier in TIERS}
    return {
        "ticker": "BE.US", "currency": "USD", "valuation_as_of": None,
        "framework_as_of": None, "historical_valuation_as_of": "2026-09-30",
        "historical_framework_as_of": "2026-10-23", "basis_changed": None, "partial_basis_changed": local_basis_changed(_local_basis_snapshot(context['axes']), LOCAL_BASIS_BASELINE),
        "units": {"price": "USD_PER_SHARE"},
        "anchors": anchors, "candidate": None,
        "option": {"value": v_opt, "value_unit": "USD_PER_SHARE", "weights": dict(zip(TIERS, p_tiers)),
                   "anchors": dict(zip(TIERS, band_v))},
        "segments": {"company": {"unit": "USD_PER_SHARE", "values": anchors}},
        "key_parameters": {"transition_discount_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, r)},
                           "terminal_discount_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, r_t)},
                           "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(TIERS, g2)},
                           "forward_return": {"unit": "RATIO", "values": roe},
                           "steady_return": {"unit": "RATIO", "values": {tier: min(roe[tier], rs) for tier in TIERS},
                                             "reference_value": rs}},
        "transition_growth": g1,
        "diagnostics": {"opening_bps": bps_open, "multiples": pes,
                        "retention": b1, "window": window, "actual_retention": ret_actual,
                        "required_external_financing": excess_cash, "flat_ladder": dict(zip(TIERS, flat)),
                        "decomposition": dec, "order_coverage": cover,
                        "option_extra_gw": opt_gw, "option_eps": opt_eps, "option_multiple": opt_pe,
                        "leverage_fy2025_gaap": LEV_2025, "leverage_2026_ttm_comparison": LEV_2026_TTM},
        "sensitivity": {"terminal_growth_minus_1pp": v_dn, "no_transition": no_transition,
                        "no_arrival_haircut": no_haircut,
                        "steady_return_median_23pct": alternative_steady(0.23),
                        "steady_return_fallback_15pct": alternative_steady(0.15),
                        "steady_return_end_2030": alternative_steady(rs, 2030),
                        "steady_return_end_2034": alternative_steady(rs, 2034),
                        "fy2026_earnings_low_coordinate": inp["eps_fy26_m"] * pe26 * (1 - k["L"]) / (1 + r) ** tau},
        "review_flags": review_flags,
    }
