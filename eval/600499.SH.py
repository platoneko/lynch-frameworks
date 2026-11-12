from __future__ import annotations

import math

from lib.gordon import basket_r, check_g_cap, check_r, implied_g, payout, perpetual_pe, recovery_two_stage_pe
from lib.inputs import check_missing, ladder
from lib.partial_basis import local_basis_changed
from lib.scenario_transition import temporary_then_steady
from lib.zones import cut_points

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis', 'scenario_transition', 'zones'),
                'axes': {'lithium': 'lithium_carbonate', 'africa': 'africa_corridor'}}
SHARED_BASIS_KEYS = {'lithium': ('li2co3_l', 'li2co3_m', 'li2co3_h', 'axis_g2_li', 'h_duration_years'),
                     'africa': ('g2_afr_l', 'g2_afr_m', 'g2_afr_h')}
BASELINE_LOCAL = 'c3b9ae9fe3ac6db42489b15063c622eb73c611511fdafea0f8af62643bf1d375'

INPUTS = {
    'shares': 1917856391.0,  # 总股本；Longbridge static；2026-06-30
    'bps': 7.22,  # 每股净资产 CNY = 归母权益 138.49 亿 ÷ 总股本（三季报）；2026-09-30
    'equity': 138.49,  # 归母权益 亿（三季报 1,384,887.84 万）；用于每档前瞻 ROE（A16）；2026-09-30
    'r_li': 0.13,  # 蓝科锂业权益腿 **篮 6** 周期商品 / 小盘 篮子 r（A19；盈利是锂价函数）；2026-09-18
    'r_afr': 0.13,  # 非洲建材腿 **篮 6** 周期商品 / 小盘 篮子 r（A19；与 `6655.HK` 海外腿同判）；2026-09-18
    'r_mac': 0.1,  # 陶瓷机械与负极腿 **篮 4** 龙头制造 篮子 r（A19；常规经营）；2026-09-18
    'ni_exli': 13.38,  # 非锂分子 亿 = 2026H1 归母 ex-蓝科（12.84 − 6.15）× 2；按 `w_afr` / `w_mac` 拆成非洲腿与机械腿，**三档同值**（A1）；2026H1
    'realization_lk': 0.87757,  # 蓝科实现率 = 前三季度不含税 ASP 138,656（收入 35.08 亿 ÷ 销量 2.53 万吨，三季报）÷ 前三季度含税现货均价 158,000（H1 16.3 万 × 6 + Q3 14.8 万 × 3 按月加权；Q3 取锂轴引德银 $21,578 × 6.8645）（A2）；H1 读数 0.8765；2026Q3
    'cost_lk': 48212.0,  # 蓝科全口径单位成本 元/吨 = 前三季度 ASP 138,656 − 净利 19.45 亿 ÷ (25,300 吨 × 0.85)（三季报不给营业利润，按 15% 税率由净利倒推；同法复算 H1 = 49,560 ≈ 中报营业利润口径 49,494）；单 Q3 读数 44,902（A17）；2026Q3
    'vol_lk_plan': 41000.0,  # 蓝科量 吨/年 = 名牌；三档同量，折现见 `n_disc`（A3）；中报
    'vol_lk_h1': 33733.0,  # 蓝科最新期销量年化 = 前三季度 2.53 万 ÷ 0.75（H1 读数 3.56 万）；仅作对照与敏感性，**不入主公式**；2026Q3
    'r_disc': 0.13,  # 蓝科腿时点对齐折现率 = 蓝科腿篮子 r（A3；eval 强制等于 `r_li`）；2026-09-18
    'n_disc': 0.5,  # 蓝科腿时点对齐 τ（年）：估值基准日 2026-06-30 → 名牌量分子（2027 run-rate）年初 2027-01-01，取代原「销量追上名牌折 1 年」；窗口利润折 τ/2（A3 / A23）；2026-10-16
    'lk_h2_parent': 4.66,  # 蓝科腿窗口可分配利润的分子 亿 CNY：2026H2 科达应占蓝科利润 = Q3 实测 2.33 亿（前三季度 8.48 − H1 6.15，三季报）+ Q4 按 Q3 同额——蓝科无卖方共识（与腿分子同口径，A23）；原按 H1 6.15 亿代替；2026Q3
    'y1_path': 2026.0,  # 稳态回报三段 Y1 = 可见年末（非洲、机械腿分子为 2026H1 年化）；A23；2026-10-16
    'y2_path': 2030.0,  # 稳态回报三段 Y2 = Y1 + 4（进入门槛判「中」：新瓷砖 / 玻璃线建设期 12–18 个月、无客户认证门槛、中国厂商出海设厂正在进入、单位产能投资中等；不确定，标「中」）；A23；2026-10-16
    'rs_afr': 0.13,  # 非洲建材腿稳态回报 = max(自身周期（口径不同，不用）, 成熟同业穿越周期（A 股样本只有短窗，不足 5 年不认 → 空）, 兜底「非洲建材」11%) = 11%，抬到下限 r 13%（同 `r_afr`，不归篮）；A23；2026-10-16
    'rs_mac': 0.15,  # 机械与负极腿稳态回报 = 兜底「有壁垒重资产 · 设备」15%（同业 9.0% 更低；同 `r_mac` 口径，不归篮）；A23；2026-10-16
    'stake_lk': 0.436,  # 科达对蓝科归母份额 = 前三季度贡献 8.48 ÷ 蓝科净利 19.45（三季报；持股 43.58%，权益法）；2026Q3
    'tax_lk': 0.15,  # 蓝科所得税率（西部大开发，A17）；2026H1
    'g2_li': 0.0,  # 蓝科腿永续 g2 = 0，来源层级 = 商品腿默认（锂实际价格漂移 ≤ −3% → 0，不取负；同业反解 2.35% 只作敏感区，A6）；cap = min(6%, r_li − 4%) = 6%；2026-09-18
    'w_afr': 0.796874,  # 非锂分子内非洲建材权重 = 公开数据推断（A5）：科达应占海外建材 2026H1 归母 5.331 亿 ÷ H1 ex-蓝科 6.69 亿；eval 由下列原始输入复算；2026H1
    'w_mac': 0.203126,  # 非锂分子内机械与负极权重 = 1 − `w_afr`（A5）；2026H1
    'afr_rev_fy2025': 81.854154,  # 海外建材分部营业收入 亿（年报分部信息 818,541.54 万）；A5 推断输入，不入主公式；FY2025
    'afr_cogs_fy2025': 52.990036,  # 海外建材分部营业成本 亿（年报 529,900.36 万）；A5 推断输入；FY2025
    'afr_rev_h1': 49.289941,  # 海外建材分部营业收入 亿（中报分部信息 492,899.41 万）；A5 推断输入；2026H1
    'afr_cogs_h1': 27.662101,  # 海外建材分部营业成本 亿（中报 276,621.01 万）；A5 推断输入；2026H1
    'tf_np_fy2025': 14.96,  # 特福国际（海外建材经营主体）FY2025 净利润 亿；重组报告书（媒体转引）；A5 推断输入；FY2025
    'tf_uplift_fy2025': 7.57,  # 特福 51.55% 并表后科达备考归母增量 = 20.66 − 13.09 亿；重组报告书备考（媒体转引）；A5 推断输入；FY2025
    'stake_tf': 0.4845,  # 科达对特福国际持股（年报：Keda 加纳 / 坦桑尼亚少数股东 51.55%）；A5 推断输入；FY2025
    'nci_fy2025': 8.579273,  # 合并少数股东损益 亿（年报 85,792.73 万）；A5 推断区间输入；FY2025
    'nci_h1': 6.887172,  # 合并少数股东损益 亿（中报 68,871.72 万）；A5 推断区间输入；2026H1
    'g2_mac_l': -0.02,  # **L** 机械与负极腿永续增长；来源层级 = 无同业锚·自定（A7 定性论证：陶瓷机械随全球瓷砖产能投资周期、负极过剩）；篮 4 下 PE 8.33×；2026-09-09
    'g2_mac_m': 0.0,  # **M** 机械与负极腿永续增长；无同业锚·自定（A7）；PE 10.0×；2026-09-09
    'g2_mac_h': 0.01,  # **H** 机械与负极腿永续增长；无同业锚·自定（A7）；PE 10.40×（稳态回报三段，A23）；2026-09-09
    'ni_ttm': 20.71,  # TTM 归母 = 前三季度 19.11 + FY2025Q4 1.60（FY2025 13.09 − 2025 前三季度 11.49，由三季报同比 +66.30% 倒推）；仅作对照，**不入主公式**；2026Q3
    'ni_fy2024': 10.06,  # FY2024 实测归母（锂价谷底年）；仅作 `deep_discount` 坐标；FY2024
    'ni_exli_fy2025': 9.91,  # FY2025 归母 ex-蓝科 = 13.09 − 3.18；仅作 `deep_discount` 坐标（A1）；FY2025
    'ni_2026e_street': 23.59,  # 国金证券 2026E 归母（三季报点评，2027E / 2028E 25.24 / 28.10；原 24.13 / 28.02 / 31.42）；仅作交叉校验；2026-10-29
    'tp_street': 26.0,  # 卖方目标价 CNY（仅 1 家）；仅作交叉校验（A14）；2026-05-06
    'pe_own_hi': 22.9,  # own-year PE 实测上沿（2024 锂价谷底）；**护栏，不入主公式**；2024
    'pe_own_lo': 6.4,  # own-year PE 实测下沿（2022 锂价高点）；仅作对照；2022
    'capex_anode': 45.0,  # 包头 50 万吨一体化人造石墨项目总投资 亿（含流动资金；控股子公司福建科达新能源；2026-10 开工、建设期 10–12 个月）；未花 \(K_{remain}\)（A20）；2026-09-21 公告
    'stake_anode': 0.7899,  # 科达对福建科达新能源持股（受让 6.82% 后 72.17% → 78.99%，2026-09-16 公告）；2026-09-16
    'roic_anode_l': 0.057,  # **L** 项目稳态 ROIC = 2026H1 负极价格战读数：尚太科技 7.6% / 中科电气 3.8% 两家均值（营业利润 × 0.85 ÷ (股东权益 + 净债)，半年年化；Longbridge）（A20）；2026H1
    'roic_anode_m': 0.089,  # **M** 项目稳态 ROIC = 同业已达产完整年中位：尚太 FY2024–25 均 11.5%、中科 FY2024–25 均 6.4% → 8.9%（同口径）（A20）；FY2025
    'roic_anode_h': 0.11,  # **H** 项目稳态 ROIC = 最可比同业（尚太，一体化 + 北方低电价）FY2023–25 全周期 10.5 / 11.9 / 11.0% ≈ 11%；> r_mac 不加分（A20）；FY2025
    'afr_rev_yoy_fy2025': 0.7361,  # 海外建材分部营业收入同比（年报 +73.61%）；倒推 FY2024 分部收入，只用于 A22 瓷砖单价；FY2025
    'tile_sales_fy2025': 2.0,  # 建筑陶瓷销量 亿㎡（年报产销量表）；A22 单价推断输入；FY2025
    'tile_sales_yoy_fy2025': 0.1507,  # 建筑陶瓷销量同比（年报 +15.07%）；倒推 FY2024 销量；FY2025
    'glass_out_fy2025': 35.0,  # 浮法玻璃产量 万吨（年报「超过 35 万吨」，取下限）；A22 玻璃单价推断输入；FY2025
    'tile_cap_now': 2.0,  # 已投产瓷砖年产能 亿㎡（2026-06 投资者关系记录「约 2 亿平方米」）；2026-06
    'tile_cap_after': 2.7,  # 科特迪瓦二期 + 肯尼亚基苏木二期 + 塞内加尔三期 + 几内亚（共 5 条线）2026–2027 投产后瓷砖年产能 亿㎡（2026-09 投资者关系记录「近 2.7 亿㎡」；2026-06 记录为 2.5，未含塞内加尔三期）；\(V_{opt}\) 份数（A22）；2026-09
    'glass_peru': 20.0,  # 秘鲁玻璃项目年产能 万吨（同上；在建，工程进度 88.44%，中报）；\(V_{opt}\) 份数（A22）；2026-06
    'glass_ghana': 20.0,  # 加纳玻璃项目年产能 万吨（同上；在建，2026H1 奠基）；\(V_{opt}\) 份数（A22）；2026-06
    't_tile': 2027.0,  # 瓷砖三项投产年（科特迪瓦二期 / 基苏木二期「2026 年底或 2027 年初」、几内亚「2027 年」，取 2027）；2026-06
    't_peru': 2026.0,  # 秘鲁玻璃投产年（「预计 2026 年投产」）；2026-06
    't_ghana': 2027.0,  # 加纳玻璃投产年（「预计 2027 年下半年投产」）；2026-06
    'capex_kisumu2': 2.877977,  # 基苏木陶瓷厂二期预算 亿（中报在建工程 28,779.77 万）；A22 未投资本；2026-06-30
    'prog_kisumu2': 0.0967,  # 基苏木二期工程进度（中报 9.67%）；2026-06-30
    'capex_ci2': 1.618814,  # 科特迪瓦陶瓷厂二期预算 亿（中报 16,188.14 万）；A22 未投资本；2026-06-30
    'prog_ci2': 0.5939,  # 科特迪瓦二期工程进度（中报 59.39%）；2026-06-30
    'capex_peru': 4.924745,  # 秘鲁玻璃厂预算 亿（中报 49,247.45 万）；A22 未投资本；加纳预算未披露，按同规模玻璃线代理；2026-06-30
    'prog_peru': 0.8844,  # 秘鲁玻璃工程进度（中报 88.44%）；2026-06-30
    'spent_ghana': 0.072202,  # 加纳玻璃厂在建工程余额 亿（中报 722.02 万）；从代理预算中扣除；2026-06-30
    'glass_kenya': 20.0,  # 肯尼亚浮法玻璃项目年产能 万吨：公告日熔 600 吨（×365 ≈ 21.9 万吨），按成品率取与秘鲁 / 加纳同规模 20 万吨（推断）；\(V_{opt}\) 份数（A22）；2026-10-28 公告
    't_kenya': 2028.0,  # 肯尼亚玻璃投产年（公告「预计 2026 年 12 月开工、建设期约 19–20 个月」→ 2028 年中后）；2026-10-28 公告
    'capex_kenya': 7.570066,  # 肯尼亚玻璃项目总投资 亿（1.127085 亿美元 × 6.7165，含流动资金；实施主体未披露，按海外建材经由特福国际 48.45% 计）；全部未投（A22）；2026-10-28 公告
}
FORMULA_ID = "keda_lanke_axis_afr_mac_perpetual_g_vopt_named_v5"
MIN_R_MINUS_G = 0.02
# A18: realised trough→recovery paths — the company's (Longbridge annual parent NI,
# FY2024 10.06 亿 → FY2025 13.09 亿, mostly Africa growth) and Lanke's own (net profit
# FY2025 7.30 亿 → 2026H1 14.11 亿 × 2, the lithium price V; 科达 interim / annual report).
RECOVERY_MEASURED = {"公司 FY2024→FY2025": (10.06, 13.09, 1), "蓝科 FY2025→2026H1×2": (7.30, 28.22, 1)}
# A6 sensitivity: the lithium-producer cross-section g2 that the framework does not use.
G2_LI_PEER = 0.0235
# A20 sensitivity: anode ROIC with every tier on 2026H1 price-war readings —
# 中科电气 3.8% / two-peer mean 5.7% / 尚太科技 7.6% (annualised, Longbridge).
ANODE_ROIC_STRESS = (0.038, 0.057, 0.076)

TIERS = ("l", "m", "h")
LEGS = ("lk", "afr", "mac")
R_ROWS = {"lk": "r_li", "afr": "r_afr", "mac": "r_mac"}
YI = 1e8

REQUIRED = [
    "shares", "bps", "equity",
    "r_li", "r_afr", "r_mac",
    "ni_exli",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_lk", "cost_lk", "vol_lk_plan", "vol_lk_h1",
    "r_disc", "n_disc", "stake_lk", "tax_lk", "g2_li", "axis_g2_li",
    "w_afr", "w_mac",
    "g2_afr_l", "g2_afr_m", "g2_afr_h",
    "g2_mac_l", "g2_mac_m", "g2_mac_h",
    "ni_ttm", "ni_fy2024", "ni_exli_fy2025", "ni_2026e_street", "tp_street",
    "pe_own_hi", "pe_own_lo",
    "capex_anode", "stake_anode", "roic_anode_l", "roic_anode_m", "roic_anode_h",
    "afr_rev_fy2025", "afr_cogs_fy2025", "afr_rev_h1", "afr_cogs_h1",
    "tf_np_fy2025", "tf_uplift_fy2025", "stake_tf", "nci_fy2025", "nci_h1",
    "afr_rev_yoy_fy2025", "tile_sales_fy2025", "tile_sales_yoy_fy2025", "glass_out_fy2025",
    "tile_cap_now", "tile_cap_after", "glass_peru", "glass_ghana", "t_tile", "t_peru", "t_ghana",
    "capex_kisumu2", "prog_kisumu2", "capex_ci2", "prog_ci2", "capex_peru", "prog_peru", "spent_ghana",
    "glass_kenya", "t_kenya", "capex_kenya",
    "lk_h2_parent", "y1_path", "y2_path", "rs_afr", "rs_mac", "h_duration_years",
]
RS_ROWS = {"afr": "rs_afr", "mac": "rs_mac"}
NUM_YEAR = 2026            # Africa / machinery numerator = 2026H1 annualised
P_TIERS = (0.0, 0.25, 1.0)  # A22 — table 3 only, never an input
TOL = 0.05


def opt_units(inp: dict[str, float]) -> dict[str, float]:
    """A22: tile 元/m² and glass 元/t from public segment data (inference, biases in A22)."""
    rev24 = inp["afr_rev_fy2025"] / (1.0 + inp["afr_rev_yoy_fy2025"])
    tile24 = inp["tile_sales_fy2025"] / (1.0 + inp["tile_sales_yoy_fy2025"])
    p_tile = rev24 / tile24                                     # 亿元 / 亿㎡ = 元/㎡
    glass_rev = inp["afr_rev_fy2025"] - inp["tile_sales_fy2025"] * p_tile   # 亿元
    p_glass = glass_rev / inp["glass_out_fy2025"] * 1e4         # 亿元 / 万吨 → 元/吨
    margin = inp["w_afr"] * inp["ni_exli"] / (2.0 * inp["afr_rev_h1"])
    return {"p_tile": p_tile, "p_glass": p_glass, "margin": margin}


def unspent(inp: dict[str, float]) -> dict[str, float]:
    """A22 (valuation-rules 2026-10-04: capacity options deduct unspent capital), 亿元, 100% basis.

    Budgets / progress from the 2026H1 在建工程 note.  Guinea, Senegal phase III
    and Ghana have no disclosed budget: Guinea and Senegal III = mean of the two
    ceramic phase-II budgets each, Ghana = the Peru budget (same 20 万吨 float
    line) less what it has already booked — proxies, named in A22.  Kenya glass
    = the 2026-10-28 announced total, nothing spent yet.
    """
    kis = inp["capex_kisumu2"] * (1.0 - inp["prog_kisumu2"])
    ci2 = inp["capex_ci2"] * (1.0 - inp["prog_ci2"])
    phase2_mean = (inp["capex_kisumu2"] + inp["capex_ci2"]) / 2.0
    return {"tile": kis + ci2 + 2.0 * phase2_mean,
            "peru": inp["capex_peru"] * (1.0 - inp["prog_peru"]),
            "ghana": max(0.0, inp["capex_peru"] - inp["spent_ghana"]),
            "kenya": inp["capex_kenya"]}


def opt_items(inp: dict[str, float], pe_afr_h: float, glass_scale: float = 1.0) -> list[tuple[str, float, float, float, float]]:
    """[(label, revenue 亿, ΔNI 亿, gross V, net V per share)] for the named projects (A22).

    Net = gross − Keda's share (stake_tf) of the unspent capital, spent before
    start-up and therefore taken at the numerator year (2026) undiscounted.
    """
    u = opt_units(inp)
    k = unspent(inp)
    items = [
        ("瓷砖 科特迪瓦二期 + 基苏木二期 + 塞内加尔三期 + 几内亚", (inp["tile_cap_after"] - inp["tile_cap_now"]) * u["p_tile"], inp["t_tile"], k["tile"]),
        ("秘鲁玻璃 20 万吨", inp["glass_peru"] * u["p_glass"] * glass_scale / 1e4, inp["t_peru"], k["peru"]),
        ("加纳玻璃 20 万吨", inp["glass_ghana"] * u["p_glass"] * glass_scale / 1e4, inp["t_ghana"], k["ghana"]),
        ("肯尼亚玻璃 20 万吨", inp["glass_kenya"] * u["p_glass"] * glass_scale / 1e4, inp["t_kenya"], k["kenya"]),
    ]
    out = []
    for label, rev, t, cap in items:
        dni = rev * u["margin"]
        gross = dni * pe_afr_h / (1.0 + inp["r_afr"]) ** (t - NUM_YEAR) * YI / inp["shares"]
        net = gross - cap * inp["stake_tf"] * YI / inp["shares"]
        out.append((label, rev, dni, gross, net))
    return out
# A5 (valuation-rules「公开数据推断」, 2026-10-03): w_afr is inferred, not a placeholder.
W_TOL = 1e-5


def afr_weight(inp: dict[str, float]) -> dict[str, float]:
    """A5 Africa-leg share of the ex-Lanke numerator, from disclosed numbers only.

    Point (gross-profit route, two periods): Twyford's FY2025 net profit / segment
    gross profit, applied to the 2026H1 segment gross profit; Twyford's parent
    share from the restructuring pro forma (uplift / 51.55%); Keda's share 48.45%.
    Assumption: net / gross ratio unchanged FY2025 -> 2026H1 (operating leverage
    makes this the low side).  Bracket (NCI route): consolidated minority P&L less
    the non-Africa minority share (FY2025 residual, at full-year or half-year level).
    """
    out: dict[str, float] = {}
    gp25 = inp["afr_rev_fy2025"] - inp["afr_cogs_fy2025"]
    gph1 = inp["afr_rev_h1"] - inp["afr_cogs_h1"]
    s = inp["stake_tf"]
    tf_attr25 = inp["tf_uplift_fy2025"] / (1.0 - s)
    attr = tf_attr25 / inp["tf_np_fy2025"]
    exli_h1 = inp["ni_exli"] / 2.0
    out["FY2025 披露"] = tf_attr25 * s / inp["ni_exli_fy2025"]
    out["2026H1 毛利路径"] = gph1 * inp["tf_np_fy2025"] / gp25 * attr * s / exli_h1
    local25 = inp["tf_np_fy2025"] - tf_attr25
    other25 = inp["nci_fy2025"] - inp["tf_uplift_fy2025"] - local25
    for label, other in (("2026H1 少数股东路径·其余按全年", other25), ("2026H1 少数股东路径·其余按半年", other25 / 2.0)):
        out[label] = (inp["nci_h1"] - other - local25 / 2.0) * s / (1.0 - s) / exli_h1
    return out


def lanke_ni(inp: dict[str, float], tag: str) -> float:
    """Keda's share of Lanke net profit, 亿 CNY, nameplate volume discounted."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    margin = inp[f"li2co3_{tag}"] * inp["realization_lk"] - inp["cost_lk"]
    return disc * inp["stake_lk"] * inp["vol_lk_plan"] * margin * (1.0 - inp["tax_lk"]) / YI


def legs(inp: dict[str, float], tag: str) -> dict[str, float]:
    """{leg: net income} for one tier, 亿 CNY."""
    return {"lk": lanke_ni(inp, tag), "afr": inp["ni_exli"] * inp["w_afr"], "mac": inp["ni_exli"] * inp["w_mac"]}


def leg_g(inp: dict[str, float], leg: str, tag: str) -> float:
    return inp["g2_li"] if leg == "lk" else inp[f"g2_{leg}_{tag}"]


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return (inp["ni_exli"] + lanke_ni(inp, tag)) / inp["equity"]


def path_pe(t0: int, g: float, roe: float, rs: float, y1: int, y2: int, r: float) -> float:
    """A23 three-segment multiple on unit earnings at t = 1 (calendar t0): RONIC = roe through
    y1, linear to rs by y2, Gordon tail from y2 (valuation-rules ②; gordon.py helper [待建])."""
    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs
        return roe + (rs - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal >= y2 and cal > y1:
            return pv + e * payout(g, rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1


def leg_rs(inp: dict[str, float], leg: str, roe: float, r_: float) -> float:
    """Steady return: min(forward, max(rs_leg, r)); forward below r -> forward (持续失败)."""
    return min(max(inp[RS_ROWS[leg]], r_), roe) if roe >= r_ else roe


def leg_pe(inp: dict[str, float], leg: str, tag: str, r_shift: float = 0.0,
           g_override: float | None = None, roe: float | None = None, t0: int | None = None) -> float:
    """Per-leg multiple.  Lanke (commodity leg, exempt) and g <= 0 legs: plain Gordon; g > 0 legs on
    the three-segment path (A23).  `roe` / `t0` serve the H pass-by's M-world tail."""
    g = leg_g(inp, leg, tag) if g_override is None else g_override
    roe = forward_roe(inp, tag) if roe is None else roe
    r_ = inp[R_ROWS[leg]] + r_shift
    if leg == "lk" or g <= 0:
        return perpetual_pe(g, roe, r_)
    t0 = NUM_YEAR if t0 is None else t0
    return path_pe(t0, g, roe, leg_rs(inp, leg, roe, r_), int(inp["y1_path"]), int(inp["y2_path"]), r_)


def anode_penalty(inp: dict[str, float], tag: str) -> float:
    """A20: unspent anode capex charged at (1 - ROIC_proj / r_mac), 亿 CNY; no credit above r."""
    shortfall = max(0.0, 1.0 - inp[f"roic_anode_{tag}"] / inp["r_mac"])
    return inp["capex_anode"] * inp["stake_anode"] * shortfall


PASSBY_LEGS = ("lk",)  # A23 (user 2026-10-18): only the lithium-axis leg passes by


def leg_values(inp: dict[str, float], tag: str, r_shift: float = 0.0,
               passby_legs: tuple[str, ...] = PASSBY_LEGS) -> dict[str, float]:
    """{leg: value 亿}.  H passes by (A23) on the Lanke leg only: one H-world year, then the M
    lithium world.  The Africa / machinery legs are not on the lithium axis and stay in their own
    H world (persistent H value), even though their RONIC borrows the company ROE."""
    ni = legs(inp, tag)
    if tag != "h":
        return {leg: ni[leg] * leg_pe(inp, leg, tag, r_shift) for leg in LEGS}
    ni_m, roe_h, roe_m = legs(inp, "m"), forward_roe(inp, "h"), forward_roe(inp, "m")
    out = {}
    for leg in LEGS:
        if leg not in passby_legs:
            out[leg] = ni[leg] * leg_pe(inp, leg, "h", r_shift)
            continue
        g = leg_g(inp, leg, "h")
        r_ = inp[R_ROWS[leg]] + r_shift
        # 原研究只让蓝科锂腿高价持续一段，随后回中档；期限由共享轴提供。
        years = inp["h_duration_years"]
        multiple = leg_pe(inp, leg, "h", r_shift, roe=roe_m, t0=NUM_YEAR + years)
        out[leg] = temporary_then_steady(ni[leg], ni_m[leg], payout(g, roe_h), g, r_, years, multiple)
    return out


def window(inp: dict[str, float], tag: str) -> float:
    """A23: Lanke-leg window distributable profit per share (Keda's 2026H2 Lanke share at the H1
    print, × (1 − g2_li/ROE)), discounted τ/2 at the Lanke basket r."""
    b = max(inp["g2_li"], 0.0) / forward_roe(inp, tag)
    return inp["lk_h2_parent"] * (1.0 - b) / (1.0 + inp["r_disc"]) ** (inp["n_disc"] / 2.0) * YI / inp["shares"]


def value(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None, r_shift: float = 0.0) -> float:
    """Sum of legs less the anode K_remain charge, 亿 CNY.  `pes` overrides the per-leg multiples
    (persistent tiers, no pass-by — flat-ladder reading only)."""
    if pes is not None:
        ni = legs(inp, tag)
        return sum(ni[leg] * pes[leg] for leg in LEGS) - anode_penalty(inp, tag)
    return sum(leg_values(inp, tag, r_shift).values()) - anode_penalty(inp, tag)


def anchor(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None, r_shift: float = 0.0) -> float:
    return value(inp, tag, pes, r_shift) * YI / inp["shares"] + window(inp, tag)


def implied_r_shift(inp: dict[str, float], target: float) -> float:
    """δ such that the M-tier SOTP with every leg at r_leg + δ equals `target`
    (the street target or book value — never the current quote).

    All three basket r move together (the volume discount r_disc stays put); the
    answer is the parallel shift the target implies for the basket table, not a
    per-leg r.  Bisection on δ ∈ [-8%, +20%]: the SOTP is monotone decreasing in δ.
    """
    lo, hi = -0.08, 0.20

    def f(delta: float) -> float:
        return anchor(inp, "m", r_shift=delta) - target

    if f(lo) < 0 or f(hi) > 0:
        raise ValueError("implied r shift outside bisection bracket")
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def evaluate(inp):
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(inp[key]) for key in REQUIRED):
        raise ValueError('all required inputs must be finite')
    for key in ('y1_path', 'y2_path', 't_tile', 't_peru', 't_ghana', 't_kenya'):
        if isinstance(inp[key], bool) or not float(inp[key]).is_integer():
            raise ValueError(f'{key} must be a whole calendar year')

    r = {leg: inp[R_ROWS[leg]] for leg in LEGS}

    # --- Step 1: baskets — each leg's r must be the basket it names -----------
    baskets = {'r_li': 6, 'r_afr': 6, 'r_mac': 4}
    for leg in LEGS:
        row = R_ROWS[leg]
        if row not in baskets:
            errors.append(f"{row}: Inputs source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errors += check_r(r[leg], row, baskets.get(row))
    # A3: the nameplate-volume discount follows the Lanke leg's basket r.
    if abs(inp["r_disc"] - r["lk"]) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal r_li={r['lk']} (A3)")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 2: Lanke leg reads the shared lithium axis ------------------------
    # Shared lithium inputs are injected by calculate(), not parsed from prose.
    for k in ("g2_li", "axis_g2_li"):
        errors += check_g_cap(inp[k], r["lk"], k)
    if inp["g2_li"] < 0:
        errors.append("g2_li must not be negative")
    if r["lk"] - inp["g2_li"] < MIN_R_MINUS_G:
        errors.append("lithium discount rate too close to growth")
    for key, lo, hi in (
        ("realization_lk", 0.0, 1.0), ("stake_lk", 0.0, 1.0), ("tax_lk", -1e-12, 1.0),
    ):
        if not lo < inp[key] < hi:
            errors.append(f"{key}={inp[key]} outside ({lo}, {hi})")
    if inp["cost_lk"] <= 0 or inp["vol_lk_plan"] <= 0:
        errors.append("cost_lk and vol_lk_plan must be positive")
    ni = {t: legs(inp, t) for t in TIERS}
    errors += ladder("Lanke NI", *(ni[t]["lk"] for t in TIERS))
    if ni["l"]["lk"] <= 0:
        errors.append(f"Lanke NI_L={ni['l']['lk']:.2f} <= 0 — leg does not clear cost at axis L")

    # --- Step 3: non-Li legs — weights, growth ladders, Africa axis ------------
    w_inf = afr_weight(inp)
    if abs(inp["w_afr"] - w_inf["2026H1 毛利路径"]) > W_TOL:
        errors.append(f"w_afr={inp['w_afr']} vs A5 inference {w_inf['2026H1 毛利路径']:.6f}")
    w_sum = inp["w_afr"] + inp["w_mac"]
    if abs(w_sum - 1.0) > 1e-6:
        errors.append(f"leg weights must sum to 1: {w_sum}")
    for leg in ("afr", "mac"):
        if not 0.0 < inp[f"w_{leg}"] < 1.0:
            errors.append(f"w_{leg}={inp[f'w_{leg}']} outside (0, 1)")
        errors += ladder(f"g2_{leg}", *(inp[f"g2_{leg}_{t}"] for t in TIERS))
        for t in TIERS:
            g = inp[f"g2_{leg}_{t}"]
            if r[leg] - g <= 0:
                errors.append(f"g2_{leg}_{t}={g:.4f} >= r_{leg}={r[leg]} — perpetuity diverges")
            # valuation-rules.md 永续上限: min(6%, r − 4%) per leg.
            errors += check_g_cap(g, r[leg], f"g2_{leg}_{t}")
    if errors:
        raise ValueError('; '.join(errors))

    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    # Growth is paid for out of retained earnings; a shrinking business is not
    # assumed to hand back more than it earns — per leg.
    for t in TIERS:
        roe = forward_roe(inp, t)
        if roe <= 0:
            errors.append(f"ROE_{t}={roe:.4f} must be positive")
            continue
        for leg in LEGS:
            g = leg_g(inp, leg, t)
            pay = payout(g, roe)
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
    # A20: the anode charge sits on the machinery leg's basket and eases toward H.
    if inp["capex_anode"] <= 0 or not 0.0 < inp["stake_anode"] < 1.0:
        errors.append("capex_anode must be positive and stake_anode in (0, 1)")
    errors += ladder("roic_anode", *(inp[f"roic_anode_{t}"] for t in TIERS))
    # A23: path years ordered, steady returns at or above their leg's r, window non-negative.
    if not inp["y1_path"] < inp["y2_path"]:
        errors.append("y1_path must precede y2_path (A23)")
    for leg, row in RS_ROWS.items():
        if inp[row] < r[leg] - 1e-12:
            errors.append(f"{row}={inp[row]} below r_{leg} — steady return floors at r (valuation-rules ②)")
    if inp["lk_h2_parent"] < 0:
        errors.append("lk_h2_parent < 0 — window profit floors at 0")
    if errors:
        raise ValueError('; '.join(errors))

    pe = {t: {leg: leg_pe(inp, leg, t) for leg in LEGS} for t in TIERS}
    total = {t: inp["ni_exli"] + ni[t]["lk"] for t in TIERS}
    # Historical band deviations are review flags, not fabricated fixes.
    pe_company = {t: value(inp, t) / total[t] for t in TIERS}
    outside_band = [t.upper() for t in TIERS
                    if not inp["pe_own_lo"] <= pe_company[t] <= inp["pe_own_hi"]]

    # --- Step 4: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        raise ValueError(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    A, B = cut_points(L, M, H)

    # flat-multiple: each leg held at its own PE_M across the three tiers — the
    # ladder must survive on the Lanke leg's axis price alone.
    flat = {t: anchor(inp, t, pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])


    # --- Step 5: V_opt (A22) — named projects, own ruler, start-up year → numerator year
    items = opt_items(inp, pe["h"]["afr"])
    v_opt = sum(x[4] for x in items)
    if v_opt <= 0:
        errors.append(f"V_opt {v_opt:.2f} <= 0 after unspent capital (A22, 回对话)")
    for t_key in ("t_tile", "t_peru", "t_ghana", "t_kenya"):
        if inp[t_key] < NUM_YEAR:
            errors.append(f"{t_key} before the numerator year")
    if not inp["tile_cap_after"] > inp["tile_cap_now"] > 0:
        errors.append("tile capacity must step up")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs: {leaked}")
    adj = [a + p_ * v_opt for a, p_ in zip((L, M, H), P_TIERS)]

    if errors:
        raise ValueError('; '.join(errors))
    tiers = lambda values: dict(zip('LMH', values))
    ps = YI / inp['shares']
    amounts = {t: leg_values(inp,t) for t in TIERS}
    option_projects = {}
    for key, (_, rev, profit, gross, net) in zip(('tile', 'peru_glass', 'ghana_glass', 'kenya_glass'), items):
        option_projects[key] = {'revenue': rev, 'profit': profit, 'gross': gross, 'value': net}
    def band(over):
        return tiers(anchor(dict(inp, **over), t) for t in TIERS)
    sensitivity = {
        'lithium_growth_plus_1pp': band({'g2_li': inp['g2_li']+.01}),
        'lithium_growth_peer': band({'g2_li': G2_LI_PEER}),
        'africa_steady_15pct': band({'rs_afr': .15}),
        'africa_growth_none': band({f'g2_afr_{t}': 0 for t in TIERS}),
        'return_path_2028': band({'y2_path': 2028}),
        'without_time_alignment': band({'n_disc': 0., 'lk_h2_parent': 0.}),
        'anode_stress': band(dict(zip((f'roic_anode_{t}' for t in TIERS), ANODE_ROIC_STRESS))),
        'anode_mid_all': band({f'roic_anode_{t}': inp['roic_anode_m'] for t in TIERS}),
        'glass_price_half_value': sum(x[4] for x in opt_items(inp, pe['h']['afr'], .5)),
        'lithium_high_persistent': (sum(ni['h'][leg]*pe['h'][leg] for leg in LEGS)
                                    - anode_penalty(inp,'h'))*ps + window(inp,'h'),
    }
    sensitivity['africa_weight_cases'] = {}
    for name, weight in zip(('fy2025', 'h1_gross_profit', 'h1_minority_full_year', 'h1_minority_half_year'), w_inf.values()):
        sensitivity['africa_weight_cases'][name] = band({'w_afr': weight, 'w_mac': 1-weight})
    for name, dr in (('discount_minus_05pp', -.005), ('discount_plus_05pp', .005)):
        sensitivity[name] = band({key: inp[key]+dr for key in ('r_li','r_afr','r_mac','r_disc')})
    for name, dg in (('africa_mid_growth_plus_1pp', .01), ('africa_mid_growth_minus_1pp', -.01)):
        sensitivity[name] = anchor({**inp, 'g2_afr_m': inp['g2_afr_m']+dg}, 'm')
    return {
        'ticker': '600499.SH', 'currency': 'CNY', 'valuation_as_of': None, 'framework_as_of': None,
        'anchors': tiers((L,M,H)), 'cut_points': {'A': A, 'B': B}, 'candidate': None,
        'option': {'label': '海外建材项目', 'value': v_opt, 'value_unit': 'CNY_PER_SHARE', 'weights': tiers(P_TIERS),
                   'anchors': tiers(adj), 'projects': option_projects},
        'segments': {**{leg: tiers(amounts[t][leg]*ps for t in TIERS) for leg in LEGS},
                     'anode': tiers(-anode_penalty(inp,t)*ps for t in TIERS),
                     'window': tiers(window(inp,t) for t in TIERS)},
        'key_parameters': {
            leg: {'discount_rate': tiers((r[leg],)*3), 'growth_rate': tiers(leg_g(inp,leg,t) for t in TIERS),
                  'forward_return': tiers(forward_roe(inp,t) for t in TIERS),
                  'steady_return': tiers(leg_rs(inp,leg,forward_roe(inp,t),r[leg]) if leg != 'lk' and leg_g(inp,leg,t)>0 else None for t in TIERS),
                  'multiple': tiers(pe[t][leg] for t in TIERS)} for leg in LEGS},
        'operating': {'company_multiple': tiers(pe_company[t] for t in TIERS),
                      'income': {leg: tiers(ni[t][leg] for t in TIERS) for leg in LEGS},
                      'roe': tiers(forward_roe(inp,t) for t in TIERS), 'flat': tiers(flat[t] for t in TIERS),
                      'africa_weight': inp['w_afr'], 'anode_penalty': tiers(anode_penalty(inp,t) for t in TIERS),
                      'lithium_passby': True},
        'sensitivity': sensitivity, 'outside_historical_band': outside_band,
    }


def calculate(context):
    lithium = dict(context['axes']['lithium'])
    if lithium.pop('h_after') != 'M' or lithium.pop('h_scope') != 'lithium':
        raise ValueError('unsupported lithium scenario transition')
    africa = context['axes']['africa']
    shared_axes = {'lithium': {k: lithium[k] for k in SHARED_BASIS_KEYS['lithium']},
                   'africa': {k: africa[k] for k in SHARED_BASIS_KEYS['africa']}}
    p = {**INPUTS, **shared_axes['lithium'], **shared_axes['africa']}
    result = evaluate(p)
    result['historical_financial_statement_as_of'] = '2026-09-30'
    result['historical_research_as_of'] = '2026-10-30'
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments'] = {key: {'unit': 'CNY_PER_SHARE', 'values': values}
                          for key, values in result['segments'].items()}
    for data in result['key_parameters'].values():
        for key in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
            data[key] = {'unit': 'RATIO', 'values': data[key]}
    result['review_flags'] = ['historical_mixed_dates_and_africa_profit_inference',
                              'historical_capital_funding_and_project_overlap_unverified',
                              'historical_multiple_band_comparability_unverified']
    if result.pop('outside_historical_band'):
        result['review_flags'].append('historical_multiple_outside_band')
    local = {'inputs': INPUTS, 'recovery_measured': RECOVERY_MEASURED,
             'g2_li_peer': G2_LI_PEER, 'anode_roic_stress': ANODE_ROIC_STRESS,
             'num_year': NUM_YEAR, 'p_tiers': P_TIERS, 'shared_axes': shared_axes}
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(local, BASELINE_LOCAL)
    return result
