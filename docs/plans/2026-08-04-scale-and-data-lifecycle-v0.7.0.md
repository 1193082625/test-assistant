# Scale and Data Lifecycle v0.7.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 test-assistant 在大型 Python 仓库中具有可重复的时间/内存基线，并安全管理跨版本 `.autotest` 数据和安装依赖。

**Architecture:** 使用确定性合成 fixture 建立基准，分别测量扫描、Git 分析、pytest 解析和持久化；存储层增加共享 schema 迁移与显式清理工作流；将 LLM 和 quality 工具改为可选依赖，保持基础 triage 安装最小化。

**Tech Stack:** Python 3.13+、pytest、resource/tracemalloc、JSON schema migration、Poetry extras。

---

### Task 1: 建立可重复的大型 fixture 生成器

**Files:** Create `tests/performance/fixture_factory.py`, `tests/performance/test_fixture_factory.py`。

生成固定 seed、模块数、符号数、测试数和 Git 提交数的临时项目；不得提交巨量生成文件。验证两次生成的摘要一致。

### Task 2: 建立性能与内存基线

**Files:** Create `tests/performance/test_analysis_benchmarks.py`, `scripts/run_benchmarks.py`, `docs/performance-baseline.md`。

分别记录源码扫描、影响分析、Git 历史、pytest JSONL 解析和记录保存的 wall time、峰值 RSS/追踪内存及输入规模。CI 只做宽松回归门，精确基线在固定环境运行；不得用易波动的单次毫秒阈值阻塞发布。

### Task 3: 优化前先建立性能归因

**Files:** 根据 Task 2 证据修改 `core/analyzers/`、`core/executors/` 或 `core/repositories/`；test `tests/performance/`。

只优化超过预算的路径；优先目录剪枝、流式解析、受控缓存和避免重复 AST。每项优化必须保存优化前后相同输入证据。

### Task 4: 统一 schema 迁移与恢复

**Files:** Create `core/repositories/schema.py`; modify各 JSON repository；test `tests/test_repository_migrations.py`。

1. 固定 v1→v2 fixture 和未知未来版本行为。
2. 读取时迁移到内存；只有显式命令才改写历史文件。
3. `latest.json` 损坏时从不可变历史中恢复最近有效记录。
4. 迁移失败不得覆盖原文件。

### Task 5: 增加数据保留与显式清理

**Files:** Create `core/workflows/clean.py`, `cli/commands/clean.py`; test `tests/test_clean_workflow.py`, `tests/test_cli_clean.py`。

实现 `test-assistant clean --dry-run` 和显式确认清理；按类型、年龄和容量展示候选。默认保留失败诊断和用户候选，不自动删除，不跟随越界符号链接。

### Task 6: 拆分可选依赖

**Files:** Modify `pyproject.toml`, import boundaries and packaging tests。

基础安装提供确定性 CLI/triage；`[llm]` 提供生成能力；`[quality]` 提供 audit adapters。缺少 extra 时返回结构化 unavailable，不在运行时安装。

### Task 7: 发布验收

运行全量测试、性能基线、`compileall`、构建和三种 wheel 安装（base、llm、quality）。在大型 fixture 上验证 Ctrl-C、临时文件清理和磁盘增长上限。

## 完成标准

- 指定规模下的时间和峰值内存具有可复现基线与合理回归门；
- 数据可跨已支持 schema 读取，损坏 latest 可恢复且原历史不丢失；
- 清理始终先预览并受路径边界保护；
- 只使用 triage 的用户无需安装 LLM 或质量工具依赖。

