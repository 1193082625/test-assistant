> 历史设计，非当前使用文档。当前结构见 `docs/project-structure.md`，当前操作方式见 `docs/user-guide.md`。

# test-assistant 产品与实施设计 v2

> 状态：历史实施基线
>
> 更新日期：2026-07-20
>
> 替代关系：本文件修订 `2026-06-29-auto-test-design.md` 的路线图与日计划；原文件保留为初始构想记录。
>
> 修订依据：当前代码实现、现有测试结果，以及会话 `019f7ce7-9bc8-7a53-b9ea-b5d0ed7cc77c` 中关于“项目缺陷、测试缺陷与测试基础设施故障归因”的讨论。

## 1. 产品定位

`test-assistant` 是一个面向开发项目的本地测试辅助 CLI。它分析目标项目的结构、语言、框架、代码符号和变更，生成可审阅的测试方案与候选测试代码，经过质量校验和用户确认后执行测试，并对失败结果给出有证据的归因建议。

工具的核心价值不是“尽可能多地生成测试”，而是建立一条可信链路：

```text
项目检测 → 代码与契约分析 → TestSpec → 候选测试代码
        → 质量门禁 → 用户确认 → 隔离执行 → 失败归因 → 状态提交
```

产品同时承担两个目标：

1. 工具目标：减少测试编写成本，及时发现回归，并避免错误测试掩盖真实缺陷。
2. 学习目标：通过真实功能逐步掌握 Python 工程化、LangChain、LangGraph、LangSmith、FastAPI 与 React。

学习目标服务于产品目标。除非固定工作流已经不足以解决问题，否则不为了练习 Agent 而引入 Agent。

## 2. v1.0 范围

### 2.1 必须完成

- 支持 Python 项目的可靠检测、源码分析、pytest 测试生成与执行。
- 支持 JavaScript/TypeScript 项目检测，以及 Vitest 纯逻辑单元测试的执行。
- 支持多模块项目的证据收集，不因第一个标志文件过早停止分析。
- 支持基于文件快照的增量检测，并在成功流程结束后提交新快照。
- 先生成结构化 `TestSpec`，再生成候选测试代码。
- 候选测试必须通过语法、导入、收集和隔离执行门禁。
- 未经用户确认，不覆盖已有测试，不改变业务断言，不执行高副作用测试。
- 将失败分为产品缺陷、测试缺陷、基础设施故障、Flaky 和证据不足。
- CLI 展示诊断证据、置信度和建议动作。

### 2.2 延后完成

- 自动生成所有前端组件测试。
- uni-app 组件渲染、页面跳转和真实小程序运行时测试。
- 自动修改目标项目业务代码。
- 完全自主的 ReAct Agent。
- 视觉、性能、变异和可访问性测试的自动生成。
- 多用户、云端协作和复杂权限系统。

这些能力可以作为 v1.x/v2.0 扩展，不能阻塞 v1.0 的可信闭环。

## 3. 核心原则

### 3.1 失败不等于产品缺陷

测试失败统一归为以下类别之一：

| 分类 | 含义 | 默认动作 |
| --- | --- | --- |
| `PRODUCT_DEFECT` | 已确认预期未被目标代码满足 | 建议定位目标代码，不自动修改测试 |
| `TEST_DEFECT` | 测试语法、导入、Mock、Fixture 或断言依据有问题 | 只允许机械性修复自动进行 |
| `INFRA_DEFECT` | Runner、依赖、浏览器、数据库或环境故障 | 修复环境后重试 |
| `FLAKY` | 相同输入和环境下结果不稳定 | 隔离并重复运行，不直接判责 |
| `INCONCLUSIVE` | 证据不足或业务预期冲突 | 请求用户确认 |

### 3.2 测试预期必须可追溯

每条业务断言应关联至少一种证据：

1. 用户明确确认的规则；
2. OpenAPI、Schema、类型契约或产品文档；
3. 项目已有测试；
4. 历史稳定行为；
5. 当前实现推断。

仅来自当前实现的预期可用于回归记录，但不能独立证明当前实现存在缺陷。

### 3.3 自动修复有明确边界

允许自动修复：import 路径、测试框架 API、语法、类型、Mock 签名、资源清理、固定时间和随机种子。

禁止自动修复：删除或跳过失败断言、把期望值改成实际值、放宽业务条件、降低断言强度、改变已确认业务契约。

### 3.4 默认安全

- 源码、注释和文档都作为不可信 prompt 数据处理。
- 生成代码先写候选区，不直接进入正式测试目录。
- 执行器使用参数数组，不拼接 Shell 命令。
- 网络、数据库、文件写入和浏览器测试必须显式声明能力并获得确认。
- 不上传密钥、二进制文件、构建产物或用户排除的内容。

## 4. 领域模型

### 4.1 项目分析

```python
class ProjectAnalysis:
    root: str
    modules: list[ProjectModule]
    primary_type: str
    capabilities: list[str]
    evidence: list[DetectionEvidence]
    warnings: list[str]

class ProjectModule:
    root: str
    languages: list[str]
    frameworks: list[str]
    test_frameworks: list[str]
    build_tools: list[str]
```

机器值统一使用小写稳定枚举，例如 `python`、`javascript`、`miniprogram`、`pytest`、`vitest`；展示名称与业务判断分离。

### 4.2 测试意图

```python
class TestSpec:
    id: str
    target_symbol: str
    test_type: str
    behavior: str
    arrange: dict
    action: str
    expected: dict
    evidence: list[ExpectationEvidence]
    side_effects: list[str]
    status: str  # proposed | approved | rejected
```

### 4.3 候选测试

```python
class TestCandidate:
    spec_id: str
    source_path: str
    candidate_path: str
    final_path: str
    content_hash: str
    validation_results: list[ValidationResult]
    status: str  # generated | validated | approved | committed | failed
```

候选路径必须保留源目录层级，避免不同目录中的同名文件互相覆盖。

### 4.4 失败诊断

```python
class FailureDiagnosis:
    category: str
    confidence: float
    symptom: str
    evidence: list[DiagnosticEvidence]
    target_locations: list[str]
    suggested_actions: list[SuggestedAction]
```

诊断输出必须包含证据，不允许只返回一个无法解释的分类。

## 5. 架构与模块边界

```text
cli/
  commands/           参数解析、交互确认、结果展示
core/
  models/             稳定枚举和领域模型
  analyzers/
    project.py        标志文件收集、模块划分、框架检测
    source.py         符号与依赖分析
    contract.py       文档、Schema、已有测试证据
    changes.py        快照和 git diff 变更检测
    impact.py         源文件到测试的影响映射
  planners/           生成和维护 TestSpec
  generators/         从已批准 TestSpec 生成候选代码
  validators/         语法、导入、收集、隔离运行验证
  executors/          执行器及注册表
  diagnosticians/     失败归因、重复运行、基线比较
  graphs/             固定工作流编排
  storage/            配置、快照、方案、历史和诊断持久化
```

CLI 必须保持薄层；检测、生成、验证和归因逻辑不能依赖 Click，确保可单测、可复用和后续可被 Web/API 调用。

## 6. 工作流

### 6.1 初始化

```text
validate_path
→ collect_project_evidence
→ analyze_modules
→ detect_test_capabilities
→ environment_preflight
→ create_workspace
→ save_config_and_baseline
→ propose_initial_plan
```

`bootstrap` 表示协助搭建测试环境；`existing` 表示扫描已有测试和覆盖缺口。模式不明确时输出建议，不静默安装依赖或覆盖配置。

### 6.2 增量运行

```text
detect_changes
→ analyze_impact
→ create_or_update_specs
→ generate_candidates
→ validate_candidates
→ user_confirm
→ commit_candidates
→ run_affected
→ diagnose_failures
→ persist_history
→ commit_snapshot
```

快照只在流程完成且状态已持久化后更新。失败或用户拒绝候选时保留旧基线，记录本次尝试，不进入无限重试。

### 6.3 候选质量门禁

按成本从低到高执行：

1. 输出结构和空内容检查；
2. Python AST / TypeScript parser 语法检查；
3. import 和模块路径检查；
4. `pytest --collect-only` 或 Vitest 列举测试；
5. 测试 Runner 健康检查；
6. 临时目录隔离执行；
7. 副作用和不稳定性检查；
8. 生成候选 diff 供用户确认。

任何门禁失败都不能覆盖正式测试。

### 6.4 失败归因

失败后依次执行：

1. 判断测试代码是否编译和收集成功；
2. 判断 Runner 健康检查是否通过；
3. 单独运行失败测试；
4. 必要时重复运行 3 次识别 Flaky；
5. 对比 Git SHA、测试摘要、生成器版本和环境摘要；
6. 对照 TestSpec 的预期证据；
7. 生成分类、置信度和建议动作。

业务预期冲突一律进入 `INCONCLUSIVE` 或人工确认，不由 LLM 自动决定。

## 7. 存储设计

```text
.autotest/
├── config.yml
├── snapshot.json
├── project-analysis.json
├── plans/
│   └── <plan-id>.json
├── candidates/
│   └── <plan-id>/...
├── test_cases/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── history.db
└── lessons.md
```

历史记录至少保存：目标项目 Git SHA、快照摘要、生成器版本、prompt/template 版本、依赖锁摘要、环境摘要、TestSpec、测试代码摘要、执行结果和诊断结果。

`lessons.md` 只保存可审计的通用经验，不保存密钥、整段源码或未经确认的业务事实。

## 8. CLI 设计

```text
test-assistant init      初始化和环境预检
test-assistant inspect   查看项目检测证据与能力
test-assistant plan      查看、批准或拒绝 TestSpec
test-assistant generate  生成并验证候选测试
test-assistant run       执行已批准的受影响测试
test-assistant diagnose  查看失败归因及证据
test-assistant status    查看基线、计划和测试健康状态
test-assistant report    导出报告
test-assistant serve     启动 Web Dashboard
```

`run` 可以提供一站式交互流程，但内部仍调用独立服务，不能把安装依赖、修改配置、生成、覆盖和执行混在一个函数中。

## 9. 非功能要求

### 9.1 正确性

- 相同输入和配置产生确定性的项目检测结果。
- 未通过门禁的候选测试绝不进入正式目录。
- 不支持的框架返回结构化“不支持”，不能因局部变量未初始化而崩溃。
- 快照提交后，无新变更再次运行应返回空变更集。

### 9.2 可恢复性

- 正式测试落盘使用临时文件加原子替换。
- 覆盖前保留内容摘要和可恢复版本。
- 任意节点失败均记录阶段、原因和可重试性。
- Graph 重试次数必须单调增加并有硬上限。

### 9.3 性能与成本

- 默认忽略二进制、构建产物、依赖目录和超大文件。
- 文件未改变时复用符号分析和 TestSpec。
- LLM 调用按文件与符号做 token 预算，超限时分块。
- 无有效源代码变更时不调用 LLM。

### 9.4 可观测性

- 每次运行具有 `run_id` 和阶段耗时。
- 记录 LLM 模型、模板版本、token 使用量和失败原因。
- LangSmith 是可选追踪能力，关闭后核心流程仍可运行。

## 10. 关键架构决策

### ADR-001：先 TestSpec，后测试代码

- 决策：业务预期先结构化并关联证据，测试代码只是 TestSpec 的可执行实现。
- 理由：把“预期是否正确”和“代码是否能运行”分开，避免直接从当前实现复制行为。
- 代价：多一个模型和确认步骤，但可审计性显著提高。

### ADR-002：固定工作流优先于自主 Agent

- 决策：v1.0 使用 LangGraph 编排确定性节点；Agent 只用于候选分析，不拥有落盘和修改业务断言权限。
- 理由：测试工具需要可重复、可恢复和可解释。
- 代价：早期自主性较低，但调试成本和安全风险更小。

### ADR-003：生成、确认、提交三阶段分离

- 决策：LLM 只写候选区；通过门禁并经确认后才提交正式测试。
- 理由：防止无效代码覆盖人工测试。
- 代价：CLI 多一个确认步骤，可通过批量审批改善体验。

### ADR-004：判责与修复分离

- 决策：失败先产生诊断；只有机械性测试问题允许自动修复，业务语义变化必须人工确认。
- 理由：防止系统通过削弱测试来制造“通过”。
- 代价：部分问题无法全自动处理，但结果更可信。

### ADR-005：先做好 Python 垂直闭环

- 决策：Python + pytest 达到完整质量标准后，再让 JS/TS 和 E2E 复用同一协议扩展。
- 理由：同时支持所有语言和测试类型会稀释验证深度。
- 代价：前端完整能力延期，但能够更早得到真正可用的产品。

## 11. 当前实现基线

截至 2026-07-20，仓库已经具备 CLI 骨架、基础框架检测、快照、Python AST 分析、pytest/vitest 执行器、LangGraph 流程和初版 LLM 生成器，但尚未形成可信闭环。

需要优先处理的已知差距：

- 项目类型和框架值大小写、枚举不一致；未知项目降级会报错。
- 项目检测遇到第一个标志文件即停止，无法可靠识别多模块项目。
- 快照比较后不提交新快照，同一变更会被永久重复检测。
- 生成结果未经语法、收集和执行校验便覆盖测试。
- 生成文件按 basename 命名，存在同名覆盖风险。
- `module_path` 没有进入 prompt，导入路径依赖模型猜测。
- `learn_node` 未实现，失败分支可能循环到图递归上限。
- 当前流程没有实现文档声明的用户确认。
- `run_affected` 实际运行全部测试，尚无影响分析。
- 现有测试 9 个中有 3 个失败；默认 pytest 收集还会误收集生产文件 `test_generator.py`。

因此，原计划不能直接把当前状态视为 v0.2 完成，也不应立即进入 ReAct Agent 或 Web Dashboard。

## 12. 修订后的 50 日计划

计划按验收门推进，而不是只按日期推进。某天任务未达到完成标准，应顺延，不把未完成风险带入下一阶段。

### Sprint A：恢复可靠底座（Day 1-10）

目标：现有功能从“能运行”提升到“行为确定、测试通过、状态闭环”。

| 天 | 主题 | 交付物 | 当日完成标准 |
| ---: | --- | --- | --- |
| 1 | 基线与测试入口 | pytest 配置、依赖检查、当前失败清单 | `pytest` 只收集 `tests/`；测试命令在干净环境可复现 |
| 2 | 领域枚举 | `ProjectType`、`Language`、`TestFramework` 和默认模型 | 删除业务判断中的大小写分支；unknown 可正常序列化 |
| 3 | 检测器修复 | 确定性标志文件解析、错误信息和检测证据 | Python/React/uni-app/unknown 表格测试通过 |
| 4 | 多模块检测 | 先收集全部证据，再划分模块和主类型 | 同时存在 package 与 pyproject 时不丢失任一模块 |
| 5 | 快照模型 | 相对路径、过滤规则、稳定排序、版本字段 | 相同目录连续快照完全一致；二进制与产物被排除 |
| 6 | 快照提交闭环 | compare/commit 分离、原子写入 | 提交后再次检测得到零变更；失败不更新基线 |
| 7 | 执行器注册表 | 按语言、框架、测试类型选择执行器 | 不支持组合返回结构化结果，不出现未绑定变量 |
| 8 | 执行结果规范 | stdout/stderr、退出码、超时、错误分类 | Runner 启动失败不会被报告成 0 个失败 |
| 9 | Graph 收敛 | 删除空重试或实现有界状态迁移 | 所有分支有限结束；重试次数单调增加 |
| 10 | Sprint 验收 | init/detect/run 集成测试与回顾 | 全量测试通过；无变更运行不调用生成器或执行器 |

学习重点：数据建模、pytest、文件系统一致性、LangGraph 状态和失败处理。

### Sprint B：可信项目与源码分析（Day 11-20）

目标：让后续生成器获得稳定、可追踪、规模可控的上下文。

| 天 | 主题 | 交付物 | 当日完成标准 |
| ---: | --- | --- | --- |
| 11 | 符号模型 | `SourceSymbol`：限定名、所属类、签名、装饰器和范围 | 顶层函数、类方法、异步函数、嵌套函数可区分 |
| 12 | Python 类型解析 | 基于 `ast.unparse` 的完整签名与类型 | 支持泛型、联合、属性类型和默认参数 |
| 13 | Python 导入解析 | 包根、src 布局、相对导入、别名导入 | 典型包结构能生成确定模块路径 |
| 14 | 可测性分类 | 公共顶层函数、类方法、副作用函数分类 | 不可直接测试的符号返回理由，不静默跳过 |
| 15 | 已有测试索引 | 源符号与已有测试之间的映射 | 不为已有等价测试重复生成候选 |
| 16 | 契约证据 | 提取 docstring、类型、已有测试、Schema 引用 | 每个预期来源带路径和强度 |
| 17 | 影响分析 v1 | changed symbol → direct test 映射 | `run_affected` 不再默认执行全部测试 |
| 18 | 上下文预算 | 文件大小、符号分块、敏感内容过滤 | 超大文件不整文件进入 prompt |
| 19 | inspect 命令 | 展示模块、证据、能力、警告和可测符号 | 用户可解释“为什么被这样识别” |
| 20 | Sprint 验收 | 多种 fixture 项目端到端分析测试 | 输出确定、可序列化、可被 planner 消费 |

学习重点：AST、模块系统、静态分析、缓存和可解释检测。

### Sprint C：TestSpec 与候选生成（Day 21-30）

目标：实现 Python + pytest 的可信生成、确认、执行和归因闭环。

| 天 | 主题 | 交付物 | 当日完成标准 |
| ---: | --- | --- | --- |
| 21 | TestSpec 模型 | 行为、输入、预期、证据、副作用和状态 | 无证据断言被标为弱推断，不能自动判项目缺陷 |
| 22 | Planner | 从符号和证据生成结构化 TestSpec | Pydantic 校验失败可重试且保留原始错误 |
| 23 | 计划审阅 | `plan` 列表、详情、批准和拒绝 | 审批状态可持久化并在重启后恢复 |
| 24 | 生成器 v2 | 从批准的 TestSpec 生成候选 pytest | prompt 明确模块路径、测试目标和禁止行为 |
| 25 | 候选存储 | 分层路径、内容摘要、模板版本、原子写入 | 同名源文件不会覆盖；已有人工测试默认不改 |
| 26 | 静态门禁 | 空输出、代码块、AST、import、collect-only | 任一门禁失败均不进入正式测试目录 |
| 27 | 隔离执行门禁 | Runner 健康检查、临时目录运行和超时 | 基础设施失败与测试失败可区分 |
| 28 | 用户确认与提交 | diff 审阅、批量确认、原子提交和恢复 | 未确认候选不能执行或覆盖正式文件 |
| 29 | 失败归因 v1 | 五类诊断、证据评分、重复运行和建议动作 | 测试语法错、Runner 故障、稳定断言失败能正确分流 |
| 30 | 垂直闭环验收 | detect→plan→generate→validate→confirm→run→diagnose→snapshot | Python fixture 项目完整演示；所有节点有测试和结构化结果 |

学习重点：PromptTemplate、Pydantic 输出、LCEL、LangGraph HITL、LangSmith 追踪和安全代码生成。

> 与原计划相比，ReAct Agent、`lessons.md` 自动学习和 Playwright 生成不再占用本 Sprint。先把确定性工作流和质量门禁做好，才有安全的 Agent 工具边界。

### Sprint D：历史、API 与 Web 最小闭环（Day 31-40）

目标：在不复制核心逻辑的前提下，把已稳定的 CLI 能力开放给 Web。

| 天 | 主题 | 交付物 | 当日完成标准 |
| ---: | --- | --- | --- |
| 31 | 历史存储 | SQLite schema、迁移和 repository | run/spec/candidate/result/diagnosis 可关联查询 |
| 32 | FastAPI 骨架 | 配置、错误模型、健康检查和依赖注入 | API 错误不会泄漏密钥或原始异常 |
| 33 | 项目与分析 API | project、inspect、status 接口 | API 与 CLI 调用同一 core service |
| 34 | 计划与审批 API | plan 查询、批准、拒绝、候选 diff | 状态迁移与 CLI 一致且幂等 |
| 35 | 执行 API | 后台任务、取消、超时和状态查询 | 重复请求不会启动重复运行 |
| 36 | WebSocket/SSE | 运行事件与日志推送 | 断线重连后可从历史状态恢复 |
| 37 | React 基础 | Vite、TypeScript、路由、API client | 有加载、空、错误和重试状态 |
| 38 | 项目与计划页面 | 检测证据、TestSpec、diff 和审批 | 用户可在页面完成候选确认 |
| 39 | 执行与诊断页面 | 进度、结果、分类、置信度和证据 | 不只显示 passed/failed，能解释归因 |
| 40 | Sprint 验收 | CLI/Web 同一项目端到端验收 | 两端状态一致；刷新页面不丢执行历史 |

学习重点：FastAPI、Pydantic、SQLite、React、Ant Design、状态管理和实时通信。

### Sprint E：扩展与发布（Day 41-50）

目标：扩展第二种技术栈，完成工程化和发布，而不是一次性铺开所有测试类型。

| 天 | 主题 | 交付物 | 当日完成标准 |
| ---: | --- | --- | --- |
| 41 | JS/TS 符号协议 | 基于稳定 parser 的符号适配器 | 与 Python 输出相同 `SourceSymbol` 协议 |
| 42 | Vitest 生成与验证 | 纯函数/工具模块 TestSpec 和候选生成 | 明确拒绝未支持的 uni-app 运行时场景 |
| 43 | Flaky 与基线诊断 | 重复策略、环境摘要、Git/依赖差分 | 目标代码、测试、环境同时变化时返回不确定 |
| 44 | lessons 受控学习 | 人工批准的通用经验和版本化模板 | 未确认诊断不能写入后续 prompt 规则 |
| 45 | watch 模式 | 防抖、事件合并、取消与安全提示 | 只自动生成候选，不自动批准业务断言 |
| 46 | 报告 | Markdown/HTML 运行与归因报告 | 报告包含证据、环境和可复现命令 |
| 47 | 安全与隐私 | prompt 注入、防路径穿越、敏感信息测试 | 恶意源码注释不能改变系统落盘权限 |
| 48 | 性能与成本 | 缓存、增量 AST、LLM 预算和性能基线 | 大 fixture 项目达到已定义时间/token 预算 |
| 49 | 发布工程 | README、配置参考、CI、版本和打包 | 干净环境安装后 smoke test 与测试通过 |
| 50 | v1.0 验收 | 场景矩阵、故障演练、复盘和后续路线 | 所有 v1.0 必须项有自动验收证据 |

学习重点：适配器设计、工程化、安全、性能、发布和生产故障思维。

## 13. Sprint 验收门

每个 Sprint 只有满足以下条件才算完成：

- 自动化测试全部通过，且默认测试命令无收集错误。
- 新增核心分支有单元测试，关键用户流程有集成测试。
- 错误结果是结构化数据，不依赖解析打印文本才能判断。
- 文档和 CLI 帮助与实际行为一致。
- 没有未经确认的覆盖、依赖安装或业务断言修改。
- 已知限制有明确输出，不以“跳过”伪装成功。
- 完成一次 fixture 项目演示，并保存可复现步骤。

## 14. 测试策略

### 14.1 测试分层

| 层级 | 测试对象 | 主要方式 |
| --- | --- | --- |
| 单元测试 | 解析器、模型、路由、评分和路径映射 | 纯函数 + 临时目录 |
| 契约测试 | LLM 输出、执行器结果、存储 schema | 固定响应和 fixture 输出 |
| 集成测试 | init、plan、generate、run、diagnose | CliRunner + fake LLM + fake executor |
| E2E fixture | Python/Vitest 示例项目 | 隔离环境真实 runner |
| 故障测试 | 超时、损坏 JSON、缺依赖、Flaky、权限错误 | 可控故障注入 |

### 14.2 必测项目矩阵

- 空目录和未知项目；
- Python 根布局和 `src/` 布局；
- React/Vitest 项目；
- package + pyproject 多模块项目；
- uni-app 项目及不支持能力说明；
- 同名源文件；
- 无变更、增加、修改、删除和重命名；
- LLM 返回空文本、说明文字、多代码块和非法语法；
- Runner 缺失、超时、退出非零和无测试收集；
- 稳定产品失败、测试导入失败、基础设施失败和 Flaky。

## 15. v1.0 完成标准

以下场景必须同时成立：

1. 用户可初始化 Python 项目并看到有证据的检测结果。
2. 修改一个公共函数后，只产生相关 TestSpec 和候选测试。
3. 非法候选不能进入正式测试目录。
4. 用户能查看 diff 并批准候选，拒绝后项目文件不变。
5. 批准测试执行后，快照正确提交；再次运行不重复生成。
6. 产品缺陷、测试缺陷和 Runner 故障能展示不同诊断与证据。
7. 系统不能通过删除、跳过或削弱断言自动制造通过结果。
8. CLI 和 Web 使用同一核心服务并展示一致状态。
9. 干净环境中默认测试命令、打包安装和 smoke test 全部通过。

## 16. 后续路线

v1.0 之后按需求和证据扩展：

1. Playwright E2E 和浏览器环境诊断；
2. uni-app 专用执行器；
3. 集成测试数据沙箱和容器能力；
4. 覆盖率与变异测试驱动的 TestSpec 优先级；
5. 经审批的 Agent 工具调用；
6. MCP 薄适配层；
7. 多项目趋势和团队协作。

任何扩展都必须复用 TestSpec、候选门禁、用户确认和失败归因协议，不能绕过可信链路。
