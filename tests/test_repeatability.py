import pytest

from core.diagnosticians import (
    diagnose_repeatability,
    repeat_test_execution,
)
from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
)
from core.models import (
    DiagnosisActionKind,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidenceKind,
)


class FakeExecutor:
    def __init__(
        self,
        reports: list[ExecutionReport],
    ) -> None:
        self.reports = list(reports)
        self.executed: list[str] = []

    def execute(
        self,
        file_path: str,
    ) -> ExecutionReport:
        self.executed.append(file_path)
        return self.reports.pop(0)


def test_repeats_only_the_failed_test_node():
    reports = [
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
        ),
        ExecutionReport(
            exit_code=0,
            error_type=None,
        ),
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
        ),
    ]
    executor = FakeExecutor(reports)

    repeated = repeat_test_execution(
        executor=executor,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
        attempts=3,
    )

    assert len(repeated) == 3
    assert repeated[0].error_type == "test_failure"
    assert repeated[1].successful is True
    assert repeated[2].error_type == "test_failure"

    assert executor.executed == [
        "tests/test_demo.py::test_add",
        "tests/test_demo.py::test_add",
        "tests/test_demo.py::test_add",
    ]

@pytest.mark.parametrize(
    "attempts",
    [
        0,
        -1,
        4,
        True,
    ],
)
def test_repeat_execution_rejects_invalid_attempts(
    attempts,
):
    executor = FakeExecutor([])

    with pytest.raises(
        ValueError,
        match="attempts 必须是 1 到 3 的整数",
    ):
        repeat_test_execution(
            executor=executor,
            test_node_id=(
                "tests/test_demo.py::test_add"
            ),
            attempts=attempts,
        )

    assert executor.executed == []


@pytest.mark.parametrize(
    "test_node_id",
    [
        "",
        "   ",
    ],
)
def test_repeat_execution_rejects_empty_test_node(
    test_node_id,
):
    executor = FakeExecutor([])

    with pytest.raises(
        ValueError,
        match="test_node_id 不能为空",
    ):
        repeat_test_execution(
            executor=executor,
            test_node_id=test_node_id,
            attempts=3,
        )

    assert executor.executed == []

def test_mixed_results_in_same_environment_are_flaky():
    environment = ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )
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

    diagnosis = diagnose_repeatability(
        reports=reports,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.FLAKY
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.HIGH
    )
    assert diagnosis.summary == (
        "测试重复执行结果不一致"
    )

    evidence = diagnosis.evidence[0]
    assert (
        evidence.kind
        is DiagnosisEvidenceKind.REPEAT_RUN
    )
    assert evidence.details == (
        "attempt_1=failed",
        "attempt_2=passed",
        "attempt_3=failed",
    )

    assert (
        diagnosis.locations[0].path
        == "tests/test_demo.py"
    )
    assert (
        diagnosis.locations[0].symbol
        == "test_add"
    )
    assert (
        diagnosis.suggested_actions[0].kind
        is DiagnosisActionKind.ISOLATE_FLAKY
    )

def test_consistent_failures_are_not_flaky():
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
            environment=environment,
        )
        for _ in range(3)
    )

    diagnosis = diagnose_repeatability(
        reports=reports,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.LOW
    )
    assert diagnosis.category is not (
        DiagnosisCategory.FLAKY
    )
    assert diagnosis.evidence[0].details == (
        "attempt_1=failed",
        "attempt_2=failed",
        "attempt_3=failed",
    )


def test_mixed_results_in_different_environments_are_not_flaky():
    first_environment = ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.12.9",
        working_directory="/demo",
    )
    second_environment = ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )

    reports = (
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            environment=first_environment,
        ),
        ExecutionReport(
            exit_code=0,
            error_type=None,
            environment=second_environment,
        ),
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            environment=second_environment,
        ),
    )

    diagnosis = diagnose_repeatability(
        reports=reports,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert diagnosis.category is not (
        DiagnosisCategory.FLAKY
    )
    assert diagnosis.suggested_actions[0].kind is (
        DiagnosisActionKind.REQUEST_CONFIRMATION
    )

def test_runner_error_takes_priority_over_flaky():
    environment = ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )
    reports = (
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            environment=environment,
        ),
        ExecutionReport(
            exit_code=4,
            error_type="runner_error",
            stderr="pytest runner failed",
            environment=environment,
        ),
        ExecutionReport(
            exit_code=0,
            error_type=None,
            environment=environment,
        ),
    )

    diagnosis = diagnose_repeatability(
        reports=reports,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.INFRA_DEFECT
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.HIGH
    )
    assert diagnosis.summary == (
        "测试 Runner 执行失败"
    )
    assert diagnosis.category is not (
        DiagnosisCategory.FLAKY
    )

def test_infrastructure_error_beats_earlier_inconclusive():
    environment = ExecutionEnvironment(
        runner="pytest",
        runtime="python",
        runtime_version="3.13.5",
        working_directory="/demo",
    )
    reports = (
        ExecutionReport(
            exit_code=9,
            error_type="unknown_error",
            environment=environment,
        ),
        ExecutionReport(
            exit_code=4,
            error_type="runner_error",
            stderr="pytest runner failed",
            environment=environment,
        ),
        ExecutionReport(
            exit_code=0,
            error_type=None,
            environment=environment,
        ),
    )

    diagnosis = diagnose_repeatability(
        reports=reports,
        test_node_id=(
            "tests/test_demo.py::test_add"
        ),
    )

    assert (
        diagnosis.category
        is DiagnosisCategory.INFRA_DEFECT
    )
    assert diagnosis.summary == (
        "测试 Runner 执行失败"
    )

@pytest.mark.parametrize(
    "reports",
    [
        (),
        (
            ExecutionReport(
                exit_code=1,
                error_type="test_failure",
            ),
        ),
        (
            ExecutionReport(
                exit_code=1,
                error_type="test_failure",
            ),
            ExecutionReport(
                exit_code=0,
                error_type=None,
            ),
        ),
    ],
)
def test_diagnosis_requires_exactly_three_reports(
    reports,
):
    with pytest.raises(
        ValueError,
        match="reports 必须包含 3 个 ExecutionReport",
    ):
        diagnose_repeatability(
            reports=reports,
            test_node_id=(
                "tests/test_demo.py::test_add"
            ),
        )

@pytest.mark.parametrize(
    "test_node_id",
    [
        "",
        "   ",
        None,
    ],
)
def test_diagnosis_rejects_empty_test_node(
    test_node_id,
):
    reports = tuple(
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
        )
        for _ in range(3)
    )

    with pytest.raises(
        ValueError,
        match="test_node_id 不能为空",
    ):
        diagnose_repeatability(
            reports=reports,
            test_node_id=test_node_id,
        )

def test_diagnosis_rejects_non_execution_report():
    reports = (
        ExecutionReport(
            exit_code=1,
            error_type="test_failure",
        ),
        None,
        ExecutionReport(
            exit_code=0,
            error_type=None,
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "reports 必须全部是 ExecutionReport"
        ),
    ):
        diagnose_repeatability(
            reports=reports,
            test_node_id=(
                "tests/test_demo.py::test_add"
            ),
        )