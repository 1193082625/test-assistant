"""将 coverage.py 行与分支事实映射到 Python 源码符号。"""

from fnmatch import fnmatch
from pathlib import Path

from core.analyzers.source import (
    analyze_python_symbols,
    resolve_python_module_name,
)
from core.models import CoverageSummary, SymbolCoverage


def _integer_lines(value: object, *, field: str) -> set[int]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int)
        for item in value
    ):
        raise ValueError(f"coverage {field} 必须是整数列表")
    return set(value)


def _branches(value: object, *, field: str) -> set[tuple[int, int]]:
    if not isinstance(value, list):
        raise ValueError(f"coverage {field} 必须是分支列表")
    branches: set[tuple[int, int]] = set()
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or any(
                isinstance(part, bool) or not isinstance(part, int)
                for part in item
            )
        ):
            raise ValueError(f"coverage {field} 必须是分支列表")
        branches.add((item[0], item[1]))
    return branches


def _coverage_for_range(
    *,
    source_path: str,
    qualified_name: str,
    kind: str,
    start_line: int,
    end_line: int,
    executed_lines: set[int],
    missing_lines: set[int],
    executed_branches: set[tuple[int, int]],
    missing_branches: set[tuple[int, int]],
) -> SymbolCoverage:
    covered = {
        line for line in executed_lines if start_line <= line <= end_line
    }
    missing = {
        line for line in missing_lines if start_line <= line <= end_line
    }
    covered_branch_edges = {
        edge for edge in executed_branches
        if start_line <= edge[0] <= end_line
    }
    missing_branch_edges = {
        edge for edge in missing_branches
        if start_line <= edge[0] <= end_line
    }
    return SymbolCoverage(
        source_path=source_path,
        qualified_name=qualified_name,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        summary=CoverageSummary(
            statements_covered=len(covered),
            statements_total=len(covered | missing),
            branches_covered=len(covered_branch_edges),
            branches_total=len(covered_branch_edges | missing_branch_edges),
        ),
        missing_lines=tuple(sorted(missing)),
        missing_branches=tuple(sorted(missing_branch_edges)),
    )


def analyze_symbol_coverage(
    *,
    project_root: str | Path,
    coverage_data: dict[str, object],
    exclude_patterns: tuple[str, ...] = (),
) -> tuple[SymbolCoverage, ...]:
    """把 coverage JSON 映射为模块、类、函数和方法覆盖事实。"""
    root = Path(project_root).resolve()
    files = coverage_data.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage files 必须是对象")

    results: list[SymbolCoverage] = []
    for raw_path, raw_data in sorted(files.items()):
        if not isinstance(raw_path, str) or not isinstance(raw_data, dict):
            raise ValueError("coverage 文件记录格式无效")
        candidate = Path(raw_path)
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError("coverage 源码路径必须位于项目内") from error
        if any(fnmatch(relative_path, pattern) for pattern in exclude_patterns):
            continue
        if path.suffix != ".py" or not path.is_file():
            raise ValueError("coverage 源码文件不存在或不是 Python 文件")

        executed_lines = _integer_lines(
            raw_data.get("executed_lines", []), field="executed_lines"
        )
        missing_lines = _integer_lines(
            raw_data.get("missing_lines", []), field="missing_lines"
        )
        executed_branches = _branches(
            raw_data.get("executed_branches", []), field="executed_branches"
        )
        missing_branches = _branches(
            raw_data.get("missing_branches", []), field="missing_branches"
        )
        module_name = resolve_python_module_name(
            file_path=str(path), project_root=str(root)
        )
        end_line = max(1, len(path.read_text(encoding="utf-8").splitlines()))
        results.append(_coverage_for_range(
            source_path=relative_path,
            qualified_name=module_name,
            kind="module",
            start_line=1,
            end_line=end_line,
            executed_lines=executed_lines,
            missing_lines=missing_lines,
            executed_branches=executed_branches,
            missing_branches=missing_branches,
        ))
        for symbol in analyze_python_symbols(str(path), module_name):
            results.append(_coverage_for_range(
                source_path=relative_path,
                qualified_name=symbol.qualified_name,
                kind=symbol.kind.value,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                executed_lines=executed_lines,
                missing_lines=missing_lines,
                executed_branches=executed_branches,
                missing_branches=missing_branches,
            ))
    return tuple(sorted(
        results,
        key=lambda item: (item.source_path, item.start_line, item.qualified_name),
    ))

