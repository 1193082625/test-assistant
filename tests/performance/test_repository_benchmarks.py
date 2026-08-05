"""Correctness gates for repository benchmark adapters."""

from pathlib import Path

import pytest

from core.benchmarks import run_benchmark
from tests.performance.benchmark_cases import build_benchmark_cases
from tests.performance.fixture_factory import FixtureProfile


@pytest.mark.performance
def test_repository_adapter_saves_history_and_latest_deterministically(
    tmp_path: Path,
) -> None:
    cases = build_benchmark_cases(
        "ci",
        tmp_path,
        fixture_profile=FixtureProfile(12, 1, 1, 1, 1),
        jsonl_event_count=1,
    )
    repository_case = cases[-1]

    results = run_benchmark(repository_case, profile="ci")

    assert repository_case.name == "repository_persistence"
    assert repository_case.input_counts == {
        "repositories": 3,
        "json_records": 6,
    }
    assert len({result.output_digest for result in results}) == 1
