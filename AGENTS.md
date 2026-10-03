# lynch-frameworks — 框架契约

长线标的的**估值框架**内容仓库，检出在代码仓库 `lynch/` 的 `frameworks/` 下（代码仓库忽略此目录）。标的由用户指定；挖掘在 `../invest`，本仓不负责。

**路径约定**：本文件与 skill 里的路径一律相对 `lynch/`（研究会话的根）。例外两条：框架题头的 `eval: eval/<TICKER>.py` 相对本仓库根解析；本仓文档里裸写的 `AGENTS.md` 指本文件（`frameworks/AGENTS.md`），不是代码仓库的开发契约。提交框架改动要在 `frameworks/` 里 `git commit`，`lynch/` 根的 `git status` 看不到这里。

面向用户的说明用**简体中文**。代码标识符、`formula_id`、林奇枚举值用英文。

## 真源

| 资产 | 路径 |
|------|------|
| 单票估值框架 | `frameworks/<TICKER>.md` |
| 标的池 | 扫 `frameworks/*.md`（排除 `_TEMPLATE.md` 及 `_` 前缀，以及本仓文档 `AGENTS.md` / `README.md`） |
| 模板 | `frameworks/_TEMPLATE.md` |
| 共享情景轴 | `frameworks/axes/<轴名>.md`（逻辑 id 仍写 `_AXIS.<轴名>`；不进标的池） |
| 同业组 | `frameworks/peers/<组名>.md`（逻辑 id `_PEER.<组名>`；组内同一把尺：腿拆法、腿 \(g_2\)、借用过渡年、\(V_{opt}\) 单位；不进标的池） |
| 演算（后置） | `frameworks/eval/<TICKER>.py`（本仓）；库 `eval/lib/`（代码仓库） |
| 跨票口径体检 | `scripts/calibration.py`（代码仓库） |

最终真源是仓库里的 Markdown，但沉淀过程 **MUST** 先多轮对话对齐；**MUST NOT** 在用户明确说「可以落盘 / 写成文件 / 确认写入」之前创建或覆盖 `frameworks/*.md`。  
沉淀或更新时 **MUST** 使用 skill **`sediment-framework`**（`/sediment-framework` / `/lynch-framework`）。  
**MUST NOT** 维护 `universe.yaml`（已废止；池子与主尺索引均在框架文件内）。

## 林奇分类

- `lynch_primary` 必填；`lynch_secondary` 可选。
- 取值仅限：`slow_grower` | `stalwart` | `fast_grower` | `cyclical` | `turnaround` | `asset_play`
- **MUST NOT** 把专属叙事（代工重估、净现金修正 PE 等）写成 secondary；那些只写在框架 §1 / Assumptions。

## 框架文档

- 固定章节：§0 现行结论 → §1 专属属性 → §2 Assumptions → §3 可演算块 → §4 Changelog
- 假设状态：`active` | `confirmed` | `weakened` | `falsified`（证伪改状态，不删行）
- 事件更新：**MUST** 增量修改，**MUST NOT** 无确认整页推翻
- 题头、可选共识行、时间线与 Changelog 何时写、引用规则版本的写法：写或改标的文档之前读 skill `references/contracts.md`「框架文档」。

## 价带约定（§3 / 日后 eval）— 五档

每票框架算出三个锚点 **\(L < M < H\)**（如何得到由该票主尺决定；例：不对称 SOTP）。

用相邻中点划分五个 **zone**（英文 id 稳定，中文名给人看）：

| zone id | 中文 | 区间 |
|---------|------|------|
| `deep_discount` | 深度折价 | \(P < L\) |
| `conservative` | 保守 | \([L,\ (L+M)/2)\) |
| `neutral` | 中性 | \([(L+M)/2,\ (M+H)/2)\) |
| `optimistic` | 乐观 | \([(M+H)/2,\ H]\) |
| `stretched` | 叙事溢价 | \(P > H\) |

语义：

- **深度折价**：低于保守可算地板（相对本框架）
- **保守 / 中性 / 乐观**：仍在框架内；乐观 ≤「已建模的成功/上沿情景」
- **叙事溢价**：超过框架内成功上沿；仍可能用 stretch 叙事解释，但是 **H 以外**。名字是历史沿用——H 以上的价格可能来自叙事 / 街倍数 / 费用结构 / 折现率差 / 分支未定，读日报时结合该票 Assumptions 理解，不望文生义（例：`513530.SH` 的来源是 QDII 费 6%，`0883.HK` 的是折现率差——市场要的 r 高于篮子）

### 估值构造口径（真源已移至 skill）

锚点语义（L/M/H 各定价什么）、价带偏离反思的语义门槛、永续增长口径（r 由 7 个篮子按生意性质给出——值的真源 `eval/lib/gordon.py` `BASKET_R`；g 上限 `min(6%, r−4%)`；Gordon、增长的表达顺序、g2 来源优先序、构造规则冲突的裁决顺序、两段式过渡、谷底档 / regime-point 双口径）、L 是情景不是地板、可比性的构造要求、\(V_{opt}\) 与候选带的判据、共享轴的构造要求——**真源在 `.claude/skills/sediment-framework/references/valuation-rules.md`**，本文与标的文档里出现的「AGENTS.md「永续增长口径」」等旧指针均指向该文件。这些只在写 / 纠正框架时需要；日报与 eval 库只依赖本文件与 `references/contracts.md` 的行契约。

价带与 zone 由脚本演算；弱 LLM 至多做归因。**MUST NOT** 让弱流水线擅自改 `frameworks/*.md` 或自行改概率锚点。  
标的文档 **MUST** 输出锚点 \(L/M/H\)、切点 \(A/B\)、以及**填入本票数字的五档价格区间表**；**MUST NOT** 写现行 `zone`——现价落在哪档只由日报与 app 用实时报价现场算（2026-09-27 定）。  
**MUST NOT** 在标的文档重复规则长文；契约核心在本文件，写作细则在 skill `references/contracts.md`，构造口径真源在 skill references，标的文档只落数字区间。

**现价 — 禁写契约（2026-09-27 定）**：标的文档（§4 Changelog 除外）**MUST NOT** 含本票现价及其函数（现行 zone、市价隐含 r / g / p / \(\delta\)、现价到锚点或切点的距离、当前市值与当前倍数……）；现价 **MAY** 在研究对话里作诊断，但现价与诊断结论都 **MUST NOT** 落盘。允许落盘的市场数据清单与 `just check` 机器守卫：`references/contracts.md` 同名节。

### 行契约与写作细则

只在写或改标的文档、轴文件时用，全文在 skill `references/contracts.md`（同名小节）：Ticker 文件名、框架文档题头与 Changelog、跨票可比性、篮子声明 — 行契约、BLOCKED 只在落盘前、未建模期权（\(V_{opt}\)）— 行契约、共识升级候选带（candidate）— 行契约、共享情景轴与共识行、同业组 — 行契约、现价禁写的允许清单与机器守卫、日报与 \(r_f\) 读数行。

## 不要做的事

- 不要在本仓做候选池挖掘或仓位执行建议冒充框架
- 不要把 invest 的 Theme/View YAML 当作本仓估值真源
- 不要编造无来源的财务数字
