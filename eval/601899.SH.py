from __future__ import annotations

import math

from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'partial_basis'),
                'axes': {'gold_copper': 'fed_path_gold_copper', 'lithium': 'lithium_carbonate'},
                'peers': {'luoyang': '603993.SH'}}


# Shared market inputs are supplied by the gold-copper and lithium axes.
HISTORICAL_PARTIAL_FINGERPRINT = 'e895be97922d7d2b3fec77e7b79ca2f975dcf70c689b793327bceaa51f4b8f80'

INPUTS = {
    'shares': 27314000000.0,  # 稀释股本；总股本 26,590,714,622 × 基本/稀释 EPS（1.473/1.434），见 A8；2026-06-30
    'bps': 7.537,  # 每股净资产 CNY；归母净资产 205,867,063,890 ÷ shares（稀释口径；总股本 BPS=7.742）；2026-06-30
    'equity': 205867063890.0,  # 归母净资产 CNY；中报；每档前瞻 \(ROE_x = NP^{parent}_x / equity\)，三腿共用（属性 G / A11）；2026-06-30
    'r_perp': 0.1,  # 金铜银腿篮子 r：**篮 4 龙头制造 10%**（A26；真源 `eval/lib/gordon.py BASKET_R`）——金铜簇固定 g 反解隐含 r 10.0%；备选篮 5 11%（国别附加）只作披露行；2026-09-20
    'r_li': 0.13,  # 锂腿篮子 r：**篮 6 周期商品 / 小盘 13%**（A26；锂价函数、g 0）；2026-09-20
    'r_rest': 0.13,  # 其余块（锌 / 钼钨硫 / 铁 / 冶炼 / 贸易 / 抵销）篮子 r：**篮 6 周期商品 / 小盘 13%**（A26；冶炼贸易若单列归篮 5 见敏感性）；2026-09-20
    'g2_aucu': 0.025,  # 金铜银腿永续 g2 = §13 商品腿 tier 默认：通胀 **2.5%** + 金铜长期实际价格漂移 ≈ 0（USD 口径；1990–2025 实测 2.6%、卖方矿业终值 g 2–3%；银 2% 漂移权重 3.6% 并入）；金铜簇 25 家同业反解 2.76% 只作印证（A21）；cap = min(6%, `r_perp` − 4%) = 6%；2026-09-20
    'g2_li': 0.0,  # 锂腿永续 g2 = §13 商品腿 tier 默认：锂长期实际价格漂移 ≤ −3%/yr → **0**，不取负；锂簇 4 家反解 2.35% 只作印证（A21）；2026-09-20
    'g2_rest': 0.0,  # 其余块永续 g2 = 0（§13 商品腿 g 0；无簇无轴、三档冻结）；2026-09-20
    'pe_own_min': 7.4,  # own-year PE 实测下沿（2022–25，A7 ①）；**护栏**，不入公式（A23）；2026-09
    'pe_own_max': 17.2,  # own-year PE 实测上沿（2022–25，A7 ①）；**护栏**，不入公式（A23）；2026-09
    'fx_usd_cny': 6.8645,  # USD→CNY，2026H1 平均；与 `603993.SH` `fx_usd_cny` 同值；即期 6.7108（2026-09-04）。三档不变，利率路径对汇率的影响见「敏感性」；2026H1
    'realization_au': 0.9718,  # 金实现率，2026H1 实测，**全档统一**（A16）；2026H1
    'realization_cu': 0.9405,  # 铜实现率，2026H1 实测，**全档统一**（A16）；2026H1
    'vol_au_g': 88360000.0,  # 年化并表矿产金销量（克）=（金锭 27,424 + 金精矿 16,756 千克）× 2；**已售口径，非矿产量 46,702 千克**（A1/属性 C）；2026H1
    'cost_au': 291.11,  # 矿产金加权单位销售成本 元/克 =（27,424×347.30 + 16,756×199.15）÷ 44,180；2026H1
    'vol_cu_t': 919592.0,  # 年化并表矿产铜销量（吨）=（铜精矿 353,831 + 电积铜 46,845 + 电解铜 59,120）× 2；**不含卡莫阿权益 54,375 吨/半年**（合营权益法，进 `inv_income`）；2026H1
    'cost_cu': 27522.0,  # 矿产铜加权单位销售成本 元/吨 =（353,831×24,480 + 46,845×36,620 + 59,120×38,513）÷ 459,796；2026H1
    'vol_ag_g': 450464000.0,  # 年化并表矿产银销量（克）= 225,232 千克 × 2；银腿挂金价梯（A4）；2026H1
    'price_ag_m': 13.952,  # M 档实现银价 元/克 = 单位毛利 11.672（26.29 亿 ÷ 225,232 千克）+ 单位成本 2.28；L/H 按 `lme_au` 比例缩放；2026H1
    'cost_ag': 2.28,  # 银单位销售成本 元/克（A4）；2026H1
    'realization_li': 0.602727,  # 锂实现率 = 2026H1 混合 ASP 90,409 ÷ 旧轴 M 150,000（≈H1 平台）；轴 M 改 12.0 万后 M 档实现价 = 90,409 × 12.0/15（A19）；2026H1
    'vol_li_t': 88000.0,  # **当期**锂销量（吨 LCE）= 2026H1 实际 4.4 万吨 × 2；两段式的起点年（A19）；2026-06-30
    'vol_cu_2028_t': 1333597.0,  # 2028 规划矿产铜中位 155 万吨 × 并表已售换算 0.860（剔卡莫阿权益、库存；A1 / 属性 C）；临 2026-012
    'jl3_cu_t': 600000.0,  # 巨龙铜矿三期达产后年矿产铜（吨，全矿）；公司具名规划（若获批，矿石 ~2 亿吨/年）；**\(V_{opt}\) 输入，不入主公式**（A34）；2026-01-24
    'jl2_cu_t': 325000.0,  # 巨龙二期达产年矿产铜（吨）= 30–35 万吨中值；已在 2028 规划分子内，期权份数从此起数（A34）；2026-01-24
    'nci_julong': 0.4184,  # 巨龙少数股东比例（`nci_share` 行所列 41.84%）；期权增量归母口径（A34）；2026H1
    't_num': 2026.0,  # 分子起点年 = 2026H1 年化当期量（两段式 E1）；\(V_{opt}\) 折现终点；2026-10-03
    't_opt': 2030.0,  # 巨龙三期兑现年 = 对齐年份 2028（规划年）+ 2，**无时点锚·拍值**（三期未获批、无投产日）（A34）；2026-10-03
    'jl2_capex': 17460000000.0,  # **参照**·巨龙二期（改扩建）总投资 174.6 亿（元）；2026 中报「重大的非股权投资」表（本期 16.69 / 累计 147.26 亿）；**不是三期预算，不入 \(V_{opt}\)**，只算未投资本参照（A34）；2026-06-30
    'jl2_ore_add': 60000000.0,  # **参照**·二期新增采选矿石量（吨/年）= 1.05 亿 − 0.45 亿（藏格 2026-005 公告）；2026-01-24
    'jl3_ore_add': 95000000.0,  # **参照**·三期新增采选矿石量（吨/年）= 约 2 亿 − 1.05 亿（藏格 2026-005 公告；三期若获批）；2026-01-24
    'vol_li_2028_t': 300000.0,  # 2028 规划碳酸锂当量中位（27–32 万吨）；公司单源，用户裁定进底牌（A19）；临 2026-012
    'ach_l_au': 0.777778,  # L 档兑现率 = 2026 指引 105 吨 ÷ 2028 规划 135 吨（增长停在 2026 指引，属性 H）；临 2026-012
    'ach_l_cu': 0.774194,  # L 档兑现率 = 120 ÷ 155 万吨；临 2026-012
    'ach_l_ag': 0.875657,  # L 档兑现率 = 1 ÷ 1.142（银量停在 2026）；推导
    'ach_l_li': 0.4,  # L 档兑现率 = 2026 指引 12 万吨 ÷ 30 万吨；临 2026-012
    'ach_m_au': 0.89,  # M 档兑现率 = 2026H1 年化产量 93.4 吨 ÷ 2026 指引 105 吨（实测时序兑现，每期财报重钉）；2026 中报
    'ach_m_cu': 0.89,  # M 档兑现率 = 2026H1 年化 106.9 万吨 ÷ 指引 120 万吨；2026 中报
    'ach_m_ag': 1.0,  # M 档银兑现率（银随铜矿伴生，H1 年化 450 吨已达 2025 水平）；2026 中报
    'ach_m_li': 0.73,  # M 档兑现率 = 2026H1 年化 8.8 万吨 ÷ 指引 12 万吨；2026 中报
    'cost_li': 33770.5,  # 锂单位销售成本 元/吨 = H1（收入 39.78 亿 − 毛利占比 3.4%×732.97）÷ 4.4 万吨；三档冻结；2026H1
    'gp_rest': 20776000000.0,  # 年化「其余块」毛利（锌/钼钨硫/铁/冶炼/贸易/内部抵销，**已剔锂**）= 旧 257.60 − 锂 H1 年化毛利 49.84；**三档不变**（A4）；分腿权重 = `gp_rest` ÷ 该档毛利合计；2026H1
    'rev_other_mine': 12975000000.0,  # 年化其他矿产品收入（税金及附加基数，**已剔锂**）=（锌 30.15 + 银 31.42 + 铁 3.30）× 2；锂收入走 `vol_li × price_li`（当期 / FY28 各自的量）；2026H1
    'levy_rate': 0.063842,  # 税金及附加 ÷ 矿产品收入 = 59.86 ÷ 937.69；2026H1
    'opex_fixed': 15977000000.0,  # 年化期间费用等（销售+管理+财务+研发+减值+营业外净）；由利润总额恒等式倒算，见 A5；**扣除 `opex_fin` 后的部分按量指数放大**（A28）；2026H1
    'opex_fin': 1300000000.0,  # 其中财务费用（年化 6.50 亿 × 2），三档固定；净债下降的省息不计（偏保守，A28）；2026H1
    'inv_income': 8334300000.0,  # 年化投资收益 + 公允价值变动 =（25.93 + 15.74 亿）× 2；含卡莫阿权益法收益（当前处淹井减产低点）；2026H1
    'tax_rate': 0.21542,  # 有效税率 = 136.77 ÷ 634.89；2026H1
    'nci_share': 0.245,  # 少数股东占净利润比，**当期与 FY28 两端同基 24.5%**（2026H1 实测 21.366%；增量资产落在巨龙 41.84% / 紫金黄金国际 15% / 赤峰 74.15% 等高 NCI 平台，A6）；2026-09-21
    'payout_actual': 0.35,  # 实际派息率（2026–28 分红比例 35%，公司公告）；**不进倍数**，只算「模型视同派出、实际留存的现金/股」（A11）；FY2025
    'n_transition': 2.0,  # 两段式过渡年数：2026H1 年化 → FY28（A7）；—
    'k_l': 0.0,  # **L** 「视同派出现金」打折 k（A32）；来源 ①：谷底价格下已完成交易的回报均 ≥ r；L 档增长关掉、留存最多但对价最便宜，取 0；2026-09-21
    'k_m': 0.0,  # **M** 打折 k：原 0.10（藏格矿业已完成参股回报 7.0% < r）乘在多留部分上，按 valuation-rules「经营价值与超额现金」④ 去掉（A32）；2026-10-16
    'k_h': 0.0,  # **H** 打折 k：原 0.22（1 − M/H）乘在多留部分上，按 valuation-rules「经营价值与超额现金」④ 去掉（A32）；2026-10-16
    'growth_capex_26_28': 60000000000.0,  # 2026–28 增长性资本开支（亿→元）：3 × FY2025 在建工程本年增加 205.4 亿；具名剩余预算合计约 560 亿（A29）；ROIC 门分母；AR2025 附注五.19
    'net_debt': 53687786729.0,  # 净债务（有息负债 − 现金）；只作「今日净现金/股」交叉备注，不进锚点（A11）；2026-06-30
    'pb_floor': 2.0,  # 资产地板倍数；2022–25 实测 PB 谷底 2.03/2.31/2.05/2.07（A9）；**只披露不 max()**——L = 盈利情景，地板 15.07 由 eval 打印；2026-09
    'gold_plan_2028_g': 135000000,  # 2028 gold production midpoint, company plan 2026-012.
    'gold_reference_production_g': 93400000,  # annualised 2026H1 mine production, matching 88.36t sales.
    'silver_growth_assumption': .142,  # plan-based annual growth proxy, company plan 2026-012.
}
FORMULA_ID = "zijin_fed_li_dual_axis_fwd2028_two_stage_v2"
MIN_R_MINUS_G = 0.02
TOL = 0.05
YI = 1e8
OZ_TO_G = 31.1035
TIERS = ("l", "m", "h")

LEGS = {
    "metal": ("r_perp", "g2_aucu"),
    "li": ("r_li", "g2_li"),
    "rest": ("r_rest", "g2_rest"),
}
BASKET4_LEGS = {"metal"}
ALT_METAL_BASKET_R = 0.11  # 备选篮 5 (country premium), disclosure only

SHARED_LADDER = {
    "lme_cu_l": "p_cu_l", "lme_cu_m": "p_cu_m", "lme_cu_h": "p_cu_h",
    "lme_au_l": "lme_au_l", "lme_au_m": "lme_au_m", "lme_au_h": "lme_au_h",
}

# 1H2026×2 parent at the filing NCI (21.366%) — the M-tier current run-rate,
# restated at the forward NCI, must reproduce this bridge (M guard).
H1_2026_X2_PARENT = 39_169_807_243 * 2
H1_NCI = 0.21366
IDENTITY_TOL = 0.01
M_PRICE_REF = {"p_au": ("price_au_m", 1006.5), "p_cu": ("price_cu_m", 84466.0)}
M_PRICE_TOL = 0.005
LI_REV_H1 = (28.80 + 10.98) * 1e8
LI_GP_H1 = 732.97e8 * 0.034
LI_VOL_H1 = 4.4e4
LI_ASP_H1 = LI_REV_H1 / LI_VOL_H1
LI_COST_H1 = (LI_REV_H1 - LI_GP_H1) / LI_VOL_H1

REQUIRED = [
    "jl3_cu_t", "jl2_cu_t", "nci_julong", "t_num", "t_opt",
    "jl2_capex", "jl2_ore_add", "jl3_ore_add",
    "shares", "bps", "fx_usd_cny", "realization_au", "realization_cu",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_g", "cost_au",
    "lme_cu_l", "lme_cu_m", "lme_cu_h", "vol_cu_t", "cost_cu",
    "vol_ag_g", "price_ag_m", "cost_ag",
    "li2co3_l", "li2co3_m", "li2co3_h", "realization_li", "vol_li_t", "cost_li",
    "vol_au_2028_g", "vol_cu_2028_t", "vol_ag_2028_g", "vol_li_2028_t",
    "ach_l_au", "ach_l_cu", "ach_l_ag", "ach_l_li", "ach_m_au", "ach_m_cu", "ach_m_ag", "ach_m_li",
    "gp_rest", "rev_other_mine", "levy_rate", "opex_fixed", "opex_fin", "inv_income",
    "tax_rate", "nci_share", "payout_actual", "n_transition", "growth_capex_26_28", "net_debt",
    "k_l", "k_m", "k_h",
    "equity", "r_perp", "r_li", "r_rest",
    "axis_g2_aucu", "axis_g2_li", "g2_aucu", "g2_li", "g2_rest",
    "pe_own_min", "pe_own_max", "pb_floor",
]

def prices(inp: dict[str, float], tag: str) -> tuple[float, float, float, float]:
    p_au = inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]
    p_cu = inp[f"lme_cu_{tag}"] * inp["fx_usd_cny"] * inp["realization_cu"]
    p_ag = inp["price_ag_m"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    p_li = inp[f"li2co3_{tag}"] * inp["realization_li"]
    return p_au, p_cu, p_ag, p_li


def volumes(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    if not forward:
        return {"au": inp["vol_au_g"], "cu": inp["vol_cu_t"], "ag": inp["vol_ag_g"], "li": inp["vol_li_t"]}
    ach = {k: (inp[f"ach_{tag}_{k}"] if tag != "h" else 1.0) for k in ("au", "cu", "ag", "li")}
    return {
        "au": inp["vol_au_2028_g"] * ach["au"], "cu": inp["vol_cu_2028_t"] * ach["cu"],
        "ag": inp["vol_ag_2028_g"] * ach["ag"], "li": inp["vol_li_2028_t"] * ach["li"],
    }


def mine_rev_at_m(inp: dict[str, float], v: dict[str, float]) -> float:
    """Mine revenue at M-tier prices — the price-neutral volume index base (A28)."""
    p_au, p_cu, _, p_li = prices(inp, "m")
    return v["au"] * p_au + v["cu"] * p_cu + inp["rev_other_mine"] + v["li"] * p_li


def scenario(inp: dict[str, float], tag: str, forward: bool) -> dict[str, float]:
    p_au, p_cu, p_ag, p_li = prices(inp, tag)
    v = volumes(inp, tag, forward)
    gp_au = v["au"] * (p_au - inp["cost_au"])
    gp_cu = v["cu"] * (p_cu - inp["cost_cu"])
    gp_ag = v["ag"] * (p_ag - inp["cost_ag"])
    gp_li = v["li"] * (p_li - inp["cost_li"])
    gp = gp_au + gp_cu + gp_ag + inp["gp_rest"] + gp_li
    mine_rev = v["au"] * p_au + v["cu"] * p_cu + inp["rev_other_mine"] + v["li"] * p_li
    vidx = mine_rev_at_m(inp, v) / mine_rev_at_m(inp, volumes(inp, tag, False)) if forward else 1.0
    opex = (inp["opex_fixed"] - inp["opex_fin"]) * vidx + inp["opex_fin"]
    pretax = gp - mine_rev * inp["levy_rate"] - opex + inp["inv_income"]
    parent = pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])
    return {
        "v": v, "p_au": p_au, "p_cu": p_cu, "p_ag": p_ag, "p_li": p_li,
        "gp_au": gp_au, "gp_cu": gp_cu, "gp_ag": gp_ag, "gp_li": gp_li, "gp": gp,
        "vidx": vidx, "parent": parent, "eps": parent / inp["shares"],
        "w_metal": (gp_au + gp_cu + gp_ag) / gp, "w_li": gp_li / gp, "w_rest": inp["gp_rest"] / gp,
    }


def leg_eps(s: dict[str, float]) -> dict[str, float]:
    return {"metal": s["eps"] * s["w_metal"], "li": s["eps"] * s["w_li"], "rest": s["eps"] * s["w_rest"]}


def tier(inp: dict[str, float], tag: str, r_over: dict[str, float] | None = None) -> dict:
    """Forward two-stage tier: g1 per leg, ROIC gate, ROE28 on B27, anchor."""
    cur, fwd = scenario(inp, tag, False), scenario(inp, tag, True)
    lc, l28 = leg_eps(cur), leg_eps(fwd)
    n = int(inp["n_transition"])
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["parent"] - cur["parent"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"]
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    g1 = g1_raw if gate else {k: (g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"]     # 2026H2 + FY27 → B27
    cum_win = cum_roll + fwd["parent"]                                          # window earnings for the cash row
    roe = fwd["parent"] / inp["equity"]
    for _ in range(60):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["parent"] / b27
        if abs(roe_new - roe) < 1e-10:
            break
        roe = roe_new
    r = {k: (r_over or {}).get(r_key, inp[r_key]) for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    anchor_pre_k = sum(contrib.values())
    # The stage-1 payout treated the retention beyond b1 as distributed at face
    # value.  k is the probability-weighted shortfall of reinvesting that cash
    # below r (valuation-rules 留存去向审计「打折 k」); it only ever subtracts.
    cash_ps = max((1 - inp["payout_actual"]) - b1, 0.0) * cum_win / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash_ps
    anchor = anchor_pre_k - haircut
    return {
        "cur": cur, "fwd": fwd, "legs_cur": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co,
        "roic": roic, "gate": gate, "b1": b1, "b27": b27, "roe28": roe, "pe": pe,
        "p1": {k: 1 - g1[k] / roe for k in LEGS}, "contrib": contrib, "anchor": anchor,
        "eq_pe": anchor_pre_k / cur["eps"],
        "cash_ps": cash_ps, "haircut": haircut, "anchor_pre_k": anchor_pre_k,
        "issue": b1 > (1 - inp["payout_actual"]),
    }


def li_passby_h(inp: dict[str, float], th: dict) -> dict[str, float]:
    """A19 H pass-by (_AXIS.lithium-carbonate「H 档是路过」, 2026-10-19 framework correction).

    The lithium axis H rung lasts one year, then the M rung; only the lithium
    leg moves (metal / rest keep their H world, H ROE28, H gate).  The price
    gap is a pure margin item: ΔE = volume × (p_li,H − p_li,M) × (1 − levy) ×
    (1 − t)(1 − NCI) ÷ shares, exact under the bridge (opex index is priced at
    M).  Mix world = H volumes at the M price: leg EPS lc − ΔE_cur → FY28
    l28 − ΔE28, own g1, two_stage_pe at the H ROE28 and r_li.  The one H-price
    year (E1 = current run-rate) adds ΔE_cur ÷ (1 + r_li), fully paid out —
    the windfall needs no reinvestment (growth capital is volume-driven)."""
    _, _, _, p_h = prices(inp, "h")
    _, _, _, p_m = prices(inp, "m")
    f = (1 - inp["levy_rate"]) * (1 - inp["tax_rate"]) * (1 - inp["nci_share"]) / inp["shares"]
    d_cur = inp["vol_li_t"] * (p_h - p_m) * f
    d_28 = th["fwd"]["v"]["li"] * (p_h - p_m) * f
    lc = th["legs_cur"]["li"] - d_cur
    l28 = leg_eps(th["fwd"])["li"] - d_28
    n = int(inp["n_transition"])
    g1 = (l28 / lc) ** (1.0 / n) - 1.0 if th["gate"] else 0.0
    pe = two_stage_pe(g1, n, inp["g2_li"], th["roe28"], inp["r_li"])
    value = lc * pe + d_cur / (1 + inp["r_li"])
    return {"d_cur": d_cur, "d_28": d_28, "lc": lc, "l28": l28, "g1": g1, "pe": pe,
            "value": value, "persist": th["contrib"]["li"]}


def apply_passby(inp: dict[str, float], th: dict) -> dict:
    """Rewrite the H tier's lithium contribution and anchor with the pass-by value."""
    pb = li_passby_h(inp, th)
    th = dict(th)
    th["contrib"] = dict(th["contrib"], li=pb["value"])
    th["anchor_persist"] = th["anchor"]
    th["anchor_pre_k"] = sum(th["contrib"].values())
    th["anchor"] = th["anchor_pre_k"] - th["haircut"]
    th["eq_pe"] = th["anchor_pre_k"] / th["cur"]["eps"]
    th["passby"] = pb
    return th


# 表3 only — never Inputs, never the base band (A2e-7a).  p_M: no anchor (phase 3 unapproved).
P_K = (0.0, 0.25, 1.0)


def julong3_option(inp: dict[str, float], th: dict) -> dict[str, float]:
    """V_opt — Julong phase 3 (A34, valuation-rules「未建模期权」2026-10-03).

    Size: the named post-phase-3 copper run-rate minus the phase-2 run-rate (the
    2028 plan already holds phase 2).  Unit economics: this ticker's own copper
    leg at the M rung (2026H1 realisation and unit cost, levy), own tax, Julong's
    own NCI.  Ruler: own metal-leg steady-state Gordon at the H-tier ROE28 lifted
    by the increment; valued in the realisation year, discounted to the numerator
    year at the basket r.  No peer multiple."""
    _, p_cu, _, _ = prices(inp, "m")
    d_cu = inp["jl3_cu_t"] - inp["jl2_cu_t"]
    pretax = d_cu * (p_cu - inp["cost_cu"]) - d_cu * p_cu * inp["levy_rate"]
    d_parent = pretax * (1 - inp["tax_rate"]) * (1 - inp["nci_julong"])
    d_eps = d_parent / inp["shares"]
    roe_post = (th["fwd"]["parent"] + d_parent) / th["b27"]
    pe_post = perpetual_pe(inp["g2_aucu"], roe_post, inp["r_perp"])
    disc = (1 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    # Unspent capital (valuation-rules「未建模期权」2026-10-04): the phase-3 budget
    # is undisclosed (待补), so V_opt carries no deduction yet and reads high.
    # Reference only — phase-2 capex per tonne of added ore throughput scaled to
    # phase 3's added throughput, equity share, one lump in t_opt (optimistic).
    k_ref = inp["jl2_capex"] / inp["jl2_ore_add"] * inp["jl3_ore_add"]
    k_ref_ps = k_ref * (1 - inp["nci_julong"]) / inp["shares"] * disc
    v_opt = d_eps * pe_post * disc
    return {"d_cu": d_cu, "d_parent": d_parent, "d_eps": d_eps, "roe_post": roe_post,
            "pe_post": pe_post, "disc": disc, "v_opt": v_opt,
            "k_ref": k_ref, "k_ref_ps": k_ref_ps, "v_opt_ref": v_opt - k_ref_ps}


def _historical_calculation(raw, peer):
    derived = {'vol_au_2028_g','vol_ag_2028_g'}
    required = [k for k in REQUIRED if k not in derived] + ['gold_plan_2028_g','gold_reference_production_g','silver_growth_assumption']
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f'missing inputs {missing}')
    if any(not math.isfinite(raw[k]) for k in required):
        raise ValueError('all required inputs must be finite')
    for key in ('t_num','t_opt','n_transition'):
        if isinstance(raw[key],bool) or not float(raw[key]).is_integer():
            raise ValueError(f'{key} must be a whole year')
    if raw['gold_reference_production_g'] <= 0 or raw['gold_plan_2028_g'] <= 0:
        raise ValueError('gold production and company plan must be positive')
    # The old research derived 2028 gold sold volume from the 135t plan and
    # 2026H1 sales/production ratio, and silver from 14.2% annual plan growth.
    # Historical numbers were recorded to the nearest hundred grams.
    inp = {**raw, 'vol_au_2028_g': round(raw['gold_plan_2028_g']*raw['vol_au_g']/raw['gold_reference_production_g'],-2),
                 'vol_ag_2028_g': round(raw['vol_ag_g']*(1+raw['silver_growth_assumption'])**raw['n_transition'],-2)}
    baskets = {'r_perp':4, 'r_li':6, 'r_rest':6}

    errors: list[str] = []
    warnings: list[str] = []
    for metal, keys in (("gold", ("lme_au_l", "lme_au_m", "lme_au_h")), ("copper", ("lme_cu_l", "lme_cu_m", "lme_cu_h")),
                        ("li2co3", ("li2co3_l", "li2co3_m", "li2co3_h"))):
        lo, mid, hi = (inp[k] for k in keys)
        if not (lo < mid < hi):
            errors.append(f"{metal} ladder violated: {lo}/{mid}/{hi}")
    for k in ("au", "cu", "ag", "li"):
        if not (0 < inp[f"ach_l_{k}"] <= inp[f"ach_m_{k}"] <= 1.0):
            errors.append(f"achievement ladder {k}: L {inp[f'ach_l_{k}']} ≤ M {inp[f'ach_m_{k}']} ≤ H 1 violated")
    for leg, (r_key, g_key) in LEGS.items():
        if r_key not in baskets:
            errors.append(f"{r_key}: no 篮 N in its Inputs source cell (A26)")
        errors += check_r(inp[r_key], r_key, baskets.get(r_key))
        errors += check_g_cap(inp[g_key], inp[r_key], g_key)
        if inp[r_key] - inp[g_key] < MIN_R_MINUS_G:
            errors.append(f"{leg}: r − g < {MIN_R_MINUS_G} (pole)")
    errors += check_g_cap(inp["axis_g2_aucu"], inp["r_perp"], "axis_g2_aucu")
    errors += check_g_cap(inp["axis_g2_li"], inp["r_li"], "axis_g2_li")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")
    if abs(inp["cost_li"] - LI_COST_H1) / LI_COST_H1 > 0.01:
        warnings.append('historical_lithium_cost_mismatch')
    if not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2:
        errors.append("payout_actual ∉ (0,1) or n_transition ≠ 2")
    # cyclical: the top-of-cycle tier's cash is the most likely to be spent on
    # expensive deals, so k must not fall as the tier rises.
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    if errors:
        raise ValueError('; '.join(errors))

    # Both companies use the same gold-copper axis. A missing peer snapshot
    # cannot suppress the independently calculated historical base price.
    peer_status = 'peer_comparison_unavailable'
    if isinstance(peer, dict):
        operating = peer.get('operating')
        shared = operating.get('shared_prices', {}) if isinstance(operating, dict) else {}
        if isinstance(shared, dict):
            values = [(inp[ours], shared.get(other)) for ours, other in SHARED_LADDER.items()]
            def valid(value):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return False
                try:
                    return math.isfinite(value)
                except OverflowError:
                    return False
            if any(valid(value) and abs(ours - value) > 1e-6 for ours, value in values):
                peer_status = 'peer_comparison_differs'
            elif all(valid(value) for _, value in values):
                peer_status = 'peer_comparison_matched'

    T = {t: tier(inp, t) for t in TIERS}
    T["h"] = apply_passby(inp, T["h"])
    cur_m = T["m"]["cur"]
    if cur_m["p_au"] <= inp["cost_au"] or T["l"]["cur"]["p_cu"] <= inp["cost_cu"] or T["l"]["cur"]["p_li"] <= inp["cost_li"]:
        warnings.append('historical_price_below_unit_cost')
    for key, (label, ref) in M_PRICE_REF.items():
        if abs(cur_m[key] / ref - 1.0) > M_PRICE_TOL:
            warnings.append('historical_realized_price_mismatch')
    li_m_ref = LI_ASP_H1 * inp["li2co3_m"] / 150_000
    if abs(cur_m["p_li"] / li_m_ref - 1.0) > M_PRICE_TOL:
        warnings.append('historical_lithium_price_mismatch')
    # M guard: the current run-rate at the filing NCI = H1×2 − old-li + li at axis M.
    def li_parent(asp: float, vol: float) -> float:
        pbt = (asp - inp["cost_li"]) * vol - inp["levy_rate"] * asp * vol
        return pbt * (1.0 - inp["tax_rate"]) * (1.0 - H1_NCI)
    expected = H1_2026_X2_PARENT - li_parent(LI_ASP_H1, LI_VOL_H1 * 2) + li_parent(cur_m["p_li"], inp["vol_li_t"])
    current_share = 1 - inp['nci_share']
    got = (cur_m['parent'] * (1 - H1_NCI) / current_share) if current_share else None
    if (not expected or not math.isfinite(expected) or got is None or not math.isfinite(got)
            or abs(got / expected - 1.0) > IDENTITY_TOL):
        warnings.append('historical_financial_bridge_mismatch')
    if errors:
        raise ValueError('; '.join(errors))

    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        raise ValueError(f"L<M<H violated: {L}, {M}, {H}")
    for t in TIERS:
        for label, pe in ((f"metal PE_{t.upper()}", T[t]["pe"]["metal"]), (f"equivalent PE_{t.upper()}", T[t]["eq_pe"])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(f"guardrail: {label}={pe:.2f} outside own band — BLOCKED, do not twist g")
        if T[t]["issue"]:
            errors.append(f"{t.upper()}: b1 {T[t]['b1']:.2%} > actual retention {1 - inp['payout_actual']:.0%} (发股融资)")
        # recombination: Σ leg EPS_cur × (1+g1_raw)^n must reproduce E28
        recomb = sum(T[t]["legs_cur"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off by {recomb / T[t]['fwd']['eps'] - 1:+.2%}")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["metal"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    floor = inp["pb_floor"] * inp["bps"]
    A, B = (L + M) / 2, (M + H) / 2
    alt_t = {t: tier(inp, t, r_over={"r_perp": ALT_METAL_BASKET_R}) for t in TIERS}
    alt_t["h"] = apply_passby(inp, alt_t["h"])
    alt = [alt_t[t]["anchor"] for t in TIERS]
    net_cash_ps = -inp["net_debt"] / inp["shares"]

    opt = None
    if (inp['jl3_cu_t'] > inp['jl2_cu_t'] and inp['t_opt'] >= inp['t_num']
            and inp['jl2_ore_add'] > 0):
        try:
            opt = julong3_option(inp, T['h'])
        except (ValueError, ZeroDivisionError, OverflowError):
            # The optional project's domain can fail independently of the base.
            pass
    if opt is not None and any(not math.isfinite(value) for value in opt.values()):
        opt = None
    option_available = opt is not None and math.isfinite(opt['v_opt']) and opt['v_opt'] >= 0
    if not option_available:
        warnings.append('julong_option_unavailable')
    # Legacy economic guard findings remain visible; they do not erase the
    # user's authorised historical valuation during this migration.
    legacy_guard_flag = bool(errors)
    tiers = lambda xs: dict(zip('LMH',xs))
    option = {'status': 'unavailable', 'label': '巨龙三期未扣投资', 'anchors': None}
    if option_available:
        band3 = tuple(base + P_K[i] * opt['v_opt'] for i, base in enumerate((L, M, H)))
        option = {'label': '巨龙三期未扣投资', 'value': opt['v_opt'], 'value_unit': 'CNY_PER_SHARE',
                  'weights': tiers(P_K), 'anchors': tiers(band3)}
    segments = {leg: {'unit': 'CNY_PER_SHARE', 'values': tiers(T[t]['contrib'][leg] for t in TIERS)}
                for leg in LEGS}
    segments['haircut'] = {'unit': 'CNY_PER_SHARE', 'values': tiers(-T[t]['haircut'] for t in TIERS)}
    params = {}
    for leg,(r_key,g_key) in LEGS.items():
        params[leg] = {'discount_rate': {'unit': 'RATIO', 'values': tiers(inp[r_key] for _ in TIERS)},
                       'growth_rate': {'unit': 'RATIO', 'values': tiers(inp[g_key] for _ in TIERS)},
                       'transition_growth':tiers(T[t]['passby']['g1'] if leg=='li' and t=='h' else T[t]['g1'][leg] for t in TIERS),
                       'transition_years':inp['n_transition'],
                       'forward_return': {'unit': 'RATIO', 'values': tiers(T[t]['roe28'] for t in TIERS)},
                       'steady_return': {'unit': 'RATIO', 'values': tiers(T[t]['roe28'] if inp[g_key]>0 else None for t in TIERS)},
                       'multiple':tiers(T[t]['passby']['pe'] if leg=='li' and t=='h' else T[t]['pe'][leg] for t in TIERS)}
    return {'ticker':'601899.SH', 'currency':'CNY', 'valuation_as_of':None, 'framework_as_of':None,
            'anchors':tiers((L,M,H)), 'candidate':None,
            'option':option,
            'review_flags': ([peer_status, 'julong_phase3_budget_unverified'] + sorted(set(warnings)) +
                             (['historical_financial_guards_require_review'] if legacy_guard_flag else [])),
            'segments':segments, 'key_parameters':params,
            'operating':{'roic':tiers(T[t]['roic'] for t in TIERS), 'growth_gate':tiers(T[t]['gate'] for t in TIERS),
                         'roe':tiers(T[t]['roe28'] for t in TIERS), 'gold_2028_volume':inp['vol_au_2028_g'],
                         'silver_2028_volume':inp['vol_ag_2028_g'], 'lithium_passby':T['h']['passby'],
                         'julong_option':opt, 'basket5_cross':tiers(alt), 'flat':tiers(flat),
                         'shared_prices':{k:inp[k] for k in SHARED_LADDER}},
    }


def calculate(context):
    gold = context['axes']['gold_copper']['stock_fields']
    lithium = context['axes']['lithium']
    selected_li = {key: lithium[key] for key in ('axis_g2_li', 'li2co3_l', 'li2co3_m', 'li2co3_h')}
    combined = {**INPUTS, **gold, **selected_li}
    result = _historical_calculation(combined, context.get('peers', {}).get('luoyang'))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['historical_framework_as_of'] = '2026-10-20'
    result['basis_changed'] = None
    model_constants = {'option_weights': P_K, 'gold_unit_grams': OZ_TO_G, 'unit_scale': YI,
                       'legs': LEGS, 'basket4_legs': sorted(BASKET4_LEGS),
                       'alternative_metal_rate': ALT_METAL_BASKET_R}
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'gold_copper': gold, 'lithium': selected_li,
         'model_constants': model_constants}, HISTORICAL_PARTIAL_FINGERPRINT)
    return result
