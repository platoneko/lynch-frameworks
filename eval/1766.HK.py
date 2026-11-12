#!/usr/bin/env python3
"""CRRC's historical valuation and UBS candidate, in HKD per share.

This draft retains the old data, A-share comparison and shared axis; it is
not a fresh forecast or publication confirmation.
"""
from __future__ import annotations
from lib.gordon import check_branch, check_g_cap, check_r, perpetual_pe, two_stage_pe
from lib.inputs import check_missing, ladder
from lib.tiers import flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'partial_basis'),
                'axes': {'southbound': 'southbound_repricing'}}

HISTORICAL_PARTIAL_FINGERPRINT = '561699bf6547cf53e2efe28e74bfdecf999ad41b27d032111525338a5ed75e87'

# Original input table with value, purpose, source and as-of.
INPUTS = {
    # 总股本（A+H）；[Q3]股本 / 中期分配方案 | as-of 2026-09-30
    'shares': 2.8698864088e10,
    # 每股净资产CNY = [Q3]归母权益175,760,254千元÷总股本；不是港元摘要BPS7.1654 | as-of 2026-09-30
    'bps': 6.1242930543,
    # **FY2026 年初**归母权益**亿元**（= 2025-12-31 实测，yfinance / 年报；BPS 6.00 CNY）；各档前瞻 ROE = eps_x × shares ÷ equity = \(E_{2026}/B_{2025}\)（valuation-rules 2026-09-21，A18）；9月末1,757.60亿含本年留存，不作分母 | as-of 2025-12-31
    'equity': 1721.2,
    # HKD→CNY；Longbridge exchange-rate 1/1.1465，四位小数与旧值相同；只更新查询日 | as-of 2026-11-03
    'fx_hkdcny': 0.8722,
    # **L** EPS CNY = 0.538 × 0.514/0.554（共识区间下沿缩放，A1）；**共识待更新**（2026-11-03核对，保留原预测日期） | as-of 2026-08-21
    'eps_l': 0.4992,
    # **M** = 2026 共识最新 mean（A1）；**共识待更新**（2026-11-03核对，保留原预测日期） | as-of 2026-08-21
    'eps_m': 0.538,
    # **H** = 0.538 × 0.594/0.554（共识区间上沿缩放，A1）；**共识待更新**（2026-11-03核对，保留原预测日期） | as-of 2026-08-21
    'eps_h': 0.5768,
    # **篮 4 龙头制造 r = r_f 中枢 4.0（利率轴 HKD，跟 USD）+ 篮子溢价 6.0**（A17 / A14）；病态区（ROE_M − r = −1.3pp）；`gordon.BASKET_R` | as-of 2026-09-18
    'r_perp': 0.10,
    # 篮 4 龙头制造 r，跨市场固定（方案 A，A14）；只用于 A 股对照带 | as-of 2026-09-18
    'r_perp_a': 0.10,
    # 利率轴 r_f 货币段差 = HKD 中枢 4.0 − CNY 2.5（A14）；只用于货币段披露行（A 股 r_perp_a − gap = 8.5% 的对照带），**不进底牌**，待 `_AXIS.rates` 建成后复核；cap 在 8.5% 下 4.5% ≥ g₂ 4% ✓；601766 十年隐含 r 中位 8.1% 互证 | as-of 2026-09-18
    'cny_rf_gap': 0.015,
    # FY2025资本开支旧资料亿CNY（旧序列59 / 74 / 81 / 102 / 94）；**不进公式，统一原文口径待核**；不能与新固定资产比较栏直接拼成序列（A16） | as-of FY2025
    'capex_fy25': 94,
    # FY2025 折旧摊销亿 CNY（HKD 口径换算，`待补`原文）；**不进公式** | as-of FY2025
    'da_fy25': 88,
    # FY2025固定资产净值亿CNY；[Q3]第14页去年末比较栏；替代旧混合口径779，旧长序列待核；不进公式（A16） | as-of 2025-12-31
    'nppe_fy25': 687.06391,
    # 旧名兼容eval，现为9月末保守净现金亿CNY；326.65422现金等价物+91.72857交易性金融资产−72.77328短借−46.28175一年内到期负债−72.76603长借−24.87822租赁；暂估，完整扩展口径待补；上界及类债见A19；[Q3]第14—15、21页 | as-of 2026-09-30
    'net_cash_ext_h1': 201.68351,
    # 9月末已宣派未付中期股息亿CNY = 0.11元×股本；[Q3]第12页，10-15实施完毕；与9月末现金同一时点 | as-of 2026-09-30
    'div_declared': 31.56875,
    # 经营所需现金锚比率 = FY2016–25 年末「扩展口径净现金 ÷ 收入」最低值（FY2016：97.8 ÷ 2,663.7 亿港元）；低于 2 个月收入 16.7%，不封顶（A19） | as-of FY2016–25
    'cash_anchor_ratio': 0.0367,
    # FY2025 营业收入**亿元**；锚 = `cash_anchor_ratio` × 本行（A19） | as-of FY2025
    'rev_fy25': 2730.6,
    # 旧名兼容eval，现为9月末归母权益亿元；只作现金门槛分母，不作全年ROE分母；[Q3]第15页 | as-of 2026-09-30
    'equity_h1': 1757.60254,
    # 少数股东权益÷合计权益 = 43,903,366÷219,663,620千元；仅所有权粗估，不是可信度折扣；[Q3]第15页 | as-of 2026-09-30
    'mi_share': 0.1998663502,
    # FY2025 全年每股派息 CNY（A 股口径；H 股 0.2652 HKD 同一笔）；派息率分子（A11） | as-of FY2025
    'dps_fy25': 0.23,
    # FY2025 归母净利润**亿元**；派息率分母 = ni ÷ shares = EPS 0.459（A11） | as-of FY2025
    'ni_fy25': 131.8,
    # **留存分支，\(g_2\) = 具名宏观默认 4%**（\(g_2\) 来源优先序第 ④ 层；原「派息 × ROE」推导已删，换源，A11）；三档共用；上限 = 实付留存 × ROE_L = (1 − 50.1%) × 8.32% = 4.15% ✓；cap 6% ✓（货币段披露 4.5% 亦 ✓） | as-of 2026-10-15
    'g2_l': 0.04,
    # 同上；上限 (1 − 50.1%) × 8.97% = 4.48% ✓；eval 校验 ∈ [2.5%, 4%] 且 ≤ 各档上限 | as-of 2026-10-15
    'g2_m': 0.04,
    # 同上；上限 (1 − 50.1%) × 9.62% = 4.80% ✓；各档派息率 = 1 − g₂/ROE_x | as-of 2026-10-15
    'g2_h': 0.04,
    # 营收 FY21→25 CAGR 4.9%（2,257 → 2,731 亿）；**只披露**（越 L 档留存上限 4.15%，不作来源；A11） | as-of 2026-09-18
    'g_evid_max': 0.049,
    # 中国通号 3969.HK 留存分支反解（fPE 7.76 / ROE 7.94%，`implied_g_retaining`）；n=1 **互证，不入公式**（A11） | as-of 2026-09-11
    'g_peer_crsc': 0.0463,
    # H 股 5 年月频 TTM PE 实测下沿（2022-11）；Longbridge `valuation --history`；**护栏，不入主公式**（A2） | as-of 2021-10~2026-09
    'pe_own_min': 6.08,
    # H 股 5 年月频 TTM PE 实测上沿（2024-08）；**护栏，不入主公式**（A2） | as-of 2021-10~2026-09
    'pe_own_max': 10.90,
    # H 股 own-year PE 实测低沿（2022）；**交叉尺，不入主公式**（A2） | as-of FY2022
    'pe_hk_ownyear_l': 5.49,
    # H 股 own-year PE 四年中位；**交叉尺，不入主公式** | as-of FY2022–25
    'pe_hk_ownyear_m': 9.20,
    # H 股 own-year PE 实测高沿（2025）；**交叉尺，不入主公式** | as-of FY2025
    'pe_hk_ownyear_h': 13.19,
    # **候选带**用：UBS 2026-08-27 FY2026E EPS（单家，CNY）；只作 UBS 自身 FY26→FY27 增速的分母（A9），不入底牌；**共识待更新**（2026-11-03核对，保留原预测日期） | as-of 2026-08-27
    'eps_fy26_ubs': 0.50,
    # **候选带**用：UBS 2026-08-27 FY2027E EPS（单家，CNY）；增长型：只取对 `eps_fy26_ubs` 的 +10%，三档共用（A9），不入底牌；**共识待更新**（2026-11-03核对，保留原预测日期） | as-of 2026-08-27
    'eps_fy27_ubs': 0.55,
    # 铁路装备48.36%+城轨14.81%+现代服务1.27%；仅收入校验，不等于盈利权重；[Q3]第8页 | as-of 2026-09-30
    'w_rail': 0.6444,
    # 新产业收入权重35.56%，仅收入校验；[Q3]第8页 | as-of 2026-09-30
    'w_new': 0.3556,
    # 2026 动车组招标列数（H1 70 + H2 186）；UBS（属性 C） | as-of 2026-08-27
    'emu_2026': 256,
    # 2025 动车组招标列数（高基数对照） | as-of FY2025
    'emu_2025': 278,
    # A 股 own-year PE 中位；仅作 A3 对照，**不入主公式** | as-of FY2022–25
    'pe_a_mid': 15.59,
    # 旧名兼容eval，现为2026年前三季四板块收入合计CNY，与总收入相等、缺口0；[Q3]第8页 | as-of 2026-09-30
    'seg_total_h1': 1.94685277e11,
    # 旧名兼容eval，现为2026年1—9月营业收入CNY，不是半年值；[Q3]第3、8页 | as-of 2026-09-30
    'rev_h1': 1.94685277e11,
}

# 2026Q3 company report: original narrative rounds nine-month parent income to CNY 103.14 亿.
HISTORICAL_Q3_PARENT_NI_YI = 103.14

# Original historical reasoning; comments are not extra model inputs.
# - **业务地图摘要**：分部启发式命中 **2 条**（① 两块分别约36% / 64%收入；② 驱动因子不同：铁路跟国铁招标、新产业跟风电与功率半导体周期）。但**反信号更强，且直接否决了分腿倍数**——见属性 B。故主公式整公司尺。
# - **属性 A — 收入分部已对账，分部利润仍是拆分估值的缺口**：官方2026年前三季四板块收入合计 **1,946.85 亿**，等于总收入，缺口 **0%**。[Q3，第8页] 原Longbridge中报分部778.6亿对营收1,316.8亿的约41%差异只代表旧数据商口径问题，不能延续为本期披露缺口。公司尚未披露本期各板块营业利润与投入资本，铁路系 / 新产业仅作收入权重校验，不能按收入权重冒充利润权重。**`待补`：完整分部利润、投入资本及统一口径历史序列**；不再把补分部收入推迟到年报。
# - **属性 B — 市场没有给新产业成长溢价，这是拆腿给不同倍数的否决性证据**：
# - **属性 C — 铁路招标下滑但好于预期，这是 M 档的支点**：2026 年时速 350 公里动车组招标合计 **256 列**（上半年 70 + 下半年 186），低于 2025 年 **278 列** 的高基数（−7.9%），但**高于市场预期**（UBS 2026-08-27，Wisburg 102973）。UBS 据此维持买入、A 股 TP 9.90（DCF），预测 EBIT 利润率从 2025 年 **6.2%** 提升至 2028 年 **7.0%**、ROIC 从 12.4% 升至 15.1%、EPS 2026–28 为 **0.50 / 0.55 / 0.59**。**「负增长但好于预期」正是 `slow_grower` 的典型形态**——它既支持 M 档（共识可兑现），也限制了 H 档（招标总量在收缩，分子上行有限）。
# - **属性 D — ROE < r 使 Gordon 倍数成峰，分支由派息率钉定，这是本票最容易读错的地方**：各档 ROE 8.3–9.6% 全部低于 \(r\)=10%，\(PE(g)=(1-g/ROE)/(r-g)\) 在 \(g=0\) 处封顶 \(1/r\) = 10×、两侧都往下走——任何低于 10× 的倍数都对应两个 \(g\)：全派息 + 萎缩，或留存 + 增长。同业负分支反解（`implied_g` 对 PE < 1/r 一律返回全派息分支）给出 −3.67%、三档 flat 7.32×，那个世界隐含股息率 13.7%、永续萎缩 3.7%。中车实际派息率 **50%**（FY2025 DPS 0.23 / EPS 0.459）、DPS 2018→2025 CAGR **+6.3%**、归母 FY21→25 CAGR +6.4%——它在留存分支上。留存分支下 \(g_2\) = 宏观默认 **+4%**（不超过实付留存 50% × 各档 ROE，A11），各档 ROE 决定维持该增长所需留存（派息率 52 / 55 / 58%），倍数 8.66 / 9.23 / 9.73 同向但温和（倍数比 0.94 / 1.05，分子比 0.93 / 1.07，A4），价带 4.95–6.44、宽 13.0%。共识 EPS 区间 **±7%**（0.514–0.594，2026-04-20）仍是分子散布的全部来源。own-year 分位带（5.49 → 13.19）作交叉尺：13.19× 是 2025 年南向再评级印下的市场事件，不是这门生意的稳态倍数；H 股 own-year PE 从 2022 年的 6.30 升到 2025 年的 10.97 是 A/H 折价收敛的历史（A2）。
# - **属性 E — H/A 年度均值单调上行，是轴上收敛最确定的一只**：H/A 年度均值 2022 0.509 → 2023 0.595 → 2024 0.580 → 2025 0.683 → 2026 **0.762**（截至 2026-09-18），**单调上行**。对比华新（0.578，59% 分位，2026 反而回落）。**但折价收敛不进主尺**（用市价定市价），只作 `stretched` 档解释与轴的方向校验。
# - **属性 F — 为什么不叠 `asset_play` 次类**：新产业里确有被埋没的资产（时代电气权益、风电装备），但 `asset_play` 的前提是**市场看不见**——而时代电气自己就在港股挂牌交易、有公开市值，市场看得一清二楚，只是**给的倍数比中车还低**（属性 B）。市场不是没看见，是不认为它值更高倍数。故不叠次类。
# | A1 | **三档分子取同一条共识区间的相对宽度，缩放到最新 mean**：EPS_L = **0.4992**、EPS_M = **0.538**、EPS_H = **0.5768** | weakened | Longbridge `forecast-eps`：2026-04-20 区间 mean **0.554** / high **0.594** / low **0.514**（同日同组分析师）；2026-08-21 最新 mean **0.538**（区间已退化为单点）。缩放：\(eps\_l = 0.538 \times 0.514/0.554\)、\(eps\_h = 0.538 \times 0.594/0.554\)。**保持同源**（同一条区间的相对宽度）+ 最新中枢 **2026Q3核对：削弱。前三季归母103.14亿、单季−13.97%；按全年三档EPS与股本，Q4尚需归母40.13 / 51.26 / 62.40亿，兑现压力增加。[Q3] 最新数据商单点0.635无可核验年度 / 币种 / 覆盖家数，不混用；原三点暂留，共识待更新。[LB]** | `eps_l`/`eps_m`/`eps_h`；**已知瑕疵**：区间来自 4 月、中枢来自 8 月，`待补`最新完整区间。UBS 2026-08-27 独立给出 2026E EPS **0.50**，低于共识 mean 0.538 约 7%——落在本框架 L(0.4992) 与 M 之间 |
# | A2 | **H 股 own-year PE 分位 5.49 / 9.20 / 13.19 只作交叉尺，不生成倍数**；倍数由 Gordon 生成（A11），自身 5 年月频 TTM PE 带 **[6.08, 10.90]** 作护栏 | active | H 股 own-year PE（H 股价折 CNY ÷ 当年 EPS，年均/低/高）：2022 6.30/**5.49**/7.26 · 2023 8.74/6.86/11.02 · 2024 9.66/6.74/12.08 · 2025 10.97/9.16/**13.19**；中位 9.20。Longbridge 5 年月频 TTM PE（2021-10~2026-09，n=60）min **6.08**（2022-11）/ max **10.90**（2024-08）/ 中位 9.21。生成的 8.66 / 9.23 / 9.73 在月频带内、也在 own-year 带 [5.49, 13.19] 内，M 档 9.23× 与月频中位 9.21 同值（留存分支反解该中位 = g +4.08%，与宏观默认 4% 差 0.1pp，A11）；超额现金未单列，带按合并口径（A19）；own-year 交叉带 3.14 / 5.67 / 8.72 **2026Q3核对：维持。单季EPS0.08元不改写历史序列；原生成倍数8.66 / 9.23 / 9.73仍在6.08–10.90护栏内；本次未刷新年度历史带。[Q3；§3复算]** | `pe_own_min/max` 护栏；`pe_hk_ownyear_l/m/h` **不进公式** |
# | A3 | **锚 H 股，倍数带 MUST 用 H 股序列** | active | A 股 own-year PE 中位 **15.59**（低沿 11.65、高沿 20.51）vs H 股 **9.20**——相差 68%。锚 H 却套 A 股带会使 M 由 5.67 跳到 **9.55 HKD** **2026Q3核对：维持。前三季合并人民币EPS0.36元适用于同一家公司；无业务或股权口径变化支持借用A股倍数。[Q3]** | 全公式；`_AXIS.southbound-repricing.md` §3 第 1 条 |
# | A4 | **本票为分子驱动的带，倍数三档同向但温和**（`slow_grower` 允许同向，A2e-5；A2e-2c-ex 豁免不使用） | active | 分子比 L/M **0.928**、H/M **1.072**；倍数比 **0.937 / 1.054**——来自同一 \(g_2\) 在各档 ROE 下所需留存不同（派息率 52 / 55 / 58%），不是另一条 de-rate 假设。两端同质：L 与 H 各自的差距都是「分子 × 倍数」同向贡献（A2e-5 红线不触发）。**flat-multiple 阶梯**（三档置 PE_M 9.23）：5.29 / 5.70 / 6.11，分子上已成阶梯 ✓。`slow_grower` 的 L / H = 共识下沿 / 上沿（A2e-1），各自可独立命名（招标兑现不及预期 vs 招标不再下滑 + 新产业利润率改善） **2026Q3核对：维持。单季归母−13.97%首先削弱EPS兑现；旧三档0.4992 / 0.538 / 0.5768暂留，不额外抬倍数。[Q3；A1]** | 全公式；**读 zone 时须知道本票的三档几乎是同一个世界的三个共识点**，价带宽度不承载周期情景 |
# | A5 | **铁路系 / 新产业只进收入校验与解释层，不按收入权重拆利润估值** | active | **2026Q3核对：结论维持，原41%收入缺口依据被证伪。** 官方四板块收入合计与总收入均为1,946.85亿，缺口0%；铁路系64.44%、新产业35.56%。[Q3，第8页] 本期仍无分部营业利润和投入资本，收入权重无法代替利润权重。时代电气H股历史PE8.48（2026-09-11）只作旧外部比较，不证明本期应有成长溢价 | 主尺仍为整公司；更新收入权重与缺口；`待补`分部利润、资本与统一口径历史数据，取得后重新评估拆腿 |
# | A6 | **不折现**：三档都是「当期盈利能力 × 当期倍数」 | active | 与其余三票同一处理 **2026Q3核对：维持。主模型仍为FY2026，前三季实际EPS0.36元未引入新的远期盈利年；不另折现。[Q3；A1]** | 全公式 |
# | A7 | **不采用卖方目标价生成倍数**；UBS A股DCF目标价9.90元保留原2026-08-27日期 | active | **2026Q3核对：维持。** Longbridge H股7家目标价均值6.484港元、范围4.581–7.975港元、评级hold（标注2026-11-01更新，11-03查询）。[LB] 原A股目标价8.10元和UBS9.90元仅为旧交叉资料，不当成本季新预测；H股目标价更新不能证明各家盈利预测已刷新 | 只作交叉，不进入EPS或倍数 |
# | A8 | **本票挂 `_AXIS.southbound-repricing.md`，轴只解释 H/A 折价的方向，不进分子也不改倍数**（倍数由 Gordon 生成，A11） | active | H/A 年度均值单调上行（2022 0.509 → 2026 0.762，截至 2026-09-18）。轴 §3 第 1 条「H 股倍数取 H 股 own-year 分位」已被 valuation-rules「永续增长口径」取代——本票按 `6655.HK` / `600011.SH` 的解法处理：走 Gordon，own-year 带降级为交叉尺 **2026Q3核对：维持。新产业占收入35.56%没有改变H/A轴仅作解释的定位；A/H折价不进入1,946.85亿收入或103.14亿归母利润的生成路径。[Q3]** | 双报 A/H 两套五档区间 |
# | A9 | **UBS 的利润率改善路径（EBIT 6.2%→7.0%、ROIC 12.4%→15.1%）未进分子；FY2027 UBS 单家 EPS 0.55 只进候选带，升级门槛 = FY2027 ≥2 家带区间共识** | weakened | UBS 2026-08-27 预测 EPS 2026/27/28 = 0.50/0.55/0.59（CAGR 约 8.6%）；yfinance 2026-09-11：601766.SS FY2027 n=1 0.562、1766.HK 线 n=1 0.553——三个单点互相印证但无一是 ≥2 家带区间。**裁决顺序 ②**：最远的 ≥2 家带区间共识年 = FY2026（Longbridge 4 月区间），故底牌分子停在 FY2026；FY2027 单家按 A2e-7h 做候选带。**判为增长型**（construction §7h）：UBS 的 0.55 是它逐年基准路径（0.50 / 0.55 / 0.59）上的普通点估计，不是乐观情景、公司目标或产能折算 → 用 UBS 自己的 FY26→FY27 增速 0.55 / 0.50 − 1 = **+10%**（不用对共识均值的 +2.2%：UBS 的起点 0.50 低于共识 0.538，混用两家口径会把口径差当增长），三档共用一年过渡 `two_stage_pe(g1 10%, n 1, g2, ROE_x, r)`（FY2027 为 t = 2、折一年）→ **L′/M′/H′ = 4.85 / 5.63 / 6.41**。三档都略低于底牌：段一派息 1 − g1/ROE = −20% / −11% / −4%，ROE 8.3–9.6% 低于 r 10%，多出的增长要靠留存、在病态区里是减值（同 A13）；FY2027 隐含 EPS 0.549 / 0.592 / 0.634，后两者高于 UBS 自己的 0.55，无来源。**不是多一年复利**：缺失输入具名 = FY2027 ≥2 家共识；触发后走框架纠正把分子年改为 FY2027 三点并删除候选带行 **2026Q3核对：削弱利润率平顺改善的把握，候选带资格不变。Q3扣非−19.47%；前三季报表营业利润率7.68%，去年同期7.94%，该口径不等同UBS标准化EBIT。[Q3] 管理层2027需求展望有客流条件、无量化利润指引；仍未取得FY2027≥2家可核验完整区间，旧UBS0.50/0.55维持原日期、共识待更新。[交流][LB]** | `eps_fy27_ubs`；Outputs 一行；eval ±0.05 复算；不进底牌 zone / 跨票比值 |
# | A10 | **对国铁集团的订单依赖未单独建模** | active | UBS 明确把「对中国国家铁路集团订单的高度依赖」列为首要风险，其余含政府公共支出下降、海外增长放缓、客运量不及预期、原材料涨价、汇率波动。本框架三档均通过共识 EPS 隐含该依赖，**未做独立情景** **2026Q3核对：维持。铁路装备收入941.46亿占48.36%，其中动车470.05亿；近期动车新造 / 高级修合同429.7亿。收入与合同不全等于国铁单一客户销售，集中度未另拆情景。[Q3][合同]** | `eps_*`；**方向性中性但集中度高**。`deep_discount` 档的主要解释材料 |
# | A11 | **倍数由 Gordon 生成，\(g_2\) = +4%，走留存分支，来源 = 具名宏观默认（\(g_2\) 来源优先序第 ④ 层）；三档共用；各档 ≤ 实付留存 × ROE_x** | active | **分支由派息率钉定**（valuation-rules「反解分支」）：FY2025 DPS 0.23 CNY / 归母 EPS 0.459（131.8 亿 ÷ 28.70 亿股）= 派息率 **50.1%**；DPS 2018→2025 CAGR **+6.3%**（0.15 → 0.23，A 股 CNY 序列）；归母 FY21→25 CAGR +6.4%；共识 FY26 0.538 → FY27 0.55–0.56（UBS / yfinance A 线 / H 线三个单点同向）→ 留存分支。**换源（2026-10-15 框架纠正）**：原值 +4.48% = (1 − 50.1%) × ROE_M，用的是已从规则里删除的「派息 × ROE」推导，按来源优先序逐层重走：① 用户判断——无（原值是助手推导）；② 同业横截面——**同业留存分支反解**（2026-09-11，`implied_g_retaining`）中国通号 3969.HK fPE 7.76 / ROE 7.94% / 派息 50% → **+4.63%**（n=1，只作互证）；时代电气 3898.HK fPE 6.92 / ROE 9.55% / 派息 37% → +8.67% **> cap 6%**，且其 6.92× 低于 \(g\in[0,6\%]\) 在该 ROE 下可达的最低倍数 9.29×——市价在 r=10% 下不可达，说的是 r≈11.4% 而非 \(g\)，**BLOCKED 剔除**；剔除后 n = 1，无共享情景轴 → 落下一层；③ 自身市场读数——非周期股取自身实测带带边反解，只在生成倍数出带时才有读数，本票不出带（A2）→ 无读数；④ **具名宏观默认 4%**（正常名义增长），在 2.5%–4% 内直接采用。**上限（valuation-rules ③ 约束 2）**：实付留存 × ROE = (1 − 50.1%) × 8.32 / 8.97 / 9.62% = **4.15 / 4.48 / 4.80%**，4% 三档都在内，不截。**域判定**：ROE 8.32 / 8.97 / 9.62% 对篮 4 10%（−1.7 / −1.0 / −0.4pp）→ **病态区**（|ROE − r| < 3pp），倍数钉在 \(1/r\) 附近、对 g 不敏感；cap 6%（货币段披露 8.5% 下 4.5%），4% 在内。同业负分支反解（`implied_g` 对 PE < 1/r 一律返回 \(r-1/PE\)：时代 −4.45% / 通号 −2.89% → −3.67%）要求 100% 派息 + 永续萎缩，与两家实际派息 37–50% 及正增长共识矛盾，并且过不了**同世界门**（裁决顺序 ④：本票共识与实测方向向上，\(g_2\le0\) 来源不可用）。交叉：营收 FY21→25 CAGR 4.9%（越 L 档留存上限，只披露）；DPS CAGR 6.3% 读作派息率抬升期（2025 起加派中期股息）而非稳态；月频 PE 中位 9.21× 的留存分支反解 +4.08%，与 4% 同量级。护栏：8.66 / 9.23 / 9.73 ∈ [6.08, 10.90] ✓（A2）。**杠杆**：宏观层两端 2.5% / 4% → 5.34 / 5.93 / 6.53 与 4.95 / 5.70 / 6.44；±1pp → 5.23 / 5.86 / 6.50 与 4.57 / 5.46 / 6.35，1pp ≈ 0.2 港元/股 **2026Q3核对：维持，4%不是本季已确认的增速。前三季扣非+3.00%，中期股息0.11元合计31.57亿、10-15支付；未转全派息 / 永久萎缩。[Q3] 原FY2025派息率及宏观来源保留原日期；通号同日完整互证数据待补，不把旧4.63%标成本季读数** | `g2_l/m/h`、`dps_fy25`、`ni_fy25`、`g_evid_max`、`g_peer_crsc`；eval 校验 \(g_2\in[2.5\%, 4\%]\)、各档 \(g_2 \le (1-\text{派息率})\times ROE_x\) 与 `check_branch`（模型派息率 vs 实付 ±20pp）；每期年报重拉派息率与 DPS（派息率上升使某档上限 < 4% → 取上限）；通号每季度同日重拉；**MUST NOT** 为迁就现价改 \(g_2\) |
# | A12 | **卖方目标价只作交叉，盈利共识是否财报后刷新须另核** | active | **2026Q3核对：维持。** H股7家均值6.484港元（4.581–7.975，hold，数据标注2026-11-01，11-03查询）；H/目标价约0.99、M/目标价0.88，按原EPS折算隐含约10.5倍，仍高于本模型10倍上限。[LB] 不由目标价回推EPS | §0卖方交叉；原派息率35%–80%区间、FY2027共识转向及A9升级门槛继续跟踪 |
# | A13 | **ROE < r 的歧义 MUST 显式陈述，但先用派息率钉分支**：各档 ROE 8.3% / 9.0% / 9.6% 全部低于 \(r\)=10%，落在 `gordon.py` 的 `_ROE_NEAR_R` 病态区（|ROE−r| < 3pp） | active | Gordon 在 ROE < r 时是一座峰：\(g=0\) 处 \(1/r\) = 10×，往正走（留存换增长、增量资本回报低于 r）与往负走（全派息、萎缩）倍数都下降，故 10× 以下每个倍数都有两个 \(g\)。**分支歧义由派息率解决**（50% 派息 → 留存分支，A11）；**剩余的 r / g 歧义仍在**：M 档 9.23× 既可读成「\(g=+4\%\)、\(r=10\%\)、派息 55%」，也可读成「\(g=0\)、全派息、\(r\approx10.8\%\)」，两者在本框架内不可区分，故锚点建立在分子（共识区间）与具名宏观 \(g\) 上，而非反解的 \(g\)。卖方 TP 6.47 = 10.5× 在顶 10× 之上，任何分支**无解** **2026Q3核对：维持。累计加权ROE5.87%不是全年前瞻回报，不能直接替换8.3 / 9.0 / 9.6%；原三档仍低于10%，不因单季利润回落抬高长期回报。[Q3]** | §3 交叉备注；防止把不稳定的反解当结论 |
# | A14 | **篮子 r 跨市场固定（方案 A）+ 锚点税前公允值**：r = 篮 4 **10%**（r_f 中枢 4.0 + 篮子溢价 6.0），H 股锚点与 A 股对照带同值（`r_perp` = `r_perp_a`）、同倍数；货币段拆分（CNY 段 2.5 + 6.0 = 8.5%，r_f 差 `cny_rf_gap` 1.5pp）是仓库级未立项的读法，只作披露行（A 股货币段带），**待 `_AXIS.rates` 建成后复核**；南向持有 H 股的 20% 红利税是持有者税务，**不进锚点**（曾作分子折扣 k 0.90，2026-09-20 撤销：锚点是资产的税前公允值，持有渠道不同税率不同，扣进锚点会使港股之间、A/H 之间不可比） | active | 同公司 A/H 对：601766 十年隐含 r 中位 8.1% / 1766 12.1%（§3 末交叉验证），篮 4 单一 10% 落在两地中间。利率平价的反论同 `0728.HK.md`——g 不加汇率项。`valuation-rules.md`「§r 篮子」篮子 r 跨市场固定，`r*` 行只能是篮子表值，8.5% 不是 **2026Q3核对：维持。中期每股股息0.11元、合计31.57亿不改变税前锚点口径；本季没有改变跨市场10%要求回报的证据。[Q3]** | `r_perp` / `r_perp_a` / `cny_rf_gap`；A 股对照带 |
# | A16 | **增长不靠留存的简式尚无成立证据，维持留存分支完整式**；重审条件为统一口径净固定资产连续两年下降且净现金吸收≥80%留存 | active | **2026Q3核对：维持，但撤回旧混合序列证明。** 原固定资产779亿与本季原文2025年末固定资产687.06391亿不是可直接比较的统一口径，不再用“2023→25净PP&E+17%”证明capex高于折旧。2026-09末固定资产681.34559亿，较去年末−0.83%，仅一期；前三季购建长期资产现金支出42.50753亿（去年55.51266亿）。存货1,065.26亿vs去年末951.43亿、应收账款1,194.94亿vs1,165.02亿，经营现金流−107.64亿，留存仍占用于经营资本，不能证明增长免费。[Q3，第13—14、19—20页] 未取得本期完整折旧明细及统一长序列，不据固定资产单项变动反推capex与折旧大小 | `nppe_fy25`改取原文固定资产687.06391亿；原capex / D&A序列仅旧资料待核，不进主公式；`待补`统一人民币口径≥7年序列 |
# | A17 | **归篮：整公司（铁路系 + 新产业两腿同归）→ 篮 4 龙头制造**（轨交装备全球龙头、`slow_grower` 常规经营现金流；无合约化 / 管制 / 条件性腿；缺少分部利润与资本使分腿估值不可落地，归篮不触发分腿，A5）；无备选篮；CAPM 粗筛 `待补`（未取 β） | active | `gordon.BASKET_R` 篮 4 = 10%；十年 A/H 隐含 r 中位 8.1 / 12.1% 夹住 10%（Longbridge 10 年月频，A14）。域判定：ROE 8.32 / 8.97 / 9.62% 对 10% 全在病态区（A11），g 取具名宏观 4%、受实付留存 × ROE 上限约束，cap 6% **2026Q3核对：维持。铁路装备与新产业合计占83.92%，仍是制造交付业务；分部收入已对账但利润未拆，不据此改风险归类。[Q3]** | `r_perp` / `r_perp_a`；全部倍数 |
# | A18 | **ROE 口径 = 分子年年初账面（\(E_{n+1}/B_n\)，valuation-rules 2026-09-21）**：分子年 FY2026 已过半，年初账面 = 2025-12-31 实测归母权益 1,721.2 亿（BPS 6.00 CNY），是已披露数、无需按 b1 = g/ROE 滚动；9月末1,757.60亿包含本年留存，不作分母（那是分子年自己的留存进分母）。ROE **8.32 / 8.97 / 9.62%**；超额现金未单列（A19），此合并口径 ROE 即 RONIC（稳态新投资回报率）。留存去向：模型留存 \(b=g_2/ROE_M\) = 44.6% vs 实付留存 49.9%，差额5.3pp仅为模型与实付之差，不证明本季资金实际流向；超额现金不到单列门槛，只作披露（A19） | confirmed | yfinance 601766.SS 年度 / 季度资产负债表（2025-12-31 归母权益 172,120.6M；2026-06-30 176,477.1M）；valuation-rules「Gordon ROE 口径」（2026-09-21）；A11 / A13 **2026Q3核对：确认。原文比较栏再次披露2025-12-31归母权益1,721.20649亿；当期归母权益1,757.60254亿不替换年初分母。Inputs保留1,721.2亿的原精度，锚点无实质变化。[Q3，第15页]** | `equity`（FY2026 年初）；eval 步骤 4a 打印宏观区间两端三档（只披露） |
# | A19 | **超额现金未达15%门槛，不单列；合并盈利、ROE、历史倍数口径维持** | active | **2026Q3核对：维持，更新金额。** 9月末现金等价物326.65422亿+交易性金融资产91.72857亿−短期借款72.77328亿−一年内到期非流动负债46.28175亿−长期借款72.76603亿−租赁24.87822亿=保守净现金201.68351亿；一年内到期负债全扣、未拆短期理财，标暂估。再扣9月末已宣派未付中期股息31.56875亿及原经营现金锚100.21302亿，超额现金69.90174亿，占归母权益1,757.60254亿的3.98%，约0.244元/股；少数股东比例19.9866%，按权益粗估归母份额55.93亿，仅披露。[Q3，第12—15、21页] **边界**：把其他流动资产55.92338亿全计可用金融资产、且不扣一年内到期负债，净现金上界303.88864亿，超额现金172.10687亿、占9.79%，仍未触发15%；未扣财务公司吸收存款58.10230亿等类债项只会使该上界更宽松。货币资金453.45251亿与现金等价物的差额不直接视作可分配现金。中期股息10-15已支付，按9月末现金仍扣未付股息，禁止混时点。原经营现金锚窗口不变，若锚取0，该宽松上界亦为15.49%，会越线，故保留具名年末窗口并披露边界，不以此认定准确净现金 | `net_cash_ext_h1`等旧字段名仅为兼容eval，日期全部更新至9月末；`待补`短期投资、受限现金、财务公司类债及归母现金分布；正式完整口径≥15%须同换经营盈利、回报和历史倍数 |
# | A20 | **经营价值与超额现金其余读数（valuation-rules「经营价值与超额现金」，2026-10-16 框架纠正，锚点不变）**：① 超额现金不单列（A19）；**增长期资金缺口 0**：分子年 FY2026 已开始，估值基准日到分子年初之间没有窗口。② **时点对齐 τ = 0**：分子 FY2026E 共识，回报分母取 2025-12-31 年末账面（A18）→ 分子年初 2026-01-01 早于估值基准日 2026-09-30（τ = −0.75），按规则边界取 0；没有窗口，窗口可分配利润不取；候选带同以 FY2026 为分子年，不动。③ **稳态回报三段不改**：三档前瞻回报 8.3 / 9.0 / 9.6% 都低于 r 10%，最近三个完整年自身回报（利润 ÷ 上年末归母权益）2023 7.55% / 2024 7.70% / 2025 7.81% 也都低于 r → 按「持续失败只往下拉」维持前瞻值，不上抬到 r；永续增长是具名宏观默认，不重解；不属商品腿。④ **无打折 k** | active | yfinance 601766.SS 年报（2023–2025 归母净利与权益）；valuation-rules「经营价值与超额现金」①②③ **2026Q3核对：维持。基准日改2026-09-30，距2026-01-01为−0.75年，仍按边界取τ=0；增长期资金缺口0。累计ROE5.87%不构成上调长期回报依据。[Q3]** | 锚点不变 |

TIERS = ("l", "m", "h")
# The 2026-04-20 consensus range the tiers are rescaled from (A1).
CONSENSUS_LOW, CONSENSUS_MEAN, CONSENSUS_HIGH = 0.514, 0.554, 0.594
EPS_TOL = 0.001
# g2 source order ④ (valuation-rules): named macro default 4%, 2.5% floor;
# a re-sourced g2 inside [2.5%, 4%] is adopted without returning to the dialogue.
G_MACRO, G_MACRO_LO = 0.04, 0.025
# 经营价值与超额现金 ①: split only when C_ex >= 15% of parent equity.
EXCESS_CASH_TRIGGER = 0.15
SEGMENT_GAP_WARN = 0.20
CANDIDATE_TOL = 0.05
YI = 1e8
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"

REQUIRED = [
    "shares", "bps", "equity", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h",
    "r_perp", "r_perp_a", "cny_rf_gap", "nppe_fy25",
    "net_cash_ext_h1", "div_declared", "cash_anchor_ratio", "rev_fy25", "equity_h1", "mi_share",
    "dps_fy25", "ni_fy25", "g2_l", "g2_m", "g2_h",
    "g_evid_max", "g_peer_crsc",
    "pe_own_min", "pe_own_max",
    "pe_hk_ownyear_l", "pe_hk_ownyear_m", "pe_hk_ownyear_h", "eps_fy26_ubs", "eps_fy27_ubs",
    "w_rail", "w_new", "emu_2026", "emu_2025",
    "pe_a_mid", "seg_total_h1", "rev_h1",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 4d / 7).
NOT_FORMULA = ("pe_hk_ownyear_l", "pe_hk_ownyear_m", "pe_hk_ownyear_h", "pe_a_mid", "eps_fy26_ubs", "eps_fy27_ubs", "g_peer_crsc")


def check_r_rows(r: float, r_a: float, baskets: dict[str, int]) -> list[str]:
    """Both r rows are the same basket: basket r is fixed across currencies
    (方案 A, A14), so the A-share companion band carries 篮 4 too."""
    errors: list[str] = []
    for where, value in (("r_perp", r), ("r_perp_a", r_a)):
        if where not in baskets:
            errors.append(f"{where}: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(value, where, baskets.get(where))
    if baskets.get("r_perp_a") != baskets.get("r_perp"):
        errors.append(f"r_perp_a 篮 {baskets.get('r_perp_a')} != r_perp 篮 {baskets.get('r_perp')} — one company, one basket (A14)")
    return errors


def band_at(g2: float, eps: dict[str, float], roe: dict[str, float], r: float, fx: float) -> tuple[float, float, float]:
    """L/M/H in HKD for one shared g2 -- each tier's own ROE sets its payout and multiple."""
    return tuple(eps[t] * perpetual_pe(g2, roe[t], r) / fx for t in TIERS)  # type: ignore[return-value]


def evaluate(inp: dict[str, float]) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    baskets = {'r_perp': 4, 'r_perp_a': 4}

    r = inp["r_perp"]
    r_a = inp["r_perp_a"]
    fx = inp["fx_hkdcny"]
    eps = {t: inp[f"eps_{t}"] for t in TIERS}

    # --- Step 1: numerator ladder and provenance -----------------------------
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    # Both EPS ends must come from the same consensus range (A1).
    for tag, ref in (("l", CONSENSUS_LOW), ("h", CONSENSUS_HIGH)):
        derived = eps["m"] * ref / CONSENSUS_MEAN
        if abs(derived - eps[tag]) > EPS_TOL:
            errors.append(
                f"eps_{tag} {eps[tag]} vs rescaled {derived:.4f} "
                f"(mean {eps['m']} x {ref}/{CONSENSUS_MEAN}) — ends not same-source"
            )
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 1b: excess-cash trigger (经营价值与超额现金 ①, A19) ----------------
    # C_ex = latest extended net cash - declared unpaid dividend - anchor, the
    # anchor being the lowest FY2016-25 year-end「net cash / revenue」x FY2025
    # revenue (below the 2-month cap).  Under 15% of parent equity → no split:
    # earnings, ROE and historical multiples all stay consolidated.
    cash_anchor = min(inp["cash_anchor_ratio"], 2 / 12) * inp["rev_fy25"]
    c_ex = inp["net_cash_ext_h1"] - inp["div_declared"] - cash_anchor
    c_ex_share = c_ex / inp["equity_h1"]
    if c_ex_share >= EXCESS_CASH_TRIGGER:
        errors.append(f"C_ex {c_ex:.1f}亿 = {c_ex_share:.1%} of parent equity >= 15% — the excess cash "
                      "must be split (operating earnings / RONIC / operating multiples), A19 no longer holds")

    # --- Step 2: tier ROE, then g2 on the retention branch (A11) --------------
    # `equity` is the FY2026 OPENING book (end-2025, reported): E_{n+1}/B_n per
    # valuation-rules 2026-09-21 (A18).  Nothing to roll — the year has started.
    # No excess-cash split (A19), so this consolidated ROE is the RONIC.
    roe = {t: eps[t] * inp["shares"] / (inp["equity"] * YI) for t in TIERS}
    payout_fy25 = inp["dps_fy25"] * inp["shares"] / (inp["ni_fy25"] * YI)
    # ③ constraint 2: a re-sourced g2 is capped by what is actually kept.
    g_retained = {t: (1.0 - payout_fy25) * roe[t] for t in TIERS}
    errors += check_r_rows(r, r_a, baskets)
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], r, f"g2_{t}")
    errors += check_g_cap(inp["g2_m"], r_a, "g2_m@r_perp_a")
    # Disclosure-only CNY r_f segment (A14): g2 must also clear its tighter cap.
    r_ccy = r_a - inp["cny_rf_gap"]
    errors += check_g_cap(inp["g2_m"], r_ccy, "g2_m@CNY 段 (披露)")
    if not (inp["g2_l"] == inp["g2_m"] == inp["g2_h"]):
        errors.append(f"g2 tiers {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} must be one shared value (A11)")
    # A negative g2 is the 100%-payout branch; on a company paying out half it
    # describes a different company (A11 / valuation-rules「反解分支」).
    if inp["g2_m"] <= 0:
        errors.append(f"g2={inp['g2_m']:+.4f} <= 0 is the full-payout branch — CRRC pays out {payout_fy25:.0%} (A11)")
    # Re-sourced to the macro layer (A11): inside [2.5%, 4%], and under each
    # tier's retained-earnings cap (1 - paid payout) x ROE_x.
    if not (G_MACRO_LO - 1e-9 <= inp["g2_m"] <= G_MACRO + 1e-9):
        errors.append(f"g2_m {inp['g2_m']} outside the macro range [{G_MACRO_LO}, {G_MACRO}] (A11)")
    for t in TIERS:
        if inp[f"g2_{t}"] > g_retained[t] + 1e-9:
            errors.append(f"g2_{t} {inp[f'g2_{t}']} > (1 - payout {payout_fy25:.3f}) x ROE_{t} = {g_retained[t]:.4f} "
                          "— take the cap (valuation-rules ③ constraint 2, A11)")
    errors += check_branch(inp["g2_m"], roe["m"], r, payout_fy25, "g2_m")
    if errors:
        raise ValueError('; '.join(errors))
    pe = {t: perpetual_pe(inp[f"g2_{t}"], roe[t], r) for t in TIERS}
    # 校验步骤 4: guardrail — generated multiples inside the realised band.
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: generated PE_{t} {pe[t]:.2f} outside realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] (A2) — STOP, do not force g"
            )
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 3: check-layer only (legs never enter the anchor path) --------
    if abs(inp["w_rail"] + inp["w_new"] - 1.0) > 1e-6:
        errors.append(f"leg weights must sum to 1: {inp['w_rail']} + {inp['w_new']}")
    gap = 1.0 - inp["seg_total_h1"] / inp["rev_h1"]
    if inp["emu_2026"] >= inp["emu_2025"]:
        errors.append(
            f"EMU tender {inp['emu_2026']:.0f} >= prior {inp['emu_2025']:.0f} — "
            "§1 属性 C assumes a declining-but-better-than-feared tender; rerun the narrative"
        )
    # Comparison-only fields must not have leaked into the multiple path.
    for key in ("pe_a_mid", "pe_hk_ownyear_m"):
        if abs(inp[key] - pe["m"]) < 1e-9:
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if abs(inp["g_peer_crsc"] - inp["g2_m"]) < 1e-9:
        errors.append("g_peer_crsc leaked into g2 — it is an n=1 cross-check, not the source (A11)")
    leaked = [k_ for k_ in NOT_FORMULA if k_ not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = band_at(inp["g2_m"], eps, roe, r, fx)
    if not (L < M < H):
        raise ValueError(f'L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}')
    A, B = cut_points(L, M, H)

    # 校验步骤 4a (A11): the macro layer's two ends (2.5% floor / 4% default)
    # and the revenue CAGR are printed as disclosure, never a reason to pick a g.
    evid = {g: band_at(g, eps, roe, r, fx) for g in (G_MACRO_LO, G_MACRO, inp["g_evid_max"])}

    flat_errs, flat_cny = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe["m"])
    errors += flat_errs
    flat = tuple(v / fx for v in flat_cny)
    flat_width = (flat[2] - flat[0]) / (2 * flat[1])

    # 校验步骤 4c (A9): UBS's FY2027 is an ordinary base forecast = growth type
    # (construction §7h).  UBS's own FY26 -> FY27 step is one n = 1 transition
    # shared by all three tiers (FY2027 at t = 2).  Compared to the Outputs line
    # the digest reads.
    g1_cand = inp["eps_fy27_ubs"] / inp["eps_fy26_ubs"] - 1
    cand = tuple(eps[t] * two_stage_pe(g1_cand, 1, inp[f"g2_{t}"], roe[t], r) / fx for t in TIERS)
    errors += ladder("候选带", *cand)
    if errors:
        raise ValueError('; '.join(errors))
    pe_a = {t: perpetual_pe(inp[f'g2_{t}'], roe[t], r_a) for t in TIERS}
    la, ma, ha = (eps[t] * pe_a[t] for t in TIERS)
    pe_ccy = {t: perpetual_pe(inp[f'g2_{t}'], roe[t], r_ccy) for t in TIERS}
    lc, mc, hc = (eps[t] * pe_ccy[t] for t in TIERS)
    # UBS's 10% transition growth exceeds all three returns. The old formula
    # therefore implies negative distributions, but it did not establish how
    # the gap was funded. Preserve the candidate as a flagged historical case.
    candidate_payout = {t: 1 - g1_cand / roe[t] for t in TIERS}
    return {
        'ticker': '1766.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'framework_as_of': None,
        'historical_valuation_as_of': '2026-09-30',
        'historical_framework_as_of': '2026-11-03',
        'units': {'price': 'HKD_PER_SHARE'},
        'anchors': dict(zip('LMH', (L, M, H))),
        'candidate': {'label': 'UBS FY2027', 'anchors': dict(zip('LMH', cand))},
        'option': None,
        'segments': {'company': {'unit': 'HKD_PER_SHARE', 'values': dict(zip('LMH', (L, M, H)))}},
        'key_parameters': {
            'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', r)},
            'growth_rate': {'unit': 'RATIO', 'values': {t.upper(): inp[f'g2_{t}'] for t in TIERS}},
            'forward_return': {'unit': 'RATIO', 'values': {t.upper(): roe[t] for t in TIERS}},
            'steady_return': {'unit': 'RATIO', 'values': {t.upper(): roe[t] for t in TIERS}},
        },
        'a_share_comparison': dict(zip('LMH', (la, ma, ha))),
        'historical_candidate_payout': {t.upper(): candidate_payout[t] for t in TIERS},
        'review_flags': ['historical_candidate_funding_unverified', 'historical_exchange_rate_unverified'],
        'diagnostics': {'eps': {t.upper(): eps[t] for t in TIERS},
                        'roe': {t.upper(): roe[t] for t in TIERS},
                        'pe': {t.upper(): pe[t] for t in TIERS},
                        'cash_anchor': cash_anchor, 'excess_cash': c_ex,
                        'excess_cash_share': c_ex_share,
                        'q4_required_profit_100m': {t.upper(): eps[t] * inp['shares'] / YI - HISTORICAL_Q3_PARENT_NI_YI for t in TIERS},
                        'sensitivity_growth_2_5pct': dict(zip('LMH', evid[G_MACRO_LO])),
                        'sensitivity_growth_4pct': dict(zip('LMH', evid[G_MACRO])),
                        'flat_multiple': dict(zip('LMH', flat))},
    }


def calculate(context):
    axis = context['axes']['southbound']
    if axis.get('role') != 'reference':
        raise ValueError('southbound axis must be a reference')
    result = evaluate(INPUTS)
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'axis_source': context['axis_versions']['southbound'],
         'consensus': [CONSENSUS_LOW, CONSENSUS_MEAN, CONSENSUS_HIGH],
         'constants': [EPS_TOL, G_MACRO, G_MACRO_LO, EXCESS_CASH_TRIGGER,
                       HISTORICAL_Q3_PARENT_NI_YI, YI]}, HISTORICAL_PARTIAL_FINGERPRINT)
    return result
