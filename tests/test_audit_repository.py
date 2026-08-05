import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

import core.repositories as repositories
from core.models import (
    AuditResult,
    AuditStatus,
    AuditThresholds,
    CoverageSummary,
    QualityFinding,
    QualityFindingKind,
    SymbolCoverage,
    ToolState,
    ToolStatus,
)
from core.repositories.audit import AuditRepository


def make_audit_result(run_id="audit-001"):
    return AuditResult(
        run_id=run_id,
        status=AuditStatus.PASSED,
        command=("test-assistant", "audit", "--path", "."),
        coverage=CoverageSummary(
            statements_covered=75,
            statements_total=100,
            branches_covered=30,
            branches_total=50,
        ),
        symbols=(),
        findings=(),
        tools=(
            ToolStatus(
                tool="coverage",
                state=ToolState.COMPLETED,
                version="7.10.0",
                reason=None,
            ),
        ),
        source_digest="sha256:abc123",
    )


def test_repository_saves_versioned_record_and_latest(tmp_path):
    repository = AuditRepository(tmp_path)
    result = make_audit_result()

    record_path = repository.save(
        result,
        created_at=datetime(2026, 8, 4, 12, 30, tzinfo=timezone.utc),
    )

    assert record_path == (
        tmp_path / ".autotest/audits/audit-001.json"
    )
    assert repository.load("audit-001") == repository.load_latest()

    record = repository.load_latest()
    assert record["schema_version"] == 2
    assert record["record_type"] == "audit"
    assert record["run_id"] == "audit-001"

    assert record["created_at"] == "2026-08-04T12:30:00+00:00"
    assert record["status"] == "passed"
    assert record["command"] == [
        "test-assistant",
        "audit",
        "--path",
        ".",
    ]
    assert record["source_digest"] == "sha256:abc123"
    assert record["thresholds"] is None
    assert record["coverage"] == {
        "statements_covered": 75,
        "statements_total": 100,
        "branches_covered": 30,
        "branches_total": 50,
    }
    assert record["symbols"] == []
    assert record["findings"] == []
    assert record["tools"] == [
        {
            "tool": "coverage",
            "state": "completed",
            "version": "7.10.0",
            "reason": None,
        },
    ]

@pytest.mark.parametrize(
    "run_id",
    [
        "../../outside",
        "nested/run",
        r"windows\path",
        "",
    ],
)
def test_repository_rejects_unsafe_run_id(tmp_path, run_id):
    repository = AuditRepository(tmp_path)

    with pytest.raises(
        ValueError,
        match="Audit run_id 包含不安全字符",
    ):
        repository.load(run_id)


def test_repository_does_not_overwrite_existing_run(tmp_path):
    repository = AuditRepository(tmp_path)
    result = make_audit_result()

    repository.save(result)

    with pytest.raises(
        FileExistsError,
        match="Audit run_id 已存在",
    ):
        repository.save(result)

    assert repository.load("audit-001")["run_id"] == "audit-001"

@pytest.mark.parametrize(
    "run_id",
    [
        "../../outside",
        "nested/run",
        r"windows\path",
    ],
)
def test_repository_rejects_unsafe_run_id_when_saving(
    tmp_path,
    run_id,
):
    repository = AuditRepository(tmp_path)

    with pytest.raises(
        ValueError,
        match="Audit run_id 包含不安全字符",
    ):
        repository.save(make_audit_result(run_id=run_id))

def test_repository_serializes_symbols_and_findings(tmp_path):
    summary = CoverageSummary(
        statements_covered=7,
        statements_total=10,
        branches_covered=2,
        branches_total=4,
    )
    symbol = SymbolCoverage(
        source_path="app/service.py",
        qualified_name="Service.create",
        kind="method",
        start_line=10,
        end_line=20,
        summary=summary,
        missing_lines=(18,),
        missing_branches=((15, 18),),
    )
    finding = QualityFinding(
        tool="ruff",
        kind=QualityFindingKind.CODE,
        rule_code="F401",
        message="unused import",
        source_path="app/service.py",
        line=3,
        column=1,
        fix_available=True,
    )
    result = replace(
        make_audit_result(),
        symbols=(symbol,),
        findings=(finding,),
    )

    repository = AuditRepository(tmp_path)
    repository.save(result)
    record = repository.load("audit-001")

    assert record["symbols"][0]["summary"] == {
        "statements_covered": 7,
        "statements_total": 10,
        "branches_covered": 2,
        "branches_total": 4,
    }
    assert record["symbols"][0]["state"] == "partial"
    assert record["symbols"][0]["missing_lines"] == [18]
    assert record["symbols"][0]["missing_branches"] == [[15, 18]]
    assert record["findings"][0]["kind"] == "code"
    assert record["findings"][0]["rule_code"] == "F401"


def test_repository_serializes_explicit_thresholds(tmp_path):
    result = replace(
        make_audit_result(),
        thresholds=AuditThresholds(
            statement_rate=0.8,
            branch_rate=0.7,
            max_ruff_findings=5,
            max_mypy_errors=0,
        ),
    )

    repository = AuditRepository(tmp_path)
    repository.save(result)

    assert repository.load("audit-001")["thresholds"] == {
        "statement_rate": 0.8,
        "branch_rate": 0.7,
        "max_ruff_findings": 5,
        "max_mypy_errors": 0,
    }

def test_repository_rejects_corrupted_or_unsupported_json(
    tmp_path,
):
    repository = AuditRepository(tmp_path)
    repository.audit_dir.mkdir(parents=True)

    latest_path = repository.audit_dir / "latest.json"
    latest_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Audit 记录 JSON 已损坏",
    ):
        repository.load_latest()

    latest_path.write_text(
        '{"schema_version": 999}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="不支持的 Audit 记录格式",
    ):
        repository.load_latest()

def test_repository_rejects_incomplete_schema(tmp_path):
    repository = AuditRepository(tmp_path)
    repository.audit_dir.mkdir(parents=True)

    latest_path = repository.audit_dir / "latest.json"
    latest_path.write_text(
        (
            '{"schema_version": 1, '
            '"run_id": "audit-001"}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="不支持的 Audit 记录格式",
    ):
        repository.load_latest()

def test_latest_write_failure_rolls_back_new_record(
    tmp_path,
    monkeypatch,
):
    repository = AuditRepository(tmp_path)
    repository.save(make_audit_result(run_id="audit-001"))
    previous_latest = repository.load_latest()

    real_replace = __import__("os").replace

    def fail_latest_replace(source, target):
        if target == repository.audit_dir / "latest.json":
            raise OSError("latest replace failed")
        return real_replace(source, target)

    monkeypatch.setattr(
        "core.repositories.audit.os.replace",
        fail_latest_replace,
    )

    with pytest.raises(
        OSError,
        match="latest replace failed",
    ):
        repository.save(
            make_audit_result(run_id="audit-002")
        )

    assert repository.load_latest() == previous_latest
    assert not (
        repository.audit_dir / "audit-002.json"
    ).exists()
    assert list(repository.audit_dir.glob("*.tmp")) == []

def test_repository_redacts_secrets_paths_and_long_text(
    tmp_path,
):
    repository = AuditRepository(tmp_path)

    finding = QualityFinding(
        tool="ruff",
        kind=QualityFindingKind.CODE,
        rule_code="F401",
        message=(
            f"token=finding-secret at "
            f"{tmp_path}/app/service.py "
            + "x" * 5_000
        ),
        source_path=f"{tmp_path}/app/service.py",
        line=3,
        column=1,
        fix_available=True,
    )
    result = replace(
        make_audit_result(),
        command=(
            "test-assistant",
            "audit",
            "--token=command-secret",
        ),
        findings=(finding,),
        tools=(
            ToolStatus(
                tool="ruff",
                state=ToolState.FAILED,
                version="0.12.0",
                reason=(
                    f"password=tool-secret at {tmp_path}"
                ),
            ),
        ),
    )

    repository.save(result)
    record = repository.load_latest()
    serialized = json.dumps(record)

    assert "finding-secret" not in serialized
    assert "command-secret" not in serialized
    assert "tool-secret" not in serialized
    assert str(tmp_path) not in serialized
    assert "[REDACTED]" in serialized
    assert "<project-root>" in serialized

    message = record["findings"][0]["message"]
    assert len(message) < 4_100
    assert message.endswith("[TRUNCATED]")
    assert record["truncation"]["occurred"] is True
    assert "findings[0].message" in (
        record["truncation"]["fields"]
    )

def test_audit_repository_is_exported_from_core_repositories():
    assert repositories.AuditRepository is AuditRepository
    assert "AuditRepository" in repositories.__all__
