# lynch-frameworks

lynch 的估值框架内容：单票框架 `<TICKER>.md`、共享情景轴 `axes/`、每票演算 `eval/<TICKER>.py`、沉淀流程 skill `.claude/skills/sediment-framework/`。

**不能单独使用**：检出在代码仓库 [`lynch`](https://github.com/platoneko/lynch) 的 `frameworks/` 下，演算脚本和日报依赖外层 `lynch/eval/lib/`。

演算需要 **Python 3.12 或更高版本**（部分脚本使用新版 f-string 语法）。运行检查前用 `python3 --version` 确认当前终端使用的版本。

```bash
gh repo clone platoneko/lynch && cd lynch
gh repo clone platoneko/lynch-frameworks frameworks
cd frameworks && just check
```

`.claude/skills/` 中的技能与参考文档直接随本仓库保存，不需要原机器上的 `agent/finance-skills`。外层代码仓库的 `.claude/skills` 只通过相对软链接访问这里；迁移时保持上面的两层目录关系即可。`just check` 会拒绝技能目录内的绝对软链接、失效软链接，以及指向本内容仓库之外的软链接。

第三方技能的来源和更新方式见 [技能来源说明](.claude/README.md)。

契约见 `AGENTS.md`；研究会话在 `lynch/` 根打开。
