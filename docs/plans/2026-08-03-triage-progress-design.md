# Triage Progress Design

## 目标

为耗时较长的 `test-assistant triage` 提供真实、可解释的四阶段进度，避免捕获 pytest 输出时看起来无响应。

## 交互

CLI 依次展示 pytest 套件执行、失败聚类、代表节点复跑和诊断保存。pytest 阶段显示范围、超时、运行时间以及 `completed / collected` 百分比；复跑阶段显示当前代表 node。

## 数据流

pytest capture plugin 在 collection 完成和每个测试得到终态时追加 JSONL 事件。父进程使用 `Popen` 捕获最终 stdout/stderr，同时轮询 JSONL 并把结构化事件传给 CLI renderer。最终诊断仍读取原有 session JSON，不从终端文本推断结果。

## 安全和兼容性

- 不解析 pytest 点号输出。
- 不改变最终事件 JSON、归因或持久化格式。
- 没有进度回调的内部调用继续使用原执行路径。
- 超时会终止 pytest 子进程并保留现有结构化超时诊断。
- `--timeout` 只调整本次套件执行上限，不扩大测试范围或权限。

## 验收

- collection 数量与 completed 数量准确包含 passed、failed、error 和 skipped。
- CLI 输出四个阶段、范围、超时、失败簇和当前复跑 node。
- 交互终端可单行刷新，非交互测试和 CI 保留稳定文本。
