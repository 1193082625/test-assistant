"""pytest 套件执行产生的稳定分诊事件模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .diagnosis import DiagnosisLocation

if TYPE_CHECKING:
    from core.executors.base import ExecutionReport
    from .diagnosis import Diagnosis


class TriagePhase(StrEnum):
    """问题发生的 pytest 生命周期阶段。"""

    COLLECTION = "collection"
    EXECUTION = "execution"
    WARNING = "warning"


class ContractMigrationType(StrEnum):
    CONFIG_DEFAULT = "config_default"
    FIELD_TYPE = "field_type"
    OPTIONAL_FIELDS = "optional_fields"
    RELATED_CONFIG = "related_config"
    ENUM_VALUES = "enum_values"
    ASYNC_MOCK_RESULT = "async_mock_result"
    ASYNC_GENERATOR_LIFECYCLE = "async_generator_lifecycle"


@dataclass(frozen=True)
class ContractMigrationEvidence:
    """已经过当前契约与历史门禁的结构化迁移证据。"""

    migration_type: ContractMigrationType
    target: str
    old_contract: str
    current_contract: str
    current_sources: tuple[str, ...]
    migration_commit: str | None = None
    current_consistent: bool = False
    history_confirmed: bool = False
    runtime_boundary_confirmed: bool = False
    warning_source: str | None = None
    lifecycle_gap: tuple[str, ...] = ()
    conflict_reason: str | None = None

    @property
    def is_runtime_boundary(self) -> bool:
        return self.migration_type in {
            ContractMigrationType.ASYNC_MOCK_RESULT,
            ContractMigrationType.ASYNC_GENERATOR_LIFECYCLE,
        }

    @property
    def high_confidence(self) -> bool:
        if self.conflict_reason or not self.current_consistent:
            return False
        if self.is_runtime_boundary:
            return self.runtime_boundary_confirmed and bool(
                self.warning_source
            )
        return (
            self.history_confirmed
            and self.migration_commit is not None
            and len(set(self.current_sources)) >= 2
        )


@dataclass(frozen=True)
class PytestIssue:
    """从 pytest hook 事件转换得到的一条稳定分诊记录。"""

    phase: TriagePhase
    outcome: str
    message: str
    node_id: str | None = None
    stage: str | None = None
    exception_type: str | None = None
    locations: tuple[DiagnosisLocation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.phase, TriagePhase):
            raise ValueError("PytestIssue phase 必须是 TriagePhase")
        if not isinstance(self.outcome, str) or not self.outcome.strip():
            raise ValueError("PytestIssue outcome 不能为空")
        if not isinstance(self.message, str):
            raise ValueError("PytestIssue message 必须是字符串")

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "outcome": self.outcome,
            "message": self.message,
            "node_id": self.node_id,
            "stage": self.stage,
            "exception_type": self.exception_type,
            "locations": [location.to_dict() for location in self.locations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PytestIssue":
        locations = data.get("locations", [])
        if not isinstance(locations, list):
            raise ValueError("PytestIssue locations 必须是列表")
        return cls(
            phase=TriagePhase(data["phase"]),
            outcome=data["outcome"],
            message=data.get("message", ""),
            node_id=data.get("node_id"),
            stage=data.get("stage"),
            exception_type=data.get("exception_type"),
            locations=tuple(
                DiagnosisLocation.from_dict(location)
                for location in locations
            ),
        )


@dataclass(frozen=True)
class FailureCluster:
    """共享同一稳定失败模式的一组 pytest 问题。"""

    fingerprint: str
    representative_node: str | None
    issues: tuple[PytestIssue, ...]
    root_cause_key: str | None = None
    root_cause_target: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.fingerprint, str) or not self.fingerprint:
            raise ValueError("FailureCluster fingerprint 不能为空")
        if not self.issues or any(
            not isinstance(issue, PytestIssue) for issue in self.issues
        ):
            raise ValueError("FailureCluster issues 必须包含 PytestIssue")

    def to_dict(self) -> dict[str, object]:
        return {
            "fingerprint": self.fingerprint,
            "representative_node": self.representative_node,
            "issues": [issue.to_dict() for issue in self.issues],
            "root_cause_key": self.root_cause_key,
            "root_cause_target": self.root_cause_target,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "FailureCluster":
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            raise ValueError("FailureCluster issues 必须是列表")
        return cls(
            fingerprint=data["fingerprint"],
            representative_node=data.get("representative_node"),
            issues=tuple(PytestIssue.from_dict(issue) for issue in issues),
            root_cause_key=data.get("root_cause_key"),
            root_cause_target=data.get("root_cause_target"),
        )


@dataclass(frozen=True)
class TriageResult:
    """一次已有测试套件分诊的稳定结果。"""

    run_id: str
    report: ExecutionReport
    clusters: tuple[FailureCluster, ...]
    diagnoses: tuple[Diagnosis, ...]
