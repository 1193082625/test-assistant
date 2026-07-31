from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
)
from core.models import (
    DiagnosisCategory,
    TestSpec as Spec,
    TestSpecStatus as SpecStatus,
)
from core.validators import (
    CandidateValidationResult,
    CandidateValidationStatus,
)
from core.workflows import (
    VerificationStatus,
    verify_test_spec,
)


class FakeExecutor:
    def __init__(self, reports):
        self.reports = list(reports)
        self.executed = []

    def execute(self, file_path):
        self.executed.append(file_path)
        return self.reports.pop(0)


def _spec() -> Spec:
    return Spec(
        id="spec-demo-verify",
        target_symbol="demo.add",
        behavior="返回两个整数之和",
        arrange={"left": 1, "right": 1},
        action="调用 add(left, right)",
        expected={"return": 2},
        status=SpecStatus.APPROVED,
    )


def _environment():
    return ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )


def _passed_gate():
    return CandidateValidationResult(
        status=CandidateValidationStatus.PASSED,
    )


def test_verification_passes_without_saving_diagnosis(
    tmp_path,
):
    executor = FakeExecutor(
        [
            ExecutionReport(
                exit_code=0,
                environment=_environment(),
            )
            for _ in range(3)
        ]
    )

    result = verify_test_spec(
        project_root=tmp_path,
        spec=_spec(),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
        validation_results=(_passed_gate(),),
        executor=executor,
    )

    assert result.status is VerificationStatus.PASSED
    assert result.diagnosis is None
    assert result.record_path is None
    assert len(executor.executed) == 3
    assert not (
        tmp_path / ".autotest" / "diagnoses"
    ).exists()
    assert (
        tmp_path
        / ".autotest"
        / "verification"
        / "latest.json"
    ).is_file()


def test_verification_saves_stable_failure_diagnosis(
    tmp_path,
):
    executor = FakeExecutor(
        [
            ExecutionReport(
                exit_code=1,
                error_type="test_failure",
                environment=_environment(),
            )
            for _ in range(3)
        ]
    )

    result = verify_test_spec(
        project_root=tmp_path,
        spec=_spec(),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
        validation_results=(_passed_gate(),),
        executor=executor,
    )

    assert result.status is VerificationStatus.DIAGNOSED
    assert result.diagnosis is not None
    assert (
        result.diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert result.record_path is not None
    assert result.record_path.is_file()


def test_failed_test_gate_skips_execution_and_is_test_defect(
    tmp_path,
):
    executor = FakeExecutor([])

    result = verify_test_spec(
        project_root=tmp_path,
        spec=_spec(),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
        validation_results=(
            CandidateValidationResult(
                status=CandidateValidationStatus.SYNTAX_ERROR,
                errors=("invalid syntax",),
            ),
        ),
        executor=executor,
    )

    assert executor.executed == []
    assert result.diagnosis is not None
    assert (
        result.diagnosis.category
        is DiagnosisCategory.TEST_DEFECT
    )


def test_mixed_results_are_saved_as_flaky(tmp_path):
    environment = _environment()
    executor = FakeExecutor(
        [
            ExecutionReport(
                exit_code=1,
                error_type="test_failure",
                environment=environment,
            ),
            ExecutionReport(
                exit_code=0,
                environment=environment,
            ),
            ExecutionReport(
                exit_code=1,
                error_type="test_failure",
                environment=environment,
            ),
        ]
    )

    result = verify_test_spec(
        project_root=tmp_path,
        spec=_spec(),
        test_node_id="tests/test_demo.py::test_add",
        source_path="demo.py",
        validation_results=(_passed_gate(),),
        executor=executor,
    )

    assert result.diagnosis is not None
    assert result.diagnosis.category is DiagnosisCategory.FLAKY
