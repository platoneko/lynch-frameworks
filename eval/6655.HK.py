#!/usr/bin/env python3
"""Huaxin's historical domestic / overseas valuation and HPI comparison.

The 2026 inputs, shared Africa / southbound axes, HPI consideration and timing
are retained. Results are HKD/share; no new forecast or publication is implied.
"""
from __future__ import annotations
from lib.gordon import check_g_cap, check_r, payout, perpetual_pe
from lib.inputs import check_missing, ladder
from lib.zones import cut_points
from lib.partial_basis import local_basis_changed

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'zones', 'partial_basis'),
                'axes': {'southbound': 'southbound_repricing', 'africa': 'africa_corridor'}}

HISTORICAL_PARTIAL_FINGERPRINT = '51612e0948a3c19420c98f74837ea1545386cfc73a1f6a352ae550b67bfcdc13'

INPUTS = {
    # 总股本（A+H）；2026Q3季报第10页实收股本 | as-of 2026-09-30
    'shares': 2.078995649e9,
    # 归母权益 343.29228866 亿 ÷ 总股本；2026Q3 季报第10页；只作账面交叉 | as-of 2026-09-30
    'bps': 16.51241015,
    # HKD→CNY；Yahoo Finance HKDCNY=X，报价时间2026-11-02 17:21:27 UTC（北京次日） | as-of 2026-11-03
    'fx_hkdcny': 0.8471,
    # FY2025 末归母权益（A 股年报合并资产负债表）；分腿净资产的**回代校验**基准（A12） | as-of 2025-12-31
    'equity_group': 320.61,
    # **海外腿归母净资产** = 境外分部资产 297.19 − 分部负债 138.04 = 159.15，再扣**已披露的** Lafarge Africa 少数股东权益 7.06（A18 基准分配）；L 档 ROE 分母；M / H 由此滚到 FY2027 末（A12，来源 ①） | as-of 2025-12-31
    'equity_ovs': 152.09,
    # **国内腿归母净资产** = 境内分部资产 679.51 − 分部负债 379.29 = 300.22，减母公司对境外子公司的投资抵销（资产抵销 −173.50 − 负债抵销 −105.50 = −68.00）= 232.22，再扣 Lafarge 之外的全部少数股东权益 53.38 − 7.06 = 46.32（A18） | as-of 2025-12-31
    'equity_dom': 185.90,
    # 未分配项 = 未分配资产 7.53 − 未分配负债 24.92（递延所得税等）；两腿 + 本项 = 归母权益 320.61（回代校验） | as-of 2025-12-31
    'equity_unalloc': -17.39,
    # 少数股东权益合计（合并资产负债表）（A18） | as-of 2025-12-31
    'nci_equity': 53.38,
    # 基准分配下归海外腿的少数股东权益 = 年报「重要的非全资子公司」唯一披露项 Lafarge Africa Plc 期末 NCI 余额 7.06（少数股东 16.19%）（A18） | as-of 2025-12-31
    'nci_equity_ovs': 7.06,
    # FY2025 少数股东损益合计（合并利润表）（A18） | as-of FY2025
    'nci_profit': 6.85,
    # 基准分配下归海外腿的少数股东损益 = Lafarge Africa 并购日至年末归属少数股东损益 0.68（部分年度）；Lafarge 之外的 NCI 损益随 NCI 权益的分配归国内（A18） | as-of FY2025
    'nci_profit_ovs': 0.68,
    # **境外分部利润总额**（年报分部附注）（A3） | as-of FY2025
    'pretax_ovs': 28.52,
    # **境内分部利润总额** 23.88 + 分部间抵销 −2.90（分部间交易全为境内向境外销售，抵销记境内）（A3） | as-of FY2025
    'pretax_dom': 20.98,
    # 两腿共用集团实际税率 = 所得税 14.12 / 利润总额 49.50；分部所得税未披露，`待补`（A19） | as-of FY2025
    'tax_eff': 0.2853,
    # 境外分部折旧和摊销（年报分部附注）；只用于海外 EBITDA 交叉行（A4） | as-of FY2025
    'da_ovs': 7.54,
    # 国内水泥腿 **篮 6 周期商品 / 小盘**（A17）篮子 r；零增长 → 1/r 7.69× | as-of 2026-09-18
    'r_dom': 0.13,
    # 海外（非洲）腿 **篮 6 周期商品 / 小盘**（A17）篮子 r；国别风险在毛利 / ROE 内，不另加；零增长 → 1/r 7.69× | as-of 2026-09-18
    'r_ovs': 0.13,
    # **L** 集团归母 = FY2025 实测（A 股年报合并利润表 2,853,332,040；年报明示境内外准则无差异）；= 两腿分部归母 19.70 + 8.83 的回代基准；当 FY2026 情景，不折（A1） | as-of FY2025
    'ni_group_l': 28.53,
    # **M** = 同花顺机构一致预测 FY2026 净利润均值（20 家，截至 2026-10-01，6 个月内）；水泥属商品价型，资产基数变动 + 国内需求下台阶 → 中枢取前瞻共识中**满足条件的最近一年**（A2）；FY+0，不折；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'ni_group_m': 37.76,
    # **H** = 同花顺 FY2028 净利润均值（19 家，同一快照；最远「≥2 家带区间」共识年，装着价格回升与新增产能，只进 H，A2）；FY+2按A22折1.25年；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'ni_group_h': 52.93,
    # M 分子年（FY+0）→ 分子年已开始，τ = 0、不折（A22）；账面不滚，期初 = FY2025 末扣 2026 年派的上年股息（A12） | as-of 2026-10-04
    'num_year_m': 2026,
    # H 分子年（FY+2）→ τ = 本行 − `t_base` = 1.25 年，各腿以篮子 r 折回并加窗口可分配利润（A22）；账面滚 FY2026–27；L 为 FY2025 实测当 FY2026 情景，不折 | as-of 2026-10-04
    'num_year_h': 2028,
    # 同花顺 FY2028 剔除离群单家中泰后的上沿 = 财通 2026-08-29（详表列出的 10 家中次高；另 9 家页面未列）；**只披露**换它的 H，不入主公式（A2）；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'ni_2028_hi': 60.55,
    # 中泰证券 FY2028 净利润预测（2026-09-03；同花顺 19 家的最大值，离群单家）；**只披露**换它的 H，不入主公式（A2）；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'ni_2028_zt': 79.97,
    # H 股上市（2022-03）以来最高收盘价 HKD，2026-01-26；Longbridge 日 K。**价格护栏**坐标（A2），不入主公式 | as-of 2026-01-26
    'close_hi_listing': 20.06,
    # TTM 归母 = FY2025 28.53332040 − 2025年前三季度20.03800231 + 2026年前三季度28.26274157；季报第11页；只作倍数交叉 | as-of 2026-09-30
    'ni_ttm': 36.75805966,
    # 估值基准日2026-09-30；H折现期 = 2028 − 本行 = 1.25年；L/M为0（A22） | as-of 2026-09-30
    't_base': 2026.75,
    # 2026年前三季度实际归母；季报第3/11页；当年尚未入账利润仅计Q4 = ni_2026 − 本行（A22） | as-of 2026-09-30
    'ni_ytd26': 28.26274157,
    # 海外腿新投资**稳态回报**：生意模式兜底「商品化重资产（非洲建材、水泥）」11%（用户 2026-10-16 定）；低于篮 6 r 13% → eval 取 max(本行, r) = 13%（A22） | as-of 2026-10-16
    'ss_return_ovs': 0.11,
    # 国内腿同上；国内三档 g < 0，回报不进倍数，本行不起作用（A22） | as-of 2026-10-16
    'ss_return_dom': 0.11,
    # 高回报期 Y1 = 可见年末（最远共识年 FY2028）（A22） | as-of 2026-10-16
    'y1_ret': 2028,
    # 高回报期 Y2 = Y1 + 4 年（海外腿进入门槛「中」，依据见 A22） | as-of 2026-10-16
    'y2_ret': 2032,
    # FY2025 末期股息（每 10 股 5.5 元，2026 年派发）；滚账面时从 FY2025 末权益扣除，按两腿 FY2025 归母份额分摊（A12） | as-of FY2025
    'div_fy2025': 11.43,
    # 同花顺 FY2026 净利润均值（20 家）；H 档账面滚动（与 H 分子同源：同一快照均值）；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'ni_2026': 37.76,
    # 同花顺 FY2027 净利润均值（20 家）；H 档账面滚动；FY+1 共识，中性带倍数读数；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'ni_2027': 45.40,
    # **交叉，不进锚点**：FY2025 境外分部利润总额 28.52 + 折旧摊销 7.54（税前 + 折摊口径，财务费用无分部数据未加）（A4） | as-of FY2025
    'ebitda_ovs_l': 36.06,
    # **交叉，不进锚点**：H1 海外收入 85.42 × FY2025 同口径海外 EBITDA 率 30.54%（36.06 / 118.07）× 2；2026 中报无分部表（A4） | as-of 2026H1
    'ebitda_ovs_m': 52.18,
    # **交叉，不进锚点**：公司 2026 海外 EBITDA 目标（公司口径含利息，宽于 L/M 口径）（A4） | as-of 2026 经营计划
    'ebitda_ovs_h': 70.00,
    # **L** 国内水泥腿永续增长（A6，`weakened`）；**无同业锚**（自定）；全派息萎缩分支，PE = 1/(r_dom − g) = 5.56× | as-of FY2025
    'g2_dom_l': -0.05,
    # **M** 国内水泥腿永续增长（A6）；**无同业锚**；PE = 6.25× | as-of FY2025
    'g2_dom_m': -0.03,
    # **H** 国内水泥腿永续增长（A6）；**无同业锚**；PE = 6.67× | as-of FY2025
    'g2_dom_h': -0.02,
    # **L** 海外腿永续增长；**共享轴** `_AXIS.africa-corridor.md`（A7）；cap = min(6%, r_ovs − 4%) = 6%；PE = 1/r 7.69×（海外腿 ROE_L 12.95% 病态区，A12） | as-of 2026-10-04
    # **M** 海外腿永续增长；**共享轴**（A7）；海外腿 ROE_M 18.09% 单调区 → 留存分支 PE 7.92×（稳态回报三段，A12 / A22） | as-of 2026-10-04
    # **H** 海外腿永续增长；**共享轴**（A7）；海外腿 ROE_H 23.00% 单调区 → 留存分支 PE 8.08×（稳态回报三段，A12 / A22） | as-of 2026-10-04
    # own-year PE 实测下沿；**护栏，不入主公式**（A9） | as-of 2023
    'pe_own_lo': 4.24,
    # own-year PE 实测上沿；**护栏，不入主公式**（A9） | as-of 2025
    'pe_own_hi': 12.78,
    # own-year PE 日频 p50；仅作交叉校验（A9） | as-of 2022–2026
    'pe_own_mid': 6.08,
    # 同花顺 FY2026 净利润最小值 35.92 亿 ÷ 股本；仅作 L 档对照，**不入主公式**（A1）；**共识待更新**（本次未核得财报后同源完整快照） | as-of 2026-10-01
    'eps_consensus_low': 1.728,
    # A 股 own-year PE 年均中位；仅作对照，**不入主公式** | as-of FY2022–25
    'pe_a_mid': 11.53,
    # 卖方 H 股共识目标价 HKD（Longbridge `6655.HK` 口径 3 家）；仅作 δ 读数对照（属性 B），**不入主公式** | as-of 2026-08-31
    'tp_sellside_h': 19.47,
    # 境外分部对外收入（年报分部附注）；只用于期权单位经济 = 海外腿税后（扣 NCI 前）利润率 `pretax_ovs` × (1 − `tax_eff`) / 本行（A15） | as-of FY2025
    'rev_ovs': 118.07,
    # **期权份数**：Holcim Philippines Inc.（HPI）2025 收入 **亿美元**（2026-08-02 关联交易公告；已签协议、已过临时股东会）（A15） | as-of FY2025
    'opt_rev_usd': 3.75,
    # HPI 第一阶段收购股权（第二阶段 31.377% 三年内、对价不低于 2.8 亿美元，不计入，A15） | as-of 2026-08-02
    'opt_stake': 0.67623,
    # HPI 第一阶段对价 **亿美元**（100%企业价值7.80亿美元口径）；扣尚未投资的本金，不重复扣税后利息（A15） | as-of 2026-08-02
    'opt_price_usd': 5.27,
    # USD→CNY；Yahoo Finance USDCNY=X，报价时间2026-11-02 17:20:12 UTC（北京次日） | as-of 2026-11-03
    'fx_usdcny': 6.6367,
    # HPI第一阶段对价支付年（已获竞争审批、尚需备案，交割取 2027 = 底牌口径年，不折；A15） | as-of 2026-10-04
    't_opt_pay': 2027,
    # 期权兑现年 = 对齐年份 FY2028（本票最远 ≥2 家带区间共识年）+ 2，**无时点锚·拍值**（交割日与扭亏年均未具名，A15） | as-of 2026-10-04
    't_opt': 2030,
}

# Historical rationale and financial evidence.
# - **业务地图摘要**：分部启发式命中 **3 条**——① 国内/海外两块各 ≥33% 收入（H1 海外已 43.81%）；② 驱动因子完全不同（国内＝需求长期下行 + 反内卷限产托价；海外＝非洲新增产能爬坡 + 当地基建需求）；③ 林奇属性按块不同。**材料**：FY2025 年报（A 股 `600801.SH`）附注「分部信息」按**境内 / 境外**两个报告分部披露了收入、成本、利润总额、折旧摊销、资产总额、负债总额、非流动资产（附注明言「境外业务占比重较大，根据地区划分业务单元」），故两腿的 L 分子与 ROE 分母都有原始披露（A3 / A12）。**未命中**：Wisburg **无华新个股研报覆盖**；分部附注**没有**所得税、财务费用、逐地区少数股东——税率与 NCI 分配是本框架剩下的两处假设（A18 / A19）。
# - **属性 A — 拆分子之后，国内是「量跌价稳」，不是「利润在崩」**：FY2025 分部附注：国内税前 20.98 亿（含抵销）、归母 **8.82 亿**，只占集团 31%；海外税前 28.52、归母 **19.70 亿**（69%）。年报分地区表回推：国内四区收入 FY2024 ≈ 261.7 亿 → FY2025 235.4 亿（**−10%**：华东 −6.6%、华中 −14.4%、华南 −7.7%、西南 −7.0%），但国内毛利 ≈ 57.8 → 57.3 亿（**−0.8%，基本持平**，四区毛利率合计 +4.6pp）。**旧版「国内归母 16.49 → 15.23（−7.6%）」是毛利份额代理的产物**（海外毛利涨得快，国内份额被机械压低），已撤。真正的读法：国内是需求萎缩、反内卷托住价格、利润薄而稳，仍是结构性下行的生意（A6，`weakened`）；FY2024 分部税前利润 `待补`（需 FY2024 年报分部附注），拿到后先复核 L 档 −5%。这条同时推翻「2026H1 净利 +55% 说明国内周期反转」的直觉读法：H1 海外收入 +107%，利润改善的归属仍在海外。
# - **属性 B — 用回报率语言读价格坐标：卖方 TP 与账面各隐含多少 r**（M 档分子，两腿篮子 r 同平移 δ 使分腿加总 = 价格；括号内为单段 g=0 近似 \(E_M/P\)）：
# - **属性 C — 海外腿的材料强度决定了它可以进主公式，而不只是进属性**：
# - **属性 D — A/H 折价使两侧的读数必然不同，这不是矛盾**：本框架锚 H；同一套分腿价值换算到 A 股口径是 9.65 / 13.45 / 18.73 CNY（§3 A 股对照带），同一时刻 A、H 两侧可落在不同 zone。轴文件 §4 的跨票校验要求 H/A 比值方向一致，不是 A/H zone 相同。
# - **属性 E — 少数股东两边都有，分不到腿是本框架剩下的最大构造自由度**：少数股东权益 FY2021 26.5 亿 → FY2025 **53.38 亿** → 2026H1 **51.4 亿**；FY2025 少数股东损益 6.85 亿。年报「企业集团的构成」显示**两边都有大量非全资子公司**：国内有黄石华新绿色建材 58%（注册资本 43 亿，骨料）、华新港城建材 51%、华新春锦建材 32%、华新交投（赤壁）51%、恩施 67% / 昭通 60% / 武汉 70% / 岳阳 68% 等；海外有 Lafarge Africa 84%、Oman Cement 65%、柬埔寨卓雷丁 68%、赞比亚 Chilanga 75%、南非 NPC 74%、塔吉克亚湾 38% / 噶优尔 36%。年报「重要的非全资子公司」只披露 Lafarge Africa 一家（NCI 权益 7.06、并购日至年末 NCI 损益 0.68）。本框架分子用**归母**（已扣 NCI），不重复调整（A11）；但 NCI 在两腿间怎么分决定各腿 ROE——基准只把已披露的 7.06 放海外（海外 ROE 的**上界口径**），三种替代分配各成敏感区一行（A18）。**证伪点：FY2026 年报若披露逐地区 NCI 或更多「重要非全资子公司」**，A18 由假设转实测。
# | A1 | **L 档分子 = FY2025 实测集团归母 28.53 亿 = 分部附注两腿之和**：国内停在实测位置、海外增长立刻停住（消化年），当 FY2026 情景、不折现 | active | A 股年报合并利润表归母 **2,853,332,040**（年报明示境内外准则无差异）。分部口径：海外 19.70 + 国内 8.82（A3）。海外按 `fast_grower` 的消化年构造，冻结在 FY2025 已实现的 19.70 亿，不退回 FY2024（那批产能已投产）。用户 2026-10-04 裁决 L 保持 **2026Q3核对（2026-11-03）**：维持：前三季度归母28.2627亿已接近L全年28.53亿；L保留为消化年压力情景，不代表当年最可能盈利（季报第3页）。 | `ni_group_l`；eval 回代：两腿之和 = 28.53 ± 0.05；**交叉**：同花顺 FY2026 最低预测 35.92 亿——L 比街上最低预期低 21% |
# | A2 | **M 分子 = 同花顺 FY2026 共识均值 37.76 亿（满足条件的最近一年）；H 分子 = 同花顺 FY2028 共识均值 52.93 亿（最远带区间共识年）**；水泥是商品价型，但中枢取前瞻共识（用户 2026-10-04 裁决）；**价格护栏**：M 15.87 低于 H 股上市以来最高收盘 20.06 港元（2026-01-26，Longbridge 日 K；Lafarge Africa 2025 年并表后同一高点），不触发 | active | **为什么 M 不是实测周期均值**：valuation-rules「周期票的中枢分子」适用范围——水泥符合篮 6 判据（区域市场定价，公司不定价），M 本应为中枢；但同节「驱动因子结构性下台阶或资产基数变动时，中枢取 ROE 中枢或前瞻共识，不取实测年份」（样板 `600011.SH`）在本票成立：2025 年现金收购 Lafarge Africa（尼日利亚 4 厂，约 1,060 万吨）改变资产基数、海外已占归母约七成、国内需求结构性下台阶（国内收入 FY2024→FY2025 −10%）。两条实测口径在旧资产基数上互相打架——2016–2025 完整周期实测归母均值 35.77 亿 vs ROE 均值 17.67% × 2026H1 归母权益 = 58.68 亿，相差 64%——故取前瞻共识。**为什么是 FY2026 而不是 FY2028**（同节 2026-10-04 补充：取满足条件的最近一年，本票是该条的反例）：FY2025 实测只含 Lafarge 并购日后的部分年度，资产基数不是今天的，不合格；FY2026 是 Lafarge 全年并表的第一年、国内价格处在现行反内卷 regime，资产基数与价格都是今天的——最近的合格年；FY2027–28 装着尼日利亚 / 莫桑比克新线爬坡与价格回升，只进 H。**H 取均值不取上沿**：最远年份本身已含增长，再取剔除中泰后的上沿（财通 2026-08-29，60.55 亿 → H 25.11）或中泰（2026-09-03，79.97 亿，FY2027 同比 +57.8%，离群 → H 32.76）只披露。**数据源**：同花顺（截至 2026-10-01，6 个月内）FY2026 20 家 35.92 / 37.76 / 40.45 亿、FY2028 19 家 40.47 / 52.93 / 79.97 亿（低 / 均 / 高）。FY2026 → M 分子年已开始，不折；FY2028 → H 是 2028 年初的价值，按各腿篮子 r 折 τ = 1.25 年并加窗口可分配利润（A22 时点对齐）。**价格护栏读法**：M 在上市以来的价格区间内，不需要具名「当时没有的利润」；H 22.11 高于该高点，H 是已建模的成功上沿，护栏不管 H——它的支撑是 FY2028 共识 52.93 亿对本期TTM36.76亿多出的新线产能与价格回升 **2026Q3核对（2026-11-03）**：维持；前三季度归母28.2627亿，全年37.76亿尚需Q4赚9.4973亿，同比约+11.8%；FY2028利润尚不可验证，共识待更新（季报第11页及FY2025基数）。 | `ni_group_m/h`、`num_year_m/h`、`close_hi_listing`、`ni_2028_hi/zt`；本期归母完成原2026均值74.8%，Q4须9.4973亿（同比+11.8%）。全年实测落地后先重判最近合格年，不自动换2027；新共识使M越过历史价格护栏时须具名支撑利润，否则回对话 |
# | A3 | **分腿口径：L 档两腿分子直接取 FY2025 分部附注；M/H 档按 FY2025 实测海外份额 \(s\) = 69.1% 恒定拆共识归母** | active | 年报附注「分部信息」：境外利润总额 **28.52**、境内 23.88、分部间抵销 −2.90（分部间交易收入 14.48 亿全在境内侧，是境内向境外销售，抵销记境内 → 境内 **20.98**）。同一实际税率 28.53%（A19）→ 税后 海外 20.38 / 国内 15.00；扣 NCI 损益（A18：海外 0.68 / 国内 6.17）→ 归母 **海外 19.70 / 国内 8.82**，\(s\) = 19.70 / 28.53 = **69.1%**。M：37.76 → 26.08 / 11.68；H：52.93 → 36.56 / 16.37 **2026Q3核对（2026-11-03）**：维持近似：前三季度归母28.2627亿，公司称增长来自海外，但未披露地区利润，69.1%不能改写成新实测值（季报第4/11页）。 | `pretax_*`、`tax_eff`、`nci_*`；**已知张力**：份额恒定 = 两腿与共识同比例增长，与「海外增、国内缩」的叙事不完全一致（若 M/H 增量全归海外，国内腿三档持平、海外腿更陡）。旧构造「海外 EBITDA × FY2025 转化率、国内取残差」在新口径下国内三档倒序（8.82 → 6.92 → 2.71），构造失效（construction.md §2c），故改份额。**触发器**：下一次共识更新或 FY2026 年报分部附注 → 重设 \(s\)；分部附注若显示国内税前同比转正、海外增速回落 → 份额随实测改 |
# | A4 | **海外 EBITDA 三档只作交叉、不进锚点**：36.06 / 52.18 / 70.00 → 海外归母 ÷ 该行 EBITDA = 0.546 / 0.500 / 0.522（M 分子 FY2026 与 2026 年 EBITDA 行同年；H 分子 FY2028 与之不同年，只作量级对照） | active | L = 境外分部利润总额 28.52 + 折旧摊销 7.54（**税前 + 折摊口径**，分部附注无财务费用，未加；集团财务费用 8.34 亿中利息 7.50、汇兑 2.27 的境外份额未披露）。M = H1 海外收入 85.42 × 同口径 EBITDA 率 30.54% × 2（2026 中报 HKEX 公告无分部表，只给集团 EBITDA 55.50 亿公司口径）。H = 年报「EBITDA 贡献超过 70 亿元」（公司口径含利息，宽于 L/M 口径，方向上高估 H 档 EBITDA）。用 FY2025 转化率 0.546 去乘 M/H 会把国内残差压成负阶梯（A3），所以这三行只作交叉 **2026Q3核对（2026-11-03）**：维持：集团归母28.2627亿不能代替海外EBITDA；本期缺分部表及海外收入，52.18亿保留为2026H1推算，70亿仍是旧目标、未核得本次重申（季报）。 | `ebitda_ovs_*`；eval 泄漏校验：三行翻倍锚点不变。**证伪点**：FY2026 年报分部利润总额 + 折摊若显示海外真实转化率 ≥ 0.5 而集团归母又兑现共识，说明国内利润比共识隐含的更差，A6 三档要下修 |
# | A5 | **贴现率按腿归篮：\(r_{dom} = r_{ovs} = 13\%\)（篮 6），零增长腿 = 7.69×**；港股折价由篮子 r（周期商品 + 港股）承接，\(g\) 只表达增长 | active | `valuation-rules.md`「§r 篮子」：r 由腿的现金流性质归篮，仓库级、不按单票拧（A17 记归篮理由）。分腿 ROE 后海外腿 M/H 落单调区（18.1% / 23.0%）、国内腿三档峰形区（4.7–9.0%）：同一个 13% 在两腿上一个给增长 credit、一个只给萎缩分支（A12） **2026Q3核对（2026-11-03）**：维持：收入296.90亿、归母28.26亿未改变两腿商品业务性质；不因短期增长下调篮子回报要求（季报第3页）。 | 全公式；**敏感性**（`eval` 复算）：两腿 r 12.5% / 13.5% → 11.81 / 16.52 / 23.04 与 11.00 / 15.28 / 21.25；两腿 r 11%（篮 5 读数，仅示）→ 13.30 / 18.79 / 26.34。归篮仍是最大的单一自由度之一，改它须走 §7 篮级对账，不能单票调 |
# | A6 | **国内水泥腿永续 \(g^{dom}\) = −5% / −3% / −2%** | weakened | 旧实证「拆分后国内归母 FY2024 16.49 → FY2025 15.23（−7.6%）」是**毛利份额代理的产物**（海外毛利 +47% 把国内份额机械压低），**已撤**。年报分地区表回推的实测是：国内四区收入 FY2024 ≈ 261.7 → FY2025 235.4 亿（**−10%**），国内毛利 ≈ 57.8 → 57.3 亿（**−0.8%，持平**）——量在跌、价被反内卷托住。三档暂留：L −5%（量降不再被价格抵消）；M −3%（量降被价格抵消一半）；H −2%（限产常态化、行业出清后的稳态）。全派息萎缩分支 → \(PE^{dom} = 1/(r_{dom}-g)\) = 5.56 / 6.25 / 6.67×；国内腿 ROE 4.7–6.8% 在峰形区，\(g<0\) 下封顶生效、倍数与 ROE 无关 **2026Q3核对（2026-11-03）**：维持weakened：集团归母+41.05%不等于国内利润转正；缺国内分部利润。近期全国价格指数一周+2.3%为短期支持，不能改永续g（季报第4页、行业报道）。 | `g2_dom_*`；**证伪触发器**：FY2024 分部税前利润 `待补`（需 FY2024 年报分部附注）——若国内税前 FY2024→FY2025 持平或上升，三档 **MUST** 复核，先动 L 档 −5%；FY2026 年报分部附注国内同比转正 → 三档一起上修 |
# | A7 | **海外腿永续 \(g^{ovs}\) = 0% / +3% / +5%，取自 `_AXIS.africa-corridor.md` §1** | active | **爬坡期的 +65% MUST NOT 当作永续**。轴 2026-10-04 起只装**不含具名项目的稳态值**：撒哈拉以南名义 GDP 按人民币计的长期增速（世界银行；2010–2025 / 2014–2025 年 3.2% / 2.8% → M 3%，2004–2025 年 4.9% → H 5%；L 0% 低于最差十年）。本票的具名项目已在别处：2026 海外 >2,700 万吨 / EBITDA >70 亿、400 亿收入目标与尼日利亚 / 莫桑比克新线在 FY2026–28 共识分子里；海外产能 5,000 万吨目标 ≈ 现有 4,000 万吨 + 豪瑞菲律宾，菲律宾在 A15。本票海外腿是自有水泥产能，按永续落地——三票（含嘉友，用户 2026-10-04 裁决其特许权按永续）同一档 g 逐格相等。cap = min(6%, r_ovs − 4%) = 6% **2026Q3核对（2026-11-03）**：维持：归母+41.05%含海外产能释放，不能外推成永久增速；共享轴0/+3/+5%不动（季报第4页）。 | `g2_ovs_*`；**MUST NOT** 单票改——`check_africa_mount()` 跨文件强制。**证伪点**：海外产能达产后第一个完整年度的海外收入同比若仍 >10%，复核轴而非本票 |
# | A8 | **倍数 MUST NOT 取自历史 PE 分位** | active | 历史 own-year PE 是「当年价 ÷ 当年盈利」，它把**当年市场对增长的看法**烘进了倍数：低增长或负增长预期的年份自然给低 PE，周期底分母塌缩的年份自然给高 PE。用它的分位做三档，等于把过去的增长状态搬到今天，再用今天的分子去乘。**本条偏离 skill A2e-2b 的「倍数三档取自同一分布的三个分位」**，依据是 `valuation-rules.md`「永续增长口径」（倍数由增长率生成、历史带降级为护栏，明示优先于 A2e-2b） **2026Q3核对（2026-11-03）**：维持：Q3归母11.1348亿、扣非10.0943亿，盈利口径差异不构成改用历史PE分位的理由（季报第3—4页）。 | 各腿 \(PE\) 的生成方式；历史带改作 A9 的护栏 |
# | A9 | **自身 own-year PE 实测带 [4.24, 12.78] 降级为交叉校验护栏** | active | H 股价折 CNY ÷ 当年归母/总股本，逐日计算（2022-03 上市起至 2026-09-08，n=1020）：p20 **5.19** · p50 **6.08** · p80 **8.17** · p90 9.47 · max **12.78**。本框架分腿加总折成公司口径倍数（两腿价值 ÷ 该档集团归母；H 含 τ 折现、不含窗口利润）7.03 / 7.40 / 6.56（H 含窗口利润 7.36），在 p50–p80 之间——**全部在实测带内、未越顶**。本票历史上过半交易日印在「篮 6 零增长公允值」7.69× 之下 **2026Q3核对（2026-11-03）**：维持：TTM归母更新36.7581亿；历史实测护栏4.24—12.78不重写，重算公司PE7.03/7.40/6.56仍在带内（季报第11页、eval）。 | eval 硬校验：三档公司口径 PE MUST ∈ [4.24, 12.78]；越顶即红并回对话 |
# | A10 | **H 档海外腿 \(g^{ovs}_H\) MUST ≥ 0**（零增长护栏，逐腿） | active | 「已建模的成功上沿」至少不能让增长腿衰退。本档 \(g^{ovs}_H = +5\%\) ✓；国内腿允许为负（A6 的结构性萎缩是它的世界定义）。这条护栏同时防止 A7 被调成「H 也在衰退」的自相矛盾构造 **2026Q3核对（2026-11-03）**：维持：公司披露海外新增产能释放，未出现需撤销成功档正增长的证据；H海外g仍+5%（季报第4页）。 | eval 硬校验 |
# | A11 | **不做净债 / NCI 二次调整** | active | 分子是**归母**（已扣少数股东、已扣利息），PE 是股权倍数——再从任何一条腿扣净债或账面 NCI 都是把同一件事算两遍。2026Q3 净债约 **150.96 亿**（短借6.26 + 一年内到期53.13 + 长借133.35 + 债券48.41 + 租赁8.12 − 货币资金88.27 − 交易性金融资产10.03；未逐项识别其他类债）、NCI **50.72 亿** **2026Q3核对（2026-11-03）**：维持：净利润36.3718亿−NCI损益8.1090亿=归母28.2627亿，分子已扣少数股东，不重复扣净债（季报第11页）。 | 全公式；EV 口径读法进「交叉备注」 |
# | A12 | **增长按 \(ROE\) 收留存成本，逐腿；各腿 ROE 来自分部附注的分腿归母净资产（来源优先序 ①），分母 = 分子年期初账面** | active | 分腿净资产（FY2025 末）：境外 297.19 − 138.04 = 159.15，境内 679.51 − 379.29 = 300.22；抵销列净 −68.00 是母公司对境外子公司的长期股权投资，从境内扣除 → 232.22；未分配 −17.39；三者 + 少数股东 53.38 = 归母权益 320.61 ✓。扣 NCI（A18 基准）→ 海外 **152.09** / 国内 **185.90**（L 档分母）。**分母 = 分子年期初账面**（valuation-rules ③ 步 2，用户 2026-10-04 裁决按规则）：两档都先扣 2026 年派发的 FY2025 股息 11.43 亿（起点日之后才支付的上年股息，按两腿 FY2025 归母份额 69.1 / 30.9 分摊）；M 分子年 FY2026，到此为止 → 海外 144.20 / 国内 182.36；H 分子年 FY2028，再加 FY2026、FY2027 共识均值 × 模型留存 \(\max(0, g/ROE)\)（国内腿 g<0 不留存）滚到 FY2027 末 → 海外 158.98 / 国内 182.36。三档 ROE：海外 12.95% / 18.09% / 23.00%，国内 4.75% / 6.40% / 8.98%。**域判定**：海外 L 病态区（倍数钉 \(1/r\)）、M/H 单调区（8.34× / 9.78× 是永续沿用前瞻 ROE 的读数；稳态回报三段后 7.92× / 8.08×，A22；Y1 前派息 83% / 78%）；国内三档峰形区，\(g<0\) 封顶，倍数 = \(1/(r-g)\) **2026Q3核对（2026-11-03）**：维持：最新集团归母权益343.2923亿但无地区净资产；不得用9月末集团数据覆盖FY2025分腿期初数据（季报第10页）。 | 全公式；实付留存高于模型留存的部分是「模型视同派出、实际留存」，归 A20 D 桶只披露 |
# | A13 | **国内「反内卷」限产的持续性未单独建模** | active | 已隐含在 `g2_dom` 的三档差（−5% / −3% / −2%）里：限产越持久，量降被价格抵消得越多。**证伪点**：限产退出致国内水泥价格回落 → `g2_dom_*` 三档一起下修 **2026Q3核对（2026-11-03）**：维持：全国水泥价格指数截至10月26日较19日+2.3%，仅支持近期治理有效，未证明永久持续（11月2日行业报道）。 | `g2_dom_*` |
# | A14 | **海外地缘与汇率风险未在 \(g^{ovs}\) 之外单独建模** | active | 产能集中尼日利亚、坦桑尼亚、莫桑比克、赞比亚、津巴布韦——本币波动剧烈、外汇管制常见；公司 2026-07 公告「部分子公司变更记账本位币」即是该风险的体现。A7 的「扣本币贬值后以 CNY 计 2~5%」与篮 6 的 r 是全部处理，国别风险不在 r 上另加（A17） **2026Q3核对（2026-11-03）**：维持风险：归母外币报表折算差额−1.2233亿，汇率对现金及等价物影响−0.6665亿；无逐国风险量化（季报第12—13页）。 | `g2_ovs_*`；量化 `待补`，是 `deep_discount` 档的主要解释材料 |
# | A15 | **豪瑞菲律宾（HPI）按新规则扣未投资本后净值为负，\(V_{opt}\) 记 0**；400 亿收入目标无超额份数 | active | **份数** = 已签合同：HPI 2025 收入 **3.75 亿美元** × 6.6367 = 24.89 亿 CNY，第一阶段 67.623%（2026-08-02 关联交易公告；熟料 520 万吨 / 水泥 900 万吨；HPI 2025 净亏 0.65 亿美元）；共识未含（无 ≥2 家明示）。**单位经济** = 本票海外腿 FY2025 分部税后利润率 **17.26%** → 增量归母 2.91 亿。**估值** = × 海外腿 H 档倍数 8.08×（2026-10-16 起含稳态回报三段，A22；此前 9.78×）（本票篮 6 r 13%、轴 g +5%、海外腿 ROE_H 23.0%；未借同业倍数）÷ 1.13³（兑现年 = 对齐年份 FY2028 + 2 = **2030**，无时点锚·拍值，折到 FY+1 口径）= **0.92 港元 / 股**。**扣未投资本**（valuation-rules 2026-10-04：收购型期权扣尚未投入的资本）：第一阶段对价 5.27 亿美元 = 34.98 亿 CNY，已获竞争审批但尚需备案、交割暂取2027付（底牌口径年，不折）= **1.99 港元 / 股** → 净值 **−1.06**；要打平需年增量归母约 6.24 亿（本票海外腿利润率下的 2.1倍）。期权仍按旧的 FY+1 口径折现、未随底牌改按估值基准日对齐——净值为负、记 0，口径差不改结论。负值说明：在本票自己的尺上，这笔收购只有在 HPI 做到远高于本票海外腿的利润率时才值对价。期权的净值不为负（可以不行权）的前提在这里不成立——协议已签、已过股东会——但它也尚未交割、可能被监管终止，故**记 0、负值作披露**，不从底牌扣（`待补`：是否把已签收购的负净值计入底牌，交用户裁决）。原「对价税后利息」口径撤销（与扣本金重复）。**400 亿收入目标**：已与共识齐平，无份数 **2026Q3核对（2026-11-03）**：维持零估值，确认审批推进：10月30日股东会通过且菲律宾竞争委员会已批准，仍需政府备案或报告；67.623%、约5.27亿美元未变，尚无交割后利润（季报第6页）。最新汇率下对价34.98亿、增量归母2.91亿，净值仍−1.06 HKD/股；不计入底牌。 | `opt_*` / `fx_usdcny` / `t_opt` / `t_opt_pay`；**敏感**：单位利润率取 2026 单期推断 15.3% → 净值 −1.17。**升级门槛**：交割完成并披露 HPI 首个完整年度利润 → 改实测单位；≥2 家卖方明示共识含 HPI → 转进分子。**证伪**：交割终止 → 本项删除 |
# | A16 | **本票挂 `_AXIS.southbound-repricing.md`** | active | H/A 年度均值 2024 0.507 → 2025 0.690 → 2026 0.638（截至 2026-09-08）。轴作用于**要求回报的收敛**而非倍数分位：南向定价权回归 = H 股要求回报向 A 股靠拢 **2026Q3核对（2026-11-03）**：维持：前三季度归母28.2627亿为A/H同一公司盈利；股本20.78995649亿未变，年度H/A序列保留原截止日，不能因事件反应认定长期收敛（季报第10—11页）。 | 轴档位读数 M（按轴 §1 带日期序列）；`optimistic` / `stretched` 侧解释 |
# | A17 | 归篮：国内水泥腿 → 篮 6 周期商品 / 小盘（国内水泥是需求长期下行的价格周期，港股上市）；海外（非洲）腿 → 篮 6 周期商品 / 小盘（非洲水泥自有产能，国别与汇率风险已在毛利 / ROE 内体现，不另加 r；与 `600499.SH` 非洲建材腿同判）；无备选；CAPM 粗筛 11.0%（β 0.74 + 港股 +1 + 国别 +2），篮 6 −2pp 内，不进质疑清单 | active | 篮子归属决策记录「6655.HK 华新建材」节（2026-09-18）；`gordon.BASKET_R`；`valuation-rules.md`「§r 篮子」。归篮触发**分腿加总构造**：两腿 r 各自进各自的倍数，不合成 \(\bar g\)（留存项非线性） **2026Q3核对（2026-11-03）**：维持：巴西拟收购仍为水泥资产，EV约158.68亿改变潜在资金需求，不自动改变归篮（巴西公告第1—2页）。 | `r_dom` / `r_ovs`；篮子变动 → 整条价带重算 |
# | A18 | **少数股东在两腿间的分配（基准 = 只把已披露的 Lafarge Africa NCI 放海外）**：NCI 权益 53.38 中海外 **7.06**、国内 46.32；NCI 损益 6.85 中海外 **0.68**、国内 6.17（Lafarge 之外的 NCI 损益随 NCI 权益的分配走） | active | 年报「重要的非全资子公司」只列 Lafarge Africa Plc（少数股东 16.19%，期末 NCI 余额 7.06 亿，并购日至年末 NCI 损益 0.68 亿；该公司并表期收入 18.05、净利 4.30）。「企业集团的构成」显示海外还有 Oman Cement 65%、柬埔寨卓雷丁 68%、Chilanga 75%、NPC 74%、塔吉克 36–38% 等非全资，国内有黄石华新绿色建材 58%（注册资本 43 亿）、港城 51%、春锦 32% 等——**两边都有，逐地区 NCI 未披露**。基准分配把 Lafarge 之外的 NCI 全放国内，因此是**海外 ROE 的上界口径、国内 ROE 的下界口径**；它隐含国内少数股东的回报 6.17 / 46.32 = 13.3% 对国内归母 ROE 4.75%，差距大，是这条假设最明显的可疑处 **2026Q3核对（2026-11-03）**：维持分配近似：NCI损益8.1090亿、上年同期5.0128亿（+61.8%），期末NCI权益50.7229亿；缺地区拆分，不混入FY2025分部口径（季报第10—11页）。 | `nci_equity_ovs` / `nci_profit_ovs`；**敏感区（eval 打印）**：一半在海外 → 11.07 / 15.54 / 21.84；全在海外 → 10.64 / 15.09 / 21.46；全在国内 → 11.47 / 15.95 / 22.16。**触发器**：FY2026 年报「重要的非全资子公司」新增披露或分部附注给逐地区 NCI → 改实测；Lafarge 全年 NCI 损益（并表期 0.68 → 全年约 1.3–1.5）→ `nci_profit_ovs` 重设 |
# | A19 | **两腿所得税同用集团实际税率 28.53%**（`待补`：分部所得税未披露） | active | 所得税 14.12 / 利润总额 49.50。法定：中国 25%、尼日利亚 / 坦桑尼亚 / 赞比亚 30%、莫桑比克 32%、南非 27%、阿曼 15%。年报税率调节表：「子公司适用不同税率的影响 **−1.23 亿**」（海外法定税率合计略低于 25%，含阿曼与税收优惠）、「海外子公司预期分配收益的预提所得税 **+0.71 亿**」（海外专属）、「未确认可抵扣暂时性差异 / 亏损 +2.70 亿」（亏损子公司，地区不明）。三项方向相抵，同税率是中性近似；若海外实际税率高于国内 5pp，海外归母 −1.0 亿、份额 69.1% → 66%，M 约 −0.14 HKD **2026Q3核对（2026-11-03）**：维持：本期所得税14.4316亿/税前50.8033亿=28.41%，接近FY2025的28.53%；FY2025两腿计算仍配FY2025税率，不跨期替换（季报第11页）。 | `tax_eff`；**触发器**：分部附注或年报分地区所得税披露 → 两腿各用各的税率，A3 的份额随之重设 |
# | A20 | **留存去向审计（海外腿）→ D 桶（具名增长窗口）**；倍数形式：L 档 \(1/r\)（窗口结束、增长停住），M/H 档完整式（窗口后按轴 g 留存）；**杠杆门未触发** | active | Step 0–1：资本开支 2022 → 2025 约 89 → 29 亿港元连降，FY2025 大项是 63 亿港元现金收购 Lafarge Africa（商誉 12 → 43.5 亿 CNY）；在建有名有投产日：尼日利亚 / 莫桑比克新建升级、坦桑尼亚 / 津巴布韦扩建，公司给出 2026 投产与 >2,700 万吨 / 70 亿 EBITDA 目标。实付派息 40%（FY2025 每 10 股 5.5 元 = 11.43 亿 / 28.53 亿），留存 60% 全部进海外产能与收购 → D 桶。**处理**：项目利润已进 M/H 分子（共识 2026 归母含 Lafarge 全年与新线），故已花资本 **不再**按 \(K \times ROE_{proj}/r\) 加回（双算防线）；未花资本不罚（M/H 海外 ROE 18–23% > r，项目回报 ≥ r 的假设由 A12 的域判定承载）；L 档 g=0 + \(1/r\) 合规（D 桶且项目价值已在分子）。**窗口终点**：2026 年报（尼日利亚 / 莫桑比克投产）；窗口后触发：海外 capex 连续两年 > 折摊且无新命名项目 → 改 E 桶（永续留存，倍数按完整式不变但 g 须由派息政策生成）。模型派息（海外 M / H 83% / 78%）与实付 40% 的差 = 「模型视同派出、实际留存」的窗口 capex，只披露不进 SOTP。**杠杆门**（valuation-rules「杠杆门」）：FY2025 年报口径净债务 =（短借 5.69 + 一年内到期 54.32 + 长借 132.15 + 应付债券 52.44 + 租赁 9.49 + 优先股 1.52）− 现金 85.35 − 交易性金融资产 0.02 = **170.2 亿**；EBITDA = 报表营业利润 50.08 + 折摊 36.53 = 86.61 → **净债 / EBITDA 1.97**；利息支出 7.50 / 营业利润 50.08 = **15.0%**（含租赁利息 7.93 → 15.8%）。两条都在阈值（3 / 33%）内，不强制 ROE 拆解 **2026Q3核对（2026-11-03）**：维持原项目分桶：前三季度CFO49.1222亿、购建长期资产现金支出17.7815亿；净债约150.96亿（未逐项识别其他类债），利息/营业利润10.4%。本期缺折摊，最新净债/EBITDA待补，不能称完整复核通过；巴西融资另见A23（季报第9—13页）。 | 全公式的倍数形式；**证伪点**：2026 年报海外 capex 未降、且新项目无投产日 → 海外腿改 E 桶并复核 A7 的 g |
# | A21 | **中枢取前瞻共识的证伪触发器**：国内水泥价格跌破上一轮低点 → 回对话，M 改回实测中枢口径重议 | active | A2 的前提是「共识里的价格不是周期高点外推」：2026 年国内价格靠反内卷 / 错峰托住，海外均价 H1 648 元/吨（同比 +156 元，同花顺页面所载卖方研报摘要）。触发阈值 = 全国水泥价格指数跌破 2024 年低点（点位与数据源 `待补`）；海外均价连续两个半年度回落 >15% 同样回对话 **2026Q3核对（2026-11-03）**：维持、触发核验未闭合：国内指数近期+2.3%，但2024低点绝对阈值仍待补；海外均价未披露，无法完成连续半年度降幅测试，不能写全部未触发（行业报道、季报）。 | `ni_group_m` / `ni_group_h` 的口径 |
# | A22 | **经营价值与超额现金**：无超额现金单列；既有共识项目增长期资金缺口暂按0，不能无条件延伸到潜在新并购；L/M不折、H折1.25年并加尚未入账窗口利润；海外新投资回报2028至2032回落至13%，无k | weakened | **2026Q3核对**：净债约150.96亿；前三季度CFO49.1222亿、购建长期资产现金支出17.7815亿支持既有项目可融资，但巴西EV158.68亿尚缺股权对价、融资和现金流，未来资金缺口为零的笼统判断削弱（季报第9—13页、A23）。本次共识不含可识别的巴西增量，既不加利润也不单边扣EV；菲律宾利润仍只在A15，不在底牌。**时点**：基准日2026-09-30，H为2028年初价值，τ=1.25；未入账利润为Q4 2026的9.49725843亿+FY2027的45.40亿，按69.1%分腿、乘账面滚动同一派息率，窗口45.51亿、折后42.17亿=2.39 HKD/股。拟派前三季度股息10.39497825亿尚待批准，是模型分配利润的去向，不另加价值、不覆盖FY2025已派股息；未来宣派未付时复核类债与留存，避免重复扣。**既有回报路径不改**：Y1=2028、Y2=2032，进入门槛中（建厂2—3年、运输半径壁垒但新进入者扩张较快）；前瞻回报18.09%/23.00%回落至13%（自身同口径分腿周期不可用、成熟同业合格读数未得，用户2026-10-16裁定兜底11%，低于r取r）；倍数7.92/8.08。无新增回报来源，不重设稳态参数。 | `t_base`、`ni_ytd26`、`ss_return_ovs/dom`、`y1_ret/y2_ret`；H折现与窗口；巴西签最终协议且明确进入共识后必须重算资金缺口 |
# | A23 | **巴西CSN水泥仅独家谈判，尚无可闭合的股东增值测算，不计底牌或期权金额** | active | 2026-10-30排他协议授予10天独家谈判权，标的企业价值127亿雷亚尔、约158.68亿CNY；尚无最终协议，需中巴审批。企业价值不是最终股权对价；股权比例、净债交割调整、融资与目标稳态利润待补。暂不将这笔交易装进只面向非洲需求的共享轴。来源：巴西排他协议公告第1—2页。 | 最终协议/终止/融资披露即复核；利润纳入底牌时同步计入对价、类债和资金缺口，避免只加利润或只扣EV；未核到可量收益前不抬H |

TIERS = ("l", "m", "h")
# Perpetual-g inputs carry the `g2_` prefix so scripts/calibration.py reports
# them in its g2 column (valuation-rules.md「永续增长口径」).  Each leg has its
# own basket r row.
LEGS = ("dom", "ovs")
R_ROWS = {"dom": "r_dom", "ovs": "r_ovs"}
MONOTONIC_GAP = 0.03        # |ROE - r| threshold of the domain table (gordon._ROE_NEAR_R)
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"
BASIS_YEAR = 2027           # FY+1 relative to today: the undiscounted basis of the deck
TOL = 0.05
H1_OVS_REV = 85.42         # 2026H1 overseas revenue 亿 (§0 snapshot); V_opt sensitivity print only

REQUIRED = [
    "shares", "bps", "fx_hkdcny",
    "equity_group", "equity_ovs", "equity_dom", "equity_unalloc",
    "nci_equity", "nci_equity_ovs", "nci_profit", "nci_profit_ovs",
    "pretax_ovs", "pretax_dom", "tax_eff", "da_ovs",
    "r_dom", "r_ovs",
    "ni_group_l", "ni_group_m", "ni_group_h",
    "ebitda_ovs_l", "ebitda_ovs_m", "ebitda_ovs_h",
    "g2_dom_l", "g2_dom_m", "g2_dom_h",
    "g2_ovs_l", "g2_ovs_m", "g2_ovs_h",
    "pe_own_lo", "pe_own_hi", "pe_own_mid",
    "eps_consensus_low", "pe_a_mid",
    "rev_ovs", "opt_rev_usd", "opt_stake", "opt_price_usd", "fx_usdcny", "t_opt", "t_opt_pay",
    "num_year_m", "num_year_h", "div_fy2025", "ni_2026", "ni_2027", "ni_2028_hi", "ni_2028_zt",
    "close_hi_listing",
    "t_base", "ni_ytd26", "ss_return_ovs", "ss_return_dom", "y1_ret", "y2_ret",
]


def opt_delta_ni(inp: dict[str, float], margin: float | None = None) -> float:
    """A15: HPI stage-1 incremental 归母, 亿元 CNY = revenue (USD 亿 -> CNY) x the
    overseas leg's FY2025 segment after-tax margin (before NCI) x the stake.
    The consideration is deducted as unspent capital, not as an interest carry."""
    if margin is None:
        margin = inp["pretax_ovs"] * (1.0 - inp["tax_eff"]) / inp["rev_ovs"]
    return inp["opt_rev_usd"] * inp["fx_usdcny"] * margin * inp["opt_stake"]


def domain(roe: float, r: float) -> str:
    """valuation-rules.md 域判定表, per leg and tier."""
    if roe - r >= MONOTONIC_GAP:
        return "单调区"
    if abs(roe - r) < MONOTONIC_GAP:
        return "病态区"
    return "峰形区"


def nci_profit_ovs(inp: dict[str, float], nci_equity_ovs: float) -> float:
    """NCI profit assigned to the overseas leg under an NCI-equity allocation.

    The disclosed Lafarge Africa share (equity 7.06 / profit 0.68, A18) is the
    only hard datum; NCI equity beyond it is split domestic/overseas by
    assumption, and its profit follows the same split pro rata.
    """
    laf_eq, laf_profit = inp["nci_equity_ovs"], inp["nci_profit_ovs"]
    rest_eq = inp["nci_equity"] - laf_eq
    rest_profit = inp["nci_profit"] - laf_profit
    extra = max(0.0, nci_equity_ovs - laf_eq) / rest_eq if rest_eq > 0 else 0.0
    return laf_profit * min(1.0, nci_equity_ovs / laf_eq) + rest_profit * extra


def leg_split(inp: dict[str, float], nci_equity_ovs: float | None = None) -> tuple[dict[str, float], dict[str, float]]:
    """({leg: 归母 net assets}, {leg: FY2025 归母 NI}) for an NCI allocation.

    Default = the framework's base allocation (only the disclosed Lafarge
    Africa NCI sits overseas).  Other allocations move NCI equity between the
    legs and move NCI profit with it.
    """
    base = inp["nci_equity_ovs"]
    nci_ovs = base if nci_equity_ovs is None else nci_equity_ovs
    equity = {"ovs": inp["equity_ovs"] + base - nci_ovs,
              "dom": inp["equity_dom"] - (base - nci_ovs)}
    p_ovs = nci_profit_ovs(inp, nci_ovs)
    after_tax = 1.0 - inp["tax_eff"]
    ni_l = {"ovs": inp["pretax_ovs"] * after_tax - p_ovs,
            "dom": inp["pretax_dom"] * after_tax - (inp["nci_profit"] - p_ovs)}
    return equity, ni_l


def legs(inp: dict[str, float], tag: str, ni_l: dict[str, float]) -> dict[str, float]:
    """{leg: net income} for one tier, 亿元 CNY: L from the segment note,
    M/H = consensus group NI x the FY2025 realised overseas share."""
    if tag == "l":
        return dict(ni_l)
    share = ni_l["ovs"] / (ni_l["ovs"] + ni_l["dom"])
    group = inp[f"ni_group_{tag}"]
    return {"ovs": group * share, "dom": group * (1.0 - share)}


def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-segment RONIC path (valuation-rules「经营价值与超额现金」② 稳态回报三段; the
    gordon.py helper is not built yet).  Multiple on the numerator year (t = 1 <-> calendar
    t0): retention of calendar year c earns the forward roe while c <= y1, falls linearly to
    the steady return by y2, and the steady return (capped at roe) holds in a Gordon tail
    from y2.  g <= 0 consumes no return -> perpetual_pe."""
    if g <= 0:
        return perpetual_pe(g, roe, r)
    rs = min(roe, r_s)

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
            return pv + e * payout(g, rs) / ((r - g) * (1.0 + r) ** (t - 1))
        pv += e * payout(g, ron(cal)) / (1.0 + r) ** t
        e *= 1.0 + g
        t += 1


def num_start(inp: dict[str, float], tag: str) -> int:
    """Calendar year of the tier's numerator: L = FY2025 actual read as the FY2026 case."""
    return 2026 if tag == "l" else int(inp[f"num_year_{tag}"])


def leg_pe(inp: dict[str, float], leg: str, tag: str, roe: float, r_shift: float = 0.0,
           g_override: float | None = None) -> float:
    """Leg multiple; new-investment return on the three-segment path (A21): forward leg ROE
    to y1_ret, linear fade, steady max(ss_return_<leg>, r) from y2_ret."""
    g = inp[f"g2_{leg}_{tag}"] if g_override is None else g_override
    r = inp[R_ROWS[leg]] + r_shift
    return path_pe(g, roe, r, num_start(inp, tag), int(inp["y1_ret"]), int(inp["y2_ret"]),
                   max(inp[f"ss_return_{leg}"], r))


def window_cny(inp: dict[str, float], equity25: dict[str, float], share: float, tag: str) -> dict[str, float]:
    """Window distributable profit per leg, 亿元 CNY (valuation-rules ③ 时点对齐; A22): the
    consensus profit not yet booked between the 2026-09-30 base date and the numerator year
    (Q4 2026 = ni_2026 - ni_ytd26, then each full year) x (1 - b), b = the book roll's
    max(0, g/ROE) for that leg and year (same roll as roll_book).  Undiscounted."""
    split = {"ovs": share, "dom": 1.0 - share}
    book = {leg: equity25[leg] - inp["div_fy2025"] * split[leg] for leg in LEGS}
    out = {leg: 0.0 for leg in LEGS}
    for year in range(2026, int(inp[f"num_year_{tag}"])):
        unbooked = inp[f"ni_{year}"] - (inp["ni_ytd26"] if year == 2026 else 0.0)
        for leg in LEGS:
            ni = inp[f"ni_{year}"] * split[leg]
            b = max(0.0, 1.0 - payout(inp[f"g2_{leg}_{tag}"], ni / book[leg]))
            out[leg] += unbooked * split[leg] * (1.0 - b)
            book[leg] += ni * b
    return out


def roll_book(inp: dict[str, float], equity25: dict[str, float], share: float, tag: str) -> dict[str, float]:
    """Start-of-numerator-year leg book (valuation-rules ③ step 2): end-FY2025 book
    less the FY2025 dividend paid in 2026 (split by NI share), plus each consensus
    year before the numerator year (同花顺 mean) x the model retention max(0, g/ROE)."""
    split = {"ovs": share, "dom": 1.0 - share}
    book = {leg: equity25[leg] - inp["div_fy2025"] * split[leg] for leg in LEGS}
    for year in range(2026, int(inp[f"num_year_{tag}"])):
        for leg in LEGS:
            ni = inp[f"ni_{year}"] * split[leg]
            book[leg] += ni * max(0.0, 1.0 - payout(inp[f"g2_{leg}_{tag}"], ni / book[leg]))
    return book


class Model:
    """One SOTP under one NCI allocation; everything else read from Inputs."""

    def __init__(self, inp: dict[str, float], nci_equity_ovs: float | None = None):
        self.inp = inp
        self.equity, self.ni_l = leg_split(inp, nci_equity_ovs)
        share = self.ni_l["ovs"] / (self.ni_l["ovs"] + self.ni_l["dom"])
        self.book = {"l": dict(self.equity)}
        for t in ("m", "h"):
            self.book[t] = roll_book(inp, self.equity, share, t)
        self.ni = {t: legs(inp, t, self.ni_l) for t in TIERS}
        self.roe = {t: {leg: self.ni[t][leg] / self.book[t][leg] for leg in LEGS} for t in TIERS}
        self.pe = {t: {leg: leg_pe(inp, leg, t, self.roe[t][leg]) for leg in LEGS} for t in TIERS}
        # 时点对齐 (A21): tau = base date -> start of the numerator year, in years; a numerator
        # year already begun (L read as FY2026, M = FY2026) takes tau 0 and no window.
        self.n = {"l": 0.0, **{t: max(0.0, inp[f"num_year_{t}"] - inp["t_base"]) for t in ("m", "h")}}
        self.window = {t: (window_cny(inp, self.equity, share, t) if self.n[t] > 0 else {leg: 0.0 for leg in LEGS})
                       for t in TIERS}

    def value_cny(self, tag: str, pes: dict[str, float] | None = None, r_shift: float = 0.0) -> float:
        """Leg values at the start of the numerator year, discounted tau years to the base
        date at each leg's r (window profit excluded -- see window_pv_cny)."""
        pe = pes or self.pe[tag]
        return sum(self.ni[tag][leg] * pe[leg] / (1.0 + self.inp[R_ROWS[leg]] + r_shift) ** self.n[tag]
                   for leg in LEGS)

    def window_pv_cny(self, tag: str, r_shift: float = 0.0) -> float:
        """Window distributable profit discounted tau/2 at each leg's r (A21)."""
        return sum(self.window[tag][leg] / (1.0 + self.inp[R_ROWS[leg]] + r_shift) ** (self.n[tag] / 2.0)
                   for leg in LEGS)

    def per_share_cny(self, tag: str, pes: dict[str, float] | None = None, r_shift: float = 0.0) -> float:
        return (self.value_cny(tag, pes, r_shift) + self.window_pv_cny(tag, r_shift)) * 1e8 / self.inp["shares"]

    def anchor(self, tag: str, pes: dict[str, float] | None = None, r_shift: float = 0.0) -> float:
        """HKD per share."""
        return self.per_share_cny(tag, pes, r_shift) / self.inp["fx_hkdcny"]

    def band(self, pes_by_tier: dict[str, dict[str, float]] | None = None, r_shift: float = 0.0) -> list[float]:
        return [self.anchor(t, pes_by_tier[t] if pes_by_tier else None, r_shift) for t in TIERS]

    def implied_r_shift(self, price_cny: float) -> float:
        """δ such that the M-tier SOTP with every leg at r_leg + δ equals a price coordinate.

        Both legs' basket r move together; the answer is the parallel shift the
        coordinate (sell-side TP, book) applies to the basket table, not a per-leg r.  Bisection on
        δ ∈ [-8%, +20%]: the SOTP is monotone decreasing in δ over that range.
        """
        lo, hi = -0.08, 0.20

        def f(delta: float) -> float:
            pes = {leg: leg_pe(self.inp, leg, "m", self.roe["m"][leg], r_shift=delta) for leg in LEGS}
            return self.per_share_cny("m", pes, delta) - price_cny

        if f(lo) < 0 or f(hi) > 0:
            raise ValueError("implied r shift outside bisection bracket")
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2


def evaluate(inp: dict[str,float]) -> dict:
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))

    lo, hi = inp["pe_own_lo"], inp["pe_own_hi"]
    r = {leg: inp[R_ROWS[leg]] for leg in LEGS}

    # --- Step 1: baskets — each leg's r must be the basket it names -----------
    baskets = {"r_dom": 6, "r_ovs": 6}
    for leg in LEGS:
        row = R_ROWS[leg]
        if row not in baskets:
            errors.append(f"{row}: Inputs source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errors += check_r(r[leg], row, baskets.get(row))
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 2: leg book and numerators -------------------------------------
    m = Model(inp)
    # 回代校验 (valuation-rules.md 分腿 ROE 来源优先序 护栏): the two legs'
    # 归母 net assets plus the unallocated block must rebuild group 归母 equity,
    # and the segment-derived L legs must rebuild the group L numerator.
    rebuilt = m.equity["ovs"] + m.equity["dom"] + inp["equity_unalloc"]
    if abs(rebuilt - inp["equity_group"]) > 0.5:
        errors.append(f"leg equity {m.equity['ovs']:.2f} + {m.equity['dom']:.2f} + unallocated "
                      f"{inp['equity_unalloc']:.2f} = {rebuilt:.2f} != equity_group {inp['equity_group']}")
    leg_sum = m.ni_l["ovs"] + m.ni_l["dom"]
    if abs(leg_sum - inp["ni_group_l"]) > 0.05:
        errors.append(f"segment legs {m.ni_l['ovs']:.2f} + {m.ni_l['dom']:.2f} = {leg_sum:.2f} "
                      f"!= ni_group_l {inp['ni_group_l']} (tax / NCI allocation does not add back)")
    for leg in LEGS:
        if m.equity[leg] <= 0:
            errors.append(f"equity_{leg}={m.equity[leg]:.2f} must be positive (回对话)")
    for t in TIERS:
        for leg in LEGS:
            if m.roe[t][leg] > 0.60:
                errors.append(f"ROE_{leg}_{t}={m.roe[t][leg]:.1%} > 60% — leg book implausible (回对话)")
    errors += ladder("ni_group", inp["ni_group_l"], inp["ni_group_m"], inp["ni_group_h"])
    errors += ladder("ebitda_ovs (cross-check)", inp["ebitda_ovs_l"], inp["ebitda_ovs_m"], inp["ebitda_ovs_h"])
    # Both legs must ladder on their own.
    errors += ladder("ni_dom", *(m.ni[t]["dom"] for t in TIERS))
    errors += ladder("ni_ovs", *(m.ni[t]["ovs"] for t in TIERS))
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 3: the growth ladders, per leg against its own basket r --------
    errors += ladder("g_dom", inp["g2_dom_l"], inp["g2_dom_m"], inp["g2_dom_h"])
    errors += ladder("g_ovs", inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    for leg in LEGS:
        for t in TIERS:
            g = inp[f"g2_{leg}_{t}"]
            if r[leg] - g <= 0:
                errors.append(f"g2_{leg}_{t}={g:.4f} >= r_{leg}={r[leg]} — perpetuity diverges")
            # valuation-rules.md 永续上限: min(6%, r − 4%) per leg.
            errors += check_g_cap(g, r[leg], f"g2_{leg}_{t}")
    if errors:
        raise ValueError('; '.join(errors))

    # Overseas growth comes directly from the shared Africa snapshot. The
    # southbound axis supplies historical reference only and cannot set EPS.

    # --- Step 5: the normative guards ----------------------------------------
    # A10: "modelled success" must not shrink the growth leg forever.
    if inp["g2_ovs_h"] < -1e-12:
        errors.append(
            f"H tier overseas g={inp['g2_ovs_h']:.2%} < 0 — the optimistic tier cannot "
            f"price perpetual decline on the growth leg (A10)"
        )
    # A9: the company-level multiple (SOTP value / group NI) still has to be a
    # price this stock could print.
    pe_company = {t: m.value_cny(t) / inp[f"ni_group_{t}"] for t in TIERS}
    for t in TIERS:
        if not (lo - 1e-9 <= pe_company[t] <= hi + 1e-9):
            errors.append(
                f"PE_{t.upper()} (company)={pe_company[t]:.2f} outside own-year measured band "
                f"[{lo}, {hi}] — the normative anchor left the ticker's history (A9)"
            )
    # A12: growth is paid for out of retained earnings, and a shrinking
    # business is not assumed to hand back more than it earns — per leg.
    for t in TIERS:
        for leg in LEGS:
            g = inp[f"g2_{leg}_{t}"]
            pay = payout(g, m.roe[t][leg])
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
    # Comparison-only fields must stay out of the computation path.
    for key in ("pe_a_mid", "pe_own_mid"):
        if any(abs(inp[key] - m.pe["m"][leg]) < 1e-9 for leg in LEGS):
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    # A4: the overseas EBITDA rows are a cross-check only.  Doubling them must
    # leave every anchor untouched.
    scaled = Model({**inp, **{f"ebitda_ovs_{t}": 2 * inp[f"ebitda_ovs_{t}"] for t in TIERS}})
    if any(abs(a - b) > 1e-9 for a, b in zip(m.band(), scaled.band())):
        errors.append("ebitda_ovs_* leaked into the anchor path — they are cross-check rows (A4)")
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 6: anchors ----------------------------------------------------
    L, M, H = m.band()
    if not (L < M < H):
        raise ValueError(f'L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}')
    A, B = cut_points(L, M, H)

    # Price guardrail (valuation-rules「中枢…」2026-10-04): an M above every close
    # since listing needs a named profit that did not exist then.
    guard_hit = M > inp["close_hi_listing"]
    if not inp["num_year_m"] <= inp["num_year_h"]:
        errors.append("num_year_m must not be later than num_year_h (M takes the nearest qualifying year)")

    # flat-multiple: each leg held at its own PE_M across the three tiers.
    flat = m.band({t: m.pe["m"] for t in TIERS})
    errors += ladder("flat-multiple", *flat)

    # --- Step 7: V_opt (A15) — own ruler, net of the unpaid consideration ------
    if not inp["t_opt_pay"] <= inp["t_opt"] or inp["t_opt"] <= BASIS_YEAR:
        errors.append("option years must satisfy t_opt_pay <= t_opt and t_opt after the deck basis (A15)")
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errors.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    pe_ovs_h = m.pe["h"]["ovs"]
    to_hkd = 1e8 / inp["shares"] / inp["fx_hkdcny"]

    def gross_of(delta_ni: float) -> float:
        return delta_ni * to_hkd * pe_ovs_h / (1.0 + r["ovs"]) ** (inp["t_opt"] - BASIS_YEAR)

    capex = inp["opt_price_usd"] * inp["fx_usdcny"] * to_hkd / (1.0 + r["ovs"]) ** (inp["t_opt_pay"] - BASIS_YEAR)
    d_ni = opt_delta_ni(inp)
    gross = gross_of(d_ni)
    net = gross - capex
    v_opt = max(0.0, net)
    if errors:
        raise ValueError('; '.join(errors))
    # Preserve the old treatment of a negative acquisition result (zero
    # extra value). A signed commitment may still have costs, which are not
    # assessed by truncating this optional result and need human review.
    segments = {}
    for leg in LEGS:
        segments[leg] = {'unit': 'HKD_PER_SHARE', 'values': {
            t.upper(): m.ni[t][leg] * m.pe[t][leg] / (1 + r[leg]) ** m.n[t] * to_hkd
            for t in TIERS}}
    segments['unbooked_earnings'] = {'unit': 'HKD_PER_SHARE', 'values': {
        t.upper(): sum(m.window[t][leg] / (1 + r[leg]) ** (m.n[t] / 2)
                       for leg in LEGS) * to_hkd for t in TIERS}}
    parameters = {}
    for leg in LEGS:
        parameters[leg] = {
            'discount_rate': {'unit': 'RATIO', 'values': dict.fromkeys('LMH', r[leg])},
            'growth_rate': {'unit': 'RATIO', 'values': {t.upper(): inp[f'g2_{leg}_{t}'] for t in TIERS}},
            'forward_return': {'unit': 'RATIO', 'values': {t.upper(): m.roe[t][leg] for t in TIERS}},
            # Nonpositive growth uses the full-payout branch and does not use
            # a terminal investment return; positive-growth return is capped.
            'steady_return': {'unit': 'RATIO', 'values': {
                t.upper(): (min(m.roe[t][leg], max(inp[f'ss_return_{leg}'], r[leg]))
                            if inp[f'g2_{leg}_{t}'] > 0 else None) for t in TIERS}},
        }
    flags = ['historical_signed_acquisition_obligation_unverified',
             'historical_nci_allocation_assumed', 'historical_estimates_not_refreshed']
    if guard_hit:
        flags.append('historical_price_guard_requires_review')
    if v_opt > 0:
        flags.append('positive_acquisition_option_weights_unavailable')
    return {
        'ticker': '6655.HK', 'currency': 'HKD',
        'valuation_as_of': None, 'framework_as_of': None,
        'historical_valuation_as_of': '2026-09-30',
        'historical_framework_as_of': '2026-11-03',
        'units': {'price': 'HKD_PER_SHARE'},
        'anchors': dict(zip('LMH', (L, M, H))), 'candidate': None, 'option': None,
        'segments': segments, 'key_parameters': parameters,
        'a_share_comparison': {t.upper(): value * inp['fx_hkdcny'] for t, value in zip(TIERS, (L, M, H))},
        'historical_acquisition': {'gross_per_share': gross, 'price_per_share': capex,
                                   'net_per_share': net, 'additional_value': v_opt},
        'review_flags': flags,
        'diagnostics': {'profit': {t.upper(): m.ni[t] for t in TIERS},
                        'book': {t.upper(): m.book[t] for t in TIERS},
                        'roe': {t.upper(): m.roe[t] for t in TIERS},
                        'pe': {t.upper(): m.pe[t] for t in TIERS},
                        'window': {t.upper(): m.window[t] for t in TIERS}},
    }


def calculate(context):
    southbound = context['axes']['southbound']
    if southbound.get('role') != 'reference':
        raise ValueError('southbound axis must be a reference')
    africa = context['axes']['africa']
    shared = {f'g2_ovs_{t}': africa[f'g2_ovs_{t}'] for t in TIERS}
    result = evaluate({**INPUTS, **shared})
    result['basis_changed'] = None
    result['partial_basis_changed'] = local_basis_changed(
        {'inputs': INPUTS, 'africa': shared, 'southbound_source': context['axis_versions']['southbound'],
         'constants': [MONOTONIC_GAP, BASIS_YEAR, H1_OVS_REV]}, HISTORICAL_PARTIAL_FINGERPRINT)
    return result
