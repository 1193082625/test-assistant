"""覆盖率与代码质量审计的稳定领域模型"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class CoverageSummary:
    """一次覆盖率采集的语句和分支计数"""

    statements_covered: int
    statements_total: int
    branches_covered: int
    branches_total: int

    def __post_init__(self) -> None:
        if (
            self.statements_covered < 0
            or self.statements_total < 0
            or self.branches_covered < 0
            or self.branches_total < 0
        ):
            raise ValueError("不能为负数")

        if (
            self.statements_covered > self.statements_total
            or self.branches_covered > self.branches_total
        ):
            raise ValueError("不能大于总数")

    @property
    def statement_rate(self) -> float | None:
        """动态计算语句覆盖率"""

        if self.statements_total == 0:
            return None

        return self.statements_covered / self.statements_total

    @property
    def branch_rate(self) -> float | None:
        if self.branches_total == 0:
            return None

        return self.branches_covered / self.branches_total


class CoverageState(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    UNCOVERED = "uncovered"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SymbolCoverage:
    """一个源码符号的覆盖事实和具体缺口"""

    source_path: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    summary: CoverageSummary
    missing_lines: tuple[int, ...]
    missing_branches: tuple[tuple[int, int], ...]

    @property
    def state(self) -> CoverageState:
        if self.summary.statements_total == 0:
            return CoverageState.NOT_APPLICABLE
        if self.summary.statements_covered == 0:
            return CoverageState.UNCOVERED
        if (
            self.summary.statements_covered == self.summary.statements_total
            and self.summary.branches_covered == self.summary.branches_total
        ):
            return CoverageState.FULL
        return CoverageState.PARTIAL

    def __post_init__(self) -> None:
        if not isinstance(self.source_path, str) or not self.source_path:
            raise ValueError("source_path 不能为空")

        if not isinstance(self.qualified_name, str) or not self.qualified_name:
            raise ValueError("qualified_name 不能为空")

        if (
            not isinstance(self.start_line, int)
            or self.start_line <= 0
        ):
            raise ValueError("start_line 必须大于等于 1")

        if (
            not isinstance(self.end_line, int)
            or self.end_line < self.start_line
        ):
            raise ValueError("end_line 不能小于 start_line")
        if any(
            line < self.start_line or line > self.end_line
            for line in self.missing_lines
        ):
            raise ValueError("missing_lines 必须位于符号范围内")


class ToolState(StrEnum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ToolStatus:
    tool: str
    state: ToolState
    version: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool, str) or not self.tool.strip():
            raise ValueError("tool 不能为空")

        if not isinstance(self.state, ToolState):
            raise ValueError("state 必须是 ToolState")

        unsuccessful_states = {
            ToolState.UNAVAILABLE,
            ToolState.TIMED_OUT,
            ToolState.FAILED,
        }
        if (
            self.state in unsuccessful_states
            and (
                not isinstance(self.reason, str)
                or not self.reason.strip()
            )
        ):
            raise ValueError("未成功状态必须包含原因")


class QualityFindingKind(StrEnum):
    CODE = "code"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"


@dataclass(frozen=True)
class QualityFinding:
    tool: str
    kind: QualityFindingKind
    rule_code: str | None
    message: str
    source_path: str | None
    line: int | None
    column: int | None
    fix_available: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tool, str)
            or not self.tool.strip()
        ):
            raise ValueError("tool 不能为空")

        if (
            not isinstance(self.message, str)
            or not self.message.strip()
        ):
            raise ValueError("message 不能为空")

        if not isinstance(self.kind, QualityFindingKind):
            raise ValueError("kind 必须是 QualityFindingKind")

        if (
            self.kind is QualityFindingKind.CODE
            and (
                not self.source_path
                or not self.line
            )
        ):
            raise ValueError("代码问题必须包含有效源码位置")

        if self.column is not None and (
            not isinstance(self.column, int)
            or self.column <= 0
        ):
            raise ValueError("column 必须大于等于 1")

        if not isinstance(self.fix_available, bool):
            raise ValueError("fix_available 必须是 bool")


class AuditStatus(StrEnum):
    PASSED = "passed"
    THRESHOLD_FAILED = "threshold_failed"
    TESTS_FAILED = "tests_failed"
    PARTIAL = "partial"
    INFRA_ERROR = "infra_error"


@dataclass(frozen=True)
class AuditThresholds:
    """用户显式提供的审计门禁；None 表示不启用该门禁。"""

    statement_rate: float | None = None
    branch_rate: float | None = None
    max_ruff_findings: int | None = None
    max_mypy_errors: int | None = None

    def __post_init__(self) -> None:
        for field, value in (
            ("statement_rate", self.statement_rate),
            ("branch_rate", self.branch_rate),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{field} 必须位于 0 到 1 之间")

        for field, value in (
            ("max_ruff_findings", self.max_ruff_findings),
            ("max_mypy_errors", self.max_mypy_errors),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(f"{field} 必须是非负整数")


@dataclass(frozen=True)
class AuditResult:
    run_id: str
    status: AuditStatus
    command: tuple[str, ...]
    coverage: CoverageSummary | None
    symbols: tuple[SymbolCoverage, ...]
    findings: tuple[QualityFinding, ...]
    tools: tuple[ToolStatus, ...]
    source_digest: str
    thresholds: AuditThresholds | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id 不能为空")

        if (
            not isinstance(self.source_digest, str)
            or not self.source_digest.strip()
        ):
            raise ValueError("source_digest 不能为空")

        if (
            not isinstance(self.command, tuple)
            or not self.command
            or any(
                not isinstance(part, str) or not part.strip()
                for part in self.command
            )
        ):
            raise ValueError("command 必须是非空命令")

        if not isinstance(self.status, AuditStatus):
            raise ValueError("status 必须是 AuditStatus")

        if (
            self.coverage is not None
            and not isinstance(
                self.coverage,
                CoverageSummary,
            )
        ):
            raise ValueError("coverage 必须是 CoverageSummary 或 None")

        if (
            not isinstance(self.symbols, tuple)
            or any(
                not isinstance(item, SymbolCoverage)
                for item in self.symbols
            )
        ):
            raise ValueError("symbols 必须包含 SymbolCoverage")

        if (
            not isinstance(self.findings, tuple)
            or any(
                not isinstance(item, QualityFinding)
                for item in self.findings
            )
        ):
            raise ValueError("findings 必须包含 QualityFinding")
        if (
            not isinstance(self.tools, tuple)
            or any(
                not isinstance(item, ToolStatus)
                for item in self.tools
            )
        ):
            raise ValueError("tools 必须包含 ToolStatus")

        if (
            self.thresholds is not None
            and not isinstance(self.thresholds, AuditThresholds)
        ):
            raise ValueError("thresholds 必须是 AuditThresholds 或 None")
