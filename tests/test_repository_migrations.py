"""Cross-repository schema v2 migration and recovery contracts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.executors.base import ExecutionReport
from core.models import AuditResult, AuditStatus, Diagnosis, TriageResult
from core.repositories import (
    AuditRepository,
    DiagnosisRepository,
    GitPermissionRepository,
    TriageRepository,
    VerificationStateRepository,
)


FIXED_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _audit_result(run_id: str) -> AuditResult:
    return AuditResult(
        run_id=run_id,
        status=AuditStatus.PASSED,
        command=("test-assistant", "audit"),
        coverage=None,
        symbols=(),
        findings=(),
        tools=(),
        source_digest="sha256:fixture",
    )


def _triage_result(run_id: str) -> TriageResult:
    return TriageResult(
        run_id=run_id,
        report=ExecutionReport(exit_code=0),
        clusters=(),
        diagnoses=(),
    )


def _write_v1(path: Path, payload: dict[str, object]) -> bytes:
    downgraded = dict(payload)
    downgraded["schema_version"] = 1
    downgraded.pop("record_type", None)
    encoded = (json.dumps(downgraded, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return encoded


def test_v1_runtime_records_load_as_v2_without_writing(tmp_path: Path) -> None:
    audit = AuditRepository(tmp_path / "audit")
    audit_path = audit.save(_audit_result("audit-001"), created_at=FIXED_TIME)
    audit_bytes = _write_v1(audit_path, audit.load("audit-001"))
    audit_latest = audit.audit_dir / "latest.json"
    audit_latest_bytes = _write_v1(audit_latest, audit.load("audit-001"))

    triage = TriageRepository(tmp_path / "triage")
    triage_path = triage.save(
        result=_triage_result("triage-001"),
        diagnosis_references=(),
        reproduction_commands={},
        created_at=FIXED_TIME,
    )
    triage_bytes = _write_v1(triage_path, triage.load("triage-001"))
    triage_latest = triage.triage_dir / "latest.json"
    triage_latest_bytes = _write_v1(
        triage_latest,
        triage.load("triage-001"),
    )

    diagnosis = DiagnosisRepository(tmp_path / "diagnosis")
    diagnosis_path = diagnosis.save(
        diagnosis=Diagnosis(summary="fixture"),
        execution_reports=(),
        reproduction_command="python -m pytest -q",
        created_at=FIXED_TIME,
    )
    diagnosis_payload = diagnosis._load_path(diagnosis_path)
    diagnosis_bytes = _write_v1(diagnosis_path, diagnosis_payload)
    diagnosis_latest = diagnosis.diagnosis_dir / "latest.json"
    diagnosis_latest_bytes = _write_v1(
        diagnosis_latest,
        diagnosis_payload,
    )

    for record, record_type in (
        (audit.load("audit-001"), "audit"),
        (triage.load("triage-001"), "triage"),
        (diagnosis._load_path(diagnosis_path), "diagnosis"),
        (audit.load_latest(), "audit"),
        (triage.load_latest(), "triage"),
        (diagnosis.load_latest(), "diagnosis"),
    ):
        assert record["schema_version"] == 2
        assert record["record_type"] == record_type

    assert audit_path.read_bytes() == audit_bytes
    assert triage_path.read_bytes() == triage_bytes
    assert diagnosis_path.read_bytes() == diagnosis_bytes
    assert audit_latest.read_bytes() == audit_latest_bytes
    assert triage_latest.read_bytes() == triage_latest_bytes
    assert diagnosis_latest.read_bytes() == diagnosis_latest_bytes


def test_new_records_write_schema_v2_and_record_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = AuditRepository(tmp_path / "audit")
    audit_path = audit.save(_audit_result("audit-001"), created_at=FIXED_TIME)
    triage = TriageRepository(tmp_path / "triage")
    triage_path = triage.save(
        result=_triage_result("triage-001"),
        diagnosis_references=(),
        reproduction_commands={},
        created_at=FIXED_TIME,
    )
    diagnosis = DiagnosisRepository(tmp_path / "diagnosis")
    diagnosis_path = diagnosis.save(
        diagnosis=Diagnosis(summary="fixture"),
        execution_reports=(),
        reproduction_command="pytest -q",
        created_at=FIXED_TIME,
    )
    verification = VerificationStateRepository(tmp_path / "verification")
    verification.save(
        status="passed",
        reproduction_command="pytest -q",
    )
    permission = GitPermissionRepository(tmp_path / "permission")
    monkeypatch.setattr(
        "core.repositories.permissions.git_repository_identity",
        lambda _: "fixture-id",
    )
    permission.grant(approved_at=FIXED_TIME)

    paths_and_types = (
        (audit_path, "audit"),
        (triage_path, "triage"),
        (diagnosis_path, "diagnosis"),
        (verification.path, "verification"),
        (permission.path, "git_permission"),
    )
    for path, record_type in paths_and_types:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 2
        assert payload["record_type"] == record_type


def test_v1_singleton_records_load_as_v2_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verification = VerificationStateRepository(tmp_path)
    verification_v1 = {
        "schema_version": 1,
        "verified_at": FIXED_TIME.isoformat(),
        "status": "passed",
        "category": None,
        "confidence": None,
        "diagnosis_record": None,
        "reproduction_command": "python -m pytest -q",
    }
    verification_bytes = _write_v1(verification.path, verification_v1)

    permission = GitPermissionRepository(tmp_path)
    permission_v1 = {
        "schema_version": 1,
        "git_history": {
            "enabled": True,
            "scope": "local_read_only",
            "repository_identity": "fixture-id",
            "approved_at": FIXED_TIME.isoformat(),
        },
    }
    permission_bytes = _write_v1(permission.path, permission_v1)
    monkeypatch.setattr(
        "core.repositories.permissions.git_repository_identity",
        lambda _: "fixture-id",
    )

    verification_record = verification.load()
    assert verification_record["schema_version"] == 2
    assert verification_record["record_type"] == "verification"
    assert permission.is_granted() is True
    assert verification.path.read_bytes() == verification_bytes
    assert permission.path.read_bytes() == permission_bytes


@pytest.mark.parametrize("repository_kind", ["audit", "triage", "diagnosis"])
def test_invalid_latest_recovers_newest_valid_history_read_only(
    tmp_path: Path,
    repository_kind: str,
) -> None:
    if repository_kind == "audit":
        repository = AuditRepository(tmp_path)
        repository.save(_audit_result("first"), created_at=FIXED_TIME)
        newest = repository.save(
            _audit_result("second"),
            created_at=FIXED_TIME + timedelta(seconds=1),
        )
        latest = repository.audit_dir / "latest.json"
    elif repository_kind == "triage":
        repository = TriageRepository(tmp_path)
        for index, run_id in enumerate(("first", "second")):
            repository.save(
                result=_triage_result(run_id),
                diagnosis_references=(),
                reproduction_commands={},
                created_at=FIXED_TIME + timedelta(seconds=index),
            )
        newest = repository.triage_dir / "second.json"
        latest = repository.triage_dir / "latest.json"
    else:
        repository = DiagnosisRepository(tmp_path)
        repository.save(
            diagnosis=Diagnosis(summary="first"),
            execution_reports=(),
            reproduction_command="pytest -q",
            created_at=FIXED_TIME,
        )
        newest = repository.save(
            diagnosis=Diagnosis(summary="second"),
            execution_reports=(),
            reproduction_command="pytest -q",
            created_at=FIXED_TIME + timedelta(seconds=1),
        )
        latest = repository.diagnosis_dir / "latest.json"

    latest.write_text("{broken", encoding="utf-8")
    broken_bytes = latest.read_bytes()

    recovered = repository.load_latest_record()

    assert recovered is not None
    assert recovered.recovered is True
    assert recovered.source_path == newest
    assert recovered.payload["schema_version"] == 2
    assert latest.read_bytes() == broken_bytes


def test_recovery_ignores_symlink_and_wrong_record_type(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path)
    valid = repository.save(_audit_result("valid"), created_at=FIXED_TIME)
    latest = repository.audit_dir / "latest.json"
    latest.write_text("{broken", encoding="utf-8")
    wrong = repository.audit_dir / "newer.json"
    wrong.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "record_type": "triage",
                "created_at": (FIXED_TIME + timedelta(days=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    symlink = repository.audit_dir / "linked.json"
    try:
        symlink.symlink_to(wrong)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    recovered = repository.load_latest_record()

    assert recovered is not None
    assert recovered.source_path == valid


def test_singleton_records_do_not_recover_corruption(tmp_path: Path) -> None:
    verification = VerificationStateRepository(tmp_path)
    verification.path.parent.mkdir(parents=True)
    verification.path.write_text("{broken", encoding="utf-8")
    permission = GitPermissionRepository(tmp_path)
    permission.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError):
        verification.load()
    with pytest.raises(ValueError):
        permission.is_granted()
