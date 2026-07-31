"""
将稳定测试失败与契约和测试门禁证据关联。
attribution 归因，归属
"""

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
    EvidenceStrength,
    TestSpec,
    TestSpecStatus,
)
from core.validators import (
    CandidateValidationResult,
    CandidateValidationStatus,
)

from .repeatability import diagnose_repeatability


_TEST_DEFECT_STATUSES = {
    CandidateValidationStatus.EMPTY,
    CandidateValidationStatus.INVALID_STRUCTURE,
    CandidateValidationStatus.SYNTAX_ERROR,
    CandidateValidationStatus.IMPORT_ERROR,
    CandidateValidationStatus.COLLECTION_ERROR,
}

_INFRA_DEFECT_STATUSES = {
    CandidateValidationStatus.RUNNER_ERROR,
    CandidateValidationStatus.TIMEOUT,
}


def _validation_details(
    validation_results: tuple[
        CandidateValidationResult,
        ...,
    ],
) -> tuple[str, ...]:
    return tuple(
        f"gate_{index}={result.status.value}"
        for index, result in enumerate(
            validation_results,
            start=1,
        )
    )


def _validation_diagnosis(
    *,
    validation_results: tuple[
        CandidateValidationResult,
        ...,
    ],
    test_node_id: str,
) -> Diagnosis | None:
    statuses = {
        result.status
        for result in validation_results
    }
    evidence = (
        DiagnosisEvidence(
            kind=DiagnosisEvidenceKind.TEST_VALIDATION,
            description="候选测试门禁结果",
            source="candidate_validation",
            details=_validation_details(validation_results),
        ),
    )
    test_path, _, symbol = test_node_id.partition("::")
    location = DiagnosisLocation(
        path=test_path,
        symbol=symbol or None,
    )

    if statuses & _INFRA_DEFECT_STATUSES:
        return Diagnosis(
            summary="测试门禁基础设施执行失败",
            category=DiagnosisCategory.INFRA_DEFECT,
            confidence=DiagnosisConfidence.HIGH,
            evidence=evidence,
            locations=(location,),
            suggested_actions=(
                DiagnosisAction(
                    kind=(
                        DiagnosisActionKind
                        .FIX_INFRASTRUCTURE
                    ),
                    description=(
                        "修复 Runner、超时或执行环境后重试"
                    ),
                ),
            ),
        )

    if statuses & _TEST_DEFECT_STATUSES:
        return Diagnosis(
            summary="候选测试未通过确定性测试门禁",
            category=DiagnosisCategory.TEST_DEFECT,
            confidence=DiagnosisConfidence.HIGH,
            evidence=evidence,
            locations=(location,),
            suggested_actions=(
                DiagnosisAction(
                    kind=DiagnosisActionKind.FIX_TEST,
                    description=(
                        "修复测试结构、语法、导入或收集问题"
                    ),
                ),
            ),
        )

    return None


def diagnose_stable_failure(
    *,
    spec: TestSpec,
    reports: tuple[ExecutionReport, ...],
    validation_results: tuple[
        CandidateValidationResult,
        ...,
    ],
    test_node_id: str,
    source_path: str,
) -> Diagnosis:
    """基于契约、门禁和重复执行证据归因测试失败。"""

    if not isinstance(spec, TestSpec):
        raise ValueError("spec 必须是 TestSpec")
    if (
        not isinstance(validation_results, tuple)
        or any(
            not isinstance(
                result,
                CandidateValidationResult,
            )
            for result in validation_results
        )
    ):
        raise ValueError(
            "validation_results 必须只包含 "
            "CandidateValidationResult"
        )
    if (
        not isinstance(source_path, str)
        or not source_path.strip()
    ):
        raise ValueError("source_path 不能为空")

    validation_diagnosis = _validation_diagnosis(
        validation_results=validation_results,
        test_node_id=test_node_id,
    )
    if validation_diagnosis is not None:
        return validation_diagnosis

    repeatability = diagnose_repeatability(
        reports=reports,
        test_node_id=test_node_id,
    )
    if repeatability.category in {
        DiagnosisCategory.INFRA_DEFECT,
        DiagnosisCategory.FLAKY,
    }:
        return repeatability

    all_gates_passed = (
        bool(validation_results)
        and all(
            result.passed
            for result in validation_results
        )
    )
    stable_assertion_failure = all(
        report.exit_code == 1
        and report.error_type == "test_failure"
        for report in reports
    )
    environments = tuple(
        report.environment
        for report in reports
    )
    same_known_environment = (
        all(
            environment is not None
            for environment in environments
        )
        and all(
            environment == environments[0]
            for environment in environments
        )
    )

    evidence = (
        *repeatability.evidence,
        DiagnosisEvidence(
            kind=DiagnosisEvidenceKind.CONTRACT,
            description="TestSpec 预期契约证据",
            source="test_spec",
            details=(
                f"spec_id={spec.id}",
                (
                    "expectation_strength="
                    f"{spec.expectation_strength.value}"
                ),
                f"spec_status={spec.status.value}",
                f"target_symbol={spec.target_symbol}",
            ),
        ),
        DiagnosisEvidence(
            kind=DiagnosisEvidenceKind.TEST_VALIDATION,
            description="候选测试门禁结果",
            source="candidate_validation",
            details=_validation_details(validation_results),
        ),
    )
    locations = (
        DiagnosisLocation(
            path=source_path,
            symbol=spec.target_symbol,
        ),
        *repeatability.locations,
    )

    if (
        spec.status is TestSpecStatus.APPROVED
        and spec.expectation_strength
        is EvidenceStrength.STRONG
        and all_gates_passed
        and stable_assertion_failure
        and same_known_environment
    ):
        return Diagnosis(
            summary="产品行为违反已批准的强契约预期",
            category=DiagnosisCategory.PRODUCT_DEFECT,
            confidence=DiagnosisConfidence.HIGH,
            evidence=evidence,
            locations=locations,
            suggested_actions=(
                DiagnosisAction(
                    kind=(
                        DiagnosisActionKind
                        .INSPECT_PRODUCT
                    ),
                    description=(
                        "检查目标实现与强契约不一致的原因"
                    ),
                ),
            ),
        )

    return Diagnosis(
        summary="稳定失败的证据不足以证明产品缺陷",
        category=DiagnosisCategory.INCONCLUSIVE,
        confidence=DiagnosisConfidence.LOW,
        evidence=evidence,
        locations=locations,
        suggested_actions=(
            DiagnosisAction(
                kind=(
                    DiagnosisActionKind
                    .REQUEST_CONFIRMATION
                ),
                description=(
                    "人工确认 TestSpec、契约证据和测试预期"
                ),
            ),
        ),
    )
