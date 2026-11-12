"""SPCX historical SOTP migration draft; no new research or stock execution.

Starlink, launch, computing and the cash bridge are separate value components.
The direct-to-cell conditional value and broker candidate must not be combined
without first verifying their respective assumptions and any overlapping value.
"""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, perpetual_pe
from lib.inputs import require_whole_years
from lib.partial_basis import local_basis_changed
from lib.zones import cut_points
from lib.valuation_guards import require_axis_alignment
from lib.share_dilution import conditional_award_dilution

DEPENDENCIES = {"libraries": ("gordon", "inputs", "zones", "valuation_guards", "share_dilution", "partial_basis"),
                "axes": {"direct": "direct_to_cell", "funding": "frontier_lab_funding"}}
NUM_YEAR = 2027
TIERS = ("l", "m", "h")
BASKETS = {"r_starlink": 4, "r_space": 4, "r_compute": 7}
INPUTS = {
    # 股本（十亿股）= 10-Q 封面 A 7.6963 + B 5.4855 + Cursor 增发 0.3893 + 0.0018; source/as-of: 2026-08-14
    'shares': 13.5728,
    # 美国联邦法定税率（有效税率 `待补`）; source/as-of: —
    'tax': 0.21,
    # Starlink 个人用户（百万），10-Q KPI; source/as-of: 2026-06-30
    'subs0': 12.0,
    # L 季度净增（Q2 实测减半，A2）; source/as-of: 2026-09-24
    'adds_q_l': 0.85,
    # M 季度净增（Q2 实测 10.3 → 12.0）; source/as-of: 2026-06-30
    'adds_q_m': 1.7,
    # H 季度净增（A2）; source/as-of: 2026-09-24
    'adds_q_h': 2.5,
    # L 月 ARPU（A2 证伪线）; source/as-of: 2026-09-24
    'arpu_l': 55.0,
    # M 月 ARPU（Q2 66，续降一档）; source/as-of: 2026-09-24
    'arpu_m': 62.0,
    # H 月 ARPU（Q2 实测持平）; source/as-of: 2026-06-30
    'arpu_h': 66.0,
    # L 终端硬件收入; source/as-of: 2026-09-24
    'hw_l': 1.0,
    # M 终端硬件收入; source/as-of: 2026-09-24
    'hw_m': 1.5,
    # H 终端硬件收入; source/as-of: 2026-09-24
    'hw_h': 2.0,
    # 企业与政府收入 Q2 年化（1,806 × 4），10-Q 收入分解; source/as-of: 2026-06-30
    'eg0': 7.224,
    # L 企业与政府年增（A2）; source/as-of: 2026-09-24
    'eg_g_l': 0.2,
    # M 企业与政府年增; source/as-of: 2026-09-24
    'eg_g_m': 0.4,
    # H 企业与政府年增; source/as-of: 2026-09-24
    'eg_g_h': 0.6,
    # L Connectivity 经营利润率; source/as-of: 2026-09-24
    'margin_c_l': 0.33,
    # M 经营利润率（Q2 实测 1,656 / 4,291）; source/as-of: 2026-06-30
    'margin_c_m': 0.39,
    # H 经营利润率; source/as-of: 2026-09-24
    'margin_c_h': 0.42,
    # Starlink 增量 ROIC（`待补` 拍值，A10）; source/as-of: 2026-09-24
    'roic_starlink': 0.3,
    # Starlink 永续增速（无同业锚，A10）; source/as-of: 2026-09-24
    'g2_starlink': 0.05,
    # 篮 4 龙头制造：客户分散、全球低轨宽带唯一规模玩家（A4）; source/as-of: 2026-09-24
    'r_starlink': 0.1,
    # L 外部发射 EBIT 剔 Starship 研发（1H26：1,581 − 610 − 169，年化）; source/as-of: 2026-06-30
    'space_ebit_l': 1.604,
    # M（Q2：962 − 329 − 99，年化）; source/as-of: 2026-06-30
    'space_ebit_m': 2.136,
    # H = M × 1.15（A8）; source/as-of: 2026-09-24
    'space_ebit_h': 2.456,
    # 篮 4 龙头制造：全球发射份额 52%、积压订单（A4）; source/as-of: 2026-09-24
    'r_space': 0.1,
    # 外部发射永续增速（A8）; source/as-of: 2026-09-24
    'g_space': 0.0,
    # g = 0 时不进倍数; source/as-of: —
    'roic_space': 0.3,
    # L 已签算力年化 = M − Anthropic 15.0（A5 / A6）; source/as-of: 2026-09-24
    'rev_ctr_l': 26.1,
    # M 已签算力年化（CFO，高盛会议）; source/as-of: 2026-09-10
    'rev_ctr_m': 41.1,
    # H 年底新云 ARR（德银 100147）; source/as-of: 2026-08-10
    'rev_ctr_h': 48.0,
    # 篮 7 单押 / 条件性：前两大客户 ≥70%、合同 90 天可退（A4）; source/as-of: 2026-09-24
    'r_compute': 0.15,
    # 算力运营成本 / 收入（`待补` 拍值，A6）; source/as-of: 2026-09-24
    'opex_pct': 0.15,
    # GPU 折旧年限（`待补`，A6）; source/as-of: 2026-09-24
    'gpu_life': 5.0,
    # 累计 AI 资本开支至 YE2026 = FY23–25 18.823 + 1H26 23.551 + H2 指引 36.738 × 86.2%; source/as-of: 2026-09-24
    'ai_capex_cum': 74.03,
    # YE2026 装机（高盛 99237）; source/as-of: 2026-08-05
    'gw0': 2.3,
    # L YE2027 装机（摩根士丹利模型）; source/as-of: 2026-08-06
    'gw_l': 5.0,
    # M YE2027 装机（摩根大通）; source/as-of: 2026-08-05
    'gw_m': 6.4,
    # H YE2027 装机（高盛 / 管理层）; source/as-of: 2026-09-11
    'gw_h': 10.0,
    # 现金及等价物; source/as-of: 2026-06-30
    'cash': 93.522,
    # 短期有价证券; source/as-of: 2026-06-30
    'mkt_sec': 6.487,
    # 债务本金 38.433 + 融资租赁 1.079（含 Valor 售后回租 13.329）; source/as-of: 2026-06-30
    'debt': 39.512,
    # L 下半年 EBITDA = Q2 × 2; source/as-of: 2026-06-30
    'h2_ebitda_l': 7.076,
    # M 下半年 EBITDA = 高盛 FY2026 26.348 − 1H 4.665（单家）; source/as-of: 2026-09-11
    'h2_ebitda_m': 21.683,
    # H 同 M; source/as-of: 2026-09-11
    'h2_ebitda_h': 21.683,
    # 下半年利息（1H 1.293）; source/as-of: 2026-06-30
    'h2_interest': 1.3,
    # 下半年资本开支（CFO：与 Q2 18.369 相近 × 2）; source/as-of: 2026-08-04
    'h2_capex': 36.738,
    # 期权持有成本 / 季（AI 研发 2.178 + Space 研发 1.076，Q2）; source/as-of: 2026-06-30
    'carry_q': 3.254,
    # 持有季数（2026Q4–2027Q4）; source/as-of: 2026-09-24
    'carry_n': 5.0,
    # 直连月活设备（百万），招股书（汇丰转述）；已在企业与政府收入里; source/as-of: 2026-03-31
    'd2c_users0': 7.4,
    # 第一代直连卫星（千颗），招股书; source/as-of: 2026-03-31
    'd2c_v1_sats': 0.65,
    # L 份数：公司 2026 年底直连用户目标（百万，媒体转述 MWC 2026，`待核`）; source/as-of: 2026-03
    'd2c_users_l': 25.0,
    # M 份数：德银 2030 年直连收入（十亿美元，单家）; source/as-of: 2026-07-29
    'd2c_rev_db': 10.0,
    # 第二代直连卫星首批（千颗）：2027 年中星舰首发后 6 个月内约 1,200 颗（媒体转述，`待核`）; source/as-of: 2026-10-05
    'd2c_sats_first': 1.2,
    # 第二代直连卫星满编（千颗）：向 FCC 申请的上限 15,000 颗（`待核` 申请日）; source/as-of: 2025-09
    'd2c_sats_full': 15.0,
    # 每千颗卫星造价（十亿美元）= 2025 Connectivity 资本开支 41.78 亿 ÷ 2025 发射约 3,100 颗（自身实测，`待核`：第二代直连星更大）; source/as-of: 2025-12-31
    'd2c_sat_cost': 1.35,
    # 频谱总对价 196 亿（股票 111 亿按合同固定价 + 现金 / 代偿债务最多 85 亿）+ 代付 EchoStar 债息约 30 亿; source/as-of: 2026-06-30
    'd2c_spec_cap': 22.6,
    # 频谱未付：代偿债务 85 + 债息 30 − 已付 8.56 + 交割时发行的 2.618 亿股按合同价 111; source/as-of: 2026-06-30
    'd2c_spec_unspent': 21.744,
    # 兑现年 2030（德银年份）折回 FY2027 的年数; source/as-of: 2026-10-05
    'd2c_years': 3.0,
    # 摩根大通 2030 年 Starlink 用户（百万，单家；候选带，A14）; source/as-of: 2026-08-05
    'subs_2030_jpm': 95.0,
    # 候选带过渡年数（2028–2030）; source/as-of: 2026-09-24
    'n_cand': 3.0,
    # 时点对齐年数 = 估值基准日 2026-06-30（10-Q 净现金日）→ Starlink 分子年初 2027-01-01；按 `r_starlink` 折（A17）; source/as-of: 2026-06-30
    'tau': 0.5,
    # Starlink 高回报期止点 = 可见年末（FY2027）；候选带顺延到 2030（A17）; source/as-of: 2026-10-16
    'y1': 2027.0,
    # Starlink 稳态落稳年 = Y1 + 6（进入门槛：高）；候选带 2036（A17）; source/as-of: 2026-10-16
    'y2': 2033.0,
    # Starlink 稳态回报 = 用户定档「有壁垒重资产」15%（成熟卫星运营商穿越周期读数都 < r，不托底；A17）; source/as-of: 2026-10-16
    'rs_steady': 0.15,
    # 手机直连期权高回报期止点 = 本腿可见年末 = 兑现年 2030（德银年份 = 轴 `t_align`）；第二代直连星 2027 年中才随星舰首发、2027 年未规模出货，不继承 Starlink 2027；用户 2026-10-19 认可（A13 ③ / A17）; source/as-of: 2026-10-19
    'y1_d2c': 2030.0,
    # 手机直连期权稳态落稳年 = `y1_d2c` + 6（进入门槛：高——频谱 + 数千颗直连星 + 自有发射，同 Starlink 腿）；用户 2026-10-19 认可（A13 ③ / A17）; source/as-of: 2026-10-19
    'y2_d2c': 2036.0,
}

# FY2025 consolidated EBIT was negative; this triggered the historical
# leverage check despite net cash. The old research treated operating legs
# plus net cash as already unlevered and estimated +100bp floating-rate impact
# on ~$13.4bn of debt at ~$0.13bn/year (10-Q note 9; 2026-06-26 8-K).
HISTORICAL_LEVERAGE = {"year": 2025, "ebit_usd_bn": -2.59,
                       "floating_debt_usd_bn": 13.4, "rate_up_100bp_usd_bn_per_year": 0.13}
# 2026-10-19 original research: Cursor issuance was already included in the
# 13.5728bn base; the 1.331bn performance/market-cap awards were conditional
# and not added to base shares. Full-vesting dilution is disclosure only.
HISTORICAL_SHARE_AWARD = {"base_shares_bn": 13.5728, "award_shares_bn": 1.331}
# The historical 2026-10-19 study says EchoStar had not closed; its 0.2618bn
# shares at the contract's $42.40 plus debt/interest were costed once in the
# direct-to-cell option's 21.744bn unspent spectrum consideration.
HISTORICAL_ECHOSTAR = {"consideration_shares_bn": 0.2618, "contract_price_usd": 42.40}

def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2; n stage-1 years at payout 1 - g1/roe.
    With rs >= roe this equals perpetual_pe / two_stage_pe.  (gordon.py helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def starlink_pe(inp: dict, r: float, g2: float | None = None, roe: float | None = None, t0: int = NUM_YEAR) -> float:
    """Starlink ruler on the steady-return path (A17): forward ROIC to y1, linear to rs_steady by y2."""
    g2 = inp["g2_starlink"] if g2 is None else g2
    roe = inp["roic_starlink"] if roe is None else roe
    return three_segment_pe(t0, int(inp["y1"]), int(inp["y2"]), inp["rs_steady"], g2, roe, r)


def starlink_nopat(inp: dict, t: str) -> tuple[float, float]:
    """FY2027 Connectivity revenue and NOPAT from the subscriber / E&G ladder.

    Subscribers grow by adds_q per quarter from the 6/30 base: two quarters to
    YE2026, four more to YE2027; FY2027 consumer revenue uses the average of
    the two year-ends.  E&G compounds 1.5 years from the Q2 run-rate.
    """
    s26 = inp["subs0"] + 2 * inp[f"adds_q_{t}"]
    s27 = s26 + 4 * inp[f"adds_q_{t}"]
    consumer = (s26 + s27) / 2 * inp[f"arpu_{t}"] * 12 / 1000 + inp[f"hw_{t}"]
    eg = inp["eg0"] * (1 + inp[f"eg_g_{t}"]) ** 1.5
    rev = consumer + eg
    return rev, rev * inp[f"margin_c_{t}"] * (1 - inp["tax"])


def compute_leg(inp: dict, t: str, r7: float) -> tuple[float, float, float]:
    """Signed run-rate value + capacity build value (both USD bn).

    Per-GW unit economics are the company's own: signed M run-rate revenue over
    YE2026 GW, the same opex ratio and straight-line GPU depreciation on its
    own cumulative AI capex.  Each GW beyond YE2026 is worth its NOPAT at 1/r
    minus its own realized capex, received one year out.
    """
    da = inp["ai_capex_cum"] / inp["gpu_life"]

    def nopat(rev: float) -> float:
        return (rev * (1 - inp["opex_pct"]) - da) * (1 - inp["tax"])

    signed = nopat(inp[f"rev_ctr_{t}"]) / r7
    per_gw_value = nopat(inp["rev_ctr_m"]) / inp["gw0"] / r7
    per_gw_capex = inp["ai_capex_cum"] / inp["gw0"]
    build = (inp[f"gw_{t}"] - inp["gw0"]) * (per_gw_value - per_gw_capex) / (1 + r7)
    return signed, build, per_gw_value - per_gw_capex


def d2c_option(inp: dict) -> dict:
    """Direct-to-cell V_opt per tier, USD per share (A13 ③).

    Revenue (USD bn, realisation year) less what the base already carries
    (today's devices x axis L price, grown with the base E&G line for 1.5 years
    and g2 to the realisation year) -> NOPAT at the axis margin.  Capital = the
    spectrum consideration + the tier's satellites at SpaceX's own realised
    per-satellite capex; Gordon on the Starlink ruler with the leg's own
    high-return window y1_d2c / y2_d2c (1/r when ROE < r - 3pp),
    discounted to FY2027, less unspent spectrum consideration (closing Nov 2027,
    not discounted) and satellites (built 2027-28, one year).  Per share on today's
    count (the 261.8M consideration shares are costed at their fixed contract value).
    """
    r, g2, tax = inp["r_starlink"], inp["g2_starlink"], inp["tax"]
    yrs = inp["d2c_years"]
    in_base = (inp["d2c_users0"] * inp["d2c_px_l"] * 12 / 1000
               * (1 + inp["eg_g_m"]) ** 1.5 * (1 + g2) ** yrs)
    per_sat_users = inp["d2c_users0"] / inp["d2c_v1_sats"]  # M devices per thousand sats

    def leg(rev: float, sats: float) -> dict:
        nopat = max(rev - in_base, 0.0) * inp["d2c_margin"] * (1 - tax)
        k = inp["d2c_spec_cap"] + sats * inp["d2c_sat_cost"]
        roe = nopat / k
        # the leg's own high-return window (A13 / A17, user 2026-10-19): Y1 = its visible-year end =
        # realisation year 2030 (gen-2 D2C sats first fly mid-2027), fade 6y like Starlink; the first
        # earning year is NUM_YEAR + yrs (value folded yrs years to 2027-01-01)
        pe = (three_segment_pe(NUM_YEAR + int(yrs), int(inp["y1_d2c"]), int(inp["y2_d2c"]),
                               inp["rs_steady"], g2, roe, r) if roe >= r - 0.03 else 1 / r)
        # folded to FY2027 (t_n 2027-01-01), then the deck's tau to the 2026-06-30 book (A17)
        v = (nopat * pe / (1 + r) ** yrs - inp["d2c_spec_unspent"]
             - sats * inp["d2c_sat_cost"] / (1 + r)) * (1 + r) ** (-inp["tau"])
        return {"rev": rev, "nopat": nopat, "k": k, "roe": roe, "pe": pe, "v": v, "ps": v / inp["shares"]}

    out = {
        "l": leg(inp["d2c_users_l"] * inp["d2c_px_l"] * 12 / 1000, inp["d2c_sats_first"]),
        "m": leg(inp["d2c_rev_db"], inp["d2c_sats_first"]),
        "cap": leg(inp["d2c_sats_full"] * per_sat_users * inp["d2c_px_h"] * 12 / 1000, inp["d2c_sats_full"]),
    }
    out["h"] = max(out["cap"], out["m"], key=lambda d: d["ps"])
    out["in_base"], out["per_sat_users"] = in_base, per_sat_users
    for t in "lmh":
        out[t]["credit"] = max(out[t]["ps"], 0.0)
    return out


def _local_basis_snapshot(axes):
    return {
        'inputs': INPUTS,
        'constants': {'numerator_year': NUM_YEAR, 'tiers': TIERS, 'baskets': BASKETS,
                      'historical_leverage': HISTORICAL_LEVERAGE, 'historical_awards': HISTORICAL_SHARE_AWARD,
                      'historical_echostar': HISTORICAL_ECHOSTAR},
        'shared': {'direct': {'low': axes['direct']['d2c_px_l'], 'middle': axes['direct']['d2c_px_m'],
                              'high': axes['direct']['d2c_px_h'], 'margin': axes['direct']['d2c_margin'],
                              'alignment': axes['direct']['t_align']},
                   'funding': {'scenario_status': axes['funding']['scenario_status'],
                               'uses_shared_haircut': axes['funding']['uses_shared_haircut']}},
    }


# The frontier haircut value is intentionally excluded: SPCX does not use it.
LOCAL_BASIS_BASELINE = '5c9d33595c62e9fcad3da44cee29319c0aec09e395fbd7de0264475ebc6c5423'


def calculate(context):
    inp = dict(INPUTS)
    direct, funding = context["axes"]["direct"], context["axes"]["funding"]
    inp.update({key: direct[key] for key in ("d2c_px_l", "d2c_px_m", "d2c_px_h", "d2c_margin")})
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in inp.values()):
        raise ValueError("inputs must be finite numbers")
    require_whole_years(inp, ("d2c_years", "n_cand", "carry_n", "y1", "y2", "y1_d2c", "y2_d2c"))
    # The older Deutsche Bank direct-to-cell forecast is explicitly FY2030;
    # the shared peer alignment must match, or the dated path needs rebuilding.
    require_axis_alignment(direct, NUM_YEAR + int(inp["d2c_years"]))
    if NUM_YEAR + int(inp["n_cand"]) != 2030:
        raise ValueError("JPM subscriber path is dated FY2030; rebuild it for another horizon")
    if funding["uses_shared_haircut"] is not False:
        raise ValueError("SPCX compute uses one risk basket, not the shared lab haircut")
    if inp["shares"] <= 0 or min(inp["r_starlink"], inp["r_space"], inp["r_compute"]) <= 0:
        raise ValueError("shares and discount rates must be positive")
    review_flags = ["direct_option_customer_target_and_satellite_cost_pending",
                    "direct_option_uses_single_broker_margin_and_demand",
                    "jpm_candidate_single_broker_forecast",
                    "fy2025_historical_negative_ebit_leverage_trigger",
                    "historical_performance_award_conditional_dilution_not_in_base",
                    "historical_echostar_transaction_not_closed_option_cost_included",
                    "ast_margin_proxy_may_overstate_shorter_lived_satellites"]
    if funding["scenario_status"] == "unbuilt":
        review_flags.append("frontier_lab_scenario_ladder_unbuilt")
    for key, basket in BASKETS.items():
        if check_r(inp[key], key, basket):
            review_flags.append("discount_basket_mismatch_" + key)
    if check_g_cap(inp["g2_starlink"], inp["r_starlink"], "g2_starlink"):
        review_flags.append("starlink_growth_above_cap")
    if check_g_cap(inp["g_space"], inp["r_space"], "g_space"):
        review_flags.append("launch_growth_above_cap")
    r4, r4s, r7 = inp["r_starlink"], inp["r_space"], inp["r_compute"]

    sh = inp["shares"]
    # Starlink: steady-return path, value at t_n 2027-01-01 discounted tau years to the 2026-06-30
    # book (A17).  No window add-on: the closure's H2 EBITDA - capex is the growth-funding gap
    # (H2 capex far above operating cash flow), so the window's distributable profit is 0.
    pe_s = starlink_pe(inp, r4)
    df_s = (1 + r4) ** (-inp["tau"])
    pe_sp = perpetual_pe(inp["g_space"], inp["roic_space"], r4s)
    carry = inp["carry_q"] * inp["carry_n"]
    net_cash0 = inp["cash"] + inp["mkt_sec"] - inp["debt"]

    rows = {}
    for t in TIERS:
        rev_s, nopat_s = starlink_nopat(inp, t)
        signed, build, net_gw = compute_leg(inp, t, r7)
        closure = net_cash0 + inp[f"h2_ebitda_{t}"] - inp["h2_interest"] - inp["h2_capex"] - carry
        legs = {
            "starlink": nopat_s * pe_s * df_s,
            "launch": inp[f"space_ebit_{t}"] * (1 - inp["tax"]) * pe_sp,
            "compute": signed + build,
            "closure": closure,
        }
        rows[t] = {"legs": legs, "total": sum(legs.values()) / sh, "rev_s": rev_s, "nopat_s": nopat_s,
                   "signed": signed, "build": build, "net_gw": net_gw}

    L, M, H = (rows[t]["total"] for t in TIERS)
    if not (L < M < H):
        review_flags.append('base_anchors_not_increasing')
    A, B = cut_points(L, M, H)

    # construction §2c: flat-multiple ladder — every leg already carries one
    # multiple across tiers, so the ladder must come from numerators alone.
    ns = [rows[t]["nopat_s"] for t in TIERS]
    if not (ns[0] < ns[1] < ns[2]):
        review_flags.append('starlink_earnings_not_increasing')

    if int(inp["y2_d2c"]) - int(inp["y1_d2c"]) != int(inp["y2"]) - int(inp["y1"]):
        review_flags.append('direct_to_cell_fade_length_mismatch')
    if int(inp["y1_d2c"]) != NUM_YEAR + int(inp["d2c_years"]):
        review_flags.append('direct_to_cell_first_year_mismatch')
    opt = d2c_option(inp)
    v_l, v_m, v_h = (opt[t]["credit"] for t in "lmh")
    if not 0 <= v_l <= v_m <= v_h or v_h <= 0:
        review_flags.append('option_values_not_increasing')
    p_rule = (v_l / v_h, v_m / v_h, 1.0) if v_h > 0 else (0.0, 0.0, 1.0)
    # Candidate band: Starlink transition g1 from JPM 2030 subscribers (single house).
    s27_m = inp["subs0"] + 6 * inp["adds_q_m"]
    g1 = (inp["subs_2030_jpm"] / s27_m) ** (1 / inp["n_cand"]) - 1
    # same path with the visible years extended to 2030 (Y1 = 2027 + n, same fall length), same tau (A17)
    n_c = int(inp["n_cand"])
    y1c = NUM_YEAR + n_c
    pe_c = three_segment_pe(NUM_YEAR, y1c, y1c + int(inp["y2"] - inp["y1"]), inp["rs_steady"],
                            inp["g2_starlink"], inp["roic_starlink"], r4, g1=g1, n=n_c)
    cand = {"l": L}
    for t in ("m", "h"):
        cand[t] = rows[t]["total"] + rows[t]["nopat_s"] * (pe_c - pe_s) * df_s / sh
    Lc, Mc, Hc = cand["l"], cand["m"], cand["h"]
    if not (Lc < Mc < Hc):
        review_flags.append('candidate_anchors_not_increasing')

    # Old growth comparisons change only the Starlink ruler; other legs and
    # cash bridge remain at the historical underlying inputs.
    sensitivity = {}
    for g, label in ((inp["g2_starlink"] - 0.01, "growth_minus_1pp"),
                     (inp["g2_starlink"] + 0.01, "growth_plus_1pp")):
        delta = (starlink_pe(inp, r4, g2=g) - pe_s) * df_s / sh
        sensitivity[label] = {t.upper(): rows[t]["total"] + rows[t]["nopat_s"] * delta for t in TIERS}
    option_anchors = {t.upper(): rows[t]["total"] + opt[t]["credit"] for t in TIERS}
    segments = {name: {"unit": "USD_PER_SHARE",
                       "values": {t.upper(): rows[t]["legs"][name] / sh for t in TIERS}}
                for name in ("starlink", "launch", "compute", "closure")}
    return {
        "ticker": "SPCX.US", "currency": "USD", "valuation_as_of": None, "framework_as_of": None,
        "historical_valuation_as_of": "2026-06-30", "historical_framework_as_of": "2026-10-19",
        "basis_changed": None, "partial_basis_changed": local_basis_changed(_local_basis_snapshot(context['axes']), LOCAL_BASIS_BASELINE), "units": {"price": "USD_PER_SHARE"},
        "anchors": {t.upper(): rows[t]["total"] for t in TIERS},
        "candidate": {"label": "Starlink 2030 用户·摩根大通单家", "anchors": {t.upper(): cand[t] for t in TIERS},
                      "status": "requires_reconciliation"},
        "option": {"value": v_h, "value_unit": "USD_PER_SHARE", "weights": dict(zip(("L", "M", "H"), p_rule)),
                   "anchors": option_anchors, "status": "requires_reconciliation"},
        "segments": segments,
        "key_parameters": {
            "starlink": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r4)},
                         "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["g2_starlink"])},
                         "forward_return": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["roic_starlink"])},
                         "steady_return": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), min(inp["roic_starlink"], inp["rs_steady"]))}},
            "launch": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r4s)},
                       "growth_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), inp["g_space"])}},
            "compute": {"discount_rate": {"unit": "RATIO", "values": dict.fromkeys(("L", "M", "H"), r7)}}},
        "diagnostics": {"starlink_multiple": pe_s, "launch_multiple": pe_sp,
                        "starlink_nopat_usd_bn": {t.upper(): rows[t]["nopat_s"] for t in TIERS},
                        "compute_signed_usd_bn": {t.upper(): rows[t]["signed"] for t in TIERS},
                        "compute_build_usd_bn": {t.upper(): rows[t]["build"] for t in TIERS},
                        "option_tiers": {t.upper(): opt[t] for t in TIERS},
                        "option_capacity_comparison": opt["cap"],
                        "candidate_transition_growth": g1, "candidate_multiple": pe_c,
                        "historical_leverage": HISTORICAL_LEVERAGE,
                        "historical_share_award": {
                            "as_of": "2026-10-19", **HISTORICAL_SHARE_AWARD,
                            "full_vesting_dilution": conditional_award_dilution(
                                HISTORICAL_SHARE_AWARD["base_shares_bn"], HISTORICAL_SHARE_AWARD["award_shares_bn"]),
                            "included_in_base_shares": False, "vesting_status": "unknown"},
                        "historical_echostar_transaction": {
                            "as_of": "2026-10-19", **HISTORICAL_ECHOSTAR,
                            "status": "not_closed_at_historical_date", "option_cost_includes_consideration": True,
                            "base_closure_includes_consideration": False},
                        "direct_margin_reference": {
                            "value": inp["d2c_margin"], "unit": "RATIO", "source": "AST_SELL_SIDE_2030",
                            "spacex_satellite_lifetime_years_range": [3, 5],
                            "shorter_lifetime_may_overstate_margin": True}},
        "sensitivity": sensitivity, "review_flags": review_flags,
    }
