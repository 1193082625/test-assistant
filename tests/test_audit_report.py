"""Audit Markdown 报告与 CLI 导出测试。"""

from click.testing import CliRunner

from cli.main import cli
from core.models import (
    AuditResult, AuditStatus, CoverageSummary, QualityFinding,
    QualityFindingKind, ToolState, ToolStatus,
)
from core.reporters import render_audit_markdown
from core.repositories import AuditRepository


def _record(tmp_path):
    repository = AuditRepository(tmp_path)
    repository.save(AuditResult(
        run_id="audit-001", status=AuditStatus.PASSED,
        command=("test-assistant", "audit"),
        coverage=CoverageSummary(8, 10, 2, 4),
        symbols=(),
        findings=(QualityFinding(
            tool="ruff", kind=QualityFindingKind.CODE,
            rule_code="F401", message="unused import",
            source_path="app.py", line=1, column=1, fix_available=True,
        ),),
        tools=(ToolStatus(
            tool="ruff", state=ToolState.COMPLETED,
            version="1", reason=None,
        ),),
        source_digest="sha256:abc",
    ))
    return repository.load_latest()


def test_render_audit_markdown_distinguishes_coverage_and_quality(tmp_path):
    markdown = render_audit_markdown(_record(tmp_path))

    assert "## 覆盖率" in markdown
    assert "语句：8 / 10" in markdown
    assert "## 静态质量 findings" in markdown
    assert "F401" in markdown


def test_report_command_exports_latest_audit(tmp_path):
    _record(tmp_path)

    result = CliRunner().invoke(cli, ["report", "--path", str(tmp_path), "--audit"])

    assert result.exit_code == 0, result.output
    output = tmp_path / ".autotest/reports/latest-audit.md"
    assert output.is_file()
    assert "Test Assistant Audit 报告" in output.read_text(encoding="utf-8")
