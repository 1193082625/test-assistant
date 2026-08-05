"""Decision table and transaction contracts for safe history cleanup."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.workflows.clean as clean_module
from core.models import (
    AuditResult,
    AuditStatus,
    CleanupReason,
    CleanupRecordType,
)
from core.repositories import AuditRepository, DiagnosisRepository
from core.models import Diagnosis
from core.workflows import execute_cleanup, plan_cleanup


NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _audit(root: Path, run_id: str, created_at: datetime) -> Path:
    return AuditRepository(root).save(
        AuditResult(
            run_id=run_id,
            status=AuditStatus.PASSED,
            command=("test-assistant", "audit"),
            coverage=None,
            symbols=(),
            findings=(),
            tools=(),
            source_digest=f"sha256:{run_id}",
        ),
        created_at=created_at,
    )


def _diagnosis(root: Path, summary: str, created_at: datetime) -> Path:
    return DiagnosisRepository(root).save(
        diagnosis=Diagnosis(summary=summary),
        execution_reports=(),
        reproduction_command="pytest -q",
        created_at=created_at,
    )


def _triage_record(
    root: Path,
    run_id: str,
    created_at: datetime,
    references: list[str] | None = None,
) -> Path:
    path = root / ".autotest" / "triage" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "record_type": "triage",
                "run_id": run_id,
                "created_at": created_at.isoformat(),
                "pytest": {},
                "clusters": [],
                "diagnosis_references": references or [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_age_boundary_and_latest_retention(tmp_path: Path) -> None:
    cutoff = NOW - timedelta(days=30)
    older = _audit(tmp_path, "older", cutoff - timedelta(microseconds=1))
    boundary = _audit(tmp_path, "boundary", cutoff)
    newer = _audit(tmp_path, "newer", cutoff + timedelta(seconds=1))

    plan = plan_cleanup(
        project_root=tmp_path,
        older_than_days=30,
        keep_latest=1,
        now=NOW,
    )

    assert [candidate.relative_path for candidate in plan.candidates] == [
        older.relative_to(tmp_path / ".autotest").as_posix()
    ]
    assert boundary.exists() and newer.exists()
    assert plan.protected_count >= 2


def test_default_keeps_latest_twenty_per_type(tmp_path: Path) -> None:
    paths = [
        _audit(tmp_path, f"run-{index:02d}", NOW - timedelta(days=100 - index))
        for index in range(22)
    ]

    plan = plan_cleanup(project_root=tmp_path, now=NOW)

    assert {candidate.relative_path for candidate in plan.candidates} == {
        path.relative_to(tmp_path / ".autotest").as_posix()
        for path in paths[:2]
    }


def test_capacity_pressure_selects_oldest_without_breaking_keep_latest(
    tmp_path: Path,
) -> None:
    paths = [
        _audit(tmp_path, f"run-{index}", NOW - timedelta(days=3 - index))
        for index in range(3)
    ]
    sizes = [path.stat().st_size for path in paths]

    plan = plan_cleanup(
        project_root=tmp_path,
        older_than_days=30,
        keep_latest=1,
        max_total_bytes=sizes[-1],
        now=NOW,
    )

    assert [candidate.relative_path for candidate in plan.candidates] == [
        path.relative_to(tmp_path / ".autotest").as_posix()
        for path in paths[:2]
    ]
    assert all(
        CleanupReason.CAPACITY_PRESSURE in candidate.reasons
        for candidate in plan.candidates
    )


def test_diagnosis_requires_opt_in_and_respects_references(tmp_path: Path) -> None:
    unreferenced = _diagnosis(
        tmp_path,
        "unreferenced",
        NOW - timedelta(days=100),
    )
    referenced = _diagnosis(
        tmp_path,
        "referenced",
        NOW - timedelta(days=99),
    )
    _triage_record(
        tmp_path,
        "kept",
        NOW,
        references=[
            "<project-root>/.autotest/diagnoses/"
            f"{referenced.name}"
        ],
    )

    default_plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        now=NOW,
    )
    assert all(
        candidate.record_type is not CleanupRecordType.DIAGNOSIS
        for candidate in default_plan.candidates
    )

    opted_in = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        include_diagnoses=True,
        now=NOW,
    )
    paths = {candidate.relative_path for candidate in opted_in.candidates}
    assert unreferenced.relative_to(tmp_path / ".autotest").as_posix() in paths
    assert referenced.relative_to(tmp_path / ".autotest").as_posix() not in paths
    assert any(
        CleanupReason.REFERENCED in protection.reasons
        for protection in opted_in.protected
    )


def test_verification_reference_protects_diagnosis(tmp_path: Path) -> None:
    diagnosis = _diagnosis(tmp_path, "referenced", NOW - timedelta(days=100))
    verification = tmp_path / ".autotest/verification/latest.json"
    verification.parent.mkdir(parents=True)
    verification.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "record_type": "verification",
                "verified_at": NOW.isoformat(),
                "status": "diagnosed",
                "category": "inconclusive",
                "confidence": "low",
                "diagnosis_record": str(diagnosis),
                "reproduction_command": "pytest -q",
            }
        ),
        encoding="utf-8",
    )

    plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        include_diagnoses=True,
        now=NOW,
    )

    assert not plan.candidates
    assert CleanupReason.REFERENCED in plan.protected[0].reasons


def test_invalid_symlink_hardlink_and_duplicate_inode_are_protected(
    tmp_path: Path,
) -> None:
    audit_dir = tmp_path / ".autotest/audits"
    audit_dir.mkdir(parents=True)
    invalid = audit_dir / "invalid.json"
    invalid.write_text("{broken", encoding="utf-8")
    regular = audit_dir / "regular.json"
    regular.write_text("{}", encoding="utf-8")
    hardlink = audit_dir / "hardlink.json"
    try:
        os.link(regular, hardlink)
        symlink = audit_dir / "symlink.json"
        symlink.symlink_to(invalid)
    except OSError:
        pytest.skip("links are unavailable")

    plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        now=NOW,
    )

    assert not plan.candidates
    reasons = {
        reason
        for protection in plan.protected
        for reason in protection.reasons
    }
    assert CleanupReason.INVALID_RECORD in reasons
    assert CleanupReason.SYMBOLIC_LINK in reasons
    assert CleanupReason.HARD_LINK in reasons
    assert CleanupReason.DUPLICATE_INODE in reasons


def test_planner_is_pure_when_autotest_is_missing(tmp_path: Path) -> None:
    before = tuple(tmp_path.iterdir())

    plan = plan_cleanup(project_root=tmp_path, now=NOW)

    assert not plan.candidates
    assert plan.protected_count == 0
    assert tuple(tmp_path.iterdir()) == before
    assert not (tmp_path / ".autotest").exists()


def test_planner_rejects_controlled_directory_symlink(tmp_path: Path) -> None:
    autotest = tmp_path / ".autotest"
    autotest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (autotest / "audits").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(ValueError, match="symbolic link"):
        plan_cleanup(project_root=tmp_path, now=NOW)


def test_unmanaged_assets_and_latest_are_never_candidates(tmp_path: Path) -> None:
    history = _audit(tmp_path, "old", NOW - timedelta(days=100))
    sentinels = {
        tmp_path / ".autotest/snapshot.json": "snapshot",
        tmp_path / ".autotest/plans/spec.json": "spec",
        tmp_path / ".autotest/candidates/item.json": "candidate",
    }
    for path, contents in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        now=NOW,
    )

    paths = {candidate.relative_path for candidate in plan.candidates}
    assert history.relative_to(tmp_path / ".autotest").as_posix() in paths
    assert all("latest.json" not in path for path in paths)
    assert all(path.read_text(encoding="utf-8") == value for path, value in sentinels.items())


def test_execute_revalidates_candidate_metadata(tmp_path: Path) -> None:
    candidate = _audit(tmp_path, "old", NOW - timedelta(days=100))
    plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        now=NOW,
    )
    candidate.write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="changed after planning"):
        execute_cleanup(project_root=tmp_path, plan=plan)

    assert candidate.read_text(encoding="utf-8") == "changed"


def test_execute_deletes_only_candidates_and_removes_trash(tmp_path: Path) -> None:
    candidate = _audit(tmp_path, "old", NOW - timedelta(days=100))
    latest = tmp_path / ".autotest/audits/latest.json"
    latest_bytes = latest.read_bytes()
    plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        now=NOW,
    )

    result = execute_cleanup(project_root=tmp_path, plan=plan)

    assert result.deleted_paths == ("audits/old.json",)
    assert result.reclaimed_bytes > 0
    assert not candidate.exists()
    assert latest.read_bytes() == latest_bytes
    assert not (tmp_path / ".autotest/.trash").exists()


def test_move_failure_rolls_back_all_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [
        _audit(tmp_path, f"old-{index}", NOW - timedelta(days=100 - index))
        for index in range(2)
    ]
    originals = {path: path.read_bytes() for path in paths}
    plan = plan_cleanup(
        project_root=tmp_path,
        keep_latest=0,
        now=NOW,
    )
    real_replace = clean_module.os.replace
    moves = 0

    def fail_second_move(source, target):
        nonlocal moves
        if ".trash" in str(target):
            moves += 1
            if moves == 2:
                raise OSError("move failed")
        return real_replace(source, target)

    monkeypatch.setattr(clean_module.os, "replace", fail_second_move)

    with pytest.raises(OSError, match="move failed"):
        execute_cleanup(project_root=tmp_path, plan=plan)

    assert all(path.read_bytes() == contents for path, contents in originals.items())
    assert not (tmp_path / ".autotest/.trash").exists()
