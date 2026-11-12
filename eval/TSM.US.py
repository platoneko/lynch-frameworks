#!/usr/bin/env python3
"""TSM legacy valuation; the migration does not update financial assumptions.

Units and fiscal dates are noted per input. Shared optical and CoWoS checks
remain active. The 4% candidate is a pressure comparison, not adopted consensus.
"""
from __future__ import annotations
import math
from lib.gordon import check_branch, check_g_cap, check_r, check_transition_years, payout, payout_gap
from lib.inputs import check_missing, ladder, require_whole_years
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES={'libraries':('gordon','inputs','tiers','zones','partial_basis','rf_report'),
              'axes':{'cowos':'cowos_capacity','optical':'optical_comms'}}
HISTORICAL_PARTIAL_FINGERPRINT='d8e80786477b0b5d19499310755c8a5d3812465177d02219dd593b70e90b2c9e'

FORMULA_ID = "tsm_sotp_2027_two_stage_gordon_v10"
LISTING_CCY = "USD"
TOL = 0.15
P_TOL = 0.0005
MIN_R_MINUS_G = 0.02
NUM_YEAR = 2027
NPM_TOL = 0.03
TWO_MONTHS = 2.0 / 12.0
TIERS = ("l", "m", "h")
# | A32 | **永续增速 4% 压力候选**：只替换先进晶圆 / B1 的 `g2_candidate=4%`，保留 2027E EPS 19.58 / 21.93 / 24.62、M/H 的 2028 平台增长 33.2%、L 无过渡、成熟 / B2 增长 2%、篮 4 折现率、期初经营股权与 RONIC、2030 / 2035 / 稳态回报 35.0%、窗口利润、现金和 B1 max 分支。资金释放与资本结构不另作判断；不是把 4% 重新反解到主尺倍数护栏上沿。**采用门槛**：后续公司指引 / 具名研究证据支持数据中心受限持续压低长期扩张能力，而非仅订单延期，并由用户确认替换主尺；否则仅保留压力候选，不自动升级。该 4% 是用户指定值，无新增卖方共识背书；按用户明确要求借用候选带机器行展示，不表示常规共识升级候选 | active | 用户对话 2026-11-06；政策背景见美银 / 高盛研报转述（2026-11-05，Longbridge 304417597 / 304414217），报道没有量化台积电永久增长损失 | `g2_candidate`；候选带与表2c；不改主尺 / 期权 |
# | A1 | FY2026 美元营收增速 base = **+40%**。**触发器**：已报季度实测 + 公司下一季营收指引中值推出的全年美元增速 < +37% 或 > +45% → 回对话（2027E 共识的起点变了，先看分子是否随之修订） | active | 2Q26 法说；8 月 +53.3% | 2026–27 共识背景 |
# | A4 | 2027 占比：**晶圆 83% / 先进封装 11% / 其余 6%**（待分部披露再修订）。**触发器**：公司在法说 / 年报给出先进封装营收占比，且与 11% 相差 ≥ 3ppts → 改占比（连带成熟 pin 与平台过渡增速重算）；管理层把封装增速指引到低于晶圆 → 回对话 | active | 封装指引略高于 10%（法说）；对话 | 三腿分子 |
# | A5 | `eps_leg = 合并 2027E × 占比`；等利润率。**腿级经济性来源层级（valuation-rules「数据优先级与同业同尺」，2026-10-03 核）= 共享规则「各腿经济性相同」**：① 卖方分部预测——无（20-F 无分部 EBIT；卖方不拆先进 / 成熟 / 封装利润）；② 公开数据推断——试过、不成立：制程营收占比（占晶圆营收）× 公司毛利率三期 2Q25 先进 74% / GM 58.6%、1Q26 74% / 66.2%、2Q26 77% / 67.7%，**同一 mix 下毛利率差 7.6pp**（涨价 / 利用率 / 汇率 / N2 与海外厂稀释），「各腿利润率两期不变」这条推断假设被数据直接否掉；只用 1Q26→2Q26 一对会解出先进−成熟毛利率差 ≈ 50pp（成熟 ≈ 29%），换一对 2Q25→2Q26 解出 ≈ 300pp，联立病态，不出区间；B1 / B2 无腿收入序列可联立。③ 故退到共享规则，非拍值。方向：增量数据提示成熟利润率低于先进 → 等利润率高估成熟腿占比、底牌 M 偏低（A24 已披露同一方向）。升级门槛：≥1 家卖方给出制程或封装分部利润率，或公司披露封装毛利率 → 替换 | active | 20-F 无分部 EBIT；TSMC 2Q25 / 2Q26 earnings release（6-K，SEC）；1Q26 由 2Q26 季比 +1.5pp 推得 | 分子 |
# | A6 | 2028E 卖方 EPS 只以 \(g_1\) 进 M/H（A22）；2027E 共识本身是分子，无需再校验桥 | active | 对话 | 防脏分子 |
# | A7 | **平台倍数（先进晶圆 + B1）由 Gordon/两段式生成**：**2026-10-16 框架纠正（A31）后现行值**：\(g_2=5.842\%\)（同一条护栏，靶改为**今天的经营倍数**——三段回报路径的 Gordon 折回估值基准日 τ 0.5 年再加窗口可分配利润，÷ 经营 EPS；H 档触上沿 21.85×）→ 平台倍数（2027 年初）**20.43 / 25.12 / 25.24×**、今天的经营倍数 **18.32 / 21.75 / 21.85×**；本行以下为纠正前（2026-10-15）的推导与读数。\(r=10\%\)（篮 4，A25），\(g_2=5.249\%\)（**自身实测带反解，靶 = 全公司经营倍数**），\(RONIC_x\) = 63.3% / 64.5% / 73.6%（2027E 经营 EPS ÷ 2027 年初经营 BPS，2Q26 账面扣超额现金后按 \(b_1=g/RONIC\) 滚过 2H26，A28）；M/H 另 \(g_{1,adv}=33.2\%,\ n=1\)（A22）。护栏 = 合并带 [9.7, 21.9] 的经营口径重读 **[9.49, 21.85]**（两端月份价扣当时可见每 ADR 超额现金、EPS 扣其税后收益：上沿 2022-01 扣 0.29、下沿 2025-03 扣 4.40；次高点 2026-06 经营口径 21.68，不约束），作用于每档经营倍数 \(V^{op}_x/E^{op}_x\)；裁决顺序 ③ 在 H 档反解得 5.249% → 平台 **19.30 / 23.85 / 24.17×**、经营倍数 **17.91 / 21.59 / 21.85×**。2026-10-15 框架纠正：原值 5.43% 是同一条护栏在合并 PE、账面 ROE 48.7–56.5% 口径下的反解；按经营口径机械重解，不是换来源。**用户判断（对话 2026-10-14 确认）**：平台腿永续增长的讨论区间为 5.5%–6%；带边护栏（裁决顺序 ③）在 5.5% 与 6% 下都使 H 档经营倍数越出上沿（22.84× / 25.19×），故落在重解值 5.249%，两数锚点相同。**成熟晶圆与 B2 不走本条**——见 A23 / A24。每 ADR 超额现金今昔差异 > 1 倍（上沿月份 0.29、今天 9.49）：上沿几乎不含现金，倍数读数不受 λ 影响；若市场对现金打折，今天按面值加回的 9.49 偏乐观。带为后视口径（分母 = 事后实际 EPS），已知偏低，见 §1 | active | yfinance 2026-09-11；`eval/lib/gordon.py`；AVGO A18；Longbridge `valuation --history` / `forecast-eps` 2026-09-16、月 K（2022-01 收盘 122.63）；对话 2026-10-14 | `g2`、`r_perp`、`pe_own_*`、`pe_op_*`、`px_edge_hi`、`cex_edge_hi_twd`、`fx_edge_hi`、`aty_edge_hi` |
# | A23 | **B2 其余后端 = 成熟 OSAT 尺**：\(PE^{B2}=\mathtt{perpetual\_pe}(g_{B2}=2\%, RONIC_x, r)\)，不背 \(g_1\)。依据：Yole traditional packaging ~1.9–2.2%；Amkor 2021–25 ~2.2%；可外包、无瓶颈。分子仍等利润率切 6%（待分部修订） | active | Yole；Longbridge AMKR；对话 2026-09-16 | `g_b2` |
# | A24 | **成熟晶圆：营收 $ pin + \(g_{\mathrm{mat}}=2\%\)**：as-of 2Q26 成熟（>7nm）占晶圆营收 **23%**（N2 3% / N3 30% / N5 33% / N7 11% = 先进 77%；FY2025 为 26%）；**假定成熟营收额停在 2Q26 年化水平**，之后的营收增长全部归先进 → 2027E 成熟/晶圆 = 23% × (4 × `rev_2q26_twd`) / `rev_2027_twd` = 23% × 5,081.5/7,297.3 ≈ **16.0%**（先进 84.0%）。桥用营收比而非 EPS 比：pin 的是营收 $，且 2027E 营收共识 +34% 高于 EPS +29%（EPS 桥会把成熟占比多算到 17.8%）。倍数 = `perpetual_pe(2%)`，不背 \(g_1\)。**\(g_{\mathrm{mat}}\) 来源 = 自身实测 CAGR 上界**：成熟 $ 营收 2022 ≈ $35.7B（75.9B × 47%）→ 2023 29.1 → 2024 27.9 → 2025 31.7 → 2Q26 年化 37.0（40.2B × 4 × 23%），3.5 年 CAGR ≈ **+1%**（未扣晶圆/总营收比下降，实际略低），2% 为上界。UMC 同尺同日反解 7.5%（fwdPE 25.9×、ROE 21%、良态）**不入锚**：25.9× 是周期分母塌缩的倍数，且 UMC 是整家成熟代工厂，与「台积电内部不再扩产的尾节点」不同世界，只作交叉。**禁止**把 as-of 23–26% 钉进 2027E（钉 23% 比 pin 路径低估 M ≈15）。等利润率仍可能高估成熟利润占比（成熟 npm 通常低于 N3/N5）→ 本条对 M 的扣减偏上限。证伪：成熟节点 ASP/利用率结构性上行且占比回升 → 回对话 | active | TSMC 2Q26 earnings release；TSMC 年报 2022–25 制程表；Longbridge `business-segments` 2Q26 营收；yfinance 2027E 营收共识 2026-09-11；UMC yfinance 2026-09-16 | `mat_of_wafer_asof`、`rev_2q26_twd`、`rev_2027_twd`、`g_mat_wafer` |
# | A8 | B1 UV = **$12.8e9 / 万片·月**（7nm 锚 1.0×；原始研报 ID 待补）；禁止再乘无来源溢价。g2 改带边反解后三档盈利地板都高于产能项（M 56.7 vs 49.4），UV 只作坐标、不进任何档的锚点，故待补不构成候选带输入 | active | 对话 | 产能项（坐标） |
# | A9 | CoWoS：L = YE26 × 0.5「只兑现一半」= **65k**；M = H = YE27 轴 **200k**（分子年 2027E）；YE28 260k 只进 stretched 解释。**触发器**：管理层或 ≥2 家法人把 YE26 / YE27 产能说低 ≥ 15%（< 110k / < 170k）→ 先改轴 `_AXIS.cowos-capacity.md`，本票随轴；三档 B1 仍是盈利地板胜出时只动坐标、不动锚点。外包给 OSAT 不触发（A11） | active | Longbridge 298789591；轴 200k | `cowos_wpm_*` |
# | A11 | 近中期紧平衡；外溢不自动 weakened | active | 2026-09 新闻 | B1 |
# | A12 | COUPE 不并进 B1 分子；期权只计增量 | active | 对话 | 防双计 |
# | A13 | SOTP v9：\(P = (P_{aw} + P_{mw} + P_{B2})/(1+r)^{\tau} + P_{B1} + W + C_{ex}\)（2026-10-16 起按时点对齐，A31：Gordon 腿估在 2027 年初、折 τ；B1 取 Gordon 地板时同折、取 CoWoS 产能值时不折；W = 窗口可分配利润；前四项按经营 EPS 计）；先进晶圆 × 平台 PE；成熟晶圆 × \(PE^{\mathrm{mat}}\)；B1 = max(UV, 先进封装×平台 PE)；B2 × \(PE^{B2}\)；超额现金每 ADR 按面值（A30）；护栏读经营倍数 \((P − C_{ex})/E^{op}\) | active | A7；A23；A24；A30 | 锚点 |
# | A14 | 2027E 分子改用共识：均值 **21.93**（13 家，USD/ADR）；旧版作者桥 21.28 已撤 | active | yfinance 2026-09-11 | `eps_2027_m` |
# | A15 | M/H 净利率 = 2027E 共识均值隐含 **49.3%**（`eps_2027_m` × ADR 数 × 汇率 ÷ 2027E 营收共识），已嵌入分子；它**低于** 1H26 实测 **53.2%**（1Q26 50.5% / 2Q26 55.6%）——共识本身承销了利润率回落（N2 爬坡、海外厂、台币），M 不是把当期利润率外推。旧写「1H26 49.9%」是算错的分母，2026-10-11 纠正；分子取共识，锚点不受影响。实测利润率只作快照、不覆盖共识（valuation-rules「数据优先级与同业同尺」）。**触发器**：连续两季净利率 < 47%，或管理层把 2027 年 N2 + 海外厂对毛利率的合计稀释说到 > 3ppts → L 方向回对话；连续两季 ≥ 53% 且共识均值隐含净利率仍 < 50% → 共识偏低，回对话看 H 分子 | active | yfinance 季度利润表 1Q26–2Q26；yfinance 2027E 共识 2026-09-11 | 分子；A17 参照 |
# | A16 | 即期汇率折 ADR（权益 6,432.5B TWD ÷ 31.63）；\(g_1\) 用 TWD 口径比值，汇率抵消；不押台币升值 | active | yfinance TWD=X 2026-09-11 | 口径 |
# | A17 | **L 的具名机制**：2027E 共识低端 19.58 ≡ 均值 × 44.6%/49.3%（2025 实测净利率 ÷ 共识均值隐含净利率，A15）= 19.83（差 1.3%）。参照取共识均值隐含而非 1H26 实测 53.2%：低端与均值是同一张共识表的两点，比的是共识内部的利润率差；拿实测 53.2% 作参照得 18.38、偏离 6%，那是把「共识已承销的回落」再算一次。退坡机制：N2 量产初期稀释 GM 2–3ppts + 海外厂（亚利桑那 N4/N3）初期稀释 2–3ppts、后期可至 3ppts 以上（管理层长期 GM 目标 56%+ 即含此），以及台币升值；eval 校验机制值与共识低端差 <3%。**分子与 g 同一世界**（Phase 3 A7）：共识低端是允许配稳态 g2 的实测水平，不是谷底（19.58 仍高于 2026E 共识均值 16.93 与 2025 实际 10.65）；「2027 = 2026 零增长」的谷底坐标（≈ 302）只进 deep_discount 行 | active | GS Communacopia 104877（2026-09-10）；20-F 2025 | L 分子 |
# | A18 | 挂载 `_AXIS.cowos-capacity.md`（CoWoS）与 `_AXIS.optical-comms.md`（COUPE OE）；两轴正交；`cowos_wpm_m=200000`；α/β/γ 不驱动本票 | active | 大摩；光通信轴 | 轴 |
# | A19 | **COUPE \(V_k\)**（挂 `_AXIS.optical-comms.md`；2026-10-03 按「未建模期权」新规则核）：\(NI_k(oe) = oe × asp\_oe × coupe\_share_k × npm\_coupe / shares\)。`oe_*` = 轴实际 OE **7.78e6 / 4.0e7 / 4.86e7**（轴三档同为 2028 年：推迟一年 / 广发 NPO / 大摩，2026-10-02 起）；`asp_oe=450`（高盛 CPO 交换机整颗 OE BoM）；`coupe_share` = **0.25 / 0.33 / 0.55**（L/M = PIC+键合防双计；H = 2028 后光源（磷化铟基激光芯片）供给上来后溢价迁入 COUPE 的中度分成）；`npm_coupe=0.50`（腿级经济性无卖方 / 无推断，按 A5 共享规则取公司 2027E 净利率）。**估值（v10）**：三档同一把尺——\(V_k = NI_k(oe_k) × \mathtt{perpetual\_pe}(g_2, RONIC_k, r) × (1+r)^{-(t_{coupe} − 2027)}\)，兑现年 `t_coupe` = 2028（量的年份 = 轴三档的卖方 2028E；公司具名的只有 COUPE CPO 2026 量产验证，早于量年，故按量年），2028 估值、篮 4 折回分子年 2027；**不用平台 PE**——那会把晶圆的 2028 +33.2% 过渡在兑现年再开一次（v9 的 L / H 就是这样，H = 28.12 未折现）。\(V_{opt} = V_H\)，\(p_k = V_k/V_H\)。**份数来源层级（未闭合，披露）**：新规则要求份数只来自本票具名的量；本票无公司 COUPE 收入目标、无合同披露；TrendForce（2026-07-08）估台积 PIC 产能 2Q26 10k → 4Q26 15k → 2028 ≥25k 片/月，但无每片单价，换算不成收入；今日实测 COUPE 收入未披露（量产验证中），「1 份今日实测腿」无数可取，规则又不许置 0 → 现行份数仍是轴量 × 拍定分成（2026-09-13），标「份数非本票具名·待闭合」。**禁止**用 PIC 名义 die 或「整颗 $450 全归台积」。升级：公司或 ≥1 家卖方给出 COUPE / PIC 晶圆单价或 COUPE 收入 → 份数改为 PIC 产能 × 单价（或收入 − 共识已含）；≥2 家台积 COUPE / 硅光收入或 ASP → 替换拍分成。证伪：搁置量产 → \(V=0\) | active | 轴 95433；高盛 OE BoM；TrendForce 2026-07-08；对话 2026-09-13 / 09-17；valuation-rules「未建模期权」2026-10-03 | 表3 |
# | A20 | **三档分子 = 2027E 共识区间三点**（低 19.58 / 均 21.93 / 高 24.62，13 家）：L 与 H 是同一分布的两端；H 非多一年复利，是同年共识上沿。旧版 +20/+25/+30% 作者桥已撤。**分子年份的裁决（构造规则冲突裁决顺序 ②）**：2027E 是最远一个有 ≥2 家共识**区间**的年份；2028E 虽是 ≥2 家可见的最远年份，但只有两家点估计（JPM 180.01；DB 187.5 由其 TP 3000 ÷ 自家 16× 得出），yfinance +1y 止于 2027E、Longbridge 季度共识止于 Q1 2027，凑不出三点同源的区间 → 只进 g1 层（A22）；2029E 无任何卖方 EPS → 不进任何层。把两家点强作 2028E 三点分子会塌成分子比 0.98 的窄带（A2e-1 的 L 失效），不采 | active | yfinance 2026-09-11；Wisburg 96303 / 96264；Longbridge 共识 2026-09-14 | 分子阶梯 |
# | A21 | **2026-10-16 起撤回「不折现」，改按时点对齐（A31）**：Gordon 给的是分子年 2027 年初的价值，折回估值基准日 2026-06-30（τ 0.5 年）并加窗口可分配利润；下文为原口径留痕。**不折现**：anchor_year = 2027 = 当前年 +1 = t=1，未达 A2e-3 强制折现门槛；2028（t=2）那一年在 `two_stage_pe` 内部已按 r 折回一年。**估值时点只有一个**（valuation-rules「两段式过渡 · 估值时点」，2026-09-14 切换）：L 的 `perpetual_pe` 与 M/H 的 `two_stage_pe` 都以 2027E 为下一期盈利、今日 = t=0 取值（切换前 `two_stage_pe` 把 2027E 当当期，M/H 比 L 晚一年取值；切换后 g2 按 ③ 同一定义在新时点重解，A7）。本框架此前未对 2027E 分子另加折现，切换后无双计可去 | active | A2e-3；valuation-rules 两段式过渡 | 口径 |
# | A22 | **两段式仅 M/H，n=1**：全公司 \(g_1\) = 2028E 两家均值 NT$183.76（JPM 180.01 / DB 187.5）÷ 2027E 五家均值 NT$144.93 − 1 = **+26.8%**（JPM 自身 2027→2028 为 +27.3%）；经营利润口径（2027、2028 同扣超额现金税后收益 0.297）= **+27.2%**；\(n\) = 有 ≥2 家共识的年数 = 1；2029E 无卖方 EPS。**平台腿背 \(g_{1,adv}\)**：\(g_{1,adv} = (g_1 − w_{mw} g_{\mathrm{mat}} − w_{B2} g_{B2}) / (w_{aw}+w_{B1})\) = (27.2% − 13.3%×2% − 6%×2%) / 80.7% = **+33.2%**——共识可见的 2028 增长 MUST 装满（裁决顺序 ②），成熟/B2 只按各自 g 走，剩下的全归稀缺腿（与 A24 pin 的方向同构）。段一派息率 M 0.49 / H 0.55（= `two_stage_pe` 原形态 1 − 33.2%/RONIC，RONIC 按 2027 年初经营股权；MUST NOT 用实付派息率替代——那会把 g1 用不到的留存定价成 0，valuation-rules 两段式 2026-09-21；A28）。旧版 n=6、g1=8% 已撤（无共识年份） | active | Wisburg 96303 / 96264 / 96268 / 96290 / 96211 / 103488；`check_transition_years` | M/H 平台 PE |
# | A25 | **归篮**：先进晶圆 → **篮 4 龙头制造 10%**（用户表：台积电 10–11.5；稀缺产能的常规经营现金流）；成熟晶圆 → **篮 4 龙头制造 10%**（营收 $ pin、\(g=2\%\) 的成熟尾节点仍是龙头的常规经营现金流，不是商品价函数）；B1 先进封装随平台腿、B2 其余后端随成熟腿，同篮 4。无备选篮。两腿同篮 → 分腿 r 相同，SOTP 加总不变；CAPM 粗筛 **9.6%**（β 1.25），与篮 4 偏离 −0.4pp，不进质疑清单。**g2 与篮子的关系**：平台 \(g_2\) 5.249% 是 H 档经营倍数触自身实测带经营口径上沿 21.85× 的带边反解（A7），靶是全公司经营倍数（SOTP 含 \(g_{1,adv}\) 过渡），不是单腿 Gordon 反解；cap = min(6%, r − 4%) = 6%，5.249% 未被收紧；成熟 / B2 的 2% 同 cap 下合法。AI 半导高增长按命名 g1 窗口表达（FY28 两家共识过渡年，n=1，\(g_{1,adv}\) +33.2%，A22），不抬 r、不进永续。证伪点：篮级季度对账显示两腿隐含 r 持续 ≥ 13% → 复审 | active | `eval/lib/gordon.py BASKET_R`；valuation-rules「§r 篮子」；CAPM 粗筛表（2026-09-18） | `r_perp`（值 = 篮 4）；`check_r` / `check_g_cap(g, r)` |
# | A26 | **留存去向审计 → 完整式（valuation-rules「留存去向审计」）**。十年数据（Longbridge af，USD B）：capex 10 / 11 / 10 / 15 / 17 / 30 / 36 / 31 / 30 / 41（2016–25）；净 PP&E 31 → 119 连年上升；净债务 −12 → −64（净现金）；D&A 2022–25 = NT$437 / 532 / 663 / 688B，capex ÷ D&A = 2.6 / 1.8 / 1.4 / 1.9。留存分桶 2023–25（NT$B）：留存 560 / 795 / 1,231，其中净 PP&E 增量 369 / 170 / 461（**E 桶 稳态增长 capex**，无终点），现金增量 123 / 662 / 640（**B 桶**，近两年吃掉留存一半以上）；无 A（还债）/ D（有终点窗口）。→ 倍数形式 = **完整式**（\(b = g/RONIC\) 进公式，v8 已是）；\(1/(r−g)\)（要 NPPE 平或降 ≥3 年 + 去向 A/B）与 \(1/r\)（要派息 ≥80%）都不合法；禁止形态七条未命中。**ROIC 序列**（税后营业利润 ÷ 不含现金投入资本，2017–25）= 34 / 31 / 28 / 38 / 37 / 48 / 32 / 38 / 53%，中位 36.5%，1H26 年化 64%；**净值 ROIC 是资产年龄的函数**：在役资产累计折旧占毛值 65 / 69 / 71%（2023–25），同期毛资产现金回报（税后营业利润 + D&A）÷ 毛 PP&E 只有 24 / 27 / 33%——净值 ROIC 从 29% 到 49% 的抬升约一半来自分母缩水（N7/N5 机台折完仍满产），不是新资本能赚的边际回报（wiki `gordon-pe-roic-scope` §5.5）。**capex 派生 \(g_2\)**：2027E 增长 capex（卖方簇 79 − D&A 32）÷ 净利 114 = 再投资率 41%，× 任何 ≥15% 的边际回报 ≥ 6% 上限，被自身带边 5.249% 挡住——捆住 g2 的是市场付过的价，不是 ROIC。**带边 \(g_2\) 隐含的边际 ROE** = 5.249% ÷ 留存率 69% ≈ 7.6%，远低于账面：自身五年前瞻带上沿把留存的大头按 B 桶现金而非 E 桶产能定价，只披露。B 桶现金：2026-10-15 框架纠正起按 valuation-rules「经营价值与超额现金」单列为超额现金 NT$1,557B ≈ 9.49 美元/ADR、按面值加回锚点（A30）；护栏带同步改读经营倍数（价扣当时超额现金），不再「带本就印在含现金的市值上」。证伪：capex 连续两年 < D&A（转 C 桶）或派息率升到 ≥80% → 重审形式 | active | Longbridge `financial-report --report af` CF/BS/IS 2016–25；yfinance 年报 D&A / 股利 / 毛 PP&E / 累计折旧 2022–25；2Q26 资产负债表；对话 2026-09-21 | 倍数形式（完整式）；`ic_2q26_twd`；披露行「ROIC 与留存去向」 |
# | A27 | **PB-ROIC 机器对照尺（用户口径 2026-09-21；非主尺，不进 `_INDEX`）**：把台积电看成「拿公司指引的 capex 买产能、按边际回报赚利润」的机器，不设永续 g，推 FY28 账面 × 自身 PB 带、折两年。步骤：① 投入资本 \(IC_t = IC_{2Q26} + \sum(capex − D\&A)\)，capex 取**公司前瞻**（2026 指引 600–640 亿中值 62；2027–28 公司无数，按「显著高于 2023–25」+ 谨慎扩产钉 64 持平，卖方簇 77–85 只作对照），D&A 25.5 / 32 / 38 亿外推**待补**；② 盈利 = **已实现基数**（1H26 年化 809 亿，定价权 = 保住现有产能利润，用户定）+ 新增资本 × **折旧后边际回报**（毛资产现金回报 33% − 1/5 年折旧 = 13%，滞后一年产利；**不用净值 ROIC**——那是老资产折完的比率，A26）；③ 账面按留存 69% 滚到 2028 末：BPS_2028 = 67.3，EPS_2028 = 16.86（vs 两家卖方 29.05：机器不承销共识增长），ROE_2028 = 25%；④ 三档只由**五年 PB 四分位** 5.00 / 7.10 / 8.25 定（同 ROE 状态：ROE 26–31% 的年份 2021 / 2023–25 PB 中位 4.75–8.78；十年带下半截印在 2016–19 ROE 21–25%，不同状态）；⑤ ÷ 1.1² → **278.1 / 394.9 / 458.9**，A 336.5 / B 426.9。**为什么只作对照**：(i) PB 分位不是 g-free——在 ROE_2028 25% 下反读永续 g = 6.2 / 7.5 / 7.9%，M/H 越 6% 上限，等于让 2021 年高预期印出来的 PB 替尺子定 g；(ii) 仓规「经营腿倍数由增长率生成、历史分位降级为护栏」；(iii) L 没有具名坏世界（盈利不退坡，下行全靠 PB）；(iv) 刻意丢掉 2028 两家共识。**它的用处**：拆主尺 M 的读数（主尺 M ≈ 五年 PB 中位 × FY28 账面折回今天 + 一截共识增长）、deep_discount 侧坐标（PB 回 5.0× → 278）、第二把尺的对照带。灵敏度几乎全在 PB 分位：capex × 回报只贡献 2028 净利的 4%，回报 13% → 36.5% 对 M 仅 +3。升级：公司给 2027 capex → 替换 64；D&A 指引 → 替换外推 | active | 2Q26 法说 capex 指引（Longbridge 293855759 / Wisburg 96268 / 96211）；HSBC 95855 2027 capex 802 亿；GS 78 / Citi 77 / BofA 80–85（WebSearch 2026-09-21）；Longbridge `valuation --history --indicator pb --range 10`；yfinance 毛 PP&E / 累计折旧；对话 2026-09-21 | `capex_*`、`da_*`、`cash_return_gross`、`dep_life`、`pb_5y_*`、`n_disc`；表2″ |
# | A28 | **RONIC 口径 = 分子年经营利润 ÷ 分子年年初经营股权（\(E_{n+1}/B_n\)，按档），账面按增长所需留存滚动（valuation-rules 裁决表 ② / 两段式过渡，2026-09-21 定；2026-10-15 框架纠正只多扣超额现金，不做防峰值）**：\(RONIC_x = E^{op}_{2027,x} ÷ OBPS_{2027 年初,x}\)，Gordon 的 \(g = b × RONIC\) 里 RONIC 是期初经营股权产出本期经营利润，年末口径会把本年尚未产出的留存放进分母。2027 年初 = 2026 末：从 2Q26 经营股权（归母权益 6,432.5B − 超额现金 1,557.2B = 29.73 美元/ADR）起、只滚 **2H26 尚未入账**的经营利润（2026E 共识 16.93 扣 1H26 实测 1,279B = 9.13，再扣半年现金税后收益 0.15 = 8.98 美元/ADR），**留存率 = \(b_1 = g/RONIC\)**——M/H 用全公司经营利润 \(g_1\) 27.2%（各腿 g 按权重加总即它，与 `two_stage_pe` 段一同一个 b），L 无窗口用 \(g_2\) 5.249%；闭式解 \(OBPS = OBPS_{2Q26} / (1 − g × 8.98 / E^{op}_x)\)。得经营 BPS_2027 年初 = 30.47 / 33.51 / 33.04、RONIC **63.3 / 64.5 / 73.6%**、\(b_1\) = 0.083 / 0.421 / 0.369。四腿共用公司整体前瞻回报（20-F 单一晶圆代工分部，无卖方腿级 ROIC，拆不开）；持续失败不触发（2023–25 年初口径经营回报 31.0 / 35.5 / 47.4%，均 > r）；历史回报只披露：2021–25 中位 35.5%。旧账面口径（不拆现金）为 BPS 40.2 / 44.1 / 43.5、ROE 48.7 / 49.7 / 56.5%。实付留存（69%）超出 \(b_1\) 的部分是多留部分，落在超额现金上（λ 1，A30），走 Outputs「多留部分」行（MUST NOT 另作腿）。以下三条被否的口径是旧账面口径的留痕，未按经营口径重算：v8 用 2027E 利润 ÷ 2Q26 权益 = 50 / 56 / 63%（分母少半年留存，g2 5.36%，底牌 349.3 / 473.7 / 538.8）；按**实付**留存 69% 滚到 2027 **末** = 33 / 36 / 39%（把堆现金的留存和本年未产出的留存都滚进分母，底牌 349.9 / 471.4 / 538.3）；按 \(b_1\) 滚到 2027 **末** = 46 / 35 / 40%（年末口径，L 因不留存而 ROE 最高、L 抬到 368.2，底牌 368.2 / 467.3 / 539.1）——后两条是 2026-09-21 当天先后被规则否掉的写法。当时账面口径底牌 352.5 / 472.3 / 539.2 与 v8 差 +1% / 0% / 0%：分母只多了半年增长所需留存，H 钉带上沿不动。RONIC 仍是净值口径、含老资产折完的成分（A26），但只进派息率系数，不进边际回报 | active | yfinance 2Q26 权益 / 1Q26–2Q26 净利 / 2023–25 股利；2026E 共识 2026-09-11；valuation-rules 2026-09-21 / 2026-10-15；对话 2026-09-21 | `eps_2026_m`、`ni_1h26_twd`、`payout_3y`（只进多留部分行与 A27）、`fx_twd`、`c_ex`；表1 RONIC 列 |
# | A30 | **超额现金单列**（valuation-rules「经营价值与超额现金」，2026-10-15 框架纠正）：扩展口径净现金 2Q26 = 现金类 3,597.4 − 有息负债与租赁 1,067.9 = 2,529.5B，扣已宣派未付股息 337.4B = 2,192.1B；**客户为保留产能支付的暂收款 234.2B 不扣**——不可退还、随交付冲抵货款，属经营负债。经营所需现金锚 = min(2021–2025「扩展口径净现金 ÷ 收入」最低值 19.3%（2021）, 2 个月收入 16.7%) = 16.7% × FY2025 收入 3,809.1B = **634.9B**（放宽到 2016–2025 最低值仍是 2021，锚不变）→ **超额现金 NT$1,557.2B = 9.49 美元/ADR，占归母权益 24.2% ≥ 15% → 单列**（2026-10-16 起按归母份额 99.35% 计：NT$1,547.2B = **9.43** 美元/ADR、税后收益 0.295，A31；本行以下读数为纠正前口径）。现金收益率 FY2025 3.77%、实际税率 17.0% → 三档分子同扣税后收益 **0.297 美元/ADR**；RONIC 分母同扣超额现金（A28）；护栏带两端改读经营倍数（A7）。历史各年超额现金按同一锚比率 × 当年收入缩放（2021 = 42.1B、2024 = 732.2B、2025 = 1,140.4B）。**λ = 1**：无资金受限；现金所在地（母公司或海外子公司）20-F 未按实体拆、未核；少数股东权益 42B 只占超额现金 3%；近 5 年无现金并购；亚利桑那等海外厂是具名政策性投资，但财报无其回报低于 r 的数（管理层只讲毛利率稀释 2–3pp），不构成证据。留存拆分（2021–2025，分母 = 经营利润合计 5,229.3B）：分红（宣派口径）35.0% / 员工持股回购 0.1% / 还债 0 / 现金积累 18.9% / 经营再投资 47.0%，合计 101.0%（差 −1.0pp，来自其他综合收益与汇率，< 10pp）；经营口径派息率 = 分红 + 现金积累 = **53.9%**（`payout_op`）。稳态约束：\(b = g_2/RONIC_M\) = 0.081 ≤ 1 − d = 0.65 ✓；\(g_2\) ≤ (1 − d) × RONIC_M = 44.5% ✓；|i − b| > 10pp 属扩张期（2020→2025 经营利润年复合 26.7%），只披露。证伪 / 重看：λ 证据清单任一项出现；超额现金被大额收购或政策性投资消耗；客户暂收款合同改为可退还 → 改按类债项扣 | active | 2Q26 财报附注 20c（暂收款、应付股息）；20-F 2025 附注 22c；SEC companyfacts `CurrentDividendPayables`；yfinance 2Q26 / 2025 资产负债表（有息负债总额）；`_local/tmp/land_v6/TSM.US/calc.py` | `net_cash_ext_2q26` / `div_declared` / `rev_2025_twd` / `cash_ratio_low` / `c_ex` / `cash_yield` / `tax_eff` / `payout_op`；三档各加 9.49 |
# | A29 | **巨型硬件上限：定价权豁免（valuation-rules「巨型硬件上限」，2026-09-27 定）**：本票是硬件（晶圆代工交付实物），分子年收入 2027E NT\$7,297 亿 ÷ 31.63 ≈ **\$2,310 亿** ≥ \$1,500 亿，但**两条定价权判据都满足 → 豁免**，平台腿 g2 仍受普通上限 6%（现行 5.842% 由自身实测带反解给出，A7 / A31，本条不改任何锚点）。(a) **无已量产的合格第二供应商**：N3 / N2 先进制程没有在大客户处起量的替代——三星代工与英特尔代工尚未在主要 AI / 手机客户量产（本框架 §3 deep_discount 把「先进制程被 Intel 14A / 三星分流」列为未命名坏事）；(b) **上一轮行业下行期维持并上调价格**：2023 年行业下行中台积电再提价约 5%（2022 年约 10%），让步只在光罩费、未降晶圆代工价（Tom's Hardware / TrendForce 报道）；同期联电 2023Q4 12 吋报价降 10–15%、8 吋约 20%，中韩成熟制程降 20–30%，三星代工折扣最高 15%（TrendForce 2024-01-04）；2023Q4 晶圆出货同比 −20%、收入仅 −1.5%，平均晶圆售价同比 +22%（含产品结构升级，非纯同品涨价）；公司 20-F（FY2023）把毛利率 59.6% → 54.4% 归因于产能利用率下降与 3 纳米爬坡，未提降价。前瞻：2026-09 报道 2027-01 起再提价 3–6%。**口径声明**：公司不披露价格，(b) 的价格证据来自媒体与研究机构报道；一手披露只有 20-F 的毛利率归因。**证伪点**：下一次行业下行中台积电跟随同行下调先进制程晶圆价，或三星 / 英特尔在 N3 / N2 同代节点拿下一家前五大客户量产 → 豁免失效，平台腿 g2 改按巨型硬件上限 4%（超出部分进候选带） | active | TSMC 20-F FY2023 / 2023 年报第 6 章；Tom's Hardware 2022-2024；TrendForce 2024-01-04；Benzinga 2026-09；对话 2026-09-27 | `g2`；A7 |
# | A31 | **经营价值与超额现金：归母份额、稳态回报三段、时点对齐（valuation-rules「经营价值与超额现金」①–④，2026-10-16 框架纠正）**。① **归母份额**：超额现金只取归母那份——归母比例 = 归母权益 6,432.5B ÷（归母 + 少数股东 42.0B）= **99.35%**（无子公司级现金披露）→ 进估值、扣分子收益、扣 RONIC 分母的都是 NT$1,547.2B = **9.43** 美元/ADR、税后收益 0.295；**增长期资金缺口**：2H26 资本开支由经营现金流覆盖，G = 0。② **稳态回报三段**：可见年 2027 用前瞻回报 63.0 / 64.4 / 73.5%（A28；四腿共用）→ 维持到 **Y1 = 2030** → 线性回落到 **Y2 = 2035** → 稳态永续（用户 2026-10-16 定；光通信链「封装、光电共测」环节、高门槛）。**稳态 35.0%**（2026-10-19 按序取，原三层取大的 35.2%）：**自身周期可用 → 取自身**，最近一轮完整谷到谷周期 = **FY2019–FY2023**（营业利润与回报的谷：2019 年 26.3%、2023 年 30.0%），投入资本口径（税后营业利润、不扣利息，税率取 20-F 实际税率 ÷ 年初（总权益含少数股东 + 有息负债 + 租赁 − 超额现金，经营现金锚 16.7% × 收入））各年 26.3 / 36.6 / 36.5 / 45.5 / 30.0%，**均值 35.0%**（Longbridge 年报 USD；旧口径——净利扣超额现金收益 ÷ 归母权益扣超额现金——同窗口均值 35.7%，2017–2025 中位 35.2%）；成熟代工同业（近 5 个年度区间收入复合增速 ≤ 10% 且不负、≥ 5 年读数、剔除本票：高塔 19.4 / 联电 16.9 / 格芯 3.0%，华虹 +20.2% 不成熟）中位 16.9% 与 `_AXIS.ai-capex` 封装、光电共测环节的稳态兜底 20%（`ss_floor_ai_capex_package`，用户 2026-10-19 暂定）只作对照、不进值。三档前瞻都高于 35.0%，都回落。本票不挂 `_AXIS.leading-edge-foundry`，不读轴值；不属「叙事换代」（规则点名台积电照走三段，自身周期可用）。不属商品腿豁免。成熟晶圆、B2、B1 地板与 COUPE 期权同走这条路径（COUPE 从兑现年 2028 起算）。③ **时点对齐**：Gordon 给的是 2027 年初（RONIC 分母时点，A28）的价值；τ = 2026-06-30 → 2027-01-01 = 0.5 年。先进晶圆、成熟晶圆、B2 与取地板的 B1 折 τ；B1 取 CoWoS 产能值时不折（今日产能读数）；超额现金不折；窗口可分配利润 = 2H26 尚未入账经营利润 8.99 美元/ADR × (1 − \(b_1\))（\(b_1\) = 账面滚动同一个 g/RONIC：L 按 g2、M/H 按 g1 27.2%），按 τ/2 折 → **7.96 / 5.07 / 5.53**；COUPE 折到 2027 后再折 τ。④ **g2 配对**：g2 由本票自身价格带反解，按规则用同一条回报路径重解，靶改为今天的经营倍数（锚点扣超额现金 ÷ 经营 EPS）：H 档触上沿 21.85× → **5.842%**（原 5.249%；稳态 35.2% 时为 5.838%，2026-10-19 稳态改 35.0% 后同法重解；< 6% 上限；稳态段留存 5.84 / 35.0 = 17% ≤ 1 − 派息 65%）——回报回落与折现都压低倍数，g2 抬高把它吃回，H 仍钉在 541.0。⑤ 不带打折 k。**影响**：L / M / H 354.9 / 476.4 / 541.0 → **362.8 / 480.0 / 541.0**（M +0.8%：时点对齐 −3.5%、归母份额 −0.03%、三段与 g2 配对 +4.3%），未触发纠正对账门；\(V_{opt}\) 20.61 → **20.55**。**敏感**（不采）：稳态不认自身周期、落到同业 / 兜底层时 g2 碰 6% 上限 → 同业 23% 读数 346.6 / 456.9 / 515.3、兜底 15% 读数 306.2 / 403.3 / 451.8（M −15%）。A7、A13、A21、A28、A30 等行带具体值的推导读数除注明外为纠正前口径，现行值以 §0 与 Outputs 为准 | active | valuation-rules「经营价值与超额现金」；Longbridge 年报（自身周期、代工同业穿越周期）；2Q26 资产负债表（少数股东）；对话 2026-10-16 | `parent_ratio`、`tau`、`y1`、`y2`、`rs_steady`、`g2`；锚点、\(V_{opt}\) |
# 原框架历史；本次迁移没有新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-09-20
# - v2 切换（篮子 r）：L/M/H v1 349.3 / 473.7 / 538.8 → 349.3 / 473.7 / 538.8（不变），zone `neutral` → `neutral`（修正带 `neutral` 不变）；篮子：先进晶圆 / 成熟晶圆（含 B1 / B2）两腿同归篮 4 龙头制造 10%（与 v1 `r_perp` 同值，无备选篮，A25）；平台 g2 5.36%（带边反解，靶 = 合并 PE）、成熟 / B2 2% 保留（cap = min(6%, r − 4%) = 6% 未收紧）；新增披露行：隐含 r(P) ≈ 10.4%、③ 出带（在带内）、敏感区（g2 −1pp 仍 `neutral`，不翻转）、地板不适用；eval 改为 `parse_baskets` + `check_r(r, 篮)` + `check_g_cap(g, r)`，并打印隐含 r(P)
# - touched: [A7, A25, r_perp, g2, 表1, 披露行]
# ### 2026-10-03
# - 迁移到 2026-10-03 规则（valuation-rules「未建模期权」「数据优先级与同业同尺」；construction §7c-1）：v9 → v10。COUPE \(V_{opt}\) 三档统一按 2028 量 × 平台稳态 PE（本档 ROE）在 2028 估值、篮 4 折回一年（v9 的 L / H 用平台两段式 PE、不折现 = 在兑现年另开过渡）→ \(V_{opt}\) 28.12 → 20.85，\(p_k\) 0.058 / 0.361 / 1.0 → 0.0715 / 0.4866 / 1.0，zone+V 354.1 / 482.5 / 567.3 → 354.0 / 482.5 / 560.1；L/M/H 352.5 / 472.3 / 539.2 不变（纠正对账门不触发）。COUPE 份数仍为轴量 × 拍定分成，标「份数非本票具名·待闭合」并写升级门槛；A5 记腿级经济性来源层级（制程 mix × 毛利率联立病态 → 退到共享规则）。新增 Inputs `t_coupe`
# - touched: [A5, A19, t_coupe, Formula 步 11, 表3, Outputs V_opt 行, eval]
# ### 2026-10-05
# - 措辞：区分磷化铟衬底与激光芯片（用户 2026-10-05 用词禁令；数值不变）
# ### 2026-11-06
# - 选后 AI / 数据中心监管风险讨论后，按用户要求新增永续增速 4% 压力候选，并使用 App 候选带展示：282.5 / 378.5 / 418.3，切点 330.5 / 398.4。仅改变先进晶圆 / B1 尾段增长；盈利共识、2028 过渡、投资回报路径与主尺保持原值。该压力值不代表政策损失预测；本次未作三季报复核或更新共识。
# - touched: [A32, g2_candidate, 候选带, 表2c, eval]
INPUTS = {
    # 稀释 ADR 数（1 ADR = 5 普通股）; 来源：2025-12-31
    'shares_adr': 5.186e9,
    # 股东权益 USD = 2Q26 资产负债表 TWD 6,432.5B（2026-06-30，yfinance）÷ 即期 31.63 TWD/USD（2026-09-11）；扣 `c_ex` 后是三档 RONIC 的**起点**——按增长所需留存 \(b_1=g/RONIC\) 滚过 2H26 到 2027 年初再作分母（A28），不直接作分母; 来源：2026-06-30
    'equity': 2.034e11,
    # 扩展口径净现金 2Q26（TWD）= 现金及等价物 + 流动金融资产 3,597.4B − 有息负债（公司债 + 借款）与租赁负债 1,067.9B（有息负债用 yfinance 总额，流动租赁约 3B 为估计）；**不扣**客户为保留产能支付的暂收款 234.2B（A30）; 来源：2026-06-30
    'net_cash_ext_2q26': 2.5295e12,
    # 已宣派未付现金股息 NT$337.4B（2Q26 财报附注 20c 应付股息）；类债项; 来源：2026-06-30
    'div_declared': 3.374e11,
    # FY2025 营收 NT$3,809.1B（20-F）；经营所需现金锚的缩放基数; 来源：2025-12-31
    'rev_2025_twd': 3.8091e12,
    # 2021–2025「扩展口径净现金（扣应付股息、不扣客户暂收款）÷ 收入」最低值（2021：306.7 ÷ 1,587.4）；锚比率 = min(本值, 2 个月 16.67%) = 16.67%（A30）; 来源：2025-12-31
    'cash_ratio_low': 0.1932,
    # 超额现金 = `net_cash_ext_2q26` − `div_declared` − 锚 16.67% × `rev_2025_twd`（634.9B）= NT$1,557.2B，占归母权益 24.2%（A30）；进估值、扣分子收益、扣 RONIC 分母的是它 × `parent_ratio`（A31）; 来源：2026-06-30
    # 归母比例 = 归母权益 NT$6,432.5B ÷（归母 6,432.5B + 少数股东 42.0B），2Q26 资产负债表；无子公司级现金披露（valuation-rules ① 归母份额；A31）; 来源：2026-06-30
    'parent_ratio': 0.99352,
    # 时点对齐年数 = 估值基准日 2026-06-30（超额现金的资产负债表日）→ 分子年 2027 年初 2027-01-01；Gordon 经营价值按 `r_perp` 折 τ、窗口可分配利润折 τ/2；B1 取 CoWoS 产能值时不折（A31）; 来源：2026-10-16
    'tau': 0.5,
    # 高回报期止点 Y1（用户 2026-10-16 定，封装 / 光电共测环节、高门槛）；A31; 来源：2026-10-16
    'y1': 2030,
    # 稳态起点 Y2（Y1 → Y2 线性回落）；A31; 来源：2026-10-16
    'y2': 2035,
    # 稳态回报按序取（2026-10-19）= **自身最近一轮完整谷到谷周期 FY2019–FY2023**（谷 2019 / 2023）投入资本口径经营回报均值 35.0%（税后营业利润 ÷ 年初（总权益 + 有息负债 + 租赁 − 超额现金））；自身可用即取自身，成熟代工同业中位 16.9% 与兜底（`_AXIS.ai-capex` `ss_floor_ai_capex_package` 20%）只作对照；三档按「≤ 该档前瞻」封顶（A31）; 来源：2026-10-19
    'rs_steady': 0.350,
    # 现金收益率 FY2025 = 利息收入 105.7 ÷ 平均现金类资产 2,806.6（NT$B）；A30; 来源：2025-12-31
    'cash_yield': 0.037661,
    # 实际所得税率 FY2025 = 所得税 346.5 ÷ 税前 2,041.7（NT$B）；A30; 来源：2025-12-31
    'tax_eff': 0.16971,
    # 经营口径派息率 = 分红（宣派口径）0.350 + 现金积累 0.189，窗口 2021–2025，分母 = 经营利润合计 NT$5,229.3B；`check_branch` 用（A30）; 来源：2025-12-31
    'payout_op': 0.539,
    # 2Q26 合并营收 NT$1,270.38B（$40.20B）；×4 = 成熟晶圆 $ pin 的年化基期；A24; 来源：2026-07-16
    'rev_2q26_twd': 1.27038e12,
    # 2027E 营收共识均值 NT$7,297.3B（yfinance +1y，+34.2%）；pin 桥分母；A24; 来源：2026-09-11
    'rev_2027_twd': 7.2973e12,
    # 2027E 共识 EPS **低端**（13 家）= L 分子；A17 / A20; 来源：2026-09-11
    'eps_2027_l': 19.58,
    # 2027E 共识 EPS **均值**（13 家）= M 分子；A20; 来源：2026-09-11
    'eps_2027_m': 21.9251,
    # 2027E 共识 EPS **高端**（13 家）= H 分子；A20; 来源：2026-09-11
    'eps_2027_h': 24.62436,
    # 2027E 卖方 EPS 均值（TWD/普通股，五家：HSBC 137.29 / GS 140.91 / JPM 141.37 / Citi 151.93 / BofA 153.17）；g1 的分母；A22; 来源：2026-08-31
    'eps_2027_cons_twd': 144.93,
    # 2028E 卖方 EPS 均值（TWD/普通股，两家：JPM 180.01 · DB 187.5 = TP 3000 ÷ 其 16× 2028E）；g1 的分子；A22; 来源：2026-07-17
    'eps_2028_cons_twd': 183.76,
    # 过渡年数（仅 2028E），只在 M/H 档；A22; 来源：2026-09-14
    'n_stage': 1,
    # 有 ≥2 家共识的远期年数（2028E）；2029E 无任何卖方 EPS；`check_transition_years`; 来源：2026-09-14
    'n_consensus': 1,
    # 晶圆收入占比（先进+成熟合计）；A4; 来源：2026-09-13
    'share_wafer': 0.83,
    # 先进封装占比；A4; 来源：2026-09-13
    'share_adv': 0.11,
    # 其余后端占比；A4; 来源：2026-09-13
    'share_other': 0.06,
    # as-of 成熟（>7nm）占**晶圆营收**比重（2Q26：N2 3% / N3 30% / N5 33% / N7 11% = 先进 77%；FY2025 为 26%）；A24; 来源：2026-07-16
    'mat_of_wafer_asof': 0.23,
    # 2Q26 N7 占晶圆营收；只作「N7 归成熟」对照行，不进锚点；A24; 来源：2026-07-16
    'n7_of_wafer_asof': 0.11,
    # L 档净利率机制 = 2025 实测（20-F）；只作 A17 校验，分子直接取共识低端; 来源：2025-12-31
    'npm_2027e_l': 0.446,
    # 2027E 共识均值**隐含**净利率 = `eps_2027_m` × `shares_adr` × `fx_twd` ÷ `rev_2027_twd` = 49.28%（eval 复算）；A17 机制的参照。1H26 实测 53.2%（NT$1,279.1B ÷ 2,404.5B，yfinance 季度利润表）只作快照，不进分子；A15; 来源：2026-09-11
    # 实付派息率 TTM（yfinance payoutRatio 25.7%）；只作披露——`check_branch` 改用经营口径 `payout_op`（A30）; 来源：2026-09-16
    'payout_ttm': 0.26,
    # 平台永续增速（先进晶圆 + B1），**自身实测带反解，经营口径**：H 档**今天的经营倍数**（今天的经营价值含窗口 ÷ 经营 EPS；稳态回报三段与时点对齐同走，A31）触经营带上沿 `pe_op_max` 21.85× 的 g2 = 5.8425%（稳态 35.0%，2026-10-19 按同一回报路径重解；稳态 35.2% 时为 5.8381%），取 5.842%（贴上沿内侧）；纠正前（不走三段、不折 τ）为 5.249%；cap = min(6%, r − 4%) = 6%（篮 4）未收紧；稳态段留存 5.84 / 35.0 = 17% ≤ 1 − 派息；A7 / A25 / A28 / A31; 来源：2026-10-19
    'g2': 0.05842,
    # 用户指定的永续增速压力值，只替换先进晶圆 / B1 的尾段；其余输入冻结，不重新反解 g2 或滚动期初经营股权；A32; 来源：2026-11-06
    'g2_candidate': 0.04,
    # 成熟晶圆永续增速，**自身实测 CAGR 上界**（成熟 $ 营收 2022→2Q26 年化 ≈ +1%）；UMC 同尺反解 7.5% 只作交叉；不背 \(g_1\)；A24; 来源：2026-09-16
    'g_mat_wafer': 0.02,
    # B2 其余后端永续增速，业界传统封装公允；不背 \(g_1\)；A23; 来源：2026-09-16
    'g_b2': 0.02,
    # 先进晶圆 / 成熟晶圆（含 B1 / B2）两腿永续折现率 = **篮 4 龙头制造** 10%（无备选篮）；值 = `gordon.BASKET_R`；A7 / A23 / A24 / A25; 来源：2026-09-20
    'r_perp': 0.10,
    # 倍数护栏下沿：自身已实现前瞻 PE 带低点（2025-03 月末价 163.59 ÷ 2026E 共识 16.93）；A7; 来源：2026-09-11
    'pe_own_min': 9.7,
    # 合并口径自身已实现前瞻 PE 带高点（2022-01 ÷ 2023 实际；2026-06 ÷ 2027E 共识同为 21.8×）；经营带上沿由它重读；A7; 来源：2026-09-11
    'pe_own_max': 21.9,
    # 经营口径带下沿：2025-03（价 163.59 扣当时可见 FY2024 超额现金每 ADR 4.40，利润 16.93 扣其税后收益 0.15）；不约束；A7; 来源：2026-10-15
    'pe_op_min': 9.49,
    # **倍数护栏上沿（经营口径）**：2022-01 月末价 `px_edge_hi` 扣当时可见 FY2021 超额现金每 ADR 0.29 ÷（2023 实际 EPS 扣其税后收益）= 21.854；2026-06 点经营口径 21.68（扣每 ADR 8.45）低于它；eval 复算；A7; 来源：2026-10-15
    # 2022-01 月末收盘（Longbridge 月 K）；与 `pe_own_max` 联立得当时 EPS 分母 5.60; 来源：2022-01-31
    'px_edge_hi': 122.63,
    # FY2021 末超额现金 = 净现金 449.3 − 应付股息 142.6 − 16.67% × 收入 1,587.4（NT$B）；2022-01 可见报告; 来源：2021-12-31
    'cex_edge_hi_twd': 4.21e10,
    # 2021 年 TWD/USD 均值（折当时每 ADR 超额现金）; 来源：2021-12-31
    'fx_edge_hi': 28.0,
    # FY2021 现金税后收益率 = 利息收入 5.7 ÷ 平均现金类 1,003.7 ×（1 − 税率 10.6%）; 来源：2021-12-31
    'aty_edge_hi': 0.00508,
    # L 档 CoWoS 产能 = YE2026 130k × 0.5「只兑现一半」；A9; 来源：2026-09-12
    'cowos_wpm_l': 65000,
    # YE2027 轴（`_AXIS.cowos-capacity.md` §1，200k wpm）；A9; 来源：2026-08-28
    # H 档同 2027 满产（分子年 2027E，不再引 YE2028 260k——那是 stretched 的解释）；A9; 来源：2026-09-14
    # B1 产能项单位价值 USD / 万片·月（7nm UV 锚，对话；原始研报 ID 待补）；A8; 来源：2026-09-01
    'uv_per_10k_wpm': 1.28e10,
    # CPO/NPO 实际 OE 出货 L；`_AXIS.optical-comms.md` §1（2028 推迟一年；数值借大摩 2027E）; 来源：2026-10-02
    # 同上 M（广发证券（香港）2028E scale-up NPO）; 来源：2026-10-02
    # 同上 H（大摩 2028E）; 来源：2026-07-10
    # 高盛 CPO 交换机整颗 OE BoM USD（非可插拔、非台积代工价）; 来源：对话
    # 台积占 OE BoM 分成 L（PIC+键合，防与腿 A 双计）; 来源：2026-09-13
    'coupe_share_l': 0.25,
    # 同上 M; 来源：2026-09-13
    'coupe_share_m': 0.33,
    # 同上 H（溢价从光源迁入 COUPE）; 来源：2026-09-13
    'coupe_share_h': 0.55,
    # COUPE 腿净利率（与 M/H 经营净利率同；A5 共享规则）; 来源：2026-09-13
    'npm_coupe': 0.50,
    # COUPE 兑现年 = 轴三档量的年份（卖方 2028E）；公司具名的只有 CPO 量产验证 2026；\(V_k\) 在此年估值、按篮 4 折回 2027；A19; 来源：2026-10-03
    't_coupe': 2028,
    # 即期 TWD/USD，`equity` 与 `ni_1h26_twd` 的折算率；A16; 来源：2026-09-11
    'fx_twd': 31.63,
    # 2026E 共识 EPS 均值（USD/ADR）；只用于把 2H26 尚未入账的利润滚进 2027 年初净资产；A28; 来源：2026-09-11
    'eps_2026_m': 16.93,
    # 1H26 归母净利 NT$1,279.1B（1Q26 572.5 + 2Q26 706.6）；已入账、从 2026E 里扣掉；也是 A27 机器尺的盈利基数（×2 年化）；A27 / A28; 来源：2026-07-16
    'ni_1h26_twd': 1.2791e12,
    # 近三年实付派息率均值（2023 34% / 2024 31% / 2025 27.5%，股利 ÷ 归母）；留存率 69% 只用于 A27 机器尺的账面推演（那是实际账面，不进倍数）和 Outputs「多留部分」行；**不进**主尺的经营 BPS 推演（主尺按 \(b_1=g/RONIC\) 滚，A28）; 来源：2025-12-31
    'payout_3y': 0.31,
    # 2Q26 经营投入资本 = 权益 6,432.5 + 有息债 1,064.9 − 现金 3,134.2（NT$B，不含现金）；A26 / A27; 来源：2026-06-30
    'ic_2q26_twd': 4.363e12,
    # 2026 资本开支指引 600–640 亿美元中值（2Q26 法说，由 520–560 上调）；A27; 来源：2026-07-16
    'capex_2026': 62e9,
    # 2027 资本开支：公司未给数，按「2026–28 显著高于 2023–25」+ 谨慎扩产钉在 2026 指引上沿持平；卖方簇 GS 780 / Citi 770 / HSBC 802 / BofA 800–850 只作对照；公司给数即替换；A27; 来源：2026-09-21
    'capex_2027': 64e9,
    # 同上；A27; 来源：2026-09-21
    'capex_2028': 64e9,
    # 2026E 折旧摊销：2Q26 D&A NT$198.5B 年化外推；**待补**公司指引；A27; 来源：2026-09-21
    'da_2026e': 25.5e9,
    # 2027E 折旧摊销外推；**待补**；A27; 来源：2026-09-21
    'da_2027e': 32e9,
    # 2028E 折旧摊销外推；**待补**；A27; 来源：2026-09-21
    'da_2028e': 38e9,
    # 毛资产现金回报 =（税后营业利润 + D&A）÷ 平均毛 PP&E，FY2025 实测（2023–25：24 / 27 / 33%）；新增资本的折旧前边际回报，取高分位（AI capex 背景，A27）；不是净值 ROIC（那是资产年龄的函数，A26）; 来源：2025-12-31
    'cash_return_gross': 0.33,
    # 设备直线折旧年限（台积电会计政策）；新资本折旧期内的折旧后回报 = `cash_return_gross` − 1/5；A27; 来源：2025-12-31
    'dep_life': 5,
    # 自身月度 PB 五年（2021-10→2026-09）低四分位；Longbridge `valuation --history --indicator pb`；A27; 来源：2026-09-21
    'pb_5y_q1': 5.00,
    # 同上中位（十年中位 5.22 只作对照：其下半截印在 2016–19 ROE 21–25% 的状态，与 FY28 不同状态）；A27; 来源：2026-09-21
    'pb_5y_med': 7.10,
    # 同上高四分位；A27; 来源：2026-09-21
    'pb_5y_q3': 8.25,
    # 机器尺 FY28 账面价折回今天的年数（FY28 = t = 2）；A27; 来源：2026-09-21
    'n_disc': 2,
}
BASKETS = {"r_perp": 4}
REQUIRED = (frozenset(INPUTS) - {"n7_of_wafer_asof"}) | {'cowos_wpm_m','cowos_wpm_h','oe_l','oe_m','oe_h','asp_oe'}

def path_value(g1: float, n: int, g2: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple (on numerator-year earnings, valued at the start of the numerator year)
    on the steady-state-return path (valuation-rules「经营价值与超额现金」② 稳态回报三段;
    gordon.py's three-segment function is not built yet, so it lives here).

    Calendar years, t = 1 is the numerator year t0.  The first n years grow at g1 with payout
    1 - g1/RONIC (two_stage_pe's stage 1); afterwards growth is g2 and RONIC = the tier's
    forward value through Y1, falls linearly to the steady value R_s by Y2 (R_s capped at the
    forward value), then the Gordon tail.  With R_s >= forward it equals two_stage_pe /
    perpetual_pe exactly (A31)."""
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
def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    # r is a basket, not a dial: the r row must name its basket in the Inputs
    # source cell and carry that basket's value (A25, valuation-rules「§r 篮子」).
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    for key in ("g2", "g_mat_wafer", "g_b2"):
        errs += check_g_cap(inp[key], inp["r_perp"], key)
        gap = inp["r_perp"] - inp[key]
        if gap <= 0:
            errs.append(f"perpetuity diverges: {key} >= r")
        elif gap < MIN_R_MINUS_G:
            errs.append(f"r - {key} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errs += check_transition_years(int(inp["n_stage"]), int(inp["n_consensus"]), "n_stage")
    if inp["eps_2028_cons_twd"] <= inp["eps_2027_cons_twd"]:
        errs.append("2028E consensus below 2027E: the transition year has no growth to name")
    if inp["rev_2027_twd"] <= 4.0 * inp["rev_2q26_twd"]:
        errs.append("rev_2027_twd <= 2Q26 run-rate: pin-bridge for mature wafer share would not shrink")
    errs += ladder("numerator (2027E low/mean/high)", inp["eps_2027_l"], inp["eps_2027_m"], inp["eps_2027_h"])
    # A15: the M margin is the one the consensus mean implies, not the 1H26 run-rate.
    npm_implied = inp["eps_2027_m"] * inp["shares_adr"] * inp["fx_twd"] / inp["rev_2027_twd"]
    if abs(npm_implied - inp["npm_2027e_m"]) > 0.005:
        errs.append(f"npm_2027e_m={inp['npm_2027e_m']:g} vs consensus-implied {npm_implied:.4f} (A15)")
    mech = inp["eps_2027_m"] * inp["npm_2027e_l"] / inp["npm_2027e_m"]
    if abs(mech / inp["eps_2027_l"] - 1.0) > NPM_TOL:
        errs.append(
            f"A17 mechanism: mean × {inp['npm_2027e_l']:g}/{inp['npm_2027e_m']:g} = {mech:.2f} "
            f"vs consensus low {inp['eps_2027_l']:g} (> {NPM_TOL:.0%} apart)"
        )
    share_sum = inp["share_wafer"] + inp["share_adv"] + inp["share_other"]
    if abs(share_sum - 1.0) > 1e-6:
        errs.append(f"leg shares sum {share_sum} != 1")
    if not (0.0 < inp["mat_of_wafer_asof"] < 0.5):
        errs.append(f"mat_of_wafer_asof={inp['mat_of_wafer_asof']} expected in (0, 0.5)")
    if not (inp["cowos_wpm_l"] < inp["cowos_wpm_m"] <= inp["cowos_wpm_h"]):
        errs.append("cowos_wpm ladder: expected L < M <= H")
    # Mature / B2 g must sit at or below platform g2.
    for key in ("g_mat_wafer", "g_b2"):
        if inp[key] > inp["g2"] + 1e-9:
            errs.append(f"{key}={inp[key]:.4f} > g2={inp['g2']:.4f} — non-bottleneck leg cannot outgrow platform")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errs.append(f"p-class fields must not appear in Inputs: {leaked}")
    return errs



def evaluate(inp: dict[str, float],rate_inputs=None) -> dict:
    inp=dict(inp)
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp,('n_stage','n_consensus','y1','y2'))
    inp['npm_2027e_m']=round(inp['eps_2027_m']*inp['shares_adr']*inp['fx_twd']/inp['rev_2027_twd'],3)
    baskets = BASKETS
    errors = sanity_checks(inp, baskets)
    review_flags=[]
    r = inp["r_perp"]
    g2, g_mat, g_b2 = inp["g2"], inp["g_mat_wafer"], inp["g_b2"]
    n = int(inp["n_stage"])
    g1_eps = inp["eps_2028_cons_twd"] / inp["eps_2027_cons_twd"] - 1.0
    eps_cons = {"l": inp["eps_2027_l"], "m": inp["eps_2027_m"], "h": inp["eps_2027_h"]}

    # --- excess cash (经营价值与超额现金 ①②) ------------------------------------
    fx, sh = inp["fx_twd"], inp["shares_adr"]
    anchor_ratio = max(min(inp["cash_ratio_low"], TWO_MONTHS), 0.0)
    cash_anchor = anchor_ratio * inp["rev_2025_twd"]
    c_ex_gross = inp["net_cash_ext_2q26"] - inp["div_declared"] - cash_anchor
    # Parent share (valuation-rules ① 归母份额, A31): only the parent's share of the excess cash
    # enters the value, the numerator's income deduction and the RONIC book.
    pr = inp["parent_ratio"]
    if not 0.9 < pr <= 1.0:
        errors.append(f"parent_ratio {pr} out of range (A31)")
    c_ex = c_ex_gross * pr
    equity_twd = inp["equity"] * fx
    if c_ex < 0.15 * equity_twd:
        review_flags.append('historical_excess_cash_threshold_unmet')
    # Steady-state-return path and time alignment (valuation-rules「经营价值与超额现金」② / ③, A31).
    tau, y1, y2, rs = inp["tau"], int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]
    if not NUM_YEAR <= y1 < y2:
        errors.append("need numerator year <= y1 < y2 (A31)")
    if not r <= rs:
        errors.append("rs_steady below r (A31)")

    def pp(g: float, roe_x: float, r_x: float, t0: int = NUM_YEAR) -> float:
        return path_value(0.0, 0, g, roe_x, r_x, t0, y1, y2, rs)

    def ts(g1_x: float, n_x: int, g2_x: float, roe_x: float, r_x: float) -> float:
        return path_value(g1_x, n_x, g2_x, roe_x, r_x, NUM_YEAR, y1, y2, rs)
    c_adr = c_ex / fx / sh
    c_inc = c_adr * inp["cash_yield"] * (1.0 - inp["tax_eff"])  # after-tax, USD/ADR, out of every numerator
    eps = {t: eps_cons[t] - c_inc for t in TIERS}  # operating EPS
    # The 2028 consensus carries the same cash income, so the company transition
    # growth on operating earnings is the consensus step net of it.
    g1 = (eps_cons["m"] * (1.0 + g1_eps) - c_inc) / eps["m"] - 1.0

    # Own band on the operating basis: the upper edge month (2022-01, over FY2023
    # actual) less the excess cash then visible (FY2021, at the then rate) and its
    # after-tax income.  The lower edge (2025-03) is stated, not binding.
    c_edge = inp["cex_edge_hi_twd"] / inp["fx_edge_hi"] / sh
    f_edge = inp["px_edge_hi"] / inp["pe_own_max"]
    op_edge = (inp["px_edge_hi"] - c_edge) / (f_edge - c_edge * inp["aty_edge_hi"])
    inp['pe_op_max']=round(op_edge,2)

    # Pin mature wafer $ at the 2Q26 run-rate → 2027E mature share of wafer shrinks with revenue growth.
    mat = inp["mat_of_wafer_asof"] * 4.0 * inp["rev_2q26_twd"] / inp["rev_2027_twd"]
    share_aw = inp["share_wafer"] * (1.0 - mat)
    share_mw = inp["share_wafer"] * mat

    # 2028E consensus growth is company-level.  With mature/B2 held at their own
    # g, the platform legs must grow faster than g1 for the company to reach it.
    w_plat = share_aw + inp["share_adv"]
    g1_adv = (g1 - share_mw * g_mat - inp["share_other"] * g_b2) / w_plat

    # ROE = E_{n+1} / B_n: the numerator year's earnings over its OPENING book
    # (= end-2026), not today's 2Q26 book and not the year-end book (that would
    # put retention the year has not yet earned into the denominator;
    # valuation-rules 裁决表 ② as of 2026-09-21).  The 2Q26 book is
    # rolled over the 2H26 earnings not yet booked (2026E consensus minus 1H26
    # actual) at the GROWTH-REQUIRED retention b1 = g/ROE -- the same b
    # two_stage_pe charges in stage 1 -- not at the actual payout complement.
    # With ROE = eps / BPS and BPS = E0 + b1·N the fixed point is closed-form:
    # BPS = E0 / (1 - g·N/eps).  M/H roll at the company g1 (the legs' g sum to
    # it); L has no window and rolls at g2.  Actual retention beyond b1 is the B
    # bucket, printed as a disclosure, not put into the book.
    # Operating book (equity − excess cash), unbooked 2H26 operating earnings
    # (half a year of cash income out).
    ni_2h26 = inp["eps_2026_m"] * sh - inp["ni_1h26_twd"] / fx
    bps_2q26 = (inp["equity"] - c_ex / fx) / sh
    unbooked = {t: ni_2h26 / sh - c_inc / 2.0 for t in TIERS}  # per ADR, 2H26 only (opening-2027 book)
    g_roll = {"l": g2, "m": g1, "h": g1}
    bps_open_2027 = {t: bps_2q26 / (1.0 - g_roll[t] * unbooked[t] / eps[t]) for t in TIERS}
    roe = {t: eps[t] / bps_open_2027[t] for t in TIERS}  # RONIC per tier
    b1 = {t: g_roll[t] / roe[t] for t in TIERS}
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"{t.upper()}: growth-required retention b1={b1[t]:.2f} outside (0,1) — book roll needs external equity")
        if roe[t] < r:
            errors.append(f"{t.upper()}: RONIC {roe[t]:.1%} < r — check the persistent-failure rule")
    ret_actual = 1.0 - inp["payout_3y"]
    retained_more = {t: (ret_actual - b1[t]) * unbooked[t] for t in TIERS}  # 多留部分, USD/ADR over 2H26
    # g2 comes from a reverse-solve, so the Gordon branch must match the payout
    # policy -- on the operating payout (dividends + excess-cash accumulation).
    errors += check_branch(g2, roe["m"], r, inp["payout_op"], "g2")
    if g2 > (1.0 - inp["payout_3y"]) * roe["m"]:
        errors.append("g2 above (1 − d) × RONIC_M (③ 约束 2)")

    def platform_pe(t: str, g2_x: float, transition: bool, r_x: float | None = None) -> float:
        r_x = r if r_x is None else r_x
        if transition:
            return ts(g1_adv, n, g2_x, roe[t], r_x)
        return pp(g2_x, roe[t], r_x)

    pe_mat = {t: pp(g_mat, roe[t], r) for t in TIERS}
    pe_b2 = {t: pp(g_b2, roe[t], r) for t in TIERS}

    def capacity(wpm: float) -> float:
        return (wpm / 10000.0) * inp["uv_per_10k_wpm"] / inp["shares_adr"]

    def window(t: str, r_x: float) -> float:
        """2H26 unbooked operating profit x (1 - b), b = the book roll's g/RONIC, at tau/2 (A31)."""
        return max(unbooked[t] * (1.0 - g_roll[t] / roe[t]), 0.0) * (1.0 + r_x) ** -(tau / 2)

    def legs_at(t: str, p_plat: float, p_mature: float, p_other: float, mat_share: float = mat,
                r_x: float | None = None) -> dict[str, float]:
        """Leg values at the start of 2027 (Gordon), folded to the valuation date (A31): the
        Gordon legs x (1+r)^-tau; B1 at its Gordon floor folds too, B1 at the CoWoS capacity
        value (a today's-capacity reading) does not; + the window profit + the excess cash."""
        r_x = r if r_x is None else r_x
        d = (1.0 + r_x) ** -tau
        e = eps[t]
        s_aw = inp["share_wafer"] * (1.0 - mat_share)
        s_mw = inp["share_wafer"] * mat_share
        paw = e * s_aw * p_plat
        pmw = e * s_mw * p_mature
        floor = e * inp["share_adv"] * p_plat
        cap = capacity(inp[f"cowos_wpm_{t}"])
        pb1 = floor * d if floor >= cap else cap
        pb2 = e * inp["share_other"] * p_other
        win = window(t, r_x)
        today = (paw + pmw + pb2) * d + pb1 + win
        return {
            "Paw": paw * d,
            "Pmw": pmw * d,
            "Pb1": pb1,
            "Pb2": pb2 * d,
            "cap": cap,
            "floor": floor,
            "win": win,
            "vop_tn": paw + pmw + max(cap, floor) + pb2,
            "vop": today,  # today's operating value (incl. window)
            "sum": today + c_adr,  # + excess cash (λ = 1, parent share)
        }

    def blended_pe(t: str, g2_x: float) -> float:
        """Today's operating multiple: today's operating value ÷ operating EPS (A31)."""
        return legs_at(t, platform_pe(t, g2_x, t != "l"), pe_mat[t], pe_b2[t])["vop"] / eps[t]

    # The own band is measured on company earnings, so the band edge is where
    # the tier's blended operating multiple (not the platform leg alone) touches it.
    def g2_at_edge(t: str, target: float) -> float:
        lo, hi = -0.05, r - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if blended_pe(t, mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_g2 = {t: g2_at_edge(t, inp["pe_op_max"]) for t in TIERS}
    edge_min = min(band_edge_g2.values())
    if g2 > edge_min + 1e-9 or edge_min - g2 > 1e-4:
        review_flags.append('historical_growth_band_edge_needs_review')
    pe = {t: platform_pe(t, g2, t != "l") for t in TIERS}
    legs = {t: legs_at(t, pe[t], pe_mat[t], pe_b2[t]) for t in TIERS}
    L, M, H = (legs[t]["sum"] for t in TIERS)
    pe_blend = {t: legs[t]["vop"] / eps[t] for t in TIERS}  # operating multiple (guardrail)
    pe_merged = {t: legs[t]["sum"] / eps_cons[t] for t in TIERS}  # whole-equity PE (disclosure)
    for t in TIERS:
        if not (inp["pe_op_min"] <= pe_blend[t] <= inp["pe_op_max"] + 1e-6):
            review_flags.append('historical_operating_multiple_outside_band')
            break
    if not (L < M < H):
        errors.append(f"invariant L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")

    eps_t = (eps["l"], eps["m"], eps["h"])
    flat_errs, _ = flat_multiple_ladder(eps_t, pe["m"])
    errors += flat_errs
    flat = tuple(legs_at(t, pe["m"], pe_mat["m"], pe_b2["m"])["sum"] for t in TIERS)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat[0]:.1f}/{flat[1]:.1f}/{flat[2]:.1f}")
    dec = decompose((L, M, H), (pe["l"], pe["m"], pe["h"]))


    # The axis tiers are all 2028 volume.  Every tier values its 2028 COUPE NI
    # in 2028 on the platform leg's steady ruler (g2, the tier's ROE, basket r)
    # and discounts to the 2027 numerator year (valuation-rules「未建模期权」,
    # construction §7c-1, 2026-10-03).  The platform PE would carry the
    # wafer business's +33% 2028 step into the realisation year -- a stage-1
    # opened at realisation, which the rule forbids (v9 did that for L and H).
    option={'status':'unavailable','label':'COUPE光引擎','anchors':None}
    coupe_rev=disc_coupe=ni_coupe=pe_coupe=v_k=v_k_v9=v_opt=p_k=None
    try:
        require_whole_years(inp,('t_coupe',))
        shares_opt=[inp[f'coupe_share_{t}'] for t in TIERS]
        if inp['t_coupe'] <= NUM_YEAR or not 0 <= shares_opt[0] < shares_opt[1] < shares_opt[2] <= 1:
            raise ValueError('COUPE realization year or share ladder invalid')
        coupe_rev={t:inp[f'oe_{t}']*inp['asp_oe']*inp[f'coupe_share_{t}'] for t in TIERS}
        disc_coupe=(1+r)**(inp['t_coupe']-NUM_YEAR)
        ni_coupe={t:coupe_rev[t]*inp['npm_coupe']/inp['shares_adr'] for t in TIERS}
        pe_coupe={t:pp(g2,roe[t],r,t0=int(inp['t_coupe'])) for t in TIERS}
        v_k={t:ni_coupe[t]*pe_coupe[t]/disc_coupe*(1+r)**-tau for t in TIERS}
        v_k_v9={'l':ni_coupe['l']*pe['l'],'m':ni_coupe['m']*pe_coupe['m']/(1+r),'h':ni_coupe['h']*pe['h']}
        v_opt=v_k['h']
        adjusted=tuple(legs[t]['sum']+v_k[t] for t in TIERS)
        if not all(math.isfinite(v) for v in (*v_k.values(),*adjusted,v_opt)) or v_opt<=0 or not 0<=adjusted[0]<adjusted[1]<adjusted[2]:
            raise ValueError('COUPE value or adjusted band invalid')
        p_k={t:v_k[t]/v_opt for t in TIERS}
        option={'value':v_opt,'weights':dict(zip('LMH',(p_k[t] for t in TIERS))),
                'anchors':dict(zip('LMH',adjusted))}
    except (ValueError,ZeroDivisionError,OverflowError):
        coupe_rev=disc_coupe=ni_coupe=pe_coupe=v_k=v_k_v9=v_opt=p_k=None

    A, B = cut_points(L, M, H)
    modelled, gap = payout_gap(g2, roe["m"], inp["payout_op"])

    def band_with(g2_x: float = g2, mat_share: float = mat, transition: bool = True) -> tuple[float, float, float]:
        return tuple(
            legs_at(t, platform_pe(t, g2_x, transition and t != "l"), pe_mat[t], pe_b2[t], mat_share)["sum"]
            for t in TIERS
        )

    # A32: a user-requested tail-growth stress, with all other inputs frozen.
    candidate_g = inp["g2_candidate"]
    candidate_result={'status':'unavailable','label':'永续增速压力情景','anchors':None}
    candidate=ca_stress=cb_stress=None
    try:
        if check_g_cap(candidate_g,r,'g2_candidate'):
            raise ValueError('candidate growth outside cap')
        candidate=band_with(g2_x=candidate_g)
        if not all(math.isfinite(v) for v in candidate) or not 0<=candidate[0]<candidate[1]<candidate[2]:
            raise ValueError('candidate band invalid')
        ca_stress,cb_stress=cut_points(*candidate)
        candidate_result={'label':'永续增速压力情景','anchors':dict(zip('LMH',candidate))}
    except (ValueError,ZeroDivisionError,OverflowError):
        candidate=ca_stress=cb_stress=None
    n7 = inp.get("n7_of_wafer_asof")
    if n7 is not None and math.isfinite(n7):
        n7_mat = (inp["mat_of_wafer_asof"] + n7) * 4.0 * inp["rev_2q26_twd"] / inp["rev_2027_twd"]
    else:
        n7=None
    # v7 read the band as a cap on the platform leg alone; kept as a coordinate.
    lo, hi = -0.05, r - 1e-4
    for _ in range(200):
        mid = (lo + hi) / 2
        if platform_pe("h", mid, True) < inp["pe_op_max"]:
            lo = mid
        else:
            hi = mid
    g2_leg = (lo + hi) / 2
    lever = []
    for delta in (-0.01, +0.01):
        g2_d = g2 + delta
        try:
            vals=band_with(g2_x=g2_d)
            legal = all(math.isfinite(v) for v in vals) and g2_d <= 0.06 + 1e-9 and all(
                inp["pe_op_min"] <= blended_pe(t, g2_d) <= inp["pe_op_max"] + 1e-6 for t in TIERS)
            lever.append({'growth':g2_d,'anchors':vals if all(math.isfinite(v) for v in vals) else None,'legal':legal})
        except (ValueError,ZeroDivisionError,OverflowError):
            lever.append({'growth':g2_d,'anchors':None,'legal':False})
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves r_perp
    # 1:1 on every leg -- platform (aw / B1 floor), mature wafer and B2 multiples are
    # re-priced; EPS, ROE, g1_adv/g2 and the CoWoS capacity value stay put.
    # Disclosure only: the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        r_x = r + dr
        return tuple(
            legs_at(t, platform_pe(t, g2, t != "l", r_x), pp(g_mat, roe[t], r_x), pp(g_b2, roe[t], r_x), r_x=r_x)["sum"]
            for t in TIERS
        )

    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # PB/ROIC is a separate comparison, so invalid comparison inputs cannot
    # erase a valid primary band. It never feeds the primary calculation.
    cross_result={'status':'unavailable','label':'PB回报对照','anchors':None}
    base_ni=c_net=d_ic_2h26=d_ic_2027=d_ic_2028=None
    ni_2027_mach=ni_2028_mach=equity_2028=bps_2028=eps_2028_mach=roe_2028_mach=None
    pb_q=disc=g_impl_pb=None
    try:
        fx=inp['fx_twd']
        ret=ret_actual
        base_ni=2*inp['ni_1h26_twd']/fx
        c_net=inp['cash_return_gross']-1/inp['dep_life']
        d_ic_2h26=(inp['capex_2026']-inp['da_2026e'])/2
        d_ic_2027=d_ic_2h26+(inp['capex_2027']-inp['da_2027e'])
        d_ic_2028=d_ic_2027+(inp['capex_2028']-inp['da_2028e'])
        ni_2027_mach=base_ni+c_net*d_ic_2h26
        ni_2028_mach=base_ni+c_net*d_ic_2027
        equity_2028=inp['equity']+ret*(base_ni/2+ni_2027_mach+ni_2028_mach)
        bps_2028=equity_2028/inp['shares_adr']
        eps_2028_mach=ni_2028_mach/inp['shares_adr']
        roe_2028_mach=eps_2028_mach/bps_2028
        pb_q=(inp['pb_5y_q1'],inp['pb_5y_med'],inp['pb_5y_q3'])
        disc=(1+r)**inp['n_disc']
        cross=tuple(bps_2028*pb/disc for pb in pb_q)
        if not all(math.isfinite(v) for v in (*cross,base_ni,c_net,d_ic_2h26,d_ic_2027,d_ic_2028,
                ni_2027_mach,ni_2028_mach,equity_2028,bps_2028,eps_2028_mach,roe_2028_mach,disc)):
            raise ValueError('comparison results must be finite')
        if not 0<=cross[0]<cross[1]<cross[2]:
            raise ValueError('comparison band must increase')
        ca,cb=cut_points(*cross)
        g_impl_pb=tuple(None if pb==1 else (roe_2028_mach-r*pb)/(1-pb) for pb in pb_q)
        cross_result={'anchors':dict(zip('LMH',cross)),'cut_points':[ca,cb]}
    except (ValueError,ZeroDivisionError,OverflowError):
        base_ni=c_net=d_ic_2h26=d_ic_2027=d_ic_2028=None
        ni_2027_mach=ni_2028_mach=equity_2028=bps_2028=eps_2028_mach=roe_2028_mach=None
        pb_q=disc=g_impl_pb=None
    # Only a clean run feeds the daily digest (output/rates/).
    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    result = {
        "ticker": "TSM.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-06-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-11-06', 'historical_framework_as_of':'2026-11-06',
        "anchors": band((L, M, H)),
        "candidate": candidate_result,
        "option": option,
        "cross_band": cross_result,
        'review_flags':review_flags+['historical_shared_optical_volume_not_company_specific',
            'historical_cash_allocation_and_spending_unverified','historical_earnings_consensus_unverified'],
        "cut_points": [A, B], "anchor_ratio": anchor_ratio, "cash_anchor": cash_anchor,
        "c_ex_gross": c_ex_gross, "c_ex": c_ex, "equity_twd": equity_twd, "c_adr": c_adr,
        "c_inc": c_inc, "eps_cons": eps_cons, "eps": eps, "g1_eps": g1_eps, "g1": g1,
        "c_edge": c_edge, "f_edge": f_edge, "op_edge": op_edge, "mat": mat,
        "share_aw": share_aw, "share_mw": share_mw, "w_plat": w_plat, "g1_adv": g1_adv,
        "ni_2h26": ni_2h26, "bps_2q26": bps_2q26, "unbooked": unbooked, "g_roll": g_roll,
        "bps_open_2027": bps_open_2027, "roe": roe, "b1": b1, "retained_more": retained_more,
        "pe_mat": pe_mat, "pe_b2": pe_b2, "band_edge_g2": band_edge_g2, "edge_min": edge_min,
        "pe": pe, "legs": legs, "pe_blend": pe_blend, "pe_merged": pe_merged, "flat": flat, "dec": dec,
        "coupe_rev": coupe_rev, "disc_coupe": disc_coupe, "ni_coupe": ni_coupe, "pe_coupe": pe_coupe,
        "v_k": v_k, "v_k_v9": v_k_v9, "p_k": p_k,
        "no_transition": band_with(transition=False), "no_pin": band_with(mat_share=inp["mat_of_wafer_asof"]),
        "n7_mat": n7_mat if n7 is not None else None,
        "n7_sensitivity": band_with(mat_share=n7_mat) if n7 is not None else None,
        "g2_leg": g2_leg, "platform_band": band_with(g2_x=g2_leg),
        "growth_lever": lever, "modelled_payout": modelled, "payout_gap": gap,
        "base_ni": base_ni, "c_net": c_net, "d_ic_2h26": d_ic_2h26, "d_ic_2027": d_ic_2027,
        "d_ic_2028": d_ic_2028, "ni_2027_mach": ni_2027_mach, "ni_2028_mach": ni_2028_mach,
        "equity_2028": equity_2028, "bps_2028": bps_2028, "eps_2028_mach": eps_2028_mach,
        "roe_2028_mach": roe_2028_mach, "pb_q": pb_q, "disc": disc, "g_impl_pb": g_impl_pb,
        "parameters": {"discount": r, "growth": {"platform": g2, "mature": g_mat, "other": g_b2},
                       "forward": band([roe[t] for t in TIERS]),
                       "mature": band([min(roe[t], rs) for t in TIERS])},
    }
    if rate_inputs is not None:
        result['rate_sensitivity']=result_rate_sensitivity(calculate_rf_readings(
            rate_currency='USD',price_currency='USD',price_unit='per_share',priced_r={'r_perp':r},
            band_at=band_rf,rates_loader=lambda _currency:rate_inputs,base_anchors=(L,M,H)))
    return result


def calculate(context):
    supply=context['axes']['cowos']['supply_wpm']
    optical=context['axes']['optical']
    selected={'cowos_wpm_m':supply,'cowos_wpm_h':supply,'asp_oe':optical['oe_bom_usd']}
    selected.update({f'oe_{t}':optical['oe'][t.upper()] for t in TIERS})
    result=evaluate({**INPUTS,**selected},context.get('rate_inputs'))
    result['basis_changed']=None
    optional={'g2_candidate','t_coupe','npm_coupe','coupe_share_l','coupe_share_m','coupe_share_h',
              'cash_return_gross','dep_life','capex_2026','capex_2027','capex_2028',
              'da_2026e','da_2027e','da_2028e','pb_5y_q1','pb_5y_med','pb_5y_q3','n_disc','n7_of_wafer_asof'}
    if any(not math.isfinite(INPUTS[k]) for k in optional if k in INPUTS and INPUTS[k] is not None):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'shared':selected,'numerator_year':NUM_YEAR},HISTORICAL_PARTIAL_FINGERPRINT)
    result['units']={'price':'USD_PER_SHARE'}
    if result['option'] is not None:
        result['option']['value_unit']='USD_PER_SHARE'
    mapping={'advanced_wafer':'Paw','mature_wafer':'Pmw','advanced_packaging':'Pb1',
             'other_packaging':'Pb2','window':'win'}
    result['segments']={name:{'unit':'USD_PER_SHARE','values':{
        t.upper():result['legs'][t][key] for t in TIERS}} for name,key in mapping.items()}
    result['segments']['cash']={'unit':'USD_PER_SHARE','values':dict.fromkeys('LMH',result['c_adr'])}
    result['key_parameters']={
        'discount_rate':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['r_perp'])},
        'platform_growth':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g2'])},
        'mature_growth':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g_mat_wafer'])},
        'other_packaging_growth':{'unit':'RATIO','values':dict.fromkeys('LMH',INPUTS['g_b2'])},
        'forward_return':{'unit':'RATIO','values':{t.upper():result['roe'][t] for t in TIERS}},
        'steady_return':{'unit':'RATIO','values':{t.upper():min(result['roe'][t],INPUTS['rs_steady']) for t in TIERS}}}
    return result
