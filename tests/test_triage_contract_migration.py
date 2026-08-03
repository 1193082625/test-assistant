from core.executors.base import ExecutionReport, PytestSuiteResult
from core.models import (
    ContractMigrationEvidence,
    ContractMigrationType,
    DiagnosisCategory,
    DiagnosisConfidence,
    PytestIssue,
    TriagePhase,
)
from core.workflows.triage import (
    TriageEvidence,
    collect_contract_migration_triage_evidence,
    triage_pytest_suite,
)


class StableFailingExecutor:
    def execute(self, file_path):
        return ExecutionReport(exit_code=1, error_type="test_failure")


def suite(nodes=("tests/test_demo.py::test_old",)):
    issues = tuple(
        PytestIssue(
            phase=TriagePhase.EXECUTION,
            outcome="failed",
            message="assert old == current",
            node_id=node,
            exception_type="AssertionError",
        )
        for node in nodes
    )
    return PytestSuiteResult(
        report=ExecutionReport(exit_code=1, error_type="test_failure"),
        issues=issues,
    )


def migration(**overrides):
    values = dict(
        migration_type=ContractMigrationType.CONFIG_DEFAULT,
        target="settings.VALUE",
        old_contract="10",
        current_contract="120",
        current_sources=("app/config.py", "app/service.py"),
        migration_commit="a" * 40,
        current_consistent=True,
        history_confirmed=True,
    )
    values.update(overrides)
    return ContractMigrationEvidence(**values)


def diagnose(evidence):
    result = triage_pytest_suite(
        suite=suite(),
        executor=StableFailingExecutor(),
        evidence_by_node={
            "tests/test_demo.py::test_old": TriageEvidence(
                contract_migration=evidence
            )
        },
    )
    return result.diagnoses[0]


def test_confirmed_migration_is_high_confidence_test_defect():
    diagnosis = diagnose(migration())
    assert diagnosis.category is DiagnosisCategory.TEST_DEFECT
    assert diagnosis.confidence is DiagnosisConfidence.HIGH
    assert "migration_commit=" in " ".join(diagnosis.evidence[0].details)


def test_missing_history_stays_inconclusive():
    diagnosis = diagnose(migration(migration_commit=None, history_confirmed=False))
    assert diagnosis.category is DiagnosisCategory.INCONCLUSIVE
    assert diagnosis.confidence is DiagnosisConfidence.LOW


def test_current_contract_conflict_stays_inconclusive():
    diagnosis = diagnose(migration(conflict_reason="schema_conflict"))
    assert diagnosis.category is DiagnosisCategory.INCONCLUSIVE


def test_async_mock_boundary_does_not_require_git():
    diagnosis = diagnose(migration(
        migration_type=ContractMigrationType.ASYNC_MOCK_RESULT,
        target="AsyncSession.execute.result",
        old_contract="implicit AsyncMock child",
        current_contract="synchronous Result API",
        current_sources=("app/service.py",),
        migration_commit=None,
        history_confirmed=False,
        runtime_boundary_confirmed=True,
        warning_source="AsyncMockMixin._execute_mock_call",
    ))
    assert diagnosis.category is DiagnosisCategory.TEST_DEFECT
    assert diagnosis.confidence is DiagnosisConfidence.HIGH


def test_async_generator_recommends_complete_lifecycle():
    diagnosis = diagnose(migration(
        migration_type=ContractMigrationType.ASYNC_GENERATOR_LIFECYCLE,
        target="get_db",
        old_contract="unawaited __anext__",
        current_contract="awaited and closed",
        current_sources=("app/dependency.py",),
        migration_commit=None,
        history_confirmed=False,
        runtime_boundary_confirmed=True,
        warning_source="asend",
        lifecycle_gap=("await_anext", "aclose_in_finally"),
    ))
    assert diagnosis.category is DiagnosisCategory.TEST_DEFECT
    assert "await anext" in diagnosis.suggested_actions[0].description


def test_green_suite_skips_project_source_scan(tmp_path, monkeypatch):
    def fail_scan(root):
        raise AssertionError("green suite must not scan project sources")

    monkeypatch.setattr(
        "core.workflows.triage._project_python_sources",
        fail_scan,
    )
    evidence, degradations = collect_contract_migration_triage_evidence(
        project_root=tmp_path,
        suite=PytestSuiteResult(report=ExecutionReport(exit_code=0)),
        git_history_enabled=True,
    )
    assert evidence == {}
    assert degradations == ()
