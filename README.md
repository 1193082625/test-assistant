# test-assistant

`test-assistant` 是一个面向 Python/pytest 项目的本地智能测试 CLI。

当前 `v0.6.2` 提供 TestSpec 审批与候选门禁、pytest 失败分诊、只读质量审计、环境诊断，以及 Ubuntu/macOS wheel 和特殊路径兼容性证据。

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
- 自动识别配置默认值、字段类型、可选字段、关联配置和枚举契约迁移；
- 识别 AsyncMock Result 与异步生成器生命周期中的测试 fixture 漂移；
- 原子保存 TestSpec、候选、验证状态、脱敏诊断和 triage 运行记录。
- 通过 `audit` 映射源码符号覆盖缺口，并汇总 Ruff 与 mypy findings；
- 支持显式覆盖率/质量阈值、`--changed-only` 和 Markdown Audit 报告。
- 通过 `doctor` 只读检查 Python、pytest、Git、pytest-cov、coverage、Ruff 和 mypy，并支持版本化 JSON 输出。

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

- Python `>=3.13,<3.14`
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

`init`、`inspect`、`run`、`triage`、`audit`、`doctor`、`verify`、`status`、`diagnose` 和 `report` 不调用 LLM。

## 环境诊断

在运行 `triage`、`audit` 或 `verify` 前，可以检查 CLI 实际使用的解释器和工具：

```bash
test-assistant doctor --path .
test-assistant doctor --path . --json
test-assistant doctor --path . --timeout 10
```

Doctor 只执行固定的版本探测命令，不联网、不安装依赖、不运行测试、lint 或类型检查，也不写入目标项目。文本输出供人工排障；`--json` 输出 `schema_version: 1` 的纯 JSON。

退出码为：`0` 表示核心环境健康（允许 Git 或可选 adapter 缺失），`1` 表示核心 Python/pytest 环境不兼容，`2` 表示参数或基础设施错误。v0.6.2 认证 Ubuntu/macOS 上的 Python 3.13；Windows 不在支持范围，Python 3.14 仅做非阻塞探测。

## 只读质量审计

```bash
test-assistant audit --path .
test-assistant audit --path . --coverage --no-quality
test-assistant audit --path . --no-coverage --quality
test-assistant audit --path . --changed-only
test-assistant report --path . --audit
```

`triage` 解释测试为何失败；`audit` 报告哪些实现缺少覆盖或存在静态质量问题。Audit 不联网、不安装缺失工具、不执行 Ruff `--fix`，也不修改源码、测试或 Git。目标环境缺少 pytest-cov、Ruff 或 mypy 时会明确显示 adapter 降级状态。

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
poetry run test-assistant triage --path /path/to/demo-project \
  --test-path tests/test_service.py --allow-git-history
```

`--test-path` 与 `--test-node` 互斥。退出码 `0` 表示没有未解决问题，`1` 表示存在诊断或未收集到测试，`2` 表示参数、Runner、环境或持久化错误。记录保存在 `.autotest/triage/`，并对密钥、项目绝对路径和大型输出做脱敏或截断。

默认不读取 Git 历史。`--allow-git-history` 会为当前仓库保存一次明确的“本地只读”授权，之后可自动复用；`--no-git-history` 可在单次运行中覆盖它。授权只允许固定白名单的 `git rev-parse`、`git log -S` 与 `git show`，不访问网络、不修改 Git，也不修改目标项目源码或测试。历史不可用时诊断安全降级，不猜测提交意图。

契约迁移只有在当前实现至少两个独立来源一致，且同一 Git 提交同时删除旧表达式、增加当前表达式时，才会输出 `TEST_DEFECT / HIGH`。AsyncMock Result 和异步生成器生命周期不依赖 Git，但必须同时具备 warning、测试 AST 和受支持运行时契约证据。所有建议都需要人工执行，`triage` 不自动修改测试。

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
├── permissions.json        当前仓库的本地 Git 只读授权
├── triage/                 版本化套件分诊记录与 latest.json
├── audits/                 版本化覆盖率/质量审计记录与 latest.json
├── verification/           最近一次验证状态
└── reports/                Markdown 报告
```

## 当前限制

- 可信生成和符号归因主流程只支持 Python/pytest；
- Web Dashboard 和 watch 尚未实现；
- Vitest 执行器不属于当前 TestSpec 生成闭环；
- 没有已批准强契约时，稳定失败通常返回 `INCONCLUSIVE`；
- v0.6.2 不自动修改失败测试或产品实现，也不使用 LLM 猜测归因；
- 当前使用版本化 JSON，尚未引入 SQLite 或远程服务；
- 真实 LLM 验证是显式 smoke test，不属于默认自动化测试。

## 文档

- [完整用户指南](docs/user-guide.md)：参数解释、完整操作、退出码和排错；
- [项目结构](docs/project-structure.md)：模块职责、依赖方向、数据流和系统不变量；
- [兼容性支持表](docs/compatibility.md)：由机器可读清单生成的系统、Python、pytest 和路径支持状态；
- [可信 CLI 路线图](docs/plans/2026-07-27-python-cli-trusted-loop-roadmap.md)：范围、里程碑和后续方向；
- [v0.6～v1.0 统一版本路线图](docs/plans/2026-08-04-version-roadmap-v0.6-v1.0.md)：当前权威版本边界、统一发布门和计划索引；
- [端到端 CLI 实施计划](docs/plans/2026-08-01-end-to-end-cli-workflow.md)：本轮架构决策和测试计划。
- [v0.5.2 契约迁移归因规划](docs/plans/2026-08-03-contract-migration-triage-v0.5.2.md)：配置默认值、常量和字段类型迁移的高置信度归因。
- [v0.6.0 覆盖率与代码质量规划](docs/plans/2026-08-03-coverage-and-code-quality-v0.6.0.md)：源码符号覆盖、Ruff、mypy 和只读 audit 工作流。
- [v0.6.x 兼容性与 doctor 规划](docs/plans/2026-08-04-compatibility-and-doctor-v0.6.x.md)：环境诊断、平台矩阵与特殊路径验证。
- [v0.6.2 详细实施计划](docs/plans/2026-08-05-compatibility-matrix-v0.6.2.md)：同一 wheel 跨平台消费、路径矩阵和兼容表生成。
- [v0.7.0 规模化与数据生命周期规划](docs/plans/2026-08-04-scale-and-data-lifecycle-v0.7.0.md)：性能/内存基线、schema 迁移、记录清理和可选依赖。
- [v1.0.0 安全发布规划](docs/plans/2026-08-04-secure-release-v1.0.0.md)：安全门、供应链证明、PyPI 和真实项目回归矩阵。

`docs/plans/` 中较早的设计文件属于历史记录；版本定义冲突时，以 v0.6～v1.0 统一版本路线图和其索引的实施计划为准。

## 开发与验证

```bash
poetry run pytest -q
poetry build
poetry run python -m cli.main --help
git diff --check
```

`poetry build` 只在本地生成 wheel 和源码发行包，不会发布到 PyPI。
