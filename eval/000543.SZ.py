"""Historical Wanneng valuation draft with an explicit shared coal snapshot.

The historical leverage issue is disclosed, not used to erase the old band.
No historical model has been executed or confirmed in this continuation.
"""
from __future__ import annotations
import math
import statistics
from lib.gordon import (BASKET_R, capped_payout_pe, check_branch, check_g_cap,
                        check_r, g_cap, payout_gap, perpetual_pe)
from lib.inputs import check_missing, ladder
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'),
                'axes': {'coal': 'coal_price'}}
HISTORICAL_PARTIAL_FINGERPRINT = 'f98235668244a21bcc007bbe249eae3eaf1e8ef9063950ced0e7f2e4c24fe491'
# The legacy baseline included the then-current axis source hash. Keep that
# historical token only when comparing to the legacy snapshot; the runner
# separately records the actual current source hash for provenance.
HISTORICAL_COAL_AXIS_VERSION = 'eadd617fd17ce8c094c5afcd6aeb6be07e6485105032edf0dcb4eac0884a9755'

INPUTS = {
    'shares': 2266863331.0,  # 总股本；Longbridge static；2026-06-30
    'bps': 7.7403,  # 每股净资产 CNY = 归母权益 175.46 亿 ÷ 股本；2026 三季报（同一控制下合并新能公司 51%，资本公积 −19.85 亿，A13）；2026-09-30
    'equity': 175.46,  # 归母权益**亿元**（2026 三季报合并资产负债表）；ROE_M = eps_m × shares ÷ equity = 9.4%（valuation-rules「永续增长口径」）；2026-09-30
    'r_perp': 0.1,  # 篮 4 龙头制造 10%：整公司一条经营腿（火电电价半管制 + 煤价周期；备选篮 6 撤销，A17）；`check_r`；零增长 → 10×；2026-09-20
    'g2': 0.0,  # 永续增长 = 0：留存三桶（A17）——ROE_M ≈ r，增长 capex NPV ≈ 0，留存不加不减 = flat \(1/r\)；cap = min(6%, r − 4%) = 6%；`check_g_cap`；2026-09-20
    'capex_fy25': 32.0,  # FY2025 资本开支（亿元），vs D&A 24 → 建设窗口收尾（A17 三桶）；FY2025
    'capex_fy22_24': 59.0,  # FY2022–24 资本开支均值（56 / 65 / 56 亿）vs D&A 15–21 → 新机组建设窗口（债务融资），第二桶，NPV ≈ 0（A17）；FY2022–24
    'pe_m': 10.0,  # 主尺倍数 = 1/r，三档 flat（A3）；eval 断言 = 1/r_perp；仓库级
    'eps_9m_26': 0.491,  # 2026 前三季度实测基本 EPS（三季报；Q3 单季 0.1271、扣非 0.1234；已含 165 容量标准与同一控制下合并追溯）；2026-09-30
    'eps_ttm': 0.5992,  # TTM EPS = 2025Q4 0.1082（追溯前）+ 2026 9M 0.4910；**坐标，不入公式**（当期 ÷ 中枢 0.82，A2）；2026-09-30
    'eps_fy26e': 0.79,  # FY2026E 单点共识（Longbridge `forecast-eps` 2026-09-13 起，n=1）；**坐标**（中性带 PE 读数，A12）；2026-09-13
    'eps_fy25': 0.9484,  # FY2025 实测 EPS（归母 21.49 亿；煤 703 年）；方法 A / C 输入；FY2025
    'eps_fy24': 0.9087,  # FY2024 实测 EPS（归母 20.64 亿；煤 855 年）；方法 A / C 输入；FY2024
    'eps_fy23': 0.6308,  # FY2023 实测 EPS（归母 14.30 亿；煤 965 年）；方法 C 输入、桥回代；FY2023
    'eps_fy22': 0.2201,  # FY2022 实测 EPS（归母 4.99 亿；煤 1,268 尖峰年）；方法 C 输入、`deep_discount` 压力坐标；FY2022
    'coal_q4_26': 1000.0,  # 2026Q4 挤压年煤价假设 = 2026-10 现货平台（秦皇岛 5500 山西产平仓价 10-10 1,003 / 10-13 1,013，Wind 经金融界；第二家 4Q26 1,000；A8）；2026-10-13
    'tariff_fy22': 466.5,  # FY2022 平均上网电价 含税 元/MWh（2023 年报上年列）；滞后联动五对之一（对 coal_fy2021）；FY2022
    'tariff_fy23': 455.6,  # FY2023 平均上网电价（2024 年报上年列；对 coal_fy2022）；FY2023
    'tariff_fy24': 449.1,  # FY2024 平均上网电价（年报；对 coal_fy2023）；FY2024
    'tariff_fy25': 424.8,  # FY2025 平均上网电价（年报；对 coal_fy2024）；L 世界 H2 桥的电价（A8）；FY2025
    'tariff_fy26_impl': 430.0,  # FY2026 电价，2026H1 收入 / 成本恒等式反解 428–436 取整（对 coal_fy2025）；**`待补` 公司经营数据公告**（A5）；2026H1
    'tariff_m': 437.0,  # **M** 世界追平电价 = 五对滞后联动拟合在 coal_m 处（437.0，A5）；拟合
    'coal_fy2026e': 845.0,  # 2026 年均煤价追踪 = 轴「FY2026 全年追踪 ≈ 830–855」中值（H1 实测 772 + H2 ~920）；H 世界电价的自变量（A5）；轴 2026-09-15
    'tariff_h': 440.0,  # **H** 世界上签电价 = tariff_fy26_impl + 三对（FY2024–26）斜率 0.0663 × (coal_fy2026e − 703) = 439.4（A5 / A9）；FY2023–26 均值 439.9 互证；拟合
    'tariff_bench': 384.4,  # 安徽燃煤基准电价 元/MWh（含税）；政策
    'tariff_cap': 461.0,  # 市场化电价顶格 = 1.2 × 基准 = 461.3（A5）；政策
    'sales_fy23': 482.2,  # FY2023 上网电量 亿 kWh（年报）；桥回代；FY2023
    'sales_fy24': 567.0,  # FY2024 上网电量 亿 kWh；FY2024
    'sales_fy25': 585.6,  # FY2025 上网电量 亿 kWh；亦为中枢结构电量（A4）；FY2025
    'gen_fy23': 512.6,  # FY2023 发电量 亿 kWh；FY2023
    'gen_fy24': 601.5,  # FY2024 发电量 亿 kWh；FY2024
    'gen_fy25': 622.1,  # FY2025 发电量 亿 kWh；亦为中枢结构电量；FY2025
    'assoc_fy23': 11.9,  # FY2023 对联营企业投资收益 亿元（神皖 49% 为主；年报）；FY2023
    'assoc_fy24': 12.22,  # FY2024 对联营企业投资收益 亿元；FY2024
    'assoc_fy25': 8.18,  # FY2025 对联营企业投资收益 亿元；FY2025
    'resid_m': 14.38,  # 发电收入残差 亿元 = FY2025 发电收入 234.52 − 424.8/1.13 × 585.6（含容量电价 100 标准；A4 / A6）；FY2025
    'nf_kwh': 0.0917,  # 非燃料发电成本 元/kWh（FY2025 发电成本 193.25 − 原材料 136.23）÷ 622.1；FY2025
    'gp_other': 3.31,  # 发电以外分部毛利 亿元（煤炭贸易 + 运输 + 垃圾；FY2023–25 均值）；FY2023–25
    'opex_m': 15.79,  # 期间费用 + 税金及附加 亿元（FY2025）；FY2025
    'misc_m': 0.67,  # 杂项 亿元（其他收益 + 非联营投资收益 + 减值 + 处置 + 营业外净；FY2023–25 均值）；FY2023–25
    'tax_op': 0.2,  # 经营利润（剔联营）有效税率；FY2024–25
    'par_op': 0.5,  # 归母占经营净利（剔联营）；FY2023–25 均值 48.7%（属性 D）；FY2023–25
    'cap_tariff_2025': 100.0,  # 容量电价 元/kW·年 2024–25 标准（已含在 resid_m 内，A6）；1501 号文
    'cap_tariff_2026': 165.0,  # 容量电价 元/kW·年 2026 起（A6）；1501 号文
    'cap_gw_coal': 15.0,  # 煤电装机 GW（容量电价基数；**`待核` 年报装机表精确值**，A6）；2025 年报
    'dps_fy25': 0.379,  # FY2025 每股派息 CNY（2026-07-16 实施）；派息率分子、D0 股息尺（A14）；FY2025
    'ni_fy25': 21.49,  # FY2025 归母净利润**亿元**（年报）；派息率分母；FY2025
    'pb_lo': 0.68,  # own-year PB 实测低沿（FY2022）；地板 = pb_lo × bps（A8）；FY2022
    'pe_own_min': 7.55,  # 自身 5 年月频 TTM PE 实测下沿（2026-01）；Longbridge `valuation --history`；护栏；2021-10~2026-09
    'pe_own_max': 36.36,  # 自身 5 年月频 TTM PE 实测上沿（2023-06）；护栏；2021-10~2026-09
    'pe_ownyear_l': 21.97,  # FY2022 own-year PE 实测点（尖峰年）；**坐标，不入公式**；FY2022
    'pe_ownyear_m': 9.11,  # own-year PE 四年年均值中位；**坐标**；FY2022–25
    'pe_ownyear_h': 7.91,  # FY2025 own-year PE 实测点；**坐标**；FY2025
    'pe_same_n': 10.0,  # 同等盈利月份数：月末可见 TTM ∈ 中枢 ±12%（0.634–0.806）的月份 = 2024-04~07（TTM 0.7569）+ 2024-10~2025-03（0.7526）；Longbridge 季度 EPS × 月 K（对账 ④）；2024-04~2025-03
    'px_same_lo': 7.19,  # 同等盈利月份收盘最低（2025-01）；2025-01
    'px_same_hi': 8.86,  # 同等盈利月份收盘最高（2024-07）；2024-07
    'px_same_med': 7.86,  # 同等盈利月份收盘中位（对账 ④）；2024-04~2025-03
    'pe_same_med': 10.4,  # 同等盈利月份 PE 中位（收盘 ÷ 可见 TTM 10.44；Longbridge 月频 PE 中位 10.38）；对 pe_m 的护栏；2024-04~2025-03
    'peer_zjn_px': 5.04,  # 浙能电力 600023 收盘（同日，对账 ⑤）；2026-09-14
    'peer_zjn_dps': 0.33,  # 浙能 FY2025 每股派息 = 末期 0.28（2026-07）+ 中期 0.05（2025-10）；Longbridge dividend；FY2025
    'peer_hd_px': 4.93,  # 华电国际 600027 收盘（同日）；2026-09-14
    'peer_hd_dps': 0.23,  # 华电 FY2025 每股派息 = 末期 0.14（2026-06）+ 中期 0.09（2025-11）；FY2025
}
FORMULA_ID = "wanneng_coal_axis_midcycle_pe_v5"
TIERS = ("l", "m", "h")
YI = 1e8
VAT = 1.13

FLOOR_RECHECK_RATIO = 0.30   # A2e-1: below this the earnings ruler has failed at L
BRIDGE_TOL = 0.20            # axis 4c-1: realised-year reproduction
RECON_TOL = 0.20             # 纠正对账门: a coordinate "agrees" within this
EPS_TOL = 0.005              # stated tier EPS vs re-derived (2-dp inputs)
# Rejected rulers, kept as reconciliation coordinates (对账 ①).
M_V3_TTM, M_V4_FROZEN = 8.50, 3.78
HISTORICAL_DATES = {'historical_financial_statement_as_of': '2026-09-30',
                    'historical_research_as_of': '2026-10-23',
                    'historical_valuation_as_of': '2026-09-30',
                    'historical_framework_as_of': '2026-10-23'}
HISTORICAL_LEVERAGE = {'year': 2025, 'net_debt_cny_100m': 406.0,
                       'net_debt_ebitda': 6.5, 'interest_ebit': .21,
                       'midcycle_leverage_status': 'unavailable',
                       'interest_up_100bp_sensitivity_status': 'unavailable'}
HISTORICAL_REVIEW_FLAGS = ['historical_leverage_gate_triggered',
                           'midcycle_leverage_and_roic_unverified',
                           'deleveraging_and_ev_comparison_incomplete']

REQUIRED = [
    "shares", "bps", "equity", "r_perp", "g2", "pe_m",
    "eps_9m_26", "eps_ttm", "eps_fy26e",
    "eps_fy25", "eps_fy24", "eps_fy23", "eps_fy22",
    "coal_l", "coal_m", "coal_h", "coal_m_lo", "coal_m_hi", "coal_q4_26", "coal_fy2026e",
    "coal_fy2019", "coal_fy2020", "coal_fy2021", "coal_fy2022", "coal_fy2023", "coal_fy2024", "coal_fy2025",
    "uf_a", "uf_b",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_fy26_impl",
    "tariff_m", "tariff_h", "tariff_bench", "tariff_cap", "sales_fy23", "sales_fy24", "sales_fy25", "gen_fy23", "gen_fy24", "gen_fy25",
    "assoc_fy23", "assoc_fy24", "assoc_fy25", "resid_m", "nf_kwh", "gp_other", "opex_m", "misc_m", "tax_op", "par_op",
    "cap_tariff_2025", "cap_tariff_2026", "cap_gw_coal", "dps_fy25", "ni_fy25", "pb_lo", "pe_own_min", "pe_own_max", "pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h",
    "pe_same_n", "px_same_lo", "px_same_hi", "px_same_med", "pe_same_med",
    "peer_zjn_px", "peer_zjn_dps", "peer_hd_px", "peer_hd_dps",
]


# --- the bridge --------------------------------------------------------------
def uf(inp: dict[str, float], coal: float) -> float:
    """Unit fuel cost CNY/kWh from the axis §4a line (皖能 fit)."""
    return inp["uf_a"] + inp["uf_b"] * coal


def assoc_fit(inp: dict[str, float], tariff: float, coal: float) -> float:
    """神皖 49% associate income, 亿元, from the FY2023-25 exact fit."""
    return inp["assoc_a"] + inp["assoc_b"] * tariff + inp["assoc_c"] * coal


def cap_uplift_yi(inp: dict[str, float], cap_std: float) -> float:
    """Pretax capacity-tariff uplift over the FY2025 standard, 亿元: the FY2025
    residual already carries the 100 CNY/kW-yr standard, so only the delta is
    added (GW x CNY/kW x 1e6 / 1e8)."""
    return (cap_std - inp["cap_tariff_2025"]) * inp["cap_gw_coal"] * 1e-2


def bridge_eps(
    inp: dict[str, float], coal: float, tariff: float, cap_std: float,
    sales: float, gen: float, assoc_yi: float, frac: float = 1.0,
) -> float:
    """EPS from the income-statement bridge (亿元 -> CNY/share); `frac` scales
    the period (0.5 = a half year, structure parameters halved with it)."""
    shares_yi = inp["shares"] / YI
    power_rev = tariff / VAT * sales * frac / 1000 + (inp["resid_m"] + cap_uplift_yi(inp, cap_std)) * frac
    fuel = uf(inp, coal) * gen * frac
    pbt_op = power_rev - fuel - inp["nf_kwh"] * gen * frac + (inp["gp_other"] - inp["opex_m"] + inp["misc_m"]) * frac
    parent = pbt_op * (1.0 - inp["tax_op"]) * inp["par_op"] + assoc_yi * frac
    return parent / shares_yi


def world_eps(inp: dict[str, float], coal: float, tariff: float, cap_std: float, frac: float = 1.0) -> float:
    """A tier world: the bridge on FY2025 volumes with the associate fit."""
    return bridge_eps(inp, coal, tariff, cap_std, inp["sales_fy25"], inp["gen_fy25"],
                      assoc_fit(inp, tariff, coal), frac)


def midcycle_readings(inp: dict[str, float], coal_m: float, cap_std: float, eps_squeeze: float) -> dict[str, float]:
    """The five cross-cycle readings whose mean is E_M (A / B x2 / C x2)."""
    uplift = cap_uplift_yi(inp, cap_std) * (1.0 - inp["tax_op"]) * inp["par_op"] / (inp["shares"] / YI)
    fat = ((inp["eps_fy24"] + uplift) + (inp["eps_fy25"] + uplift)) / 2.0
    realised = [inp["eps_fy22"], inp["eps_fy23"], inp["eps_fy24"], inp["eps_fy25"]]
    return {
        "A 一个滞后波（肥年 FY24/25 归一到 165 + 挤压年 2026E，等权）": (fat + eps_squeeze) / 2.0,
        "B 桥稳态 煤 830 + 电价追平 437 + 容量 165": world_eps(inp, coal_m, inp["tariff_m"], cap_std),
        "B' 桥稳态 电价 430（2026 隐含）": world_eps(inp, coal_m, inp["tariff_fy26_impl"], cap_std),
        "C 改革后实测均值 FY2022–25": statistics.mean(realised),
        "C' 同上含 2026E": (sum(realised) + eps_squeeze) / 5.0,
    }


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """(intercept, slope) least squares."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - slope * mx, slope


def solve3(rows: list[tuple[float, float, float]], rhs: list[float]) -> tuple[float, float, float]:
    """Cramer's rule for the 3x3 associate fit (a + b x tariff + c x coal)."""
    def det(m: list[tuple[float, float, float]]) -> float:
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(rows)
    cols = []
    for j in range(3):
        m = [tuple(rhs[i] if k == j else rows[i][k] for k in range(3)) for i in range(3)]
        cols.append(det(m) / d)
    return cols[0], cols[1], cols[2]


def anchors_of(inp: dict[str, float], eps_l: float, eps_m: float, eps_h: float) -> tuple[float, float, float]:
    """L = max(scenario, PB floor) (A2e-1 floor allowed, both reported); M/H flat at pe_m."""
    floor = inp["pb_lo"] * inp["bps"]
    return max(eps_l * inp["pe_m"], floor), eps_m * inp["pe_m"], eps_h * inp["pe_m"]


def _historical_calculation(raw, coal):
    errors = check_missing(raw, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(not math.isfinite(raw[k]) for k in REQUIRED):
        raise ValueError('all required inputs must be finite')
    inp = dict(raw)
    baskets = {'r_perp': 4}
    r = inp['r_perp']
    errors += check_r(r, 'r_perp', 4)
    if errors:
        raise ValueError('; '.join(errors))
    shares_yi = inp['shares'] / YI
    # Original research fits associate profits to 2023–2025 electricity and
    # coal prices, then uses the displayed precision (-101.92, .2926, -.0202).
    # These coefficients are derived, not another source of model input.
    fit_years = (2023, 2024, 2025)
    coef = solve3([(1., inp[f'tariff_fy{y%100:02d}'], inp[f'coal_fy{y}']) for y in fit_years],
                  [inp[f'assoc_fy{y%100:02d}'] for y in fit_years])
    inp['assoc_a'], inp['assoc_b'], inp['assoc_c'] = round(coef[0], 2), round(coef[1], 4), round(coef[2], 4)
    # The original study adopted 437 / 440 as rounded tariff scenarios and
    # required them to remain close to its fit. Preserve both choices and the
    # guard; the source does not define an updating rounding rule.
    # The original ruler intentionally rounded the three model-derived EPS to
    # two decimals before capitalising; retain that historical convention.
    q4_derived = world_eps(inp, inp['coal_q4_26'], inp['tariff_fy25'], inp['cap_tariff_2026'], frac=.25)
    squeeze_derived = inp['eps_9m_26'] + q4_derived
    reads_derived = midcycle_readings(inp, inp['coal_m'], inp['cap_tariff_2026'], squeeze_derived)
    eps = {'l': round(squeeze_derived,2), 'm': round(statistics.mean(reads_derived.values()),2),
           'h': round(world_eps(inp, inp['coal_m'], inp['tariff_h'], inp['cap_tariff_2026']),2)}
    inp['eps_m_lo'], inp['eps_m_hi'] = round(min(reads_derived.values()),2), round(max(reads_derived.values()),2)
    # Shared axis is authoritative: generator tiers are the reversed coal
    # scenario order; annual series and fitted coordinates arrive in the same
    # versioned axis snapshot. No prose or second local copy is read here.
    series = coal["series"]
    uf_axis = coal["coordinates"]["uf_reference"]
    # These three observed fuel-cost references belong to their original
    # historical price coordinates, not whichever axis scenarios are current.
    uf_reference_prices = coal["coordinates"]["uf_reference_prices"]
    uf_own = tuple(uf(inp, price) for price in uf_reference_prices)
    for price, got, want in zip(uf_reference_prices, uf_own, uf_axis):
        if abs(got - want) > 0.0005:
            errors.append(f"uf({price:g}) {got:.4f} vs axis §4a {want:.4f} (axis 4c-2, ±0.0005)")
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    if not (inp["coal_l"] > inp["coal_m"] > inp["coal_h"]):
        errors.append("coal ladder must fall as earnings rise (generator reads the axis mirrored)")
    if errors:
        raise ValueError('; '.join(errors))
    pass

    # --- Step 2: the bridge must reproduce the realised years (axis 4c-1) ----
    years = {
        "FY2023": (inp["coal_fy2023"], inp["tariff_fy23"], inp["sales_fy23"], inp["gen_fy23"], inp["assoc_fy23"], inp["eps_fy23"]),
        "FY2024": (inp["coal_fy2024"], inp["tariff_fy24"], inp["sales_fy24"], inp["gen_fy24"], inp["assoc_fy24"], inp["eps_fy24"]),
        "FY2025": (inp["coal_fy2025"], inp["tariff_fy25"], inp["sales_fy25"], inp["gen_fy25"], inp["assoc_fy25"], inp["eps_fy25"]),
    }
    pass
    passed = 0
    for name, (coal, tariff, sales, gen, assoc_yi, actual) in years.items():
        e = bridge_eps(inp, coal, tariff, inp["cap_tariff_2025"], sales, gen, assoc_yi)
        err = e / actual - 1.0
        ok = abs(err) <= BRIDGE_TOL
        passed += ok
        pass
        if not ok:
            errors.append(f"bridge {name}: {e:.4f} vs {actual} ({err:+.1%}) outside ±{BRIDGE_TOL:.0%} — 桥错, BLOCKED (axis 4c-1)")
    if passed < 2:
        errors.append(f"bridge reproduces only {passed} realised year(s); axis 4c-1 needs >= 2")
    # The associate fit is the exact solution through the three realised points.
    a, b, c = solve3([(1.0, y[1], y[0]) for y in years.values()], [y[4] for y in years.values()])
    if abs(a - inp["assoc_a"]) > 0.05 or abs(b - inp["assoc_b"]) > 0.0005 or abs(c - inp["assoc_c"]) > 0.0005:
        errors.append(f"assoc fit re-solved {a:.2f} / {b:.4f} / {c:.4f} vs stated {inp['assoc_a']} / {inp['assoc_b']} / {inp['assoc_c']}")
    pass
    # Tariff second layer: lag-linkage fit (coal_{t-1} -> tariff_t) and the cap.
    pairs = [(inp["coal_fy2021"], inp["tariff_fy22"]), (inp["coal_fy2022"], inp["tariff_fy23"]),
             (inp["coal_fy2023"], inp["tariff_fy24"]), (inp["coal_fy2024"], inp["tariff_fy25"]),
             (inp["coal_fy2025"], inp["tariff_fy26_impl"])]
    t0, t1 = ols([p[0] for p in pairs], [p[1] for p in pairs])
    tariff_m_fit = t0 + t1 * inp["coal_m"]
    if abs(inp["tariff_m"] - tariff_m_fit) > 1.0:
        errors.append(f"tariff_m {inp['tariff_m']} vs lag fit at coal {inp['coal_m']:g}: {tariff_m_fit:.1f}")
    # H tariff = the 2027 contract signed on 2026's coal: the post-spike slope
    # (FY2024-26 pairs, no capped year) applied from the FY2026 base.
    _, t1_3 = ols([p[0] for p in pairs[2:]], [p[1] for p in pairs[2:]])
    tariff_h_lag = inp["tariff_fy26_impl"] + t1_3 * (inp["coal_fy2026e"] - inp["coal_fy2025"])
    tariff_mean_post = statistics.mean([inp["tariff_fy23"], inp["tariff_fy24"], inp["tariff_fy25"], inp["tariff_fy26_impl"]])
    if abs(inp["tariff_h"] - tariff_h_lag) > 1.0:
        errors.append(f"tariff_h {inp['tariff_h']} vs 2027-on-2026-coal lag {tariff_h_lag:.1f}")
    if abs(inp["tariff_cap"] - 1.2 * inp["tariff_bench"]) > 0.5:
        errors.append(f"tariff_cap {inp['tariff_cap']} != 1.2 x benchmark {inp['tariff_bench']}")
    pass
    # Per-unit sensitivities of the bridge at the mid-cycle world.
    base = world_eps(inp, inp["coal_m"], inp["tariff_fy25"], inp["cap_tariff_2025"])
    k_tariff = world_eps(inp, inp["coal_m"], inp["tariff_fy25"] + 1.0, inp["cap_tariff_2025"]) - base
    k_coal10 = world_eps(inp, inp["coal_m"] + 10.0, inp["tariff_fy25"], inp["cap_tariff_2025"]) - base
    uplift_eps = cap_uplift_yi(inp, inp["cap_tariff_2026"]) * (1.0 - inp["tax_op"]) * inp["par_op"] / shares_yi
    pass
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 3: tier numerators from the lag wave -----------------------------
    q4 = world_eps(inp, inp["coal_q4_26"], inp["tariff_fy25"], inp["cap_tariff_2026"], frac=0.25)
    squeeze = inp["eps_9m_26"] + q4
    e_h = world_eps(inp, inp["coal_m"], inp["tariff_h"], inp["cap_tariff_2026"])
    reads = midcycle_readings(inp, inp["coal_m"], inp["cap_tariff_2026"], squeeze)
    e_m = statistics.mean(reads.values())
    lo, hi = min(reads.values()), max(reads.values())
    pass
    pass
    for k, v in reads.items():
        pass
    pass
    pass
    pass
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 4: the multiple — flat 1/r; Gordon and DDM are crosses ---------
    roe_m = eps["m"] * inp["shares"] / (inp["equity"] * YI)
    payout_fy25 = inp["dps_fy25"] * inp["shares"] / (inp["ni_fy25"] * YI)
    g_policy = (1.0 - payout_fy25) * roe_m
    inp['payout_fy25'] = round(payout_fy25, 2)
    inp['g2_policy'] = round(g_policy, 4)
    errors += check_g_cap(inp["g2"], r, "g2")
    if abs(inp["g2"]) > 1e-9:
        errors.append(f"g2 {inp['g2']} != 0 — the main ruler is flat 1/r (growth capex NPV ~ 0, A17)")
    if abs(inp["pe_m"] - 1.0 / (r - inp["g2"])) > 1e-9:
        errors.append(f"pe_m {inp['pe_m']} != 1/(r − g2) {1 / (r - inp['g2']):.2f} — the main ruler is flat E/r")
    if abs(payout_fy25 - inp["payout_fy25"]) > 0.005:
        errors.append(f"payout_fy25 {inp['payout_fy25']} vs DPS x shares / NI = {payout_fy25:.4f}")
    if abs(g_policy - inp["g2_policy"]) > 0.0005:
        errors.append(f"g2_policy {inp['g2_policy']} vs (1 − {payout_fy25:.3f}) × ROE_M {roe_m:.4f} = {g_policy:.4f}")
    errors += check_g_cap(inp["g2_policy"], r, "g2_policy")
    errors += check_branch(inp["g2_policy"], roe_m, r, payout_fy25, "g2_policy")
    pe_gordon = perpetual_pe(inp["g2_policy"], roe_m, r)
    if abs(capped_payout_pe(g_policy, roe_m, r, payout_fy25) - perpetual_pe(g_policy, roe_m, r)) > 1e-9:
        errors.append("capped_payout_pe != perpetual_pe — policy g crossed the cap, the dividend ruler would apply")
    d_m = payout_fy25 * eps["m"]
    ddm_m = d_m * (1.0 + inp["g2_policy"]) / (r - inp["g2_policy"])
    modelled, gap = payout_gap(inp["g2_policy"], roe_m, payout_fy25)
    regime = "病态区" if abs(roe_m - r) < 0.03 else ("峰形区" if roe_m < r else "单调区")
    pass
    pass
    pass
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 5: anchors, floor, interval re-pricing -------------------------
    floor = inp["pb_lo"] * inp["bps"]
    scenario_l = eps["l"] * inp["pe_m"]
    L, M, H = anchors_of(inp, eps["l"], eps["m"], eps["h"])
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
        raise ValueError('; '.join(errors))
    if scenario_l / M <= FLOOR_RECHECK_RATIO:
        errors.append(f"scenario_L/M = {scenario_l / M:.3f} <= {FLOOR_RECHECK_RATIO} — earnings ruler failed at L, A2e-1 回问")
    A, B = cut_points(L, M, H)
    winner = "地板胜出" if floor > scenario_l else "情景胜出"
    pass
    pass
    # The E_M evidence interval and the axis M window (axis 4c-5), re-priced
    # and printed (disclosure — the doc states no zone to hold them to).
    for tag, em in (("eps_m_lo", inp["eps_m_lo"]), ("eps_m_hi", inp["eps_m_hi"])):
        b = anchors_of(inp, eps["l"], em, eps["h"])
        a_, b_ = cut_points(*b)
        pass
    for cm in (inp["coal_m_lo"], inp["coal_m_hi"]):
        em = statistics.mean(midcycle_readings(inp, cm, inp["cap_tariff_2026"], squeeze).values())
        eh = world_eps(inp, cm, inp["tariff_h"], inp["cap_tariff_2026"])
        b = anchors_of(inp, eps["l"], em, eh)
        a_, b_ = cut_points(*b)
        pass
    # Sensitivities (printed, not asserted): tariff, capacity, TTM as numerator.
    for t in (inp["tariff_fy26_impl"], inp["tariff_m"], inp["tariff_h"]):
        em = world_eps(inp, inp["coal_m"], t, inp["cap_tariff_2026"])
        m_t = em * inp["pe_m"]
        pass
    sq100 = inp["eps_9m_26"] + world_eps(inp, inp["coal_q4_26"], inp["tariff_fy25"], inp["cap_tariff_2025"], frac=0.25)
    em100 = statistics.mean(midcycle_readings(inp, inp["coal_m"], inp["cap_tariff_2025"], sq100).values())
    eh100 = world_eps(inp, inp["coal_m"], inp["tariff_h"], inp["cap_tariff_2025"])
    b100 = anchors_of(inp, sq100, em100, eh100)
    pass
    m_ttm = inp["eps_ttm"] * inp["pe_m"]
    pass
    # Basket-r disclosures (printed, not asserted): g2 ±1pp, r ±50bp and the
    # alternative baskets the framework rejected (A17).
    for tag, rr, gg in (("g2 +1pp", r, 0.01), ("g2 −1pp", r, -0.01), ("r −50bp", r - 0.005, 0.0), ("r +50bp", r + 0.005, 0.0),
                        ("篮 2 7.5%", 0.075, 0.0), ("篮 6 13%", 0.13, 0.0)):
        pe_x = 1.0 / (rr - gg)
        b = (max(eps["l"] * pe_x, floor), eps["m"] * pe_x, eps["h"] * pe_x)
        pass
    flat_errs, flat = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), inp["pe_m"])
    errors += flat_errs
    pass
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 6: 纠正对账门 (valuation-rules 2026-09-15) ---------------------
    g_zjn = (inp["peer_zjn_px"] * r - inp["peer_zjn_dps"]) / (inp["peer_zjn_px"] + inp["peer_zjn_dps"])
    g_hd = (inp["peer_hd_px"] * r - inp["peer_hd_dps"]) / (inp["peer_hd_px"] + inp["peer_hd_dps"])
    g_peer = statistics.median([g_zjn, g_hd])
    peer_d0 = inp["dps_fy25"] * (1.0 + g_peer) / (r - g_peer)
    peer_dm = d_m * (1.0 + g_peer) / (r - g_peer)
    rows = [
        ("① 上一版 M（v3，TTM 作中枢）", M_V3_TTM, True),
        ("①' v4 M（冻结电价的桥，已废，只报不计）", M_V4_FROZEN, False),
        ("② E_M / r", eps["m"] / r, True),
        (f"③ 股息尺 D_M {d_m:.3f} × (1+g) ÷ (r−g)，g = 政策 {inp['g2_policy']:.2%}", ddm_m, True),
        (f"④ 同等盈利月份实付价中位（可见 TTM ∈ 中枢 ±12%，n = {inp['pe_same_n']:g}，价 {inp['px_same_lo']}–{inp['px_same_hi']}，PE 中位 {inp['pe_same_med']}×）", inp["px_same_med"], True),
        (f"⑤ 同业同尺同日：浙能 / 华电 D0 尺反解 g_d {g_zjn:.2%} / {g_hd:.2%} 中位 {g_peer:.2%} → 皖能 D0 {inp['dps_fy25']}", peer_d0, True),
        (f"⑤' 同上配中枢股息 D_M {d_m:.3f}（跨口径：同业 g_d 从当期股息反解，只报不计）", peer_dm, False),
    ]
    pass
    outside = counted = 0
    for label, v, counts in rows:
        dev = M / v - 1.0
        pass
        if counts:
            counted += 1
            outside += abs(dev) > RECON_TOL
    m_pb = M / inp["bps"]
    pass
    if m_pb < inp["pb_lo"]:
        errors.append(f"M/BPS {m_pb:.2f} below the own PB low {inp['pb_lo']} — 尺错 signal")
    if outside == counted:
        errors.append(f"new M outside every reconciliation coordinate by >{RECON_TOL:.0%} — BLOCKED")
    if abs(inp["pe_same_med"] - inp["pe_m"]) / inp["pe_m"] > RECON_TOL:
        errors.append(f"pe_same_med {inp['pe_same_med']} vs pe_m {inp['pe_m']}: the market paid a different multiple on ≈ mid-cycle earnings")
    band = {"中枢": eps["m"], "TTM": inp["eps_ttm"], "FY26E": inp["eps_fy26e"]}
    pass
    if B / inp["eps_ttm"] <= 7.0:
        errors.append(f"neutral band tops out at {B / inp['eps_ttm']:.1f}× TTM on a 40%-payout utility — 荒诞信号 (valuation-rules「纠正对账门」)")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 7: coordinates outside the band and the stated outputs ----------
    d = decompose((L, M, H), (inp["pe_m"],) * 3)
    pass
    pass
    perm = world_eps(inp, inp["coal_m"], inp["tariff_fy25"], inp["cap_tariff_2025"])
    spike_new = inp["eps_fy22"] + inp["cap_tariff_2026"] * inp["cap_gw_coal"] * 1e-2 * (1.0 - inp["tax_op"]) * inp["par_op"] / shares_yi
    pass
    bull = world_eps(inp, inp["coal_h"], inp["tariff_h"], inp["cap_tariff_2026"])
    pass

    if errors:
        raise ValueError('; '.join(errors))
    bands = lambda values: dict(zip('LMH', values))
    sensitivity = {'capacity_2025': bands(b100), 'ttm_mid': m_ttm,
                   'pb_floor': floor, 'no_lag_pressure': perm*inp['pe_m'],
                   'coal_extreme': bull*inp['pe_m'], 'flat': bands(flat),
                   'midcycle_low': bands(anchors_of(inp, eps['l'], inp['eps_m_lo'], eps['h'])),
                   'midcycle_high': bands(anchors_of(inp, eps['l'], inp['eps_m_hi'], eps['h']))}
    for name, cm in (('coal_window_low', inp['coal_m_lo']), ('coal_window_high', inp['coal_m_hi'])):
        em = statistics.mean(midcycle_readings(inp, cm, inp['cap_tariff_2026'], squeeze).values())
        eh = world_eps(inp, cm, inp['tariff_h'], inp['cap_tariff_2026'])
        sensitivity[name] = bands(anchors_of(inp, eps['l'], em, eh))
    for name, tariff in (('tariff_current', inp['tariff_fy26_impl']),
                         ('tariff_mid', inp['tariff_m']), ('tariff_high', inp['tariff_h'])):
        sensitivity[name] = world_eps(inp, inp['coal_m'], tariff, inp['cap_tariff_2026'])*inp['pe_m']
    for name, rr, gg in (('growth_plus_1pp',r,.01), ('growth_minus_1pp',r,-.01),
                         ('discount_minus_05pp',r-.005,0), ('discount_plus_05pp',r+.005,0),
                         ('basket_2',.075,0), ('basket_6',.13,0)):
        pe_x = 1/(rr-gg)
        sensitivity[name] = bands((max(eps['l']*pe_x,floor), eps['m']*pe_x, eps['h']*pe_x))
    return {
        'ticker': '000543.SZ', 'currency': 'CNY', 'valuation_as_of': None, 'framework_as_of': None,
        'anchors': dict(zip('LMH', (L,M,H))), 'candidate': None, 'option': None,
        'segments': {'company': {'values': dict(zip('LMH', (L,M,H)))}},
        # L is an actual PB floor, not an earnings-model multiple.
        'key_parameters': {'method': {'L': 'historical_pb_floor', 'M': 'zero_growth_earnings', 'H': 'zero_growth_earnings'},
                           'discount_rate': {'L': None, 'M': r, 'H': r},
                           'growth_rate': {'L': None, 'M': inp['g2'], 'H': inp['g2']},
                           'forward_return': {'L': None, 'M': roe_m, 'H': None},
                           'steady_return': {'L': None, 'M': None, 'H': None}},
        'operating': {'eps': dict(zip('LMH', (eps['l'],eps['m'],eps['h']))), 'floor': floor,
                      'squeeze': squeeze, 'q4': q4, 'bridge_h': e_h, 'midcycle': e_m,
                      'midcycle_readings': list(reads.values()), 'coal_series': series,
                      'assoc_coefficients': [inp['assoc_a'],inp['assoc_b'],inp['assoc_c']],
                      'tariff_mid': inp['tariff_m'], 'tariff_high': inp['tariff_h'],
                      'tariff_delta_1': k_tariff, 'coal_delta_10': k_coal10, 'capacity_uplift_eps': uplift_eps,
                      'reconciliation_outside': outside, 'reconciliation_count': counted},
        'sensitivity': sensitivity,
    }


def evaluate(inp, coal):
    # Preserve the old valuation while disclosing the old leverage finding;
    # migration does not imply that ROIC, debt reduction or EV were checked.
    result = _historical_calculation(inp, coal)
    result['historical_financial_statement_as_of'] = HISTORICAL_DATES['historical_financial_statement_as_of']
    result['historical_research_as_of'] = HISTORICAL_DATES['historical_research_as_of']
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    params = result['key_parameters']
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        params[name] = {'unit': 'RATIO', 'values': params[name]}
    result['review_flags'] = list(HISTORICAL_REVIEW_FLAGS)
    return result



def calculate(context):
    coal = context['axes']['coal']
    if coal.get('side') != 'generator' or coal.get('mount') != 'reference':
        raise ValueError('coal axis role must be the historical generator reference')
    coord = coal['coordinates']
    window = coal['mid_window']
    # Generator tiers reverse the miner/commodity ladder. Use the actual axis
    # values, not the historic 965/830/703 copies formerly in this file.
    shared = {**{f'coal_{tier.lower()}': coal['tier_prices'][tier] for tier in 'LMH'},
              **{f'coal_fy{year}': value for year, value in coal['series'].items()},
              'coal_m_lo': window['low'], 'coal_m_hi': window['high'],
              'uf_a': coord['uf_a'], 'uf_b': coord['uf_b']}
    result = evaluate({**INPUTS, **shared}, coal)
    result['basis_changed'] = None
    coal_fingerprint_input = {key: value for key, value in coal.items() if key != 'axis_metadata'}
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'coal': coal_fingerprint_input, 'coal_axis_version': HISTORICAL_COAL_AXIS_VERSION,
         'constants': {'yi': YI, 'vat': VAT, 'floor_recheck_ratio': FLOOR_RECHECK_RATIO,
                       'bridge_tolerance': BRIDGE_TOL, 'reconciliation_tolerance': RECON_TOL,
                       'eps_tolerance': EPS_TOL, 'previous_m_v3': M_V3_TTM, 'previous_m_v4': M_V4_FROZEN},
         'historical_dates': HISTORICAL_DATES, 'historical_leverage': HISTORICAL_LEVERAGE,
         'historical_review_flags': HISTORICAL_REVIEW_FLAGS},
        HISTORICAL_PARTIAL_FINGERPRINT)
    result['historical_valuation_as_of'] = HISTORICAL_DATES['historical_valuation_as_of']
    result['historical_framework_as_of'] = HISTORICAL_DATES['historical_framework_as_of']
    # Historical FY2025 actual-year comparison, not an as-yet-unobtained
    # midcycle-year leverage ratio or proof that the required reviews passed.
    result['historical_leverage'] = dict(HISTORICAL_LEVERAGE)
    return result
