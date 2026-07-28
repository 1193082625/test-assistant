"""稳定枚举和领域模型"""

from .enums import (
    Language,
    ProjectType,
    TestFramework,
    SymbolKind,
    TestabilityStatus,
    EvidenceKind,
    EvidenceStrength,
    TestSelectionMode,
    TestSpecStatus,
)
from .project import (
    FrameworkInfo,
    ProjectAnalysis,
    ProjectModule,
)
from .source import (
    SourceSymbol,
    ImportReference,
    TestabilityAssessment,
    TestIndexEntry,
    TestIndex,
    ContractEvidence
)

from .impact import TestSelection

from .test_spec import ExpectationEvidence, TestSpec

__all__ = [
    "FrameworkInfo",
    "Language",
    "ProjectAnalysis",
    "ProjectModule",
    "ProjectType",
    "TestFramework",
    "SymbolKind",
    "SourceSymbol",
    "ImportReference",
    "TestabilityAssessment",
    "TestabilityStatus",
    "TestIndexEntry",
    "TestIndex",
    "EvidenceKind",
    "EvidenceStrength",
    "ContractEvidence",
    "TestSelectionMode",
    "TestSelection",
    "TestSpecStatus",
    "ExpectationEvidence",
    "TestSpec",
]