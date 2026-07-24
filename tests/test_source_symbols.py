from core.models import SourceSymbol, SymbolKind
from core.analyzers.source import analyze_python_symbols

def test_source_symbol_distinguishes_function_contexts():
    top_level = SourceSymbol(
        name="load",
        qualified_name="demo.load", # 是限定名，用完整上下文标识符号
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="load(path: str) -> str",
        start_line=1,
        end_line=3,
    )

    method = SourceSymbol(
        name="load",
        qualified_name="demo.Service.load",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="load(self, path: str) -> str",
        start_line=6,
        end_line=8,
        owner_class="Service",
    )

    nested = SourceSymbol(
        name="normalize",
        qualified_name="demo.load.normalize",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="normalize(path: str) -> str",
        start_line=10,
        end_line=11,
        parent_qualified_name="demo.load",
    )

    async_function = SourceSymbol(
        name="fetch",
        qualified_name="demo.fetch",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="async fetch(url: str) -> bytes",
        start_line=14,
        end_line=16,
        is_async=True,
    )

    assert top_level.owner_class is None
    assert method.owner_class == "Service"
    assert nested.parent_qualified_name == "demo.load"
    assert async_function.is_async is True

    assert len({
        top_level.qualified_name,
        method.qualified_name,
        nested.qualified_name,
        async_function.qualified_name,
    }) == 4

def test_analyze_python_symbols_extracts_top_level_function(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def load(path: str) -> str:\n"
            "    return path\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(
        file_path=str(source_path),
        module_name="demo",
    )

    assert len(symbols) == 1

    symbol = symbols[0]
    assert symbol.name == "load"
    assert symbol.qualified_name == "demo.load"
    assert symbol.kind == SymbolKind.FUNCTION
    assert symbol.file_path == str(source_path)
    assert symbol.signature == "load(path: str) -> str"
    assert symbol.start_line == 1
    assert symbol.end_line == 2
    assert symbol.owner_class is None
    assert symbol.parent_qualified_name is None
    assert symbol.is_async is False

def test_analyze_python_symbols_extracts_class_method(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "class Service:\n"
            "    @classmethod\n"
            "    def load(cls, path: str) -> str:\n"
            "        return path\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(file_path=str(source_path), module_name="demo")

    symbols_by_name = {
        symbol.qualified_name: symbol
        for symbol in symbols
    }

    assert set(symbols_by_name) == {
        "demo.Service",
        "demo.Service.load",
    }

    class_symbol = symbols_by_name["demo.Service"]
    assert class_symbol.kind is SymbolKind.CLASS
    assert class_symbol.signature == "class Service"
    assert class_symbol.start_line == 1
    assert class_symbol.end_line == 4

    method = symbols_by_name["demo.Service.load"]
    assert method.kind is SymbolKind.METHOD
    assert method.owner_class == "Service"
    assert method.parent_qualified_name == "demo.Service"
    assert method.signature == (
        "load(cls, path: str) -> str"
    )
    assert method.decorators == ["classmethod"]

    # 方法范围从装饰器开始，而不是从 def 开始
    assert method.start_line == 2
    assert method.end_line == 4

def test_analyze_python_symbols_preserves_nested_function(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def outer(value: str) -> str:\n"
            "    def normalize(item: str) -> str:\n"
            "        return item.strip()\n"
            "    return normalize(value)\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(
        file_path=str(source_path),
        module_name="demo",
    )

    symbols_by_name = {
        symbol.qualified_name: symbol for symbol in symbols
    }

    assert set(symbols_by_name) == {
        "demo.outer",
        "demo.outer.normalize",
    }

    outer = symbols_by_name["demo.outer"]
    assert outer.parent_qualified_name is None

    nested = symbols_by_name["demo.outer.normalize"]
    assert nested.kind is SymbolKind.FUNCTION
    assert nested.parent_qualified_name == "demo.outer"
    assert nested.owner_class is None
    assert nested.signature == "normalize(item: str) -> str"

    assert nested.start_line == 2
    assert nested.end_line == 3

def test_analyze_python_symbols_distinguishes_async_symbols(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "async def fetch(url: str) -> bytes:\n"
            "    return b'data'\n"
            "\n"
            "class Client:\n"
            "    @staticmethod\n"
            "    async def request(url: str) -> bytes:\n"
            "        return await fetch(url)\n"
        ),
        encoding="utf-8",
    )

    symbols = analyze_python_symbols(
        file_path=str(source_path),
        module_name="demo",
    )

    symbols_by_name = {
        symbol.qualified_name: symbol
        for symbol in symbols
    }

    fetch = symbols_by_name["demo.fetch"]
    assert fetch.kind is SymbolKind.FUNCTION
    assert fetch.is_async is True
    assert fetch.signature == "async fetch(url: str) -> bytes"

    request = symbols_by_name["demo.Client.request"]
    assert request.kind is SymbolKind.METHOD
    assert request.owner_class == "Client"
    assert request.is_async is True
    assert request.decorators == ["staticmethod"]
    assert request.signature == "async request(url: str) -> bytes"
    assert request.start_line == 5
    assert request.end_line == 7