"""audit CLI 参数、输出、持久化与退出码测试。"""

from dataclasses import replace

from click.testing import CliRunner

import cli.commands.audit as audit_module
from cli.main import cli
from core.models import (
    AuditResult,
    AuditStatus,
    CoverageSummary,
    ToolState,
    ToolStatus,
)
from core.repositories import AuditRepository


def _result(status=AuditStatus.PASSED):
    return AuditResult(
        run_id="audit-001", status=status,
        command=("test-assistant", "audit", "--path", "."),
        coverage=CoverageSummary(8, 10, 2, 4),
        symbols=(), findings=(),
        tools=(ToolStatus(
            tool="coverage", state=ToolState.COMPLETED,
            version="7", reason=None,
        ),),
        source_digest="sha256:abc",
    )


def test_audit_cli_reports_and_saves_result(tmp_path, monkeypatch):
    observed = {}

    def fake_run_audit(**kwargs):
        observed.update(kwargs)
        return replace(_result(), run_id=kwargs["run_id"])

    monkeypatch.setattr(audit_module, "run_audit", fake_run_audit)

    result = CliRunner().invoke(cli, ["audit", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Audit 状态: passed" in result.output
    assert "语句 8/10 (80.0%)" in result.output
    assert "Audit 记录:" in result.output
    assert observed["coverage_enabled"] is True
    assert observed["quality_enabled"] is True
    assert AuditRepository(tmp_path).load_latest() is not None


def test_audit_cli_passes_explicit_thresholds(tmp_path, monkeypatch):
    observed = {}

    def fake_run_audit(**kwargs):
        observed.update(kwargs)
        return replace(
            _result(AuditStatus.THRESHOLD_FAILED),
            run_id=kwargs["run_id"], thresholds=kwargs["thresholds"],
        )

    monkeypatch.setattr(audit_module, "run_audit", fake_run_audit)
    result = CliRunner().invoke(cli, [
        "audit", "--path", str(tmp_path),
        "--statement-threshold", "0.9",
    ])

    assert result.exit_code == 1
    assert observed["thresholds"].statement_rate == 0.9


def test_audit_cli_infra_error_uses_exit_code_two(tmp_path, monkeypatch):
    monkeypatch.setattr(
        audit_module, "run_audit",
        lambda **kwargs: replace(
            _result(AuditStatus.INFRA_ERROR), run_id=kwargs["run_id"]
        ),
    )

    result = CliRunner().invoke(cli, ["audit", "--path", str(tmp_path)])

    assert result.exit_code == 2


def test_audit_cli_rejects_all_adapters_disabled(tmp_path):
    result = CliRunner().invoke(cli, [
        "audit", "--path", str(tmp_path),
        "--no-coverage", "--no-quality",
    ])

    assert result.exit_code == 2
    assert "至少启用" in result.output


def test_audit_cli_passes_exact_test_node(tmp_path, monkeypatch):
    observed = {}
    monkeypatch.setattr(
        audit_module, "run_audit",
        lambda **kwargs: observed.update(kwargs) or replace(
            _result(), run_id=kwargs["run_id"]
        ),
    )

    result = CliRunner().invoke(cli, [
        "audit", "--path", str(tmp_path),
        "--test-node", "tests/test_app.py::test_run",
    ])

    assert result.exit_code == 0, result.output
    assert observed["test_path"] is None
    assert observed["test_node"] == "tests/test_app.py::test_run"


def test_audit_cli_rejects_conflicting_test_ranges(tmp_path):
    result = CliRunner().invoke(cli, [
        "audit", "--path", str(tmp_path),
        "--test-path", "tests", "--test-node", "tests/test_app.py::test_run",
    ])

    assert result.exit_code == 2
    assert "不能同时使用" in result.output


def test_audit_cli_changed_only_passes_explicit_evidence(tmp_path, monkeypatch):
    from core.analyzers.change_evidence import ChangeEvidence

    observed = {}
    monkeypatch.setattr(
        audit_module, "collect_change_evidence",
        lambda root: ChangeEvidence("snapshot", ("app.py",), ("app.run",)),
    )
    monkeypatch.setattr(
        audit_module, "run_audit",
        lambda **kwargs: observed.update(kwargs) or replace(
            _result(), run_id=kwargs["run_id"]
        ),
    )
    result = CliRunner().invoke(cli, [
        "audit", "--path", str(tmp_path), "--changed-only",
    ])

    assert result.exit_code == 0, result.output
    assert "变更证据: snapshot" in result.output
    assert observed["changed_paths"] == ("app.py",)
    assert observed["changed_qualified_names"] == ("app.run",)
