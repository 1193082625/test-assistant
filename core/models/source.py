"""源码符号领域模型"""

from dataclasses import dataclass, field
from .enums import SymbolKind, TestabilityStatus


@dataclass
class SourceSymbol:
    """一个可定位、可区分上下文的源码符号"""
    name: str
    qualified_name: str
    kind: SymbolKind
    file_path: str
    signature: str
    start_line: int
    end_line: int

    owner_class: str | None = None
    parent_qualified_name: str | None = None
    decorators: list[str] = field(
        default_factory=list,
    )
    is_async: bool = False

    side_effects: list[str] = field(
        default_factory=list,
    )


# frozen=True 表示对象创建后不能修改，适合表达已经从源码提取出的事实
@dataclass(frozen=True)
class ImportReference:
    """一个稳定、可比较的 Python 导入引用"""
    module: str
    imported_name: str | None = None
    alias: str | None = None
    relative_level: int = 0


@dataclass(frozen=True)
class TestabilityAssessment:
    """一个源码符号的可测性判断"""
    symbol: SourceSymbol
    status: TestabilityStatus
    reasons: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class TestIndexEntry:
    """
    不可变的一条事实
    已有测试与源码符号之间的一条映射关系。
    多对多关系使用多条简单记录表达，
    便于查询、去重和序列化。
    """
    source_qualified_name: str
    test_qualified_name: str
    test_file_path: str
    test_line: int


@dataclass
class TestIndex:
    """
    可更新的事实集合
    已有测试索引及其查询行为
    """
    entries: list[TestIndexEntry] = field(default_factory=list)

    def has_tests_for(self, source_qualified_name: str) -> bool:
        # any() 遇到第一个 True 就会停止，不需要继续扫描后面的条目
        return any(
            entry.source_qualified_name == source_qualified_name
            for entry in self.entries
        )

    def tests_for(self, source_qualified_name: str) -> list[TestIndexEntry]:
        matched_entries = [
            entry
            for entry in self.entries
            if (
                entry.source_qualified_name == source_qualified_name
            )
        ]

        return sorted(
            matched_entries,
            key=lambda entry: (
                entry.test_qualified_name,
                entry.test_file_path,
                entry.test_line,
            ),
        )