from core.analyzers.source import classify_symbol_testability, analyze_python_symbols

from core.models import SourceSymbol, SymbolKind, TestabilityStatus as Status

def test_public_top_level_function_is_directly_testable():
    symbol = SourceSymbol(
        name="calculate",
        qualified_name="demo.calculate",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="calculate(value: int) -> int",
        start_line=1,
        end_line=2,
    )

    assessment = classify_symbol_testability(symbol)

    assert assessment.status is Status.DIRECT
    assert assessment.reasons == []

def test_nested_function_is_not_directly_importable():
    symbol = SourceSymbol(
        name="normalize",
        qualified_name="demo.outer.normalize",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="normalize(value: str) -> str",
        start_line=2,
        end_line=3,
        parent_qualified_name="demo.outer",
    )

    assessment = classify_symbol_testability(symbol)

    assert (
        assessment.status
        is Status.NOT_DIRECT
    )
    assert assessment.reasons == [
        "嵌套函数不能通过模块路径直接导入"
    ]

def test_class_is_not_direct_but_public_method_is():
    class_symbol = SourceSymbol(
        name="Calculator",
        qualified_name="demo.Calculator",
        kind=SymbolKind.CLASS,
        file_path="demo.py",
        signature="class Calculator",
        start_line=1,
        end_line=6,
    )

    method_symbol = SourceSymbol(
        name="add",
        qualified_name="demo.Calculator.add",
        kind=SymbolKind.METHOD,
        file_path="demo.py",
        signature="add(self, a: int, b: int) -> int",
        start_line=2,
        end_line=3,
        owner_class="Calculator",
        parent_qualified_name="demo.Calculator",
    )

    class_assessment = classify_symbol_testability(class_symbol)
    method_assessment = classify_symbol_testability(method_symbol)

    assert class_assessment.status is Status.NOT_DIRECT
    assert class_assessment.reasons == [
        "类本身不是可直接执行的测试入口"
    ]

    assert method_assessment.status is Status.DIRECT
    assert method_assessment.reasons == []

def test_private_function_is_not_direct():
    """测试 私有函数不作为直接测试入口"""
    symbol = SourceSymbol(
        name="_normalize",
        qualified_name="demo._normalize",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="_normalize(value: str) -> str",
        start_line=1,
        end_line=2,
    )

    assessment = classify_symbol_testability(symbol)

    assert assessment.status is Status.NOT_DIRECT
    assert assessment.reasons == [
        "私有符号默认不作为直接测试入口"
    ]

def test_filesystem_side_effect_needs_isolation():
    """
    测试一个会访问文件系统的函数
    区分“不能直接测试”和“可以测试，但需要隔离副作用”
    """
    symbol = SourceSymbol(
        name="load_config",
        qualified_name="demo.load_config",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="def load_config(path: str) -> dict",
        start_line=1,
        end_line=3,
        side_effects=["filesystem"]
    )

    assessment = classify_symbol_testability(symbol)
    assert assessment.status is Status.NEEDS_ISOLATION
    assert assessment.reasons == [
        "符号包含 filesystem 副作用，需要隔离后测试"
    ]


def test_analyzer_detects_filesystem_side_effect(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def load_config(path: str) -> str:\n"
            "  with open(path, encoding='utf-8') as f:\n"
            "    return f.read()\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(
        file_path=str(source_path),
        module_name="demo"
    )
    symbol_by_name = {
        symbol.qualified_name: symbol
        for symbol in symbols
    }
    symbol = symbol_by_name["demo.load_config"]
    assert symbol.side_effects == ["filesystem"]

    assessment = classify_symbol_testability(symbol)

    assert assessment.status is Status.NEEDS_ISOLATION
    assert assessment.reasons == [
        "符号包含 filesystem 副作用，需要隔离后测试"
    ]

def test_analyzer_detects_subprocess_side_effect(tmp_path):
    """测试 启动外部进程"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "import subprocess\n"
            "\n"
            "def run_tests() -> int:\n"
            "    result = subprocess.run(['pytest'])\n"
            "    return result.returncode\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(
        file_path=str(source_path),
        module_name="demo"
    )

    symbol_by_name = {
        symbol.qualified_name: symbol
        for symbol in symbols
    }
    symbol = symbol_by_name["demo.run_tests"]

    assert symbol.side_effects == ["subprocess"]

    assessment = classify_symbol_testability(symbol)
    assert assessment.status is Status.NEEDS_ISOLATION
    assert assessment.reasons == [
        "符号包含 subprocess 副作用，需要隔离后测试"
    ]

def test_nested_function_side_effect_does_not_pollute_parent(tmp_path):
    """测试 嵌套函数的副作用不能污染外层函数"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def outer() -> None:\n"
            "    def write_file(path: str) -> None:\n"
            "        with open(path, 'w') as file:\n"
            "            file.write('data')\n"
            "    write_file('result.txt')\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(
        file_path=str(source_path),
        module_name="demo"
    )
    symbol_by_name = {
        symbol.qualified_name: symbol
        for symbol in symbols
    }
    outer = symbol_by_name["demo.outer"]
    write_file = symbol_by_name["demo.outer.write_file"]
    assert outer.side_effects == []
    assert write_file.side_effects == ["filesystem"]