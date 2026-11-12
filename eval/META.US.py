"""META historical valuation migration; no fresh research or model execution.

Two legs and a financing adjustment preserve the original 2026-10-29 study.
The capital-path snapshot preserves the historical adopted approximation,
not a user confirmation or a guarantee that future investment earns that ROIC.
"""
from __future__ import annotations
import math
from lib.gordon import check_branch, check_g_cap, check_r, payout_gap, perpetual_pe
from lib.inputs import ladder
from lib.partial_basis import local_basis_changed
from lib.historical_precision import historical_meta_invested_capital, preserve_reference_residual, replace_capex_reference
from lib.valuation_guards import nonnegative_option_value

DEPENDENCIES = {"libraries": ("gordon", "inputs", "historical_precision", "valuation_guards", "partial_basis"),
                "axes": {"capex": "ai_capex"}}
TIERS = ("l", "m", "h")
P_TIERS = (0.0, 1.0 / 6.0, 1.0)
PAYOUT_OBSERVED = 0.32
M_BAND_TOL, H_BAND_TOL = 0.02, 0.01
INPUTS = {
    # 稀释股本（B）= Q3 2026 加权稀释股数（8-K 附件 99.1）；2027-01-19 C 类股送股生效后按 ×2 换口径（A17）; source/as-of: 2026-09-30
    'shares': 2.573,
    # FY2027E 共识 GAAP EPS 低端（56 家，yfinance earnings_estimate）；A3; source/as-of: 2026-10-28
    'eps_l': 29.32,
    # FY2027E 共识 GAAP EPS 均值（同源）；A3; source/as-of: 2026-10-28
    'eps_m': 33.94,
    # FY2027E 共识 GAAP EPS 高端（同源）；A3; source/as-of: 2026-10-28
    'eps_h': 41.5,
    # RL 年化经营亏损 L 档（B）= 2027 不收窄、停在 FY26 指引 $180–190 亿中点；只进 RL 腿；A18; source/as-of: 2026-10-21
    'rl_loss_l': 18.5,
    # RL 年化经营亏损 M 档（B）= 管理层 2027 指引「around $15 billion」（Q3 新闻稿 / call 2026-10-21）；只进 RL 腿；A18; source/as-of: 2026-10-21
    'rl_loss_m': 15.0,
    # RL 年化经营亏损 H 档（B）= 同 M；「trending towards profitability」无量值，不另设更窄档；只进 RL 腿；A18; source/as-of: 2026-10-21
    'rl_loss_h': 15.0,
    # 共识 EPS 里已扣的 RL 亏损（B），三档同值，只用于加回 FoA 腿：卖方已按 2027 指引 ~$150 亿改模型，且把 RL 少亏的钱等额改记为 AI 投入（大摩 2026-10-22：RL 2027/28 下调约 $40 / 30 亿、AI 投入相应上调、EPS 持平；管理层「不假设总运营支出下降」），FY27 共识均值 33.87 → 33.94 近不变；A18; source/as-of: 2026-10-29
    'rl_addback': 15.0,
    # 年化利息费用（B）。**维持**：Q2 10-Q 利息费用 0.783 → 3.1 年化；4 月 30 日 $250 亿六期票据 4.55–6.45%（加权 ≈5.7%，+$14 亿/年）Q2 只计 2 个月 → 满季 run-rate ≈ 3.6；Q2 后至 2026-09-18 无新公司债（9-17 的 Meta 关联数据中心高收益债为项目层 SPV，不上表）；总债 $837 亿 × ≈4.9% ≈ 4.1 为上限。FY27 明显 >5 需再发 ≥$250 亿，届时改此行；A6; source/as-of: 2026-09-18
    'interest': 4.0,
    # 有效税率 = Q2'26 16.0% 与 FY23 17.6% 中点；Q3'26 剔除和解后 17%、Q4 指引 15–17% 印证（FY25 29.6% 含 Q3'25 一次性 $189.5 亿、Q1'26 −23% 回冲，均剔除）; source/as-of: 2026-10-21
    'tax': 0.17,
    # 归母权益（B），Q3 2026 资产负债表（8-K 附件 99.1）; source/as-of: 2026-09-30
    'equity': 272.4,
    # 净负债（B）= 公司债 83.7（call 口径，含一年内到期）+ **融资租赁 28.7**（沿用 Q2 10-Q，Q3 10-Q 出后更新）− 现金与有价证券 82.45；数据中心租赁是债务性资本，计入 IC 与闭合项与属性 B 口径一致；受限现金 $125 亿（其他资产）用途未披露，不计入现金; source/as-of: 2026-09-30
    'net_debt': 29.95,
    # 和解 NPV（B）= Q3 实际计提 $98.9 亿（固定部分约 70% 分 10 年付；或有 30% 不进）；A8; source/as-of: 2026-09-30
    'settlement_npv': 9.89,
    # 新墨西哥州隐私案民事罚款（B），2026-10-21 州法院判决全额（另 15% 判决后年息未计）；Meta 10-Q「accrued an amount」未披露金额、将上诉，庭上主张 ≤ $15.3 亿；严格口径全额作类债项扣；A19; source/as-of: 2026-10-21
    'nm_penalty': 25.0,
    # 2026-10 股权发行新增股数（B 股）= 远期出售 A 股 0.040（$625，2027-11-19 前交割）+ 强制可转优先股按最高转换率 1.6 × 1,250 万股 = 0.020（2029-08 转换，区间 0.017–0.020，取严）；超额配售未计；A17; source/as-of: 2026-10-26
    'new_shares': 0.06,
    # 2026-10 股权发行净募资（B）= 远期 24.9（初始远期价 $622.92）+ 优先股 12.5；视同已到账（远期最晚 13 个月内交割，不折）；A17; source/as-of: 2026-10-26
    'offering_proceeds': 37.4,
    # 优先股股息至转换日的现值（B）：首期 $19.14 + 其后每季 $16.25 / 股 × 1,250 万股，约 $22.7 亿到 2029-08，按 10% 折现；A17; source/as-of: 2026-10-26
    'pref_div_pv': 2.0,
    # FoA 腿折现率 = **篮 4 龙头制造** 10%：常规经营现金流、可见度高的行业龙头，与 GOOG Services 腿同篮（A2）；值 = `gordon.BASKET_R[4]`，`check_r()` 按篮子强制; source/as-of: 2026-09-20
    'r_foa': 0.1,
    # RL 腿折现率 = **篮 4** 与 FoA 同 r：负值流由集团现金流稳定支付，更高 r 会系统性抬高估值，不归篮 7（A2）；值 = `gordon.BASKET_R[4]`，`check_r()` 按篮子强制; source/as-of: 2026-09-20
    'r_rl': 0.1,
    # FoA 永续增长 = 同业簇按「今天的经营价值」同口径重解（折 τ、回报路径）的剔除自身中位 6.36%（GOOG 7.39 / RDDT 6.36 / TTD 4.04），截到 \(G_{cap}\) 6%；A5; source/as-of: 2026-10-16
    'g2': 0.06,
    # 时点对齐：估值基准日 2026-09-30（Q3 资产负债表日）→ 分子年 FY2027 年初 2027-01-01 的年数；A15; source/as-of: 2026-09-30
    'tau': 0.25,
    # 稳态回报 = 自身周期（按序取第一层）：最近一轮完整谷到谷 2019–2022（经营利润谷 2019 / 2022）投入资本口径均值 41.9%（10-K XBRL；公司合并 GAAP 经营利润含 RL 亏损，读法更严）；同业 TTD 20.6%、兜底 30% 只作对照；三档前瞻 ROIC 都低于它，回报路径不起作用；A16; source/as-of: 2026-10-19
    'ronic_ss': 0.419,
    # FY2026E 共识 GAAP EPS 均值（yfinance，已含 Q3 实际）；只用来推 Q4 窗口利润与经营现金流；A15; source/as-of: 2026-10-28
    'eps_fy26': 29.16,
    # 2026 前 9 月实际 GAAP 稀释 EPS（8-K 附件 99.1）；A15; source/as-of: 2026-09-30
    'eps_9m_26': 20.44,
    # 经营现金流 ÷ 净利，近 3 年实测；A15; source/as-of: 2025-12-31
    'ocf_ni': 1.73,
    # 2026 Q4 资本开支（B）= 全年指引中值 140（$1,350–1,450 亿）− 前 9 月实际 85.8（购置 PP&E 83.06 + 融资租赁本金 2.77）；A15; source/as-of: 2026-10-21
    'capex_q4_26': 54.2,
    # 2026 Q4 股权激励（B，非现金加回，不是可用现金）= Q3 实际 7.36；A15; source/as-of: 2026-09-30
    'sbc_q4_26': 7.4,
    # reported TTM GAAP EPS（Q4'25–Q3'26）= FY25 23.49 − 9M25 14.62 + 9M26 20.44，③ 护栏分母; source/as-of: 2026-09-30
    'eps_ttm_reported': 29.31,
    # 干净 TTM EPS（严格口径，用户 2026-10-22）= Q4'25 8.87 + Q1'26 7.00（扣一次性税收回冲 ≈ $88 亿，按 17% 重算）+ Q2'26 7.34（加回法律与遣散 $36 亿税后）+ Q3'26 7.40（公司口径剔和解）; source/as-of: 2026-09-30
    'eps_ttm_clean': 30.61,
    # 自身 5 年 reported PE 带下沿，③ 护栏; source/as-of: 2026-09-18
    'pe_own_min': 21.0,
    # 自身 5 年 reported PE 带上沿，③ 护栏; source/as-of: 2026-09-18
    'pe_own_max': 28.7,
    # FY26 capex 指引下沿 USD（Q3 自 1,300 收窄）；**不进分子**，轴构成方份额校验；A11; source/as-of: 2026-10-21
    'capex_guide_low': 135000000000.0,
    # FY26 capex 指引上沿 USD（中值 140B）；同上; source/as-of: 2026-10-21
    'capex_guide_high': 145000000000.0,
    # AMD 绩效认股权证股数上限（B 股），AMD IR 2026-02-24 公告；**只进 \(V_{opt}\) / 表3，不进底牌**；A14; source/as-of: 2026-02-24
    'amd_warrant_shares': 0.16,
    # 权证行权价 USD/股（Yahoo Finance / MarketBeat 报道，AMD 公告未列数字）；A14; source/as-of: 2026-02-24
    'amd_warrant_strike': 0.01,
    # AMD.US 收盘 USD（Longbridge；他股市价，非本票价格），权证单位经济；低于末批门槛 $600，A14 weakened; source/as-of: 2026-10-21
    'amd_price': 552.72,
    # GS FY2027 capital expenditure forecast (not company guidance); original capital-path description, 2026-10-26; USD billion.
    "capex_fy27": 223.4,
    # Wedbush FY2027 249bn comparison from original A11; independent scenario, not adopted guidance; Q3 2026, USD billion.
    "capex_fy27_reference": 249.0,
}

# The old path rounded the adopted capital to $499.8bn. Keep the 2026-10-29
# reference input snapshot and adoption as historical precision evidence; the
# original path and historical 223.4 capex forecast are frozen in the separate
# source-bound reference helper. Current model inputs and formula remain distinct.
HISTORICAL_REFERENCE = {
    # Frozen 2026-10-29 reference, not a current input: 稀释股本（B）= Q3 2026 加权稀释股数（8-K 附件 99.1）；2027-01-19 C 类股送股生效后按 ×2 换口径（A17）; as-of 2026-09-30
    'shares': 2.573,
    # Frozen 2026-10-29 reference, not a current input: FY2027E 共识 GAAP EPS 均值（同源）；A3; as-of 2026-10-28
    'eps_m': 33.94,
    # Frozen 2026-10-29 reference, not a current input: 归母权益（B），Q3 2026 资产负债表（8-K 附件 99.1）; as-of 2026-09-30
    'equity': 272.4,
    # Frozen 2026-10-29 reference, not a current input: 净负债（B）= 公司债 83.7（call 口径，含一年内到期）+ **融资租赁 28.7**（沿用 Q2 10-Q，Q3 10-Q 出后更新）− 现金与有价证券 82.45；数据中心租赁是债务性资本，计入 IC 与闭合项与属性 B 口径一致；受限现金 $125 亿（其他资产）用途未披露，不计入现金; as-of 2026-09-30
    'net_debt': 29.95,
    # Frozen 2026-10-29 reference, not a current input: FY2026E 共识 GAAP EPS 均值（yfinance，已含 Q3 实际）；只用来推 Q4 窗口利润与经营现金流；A15; as-of 2026-10-28
    'eps_fy26': 29.16,
    # Frozen 2026-10-29 reference, not a current input: 2026 前 9 月实际 GAAP 稀释 EPS（8-K 附件 99.1）；A15; as-of 2026-09-30
    'eps_9m_26': 20.44,
    # Frozen 2026-10-29 reference, not a current input: 经营现金流 ÷ 净利，近 3 年实测；A15; as-of 2025-12-31
    'ocf_ni': 1.73,
    # Frozen 2026-10-29 reference, not a current input: 2026 Q4 资本开支（B）= 全年指引中值 140（$1,350–1,450 亿）− 前 9 月实际 85.8（购置 PP&E 83.06 + 融资租赁本金 2.77）；A15; as-of 2026-10-21
    'capex_q4_26': 54.2,
    "capex_fy27": 223.4,
}
HISTORICAL_IC_ADOPTED = 499.8
HISTORICAL_PARTIAL_FINGERPRINT = '17107bd9f2f171892fa7308dab387f388637e82dd683a2d363e5e43cc8080775'

def to_equity(v: float, inp: dict[str, float]) -> float:
    """Spread the per-share deck over the post-offering count, cash in, preferred dividends out."""
    shares = inp["shares"]
    return (v * shares + inp["offering_proceeds"] - inp["pref_div_pv"]) / (shares + inp["new_shares"])


def funding_gap(inp: dict[str, float]) -> float:
    """① growth-period funding gap per share: Q4'26 capex + SBC beyond Q4'26 OCF."""
    ocf = (inp["eps_fy26"] - inp["eps_9m_26"]) * inp["shares"] * inp["ocf_ni"]
    return max(inp["capex_q4_26"] + inp["sbc_q4_26"] - ocf, 0.0) / inp["shares"]

TIERS = ("l", "m", "h")

def warrant_value(inp: dict[str, float], amd_price: float | None = None) -> float:
    """A14: after-tax face value per META share of the AMD warrant at full vesting."""
    px = inp["amd_price"] if amd_price is None else amd_price
    per = inp["shares"] + inp["new_shares"]
    return inp["amd_warrant_shares"] * (px - inp["amd_warrant_strike"]) * (1.0 - inp["tax"]) / per


def band(
    inp: dict[str, float],
    *,
    g2: float | None = None,
    ic: float | None = None,
    r_shift: float = 0.0,
    rl_scale: float = 1.0,
    tax: float | None = None,
    settlement_npv: float | None = None,
) -> dict[str, dict[str, float]]:
    """Per-tier {v, nopat, roic, pe, rl} for the base deck or one perturbation."""
    g2 = inp["g2"] if g2 is None else g2
    ic = inp["ic_fy27"] if ic is None else ic
    tax = inp["tax"] if tax is None else tax
    settlement_npv = inp["settlement_npv"] if settlement_npv is None else settlement_npv
    r_foa, r_rl = inp["r_foa"] + r_shift, inp["r_rl"] + r_shift
    shares = inp["shares"]
    closing = -(inp["net_debt"] + settlement_npv + inp["nm_penalty"]) / shares - funding_gap(inp)
    disc = (1.0 + r_foa) ** inp["tau"]
    out: dict[str, dict[str, float]] = {}
    for k in TIERS:
        rl_ps = inp[f"rl_loss_{k}"] * rl_scale * (1.0 - tax) / shares
        add_ps = inp["rl_addback"] * (1.0 - tax) / shares
        nopat = inp[f"eps_{k}"] + add_ps + inp["interest"] * (1.0 - tax) / shares
        roic = nopat * shares / ic
        pe = perpetual_pe(g2, roic, r_foa)
        rl_leg = -rl_ps / r_rl
        out[k] = {"v": to_equity((nopat * pe + rl_leg) / disc + closing, inp), "nopat": nopat, "roic": roic, "pe": pe,
                  "rl": rl_leg, "disc": disc}
    return out


def lmh(b: dict[str, dict[str, float]]) -> tuple[float, float, float]:
    return b["l"]["v"], b["m"]["v"], b["h"]["v"]


def invested_capital_path(inp):
    """Current capital = starting capital plus two net-investment bridges."""
    current = inp["equity"] + inp["net_debt"]
    q4_earnings = (inp["eps_fy26"] - inp["eps_9m_26"]) * inp["shares"]
    fy27_earnings = inp["eps_m"] * inp["shares"]
    return (current + q4_earnings + inp["capex_q4_26"] - q4_earnings * inp["ocf_ni"]
            + fy27_earnings + inp["capex_fy27"] - fy27_earnings * inp["ocf_ni"])


def calculate(context):
    inp = dict(INPUTS)
    capex = context["axes"]["capex"]
    if capex["role"] != "constituent":
        raise ValueError("META is an AI capital-spending pool constituent")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("inputs must be finite numbers")
    if inp["shares"] <= 0 or inp["shares"] + inp["new_shares"] <= 0:
        raise ValueError("pre- and post-offering shares must be positive")
    if min(inp["r_foa"], inp["r_rl"]) <= 0 or inp["r_foa"] <= inp["g2"]:
        raise ValueError("discount or perpetual-growth rate is mathematically invalid")
    raw_ic = invested_capital_path(inp)
    historical_raw_ic = historical_meta_invested_capital(HISTORICAL_REFERENCE)
    inp["ic_fy27"] = preserve_reference_residual(raw_ic, historical_raw_ic, HISTORICAL_IC_ADOPTED)
    if inp["ic_fy27"] == 0:
        raise ValueError("invested capital cannot be zero")
    review_flags = ["historical_low_multiple_user_decision_2026_10_29",
                    "historical_capital_path_rounding_residual_carried",
                    "investment_return_rebound_and_new_business_capex_rules_pending",
                    "amd_warrant_market_price_historical_and_vesting_conditional"]
    if check_r(inp["r_foa"], "r_foa", 4):
        review_flags.append("foa_discount_basket_mismatch")
    if check_r(inp["r_rl"], "r_rl", 4):
        review_flags.append("reality_labs_discount_basket_mismatch")
    if check_g_cap(inp["g2"], inp["r_foa"], "g2"):
        review_flags.append("growth_above_cap")
    if inp["r_foa"] - inp["g2"] < 0.02:
        review_flags.append("growth_close_to_discount_rate")
    if any(k == "p" or k.startswith("p_") for k in inp):
        review_flags.append("option_probability_inside_base_inputs")
    if not 0 < inp["capex_guide_low"] <= inp["capex_guide_high"] < capex["base_2026_usd"]:
        review_flags.append("capex_constituent_guidance_outside_pool")
    base = band(inp)
    L, M, H = lmh(base)
    if ladder("base", L, M, H):
        review_flags.append("base_anchors_not_increasing")
    if ladder("nopat", *(base[t]["nopat"] for t in TIERS)):
        review_flags.append("foa_profit_not_increasing")
    if not inp["rl_loss_l"] >= inp["rl_loss_m"] >= inp["rl_loss_h"]:
        review_flags.append("reality_labs_loss_order_invalid")
    # Original main formula is flat-return Gordon only; a future input that
    # requires a return-fade path is a technical limitation, not a valid band.
    if any(base[t]["roic"] > inp["ronic_ss"] + 1e-12 for t in TIERS):
        raise ValueError("forward ROIC exceeds historical steady return; rebuild the return path")
    if check_branch(inp["g2"], base["m"]["roic"], inp["r_foa"], PAYOUT_OBSERVED, "M"):
        review_flags.append("foa_retention_branch_requires_review")
    pe_m_ttm, pe_h_clean = M / inp["eps_ttm_reported"], H / inp["eps_ttm_clean"]
    if pe_m_ttm > inp["pe_own_max"] or 1 - pe_m_ttm / inp["pe_own_min"] > M_BAND_TOL:
        review_flags.append("middle_multiple_outside_historical_reference_band")
    if pe_h_clean / inp["pe_own_max"] - 1 > H_BAND_TOL:
        review_flags.append("high_multiple_above_historical_reference_band")
    # Original low-tier comparable-earnings floor and the 2026-10-29 decision
    # are historical evidence, not a blanket approval for later changed data.
    if L / inp["eps_l"] < 20.5:
        review_flags.append("low_multiple_below_historical_comparable_floor")
    v_opt = warrant_value(inp)
    available_option = nonnegative_option_value(v_opt)
    if available_option is None:
        review_flags.append("amd_warrant_underwater")
    weights = dict(zip(("L", "M", "H"), P_TIERS))
    option_band = (None if available_option is None else
                   dict(zip(("L", "M", "H"), (v + p * available_option for v, p in zip((L, M, H), P_TIERS)))))
    option_result = (None if available_option is None else
                     {"value": available_option, "value_unit": "USD_PER_SHARE", "weights": weights,
                      "anchors": option_band, "status": "requires_reconciliation"})
    shares, factor = inp["shares"], inp["shares"] / (inp["shares"] + inp["new_shares"])
    gap = funding_gap(inp)
    closing = -(inp["net_debt"] + inp["settlement_npv"] + inp["nm_penalty"]) / shares - gap
    issuance = (inp["offering_proceeds"] - inp["pref_div_pv"]) / (shares + inp["new_shares"])
    middle_multiple = base["m"]["pe"]
    flat = [to_equity((base[t]["nopat"] * middle_multiple + base[t]["rl"]) / base["m"]["disc"] + closing, inp)
            for t in TIERS]
    if ladder("flat-multiple", *flat):
        review_flags.append("flat_multiple_ladder_invalid")
    segments = {
        "foa": {"unit": "USD_PER_SHARE", "values": {t.upper(): base[t]["nopat"] * base[t]["pe"] / base[t]["disc"] * factor for t in TIERS}},
        "reality_labs": {"unit": "USD_PER_SHARE", "values": {t.upper(): base[t]["rl"] / base[t]["disc"] * factor for t in TIERS}},
        "debt_settlement_and_funding": {"unit": "USD_PER_SHARE", "values": dict.fromkeys(("L", "M", "H"), closing * factor)},
        "equity_offering": {"unit": "USD_PER_SHARE", "values": dict.fromkeys(("L", "M", "H"), issuance)},
    }
    def as_band(values):
        return dict(zip(("L", "M", "H"), lmh(values)))
    payout_modelled, payout_difference = payout_gap(inp["g2"], base["m"]["roic"], PAYOUT_OBSERVED)
    return {
        "ticker": "META.US", "currency": "USD", "valuation_as_of": None, "framework_as_of": None,
        "historical_valuation_as_of": "2026-09-30", "historical_framework_as_of": "2026-10-29",
        "basis_changed": None, "partial_basis_changed": local_basis_changed(
            {"inputs": INPUTS, "historical_reference": HISTORICAL_REFERENCE,
             "historical_ic_adopted": HISTORICAL_IC_ADOPTED,
             "capex": {"role": capex["role"], "base_2026_usd": capex["base_2026_usd"]},
             "option_weights": P_TIERS, "payout_observed": PAYOUT_OBSERVED,
             "band_tolerances": [M_BAND_TOL, H_BAND_TOL]}, HISTORICAL_PARTIAL_FINGERPRINT),
        "units": {"price": "USD_PER_SHARE"},
        "anchors": dict(zip(("L", "M", "H"), (L, M, H))), "candidate": None,
        "option": option_result,
        "option_unavailable_reason": "amd_warrant_underwater" if option_result is None else None,
        "segments": segments,
        "key_parameters": {
            "foa": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["r_foa"])},
                    "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["g2"])},
                    "forward_return": {"unit": "RATIO", "values": {t.upper(): base[t]["roic"] for t in TIERS}},
                    "steady_return": {"unit": "RATIO", "values": {t.upper(): min(base[t]["roic"], inp["ronic_ss"]) for t in TIERS},
                                      "reference_value": inp["ronic_ss"]}},
            "reality_labs": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["r_rl"])},
                             "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), 0.0)}}},
        "diagnostics": {"foa_nopat_per_share": {t.upper(): base[t]["nopat"] for t in TIERS},
                        "foa_multiples": {t.upper(): base[t]["pe"] for t in TIERS},
                        "invested_capital_usd_bn": inp["ic_fy27"], "invested_capital_unrounded_usd_bn": raw_ic,
                        "historical_capital_rounding_residual_usd_bn": HISTORICAL_IC_ADOPTED - historical_raw_ic,
                        "funding_gap_per_old_share": gap, "flat_multiple_ladder": dict(zip(("L", "M", "H"), flat)),
                        "payout_modelled": payout_modelled,
                        "payout_gap": payout_difference,
                        "capex_guide_share_low": inp["capex_guide_low"] / capex["base_2026_usd"],
                        "capex_guide_share_high": inp["capex_guide_high"] / capex["base_2026_usd"]},
        "sensitivity": {"growth_minus_1pp": as_band(band(inp, g2=inp["g2"] - .01)),
                        "growth_plus_1pp_reference": as_band(band(inp, g2=inp["g2"] + .01)),
                        "capital_frozen": as_band(band(inp, ic=inp["equity"] + inp["net_debt"])),
                        "capital_high_capex": as_band(band(inp, ic=replace_capex_reference(
                            inp["ic_fy27"], inp["capex_fy27"], inp["capex_fy27_reference"]))),
                        "reality_labs_zero": as_band(band(inp, rl_scale=0.0)),
                        "settlement_contingent_middle": band(inp, settlement_npv=inp["settlement_npv"] + 5.3)["m"]["v"],
                        "tax_21pct_middle": band(inp, tax=.21)["m"]["v"],
                        "amd_warrant_prices": {"400": warrant_value(inp, 400), "600": warrant_value(inp, 600), "800": warrant_value(inp, 800)},
                        "option_middle_50pct_weight": None if available_option is None else M + 0.5 * available_option},
        "review_flags": review_flags,
    }
