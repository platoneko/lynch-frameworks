# v2 篮子折现率正式切换 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `sediment-framework-v2`（篮子折现率）变成仓库现行口径：库、skill、契约、62 份框架 + eval、索引与日报一次切换完成。

**Architecture:** 先改仓库级基础设施（`eval/lib` 篮子常量 / BLOCKED 解析 / ETF 通道库 → skill 改名 → 契约与模板 → 索引 / 日报 / calibration），再用 subagent 逐票把 `_local/ab/frameworks_v2/<T>.md` 草稿正式化并改写 `eval/<T>.py`，每票以「eval 不打补丁复现文档底牌 + 文档 zone 与脚本一致」为验收，最后全量校验并写迁移记录。

**Tech Stack:** Python 3 标准库 + numpy / pandas（ETF 通道）；unittest（`python3 -m pytest eval/lib -q` 或 `python3 -m unittest`）；Longbridge 报价（日报，dry-run 时仍会取数）。

**Spec:** `docs/superpowers/specs/2026-09-20-v2-basket-r-cutover-design.md`

## Global Constraints

- 篮子表七个值：1 6.5% / 2 7.5% / 3 8.5% / 4 10% / 5 11% / 6 13% / 7 15%；单票 MUST NOT 改篮子值。
- 永续 g 上限 `g_cap(r) = min(6%, r − 4%)`。
- 框架 Inputs 每条 `r*` 行的来源单元格 MUST 含 `篮 N`。
- BLOCKED 题头第三行：`> **状态：BLOCKED**（原因；解封条件）`；BLOCKED 票不出 zone，但仍写底牌行（对照带）。
- Outputs 行契约（底牌 / \(V_{opt}\) / 候选带）不变。
- 不改 crontab；不建利率轴；不加日报新行；不改 `_local/` 任何内容；不 `git add` `_local/`。
- 面向用户叙述用简体中文；代码 / 注释 / commit message 英文。
- 每票 eval 的 `check_against_stated` 保留：脚本重算 = 文档底牌（容差 0.05）。

---

### Task 1: `gordon.py` 篮子常量与 g 上限函数

**Files:**
- Modify: `eval/lib/gordon.py:31-64, 87-99`
- Test: `eval/lib/test_gordon_caps.py`

**Interfaces:**
- Produces: `BASKET_R: dict[int, tuple[str, float]]`, `BASKET_VALUES: tuple[float, ...]`, `basket_r(basket: int) -> float`, `check_r(r: float, where: str, basket: int | None = None) -> list[str]`, `g_cap(r: float) -> float`, `check_g_cap(g: float, r: float, where: str) -> list[str]`, `capped_payout_pe(g_raw, roe, r, payout_observed)`（内部改用 `g_cap(r)`）。
- Removes: `R_CONTRACTED / R_OPERATING / R_CONDITIONAL / R_TIERS / G_CAP`。

- [ ] **Step 1: 改测试**（`test_gordon_caps.py` 整文件替换）

```python
"""valuation-rules.md「§r 篮子」「永续增长口径」: basket r, g cap, transition years."""
from __future__ import annotations

import unittest

from eval.lib.gordon import (
    BASKET_R, basket_r, check_g_cap, check_r, check_transition_years, g_cap,
)


class BasketTests(unittest.TestCase):
    def test_seven_baskets(self) -> None:
        self.assertEqual([basket_r(b) for b in range(1, 8)],
                         [0.065, 0.075, 0.085, 0.10, 0.11, 0.13, 0.15])
        self.assertEqual(BASKET_R[4][0], "龙头制造")

    def test_r_in_table_passes(self) -> None:
        self.assertEqual(check_r(0.10, "r_perp"), [])
        self.assertEqual(check_r(0.10, "r_perp", basket=4), [])

    def test_r_off_table_is_flagged(self) -> None:
        errs = check_r(0.12, "r_perp")
        self.assertEqual(len(errs), 1)
        self.assertIn("r_perp", errs[0])

    def test_r_basket_mismatch_is_flagged(self) -> None:
        errs = check_r(0.13, "r_perp", basket=4)
        self.assertEqual(len(errs), 1)
        self.assertIn("篮 4", errs[0])


class GordonCapTests(unittest.TestCase):
    def test_cap_follows_r(self) -> None:
        self.assertAlmostEqual(g_cap(0.065), 0.025)
        self.assertAlmostEqual(g_cap(0.075), 0.035)
        self.assertAlmostEqual(g_cap(0.10), 0.06)
        self.assertAlmostEqual(g_cap(0.15), 0.06)

    def test_g_at_cap_passes(self) -> None:
        self.assertEqual(check_g_cap(0.06, 0.10, "g2_x"), [])
        self.assertEqual(check_g_cap(0.035, 0.075, "g2_x"), [])

    def test_g_above_cap_is_flagged(self) -> None:
        errs = check_g_cap(0.04, 0.075, "g2_x")
        self.assertEqual(len(errs), 1)
        self.assertIn("g2_x", errs[0])

    def test_transition_within_consensus_years_passes(self) -> None:
        self.assertEqual(check_transition_years(1, 1, "n_stage"), [])

    def test_transition_beyond_consensus_years_is_flagged(self) -> None:
        errs = check_transition_years(2, 1, "n_stage")
        self.assertEqual(len(errs), 1)
        self.assertIn("n_stage", errs[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**  `python3 -m pytest eval/lib/test_gordon_caps.py -q` → ImportError（`BASKET_R` 不存在）。

- [ ] **Step 3: 实现**（替换 `gordon.py` 第 31–64 行的三档块与 `G_CAP` 块；`capped_payout_pe` 内的 `G_CAP` 改 `g_cap(r)`；模块 docstring 首段「with r = 10%」改「with r set by the leg's basket (valuation-rules.md「§r 篮子」)」）

```python
# valuation-rules.md「§r 篮子」: r is set by the nature of the business the leg
# belongs to -- seven baskets, repo-level, never a per-ticker dial.  A framework
# names the basket and the reason; the value lives here so the same kind of
# business discounts the same way everywhere and cross-ticker bands stay
# comparable.  Changing a basket value is a repo-level decision taken on two
# quarters of basket-level implied-r evidence, never inside one ticker.
BASKET_R: dict[int, tuple[str, float]] = {
    1: ("固定合约年金", 0.065),
    2: ("管制公用事业", 0.075),
    3: ("按量专利许可", 0.085),
    4: ("龙头制造", 0.100),
    5: ("大行 / 优质股份行", 0.110),
    6: ("周期商品 / 小盘", 0.130),
    7: ("单押 / 国别 / 故事", 0.150),
}
BASKET_VALUES: tuple[float, ...] = tuple(r for _, r in BASKET_R.values())


def basket_r(basket: int) -> float:
    return BASKET_R[basket][1]


def check_r(r: float, where: str, basket: int | None = None) -> list[str]:
    """A leg's r must be a basket value; with the basket named it must be THAT basket's."""
    if basket is not None:
        if basket not in BASKET_R:
            return [f"{where}: 篮 {basket} is not one of 1..7 (valuation-rules.md「§r 篮子」)"]
        if abs(r - basket_r(basket)) > 1e-9:
            return [f"{where}: r={r} but 篮 {basket} {BASKET_R[basket][0]} is {basket_r(basket)} (valuation-rules.md「§r 篮子」)"]
        return []
    if not any(abs(r - v) < 1e-9 for v in BASKET_VALUES):
        return [f"{where}: r={r} not in baskets {BASKET_VALUES} (valuation-rules.md「§r 篮子」)"]
    return []


# valuation-rules.md「永续增长口径」: a perpetual g above the cap is a dial, not a
# state.  The cap keeps at least 4pp between r and g (between r - g = 2% and 4%
# the multiple's elasticity to g passes 25x) and never exceeds the 6% macro
# ceiling however high r is; growth beyond it has to be named as a finite
# transition (two_stage_pe, n bounded by consensus years), never left in the
# perpetuity.
G_CAP_MACRO = 0.06
MIN_R_MINUS_G = 0.04


def g_cap(r: float) -> float:
    return min(G_CAP_MACRO, r - MIN_R_MINUS_G)


def check_g_cap(g: float, r: float, where: str) -> list[str]:
    """A perpetual g must sit at or below g_cap(r); the excess belongs in g1."""
    cap = g_cap(r)
    if g > cap + 1e-9:
        return [f"{where}: g2={g:.4f} > cap {cap:.3f} at r={r} (valuation-rules.md「永续增长口径」) — move the excess into a named g1"]
    return []
```

`capped_payout_pe`：

```python
    cap = g_cap(r)
    if g_raw <= cap + 1e-9:
        return perpetual_pe(g_raw, roe, r)
    return payout_observed / (r - cap)
```

块注释里 `G_CAP` 的提法（第 261 行）改成 `g_cap(r)`。

- [ ] **Step 4: 跑测试通过**  `python3 -m pytest eval/lib/test_gordon_caps.py eval/lib/test_gordon_recovery.py -q` → 全绿（recovery 测试若引用旧名同步改）。
- [ ] **Step 5: 提交**  `git add eval/lib/gordon.py eval/lib/test_gordon_caps.py` ；`git commit -m "feat(gordon): basket discount rates and r-dependent perpetual g cap"`。

---

### Task 2: `inputs.parse_baskets` + `frameworks.py` BLOCKED / baskets

**Files:**
- Modify: `eval/lib/inputs.py`（新增函数）、`eval/lib/frameworks.py:80-95, 241-289`
- Test: `eval/lib/test_zones_parse.py`

**Interfaces:**
- Produces: `parse_baskets(md: str) -> dict[str, int]`；`FrameworkMeta.blocked: str | None`、`FrameworkMeta.baskets: dict[str, int]`。
- Consumes: `re`, 现有 `parse_inputs` 的表格遍历方式。

- [ ] **Step 1: 测试**（追加到 `test_zones_parse.py` 的 `ParseTests`；文件顶部补 `from eval.lib.inputs import parse_baskets`）

```python
    def test_parse_baskets_reads_leg_baskets(self) -> None:
        md = (
            "### Inputs\n\n| 字段名 | 含义 | 取值 / 来源 | as-of |\n|---|---|---|---|\n"
            "| r_sw | 0.10 | 篮 4 龙头制造：软件年金 | 2026-09-20 |\n"
            "| r_oci | 0.15 | 篮 7 单押：融资未落定 | 2026-09-20 |\n"
            "| r_disc | 0.10 | 年漂移折现，不归篮 | 2026-09-20 |\n"
            "| g2 | 0.06 | 篮 4 下截顶 | 2026-09-20 |\n\n### Formula\n"
        )
        self.assertEqual(parse_baskets(md), {"r_sw": 4, "r_oci": 7})

    def test_blocked_header_is_parsed(self) -> None:
        import tempfile
        md = (
            "# X.US — 甲 / X Inc.\n\n"
            "> 林奇：`stalwart` | 更新：2026-09-20 | eval: eval/X.US.py\n"
            "> **状态：BLOCKED**（③ 出带：篮 4 仍出带；解封 = ROIC 证据 ≥14%）\n"
            "> 主尺：x\n\n## 3\n\n### Inputs\n\n| 字段名 | 含义 | 取值 | as-of |\n|---|---|---|---|\n"
            "| r_perp | 0.10 | 篮 4 龙头制造 | 2026-09-20 |\n\n"
            "### Outputs\n\n- 价带锚点（USD）对照带：L = **57.35** · M = **77.23** · H = **136.83**\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "X.US.md"
            p.write_text(md, encoding="utf-8")
            m = load_framework(p)
        self.assertEqual(m.blocked, "③ 出带：篮 4 仍出带；解封 = ROIC 证据 ≥14%")
        self.assertEqual(m.baskets, {"r_perp": 4})
        self.assertEqual((m.L, m.M, m.H), (57.35, 77.23, 136.83))
```

- [ ] **Step 2: 跑测试确认失败**  `python3 -m pytest eval/lib/test_zones_parse.py -q -k "baskets or blocked"`。

- [ ] **Step 3: 实现**

`inputs.py` 末尾追加：

```python
_BASKET_TAG = re.compile(r"篮\s*([1-7])")


def parse_baskets(md: str) -> dict[str, int]:
    """{r-field: basket} for every `r*` Inputs row whose source cell names `篮 N`.

    valuation-rules.md「§r 篮子」: the framework names the basket, the value
    lives in gordon.BASKET_R.  Rows without a basket tag (e.g. `r_disc`, the
    year-drift discount) are simply absent from the dict.
    """
    out: dict[str, int] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or not cells[0].startswith("r"):
            continue
        m = _BASKET_TAG.search(cells[2])
        if m:
            out[cells[0]] = int(m.group(1))
    return out
```

`frameworks.py`：

```python
# Header line 3 of a framework the rules stopped (valuation-rules.md「BLOCKED 的语义」):
#   > **状态：BLOCKED**（reason; unblock condition）
# The deck line is still written (对照带) so the anchors parse; consumers
# (digest / index / calibration) must not derive a zone from it.
_BLOCKED = re.compile(r"^>\s*\*\*状态：BLOCKED\*\*\s*[（(]([^）)]*)[）)]", re.MULTILINE)
```

`FrameworkMeta` 新增字段（放 `candidate_label` 之后）：

```python
    blocked: str | None = None
    baskets: dict[str, int] = field(default_factory=dict)
```

（`from dataclasses import dataclass, field`；frozen dataclass 允许 `field(default_factory=dict)`。）

`load_framework` 中 `currency = _parse_currency(md)` 之后：

```python
    bm = _BLOCKED.search(md)
    blocked = bm.group(1).strip() if bm else None
    baskets = parse_baskets(md)
```

并传入构造：`blocked=blocked, baskets=baskets`。`frameworks.py` 顶部 `from eval.lib.inputs import parse_baskets`（`inputs.py` 不导入 frameworks，无循环）。

- [ ] **Step 4: 跑测试通过**  `python3 -m pytest eval/lib/test_zones_parse.py -q -k "baskets or blocked"`。
- [ ] **Step 5: 提交**  `git commit -m "feat(frameworks): parse leg baskets and BLOCKED header"`。

---

### Task 3: `eval/lib/etf.py` 通道库

**Files:**
- Create: `eval/lib/etf.py`（从 `_local/ab/etf.py` 搬 `_fetch / history / channel / rates / rate_neutral / slope_since`；删 `ETF` 表、`inputs()`、`run()`、`report_rows()`）
- Test: `eval/lib/test_etf_channel.py`

**Interfaces:**
- Produces: `history(src: str, code: str) -> pd.Series`（日期索引，缓存 `_local/tmp/etf_index_hist.json`）、`channel(s: pd.Series) -> dict`（`slope, sigma, p10, p90, z, trend_now, resid_now`）、`slope_since(s, start: str) -> float`、`rates(ccy) -> pd.Series`、`rate_neutral(s, rf, rf_mid, dy) -> dict`、`REGIME_GAP = 0.05`、`SUBWINDOWS = ("2019-01-01", "2021-01-01")`。
- 各 ETF eval 自己声明 `src / code / regime / dividend / dy`。

- [ ] **Step 1: 测试**（纯算法，不联网）

```python
"""eval.lib.etf channel maths (valuation-rules.md「§ETF 例外」)."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from eval.lib.etf import channel, slope_since


def _synthetic(slope: float = 0.08, n_years: int = 6) -> pd.Series:
    idx = pd.date_range("2019-01-01", periods=n_years * 252, freq="B")
    t = np.arange(len(idx)) / 252.0
    rng = np.random.default_rng(0)
    y = np.exp(np.log(1000.0) + slope * t + rng.normal(0, 0.02, len(idx)))
    return pd.Series(y, index=idx)


class ChannelTests(unittest.TestCase):
    def test_slope_recovers_trend(self) -> None:
        c = channel(_synthetic(0.08))
        self.assertAlmostEqual(c["slope"], 0.08, delta=0.01)
        self.assertLess(c["p10"], 0.0)
        self.assertGreater(c["p90"], 0.0)

    def test_slope_since_subwindow(self) -> None:
        s = _synthetic(0.05)
        self.assertAlmostEqual(slope_since(s, "2021-01-01"), 0.05, delta=0.015)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**（ImportError）。
- [ ] **Step 3: 实现**：复制 `_local/ab/etf.py` 的函数体到 `eval/lib/etf.py`；`channel()` 返回 dict 的键名以现有实现为准并在 docstring 列出；`history(src, code)` 取代原 `history(ticker)`（查表改成参数）。模块 docstring 保留原第一段（为什么 ETF 不用公司尺），去掉「arm B」措辞。
- [ ] **Step 4: 跑测试通过**  `python3 -m pytest eval/lib/test_etf_channel.py -q`。
- [ ] **Step 5: 提交**  `git commit -m "feat(etf): total-return trend channel library for passive baskets"`。

---

### Task 4: skill 改名与措辞、`AGENTS.md`、模板

**Files:**
- `git rm -r .claude/skills/sediment-framework`；`git mv .claude/skills/sediment-framework-v2 .claude/skills/sediment-framework`（先 `git add` 未跟踪的 v2 目录）
- Modify: `.claude/skills/sediment-framework/SKILL.md`、`references/*.md`、`AGENTS.md`、`frameworks/_TEMPLATE.md`

- [ ] **Step 1: 目录**  上面三条 git 命令。
- [ ] **Step 2: `SKILL.md`**
  - frontmatter：`name: sediment-framework`；description 改为：
    ```
    与用户多轮对话，对齐林奇分类、归篮（篮子折现率）、专属属性、假设与可演算主尺后，再把估值框架沉淀落盘。
    在用户要求「写估值框架」「按林奇分类」「沉淀框架」「更新框架」「财报后修订假设」「归篮」、
    「入库标的」、说出 /sediment-framework 或 /lynch-framework，
    或明确要以可复现方式把某 ticker 的专属估值逻辑写入 frameworks/ 时使用。
    默认先持续对话，禁止一上来就写文件。不要用于纯行情查询、下单、或 invest 候选池挖掘。
    ```
  - 标题改「沉淀估值框架（sediment-framework · 篮子折现率）」；第 13 行整段改为：「折现率 \(r\) 按生意性质归入 7 个篮子（`references/valuation-rules.md`「§r 篮子」；值的真源 `eval/lib/gordon.py` `BASKET_R`），\(G_{cap}=\min(6\%, r-4\%)\)（`gordon.g_cap`）。利率轴 `_AXIS.rates.md` 与日报的共识 / 反向压力两行 **[待建]**。」
  - 硬约束 14：「篮子值是仓库级（`gordon.py` `BASKET_R`）」；Inputs `r*` 行来源单元格 **MUST** 写 `篮 N`（eval 用 `parse_baskets` 校验）。
  - A2 步 7「报 \(r_f\) 敏感带 + 共识列 + 反向压力列」后加「（利率轴 **[待建]** 前只报隐含 r(P)）」。
  - A3 落盘：加「BLOCKED 票题头第三行 `> **状态：BLOCKED**（原因；解封条件）`，底牌行写对照带」。
- [ ] **Step 3: `references/valuation-rules.md`**：第 5 行段落改为「\(r\) 按生意性质归 7 个篮子（「§r 篮子」）；派生：\(G_{cap}\) 随 r、域判定表、峰形区处理、单调区不可达、DDM 触发、周期票 regime / point 双口径、利率轴敏感性。篮子值真源 `eval/lib/gordon.py` `BASKET_R`；eval 用 `check_r(r, where, basket)` + `check_g_cap(g, r, where)` 校验。」删「A/B 期间…」句。全文 `grep -n "v2 待实现\|A/B\|_local/ab\|run_ab"` 逐条：已实现 → 真实路径；未实现 → `[待建]`；`_local/ab/etf.py` → `eval/lib/etf.py`；`_local/wiki/...` 引用保留（用户私有设计稿）但加「（本地设计稿）」。`construction.md` / `checklist.md` / `heuristics.md` / `zone-reflection.md` 同样 grep 处理。
- [ ] **Step 4: `AGENTS.md`**
  - 「估值构造口径（真源已移至 skill）」段第一句「永续增长口径（r 三档、…）」→「永续增长口径（r 由 7 个篮子给出，值的真源 `eval/lib/gordon.py` `BASKET_R`；g 上限 `min(6%, r−4%)`；…）」。
  - 「跨票可比性」段末加：「`_INDEX.md` 每票带篮子列（各腿 `篮 N r%`），由 Inputs `r*` 行的 `篮 N` 标签生成。」
  - 新增小节（放在「未建模期权」行契约之前）：

    ```
    **篮子声明 — 行契约**：Inputs 表每条 `r*` 行（`r_disc` 年漂移折现除外）的来源单元格 **MUST** 含 `篮 N`（N ∈ 1..7）+ 归篮理由；eval 以 `parse_baskets` + `check_r(r, where, basket)` 校验值与篮子一致。

    **BLOCKED — 题头契约**：规则拦下的票仍入池，题头第三行 `> **状态：BLOCKED**（原因；解封条件）`；Outputs 仍写底牌行（散文称对照带）。`daily_bands.py` / `_INDEX.md` / `calibration.py` 对 BLOCKED 票 **MUST NOT** 出 zone、**MUST NOT** 触发跨带告警。
    ```
- [ ] **Step 5: `frameworks/_TEMPLATE.md`**：题头加第三行示例 `> **状态：BLOCKED**（仅规则拦下时；原因；解封条件）` 并注明可选；Inputs 示例加 `| r_perp | 永续折现率 | 篮 4 龙头制造：<一句归篮理由> | |`；§2 加示例行 `| A2 | 归篮：整公司 → 篮 4 龙头制造（理由）；CAPM 粗筛 x% | active | | r_perp |`；Outputs「可比性读数」下加披露行示例：
  ```
  - **隐含 r(P)**：（市价在本尺、本 g 下反解的 r，与篮子的偏离量）
  - **③ 出带 / 敏感区 / 地板**：（生成倍数与自身实测带的关系；g2 ±1pp 是否翻 zone；资产地板值——只披露不 max）
  ```
- [ ] **Step 6: 校验**  `grep -rn "v2 待实现\|A/B 试行\|sediment-framework-v2" .claude/skills AGENTS.md frameworks/_TEMPLATE.md` 无输出。
- [ ] **Step 7: 提交**  `git commit -m "feat(skill): sediment-framework v2 (basket r) replaces v1; contract and template updated"`。

---

### Task 5: 索引 / 日报 / calibration 支持篮子与 BLOCKED

**Files:**
- Modify: `scripts/gen_index.py:98-140`、`scripts/daily_bands.py:31-53, 126-170, 194-218, 236-335`、`scripts/calibration.py:24, 54-80, 108-140`、`eval/lib/bands_io.py`
- Test: `eval/lib/test_daily_bands.py`（现有；追加）、`eval/lib/test_zones_parse.py`

**Interfaces:**
- Consumes: `FrameworkMeta.blocked / .baskets`（Task 2）、`gordon.BASKET_R / g_cap`（Task 1）。
- Produces: `frameworks.basket_label(meta) -> str`（`篮 4 10%`；多腿 `r_sw 篮 4 10% · r_oci 篮 7 15%`；无 → `—`）；`daily_bands.Row.zone: str | None`；bands JSON `zone: null, "blocked": "<原因>"`。

- [ ] **Step 1: 测试**（`test_daily_bands.py` 追加；按该文件现有 fixture 写法构造 `FrameworkMeta`）

```python
    def test_blocked_ticker_prints_no_zone_and_never_crosses(self) -> None:
        meta = FrameworkMeta(ticker="X.US", path=Path("frameworks/X.US.md"), name="x", L=57.35, M=77.23, H=136.83,
                             currency="USD", eval_script=None, lynch_primary="stalwart", lynch_secondary=None,
                             blocked="③ 出带；解封 = ROIC ≥14%")
        r = Row(meta=meta, price=150.0, zone=None, previous_zone="stretched", crossed=False, notes=[], record={})
        lines = format_pool_lines(r)
        self.assertEqual(lines[0], "⛔ X.US 150.0 USD")
        self.assertEqual(lines[1], "BLOCKED（③ 出带；解封 = ROIC ≥14%）· 对照带 L/M/H = 57.35/77.23/136.83")
        self.assertFalse(r.any_crossed)
```

`test_zones_parse.py` 追加：

```python
    def test_basket_label(self) -> None:
        from eval.lib.frameworks import basket_label
        base = dict(path=Path("x"), name="x", L=1, M=2, H=3, currency="USD", eval_script=None,
                    lynch_primary="stalwart", lynch_secondary=None)
        self.assertEqual(basket_label(FrameworkMeta(ticker="A", baskets={"r_perp": 4}, **base)), "篮 4 10%")
        self.assertEqual(basket_label(FrameworkMeta(ticker="B", baskets={"r_sw": 4, "r_oci": 7}, **base)),
                         "r_sw 篮 4 10% · r_oci 篮 7 15%")
        self.assertEqual(basket_label(FrameworkMeta(ticker="C", **base)), "—")
```

- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现**

`frameworks.py`：

```python
def basket_label(meta: "FrameworkMeta") -> str:
    """Human label for the index / digest: `篮 4 10%`, per leg when several."""
    from eval.lib.gordon import BASKET_R  # local import: gordon does not depend on frameworks
    if not meta.baskets:
        return "—"
    cells = [f"篮 {b} {BASKET_R[b][1]:.1%}".replace(".0%", "%") for b in meta.baskets.values()]
    if len(cells) == 1:
        return cells[0]
    return " · ".join(f"{k} {c}" for k, c in zip(meta.baskets, cells))
```

`daily_bands.py`：
- `Row.zone: str | None`；`any_crossed` 不变（BLOCKED 时三个 crossed 都为 False）。
- `format_pool_lines` 开头：

```python
    if r.meta.blocked:
        title = r.meta.ticker if r.meta.ticker.endswith(".US") else f"{r.meta.ticker} {_short_name(r.meta)}"
        return [
            f"⛔ {title} {_fmt_price(r.price, r.meta.currency)}",
            f"BLOCKED（{r.meta.blocked}）· 对照带 {format_lmh(r.meta.L, r.meta.M, r.meta.H)}",
        ]
```

- `run()` 循环里：`zone = None if meta.blocked else zone_of(...)`；`option_zone` / `cand_zone` 同样在 BLOCKED 时为 `None`；`crossed = False if meta.blocked else zone_changed(...)`（三个都这样）；`build_record(..., zone=zone, blocked=meta.blocked)`。
- `bands_io.build_record` 加参数 `blocked: str | None = None`，写进记录 `"blocked": blocked`；`zone` 类型放宽为 `str | None`。
- `build_cross_post` 中读 `r.zone` 的地方对 None 打 `?`（已有 `or "?"` 模式的沿用）。

`gen_index.py`：每票行由 `- [T](./T.md) — 中文名` 改为 `- [T](./T.md) — 中文名 · 篮子：<basket_label> [· **BLOCKED**]`；需要 `load_framework` 而不只是标题解析——`build_index` 内对每个 path 调 `load_framework(path)` 取 `baskets/blocked`（解析失败则 raise，索引不能带错数）。

`calibration.py`：`from eval.lib.gordon import g_cap`；`_r_tiers` 改名 `_baskets(m)` 返回 `"/".join(str(b) for b in sorted(set(m.baskets.values())))` 或 `—`，表头 `r档` → `篮`；`_g2_max(m)`：`cap = g_cap(min(basket_r(b) for b in m.baskets.values()))` 若有篮子否则 `0.06`；`main()` 开头 `metas = [m for m in load_all_frameworks() if not m.blocked]`，末尾打印 `BLOCKED（不进分布）: T1, T2`。

- [ ] **Step 4: 跑测试**  `python3 -m pytest eval/lib -q`（`test_all_frameworks_parse` 的 INTC 期望值此时仍是旧值——留到 Task 8 统一改）。
- [ ] **Step 5: 提交**  `git commit -m "feat(digest,index,calibration): basket column and BLOCKED state"`。

---

### Task 6: 逐票正式化（62 只，subagent 每票一只）

**Files（每票）:**
- Modify: `frameworks/<T>.md`（以 `_local/ab/frameworks_v2/<T>.md` 为底）、`eval/<T>.py`
- 新增：`frameworks/META.US.md`、`eval/META.US.py`（以 `_local/ab/meta_v2.py` 为底改成标准 eval）

**批次**：US（AEHR ALB AVGO BE COHR GFS GLW GOOG INTC LITE META MRVL NOK NVDA ORCL QCOM SOFI TSEM TSM WOLF）→ HK（0189 0700 0728 0857 0883 1072 1378 1766 1772 1810 1898 2631 6655 9696 9988）→ A（000100 000338 000543 000725 000792 000933 002532 002895 002897 159263 159307 300014 300750 513530 520900 600011 600036 600096 600111 600309 600499 601600 601899 603799 603871 603993）。每批 6–8 只并行。

**Subagent 简报（逐字给每只票，替换 `<T>`）**：

```
你在 /home/neko/plat1ko/lynch 仓库把 <T> 的 v2（篮子折现率）草稿正式化。只改两个文件：frameworks/<T>.md 与 eval/<T>.py。MUST NOT 改 eval/lib、scripts、其它票、_local/ 下任何文件；MUST NOT git commit。

先读（按序）：
1. docs/superpowers/specs/2026-09-20-v2-basket-r-cutover-design.md §1、§4（契约）
2. _local/ab/frameworks_v2/<T>.md（草稿 = 目标数字与叙述）
3. frameworks/<T>.md（v1 现行，已提交）与 eval/<T>.py（v1 eval）
4. eval/lib/gordon.py（BASKET_R / basket_r / check_r(r, where, basket) / g_cap / check_g_cap(g, r, where)）、eval/lib/inputs.py（parse_inputs / parse_baskets / check_against_stated）
5. _local/wiki/sediment-framework-v2-ticker-decisions.md 里 `### <T>` 节（若有）
6. ETF（159263 / 159307 / 513530 / 520900）另读 eval/lib/etf.py 与 _local/ab/etf.py 里该票的 ETF 表项

frameworks/<T>.md 交付：
- 以草稿全文为底写回 frameworks/<T>.md。题头第 2 行删 `**v2 草稿（…）**`，更新日改 2026-09-20；草稿题头有 `**v2 状态：BLOCKED**` 的票改成独立第三行 `> **状态：BLOCKED**（原因一句；解封条件一句）`。
- 删除整节 `## 0b. v2 变更`，内容归位：归篮与理由 → §2 Assumptions 新增一条具名假设（编号接现有最大号；假设文本写「归篮：<腿> → 篮 N <篮名>（理由）；CAPM 粗筛 x%」）；隐含 r(P)、③ 出带、敏感区、地板披露 → §3 Outputs「可比性读数」之后各一行（`- **隐含 r(P)**：…`、`- **③ 出带**：…`、`- **敏感区**：…`、`- **地板（只披露）**：…`，没有的不写）；g2 来源口径 → Inputs 对应行来源单元格；与 v1 的 L/M/H/zone 差异一句话 → §4 Changelog 追加 `### 2026-09-20` 节（`- v2 切换（篮子 r）：L/M/H v1 a/b/c → d/e/f，zone x → y；篮子 …` + `- touched: [...]`），草稿 Changelog 里的「v2 草稿」条目并入这一节。
- 正文（§0 / §1 / §2 / §3）里的「v2：…」「v1 留痕」「（与 v1 同值）」「_local/ab/…」「A/B」措辞收成现行口径陈述；v1 数值只留在 Changelog 那一条。`sediment-framework-v2` 字样改 `sediment-framework`；`_local/ab/baskets.py` / `report.md` / `run_ab.py` 引用删掉或改成「§2 Axx」。
- Inputs 每条 `r*` 行（r_disc 除外）来源单元格 MUST 含 `篮 N`。
- Outputs 底牌行格式不变：`- 底牌 L = **x** · M = **y** · H = **z** · 切点 A = **…** · B = **…**（币种）`；BLOCKED 票也写（散文称对照带），`现价 → zone` 处写「BLOCKED，不出 zone」。
- 数字一律取草稿；不得重新拍数。草稿与 ticker-decisions 专属节冲突时以专属节为准并在最终回复里说明。

eval/<T>.py 交付：
- 从 Inputs 读 r（已是篮子值）；`baskets = parse_baskets(md)`；每腿 `errors += check_r(r, "r_x", baskets.get("r_x"))`（篮子缺失也算错：`if "r_x" not in baskets: errors.append(...)`）；`check_g_cap(g2, r, "g2")`；删除对 R_OPERATING / R_TIERS / G_CAP 的引用；docstring 里 r=10% 三档措辞改篮子。
- 草稿说「地板只披露不 max()」的票：L 不再 max(地板)，地板值打印到 stdout。
- 草稿说 BLOCKED 的票：仍重算对照带并 `check_against_stated` 比对 L/M/H，但不断言 zone（stated_zone 为 None 时跳过 zone 比较——自己在脚本里处理，不改 inputs.py）。
- ETF 四只：用 eval/lib/etf.py 的 history/channel/slope_since（520900 走 look-through：按草稿的成分篮子 r 加权）；网络取数走缓存 _local/tmp/etf_index_hist.json（已存在）。
- 其它校验（阶梯、桥、护栏）沿用 v1 逻辑，按草稿数值调整期望。

验收（都要跑并把输出贴进最终回复）：
1. `cd /home/neko/plat1ko/lynch && python3 eval/<T>.py` 退出码 0（BLOCKED 票允许打印 BLOCKED 但退出 0）。
2. 
   python3 - <<'EOF'
   from pathlib import Path
   from eval.lib.frameworks import load_framework
   from eval.lib.inputs import parse_inputs, stated_zone
   from eval.lib.zones import zone_of
   p = Path("frameworks/<T>.md"); md = p.read_text()
   m = load_framework(p); inp = parse_inputs(md)
   assert "v2 草稿" not in md and "## 0b" not in md and "_local/ab" not in md and "sediment-framework-v2" not in md, "leftover draft wording"
   assert m.baskets, "no 篮 N in r rows"
   if m.blocked: print("BLOCKED", m.blocked)
   else: assert stated_zone(md) == zone_of(inp["price"], m.L, m.M, m.H), (stated_zone(md), zone_of(inp["price"], m.L, m.M, m.H))
   print("OK", m.ticker, m.L, m.M, m.H, m.baskets, m.blocked)
   EOF
3. `grep -n "v1 留痕\|A/B\|待实现" frameworks/<T>.md` 应为空（Changelog 那条除外）。

最终回复：一张表 `ticker | v1 L/M/H zone | v2 L/M/H zone | 篮子 | g2 | 备注`，加两段验收输出原文，以及你没能落地的点。
```

- [ ] **Step 1: 批 US-1**（AEHR ALB AVGO BE COHR GFS GLW）并行派 7 个 subagent。
- [ ] **Step 2: 验收**：主会话逐票跑 `python3 eval/<T>.py` 与上面 python 校验；不过的回给同一 subagent 修。
- [ ] **Step 3: 提交本批**  `git add frameworks/<批内票>.md eval/<批内票>.py`；`git commit -m "feat(frameworks): v2 basket-r cutover — US batch 1 (AEHR ALB AVGO BE COHR GFS GLW)"`。
- [ ] **Step 4–15**：其余批次同样三步：US-2（GOOG INTC LITE META MRVL NOK NVDA）、US-3（ORCL QCOM SOFI TSEM TSM WOLF）、HK-1（0189 0700 0728 0857 0883 1072 1378 1766）、HK-2（1772 1810 1898 2631 6655 9696 9988）、A-1（000100 000338 000543 000725 000792 000933 002532）、A-2（002895 002897 159263 159307 300014 300750 513530）、A-3（520900 600011 600036 600096 600111 600309 600499）、A-4（601600 601899 603799 603871 603993）。

---

### Task 7: 全量校验

- [ ] **Step 1**  `for f in eval/*.py; do python3 $f >/dev/null 2>&1 || echo "FAIL $f"; done` → 无输出。
- [ ] **Step 2**  `python3 scripts/gen_index.py`；检查 `frameworks/_INDEX.md` 62 票、ORCL 带 BLOCKED、每票有篮子。
- [ ] **Step 3**  `python3 scripts/daily_bands.py --dry-run` → 62 块，ORCL 为 `⛔ … BLOCKED`；`output/bands/` 不写（dry-run）。
- [ ] **Step 4**  `python3 scripts/calibration.py` → 出表，末尾列 BLOCKED。
- [ ] **Step 5**  `python3 -m pytest eval/lib -q`：把 `test_all_frameworks_parse` 的 INTC 期望值改为 v2 正式文件的 L/M/H；`test_candidate_band` 的过期期望字符串按现行 `format_pool_lines` 输出更新（基线在切换前已红，属过期期望）。全绿。
- [ ] **Step 6: 提交**  `git commit -m "chore: regenerate index; refresh stale parser expectations after v2 cutover"`。

---

### Task 8: 迁移记录

**Files:**
- Create: `docs/migrations/2026-09-20-v2-basket-r.md`

- [ ] **Step 1**  临时脚本（放 scratchpad，不入库）：对每票读 `git show d45a3e5:frameworks/<T>.md` 的 v1 锚点（`load_framework` 于临时文件）与现行文件的 v2 锚点、`baskets`、`blocked`，Inputs `price` 下的两个 zone，生成 markdown 表（按 US / HK / A 分节），前言写：切换日期、篮子表、g 上限、BLOCKED 票、zone 迁移矩阵 5×5 计数、`_local/ab/report.md` 为原始 A/B 报告（本地）。
- [ ] **Step 2**  提交  `git commit -m "docs: v2 basket-r migration record (zone changes per ticker)"`。

---

### Task 9: 收尾汇报

- [ ] 用中文汇报：改了什么 / 每批验收结果 / 没落地的点（利率轴、日报两行、季度篮级对账 → 待建）/ crontab 未动、下次 16:13 自动按新框架发日报。
