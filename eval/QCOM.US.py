"""Historical QCOM model. Caller supplies shared data and Python library path."""

from __future__ import annotations
import math

from lib.gordon import (BASKET_R, check_g_cap, check_r, check_transition_years, g_cap, implied_g, payout, perpetual_pe, two_stage_pe)
from lib.inputs import check_missing, ladder
from lib.licensing import bind_ladder, fingerprint, rate_readings, normalized_rate_readings
from lib.zones import cut_points

from lib.partial_basis import local_basis_changed
DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'licensing', 'zones', 'partial_basis'), 'axes': {'licensing': 'licensing_annuity'}}

HISTORICAL_PARTIAL_FINGERPRINT = '87fafe650a3a8ba1b9a0cf2596d6ba1bf9670d92fc71c21d851a5f3bacbcf9e5'

INPUTS = {
    'shares': 1073000000.0,  # FY26Q4 实际加权稀释股本，作为 FY27 暂用代理；FY27 回购及稀释预测共识待更新，含权证稀释、不另加旧 1.84M；A7; as-of 2026-09-27
    'tax_rate': 0.13,  # FY26 全年 non-GAAP 实际约 13%；Q4 12.5% 不外推；FY27 暂沿用、共识待更新；A6; as-of 2026-09-27
    'equity': 30401000000.0,  # FY26 10-K 实际期末股东权益 USD，直接作为 FY27 期初权益；不再用 Q3 权益推演；A19; as-of 2026-09-27
    'rev_qtl_l': 5300.0,  # QTL 收入 $M，L 档；A2；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_qtl_m': 5900.0,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_qtl_h': 6200.0,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_hs_l': 17500.0,  # Handsets 收入 $M，L 档；A2 实测跌幅；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_hs_m': 22100.0,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_hs_h': 23500.0,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_auto_l': 6300.0,  # Automotive 收入 $M，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_auto_m': 7365.0,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_auto_h': 7900.0,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_iot_l': 6500.0,  # IoT 收入 $M，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_iot_m': 7857.0,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'rev_iot_h': 8300.0,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_qtl_l': 0.7,  # QTL EBT margin，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_qtl_m': 0.72,  # M 档；FY26 9M 实测 73%；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_qtl_h': 0.74,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_hs_l': 0.22,  # Handsets EBT margin，L 档；A5；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_hs_m': 0.25,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_hs_h': 0.27,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_auto_l': 0.27,  # Automotive EBT margin，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_auto_m': 0.3,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_auto_h': 0.32,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_iot_l': 0.25,  # IoT EBT margin，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_iot_m': 0.28,  # M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'om_iot_h': 0.3,  # H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'unalloc_l': 2100.0,  # 闭合项 $M，L 档；含 Data Center EBT −900；A8；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'unalloc_m': 1900.0,  # M 档；含 DC −800；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'unalloc_h': 1700.0,  # H 档；含 DC −700；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测）; as-of 2026-09-09
    'g_qtl': -0.0172,  # QTL 九年实测 CAGR；A4。**叙事/敏感性坐标，不进 PE**（QTL 已改 EV/EBIT）; as-of 2026-09-10
    'r_op': 0.1,  # 篮 4 龙头制造：Handsets / Auto / IoT 三腿折现率（A15，无备选篮）；QTL 归篮 3（8.5%）但主尺为 EV/EBIT 年金阶梯、无 r 行; as-of 2026-09-18
    'dc_target_rev': 15000.0,  # FY29 DC 收入目标 $M（more than $15B），本期重申，按 15B 下界计算增量上限；A10; as-of 2026-11-04
    'dc_cons_rev': 5000.0,  # FY27 DC 收入指引 $M，本期重申；从 FY29 目标扣除以避免重复计值；卖方更新及 FY28 覆盖待核实；A10; as-of 2026-11-04
    'hsbc_eps_fy27': 10.73,  # HSBC 96032 FY27 EPS（其 DC 敏感性的基数）；只用于把「+4%」换成每股增量；A10; as-of 2026-09-10
    'hsbc_dc_uplift': 0.04,  # HSBC 96032：DC 收入 20 亿 → 50 亿则 FY27 EPS +4%；**腿级卖方·单家**，DC 唯一有来源的利润率数据点（增量口径）；A8 / A10; as-of 2026-09-10
    'hsbc_dc_drev': 3000.0,  # 上行对应的 DC 收入增量 $M（50 − 20 亿）；A10; as-of 2026-09-10
    'hsbc_shares': 1062000000.0,  # HSBC 敏感性在旧框架折成美元利润时使用的固定股本；先还原增量税前利润率 17.46%，再除本期 shares，避免更新股本时改变单位经济；A10; as-of 2026-09-10
    'g2_dc_src': 0.0652,  # DC 腿 g2 来源 = 半导体横截面反解中位（`AVGO.US` A18 同尺同日：r=10% Gordon、yfinance 前瞻 PE × ROE；剔本票 10 家中位 6.525%），截到 cap 6%（本票 FY27 收入约 $450 亿 < $1,500 亿，不适用巨型硬件上限）；只进 \(V_{opt}\)；A10; as-of 2026-09-11
    't_opt': 2029.0,  # 兑现年 = 公司 DC 目标年 FY29；折回分子年 FY27 两年；A10; as-of 2026-06-24
    'g2_hs': -0.02,  # 手机永续增速，三档共用，无同业锚；沿用用户裁定。联发科反解 7.88% 含 ASIC/DC 叙事，与手机腿分子世界不符，未采用；本期不以安卓单季改善上调长期 g；A15; as-of 2026-09-14
    'g2_auto': 0.0502,  # Automotive 永续增长 = **同业横截面反解**：车用 / 模拟簇 NXPI 3.24% / TXN 6.80% 中位（`AVGO.US` A18 同尺同日，r=10%；剔本票）；三档共用（flat）；同世界门：FY27 Auto 收入上行，g2 > 0 可用；未触 cap 6%。v1 的 6% 为「无同业锚」贴顶，理由是近端 +61% 的高增，违反「MUST NOT 用抬高 g2 表达还有几年高增」（2026-10-03），撤销；FY29 公司目标 $10B 超出 FY27 共识的部分不进永续（只作 `stretched` 解释，A15）; as-of 2026-09-11
    'g2_iot': 0.02,  # IoT 永续增长；**无同业锚**（cap = min(6%, r−4%) = 6%，未收紧）; as-of 2026-09-09
    'pe_own_min': 9.81,  # 自身 5 年 trailing PE 实测底（2022-10；Longbridge `valuation --history pe`，月度 n=60，p10 11.78 / p50 17.05 / p90 26.62）；**护栏，不入公式**：整票 L/M/H ÷ 各档 eps 须落在 [min, max] 内（裁决顺序 ③）; as-of 2026-09-14
    'pe_own_max': 32.82,  # 同一序列实测顶（2026-01）；trailing GAAP 分母含 QSI 一次性收益等噪声，带只作护栏; as-of 2026-09-14
    'g2_auto_today': 0.051,  # Auto 腿进锚点的永续增速 = `g2_auto` 同一组同业（恩智浦 / 德州仪器，2026-09-14 快照的前瞻 PE × 账面 ROE）按本票同一条回报路径重解（2026-10-19：芯片腿稳态取自身周期、高于前瞻 → 路径平，只剩时点对齐；两家同业自身 ROE 27.9% / 35.2% 也不回落）→ 5.10%；`g2_auto` 行保留原读数；A17; as-of 2026-10-19
    'tau': 0.0,  # 估值基准日更新为 FY26 期末 2026-09-27，紧邻 FY27 年初 2026-09-28；按年度模型取 0，不再加已实现的 Q4 窗口利润；A17 / A19; as-of 2026-09-27
    't0_cal': 2027.0,  # 稳态回报三段的日历起点 = 分子年 FY27；A17; as-of 2026-10-16
    'y1': 2027.0,  # 高回报期止点 Y1 = 可见年末 FY27（默认路径；不在光通信链、不挂 ai-capex）；A17; as-of 2026-10-16
    'y2': 2031.0,  # 稳态起点 Y2 = Y1 + 4（进入门槛判「中」：芯片设计不建厂、单位产能投资低；手机 SoC / 基带客户认证约 1–2 年；联发科、苹果自研基带几年内抢下份额；车用 / IoT 认证更长；不确定）；A17; as-of 2026-10-16
    'rs_steady': 0.664,  # 经营三腿自身谷到谷 FY2018–23 投入资本回报均值 66.4%，去掉 FY19 失真年仍约 50%；高于本期前瞻 35.15%，按前瞻封顶；用户 2026-10-19 已认可；A17; as-of 2026-10-19
    'rs_steady_dc': 0.3,  # DC 新产品线叙事换代，稳态 min(本期前瞻 35.15%,30%)=30%；不套主业历史；用户 2026-10-19 已认可；A10/A17; as-of 2026-10-19
    'y1_dc': 2029.0,  # 期权高回报期止点 = 兑现年 FY29（按期权自己的产品阶段，不继承主业的 2027；A10 / A17）; as-of 2026-10-19
    'y2_dc': 2033.0,  # 期权稳态起点 = y1_dc + 4（门槛同芯片腿「中」；A10 / A17）; as-of 2026-10-19
}

FORMULA_ID = 'qcom_sotp_base4_qtl_evebit_vopt_fy27_v3'
BASELINE_FINGERPRINT = 'ad7122fe0c1cd70e615a3d05cd5e3318245c617df2acdfa3546aa2e2dc22aeeb'
NUM_YEAR = 2027
MIN_R_MINUS_G = 0.02
MM = 1000000.0
LISTING_CCY = 'USD'
LEGS = ('qtl', 'hs', 'auto', 'iot')
OP_LEGS = ('hs', 'auto', 'iot')
TIERS = ('l', 'm', 'h')
P_K = (0.0, 0.35, 1.0)
REQUIRED = ['shares', 'tax_rate', 'equity', 'r_op', 'pe_own_min', 'pe_own_max', 'dc_target_rev', 'dc_cons_rev', 'hsbc_eps_fy27', 'hsbc_dc_uplift', 'hsbc_dc_drev', 'g2_dc_src', 't_opt', 'hsbc_shares', 'g2_auto_today', 'tau', 't0_cal', 'y1', 'y2', 'rs_steady', 'rs_steady_dc', 'y1_dc', 'y2_dc', 'ev_ebit_ts_l', 'ev_ebit_ts_m', 'ev_ebit_ts_h', 'rev_qtl_l', 'rev_qtl_m', 'rev_qtl_h', 'rev_hs_l', 'rev_hs_m', 'rev_hs_h', 'rev_auto_l', 'rev_auto_m', 'rev_auto_h', 'rev_iot_l', 'rev_iot_m', 'rev_iot_h', 'om_qtl_l', 'om_qtl_m', 'om_qtl_h', 'om_hs_l', 'om_hs_m', 'om_hs_h', 'om_auto_l', 'om_auto_m', 'om_auto_h', 'om_iot_l', 'om_iot_m', 'om_iot_h', 'unalloc_l', 'unalloc_m', 'unalloc_h', 'g2_hs', 'g2_auto', 'g2_iot']

def tier_legs(
    inp: dict[str, float], t: str
) -> tuple[dict[str, float], dict[str, float], float]:
    """Per-leg scaled EBT/share and after-tax EPS, with the closing item pro-rated.

    The closing item carries the Data Center loss (A8). Its upside sits in
    V_opt, but the money it is losing today is real and belongs to the base --
    dropping it here would hand the base an improvement that has not happened,
    and the consensus reconciliation in §3 would stop tying out.

    The AWS deal (2026-09-09) made DC revenue computable without making its
    earnings positive, so this split survives the event: pulling the loss out
    here and giving DC a positive leg drifts consensus from -1.5% to +5.7%.

    QTL is valued on scaled EBT × EV/EBIT (pre-tax, same as NOK TS); the other
    three legs take after-tax EPS × Gordon PE. Scale is identical for both.
    """
    net = 1.0 - inp["tax_rate"]
    gross_ebt = {
        leg: inp[f"rev_{leg}_{t}"] * MM * inp[f"om_{leg}_{t}"] / inp["shares"]
        for leg in LEGS
    }
    drag_ebt = inp[f"unalloc_{t}"] * MM / inp["shares"]
    total_ebt = sum(gross_ebt.values())
    scale = (total_ebt - drag_ebt) / total_ebt
    ebt = {leg: v * scale for leg, v in gross_ebt.items()}
    eps = {leg: ebt[leg] * net for leg in LEGS}
    return ebt, eps, sum(eps.values())

def option_value(inp: dict[str, float], roe_m: float, g2_dc: float, r: float,
                 pe_fn=None) -> tuple[float, float, float, float]:
    """A10: Data Center option, closed by public data (valuation-rules 2026-10-03).

    Units: company FY29 DC target minus the FY27 guidance consensus already
    carries.  Unit economics: HSBC's FY27 DC sensitivity, read as after-tax EPS
    per dollar of DC revenue (no multiple taken from it).  Ruler: this ticker's
    Gordon PE at r_op, ROE_M and the DC leg's g2, struck in the target year and
    discounted to FY27.  Returns (V_opt, income/share, pre-tax margin, PE).
    """
    opt_rev = (inp["dc_target_rev"] - inp["dc_cons_rev"]) * MM
    # Preserve the source's dollar profit when updating this ticker's share
    # count; otherwise a share-count change would invent a new DC margin.
    eps_per_rev = (inp["hsbc_eps_fy27"] * inp["hsbc_dc_uplift"]
                   / (inp["hsbc_dc_drev"] * MM)
                   * inp["hsbc_shares"] / inp["shares"])
    inc = opt_rev * eps_per_rev
    margin = eps_per_rev * inp["shares"] / (1.0 - inp["tax_rate"])
    pe = perpetual_pe(g2_dc, roe_m, r) if pe_fn is None else pe_fn(g2_dc, roe_m, r)
    return inc * pe / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR), inc, margin, pe

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the steady-state-return path (valuation-rules「经营价值与超额现金」②
    稳态回报三段; gordon.py's three-segment function is not built yet, so it lives here).
    Calendar years, t = 1 is year t0; RONIC = roe through Y1, linear to min(rs, roe) by Y2,
    steady after.  With rs >= roe this equals perpetual_pe(g, roe, r)."""
    rs_eff = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs_eff
        return roe + (rs_eff - roe) * (cal - y1) / (y2 - y1)

    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g / rs_eff) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g / ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1

def check_no_p_leak(base_l: float, row_l: float) -> list[str]:
    """A2e-7a: p must not reach the base. The p=0 row has to reproduce base L."""
    if abs(row_l - base_l) > 1e-9:
        return [f"p leaked into the base: 表3 L row {row_l:.4f} != base L {base_l:.4f}"]
    return []


def evaluate(inputs: dict[str, float], *, shared_ladder: dict[str, float], rate_inputs: dict[str, float] | None = None) -> dict:
    """Evaluate the historical model against the caller's shared licensing ladder."""
    inp = bind_ladder(inputs, shared_ladder, 'QCOM.US')
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in inp.values()):
        raise ValueError('inputs must be finite numbers')
    whole_year_fields = ('t_opt', 't0_cal', 'y1', 'y2', 'y1_dc', 'y2_dc')
    for field in whole_year_fields:
        if inp[field] % 1:
            raise ValueError(f'{field} must be a whole year')
    if any(key == 'p' or key.startswith('p_') for key in inputs):
        raise ValueError('probability fields must not appear in Inputs')

    ebt, eps, totals = [], [], []
    for tier in TIERS:
        before_tax, after_tax, total = tier_legs(inp, tier)
        ebt.append(before_tax)
        eps.append(after_tax)
        totals.append(total)
    inp['g2_auto'] = inp['g2_auto_today']
    roe_m = totals[1] / (inp['equity'] / inp['shares'])
    if inp['tau'] != 0:
        errors.append('FY26 closing basis requires tau=0; the Q4 cash window is already realised')
    tau, t0 = inp['tau'], int(inp['t0_cal'])
    y1, y2, steady = int(inp['y1']), int(inp['y2']), inp['rs_steady']

    def leg_pe(g, rate):
        value = path_pe(g, roe_m, rate, t0, y1, y2, steady) if g > 0 else perpetual_pe(g, roe_m, rate)
        return value * (1 + rate) ** -tau

    multiples = {leg: leg_pe(inp[f'g2_{leg}'], inp['r_op']) for leg in OP_LEGS}
    licensing = [inp[f'ev_ebit_ts_{tier}'] for tier in TIERS]
    legs = []
    for index in range(3):
        row = {leg: eps[index][leg] * multiples[leg] for leg in OP_LEGS}
        row['qtl'] = ebt[index]['qtl'] * licensing[index]
        row['win'] = 0.0
        legs.append(row)
    base = [sum(row.values()) for row in legs]
    L, M, H = base
    A, B = cut_points(L, M, H)
    g2_dc = min(inp['g2_dc_src'], g_cap(inp['r_op']))
    y1_dc, y2_dc, steady_dc = int(inp['y1_dc']), int(inp['y2_dc']), inp['rs_steady_dc']
    if y1_dc < int(inp['t_opt']):
        errors.append('option return path starts before its realisation year')
    value, _, _, option_multiple = option_value(inp, roe_m, g2_dc, inp['r_op'],
        pe_fn=lambda g, roe, rate: path_pe(g, roe, rate, int(inp['t_opt']), y1_dc, y2_dc, steady_dc))
    value *= (1 + inp['r_op']) ** -tau
    adjusted = [base[i] + P_K[i] * value for i in range(3)]
    option_a, option_b = cut_points(*adjusted)

    for tier, price, earnings in zip('LMH', base, totals):
        multiple = price / earnings
        if not inp['pe_own_min'] - 1e-9 <= multiple <= inp['pe_own_max'] + 1e-9:
            errors.append(f'guardrail: {tier} blended multiple outside own band')
    errors += ladder('base', L, M, H)
    if any(not math.isfinite(number) or number < 0 for number in (*base, *adjusted)):
        errors.append('price anchors must be finite and non-negative')
    errors += ladder('option-adjusted base', *adjusted)
    errors += ladder('eps', *totals)
    errors += ladder('ev_ebit_ts', *licensing)
    errors += check_no_p_leak(L, adjusted[0])
    errors += check_r(inp['r_op'], 'r_op', 4)
    for leg in OP_LEGS:
        errors += check_g_cap(inp[f'g2_{leg}'], inp['r_op'], f'g2_{leg}')
    if not P_K[0] <= P_K[1] <= P_K[2]:
        errors.append('option weights must be non-decreasing')
    errors += check_g_cap(g2_dc, inp['r_op'], 'g2_dc')
    if inp['r_op'] - g2_dc < MIN_R_MINUS_G:
        errors.append('option growth too close to discount rate')
    if inp['t_opt'] <= NUM_YEAR:
        errors.append('option year must lie after numerator year')
    if inp['dc_target_rev'] <= inp['dc_cons_rev']:
        errors.append('DC target does not exceed consensus')
    if value < 0:
        errors.append('option value is negative')
    if errors:
        raise ValueError('; '.join(errors))
    def band_at(shift):
        rate = inp['r_op'] + shift
        if any(rate - inp[f'g2_{leg}'] <= 1e-12 for leg in OP_LEGS):
            raise ValueError('rate scenario requires discount rate above perpetual growth')
        pe = {leg: leg_pe(inp[f'g2_{leg}'], rate) for leg in OP_LEGS}
        return tuple(ebt[i]['qtl'] * licensing[i] + sum(eps[i][leg] * pe[leg] for leg in OP_LEGS)
                     for i in range(3))
    rate = rate_readings(rate_inputs, band_at, base)
    basis_inputs = dict(inputs, **{field: float(inputs[field]) for field in whole_year_fields})
    changed = fingerprint(basis_inputs, shared_ladder) != BASELINE_FINGERPRINT
    def parameter(values, unit='RATIO'):
        return {'unit': unit, 'values': dict(zip('LMH', values))}

    def shared(value):
        return [value] * 3

    def multiple_parameter(values, basis, year, valuation_point):
        return {**parameter(values, 'MULTIPLE'), 'basis': basis,
                'year': dict.fromkeys('LMH', year), 'year_type': 'fiscal',
                'valuation_point': valuation_point, 'discounted_to_valuation_as_of': False}

    # All chip legs receive the same group M return, not independent leg estimates.
    parameters = {}
    for leg in OP_LEGS:
        growth = inp[f'g2_{leg}']
        affects = growth > 0
        parameters[leg] = {
            'discount_rate': parameter(shared(inp['r_op'])),
            'growth_rate': parameter(shared(growth)),
            'forward_return': {**parameter(shared(roe_m)), 'basis': 'group_mid'},
            'steady_return': parameter(shared(min(roe_m, steady) if affects else None)),
            'steady_return_reference': parameter(shared(steady)),
            'multiple': multiple_parameter(shared(multiples[leg]), 'after_tax_earnings_per_share',
                                           NUM_YEAR, 'numerator_year_start'),
            'return_affects_multiple': dict.fromkeys('LMH', affects),
        }
    parameters['qtl'] = {
        'discount_rate': parameter(shared(None)), 'growth_rate': parameter(shared(None)),
        'forward_return': parameter(shared(None)), 'steady_return': parameter(shared(None)),
        'multiple': multiple_parameter(licensing, 'pre_tax_ebt_per_share', NUM_YEAR, 'valuation_as_of'),
    }
    # One option value is computed on the group M proxy, then weighted by tier.
    parameters['data_center_option'] = {
        'discount_rate': parameter(shared(inp['r_op'])), 'growth_rate': parameter(shared(g2_dc)),
        'growth_rate_reference': parameter(shared(inp['g2_dc_src'])),
        'forward_return': {**parameter(shared(roe_m)), 'basis': 'group_mid'},
        'steady_return': parameter(shared(min(roe_m, steady_dc) if g2_dc > 0 else None)),
        'steady_return_reference': parameter(shared(steady_dc)),
        'multiple': multiple_parameter(shared(option_multiple), 'incremental_after_tax_earnings_per_share',
                                       inp['t_opt'], 'numerator_year_start'),
        'return_affects_multiple': dict.fromkeys('LMH', g2_dc > 0),
    }
    return {'ticker': 'QCOM.US', 'currency': 'USD', 'formula_id': FORMULA_ID, 'valuation_as_of': None if changed else '2026-09-27',
            'framework_as_of': None if changed else '2026-11-05', 'basis_changed': changed, 'confirmed': False,
            'anchors': dict(zip('LMH', base)),
            'cut_points': {'A': A, 'B': B}, 'candidate': None,
            'option': {'label': 'data_center', 'value': value, 'weights': dict(zip('LMH', P_K)),
                       'anchors': dict(zip('LMH', adjusted)), 'cut_points': {'A': option_a, 'B': option_b}},
            'segments': {leg: {'values': dict(zip('LMH', (row[leg] for row in legs)))} for leg in LEGS},
            'key_parameters': parameters, 'rate': rate,
            'shared_inputs': {'licensing_ladder': {'id': shared_ladder['id'], 'version': shared_ladder['version'],
                                                   'fingerprint': fingerprint(shared_ladder)}}}


def calculate(context):
    shared = context['axes']['licensing']
    result = evaluate(INPUTS, shared_ladder=shared, rate_inputs=context.get('rate_inputs'))
    local = {'inputs': INPUTS, 'licensing': shared, 'option_weights': P_K}
    result['historical_valuation_as_of'] = '2026-09-27'
    result['historical_framework_as_of'] = '2026-11-05'
    result['review_flags'] = ['historical_segment_forecasts_not_refreshed',
                              'historical_data_center_unit_economics_single_source']
    result['option']['value_unit'] = 'USD_PER_SHARE'
    return _adapt_result(result, local)


def _adapt_result(result, local):
    # These are old research dates, not proof of current source validity or
    # approval. The runner alone attaches its unconfirmed status and versions.
    result.pop('confirmed', None)
    rate = normalized_rate_readings(result.pop('rate', None))
    if rate is not None:
        result['rate_sensitivity'] = rate
    result['valuation_as_of'] = None
    result['framework_as_of'] = None
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(local, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    for segment in result['segments'].values():
        segment['unit'] = 'USD_PER_SHARE'
    return result


# Historical source and judgments, transcribed verbatim; superseded values remain historical.
# # QCOM.US — 高通 / QUALCOMM Incorporated
#
# > 🔴 林奇：`cyclical` / `stalwart` | 更新：2026-11-05 | eval: eval/QCOM.US.py
# > 主尺：FY27 四腿 SOTP——QTL 税前 EBT × 共享年金梯 10 / 12.4 / 18.9；手机 / 汽车 / 物联网采用 Gordon、篮 4 的 10%，长期增速 −2% / 5.10% / 2%、三档同倍数；数据中心当期损益留闭合项，上行单列期权。FY26 年末实际权益作为 FY27 期初，τ=0、无 Q4 窗口利润；FY27 分部预测共识待更新。
#
# ## 0. 现行结论
#
# - **一句话 thesis**：高通仍按手机周期股估值，但手机下滑同时包含安卓去库存与苹果自研基带的结构性退出；FY26Q4 手机收入同比 −26%、汽车 +89%。QTL 已完成苹果、华为、传音续约，主要许可协议到期窗口移至 FY2030–2033，近端续约风险下降，但费率与长期收入预测基本不变。数据中心 FY27 收入目标 $5B、FY29 >$15B 重申，尚无可独立复算的整体利润，保留“亏损进底牌闭合项、增量上行进期权”的分工。
# - **这张表怎么读**：底牌 M **120.12** 美元，来自 QTL **42.51**、手机 **32.33**、汽车 **27.07**、物联网 **18.21**。QTL 用税前利润乘年金倍数；其余三腿按税后每股利润乘 Gordon 倍数，分别为 **8.33 / 17.45 / 11.79×**，三档共用。前瞻回报按 FY27 M 档利润除 FY26 年末实际权益，得 **35.15%**；既有自身周期回报 66.4% 高于前瞻，仍按前瞻封顶、不回落。数据中心上行另有 **23.48** 美元/股，底牌计零，中档另计 35%。
# - **本期变动边界**：底牌 82.20 / 121.41 / 165.21 → **80.86 / 120.12 / 163.72**（−1.6% / −1.1% / −0.9%）。本次只把权益、稀释股本代理、估值时点改为本期依据；取消旧 Q4 窗口利润 1.45/股，未因汽车单季年化接近 $8B 就擅自上调 FY27 全年预测。QTL 倍数梯与经营腿长期增速均不变。
# - **主要判断与局限**：QTL 梯 10 / 12.4 / 18.9 决定大部分高档扩张；钉在中档 12.4× 时，三档对照为 **87.56 / 120.12 / 138.89**。完成续约并不意味着高档已兑现，新授权、费率改善仍须举证。数据中心单位经济仍来自 HSBC 单家历史敏感性，不把定制芯片“对经营利润有贡献”误读为整个数据中心已盈利。
# - **主尺**：`formula_id = qcom_sotp_base4_qtl_evebit_vopt_fy27_v3`。经营腿篮 4 r=10%；QTL 篮 3，但使用共享 EV/EBIT 梯、8.5% 不入公式。三档分子同为 FY27；截至本期仍保留旧分部预测，**共识待更新**，不自动滚到尚未核实覆盖的 FY28。
# - **业务地图**：FY26 QCT 含手机、汽车、物联网；QTL 单独一腿；QSI 排除。FY26 不可报告分部含 Data Center、QGOV、Modular；FY27Q1 起 Data Center 并入公司披露的 QCT，但模型在盈利可算前仍单独留闭合项，不与 QCT 重复扣减。
# - **价带锚点**：底牌 L = **80.86** · M = **120.12** · H = **163.72**（USD）；数据中心期权上限 **23.48**。
# - **现行关键数字快照**（as-of 财报期：FY26Q4 / FY26 10-K，期末 **2026-09-27**；发布于美东 2026-11-04 盘后、北京时间 **2026-11-05**；FY27 共识仍为 2026-09-09/10 版本，**共识待更新**）：
#   - Q4 GAAP / non-GAAP 收入 **$10.322B / $10.442B**，non-GAAP EPS **2.17**；FY26 GAAP 收入 **$43.120B**、non-GAAP EPS **10.54**。
#   - Q4 手机 / 汽车 / 物联网收入 **$5.137B / $1.990B / $1.888B**；QCT EBT margin **24%**，QTL **70%**。
#   - FY26 年末权益 **$30.401B**；Q4 加权稀释股数 **1.073B**，作为 FY27 暂用代理；年末普通股 **1.072B**，两者口径不同。
#   - FY27Q1 收入指引 **$10.4–11.2B**、non-GAAP EPS **2.15–2.35**；QCT EBT margin **20–22%**（含 DC 前置投入约 −3pp）、QTL **72–76%**；DC 收入预计 >$650M。
#   - FY27E 底牌 EPS **9.959**，对旧共识 10.22 偏离 **−2.6%**，不称为本期刷新后的共识对账。
#   - 修正带（+ DC 期权，表3）**80.86 / 128.34 / 187.20**，切点 A′ **104.60** / B′ **157.77**。
# - **本期来源**（以下简写 S1 / S2 / S3）：[S1 公司业绩公告及非 GAAP 桥，8-K Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/804328/000080432826000127/qcom092726erex991.htm)；[S2 FY26 10-K，Note 1/8/9、MD&A、三表](https://www.sec.gov/Archives/edgar/data/804328/000080432826000128/qcom-20260927.htm)；[S3 电话会转录，AI 辅助中文翻译](https://longbridge.cn/news/304377971)。转录与公司文件冲突时以 S1/S2 为准；例如 DC 并入 QCT 的起点是 FY27，非转录问答误写的 FY26。
#
# ## 1. 专属属性
#
# - **业务地图摘要**（S1 / S2，$M；不可报告分部 Q4 为全年减原 9M，含取整差）：
#
#   | 分部 | Q4 收入 | YoY | FY26 收入 | Q4 EBT | FY26 EBT | 本框架归属 |
#   |---|---:|---:|---:|---:|---:|---|
#   | QCT-Handsets | 5,137 | −26% | 24,072 | — | — | 腿 |
#   | QCT-Automotive | 1,990 | +89% | 6,004 | — | — | 腿 |
#   | QCT-IoT | 1,888 | +4% | 7,132 | — | — | 腿 |
#   | QCT 合计 | 9,015 | −8% | 37,208 | 2,142 | 10,101 | 经营三腿 |
#   | QTL | 1,304 | −7% | 5,556 | 918 | 4,022 | 年金腿 |
#   | QSI | 0 | — | 0 | −123 | 794 | 排除 |
#   | 不可报告（DC + QGOV + Modular） | 123 | — | 476 | −188 | −607 | 闭合项；DC 上行进期权 |
#
# - **分部完备性与利润桥**：QSI 全年收益 794、Q4 亏损 123，仍排除。FY26 QCT + QTL EBT = **14,123**，减公司 non-GAAP EBT **12,976**，差额 **1,147**；Q4 同口径差额 **394**。这是核对闭合项的实际坐标，**不是 FY27 费用预测**，也不能把 GAAP 全部未分摊费用直接拿来扣非 GAAP 分子。原 FY27 闭合项 2,100 / 1,900 / 1,700（内含 DC 损益 −900 / −800 / −700）暂留、共识待更新。FY27 公司 QCT 指引含 DC，但本模型三条芯片腿仍不含 DC；之后采用新分部预测时必须先拆 DC，避免把同一亏损扣两遍。
# - **两张底牌质地不同**：QTL FY26 EBT margin 72%、Q4 70%，苹果、华为、传音续约完成，S2 明载主要协议窗口移至 FY2030–2033；手机 Q4 收入同比 −26%，两者仍不能共用一个整体 PE。
#
#   - **QTL 的债性由倍数锚表达，不再走合约化 \(r\)**：Gordon 在 \(g\le0\) 时 payout 封顶 1、\(pe=1/(r-g)\)，高 margin / 零资本消耗进不了倍数，只进分子（`om_qtl`）。付款方、费率、期限写在已签许可协议里——这笔现金流的债性是真的，但用 \(r=7\%\) 生成 PE 是仓库里的一条旁路，与 NOK.US 授权腿（Technology Standards）已经对齐的尺不一致。本票改与 NOK 同构且同梯：**税前 EBT/股 × EV/EBIT 10 / 12.4 / 18.9**（年金资产类的共享锚梯，当期、不折现；A14），续约情景落在倍数带上；Handsets / Auto / IoT 仍 Gordon flat @ \(r=10\%\)。
# - **Handsets 下滑为混合原因**：S2 MD&A 继续写明“customers adjusting build plans to reduce their inventory levels … memory supply constraints and related price increases”；S3 称中国安卓六月季度触底、渠道库存偏紧，Q4 手机收入较 Q3 环比约 +1%。但 FY27Q1 手机收入仍指引环比下降中个位数，安卓增长被苹果产品减少抵消。主类暂维持周期股，A3 的“非结构性流失”已削弱。
# - **Apple 的利润弹性仍待独立验证**：原 FY26Q3 10-Q 的 MDM“lower revenue and margin contributions”保留为历史依据；本期没有披露 Apple 单独利润率。QCT Q4 利润率 24% vs 上年 29%，不能据整体利润率反证或确认苹果一家的利润率。
# - **本期新增可观察事项**：S3 重申 DC FY27 $5B、FY29 >$15B，FY27Q1 >$650M、年末年化约 $7B；AWS 十月开始发货，但不能把出货直接当成本季收入。汽车 Q4 $1.990B、第五代平台放量支持近端增长，未直接改永续增速。SpaceX 合作预计 FY27 末至 FY28 体现，尚无金额与利润依据，不新增盈利腿或期权金额。
#
# - **\(V_{opt}\) 具名条目：Data Center**（A2e-7c-2 要求的三件套）
#   - **为什么落此（FY26Q4 核对）**：DC 收入有目标，利润尚不能独立复算。FY26 不可报告分部 EBT −$607M 含 DC、QGOV 与 Modular，不能全归给 DC。S3 对定制芯片“有经营利润贡献”的表述，不代表整个 DC（含 CPU / 商用加速器前置投入）转正。FY27 起 DC 并入 QCT 本身也不满足单列盈利腿的门槛；旧亏损继续留闭合项，待贡献利润可复算后再迁移。
#   - **上限锚：公开数据闭合 = 23.48/股**（A10 / A17；FY26 年末基准）：
#     - **份数**：FY29 具名目标 >$15B 减 FY27 已含指引 $5B = **$10B**，两者于本期重申；FY28 的更远共识尚未核实，不凭年末运行率自动前移预测年。
#     - **单位经济**：HSBC 96032 历史敏感性，FY27 DC $2B → $5B 对其 EPS 10.73 上行 4%；源每股增量为 0.4292，对 $3B 收入。固定原折算股本 1.062B，得增量税前利润率 **17.46%**；换本期 1.073B 股后，每 $1B 收入增量 **0.1416 美元/股税后**。这是旧模型单家敏感性，**不是公司本期披露的 DC 利润率**。
#     - **估值（本票尺）**：$10B × 17.46% × (1−13%) ÷ 1.073B = **1.4160** 美元/股，× PE **20.07×** = FY29 **28.41**；r 10%、g2 6%（半导体同业簇截顶）、前瞻回报 35.15% 维持至 FY29、FY33 降至 30%，按两年折现 ÷1.21 = **23.48**。τ=0；没有 Q4 窗口。
#     - **沿用与撤销**：2026-10-19 用户已认可 DC 自己的 FY29→FY33 回报路径，主业 FY27→FY31 与长期增速不动。v1 的 HSBC 目标倍数 17×、全额 $15B 和未折现口径继续撤销，不借同业倍数。g2 改取 4% 时期权 **16.95**，只作敏感性。
#
#   - **升级门槛**（门槛已因 AWS 公告上移一级：收入可算不再是门槛，**利润可算才是**）：
#     - *定制 ASIC（custom silicon）*：**收入侧门槛已于 2026-09-09 触发**——具名客户（AWS、字节跳动）+ 可复算 program 规模 + ≥2 家卖方拆出 FY27 DC 收入。但整体盈利分子仍无法独立复算，**未**移出 \(V_{opt}\)。**新门槛 = 公司披露 DC 分部 EBT 且转正，或 ≥2 家卖方给出可复算的 DC 贡献利润。** 届时做成腿 **MUST** 用本票尺（篮 4 r、本票 ROE 口径、DC 腿 g2 = 半导体横截面反解，`g2_dc_src`）由 Gordon 生成，**MUST NOT** 借 `AVGO.US` XPU 腿或任何同业的倍数（借量不借价，2026-10-03），也 **MUST NOT** 沿用 `pe_auto`——后者由车用 / 模拟簇的 g2 生成。
#     - *自研加速器（AI200/AI250）*：公司把 Data Center 提为 reportable segment 并单独披露收入 + EBT，且商用加速器收入可与定制硅分开。
#     - 任一触发即按 7c-3 把**对应部分**移出 \(V_{opt}\) 做成腿并上调 H，未触发的另一条仍留在 \(V_{opt}\)。
#   - **证伪触发器**（两条路径各自可证伪；两条均触发 → \(V_{opt}\) 置 0，H 以上的价格失去框架内解释）：
#     - *定制 ASIC*：AWS 权证在首批 375 万股之后 **12 个月内无新增归属**（说明绑定采购订单没有续下）；或字节跳动那笔在 FY27 结束时仍无收入确认；或公司明确表态不承接第三方定制业务。**先决条件观测点**：定制 ASIC 同样占用 CoWoS 产能，`_AXIS.cowos-capacity.md` 的「其余」桶 CY2027 为 36.7–45.8 万片，高通在该桶内取得可见分配是兑现的必要条件（本票未挂该轴，仅作可观测量级参照）。
#     - *自研加速器*：AI200 量产时点较现行公开口径推迟 >12 个月；或 FY29 DC 收入指引（现 >150 亿）被下修 >30%；或 FY27 DC 实绩 / 指引上修使「共识已含」接近 FY29 目标（份数收缩，重算 `dc_cons_rev`）。
#     - **注意口径已变**：原触发器「FY27 结束时 DC 收入仍 <10 亿」已被公告作废——卖方最低口径（HSBC）都给到 20 亿，该条不再有区分力。
#   - **已投入**：Alphawave 23 亿（2025-12-18 完成，goodwill 22.1 亿全额分配至 Data Center）+ Modular 约 31 亿（2026-07-28 完成）+ 其他 7 笔中 0.76 亿 → 合计约 **55–60 亿，几乎全部股票支付**。此为管理层出价，非 \(V_{opt}\) 的锚，仅作量级参照。
#
# ## 2. Assumptions
#
# | id | 假设 | 状态 | 证据 | 影响 |
# |----|------|------|------|------|
# | A1 | FY27E 合并收入 M 44,822、H 45,900（旧共识 high 47,100，$M）暂留；FY26 实际收入 43,120、FY27Q1 指引 10,400–11,200 不足以确认全年及分部拆分。**共识待更新**，维持原预测日期 | active | 原 yfinance 32 家共识 2026-09-09；本期 S1/S3 | 各腿 M/H 分子；不得把单季乘四当新共识 |
# | A2 | **维持 L 档实测周期谷底**：FY22→FY23 收入 −19.0%（44.20→35.82B）、GAAP EPS −43.5%、OI margin 35.9%→24.1%，施于 FY25 峰值约得 35.6B。FY26 全年收入只降 3%，手机 Q4 −26%，汽车全年 +52%；低档是压力情景，不宣称已见底 | active | 原年度利润表 FY22–FY25；本期 S1 | L 档分子；维持原周期坐标 |
# | A3 | 原“手机下滑主要是内存涨价去库存、非结构性份额流失”**削弱**。本期改读为安卓周期去库存 + Apple 基带结构性退出：Q4 手机 5,137M、同比 −26% / 环比约 +1%；FY27Q1 环比下降中个位数，安卓增长被苹果下降抵消 | weakened | S2 MD&A 库存与 memory supply constraints 原句；S3 手机指引及库存问答 | 主类暂维持 cyclical；手机分子共识待更新 |
# | A4 | **旧窗口已证伪、保留历史**：主要许可协议原预计 FY2027–2031 到期；S2 已改为 FY2030–2033，续约见 A18。原 FY2017→FY2025 QTL 收入 CAGR −1.72%、FY2021→FY2025 −3.06% 保留历史坐标，不生成倍数；旧窗口不再用于现行情景 | falsified | 原 FY26Q3 10-Q；本期 S2 Note 1 明载新窗口、S1 续约公告 | g_qtl 仅叙事；当前续约状态见 A18 |
# | A5 | **维持、未独立量化确认**：Apple 为 thin modem / MDM，旧披露为较低收入及利润贡献；本期未披露 Apple 独立利润率。手机 Q4 −26%、QCT EBT margin 24% vs 29% 不能隔离 Apple 的利润弹性 | active | 原 FY26Q3 10-Q 风险因素；本期 S1/S3 | Handsets om 三档暂留，共识待更新 |
# | A6 | **确认 FY26 年度口径**：全年 non-GAAP 税率约 13%，Q4 12.5%；分部 EBT 排除 SBC，仍须与合并 non-GAAP 桥核对。FY27 税率未获得独立新指引，主尺暂用 13%，不把单季 12.5% 外推全年 | confirmed | S1 非 GAAP 税率脚注、S2 Note 8 unallocated share-based compensation | tax_rate=13% 暂留；共识待更新 |
# | A7 | **旧 FY27 股本 1.062B 预测削弱**：FY26Q4 实际稀释加权股数 1.073B、期末普通股 1.072B，Q4 回购 6M / $1,011M。新主尺暂以实际 1.073B 代理 FY27，回购与稀释预测共识待更新；已含权证稀释，不再另加旧库藏股法 1.84M。未来须按实际归属 / 期间平均价格及回购重建，不能用总权证 25M 当稀释 EPS 股数 | weakened | S1 EPS reconciliation / return of capital；S2 库藏股法、收购及 customer warrant 附注 | shares=1.073e9；HSBC 单位经济固定原股本再换本期分母 |
# | A8 | **维持亏损入闭合项，削弱旧金额依据**：FY27 DC EBT −900/−800/−700M 暂留、共识待更新；FY26 不可报告分部收入 476M、EBT −607M 含 DC/QGOV/Modular，不能直接当 DC。FY27Q1 DC 并入 QCT、前置投入拖累 QCT margin 约 3pp，尚无可独立复算的整体 DC 利润。只在公司披露独立 EBT 且转正、或 ≥2 家卖方贡献利润可复算后迁移；采用新 QCT 预测前先去重 | weakened | S2 Note 8；S3 QCT 利润率指引；旧 HSBC 96032 为 17.46% 增量口径 | unalloc_* 暂留；FY26 QCT+QTL EBT − non-GAAP EBT=1,147M，Q4=394M，仅作实际校验 |
# | A9 | **确认**：QSI 投资损益不可永续化，排除底牌。FY26 EBT +794M、Q4 −123M；年度收益含权益法、非上市投资估值及 IPO 收益，不再把旧 9M 收益笼统描述为全部来自 IPO | confirmed | S1 非 GAAP 桥；S2 Note 8 / MD&A QSI 投资收益构成 | 分部完备性；QSI 不进闭合后的经营利润 |
# | A10 | **维持期权构造、重算上限 23.20→23.48**：FY29 DC >$15B 减 FY27 $5B=$10B，本期重申。HSBC 96032 EPS 10.73 ×4% / $3B，用旧折算股本 1.062B 固定税前单位经济 17.46%，再用本期 1.073B 股得到增量 EPS 1.4160；本票 PE 20.07×，FY29 值 28.41、折两年到 FY27 为 23.48。r 10%、g2 6%；DC 回报从前瞻 35.15% 维持至 FY29、FY33 到 30%，沿用用户 2026-10-19 认可的路径，不套主业 66.4% | active | S1/S3 重申收入目标；旧 HSBC 96032（单家、增量利润率，非本期公司利润指引）；AVGO A18 半导体簇 g2 | dc_*、hsbc_*、hsbc_shares；表3；盈利可算才升级 |
# | A11 | **维持 p_M=0.35**（不进底牌）：历史坐标为归属 3.75M /25M=15%、两家具名客户覆盖 FY27 指引约 80%。S2 期末“约 4M 股已归属”是取整，不据此认定新增归属；S3 AWS 十月发货、Q1 DC 指引 >650M 增强执行证据，但 FY29 额外 $10B 尚无完整合同覆盖，暂不上调比例 | active | 原 AWS 公告 2026-09-09；S2 customer warrant；S3 客户与发货节奏 | 表3 M 行；期权对 FY29 增量计 35% |
# | A13 | **维持历史倍数来源**：卖方 QTL EV $45–55B 对应税前 EV/EBIT 11.1–13.6×，中点 12.4；H 18.9× 为 IDCC 2026-09-04 实测。FY26 QTL EBT 4,022M / margin 72%、重要续约完成支持年金性质，但基本维持费率、未验证 H 所含费率改善或新授权。旧估值来源不标成本期新验证 | active | 原第三方 SOTP、IDCC yfinance；本期 S1/S3 | ev_ebit_ts_m 与读带；不据续约自动上调梯 |
# | A14 | **维持同尺同梯**：QTL 税前分摊后 EBT/股 × EV/EBIT 10/12.4/18.9，与 NOK 授权腿逐格校验。L 美银其它业务 10×、M 卖方 SOTP 税前中点、H IDCC 实测；旧无来源梯 9/12/16 仍撤销。FY26Q4 QTL 收入 −7%、margin 70%，新续约窗口 FY2030–2033，风险下降仍有终端量风险；不重启 Gordon r_qtl | active | 原美银 97381 / SOTP / IDCC；S1/S2；NOK 同梯 | ev_ebit_ts_* 不变；A4 历史窗口由 A18 替代 |
# | A12 | **维持分子同为 FY27，修正时间理由**：FY26 已结束，FY27 已是当前财年，不再援引“当前财年+1”。截至本次仍只核实原 FY27 多家共识，FY28 覆盖待核实，不自动滚年。估值基准 FY26 年末，FY27 t=1、tau=0，不额外折现经营腿；FY29 期权折回两年 | active | S1 财年结束；原共识年限；A17/A19 时点对齐 | 年份口径；修复旧“不折现”与 A17 的冲突 |
# | A15 | **维持归篮与长期增速**：手机/汽车/物联网篮 4 r=10%；QTL 篮 3 按量许可，8.5% 不入公式。三条经营腿 flat，g2 手机 −2%、物联网 2%（两者无同业锚，沿用定稿），汽车源 5.02% 按已认可路径重解 5.10%（NXPI/TXN，2026-09-14）；本期汽车 +89% 不直接抬永续 g。FY28 共识待核实，无新增高增长窗口。ROE_M 35.15% > r，仍在单调区；自身周期回报 66.4% 按前瞻封顶 | active | gordon.BASKET_R；旧同业反解与用户 2026-10-19 定稿；本期 S1 | r_op / g2_* 不变；不为单季表现换篮或抬 g |
# | A16 | **旧 Q3→FY27 年初推演已失效、留历史**：原用 Q3 权益 27.95B、FY26 共识 EPS 10.484−9M 8.36，按增长所需留存推得 BPS 26.34、ROE 38.21%。FY26 实际权益 30.401B 已公布，原推演与 Q4“模型视同派出”1.41/股披露不再作为现行输入；改用 A19 | falsified | 原 yfinance 2026-09-21；本期 S1/S2 实际权益、全年 non-GAAP EPS 10.54 | 移除 eps_fy26_cons / eps_9m_fy26 / payout_3y 的旧推演依赖 |
# | A17 | **旧窗口削弱并撤销，稳态回报路径维持**：FY26 年末基准紧邻 FY27 年初，tau=0，取消旧 Q4 窗口利润 1.45/股；不再把已实现利润另加价值。经营三腿自身 FY2018–23 谷到谷投入资本回报 66.4%（去掉 FY19 失真年仍约 50%）高于新前瞻 35.15%，仍封顶前瞻、路径平；Y1 FY27/Y2 FY31、DC FY29/FY33 和稳态 30% 沿用 2026-10-19 用户认可。无超额现金腿；现金短投 7.681B 对有息债 15.112B，净债 7.431B；全年 CFO 11.145B、capex 2.494B，FCF 8.651B。既有主尺与资金处理未另改 | weakened | S1/S2 三表；原 SEC XBRL 周期回报；用户 2026-10-19 定稿 | tau、ROE 参数、窗口=0；不因数据中心并入 QCT 取消其亏损 |
#
# | A18 | **确认新续约状态**：苹果、华为、传音长期许可协议已续签，主要 OEM 协议到期窗口 **FY2030–2033**；管理层称收入运行率与长期预测不变，基本维持费率。FY26 QTL 收入 5,556M vs FY25 5,582M，不把续约等同收入增长；替代 A4 旧窗口 | confirmed | S1 续约公告；S2 Note 1 原句“terms now expiring … between fiscal 2030 and 2033”；S3 费率问答 | 年金情景与续约风险；不单独改共享梯 |
# | A19 | **确认采用实际期初权益**：FY27 利润除 FY26 年末实际权益 30.401B；以 shares 暂用代理 1.073B 折 BPS=28.33、M EPS 9.959，ROE_M=35.15%。同一股本在分子分母抵消。FY26 GAAP EPS 12.70 含税项等调整，不能直接替代 non-GAAP 10.54 或 FY27 前瞻利润；无需再滚 Q4 留存 | confirmed | S1 资产负债表与非 GAAP 桥；S2 股东权益 30,401M | equity 直接作 FY27 期初；替代 A16；Gordon 及期权共用此回报分母 |
#
# 状态只能是：`active` | `confirmed` | `weakened` | `falsified`
#
# ## 3. 可演算块
#
# ### Inputs
#
# （取值列只放裸数字；`eval/QCOM.US.py` 解析本表。**无 \(p\) 类字段**——A2e-7a 硬红线。）
#
# | 字段名 | 取值 | 含义 / 来源 | as-of |
# |--------|------|-------------|-------|
# | shares | 1.073e9 | FY26Q4 实际加权稀释股本，作为 FY27 暂用代理；FY27 回购及稀释预测共识待更新，含权证稀释、不另加旧 1.84M；A7 | 2026-09-27 |
# | tax_rate | 0.13 | FY26 全年 non-GAAP 实际约 13%；Q4 12.5% 不外推；FY27 暂沿用、共识待更新；A6 | 2026-09-27 |
# | equity | 3.0401e10 | FY26 10-K 实际期末股东权益 USD，直接作为 FY27 期初权益；不再用 Q3 权益推演；A19 | 2026-09-27 |
# | rev_qtl_l | 5300 | QTL 收入 $M，L 档；A2；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_qtl_m | 5900 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_qtl_h | 6200 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_hs_l | 17500 | Handsets 收入 $M，L 档；A2 实测跌幅；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_hs_m | 22100 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_hs_h | 23500 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_auto_l | 6300 | Automotive 收入 $M，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_auto_m | 7365 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_auto_h | 7900 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_iot_l | 6500 | IoT 收入 $M，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_iot_m | 7857 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | rev_iot_h | 8300 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_qtl_l | 0.70 | QTL EBT margin，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_qtl_m | 0.72 | M 档；FY26 9M 实测 73%；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_qtl_h | 0.74 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_hs_l | 0.22 | Handsets EBT margin，L 档；A5；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_hs_m | 0.25 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_hs_h | 0.27 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_auto_l | 0.27 | Automotive EBT margin，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_auto_m | 0.30 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_auto_h | 0.32 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_iot_l | 0.25 | IoT EBT margin，L 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_iot_m | 0.28 | M 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | om_iot_h | 0.30 | H 档；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | unalloc_l | 2100 | 闭合项 $M，L 档；含 Data Center EBT −900；A8；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | unalloc_m | 1900 | M 档；含 DC −800；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | unalloc_h | 1700 | H 档；含 DC −700；FY27 预测共识待更新（本期实际见 §0/§1，非替代预测） | 2026-09-09 |
# | g_qtl | -0.0172 | QTL 九年实测 CAGR；A4。**叙事/敏感性坐标，不进 PE**（QTL 已改 EV/EBIT） | 2026-09-10 |
# | ev_ebit_ts_l | 10 | QTL L 档 = **共享年金锚梯**低端：美银「其它业务 10×」（A14；与 `NOK.US` `ev_ebit_ts_l` 同值，eval 跨文件校验） | 2026-07-24 |
# | ev_ebit_ts_m | 12.4 | QTL M 档 = 共享年金锚梯中端：卖方 QTL SOTP 簇 EV $45–55B ≈ 12.8–15.6× 净利 → 税前（13%）11.1–13.6× EV/EBIT 的中点（A13 / A14；与 `NOK.US` `ev_ebit_ts_m` 同值） | 2026-09-14 |
# | ev_ebit_ts_h | 18.9 | QTL H 档 = 共享年金锚梯高端：InterDigital 实测 EV/EBITDA 18.9×（授权 D&A 极小 ≈ EV/EBIT；yfinance）（A14；与 `NOK.US` `ev_ebit_ts_h` 同值） | 2026-09-04 |
# | r_op | 0.10 | 篮 4 龙头制造：Handsets / Auto / IoT 三腿折现率（A15，无备选篮）；QTL 归篮 3（8.5%）但主尺为 EV/EBIT 年金阶梯、无 r 行 | 2026-09-18 |
# | dc_target_rev | 15000 | FY29 DC 收入目标 $M（more than $15B），本期重申，按 15B 下界计算增量上限；A10 | 2026-11-04 |
# | dc_cons_rev | 5000 | FY27 DC 收入指引 $M，本期重申；从 FY29 目标扣除以避免重复计值；卖方更新及 FY28 覆盖待核实；A10 | 2026-11-04 |
# | hsbc_eps_fy27 | 10.73 | HSBC 96032 FY27 EPS（其 DC 敏感性的基数）；只用于把「+4%」换成每股增量；A10 | 2026-09-10 |
# | hsbc_dc_uplift | 0.04 | HSBC 96032：DC 收入 20 亿 → 50 亿则 FY27 EPS +4%；**腿级卖方·单家**，DC 唯一有来源的利润率数据点（增量口径）；A8 / A10 | 2026-09-10 |
# | hsbc_dc_drev | 3000 | 上行对应的 DC 收入增量 $M（50 − 20 亿）；A10 | 2026-09-10 |
# | hsbc_shares | 1.062e9 | HSBC 敏感性在旧框架折成美元利润时使用的固定股本；先还原增量税前利润率 17.46%，再除本期 shares，避免更新股本时改变单位经济；A10 | 2026-09-10 |
# | g2_dc_src | 0.0652 | DC 腿 g2 来源 = 半导体横截面反解中位（`AVGO.US` A18 同尺同日：r=10% Gordon、yfinance 前瞻 PE × ROE；剔本票 10 家中位 6.525%），截到 cap 6%（本票 FY27 收入约 $450 亿 < $1,500 亿，不适用巨型硬件上限）；只进 \(V_{opt}\)；A10 | 2026-09-11 |
# | t_opt | 2029 | 兑现年 = 公司 DC 目标年 FY29；折回分子年 FY27 两年；A10 | 2026-06-24 |
# | g2_hs | -0.02 | 手机永续增速，三档共用，无同业锚；沿用用户裁定。联发科反解 7.88% 含 ASIC/DC 叙事，与手机腿分子世界不符，未采用；本期不以安卓单季改善上调长期 g；A15 | 2026-09-14 |
# | g2_auto | 0.0502 | Automotive 永续增长 = **同业横截面反解**：车用 / 模拟簇 NXPI 3.24% / TXN 6.80% 中位（`AVGO.US` A18 同尺同日，r=10%；剔本票）；三档共用（flat）；同世界门：FY27 Auto 收入上行，g2 > 0 可用；未触 cap 6%。v1 的 6% 为「无同业锚」贴顶，理由是近端 +61% 的高增，违反「MUST NOT 用抬高 g2 表达还有几年高增」（2026-10-03），撤销；FY29 公司目标 $10B 超出 FY27 共识的部分不进永续（只作 `stretched` 解释，A15） | 2026-09-11 |
# | g2_iot | 0.02 | IoT 永续增长；**无同业锚**（cap = min(6%, r−4%) = 6%，未收紧） | 2026-09-09 |
# | pe_own_min | 9.81 | 自身 5 年 trailing PE 实测底（2022-10；Longbridge `valuation --history pe`，月度 n=60，p10 11.78 / p50 17.05 / p90 26.62）；**护栏，不入公式**：整票 L/M/H ÷ 各档 eps 须落在 [min, max] 内（裁决顺序 ③） | 2026-09-14 |
# | pe_own_max | 32.82 | 同一序列实测顶（2026-01）；trailing GAAP 分母含 QSI 一次性收益等噪声，带只作护栏 | 2026-09-14 |
# | g2_auto_today | 0.0510 | Auto 腿进锚点的永续增速 = `g2_auto` 同一组同业（恩智浦 / 德州仪器，2026-09-14 快照的前瞻 PE × 账面 ROE）按本票同一条回报路径重解（2026-10-19：芯片腿稳态取自身周期、高于前瞻 → 路径平，只剩时点对齐；两家同业自身 ROE 27.9% / 35.2% 也不回落）→ 5.10%；`g2_auto` 行保留原读数；A17 | 2026-10-19 |
# | tau | 0 | 估值基准日更新为 FY26 期末 2026-09-27，紧邻 FY27 年初 2026-09-28；按年度模型取 0，不再加已实现的 Q4 窗口利润；A17 / A19 | 2026-09-27 |
# | t0_cal | 2027 | 稳态回报三段的日历起点 = 分子年 FY27；A17 | 2026-10-16 |
# | y1 | 2027 | 高回报期止点 Y1 = 可见年末 FY27（默认路径；不在光通信链、不挂 ai-capex）；A17 | 2026-10-16 |
# | y2 | 2031 | 稳态起点 Y2 = Y1 + 4（进入门槛判「中」：芯片设计不建厂、单位产能投资低；手机 SoC / 基带客户认证约 1–2 年；联发科、苹果自研基带几年内抢下份额；车用 / IoT 认证更长；不确定）；A17 | 2026-10-16 |
# | rs_steady | 0.664 | 经营三腿自身谷到谷 FY2018–23 投入资本回报均值 66.4%，去掉 FY19 失真年仍约 50%；高于本期前瞻 35.15%，按前瞻封顶；用户 2026-10-19 已认可；A17 | 2026-10-19 |
# | rs_steady_dc | 0.30 | DC 新产品线叙事换代，稳态 min(本期前瞻 35.15%,30%)=30%；不套主业历史；用户 2026-10-19 已认可；A10/A17 | 2026-10-19 |
# | y1_dc | 2029 | 期权高回报期止点 = 兑现年 FY29（按期权自己的产品阶段，不继承主业的 2027；A10 / A17） | 2026-10-19 |
# | y2_dc | 2033 | 期权稳态起点 = y1_dc + 4（门槛同芯片腿「中」；A10 / A17） | 2026-10-19 |
#
# ### Formula / 步骤
#
# `formula_id`：`qcom_sotp_base4_qtl_evebit_vopt_fy27_v3`
#
# 1. 四腿税前每股利润：`ebt_i,k = rev_i,k × om_i,k × 1e6 / shares`；税后 `eps_i,k = ebt_i,k × (1−tax_rate)`。收入均为 $M；三档同为 FY27。
# 2. 闭合项按税前利润比例分摊：`scale_k = (Σebt_i,k − unalloc_k×1e6/shares) / Σebt_i,k`，各腿税前与税后利润都乘同一 scale。DC 当期亏损只在这里扣一次。
# 3. QTL：分摊后税前 EBT/股 × 10 / 12.4 / 18.9；与 NOK 共享梯逐格校验。经营三腿：分摊后税后 EPS × Gordon PE，r_op=10%，g2=−2% / 5.10% / 2%；三档共用 M 档前瞻回报（flat）。
# 4. `BPS_open = equity/shares`，`ROE_M = EPS_M/BPS_open`。直接用 FY26 年末实际权益，不再滚 Q4；经营三腿稳态取 min(66.4%, ROE_M)，Y1 FY27→Y2 FY31。本期稳态高于前瞻、路径平。估值基准更新到 FY26 年末，tau=0、Q4 窗口利润=0。
# 5. 各腿价值相加得底牌 L/M/H，切点为相邻中点；底牌无概率、无 DC 上行。
# 6. 期权税前增量利润率 = `hsbc_eps_fy27 × hsbc_dc_uplift × hsbc_shares / (hsbc_dc_drev×1e6×(1−tax_rate))` = 17.46%；先固定源美元利润再换股本。增量 EPS = `(dc_target_rev−dc_cons_rev) × hsbc_eps_fy27 × hsbc_dc_uplift / hsbc_dc_drev × hsbc_shares/shares`。FY29 按本票尺估值：DC g2=min(6.52%,cap)=6%，r=10%，前瞻回报维持至 FY29、FY33 到 min(前瞻,30%)；再折回 FY27 两年，tau=0。
# 7. 表3逐档 `底牌_k + p_k×V_opt`，p=0 / 0.35 / 1；p 不进 Inputs，不参与底牌计算。
#
# **口径与未更新项**：FY27 分子保留原多家共识拆分，**共识待更新**；L 沿用自身周期压力情景，不把本期 Q4 年化当全年低点。FY27 为当前财年，估值基准为 FY26 年末、模型 t=1，故经营腿不额外折现；期权 FY29 折两年。共享情景轴无；QTL 同梯跨票校验保留。自身 5 年 trailing PE 9.81–32.82× 仍为旧历史护栏，非本期更新的估值带。
#
# ### Outputs — 锚点与五档区间
#
# （由 `eval/QCOM.US.py` 从 Inputs 重算，容差 0.05；FY27 分部预测共识待更新。）
#
# - 底牌 L = **80.86** · M = **120.12** · H = **163.72** · 切点 A = **100.49** · B = **141.92**（USD）
# - \(V_{opt}\) = **23.48** · \(p_L/p_M/p_H\) = **0 / 0.35 / 1.00**（FY29 目标减 FY27 指引 $10B；历史单家增量 EBT margin 17.46%；FY29 估值后折两年）
#
# **表1 · 档位构造**（USD/股；QTL：篮 3、税前 EBT × EV/EBIT，无 r；经营三腿：篮 4 r=10%、三档共用前瞻回报 35.15%，自身周期 66.4% 按前瞻封顶，Y1 FY27 / Y2 FY31 路径平；tau=0，无窗口利润）
#
# | 档 | QTL 腿 | Handsets 腿 | Auto 腿 | IoT 腿 | 合计 |
# |----|-------:|------------:|-------:|------:|-----:|
# | L | 27.91（EV/EBIT 10×，年金梯下沿） | 21.00（PE=8.33 · r=10% g2=−2%） | 19.42（PE=17.45 · r=10% g2=5.10% 同业重解） | 12.54（PE=11.79 · r=10% g2=2%） | **80.86** |
# | M | 42.51（EV/EBIT 12.4×，SOTP 税前中点） | 32.33（同上） | 27.07（同上） | 18.21（同上） | **120.12** |
# | H | 72.20（EV/EBIT 18.9×，IDCC 实测） | 38.30（同上） | 31.95（同上） | 21.26（同上） | **163.72** |
#
# - **分子阶梯**：税后 EPS 7.124 / 9.959 / 11.555；整票隐含倍数 11.35 / 12.06 / 14.17×，落在旧自身历史带 9.81–32.82× 内。
# - **实证坐标**：L 沿用 FY22→FY23 实测周期跌幅，FY23 GAAP EPS 6.42 与本表非 GAAP 7.124 不直接比较。H 为旧 FY27 共识区间上沿分部拆分，非多一年复利。原卖方低目标价 100（2026-09-09）只作历史交叉，不是本期新目标价。
# - **地板**：无资产地板，scenario_L 即 L；无分子年份漂移。
# - **可比性读数**：L/M **0.67** · H/M **1.36** · (H−L)/2M **34%** · V_opt/M **19.5%**。
# - **分解**：L/M=倍数比 0.94 × 分子比 0.72；H/M=倍数比 1.17 × 分子比 1.16。经营三腿倍数 flat，整票的倍数差来自 QTL 年金梯，非手机周期双压。原 2026-09-14 同类校准中位 L/M 约 0.72，当前稍低；H/M 扩张仍主要来自 QTL 梯。
# - **Flat@12.4× 对照**：只钉住 QTL 中档倍数、分子不变 → **87.56 / 120.12 / 138.89**。分子本身仍分开三档；高档多出的约 24.83/股来自 QTL 倍数情景。
# - **ROE 与时点**：FY26 年末权益 30.401B ÷ 暂用股数 1.073B = FY27 期初 BPS **28.33**；M EPS 9.959 ÷ BPS = **35.15%**。原 Q4 窗口利润 1.45/股与“实际留存 B 桶”1.41/股推演均退役，不能另加价值。
# - **本期核对边界**：汽车 Q4 年化约 $7.96B 已接近旧 FY27 H 的 $7.9B，但单季不是全年共识；本次未据此改收入预测。QTL 新续约状态已确认，费率提升未确认。DC 仍无独立整体利润，旧 FY27 亏损预测与闭合项暂留，不能把 3pp 单季拖累直接年化替代全年。
#
# **表2 · zone**（底牌五档区间；无现行价格位置）
#
# | zone | 中文 | 本票价格区间（USD） | 本票隐含场景（定价了什么） |
# |------|------|---------------------|----------------------------|
# | deep_discount | 深度折价 | \(P < 80.86\) | 低于旧周期压力情景与 QTL 年金梯下沿；须查手机是否发生超过旧周期的结构性损失、主要授权客户是否新增违约或法律风险。旧 FY2027–2031 续约悬念已由 A18 更新。 |
# | conservative | 保守 | \([80.86,\ 100.49)\) | 手机周期压力重演，FY27 手机收入 17.5B / margin 22%；QTL 收入 5.3B / margin 70%、按 10× 年金下沿估值。三条芯片腿回报按前瞻 35.15% 封顶、Y1 FY27/Y2 FY31 路径平；r 10%，g2 手机 −2%（定稿、无同业锚）、汽车 5.10%（车用同业重解）、物联网 2%（定稿、无同业锚）；tau=0。DC 上行计零、当期亏损保留。 |
# | neutral | 中性 | \([100.49,\ 141.92)\) | 旧 FY27 共识中枢兑现：收入约 44.8B，模型 EPS 9.959；QTL 12.4×。续约已完成但收入运行率不抬升；经营三腿参数同保守档（r 10%、前瞻回报 35.15% 不回落、Y1 FY27/Y2 FY31、g2 −2%/5.10%/2%、tau=0）。FY27 共识待更新。 |
# | optimistic | 乐观 | \([141.92,\ 163.72]\) | 手机 FY27 收入 23.5B / margin 27%、汽车 7.9B、物联网 8.3B，同时 QTL 按 IDCC 历史 18.9× 定价。本期汽车运行率支持近端增长，但基本维持费率的续约本身未验证高档授权增值。三条芯片腿参数仍同中性档，DC 上行不进底牌。 |
# | stretched | 叙事溢价 | \(P > 163.72\) | 超出已建模同年上沿，可能对应 FY29 DC 增量、远期非手机目标、整公司卖方更高倍数；可量化的 DC 增量仅在表3。主业稳态回报仍按 35.15% 封顶、Y1 FY27/Y2 FY31；不为远期目标抬主业 g2。 |
#
# **表3 · zone+V 修正带**（逐档相加后再取中点；DC r=10%，g2=6%，回报 35.15% 至 FY29、FY33 到 30%）
#
# | 档 | 底牌 | p_k | p_k·V_opt | 修正后 | 期权隐含场景 |
# |----|-----:|----:|----------:|-------:|---------------|
# | L | 80.86 | 0.00 | 0.00 | **80.86** | FY29 超出 FY27 已含 $5B 的增量不兑现；不取消底牌里的爬坡亏损。 |
# | M | 120.12 | 0.35 | 8.22 | **128.34** | 额外 $10B 收入只兑现 35%，即 FY29 DC 约 $8.5B；增量税后 EPS 约 0.496。参数同 H，只乘兑现比例；历史归属 / 客户覆盖率为概率坐标，非完整合同覆盖。 |
# | H | 163.72 | 1.00 | 23.48 | **187.20** | FY29 DC 到 $15B，减已含 $5B=$10B；×历史单家增量税前 margin 17.46%×(1−13%)÷1.073B=增量 EPS 1.4160；本票回报 35.15%、r 10%、g2 6%、FY29→FY33 到 30%，PE 20.07×，FY29 值 28.41，÷1.1²=23.48（tau=0）。 |
#
# 修正带切点 A′ = **104.60** · B′ = **157.77**。
#
# - **敏感性（只报底牌锚点，保持其他输入）**：
#   - 经营三腿 g2 同 −1pp → **75.43 / 112.26 / 154.45**；手机与物联网同 +1pp → **84.13 / 125.04 / 169.50**。
#   - 汽车 g2 −1pp → **78.10 / 116.28 / 159.19**；汽车到 cap 6% → **84.52 / 125.22 / 169.73**。
#   - QTL 梯固定中档 → **87.56 / 120.12 / 138.89**；旧 9/12/16 梯对照 **78.07 / 118.75 / 152.64**（已退役）。
#   - 手机 g2 改取联发科叙事混合读数的截顶 6% → **112.10 / 168.23 / 220.71**，未采用，原因见 A15。
# - **期权敏感性**：g2_dc 4% 且保持同一回报路径 → V_opt **16.95**；p_M 0.25 / 0.35 / 0.50 → 修正带中档 **126.00 / 128.34 / 131.87**，底牌不变。
# - **共享梯与护栏**：QTL 与 NOK 逐格相等；M ROE 下带边反解 g 约 −0.19%～7.61%，截 6%；三腿沿用定稿 g。历史带不入主公式，未为本期结果扩带。
#
# ### 交叉校验（非主公式）
#
# | 方法 | 本期读数 / 来源日期 | 结论 |
# |------|--------------------|------|
# | 共识对账 | FY27 模型 EPS 9.959 vs 旧共识 10.22（2026-09-10） | −2.6%，未达旧 15% 偏离阈值；**共识待更新**，不称为新共识验证 |
# | 实际利润桥 | FY26 QCT+QTL EBT 14.123B − non-GAAP EBT 12.976B=1.147B；Q4 差额 0.394B（S1） | 不将 GAAP SBC 再扣一次；不把 FY26 差额自动等同 FY27 闭合项 |
# | DC 单位经济 | 固定原股本后增量 EBT margin 17.46%，本期增量 EPS 1.4160/股对 $10B 收入 | 仍为 HSBC 96032 单家历史敏感性；不是本期公司分部利润 |
# | 卖方估值矩阵 | 历史 QTL SOTP EV $45–55B、整公司 HSBC 17× / UBS 16× / 巴克莱 16×；2026-09-09 TP median 175、mean 193.9 | 历史交叉，均非财报后刷新；本框架 M 12.06×仍低于其整体倍数，不能直接借目标倍数抬尺 |
# | ROE / PEG | M 前瞻回报 35.15%，分母为实际期初权益；FY27 EPS 增速仍待刷新 | GAAP 12.70 含税项，不拿来混算 non-GAAP 前瞻增长 |
# | 现金流 / 债务 | FY26 CFO 11.145B−capex 2.494B=FCF 8.651B；有息债 15.112B−现金短投 7.681B=净债 7.431B（S2） | 不沿用旧 FCF 10.24B；现金流覆盖资本开支，不新增超额现金腿 |
#
# ## 4. Changelog
#
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
#
# ### 2026-11-05
#
# **事件：FY26Q4 / FY26 年报发布（美东 2026-11-04 盘后）。**Q4 GAAP 收入 $10.322B、non-GAAP 收入 $10.442B / EPS 2.17；手机收入 −26%、汽车 +89%。FY27Q1 EPS 指引 2.15–2.35；公司文件 S1/S2、电话会转录 S3 见 §0。
#
# - **假设核对**：A3（纯周期解释）、A7（股本 1.062B）、A8（DC 亏损金额依据）削弱；A4 旧 FY2027–2031 到期窗口证伪，新增 A18 确认苹果 / 华为 / 传音续约及新 FY2030–2033 窗口。A6 年度税率与排除 SBC、A9 排除 QSI 确认。A16 旧 Q3 权益推演失效，新增 A19 采用实际年末权益；A17 旧窗口撤销、稳态路径保留。A1/A2/A5/A10/A11/A12/A13/A14/A15 维持或修正文义，证据与限制逐条见 §2。
# - **实际数先入库**：§0 as-of 更新到 FY26Q4 / FY26 期末 2026-09-27；equity 27.950B → 30.401B；shares 1.062B → Q4 实际 1.073B（FY27 暂用代理，非全年预测已获确认）；不重复加 AWS 权证。FY27 收入、分部利润率与闭合项保留原预测日期并标 **共识待更新**，不因共识滞后推迟本期落盘。
# - **重算**：估值基准更新至 FY26 年末，tau 0.25205→0，取消已实现 Q4 窗口利润 1.45/股；ROE_M 38.21%→35.15%。L/M/H **82.20 / 121.41 / 165.21 → 80.86 / 120.12 / 163.72**（−1.6% / −1.1% / −0.9%）；切点 **100.49 / 141.92**。QTL 倍数梯、经营腿长期增速及稳态回报来源不变；汽车单季年化接近旧高档，尚未替代全年分子。
# - **期权**：FY27 $5B / FY29 >$15B 目标重申，p=0/0.35/1 不变。固定 HSBC 敏感性的源美元利润，随本期股本换算，增量利润率仍 17.46%；V_opt **23.20→23.48**，修正带 **80.86 / 128.34 / 187.20**。DC 并入 QCT 不等于独立盈利已披露，仍保留亏损于闭合项；未来更新需去重。
# - **演算版本**：v2→v3，实际期初权益替代旧 Q4 推演；HSBC 单位经济显式固定源股本。
# - touched: [题头, §0, §1 业务地图与 DC, A1–A19, §3 Inputs/Formula/Outputs/交叉校验, eval/QCOM.US.py]
#
# ### 2026-10-03
#
# - 规则迁移（valuation-rules「未建模期权」/「增长的表达顺序」2026-10-03）：① \(V_{opt}\) 36.48 → **24.92**——份数改为公司 FY29 DC 目标 >$15B 减共识已含的 FY27 指引 $5B（Investor Day 2026-06-24）= $10B；单位经济仍取 HSBC 96032 敏感性（腿级卖方·单家，增量税前利润率 17.5%），撤销借用的 HSBC 目标倍数 17×，改本票尺 `perpetual_pe`(g2_dc 6% 半导体簇截顶, ROE_M 38.2%, r 10%) 21.07× 在 FY29 估值、折回 FY27 两年；v1「知情偏离」失效。② `g2_auto` 6%（无同业锚、贴顶表达近端高增）→ **5.02%**（车用 / 模拟簇 NXPI / TXN 反解中位，`AVGO.US` A18）。L/M/H 85.83 / 127.14 / 172.23 → **81.75 / 121.45 / 165.51**（M −4.5%，未触发纠正对账门）；修正带 85.83 / 139.91 / 208.71 → 81.75 / 130.17 / 190.42。`formula_id` v1 → v2；QTL 年金梯与 NOK 跨文件校验不动
# - touched: [题头, §0, §1 DC 条目, A10, A11, A15, A16, Inputs（删 `v_opt`；增 `dc_*` / `hsbc_*` / `g2_dc_src` / `t_opt`；改 `g2_auto`）, Formula 步 6, 表1/2/3, 敏感性, 交叉校验, eval]
#
#
# ### 2026-09-20
#
# - v2 切换（篮子 r）：L/M/H v1 85.84 / 127.15 / 172.23 → 85.84 / 127.15 / 172.23（无变化：`r_op` 只进经营三腿，篮 4 的 10% 与 v1 同值；QTL 腿无 r），zone `stretched` → `stretched`（修正带 `optimistic` 不变）；篮子：Handsets / Auto / IoT 篮 4 龙头制造 10%，QTL 篮 3 按量专利许可（主尺仍 EV/EBIT 年金阶梯 10 / 12.4 / 18.9，8.5% 不进公式、无 r 行）；g2 三腿沿用 v1 值 −2% / 6% / 2%（cap = min(6%, r−4%) = 6% 未收紧）；新增 A15 归篮与披露行（隐含 r(P) δ −2.20% → 三腿 7.8%、g2 ±1pp 无翻转、③ 不出带、无地板）。分子（FY27 四腿、闭合项、V_opt）不动；`eval/QCOM.US.py` 改 `check_r(r, "r_op", 篮 4)` / `check_g_cap(g2, r)`，并打印隐含 r(P) 与 g2 ±1pp 杠杆
# - touched: [A15, r_op, g2_hs, g2_auto, g2_iot, 披露行]
#
# ### 2026-09-10
#
# **事件：高通与 AWS 达成多代定制芯片协议（公告 2026-09-09）。** FY27 贡献约 20 亿，字节跳动「类似规模」为第二家具名超大厂；权证 2,500 万股 @ $161.26 按**绑定采购订单**分批归属、上限对应十年 600 亿采购，首批已归属 375 万股（隐含约 90 亿订单）。公司同期重申 FY29 数据中心收入 150 亿。
#
# - **A11 被证伪 → 重写**：原 \(p_M=0.25\) 的依据「自研加速器尚无任何已披露客户或订单」不再成立。改 \(p_M=0.35\)，并从「无概率锚·拍值」升级为**有锚**——权证已归属 15%、两家具名客户覆盖 FY27 指引 80%。
# - **DC 仍留 \(V_{opt}\)，未做成腿**：收入分子已可算（卖方 FY27 落 20 / 50 / 52 亿），但**盈利分子仍为负**。实测把亏损移出闭合项再配正腿，共识对账从 −1.5% 漂到 **+5.7%**，故维持「当期亏损进底牌闭合项、上行进期权」的分工。
# - **\(V_{opt}\) 换锚 33.04 → 36.48**：旧锚（自身 Automotive 腿）与 DC 无因果关系；新锚为卖方残差反推——HSBC 敏感性隔离出「每 10 亿 DC 收入 = 2.43/股」，乘公司 FY29 目标 150 亿。属知情偏离 A2e-7c-1，理由与旧锚对照记于 §1。
# - **A7 股本 1.060e9 → 1.062e9**：AWS 权证按**库藏股法**计入 1.84M 股（非巴克莱所称 2% 的总股数口径）。
# - **A8 补证**：HSBC 敏感性隐含 DC **增量 EBT margin 17.5%**，为目前唯一有来源的 DC 利润率数据点；属增量口径，不推翻「20 亿基数上整体仍亏损」。
# - **门槛上移**：定制 ASIC 的**收入侧**升级门槛已触发，新门槛改为「DC 分部 EBT 被披露且转正」。原证伪触发器「FY27 结束时 DC 收入 <10 亿」作废——卖方最低口径已给到 20 亿，该条不再有区分力。
#
# `touched`: 题头 · §0 · §1（DC 具名条目）· A7 · A8 · A10 · A11 · §3 Inputs（`shares`）· 表1/2/3 · 敏感性 · 交叉校验 · `eval/QCOM.US.py`
