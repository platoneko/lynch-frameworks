#!/usr/bin/env python3
"""MSFT legacy valuation; this migration does not update assumptions.

Amounts are USD millions except capex_fy26 (USD), shares millions. The lab
share and Azure segment margin are research estimates, not company disclosure.
"""
from __future__ import annotations
from lib.gordon import check_basket_pair, check_g_cap, check_k_declared, check_r, payout, perpetual_pe
from lib.inputs import require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'),
                'axes': {'lab': 'frontier_lab_funding', 'capex': 'ai_capex'}}

FORMULA_ID = "msft_fwd_numerator_gordon_ai_dc_openai_v1"
TOL = 0.05
MIN_R_MINUS_G = 0.02
K_LADDER_TOL = 1e-4
IC_SENSITIVITY = (1.20, 1.40)
MAX_LEG_ROE = 0.60
LISTING_CCY = "USD"
# | A1 | 林奇主类 `stalwart` + 次类 `fast_grower`：利润基座是 15–18% 增速的成熟软件（软件 + D&C 占 OI 69%），Azure +41% 与 RPO +84% 在拉整体到 18–20%；单一 `stalwart` 低估分子增速，单一 `fast_grower` 掩盖 69% 利润来自成熟块 | active | 10-K FY2026；yfinance 共识 FY27E 收入 +17.8% / FY28E +19.5% | 主尺骨架；L 按 `stalwart` 取共识下沿、不退利润率 |
# | A2 | **分子年份 = FY2028E 共识区间**：最远的、仍有 ≥2 家且带区间的共识年（33 家，22.03–25.68）；FY2028 年初的值按时点对齐折回 1 年（A16）。桥的基座 = FY26 非 GAAP EPS 17.28（与共识同为整公司 GAAP 口径、剔 OpenAI 项）；\(k_{eps}\) = 1.275 / 1.371 / 1.486；FY27 未入账年按 FY27E 19.76 ÷ 17.28 = 1.1435 滚。2026-10-30 读数与 7 天前几乎相同——卖方尚未按 FY27 Q1（Azure +48%、Q2 指引 +49–50%）改模型，下一轮修订后重拉 | active | yfinance earnings_estimate 2026-10-30（FY27E 19.76，34 家；FY28E 22.03/23.69/25.68，33 家；2026-09-21 为 20.93/23.59/26.00） | `k_eps_*`、`eps_fy28e_*`、`eps_fy27e` |
# | A3 | 正常化税率 **19.21%** = FY26 有效税率剔除 OpenAI 项：(32,185 − 1,567) ÷ (165,934 − 6,530)。FY27 Q1 有效税率 20.3%（9,324 ÷ 45,953；10-Q 归因于股权激励税收抵扣减少与地区结构），一季不改输入；下季仍 >20% 则改（+1pp ≈ 中档 −5） | weakened | 10-K FY2026 非 GAAP 对账；10-Q FY27 Q1 Note 10 | `tax_rate` |
# | A4 | **Azure 留存回报率 = 新投资本的边际稳态 ROIC，不是平均 ROE**：Gordon 的 b = g/ROE 量的是「为增长留下的钱按什么回报率再投」，Azure 的增量资本是数据中心，回报率取投产后第 2–3 年的稳态（valuation-rules「ROE_proj 一律取稳态，不取首年」）。来源层级：① 汇丰 2027E Azure ROIC **14.6%**（99586）→ 底牌；② 卖方 FY26 → FY28 共识隐含边际约 20% → 上界敏感行；③ 实测首年（智能云 FY25 → FY26）≈ 10% → 下界敏感行。软件腿与 D&C 增长几乎不要资本，用自己的快照 ROE。FY2028 年初资本按 b1 = g/ROE 滚未入账 FY27（与 GOOG A25 同口径）；capex 潮实际留存远大于此，+20% / +40% 敏感行（`ic_fy28_path` 待补） | active | Wisburg 99586；10-K FY2025 / FY2026 分部与固定资产 | `roic_marg_az`；Azure 两子腿倍数 |
# | A5 | **Azure 利润率与 OI 份额是代理值**：Azure 独立 OI 不披露；用 FY26 智能云分部利润率 41.3% × 重述 Azure 收入 1,019 亿 = Azure OI 421 亿 = A&I OI 的 30.9%；其余 69.1% 归软件腿。**FY27 Q1 首份新口径财报**：A&I OI 份额 88.3%（vs 88%，不重算）；Azure 收入 33,165（+48%）；Microsoft Cloud 毛利率 66%（结构向 Azure 倾斜，Azure 单品毛利改善）；A&I 分部利润率 52.8%（上年同期 53.1%）。Azure 独立利润率仍 `待补` | active | 花旗 103969 / 大摩 103949（重述数）；10-K FY2026 | `rev_azure_fy26` / `oi_ic_fy26` / `rev_ic_fy26` |
# | A6 | **归篮**：Azure 非 OpenAI 子腿 / 软件腿 / D&C → **篮 4 龙头制造 10%**（企业软件与云基础设施龙头，常规经营现金流）；Azure OpenAI 子腿 → **篮子对**（`valuation-rules`「篮子对」，2026-09-23）：**过渡篮 7 单押 / 故事 15%**（判据「收入依赖对手方未落定融资」：OpenAI 2,500 亿 Azure 承诺 vs 其到 2030 年 2,800 亿累计烧钱；单一客户 ≥50% 的收入判据不触发（FY26 7.3%、FY27 Q1 10.8%），触发的是融资判据，与 `ORCL.US` A7 同一条理由）→ **终值篮 4 10%**（OpenAI 做成了的世界里是用自身收入付账的超大客户；稳态特征、共用 k_lab 0.30、合篮条件由 `_AXIS.frontier-lab-funding` §3 一次定义）。本腿单段 Gordon，**到达风险全部在 k_lab**。**本票第二层**：OpenAI 的 2,500 亿承诺 vs 2,800 亿累计烧钱是轴 §3a 第 1 条（\(c \ge 1\)）今天不满足的直接读数；「微软投钱 → OpenAI 付给 Azure」的循环若结构性延续，即轴 §3c 合篮情形。**禁双计声明**：OpenAI 股权的折价带（L 60% / M 40% / H 20%）定价持股，k_lab 定价收入子腿，同一事件打两条现金流，各计一次；L 档（共识低端）不含 OpenAI 断供情景，不与 k_lab 重叠。**份额 30.2%**（2026-10-30 起）= 10-Q FY27 Q1 披露的单季 OpenAI 收入 100 亿 ÷ 当季 Azure 收入 331.65 亿；含收入分成（不全是 Azure），是偏高读法，按「边界判断取更严」采用；FY26 均值 23.6%（241 亿 ÷ 1,019 亿）降为敏感行，35% 为承诺爬坡敏感行。融资判据仍触发：新一轮约 300 亿在谈未成交，应收 OpenAI 一季 +20%（60 → 72 亿）。Anthropic 承诺 2026-11 到 2033-05 至少 449 亿微软算力（Fortune 2026-10-28 转述），不进份额。CAPM 粗筛 = USD \(r_f\) 中枢 4.0% + β 1.108 × 4.5% = **9.0%**，与篮 4 偏离 −1.0pp，不进质疑清单 | active | 10-K FY2026 / 10-Q FY27 Q1 关联方披露；news 299502100（OpenAI 现金消耗）；yfinance β；`_AXIS.frontier-lab-funding` §3 | `r_perp` / `r_az_lab` / `r_az_lab_t` / `k_lab`；`share_openai_az`、`rev_openai_fy26` |
# | A7 | **永续 g**：A&I（Azure 两子腿 + 软件腿共用）**6.0%** = 云同业市价反解（汇丰隐含 2028E EV/EBIT 经本仓 Gordon 单位反解：Azure 7.02% / AWS 7.26% / GCloud 3.97%，中位 7.02%）截到 \(G_{cap}\) = 6%；软件腿共用同一 g 是简化（M365 商业云 +17–18%、Copilot 席位 3,000 万），单独反解无同业锚；D&C **2.5%** 无同业锚·自定（Windows OEM 持平、Xbox −5%、搜索广告 +高个位数，±1pp 敏感行）。b 交叉里生产力腿 5.5%（借 GOOG A21 广告平台簇中位） | active | GOOG.US A7 横截面；10-K FY2026 | `g2_ai` / `g2_dc` / `g_b_pbp` / `g_b_mpc` |
# | A8 | **留存去向审计：E 桶**（capex 持续远大于折旧、无终点：FY2018 → FY2026 capex 116 → 1,159 亿，固定资产 295 → 3,131 亿）→ 完整式；「模型视同派出、实际留存的现金」按前瞻分子形态只算未入账 FY27：(1 − 实付派息 22.7% − b1) × 未入账 NOPAT。**打折 k：原 0.15 / 0.15 / 0.15，2026-10-16 去掉（k = 0，A17）；下面的推导留作记录**（来源 ①：FY22–26 现金用途 = capex 2,730 亿 + 收购 1,005 亿（动视 691、Nuance 220）+ 回购 1,129 亿；动视第 3 个完整年 Xbox 内容收入 −5%、交易 ROIC 约 3–4% → 该份额 k ≈ 0.65；回购价对应盈利收益率 3.3% + g 6% ≈ 9.3% 略低于 r → 0.07；capex 投 Azure 边际 14.6% ≥ r → 0；按金额加权 ≈ 0.15；H/M 差不来自价格轴，①b 不适用，三档同）。**杠杆门未触发**：净债（长期债务 403 + 融资租赁 788 + 流动租赁 97 + 经营租赁 219 − 现金及短投 768）= 739 亿 / FY26 EBITDA 1,942 亿 = **0.38**；利息 31 亿 / EBIT 1,552 亿 = **2.0%** | active | SEC XBRL companyfacts（FY2018–2026）；10-K FY2026 | `payout_3y` / `k_*`；`net_debt_ebitda` / `interest_ebit` |
# | A9 | **资产腿口径**：OpenAI 股权 = 24%（10-Q FY27 Q1「as-converted 约 24%」，FY26 末约 25%）× 上一轮 post-money 8,520 亿（2026-03，news 299051289；在谈新一轮成交前不换）= 2,045 亿；账面 120 亿（权益法）；递延税按内含收益 × 21%；折价带 L 60% / M 40% / H 20%（私募、无 IPO 计划、利润分成上限等持有条款未披露 `待补`、正在谈 1.2 万亿新一轮）。其他股权投资 152 亿（Anthropic、Inflection 等，替代计量法 124 亿 + 上市 27 亿）按账面、同折价带。上市权益证券已在其中，不进净现金 | active | 10-K FY2026（股权投资 272.4 亿 = 权益法 120 + 替代计量 124 + 其他）；10-Q FY27 Q1 关联方；news 299551341 | `openai_*` / `other_eq_inv` / `dtl_rate` / `d_oai_*` |
# | A10 | **折旧滞后 — 采用前瞻分子的前提**：FY26 折旧摊销 390 亿 vs capex 1,159 亿（3.0×），当期分部利润只背已投产资产的折旧；采用 FY2028E 共识分子的前提是卖方模型已建 capex（美银 2027E FCF 324 亿隐含 capex 约 1,700 亿+）、对应折旧在其 EPS 里。**证伪触发器**：capex 指引不变或上调、而 FY28E 共识 EPS 被下修 >10% → 退回 trailing 分子；Microsoft Cloud 毛利率连续两季跌破 65% → 处置。**FY27 Q1 读数**：两条都未触发——资本开支没减（2026 自然年约 1,700 亿，7 月指引约 1,750 亿；减量来自第三方机房交付推迟到下半年），FY28E 共识均值反升（23.59 → 23.69）；Microsoft Cloud 毛利率 66%，离 65% 线 1pp | active | 10-K FY2026 现金流量表；美银 103650；10-Q FY27 Q1；电话会转述（24/7 Wall St.、Fortune 2026-10-28） | `k_eps_*` 前提 |
# | A11 | **自身实测带作护栏**：Longbridge 5 年月度 trailing PE [22.80, 39.39]、p50 33.31（分母 GAAP EPS，含 OpenAI 项但量级小，带干净）；H = 27.1× 当期核心 EPS 在带内，余量 12 turns；M 24.9× 低于 p50（无超额现金，经营口径与整个股权口径相同） | active | Longbridge valuation --history 2026-09-21 | `pe_own_top` / `pe_own_p50` |
# | A12 | **挂载 `_AXIS.ai-capex.md`，身份构成方**：FY26 capex 1,159 亿（现金口径，另有融资租赁新增）在轴的基数里；FY27 指引只说「增速高于 FY26」，数字 `待补`；FY27 Q1 电话会：Q1 资本开支含融资租赁 452 亿（+30%；现金口径 394 亿，上年同期 194 亿），Q2 >500 亿，下半年加速（CPU / GPU、内存与存储涨价、推迟的第三方交付），2026 自然年约 1,700 亿，FY27 全年自由现金流为正（有报道称 1,700 亿指 2027 自然年，待纪要原文核实）；L 档不得比轴 L 档（2027 仍 +32%）更悲观 | active | 10-K FY2026；Q4 FY26 call；10-Q FY27 Q1；Q1 FY27 call 转述 | `capex_fy26` |
# | A13 | **无期权、无候选带**：FY2028E 已是分子年；无 ≥1 家明确的 FY2029E 点估计；Copilot / agent 平台的增量已在 M365 商业云共识里，不另开腿（防双计） | active | yfinance 2026-09-21 | `v_opt` |
# | A14 | **b 交叉的边界**：FY26 旧三分部各配自己的 g 与分摊资本（生产力 5.5% / 智能云 6.0%（OpenAI 子腿 22.3% = 主尺份额换算到智能云，篮子对 7→4 × (1−k_lab)）/ 个人计算 2.5%），智能云腿同样按边际 14.6% 留存。生产力腿分摊 ROE 76% > 60% 门槛 → 分摊法给它的资本偏少，b **只作交叉**；落盘只报 b 带与主尺 M 的差（锚点对锚点）；用现价把两把尺各自归档、比差几档只在研究对话里做（`AGENTS.md`「现价 — 禁写契约」） | active | 10-K FY2026 Note 8（分部商誉）；9/9 分摊脚本 | `oi_pbp_fy26` / `oi_mpc_fy26` / `ic_pbp` / `g_b_*` |
# | A15 | **股本**：`shares_diluted` = 7,453M（FY26 稀释加权）；FY26 回购 223 亿、发行 SBC 后股数基本持平 | active | 10-K FY2026 | `shares_diluted` |
# | A16 | **超额现金、增长期资金缺口与时点对齐**（valuation-rules「经营价值与超额现金」① / ③，框架纠正 2026-10-16）：闭合项净现金 365 亿（现金及短投 − 长期债务）= 归母权益约 10%，低于 15% 门槛，不另拆超额现金；现框架已把净现金按面值单列、分子是分部经营利润（不含利息），按「保留原结构」不动；股权投资是资产腿。归母比例 1.0（无少数股东）。**增长期资金缺口 = 0**：FY27 现金资本开支（共识含融资租赁 2,207 亿 × 现金部分 0.797）由同期经营现金流（约 1,990 亿）付得起；故窗口可分配利润照计（FY27 Q1 实测：经营现金流 580 亿 > 现金资本开支 394 亿）。**时点对齐**：τ = 2026-06-30 → FY2028 年初 2027-07-01 = **1.0 年**；Azure 非 OpenAI / 软件 / D&C ÷ 1.1，OpenAI 子腿按篮子对过渡篮 ÷ 1.15；**窗口可分配利润** = 未入账 FY27 各腿利润 × (1 − 该腿滚动用的 b1 = g / 留存回报)，按 τ/2 折今 = **14.62 / 14.74 / 14.87**；资产腿与闭合项不折。原框架无折回 | active | 10-K FY2026；卖方 FY27 资本开支与经营现金流共识；框架纠正试算 2026-10-16 | `tau`；窗口行 |
# | A17 | **稳态回报三段与打折 k**（valuation-rules「经营价值与超额现金」② / ④）：可见年 FY2028 用前瞻回报 → 默认路径 **Y1 = 可见年末 FY2028**（云厂商不继承 `_AXIS.ai-capex` 的高回报期）→ 线性回落 → **Y2 FY2034**（A&I 软件进入门槛判「高」，回落 6 年：企业软件的客户迁移与认证周期长达数年（M365 / Azure 的合同与数据迁移成本）；近十年办公套件份额没有被新进入者实质撼动）。**A&I 其余软件腿（稳态回报按序取，2026-10-19 规则）**：**自身周期可用 → 取自身 50.3%**。微软不是周期股、没有明显谷底，按近 5 个完整财年取均值：FY2022–2026 投入资本口径（税后 GAAP 经营利润 ÷ 年初〔权益 + 有息负债 + 经营与融资租赁 − 现金及短投〕；经营所需现金锚 0）逐年 77.1 / 51.2 / 51.3 / 37.3 / 34.7%（10-K XBRL，`_local/tmp/round9/sweep/LLY.US/ic.py 789019 --cash-combined`）。取 5 年而不取 9 年（FY2018–2026 均值 65.3%）：更早几年净现金极多、投入资本很小，读数虚高；5 年读数已含 FY2024 起 AI 资本开支把分母撑大的年份，又是公司合并口径（含重资产的 Azure 与动视商誉），对只装 M365 等软件的这条腿是更严的读法。旧版以「历史只有 GAAP 净利 ÷ 权益、公式不同」弃用自身周期，不成立，改正。成熟软件同业（INTU 35.9% / CHKP 42.1% / OTEX 12.8% / DOX 20.6%，中位 28.3%）与兜底「边际成本近零」30% 只作对照。每档稳态 = min(该档前瞻, 50.3%)：L / M / H 前瞻 53.6 / 57.9 / 63.0%（2026-10-30 共识）都在 2028 → 2034 回落到 50.3%。**Azure 两子腿**：留存回报本就是卖方的边际稳态 ROIC 14.6%（A4），低于稳态，路径平；**D&C**：前瞻 12.8–15.0% 低于稳态，路径平。g 不重解：A&I 6% 是同业反解截顶，按新路径重解只会更高，仍截在 6%；D&C 2.5% 是自定。不属于商品腿豁免。**打折 k 去掉**：原 0.15（A8）乘在「视同派出」行、即整个多留部分上，不是具名交易——经营价值的再投资回报已在回报里，多留部分落在现金上归 λ（λ = 1，无「钱回不到股东」的具名证据），k_l / k_m / k_h = 0；视同派出行 10.97 / 11.10 / 11.23 只披露。**k_lab 0.30 保留**：篮子对规则强制的显式到达折扣，乘在具名的 OpenAI 收入子腿上 | active | 10-K XBRL FY2021–2026（2026-10-19）；成熟软件同业年报与兜底表只作对照；框架纠正试算 2026-10-16 | `t0`、`y1`、`y2`、`ronic_ss_rest`、`k_*`；软件腿倍数 |
# 原框架历史，本次迁移没有新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-10-30
# FY27 Q1 财报（2026-10-28 盘后，季末 2026-09-30）后核对。touched: [A2, A3, A5, A6, A9, A10, A11, A12, A16, A17, §0, §1 属性 C / D / E, `share_openai_az`（新增）, `openai_stake`, `eps_fy28e_*`, `k_eps_*`, eval 份额口径与敏感行]
# - **本季**（10-Q FY27 Q1 / 8-K）：收入 922.8 亿（+19%），经调整 EPS 4.89（+18%，共识约 4.73）；A&I OI 405.58 亿 = 88.3%（新口径首次核对通过）；Azure 331.65 亿（+48%，指引 44–45%）；Microsoft Cloud 毛利率 66%；商业 RPO 6,770 亿（+73%）；有效税率 20.3%；经营现金流 580 亿、现金资本开支 394 亿；未起租租赁 3,646 亿。指引（电话会转述）：Q2 收入 960–971 亿、Azure +49–50%（固定汇率）、资本开支 >500 亿且下半年加速、营业利润率同比小降、FY27 自由现金流为正。
# - **OpenAI**：单季收入 100 亿 = 10.8% 收入 / 30.2% Azure（FY26 23.6%）→ 份额输入改为季度读数、FY26 均值降为敏感行；持股 25% → 24%；应收 60 → 72 亿；估值仍用 8,520 亿（新一轮在谈未成交）。
# - **假设判定**：A3 → `weakened`（税率 20.3%，一季不改输入）；A5 份额核对通过；A6 结构不变、份额更新；A9 持股更新；A10 两条触发器都未触发（Cloud 毛利率离 65% 线 1pp）；A2 共识换 2026-10-30 读数（卖方尚未按本季改模型，下轮修订后重拉）；其余不变。
# - **锚点**：L/M/H 369.54 / 419.31 / 464.86 → **386.02 / 418.65 / 456.80**。L 上移来自共识低端 20.93 → 22.03；H 下移来自高端 26.00 → 25.68 与 OpenAI 份额 / 持股；M 基本不动。\((H-L)/2M\) 0.114 → 0.085。
# - **异动**（Longbridge）：10-28 收盘 531.01，盘后最高 568.03（+7.0%），10-29 04:04 前后约 +5.5%，盘前回到约 540，10-29 盘中约 523（−1.5%）。冲高来自 Azure 与 Q2 指引超预期、资本开支低于预期；回落伴随资本开支只是推迟到下半年、自由现金流同比 −27%、OpenAI 占收入升到 11%，以及同日 Alphabet −13% 拖累 AI 资本开支板块（归因为推断）。整个过程价格都在 `stretched`（旧 H 464.86、新 H 456.80 之上），不跨档。
HISTORICAL_PARTIAL_FINGERPRINT = '06772817697e77bddc0c59fa3962d0ed154f5cc1232c22a8daaa4aa55c23ae05'

INPUTS = {
    # 稀释加权股数（百万）（A15）; 来源：10-K FY2026
    'shares_diluted': 7453,
    # 正常化税率 = FY26 有效税率剔 OpenAI 项（A3）; 来源：10-K FY2026
    'tax_rate': 0.1921,
    # FY26 合并经营利润（$M）= 三旧分部之和 83,879 + 56,972 + 14,386; 来源：10-K FY2026
    'oi_total_fy26': 155237,
    # Agents & Infrastructure 占 FY26 经营利润份额（重述；D&C = 1 − 本项）（A5）; 来源：大摩 103949
    'share_ai_oi': 0.88,
    # FY26 Azure 收入（$M，重述口径）（A5）; 来源：花旗 103969
    'rev_azure_fy26': 101938,
    # FY26 智能云分部收入（$M）；Azure 利润率代理的分母（A5）; 来源：10-K FY2026
    'rev_ic_fy26': 137791,
    # FY26 智能云分部经营利润（$M）；Azure 利润率代理 = 本项 ÷ `rev_ic_fy26` = 41.3%（A5）; 来源：10-K FY2026
    'oi_ic_fy26': 56972,
    # FY26 来自 OpenAI 的收入（$M，含收入分成）；÷ `rev_azure_fy26` = FY26 均值份额 23.6%，只进敏感行（A6）; 来源：10-K FY2026 关联方
    'rev_openai_fy26': 24100,
    # **OpenAI 子腿份额**（切 Azure 的 NOPAT）= FY27 Q1 来自 OpenAI 的收入 10,000 ÷ 当季 Azure 收入 33,165（含收入分成，偏高读）；旧三分部交叉按同一美元数换算到智能云（A6）; 来源：10-Q FY27 Q1 关联方
    'share_openai_az': 0.3015,
    # Azure 非 OpenAI 子腿 / 软件腿 / D&C 的永续折现率 = **篮 4 龙头制造** 10%（A6）；值 = `gordon.BASKET_R`; 来源：2026-09-22
    'r_perp': 0.10,
    # Azure OpenAI 子腿**过渡篮** = **篮 7 单押 / 国别 / 故事** 15%（今天收入依赖对手方未落定融资，A6）；本腿单段 Gordon，过渡篮无算术作用点，只记录今天的性质、定 \(G_{cap}\)、作合篮回退目标; 来源：2026-09-23
    'r_az_lab': 0.15,
    # Azure OpenAI 子腿**终值篮** = **篮 4 龙头制造** 10%：OpenAI 做成了的世界里是用自身收入付账的超大客户，与其余 Azure 客户同类（`_AXIS.frontier-lab-funding` §3）；稳态按此资本化；A6; 来源：2026-09-23
    'r_az_lab_t': 0.10,
    # OpenAI 子腿确定性等价折扣 = `_AXIS.frontier-lab-funding` §3b 共用值（eval 跨文件校验）；单段估值下承担**全部**到达风险；只乘 OpenAI 子腿（旧三分部交叉口径的 IC-lab 同乘）；A6; 来源：2026-09-23
    # 集团经营投入资本 IC0（$M，2026-06-30）= 总资产 758,376 − 流动负债 168,825 − 现金及短投 76,843 − 股权投资 36,348; 来源：10-K FY2026
    'ic_group': 476360,
    # Azure 分摊资本（$M）= 智能云分摊 213,698 × Azure 占智能云收入 74%（§0）; 来源：2026-09-22
    'ic_azure': 158094,
    # D&C 分摊资本（$M）≈ 个人计算分摊（含动视商誉 62,340）；软件腿 = `ic_group` − `ic_azure` − 本项 = 171,598; 来源：2026-09-22
    'ic_dc': 146668,
    # **Azure 新投资本的边际稳态 ROIC**（A4）= 汇丰 2027E Azure ROIC；进两条 Azure 子腿的留存项; 来源：Wisburg 99586
    'roic_marg_az': 0.146,
    # A&I 三条腿共用的永续增速（A7）；= \(G_{cap}\); 来源：2026-09-22
    'g2_ai': 0.06,
    # D&C 永续增速；无同业锚·自定（A7）; 来源：2026-09-22
    'g2_dc': 0.025,
    # FY26 非 GAAP 稀释 EPS（剔 OpenAI 项）；桥的基座（A2）; 来源：10-K FY2026
    'eps_adj_fy26': 17.28,
    # FY2027E 共识均值（34 家）；只用于滚未入账 FY27 的 NOPAT; 来源：yfinance 2026-10-30
    'eps_fy27e': 19.76,
    # L 档分子缩放系数 = 22.03 ÷ 17.28（A2）; 来源：yfinance 2026-10-30
    'k_eps_l': 1.27488,
    # M 档分子缩放系数 = 23.69 ÷ 17.28; 来源：yfinance 2026-10-30
    'k_eps_m': 1.37095,
    # H 档分子缩放系数 = 25.68 ÷ 17.28; 来源：yfinance 2026-10-30
    'k_eps_h': 1.48611,
    # FY2028E 共识低端（33 家）；一致性校验; 来源：yfinance 2026-10-30
    'eps_fy28e_low': 22.03,
    # FY2028E 共识均值; 来源：yfinance 2026-10-30
    'eps_fy28e_consensus': 23.69,
    # FY2028E 共识高端; 来源：yfinance 2026-10-30
    'eps_fy28e_high': 25.68,
    # 现金及短期投资（$M）; 来源：10-K FY2026
    'cash_sti': 76843,
    # 长期债务（$M）= 非流动 31,067 + 流动 9,227; 来源：10-K FY2026
    'lt_debt': 40294,
    # OpenAI 权益法账面（$M）（A9）; 来源：10-K FY2026
    'openai_book': 12000,
    # OpenAI 上一轮 post-money（$M，2026-03）（A9）; 来源：news 299051289
    'openai_post': 852000,
    # 微软持股（as-converted 约 24%，FY26 末约 25%）（A9）; 来源：10-Q FY27 Q1
    'openai_stake': 0.24,
    # 其他股权投资账面（$M）= 272.4 亿 − OpenAI 120 亿（A9）; 来源：10-K FY2026
    'other_eq_inv': 15240,
    # OpenAI 股权内含收益的递延税率（A9）; 来源：2026-09-22
    'dtl_rate': 0.21,
    # OpenAI 与其他股权 L 档折价（A9）; 来源：2026-09-22
    'd_oai_l': 0.60,
    # 中档折价; 来源：2026-09-22
    'd_oai_m': 0.40,
    # 上档折价; 来源：2026-09-22
    'd_oai_h': 0.20,
    # 近 3 年现金派息率均值（FY24 24.7% / FY25 23.7% / FY26 19.7%；回购视为留存现金用途）；只进「视同派出」行（A8）; 来源：10-K FY2024–2026
    'payout_3y': 0.227,
    # L 档「视同派出现金」打折 k：原 0.15（来源 ① 现金用途加权）乘在整个多留部分上，按 valuation-rules「经营价值与超额现金」④ 去掉（A17）; 来源：2026-10-16
    'k_l': 0,
    # M 档 k；同上（A17）; 来源：2026-10-16
    'k_m': 0,
    # H 档 k；同上（A17）; 来源：2026-10-16
    'k_h': 0,
    # 时点对齐：估值基准日 2026-06-30（10-K 资产负债表日）→ 分子年 FY2028 年初 2027-07-01 的年数；Azure 非 OpenAI / 软件 / D&C 按 `r_perp` 折、OpenAI 子腿按过渡篮 `r_az_lab` 折；窗口可分配利润按 τ/2 折（A16）; 来源：2026-06-30
    'tau': 1.0,
    # 回报路径第 1 年 = 分子年 FY2028（A17）; 来源：2026-10-16
    't0': 2028,
    # 高回报期止点 = 可见年末 FY2028（默认路径，云厂商不继承 `_AXIS.ai-capex`；A17）; 来源：2026-10-16
    'y1': 2028,
    # 稳态起点 = 可见年末 + 6（A&I 软件进入门槛「高」；A17）; 来源：2026-10-16
    'y2': 2034,
    # A&I 其余软件腿稳态回报 = 自身周期（按序取第一层）：近 5 个完整财年 FY2022–2026 投入资本口径均值 50.3%（10-K XBRL，公司合并口径）；同业中位 28.3%、兜底 30% 只作对照；每档不超过该档前瞻（A17）; 来源：2026-10-19
    'ronic_ss_rest': 0.503,
    # 自身 5 年月度 trailing PE 实测顶；护栏（A11）; 来源：Longbridge 2026-09-21
    'pe_own_top': 39.39,
    # 同一序列中位；只披露（A11）; 来源：Longbridge 2026-09-21
    'pe_own_p50': 33.31,
    # FY26 购置不动产及设备 USD；`_AXIS.ai-capex.md` 构成方（A12）; 来源：10-K FY2026
    'capex_fy26': 1.159e11,
    # 杠杆门读数（A8）; 来源：10-K FY2026
    'net_debt_ebitda': 0.38,
    # 杠杆门读数（A8）; 来源：10-K FY2026
    'interest_ebit': 0.020,
    # FY26 生产力与业务流程分部 OI（$M）；只进 b 交叉（A14）; 来源：10-K FY2026
    'oi_pbp_fy26': 83879,
    # FY26 个人计算分部 OI（$M）；只进 b 交叉; 来源：10-K FY2026
    'oi_mpc_fy26': 14386,
    # 生产力分部分摊资本（$M）；只进 b 交叉; 来源：2026-09-22
    'ic_pbp': 115994,
    # b 交叉：生产力腿永续增速（A7）; 来源：2026-09-22
    'g_b_pbp': 0.055,
    # b 交叉：个人计算腿永续增速（= `g2_dc`）; 来源：2026-09-22
    'g_b_mpc': 0.025,
    # 无期权（A13）; 来源：2026-09-22
    'v_opt': 0,
}
BASKETS = {"r_perp": 4, "r_az_lab": 7, "r_az_lab_t": 4}
REQUIRED = frozenset(INPUTS) | {'k_lab'}

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



def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    missing = REQUIRED - inp.keys()
    if missing:
        raise ValueError(f"missing inputs: {sorted(missing)}")
    require_whole_years(inp, ('t0', 'y1', 'y2'))
    baskets = BASKETS
    errors: list[str] = []

    r4, r7, r7t = inp["r_perp"], inp["r_az_lab"], inp["r_az_lab_t"]
    # The OpenAI sub-leg is a basket PAIR (valuation-rules「篮子对」): 篮 7 is what
    # the counterparty is today, 篮 4 what it is if it makes it.  Every leg here is
    # single-stage, so the steady state capitalises at the terminal rate and the
    # shared k_lab carries all of the arrival risk (_AXIS.frontier-lab-funding §3).
    errors += check_basket_pair(r7, r7t, "lab", baskets.get("r_az_lab"), baskets.get("r_az_lab_t"))
    errors += check_k_declared(r7, r7t, (inp["k_lab"],) * 3, "k_lab")
    for field, r in (("r_perp", r4), ("r_az_lab", r7), ("r_az_lab_t", r7t)):
        if field not in baskets:
            errors.append(f"{field}: Inputs source cell names no 篮 N")
        errors += check_r(r, field, baskets.get(field))
    for field, g, r in (("g2_ai", inp["g2_ai"], r4), ("g2_ai@lab", inp["g2_ai"], r7), ("g2_dc", inp["g2_dc"], r4)):
        errors += check_g_cap(g, r, field)
        if r - g < MIN_R_MINUS_G:
            errors.append(f"{field}: r - g = {r - g:.2%} < {MIN_R_MINUS_G:.0%}")
    if not (inp["k_eps_l"] < inp["k_eps_m"] < inp["k_eps_h"]):
        errors.append("k_eps_* ladder not increasing")
    mean = inp["eps_fy28e_consensus"]
    for tier, endpoint in (("l", "eps_fy28e_low"), ("h", "eps_fy28e_high")):
        want, got = inp[endpoint] / mean, inp[f"k_eps_{tier}"] / inp["k_eps_m"]
        if abs(got - want) > K_LADDER_TOL:
            errors.append(f"k_eps_{tier}/k_eps_m = {got:.5f} != {endpoint}/consensus = {want:.5f}")
    if abs(inp["k_eps_m"] - mean / inp["eps_adj_fy26"]) > K_LADDER_TOL:
        errors.append("k_eps_m != eps_fy28e_consensus / eps_adj_fy26")
    if not (1.0 >= inp["d_oai_l"] > inp["d_oai_m"] > inp["d_oai_h"] >= 0.0):
        errors.append("d_oai_* must be a decreasing band inside [0,1]")
    if not all(0.0 <= inp[f"k_{t}"] <= 1.0 for t in "lmh"):
        errors.append("k_* haircut outside [0,1]")
    if abs(inp["ic_azure"] + inp["ic_dc"] - inp["ic_group"]) > inp["ic_group"]:
        errors.append("capital split inconsistent")
    if inp["net_debt_ebitda"] > 3.0 or inp["interest_ebit"] > 1.0 / 3.0:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition")

    # --- Step 1: FY26 base on the recast segments
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_diluted"]
    oi_ai = inp["oi_total_fy26"] * inp["share_ai_oi"]
    oi_dc = inp["oi_total_fy26"] * (1 - inp["share_ai_oi"])
    azure_om = inp["oi_ic_fy26"] / inp["rev_ic_fy26"]           # proxy (待补)
    oi_azure = inp["rev_azure_fy26"] * azure_om
    share_az = oi_azure / oi_ai
    # A6: the OpenAI cut is the latest quarterly reading (10-Q), not the FY26 average;
    # FY26 (rev_openai_fy26 / rev_azure_fy26) is kept as a sensitivity row.
    share_lab_az = inp["share_openai_az"]
    share_lab_fy26 = inp["rev_openai_fy26"] / inp["rev_azure_fy26"]
    if not 0.0 < share_lab_az < 1.0:
        errors.append(f"share_openai_az = {share_lab_az} outside (0,1)")
    nopat_ai, nopat_dc = oi_ai * keep, oi_dc * keep
    core_eps = (nopat_ai + nopat_dc) / sh
    ic_rest = inp["ic_group"] - inp["ic_azure"] - inp["ic_dc"]
    k27 = inp["eps_fy27e"] / inp["eps_adj_fy26"]                 # FY27 unbooked bridge

    # --- asset legs
    openai_gross = inp["openai_post"] * inp["openai_stake"]
    openai_net = openai_gross - (openai_gross - inp["openai_book"]) * inp["dtl_rate"]
    net_cash = inp["cash_sti"] - inp["lt_debt"]

    def roe_open(e: float, ic0: float, g: float, unbooked: float) -> float:
        if g * unbooked / e >= 1.0:
            raise ValueError("opening-capital roll diverges")
        return e / (ic0 / (1.0 - g * unbooked / e))

    t0, y1, y2, tau = int(inp["t0"]), int(inp["y1"]), int(inp["y2"]), inp["tau"]
    r7tau = r7  # the OpenAI sub-leg's tau segment runs at its journey basket (篮子对)

    def tier(t: str, k: float, ic_scale: float = 1.0, roic_marg: float | None = None,
             share_lab: float | None = None, r_lab: float | None = None, k_lab: float | None = None,
             g_ai: float | None = None, g_dc: float | None = None, flat: dict | None = None,
             rs_rest: float | None = None) -> dict:
        roic_marg = inp["roic_marg_az"] if roic_marg is None else roic_marg
        share_lab = share_lab_az if share_lab is None else share_lab
        r_lab = r7t if r_lab is None else r_lab
        k_lab = inp["k_lab"] if k_lab is None else k_lab
        g_ai = inp["g2_ai"] if g_ai is None else g_ai
        g_dc = inp["g2_dc"] if g_dc is None else g_dc
        rs_rest = inp["ronic_ss_rest"] if rs_rest is None else rs_rest
        n_az, n_rest = nopat_ai * share_az, nopat_ai * (1 - share_az)
        out: dict = {}
        legs = (
            ("az", n_az * (1 - share_lab), inp["ic_azure"] * ic_scale * (1 - share_lab), g_ai, r4, roic_marg, r4),
            ("lab", n_az * share_lab, inp["ic_azure"] * ic_scale * share_lab, g_ai, r_lab, roic_marg, r7tau),
            ("rest", n_rest, ic_rest * ic_scale, g_ai, r4, None, r4),
            ("dc", nopat_dc, inp["ic_dc"] * ic_scale, g_dc, r4, None, r4),
        )
        for name, n, ic, g, r, rm, r_tau in legs:
            e, unb = n * k, n * k27                          # unbooked FY27
            roe_avg = roe_open(e, ic, g, unb)
            roe_ret = roe_avg if rm is None else rm          # A4: Azure retains at the marginal ROIC
            # ② only the A&I rest leg fades (to its own-cycle stable return); Azure retains at
            # the marginal steady-state ROIC and D&C's forward ROE sits below it -> flat.
            rs = rs_rest if name == "rest" else roe_ret
            pe = path_pe(g, roe_ret, r, t0, y1, y2, rs) if flat is None else flat[name]
            # k_lab leaves the OpenAI sub-leg's value only, never its multiple (axis §3b).
            haircut = (1.0 - k_lab) if name == "lab" else 1.0
            out[name] = dict(e=e, roe=roe_avg, roe_ret=roe_ret, pe=pe, b1=g / roe_ret, unb=unb,
                             rs=min(roe_ret, max(rs, r)),
                             val=e * pe * haircut / sh / (1 + r_tau) ** tau)
        d = inp[f"d_oai_{t}"]
        out["oai"] = dict(val=(openai_net + inp["other_eq_inv"]) * (1 - d) / sh, d=d)
        out["cash"] = dict(val=net_cash / sh)
        # ③ window: unbooked FY27 leg NOPAT x (1 - b1), discounted tau/2 (no funding gap).
        window = sum((1 - out[n]["b1"]) * out[n]["unb"] for n in ("az", "lab", "rest", "dc")) / sh
        out["win"] = dict(val=window / (1 + r4) ** (tau / 2))
        deemed = sum(max(1 - inp["payout_3y"] - out[n]["b1"], 0.0) * out[n]["unb"] for n in ("az", "lab", "rest", "dc")) / sh
        pre = sum(v["val"] for v in out.values())
        out["deemed"], out["pre"] = deemed, pre
        out["total"] = pre - inp[f"k_{t}"] * deemed
        return out

    def band(**kw) -> dict:
        return {t: tier(t, inp[f"k_eps_{t}"], **kw) for t in "lmh"}

    base = band()
    L, M, H = (base[t]["total"] for t in "lmh")
    if not (L < M < H):
        raise ValueError(f"L<M<H violated: {L}, {M}, {H}")
    A, B = cut_points(L, M, H)
    for t in "lmh":
        for name in ("az", "lab", "rest", "dc"):
            b1 = base[t][name]["b1"]
            if not (0.0 < b1 < 1.0):
                errors.append(f"{name} {t}: b1 = {b1:.3f} outside (0,1)")
        # The >60% leg-ROE guard is judged on the M tier (the leg's own state);
        # L/H are scenario numerators on the same capital and are only printed.
        for name in ("rest", "dc"):
            if t == "m" and base[t][name]["roe"] > MAX_LEG_ROE:
                errors.append(f"{name} {t}: derived ROE {base[t][name]['roe']:.1%} > {MAX_LEG_ROE:.0%}")
        # Per dollar of earnings the OpenAI sub-leg must never be worth more than the
        # rest of Azure: same terminal basket, so the haircut keeps it below.
        if base[t]["lab"]["pe"] * (1.0 - inp["k_lab"]) > base[t]["az"]["pe"] + 1e-9:
            errors.append(f"tier {t}: OpenAI sub-leg after k_lab out-values the non-OpenAI sub-leg per unit of earnings")
    if H / core_eps > inp["pe_own_top"]:
        errors.append(f"生成的倍数越出自身实测带: H/core_eps {H / core_eps:.2f}x > {inp['pe_own_top']:.2f}x")
    flat = {n: base["m"][n]["pe"] for n in ("az", "lab", "rest", "dc")}
    fb = band(flat=flat)
    flat_l, flat_h = fb["l"]["total"], fb["h"]["total"]
    if not (flat_l < M < flat_h):
        raise ValueError(f"flat-multiple ladder collapsed: {flat_l:.2f}/{M:.2f}/{flat_h:.2f}")

    # --- cross-check (b): FY26 old segments
    share_lab_ic = share_lab_az * inp["rev_azure_fy26"] / inp["rev_ic_fy26"]  # same OpenAI dollars on the old cloud segment
    ic_old = {"pbp": inp["ic_pbp"], "ic": inp["ic_azure"] * inp["rev_ic_fy26"] / inp["rev_azure_fy26"], "mpc": inp["ic_dc"]}
    oi_old = {"pbp": inp["oi_pbp_fy26"], "ic": inp["oi_ic_fy26"], "mpc": inp["oi_mpc_fy26"]}
    g_old = {"pbp": inp["g_b_pbp"], "ic": inp["g2_ai"], "mpc": inp["g_b_mpc"]}

    def tier_b(t: str) -> tuple[float, dict]:
        k = inp[f"k_eps_{t}"]
        out: dict = {}
        for name in ("pbp", "ic", "mpc"):
            n, ic, g = oi_old[name] * keep, ic_old[name], g_old[name]
            parts = ((name, n, ic, r4, None),) if name != "ic" else (
                ("ic-non", n * (1 - share_lab_ic), ic * (1 - share_lab_ic), r4, inp["roic_marg_az"]),
                ("ic-lab", n * share_lab_ic, ic * share_lab_ic, r7t, inp["roic_marg_az"]),
            )
            for pn, nn, icc, r, rm in parts:
                e, unb = nn * k, nn * k27
                roe = roe_open(e, icc, g, unb)
                pe = perpetual_pe(g, roe if rm is None else rm, r)
                haircut = (1.0 - inp["k_lab"]) if pn == "ic-lab" else 1.0
                out[pn] = dict(e=e, roe=roe, pe=pe, b1=g / (roe if rm is None else rm), unb=unb,
                               val=e * pe * haircut / sh)
        d = inp[f"d_oai_{t}"]
        deemed = sum(max(1 - inp["payout_3y"] - v["b1"], 0.0) * v["unb"] for v in out.values()) / sh
        total = sum(v["val"] for v in out.values()) + (openai_net + inp["other_eq_inv"]) * (1 - d) / sh + net_cash / sh - inp[f"k_{t}"] * deemed
        return total, out

    bres = {t: tier_b(t) for t in "lmh"}
    Lb, Mb, Hb = (bres[t][0] for t in "lmh")


    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0: no consensus-referenced option anchor")
    sens = [
        ("Azure marginal ROIC 20% (consensus-implied FY26→28)", dict(roic_marg=0.20)),
        ("Azure marginal ROIC 10% (= r; realised first-year lower bound)", dict(roic_marg=0.10)),
        ("OpenAI share of Azure 35% (FY28 ramp of the $250B commitment)", dict(share_lab=0.35)),
        (f"OpenAI share of Azure at the FY26 average {share_lab_fy26:.1%}", dict(share_lab=share_lab_fy26)),
        ("k_lab = 0 (no arrival haircut)", dict(k_lab=0.0)),
        ("single-basket OpenAI (篮 7 15%, no k — the pre-pair ruler)", dict(r_lab=r7, k_lab=0.0)),
        ("g2_ai −0.5pp", dict(g_ai=inp["g2_ai"] - 0.005)),
        ("g2_ai −1pp", dict(g_ai=inp["g2_ai"] - 0.01)),
        ("g2_dc ±1pp", dict(g_dc=inp["g2_dc"] + 0.01)),
        ("stable-return path off (A&I rest permanent at the forward ROE)", dict(rs_rest=1.0)),
    ] + [(f"opening IC x{s:.1f} (A4 待补 capital path)", dict(ic_scale=s)) for s in IC_SENSITIVITY]

    ids = ("azure_roic_20", "azure_roic_10", "openai_share_35", "openai_fy26_share",
           "lab_haircut_zero", "lab_single_basket", "ai_growth_down_half", "ai_growth_down",
           "device_growth_up", "stable_return_off", "opening_capital_120", "opening_capital_140")
    scenarios = {name: band(**kw) for name, (_, kw) in zip(ids, sens)}
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r4, r7t, r7tau
        saved = r4, r7t, r7tau
        r4, r7t, r7tau = r4 + dr, r7t + dr, r7tau + dr
        try:
            b = band()
            return b["l"]["total"], b["m"]["total"], b["h"]["total"]
        finally:
            r4, r7t, r7tau = saved

    if errors:
        raise ValueError("; ".join(errors))

    def band_values(values):
        return {t.upper(): values[t]["total"] for t in "lmh"}
    result = {
        "ticker": "MSFT.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-06-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-30', 'historical_framework_as_of': '2026-10-30',
        "anchors": band_values(base), "candidate": None, "option": None,
        "cut_points": {"A": A, "B": B}, "base_detail": base,
        "old_segment_cross": bres, "flat": [flat_l, M, flat_h], "sensitivity": scenarios,
        "parameters": {"discount": {"azure": r4, "lab_terminal": r7t, "lab_journey": r7,
                                    "rest": r4, "device": r4},
                       "growth": {"ai": inp["g2_ai"], "device": inp["g2_dc"]},
                       "return_path": {t: {leg: {"forward": base[t][leg]["roe_ret"], "stable": base[t][leg]["rs"]}
                                           for leg in ("az", "lab", "rest", "dc")} for t in "lmh"}}
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if min(r4 + dr, r7t + dr) <= max(inp[k] for k in ('g2_ai', 'g2_dc')):
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_perp': r4, 'r_az_lab_t': r7t}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    lab, capex = context['axes']['lab'], context['axes']['capex']
    if not lab.get('uses_shared_haircut') or capex.get('role') != 'constituent':
        raise ValueError('shared frontier-lab and AI capital roles are required')
    shared = {'k_lab': lab['k_lab']}
    result = evaluate({**INPUTS, **shared}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'shared': shared, 'capex': {'role': capex['role'], 'base_2026_usd': capex['base_2026_usd']},
         'baskets': BASKETS, 'minimum_rate_gap': MIN_R_MINUS_G, 'ladder_tolerance': K_LADDER_TOL,
         'ic_sensitivity': IC_SENSITIVITY, 'max_leg_roe': MAX_LEG_ROE}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    base = result['base_detail']
    result['segments'] = {name: {'unit': 'USD_PER_SHARE',
                                 'values': {t.upper(): base[t][name]['val'] for t in 'lmh'}}
                          for name in ('az', 'lab', 'rest', 'dc', 'oai', 'cash', 'win')}
    result['segments']['distribution_adjustment'] = {'unit': 'USD_PER_SHARE',
        'values': {t.upper(): -INPUTS[f'k_{t}'] * base[t]['deemed'] for t in 'lmh'}}
    parameters = result['parameters']
    growth_names, discount_names = {'az': 'g2_ai', 'lab': 'g2_ai', 'rest': 'g2_ai', 'dc': 'g2_dc'}, {'az': 'azure', 'lab': 'lab_terminal', 'rest': 'rest', 'dc': 'device'}
    result['key_parameters'] = {}
    for leg in growth_names:
        result['key_parameters'][leg] = {
            'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'][discount_names[leg]])},
            'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS[growth_names[leg]])},
            'forward_return': {'unit': 'RATIO', 'values': {t.upper(): parameters['return_path'][t][leg]['forward'] for t in 'lmh'}},
            'steady_return': {'unit': 'RATIO', 'values': {t.upper(): parameters['return_path'][t][leg]['stable'] for t in 'lmh'}},
        }
    result['review_flags'] = ['historical_lab_funding_discount_estimated',
                              'historical_cloud_invested_capital_path_unverified',
                              'historical_forecasts_and_asset_values_unverified']
    return result
