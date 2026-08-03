# Contract Migration Triage v0.5.2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 `triage` 自动识别配置默认值迁移、常量值变化和 ORM/Schema 字段类型迁移，并在证据闭合时输出 `TEST_DEFECT / HIGH`。

**Architecture:** 在现有失败根因提取与只读 Git evidence provider 之间增加“契约迁移分析器”。分析器先从失败测试和异常中提取旧值、实际值、字段或配置目标，再验证当前实现、Schema、ORM 和配置是否一致；只有 Git 历史明确记录迁移且当前契约无冲突时才形成高置信度证据。未授权、历史缺失或证据冲突时继续安全降级为 `INCONCLUSIVE`。

**Tech Stack:** Python 3.13、AST、Pydantic 错误解析、Click、pytest、`subprocess(shell=False)`、版本化 JSON。

---

## 真实项目验收案例

v0.5.2 必须覆盖以下来自 `fitstyle-backend` 的真实失败，而不是只使用抽象示例：

1. `ClothingDeleteService.UNDO_EXPIRES_SECONDS`：测试断言 `10`，实现迁移为 `settings.CLOTHING_DELETE_UNDO_SECONDS`，默认值为 `120`。
2. `PaginationParams.page_size`：测试断言 `10`，Schema 迁移为 `settings.DEFAULT_PAGE_SIZE`，默认值为 `20`。
3. `Topic.id`：测试 fixture 使用整数 `1`，ORM 和 `TopicResponse` 已从 `int` 迁移为 UUID 字符串。
4. `FragranceResponse`：ORM 与 Schema 新增四个购买信息可选字段后，旧 `MagicMock(spec=Fragrance)` fixture 未初始化这些属性，Pydantic 实际收到子 `MagicMock` 而不是默认的 `None`。

成功输出必须包含迁移类型、旧契约、当前契约、当前一致性证据和迁移提交 SHA；不得仅输出“Git 中出现过两个值”。

## 明确边界

- 不修改目标项目的测试、源码、配置、数据库或 Git。
- 不执行数据库迁移，不连接数据库，不访问网络。
- 不根据提交信息推测意图；提交信息只能作为展示信息，不能作为唯一证据。
- 不把所有 `expected != actual` 自动判为测试缺陷。
- v0.5.2 不实现覆盖率、Ruff、mypy、安全扫描或自动修复。

### Task 1: 增加真实契约迁移 fixtures

**Files:**
- Create: `tests/fixtures/real_project_triage/config_default_migration/app/config.py`
- Create: `tests/fixtures/real_project_triage/config_default_migration/app/service.py`
- Create: `tests/fixtures/real_project_triage/config_default_migration/case.py`
- Create: `tests/fixtures/real_project_triage/field_type_migration/app/model.py`
- Create: `tests/fixtures/real_project_triage/field_type_migration/app/schema.py`
- Create: `tests/fixtures/real_project_triage/field_type_migration/case.py`
- Create: `tests/fixtures/real_project_triage/optional_field_fixture_drift/app/model.py`
- Create: `tests/fixtures/real_project_triage/optional_field_fixture_drift/app/schema.py`
- Create: `tests/fixtures/real_project_triage/optional_field_fixture_drift/case.py`
- Modify: `tests/test_real_project_fixtures.py`

**Steps:**
1. 写一个 `10 → settings.VALUE → 120` fixture，确认当前 v0.5.1 返回 `INCONCLUSIVE`。
2. 写一个 `id=1 → ORM str + response str` fixture，确认当前 v0.5.1 返回 `INCONCLUSIVE`。
3. 写一个 ORM/Schema 同时新增可选字段、旧 `MagicMock(spec=...)` 未赋值的 fixture，确认 Pydantic 收到 `MagicMock` 而不是 `None`。
4. fixture 使用真实临时 Git 提交表示迁移前后状态，不 mock Git 输出。
5. 运行 `poetry run pytest tests/test_real_project_fixtures.py -q`，保留预期失败作为红灯。
6. 提交 fixtures：`test: add contract migration triage fixtures`。

### Task 2: 提取失败中的旧值、实际值和目标字段

**Files:**
- Create: `core/analyzers/contract_migration.py`
- Modify: `core/analyzers/__init__.py`
- Test: `tests/test_contract_migration_analyzer.py`

**Steps:**
1. 定义不可变模型 `ContractMismatch(kind, target, expected, actual, source_path, test_path)`。
2. AST 识别 `assert object.field == literal` 和 `assert class.CONSTANT == literal`。
3. 解析 Pydantic v2 `ValidationError` 的字段路径、期望类型、输入值和输入类型。
4. 追踪测试内 `fixture.field = literal` 到 `Schema.model_validate(fixture)` 的局部数据流。
5. 识别 `MagicMock(spec=Model)`，区分显式赋值 `None` 与未赋值时生成的子 MagicMock；只在 ValidationError 明确报告 `input_type=MagicMock` 时建立候选证据。
6. 对动态表达式、多个候选目标和无法解析的字符串返回无证据，不猜测。
7. 运行 `poetry run pytest tests/test_contract_migration_analyzer.py -q`。
8. 提交：`feat: extract contract mismatches from failing tests`。

### Task 3: 建立当前契约一致性证据

**Files:**
- Create: `core/analyzers/current_contract.py`
- Test: `tests/test_current_contract.py`

**Steps:**
1. 解析 `Field(default=settings.NAME)`、类常量赋值和简单模块级配置引用。
2. 解析 `Mapped[str]`、`mapped_column(String(...))` 和 Pydantic `field: str`。
3. 只有独立来源一致时才生成 `CurrentContractEvidence`：配置迁移至少需要实现引用和配置默认值；类型迁移至少需要 ORM 与响应 Schema 类型一致。
4. 对新增可选字段，验证 ORM `Mapped[Optional[T]]`/`nullable=True` 与 Pydantic `Optional[T] = None` 一致，并确认测试 fixture 未显式设置该字段。
5. 同一字段出现类型冲突、可空性冲突、环境覆盖值或无法静态求值时标记 `conflict`。
6. 禁止 import 或执行目标项目模块，避免导入副作用。
7. 运行 `poetry run pytest tests/test_current_contract.py -q`。
8. 提交：`feat: validate current static contract consistency`。

### Task 4: 扩展白名单 Git 迁移证据

**Files:**
- Modify: `core/analyzers/git_history.py`
- Test: `tests/test_git_contract_history.py`

**Steps:**
1. 新增 `GitContractHistory`，只保存 SHA、旧表达式摘要、新表达式摘要和降级原因。
2. 复用现有授权；无授权时绝不调用历史 provider。
3. 固定允许 `git log -S/-G --format=%H -- <path>` 与 `git show --format= --unified=0 <sha> -- <path>`。
4. 验证迁移提交同时删除旧契约并增加当前契约；只有一侧时不确认迁移。
5. 限制路径、提交数、超时和输出长度；禁止 `--all` 之外的隐式扩大路径，禁止 shell。
6. 覆盖非仓库、浅克隆、重命名、超时、二进制 diff 和损坏输出的安全降级。
7. 运行 `poetry run pytest tests/test_git_contract_history.py tests/test_git_history.py -q`。
8. 提交：`feat: collect read-only contract migration history`。

### Task 5: 固定高置信度归因决策表

**Files:**
- Modify: `core/workflows/triage.py`
- Modify: `core/models/triage.py`
- Test: `tests/test_triage_contract_migration.py`
- Modify: `tests/test_triage_workflow.py`

**Steps:**
1. 将契约迁移证据按 root-cause key 合并，避免同一配置或字段形成多个失败簇。
2. 配置迁移判定条件：测试旧值与当前默认值冲突、实现引用配置、Git 确认迁移、当前无冲突。
3. 类型迁移判定条件：fixture 旧类型与 Pydantic 错误一致、ORM 与 Schema 当前类型一致、Git 确认旧类型到新类型迁移。
4. 可选字段 fixture 漂移判定条件：Git 确认 ORM 与 Schema 同次新增字段、两侧类型与可空性一致、失败输入类型为 `MagicMock`、旧 fixture 未显式初始化字段。
5. 同一个 Schema 扩展提交造成的多个字段错误合并为一个根因簇，输出全部遗漏字段，不为每个字段重复复跑。
6. 满足全部条件时输出 `TEST_DEFECT / HIGH`；缺少 Git 时为 `INCONCLUSIVE / LOW`；当前契约冲突时为 `INCONCLUSIVE / LOW` 并请求确认。
7. 保持 `INFRA_DEFECT`、`FLAKY`、collection error 和已存在的符号删除优先级不回归。
8. 运行 `poetry run pytest tests/test_triage_contract_migration.py tests/test_triage_workflow.py -q`。
9. 提交：`feat: attribute confirmed contract migrations`。

### Task 6: CLI 展示和审计

**Files:**
- Modify: `cli/commands/triage.py`
- Modify: `core/repositories/triage.py`
- Test: `tests/test_cli_triage.py`
- Modify: `tests/test_triage_repository.py`

**Steps:**
1. 不新增授权参数，继续复用 `--allow-git-history` 和仓库级 permission。
2. 输出 `迁移类型`、`旧契约`、`当前契约`、`当前一致性`、`migration_commit`。
3. JSON 记录保存结构化证据，不保存仓库绝对路径或完整 diff。
4. 未授权输出明确说明“未读取契约迁移历史”，不能暗示已经检查 Git。
5. 运行 `poetry run pytest tests/test_cli_triage.py tests/test_triage_repository.py -q`。
6. 提交：`feat: report contract migration evidence`。

### Task 7: v0.5.2 发布验收

**Files:**
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `pyproject.toml`
- Modify: `tests/test_cli_end_to_end.py`

**Steps:**
1. 将版本提升到 `0.5.2`，记录仍不会自动修改目标项目。
2. 用四个真实 fixture 验证 `TEST_DEFECT / HIGH` 和单根因聚类。
3. 用反例验证实现与 Schema 冲突时不能高置信度归因。
4. 运行 `poetry run pytest -q`，预期全部通过。
5. 运行 `poetry build` 与 `git diff --check`。
6. 在干净 Python 3.13 环境安装 wheel，运行四个 fixture smoke。
7. 在 `fitstyle-backend` 上只读复验四个真实案例。
8. 提交：`release: prepare test-assistant v0.5.2`。

## v0.5.2 完成标准

- 四个真实案例无需人工 Git 命令即可得到正确归因。
- 所有高置信度结论至少包含两个当前契约来源和一个历史迁移提交。
- 未授权或证据不完整时保持 `INCONCLUSIVE`。
- 不新增网络访问、Git 修改、目标代码修改或数据库访问。
