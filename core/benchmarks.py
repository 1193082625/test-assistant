"""Reproducible benchmark measurement and report helpers."""

from __future__ import annotations

import platform
import resource
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from core.models import BenchmarkResult


BenchmarkOperation = Callable[[], str]


@dataclass(frozen=True)
class BenchmarkCase:
    """A named benchmark operation and its stable input dimensions."""

    name: str
    input_counts: Mapping[str, int]
    operation: BenchmarkOperation

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.input_counts, Mapping):
            raise ValueError("input_counts must be a mapping")
        if not callable(self.operation):
            raise ValueError("operation must be callable")
        normalized_counts: dict[str, int] = {}
        for key, value in self.input_counts.items():
            if (
                not isinstance(key, str)
                or not key.strip()
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError("input_counts must contain stable counts")
            normalized_counts[key] = value
        object.__setattr__(
            self,
            "input_counts",
            MappingProxyType(dict(sorted(normalized_counts.items()))),
        )


@dataclass(frozen=True)
class BenchmarkLimits:
    """Broad safety limits applied to every measured sample."""

    wall_time_seconds: float = 30.0
    traced_peak_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        if (
            isinstance(self.wall_time_seconds, bool)
            or not isinstance(self.wall_time_seconds, (int, float))
            or self.wall_time_seconds < 0
        ):
            raise ValueError("wall_time_seconds must be non-negative")
        if (
            isinstance(self.traced_peak_bytes, bool)
            or not isinstance(self.traced_peak_bytes, int)
            or self.traced_peak_bytes < 0
        ):
            raise ValueError("traced_peak_bytes must be non-negative")


class BenchmarkLimitExceeded(RuntimeError):
    """Raised when an individual sample exceeds a safety limit."""


def measure_benchmark(
    operation: BenchmarkOperation,
    *,
    name: str,
    profile: str,
    input_counts: Mapping[str, int],
) -> BenchmarkResult:
    """Measure one operation using monotonic time and memory peaks."""

    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    tracemalloc.reset_peak()
    start_ns = time.perf_counter_ns()
    try:
        output_digest = operation()
        elapsed_ns = time.perf_counter_ns() - start_ns
        _, traced_peak_bytes = tracemalloc.get_traced_memory()
    finally:
        if not tracing_was_active:
            tracemalloc.stop()

    if not isinstance(output_digest, str) or not output_digest.strip():
        raise ValueError("benchmark operation must return a non-empty digest")

    return BenchmarkResult(
        schema_version=1,
        name=name,
        profile=profile,
        input_counts=input_counts,
        wall_time_seconds=elapsed_ns / 1_000_000_000,
        traced_peak_bytes=traced_peak_bytes,
        rss_peak_bytes=_rss_peak_bytes(),
        output_digest=output_digest,
    )


def run_benchmark(
    case: BenchmarkCase,
    *,
    profile: str,
    sample_count: int = 3,
) -> tuple[BenchmarkResult, ...]:
    """Warm once, then collect a fixed number of measured samples."""

    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count <= 0
    ):
        raise ValueError("sample_count must be a positive integer")

    expected_digest = case.operation()
    if not isinstance(expected_digest, str) or not expected_digest.strip():
        raise ValueError("benchmark operation must return a non-empty digest")

    results = tuple(
        measure_benchmark(
            case.operation,
            name=case.name,
            profile=profile,
            input_counts=case.input_counts,
        )
        for _ in range(sample_count)
    )
    if any(result.output_digest != expected_digest for result in results):
        raise RuntimeError("benchmark output digest changed between runs")
    return results


def render_report(
    *,
    profile: str,
    benchmark_results: Mapping[str, Sequence[BenchmarkResult]],
    limits: BenchmarkLimits | None = None,
) -> dict[str, object]:
    """Summarize raw samples with median time and maximum memory peaks."""

    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("profile must be a non-empty string")

    summaries: list[dict[str, object]] = []
    for name in sorted(benchmark_results):
        results = tuple(benchmark_results[name])
        _validate_result_group(name, profile, results)
        if limits is not None:
            _enforce_limits(results, limits)
        first = results[0]
        summaries.append(
            {
                "name": name,
                "profile": profile,
                "input_counts": dict(first.input_counts),
                "samples": [result.to_dict() for result in results],
                "wall_time_seconds_median": statistics.median(
                    result.wall_time_seconds for result in results
                ),
                "traced_peak_bytes_max": max(
                    result.traced_peak_bytes for result in results
                ),
                "rss_peak_bytes_max": max(
                    result.rss_peak_bytes for result in results
                ),
                "output_digest": first.output_digest,
            }
        )
    return {
        "schema_version": 1,
        "profile": profile,
        "benchmarks": summaries,
    }


def _validate_result_group(
    name: str,
    profile: str,
    results: tuple[BenchmarkResult, ...],
) -> None:
    if not results:
        raise ValueError(f"benchmark {name!r} has no samples")
    first = results[0]
    for result in results:
        if result.name != name or result.profile != profile:
            raise ValueError("benchmark result identity does not match its group")
        if (
            result.input_counts != first.input_counts
            or result.output_digest != first.output_digest
        ):
            raise ValueError("benchmark samples describe different work")


def _enforce_limits(
    results: Sequence[BenchmarkResult],
    limits: BenchmarkLimits,
) -> None:
    for result in results:
        if result.wall_time_seconds > limits.wall_time_seconds:
            raise BenchmarkLimitExceeded(
                f"{result.name} exceeded wall-time limit"
            )
        if result.traced_peak_bytes > limits.traced_peak_bytes:
            raise BenchmarkLimitExceeded(
                f"{result.name} exceeded traced-memory limit"
            )


def _rss_peak_bytes() -> int:
    maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return int(maximum_rss)
    return int(maximum_rss) * 1024
