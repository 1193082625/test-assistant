"""
扫描 Python 项目并输出函数列表的分析器
输入：项目路径 → 扫描 .py 文件 → AST 解析 → 输出函数签名列表

收集函数签名是为了让 LLM 知道被测项目里有什么函数，从而生成有针对性、有意义的测试代码
"""

import os
import ast
from dataclasses import dataclass

@dataclass
class FunctionInfo:
    name: str
    params: list[str] # ["a: int", "b: int"]
    return_type: str
    file_path: str # 源文件路径
    line_number: int # 文件中的行号，方便定位

def _extract_type(node)-> str:
    """从类型注解节点提取类型名字符串"""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id

    # 暂时只处理 Name， 后续加 Attribute, Subscript
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
            tree = ast.parse(f.read())
        except SyntaxError:
            return []

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
                all_functions.extend(analyze_python_file(file_path))

    return all_functions

if __name__ == "__main__":
    # result = analyze_python_file(__file__)
    result = analyze_python_project("/Users/wangyue/Desktop/work/test-assistant/core/analyzers")
    for func in result:
        print(f"{func.name}({', '.join(func.params)}) -> {func.return_type}")