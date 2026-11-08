# lynch-frameworks

lynch 的估值框架内容：单票框架 `<TICKER>.md`、共享情景轴 `axes/`、每票演算 `eval/<TICKER>.py`、沉淀流程 skill `.claude/skills/sediment-framework/`。

**不能单独使用**：检出在代码仓库 [`lynch`](https://github.com/platoneko/lynch) 的 `frameworks/` 下，演算脚本和日报依赖外层 `lynch/eval/lib/`。

演算需要 **Python 3.12 或更高版本**（部分脚本使用新版 f-string 语法）。运行检查前用 `python3 --version` 确认当前终端使用的版本。

```bash
gh repo clone platoneko/lynch && cd lynch
gh repo clone platoneko/lynch-frameworks frameworks
cd frameworks && just check
```

`.claude/skills/` 中的技能与参考文档直接随本仓库保存，不需要原机器上的 `agent/finance-skills`。`.agents/skills` 和 `.grok/skills` 通过仓库内相对软链接访问同一份文件；单独检出本仓库也能发现技能。外层 lynch app 同样使用这里的文件。`just check` 会拒绝技能目录内的绝对软链接、失效软链接，以及指向本内容仓库之外的软链接。

在本仓库执行 `just skills-update` 同步上游全部 finance-skills；这个命令只需 Python 3、npx 和网络，不依赖 lynch 的代码或服务。更新器会保留 sediment-framework，拒绝覆盖本地改写及未知技能；完整文件与来源清单更新后可用 Git 检视，不会自动暂存或提交。终端研究前先运行此命令；lynch app 会在启动或恢复研究进程前自动调用。执行 `just skills-test` 可独立验证更新器，完整框架与演算检查仍使用上述两层目录中的 `just check`。

第三方技能的来源和更新方式见 [技能来源说明](.claude/README.md)。

契约见 `AGENTS.md`；研究会话在 `lynch/` 根打开。
