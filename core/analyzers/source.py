"""符号与依赖分析"""

import ast
from importlib.util import source_hash
from pathlib import Path

from core.models import SourceSymbol, SymbolKind

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

def analyze_python_symbols(file_path: str, module_name: str) -> list[SourceSymbol]:
    """分析 Python 文件中的顶层源码符号"""
    source_path = Path(file_path)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    visitor = _SourceSymbolVisitor(
       file_path=str(source_path),
       module_name=module_name
    )
    visitor.visit(tree)

    return visitor.symbols

"""
ast.NodeVisitor ： NodeVisitor 会根据节点类型自动寻找对应方法:
比如 遇到 ClassDef -> 调用 visit_ClassDef()
入口是 visitor.visit(tree)
"""
class _SourceSymbolVisitor(ast.NodeVisitor):
    """
    是analyze_python_symbols 内部使用的 AST 遍历器
    任务是：按照源码的嵌套结构访问类和函数，同时记住当前处于哪个类、哪个函数中
    在遍历 AST 时保存类和函数上下文
    append() 表示进入上下文，pop() 标识退出上下文
    """

    def __init__(self, file_path: str, module_name: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.symbols: list[SourceSymbol] = []

        self._qualified_stack: list[str] = [] # qualified 表示限定的【包含它所属的模块、类和外层函数】、带完整上下文的
        self._kind_stack: list[SymbolKind] = []
        self._class_stack: list[str] = []

    def _current_parent(self) -> str | None:
        if not self._qualified_stack:
            return None
        return self._qualified_stack[-1]

    # 负责处理类本身
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        parent = self._current_parent()

        if parent is None:
            qualified_name = f"{self.module_name}.{node.name}"
        else:
            qualified_name = f"{parent}.{node.name}"

        self.symbols.append(
            SourceSymbol(
                name=node.name,
                qualified_name=qualified_name,
                kind=SymbolKind.CLASS,
                file_path=self.file_path,
                signature=f"class {node.name}",
                start_line=_node_start_line(node),
                end_line=node.end_lineno or node.lineno,
                parent_qualified_name=parent,
                decorators=[
                    ast.unparse(decorator)
                    for decorator in node.decorator_list
                ]
            )
        )

        self._qualified_stack.append(qualified_name)
        self._kind_stack.append(SymbolKind.CLASS)
        self._class_stack.append(node.name)

        # 会继续访问类里面的子节点，包括方法
        self.generic_visit(node)

        self._class_stack.pop()
        self._kind_stack.pop()
        self._qualified_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_function(node)

    def visit_function(self, node: FunctionNode) -> None:
        parent = self._current_parent()

        is_direct_class_child = (
            bool(self._kind_stack)
            and self._kind_stack[-1] == SymbolKind.CLASS
        )

        kind = SymbolKind.METHOD if is_direct_class_child else SymbolKind.FUNCTION

        owner_class = self._class_stack[-1] if self._class_stack else None

        symbol = _build_function_symbol(
            node=node,
            file_path=self.file_path,
            module_name=self.module_name,
            kind=kind,
            owner_class=owner_class,
            parent_qualified_name=parent,
        )
        self.symbols.append(symbol)
        self._qualified_stack.append(symbol.qualified_name)
        self._kind_stack.append(kind)
        self.generic_visit(node)
        self._kind_stack.pop()
        self._qualified_stack.pop()

# 函数前面加 _ 表示这是模块内部实现细节，不建议其他模块直接使用
def _node_start_line(node: ast.ClassDef | FunctionNode) -> int:
    """装饰器存在时，从第一个装饰器开始"""
    decorator_lines = [decorator.lineno for decorator in node.decorator_list]

    if decorator_lines:
        return min(
            node.lineno,
            *decorator_lines,
        )

    return node.lineno

def _build_function_symbol(
        node: FunctionNode,
        file_path: str,
        module_name: str,
        kind: SymbolKind,
        owner_class: str | None = None,
        parent_qualified_name: str | None = None,
) -> SourceSymbol:
    if parent_qualified_name is None:
        qualified_name = f"{module_name}.{node.name}"
    else:
        qualified_name = f"{parent_qualified_name}.{node.name}"

    return SourceSymbol(
        name=node.name,
        qualified_name=qualified_name,
        kind=kind,
        file_path=file_path,
        signature=_build_function_signature(node),
        start_line=_node_start_line(node),
        end_line=node.end_lineno or node.lineno,
        owner_class=owner_class,
        parent_qualified_name=parent_qualified_name,
        decorators=[
            ast.unparse(decorator) for decorator in node.decorator_list
        ],
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )

def _build_function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    """从函数节点生成可读签名"""
    async_prefix = (
        "async "
        if isinstance(node, ast.AsyncFunctionDef)
        else ""
    )

    arguments = ast.unparse(node.args)
    return_annotation = ""
    if node.returns is not None:
        return_annotation = (
            f" -> {ast.unparse(node.returns)}"
        )

    return (
        f"{async_prefix}{node.name}"
        f"({arguments})"
        f"{return_annotation}"
    )
