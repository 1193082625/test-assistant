# Local Git Evidence v0.5.1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在项目级明确授权下，为 pytest triage 增加本地只读 Git 删除证据、结构化共同根因聚类和高置信度旧测试归因。

**Architecture:** 新增独立 permission repository 和只读 Git evidence provider；Python AST 分析器从失败测试提取缺失符号或 patch 目标，工作流以 root-cause key 聚类并消费 Git 证据。CLI 只解析授权参数和展示是否启用，所有失败均安全降级且不访问网络。

**Tech Stack:** Python 3.13、Click、pytest、AST、subprocess `shell=False`、版本化 JSON repository。

---

### Task 1: 项目级 Git 只读授权

**Files:**
- Create: `core/repositories/permissions.py`
- Modify: `core/repositories/__init__.py`
- Test: `tests/test_git_permission_repository.py`

**Steps:**
1. 写失败测试覆盖首次未授权、授权持久化、仓库身份变化、损坏 JSON、原子写入和路径脱敏。
2. 用 `git rev-parse --show-toplevel/--git-common-dir` 生成仓库身份摘要，不保存绝对路径。
3. 保存 `local_read_only` scope、授权时间和 identity digest。
4. 运行 `poetry run pytest tests/test_git_permission_repository.py -q`。

### Task 2: 白名单 Git 历史证据

**Files:**
- Create: `core/analyzers/git_history.py`
- Modify: `core/analyzers/__init__.py`
- Test: `tests/test_git_history.py`

**Steps:**
1. 写失败测试锁定命令参数、`shell=False`、超时、输出限制、非仓库与浅历史降级。
2. 实现 `git log -S <symbol> --format=%H -- <path>` 与对应 `git show` 最小 diff。
3. 只输出 SHA、added/deleted 状态和脱敏摘要。
4. 禁止调用白名单之外的 Git 子命令。

### Task 3: 测试结构根因提取与聚类

**Files:**
- Create: `core/analyzers/test_failure.py`
- Modify: `core/diagnosticians/clustering.py`
- Modify: `core/models/triage.py`
- Test: `tests/test_failure_root_causes.py`
- Test: `tests/test_triage_clustering.py`

**Steps:**
1. 用旧 patch 和已删除异步方法 fixture 写失败测试。
2. AST 提取 patch target、`hasattr` 目标、缺失方法调用和源码字符串断言。
3. 为 `PytestIssue` 关联可选 root-cause key；同 key 优先合并。
4. 无结构化目标时保持 v0.5.0 fingerprint 兼容。

### Task 4: 自动证据收集与归因

**Files:**
- Modify: `core/workflows/triage.py`
- Modify: `core/workflows/__init__.py`
- Test: `tests/test_triage_git_attribution.py`
- Test: `tests/test_triage_workflow.py`

**Steps:**
1. 新增 evidence collector，从失败 node 找测试文件和候选源码模块。
2. 当前目标不存在且 Git 确认删除时构造 `TriageEvidence(removal_confirmed=True)`。
3. 相同根因簇只复跑一个代表 node；证据闭合时 `TEST_DEFECT/HIGH`，否则 `INCONCLUSIVE`。
4. 确认契约冲突、Flaky 和 Runner 优先级不回归。

### Task 5: CLI 授权与审计输出

**Files:**
- Modify: `cli/commands/triage.py`
- Modify: `core/repositories/triage.py`
- Test: `tests/test_cli_triage.py`
- Test: `tests/test_triage_repository.py`

**Steps:**
1. 添加互斥 `--allow-git-history` / `--no-git-history`。
2. 首次 allow 保存项目授权；无参数时只复用有效授权。
3. 输出本地只读/无网络/无 Git 修改边界和降级原因。
4. triage 记录保存授权状态与最小证据引用。

### Task 6: v0.5.1 发布验收

**Files:**
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `pyproject.toml`
- Test: `tests/test_cli_end_to_end.py`

**Steps:**
1. 在临时 Git fixture 端到端验证授权、删除证据、单簇和 `TEST_DEFECT/HIGH`。
2. 验证未授权完全不读历史且仍输出 `INCONCLUSIVE`。
3. 验证源码、测试、snapshot 和 Git 状态不变。
4. 将版本提升至 `0.5.1` 并更新权限文档。
5. 运行 `poetry run pytest -q`、`poetry build`、`git diff --check`。
6. 在干净 Python 3.13 环境安装 wheel 并运行 fixture smoke。
