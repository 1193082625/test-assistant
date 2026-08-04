"""coverage 子进程适配器的安全边界测试。"""

import json
import subprocess

import pytest

from core.executors.coverage_executor import CoverageExecutor
from core.models import ToolState


def _coverage_output_path(command: list[str]) -> str:
    argument = next(
        item for item in command if item.startswith("--cov-report=json:")
    )
    return argument.removeprefix("--cov-report=json:")


def _write_coverage_payload(command: list[str]) -> str:
    path = _coverage_output_path(command)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "meta": {"version": "7.10.0"},
                "files": {},
                "totals": {
                    "covered_lines": 1,
                    "num_statements": 1,
                    "covered_branches": 0,
                    "num_branches": 0,
                },
            },
            stream,
        )
    return path


def test_execute_uses_argument_array_and_parses_temporary_json(
    tmp_path,
    monkeypatch,
):
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        observed["coverage_path"] = _write_coverage_payload(command)
        return subprocess.CompletedProcess(command, 0, "1 passed", "")

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(
        source_path="app",
        test_path="tests/test_service.py",
        timeout=30,
    )

    assert result.status.state is ToolState.COMPLETED
    assert result.status.version == "7.10.0"
    assert result.coverage_data["totals"]["covered_lines"] == 1
    assert observed["command"][:3] == [
        result.command[0],
        "-m",
        "pytest",
    ]
    assert "--cov=app" in observed["command"]
    assert observed["kwargs"]["shell"] is False
    assert observed["kwargs"]["cwd"] == str(tmp_path.resolve())
    assert not __import__("pathlib").Path(observed["coverage_path"]).exists()


def test_execute_keeps_coverage_when_tests_fail(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        _write_coverage_payload(command)
        return subprocess.CompletedProcess(command, 1, "1 failed", "")

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(source_path="app")

    assert result.status.state is ToolState.COMPLETED
    assert result.report.error_type == "test_failure"
    assert result.coverage_data is not None


def test_execute_supports_exact_test_node(tmp_path, monkeypatch):
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        _write_coverage_payload(command)
        return subprocess.CompletedProcess(command, 0, "1 passed", "")

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    CoverageExecutor(tmp_path).execute(
        source_path="app",
        test_node="tests/test_service.py::test_case",
    )

    assert "tests/test_service.py::test_case" in observed["command"]


def test_execute_reports_startup_error(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise FileNotFoundError("python executable not found")

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(source_path="app")

    assert result.status.state is ToolState.FAILED
    assert result.status.reason == "startup_error"
    assert result.report.error_type == "startup_error"


def test_execute_reports_missing_pytest_cov(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            4,
            "",
            "pytest: error: unrecognized arguments: --cov=app",
        )

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(source_path="app")

    assert result.status.state is ToolState.UNAVAILABLE
    assert result.status.reason == "pytest_cov_not_installed"
    assert result.coverage_data is None


def test_execute_reports_corrupt_coverage_json(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        path = _coverage_output_path(command)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("{broken")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(source_path="app")

    assert result.status.state is ToolState.FAILED
    assert result.status.reason == "invalid_coverage_json"
    assert result.coverage_data is None


def test_execute_reports_timeout(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(
        source_path="app",
        timeout=1,
    )

    assert result.status.state is ToolState.TIMED_OUT
    assert result.report.timed_out is True
    assert result.coverage_data is None


@pytest.mark.parametrize(
    "path",
    ["/outside/app", "../outside", "app/../../outside"],
)
def test_execute_rejects_source_path_outside_project(tmp_path, path):
    with pytest.raises(ValueError, match="source_path 必须位于项目内"):
        CoverageExecutor(tmp_path).execute(source_path=path)


def test_execute_rejects_oversized_coverage_json(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        path = _coverage_output_path(command)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("x" * (5_000_001))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "core.executors.coverage_executor.subprocess.run",
        fake_run,
    )

    result = CoverageExecutor(tmp_path).execute(source_path="app")

    assert result.status.state is ToolState.FAILED
    assert result.status.reason == "coverage_json_too_large"
