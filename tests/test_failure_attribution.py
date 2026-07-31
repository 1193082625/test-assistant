from core.diagnosticians import diagnose_stable_failure
from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
)
from core.models import (
    DiagnosisActionKind,
    DiagnosisCategory,
    DiagnosisConfidence,
    EvidenceKind,
    EvidenceStrength,
    ExpectationEvidence,
    TestSpec as Spec,
    TestSpecStatus as SpecStatus,
)
from core.validators import (
    CandidateValidationResult,
    CandidateValidationStatus,
)


def test_weak_contract_cannot_prove_product_defect():
    spec = Spec(
        id="spec-demo-001",
        target_symbol="demo.add",
        behavior="返回两个整数之和",
        arrange={
            "left": 1,
            "right": 1,
        },
        action="调用 add(left, right)",
        expected={
            "return": 2,
        },
    )
    environment = ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )
    reports = tuple(
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            stderr="assert 3 == 2",
            environment=environment,
        )
        for _ in range(3)
    )
    validation_results = (
        CandidateValidationResult(
            status=CandidateValidationStatus.PASSED,
        ),
    )

    diagnosis = diagnose_stable_failure(
        spec=spec,
        reports=reports,
        validation_results=validation_results,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
        source_path="demo.py",
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.LOW
    )
    assert diagnosis.suggested_actions[0].kind is (
        DiagnosisActionKind.REQUEST_CONFIRMATION
    )
    assert diagnosis.category is not (
        DiagnosisCategory.PRODUCT_DEFECT
    )


def _strong_spec() -> Spec:
    return Spec(
        id="spec-demo-strong",
        target_symbol="demo.add",
        behavior="返回两个整数之和",
        arrange={"left": 1, "right": 1},
        action="调用 add(left, right)",
        expected={"return": 2},
        evidence=[
            ExpectationEvidence(
                kind=EvidenceKind.SCHEMA,
                content="add(1, 1) returns 2",
                strength=EvidenceStrength.STRONG,
                source_path="contract.json",
                source_line=1,
            ),
        ],
        status=SpecStatus.APPROVED,
    )


def _environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )


def _stable_failure_reports() -> tuple[
    ExecutionReport,
    ...,
]:
    environment = _environment()
    return tuple(
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            stderr="assert 3 == 2",
            environment=environment,
        )
        for _ in range(3)
    )


def test_strong_approved_contract_can_prove_product_defect():
    diagnosis = diagnose_stable_failure(
        spec=_strong_spec(),
        reports=_stable_failure_reports(),
        validation_results=(
            CandidateValidationResult(
                status=CandidateValidationStatus.PASSED,
            ),
        ),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.PRODUCT_DEFECT
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.HIGH
    )
    assert diagnosis.suggested_actions[0].kind is (
        DiagnosisActionKind.INSPECT_PRODUCT
    )
    assert diagnosis.locations[0].path == "demo.py"
    assert diagnosis.locations[0].symbol == "demo.add"


def test_failed_test_gate_is_test_defect():
    diagnosis = diagnose_stable_failure(
        spec=_strong_spec(),
        reports=_stable_failure_reports(),
        validation_results=(
            CandidateValidationResult(
                status=(
                    CandidateValidationStatus.SYNTAX_ERROR
                ),
                errors=("invalid syntax",),
            ),
        ),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.TEST_DEFECT
    )
    assert diagnosis.suggested_actions[0].kind is (
        DiagnosisActionKind.FIX_TEST
    )


def test_flaky_result_takes_priority_over_contract():
    environment = _environment()
    reports = (
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            environment=environment,
        ),
        ExecutionReport(
            exit_code=0,
            error_type=None,
            environment=environment,
        ),
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            environment=environment,
        ),
    )

    diagnosis = diagnose_stable_failure(
        spec=_strong_spec(),
        reports=reports,
        validation_results=(
            CandidateValidationResult(
                status=CandidateValidationStatus.PASSED,
            ),
        ),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
    )

    assert diagnosis.category is DiagnosisCategory.FLAKY
