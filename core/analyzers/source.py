"""符号与依赖分析"""

import ast
from pathlib import Path

from core.models import (
    SourceSymbol,
    SymbolKind,
    ImportReference,
    TestabilityStatus,
    TestabilityAssessment,
    TestIndexEntry,
    TestIndex
)

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

def filter_symbols_without_existing_tests(
        source_symbols: list[SourceSymbol],
        test_index: TestIndex,
) -> list[SourceSymbol]:
    """过滤已经存在直接测试映射的源码符号"""

    return [
        symbol
        for symbol in source_symbols
        if not test_index.has_tests_for(symbol.qualified_name)
    ]

def analyze_python_symbols(file_path: str, module_name: str) -> list[SourceSymbol]:
    """分析 Python 文件中的类、函数和方法符号"""
    source_path = Path(file_path)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    visitor = _SourceSymbolVisitor(
       file_path=str(source_path),
       module_name=module_name
    )
    visitor.visit(tree)

    return visitor.symbols

def analyze_python_test_symbols(file_path: str, module_name: str) -> list[SourceSymbol]:
    """提取 pytest 可以收集的测试函数符号"""

    symbols = analyze_python_symbols(file_path, module_name)

    return [
        symbol
        for symbol in symbols
        if (
            symbol.name.startswith("test_") # 要求名称符合 pytest 的测试函数规则
            and (
                symbol.parent_qualified_name is None # 是顶层测试函数
                or ( # 或者 Test 类中的测试方法，这样可以避免把嵌套函数误认为 pytest 测试
                    symbol.kind is SymbolKind.METHOD
                    and symbol.owner_class is not None
                    and symbol.owner_class.startswith("Test")
                )
            )
        )
    ]

def index_python_test_file(
        file_path: str,
        module_name: str,
        project_root: str,
        source_symbols: list[SourceSymbol],
) -> list[TestIndexEntry]:
    """
    建立一个 python 测试文件到源码符号的索引

    以以下测试为例
    # test_demo.py
    from demo import add
    def test_add() -> None:
        assert add(1, 2) == 3
    """
    test_path = Path(file_path) # 构造测试文件路径对象
    source = test_path.read_text(encoding="utf-8") # 读取测试文件内容
    tree = ast.parse(source) # 将测试文件内容解析成 ast 树

    # 获取源码符号（对应源码中的函数名称）
    # {"demo.add"}
    source_names = {
        symbol.qualified_name
        for symbol in source_symbols
    }
    callable_source_names = {
        symbol.qualified_name
        for symbol in source_symbols
        if symbol.kind is not SymbolKind.CLASS
    }

    imported_targets: dict[str, str] = {}
    imported_modules: dict[str, str] = {}

    # 遍历测试文件节点
    for node in tree.body:
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.asname is not None:
                    local_name = imported.asname
                    module_name_in_source = imported.name
                else:
                    local_name = imported.name.split(".")[0]
                    module_name_in_source = local_name

                imported_modules[local_name] = (
                    module_name_in_source
                )

        elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module is not None
        ):
            for imported in node.names:
                local_name = (
                        imported.asname
                        or imported.name
                )
                target_name = (
                    f"{node.module}.{imported.name}"
                )

                if _matches_source_or_owner(
                    target_name,
                    source_names,
                ):
                    imported_targets[local_name] = (
                        target_name
                    )

    setup_instance_bindings = (
        _collect_test_class_setup_bindings(
            tree=tree,
            imported_targets=imported_targets,
            imported_modules=imported_modules,
            source_names=source_names,
        )
    )

    # 按限定名保存pytest测试函数的AST节点
    # 既包含顶层测试函数，也包含 Test 类中的测试方法
    # 使用限定名可以避免不同测试类中的同名方法互相覆盖
    test_nodes = _collect_test_function_nodes(
        tree=tree,
        module_name=module_name,
    )

    # 保存稳定的领域模型，包含限定名、文件、行号
    test_symbols = analyze_python_test_symbols(
        file_path=file_path,
        module_name=module_name,
    )

    relative_test_path = (
        test_path.resolve()
        .relative_to(Path(project_root).resolve())
        .as_posix()
    )

    entries: list[TestIndexEntry] = []

    for test_symbol in test_symbols:
        test_node = test_nodes.get(test_symbol.qualified_name)

        if test_node is None:
            continue

        instance_bindings = dict(
            setup_instance_bindings.get(
                test_symbol.owner_class or "",
                {},
            )
        )
        instance_bindings.update(
            _collect_instance_bindings(
                node=test_node,
                imported_targets=imported_targets,
                imported_modules=imported_modules,
                source_names=source_names,
            )
        )

        call_names = _collect_function_calls(test_node)

        for call_name in call_names:
            target_name = _resolve_imported_call_target(
                call_name=call_name,
                imported_targets=imported_targets,
                imported_modules=imported_modules,
                source_names=callable_source_names,
            )

            if target_name is None:
                call_parts = call_name.split(".")
                if len(call_parts) >= 2:
                    receiver_name = ".".join(
                        call_parts[:-1]
                    )
                    owner_name = instance_bindings.get(
                        receiver_name
                    )
                    if owner_name is not None:
                        candidate_name = (
                            f"{owner_name}."
                            f"{call_parts[-1]}"
                        )
                        if (
                            candidate_name
                            in callable_source_names
                        ):
                            target_name = candidate_name

            if target_name is None:
                continue

            entries.append(
                TestIndexEntry(
                    source_qualified_name=target_name,
                    test_qualified_name=test_symbol.qualified_name,
                    test_file_path=relative_test_path,
                    test_line=test_node.lineno
                )
            )

    return sorted(entries, key=lambda entry: (
        entry.source_qualified_name,
        entry.test_qualified_name,
        entry.test_file_path,
        entry.test_line,
    ))


def _matches_source_or_owner(
    qualified_name: str,
    source_names: set[str],
) -> bool:
    """判断名称是源码符号或源码方法的所属对象。"""
    return (
        qualified_name in source_names
        or any(
            source_name.startswith(
                f"{qualified_name}."
            )
            for source_name in source_names
        )
    )


def _resolve_imported_call_target(
    *,
    call_name: str,
    imported_targets: dict[str, str],
    imported_modules: dict[str, str],
    source_names: set[str],
) -> str | None:
    """把导入后的本地调用名解析为源码限定名。"""
    call_parts = call_name.split(".")

    imported_target = imported_targets.get(
        call_parts[0]
    )
    if imported_target is not None:
        candidate_name = ".".join(
            [imported_target, *call_parts[1:]]
        )
        if candidate_name in source_names:
            return candidate_name

    imported_module = imported_modules.get(call_parts[0])
    if imported_module is not None:
        candidate_name = ".".join(
            [imported_module, *call_parts[1:]]
        )
        if candidate_name in source_names:
            return candidate_name

    return None


def _resolve_constructor_target(
    *,
    constructor_name: str,
    imported_targets: dict[str, str],
    imported_modules: dict[str, str],
    source_names: set[str],
) -> str | None:
    """只解析能由导入和源码符号共同证明的构造器。"""
    constructor_parts = constructor_name.split(".")
    imported_target = imported_targets.get(
        constructor_parts[0]
    )
    if imported_target is not None:
        candidate_name = ".".join(
            [imported_target, *constructor_parts[1:]]
        )
        if _matches_source_or_owner(
            candidate_name,
            source_names,
        ):
            return candidate_name

    imported_module = imported_modules.get(
        constructor_parts[0]
    )
    if imported_module is not None:
        candidate_name = ".".join(
            [imported_module, *constructor_parts[1:]]
        )
        if _matches_source_or_owner(
            candidate_name,
            source_names,
        ):
            return candidate_name

    return None


def _collect_instance_bindings(
    *,
    node: FunctionNode,
    imported_targets: dict[str, str],
    imported_modules: dict[str, str],
    source_names: set[str],
) -> dict[str, str]:
    visitor = _InstanceBindingVisitor(
        imported_targets=imported_targets,
        imported_modules=imported_modules,
        source_names=source_names,
    )
    for statement in node.body:
        visitor.visit(statement)
    return visitor.bindings


def _collect_test_class_setup_bindings(
    *,
    tree: ast.Module,
    imported_targets: dict[str, str],
    imported_modules: dict[str, str],
    source_names: set[str],
) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        class_bindings: dict[str, str] = {}
        for child in node.body:
            if not isinstance(child, FunctionNode):
                continue
            if child.name not in {
                "setup_method",
                "setup_class",
            }:
                continue
            class_bindings.update(
                _collect_instance_bindings(
                    node=child,
                    imported_targets=imported_targets,
                    imported_modules=imported_modules,
                    source_names=source_names,
                )
            )

        if class_bindings:
            bindings[node.name] = class_bindings

    return bindings


class _InstanceBindingVisitor(ast.NodeVisitor):
    """收集由明确源码类构造器产生的局部实例。"""

    def __init__(
        self,
        *,
        imported_targets: dict[str, str],
        imported_modules: dict[str, str],
        source_names: set[str],
    ) -> None:
        self.imported_targets = imported_targets
        self.imported_modules = imported_modules
        self.source_names = source_names
        self.bindings: dict[str, str] = {}

    def _record(
        self,
        target: ast.expr,
        value: ast.expr | None,
    ) -> None:
        if not isinstance(value, ast.Call):
            return

        target_name = _get_call_name(target)
        constructor_name = _get_call_name(value.func)
        if target_name is None or constructor_name is None:
            return

        owner_name = _resolve_constructor_target(
            constructor_name=constructor_name,
            imported_targets=self.imported_targets,
            imported_modules=self.imported_modules,
            source_names=self.source_names,
        )
        if owner_name is not None:
            self.bindings[target_name] = owner_name

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record(target, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record(node.target, node.value)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

def index_python_project_tests(
        project_root: str,
        source_symbols: list[SourceSymbol],
) -> TestIndex:
    """扫描项目中的正式 pytest 文件并建立索引"""

    # 放在函数内部的延迟导入 表示只有实际建立项目索引时才导入排除规则，也降低分析器模块之间在加载阶段互相依赖的风险
    from core.analyzers.framework import EXCLUDE_DIRS

    root_path = Path(project_root).resolve()
    exclude_dirs = set(EXCLUDE_DIRS)

    test_paths = [
        path
        for path in root_path.rglob('*.py')
        if (
            _is_python_test_file(path)
            and not any(
                part in exclude_dirs
                for part in (
                    # [:-1] 表示取列表中从零到倒数第二个元素 (".venv", "tests", "test_demo.py") -> (".venv", "tests")
                    path.relative_to(root_path).parts[:-1]
                )
            )
        )
    ]

    entries: list[TestIndexEntry] = []

    for test_paths in sorted(
        test_paths,
        key=lambda path: path.as_posix(),
    ):
        module_name = resolve_python_module_name(
            file_path=str(test_paths),
            project_root=str(root_path),
        )

        entries.extend(
            index_python_test_file(
                file_path=str(test_paths),
                module_name=module_name,
                project_root=str(root_path),
                source_symbols=source_symbols,
            )
        )

    entries.sort(key=lambda entry: (
        entry.test_qualified_name,
        entry.source_qualified_name,
        entry.test_file_path,
        entry.test_line,
    ))

    return TestIndex(entries=entries)

def _is_python_test_file(path: Path) -> bool:
    return (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )

def _collect_function_calls(node: FunctionNode) -> set[str]:
    visitor = _FunctionCallVisitor()

    for statement in node.body:
        visitor.visit(statement)

    return visitor.call_names

class _FunctionCallVisitor(ast.NodeVisitor):
    """收集一个函数自身直接包含的调用名称"""
    def __init__(self) -> None:
        self.call_names: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _get_call_name(node.func)

        if call_name is not None:
            self.call_names.add(call_name)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

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

def _collect_test_function_nodes(
        tree: ast.Module,
        module_name: str,
) -> dict[str, FunctionNode]:
    visitor = _TestFunctionNodeVisitor(
        module_name=module_name,
    )
    visitor.visit(tree)
    return visitor.nodes

class _TestFunctionNodeVisitor(ast.NodeVisitor):
    """按限定名保存测试函数的 AST 节点"""
    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self.class_stack: list[str] = []
        self.nodes: dict[str, FunctionNode] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)

    def _record_function(self, node: FunctionNode) -> None:
        if not node.name.startswith("test_"):
            return

        name_parts = [
            self.module_name,
            *self.class_stack,
            node.name,
        ]
        qualified_name = ".".join(name_parts)

        self.nodes[qualified_name] = node


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
