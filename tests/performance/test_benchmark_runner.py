"""Contracts for reproducible benchmark measurement and reporting."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.benchmarks as benchmark_module
from core.benchmarks import (
    BenchmarkCase,
    BenchmarkLimitExceeded,
    BenchmarkLimits,
    measure_benchmark,
    render_report,
    run_benchmark,
)
from scripts import run_benchmarks


@pytest.mark.performance
def test_measure_benchmark_captures_metrics_and_digest() -> None:
    result = measure_benchmark(
        lambda: "stable-digest",
        name="example",
        profile="ci",
        input_counts={"items": 3},
    )

    assert result.name == "example"
    assert result.profile == "ci"
    assert result.wall_time_seconds >= 0
    assert result.traced_peak_bytes >= 0
    assert result.rss_peak_bytes >= 0
    assert result.output_digest == "stable-digest"


@pytest.mark.parametrize(
    ("system_name", "expected"),
    [("Darwin", 123), ("Linux", 123 * 1024)],
)
def test_rss_peak_uses_platform_units(
    monkeypatch: pytest.MonkeyPatch,
    system_name: str,
    expected: int,
) -> None:
    monkeypatch.setattr(
        benchmark_module.platform,
        "system",
        lambda: system_name,
    )
    monkeypatch.setattr(
        benchmark_module.resource,
        "getrusage",
        lambda _: SimpleNamespace(ru_maxrss=123),
    )

    assert benchmark_module._rss_peak_bytes() == expected


@pytest.mark.performance
def test_run_benchmark_warms_once_and_measures_three_times() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        return "same-output"

    results = run_benchmark(
        BenchmarkCase(
            name="example",
            input_counts={"items": 1},
            operation=operation,
        ),
        profile="ci",
    )

    assert calls == 4
    assert len(results) == 3
    assert {result.output_digest for result in results} == {"same-output"}


def test_run_benchmark_rejects_changed_output() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        return str(calls)

    with pytest.raises(RuntimeError, match="output digest"):
        run_benchmark(
            BenchmarkCase(
                name="unstable",
                input_counts={},
                operation=operation,
            ),
            profile="ci",
        )


def test_limits_apply_to_each_measured_sample() -> None:
    results = run_benchmark(
        BenchmarkCase("example", {}, lambda: "digest"),
        profile="ci",
    )

    with pytest.raises(BenchmarkLimitExceeded):
        render_report(
            profile="ci",
            benchmark_results={"example": results},
            limits=BenchmarkLimits(
                wall_time_seconds=0,
                traced_peak_bytes=0,
            ),
        )


def test_report_contains_raw_samples_median_and_maxima() -> None:
    results = run_benchmark(
        BenchmarkCase("example", {"items": 2}, lambda: "digest"),
        profile="ci",
    )

    report = render_report(
        profile="ci",
        benchmark_results={"example": results},
    )
    benchmark = report["benchmarks"][0]

    assert report["schema_version"] == 1
    assert benchmark["name"] == "example"
    assert len(benchmark["samples"]) == 3
    assert benchmark["wall_time_seconds_median"] >= 0
    assert benchmark["traced_peak_bytes_max"] >= 0
    assert benchmark["rss_peak_bytes_max"] >= 0
    assert benchmark["output_digest"] == "digest"


def test_cli_writes_pure_json_and_atomic_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = BenchmarkCase("example", {"items": 1}, lambda: "digest")
    output = tmp_path / "nested" / "report.json"

    exit_code = run_benchmarks.main(
        ["--profile", "ci", "--json", "--output", str(output)],
        cases=(case,),
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert not list(output.parent.glob(".*.tmp"))


def test_cli_rejects_unknown_profile(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_benchmarks.main(["--profile", "unknown"])

    assert exit_code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_project_profile_is_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "真实 project"
    project.mkdir()
    source = project / "app.py"
    source.write_text(
        "def add(left, right):\n    return left + right\n",
        encoding="utf-8",
    )
    before = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    exit_code = run_benchmarks.main(
        ["--profile", "ci", "--project", str(project), "--json"],
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["benchmarks"][0]["name"] == "project_snapshot_and_symbols"
    assert payload["benchmarks"][0]["input_counts"] == {
        "files": 1,
        "python_symbols": 1,
    }
    after = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    assert after == before
