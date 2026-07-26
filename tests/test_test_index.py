from core.models import TestIndexEntry as IndexEntry
from core.analyzers.source import analyze_python_test_symbols

def test_test_index_entry_maps_test_to_source_symbol():
    entry = IndexEntry(
        source_qualified_name="demo.add",
        test_qualified_name="test.test_demo.test_add",
        test_file_path="tests/test_demo.py",
        test_line=4,
    )

    assert entry.source_qualified_name == "demo.add"
    assert entry.test_qualified_name == "test.test_demo.test_add"
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
        module_name="test.test_demo",
    )

    assert [
        symbol.qualified_name
        for symbol in symbols
    ] == ["test.test_demo.test_add"]