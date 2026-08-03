# Coverage and Code Quality v0.6.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为目标 Python/pytest 项目提供可审计的测试覆盖率、未覆盖源码符号和实现代码质量报告，同时保持与失败分诊相互独立。

**Architecture:** 新增只读 `audit` 工作流，coverage adapter 通过 pytest-cov 生成临时 JSON 并映射到源码符号，quality adapter 消费 Ruff 与 mypy 的结构化输出。统一的 `AuditResult` 只聚合事实、阈值和工具降级状态；`triage` 继续回答“为什么测试失败”，`audit` 回答“哪些实现缺少验证或存在静态质量问题”。所有正式记录原子写入 `.autotest/audits/`，默认不自动修复。

**Tech Stack:** Python 3.13、pytest、pytest-cov/coverage.py、Ruff JSON、mypy JSON 或稳定文本适配器、AST、Click、版本化 JSON。

---

## 产品边界与命令形态

推荐新增：

```bash
test-assistant audit --path .
test-assistant audit --path . --coverage
test-assistant audit --path . --quality
test-assistant audit --path . --coverage --quality
test-assistant audit --path . --changed-only
```

`audit` 默认等价于 `--coverage --quality`。它不替代 `triage`、`run` 或 `verify`，不自动安装工具，不联网，不执行 Ruff `--fix`，不修改源码或测试。目标项目未安装某个 adapter 时，其他 adapter 仍可完成并明确报告降级。

## 指标原则

- 总覆盖率只作摘要，首要输出是未覆盖的文件、函数、方法和分支。
- 不把高覆盖率等同于实现正确，也不生成单一“代码质量总分”。
- Ruff/mypy 结果按工具规则、严重性、源码位置展示，不擅自改写规则等级。
- 质量门禁阈值必须来自目标项目配置或显式 CLI 参数，不使用隐藏默认值。
- 生成的新测试仍走既有 TestSpec 审批和候选门禁，`audit` 本身不写正式测试。

### Task 1: 定义 Audit 领域模型与版本化仓库

**Files:**
- Create: `core/models/audit.py`
- Modify: `core/models/__init__.py`
- Create: `core/repositories/audit.py`
- Modify: `core/repositories/__init__.py`
- Test: `tests/test_audit_models.py`
- Test: `tests/test_audit_repository.py`

**Steps:**
1. 定义 `CoverageSummary`、`SymbolCoverage`、`QualityFinding`、`ToolStatus` 和 `AuditResult`。
2. 明确 statement、branch、function/method 覆盖字段，不以浮点数作为唯一事实，保留 covered/total。
3. 保存 schema version、命令、工具版本、源码摘要、阈值和降级原因。
4. 对绝对路径、密钥和大输出复用现有脱敏/截断策略。
5. 原子写入 `.autotest/audits/<run-id>.json` 与 `latest.json`。
6. 运行 `poetry run pytest tests/test_audit_models.py tests/test_audit_repository.py -q`。
7. 提交：`feat: add versioned audit result model`。

### Task 2: 安全执行覆盖率采集

**Files:**
- Create: `core/executors/coverage_executor.py`
- Modify: `core/executors/__init__.py`
- Test: `tests/test_coverage_executor.py`

**Steps:**
1. 使用参数数组和 `shell=False` 调用目标 Python：`python -m pytest --cov=<source> --cov-branch --cov-report=json:<temp>`。
2. 临时覆盖率文件写入受控临时目录，不写目标项目正式文件。
3. 支持 suite、test path 和精确 node；复用现有路径边界与超时。
4. 区分测试失败、pytest-cov 缺失、coverage JSON 损坏、超时和 runner error。
5. 测试命令注入、超大 JSON、绝对路径脱敏和临时文件清理。
6. 运行 `poetry run pytest tests/test_coverage_executor.py -q`。
7. 提交：`feat: collect pytest coverage safely`。

### Task 3: 将行与分支覆盖映射到源码符号

**Files:**
- Create: `core/analyzers/coverage.py`
- Test: `tests/test_coverage_analyzer.py`

**Steps:**
1. 复用 `core/analyzers/source.py` 的 Python AST 符号边界。
2. 将 executed/missing lines 和 branches 映射到 module、class、function、async function。
3. 对装饰器、多行签名、嵌套函数、property 和无法执行行编写 fixtures。
4. 输出完全未覆盖、部分覆盖和完全覆盖符号，并区分语句与分支缺口。
5. 忽略 `tests/`、迁移脚本和生成文件必须由配置决定，不能硬编码业务目录。
6. 运行 `poetry run pytest tests/test_coverage_analyzer.py -q`。
7. 提交：`feat: map coverage gaps to python symbols`。

### Task 4: 关联已有测试与未覆盖符号

**Files:**
- Create: `core/analyzers/coverage_impact.py`
- Modify: `core/analyzers/impact.py`
- Test: `tests/test_coverage_impact.py`

**Steps:**
1. 复用 import/call 关系建立“候选已有测试”，不声称静态引用等于真实覆盖。
2. 对零候选测试的公共符号标记 `no_known_test`。
3. 对有测试但分支未覆盖的符号标记具体 missing branches。
4. `--changed-only` 使用 snapshot/Git diff 限定到新增或修改符号；Git 未授权时允许基于 snapshot 工作。
5. 输出补测优先级的可解释因素：变更、公共 API、分支缺口、现有测试数量；不生成黑盒分数。
6. 运行 `poetry run pytest tests/test_coverage_impact.py -q`。
7. 提交：`feat: relate coverage gaps to existing tests`。

### Task 5: Ruff 只读质量适配器

**Files:**
- Create: `core/executors/ruff_executor.py`
- Create: `core/analyzers/quality.py`
- Test: `tests/test_ruff_executor.py`
- Test: `tests/test_quality_analyzer.py`

**Steps:**
1. 检测目标环境中的 Ruff；缺失时返回 `unavailable`，不安装、不联网。
2. 只运行 `ruff check --output-format json`，明确禁止 `--fix` 和不受控额外参数。
3. 解析 rule code、message、location、fix availability；不执行建议修复。
4. 尊重目标项目 `pyproject.toml`/`ruff.toml`，记录实际配置来源摘要。
5. 覆盖损坏 JSON、未知规则、超时和工具版本差异。
6. 运行 `poetry run pytest tests/test_ruff_executor.py tests/test_quality_analyzer.py -q`。
7. 提交：`feat: add read-only Ruff quality adapter`。

### Task 6: mypy 只读类型质量适配器

**Files:**
- Create: `core/executors/mypy_executor.py`
- Modify: `core/analyzers/quality.py`
- Test: `tests/test_mypy_executor.py`

**Steps:**
1. 检测 mypy 可用性并读取目标项目配置，不自动安装类型 stub。
2. 优先使用当前 mypy 支持的结构化输出；否则用隔离、版本锁定的文本解析器。
3. 解析 error code、message、path、line/column，区分工具错误与代码 finding。
4. 不把第三方缺失 stub 自动归为产品实现错误，单独标记 dependency/configuration。
5. 运行 `poetry run pytest tests/test_mypy_executor.py -q`。
6. 提交：`feat: add read-only mypy quality adapter`。

### Task 7: Audit 工作流与门禁语义

**Files:**
- Create: `core/workflows/audit.py`
- Modify: `core/workflows/__init__.py`
- Test: `tests/test_audit_workflow.py`

**Steps:**
1. 并列运行已启用 adapter；单个 adapter 不可用不丢失其他结果。
2. 明确状态：`passed`、`threshold_failed`、`tests_failed`、`partial`、`infra_error`。
3. coverage 阈值支持 statement 和 branch；质量阈值支持按 Ruff code/mypy error count。
4. 无显式阈值时只报告，不因低覆盖率返回失败。
5. 测试失败时仍保存可用覆盖率，但不得把不完整运行误称为完整覆盖结果。
6. 运行 `poetry run pytest tests/test_audit_workflow.py -q`。
7. 提交：`feat: orchestrate coverage and quality audits`。

### Task 8: 新增 `audit` CLI

**Files:**
- Create: `cli/commands/audit.py`
- Modify: `cli/commands/__init__.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_audit.py`

**Steps:**
1. 添加 `--coverage/--no-coverage`、`--quality/--no-quality`、`--changed-only`、测试范围和显式阈值参数。
2. 输出总体执行状态、覆盖率分数的分子/分母、前 N 个未覆盖符号和质量 findings。
3. 为完整结果提供 `.autotest/audits/<run-id>.json` 路径。
4. 退出码：`0` 完成且满足显式门禁；`1` 门禁或测试失败；`2` 参数/全部 adapter 不可用/基础设施错误。
5. 验证 `audit` 不调用 LLM、不写源码、不修改 Git。
6. 运行 `poetry run pytest tests/test_cli_audit.py -q`。
7. 提交：`feat: add coverage and quality audit command`。

### Task 9: 报告与补测规划衔接

**Files:**
- Modify: `core/reporters.py`
- Modify: `cli/commands/report.py`
- Modify: `cli/commands/plan.py`
- Test: `tests/test_audit_report.py`
- Test: `tests/test_cli_plan.py`

**Steps:**
1. Markdown 报告加入 coverage gaps、Ruff/mypy findings 和 adapter 降级信息。
2. 允许用户从一个明确选择的未覆盖符号创建 proposed TestSpec。
3. 生成前仍要求现有 propose/approve/candidate/diff 门禁，不允许 audit 自动写正式测试。
4. 报告中区分“未覆盖”“静态 finding”“已确认 defect”，避免概念混淆。
5. 运行 `poetry run pytest tests/test_audit_report.py tests/test_cli_plan.py -q`。
6. 提交：`feat: connect audit findings to reviewed test plans`。

### Task 10: v0.6.0 真实项目验收与发布

**Files:**
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `pyproject.toml`
- Modify: `tests/test_cli_end_to_end.py`

**Steps:**
1. 将版本提升到 `0.6.0`，文档解释 triage 与 audit 的职责边界。
2. 在小型 fixture 上验证行/分支/符号映射和显式门禁。
3. 在缺 Ruff、缺 mypy、缺 pytest-cov 的环境分别验证 partial/degraded 输出。
4. 在 `fitstyle-backend` 上运行 coverage-only audit，记录基线但不立即设置全局阈值。
5. 再运行 quality-only audit，先确认目标项目现有 Ruff/mypy 配置，避免引入任意规则。
6. 验证 audit 前后产品源码、测试、snapshot 和 Git 状态不变。
7. 运行 `poetry run pytest -q`、`poetry build`、`git diff --check`。
8. 在干净 Python 3.13 环境安装 wheel 并完成 CLI smoke。
9. 提交：`release: prepare test-assistant v0.6.0`。

## v0.6.0 完成标准

- 能回答“哪些源码符号和分支没有被测试执行”，而不只给总百分比。
- 能分别展示 Ruff 与 mypy 的真实 findings 和工具降级状态。
- 没有显式阈值时只报告，不制造失败；有阈值时退出码稳定可用于 CI。
- audit 不自动修复、不联网、不修改 Git，并能在部分工具缺失时产出其余可信结果。
- 未覆盖符号可进入人工审批的 TestSpec 流程，但不能绕过现有候选门禁。

