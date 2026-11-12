# 估值构造口径（valuation-rules · 篮子折现率）

**`rules/` 下这几份文件合起来是 skill `sediment-framework` 的语义真源**：锚点各定价什么、折现率怎么归篮、倍数怎么由增长生成、增长怎么分层表达、期权与候选带的判据、共享轴的构造要求，以及这些规则互相顶时的裁决顺序。本文件只是索引：别处写「`valuation-rules.md`「X」」时，按下表找到 X 所在的文件，**只 Read 那一份**。**怎么操作**见同目录 `construction.md` / `zone-reflection.md` / `heuristics.md`（由 `SKILL.md` 按需加载）；**仓库级契约**（五档 zone、Outputs 行格式、日报与 eval）在仓库根 `AGENTS.md`。

**折现率 \(r\) 按生意性质归入 7 个篮子**（「§r 篮子」；2026-09-20 起为仓库现行口径，取代此前按腿的现金流性质分 7 / 10 / 13 三档）。由此派生：\(G_{cap}\) 随 r、域判定表、峰形区处理、单调区不可达、DDM 触发、周期票 regime / point 双口径、利率轴敏感性。篮子值真源 `eval/lib/gordon.py` `BASKET_R`，g 上限 `gordon.g_cap(r)`；新脚本持有各腿篮子声明并调用 `check_r(r, where, basket)` 与 `check_g_cap(g, r, where)` 校验，不从正文解析篮子。旧脚本的 `inputs.parse_baskets` 属于迁移前现状。利率轴机器数据和结果读数已有部分实现，但 CNY 仅有长期中枢、TWD 待建，个股接入未全覆盖；缺失读数标待补。季度篮级对账、`decay_two_stage_pe`、SOTP δ 反解库函数等标 `[待建]` 的部分尚无代码，framework 里对应项标 `待建` 而非勾选。

## 索引

| 文件 | 节（及常被引用的小节） |
|------|------------------------|
| `rules/anchors.md` | 价带偏离反思（zone 触发）· 锚点语义 · L 是情景，不是地板 · 可比性的构造要求 · 数据优先级与同业同尺（同业同尺、借用过渡年） |
| `rules/basket.md` | 永续增长口径（经营腿、准年金腿例外、DDM 主尺例外）· §r 篮子（篮子表、锚点税前、腿归篮、单票 SOTP 不合成 \(\bar r\)、CAPM 粗筛、隐含 r 对账）· 篮子对：过渡篮 / 终值篮（\(k\) 强制） |
| `rules/retention.md` | 经营价值与超额现金（① 拆分 … ⑤ 零增长、时点对齐、框架纠正的范围）· 留存去向审计（Step 0–5、视同派出现金的打折 k、禁止形态）· 杠杆门（权益法被投资方自带债务） |
| `rules/growth.md` | 增长 \(g\)、域与上限（域判定表、峰形区、6% 的含义、巨型硬件上限、增长的表达顺序、已实现增长窗口、\(g_2\) 来源优先序、碰顶即停）· 构造规则冲突的裁决顺序 · 周期票的中枢分子与 PE < 1/r 的读法 · 两段式过渡（周期票 regime / point 双口径、谷底档） |
| `rules/out-of-band.md` | ③ 出带处理流程 · 独立成交价护栏 · \(g_2\) 敏感性 · 纠正对账门 · BLOCKED 的语义 |
| `rules/options.md` | 未建模期权（\(V_{opt}\)）· 共识升级候选带（candidate）· 共享情景轴（构造要求） |
| `rules/special-legs.md` | 保险腿：内含价值尺 · 利率轴与 \(r_f\) 敏感性（§利率轴）· ETF 例外：被动篮子 = 全收益趋势通道（§ETF 例外、去利率化对照版） |

表里没有的名字：`grep -n '<名字>' references/rules/*.md` 定位，再按命中的节 Read。
