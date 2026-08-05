"""Shared versioned JSON loading, migration, and atomic writing."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


Migration = Callable[[dict[str, object]], Mapping[str, object]]


@dataclass(frozen=True)
class LoadedRecord:
    """A validated record and its on-disk version information."""

    payload: dict[str, object]
    source_version: int
    migrated: bool


@dataclass(frozen=True)
class LatestRecord:
    """A latest payload and the path it was safely loaded from."""

    payload: dict[str, object]
    recovered: bool
    source_path: Path


class SchemaRegistry:
    """Validate and migrate explicitly registered record types in memory."""

    def __init__(
        self,
        *,
        current_versions: Mapping[str, int],
        migrations: Mapping[tuple[str, int], Migration] | None = None,
    ) -> None:
        if not isinstance(current_versions, Mapping) or not current_versions:
            raise ValueError("current_versions must be a non-empty mapping")

        normalized_versions: dict[str, int] = {}
        for record_type, version in current_versions.items():
            _validate_record_type(record_type)
            _validate_schema_version(version)
            normalized_versions[record_type] = version

        normalized_migrations: dict[tuple[str, int], Migration] = {}
        for key, migration in (migrations or {}).items():
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or key[0] not in normalized_versions
            ):
                raise ValueError("migration key must identify a registered type")
            _validate_schema_version(key[1])
            if not callable(migration):
                raise ValueError("migration must be callable")
            normalized_migrations[key] = migration

        self._current_versions = normalized_versions
        self._migrations = normalized_migrations

    def load(self, path: Path, *, record_type: str) -> LoadedRecord:
        """Read and migrate one JSON object without writing it back."""

        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("record JSON is corrupt") from error
        return self.migrate_payload(payload, record_type=record_type)

    def migrate_payload(
        self,
        payload: Mapping[str, object],
        *,
        record_type: str,
    ) -> LoadedRecord:
        """Validate and purely migrate a payload to its registered version."""

        _validate_record_type(record_type)
        if record_type not in self._current_versions:
            raise ValueError(f"unknown record_type: {record_type}")
        if not isinstance(payload, Mapping):
            raise ValueError("record payload must be an object")

        working = deepcopy(dict(payload))
        source_version = working.get("schema_version")
        _validate_schema_version(source_version)
        target_version = self._current_versions[record_type]
        if source_version > target_version:
            raise ValueError("record uses an unknown future schema_version")
        stored_record_type = working.get("record_type")
        if (
            stored_record_type != record_type
            and not (
                stored_record_type is None
                and source_version < target_version
            )
        ):
            raise ValueError("record_type does not match requested type")

        current_version = source_version
        while current_version < target_version:
            migration = self._migrations.get((record_type, current_version))
            if migration is None:
                raise ValueError(
                    f"missing migration for {record_type} v{current_version}"
                )

            migration_input = deepcopy(working)
            input_before = deepcopy(migration_input)
            migrated_payload = migration(migration_input)
            if migration_input != input_before:
                raise ValueError("migration must not mutate its input")
            if not isinstance(migrated_payload, Mapping):
                raise ValueError("migration must return an object")

            working = deepcopy(dict(migrated_payload))
            if working.get("record_type") != record_type:
                raise ValueError("migration changed record_type")
            next_version = working.get("schema_version")
            _validate_schema_version(next_version)
            if next_version != current_version + 1:
                raise ValueError("migration must advance exactly one version")
            current_version = next_version

        return LoadedRecord(
            payload=working,
            source_version=source_version,
            migrated=source_version != target_version,
        )


def atomic_write_json(
    path: Path,
    payload: Mapping[str, object],
) -> None:
    """Atomically replace one JSON file and preserve the old file on error."""

    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                deepcopy(dict(payload)),
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def load_latest_with_recovery(
    latest_path: Path,
    *,
    load_path: Callable[[Path], dict[str, object]],
) -> LatestRecord | None:
    """Read latest or recover the newest valid immutable history in memory."""

    latest_path = Path(latest_path)
    if not os.path.lexists(latest_path):
        return None
    try:
        if latest_path.is_symlink():
            raise ValueError("latest record must not be a symbolic link")
        return LatestRecord(
            payload=load_path(latest_path),
            recovered=False,
            source_path=latest_path,
        )
    except (KeyError, OSError, TypeError, ValueError) as latest_error:
        candidates: list[tuple[float, str, Path, dict[str, object]]] = []
        try:
            paths = tuple(latest_path.parent.iterdir())
        except OSError:
            raise latest_error
        for path in paths:
            if (
                path == latest_path
                or path.suffix != ".json"
                or path.is_symlink()
                or not path.is_file()
            ):
                continue
            try:
                payload = load_path(path)
                created_at = payload.get("created_at")
                if not isinstance(created_at, str):
                    continue
                timestamp = datetime.fromisoformat(created_at)
                if timestamp.tzinfo is None:
                    continue
            except (KeyError, OSError, TypeError, ValueError):
                continue
            candidates.append((timestamp.timestamp(), path.name, path, payload))
        if not candidates:
            raise latest_error
        _, _, source_path, payload = max(candidates)
        return LatestRecord(
            payload=payload,
            recovered=True,
            source_path=source_path,
        )


def _validate_record_type(record_type: object) -> None:
    if not isinstance(record_type, str) or not record_type.strip():
        raise ValueError("record_type must be a non-empty string")


def _validate_schema_version(version: object) -> None:
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("schema_version must be a positive integer")
