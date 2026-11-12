#!/usr/bin/env python3
"""Historical Huayou model: offline reconciliation only, not a confirmed band.

Eight product gross-profit components form an overall earnings bridge; their
expenses and minority interests are not separately disclosed. The company's
observed profit-to-parent conversion drives scenarios, while copper is tied to
the shared historical price axis. Pomalaa's unspent investment is deducted and
only the already-invested share enters the option to avoid double counting.
"""
from __future__ import annotations
import math
from lib.gordon import basket_r, check_branch, check_g_cap, check_r, payout_gap, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'partial_basis'),
                'axes': {'gold_copper': 'fed_path_gold_copper'},
                'peers': {'zijin': '601899.SH'}}
BASELINE_LOCAL = '442b73fc1c60d21588376702350a54c544933c31b9e7e3b99c8aa74b0390f25f'

YI = 1e8

# Audited baseline: 2026 interim net profit to parent x 2 (35.074054亿 x 2).
# The M scenario re-uses the interim segment table verbatim, so its recomputed
# net profit must land back on this number — that is what welds the eight-leg
# bridge to the filing.
BASE_NP_PARENT_YI = 70.1481
BASE_NP_TOL_YI = 0.5

# skill A2e-1: if the earnings scenario falls below this share of M the
# earnings ruler has failed at L and must be re-opened.  Read on the L scenario
# before the Pomalaa unspent-capital penalty (user ruling 2026-10-18, A23).
SCENARIO_L_MIN_RATIO = 0.30
# A12: 2025H1 eight-leg gross profit annualised (58.92 x 2), for the rigid-opex
# L reading only — the number that shows why L pairs opex with its own period.
GP_2025H1_ANNUALISED = 118.0
# A19: the alternative basket (印尼国别附加) is a disclosure coordinate, not the ruler.
ALT_BASKET = 7

G2_TOL = 1e-4             # stated g2 must equal the cluster blend recomputed from its parts (A13)
MIN_PRINT_MONTHS = 6      # A18: fewer EPS-matched months than this -> corroboration only, not a g2 source
G2_LEVER_PP = 0.01        # valuation-rules: L/M/H re-read at g2 ± this (g2 lever, disclosure)
TOL = 0.05
# 表3 per-tier credit on the Pomalaa option (A11): 拍值, never an Input, never the base.
P_K = (0.0, 0.25, 1.0)

# The shared USD copper ladder: our field -> the peer framework's field.
SHARED_LADDER = {"p_cu_l": "lme_cu_l", "p_cu_m": "lme_cu_m", "p_cu_h": "lme_cu_h"}

REQUIRED = [
    "shares", "bps", "pb_floor",
    "gp_ni_prod_m", "gp_ni_prod_h",
    "gp_ni_mhp_m", "gp_ni_mhp_h",
    "gp_co_m", "gp_li_m", "gp_cam_m",
    "gp_pcam_m", "gp_pcam_h",
    "gp_trade_m",
    "rev_cu_base", "cost_cu_base",
    "p_cu_l", "p_cu_m", "p_cu_h",
    "opex", "pretax_l",
    "conv_l", "conv_m", "conv_h",
    "equity_parent", "r_perp", "g_cu_cluster", "g_li_cluster", "w_cu_gp", "w_li_gp", "g2",
    "pe_print_lo", "pe_print_hi", "g_print_m", "g_print_lo", "g_print_hi", "n_print_m",
    "pomalaa_kt", "mhp_unit_gp", "t_opt", "pomalaa_spent_share",
    "eps_cons_lo", "eps_cons_mean", "eps_cons_hi",
    "payout_actual", "window_years",
    "pom_budget", "roic_pom_l", "roic_pom_m", "roic_pom_h",
]
# A21: the D-bucket conclusion that licenses the check_branch downgrade must be
# written in §2, not just implied by the inputs.
D_BUCKET_TAG = "D 桶"
CONSENSUS_BAND = 0.20  # ②-b: |EPS_M / consensus mean - 1| beyond this needs a named measured variable

# Legs that are already at their measured peak in the interim print, so the H
# scenario leaves them where they are (see A7 / A8 / A9 / A5).
FLAT_LEGS = ("gp_co_m", "gp_li_m", "gp_cam_m", "gp_trade_m")


INPUTS = {
    'shares': 1893527517.0,  # 总股本 1,893,527,517 股；中报；2026-06-30
    'bps': 26.8656,  # 每股净资产 CNY ＝ 归母权益 508.7077 亿 ÷ 总股本；2026-06-30
    'pb_floor': 1.0228,  # **实测 PB 地板** ＝ 2024-06 最低价 20.82 ÷ 当期 BPS 20.3557（＝ 归母权益 345.4789 亿 ÷ 16.9721 亿股）；**只披露不 max()**（sediment-framework §13 峰形区地板条款）——L = 盈利情景，地板 27.48 作 [L, H] 内坐标进表2；2024-06
    'gp_ni_prod_m': 42.1654,  # 镍产品腿 M 档年化毛利 ＝ 21.0827 × 2；见 A6；2026H1
    'gp_ni_prod_h': 54.7724,  # 镍产品腿 H 档 ＝ **2024H2 实测峰** 27.3862 × 2；2024H2
    'gp_ni_mhp_m': 27.6456,  # 镍中间品（MHP）腿 M 档 ＝ 13.8228 × 2；2026H1
    'gp_ni_mhp_h': 31.3256,  # 镍中间品腿 H 档 ＝ **2025H2 实测峰** 15.6628 × 2；2025H2
    'gp_co_m': 29.378,  # 钴腿 ＝ 14.6890 × 2；当期已是五个半年度的实测峰，三档不变；见 A7；2026H1
    'gp_li_m': 21.1622,  # 锂腿 ＝ 10.5811 × 2；当期已是实测峰，三档不变；见 A9；2026H1
    'gp_cam_m': 37.5326,  # 正极材料腿 ＝ 18.7663 × 2；当期已是实测峰，三档不变；见 A8；2026H1
    'gp_pcam_m': 13.8498,  # 三元前驱体腿 M 档 ＝ 6.9249 × 2；2026H1
    'gp_pcam_h': 14.7274,  # 三元前驱体腿 H 档 ＝ **2024H2 实测峰** 7.3637 × 2；2024H2
    'gp_trade_m': 30.4444,  # 贸易及其他腿 ＝ 15.2222 × 2；**约 9.9 亿无解释，见 A5（最高优先级待补）**；2026H1
    'rev_cu_base': 39.524,  # 铜腿年化收入 ＝ 19.7620 × 2；中报分商品表；2026H1
    'cost_cu_base': 23.9509,  # 铜腿年化成本 ＝ 11.9754 × 2；三档不变（价格全额传导，见 A10）；2026H1
    'opex': 91.82,  # 毛利→利润总额的净额（期间费用 + 减值 + 公允价值变动 − 投资收益 + 其他业务净额），年化 ＝ 217.7512 − 125.9312；三档不变，见 A12；2026H1
    'pretax_l': 74.8456,  # **L 档利润总额**（年化）＝ 2025H1 实测 37.4228 × 2。`opex` 与毛利**同期配对**，复合效应已完整落在实测数字里，不二次外推；见 §3 L 档说明与 A12；2025H1
    'conv_l': 0.387835,  # **L** 利润总额→归母转换率 ＝ 2026Q2 实测（归母 10.1013 ÷ 利润总额 26.0453）；见 A3；2026Q2
    'conv_m': 0.557035,  # **M** ＝ 2026H1 实测（35.0741 ÷ 62.9656）；2026H1
    'conv_h': 0.7336,  # **H** ＝ FY2025 实测全年（归母 ÷ 利润总额）——**市场基准世界**（②-b：共识 FY2026E 均值 5.669 高于旧 H 5.35，H 换成市场默认的分配结构，见 A3 / 属性 F）；旧 H 的 2026Q1 67.64% 降为 `optimistic` 行坐标；FY2025
    'eps_cons_lo': 5.332,  # 共识 FY2026E EPS 区间下沿（LB forecast-eps，中报后）；**只作 ②-b 判据与交叉，不进公式**（A1）；2026-09-08
    'eps_cons_mean': 5.669,  # 共识 FY2026E EPS 均值；②-b 判据：须落在 [EPS_M, EPS_H] 内（A1）；2026-09-08
    'eps_cons_hi': 6.006,  # 共识 FY2026E EPS 区间上沿；交叉；2026-09-08
    'equity_parent': 508.7077,  # 归母权益（亿 CNY）；中报；各档 ROE = 归母净利 ÷ 本值（A13）；2026-06-30
    'r_perp': 0.13,  # 篮 6 周期商品 / 小盘 13%：整公司八腿合成一只 PE，商品价函数、印尼敞口重（A19；真源 `eval/lib/gordon.py BASKET_R`）；备选篮 7 15%（印尼国别附加）只作敏感性披露；`check_r` → r 等于篮 6 值；2026-09-20
    'g_cu_cluster': 0.025,  # 铜腿 g2 = sediment-framework §13 商品腿 tier 默认——铜实际价格漂移 ≈ 0 + 通胀 **2.5%**（与 `601899.SH` / `603993.SH` 铜金腿同）；商品腿不走同业反解（A13）；2026-09-20
    'g_li_cluster': 0.0,  # 锂腿 g2 = sediment-framework §13 商品腿 tier 默认——锂实际价格漂移 ≤ −3%/yr → **0**，不取负；商品腿不走同业反解（A13）；2026-09-20
    'w_cu_gp': 0.0715,  # 铜腿占 M 档毛利权重（15.57 ÷ 217.75）；A13；2026H1
    'w_li_gp': 0.0972,  # 锂腿占 M 档毛利权重（21.16 ÷ 217.75）；A13；2026H1
    'g2': 0.0018,  # **§13 商品腿 tier·按毛利权重合成**：永续增速 = g_cu_cluster × w_cu_gp + g_li_cluster × w_li_gp = 2.5% × 7.15% + 0 × 9.72% = **0.18%**（其余六腿 0）；三档共用，H 档 g ≤ M 档取等；eval 复算校验（A13）；cap = min(6%, r − 4%) = 6%；2026-09-20
    'pe_print_lo': 9.04,  # **护栏下沿**：M 档 EPS ±12% 配对月（2026-05～08）最低 PE（2026-08，前复权收 35.69 ÷ 可见 TTM 3.95）；A18；2026-08
    'pe_print_hi': 12.22,  # **护栏上沿**：同配对月最高 PE（2026-05，48.26 ÷ 3.95）；A18；2026-05
    'g_print_m': 0.002,  # M 档配对月按可见 ROE 14.3% 反解 g 的中位（+4.23 / +0.33 / +0.06 / −1.07%）；**n < 6 只作印证**（A18）；2026-09-14
    'g_print_lo': -0.0107,  # 配对月反解 g 的最低值（2026-08，PE 9.04）；杠杆披露的证据区间下端（A18）；2026-08
    'g_print_hi': 0.0423,  # 配对月反解 g 的最高值（2026-05，PE 12.22）；证据区间上端（A18）；2026-05
    'n_print_m': 4.0,  # M 档配对月数（< 6 → 配对不足，g2 不由此取）；A18；2026-09-14
    'pomalaa_kt': 12.0,  # Pomalaa 项目份数：12 万吨镍（MHP），预计 2026 年底投产；期权用（A11）；2026-08-18
    'mhp_unit_gp': 1.428,  # 已实现单位：2026H1 MHP 腿毛利 13.8228 亿 ÷ 出货 9.68 万吨（亿 CNY / 万吨）；期权用（A11）；2026H1
    't_opt': 1.0,  # 期权折现年数（投产在一年后，A15 边界条款）；折现率 = `r_perp`；2026-09-14
    'pomalaa_spent_share': 0.411,  # **Pomalaa 已投 ÷ 预算** = 100.14 ÷ 243.64 亿（中报「重要在建工程」表，累计投入占预算 41.10%、工程进度 78%）；期权只定价**已花部分**的产出——未花 143.5 亿由未投资本罚项按 ROIC/r 记值，再进期权即双计（A11 / A22）；2026-06-30
    'payout_actual': 0.155,  # **实付派息率** = FY2025 现金分红 9.48 亿 ÷ 归母 61.10 亿（三年均值 28.8%、2025–27 规划下限 20% 只作敏感性）；**不进倍数、不进锚点**，只算「模型视同派出、实际留存的现金/股」披露行（A21 / A22）；FY2025
    'window_years': 2.5,  # **D 桶窗口年数**：2026H2–FY2028（Pomalaa 剩余 143 亿 + 华星 10 + Sorowako 6 万吨 + Ewoyaa），终点 = Sorowako / 华星投产；E 桶回退触发见 A21；2026-09-21
    'pom_budget': 243.64,  # Pomalaa 12 万吨镍预算 亿 CNY（中报「重要在建工程」表）；未投 = 本值 × (1 − `pomalaa_spent_share`) = 143.50 亿（A22）；2026-06-30
    'roic_pom_l': 0.064,  # **L** 世界的 Pomalaa 项目回报：套华飞 FY2025 经济 NOPAT 15.6 亿 → ROIC 6.4%；未投资本罚项用（A22）；2026-09-21
    'roic_pom_m': 0.103,  # **M** 世界：套华飞 2026H1 经济 NOPAT 25.1 亿 → ROIC 10.3%（A22）；2026-09-21
    'roic_pom_h': 0.103,  # **H** 世界：取 M 的 10.3% 作下限（偏保守）（A22）；2026-10-16
}

# The old research explicitly names conversion-rate change as the measured
# driver of the >20% consensus gap and identifies the project-funded D bucket.
NAMED_CONVERSION_RATIONALE = True
NAMED_PROJECT_RETENTION = True


def pomalaa_option(inp, pe_m, r, base):
    unavailable = {'status': 'unavailable', 'label': 'Pomalaa 已投资部分', 'anchors': None}
    if not (0 < inp['pomalaa_spent_share'] <= 1) or inp['t_opt'] < 0:
        return unavailable, None
    try:
        full = (inp['pomalaa_kt'] * inp['mhp_unit_gp'] * inp['conv_m'] * pe_m * YI
                / inp['shares'] / (1 + r) ** inp['t_opt'])
        value = full * inp['pomalaa_spent_share']
        adjusted = {tier: base[tier] + weight * value for tier, weight in zip('LMH', P_K)}
    except (ArithmeticError, ValueError, OverflowError):
        return unavailable, None
    if (not math.isfinite(full) or not math.isfinite(value) or value < 0
            or any(not math.isfinite(v) for v in adjusted.values())
            or not adjusted['L'] < adjusted['M'] < adjusted['H']):
        return unavailable, None
    return {'label': 'Pomalaa 已投资部分', 'value': value, 'value_unit': 'CNY_PER_SHARE',
            'weights': dict(zip('LMH', P_K)), 'anchors': adjusted}, full


def _historical_calculation(inp, peer):
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    if any(isinstance(inp[k], bool) or not isinstance(inp[k], (int,float)) or not math.isfinite(inp[k]) for k in REQUIRED):
        raise ValueError('required inputs must be finite numbers')
    if not float(inp['n_print_m']).is_integer() or inp['n_print_m'] < 0:
        raise ValueError('number of observed months must be a nonnegative integer')
    if (inp['shares'] <= 0 or inp['equity_parent'] <= 0 or inp['p_cu_m'] <= 0
            or inp['r_perp'] <= 0 or inp['r_perp'] <= inp['g2']):
        raise ValueError('valuation denominator or perpetuity domain is invalid')
    warnings = ['historical_own_band_outside', 'historical_leverage_ev_unreviewed']
    # --- sanity guards (see §3 校验步骤) -------------------------------------
    errors += ladder("copper price", inp["p_cu_l"], inp["p_cu_m"], inp["p_cu_h"])
    errors += ladder("conv", inp["conv_l"], inp["conv_m"], inp["conv_h"])
    # Perpetuity inputs (A13 / A19): r is the named basket's value (valuation-
    # rules「§r 篮子」), g2 under g_cap(r) and equal to the gross-profit-weighted
    # tier blend it claims to be.
    errors += check_r(inp["r_perp"], "r_perp", 6)
    errors += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    g2_blend = inp["g_cu_cluster"] * inp["w_cu_gp"] + inp["g_li_cluster"] * inp["w_li_gp"]
    if abs(inp["g2"] - g2_blend) > G2_TOL:
        errors.append(f"g2={inp['g2']} != cluster blend {g2_blend:.5f} (A13)")
    if inp["g2"] < 0:
        errors.append("g2 < 0 contradicts the same-world gate: consensus FY25->FY26E is up (A1/A13)")
    if not (0 < inp["pe_print_lo"] < inp["pe_print_hi"]):
        errors.append("print band malformed (A18)")
    # `p_cu_*` is the copper price ladder; the banned names are the option credits.
    leaked = [k for k in inp if k in ("p", "p_l", "p_m", "p_h") or k.startswith("p_k")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    for leg in ("gp_ni_prod", "gp_ni_mhp", "gp_pcam"):
        if inp[f"{leg}_h"] < inp[f"{leg}_m"]:
            errors.append(f"{leg}: H ({inp[f'{leg}_h']}) below M ({inp[f'{leg}_m']})")
    for k in ("conv_l", "conv_m", "conv_h"):
        if not (0.0 < inp[k] < 1.0):
            errors.append(f"{k}={inp[k]} outside (0,1)")
    if inp["cost_cu_base"] >= inp["rev_cu_base"]:
        errors.append("copper leg: cost exceeds revenue at base — check 口径")
    # A21 retention inputs: payout in (0,1), a named window, k ladder within [0,1].
    if not (0.0 < inp["payout_actual"] < 1.0):
        errors.append(f"payout_actual={inp['payout_actual']} outside (0,1)")
    if inp["window_years"] <= 0:
        errors.append("window_years must be > 0 (D 桶窗口终点 MUST 具名, A21)")
    # A22 Pomalaa project return per tier world: worse world, lower return.
    if not (0.0 < inp["roic_pom_l"] <= inp["roic_pom_m"] <= inp["roic_pom_h"] < 1.0):
        errors.append(
            f"Pomalaa ROIC ladder L ≤ M ≤ H within (0,1) violated: "
            f"{inp['roic_pom_l']}/{inp['roic_pom_m']}/{inp['roic_pom_h']}"
        )
    if inp["pom_budget"] <= 0:
        errors.append("pom_budget must be > 0 (A22)")
    if errors:
        warnings.append('historical_input_guards_require_review')
        errors = []

    # The shared copper axis determines this model. A missing or incomplete
    # peer snapshot is a comparison gap, not a reason to erase its base band.
    peer_status = 'peer_comparison_unavailable'
    if isinstance(peer, dict):
        operating = peer.get('operating', {})
        shared = operating.get('shared_prices', {}) if isinstance(operating, dict) else {}
        if isinstance(shared, dict):
            values = [(inp[ours], shared.get(other)) for ours, other in SHARED_LADDER.items()]
            def valid(value):
                try:
                    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                except OverflowError:
                    return False
            if any(valid(value) and abs(ours - value) > 1e-6 for ours, value in values):
                peer_status = 'peer_comparison_differs'
            elif all(valid(value) for _, value in values):
                peer_status = 'peer_comparison_matched'

    # --- the ruler -----------------------------------------------------------
    def copper_leg(price_usd_t: float) -> float:
        """Annualised copper gross profit, 亿 CNY — the only price-shifted leg."""
        return inp["rev_cu_base"] * price_usd_t / inp["p_cu_m"] - inp["cost_cu_base"]

    def gross_profit(suffix: str, p_cu: float) -> float:
        legs = sum(inp[k] for k in FLAT_LEGS)
        legs += sum(inp[f"{leg}_{suffix}"] for leg in ("gp_ni_prod", "gp_ni_mhp", "gp_pcam"))
        return legs + copper_leg(p_cu)

    r, g2 = inp["r_perp"], inp["g2"]
    ROIC_POM = (inp["roic_pom_l"], inp["roic_pom_m"], inp["roic_pom_h"])
    unspent = inp["pom_budget"] * (1.0 - inp["pomalaa_spent_share"])

    def penalty(roic: float, r_: float = r) -> float:
        # A22 named-project rule: unspent capex earning below r costs
        # unspent × (1 − ROIC/r); a project at or above r costs nothing.
        return unspent * max(1.0 - roic / r_, 0.0) * YI / inp["shares"]

    def anchor(pretax: float, conv: float, g: float, r_: float = r, roic: float = 1.0) -> tuple[float, ...]:
        # Tier ROE on parent book; the multiple is Gordon on that ROE with the
        # shared g (A13). ROE <= r pins the multiple at 1/r — a result, not a bug.
        # The 「视同派出」row is disclosure only (A21 / A22); the anchor is the
        # earnings value less the Pomalaa unspent-capital penalty in that
        # tier's world. Neither enters the multiple.
        np_parent = pretax * conv
        eps = np_parent * YI / inp["shares"]
        roe = np_parent / inp["equity_parent"]
        pe = perpetual_pe(g, roe, r_)
        pre = eps * pe
        row = max(1.0 - inp["payout_actual"] - g / roe, 0.0) * eps * inp["window_years"]
        pen = penalty(roic, r_)
        return np_parent, eps, roe, pe, pre, row, pen, pre - pen

    gp_m = gross_profit("m", inp["p_cu_m"])
    gp_h = gross_profit("h", inp["p_cu_h"])
    pretax_m, pretax_h = gp_m - inp["opex"], gp_h - inp["opex"]

    def tiers(g: float, r_: float = r, roics: tuple[float, float, float] = ROIC_POM) -> tuple[tuple, tuple, tuple]:
        # H carries g <= M's (post-peak normalisation, A13) — equal here.
        return (
            anchor(inp["pretax_l"], inp["conv_l"], g, r_, roics[0]),
            anchor(pretax_m, inp["conv_m"], g, r_, roics[1]),
            anchor(pretax_h, inp["conv_h"], min(g, g), r_, roics[2]),
        )

    (np_l, eps_l, roe_l, pe_l, pre_l, row_l, pen_l, scenario_l), (np_m, eps_m, roe_m, pe_m, pre_m, row_m, pen_m, M), (np_h, eps_h, roe_h, pe_h, pre_h, row_h, pen_h, H) = tiers(g2)

    # The PB floor is disclosure only (§13 峰形区地板条款): L is the scenario.
    floor = inp["pb_floor"] * inp["bps"]
    L = scenario_l

    # Guardrail (A18, valuation-rules ④): the M multiple is read against the
    # band the market actually printed at this earnings level. The own 5y PE
    # band is not the target for a cyclical — it was printed at EPS <= 2.9.
    # At the basket r the multiple sits below the band: ③ 出带 is disclosed
    # (ruled a numerator issue, repo-level, pending), not asserted.
    in_band = inp["pe_print_lo"] - 1e-9 <= pe_m <= inp["pe_print_hi"] + 1e-9
    # r at which the M multiple would reach the band floor, same Gordon form.
    r_band_lo = ((1 - g2 / roe_m) / inp["pe_print_lo"] + g2
                 if inp["pe_print_lo"] > 0 and roe_m != 0 else None)
    if r_band_lo is None:
        warnings.append('historical_band_reference_unavailable')
    print_is_evidence = inp["n_print_m"] >= MIN_PRINT_MONTHS

    # Baseline closure: M must reproduce the filed net profit to parent.
    if abs(np_m - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {np_m:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    # skill A2e-1: an earnings scenario this far below M means the earnings
    # ruler no longer describes the downside — that is a conversation, not a
    # number to ship.  Read before the Pomalaa penalty (user ruling 2026-10-18,
    # A23): the penalty is a named-project capital deduction, not the ruler.
    ratio = pre_l / M if M else 0.0
    ratio_post = scenario_l / M if M else 0.0
    if ratio < SCENARIO_L_MIN_RATIO:
        errors.append(
            f"A2e-1: pre-penalty scenario_L/M={ratio:.3f} < {SCENARIO_L_MIN_RATIO} "
            "— earnings ruler has failed at L, reopen the framework"
        )

    # 裁决顺序 ②-b (valuation-rules): a bottom-up ladder may stand in for the
    # consensus three points only if the consensus mean sits inside [M, H] and
    # M is within 20% of it — or, beyond 20%, a measured structural variable
    # (here conv) is named with a falsification trigger (the ②-b tag in §2).
    if not (eps_m <= inp["eps_cons_mean"] <= eps_h):
        errors.append(
            f"②-b: consensus FY26E mean {inp['eps_cons_mean']} outside [EPS_M {eps_m:.3f}, EPS_H {eps_h:.3f}]"
            " — H must be the market-base world"
        )
    cons_dev = eps_m / inp["eps_cons_mean"] - 1.0 if inp["eps_cons_mean"] else None
    if cons_dev is None:
        warnings.append('historical_consensus_comparison_unavailable')
    if cons_dev is not None and abs(cons_dev) > CONSENSUS_BAND and not NAMED_CONVERSION_RATIONALE:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus mean with no ②-b named-variable row in §2")

    # skill A2e-2c: the three tiers must already be a ladder in the numerator,
    # so re-run them all at the M multiple and check the ordering survives.
    flat = (eps_l * pe_m, eps_m * pe_m, eps_h * pe_m)
    errors += ladder("flat-multiple", *flat)

    # Payout branch (valuation-rules「选分支」): the shared g2 implies a ~99%
    # payout at ROE_M while the company pays payout_actual. The red light is
    # downgraded to a payout_gap disclosure only when §2 carries the D-bucket
    # conclusion (A21; the unspent Pomalaa capital is priced by the A22
    # penalty); otherwise it stays an error.
    branch = check_branch(g2, roe_m, r, inp["payout_actual"], "M")
    modelled_payout, gap = payout_gap(g2, roe_m, inp["payout_actual"])
    d_bucket = NAMED_PROJECT_RETENTION
    if branch and not d_bucket:
        errors += branch

    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")

    # g2 leverage (valuation-rules「g2 的杠杆 MUST 显式」): L/M/H are re-read
    # at g2 ± 1pp and across the print evidence range — disclosed, not a blocker.
    def band_at(g: float, r_: float = r, roics: tuple[float, float, float] = ROIC_POM) -> tuple[float, float, float]:
        return tuple(t[7] for t in tiers(g, r_, roics))

    lever = {}
    for tag, growth in (("-1pp", g2 - G2_LEVER_PP), ("+1pp", g2 + G2_LEVER_PP),
                        ("print_lo", inp["g_print_lo"]), ("print_hi", inp["g_print_hi"])):
        try:
            values = band_at(growth)
            lever[tag] = values if all(math.isfinite(value) for value in values) else None
        except (ArithmeticError, ValueError, OverflowError):
            lever[tag] = None
        if lever[tag] is None:
            warnings.append('historical_growth_sensitivity_unavailable')

    # --- Pomalaa option (A11): own realised MHP unit x 12 kt, conv_m, M multiple, one year,
    # x spent share — the unspent capex is priced by the named-project penalty (A22) ---
    option, v_opt_full = pomalaa_option(inp, pe_m, r, dict(zip('LMH', (L, M, H))))
    if option.get('status') == 'unavailable':
        warnings.append('pomalaa_option_unavailable')
    if not (L < M < H):
        raise ValueError('base valuation tiers must be ordered')
    if errors:
        warnings.append('historical_economic_guards_require_review')
    labels = ('L', 'M', 'H')
    tv = lambda values: dict(zip(labels, values))
    raw_tiers = ((np_l, eps_l, roe_l, pe_l, pre_l, row_l, pen_l, L),
                 (np_m, eps_m, roe_m, pe_m, pre_m, row_m, pen_m, M),
                 (np_h, eps_h, roe_h, pe_h, pre_h, row_h, pen_h, H))
    return {'ticker':'603799.SH', 'currency':'CNY', 'valuation_as_of':None, 'framework_as_of':None,
            'anchors':tv((L,M,H)), 'candidate':None,
            'option': option,
            'review_flags': warnings + [peer_status],
            'segments':{'company':{'values':tv((L,M,H))}},
            'key_parameters':{'discount_rate':tv((r,)*3), 'growth_rate':tv((g2,)*3),
                              'forward_return':tv((roe_l,roe_m,roe_h)),
                              'steady_return':tv((None,)*3), 'multiple':tv((pe_l,pe_m,pe_h))},
            'operating':{'tiers':tv(raw_tiers), 'gross_profit':{'M':gp_m,'H':gp_h},
                         'pretax':tv((inp['pretax_l'],pretax_m,pretax_h)),
                         'copper':tv(copper_leg(inp['p_cu_'+t.lower()]) for t in labels),
                         'unspent':unspent, 'floor':floor, 'pre_penalty_ratio':ratio,
                         'post_penalty_ratio':ratio_post, 'in_band':in_band, 'band_floor_rate':r_band_lo,
                         'consensus_deviation':cons_dev, 'payout_gap':gap, 'modelled_payout':modelled_payout,
                         'flat':tv(flat), 'option_full':v_opt_full,
                         'shared_prices':{k: inp[k] for k in SHARED_LADDER}},
            'sensitivity':{'growth':{k:(tv(v) if v is not None else None) for k,v in lever.items()},
                           'alt_basket':tv(band_at(g2,basket_r(ALT_BASKET))),
                           'basket_4':tv(band_at(g2,basket_r(4))),
                           'old_penalty_mapping':tv(band_at(g2,r,(1.0,ROIC_POM[1],ROIC_POM[0]))),
                           'no_penalty':tv((pre_l,pre_m,pre_h)),
                           'rigid_opex':anchor(GP_2025H1_ANNUALISED-inp['opex'],inp['conv_l'],g2,r,ROIC_POM[0])[7]}}

def calculate(context):
    copper = context['axes']['gold_copper']['stock_fields']
    selected = {key: copper[key] for key in ('p_cu_l', 'p_cu_m', 'p_cu_h')}
    result = _historical_calculation({**INPUTS, **selected}, context.get('peers', {}).get('zijin'))
    result['units'] = {'price': 'CNY_PER_SHARE'}
    result['segments']['company']['unit'] = 'CNY_PER_SHARE'
    for name in ('discount_rate', 'growth_rate', 'forward_return', 'steady_return'):
        result['key_parameters'][name] = {'unit': 'RATIO', 'values': result['key_parameters'][name]}
    result['valuation_as_of'] = result['framework_as_of'] = None
    result['historical_financial_statement_as_of'] = '2026-06-30'
    result['historical_research_as_of'] = '2026-10-18'
    result['basis_changed'] = None
    constants = {'option_weights': P_K, 'unit_scale': YI, 'minimum_months': MIN_PRINT_MONTHS,
                 'alternative_basket': ALT_BASKET, 'historical_profit': BASE_NP_PARENT_YI,
                 'historical_profit_tolerance': BASE_NP_TOL_YI, 'minimum_ratio': SCENARIO_L_MIN_RATIO,
                 'consensus_band': CONSENSUS_BAND, 'flat_legs': FLAT_LEGS,
                 'growth_comparison_tolerance': G2_TOL, 'growth_sensitivity_step': G2_LEVER_PP,
                 'rigid_opex_reference': GP_2025H1_ANNUALISED, 'peer_fields': SHARED_LADDER,
                 'named_conversion': NAMED_CONVERSION_RATIONALE, 'named_retention': NAMED_PROJECT_RETENTION}
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'copper': selected, 'constants': constants}, BASELINE_LOCAL)
    return result
