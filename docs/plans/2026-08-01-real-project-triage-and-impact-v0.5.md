# Real-Project Triage and Impact v0.5.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于 `fitstyle-backend` 的真实试用证据，让 `test-assistant` 能正确映射常见实例方法测试，并对已有 pytest 测试套件的失败进行确定性分组、复跑和五类归因。

**Architecture:** 保留 `verify` 的“已批准 TestSpec + 单个精确 pytest node”职责，新增独立 `triage` 工作流处理项目已有测试。`triage` 先运行或读取 pytest 结果，形成结构化失败簇，再复用执行器、契约提取、重复运行、诊断模型和持久化能力；首版不调用 LLM，也不自动修改产品代码或测试。影响分析侧扩展 AST 测试索引，使 `self.service.method()` 等常见实例调用能映射回源码符号，并把无法精确判断的文件级变更明确标为保守近似。

**Tech Stack:** Python 3.13、Click、pytest、Python AST、现有 `ExecutionReport` / `Diagnosis` / JSON repositories。

---

## 1. 真实项目试用基线

目标项目：`fitstyle-backend`（本地 Python/pytest 项目）。本文只记录脱敏后的行为和命令，不复制业务源码、密钥、数据库地址或用户数据。

首次全量基线：

```text
1990 collected
1927 passed
50 failed
10 skipped
3 errors
18 warnings
```

真实试用采用以下循环：

```text
pytest -q -x
→ 定位第一个失败
→ 检查源码、测试、契约和 Git 历史
→ 归入五类诊断
→ 对同文件运行完整测试形成失败簇
→ 修复明确产品缺陷或暂时 deselect 已确认旧测试
→ 继续采样
```

截至本文创建时，已分析的代表性场景如下：

| 场景 | 真实表现 | 归因 | 关键证据 |
| --- | --- | --- | --- |
| 已删除方法仍被旧测试要求 | 3 个测试要求已经移除的异步语义相似度方法 | `TEST_DEFECT` | 当前设计明确移除该能力，Git 历史包含删除提交 |
| 依赖迁移后 mock 未更新 | 2 个测试 patch 已不存在的 `clip.load` | `TEST_DEFECT` | 实现已迁移到 HuggingFace `from_pretrained` |
| 业务时间契约冲突 | 测试和 Schema 为 10 秒，实现配置默认为 120 秒 | `INCONCLUSIVE` | 两侧均有明确证据，但变更提交没有业务解释 |
| 布尔函数缺少失败返回 | 4 个反例得到 `None` 而不是 `False` | `PRODUCT_DEFECT` | `-> bool`、docstring 和测试一致；补 `return False` 后 25 个测试通过 |
| 实例方法测试未映射 | `inspect` 找到变更方法，却对已有测试返回 `none` | 工具缺陷 | 测试通过 `self.service.method()` 调用，索引器只处理直接导入和模块属性调用 |
| 单元测试触发外部连接 | 导入服务时尝试连接本地 Milvus | 基础设施风险 | 测试虽通过，但出现真实连接失败日志 |
| 同步方法被异步 mock | 多处 `AsyncMock` 调用产生“never awaited”警告 | 待确认测试基础设施缺陷 | SQLAlchemy `AsyncSession.add()` 是同步方法，测试 double 可能配置错误 |

## 2. 版本范围

### 2.1 v0.5.0 必须完成

- 提供可提交、可重复、无业务代码的最小 fixture，覆盖上述五个核心归因/映射场景。
- `inspect` 能把常见的实例变量和 `self` 属性方法调用映射到源码类方法。
- `inspect` 不把“没有直接映射”描述为“没有测试”；输出明确的未解析原因与安全降级。
- 新增 `test-assistant triage --path .`，可运行已有 pytest 套件并解析失败、错误、跳过和警告摘要。
- 对失败 node 进行精确复跑，区分稳定失败、Flaky、收集/Runner 故障。
- 以失败簇为单位输出 `PRODUCT_DEFECT`、`TEST_DEFECT`、`INFRA_DEFECT`、`FLAKY` 或 `INCONCLUSIVE`。
- 诊断必须展示证据、置信度、位置、复现命令和建议动作。
- 无批准强契约或证据冲突时保持 `INCONCLUSIVE`。
- 保存 triage 运行摘要和诊断历史，且对输出进行脱敏和体积限制。
- 不自动修改产品源码、测试、配置、TestSpec 或快照。

### 2.2 v0.5.0 明确不做

- 不引入 Web Dashboard、watch、Vitest、Playwright 或 ReAct Agent。
- 不使用 LLM 判定失败类别；真实模型不是默认验收条件。
- 不自动删除、跳过、放宽或改写失败断言。
- 不根据当前实现值自动覆盖文档或测试契约。
- 不实现跨模块完整数据流/类型推断；无法可靠解析时结构化降级。
- 不把 triage 成功等同于提交 snapshot；快照仍由原增量流程管理。

## 3. 目标用户流程

```text
test-assistant triage --path .
→ pytest preflight / collect
→ 运行现有测试套件
→ 解析 node 和阶段
→ 按共同异常、位置和失败模式聚类
→ 对代表 node 精确复跑 3 次
→ 收集源码、测试、契约、环境和 Git 证据
→ 确定性归因
→ 保存运行摘要和诊断
→ 输出下一步及精确复现命令
```

支持用户控制运行范围：

```bash
test-assistant triage --path .
test-assistant triage --path . --test-path tests/test_service.py
test-assistant triage --path . --test-node tests/test_service.py::test_case
test-assistant triage --path . --max-failures 10
```

`--test-path`、`--test-node` 互斥。所有 pytest 参数由结构化 CLI 选项生成，不接受拼接后的任意 shell 字符串。

## 4. 领域与存储设计

新增稳定领域对象：

```python
class TriagePhase(StrEnum):
    COLLECTION = "collection"
    EXECUTION = "execution"
    WARNING = "warning"

@dataclass(frozen=True)
class PytestIssue:
    node_id: str | None
    phase: TriagePhase
    outcome: str
    exception_type: str | None
    message: str
    locations: tuple[DiagnosisLocation, ...]

@dataclass(frozen=True)
class FailureCluster:
    fingerprint: str
    representative_node: str | None
    issues: tuple[PytestIssue, ...]

@dataclass(frozen=True)
class TriageResult:
    run_id: str
    report: ExecutionReport
    clusters: tuple[FailureCluster, ...]
    diagnoses: tuple[Diagnosis, ...]
```

失败指纹首版只使用确定性信息：phase、异常类型、归一化首个错误位置和去除临时路径/地址后的消息模板。不要仅按完整 stdout 字符串聚类。

目标项目存储：

```text
.autotest/
├── triage/
│   ├── <run-id>.json
│   └── latest.json
└── diagnoses/
    └── ...                 复用现有诊断历史
```

## 5. 实施任务

### Task 1: 建立脱敏真实项目 fixture

**Files:**
- Create: `tests/fixtures/real_project_triage/*/app/__init__.py`
- Create: `tests/fixtures/real_project_triage/stale_removed_method/app/service.py`
- Create: `tests/fixtures/real_project_triage/stale_removed_method/case.py`
- Create: `tests/fixtures/real_project_triage/migrated_dependency_mock/app/model.py`
- Create: `tests/fixtures/real_project_triage/migrated_dependency_mock/case.py`
- Create: `tests/fixtures/real_project_triage/conflicting_contract/app/{config,schema,service}.py`
- Create: `tests/fixtures/real_project_triage/conflicting_contract/case.py`
- Create: `tests/fixtures/real_project_triage/missing_boolean_return/app/service.py`
- Create: `tests/fixtures/real_project_triage/missing_boolean_return/case.py`
- Create: `tests/fixtures/real_project_triage/instance_method_mapping/app/service.py`
- Create: `tests/fixtures/real_project_triage/instance_method_mapping/case.py`
- Create: `tests/test_real_project_fixtures.py`

**Steps:**

1. 为每个目录写一个不含业务名和外部依赖的最小项目，保留真实失败结构。
2. 写参数化测试，调用目标解释器运行每个 fixture，并锁定退出码与首个失败类型。
3. 运行 `poetry run pytest tests/test_real_project_fixtures.py -q`，确认 fixture 行为稳定。
4. 检查 fixture 不包含绝对路径、token、真实服务地址或业务数据。
5. 提交：`test: add anonymized real-project triage fixtures`。

### Task 2: 支持实例方法测试映射

**Files:**
- Modify: `core/analyzers/source.py`
- Modify: `core/models/source.py`
- Test: `tests/test_test_index.py`
- Test: `tests/test_impact.py`

**Steps:**

1. 写失败测试覆盖以下形式：

```python
from app.service import Service

class TestService:
    def setup_method(self):
        self.service = Service()

    def test_rule(self):
        assert self.service.rule({}) is False
```

2. 运行精确测试，确认当前索引为空。
3. 在 AST 索引中收集测试类的 `setup_method` / `setup_class` 赋值，将构造器本地名解析为源码类限定名。
4. 将 `self.<attribute>.<method>` 解析为 `<source class>.<method>`；只有目标方法存在于 `source_symbols` 时建立映射。
5. 增加同一测试内局部实例 `service = Service(); service.rule()`、import alias 和无法解析对象的降级测试。
6. 禁止仅凭方法同名跨类猜测映射。
7. 运行 `poetry run pytest tests/test_test_index.py tests/test_impact.py -q`。
8. 提交：`feat: map common instance method calls to source symbols`。

### Task 3: 明确符号级变更精度与安全降级

**Files:**
- Modify: `core/analyzers/snapshot.py`
- Modify: `core/analyzers/source.py`
- Modify: `core/analyzers/impact.py`
- Modify: `core/models/impact.py`
- Test: `tests/test_snapshot.py`
- Test: `tests/test_impact.py`
- Test: `tests/test_cli_inspect.py`

**Steps:**

1. 写测试锁定“仅函数体增加 `return False` 时，只报告该方法”的期望。
2. 为 snapshot 保存可选的 Python 符号摘要：限定名、范围和规范化 AST hash；旧 snapshot 缺少该字段时保持兼容。
3. 比较新旧符号摘要，返回 added / modified / deleted symbol；文件语法损坏或旧基线不足时标记 `file_level_fallback`。
4. 更新 `inspect`：精确时输出真实 changed symbols；降级时明确说明“文件级保守分析，可能包含未修改符号”。
5. 删除符号、重命名、装饰器变化和签名变化必须进入影响分析。
6. 运行相关测试并确认旧 snapshot fixture 仍可加载。
7. 提交：`feat: track symbol-level Python changes with safe fallback`。

### Task 4: 结构化解析 pytest 套件问题

**Files:**
- Modify: `core/executors/pytest_executor.py`
- Modify: `core/executors/base.py`
- Create: `core/models/triage.py`
- Modify: `core/models/__init__.py`
- Test: `tests/test_executors.py`
- Create: `tests/test_pytest_triage_parser.py`

**Steps:**

1. 添加失败测试，覆盖 passed、failed、setup error、collection error、skipped、warning、timeout 和无测试收集。
2. 优先使用 pytest 可稳定消费的结构化输出；若新增最小内部 pytest plugin，则将事件写到临时 JSON 文件，不解析彩色终端文本。
3. 将 suite 结果转换为 `PytestIssue`，保留 stdout/stderr 摘要但限制体积。
4. 区分测试断言失败、fixture/setup error、收集失败和 Runner 启动失败。
5. 确保 `PytestExecutor.execute()` 的现有单 node 行为保持兼容。
6. 运行 `poetry run pytest tests/test_executors.py tests/test_pytest_triage_parser.py -q`。
7. 提交：`feat: capture structured pytest suite issues`。

### Task 5: 确定性失败聚类和归因

**Files:**
- Create: `core/diagnosticians/clustering.py`
- Create: `core/workflows/triage.py`
- Modify: `core/workflows/__init__.py`
- Modify: `core/diagnosticians/__init__.py`
- Test: `tests/test_triage_clustering.py`
- Test: `tests/test_triage_workflow.py`

**Steps:**

1. 用五个真实 fixture 写失败测试，锁定聚类数量与代表 node。
2. 实现稳定 fingerprint，路径、内存地址、时间戳和随机临时目录不影响聚类。
3. 对每个可执行失败簇选择代表 node，使用现有 repeatability 能力精确复跑三次。
4. 归因顺序固定为：Runner/collection → test structure → repeatability → contract conflict → strong contract violation → insufficient evidence。
5. 缺失符号且 Git 历史/当前源码明确显示能力已移除时可建议 `TEST_DEFECT`；首版证据不足则保持 `INCONCLUSIVE`，不得猜测提交意图。
6. 类型注解、docstring 和多个有效测试一致且实现违反返回契约时，允许形成高置信度 `PRODUCT_DEFECT`。
7. 契约值冲突时必须是 `INCONCLUSIVE` + `REQUEST_CONFIRMATION`。
8. 运行 `poetry run pytest tests/test_triage_clustering.py tests/test_triage_workflow.py -q`。
9. 提交：`feat: add deterministic existing-suite triage workflow`。

### Task 6: Triage repository 与脱敏

**Files:**
- Create: `core/repositories/triage.py`
- Modify: `core/repositories/__init__.py`
- Modify: `core/reporters.py`
- Test: `tests/test_triage_repository.py`

**Steps:**

1. 写失败测试覆盖版本化记录、latest、原子写入、损坏 JSON 和路径边界。
2. 保存 run id、pytest 摘要、失败簇、诊断引用、Git SHA、依赖摘要和复现命令。
3. 复用现有密钥脱敏规则，并移除目标项目绝对根路径。
4. 限制单个 issue 和整次运行的 stdout/stderr 体积，记录截断事实。
5. 失败持久化不能修改 snapshot、TestSpec 或正式测试。
6. 运行 `poetry run pytest tests/test_triage_repository.py -q`。
7. 提交：`feat: persist redacted triage runs`。

### Task 7: `test-assistant triage` CLI

**Files:**
- Create: `cli/commands/triage.py`
- Modify: `cli/main.py`
- Create: `tests/test_cli_triage.py`

**Steps:**

1. 写 CLI 测试覆盖默认套件、文件范围、精确 node、最大失败数、路径错误和互斥参数。
2. CLI 只做参数解析、调用 workflow 和文本展示。
3. 输出 suite 摘要、每个失败簇的类别/置信度/证据、代表 node、复现命令和记录路径。
4. 退出码定义：无问题为 `0`；存在未解决诊断为 `1`；参数、环境或持久化错误为 `2`。
5. `triage` 不要求 TestSpec；存在已批准 TestSpec 时可附加其契约证据，但不能修改审批状态。
6. 运行 `poetry run pytest tests/test_cli_triage.py -q`。
7. 提交：`feat: add existing pytest suite triage command`。

### Task 8: 真实项目验收与 v0.5.0 文档

**Files:**
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `docs/plans/2026-07-27-python-cli-trusted-loop-roadmap.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Test: `tests/test_cli_end_to_end.py`

**Steps:**

1. 在脱敏 fixture 上完成 `inspect → triage → diagnose/report` 端到端测试。
2. 在 `fitstyle-backend` 的测试副本上执行只读 smoke test，确认实例方法能映射到 `tests/test_cold_start_service.py`。
3. 确认 `triage` 能把五类代表场景分流，且契约冲突不被判为产品缺陷。
4. 确认执行过程中不修改目标源码、已有测试、TestSpec 审批状态或 snapshot。
5. 更新用户指南，说明 `run`、`verify`、`triage` 的职责边界。
6. 将版本提升到 `0.5.0`，更新 CLI help 与当前限制。
7. 运行：

```bash
poetry run pytest -q
poetry build
git diff --check
```

8. 在干净 Python 3.13 虚拟环境安装 wheel，运行 fixture smoke test。
9. 提交：`release: prepare test-assistant v0.5.0`。

## 6. 验收门

v0.5.0 只有同时满足以下条件才算完成：

- 默认自动化测试全部通过，且没有新增未解释 warning。
- `self.service.method()` 与局部实例 `service.method()` 均能正确映射，无法解析时不按方法名猜测。
- 只修改一个方法时，`inspect` 精确报告该方法；降级时明确标注精度。
- pytest collection error、setup error、assertion failure、Runner error 和 warning 可结构化区分。
- 同根因失败能聚为一簇，不同异常不会因消息相似被错误合并。
- 稳定失败与 Flaky 通过三次精确复跑区分。
- 过期测试、迁移 mock、契约冲突和缺失布尔返回 fixture 得到预期类别；证据不足默认 `INCONCLUSIVE`。
- `triage` 不调用 LLM、不自动修复、不更新 snapshot。
- 诊断记录不包含密钥、真实绝对路径或无限量执行输出。
- CLI help、用户指南、项目结构和实际行为一致。
- `fitstyle-backend` smoke test 能选择冷启动服务已有测试，而不是返回 `none`。

## 7. 后续版本候选

> **历史说明：** 下列内容是 v0.5.0 当时的候选排序。v0.6.0 已在后续反馈中确定为 coverage、Ruff、mypy 与只读 `audit`；当前版本定义见 `docs/plans/2026-08-04-version-roadmap-v0.6-v1.0.md`。

只有 v0.5.0 获得更多真实项目反馈后再排序：

1. `v0.5.x`：warning 严格模式、外部连接副作用检测、可导入既有 JUnit XML。
2. `v0.6.0`：经人工确认的机械性测试修复建议与候选 diff；仍禁止自动修改业务断言。
3. `v1.0.0`：发布门、干净环境矩阵、安全审计和真实项目回归矩阵。
4. `v1.1+`：Vitest、watch、Web 或受限 Agent，根据真实收益选择，不预先并行铺开。

## 8. 架构决策

- `triage` 与 `verify` 分离：前者处理既有套件，后者验证已批准 TestSpec 对应的单 node。
- 确定性证据优先：pytest 事件、AST、类型、docstring、Git 和重复运行先于任何模型总结。
- fixture 来源于真实失败结构，但必须最小化和脱敏。
- 诊断与修复继续分离；v0.5.0 只解释和建议，不落盘修改目标代码。
- 影响映射宁可明确降级，也不跨类型按方法同名猜测。
- 真实项目 smoke test 是发布证据，不成为仓库自动测试对外部项目路径的硬依赖。
