"""Historical Corning SOTP; input sources and original reasoning remain below."""
from __future__ import annotations
import math
from lib.gordon import annuity_factor, check_branch
from lib.partial_basis import local_basis_changed

# The Chinese bare-fiber price is only a cross-reference: Corning's US
# long-term contracts are not valued from the Chinese spot-price scenarios.
DEPENDENCIES = {'libraries': ('gordon', 'partial_basis'),
                'axes': {'capex': 'ai_capex', 'fiber': 'optical_fiber'}}
BASELINE_LOCAL = '9fd9ec929f866dacca5d45a68d02c7f817be5a1fe758a292def85454ab6350d9'
ANCHOR_YEAR, N_STAGE, MM = 2027, 1, 1e6
PE_HARD_CAP = 30.
TIERS, LEGS = ('l', 'm', 'h'), ('oc', 'gi', 'au')
P_SIGNED = {'l': 0., 'm': 0., 'h': 0.}
P_RENEW = {'l': 0., 'm': 0., 'h': 0.}
P_PHOT = {'l': 0., 'm': 0., 'h': 1.}
INPUTS = {
    'shares_diluted': 871000000.0,  # 稀释股本（Q3 摊薄加权，8-K 2026-10-27；完全稀释口径核对见 A35） 2026-09-30
    'shares_outstanding': 861401106.0,  # 已发行普通股；Q3 10-Q 封面（10-23），仅作稀释口径核对 2026-10-23
    'prefunded_warrant': 3000000.0,  # NVIDIA 预融资权证股数（EPS 口径视同流通，A35） 2026-05-06
    'warrant_shares': 15000000.0,  # NVIDIA 认股权证股数（A35） 2026-05-06
    'warrant_strike': 180.0,  # 认股权证行权价 USD（A35；锚点 / 表3 超过即须稀释） 2026-05-06
    'eps_fy27_m': 4.52516,  # FY2027 core EPS 共识均值，yfinance +1y，18 家（A1） 2026-11-05
    'eps_fy27_h': 4.99,  # 同源 FY2027 EPS 上沿，18 家 2026-11-05
    'eps_fy27_low': 4.19,  # 同源 FY2027 EPS 下沿；L 仍取实测消化年 2026-11-05
    'eps_fy28_pt_ms': 5.6,  # 大摩财报后 FY2028 EPS；媒体转述，非完整模型（A15） 2026-10-29
    'eps_fy28_pt_bernstein': 5.7,  # 伯恩斯坦财报后 FY2028 EPS；同篇转述（A15） 2026-10-29
    'oc_ni_fy22': 661.0,  # OC 分部净利 FY2022（消化年前；Q4'23 新闻稿；A1） 2024-01-30
    'oc_ni_fy23': 478.0,  # OC 分部净利 FY2023（实测消化年；同上；A1） 2024-01-30
    'ni_oc_q': 532.0,  # OC 分部净利/季（L 的运行率起点；A32 推断输入） 8-K 2026-10-27（Q3）
    'ni_gi_q': 328.0,  # GI 分部净利/季 8-K 2026-10-27（Q3）
    'ni_au_q': 67.0,  # Automotive 分部净利/季 8-K 2026-10-27（Q3）
    'sales_so_q': 436.0,  # Solar 收入/季 8-K 2026-10-27（Q3）
    'sales_ls_q': 290.0,  # LS&EGB 收入/季 8-K 2026-10-27（Q3）
    'g_gi': 1.25,  # 拆法：GI 相对最近一季 ×4 到 FY28 的桥因子（FY27 取 ^`bridge_frac_fy27`；A1） 2026-09-08
    'g_au': 1.2,  # 拆法：Automotive 桥因子（同上） 2026-09-08
    'g_so': 1.5,  # 拆法：Solar 收入桥因子（同上） 2026-09-08
    'g_ls': 1.1,  # 拆法：LS 收入桥因子（同上） 2026-09-08
    'bridge_frac_fy27': 0.5,  # FY27 取桥因子的半程幂（FY27 中点距运行率季约一年、FY28 两年；运行率换到 Q3 后照用，A1） 2026-10-04
    'g_so_l': 1.0,  # **L 档** Solar 收入因子：冻结在最近一季年化（A6） 2026-09-12
    'sales_so_fy28_guide': 3000.0,  # 太阳能 2028 年收入目标 $M（公司指引，只进候选带 H′；A29） 2026-07-28
    'unalloc_rde_q': 32.0,  # 总部未分摊研发税前/季；Q3 10-Q Note 14（A7/A18） 2026-09-30
    'net_interest_q': 49.0,  # 总部净利息税前/季；Q3 10-Q Note 14，分部利润未扣利息（A7） 2026-09-30
    'so_ls_ni_q': -35.0,  # Solar (−7) + LS&EGB (−28) 分部净利/季，三档持平 8-K 2026-10-27（Q3）
    'equity': 13671.0,  # 归母股东权益（ROE 滚动起点 BPS₀ 15.70，A31） 8-K 2026-10-27（2026-09-30 资产负债表）
    'eps_fy26_cons': 3.37425,  # FY2026 core EPS 共识均值，yfinance 0y，15 家（A31） 2026-11-05
    'eps_ytd26': 2.4,  # 9M core EPS 取 Q3 10-Q 累计实数，不再把单季取整数相加 2026-09-30
    'div_q_left': 1.0,  # FY26 尚未派发的季度股息个数（Q4；A31） 2026-09-30
    'r_perp': 0.1,  # 折现率 = **篮 4 常规经营**：OC / GI / AU 三腿同篮（盈利非商品价函数，无单客户 ≥50%；A30）；`check_r()` 强制 2026-09-20
    'g2_oc': 0.06,  # **同业反解**·OC 永续 g = min(同业中位 0.0635, 上限 0.06)（A25） 2026-09-11
    'g2_gi': 0.0,  # **无同业锚**·GI 永续 g（A4） 2026-09-14
    'g2_au': 0.0123,  # **同业反解（留存分支）**·Automotive 永续 g（A5） 2026-09-11
    'dps_annual': 1.12,  # 年度股息/股；只用于公司派息率 → `check_branch`（A5） 2026-06-30
    'core_eps_ann': 3.64,  # 当期年化 core EPS（Q3 0.91 × 4）；只作护栏分母与派息率分母 8-K 2026-10-27
    'pe_own_min': 19.7,  # 自身实测带下沿（A16 / A27；M 护栏） 2026-09-11
    'pe_own_max': 91.1,  # 自身实测带上沿（A27） 2026-09-11
    'ps_so': 1.0,  # Solar P/S（A6） 2026-09-12
    'ps_ls': 0.8,  # LS&EGB P/S（A6） 2026-09-12
    'corp_pretax_q': 32.0,  # 总部研发资本化输入，与 unalloc_rde_q 同源；摊销不再扣（A7） 2026-09-30
    'amort_q': 22.0,  # 收购无形资产摊销税前/季；核心口径已剔除，仅作敏感性 2026-09-30
    'tax_core': 0.185,  # Q3 core 有效税率；10-Q Core Performance Measures 调节表 2026-09-30
    'nci_q': 67.0,  # 核心口径少数股东利润/季，Q3 10-Q 调节表注 b；GAAP 为 66（A8） 2026-09-30
    'pe_corp': 15.0,  # 闭合项资本化倍数（A7） 2026-09-06
    'net_debt': 5663.0,  # 净债务 = 总债务 8,200（短期 933 + 长期 7,267）− 现金 2,537（A7） 8-K 2026-10-27（2026-09-30）
    'pension': 625.0,  # 养老金负债；Q3 10-Q Note 5 2026-09-30
    'contract_liab': 2701.0,  # 合同负债 501 流动 + 2200 非流动；无两张运营商新单导致的跳升（A22） 2026-09-30
    'pp_margin': 0.2236,  # 预付锁定利润率 = 最近一季（Q3'26）OC 净利率 532 ÷ 2,379（A17）；期权单位经济的下界披露 8-K 2026-10-27
    'sales_oc_q': 2379.0,  # OC 分部收入 Q3'26（A32） 8-K 2026-10-27
    'enterprise_growth_q': 0.84,  # Q3 企业网络收入同比增速；四舍五入披露，推断拆分用（A38） 2026-10-27
    'carrier_growth_q': 0.04,  # Q3 运营商收入同比；收入桥延续此增速只是条件假设（A38） 2026-10-27
    'enterprise_growth_single': 0.51,  # 伯恩斯坦 2026—2028 企业网络收入 CAGR 的媒体转述；从 Q3 年化连推两年是本框架偏强条件，不是原卖方模型（A38） 2026-10-29
    'phot_margin_reference': 0.2633,  # 上次光通信前瞻利润率推断，仅作光子学条件对照，不是新业务披露 2026-10-27
    'sales_oc_q_yago': 1652.0,  # OC 分部收入 Q3'25（同口径；A32） 8-K 2026-10-27
    'ni_oc_q_yago': 295.0,  # OC 分部净利 Q3'25（A32） 8-K 2026-10-27
    'sales_oc_q1': 2072.0,  # OC 分部收入上一季 Q2'26（环比对；A32） 10-Q 2026-06-30
    'ni_oc_q1': 438.0,  # OC 分部净利上一季 Q2'26（环比对；A32） 10-Q 2026-06-30
    'sales_oc_fy24': 4660.0,  # OC 分部收入 FY2024（旧口径；A32） 2025-01-28
    'ni_oc_fy24': 612.0,  # OC 分部净利 FY2024（A32） 2025-01-28
    'sales_oc_fy25': 6274.0,  # OC 分部收入 FY2025（A32） 2026-01-27
    'ni_oc_fy25': 1048.0,  # OC 分部净利 FY2025（A32） 2026-01-27
    'carrier_anchor': 3000.0,  # 运营商长约年速率的分子 = AT&T 公告额 >$30 亿（A23a / A33） 2026-09-29
    'carrier_unincluded': 0.0,  # 两张长约早于采用的财报后预测；无可证明的共识外增量，额外计值关闭（A23a/A33） 2026-11-05
    'carrier_years': 4.0,  # 年速率的分母 = AT&T 期限 2027–2030（`待核`；A33） 2026-09-29
    'contract_years': 6.0,  # Verizon 已公告期限 2027–2032（年金 n；续约折现年数，A23a/b） 2026-09-08
    't_opt': 2027.0,  # Verizon 交付起始年 = 锚点年（A23a） 2026-09-08
    'att_years': 4.0,  # AT&T 年金 n（2027–2030，`待核`；A33） 2026-09-29
    't_att': 2027.0,  # AT&T 交付起始年（`待核`；A33） 2026-09-29
    'meta_anchor': 6000.0,  # Meta 单 up to $6,000M：旧年速率锚，只作敏感性（A23a） 2026-01-27
    'meta_years': 4.0,  # Meta 单期限（through 2030）；只作敏感性 2026-01-27
    'phot_rev_target': 10000.0,  # 新 Photonics 2030 年末收入运行率机会；不是 FY2030 全年收入承诺（A34） 2026-05-06
    'phot_cons_included': 0.0,  # 条件成功情景假定共识外增量；无独立可复算分部预测，M 不计入（A34） 2026-11-05
    't_phot': 2031.0,  # 将 2030 年末运行率视为首个完整年收入的年份；不计未有预测的爬坡期利润 2026-11-05
    'phot_capex_unspent': 5295.292139554435,  # 初始资本需求推断 = 5039 ÷ 9516 × 10000；假定尚未投入、无复用，非公司预算；不再把未知默认为零（A34） 2026-11-05
    'seg_assets_oc': 5039.0,  # 光通信分部资产；Q3 10-Q Note 14，用于初始资本密度代理 2026-09-30
    'r_disc': 0.1,  # 期权年金与折回用的折现率 = 同 `r_perp`，不归篮（A26） 2026-09-20
    'ss_return': 0.1,  # **玻璃 / 汽车腿**的稳态回报 = 自身周期按序取：最近一轮谷到谷 2020–2023 投入资本口径均值 core 9.3% / GAAP 5.0%（取更严），低于 r → 取 r 10%（三档前瞻高于 r，非持续失败）；同业与兜底 15% 只作对照；各档 min(ROE, 本值)（A36）。光通信腿不用本值（叙事换代，见 `ss_cap_oc`） 2026-10-19
    'ss_cap_oc': 0.3,  # **光通信腿 = 叙事换代的腿**：稳态 = min(该档前瞻 ROE, 本值)，不回落；本值 = valuation-rules「经营价值与超额现金」② 叙事换代条的封顶（兜底表最高档）；两条判据见 A36 2026-10-18
    'ss_mgmt_lo': 0.23,  # 管理层「2030 年核心 ROIC 提升到十几个百分点的高段」换算到本票 ROE 口径的下沿；**只作敏感性，不取**（用户裁定 2026-10-18，A36） 2026-05-06
    'ss_mgmt_hi': 0.26,  # 同上上沿；只作敏感性 2026-05-06
    'y1_ga': 2028.0,  # 玻璃 / 汽车腿高回报期 Y1 = 默认「可见年末」FY2028（FY28 点估计年）；两腿不在光通信链上，不借光通信腿的 2030（用户 2026-10-18，A36） 2026-10-18
    'y2_ga': 2032.0,  # 玻璃 / 汽车腿 Y2 = Y1 + 4 年（中门槛默认回落年数）；Y1 → Y2 线性回落到 min(ROE, 10%)（A36） 2026-10-18
    'tau': 0.25,  # 时点对齐 τ = 最近资产负债表日 2026-09-30 → FY27 年初 2027-01-01；只折三条 Gordon 腿与期权（A37） 2026-10-27
}

def _lin(cal: int, y1: int, y2: int, a: float, b: float) -> float:
    """a through Y1, linear to b at Y2, b after (valuation-rules ② 稳态回报三段)."""
    if cal <= y1:
        return a
    if cal >= y2:
        return b
    return a + (b - a) * (cal - y1) / (y2 - y1)


def path_value(t0: int, y1: int, y2: int, r_s: float, g1: float, n: int, g2: float, roe: float, r: float,
               recovery: bool = False, floor: bool = True, narrative: float | None = None) -> float:
    """Multiple on next-period earnings: n transition years at g1 (payout 1 - g1/ROE floored at 0
    unless floor=False, or 1 in the recovery form), then g2 with the RONIC path; t = 1 <-> year t0.
    narrative = cap -> RONIC = min(ROE, cap) for ever (叙事换代的腿, A36); else three segments: ROE
    through Y1, linear to min(ROE, r_s) at Y2, Gordon tail after."""
    if r - g2 <= 0:
        raise ValueError(f"perpetuity diverges: g2={g2} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    for _ in range(int(n)):
        p1 = 1.0 if recovery else 1.0 - g1 / roe
        pv += e * (max(0.0, p1) if floor else p1) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    if narrative is not None:
        rn = min(roe, narrative)
        return pv + e * min(1.0, 1.0 - g2 / rn) / ((r - g2) * (1 + r) ** (t - 1))
    rs = min(roe, r_s)
    while True:
        cal = t0 + t - 1
        pay = min(1.0, 1.0 - g2 / _lin(cal, y1, y2, roe, rs))
        if cal > y1 and cal >= y2:
            return pv + e * pay / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * pay / (1 + r) ** t
        e *= 1 + g2
        t += 1



def calculate(context):
    ax = context['axes']['capex']
    inp = {**INPUTS, **{f'capex_{t}': ax['rungs'][t.upper()] for t in TIERS},
           'y1': ax['y1_ai_capex_package'], 'y2': ax['y2_ai_capex_package'],
           'ss_floor_ai_capex_package': ax['ss_floor_ai_capex_package']}
    if any(not math.isfinite(v) for v in inp.values()):
        raise ValueError('inputs must be finite')
    if inp['shares_diluted'] <= 0 or inp['equity'] <= 0 or inp['r_perp'] <= max(inp[f'g2_{leg}'] for leg in LEGS):
        raise ValueError('invalid base denominator or discount rate')
    if any(not float(inp[k]).is_integer() for k in ('y1', 'y2', 'y1_ga', 'y2_ga')) or inp['y1'] >= inp['y2'] or inp['y1_ga'] >= inp['y2_ga']:
        raise ValueError('invalid return path years')
    pts = {k[len('eps_fy28_pt_'):]: v for k, v in inp.items() if k.startswith('eps_fy28_pt_')}
    if not pts:
        raise ValueError('historical transition estimates unavailable')
    warnings = ['historical_optical_residual_and_photonics_capital_unverified']
    if len(pts) < 2:
        warnings.append('historical_transition_estimates_require_review')
    sh = inp["shares_diluted"] / MM
    tax = inp["tax_core"]
    r = inp["r_perp"]
    fr = inp["bridge_frac_fy27"]
    y1, y2, rs, tau = int(inp["y1"]), int(inp["y2"]), inp["ss_return"], inp["tau"]  # A36 / A37
    y1g, y2g = int(inp["y1_ga"]), int(inp["y2_ga"])  # GI / AU default window (A36)

    # ---- Step 1: leg split (existing rule) at FY27 and FY28 ----
    ni_gi = {27: inp["ni_gi_q"] * 4 * inp["g_gi"] ** fr, 28: inp["ni_gi_q"] * 4 * inp["g_gi"]}
    ni_au = {27: inp["ni_au_q"] * 4 * inp["g_au"] ** fr, 28: inp["ni_au_q"] * 4 * inp["g_au"]}
    sales_ls = inp["sales_ls_q"] * 4 * inp["g_ls"] ** fr
    s_so_m = inp["sales_so_q"] * 4 * inp["g_so"] ** fr
    sales_so = {"l": inp["sales_so_q"] * 4 * inp["g_so_l"], "m": s_so_m, "h": s_so_m}
    so_ls_ni = inp["so_ls_ni_q"] * 4
    close_core = (inp["unalloc_rde_q"] + inp["net_interest_q"]) * 4 * (1 - tax) + inp["nci_q"] * 4

    def oc_residual(eps: float, yr: int) -> float:
        return eps * sh + close_core - ni_gi[yr] - ni_au[yr] - so_ls_ni

    # L: own measured digestion year on the OC leg (A1).
    digest = inp["oc_ni_fy23"] / inp["oc_ni_fy22"]
    ni_oc = {
        "l": inp["ni_oc_q"] * 4 * digest,
        "m": oc_residual(inp["eps_fy27_m"], 27),
        "h": oc_residual(inp["eps_fy27_h"], 27),
    }
    eps = {
        "l": (ni_oc["l"] + ni_gi[27] + ni_au[27] + so_ls_ni - close_core) / sh,
        "m": inp["eps_fy27_m"],
        "h": inp["eps_fy27_h"],
    }
    if not (ni_oc['l'] < ni_oc['m'] < ni_oc['h']):
        warnings.append('historical_optical_numerator_order_requires_review')
    if not (sales_so['l'] <= sales_so['m'] <= sales_so['h']):
        warnings.append('historical_solar_order_requires_review')

    # FY28 transition (shared g1): point mean of verified houses.
    eps28 = sum(pts.values()) / len(pts)
    ni_oc28 = oc_residual(eps28, 28)
    g1 = {
        "oc": ni_oc28 / ni_oc["m"] - 1,
        "gi": ni_gi[28] / ni_gi[27] - 1,
        "au": ni_au[28] / ni_au[27] - 1,
    }

    # ---- Step 2: ROE on the FY27 opening book, rolled at the actual retention (A31) ----
    bps0 = inp["equity"] / sh
    unbooked = inp["eps_fy26_cons"] - inp["eps_ytd26"]
    bps_open = bps0 + unbooked - inp["dps_annual"] / 4 * inp["div_q_left"]  # user ruling 2026-10-18: actual retention over the rest of FY26
    ni_leg27 = {"oc": ni_oc, "gi": {k: ni_gi[27] for k in TIERS}, "au": {k: ni_au[27] for k in TIERS}}

    def g1_co(k: str, g1s: dict[str, float]) -> float:
        return sum(ni_leg27[leg][k] * g1s[leg] for leg in LEGS) / (eps[k] * sh)

    def roe_at(k: str, g1s: dict[str, float] | None = None, rolled: bool = False) -> float:
        """FY27 EPS / FY27 opening BPS.  rolled=True = the retired b1 = g/ROE issuance roll (disclosure)."""
        if not rolled:
            return eps[k] / bps_open
        x = g1_co(k, g1 if g1s is None else g1s) * unbooked / eps[k]
        if x >= 1.0:
            raise ValueError(f"opening-book roll diverges on {k}: g·N/EPS = {x:.3f}")
        return eps[k] / (bps0 / (1.0 - x))

    roe = {k: roe_at(k) for k in TIERS}
    gco = {k: g1_co(k, g1) for k in TIERS}
    b1 = {k: gco[k] / roe[k] for k in TIERS}
    cap_oc = inp["ss_cap_oc"]

    def leg_pe(leg: str, k: str, *, g2: float | None = None, g1s: dict[str, float] | None = None,
               rr: float | None = None, roe_k: float | None = None, trough: bool | None = None,
               floor: bool = True, oc_cap: float | None | bool = True) -> float:
        # L is the measured digestion year (谷底档, valuation-rules「周期票 regime / point」):
        # the step back up is utilisation, not retention, so stage 1 pays out 100% and
        # the tail carries the mid-cycle (M-tier) ROE — recovery_two_stage_pe.  The g1
        # value itself is the shared one (user ruling 2026-10-04).  OC = 叙事换代 (min(ROE, cap)
        # for ever); GI / AU = three segments (A36).  oc_cap=None -> OC back on three segments.
        g1s = g1 if g1s is None else g1s
        g2v = inp[f"g2_{leg}"] if g2 is None else g2
        rv = r if rr is None else rr
        rec = (k == "l") if trough is None else trough
        rk = (roe["m"] if rec else roe[k]) if roe_k is None else roe_k
        narr = (cap_oc if oc_cap is True else oc_cap) if leg == "oc" else None
        ya, yb = (y1, y2) if leg == "oc" else (y1g, y2g)
        # OC back on three segments (sensitivity only) lands on the _AXIS.ai-capex packaging-row
        # floor: own cycle unusable (business-model change), no same-business peer -> axis floor (A36).
        rsv = inp["ss_floor_ai_capex_package"] if leg == "oc" else rs
        return path_value(ANCHOR_YEAR, ya, yb, rsv, g1s[leg], N_STAGE, g2v, rk, rv, recovery=rec,
                          floor=floor, narrative=narr)  # A36

    pe = {leg: {k: leg_pe(leg, k) for k in TIERS} for leg in LEGS}
    if any(pe['oc'][k] >= PE_HARD_CAP for k in TIERS):
        warnings.append('historical_optical_multiple_guard_requires_review')
    if check_branch(inp['g2_au'], roe['m'], r, inp['dps_annual'] / inp['core_eps_ann'], 'g2_au'):
        warnings.append('historical_payout_guard_requires_review')

    # ---- Step 3: legs, closing items, prepaid, anchors ----
    corp_cap = inp["corp_pretax_q"] * 4 * (1 - tax) * inp["pe_corp"]
    nci_cap = inp["nci_q"] * 4 * inp["pe_corp"]
    adj = -corp_cap - nci_cap - inp["net_debt"] - inp["pension"]
    # Historical A17: Q3 10-Q contract liabilities times the observed optical
    # margin; the prepayment itself is not extra profit. Whether this amount
    # is independent of already valued earnings remains disputed; omitting it
    # lowers every anchor by about $0.69/share. Keep the inherited method until
    # that overlap is resolved, and do not add another option for the same order.
    pp_locked_ni = inp["contract_liab"] * inp["pp_margin"]

    def window(k: str, rd: float) -> float:
        """A37: unbooked rest-of-FY26 core EPS x (1 - b1), clipped at 0 (b1 > 1 = issuance-funded growth)."""
        return unbooked * max(0.0, 1.0 - b1[k]) * (1.0 + rd) ** (-tau / 2)

    def anchor(k: str, *, pe_k: dict[str, float] | None = None, sales_so_k: float | None = None,
               ni_oc_k: float | None = None, rd: float | None = None) -> tuple[dict[str, float], float]:
        pk = {leg: pe[leg][k] for leg in LEGS} if pe_k is None else pe_k
        rd = r if rd is None else rd
        df = (1.0 + rd) ** (-tau)  # A37: only the Gordon legs are FY27-opening values
        lg = {
            "oc": (ni_oc[k] if ni_oc_k is None else ni_oc_k) * pk["oc"] * df,
            "gi": ni_gi[27] * pk["gi"] * df,
            "au": ni_au[27] * pk["au"] * df,
            "so": (sales_so[k] if sales_so_k is None else sales_so_k) * inp["ps_so"],
            "ls": sales_ls * inp["ps_ls"],
            "pp": pp_locked_ni,
        }
        return lg, (sum(lg.values()) + adj) / sh + window(k, rd)

    legs_l, L = anchor("l")
    legs_m, M = anchor("m")
    legs_h, H = anchor("h")
    A, B = (L + M) / 2, (M + H) / 2
    base = {"l": L, "m": M, "h": H}


    if not all(math.isfinite(v) for v in (L, M, H)) or not L < M < H:
        raise ValueError('base anchors must be finite and ordered')
    def band(values):
        return dict(zip('LMH', values))
    details = {'l': legs_l, 'm': legs_m, 'h': legs_h}
    result = {'ticker': 'GLW.US', 'currency': 'USD', 'units': {'price': 'USD_PER_SHARE'},
              'valuation_as_of': None, 'framework_as_of': None,
              'historical_financial_statement_as_of': '2026-09-30', 'historical_research_as_of': '2026-11-05',
              'anchors': band((L, M, H)), 'cut_points': {'A': A, 'B': B},
              'candidate': None, 'review_flags': warnings,
              'segments': {leg: {'unit': 'USD_PER_SHARE', 'values': band(details[t][leg] / sh for t in TIERS)}
                           for leg in ('oc', 'gi', 'au', 'so', 'ls', 'pp')},
              'key_parameters': {leg: {
                  'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', r)},
                  'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', inp[f'g2_{leg}'])},
                  'forward_return': {'unit': 'RATIO', 'values': band(roe[t] for t in TIERS)},
                  'steady_return': {'unit': 'RATIO', 'values': band(min(roe[t], cap_oc if leg == 'oc' else rs) for t in TIERS)}}
                  for leg in LEGS},
              'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                  {'inputs': inp, 'option_weights': {'signed': P_SIGNED, 'renew': P_RENEW, 'photonics': P_PHOT},
                   'anchor_year': ANCHOR_YEAR, 'stage': N_STAGE}, BASELINE_LOCAL)}
    result['segments']['adjustments'] = {'unit': 'USD_PER_SHARE', 'values': band(adj / sh for t in TIERS)}
    result['segments']['window'] = {'unit': 'USD_PER_SHARE', 'values': band(window(t, r) for t in TIERS)}
    try:
        guide = inp['sales_so_q'] * 4 * (inp['sales_so_fy28_guide'] / (inp['sales_so_q'] * 4)) ** fr
        if guide <= sales_so['h']:
            raise ValueError('solar guide does not add a candidate')
        _, candidate_h = anchor('h', sales_so_k=guide)
        if not math.isfinite(candidate_h) or not M < candidate_h:
            raise ValueError('invalid candidate')
        result['candidate'] = {'label': '太阳能指引', 'anchors': band((L, M, candidate_h))}
    except (ArithmeticError, ValueError, TypeError):
        warnings.append('historical_solar_candidate_unavailable')

    def calculate_option():
        errors = []
        # ---- Options (after anchors; cannot reach L/M/H) ----
        r_disc = inp["r_disc"]

        def fy28_oc_margin(d_ni: float, d_sales: float) -> tuple[float, float]:
            inc = d_ni / d_sales
            rev28 = inp["sales_oc_q"] * 4 + (ni_oc28 - inp["ni_oc_q"] * 4) / inc
            return inc, ni_oc28 / rev28

        pairs = {
            "latest qtr YoY": (inp["ni_oc_q"] - inp["ni_oc_q_yago"], inp["sales_oc_q"] - inp["sales_oc_q_yago"]),
            "FY24->FY25": (inp["ni_oc_fy25"] - inp["ni_oc_fy24"], inp["sales_oc_fy25"] - inp["sales_oc_fy24"]),
            "latest qtr QoQ": (inp["ni_oc_q"] - inp["ni_oc_q1"], inp["sales_oc_q"] - inp["sales_oc_q1"]),
        }
        margins = {'latest qtr YoY': fy28_oc_margin(*pairs['latest qtr YoY'])}
        _, opt_margin = margins["latest qtr YoY"]
        if not (inp["pp_margin"] < opt_margin < 1):
            errors.append(f"aligned-year OC margin {opt_margin:.4f} not above the latest-quarter print (A32)")

        carrier_rate = inp["carrier_anchor"] / inp["carrier_years"]

        def lta(rate: float, n: float, t0: float, margin: float, rr: float) -> tuple[float, float]:
            signed = rate * margin * annuity_factor(0.0, rr, n) * (1.0 + rr) ** (ANCHOR_YEAR - t0) / sh
            return signed, signed / (1.0 + rr) ** n

        vz_s, vz_r = lta(carrier_rate, inp["contract_years"], inp["t_opt"], opt_margin, r_disc)
        att_s, att_r = lta(carrier_rate, inp["att_years"], inp["t_att"], opt_margin, r_disc)
        # 12y / 8y annuity identities (split is structure, not value).
        for name, (s_, r_), n in (("Verizon", (vz_s, vz_r), inp["contract_years"]), ("AT&T", (att_s, att_r), inp["att_years"])):
            whole = carrier_rate * opt_margin * annuity_factor(0.0, r_disc, 2 * n) * (1 + r_disc) ** (ANCHOR_YEAR - inp["t_opt"]) / sh
            if abs(s_ + r_ - whole) > 1e-9:
                errors.append(f"{name} segments do not sum to the {2 * n:.0f}y annuity")

        # Photonics (A34): first full revenue year at t_phot, valued back to FY27.
        phot_units = inp["phot_rev_target"] - inp["phot_cons_included"]
        phot_ni = phot_units * opt_margin
        # Success world uses the OC ruler: RONIC = min(ROE_M, cap) for ever.
        phot_pe = path_value(int(inp["t_phot"]), y1, y2, rs, 0.0, 0, inp["g2_oc"], roe["m"], r, narrative=cap_oc)
        disc_phot = (1.0 + r) ** -(inp["t_phot"] - ANCHOR_YEAR)
        capex_unspent = inp["phot_capex_unspent"]
        v_phot = (phot_ni * phot_pe - capex_unspent) * disc_phot / sh

        # All option parts are FY27-opening values: one more tau to today (A37).
        df_opt = (1.0 + r_disc) ** (-tau)
        carrier_credit = inp["carrier_unincluded"]
        v_parts = {"vz_s": vz_s * carrier_credit, "vz_r": vz_r * carrier_credit,
                   "att_s": att_s * carrier_credit, "att_r": att_r * carrier_credit, "phot": v_phot}
        v_parts = {k: v * df_opt for k, v in v_parts.items()}
        vz_s, vz_r, att_s, att_r, v_phot = (v_parts[k] for k in ("vz_s", "vz_r", "att_s", "att_r", "phot"))
        v_opt = sum(v_parts.values())

        def opt_k(k: str) -> float:
            return (P_SIGNED[k] * (vz_s + att_s) + P_RENEW[k] * (vz_r + att_r) + P_PHOT[k] * v_phot)

        zone_v = {k: base[k] + opt_k(k) for k in TIERS}
        p_eff = {k: opt_k(k) / v_opt for k in TIERS}

        if not math.isfinite(v_opt) or v_opt <= 0 or any(not math.isfinite(v) or v < 0 for v in p_eff.values()):
            raise ValueError('option unavailable')
        if not zone_v['l'] < zone_v['m'] < zone_v['h']:
            raise ValueError('option band unavailable')
        if errors:
            warnings.append('historical_option_guards_require_review')
        return {'label': '机箱内光子学', 'value': v_opt, 'value_unit': 'USD_PER_SHARE',
                'weights': {t.upper(): p_eff[t] for t in TIERS}, 'anchors': {t.upper(): zone_v[t] for t in TIERS}}

    try:
        result['option'] = calculate_option()
    except (ArithmeticError, ValueError, TypeError):
        result['option'] = {'status': 'unavailable', 'label': '机箱内光子学', 'anchors': None}
        warnings.append('historical_photonics_option_unavailable')
    return result
