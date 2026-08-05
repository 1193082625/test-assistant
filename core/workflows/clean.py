"""Pure cleanup planning and recoverable history deletion."""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from core.models import (
    CleanupCandidate,
    CleanupPlan,
    CleanupProtection,
    CleanupReason,
    CleanupRecordType,
    CleanupResult,
)
from core.repositories import AuditRepository, DiagnosisRepository, TriageRepository


@dataclass(frozen=True)
class _ScannedRecord:
    path: Path
    relative_path: str
    record_type: CleanupRecordType
    size_bytes: int
    device: int
    inode: int
    mtime_ns: int
    created_at: datetime | None
    payload: dict[str, object] | None
    problems: tuple[CleanupReason, ...] = ()
    latest: bool = False


def plan_cleanup(
    *,
    project_root: str | Path,
    older_than_days: int = 30,
    keep_latest: int = 20,
    max_total_bytes: int | None = None,
    include_diagnoses: bool = False,
    now: datetime | None = None,
) -> CleanupPlan:
    """Build a cleanup plan without creating or modifying any path."""

    _validate_non_negative_integer(older_than_days, "older_than_days")
    _validate_non_negative_integer(keep_latest, "keep_latest")
    if max_total_bytes is not None:
        _validate_non_negative_integer(max_total_bytes, "max_total_bytes")
    if not isinstance(include_diagnoses, bool):
        raise ValueError("include_diagnoses must be bool")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current_time = current_time.astimezone(timezone.utc)

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"project path does not exist: {root}")
    autotest = root / ".autotest"
    if not os.path.lexists(autotest):
        return CleanupPlan(1, (), 0, 0)
    _require_real_directory(autotest)

    scanned = _scan_records(root, autotest)
    histories = [record for record in scanned if not record.latest]
    protected_reasons: dict[str, set[CleanupReason]] = {
        record.relative_path: set(record.problems)
        for record in scanned
        if record.problems
    }
    for record in scanned:
        if record.latest:
            protected_reasons.setdefault(record.relative_path, set()).add(
                CleanupReason.LATEST_ALIAS
            )

    valid_histories = [
        record
        for record in histories
        if record.created_at is not None and not record.problems
    ]
    for record_type in CleanupRecordType:
        records = sorted(
            (
                record
                for record in valid_histories
                if record.record_type is record_type
            ),
            key=lambda record: (record.created_at, record.relative_path),
            reverse=True,
        )
        for record in records[:keep_latest]:
            protected_reasons.setdefault(record.relative_path, set()).add(
                CleanupReason.LATEST_RETENTION
            )

    if not include_diagnoses:
        for record in valid_histories:
            if record.record_type is CleanupRecordType.DIAGNOSIS:
                protected_reasons.setdefault(record.relative_path, set()).add(
                    CleanupReason.DIAGNOSIS_OPT_IN_REQUIRED
                )

    cutoff = current_time - timedelta(days=older_than_days)
    candidate_reasons: dict[str, set[CleanupReason]] = {}
    for record in valid_histories:
        if record.relative_path in protected_reasons:
            continue
        if record.created_at < cutoff:
            candidate_reasons[record.relative_path] = {CleanupReason.EXPIRED}

    if max_total_bytes is not None:
        remaining = sum(record.size_bytes for record in histories)
        remaining -= sum(
            record.size_bytes
            for record in valid_histories
            if record.relative_path in candidate_reasons
        )
        capacity_pool = sorted(
            (
                record
                for record in valid_histories
                if record.relative_path not in candidate_reasons
                and record.relative_path not in protected_reasons
            ),
            key=lambda record: (record.created_at, record.relative_path),
        )
        for record in capacity_pool:
            if remaining <= max_total_bytes:
                break
            candidate_reasons[record.relative_path] = {
                CleanupReason.CAPACITY_PRESSURE
            }
            remaining -= record.size_bytes

    referenced_diagnoses, uncertain_references = _diagnosis_references(
        root,
        scanned,
        candidate_reasons,
    )
    for record in valid_histories:
        if record.record_type is not CleanupRecordType.DIAGNOSIS:
            continue
        if uncertain_references or record.relative_path in referenced_diagnoses:
            candidate_reasons.pop(record.relative_path, None)
            protected_reasons.setdefault(record.relative_path, set()).add(
                CleanupReason.REFERENCED
            )

    for record in valid_histories:
        if (
            record.relative_path not in candidate_reasons
            and record.relative_path not in protected_reasons
        ):
            protected_reasons[record.relative_path] = {
                CleanupReason.WITHIN_RETENTION
            }

    records_by_path = {record.relative_path: record for record in valid_histories}
    candidates = tuple(
        _candidate(records_by_path[path], reasons)
        for path, reasons in sorted(candidate_reasons.items())
    )
    protections = tuple(
        CleanupProtection(
            relative_path=path,
            record_type=next(
                record.record_type for record in scanned
                if record.relative_path == path
            ),
            reasons=tuple(sorted(reasons, key=lambda reason: reason.value)),
        )
        for path, reasons in sorted(protected_reasons.items())
    )
    return CleanupPlan(
        schema_version=1,
        candidates=candidates,
        protected_count=len(protections),
        reclaimable_bytes=sum(candidate.size_bytes for candidate in candidates),
        protected=protections,
    )


def execute_cleanup(
    *,
    project_root: str | Path,
    plan: CleanupPlan,
) -> CleanupResult:
    """Move all candidates to controlled trash, then permanently remove it."""

    if not isinstance(plan, CleanupPlan) or plan.schema_version != 1:
        raise ValueError("unsupported cleanup plan")
    root = Path(project_root).resolve()
    autotest = root / ".autotest"
    _require_real_directory(autotest)

    targets: list[tuple[CleanupCandidate, Path]] = []
    identities: set[tuple[int, int]] = set()
    for candidate in plan.candidates:
        target = _candidate_path(autotest, candidate)
        metadata = target.lstat()
        identity = (metadata.st_dev, metadata.st_ino)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or identity in identities
            or metadata.st_dev != candidate.device
            or metadata.st_ino != candidate.inode
            or metadata.st_size != candidate.size_bytes
            or metadata.st_mtime_ns != candidate.mtime_ns
        ):
            raise ValueError(
                f"cleanup candidate changed after planning: {candidate.relative_path}"
            )
        identities.add(identity)
        targets.append((candidate, target))

    if not targets:
        return CleanupResult(1, (), 0)

    trash_root = autotest / ".trash"
    if os.path.lexists(trash_root):
        _require_real_directory(trash_root)
        trash_created = False
    else:
        trash_root.mkdir()
        trash_created = True
    operation_root = trash_root / uuid.uuid4().hex
    operation_root.mkdir()
    moved: list[tuple[Path, Path]] = []
    try:
        for _, source in targets:
            destination = operation_root / source.relative_to(autotest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            moved.append((source, destination))
        for directory in {path.parent for pair in moved for path in pair}:
            _fsync_directory(directory)
    except BaseException:
        rollback_errors: list[OSError] = []
        for source, destination in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
            except OSError as error:
                rollback_errors.append(error)
        if rollback_errors:
            raise RuntimeError(
                f"cleanup rollback incomplete; trash preserved at {operation_root}"
            )
        shutil.rmtree(operation_root, ignore_errors=True)
        if trash_created and trash_root.is_dir() and not any(trash_root.iterdir()):
            trash_root.rmdir()
        raise

    shutil.rmtree(operation_root)
    if trash_created and not any(trash_root.iterdir()):
        trash_root.rmdir()
    _fsync_directory(autotest)
    return CleanupResult(
        schema_version=1,
        deleted_paths=tuple(candidate.relative_path for candidate, _ in targets),
        reclaimed_bytes=sum(candidate.size_bytes for candidate, _ in targets),
    )


def _scan_records(root: Path, autotest: Path) -> list[_ScannedRecord]:
    repositories = {
        CleanupRecordType.AUDIT: AuditRepository(root)._load_path,
        CleanupRecordType.TRIAGE: TriageRepository(root)._load_path,
        CleanupRecordType.DIAGNOSIS: DiagnosisRepository(root)._load_path,
    }
    directories = {
        CleanupRecordType.AUDIT: "audits",
        CleanupRecordType.TRIAGE: "triage",
        CleanupRecordType.DIAGNOSIS: "diagnoses",
    }
    scanned: list[_ScannedRecord] = []
    identities: dict[tuple[int, int], list[int]] = {}
    for record_type, directory_name in directories.items():
        directory = autotest / directory_name
        if not os.path.lexists(directory):
            continue
        _require_real_directory(directory)
        for path in sorted(directory.iterdir()):
            if path.suffix != ".json":
                continue
            metadata = path.lstat()
            problems: set[CleanupReason] = set()
            if stat.S_ISLNK(metadata.st_mode):
                problems.add(CleanupReason.SYMBOLIC_LINK)
            elif not stat.S_ISREG(metadata.st_mode):
                problems.add(CleanupReason.NON_REGULAR_FILE)
            if metadata.st_nlink > 1:
                problems.add(CleanupReason.HARD_LINK)
            payload = None
            created_at = None
            if not problems:
                try:
                    payload = repositories[record_type](path)
                    value = payload.get("created_at")
                    if not isinstance(value, str):
                        raise ValueError("created_at is missing")
                    created_at = datetime.fromisoformat(value)
                    if created_at.tzinfo is None:
                        raise ValueError("created_at must be timezone-aware")
                    created_at = created_at.astimezone(timezone.utc)
                except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                    problems.add(CleanupReason.INVALID_RECORD)
            index = len(scanned)
            scanned.append(
                _ScannedRecord(
                    path=path,
                    relative_path=path.relative_to(autotest).as_posix(),
                    record_type=record_type,
                    size_bytes=metadata.st_size,
                    device=metadata.st_dev,
                    inode=metadata.st_ino,
                    mtime_ns=metadata.st_mtime_ns,
                    created_at=created_at,
                    payload=payload,
                    problems=tuple(sorted(problems, key=lambda reason: reason.value)),
                    latest=path.name == "latest.json",
                )
            )
            identities.setdefault((metadata.st_dev, metadata.st_ino), []).append(index)

    duplicate_indexes = {
        index
        for indexes in identities.values()
        if len(indexes) > 1
        for index in indexes
    }
    for index in duplicate_indexes:
        record = scanned[index]
        scanned[index] = _ScannedRecord(
            **{
                **record.__dict__,
                "problems": tuple(sorted(
                    {*record.problems, CleanupReason.DUPLICATE_INODE},
                    key=lambda reason: reason.value,
                )),
            }
        )
    return scanned


def _diagnosis_references(
    root: Path,
    scanned: list[_ScannedRecord],
    candidates: dict[str, set[CleanupReason]],
) -> tuple[set[str], bool]:
    references: set[str] = set()
    uncertain = False
    for record in scanned:
        if record.record_type is not CleanupRecordType.TRIAGE:
            continue
        if record.relative_path in candidates:
            continue
        if record.payload is None:
            uncertain = True
            continue
        values = record.payload.get("diagnosis_references", [])
        if not isinstance(values, list):
            uncertain = True
            continue
        for value in values:
            if not isinstance(value, str):
                uncertain = True
                continue
            normalized = _normalize_diagnosis_reference(root, value)
            if normalized is None:
                uncertain = True
            else:
                references.add(normalized)

    verification_path = root / ".autotest/verification/latest.json"
    if os.path.lexists(verification_path):
        if verification_path.is_symlink() or not verification_path.is_file():
            uncertain = True
        else:
            try:
                payload = json.loads(verification_path.read_text(encoding="utf-8"))
                value = payload.get("diagnosis_record")
                if isinstance(value, str):
                    normalized = _normalize_diagnosis_reference(root, value)
                    if normalized is None:
                        uncertain = True
                    else:
                        references.add(normalized)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                uncertain = True
    return references, uncertain


def _normalize_diagnosis_reference(root: Path, value: str) -> str | None:
    placeholder = "<project-root>/.autotest/diagnoses/"
    if value.startswith(placeholder):
        name = value.removeprefix(placeholder)
        if name and "/" not in name and name.endswith(".json"):
            return f"diagnoses/{name}"
    path = Path(value)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root / ".autotest").as_posix()
        except ValueError:
            return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        return None
    if pure.parts[:1] == ("diagnoses",):
        return pure.as_posix()
    if pure.parts[:2] == (".autotest", "diagnoses"):
        return PurePosixPath(*pure.parts[1:]).as_posix()
    return None


def _candidate(
    record: _ScannedRecord,
    reasons: set[CleanupReason],
) -> CleanupCandidate:
    assert record.created_at is not None
    return CleanupCandidate(
        relative_path=record.relative_path,
        record_type=record.record_type,
        size_bytes=record.size_bytes,
        created_at=record.created_at,
        reasons=tuple(sorted(reasons, key=lambda reason: reason.value)),
        device=record.device,
        inode=record.inode,
        mtime_ns=record.mtime_ns,
    )


def _candidate_path(autotest: Path, candidate: CleanupCandidate) -> Path:
    relative = PurePosixPath(candidate.relative_path)
    directories = {
        CleanupRecordType.AUDIT: "audits",
        CleanupRecordType.TRIAGE: "triage",
        CleanupRecordType.DIAGNOSIS: "diagnoses",
    }
    if (
        len(relative.parts) != 2
        or relative.parts[0] != directories[candidate.record_type]
        or relative.name == "latest.json"
        or relative.suffix != ".json"
    ):
        raise ValueError("cleanup candidate is outside controlled history")
    directory = autotest / relative.parts[0]
    _require_real_directory(directory)
    target = directory / relative.name
    if target.is_symlink():
        raise ValueError("cleanup candidate changed after planning")
    return target


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_real_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"controlled directory must not be a symbolic link: {path}")
    if not path.is_dir():
        raise ValueError(f"controlled path must be a directory: {path}")


def _validate_non_negative_integer(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
