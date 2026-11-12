# lynch-frameworks

lynch 的估值框架内容：单票框架 `<TICKER>.md`、共享情景轴 `axes/`、每票演算 `eval/<TICKER>.py`、沉淀流程 skill `.claude/skills/sediment-framework/`。

**不能单独使用**：检出在代码仓库 [`lynch`](https://github.com/platoneko/lynch) 的 `frameworks/` 下，演算脚本和日报依赖外层 `lynch/eval/lib/`。

演算需要 **Python 3.12 或更高版本**（部分脚本使用新版 f-string 语法）。运行检查前用 `python3 --version` 确认当前终端使用的版本。

```bash
gh repo clone platoneko/lynch && cd lynch
gh repo clone platoneko/lynch-frameworks frameworks
cd frameworks
export LYNCH_FRAMEWORK_ARCHIVE='<应用归档清单的绝对路径>'
just check
```

检查会跳过归档标的，归档清单缺失时会报错。基金等模型需要额外历史数据时，须将 `LYNCH_FRAMEWORK_CHECK_INPUTS` 指向包含各票 `external_inputs`、`peer_results` 或 `rate_inputs` 的 JSON 文件绝对路径；缺少必要数据会报告对应标的的错误。不要用虚构数据代替真实历史数据。

`.claude/skills/sediment-framework/` 是随本仓库保存的项目自有技能。其他研究技能由各工具的用户级环境提供，与 Longbridge 技能一样，不在本仓库存放或更新。`just check` 会拒绝项目技能目录内的绝对软链接、失效软链接，以及指向本内容仓库之外的软链接。

第三方技能的来源和管理位置见 [技能来源说明](.claude/README.md)。

契约见 `AGENTS.md`；研究会话在 `lynch/` 根打开。
