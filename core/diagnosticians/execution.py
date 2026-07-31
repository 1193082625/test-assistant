"""根据测试执行报告执行确定性失败预检"""

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


_INFRASTRUCTURE_SUMMARIES = {
    "timeout": "测试执行超时",
    "startup_error": "测试 Runner 启动失败",
    "runner_error": "测试 Runner 执行失败",
    "parse_error": "测试 Runner 输出解析失败",
}

def _build_environment_evidence(
    report: ExecutionReport,
) -> tuple[DiagnosisEvidence, ...]:
    environment = report.environment
    if environment is None:
        return ()

    working_directory = (
        environment.working_directory
        if environment.working_directory is not None
        else "<unknown>"
    )

    return (
        DiagnosisEvidence(
            kind=(
                DiagnosisEvidenceKind.ENVIRONMENT
            ),
            description="测试执行环境摘要",
            source="execution_environment",
            details=(
                f"runner={environment.runner}",
                f"runtime={environment.runtime}",
                (
                    "runtime_version="
                    f"{environment.runtime_version}"
                ),
                (
                    "working_directory="
                    f"{working_directory}"
                ),
            ),
        ),
    )

def diagnose_execution_preflight(
    *,
    report: ExecutionReport,
    test_file: str,
) -> Diagnosis | None:
    """识别不需要业务推断的执行基础设施故障"""
    if report.timed_out:
        error_type = "timeout"
    else:
        error_type = report.error_type

    if error_type is None:
        if report.exit_code == 0:
            return None

        error_type = "missing_error_type"

    if error_type == "test_failure":
        if report.exit_code == 1:
            return None

        error_type = "inconsistent_test_failure"

    details = [
        f"error_type={error_type}",
    ]

    if report.exit_code is not None:
        details.append(
            f"exit_code={report.exit_code}"
        )

    if report.stderr.strip():
        details.append(
            f"stderr={report.stderr.strip()}"
        )

    if error_type == "no_tests_collected":
        return Diagnosis(
            summary="未收集到可执行测试",
            category=(
                DiagnosisCategory.INCONCLUSIVE
            ),
            confidence=DiagnosisConfidence.LOW,
            evidence=(
                DiagnosisEvidence(
                    kind=(
                        DiagnosisEvidenceKind
                        .TEST_VALIDATION
                    ),
                    description=(
                        "测试 Runner 未发现"
                        "可执行测试用例"
                    ),
                    source="execution_report",
                    details=tuple(details),
                ),
                # * 在这里表示把辅助函数返回的元组成员展开
                *_build_environment_evidence(report),
            ),
            locations=(
                DiagnosisLocation(
                    path=test_file,
                ),
            ),
            suggested_actions=(
                DiagnosisAction(
                    kind=DiagnosisActionKind.FIX_TEST,
                    description=(
                        "检查测试文件路径、命名规则"
                        "和测试收集配置"
                    ),
                ),
            ),
        )

    summary = _INFRASTRUCTURE_SUMMARIES.get(
        error_type
    )

    if summary is None:
        return Diagnosis(
            summary="无法识别测试执行错误",
            category=(
                DiagnosisCategory.INCONCLUSIVE
            ),
            confidence=DiagnosisConfidence.LOW,
            evidence=(
                DiagnosisEvidence(
                    kind=DiagnosisEvidenceKind.RUNNER,
                    description=(
                        "执行器返回了未知错误类型"
                    ),
                    source="execution_report",
                    details=tuple(details),
                ),
                *_build_environment_evidence(report),
            ),
            locations=(
                DiagnosisLocation(
                    path=test_file,
                ),
            ),
            suggested_actions=(
                DiagnosisAction(
                    kind=(
                        DiagnosisActionKind
                        .REQUEST_CONFIRMATION
                    ),
                    description=(
                        "检查执行报告并确认新的"
                        "错误类型应如何分类"
                    ),
                ),
            ),
        )

    return Diagnosis(
        summary=summary,
        category=DiagnosisCategory.INFRA_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=(
            DiagnosisEvidence(
                kind=DiagnosisEvidenceKind.RUNNER,
                description=summary,
                source="execution_report",
                details=tuple(details),
            ),
            *_build_environment_evidence(report),
        ),
        locations=(
            DiagnosisLocation(
                path=test_file,
            ),
        ),
        suggested_actions=(
            DiagnosisAction(
                kind=(
                    DiagnosisActionKind
                    .FIX_INFRASTRUCTURE
                ),
                description=(
                    "检查 Runner、依赖、权限、"
                    "超时配置和运行环境后重试"
                ),
            ),
        ),
    )
