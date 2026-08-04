# Environment Doctor v0.6.1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 提供只读 `test-assistant doctor` 命令，让用户在执行 `triage`、`audit` 或 `verify` 前确认实际解释器、核心依赖、Git 与可选 Audit adapter 的可用性和兼容状态。

**Architecture:** 新增稳定的环境诊断领域模型和确定性 `doctor` 工作流。工作流只通过当前进程事实、受控参数数组子进程和现有 adapter 探测能力收集信息，不导入目标项目业务模块、不联网、不安装依赖、不写 `.autotest`；CLI 负责文本/JSON 展示和退出码映射。v0.6.1 只认证当前明确支持的 Python 3.13 与 pytest 运行环境，跨平台 wheel 矩阵和特殊路径扩展留给 v0.6.2。

**Tech Stack:** Python 3.13、Click、dataclasses、StrEnum、`platform`、`sys`、`subprocess`、JSON、pytest。

---

## 1. 产品边界与决策

### 1.1 命令形态

```bash
test-assistant doctor --path .
test-assistant doctor --path . --json
test-assistant doctor --path . --timeout 10
```

默认文本输出面向人工排障；`--json` 将同一份版本化模型写到 stdout，供 CI 或外部工具消费。v0.6.1 不增加输出文件参数，也不写入 `.autotest`。

### 1.2 检查范围

必须报告：

- test-assistant 版本；
- 当前 Python 版本、实现、平台和实际解释器路径；
- 目标项目规范化路径及其可读性；
- pytest 的可用性和版本；
- Git 的可用性、版本以及目标路径是否属于 Git worktree；
- pytest-cov、coverage、Ruff、mypy 的可用性和版本；
- 每项检查的状态、原因和是否属于核心能力；
- 汇总状态及进程退出码。

不检查网络、LLM 配置、数据库、浏览器、Node/Vitest、Docker 或操作系统包管理器；这些能力不属于 v0.6.1 的 Python/pytest 可信闭环。

### 1.3 状态与退出码

单项检查状态使用稳定机器值：

| 状态 | 含义 |
| --- | --- |
| `available` | 可执行且版本可解析 |
| `unavailable` | 未安装或命令不存在 |
| `incompatible` | 已安装，但不在当前支持范围 |
| `timed_out` | 探测超过显式超时 |
| `failed` | 命令存在但返回损坏或不可解释结果 |
| `not_applicable` | 当前路径或模式下不适用 |

汇总状态：

- `healthy`：核心检查通过；允许可选 adapter 为 `unavailable`；退出码 `0`；
- `incompatible`：Python 或 pytest 等核心环境明确不兼容；退出码 `1`；
- `infra_error`：路径无效、核心探测超时/损坏或内部基础设施错误；退出码 `2`。

Git 不可用、目标项目不是 Git 仓库、pytest-cov/Ruff/mypy 缺失均不能单独导致退出码非零。它们必须显示降级原因和受影响能力。

### 1.4 安全与隐私

- 所有命令使用参数数组和 `shell=False`；
- 不执行目标项目配置中的命令，不导入目标业务模块；
- 不读取 `.env`、密钥或 Git 历史；
- 文本输出可以显示用户显式传入的目标路径和当前解释器路径；
- JSON 中路径使用统一的展示形式，不包含 home 目录之外的环境变量或完整命令输出；
- stderr/stdout 仅保留规范化原因码，不回显无限工具输出；
- `doctor` 前后目标源码、测试、snapshot、Git 和 `.autotest` 必须不变。

## 2. 领域模型

建议在 `core/models/environment.py` 定义：

```python
class EnvironmentCheckState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class DoctorStatus(StrEnum):
    HEALTHY = "healthy"
    INCOMPATIBLE = "incompatible"
    INFRA_ERROR = "infra_error"


@dataclass(frozen=True)
class EnvironmentCheck:
    name: str
    state: EnvironmentCheckState
    version: str | None
    executable: str | None
    required: bool
    reason: str | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DoctorResult:
    schema_version: int
    status: DoctorStatus
    test_assistant_version: str
    project_path: str
    python_implementation: str
    platform: str
    checks: tuple[EnvironmentCheck, ...]
```

模型必须验证稳定枚举、非空名称、合法版本字段，以及所有非成功状态具有原因。`DoctorResult` 的状态由工作流计算，模型只验证不变量，不隐藏重新推导业务状态。

JSON 顶层字段固定为：`schema_version`、`status`、`test_assistant_version`、`project_path`、`python_implementation`、`platform`、`checks`。首版 `schema_version` 为 `1`。

## 3. 探测策略

实现一个内部安全探测函数，接受固定参数数组，例如：

```python
probe_command(
    [sys.executable, "-m", "pytest", "--version"],
    cwd=project_root,
    timeout=timeout,
)
```

各工具建议命令：

- Python：当前 `sys.version_info`、`sys.implementation.name`、`sys.executable`，不启动第二个解释器；
- pytest：`sys.executable -m pytest --version`；
- pytest-cov：`sys.executable -c "import importlib.metadata ..."`，脚本内容必须由工具内固定，不能拼接用户输入；
- coverage：`sys.executable -m coverage --version`；
- Ruff：优先 `sys.executable -m ruff --version`；
- mypy：`sys.executable -m mypy --version`；
- Git：`git --version`，随后 `git -C <root> rev-parse --is-inside-work-tree`。

不要复用会实际执行项目测试的 `CoverageExecutor`，也不要运行 Ruff check 或 mypy 分析；doctor 只验证工具能否启动和报告版本。版本解析失败返回 `failed/version_output_invalid`，找不到模块或命令返回 `unavailable`，超时返回 `timed_out`。

## 4. 实施任务

### Task 0: 保护已有 `.autotest` 的初始化事务

**Files:**
- Modify: `cli/commands/init.py`
- Modify: `tests/test_init.py`

**背景：** 原实现会在 `init` 任一步骤失败后直接删除整个 `.autotest`。当用户确认覆盖一个已有工作区时，这可能同时删除原有计划、候选测试、验证结果、失败诊断和 Audit 历史。该问题属于数据安全缺陷，必须在实现 Doctor 前修复，不能延后到 v0.7.0 的主动数据清理功能。

**已实现的事务语义：**

1. 初始化前不存在 `.autotest`：成功时保留新目录，失败时只删除本次创建的目录。
2. 初始化前存在 `.autotest`：用户拒绝时不创建备份、不修改文件；用户确认后先创建完整备份，再开始任何写入。
3. 已有工作区初始化失败：删除半初始化工作区，并原子恢复原有备份。
4. 已有工作区初始化成功：保留原历史，更新配置和 snapshot，再删除备份。
5. 初始化已完成但备份清理失败：保留成功的新工作区和剩余备份，明确报告错误，不执行危险回滚。
6. 回滚失败：同时报告初始化错误和回滚错误，并保留最后可恢复的备份。

**安全边界：**

- 备份创建在目标项目同级目录，避免污染项目分析和 snapshot；
- 备份目录使用项目专属随机前缀，创建与校验共享同一个前缀函数；
- 拒绝顶层 `.autotest` 符号链接和非目录路径；
- `restore` 与 `discard` 在删除或移动前验证备份父目录、项目专属前缀、真实目录和符号链接边界；
- 内部符号链接按链接本身复制，不跟随目标读取项目边界外数据；
- 备份复制失败时清理不完整备份，但不修改或删除用户原工作区。

**测试覆盖：**

- 已有工作区写入失败后恢复历史和原配置；
- 新工作区写入失败后删除本次目录；
- 成功覆盖时保留历史、更新配置和 snapshot，并删除备份；
- 顶层 `.autotest` 符号链接被拒绝，链接目标保持不变；
- 备份复制失败时原工作区保持不变；
- 回滚失败时保留备份并输出双重错误；
- 备份清理失败时保留已完成工作区和备份；
- `restore` 与 `discard` 拒绝不受控路径。

**验收结果（2026-08-05）：**

```text
相关回归：30 passed
完整测试：691 passed
Python 语法编译：通过
git diff --check：通过
```

**建议提交：**

```bash
git add cli/commands/init.py tests/test_init.py \
  docs/plans/2026-08-04-environment-doctor-v0.6.1.md
git commit -m "fix: preserve autotest data on init failure"
```

### Task 1: 固定环境诊断模型契约

**Files:**
- Create: `core/models/environment.py`
- Modify: `core/models/__init__.py`
- Test: `tests/test_environment_model.py`

**Step 1: 写失败测试**

覆盖枚举机器值、合法 `EnvironmentCheck`、非成功状态缺少 reason、空名称、非法 capabilities、`DoctorResult` schema version 和稳定 JSON 字段。

**Step 2: 运行失败测试**

Run: `poetry run pytest tests/test_environment_model.py -q`

Expected: FAIL，因为 `core.models.environment` 尚不存在。

**Step 3: 实现最小模型**

按第 2 节定义模型，并提供显式 `to_dict()`；禁止用 `dataclasses.asdict()` 无选择暴露未来内部字段。

**Step 4: 运行测试**

Run: `poetry run pytest tests/test_environment_model.py -q`

Expected: PASS。

**Step 5: 提交**

```bash
git add core/models/environment.py core/models/__init__.py tests/test_environment_model.py
git commit -m "feat: add environment diagnosis model"
```

### Task 2: 实现受控版本探测器

**Files:**
- Create: `core/executors/environment_probe.py`
- Modify: `core/executors/__init__.py`
- Test: `tests/test_environment_probe.py`

**Step 1: 写失败测试**

测试成功版本、命令不存在、模块不存在、非零退出、损坏版本文本、超时、超长输出截断、参数数组传递、`shell=False` 和目标 cwd。用 fake runner 注入结果，不依赖开发机实际安装状态。

**Step 2: 运行失败测试**

Run: `poetry run pytest tests/test_environment_probe.py -q`

Expected: FAIL，因为探测器尚不存在。

**Step 3: 实现最小探测器**

探测器只返回规范化的 `EnvironmentCheck`，不决定整体 Doctor 状态。将 `FileNotFoundError`、`TimeoutExpired` 和已知 `No module named` 分别映射为稳定原因码；原始输出限制长度。

**Step 4: 运行测试**

Run: `poetry run pytest tests/test_environment_probe.py -q`

Expected: PASS。

**Step 5: 回归安全执行器**

Run: `poetry run pytest tests/test_coverage_executor.py tests/test_ruff_executor.py tests/test_mypy_executor.py tests/test_pytest_interrupt.py -q`

Expected: PASS。

**Step 6: 提交**

```bash
git add core/executors/environment_probe.py core/executors/__init__.py tests/test_environment_probe.py
git commit -m "feat: probe environment tools safely"
```

### Task 3: 实现只读 Doctor 工作流

**Files:**
- Create: `core/workflows/doctor.py`
- Modify: `core/workflows/__init__.py`
- Test: `tests/test_doctor_workflow.py`

**Step 1: 写失败测试**

至少覆盖：

- 所有核心检查和可选工具可用时为 `healthy`；
- pytest-cov、coverage、Ruff、mypy 全部缺失仍为 `healthy`；
- Git 缺失或非 Git 项目仍为 `healthy`；
- Python 版本不支持为 `incompatible`；
- pytest 明确不兼容为 `incompatible`；
- 核心探测超时/损坏为 `infra_error`；
- 可选探测超时只产生降级，不使整体失败；
- 每个工具只探测版本，不执行测试、lint 或类型检查；
- 目标目录在工作流前后没有新增或修改文件。

**Step 2: 运行失败测试**

Run: `poetry run pytest tests/test_doctor_workflow.py -q`

Expected: FAIL，因为 `run_doctor` 尚不存在。

**Step 3: 实现最小工作流**

公开函数建议为：

```python
def run_doctor(
    *,
    project_root: str | Path,
    timeout: float = 10,
    probe=None,
) -> DoctorResult:
    ...
```

支持范围必须集中为显式常量或纯函数，不能散落在 CLI。v0.6.1 只将项目当前声明并实际测试的 Python/pytest 范围标为 supported；未知未来版本不得自动视为支持。

**Step 4: 运行测试**

Run: `poetry run pytest tests/test_doctor_workflow.py -q`

Expected: PASS。

**Step 5: 提交**

```bash
git add core/workflows/doctor.py core/workflows/__init__.py tests/test_doctor_workflow.py
git commit -m "feat: add read-only doctor workflow"
```

### Task 4: 新增 Doctor CLI 与 JSON 输出

**Files:**
- Create: `cli/commands/doctor.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_doctor.py`

**Step 1: 写失败测试**

覆盖默认文本、`--json` 严格 JSON、`--timeout`、不存在路径、空格/中文路径的参数传递、三种退出码、可选工具降级说明，以及 JSON 模式 stdout 不混入进度或人类文本。

**Step 2: 运行失败测试**

Run: `poetry run pytest tests/test_cli_doctor.py -q`

Expected: FAIL，因为命令尚未注册。

**Step 3: 实现命令**

```python
@click.command("doctor")
@click.option(
    "--path", "project_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".", show_default=True,
)
@click.option(
    "--json", "json_output", is_flag=True,
    help="输出版本化 JSON",
)
@click.option(
    "--timeout", type=click.FloatRange(min=1),
    default=10.0, show_default=True,
)
def doctor_command(...):
    ...
```

文本输出先给汇总状态，再逐项显示 `名称 / 状态 / 版本 / 原因 / 受影响能力`。JSON 使用 `json.dumps(..., ensure_ascii=False, sort_keys=True)`；不得同时输出文本表格。

**Step 4: 运行 CLI 测试**

Run: `poetry run pytest tests/test_cli_doctor.py tests/test_cli_version.py -q`

Expected: PASS。

**Step 5: 手工 smoke**

Run: `poetry run test-assistant doctor --path .`

Expected: 显示 test-assistant、Python、pytest、Git、pytest-cov、coverage、Ruff 和 mypy；不创建或修改文件。

Run: `poetry run test-assistant doctor --path . --json | poetry run python -m json.tool`

Expected: JSON 可解析，`schema_version` 为 `1`。

**Step 6: 提交**

```bash
git add cli/commands/doctor.py cli/main.py tests/test_cli_doctor.py
git commit -m "feat: add doctor command"
```

### Task 5: 建立真实 CLI 只读与错误语义验收

**Files:**
- Modify: `tests/test_cli_end_to_end.py`
- Create: `tests/test_v061_release_acceptance.py`

**Step 1: 写真实子进程测试**

在临时 Python fixture 中从 CLI 入口运行文本和 JSON doctor。记录运行前后文件清单与内容摘要，证明没有创建 `.autotest`、没有修改源码和测试。至少覆盖普通项目、非 Git 项目、缺可选 adapter 的隔离环境模拟和核心不兼容结果。

**Step 2: 运行测试并确认失败**

Run: `poetry run pytest tests/test_cli_end_to_end.py tests/test_v061_release_acceptance.py -q`

Expected: 新增验收测试在必要实现补齐前 FAIL。

**Step 3: 只修复暴露出的最小实现缺口**

不得在验收测试里放宽退出码、删除只读断言或依赖开发机恰好安装某个可选工具。

**Step 4: 运行验收**

Run: `poetry run pytest tests/test_environment_model.py tests/test_environment_probe.py tests/test_doctor_workflow.py tests/test_cli_doctor.py tests/test_cli_end_to_end.py tests/test_v061_release_acceptance.py -q`

Expected: PASS。

**Step 5: 提交**

```bash
git add tests/test_cli_end_to_end.py tests/test_v061_release_acceptance.py core cli
git commit -m "test: verify v0.6.1 doctor behavior"
```

### Task 6: 更新版本和用户文档

**Files:**
- Modify: `pyproject.toml`
- Modify: `cli/__init__.py`
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `docs/plans/2026-08-04-version-roadmap-v0.6-v1.0.md`
- Modify: `docs/plans/2026-08-04-compatibility-and-doctor-v0.6.x.md`
- Modify: `tests/test_cli_version.py`

**Step 1: 先更新版本失败测试**

要求 `test-assistant --version` 精确输出 `0.6.1`，并增加 `doctor --help` 命令可发现性断言。

**Step 2: 运行失败测试**

Run: `poetry run pytest tests/test_cli_version.py tests/test_cli_doctor.py -q`

Expected: FAIL，当前版本仍为 `0.6.0`。

**Step 3: 更新版本与文档**

同步 `pyproject.toml` 和 `cli/__init__.py`；文档加入 doctor 示例、退出码、支持/降级说明。路线图当前基线改为 v0.6.0 已完成，v0.6.1 完成后再标记 doctor 已交付，不能提前把 v0.6.2 的平台矩阵写成已支持。

**Step 4: 运行文档相关测试**

Run: `poetry run pytest tests/test_cli_version.py tests/test_cli_doctor.py -q`

Expected: PASS，版本精确为 `0.6.1`。

**Step 5: 提交**

```bash
git add pyproject.toml cli/__init__.py README.md docs tests/test_cli_version.py
git commit -m "docs: prepare v0.6.1 doctor release"
```

### Task 7: 发布前完整验证

**Files:**
- Modify: `.github/workflows/ci.yml` only if the existing single-platform wheel smoke does not discover `doctor --help`

**Step 1: 运行静态与完整测试**

```bash
poetry run python -m compileall -q cli core tests
poetry check
poetry run pytest -q
git diff --check
```

Expected: 全部通过，无 warning 被误当成成功证据。

**Step 2: 构建产物**

Run: `poetry build`

Expected: 生成 `test_assistant-0.6.1-py3-none-any.whl` 和 sdist。

**Step 3: 干净环境只安装 wheel**

在 `/private/tmp` 下创建临时虚拟环境，只安装 wheel 和它声明的依赖，不从源码目录导入。

验证：

```bash
test-assistant --version
test-assistant doctor --help
test-assistant doctor --path <minimal-fixture>
test-assistant doctor --path <minimal-fixture> --json
```

Expected: 版本为 `0.6.1`；文本与 JSON 均成功；缺少可选 adapter 时退出码仍为 `0`；fixture 不产生新文件。

**Step 4: 检查 wheel 内容**

确认 wheel 不包含 `tests/`、`.autotest/`、`.env`、本机绝对路径或真实项目数据。

**Step 5: 最终提交**

如 CI smoke 需要更新：

```bash
git add .github/workflows/ci.yml
git commit -m "ci: smoke test installed doctor command"
```

否则不创建空提交。

## 5. v0.6.1 完成标准

- `test-assistant doctor --path .` 能解释当前实际运行环境；
- `--json` 输出稳定的 schema version 1，且 stdout 是纯 JSON；
- Python、pytest、Git、pytest-cov、coverage、Ruff、mypy 均有明确状态和原因；
- 可选工具缺失和非 Git 项目不会误报为核心失败；
- 核心不兼容与基础设施错误使用不同状态和退出码；
- 所有探测均为固定参数数组、有限输出和有限超时；
- 命令不联网、不安装工具、不运行测试/lint/type-check、不写目标项目；
- 完整 pytest、Poetry 校验、语法编译和 `git diff --check` 通过；
- v0.6.1 wheel 在干净 Python 3.13 环境完成版本、帮助、文本和 JSON smoke；
- 文档只声明实际验证过的范围，不提前宣称 v0.6.2 的 Ubuntu/macOS 矩阵或 Python 3.14 支持。

## 6. 明确留给 v0.6.2 的事项

- Ubuntu 与 macOS GitHub Actions wheel 消费矩阵；
- 中文、空格、长路径、符号链接和只读源码目录的系统性矩阵；
- Windows runner 与 Windows 进程终止语义；
- Python 3.14 和新 pytest 的允许失败探测 job；
- 自动生成兼容性支持表。

这些事项可以利用 v0.6.1 的 Doctor 模型作为 CI 证据，但不能反向扩大 v0.6.1 的发布范围。
