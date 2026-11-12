# 对话授权后的结果保存

首页、日报和索引读取同一结果库；研究 agent 负责在用户授权落盘后保存本次正式采纳的脚本输出。未授权的研究试算不写结果库；不能把条件情景替换为基础价带。对话中的用户决定由研究 agent 判断，程序只记录本地操作员引用的对话和原话，不能证明自然语言的授权语义或隔离执行。

**准备计算目录和结果。** 以下命令从代码仓根执行；`code_root` 是当前代码仓的绝对路径，`content_root` 是其 `frameworks/` 的绝对路径，`ticker` 是本票规范化代码。由 agent 在 `frameworks/_local/tmp/` 选取此前不存在的独立目录作为 `proposal_content`，并在其中建立 `eval/`、`axes/`：将拟采纳的单票脚本放在 `eval/<ticker>.py`，将脚本 `DEPENDENCIES` 声明的共享轴 `.py` 复制到 `axes/`。需要对共享轴试算时仅修改临时副本。公共库从 `code_root/eval/lib/` 读取；缺少声明的依赖须补齐或报告，不能用空值冒充。`proposal_result` 和 `final_result` 是该私有临时目录内不同的 JSON 文件绝对路径，`receipt` 也放在那里；不得覆盖其他研究资料。

用已安装估值所需依赖的 `python3` 分别计算拟采纳结果和授权后的正式结果；App 的虚拟环境用于后面的保存命令，不保证含估值依赖。第一条在授权前对临时副本运行；第二条仅在授权后、正式脚本及相关共享轴已按采纳内容更新时运行。

```bash
python3 -m eval.lib.valuation_runner --code-root "$code_root" --content-root "$proposal_content" --ticker "$ticker" > "$proposal_result"
python3 -m eval.lib.valuation_runner --code-root "$code_root" --content-root "$content_root" --ticker "$ticker" > "$final_result"
```

有外部历史数据时，两条计算命令均在输出重定向前加 `--external-inputs "$external_inputs"`，并在下面的 `prepare` 和 `publish` 命令中分别加同一参数；该文件为实际引用的同一份历史输入。需要跨票结果时，按脚本声明的别名将同业输出组成 JSON 对象，计算命令加 `--peer-results "$peer_results"`；临时试算的同业输出须使用同一 `code_root` 和 `proposal_content`，正式计算的同业输出须使用同一 `code_root` 和 `content_root`。两阶段分别使用对应根目录生成的同业输出，不能把其他根目录的结果冒充当前来源。当前入口尚不支持嵌套同业快照或带外部历史的同业快照；同业缺失时保留可算基础结果并标明待核，不编造数据或额外要求用户逐票审批。CLI 当前没有外传利率参数；所需情景数据不可用时说明影响，保留仍可计算的结果。

1. **拟落盘摘要前**，先在临时脚本中本次新增或修改的量化输入旁注释来源、日期、口径及必要的推算依据，再运行统一演算入口，将拟采纳结果 JSON 放在用户私有的 `frameworks/_local/tmp/`。来源仅为对话中用户给出的判断时如实标注；来源或日期不明写待补，不编造财报或卖方资料。注释随拟采纳脚本进入正式脚本，不能到授权后才补写再更换收据。运行下列 `prepare` 命令，把其输出存入同一临时目录中的收据；这只读取现有结果版本，不会写入结果库。为用户解释的基础区间、候选和新业务应与这个结果一致。若计算需要外部历史输入，对两个步骤都使用同一份输入文件。用户已明确授权时不重复征询，但仍须在修改正式文件前完成准备。
2. 未获授权时等用户明确说可以落盘。按既定研究规则更新正式框架文档及演算脚本，重新运行正式脚本得到结果；不得从摘要或旧文档手抄价带。正式脚本及共享源码、实际输出和先前提案不一致时，命令会拒绝保存；应检查差异，不得更换收据或悄悄将另一组试算当作已获授权。
3. 运行 `publish` 命令，使用同一收据、当前 app 提供的对话引用及用户授权原话。它把结果和引用记录进 app 结果库，保留旧版本；不要求用户手工导入或额外点击确认。命令失败时保留原结果，向用户说明框架与首页尚未同步，并根据错误修复，不得宣称已经发布。

以下参数中的文件均由 agent 在研究过程中准备，用户不需要手工操作；命令从代码仓库根运行。`LYNCH_VALUATION_DB` 使用当前 app 的结果库配置；源码和内容目录分别是当前代码仓根及其 `frameworks/`，不要指向临时副本。

```bash
PYTHONPATH=app/server app/server/.venv/bin/python -m lynch_reader.conversation_publication prepare --database "$LYNCH_VALUATION_DB" --result "$proposal_result" > "$receipt"
PYTHONPATH=app/server app/server/.venv/bin/python -m lynch_reader.conversation_publication publish --database "$LYNCH_VALUATION_DB" --result "$final_result" --archive "$LYNCH_FRAMEWORK_ARCHIVE" --receipt "$receipt" --code-root "$code_root" --content-root "$content_root" --session-reference "$conversation_reference" --authorization "$user_authorization"
```

所有文件和目录参数使用绝对路径；如使用外部历史输入，为两个命令分别加 `--external-inputs` 和对应绝对文件路径。`LYNCH_FRAMEWORK_ARCHIVE` 和 `LYNCH_VALUATION_DB` 使用 app 当前配置；收据绑定准备时的结果库，归档路径须与 app 使用的同一清单一致。`$conversation_reference` 使用 app 告知的当前对话引用，`$user_authorization` 为用户实际授权原话。对话被编辑、授权被撤回或结果库版本并发变化时，重新核对当前对话和结果，不得凭旧收据覆盖。
