"""源文件到测试的影响映射"""
from pathlib import Path
from core.models import (
    SourceSymbol,
    TestIndex,
    TestIndexEntry
)
from core.analyzers.source import (
    analyze_python_symbols,
    resolve_python_module_name,
    index_python_project_tests,
)

# affected 受影响的

def find_directly_affected_tests(
        changed_symbol_qualified_names: list[str],
        test_index: TestIndex,
) -> list[TestIndexEntry]:
    """查找变更源码符号直接关联的已有测试"""

    affected_tests: list[TestIndexEntry] = []
    seen_test_ids: set[tuple[str, str, int]] = set()

    for qualified_name in changed_symbol_qualified_names:
        for entry in test_index.tests_for(qualified_name):
            test_id = (
                entry.test_qualified_name,
                entry.test_file_path,
                entry.test_line,
            )

            if test_id in seen_test_ids:
                continue

            seen_test_ids.add(test_id)
            affected_tests.append(entry)

    return affected_tests

def _find_changed_python_symbols(
        project_root: str,
        changed_files: dict[str, list[str]],
) -> list[SourceSymbol]:
    """提取新增和修改的 python 文件中的源码符号"""
    root_path = Path(project_root)
    symbols_by_name: dict[str, SourceSymbol] = {}

    for change_type in ("added", "modified"):
        for relative_path in sorted(
            changed_files.get(change_type, []),
        ):
            if not relative_path.endswith(".py"):
                continue

            source_path = root_path / relative_path
            module_name = resolve_python_module_name(
                file_path=str(source_path),
                project_root=str(root_path),
            )
            symbols = analyze_python_symbols(
                file_path=str(source_path),
                module_name=module_name,
            )

            for symbol in symbols:
                symbols_by_name[symbol.qualified_name] = symbol

    return [
        symbols_by_name[qualified_name]
        for qualified_name in sorted(symbols_by_name)
    ]

def find_changed_python_symbol_names(
        project_root: str,
        changed_files: dict[str, list[str]],
) -> list[str]:
    """提取新增和修改的 python 文件中的源码符号限定名"""
    return [
        symbol.qualified_name
        for symbol in _find_changed_python_symbols(
            project_root=project_root,
            changed_files=changed_files,
        )
    ]

def find_affected_python_tests(
        project_root: str,
        changed_files: dict[str, list[str]],
) -> list[TestIndexEntry]:
    """根据文件变更查找直接受影响的 pytest 测试"""

    changed_symbols = _find_changed_python_symbols(
        project_root=project_root,
        changed_files=changed_files,
    )
    test_index = index_python_project_tests(
        project_root=project_root,
        source_symbols=changed_symbols,
    )
    return find_directly_affected_tests(
        changed_symbol_qualified_names=[
            symbol.qualified_name
            for symbol in changed_symbols
        ],
        test_index=test_index,
    )
