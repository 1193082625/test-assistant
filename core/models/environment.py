"""环境诊断的稳定领域模型"""

from enum import StrEnum
from dataclasses import dataclass


class DoctorStatus(StrEnum):
    """Doctor 汇总状态"""

    HEALTHY = "healthy"
    INCOMPATIBLE = "incompatible"
    INFRA_ERROR = "infra_error"

class EnvironmentCheckState(StrEnum):
    """单项环境检查状态"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class EnvironmentCheck:
    """一个工具或环境维度的检查结果。"""

    name: str
    state: EnvironmentCheckState
    version: str | None
    executable: str | None
    required: bool
    reason: str | None = None
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
        ):
            raise ValueError(
                "name 不能为空"
            )

        if (
            not isinstance(self.state, EnvironmentCheckState)
        ):
            raise ValueError(
                "state 必须是 EnvironmentCheckState"
            )

        if (
            self.version is not None
            and (
                not isinstance(self.version, str)
                or not self.version.strip()
            )
        ):
            raise ValueError(
                "version 必须是非空字符串或 None"
            )

        if (
            self.executable is not None
            and (
                not isinstance(
                    self.executable,
                    str,
                )
                or not self.executable.strip()
            )
        ):
            raise ValueError(
                "executable 必须是非空字符串或 None"
            )

        if not isinstance(self.required, bool):
            raise ValueError(
                "required 必须是 bool"
            )

        if (
            self.state
            is not EnvironmentCheckState.AVAILABLE
            and (
                not isinstance(self.reason, str)
                or not self.reason.strip()
            )
        ):
            raise ValueError(
                "非可用状态必须包含原因"
            )

        if (
            not isinstance(
                self.capabilities,
                tuple,
            )
            or any(
                not isinstance(capability, str)
                or not capability.strip()
                for capability
                in self.capabilities
            )
        ):
            raise ValueError(
                "capabilities 必须是非空字符串组成的 tuple"
            )

@dataclass(frozen=True)
class DoctorResult:
    """一次完整、版本化的环境诊断结果。"""

    schema_version: int
    status: DoctorStatus
    test_assistant_version: str
    project_path: str
    python_implementation: str
    platform: str
    checks: tuple[EnvironmentCheck, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != 1
        ):
            raise ValueError(
                "schema_version 必须是 1"
            )

        if not isinstance(
            self.status,
            DoctorStatus,
        ):
            raise ValueError(
                "status 必须是 DoctorStatus"
            )

        for field_name, value in (
            (
                "test_assistant_version",
                self.test_assistant_version,
            ),
            (
                "project_path",
                self.project_path,
            ),
            (
                "python_implementation",
                self.python_implementation,
            ),
            (
                "platform",
                self.platform,
            ),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{field_name} 不能为空"
                )

        if (
            not isinstance(self.checks, tuple)
            or any(
                not isinstance(
                    check,
                    EnvironmentCheck,
                )
                for check in self.checks
            )
        ):
            raise ValueError(
                "checks 必须是 EnvironmentCheck 组成的 tuple"
            )

        names = [
            check.name
            for check in self.checks
        ]
        if len(names) != len(set(names)):
            raise ValueError(
                "检查名称不能重复"
            )

    def to_dict(self) -> dict[str, object]:
        """转换为稳定、JSON 可编码的公开结构。"""

        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "test_assistant_version": (
                self.test_assistant_version
            ),
            "project_path": self.project_path,
            "python_implementation": (
                self.python_implementation
            ),
            "platform": self.platform,
            "checks": [
                {
                    "name": check.name,
                    "state": check.state.value,
                    "version": check.version,
                    "executable": check.executable,
                    "required": check.required,
                    "reason": check.reason,
                    "capabilities": list(
                        check.capabilities
                    ),
                }
                for check in self.checks
            ],
        }
