"""失败测试的受控重复执行"""

from typing import Protocol

from core.executors.base import ExecutionReport
from core.models import (
    Diagnosis,
    DiagnosisAction,
    DiagnosisActionKind,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidence,
    DiagnosisEvidenceKind,
    DiagnosisLocation,
)
from .execution import (
    diagnose_execution_preflight,
)


class TestExecutor(Protocol):
    """重复执行服务需要的最小执行器协议"""

    def execute(
        self,
        file_path: str,
    ) -> ExecutionReport:
        ...


def repeat_test_execution(
    *,
    executor: TestExecutor,
    test_node_id: str,
    attempts: int,
) -> tuple[ExecutionReport, ...]:
    """按固定次数重复执行同一个测试节点"""

    if (
        not isinstance(test_node_id, str)
        or not test_node_id.strip()
    ):
        raise ValueError(
            "test_node_id 不能为空"
        )

    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not 1 <= attempts <= 3
    ):
        raise ValueError(
            "attempts 必须是 1 到 3 的整数"
        )

    return tuple(
        executor.execute(test_node_id)
        for _ in range(attempts)
    )


def _report_outcome(
    report: ExecutionReport,
) -> str:
    if report.successful:
        return "passed"

    if (
        report.error_type == "test_failure"
        and report.exit_code == 1
    ):
        return "failed"

    return "error"


def diagnose_repeatability(
    *,
    reports: tuple[ExecutionReport, ...],
    test_node_id: str,
) -> Diagnosis:
    """根据同一测试节点的重复报告判断稳定性。"""

    if len(reports) != 3:
        raise ValueError(
            "reports 必须包含 3 个 ExecutionReport"
        )

    if not all(
        isinstance(report, ExecutionReport)
        for report in reports
    ):
        raise ValueError(
            "reports 必须全部是 ExecutionReport"
        )

    if (
        not isinstance(test_node_id, str)
        or not test_node_id.strip()
    ):
        raise ValueError(
            "test_node_id 不能为空"
        )

    test_path, separator, symbol = (
        test_node_id.partition("::")
    )
    location = DiagnosisLocation(
        path=test_path,
        symbol=(
            symbol
            if separator and symbol
            else None
        ),
    )

    preflight_diagnoses: list[Diagnosis] = []

    for report in reports:
        preflight_diagnosis = (
            diagnose_execution_preflight(
                report=report,
                test_file=test_path,
            )
        )
        if preflight_diagnosis is not None:
            preflight_diagnoses.append(
                preflight_diagnosis
            )

    infrastructure_diagnosis = next(
        (
            diagnosis
            for diagnosis in preflight_diagnoses
            if (
                diagnosis.category
                is DiagnosisCategory.INFRA_DEFECT
            )
        ),
        None,
    )

    if infrastructure_diagnosis is not None:
        return infrastructure_diagnosis

    if preflight_diagnoses:
        return preflight_diagnoses[0]

    outcomes = tuple(
        _report_outcome(report)
        for report in reports
    )
    details = tuple(
        f"attempt_{index}={outcome}"
        for index, outcome in enumerate(
            outcomes,
            start=1,
        )
    )

    environments = tuple(
        report.environment
        for report in reports
    )
    same_known_environment = (
        bool(environments)
        and all(
            environment is not None
            for environment in environments
        )
        and all(
            environment == environments[0]
            for environment in environments
        )
    )

    evidence = (
        DiagnosisEvidence(
            kind=DiagnosisEvidenceKind.REPEAT_RUN,
            description="同一测试节点的重复执行结果",
            source="repeat_test_execution",
            details=details,
        ),
    )

    if (
        same_known_environment
        and set(outcomes) == {
            "passed",
            "failed",
        }
    ):
        return Diagnosis(
            summary="测试重复执行结果不一致",
            category=DiagnosisCategory.FLAKY,
            confidence=DiagnosisConfidence.HIGH,
            evidence=evidence,
            locations=(location,),
            suggested_actions=(
                DiagnosisAction(
                    kind=(
                        DiagnosisActionKind
                        .ISOLATE_FLAKY
                    ),
                    description=(
                        "隔离该测试并检查时间、随机性、"
                        "共享状态和外部依赖"
                    ),
                ),
            ),
        )

    return Diagnosis(
        summary="重复执行证据不足以判断 Flaky",
        evidence=evidence,
        locations=(location,),
        suggested_actions=(
            DiagnosisAction(
                kind=(
                    DiagnosisActionKind
                    .REQUEST_CONFIRMATION
                ),
                description=(
                    "检查重复执行结果和环境差异"
                ),
            ),
        ),
    )