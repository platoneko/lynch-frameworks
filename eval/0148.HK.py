#!/usr/bin/env python3
"""Kingboard's historical multi-leg valuation and two capacity options.

The 2026 sources, cash and asset bridge, separate business axes and conditional
candidate are preserved. Values are HKD/share; this is not a new forecast.
"""
from __future__ import annotations
import math
from lib.gordon import check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe
from lib.inputs import check_missing, require_whole_years
from lib.partial_basis import local_basis_changed
from lib.rf_report import calculate_rf_readings, result_rate_sensitivity

DEPENDENCIES = {'libraries':('gordon','inputs','partial_basis','rf_report'),
                'axes':{'glass':'ai_glass_fabric','copper':'hvlp_copper_foil'}}
HISTORICAL_PARTIAL_FINGERPRINT = 'c95a7c53786435e7de7f1e261438d4621f8d7bc686c13a9cc6944f1dd7ec03a4'

# Original inputs with sources, purpose and as-of.
INPUTS = {
    # 已发行股数（十亿股）：中报股本 112,178 千港元 ÷ 0.10 | as-of 2026-06-30
    'shares': 1.12178,
    # 持有 1888 比例：中报「重大收购及出售」 | as-of 2026-06-30
    'stake_kl': 0.6169,
    # 经营腿税率：内地 25% / 高新 15% 混合 + 股息预提 5–10%（1888 中报附注 8：2026H1 实际 17.9%） | as-of 2026-06-30
    'tax': 0.20,
    # 物业腿税率：内地企业所得税 | as-of 2026-06-30
    'tax_prop': 0.25,
    # 覆铜板分部净资产（十亿港元）：年报分部附注 (b)：分部资产 21,297 − 分部负债 3,408 百万 | as-of 2025-12-31
    'na_lam': 17.889,
    # 线路板分部净资产：同上 17,738 − 2,668 | as-of 2025-12-31
    'na_pcb': 15.070,
    # 化工分部净资产：同上 10,201 − 455 | as-of 2025-12-31
    'na_chem': 9.746,
    # 母公司层投资物业（仅用于域判定）：中报 26,981 − 1888 中报 1,230 | as-of 2026-06-30
    'ip_hold': 25.751,
    # 覆铜板中枢回报（分部业绩 / 年初分部净资产）：FY2017–2025 九年均值（eval `HIST_*` 复算） | as-of 2025-12-31
    # 覆铜板谷底回报：FY2023 1,572 / 2022 年末 16,026 | as-of 2023-12-31
    # 谷底实测回升年增速：FY2023 1,572 → FY2025 2,837 两年 CAGR | as-of 2025-12-31
    # 实测回升年数：覆铜板 2023→2025、化工 2016→2018 | as-of 2025-12-31
    'n_rec': 2,
    # H 路径 FY2026 覆铜板税后利润（十亿港元）：1888 卖方 FY2026E EPS 均值 2.626（Longbridge，区间 2.17–3.155）× 31.5145 亿股；以净利近似 NOPAT（利息与投资损益方向相反、量级 < 3%） | as-of 2026-09-23
    'e_lam_26': 8.28,
    # H 路径 FY2027：摩根大通 3.55（目标价 65 ÷ 1.41 ÷ 13×）与花旗 4.14（目标价 120 ÷ 29×）EPS 均值 × 股数；两家点估计进 \(g_1\) 路径 | as-of 2026-09-23
    'e_lam_27': 12.12,
    # 花旗单家 FY2027 净利（十亿港元）：EPS 4.14（目标价 120 ÷ 29×）× 31.5145 亿股；只用来把花旗的 FY2028 换成花旗自己的 FY27→FY28 增速（候选带，A10） | as-of 2026-07-04
    'e_lam_27c': 13.047,
    # 候选带 FY2028（单家）：花旗「至 2028 年三年盈利 CAGR 92%」× FY2025 净利 2.44（Longbridge）；候选带只取它对 `e_lam_27c` 的增速（增长型，A10），A9 特种布量仍用此水平 | as-of 2026-07-04
    'e_lam_28c': 17.27,
    # 高点回落到中枢年数：实测：覆铜板回报 2017 28.2% → 2019 15.0%；2021 50.1% → 2022 11.8% | as-of 2025-12-31
    'n_fade': 2,
    # 覆铜板腿 H 档回落后新投资的稳态回报 = 自身最近一轮谷到谷 FY2019–23 税后 17.81%（同 `rs_gf`；M / L 档受各自前瞻 = 九年中枢 16.94% 封顶，不变；A2） | as-of 2026-10-19
    # 线路板回报低点：FY2019 487 / 2018 年末 10,395 | as-of 2019-12-31
    # 线路板回报均值：FY2017–2025 | as-of 2025-12-31
    # 线路板回报高点：FY2024 1,360 / 2023 年末 12,949 | as-of 2024-12-31
    # 化工分部业绩低点（十亿港元）：FY2016 | as-of 2016-12-31
    # 化工分部业绩均值：FY2016–2025 | as-of 2025-12-31
    # 化工分部业绩高点：FY2021 | as-of 2021-12-31
    # 年租金 L：M −10%（A5 转弱线） | as-of 2026-06-30
    'rent_l': 1.224,
    # 年租金 M：2026H1 679.8 百万 × 2 | as-of 2026-06-30
    'rent_m': 1.360,
    # 年租金 H：M +2% | as-of 2026-06-30
    'rent_h': 1.387,
    # 租金 NOI 率：假设，待补核实（A5） | as-of 2026-06-30
    'noi_margin': 0.80,
    # 覆铜板腿 r：篮 6 周期商品：盈利是玻纤布 / 铜箔 / 覆铜板价格的函数（A11） | as-of 2026-09-28
    'r_lam': 0.13,
    # 线路板腿 r：篮 4 龙头制造：加工费生意，原料涨价可转嫁、客户分散（A11） | as-of 2026-09-28
    'r_pcb': 0.10,
    # 化工腿 r：篮 6 周期商品：烧碱等大宗化工（A11） | as-of 2026-09-28
    'r_chem': 0.13,
    # 出租物业腿 r：篮 6 小盘不明朗：内地商业物业，免租期与减值未止（A11） | as-of 2026-09-28
    'r_prop': 0.13,
    # 总部费用资本化 r：篮 4：与集团经营同级（A11） | as-of 2026-09-28
    'r_hq': 0.10,
    # 覆铜板腿永续增长：具名宏观上限：商品腿按通胀；≤ \(G_{cap}\) 6%；无同业锚（台光 / 生益 / 南亚同尺反解待补） | as-of 2026-09-28
    'g2_lam': 0.02,
    # 覆铜板腿 M 倍数：Gordon：r 13%、g 2%、ROIC 16.94%（= 21.17% × 0.8） | as-of 2026-09-28
    # 1888 自持证券 + 债券（十亿港元）：1888 中报：流动 2,407 + 非流动 547 + 债券 256 百万 | as-of 2026-06-30
    'kl_sec': 3.210,
    # 1888 投资物业：1888 中报 | as-of 2026-06-30
    'kl_ip': 1.230,
    # 1888 净借款：1888 中报：借款 6,486 + 1,228 − 现金 2,196 百万 | as-of 2026-06-30
    'kl_netdebt': 5.518,
    # 1888 应付股息：1888 中报 | as-of 2026-06-30
    'kl_divpay': 1.671,
    # 母公司层待开发物业：中报 11,030 − 1888 110 百万 | as-of 2026-06-30
    'pud': 10.920,
    # 母公司层证券 + 债券：中报 18,861 + 2,089 + 1,773 − 1888 3,211 百万 | as-of 2026-06-30
    'sec_hold': 19.511,
    # 合营 + 联营账面：中报 2,426 + 456 百万 | as-of 2026-06-30
    'jv': 2.882,
    # 母公司层净借款：中报借款 30,854 − 1888 7,714；现金 11,334 − 1888 2,196（百万） | as-of 2026-06-30
    'hold_netdebt': 14.002,
    # 母公司已宣派未付 FY2025 末期 + 特别息：中报应付股息 2,313 − 1888 应付 1,671 × 38.31% 少数股东份额（百万）；2026-07-08 支付 | as-of 2026-06-30
    'divpay': 1.673,
    # 母公司层年度总部费用：中报未分配企业费用 226.7 − 1888 51.2 百万，× 2 | as-of 2026-06-30
    'hq_cost': 0.351,
    # 证券 / 合营联营折价 L：A7 | as-of 2026-09-28
    'd_sec_l': 0.40,
    # 同上 M：A7 | as-of 2026-09-28
    'd_sec_m': 0.30,
    # 同上 H：A7 | as-of 2026-09-28
    'd_sec_h': 0.20,
    # 待开发物业 / 1888 投资物业折价 L：A7 | as-of 2026-09-28
    'd_prop_l': 0.50,
    # 同上 M：A7 | as-of 2026-09-28
    'd_prop_m': 0.40,
    # 同上 H：A7 | as-of 2026-09-28
    'd_prop_h': 0.30,
    # 实付派息率：FY2025 每股派息 2.20 / 报告每股收益 3.971 | as-of 2025-12-31
    'payout_obs': 0.554,
    # D 桶窗口年数：2026Q4–FY2028（A12） | as-of 2026-09-28
    'window': 2.25,
    # 视同派出打折 L：D 桶去向具名（来源层级 ②） | as-of 2026-09-28
    'k_l': 0,
    # 视同派出打折 M：同上 | as-of 2026-09-28
    'k_m': 0,
    # 视同派出打折 H：已去掉——原 ①b \(1-V_M/V_H\) = 0.3073 乘的是多留部分，不是具名交易（A12） | as-of 2026-10-16
    'k_h': 0,
    # 1888 AI 布毛利占比 FY2028E（花旗 2026-07-04，Wisburg 94820；单家卖方量，A9） | as-of 2026-07-04
    'gf_citi_share': 0.174,
    # 1888 净利 ÷ 毛利（2026H1 实测：净利 28.9 亿 ÷ 毛利 45.8 亿 = 收入 149.0 亿 × 30.73%；Longbridge 中报）；用于把花旗 FY2028 净利折回毛利 | as-of 2026-06-30
    'np_gp_kl': 0.631,
    # 特种纱窑炉总数（现有 5 座 + 清远在建 8 座；1888 中报「展望」） | as-of 2026-06-30
    'gf_kilns_total': 13,
    # 不在底牌里的窑炉：13 − 2025 年底前已投产的 2 座（2026H1 新增 3 座各 500 吨，1888 中报） | as-of 2026-06-30
    'gf_kilns_new': 11,
    # 清远在建 8 座（2 座 2026H2、其余 2027 投产）：资本按全部未投计（保守，A9） | as-of 2026-06-30
    'gf_kilns_unspent': 8,
    # 每座特种纱窑年产能（吨）：2026H1 新增三座「年产各 500 吨」（1888 中报） | as-of 2026-06-30
    'gf_t_per_kiln': 500,
    # 满产折扣：新窑良率爬坡 + 英伟达认证（花旗预期 2027 年中）未落地，−20%（拍值；±10pp 敏感） | as-of 2026-10-05
    'gf_yield': 0.80,
    # 兑现年 FY2028（花旗量的年份；清远 8 座 2027H1 前投产）− 分子年 FY2026 | as-of 2026-10-05
    'gf_years': 2,
    # 清远 RTF / HVLP 铜箔年产能（吨），「筹建中」、2027Q3 投产（1888 中报「展望」）；资本按全部未投计 | as-of 2026-06-30
    'cu_tons': 21000,
    # 满产折扣 = HVLP3 良率：`_AXIS.hvlp-copper-foil` | as-of 2026-06-10
    # 兑现年 FY2029（2027Q3 投产 + 约 1.5 年爬坡与逐代认证；无具名满产年·拍值）− 分子年 FY2026 | as-of 2026-10-05
    'cu_years': 3,
    # 特种布腿高回报期（短缺利润率与回报）开始回落年 = 兑现年 FY2028 = 特种布短缺可见止点（花旗量与宏和卖方利润率都到 2028；日东纺 T 玻纤 3 倍扩产到 FY2029），不继承母腿普通电子布 2027→2029（A9） | as-of 2026-10-19
    'gf_y1': 2028,
    # 特种布腿回落到常态年 = Y1 + 6（进入门槛「高」：供应商少、客户认证长、石英 / 低介电布扩产周期长，A9） | as-of 2026-10-16
    'gf_y2': 2034,
    # 特种布腿稳态回报 = 按序取第一层自身周期：覆铜板分部最近一轮完整谷到谷 FY2019（15.0%）→ FY2023（9.8%）分部业绩 ÷ 年初分部净资产均值 22.26% × (1 − 20%) = 17.81%（2026-10-19 改，取代「max(兜底 15%, 日东纺 9.4%, 九年中枢 16.94%)」；同业与兜底只作对照）；同一公司内部一致：玻纤布在覆铜板分部里，与主业 H 档回落到同一个常态；用户 2026-10-19 认可（A9） | as-of 2026-10-19
    # HVLP 铜箔腿高回报期开始回落年 = 第三代 HVLP 短缺可见止点 2028（东吴 2026-06-10「2027–28 年仍有缺口」）；建滔 2029 满产时已在回落路径上（第 1 / 4 年），不取兑现年 2029；用户 2026-10-19 认可（A9） | as-of 2026-10-19
    'cu_y1': 2028,
    # HVLP 铜箔腿回落到常态年 = Y1 + 4（进入门槛「中」，A9） | as-of 2026-10-19
    'cu_y2': 2032,
    # HVLP 铜箔腿稳态回报 = 同 `rs_gf`：覆铜板分部 FY2019–23 谷到谷 17.81%（铜箔在覆铜板分部里，产品升级、生意模式没变；金居 14.5% 与兜底 15% 只作对照）；eval 校验三者（`rs_gf` / `rs_cu` / `rs_lam_h`）= 分部表复算；用户 2026-10-19 认可（A9） | as-of 2026-10-19
    # HVLP 每吨净利 L（万元）：`_AXIS.hvlp-copper-foil` | as-of 2026-06-10
    # HVLP 每吨净利 M：`_AXIS.hvlp-copper-foil` | as-of 2026-06-10
    # HVLP 每吨净利 H：`_AXIS.hvlp-copper-foil` | as-of 2026-06-10
    # 每吨年产能投资（万元）：`_AXIS.hvlp-copper-foil` | as-of 2026-06-10
    # CNY→HKD 市场交叉汇率（USDHKD 7.8400 ÷ USDCNY 6.7190，yfinance 2026-09-04；与 `0189.HK` 同源） | as-of 2026-09-04
    'fx_cny_hkd': 1.1668,
    # 特种布单价 L（元 / 米）：`_AXIS.ai-glass-fabric` | as-of 2026-08-14
    # 特种布单价 M：`_AXIS.ai-glass-fabric` | as-of 2026-08-14
    # 特种布单价 H：`_AXIS.ai-glass-fabric` | as-of 2026-08-14
    # 特种布净利率 L：`_AXIS.ai-glass-fabric` | as-of 2026-03-27
    # 特种布净利率 M：`_AXIS.ai-glass-fabric` | as-of 2026-08-21
    # 特种布净利率 H：`_AXIS.ai-glass-fabric` | as-of 2026-08-21
    # 毛利 → 收入换算毛利率：`_AXIS.ai-glass-fabric` | as-of 2026-08-21
    # 每吨特种纱织布米数：`_AXIS.ai-glass-fabric` | as-of 2026-10-05
    # 每年米特种布产能投资（元）：`_AXIS.ai-glass-fabric` | as-of 2026-09-21
}

# Original historical financial rationale and evidence.
# - **业务地图摘要**：分部附注六块，覆铜板 / 线路板 / 化工三块收入各占 20% 以上，驱动完全不同（玻纤布短缺 / 加工费 / 烧碱周期 / 内地租金 / 港股行情），且三块经营腿落不同篮子（valuation-rules「归篮触发分腿」），故拆腿。证券投资分部的公允值变动（2025 +30.2 亿、2026H1 −5.5 亿）使合并 EPS 失真，证券单独按公允值 × (1 − d) 计价、不进任何腿的分子。
# - **属性 A · 全链自产与自身扩产**：玻纤纱 → 玻纤布 → 覆铜板，外加铜箔、环氧树脂、漂白木浆纸全部自产。2026H1 同业因缺布停产时建滔近满产，覆铜板出货 +14%（1888 中报）。但建滔自己在大幅扩产：织机 2025 年 3,333 台 → 2028 年 5,833 台，玻纤布总产能 10.5 亿米；7 万吨玻纤纱（2026-06 投产）、8 座特种纱窑（2026–2027）、韶关 9,500 万米 / 南沙 1.5 亿米 / 清远 7,800 万米玻纤布、清远 2.1 万吨 RTF / HVLP 铜箔（2027Q3）、萍乡覆铜板（2027 年中）。短缺会不会结束，建滔自己就是变量之一（A1）。
# - **属性 B · 集团内利润转移**：1888 卖给母公司全资线路板厂的覆铜板 2026H1 达 25.9 亿港元（1888 中报分部附注，成本加成定价）。覆铜板涨价时利润从 100% 持有的线路板挪到 61.69% 持有的 1888——2026H1 线路板 EBITDA 只 +1%，覆铜板 +172%；其中 38.31% 归 1888 少数股东。
# - **属性 C · 资本配置**：Hallgain（张氏家族）持 0148 的 31.75%（2026-09-09 关联交易公告）。2026 年母公司两次配售 1888 股份套现约 145 亿港元，同期银行借款由 228 亿增至 309 亿，证券组合由 116 亿增至 227 亿（中报「投资」段）。这是控股折价的主要理由之一，折价只放在证券 / 待开发物业 / 合营联营三项的 d 上（A7），不另对 1888 腿打控股折扣（该腿已只计 61.69% 归母、且用篮 6）。
# - **属性 D · 物业**：投资物业 269.8 亿（1888 持 12.3 亿），年租金约 13.6 亿（2026H1 679.8 百万 × 2）；待开发物业 110.3 亿（1888 持 1.1 亿），2025 年撇减 13.2 亿、投资物业公允值亏损 6.6 亿（年报分部附注 (c)）。
# - **属性 E · 派息**：常规股息 + 历年特别息；FY2025 每股 2.20（含特别 0.40）/ 报告每股收益 3.971 = 55.4%。
# - **\(V_{opt}\) 的理由（A9）**：AI 特种玻纤（低介电一代 / 二代、低 CTE、石英纱布）与 HVLP / RTF 铜箔没有可单独拆出的收入或利润（分部附注只有「覆铜板」一块；管理层只披露「玻纤纱及布业务 2026H1 利润约 10 亿、同比 +280%」，含传统品），算不出底牌分子 → 走 \(V_{opt}\)。按 2026-10-05「未建模期权」规则（未投产 / 不披露收入不得因此记 0）：份数取本票具名的量——特种布有花旗单家卖方量（AI 布毛利占比 2026 6.9% → 2028 17.4%）进 L / M，满产（11 座不在底牌的特种纱窑 × 500 吨 × 纱→布换算 × 轴单价 × 良率折扣）进 H 并与卖方量取大；铜箔无本票卖方量，只有清远 2.1 万吨产能进 H。单价与利润率取两条新建同业尺轴（`_AXIS.ai-glass-fabric`、`_AXIS.hvlp-copper-foil`）上的同业卖方读数，估值用本票覆铜板腿的尺（篮 6 13%、\(g_2\) 2%、ROE 分母只放本腿新增投资），扣未投资本。
# | A1 | **短缺是周期高点（point），不是新常态**。三档语义：L = 实测谷底 + 实测回升（point）；H = 共识路径后两年线性回落到中枢（point，回落年数锚 = 2017→2019 与 2021→2022 两次实测）；regime 读法（峰 / 谷按稳态倍数持续）只作对照价带与压力坐标。**证伪**：2027–2028 年行业新产能（含建滔织机 +75%）投产后，电子玻纤布价格仍在 2026H2 均价的 80% 以上且 1888 单月利润 ≥ 8 亿港元 → 主副互换（对照带升为主价带）。**转弱**：布价自高点回落 ≥ 20% 前均视为 active | active | 1888 中报「Prospects」段；0148 中报扩产表；历年分部附注 | `e_lam_26` `e_lam_27` `n_fade`；对照价带 |
# | A2 | **覆铜板中枢 = 2017–2025 分部回报均值 21.17% × 今日分部净资产**。资产基数已变（2016 年 140 亿 → 2025 年 178.9 亿），按 valuation-rules「中枢…资产基数变动时取 ROE 中枢」不取实测年份绝对值。取样窗口供给状态：2016–2017 铜箔短缺、2020–2021 全面短缺、2019 / 2022–2024 过剩，两种状态都在窗口内，无单向偏差；窗口内几乎无 AI 年份（仅 2025），见 A10 | active | 0148 年报 2016–2025 分部附注 (b) 分部资产 − 分部负债；年度业绩公告分部业绩 | `ret_lam_m` `na_lam` |
# | A3 | **线路板是加工费生意**：回报 2017–2025 在 4.7%–10.5%（均值 8.49%），税后 ROIC 3.7%–8.4% < r 10% − 3pp（M、L）或贴近（H）→ 倍数封顶 \(1/r\)；越南 / 泰国 / 开平扩产在历史回报下不增值。**转弱**：连续两个半年分部业绩 < 5 亿港元 | active | 分部附注；中报扩产表 | `ret_pcb_*` |
# | A4 | **化工跟烧碱周期**：分部业绩 2016–2025 取最低（2016 3.13 亿）/ 均值（12.66 亿）/ 最高（2021 39.76 亿）三点同源；中枢税后 ROIC 10.4% < 13% − 3pp → \(1/r\)；L 按 2016→2018 实测两年回升、H 按 2021→2023 实测两年回落 | active | 分部附注 | `chem_*` |
# | A5 | **出租物业租金约 13.6 亿 / 年**，NOI 率 80%（**假设，待补核实**：分部附注未拆租金成本），物业税 25%；税后 ROIC ≈ 3% < 13% → \(1/r\)、\(g=0\)。L = 租金 −10%，H = +2%。**转弱**：租金同比 −10% 或投资物业单年公允值亏损 > 5% | active | 中报「物业」段 | `rent_*` `noi_margin` |
# | A6 | **资本配置不再恶化**。**转弱**：母公司层净债 > 200 亿，或证券组合 > 300 亿，或以低于本框架 1888 每股 H 的价格继续配售 1888 | active | 中报；配售公告 2026-03-18 / 2026-06-17 | `hold_netdebt` `sec_hold` |
# | A7 | **折价**：证券与合营联营 d = 40% / 30% / 20%（口径同 `0700.HK` A4 投资组合 NAV 折价，对话设定）；待开发物业 d = 50% / 40% / 30%（2025 年已撇减 13.2 亿，住宅去化中，对话设定）；1888 自持证券 / 投资物业同档 d | active | `0700.HK` A4；年报分部附注 (c) | `d_sec_*` `d_prop_*` |
# | A8 | **控股权**：母公司持 1888 超过 50%（现 61.69%），1888 继续并表。**证伪**：持股降至 50% 以下 → 口径重做 | active | 中报「重大收购及出售」 | `stake_kl` |
# | A9 | **AI 特种玻纤布 + HVLP 铜箔 = 未建模期权，\(V_{opt}\) = 4.20，\(p\) = 0.617 / 0.840 / 1.0**（2026-10-05 按「未建模期权」未投产不记 0 条重做；2026-10-16 框架纠正按 valuation-rules「经营价值与超额现金」② 稳态回报三段改两条腿的倍数；2026-10-19 框架纠正改为利润率随回报一起回落到常态，见本条末「2026-10-19」段——下文 8.60 / 8.74 / 8.77×、8.83×、5.46 / 8.69 / 9.44、2.75、12.19 为 10-16 之前单段 Gordon 读数，8.13 / 8.20 / 8.21×、8.15×、5.06 / 8.03 / 11.20 为 10-16 读数）。**2026-10-16 稳态回报**（成熟同业判据：同一门生意、近 5 个完整财年即 5 个年度区间收入复合增速 ≤ 10% 且不为负、读数 ≥ 5 个完整财年；读数 = 期初权益口径的经营回报均值）：① **特种布腿——照常三段**。成熟同业：**日东纺**（3110.T，玻纤纱 / 电子级玻纤布，含低介电、低膨胀特种布，同一门生意）FY3/2021 → FY3/2026 收入 787 → 1,182 亿日元，复合 **+8.5%**，成熟；FY2017–26 十年 ROE 9.7 / 11.8 / 8.9 / 6.2 / 8.2 / 6.2 / 2.7 / 6.2 / 9.9 / 24.1%，均值约 **9.4%**（irbank 年度业绩，账面 ROE 口径；该公司净现金不大，扣超额现金后读数只略高）。宏和科技（603256.SH）按 5 个年度区间 FY2020 → 25 收入 6.21 → 11.71 亿，复合 +13.5%，**不成熟**（旧读法只用 4 个区间得 9.7%，按 valuation-rules 已撤）；中国巨石 5 个区间 +10.1%，不成熟。→ 前瞻 37–56% 持有到兑现年 2028，进入门槛「高」（供应商少、客户认证长、石英 / 低介电布扩产周期长）→ 6 年回落到 2034，稳态 = max(日东纺约 9.4%, 兜底「有壁垒重资产」15%, r 13%) = **15%** → 倍数 8.13 / 8.20 / 8.21×。② **HVLP 铜箔腿——不是叙事换代，照常三段**。叙事换代要两条同时成立，第 ② 条不成立：同一门生意有 ≥ 5 年读数的成熟同业——**金居**（8358.TWO，PCB 用电解铜箔，含 RTF / HVLP 高频高速铜箔）FY2020 → 25 收入约 60.4 → 78.8 亿新台币，复合 **+5.5%**，成熟（2020 全年 = 前 9 月累计 44.52 亿 + 4Q 15.85 亿，TechNews 月营收快讯 / Yahoo 股市季报；2025 = yfinance）；FY2019–25 七年 ROE 7.4 / 10.5 / 26.9 / 15.8 / 8.8 / 15.4 / 16.3%，均值约 **14.5%**（2019–22 取 stock.wearn.com 个股年度财报表的 ROE，第三方口径、待以公开资讯观测站年报核对；2023–25 = 归母净利 ÷ 期初权益，yfinance；净现金近 0，超额现金调整可忽略）。诺德、嘉元、铜冠铜箔 5 个区间复合 > 10%，不成熟；三井金属（铜箔只是其功能材料分部的一块）、古河电工不是同一门生意。→ 前瞻 70% 持有到兑现年 2029，进入门槛「中」（第 8 轮补充裁定）→ 4 年回落到 2033，稳态 = max(金居约 14.5%, 兜底「有壁垒重资产」15%, r 13%) = **15%** → 倍数 8.15×（叙事换代读法 8.48×、H 2.61 撤销）。若兜底改按「商品化重资产」11%，稳态取金居 14.5%，影响 < 0.05 / 股。（10-16 读法只改回报路径、单位经济长期持有，结果 5.06 / 8.03 / 11.20，已被 10-19 段取代。）**2026-10-19 框架纠正：利润率沿高回报期回落到常态（用户 2026-10-19 认可）**。原因：主业覆铜板的短缺利润 2027 年后两年回到中枢，期权却让特种布净利率 33 / 46.7 / 49.9%、HVLP 每吨净利 6 万元永续，只回落回报——在 \(g_2\) 2% 下回报回落几乎不动价格，价值实际落在「短缺利润永续」上；且期权稳态 15% 低于主业覆铜板自身周期 16.94%，新产品比老产品更悲观。改法：① **常态 = 同一公司内部一致**——稳态回报 15% → 16.94%（当日按 max(兜底, 同业, 九年中枢) 取）→ **17.81%**（同日稳态回报按序取：自身周期可用即取自身最近一轮完整谷到谷 FY2019（15.0%）→ FY2023（9.8%）分部业绩 ÷ 年初分部净资产均值 22.26% × (1 − 20%)；日东纺约 9.4% / 金居约 14.5% / 兜底 15% 只作对照；用户 2026-10-19 认可），即主业 H 档回落的终点（玻纤布、铜箔都在覆铜板分部里；主业 M / L 档受各自前瞻 = 九年中枢 16.94% 封顶）；常态利润 = 17.81% × 本项资本 → 特种布净利率约 **15.8%**（三档同）、HVLP 每吨净利约 **1.53 万元**。② **回落形状**：利润 × 线性因子（Y1 前 1，Y2 时 = 常态 ÷ 短缺读数），回报走同一条路径（valuation-rules「未建模期权」单位经济不阶跃）。③ **Y1 / Y2 按各自产品阶段**，不继承母腿普通电子布的 2027 → 2029：特种布 2028 → **2034**（不变；建滔 8 座特种纱窑 2026–2027 投产，花旗量与宏和卖方利润率都到 2028，日东纺 T 玻纤 3 倍扩产到 FY2029——短缺可见到 2028；门槛「高」回落 6 年；与主业 2 年回落的差别：普通电子布门槛低，历史两次实测 2 年回落）；HVLP 铜箔 2029 → 2033 改 **2028 → 2032**（东吴 2026-06-10「2027–28 年仍有缺口」是第三代 HVLP 短缺的可见止点；建滔清远 2027Q3 投产、2029 满产时第三代已过短缺期，前沿转向 HVLP4、建滔尚在争取认证 → Y1 取 HVLP3 环节止点 2028，不取建滔兑现年 2029；兑现年 2029 已在回落路径第 1 / 4 年，不是阶跃；门槛「中」回落 4 年）。**常态交叉（只披露，不进数）**：特种布常态 15.8% vs 日东纺营业利润率 FY3/23–26 5.6 / 9.0 / 15.1 / 17.6%（均约 **11.8%**；FY3/26 净利率 35.3% 含一次性收益不用）、宏和科技净利率 FY2022–25 8.6 / −9.5 / 2.7 / 17.2%（yfinance）——自身中枢高于同业实测，偏乐观方向，不是悲观；铜箔常态每吨 1.53 万元落在轴 §3「过剩时回落到 RTF 级约 0.5–2 万」与 HVLP1 1–2 万之内，金居净利率 FY2022–25 13.1 / 8.6 / 13.5 / 13.5%（无吨数，不能换算每吨）。**结果**每股 L / M / H 特种布 2.59 / 3.53 / 3.75（兑现年倍数 5.25 / 4.48 / 4.36×，对短缺年利润）+ 铜箔 0 / 0 / 0.45（2.98×）= **2.59 / 3.53 / 4.20**；倍数低于 \(1/r\) 7.69× 是因为分子是短缺年利润、常态只有其 1/3–1/4。底牌 L / M / H 不变（期权不进底牌）。**敏感**（\(V_H\)）：铜箔保留 2029 → 2033 → 4.42；稳态取九年中枢 16.94% → 4.03；稳态 15% → 3.66；特种布门槛改「中」2028 → 2032 → 3.64；两项都按主业 2 年回落 2028 → 2030 → 2.77；按 ai-capex 默认 2030 → 2035 → 5.55。**价值靠什么撑**：短缺读数仍是单家卖方（花旗量、宏和 / 菲利华利润率、东吴每吨利润），常态取自身中枢（本票 9 年分部数据），高于同业实测、方向偏宽。**① 特种布**——份数：L / M = 花旗单家（2026-07-04）FY2028E AI 布毛利占比 17.4% × 花旗 FY2028 1888 净利 172.7 亿 ÷ 1888 实测净利 / 毛利 0.631 = AI 布毛利 47.6 亿 → ÷ 轴毛利率 67% = 收入 71.1 亿港元 → × 11 / 13（扣掉 2025 年底前已投产、已在覆铜板分部净资产里的 2 座窑）= **60.1 亿**；H = 满产与卖方量取大：11 座窑 × 500 吨 × 16,700 米 / 吨 × 良率折扣 0.80 × 轴单价 H 40 元 / 米 × 1.1668 = 34.3 亿 < 60.1 亿 → H 仍取花旗量（花旗的量隐含新产能平均约 70 元 / 米，即以二代 / 低膨胀 / 石英为主的产品结构；轴单价是一代口径，**待核**）。单位经济：轴净利率 L 33.0%（菲利华 FY2027E）/ M 46.7%（宏和 FY2028E 两家均值）/ H 49.9%（宏和最高家）→ 净利 19.8 / 28.1 / 30.0 亿。资本：11 座窑对应 9,185 万米 × 49.9 元 / 米 × 1.1668 = 53.5 亿（ROE 37% / 53% / 56%，Gordon r 13%、g 2% → 8.60 / 8.74 / 8.77×）；清远 8 座按全部未投计（保守），折一年扣 34.4 亿。兑现 FY2028，折回两年。1888 层 99.3 / 157.9 / 171.6 亿 × 61.69% ÷ 11.2178 亿股 = **5.46 / 8.69 / 9.44**。**② HVLP 铜箔**——无本票卖方吨数（摩根大通只说量产 HVLP1–3、争取 HVLP4；花旗只给全部铜箔每月约 9,000 吨与 2.3–2.5 亿港元净利）→ L / M = 0；H = 2.1 万吨 × 良率 70% × HVLP3 每吨净利 6 万元 × 1.1668 = 10.3 亿港元，资本 2.1 万吨 × 6 万元 = 14.7 亿港元（ROE 70%，8.83×），兑现 FY2029（2027Q3 投产 + 爬坡认证，拍值）折回三年、扣全部未投资本（折一年 13.0 亿）→ 1888 层 50.0 亿 → **2.75**。**合计** 5.46 / 8.69 / 12.19；\(p_k=V_k/V_H\)。**重叠**：底牌 H 的 2026–27 共识路径已含特种布利润，期权从 FY2028 起算、不重叠；FY2028–29 回落年里若有特种布超额，偏高方向。**双计防线**：清远窑与铜箔是 A12 的 D 桶资本开支，未投部分在期权里全额扣减。**敏感**：特种布良率折扣 ±10pp 不改 H（卖方量胜）；HVLP 每吨净利取 HVLP2 3.5 万 → 铜箔 H 2.75 → 1.26，\(V_{opt}\) 12.19 → 10.70。**升级 / 证伪**：公司或 ≥2 家卖方披露特种布或 HVLP 收入 / 吨数 → 改用多家路径；第二家卖方给出二代 / 石英布单价预测 → 轴分代际单价、H 按产品结构重算；1888 获英伟达认证（花旗预期 2027 年中）落空，或一代低介电布价跌回 25 元 / 米以下 → 期权 M 改按 L 利润率复核 | active | 花旗 2026-07-04（Wisburg 94820）；摩根大通 2026-09-23（Wisburg 106700）；1888 2026 中报「展望」（13 座特种纱窑、每座 500 吨、清远 2.1 万吨铜箔 2027Q3）；`_AXIS.ai-glass-fabric`；`_AXIS.hvlp-copper-foil` | \(V_{opt}\)；`gf_*` `cu_*` 与两条轴的行 |
# | A10 | **候选带「AI 短缺延长」**：短缺持续到建滔织机 2028 年扩至 5,833 台，H 路径加花旗单家 FY2028（三年利润 CAGR 92% → 1888 净利约 172.7 亿），其后两年回落；L′ = L、M′ = M。花旗原文「预计截至 2028 年的三年盈利 CAGR 为 92%」是卖方对整体盈利的**基准**预测，不由产能 / 合同折算，判为**增长型**（construction §7h）→ 换成花旗自己的 FY27→FY28 增速 172.7 ÷ 130.5 − 1 = **+32.4%**（花旗 FY2027 = EPS 4.14 × 股数），乘在 H 路径的 FY2027 121.2 亿上 → H′ 的 FY2028 = 160.4 亿，不直接用 172.7 亿这个水平（H 路径的 FY2027 是摩根大通 / 花旗均值，比花旗自己低约 9 亿，直接接 172.7 亿等于把两家的口径差算成一年增长）。基年核对：三年 = FY2025 → FY2028，FY2025 1888 净利 24.42 亿（yfinance / Longbridge）× 1.92³ = 172.7 亿；花旗的 PEG 0.3 = 29× ÷ 92 也对得上。CAGR 只定两端、不要求逐年等速——花旗 FY2027 130.5 亿与 FY2028 172.7 亿同一路径自洽（前高后低：FY26 共识约 83 亿、FY27 +57%、FY28 +32%），按等速倒推的 FY2027 约 90 亿、FY2026 约 47 亿反而低于 2026H1 实测 28.9 亿的年化，不是花旗的路径。**升级门槛**（任一）：① 韶关 9,500 万米（2026Q3）与南沙 1.5 亿米（2027Q3）两项玻纤布投产后的两个季度，电子玻纤布均价 ≥ 2026H2 均价的 90%；② FY2027 覆铜板分部业绩 / 年初分部净资产 ≥ 40%。**删除**：玻纤布价格自高点回落 ≥ 20%（同时 A1 → confirmed） | active | 花旗 2026-07-04（Wisburg 94820） | `e_lam_28c`；候选带 |
# | A11 | **归篮**：覆铜板腿 → 篮 6（盈利是玻纤布 / 铜箔 / 覆铜板价格的函数：母公司 EPS 2021 年 9.73、2023 年 1.86）；线路板 → 篮 4（加工费、原料涨价可转嫁、客户分散，不是商品价函数）；化工 → 篮 6（烧碱等大宗化工）；出租物业 → 篮 6（内地商业物业，免租期与减值未止，不明朗）；总部费用资本化 → 篮 4（与集团经营同级）。CAPM 粗筛：0148 对恒指 5 年周 β 0.77（2025 年前 1.00），\(r_f\) 4.0% + β × 5.5% + 港股 1% = 9.2%–10.5%，比篮 6 低 2.5–3.8pp；扣 HKD 段中位偏移约 −3pp 后残差 ≤ 1pp，不进篮子质疑清单 | active | 篮子归属决策（本日对话）；Longbridge 周线 2021-09 至 2026-09 | `r_lam` `r_pcb` `r_chem` `r_prop` `r_hq` |
# | A12 | **留存去向审计 = D 桶（增长窗口）**：FY2025 资本增添 41.8 亿 vs 折旧 23.2 亿；物业厂房设备 2021 年 174 亿 → 2025 年 248 亿 → 2026-06 245 亿（中报口径）；扩产项目有名称有投产日，窗口终点 FY2028。三条经营腿按全派出（\(g=0\)）计，实付派息 55.4%，超额留存按「视同派出」行处理：\(k_L=k_M=k_H=0\)。**2026-10-16 框架纠正去掉 \(k_H\)**：原 \(k_H\) = ①b 顶部折价 \(1-V_M/V_H\)（k 前）= 0.3073 乘在 H 档「视同派出」9.04 元/股上（扣 2.78），乘的是多留部分，不是具名交易；按 valuation-rules「经营价值与超额现金」④，多留部分由超额现金 × λ 承担（λ = 1），k 只剩具名交易（D 桶项目已在期权里扣未投资本）→ 去掉，H 回到 k 前 52.04（2026-10-19 H 档尾段稳态改 17.81% 后 52.10）。窗口 2.25 年（2026Q4–FY2028）。**经营价值与超额现金其余读数**：母公司层与 1888 层都是净债，超额现金 0、不单列，归母份额不涉及；时点对齐不适用——M 是跨周期中枢、L 是实测谷底 + 回升，H 的共识路径从 FY2026 起（分子年已开始，τ 取 0，窗口为空）；覆铜板腿稳态（2026-10-19 按序取）= 自身最近一轮完整谷到谷 FY2019–23 税后 **17.81%**（同业层为空：台光、生益、联茂、揖斐电近年高增长不成熟）；M / L 档的前瞻就是九年中枢 16.94%（A2 定稿取法），封顶后不动；H 档短缺两年回落到中枢后，新投资回报取 17.81%（倍数尾段 8.017 → 8.070×，H 52.04 → 52.10）；三档各取各的稳态（retention）：高档的卖方路径本身在 2027 年后两年回落到中枢（A1「短缺是周期高点」），去周期后的高档前瞻就是中枢利润 × 自身周期回报，预测里没有超出中枢的竞争力提升，取按序值；其余腿回报 < r 封顶 1/r | active | 年报分部附注 (c) 资本增添 / 折旧；中报；valuation-rules「经营价值与超额现金」 | `k_*` `payout_obs` `window` |
# | A13 | **杠杆门未触发**：FY2025 净债（借款 227.8 亿 − 现金 34.7 亿）/ EBITDA 95.5 亿 = 2.0；利息 8.03 亿 / EBIT 71.7 亿 = 11% | active | 年度业绩公告 | — |
# | A14 | **③ 自身实测带：不可判定**。与 M 档每股中枢收益（约 3.9）± 12% 同量级的 TTM 月份只有 2021-04 至 2021-08（5 个月，< 6），且当时市场看到 FY2021 暴增（带失真）；2026 年的同量级月份处在狂热期（2026-05 月内 57.8–151.8），同样失真。尺子留在初分篮，披露 | active | Longbridge 月线；历年年报每股收益 | Outputs 披露行 |

LISTING_CCY = "HKD"
TOL = 0.05
RET_TOL = 0.0005  # returns are stated to 4 decimals

# Segment results and segment net assets (segment assets - segment liabilities),
# HK$ million, from the 0148 annual reports' note "Segment information" (b).
# Results: FY2016-2025; net assets: year-ends 2016-2024 (opening base for 2017-2025).
HIST_RESULT = {  # year: (laminates, PCBs, chemicals)
    2016: (2465, 378, 313), 2017: (3953, 693, 966), 2018: (2937, 474, 1378),
    2019: (2185, 487, 735), 2020: (3313, 1066, 1157), 2021: (8320, 1057, 3976),
    2022: (2307, 1059, 2465), 2023: (1572, 1316, 606), 2024: (2105, 1360, 595),
    2025: (2837, 1396, 468),
}
HIST_NET_ASSETS = {
    2016: (14001, 8497, 5679), 2017: (15545, 8857, 6103), 2018: (14528, 10395, 5593),
    2019: (13464, 11059, 5135), 2020: (16612, 11309, 2752), 2021: (19576, 13056, 2680),
    2022: (16026, 12835, 3431), 2023: (15395, 12949, 5727), 2024: (15412, 13478, 8522),
}
RET_YEARS = range(2017, 2026)

REQUIRED = [
    "shares", "stake_kl", "tax", "tax_prop",
    "na_lam", "na_pcb", "na_chem", "ip_hold",
    "ret_lam_l", "ret_lam_m", "g1_lam_rec", "n_rec", "e_lam_26", "e_lam_27", "e_lam_27c", "e_lam_28c", "n_fade", "rs_lam_h",
    "ret_pcb_l", "ret_pcb_m", "ret_pcb_h",
    "chem_l", "chem_m", "chem_h",
    "rent_l", "rent_m", "rent_h", "noi_margin",
    "r_lam", "r_pcb", "r_chem", "r_prop", "r_hq", "g2_lam", "pe_lam_m",
    "kl_sec", "kl_ip", "kl_netdebt", "kl_divpay",
    "pud", "sec_hold", "jv", "hold_netdebt", "divpay", "hq_cost",
    "d_sec_l", "d_sec_m", "d_sec_h", "d_prop_l", "d_prop_m", "d_prop_h",
    "payout_obs", "window", "k_l", "k_m", "k_h",
]


# Rows the framework copies from its peer-ruler axes (contracts.md「同业尺轴」): one source per field.
AXIS_ROWS = {
    "ai-glass-fabric": ["px_ai_gf_l", "px_ai_gf_m", "px_ai_gf_h", "nm_ai_gf_l", "nm_ai_gf_m", "nm_ai_gf_h",
                        "gm_ai_gf_ref", "m_per_t_ai_gf", "capex_per_m_ai_gf"],
    "hvlp-copper-foil": ["pt_hvlp_l", "pt_hvlp_m", "pt_hvlp_h", "capex_per_t_hvlp"],
}
OPT_REQUIRED = [
    "gf_citi_share", "np_gp_kl", "gf_kilns_total", "gf_kilns_new", "gf_kilns_unspent", "gf_t_per_kiln",
    "gf_yield", "gf_years", "cu_tons", "cu_yield", "cu_years", "fx_cny_hkd",
    "gf_y1", "gf_y2", "rs_gf", "cu_y1", "cu_y2", "rs_cu",
] +[k for ks in AXIS_ROWS.values() for k in ks]
OPT_NUM_YEAR = 2026  # numerator year FY2026; realisation year = OPT_NUM_YEAR + gf_years / cu_years


def lin(cal: int, y1: int, y2: int, end: float) -> float:
    """1 through calendar Y1, linear to `end` by Y2, `end` after."""
    if cal <= y1:
        return 1.0
    if cal >= y2:
        return end
    return 1.0 + (end - 1.0) * (cal - y1) / (y2 - y1)


def path_pe(g2: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float) -> float:
    """Three-stage return path Gordon (library function not built yet): the forward return holds to
    calendar Y1, falls linearly to the steady return by Y2, steady after; per unit of t0 earnings.
    The unit economics fade on the same path (options.md「未建模期权」, user 2026-10-19): earnings
    x lin(cal, Y1, Y2, rs/roe), i.e. the shortage margin falls to the normal margin = steady return
    x the leg's own capital by Y2, not held forever."""
    rs = min(roe, r_s)
    end = rs / roe
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        f = lin(cal, y1, y2, end)
        if cal > y1 and cal >= y2:
            return pv + e * f * min(1.0, 1.0 - g2 / rs) / ((r - g2) * (1.0 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (rs - roe) * (cal - y1) / (y2 - y1)
        pv += e * f * min(1.0, 1.0 - g2 / ro) / (1.0 + r) ** t
        e *= 1.0 + g2
        t += 1


def option_values(inp: dict[str, float]) -> dict:
    """V_opt per tier, HK$ per 0148 share (A9; valuation-rules「未建模期权」2026-10-05).

    Size: L / M = the ticker's own sell-side quantity (Citi's AI-cloth gross-profit share of
    its FY2028 KLHL forecast, gross profit -> revenue at the axis gross margin, scaled to the
    kilns not already in the base); H = the larger of that path and full capacity
    (new kilns x tons x m/t x yield x axis price).  HVLP has no own sell-side quantity:
    L / M = 0, H = capacity tons x yield x axis profit per ton.
    Value: the ticker's ruler -- laminate leg r (basket 6) and g2, ROE on the leg's own
    capital (capacity x axis capex), 1/r below r - 3pp; valued in the realisation year,
    discounted to the numerator year, minus the capital not yet spent (one year out),
    x stake / shares.  Net margins / per-ton profits on the axes are after tax.
    """
    r, g2, fx = inp["r_lam"], inp["g2_lam"], inp["fx_cny_hkd"]
    keep = inp["gf_kilns_new"] / inp["gf_kilns_total"]
    gp28 = inp["e_lam_28c"] / inp["np_gp_kl"]
    citi_rev = inp["gf_citi_share"] * gp28 / inp["gm_ai_gf_ref"] * keep
    cap_m = inp["gf_kilns_new"] * inp["gf_t_per_kiln"] * inp["m_per_t_ai_gf"]  # metres / yr
    k_gf = cap_m * inp["capex_per_m_ai_gf"] * fx / 1e9
    k_cu = inp["cu_tons"] * inp["capex_per_t_hvlp"] * 1e4 * fx / 1e9

    def leg(np_: float, k: float, years: float, unspent: float, rev: float, kind: str) -> dict[str, float]:
        if np_ <= 0:
            return {"rev": rev, "np": 0.0, "k": k, "roe": 0.0, "pe": 0.0, "value": 0.0,
                    "years": years, "unspent": 0.0, "v1888": 0.0, "ps": 0.0}
        roe = np_ / k
        if roe <= r - 0.03:
            pe = 1.0 / r
        elif kind == "gf":
            # Three-stage return path (valuation-rules「经营价值与超额现金」② 稳态回报三段): >= 5-year
            # mature same-business peers exist (日东纺 3110.T, 宏和科技), so the leg fades from its forward
            # return and margin to the steady return rs_gf over gf_y1 -> gf_y2 (high entry barrier:
            # 6 years); valued from the realisation year, A9.
            pe = path_pe(g2, roe, r, OPT_NUM_YEAR + int(years), int(inp["gf_y1"]), int(inp["gf_y2"]),
                         max(inp["rs_gf"], r))
        else:
            # HVLP copper foil: a >= 5-year mature same-business peer exists (金居 8358.TWO, PCB copper
            # foil incl. RTF / HVLP) -> not 叙事换代; valued from the realisation year (2029), the
            # shortage window is the HVLP3 stage's (cu_y1 2028), medium barrier 4 years to cu_y2, A9.
            pe = path_pe(g2, roe, r, OPT_NUM_YEAR + int(years), int(inp["cu_y1"]), int(inp["cu_y2"]),
                         max(inp["rs_cu"], r))
        value = np_ * pe
        unspent_pv = unspent / (1 + r)
        v = value / (1 + r) ** years - unspent_pv
        return {"rev": rev, "np": np_, "k": k, "roe": roe, "pe": pe, "value": value, "years": years,
                "unspent": unspent_pv, "v1888": v, "ps": v * inp["stake_kl"] / inp["shares"]}

    out: dict = {}
    unspent_gf = k_gf * inp["gf_kilns_unspent"] / inp["gf_kilns_new"]
    for x in "lmh":
        rev = citi_rev
        if x == "h":
            cap_rev = cap_m * inp["gf_yield"] * inp["px_ai_gf_h"] * fx / 1e9
            out["cap_rev_h"], out["citi_rev"] = cap_rev, citi_rev
            out["citi_px"] = citi_rev / (cap_m * inp["gf_yield"] * fx / 1e9)
            rev = max(cap_rev, citi_rev)
        gf = leg(rev * inp[f"nm_ai_gf_{x}"], k_gf, inp["gf_years"], unspent_gf, rev, "gf")
        cu_np = inp["cu_tons"] * inp["cu_yield"] * inp[f"pt_hvlp_{x}"] * 1e4 * fx / 1e9 if x == "h" else 0.0
        cu = leg(cu_np, k_cu, inp["cu_years"], k_cu, 0.0, "cu")
        out[x] = {"gf": gf, "cu": cu, "total": gf["ps"] + cu["ps"]}
    return out


def seg_returns(i: int) -> list[float]:
    """Segment result / opening segment net assets for leg i, FY2017-2025."""
    return [HIST_RESULT[y][i] / HIST_NET_ASSETS[y - 1][i] for y in RET_YEARS]


def derived_history(inp):
    lam, pcb = seg_returns(0), seg_returns(1)
    chem = [HIST_RESULT[y][2] / 1000 for y in range(2016,2026)]
    data = {'ret_lam_m':round(sum(lam)/len(lam),4),
            'ret_lam_l':round(HIST_RESULT[2023][0]/HIST_NET_ASSETS[2022][0],4),
            'ret_pcb_l':round(min(pcb),4), 'ret_pcb_m':round(sum(pcb)/len(pcb),4),
            'ret_pcb_h':round(max(pcb),4),
            'g1_lam_rec':round((HIST_RESULT[2025][0]/HIST_RESULT[2023][0])**.5-1,4),
            'chem_l':round(min(chem),4),'chem_m':round(sum(chem)/len(chem),4),'chem_h':round(max(chem),4)}
    steady = round(sum(HIST_RESULT[y][0]/HIST_NET_ASSETS[y-1][0] for y in range(2019,2024))/5*(1-inp['tax']),4)
    data.update(rs_lam_h=steady,rs_gf=steady,rs_cu=steady)
    data['pe_lam_m'] = round(perpetual_pe(inp['g2_lam'],data['ret_lam_m']*(1-inp['tax']),inp['r_lam']),3)
    return data


def finite_data(value):
    if value is None or isinstance(value,str):
        return True
    if isinstance(value,dict):
        return all(finite_data(v) for v in value.values())
    if isinstance(value,(tuple,list)):
        return all(finite_data(v) for v in value)
    return isinstance(value,(int,float)) and math.isfinite(value)


def evaluate(inp: dict[str, float], rate_inputs=None) -> dict:
    inp = dict(inp)  # sensitivity readings must not mutate caller's inputs
    errors = check_missing(inp, REQUIRED + OPT_REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))
    require_whole_years(inp, ('n_rec','n_fade'))

    t, tp = inp["tax"], inp["tax_prop"]

    # --- baskets and g caps -------------------------------------------------
    baskets = {"r_lam": 6, "r_pcb": 4, "r_chem": 6, "r_prop": 6, "r_hq": 4}
    r_keys = ("r_lam", "r_pcb", "r_chem", "r_prop", "r_hq")
    for k in r_keys:
        if k not in baskets:
            errors.append(f"{k}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[k], k, baskets.get(k))
    errors += check_g_cap(inp["g2_lam"], inp["r_lam"], "g2_lam")

    # --- same-source: the returns are the segment tables, not a pick ---------
    lam_ret, pcb_ret = seg_returns(0), seg_returns(1)
    chem_res = [HIST_RESULT[y][2] / 1000 for y in range(2016, 2026)]
    same = {
        "ret_lam_m": sum(lam_ret) / len(lam_ret),
        "ret_lam_l": HIST_RESULT[2023][0] / HIST_NET_ASSETS[2022][0],
        "ret_pcb_l": min(pcb_ret),
        "ret_pcb_m": sum(pcb_ret) / len(pcb_ret),
        "ret_pcb_h": max(pcb_ret),
        "g1_lam_rec": (HIST_RESULT[2025][0] / HIST_RESULT[2023][0]) ** 0.5 - 1,
    }
    for k, v in same.items():
        if abs(inp[k] - v) > RET_TOL:
            errors.append(f"same-source: {k}={inp[k]} but the segment tables give {v:.4f}")
    for k, v in (("chem_l", min(chem_res)), ("chem_m", sum(chem_res) / len(chem_res)), ("chem_h", max(chem_res))):
        if abs(inp[k] - v) > 0.001:
            errors.append(f"same-source: {k}={inp[k]} but FY2016-2025 chemicals results give {v:.4f}")

    # --- leg earnings (HK$ bn, after tax) and domains ------------------------
    lam_mid = inp["na_lam"] * inp["ret_lam_m"] * (1 - t)
    roe_lam = lam_mid / inp["na_lam"]
    chem_mid = inp["chem_m"] * (1 - t)
    roe_chem = chem_mid / inp["na_chem"]

    def pe(g: float, roe: float, r: float) -> float:
        """Gordon multiple; peak-shaped domain (ROE <= r - 3pp) is capped at 1/r with g = 0."""
        return perpetual_pe(g, roe, r) if roe > r - 0.03 else 1.0 / r

    pe_lam = perpetual_pe(inp["g2_lam"], roe_lam, inp["r_lam"])
    if abs(pe_lam - inp["pe_lam_m"]) > TOL:
        errors.append(f"pe_lam_m={inp['pe_lam_m']} is not the Gordon multiple {pe_lam:.3f} of g2_lam at ROE {roe_lam:.4f}")
    if roe_lam < inp["r_lam"] + 0.03:
        errors.append(f"laminate mid ROIC {roe_lam:.4f} is not in the monotone domain the Formula claims")
    for name, roe, r in (("pcb", inp["ret_pcb_h"] * (1 - t), inp["r_pcb"]),
                         ("chem", roe_chem, inp["r_chem"]),
                         ("rent", inp["rent_h"] * inp["noi_margin"] * (1 - tp) / inp["ip_hold"], inp["r_prop"])):
        if roe > r:
            errors.append(f"{name}: ROIC {roe:.4f} > r {r} — the 1/r cap in the Formula no longer applies")

    def fade(path: list[float], mid: float, n: int, pe_mid: float, r: float) -> float:
        """Explicit path, then linear fade to mid over n years, tail at the mid multiple.
        Mirror of recovery_two_stage_pe: stage-1 payout 100%, tail valued at t = len+n-1."""
        es = list(path) + [path[-1] + (mid - path[-1]) * j / n for j in range(1, n)]
        pv = sum(e / (1 + r) ** (i + 1) for i, e in enumerate(es))
        return pv + mid * pe_mid / (1 + r) ** len(es)

    def lam_value(x: str, dr: float, h_path: list[float] | None = None) -> float:
        r = inp["r_lam"] + dr
        if x == "l":
            e_l = inp["na_lam"] * inp["ret_lam_l"] * (1 - t)
            return e_l * recovery_two_stage_pe(inp["g1_lam_rec"], int(inp["n_rec"]), inp["g2_lam"], roe_lam, r)
        if x == "m":
            return lam_mid * perpetual_pe(inp["g2_lam"], roe_lam, r)
        path = h_path or [inp["e_lam_26"], inp["e_lam_27"]]
        # H: after the shortage fades back to the mid earnings, new investment earns the laminate
        # own-cycle steady return (ordered pick, 2026-10-19), not the M forward (A2).
        return fade(path, lam_mid, int(inp["n_fade"]), perpetual_pe(inp["g2_lam"], inp["rs_lam_h"], r), r)

    def chem_value(x: str, dr: float) -> float:
        r = inp["r_chem"] + dr
        pe_mid = pe(0.0, roe_chem, r)
        if x == "l":
            e = inp["chem_l"] * (1 - t)
            g1 = (inp["chem_m"] / inp["chem_l"]) ** 0.5 - 1
            return e * recovery_two_stage_pe(g1, int(inp["n_rec"]), 0.0, roe_chem, r)
        if x == "m":
            return chem_mid * pe_mid
        return fade([inp["chem_h"] * (1 - t)], chem_mid, int(inp["n_fade"]), pe_mid, r)

    def tier(x: str, dr: float = 0.0, lam_v: float | None = None) -> dict[str, float]:
        d_sec, d_prop = inp[f"d_sec_{x}"], inp[f"d_prop_{x}"]
        lv = lam_value(x, dr) if lam_v is None else lam_v
        klhl = lv + inp["kl_sec"] * (1 - d_sec) + inp["kl_ip"] * (1 - d_prop) - inp["kl_netdebt"] - inp["kl_divpay"]
        legs = {
            "klhl": inp["stake_kl"] * klhl,
            "pcb": inp["na_pcb"] * inp[f"ret_pcb_{x}"] * (1 - t) / (inp["r_pcb"] + dr),
            "chem": chem_value(x, dr),
            "rent": inp[f"rent_{x}"] * inp["noi_margin"] * (1 - tp) / (inp["r_prop"] + dr),
            "pud": inp["pud"] * (1 - d_prop),
            "sec": inp["sec_hold"] * (1 - d_sec),
            "jv": inp["jv"] * (1 - d_sec),
            "debt": -inp["hold_netdebt"] - inp["divpay"] - inp["hq_cost"] * (1 - t) / (inp["r_hq"] + dr),
        }
        ps = {k: v / inp["shares"] for k, v in legs.items()}
        # Attributable after-tax earnings for the 視同派出 line (securities income and
        # holdco interest roughly offset and are left out; A12).
        e_lam1 = {"l": inp["na_lam"] * inp["ret_lam_l"] * (1 - t), "m": lam_mid, "h": inp["e_lam_26"]}[x]
        eps = (inp["stake_kl"] * e_lam1 + inp["na_pcb"] * inp[f"ret_pcb_{x}"] * (1 - t)
               + inp[f"chem_{x}"] * (1 - t) + inp[f"rent_{x}"] * inp["noi_margin"] * (1 - tp)
               - inp["hq_cost"] * (1 - t)) / inp["shares"]
        return {**ps, "klhl_eq": klhl, "pre_k": sum(ps.values()), "eps": eps}

    def excess(x: str, eps: float) -> float:
        """Retained-but-deemed-paid cash per share over the D-bucket window (A12)."""
        return (1 - inp["payout_obs"]) * eps * inp["window"]

    def anchors(dr: float = 0.0, h_path: list[float] | None = None) -> tuple[float, float, float]:
        out = []
        for x in "lmh":
            tv = tier(x, dr, lam_value(x, dr, h_path) if x == "h" else None)
            out.append(tv["pre_k"] - inp[f"k_{x}"] * excess(x, tv["eps"]))
        return tuple(out)

    tiers = {x: tier(x) for x in "lmh"}
    L, M, H = anchors()
    A, B = (L + M) / 2, (M + H) / 2
    if not L < M < H:
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")

    # --- k: cyclical ordering and the ①b top discount -------------------------
    if not inp["k_l"] <= inp["k_m"] <= inp["k_h"]:
        errors.append("k must satisfy k_l <= k_m <= k_h (valuation-rules「視同派出」)")
    # The ①b k sat on the 「多留部分」 (retained-but-deemed-paid cash), not on a named transaction;
    # removed 2026-10-16 (valuation-rules「经营价值与超额现金」④, λ = 1).  The ①b ratio is printed only.
    k_h_rule = 1 - tiers["m"]["pre_k"] / tiers["h"]["pre_k"]
    if any(inp[f"k_{x}"] != 0.0 for x in "lmh"):
        errors.append("k must be 0: no named transaction for a k to sit on (A12)")

    # --- flat-multiple ladder on the laminate numerators (A2e-2c) ------------
    e_lam = (inp["na_lam"] * inp["ret_lam_l"] * (1 - t), lam_mid, inp["e_lam_26"])
    if not e_lam[0] < e_lam[1] < e_lam[2]:
        errors.append(f"laminate numerators not a ladder: {e_lam}")
    flat = [tier(x, 0.0, e * inp["pe_lam_m"])["pre_k"] for x, e in zip("lmh", e_lam)]
    if not flat[0] < flat[1] < flat[2]:
        errors.append(f"flat-multiple ladder collapses: {flat}")

    # --- candidate band (A10): FY2028 single-source added to the H path ------
    # Citi's FY2028 is an ordinary base forecast (growth type, construction §7h): convert it to
    # Citi's own FY27 -> FY28 growth and apply that to the H path's FY2027, not the level itself.
    candidate = {'status':'unavailable','label':'花旗FY2028覆铜板预测','anchors':None}
    g1_cand = e_lam_28h = cand = None
    try:
        g1_cand = inp["e_lam_28c"] / inp["e_lam_27c"] - 1
        e_lam_28h = inp["e_lam_27"] * (1 + g1_cand)
        cand = anchors(0.0, [inp["e_lam_26"], inp["e_lam_27"], e_lam_28h])
        cand = (L, M, cand[2])
        if all(math.isfinite(v) for v in cand) and 0 <= cand[0] < cand[1] < cand[2]:
            candidate = {'label':'花旗FY2028覆铜板预测','anchors':dict(zip('LMH',cand))}
    except (ValueError,ZeroDivisionError,OverflowError):
        pass  # A missing or invalid candidate must not suppress the base.
    if candidate.get('status') == 'unavailable':
        g1_cand = e_lam_28h = cand = None
    # Same company, same normal (A9, user 2026-10-19): both options and the main leg's H tail fade to
    # the laminate leg's own cycle -- the latest full trough-to-trough FY2019 -> FY2023, after tax
    # (ordered pick, 2026-10-19; replaces max(floor, peers, nine-year mean)).
    own_steady = sum(HIST_RESULT[y][0] / HIST_NET_ASSETS[y - 1][0] for y in range(2019, 2024)) / 5 * (1 - inp["tax"])
    for k in ("rs_gf", "rs_cu", "rs_lam_h"):
        if abs(inp[k] - own_steady) > 5e-4:
            errors.append(f"{k} {inp[k]} != laminate own cycle FY2019-23 after tax {own_steady:.4f} (A2 / A9)")
    option = {'status':'unavailable','label':'玻纤布及铜箔','anchors':None}
    opt = v_l = v_m = v_h = p_rule = None
    try:
        if not all(math.isfinite(inp[k]) for k in (*OPT_REQUIRED,'e_lam_28c')):
            raise ValueError('option inputs must be finite')
        require_whole_years(inp,('gf_years','cu_years','gf_y1','gf_y2','cu_y1','cu_y2'))
        opt = option_values(inp)
        if not finite_data(opt):
            raise ValueError('option data must be finite')
        v_l,v_m,v_h = (opt[x]['total'] for x in 'lmh')
        option_band = (L+v_l,M+v_m,H+v_h)
        if (all(math.isfinite(v) for v in (v_l,v_m,v_h,*option_band))
                and 0 <= v_l <= v_m <= v_h and v_h > 0
                and 0 <= option_band[0] < option_band[1] < option_band[2]):
            p_rule = (v_l/v_h,v_m/v_h,1.0)
            option = {'value':v_h,'weights':dict(zip('LMH',p_rule)),
                      'anchors':dict(zip('LMH',option_band))}
    except (ValueError,ZeroDivisionError,OverflowError):
        opt = None  # Option-only calculations cannot invalidate base anchors.
    if option.get('status') == 'unavailable':
        opt = v_l = v_m = v_h = p_rule = None
    # --- regime comparison band (A1) -----------------------------------------
    r0 = inp["r_lam"]
    reg_l_lam = e_lam[0] * pe(inp["g2_lam"], e_lam[0] / inp["na_lam"], r0)
    reg_h_lam = inp["e_lam_26"] * perpetual_pe(inp["g2_lam"], inp["e_lam_26"] / inp["na_lam"], r0)
    reg = (tier("l", 0.0, reg_l_lam)["pre_k"] - inp["k_l"] * excess("l", tiers["l"]["eps"]),
           M,
           tier("h", 0.0, reg_h_lam)["pre_k"] - inp["k_h"] * excess("h", tiers["h"]["eps"]))

    if errors:
        raise ValueError('; '.join(errors))
    axis_data = {axis:{k:inp[k] for k in keys} for axis,keys in AXIS_ROWS.items()}
    rs_gf_eff, rs_cu_eff = max(inp['rs_gf'], inp['r_lam']), max(inp['rs_cu'], inp['r_lam'])
    cu_tons_out = inp['cu_tons'] * inp['cu_yield']
    cu_norm_pt = (rs_cu_eff * opt['h']['cu']['k'] * 1e9 / inp['fx_cny_hkd'] / cu_tons_out / 1e4
                  if opt is not None and cu_tons_out > 0 else None)
    sensitivity = {}
    for g in (inp['g2_lam']-.01, inp['g2_lam']+.01):
        saved, inp['g2_lam'] = inp['g2_lam'], g
        sensitivity[f'g_{g}'] = anchors()
        inp['g2_lam'] = saved
    saved = {x: inp[f'd_sec_{x}'] for x in 'lmh'}
    for x in 'lmh':
        inp[f'd_sec_{x}'] += .10
    sensitivity['d_sec_plus_10pp'] = anchors()
    for x in 'lmh':
        inp[f'd_sec_{x}'] = saved[x]
    saved, inp['noi_margin'] = inp['noi_margin'], .60
    sensitivity['noi_60'] = anchors()
    inp['noi_margin'] = saved
    def band_rf(dr):
        return anchors(dr)
    if any(abs(x-y) > TOL for x,y in zip(band_rf(0), (L,M,H))):
        raise ValueError('rate sensitivity base differs from anchors')
    result = {'ticker': '0148.HK', 'currency': 'HKD', 'valuation_as_of': None,
            'framework_as_of': None, 'historical_research_as_of': '2026-10-19', 'historical_framework_as_of':'2026-10-19',
            'anchors': dict(zip('LMH', (L,M,H))),
            'candidate': candidate, 'option': option,
            'review_flags':['historical_cash_and_segment_allocation_unverified',
                            'historical_glass_and_copper_capacity_unverified',
                            'historical_single_house_candidate'],
            'lam_ret': lam_ret, 'pcb_ret': pcb_ret, 'chem_res': chem_res, 'same': same,
            'lam_mid': lam_mid, 'roe_lam': roe_lam, 'chem_mid': chem_mid, 'roe_chem': roe_chem,
            'pe_lam': pe_lam, 'tiers': tiers, 'L': L, 'M': M, 'H': H, 'A': A, 'B': B,
            'k_h_rule': k_h_rule, 'e_lam': e_lam, 'flat': flat, 'g1_cand': g1_cand,
            'e_lam_28h': e_lam_28h, 'cand': cand, 'own_steady': own_steady, 'opt': opt,
            'v_l': v_l, 'v_m': v_m, 'v_h': v_h, 'p_rule': p_rule, 'r0': r0,
            'reg_l_lam': reg_l_lam, 'reg_h_lam': reg_h_lam, 'reg': reg,
            'rs_gf_eff': rs_gf_eff, 'rs_cu_eff': rs_cu_eff, 'cu_tons_out': cu_tons_out,
            'cu_norm_pt': cu_norm_pt, 'axis_data': axis_data, 'sensitivity': sensitivity}
    if rate_inputs is not None:
        result['rate_sensitivity'] = result_rate_sensitivity(calculate_rf_readings(
            rate_currency='HKD',price_currency='HKD',price_unit='per_share',
            priced_r={k:inp[k] for k in r_keys},band_at=band_rf,
            rates_loader=lambda _currency:rate_inputs,base_anchors=(L,M,H)))
    return result


def calculate(context):
    glass,copper=context['axes']['glass'],context['axes']['copper']
    selected={key:glass[key] for key in AXIS_ROWS['ai-glass-fabric']}
    selected.update({key:copper[key] for key in AXIS_ROWS['hvlp-copper-foil']})
    selected['cu_yield']=copper['yield_hvlp3']
    derived=derived_history(INPUTS)
    result=evaluate({**INPUTS,**selected,**derived},context.get('rate_inputs'))
    result['basis_changed']=None
    optional=set(OPT_REQUIRED)|{'e_lam_27c','e_lam_28c'}
    if any(not math.isfinite(INPUTS[k]) for k in optional if k in INPUTS):
        result['partial_basis_changed']=True
    else:
        result['partial_basis_changed']=local_basis_changed(
            {'inputs':INPUTS,'axes':selected,'history_result':HIST_RESULT,
             'history_assets':HIST_NET_ASSETS,'return_years':list(RET_YEARS)},HISTORICAL_PARTIAL_FINGERPRINT)
    result['units']={'price':'HKD_PER_SHARE'}
    result['option']['value_unit']='HKD_PER_SHARE'
    names=('klhl','pcb','chem','rent','pud','sec','jv','debt')
    result['segments']={name:{'unit':'HKD_PER_SHARE','values':{
        t.upper():result['tiers'][t][name] for t in 'lmh'}} for name in names}
    result['key_parameters']={
        'laminate':{'discount_rate':INPUTS['r_lam'],'growth_rate':INPUTS['g2_lam'],
                    'mid_forward_return':derived['ret_lam_m']*(1-INPUTS['tax']),
                    'steady_return':derived['rs_lam_h']},
        'pcb':{'discount_rate':INPUTS['r_pcb'],'growth_rate':0},
        'chemicals':{'discount_rate':INPUTS['r_chem'],'growth_rate':0},
        'property':{'discount_rate':INPUTS['r_prop'],'growth_rate':0}}
    return result
