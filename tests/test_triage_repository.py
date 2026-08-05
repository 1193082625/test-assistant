import json
from datetime import datetime, timezone

import pytest

from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
    TestResult as ExecutionTestResult,
)
from core.models import (
    ContractMigrationEvidence,
    ContractMigrationType,
    Diagnosis,
    DiagnosisLocation,
    FailureCluster,
    PytestIssue,
    TriagePhase,
    TriageResult,
)
from core.workflows.triage import TriageEvidence, triage_pytest_suite
from core.reporters import render_triage_markdown
from core.repositories import TriageRepository


def _result(root, run_id="run-001", message="assert False"):
    issue = PytestIssue(
        phase=TriagePhase.EXECUTION,
        stage="call",
        outcome="failed",
        message=message,
        node_id=f"{root}/tests/test_demo.py::test_demo",
        exception_type="AssertionError",
        locations=(DiagnosisLocation(
            path=f"{root}/tests/test_demo.py",
            line=7,
        ),),
    )
    cluster = FailureCluster(
        fingerprint="a" * 64,
        representative_node=issue.node_id,
        issues=(issue,),
    )
    report = ExecutionReport(
        test_results=[ExecutionTestResult(
            name=issue.node_id,
            status="failed",
            duration=0.01,
            message=message,
        )],
        stdout="1 failed",
        stderr="",
        exit_code=1,
        error_type="test_failure",
        environment=ExecutionEnvironment(
            runner="pytest",
            runtime="python",
            runtime_version="3.13",
            working_directory=str(root),
        ),
    )
    return TriageResult(
        run_id=run_id,
        report=report,
        clusters=(cluster,),
        diagnoses=(Diagnosis(summary="需要人工确认"),),
    )


def _save(repository, result, **kwargs):
    return repository.save(
        result=result,
        diagnosis_references=(
            f"{repository.project_root}/.autotest/diagnoses/d1.json",
        ),
        reproduction_commands={
            result.clusters[0].fingerprint: (
                "python -m pytest tests/test_demo.py::test_demo -q"
            ),
        },
        git_sha="abc123",
        dependency_digest="sha256:deps",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        **kwargs,
    )


def test_repository_saves_versioned_record_and_latest(tmp_path):
    repository = TriageRepository(tmp_path)
    result = _result(tmp_path)

    record_path = _save(repository, result)

    assert record_path == tmp_path / ".autotest/triage/run-001.json"
    assert repository.load("run-001") == repository.load_latest()
    record = repository.load_latest()
    assert record["schema_version"] == 2
    assert record["record_type"] == "triage"
    assert record["run_id"] == "run-001"
    assert record["git_sha"] == "abc123"
    assert record["dependency_digest"] == "sha256:deps"
    assert record["pytest"]["status_counts"] == {"failed": 1}
    assert len(record["clusters"]) == 1
    assert len(record["diagnosis_references"]) == 1
    assert len(record["reproduction_commands"]) == 1


def test_repository_redacts_secrets_and_absolute_project_root(tmp_path):
    repository = TriageRepository(tmp_path)
    result = _result(
        tmp_path,
        message=(
            f"token=secret-value at {tmp_path}/app/service.py "
            "Bearer abc.def"
        ),
    )

    _save(repository, result)
    serialized = json.dumps(repository.load_latest())

    assert "secret-value" not in serialized
    assert "abc.def" not in serialized
    assert str(tmp_path) not in serialized
    assert "[REDACTED]" in serialized
    assert "<project-root>" in serialized


def test_repository_limits_issue_and_stream_text_and_records_fact(tmp_path):
    repository = TriageRepository(tmp_path)
    result = _result(tmp_path, message="m" * 5_000)
    result.report.stdout = "o" * 8_000
    result.report.stderr = "e" * 7_000

    _save(repository, result)
    record = repository.load_latest()

    message = record["clusters"][0]["issues"][0]["message"]
    assert len(message) < 2_100
    assert len(record["pytest"]["stdout"]) < 4_100
    assert len(record["pytest"]["stderr"]) < 4_100
    assert record["truncation"]["occurred"] is True
    assert record["truncation"]["fields"] == [
        "clusters[0].issues[0].message",
        "pytest.stderr",
        "pytest.stdout",
    ]


def test_repository_rejects_unsafe_run_id_and_existing_record(tmp_path):
    repository = TriageRepository(tmp_path)

    with pytest.raises(ValueError, match="run_id 包含不安全字符"):
        repository.load("../../outside")

    result = _result(tmp_path)
    _save(repository, result)
    with pytest.raises(FileExistsError, match="run_id 已存在"):
        _save(repository, result)


def test_repository_reports_corrupted_or_unsupported_json(tmp_path):
    repository = TriageRepository(tmp_path)
    repository.triage_dir.mkdir(parents=True)
    latest = repository.triage_dir / "latest.json"
    latest.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON 已损坏"):
        repository.load_latest()

    latest.write_text('{"schema_version": 999}', encoding="utf-8")
    with pytest.raises(ValueError, match="不支持的 Triage 记录格式"):
        repository.load_latest()


def test_atomic_failure_preserves_latest_and_cleans_temporary_file(
    tmp_path,
    monkeypatch,
):
    repository = TriageRepository(tmp_path)
    _save(repository, _result(tmp_path, run_id="run-001"))
    previous = repository.load_latest()

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(
        "core.repositories.triage.os.replace",
        fail_replace,
    )
    with pytest.raises(OSError, match="replace failed"):
        _save(repository, _result(tmp_path, run_id="run-002"))

    assert repository.load_latest() == previous
    assert not (repository.triage_dir / "run-002.json").exists()
    assert list(repository.triage_dir.glob("*.tmp")) == []


def test_save_does_not_modify_other_project_artifacts(tmp_path):
    sentinels = {
        tmp_path / ".autotest/snapshot.json": "snapshot",
        tmp_path / ".autotest/plans/spec.json": "approved-spec",
        tmp_path / "tests/test_existing.py": "def test_existing(): pass",
    }
    for path, content in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _save(TriageRepository(tmp_path), _result(tmp_path))

    assert {
        path: path.read_text(encoding="utf-8") for path in sentinels
    } == sentinels


def test_triage_reporter_uses_persisted_safe_summary(tmp_path):
    repository = TriageRepository(tmp_path)
    _save(repository, _result(tmp_path))

    markdown = render_triage_markdown(repository.load_latest())

    assert "Run ID：`run-001`" in markdown
    assert "pytest 退出码：`1`" in markdown
    assert "失败簇：`1`" in markdown
    assert "failed: 1" in markdown


def test_repository_persists_structured_contract_migration(tmp_path):
    class Executor:
        def execute(self, file_path):
            return ExecutionReport(exit_code=1, error_type="test_failure")

    base = _result(tmp_path, run_id="migration-001")
    node = base.clusters[0].representative_node
    suite = __import__(
        "core.executors.base", fromlist=["PytestSuiteResult"]
    ).PytestSuiteResult(
        report=base.report,
        issues=base.clusters[0].issues,
    )
    result = triage_pytest_suite(
        suite=suite,
        executor=Executor(),
        evidence_by_node={
            node: TriageEvidence(contract_migration=ContractMigrationEvidence(
                migration_type=ContractMigrationType.CONFIG_DEFAULT,
                target="settings.VALUE",
                old_contract="10",
                current_contract="120",
                current_sources=("app/config.py", "app/service.py"),
                migration_commit="a" * 40,
                current_consistent=True,
                history_confirmed=True,
            ))
        },
        run_id="migration-001",
    )
    repository = TriageRepository(tmp_path)
    repository.save(
        result=result,
        diagnosis_references=(".autotest/diagnoses/d1.json",),
        reproduction_commands={
            result.clusters[0].fingerprint: "python -m pytest test.py -q"
        },
    )

    migration = repository.load_latest()["contract_migrations"][0]
    assert migration["migration_type"] == "config_default"
    assert migration["old_contract"] == "10"
    assert migration["current_contract"] == "120"
    assert migration["migration_commit"] == "a" * 40
    assert migration["current_sources"] == [
        "app/config.py",
        "app/service.py",
    ]
