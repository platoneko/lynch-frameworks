#!/usr/bin/env python3
"""SOFI legacy valuation; no financial assumption was updated in migration.

Inputs are USD millions except ratios, EPS and shares in millions. Financial
service maintenance share is an explicit unverified estimate, not a disclosure.
"""
from __future__ import annotations
from math import ceil
from lib.gordon import check_g_cap, check_r, check_transition_years, g_cap
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

FORMULA_ID = "sofi_gordon_tbv_oe_v1"
LISTING_CCY = "USD"
MAINT_TOL = 0.005
MAINT_STATED = 0.485  # legacy A18 calculated value and guard
PB_BAND = (1.26, 2.03)  # historical guardrail, not a generator
CONSENSUS_YEARS = 2
# | A1 | 主类 `fast_grower`，次类 `cyclical` 只改 L 的下行形状（经常性信用/利率冲击），不改 M/H 分子逻辑 | active | 对话锁定 2026-09-12；64% 贡献利润来自无抵押消费贷 | L 构造按更苛刻类 |
# | A2 | 账面基数 = **TBV**（权益 − 商誉 − 无形 + 相关 DTL）= $9,705.0M；TBVPS 7.48；股数 = 期末普通股 1,296.617M | active | 8-K 2026-10-27 TBV 表（2026-09-30） | `tce`、`shares` |
# | A3 | 分子股数口径：共识为稀释 EPS，乘以期末普通股 1,296.6M 求 NI（较 Q3 GAAP 稀释 WASO 1,357.8M 偏保守 ~5%）。**2026-10-27 削弱**：管理层 FY27 指引调整净利 ~$1.28B ÷ EPS ~0.90 隐含约 14.2 亿股（Q3 调整稀释 WASO 1,331.4M），比期末普通股多约 10%，电话会未解释；若属实，EPS × 普通股的 NI 口径一致，但加回的获客支出每股值偏高约 9%（对 M 约 −0.4） | weakened | 8-K 2026-10-27 EPS 表；电话会 2026-10-27 | `ni_27_*`；Q3 10-Q 或卖方刷新后核股数；Longbridge 若出 FY27 NI 共识则替换 |
# | A4 | 超额资本 \(X\) = CET1 资本 − 16.0% × RWA = 9,520 − 0.16 × 56,237 = **$523M**（2026-06：$1,316M）；16.0% = 2024-12 holdco 实测 CET1。**2026-10-27 削弱**：管理层把资本率目标说成「十几出头到十五左右」（按 13.5% 计），16% 不再是自然落点；仍按「出现新的自身实测低点才改」保留 | weakened | 8-K 2026-10-27 监管资本表；电话会 2026-10-27 | 只定跑道 \(n\)（A5）；留存 \(b\) 中 CET1 目标约掉，对 M 无影响（敏感性：12% / 16.9% → M 不变）；L 世界 \(X\) 作吸损垫不分列 |
# | A5 | **\(n = 1.25\) 年**（Q4'26 + FY27，自 2026-09-30）：CET1 资本 + 共识留存 = 9,520 + 267 + 1,067 = $10.85B 回到 16% 需 RWA $67.8B（+21%）；Q3 RWA 单季 +15%、共识营收 FY27 +26% → 跑道 ≤ 1.25y。**2026-10-27 确认**：超额资本消化快于原路径（CET1 18.7% → 16.9% 一个季度） | confirmed | 8-K 2026-10-27 资本表；Longbridge / yfinance 共识 | `n`；证伪：2027Q2 holdco CET1 仍 >17% → 延长 \(n\) 或说明 LPB 吸收 |
# | A6 | M/H 分子基年 FY2027E：共识 EPS **0.8226**（均值）/ **0.88**（上沿），10 家，区间 0.78–0.88（yfinance 2026-10-28，会后尚未刷新）；段前留存 = Q4'26 共识净利 $267.1M（Q3 实际 $241.0M 已在 09-30 账面）；无分红回购。**2026-10-27 削弱（数据将过期）**：管理层 FY27 指引 EPS ~0.90 / 调整净利 ~$1.28B 高于共识上沿；共识若移向指引（M 用 0.90、营收 +27%），M ≈ 11.9 | weakened | yfinance 2026-10-28；Longbridge 季度共识 2026-10-28；8-K / 电话会 2026-10-27 | `eps_27_m/h`、`rev_g_27`、`ni_q4e_26`；共识刷新后重设 |
# | A7 | **\(g = 4\%\)**（M/H 永续，美国消费信贷余额长期名义增速——Fed G.19 总消费信贷（FRED `TOTALSL`，月度季调）截至 2026-08 的年化增速：10 年 3.84% / 20 年 3.90% / 25 年 4.32% / 30 年 4.95%）；**\(g_L = 0\)**（信用周期坏 + 增长停滞） | active | FRED `TOTALSL`（Fed G.19 Consumer Credit，Total Consumer Credit Owned and Securitized），as-of 2026-08（取数 2026-10-19） | `g2`、`g2_l`；敏感性 3% / 5% |
# | A8 | \(r\) 由归篮给出 = 篮 5 大行 / 优质股份行 **11%**（A24）；存款利息是生意成本，非资本结构，整公司一腿、无分腿 | active | `gordon.BASKET_R`；A24 | `r_op` |
# | A9 | **L 账面标记（一次性）**：利率 +100bp → FV **−$1,041M**（公司披露，2026-06-30，未计对冲）；损失率回 3.8% = 现行 2.26% × 1.68 → 按「+10% → −$205.6M」线性外推 **−$1,401M**；TBV\(_L\) = $7,263M（TBVPS 5.60）。在 \(g=0\) 的 Gordon 里账面不进价格，只作 PB\(_L\) 与 ROTCE\(_L\) 的分母披露。**2026-10-27 削弱**：Q3 基准利率实际上行 76–90bp，FV 损失逾 $800M、对冲收益约 $734M，TBV 仍季增 $235M——毛敏感度大幅高估对冲后的账面冲击 | weakened | 10-Q Item 3（2026-06-30）；2024Q2 10-Q；电话会 2026-10-27 | `mark_rate`、`mark_credit`；线性外推为简化（公司声明非线性）；Q3 10-Q 出后重设并核对冲口径 |
# | A10 | **L 经常性冲击**：NII −$159M/年（+100bp，2026-06-30 披露）+ 个人贷损失率回 3.8% × $30.9B（3.8% − 2.26%）= −$476M/年；税后 −$495M（2026-06：−$364M）。**2026-10-27 削弱（NII 一项）**：利率实涨 76bp 的季度里净息差 +16bp、NII 季增 18%（混有规模增长，不是干净检验）；信用一项口径一致（报表口径对报表口径），冲击随余额变大、当期核销变低而加大 | weakened | 10-Q Item 3（2026-06-30）；8-K 2026-10-27 Lending 公允价值表与净核销表 | `nii_shock`、`pl_book`、`pl_loss_rate`、`nco_peak`；Q3 10-Q 出后重设 `nii_shock` |
# | A11 | 折现：M/H 终值折 \(n=1.25\) 年 @ \(r\)（2026-09-30 → 2028-01-01）；L 不折（当期账面上的经常性盈利） | active | 对话锁定；A25 时点对齐 | Formula |
# | A12 | 卖方 TP 只进映射：26 家均值 **20.28**（12–30）；LSEG 28 家中位 19.50；2026-10-26 Monness 首次覆盖买入 20 | active | Longbridge 机构评级 2026-10-27；Longbridge 新闻（LSEG / MarketBeat）2026-10-27 | 不反解进倍数；表2 场景列 |
# | A13 | Tech Platform 商誉 $1,364M（全公司 $1,425M）不在 TBV 内；减值只影响 GAAP 权益与一次性 EPS，不动锚点 | active | 10-Q Note 17；8-K 2026-10-27 | 无 |
# | A14 | **ROTCE ≈ r 歧义声明**（GAAP 口径）：GAAP ROTCE\(_{27}\) 10.2% 与 \(r\) 11% 差 0.8pp <3pp，由倍数反解 \(g\) 在 GAAP 口径不稳定；本框架分子为 OE（ROTCE\(_{OE}\) 15.7%），\(g\) 不从价格反解 | active | AGENTS.md well_conditioned | `g2` 来源层级（A7） |
# | A15 | **无未建模期权（期权上限 0）**：管理层 ROTCE 20–30% 目标无实测单位；SoFiUSD / Big Business Banking 无分子亦无实测上限锚；「再长一年」属同一分子延续（A22）→ 全部留 `stretched` 解释 | active | 纪要 98091；A2e-7b | 无表3 |
# | A16 | 利率情景与 `_AXIS.fed-path-*` 的 **L = 加息** 同 regime 命名，但**不正式挂轴**（现有轴只有商品价格梯，无 bp 梯）；本票 L 的 +100bp 由公司披露敏感度传导。2026-10-27 注：管理层 FY27 指引已假设 2027 年加息两次，Q3 基准利率实涨 76–90bp——加息从 L 的尾部情景变成指引主线；L 的 +100bp 叠在 FY26 运行率上，不与 M 的共识重叠 | active | 对话锁定（选项 a）；电话会 2026-10-27 | §1 属性 C |
# | A17 | **Owner earnings 定义**：\(OE = NI + GS\,(1-t)\)（M/H 用 FY27 税率 24%，L 用 FY26 22%），\(GS\) = 增长性获客支出 = 4 × [Lending 营销 × (1 − 48.5%) + FS 营销 × (1 − 50%)] = **$610.7M/年**（FY26 基）；FY27 按共识营收增速 +25.8% 放大为 **$768.0M**。营销费仍为 Q2 Note 17 值（Q3 10-Q 未出），方向确认：CEO 称营销线性加码而获客成本未加速 | active | 10-Q Note 17 费用行（2026Q2）；电话会 2026-10-27 | `gs_26`、`gs_27`；Q3 10-Q 出后重设 `lend_mkt_q` / `fs_mkt_q` |
# | A18 | **Lending 维护份额 48.5%**：维护性发起 = (个人贷 $30.9B × 49.0% + 学生贷 $18.1B × 14.1%)/4 = $4.42B/季，加 LPB $3.8B/季（COGS），÷ 总发起 $16.9B/季（2026-06：46.4%） | active | 8-K 2026-10-27 公允价值输入（CPR / 违约率）与发起量 | `maint_lend` 由 eval 从 `pl_book`/`pl_runoff`/`sl_book`/`sl_runoff`/`orig_q`/`lpb_q` 复算 |
# | A19 | **为 \(g\) 显式扣留存**（不让增长白拿）：\(E^{term} = OE_{27} - GS_{27}\cdot(g/g_{rev,27})(1-t)\)；\(b = g\cdot cet1_{tgt}\cdot RWA_T/E^{term}\)，\(RWA_T = (\text{CET1 资本} + NI_{H2'26} + NI_{27})/cet1_{tgt}\) | active | AGENTS.md「增长要靠留存资本换」 | Formula ②③ |
# | A20 | FS 维护份额 **50%**（会员/存款流失率未披露）→ `待补`；0% / 100% 对应 M 12.29 / 9.47 | active | 待补 | `maint_fs`；敏感性 |
# | A21 | 公司层面「其他公司及未分配」内的品牌营销（$150M/季，含 FDIC 保险等）**不加回**——无法拆分，偏保守 | active | 10-Q Note 17 注(2) | 无 |
# | A22 | **`stretched` 的升级门槛**：FY2028 出现 ≥2 家共识且 EPS/营收增速 ≥ +25% → 框架纠正：\(n\) 延至 FY28、分子换 FY28 区间；Piper 单家（营收 +22% / EBITDA +27%）只作 Outputs 的**共识升级候选带**（L′/M′/H′ = 5.70 / 12.93 / 13.52，「zone+窗口」第二口径，日报第三行；2026-10-27 管理层只给到 FY27，FY28 ≥2 家待卖方会后刷新），不进底牌、不进 zone 判定。它不是 \(V_{opt}\)：同一分子的延续、连续不二元、且底牌 \(g=4\%\) 已含 FY28 的 4%（再入期权即双计） | active | Longbridge 新闻 297819938（Piper）；2a 同源要求；A2e-7c | 触发后改 A5/A6，候选带升级为底牌并删除 |
# | A23 | **四个合法杠杆逐一交代（2026-10-28；11% 下读数）**：H/TP 均值 = 11.57/20.28 = 0.57。① Gordon 已是（g2 ±1pp → H 11.24 / 12.01，拧到 cap 6% 也只到 H 12.63；同业读数 NU / AXP 中位 3.75% 记录未采用，A7）；② g1 不可用（FY28 无 ≥2 家；n=1.25 是资本跑道）；③ V_opt 不可用（无实测单位，A15）；④ 候选带已入位（A22），H′ 13.52 / TP 均值 20.28 = 0.67；差额表只剩街倍数（TP 均值 = 24.7× FY27E，本仓 H = 13.2×）、管理层 ROTCE 20–30% 目标（A15）、FY28 之后的第二段（仅单家）三项，均刻意不承销；11% 下 M 分子上任何 \(g \le\) cap 都够不到 TP，TP 在为共识外的 FY28+ 增长与更低的 r 付钱 | active | A12 / A15 / A22；同业横截面 yfinance 2026-09-13 | 不改锚点 |
# | A24 | **归篮：整公司一腿 → 篮 5 大行 / 优质股份行 r = 11%**（2026-10-28 纠正归篮，按「③ 出带处理流程」步 3「初分本就不满足篮子判据 → 纠正归篮」，不经带）。**初分篮 6 为什么不成立**：篮 6 判据（2026-09-28 起）= 盈利是商品价函数（金属、能源、化工品、面板、运价……），只有周期、没有商品价函数的不进本篮，「小盘」不再是归篮理由；高 β 是价格波动、不是要求回报（2026-10-03）。初分的三条理由——无抵押消费信贷周期、β ≈ 2.1、小盘——均已被规则排除；SoFi 的利差由自己定价、核销是信用周期而非商品价。**篮 5 为什么成立**：判据 = 银行主尺启发式命中 ≥2 条——① 主业吸存放贷，关键驱动是 NIM（6.14%）、净核销、资本充足率（CET1 16.9%）；② 三个分部共用一张资产负债表（FS 的 NII 是 Lending 贷款的资金端，§1 属性 B）；（另有半条：卖方以整公司 PE 或 P·TBV 论证、无 SOTP）；持全国性银行牌照（SoFi Bank, N.A.），存款 $51.3B。无抵押消费信贷比综合性大行风险高、公允价值簿记放大利率波动、连续盈利仅 12 个季度——这些进 L 情景（A9 / A10），不在 r 里再收一次。**CAPM 粗筛 13.5%**（β 2.1 × ERP 4.5 + r\(_f\) 4.0），与篮 5 残差 +2.5pp < 3pp，不进篮子质疑清单。**③ 护栏在带内**：尺是 P/TBV，自身带 = P·TBV 实测带 [1.26, 2.03]；11% 下 PB\(_M\) 1.46 / PB\(_H\) 1.54 在带内，③ 不触发。带下沿 1.26×（2022-12）步 1b 核验仍判失真（FY22 ROE −7.5% / ROTCE ≈ −11.6%，市场当年买未来 ROTCE 20–30%），本版不依赖它。**留痕**：2026-09-20 初分篮 6；09-18 曾按「③ 出带降篮门」降篮 5 后因带失真于 09-19 撤回（见 §4 2026-09-20）——那次撤回的是「经失真带降篮」这条路径，不是篮 5 判据 | active | 银行主尺启发式（skill heuristics「银行 / 存款类主尺启发式」）；valuation-rules「§r 篮子」篮 5 / 篮 6 判据（2026-09-28、2026-10-03）；用户 2026-10-28 裁定；`gordon.BASKET_R`；`eval/SOFI.US.py` `check_r(r_op, 篮 5)`；LB 历史 PB / FY22 ROE | `r_op`；全公式（M/H 倍数 10.31× / 10.46×、折现 n、L 的 1/r = 9.09×）；**改判条件**：出现盈利随商品价变动的业务且占利润主体 → 回篮 6；业务转为非银行（放弃牌照、以出表为主）→ 重审篮 4。篮子值 **MUST NOT** 单票修改，能动的只有归属 |
# | A25 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」，2026-10-16 纠正：锚点不变）**：本票是银行 PB-ROE 尺（有形净资产口径 owner earnings），属该节「银行不适用」——不拆超额现金、不走稳态回报三段；只把时点对齐与窗口扩到银行。**时点对齐**：M / H 终值按 1.25 年 @ 11% 从 2026-09-30 资产负债表日折到 2028-01-01（资本跑道终点 = 分子 FY2027 之后的稳态起点，A11），等于规则的 τ = 1.25，已对齐（2026-10-27 财报滚动：1.5 → 1.25）；L 是当期运行率分子、g = 0，属当期年化，不适用。**窗口**（2026Q4 + FY2027 的 owner earnings 约 20.4 亿 = 1.57 / 股）：段一是「超额 CET1 16.9% → 16.0% 的资本跑道」，段一利润与超额资本一起被风险资产增长消化、不派出 → 窗口价值取 0，等价于段一利润全部留存（用户 2026-10-16 裁定按此主读；当时 13% 口径下「按 \(g_2\) 4% ÷ ROTCE 16.1% 取留存率 → 窗口 +1.36 / 股」不采用；按段一营收增速取留存率 > 1 的负窗口已由「窗口 < 0 截到 0」关闭）。无超额现金行、无少数股东；**k**：无 | active | 第 8 / 9 轮复核 2026-10-16；用户裁定 2026-10-16 | 无数值变动（结构）；现行 L/M/H 5.70 / 10.88 / 11.57 |
# 原框架历史，迁移不产生新的财务更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-09-20
# - v2 切换（篮子 r）：L/M/H v1 7.23 / 13.02 / 13.88 → 5.56 / 8.34 / 8.89，zone `stretched` → `stretched`；篮子：整公司一腿篮 6 周期商品 / 小盘 13%（v1 默认经营档 10%；无备选篮，CAPM 粗筛 13.5%）；M ×0.64 全部来自 r（M 倍数 12.19× → 8.13×，L 10× → 7.69×）；g2 4% / g_L 0 保留（cap 6% 未收紧，13% 下 g 对 M 无杠杆：±1pp → ±0.01，v1 12.41 / 13.87）；候选带 7.23 / 15.54 / 16.29 → 5.56 / 9.69 / 10.15，改「zone+窗口」第二口径披露；A23「接受溢价 24.8% / 6.3%」改为隐含 r(P) 8.8%（δ −4.2pp）披露、溢价 95% / 71%；③ 护栏：13% 下 PB 0.96 / 1.17 / 1.24 全低于自身 P·TBV 带底 1.26（v1 1.24 / 1.76 / 1.86 在带内），步 1b 判带下沿失真（2022-12 亏损年印出）→ ③ 不可判定，只披露、不降篮，走纠正对账门（M −36% vs v1，落 ② E_M/r 9.48 的 −12% 与 ⑥ TBVPS × 1.26 = 9.25 的 −10%，过门）；v1 口径其余对照：FS 维护份额 0% / 100% → M 14.70 / 11.34、g* 7.0%、GAAP 对照 M ≈ 7.6 / L ≈ 4.1；新增 A24 归篮、A8 改由归篮给出。`eval/SOFI.US.py` 改读篮子（`parse_baskets` + `check_r(r_op, 篮)` + `check_g_cap(g, r)`），打印隐含 r(P) 与地板披露。
#   - 路径留痕（2026-09-18 / 09-19）：09-18 首稿篮 6 → 同日按「③出带降篮门」降篮 5（11%）入带即停，底牌 6.58 / 11.01 / 11.74（PB\(_M\) 1.51 / PB\(_H\) 1.60；候选带 6.58 / 13.02 / 13.65；隐含 r δ −2.2pp）；09-19 用户裁决：步 1b 带有效性核验判 P·TBV 带下沿 1.26×（2022-12）失真——印在亏损年（FY22 ROE −7.5% / ROTCE −11.6%），市场当时买未来 ROTCE 20–30%，与现模型 ROTCE\(_{OE}\) 16.1% 差 ~24pp → 降篮 5 撤回，尺子回篮 6；篮 5 读数不进 zone，仅此处留痕。ticker-decisions 专属节 §SOFI.US（`_local/wiki`）记「篮 6 vs 备选篮 5 待」与「窗口口径 议」，以 09-19 裁决为准。
# - touched: [r 篮子, 锚点, 候选带, A8, A23, A24, Outputs 披露行, eval]
# ### 2026-10-27
# - 2026Q3 财报（8-K 2026-10-27 盘前、同日电话会）：调整净营收 $1,371M（+44%，共识 $1,264M）、GAAP 净利 $241.0M（共识 $226.5M）、EPS 0.18；会员 1,710 万（+35%）；发起 $16.9B（LPB $3.8B）；TBV $9,705M / TBVPS 7.48；holdco CET1 18.7% → 16.9%（RWA 季增 15%）；个人贷报表 NCO 2.26%（all-in 约 3.4%），FV 违约率假设 4.77% → 5.10%；基准利率 +76–90bp，FV 损失逾 $800M、对冲收益约 $734M，净息差 6.14%。FY26 指引上调到调整净营收 ~$5.04B / 调整净利 ~$840M；首次给 FY27：调整净营收 ~$6.4B、调整净利 ~$1.28B、EPS ~0.90（高于 10 家共识上沿 0.88；假设加息两次、税率 24%、不需再融资）。
# - 假设：A3 weakened（指引隐含约 14.2 亿股）· A4 weakened（超额资本 $1,316M → $523M；管理层资本率目标十几出头到十五左右）· A5 confirmed（消化快于路径）· A6 weakened（共识会后待刷新）· A9 weakened（加息实测、对冲后账面冲击远小于毛敏感度）· A10 weakened（NII 一项；信用冲击 −$308M → −$476M/年）；A16 / A17 / A18 / A22 / A23 / A25 数字滚动。
# - Inputs 滚动到 2026-09-30；公式机械更新：Q3 改实际净利、M/H 段前留存只剩 Q4、`n` 1.5 → 1.25、拆出 `tax_27` 24%（FY27 指引）。营销费拆分与利率 / 信用敏感度仍为 2026-06-30 值，待 Q3 10-Q。
# - 锚点：仅本次滚动（13% 下）5.56 / 8.34 / 8.89 → 4.82 / 8.28 / 8.80；现行 5.70 / 10.88 / 11.57（含同日归篮，A24）；候选带 → 5.70 / 12.93 / 13.52。卖方 TP 均值 20.34 → 20.28。
# - 价格：基准收盘 14.46（10-26），10-27 收 16.40（+13.4%，盘中最高 16.76）。
# - touched: [Inputs, Formula 步骤 1/4–6/8/14, eval, A2–A6, A8–A14, A16–A18, A20, A22–A25, 锚点, 候选带, 表1, 表2, 表2c, Outputs 披露行]
HISTORICAL_PARTIAL_FINGERPRINT = 'c3e4c19913cc4f8e9b622d54b6bde094e066e303c42220997b0cb024a1b7df05'

INPUTS = {
    # 期末普通股（M 股）；8-K 2026-10-27 TBV 表; 来源：2026-09-30
    'shares': 1296.617,
    # TBV = 11,295.137 − 1,425.159 − 208.093 + 43.074；8-K 2026-10-27 TBV 表; 来源：2026-09-30
    'tce': 9704.959,
    # holdco CET1 资本；8-K 2026-10-27 监管资本表（RWA 56,236.976）; 来源：2026-09-30
    'cet1_cap': 9520.479,
    # holdco CET1 比率; 来源：2026-09-30
    'cet1_ratio': 0.169,
    # 自身实测 CET1（2024-12 holdco）；A4; 来源：2024-12-31
    'cet1_tgt': 0.16,
    # 2026Q1 GAAP 净利；Longbridge; 来源：2026-03-31
    'ni_q1_26': 166.73,
    # 2026Q2 GAAP 净利; 来源：2026-06-30
    'ni_q2_26': 156.59,
    # 2026Q3 GAAP 净利；8-K 2026-10-27（只进 L 的 FY26 运行率；已在 09-30 账面内，不再计入 M/H 的段前留存）; 来源：2026-09-30
    'ni_q3_26': 240.989,
    # 2026Q4 共识净利；Longbridge（管理层电话会指引调整净利 ~270–276）; 来源：2026-10-28
    'ni_q4e_26': 267.094,
    # FY27 共识 EPS 下沿（坐标，不进 L 分子）；yfinance 10 家（会后尚未刷新）; 来源：2026-10-28
    'eps_27_l': 0.78,
    # FY27 共识 EPS 均值；**M**（管理层 FY27 指引 0.90 高于共识上沿，A6）; 来源：2026-10-28
    'eps_27_m': 0.8226,
    # FY27 共识 EPS 上沿；**H**; 来源：2026-10-28
    'eps_27_h': 0.88,
    # FY27 共识营收增速（6,141.4/4,883.4 − 1）；yfinance（管理层指引 6.4B/5.04B = +27%）; 来源：2026-10-28
    'rev_g_27': 0.2576,
    # Lending 直接广告 119.825 + 线索采购 89.006（Q2；Q3 10-Q Note 17 未出，`待补` 替换——Q3 合并销售与营销费 444.0 较 Q2 392.4 +13.2%）; 来源：2026-06-30
    'lend_mkt_q': 208.831,
    # FS 直接广告 3.659 + 线索采购 55.372 + 会员激励 31.357（Q2；同上待 Q3 10-Q）; 来源：2026-06-30
    'fs_mkt_q': 90.388,
    # 个人贷未偿本金；8-K 2026-10-27 公允价值表; 来源：2026-09-30
    'pl_book': 30902.941,
    # 个人贷年 runoff = CPR 0.2587 + 违约 0.0510 + 摊还 0.18；8-K 公允价值输入；A18; 来源：2026-09-30
    'pl_runoff': 0.4897,
    # 学生贷未偿本金; 来源：2026-09-30
    'sl_book': 18067.482,
    # 学生贷年 runoff = CPR 0.1017 + 违约 0.0089 + 摊还 0.03; 来源：2026-09-30
    'sl_runoff': 0.1406,
    # Q3 总发起量；8-K; 来源：2026-09-30
    'orig_q': 16932.283,
    # Q3 LPB 代发起量（计 COGS）；8-K; 来源：2026-09-30
    'lpb_q': 3800,
    # FS 维护份额；A20 `待补` 前占位; 来源：2026-09-12（对话锁定）
    'maint_fs': 0.50,
    # FY26 有效税率（管理层 FY26 指引）；只进 L（FY26 运行率）; 来源：2026-07-29
    'tax': 0.22,
    # FY27 有效税率（管理层 FY27 指引，电话会 2026-10-27；Q3 实测 24.2%）；进 M/H 与候选带; 来源：2026-10-27
    'tax_27': 0.24,
    # 整公司永续折现率 = **篮 5 大行 / 优质股份行 11%**（银行主尺启发式命中 ≥2 条：吸存放贷、驱动为 NIM / 净核销 / 资本充足率，各分部共用一张资产负债表；全国性银行牌照 SoFi Bank, N.A.；不是商品价函数 → 篮 6 判据不成立；值 = `gordon.BASKET_R`）；CAPM 粗筛 13.5%，残差 +2.5pp < 3pp；折现年数 n 同用本值；A8 / A24; 来源：2026-10-28
    'r_op': 0.11,
    # M/H 永续增速；**来源层级：无同业锚**（拟升级为具名宏观上限：Fed G.19 消费信贷余额长期名义增速，FRED `TOTALSL` 截至 2026-08 年化 10 年 3.84% / 20 年 3.90% / 25 年 4.32% / 30 年 4.95%，A7）；cap = min(6%, r − 4%) = 6% 未收紧；11% 下 ROTCE\(_{OE}\) − r = +4.7pp，留存换增长创值，M 对 g 中度敏感（±1pp → M 10.63 / 11.22，Outputs 敏感区行）。同业反解读数（yfinance 2026-09-13，同一把 Gordon 尺 r=10%）：NU 12.8× / ROE 31.6% → 2.9%、AXP 16.1× / 34.4% → 4.6%（数字银行 / 卡簇中位 3.75%）；SYF −3.8% / COF −1.5% / ALLY −5.3% / UPST −3.6%（消费信贷簇 <10× 全为负，作 `fast_grower` 同业不成立）——**是否改标「同业反解 3.75%」属用户裁定项，记录未采用**（M 约 −0.1）; 来源：2026-09-14
    'g2': 0.04,
    # L 永续增速（停滞）；A7；L 档 ROTCE 11.2% − r 11% = +0.2pp（贴 r），g=0 → 1/r = 9.09×; 来源：2026-09-12（对话锁定）
    'g2_l': 0.0,
    # 两段式段一年数（Q4'26 + FY27，2026-09-30 资产负债表日 → 2028-01-01）；A5 / A25；≤ 有共识的年数 2（FY26 / FY27）; 来源：2026-09-30
    'n': 1.25,
    # +100bp → NII 年冲击（税前）；10-Q Item 3; 来源：2026-06-30
    'nii_shock': 159.004,
    # 个人贷年化 NCO（2026Q3 报表口径，含不良出售；剔除后 all-in 约 3.4%）；与 `nco_peak` 同口径（2024Q2 报表 3.8% 亦含不良出售，剔除后约 5.4%）; 来源：2026-09-30
    'pl_loss_rate': 0.0226,
    # 个人贷 NCO 实测峰（2024Q2）; 来源：2024-06-30
    'nco_peak': 0.038,
    # +100bp → 公允价值一次性标记（披露）; 来源：2026-06-30
    'mark_rate': 1040.813,
    # 损失率 +10% → 公允价值一次性标记（披露）; 来源：2026-06-30
    'credit_sens_10': 205.583,
    # FY27 共识营收 $M（候选带用）；yfinance; 来源：2026-10-28
    'rev_27': 6141.4,
    # Piper FY28 营收增速——**单家，只进候选带，不进底牌**（A22）; 来源：2026-08
    'piper_rev_g_28': 0.22,
    # 自身实测增量调整净利率（9M'26，Q3 单季 25%）；8-K 非 GAAP 表（管理层 FY27 指引 32%，不采用）; 来源：2026-09-30
    'incr_ni_margin': 0.24,
    # 卖方 TP 均值（映射用）；Longbridge 26 家; 来源：2026-10-27
    'seller_tp_mean': 20.28,
    # 卖方 TP 下沿; 来源：2026-10-27
    'seller_tp_lo': 12.00,
    # 卖方 TP 上沿; 来源：2026-10-27
    'seller_tp_hi': 30.00,
}
BASKETS = {"r_op": 5}  # deposit-funded lending, original A24
REQUIRED = frozenset(INPUTS) - {"seller_tp_hi", "seller_tp_lo", "seller_tp_mean"}

def maint_lend_of(inp: dict[str, float]) -> float:
    maint_orig_q = (inp["pl_book"] * inp["pl_runoff"] + inp["sl_book"] * inp["sl_runoff"]) / 4.0
    return (maint_orig_q + inp["lpb_q"]) / inp["orig_q"]


def growth_spend_26(inp: dict[str, float], maint_lend: float) -> float:
    return 4.0 * (inp["lend_mkt_q"] * (1.0 - maint_lend) + inp["fs_mkt_q"] * (1.0 - inp["maint_fs"]))


def tier_mh(inp: dict[str, float], eps27: float, gs27: float, g: float) -> dict[str, float]:
    """One M/H tier: returns price per share plus the disclosed intermediates.

    The balance sheet (tce, cet1_cap) is at 2026-09-30, so only Q4'26 is still to be
    retained before the FY27 terminal year.
    """
    ni27 = eps27 * inp["shares"]
    return _terminal(inp, ni_term=ni27, gs_term=gs27, rev_g_term=inp["rev_g_27"], g=g,
                     retained_before=inp["ni_q4e_26"], n=inp["n"])


def _terminal(inp: dict[str, float], *, ni_term: float, gs_term: float, rev_g_term: float,
              g: float, retained_before: float, n: float) -> dict[str, float]:
    """Gordon terminal on owner earnings of the stage-end year, discounted n years.

    `retained_before` is the NI retained between today and the terminal year's
    opening balance; the terminal year's own NI is added on top for TCE_T / RWA_T.
    """
    t, r = inp["tax_27"], inp["r_op"]
    oe = ni_term + gs_term * (1.0 - t)
    e_term = oe - gs_term * (g / rev_g_term) * (1.0 - t)
    rwa_t = (inp["cet1_cap"] + retained_before + ni_term) / inp["cet1_tgt"]
    b = g * inp["cet1_tgt"] * rwa_t / e_term
    mult = (1.0 - b) / (r - g)
    tv = mult * e_term
    tce_open = inp["tce"] + retained_before
    tce_t = tce_open + ni_term
    return {
        "ni27": ni_term, "oe27": oe, "e_term": e_term, "rwa_t": rwa_t, "b": b,
        "mult": mult, "tv": tv, "tce_t": tce_t,
        "rotce_oe": oe / (0.5 * (tce_open + tce_t)),
        "pb_t": tv / tce_t,
        "price": tv / inp["shares"] / (1.0 + r) ** n,
    }


def fy28_coordinate(inp: dict[str, float], eps27: float, gs27: float, g: float) -> dict[str, float]:
    """A22 coordinate band (single-house Piper FY28 × own realized incremental NI margin).

    Reference only — never an anchor, never a zone input.  Same terminal mechanics
    as M/H with the stage stretched one year (n + 1) so the two bands are comparable.
    """
    ni_q4 = inp["ni_q4e_26"]
    ni27 = eps27 * inp["shares"]
    d_rev_28 = inp["rev_27"] * inp["piper_rev_g_28"]
    ni28 = ni27 + inp["incr_ni_margin"] * d_rev_28
    gs28 = gs27 * (1.0 + inp["piper_rev_g_28"])
    out = _terminal(inp, ni_term=ni28, gs_term=gs28, rev_g_term=inp["piper_rev_g_28"], g=g,
                    retained_before=ni_q4 + ni27, n=inp["n"] + 1.0)
    out["rwa_g_28"] = out["rwa_t"] / ((inp["cet1_cap"] + ni_q4 + ni27) / inp["cet1_tgt"]) - 1.0
    return out


def tier_l(inp: dict[str, float], gs26: float) -> dict[str, float]:
    t, r = inp["tax"], inp["r_op"]
    ni_26 = inp["ni_q1_26"] + inp["ni_q2_26"] + inp["ni_q3_26"] + inp["ni_q4e_26"]
    oe26 = ni_26 + gs26 * (1.0 - t)
    uplift = inp["nco_peak"] / inp["pl_loss_rate"] - 1.0
    d_credit = inp["pl_book"] * inp["pl_loss_rate"] * uplift
    oe_l = oe26 - (inp["nii_shock"] + d_credit) * (1.0 - t)
    mark_credit = inp["credit_sens_10"] * uplift / 0.10
    tce_l = inp["tce"] - inp["mark_rate"] - mark_credit
    price = oe_l / (r - inp["g2_l"]) / inp["shares"]  # g2_l = 0 → 1/r
    return {
        "ni_26": ni_26, "oe26": oe26, "d_credit": d_credit, "oe_l": oe_l,
        "mark_credit": mark_credit, "tce_l": tce_l,
        "rotce_l": oe_l / tce_l, "pb_l": price * inp["shares"] / tce_l, "price": price,
    }



def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    r, g, t = inp["r_op"], inp["g2"], inp["tax"]
    # valuation-rules.md「§r 篮子」: r is the named basket's value (A24), never a per-ticker dial.
    baskets = BASKETS
    if "r_op" not in baskets:
        errors.append("r_op: Inputs source cell names no 篮 N (A24 归篮)")
    errors += check_r(r, "r_op", baskets.get("r_op"))
    # valuation-rules.md「永续增长口径」: perpetual g capped by g_cap(r); stage one bounded by consensus years.
    errors += check_g_cap(g, r, "g2")
    errors += check_g_cap(inp["g2_l"], r, "g2_l")
    errors += check_transition_years(ceil(inp["n"]), CONSENSUS_YEARS, "n")
    if r - g <= 0:
        errors.append(f"g2={g} must be < r={r}")
    if inp["g2_l"] != 0.0:
        errors.append("g2_l must be 0 — L world is defined as growth stall (A7)")
    if not 0.0 < inp["maint_fs"] < 1.0:
        errors.append(f"maint_fs={inp['maint_fs']} must lie in (0,1)")
    if inp["nco_peak"] <= inp["pl_loss_rate"]:
        errors.append("nco_peak must exceed pl_loss_rate — L is a credit *deterioration*")

    # A18: maintenance share is recomputed from the fair-value model inputs, never typed in.
    maint_lend = maint_lend_of(inp)
    if not 0.0 < maint_lend < 1.0:
        errors.append(f"maint_lend={maint_lend:.3f} out of (0,1)")
    maintenance_changed = abs(maint_lend - MAINT_STATED) > MAINT_TOL

    gs26 = growth_spend_26(inp, maint_lend)
    gs27 = gs26 * (1.0 + inp["rev_g_27"])

    tl = tier_l(inp, gs26)
    tm = tier_mh(inp, inp["eps_27_m"], gs27, g)
    th = tier_mh(inp, inp["eps_27_h"], gs27, g)
    for lab, tier in (("M", tm), ("H", th)):
        if not 0.0 < tier["b"] < 1.0:
            errors.append(f"retention b_{lab}={tier['b']:.3f} out of (0,1)")
    if tl["oe_l"] <= 0:
        errors.append(f"OE_L={tl['oe_l']:.1f} must be positive")

    # A2e-2c: the ladder must already stand in the numerators.
    errors += ladder("numerator OE_L < E_term_M < E_term_H", tl["oe_l"], tm["e_term"], th["e_term"])
    errors += ladder("ROTCE", tl["rotce_l"], tm["rotce_oe"], th["rotce_oe"])
    if errors:
        raise ValueError("; ".join(errors))

    L, M, H = tl["price"], tm["price"], th["price"]
    if not (L < M < H):
        raise ValueError(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    A, B = cut_points(L, M, H)


    # flat-multiple check: every tier on mult_M; L also pays for g's growth spend and is discounted.
    disc = (1.0 + r) ** inp["n"]
    e_l_flat = tl["oe_l"] - gs26 * (g / inp["rev_g_27"]) * (1.0 - t)
    L_flat = e_l_flat * tm["mult"] / inp["shares"] / disc
    H_flat = th["e_term"] * tm["mult"] / inp["shares"] / disc
    if not (L_flat < M < H_flat):
        errors.append(f"flat-multiple ladder failed: {L_flat:.2f} / {M:.2f} / {H_flat:.2f}")

    x_excess = inp["cet1_cap"] - inp["cet1_tgt"] * inp["cet1_cap"] / inp["cet1_ratio"]

    # Disclosure only (A24 / Outputs): the band-low check is ③ 护栏 read on M/H only (L is
    # *built* to sit at the tested trough).  The 2022-12 band low printed in a loss year
    # (1b 失真), so a reading below it would be disclosed, not a downgrade trigger.
    mh_ok = all(PB_BAND[0] <= pb for pb in (tm["pb_t"], th["pb_t"]))
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves r_op
    # 1:1 — the L 1/r multiple, the M/H Gordon multiple and their n-year discount —
    # while numerators, g and the CET1 retention stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        inp_dr = {**inp, "r_op": r + dr}
        return (
            tier_l(inp_dr, gs26)["price"],
            tier_mh(inp_dr, inp["eps_27_m"], gs27, g)["price"],
            tier_mh(inp_dr, inp["eps_27_h"], gs27, g)["price"],
        )

    # A22 candidate is computed independently from the base anchors.
    cm = fy28_coordinate(inp, inp["eps_27_m"], gs27, g)
    ch = fy28_coordinate(inp, inp["eps_27_h"], gs27, g)
    cand = (L, cm["price"], ch["price"])  # L′ = L: the L world carries no transition
    if not cand[0] < cand[1] < cand[2]:
        errors.append("candidate ladder collapsed")
    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    maintenance = []
    for fsm in (0.0, 1.0):
        gs = 4.0 * (inp["lend_mkt_q"] * (1-maint_lend) + inp["fs_mkt_q"] * (1-fsm)) * (1+inp["rev_g_27"])
        maintenance.append(tier_mh(inp, inp["eps_27_m"], gs, g)["price"])
    growth = [[tier_mh(inp, inp[f"eps_27_{k}"], gs27, gg)["price"] for k in "mh"] for gg in (0.03, 0.05)]
    result = {
        "ticker": "SOFI.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-09-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-28', 'historical_framework_as_of': '2026-10-28',
        "anchors": band((L, M, H)),
        "candidate": {"label": "Piper 2028 收入增长估计", "anchors": band(cand)},
        "option": None, "cut_points": [A, B],
        "maint_lend": maint_lend, "gs26": gs26, "gs27": gs27,
        "tl": tl, "tm": tm, "th": th, "x_excess": x_excess,
        "L_flat": L_flat, "H_flat": H_flat, "mh_ok": mh_ok,
        "cm": cm, "ch": ch,
        "parameters": {"discount": r, "growth": {"L": inp["g2_l"], "M": g, "H": g},
                       "return": {"L": tl["rotce_l"], "M": tm["rotce_oe"], "H": th["rotce_oe"]},
                       "retention": {"M": tm["b"], "H": th["b"]}},
        "sensitivity": {"maintenance": maintenance, "growth": growth},
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if r + dr <= g:
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_op': r}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    result['maintenance_assumption_changed'] = maintenance_changed
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'baskets': BASKETS, 'maintenance_reference': MAINT_STATED,
         'maintenance_tolerance': MAINT_TOL, 'pb_band': PB_BAND,
         'consensus_years': CONSENSUS_YEARS}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments'] = {'company': {'unit': 'USD_PER_SHARE', 'values': dict(result['anchors'])}}
    parameters = result['parameters']
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'])},
        'growth_rate': {'unit': 'RATIO', 'values': parameters['growth']},
        'forward_return': {'unit': 'RATIO', 'values': parameters['return']},
    }
    result['review_flags'] = ['historical_financial_services_maintenance_estimate',
                              'historical_credit_and_interest_sensitivity_unverified',
                              'historical_pb_reference_only_checked_at_lower_edge']
    if result['maintenance_assumption_changed']:
        result['review_flags'].append('lending_maintenance_assumption_changed')
    return result
