"""Contracts for shared versioned JSON repository infrastructure."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import core.repositories.schema as schema_module
from core.repositories import LoadedRecord, SchemaRegistry, atomic_write_json


def _registry() -> SchemaRegistry:
    def migrate_example_v1(payload):
        return {
            **payload,
            "schema_version": 2,
            "renamed": payload["legacy"],
        }

    return SchemaRegistry(
        current_versions={"example": 2},
        migrations={("example", 1): migrate_example_v1},
    )


def test_atomic_write_json_writes_stable_json(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "record.json"

    atomic_write_json(
        path,
        {"schema_version": 2, "record_type": "example", "value": 1},
    )

    assert json.loads(path.read_text(encoding="utf-8"))["value"] == 1
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_load_rejects_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON"):
        _registry().load(path, record_type="example")


@pytest.mark.parametrize("version", [True, False, 0, -1, "1"])
def test_registry_rejects_invalid_schema_version(version: object) -> None:
    with pytest.raises(ValueError, match="schema_version"):
        _registry().migrate_payload(
            {
                "schema_version": version,
                "record_type": "example",
            },
            record_type="example",
        )


def test_registry_rejects_unknown_future_version() -> None:
    with pytest.raises(ValueError, match="future"):
        _registry().migrate_payload(
            {"schema_version": 3, "record_type": "example"},
            record_type="example",
        )


def test_registry_rejects_wrong_record_type() -> None:
    with pytest.raises(ValueError, match="record_type"):
        _registry().migrate_payload(
            {"schema_version": 1, "record_type": "other", "legacy": 1},
            record_type="example",
        )


def test_v1_to_v2_migration_is_in_memory_and_preserves_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "record.json"
    original = {
        "schema_version": 1,
        "record_type": "example",
        "legacy": {"nested": [1, 2]},
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    before_bytes = path.read_bytes()

    loaded = _registry().load(path, record_type="example")

    assert loaded == LoadedRecord(
        payload={
            "schema_version": 2,
            "record_type": "example",
            "legacy": {"nested": [1, 2]},
            "renamed": {"nested": [1, 2]},
        },
        source_version=1,
        migrated=True,
    )
    assert path.read_bytes() == before_bytes


def test_migrate_payload_does_not_modify_input() -> None:
    payload = {
        "schema_version": 1,
        "record_type": "example",
        "legacy": {"nested": [1]},
    }
    original = deepcopy(payload)

    _registry().migrate_payload(payload, record_type="example")

    assert payload == original


def test_registry_rejects_mutating_migration() -> None:
    def mutate(payload):
        payload["schema_version"] = 2
        return payload

    registry = SchemaRegistry(
        current_versions={"example": 2},
        migrations={("example", 1): mutate},
    )

    with pytest.raises(ValueError, match="must not mutate"):
        registry.migrate_payload(
            {"schema_version": 1, "record_type": "example"},
            record_type="example",
        )


def test_registry_rejects_migration_chain_gap() -> None:
    registry = SchemaRegistry(
        current_versions={"example": 3},
        migrations={
            ("example", 1): lambda payload: {
                **payload,
                "schema_version": 2,
            },
        },
    )

    with pytest.raises(ValueError, match="missing migration"):
        registry.migrate_payload(
            {"schema_version": 1, "record_type": "example"},
            record_type="example",
        )


def test_atomic_write_failure_preserves_old_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "record.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(schema_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_json(path, {"new": True})

    assert path.read_text(encoding="utf-8") == '{"old": true}\n'
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))
