"""Historical Intel valuation, migrated without a new financial forecast."""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, perpetual_pe
from lib.inputs import ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'),
                'axes': {'advanced': 'leading_edge_foundry', 'foundry': 'mature_foundry'}}
BASELINE_LOCAL = '5b8871278a2fb8879812c0706177129ca4fc87b0ef27bd9de38adadd3aa031e0'
NARRATIVE_CAP = .30
MIN_R_MINUS_G = .02
ADJ_PS = ('net_cash_ps', 'nci_ps', 'mbly_stake_ps', 'altera_stake_ps', 'tax_asset_ps')
QTRS = ('q1', 'q2', 'q3')
EXT_YEARS = (2027, 2028, 2030)
WSPM = ('wspm_f52', 'wspm_f62', 'wspm_ie_now', 'wspm_ie_full', 'wspm_i7', 'wspm_legacy')
PX = {'18A': 'px_n3', '14A': 'px_n2', 'I3': 'px_n5', 'I7': 'px_n7', 'LEG': 'px_n16'}
TIERS = ('L', 'M', 'H')
MM, B = 1e6, 1e9
INPUTS = {
    'shares_diluted': 5310000000.0,  # 股本 = 归属权益 114,914 ÷ 每股净资产 21.6411 = 5,310M（8-K 2026-09-26；yfinance sharesOutstanding 5.31B 同）；流通股口径，RSU 稀释增量未计（由 A10b 的 SBC 扣除代偿）；**不含**美国政府托管股 1.43 亿（`escrow_shares` 另计一次，A10d） 2026-09-26
    'equity': 114914000000.0,  # 归属 Intel 股东权益 USD（8-K 2026-09-26：权益合计 131,556 − 少数股东 16,642 = 114,914）；ROE 分母，公司口径（无分部权益，A15）；**含 2026-08 约 $23B 增发**；剔除增发的产品腿读法见 §3 敏感区 2026-09-26
    'tax_rate': 0.12,  # A5 正常化 non-GAAP 税率；GAAP 实际 −0.3%(Q2) 因 valuation allowance，不可持续故不采（A5） 10-Q 2026-06-27
    'oi_products_l': 12739.0,  # L 分子：**FY2025 全年** Intel Products（CCG+DCAI）营业利润 $M——A2e-1 的**消化年（收入冻结）**：产品收入 FY2023 48,285 / FY2024 49,471 / FY2025 49,147（−0.7% YoY），OI 序列 11,073 / 13,008 / 12,739；也是同一 internal-foundry-model 口径上最近一个已实现的完整年；世界 = H1'26 的抬升是一次性的，运行率回到 FY2025 水平并从那里按 g2 增长；FY2023 谷底只作 `deep_discount` 压力坐标；A5 10-K FY2025 Note 3
    'rev_fy27_low': 64600000000.0,  # FY2027 合并营收共识下沿（yfinance +1y low，46 家）；**只作披露**——L 不用它（L = FY2025 实测消化年，周期票 L 例外），eval 打印其推断产品利润作坐标；A5c。**共识待更新**：Q3（2026-10-29）后卖方尚未改完，下一次事件增量重落 2026-10-30
    'rev_fy27_m': 72773000000.0,  # M 分子来源：FY2027 合并营收共识均值（yfinance +1y avg，46 家，区间 64.6–94.2B）——≥2 家带区间的最远年；× 产品占比 × 产品利润率 → `oi_products_m`（eval 计算）；A5c。**共识待更新**（同上） 2026-10-30
    'rev_fy27_h': 94171000000.0,  # H 分子来源：FY2027 合并营收共识上沿（同上 high，单家最高）；A5c。**共识待更新**：上沿是单家数，Q3 后大概率下修——这是 H 档最大的不确定性 2026-10-30
    'prod_rev_q1': 12779.0,  # Q1'26 Intel Products 收入 $M（CCPG 7,727 + DCAI 5,052）；A5c 推断输入 10-Q 2026-03-28（Longbridge 分部表）
    'prod_rev_q2': 15139.0,  # Q2'26 Intel Products 收入 $M（CCPG 8,877 + DCAI 6,262）；A5c 10-Q 2026-06-27
    'prod_oi_q1': 4058.0,  # Q1'26 Intel Products 营业利润 $M（H1 8,875 − Q2 4,817）；A5c 10-Q 2026-06-27
    'prod_oi_q2': 4817.0,  # Q2'26 Intel Products 营业利润 $M；A5c 10-Q 2026-06-27
    'cons_rev_q1': 13577.0,  # Q1'26 合并营收 $M；A5c 10-Q 2026-03-28
    'cons_rev_q2': 16128.0,  # Q2'26 合并营收 $M；A5c 10-Q 2026-06-27
    'prod_rev_q3': 15415.0,  # Q3'26 Intel Products 收入 $M（CCPG 8,097 + DCAI 7,318）；A5c 8-K 2026-10-29
    'prod_oi_q3': 5324.0,  # Q3'26 Intel Products 营业利润 $M（CCPG 2,285 + DCAI 3,039）；A5c 8-K 2026-10-29
    'cons_rev_q3': 16513.0,  # Q3'26 合并营收 $M；A5c 8-K 2026-10-29
    'prod_rev_fy25': 49147.0,  # FY2025 Intel Products 收入 $M——利润率敏感性（FY2025 25.9%）的分母；A5c 10-K FY2025 Note 3
    'cons_rev_fy25': 52853.0,  # FY2025 合并营收 $M——占比敏感性；A5c 10-K FY2025
    'r_perp': 0.1,  # CPU 腿永续贴现率 = **篮 4 龙头制造 10%**（产品腿，无备选；A19）；Foundry 腿归篮 7（15%）但无 r 行——它是期权（\(V_{opt}\)），按底牌篮子 r 估值与折现，15% 只作敏感性（A19）；A15 / §1 2026-09-20
    'g2_cpu': 0.045691,  # CPU 腿永续增速，三档共用；**来源层级：同业反解（半导体行业簇中位）**——14 家同日 forwardPE × ROE 反解，剔除不良条件与贴极点者后 8 家；**按 CPU 腿的同一回报路径重解**（2026-10-18 叙事换代：同业稳态 min(前瞻, 30%)、FY2027 / 2031，并做时点对齐：τ ≈ 0.3 年、加窗口利润；A24）：QCOM 5.46 / NVDA 3.68 / AVGO 5.69 / TXN 7.01 / NXPI 3.32 / STM −6.06 / MU −6.00 / 2454.TW 7.94% → 中位 **4.57%**（2026-10-16 版 15% 稳态 5.92%；原 perpetual 口径 4.25%）；≤ 上限 `g_cap(r)` = min(6%, r−4%) = 6%（篮 4 下未收紧）；\(r-g=5.43\%\) 2026-09-14 拉取（市场 as-of 09-11 收盘）；2026-10-18 重解
    'eps_fy27_hsbc': 4.25,  # 汇丰 2027E core EPS（税后、剔代工、未扣公司未分摊，A5b 已核同口径）——**单家，只作交叉校验**：须落在推断的产品 EPS [M, H] 内（A18；候选带已删） Wisburg 97352
    'pe_own_min': 6.04,  # 护栏下沿：自身 trailing PE 实测底（2022-07）；A16 Longbridge 2026-09-13
    'pe_own_max': 14.97,  # 护栏上沿：自身 trailing PE 实测顶（2023-02，盈利正常段）；A16 Longbridge 2026-09-13
    'cons_eps_fy27_low': 1.48,  # FY2027 合并调整后 EPS 共识下沿（yfinance +1y low，44 家）；只进口径二交叉坐标（A21）。**共识待更新** 2026-10-30
    'cons_eps_fy27_m': 2.193,  # FY2027 合并调整后 EPS 共识均值（yfinance +1y avg，44 家，区间 1.48–3.44；7 天前 2.13、30 天前 2.06）；A21 用它经 A5b 的桥反解 FY2027 代工亏损。**共识待更新** 2026-10-30
    'cons_eps_fy27_h': 3.44,  # FY2027 合并调整后 EPS 共识上沿（yfinance +1y high，44 家）；只进口径二交叉坐标（A21）。**共识待更新** 2026-10-30
    'oi_products_trough': 11073.0,  # FY2023 Intel Products 营业利润 $M（PC 去库存谷底）；只作 `deep_discount` 压力坐标（谷底 × 1/r + 闭合项 + L 档代工亏损），不作 L（A5） 10-K FY2025 Note 3
    'bridge_other_eps': 0.32,  # A5b 桥的「其他 / 抵销」项（All Other + 分部间抵销，H1'26 年化税后每股）；A21 10-Q 2026-06-27
    'sbc_acq_eps': 0.535,  # A5b 桥的 non-GAAP 加回项：SBC $687M + 收购相关 $117M /季 × 4 × (1−0.12) ÷ 5.29e9（原始股本口径；按 5.31e9 重算为 0.533，差 0.002/股 < 0.01，为保持全表口径沿用 0.535）（调整后 EPS 不扣它们，`corp_other_eps` 扣了，故桥里加回）；A21 10-Q 2026-06-27
    'cons_rev_fy28_m': 85200000000.0,  # FY2028 合并营收共识均值（WallStreetZen 页面内嵌数据，36 家，区间 71.8–103.9B；Fintel 同值同家数，是同一上游、不算独立）；**均值已有第二源印证**：MarketScreener 2026-10-05 FY2028 营收 $82.53B（差 3%，无家数无区间；其 FY2026 / FY2027 与 yfinance 完全相同，供应商同 yfinance）；只用于反解 FY2028 代工亏损（过渡年点估计，不作分子），A21 2026-10-03
    'cons_rev_fy28_h': 103900000000.0,  # FY2028 合并营收共识上沿（同上）；只进「FY2028 作分子」的升级读数（未采用，A21） 2026-10-03
    'cons_eps_fy28_m': 3.31,  # FY2028 合并调整后 EPS 共识均值（WallStreetZen，37 家，区间 1.94–6.00；Fintel 同源）；**未获独立印证**（2026-10-05 核：MarketScreener 2.03 疑为 GAAP 口径、Nasdaq / Zacks 1 家 2.05；单家美银 2.92（2026-08）、瑞银 2.82（2026-07-27）都低于 3.31——若取 2.9 左右，FY2028 反解亏损 +0.39/股，L / M 底牌约 −0.35）；经 A5b 的桥反解 FY2028 代工亏损，A21 2026-10-03
    'be_year_m': 2028.0,  # M 档代工盈亏平衡年：CFO「可能滑到 2028 年底」+ FY2027 共识反解的亏损未见收窄（用户裁决 2026-10-04，与 L 同口径）；FY2028 亏损由 FY2028 共识反解；A21 2026-10-04
    'be_year_h': 2028.0,  # H 档代工盈亏平衡年：**2026-10-30 由 2027 改 2028**——Q3 电话会未重申「2027 年底盈亏平衡」（管理层只说「还有大量工作」），且 14A 2028 年才量产、2027 年自由现金流预计为负；按 A21 的保守读法 H 与 L / M 同计到 2028 年底。原依据：CFO「推动代工在 2027 年底盈亏平衡」（Deutsche Bank 科技会议 2026-08-26）；A21 2026-10-30
    'be_year_l': 2028.0,  # L 档代工盈亏平衡年：同一场合 CFO 说「可能滑到 2028 年底」；FY2028 亏损由 FY2028 共识反解（与 M 同值）；A21 2026-08-26
    'foundry_oi_h1': -4526.0,  # H1'26 Intel Foundry 营业利润 $M（Q1 −2,437 + Q2 −2,089）；只作快照对照 A21 的共识反解 10-Q 2026-06-27
    'foundry_oi_q2': -2089.0,  # Q2'26 Intel Foundry 营业利润 $M；管理层直线到盈亏平衡路径的敏感性起点；A21 10-Q 2026-06-27
    'foundry_rev_h1': 11186.0,  # H1'26 Intel Foundry 收入 $M（Q1 5,421 + Q2 5,765，含内部）；内部 = 11,186 − 467 = 10,719，÷ 同期产品收入 27,918 = 38.4% → 期权内部收入路径的比率（A6）；**Q3 单季内部 = 6,697 − 411 = 6,286 ÷ 15,415 = 40.8%**（比 H1 高 2.4pp，可能是转移定价或 mix，10-Q 出前不改比率，A9） 10-Q 2026-06-27（Longbridge 分部表）
    'foundry_ext_h1': 467.0,  # H1'26 外部代工收入 $M（Q1 174 + Q2 293，含 Altera 晶圆供应）；× 2 = $0.93B/年 = 产品腿重叠扣减的起点（产品腿 FY2027 共识里外部代工高出今天的部分，A6） 10-Q 2026-03-28 / 2026-06-27
    'foundry_ext_q2': 293.0,  # Q2'26 外部代工收入 $M；× 4 = $1.17B/年，只作快照（A6） 10-Q 2026-06-27
    'ext_rev_l_2027': 1100000000.0,  # 外部代工收入低路径 2027：广发证券（Jeff Pu）EMIB 封装 $1.1B——该年最低家；**只含封装**（无晶圆），低路径偏低、保守方向；二手转述（GuruFocus / BlockBeats 2026-08-14），原报告未见。2026-10-05 起取代美银 2026-01-26 的 $2B（该报告已被同一分析师 2026-06-11、2026-08 两份报告取代，作废）（A6） 2026-08-14
    'ext_rev_l_2028': 7000000000.0,  # 低路径 2028：广发证券 EMIB 封装 $7B（同上，只含封装）；取代美银 2026-01-26 的 $4B（作废） 2026-08-14
    'ext_rev_l_2030': 21000000000.0,  # 低路径 2030：高盛外部晶圆 $11B + 先进封装 $10B——该年最低家（高盛 2026-06-26 首次覆盖，7 月财报后维持中性、未见新数）；KeyBanc（2026-07-14）同年晶圆 $10.6B + EMIB-T 封装 > $22B = > $32.6B，居中，不进低 / 高（A6） Wisburg 93757（2026-06-26）
    'ext_rev_h_2027': 4600000000.0,  # 高路径 2027：花旗外部代工（外部晶圆 + EMIB 封装）$4.6B——该年最高家；花旗 2026-07-25 / 09-17 两份更新维持买入、目标价 130，未见新路径数；A6 Wisburg 96063（2026-07-15）
    'ext_rev_h_2028': 10000000000.0,  # 高路径 2028：花旗 $10B（同上） Wisburg 96063（2026-07-15）
    'ext_rev_h_2030': 40000000000.0,  # 高路径 2030：美银（Vivek Arya）最新报告「代工收入从 2026 年约 $1.1B 升到 2030 年近 $40B」——2026-08 增发后（目标价 160 → 145，Yahoo / moomoo 2026-08-13 转述）；拆分：晶圆代工市场约 $380B 的 8–10%（$30–38B）+ 2.5D / 3D 先进封装约 $20B 市场的 25–30%（$5–6B），合计与「近 $40B」相符 → 读作含封装的外部总额。取代其 2026-06-11 双级上调报告的 $47.1B（中间年两份都未见）。该年最高家（A6） 2026-08-13
    'ext_pkg_h_2030': 5500000000.0,  # 高路径 2030 里的先进封装段 = 美银「约 $20B 先进封装市场的 25–30%」取中 $5.5B（**推断**：由份额区间折算，原报告未给金额）；用途：封装只计一次的核对、H 方法 (b) 从路径里剔除封装后求所需晶圆产能、H 方法 (a) 的外部封装（A6 / A6b）。2026-10-05 由高盛 $10B 改（高路径 2030 由高盛换成美银） 2026-08-13
    'opt_rev_pkg': 2000000000.0,  # 现任 CFO 具名的先进封装量：1 家已公开采用 EMIB-T 的客户（联发科，A13）×「每客户每年数十亿美元」取下限 $2B；2026-10-04 起**不再单列期权**，eval 只核它 ≤ 低路径 2029 年外部收入（已含在路径内，A6） Deutsche Bank 科技会议 2026-08-26
    'opt_opm': 0.3,  # CFO 对先进封装具名的营业利润率 30%（40% 毛利）；只作封装部分按 30% 计的敏感性（A6） Deutsche Bank 科技会议 2026-08-26；TrendForce 2026-08-31
    'ppe_net': 105314000000.0,  # 代工自身经营资本代理 = 公司 PP&E 净值 $105,314M（8-K 2026-09-26；Intel 不披露分部资产；PP&E 绝大部分是晶圆厂与封装厂）；期权 ROE 的分母（A22） 2026-09-26
    'ss_year': 2030.0,  # 代工稳态年 = 对齐年份（外部收入有 ≥2 家点估计的最远年：高盛、KeyBanc、美银；`_AXIS.leading-edge-foundry` `t_align`）；盈亏平衡后线性爬到该年（线性为拍值），在该年按 Gordon 估值、折回 FY2027（A6 / A11） 2026-10-04
    'pkg_capex_budget': 2938000000.0,  # 期权扣未投资本：唯一具名的产能预算 = 槟城先进封装厂资本承诺 RM12B ÷ 4.0845（USDMYR 2026-10-04）；已建成产能（含新墨西哥 Fab 9）是沉没成本，不扣；14A / 俄亥俄无具名预算，不扣（A6） crnasia / techpowerup 2026；yfinance 2026-10-04
    'pkg_capex_done': 0.99,  # 槟城厂已完成比例（「99% complete」，2026 下半年首期投产）；剩余 1% 在 2026 年投入、早于分子年，不折现（A6） crnasia 2026
    'wspm_f52': 40000.0,  # H 产能：亚利桑那 Fab 52（18A）每月投片 = 「每周 1 万片以上 18A」× 4（公司具名：CTO Chandrasekaran 对 CNBC 2025-12；Tom's Hardware 2026-06-17 称其为具名产能、非当前产出）；定价对标台积电 N3（A6b） 2025-12
    'wspm_f62': 4800.0,  # H 产能：亚利桑那 Fab 62 每月投片 = 合资预算 `az_budget` ÷ `capex_per_wspm` − Fab 52 = 44,800 − 40,000（eval 校验；与俄亥俄同一条「预算 ÷ 建厂成本率」规则）。2026-10-05 核验改：原按孪生厂房 4 万计，但合资两座厂的全部预算 $28B 按 Intel 自己的成本率只够约 4.5 万片，独立分析者本人的读数也是 Fab 52 + 62 **合计** 4 万片（其 Fab 42 的 1.43 万片即按「68.5 万平方英尺 = 4 万片」折算）；Fab 62 装满 4 万片需在合资预算外再投约 $22B（无具名预算，只作敏感性）；公司未指定节点，按 18A 定价；约 2028 年就绪（`az_done`）（A6b） 10-K FY2025；alexintel 2026-01-20
    'wspm_ie_now': 40000.0,  # H 产能：爱尔兰 Fab 34（Intel 4 / 3）当前每月投片，**推断**（独立分析者按 Intel 2024 年产能柱状图反推，非公司披露）；定价对标台积电 N5（A6b） alexintel 2026-01-20
    'wspm_ie_full': 65000.0,  # H 产能：爱尔兰 €5B（$5.7B）Intel 3 扩产计划完成后的每月投片，**推断**（同上柱状图的上限读数）；计划 2027 年底基本部署完（`ie_done`），2028 年起计（A6b） alexintel 2026-01-20；Tom's Hardware 2026-07-15
    'wspm_i7': 67000.0,  # H 产能：Intel 7（10nm 级）每月投片 = 以色列 Fab 28 约 4 万 + 亚利桑那非 EUV 厂约 2.7 万，**推断**（独立分析者，2025 年初读数）；定价对标台积电 N7；H 世界不转产、照满载计（A6b） alexintel 2026-01-20
    'wspm_legacy': 16000.0,  # H 产能：Intel 14nm / 22nm / Intel 16 等旧节点（爱尔兰非 EUV 厂）每月投片，**推断**（同上）；定价对标台积电 N16 / N12（A6b） alexintel 2026-01-20
    'capex_per_wspm': 625000.0,  # Intel 自身的建厂资本强度：每 1 万片/周（4 万片/月）低 NA EUV 产能约 $25B → $625,000 / 每月片；用于把俄亥俄 $28B 预算（44,800 片/月，两座厂各一半，14A，对标台积电 N2）与亚利桑那合资 $28B 预算（44,800 片/月，含 Fab 52 的 4 万）换算成产能；**原图据独立分析者称是 Intel 2024 年信息图（他读作 Fab 52 + 62 两座厂合计 $25B / 4 万片），2026-10-05 再查未找到原件（Intel 全球制造新闻页已下线），待核**（A6b） alexintel 2026-01-20
    'ohio_mod1_ops': 2031.0,  # 俄亥俄第一座厂投产年（公司 2025-02 时间表「2030 建成、2030–31 投产」取后者）；第二座 2032 投产（`ss_year_h`）；各计一半产能（A6b） Intel newsroom 2025-02-28
    'ie_budget': 5700000000.0,  # 爱尔兰 Leixlip Intel 3 扩产计划 €5B ≈ $5.7B（2026-07-13 公告，升级现有厂房、不建新厂，自有资金）；**按 2Q26 时点全额未投计**（公告称工作「年初已开始」，已投部分未披露，偏多扣方向）；扣减并进 H 的 ROE 分母（A6b） Tom's Hardware 2026-07-15 / Reuters
    'ie_done': 2027.0,  # 爱尔兰计划「2027 年底基本部署完」；未投资本按 2026–2027 平摊，`wspm_ie_full` 自 2028 年起计（A6b） Tom's Hardware 2026-07-15
    'px_n3': 20000.0,  # 台积电 N3 晶圆价 $/片（对标 18A）：约 $20,000（Digitimes 2022-11-21 首报、约比 N5 高 25%；TrendForce 2025-10-08 同值）；siliconanalysts 2026 汇总点估计 $20,000（区间 18,000–27,000）；TechNode 2025-10-09 称 2025 年 3nm 均价 $25,000–27,000、N3P 2025 年再涨约 20%（TrendForce 2025-09-23）——取 $20,000 偏保守（A6b） 2026-10-05 核
    'px_n2': 30000.0,  # 台积电 N2 晶圆价 $/片（对标 14A）：约 $30,000（Tom's Hardware 2024-10 报道、TechNode 2025-10-09 称「定价落在 $30,000」、TrendForce 2025-09-23）（A6b） 2026-10-05 核
    'px_n5': 18500.0,  # 台积电 N5 / N4 晶圆价 $/片（对标 Intel 4 / 3）：siliconanalysts 2026 汇总均值 $18,500（区间 16,000–21,300）；早期读数 CSET 2020-09 $16,988、Digitimes 2022-11 约 $16,000；工商时报 2025-11 称 5nm 及以下 2026 年起每年涨 3–5%（A6b） 2026-10-05 核
    'px_n7': 9500.0,  # 台积电 N7 晶圆价 $/片（对标 Intel 7）：$9,500（siliconanalysts 2026 汇总，区间 8,100–10,900；CSET 2020-09 $9,346）；交叉：同一页 Intel 7 定位价 $6,500（A6b） 2026-10-05 核
    'px_n16': 4500.0,  # 台积电 N16 / N12 晶圆价 $/片（对标 Intel 14nm / 22nm / 16）：$4,500（siliconanalysts 2026 汇总，区间 3,800–5,200；CSET 2020-09 $3,984）；2026-10-05 核验由 $5,500 改——原值高于公开区间上沿（A6b） 2026-10-05 核
    'pkg_share_tsm': 0.1,  # 自有晶圆的封装测试收入占代工总收入的比例 = 台积电先进封装占营收约 10%（2025 年，CFO 财报会）；H 世界按此加回自有晶圆的封测收入（A6b） 台积电 Q4'25 电话会
    'az_budget': 28000000000.0,  # 亚利桑那 SCIP（Fab 52 / 62，与 Brookfield 51/49 合资）项目总成本 = FY2025 末已入账 PP&E $17.8B（在建 5.6 + 已转固 12.2）+ Intel 剩余未出资 $5.2B ÷ 51% = **$28.0B**（10-K FY2025 承诺附注；2022 年 8-K 原始为 Intel 约 $14.8B + Brookfield 约 $14.2B = $29.0B，新闻稿「最多 $30B」）（A6b） 10-K FY2025
    'az_spent_q2': 19800000000.0,  # 亚利桑那 SCIP 已入账 PP&E（2Q26 末）：在建 6.0 + 已转固 13.8 $B → 未投 $8.2B（含 Brookfield 将出的 49%，等价于其新增的资本索取权按账面计，A10），作扣减的未投资本并进 H 的 ROE 分母（与 `ppe_net` 同一时点）；2026-10-05 核验改：原「Intel 剩余出资 $5.2B ÷ 51% = $10.2B」是 FY2025 末的数，与 2Q26 已投额混了时点（A6b） 10-Q 2Q26 VIE 附注
    'az_done': 2028.0,  # 亚利桑那 Fab 62 预计投产年（Fab 52 2025-10 已量产 18A）；未投资本按 2026–2028 平摊投入（A6b） Tom's Hardware / TrendForce 2026
    'ohio_budget': 28000000000.0,  # 俄亥俄 Ohio One 两座先进晶圆厂总投资 $28B（2025-02 公司公告的预算口径）（A6b） Intel newsroom 2025-02-28；DCD
    'ohio_spent': 5260000000.0,  # 俄亥俄累计资本支出（截至 2025 年末；2025 年投入 $1.53B），公司向俄亥俄发展署的年报（A6b） WHIO / Yahoo 2026-02
    'ohio_done': 2031.0,  # 俄亥俄第二座厂建成年（第一座 2030 建成、2030–31 投产，第二座 2031 建成、2032 投产）；未投资本按 2026–2031 平摊（A6b） Intel newsroom 2025-02-28
    'ss_year_h': 2032.0,  # H 档满产兑现年 = 俄亥俄第二座厂投产年；H 档收入逐年跟随在用产能，利润率从平衡年（2027 年底）线性爬到此年的 30%（A6b） Intel newsroom 2025-02-28
    'tsm_rev_2025': 122930000000.0,  # 交叉用：台积电 FY2025 营收 USD（Longbridge 年报）；只算「营收 ÷ PP&E 净值」作对照，不进量（A6b） 2026-10-04
    'tsm_ppe_net_2025': 119450000000.0,  # 交叉用：台积电 FY2025 末 PP&E 净值 USD（A6b） 2026-10-04
    'tsm_ppe_net_2024': 99960000000.0,  # 交叉用：台积电 FY2024 末 PP&E 净值 USD（A6b） 2026-10-04
    't_num': 2027.0,  # 分子年（M / H 分子 = FY2027，A11）；期权折回到该年；代工亏损从该年计起（A21） 2026-10-03
    'tau': 0.26575,  # 时点对齐年数 = 估值基准日 2026-09-26（8-K 资产负债表日）→ 分子年 FY2027 年初 2027-01-01，97 天 ÷ 365；M / H 的 CPU 腿价值与资本化闭合项、三档代工过渡亏损、期权按 `r_perp` 折 τ，M / H 另加 Q4'26 窗口可分配利润（折 τ/2）；A24 2026-10-30
    'y1': 2027.0,  # CPU 腿高回报期止点 Y1 = 可见年末 FY2027（默认路径，不挂需求轴；叙事换代下本票三档不回落，只对 g2 配对里前瞻高于 30% 的同业起作用；A24） 2026-10-16
    'y2': 2031.0,  # CPU 腿稳态起点 Y2 = Y1 + 4（进入门槛「中」，不确定：x86 授权与自有晶圆厂使单位产能投资高、新厂 3–5 年，但 Arm 阵营抢份额的历史速度快，服务器 / PC 客户认证约 1–2 年；A24） 2026-10-16
    'rs_cpu': 0.3,  # CPU 腿稳态回报 = 叙事换代的腿：min(该档前瞻, 30%)，eval 每档封在该档前瞻 → 三档 = 前瞻 12.8 / 21.6 / 27.4%、不回落。判据：① 自身周期因商业模式变化不可用（内部代工模型重述后同公式只有 3 年，之前是一体化 IDM 口径）；② CPU 没有 ≥ 5 年读数的同一门生意成熟同业；A24 2026-10-18
    'eps_fy26_cons': 1.544,  # FY2026 公司调整后 EPS 共识（yfinance 0y avg，41 家，区间 1.12–1.89）；减 9M26 实际与 Q4 的 SBC / 收购加回得 Q4'26 未入账利润 = 窗口可分配利润的基数（A24）。**共识待更新** 2026-10-30
    'eps_9m26': 1.23,  # 9M26 公司调整后 EPS 实际（Q1 0.29 + Q2 0.42 + Q3 0.52）；估值基准日 2026-09-26 起只剩 Q4'26 未入账，A24 窗口 2026-10-29
    'escrow_shares': 143000000.0,  # 尚在托管、待随安全飞地拨款释放给美国政府的股份（7,100 万非或有 + 7,100 万或有）；`shares_diluted` 不含，计一次（A10d） 10-Q 2026-06-27
    'escrow_price': 20.0,  # 托管股每股对应的政府拨款现金 $20（按「新股 × $20 入现金」计，不再扣 $15.6B 衍生负债，`net_cash_ps` 本就没扣，A10d） 10-Q 2026-06-27
    'warrant_shares': 240516150.0,  # 代工 51% 认股权证股数（@ $20，Intel 持有代工 < 51% 才可行权，约 2030-08 到期；公司称「既不可行权也不预期可行权」）——只披露，不进底牌（A10d） 10-Q 2026-06-27
    'net_cash_ps': 0.73,  # 闭合项：净现金/股 = 净现金 $3.871B ÷ 5.31e9（8-K 2026-09-26：现金与短投 54.005B，净债务 −3.871B，Longbridge 同值）；正=净现金 2026-09-26
    'nci_ps': -2.75,  # 闭合项：−少数股东权益（不含 Mobileye）≈ $14.59B ÷ 5.31e9 = −2.75；总少数股东权益 16,642（8-K 2026-09-26）减 Mobileye 约 2,050（沿用 2Q26 账面读数，10-Q 未出，**待核**）；Mobileye 少数股东不在此扣、由 `mbly_stake_ps` 表达（A10） 2026-09-26
    'mbly_stake_ps': 0.75,  # 闭合项：Mobileye 77% × Mobileye 市值 5.156B（他股市价，yfinance 2026-10-30）/ 5.31e9；持股比例已核：10-Q 2Q26 Note 3 少数股东 23%（A10） 2026-10-30
    'altera_stake_ps': 0.79,  # 闭合项：Altera 48% × Silver Lake 作价 8.75B（2025-04 公告的 100% 估值）/ 5.31e9；已核：10-K FY2025 Note「our ownership interest was 48%」，账面 $3.2B（权益法）（A10） 2025-04 公告；10-K FY2025
    'corp_other_eps': -0.826,  # 闭合项：经常性公司未分摊**年化税后每股成本** = (SBC 687 + 收购相关 117 + 其他 442 = $1,246M/季) × 4 × (1−0.12) ÷ 5.31e9；剔除一次性重组 $170M；Q3 未分摊费用 $1.06B 低于该经常性口径，明细待 10-Q（**待核**）；由 eval × M 档生成倍数资本化（A10b） 2026-10-30
    'tax_asset_ps': 1.66,  # 闭合项：AMIC 税务应收 $7.5B（流动）+ $1.3B（非流动）= $8.8B ÷ 5.31e9 = 1.657；valuation allowance 下的 NOL 递延税资产未计，方向偏正（A10c） 2026-06-27
}

def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the steady-state-return path (valuation-rules「经营价值与超额现金」②
    稳态回报三段; gordon.py's three-segment function is not built yet, so it lives here).

    Calendar years, t = 1 is the numerator year t0; the retention of year c earns from c+1.
    RONIC = the tier's forward value through Y1, falls linearly to the steady value R_s by Y2,
    and stays there (R_s capped at the tier's forward value).  With R_s >= forward this is
    exactly perpetual_pe(g, roe, r)."""
    rs_eff = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs_eff
        return roe + (rs_eff - roe) * (cal - y1) / (y2 - y1)

    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g / rs_eff) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g / ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1



def calculate(context):
    ax = context['axes']['advanced']
    inp = {**INPUTS, 'g2_foundry': ax['g2_foundry_src'], 'g2_foundry_h': ax['g2_foundry_h_src'],
           'foundry_opm_l': ax['opm_weak_peer'], 'foundry_opm_h': ax['opm_strong_peer'] - ax['yield_discount']}
    if any(not math.isfinite(value) for value in inp.values()):
        raise ValueError('inputs must be finite')
    if inp['shares_diluted'] <= 0 or inp['equity'] <= 0 or inp['r_perp'] <= inp['g2_cpu']:
        raise ValueError('invalid base denominator or discount rate')
    baskets = {'r_perp': 4}
    errors = []
    r, g2 = inp["r_perp"], inp["g2_cpu"]
    sh, eq, keep = inp["shares_diluted"], inp["equity"], 1.0 - inp["tax_rate"]
    esc_sh, esc_px = inp["escrow_shares"], inp["escrow_price"]
    sh_post = sh + esc_sh

    def esc(v: float) -> float:
        """Per-share value on 5.29e9 shares -> per share after the escrow shares come in at $20."""
        return (v * sh + esc_sh * esc_px) / sh_post

    # ---- Guards on the growth 口径 (AGENTS.md 永续增长口径) ----
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2_cpu")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"r - g2_cpu = {r - g2:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # ---- Step 0: leg economics by public-data inference (A5c) ----
    q_margin = {q: inp[f"prod_oi_{q}"] / inp[f"prod_rev_{q}"] for q in QTRS}
    q_share = {q: inp[f"prod_rev_{q}"] / inp[f"cons_rev_{q}"] for q in QTRS}
    if max(q_share.values()) - min(q_share.values()) > 0.01:
        errors.append(f"product share not constant across {QTRS}: {q_share} — inference assumption fails (A5c)")
    if max(q_margin.values()) - min(q_margin.values()) > 0.05:
        errors.append(f"product margin regime break across {QTRS}: {q_margin} — back to the conversation (A5c)")
    p_rev_h1 = sum(inp[f"prod_rev_{q}"] for q in QTRS)
    margin = sum(inp[f"prod_oi_{q}"] for q in QTRS) / p_rev_h1
    share = p_rev_h1 / sum(inp[f"cons_rev_{q}"] for q in QTRS)
    bridge = inp["bridge_other_eps"] + inp["corp_other_eps"] + inp["sbc_acq_eps"]
    t0 = inp["t_num"]
    be = {"L": inp["be_year_l"], "M": inp["be_year_m"], "H": inp["be_year_h"]}

    def prod_eps(rev: float, m_: float = margin, s_: float = share) -> float:
        return rev * s_ * m_ * keep / sh

    tau, y1, y2, rs = inp["tau"], int(inp["y1"]), int(inp["y2"]), inp["rs_cpu"]
    # FY26H2 unbooked company adjusted EPS less the half-year SBC / acquisition add-back (the
    # closure capitalises them): the window distributable profit base (A24).
    unbooked = inp["eps_fy26_cons"] - inp["eps_9m26"] - inp["sbc_acq_eps"] / 4

    def compute(m_: float = margin, s_: float = share, g_: float = g2, r_: float = r,
                l28: float | None = None, be_: dict | None = None, fy28_num: bool = False,
                eq_: float = eq, l27: float | None = None, rs_: float = rs) -> dict:
        """Base band on the escrow-adjusted share count; consensus EPS fixed, so a
        different product EPS implies a different foundry loss (A21).
        A24 (2026-10-16): CPU multiples on the steady-state-return path; the M / H CPU value and
        the capitalised corporate closure are folded back tau years from the start of FY2027 and
        get the FY26H2 window profit x (1 - b1) at tau/2; L's numerator is the realised FY2025
        digestion year (a world-state numerator, not calendar-bound) -> no tau, no window; the
        foundry transition losses (valued at the start of FY2027) are folded by tau in every tier."""
        be_ = be if be_ is None else be_
        rev = ({"M": inp["cons_rev_fy28_m"], "H": inp["cons_rev_fy28_h"]} if fy28_num
               else {"M": inp["rev_fy27_m"], "H": inp["rev_fy27_h"]})
        e = {"L": inp["oi_products_l"] * MM * keep / sh, "M": prod_eps(rev["M"], m_, s_), "H": prod_eps(rev["H"], m_, s_)}
        roe_ = {t: e[t] * sh / eq_ for t in TIERS}
        pe_ = {t: path_pe(g_, roe_[t], r_, int(t0), y1, y2, rs_) for t in TIERS}
        d_ = {t: (1.0 if t == "L" else (1 + r_) ** -tau) for t in TIERS}
        df_num = {t: ((1 + r_) ** -1 if fy28_num and t != "L" else 1.0) for t in TIERS}  # construction §3: FY+2 discounted
        cpu_ = {t: e[t] * pe_[t] * df_num[t] * d_[t] for t in TIERS}
        adj_ = {t: sum(inp[k] for k in ADJ_PS) + inp["corp_other_eps"] * pe_["M"] * d_[t] for t in TIERS}
        l27_ = (prod_eps(inp["rev_fy27_m"], m_, s_) + bridge - inp["cons_eps_fy27_m"]) if l27 is None else l27
        l28_ = (prod_eps(inp["cons_rev_fy28_m"], m_, s_) + bridge - inp["cons_eps_fy28_m"]) if l28 is None else l28
        loss = {2027: l27_, 2028: l28_}
        f_ = {t: -sum(loss.get(y, l28_) * (1 + r_) ** -(y - t0) for y in range(int(t0), int(be_[t]) + 1))
              * (1 + r_) ** -tau for t in TIERS}
        win_ = {t: (0.0 if t == "L" else max(unbooked * (1 - g_ / roe_[t]), 0.0) * (1 + r_) ** -(tau / 2)) for t in TIERS}
        pre = {t: cpu_[t] + adj_[t] + f_[t] + win_[t] for t in TIERS}
        return dict(eps=e, roe=roe_, pe=pe_, d=d_, cpu=cpu_, adj=adj_, l27=l27_, l28=l28_, F=f_, win=win_, pre=pre,
                    base={t: esc(pre[t]) for t in TIERS})

    if not int(inp["t_num"]) <= y1 < y2:
        errors.append("need t_num <= y1 < y2 (A24)")
    if not r <= rs:
        errors.append("rs_cpu must not fall below r (A24)")
    if rs > NARRATIVE_CAP + 1e-12:
        errors.append(f"rs_cpu {rs:g} above the narrative-change cap {NARRATIVE_CAP:g} (A24)")
    c = compute()
    eps, roe, pe, cpu, adj, fdy = c["eps"], c["roe"], c["pe"], c["cpu"], c["adj"], c["F"]
    dfac, win = c["d"], c["win"]
    pe_today = {t: pe[t] * dfac[t] for t in TIERS}  # today's operating multiple of the CPU leg (A24)
    loss27, loss28 = c["l27"], c["l28"]
    base = c["base"]
    L, M, H = (base[t] for t in TIERS)
    A, B_ = cut_points(L, M, H)
    oi = {t: eps[t] * sh / keep / MM for t in TIERS}
    errors += ladder("oi_products", oi["L"], oi["M"], oi["H"])
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe_today[t] <= inp["pe_own_max"]):
            errors.append(f"{t} today's operating PE {pe_today[t]:.2f}x outside own realised band "
                          f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] — 回对话，不拧 g")
    if loss27 <= 0:
        errors.append(f"consensus implies no FY2027 foundry loss ({loss27:.3f}) — recheck A21 bridge")
    if loss28 <= 0:
        errors.append(f"FY2028 consensus implies a foundry profit ({loss28:.3f}) — breakeven moved earlier, back to the conversation (A21)")
    if not all(be[t] >= t0 for t in TIERS) or not be["L"] >= be["M"] >= be["H"]:
        errors.append(f"breakeven years {be} must be >= t_num {t0} and L >= M >= H (A21)")


    if not all(math.isfinite(v) for v in (L, M, H)) or not L < M < H:
        raise ValueError('base anchors must be finite and ordered')
    warnings = ['historical_forecast_and_foundry_financing_unverified']
    if errors:
        warnings.append('historical_base_guards_require_review')

    def calculate_option():
        errors = []
        # ---- Foundry option above breakeven (A6 / A22) ----
        g2f, g2fh = inp["g2_foundry"], inp["g2_foundry_h"]
        errors += check_g_cap(g2f, r, "g2_foundry")
        errors += check_g_cap(g2fh, r, "g2_foundry_h")
        ss = int(inp["ss_year"])
        ext = {s.upper(): {y: inp[f"ext_rev_{s}_{y}"] for y in EXT_YEARS} for s in ("l", "h")}
        for s in ("L", "H"):  # gap year: geometric interpolation (marked in A6)
            ext[s][2029] = (ext[s][2028] * ext[s][2030]) ** 0.5
        ext["M"] = {y: (ext["L"][y] + ext["H"][y]) / 2 for y in ext["L"]}
        for y in sorted(ext["L"]):
            if not ext["L"][y] <= ext["M"][y] <= ext["H"][y]:
                errors.append(f"external path {y}: low {ext['L'][y]:.3g} <= mid <= high {ext['H'][y]:.3g} violated")
        # Packaging exactly once: the CFO-named packaging quantity must already sit inside every path.
        pkg_named = inp["opt_rev_pkg"]
        if not pkg_named <= ext["L"][2029]:
            errors.append(f"named packaging {pkg_named / B:.1f}B above the low path in 2029 ({ext['L'][2029] / B:.2f}B) — add the excess, A6")
        if not inp["ext_pkg_h_2030"] <= ext["H"][2030]:
            errors.append("high-path packaging exceeds the high path total — recheck A6")
        int_ratio = ((inp["foundry_rev_h1"] - inp["foundry_ext_h1"])
                     / (inp["prod_rev_q1"] + inp["prod_rev_q2"]))  # H1 ratio; Q3 jump disclosed in A6/A9
        prod_rev = {"L": inp["prod_rev_fy25"] * MM, "M": inp["rev_fy27_m"] * share, "H": inp["rev_fy27_h"] * share}

        # Leg ruler from _AXIS.leading-edge-foundry
        opm = {"L": inp["foundry_opm_l"], "H": inp["foundry_opm_h"]}
        opm["M"] = (opm["L"] + opm["H"]) / 2
        ax = context['axes']['advanced']
        opm_strong = ax['opm_strong_peer']
        if abs(context['axes']['foundry']['g2_rest_src'] - g2f) > 1e-9:
            errors.append('historical foundry peer reading differs')

        def option(t: str, m_: float | None = None, path: dict | None = None, be_t: float | None = None,
                   r_: float = r, capital: float | None = inp["ppe_net"], internal: bool = True,
                   retain: bool = False) -> dict:
            """PV (total $) at FY2027 of foundry profit above breakeven for tier t.
            capital=None -> company-equity ROE (old convention, sensitivity only)."""
            m_ = opm[t] if m_ is None else m_
            path = ext[t] if path is None else path
            b_ = int(be[t] if be_t is None else be_t)
            ni = {}
            for y in range(b_ + 1, ss + 1):
                frev = (prod_rev[t] * int_ratio * (1 + g2) ** (y - t0) if internal else 0.0) + path[y]
                ni[y] = frev * m_ * (y - b_) / (ss - b_) * keep
            ni_ss = ni[ss]
            roe_ = ni_ss / capital if capital is not None else (eps[t] * sh + ni_ss) / eq
            pe_ = perpetual_pe(g2f, roe_, r_) if roe_ > r_ else 1 / r_
            pv = sum(ni[y] * (1 + r_) ** -(y - t0) for y in ni if y < ss) + ni_ss * pe_ * (1 + r_) ** -(ss - t0)
            if retain and roe_ > 0:  # sensitivity: ramp growth paid from retained capital the year before
                pv -= sum((ni[y] - ni.get(y - 1, 0.0)) / roe_ * (1 + r_) ** -(y - 1 - t0) for y in ni)
            return dict(ni=ni, roe=roe_, pe=pe_, pv=pv)

        # ---- H quantity = full-capacity revenue = wafer capacity x market wafer price (A6b, 2026-10-05) ----
        az_left_q2 = inp["az_budget"] - inp["az_spent_q2"]
        ohio_left = inp["ohio_budget"] - inp["ohio_spent"]
        ie_left = inp["ie_budget"]  # announced 2026-07-13, treated as wholly unspent at the 2Q26 point (A6b)
        if min(az_left_q2, ohio_left) < 0:
            errors.append("named project spent above budget — recheck A6b")
        ss_h = int(inp["ss_year_h"])
        if ss_h < ss:
            errors.append(f"ss_year_h {ss_h} before ss_year {ss} — H full capacity realised before the aligned year?")
        if not inp["ohio_mod1_ops"] <= ss_h:
            errors.append("Ohio Mod 1 operations after the H full-capacity year — recheck A6b")
        wspm_ohio = inp["ohio_budget"] / inp["capex_per_wspm"]  # both Ohio mods, Intel's own capital intensity
        # Arizona JV (Fab 52 + 62): same budget-to-capacity rule as Ohio; Fab 52's named 40k sits inside it (A6b).
        wspm_az = inp["az_budget"] / inp["capex_per_wspm"]
        if abs(inp["wspm_f52"] + inp["wspm_f62"] - wspm_az) > 0.01 * wspm_az:
            errors.append(f"Fab 52 + Fab 62 {inp['wspm_f52'] + inp['wspm_f62']:,.0f} WSPM != Arizona budget / capex per WSPM "
                          f"{wspm_az:,.0f} (A6b)")

        def price_disc(m_: float) -> float:
            """Price discount to TSMC that, at TSMC's cost per wafer, lands on margin m_ (A6b)."""
            return 1 - (1 - opm_strong) / (1 - m_)

        def capacity(y: int, ohio_w: float = wspm_ohio, f62: float | None = None, with_ohio: bool = True) -> dict:
            """Wafer starts per month in service in year y, by node group (H world: full utilisation)."""
            f62 = inp["wspm_f62"] if f62 is None else f62
            oh = (ohio_w / 2 if y >= inp["ohio_mod1_ops"] else 0.0) + (ohio_w / 2 if y >= ss_h else 0.0)
            return {"18A": inp["wspm_f52"] + (f62 if y >= inp["az_done"] else 0.0),
                    "14A": oh if with_ohio else 0.0,
                    "I3": inp["wspm_ie_full"] if y > inp["ie_done"] else inp["wspm_ie_now"],
                    "I7": inp["wspm_i7"], "LEG": inp["wspm_legacy"]}

        def rev_cap(y: int, m_: float | None = None, own_pkg: bool = True, **kw) -> dict:
            """Full-capacity foundry revenue in year y: wafers + own-wafer packaging/test + external packaging."""
            d_ = price_disc(opm["H"] if m_ is None else m_)
            c_ = capacity(y, **kw)
            by = {k: c_[k] * 12 * inp[PX[k]] * (1 - d_) for k in c_}
            wafer = sum(by.values())
            pkg_own = wafer * inp["pkg_share_tsm"] / (1 - inp["pkg_share_tsm"]) if own_pkg else 0.0
            # External packaging rides the high path's shape up to Goldman's 2030 $10B; none before the path starts.
            pkg_ext = 0.0 if y < min(ext["H"]) else inp["ext_pkg_h_2030"] * min(1.0, ext["H"].get(y, ext["H"][2030]) / ext["H"][2030])
            return dict(by=by, wafer=wafer, pkg_own=pkg_own, pkg_ext=pkg_ext, total=wafer + pkg_own + pkg_ext,
                        wspm=sum(c_.values()), disc=d_)

        rev_full = rev_cap(ss_h)["total"]

        def spread_pv(amount: float, done: int, r_: float) -> float:
            """Unspent budget spread evenly from 2026 to the completion year; spend before t_num not discounted."""
            yrs = range(2026, done + 1)
            return sum(amount / len(yrs) * (1 + r_) ** -max(0, y - t0) for y in yrs)

        def option_full(m_: float | None = None, be_t: float | None = None, r_: float = r, with_ohio: bool = True,
                        g_: float | None = None, az_extra: float = 0.0, **kw) -> dict:
            """H tier: revenue follows capacity in service, margin ramps linearly from breakeven to 30% at
            ss_year_h; ROE on operating PP&E + unspent named capital; unspent capital deducted.
            az_extra: sensitivity only -- capital beyond the JV budget to tool a larger Fab 62."""
            m_ = opm["H"] if m_ is None else m_
            b_ = int(be["H"] if be_t is None else be_t)
            g_ = g2fh if g_ is None else g_
            ss_ = ss_h if with_ohio else max(ss, int(inp["az_done"]), int(inp["ie_done"]) + 1)
            rev_ = {y: rev_cap(y, m_=m_, with_ohio=with_ohio, **kw)["total"] for y in range(b_ + 1, ss_ + 1)}
            ni = {y: rev_[y] * m_ * keep * (y - b_) / (ss_ - b_) for y in rev_}
            az_left = az_left_q2 + az_extra
            cap = inp["ppe_net"] + az_left + ie_left + (ohio_left if with_ohio else -inp["ohio_spent"])
            roe_ = ni[ss_] / cap
            pe_ = perpetual_pe(g_, roe_, r_) if roe_ > r_ else 1 / r_
            pv = sum(ni[y] * (1 + r_) ** -(y - t0) for y in ni if y < ss_) + ni[ss_] * pe_ * (1 + r_) ** -(ss_ - t0)
            uns = (spread_pv(az_left, int(inp["az_done"]), r_) + spread_pv(ie_left, int(inp["ie_done"]), r_)
                   + (spread_pv(ohio_left, int(inp["ohio_done"]), r_) if with_ohio else 0.0))
            return dict(ni=ni, roe=roe_, pe=pe_, pv=pv, rev=rev_[ss_], revs=rev_, cap=cap, unspent=uns)

        int_flat = prod_rev["H"] * int_ratio  # H internal held at FY2027: transfer price ~ market wafer price (A6b)

        def option_path_h(m_: float | None = None, be_t: float | None = None, r_: float = r, g_: float | None = None,
                          own_pkg: bool = True, internal_growth: bool = False, **kw) -> dict:
            """H tier when the sell-side high path beats full capacity (method (b), 2026-10-05): revenue = internal
            (flat at FY2027) + external high path, steady at ss_year; the wafers that path needs at the same
            discounted prices beyond all named capacity are new 14A-class capacity at Intel's own capital
            intensity; that capital plus the named unspent budgets is deducted and sits in the ROE denominator.
            Ohio and the unnamed capacity must be in service by ss_year -> their spend spreads 2026..ss_year."""
            m_ = opm["H"] if m_ is None else m_
            b_ = int(be["H"] if be_t is None else be_t)
            g_ = g2fh if g_ is None else g_
            d_ = price_disc(m_)
            rev_ = {y: int_flat * ((1 + g2) ** (y - t0) if internal_growth else 1.0) + ext["H"][y] for y in range(b_ + 1, ss + 1)}
            ni = {y: rev_[y] * m_ * keep * (y - b_) / (ss - b_) for y in rev_}
            az_left = az_left_q2 + kw.pop("az_extra", 0.0)
            named = rev_cap(ss_h, m_=m_, own_pkg=own_pkg, **kw)  # every named fab at full load (incl. Ohio)
            own = (1 - inp["pkg_share_tsm"]) if own_pkg else 1.0
            wafer_need = (rev_[ss] - inp["ext_pkg_h_2030"]) * own
            px_new = 12 * inp["px_n2"] * (1 - d_)
            wspm_new = max(0.0, wafer_need - named["wafer"]) / px_new
            capex_new = wspm_new * inp["capex_per_wspm"]
            oh_left = ohio_left if kw.get("with_ohio", True) else 0.0  # Ohio budget fixed; ohio_w only changes its WSPM
            cap = inp["ppe_net"] + az_left + ie_left + oh_left + capex_new
            roe_ = ni[ss] / cap
            pe_ = perpetual_pe(g_, roe_, r_) if roe_ > r_ else 1 / r_
            pv = sum(ni[y] * (1 + r_) ** -(y - t0) for y in ni if y < ss) + ni[ss] * pe_ * (1 + r_) ** -(ss - t0)
            uns = (spread_pv(az_left, int(inp["az_done"]), r_) + spread_pv(ie_left, int(inp["ie_done"]), r_)
                   + spread_pv(oh_left + capex_new, ss, r_))
            return dict(ni=ni, roe=roe_, pe=pe_, pv=pv, rev=rev_[ss], revs=rev_, cap=cap, unspent=uns,
                        wafer_need=wafer_need, wafer_named=named["wafer"], wspm_new=wspm_new, capex_new=capex_new,
                        wspm_named=named["wspm"])

        unspent_ps = inp["pkg_capex_budget"] * (1 - inp["pkg_capex_done"]) / sh_post
        ext_now = inp["foundry_ext_h1"] * 2 * MM
        overlap = {t: (0.0 if t == "L" else
                       max(0.0, ext[t][2027] - ext_now) * share * margin * keep / sh * pe[t] * sh / sh_post)
                   for t in TIERS}

        # H method (A6b, user 2026-10-05): the higher of (a) full-capacity revenue and (b) the sell-side high path on
        # the same flat-price basis (internal leg held at FY2027: its g2 growth is product price, not wafers).
        path_tot = {s: {y: prod_rev[s] * int_ratio * (1 + g2) ** (y - t0) + ext[s][y] for y in sorted(ext[s])} for s in ("M", "H")}
        path_flat = {y: int_flat + ext["H"][y] for y in sorted(ext["H"])}
        h_method = "path" if path_flat[ss] > rev_full else "capacity"

        fold = (1 + r) ** -tau  # the option is valued at the start of FY2027; fold to the valuation date (A24)

        def v_net(t: str, method: str | None = None, **kw) -> float:
            if t == "H":
                o = (option_path_h if (method or h_method) == "path" else option_full)(**kw)
                return ((o["pv"] - o["unspent"]) / sh_post - unspent_ps - overlap[t]) * fold
            return (option(t, **kw)["pv"] / sh_post - unspent_ps - overlap[t]) * fold

        opt = {"H": option_path_h() if h_method == "path" else option_full()}
        v_k = {t: v_net(t) for t in TIERS}
        # The chosen H revenue must top the M path and every year of the high path it stands for.
        h_rev_ss = max(rev_full, path_flat[ss])
        if not h_rev_ss >= path_tot["M"][ss]:
            errors.append(f"H revenue {h_rev_ss / B:.1f}B below the M path {path_tot['M'][ss] / B:.1f}B (A6b)")
        if h_method == "path" and opt["H"]["wafer_need"] < 0:
            errors.append("high path needs negative wafer revenue -- external packaging above the path (A6b)")
        if not pkg_named <= inp["ext_pkg_h_2030"]:
            errors.append(f"named packaging {pkg_named / B:.1f}B exceeds the H external packaging {inp['ext_pkg_h_2030'] / B:.1f}B (A6b)")
        v_opt = v_k["H"]
        p_k = {t: v_k[t] / v_opt for t in TIERS} if v_opt > 0 else {t: float("nan") for t in TIERS}
        adj_band = [base[t] + p_k[t] * v_opt for t in TIERS]
        if errors:
            warnings.append('historical_foundry_option_guards_require_review')
        if not math.isfinite(v_opt) or v_opt <= 0 or any(not math.isfinite(v) or v < 0 for v in v_k.values()):
            raise ValueError('foundry option unavailable')
        if not 0 <= p_k['L'] <= p_k['M'] <= p_k['H'] == 1:
            raise ValueError('foundry option tiers unavailable')
        if not all(math.isfinite(v) for v in adj_band) or not adj_band[0] < adj_band[1] < adj_band[2]:
            raise ValueError('foundry option band unavailable')
        return {'label': '代工转盈', 'value': v_opt, 'value_unit': 'USD_PER_SHARE',
                'weights': p_k, 'anchors': dict(zip(TIERS, adj_band))}


    # Escrow conversion is a separate contribution to avoid hiding dilution.
    parts = {'products': {t: cpu[t] + win[t] for t in TIERS},
             'foundry_loss': dict(fdy), 'closure': dict(adj),
             'escrow': {t: base[t] - c['pre'][t] for t in TIERS}}
    result = {'ticker': 'INTC.US', 'currency': 'USD', 'units': {'price': 'USD_PER_SHARE'},
              'valuation_as_of': None, 'framework_as_of': None,
              'historical_financial_statement_as_of': '2026-09-26',
              'historical_research_as_of': '2026-10-30',
              'anchors': dict(zip(TIERS, (L, M, H))), 'cut_points': {'A': A, 'B': B_},
              'candidate': None, 'review_flags': warnings,
              'segments': {k: {'unit': 'USD_PER_SHARE', 'values': v} for k, v in parts.items()},
              'key_parameters': {'products': {
                  'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys(TIERS, r)},
                  'growth_rate': {'unit': 'RATIO', 'values': dict.fromkeys(TIERS, g2)},
                  'forward_return': {'unit': 'RATIO', 'values': roe},
                  'steady_return': {'unit': 'RATIO', 'values': {t: min(roe[t], rs) for t in TIERS}}}},
              'basis_changed': None, 'partial_basis_changed': local_basis_changed(
                  {'inputs': inp, 'numerator_scale': MM, 'closure_fields': ADJ_PS}, BASELINE_LOCAL)}
    try:
        result['option'] = calculate_option()
    except (ArithmeticError, ValueError, TypeError):
        result['option'] = {'status': 'unavailable', 'label': '代工转盈', 'anchors': None}
        warnings.append('historical_foundry_option_unavailable')
    return result
