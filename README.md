# test-assistant

`test-assistant` 是一个面向 Python/pytest 项目的本地智能测试 CLI。

当前 `v0.5.0` 提供两条相互独立的可信闭环：为新测试执行 TestSpec 审批与候选门禁，以及对项目已有 pytest 套件执行结构化分诊、失败聚类、三次精确复跑和证据归因。

## 当前能力

- 分析 Python 项目、源码符号、契约证据和已有 pytest 映射；
- 根据变更安全选择需要执行的已有测试；
- 从指定源码符号提议结构化 TestSpec；
- 只有人工批准的 TestSpec 才能进入测试生成器；
- 候选测试经过静态、导入、收集、Runner、隔离执行和副作用门禁；
- 正式测试写入前展示 diff，并要求第二次人工确认；
- 对指定 pytest node 精确复跑三次；
- 对已有 pytest 套件解析 collection、setup、call、skip 和 warning 事件；
- 按稳定指纹聚类失败，并用代表 node 精确复跑三次；
- 区分产品缺陷、测试缺陷、基础设施故障、Flaky 和证据不足；
- 原子保存 TestSpec、候选、验证状态、脱敏诊断和 triage 运行记录。

## 安全原则

```text
TestSpec 人工审批
→ 候选测试隔离生成
→ 自动质量门禁
→ diff 人工审批
→ 正式测试提交
→ 确定性验证与诊断
```

- 未批准的 TestSpec 不能生成测试；
- 未通过门禁或未确认 diff 的候选不能进入正式测试目录；
- `verify` 只执行用户指定的精确 pytest node；
- `triage` 不修改源码、正式测试、TestSpec 或 snapshot；
- 证据不足时返回 `INCONCLUSIVE`，不以高置信度猜测；
- 工具不会自动修改产品源码或自动批准业务预期。

## 环境要求

- Python `>=3.13,<4.0`
- Poetry
- 目标项目可以在当前 Python 环境运行 pytest

安装项目依赖：

```bash
git clone <repository-url>
cd test-assistant
poetry install
poetry run test-assistant --help
```

## 配置 LLM

`plan propose` 和 `generate` 需要调用 LLM：

```bash
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://your-api-endpoint"
```

`DEEPSEEK_BASE_URL` 应指向所使用的 OpenAI 兼容服务地址。不要把密钥提交到 Git。

`init`、`inspect`、`run`、`triage`、`verify`、`status`、`diagnose` 和 `report` 不调用 LLM。

## 快速开始

第一次使用建议选择一个小型 Python/pytest 项目，并在独立 Git 分支或项目副本中试运行。

以下示例假设目标项目是 `/path/to/demo-project`，其中存在：

```python
# demo.py
def add(left: int, right: int) -> int:
    """返回两个整数之和。"""
    return left + right
```

### 1. 初始化目标项目

```bash
poetry run test-assistant init \
  --path /path/to/demo-project \
  --mode auto
```

该命令创建 `.autotest/`、配置和初始快照。目标项目已经初始化过时，不需要重复执行。

### 2. 检查项目分析结果

```bash
poetry run test-assistant inspect \
  --path /path/to/demo-project
```

确认项目语言、pytest、目标符号、契约证据和测试选择没有异常。

### 3. 提议 TestSpec

```bash
poetry run test-assistant plan propose demo.add \
  --path /path/to/demo-project \
  --source-path demo.py \
  --module-path demo
```

命令会输出生成的 `SPEC_ID` 和保存位置。

### 4. 查看并批准 TestSpec

```bash
poetry run test-assistant plan list \
  --path /path/to/demo-project

poetry run test-assistant plan show SPEC_ID \
  --path /path/to/demo-project

poetry run test-assistant plan approve SPEC_ID \
  --path /path/to/demo-project
```

批准前应人工检查行为、输入、预期结果、证据来源和副作用声明。不符合业务意图时使用 `plan reject`。

### 5. 生成并审阅候选测试

```bash
poetry run test-assistant generate SPEC_ID \
  --path /path/to/demo-project \
  --module-path demo \
  --source-path demo.py \
  --test-filename test_demo.py
```

候选通过质量门禁后，CLI 会展示 diff。只有明确确认后才会写入正式测试目录。请记录命令输出中的正式测试路径和 pytest 函数名。

### 6. 验证精确 pytest node

```bash
poetry run test-assistant verify SPEC_ID \
  --path /path/to/demo-project \
  --test-node ".autotest/test_cases/unit/demo.py/test_demo.py::test_add" \
  --source-path demo.py
```

`verify` 会重新检查测试门禁，并只执行指定 node 三次：

- 连续三次通过：返回 `0` 并更新健康状态；
- 失败或结果不一致：保存诊断并返回非零退出码。

实际测试路径和函数名以 `generate` 输出及 pytest collect 结果为准。

### 7. 查看状态、诊断和报告

```bash
poetry run test-assistant status \
  --path /path/to/demo-project
```

失败后可以解释诊断并生成 Markdown 报告：

```bash
poetry run test-assistant diagnose \
  --input /path/to/demo-project/.autotest/diagnoses/latest.json

poetry run test-assistant report \
  --path /path/to/demo-project
```

报告默认写入：

```text
.autotest/reports/latest.md
```

## 增量运行已有测试

`run` 是独立的快照驱动流程，用于选择并执行受变更影响的已有测试：

```bash
poetry run test-assistant run \
  --path /path/to/demo-project
```

它与 TestSpec 的 `propose → approve → generate → verify` 生命周期可以分别使用。

## 分诊已有 pytest 套件

`triage` 不要求 TestSpec，也不使用 LLM。它运行已有套件、结构化解析 pytest 生命周期事件、聚类失败并对代表 node 复跑三次：

```bash
poetry run test-assistant triage --path /path/to/demo-project
poetry run test-assistant triage --path /path/to/demo-project \
  --test-path tests/test_service.py --max-failures 10
poetry run test-assistant triage --path /path/to/demo-project \
  --test-node tests/test_service.py::test_case
```

`--test-path` 与 `--test-node` 互斥。退出码 `0` 表示没有未解决问题，`1` 表示存在诊断或未收集到测试，`2` 表示参数、Runner、环境或持久化错误。记录保存在 `.autotest/triage/`，并对密钥、项目绝对路径和大型输出做脱敏或截断。

三个执行入口的边界：

- `run`：基于 snapshot 选择受变更影响的已有测试；
- `verify`：验证一个已批准 TestSpec 对应的精确 node；
- `triage`：分析已有 pytest 套件，不要求或修改 TestSpec。

## 目标项目工作区

初始化和后续命令会维护：

```text
.autotest/
├── config.yml              项目配置
├── snapshot.json           增量分析基线
├── plans/                  TestSpec
├── candidates/             隔离候选及 metadata
├── test_cases/unit/        人工确认后的正式测试
├── diagnoses/              诊断历史与 latest.json
├── triage/                 版本化套件分诊记录与 latest.json
├── verification/           最近一次验证状态
└── reports/                Markdown 报告
```

## 当前限制

- 可信生成和符号归因主流程只支持 Python/pytest；
- Web Dashboard 和 watch 尚未实现；
- Vitest 执行器不属于当前 TestSpec 生成闭环；
- 没有已批准强契约时，稳定失败通常返回 `INCONCLUSIVE`；
- v0.5.0 不自动修改失败测试或产品实现，也不使用 LLM 猜测归因；
- 当前使用版本化 JSON，尚未引入 SQLite 或远程服务；
- 真实 LLM 验证是显式 smoke test，不属于默认自动化测试。

## 文档

- [完整用户指南](docs/user-guide.md)：参数解释、完整操作、退出码和排错；
- [项目结构](docs/project-structure.md)：模块职责、依赖方向、数据流和系统不变量；
- [可信 CLI 路线图](docs/plans/2026-07-27-python-cli-trusted-loop-roadmap.md)：范围、里程碑和后续方向；
- [端到端 CLI 实施计划](docs/plans/2026-08-01-end-to-end-cli-workflow.md)：本轮架构决策和测试计划。

`docs/plans/` 中较早的设计文件属于历史记录，不代表当前命令或目录结构。

## 开发与验证

```bash
poetry run pytest -q
poetry build
poetry run python -m cli.main --help
git diff --check
```

`poetry build` 只在本地生成 wheel 和源码发行包，不会发布到 PyPI。
