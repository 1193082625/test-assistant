"""符号与依赖分析"""

import ast
from ast import NodeVisitor
from pathlib import Path

from core.models import SourceSymbol, SymbolKind, ImportReference, TestabilityStatus, TestabilityAssessment

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

def classify_symbol_testability(symbol: SourceSymbol) -> TestabilityAssessment:
    """根据符号上下文判断是否可直接测试"""
    if symbol.kind is SymbolKind.CLASS:
        return TestabilityAssessment(
            symbol=symbol,
            status=TestabilityStatus.NOT_DIRECT,
            reasons=[
                "类本身不是可直接执行的测试入口"
            ],
        )

    if symbol.kind is SymbolKind.FUNCTION and symbol.parent_qualified_name is not None:
        return TestabilityAssessment(
            symbol=symbol,
            status=TestabilityStatus.NOT_DIRECT,
            reasons=["嵌套函数不能通过模块路径直接导入"]
        )

    if symbol.name.startswith("_"):
        return TestabilityAssessment(
            symbol=symbol,
            status=TestabilityStatus.NOT_DIRECT,
            reasons=["私有符号默认不作为直接测试入口"]
        )

    if symbol.side_effects:
        return TestabilityAssessment(
            symbol=symbol,
            status=TestabilityStatus.NEEDS_ISOLATION,
            reasons=[
                f"符号包含 {effect} 副作用，需要隔离后测试"
                for effect in symbol.side_effects
            ]
        )

    return TestabilityAssessment(
        symbol=symbol,
        status=TestabilityStatus.DIRECT,
    )

def resolve_import_module(reference: ImportReference, current_module: str, current_is_package: bool = False) -> str:
    """将导入引用解析成绝对模块名"""
    if reference.relative_level == 0:
        return reference.module

    current_parts = current_module.split(".")

    if current_is_package:
        package_parts = current_parts
    else:
        # [1, 2, 3] --> [1, 2]
        package_parts = current_parts[:-1]

    levels_up = reference.relative_level - 1

    if levels_up >= len(package_parts):
        raise ValueError(
            "相对导入超出顶层包： "
            f"module={current_module}，"
            f"level={reference.relative_level}"
        )
    if levels_up == 0:
        resolved_paths = list(package_parts)
    else:
        resolved_paths = package_parts[:levels_up]

    if reference.module:
        resolved_paths.extend(reference.module.split("."))

    return ".".join(resolved_paths)

def extract_python_imports(source: str) -> list[ImportReference]:
    """提取 Python 导入，保留别名和相对层级"""
    tree = ast.parse(source)

    import_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]

    import_nodes.sort(
        key=lambda node: (node.lineno, node.col_offset)
    )

    references = []

    for node in import_nodes:
        if isinstance(node, ast.Import):
            for imported in node.names:
                references.append(
                    ImportReference(
                        module=imported.name,
                        alias=imported.asname,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for imported in node.names:
                references.append(
                    ImportReference(
                        module=module,
                        imported_name=imported.name,
                        alias=imported.asname,
                        relative_level=node.level,
                    )
                )

    return references

def resolve_python_module_name(file_path: str, project_root: str) -> str:
    """根据项目根目录计算 Python 模块名"""
    source_path = Path(file_path).resolve()
    root_path = Path(project_root).resolve()

    relative_path = source_path.relative_to(root_path)
    # 把路径拆成 ("src", "acme", "services", "user.py")
    # 转换成列表 是因为 元组不能修改
    parts = list(relative_path.parts)

    # src 是源码根目录，不属于 Python 模块名
    if parts and parts[0] == "src":
        parts = parts[1:]

    if not parts or not parts[-1].endswith(".py"):
        raise ValueError(
            f"不是 Python 源文件：{file_path}"
        )

    # 取相对路径最后面的 Python 文件名，并把它包装成 Path
    # 方便安全取得文件名和不带扩展名的模块名
    module_file = Path(parts[-1])

    # acmes/services/__init__.py -->  acmes/services
    if module_file.name == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = module_file.stem # 获取不带扩展名的文件名

    return ".".join(parts)

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
                signature=_build_class_signature(node),
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

def _get_call_name(node: ast.expr) -> str | None:
    """辅助函数： 把调用目标还原成带层级的名称"""
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent_name = _get_call_name(node.value)

        if parent_name is None:
            return None

        return f"{parent_name}.{node.attr}"

    return None

class _FunctionSideEffectVisitor(ast.NodeVisitor):
    """检测单个函数自身的副作用，不进入嵌套函数或嵌套类"""
    def __init__(self) -> None:
        self.effects: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _get_call_name(node.func)

        if call_name == "open":
            self.effects.add("filesystem")

        if call_name in {
            "subprocess.run",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
            "subprocess.Popen",
        }:
            self.effects.add("subprocess")

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

def _detect_function_side_effects(node: FunctionNode) -> list[str]:
    visitor = _FunctionSideEffectVisitor()

    for statement in node.body:
        visitor.visit(statement)

    return  sorted(visitor.effects)


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
        side_effects=_detect_function_side_effects(node),
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

def _build_class_signature(node: ast.ClassDef) -> str:
    """生成包含基类和关键字参数的类签名"""
    arguments = [
        ast.unparse(base)
        for base in node.bases
    ]
    # 之所以同时处理 node.keywords 是为了支持 class Model(Base, metaclass=ModelMeta):... 以及少见但合法的 class Model(**class_options):...
    for keyword in node.keywords:
        # 当 keyword.arg is None 时，表示它来自 **class_options
        if keyword.arg is None:
            arguments.append(
                f"**{ast.unparse(keyword.value)}"
            )
        else:
            arguments.append(
                f"{keyword.arg}="
                f"{ast.unparse(keyword.value)}"
            )

    if not arguments:
        return f"class {node.name}"

    return (
        f"class {node.name}"
        f"({', '.join(arguments)})"
    )