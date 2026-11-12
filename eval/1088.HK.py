#!/usr/bin/env python3
"""China Shenhua's historical coal-axis valuation, output in HKD per share.

This draft retains the old inputs, post-acquisition bridge and one-year high
commodity-price world. It is not a new forecast or publication confirmation.
"""
from __future__ import annotations
import hashlib
import json
from datetime import date
from math import isfinite
import sys
from pathlib import Path
import numpy as np
from lib.gordon import check_r
from lib.inputs import check_missing, ladder
from lib.tiers import decompose
from lib.zones import cut_points
from lib.rf_report import calculate_rf_readings

DEPENDENCIES = {'libraries': ('gordon', 'inputs', 'tiers', 'zones', 'rf_report'),
                'axes': {'coal': 'coal_price', 'rates': 'rates'}}

# Original Inputs table: source, intent and as-of preserved.
INPUTS = {
    # 总股本 百万股（重组后 21,689,434,304；2026 中报） | as-of 2026-06-30
    'shares': 21689,
    # HKD→CNY；yfinance `HKDCNY=X` | as-of 2026-10-05
    'fx_hkdcny': 0.8544,
    # 2Q26 每股净资产 CNY（Longbridge BS 2026H1；与 `520900.SH` `shenhua_bps` 同值）；只披露 | as-of 2026-06-30
    'bps': 21.173,
    # 净负债 RMB 百万（2026-06-30，重组后）；只披露，不进倍数 | as-of 2026-06-30
    'net_debt': 26500,
    # 备考归母 / 备考利润总额（A3）；归母 = 利润总额 × conv | as-of FY2025 备考
    'conv': 0.6814,
    # 煤炭分部利润总额（年报分部附注，最新重述） | as-of FY2019
    'seg_coal_fy2019': 35007,
    # 同上 | as-of FY2020
    'seg_coal_fy2020': 32189,
    # 同上（2022 年报重述） | as-of FY2021
    'seg_coal_fy2021': 57109,
    # 同上 | as-of FY2022
    'seg_coal_fy2022': 70384,
    # 同上 | as-of FY2023
    'seg_coal_fy2023': 58530,
    # 同上（2025 年报重述） | as-of FY2024
    'seg_coal_fy2024': 51539,
    # 同上 | as-of FY2025
    'seg_coal_fy2025': 46597,
    # 发电分部利润总额 | as-of FY2019
    'seg_power_fy2019': 8499,
    # 同上 | as-of FY2020
    'seg_power_fy2020': 6923,
    # 同上 | as-of FY2021
    'seg_power_fy2021': 1800,
    # 同上 | as-of FY2022
    'seg_power_fy2022': 7938,
    # 同上 | as-of FY2023
    'seg_power_fy2023': 10642,
    # 同上 | as-of FY2024
    'seg_power_fy2024': 11108,
    # 同上 | as-of FY2025
    'seg_power_fy2025': 12627,
    # 未分配项目（联营投资收益为主） | as-of FY2019
    'seg_unalloc_fy2019': 4354,
    # 同上 | as-of FY2020
    'seg_unalloc_fy2020': 4663,
    # 同上 | as-of FY2021
    'seg_unalloc_fy2021': -2468,
    # 同上 | as-of FY2022
    'seg_unalloc_fy2022': 1468,
    # 同上 | as-of FY2023
    'seg_unalloc_fy2023': 3946,
    # 同上 | as-of FY2024
    'seg_unalloc_fy2024': 5989,
    # 同上 | as-of FY2025
    'seg_unalloc_fy2025': 4275,
    # 利润总额（分部合计）；桥复现 conv | as-of FY2022
    'pbt_fy2022': 96247,
    # 同上 | as-of FY2023
    'pbt_fy2023': 87176,
    # 同上 | as-of FY2024
    'pbt_fy2024': 82928,
    # 同上 | as-of FY2025
    'pbt_fy2025': 79339,
    # IFRS 归母（最新重述口径） | as-of FY2022
    'ni_fy2022': 72925,
    # 同上 | as-of FY2023
    'ni_fy2023': 64625,
    # 同上 | as-of FY2024
    'ni_fy2024': 59544,
    # 同上；桥复现锚 | as-of FY2025
    'ni_fy2025': 54218,
    # 煤炭腿备考基数（A3） | as-of FY2025 备考
    'pbt_coal_pf': 56399,
    # 发电腿备考基数 = 发电 14,477 + 国电合资联营 3,369（A3） | as-of FY2025 备考
    'pbt_power_pf': 17846,
    # 发电分部备考（不含联营）；power_scale = 本值 ÷ `seg_power_fy2025` | as-of FY2025 备考
    'pbt_power_fy25_exassoc': 14477,
    # 铁路 12,903 + 港口 2,675 备考 | as-of FY2025 备考
    'pbt_rail_pf': 15578,
    # 航运 + 煤化工：2025H1 重述 + 2026H1（A5） | as-of 2025H1–2026H1
    'pbt_shipchem': 2503,
    # 残差：未分配 − 联营 − 收购利息 1,690 + 抵销（A3）；按腿份额摊入 | as-of FY2025 备考
    'pbt_resid_pf': -872,
    # 自产煤销量 2026H1 年化 488.6 ÷ FY2025 332.3 百万吨（A3） | as-of 2026H1
    'vol_scale': 1.47,
    # **H 档周期高年维持年数**：H = `_AXIS.coal-price`「周期高年」（一个年均），按 1 年后回到 M 档计，逐腿按各自 r；**MUST NOT** 把高年利润按永续资本化（A17） | as-of 2026-10-16
    'h_pass_years': 1,
    # 商品腿（煤炭 + 航运 + 煤化工）→ **篮 6 周期商品**（盈利是煤价 / 运价 / 化工品价函数；A16） | as-of 2026-10-07
    'r_coal': 0.13,
    # 发电腿（含国电合资联营）→ **篮 4 常规经营**（沿用 `600011.SH` 煤电归篮；A16） | as-of 2026-10-07
    'r_power': 0.10,
    # 铁路港口腿 → **篮 4 常规经营**（内部运量与内部定价，非管制公用；A16） | as-of 2026-10-07
    'r_rail': 0.10,
    # FY2025 派息率（中国准则）；DDM 坐标与 A7，不进公式 | as-of FY2025
    'payout_fy25': 0.791,
    # 同等盈利月份带下沿（2022-07）；**护栏**（A8） | as-of 2022-03~2025-12
    'pe_own_min': 5.43,
    # 同等盈利月份带上沿；**护栏** | as-of 2022-03~2025-12
    'pe_own_max': 13.15,
    # 同等盈利月份 H 股月末收盘 p25 HKD（36 个月）；对账坐标，不进公式 | as-of 2022-03~2025-12
    'px_same_p25': 25.51,
    # 同上中位 | as-of 2022-03~2025-12
    'px_same_med': 31.05,
    # 同上 p75 | as-of 2022-03~2025-12
    'px_same_p75': 33.79,
    # H 股 5 年月频 PB 中位；对账坐标 | as-of 2021-09~2026-08
    'pb_own_med': 1.19,
    # 共识 FY2026E EPS 均值 CNY（yfinance 7 家，2.53–3.14）；不进公式 | as-of 2026-10-05
    'eps_cons_fy26_mean': 2.915,
    # 共识 FY2027E 下沿（yfinance 7 家）；②-b，不进公式 | as-of 2026-10-05
    'eps_cons_fy27_lo': 2.57,
    # 共识 FY2027E 均值 | as-of 2026-10-05
    'eps_cons_fy27_mean': 2.788,
    # 共识 FY2027E 上沿 | as-of 2026-10-05
    'eps_cons_fy27_hi': 3.14,
    # Longbridge H 股 12 家 TP 均值 HKD（42.0–61.1）；交叉 | as-of 2026-10-05
    'tp_cons_h': 50.13,
}

# Original evidence and rationale, not additional model inputs.
# - **业务地图摘要**：七个报告分部的利润总额、折旧、减值、资本开支、资产与负债全部披露。**2018–25 分部利润总额**（亿元；每年取最新重述值）：
# - **属性 A — 长协把当期弹性压到很低，桥用的是多年斜率**：电煤中长期合同占自产动力煤 86%（2026 中报），年度长协均价 FY2022–25 722 / 714 / 701 / 680、2026-09 704（轴政策锚）；2026H1 秦皇岛同比 +12.7% 而自产动力煤售价持平、EPS +2.8%。本框架的桥是 2019–25 七年分部回归，复现 FY2022 / 2023 / 2024 误差 −0.9% / −3.4% / −1.2%（锚 FY2025），说明多年尺度上长协会跟上现货；当期弹性低是滞后，不是斜率错。**证伪观察**：FY2026 全年归母若在秦皇岛年均 ≥ 830 下仍低于桥值 15% 以上 → 桥斜率重估（A2）。
# - **属性 B — 2026 重组改变了基数与资产负债表**：12 家标的（国家能源集团公司及西部能源持有；发行 A 股 + 现金对价）并表并追溯重述 2025；股本 +9.2%，2025H1 归母重述 +12%（246.38 → 275.83 亿），即重组轻度增厚 EPS；现金对价约 935 亿（配套募资 200 亿）使净现金 578 亿 → 净负债 265 亿（2026-06-30）。重组后全年口径要等 FY2026 年报，本框架用「FY2025 + 2 × 2025H1 重述差」备考（A3），利率 2.3% `待核`。
# - **属性 C — 派息高且有承诺，前瞻留存去还收购负债**：派息率（中国准则）2019–25 57.9 / 91.8 / 100.4 / 72.8 / 75.2 / 76.5 / 79.1%；2025–27 承诺每年 ≥ 65%。留存分桶：2019–22 主要堆现金（B 桶，净现金 345 → 1,136 亿）；2023–25 主要进具名增长 capex（D 桶，capex 420 / 330 / 447 亿 vs D&A 249 / 244 / 248 亿）；2026 起主要偿还收购负债（A 桶）→ 各腿 \(g\) = 0、倍数 \(1/r\)（A7）。
# - **属性 D — 为什么不叠 `slow_grower` 次类**：铁路 + 港口 + 发电合计约四成利润，但发电与煤价反向、铁路运量绑定自产煤，不是独立年金；四成垫子体现在价带窄（\(L/M\) 0.93），不在分类上。
# | A1 | **三档分子 = 煤价轴三档经自身分部回归桥到重组后 FY2027**：L 703 = FY2025 实测（备考基数本身），M 830 / H 965 按斜率抬升；归母 623.2 / 679.6 / 739.5 亿、EPS 2.873 / 3.133 / 3.409 元；分子年 FY2027（≥2 家带区间的最远共识年），不折现 | active | `_AXIS.coal-price` §1 / §3（矿商侧）；2019–25 分部表（§1） | `coal_l/m/h`、`seg_*`、`pbt_*_pf`；eval 对轴逐格校验（`check_coal_mount(..., "miner")`、基准序列、§4a 自产煤坐标） |
# | A2 | **桥 = 2019–25 分部利润总额对轴基准序列的回归斜率**（煤炭 52.14、发电 −3.53、未分配 −6.50 百万元 / 元·吨），不是自产煤售价 × 销量——后者（§4a 自产煤线 0.2147 × 销量 3.32 亿吨 = 71.3）不扣随价成本（资源税、外购煤、运费），会高估。**复现**（轴 4c-1）：锚 FY2025 归母，按各年自身 NI/PBT，FY2022 −0.9% / FY2023 −3.4% / FY2024 −1.2% ✓；FY2019–21 +23% ～ +43%（旧长协 regime，不在本 regime 内，只披露）。§4a 自产煤坐标 481.9 / 509.2 / 538.2 元/吨写进 Inputs 供对轴校验，不进公式 | active | 2019–25 年报分部附注；轴 §4a；eval 复算斜率与复现 | `seg_*_fy*`、`pbt_fy*`、`ni_fy*`；任一年复现 > ±20% 且不足 2 年 → BLOCKED |
# | A3 | **重组后备考基数**：煤炭 56,399 = 46,597 + 2 ×（2025H1 重述 26,663 − 原 21,762）；发电 14,477 = 12,627 + 2 ×（6,012 − 5,087），另把未分配里的联营投资收益 3,369（国电合资煤电）划入发电腿 → 17,846；铁路 + 港口 15,578；航运 + 煤化工 2,503 = 2025H1 重述（282 − 338）+ 2026H1（427 + 2,132）两个半年合计；残差 −872 = 未分配 4,275 − 联营 3,369 − 收购利息 1,690（新增净债 73,500 × 2.3% `待核`）− 抵销 87。斜率放大：煤炭 × vol_scale 1.470（2026H1 自产煤销量年化 488.6 / FY2025 332.3 百万吨）、发电 + 未分配 × power_scale 1.147（备考发电 / FY2025 发电）。conv = 备考归母 / 备考利润总额 0.6814 | active | 2026 中报（重述比较列、股本 21,689,434,304、收购公告）；2025 年报。**待 FY2026 年报**：重组后全年实测替换备考，利率实测替换 2.3% | `pbt_*_pf`、`vol_scale`、`conv`、`shares` |
# | A4 | **主尺 = 三腿分腿加总**；分腿 ROE 未接（分部资产 / 负债已披露，下次纠正按来源优先序 ① 接入）；切腿用分部利润总额（未逐腿分税），残差按份额摊入 | active | valuation-rules「归篮触发分腿」 | 主尺形态 |
# | A5 | **航运 + 煤化工固定为两个半年的合计**：煤化工 2025 年利润 0.58 亿、2026H1 21.32 亿（并入标的后），波动大，取最近两个半年 | active | 2026 中报 / 2025 中报重述 | `pbt_shipchem` |
# | A6 | **②-b**：共识 FY2027 均值 2.788 元（yfinance 7 家，2.57–3.14）**低于 L 的 2.872**，M 偏离 +12.3%（≤ 20%）。具名结构变量：**共识口径未统一到重组后股本与并表利润**——7 家里 FY26E 均值 2.915 > FY27E 2.788，区间下沿 2.57 低于重组前 FY2025 实测 2.73，说明多家仍按旧股本 / 旧利润或按煤价回落建模；本框架 L 已是 FY2025 实测煤价下的备考值。**证伪触发器**：FY2026 年报后（≥ 2027-03-31）重拉共识，若均值仍低于 M 10% 以上 → 分子改用共识三点（L 仍退到轴 L） | active | yfinance 2026-10-05；Longbridge 共识（H 股 2.98–3.67 港元，均值 3.333，家数与财年 `待补`） | `eps_cons_*`（不进公式）；eval 机械化 |
# | A7 | **留存去向审计 → 各腿 \(g\) = 0、倍数 \(1/r\)**：capex vs D&A（亿元）2018–20 232 / 195 / 215 vs 236 / 206 / 198（持平，维持）、2021–25 434 / 319 / 420 / 330 / 447 vs 208 / 229 / 249 / 244 / 248（D 桶：新矿、电厂、煤化工的具名增长 capex，已投产部分在 2025 / 2026H1 基数内）；固定资产 + 在建 2,589 → 3,054 亿，2026-06 并表后 4,148 亿；净现金 2018–25 448 / 345 / 636 / 975 / 1,136 / 1,059 / 1,134 / 578 亿，2026-06 **净负债 265 亿**。前瞻：派息承诺 ≥ 65%（实付 79%），留存约两成先还收购负债（A 桶）→ \(g = 0\)；D 桶在建项目的价值未单列（`待补`，进 `stretched` 解释，不作 \(V_{opt}\)：份数无具名产能目标）。**杠杆门**：净债 / EBITDA 0.21（含长期应付款 276 亿 0.43）、利息 / EBIT ≈ 5%，未触发 | active | 2018–25 年报现金流量表与资产负债表；2026 中报 | `r_*` 倍数形式；派息率移出 [65%, 95%] 或净负债 / EBITDA > 1 → 回对话 |
# | A8 | **护栏（裁决顺序 ③）**：有效 PE 8.53 / 8.43 / 7.81×（H 按高年维持 1 年，A17）落同等盈利月份带（TTM EPS 落 M 3.131 ±12% 的 36 个月，2022-03~2025-12）[5.43, 13.15] 内，中位 9.29；③ 不触发。**带有效性核验**：带下沿 2022-07（PE 5.43，TTM EPS 3.50，2022 尖峰年）当时 ROE ≈ 18%（现模型 ROE_M ≈ 14.8%，差 3pp），其后两年实测 EPS CAGR −9.6%/yr（FY2022→24，低于现模型 g 0）→ **干净** | active | Longbridge 月频（`valuation --history`）；5 年 PE 4.88–17.55、中位 8.92 | `pe_own_min/max`；eval 校验 |
# | A9 | **轴 M 证据区间**：M = 821 / 855 → M 30.74 / 31.33（±1.4%） | active | 轴 4c-5 | eval 打印 |
# | A10 | **归篮排查（隐含 r 对账第 3 条）结论**：差额在 r 层——② 分子：桥复现三年 ≤ 3.4%、L 已是 FY2025 实测；同等盈利月份中位 31.05 港元与 M 一致；③ g：\(g\) = 0 有 A 桶依据；① 归篮：煤炭盈利是秦皇岛函数（相关 0.98），篮 6 正向成立。2026 年市价越过同等盈利月份上沿的部分 = 市场给央企煤企的要求回报低于篮 6（与 `0857.HK` A10 同一个「央企标签」篮子地板样本），走仓库级篮级对账，**MUST NOT** 在本票拧 r；卖方 TP 不反解 | active | 同等盈利月份表；`0857.HK` A10 | `r_coal` |
# | A11 | **未采用卖方目标价**：汇丰 43 港元（持有，2026-08-15）、美银 48（买入，2026-09-08）、Longbridge 12 家均值 50.13（42.0–61.1）；高盛中性、TP `待补` | active | Longbridge `institution-rating`；Wisburg | 交叉校验 |
# | A12 | **\(V_{opt}\) = 0；无候选带**：在建矿井 / 电厂的增量（D 桶）无具名产能与时点，份数缺 → `待补`；重组协同未具名 | active | — | Outputs 无表3 |
# | A13 | **`deep_discount` 观察项**：① 煤价回到旧长协 regime 谷底（FY2019–20 588 / 577，压力坐标）；② 303 号文长协基准下调；③ 收购利息高于 2.3% 或现金对价追加；④ 派息承诺下调到 65% 以下 | active | 轴 §1「L 排除」 | `deep_discount` 行 |
# | A14 | **同世界门**：分子年 FY2027 = 最远带区间共识年；自身 ≥3 年实测方向：归母 FY2022 729 → FY2025 542 亿（−9.4%/yr）、DPS 2.55 → 2.01（下行）→ \(g_2 > 0\) 的来源不可用，\(g\) = 0 与之同世界 | active | 年报 | A7 |
# | A15 | **分子口径 = 归属本公司股东（IFRS）**；无永续债 / 优先股 | active | 2025 年报 / 2026 中报权益表 | `ni_*` |
# | A16 | **归篮**：**商品腿**（煤炭 + 航运 + 煤化工）→ 篮 6（盈利是秦皇岛 5500 / 运价 / 化工品价函数）；**发电腿**（含国电合资联营）→ 篮 4（沿用 `600011.SH` 煤电归篮：上网电价管制 + 容量电价，盈利是价差但电价不由市场单边定）；**铁路港口腿** → 篮 4，不归篮 2：铁路 72% 收入来自集团内部、利润在煤炭与铁路之间按内部定价分配，运量绑定自产煤，「需求无弹性、永续」不成立；同业市场证据（大秦铁路 10 年 PE 中位 9.4×、秦港 H 股 6.9×）从未按 7.5% 定价。**CAPM 粗筛**：5 年周频 β 对恒指 **0.457**（相关 0.37）→ 4% + 0.457 × 5.5 + 港股 1 ≈ 7.5%，对价值加权 \(\bar r\) 11.9% −4.4pp；扣 HKD 段中位偏移 −3pp 后残差 −1.4pp（≤ 3pp）；β 低是因为盈利是煤价函数而非恒指函数 | active | valuation-rules「§r 篮子」；2025 年报分部附注（铁路分部间收入 31,301 / 43,710） | `r_coal` / `r_power` / `r_rail` |
# | A17 | **H 档周期高年是「路过」：高年维持 1 年后回到 M（2026-10-16 框架纠正，H 33.26 → 31.18）**：`_AXIS.coal-price` H 行「周期高年回归（2026-09 现货平台成为年均）……H = 当期现货平台延续成**一个年均**」、M 行「长协 regime 内一个完整周期的实测均值（中枢）」；本框架表2 H 行「现货在长协之上 250–300 元**持续一年**」——H 是周期里路过的一年。按 valuation-rules「经营价值与超额现金」② 商品腿豁免「每档 MUST 与该档的世界状态一致」（规则以本票为样本），H 档各腿取 965 世界的利润一年、之后取 M 世界，各腿 g = 0、倍数 1/r，故逐腿 H = M + (H 世界 − M) × (1 − (1 + r_腿)⁻¹)：商品腿 +2.91 × 0.115、发电腿（与煤价反向）−0.56 × 0.091、铁路港口不变。L（长协 regime 实测谷底）与 M（中枢）不动。**经营价值与超额现金其余读数**：① 超额现金未单列——重组后净负债 265 亿（2026-06-30）→ \(C_{ex}\) = 0，合并口径；归母比例不涉及（无现金行）；② 增长期资金缺口 0（无窗口）；③ 时点对齐不适用：分子是 FY2025 备考基数沿煤价**周期位置**移动（M = 一轮完整周期实测均值），不随日历漂移，属规则边界「周期中枢」，τ = 0；④ 稳态回报三段不适用：三腿 g = 0，RONIC 不进倍数，商品腿同属豁免；⑤ 无打折 k | active | `_AXIS.coal-price` §1 H / M 行；valuation-rules「经营价值与超额现金」② ③ | `h_pass_years`；eval 逐腿实现 |

TIERS = ("l", "m", "h")
YEARS = range(2019, 2026)
REPLAY_YEARS = (2022, 2023, 2024)
REPLAY_TOL = 0.20
CONS_DEV_MAX = 0.20
GATE_OUT = 0.20
LEGS = ("r_coal", "r_power", "r_rail")
# Canonical hash of the pre-migration stock inputs and both dated axis inputs.
# It flags changed assumptions; source reconciliation and confirmation are separate.
HISTORICAL_INPUT_FINGERPRINT = "866a6bef0416a07b51c2144d35ef022d9ee5019a87766b406301264269c9587d"

REQUIRED = [
    "shares", "fx_hkdcny", "bps", "net_debt", "conv",
    "coal_l", "coal_m", "coal_h", *(f"coal_fy{y}" for y in YEARS),
    "asp_a", "asp_b",
    *(f"seg_{s}_fy{y}" for s in ("coal", "power", "unalloc") for y in YEARS),
    *(f"pbt_fy{y}" for y in REPLAY_YEARS + (2025,)), *(f"ni_fy{y}" for y in REPLAY_YEARS + (2025,)),
    "pbt_coal_pf", "pbt_power_pf", "pbt_power_fy25_exassoc", "pbt_rail_pf", "pbt_shipchem", "pbt_resid_pf",
    "vol_scale", "h_pass_years", *LEGS,
    "payout_fy25", "pe_own_min", "pe_own_max",
    "px_same_p25", "px_same_med", "px_same_p75", "pb_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
]
NOT_FORMULA = ("bps", "net_debt", "payout_fy25", "pe_own_min", "pe_own_max", "px_same_p25", "px_same_med",
               "px_same_p75", "pb_own_med", "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean",
               "eps_cons_fy27_hi", "tp_cons_h", "asp_a", "asp_b")


def slope(inp: dict[str, float], seg: str) -> float:
    x = [inp[f"coal_fy{y}"] for y in YEARS]
    y = [inp[f"seg_{seg}_fy{y}"] for y in YEARS]
    return float(np.polyfit(x, y, 1)[0])


def evaluate(inp: dict[str, float], coal: dict, rates: dict) -> dict:
    if coal['side'] != 'miner' or coal['mount'] != 'priced':
        raise ValueError('1088 requires the miner priced mount')
    coordinates = {key: coal['coordinates'][key] for key in ('asp_a', 'asp_b')}
    if (not all(isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
                for value in coordinates.values()) or coordinates['asp_b'] <= 0):
        raise ValueError('invalid miner realised-price line')
    shared = {**coordinates,
              **{f'coal_{tier.lower()}': value for tier, value in coal['tier_prices'].items()},
              **{f'coal_fy{year}': value for year, value in coal['series'].items()}}
    asp = {tier.upper(): round(coordinates['asp_a'] + coordinates['asp_b'] * shared[f'coal_{tier}'], 1)
           for tier in TIERS}
    duplicate_fields = {**shared, **{f'asp_{tier.lower()}': value for tier, value in asp.items()}}
    for name, value in duplicate_fields.items():
        if name in inp and (isinstance(inp[name], bool) or not isinstance(inp[name], (int, float))
                            or not isfinite(inp[name]) or inp[name] != value):
            raise ValueError(f'{name}: stock input conflicts with shared axis or derived coordinate')
    # Identical duplicate fields add no information; canonicalize them before
    # computing the historical identity so a redundant copy is not a new fact.
    inp = {name: value for name, value in inp.items() if name not in duplicate_fields}
    # Axis display metadata is tracked by the runner, not an economic input.
    coal_fingerprint_input = {key: value for key, value in coal.items() if key != 'axis_metadata'}
    payload = {'stock': inp, 'coal': coal_fingerprint_input, 'rates': rates}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                            allow_nan=False).encode()).hexdigest()
    basis_changed = fingerprint != HISTORICAL_INPUT_FINGERPRINT
    try:
        rate_date = rates['as_of']
        if not isinstance(rate_date, str) or date.fromisoformat(rate_date).isoformat() != rate_date:
            raise ValueError('invalid rates as-of date')
        segment = rates['segments']['HKD']
        if segment['status'] != 'linked' or segment['linked_to'] != 'USD':
            raise ValueError('invalid HKD rates link')
        rate_inputs = segment['values']
    except (KeyError, TypeError) as exc:
        raise ValueError('missing dated HKD rates axis') from exc
    inp = dict(inp)
    inp.update(shared)
    errors = check_missing(inp, REQUIRED)
    if errors:
        raise ValueError('; '.join(errors))

    errors += [f"probability-looking input {k}" for k in inp if k.startswith("p_")]

    # --- Step 1: axis mount (miner side), base series, own coordinate ---------
    q = {t: inp[f"coal_{t}"] for t in TIERS}
    series = coal['series']

    # --- Step 2: bridge slopes and replay (axis 4c-1) --------------------------
    s_coal, s_pow, s_un = slope(inp, "coal"), slope(inp, "power"), slope(inp, "unalloc")
    s_used = s_coal + s_pow + s_un
    replay = {}
    for y in REPLAY_YEARS:
        conv_y = inp[f"ni_fy{y}"] / inp[f"pbt_fy{y}"]
        pred = inp["ni_fy2025"] + s_used * (inp[f"coal_fy{y}"] - inp["coal_fy2025"]) * conv_y
        replay[y] = pred / inp[f"ni_fy{y}"] - 1.0
    if sum(abs(e) <= REPLAY_TOL for e in replay.values()) < 2:
        errors.append(f"bridge replays < 2 realised years within ±{REPLAY_TOL:.0%}: {replay} — BLOCKED on the axis (4c-1)")

    # --- Step 3: baskets ----------------------------------------------------------
    baskets = {"r_coal": 6, "r_power": 4, "r_rail": 4}
    for leg in LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in its Inputs source cell")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    if errors:
        raise ValueError('; '.join(errors))

    # --- Step 4: legs and anchors ---------------------------------------------------
    power_scale = inp["pbt_power_fy25_exassoc"] / inp["seg_power_fy2025"]   # pro-forma power ex-associates / FY2025 reported

    def legs(t: str, r: dict[str, float], qx: float | None = None, vol: float | None = None) -> dict[str, float]:
        dq = (q[t] if qx is None else qx) - inp["coal_fy2025"]
        coal = inp["pbt_coal_pf"] + s_coal * (inp["vol_scale"] if vol is None else vol) * dq
        power = inp["pbt_power_pf"] + (s_pow + s_un) * power_scale * dq
        rail = inp["pbt_rail_pf"]
        sc = inp["pbt_shipchem"]
        base = coal + power + rail + sc
        k = 1.0 + inp["pbt_resid_pf"] / base
        hk = inp["conv"] * k / inp["shares"] / inp["fx_hkdcny"]
        return {
            "pbt": base + inp["pbt_resid_pf"],
            "coal": (coal + sc) * hk / r["r_coal"],
            "power": power * hk / r["r_power"],
            "rail": rail * hk / r["r_rail"],
        }

    r0 = {leg: inp[leg] for leg in LEGS}

    leg_r = {"coal": "r_coal", "power": "r_power", "rail": "r_rail"}
    n_pass = inp["h_pass_years"]
    if not n_pass > 0:
        errors.append(f"h_pass_years {n_pass} must be > 0 (H = 周期高年 passes, MUST NOT be capitalised as a regime)")

    def band(r: dict[str, float] = r0, **kw) -> tuple[float, float, float]:
        """H passes through (valuation-rules「经营价值与超额现金」② 商品腿豁免「每档 MUST 与该档的世界状态
        一致」; axis H = 周期高年「一个年均」): each leg earns its H-world profit for `h_pass_years`,
        then the M world; every leg is g = 0 / 1/r, so the H excess is an n-year annuity per leg."""
        lt = {t: legs(t, r, **kw) for t in TIERS}
        h = sum(lt["m"][k] + (lt["h"][k] - lt["m"][k]) * (1 - (1 + r[rk]) ** -n_pass) for k, rk in leg_r.items())
        return (sum(v for k, v in lt["l"].items() if k != "pbt"),
                sum(v for k, v in lt["m"].items() if k != "pbt"), h)

    lg = {t: legs(t, r0) for t in TIERS}
    ni = {t: lg[t]["pbt"] * inp["conv"] for t in TIERS}
    eps = {t: ni[t] / inp["shares"] for t in TIERS}
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    L, M, H = band()
    if not (L < M < H):
        raise ValueError('; '.join(errors + [f'L<M<H violated {L:.2f} {M:.2f} {H:.2f}']))
    A, B = cut_points(L, M, H)
    pe_eff = {t: a * inp["fx_hkdcny"] / eps[t] for t, a in zip(TIERS, (L, M, H))}

    # --- Step 5: guards ---------------------------------------------------------------
    in_band = all(inp["pe_own_min"] <= pe_eff[t] <= inp["pe_own_max"] for t in TIERS)
    cons = inp["eps_cons_fy27_mean"]
    dev = eps["m"] / cons - 1.0
    if cons > eps["h"]:
        errors.append(f"②-b: consensus FY27 mean {cons} above EPS_H {eps['h']:.3f}")
    if abs(dev) > CONS_DEV_MAX:
        errors.append(f"②-b: M deviates {dev:+.1%} from consensus mean (> {CONS_DEV_MAX:.0%})")
    consensus_below_mid = cons < eps["m"]
    bps_hkd = inp["bps"] / inp["fx_hkdcny"]
    zero_r = band({leg: inp["r_coal"] for leg in LEGS})
    coords = {
        "E_M/r 整篮 13%": zero_r[1],
        "D_M/(r̄)": inp["payout_fy25"] * eps["m"] / inp["fx_hkdcny"] / (
            (lg["m"]["coal"] * inp["r_coal"] + lg["m"]["power"] * inp["r_power"] + lg["m"]["rail"] * inp["r_rail"]) / M),
        "同等盈利月份中位": inp["px_same_med"],
        "BPS × 5 年 PB 中位": bps_hkd * inp["pb_own_med"],
    }
    if all(abs(M / v - 1.0) > GATE_OUT for v in coords.values()):
        errors.append(f"对账: M {M:.2f} outside every coordinate by > {GATE_OUT:.0%} — BLOCKED")
    for k in NOT_FORMULA:
        if k not in inp:
            errors.append(f"reference row missing: {k}")
    if errors:
        raise ValueError('; '.join(errors))
    d = decompose((L, M, H), (pe_eff['l'], pe_eff['m'], pe_eff['h']))
    sensitivity = {'rail_basket2': band(r={**r0, 'r_rail': .075}),
                   'coal_basket4': band(r={**r0, 'r_coal': .10}),
                   'power_basket6': band(r={**r0, 'r_power': .13}),
                   'volume_1': band(vol=1.),
                   'axis_m_821': legs('m', r0, qx=821.),
                   'axis_m_855': legs('m', r0, qx=855.)}
    def band_rf(dr):
        return band({leg: value + dr for leg, value in r0.items()})
    rf = calculate_rf_readings(rate_currency='HKD', price_currency='HKD',
                               price_unit='per_share', priced_r=dict(r0), band_at=band_rf,
                               rates_loader=lambda currency: rate_inputs,
                               base_anchors=(L, M, H))
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0), (L, M, H))):
        raise ValueError('rate sensitivity base differs from anchors')
    return {'ticker': '1088.HK', 'currency': 'HKD',
            # Input matching alone cannot prove the full research basis.
            'valuation_as_of': None, 'framework_as_of': None,
            'financial_basis_as_of': None,
            'historical_financial_basis_as_of': '2026-06-30',
            'historical_research_as_of': '2026-10-16',
            'research_review_required': True,
            'input_change_review_required': basis_changed,
            'rate_axis_as_of': rate_date,
            'derived_coordinates': {'asp': asp},
            # These are the old axis evidence endpoints, not a new forecast.
            'historical_axis_evidence': {'midpoints': [821.0, 855.0],
                                         'review_required': basis_changed},
            'anchors': dict(zip('LMH', (L, M, H))), 'candidate': None, 'option': None,
            'q': q, 'series': series, 's_coal': s_coal, 's_pow': s_pow,
            's_un': s_un, 's_used': s_used, 'replay': replay, 'power_scale': power_scale,
            'r0': r0, 'lg': lg, 'ni': ni, 'eps': eps, 'L': L, 'M': M, 'H': H,
            'A': A, 'B': B, 'pe_eff': pe_eff, 'in_band': in_band, 'cons': cons,
            'dev': dev, 'consensus_below_mid': consensus_below_mid, 'bps_hkd': bps_hkd,
            'zero_r': zero_r, 'coords': coords, 'd': d, 'sensitivity': sensitivity,
            # The same sensitivity endpoints now use the shared result shape;
            # no rate assumption or per-share value is recalculated here.
            'rate_sensitivity': {'inputs': rf['segment'], 'low': rf['step_down'],
                                 'high': rf['step_up'], 'consensus': dict(zip('LMH', rf['consensus'])),
                                 'pressure': dict(zip('LMH', rf['pressure'])),
                                 'price_currency': 'HKD', 'price_unit': 'per_share'},
            'basis_changed': None, 'partial_basis_changed': basis_changed}


def calculate(context):
    if context.get('rate_inputs') is not None:
        raise ValueError('rates must come from the declared dated rates axis')
    return evaluate(INPUTS, context['axes']['coal'], context['axes']['rates'])


if __name__ == '__main__':
    raise SystemExit('Use the explicit valuation_runner with code and content roots')
