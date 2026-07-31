"""测试失败诊断的稳定领域模型"""

from dataclasses import dataclass
from enum import StrEnum


class DiagnosisCategory(StrEnum):
    """测试失败的归因分类"""
    PRODUCT_DEFECT = "product_defect"
    TEST_DEFECT = "test_defect"
    INFRA_DEFECT = "infra_defect"
    FLAKY = "flaky"
    INCONCLUSIVE = "inconclusive"

class DiagnosisConfidence(StrEnum):
    """诊断结论的证据置信等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
class DiagnosisEvidenceKind(StrEnum):
    """诊断证据的来源类型。"""

    TEST_VALIDATION = "test_validation"
    RUNNER = "runner"
    EXECUTION = "execution"
    REPEAT_RUN = "repeat_run"
    CONTRACT = "contract"
    ENVIRONMENT = "environment"

@dataclass(frozen=True)
class DiagnosisEvidence:
    """支撑诊断结论的一条可审计证据。"""

    kind: DiagnosisEvidenceKind
    description: str
    source: str
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(
            self.kind,
            DiagnosisEvidenceKind,
        ):
            raise ValueError(
                "DiagnosisEvidence kind "
                "必须是 DiagnosisEvidenceKind"
            )

        if (
            not isinstance(self.description, str)
            or not self.description.strip()
        ):
            raise ValueError(
                "DiagnosisEvidence description 不能为空"
            )

        if (
            not isinstance(self.source, str)
            or not self.source.strip()
        ):
            raise ValueError(
                "DiagnosisEvidence source 不能为空"
            )

        if (
            not isinstance(self.details, tuple)
            or any(
                not isinstance(item, str)
                or not item.strip()
                for item in self.details
            )
        ):
            raise ValueError(
                "DiagnosisEvidence details "
                "必须只包含非空字符串"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "description": self.description,
            "source": self.source,
            "details": list(self.details),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "DiagnosisEvidence":
        if not isinstance(data, dict):
            raise ValueError(
                "DiagnosisEvidence 持久化数据必须是字典"
            )

        details = data.get("details", [])
        if not isinstance(details, list):
            raise ValueError(
                "DiagnosisEvidence details 必须是列表"
            )

        return cls(
            kind=DiagnosisEvidenceKind(data["kind"]),
            description=data["description"],
            source=data["source"],
            details=tuple(details),
        )


@dataclass(frozen=True)
class DiagnosisLocation:
    """诊断关联的源码或测试位置。"""

    path: str
    line: int | None = None
    column: int | None = None
    symbol: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, str)
            or not self.path.strip()
        ):
            raise ValueError(
                "DiagnosisLocation path 不能为空"
            )

        if (
            self.line is not None
            and (
            not isinstance(self.line, int)
            or isinstance(self.line, bool)
            or self.line < 1
        )
        ):
            raise ValueError(
                "DiagnosisLocation line 必须是正整数"
            )

        if (
            self.column is not None
            and (
            not isinstance(self.column, int)
            or isinstance(self.column, bool)
            or self.column < 0
        )
        ):
            raise ValueError(
                "DiagnosisLocation column 必须是非负整数"
            )

        if (
            self.symbol is not None
            and (
            not isinstance(self.symbol, str)
            or not self.symbol.strip()
        )
        ):
            raise ValueError(
                "DiagnosisLocation symbol "
                "必须是非空字符串或 None"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "symbol": self.symbol,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "DiagnosisLocation":
        if not isinstance(data, dict):
            raise ValueError(
                "DiagnosisLocation 持久化数据必须是字典"
            )

        return cls(
            path=data["path"],
            line=data.get("line"),
            column=data.get("column"),
            symbol=data.get("symbol"),
        )

class DiagnosisActionKind(StrEnum):
    """诊断建议动作的机器类型。"""

    INSPECT_PRODUCT = "inspect_product"
    FIX_TEST = "fix_test"
    FIX_INFRASTRUCTURE = "fix_infrastructure"
    RERUN = "rerun"
    ISOLATE_FLAKY = "isolate_flaky"
    REQUEST_CONFIRMATION = "request_confirmation"


@dataclass(frozen=True)
class DiagnosisAction:
    """提供给用户的结构化建议动作。"""

    kind: DiagnosisActionKind
    description: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.kind,
            DiagnosisActionKind,
        ):
            raise ValueError(
                "DiagnosisAction kind "
                "必须是 DiagnosisActionKind"
            )

        if (
            not isinstance(self.description, str)
            or not self.description.strip()
        ):
            raise ValueError(
                "DiagnosisAction description 不能为空"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "DiagnosisAction":
        if not isinstance(data, dict):
            raise ValueError(
                "DiagnosisAction 持久化数据必须是字典"
            )

        return cls(
            kind=DiagnosisActionKind(data["kind"]),
            description=data["description"],
        )

@dataclass(frozen=True)
class Diagnosis:
    """一次测试失败的结构化诊断结论"""
    summary: str
    category: DiagnosisCategory = (
        DiagnosisCategory.INCONCLUSIVE
    )
    confidence: DiagnosisConfidence = (
        DiagnosisConfidence.LOW
    )
    evidence: tuple[DiagnosisEvidence, ...] = ()
    locations: tuple[DiagnosisLocation, ...] = ()
    suggested_actions: tuple[DiagnosisAction, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.summary, str)
            or not self.summary.strip()
        ):
            raise ValueError(
                "Diagnosis summary 不能为空"
            )

        if not isinstance(
            self.category,
            DiagnosisCategory,
        ):
            raise ValueError(
                "Diagnosis category 必须是 DiagnosisCategory"
            )

        if not isinstance(
            self.confidence,
            DiagnosisConfidence,
        ):
            raise ValueError(
                "Diagnosis confidence "
                "必须是 DiagnosisConfidence"
            )

        if (
            not isinstance(self.evidence, tuple)
            or any(
                not isinstance(
                    item,
                    DiagnosisEvidence,
                )
                for item in self.evidence
            )
        ):
            raise ValueError(
                "Diagnosis evidence "
                "必须只包含 DiagnosisEvidence"
            )

        if (
            not isinstance(self.locations, tuple)
            or any(
                not isinstance(
                    item,
                    DiagnosisLocation,
                )
                for item in self.locations
            )
        ):
            raise ValueError(
                "Diagnosis locations "
                "必须只包含 DiagnosisLocation"
            )

        if (
            not isinstance(
                self.suggested_actions,
                tuple,
            )
            or any(
                not isinstance(
                    item,
                    DiagnosisAction,
                )
                for item in self.suggested_actions
            )
        ):
            raise ValueError(
                "Diagnosis suggested_actions "
                "必须只包含 DiagnosisAction"
            )

        if (
                self.category
                is not DiagnosisCategory.INCONCLUSIVE
                and not self.evidence
        ):
            raise ValueError(
                "非 INCONCLUSIVE 诊断必须包含证据"
            )

    def to_dict(self) -> dict[str, object]:
        """转换为可持久化的基础数据结构"""
        return {
            "category": self.category.value,
            "confidence": self.confidence.value,
            "summary": self.summary,
            "evidence": [
                item.to_dict()
                for item in self.evidence
            ],
            "locations": [
                item.to_dict()
                for item in self.locations
            ],
            "suggested_actions": [
                item.to_dict()
                for item in self.suggested_actions
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "Diagnosis":
        if not isinstance(data, dict):
            raise ValueError(
                "Diagnosis 持久化数据必须是字典"
            )

        evidence_data = data.get("evidence", [])
        locations_data = data.get("locations", [])
        actions_data = data.get(
            "suggested_actions",
            [],
        )

        if not isinstance(evidence_data, list):
            raise ValueError(
                "Diagnosis evidence 必须是列表"
            )

        if not isinstance(locations_data, list):
            raise ValueError(
                "Diagnosis locations 必须是列表"
            )

        if not isinstance(actions_data, list):
            raise ValueError(
                "Diagnosis suggested_actions 必须是列表"
            )

        return cls(
            summary=data["summary"],
            category=DiagnosisCategory(
                data["category"]
            ),
            confidence=DiagnosisConfidence(
                data["confidence"]
            ),
            evidence=tuple(
                DiagnosisEvidence.from_dict(item)
                for item in evidence_data
            ),
            locations=tuple(
                DiagnosisLocation.from_dict(item)
                for item in locations_data
            ),
            suggested_actions=tuple(
                DiagnosisAction.from_dict(item)
                for item in actions_data
            ),
        )