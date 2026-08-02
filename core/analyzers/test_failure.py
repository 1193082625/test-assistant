"""从失败 pytest node 的测试 AST 提取结构化共同根因。"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.models import PytestIssue


_PRIVATE_SYMBOL = re.compile(r"\b(_[A-Za-z][A-Za-z0-9_]*)\b")


@dataclass(frozen=True)
class FailureRootCause:
    key: str
    kind: str
    target: str
    symbol: str
    source_path: str


def _imported_sources(tree: ast.AST) -> dict[str, tuple[str, str]]:
    imported: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            imported[alias.asname or alias.name] = (node.module, alias.name)
    return imported


def _source_path(root: Path, module: str) -> Path | None:
    candidate = root / (module.replace(".", "/") + ".py")
    return candidate if candidate.is_file() else None


def _module_names(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            )
    return names


def _patch_cause(root: Path, target: str) -> FailureRootCause | None:
    parts = target.split(".")
    for index in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:index])
        path = _source_path(root, module)
        if path is None:
            continue
        remainder = parts[index:]
        if not remainder or remainder[0] in _module_names(path):
            return None
        missing = remainder[0]
        qualified = f"{module}.{missing}"
        return FailureRootCause(
            key=f"obsolete_patch:{qualified}",
            kind="obsolete_patch",
            target=qualified,
            symbol=missing,
            source_path=path.relative_to(root).as_posix(),
        )
    return None


def _missing_symbol_cause(
    *,
    root: Path,
    imported: Mapping[str, tuple[str, str]],
    owner: str | None,
    symbol: str,
) -> FailureRootCause | None:
    if owner in imported:
        module, class_name = imported[owner]
    elif len(imported) == 1:
        module, class_name = next(iter(imported.values()))
    else:
        return None
    path = _source_path(root, module)
    if path is None:
        return None
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if re.search(rf"\b(?:async\s+def|def)\s+{re.escape(symbol)}\b", source):
        return None
    target = f"{module}.{class_name}.{symbol}"
    return FailureRootCause(
        key=f"missing_symbol:{target}",
        kind="missing_symbol",
        target=target,
        symbol=symbol,
        source_path=path.relative_to(root).as_posix(),
    )


def _test_function(tree: ast.AST, name: str) -> ast.AST | None:
    return next(
        (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ),
        None,
    )


def _local_type_bindings(function: ast.AST) -> dict[str, str]:
    """记录 ``service = Service()`` 这类局部实例与导入类型的关系。"""
    bindings: dict[str, str] = {}
    for node in ast.walk(function):
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ):
            targets = (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value.func.id
    return bindings


def _cause_for_node(root: Path, node_id: str) -> FailureRootCause | None:
    test_path_text, _, qualified_test = node_id.partition("::")
    test_path = (root / test_path_text).resolve()
    try:
        test_path.relative_to(root)
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return None
    function = _test_function(tree, qualified_test.split("::")[-1])
    if function is None:
        return None
    imported = {
        name: value
        for name, value in _imported_sources(tree).items()
        if _source_path(root, value[0]) is not None
    }
    bindings = _local_type_bindings(function)
    referenced_types = {
        node.id
        for node in ast.walk(function)
        if isinstance(node, ast.Name) and node.id in imported
    }
    for decorator in getattr(function, "decorator_list", []):
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "patch"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and isinstance(decorator.args[0].value, str)
        ):
            cause = _patch_cause(root, decorator.args[0].value)
            if cause is not None:
                return cause
    direct_candidates: list[tuple[str | None, str]] = []
    string_candidates: list[tuple[str | None, str]] = []
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "hasattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            direct_candidates.append((node.args[0].id, node.args[1].value))
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            owner = None
            if isinstance(node.value, ast.Name):
                owner = bindings.get(node.value.id, node.value.id)
            elif (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
            ):
                owner = node.value.func.id
            direct_candidates.append((owner, node.attr))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            owner = (
                next(iter(referenced_types))
                if len(referenced_types) == 1
                else None
            )
            string_candidates.extend(
                (owner, match) for match in _PRIVATE_SYMBOL.findall(node.value)
            )
    # 实际属性访问比 mock 参数或说明字符串更接近失败行为。
    for owner, symbol in (*direct_candidates, *string_candidates):
        cause = _missing_symbol_cause(
            root=root,
            imported=imported,
            owner=owner,
            symbol=symbol,
        )
        if cause is not None:
            return cause
    return None


def extract_failure_root_causes(
    *,
    project_root: str | Path,
    issues: tuple[PytestIssue, ...],
) -> dict[str, FailureRootCause]:
    root = Path(project_root).resolve()
    result: dict[str, FailureRootCause] = {}
    for issue in issues:
        if issue.node_id is None or issue.node_id in result:
            continue
        cause = _cause_for_node(root, issue.node_id)
        if cause is not None:
            result[issue.node_id] = cause
    return result
