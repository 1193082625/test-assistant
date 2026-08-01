from pathlib import Path

import pytest

from core.diagnosticians import cluster_pytest_issues
from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
    PytestSuiteResult,
)
from core.executors.pytest_executor import PytestExecutor
from core.models import (
    DiagnosisActionKind,
    DiagnosisCategory,
    EvidenceKind,
    PytestIssue,
    TriagePhase,
)
from core.workflows import TriageEvidence, triage_pytest_suite


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "real_project_triage"
)


class FakeExecutor:
    def __init__(self, outcomes=("failed", "failed", "failed")):
        self.outcomes = outcomes
        self.executed: list[str] = []
        self.environment = ExecutionEnvironment(
            runner="pytest",
            runtime="python",
            runtime_version="3.13",
            working_directory="/fixture",
        )

    def execute(self, file_path: str) -> ExecutionReport:
        self.executed.append(file_path)
        outcome = self.outcomes[(len(self.executed) - 1) % 3]
        return ExecutionReport(
            exit_code=0 if outcome == "passed" else 1,
            error_type=None if outcome == "passed" else "test_failure",
            environment=self.environment,
        )


def _run_fixture(name: str) -> PytestSuiteResult:
    root = (FIXTURE_ROOT / name).resolve()
    return PytestExecutor(cwd=str(root)).execute_suite("case.py")


@pytest.mark.parametrize(
    ("name", "expected_cluster_count"),
    [
        ("stale_removed_method", 1),
        ("migrated_dependency_mock", 1),
        ("conflicting_contract", 1),
        ("missing_boolean_return", 4),
        ("instance_method_mapping", 0),
    ],
)
def test_real_project_fixtures_have_stable_cluster_counts(
    name,
    expected_cluster_count,
):
    suite = _run_fixture(name)

    clusters = cluster_pytest_issues(suite.issues)

    assert len(clusters) == expected_cluster_count
    assert clusters == cluster_pytest_issues(tuple(reversed(suite.issues)))
    assert all(
        cluster.representative_node is not None for cluster in clusters
    )


def test_confirmed_removed_symbol_is_test_defect_without_rerun():
    suite = _run_fixture("stale_removed_method")
    node = cluster_pytest_issues(suite.issues)[0].representative_node
    executor = FakeExecutor()

    result = triage_pytest_suite(
        suite=suite,
        executor=executor,
        evidence_by_node={node: TriageEvidence(
            missing_symbol=True,
            removal_confirmed=True,
            details=("current_source=missing", "git_history=removed"),
        )},
        run_id="stale-method-run",
    )

    assert result.run_id == "stale-method-run"
    assert result.diagnoses[0].category is DiagnosisCategory.TEST_DEFECT
    assert executor.executed == []


def test_confirmed_migrated_mock_is_test_defect_without_rerun():
    suite = _run_fixture("migrated_dependency_mock")
    node = cluster_pytest_issues(suite.issues)[0].representative_node
    executor = FakeExecutor()

    result = triage_pytest_suite(
        suite=suite,
        executor=executor,
        evidence_by_node={node: TriageEvidence(
            obsolete_dependency_mock=True,
            details=("current_loader=NewLoader.from_pretrained",),
        )},
    )

    assert result.diagnoses[0].category is DiagnosisCategory.TEST_DEFECT
    assert executor.executed == []


def test_conflicting_contract_stays_inconclusive_after_three_reruns():
    suite = _run_fixture("conflicting_contract")
    node = cluster_pytest_issues(suite.issues)[0].representative_node
    executor = FakeExecutor()

    result = triage_pytest_suite(
        suite=suite,
        executor=executor,
        evidence_by_node={node: TriageEvidence(
            contract_values=("10", "120"),
        )},
    )

    diagnosis = result.diagnoses[0]
    assert diagnosis.category is DiagnosisCategory.INCONCLUSIVE
    assert diagnosis.suggested_actions[0].kind is (
        DiagnosisActionKind.REQUEST_CONFIRMATION
    )
    assert executor.executed == [node, node, node]


def test_consistent_boolean_contract_is_product_defect():
    suite = _run_fixture("missing_boolean_return")
    clusters = cluster_pytest_issues(suite.issues)
    nodes = tuple(cluster.representative_node for cluster in clusters)
    evidence = TriageEvidence(
        contract_kinds=frozenset({
            EvidenceKind.TYPE_HINT,
            EvidenceKind.DOCSTRING,
        }),
        supporting_test_count=4,
        implementation_violates_contract=True,
        details=("observed=None", "expected=False"),
    )
    executor = FakeExecutor()

    result = triage_pytest_suite(
        suite=suite,
        executor=executor,
        evidence_by_node={node: evidence for node in nodes},
    )

    assert len(result.diagnoses) == 4
    assert {
        diagnosis.category for diagnosis in result.diagnoses
    } == {DiagnosisCategory.PRODUCT_DEFECT}
    assert executor.executed == [
        node for node in nodes for _ in range(3)
    ]


def test_passing_fixture_has_no_failure_diagnosis():
    suite = _run_fixture("instance_method_mapping")

    result = triage_pytest_suite(
        suite=suite,
        executor=FakeExecutor(),
    )

    assert result.clusters == ()
    assert result.diagnoses == ()


def test_flaky_result_wins_before_contract_attribution():
    issue = PytestIssue(
        phase=TriagePhase.EXECUTION,
        stage="call",
        outcome="failed",
        message="assert False",
        node_id="tests/test_demo.py::test_demo",
        exception_type="AssertionError",
    )
    suite = PytestSuiteResult(
        report=ExecutionReport(exit_code=1, error_type="test_failure"),
        issues=(issue,),
    )

    result = triage_pytest_suite(
        suite=suite,
        executor=FakeExecutor(("failed", "passed", "failed")),
        evidence_by_node={issue.node_id: TriageEvidence(
            contract_kinds=frozenset({
                EvidenceKind.TYPE_HINT,
                EvidenceKind.DOCSTRING,
            }),
            supporting_test_count=3,
            implementation_violates_contract=True,
        )},
    )

    assert result.diagnoses[0].category is DiagnosisCategory.FLAKY


def test_collection_error_is_classified_before_repeatability():
    issue = PytestIssue(
        phase=TriagePhase.COLLECTION,
        stage="collect",
        outcome="error",
        message="SyntaxError: invalid syntax",
        exception_type="SyntaxError",
    )
    suite = PytestSuiteResult(
        report=ExecutionReport(exit_code=2, error_type="runner_error"),
        issues=(issue,),
    )
    executor = FakeExecutor()

    result = triage_pytest_suite(suite=suite, executor=executor)

    assert result.diagnoses[0].category is DiagnosisCategory.TEST_DEFECT
    assert executor.executed == []


def test_missing_symbol_without_removal_confirmation_is_inconclusive():
    suite = _run_fixture("stale_removed_method")
    node = cluster_pytest_issues(suite.issues)[0].representative_node
    executor = FakeExecutor()

    result = triage_pytest_suite(
        suite=suite,
        executor=executor,
        evidence_by_node={node: TriageEvidence(missing_symbol=True)},
    )

    assert result.diagnoses[0].category is DiagnosisCategory.INCONCLUSIVE
    assert executor.executed == [node, node, node]


def test_runner_failure_is_classified_before_clusters():
    suite = PytestSuiteResult(report=ExecutionReport(
        exit_code=None,
        error_type="startup_error",
        stderr="python executable not found",
    ))
    executor = FakeExecutor()

    result = triage_pytest_suite(suite=suite, executor=executor)

    assert result.diagnoses[0].category is DiagnosisCategory.INFRA_DEFECT
    assert executor.executed == []
