"""Stable models for safe history cleanup planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CleanupRecordType(StrEnum):
    AUDIT = "audit"
    TRIAGE = "triage"
    DIAGNOSIS = "diagnosis"


class CleanupReason(StrEnum):
    EXPIRED = "expired"
    CAPACITY_PRESSURE = "capacity_pressure"
    WITHIN_RETENTION = "within_retention"
    LATEST_RETENTION = "latest_retention"
    LATEST_ALIAS = "latest_alias"
    DIAGNOSIS_OPT_IN_REQUIRED = "diagnosis_opt_in_required"
    REFERENCED = "referenced"
    INVALID_RECORD = "invalid_record"
    SYMBOLIC_LINK = "symbolic_link"
    HARD_LINK = "hard_link"
    DUPLICATE_INODE = "duplicate_inode"
    NON_REGULAR_FILE = "non_regular_file"


@dataclass(frozen=True)
class CleanupCandidate:
    relative_path: str
    record_type: CleanupRecordType
    size_bytes: int
    created_at: datetime
    reasons: tuple[CleanupReason, ...]
    device: int
    inode: int
    mtime_ns: int

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path)
        if not isinstance(self.record_type, CleanupRecordType):
            raise ValueError("record_type must be CleanupRecordType")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be non-negative")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if not isinstance(self.reasons, tuple) or not self.reasons or any(
            not isinstance(reason, CleanupReason) for reason in self.reasons
        ):
            raise ValueError("reasons must contain CleanupReason")
        for field_name in ("device", "inode", "mtime_ns"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be non-negative")

    @property
    def type(self) -> CleanupRecordType:
        return self.record_type

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "type": self.record_type.value,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "reasons": [reason.value for reason in self.reasons],
        }


@dataclass(frozen=True)
class CleanupProtection:
    relative_path: str
    record_type: CleanupRecordType
    reasons: tuple[CleanupReason, ...]

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path)
        if not isinstance(self.record_type, CleanupRecordType):
            raise ValueError("record_type must be CleanupRecordType")
        if not isinstance(self.reasons, tuple) or not self.reasons or any(
            not isinstance(reason, CleanupReason) for reason in self.reasons
        ):
            raise ValueError("reasons must contain CleanupReason")

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "type": self.record_type.value,
            "reasons": [reason.value for reason in self.reasons],
        }


@dataclass(frozen=True)
class CleanupPlan:
    schema_version: int
    candidates: tuple[CleanupCandidate, ...]
    protected_count: int
    reclaimable_bytes: int
    protected: tuple[CleanupProtection, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, CleanupCandidate) for item in self.candidates
        ):
            raise ValueError("candidates must contain CleanupCandidate")
        if not isinstance(self.protected, tuple) or any(
            not isinstance(item, CleanupProtection) for item in self.protected
        ):
            raise ValueError("protected must contain CleanupProtection")
        if (
            isinstance(self.protected_count, bool)
            or not isinstance(self.protected_count, int)
            or self.protected_count < 0
        ):
            raise ValueError("protected_count must be non-negative")
        if (
            isinstance(self.reclaimable_bytes, bool)
            or not isinstance(self.reclaimable_bytes, int)
            or self.reclaimable_bytes < 0
        ):
            raise ValueError("reclaimable_bytes must be non-negative")
        if self.protected_count != len(self.protected):
            raise ValueError("protected_count does not match protected records")
        if self.reclaimable_bytes != sum(
            candidate.size_bytes for candidate in self.candidates
        ):
            raise ValueError("reclaimable_bytes does not match candidates")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "protected_count": self.protected_count,
            "reclaimable_bytes": self.reclaimable_bytes,
            "protected": [item.to_dict() for item in self.protected],
        }


@dataclass(frozen=True)
class CleanupResult:
    schema_version: int
    deleted_paths: tuple[str, ...]
    reclaimed_bytes: int

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if not isinstance(self.deleted_paths, tuple):
            raise ValueError("deleted_paths must be a tuple")
        for path in self.deleted_paths:
            _validate_relative_path(path)
        if (
            isinstance(self.reclaimed_bytes, bool)
            or not isinstance(self.reclaimed_bytes, int)
            or self.reclaimed_bytes < 0
        ):
            raise ValueError("reclaimed_bytes must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "deleted_paths": list(self.deleted_paths),
            "reclaimed_bytes": self.reclaimed_bytes,
        }


def _validate_relative_path(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or ".." in value.split("/")
        or value.startswith(".autotest/")
    ):
        raise ValueError("path must be relative to .autotest")
