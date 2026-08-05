"""Read-only planning and transactional application of schema migrations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from core.models import (
    MigrationAction,
    MigrationItem,
    MigrationPlan,
    MigrationResult,
)
from core.repositories import (
    AuditRepository,
    DiagnosisRepository,
    GitPermissionRepository,
    TriageRepository,
    VerificationStateRepository,
    atomic_write_json,
)


TARGET_VERSION = 2


@dataclass(frozen=True)
class _RecordSpec:
    directory: str | None
    record_type: str
    loader: Callable[[Path], dict[str, object]]
    has_history: bool


def plan_migration(*, project_root: str | Path) -> MigrationPlan:
    """Scan only controlled paths and return a read-only migration plan."""

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"project path does not exist: {root}")
    autotest = root / ".autotest"
    if not os.path.lexists(autotest):
        return MigrationPlan(schema_version=1, items=())
    _require_real_directory(autotest)

    audit = AuditRepository(root)
    triage = TriageRepository(root)
    diagnosis = DiagnosisRepository(root)
    verification = VerificationStateRepository(root)
    permission = GitPermissionRepository(root)
    specs = (
        _RecordSpec("audits", "audit", audit._load_path, True),
        _RecordSpec("triage", "triage", triage._load_path, True),
        _RecordSpec("diagnoses", "diagnosis", diagnosis._load_path, True),
        _RecordSpec(
            "verification",
            "verification",
            lambda path: _load_singleton(verification.path, verification.load, path),
            False,
        ),
        _RecordSpec(
            None,
            "git_permission",
            lambda path: _load_singleton(permission.path, permission.load, path),
            False,
        ),
    )

    items: list[MigrationItem] = []
    blocked = False
    for spec in specs:
        if spec.directory is None:
            path = autotest / "permissions.json"
            if os.path.lexists(path):
                if path.is_symlink():
                    raise ValueError(
                        f"controlled record must not be a symbolic link: {path}"
                    )
                item, item_blocked = _plan_existing(path, autotest, spec)
                items.append(item)
                blocked = blocked or item_blocked
            continue

        directory = autotest / spec.directory
        if not os.path.lexists(directory):
            continue
        _require_real_directory(directory)
        paths = sorted(
            path
            for path in directory.iterdir()
            if path.suffix == ".json" and (path.is_file() or path.is_symlink())
        )
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"controlled record must not be a symbolic link: {path}")
        history_paths = (
            tuple(path for path in paths if path.name != "latest.json")
            if spec.has_history
            else ()
        )
        for path in history_paths:
            item, item_blocked = _plan_existing(path, autotest, spec)
            items.append(item)
            blocked = blocked or item_blocked
        latest = directory / "latest.json"
        if spec.has_history:
            item, item_blocked = _plan_latest(
                latest,
                history_paths,
                autotest,
                spec,
            )
            if item is not None:
                items.append(item)
                blocked = blocked or item_blocked
        elif os.path.lexists(latest):
            item, item_blocked = _plan_existing(latest, autotest, spec)
            items.append(item)
            blocked = blocked or item_blocked

    items.sort(key=lambda item: item.relative_path)
    return MigrationPlan(schema_version=1, items=tuple(items), blocked=blocked)


def execute_migration(
    *,
    project_root: str | Path,
    plan: MigrationPlan,
) -> MigrationResult:
    """Apply a previously generated plan as one recoverable transaction."""

    if not isinstance(plan, MigrationPlan):
        raise ValueError("plan must be MigrationPlan")
    if plan.schema_version != 1:
        raise ValueError("unsupported migration plan version")
    if plan.blocked:
        raise ValueError("migration plan is blocked")
    root = Path(project_root).resolve()
    autotest = root / ".autotest"
    _require_real_directory(autotest)
    actionable = tuple(
        item for item in plan.items if item.action is not MigrationAction.SKIP
    )
    if not actionable:
        return MigrationResult(1, True, 0, 0)

    targets: list[tuple[MigrationItem, Path, Path | None]] = []
    for item in actionable:
        _validate_item_scope(item)
        target = _controlled_path(autotest, item.relative_path)
        _verify_digest(target, item.source_digest)
        recovery = None
        if item.recovery_source is not None:
            _validate_recovery_scope(item)
            recovery = _controlled_path(autotest, item.recovery_source)
            _verify_digest(recovery, item.recovery_digest)
        targets.append((item, target, recovery))

    backup_root = Path(
        tempfile.mkdtemp(
            prefix=".autotest-migrate-backup-",
            dir=root.parent,
        )
    )
    existed: dict[Path, bool] = {}
    try:
        for _, target, _ in targets:
            existed[target] = target.exists()
            if target.exists():
                backup = backup_root / target.relative_to(autotest)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
    except BaseException:
        shutil.rmtree(backup_root, ignore_errors=True)
        raise

    written: list[Path] = []
    try:
        for item, target, recovery in targets:
            source = recovery if recovery is not None else target
            payload = _load_for_type(root, source, item.record_type)
            atomic_write_json(target, payload)
            written.append(target)
    except BaseException:
        rollback_errors: list[OSError] = []
        for target in reversed(written):
            try:
                if existed[target]:
                    backup = backup_root / target.relative_to(autotest)
                    if backup.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            except OSError as error:
                rollback_errors.append(error)
        if rollback_errors:
            raise RuntimeError(
                "migration failed and rollback was incomplete; "
                f"backup preserved at {backup_root}"
            )
        shutil.rmtree(backup_root, ignore_errors=True)
        raise
    shutil.rmtree(backup_root)
    return MigrationResult(
        schema_version=1,
        applied=True,
        migrated_count=sum(
            item.action is MigrationAction.MIGRATE for item in actionable
        ),
        repaired_count=sum(
            item.action is MigrationAction.REPAIR_LATEST for item in actionable
        ),
    )


def _plan_existing(
    path: Path,
    autotest: Path,
    spec: _RecordSpec,
) -> tuple[MigrationItem, bool]:
    source_digest = _file_digest(path)
    source_version = _read_source_version(path)
    if source_version is not None and source_version > TARGET_VERSION:
        return (
            _item(path, autotest, spec, source_version, MigrationAction.SKIP,
                  source_digest, reason="unknown_future_version"),
            True,
        )
    try:
        spec.loader(path)
    except (KeyError, OSError, TypeError, ValueError) as error:
        return (
            _item(path, autotest, spec, source_version, MigrationAction.SKIP,
                  source_digest, reason=f"invalid_record:{type(error).__name__}"),
            False,
        )
    action = (
        MigrationAction.MIGRATE
        if source_version is not None and source_version < TARGET_VERSION
        else MigrationAction.SKIP
    )
    return _item(path, autotest, spec, source_version, action, source_digest), False


def _plan_latest(
    latest: Path,
    history_paths: tuple[Path, ...],
    autotest: Path,
    spec: _RecordSpec,
) -> tuple[MigrationItem | None, bool]:
    if os.path.lexists(latest):
        item, blocked = _plan_existing(latest, autotest, spec)
        if blocked or item.action is not MigrationAction.SKIP or item.reason is None:
            return item, blocked
    newest = _newest_valid_history(history_paths, spec)
    if newest is None:
        if os.path.lexists(latest):
            return item, False
        return None, False
    source_version = _read_source_version(latest) if os.path.lexists(latest) else None
    return MigrationItem(
        relative_path=latest.relative_to(autotest).as_posix(),
        record_type=spec.record_type,
        source_version=source_version,
        target_version=TARGET_VERSION,
        action=MigrationAction.REPAIR_LATEST,
        source_digest=_file_digest(latest) if os.path.lexists(latest) else None,
        recovery_source=newest.relative_to(autotest).as_posix(),
        recovery_digest=_file_digest(newest),
        reason="latest_missing_or_invalid",
    ), False


def _newest_valid_history(
    paths: tuple[Path, ...],
    spec: _RecordSpec,
) -> Path | None:
    candidates: list[tuple[float, str, Path]] = []
    for path in paths:
        try:
            payload = spec.loader(path)
            created_at = payload.get("created_at")
            if not isinstance(created_at, str):
                continue
            timestamp = datetime.fromisoformat(created_at)
            if timestamp.tzinfo is None:
                continue
        except (KeyError, OSError, TypeError, ValueError):
            continue
        candidates.append((timestamp.timestamp(), path.name, path))
    return max(candidates)[2] if candidates else None


def _load_for_type(root: Path, path: Path, record_type: str) -> dict[str, object]:
    if record_type == "audit":
        return AuditRepository(root)._load_path(path)
    if record_type == "triage":
        return TriageRepository(root)._load_path(path)
    if record_type == "diagnosis":
        return DiagnosisRepository(root)._load_path(path)
    if record_type == "verification":
        value = VerificationStateRepository(root).load()
    elif record_type == "git_permission":
        value = GitPermissionRepository(root).load()
    else:
        raise ValueError(f"unsupported record type: {record_type}")
    if value is None:
        raise ValueError(f"missing {record_type} record")
    return value


def _load_singleton(
    expected_path: Path,
    loader: Callable[[], dict[str, object] | None],
    actual_path: Path,
) -> dict[str, object]:
    if actual_path != expected_path:
        raise ValueError("singleton path mismatch")
    payload = loader()
    if payload is None:
        raise ValueError("singleton record is missing")
    return payload


def _item(
    path: Path,
    autotest: Path,
    spec: _RecordSpec,
    source_version: int | None,
    action: MigrationAction,
    source_digest: str,
    *,
    reason: str | None = None,
) -> MigrationItem:
    return MigrationItem(
        relative_path=path.relative_to(autotest).as_posix(),
        record_type=spec.record_type,
        source_version=source_version,
        target_version=TARGET_VERSION,
        action=action,
        source_digest=source_digest,
        reason=reason,
    )


def _read_source_version(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("schema_version")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_digest(path: Path, expected: str | None) -> None:
    if expected is None:
        if os.path.lexists(path):
            raise ValueError(f"migration target changed after planning: {path}")
        return
    if not path.is_file() or path.is_symlink() or _file_digest(path) != expected:
        raise ValueError(f"migration target changed after planning: {path}")


def _controlled_path(autotest: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("migration path is outside .autotest")
    target = autotest.joinpath(*relative.parts)
    current = autotest
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError("migration path contains a symbolic link")
    if target.is_symlink():
        raise ValueError("migration target must not be a symbolic link")
    return target


def _validate_item_scope(item: MigrationItem) -> None:
    path = PurePosixPath(item.relative_path)
    allowed = {
        "audit": len(path.parts) == 2 and path.parts[0] == "audits",
        "triage": len(path.parts) == 2 and path.parts[0] == "triage",
        "diagnosis": len(path.parts) == 2 and path.parts[0] == "diagnoses",
        "verification": path.parts == ("verification", "latest.json"),
        "git_permission": path.parts == ("permissions.json",),
    }
    if not allowed.get(item.record_type, False) or path.suffix != ".json":
        raise ValueError("migration item is outside its controlled record scope")


def _validate_recovery_scope(item: MigrationItem) -> None:
    if item.action is not MigrationAction.REPAIR_LATEST:
        raise ValueError("only latest repair may use a recovery source")
    source = PurePosixPath(item.recovery_source or "")
    target = PurePosixPath(item.relative_path)
    if (
        len(source.parts) != 2
        or source.parent != target.parent
        or source.name == "latest.json"
        or source.suffix != ".json"
    ):
        raise ValueError("invalid latest recovery source")


def _require_real_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"controlled directory must not be a symbolic link: {path}")
    if not path.is_dir():
        raise ValueError(f"controlled path must be a directory: {path}")
