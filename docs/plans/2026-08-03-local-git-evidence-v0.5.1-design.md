# Local Git Evidence v0.5.1 Design

## 目标

让 `triage` 在用户明确授权后读取当前目标项目的本地 Git 历史，自动识别“测试仍依赖已删除符号”和“测试仍 patch 已迁移依赖”，把同一缺失目标产生的多个失败聚为一个共同根因，并在证据闭合时输出高置信度 `TEST_DEFECT`。

## 授权模型

授权按目标 Git 仓库绑定，而不是按 test-assistant 安装或用户机器全局绑定。首次使用：

```bash
test-assistant triage --path . --allow-git-history
```

工具只允许本地、只读、固定参数的 `git rev-parse`、`git log -S` 和 `git show`，全部使用 `shell=False`、超时及输出限长。禁止 add、commit、tag、checkout、restore、fetch、pull、push 和任何网络操作。授权保存到 `.autotest/permissions.json`，包含仓库根目录摘要、Git common-dir 摘要、scope 和授权时间；仓库身份变化时授权失效。`--no-git-history` 可显式禁用本次读取，未授权时 triage 仍正常执行并保持安全降级。

## 证据与聚类

新增 Python 测试结构分析器，从失败测试 AST 与消息中提取：

- `@patch("module.target")`、`patch.object()` 的目标；
- `hasattr(Type, "symbol")` 和缺失属性错误；
- 对缺失私有方法的调用与源码字符串断言。

证据对象记录目标字符串、测试位置、当前源码是否存在，以及 Git pickaxe 是否找到新增后又删除该符号的提交。原始提交正文、作者邮箱和绝对路径不持久化。

聚类优先使用结构化根因键：`missing_symbol:<qualified-target>` 或 `obsolete_patch:<target>`；没有结构化根因时继续使用 v0.5.0 的异常/位置/消息指纹。这样三个 `_compute_semantic_similarity_async` 失败和两个 `clip.load` 失败分别形成一个簇。

## 归因与失败模式

固定顺序保持不变。只有同时满足以下条件才输出 `TEST_DEFECT/HIGH`：测试明确依赖目标、当前源码确认目标不存在、本地 Git 历史确认该目标曾存在并被删除。仅“当前不存在”不足以推断删除意图，仍返回 `INCONCLUSIVE`。

非 Git 仓库、浅历史、Git 不可用、超时、损坏授权或命令失败都不得中断 pytest；工具记录降级原因，不尝试联网补历史。v0.5.1 仍不生成或应用修复，不修改源码、测试、snapshot 或 Git 状态。

## 验收

- 未授权时不调用历史读取器；授权后同一仓库可复用，仓库变化重新授权。
- 所有 Git 命令来自白名单且不使用 shell。
- 脱敏 fixture 自动形成 `TEST_DEFECT/HIGH`；无删除历史保持 `INCONCLUSIVE`。
- 同一失效 patch/缺失方法跨测试合并为一个簇。
- `triage` JSON 保存授权状态和最小 Git 证据，不保存绝对路径、邮箱或无限输出。
- 全量测试、构建和干净 wheel smoke 通过。
