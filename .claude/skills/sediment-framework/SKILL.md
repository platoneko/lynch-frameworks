---
name: sediment-framework
description: >
  与用户多轮对话，对齐林奇分类、归篮（篮子折现率）、专属属性、假设与可演算主尺后，再把估值框架沉淀落盘。
  在用户要求「写估值框架」「按林奇分类」「沉淀框架」「更新框架」「财报后修订假设」「归篮」、
  「入库标的」、说出 /sediment-framework 或 /lynch-framework，
  或明确要以可复现方式把某 ticker 的专属估值逻辑写入 frameworks/ 时使用。
  默认先持续对话，禁止一上来就写文件。不要用于纯行情查询、下单、或 invest 候选池挖掘。
---

# 沉淀估值框架（sediment-framework · 篮子折现率）

折现率 \(r\) 按生意性质归入 7 个篮子（`references/valuation-rules.md`「§r 篮子」；值的真源 `eval/lib/gordon.py` `BASKET_R`），\(G_{cap}=\min(6\%, r-4\%)\)（`gordon.g_cap`）；随之而来的是域判定、DDM 触发、周期票 regime / point 双口径与利率敏感性。利率轴 `_AXIS.rates`：USD 段已建（HKD 跟 USD；`axes.load_rates` / `rf_report.rf_block`），日报共识 / 反向压力两行已建（读 eval 写的 `output/rates/`，样板 `eval/GOOG.US.py`）；CNY / TWD 段与其余票的 eval 接入 **[待建]**，未接入的票只报隐含 r(P)。

**主形态是持续对话，不是一次性写文档。**  
用户明确说「可以落盘 / 写成文件 / 确认写入」之后，才写 `frameworks/<TICKER>.md`。  
「继续 / 嗯 / 好」≠ 授权落盘。标的池 = 扫 `frameworks/*.md`（排除 `_` 前缀）；**MUST NOT** 维护 `universe.yaml`。  
模板：`frameworks/_TEMPLATE.md`。仓库契约：`AGENTS.md`。语义真源：`references/valuation-rules.md`。

### 懒加载（MUST）

| 时机 | Read |
|------|------|
| 第 2 块业务地图 / 定 pe 带 / 银行票 | `references/heuristics.md` |
| 第 3 块归篮 / 任何涉及 \(r\) 的讨论 | `references/valuation-rules.md`「§r 篮子」 |
| 第 7 块定锚**之前**、任何选倍数形式（完整式 / \(1/r\) / \(1/(r-g)\) / 窗口 NPV）的讨论 | `references/valuation-rules.md`「留存去向审计」+「杠杆门」（先拉 ≥7 年 capex / NPPE / 净债，分桶、算净债 / EBITDA 与利息 / EBIT 后才许定形式） |
| 第 6 块定锚 / 框架纠正改尺 | `references/construction.md` |
| 生成的 M 倍数低于自身实测带下沿（③ 出带） | `references/valuation-rules.md`「③ 出带处理流程」（先补 ②、带同基、增长率诚实、逐档降篮、篮 4 仍出带 → BLOCKED + 带边 r 并列） |
| zone ∈ {`stretched`,`deep_discount`} | `references/zone-reflection.md` |
| 拟落盘摘要之后、授权之前 | `references/checklist.md` |

未按上表加载对应 reference → **不得**报价带 / 声称 A2f 完成 / 勾自检完成。

---

## 硬约束（违反则停下问用户）

1. **对话优先 / 落盘门闩**：一次只问一块；授权前 **MUST NOT** 写 `frameworks/` 或 `eval/`。取数与贴表可以。
2. **只写本仓库**（授权后）：`frameworks/<TICKER>.md`；可选 `eval/<TICKER>.py`。不写 invest-data / `universe.yaml`。
3. **林奇分类**：`lynch_primary` 必填；`lynch_secondary` 可选；∈ 六类枚举。专属叙事只进 §1 / Assumptions，不作 secondary。
4. **业务地图有材料**：分部/SOTP 前 **MUST** 拉财报分部 + ≥1 份研报线索；**MUST NOT** 凭常识空拆。不足标 `待补`。
5. **单文件时间线**：不建多版本文件。Changelog **仅事件追踪**；初建日不写；框架纠正不写；事件按自然日合并 `### YYYY-MM-DD`。
6. **不整页推翻**：先读全文再增量；大改也在同文件改现行块。
7. **数字可追溯**：§3 Inputs 写来源与 as-of；缺则 `待补`，不编造。
8. **倍数多维印证**：定倍数 / \(L/M/H\) 前 **MUST** 展示印证矩阵（`heuristics.md` A2d）。
9. **档位跨票可比**：构造走 `construction.md`；语义见 `valuation-rules.md`「锚点语义」。散布 **MUST NOT** 来自手法。
10. **不做交易指令**。
11. **Ticker 规范化**：见下方表；文件名 = 题头 `# TICKER` = `eval/<TICKER>.py`。
12. **两端 zone MUST 反思**：`stretched` / `deep_discount` → `zone-reflection.md`。现价不是输入；两终点同等合法（\(P\le H+V_{opt}\)，或接受溢价并举证）。中间三档不强制。
13. **BLOCKED 不落盘**：见 `valuation-rules.md`「BLOCKED 的语义」「纠正对账门」。授权解不开 BLOCKED；subagent prompt **MUST** 转述本条。
14. **r 只能归篮，不能拧**：每腿 \(r\) 只能是 `valuation-rules.md`「§r 篮子」表中 7 个值之一（真源 `gordon.py` `BASKET_R`）；一腿 **MAY** 按「篮子对」声明过渡篮 / 终值篮**两个**篮子值（默认相等；四条判据 + \(k\) 强制见该节；稳态特征**不要求今天已满足**，差距归 \(k\)），仍**只能取表中值**；Inputs 每条**进锚点公式的 r 行**来源单元格 **MUST** 写 `篮 N` + 归篮理由（eval 用 `inputs.parse_baskets` + `check_r(r, where, basket)` 校验）；只作披露的 r 读数（`r_disc` 年漂移折现、`r_lt_implied`、带边 / 隐含 r）**MUST NOT** 含 `篮 N` 字样；改篮子值属仓库级，单票 **MUST NOT** 动。市价与篮子尺的差走「隐含 r 对账」，不走 r。
15. **倍数形式由留存去向审出，不是选的**：定锚前 **MUST** 跑 `valuation-rules.md`「留存去向审计」Step 0–5 并把分桶结论写进 Assumptions；命中「禁止形态」任一条即停下回对话。
16. **出带不许照印，也不许换带 / 拧 g 凑进去**：M 倍数低于自身带下沿时 **MUST** 走 `valuation-rules.md`「③ 出带处理流程」——先补 ②、带与分子同基、**带有效性核验**（带下沿月份的预期增速与 ROE 是否与现模型同量级；失真带 **MUST NOT** 用来降篮或反推，③ 判不可判定走对账门）、增长率按窗口 + 终值诚实写、逐档降篮到篮 4（仅限干净带）；仍出带 → BLOCKED，不出 zone，印对照带 + 带边 r 并列 zone。**MUST NOT** 维持初分篮照印、改看另一条能过的带、把区间 CAGR 当永续、用期权救尺、用失真带降篮。

---

## 模式判定

| 用户意图 | 模式 |
|----------|------|
| 新 ticker / 尚无文件 | **初建** |
| 纠正口径 / 修公式 / 证据链 / skill 对齐 | **框架纠正** — 改现行块，**不写 Changelog** |
| 财报后更新 / 假设状态变化 / 里程碑 | **事件增量** — 改现行块 **并** append Changelog |
| 只改分类或题头主尺一行 | **题头修补** |

已有文件却说「重写」→ 先确认纠正 vs 事件；Changelog 默认保留。

### Ticker 规范化

| 市场 | 规则 | 例 | 禁止 |
|------|------|----|------|
| 美股 | **MUST** `.US` | `WOLF.US` | `WOLF` |
| 港股 | 保留 `.HK`，常 4 位补零 | `0700.HK` | `700.HK`、`0700` |
| A 股 | `.SH` / `.SZ`（全仓一致） | `601899.SH` | `601899`、随意 `.SS` |

口述裸美股代码 → 先补 `*.US` 再写路径。

---

## 步骤 A — 初建

### A1. 静默准备（可工具，不落盘）

- 读 `_TEMPLATE.md`；已有同名 → 改走 B 或 C
- **轴候选懒加载**：只读 `_INDEX.md`「共享情景轴」或 `ls frameworks/axes/`，记文件名/逻辑 id/挂载票；**MUST NOT** 预读全部轴正文
- 预取：最近财报 segment + ≥1 份卖方分部/SOTP 线索
- **原始披露优先**：分部利润、资本结构、章程、减值、分红政策 → 定期报告原文（PDF → `pdftotext -layout`）；搜索摘要**只定位文档**。口径字段 **MUST** 引附注原句（归母 vs 归属普通股股东）
- **不要**此时创建框架文件

### A2. 对话对齐（一次一块）

1. **林奇主类**（及是否次类）— 2–3 选项 + 倾向理由
2. **业务地图 → 是否分部** — **MUST** `Read references/heuristics.md`；贴有来源业务表；按分部/银行启发式给主尺骨架 2–3 选项（**不要擅自定案**）。DDM 例外见 `valuation-rules.md`（只剩触发 (b)；`0883.HK` 是旧样板，篮子 r 下它本身不再触发，只借其纪律）
3. **归篮** — **MUST** `Read references/valuation-rules.md`「§r 篮子」：每腿（ETF 按成分行业；**被动 ETF 主尺走「§ETF 例外」趋势通道，红利类加去利率化对照版**）给篮子 + 一句判据理由 + CAPM 粗筛读数；|CAPM − 篮子| > 3pp 须写「为什么行业风险 ≠ β 风险」。周期票同时声明挂载商品轴各档 regime / point 语义、利率轴货币段
4. **一句话 thesis** + 主尺公式（映射到 \(L/M/H\)）
5. **专属属性**（≥1）
6. **可证伪假设**
7. **锚点** — **MUST** `Read references/construction.md` + `heuristics.md`（A2d）
   - 分腿先声明每腿 Gordon vs EV/EBIT（§5b）；分腿 **不合成 \(\bar r\)**，逐腿相加
   - 先印证矩阵，再锁倍数，再算 \(L/M/H\)、切点、五档、zone；周期票两口径都算，主 zone 取轴声明语义
   - 每锚一句「定价了什么」；**禁止现价倒推**
   - 报隐含 r(P)；USD / HKD 票 eval 接 `rf_report.rf_block` 出 \(r_f\) 敏感带 + 共识列 + 反向压力列（`valuation-rules.md`「§利率轴」；CNY / TWD 段 **[待建]**）
   - 两端 zone → **MUST** `Read references/zone-reflection.md` 跑完再进摘要

**决定权边界**：仅**林奇主类**、**归篮**与**主尺骨架**列选项；其余构造给推荐+默认并推进，用户不反对即定。

七块对齐且 A2f（若触发）完成后：贴拟落盘摘要 → `Read references/checklist.md` → 问是否授权落盘。

### A2b. 取数

| 需要 | 工具 |
|------|------|
| 报价 / 三表 / 倍数 | yfinance / longbridge |
| 分部 / segment Note | 财报技能、Longbridge、earnings-recap；缺则 Wisburg |
| 资本结构 / 章程 / 减值 / 分红 | **定期报告原文** |
| EPS/EBIT 共识与桥 | estimate-analysis / consensus |
| ROIC/ROE | fundamentals / valuation |
| 研报 SOTP / 分部倍数 | Wisburg ≥2 家 |
| 历史 PE / 同业 | Longbridge valuation* |
| 共享轴全文 | 仅命中后 `Read frameworks/axes/<名>.md` |

### A3. 落盘（仅明确授权后）

1. 写满框架：题头两行 + §0–§3（§0 含「这张表怎么读」）；§4 初建日留空。规则拦下但用户拍板入池的票，题头第三行 `> **状态：BLOCKED**（原因；解封条件）`，底牌行照写（对照带），日报 / 索引不出 zone（`AGENTS.md`「BLOCKED — 题头契约」）
2. 可选 `eval/<TICKER>.py` 薄壳
3. 新建/改题头/改轴挂载 → `python3 scripts/gen_index.py`
4. 汇报路径、分类、主尺、假设条数、尚缺数据

未授权 → 停在对话。

---

## 步骤 B — 框架纠正（不写 Changelog）

读现行 → 对话列拟改 → 涉倍数走 A2d、涉锚点 **MUST** 走 `construction.md`、两端 zone 走 A2f → **授权后**只改现行块 + 必要时 eval。过程不进 §4。

## 步骤 C — 事件增量（写 Changelog）

读现行 → 逐条判定 confirmed / weakened / falsified → 若改 Inputs/锚点则重算 + 必要时 A2f → **授权后**改现行块，Changelog 按当日合并 + `touched: […]`。

## 步骤 D — 题头修补

只改题头两行引用块；纯修补不写 Changelog。改 ticker/中文名 → `gen_index.py`。

---

## 题头约定

```markdown
# TICKER — 中文名 / English Name

> 林奇：`primary`[ / `secondary`] | 更新：YYYY-MM-DD | eval: eval/TICKER.py
> 主尺：（一句话索引；细节在 §0 / §3）
```

## 林奇六类

| 枚举值 | 中文 |
|--------|------|
| `slow_grower` | 缓慢增长 |
| `stalwart` | 稳定增长 / 绩优 |
| `fast_grower` | 快速增长 |
| `cyclical` | 周期 |
| `turnaround` | 转机 |
| `asset_play` | 资产隐蔽 |

「估值重估」不是第七类，写在 §1 thesis。
