"""pytest 结构化事件采集的真实子进程契约测试。"""

import subprocess

from core.executors.pytest_executor import PytestExecutor
from core.models import TriagePhase


def _write(path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_execute_suite_captures_pass_failure_skip_and_warning(tmp_path):
    _write(tmp_path / "test_sample.py", """
import warnings
import pytest

def test_passes():
    warnings.warn("old api", DeprecationWarning)

def test_fails():
    assert 1 == 2

@pytest.mark.skip(reason="later")
def test_skips():
    pass
""")

    result = PytestExecutor(cwd=str(tmp_path)).execute_suite()

    assert result.report.exit_code == 1
    assert result.report.error_type == "test_failure"
    execution_outcomes = {
        issue.outcome
        for issue in result.issues
        if issue.phase is TriagePhase.EXECUTION
    }
    assert {"passed", "failed", "skipped"} <= execution_outcomes
    assert {
        test.status for test in result.report.test_results
    } == {"passed", "failed", "skipped"}
    warning = next(
        issue for issue in result.issues
        if issue.phase is TriagePhase.WARNING
    )
    assert warning.outcome == "warning"
    assert warning.exception_type == "DeprecationWarning"
    assert warning.message == "old api"


def test_execute_suite_captures_setup_error(tmp_path):
    _write(tmp_path / "test_setup.py", """
import pytest

@pytest.fixture
def broken():
    raise RuntimeError("setup exploded")

def test_uses_fixture(broken):
    pass
""")

    result = PytestExecutor(cwd=str(tmp_path)).execute_suite()

    issue = next(issue for issue in result.issues if issue.outcome == "error")
    assert issue.phase is TriagePhase.EXECUTION
    assert issue.stage == "setup"
    assert issue.exception_type == "RuntimeError"
    assert "setup exploded" in issue.message


def test_execute_suite_captures_collection_error(tmp_path):
    _write(tmp_path / "test_invalid.py", "def test_broken(:\n")

    result = PytestExecutor(cwd=str(tmp_path)).execute_suite()

    issue = next(
        issue for issue in result.issues
        if issue.phase is TriagePhase.COLLECTION
    )
    assert issue.outcome == "error"
    assert issue.stage == "collect"
    assert "SyntaxError" in issue.message


def test_execute_suite_reports_no_tests_collected(tmp_path):
    result = PytestExecutor(cwd=str(tmp_path)).execute_suite()

    assert result.report.exit_code == 5
    assert result.report.error_type == "no_tests_collected"
    assert len(result.issues) == 1
    assert result.issues[0].outcome == "no_tests_collected"
    assert result.issues[0].phase is TriagePhase.COLLECTION


def test_execute_suite_reports_timeout(monkeypatch):
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0], timeout=kwargs["timeout"], output=b"partial"
        )

    monkeypatch.setattr(
        "core.executors.pytest_executor.subprocess.run",
        timeout_run,
    )

    result = PytestExecutor(cwd="/demo").execute_suite(timeout=0.01)

    assert result.report.timed_out is True
    assert result.report.error_type == "timeout"
    assert result.report.stdout == "partial"
    assert result.issues[0].outcome == "timeout"


def test_execute_suite_reports_startup_error(monkeypatch):
    def fail_run(*args, **kwargs):
        raise FileNotFoundError("python executable not found")

    monkeypatch.setattr(
        "core.executors.pytest_executor.subprocess.run",
        fail_run,
    )

    result = PytestExecutor(cwd="/demo").execute_suite()

    assert result.report.exit_code is None
    assert result.report.error_type == "startup_error"
    assert result.issues[0].stage == "startup"
    assert result.issues[0].exception_type == "FileNotFoundError"


def test_execute_suite_reports_invalid_plugin_payload(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        output_index = args.index("--test-assistant-json") + 1
        _write(tmp_path / "observed.txt", args[output_index])
        return subprocess.CompletedProcess(args, 0, "1 passed", "")

    monkeypatch.setattr(
        "core.executors.pytest_executor.subprocess.run",
        fake_run,
    )

    result = PytestExecutor(cwd=str(tmp_path)).execute_suite()

    assert result.report.error_type == "parse_error"
    assert "结构化结果解析失败" in result.report.stderr


def test_execute_suite_limits_process_output(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        output_path = args[args.index("--test-assistant-json") + 1]
        with open(output_path, "w", encoding="utf-8") as stream:
            stream.write('{"events": []}')
        return subprocess.CompletedProcess(
            args, 0, "x" * 25_000, "y" * 25_000
        )

    monkeypatch.setattr(
        "core.executors.pytest_executor.subprocess.run",
        fake_run,
    )

    result = PytestExecutor(cwd=str(tmp_path)).execute_suite()

    assert len(result.report.stdout) < 21_000
    assert "omitted 5000 characters" in result.report.stdout
    assert len(result.report.stderr) < 21_000


def test_execute_suite_emits_exact_incremental_progress(tmp_path):
    _write(tmp_path / "test_progress.py", """
import pytest

def test_first():
    assert True

@pytest.mark.skip(reason="later")
def test_second():
    pass

def test_third():
    assert True
""")
    events = []

    result = PytestExecutor(cwd=str(tmp_path)).execute_suite(
        progress_callback=events.append,
    )

    assert result.report.exit_code == 0
    collection = next(event for event in events if event["event"] == "collection")
    assert collection["total"] == 3
    completions = [
        event for event in events if event["event"] == "test_complete"
    ]
    assert [event["completed"] for event in completions] == [1, 2, 3]
    assert completions[-1]["node_id"].endswith("::test_third")
