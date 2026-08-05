"""Run registered deterministic benchmarks and emit a versioned report."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.benchmarks import (  # noqa: E402
    BenchmarkCase,
    BenchmarkLimitExceeded,
    BenchmarkLimits,
    render_report,
    run_benchmark,
)


PROFILES = ("ci", "large")
REGISTERED_BENCHMARKS: tuple[BenchmarkCase, ...] = ()


def main(
    argv: Sequence[str] | None = None,
    *,
    cases: Sequence[BenchmarkCase] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=PROFILES)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    try:
        if cases is None and not REGISTERED_BENCHMARKS:
            from tests.performance.benchmark_cases import (
                build_benchmark_cases,
            )

            with tempfile.TemporaryDirectory(
                prefix="test-assistant-benchmarks-"
            ) as temporary_directory:
                selected_cases = build_benchmark_cases(
                    arguments.profile,
                    Path(temporary_directory),
                )
                report = _run_cases(arguments.profile, selected_cases)
        else:
            selected_cases = tuple(
                REGISTERED_BENCHMARKS if cases is None else cases
            )
            report = _run_cases(arguments.profile, selected_cases)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if arguments.output is not None:
            _atomic_write(arguments.output, rendered)
        if arguments.json_output:
            sys.stdout.write(rendered)
        else:
            print(
                f"benchmark profile {arguments.profile}: "
                f"{len(selected_cases)} completed"
            )
    except (BenchmarkLimitExceeded, OSError, RuntimeError, ValueError) as error:
        print(f"benchmark error: {error}", file=sys.stderr)
        return 1
    return 0


def _run_cases(
    profile: str,
    cases: Sequence[BenchmarkCase],
) -> dict[str, object]:
    grouped_results = {
        case.name: run_benchmark(case, profile=profile)
        for case in cases
    }
    if len(grouped_results) != len(cases):
        raise ValueError("benchmark names must be unique")
    return render_report(
        profile=profile,
        benchmark_results=grouped_results,
        limits=BenchmarkLimits(),
    )


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
