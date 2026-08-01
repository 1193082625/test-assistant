from core.models import (
    TestIndexEntry as IndexEntry,
    SourceSymbol,
    SymbolKind,
    TestIndex as Index,
)
from core.analyzers.source import (
    analyze_python_test_symbols,
    index_python_test_file,
    index_python_project_tests,
    filter_symbols_without_existing_tests
)

def test_test_index_entry_maps_test_to_source_symbol():
    entry = IndexEntry(
        source_qualified_name="demo.add",
        test_qualified_name="tests.test_demo.test_add",
        test_file_path="tests/test_demo.py",
        test_line=4,
    )

    assert entry.source_qualified_name == "demo.add"
    assert entry.test_qualified_name == "tests.test_demo.test_add"
    assert entry.test_file_path == "tests/test_demo.py"
    assert entry.test_line == 4

def test_analyze_python_test_symbols_extracts_test_function(tmp_path):
    """测试 不把测试文件中的辅助函数也当成测试"""
    test_path = tmp_path / "test_demo.py"
    test_path.write_text(
        (
            "from demo import add\n"
            "\n"
            "def helper() -> int:\n"
            "    return 1\n"
            "\n"
            "def test_add() -> None:\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_test_symbols(
        file_path=str(test_path),
        module_name="tests.test_demo",
    )

    assert [
        symbol.qualified_name
        for symbol in symbols
    ] == ["tests.test_demo.test_add"]

def test_index_python_test_file_maps_imported_function(tmp_path):
    """
    把测试中的调用映射到源码符号

    from demo import add
    def test_add():
        assert add(1, 2) == 3

    可以确定： tests.test_demo.test_add --> demo.add
    """
    source_symbol = SourceSymbol(
        name="add",
        qualified_name="demo.add",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="add(a: int, b: int) -> int",
        start_line=1,
        end_line=2,
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    test_path = tests_dir / "test_demo.py"
    test_path.write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add() -> None:\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_demo",
        project_root=str(tmp_path),
        source_symbols=[source_symbol],
    )

    assert entries == [
        IndexEntry(
            source_qualified_name="demo.add",
            test_qualified_name="tests.test_demo.test_add",
            test_file_path="tests/test_demo.py",
            test_line=3,
        )
    ]

def test_index_python_test_file_maps_module_attribute_call(tmp_path):
    source_symbol = SourceSymbol(
        name="add",
        qualified_name="demo.add",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="add(a: int, b: int) -> int",
        start_line=1,
        end_line=2,
    )

    test_dir = tmp_path / "tests"
    test_dir.mkdir()

    test_path = test_dir / "test_demo.py"
    test_path.write_text(
        (
            "import demo\n"
            "\n"
            "def test_add() -> None:\n"
            "    assert demo.add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_demo",
        project_root=str(tmp_path),
        source_symbols=[source_symbol],
    )

    assert entries == [
        IndexEntry(
            source_qualified_name="demo.add",
            test_qualified_name="tests.test_demo.test_add",
            test_file_path="tests/test_demo.py",
            test_line=3,
        )
    ]

def test_index_python_test_file_maps_test_class_method(tmp_path):
    source_symbol = SourceSymbol(
        name="add",
        qualified_name="demo.add",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="add(a: int, b: int) -> int",
        start_line=1,
        end_line=2,
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_path = tests_dir / "test_demo.py"
    test_path.write_text(
        (
            "from demo import add\n"
            "\n"
            "class TestCalculator:\n"
            "    def test_add(self) -> None:\n"
            "        assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_demo",
        project_root=str(tmp_path),
        source_symbols=[source_symbol],
    )

    assert entries == [
        IndexEntry(
            source_qualified_name="demo.add",
            test_qualified_name=(
                "tests.test_demo."
                "TestCalculator.test_add"
            ),
            test_file_path="tests/test_demo.py",
            test_line=4,
        )
    ]

def test_test_index_queries_entries_by_source_symbol():
    """让调用方能按源码符号查询已有测试"""
    index = Index(
        entries=[
            IndexEntry(
                source_qualified_name="demo.subtract",
                test_qualified_name="tests.test_demo.test_subtract",
                test_file_path="tests/test_demo.py",
                test_line=8,
            ),
            IndexEntry(
                source_qualified_name="demo.add",
                test_qualified_name="tests.test_demo.test_add_negative",
                test_file_path="tests/test_demo.py",
                test_line=5,
            ),
            IndexEntry(
                source_qualified_name="demo.add",
                test_qualified_name="tests.test_demo.test_add",
                test_file_path="tests/test_demo.py",
                test_line=2,
            )
        ]
    )

    assert index.has_tests_for("demo.add") is True
    assert index.has_tests_for("demo.multiply") is False

    assert [
        entry.test_qualified_name
        for entry in index.tests_for("demo.add")
    ] == [
        "tests.test_demo.test_add",
        "tests.test_demo.test_add_negative",
    ]

def test_index_python_project_collects_multiple_test_files(tmp_path):
    source_symbols = [
        SourceSymbol(
            name="add",
            qualified_name="demo.add",
            kind=SymbolKind.FUNCTION,
            file_path="demo.py",
            signature="add(a: int, b: int) -> int",
            start_line=1,
            end_line=2,
        ),
        SourceSymbol(
            name="subtract",
            qualified_name="demo.subtract",
            kind=SymbolKind.FUNCTION,
            file_path="demo.py",
            signature="subtract(a: int, b: int) -> int",
            start_line=4,
            end_line=5,
        )
    ]

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    # 故意先创建名称靠后的文件，验证结果不依赖创建顺序
    (tests_dir / "test_subtract.py").write_text(
        (
            "from demo import subtract\n"
            "\n"
            "def test_subtract() -> None:\n"
            "    assert subtract(3, 1) == 2\n"
        ),
        encoding="utf-8",
    )

    (tests_dir / "test_add.py").write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add() -> None:\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    index = index_python_project_tests(
        project_root=str(tmp_path),
        source_symbols=source_symbols,
    )

    assert index.has_tests_for("demo.add") is True
    assert index.has_tests_for("demo.subtract") is True

    assert [
        entry.test_qualified_name
        for entry in index.entries
    ] == [
        "tests.test_add.test_add",
        "tests.test_subtract.test_subtract",
    ]

def test_filter_symbols_excludes_already_tested_symbol():
    add_symbol = SourceSymbol(
        name="add",
        qualified_name="demo.add",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="add(a: int, b: int) -> int",
        start_line=1,
        end_line=2,
    )

    subtract_symbol = SourceSymbol(
        name="subtract",
        qualified_name="demo.subtract",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="subtract(a: int, b: int) -> int",
        start_line=4,
        end_line=5,
    )

    index = Index(
        entries=[
            IndexEntry(
                source_qualified_name="demo.add",
                test_qualified_name="tests.test_demo.test_add",
                test_file_path="tests/test_demo.py",
                test_line=3,
            )
        ]
    )

    remaining_symbols = (
        filter_symbols_without_existing_tests(
            source_symbols=[
                add_symbol,
                subtract_symbol,
            ],
            test_index=index,
        )
    )

    assert [
        symbol.qualified_name for symbol in remaining_symbols
    ] == ["demo.subtract"]


def _service_rule_symbol(
    qualified_name: str = "app.service.Service.rule",
) -> SourceSymbol:
    owner_name = qualified_name.rsplit(".", 2)[-2]
    return SourceSymbol(
        name="rule",
        qualified_name=qualified_name,
        kind=SymbolKind.METHOD,
        file_path="app/service.py",
        signature="rule(self, values: dict) -> bool",
        start_line=2,
        end_line=3,
        owner_class=owner_name,
        parent_qualified_name=qualified_name.rsplit(".", 1)[0],
    )


def test_index_maps_self_attribute_created_in_setup_method(
    tmp_path,
):
    test_path = tmp_path / "test_service.py"
    test_path.write_text(
        (
            "from app.service import Service\n"
            "\n"
            "class TestService:\n"
            "    def setup_method(self):\n"
            "        self.service = Service()\n"
            "\n"
            "    def test_rule(self):\n"
            "        assert self.service.rule({}) is False\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_service",
        project_root=str(tmp_path),
        source_symbols=[_service_rule_symbol()],
    )

    assert entries == [
        IndexEntry(
            source_qualified_name=(
                "app.service.Service.rule"
            ),
            test_qualified_name=(
                "tests.test_service."
                "TestService.test_rule"
            ),
            test_file_path="test_service.py",
            test_line=7,
        )
    ]


def test_index_maps_local_instance_created_in_test(tmp_path):
    test_path = tmp_path / "test_service.py"
    test_path.write_text(
        (
            "from app.service import Service\n"
            "\n"
            "def test_rule():\n"
            "    service = Service()\n"
            "    assert service.rule({}) is False\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_service",
        project_root=str(tmp_path),
        source_symbols=[_service_rule_symbol()],
    )

    assert [entry.source_qualified_name for entry in entries] == [
        "app.service.Service.rule",
    ]


def test_index_maps_instance_created_from_import_alias(tmp_path):
    test_path = tmp_path / "test_service.py"
    test_path.write_text(
        (
            "from app.service import Service as Subject\n"
            "\n"
            "def test_rule():\n"
            "    service = Subject()\n"
            "    assert service.rule({}) is False\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_service",
        project_root=str(tmp_path),
        source_symbols=[_service_rule_symbol()],
    )

    assert [entry.source_qualified_name for entry in entries] == [
        "app.service.Service.rule",
    ]


def test_index_does_not_guess_method_owner_from_name(tmp_path):
    test_path = tmp_path / "test_service.py"
    test_path.write_text(
        (
            "def test_rule(unknown_service):\n"
            "    assert unknown_service.rule({}) is False\n"
        ),
        encoding="utf-8",
    )

    entries = index_python_test_file(
        file_path=str(test_path),
        module_name="tests.test_service",
        project_root=str(tmp_path),
        source_symbols=[
            _service_rule_symbol(),
            _service_rule_symbol(
                "app.other.OtherService.rule"
            ),
        ],
    )

    assert entries == []
