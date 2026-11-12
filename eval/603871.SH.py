"""Historical Jiayou model; no new research or forecast."""
from __future__ import annotations
import math
from lib.gordon import payout, perpetual_pe
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'zones', 'partial_basis'), 'axes': {'africa': 'africa_corridor'}}
BASELINE_LOCAL = '6dbcc16ed248d90075ff874aa702178b99ae8320b11fa50ab23ebaf4649a8f53'
TIERS = ('l', 'm', 'h')
P_MOKAMBO = (0., .25, 1.)
P_UNSIGNED = (0., 0., 1.)
INPUTS = {
    'shares': 1368008658.0,  # 总股本；Longbridge static（三季报股本 13.68 亿未变）；2026-09-30
    'bps': 4.53,  # 每股净资产 CNY；东方财富 F10 2026 三季报（4.526）；2026-09-30
    'equity': 61.92,  # 归母权益（东方财富 F10 2026 三季报资产负债表）= 中报 62.60 + Q3 归母 3.86 − 已宣派未付中期股息 3.80（每股 0.28，10-23 发放）− 回购 0.18 − 外币折算等其他综合收益约 −0.6；用于每档前瞻 ROE（A15）；2026-09-30
    'r_mgl': 0.1,  # 中蒙 / 其他腿贴现率 = 篮 4 常规经营（降篮门结果，初分篮 6；A4 / A17）；零增长 → 1/r 10×；2026-09-18
    'r_afr': 0.1,  # 非洲通道腿贴现率 = 篮 4 常规经营（降篮门结果，初分篮 7；2026-10-04 按步 1c 复核仍成立；A4 / A17）；永续 Gordon 与 \(V_{opt}\) 折现均按此 r；2026-10-04
    'concession_years': 22.0,  # 莫坎博特许期（含建设期 2 年）；**只作有限期交叉与证伪条件**，不进主公式（A5）；2026-02
    'ni_group_l': 11.41,  # **L** 归母 = FY2025 实测（A1；同花顺 2025 实际值同）；FY2025
    'ni_group_m': 18.0,  # **M** = 同花顺机构一致预测 FY2028 净利润均值（15 家，截至 2026-10-29，6 个月内；A3）；2026-10-29
    'ni_group_h': 20.5,  # **H** = 同一组 FY2028 最大值（15 家同源上沿；出自哪家详表未列，详表可见最高 19.21；A2）；2026-10-29
    'num_year': 2028.0,  # M / H 分子年（FY+2）→ τ = 本行 − `t_base` = 1.25 年，以各腿篮子 r 折回并加窗口可分配利润（A18）；L 为 FY2025 实测当 FY2026 情景，不折；2026-10-04
    't_base': 2026.75,  # 估值基准日 2026-09-30（年份小数，= 三季报资产负债表日）；τ 与 \(V_{opt}\) 折现的起点（A18）；2026-09-30
    'ss_return': 0.257,  # 新投资**稳态回报** = 自身周期（按序取第一层，自身可用即取自身）：投入资本口径（税后经营利润 ÷ 期初权益含少数股东 + 有息负债 + 租赁 − 超额现金），最近一轮谷到谷 FY2021–25 读数 23.2 / 24.5 / 27.9 / 32.6 / 20.4%，均值 25.7%；兜底「有壁垒的重资产」15% 只作对照（A18）；2026-10-19
    'y1_ret': 2028.0,  # 高回报期 Y1 = 可见年末（最远共识年 FY2028）（A18）；2026-10-16
    'y2_ret': 2032.0,  # 高回报期 Y2 = Y1 + 4 年（进入门槛「中」，依据见 A18）；2026-10-16
    'ni_2026_cons': 14.37,  # 同花顺 FY2026 净利润均值（16 家）；账面滚动起点之后尚未入账部分 = 本行 − `ni_ytd_2026`；亦作 ③ 带测试的 EPS 基（带印在 2026 own-year 上）；2026-10-29
    'ni_ytd_2026': 11.17,  # 2026 年初至估值基准日的实测归母 = 前三季度（三季报；Q3 单季 3.86）；2026-09-30
    'ni_2027_m': 16.07,  # 同花顺 FY2027 净利润均值（16 家）；M 档账面滚动；2026-10-29
    'ni_2027_h': 17.64,  # 同花顺 FY2027 最大值（16 家）；H 档账面滚动；2026-10-29
    'w_afr': 0.4,  # 非洲腿利润权重；券商测算（A3，**待补**）；2026H1
    'g2_mgl_l': -0.03,  # **L** 中蒙腿永续增长（A6）：份额红利用完 + 粗钢需求下行；**无同业锚**；派息封顶 → 1/(r−g) 7.69×；2026-06-30 口岸数据
    'g2_mgl_m': 0.0,  # **M** 中蒙腿永续增长（A6）：替代份额抵消需求下行；**无同业锚**；1/r 10.0×；2026-06-30 口岸数据
    'g2_mgl_h': 0.02,  # **H** 中蒙腿永续增长（A6）：口岸扩能 + 继续替代；**无同业锚**；cap = min(6%, r_mgl − 4%) = 6%；2026-06-30 口岸数据
    'ni_ttm': 13.84,  # TTM 归母 = FY2025 11.41 − 前三季度'25 8.74 + 前三季度'26 11.17；仅作对照，**不入主公式**；2026Q3
    'net_cash': 21.75,  # 扩展口径净现金 = 货币资金 17.77 + 理财 8.75 − 短借 3.20 − 一年内到期 0.10 − 租赁 0.17 − 应付债券 1.30（未扣已宣派未付股息 3.80，扣后 17.95）；**不入主公式**（A11 / A18）；2026Q3
    'tp_street': 16.63,  # 卖方共识目标价 CNY（4 家）；仅作交叉校验（A13）；2026-09-06
    'pe_own_hi': 48.2,  # own-year PE 实测上沿；**护栏，不入主公式**；2022
    'pe_own_lo': 10.7,  # own-year PE 实测下沿；**降篮门护栏**（M 倍数 ≥ 此值），不入主公式；2026
    'trade_rev_fy25': 51.74,  # FY2025 供应链贸易收入（亿）；只用于卡萨 NI/GP 分母；FY2025
    'trade_gm_fy25': 0.1047,  # FY2025 贸易毛利率；FY2025
    'logi_rev_fy25': 23.96,  # FY2025 跨境多式联运收入（亿）；只用于卡萨 NI/GP 分母；FY2025
    'logi_gm_fy25': 0.2673,  # FY2025 物流毛利率；FY2025
    'lp_rev_fy25': 6.15,  # FY2025 陆港项目服务收入（亿）；萨卡尼亚尚未收费，口径 = 卡萨；FY2025
    'lp_gm_fy25': 0.5948,  # FY2025 陆港毛利率；FY2025
    't_mokambo': 2028.0,  # 莫坎博口岸 + 道路兑现年 = 2026-02 公告 + 建设期 2 年（具名时点）；\(V_{opt}\) 第一项（A14）；2026-02
    'inv_kasa_musd': 229.0,  # 卡萨（卡松巴莱萨—萨卡尼亚公路 + 干港）总投资 百万美元；actualite.cd 2022-01-21 转述项目方；**只用于莫坎博份数的投资额比**（A14）；2022-01-21
    'inv_mokambo_musd': 56.6569,  # 莫坎博口岸 + 穆富利拉—莫坎博道路投资 百万美元（公告 5,665.69 万美元）；份数 = 本行 ÷ `inv_kasa_musd` × 卡萨实测单位（A14）；2026-02
    't_unsigned': 2030.0,  # 未签约下一条通道兑现年 = 对齐年份 FY2028 + 2，**无时点锚·拍值**；\(V_{opt}\) 第二项（A14）；2026-10-04
    'fx_usdcny': 6.7048,  # USD→CNY；yfinance `USDCNY=X`（与 `6655.HK` 同日）；只用于期权未投资本；2026-10-02
    't_inv_mokambo': 2027.0,  # 莫坎博未投资本的投入年（建设期 2026–2027，取 2027，折到估值基准日 0.25 年，A18）；已投金额未披露，按全额未投、持股按 100%（A14；2026 前三季度全公司资本开支仅 1.15 亿，施工节奏 `待查`）；2026-10-30
    't_inv_unsigned': 2029.0,  # 下一条通道投资的投入年 = 兑现年前一年（拍值）；投资额按卡萨 2.29 亿美元、持股按 100%（A14）；2026-10-04
}

def g_of(inp: dict[str, float], leg: str, tag: str) -> float:
    return inp[f"g2_{leg}_{tag}"]


def model_b(inp: dict[str, float], tag: str, roe: float) -> float:
    """Retention the model needs for its growth: Σ w_i g_i / ROE (g ≤ 0 legs retain 0)."""
    w = inp["w_afr"]
    return ((1 - w) * max(0.0, g_of(inp, "mgl", tag)) + w * max(0.0, g_of(inp, "afr", tag))) / roe


def book(inp: dict[str, float], tag: str) -> float:
    """Start-of-numerator-year 归母 book.  L = base-date equity (FY2025 as the FY2026 case);
    M / H = base-date equity + the rest of FY2026 and FY2027 consensus profit × model b."""
    e = inp["equity"]
    if tag == "l":
        return e
    roe26 = inp["ni_2026_cons"] / e
    e += (inp["ni_2026_cons"] - inp["ni_ytd_2026"]) * model_b(inp, tag, roe26)
    n27 = inp[f"ni_2027_{tag}"]
    e += n27 * model_b(inp, tag, n27 / e)
    return e


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_group_{tag}"] / book(inp, tag)


def disc_years(inp: dict[str, float], tag: str) -> float:
    """时点对齐 tau (A18): base date -> start of the numerator year; L (FY2025 read as the
    FY2026 case, numerator year begun) takes 0."""
    return 0.0 if tag == "l" else max(0.0, inp["num_year"] - inp["t_base"])


def path_pe(g: float, roe: float, r: float, inp: dict[str, float]) -> float:
    """Three-segment RONIC path (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    gordon.py helper is not built yet).  Multiple on the numerator year (t = 1 <-> calendar
    num_year): retention of calendar year c earns the forward roe while c <= y1_ret, falls
    linearly to the steady return by y2_ret, and the steady return max(ss_return, r) (capped
    at roe) holds in a Gordon tail from y2_ret.  g <= 0 consumes no return -> perpetual_pe."""
    if g <= 0:
        return perpetual_pe(g, roe, r)
    t0, y1, y2 = int(inp["num_year"]), int(inp["y1_ret"]), int(inp["y2_ret"])
    rs = min(roe, max(inp["ss_return"], r))

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
            return pv + e * payout(g, rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1


def leg_pes(inp: dict[str, float], tag: str, r_mgl: float | None = None,
            r_afr: float | None = None) -> tuple[float, float]:
    roe = forward_roe(inp, tag)
    rm = inp["r_mgl"] if r_mgl is None else r_mgl
    ra = inp["r_afr"] if r_afr is None else r_afr
    return (path_pe(g_of(inp, "mgl", tag), roe, rm, inp),
            path_pe(g_of(inp, "afr", tag), roe, ra, inp))


def window_ps(inp: dict[str, float], tag: str) -> float:
    """Window distributable profit, CNY/share, undiscounted (valuation-rules ③ 时点对齐;
    A18): consensus profit not yet booked between the base date and the numerator year
    (rest of FY2026 = ni_2026_cons - ni_ytd_2026, then FY2027) x (1 - model b), b = the same
    retention the book roll charges.  L has none."""
    if tag == "l":
        return 0.0
    e = inp["equity"]
    b26 = model_b(inp, tag, inp["ni_2026_cons"] / e)
    n26 = inp["ni_2026_cons"] - inp["ni_ytd_2026"]
    e26 = e + n26 * b26
    n27 = inp[f"ni_2027_{tag}"]
    b27 = model_b(inp, tag, n27 / e26)
    return (n26 * (1 - b26) + n27 * (1 - b27)) * 1e8 / inp["shares"]


def leg_contrib(inp: dict[str, float], tag: str, pes: tuple[float, float] | None = None,
                r_mgl: float | None = None, r_afr: float | None = None) -> tuple[float, float]:
    """Per-share CNY from each leg, discounted from the numerator year at the leg's own r."""
    rm = inp["r_mgl"] if r_mgl is None else r_mgl
    ra = inp["r_afr"] if r_afr is None else r_afr
    pe_m, pe_a = pes if pes is not None else leg_pes(inp, tag, rm, ra)
    ni, w, n = inp[f"ni_group_{tag}"], inp["w_afr"], disc_years(inp, tag)
    return ((1 - w) * ni * pe_m * 1e8 / inp["shares"] / (1 + rm) ** n,
            w * ni * pe_a * 1e8 / inp["shares"] / (1 + ra) ** n)


def anchor(inp: dict[str, float], tag: str, **kw) -> float:
    """Two legs at the start of the numerator year, discounted tau at each leg's r, plus the
    window distributable profit discounted tau/2 (A18; both legs share 篮 4, r_mgl used)."""
    rm = kw.get("r_mgl") or inp["r_mgl"]
    win = window_ps(inp, tag) / (1 + rm) ** (disc_years(inp, tag) / 2.0)
    return sum(leg_contrib(inp, tag, **kw)) + win


def kasa_gp(inp: dict[str, float]) -> float:
    return inp["lp_rev_fy25"] * inp["lp_gm_fy25"]


def group_gp_fy25(inp: dict[str, float]) -> float:
    return (inp["trade_rev_fy25"] * inp["trade_gm_fy25"]
            + inp["logi_rev_fy25"] * inp["logi_gm_fy25"] + kasa_gp(inp))


def kasa_ni(inp: dict[str, float]) -> float:
    """FY2025 land-port GP × group NI/GP (Sakania was not tolling in FY2025)."""
    return kasa_gp(inp) * inp["ni_group_l"] / group_gp_fy25(inp)


def unit_value(inp: dict[str, float], t: float, pe_afr_h: float, r_afr: float | None = None,
               k: float = 1.0) -> float:
    """k × one measured Kasa unit on the Africa-leg H multiple, discounted to the base date
    (t_base; A18 时点对齐 -- formerly to the FY+1 deck basis)."""
    ra = inp["r_afr"] if r_afr is None else r_afr
    return k * kasa_ni(inp) * pe_afr_h * 1e8 / inp["shares"] / (1 + ra) ** (t - inp["t_base"])


def capex_ps(inp: dict[str, float], musd: float, t_inv: float, r_afr: float | None = None) -> float:
    """Unspent capital per share (valuation-rules 2026-10-04: capacity options deduct it),
    discounted from its investment year to the base date (t_base, A18).  100% basis: the
    stake in each corridor company is not disclosed (A14)."""
    ra = inp["r_afr"] if r_afr is None else r_afr
    return musd * inp["fx_usdcny"] / 100.0 * 1e8 / inp["shares"] / (1 + ra) ** (t_inv - inp["t_base"])


def net_options(inp: dict[str, float], pe_afr_h: float, r_afr: float | None = None) -> dict[str, float]:
    """{name: (gross, capex, net)} for Mokambo and the unsigned corridor (A14)."""
    mok_g = unit_value(inp, inp["t_mokambo"], pe_afr_h, r_afr, k=k_mokambo(inp))
    mok_c = capex_ps(inp, inp["inv_mokambo_musd"], inp["t_inv_mokambo"], r_afr)
    uns_g = unit_value(inp, inp["t_unsigned"], pe_afr_h, r_afr)
    uns_c = capex_ps(inp, inp["inv_kasa_musd"], inp["t_inv_unsigned"], r_afr)
    return {"mok": (mok_g, mok_c, mok_g - mok_c), "uns": (uns_g, uns_c, uns_g - uns_c)}


def k_mokambo(inp: dict[str, float]) -> float:
    """Mokambo's size in Kasa units = its announced investment ÷ Kasa's (capacity proxy)."""
    return inp["inv_mokambo_musd"] / inp["inv_kasa_musd"]




def calculate(context):
    inp = {**INPUTS, **{f'g2_afr_{t}': context['axes']['africa'][f'g2_afr_{t}'] for t in TIERS}}
    if any(not math.isfinite(v) for v in inp.values()):
        raise ValueError('inputs must be finite')
    if min(inp['shares'], inp['equity'], inp['r_mgl'], inp['r_afr']) <= 0:
        raise ValueError('invalid base denominator or discount rate')
    for leg in ('mgl', 'afr'):
        if inp[f'r_{leg}'] <= max(inp[f'g2_{leg}_{t}'] for t in TIERS):
            raise ValueError('growth must be below discount rate')
    if any(not float(inp[k]).is_integer() for k in ('num_year', 'y1_ret', 'y2_ret')) or inp['y1_ret'] >= inp['y2_ret']:
        raise ValueError('invalid return path years')
    pes = {t: leg_pes(inp, t) for t in TIERS}
    values = tuple(anchor(inp, t, pes=pes[t]) for t in TIERS)
    if not all(math.isfinite(v) for v in values) or not values[0] < values[1] < values[2]:
        raise ValueError('base anchors must be finite and ordered')
    A, B = cut_points(*values)
    leg = {t: leg_contrib(inp, t, pes=pes[t]) for t in TIERS}
    band = lambda values: dict(zip('LMH', values))
    warnings = ['historical_regional_profit_split_unverified', 'historical_project_capital_and_stake_unverified']
    result = {'ticker': '603871.SH', 'currency': 'CNY', 'units': {'price': 'CNY_PER_SHARE'},
              'valuation_as_of': None, 'framework_as_of': None,
              'historical_financial_statement_as_of': '2026-09-30', 'historical_research_as_of': '2026-10-30',
              'anchors': band(values), 'cut_points': {'A': A, 'B': B}, 'candidate': None, 'review_flags': warnings,
              'segments': {'mongolia': {'unit': 'CNY_PER_SHARE', 'values': band(leg[t][0] for t in TIERS)},
                           'africa': {'unit': 'CNY_PER_SHARE', 'values': band(leg[t][1] for t in TIERS)},
                           'window': {'unit': 'CNY_PER_SHARE', 'values': band(window_ps(inp, t)/(1+inp['r_mgl'])**(disc_years(inp, t)/2) for t in TIERS)}},
              'key_parameters': {name: {
                    'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', inp[f'r_{code}'])},
                    'growth_rate': {'unit': 'RATIO', 'values': band(g_of(inp, code, t) for t in TIERS)},
                    'forward_return': {'unit': 'RATIO', 'values': band(forward_roe(inp, t) for t in TIERS)},
                    'steady_return': {'unit': 'RATIO', 'values': band(min(forward_roe(inp, t), max(inp['ss_return'], inp[f'r_{code}'])) if g_of(inp, code, t) > 0 else None for t in TIERS)}}
                    for name, code in (('mongolia', 'mgl'), ('africa', 'afr'))},
              'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                 {'inputs': inp, 'project_weights': {'mokambo': P_MOKAMBO, 'unsigned': P_UNSIGNED}}, BASELINE_LOCAL)}
    try:
        options = net_options(inp, pes['h'][1])
        mok, unsigned = options['mok'][2], options['uns'][2]
        if not all(math.isfinite(v) and v > 0 for v in (mok, unsigned)):
            raise ValueError('invalid project values')
        total = mok + unsigned
        increments = [m * mok + u * unsigned for m, u in zip(P_MOKAMBO, P_UNSIGNED)]
        adjusted = [v + add for v, add in zip(values, increments)]
        if not adjusted[0] < adjusted[1] < adjusted[2]:
            raise ValueError('invalid option band')
        result['option'] = {'label': '非洲通道', 'value': total, 'value_unit': 'CNY_PER_SHARE',
                            'weights': band(v / total for v in increments), 'anchors': band(adjusted),
                            'projects': {'mokambo': {'value': mok, 'weights': band(P_MOKAMBO)},
                                         'unsigned': {'value': unsigned, 'weights': band(P_UNSIGNED)}}}
    except (ArithmeticError, ValueError, TypeError):
        result['option'] = {'status': 'unavailable', 'label': '非洲通道', 'anchors': None}
        warnings.append('historical_corridor_option_unavailable')
    return result
