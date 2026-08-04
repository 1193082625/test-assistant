"""Ruff 只读子进程适配器测试。"""

import json
import subprocess

from core.executors.ruff_executor import RuffExecutor
from core.models import ToolState


def test_ruff_executor_uses_read_only_json_command(tmp_path, monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "ruff 0.12.0\n", "")
        observed["command"] = command
        observed["kwargs"] = kwargs
        payload = [{
            "code": "F401",
            "message": "unused import",
            "filename": str(tmp_path / "app.py"),
            "location": {"row": 1, "column": 1},
            "fix": None,
        }]
        return subprocess.CompletedProcess(command, 1, json.dumps(payload), "")

    monkeypatch.setattr(
        "core.executors.ruff_executor.subprocess.run", fake_run
    )

    result = RuffExecutor(tmp_path).execute()

    assert result.status.state is ToolState.COMPLETED
    assert result.status.version == "0.12.0"
    assert len(result.findings) == 1
    assert "--fix" not in observed["command"]
    assert observed["command"][-4:] == ["check", "--output-format", "json", "."]
    assert observed["kwargs"]["shell"] is False


def test_ruff_executor_reports_unavailable(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, "", "python: No module named ruff"
        )

    monkeypatch.setattr(
        "core.executors.ruff_executor.subprocess.run", fake_run
    )

    result = RuffExecutor(tmp_path).execute()

    assert result.status.state is ToolState.UNAVAILABLE
    assert result.status.reason == "ruff_not_installed"


def test_ruff_executor_reports_invalid_json(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "{broken", "")

    monkeypatch.setattr(
        "core.executors.ruff_executor.subprocess.run", fake_run
    )

    result = RuffExecutor(tmp_path).execute()

    assert result.status.state is ToolState.FAILED
    assert result.status.reason == "invalid_ruff_json"
