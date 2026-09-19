# v2（篮子折现率）正式切换 — 设计稿

> 2026-09-20 与用户对齐后定稿。目标：`sediment-framework-v2` 正式替换 v1，`_local/ab/frameworks_v2/` 的 62 份草稿转成正式框架，eval 全量改到不打补丁复现 v2 数字，日报自动读新框架。

## 0. 用户已拍板的分岔

| 分岔 | 决定 |
|---|---|
| eval 层 | **一次到位**：60+2 个 `eval/<T>.py` 全部改到能在 `gordon.py` 篮子常量下跑通并复现草稿 L/M/H |
| BLOCKED 票（ORCL.US） | **搬进正式池，不出 zone**：题头声明 BLOCKED，日报 / 索引 / calibration 识别该状态 |
| 日报范围 | **只切换**：不加共识利率 / 反向压力两行；crontab 不改（`lynch-daily-bands` 自动读新框架）；利率轴 `_AXIS.rates.md` 另起任务 |
| skill 目录 | v2 改名为 `sediment-framework`，v1 目录删除（git 历史保留） |
| 文档形态 | 去掉「v2 草稿」标记；`0b. v2 变更` 节**合并进 §0 / §2 / §3 正文**；与 v1 的差异一句话进 Changelog `### 2026-09-20`（v2 切换事件） |
| 工作区未提交的 v1 改动 | **先单独提交**一个 commit，再开始切换 |
| 执行方式 | 每票一个 subagent（继承 session 模型），分批 6–8 只；主会话逐批验收 |

## 1. 库层（`eval/lib/`）

### 1.1 `gordon.py`

- 删 `R_CONTRACTED / R_OPERATING / R_CONDITIONAL / R_TIERS`，改为篮子表（真源与 skill `valuation-rules.md`「§r 篮子」一致）：

  ```python
  BASKET_R = {1: ("固定合约年金", 0.065), 2: ("管制公用事业", 0.075), 3: ("按量专利许可", 0.085),
              4: ("龙头制造", 0.100), 5: ("大行 / 优质股份行", 0.110), 6: ("周期商品 / 小盘", 0.130),
              7: ("单押 / 国别 / 故事", 0.150)}
  BASKET_VALUES = tuple(r for _, r in BASKET_R.values())
  def basket_r(basket: int) -> float
  def check_r(r, where, basket: int | None = None) -> list[str]   # r ∈ 篮子表；给了 basket 则还要求 r == basket_r(basket)
  ```

- `G_CAP` 常量改函数 `g_cap(r) = min(0.06, r - 0.04)`；`check_g_cap(g, r, where)`、`capped_payout_pe(g_raw, roe, r, payout_observed)` 内部改用 `g_cap(r)`。模块 docstring 里「r = 10%」的措辞改为篮子 r。
- 不新增 `decay_two_stage_pe`（62 份草稿无一使用；YAGNI）。

### 1.2 `inputs.py`

- 新增 `parse_baskets(md) -> dict[str, int]`：扫 `### Inputs` 表里字段名以 `r` 开头（`r`、`r_perp`、`r_sw`…）的行，从来源单元格取第一个 `篮 N`（N ∈ 1..7）；没写篮子的 r 行不进字典。
- eval 通过 `parse_baskets` 拿到每腿篮子号，配合 `check_r(r, where, basket)` 校验「篮子名与 r 一致」。

### 1.3 `frameworks.py`

- `FrameworkMeta` 新增 `blocked: str | None`（BLOCKED 原因短句）与 `baskets: dict[str, int]`。
- 题头第三行契约：`> **状态：BLOCKED**（原因；解封条件）` → `blocked = 括号内全文`。不是 BLOCKED 的票没有这一行。
- BLOCKED 票的 Outputs 仍写一条 `- 底牌 L = … · M = … · H = …` 行（散文里称「对照带」），`_parse_anchors` 不变；zone 由消费者决定不出。

### 1.4 `etf.py`（新，从 `_local/ab/etf.py` 搬）

- 只搬**算法**：`channel(series)`（对数线性拟合 + 剔 2σ 重拟 → 斜率 / σ / 残差 p10 p90 / z）、`slope_since`、`rate_neutral`、regime 断裂判定常量。
- 取数（CSI / CNI / 东财 10y）与缓存也搬进来，缓存路径改 `_local/tmp/etf_index_hist.json`（已是 `_local/tmp`）。ETF 表（`ETF = {...}`）从库里删，各 ETF eval 自己声明自己的指数与 regime。
- 依赖 numpy / pandas（`_local/ab/etf.py` 已在用；仓库其它 eval 已依赖 pandas 与否以实际 `pip show` 为准，缺则记录到 `_local/wiki/tooling-install.md`）。

### 1.5 测试

- `test_gordon_caps.py`：`g_cap` 三个分段（篮 1 → 2.5%、篮 2 → 3.5%、篮 4+ → 6%）；`check_r` 对篮子内 / 外值与篮子不匹配三种情况。
- `test_zones_parse.py`：BLOCKED 题头解析；`parse_baskets` 对单腿 / 多腿 / 无篮子行。
- 现有 `test_gordon_recovery.py` 等按签名变化同步改。

## 2. skill 与仓库契约

### 2.1 目录

- `git mv .claude/skills/sediment-framework-v2 .claude/skills/sediment-framework`（先 `git rm -r` 旧 v1）。
- `SKILL.md` frontmatter：`name: sediment-framework`；description 改回 v1 那种触发词（写估值框架 / 按林奇分类 / 沉淀框架 / 更新框架 / 财报后修订假设 / `/sediment-framework` / `/lynch-framework`），删「仅当点名 v2」「与 v1 互斥」。
- 正文与 references 里：删「A/B 试行期间…」段；`[v2 待实现]` 标记逐条处理——已实现的改成真实路径（`eval/lib/gordon.py BASKET_R` / `g_cap`、`eval/lib/etf.py`、`inputs.parse_baskets`），未实现的（`_AXIS.rates.md` 利率轴、日报共识 / 反向压力两行、`calibration.py` 季度篮级对账、`decay_two_stage_pe`、SOTP δ 反解入库）改成 `[待建]` 并保留语义；`_local/ab/run_ab.py` / `_local/ab/etf.py` / `_local/wiki/...` 的引用改成仓库内路径或删掉。
- `references/valuation-rules.md` 第 5 行「v2 与 v1 的分叉只在 r」段改为现行口径的陈述（不再对照 v1）。

### 2.2 `AGENTS.md`

- 「估值构造口径」段：「永续增长口径（r 三档…）」→「r 由篮子给出（7 篮，真源 `eval/lib/gordon.py BASKET_R` + skill `valuation-rules.md`「§r 篮子」）；g 上限 `min(6%, r−4%)`」。
- 新增契约行：**篮子声明** — Inputs 表每条 `r*` 行来源单元格 MUST 含 `篮 N`；**BLOCKED** — 题头第三行 `> **状态：BLOCKED**（…）`，日报 / 索引 / calibration 不出 zone；BLOCKED 票仍写底牌行作对照带。
- 「跨票可比性」段加：`_INDEX.md` 有篮子列。
- Outputs 行契约（底牌 / V_opt / 候选带）**不变**。

### 2.3 `frameworks/_TEMPLATE.md`

- 题头示例加可选第三行 BLOCKED；Inputs 示例 r 行来源单元格写 `篮 4 龙头制造：<归篮理由>`；§2 Assumptions 示例加一条「归篮」假设；Outputs 披露行示例：`隐含 r(P)`、`③出带`、`敏感区`、`地板（只披露）`。

## 3. 索引 / 日报 / calibration

- `scripts/gen_index.py`：每票一行加篮子列（从 `meta.baskets` 生成 `篮 4 10%`，多腿 `腿名 篮 N r%` 用 ` · ` 连）；BLOCKED 票 zone 列印 `BLOCKED`。（现行索引没有 zone 列则只加篮子列 + 状态。）
- `scripts/daily_bands.py`：`meta.blocked` 为真的票 → 主行印 `⛔ BLOCKED · 对照带 L/M/H`，不判 zone、不写 previous_zone 比较、不进跨带告警；`+V` / 候选带行同样不出。`output/bands/<T>.json` 写 `zone: null, blocked: <原因>`。
- `scripts/calibration.py`：`_r_tiers` 改成篮子列（`篮 N`）；`_g2_max` 的 cap 用该票最低篮子 r 的 `g_cap`；BLOCKED 票跳过并在表尾列出。

## 4. 逐票正式化（subagent）

输入：`_local/ab/frameworks_v2/<T>.md`（草稿）、`frameworks/<T>.md`（v1，已提交）、`eval/<T>.py`（v1）、`_local/wiki/sediment-framework-v2-ticker-decisions.md`、`_local/ab/report.md`。

每票交付：

1. `frameworks/<T>.md` = 草稿正式化：
   - 题头去掉 `**v2 草稿（…）**`；更新日改 2026-09-20；BLOCKED 票加第三行。
   - `## 0b. v2 变更` 整节删除，其内容归位：归篮与理由 → §2 Assumptions 新增具名假设（`Axx 归篮：…`）；隐含 r(P) / ③出带 / 敏感区 / 地板披露 → §3 Outputs 披露行；g2 来源变化 → §3 Inputs 来源单元格；与 v1 差异一句话 → §4 Changelog `### 2026-09-20`（`touched: [r 篮子, g2, 锚点]`）。
   - 正文里「v2：…」「v1 留痕」这类对照措辞收成现行口径陈述；v1 数值只保留在 Changelog 那一条里。
   - Inputs 每条 `r*` 行来源单元格含 `篮 N`。
2. `eval/<T>.py`：从 Inputs 读 r（已是篮子值）与 `parse_baskets`；`check_r(r, where, basket)`；`check_g_cap(g, r, where)`；地板改披露不 `max()`（草稿如此的票）；ETF 四只走 `eval/lib/etf.py`。`check_against_stated` 保留——脚本算出的 L/M/H 必须等于文档底牌。
3. 校验（每票必跑，贴输出）：`python3 eval/<T>.py` 退出 0；下面脚本通过：

   ```bash
   python3 - <<'EOF'
   from pathlib import Path
   from eval.lib.frameworks import load_framework
   from eval.lib.inputs import parse_inputs, stated_zone
   from eval.lib.zones import zone_of
   p = Path("frameworks/<T>.md"); md = p.read_text()
   m = load_framework(p); inp = parse_inputs(md)
   assert "v2 草稿" not in md and "## 0b" not in md
   assert m.baskets, "no 篮 N in r rows"
   if m.blocked: print("BLOCKED", m.blocked)
   else: assert stated_zone(md) == zone_of(inp["price"], m.L, m.M, m.H)
   EOF
   ```

   BLOCKED 票：eval 只校验对照带复现，不断言 zone。

分批：US 20 → HK 21 → A 股 21（含 META.US 新增、600111.SH）。每批完成后主会话跑 `python3 -m pytest eval/lib -q`（或 unittest）与批内 eval。

## 5. 收口

- `python3 scripts/gen_index.py`；`python3 scripts/daily_bands.py --dry-run --no-notify` 出 62 行且 ORCL 行为 BLOCKED；`python3 scripts/calibration.py`。
- 迁移记录 `docs/migrations/2026-09-20-v2-basket-r.md`：每票 v1 L/M/H zone → v2 L/M/H zone、篮子、备注（从 `_local/ab/report.md` 与正式文件生成，脚本一次性，不入库）。
- 提交拆分：① v1 工作区改动；② 库层 + 测试；③ skill 改名与措辞 + AGENTS.md + 模板；④ 索引 / 日报 / calibration；⑤ 框架 + eval（可按市场分 3 个）；⑥ 迁移记录 + `_INDEX.md`。不含 `_local/`。

## 6. 不做的事

- 不建利率轴，不加日报两行，不做季度篮级对账，不做 SOTP δ 反解库函数，不做 `decay_two_stage_pe`。
- 不改 crontab。
- 不修改 `_local/ab/` 任何内容（作为历史留档）。
