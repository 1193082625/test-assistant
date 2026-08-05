"""Stable models for explicit repository schema migration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MigrationAction(StrEnum):
    MIGRATE = "migrate"
    REPAIR_LATEST = "repair_latest"
    SKIP = "skip"


@dataclass(frozen=True)
class MigrationItem:
    relative_path: str
    record_type: str
    source_version: int | None
    target_version: int
    action: MigrationAction
    source_digest: str | None
    recovery_source: str | None = None
    recovery_digest: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "record_type": self.record_type,
            "source_version": self.source_version,
            "target_version": self.target_version,
            "action": self.action.value,
            "source_digest": self.source_digest,
            "recovery_source": self.recovery_source,
            "recovery_digest": self.recovery_digest,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MigrationPlan:
    schema_version: int
    items: tuple[MigrationItem, ...]
    blocked: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "blocked": self.blocked,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class MigrationResult:
    schema_version: int
    applied: bool
    migrated_count: int
    repaired_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "applied": self.applied,
            "migrated_count": self.migrated_count,
            "repaired_count": self.repaired_count,
        }
