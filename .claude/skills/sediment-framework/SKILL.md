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

折现率 \(r\) 按生意性质归入 7 个篮子（`references/rules/basket.md`「§r 篮子」；值的真源 `eval/lib/gordon.py` `BASKET_R`），\(G_{cap}=\min(6\%, r-4\%)\)（`gordon.g_cap`）；随之而来的是域判定、DDM 触发、周期票 regime / point 双口径与利率敏感性。利率轴 `_AXIS.rates` 的机器数据在 `frameworks/axes/rates.py`：USD 段已建、HKD 跟 USD，CNY 仅有长期中枢、TWD 待建；个股接入并不完整。新版脚本将已有敏感读数放入结果，日报从已保存结果读取；缺少读数时日报不显示利率行，研究中如实说明缺口，不从轴正文补读。

**主形态是持续对话，不是一次性写文档。**  
用户明确说「可以落盘 / 写成文件 / 确认写入」之后，才写 `frameworks/<TICKER>.md`。  
「继续 / 嗯 / 好」≠ 授权落盘。标的池 = 扫 `frameworks/*.md`（排除 `_` 前缀与 `AGENTS.md` / `README.md`）；**MUST NOT** 维护 `universe.yaml`。  
模板：`frameworks/_TEMPLATE.md`。仓库契约：`frameworks/AGENTS.md`（核心）+ `references/contracts.md`（脚本、输出和写作契约）。语义真源：`references/rules/*.md`（节名 → 文件的索引在 `references/valuation-rules.md`；别处写「valuation-rules.md「X」」就查索引，只读命中的那份）。各参考文件沿用的 Inputs、Outputs、表格或 Assumptions 旧称是计算与研究内容的定位词，不是要求正文保留机器格式；涉及正文及输出的具体形式统一按 `references/contracts.md`。

### 懒加载（MUST）

资金用途不明、截顶换尺或回报域边界导致锚点跳变时，读 `references/rules/retention.md`「资金用途不确定时的候选区间」及 `references/contracts.md`「资金用途候选区间」。

| 时机 | Read |
|------|------|
| 第 2 块业务地图 / 定 pe 带 / 银行票 | `references/heuristics.md` |
| 第 3 块归篮 / 任何涉及 \(r\) 的讨论 | `references/rules/basket.md`「§r 篮子」 |
| 第 7 块定锚**之前**、任何选倍数形式（完整式 / \(1/r\) / \(1/(r-g)\) / 窗口 NPV）的讨论 | `references/rules/retention.md`「经营价值与超额现金」+「留存去向审计」+「杠杆门」（先拉 ≥7 年 capex / NPPE / 净债 / 现金，拆超额现金、定 RONIC 层级、分桶、算净债 / EBITDA 与利息 / EBIT 后才许定形式；2026-10-13） |
| 第 6 块定锚 / 框架纠正改尺 | `references/construction.md` |
| 定 L 档倍数，或公式生成的倍数掉出本票历史实付区间（护栏红） | `references/rules/anchors.md`「L 的倍数也要有实证」（L 的倍数取同等盈利月份实付的下沿，不由 g 生成；隐含 g 只作坐标） |
| 定 \(g\) / \(g_2\)、两段式、周期票中枢分子或 regime / point 双口径 | `references/rules/growth.md` |
| 定 \(V_{opt}\) / 候选带 / 共享轴的构造 | `references/rules/options.md` |
| 保险腿、被动 ETF、\(r_f\) 敏感带 | `references/rules/special-legs.md` |
| 生成的 M 倍数低于自身实测带下沿（③ 出带） | `references/rules/out-of-band.md`「③ 出带处理流程」（先补 ②、带同基、增长率诚实、逐档降篮、篮 4 仍出带 → BLOCKED + 带边 r 并列） |
| zone ∈ {`stretched`,`deep_discount`}（研究当日现价归 zone，只在对话里） | `references/zone-reflection.md` |
| 向用户说明期权 \(V_{opt}\) / 候选带在卡片、日报上怎么显示、跨档告不告警 | 先核对实际消费方代码；`references/contracts.md` 记录目标契约，迁移完成前不能将目标描述成现有行为 |
| 任何锚点 / 敏感性 / 子代理结果交给用户之前；落盘前 | `references/self-review.md`（四问 + 稳态回报与 \(g_2\) 认可门） |
| 准备拟落盘摘要之前，及授权后保存结果时 | `references/result-publication.md` |
| 拟落盘摘要之后、授权之前 | `references/checklist.md` |
| 写或改标的文档、轴文件之前（含题头修补） | `references/contracts.md` |
| 设计脚本、校验或接入消费方 | `references/contracts.md`「计算与测试」 |

未按上表加载对应 reference → **不得**报价带 / 声称 A2f 完成 / 勾自检完成。

### 派后台子代理

子代理只读任务说明点到的东西，读多少由任务说明决定。写任务说明时：

1. **点名文件与节**：从上表挑本任务命中的行，写成 `references/rules/<文件>.md「节名」`；任务说明里只列这些文件，SKILL.md 与其余 references 由主会话按需转述。
2. **框架文档按目录读**：先在 `lynch/` 根跑 `just outline <TICKER>`（轴文件给路径；`frameworks/` 里有自己的 justfile，在那里跑找不到这条）拿各节行号与每条假设一行，再用 Read 的 offset / limit 只读任务要的节或假设行；整篇改写才全文读。eval 脚本先跑看输出，要改哪段再读哪段。
3. **一段只读一次**：读过的段留在上下文里，后面直接引用；Edit 成功即已落地，核对改动 `grep -n` 那几行。
4. **复用已有材料**：同批已拉的数据与试算结果写明路径，注明直接复用。
5. **转述硬约束**：落盘门闩、第 13 条 BLOCKED、第 17 条个人信息，以及本任务的写入范围。
6. **产出落文件、回报给摘要**：完整产出写 `frameworks/_local/tmp/<批次>/`；回给主会话的只有一屏以内的结论 + 文件路径。
7. **长输出先落文件**：`pdftotext`、`longbridge` 报表、`just check` 的输出写进 `_local/tmp/` 再 `grep` / `sed -n` 取行。

---

## 硬约束（违反则停下问用户）

1. **对话优先 / 落盘门闩**：一次只问一块；授权前 **MUST NOT** 创建或修改正式框架、共享轴及每票演算脚本，也不得写正式结果库。取数与贴表可以；临时试算、拟采纳提案和收据可写入用户私有的 `frameworks/_local/tmp/`。
2. **框架内容只写本仓库**（授权后）：`frameworks/<TICKER>.md`；可选 `frameworks/eval/<TICKER>.py`。用户授权后，可按 `references/result-publication.md` 使用专用命令维护 App 结果库；其他文件的写入范围不变。不写 invest-data / `universe.yaml`。新票的演算脚本写到 `frameworks/eval/<TICKER>.py`（内容仓库），题头仍写 `eval: eval/<TICKER>.py`（相对内容仓库根）。**MUST NOT** 在 `lynch/eval/` 下建每票脚本——那是代码仓库的库目录。
3. **林奇分类**：`lynch_primary` 必填；`lynch_secondary` 可选；∈ 六类枚举。专属叙事只进 §1 / Assumptions，不作 secondary。
4. **业务地图有材料**：分部/SOTP 前 **MUST** 拉财报分部 + ≥1 份研报线索；**MUST NOT** 凭常识空拆。不足标 `待补`。
5. **单文件时间线**：不建多版本文件。Changelog **仅事件追踪**；初建日不写；框架纠正不写；事件按自然日合并 `### YYYY-MM-DD`。
6. **不整页推翻**：先读全文再增量；大改也在同文件改现行块。
7. **数字可追溯**：计算输入旁的脚本注释写来源、日期、口径和判断；正文解释读者需要质疑的关键数字。缺则 `待补`，不编造。
8. **倍数多维印证**：定倍数 / \(L/M/H\) 前 **MUST** 展示印证矩阵（`heuristics.md` A2d）。
9. **档位跨票可比**：构造走 `construction.md`；语义见 `rules/anchors.md`「锚点语义」。散布 **MUST NOT** 来自手法。
10. **不做交易指令**。
11. **Ticker 规范化**：见下方表；文件名 = 题头 `# TICKER` = `frameworks/eval/<TICKER>.py`。
12. **两端 zone MUST 反思**：`stretched` / `deep_discount` → `zone-reflection.md`。现价不是输入；两终点同等合法（\(P\le H+V_{opt}\)，或接受溢价并举证）。中间三档不强制。现价只在研究对话里用，A2f 结论不落盘（2026-09-27 定）。
13. **BLOCKED 不落盘**：见 `rules/out-of-band.md`「BLOCKED 的语义」「纠正对账门」。泛授权（「按推荐来 / 不用对话」）解不开 BLOCKED；只有用户看过原因后明确拍板才落盘，未满足的规则和复核条件用人话说明；subagent prompt **MUST** 转述本条。
14. **r 只能归篮，不能拧**：每腿 \(r\) 只能是 `rules/basket.md`「§r 篮子」表中 7 个值之一（真源 `gordon.py` `BASKET_R`）；一腿 **MAY** 按「篮子对」声明过渡篮 / 终值篮两个篮子值，适用判据见该节。脚本声明每条实际折现率对应的篮子和理由并调用 `check_r` 校验；只作披露的读数不冒充篮子值。改篮子值属仓库级，单票 **MUST NOT** 动。市价隐含回报只在对话里讨论。
15. **倍数形式由留存去向审出，不是选的**：定锚前 **MUST** 跑 `rules/retention.md`「经营价值与超额现金」（拆超额现金、经营口径三处同换、RONIC 按档取最远卖方年份前瞻回报、留存拆分与约束、零增长条件）与「留存去向审计」Step 0–5，把拆分读数、RONIC 来源与分桶结论写进 Assumptions；命中「禁止形态」任一条、周期股同等盈利月份交叉差 > 20%、或新建框架 \(g_2\) 任一层原值碰到上限（碰顶即停），即停下回对话。存量框架的框架纠正只做三件事（同节「框架纠正的范围」），已讨论定稿的取法不动（2026-10-13；2026-10-15 改）。
16. **出带不许照印，也不许换带 / 拧 g 凑进去**：M 倍数低于自身带下沿时 **MUST** 走 `rules/out-of-band.md`「③ 出带处理流程」——先补 ②、带与分子同基、**带有效性核验**（带下沿月份的预期增速与 ROE 是否与现模型同量级；失真带 **MUST NOT** 用来降篮或反推，③ 判不可判定走对账门）、增长率按窗口 + 终值诚实写、逐档降篮到篮 4（仅限干净带）；仍出带 → BLOCKED：停下报告（篮 4 诚实结构下 L/M/H + 带边 r 并列价带；市价隐含 r 只在对话里报、不落盘）。**MUST NOT** 维持初分篮照印、改看另一条能过的带、把区间 CAGR 当永续、用期权救尺、用失真带降篮。
17. **子代理网络请求 MUST NOT 含用户个人信息**（邮箱、姓名等，含 SEC User-Agent）；网站要求联系方式就换来源（2026-10-14 定）。

---

## 模式判定

| 用户意图 | 模式 |
|----------|------|
| 新 ticker / 尚无文件 | **初建** |
| 纠正口径 / 修公式 / 证据链 / skill 对齐 | **框架纠正** — 改现行块，**不写 Changelog** |
| 财报后核对 / 假设状态变化 / 里程碑 | **事件增量** — 改现行块；仅引用的客观数字发生变化时写更新记录（`references/contracts.md`「框架文档」） |
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
- **轴候选懒加载**：只读 `_INDEX.md`「共享情景轴」或 `ls frameworks/axes/`，记候选逻辑 id；命中后再核对共享轴机器模块及可阅读说明，**MUST NOT** 预读全部轴正文，也不把正文作为计算输入。
- 预取：最近财报 segment + ≥1 份卖方分部/SOTP 线索
- **原始披露优先**：分部利润、资本结构、章程、减值、分红政策 → 定期报告原文（PDF → `pdftotext -layout`）；搜索摘要**只定位文档**。口径字段 **MUST** 引附注原句（归母 vs 归属普通股股东）
- **不要**此时创建框架文件

### A2. 对话对齐（一次一块）

1. **林奇主类**（及是否次类）— 2–3 选项 + 倾向理由
2. **业务地图 → 是否分部** — **MUST** `Read references/heuristics.md`；贴有来源业务表；按分部/银行启发式给主尺骨架 2–3 选项（**不要擅自定案**）。DDM 例外见 `rules/basket.md`「永续增长口径」（只剩触发 (b)）
3. **归篮** — **MUST** `Read references/rules/basket.md`「§r 篮子」：每腿（ETF 按成分行业；**被动 ETF 主尺走「§ETF 例外」趋势通道，红利类加去利率化对照版**）给篮子 + 一句判据理由 + CAPM 粗筛读数；|CAPM − 篮子| > 3pp 须写「为什么行业风险 ≠ β 风险」。周期票同时声明挂载商品轴各档 regime / point 语义、利率轴货币段
4. **一句话 thesis** + 主尺公式（映射到 \(L/M/H\)）
5. **专属属性**（≥1）
6. **可证伪假设**
7. **锚点** — **MUST** `Read references/construction.md` + `heuristics.md`（A2d）
   - 分腿先声明每腿 Gordon vs EV/EBIT（§5b）；分腿 **不合成 \(\bar r\)**，逐腿相加
   - 先印证矩阵，再锁倍数，再算 \(L/M/H\)、切点、五档价格区间；周期票两口径都算，主价带取轴声明语义
   - 每锚一句「定价了什么」；**禁止现价倒推**，现价及其派生读数亦不落盘（`AGENTS.md`「现价 — 禁写契约」）
   - 隐含 r(P) 只在对话里作诊断、不落盘；新研究的 USD / HKD 票 **MUST** 接入机器利率轴并输出 \(r_f\) 敏感带、共识列和反向压力列（`rules/special-legs.md`「§利率轴」）。迁移旧记录时未接入的读数如实标待补，不从正文代取或为迁移补造数据。
   - 用研究当日现价归 zone（只在对话里）；两端 zone → **MUST** `Read references/zone-reflection.md` 跑完再进摘要，A2f 结论不落盘

**决定权边界**：仅**林奇主类**、**归篮**与**主尺骨架**列选项；其余构造给推荐+默认并推进，用户不反对即定。

七块对齐且 A2f（若触发）完成后：按 `references/result-publication.md` 准备拟采纳结果和收据 → 贴拟落盘摘要 → `Read references/checklist.md` → 未获授权时问是否授权落盘。若用户已明确授权，不重复征询；仍须在改正式文件前准备拟采纳结果和收据。

**拟落盘摘要 MUST 含两块（2026-10-12 定：曾有两处近门槛判断要用户追问才翻出）**：

- **回报率拆解**：M 档 ROE = 净利率 × 资产周转 × 权益乘数，并列 ROIC（口径同「杠杆门」①）、RONIC（层级与取值，「经营价值与超额现金」②）与 RONIC 所在的域，超额现金单列时并列经营口径 ROE；商誉 + 无形资产 > 归母权益（有形净资产为负）**MUST** 点名。只报 ROE 不算拆解
- **边界判断清单**：凡换一种读法会翻转某道门的触发结果、或使任一锚点变动 >5% 的判断，逐条列「宽松读法 / 严格读法 / 采用 / 理由」，**默认采用更严的读法**；偏离默认 **MUST** 写具名理由（规则明文、仓库同口径可比性），不得以「更贴卖方 / 更贴现价」为理由

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
| 共享轴 | 仅命中后核对 `frameworks/axes/<轴模块>.py` 的数据与来源，以及人读轴说明 |

### A3. 落盘（仅明确授权后）

1. 按 `references/contracts.md` 写人读框架与 `frameworks/eval/<TICKER>.py`：脚本持有量化输入、来源注释、计算和检查；文档解释结果、关键参数及判断。现价与其派生读数不写入正文。规则拦下但用户知情拍板的，说明未满足的规则与复核条件。
2. 执行脚本及适用的测试；保存结果按 `references/result-publication.md` 执行，确认与消费按 `references/contracts.md` 执行。
3. 新建/改题头/改轴挂载 → `python3 scripts/gen_index.py`
4. 汇报路径、分类、主尺、假设条数、尚缺数据

未授权 → 停在对话。

---

## 步骤 B — 框架纠正（不写 Changelog）

读现行 → 对话列拟改 → 涉倍数走 A2d、涉锚点 **MUST** 走 `construction.md`、两端 zone 走 A2f（研究当日现价，不落盘） → 拟摘要前按 `references/result-publication.md` 准备拟采纳结果和收据 → **授权后**只改现行块 + 必要时 eval，并按该参考保存结果。用户已明确授权时不重复征询，但须先准备结果和收据。过程不进 §4。

## 步骤 C — 事件增量

读现行 → 判断新证据改变哪些输入、模型或观察结论 → 使用临时副本试算 + 必要时 A2f（研究当日现价，不落盘） → 拟摘要前按 `references/result-publication.md` 准备拟采纳结果和收据 → **用户授权后**更新正式脚本并重算、修改现行文档并按该参考保存结果；用户已明确授权时不重复征询，但须先准备结果和收据。引用的客观数字有变化才写更新记录（`references/contracts.md`「框架文档」）。

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
