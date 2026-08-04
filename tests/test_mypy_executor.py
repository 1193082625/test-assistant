"""mypy 只读适配器与稳定文本解析测试。"""

import subprocess

from core.analyzers.quality import parse_mypy_findings
from core.executors.mypy_executor import MypyExecutor
from core.models import QualityFindingKind, ToolState


def test_parse_mypy_separates_code_and_dependency_findings(tmp_path):
    output = "\n".join([
        "app.py:3:5: error: Incompatible return value type  [return-value]",
        "app.py:7:1: error: Library stubs not installed  [import-untyped]",
        "app.py:7:1: note: Hint: install types-demo",
    ])

    findings = parse_mypy_findings(output, project_root=tmp_path)

    assert findings[0].kind is QualityFindingKind.CODE
    assert findings[0].rule_code == "return-value"
    assert findings[1].kind is QualityFindingKind.DEPENDENCY
    assert findings[1].rule_code == "import-untyped"


def test_mypy_executor_uses_fixed_read_only_flags(tmp_path, monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "mypy 1.18.0\n", "")
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command, 1,
            "app.py:3:5: error: Wrong type  [return-value]\n", "",
        )

    monkeypatch.setattr(
        "core.executors.mypy_executor.subprocess.run", fake_run
    )

    result = MypyExecutor(tmp_path).execute()

    assert result.status.state is ToolState.COMPLETED
    assert result.status.version == "1.18.0"
    assert len(result.findings) == 1
    assert "--install-types" not in observed["command"]
    assert "--no-error-summary" in observed["command"]
    assert observed["kwargs"]["shell"] is False


def test_mypy_executor_reports_unavailable(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, "", "python: No module named mypy"
        )

    monkeypatch.setattr(
        "core.executors.mypy_executor.subprocess.run", fake_run
    )

    result = MypyExecutor(tmp_path).execute()

    assert result.status.state is ToolState.UNAVAILABLE
    assert result.status.reason == "mypy_not_installed"


def test_mypy_executor_rejects_unparseable_error_output(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "unexpected", "")

    monkeypatch.setattr(
        "core.executors.mypy_executor.subprocess.run", fake_run
    )

    result = MypyExecutor(tmp_path).execute()

    assert result.status.state is ToolState.FAILED
    assert result.status.reason == "invalid_mypy_output"

