"""Audit adapter 编排、降级与显式门禁测试。"""

from types import SimpleNamespace

from core.executors.base import ExecutionReport
from core.models import (
    AuditStatus,
    AuditThresholds,
    QualityFinding,
    QualityFindingKind,
    ToolState,
    ToolStatus,
)
from core.workflows.audit import run_audit


def _coverage_payload(covered=1, total=2):
    return {
        "meta": {"version": "7"},
        "files": {},
        "totals": {
            "covered_lines": covered,
            "num_statements": total,
            "covered_branches": 0,
            "num_branches": 0,
        },
    }


class FakeCoverage:
    def __init__(self, *, state=ToolState.COMPLETED, test_failure=False):
        self.state = state
        self.test_failure = test_failure

    def execute(self, **kwargs):
        return SimpleNamespace(
            status=ToolStatus(
                tool="coverage", state=self.state, version="7",
                reason=None if self.state is ToolState.COMPLETED else "missing",
            ),
            coverage_data=(
                _coverage_payload() if self.state is ToolState.COMPLETED else None
            ),
            report=ExecutionReport(
                exit_code=1 if self.test_failure else 0,
                error_type="test_failure" if self.test_failure else None,
            ),
        )


class FakeQuality:
    def __init__(self, tool, *, state=ToolState.COMPLETED, findings=()):
        self.tool = tool
        self.state = state
        self.findings = findings

    def execute(self, **kwargs):
        return SimpleNamespace(
            status=ToolStatus(
                tool=self.tool, state=self.state, version="1",
                reason=None if self.state is ToolState.COMPLETED else "missing",
            ),
            findings=self.findings,
            report=ExecutionReport(),
        )


def _run(tmp_path, **overrides):
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    values = {
        "project_root": tmp_path,
        "run_id": "audit-001",
        "source_path": ".",
        "coverage_executor": FakeCoverage(),
        "ruff_executor": FakeQuality("ruff"),
        "mypy_executor": FakeQuality("mypy"),
    }
    values.update(overrides)
    return run_audit(**values)


def test_no_explicit_threshold_only_reports_low_coverage(tmp_path):
    result = _run(tmp_path)

    assert result.status is AuditStatus.PASSED
    assert result.coverage.statement_rate == 0.5


def test_explicit_threshold_failure_is_stable(tmp_path):
    result = _run(
        tmp_path,
        thresholds=AuditThresholds(statement_rate=0.8),
    )

    assert result.status is AuditStatus.THRESHOLD_FAILED


def test_test_failure_keeps_coverage_but_has_distinct_status(tmp_path):
    result = _run(
        tmp_path,
        coverage_executor=FakeCoverage(test_failure=True),
    )

    assert result.status is AuditStatus.TESTS_FAILED
    assert result.coverage is not None


def test_one_unavailable_adapter_produces_partial_result(tmp_path):
    result = _run(
        tmp_path,
        mypy_executor=FakeQuality("mypy", state=ToolState.UNAVAILABLE),
    )

    assert result.status is AuditStatus.PARTIAL
    assert any(tool.state is ToolState.COMPLETED for tool in result.tools)


def test_test_failure_is_not_hidden_by_another_adapter_degradation(tmp_path):
    result = _run(
        tmp_path,
        coverage_executor=FakeCoverage(test_failure=True),
        mypy_executor=FakeQuality("mypy", state=ToolState.UNAVAILABLE),
    )

    assert result.status is AuditStatus.TESTS_FAILED
    assert any(tool.state is ToolState.UNAVAILABLE for tool in result.tools)


def test_all_enabled_adapters_unavailable_is_infra_error(tmp_path):
    result = _run(
        tmp_path,
        coverage_executor=FakeCoverage(state=ToolState.UNAVAILABLE),
        ruff_executor=FakeQuality("ruff", state=ToolState.UNAVAILABLE),
        mypy_executor=FakeQuality("mypy", state=ToolState.UNAVAILABLE),
    )

    assert result.status is AuditStatus.INFRA_ERROR


def test_quality_threshold_counts_code_findings(tmp_path):
    finding = QualityFinding(
        tool="mypy", kind=QualityFindingKind.CODE,
        rule_code="return-value", message="wrong type",
        source_path="app.py", line=1, column=1, fix_available=False,
    )
    result = _run(
        tmp_path,
        mypy_executor=FakeQuality("mypy", findings=(finding,)),
        thresholds=AuditThresholds(max_mypy_errors=0),
    )

    assert result.status is AuditStatus.THRESHOLD_FAILED
