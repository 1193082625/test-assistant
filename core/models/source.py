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