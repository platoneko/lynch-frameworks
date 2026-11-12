#!/usr/bin/env python3
"""Alphabet Q3 2026 segment valuation; inputs USD millions, output USD/share."""
import math
from lib.gordon import check_basket_pair, check_g_cap, check_k_declared, check_r, payout, perpetual_pe
from lib.inputs import ladder, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES={'libraries':('gordon','inputs','partial_basis','rf_report'),
              'axes':{'lab':'frontier_lab_funding','capex':'ai_capex'}}
HISTORICAL_PARTIAL_FINGERPRINT='442f003ed83d7609e18edce61654ea5a366fdfae49f8665b48d2564999d5bb1e'
ANNUALIZE=4
# Q3 2026 actuals and capex guidance: 2026-10-28 release. Quarterly
# consensus EBIT is Longbridge 2026-09-04; Q4 EBIT estimate 48,129m is the
# 2026-10-29 Longbridge consensus. 1.29 is the original three-year OCF / NI
# proxy, not management guidance. One-off charges remain zero because no Q3
# charge was disclosed; the 10-Q may revise that judgment. Q3 group invested
# capital has not been split: Services still uses its 2026-06-30 estimate.
# Unlisted securities, deferred tax and Waymo ownership retain their earlier
# dates. The SpaceX listed stake under non-current assets is included exactly
# once, separately from cash securities and non-market equity. Future Q4 gap
# is projected capex less projected OCF excluding SBC, not a confirmed outflow.
INPUTS={
    'r_perp': 0.1,  # Services 腿与 Cloud 非实验室子腿的永续折现率 = **篮 4 龙头制造** 10%（A24）；值 = `gordon.BASKET_R`，来源单元格篮号与值须一致（`check_r`）；零增长 → PE 10×; as-of 2026-09-20
    'r_cld_lab': 0.15,  # Cloud 实验室子腿（Anthropic 收入）**过渡篮** = **篮 7 单押 / 国别 / 故事** 15%（今天收入依赖对手方未落定融资；A27，与 `ORCL.US` A7 / `AMZN.US` A6 / `MSFT.US` A6 同一条理由）；本腿单段 Gordon，过渡篮无算术作用点，只记录今天的性质、定 \(G_{cap}\)、作合篮回退目标; as-of 2026-09-23
    'r_cld_lab_t': 0.1,  # Cloud 实验室子腿**终值篮** = **篮 4 龙头制造** 10%：Anthropic 做成了的世界里是用自身收入付账的超大客户，与其余 Cloud 客户同类（`_AXIS.frontier-lab-funding` §3）；稳态按此资本化；A27; as-of 2026-09-23
    'roic_marg_cld': 0.16,  # **Cloud 新投资本的边际稳态 ROIC**（A26）= 汇丰 2027E Google Cloud ROIC；进两条 Cloud 子腿的留存项 b = g/ROIC，L 档随 A18 退坡同比例缩；快照 ROE（`equity_cloud` 行）只披露; as-of Wisburg 99586
    'share_lab_cld': 0.3,  # Anthropic 占 FY2027E Cloud 收入 / 利润的份额 `估算`（A27）：RPO 份额约 50%（汇丰）× backlog 5,139 亿 ÷ 加权剩余期（未披露，按 5 年）≈ 每年 514 亿 vs FY2027E Cloud 收入约 1,500 亿 → 34%，取 30%；15% / 50% 敏感行; as-of 2026-09-22
    'shares_diluted': 12368.0,  # 稀释加权股数（百万）：Q3 2026 稀释加权 12,368（Q2 12,306）；Q3 用 ATM 增发 $124 亿（A 类 43 + C 类 81），剩余额度 $276 亿；未建模 SBC / 优先股转股与后续 ATM 的未来稀释（A10）; as-of 8-K 2026-10-28
    'tax_rate': 0.17,  # 正常化税率；2025 同期实际 16.9%(Q2)/17.1%(H1)。**不用** H1'26 的 19.1%（含未实现权益收益的递延税，A3）; as-of 10-Q 2026-06-30
    'oi_services_q3': 39157.0,  # Google Services Q3 2026 分部经营利润（$M）；margin 40.7%（Q2 41.8%、去年同期 38.5%）；收入 96,302（+10.6%），其中 Search & other 63,350（+12.0%，Q2 +17%）; as-of 8-K Ex-99.1 2026-10-28
    'oi_cloud_q3': 11121.0,  # Google Cloud Q3 2026 分部经营利润（$M）；收入 30,709（+103%）、margin 36.2%（去年同期 23.7%）；**已含分摊技术基础设施折旧**（A5/属性 B）; as-of 8-K Ex-99.1 2026-10-28
    'oi_corp_q3': -7655.0,  # Alphabet-level activities Q3 2026（$M）：通用 AI 模型共享研发 + 公司共享成本 + 罚金和解（Q2 −5,789、去年同期 −4,467）；新闻稿未列一次性项，**待 10-Q 核**（A4）; as-of 8-K Ex-99.1 2026-10-28
    'corp_oneoff_q3': 0.0,  # 从上行加回的一次性（$M）：Q3 新闻稿未披露任何判赔 / 罚金一次性计提，记 0（Q2 的 PriceRunner 本金 1,500 已不在窗口内）；欧盟 Android 罚款 $52 亿本季为**现金支付**、此前已计提，不进分部利润；待 10-Q Note 10 核（A4）; as-of 8-K Ex-99.1 2026-10-28
    'oi_other_bets_q3': -2047.0,  # Other Bets Q3 2026（$M）；**不进盈利腿**，仅用于 eval 的合并 EBIT 对账与 A15 的"不回加亏损"校验; as-of 8-K Ex-99.1 2026-10-28
    'ebit_q3e_consensus': 42540.0,  # 财报前 Q3 2026 合并 EBIT 共识（$M，Longbridge consensus 2026-09-04，与 `ebit_fy26e_consensus` 原值同一份）；实际 40,576 → 落差 **−4.6%**，进 `k_eps_m` 的下修（A2）; as-of Longbridge 2026-09-04
    'ebit_fy27e_3leg': 223249.0,  # 财报前 FY2027E 三腿 EBIT（$M）= 2026-09 桥 1.300 × 当期年化三腿 171,730（H1 2026 ×2）≈ 2,240 亿（A2）；eval 强制 `k_eps_m` = 本值 × (Q3 实际 ÷ Q3E) ÷ 当期年化三腿; as-of §0 桥 2026-09-05
    'equity_services': 247800.0,  # **Services + Alphabet-level 腿的经营投入资本 IC0（$M，2026-06-30 值沿用；9-30 集团投入资本待 10-Q，2026-10-29 未重切；Q3 口径 M 档 ROE 52.1%，见 §3 第 15 条）**；残差法 = 集团 **407,800** − 云腿 160,000。**ROE 分母不是它本身，是它滚到 FY2027 年初的值**（A25）：IC_open = IC0 ÷ (1 − g·N/E)，N = 未入账的 2H26 年化 NOPAT 58,476；M 档 ROE = 152,038 / 253,046 = **60.1%**（旧口径 当期年化 116,952 / 247,800 = 47.2% 留作记录）。**⚠ 滚动只留 b1 = g/ROE，capex 潮实际留存远大于此（A23）**：真实 FY2027 年初资本更大、倍数偏高，敏感带 +20%/+40% 见 Outputs。**待补**：Meta 广告腿对照仅 **34–38%**（10-K 明文不披露分部资产，该数为估算），本票 47.2% 高出约 **10pp**，差距需持续复核; as-of 2026-09-09
    'payout_3y': 0.05,  # 近 3 年现金派息率均值（FY23 0% / FY24 7.4% = 7,363 ÷ 100,118 / FY25 7.6% = 10,049 ÷ 132,170；回购视为留存现金用途）；只进「模型视同派出、实际留存的现金」披露行（A25），不进公式; as-of yfinance 2026-09-21
    'eps_fy27e_low': 13.5,  # FY2027E 稀释 EPS 共识**低端**（51 家）；与 `k_eps_l` 做一致性校验，本身不入公式; as-of yfinance 2026-09-05
    'eps_fy27e_high': 17.21,  # FY2027E 稀释 EPS 共识**高端**（51 家）；与 `k_eps_h` 做一致性校验，本身不入公式; as-of yfinance 2026-09-05
    'g2_svc': 0.06,  # **Services 腿永续增速，三档共用**（倍数 M 档 **21.43×**，三档 21.39 / 21.43 / 21.49× 随 ROE 与回报路径微动，A25 / A30）。**来源层级：同业横截面反解（n=3，剔除自身）**——同尺（Gordon、r=10%）、FY+2 共识 EPS、投入资本单位的**市价**反解；2026-10-16 按 valuation-rules「经营价值与超额现金」② 配对条与 ③ 时点对齐重解（模型侧 = 今天的经营价值：FY+2 年初的回报路径 Gordon 值折 τ 0.5 年 + 窗口利润；各成员稳态回报取平台兜底 30%；观察倍数不重读价格）：**META 6.28% / RDDT 6.36% / TTD 4.04%** → 中位 **6.28%** → 截到 cap **6%**（2026-10-19 各成员稳态改按新序——自身历史 / 兜底——重解，META、TTD 前瞻低于各自稳态、路径平，中位不变，A21）（旧尺 2026-09-18 读数 META 6.14% / RDDT 5.51% / TTD 3.94%，中位 5.51%；广告平台簇共享横截面表；A21；PINS 病态区、SNAP 亏损剔除；只引市价、不引 META 框架值，防互引循环）；A11 的救济拖累仍未在 \(g_{svc}\) 里显性体现，是本框架现存最弱的一环。≤ cap = min(6%, r − 4%) = 6%（篮 4，A24）✓；\(r-g = 4.0\% \ge 2\%\) ✓；**敏感区**：−1pp → L/M/H 210.13 / 260.01 / 304.53（§3 敏感性）; as-of 2026-10-16
    'g2_cld': 0.06,  # **Cloud 腿永续增速，三档共用**。**来源层级：同业横截面反解 → 截到上限**——同一横截面（汇丰隐含 2028E EV/EBIT 经本仓 Gordon 单位反解，A7/A20）给 AWS +7.26% / Azure +7.02% / Google Cloud 自身 +3.97%；6.0% = 仓库永续上限（AGENTS.md「永续增长口径」），低于 AWS/Azure、高于 GCP 自身反解（残差法，A7 缺维，作对照不作锚）。原值 6.5%（2026-09-13 截断）的反解出处本文未写明，`待补`（截顶后原值不影响锚：AWS / Azure 反解均 > 6%）。定性支撑：backlog **$5,139 亿覆盖 3.4 年 NTM 收入**（汇丰，A7/A12）。倍数与 L 档退坡值见 Outputs。\(r-g = 4.0\%\) ✓；cap = min(6%, r − 4%) = 6%（篮 4，A24）即上限本身; as-of 2026-09-13
    'pe_own_top': 32.88,  # 自身 5 年 trailing PE **实测顶**（2026-02；Longbridge 60 点月度序列）。**护栏，不入主公式**：`H / trailing 核心 EPS` 越出即红、回对话（AGENTS.md:74 / A6）。现 **30.77× ≤ 32.88×** ✓; as-of Longbridge 2026-09-08
    'pe_own_p50': 24.09,  # 同一序列实测中位；**护栏 / 交叉校验**，不入主公式。日线独立复算中位 25.18（n=1255）互证; as-of Longbridge 2026-09-08
    'cash_and_securities': 265098.0,  # 现金及现金等价物 + 有价证券（$M；新闻稿合计口径，分项待 10-Q）; as-of 8-K 2026-09-30
    'mkt_equity_sec': 90400.0,  # 上述有价证券中的**上市权益证券**（$M；电话会 CFO：$904 亿，含 SpaceX）；从闭合项剔出、改入资产腿，避免与债券类现金混计; as-of 电话会 2026-10-28
    'nonmkt_sec': 131461.0,  # 非上市证券（$M，**2026-06-30 值**；Q3 权益证券净亏损 $86.6 亿的分项与 9-30 余额待 10-Q）；非权益部分占比未披露（A14）。**不含** SpaceX 的 14,126——那笔在另一条线上（见下行）; as-of 10-Q 2026-06-30
    'other_mkt_equity_sec': 14126.0,  # Other non-current assets 项下的**上市**权益证券（$M）= 限售至 2027Q3 的 SpaceX 股份。它既不在 `cash_and_securities`（那是流动项）也不在 `nonmkt_sec`（10-Q Note 3 把它列为 Level 1），旧版把它误当作 `nonmkt_sec` 的一部分描述，结果**任何一条腿都没算它**（A14）; as-of 10-Q Note 3 脚注(2)
    'lt_debt': 125102.0,  # 长期债务（$M）；2026-06-30 为 98,165，Q3 发行优先无担保票据净额 $287 亿; as-of 8-K 2026-09-30
    'pref_liq': 19000.0,  # 6.25% 强制可转优先股清偿优先额（$M）= 19,000 股 × $1,000；按负债扣除、不另计股数稀释（A10）; as-of 10-Q Note 11
    'dtl_noncurrent': 22819.0,  # 非流动递延所得税负债（$M）；2025-12-31 仅 919，增量主要对应未实现权益收益的法定税（A3/A14）; as-of 10-Q 2026-06-30
    'd_port_l': 0.4,  # 证券组合 L 档折价：SpaceX 限售 + 单一标的集中 + 私募标记回撤（A14）; as-of 2026-09-06
    'd_port_m': 0.25,  # 中档折价；约 40% 组合已是 Level-1 可交易; as-of 2026-09-06
    'd_port_h': 0.1,  # 上档折价；仅留残余流动性折价; as-of 2026-09-06
    'waymo_post_money': 126000.0,  # Waymo 2026-02 轮 post-money 估值（$M），$16B 融资，Alphabet 出资超 3/4 且为最大股东; as-of 2026-02-02
    'waymo_stake': 0.7,  # Alphabet 对 Waymo 的归属比例（**待核**；60%–80% 区间对 M/H 的影响 ≤0.7，A15）; as-of 2026-02-02
    'd_ob_l': 1.0,  # Other Bets L 档折价 100%：期权价值被非 Waymo 部分的持续烧钱与私募标记的自成交属性抵消; as-of 2026-09-06
    'd_ob_m': 0.6,  # 中档：计入私募标记的 40%; as-of 2026-09-06
    'd_ob_h': 0.3,  # 上档：计入 70%，仍留 30% 私募/流动性折价; as-of 2026-09-06
    'capex_9m': 131953.0,  # 2026 前九个月购置不动产及设备（$M；Q3 单季 51,355）；2026 全年指引 195,000–205,000 不变，2027「显著增加」; as-of 8-K 2026-10-28
    'dep_9m': 21955.0,  # 2026 前九个月不动产及设备折旧（$M；Q3 单季 8,369，年化约 335 亿）；capex/折旧 ≈ 6.0×，即 A5 的折旧滞后倍数; as-of 8-K 2026-10-28
    'ebit_fy26e_consensus': 169171.0,  # FY2026E 合并 EBIT（$M）= Q1 实际 39,696 + Q2 实际 40,770 + Q3 实际 40,576 + Q4E 48,129；用于 eval 对账**当期年化基座**（\(k_{eps}\) 乘上去的那个底）是否偏离 >10% 而失效; as-of Longbridge consensus 2026-10-29
    'capex_guide_low': 195000000000.0,  # 2026 全年 capex 指引下沿 USD；`_AXIS.ai-capex.md` **构成方**校验用（A19）; as-of 10-Q 2026-06-30
    'capex_guide_high': 205000000000.0,  # 2026 全年 capex 指引上沿 USD；同上; as-of 10-Q 2026-06-30
    'cloud_om_l': 0.237,  # **L 档**云腿分部 OI margin = **去年同期实测值**（Q3 2025：3,594 / 15,157）；A18。公司不给 EPS 指引，但已实现的分部利润率是**证据不是预测**（skill A2e-2c）; as-of 8-K 2026-10-28
    'cloud_om_now': 0.362,  # 当期云腿分部 OI margin（Q3 2026：11,121 / 30,709）；A18 的分母; as-of 8-K 2026-10-28
    'eps_fy27e_consensus': 14.83,  # FY2027E 稀释 EPS 共识**均值**（51 家；区间 13.50–17.21）；`k_eps_*` 一致性校验的分母，并用于隐含前瞻 PE; as-of yfinance 2026-09-05
    'tau': 0.25,  # 时点对齐：估值基准日 2026-09-30（Q3 资产负债表日）→ 分子年 FY2027 年初 2027-01-01 的年数；Services 与 Cloud 非实验室子腿按 `r_perp` 折、Anthropic 子腿按过渡篮 `r_cld_lab` 折；ROE 年初资本滚动的未入账窗口同为 τ（Q4 2026）（A29）; as-of 2026-09-30
    't0': 2027,  # 回报路径第 1 年 = 分子年 FY2027（A30）; as-of 2026-10-16
    'y1': 2027,  # 高回报期止点 = 可见年末（默认路径，云厂商不继承 `_AXIS.ai-capex`；A30）; as-of 2026-10-16
    'y2': 2033,  # 稳态起点 = 可见年末 + 6（Services 进入门槛「高」；A30）; as-of 2026-10-16
    'ronic_ss_svc': 0.402,  # Services 腿稳态回报 = **自身历史（投入资本口径）**：FY2018–FY2025 八年（分部重述起点；非周期票，无谷到谷）Services + Alphabet-level 税后经营利润（税率 17%）÷ 集团年初投入资本（权益 + 有息负债 + 租赁 − 超出 10% 收入经营现金锚的现金类资产；Cloud、Other Bets 与非上市证券的资本全算在本腿身上，取最严读法）均值 **40.2%**；同业层空（广告同业近 5 年收入复合增速都 > 10%）、兜底 30% 只作对照；每档不超过该档前瞻（A30）; as-of 2026-10-19
    'sbc_q4': 7300.0,  # 2026 Q4 股权激励（$M，年化约 294 亿的四分之一；经营现金流里的非现金加回，不是可用现金）（A29）; as-of 2026-06-30
    'ebit_q4_cons': 48129.,  # Longbridge 2026-10-29 Q4 EBIT estimate
    'ocf_income_multiple': 1.29,  # historical three-year OCF / NI proxy
}

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on next-period earnings with the three-stage return path
    (valuation-rules「经营价值与超额现金」② 稳态回报三段).

    Year t = 1 is calendar t0.  The retention of calendar c earns the forward return
    while c <= y1, fades linearly to the stable return by y2, and the stable return
    from y2 on.  Stable return capped at the forward return and floored at r; a flat
    path equals `perpetual_pe`.
    """
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    rs = min(roe, max(rs, r))

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
            return pv + e * payout(g, rs) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1

# V_opt is a parallel dimension, never part of L/M/H.  It only splits the region
# above H into "the market is paying for a named option" and "beyond every
# option we can name".  Its share of M is a disclosure, never a failure
# (skill A2e-7e): past this share the ticker is 期权主导型 and §0 must say so,
# but the eval only reports it.
OPTION_DOMINANT_SHARE = 1.00



def derived_inputs(inp):
    keep=1-inp['tax_rate']
    quarter_total=inp['oi_services_q3']+inp['oi_cloud_q3']+inp['oi_corp_q3']+inp['oi_other_bets_q3']
    annual_legs=(inp['oi_services_q3']+inp['oi_cloud_q3']+inp['oi_corp_q3']+inp['corp_oneoff_q3'])*ANNUALIZE
    scale=inp['ebit_fy27e_3leg']*(quarter_total/inp['ebit_q3e_consensus'])/annual_legs
    low=scale*inp['eps_fy27e_low']/inp['eps_fy27e_consensus']
    high=scale*inp['eps_fy27e_high']/inp['eps_fy27e_consensus']
    return {'equity_cloud':round(inp['oi_cloud_q3']*ANNUALIZE*keep/inp['roic_marg_cld']),
            'k_eps_l':round(low,5),'k_eps_m':round(scale,5),'k_eps_h':round(high,5),
            'capex_q4':round((inp['capex_guide_low']+inp['capex_guide_high'])/2/1e6-inp['capex_9m'],-3),
            'ocf_q4':round(inp['ebit_q4_cons']*keep*inp['ocf_income_multiple'],-2)}


def evaluate(inp,rate_inputs=None):
    inp={**inp,**derived_inputs(inp)}
    require_whole_years(inp,('t0','y1','y2'))
    if not inp['t0']<=inp['y1']<inp['y2']:
        raise ValueError('return-path years invalid')
    r=inp['r_perp']; rj=inp['r_cld_lab']; rt=inp['r_cld_lab_t']; k=inp['k_lab']
    errors=check_r(r,'r_perp',4)+check_basket_pair(rj,rt,'lab',7,4)+check_k_declared(rj,rt,(k,)*3,'lab')
    errors+=check_g_cap(inp['g2_svc'],r,'g2_svc')+check_g_cap(inp['g2_cld'],r,'g2_cld')
    if errors:
        raise ValueError('; '.join(errors))
    sh=inp['shares_diluted']; keep=1-inp['tax_rate']; tau=inp['tau']
    svc=(inp['oi_services_q3']+inp['oi_corp_q3']+inp['corp_oneoff_q3'])*ANNUALIZE*keep
    cloud=inp['oi_cloud_q3']*ANNUALIZE*keep
    if min(sh,svc,cloud,inp['equity_services'],inp['equity_cloud'])<=0:
        raise ValueError('business income, capital and shares must be positive')
    cash=inp['cash_and_securities']-inp['mkt_equity_sec']-inp['lt_debt']-inp['pref_liq']
    portfolio=inp['mkt_equity_sec']+inp['other_mkt_equity_sec']+inp['nonmkt_sec']-inp['dtl_noncurrent']
    waymo=inp['waymo_post_money']*inp['waymo_stake']
    gap=max(inp['capex_q4']-(inp['ocf_q4']-inp['sbc_q4']),0)/sh
    cloud_retreat=inp['cloud_om_l']/inp['cloud_om_now']
    def opened_return(earnings,capital,growth,unbooked):
        roll=growth*unbooked/earnings
        if roll>=1:
            raise ValueError('opening capital roll diverges')
        return earnings/(capital/(1-roll))
    def at_rates(ro,rj_,rt_):
        contributions={}; params={}
        for t in 'lmh':
            scale=cloud_retreat if t=='l' else 1.
            size=inp[f'k_eps_{t}']
            rs=opened_return(svc*size,inp['equity_services'],inp['g2_svc'],svc*tau)
            rc=opened_return(cloud*scale*size,inp['equity_cloud'],inp['g2_cld'],cloud*tau)
            marginal=inp['roic_marg_cld']*scale
            ps=path_pe(inp['g2_svc'],rs,ro,inp['t0'],inp['y1'],inp['y2'],inp['ronic_ss_svc'])
            pc=perpetual_pe(inp['g2_cld'],marginal,ro)
            pl=perpetual_pe(inp['g2_cld'],marginal,rt_)
            lab=inp['share_lab_cld']
            parts={'services':svc*size*ps/sh/(1+ro)**tau,
                   'cloud':cloud*scale*size*(1-lab)*pc/sh/(1+ro)**tau,
                   'lab':cloud*scale*size*lab*pl*(1-k)/sh/(1+rj_)**tau,
                   'cash':cash/sh,'portfolio':portfolio*(1-inp[f'd_port_{t}'])/sh,
                   'waymo':waymo*(1-inp[f'd_ob_{t}'])/sh,'funding_gap':-gap}
            contributions[t]=parts
            params[t]={'services_forward_return':rs,'cloud_forward_return':rc,
                       'cloud_marginal_return':marginal,'services_multiple':ps,
                       'cloud_multiple':pc,'lab_multiple':pl}
        return contributions,params
    parts,params=at_rates(r,rj,rt)
    anchors={t.upper():sum(parts[t].values()) for t in 'lmh'}
    errors=ladder('anchors',*(anchors[t] for t in 'LMH'))
    if errors:
        raise ValueError('; '.join(errors))
    flags=['historical_partial_capital_split_unverified','historical_q4_funding_forecast',
           'historical_waymo_ownership_unverified','historical_nonmarket_security_and_tax_dates_mixed',
           'historical_single_source_cloud_marginal_return']
    if gap==0:
        flags.append('unbooked_window_release_not_modelled_when_no_gap')
    if anchors['H']/((svc+cloud)/sh)>inp['pe_own_top']:
        flags.append('historical_multiple_outside_band')
    result={'ticker':'GOOG.US','currency':'USD','valuation_as_of':None,'framework_as_of':None,
        'historical_valuation_as_of':'2026-09-30','historical_framework_as_of':'2026-11-07',
        'basis_changed':None,'anchors':anchors,'candidate':None,'option':None,'review_flags':flags,
        'units':{'price':'USD_PER_SHARE'},
        'segments':{name:{'unit':'USD_PER_SHARE','values':{t.upper():parts[t][name] for t in 'lmh'}}
                    for name in ('services','cloud','lab','cash','portfolio','waymo','funding_gap')},
        'key_parameters':{
            'discount_rate':{'services':r,'cloud':r,'lab_transition':rj,'lab_terminal':rt},
            'growth_rate':{'services':inp['g2_svc'],'cloud':inp['g2_cld']},
            'services_forward_return':{t.upper():params[t]['services_forward_return'] for t in 'lmh'},
            'services_steady_return':{t.upper():min(params[t]['services_forward_return'],max(inp['ronic_ss_svc'],r)) for t in 'lmh'},
            'cloud_marginal_return':{t.upper():params[t]['cloud_marginal_return'] for t in 'lmh'},
            'cloud_forward_return_reference':{t.upper():params[t]['cloud_forward_return'] for t in 'lmh'}},
        'derived':{key:inp[key] for key in ('equity_cloud','k_eps_l','k_eps_m','k_eps_h','capex_q4','ocf_q4')}}
    if rate_inputs is not None:
        def band_at(dr):
            shifted,_=at_rates(r+dr,rj+dr,rt+dr)
            return tuple(sum(shifted[t].values()) for t in 'lmh')
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',
            priced_r={'r_perp':r,'r_cld_lab':rj,'r_cld_lab_t':rt},band_at=band_at,
            rates_loader=lambda _currency:rate_inputs,base_anchors=tuple(anchors[t] for t in 'LMH')))
    return result


def calculate(context):
    k=context['axes']['lab']['k_lab']
    base=context['axes']['capex']['base_2026_usd']
    result=evaluate({**INPUTS,'k_lab':k},context.get('rate_inputs'))
    result['partial_basis_changed']=local_basis_changed(
        {'inputs':INPUTS,'lab_haircut':k,'capex_reference':base},HISTORICAL_PARTIAL_FINGERPRINT)
    return result
