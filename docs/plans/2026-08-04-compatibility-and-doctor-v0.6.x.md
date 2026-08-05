# Compatibility and Doctor v0.6.x Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让用户能确认 test-assistant 实际运行环境，并用自动兼容矩阵证明受支持平台、Python、pytest 和路径形态。

**Architecture:** 新增只读 `doctor` 命令聚合环境事实和 adapter 可用性；CI 使用最小矩阵验证安装包和关键 fixture。兼容性失败必须报告具体维度，不自动安装或修改目标环境。

**Tech Stack:** Python 3.13+、Click、pytest、GitHub Actions、JSON。

**当前进度（2026-08-05）：** `v0.6.1` 的环境模型、安全探测器、只读工作流、CLI、JSON/退出码和真实子进程验收已完成；发布构建验证尚待执行。跨平台 wheel 与特殊路径矩阵仍属于 `v0.6.2`，未提前声明支持。

---

## 范围

- `v0.6.1`：`doctor`、环境 JSON、错误退出码；
- `v0.6.2`：Ubuntu/macOS wheel 矩阵与特殊路径；
- 后续 `v0.6.x`：在 Python 3.14/新 pytest 可用后显式认证，不提前宣称支持。

### Task 1: 定义环境诊断模型（v0.6.1 已完成）

**Files:** Create `core/models/environment.py`; modify `core/models/__init__.py`; test `tests/test_environment_model.py`。

1. 先写失败测试，固定工具版本、Python、平台、可执行路径、目标 pytest/Git 和 adapter 状态。
2. 实现版本化、可序列化模型；绝对路径展示和持久化采用不同脱敏策略。
3. 运行 `poetry run pytest tests/test_environment_model.py -q`。
4. 提交 `feat: add environment diagnosis model`。

### Task 2: 实现只读 doctor 工作流与 CLI（v0.6.1 已完成）

**Files:** Create `core/workflows/doctor.py`, `cli/commands/doctor.py`; modify `core/workflows/__init__.py`, `cli/main.py`; test `tests/test_doctor_workflow.py`, `tests/test_cli_doctor.py`。

1. 覆盖 pytest/Git/coverage/Ruff/mypy 可用、缺失、超时和损坏版本输出。
2. 实现 `test-assistant doctor --path . [--json]`，禁止安装依赖和联网。
3. 退出码：健康或部分可选工具缺失为 `0`；核心 Python/pytest 不兼容为 `1`；参数/基础设施错误为 `2`。
4. 运行相关测试并提交 `feat: add read-only doctor command`。

### Task 3: 建立兼容 CI 矩阵（v0.6.2）

**Files:** Modify `.github/workflows/ci.yml`; create `tests/test_installed_cli_smoke.py`（如 shell smoke 无法提供足够断言）。

1. Ubuntu 与 macOS 分别从 wheel 安装，不从源码目录导入。
2. 运行 `--version`、`doctor`、`triage --help` 和一个最小真实 fixture。
3. 新 Python/pytest 版本先作为允许失败的探测 job，通过后才能进入支持矩阵。
4. 提交 `ci: verify supported runtime matrix`。

### Task 4: 路径与环境边界（v0.6.2）

**Files:** Test `tests/test_path_compatibility.py`, `tests/test_cli_end_to_end.py`；按失败点修改路径组件。

覆盖中文、空格、长路径、符号链接、非 Git 仓库、只读源码目录和 Windows 绝对路径拒绝逻辑。真实 Windows 支持在加入 Windows runner 并通过进程终止测试前不得声明。

## 完成标准

- 用户能一条命令确认版本、解释器、pytest、Git 和 audit adapters；
- 支持矩阵中的每个平台均从 wheel 完成真实 CLI smoke；
- 文档明确列出已认证、探测中和不支持环境；
- 特殊路径不会导致越界读取、错误写入或命令注入。
