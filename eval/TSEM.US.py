"""Historical model snapshot for TSEM.US, migrated from the user's working copy."""
from __future__ import annotations
import math
from lib.gordon import g_cap, payout
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'zones', 'partial_basis'), 'axes': {'sipho': 'sipho_wafer', 'foundry': 'mature_foundry'}}
BASELINE_LOCAL = '2e04561cb6535995e59d1e4e35c2ca44155aa87e0709a2376986e62be127cde4'
AXIS_FIELDS = ('g2_sipho_src', 'gm_sipho', 't_align', 'asp_sipho_300', 'gf_cogs_2025', 'gf_wafers_2025', 'ss_return_cap_sipho', 'ss_return_sipho_ref', 'y1_sipho', 'y2_sipho')
NUM_YEAR = 2027
P_TIERS = (0.0, 0.25, 1.0)
MONTHS = 12
TIERS = ('L', 'M', 'H')
INPUTS = {
    'shares': 113100000.0,  # 旧期末股数 113.1M 暂留，本期期末数待补；S1 Q3 基本 / 稀释加权平均数 113.324M / 114.463M 不是期末股数，不直接替换 2026-06-30
    'equity': 3208124000.0,  # S1「TOTAL SHAREHOLDERS’ EQUITY」合并权益；本期未拆归母 / 少数股东，暂作归母经营权益的代理（A6）；不是精确归母值。减净现金后滚 Q4 至 2027 年初 2026-09-30
    'net_cash': 1319145000.0,  # S1：现金 250.748 + 短存 1,222.124 − 短债 13.452 − 长债 140.275（$M）；沿旧公司净现金定义，不另重切租赁及预付款 2026-09-30
    'nii_4q': 49800000.0,  # 旧滚动四季净利息暂留（A6），最新纯净利息待补；S1 Q3 financing and other income 11.943M 包含其他收益，不能直接全当净利息 2026-06-30
    'gaap_gap_ps': 0.3804,  # GAAP–调整口径差 USD/股 = yfinance 2027E 调整后 6.5314 − marketscreener GAAP 6.151；A8 ；**共识待更新** 2026-09-14
    'tax': 0.1,  # 既有正常化税率暂留，待复核；S1 Q3 / 前三季实际 13.80% / 12.93%，全球最低税已提示。13% / 15% 敏感性见 Outputs，不对已含税共识 EPS 再扣一次税 2026-11-03
    'eps_2026_m': 3.8649,  # FY2026E 共识均值（7 家、调整后）= L 消化年分子；也是 Q4 尚未入账利润 = 全年减 `eps_ytd26_a` 的来源（A16）；**共识待更新** 2026-09-11
    'eps_ytd26_a': 2.68,  # 前三季实测调整后稀释 EPS；已入 3Q26 账面，只滚 FY26 共识减前三季实测的 Q4 利润（A16）；Q3 公告调节表 2026-09-30
    'payout_3y': 0.0,  # 近三年实付派息率（无股利，实付留存 100%）；只进 A16 的 B 桶披露行，**不进** BPS 推演（主尺按 \(b_1 = g/ROE\) 滚） 2026-06-30
    'eps_2027_l': 5.73,  # FY2027E 共识低端（8 家）；只作 A3 校验坐标，不进公式 ；**共识待更新** 2026-09-11
    'eps_2027_m': 6.5314,  # FY2027E 共识均值 = M 分子；A3 ；**共识待更新** 2026-09-11
    'eps_2027_h': 7.52,  # FY2027E 共识高端 = H 分子；A3 ；**共识待更新** 2026-09-11
    'eps_2027_gaap_m': 6.151,  # 2027E 共识（marketscreener 7 家，GAAP）；g1 分母；A4 ；**共识待更新** 2026-09-14
    'eps_2028_gaap_m': 9.923,  # 2028E 共识（同源）；g1 分子；A4 ；**共识待更新** 2026-09-14
    'n_stage': 1.0,  # 过渡年数（仅 2028E），只在 M/H；A4 2026-09-14
    'n_consensus': 1.0,  # 有 ≥2 家共识的远期年数；2029E 无 2026-09-14
    'rev_2026': 1999871000.0,  # S1 前三季实际 1,399.871M + Q4 指引中值 600M；替换旧年度收入共识，作为 L 资本占比分母。全年指引推算，非全年实际 2026-11-02
    'rev_2027': 2725000000.0,  # FY2027E 营收共识均值（yfinance 9 家，2.59–3.02）；M/H 资本占比分母、硅光倒推 ；**共识待更新** 2026-10-03
    'sipho_rev_2026': 761000000.0,  # 路径近似：旧 Q1≈106 + Q2≈170 + Q3≈210（旧估，非本期实测）+ Q4 275（S1 年化目标 1.1B ÷4），$M；只上调 Q4 25M，不把 RF 基础设施 56% 当硅光 2026-11-03
    'sipho_rev_2027': 1424000000.0,  # FY2027 硅光 = 营收共识 2,725 − 其余（FY26 1,239 × 1.05）$M（公司级共识倒推，A17）；巴克莱 1.6B / 公司合同 1.3B 交叉 ；**共识待更新** 2026-10-03
    'sipho_rev_2028': 2211000000.0,  # FY2028 硅光 = 营收共识 3,577（marketscreener 均值）− 其余（1,239 × 1.05²）$M；巴克莱 62% ≈ 2.22B / Wedbush ≈ 2.4B 交叉；A17 ；**共识待更新** 2026-10-03
    'opex_ratio': 0.0981144554613512,  # S1 Q3 (R&D 26.625 + SG&A 24.999) ÷ 营收 526.161（$M）；按组尺重算利润拆分 2026-09-30
    'r_perp': 0.1,  # 篮 4 龙头制造 10%：整公司一腿（特种代工细分龙头；街 WACC ≈10.7%、β 0.88；备选篮 6 撤销）；A15 2026-09-18
    'pe_own_min': 9.2,  # 护栏下沿（2025-03）；A7 2026-09-11
    'pe_own_max': 39.9,  # 护栏上沿（2026-06）；A7 2026-09-11
    'bvps': 28.365375773651635,  # S1 合并权益 3,208.124M ÷ 旧股数 113.1M，仅估算；归母权益及最新期末股数待补，不能称本期归母 BVPS 2026-11-03
    'pb_floor': 0.99,  # 自身实测 PB 低点（2023-10）；地板只披露不 max() 2026-09-11
    'jp_wpm_2029': 45000.0,  # 日本 300mm 产能 2029 年（300mm 等效片 / 月，Track 1 + Track 2 合计）= CEO Ellwanger 接受 Nikkei Asia 采访（DCD 2026-09-24、Investment Monitor 2026-09-25 转引；Nikkei 原文 `待核`）；A9 2026-09-24
    'jp_mult_t2': 4.0,  # Track 2 使日本 300mm 产能 ×4（含 Fab 6 增量）——Q2'26 电话会 CEO 答 Benchmark；A9 2026-08-04
    'jp_mult_2025': 40.0,  # 2029 产能 ≈ 2025 年的 40 倍（同一采访）→ 2025 基数 1,125 片 / 月；只用于拆 Track 1 增量；A9 2026-09-24
    'opex_ratio_full': 0.07,  # 满产营业费用率 = 公司 2028 模型 毛利率 45% − 营业利润率 38%（Track 1 满产口径，Q2'26 电话会）；A9 2026-08-04
    'k_dual': 3000000000.0,  # 日本双轨扩产合计投资「up to \$3B, net of grants」（投资者 FAQ；补助约 \$1B 另计）；按新增产能拆给 Track 2（A9） 2026-07-14
    'k_t2_spent': 0.0,  # Track 2 已投 USD：definitive agreements 未签、设备在终谈（Q2'26 电话会）→ 按 0 读；A9 2026-08-04
    't_opt': 2030.0,  # 满产年：Track 2 2028Q4 装机、2029 年产能到 45,000 片 / 月 → 第一个满产整年 2030；A9 2026-09-24
    'y1_rest': 2028.0,  # 成熟代工腿高回报期 Y1 = 可见年末（默认路径；A19） 2026-10-16
    'y2_rest': 2032.0,  # 成熟代工腿 Y2 = Y1 + 4（门槛「中」，不确定：成熟制程新厂 2–3 年、客户认证约 1 年、中国大陆新增产能抢份额快、单位产能投资高；A19） 2026-10-16
    'rs_rest': 0.117,  # 成熟代工腿稳态回报 = **自身周期**（2026-10-19 按序取）：高塔最近一轮完整谷到谷 FY2019–FY2023 投入资本口径经营回报均值 11.7%（2023 剔英特尔终止赔付 3.53 亿）；同业中位 9.95% 与兜底 15% 只作对照；各档 min(前瞻, 本值)：只 H 档（14.05%）回落；A19 2026-10-19
    'tau': 0.25,  # 时点对齐：估值基准日 2026-09-30 → FY2027 年初，按季度约定取一季；同为剩余未入账年度比例（A16 / A19），两腿与期权折 tau、窗口利润折 tau/2 2026-11-03
    'parent_ratio': 1.0,  # 旧归母现金比例暂留（Q2 少数股东权益 −14.7M，不放大现金）；S1 未拆最新少数股东权益，本期比例待补，非新增确认 2026-06-30
}

def path_value(g1: float, n: int, g2: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the numerator-year earnings, valued at the start of the numerator year,
    on the steady-state-return path (valuation-rules「经营价值与超额现金」② 稳态回报三段;
    gordon.py's three-segment function is not built yet, so it lives here).

    t = 1 is the numerator year t0; the first n years grow at g1 (two_stage_pe's stage 1),
    then g2 with RONIC = forward through Y1, linear to min(R_s, forward) by Y2, then the
    Gordon tail.  With R_s >= forward it is exactly two_stage_pe / perpetual_pe (A19)."""
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

    # ---- Step 1: company economic EPS (A8, A6) ----
    nii_ps = inp["nii_4q"] * (1.0 - inp["tax"]) / inp["shares"]
    ops = {t: street[t] - inp["gaap_gap_ps"] - nii_ps for t in TIERS}
    equity_op = inp["equity"] - inp["net_cash"]
    cash_ps = inp["net_cash"] / inp["shares"]
    bps_op_latest = equity_op / inp["shares"]
    # Q3 is already in the latest book: only Q4 profit and a quarter of the
    # annual GAAP bridge / cash income remain in the opening-FY27 roll.
    unbooked = inp["eps_2026_m"] - inp["eps_ytd26_a"] - tau * (inp["gaap_gap_ps"] + nii_ps)

    # ---- Step 2: leg split (group ruler) ----
    def split(gm: float, cap_mult: float = 1.0):
        oi = {y: inp[f"sipho_rev_{y}"] * (gm - inp["opex_ratio"]) for y in (2026, 2027, 2028)}
        pre = {t: ops[t] * inp["shares"] / (1.0 - inp["tax"]) for t in TIERS}
        sh = {"L": oi[2026] / pre["L"], "M": oi[2027] / pre["M"]}
        sh["H"] = sh["M"]
        cap = {"L": inp["sipho_rev_2026"] / inp["rev_2026"], "M": inp["sipho_rev_2027"] / inp["rev_2027"]}
        cap["H"] = cap["M"]
        cap = {t: min(cap[t] * cap_mult, 0.95) for t in TIERS}
        g1s = inp["sipho_rev_2028"] / inp["sipho_rev_2027"] - 1.0
        return sh, cap, g1s

    def deck(gm: float = inp["gm_sipho"], g2s_: float = g2s, g2r_: float = g2r, cap_mult: float = 1.0, g1_: float = g1,
             rr: float | None = None, ps: tuple = path_s, prr: tuple = path_r):
        rr = r if rr is None else rr
        d = (1.0 + rr) ** -tau
        sh, cap, g1s = split(gm, cap_mult)
        g1r = (g1_ - sh["M"] * g1s) / (1.0 - sh["M"])
        out = {}
        for t in TIERS:
            g_roll = sh[t] * g2s_ + (1.0 - sh[t]) * g2r_ if t == "L" else g1_
            frac = g_roll * unbooked / ops[t]
            if frac >= 1.0:
                raise ValueError(f"{t}: book roll diverges, g·N/eps = {frac:.2f} >= 1 (BLOCKED-by-rule)")
            bps = bps_op_latest / (1.0 - frac)
            es, er = ops[t] * sh[t], ops[t] * (1.0 - sh[t])
            roe_s, roe_r = es / (bps * cap[t]), er / (bps * (1.0 - cap[t]))
            n_t = 0 if t == "L" else n
            pe_s = path_value(g1s, n_t, g2s_, roe_s, rr, *ps)
            pe_r = path_value(g1r, n_t, g2r_, roe_r, rr, *prr)
            b1 = g_roll * bps / ops[t]
            win = max(unbooked * (1.0 - b1), 0.0) * (1.0 + rr) ** -(tau / 2)  # window profit, < 0 -> 0 (A19)
            out[t] = dict(bps=bps, b1=b1, sh=sh[t], cap=cap[t], es=es, er=er, roe_s=roe_s, roe_r=roe_r,
                          pe_s=pe_s, pe_r=pe_r, v_s=es * pe_s * d, v_r=er * pe_r * d, win=win,
                          val=(es * pe_s + er * pe_r) * d + win + cash_ps * pr)
        return out, g1s, g1r

    base, g1s, g1r = deck()
    L, M, H = (base[t]["val"] for t in TIERS)
    if not all(math.isfinite(x) for x in (L, M, H)) or not L < M < H:
        raise ValueError("base anchors must be finite and ordered")

    def option_result():
        if not float(inp['t_opt']).is_integer() or inp['t_opt'] < NUM_YEAR:
            raise ValueError('invalid project realization year')
        wpm_t2 = inp["jp_wpm_2029"] * (1.0 - 1.0 / inp["jp_mult_t2"])
        wpm_t1 = inp["jp_wpm_2029"] / inp["jp_mult_t2"] - inp["jp_wpm_2029"] / inp["jp_mult_2025"]
        t2_share = wpm_t2 / (wpm_t2 + wpm_t1)

        def option(price: float = inp["asp_sipho_300"], opex: float = inp["opex_ratio_full"],
                   t_opt: float = inp["t_opt"], share: float = t2_share, wpm: float = wpm_t2) -> dict:
            k = inp["k_dual"] * share
            unspent = k - inp["k_t2_spent"]
            rev = wpm * MONTHS * price
            ni = rev * (inp["gm_sipho"] - opex) * (1.0 - inp["tax"])
            roe = ni / k
            # SiPho path, calendar from the realisation year t_opt (2026-10-19: was NUM_YEAR 2027,
            # which pushed the option's high-return window 3 years later than the Y1/Y2 calendar; A9 / A19)
            pe = path_value(0.0, 0, g2s, roe, r, int(t_opt), *path_s[1:])
            gross = ni / inp["shares"] * pe / (1.0 + r) ** (t_opt - NUM_YEAR)
            k_ps = unspent / inp["shares"] * (1.0 + 1.0 / (1.0 + r)) / 2.0  # 2027-28 even spend
            fold = (1.0 + r) ** -tau  # valued at FY2027 -> folded to the valuation date (A19)
            return dict(k=k, rev=rev, ni=ni, roe=roe, pe=pe, gross=gross, k_ps=k_ps, v=(gross - k_ps) * fold)

        o = option()
        v_opt = o["v"]
        return o, v_opt


    bands = dict(zip(TIERS, (L, M, H)))
    result = {'ticker': 'TSEM.US', 'currency': 'USD', 'units': {'price': 'USD_PER_SHARE'},
              'valuation_as_of': None, 'framework_as_of': None,
              'historical_financial_statement_as_of': '2026-09-30',
              'historical_research_as_of': '2026-11-03',
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
        result['option'] = {'label': 'Track 2 产能', 'value': value, 'value_unit': 'USD_PER_SHARE',
                            'weights': dict(zip(TIERS, P_TIERS)), 'anchors': option_band, 'details': detail}
    except (ArithmeticError, ValueError, TypeError):
        result['option'] = {'status': 'unavailable', 'label': 'Track 2 产能', 'anchors': None}
        result['review_flags'].append('historical_option_unavailable')

    return result
