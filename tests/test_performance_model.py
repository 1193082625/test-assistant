"""Contracts for versioned performance result models."""

import math

import pytest

from core.models import BenchmarkResult


def _result(**overrides: object) -> BenchmarkResult:
    values: dict[str, object] = {
        "schema_version": 1,
        "name": "snapshot",
        "profile": "ci",
        "input_counts": {"files": 100, "symbols": 1_000},
        "wall_time_seconds": 0.25,
        "traced_peak_bytes": 1_024,
        "rss_peak_bytes": 2_048,
        "output_digest": "abc123",
    }
    values.update(overrides)
    return BenchmarkResult(**values)  # type: ignore[arg-type]


def test_benchmark_result_normalizes_and_serializes_counts() -> None:
    result = _result(input_counts={"symbols": 1_000, "files": 100})

    assert tuple(result.input_counts) == ("files", "symbols")
    assert result.to_dict() == {
        "schema_version": 1,
        "name": "snapshot",
        "profile": "ci",
        "input_counts": {"files": 100, "symbols": 1_000},
        "wall_time_seconds": 0.25,
        "traced_peak_bytes": 1_024,
        "rss_peak_bytes": 2_048,
        "output_digest": "abc123",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("name", " "),
        ("profile", ""),
        ("output_digest", None),
        ("wall_time_seconds", -0.1),
        ("wall_time_seconds", math.inf),
        ("wall_time_seconds", True),
        ("traced_peak_bytes", -1),
        ("traced_peak_bytes", 1.5),
        ("rss_peak_bytes", True),
    ],
)
def test_benchmark_result_rejects_invalid_scalar_fields(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        _result(**{field: value})


@pytest.mark.parametrize(
    "counts",
    [
        [],
        {"": 1},
        {"files": -1},
        {"files": True},
        {1: 2},
    ],
)
def test_benchmark_result_rejects_invalid_input_counts(counts: object) -> None:
    with pytest.raises(ValueError):
        _result(input_counts=counts)


def test_benchmark_result_copies_input_counts() -> None:
    counts = {"files": 1}
    result = _result(input_counts=counts)

    counts["files"] = 999

    assert result.input_counts["files"] == 1
    with pytest.raises(TypeError):
        result.input_counts["files"] = 2  # type: ignore[index]
