"""源文件到测试的影响映射"""
from pathlib import Path
from core.models import (
    SourceSymbol,
    TestIndex,
    TestIndexEntry, TestSelection, TestSelectionMode
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

def _find_python_test_files(
    project_root: str,
) -> list[str]:
    """查找正式测试目录中的 pytest 文件。"""

    from core.analyzers.framework import EXCLUDE_DIRS

    root_path = Path(project_root).resolve()

    excluded_dirs = set(EXCLUDE_DIRS)
    test_dir_names = {
        "test",
        "tests",
    }

    test_files: list[str] = []

    for path in root_path.rglob("*.py"):
        relative_path = path.relative_to(
            root_path
        )
        directory_parts = (
            relative_path.parts[:-1]
        )

        # 如果位于排除目录，则跳过
        if any(
            part in excluded_dirs
            for part in directory_parts
        ):
            continue

        if not any(
            part in test_dir_names
            for part in directory_parts
        ):
            continue

        if not (
            path.name.startswith("test_")
            or path.name.endswith("_test.py")
        ):
            continue

        test_files.append(
            relative_path.as_posix()
        )

    return sorted(test_files)

def _is_formal_python_test_file(
    relative_path: str,
) -> bool:
    """判断路径是否属于正式 pytest 测试文件。"""
    path = Path(relative_path)
    directory_parts = path.parts[:-1]

    return (
        any(
            part in {"test", "tests"}
            for part in directory_parts
        )
        and (
            path.name.startswith("test_")
            or path.name.endswith("_test.py")
        )
    )

def find_changed_python_symbols(
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

            if _is_formal_python_test_file(
                    relative_path
            ):
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
        for symbol in find_changed_python_symbols(
            project_root=project_root,
            changed_files=changed_files,
        )
    ]

def find_affected_python_tests(
    project_root: str,
    changed_files: dict[str, list[str]],
) -> list[TestIndexEntry]:
    """根据文件变更查找直接受影响的 pytest 测试。"""

    changed_symbols = find_changed_python_symbols(
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

def _build_analysis_failure_selection(
        project_root: str,
        python_files: list[str],
        error: Exception
) -> TestSelection:
    """构建 Python 影响分析失败时的全量降级结果"""
    return TestSelection(
        # 安全降级：源码无法解析时不能直接抛异常，也不能返回假成功，应降级为FULL
        # 安全降级：源码本身有效，但已有测试文件语法损坏，导致建立 TestIndex 失败，也应该为 FULL
        mode=TestSelectionMode.FULL,
        test_files=_find_python_test_files(project_root),
        evidence=[
            (
                "Python files requiring analysis: "
                f"{', '.join(python_files)}"
            ),
        ],
        warnings=[
            (
                "Python impact analysis failed "
                f"({type(error).__name__}); "
                "falling back to all pytest "
                "test files"
            ),
        ]
    )

def select_tests_for_changes(
    project_root: str,
    language: str | None,
    changed_files: dict[str, list[str]],
) -> TestSelection:
    """为项目变更生成可解释的测试选择结果。"""
    if (
            not isinstance(language, str)
            or not language.strip()
    ):
        language_name = "unknown"
    else:
        language_name = (
            language.strip().lower()
        )

    if language_name != "python":
        return TestSelection(
            mode=TestSelectionMode.UNSUPPORTED,
            test_files=[],
            evidence=[
                f"Requested language: {language_name}"
            ],
            warnings=[
                (
                    "Symbol-level impact analysis "
                    "currently supports only Python"
                )
            ],
        )

    changed_test_files = sorted({
        relative_path
        for change_type in ("added", "modified")
        for relative_path in changed_files.get(
            change_type,
            [],
        )
        if _is_formal_python_test_file(
            relative_path
        )
    })

    changed_python_source_files = sorted({
        relative_path
        for change_type in ("added", "modified")
        for relative_path in changed_files.get(
            change_type,
            [],
        )
        if (
                relative_path.endswith(".py")
                and not _is_formal_python_test_file(
            relative_path
        )
        )
    })

    if (
            changed_test_files
            and not changed_python_source_files
    ):
        return TestSelection(
            mode=TestSelectionMode.DIRECT,
            test_files=changed_test_files,
            evidence=[
                (
                    "Changed pytest test file: "
                    f"{test_file}"
                )
                for test_file in changed_test_files
            ],
            warnings=[],
        )

    deleted_python_files = sorted(
        relative_path
        for relative_path in changed_files.get("deleted", [])
        if relative_path.endswith(".py")
    )

    if deleted_python_files:
        return TestSelection(
            mode=TestSelectionMode.FULL,
            test_files=_find_python_test_files(project_root),
            evidence=[
                (
                    "Deleted Python files: "
                    f"{', '.join(deleted_python_files)}"
                ),
            ],
            warnings=[
                (
                    "Deleted files cannot be analyzed "
                    "from current source; falling back "
                    "to all pytest test files"
                ),
            ],
        )

    python_files_requiring_analysis = sorted(
        relative_path
        for change_type in ("added", "modified")
        for relative_path in changed_files.get(change_type, [])
        if relative_path.endswith(".py")
    )

    try:
        changed_symbols = find_changed_python_symbols(
            project_root=project_root,
            changed_files=changed_files,
        )
    except (SyntaxError, UnicodeError, OSError) as error:
        return _build_analysis_failure_selection(
            project_root=project_root,
            python_files=python_files_requiring_analysis,
            error=error,
        )

    if not changed_symbols:
        return TestSelection(
            mode=TestSelectionMode.NONE,
            test_files=[],
            evidence=[
                (
                    "No added or modified Python "
                    "source symbols were found"
                ),
            ],
            warnings=[],
        )

    try:
        test_index = index_python_project_tests(
            project_root=project_root,
            source_symbols=changed_symbols,
        )
    except (SyntaxError, UnicodeError, OSError) as error:
        return _build_analysis_failure_selection(
            project_root=project_root,
            python_files=python_files_requiring_analysis,
            error=error,
        )

    affected_tests = find_directly_affected_tests(
        changed_symbol_qualified_names=[
            symbol.qualified_name
            for symbol in changed_symbols
        ],
        test_index=test_index,
    )

    if not affected_tests:
        changed_symbol_names = ", ".join(
            symbol.qualified_name
            for symbol in changed_symbols
        )

        evidence = [
            *(
                (
                    "Changed pytest test file: "
                    f"{test_file}"
                )
                for test_file in changed_test_files
            ),
            (
                "Changed Python symbols: "
                f"{changed_symbol_names}"
            ),
        ]

        return TestSelection(
            mode=(
                TestSelectionMode.DIRECT
                if changed_test_files
                else TestSelectionMode.NONE
            ),
            test_files=changed_test_files,
            evidence=evidence,
            warnings=[
                (
                    "No existing tests directly map to "
                    "the changed symbols; create a "
                    "TestSpec before generating tests"
                ),
            ],
        )

    test_files = sorted({
        *changed_test_files,
        *(
            entry.test_file_path
            for entry in affected_tests
        ),
    })

    evidence = [
        *(
            (
                "Changed pytest test file: "
                f"{test_file}"
            )
            for test_file in changed_test_files
        ),
        *(
            (
                f"{entry.source_qualified_name} -> "
                f"{entry.test_qualified_name} "
                f"at {entry.test_file_path}:"
                f"{entry.test_line}"
            )
            for entry in affected_tests
        ),
    ]

    return TestSelection(
        mode=TestSelectionMode.DIRECT,
        test_files=test_files,
        evidence=evidence,
        warnings=[],
    )