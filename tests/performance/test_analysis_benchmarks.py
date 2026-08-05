"""Correctness gates for analysis benchmark adapters."""

from pathlib import Path

import pytest

from core.benchmarks import run_benchmark
from tests.performance.benchmark_cases import build_benchmark_cases
from tests.performance.fixture_factory import FixtureProfile


TINY_PROFILE = FixtureProfile(11, 3, 2, 4, 2)


@pytest.mark.performance
def test_analysis_adapters_measure_stable_complete_outputs(tmp_path: Path) -> None:
    cases = build_benchmark_cases(
        "ci",
        tmp_path,
        fixture_profile=TINY_PROFILE,
        jsonl_event_count=20,
    )
    analysis_cases = cases[:4]

    results = {
        case.name: run_benchmark(case, profile="ci")
        for case in analysis_cases
    }

    assert tuple(results) == (
        "snapshot_and_symbols",
        "test_index_and_selection",
        "git_symbol_history",
        "pytest_jsonl_parser",
    )
    assert all(len(samples) == 3 for samples in results.values())
    assert all(
        len({sample.output_digest for sample in samples}) == 1
        for samples in results.values()
    )
