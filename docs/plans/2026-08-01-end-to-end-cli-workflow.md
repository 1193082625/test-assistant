# End-to-End CLI Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Python/pytest 项目通过 CLI 完成 TestSpec 提议、人工审批、候选生成、精确验证、失败归因和诊断持久化。

**Architecture:** `plan propose` 复用源码分析、契约提取和 Planner，只负责产生待审批 TestSpec。新增 `core.workflows.verification` 编排确定性门禁、三次精确 node 执行、证据归因和 DiagnosisRepository；`verify` CLI 只负责参数、文本输出和退出码。

**Tech Stack:** Python 3.13、Click、pytest、现有 JSON repositories 和 diagnosticians。

---

### Task 1: TestSpec proposal CLI

**Files:**
- Modify: `cli/commands/plan.py`
- Test: `tests/test_cli_plan_propose.py`

1. 写 fake LLM CLI 测试，验证目标符号、契约证据、保存结果和错误边界。
2. 运行测试确认缺少 `plan propose`。
3. 实现源码路径解析、符号选择、可测性判断、契约筛选、Planner 调用和 repository 保存。
4. 运行 plan 相关测试。

### Task 2: Deterministic verification workflow

**Files:**
- Create: `core/workflows/verification.py`
- Modify: `core/workflows/__init__.py`
- Test: `tests/test_verification_workflow.py`

1. 覆盖三次通过、稳定失败、Flaky、测试门禁失败和 Runner 故障。
2. 实现精确 node 重跑、归因、Git/依赖摘要和诊断原子保存。
3. 确认成功不写失败诊断，失败保留完整记录。

### Task 3: Verify CLI

**Files:**
- Create: `cli/commands/verify.py`
- Modify: `cli/main.py`
- Test: `tests/test_cli_verify.py`

1. 验证 approved TestSpec、测试 node 和 source path 参数。
2. 重新执行静态、collect-only 和 Runner 健康门禁。
3. 调用 verification workflow，输出健康或诊断摘要、复现命令与记录路径。
4. 健康返回 0，所有未解决失败返回 1。

### Task 4: End-to-end fixture and documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-07-27-python-cli-trusted-loop-roadmap.md`
- Test: `tests/test_cli_end_to_end.py`

1. 用临时 Python/pytest 项目演练 propose 后的确定性审批至 verify 链路。
2. 更新真实项目命令顺序和当前限制。
3. 运行 CLI 相关测试、全量测试、构建和 `git diff --check`。

### Architectural decisions

- Web 不进入本阶段；先稳定 CLI 领域接口和持久化 schema。
- `verify` 不调用 LLM，避免相同项目因模型输出产生不同诊断。
- 只执行用户明确指定的 pytest node，不扩大到任意测试集。
- 正式测试门禁不要求测试通过，否则无法发现已有产品缺陷；只要求源码结构、收集和 Runner 健康。
- 没有已批准强契约时，稳定失败保持 `INCONCLUSIVE`。
- 不自动修改产品源码、正式测试或 TestSpec 审批状态。
