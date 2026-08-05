"""Stable models for performance measurements."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class BenchmarkResult:
    """One versioned benchmark measurement."""

    schema_version: int
    name: str
    profile: str
    input_counts: Mapping[str, int]
    wall_time_seconds: float
    traced_peak_bytes: int
    rss_peak_bytes: int
    output_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("schema_version must be 1")

        for field_name in ("name", "profile", "output_digest"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not isinstance(self.input_counts, Mapping):
            raise ValueError("input_counts must be a mapping")
        normalized_counts: dict[str, int] = {}
        for key, value in self.input_counts.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("input_counts keys must be non-empty strings")
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    "input_counts values must be non-negative integers"
                )
            normalized_counts[key] = value
        object.__setattr__(
            self,
            "input_counts",
            MappingProxyType(dict(sorted(normalized_counts.items()))),
        )

        if (
            isinstance(self.wall_time_seconds, bool)
            or not isinstance(self.wall_time_seconds, (int, float))
            or not math.isfinite(self.wall_time_seconds)
            or self.wall_time_seconds < 0
        ):
            raise ValueError("wall_time_seconds must be finite and non-negative")

        for field_name in ("traced_peak_bytes", "rss_peak_bytes"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-encodable representation."""

        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "profile": self.profile,
            "input_counts": dict(self.input_counts),
            "wall_time_seconds": self.wall_time_seconds,
            "traced_peak_bytes": self.traced_peak_bytes,
            "rss_peak_bytes": self.rss_peak_bytes,
            "output_digest": self.output_digest,
        }
