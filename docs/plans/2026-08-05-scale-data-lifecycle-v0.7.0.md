# Scale and Data Lifecycle v0.7.0 Detailed Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 test-assistant 在大型 Python 仓库中具有可重复的性能/内存证据，能够安全读取和显式迁移旧 `.autotest` 记录、预览并清理受控历史数据，并允许只使用确定性能力的用户进行最小安装。

**Architecture:** 先使用确定性合成项目建立测量基线，只有证据超预算时才优化；再抽取共享的版本化 JSON 读取、原子写入和迁移注册表，使正常读取只做内存迁移，显式 `migrate` 才写盘。清理工作流只扫描固定白名单目录，默认 dry-run，并用同文件系统隔离区实现失败可恢复；依赖拆分通过延迟导入保持根 CLI 和确定性命令在 base wheel 中可用。

**Tech Stack:** Python 3.13、pytest、Click、dataclasses、JSON、`tracemalloc`、`resource`、`time.perf_counter_ns`、Git、Poetry optional dependencies。

---

## 1. 固定产品决策

### 1.1 性能 profiles

合成 fixture 不提交生成结果，只提交生成器。固定两个 profile：

| Profile | Python 模块 | 每模块函数 | pytest 测试 | Git 提交 | 用途 |
| --- | ---: | ---: | ---: | ---: | --- |
| `ci` | 100 | 10 | 200 | 5 | 每次 CI 的宽松回归门 |
| `large` | 1,000 | 10 | 2,000 | 25 | 固定机器手工基线与发布验收 |

生成器接受显式 seed；同配置必须得到相同逻辑摘要。文件 mtime、临时绝对路径和 Git commit 时间不得进入摘要。CI 单项安全上限使用 `30s / 512 MiB traced peak`，它只捕获数量级退化，不作为产品速度承诺。精确数字记录在固定环境的 `docs/performance-baseline.md`。

### 1.2 schema v2 范围

v0.7.0 将以下运行记录升级到 schema v2：

- `diagnoses/*.json`；
- `triage/*.json`；
- `audits/*.json`；
- `verification/latest.json`；
- `permissions.json`。

schema v2 在原 payload 上增加稳定 `record_type`，其值分别为 `diagnosis`、`triage`、`audit`、`verification`、`git_permission`。v1→v2 只增加该字段，不改变业务内容。

以下用户资产不纳入本轮通用迁移：TestSpec、candidate metadata、正式测试、snapshot 和 config。它们具有独立契约或包含用户意图，不能用通用记录迁移器改写。

正常 repository 读取允许把 v1 在内存中升级为 v2，但绝不写盘。未知未来版本、错误 `record_type` 和损坏 JSON 必须失败。Audit/Triage/Diagnosis 的 `latest.json` 损坏时，可以从不可变历史中返回最近的有效记录，但只有显式 `migrate --apply` 才修复磁盘上的 latest。

### 1.3 数据清理策略

`test-assistant clean` 默认等同 dry-run。默认候选仅包括：

- `audits/` 中除 `latest.json` 外的不可变历史；
- `triage/` 中除 `latest.json` 外的不可变历史。

默认规则为“至少保留每类最新 20 条，且只选择超过 30 天的历史”。`--max-total-mib` 可以进一步从最旧记录开始选择，仍不得突破保留和引用保护。

Diagnosis 默认永不清理。只有显式 `--include-diagnoses` 才进入候选；被保留的 Triage 或 verification latest 引用的诊断仍不可删除。Candidate、TestSpec、正式测试、snapshot、config、permissions、verification latest 在 v0.7.0 中永不清理。

执行必须同时满足 `--apply` 和 Click 人工确认。删除分两阶段：先原子移动到项目内受控 `.autotest/.trash/<operation-id>/`，全部移动成功后再删除隔离区；移动失败则回滚。顶层 `.autotest`、类型目录或候选文件为符号链接时拒绝，不跟随链接目标。

### 1.4 可选依赖边界

Base wheel 仅直接依赖 Click 与 PyYAML，提供 `doctor`、`init`、`inspect`、`triage`、`audit`（adapter 可降级）、`verify`、`status`、`diagnose`、`report`、`clean` 和 `migrate`。

- `[llm]`：`langchain-core`、`langchain-openai`、`langgraph`、`python-dotenv`，提供 `plan propose`、`generate` 和 legacy graph `run`；
- `[quality]`：pytest-cov、coverage、Ruff、mypy；
- `[all]`：上述两组依赖的并集。

`plan list/show/approve/reject` 不依赖 LLM extra。缺少 extra 时命令返回稳定原因和退出码 2，不尝试联网或安装。pytest 仍由目标项目环境提供，不作为 test-assistant 的强制运行依赖。

---

## 2. 实施任务

### Task 0: 固定 v0.7.0 契约与基线测试入口

**Files:**
- Modify: `docs/plans/2026-08-04-scale-and-data-lifecycle-v0.7.0.md`
- Create: `tests/performance/__init__.py`
- Create: `tests/performance/conftest.py`

**Step 1: 链接本详细计划**

将旧任务级计划标记为摘要，并链接本文件。明确 Audit 重复符号属于独立缺陷，不混入性能优化，除非 benchmark 证明它造成数量级问题。

**Step 2: 注册 pytest marker**

在 `pyproject.toml` 的 pytest 配置中注册 `performance` 和 `large_performance`。默认 `pytest -q` 运行 `ci` profile，但不运行 `large_performance`。

**Step 3: 验证基线**

Run:

```bash
poetry run pytest -q
git diff --check
```

Expected: 当前全量测试通过；仅增加 marker 不改变行为。

**Step 4: Commit**

```bash
git add pyproject.toml docs/plans tests/performance
git commit -m "test: define v0.7.0 scale contracts"
```

### Task 1: 建立确定性大型 fixture 生成器

**Files:**
- Create: `tests/performance/fixture_factory.py`
- Create: `tests/performance/test_fixture_factory.py`

**Step 1: 写失败测试**

定义：

```python
@dataclass(frozen=True)
class FixtureProfile:
    seed: int
    module_count: int
    functions_per_module: int
    test_count: int
    git_commit_count: int

@dataclass(frozen=True)
class GeneratedFixture:
    root: Path
    source_files: tuple[Path, ...]
    test_files: tuple[Path, ...]
    commit_ids: tuple[str, ...]
    logical_digest: str
```

测试相同 profile 在两个目录生成相同相对路径、内容摘要和 commit 数；不同 seed 摘要不同；数量精确；生成结果不包含真实 home、当前时间或网络数据。

**Step 2: 运行失败测试**

```bash
poetry run pytest tests/performance/test_fixture_factory.py -q
```

Expected: FAIL，因为 factory 尚不存在。

**Step 3: 实现最小生成器**

生成 `src/large_fixture/module_NNNN.py`、`tests/test_module_NNNN.py` 和最小 `pyproject.toml`。Git commit 使用固定 author、email 和从 `2000-01-01T00:00:00Z` 递增的 author/committer date；所有 Git 命令使用参数数组、`shell=False` 和有限超时。

**Step 4: 验证并提交**

```bash
poetry run pytest tests/performance/test_fixture_factory.py -q
git add tests/performance
git commit -m "test: add deterministic large repository fixture"
```

### Task 2: 建立可复现测量模型和 runner

**Files:**
- Create: `core/models/performance.py`
- Modify: `core/models/__init__.py`
- Create: `core/benchmarks.py`
- Create: `scripts/run_benchmarks.py`
- Create: `tests/test_performance_model.py`
- Create: `tests/performance/test_benchmark_runner.py`

**Step 1: 固定结果模型**

定义 versioned `BenchmarkResult`：`schema_version=1`、name、profile、input_counts、wall_time_seconds、traced_peak_bytes、rss_peak_bytes、output_digest。验证有限非负数字、非空名称和稳定字典字段。

**Step 2: 固定测量语义**

`measure_benchmark(callable)` 使用 `perf_counter_ns` 和 `tracemalloc`；RSS 在 macOS 将 `ru_maxrss` 视为 bytes，在 Linux 乘 1024。runner 预热一次，正式测量三次，文档报告中位数与最大峰值；CI 门只检查每次不超过安全上限。

**Step 3: CLI runner**

```bash
poetry run python scripts/run_benchmarks.py --profile ci --json
poetry run python scripts/run_benchmarks.py --profile large --output docs/performance-baseline.json
```

`--json` stdout 必须为纯 JSON；`--output` 原子写入；未知 profile 退出 2。

**Step 4: TDD 验证与提交**

```bash
poetry run pytest tests/test_performance_model.py tests/performance/test_benchmark_runner.py -q
git add core/models core/benchmarks.py scripts/run_benchmarks.py tests
git commit -m "feat: add deterministic benchmark runner"
```

### Task 3: 测量五条关键路径并记录基线

**Files:**
- Create: `tests/performance/test_analysis_benchmarks.py`
- Create: `tests/performance/test_repository_benchmarks.py`
- Create: `docs/performance-baseline.md`
- Modify: `.github/workflows/ci.yml`

**Step 1: 为五条路径写 benchmark adapter**

测量：

1. `take_snapshot()` 和 Python symbol snapshot；
2. `index_python_project_tests()` / `select_tests_for_changes()`；
3. 白名单 `read_symbol_history()`；
4. `PytestExecutor` 的 JSONL 事件解析（使用固定 100,000 条合成事件，不启动 pytest）；
5. Audit/Triage/Diagnosis 原子记录保存与 latest 更新。

每项必须断言输出计数和 digest，防止“通过跳过工作获得性能提升”。

**Step 2: CI 宽松回归门**

新增独立 `performance-smoke` job，只运行 `ci` profile，超时 10 分钟；单项上限 `30s / 512 MiB traced peak`。不把不同 runner 的精确毫秒差异与历史常量比较。

**Step 3: 固定机器记录 large baseline**

文档记录 CPU、OS、Python、Git SHA、profile、三次原始结果、中位数和峰值。不得提交 fixture 的绝对路径或项目源码。

**Step 4: 验证与提交**

```bash
poetry run pytest tests/performance -m performance -q
poetry run python scripts/run_benchmarks.py --profile ci --json
git add .github/workflows/ci.yml docs/performance-baseline.md tests/performance scripts
git commit -m "test: establish scale and memory baselines"
```

### Task 4: 只对超预算路径做证据驱动优化

**Files:**
- Modify only the measured module that exceeds budget
- Modify matching tests under `tests/performance/`
- Modify: `docs/performance-baseline.md`

**Step 1: 建立优化前证据**

保存相同 profile 的三次结果和 profiler 归因。没有路径超出安全预算时，本 Task 标记为 `not needed`，不创建代码提交。

**Step 2: 按优先级最小优化**

依次考虑目录剪枝、一次遍历、流式 JSONL、避免重复 AST、以内容摘要为 key 的有界单次运行缓存。禁止全局无界缓存、并发扩大和改变诊断语义。

**Step 3: 证明结果等价**

输出 digest 必须完全相同；性能测试至少三次，记录前后中位数与峰值。

**Step 4: 回归并按需提交**

```bash
poetry run pytest tests/performance tests/test_snapshot.py tests/test_impact.py tests/test_pytest_triage_parser.py -q
git commit -m "perf: reduce measured analysis overhead"
```

仅在确有改动时提交。

### Task 5: 抽取共享 versioned JSON 基础设施

**Files:**
- Create: `core/repositories/schema.py`
- Modify: `core/repositories/__init__.py`
- Create: `tests/test_repository_schema.py`

**Step 1: 写失败测试**

覆盖：原子写入、损坏 JSON、bool schema、未知未来版本、错误 record type、v1→v2 纯迁移、输入对象不被修改、迁移链缺口、写入失败保留旧文件。

**Step 2: 定义 API**

```python
@dataclass(frozen=True)
class LoadedRecord:
    payload: dict[str, object]
    source_version: int
    migrated: bool

class SchemaRegistry:
    def load(self, path: Path, *, record_type: str) -> LoadedRecord: ...
    def migrate_payload(self, payload: Mapping[str, object], *, record_type: str) -> LoadedRecord: ...

def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None: ...
```

迁移函数必须纯函数；registry 不扫描目录、不决定清理策略。

**Step 3: 实现并验证**

```bash
poetry run pytest tests/test_repository_schema.py -q
git add core/repositories/schema.py core/repositories/__init__.py tests/test_repository_schema.py
git commit -m "feat: add shared repository schema migrations"
```

### Task 6: 将运行记录升级为 schema v2 并提供内存恢复

**Files:**
- Modify: `core/repositories/diagnosis.py`
- Modify: `core/repositories/triage.py`
- Modify: `core/repositories/audit.py`
- Modify: `core/repositories/verification.py`
- Modify: `core/repositories/permissions.py`
- Modify: `cli/commands/status.py`
- Modify: `cli/commands/report.py`
- Create: `tests/test_repository_migrations.py`
- Modify existing repository and CLI tests

**Step 1: 固定 v1 fixtures**

从当前测试构造最小合法 v1 Diagnosis/Triage/Audit/Verification/Permission。断言读取结果为 schema v2 + 正确 `record_type`，但磁盘 bytes 不变。

**Step 2: 新写入使用 v2**

所有新运行记录包含 `schema_version: 2` 和 `record_type`。repository 业务字段验证仍由各自负责，不能只相信通用 registry。

**Step 3: latest 内存恢复**

Audit/Triage/Diagnosis 遇到损坏或不支持的 latest 时，按 payload `created_at` 选择最近的有效历史记录；忽略符号链接、latest 自身和不匹配 record type。普通读取不得修复文件，并向 CLI 暴露 `recovered=True/source_path` 以显示降级来源。

Verification 与 Permission 没有不可变历史，损坏时仍明确失败。

**Step 4: 验证**

```bash
poetry run pytest tests/test_repository_migrations.py tests/test_diagnosis_repository.py tests/test_triage_repository.py tests/test_audit_repository.py tests/test_git_permission_repository.py tests/test_cli_diagnose_status.py -q
```

**Step 5: Commit**

```bash
git add core/repositories cli/commands/status.py cli/commands/report.py tests
git commit -m "feat: read v1 records through schema v2"
```

### Task 7: 增加显式 migrate 工作流与 CLI

**Files:**
- Create: `core/models/migration.py`
- Modify: `core/models/__init__.py`
- Create: `core/workflows/migrate.py`
- Modify: `core/workflows/__init__.py`
- Create: `cli/commands/migrate.py`
- Modify: `cli/main.py`
- Create: `tests/test_migrate_workflow.py`
- Create: `tests/test_cli_migrate.py`

**Step 1: 固定命令契约**

```bash
test-assistant migrate --path . --dry-run
test-assistant migrate --path . --apply
```

默认 dry-run。输出每个受控文件的 record type、源版本、目标版本和 `migrate/repair_latest/skip`。`--apply` 必须人工确认；取消退出 0 且无写入。JSON 仅允许 dry-run。

**Step 2: 安全扫描测试**

只扫描 1.2 节白名单；拒绝顶层或内部类型目录符号链接；普通未知文件不删除、不改写；未知未来 schema 阻止 apply；一次 apply 中任一写入失败时保留原文件和可恢复备份。

**Step 3: 实现事务**

在项目同级创建受控备份目录，复用 init 的备份路径验证原则；全部目标先备份，再用 `atomic_write_json` 替换。成功后删除备份；失败恢复全部原 bytes。

**Step 4: 验证并提交**

```bash
poetry run pytest tests/test_migrate_workflow.py tests/test_cli_migrate.py tests/test_repository_migrations.py -q
git add core/models core/workflows cli tests
git commit -m "feat: add explicit autotest schema migration"
```

### Task 8: 建立清理领域模型和候选规划器

**Files:**
- Create: `core/models/cleanup.py`
- Modify: `core/models/__init__.py`
- Create: `core/workflows/clean.py`
- Modify: `core/workflows/__init__.py`
- Create: `tests/test_clean_workflow.py`

**Step 1: 定义稳定模型**

定义 `CleanupRecordType`、`CleanupReason`、`CleanupCandidate(relative_path, type, size_bytes, created_at, reasons)`、`CleanupPlan(schema_version=1, candidates, protected_count, reclaimable_bytes)` 和 `CleanupResult`。所有对外路径必须相对 `.autotest`。

**Step 2: 写候选决策表**

覆盖年龄边界、最新 20 条、latest alias、容量压力、Diagnosis opt-in、Triage/Verification 引用保护、候选/TestSpec 永久保护、损坏 JSON、符号链接、hard link、非规则文件和重复 inode。

损坏记录默认保护并报告 `invalid_record`，不得为释放空间而删除无法理解的数据。

**Step 3: 实现纯规划器**

```python
def plan_cleanup(
    *,
    project_root: str | Path,
    older_than_days: int = 30,
    keep_latest: int = 20,
    max_total_bytes: int | None = None,
    include_diagnoses: bool = False,
    now: datetime | None = None,
) -> CleanupPlan: ...
```

规划器只读，不创建 `.autotest` 或临时文件。

**Step 4: 实现可恢复执行器**

```python
def execute_cleanup(*, project_root: str | Path, plan: CleanupPlan) -> CleanupResult: ...
```

重新校验每个候选的相对路径、inode/size/mtime，防止 plan 后竞争修改；先移动到 `.trash`，失败回滚。成功后删除隔离区并 fsync 父目录。

**Step 5: 验证并提交**

```bash
poetry run pytest tests/test_clean_workflow.py -q
git add core/models/cleanup.py core/models/__init__.py core/workflows/clean.py core/workflows/__init__.py tests/test_clean_workflow.py
git commit -m "feat: plan and execute safe autotest cleanup"
```

### Task 9: 增加 clean CLI

**Files:**
- Create: `cli/commands/clean.py`
- Modify: `cli/main.py`
- Create: `tests/test_cli_clean.py`
- Modify: `tests/test_cli_end_to_end.py`

**Step 1: 固定 CLI**

```text
--path DIRECTORY
--older-than-days INTEGER RANGE   default 30
--keep-latest INTEGER RANGE       default 20
--max-total-mib FLOAT RANGE
--include-diagnoses
--dry-run / --apply               default dry-run
--json                            dry-run only
```

文本先显示总候选数/字节，再按类型列出相对路径与原因。没有候选退出 0。参数/扫描/事务错误退出 2；不得回显目标文件内容。

**Step 2: 确认语义测试**

`--apply` 必须出现候选摘要后再确认。拒绝时 bytes 不变；确认时只删除计划内文件；执行前发生竞态时失败且不删除新内容。

**Step 3: 真实 CLI no-surprise 测试**

用临时 `.autotest` 同时放入历史记录、latest、TestSpec、candidate、正式测试、snapshot、permissions。dry-run 前后全树一致；apply 后只有白名单候选消失。

**Step 4: 验证并提交**

```bash
poetry run pytest tests/test_cli_clean.py tests/test_clean_workflow.py tests/test_cli_end_to_end.py -q
git add cli/commands/clean.py cli/main.py tests
git commit -m "feat: add explicit clean command"
```

### Task 10: 拆分 base、llm、quality 依赖并延迟导入

**Files:**
- Modify: `pyproject.toml`
- Modify: `poetry.lock`
- Modify: `cli/main.py`
- Modify: `cli/commands/plan.py`
- Modify: `cli/commands/generate.py`
- Modify: `cli/commands/run.py`
- Modify: `core/graphs/run_graph.py`
- Create: `core/optional_dependencies.py`
- Create: `tests/test_optional_dependencies.py`
- Create: `tests/test_installed_extras.py`
- Modify: `.github/workflows/ci.yml`

**Step 1: 写 base-import 失败测试**

在隔离 venv 仅安装 `--no-deps` wheel + Click/PyYAML，断言 `test-assistant --help`、`doctor --help`、`triage --help`、`plan list --help` 可导入；`plan propose`、`generate`、`run` 缺 extra 时返回 `llm_extra_required/2`，不出现 traceback。

**Step 2: 移动依赖**

`[project.dependencies]` 只保留 Click/PyYAML；新增 `[project.optional-dependencies] llm/quality/all`。删除未被直接使用的顶层 `langchain` 声明。

**Step 3: 延迟导入**

将 `LLMClient` 移入 `plan propose` 和 `generate` handler；将 LangGraph import 移入 graph 构建路径。`OptionalDependencyError(extra, capability)` 由 CLI 统一映射为稳定错误，不捕获用户项目自己的 ImportError。

**Step 4: 三种 wheel 安装矩阵**

CI 构建一次 wheel，分别安装：

- base：`wheel + pytest`；
- llm：`wheel[llm] + pytest`，只做 import/help，不联网调用模型；
- quality：`wheel[quality] + pytest`，运行 Doctor 并确认 adapters available。

**Step 5: 验证并提交**

```bash
poetry lock
poetry check
poetry run pytest tests/test_optional_dependencies.py tests/test_installed_extras.py tests/test_cli_plan.py tests/test_cli_generate.py tests/test_cli_run.py -q
git add pyproject.toml poetry.lock cli core tests .github/workflows/ci.yml
git commit -m "feat: split optional llm and quality dependencies"
```

### Task 11: 更新 v0.7.0 版本和用户文档

**Files:**
- Modify: `pyproject.toml`
- Modify: `cli/__init__.py`
- Modify: `tests/test_cli_version.py`
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `docs/performance-baseline.md`
- Modify: `docs/plans/2026-08-04-version-roadmap-v0.6-v1.0.md`
- Modify: `docs/plans/2026-08-04-scale-and-data-lifecycle-v0.7.0.md`

**Step 1: 版本测试先失败**

要求根 CLI 精确输出 `0.7.0`，并发现 `migrate`、`clean`。

**Step 2: 同步版本与文档**

文档必须包含性能 profile/测量限制、schema v2、正常读取不写盘、migrate 事务、clean 默认保护、extras 安装命令和退出码。不得把 large profile 数字描述为所有机器的 SLA。

**Step 3: 验证与提交**

```bash
poetry lock
poetry check
poetry run pytest tests/test_cli_version.py tests/test_cli_clean.py tests/test_cli_migrate.py tests/test_installed_extras.py -q
git add pyproject.toml poetry.lock cli/__init__.py README.md docs tests/test_cli_version.py
git commit -m "docs: prepare v0.7.0 scale release"
```

### Task 12: 完整发布与真实项目验收

**Files:**
- Create: `tests/test_v070_release_acceptance.py`
- Modify: `.github/workflows/ci.yml` only for demonstrated gaps

**Step 1: 自动化发布门**

```bash
poetry run python -m compileall -q cli core scripts tests
poetry check
poetry run pytest -q
poetry run pytest tests/performance -m performance -q
poetry run python scripts/run_benchmarks.py --profile ci --json
git diff --check
poetry build
```

**Step 2: 检查产物**

确认 wheel/sdist 版本 0.7.0、Python `>=3.13,<3.14`、无 tests/`.autotest`/`.env`/绝对路径/真实项目数据，并生成 SHA-256。

**Step 3: 干净安装验收**

分别安装 base、`[llm]`、`[quality]` wheel。base 环境运行 Doctor、Triage help、migrate dry-run、clean dry-run；llm 只做 import/help；quality 确认 coverage/Ruff/mypy 可探测。所有临时目录验收后清理。

**Step 4: `fitstyle-backend` 只读验收**

先记录 Git 状态和 `.autotest` 全树摘要，然后运行：

```bash
test-assistant doctor --path . --json
test-assistant migrate --path . --dry-run
test-assistant clean --path . --dry-run --json
poetry run python /path/to/test-assistant/scripts/run_benchmarks.py --profile ci --project . --json
```

真实项目只允许 dry-run；schema apply 和 clean apply 只在 `.autotest` 副本中验证。验收后 Git 状态及真实 `.autotest` bytes 必须不变，结果只记录版本、计数、耗时、峰值和可回收字节，不提交源码路径或记录内容。

**Step 5: 发布条件**

Ubuntu/macOS base/llm/quality wheel matrix、全量测试、性能宽松门和真实项目只读验收全部通过后，才允许 Tag `v0.7.0`。

**Step 6: Commit**

```bash
git add tests/test_v070_release_acceptance.py .github/workflows/ci.yml docs
git commit -m "test: verify v0.7.0 scale and lifecycle release"
```

---

## 3. 明确不属于 v0.7.0

- 自动清理 candidate、TestSpec、正式测试、snapshot、config 或 permissions；
- 后台定时清理、全局缓存或常驻索引服务；
- 自动修改用户项目以提升性能；
- 将单台开发机 benchmark 当成跨平台 SLA；
- Windows 支持、Python 3.14 认证；
- Web、多用户服务、自动调参、安全扫描或 PyPI 正式发布；
- 为 Audit 重复未覆盖符号顺带改变业务语义；该问题单独跟踪。

## 4. v0.7.0 完成标准

- `ci`/`large` fixture 可确定性重建且不提交巨量文件；
- 五条关键路径有输出 digest、wall time、traced/RSS peak 和输入规模；
- CI 使用宽松安全上限，固定机器文档记录可比较基线；
- v1 运行记录可内存读取为 v2，正常读取不改写磁盘；
- 未知未来 schema 和错误 record type 明确失败；
- 损坏 Audit/Triage/Diagnosis latest 可从有效历史只读恢复；
- `migrate` 默认 dry-run，apply 有完整备份和失败回滚；
- `clean` 默认 dry-run，只处理白名单历史并保护引用和用户资产；
- base wheel 不安装 LLM/quality 依赖，缺 extra 时结构化降级且不联网；
- base、llm、quality 三类 wheel 安装和 Ubuntu/macOS CI 通过；
- `fitstyle-backend` dry-run 验收不改变 Git 或 `.autotest` bytes。
