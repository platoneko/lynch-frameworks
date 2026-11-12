from __future__ import annotations

import math

from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe
from lib.inputs import check_missing
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis'),
                'axes': {'gold_copper': 'fed_path_gold_copper'},
                'peers': {'zijin': '601899.SH'}}


# Shared prices are injected from the gold-copper axis.
HISTORICAL_PARTIAL_FINGERPRINT = 'e47b7beb5292f4e632bb37a0fdabfdc9ba8756b1259819fa7a36678807cf4147'

INPUTS = {
    'shares': 21394310176.0,  # 总股本 21,394,310,176 股；中报；2026-06-30
    'equity': 899.63,  # 归母权益 亿 CNY；中报（A17）；每档前瞻 \(ROE_x = NP_x / equity\)；2026-06-30
    'r_perp': 0.1,  # 铜金腿篮子 r：篮 4 龙头制造（金铜簇隐含 r 10.0%、辉立 WACC 10.23%，A26）；备选篮 5 11%（国别附加只披露）；其它腿 r 见下三行（分腿加总，A24）；`check_r(r, 篮 4)`；2026-09-18
    'r_co': 0.13,  # 钴（刚果配额）腿篮子 r：篮 6 周期商品 / 小盘（配额 + 价格十倍级摆动，峰形商品，A26）；`check_r(r, 篮 6)`；2026-09-18
    'r_other': 0.13,  # 钼钨铌磷腿篮子 r：篮 6 周期商品 / 小盘（A26）；`check_r(r, 篮 6)`；2026-09-18
    'r_ixm': 0.11,  # IXM 贸易腿篮子 r：篮 5 大行 / 优质股份行（薄利费率型，利润率稳、量随价，A26）；`check_r(r, 篮 5)`；2026-09-18
    'g2_aucu': 0.025,  # 铜金腿永续 g2；来源层级 = §13 商品腿 tier 默认——金铜实际价格漂移 ≈ 0 + 通胀 **2.5%**（USD 口径；卖方矿业终值 g 2–3%）；金铜簇 25 家同业反解 2.76% 只作印证（A22）；cap = min(6%, 10% − 4%) = 6%；2026-09-18
    'g2_co': 0.0,  # 钴腿永续 g2 = 0（§13 其他商品腿 g 0；配额量增走 `gp_co_*` 三档，A22）；2026-09-18
    'g2_other': 0.0,  # 钼钨铌磷腿永续 g2 = 0（§13 商品腿 g 0，A22）；2026-09-18
    'g2_ixm': 0.0,  # IXM 贸易腿永续 g2 = 0（费率型，量随价不给永续增长，A22）；2026-09-18
    'pe_own_min': 9.85,  # 自身近 5 年 TTM PE 实测低点；**护栏**，不入公式（A25）；2026-09-05
    'pe_own_max': 51.48,  # 自身近 5 年 TTM PE 实测高点；**护栏**，不入公式（A25）；2026-09-05
    'fx_usd_cny': 6.8645,  # USD→CNY，2026H1 平均（与基线同期，见 A12）；即期 6.7190；2026H1
    'vol_cu': 752328.0,  # 铜年化销量（吨）= 中报销量 376,164 × 2；见 A4；2026H1
    'p_cu_base': 13083.97,  # 基线 LME 铜均价（美元/吨），公司中报披露的 2026H1 均价；2026H1
    'vol_au_oz': 200800.0,  # 金年化销量（盎司）= 巴西四矿 2026H1 产 100,400 oz × 2；见 A20；2026H1
    'cost_au_oz': 17689.0,  # 金单位成本 元/oz = 金营业成本 17.76 亿 ÷ 100,400 oz；2026H1
    'price_au_m_oz': 30050.0,  # M 档实现金价 元/oz = 金收入 30.17 亿 ÷ 100,400 oz；L/H 按 `lme_au` 比例缩放（对 LME 的实现率 0.933）；2026H1
    'realization_cu': 0.962494,  # 实现率 = 86,446 ÷ (13,083.97 × 6.8645)；见 A15，**衍生值**；2026H1
    'royalty_cu': 0.035,  # 刚果金铜矿业权利金，计入「税金及附加」故只作用于价差；见 A13；2018 矿业法
    'cogs_cu': 32091.0,  # TFM/KFM 铜单位营业成本 元/吨（含折旧，不含权利金）= 铜营业成本 120.71 亿 ÷ 销量 376,164 t（A13）；前瞻口径铜腿 = 销量 ×（单位收入 − 本值），基量下与 `gp_cu_base` 恒等；2026H1
    'gp_cu_base': 408.9316,  # 铜腿年化毛利 = (325.180 − 120.714) × 2；2026H1
    'gp_co_l': 30.0,  # L 档钴腿年化毛利 = FY2024 实际（87.43 − 57.43）；见 A5；FY2024
    'gp_co_m': 34.2954,  # M 档 = 2026 前三季度钴毛利 25.7216 亿（收入 34.7823 − 成本 9.0608）× 4/3；2026-10-25 由 2026H1 年化 52.52 重钉（A5）；2026-09-30
    'gp_co_h1': 52.5232,  # 2026H1 钴毛利 26.2616 × 2；**只供 §3 校验步骤 1 基线闭合**，不进锚点；2026H1
    'gp_co_h': 60.0,  # H 档 = 销量 3 万吨（贴近公司 2026 配额 3.12 万吨，二手来源`待核`）× 单位毛利 20 万元/吨（≈ 前三季度实测 20.3 万）；2026-10-25 由 90（2.5 万吨 × 36 万元/吨）下调；**本框架最弱单点**，见 A5；2026-09-30
    'gp_other': 104.9945,  # 钼+钨+铌+磷 年化毛利 =（64.9046 − 金 12.4073）× 2；**已剔除金腿**（金单列并挂金价梯，A20）；三档不变，见 A8；2026H1
    'gp_ixm': 59.7434,  # IXM 两条贸易线年化毛利 = 29.8717 × 2；三档不变，见 A2；2026H1
    'gp_misc': -28.2903,  # 其他业务 + 内部交易抵销 年化 = −14.1452 × 2；2026H1
    'opex': 108.6211,  # 毛利→利润总额的净额（税金及附加 + 期间费用 − 其他收益/投资收益等）年化 = 54.3105 × 2；当期冻结，FY28 = 固定部分 + `opex_vol` × 量指数 + 增量权利金（A27）；2026H1
    'opex_vol': 39.81,  # 其中随量放大的部分 = 销售 0.425 + 管理 15.68 + 研发 3.80（亿，H1）× 2；财务费用 16.99 × 2（含汇兑损失 10.49）与税金及附加基数固定；2026H1
    'tax_rate': 0.282227,  # 实际税率 = 72.55 ÷ 257.05；见 A7；2026H1
    'mi_rate': 0.1326,  # 少数股东占净利 = 2026 前三季度 36.72 ÷ 276.91；作用于基量利润；2026-10-25 由 2026H1 12.46% 重钉（A6）；2026-09-30
    'mi_rate_h1': 0.124552,  # 2026H1 少数股东占净利 = 22.98 ÷ 184.50；**只供 §3 校验步骤 1 基线闭合**，不进锚点；2026H1
    'mi_kfm': 0.2875,  # KFM 二期增量利润的少数股东比例（CMOC 持 KFM 71.25%）；只作用于 FY28 铜增量（A6）；中报附注
    'vol_cu_2028': 862952.0,  # FY28 铜销量（吨）=（2026 指引中值 79 万吨 + KFM 二期 10 万吨）× 已售比 0.970（2026H1 销量 ÷ 产量年化）；A4；2026 中报 / KFM2 公告
    'vol_au_2029_oz': 643015.0,  # 公司具名目标：巴西金 2029 年 >20 吨（= 643,015 oz）；超出 FY28 路径的部分走 \(V_{opt}\)（A33）；**不入主公式**；2026 中报
    't_num': 2026.0,  # 分子起点年 = 2026H1 年化当期量（两段式 E1）；\(V_{opt}\) 折现终点；2026-10-03
    't_opt': 2029.0,  # 金目标兑现年 = 公司目标年 2029（A33）；**\(V_{opt}\) 输入**；2026 中报
    'odin_k': 116.6965,  # **期权**·奥丁（厄瓜多尔 Cangrejos，全资）未投资本 = 采矿协议投资承诺 >17 亿$ × `fx_usd_cny` 6.8645 − 已投 0（中报在建工程重要项目表无奥丁行、仍在前期设计；2026-04 预付权利金 0.34 亿$ 未计）；收购对价 30 亿已付 2025-06，沉没不扣（A33）；2026-06-30
    'masa_k': 1.8057,  # **期权**·巴西 Aurizona 地下矿（MASA）未投资本 = 预算 4.0359 亿 ×（1 − 投入占预算 55.26%）（A33）；2026-06-30
    'fbdm_k': 0.313,  # **期权**·巴西 Fazenda 地下矿井扩建（FBDM）未投资本 = 预算 0.5006 亿 ×（1 − 37.48%）（A33）；2026-06-30
    'au_cc_k': 2.7,  # **期权**·巴西四矿或有对价未付 = 期末公允价值 270,004 千元（上限 1.15 亿$；交割满一年按首年售金量结算）；首付 62.31 亿已付、沉没不扣（A33）；2026-06-30
    'ach_l_cu': 0.88764,  # L 档铜兑现率 = 增长停在 2026 指引 79 万吨 ÷ 89 万吨；推导
    'ach_l_au': 0.405157,  # L 档金兑现率 = 当期 200,800 ÷ 495,610（金无增长）；推导
    'ach_m_cu': 1.0,  # M 档铜兑现率 = min(2026 前三季度年化产量 79.56 万吨 ÷ 指引中值 79 万吨 = 1.007, 1)；每期财报重钉（2026H1 为 0.98）；2026-09-30
    'ach_m_au': 0.9,  # M 档金兑现率；**假设值**——公司有 2026 当年指引 6–8 吨（cmoc.com 2026-01-15），前三季度 16.09 万盎司跟踪指引中值，但当年指引不覆盖 2028 路径；按铜同口径会是约 0.98，取严保留 0.90，随 2027 指引重钉（A9）；假设
    'payout_actual': 0.37,  # 实际派息率 = FY23 40% / FY24 40% / FY25 30% 三年均值；不进倍数，只算「模型视同派出、实际留存的现金/股」（A24）；Longbridge 分红
    'k_l': 0.0,  # **L** 「视同派出现金」打折 k（A31）；来源 ①：2026H1 巴西四金矿 59 亿对价，年化约 20 万盎司，L 档金价下税前回报仍远高于 r 10% → 0；FY2021–25 现金收购≈0；2026-09-21
    'k_m': 0.0,  # **M** 打折 k（A31）；来源 ① 同上 → 0；2026-09-21
    'k_h': 0.0,  # **H** 打折 k：原 0.25（1 − M/H）乘在多留部分上，按 valuation-rules「经营价值与超额现金」④ 去掉（A31）；2026-10-16
    'n_transition': 2.0,  # 两段式过渡年数：2026H1 年化 → FY28；—
    'growth_capex_26_28': 60.0,  # 2026–28 增长性资本开支（亿）：KFM 二期剩余 (10.84 − 6.86) 亿$ ≈ 28 亿 + 金矿扩建假设 30 亿（`待补`）；ROIC 门分母，区间 40–100（A28）；**2026-10-25 标注偏低**：前三季度购建长期资产现金 80.96 亿、在建工程 40.54 → 104.93 亿（三季报：铜钴业务在建项目增加），含 N'zilo 2 水电站等非产能项，待年报拆分；翻倍到 120 亿门的结果不变；2026 中报 / KFM2 公告 / 2026 三季报
    'capex_kfm2': 76.96,  # KFM 二期总投资 10.84 亿$ × 7.1（董事会 2025-10-24 批准）；单项目回报分母；SMM 2025-10
    'net_debt': 15461104767.0,  # 净债务 元 = 有息负债 605.19 亿（短期借款 466.43 + 一年内到期非流动负债 22.31 + 长期借款 2.96 + 应付债券 15.00 + 其他流动负债 98.49，后者主要是 2026 年发行的 H 股可转债）− 货币资金 450.58 亿；不含交易性金融资产 226.12 亿（若计入为净现金 71.5 亿）；只作每股净现金 / 净负债交叉备注（A24）；2026-06-30 旧值 −128.9 亿（净现金）；2026-09-30
}
FORMULA_ID = "cmoc_fed_path_fwd2028_two_stage_v3"
MIN_R_MINUS_G = 0.02
TOL = 0.05
YI = 1e8
TIERS = ("l", "m", "h")

LEGS = {"铜金": ("r_perp", "g2_aucu"), "钴": ("r_co", "g2_co"), "钼钨铌磷": ("r_other", "g2_other"), "IXM": ("r_ixm", "g2_ixm")}
BASKET4_LEGS = {"铜金"}
SHARED_LADDER = {"p_cu_l": "lme_cu_l", "p_cu_m": "lme_cu_m", "p_cu_h": "lme_cu_h",
                 "lme_au_l": "lme_au_l", "lme_au_m": "lme_au_m", "lme_au_h": "lme_au_h"}
BASE_NP_PARENT_YI = 323.0437
BASE_NP_TOL_YI = 0.5

REQUIRED = [
    "vol_au_2029_oz", "t_num", "t_opt", "odin_k", "masa_k", "fbdm_k", "au_cc_k",
    "shares", "fx_usd_cny", "vol_cu", "p_cu_base", "p_cu_l", "p_cu_m", "p_cu_h",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_oz", "cost_au_oz", "price_au_m_oz",
    "realization_cu", "royalty_cu", "cogs_cu", "gp_cu_base", "gp_co_l", "gp_co_m", "gp_co_h",
    "gp_co_h1", "mi_rate_h1",
    "gp_other", "gp_ixm", "gp_misc", "opex", "opex_vol", "tax_rate", "mi_rate", "mi_kfm",
    "vol_cu_2028", "vol_au_2028_oz", "ach_l_cu", "ach_l_au", "ach_m_cu", "ach_m_au",
    "payout_actual", "n_transition", "growth_capex_26_28", "capex_kfm2", "net_debt",
    "k_l", "k_m", "k_h",
    "equity", "r_perp", "r_co", "r_other", "r_ixm", "g2_aucu", "g2_co", "g2_other", "g2_ixm",
    "axis_g2_aucu", "pe_own_min", "pe_own_max",
]
def unit_rev_cu(inp: dict[str, float], tag: str) -> float:
    return inp[f"p_cu_{tag}"] * inp["realization_cu"] * inp["fx_usd_cny"]


def year(inp: dict[str, float], tag: str, v_cu: float, v_au: float, forward: bool) -> dict[str, float]:
    """One tier-year P&L (亿 CNY).  forward=False is the audited-base run-rate."""
    gp_cu = v_cu * (unit_rev_cu(inp, tag) - inp["cogs_cu"]) / YI
    p_au = inp["price_au_m_oz"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    gp_au = v_au * (p_au - inp["cost_au_oz"]) / YI
    gp_co = inp[f"gp_co_{tag}"]
    gp = gp_cu + gp_au + gp_co + inp["gp_other"] + inp["gp_ixm"] + inp["gp_misc"]
    # base royalty sits inside opex; the framework applies (1 − royalty) to the price move only (A13)
    roy_price = inp["royalty_cu"] * inp["vol_cu"] * (unit_rev_cu(inp, tag) - unit_rev_cu(inp, "m")) / YI
    if forward:
        base_rev = inp["vol_cu"] * unit_rev_cu(inp, "m") + inp["vol_au_oz"] * inp["price_au_m_oz"]
        vidx = (v_cu * unit_rev_cu(inp, "m") + v_au * inp["price_au_m_oz"]) / base_rev
        roy_vol = inp["royalty_cu"] * (v_cu - inp["vol_cu"]) * unit_rev_cu(inp, tag) / YI
        opex = (inp["opex"] - inp["opex_vol"]) + inp["opex_vol"] * vidx + roy_price + roy_vol
        pretax_kfm = max((v_cu - inp["vol_cu"]) * (unit_rev_cu(inp, tag) * (1 - inp["royalty_cu"]) - inp["cogs_cu"]) / YI, 0.0)
    else:
        vidx, opex, pretax_kfm = 1.0, inp["opex"] + roy_price, 0.0
    pretax = gp - opex
    np_ = ((pretax - pretax_kfm) * (1 - inp["mi_rate"]) + pretax_kfm * (1 - inp["mi_kfm"])) * (1 - inp["tax_rate"])
    legs = {"铜金": gp_cu + gp_au, "钴": gp_co, "钼钨铌磷": inp["gp_other"] + inp["gp_misc"], "IXM": inp["gp_ixm"]}
    return {"np": np_, "eps": np_ * YI / inp["shares"], "gp": gp, "gp_cu": gp_cu, "gp_au": gp_au, "p_au": p_au,
            "pretax": pretax, "vidx": vidx, "w": {k: legs[k] / gp for k in legs}}


def tier(inp: dict[str, float], tag: str, r_over: dict[str, float] | None = None) -> dict:
    ach = {"cu": 1.0, "au": 1.0} if tag == "h" else {"cu": inp[f"ach_{tag}_cu"], "au": inp[f"ach_{tag}_au"]}
    v_cu, v_au = inp["vol_cu_2028"] * ach["cu"], inp["vol_au_2028_oz"] * ach["au"]
    cur, fwd = year(inp, tag, inp["vol_cu"], inp["vol_au_oz"], False), year(inp, tag, v_cu, v_au, True)
    lc = {k: cur["eps"] * cur["w"][k] for k in LEGS}
    l28 = {k: fwd["eps"] * fwd["w"][k] for k in LEGS}
    n = int(inp["n_transition"])
    g1_raw = {k: (l28[k] / lc[k]) ** (1.0 / n) - 1.0 for k in LEGS}
    g1_co = (fwd["eps"] / cur["eps"]) ** (1.0 / n) - 1.0
    roic = (fwd["np"] - cur["np"]) / inp["growth_capex_26_28"]
    gate = roic >= inp["r_perp"]
    g2 = {k: inp[g_key] for k, (_, g_key) in LEGS.items()}
    g1 = g1_raw if gate else {k: (g2[k] if k in BASKET4_LEGS else 0.0) for k in LEGS}
    w = {k: lc[k] / cur["eps"] for k in LEGS}
    g1_roll = g1_co if gate else sum(w[k] * g1[k] for k in LEGS)
    cum_roll = (cur["eps"] / 2 + cur["eps"] * (1 + g1_co)) * inp["shares"] / YI
    cum_win = cum_roll + fwd["np"]
    roe = fwd["np"] / inp["equity"]
    for _ in range(60):
        b1 = max(g1_roll / roe, 0.0)
        b27 = inp["equity"] + b1 * cum_roll
        roe_new = fwd["np"] / b27
        if abs(roe_new - roe) < 1e-10:
            break
        roe = roe_new
    r = {k: (r_over or {}).get(r_key, inp[r_key]) for k, (r_key, _) in LEGS.items()}
    pe = {k: two_stage_pe(g1[k], n, g2[k], roe, r[k]) for k in LEGS}
    contrib = {k: lc[k] * pe[k] for k in LEGS}
    anchor_pre_k = sum(contrib.values())
    # Retention beyond b1 was treated as distributed at face value; k is the
    # probability-weighted shortfall of reinvesting it below r (valuation-rules
    # 留存去向审计「打折 k」) and only ever subtracts.
    cash_ps = max((1 - inp["payout_actual"]) - b1, 0.0) * cum_win * YI / inp["shares"]
    haircut = inp[f"k_{tag}"] * cash_ps
    anchor = anchor_pre_k - haircut
    return {"cur": cur, "fwd": fwd, "v_cu": v_cu, "v_au": v_au, "legs_cur": lc, "g1": g1, "g1_raw": g1_raw, "g1_co": g1_co,
            "roic": roic, "gate": gate, "b1": b1, "b27": b27, "roe28": roe, "pe": pe, "p1": {k: 1 - g1[k] / roe for k in LEGS},
            "contrib": contrib, "anchor": anchor, "eq_pe": anchor_pre_k / cur["eps"],
            "cash_ps": cash_ps, "haircut": haircut, "anchor_pre_k": anchor_pre_k,
            "issue": b1 > (1 - inp["payout_actual"])}


# 表3 only — never Inputs, never the base band (A2e-7a).  p_M: no anchor (judgement).
P_K = (0.0, 0.25, 1.0)
# Unspent capital behind the >20 t gold target (亿 CNY, 100% equity, A33):
# Odin build budget, Brazil growth CIP remainders, unpaid Brazil contingent consideration.
GOLD_K_KEYS = ("odin_k", "masa_k", "fbdm_k", "au_cc_k")


def gold_target_option(inp: dict[str, float], th: dict) -> dict[str, float]:
    """V_opt — the part of the company's named 2029 gold target (>20 t) beyond the
    FY28 path already in the numerator (A33, valuation-rules「未建模期权」2026-10-03).
    Unit economics: this ticker's own gold leg at the M rung (2026H1 unit price
    and cost), own NCI and tax; ruler: own copper-gold leg steady-state Gordon at
    the H-tier ROE28 lifted by the increment; valued in 2029, discounted to the
    numerator year at the basket r.  No peer multiple.
    Unspent capital (valuation-rules 2026-10-04): the pool still to be spent on the
    whole target (Odin build + Brazil growth CIP + unpaid contingent consideration;
    paid consideration is sunk) is shared pro rata by ounces between the FY28 path
    (funded by b1 retention inside the anchor) and this increment; the increment's
    share is deducted once in 2029 (lump at realisation, optimistic on timing)."""
    d_oz = inp["vol_au_2029_oz"] - inp["vol_au_2028_oz"]
    d_np = d_oz * (inp["price_au_m_oz"] - inp["cost_au_oz"]) / YI * (1 - inp["mi_rate"]) * (1 - inp["tax_rate"])
    d_eps = d_np * YI / inp["shares"]
    roe_post = (th["fwd"]["np"] + d_np) / th["b27"]
    pe_post = perpetual_pe(inp["g2_aucu"], roe_post, inp["r_perp"])
    disc = (1 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    k_pool = sum(inp[k] for k in GOLD_K_KEYS)
    k_share = d_oz / (inp["vol_au_2029_oz"] - inp["vol_au_oz"])
    k_opt = k_pool * k_share
    v_gross = d_np * pe_post
    return {"d_oz": d_oz, "d_np": d_np, "d_eps": d_eps, "roe_post": roe_post, "pe_post": pe_post,
            "disc": disc, "k_pool": k_pool, "k_share": k_share, "k_opt": k_opt, "v_gross": v_gross,
            "v_pre_k": v_gross * disc * YI / inp["shares"],
            "v_full_k": (v_gross - k_pool) * disc * YI / inp["shares"],
            "v_opt": (v_gross - k_opt) * disc * YI / inp["shares"]}


def evaluate(inp, peer):
    required = [key for key in REQUIRED if key != 'vol_au_2028_oz']
    errors = check_missing(inp, required)
    warnings = []
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[k]) for k in required):
        raise ValueError('all required inputs must be finite')
    for key in ('t_num', 't_opt', 'n_transition'):
        if isinstance(inp[key], bool) or not float(inp[key]).is_integer():
            raise ValueError(f'{key} must be a whole year')
    if inp['t_opt'] <= inp['t_num'] or not 0 < inp['n_transition'] < inp['t_opt'] - inp['t_num']:
        raise ValueError('gold target year must be later than the end of the transition')
    # No annual guidance was available: the original 2028 volume is the
    # elapsed-time interpolation from 2026 volume to the 2029 target. Derive
    # it from those inputs to prevent target and assumed path drifting apart.
    inp = {**inp, 'vol_au_2028_oz': inp['vol_au_oz'] + (inp['vol_au_2029_oz'] - inp['vol_au_oz'])
                 * inp['n_transition'] / (inp['t_opt'] - inp['t_num'])}
    r = {leg: inp[rrow] for leg, (rrow, _) in LEGS.items()}
    g = {leg: inp[grow] for leg, (_, grow) in LEGS.items()}
    baskets = {'r_perp': 4, 'r_co': 6, 'r_other': 6, 'r_ixm': 5}
    for leg, (rrow, _) in LEGS.items():
        if rrow not in baskets:
            errors.append(f"{rrow}: Inputs source cell names no 篮 N")
        errors += check_r(r[leg], rrow, baskets.get(rrow))
    if errors:
        raise ValueError('; '.join(errors))
    if not (inp["p_cu_l"] < inp["p_cu_m"] < inp["p_cu_h"]) or not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]):
        errors.append("price ladder order violated")
    if not (inp["gp_co_l"] < inp["gp_co_m"] < inp["gp_co_h"]):
        errors.append("cobalt leg order violated")
    if inp["price_au_m_oz"] <= inp["cost_au_oz"]:
        warnings.append('historical_gold_unit_cost_above_price')
    for k in ("cu", "au"):
        if not (0 < inp[f"ach_l_{k}"] <= inp[f"ach_m_{k}"] <= 1.0):
            errors.append(f"achievement ladder {k} violated")
    for leg, (_, grow) in LEGS.items():
        errors += check_g_cap(g[leg], r[leg], grow)
        if g[leg] < 0:
            errors.append(f"{grow} < 0")
    errors += check_g_cap(inp["axis_g2_aucu"], r["铜金"], "axis_g2_aucu")
    if r["铜金"] - g["铜金"] < MIN_R_MINUS_G:
        errors.append("r_perp − g2_aucu below pole margin")
    if inp["equity"] <= 0 or not (0 < inp["payout_actual"] < 1) or inp["n_transition"] != 2:
        errors.append("equity / payout_actual / n_transition invalid")
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append(f"haircut ladder k_L ≤ k_M ≤ k_H within [0,1] violated: {inp['k_l']}/{inp['k_m']}/{inp['k_h']}")
    if abs(inp["p_cu_m"] - inp["p_cu_base"]) > 1e-6:
        warnings.append('copper_axis_differs_from_historical_base')
    for k in inp:
        if k.startswith("p_") and k not in ("p_cu_base", "p_cu_l", "p_cu_m", "p_cu_h"):
            errors.append(f"probability-style input {k}")
    if errors:
        raise ValueError('; '.join(errors))
    # Both companies use the same gold-copper source; missing peer snapshots
    # cannot erase this company's independently calculated historical band.
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
    # M guard: base-volume M run-rate reproduces the audited interim ×2, and the
    # volume × (unit revenue − unit COGS) copper leg reproduces gp_cu_base.  The
    # cobalt M rung and the base NCI rate are re-pinned to 9M data (2026-10-25),
    # so the closure runs on their 2026H1 values (gp_co_h1 / mi_rate_h1).
    base_m = year({**inp, "gp_co_m": inp["gp_co_h1"], "mi_rate": inp["mi_rate_h1"]}, "m", inp["vol_cu"], inp["vol_au_oz"], False)
    if abs(base_m["np"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        warnings.append('historical_parent_profit_bridge_mismatch')
    if abs(base_m["gp_cu"] - inp["gp_cu_base"]) > 0.5:
        warnings.append('historical_copper_profit_bridge_mismatch')
    L, M, H = (T[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")
    if errors:
        raise ValueError('; '.join(errors))
    for t in TIERS:
        for label, pe in ((f"铜金 PE_{t.upper()}", T[t]["pe"]["铜金"]), (f"equivalent PE_{t.upper()}", T[t]["eq_pe"])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(f"guardrail: {label}={pe:.2f} outside own band — BLOCKED")
        if T[t]["issue"]:
            errors.append(f"{t.upper()}: b1 > actual retention (发股融资)")
        recomb = sum(T[t]["legs_cur"][k] * (1 + T[t]["g1_raw"][k]) ** inp["n_transition"] for k in LEGS)
        if abs(recomb / T[t]["fwd"]["eps"] - 1) > 0.005:
            errors.append(f"{t.upper()}: per-leg g1 recombination off")
    flat = [T[t]["cur"]["eps"] * T["m"]["pe"]["铜金"] for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append("flat-multiple ladder broken")
    A, B = (L + M) / 2, (M + H) / 2
    alt = [tier(inp, t, r_over={"r_perp": 0.11})["anchor"] for t in TIERS]
    kfm2_ret = None
    if inp['capex_kfm2'] > 0:
        kfm2_ret = {t: max((100_000 * (unit_rev_cu(inp, t) * (1 - inp['royalty_cu']) - inp['cogs_cu']) / YI)
                          * (1 - inp['tax_rate']), 0) / inp['capex_kfm2'] for t in TIERS}
        if any(not math.isfinite(value) for value in kfm2_ret.values()):
            kfm2_ret = None
    if kfm2_ret is None:
        warnings.append('kfm2_reference_return_unavailable')
    net_cash_ps = -inp["net_debt"] / inp["shares"]
    # Invalid project assumptions affect the optional project, not the base.
    opt = None
    target_gap = inp['vol_au_2029_oz'] - inp['vol_au_oz']
    if (target_gap > 0 and inp['vol_au_2029_oz'] > inp['vol_au_2028_oz']
            and inp['t_opt'] >= inp['t_num'] and all(inp[k] >= 0 for k in GOLD_K_KEYS)):
        try:
            opt = gold_target_option(inp, T['h'])
        except (ValueError, ZeroDivisionError, OverflowError):
            pass
    if opt is not None and any(not math.isfinite(value) for value in opt.values()):
        opt = None
    available = (opt is not None and math.isfinite(opt['v_opt']) and opt['v_opt'] >= 0
                 and 0 < opt['k_share'] <= 1)
    if not available:
        warnings.append('gold_target_option_unavailable')
    legacy_guard_flag = bool(errors)
    tiers = lambda xs: dict(zip('LMH', xs))
    option = {'status': 'unavailable', 'label': '巴西黄金目标', 'anchors': None}
    if available:
        band3 = tuple(base + P_K[i] * opt['v_opt'] for i, base in enumerate((L, M, H)))
        option = {'label': '巴西黄金目标', 'value': opt['v_opt'], 'value_unit': 'CNY_PER_SHARE',
                  'weights': tiers(P_K), 'anchors': tiers(band3)}
    names = {'铜金':'copper_gold', '钴':'cobalt', '钼钨铌磷':'other_mining', 'IXM':'ixm'}
    segments = {slug: {'unit': 'CNY_PER_SHARE', 'values': tiers(T[t]['contrib'][label] for t in TIERS)}
                for label, slug in names.items()}
    segments['haircut'] = {'unit': 'CNY_PER_SHARE', 'values': tiers(-T[t]['haircut'] for t in TIERS)}
    parameters = {}
    for label, slug in names.items():
        r_key, g_key = LEGS[label]
        parameters[slug] = {'discount_rate': {'unit': 'RATIO', 'values': tiers(inp[r_key] for _ in TIERS)},
                            'growth_rate': {'unit': 'RATIO', 'values': tiers(inp[g_key] for _ in TIERS)},
                            'transition_growth': tiers(T[t]['g1'][label] for t in TIERS),
                            'transition_years': inp['n_transition'],
                            'forward_return': {'unit': 'RATIO', 'values': tiers(T[t]['roe28'] for t in TIERS)},
                            'steady_return': {'unit': 'RATIO', 'values': tiers(T[t]['roe28'] if inp[g_key] > 0 else None for t in TIERS)},
                            'multiple': tiers(T[t]['pe'][label] for t in TIERS)}
    return {
        'ticker':'603993.SH', 'currency':'CNY', 'valuation_as_of':None, 'framework_as_of':None,
        'anchors':tiers((L,M,H)), 'candidate':None,
        'option':option,
        'review_flags': [peer_status, *sorted(set(warnings))] + (['historical_financial_guards_require_review'] if legacy_guard_flag else []),
        'segments':segments, 'key_parameters':parameters,
        'operating':{'roe':tiers(T[t]['roe28'] for t in TIERS), 'roic':tiers(T[t]['roic'] for t in TIERS),
                     'growth_gate':tiers(T[t]['gate'] for t in TIERS),
                     'profit_current':tiers(T[t]['cur']['np'] for t in TIERS),
                     'profit_forward':tiers(T[t]['fwd']['np'] for t in TIERS),
                     'haircut':tiers(T[t]['haircut'] for t in TIERS),
                     'gold_option':opt, 'basket_5_cross':tiers(alt), 'flat':tiers(flat),
                     'kfm2_reference_return': None if kfm2_ret is None else tiers(kfm2_ret[t] for t in TIERS),
                     'shared_prices':{k:inp[k] for k in SHARED_LADDER}},
        'currency_inputs': {'usd_cny': inp['fx_usd_cny']},
    }


def calculate(context):
    gold = context['axes']['gold_copper']['stock_fields']
    result = evaluate({**INPUTS, **gold}, context.get('peers', {}).get('zijin'))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['historical_framework_as_of'] = '2026-10-25'
    result['basis_changed'] = None
    model_constants = {'option_weights': P_K, 'unit_scale': YI, 'legs': LEGS,
                       'tiers': TIERS, 'gold_project_cost_keys': GOLD_K_KEYS,
                       'historical_parent_profit': BASE_NP_PARENT_YI,
                       'historical_parent_tolerance': BASE_NP_TOL_YI}
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'gold_copper': gold, 'model_constants': model_constants},
        HISTORICAL_PARTIAL_FINGERPRINT)
    return result
