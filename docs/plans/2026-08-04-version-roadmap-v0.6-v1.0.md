# test-assistant v0.6～v1.0 统一版本路线图

> 状态：当前权威版本规划  
> 基线：`v0.6.2` 已完成并通过 Ubuntu/macOS 同一 wheel 兼容矩阵
> 制定日期：2026-08-04

## 1. 规划原则

版本按用户可验证的能力闭环升级，不按开发时长升级。每个版本必须具有自动化测试、安装产物 smoke、文档和明确降级行为；未通过验收门的能力不得标记为完成。

`triage`、`audit` 和未来服务化能力保持边界清晰：

- `triage` 回答“已有 pytest 为什么失败”；
- `audit` 回答“哪些实现缺少验证或存在静态质量问题”；
- 两者默认只读、不联网、不修改 Git，不以自动修复制造通过。

## 2. 当前基线

`v0.6.1` 已实现只读 `doctor`、schema v1 环境 JSON 和稳定退出码，并完成 Python 3.13 干净 wheel 安装以及 `fitstyle-backend` Doctor/coverage Audit 只读验收。

`v0.6.2` 已通过同一 wheel 的 Ubuntu/macOS Python 3.13 消费矩阵，并交付特殊路径系统测试、Python 3.14 非阻塞探测和自动兼容表。`v0.6.2` Tag 已发布；Windows 与 Python 3.14 仍不在支持范围。

下一阶段为 `v0.7.0`：建立大型仓库性能/内存基线、统一 `.autotest` schema 迁移与恢复、显式数据清理，以及基础/LLM/quality 可选依赖拆分。

## 3. 版本边界

| 版本 | 定位 | 核心交付 | 明确不做 |
| --- | --- | --- | --- |
| `v0.6.0` | 只读质量审计版 | coverage、Ruff、mypy、`audit`、`--version`、中断清理、wheel 自动 smoke | 自动修复、安全扫描、性能优化 |
| `v0.6.1` | 环境诊断版 | 只读 `doctor`、schema v1 JSON、核心/降级状态和稳定退出码 | 跨平台矩阵、Python 3.14、自动安装或修复环境 |
| `v0.6.2` | 兼容性证据版 | Ubuntu/macOS 同一 wheel 矩阵、特殊路径、生成式支持表、3.14 探测 | Windows 支持、Python 3.14 认证、运行时修复环境 |
| `v0.6.x` | 兼容性与可诊断性列车 | `doctor`、平台/解释器/pytest 矩阵、特殊路径与降级验证 | 改变 triage/audit 核心语义、Web、负载测试 |
| `v0.7.0` | 规模化与数据生命周期版 | 性能/内存基线、大 fixture、schema 迁移、记录清理、可选依赖拆分 | 多用户服务、自动调参 |
| `v1.0.0` | 正式安全发布版 | 安全门、发布矩阵、供应链证据、PyPI、治理文件、真实项目回归矩阵 | Web、watch、Vitest 完整闭环 |

Web 或常驻服务出现后再规划负载、并发压力、长稳、运行时监控和泄漏监控，不为尚不存在的服务预设版本号。

## 4. 统一发布门

每个版本必须同时满足：

1. 默认测试、目标版本新增测试和 `git diff --check` 通过；
2. Python 源码编译通过；
3. wheel/sdist 构建成功，并从 wheel 在干净环境完成 CLI smoke；
4. CLI help、README、用户指南、项目结构与实际行为一致；
5. 失败、超时、工具缺失和用户中断均有稳定退出码与结构化状态；
6. 运行前后目标项目源码、测试、snapshot 和 Git 状态不变，除非用户显式批准既有候选提交流程；
7. 新持久化格式有 schema version、原子写入、脱敏、限长和损坏输入测试；
8. 真实项目验收只记录脱敏摘要，不成为默认 CI 对外部路径的硬依赖。

## 5. 计划索引

- `v0.6.0`：`2026-08-03-coverage-and-code-quality-v0.6.0.md`
- `v0.6.1`：`2026-08-04-environment-doctor-v0.6.1.md`
- `v0.6.2`：`2026-08-05-compatibility-matrix-v0.6.2.md`
- `v0.6.x`：`2026-08-04-compatibility-and-doctor-v0.6.x.md`
- `v0.7.0`：`2026-08-04-scale-and-data-lifecycle-v0.7.0.md`
- `v1.0.0`：`2026-08-04-secure-release-v1.0.0.md`

较早计划保留为历史决策记录；当其版本定义与本文冲突时，以本文及上述版本实施计划为准。
