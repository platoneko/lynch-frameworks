# 技能来源

`skills/sediment-framework/` 是本项目维护的沉淀流程。其余 14 个技能及其参考文档来自 [himself65/finance-skills](https://github.com/himself65/finance-skills)，版本为 [`8bf3b5bda21ba4ecb93246d0f74134476ac24f5b`](https://github.com/himself65/finance-skills/tree/8bf3b5bda21ba4ecb93246d0f74134476ac24f5b/skills)，上游声明使用 MIT 许可证。

这些文件以完整副本保存在本仓库，替代原来指向 `agent/finance-skills` 的软链接。克隆内容仓库即可获得文件；技能各自需要的命令行工具、Python 依赖和服务凭据仍按各技能说明配置。

更新第三方技能时，从上游选定版本复制对应技能目录及其 `references/`，保留来源说明并更新这里的版本；不要恢复指向仓库外部的软链接。更新后运行 `just check`。
