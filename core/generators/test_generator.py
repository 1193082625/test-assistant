"""
LLM 驱动的测试代码生成器

prompt 模板 + 生成逻辑

expert: 专家 、extract: 提炼，获取，得到
prompt 设计（核心环节）：
- System: "You are a Python test generation expert",
- Context: file_path, imports, function_source
- Guidelines: pytest 风格、happy path + edge case 、 正确 import
- Output: 只输出一个 markdown python 代码块
"""
import os
import re

from core.llm.client import LLMClient
from core.analyzers.source_analyzer import analyze_python_file, get_class_def_from_import

# 让 LLM 理解逻辑、了解依赖、知道代码和数据结构
UNIT_TEST_PROMPT = """You are a Python test generation expert. Generate pytest unit tests for the following Python function.

source file: {file_path}
File imports:
{imports}

Functions to test:
```python
{function_source}
```

Requirements:
1. Use pytest style (assert statements, not unittest.TestCase)
2. Cover: happy path, edge cases, error cases
5. Only output the test code in a single ```python code block```
6. Do NOT include any text outside the code block
7. If the source file use Click (@click.command or @click.group), use `from click.testing import CliRunner` to test CLI commands, don't call the function directly.
"""

def _extract_python_code(llm_output: str) -> str:
    """从 LLM 回复中提取 python ... 代码块"""
    match = re.search(r"```python\n(.*?)```", llm_output, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 没有代码块标记时，尝试直接当 Python 代码处理
    return llm_output.strip()

def _get_module_path(file_path: str, project_path: str) -> str:
    """从文件路径转成 Python 模块导入路径"""
    rel_path = os.path.relpath(file_path, project_path)
    # 去掉 .py 后缀，把 / 换成 .
    module_path = rel_path.replace(os.sep, ".").replace("/", ".").removesuffix(".py")
    return module_path

def generate_tests_for_file(file_path: str, output_dir: str, project_path: str | None = None) -> str | None:
    """
    对单个 .py 文件生成测试
    1. 调用 analyze_python_file() 获取 FunctionInfo
    2. 过滤 test_ 开头的函数
    3. 构建 prompt 上下文
    4. 调 LLMClient invoke_template
    5. 从 markdown 代码块提取 Python 代码
    6. 写入 output_dir/test_{basename}.py
    7. 返回生成的文件路径（或 None）
    """
    functions = analyze_python_file(file_path)
    # 过滤掉 test_ 开头的函数
    target_funcs = [f for f in functions if not f.name.startswith("test_")]
    if not target_funcs:
        return None

    # 如果文件 import 了 click，跳过测试生成（CliRunner 容易产生副作用）
    if any(kw in imp for func in target_funcs for imp in func.imports for kw in ("click", "langgraph")):
        print(f"  → 跳过 Click CLI 文件: {os.path.basename(file_path)}")
        return None

    # 取第一个函数的信息作为 prompt 上下文
    functions_context = ""
    import_str = ""
    for i, func in enumerate(target_funcs, 1):
        functions_context += f"{i}. Function: {func.name}\n"
        functions_context += f"```python\n{func.body_source}```\n\n"

    func = target_funcs[0]
    import_str += "\n".join(func.imports) if func.imports else "# (no imports)"
    module_path = _get_module_path(file_path, project_path) if project_path else ""

    for import_ in func.imports:
        import_source_code = get_class_def_from_import(project_path,import_)
        if import_source_code:
            import_str += f"```python\n{import_source_code}```\n\n"

    try:
        print(f"  → LLM 生成测试: {os.path.basename(file_path)}...", end="", flush=True)
        client = LLMClient(temperature=0.2)
        response = client.invoke_template(
            UNIT_TEST_PROMPT,
            file_path=file_path,
            imports=import_str,
            module_path=module_path,
            function_source=functions_context
        )
    except Exception as e:
        print(f"  ⚠ LLM 生成测试失败: {e}")
        return None

    test_code = _extract_python_code(response)

    # 写入测试文件
    base_name = os.path.basename(file_path)
    test_file_name = f"test_{base_name}"
    output_path = os.path.join(output_dir, test_file_name)

    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(test_code)
        f.write("\n")

    print(" ✓")
    return output_path

def generate_tests_for_project(project_path: str, changed_files: dict) -> list[str]:
    """
    对项目中变更的 .py 文件生成测试
    参数：
        project_path: 项目根路径
        changed_files: {"added": [...], "modified": [...], "deleted": [...]}

    返回：
        生成的文件路径列表
    """

    output_dir = os.path.join(project_path, ".autotest", "test_cases", "unit")
    generated = []

    for change_type in ("added", "modified"):
        for file_path in changed_files.get(change_type, []):
            if not file_path.endswith(".py"):
                continue
            if os.path.basename(file_path).startswith("test_"):
                continue
            if not os.path.isfile(file_path):
                continue

            result = generate_tests_for_file(file_path, output_dir, project_path)
            if result:
                generated.append(result)

    return generated
