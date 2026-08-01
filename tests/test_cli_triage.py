from click.testing import CliRunner

import cli.commands.triage as triage_module
from cli.main import cli
from core.executors.base import ExecutionReport, PytestSuiteResult
from core.models import PytestIssue, TriagePhase
from core.repositories import TriageRepository


def _write_project(tmp_path, body: str) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text(body, encoding="utf-8")


def test_triage_default_suite_passes_and_saves_record(tmp_path):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert "pytest 摘要: 1 passed" in result.output
    assert "失败簇: 0" in result.output
    assert "Triage 记录:" in result.output
    assert TriageRepository(tmp_path).load_latest() is not None


def test_triage_empty_suite_is_unresolved(tmp_path):
    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 1, result.output
    assert "未收集到可执行测试" in result.output


def test_triage_test_path_reports_cluster_and_evidence(tmp_path):
    _write_project(tmp_path, "def test_bad():\n    assert 1 == 2\n")

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_demo.py",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "失败簇: 1" in result.output
    assert "inconclusive" in result.output
    assert "置信度: low" in result.output
    assert "代表 node: tests/test_demo.py::test_bad" in result.output
    assert "证据:" in result.output
    assert "复现命令: python -m pytest" in result.output


def test_triage_exact_node_only_runs_selected_test(tmp_path):
    _write_project(
        tmp_path,
        (
            "def test_first():\n    assert False\n\n"
            "def test_second():\n    assert False\n"
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-node",
            "tests/test_demo.py::test_second",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "test_second" in result.output
    assert "test_first" not in result.output


def test_triage_passes_structured_max_failures_to_executor(
    tmp_path,
    monkeypatch,
):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")
    observed = {}

    def fake_execute_suite(self, test_path=None, timeout=120, max_failures=None):
        observed["test_path"] = test_path
        observed["max_failures"] = max_failures
        return PytestSuiteResult(report=ExecutionReport(exit_code=0))

    monkeypatch.setattr(
        triage_module.PytestExecutor,
        "execute_suite",
        fake_execute_suite,
    )

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_demo.py",
            "--max-failures",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert observed == {
        "test_path": "tests/test_demo.py",
        "max_failures": 2,
    }


def test_triage_rejects_mutually_exclusive_scope_options(tmp_path):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_demo.py",
            "--test-node",
            "tests/test_demo.py::test_ok",
        ],
    )

    assert result.exit_code == 2
    assert "不能同时使用" in result.output


def test_triage_rejects_missing_or_outside_paths(tmp_path):
    missing_project = CliRunner().invoke(
        cli,
        ["triage", "--path", str(tmp_path / "missing")],
    )
    outside_test = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "../outside.py",
        ],
    )

    assert missing_project.exit_code == 2
    assert outside_test.exit_code == 2
    assert "必须位于目标项目内" in outside_test.output


def test_triage_runner_error_uses_exit_code_two(tmp_path, monkeypatch):
    issue = PytestIssue(
        phase=TriagePhase.EXECUTION,
        stage="startup",
        outcome="error",
        message="python not found",
        exception_type="FileNotFoundError",
    )

    def fake_execute_suite(self, test_path=None, timeout=120, max_failures=None):
        return PytestSuiteResult(
            report=ExecutionReport(
                exit_code=None,
                error_type="startup_error",
                stderr="python not found",
            ),
            issues=(issue,),
        )

    monkeypatch.setattr(
        triage_module.PytestExecutor,
        "execute_suite",
        fake_execute_suite,
    )

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 2, result.output
    assert "infra_defect" in result.output


def test_triage_persistence_error_uses_exit_code_two(tmp_path, monkeypatch):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")

    def fail_save(self, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(triage_module.TriageRepository, "save", fail_save)

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 2
    assert "disk full" in result.output
