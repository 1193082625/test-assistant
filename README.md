## `test-assistant` 的核心流程可以简化为:

`test-assistant` 的核心流程可以先简化为：


```mermaid
flowchart LR
    A["目标项目目录"] --> B["项目检测"]
    B --> C["生成测试方案"]
    C --> D["生成候选测试"]
    D --> E["验证候选测试"]
    E --> F["用户确认"]
    F --> G["执行测试"]
    G --> H["判断失败原因"]
```


## 项目的代码地图

```text
cli/
  commands/
    init.py              用户执行 init 的入口
    run.py               用户执行测试的入口

core/
  models/                业务概念和合法值
    enums.py             项目类型、语言、测试框架
    project.py           FrameworkInfo

  analyzers/
    framework.py         读取目标项目并判断它是什么项目
    snapshot.py          记录文件状态
    source_analyzer.py   分析 Python 函数和类

  generators/
    test_generator.py    调用 LLM 生成测试

  executors/
    pytest_executor.py   执行 pytest
    vitest_executor.py   执行 vitest

  graphs/
    run_graph.py         把检测、生成和执行串联起来
```

## 项目检测的完整数据流

**当前检测流程可以概括为：**

```
扫描目录
→ 选择标志文件
→ 读取文件
→ 根据标志与依赖初步分类
→ 生成 ProjectInfo
→ 提取框架、测试框架、构建工具
→ 生成 FrameworkInfo
→ 包装为 AnalyzeInfo
```

**异常流程是：**

```
解析失败
→ ProjectDetectionError 或 PARSER_ERRORS
→ unknown_analysis
→ 返回可解释的 AnalyzeInfo
```



假设目录是：

```
demo/
├── frontend/
│   └── package.json
├── backend/
│   └── pyproject.toml
└── broken-worker/
    └── package.json
```

执行：

```
analysis = analyze_project_modules("/demo")
```


流程为：
```mermaid
flowchart TD
    A["analyze_project_modules"] --> B["os.walk 扫描全部目录"]
    B --> C["detect_project_type"]
    C --> D["ProjectInfo"]
    D --> E["build_framework_info"]
    E --> F["FrameworkInfo"]
    F --> G["ProjectModule"]
    G --> H["ProjectAnalysis.modules"]

    C -->|ProjectDetectionError| I["unknown ProjectModule"]
    E -->|PARSER_ERRORS| I
    I --> J["ProjectAnalysis.warnings"]
```


最终结果类似：

```
ProjectAnalysis(
    root_path="/demo",
    modules=[
        ProjectModule(
            root_path="/demo/frontend",
            source_file="package.json",
            framework_info=FrameworkInfo(
                project_type=ProjectType.FRONTEND,
                language=Language.TYPESCRIPT,
            ),
        ),
        ProjectModule(
            root_path="/demo/backend",
            source_file="pyproject.toml",
            framework_info=FrameworkInfo(
                project_type=ProjectType.BACKEND,
                language=Language.PYTHON,
            ),
        ),
        ProjectModule(
            root_path="/demo/broken-worker",
            source_file="package.json",
            framework_info=FrameworkInfo(),
        ),
    ],
    warnings=[
        "broken-worker/package.json 解析失败：...",
    ],
)
```

计算整体类型时：

```
known_types = {
    ProjectType.FRONTEND,
    ProjectType.BACKEND,
}
```

unknown 模块被忽略，因此：

```
analysis.primary_type is ProjectType.MIXED
```



## ProjectInfo 和 FrameworkInfo 有什么区别

这是目前最容易混淆的地方。

### ProjectInfo：检测过程中的中间结果

```
ProjectInfo(
    project_type=ProjectType.BACKEND,
    language=Language.JAVASCRIPT,
    source_file="package.json",
    target_analysis="json",
    file_content="...",
)
```

它表达：

> 我通过哪个文件，初步判断这是什么项目，并保留后续解析需要的原始内容。

其中：

- `source_file`：依据来自哪个文件；
- `target_analysis`：应该用什么解析器；
- `file_content`：标志文件原始内容。

### FrameworkInfo：最终标准化结果

```
FrameworkInfo(
    project_type=ProjectType.BACKEND,
    language=Language.JAVASCRIPT,
    frameworks=["Express"],
    test_frameworks=[TestFramework.VITEST],
)
```

它表达：

> 完整分析后，这个项目具有什么属性。

可以记成：

```
ProjectInfo   = 检测过程中的证据
FrameworkInfo = 检测完成后的结论
```
