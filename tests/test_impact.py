from core.analyzers.impact import (
    find_directly_affected_tests,
    find_changed_python_symbol_names,
    find_affected_python_tests,
    select_tests_for_changes,
)

from core.models import (
    TestIndex as Index,
    TestIndexEntry as IndexEntry,
    TestSelection as Selection,
    TestSelectionMode as SelectionMode
)

def test_finds_tests_for_changed_source_symbol():
    """
    测试查找变更源码符号直接关联的已有测试

    调用过程：
    changed_symbol_qualified_names
    → 逐个取得 qualified_name
    → test_index.tests_for(qualified_name)
    → 找到该源码符号对应的索引条目
    → 合并到 affected_tests
    """
    add_test = IndexEntry(
        source_qualified_name="demo.add",
        test_qualified_name="tests.test_demo.test_add",
        test_file_path="tests/test_demo.py",
        test_line=3
    )

    subtract_test = IndexEntry(
        source_qualified_name="demo.subtract",
        test_qualified_name="tests.test_demo.test_subtract",
        test_file_path="tests/test_demo.py",
        test_line=8
    )

    index = Index(
        entries=[add_test, subtract_test]
    )

    affected_tests = find_directly_affected_tests(
        changed_symbol_qualified_names=["demo.add"],
        test_index=index,
    )

    assert affected_tests == [add_test]

def test_deduplicates_test_reached_by_multiple_symbols():
    add_entry = IndexEntry(
        source_qualified_name="demo.add",
        test_qualified_name="tests.test_demo.test_add_and_format",
        test_file_path="tests/test_demo.py",
        test_line=3
    )

    format_entry = IndexEntry(
        source_qualified_name="demo.format_result",
        test_qualified_name="tests.test_demo.test_add_and_format",
        test_file_path="tests/test_demo.py",
        test_line=3
    )

    index = Index(
        entries=[add_entry, format_entry]
    )

    affected_tests = find_directly_affected_tests(
        changed_symbol_qualified_names=[
            "demo.add",
            "demo.format_result",
        ],
        test_index=index,
    )

    assert affected_tests == [add_entry]

def test_find_symbols_in_changed_python_files(tmp_path):
    """
    期望的数据转换是：

    changed_files["modified"]
    → demo.py
    → resolve_python_module_name(...)
    → 模块名 demo
    → analyze_python_symbols(...)
    → demo.add
    → demo.subtract
    """
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def subtract(a, b):\n"
            "    return a - b\n"
        ),
        encoding="utf-8",
    )

    changed_files = {
        "added": [],
        "modified": ["demo.py"],
        "deleted": [],
    }

    changed_symbol_names = (
        find_changed_python_symbol_names(
            project_root=str(tmp_path),
            changed_files=changed_files,
        )
    )

    assert changed_symbol_names == ["demo.add", "demo.subtract"]

def test_finds_affected_tests_from_changed_files(tmp_path):
    """
    这个测试覆盖完整链路

    demo.py 被修改
    → 提取 demo.add
    → 扫描 tests/test_demo.py
    → 发现 test_add 调用了导入的 add
    → 建立 demo.add → test_add 索引
    → 返回 test_add

    测试索引应扫描项目中的已有测试，而不是只扫描发生变化的测试文件
    """
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    test_path = tests_path / "test_demo.py"
    test_path.write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    affected_tests = find_affected_python_tests(
        project_root=str(tmp_path),
        changed_files = {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        }
    )

    assert affected_tests == [
        IndexEntry(
            source_qualified_name="demo.add",
            test_qualified_name="tests.test_demo.test_add",
            test_file_path="tests/test_demo.py",
            test_line=3
        )
    ]

def test_returns_no_direct_tests_when_symbol_has_no_mapping(tmp_path):
    """验证 源码有变化， 但没有已有测试映射"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    affected_tests = find_affected_python_tests(
        project_root=str(tmp_path),
        changed_files={
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        }
    )
    assert affected_tests == [] # 表示没有找到直接关联的已有测试

def test_ignores_changed_non_python_files(tmp_path):
    """验证非 python 文件不会进入 Python AST 分析"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"enabled": true}',
        encoding="utf-8",
    )

    changed_symbol_names = (
        find_changed_python_symbol_names(
            project_root=str(tmp_path),
            changed_files={
                "added": [],
                "modified": ["config.json"],
                "deleted": [],
            }
        )
    )

    assert changed_symbol_names == []

def test_selects_directly_mapped_python_tests(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        }
    )

    assert selection == Selection(
        mode=SelectionMode.DIRECT,
        test_files=["tests/test_demo.py"],
        evidence=[
            (
                "demo.add -> "
                "tests.test_demo.test_add "
                "at tests/test_demo.py:3"
            ),
        ],
        warnings=[]
    )

def test_returns_none_when_no_python_symbols_changed(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"enabled": true}',
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": ["config.json"],
            "deleted": [],
        },
    )

    assert selection == Selection(
        mode=SelectionMode.NONE,
        test_files=[],
        evidence=[
            (
                "No added or modified Python "
                "source symbols were found"
            )
        ],
        warnings=[]
    )

def test_warns_when_changed_symbols_have_no_tests(tmp_path):
    """Python 源码有变化，但没有已有测试映射，不能静默返回普通空结果，必须明确提示创建 TestSpec"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        }
    )

    assert selection == Selection(
        mode=SelectionMode.NONE,
        test_files=[],
        evidence=[
            "Changed Python symbols: demo.add",
        ],
        warnings=[
            (
                "No existing tests directly map to "
                "the changed symbols; create a "
                "TestSpec before generating tests"
            ),
        ],
    )

def test_returns_unsupported_for_non_python_project(tmp_path):
    """非 python 项目不能被错误解释成 “没有 python 变更”"""
    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="javascript",
        changed_files={
            "added": [],
            "modified": ["src/app.js"],
            "deleted": [],
        }
    )

    assert selection == Selection(
        mode=SelectionMode.UNSUPPORTED,
        test_files=[],
        evidence=[
            "Requested language: javascript",
        ],
        warnings=[
            (
                "Symbol-level impact analysis "
                "currently supports only Python"
            )
        ]
    )

def test_falls_back_to_full_tests_for_deleted_python_file(tmp_path):
    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": [],
            "deleted": ["demo.py"],
        }
    )

    assert selection == Selection(
        mode=SelectionMode.FULL,
        test_files=["tests/test_demo.py"],
        evidence=["Deleted Python files: demo.py"],
        warnings=[
            (
                "Deleted files cannot be analyzed "
                "from current source; falling back "
                "to all pytest test files"
            ),
        ]
    )

def test_falls_back_to_full_when_python_analysis_fails(tmp_path):
    """测试源码无法解析时不能直接抛异常，也不能返回假成功，应降级为FULL"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        "def broken(:\n",
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )
    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
    )

    assert selection == Selection(
        mode=SelectionMode.FULL,
        test_files=["tests/test_demo.py"],
        evidence=[
            (
                "Python files requiring analysis: "
                "demo.py"
            ),
        ],
        warnings=[
            (
                "Python impact analysis failed "
                "(SyntaxError); falling back to "
                "all pytest test files"
            ),
        ]
    )

def test_falls_back_to_full_when_test_index_fails(tmp_path):
    """测试 源码本身有效，但已有测试文件语法损坏，导致建立 TestIndex 失败"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    test_path = tmp_path / "tests"
    test_path.mkdir()

    (test_path / "test_demo.py").write_text(
        "def broken_test(:\n",
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        }
    )

    assert selection == Selection(
        mode=SelectionMode.FULL,
        test_files=["tests/test_demo.py"],
        evidence=[
            (
                "Python files requiring analysis: "
                "demo.py"
            )
        ],
        warnings=[
            (
                "Python impact analysis failed "
                "(SyntaxError); falling back to "
                "all pytest test files"
            )
        ]
    )

def test_full_fallback_selects_only_formal_test_directories(tmp_path):
    """测试 FULL 降级误选生产文件和历史文件"""
    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    source_path = tmp_path / "core" / "generators"
    source_path.mkdir(parents=True)

    (source_path / "test_generator.py").write_text(
        "def generator(): pass\n",
        encoding="utf-8",
    )

    history_path = (
        tmp_path / ".history" / "tests"
    )
    history_path.mkdir(parents=True)

    (history_path / "test_old.py").write_text(
        "def test_old(): pass\n",
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": [],
            "deleted": ["demo.py"],
        }
    )

    assert selection.test_files == ["tests/test_demo.py"]

def test_returns_unsupported_for_missing_language(tmp_path):
    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language=None,
        changed_files={
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        }
    )
    assert selection == Selection(
        mode=SelectionMode.UNSUPPORTED,
        test_files=[],
        evidence=["Requested language: unknown",],
        warnings=[
            (
                "Symbol-level impact analysis "
                "currently supports only Python"
            ),
        ]
    )

def test_selects_modified_test_file_itself(tmp_path):
    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": ["tests/test_demo.py"],
            "deleted": [],
        },
    )

    assert selection.mode is SelectionMode.DIRECT
    assert selection.test_files == [
        "tests/test_demo.py",
    ]
    assert selection.evidence == [
        "Changed pytest test file: tests/test_demo.py",
    ]
    assert selection.warnings == []

def test_merges_changed_tests_with_source_affected_tests(
    tmp_path,
):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    (tests_path / "test_manual.py").write_text(
        "def test_manual(): pass\n",
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": [
                "demo.py",
                "tests/test_manual.py",
            ],
            "deleted": [],
        },
    )

    assert selection.mode is SelectionMode.DIRECT
    assert selection.test_files == [
        "tests/test_demo.py",
        "tests/test_manual.py",
    ]
    assert (
        "Changed pytest test file: "
        "tests/test_manual.py"
    ) in selection.evidence

def test_runs_changed_test_when_source_has_no_mapping(
    tmp_path,
):
    source_path = tmp_path / "orphan.py"
    source_path.write_text(
        (
            "def calculate():\n"
            "    return 42\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()
    (tests_path / "test_manual.py").write_text(
        "def test_manual(): pass\n",
        encoding="utf-8",
    )

    selection = select_tests_for_changes(
        project_root=str(tmp_path),
        language="python",
        changed_files={
            "added": [],
            "modified": [
                "orphan.py",
                "tests/test_manual.py",
            ],
            "deleted": [],
        },
    )

    assert selection.mode is SelectionMode.DIRECT
    assert selection.test_files == [
        "tests/test_manual.py",
    ]
    assert (
        "Changed pytest test file: "
        "tests/test_manual.py"
    ) in selection.evidence
    assert (
        "Changed Python symbols: "
        "orphan.calculate"
    ) in selection.evidence
    assert selection.warnings == [
        (
            "No existing tests directly map to "
            "the changed symbols; create a "
            "TestSpec before generating tests"
        )
    ]