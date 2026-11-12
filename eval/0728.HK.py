#!/usr/bin/env python3
"""China Telecom's historical valuation. CNY inputs; H-share results HKD/share.

Retains the old 2026 valuation and evidence; this is not a new publication.
"""
from __future__ import annotations
from lib.gordon import check_branch, check_g_cap, check_r
from lib.inputs import check_missing, ladder, require_whole_years
from lib.tiers import decompose, flat_multiple_ladder
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'rf_report', 'partial_basis'), 'axes': {}}

# Values, original rationale and sources from the old Inputs table.
HISTORICAL_PARTIAL_FINGERPRINT = '91f9e8fe5bf0fe3dae19ee3fd57a8c34963945c536e43628a8c74e5f9c850eff'

INPUTS = {
    # 总股本 A+H | as-of 2026-09
    'shares': 91507138699,
    # 每股净资产 CNY（A 股 static；与 H 股 HKD BPS×fx 同量级） | as-of 2026-09
    'bps': 5.1568,
    # 归母权益**亿元** = bps × shares / 1e8 | as-of 2026-09
    'equity': 4718.83,
    # CNY per HKD；Longbridge exchange-rate 1/1.1465（A5） | as-of 2026-09-18
    'fx_hkdcny': 0.8722,
    # FY2027E EPS 下沿 CNY（A1） | as-of 2026-09
    'eps_l': 0.293,
    # FY2027E EPS 中位 CNY（A1） | as-of 2026-09
    'eps_m': 0.359,
    # FY2027E EPS 上沿 CNY（A1） | as-of 2026-09
    'eps_h': 0.476,
    # 篮 2 管制公用 HKD 段 r = r_f 中枢 4.0 + 篮子溢价 3.5（A4 / A16）；零增长 → 13.33×；cap = min(6%, r − 4%) = 3.5% | as-of 2026-09-18
    'r_perp': 0.075,
    # 篮 2 管制公用 r，跨市场固定（A4）；只用于 A 股对照带 | as-of 2026-09-18
    'r_perp_a': 0.075,
    # 利率轴 r_f 货币段差 = HKD 中枢 4.0 − CNY 2.5（A4）；只用于货币段披露行（A 股 r_perp − gap = 6.0% 的对照带），**不进底牌**；601728 十年 PE 中位的 g 0 读数 5.7% 互证 | as-of 2026-09-18
    'cny_rf_gap': 0.015,
    # 派息政策（2026 中期按归母 75%；FY23–25 70–77%）；定 \(g_2\) 与 `check_branch` 的实付派息 | as-of 2026-08-20
    'payout_policy': 0.75,
    # FY2025 资本开支亿 CNY（2021–25：849 / 915 / 899 / 903 / 731）；**不进公式**；A15 证据 | as-of FY2025
    'capex_fy25': 731,
    # FY2025 折旧摊销亿 CNY；**不进公式**；A15 证据 | as-of FY2025
    'da_fy25': 1042,
    # FY2025 固定资产净值亿 CNY（2021–25：5,286 / 5,374 / 5,591 / 5,323 / 5,090，Longbridge A 股 BS）；2021–23 上升 → capex > D&A（A15）；**不进公式**；重审条件 = 连续四年下降 | as-of FY2025
    'nppe_fy25': 5090,
    # 净现金亿 CNY（现金 1,115 − 有息债 493）≈ 0.68 CNY = 0.78 HKD/股，按面值只披露，**不进倍数** | as-of 2026-06-30
    'net_cash': 622,
    # 近全派息分支门槛（A3）；政策 75% < 门槛 → 留存分支 | as-of 2026-09
    'payout_obs': 0.80,
    # FY2026E 共识 EPS 中位 CNY（A1 交叉行同源）；只用于把 2H26 尚未入账的利润滚进 2027 年初净资产（A17） | as-of 2026-09
    'eps26_m': 0.323,
    # 1H26 归母净利**亿元**（中报）；已在 H1'26 账面里，从 FY2026E 里扣掉（A17） | as-of 2026-06-30
    'ni_1h26': 195.88,
    # 近三年实付派息率均值（现金股利 ÷ 归母：2023 200.6/304.5 = 66%、2024 235.3/330.1 = 71%、2025 250.6/331.9 = 76%，亿 CNY；yfinance 年报现金流量表）；**只进** A17 的 B 桶披露行，不进 BPS 推演（主尺按 \(b_1 = g_2/ROE\) 滚） | as-of 2025-12-31
    'payout_3y': 0.71,
    # 留存分支完整式 \(g_2 = (1 - payout\_policy) \times ROE_M\) = 25% × 6.9%（A3；病态区 → g 只能来自派息政策，A15）；三档共用；cap 3.5% ✓；g 0 作对照 | as-of 2026-09-18
    # 同上 | as-of 2026-09-18
    # 同上 | as-of 2026-09-18
    # 证据区间下沿 = 派息 80% × ROE_M（A13） | as-of 2026-09-18
    'g_evid_min': 0.014,
    # 证据区间上沿 = 派息 70% × ROE_M（A13） | as-of 2026-09-18
    'g_evid_max': 0.021,
    # 全样本自身 PE 护栏下沿（A2） | as-of Longbridge history
    'pe_own_min': 9.27,
    # 全样本自身 PE 护栏上沿（A2） | as-of Longbridge history
    'pe_own_max': 16.08,
    # 3 年带底；**不入主公式**，只作 ③ 出带读数 | as-of 2026-09
    'pe_3y_min': 11.27,
    # 3 年带顶；不入主公式 | as-of 2026-09
    'pe_3y_max': 14.03,
    # 云/AIDC 无分腿利润（A6） | as-of 2026-09
    'v_opt': 0,
    # 时点对齐年数 τ = 估值基准日（中报资产负债表日 2026-06-30）→ 分子年初 2027-01-01（A18） | as-of 2026-06-30
    'tau': 0.5,
    # 自身周期经营回报，投入资本口径（超额现金不足门槛 → 合并口径：税后（税前利润 + 利息费用）÷ 年初（权益含少数股东 + 有息负债 + 租赁））FY2016–25 十年均值 6.00%（FY2013–25 6.24%、FY2021–25 6.41%）；东财 F10 601728 合并报表（A18 ③） | as-of FY2025
    'ronic_own': 0.060,
    # 自身近三个完整财年同口径读数最大值（FY2023 6.31% / FY2024 6.80% / FY2025 6.73%），< r → L / M「持续失败」判据之一（A18 ③） | as-of FY2025
    'ronic_own_last3_max': 0.068,
    # 高回报期止点 = 可见年末（未讨论，默认；A18 ③） | as-of 2026-10-19
    'y1': 2027,
    # 回落止点 = Y1 + 6（高门槛：牌照 / 频谱 + 全国网络规模；A18 ③） | as-of 2026-10-19
    'y2': 2033,
}

# Historical evidence and judgments; comments are not additional model inputs.
# - **业务地图摘要**：中报附注「本集团只有一个经营分部」。产品收入三刀够大，但无分部利润；卖方主用整公司 PE / EV/EBITDA / 股息率，偶见 DCF-SOTP（含铁塔等股权）。启发式约 2–3 条命中，反信号（官方单分部）更硬 → 整公司尺；云留在整公司分子内，增量只进解释层（属性 E）。
# - **属性 A — 官方单分部，收入可拆、利润不可拆**：移动 / 固网智慧家庭 / 产业数字化 / 其他（H1'26：1,054 / 618 / 699 / 234 亿）。拆云缺 EBIT → 不进底牌。
# - **属性 B — 增值税 6%→9%（2026-01）是报表主拖累**：H1 经营收入 −4.1%，可比口径「基本稳定」。L 优先读税负 regime，不是份额崩塌。
# - **属性 C — 股东回报靠高派息，留存是支撑名义增长的资本**：FY23–25 约 70–77%；2026H1 中期按归母 75% 派（+3pp）。ROE ~6–9% < r 7.5% 峰形区；PP&E 5,090 亿 ≈ 权益 4,719 亿，资本密度 1:1，名义增长要吃留存——留存 25% 按账面 ROE 复利只换来 \(g_2\) 1.73%。
# - **属性 D — 现金流形态是公用事业的，不是「龙头制造」的**：资费名义市场化但三家寡头 + 工信部指导（A10）、派息政策书面化（70%+）、官方单经营分部、ROE 十年 5.8–7.4% 从未越过 8%；A 股十年 PE 中位按篮 2 定价，H 股在篮 2 上方 0.8pp（A16）。篮 2 的「管制」在本票是**事实管制**而非法定管制，是归篮理由里最弱的一条，靠两地十年 PE 带的 g 0 读数补强。
# - **属性 E — 天翼云 / AIDC 已在分子里，不另作期权**：H1 天翼云 618 亿、AIDC +9.3%、自称容量近 8GW——这些收入与利润已在合并 EPS 与 FY2027E 共识内（已在腿内的资产不得再进期权）；公司没有超出共识的具名量（收入目标 / 新增产能 / 合同，2026-10-03 检索未见），故期权份数为 0 → \(V_{opt}=0\)（理由是「无共识外的具名量」，不是「无卖方数」）。升级门槛 = 公司给出云 / 智算收入目标或新增 AIDC 产能投产计划（按目标 − 共识已含换算份数），或财报 / ≥2 家卖方可复算云贡献利润（届时拆腿）。
# - **属性 F — A/H 双挂，锚 H**：不挂 `_AXIS.southbound-repricing` 定倍数（轴已写对新挂载失效）；只双报，各用各的货币段 r。
# | A1 | 分子 = **FY2027E** 共识三点 CNY **0.293 / 0.359 / 0.476**（9 家）；时点对齐见 A18 | active | yfinance earnings_estimate +1y；FY2026E 0.275/0.323/0.349 作 VAT 年交叉 | `eps_*` |
# | A2 | 护栏 = 全样本自身 PE **[9.27, 16.08]**；L / M / H（12.02 / 13.00 / 13.47×）∈ 3 年带 [11.27, 14.03] | active | Longbridge valuation history n=157；3y high/low/median 14.03/11.27/12.23 | `pe_own_*` |
# | A3 | 分支 = **留存分支**：政策派息 75% < `payout_obs` 0.80 门槛 → \(g_2 = (1-payout\_policy) \times ROE_M\) = **1.73%** 三档共用，完整式 \((1-g_2/ROE_x)/(r-g_2)\)；各档 ROE 定派息率 69 / 75 / 81%；近全派息 g 0（\(1/r\) 13.33×）降为对照 | active | 中期 75%；FY 轨迹 70–77%；`check_branch(g2, ROE_M, r, 0.75)` M 档模型派息率 = 实付 | `g2_*` `payout_policy` `payout_obs` |
# | A4 | r = 篮 2 管制公用 **7.5%**（r_f 中枢 4.0 + 篮子溢价 3.5），跨市场固定：H 股锚点与 A 股对照带同值；货币段拆分（CNY 段 2.5 + 3.5 = 6.0%，r_f 差 1.5pp）是仓库级未立项的读法，只作披露行（A 股货币段带） | active | A16 归篮；`valuation-rules.md`「§r 篮子」篮子 r 跨市场固定；利率轴 HKD 中枢跟 USD、CNY 2.5 | `r_perp` `r_perp_a` `cny_rf_gap` |
# | A5 | fx = **0.8722** CNY/HKD（Longbridge exchange-rate 1/1.1465） | active | 2026-09-18 汇率 | `fx_hkdcny` |
# | A6 | 天翼云 / AIDC **\(V_{opt}=0\)**：已在合并分子与 FY2027E 共识内，且无超出共识的公司具名量（valuation-rules「未建模期权」2026-10-03：份数只来自本票具名的量；已在腿内的不再进期权）。升级门槛 = 公司具名云 / 智算收入目标或新增 AIDC 产能投产计划 → 按（目标 − 共识已含）× 本票单位经济、兑现年折回计 \(V_{opt}\)；或财报 / ≥2 家卖方可复算云贡献利润 → 拆腿 | active | 官方单分部；仅收入侧披露；2026-10-03 检索未见公司具名云收入目标 | `V_opt` |
# | A7 | Token/AI 套餐 12 个月内对盈利贡献有限 | active | 汇丰 89061；高盛会议纪要 | 不抬 H 分子 |
# | A8 | Capex 5G↓、AI↑，FCF 仍支撑高派息 | active | H1 Capex 324 亿、FCF 289 亿（+121%） | 派息可持续 |
# | A9 | **不挂**南向轴定倍数；A/H 只双报 | active | `_AXIS.southbound-repricing.md`；属性 F | 无轴倍数 |
# | A10 | 竞争理性、通服价格大体稳定 | active | 瑞银行业前瞻 | L 不叠价格战 |
# | A11 | DDM 与完整式在 \(g_d = g\) 下是同一把尺（\(b = g/ROE\) 即派息率的补），两地恒等，不单列对照带；\(g_d\) 3.8% 是派息率抬升期的 DPS 增速，非永续，作废 | active | §3 Outputs「DDM = 完整式」 | 无独立 DDM 带 |
# | A13 | \(g_2\) 证据区间 = **[1.4%, 2.1%]**（派息 80 / 70% × ROE_M）；两端三档（含时点对齐）4.09 / 5.29 / 7.18 与 3.85 / 5.21 / 7.20，M ±0.8% | active | 派息政策区间 FY23–25 70–77% + 中期 75% | `g_evid_*` |
# | A14 | **锚点是税前公允值**：南向持有 H 股的 20% 红利税是持有者税务（持有渠道不同税率不同：港股通个人 20%、香港券商直接持有 H 股 10%、A 股持有 >1 年免税），**不进锚点**；曾作分子折扣 k 0.85，2026-09-20 撤销——扣进锚点会使港股之间、A/H 之间不可比。H 股十年 PE 中位的 g 0 读数对篮 2 HKD 段多出的 0.8pp 作「H 股投资者结构折价」披露 | active | `valuation-rules.md`「锚点税前」；§3 交叉验证 ② | 无输入；§3 交叉验证 ①② |
# | A15 | \(b_g \approx 0\) 捷径（\(1/(r-g)\)、g 2.5%）**驳回**：三条证据本票只满足②（留存去向：净现金 +333 亿、有息债 774 → 493）——净 PP&E 2021–23 上升 305 亿（capex > D&A）、capex < D&A 仅 FY24–25 两年、NI 2021–25 CAGR 6.3% 远超 \(b \times ROE\) 1.73%（来源是 D&A 退坡，是 \(g_1\) 窗口题材不是「留存不复利」）；且资本密度 1:1 使通胀增长必须吃留存。重审条件 = 净 PP&E 连续四年下降且 AIDC capex 未回升至 D&A 以上 | active | Longbridge A 股年报（capex 849 / 915 / 899 / 903 / 731；净 PP&E 5,286 / 5,374 / 5,591 / 5,323 / 5,090；净现金 163 / 10 / 267 / 327 / 496 亿，2021–25） | `g2_*` `nppe_fy25` `capex_fy25` |
# | A16 | 归篮：整公司 → 篮 2 管制公用事业（(a) A 股十年 PE 带按篮 2 定价、H 股在篮 2 上方——g 0 读数（1/PE）：H 十年 PE 中位 12.0 → 8.3%，对 HKD 段 7.5% +0.8（对篮 4 −1.7）；A 十年中位 17.5 → 5.7%，对 CNY 段 6.0% −0.3（对跨市场固定的 7.5% 为 −1.8pp，对篮 4 CNY 段 8.5% 为 −2.8pp）；篮子跨市场固定、一家公司一个篮，A 股把它钉在篮 2，H 股多出的 0.8pp 是投资者结构折价（A14），残差在 3pp 门槛内；(b) 生意性质：寡头 + 工信部指导、派息政策书面化、官方单分部、ROE 十年 5.8–7.4%——现金流形态是公用事业的，「管制」是事实管制而非法定管制，为最弱一条；(c) 篮 4 下三档 ROE 全在峰形区，且两地十年 PE 中位（12.0 / 17.5×）都在篮 4 的 g 0 顶 \(1/r\)（10 / 11.8×；FY27 中枢 EPS 下 H 4.12 港元 / A 3.59 CNY）之上 = 不可达，按峰形区处理 ④ 排查：终值 ROE 输入错已排除（D&A 退坡造成的 \(\Delta NI/\Delta Equity\) ≈ 22% 是折旧窗口，同类资产重置的边际回报 ≈ 账面 7%）→ 归篮错）；CAPM 粗筛：未取 β，以两地十年 PE 中位的 g 0 读数作粗筛替代（A 5.7% 落篮 2；H 8.3% 在篮 2–4 之间偏篮 2）。cap = min(6%, 7.5 − 4) = 3.5% ≥ 1.73% ✓ | active | Longbridge 10 年月频 TTM PE（H / A）；`gordon.BASKET_R`；`valuation-rules.md`「§r 篮子」§7 规则 3、峰形区处理 ④ | `r_perp` `r_perp_a` |
# | A17 | **ROE 口径 = 分子年盈利 ÷ 分子年年初净资产（\(E_{n+1}/B_n\)），账面按增长所需留存滚动（valuation-rules 裁决表 ② / 两段式过渡，2026-09-21 定）**：\(ROE_x = EPS_{FY27,x} ÷ BPS_{2027 年初,x}\)，Gordon 的 \(g = b × ROE\) 里 ROE 是期初权益产出本期利润；年末口径会把本年尚未产出的留存放进分母，H1'26 账面直接作分母则少了半年留存。2027 年初 = 2026 末：从 H1'26 账面（BPS 5.157 CNY）起、只滚 **2H26 尚未入账**的利润 N = FY2026E 共识 0.323 − 1H26 实测 195.88 亿 ÷ 915.07 亿股 0.214 = **0.109 CNY/股**，**留存率 = \(b_1 = g_2/ROE\)**——无 g1 窗口，三档都按 \(g_2\) 滚。本票 \(g_2\) 自身 = (1 − 派息政策) × ROE_M，所以 M 档 \(b_1 = g_2/ROE_M\) 恒等于政策留存 25%，(ROE_M, BPS_M, g₂) 的联立不动点有闭式：\(BPS_M = 5.157 + 0.25 × 0.109 = 5.184\)，\(ROE_M = 0.359 / 5.184 = 6.93\%\)，\(g_2 = 25\% × 6.93\% = 1.73\%\)（旧 1.75%）；L / H 按这个共用 \(g_2\) 滚，\(BPS_x = 5.157 / (1 − g_2 × 0.109 / EPS_x)\) = 5.190 / 5.177 → ROE **5.6 / 6.9 / 9.2%**、\(b_1\) = 0.31 / 0.25 / 0.19（L 档模型要的留存高于政策：低盈利下 1.73% 也得多留）。倍数 12.02 / 13.00 / 14.07×（旧 12.03 / 13.02 / 14.09×；H 档 2026-10-19 起含回报回落 → 13.47×，A18 ③）。实付留存（29%，`payout_3y` 三年均值 71%）超出 \(b_1\) 的部分是留存去向审计的 B 桶，走 Outputs 披露行「模型视同派出、实际留存的现金」= (29% − \(b_1\)) × 0.109 ÷ fx = **−0.002 / +0.005 / +0.013 港元/股**（M 档只剩政策 75% 与三年实付 71% 的 4pp；它是锚点的前提「不被烧掉」，不是锚点外的价值，MUST NOT 另作腿）。旧口径留痕：H1'26 账面直接作分母 = 5.7 / 7.0 / 9.2%、g 1.75%（底牌 4.04 / 5.36 / 7.69）。现行 4.04 / 5.35 / 7.68 与旧口径差 −0.2% × 3：分母只多了半年增长所需留存，A 股对照带 / 货币段披露同步微调 | active | 中报 2026-06-30 归母净利 195.88 亿 / BPS；FY2026E 共识 yfinance +0y；yfinance 年报现金股利 / 归母净利 2023–25；valuation-rules 2026-09-21 | `eps26_m`、`ni_1h26`、`payout_3y`（只进披露行）；`g2_*` 0.0175 → 0.0173；表1 ROE 列 |
# | A18 | **经营价值与超额现金（valuation-rules「经营价值与超额现金」，2026-10-15）**：① **超额现金不单列**——净现金 622 亿（现金 1,115 − 有息债 493）照旧只披露，归母比例 0.984（归母 4,718.8 ÷（+ 少数股东 75.2）亿，2026-06-30）不涉及；**增长期资金缺口 0**：资本开支低于经营现金流（FY2025 731.5 vs 1,250.7 亿）。② **时点对齐**：分子 FY2027E、回报分母 2027 年初账面 → Gordon 值在 2027-01-01；估值基准日 = 中报资产负债表日 2026-06-30，\(\tau\) = 0.5 年，按篮 2 r 7.5% 折回；窗口（2H26）可分配利润 = 账面滚动里的 2H26 未入账共识利润 0.109 CNY ×（1 − 滚动用留存率 \(b_1 = g_2/ROE_x\)）按 \(\tau/2\) 折，三档 0.087 / 0.094 / 0.101 港元/股；M 5.35 → 5.25（−1.8%）。③ **稳态回报三段（按序取，2026-10-19 规则）**：**自身周期可用**——牌照电信、生意模式十余年未变、读数齐，取自身：投入资本口径（超额现金不足门槛 → 合并口径，现金留在分母：税后（税前利润 + 利息费用）÷ 年初（权益含少数股东 + 有息负债 + 租赁））FY2016–25 十年均值 **6.0%**（FY2013–25 6.2%、FY2021–25 6.4%；近三年 6.3 / 6.8 / 6.7%；东财 F10 601728 合并报表）；公用事业无谷到谷周期，取十年均值。L / M 前瞻 5.6 / 6.9% < r 且近三年读数都 < r → 「持续失败」，维持前瞻、不回落；H 前瞻 9.2% > r，自身 6.0% < r → 稳态取 r **7.5%**（≤ 前瞻、≥ r），高回报期 \(Y_1\) = 可见年末 2027（未讨论，默认）、回落 6 年到 \(Y_2\) = 2033（高门槛：牌照 / 频谱 + 全国网络规模）→ H 倍数 14.07× → 13.47×，H 7.51 → 7.19（−4.3%），L / M 不变；旧版「H 低于兜底 11% → 被前瞻封顶」改掉（兜底只是替补，自身可用不看兜底）。\(g_2\) 来自派息政策，不重解。④ 无打折 k | active | 2026 中报资产负债表；yfinance 年报现金流（FY2023–25）；valuation-rules「经营价值与超额现金」①②③ | `tau`；锚点 |

TIERS = ("l", "m", "h")
YI = 1e8
R_LEGS = ("r_perp", "r_perp_a")

REQUIRED = [
    "shares", "bps", "equity", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h",
    "r_perp", "r_perp_a", "cny_rf_gap", "payout_policy", "payout_obs",
    "eps26_m", "ni_1h26", "payout_3y",
    "g2_l", "g2_m", "g2_h",
    "g_evid_min", "g_evid_max",
    "pe_own_min", "pe_own_max",
    "net_cash", "v_opt", "tau",
    "ronic_own", "ronic_own_last3_max", "y1", "y2",
]
NUM_YEAR = 2027


def payout(g: float, roe: float) -> float:
    return 1.0 - g / roe


def path_pe(g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (retention.md 稳态回报三段) at the start of NUM_YEAR per unit of
    NUM_YEAR earnings: RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after.
    With r_ss >= roe it is exactly perpetual_pe(g, roe, r)."""
    if r - g <= 0:
        raise ValueError("r <= g")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = NUM_YEAR + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g, ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def evaluate(inp: dict[str, float], rate_inputs: dict | None = None) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('y1', 'y2'))

    r = inp["r_perp"]
    r_a = inp["r_perp_a"]
    fx = inp["fx_hkdcny"]
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    g2 = {t: inp[f"g2_{t}"] for t in TIERS}
    payout_policy = inp["payout_policy"]
    payout_obs = inp["payout_obs"]
    payout_3y = inp["payout_3y"]

    # Each r leg must name its basket and carry that basket's value (A4 / A16).
    baskets = {"r_perp": 2, "r_perp_a": 2}
    for leg in R_LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in Inputs source cell")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    for t in TIERS:
        errors += check_g_cap(g2[t], r, f"g2_{t}")
        errors += check_g_cap(g2[t], r_a, f"g2_{t}@r_perp_a")
    if abs(g2["l"] - g2["m"]) > 1e-12 or abs(g2["h"] - g2["m"]) > 1e-12:
        errors.append("g2 tiers must be identical (policy-derived, shared)")
    if payout_policy + 1e-12 < payout_obs and g2["m"] <= 0:
        errors.append(
            f"payout_policy {payout_policy:.0%} < {payout_obs:.0%} threshold is the "
            "retention branch; g2 must be > 0 (A3)"
        )
    if errors:
        raise ValueError('; '.join(errors))

    # ROE = E_{n+1} / B_n: FY27E EPS over the OPENING-2027 book (= end-2026),
    # not the H1'26 book and not the end-2027 book (valuation-rules 裁决表 ②
    # as of 2026-09-21; A17).  The H1'26 book is rolled over the 2H26
    # earnings not yet booked at the GROWTH-REQUIRED retention b1 = g2/ROE, never
    # at the actual payout complement.  Because g2 = (1 - payout) x ROE_M, the M
    # tier's b1 is exactly 1 - payout, so the joint fixed point (ROE_M, BPS_M,
    # g2) is closed-form; L / H then roll at that shared g2 with
    # BPS_x = BPS0 / (1 - g2 N / EPS_x).  FY2027's own retention is NOT rolled.
    bps0 = inp["equity"] * YI / inp["shares"]
    n_unbooked = inp["eps26_m"] - inp["ni_1h26"] * YI / inp["shares"]  # CNY/share, 2H26 only
    if n_unbooked <= 0:
        raise ValueError('2H26 unbooked EPS must be positive')
    bps_open = {"m": bps0 + (1.0 - payout_policy) * n_unbooked}
    roe = {"m": eps["m"] / bps_open["m"]}
    g2_policy = (1.0 - payout_policy) * roe["m"]
    for t in ("l", "h"):
        bps_open[t] = bps0 / (1.0 - g2_policy * n_unbooked / eps[t])
        roe[t] = eps[t] / bps_open[t]
    b1 = {t: g2_policy / roe[t] for t in TIERS}
    roe_old = {t: eps[t] / bps0 for t in TIERS}  # H1'26 book as denominator (superseded basis)
    excess_cash = {t: ((1.0 - payout_3y) - b1[t]) * n_unbooked for t in TIERS}  # B bucket, disclosure only
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"ROE basis {t}: b1 = g2/ROE = {b1[t]:.3f} outside (0,1) — roll diverges")
    # g2 is pinned by policy: (1 - payout_policy) x ROE_M, to input rounding.
    if abs(g2_policy - g2["m"]) > 0.0005:
        errors.append(f"g2_m {g2['m']:.4f} != (1 - payout_policy) x ROE_M = {g2_policy:.4f}")
    for t in TIERS:
        errors += check_branch(g2[t], roe[t], r, payout_policy, f"tier_{t}")
    if errors:
        raise ValueError('; '.join(errors))

    # Steady return 按序取 (A18 ③): own cycle usable; forward < r with the last three own
    # readings < r -> 持续失败, keep forward; else min(forward, max(own, r)).
    own, y1, y2 = inp["ronic_own"], int(inp["y1"]), int(inp["y2"])
    if y1 != NUM_YEAR or y2 != y1 + 6:
        errors.append("Y1 must be the visible-year end 2027 and Y2 = Y1 + 6 (high entry barrier, A18)")
    fail = {t: roe[t] < r and inp["ronic_own_last3_max"] < r for t in TIERS}
    ss = {t: roe[t] if fail[t] else min(roe[t], max(own, r)) for t in TIERS}

    def mult(g: float, t: str, rr: float) -> float:
        return path_pe(g, roe[t], rr, y1, y2, ss[t])

    # Pre-tax fair value: no holder-tax haircut on the multiple (A14).
    pe = {t: mult(g2[t], t, r) for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] - 1e-9 <= pe[t] <= inp["pe_own_max"] + 1e-9):
            errors.append(
                f"PE_{t} {pe[t]:.2f} outside own band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}]"
            )
    if errors:
        raise ValueError('; '.join(errors))

    # Timing (valuation-rules「经营价值与超额现金」③ 时点对齐, 2026-10-15): Gordon gives the
    # value at the numerator year's opening (2027-01-01); discount it tau years to the
    # balance-sheet date (2026-06-30) and add the window's distributable profit = the
    # 2H26 unbooked consensus profit x (1 - b1), b1 = the roll's g2/ROE, at tau/2.
    tau = inp["tau"]
    window = {t: n_unbooked * (1.0 - b1[t]) for t in TIERS}  # CNY/share

    def value(t: str, rr: float) -> float:
        return (eps[t] * mult(g2[t], t, rr) / (1 + rr) ** tau
                + window[t] / (1 + rr) ** (tau / 2)) / fx

    anchor = {t: value(t, r) for t in TIERS}
    L, M, H = anchor["l"], anchor["m"], anchor["h"]
    errors += ladder("anchor", L, M, H)
    A, B = cut_points(L, M, H)

    # Evidence interval = payout policy 80% / 70% (A13): disclosed bands.
    band_ev = {
        g_ev: tuple((eps[t] * mult(g_ev, t, r) / (1 + r) ** tau
                     + n_unbooked * (1.0 - g_ev / roe[t]) / (1 + r) ** (tau / 2)) / fx for t in TIERS)
        for g_ev in (inp["g_evid_min"], inp["g_evid_max"])
    }

    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0 until cloud contribution profit is sourced")

    eps_t = (eps["l"], eps["m"], eps["h"])
    pe_t = (pe["l"], pe["m"], pe["h"])
    anc_t = (L, M, H)
    flat_errs, flat_cny = flat_multiple_ladder(eps_t, pe["m"])
    errors += flat_errs
    flat_hkd = tuple(v / fx for v in flat_cny)
    dec = decompose(anc_t, pe_t)

    # A-share cross band at the same basket r, same multiple (A4 / A9).
    pe_a = {t: mult(g2[t], t, r_a) for t in TIERS}
    band_a = {t: eps[t] * pe_a[t] for t in TIERS}
    # Currency-segment reading (r_f gap HKD → CNY) -- disclosure, not an anchor.
    r_ccy = r_a - inp["cny_rf_gap"]
    band_ccy = {t: eps[t] * mult(g2[t], t, r_ccy) for t in TIERS}

    # Disclosure-only readings: book floor in HKD, net cash per share.
    floor_hkd = inp["bps"] / fx
    net_cash_ps_hkd = inp["net_cash"] * YI / inp["shares"] / fx

    if errors:
        raise ValueError('; '.join(errors))
    # Original document's comparisons below are undiscounted FY2027-start
    # values, unlike the formal anchors; steady returns remain fixed at basket 2.
    def undiscounted_band(rr, growth=None, currency='HKD', exchange_rate=fx, steady=ss):
        return {t: eps[t] * path_pe(g2[t] if growth is None else growth, roe[t], rr, y1, y2, steady[t])
                / (exchange_rate if currency == 'HKD' else 1) for t in TIERS}
    # For the separate basket-4 comparison the original document changes the
    # basket itself, so its steady return also follows that basket's 10% rate.
    basket4_steady = {t: roe[t] if roe[t] < .10 and inp['ronic_own_last3_max'] < .10
                      else min(roe[t], max(own, .10)) for t in TIERS}
    comparisons = {
        'zero_growth': {t: eps[t] / r / fx for t in TIERS},
        'r_minus_50bp': undiscounted_band(r - .005),
        'r_plus_50bp': undiscounted_band(r + .005),
        'growth_min': undiscounted_band(r, inp['g_evid_min']),
        'growth_max': undiscounted_band(r, inp['g_evid_max']),
        'basket_4_hkd': undiscounted_band(.10, steady=basket4_steady),
        'basket_4_cny_segment': undiscounted_band(.085, currency='CNY', steady=basket4_steady),
        'basket_1_hkd': undiscounted_band(.065),
        'fx_minus_1pct': undiscounted_band(r, exchange_rate=fx * .99),
        'fx_plus_1pct': undiscounted_band(r, exchange_rate=fx * 1.01),
    }
    # Old document's FY2026 downside cross-check: nine-house consensus low EPS
    # CNY .275, historical disclosure multiple 12.03, before timing alignment.
    comparisons['fy2026_low_pressure'] = .275 * 12.03 / fx
    # Original A/H tax comparison is holder-specific and is not deducted from
    # anchor prices: southbound dividend withholding 20% x M dividend yield.
    comparisons['southbound_tax_yield_drag'] = .20 * payout_policy * eps['m'] / (M * fx)
    def band_rf(dr):
        return tuple(value(t, r + dr) for t in TIERS)
    result = {
        'ticker': '0728.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'historical_valuation_as_of': '2026-06-30',
        'framework_as_of': None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of': '2026-10-19',
        'anchors': dict(zip('LMH', (L, M, H))), 'option': None, 'candidate': None,
        'eps': eps, 'g2': g2, 'bps0': bps0, 'n_unbooked': n_unbooked,
        'bps_open': bps_open, 'roe': roe, 'g2_policy': g2_policy, 'b1': b1,
        'roe_old': roe_old, 'excess_cash': excess_cash, 'fail': fail, 'ss': ss,
        'pe': pe, 'window': window, 'anchor': anchor, 'A': A, 'B': B,
        'band_ev': band_ev, 'flat_hkd': flat_hkd, 'dec': dec, 'pe_a': pe_a,
        'band_a': band_a, 'r_ccy': r_ccy, 'band_ccy': band_ccy,
        'floor_hkd': floor_hkd, 'net_cash_ps_hkd': net_cash_ps_hkd,
        'old_document_comparisons': comparisons,
    }

    if rate_inputs is not None:
        def checked_band(dr):
            if r + dr <= max(g2.values()):
                raise ValueError('rate scenario must exceed perpetual growth')
            return band_rf(dr)
        result['rate_sensitivity'] = calculate_rf_readings(
            rate_currency='HKD', price_currency='HKD', price_unit='per_share',
            priced_r={'r_perp': r}, band_at=checked_band,
            rates_loader=lambda _currency: rate_inputs, base_anchors=(L, M, H))
        result['rate_sensitivity'] = result_rate_sensitivity(result['rate_sensitivity'])
    return result


def policy_growth(inputs):
    # Historic research computes the rounded common rate from retained profit
    # and the M-tier ROE after rolling the opening book. Keep its four-decimal
    # adopted precision, while ensuring later policy or EPS edits propagate.
    bps0 = inputs['equity'] * YI / inputs['shares']
    unbooked = inputs['eps26_m'] - inputs['ni_1h26'] * YI / inputs['shares']
    bps_m = bps0 + (1 - inputs['payout_policy']) * unbooked
    return round((1 - inputs['payout_policy']) * inputs['eps_m'] / bps_m, 4)


def calculate(context):
    growth = policy_growth(INPUTS)
    result = evaluate({**INPUTS, **{f'g2_{t}': growth for t in TIERS}}, context.get('rate_inputs'))
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'tiers': TIERS, 'rate_legs': R_LEGS, 'numerator_year': NUM_YEAR,
         'units_100m': YI}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'HKD_PER_SHARE'}
    result['segments'] = {'company': {'unit': 'HKD_PER_SHARE', 'values': dict(result['anchors'])}}
    result['a_share_comparison'] = {t.upper(): result['band_a'][t] for t in TIERS}
    result['key_parameters'] = {
        'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', INPUTS['r_perp'])},
        'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', growth)},
        'forward_return': {'unit': 'RATIO', 'values': {t.upper(): result['roe'][t] for t in TIERS}},
        'steady_return': {'unit': 'RATIO', 'values': {t.upper(): result['ss'][t] for t in TIERS},
                          'reference_value': INPUTS['ronic_own']},
    }
    result['review_flags'] = ['historical_exchange_rate_source_unverified',
                              'historical_regulatory_classification_and_cash_needs_unverified']
    return result
