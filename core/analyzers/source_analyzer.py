"""
扫描 Python 项目并输出函数列表的分析器
输入：项目路径 → 扫描 .py 文件 → AST 解析 → 输出函数签名列表

收集函数签名是为了让 LLM 知道被测项目里有什么函数，从而生成有针对性、有意义的测试代码
"""

import os
import ast
import re
from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    name: str
    params: list[str] # ["a: int", "b: int"]
    return_type: str
    file_path: str # 源文件路径
    line_number: int # 文件中的行号，方便定位
    body_source: str = "" # 函数源码全文（含 def 行）
    imports: list = field(default_factory=list) # 文件级 import 语句

def _extract_type(node)-> str:
    """从类型注解节点提取类型名字符串"""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id

    # 暂时只处理 Name， 后续加 Attribute, Subscript
    return ""

def _extract_imports(tree: ast.Module) -> list[str]:
    """从 AST 中提取所有 import 语句"""
    imports = []
    # iter_child_nodes 只遍历顶层
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]

            if node.level: # 相对导入 如 form . import XXX
                imports.append(f"from {'%s' % ('.' * node.level)}{module} import {', '.join(names)}")
            else:
                imports.append(f"from {module} import {', '.join(names)}")
    return imports

def _extract_class_name(class_source: str) -> str:
    """从 class 源码中提取类名"""
    match = re.search(r"class (\w+)", class_source)
    return match.group(1) if match else ""

def get_class_def_from_import(project_path: str, import_str: str) -> str:
    """根据from 引用 获取 对应函数的源码"""
    search_result = re.search(r"from ([\w.]+) import ([\w.]+)", import_str)
    file_path = "/".join(search_result.group(1).split(".")) + ".py" if search_result else ""
    import_name = search_result.group(2) if search_result else ""
    source_code = ""
    if file_path:
        file_full_path = os.path.join(project_path, file_path)
        if not os.path.isfile(file_full_path): # 文件不存在说明是 stdlib 或第三方
            return "" # 跳过，不给 prompt 加上下文
        with open(file_full_path, "r", encoding="utf-8") as f:
            file_source = f.read()
            file_source_lines = file_source.splitlines(keepends=True)
            tree = ast.parse(file_source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == import_name:
                        source_lines = file_source_lines[node.lineno - 1 : node.end_lineno]
                        source_code = "".join(source_lines)
                if isinstance(node, ast.ClassDef):
                    source_lines = file_source_lines[node.lineno - 1 : node.end_lineno]
                    node_name = _extract_class_name("\n".join(source_lines))
                    if node_name == import_name:
                        source_code = "".join(source_lines)

        return source_code

    return ""

def analyze_python_file(file_path: str) -> list[FunctionInfo]:
    """
    解析一个 Python 文件，提取所有函数签名
    1. 处理 def func() -- 无类型注解的函数
    2. 处理 async def func() -- 异步函数
    3. 处理 @property、@staticmethod 等装饰器
    4. 跳过 test_ 开头的函数
    """
    # 获取函数列表
    if not os.path.isfile(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            source = f.read()
            tree = ast.parse(source)
        except SyntaxError:
            return []

    # 按行拆开（保留换行符）
    source_lines = source.splitlines(keepends=True)
    # 提取 imports
    file_imports = _extract_imports(tree)

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 用行号切出函数源码片段
            # AST 的行号从 1 开始计数，而 Python list 从 0 开始
            body_lines = source_lines[node.lineno - 1: node.end_lineno]
            body_source = "".join(body_lines)
            # # 取装饰器
            # decorators = []
            # for decorator in node.decorator_list:
            #     decorators.append(decorator.id)

            params = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg_str in ("self", "cls"):
                    continue
                type_str = _extract_type(arg.annotation)
                if type_str:
                    arg_str += f": {type_str}"
                params.append(arg_str)

            #  取返回值类型
            return_type = _extract_type(node.returns)

            functions.append(FunctionInfo(
                name=node.name,
                params=params,
                return_type=return_type,
                file_path=file_path,
                line_number=node.lineno,
                body_source=body_source,
                imports=file_imports,
            ))
    return functions

def analyze_python_project(project_path: str) -> list[FunctionInfo]:
    """遍历项目下的所有 .py 文件，收集函数签名"""
    from core.analyzers.framework import EXCLUDE_DIRS

    all_functions = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                functions = analyze_python_file(file_path)
                all_functions.extend(functions)

    return all_functions

if __name__ == "__main__":
    # result = analyze_python_file(__file__)
    result = analyze_python_project("/Users/wangyue/Desktop/work/test-assistant/core/analyzers")
    for func in result:
        print(f"{func.name}({', '.join(func.params)}) -> {func.return_type}")