#!/usr/bin/env python3
"""China Merchants Bank's historical common-equity PB-ROE model.

The Q3 book already reflects the July dividend. Roll only the unbooked FY26
consensus earnings into opening 2027 book, then discount the 2027 value over
the actual quarter and add the modeled distributable earnings in that window.
The bank's excess retention is deducted, not a second cash asset. The A/H
comparison uses a historical currency rate, not a current premium.
"""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, justified_pb
from lib.inputs import check_missing, ladder
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis'),
                'axes': {'southbound': 'southbound_repricing'}}
# Historical local input snapshot only; the runner binds code/axis separately.
BASELINE_FINGERPRINT = '33f562cf6d70de04a7c97cde3ae4cba2bf4b1327a0c849b35d73382615971754'

YI = 1e8
TIERS = ('L', 'M', 'H')
REQUIRED = ['shares', 'bps', 'bps_prev', 'fx_hkdcny', 'eps_2027_l', 'eps_2027_m', 'eps_2027_h', 'eps_2026_m', 'eps_booked_a', 'div_after_report', 'roe_snap', 'g2', 'r_op', 'pb_hist_hi', 'npl', 'cov_now', 'cov_l', 'tax_rate', 'payout_obs', 'k_l', 'k_m', 'k_h', 'tau_yr']
INPUTS = {
    'shares': 25219845601.0,  # 普通股总股本A+H；本期无普通股增发，[Q3]股本百万元取整25220；2026-09-30
    'bps': 46.87,  # [Q3]第2页：归属于普通股股东每股净资产，人民币，不用HKD换算值；2026-09-30
    'bps_prev': 43.4348,  # 上年末普通股 BPS（平均权益用）；2025-12-31
    'fx_hkdcny': 0.872219799389446,  # Longbridge exchange-rate：1 CNY=1.1465 HKD，取倒数为HKD→CNY；只换算港股带；2026-11-05
    'eps_2027_l': 6.0147,  # [E] FY2027E同源20家低端；部分共识待更新，财报后覆盖完整性未确认；2026-11-05
    'eps_2027_m': 6.25363,  # [E] FY2027E同源20家均值；部分共识待更新，财报后覆盖完整性未确认；2026-11-05
    'eps_2027_h': 6.69,  # [E] FY2027E同源20家高端；A3削弱，不等于管理层指引；2026-11-05
    'eps_2026_m': 5.85938,  # [E] FY2026E均值，2家，5.84–5.87876；只滚未入账窗口，非三档盈利分子；部分共识待更新；2026-11-05
    'eps_booked_a': 4.57,  # [Q3]第2页：9M26已入账普通股EPS，从全年共识中扣除，只剩4Q；2026-09-30
    'div_after_report': 0.0,  # 9月底后已付、但未体现在该账面的股息扣减；7月1.003已体现在9月底账面，不能重复扣；公告索引核对至11月5日；2026-11-05
    'roe_snap': 0.1349,  # [Q3]第2页：9M26年化普通股ROAE，仅快照，不替代前瞻ROE；2026-09-30
    'g2': 0.03,  # 三档共用永续增速（A4）；**来源层级：无同业锚**（自身近体制 EPS CAGR 2.71% / NI YoY 2.9%；同业反解不成立，中位 2.19% 仅作交叉）；实测增速非留存恒等式，r 换档不重解；cap = min(6%, r − 4%) = 6% ✓；2026-09-18
    'r_op': 0.11,  # **篮 5 大行 / 优质股份行 r = 11%**（命中 A2c-2，PB-ROE 尺；无备选篮，A13）；`r_` 前缀供 `calibration.py` 报 r 档；2026-09-18
    'pb_hist_hi': 1.2332,  # FY2022 own-year PB实测顶，仅护栏；本次三档均不触发；FY2022
    'npl': 70068000000.0,  # [Q3]第4页集团不良余额700.68亿，不用本行666.13亿；2026-09-30
    'cov_now': 3.8939,  # [Q3]第4页集团拨备覆盖率389.39%，不用本行391.73%；2026-09-30
    'cov_l': 4.1093,  # L 档覆盖率目标 = 2025H1 官方实测；2025-06-30
    'tax_rate': 0.25,  # 拨备税盾；法定税率
    'payout_obs': 0.354,  # 实付派息率 = 2025 DPS 2.016 ÷ EPS 5.70（A14）；2025-12-31
    'k_l': 0.63,  # L 打折：留存边际回报实测代理 2022→25 4.1% → 1 − 4.1/11；来源 ① 代理（A14）；2026-09-30
    'k_m': 0.5,  # M 打折：E 桶默认上沿；来源 ②（A14）；2026-09-30
    'k_h': 0.3,  # H 打折：E 桶默认下沿；来源 ②（A14）；2026-09-30
    'tau_yr': 0.25,  # 基准日2026-09-30到2027年初；2027年初价值折τ，4Q窗口可分配利润折τ/2；2026-09-30
    'seller_tp_mean': 53.26,  # 卖方 A 股目标价均值（映射用，不进公式）；2026-09-07
    'seller_tp_lo': 43.44,  # 卖方区间下沿；2026-09-07
    'seller_tp_hi': 64.0,  # 卖方区间上沿；2026-09-07
}

def equity_avg(inp: dict[str, float]) -> float:
    return 0.5 * (inp["bps"] + inp["bps_prev"]) * inp["shares"]


def provision_hit_pp(inp: dict[str, float]) -> float:
    delta_ni = inp["npl"] * (inp["cov_l"] - inp["cov_now"]) * (1.0 - inp["tax_rate"])
    return delta_ni / equity_avg(inp)


def unbooked_eps(inp: dict[str, float]) -> float:
    """FY26 consensus EPS not yet in the latest reported book (FY26E less 9M26 actual)."""
    return inp["eps_2026_m"] - inp["eps_booked_a"]


def bps_2027(inp: dict[str, float], eps: float) -> float:
    """Common BPS at the start of 2027, retaining b1 = g/ROE of the unbooked profit.

    start = 3Q26 BPS less dividends paid after the balance-sheet date;
    the July 2026 payment is already reflected in 3Q26 BPS and is not deducted again; BPS = start + (g / ROE) N with ROE = eps / BPS → closed form.
    """
    start = inp["bps"] - inp["div_after_report"]
    gn = inp["g2"] * unbooked_eps(inp) / eps
    if gn >= 1.0:
        raise ValueError(f"BPS roll diverges: g N / eps = {gn:.3f}")
    return start / (1.0 - gn)


def full_value(inp: dict[str, float], bps: float, roe: float) -> float:
    """Gordon PB-ROE value: the model pays out 1 - g/ROE of earnings."""
    return bps * justified_pb(inp["g2"], roe, inp["r_op"])


def excess_retention(inp: dict[str, float], bps: float, roe: float) -> float:
    """Retained beyond what g needs, which Gordon counts as paid out (bucket E).

    Per share, capitalized at (r - g): (1 - payout_obs - g/ROE) × EPS / (r - g).
    """
    g, r = inp["g2"], inp["r_op"]
    share = 1.0 - inp["payout_obs"] - g / roe
    return share * roe * bps / (r - g)


def anchor(inp: dict[str, float], bps: float, roe: float, k: float, clip: bool) -> float:
    value = full_value(inp, bps, roe) - k * excess_retention(inp, bps, roe)
    if clip:
        value = min(value, bps * inp["pb_hist_hi"])
    return value


def tiers(inp: dict[str, float]) -> dict[str, tuple[float, float]]:
    """{tier: (BPS at start of 2027, ROE_x = FY27E eps_x / that BPS)}."""
    out = {}
    for lab in TIERS:
        eps = inp[f"eps_2027_{lab.lower()}"]
        b = bps_2027(inp, eps)
        out[lab] = (b, eps / b)
    return out


def timed(inp: dict[str, float], value_tn: float, roe: float) -> float:
    """时点对齐 (valuation-rules「经营价值与超额现金」③; A16): the PB-ROE value is struck on
    the BPS at the opening of 2027 (t_n) -> today = x (1+r)^-tau, plus the window
    distributable profit = the unbooked FY26 profit x (1 - b), b = g/ROE (the roll's b1,
    the same 视同派出 basis), discounted (1+r)^-(tau/2).  Dividends paid after the reporting date are not added back."""
    r = inp["r_op"]
    window = unbooked_eps(inp) * (1.0 - inp["g2"] / roe)
    return value_tn * (1.0 + r) ** -inp["tau_yr"] + window * (1.0 + r) ** (-inp["tau_yr"] / 2.0)


def anchors(inp: dict[str, float]) -> tuple[float, float, float]:
    t = tiers(inp)
    return tuple(timed(inp, anchor(inp, *t[lab], inp[f"k_{lab.lower()}"], clip=lab == "H"), t[lab][1])
                 for lab in TIERS)



def evaluate(inp, axis):
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(isinstance(inp[k], bool) or not isinstance(inp[k], (int, float)) or not math.isfinite(inp[k]) for k in REQUIRED):
        raise ValueError('required inputs must be finite numbers')
    if inp['shares'] <= 0 or inp['fx_hkdcny'] <= 0 or inp['tau_yr'] < 0:
        raise ValueError('shares and exchange rate must be positive, and discount duration nonnegative')
    # This is elapsed time, not a whole calendar year: 0.25 years is valid.
    errors += check_r(inp['r_op'], 'r_op', 5)
    errors += check_g_cap(inp['g2'], inp['r_op'], 'g2')
    if axis.get('role') != 'reference' or axis.get('h_share') != '3968.HK':
        errors.append('southbound axis does not declare the historical bank reference')
    errors += ladder('eps_2027', *(inp[f'eps_2027_{t.lower()}'] for t in TIERS))
    if inp['cov_l'] <= inp['cov_now']:
        errors.append('coverage stress must be a provision rebuild')
    if inp['g2'] >= inp['r_op']:
        errors.append('growth must be below discount rate')
    if inp['eps_2027_m'] <= inp['eps_2026_m'] and inp['g2'] > 0:
        errors.append('same-world consensus growth gate')
    ts = tiers(inp)
    roe = {t: ts[t][1] for t in TIERS}
    bps = {t: ts[t][0] for t in TIERS}
    errors += ladder('roe', *(roe[t] for t in TIERS))
    if any(roe[t] <= inp['g2'] for t in TIERS):
        errors.append('each ROE must exceed growth')
    k = {t: inp[f'k_{t.lower()}'] for t in TIERS}
    if not 0 <= k['H'] <= k['M'] <= k['L'] <= 1:
        errors.append('invalid retention haircut ladder')
    if not 0 < inp['payout_obs'] < 1:
        errors.append('invalid payout')
    if any(1-inp['payout_obs']-inp['g2']/roe[t] <= 0 for t in TIERS):
        errors.append('no excess retention to discount')
    if errors:
        raise ValueError('; '.join(errors))
    values = dict(zip(TIERS, anchors(inp)))
    if not values['L'] < values['M'] < values['H']:
        raise ValueError('anchors must be strictly ordered')
    pb = {t: values[t]/bps[t] for t in TIERS}
    pe_m = pb['M']/roe['M']
    flat = {t: inp[f'eps_2027_{t.lower()}']*pe_m for t in TIERS}
    errors += ladder('flat-multiple', *(flat[t] for t in TIERS))
    if errors:
        raise ValueError('; '.join(errors))
    hit = provision_hit_pp(inp)
    raw_h = timed(inp, anchor(inp, bps['H'], roe['H'], k['H'], clip=False), roe['H'])
    fx = inp['fx_hkdcny']
    return {'ticker':'600036.SH', 'currency':'CNY', 'valuation_as_of':None, 'framework_as_of':None,
            'anchors':values, 'candidate':None, 'option':None,
            'units':{'price':'CNY_PER_SHARE'},
            'segments':{'company':{'unit':'CNY_PER_SHARE','values':values}},
            'key_parameters':{'discount_rate':{'unit':'RATIO','values':{t:inp['r_op'] for t in TIERS}},
                              'growth_rate':{'unit':'RATIO','values':{t:inp['g2'] for t in TIERS}},
                              'forward_return':{'unit':'RATIO','values':roe},
                              'steady_return':{'unit':'RATIO','values':{t:None for t in TIERS}}},
            'operating':{'book_per_share':bps, 'unbooked_eps':unbooked_eps(inp),
                         'gordon':{t:full_value(inp,bps[t],roe[t]) for t in TIERS},
                         'excess_retention':{t:excess_retention(inp,bps[t],roe[t]) for t in TIERS},
                         'opening_pb':{t:anchor(inp,bps[t],roe[t],k[t],clip=t=='H')/bps[t] for t in TIERS},
                         'raw_high':raw_h, 'provision_hit':hit,
                         'h_share_hkd':{t:values[t]/fx for t in TIERS},
                         'stress':timed(inp,anchor(inp,bps['M'],roe['M']-hit,k['L'],False),roe['M']-hit),
                         'snapshot':anchor(inp,inp['bps'],inp['roe_snap'],k['M'],False),
                         'retention_haircut':k,
                         'ddm':{t:full_value(inp,bps[t],roe[t])-excess_retention(inp,bps[t],roe[t]) for t in TIERS},
                         'flat':flat},
            'sensitivity':{'growth_minus_1pp':dict(zip(TIERS,anchors({**inp,'g2':inp['g2']-.01}))),
                           'growth_plus_1pp':dict(zip(TIERS,anchors({**inp,'g2':inp['g2']+.01}))),
                           'payout_50pct':dict(zip(TIERS,anchors({**inp,'payout_obs':.5}))),
                           'haircut_m_063':dict(zip(TIERS,anchors({**inp,'k_m':.63}))),
                           'haircut_m_047':dict(zip(TIERS,anchors({**inp,'k_m':.47}))),
                           'haircut_l_091':dict(zip(TIERS,anchors({**inp,'k_l':.91}))),
                           'haircut_h_050':dict(zip(TIERS,anchors({**inp,'k_h':.50})))}}


def calculate(context):
    axis = context['axes']['southbound']
    result = evaluate(dict(INPUTS), axis)
    # This detects only changes in the explicit stock inputs and its own axis
    # role; it does not claim that the full source set has been reconciled.
    local = {'inputs': INPUTS, 'southbound': {'role': axis['role'], 'h_share': axis['h_share']}}
    result.update({'basis_changed': None, 'partial_basis_changed': local_basis_changed(local, BASELINE_FINGERPRINT),
                   'historical_financial_statement_as_of': '2026-09-30',
                   'historical_research_as_of': '2026-11-05',
                   'review_flags': ['historical_consensus_coverage_incomplete',
                                    'historical_net_interest_margin_below_watch_level']})
    return result
