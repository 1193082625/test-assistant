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
    PlannerStatus,
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

from .impact import (
    ImpactAnalysisPrecision,
    PythonSymbolAnalysis,
    TestSelection,
)

from .test_spec import ExpectationEvidence, TestSpec, build_test_spec_id
from .planner import PlannerResult
from .diagnosis import (
    Diagnosis,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidence,
    DiagnosisEvidenceKind,
    DiagnosisLocation,
    DiagnosisAction,
    DiagnosisActionKind,
)
from .triage import PytestIssue, TriagePhase

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
    "ImpactAnalysisPrecision",
    "PythonSymbolAnalysis",
    "TestSpecStatus",
    "ExpectationEvidence",
    "TestSpec",
    "build_test_spec_id",
    "PlannerResult",
    "PlannerStatus",
    "Diagnosis",
    "DiagnosisCategory",
    "DiagnosisConfidence",
    "DiagnosisEvidence",
    "DiagnosisEvidenceKind",
    "DiagnosisLocation",
    "DiagnosisAction",
    "DiagnosisActionKind",
    "PytestIssue",
    "TriagePhase",
]
