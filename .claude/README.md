# 技能来源

`skills/sediment-framework/` 是本项目维护的沉淀流程。其余技能及其参考文档来自 [himself65/finance-skills](https://github.com/himself65/finance-skills)，上游声明使用 MIT 许可证。全部第三方源码完整保存在本内容仓库；当前安装文件逐一记录在 `skills/.finance-skills.json`，包含来源、安装器版本、上游内容哈希和本地文件 SHA-256，可复核更新及检测本地改写。

上游原有 14 个技能的来源版本为 [`8bf3b5bda21ba4ecb93246d0f74134476ac24f5b`](https://github.com/himself65/finance-skills/tree/8bf3b5bda21ba4ecb93246d0f74134476ac24f5b/skills)。

这些文件以完整副本保存在本仓库，替代原来指向 `agent/finance-skills` 的软链接。克隆内容仓库即可获得文件；技能各自需要的命令行工具、Python 依赖和服务凭据仍按各技能说明配置。

在本仓库运行 `just skills-update` 跟随上游默认分支同步全部技能；固定的 skills@1.7.6 安装器与 node@22.20.0 运行时只缓存于 `_local/tmp/`。安装在隔离目录完成，检查全部技能和参考文件后统一发布；发生中断时，下次更新先恢复旧文件。已有技能的本地修改、未知入口冲突会阻止覆盖，旧文件备份保留于 `_local/tmp/`。更新不会自动暂存或提交；更新后运行 `just skills-test` 和 `just check`。
