"""pytest 套件执行产生的稳定分诊事件模型。"""

from dataclasses import dataclass
from enum import StrEnum

from .diagnosis import DiagnosisLocation


class TriagePhase(StrEnum):
    """问题发生的 pytest 生命周期阶段。"""

    COLLECTION = "collection"
    EXECUTION = "execution"
    WARNING = "warning"


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
