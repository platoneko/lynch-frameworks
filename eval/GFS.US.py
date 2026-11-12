"""Historical model snapshot for GFS.US, migrated from the user's working copy."""
from __future__ import annotations
import math
from lib.gordon import g_cap, payout
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'zones', 'partial_basis'), 'axes': {'sipho': 'sipho_wafer', 'foundry': 'mature_foundry'}}
BASELINE_LOCAL = 'd25a41aa98a4e146213a2268ebc4e34d74812854d27509d8da3cc5ce82fb832e'
AXIS_FIELDS = ('g2_sipho_src', 'gm_sipho', 't_align', 'ss_return_cap_sipho', 'ss_return_sipho_ref', 'y1_sipho', 'y2_sipho')
NUM_YEAR = 2027
P_TIERS = (0.0, 0.25, 1.0)
MONTHS = 12
TIERS = ('L', 'M', 'H')
INPUTS = {
    'shares': 558000000.0,  # Q3'26 实际 non-IFRS 稀释股数；Q4 指引约575M 另列，旧共识未证实包含新稀释，不机械二次调整 EPS 2026-09-30
    'equity': 11929000000.0,  # 归母权益；Q3'26 中期报表（6-K 附件） 2026-09-30
    'net_cash': 2009000000.0,  # 沿原现金单列结构：现金997 + 短期证券1258 + 长期证券957 − 债1136 − 已宣派未付股息67（累计宣派133−已付66），$M；不再重复扣该67 2026-09-30
    'nii_4q': 50000000.0,  # TTM 净利息：FY25Q4 17（旧来源保留）+ FY26前三季33；Q2原文净利息9，纠正旧季度排列；A6 2026-09-30
    'sbc_annual': 258000000.0,  # 沿近两季现金流口径：Q2 68 + Q3 (前三季189−上半年128)=61，合计129×2；non-IFRS调整表Q3为50、Q2为86，口径不同不混接；A9 2026-09-30
    'tax': 0.1,  # 正常化税率（SBC / 净利息税后、候选带 NI 用） 2026-09-14
    'eps_2026_m': 1.9567,  # FY2026E 共识均值（19 家，non-GAAP）= **L 分子（消化年）**；A3。也是 A20 账面滚动的 Q4'26 未入账利润的来源（扣 `eps_ytd_a`）；共识待更新 2026-09-11
    'eps_ytd_a': 1.39,  # 前三季实际 non-IFRS EPS=0.40+0.46+0.53；Q3已入账，只滚Q4；A20 2026-09-30
    'window_fraction': 0.25,  # 未入账利润窗口=Q4；税后年度SBC和净利息只扣四分之一；A20 2026-09-30
    'payout_ytd': 0.084507,  # 本期现金股息66M ÷ 前三季non-IFRS净利(227+256+298)=781M；非GAAP法定派息率、非三年均值；只作披露，回购500M另列，不进BPS 2026-09-30
    'eps_2027_l': 2.4,  # FY2027E 共识低端（21 家）；只作 A3 校验坐标，不进公式；共识待更新 2026-09-11
    'eps_2027_m': 2.6241,  # FY2027E 共识均值 = M 分子；A3；共识待更新 2026-09-11
    'eps_2027_h': 3.63,  # FY2027E 共识高端 = H 分子；A3；共识待更新 2026-09-11
    'eps_2027_gaap_m': 2.174,  # 2027E GAAP 共识（marketscreener 22 家）；g1 分母；A4；共识待更新 2026-09-14
    'eps_2028_gaap_m': 3.049,  # 2028E GAAP 共识（同源，仅均值）；g1 分子；A4；共识待更新 2026-09-14
    'n_stage': 1.0,  # 过渡年数（仅 2028E），只在 M/H；A4 2026-09-14
    'n_consensus': 1.0,  # 有 ≥2 家共识的远期年数；2029E 无 2026-09-14
    'rev_2026': 7307000000.0,  # FY2026E 营收共识均值（yfinance 22 家）；L 档资本占比分母；共识待更新 2026-10-03
    'rev_2027': 8222000000.0,  # FY2027E 营收共识均值（yfinance 21 家，7.90–8.99B）；M/H 资本占比分母；共识待更新 2026-10-03
    'sipho_rev_2026': 420000000.0,  # FY2026 硅光收入：2025 「翻倍至 >$200M」→ 2026「超过翻倍」（Q4'25 / Q2'26 电话会 99448）；公司口径下限；A21；旧路径暂留，Q3电话会媒体转述的FY26约500M及2027年底1B年化未获全年分布，不把年化直接当全年 2026-08-05
    'sipho_rev_2027': 615000000.0,  # FY2027 硅光 = FY26 与 FY28 的几何中点（公司目标路径插值）；A21；旧路径暂留，Q3电话会媒体转述的FY26约500M及2027年底1B年化未获全年分布，不把年化直接当全年 2026-10-03
    'sipho_rev_2028': 900000000.0,  # FY2028 硅光 = 「出 2028 年 $1B run-rate」线性爬坡的全年值（Investor Day 2026-05-07）；视同已在 2028 营收共识（9.34B ≈ 公司模型 9.29B；原文数量级笔误纠正）内；A21；旧路径暂留，Q3电话会媒体转述的FY26约500M及2027年底1B年化未获全年分布，不把年化直接当全年 2026-10-03
    'opex_ratio': 0.179568,  # Q3 IFRS 研发184+销售管理157，除以营收1899；含SBC，与经济口径一致；A21 2026-09-30
    'r_perp': 0.1,  # 篮 4 龙头制造：成熟制程代工龙头，周期但盈利不是商品价函数（街 WACC 中位 10.6%；备选 6 撤销）；A19 2026-09-18
    'pe_own_min': 15.6,  # 自身前瞻 PE 带低点（2021-10 = IPO ≠ 当前成交）；**③ 护栏（2026-09-19 恢复）**；A7 2026-09-11
    'pe_own_max': 46.2,  # 自身前瞻 PE 带高点（2023-03）；③ 护栏（2026-09-19 恢复）；A7 2026-09-11
    'bvps': 21.40016,  # 归母权益11929M ÷ 期末实际股数557.448741M；不用加权稀释股数 2026-09-30
    'pb_own_min': 1.55,  # 自身实测 PB 低点（2025-08 月末）；**坐标**，不作地板；A8 2026-09-11
    'rev_2025': 6791000000.0,  # FY2025 营收 USD；候选带基数；A17 2025-12-31
    'cagr_model': 0.11,  # Analyst Day 2025→2028 营收 CAGR 10–12% 取中；A17 2026-05-07
    'cagr_model_hi': 0.12,  # Analyst Day 2025→2028 营收 CAGR 区间上沿 = H′ 的 2028 封顶水平（水平型，不换算成增速再乘到 H 档）；A17 2026-05-07
    'opm_model_2028': 0.25,  # Analyst Day 2028 营业利润率目标；A17 2026-05-07
    'opt_target_rev': 2000000000.0,  # 公司2030硅光收入目标；Investor Day 2026-05-07。实际期权份数由该目标减H底牌同单位经济2030已含收入；不直接使用旧1.1B差额；A10 2026-05-07
    't_opt': 2030.0,  # 兑现年 = 公司目标年；A10 2026-05-07
    'y1_rest': 2028.0,  # 成熟代工腿高回报期 Y1 = 可见年末（默认路径；A22） 2026-10-16
    'y2_rest': 2032.0,  # 成熟代工腿 Y2 = Y1 + 4（门槛「中」，不确定：成熟制程新厂 2–3 年、客户认证约 1 年、中国大陆新增产能抢份额快、单位产能投资高；A22） 2026-10-16
    'rs_rest': 0.1,  # 成熟代工腿稳态回报 = max(r, 自身周期) = **10%**：自身最近一轮谷到谷 FY2020–FY2024（收入谷 2020 $4.85B / 2024 $6.75B）投入资本口径均值约 1.5%（`rs_rest_own`）< r 10% → 取 r；本期前瞻 L / M 7.27 / 9.99% 低于它 → 按前瞻不回落，本期H 15.15% 2028→2032 回落到 10%。同业中位 18.15%（高塔 19.4 / 联电 16.9%）与兜底 15% 只作对照；A22 2026-10-19
    'rs_rest_own': 0.015,  # 成熟代工腿自身周期读数（只作校验，不直接进倍数）：FY2020–FY2024 税后 GAAP 经营利润 ÷ 年初投入资本（权益含少数股东 + 有息负债 + 租赁 − 现金及短投），逐年 −16.3 / −0.5 / 15.2 / 10.4 / −1.5%，均值约 1.5%；2019 年末债务标签缺（补上只把 2020 拉近 −13%），去掉 2020 的 FY2021–FY2025 均值 6.2%，任何读法都 < r；eval 校验 `rs_rest` = max(`r_perp`, 本值)；A22 2026-10-19
    'tau': 0.25,  # 估值基准2026-09-30到FY2027年初约一季度；窗口同步只留Q4；A13/A22 2026-09-30
    'parent_ratio': 0.995244,  # 归母11929 ÷ 总权益11986；Q3中期报表；A22 2026-09-30
}

def path_value(g1: float, n: int, g2: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the numerator-year earnings, valued at the start of the numerator year,
    on the steady-state-return path (valuation-rules「经营价值与超额现金」② 稳态回报三段;
    gordon.py's three-segment function is not built yet, so it lives here).

    t = 1 is the numerator year t0; the first n years grow at g1 (two_stage_pe's stage 1),
    then g2 with RONIC = forward through Y1, linear to min(R_s, forward) by Y2, then the
    Gordon tail.  With R_s >= forward it is exactly two_stage_pe / perpetual_pe (A22)."""
    rs_eff = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs_eff
        return roe + (rs_eff - roe) * (cal - y1) / (y2 - y1)

    if r - g2 <= 0:
        raise ValueError(f"perpetuity diverges: g={g2} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g2, rs_eff) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * payout(g2, ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def calculate(context):
    inp = {**INPUTS, **{k: context['axes']['sipho'][k] for k in AXIS_FIELDS},
           **context['axes']['foundry']}
    if any(not math.isfinite(value) for value in inp.values()):
        raise ValueError('inputs must be finite')
    if inp['shares'] <= 0 or inp['equity'] <= inp['net_cash'] or inp['r_perp'] <= 0 or inp['tax'] >= 1:
        raise ValueError('invalid base denominator or discount rate')
    for key in ('n_stage', 'y1_sipho', 'y2_sipho', 'y1_rest', 'y2_rest'):
        if not float(inp[key]).is_integer():
            raise ValueError(f'{key} must be a whole number')
    if inp['n_stage'] < 0 or inp['y1_sipho'] >= inp['y2_sipho'] or inp['y1_rest'] >= inp['y2_rest']:
        raise ValueError('invalid base return path')
    r, n = inp["r_perp"], int(inp["n_stage"])
    g2s, g2r = min(inp["g2_sipho_src"], g_cap(r)), min(inp["g2_rest"], g_cap(r))
    tau, pr = inp["tau"], inp["parent_ratio"]
    path_s = (NUM_YEAR, int(inp["y1_sipho"]), int(inp["y2_sipho"]), inp["ss_return_cap_sipho"])
    path_r = (NUM_YEAR, int(inp["y1_rest"]), int(inp["y2_rest"]), inp["rs_rest"])
    g1 = inp["eps_2028_gaap_m"] / inp["eps_2027_gaap_m"] - 1.0
    street = {"L": inp["eps_2026_m"], "M": inp["eps_2027_m"], "H": inp["eps_2027_h"]}

    # ---- Step 1: company economic EPS (A9, A6) ----
    sbc_ps = inp["sbc_annual"] * (1.0 - inp["tax"]) / inp["shares"]
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    bps_op_2q26 = equity_op / inp["shares"]
    unbooked = (inp["eps_2026_m"] - inp["eps_ytd_a"]) - inp["window_fraction"] * (sbc_ps + nii_ps)

    def deck(num: dict[str, float] | None = None, gm: float = inp["gm_sipho"], g2s_: float = g2s, g2r_: float = g2r,
             cap_mult: float = 1.0, g1_: float = g1, rr: float | None = None, unb: float = unbooked,
             ps: tuple = path_s, prr: tuple = path_r):
        num = {t: street[t] - sbc_ps - nii_ps for t in TIERS} if num is None else num
        rr = r if rr is None else rr
        d = (1.0 + rr) ** -tau
        oi = {y: inp[f"sipho_rev_{y}"] * (gm - inp["opex_ratio"]) for y in (2026, 2027)}
        pre = {t: num[t] * inp["shares"] / (1.0 - inp["tax"]) for t in TIERS}
        sh = {"L": oi[2026] / pre["L"], "M": oi[2027] / pre["M"]}
        sh["H"] = sh["M"]
        cap = {"L": inp["sipho_rev_2026"] / inp["rev_2026"], "M": inp["sipho_rev_2027"] / inp["rev_2027"]}
        cap["H"] = cap["M"]
        cap = {t: min(cap[t] * cap_mult, 0.95) for t in TIERS}
        g1s = inp["sipho_rev_2028"] / inp["sipho_rev_2027"] - 1.0
        g1r = (g1_ - sh["M"] * g1s) / (1.0 - sh["M"])
        out = {}
        for t in TIERS:
            g_roll = sh[t] * g2s_ + (1.0 - sh[t]) * g2r_ if t == "L" else g1_
            frac = g_roll * unb / num[t]
            if frac >= 1.0:
                raise ValueError(f"{t}: book roll diverges, g·N/eps = {frac:.2f} >= 1 (BLOCKED-by-rule)")
            bps = bps_op_2q26 / (1.0 - frac)
            es, er = num[t] * sh[t], num[t] * (1.0 - sh[t])
            roe_s, roe_r = es / (bps * cap[t]), er / (bps * (1.0 - cap[t]))
            n_t = 0 if t == "L" else n
            pe_s = path_value(g1s, n_t, g2s_, roe_s, rr, *ps)
            pe_r = path_value(g1r, n_t, g2r_, roe_r, rr, *prr)
            b1 = g_roll / (num[t] / bps)
            win = max(unb * (1.0 - b1), 0.0) * (1.0 + rr) ** -(tau / 2)  # window profit, < 0 -> 0 (A22)
            out[t] = dict(bps=bps, b1=b1, sh=sh[t], cap=cap[t], es=es, er=er, roe_s=roe_s, roe_r=roe_r,
                          pe_s=pe_s, pe_r=pe_r, v_s=es * pe_s * d, v_r=er * pe_r * d, win=win,
                          val=(es * pe_s + er * pe_r) * d + win + cash_ps * pr)
        return out, g1s, g1r

    ops = {t: street[t] - sbc_ps - nii_ps for t in TIERS}
    base, g1s, g1r = deck()
    L, M, H = (base[t]["val"] for t in TIERS)
    if not all(math.isfinite(x) for x in (L, M, H)) or not L < M < H:
        raise ValueError("base anchors must be finite and ordered")

    def option_result():
        if not float(inp['t_opt']).is_integer() or inp['t_opt'] < NUM_YEAR:
            raise ValueError('invalid project realization year')
        opt_base_revenue = (inp["sipho_rev_2028"] * base["H"]["es"] / base["M"]["es"]
                            * (1.0 + g2s) ** (inp["t_opt"] - inp["t_align"]))
        opt_revenue = inp["opt_target_rev"] - opt_base_revenue
        if opt_revenue <= 0:
            raise ValueError("no incremental project revenue")

        def option_value(gm: float, d: dict, cap_mult: float = 1.0, ps: tuple = path_s) -> dict:
            # Shared axis allocates operating capital by revenue. This is a proxy, not a company capex budget.
            density = d["H"]["bps"] * inp["shares"] / inp["rev_2027"]
            capital = opt_revenue * density * cap_mult
            profit = opt_revenue * (gm - inp["opex_ratio"]) * (1.0 - inp["tax"])
            roe = profit / capital
            pe = path_value(0.0, 0, g2s, roe, r, int(inp["t_opt"]), *ps[1:])
            gross = profit / inp["shares"] * pe / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR + tau)
            # No credit for undisclosed grants/prepayments or assumed capital already spent; opening-2027 payment.
            cost = capital / inp["shares"] / (1.0 + r) ** tau
            return dict(density=density, capital=capital, profit=profit, roe=roe, pe=pe,
                        gross=gross, cost=cost, net=gross - cost)

        option = option_value(inp["gm_sipho"], base)
        v_opt = option["net"]

        return option, v_opt


    def candidate_result():
        def econ_at(cagr: float) -> float:
            rev_2028 = inp["rev_2025"] * (1.0 + cagr) ** 3
            return rev_2028 * inp["opm_model_2028"] * (1.0 - inp["tax"]) / inp["shares"] - sbc_ps - nii_ps
        econ_2028, econ_2028_hi = econ_at(inp["cagr_model"]), econ_at(inp["cagr_model_hi"])
        g1_cand = econ_2028 / ops["M"] - 1.0
        g1_cand_h = max(0.0, econ_2028_hi / ops["H"] - 1.0)
        cand = {"M": deck(g1_=g1_cand)[0]["M"], "H": deck(g1_=g1_cand_h)[0]["H"]}
        cand_band = (L, cand["M"]["val"], cand["H"]["val"])
        return cand_band

    bands = dict(zip(TIERS, (L, M, H)))
    result = {'ticker': 'GFS.US', 'currency': 'USD', 'units': {'price': 'USD_PER_SHARE'},
              'valuation_as_of': None, 'framework_as_of': None,
              'historical_financial_statement_as_of': '2026-09-30',
              'historical_research_as_of': '2026-11-05',
              'anchors': bands, 'cut_points': dict(zip(('A', 'B'), cut_points(L, M, H))),
              'candidate': None, 'review_flags': ['historical_forecast_and_peer_sample_unverified'],
              'segments': {'sipho': {'unit': 'USD_PER_SHARE', 'values': {t: base[t]['v_s'] for t in TIERS}},
                           'rest': {'unit': 'USD_PER_SHARE', 'values': {t: base[t]['v_r'] for t in TIERS}},
                           'cash_and_window': {'unit': 'USD_PER_SHARE', 'values': {t: cash_ps * pr + base[t]['win'] for t in TIERS}}},
              'key_parameters': {leg: {'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys(TIERS, r)},
                 'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys(TIERS, g)},
                 'forward_return': {'unit': 'RATIO', 'values': {t: base[t][roe] for t in TIERS}},
                 'steady_return': {'unit': 'RATIO', 'values': {t: min(base[t][roe], steady) for t in TIERS}}}
                 for leg, g, roe, steady in (('sipho', g2s, 'roe_s', path_s[3]), ('rest', g2r, 'roe_r', path_r[3]))},
              'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                  {'inputs': inp, 'numerator_year': NUM_YEAR, 'option_weights': P_TIERS}, BASELINE_LOCAL)}
    try:
        detail, value = option_result()
        option_band = {t: bands[t] + w * value for t, w in zip(TIERS, P_TIERS)}
        if not math.isfinite(value) or value < 0 or not all(math.isfinite(v) for v in option_band.values()) or not option_band['L'] < option_band['M'] < option_band['H']:
            raise ValueError('invalid option')
        result['option'] = {'label': '硅光目标', 'value': value, 'value_unit': 'USD_PER_SHARE',
                            'weights': dict(zip(TIERS, P_TIERS)), 'anchors': option_band, 'details': detail}
    except (ArithmeticError, ValueError, TypeError):
        result['option'] = {'status': 'unavailable', 'label': '硅光目标', 'anchors': None}
        result['review_flags'].append('historical_option_unavailable')
    try:
        cand = candidate_result()
        if not all(math.isfinite(x) for x in cand) or not cand[0] < cand[1] < cand[2]:
            raise ValueError('invalid candidate')
        result['candidate'] = {'label': '公司2028目标', 'anchors': dict(zip(TIERS, cand))}
    except (ArithmeticError, ValueError, TypeError):
        result['review_flags'].append('historical_candidate_unavailable')

    return result
