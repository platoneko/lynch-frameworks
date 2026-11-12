#!/usr/bin/env python3
"""VIAV historical FY28 earnings and three-stage Gordon valuation.

Amounts USD millions, shares are absolute counts and prices USD per share.
Forecasts and older balance-sheet inputs retain their source dates below.
The historical model is conditional on the unresolved issues in the document.
"""
from lib.partial_basis import local_basis_changed
from lib.gordon import check_g_cap, check_r
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries': ('partial_basis', 'gordon', 'rf_report'),
                'axes': {'plug': 'pluggable_module', 'capex': 'ai_capex'}}
TIERS = ('L', 'M', 'H')
# Q1 FY27 earnings release (2026-11-04):
# https://www.sec.gov/Archives/edgar/data/912093/000162828026070170/viavq1fy278-kex991.htm
# FY27/FY28 consensus was queried from yfinance/Longbridge on 2026-11-05;
# it had not yet incorporated the earnings release. The single-house candidate
# is a Rosenblatt estimate reported by Longbridge on 2026-09-23.
HISTORICAL_PARTIAL_FINGERPRINT = '51cda5de94b41cc6f156d23ec054acc8734ca1cefed73a4c819b328ad5c4bb2f'
INPUTS = {
    'shares_basic': 246749828.0,  # 在外流通股（10-K 封面，2026-07-25）; as-of 2026-07-25
    'dil_q4': 21700000.0,  # FY26 Q4 non-GAAP 稀释股数 261.0M − basic 239.3M（8-K）；街 EPS 股数基 = shares_basic + dil_q4（A11）; as-of 2026-06-27
    'conv_shares': 18132400.0,  # 2031 可转债全转股数 = 250M × 72.5295 / 1000（10-K Note 11）; as-of 2026-06-27
    'conv_price': 13.79,  # 2031 可转债初始转股价（10-K Note 11）; as-of 2026-06-27
    'conv_principal': 250.0,  # 2031 可转债本金 $M; as-of 2026-06-27
    'conv_carry': 245.1,  # 2031 可转债账面值 $M（FY27 Q1 8-K）; as-of 2026-10-03
    'px_q4_avg': 47.42,  # FY26 Q4（2026-03-27~06-26）日收盘均值，只用于拆 Q4 稀释股数中的可转债净股（A11）; as-of 2026-06-26
    'equity': 1324.3,  # 股东权益 $M（FY27 Q1 8-K，已含 Q1 GAAP 净利 76.0）; as-of 2026-10-03
    'cash': 528.8,  # 现金及等价物 526.7 + 短投 2.1；排除受限 6.5 $M（FY27 Q1 8-K，初步）; as-of 2026-10-03
    'notes_2029': 400.0,  # 3.75% 2029 优先票据本金 $M; as-of 2026-06-27
    'contingent': 76.9,  # Inertial Labs 或有对价公允价值 $M（类债，A10）; as-of 2026-06-27
    'cash_yield': 0.0285,  # 现金税前收益率 = FY26 利息及其他收入 15.3M ÷ 年均现金及短投（(425.3 + 649.8) / 2）（A10）; as-of 2026-06-27
    'coupon_2029': 0.0375,  # 2029 票据票息; as-of 2026-06-27
    'coupon_conv': 0.00625,  # 2031 可转债票息; as-of 2026-06-27
    'tax': 0.15,  # non-GAAP 有效税率 = 1 − 243.8 ÷ (312.9 − (47.4 − 5.8) + 15.3)（8-K 调节表）; as-of 2026-06-27
    'eps_fy27_m': 1.64374,  # FY27 共识 non-GAAP EPS 均值（8 家，1.48–1.7899）；yfinance 查询；共识待更新; as-of 2026-11-05
    'rev_fy27_m': 1886.7319,  # FY27 共识收入均值 $M（7 家）；yfinance 查询；共识待更新; as-of 2026-11-05
    'eps_fy28_l': 1.71,  # FY28 共识下沿（7 家），只作对照；共识待更新; as-of 2026-11-05
    'eps_fy28_m': 1.95071,  # FY28 共识 EPS 均值（7 家）；共识待更新; as-of 2026-11-05
    'eps_fy28_h': 2.185,  # FY28 共识 EPS 上沿（7 家）；共识待更新; as-of 2026-11-05
    'rev_fy28_m': 2140.43559,  # FY28 共识收入均值 $M（6 家，2,013.6–2,311.4）；共识待更新; as-of 2026-11-05
    'eps_fy28_cand': 3.0,  # Rosenblatt 单家 FY28 EPS（约数），只进候选带 H′（A16）; as-of 2026-09-23
    'sbc_ttm': 64.7,  # 滚动四季 SBC + 雇主税 = FY26 58.1 − FY26 Q1 15.0 + FY27 Q1 21.6 $M；TTM口径，A9; as-of 2026-10-03
    'rev_ttm': 1688.5,  # 滚动四季收入 = 1,518.3 − 299.1 + 469.3 $M；TTM口径，A9; as-of 2026-10-03
    'osp_rev_q1g': 93.2,  # FY27 Q1 OSP 实际收入 $M，替换原指引 91；按原拆分规则年化 × 4（A6）; as-of 2026-10-03
    'osp_om_q1g': 0.432,  # FY27 Q1 OSP 实际利润率（A6）；原指引同为 43.2%; as-of 2026-10-03
    'osp_oi_fy26': 122.9,  # OSP 分部利润 FY26 $M = L 档 OSP（A6）、g_osp 终点（A8）; as-of 2026-06-27
    'osp_oi_fy17': 100.5,  # OSP 分部利润 FY17 $M（FY19 10-K）；g_osp 起点（A8）; as-of 2017-07-01
    'nse_rev_fy22': 949.1,  # NSE 收入 FY22 $M（FY23 10-K）；L 档退坡幅度起点（A6）; as-of 2022-07-02
    'nse_oi_fy22': 147.8,  # NSE 分部利润 FY22 $M（FY23 10-K）; as-of 2022-07-02
    'nse_rev_fy24': 702.0,  # NSE 收入 FY24 $M（FY26 10-K 重述口径）; as-of 2024-06-29
    'nse_oi_fy24': 8.7,  # NSE 分部利润 FY24 $M（FY26 10-K 重述口径）; as-of 2024-06-29
    'dc_share_nse': 0.5,  # 数据中心占 NSE 收入比例（FY26 Q4 电话会「约 50%」）；只用于轴隐含份额（A24）; as-of 2026-08-05
    'r_perp': 0.1,  # 永续折现率 = 篮 4 常规经营 10%：NSE 测试仪器价格公司议定、盈利随客户研发与扩产周期，非商品价函数；OSP 单一客户是 SICPA 独家营销渠道、终端为分散的央行，不按单押归篮（A3）；`check_r`; as-of 2026-10-02
    'g_nse': 0.06,  # NSE 永续增速 = 同业反解中位 7.50% 截到 cap min(6%, r − 4%)（A7）；`check_g_cap`; as-of 2026-10-02
    'g_peer_median': 0.075,  # 测试设备簇反解原值（KEYS / TER / ONTO / FORM / CAMT 中位）；记录与证伪点，不进公式（A7）; as-of 2026-10-02
    'g_osp': 0.0226,  # OSP 永续增速 = 自身 FY17→FY26 分部利润 CAGR（无同业锚，A8）; as-of 2026-06-27
    'k_l': 0.0,  # 打折 k：0（原 0.3 / 0.4 / 0.5 乘在「视同派出」行上，即多留部分，乘错对象，2026-10-16 去掉；valuation-rules「经营价值与超额现金」④；A12）; as-of 2026-10-16
    'k_m': 0.0,  # 同上（原 0.4）; as-of 2026-10-16
    'k_h': 0.0,  # 同上（原 0.5）; as-of 2026-10-16
    'ss_return': 0.128,  # L / M 档稳态回报 = 自身最近一轮谷到谷 FY2017–FY2024 均值：GAAP 营业利润加回收购摊销（与前瞻剔摊销同口径）× (1 − 15%) ÷ 年初投入资本（含经营租赁）；同业层空（测试测量无 ≥ 5 年成熟同业），兜底 15% 只作对照；各档 min(ROE, 本值)；用户 2026-10-19 认可；A25; as-of 2026-10-19
    'ss_return_h': 0.249,  # H 档稳态回报 = 高档去周期前瞻：FY28 H 核心利润率 23.7% 减周期高点抬升 3.9pp（FY19–24 峰减均值）与经常性重组 1.1pp → 18.8% × FY19–24 平均周转 1.323；≤ 原测算H前瞻32.2%、≤ 30%（「三档各取各的稳态」高档认卖方预测里的提升）；用户 2026-10-19 认可；A25; as-of 2026-10-19
    'num_year': 2028,  # 分子年（FY2028，按财年记日历）；回报路径 t = 1；A25; as-of 2026-10-16
    'tau': 0.7479452055,  # 估值日 2026-10-03 → FY28 年初约 2027-07-03；273 / 365（A26）; as-of 2026-10-03
    'ni_booked_fy27': 125.8,  # 已入账 FY27 Q1 non-GAAP 净利 $M（8-K）；按主尺同一 SBC 折扣转换后从全年预测扣除（A26）; as-of 2026-10-03
    'window_fraction': 0.7358490566,  # FY27 剩余 273 天 / 全年 371 天；只缩放窗口净利息与转股票息，不缩放已扣实际的剩余利润（A26）; as-of 2026-10-03
}

def _lin(cal: int, y1: int, y2: int, a: float, b: float) -> float:
    """a through Y1, linear to b at Y2, b after (valuation-rules ② 稳态回报三段)."""
    if cal <= y1:
        return a
    if cal >= y2:
        return b
    return a + (b - a) * (cal - y1) / (y2 - y1)


def path_value(t0: int, y1: int, y2: int, r_s: float, g: float, roe: float, r: float) -> float:
    """Gordon multiple on next-period earnings with the three-segment RONIC path (A25); t = 1 <->
    fiscal year t0; ROE through Y1, linear to min(ROE, r_s) at Y2, Gordon tail after."""
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


def evaluate(inp, rate_inputs=None):
    # Company-wide path uses the shared timing, but company-specific steady
    # returns: FY17-24 trough-cycle 12.8% and high-case de-cycled 24.9%.
    r, t = inp['r_perp'], inp['tax']
    errors = check_r(r, 'r_perp', 4) + check_g_cap(inp['g_nse'], r, 'g_nse')
    if errors:
        raise ValueError('; '.join(errors))
    ks = (inp['k_l'], inp['k_m'], inp['k_h'])
    y0, y1, y2, tau = inp['num_year'], inp['y1'], inp['y2'], inp['tau']
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (y0, y1, y2)) or not y0 <= y1 < y2:
        raise ValueError('invalid return path years')
    rs_tier = {'L': inp['ss_return'], 'M': inp['ss_return'], 'H': inp['ss_return_h']}
    def pp(gg, roe, rr, tier):
        return path_value(y0, y1, y2, rs_tier[tier], gg, roe, rr)

    # ---- Step 1: share bases (A11) ----
    s_cons = inp["shares_basic"] + inp["dil_q4"]  # street EPS base: post-offering basic + Q4 dilution
    net_conv_q4 = inp["conv_shares"] * (1 - inp["conv_price"] / inp["px_q4_avg"])
    d_rsu = inp["dil_q4"] - net_conv_q4
    s_debt = inp["shares_basic"] + d_rsu
    s_conv = s_debt + inp["conv_shares"]
    if d_rsu <= 0:
        raise ValueError("implied RSU dilution must be positive")

    # ---- Step 2-3: SBC haircut, net interest (A9, A10) ----
    sbc28_at = inp["sbc_ttm"] / inp["rev_ttm"] * inp["rev_fy28_m"] * (1 - t)  # $M after tax
    ni_m_street = inp["eps_fy28_m"] * s_cons / 1e6
    haircut = sbc28_at / ni_m_street
    net_int_pre = (inp["cash"] * inp["cash_yield"] - inp["notes_2029"] * inp["coupon_2029"]
                   - inp["conv_principal"] * inp["coupon_conv"])
    int_at = net_int_pre * (1 - t)
    coupon_at = inp["conv_principal"] * inp["coupon_conv"] * (1 - t)

    # Q1 is already in the latest equity. Only the remaining annual profit and
    # remaining-period interest/coupon may enter the opening-book roll and window.
    unbooked_street = inp["eps_fy27_m"] * s_cons / 1e6 - inp["ni_booked_fy27"]
    window_fraction = inp["window_fraction"]
    if unbooked_street < 0 or not 0 <= window_fraction <= 1:
        raise ValueError("invalid booked profit or remaining-year fraction")

    # ---- Step 4: L numerator, bottom-up FY28 digestion year (A6) ----
    osp27_rev = inp["osp_rev_q1g"] * 4
    osp27_oi = osp27_rev * inp["osp_om_q1g"]
    oi27 = inp["eps_fy27_m"] * s_cons / 1e6 / (1 - t) - net_int_pre
    nse27_rev = inp["rev_fy27_m"] - osp27_rev
    nse27_oi = oi27 - osp27_oi
    drop = 1 - inp["nse_rev_fy24"] / inp["nse_rev_fy22"]
    decr = (inp["nse_oi_fy22"] - inp["nse_oi_fy24"]) / (inp["nse_rev_fy22"] - inp["nse_rev_fy24"])
    nse_l = nse27_oi - decr * drop * nse27_rev
    osp_l = inp["osp_oi_fy26"]
    eps_l_street = (nse_l + osp_l + net_int_pre) * (1 - t) * 1e6 / s_cons
    street = {"L": eps_l_street, "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}

    # ---- Step 5: blended g (A7, A8) ----
    osp28 = osp27_oi * (1 + inp["g_osp"])
    oi28_m = ni_m_street / (1 - t) - net_int_pre
    w_nse = (oi28_m - osp28) / oi28_m
    g = w_nse * inp["g_nse"] + (1 - w_nse) * inp["g_osp"]
    if not 0 <= g < r:
        raise ValueError("blended growth must be below discount rate")

    # ---- Step 6-8: per basis value, rolled ROE, Gordon PE, k (A10-A12) ----
    closing_conv = inp["cash"] - inp["notes_2029"] - inp["contingent"]
    bases = {
        "debt": dict(s=s_debt, extra=0.0, closing=closing_conv - inp["conv_principal"], eq=inp["equity"]),
        "conv": dict(s=s_conv, extra=coupon_at, closing=closing_conv, eq=inp["equity"] + inp["conv_carry"]),
    }

    def deck(rr: float, gg: float, eps: dict[str, float]) -> dict[str, dict]:
        out = {}
        for i, tier in enumerate(TIERS):
            best = None
            for name, b in bases.items():
                core = eps[tier] * s_cons / 1e6 * (1 - haircut) - int_at + b["extra"]
                unbooked = unbooked_street * (1 - haircut) + (b["extra"] - int_at) * window_fraction
                op0 = b["eq"] - b["closing"]
                share = gg * unbooked / core
                if share >= 1:
                    raise ValueError(f"book roll diverges at {tier}/{name}: g·N/core = {share:.2f}")
                book = op0 / (1 - share)
                roe = core / book
                pe = pp(gg, roe, rr, tier)
                pre_k = (core * pe + b["closing"]) / b["s"] * 1e6  # FY28-opening operating value + closing
                excess = (1 - gg / roe) * unbooked / b["s"] * 1e6  # = FY27 window distributable profit
                # A26: operating value tau back to today, window at tau / 2, closing item not discounted.
                timed = (core * pe / (1 + rr) ** tau + b["closing"]) / b["s"] * 1e6 + excess / (1 + rr) ** (tau / 2)
                val = timed - ks[i] * excess
                row = dict(basis=name, core_ps=core / b["s"] * 1e6, roe=roe, pe=pe, pre_k=pre_k,
                           excess=excess, val=val, core=core, book=book, unbooked=unbooked)
                if best is None or val < best["val"]:
                    best = row
            out[tier] = best
        return out

    d = deck(r, g, street)
    L, M, H = (d[x]["val"] for x in TIERS)
    if not (L < M < H):
        raise ValueError("anchors must increase")

    # The candidate changes only high EPS; each capital structure is still
    # re-evaluated and the lower per-share value is selected by the old model.
    candidate_street = dict(street, H=inp['eps_fy28_cand'])
    candidate = deck(r, g, candidate_street)
    band = lambda rows: {tier: rows[tier]['val'] for tier in TIERS}
    result = {
        'ticker': 'VIAV.US', 'currency': 'USD', 'valuation_as_of': None,
        'framework_as_of': None, 'historical_valuation_as_of': '2026-11-05',
        'historical_framework_as_of': '2026-11-05', 'basis_changed': None,
        'anchors': band(d), 'candidate': {'label': 'Rosenblatt 单家预测', 'anchors': band(candidate)},
        'option': None, 'units': {'price': 'USD_PER_SHARE'},
        'segments': {'company': {'unit': 'USD_PER_SHARE', 'values': band(d)}},
        'key_parameters': {
            'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys(TIERS, r)},
            'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys(TIERS, g)},
            'forward_return': {'unit': 'RATIO', 'values': {tier: d[tier]['roe'] for tier in TIERS}},
            'steady_return': {'unit': 'RATIO', 'values': {tier: min(d[tier]['roe'], rs_tier[tier]) for tier in TIERS}},
        },
        'review_flags': ['historical_consensus_pending_update', 'historical_dilution_cash_yield_tax_and_contingent_balance_unverified',
                         'historical_funding_and_comparable_band_unverified'],
    }
    if rate_inputs is not None:
        def band_at(dr=0.0):
            rows = deck(r + dr, g, street)
            return tuple(rows[tier]['val'] for tier in TIERS)
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': r}, band_at=band_at,
            rates_loader=lambda _currency: rate_inputs,
            base_anchors=tuple(result['anchors'][tier] for tier in TIERS)))
    return result


def calculate(context):
    plug = context['axes']['plug']
    capex = context['axes']['capex']
    if capex['role'] != 'demand_reference':
        raise ValueError('VIAV requires the AI demand reference role')
    selected = {'y1': plug['y1_plug'], 'y2': plug['y2_plug']}
    result = evaluate({**INPUTS, **selected}, context.get('rate_inputs'))
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'selected_path': selected}, HISTORICAL_PARTIAL_FINGERPRINT)
    # AI spending is a contextual reference, not an input to the price band.
    result['ai_capex_reference'] = dict(capex['rungs'])
    return result
