#!/usr/bin/env python3
"""RKLB legacy valuation, retaining its financial inputs and judgments.

Amounts and shares are USD billions and billions of shares; outputs are USD/share.
The self-extrapolated candidate was explicitly accepted as a rule exception.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

FORMULA_ID = "rklb_sotp_fy27_mature_margin_iridium_evebit_v4"
TIERS = ("l", "m", "h")
NUM_YEAR = 2027
LISTING_CCY = "USD"
OPTION_FRACTIONS = (0.15, 0.35, 1.0)  # original scenario judgments, not probabilities
# | A1 | 林奇主类 `fast_grower`：营收 FY2024 +78% / FY2025 +38% / FY2026E +60% / FY2027E +42%，毛利率 FY2023 21% → Q2'26 36%；亏损来自 Neutron 投入期，不是困境（从未盈利，不是 `turnaround`）。**证伪**：剔除收购后空间系统营收同比连续两季 < 20% | active | 10-K；10-Q；yfinance | 主尺骨架 |
# | A2 | **SOTP 骨架**：A2c 命中 4 条（两分部各 > 15% 营收；驱动不同——合同交付 vs 发射次数；一块被 Neutron 研发拖成亏损、合并利润失真；融资与资本开支服务 Neutron 与铱星）；未命中：无卖方公开分部拆表。卫星与 Electron 因费用不分摊合为一腿；各腿无杠杆、净现金收尾、不合成 \(\bar r\) | active | heuristics A2c；10-K Note 20 | Formula |
# | A3 | **归篮**：卫星 + Electron → **篮 4**（按合同交付的制造 + 已跑 5 年以上的发射，盈利不是商品价函数；FY2025 前五大客户 49%，单一客户未达 50%、前两大未达 70%，不命中篮 7）；铱星 → **篮 4**（订阅制卫星通信，有替换资本开支、不受价格管制，不进篮 2；美国政府固定价合同约 1 亿 / 年，约占 11%，不够拆篮 1 腿）；Neutron 期权 → 同底牌篮 4（construction §7c-7）。**CAPM 粗筛**：4.0% + 2.61 × 4.5% = **15.7%**，比篮 4 高 5.7pp → 进篮子质疑清单，理由：β 来自 Neutron 期权与情绪交易，两块已实现生意（合同制造 + 稳态发射）的风险已由 L 情景承载，Neutron 的风险在 \(p_k\) 里收一次，不在 r 里再收 | active | 10-K「top five customers ~49%」；yfinance β（2026-10-02） | `r_legs` |
# | A4 | **分子（FY2027 共识营收 × 成熟利润率）**：营收三点 = yfinance FY2027 区间 12.18 / 13.63 / 15.43 亿，扣 Neutron 收入 1.0 亿（`待补`：一致预期内含 Neutron 次数不可得，按约 2 次 × 5,000 万）。FY2027 本身仍在投入期（合并经营利润约盈亏平衡），**MUST NOT** 当稳态；稳态分子 = 同一营收 × 已实现的成熟利润率，视作 FY2029 盈利（不计 FY27→29 的增长），按 r 折回 2 年，再按时点对齐折 0.5 年到 2026-06-30（A19）。分子与 g 同世界：稳态分子配稳态 g2 | active | yfinance 2026-10-02；Q2'26 业绩会（GAAP 营业费用 1.42 亿 / 季） | `rev_*` / `neutron_rev` / `n_arr` |
# | A5 | **成熟经营利润率（已实现锚）**：L = 洛克希德 Space 分部 FY2025 10.3%（130.29 亿 / 13.45 亿）；M = MDA Space FY2025 15.5%（调整后净利 1.90 亿 ÷ (1 − 25%) ÷ 营收 16.33 亿，推算，`待补`核 EBIT）；H = 20%（自身 1H26 GAAP 毛利率约 37% − 规模化费用率 17%，费用率为**拍值**，无已实现锚）。诺斯罗普 Space Systems FY2025 11.0% 作 L 旁证。**证伪**：FY2027 起合并 GAAP 毛利率回落到 2024 年的 26.6% 以下 | active | LMT / NOC 10-K FY2025；MDA FY2025 年报（2026-03-04）；10-Q | `margin_*` |
# | A6 | **边际资本效率（商誉沉没）**：Gordon 用稳态边际 ROIC（valuation-rules「峰形区处理」第 1 条：先审 ROE 输入）。内生增长每多 1 美元营收需追加约 0.40 美元资本：FY2025 营收 +1.66 亿；剔 Neutron 资本开支约 0.6 亿（总 1.56 亿，Neutron 占比 `待补`）− 折旧 0.44 亿 + 存货与应收增加约 0.5 亿 ≈ 0.66 亿。过去收购的商誉 + 无形资产（FY2025 末 2.06 + 2.25 亿，2026 年再增）是沉没成本，不进边际 ROIC 分母。边际 ROIC = 利润率 × (1 − 税) ÷ 0.40 → 20% / 31% / 40%，均落单调区（ROE − r ≥ 3pp）。敏感：0.30 / 0.50 → M 10.28 / 10.13（稳态回报路径下前瞻 ROIC 越高、回落越多，敏感度小） | active | 10-K 现金流量表与资产负债表 | `cap_int` |
# | A7 | **永续 g2 = 5%**（`无同业锚`，≤ \(G_{cap}\) 6%）：无 ≥2 家 FY2028+ 预测 → 无过渡窗口（n = 0）；方向门：自身 3 年营收 CAGR 为正 → g2 > 0 可用。±1pp → L/M/H 6.25/9.86/15.42 · 6.71/10.87/16.92 | active | valuation-rules「永续增长口径」 | `g2` |
# | A8 | **铱星腿 = 准年金分支（EV/EBIT 自身实测带）**：construction §5b 决策树第 1 条——铱星 EBIT ≈ 可分配现金（FY2025 资本开支 1.00 亿 < 折旧 2.10 亿，自由现金流 3.00 亿 > 税后 EBIT 1.86 亿；2024 年把卫星寿命调长、折旧由 3.20 亿降到 2.03 亿），卖方与同业按 EV/OEBITDA、EV/EBIT 定价，L 波段频谱特许 + 订阅。Gordon 只作交叉：账面投入资本 22.2 亿、ROIC 约 9% ≈ r，Gordon 给约 10 倍（+ 十年收获期约 7 亿）≈ 25 亿，低于自身带底 → 出带；判定不是篮子问题而是形式问题（折旧 > 维持资本开支、账面资本是 2017–2019 星座造价），故换准年金分支，不降篮、不双计（未同时取低 r）。**倍数带**：2025-01 至 2026-06-26（宣布前，折旧口径调整后）月末 EV / TTM EBIT，n = 18：p10 15.0 / 中位 20.0 / p90 29.6（最低 14.7 @ 2025-11，铱星当月最低价 15.52 @ 2025-11-20）；2026-04 至 06 可能含并购传闻，H 档据此偏高。**分子**：FY2027 EBIT M = 2.60 亿（Longbridge 季度 EBIT 一致预期 2026Q3–2027Q1 约 0.61–0.67 亿 / 季 × 4）；L / H 按 5 家营收区间比例（9.135 / 9.951、10.453 / 9.951）同源缩放 → 2.39 / 2.73 亿。**证伪**：交割前服务收入连续两季同比下滑 | active | yfinance 年报与股价（2026-06-26 前）；Longbridge 一致预期 2026-10-03 | `ir_ebit_*` / `ir_mult_*` |
# | A9 | **铱星对价与交割**：现金 27 美元 × 1.0596 亿股（Longbridge 总股本，完全稀释股数 `待补`）= 28.61 亿；承接净债 16.05 亿（Longbridge Q2'26）；股票部分按换股比例上限 0.40 进股本（4,238 万股）。**交割失败**（股东 / 监管否决）→ 回不含铱星口径：铱星腿删除、换股股数删除、9 月 ATM 留在净现金；事件增量重算 | active | 10-Q 合并协议条款；8-K 2026-06-28 | `irdm_shares` / `exch_ratio` / `ir_nd` / `ir_cash_ps` |
# | A10 | **净现金收尾**：6/30 现金及短期投资 23.02 亿（Longbridge）+ 2026-09-15 ATM 19.44 亿（GovConWire，净额 `待补`）− 有息债务 1.34 亿（含可转债余额 0.13 亿）。9 月 ATM 指定用于铱星现金对价，与 A9 的现金对价一减一加，不双计；Neutron 投入不在此扣（A12） | active | Longbridge Q2'26；GovConWire 2026-09 | `cash` / `sep_raise` / `debt` |
# | A11 | **Neutron 期权（2026-10-04 重做）**：**份数**按取数序逐层：① 卖方 Neutron 预测——只有摩根士丹利一家公开次数（A18），不满足 ≥2 家同年；② 公司级共识倒推——FY2028 营收共识 17.70 亿只有点值、拆不出 Neutron（A15）；③ 公司具名的量——CFO Spice（高盛工业会议 2025-12-04）「未来几年建约 4 架机队，每季周转一次即每年 16 次」→ **16 次 / 年**；一份 = Beck 的爬坡终点「1 → 3 → 5 → 7 次及以上」的下沿 7 次，k = 16 ÷ 7 = **2.29**（兑现后的继续增长按 k 表达，不另开两段式）。上一版把「7 次及以上」的下限当全部、且把 Motley Fool 撰稿人的「7 次 × 5,000 万 = 3.5 亿」算例当公司口径，作废。「每年 10–20–30 次」（同场 CFO，条件是规模化复用）、独立研究 Northwise 的 2030 年 18 次、可竞标市场 90–100 次 / 年都没有具名的量，只落 \(p_k\)。FY2027 共识里的 Neutron 收入已从底牌剔除（`neutron_rev`），不再扣。**单价** 5,000 万（自报 5,000–5,500 万下沿；Q2'26 称「涨价空间大于降价」，不计）。**单位经济 = 发射业务经济性**：卖方 Neutron 利润率无（摩根士丹利只说早期为负）→ 公司具名单次经济：CFO（CNBC 2023-03-24）单次成本 2,000–2,500 万、价 5,000–5,500 万（约一半成本在不回收的二级），「最终毛利率 50% 左右」→ 取 **50%**（下沿）；交叉 / 下限：Electron 发射分部两期拆固定 / 变动（FY2024 16 次 毛利 0.346 / 收入 1.254 亿；FY2025 21 次 0.813 / 1.990 亿 → 单次变动成本约 538 万、固定约 470 万）外推到 24 次约 41%，FY2025 实测 40.8%（一次性火箭，Neutron 一级复用只应更高）；CFO 称 Electron 在 24 次 / 年时毛利 45–50%。费用率 17% 同 `margin_h` 拍值 → 经营利润率 **33%**、税后；**倍数** = 本票的尺（g2 5%、边际 ROIC 65.2%、r 10%）走稳态回报路径，**高回报期按 Neutron 自己的产品阶段取、不沿用卫星腿的 2029 / 2033**（retention「高回报期 MUST 对上该腿自己的产品阶段」，用户 2026-10-19）：2027 首飞、2031 机队满产，满产那年之前产品还没规模出货，谈不上被竞争磨平，故 65.2% 维持到 Y1 = 2031（`t_opt`）；**进入门槛判高** → 回落 6 年（`opt_fall`），Y2 = 2037——依据：可重复使用的中型火箭开发周期 5–8 年、投入以十亿美元计，一级回收至今只有 SpaceX 一家规模化做成，蓝色起源、Relativity、Stoke、Firefly / 诺格 Eclipse 都还在首飞或复用验证阶段，国家安全发射（NSSL）认证需多次成功飞行（卫星腿判「中」是因为小火箭与卫星整星已有多家新进入者，Neutron 的门槛高一档）；稳态 = 叙事换代上限 30%（A19）→ **16.98×**（不回落则 18.47×；ROIC 按同一 `cap_int` 0.40）。**兑现年**：一份（7 次）= 2027 首飞 + 第四年 = **2030**；机队产能 16 次 = **2031**（爬坡到 7 次后再一年，无时点锚·拍值）→ 8 亿 × 33% × 0.79 = 2.09 亿 × 16.98 = 35.4 亿 ÷ 1.1⁴ ÷ 6.70 亿股 = 3.61 / 股。**扣未投资本**（valuation-rules「未建模期权」2026-10-04：新建产能型期权 MUST 扣未投资本，按投入年份折到分子年）：16 次 / 年要约 4 架可复用一级（CFO「约 4 架」，每架每季一飞）；首飞那架不试回收、已在首飞前投入里（A12），故 4 架全部是首飞后新造；**每架造价公司未披露**（10-K / 10-Q 不分拆，电话会只说首飞后支出「从研发转向后续火箭存货」）→ 拍值 5,000 万：单次成本 2,000–2,500 万里约一半是不回收的二级，即二级约 1,000–1,250 万；一级装 9 台 Archimedes、二级 1 台，再加整流罩与着陆结构，取二级的约 4 倍 ≈ 5,000 万（区间 3,000 万–1 亿）；首飞后每年造一架、2027–2030 → 现值 1.74 亿 = 0.26 / 股；发射台（LC-3 已启用）、Wallops 生产厂、着陆驳船「Return On Investment」已建或在建、属已投，每次的二级与翻修在单次成本里，均不再扣 → 3.35，再同底牌按时点对齐折 τ 半年（A19）→ **\(V_{opt}\) = 3.19 / 股**（一份 7 次 @2030、2 架 → 1.52；一份的高回报期同样从它自己的满产年 2030 起算）。**升级门槛**：≥2 家卖方给出同年 Neutron 次数或收入 → 份数按卖方（扣共识已含）；首飞成功 + 公开单次成本或第 2 次复用飞行 → 首年次数做成底牌腿、同步移出 \(V_{opt}\)；公司给出高于 16 次的具名机队 / 节奏或新签多次合同 → 份数改按具名量。**下修触发**：首飞失败或推迟到 2027 年底之后 → \(p_M\) 下调、兑现年顺延（顺延一年、高回报期随之顺延 → \(V_{opt}\) 2.88）；公司披露单架造价 → 替换 `booster_cost` 拍值 | active | CNBC 2023-03-24（单次成本）；BofA 工业会议 2025-03-18（Neutron 目标毛利 45–50%）；Q2'26 业绩会（首飞后支出转向后续火箭存货、首飞不试回收）；GrowWire 转述高盛工业会议 2025-12-04（机队 / 16 次）；Motley Fool 2025-11-16 / 2026-09-04（节奏）；Q2'26 业绩会纪要 100372（单价）；10-K FY2025 Note 20 | `neutron_price` / `neutron_cadence` / `neutron_unit` / `neutron_gm` / `neutron_opex` / `t_unit` / `t_opt` / `fleet_n` / `fleet_unit_n` / `booster_cost` / `t_fleet0` / `opt_fall` |
# | A12 | **Neutron 剩余投入**：粗估 4.2 亿（首飞前研发 + 剩余资本开支，`待补`；CFO 2025-12-04：截至 2025 年底累计开发约 3.6 亿、首飞前另需 0.4–0.5 亿——其后储箱测试破裂、首飞推迟，实际更多；管理层称首飞后仍需 18–24 个月自由现金流才转正）。本项只含**首飞前**、不论成败都会花的投入（含首飞那架火箭），表3 全额扣、不乘 \(p_k\)：失败世界里这笔钱也已花掉。首飞后为 16 次 / 年建的约 4 架机队只在成功世界才花，按「未投资本」在 \(V_{opt}\) 内扣（A11），不在本项重复；区间上沿约 10 亿 → 1.49 / 股（若首飞前再遇重大返工）。日报 `+V` 带按 `底牌 + p × V_opt` 计、未扣本项（行契约限制），读者自行减 0.63 / 股 | active | 业绩会纪要 100372 | `neutron_carry` |
# | A13 | **未计价的具名项**：① 铱星协同（自造下一代星座 / Neutron 发射降本）——门槛：披露下一代星座造价与合同；② 手机直连、导航新服务——门槛：披露用户数与单用户收入；③ HASTE 国防增长——已在 FY2027 共识内，不另计；⑤ Neutron 超出机队产能 16 次的部分——CFO「每年 10–20–30 次」（条件是规模化复用）、NSSL Lane 1 任务单（首飞成功前不能竞标）、铱星下一代星座（「需要更大运力时用 Neutron」，未给星数与发射次数）、自有星座（CFO：约三年后才考虑，未给规模）——均无具名的量，只落 \(p_k\)，门槛：公司给出机队 / 节奏数字或签下具名多次合同；④ 「SpaceX 式经济性」（利润率显著高于 20%、增长几乎不需追加资本）——门槛：卫星业务连续四季 GAAP 经营利润率 > 15%。任一满足即按 construction §7c-7 写全链入位 | active | construction §7b | — |
# | A14 | **留存去向审计**：从未分红、无回购；资本开支 FY2023–2025 0.55 / 0.67 / 1.56 亿 vs 折旧 0.30 / 0.34 / 0.44 亿，NPPE 2.39 亿（2024Q3）→ 5.20 亿（2026Q2），持续远超折旧 → 公司层 **E 桶**（稳态增长资本开支）+ Neutron **D 桶**（窗口终点 = 首飞后 18–24 个月，已移入期权投入，A12）；增长靠增发融资而非留存（段一派息为负 = 发股融资的增长）。卫星 + Electron 腿用完整式 \(b=g/ROIC\)（边际 ROIC，A6）。「视同派出」k 行不设：无派息、无超额留存，9 月 ATM 现金具名用于铱星对价（B 桶，按面值计且已在 A9 一减一加）→ k = 0。禁止形态七条逐条未命中 | active | 10-K 现金流量表；Longbridge NPPE | Formula |
# | A15 | **候选带（自推增速线性衰减，规则例外，用户 2026-10-03 拍板）**：仓库只许候选带替换「单家 / 待补」输入，自推外推不在允许来源内。路径：2024–2027 年四个营收增速（+78% / +38% / +60%E / +42%E）线性拟合斜率 −8.6pp / 年，从 FY2027 的 42% 外推 → 2028–2031 年 33.4% / 24.8% / 16.2% / 7.6%，其后 g2；成熟利润率同底牌、FY2029 起计，每年增长按 0.40 追加资本扣除，尾段同一 Gordon 尺走稳态回报路径（可见年延到 2031、2035 年落到 min(前瞻, 30%)），整腿同底牌折 τ（A19）。只作用于卫星 + Electron 腿的 M / H；L′ = L。外推 2030 年剔 Neutron 营收 24.4 亿，与一条未核实的 3 位分析师摘要（2030 年 26.1 亿含 Neutron）同量级。**2026-10-04 复核（未升级）**：FY2028 只有聚合点值——营收 17.70 亿、EBIT 2.42 亿、EPS 0.14（MarketScreener，2026-10-04；Simply Wall St 17.75 亿）；每年家数与高低区间不可见，Zacks（Nasdaq）年度预测只到 FY2027（2 家）；未找到任何具名卖方的 FY2028+ 卫星制造营收 / 利润预测，Wisburg 无覆盖报告——不满足 ≥2 家带区间（进分子）或 ≥2 家点估计（进过渡年），保留候选带。交叉：共识 FY2028 隐含增速 29.9%（17.70 ÷ 13.63），自推 33.4%；自推剔 Neutron 的 FY2028 营收 16.85 亿与共识差 0.85 亿 ≈ 1.7 次 Neutron（爬坡第二年 3 次的量级内，共识可能含 Neutron）；共识 FY2028 EBIT 率 13.7% 落在本框架 L / M 成熟利润率（10.3% / 15.5%）之间。**升级门槛**：≥2 家具名卖方给出 FY2028+ 营收或 EBIT → 替换为两段式过渡并删除本行 | active | yfinance；10-K；MarketScreener / Simply Wall St 2026-10-04；Nasdaq（Zacks）2026-10-04 | 候选带 |
# | A16 | **杠杆门**：净债 / EBITDA 为负（净现金）未触发；利息 / EBIT：FY2025 合并 EBIT −2.29 亿 < 0 → **按公司口径触发**（`INTC.US` / `SPCX.US` 同例）。本框架为「无杠杆各腿 + 净现金收尾」，ROIC 拆解与去杠杆分子视同满足。交割后承接铱星 17.75 亿定期贷款（浮动利率 `待补`）：+100bp ≈ 0.18 亿 / 年，税后约 0.02 / 股。类债工具：可转债余额 0.13 亿（2026 年大部分已转股），按债计 | active | 10-Q；GovConWire | `debt` / `ir_nd` |
# | A17 | **③ 护栏与对账**：卫星 + Electron 腿从未盈利，无同等盈利月份 → 带测试「无可比状态」，不降篮、不带边反推；铱星腿的倍数即自身实测带（A8）。A2d 印证：卖方 TP 方法未公开（`待补`）；EPS 为负 → PEG 未采用；无分红 → 股息交叉不适用；可比 EV / 营收（yfinance 2026-10-02，2027E）：Firefly 4.7、Planet 9.7、Redwire 3.8、MDA 2.3、Intuitive Machines 3.2、AST SpaceMobile 29、SpaceX 18（只作交叉，不定锚） | active | 对话调研 2026-10-03 | Outputs 披露行 |
# | A18 | **卖方 Neutron 预测逐家（2026-10-04 检索；Wisburg 无 RKLB 个股研报，以下为公开报道摘要）**：摩根士丹利（Liwag，2025-10-13，TP 68 → 后 105）——2025 年 1 次测试、2029 年爬到每年 12 次，早期利润率为负，公司营收 2025–2029 年复合 41%；花旗（Godyn，2026-10-01，105）、Cantor（Sheppard，2026-08-11 / 09-21，122；只复述单价与「每台发动机最多复用 20 次」）、美银（Epstein，2026-08-14，115 → 110；2045 年前三情景 DCF，未披露次数）、KeyBanc（Leshock，约 2026-09，135）、Raymond James（Gesuale，2026-09-11，80；「2027–2028 年 EBITDA 与自由现金流转正」）、Needham（2026-02-27，95，后 120）、德银（Yu，120）、Stifel（150）——公开摘要均无 Neutron 次数、收入或利润率。非卖方：Northwise Project（独立研究）2027–2030 年 2 / 7 / 12 / 18 次、2028–2030 年 Neutron 收入 4.0 / 7.8 / 12.0 亿、毛利率 43%；Motley Fool 撰稿人「7 次 × 5,000 万 = 3.5 亿」算例。**结论**：任一年都没有 ≥2 家卖方数字 → 取数序第一层不满足，份数退到公司具名的量（A11）；摩根士丹利 12 次按 2025 首飞排，顺延到 2027 首飞约当 2031 年，与本框架 16 次同量级（12 次 @2031 → \(V_{opt}\) 2.33）。**升级门槛**：第 2 家卖方公开同年 Neutron 次数 / 收入 | active | Yahoo Finance / TheStreet 2025-10-13（摩根士丹利）；TipRanks 2026-10-01；Investing.com 2026-08-11、2026-02-27；Bitget 2026-08-14；Yahoo Finance 2026-09-11、2026-09-21；24/7 Wall St 2026-09-01；northwiseproject.com | A11 |
# | A19 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」①–④，2026-10-16 纠正）**：**超额现金不单列**——本框架是「无杠杆各腿 + 净现金收尾」结构，净现金（含 9 月 ATM）已按面值进收尾，腿分子是经营利润、不含利息，不双计 → 保留原结构；归母比例 1。**增长期资金缺口：不计**——只计产出落在分子年内的扩产；Neutron 在分子年之后投产，已在期权里扣未投资本（机队）并在表3 全额扣首飞前投入；卫星 + Electron 腿没有具名的前瞻扩产资本开支数据。**时点对齐**：旧框架按「FY2029 到达」整年折回 2 年（基准 = 2027-01-01）；还原到估值基准日 2026-06-30 后 τ = 2.5 年，即在 `n_arr` 之外再折 `tau` 0.5 年；窗口可分配利润 = 2026H2–FY2028 尚未入账的公司级共识 EPS（−0.115 − 0.082 + 0.14 = −0.057 / 股）× (1 − b) < 0 → 截到 0。铱星腿（EV/EBIT 当期年金）与净现金不适用。**稳态回报三段**（②，只作用于卫星 + Electron 的 Gordon 腿与 Neutron 期权）：腿的前瞻边际 ROIC L 20.3 / M 30.6 / H 39.5%、期权 65.2%；默认路径 Y1 = 可见年末 = 到达年 2029；进入门槛判**中** → 回落 4 年，Y2 = 2033——依据：卫星整星与部件产线 1–2 年可扩、政府客户认证周期长、小火箭发射已有多家新进入者但成功率低。稳态值按**叙事换代的腿**（retention「叙事换代的腿」；**用户 2026-10-19 裁定**），两条判据：① **自身周期不可用**——卫星 + Electron 从未有过盈利年份（FY2021–2025 经营利润均为负，亏损来自亚规模与 Neutron 投入期），没有一轮可读的经营回报；② **没有同一门生意的成熟同业**——洛克希德、诺格、L3Harris、通用动力四家军工总包商做的是大型武器系统总包（战机、舰船、导弹、指挥控制），不是中小卫星整星 + 小火箭发射这门生意，与 `FORM.US` / `TER.US` 不认作同业的裁定同一标准（用户 2026-10-19）；MDA 增速 > 10% 不算成熟；上市发射商没有 ≥ 5 年读数的成熟样本 → 同业层为空。→ 稳态 = min(该档前瞻, 30%)，不回落到兜底：L 20.3%（低于 30%、不回落）/ M 30.6% → 30% / H 39.5% → 30%（倍数 17.47 → 16.76×），M 档几乎不动，L 档不动。旧读数（四家账面口径中位 30.1%、投入资本含养老金口径中位 14.2%）作废，不再进锚点。期权（A11）同按叙事换代（前瞻 65.2% → 30%），但高回报期按 Neutron 自身产品阶段取 Y1 2031 / Y2 2037（倍数 18.47 → 16.98×）、再同折 τ：\(V_{opt}\) 3.15 → 3.19。候选带（A15）尾段可见年延到 2031、Y2 2035，整腿同折 τ：M′ / H′ 12.49 / 19.49。\(g_2\) 5% 是自定层，不配对。**k**：无 | active | 10-Q Q2'26；yfinance 共识 2026-10-02；Longbridge 年报（洛克希德 / 诺格 / L3Harris / 通用动力 / MDA）2026-10-16；用户裁定 2026-10-19 | `tau`、`y1`、`y2`、`rs_steady`、`opt_fall`；卫星 + Electron 腿、\(V_{opt}\)、候选带 |
# 原框架历史，迁移未新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-10-03
# - 规则迁移（valuation-rules「未建模期权」2026-10-03：份数只来自本票具名的量、借量不借价、按兑现年折现）：Neutron \(V_{opt}\) 19.46 → 1.08——份数由「SpaceX 外部发射已实现 EBIT」改为公司自述稳态节奏 7 次 / 年 × 自报单价 5,000 万；倍数由借来的 20× 改为本票卫星 + Electron 腿 H 档尺（17.47×）；折现由 10 年拍值改为兑现年 2030 折回 FY2027。表3 修正带 8.81 / 16.61 / 35.27 → 6.05 / 10.18 / 16.90；撤销「期权主导型」状态与 `SPCX.US` 跨票待办。底牌 L/M/H 6.51 / 10.42 / 16.44、候选带不变。`formula_id` → `_v2`。
# - touched: [题头, §0, 属性 B, 为什么落 \(V_{opt}\), A11, Inputs（删 `spx_launch_ebit` / `g_opt` / `roic_opt` / `n_opt`，增 `neutron_price` / `neutron_cadence` / `t_opt`）, Formula 步 6, Outputs, 表3, eval]
# ### 2026-10-04
# - Neutron 期权重做（valuation-rules「未建模期权」取数序；用户质疑「稳态 7 次」）：卖方 Neutron 预测逐家检索只有摩根士丹利一家（2029 年 12 次，A18），不足 2 家；份数由「公司自述 7 次」改为 CFO 具名机队产能 **16 次 / 年**（2025-12-04 高盛会议：约 4 架 × 每季周转；7 次降为一份，k = 2.29）；单位经济由卫星 + Electron 腿 H 档 20% 改为发射经济性 33%（CFO 单次成本 2,000–2,500 万 / 价 5,000–5,500 万 →「毛利率 50% 左右」− 费用率 17%）；兑现年 2030 → 2031；按新规则（valuation-rules「未建模期权」2026-10-04：新建产能型期权扣未投资本）扣首飞后新造 4 架可复用一级（每架造价未披露，拍值 5,000 万，2027–2030 每年一架按造年折回 = 0.26 / 股），首飞前剩余投入 0.63 仍在表3 全额扣；\(V_{opt}\) 1.08 → **3.67**，表3 修正带 6.05 / 10.18 / 16.90 → 6.44 / 11.08 / 19.48。另订正：「7 次 × 5,000 万 = 3.5 亿」是 Motley Fool 撰稿人算例，非公司口径。卫星制造 FY2028+ 复核：只有聚合点值（MarketScreener 营收 17.70 亿），无 ≥2 家具名带区间预测 → 候选带不升级（A15）。底牌 L/M/H 6.51 / 10.42 / 16.44、候选带不变。`formula_id` → `_v4`。
# - touched: [题头, §0, 属性 B, 为什么落 \(V_{opt}\), A11, A12, A13, A15, A18（新增）, Inputs（`neutron_cadence` 7 → 16、`t_opt` 2030 → 2031，增 `neutron_unit` / `t_unit` / `neutron_gm` / `neutron_opex` / `fleet_n` / `fleet_unit_n` / `booster_cost` / `t_fleet0`）, Formula 步 6, Outputs, 表2 `stretched`, 表3, eval]
HISTORICAL_PARTIAL_FINGERPRINT = '378b8153a4c3bef14ccbb46a800513a2630db25de26233dad782710b80378af9'

INPUTS = {
    # 10-Q 封面普通股 598,350,482; 来源：2026-08-05
    'shares_base': 0.59835,
    # 2026-09 ATM 新增股数（约 2,930 万，GovConWire；`待补`核 8-K）; 来源：2026-09-15
    'shares_sep': 0.0293,
    # 铱星总股本（Longbridge；完全稀释 `待补`）; 来源：2026-10-03
    'irdm_shares': 0.10596,
    # 换股比例上限（RKLB ≤ 67.5 时；合并协议）; 来源：2026-06-28
    'exch_ratio': 0.40,
    # 美国联邦法定税率; 来源：—
    'tax': 0.21,
    # FY2027 营收一致预期低端（yfinance）; 来源：2026-10-02
    'rev_l': 1.218,
    # FY2027 营收一致预期均值; 来源：2026-10-02
    'rev_m': 1.363,
    # FY2027 营收一致预期高端; 来源：2026-10-02
    'rev_h': 1.543,
    # FY2027 一致预期内含的 Neutron 收入（约 2 次 × 0.05，`待补`）; 来源：2026-10-03
    'neutron_rev': 0.10,
    # 洛克希德 Space 分部 FY2025 经营利润率（A5）; 来源：2025-12-31
    'margin_l': 0.103,
    # MDA Space FY2025 推算经营利润率（A5）; 来源：2025-12-31
    'margin_m': 0.155,
    # 自身 GAAP 毛利率 37% − 费用率 17%（拍值，A5）; 来源：2026-06-30
    'margin_h': 0.20,
    # 内生增长每 1 美元营收追加资本（A6，`待补`核 Neutron 资本开支）; 来源：2025-12-31
    'cap_int': 0.40,
    # 永续增速（无同业锚，≤ \(G_{cap}\)）; 来源：2026-10-03
    'g2': 0.05,
    # 篮 4 常规经营：合同制造 + 稳态发射，前五大客户 49% 不命中篮 7（A3）；Neutron 期权同用; 来源：2026-10-03
    'r_legs': 0.10,
    # 成熟利润率到达年数（FY2027 → FY2029）; 来源：2026-10-03
    'n_arr': 2,
    # 铱星 FY2027 EBIT 低档（M × 营收区间低端比例，A8）; 来源：2026-10-03
    'ir_ebit_l': 0.239,
    # 铱星 FY2027 EBIT（Longbridge 季度 EBIT 一致预期 × 4）; 来源：2026-10-03
    'ir_ebit_m': 0.260,
    # 铱星 FY2027 EBIT 高档（同源缩放）; 来源：2026-10-03
    'ir_ebit_h': 0.273,
    # 铱星 EV / TTM EBIT 月末带 p10（2025-01 至 2026-06-26，n = 18）; 来源：2026-06-26
    'ir_mult_l': 15.0,
    # 同带中位; 来源：2026-06-26
    'ir_mult_m': 20.0,
    # 同带 p90; 来源：2026-06-26
    'ir_mult_h': 29.6,
    # 铱星净债务（Longbridge）; 来源：2026-06-30
    'ir_nd': 1.605,
    # 每股现金对价（合并协议）; 来源：2026-06-28
    'ir_cash_ps': 27,
    # 现金及短期投资（Longbridge）; 来源：2026-06-30
    'cash': 2.302,
    # 2026-09 ATM 募资（GovConWire；净额 `待补`）; 来源：2026-09-15
    'sep_raise': 1.944,
    # 有息债务（含可转债余额 0.013）; 来源：2026-06-30
    'debt': 0.134,
    # Neutron 单次发射价（十亿美元；业绩会 5,000–5,500 万取下沿，A11）; 来源：2026-08-12
    'neutron_price': 0.05,
    # 期权份数：CFO 具名机队产能（约 4 架 × 每季周转一次，次 / 年；k = 16 ÷ 7，A11）; 来源：2025-12-04
    'neutron_cadence': 16,
    # 一份 = 公司自述爬坡终点「7 次及以上」的下沿（次 / 年，A11）; 来源：2025-11-16
    'neutron_unit': 7,
    # 一份兑现年 = 2027 首飞 + 1 → 3 → 5 → 7 爬坡第四年（A11）; 来源：2026-10-04
    't_unit': 2030,
    # 机队产能兑现年 = 爬坡到 7 次后再一年（无时点锚·拍值，A11）; 来源：2026-10-04
    't_opt': 2031,
    # Neutron 稳态单次毛利率（CFO：单次成本 2,000–2,500 万、价 5,000–5,500 万，「毛利率 50% 左右」取下沿；A11）; 来源：2023-03-24
    'neutron_gm': 0.50,
    # 费用率，同 `margin_h` 的规模化费用率拍值（A5）; 来源：2026-10-04
    'neutron_opex': 0.17,
    # 期权未投资本·机队：16 次 / 年所需可复用一级（CFO「约 4 架」；首飞那架不试回收、算在 `neutron_carry`，A11）; 来源：2025-12-04
    'fleet_n': 4,
    # 一份（7 次 / 年）所需一级架数（每季周转 4 次 / 架，只作披露，A11）; 来源：2026-10-04
    'fleet_unit_n': 2,
    # 每架可复用一级 + 整流罩造价（十亿美元；公司未披露 → 拍值：二级约占单次成本一半 = 1,000–1,250 万，一级 9 台 Archimedes 对二级 1 台，取约 4 倍 ≈ 单次报价；区间 0.03–0.10，A11）; 来源：2026-10-04
    'booster_cost': 0.05,
    # 机队首架开造年（首飞后每年一架，2027–2030，A11）; 来源：2026-10-04
    't_fleet0': 2027,
    # Neutron 剩余投入（`待补`；区间上沿 1.0，A12）; 来源：2026-10-03
    'neutron_carry': 0.42,
    # 候选带 FY2028 增速（A15）; 来源：2026-10-03
    'g_fade0': 0.334,
    # 候选带增速年降幅（2024–2027 线性拟合斜率）; 来源：2026-10-03
    'fade_step': 0.086,
    # 候选带衰减年数（2028–2031）; 来源：2026-10-03
    'n_fade': 4,
    # 时点对齐年数 = 估值基准日 2026-06-30（净现金日）→ 2027-01-01；卫星 + Electron 腿与 \(V_{opt}\) 在 `n_arr` 之外再折这 0.5 年（A19）; 来源：2026-06-30
    'tau': 0.5,
    # 卫星 + Electron 腿高回报期止点 = 可见年末（FY2029 到达年）；候选带顺延到 2031（A19）; 来源：2026-10-16
    'y1': 2029,
    # 稳态落稳年 = Y1 + 4（进入门槛：中）；候选带 2035（A19）; 来源：2026-10-16
    'y2': 2033,
    # 稳态回报上限 = 叙事换代：自身一直亏损、无同一门生意成熟同业（四家军工总包商不是同一门生意，用户 2026-10-19 裁定）→ 每档取 min(前瞻, 30%)，卫星 + Electron 腿与 Neutron 期权同用（A19）; 来源：2026-10-19
    'rs_steady': 0.30,
    # Neutron 期权回落年数 = 进入门槛高（可重复使用中型火箭）；期权高回报期 Y1 = 兑现年（满产年）、Y2 = Y1 + 6（A11）; 来源：2026-10-19
    'opt_fall': 6,
}
BASKETS = {"r_legs": 4}
REQUIRED = frozenset(INPUTS)

def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float) -> float:
    """Single-stage multiple on year-t0 earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2.  With rs >= roe this equals perpetual_pe.
    (gordon.py helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


NARRATIVE_CAP = 0.30  # retention「叙事换代的腿」: steady = min(tier forward, 30%), no fallback floor


def steady_pe(inp: dict, t0: int, roic: float, r: float, g2: float | None = None,
              y1: int | None = None, fall: int | None = None) -> float:
    """This ticker's ruler on the steady-return path (A19): forward ROIC to y1, then `fall`
    years down to min(forward, rs_steady) — rs_steady is the 叙事换代 cap 30% (A19)."""
    y1 = int(inp["y1"]) if y1 is None else y1
    fall = int(inp["y2"] - inp["y1"]) if fall is None else fall
    return three_segment_pe(t0, y1, y1 + fall, inp["rs_steady"], inp["g2"] if g2 is None else g2, roic, r)


def legs_value(inp: dict, t: str, r: float, g2: float | None = None) -> tuple[float, float, float, float]:
    """Space + Electron leg (USD bn), its NOPAT, marginal ROIC and multiple.  Numerator = the
    FY2029 arrival year; value at 2029-01-01 discounted n_arr + tau years to the 2026-06-30
    book (A19)."""
    rev = inp[f"rev_{t}"] - inp["neutron_rev"]
    m = inp[f"margin_{t}"]
    nopat = rev * m * (1 - inp["tax"])
    roic = m * (1 - inp["tax"]) / inp["cap_int"]
    pe = steady_pe(inp, NUM_YEAR + int(inp["n_arr"]), roic, r, g2)
    return nopat * pe / (1 + r) ** (inp["n_arr"] + inp["tau"]), nopat, roic, pe


def legs_candidate(inp: dict, t: str, r: float) -> float:
    """Same leg on the faded-growth revenue path (USD bn).

    FY2027 is t=1.  Revenue grows g_fade0, g_fade0 − step, … for n_fade years;
    the mature margin is earned from t = 1 + n_arr on that path (same arrival as
    the deck), every year's growth is charged cap_int of new capital, and the
    tail after the fade is the ruler on the last year's NOPAT × (1 + g2) — on the
    steady-return path with the visible years extended to the fade end (Y1 2031,
    same fall length) — and the whole leg carries the deck's tau (A19).
    """
    tax, ci, m = inp["tax"], inp["cap_int"], inp[f"margin_{t}"]
    n = int(inp["n_fade"])
    rev = inp[f"rev_{t}"] - inp["neutron_rev"]
    pv = 0.0
    nopat = 0.0
    for k in range(n):
        year = k + 2
        new = rev * (1 + inp["g_fade0"] - inp["fade_step"] * k)
        pv -= (new - rev) * ci / (1 + r) ** year
        rev = new
        if year >= 1 + inp["n_arr"]:
            nopat = rev * m * (1 - tax)
            pv += nopat / (1 + r) ** year
    roic = m * (1 - tax) / ci
    pe = steady_pe(inp, NUM_YEAR + n + 1, roic, r, y1=NUM_YEAR + n)
    return (pv + nopat * (1 + inp["g2"]) * pe / (1 + r) ** (n + 1)) / (1 + r) ** inp["tau"]


def iridium_value(inp: dict, t: str) -> float:
    consideration = inp["ir_nd"] + inp["ir_cash_ps"] * inp["irdm_shares"]
    return inp[f"ir_ebit_{t}"] * inp[f"ir_mult_{t}"] - consideration




def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(inp, ('n_arr', 't_opt', 't_unit', 't_fleet0', 'fleet_n', 'fleet_unit_n', 'y1', 'y2', 'opt_fall'))
    if inp['y1'] < NUM_YEAR or inp['y2'] <= inp['y1']:
        raise ValueError('invalid return path years')
    baskets = BASKETS
    if "r_legs" not in baskets:
        errors.append("r_legs: no 篮 N in the Inputs source cell")
    errors += check_r(inp["r_legs"], "r_legs", baskets.get("r_legs"))
    r = inp["r_legs"]
    errors += check_g_cap(inp["g2"], r, "g2")
    # 叙事换代 (A19): own cycle unusable (never profitable), peer layer empty (user 2026-10-19:
    # the four defense primes are not the same business) → steady = min(forward, 30%).
    if abs(inp["rs_steady"] - NARRATIVE_CAP) > 1e-9:
        errors.append(f"rs_steady {inp['rs_steady']:g} must equal the 叙事换代 cap {NARRATIVE_CAP:g} (A19)")
    if inp["opt_fall"] not in (2, 4, 6):
        errors.append(f"opt_fall {inp['opt_fall']:g} must be an entry-barrier rung 2 / 4 / 6 (A11)")

    sh = inp["shares_base"] + inp["shares_sep"] + inp["irdm_shares"] * inp["exch_ratio"]
    closure = inp["cash"] + inp["sep_raise"] - inp["debt"]

    rows = {}
    for t in TIERS:
        lv, nopat, roic, pe = legs_value(inp, t, r)
        ir = iridium_value(inp, t)
        rows[t] = {"legs": lv, "nopat": nopat, "roic": roic, "pe": pe, "ir": ir,
                   "total": (lv + ir + closure) / sh}

    L, M, H = (rows[t]["total"] for t in TIERS)
    errors += ladder("L<M<H", L, M, H)
    A, B = cut_points(L, M, H)


    # construction §2c: flat-multiple ladder — numerators must already climb.
    errors += ladder("legs NOPAT", *(rows[t]["nopat"] for t in TIERS))
    errors += ladder("Iridium EBIT", *(inp[f"ir_ebit_{t}"] for t in TIERS))
    flat = [(rows[t]["nopat"] * rows["m"]["pe"] / (1 + r) ** (inp["n_arr"] + inp["tau"])
             + inp[f"ir_ebit_{t}"] * inp["ir_mult_m"] - inp["ir_nd"] - inp["ir_cash_ps"] * inp["irdm_shares"]
             + closure) / sh for t in TIERS]
    errors += ladder("flat-multiple L<M<H", *flat)

    # Neutron option: own named fleet cadence × own price, launch economics, own ruler, discounted from t_opt.
    t_opt, t_unit = int(inp["t_opt"]), int(inp["t_unit"])
    if not NUM_YEAR < t_unit <= t_opt:
        errors.append("t_unit / t_opt must lie after the numerator year, unit year first (A11)")
    if inp["neutron_cadence"] < inp["neutron_unit"]:
        errors.append("neutron_cadence below the stated unit cadence: k must be ≥ 1 (A11)")
    k_units = inp["neutron_cadence"] / inp["neutron_unit"]

    # Option high-return period follows Neutron's own product stage, not the satellite leg's
    # calendar (retention「高回报期 MUST 对上该腿自己的产品阶段」, user 2026-10-19): forward
    # return held through the year the named capacity is reached (Y1 = realisation year),
    # then opt_fall years (entry barrier: high) down to the same 叙事换代 cap.  Valued in the
    # realisation year, folded to FY2027, then the deck's tau to the 2026-06-30 book.
    tau_df = (1 + r) ** (-inp["tau"])
    opt_fall = int(inp["opt_fall"])

    def opt_ruler(gm: float, year: int = t_opt) -> tuple[float, float, float]:
        m = gm - inp["neutron_opex"]
        roic = m * (1 - inp["tax"]) / inp["cap_int"]
        return m, roic, steady_pe(inp, year, roic, r, y1=year, fall=opt_fall)

    m_opt, roic_opt, pe_opt = opt_ruler(inp["neutron_gm"])

    def fleet_pv(n_boosters: float, cost: float | None = None) -> float:
        """Unspent booster capital, one per year from t_fleet0, PV at FY2027 (USD bn)."""
        c = inp["booster_cost"] if cost is None else cost
        return sum(c / (1 + r) ** (int(inp["t_fleet0"]) + i - NUM_YEAR) for i in range(int(n_boosters)))

    def v_gross(year: int, n: float, price: float | None = None, gm: float | None = None) -> float:
        m, _, pe = opt_ruler(inp["neutron_gm"] if gm is None else gm, year)
        rev = n * (inp["neutron_price"] if price is None else price)
        return rev * m * (1 - inp["tax"]) * pe / (1 + r) ** (year - NUM_YEAR) / sh

    def v_at(year: int, n: float, price: float | None = None, gm: float | None = None,
             boosters: float | None = None, cost: float | None = None) -> float:
        b = inp["fleet_n"] if boosters is None else boosters
        return (v_gross(year, n, price, gm) - fleet_pv(b, cost) / sh) * tau_df

    opt_rev = inp["neutron_price"] * inp["neutron_cadence"]
    opt_nopat = opt_rev * m_opt * (1 - inp["tax"])
    v_opt = v_at(t_opt, inp["neutron_cadence"])
    v_unit = v_at(t_unit, inp["neutron_unit"], boosters=inp["fleet_unit_n"])
    if int(inp["t_fleet0"]) < NUM_YEAR or int(inp["t_fleet0"]) + int(inp["fleet_n"]) - 1 >= t_opt:
        errors.append("booster builds must start in/after FY2027 and finish before t_opt (A11)")
    carry = inp["neutron_carry"] / sh
    ps = OPTION_FRACTIONS
    if not all(0 <= p <= 1 for p in ps) or not ps[0] <= ps[1] <= ps[2]:
        errors.append(f"p_L/p_M/p_H must be in [0,1] and non-decreasing, got {ps}")
    plus_v = [rows[t]["total"] + p * v_opt - carry for t, p in zip(TIERS, ps)]

    # Candidate band: faded-growth path on the leg only; L′ copies the deck.
    cand = {"l": L}
    for t in ("m", "h"):
        cand[t] = rows[t]["total"] + (legs_candidate(inp, t, r) - rows[t]["legs"]) / sh
    errors += ladder("candidate L′<M′<H′", cand["l"], cand["m"], cand["h"])
    def v_path(y1_: int, fall_: int) -> float:
        pe_ = steady_pe(inp, t_opt, roic_opt, r, y1=y1_, fall=fall_)
        return (opt_nopat * pe_ / (1 + r) ** (t_opt - NUM_YEAR) - fleet_pv(inp["fleet_n"])) / sh * tau_df

    # r_f readings (_AXIS.rates): Δr_f moves the leg basket (multiple and the
    # arrival discount); Iridium's EV/EBIT band and the closure stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        out = [(legs_value(inp, t, r + dr)[0] + rows[t]["ir"] + closure) / sh for t in TIERS]
        return out[0], out[1], out[2]

    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    sensitivity = {
        "booster_cost": [v_at(t_opt, inp["neutron_cadence"], cost=x) for x in (0.03, 0.10)],
        "slip": v_at(t_opt+1, inp["neutron_cadence"]),
        "twelve_launches": v_at(t_opt, 12), "price": v_at(t_opt, inp["neutron_cadence"], price=0.055),
        "path": [v_path(t_opt, 4), v_path(int(inp["y1"]), int(inp["y2"]-inp["y1"]))],
        "gross_margin": [v_at(t_opt, inp["neutron_cadence"], gm=gm) for gm in (0.408, 0.60)],
        "growth": [[(legs_value(inp, t, r, g2=inp["g2"]+dg)[0] + rows[t]["ir"] + closure) / sh for t in TIERS] for dg in (-0.01, 0.01)],
        "capital": [[(legs_value(dict(inp, cap_int=ci), t, r)[0] + rows[t]["ir"] + closure) / sh for t in TIERS] for ci in (0.3, 0.5)],
    }
    result = {
        "ticker": "RKLB.US", "currency": LISTING_CCY,
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-06-30',
        "framework_as_of": None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of': '2026-10-19',
        "anchors": band((L, M, H)),
        "candidate": {"label": "自推营收增长衰减", "anchors": band([cand[t] for t in TIERS])},
        "option": {"value": v_opt, "fractions": band(ps), "anchors": band(plus_v),
                   "before_carry": band([rows[t]["total"] + p * v_opt for t, p in zip(TIERS, ps)]),
                   "carry_per_share": carry},
        "sh": sh, "closure": closure, "rows": rows, "flat": flat, "cut_points": [A, B],
        "k_units": k_units, "m_opt": m_opt, "roic_opt": roic_opt, "pe_opt": pe_opt,
        "opt_rev": opt_rev, "opt_nopat": opt_nopat, "v_unit": v_unit,
        "parameters": {"discount": r, "growth": inp["g2"],
                       "forward": band([rows[t]["roic"] for t in TIERS]),
                       "mature": band([min(rows[t]["roic"], inp["rs_steady"]) for t in TIERS])},
        "sensitivity": sensitivity,
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if r + dr <= inp['g2']:
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='USD', price_currency='USD', price_unit='per_share',
            priced_r={'r_legs': r}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def calculate(context):
    result = evaluate(INPUTS, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'baskets': BASKETS, 'numerator_year': NUM_YEAR,
         'option_weights': OPTION_FRACTIONS, 'steady_return_cap': NARRATIVE_CAP}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    rows, shares, closure = result['rows'], result['sh'], result['closure']
    result['segments'] = {
        'satellite_and_electron': {'unit': 'USD_PER_SHARE', 'values': {t.upper(): rows[t]['legs'] / shares for t in TIERS}},
        'iridium_net': {'unit': 'USD_PER_SHARE', 'values': {t.upper(): rows[t]['ir'] / shares for t in TIERS}},
        'cash_and_financing': {'unit': 'USD_PER_SHARE', 'values': dict.fromkeys('LMH', closure / shares)},
    }
    if result['option']['value'] >= 0:
        result['option']['value_unit'] = 'USD_PER_SHARE'
        result['option']['weights'] = result['option'].pop('fractions')
        result['option']['carry_unit'] = 'USD_PER_SHARE'
    else:
        result['option_unavailable_carry_per_share'] = result['option']['carry_per_share']
        result['option'] = {'status': 'unavailable', 'label': 'Neutron', 'anchors': None}
        result['option_unavailable_reason'] = 'neutron_net_increment_negative'
    parameters = result['parameters']
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['discount'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', parameters['growth'])},
        'forward_return': {'unit': 'RATIO', 'values': parameters['forward']},
        'steady_return': {'unit': 'RATIO', 'values': parameters['mature'], 'reference_value': NARRATIVE_CAP},
    }
    result['review_flags'] = ['historical_iridium_transaction_conditional',
                              'historical_neutron_fleet_and_funding_unverified',
                              'historical_neutron_overlap_with_consensus_unverified']
    return result
