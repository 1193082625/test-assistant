# test-assistant: LLM 驱动的智能测试工具

## 概述

`test-assistant` 是一个基于 LangChain 生态构建的智能测试 CLI 工具 + Web Dashboard。它能够绑定一个开发项目，自动分析项目结构，LLM 驱动生成多类型测试用例，经用户确认后执行，并在迭代过程中持续增量更新。

## 项目双重目标

### 目标一：工具价值

帮助开发团队保证交付质量并提升效率——通过自动化测试生成、增量执行、持续学习，减少人工编写维护测试的工作量。

### 目标二：学习成长（核心驱动）

**通过开发 `test-assistant`，系统性地掌握 LangChain 生态和 React 生态，达到后期能独立开发 Agent 的能力。**

- **LangChain 生态学习路径**：
  - LangChain Core（链、提示词模板、输出解析器）
  - LangGraph（有向图工作流编排 → Agent 多步推理）
  - LangSmith（可观测性 → Agent 调试与优化）
  - Agent 模式（ReAct、Tool-use → 自主决策系统）

- **React 生态学习路径**：
  - React + TypeScript 基础
  - Ant Design 组件库（企业级 UI）
  - React Router（SPA 路由）
  - Hooks、状态管理、WebSocket 实时通信
  - 前端工程化（构建、打包、部署）

- **学习路径设计**：从简单到复杂，从 CRUD 到 Agent，每个功能模块同时承担"产出功能"和"练习课题"双重身份

> 这个项目的最终交付物不仅是 `test-assistant` 工具本身，更是"能用 LangChain + React 独立构建 Agent 级应用"的工程能力。

## 核心原则

- **长期伴生**：贯穿项目的整个开发周期，不是一次性工具
- **测试注入**：测试用例持久化到项目 `.autotest/` 目录，可直接被项目引用
- **增量驱动**：只检测变更、只生成/执行受影响用例，不做无意义全量重跑
- **持续学习**：从失败模式中学习，优化后续生成策略
- **CLI 为主，Web 为辅**：日常操作 CLI 快速完成，深度操作 Web Dashboard 辅助

## 技术栈

| 层       | 技术                                            |
| -------- | ----------------------------------------------- |
| CLI 框架 | Python (Click/Typer)                            |
| AI 编排  | LangChain + LangGraph                           |
| 可观测性 | LangSmith                                       |
| Web 后端 | FastAPI                                         |
| Web 前端 | React + Ant Design                              |
| 数据存储 | SQLite + 文件系统快照                           |
| 测试执行 | subprocess 调用 pytest / vitest / Playwright 等 |

## 交付形态

```
test-assistant 命令行工具（主入口）
├── test-assistant init        初始化绑定项目
├── test-assistant run         增量运行测试
├── test-assistant watch       监听模式
├── test-assistant plan        查看/编辑测试方案
├── test-assistant status      项目测试健康状态
├── test-assistant serve       启动 Web Dashboard
└── test-assistant report      导出 HTML 报告
```

## 被测试项目结构

绑定后，工具在项目中创建 `.autotest/` 工作区：

```
my-project/
├── src/
├── .autotest/
│   ├── config.yml          用户可编辑配置
│   ├── snapshot.json       文件哈希/结构快照（变更检测用）
│   ├── lessons.md          AI 从失败中学习的模式
│   ├── test_cases/
│   │   ├── unit/            单元测试
│   │   ├── integration/     集成测试
│   │   ├── e2e/             E2E 测试
│   │   ├── visual/          视觉回归测试
│   │   ├── accessibility/   可访问性测试
│   │   ├── mock/            Mock/契约测试
│   │   ├── mutation/        变异测试
│   │   ├── performance/     性能基线测试
│   │   └── edge/            边界测试
│   └── history.db          历史执行记录
└── package.json            （可选）自动追加测试脚本
```

## 测试类型

按项目类型自动推荐优先级：

| 测试类型  | 覆盖场景                    | 前端 | 后端 | 小程序 |
| --------- | --------------------------- | :--: | :--: | :----: |
| 单元测试  | 函数、组件、Hook 输入输出   | ★★★  | ★★★  |  ★★★   |
| 集成测试  | API、数据库、模块间协作     | ★★☆  | ★★★  |  ★★☆   |
| E2E 测试  | 用户关键路径流程            | ★★★  | ★★☆  |  ★★★   |
| 视觉回归  | CSS 变更导致的布局/样式问题 | ★★★  | ☆☆☆  |  ★★☆   |
| 可访问性  | WCAG 合规、屏幕阅读器支持   | ★★☆  | ☆☆☆  |  ★☆☆   |
| Mock 测试 | 前端依赖的后端 API 模拟     | ★★★  | ★★☆  |  ★★★   |
| 变异测试  | 测试是否能真正捕获 bug      | ★★☆  | ★★☆  |  ★★☆   |
| 性能基线  | 关键路径耗时对比            | ★★☆  | ★★★  |  ★☆☆   |
| 边界测试  | 空值、极限、异常输入        | ★★☆  | ★★★  |  ★★☆   |

## 两种初始化场景

### 初始项目 (`--mode bootstrap`)

- 搭测试框架骨架（jest/vitest 配置 + 依赖 + 钩子）
- 生成空测试模板（写代码时自动填充）
- 启动 watch 模式随开发自动补用例

### 迭代中的项目（默认）

- 扫描现有测试覆盖率，识别缺口
- 保留现有测试不变，只补充缺失
- 接入 git diff / 文件快照做变更检测

## 架构设计

```
test-assistant (Python CLI 包)
├── core/                    核心库
│   ├── agents/              各种 Agent 实现
│   ├── graphs/              LangGraph 工作流
│   │   ├── init_graph.py      初始化图
│   │   ├── run_graph.py       增量执行图
│   │   └── report_graph.py    报告生成图
│   ├── analyzers/           项目分析器
│   │   ├── framework.py      框架检测
│   │   ├── coverage.py       覆盖率扫描
│   │   └── changes.py        变更检测
│   ├── generators/          测试生成器
│   │   ├── unit.py
│   │   ├── e2e.py
│   │   └── ...
│   ├── executors/           测试执行器
│   │   ├── pytest_executor.py
│   │   ├── vitest_executor.py
│   │   └── playwright_executor.py
│   └── models/              数据模型
├── cli/                     Click 命令
│   ├── main.py              入口
│   ├── commands/
│   │   ├── init.py
│   │   ├── run.py
│   │   ├── plan.py
│   │   └── serve.py
│   └── watcher.py           文件系统监听
├── web/                     FastAPI 后端
│   ├── main.py
│   ├── api/
│   ├── ws/                   WebSocket
│   └── static/               React 构建产物
├── reports/                 报告生成
│   ├── html/
│   └── markdown/
├── frontend/                React + Ant Design 源码
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── PlanEditor.tsx
│   │   │   ├── ExecutionBoard.tsx
│   │   │   └── ReportDetail.tsx
│   │   ├── components/
│   │   └── hooks/
│   └── package.json
└── pyproject.toml           Poetry 管理整个 python 包
```

## LangGraph 工作流

### 入口图

```
detect_mode ──→ bootstrap_tests  (初始项目)
             ──→ scan_coverage    (迭代项目/首次绑定)
             ──→ detect_changes   (已绑定 → 增量运行)
```

### 增量运行图

```
detect_changes → analyze_impact → update_tests → user_confirm
    ↓                                                      |
    └── (确认) → run_affected → analyze_results → learn ←─┘
    └── (拒绝) → update_tests (重新生成)
```

### HITL (Human-in-the-Loop)

关键节点：用户确认测试用例后才执行。用户可以在 CLI 确认，也可以在 Web Dashboard 上批量操作。

## API 设计

```
GET    /api/projects                     # 项目列表
POST   /api/projects                     # 绑定项目
GET    /api/projects/{id}                # 项目详情

POST   /api/projects/{id}/run            # 触发增量运行
POST   /api/projects/{id}/watch          # 启动监听

GET    /api/projects/{id}/plan           # 获取测试方案
PUT    /api/test-cases/{id}              # 编辑/确认用例
POST   /api/plans/{id}/confirm           # 批量确认 → 触发执行

WS     /ws/executions/{plan_id}          # 实时日志推送

GET    /api/projects/{id}/reports        # 报告列表
GET    /api/projects/{id}/reports/{rid}  # 报告详情
GET    /api/projects/{id}/trend          # 回归趋势数据
```

## Web Dashboard 页面

| 路由                         | 页面     | 说明                           |
| ---------------------------- | -------- | ------------------------------ |
| `/`                          | 项目总览 | 多项目健康卡片、快捷操作       |
| `/projects/:id/plan`         | 测试方案 | 按类型 Tab 分组、批量确认/编辑 |
| `/projects/:id/exec`         | 执行看板 | 实时进度、日志流、控制按钮     |
| `/projects/:id/reports/:rid` | 报告详情 | 统计、失败分析、回归趋势图     |
| `/settings`                  | 设置     | LLM 配置、排除规则、提示词     |

## 版本规划

| 版本 | 周期     | 核心交付            | 完成标准                                           | LangChain 阶段                                | React 阶段                |
| ---- | -------- | ------------------- | -------------------------------------------------- | --------------------------------------------- | ------------------------- |
| v0.1 | 第1-2周  | CLI 骨架 + 项目分析 | `test-assistant init` 能绑定项目、识别框架、拍快照 | Core: ChatModel, PromptTemplate, OutputParser | -                         |
| v0.2 | 第3-4周  | LangGraph 增量执行  | `test-assistant run` 能检测变更并执行测试          | LCEL, Graph, Smith Tracing                    | -                         |
| v0.3 | 第5-6周  | LLM 测试生成        | 能自动生成用例、用户确认后执行                     | Tool, Agent, ReAct, Few-shot                  | -                         |
| v0.4 | 第7-8周  | Web Dashboard       | 浏览器管理测试全流程                               | (复用深化)                                    | Vite, TSX, Ant Design, WS |
| v1.0 | 第9-10周 | 打磨完善            | 生产可用、发布 PyPI                                | (深化理解)                                    | 前端工程化                |

## 阶段规划（日级）

每个版本 = 1 个 Sprint = 10 个工作日。每天有明确的**交付物**和**学习目标**。

---

### v0.1：CLI 骨架 + 项目分析（Day 1-10）

**学习主线**：Python 工程化 → Click CLI → 文件 I/O → LangChain Core 入门

| 天  | 模块           | 交付物                                                          | 学习目标                      |
| :-: | -------------- | --------------------------------------------------------------- | ----------------------------- |
|  1  | 项目初始化     | pyproject.toml, CLI 骨架, `test-assistant --help` 显示所有命令  | Python 包结构, Click 命令组   |
|  2  | `init` 命令壳  | init 命令解析 path/mode/name, 创建 .autotest/ 目录 + config.yml | Click 参数/选项, YAML         |
|  3  | 框架检测器     | 扫描项目识别前端/后端/小程序，输出框架信息                      | 文件系统遍历, 模式匹配        |
|  4  | 测试框架检测   | 识别 jest/vitest/pytest/JUnit, 检测构建工具                     | 配置文件解析 (JSON/YAML/TOML) |
|  5  | 文件快照系统   | 遍历文件树 + SHA256 hash → snapshot.json                        | Python hashlib, JSON 序列化   |
|  6  | init 完整流程  | 整合 2-5: 绑定→检测→快照→写入，含错误处理                       | 流程编排, 错误处理            |
|  7  | LangChain 入门 | 安装 LC, 写第一个 ChatModel 调用, PromptTemplate                | LangChain Core, LLM 调用      |
|  8  | OutputParser   | 用 LLM 生成测试框架配置建议, StructuredOutputParser             | OutputParser, 结构化输出      |
|  9  | 自验证         | 用 test-assistant 检测自身项目, 编写 pytest 测试                | 自举验证, 测试驱动            |
| 10  | Sprint 回顾    | 代码审查, v0.1 完整验证, 学习总结 → lessons.md                  | 回顾反思                      |

**v0.1 完成标志**：

```
$ test-assistant init --path /some/project
✓ 已绑定项目: some-project
✓ 框架检测: React + Vitest
✓ 快照已保存 (42 files)
$ test-assistant status
项目: some-project  |  框架: React  |  测试框架: Vitest  |  文件: 42
```

---

### v0.2：LangGraph 增量执行（Day 11-20）

**学习主线**：LCEL → 执行器 → LangGraph → LangSmith

| 天  | 模块           | 交付物                                                     | 学习目标                      |
| :-: | -------------- | ---------------------------------------------------------- | ----------------------------- |
| 11  | LCEL 深入      | RunnablePassthrough, RunnableParallel, Chain 组合          | LangChain Expression Language |
| 12  | 执行器抽象     | BaseExecutor 抽象类, ProcessExecutor 基础实现              | Python ABC, subprocess        |
| 13  | pytest 执行器  | 调用 pytest 捕获输出, 解析 JUnit XML → TestResult          | pytest CLI, XML 解析          |
| 14  | vitest 执行器  | 调用 vitest, 解析 JSON 输出 → 归一化 TestResult            | vitest CLI, JSON 解析         |
| 15  | LangGraph 入门 | StateGraph, Node, Edge, 状态传递, 简单图 A→B→C             | LangGraph 核心概念            |
| 16  | 变更检测       | 加载旧 snapshot → 对比新扫描 → 输出 added/modified/deleted | diff 算法, 文件比对           |
| 17  | run_graph 搭建 | detect_changes → run_affected → analyze_results, 条件分支  | LangGraph 条件边              |
| 18  | 执行器集成     | run_graph 调用 executor, 聚合结果, 输出报告                | Graph + Tool 集成             |
| 19  | LangSmith 接入 | 配置 LangSmith, run_graph 全链路追踪, trace 调试           | LangSmith Tracing, Debug      |
| 20  | Sprint 回顾    | `test-assistant run` 端到端验证, 学习总结 → lessons.md     | 回顾反思                      |

**v0.2 完成标志**：

```
$ test-assistant run
✓ 变更检测: 3 个文件变更
  - src/user.ts (modified)
  - src/api/user.ts (modified)
  - src/utils/helper.ts (added)
→ 执行受影响测试...
  ✓ test/user.test.ts (2 passed)
  ✓ test/api/user.test.ts (1 passed)
  ✗ test/utils/helper.test.ts (1 failed)
→ 分析完成: 4 passed, 1 failed
```

---

### v0.3：LLM 测试生成（Day 21-30）

**学习主线**：AST 分析 → LangChain Tool → Agent → Prompt Engineering

| 天  | 模块             | 交付物                                           | 学习目标                                  |
| :-: | ---------------- | ------------------------------------------------ | ----------------------------------------- |
| 21  | 源码分析器       | Python AST 解析, TS/JS 函数签名提取              | AST 遍历, 源码分析                        |
| 22  | LangChain Tool   | 把分析器包装为 Tool, Tool 输入输出规范           | Tool 概念, Tool 规范                      |
| 23  | Agent 入门       | ReAct Agent, Agent 调用 Tool 多步推理            | Agent, ReAct 模式                         |
| 24  | 单元测试生成器   | 根据函数签名生成 pytest/vitest 测试代码          | PromptTemplate, 代码生成                  |
| 25  | Agent + 生成集成 | Agent 分析代码→决定测试类型→生成→写入 .autotest/ | Agent + Tool 编排                         |
| 26  | `plan` 命令      | 查看待生成测试方案, 按类型/文件分组, 表格输出    | Click 表格输出, 数据展示                  |
| 27  | 用户确认流程     | CLI 交互式确认/拒绝/修改, 批量确认, 确认后执行   | CLI 交互设计 (questionary/prompt_toolkit) |
| 28  | lessons.md 学习  | 从失败记录模式, 结构设计, 下轮生成引用           | Few-shot, 持续学习                        |
| 29  | e2e 生成扩展     | Playwright 测试生成, 页面交互分析                | Playwright 基础                           |
| 30  | Sprint 回顾      | `plan → 确认 → 生成 → 执行` 全流程, 总结         | 回顾反思                                  |

**v0.3 完成标志**：

```
$ test-assistant plan
📋 待生成测试方案
  单元测试 (3)
    - src/user.ts → user.test.ts [待确认]
    - src/api/order.ts → order.test.ts [待确认]
    - src/utils/format.ts → format.test.ts [待确认]
  > 确认全部? [Y/n] Y
  ✓ 正在生成 3 个测试...
  ✓ 正在执行...
  ✓ 3 passed, 0 failed
```

---

### v0.4：Web Dashboard（Day 31-40）

**学习主线**：FastAPI → SQLAlchemy → React → Ant Design → WebSocket

| 天  | 模块             | 交付物                                                 | 学习目标                   |
| :-: | ---------------- | ------------------------------------------------------ | -------------------------- |
| 31  | FastAPI 入门     | FastAPI 骨架, REST 路由, Pydantic models               | FastAPI, Pydantic          |
| 32  | 项目管理 API     | GET/POST /api/projects, GET /api/projects/{id}, SQLite | FastAPI CRUD, SQLAlchemy   |
| 33  | 运行/计划 API    | POST run, GET plan, PUT test-cases, SQLite 复杂查询    | FastAPI 复杂路由, 关联查询 |
| 34  | WebSocket        | WS /ws/executions/{plan_id}, 后端推送执行日志          | WebSocket, asyncio         |
| 35  | React 项目初始化 | Vite + React + TS + Ant Design, 组件基础               | Vite, TSX, React 组件      |
| 36  | Dashboard 页面   | 项目健康卡片, 快捷操作, Ant Card/Button/Statistic      | Ant Design 布局组件        |
| 37  | PlanEditor 页面  | 用例表格 (Ant Table), 类型 Tab (Tabs), 批量操作        | Ant Table, 状态管理        |
| 38  | 前后端联调       | fetch 调 API, 错误/加载/空状态处理                     | 前后端联调, 状态管理       |
| 39  | 执行看板 + 报告  | WebSocket 实时日志, 报告详情, Ant Charts 趋势图        | WS 客户端, 图表组件        |
| 40  | Sprint 回顾      | `test-assistant serve` → 浏览器全流程, 总结            | 回顾反思                   |

**v0.4 完成标志**：

```
$ test-assistant serve
✓ Web Dashboard → http://localhost:8080
```

浏览器打开能看到项目总览、测试方案编辑、实时执行日志、报告详情。
等到 v0.3/v0.4 核心功能完成后，再加一层薄薄的 MCP 包装，让 Claude 也能调用 test-assistant 的能力——这样两个都有

---

### v1.0：打磨完善（Day 41-50）

**学习主线**：watch 模式 → 报告 → 工程化 → 发布

| 天  | 模块         | 交付物                                               | 学习目标           |
| :-: | ------------ | ---------------------------------------------------- | ------------------ |
| 41  | watch 模式   | 文件监听 (watchdog), 变更自动触发执行                | 事件驱动, watchdog |
| 42  | HTML 报告    | 报告模板, 统计图表 + 失败详情, `report` 命令         | 报告生成, 模板引擎 |
| 43  | 多项目支持   | 绑定/切换/管理多项目, 项目列表/状态概览              | 多项目管理         |
| 44  | 错误处理强化 | 网络超时, LLM 限流, 无测试框架, 全面兜底             | 健壮性设计         |
| 45  | 自测试       | 用 test-assistant 测试 test-assistant 自身, 补充用例 | 元测试, 覆盖率     |
| 46  | CLI 体验打磨 | 彩色输出, 进度条, --help 完善                        | CLI UX 设计        |
| 47  | 文档编写     | README, 快速开始, API 文档                           | 技术文档           |
| 48  | 性能优化     | 大项目优化, 并发执行, 缓存                           | 性能分析           |
| 49  | 发布准备     | PyPI 配置, CI/CD, CHANGELOG                          | 发布流程           |
| 50  | 项目复盘     | 功能完整验收, Agent 开发能力总结, 下一步规划         | 全局回顾           |

**v1.0 完成标志**：

```
$ test-assistant init --mode bootstrap my-new-project
$ test-assistant watch
  监听中... (文件变更自动触发测试)
$ test-assistant report --format html
✓ 报告已导出: report-2026-08-28.html
$ pip install test-assistant  # 发布到 PyPI
```

## 学习规划

### 学习路径全景图

```
第1周                 第5周                 第10周
├──Click─────────────┤                      Python CLI 精通
│   ├──Python 工程化─┤                      工程化基础
│       ├──LC Core───┤                      能调 LLM
│           ├──LCEL──┤                      链式组合
│               ├──LangGraph────────┤       能编排多步流程
│                   ├──LangSmith────┤       能调试追踪
│                       ├──Tool─────┤
│                           ├──Agent────────┤  能独立开发 Agent 🎯
│                               ├──FastAPI─┤    Python Web
│                                   ├──React──────┤ 前端开发
│                                       ├──Ant Design─┤
│                                           ├──WebSocket─┤
│                                               ├──工程化──┤
│                                                   ├──发布──┤
```

### 模块 → 技能映射表

#### LangChain 生态学习地图

| 版本         | 模块             | 练习的技能                                                         | 掌握程度                     |
| ------------ | ---------------- | ------------------------------------------------------------------ | ---------------------------- |
| v0.1 Day 7-8 | init 中 LLM 调用 | ChatModel, PromptTemplate, StrOutputParser, StructuredOutputParser | 能写最简单的 LLM 调用链      |
| v0.2 Day 11  | 执行器组合       | LCEL: RunnablePassthrough, RunnableParallel, chain 组合            | 能组合多个链                 |
| v0.2 Day 15  | run_graph        | StateGraph, Node, Edge, 状态传递                                   | 能搭简单有向图               |
| v0.2 Day 17  | 条件分支         | conditional_edge, 路由函数                                         | 能搭分支图                   |
| v0.2 Day 19  | 全链路追踪       | LangSmith project, trace, run 调试                                 | 能通过 trace 调试            |
| v0.3 Day 22  | Tool 包装        | @tool, Tool 规范, 输入输出 schema                                  | 能把任意函数包装为 Tool      |
| v0.3 Day 23  | ReAct Agent      | create_react_agent, AgentExecutor                                  | 能搭 Tool-use Agent          |
| v0.3 Day 25  | Agent 编排       | Agent 调用多个 Tool 完成复杂任务                                   | 能设计多 Tool Agent          |
| v0.3 Day 28  | 持续学习         | Few-shot prompt, lessons 注入                                      | 能让 Agent 从经验学习        |
| v0.3 整体    | 测试生成         | 代码生成, 结构化输出, 质量验证                                     | **能独立构建代码生成 Agent** |

> **v0.3 完成后**：你已经具备了用 LangChain + LangGraph + LangSmith 构建 Agent 级应用的能力。后续 v0.4/v1.0 是 React 和工程化能力的补全。

#### React 生态学习地图

| 版本        | 模块            | 练习的技能                            | 掌握程度             |
| ----------- | --------------- | ------------------------------------- | -------------------- |
| v0.4 Day 35 | 项目 init       | Vite + React + TS 项目搭建, TSX 语法  | 能初始化 React 项目  |
| v0.4 Day 35 | 组件基础        | Function Component, Props, JSX        | 能写简单组件         |
| v0.4 Day 36 | Ant Design 入门 | Card, Button, Statistic, Layout, 布局 | 能搭企业级 UI 页面   |
| v0.4 Day 37 | 数据表格        | Ant Table, Tabs, 状态管理 (useState)  | 能展示和操作列表数据 |
| v0.4 Day 37 | React Router    | BrowserRouter, Route, Link, useParams | 能搭 SPA 路由        |
| v0.4 Day 38 | 前后端联调      | fetch, useEffect, 错误/加载/空状态    | 能对接 REST API      |
| v0.4 Day 39 | WebSocket       | WebSocket 客户端, 实时数据流          | 能处理实时通信       |
| v0.4 Day 39 | 图表            | Ant Charts / ECharts, 趋势图          | 能可视化数据         |
| v1.0 Day 46 | 前端工程化      | 构建优化, 打包, 部署                  | 能独立部署前端应用   |

### 学习进展验收标准

每个 Sprint 结束时，你应该能回答以下问题：

**v0.1 结束后**：

- 我能用 Click 写一个多命令 CLI 工具吗？
- 我能在 Python 中调用 LLM API 并解析结构化输出吗？
- 我能读写文件、遍历目录、计算 hash 吗？

**v0.2 结束后**：

- 我能用 LCEL 组合多个 Runnable 吗？
- 我能用 LangGraph 搭一个有条件分支的工作流吗？
- 我能用 LangSmith 追踪和调试链的执行吗？

**v0.3 结束后**：

- 我能把任意函数包装成 LangChain Tool 吗？
- 我能搭建一个 ReAct Agent 来自主完成多步任务吗？← **核心里程碑**
- 我能用 Few-shot 让 Agent 从经验中学习吗？

**v0.4 结束后**：

- 我能用 FastAPI 写 REST API + WebSocket 吗？
- 我能用 React + Ant Design 搭一个完整的管理后台吗？
- 我能实现前后端联调和实时数据推送吗？

**v1.0 结束后**：

- 我能独立从零开发一个 CLI + Web 的全栈 Agent 工具吗？
- 我能发布一个 Python 包到 PyPI 吗？
- 我能编写生产级的技术文档吗？

## 数据存储

| 数据           | 存储方式                               |
| -------------- | -------------------------------------- |
| 绑定项目元信息 | SQLite (本地数据库)                    |
| 文件结构快照   | `.autotest/snapshot.json` (JSON 文件)  |
| 测试用例代码   | `.autotest/test_cases/` (实际代码文件) |
| 历史执行记录   | `.autotest/history.db` (SQLite)        |
| 用户配置       | `.autotest/config.yml` (YAML)          |
| AI 学习记录    | `.autotest/lessons.md` (Markdown)      |
