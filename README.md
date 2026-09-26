# lynch-frameworks

lynch 的估值框架内容：单票框架 `<TICKER>.md`、共享情景轴 `axes/`、每票演算 `eval/<TICKER>.py`、沉淀流程 skill `.claude/skills/sediment-framework/`。

**不能单独使用**：检出在代码仓库 [`lynch`](https://github.com/platoneko/lynch) 的 `frameworks/` 下，演算脚本和日报依赖外层 `lynch/eval/lib/`。

```bash
git clone git@github.com:platoneko/lynch.git && cd lynch
git clone git@github.com:platoneko/lynch-frameworks.git frameworks
cd frameworks && just check
```

契约见 `AGENTS.md`；研究会话在 `lynch/` 根打开。
