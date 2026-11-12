#!/usr/bin/env python3
"""WOLF legacy valuation; no assumptions updated in this format migration.

Amounts are USD millions and share counts are absolute. Full-capacity margin,
realisation year and unspent equipment cost remain research estimates.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, g_cap, perpetual_pe
from lib.inputs import check_missing, ladder, require_whole_years
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'),
                'axes': {'sic': 'sic', 'capex': 'ai_capex'}}

FORMULA_ID = "wolf_asset_pb_fd_sic_axis_vopt_v6"
SHARED = ("g2_sic_src", "t_align", "ss_return_sic", "y1_sic", "y2_sic")
MM = 1e6
TIERS = ("l", "m", "h")
P_K = (0.0, 0.25, 1.0)
# | A1 | 估值必须使用完全稀释口径；本次股数 **114,667,000** = 季末在外53,021,000 + 剩余转债转股50,936,000 + 未归属奖励3,766,000 + Renesas权证4,944,000 + pre-funded权证2,000,000。**未归属奖励沿用旧期，精确本期余额待补**；尚未授予的计划额度不计，ESPP新预留1,700,000也不等于已发行。政府融资配套增发与权证单列条件性风险，不提前当已完成。 | weakened | [Q]权益变动表季末53,021千股、当季转股818千股；Note 9转债本金267.1→257.1，其余203.6 / 379.0不变。沿用10-K期末转股预留51,754千股减已转818千股=50,936千股；旧奖励与权证余额沿用2026-06-28。10-Q封面53,581,878为2026-10-30，不与季末负债混配；Note 10加权平均55,000千股含低价权证，不再加作基本股。Note 14 / [F]融资拟配套股权150、政府权证最多7.5%。 | `shares_fd` / `shares_basic`；完全稀释方法维持，固定旧股数被削弱 |
# | A2 | 收入恢复仍只作场景坐标，不进底牌；低坐标由旧指引年化600更新为**本期实际年化620**。M795.1 / H807.2维持，前者共识待更新。毛利打平线从年化约800下调为略低于800，尚无精确数。≥2家正EPS或正EBIT共识才触发盈利尺升级，未触发。 | active | 本期确认阶段改善：[E]收入155较前季149.6增3.6%，高于旧140–160指引中点；[C]毛利打平季度收入略低于200、利用率25%–30%；[E]下季155–175。旧FY2028E两家共识795.1（2026-09-13）保留；长桥2026-11-06已回填本期实际数，未证实远期预测刷新，共识待更新。 | `rev_l/m/h`坐标；`rev_fy27_mean` |
# | A3 | EV/Sales尺继续撤销；法院EV是第三方DCF判断，不是倍数生成器，恢复路径不能再与恢复收入重复相乘。法院EV只作历史交叉，不作为成功路径上限。 | active | 本期维持：[E]GAAP毛利率−21.9%、营业亏损112.8，尚无正盈利支撑收入倍数。旧尺3.53 / 3.91 / 4.29×仍为法院EV÷FY26拼接收入665.1；原撤销理由及日期2026-09-14沿用；[Q]本期未提供替代盈利尺。 | 历史EV/S带仅证据；旧尺不入锚 |
# | A4 | 净债务使用**非转股本金932.3 − 现金995.1 − 既有权证款118.4 = −181.2 $M**。剩余转债839.7已对应稀释股份，不能再次扣债；本金合计1772.0不得与完全稀释股数并用扣减。 | active | 本期维持方法并刷新：[Q]Note 9非转股635.9+296.4=932.3；转股257.1+203.6+379.0=839.7；合计1772.0。现金995.1；旧权证款=4.944M×23.95+2M×0.01≈118.4（旧余额日期2026-06-28）。政府贷款未提款不加现金，首批再融资不能当新增净现金。 | `debt` / `cash` / `conv_principal` / `debt_total` / `warrant_proceeds`；与A1同口径 |
# | A5 | 底牌为2026-09-27当期账面，不折现；成功路径FY2030兑现，按10%折回2026年，净现金不折现。FY2030=轴对齐年2028+2，仍是**无时点锚·拍值**；财季名称FY2027不使日历估值基准年跳到2027。 | active | 本期维持：[C]仍未给满产日期；[E]只给下季155–175指引。政府贷款希望年底完成是融资时点，不是产能兑现年。 | `t_opt` / `year_now`；不新增一年的时间滚动收益 |
# | A6 | 未采用PE / PEG / ROIC主尺：没有可长期化的正盈利分子。 | confirmed | 本期确认：[E]GAAP净亏143.8、营业亏112.8，GAAP / 非GAAP EPS −2.61 / −2.03。旧FY28E EPS −5.83共识待更新；不引用跨重整历史EPS作增长。 | 主尺仍资产PB；ROIC仅风险披露 |
# | A7 | 不采用EV/nameplate-wafer：缺少可换算的片数满产产能；利用率百分比不等于片数。 | active | 本期维持：[C]给出毛利打平设备利用率约25%–30%，未给满产片数；[Q]未补片数产能。不能与同业每片价值硬比，待补。 | 不换尺 |
# | A8 | L是清算/减值压力情景，不是保证地板；专用产线折价、持续烧损与优先债权可使股权继续低于账面、趋近0。 | confirmed | 本期确认：[Q/E]权益930.2→804.0，现金1088.6→995.1，自由现金流−96.5；[Q]非转股本金932.3仍优先于股权。fresh-start持续经营估值不等于清算可收回额。 | `pb_l`维持0.55 |
# | A9 | 卖方目标价不定锚；最近可见TP25替代原27.50作带日期参考，不能冒充财报后刷新。 | active | 本期维持：长桥institution-rating查询，最近更新2026-10-21：2家hold、1家no opinion，TP25；[E]财报11月4日发布，该评级在其之前。仅作坐标，共识待更新。 | 防目标价绑架 |
# | A10 | 三档共用本期静态资产负债表；仍未建模各情景未来现金消耗/生成。滚动到本期只确认已发生的亏损，不能声称已扣清后续爬坡资金。 | confirmed | 本期确认局限：[Q/E]现金减93.5、权益减126.2，经营现金流−84.2、自由现金流−96.5。资产PB折价近似承载亏损风险；[C]库存优化基本完成，不能把过去营运资金释放永久外推。 | 底牌与成功路径现金桥均有静态简化 |
# | A11 | 底牌=PB **0.55 / 0.80 / 1.00 × FD BPS 15.37**。FD账面=权益804.0+转债本金839.7+权证款118.4=1762.1，÷114667000。L清算/减值压力；M产能不作废但持续亏损；H值一个账面；三档具名情景，不是市场分位。 | weakened | 本期削弱旧账面数：[Q]权益804.0、债务Note 9；[E]负毛利及现金消耗仍在。A1奖励余额未重列，故新BPS仍含旧期奖励数量假设。PB三档不变；历史收盘最低14.80（2026-03-30）÷本期FD BPS=0.96仅作跨期证据，不是同日PB实测。 | `equity_book` / `pb_l/m/h` / `shares_fd`；底牌下移 |
# | A12 | 成功路径 **V_opt=22.51−15.37=7.15**；总成功世界22.79→22.51，差额增加不代表成功概率提高。份数维持Mohawk Valley满产收入2000；已装1100只作敏感性（2025-06债权人材料）。满产EBIT率沿用**14.9%**，区间−0.9%–20.4%（2026-10-03推断）；FY26Q4年化收入598、非GAAP成本718与旧毛利打平收入800联立，成本≈473+0.409×收入，外推满产毛利约35%、扣营业费用及GAAP差异得EBIT298。仍假设成本线线性、费用约330不随收入同比扩张；不得以爬坡FY28亏损率乘满产收入。经营资本**1580.9=804+1772−995.1**，NOPAT235.4、经营回报14.89%，g2=6%、r=10%，FY2030折回4年+净现金181.2，得22.51。**未投资本待补**：1100→2000的专项机台预算未披露，未扣资本使成功价值偏高；[Q]只说FY27 modest spend，不能把整体capex10.6或政府贷款1500当专项预算。政府融资未完成，既不加贷款现金也不加预计省息；股权150和最多7.5%权证单列风险，未来确定股数/执行价/提款额时连同现金、债务、用途一起更新。GaN与透明SiC缺可闭合量与利润率，不另叠价值。 | weakened | 本期经营证据增强但完整性削弱：[E]非GAAP毛利−19.8/收入155=−12.8%，销售成本174.8、营业费用63.6；[C]环比+710bp、打平收入略低于200/季、利用率25%–30%。只给模糊新打平点，不能精确重估长期成本线；本期数据支持改善而非足以抬高14.9%。[Q]Note 9、Note 14及MD&A；[F]配套股权150、政府权证最多7.5%与转债权益化条件。来源层级：本票公开数据推断；轴参数沿用。 | `V_opt`；升级：更远卖方满产预测/明确打平或满产年/追加机台预算/最终融资条款。证伪：收入年化800仍非GAAP负毛利；再融资失败及现金烧穿；新增稀释改变每股口径 |
# | A13 | 表3兑现比例维持 **0 / 0.25 / 1.0**（eval常量，不进Inputs）；中档0.25无概率锚·拍值。观测代理为收入年化对比毛利打平线、利用率与GAAP毛利转正，不用TP反推。 | active | 本期维持：[E]年化收入620，GAAP毛利率−21.9%；[C]打平设备利用率参考25%–30%而非本期实际利用率。改善未达到抬高中档比例的证据门槛。 | 表3 |
# | A14 | 整公司篮4常规经营，r=10%，只进成功路径；行业周期、重整历史、亏损不单独抬r。现有收入仍来自既有器件与材料经营；扩张融资有条件不等同本期收入依赖未落定融资。客户集中度未更新，不把旧10-K数字改成本期已证实。 | active | 本期维持：[E]器件116.8、材料38.2；[Q]现金995.1且管理层判断可覆盖至少12个月经营及资本需要。[F]政府融资用于再融资/后续战略项目，仍有条件；旧第一大27%、前两大38%（10-K截至2026-06-28）沿用。 | `r_perp`篮4 10%；底牌不用r |
# | A15 | 杠杆门继续视同触发。报表债务净额1680.6+租赁106.0−现金995.1=**791.5**；EBIT=营业亏损−112.8，EBITDA≈−83.6（加折旧摊销29.2），两者为负，不给无意义倍数。FD估值视同转股净现金181.2与报表杠杆并列。 | confirmed | [Q/E]本期确认；权益乘数2875.5/804=3.58。季末口径ROE≈−17.9%=净利率−92.8%×资产周转0.0539×权益乘数3.58（仅季度披露，非前瞻回报）；税后ROIC约−5.6%=−112.8×0.79/(804+791.5)，负域。利息40.0/负EBIT不作正比率解读。利率+100bp对年度税前费用约+17.72M、按21%税率EPS约−0.264（基本5302.1万股；亏损期无税抵则−0.334），静态全债重定价敏感性，不进锚。 | 无正盈利故底牌资产PB；成功路径分子用税后EBIT、净债桥已闭合，不重复扣息。盈利尺升级时重跑去杠杆与换尺门 |
# | A16 | 经营价值与超额现金规则：底牌资产PB不适用超额现金拆分，不新增现金价值。成功路径回报与EBIT率同走2030→2035，轴稳态兜底15%，前瞻回报**14.89%**封顶后稳态14.89%，常态EBIT率14.9%，基准无回落。高利润率敏感行回落到15%经营回报/常态EBIT率约15.0%。本次不动轴、不加第二次时点折现、不带折扣k。 | active | 本期维持方法、刷新派生值：[Q]经营资本1580.9；满产NOPAT235.4。稳态15%、Y1=2030/Y2=2035、g2截顶6%来自`_AXIS.sic`，2026-10-16/19已认可，未因本期财报修改。未投资本与未来烧钱局限见A10/A12，不能以公式派息率证明现金可释放。 | 回报/正常利润率/高利润率敏感行联动重算 |
# 原框架历史，本次迁移没有新增数据更新：
# （初建日不写条目。框架纠正只改现行块、不写 Changelog。事件追踪按自然日追加；同一天合并为一节。）
# ### 2026-09-20
# - v2 切换（篮子 r）：L/M/H v1 9.04 / 13.15 / 16.44 → 9.04 / 13.15 / 16.44，zone `stretched` → `stretched`（修正带 `optimistic` 不变）；篮子：整公司 → 篮 7 单押 / 故事 15%（A14）。底牌为资产 PB 尺、无 g2 行，r 只披露不入公式；\(V_{opt}\) 锚（法院 DCF，WACC 20.1%）不随篮子重折。新增 Outputs 披露行（隐含 r(P) / ③出带 / 敏感区 / 地板）。
# - touched: [A14, r_perp（新增，只披露）, Outputs 披露行]
# ### 2026-10-03
# - 规则迁移（期权上限锚由公开数据闭合、借量不借价、按兑现年折现）：\(V_{opt}\) 10.62 → **0**。原上限锚法院 fresh-start EV 上沿 $2,850M（桥到 FD 每股 27.06）是第三方 DCF 给的价，撤为交叉坐标；新锚 = 具名产能 Mohawk Valley 满产 ~$2B/年 × 对齐年份 FY2028E 共识净利率约 −39% → 本票篮 7 尺下无经营价值，只剩 FD 净现金 2.38/股 < H 16.44（实测最好单位经济敏感性 3.67，仍 < H）；兑现年 FY2030（对齐年份 + 2，无时点锚·拍值）。L/M/H 9.04 / 13.15 / 16.44 不变；表3 删除；`formula_id` `wolf_asset_pb_fd_court_vopt_v3` → `wolf_asset_pb_fd_own_vopt_v4`；Inputs 新增 `rev_named`、`eps_fy28e`、`rev_fy28e`、`gm_best`、`opex_meas`、`interest_meas`、`t_opt`、`year_now`。
# - 同业组：与 `2631.HK` 都有碳化硅衬底，但本票衬底与器件共用产线、整公司单腿，两票底牌都是资产尺、期权各用本票数据、都无 g2，尺子一致，不建组。
# - touched: [§0, 属性 E / G, A3, A5, A12–A14, Inputs, Formula 3–7, Outputs, 表2 `optimistic` / `stretched`, 表3（删）, 交叉备注, eval]
# - **同业尺轴 `_AXIS.sic` + 期权重算**（同日第二轮，用户裁定：乐观世界期权不能是 0；单位经济配满产；ROE 只算经营资本；篮 7 收窄；g2 取同业横截面）：上一条「不建组」作废，挂同业尺轴 `_AXIS.sic`（参照）。归篮 篮 7 15% → **篮 4 10%**（第一大客户 27%、前两大 38%、美国公司；器件无公开报价不入篮 6）。期权 \(V_{opt}\) 0 → **6.35**（\(V^{G}_{H}\) 2.38 → 22.79）：单位经济 FY2028E 共识净利率 −39%（爬坡中段）→ 满产 EBIT 率 **14.9%**（区间 −0.9%–20.4%：FY26Q4 实测 + CFO 打平点联立的成本线外推到 $2B，毛利率约 35%；计划书斜率 20.4% 作上端；今日价格满利用 −0.9% 作下端；卖方无 FY2029+ 估计）；经营资本 1,623.6（FD 账面 − FD 净现金），税后 ROE 14.5%；g2 —（1/r）→ 6%（功率半导体横截面中位 7.12% 截顶）；兑现年 FY2030 不变（无具名满产年）。表3 恢复：L′ / M′ / H′ = 9.04 / 14.74 / 22.79。底牌 L/M/H 9.04 / 13.15 / 16.44 不变。`formula_id` `wolf_asset_pb_fd_own_vopt_v4` → `wolf_asset_pb_fd_sic_axis_vopt_v5`；Inputs 新增 `rev_installed`、`m_full`、`m_full_lo`、`m_full_hi`、`m_plan29`、`tax_opt`、`lease_liab`、`g2_sic_src`、`t_align`，删 `gm_best`、`opex_meas`、`interest_meas`；`eps_fy28e` / `rev_fy28e` 降为敏感性。
# - touched: [题头主尺, §0, 属性 E / G, A5, A12–A15, Inputs, Formula 3–7, 口径, 中间量, Outputs, 表2 `optimistic` / `stretched`, 表3, 敏感性, eval]
# ### 2026-10-04
# - 规则迁移（valuation-rules「未建模期权」新建产能型期权扣未投资本，2026-10-04）：期权份数 Mohawk Valley 满产 ~$2,000M/年中，已装产能约 $1,100M 以上的一段属规划产能，按新规则应扣「预算 − 已投」。查 Disclosure Statement Exhibit E（FY26–29 购建 PP&E 200 / 50 / 100 / 100，混列收尾与维持性、只到约 50% 利用率）、10-K（2026-06-28，初期阶段 FY2025 末基本完工、FY2027 capex 继续低位、无金额）、电话会 2026-08-19（无 capex 指引）、CHIPS PMT（2024-10-15，未落定、非专项），均无可归因于 1,100 → 2,000 的预算 → \(V_{opt}\) 6.35 → **6.35**（不动数），A12 标「未投资本 `待补`」、偏高方向、升级门槛（披露机台预算即扣，新增 `mvf_k`、`formula_id` 升版）。L/M/H、表3、`formula_id` 不变。
# - touched: [题头更新日, §0, A12]
# ### 2026-11-06
# - FY2027Q1财报后核对（截至2026-09-27；财报2026-11-04美东盘后、10-Q 2026-11-05美东提交）：收入155.0、器件116.8、材料38.2；非GAAP毛利率−12.8%，环比改善710bp；GAAP毛利−21.9%、营业亏112.8，经营/自由现金流−84.2/−96.5。CFO把季度毛利打平收入由约200下调为“略低于200”，约25%–30%设备利用率；FY27Q2收入指引155–175。毛利打平不等于营业或现金流打平。
# - 假设逐条：A1削弱固定股数、保留完全稀释方法；A2确认阶段恢复；A3维持撤销EV/S；A4维持方法并更新净现金；A5维持2030兑现；A6确认无正盈利尺；A7维持缺片数；A8确认非保底；A9维持TP不定锚、旧坐标27.50→25（2026-10-21）；A10确认静态现金局限；A11削弱旧账面；A12经营支撑增强但融资/投资完整性削弱；A13维持兑现比例；A14维持篮4；A15确认杠杆门触发；A16维持回报/利润率同路规则并重算派生值。
# - 本期权益930.2→804.0、现金1088.6→995.1、剩余转债本金849.7→839.7（已转股10.0）；非转股本金932.3不变。本期季末股数53.021M加剩余转股50.936M、旧奖励3.766M、旧权证6.944M，FD股数115.459396M→114.667M；奖励/权证完整期末余额待补，不把EPS加权55M或10月30日封面股数混入。FD BPS16.44→15.37，L/M/H **9.04/13.15/16.44→8.45/12.29/15.37**；切点10.37/13.83。
# - PB0.55/0.80/1.00、篮4 r10%、g2 6%、轴稳态15%、Y1/Y2 2030/2035、满产EBIT14.9%、兑现FY2030均不变。净现金274.7→181.2、经营资本1623.6→1580.9，满产回报14.5%→14.89%，成功世界22.79→22.51；V_opt6.35→7.15来自底牌下降更多，不是成功概率提高；表3 **9.04/14.74/22.79→8.45/14.08/22.51**。公式v6不变，已重算。
# - 补录10月7日政府有条件融资：最多1500，首批600拟再融资，配套股权150、政府权证最多7.5%、转债权益化/项目预算等条件；未完成不加贷款现金、不加预计省息、不提前发行股数。1100→2000专项机台预算仍待补，不能用贷款总额替代。
# - §0快照as-of改FY2027Q1/2026-09-27，题头为落盘日2026-11-06；旧FY27/28共识Inputs保留原日期并注明“共识待更新”，不延后本期实际数字落盘。
# - touched: [题头, §0, 属性E当前对照, A1–A16, §3 Inputs/Formula/中间量/Outputs/表1–3/敏感性]
HISTORICAL_PARTIAL_FINGERPRINT = 'ac88ca331f89ced9db66d491cb64edf0bda320dc622303f2deea78990c225237'

INPUTS = {
    # 季末股数+剩余转股+旧期奖励/权证；未归属奖励沿用2026-06-28，余额待补；A1; 来源：2026-09-27（奖励/权证2026-06-28）
    'shares_fd': 1.14667e8,
    # 季末在外53,021千股；10-Q权益变动表，不用封面10月30日股数或EPS加权股数; 来源：2026-09-27
    'shares_basic': 5.3021e7,
    # 现金及短期投资$M；10-Q资产负债表; 来源：2026-09-27
    'cash': 995.1,
    # 非转股债务本金635.9+296.4；10-Q Note 9，A4; 来源：2026-09-27
    'debt': 932.3,
    # 剩余转债本金257.1+203.6+379.0；10-Q Note 9；本期已转10.0; 来源：2026-09-27
    'conv_principal': 839.7,
    # 既有权证款；沿用10-K余额，未获本期完整重列；不含未完成政府权证，A1/A4; 来源：2026-06-28
    'warrant_proceeds': 118.4,
    # 债务本金合计；10-Q Note 9，净账面1680.6不是本金; 来源：2026-09-27
    'debt_total': 1772.0,
    # 权益合计=归母权益；10-Q权益表，FD账面另加转股本金与既有权证款，A11; 来源：2026-09-27
    'equity_book': 804.0,
    # 篮 4 常规经营 10%：整公司一篮（A14：器件与材料制造；第一大客户 27%、前两大 38%、美国公司，不命中篮 7；器件无公开报价，不命中篮 6）；底牌资产尺无 r 落点，**只进期权**（A12）；值 = `gordon.BASKET_R[4]`，`check_r` 按篮子强制; 来源：2026-10-03
    'r_perp': 0.10,
    # 底牌 L：清算 / 减值压力；A11; 来源：对话锁定
    'pb_l': 0.55,
    # 底牌 M：产能不作废但持续亏损；A11; 来源：对话锁定
    'pb_m': 0.80,
    # 底牌 H：值一个账面；A11; 来源：对话锁定
    'pb_h': 1.00,
    # 本期收入155年化，场景坐标；下季指引年化620–700另披露，不入底牌; 来源：2026-09-27
    'rev_l': 620,
    # FY2028E两家收入共识均值；旧来源yfinance，**共识待更新**，不以查询日期冒充更新; 来源：2026-09-13
    'rev_m': 795.1,
    # 收入恢复坐标 H $M：FY2024 持续经营收入（实测峰）；坐标（A2）; 来源：2025-06-29
    'rev_h': 807.2,
    # FY2027E三家收入共识均值；旧来源，**共识待更新**；坐标，不入公式; 来源：2026-09-13
    'rev_fy27_mean': 764.0,
    # FY2027E三家收入共识高端；旧来源，**共识待更新**；坐标，不入公式; 来源：2026-09-13
    'rev_fy27_high': 1006.0,
    # FY2026 拼接收入 $M（Predecessor+Successor）；旧尺 EV/S 的分母，只作交叉；10-K; 来源：2026-06-28
    'rev_fy26': 665.1,
    # 法院批准 fresh-start EV 区间下沿 $M；10-K Note 4；交叉（A12）; 来源：2025-09-29
    'ev_court_l': 2350,
    # 法院批准 fresh-start EV 区间中值 $M；交叉（A12）; 来源：2025-09-29
    'ev_court_m': 2600,
    # 法院批准 fresh-start EV 区间上沿 $M；**交叉坐标，不入公式**（2026-10-03 起不再作期权上限锚，A12）; 来源：2025-09-29
    'ev_court_h': 2850,
    # 法院 Note 4 桥表隐含权益 $M（出表日）；交叉，不入公式（A12）; 来源：2025-09-29
    'eq_court_bridge': 959.4,
    # 期权份数 = Mohawk Valley 满产收入产能 $M/年（Investor Day 2022 具名口径；2025-06 债权人材料 FY29 $1,000M @ 50% 利用率复核）；A12; 来源：2025-06-23
    'rev_named': 2000,
    # 已装产能可支撑收入 $M/年（2025-06 债权人材料「Capacity at end FY25 expected to support $1.1B in revenues」）；**只作敏感性**（A12）; 来源：2025-06-23
    'rev_installed': 1100,
    # 期权单位经济 = 满产 EBIT 利润率（公开数据推断：FY26Q4 年化实测 + CFO「年化约 $8 亿收入时非 GAAP 毛利率打平」两点联立 → 非 GAAP 销售成本 ≈ 473 + 0.409 × 收入 → 满产毛利率约 35%；扣营业费用约 330、SBC、无形摊销 62）；A12; 来源：2026-10-03
    'm_full': 0.149,
    # 区间下端：今日价格 × 满利用（剔除公司披露的利用不足成本后毛利率约 8%）；**只作敏感性**（A12）; 来源：2026-10-03
    'm_full_lo': -0.009,
    # 区间上端：计划书成本斜率（增量毛利率约 60%）外推到 $2,000M；**只作敏感性**（A12）; 来源：2025-06-27
    'm_full_hi': 0.204,
    # 计划书 FY2029 比率（毛利率 37.7% / 非 GAAP EBIT 16.3%，收入 1,450）按满产重算的 EBIT 率；**只作敏感性**（A12）; 来源：2025-06-27
    'm_plan29': 0.164,
    # 成功世界税率（美国联邦法定；NOL 615.7 先抵的部分不计）；A12; 来源：2026-06-28
    'tax_opt': 0.21,
    # 经营104.0+融资2.0；10-Q Note 4；只作债务敏感性，A15; 来源：2026-09-27
    'lease_liab': 106.0,
    # FY2028E共识EPS旧来源yfinance，**共识待更新**；只作爬坡敏感性，A12; 来源：2026-10-03
    'eps_fy28e': -5.83,
    # FY2028E收入共识旧来源，**共识待更新**；只作敏感性; 来源：2026-10-03
    'rev_fy28e': 795.1,
    # `sic` 腿 g2 来源 = 功率半导体 / 碳化硅横截面反解中位；`_AXIS.sic`；用时截到 G_cap 6%; 来源：2026-10-02
    # 对齐年份；`_AXIS.sic`; 来源：2026-10-03
    # 成功世界稳态回报；`_AXIS.sic`（同生意成熟同业为空 → 兜底「有壁垒的重资产」15%）；本票自身周期长期亏损，不构成下限；按 min(前瞻经营 ROE, 15%) 取，前瞻 14.5% 封顶（A16）; 来源：2026-10-16
    # 成功世界高回报期 Y1（回报与满产 EBIT 率开始回落）；`_AXIS.sic`（继承 `_AXIS.ai-capex`）（A16）; 来源：2026-10-16
    # 成功世界高回报期 Y2（落稳到稳态回报 / 常态 EBIT 率）；`_AXIS.sic`（A16）; 来源：2026-10-16
    # 期权兑现年 = 对齐年份 FY2028 + 2（无具名满产年：计划书 FY29 只到 50% 利用率，CFO 不给打平日期；**无时点锚·拍值**）；A5 / A12; 来源：2026-10-03
    't_opt': 2030,
    # 日历折现基准年；本期账面日2026-09-27，不随FY2027季度标签加一年; 来源：2026-09-27
    'year_now': 2026,
    # 出表后最低收盘 USD（2026-03-30，Longbridge 日 K）；证据 / 锚失效退路，不入公式（A11 / A12）; 来源：2026-09-14
    'close_own_min': 14.80,
    # 自身实测 EV/S 最低（2026-02-05 盘中低 13.485；FD 同口径）；**证据，不入公式**（A3）; 来源：2026-02-05
    'evs_own_min': 1.93,
    # 自身实测 EV/S 最高（2026-05-22 盘中高 80.82；属性 F）；证据; 来源：2026-05-22
    'evs_own_max': 13.62,
}
BASKETS = {"r_perp": 4}
REQUIRED = frozenset(INPUTS) - {"evs_own_max", "evs_own_min", "rev_fy27_high", "rev_fy27_mean"} | frozenset(SHARED)

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-segment RONIC path with the margin on the same calendar (valuation-rules
    「经营价值与超额现金」② 稳态回报三段; 2026-10-19 user: margin and return fade together,
    same method as 2631.HK).  Multiple on the t0 full-capacity NOPAT (t = 1): RONIC = roe and
    the full margin hold while c <= y1, both fall linearly to the steady return / normal margin
    by y2, steady thereafter.  rs = min(roe, r_s) (r_s floored at r by the caller); normal
    margin = rs × operating capital ÷ full revenue, i.e. a ratio rs / roe of the full margin —
    so when the forward roe is already below the axis steady return nothing fades."""
    rs = min(roe, r_s)
    m_ss = rs / roe

    def lin(cal: int, a: float, b: float) -> float:
        if cal <= y1:
            return a
        if cal >= y2:
            return b
        return a + (b - a) * (cal - y1) / (y2 - y1)

    def payout(ron: float) -> float:
        return 1.0 if g <= 0 else min(1.0, 1.0 - g / ron)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * m_ss * payout(rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * lin(cal, 1.0, m_ss) * payout(lin(cal, roe, rs)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1



def evaluate(i: dict[str, float]) -> dict:
    errors = check_missing(i, REQUIRED)
    if errors:
        raise ValueError("; ".join(errors))
    require_whole_years(i, ('t_align', 't_opt', 'year_now', 'y1_sic', 'y2_sic'))
    if i['y2_sic'] <= i['y1_sic']:
        raise ValueError('invalid return path years')
    # A1 counts converted shares, so A4 must exclude the debt those shares
    # replace and A11 must add it back to book. Both legs have to reconcile.
    if i["debt"] >= i["debt_total"] - 1e-9:
        errors.append(
            f"debt={i['debt']} is the full principal ({i['debt_total']}); shares_fd already "
            "prices the converts, so debt must be the non-convertible balance only (A1/A4)"
        )
    if abs(i["debt"] + i["conv_principal"] - i["debt_total"]) > 0.1:
        errors.append(f"debt({i['debt']}) + conv_principal({i['conv_principal']}) != debt_total({i['debt_total']})")
    if not (i["pb_l"] < i["pb_m"] < i["pb_h"]):
        errors.append(f"pb order violated: {i['pb_l']}/{i['pb_m']}/{i['pb_h']}")
    if not (i["m_full_lo"] <= i["m_full"] <= i["m_full_hi"]):
        errors.append(f"m_full {i['m_full']} outside its stated range [{i['m_full_lo']}, {i['m_full_hi']}] (A12)")
    leaked = [k for k in i if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    baskets = BASKETS
    if "r_perp" not in baskets:
        errors.append("r_perp source cell names no 篮 N (A14)")
    errors += check_r(i["r_perp"], "r_perp", baskets.get("r_perp"))
    r = i["r_perp"]
    g2 = min(i["g2_sic_src"], g_cap(r))
    errors += check_g_cap(g2, r, "g2 (_AXIS.sic)")
    if abs(i["t_opt"] - (i["t_align"] + 2)) > 1e-9:
        errors.append(f"t_opt {i['t_opt']} != t_align + 2 ({i['t_align'] + 2}): no named full-capacity year (A5)")

    # ---- Step 1: bottom card — fully diluted book × PB tiers (A11) ----
    book_fd = i["equity_book"] + i["conv_principal"] + i["warrant_proceeds"]
    bps_fd = book_fd * MM / i["shares_fd"]
    L, M, H = (i[f"pb_{t}"] * bps_fd for t in TIERS)
    A, B = cut_points(L, M, H)

    # ---- Step 2: option — full-capacity world on the own ruler (A12) ----
    net_debt = i["debt"] - i["cash"] - i["warrant_proceeds"]
    cap_op = book_fd + net_debt  # = equity + all debt principal − cash; convert-neutral

    def success(margin: float, rev: float | None = None, rr: float | None = None, g: float | None = None,
                cap: float | None = None, nd: float | None = None) -> dict[str, float]:
        rr = r if rr is None else rr
        g = g2 if g is None else g
        rev = i["rev_named"] if rev is None else rev
        cap = cap_op if cap is None else cap
        nd = net_debt if nd is None else nd
        nopat = rev * margin * (1.0 - i["tax_opt"])
        roe = nopat / cap
        rs = max(i["ss_return_sic"], rr)
        pe = (path_pe(g, roe, rr, int(i["t_opt"]), int(i["y1_sic"]), int(i["y2_sic"]), rs)
              if roe > 0 else 0.0)
        m_norm = min(roe, rs) * cap / (rev * (1.0 - i["tax_opt"])) if roe > 0 else margin
        disc = (1.0 + rr) ** (-(i["t_opt"] - i["year_now"]))
        v = (pe * max(0.0, nopat) * disc - nd) * MM / i["shares_fd"]
        return {"nopat": nopat, "roe": roe, "pe": pe, "disc": disc, "op": pe * max(0.0, nopat), "v": v,
                "m_norm": m_norm, "pe_flat": perpetual_pe(g, roe, rr) if roe > 0 else 0.0}

    post = success(i["m_full"])
    v_top = post["v"]
    v_opt = max(0.0, v_top - H)
    adj = [x + p * v_opt for x, p in zip((L, M, H), P_K)]
    adj_a, adj_b = cut_points(*adj)
    m_align = i["eps_fy28e"] * i["shares_basic"] / MM / i["rev_fy28e"]
    rev_scale = i["rev_installed"] / i["rev_named"]
    sens = {
        "margin hi (plan slope 2,000)": success(i["m_full_hi"]),
        "plan FY29 ratios": success(i["m_plan29"]),
        "margin lo (today price, full util)": success(i["m_full_lo"]),
        "FY28E cons margin (mid-ramp)": success(m_align),
        "installed capacity 1,100": success(i["m_full"], rev=i["rev_installed"]),
        "capital scaled x 2000/1100": success(i["m_full"], cap=cap_op / rev_scale),
        "leases as debt": success(i["m_full"], cap=cap_op + i["lease_liab"], nd=net_debt + i["lease_liab"]),
        "g2 -1pp": success(i["m_full"], g=g2 - 0.01),
        "g2 0": success(i["m_full"], g=0.0),
        "old 篮 7 r 15%": success(i["m_full"], rr=0.15),
    }
    court = {t: (i[f"ev_court_{t}"] - net_debt) * MM / i["shares_fd"] for t in TIERS}
    bridge_fd = (i["eq_court_bridge"] + i["conv_principal"] + i["warrant_proceeds"]) * MM / i["shares_fd"]
    evs = {t: i[f"ev_court_{t}"] / i["rev_fy26"] for t in TIERS}
    old = {t: (i[f"rev_{t}"] * evs[t] - net_debt) * MM / i["shares_fd"] for t in TIERS}
    basic = i["shares_basic"]

    if i["t_opt"] <= i["year_now"]:
        errors.append(f"t_opt {i['t_opt']} must be after year_now {i['year_now']}")
    errors += ladder("base", L, M, H)
    if abs(adj[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L row {adj[0]:.4f} != base L {L:.4f}")
    if errors:
        raise ValueError("; ".join(errors))
    def band(values):
        return dict(zip("LMH", values))
    sensitivity_ids = ("margin_high", "plan_2029", "margin_low", "ramp_margin",
                       "installed_capacity", "scaled_capital", "lease_debt",
                       "growth_down", "zero_growth", "basket_7")
    return {
        "ticker": "WOLF.US", "currency": "USD",
        "valuation_as_of": None, 'historical_valuation_as_of': '2026-09-27',
        "framework_as_of": None, 'historical_research_as_of': '2026-11-06', 'historical_framework_as_of': '2026-11-06',
        "anchors": band((L, M, H)), "candidate": None,
        "option": {"value": v_opt, "fractions": band(P_K), "anchors": band(adj)},
        "cut_points": [A, B], "option_cut_points": [adj_a, adj_b],
        "g2": g2, "book_fd": book_fd, "bps_fd": bps_fd, "net_debt": net_debt,
        "cap_op": cap_op, "post": post, "v_top": v_top, "m_align": m_align,
        "rev_scale": rev_scale, "sensitivity": dict(zip(sensitivity_ids, sens.values())),
        "court": court, "bridge_fd": bridge_fd, "evs": evs, "old": old, "basic": basic,
        "parameters": {"option_discount": r, "option_growth": g2, "option_forward": post["roe"],
                       "option_mature": min(post["roe"], max(i["ss_return_sic"], r))}
    }


def calculate(context):
    sic, capex = context['axes']['sic'], context['axes']['capex']
    if capex.get('role') != 'path_reference':
        raise ValueError('Wolfspeed requires the AI return-path reference role')
    shared = {key: sic[key] for key in ('g2_sic_src', 't_align', 'ss_return_sic')}
    shared.update(y1_sic=capex['y1_ai_capex'], y2_sic=capex['y2_ai_capex'])
    result = evaluate({**INPUTS, **shared})
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'shared': shared, 'option_weights': P_K,
         'baskets': BASKETS, 'million': MM}, HISTORICAL_PARTIAL_FINGERPRINT)
    result['units'] = {'price': 'USD_PER_SHARE'}
    result['segments'] = {'assets': {'unit': 'USD_PER_SHARE', 'values': dict(result['anchors'])}}
    result['option']['value_unit'] = 'USD_PER_SHARE'
    result['option']['weights'] = result['option'].pop('fractions')
    result['key_parameters'] = {
        'asset_book_multiple': {'unit': 'MULTIPLE', 'values': {t.upper(): INPUTS[f'pb_{t}'] for t in TIERS}},
        'success_discount_rate': result['parameters']['option_discount'],
        'success_growth_rate': result['parameters']['option_growth'],
        'success_forward_return': result['parameters']['option_forward'],
        'success_steady_return': result['parameters']['option_mature'],
    }
    result['review_flags'] = ['historical_equipment_budget_not_included',
                              'historical_warrants_and_awards_unverified',
                              'historical_conditional_government_financing_unverified']
    return result
