"""中粮资本历史 SOTP：输入来源与各业务计算均在此；不读取正文。"""
from __future__ import annotations
import math
from lib.gordon import capped_payout_pe, g_cap, perpetual_pe
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'partial_basis'), 'axes': {}}
TIERS = ('L', 'M', 'H')
CAP_TRIM_MAX = .02
BASELINE_LOCAL = '33128bab30e3c0cd84d6099c8368fece0ded9944b81a42b62c0a002c42bdbcea'

# 原研究 2026-10-09；金额单位为亿元人民币，股数单位为亿股。
# 人寿新单侵蚀使用 2023–25 三个同口径年度；2022 旧口径仅作对照。
# 2024–25 年未披露贴现率，沿用 2023 年数值；分红和注资未核。
INPUTS = {
    'shares': 23.04105575,  # 总股本（亿股）；2026 中报；2026-06-30
    'r_op': 0.1,  # 篮 4 常规经营：中英 / 信托 / 期货 / 总部——非银金融，盈利非商品价函数，无单一客户（A2）；2026-10-09
    'r_bank': 0.11,  # 篮 5 大行 / 优质股份行：龙江银行存贷业务命中 A2c-2，银行唯一可落的篮（A2）；2026-10-09
    'payout_obs': 0.301,  # 实付派息率（2025：30.10%，A10）；2025-12-31
    'ev_2021': 149.63,  # 中英 EV（无永续债）；中粮资本 2021 年报 / 中诚信；2021-12-31
    'ev_2022': 151.25,  # 中英 EV（无永续债）；2022-12-31
    'ev_2023': 170.03,  # 中英 EV（无永续债）；2023 年报 p15；2023-12-31
    'ev_2024_disc': 216.6,  # 中英披露 EV（含永续债）；中证鹏元 2026 资本补充债评级 p20；2024-12-31
    'perp_2024': 30.0,  # 2024 年发行永续债（中诚信：「30 亿元无固定期限资本债券的发行」）；2024-12-31
    'ev_2025_disc': 222.68,  # 中英披露 EV（含永续债）；中证鹏元 / 中诚信 2026 永续债评级；2025-12-31
    'perp_2025': 44.97,  # 中英永续债账面（2025 未审财报 4,497,300,000 元）；2025-12-31
    'rdr_2022': 0.1015,  # 中英 RDR（中证鹏元 2024 永续债第二期 p21）；2022-12-31
    'rdr_2023': 0.0975,  # 中英 RDR（同上）；2023-12-31
    'rdr_2024': 0.0975,  # 未披露（「审慎下调」），沿用 2023 值（A14）；2024-12-31
    'rdr_2025': 0.0975,  # 未披露，沿用 2023 值（A14）；2025-12-31
    'nbv_2022_old': 3.79,  # 中英 NBV 旧口径（扣资本成本后；只进 4 年窗口交叉）；2022-12-31
    'nbv_2023': 8.42,  # 中英 NBV 新口径重述；2023-12-31
    'nbv_2024': 6.7,  # 中英 NBV 新口径重述；2024-12-31
    'nbv_2025': 15.49,  # 中英 NBV 新口径（+131.20%）；基数（A5）；2025-12-31
    'g_nbv': 0.0,  # NBV 永续增速：无卖方 / 同业锚 → 0（A5）；2026-10-09
    'hold_ins': 0.5,  # 中英持股（并表；英杰华 50%）；2026-06-30
    'ins_book_2025': 111.97,  # 中英普通股账面 = 所有者权益 156.94 − 永续债 44.97（VIF 推算用）；2025-12-31
    'trust_eq': 92.36,  # 信托分部净资产均值（2025 末 91.62 / 2026-06 93.10）；2026-06-30
    'hold_trust': 0.8051,  # 信托持股；2026-06-30
    'roe_trust_l': 0.0747,  # 2025：6.551 ÷ 均值(83.70, 91.62)（A6）；2025-12-31
    'roe_trust_m': 0.0798,  # TTM：7.373 ÷ 均值(91.62, 93.10)（A6）；2026-06-30
    'roe_trust_h': 0.0883,  # 2024：7.031 ÷ 均值(75.57, 83.70)（A6）；2024-12-31
    'fut_eq': 48.6,  # 期货分部净资产均值（2025 末 49.00 / 2026-06 48.20）；2026-06-30
    'hold_fut': 0.7042,  # 期货持股（2024-12 增资后）；2026-06-30
    'roe_fut_l': 0.0505,  # 2025：2.433 ÷ 均值(47.31, 49.00)（A7）；2025-12-31
    'roe_fut_m': 0.0601,  # TTM：2.921 ÷ 均值(49.00, 48.20)（A7）；2026-06-30
    'roe_fut_h': 0.068,  # 2023 年报「ROE 6.8%」（A7）；2023-12-31
    'lj_bv': 40.124,  # 龙江银行权益法账面（20%）；2025 年报 p188；2025-12-31
    'roe_lj_l': 0.0338,  # 2025：6.712 ÷ 均值(196.93, 200.55)（A8）；2025-12-31
    'roe_lj_m': 0.0355,  # 2024 / 2025 均值（A8）；2025-12-31
    'roe_lj_h': 0.0597,  # 2026H1 年化：5.986 × 2 ÷ 200.55（A8，年化）；2026-06-30
    'k_lj_l': 1.0,  # 留存边际回报为负 → 全扣（A8）；2025-12-31
    'k_lj_m': 0.5,  # E 桶默认上沿（A8）；2025-12-31
    'k_lj_h': 0.3,  # E 桶默认下沿（A8）；2025-12-31
    'hq_ni': -1.073,  # 总部年费用（A9）；2025-12-31
    'eps_ttm': 0.522,  # TTM 归母 EPS（2025 0.4916 − 2025H1 0.3679 + 2026H1 0.3981）；③ 对带用；2026-06-30
    'band_pe_lo': 12.6,  # 同等盈利月份 PE 下沿（2023-12，A12）；2023-12-31
}

REQUIRED = ('shares', 'r_op', 'r_bank', 'payout_obs', 'ev_2021', 'ev_2022', 'ev_2023', 'ev_2024_disc', 'perp_2024', 'ev_2025_disc', 'perp_2025', 'rdr_2022', 'rdr_2023', 'rdr_2024', 'rdr_2025', 'nbv_2022_old', 'nbv_2023', 'nbv_2024', 'nbv_2025', 'g_nbv', 'hold_ins', 'ins_book_2025', 'trust_eq', 'hold_trust', 'roe_trust_l', 'roe_trust_m', 'roe_trust_h', 'fut_eq', 'hold_fut', 'roe_fut_l', 'roe_fut_m', 'roe_fut_h', 'lj_bv', 'roe_lj_l', 'roe_lj_m', 'roe_lj_h', 'k_lj_l', 'k_lj_m', 'k_lj_h', 'hq_ni', 'eps_ttm', 'band_pe_lo')

def ev_series(inp: dict[str, float]) -> dict[int, float]:
    """Shareholder EV (亿): disclosed EV less perpetual bonds where they exist."""
    return {
        2021: inp["ev_2021"], 2022: inp["ev_2022"], 2023: inp["ev_2023"],
        2024: inp["ev_2024_disc"] - inp["perp_2024"],
        2025: inp["ev_2025_disc"] - inp["perp_2025"],
    }


def eaten_share(inp: dict[str, float], y0: int, y1: int, nbv: dict[int, float]) -> float:
    """e = (expected − actual EV growth) / Σ NBV over (y0, y1]."""
    ev = ev_series(inp)
    unwind = sum(ev[y - 1] * inp[f"rdr_{y}"] for y in range(y0 + 1, y1 + 1))
    s = sum(nbv[y] for y in range(y0 + 1, y1 + 1))
    return (unwind + s - (ev[y1] - ev[y0])) / s


def nbv_same_basis(inp: dict[str, float]) -> dict[int, float]:
    return {y: inp[f"nbv_{y}"] for y in (2023, 2024, 2025)}


def k_ins(inp: dict[str, float]) -> dict[str, float]:
    e = eaten_share(inp, 2022, 2025, nbv_same_basis(inp))
    kl = min(1.0, max(0.0, e))
    return {"L": kl, "M": kl / 2.0, "H": 0.0}


def ins_leg(inp: dict[str, float], k: float) -> float:
    ev = ev_series(inp)[2025]
    return (ev + inp["nbv_2025"] / (inp["r_op"] - inp["g_nbv"]) * (1.0 - k)) * inp["hold_ins"]


def gordon_leg(eq: float, roe: float, r: float, payout: float) -> tuple[float, float, float, str]:
    """(value 亿, PE, g, ruler) for a retaining leg at b = 1 - payout."""
    cap = g_cap(r)
    g_raw = (1.0 - payout) * roe
    if g_raw <= cap:
        return eq * roe * perpetual_pe(g_raw, roe, r), perpetual_pe(g_raw, roe, r), g_raw, "perpetual"
    if g_raw - cap > CAP_TRIM_MAX:
        raise ValueError(f"policy g {g_raw:.4f} over cap {cap:.4f} by > 2pp — not a dividend payer")
    pe = capped_payout_pe(g_raw, roe, r, payout)
    return eq * roe * pe, pe, cap, "capped_payout"


def bank_leg(inp: dict[str, float], roe: float, k: float) -> float:
    """g = 0 PB-ROE less k × excess retention; payout 0 → excess = E / r."""
    e = inp["lj_bv"] * roe
    return e / inp["r_bank"] * (1.0 - k)


def legs(inp: dict[str, float]) -> dict[str, dict[str, float]]:
    k = k_ins(inp)
    out: dict[str, dict[str, float]] = {}
    for lab in TIERS:
        lo = lab.lower()
        t, *_ = gordon_leg(inp["trust_eq"] * inp["hold_trust"], inp[f"roe_trust_{lo}"],
                           inp["r_op"], inp["payout_obs"])
        f, *_ = gordon_leg(inp["fut_eq"] * inp["hold_fut"], inp[f"roe_fut_{lo}"],
                           inp["r_op"], inp["payout_obs"])
        out[lab] = {
            "ins": ins_leg(inp, k[lab]),
            "trust": t,
            "fut": f,
            "lj": bank_leg(inp, inp[f"roe_lj_{lo}"], inp[f"k_lj_{lo}"]),
            "hq": inp["hq_ni"] / inp["r_op"],
        }
    return out


def anchors(inp: dict[str, float]) -> tuple[float, float, float]:
    lg = legs(inp)
    return tuple(sum(lg[lab].values()) / inp["shares"] for lab in TIERS)


def calculate(context):
    inp = dict(INPUTS)
    if any(key not in inp for key in REQUIRED):
        raise ValueError('missing required historical inputs')
    if any(isinstance(inp[key], bool) or not isinstance(inp[key], (int, float))
           or not math.isfinite(inp[key]) for key in REQUIRED):
        raise ValueError('historical inputs must be finite numbers')
    if inp['shares'] <= 0 or inp['r_op'] <= inp['g_nbv'] or inp['r_bank'] <= 0:
        raise ValueError('share count or discount domain is invalid')
    lg = legs(inp)
    prices = {tier: sum(lg[tier].values()) / inp['shares'] for tier in TIERS}
    if not prices['L'] < prices['M'] < prices['H']:
        raise ValueError('historical price tiers are not ordered')
    values = lambda field: {tier: lg[tier][field] / inp['shares'] for tier in TIERS}
    params = {}
    for name, eq, hold in (('trust', 'trust_eq', 'hold_trust'), ('futures', 'fut_eq', 'hold_fut')):
        prefix = 'trust' if name == 'trust' else 'fut'
        roes = {tier: inp[f'roe_{prefix}_{tier.lower()}'] for tier in TIERS}
        details = {tier: gordon_leg(inp[eq] * inp[hold], roes[tier], inp['r_op'], inp['payout_obs'])
                   for tier in TIERS}
        params[name] = {'discount_rate': {'unit': 'RATIO', 'values': {t: inp['r_op'] for t in TIERS}},
                        'forward_return': {'unit': 'RATIO', 'values': roes},
                        'growth_rate': {'unit': 'RATIO', 'values': {t: details[t][2] for t in TIERS}}}
    params['insurance'] = {'discount_rate': {'unit': 'RATIO', 'values': {t: inp['r_op'] for t in TIERS}},
                           'growth_rate': {'unit': 'RATIO', 'values': {t: inp['g_nbv'] for t in TIERS}},
                           'erosion_share': {'unit': 'RATIO', 'values': k_ins(inp)}}
    params['bank'] = {'discount_rate': {'unit': 'RATIO', 'values': {t: inp['r_bank'] for t in TIERS}},
                      'growth_rate': {'unit': 'RATIO', 'values': {t: 0. for t in TIERS}},
                      'forward_return': {'unit': 'RATIO',
                          'values': {t: inp[f'roe_lj_{t.lower()}'] for t in TIERS}}}
    return {'ticker': '002423.SZ', 'currency': 'CNY', 'units': {'price': 'CNY_PER_SHARE'},
            'valuation_as_of': None, 'framework_as_of': None,
            'historical_financial_statement_as_of': '2026-06-30',
            'historical_research_as_of': '2026-10-09', 'anchors': prices,
            'candidate': None, 'option': None,
            'segments': {name: {'unit': 'CNY_PER_SHARE', 'values': values(key)}
                         for name, key in (('insurance', 'ins'), ('trust', 'trust'),
                                           ('futures', 'fut'), ('bank', 'lj'), ('headquarters', 'hq'))},
            'key_parameters': params,
            'review_flags': ['insurance_three_year_same_basis_window',
                             'insurance_dividends_and_capital_injections_unverified',
                             'insurance_2024_2025_discount_rate_proxy',
                             'subsidiary_dividend_policy_proxy'],
            'basis_changed': None,
            'partial_basis_changed': local_basis_changed({'inputs': INPUTS, 'cap_trim_max': CAP_TRIM_MAX}, BASELINE_LOCAL)}
