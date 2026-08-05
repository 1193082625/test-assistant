"""Deterministic adapters for the v0.7.0 performance baselines."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.analyzers.framework import EXCLUDE_DIRS
from core.analyzers.git_history import read_symbol_history
from core.analyzers.impact import select_tests_for_changes
from core.analyzers.snapshot import take_snapshot
from core.analyzers.source import (
    analyze_python_symbols,
    index_python_project_tests,
)
from core.benchmarks import BenchmarkCase
from core.executors.base import ExecutionReport
from core.executors.pytest_executor import PytestExecutor
from core.models import AuditResult, AuditStatus, Diagnosis, TriageResult
from core.repositories import AuditRepository, DiagnosisRepository, TriageRepository
from tests.performance.fixture_factory import (
    CI_PROFILE,
    LARGE_PROFILE,
    FixtureProfile,
    GeneratedFixture,
    generate_fixture,
)


JSONL_EVENT_COUNT = 100_000
FIXED_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


def build_benchmark_cases(
    profile_name: str,
    workspace: Path,
    *,
    fixture_profile: FixtureProfile | None = None,
    jsonl_event_count: int = JSONL_EVENT_COUNT,
) -> tuple[BenchmarkCase, ...]:
    """Build the five measured paths without timing input generation."""

    if profile_name not in {"ci", "large"}:
        raise ValueError(f"unknown benchmark profile: {profile_name}")
    profile = fixture_profile or (
        CI_PROFILE if profile_name == "ci" else LARGE_PROFILE
    )
    fixture = generate_fixture(workspace / "fixture", profile)
    jsonl_path = workspace / "pytest-progress.jsonl"
    _write_jsonl(jsonl_path, jsonl_event_count)

    return (
        _snapshot_case(fixture, profile),
        _impact_case(fixture, profile),
        _git_history_case(fixture),
        _jsonl_case(jsonl_path, jsonl_event_count),
        _repository_case(workspace / "repositories"),
    )


def _snapshot_case(
    fixture: GeneratedFixture,
    profile: FixtureProfile,
) -> BenchmarkCase:
    expected_files = profile.module_count + profile.test_count + 3
    expected_symbols = (
        profile.module_count * profile.functions_per_module
        + profile.test_count
    )

    def operation() -> str:
        snapshots, skipped = take_snapshot(
            str(fixture.root),
            [*EXCLUDE_DIRS, ".fixture-history"],
        )
        symbol_count = sum(len(snapshot.symbols or ()) for snapshot in snapshots)
        if len(snapshots) != expected_files or symbol_count != expected_symbols:
            raise RuntimeError("snapshot benchmark processed unexpected counts")
        return _digest(
            {
                "files": [
                    [
                        snapshot.path,
                        snapshot.hash,
                        len(snapshot.symbols or ()),
                    ]
                    for snapshot in snapshots
                ],
                "skipped": skipped,
                "symbol_count": symbol_count,
            }
        )

    return BenchmarkCase(
        name="snapshot_and_symbols",
        input_counts={
            "files": expected_files,
            "python_symbols": expected_symbols,
        },
        operation=operation,
    )


def _impact_case(
    fixture: GeneratedFixture,
    profile: FixtureProfile,
) -> BenchmarkCase:
    source_symbols = []
    for source_path in fixture.source_files:
        source_symbols.extend(
            analyze_python_symbols(
                file_path=str(source_path),
                module_name=(
                    "large_fixture."
                    f"{source_path.stem}"
                ),
            )
        )
    changed_files = {
        "modified": [
            path.relative_to(fixture.root).as_posix()
            for path in fixture.source_files
        ]
    }

    def operation() -> str:
        index = index_python_project_tests(
            project_root=str(fixture.root),
            source_symbols=source_symbols,
        )
        selection = select_tests_for_changes(
            project_root=str(fixture.root),
            language="python",
            changed_files=changed_files,
        )
        if len(index.entries) != profile.test_count:
            raise RuntimeError("test index benchmark skipped mappings")
        if len(selection.test_files) != profile.test_count:
            raise RuntimeError("test selection benchmark skipped tests")
        return _digest(
            {
                "entries": [
                    [
                        entry.source_qualified_name,
                        entry.test_qualified_name,
                        entry.test_file_path,
                        entry.test_line,
                    ]
                    for entry in index.entries
                ],
                "selection_mode": selection.mode.value,
                "selected_tests": selection.test_files,
            }
        )

    return BenchmarkCase(
        name="test_index_and_selection",
        input_counts={
            "source_symbols": len(source_symbols),
            "tests": profile.test_count,
        },
        operation=operation,
    )


def _git_history_case(fixture: GeneratedFixture) -> BenchmarkCase:
    source_path = fixture.source_files[0].relative_to(fixture.root).as_posix()

    def operation() -> str:
        history = read_symbol_history(
            project_root=fixture.root,
            symbol="function_000",
            source_paths=(source_path,),
        )
        if not history.available or not history.was_added:
            raise RuntimeError("Git history benchmark found no addition")
        if history.was_deleted or len(history.commits) != 1:
            raise RuntimeError("Git history benchmark returned unexpected history")
        return _digest(
            {
                "available": history.available,
                "was_added": history.was_added,
                "was_deleted": history.was_deleted,
                "commits": history.commits,
            }
        )

    return BenchmarkCase(
        name="git_symbol_history",
        input_counts={"paths": 1, "fixture_commits": len(fixture.commit_ids)},
        operation=operation,
    )


def _jsonl_case(path: Path, event_count: int) -> BenchmarkCase:
    def operation() -> str:
        observed_count = 0
        index_total = 0

        def observe(payload: dict[str, object]) -> None:
            nonlocal observed_count, index_total
            observed_count += 1
            index_total += int(payload["index"])

        offset = PytestExecutor._emit_progress_events(path, 0, observe)
        if observed_count != event_count or offset != path.stat().st_size:
            raise RuntimeError("JSONL benchmark did not parse every event")
        return _digest(
            {
                "events": observed_count,
                "index_total": index_total,
                "offset": offset,
            }
        )

    return BenchmarkCase(
        name="pytest_jsonl_parser",
        input_counts={"events": event_count},
        operation=operation,
    )


def _repository_case(root: Path) -> BenchmarkCase:
    invocation = 0

    def operation() -> str:
        nonlocal invocation
        invocation += 1
        run_root = root / f"run-{invocation:04d}"

        audit = AuditRepository(run_root / "audit")
        audit.save(
            AuditResult(
                run_id="audit-001",
                status=AuditStatus.PASSED,
                command=("test-assistant", "audit"),
                coverage=None,
                symbols=(),
                findings=(),
                tools=(),
                source_digest="sha256:fixture",
            ),
            created_at=FIXED_TIME,
        )

        report = ExecutionReport(exit_code=0)
        triage = TriageRepository(run_root / "triage")
        triage.save(
            result=TriageResult(
                run_id="triage-001",
                report=report,
                clusters=(),
                diagnoses=(),
            ),
            diagnosis_references=(),
            reproduction_commands={},
            created_at=FIXED_TIME,
        )

        diagnosis = DiagnosisRepository(run_root / "diagnosis")
        diagnosis.save(
            diagnosis=Diagnosis(summary="deterministic fixture"),
            execution_reports=(report,),
            reproduction_command="python -m pytest -q",
            created_at=FIXED_TIME,
        )

        records = {
            "audit": audit.load_latest(),
            "triage": triage.load_latest(),
            "diagnosis": diagnosis.load_latest(),
        }
        record_files = sorted(run_root.rglob("*.json"))
        if len(record_files) != 6 or any(value is None for value in records.values()):
            raise RuntimeError("repository benchmark did not save history and latest")
        return _digest(records)

    return BenchmarkCase(
        name="repository_persistence",
        input_counts={"repositories": 3, "json_records": 6},
        operation=operation,
    )


def _write_jsonl(path: Path, event_count: int) -> None:
    if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 1:
        raise ValueError("jsonl_event_count must be a positive integer")
    with path.open("w", encoding="utf-8") as stream:
        for index in range(event_count):
            stream.write(
                json.dumps(
                    {"event": "test_complete", "index": index},
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
