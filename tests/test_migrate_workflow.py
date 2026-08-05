"""Contracts for explicit, transactional schema migration."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.workflows.migrate as migrate_module
from core.models import (
    AuditResult,
    AuditStatus,
    MigrationAction,
    MigrationItem,
    MigrationPlan,
)
from core.repositories import AuditRepository
from core.workflows import execute_migration, plan_migration


FIXED_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _result(run_id: str) -> AuditResult:
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


def _downgrade(path: Path) -> bytes:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    payload.pop("record_type")
    contents = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(contents)
    return contents


def test_plan_is_read_only_and_only_scans_whitelist(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path)
    history = repository.save(_result("run-001"), created_at=FIXED_TIME)
    before = _downgrade(history)
    unknown = tmp_path / ".autotest" / "custom.json"
    unknown.write_text('{"schema_version": 1}', encoding="utf-8")
    candidate = tmp_path / ".autotest/candidates/item.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text('{"schema_version": 1}', encoding="utf-8")

    plan = plan_migration(project_root=tmp_path)

    item = next(item for item in plan.items if item.relative_path.endswith("run-001.json"))
    assert item.record_type == "audit"
    assert item.source_version == 1
    assert item.target_version == 2
    assert item.action is MigrationAction.MIGRATE
    assert history.read_bytes() == before
    assert all("custom.json" not in item.relative_path for item in plan.items)
    assert all("candidates" not in item.relative_path for item in plan.items)


def test_plan_rejects_autotest_or_type_directory_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    autotest = tmp_path / ".autotest"
    try:
        autotest.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ValueError, match="symbolic link"):
        plan_migration(project_root=tmp_path)


def test_plan_rejects_internal_type_directory_symlink(tmp_path: Path) -> None:
    autotest = tmp_path / ".autotest"
    autotest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (autotest / "audits").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ValueError, match="symbolic link"):
        plan_migration(project_root=tmp_path)


def test_future_schema_blocks_apply(tmp_path: Path) -> None:
    path = tmp_path / ".autotest/audits/future.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "record_type": "audit",
                "created_at": FIXED_TIME.isoformat(),
            }
        ),
        encoding="utf-8",
    )

    plan = plan_migration(project_root=tmp_path)

    assert plan.blocked is True
    assert plan.items[0].action is MigrationAction.SKIP
    with pytest.raises(ValueError, match="blocked"):
        execute_migration(project_root=tmp_path, plan=plan)


def test_apply_repairs_corrupt_latest_from_newest_history(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path)
    repository.save(_result("old"), created_at=FIXED_TIME)
    newest = repository.save(
        _result("new"),
        created_at=FIXED_TIME + timedelta(seconds=1),
    )
    latest = repository.audit_dir / "latest.json"
    latest.write_text("{broken", encoding="utf-8")

    plan = plan_migration(project_root=tmp_path)
    repair = next(item for item in plan.items if item.relative_path.endswith("latest.json"))

    assert repair.action is MigrationAction.REPAIR_LATEST
    assert repair.recovery_source is not None
    result = execute_migration(project_root=tmp_path, plan=plan)

    assert result.applied is True
    assert result.repaired_count == 1
    assert repository.load_latest()["run_id"] == "new"
    assert repair.recovery_source.endswith(newest.name)


def test_apply_repairs_missing_latest(tmp_path: Path) -> None:
    repository = AuditRepository(tmp_path)
    repository.save(_result("run-001"), created_at=FIXED_TIME)
    latest = repository.audit_dir / "latest.json"
    latest.unlink()

    plan = plan_migration(project_root=tmp_path)
    repair = next(item for item in plan.items if item.relative_path.endswith("latest.json"))
    assert repair.action is MigrationAction.REPAIR_LATEST
    assert repair.source_version is None

    execute_migration(project_root=tmp_path, plan=plan)

    assert repository.load_latest()["run_id"] == "run-001"


def test_apply_failure_restores_every_original_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = AuditRepository(tmp_path)
    first = repository.save(_result("first"), created_at=FIXED_TIME)
    second = repository.save(
        _result("second"),
        created_at=FIXED_TIME + timedelta(seconds=1),
    )
    originals = {path: _downgrade(path) for path in (first, second)}
    plan = plan_migration(project_root=tmp_path)
    real_write = migrate_module.atomic_write_json
    calls = 0

    def fail_second(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated migration failure")
        real_write(path, payload)

    monkeypatch.setattr(migrate_module, "atomic_write_json", fail_second)

    with pytest.raises(OSError, match="simulated migration failure"):
        execute_migration(project_root=tmp_path, plan=plan)

    assert all(path.read_bytes() == contents for path, contents in originals.items())
    assert not list(tmp_path.parent.glob(".autotest-migrate-backup-*"))


def test_backup_failure_does_not_modify_or_delete_originals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = AuditRepository(tmp_path)
    first = repository.save(_result("first"), created_at=FIXED_TIME)
    second = repository.save(
        _result("second"),
        created_at=FIXED_TIME + timedelta(seconds=1),
    )
    originals = {path: _downgrade(path) for path in (first, second)}
    plan = plan_migration(project_root=tmp_path)
    real_copy = migrate_module.shutil.copy2
    calls = 0

    def fail_second_copy(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated backup failure")
        return real_copy(source, target)

    monkeypatch.setattr(migrate_module.shutil, "copy2", fail_second_copy)

    with pytest.raises(OSError, match="simulated backup failure"):
        execute_migration(project_root=tmp_path, plan=plan)

    assert all(path.read_bytes() == contents for path, contents in originals.items())
    assert not list(tmp_path.parent.glob(".autotest-migrate-backup-*"))


def test_execute_rejects_plan_path_outside_record_scope(tmp_path: Path) -> None:
    autotest = tmp_path / ".autotest"
    autotest.mkdir()
    config = autotest / "config.yaml"
    config.write_text("protected: true\n", encoding="utf-8")
    digest = migrate_module._file_digest(config)
    plan = MigrationPlan(
        schema_version=1,
        items=(
            MigrationItem(
                relative_path="config.yaml",
                record_type="audit",
                source_version=1,
                target_version=2,
                action=MigrationAction.MIGRATE,
                source_digest=digest,
            ),
        ),
    )

    with pytest.raises(ValueError, match="controlled record scope"):
        execute_migration(project_root=tmp_path, plan=plan)

    assert config.read_text(encoding="utf-8") == "protected: true\n"


def test_incomplete_rollback_preserves_recoverable_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = AuditRepository(tmp_path)
    first = repository.save(_result("first"), created_at=FIXED_TIME)
    second = repository.save(
        _result("second"),
        created_at=FIXED_TIME + timedelta(seconds=1),
    )
    _downgrade(first)
    _downgrade(second)
    plan = plan_migration(project_root=tmp_path)
    real_write = migrate_module.atomic_write_json
    real_replace = migrate_module.os.replace
    calls = 0

    def fail_second_write(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("write failed")
        real_write(path, payload)

    def fail_restore(source, target):
        if ".autotest-migrate-backup-" in str(source):
            raise OSError("rollback failed")
        return real_replace(source, target)

    monkeypatch.setattr(migrate_module, "atomic_write_json", fail_second_write)
    monkeypatch.setattr(migrate_module.os, "replace", fail_restore)

    with pytest.raises(RuntimeError, match="backup preserved at"):
        execute_migration(project_root=tmp_path, plan=plan)

    backups = list(tmp_path.parent.glob(".autotest-migrate-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / first.relative_to(tmp_path / ".autotest")).is_file()
    migrate_module.shutil.rmtree(backups[0])
