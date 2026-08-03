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
5. `COVER_IMAGE_WIDTH/HEIGHT`：封面生成布局在提交中从 `800×1200` 迁移为 `840×1040`，一个测试直接断言旧尺寸，另一个测试断言由旧尺寸派生的 `2:3` 宽高比；两者应合并为同一个画布规格迁移根因。
6. `OutfitComposeRequest.layout`：Pydantic 允许值从 `auto|vertical|grid` 迁移为 `auto|left-right`，旧参数化测试仍把 `vertical/grid` 当作有效值；同一提交还更新了布局路由列表并删除旧排列方法，但枚举契约迁移应与私有符号删除分别归因。
7. `AnalyticsService.sync_signal_to_recommend`：实现新增 `await AsyncSession.execute(...)` 查询后，旧测试只把数据库会话声明为 `AsyncMock`，没有把 `execute.return_value` 配置为同步 SQLAlchemy Result；`scalar_one_or_none()` 因而返回未等待的子协程并触发 `RuntimeWarning`/`PytestUnraisableExceptionWarning`。诊断应指出测试 fixture 的异步边界错误，并区分生产代码真正漏写 `await` 的反例。
8. `TestGetDb.test_get_db_yields_session`：测试调用 `get_db()` 得到异步生成器后，把 `gen.__anext__()` 返回的 awaitable 当作 session 使用，且没有关闭生成器，触发 `coroutine method 'asend' of 'get_db' was never awaited`。诊断应建议使用 `session = await anext(gen)` 并在 `finally` 中 `await gen.aclose()`，同时区分生产异步生成器自身清理逻辑错误。

契约迁移类成功输出必须包含迁移类型、旧契约、当前契约、当前一致性证据和迁移提交 SHA；不得仅输出“Git 中出现过两个值”。异步 Mock 边界属于运行时 fixture 契约漂移，输出改为包含异步入口、返回对象同步 API、Mock 配置缺口和 warning 来源；异步生成器生命周期输出必须包含未等待操作、缺失的关闭路径和生产清理结构。两类异步运行时结论均不强制要求迁移提交。

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
- Create: `tests/fixtures/real_project_triage/related_config_migration/app/config.py`
- Create: `tests/fixtures/real_project_triage/related_config_migration/app/composition.py`
- Create: `tests/fixtures/real_project_triage/related_config_migration/case.py`
- Create: `tests/fixtures/real_project_triage/enum_contract_migration/app/schema.py`
- Create: `tests/fixtures/real_project_triage/enum_contract_migration/app/router.py`
- Create: `tests/fixtures/real_project_triage/enum_contract_migration/case.py`
- Create: `tests/fixtures/real_project_triage/async_mock_result_contract/app/service.py`
- Create: `tests/fixtures/real_project_triage/async_mock_result_contract/case.py`
- Create: `tests/fixtures/real_project_triage/async_generator_lifecycle/app/dependency.py`
- Create: `tests/fixtures/real_project_triage/async_generator_lifecycle/case.py`
- Modify: `tests/test_real_project_fixtures.py`

**Steps:**
1. 写一个 `10 → settings.VALUE → 120` fixture，确认当前 v0.5.1 返回 `INCONCLUSIVE`。
2. 写一个 `id=1 → ORM str + response str` fixture，确认当前 v0.5.1 返回 `INCONCLUSIVE`。
3. 写一个 ORM/Schema 同时新增可选字段、旧 `MagicMock(spec=...)` 未赋值的 fixture，确认 Pydantic 收到 `MagicMock` 而不是 `None`。
4. 写一个成对尺寸配置从 `800×1200` 迁移到 `840×1040` 的 fixture，同时包含直接尺寸断言和派生宽高比断言。
5. 写一个 Pydantic `Field(pattern=...)` 允许值集合发生变化的 fixture，包含旧有效值、当前有效值和路由公开列表。
6. 写一个 `AsyncMock` 数据库会话 fixture：`execute` 保持异步，但未显式配置的 `execute.return_value.scalar_one_or_none()` 被错误创建为子 `AsyncMock`，复现未等待协程警告；同时写一个生产代码漏写 `await db.execute(...)` 的反例。
7. 写一个异步生成器生命周期 fixture：测试调用 `gen.__anext__()` 却不等待，也不在 `finally` 中执行 `gen.aclose()`；同时写一个测试正确消费、但生产生成器清理阶段失败的反例。
8. 六个历史迁移 fixture 使用真实临时 Git 提交表示迁移前后状态，不 mock Git 输出；两个异步运行时 fixture 不伪造无关 Git 历史。
9. 运行 `poetry run pytest tests/test_real_project_fixtures.py -q`，保留预期失败作为红灯。
10. 提交 fixtures：`test: add contract migration triage fixtures`。

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
6. 识别由同组配置字段构成的简单算术表达式，例如 `WIDTH / HEIGHT == approx(ratio)`，保留字段依赖集合与期望派生值。
7. 识别参数化循环或常量列表向 Pydantic 字段传入的枚举值，并从 ValidationError 提取 `string_pattern_mismatch`、字段名与失败输入值。
8. 解析 `RuntimeWarning: coroutine ... was never awaited` 及其外层 `PytestUnraisableExceptionWarning`，保留协程来源、触发测试和可用分配位置；不能仅凭 warning 文本判定测试缺陷。
9. AST 追踪 `AsyncMock` fixture、被 `await` 的方法及其返回对象上的同步调用链，例如 `result = await db.execute(...)` 后的 `result.scalar_one_or_none()`。
10. 识别异步生成器的局部生命周期：`gen = async_generator()`、未等待的 `gen.__anext__()`/`anext(gen)`、是否存在 `try/finally` 和 `await gen.aclose()`；解析 `coroutine method 'asend' ... was never awaited` 以及异常对象为 `async_generator` 的 unraisable warning。
11. 对动态表达式、跨函数保存的生成器、多个候选目标和无法解析的字符串返回无证据，不猜测。
12. 运行 `poetry run pytest tests/test_contract_migration_analyzer.py -q`。
13. 提交：`feat: extract contract mismatches from failing tests`。

### Task 3: 建立当前契约一致性证据

**Files:**
- Create: `core/analyzers/current_contract.py`
- Test: `tests/test_current_contract.py`

**Steps:**
1. 解析 `Field(default=settings.NAME)`、类常量赋值和简单模块级配置引用。
2. 解析 `Mapped[str]`、`mapped_column(String(...))` 和 Pydantic `field: str`。
3. 只有独立来源一致时才生成 `CurrentContractEvidence`：配置迁移至少需要实现引用和配置默认值；类型迁移至少需要 ORM 与响应 Schema 类型一致。
4. 对新增可选字段，验证 ORM `Mapped[Optional[T]]`/`nullable=True` 与 Pydantic `Optional[T] = None` 一致，并确认测试 fixture 未显式设置该字段。
5. 对关联配置迁移，验证当前配置值、直接消费这些配置的实现常量或画布初始化，以及由当前值静态计算出的派生比例一致。
6. 对枚举迁移，将 Pydantic `pattern` 或 `Literal[...]` 规范化为允许值集合，并验证路由公开选项是该集合的子集且包含所有非自动布局值。
7. 对异步 Mock 边界，仅依据静态调用方式、类型注解或受支持 API 契约表确认：`AsyncSession.execute` 必须被等待，而 SQLAlchemy Result 的 `scalar_one_or_none`、`scalars`、`all` 等读取方法是同步调用；不 import 或执行目标项目及第三方模块。
8. 同一字段出现类型冲突、可空性冲突、枚举来源冲突、环境覆盖值或无法静态求值时标记 `conflict`。
9. 禁止 import 或执行目标项目模块，避免导入副作用。
10. 运行 `poetry run pytest tests/test_current_contract.py -q`。
11. 提交：`feat: validate current static contract consistency`。

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
6. 关联配置迁移以字段集合生成 root-cause key；直接值断言和依赖相同字段集合的派生表达式必须合并为一个失败簇。
7. 关联配置迁移只有在 Git 同一提交修改整组值、当前多个实现位置消费新值且旧文档或测试自迁移前沿用至今时，才可判为 `TEST_DEFECT / HIGH`，并额外报告文档漂移；如果迁移后的新文档仍明确声明旧契约，则保持 `INCONCLUSIVE` 并请求产品确认。
8. 枚举迁移只有在 Git 同一提交删除旧允许值并增加当前允许值、Schema 与路由当前一致时，才可判为 `TEST_DEFECT / HIGH`；测试仍使用已删除私有方法时继续形成独立的符号删除簇，不按提交 SHA 粗暴合并。
9. 异步 Mock fixture 漂移只有在 traceback 确认未等待协程来自 Mock、生产代码正确等待异步入口、返回对象调用的是已确认的同步 Result API，且测试未显式配置正确返回对象时，才可判为 `TEST_DEFECT / HIGH`。建议使用 `MagicMock` 配置 Result，但不得自动修改测试。
10. 如果生产代码漏写 `await`、返回 API 的同步/异步契约无法确认、warning 缺少来源，或测试已经配置了正确 Result 对象，则不得判为测试缺陷，保持 `INCONCLUSIVE` 或交由现有实现缺陷规则处理。
11. 异步生成器生命周期只有在 traceback 指向未等待的 `asend`/`anext`、测试 AST 确认缺少 `await` 或未关闭生成器、生产生成器定义本身具有正常 `yield`/`finally` 清理结构时，才可判为 `TEST_DEFECT / HIGH`；建议使用 `await anext(gen)` 与 `finally: await gen.aclose()`，不得自动修改测试。
12. 如果测试正确消费并关闭生成器，但生产生成器的 `finally`、回滚或关闭逻辑报错，则不得归为测试缺陷；保持 `INCONCLUSIVE` 或交由实现缺陷规则处理。
13. 满足全部条件时输出 `TEST_DEFECT / HIGH`；缺少 Git 时为 `INCONCLUSIVE / LOW`；当前契约冲突时为 `INCONCLUSIVE / LOW` 并请求确认。两个异步运行时边界案例不要求存在 Git 迁移提交，但必须满足各自的 traceback、静态调用和契约证据门槛。
14. 保持 `INFRA_DEFECT`、`FLAKY`、collection error 和已存在的符号删除优先级不回归。
15. 运行 `poetry run pytest tests/test_triage_contract_migration.py tests/test_triage_workflow.py -q`。
16. 提交：`feat: attribute confirmed contract migrations`。

### Task 6: CLI 展示和审计

**Files:**
- Modify: `cli/commands/triage.py`
- Modify: `core/repositories/triage.py`
- Test: `tests/test_cli_triage.py`
- Modify: `tests/test_triage_repository.py`

**Steps:**
1. 不新增授权参数，继续复用 `--allow-git-history` 和仓库级 permission。
2. 输出 `迁移类型`、`旧契约`、`当前契约`、`当前一致性`、`migration_commit`。
3. 对异步运行时 fixture 漂移改为输出 `异步边界`、`生命周期缺口`、`warning 来源` 和修复建议，不显示不存在的 `migration_commit`。
4. JSON 记录保存结构化证据，不保存仓库绝对路径或完整 diff。
5. 未授权输出明确说明“未读取契约迁移历史”，不能暗示已经检查 Git；不需要历史证据的异步运行时结论应明确标注其证据来源。
6. 运行 `poetry run pytest tests/test_cli_triage.py tests/test_triage_repository.py -q`。
7. 提交：`feat: report contract migration evidence`。

### Task 7: v0.5.2 发布验收

**Files:**
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `pyproject.toml`
- Modify: `tests/test_cli_end_to_end.py`

**Steps:**
1. 将版本提升到 `0.5.2`，记录仍不会自动修改目标项目。
2. 用八个真实 fixture 验证 `TEST_DEFECT / HIGH` 和符合契约边界的根因聚类。
3. 用反例验证实现与 Schema 冲突时不能高置信度归因。
4. 运行 `poetry run pytest -q`，预期全部通过。
5. 运行 `poetry build` 与 `git diff --check`。
6. 在干净 Python 3.13 环境安装 wheel，运行八个 fixture smoke。
7. 在 `fitstyle-backend` 上只读复验八个真实案例。
8. 提交：`release: prepare test-assistant v0.5.2`。

## v0.5.2 完成标准

- 八个真实案例无需人工 Git 命令即可得到正确归因；两个异步运行时案例无需 Git 历史，但必须满足各自专门的证据门槛。
- 契约迁移类高置信度结论至少包含两个当前契约来源和一个历史迁移提交；异步 Mock fixture 漂移必须包含 traceback、静态调用和受支持 API 契约三类证据；异步生成器生命周期必须包含 traceback、测试生命周期和生产生成器清理结构三类证据。
- 未授权或证据不完整时保持 `INCONCLUSIVE`。
- 不新增网络访问、Git 修改、目标代码修改或数据库访问。
