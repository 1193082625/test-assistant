import pytest

import core.models as models
from core.models.audit import (
    AuditResult,
    AuditStatus,
    AuditThresholds,
    CoverageState,
    CoverageSummary,
    QualityFinding,
    QualityFindingKind,
    SymbolCoverage,
    ToolState,
    ToolStatus,
)


def make_symbol():
    summary = CoverageSummary(
        statements_covered=7,
        statements_total=10,
        branches_covered=2,
        branches_total=4,
    )

    return {
        "source_path": "app/service.py",
        "qualified_name": "UserService.create_user",
        "kind": "method",
        "start_line": 10,
        "end_line": 25,
        "summary": summary,
        "missing_lines": (18, 21, 22),
        "missing_branches": ((15, 18), (15, 21)),
    }

def test_coverage_summary_preserves_statement_and_branch_counts():
    summary = CoverageSummary(
        statements_covered=75,
        statements_total=100,
        branches_covered=30,
        branches_total=50,
    )

    assert summary.statements_covered == 75
    assert summary.statements_total == 100
    assert summary.branches_covered == 30
    assert summary.branches_total == 50


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("statements_covered", -1),
        ("statements_total", -1),
        ("branches_covered", -1),
        ("branches_total", -1),
    ],
)
def test_coverage_summary_rejects_negative_counts(field, value):
    values = {
        "statements_covered": 75,
        "statements_total": 100,
        "branches_covered": 30,
        "branches_total": 50,
    }
    values[field] = value

    with pytest.raises(ValueError, match="不能为负数"):
        CoverageSummary(**values)


@pytest.mark.parametrize(
    "values",
    [
        {
            "statements_covered": 101,
            "statements_total": 100,
            "branches_covered": 30,
            "branches_total": 50,
        },
        {
            "statements_covered": 75,
            "statements_total": 100,
            "branches_covered": 51,
            "branches_total": 50,
        },
    ],
)
def test_coverage_summary_rejects_covered_greater_than_total(values):
    with pytest.raises(ValueError, match="不能大于总数"):
        CoverageSummary(**values)

def test_coverage_summary_calculates_statement_and_branch_rates():
    summary = CoverageSummary(
        statements_covered=75,
        statements_total=100,
        branches_covered=30,
        branches_total=50,
    )
    assert summary.statement_rate == pytest.approx(0.75)
    assert summary.branch_rate == pytest.approx(0.6)

def test_coverage_summary_returns_none_when_total_is_zero():
    summary = CoverageSummary(
        statements_covered=0,
        statements_total=0,
        branches_covered=0,
        branches_total=0,
    )

    assert summary.statement_rate is None
    assert summary.branch_rate is None

def test_symbol_coverage_preserves_identity_location_and_gaps():
    summary = CoverageSummary(
        statements_covered=7,
        statements_total=10,
        branches_covered=2,
        branches_total=4,
    )

    symbol = SymbolCoverage(
        source_path="app/service.py",
        qualified_name="UserService.create_user",
        kind="method",
        start_line=10,
        end_line=25,
        summary=summary,
        missing_lines=(18,21,22),
        missing_branches=((15,18), (15,21)),
    )
    assert symbol.source_path == "app/service.py"
    assert symbol.qualified_name == "UserService.create_user"
    assert symbol.kind == "method"
    assert symbol.start_line == 10
    assert symbol.end_line == 25
    assert symbol.summary is summary
    assert symbol.missing_lines == (18, 21, 22)
    assert symbol.missing_branches == ((15, 18), (15, 21))

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_path", "", "source_path 不能为空"),
        ("qualified_name", "", "qualified_name 不能为空"),
        ("start_line", 0, "start_line 必须大于等于 1"),
        ("end_line", 9, "end_line 不能小于 start_line"),
    ],
)
def test_symbol_coverage_rejects_invalid_identity_and_location(
    field, value, message
):
    values = make_symbol()
    values[field] = value
    with pytest.raises(ValueError, match=message):
        SymbolCoverage(**values)

@pytest.mark.parametrize("missing_line", [9, 26])
def test_symbol_coverage_rejects_missing_lines_outside_symbol(missing_line):
    values = make_symbol()
    values["missing_lines"] = (missing_line,)
    values["missing_branches"] = ()

    with pytest.raises(
        ValueError,
        match="missing_lines 必须位于符号范围内"
    ):
        SymbolCoverage(**values)

@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (ToolState.COMPLETED, None),
        (ToolState.UNAVAILABLE, "executable_not_found"),
        (ToolState.TIMED_OUT, "execution_timeout"),
        (ToolState.FAILED, "invalid_output"),
        (ToolState.SKIPPED, None),
    ],
)
def test_tool_status_preserves_stable_state(state, reason):
    status = ToolStatus(
        tool="ruff",
        state=state,
        version="0.12.0",
        reason=reason,
    )

    assert status.tool == "ruff"
    assert status.state is state
    assert status.version == "0.12.0"
    assert status.reason == reason

def test_tool_status_has_stable_serialized_values():
    assert ToolState.COMPLETED.value == "completed"
    assert ToolState.UNAVAILABLE.value == "unavailable"
    assert ToolState.TIMED_OUT.value == "timed_out"
    assert ToolState.FAILED.value == "failed"
    assert ToolState.SKIPPED.value == "skipped"

def test_tool_status_rejects_empty_tool_name():
    with pytest.raises(ValueError, match="tool 不能为空"):
        ToolStatus(
            tool="",
            state=ToolState.COMPLETED,
            version="0.12.0",
            reason=None,
        )

def test_tool_status_rejects_untyped_state():
    with pytest.raises(ValueError, match="state 必须是 ToolState"):
        ToolStatus(
            tool="ruff",
            state="completed",
            version="0.12.0",
            reason=None,
        )

@pytest.mark.parametrize(
    "state",
    [
        ToolState.UNAVAILABLE,
        ToolState.TIMED_OUT,
        ToolState.FAILED,
    ]
)
def test_tool_status_requires_reason_for_unsuccessful_state(state):
    with pytest.raises(ValueError, match="未成功状态必须包含原因"):
        ToolStatus(
            tool="mypy",
            state=state,
            version=None,
            reason=None,
        )

def test_quality_finding_preserves_structured_source_finding():
    finding = QualityFinding(
        tool="ruff",
        kind=QualityFindingKind.CODE,
        rule_code="F401",
        message="os imported but unused",
        source_path="app/service.py",
        line=3,
        column=1,
        fix_available=True,
    )

    assert finding.tool == "ruff"
    assert finding.kind is QualityFindingKind.CODE
    assert finding.rule_code == "F401"
    assert finding.message == "os imported but unused"
    assert finding.source_path == "app/service.py"
    assert finding.line == 3
    assert finding.column == 1
    assert finding.fix_available is True

def test_quality_finding_kind_has_stable_serialized_values():
    assert QualityFindingKind.CODE.value == "code"
    assert QualityFindingKind.DEPENDENCY.value == "dependency"
    assert QualityFindingKind.CONFIGURATION.value == "configuration"

def make_quality_finding(**overrides):
    values = {
        "tool": "ruff",
        "kind": QualityFindingKind.CODE,
        "rule_code": "F401",
        "message": "os imported but unused",
        "source_path": "app/service.py",
        "line": 3,
        "column": 1,
        "fix_available": True,
    }
    values.update(overrides)
    return QualityFinding(**values)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tool", "", "tool 不能为空"),
        ("tool", "   ", "tool 不能为空"),
        ("message", "", "message 不能为空"),
        ("message", "   ", "message 不能为空"),
    ],
)
def test_quality_finding_rejects_empty_text_fields(
    field, value, message
):
    with pytest.raises(ValueError, match=message):
        make_quality_finding(**{field: value})

def test_quality_finding_rejects_untyped_kind():
    with pytest.raises(
        ValueError,
        match="kind 必须是 QualityFindingKind",
    ):
        make_quality_finding(kind="code")

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_path", None),
        ("source_path", ""),
        ("line", None),
        ("line", 0),
    ],
)
def test_code_finding_requires_valid_source_location(field, value):
    with pytest.raises(
        ValueError,
        match="代码问题必须包含有效源码位置",
    ):
        make_quality_finding(**{field: value})


def test_quality_finding_rejects_invalid_column():
    with pytest.raises(ValueError, match="column 必须大于等于 1"):
        make_quality_finding(column=0)


def test_quality_finding_rejects_non_boolean_fix_availability():
    with pytest.raises(
        ValueError,
        match="fix_available 必须是 bool",
    ):
        make_quality_finding(fix_available=1)

def test_dependency_finding_allows_no_source_location():
    finding = QualityFinding(
        tool="mypy",
        kind=QualityFindingKind.DEPENDENCY,
        rule_code="import-untyped",
        message="Library stubs not installed",
        source_path=None,
        line=None,
        column=None,
        fix_available=False,
    )

    assert finding.source_path is None
    assert finding.line is None
    assert finding.column is None


def test_code_finding_allows_missing_column():
    finding = make_quality_finding(column=None)

    assert finding.source_path == "app/service.py"
    assert finding.line == 3
    assert finding.column is None

def test_audit_result_aggregates_stable_audit_facts():
    coverage = CoverageSummary(
        statements_covered=75,
        statements_total=100,
        branches_covered=30,
        branches_total=50,
    )
    symbol = SymbolCoverage(**make_symbol())
    finding = make_quality_finding()
    tool = ToolStatus(
        tool="ruff",
        state=ToolState.COMPLETED,
        version="0.12.0",
        reason=None,
    )

    result = AuditResult(
        run_id="audit-001",
        status=AuditStatus.PASSED,
        command=(
            "test-assistant",
            "audit",
            "--path",
            ".",
        ),
        coverage=coverage,
        symbols=(symbol,),
        findings=(finding,),
        tools=(tool,),
        source_digest="sha256:abc123",
    )

    assert result.run_id == "audit-001"
    assert result.status is AuditStatus.PASSED
    assert result.command == (
        "test-assistant",
        "audit",
        "--path",
        ".",
    )
    assert result.coverage is coverage
    assert result.symbols == (symbol,)
    assert result.findings == (finding,)
    assert result.tools == (tool,)
    assert result.source_digest == "sha256:abc123"


def test_audit_status_has_stable_serialized_values():
    assert AuditStatus.PASSED.value == "passed"
    assert AuditStatus.THRESHOLD_FAILED.value == "threshold_failed"
    assert AuditStatus.TESTS_FAILED.value == "tests_failed"
    assert AuditStatus.PARTIAL.value == "partial"
    assert AuditStatus.INFRA_ERROR.value == "infra_error"


def test_audit_thresholds_preserve_explicit_gates():
    thresholds = AuditThresholds(
        statement_rate=0.8,
        branch_rate=0.7,
        max_ruff_findings=5,
        max_mypy_errors=0,
    )

    assert thresholds.statement_rate == pytest.approx(0.8)
    assert thresholds.branch_rate == pytest.approx(0.7)
    assert thresholds.max_ruff_findings == 5
    assert thresholds.max_mypy_errors == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("statement_rate", -0.1, "statement_rate 必须位于 0 到 1 之间"),
        ("statement_rate", 1.1, "statement_rate 必须位于 0 到 1 之间"),
        ("branch_rate", True, "branch_rate 必须位于 0 到 1 之间"),
        ("max_ruff_findings", -1, "max_ruff_findings 必须是非负整数"),
        ("max_mypy_errors", True, "max_mypy_errors 必须是非负整数"),
    ],
)
def test_audit_thresholds_reject_invalid_gates(field, value, message):
    with pytest.raises(ValueError, match=message):
        AuditThresholds(**{field: value})

def make_audit_result(**overrides):
    values = {
        "run_id": "audit-001",
        "status": AuditStatus.PASSED,
        "command": (
            "test-assistant",
            "audit",
            "--path",
            ".",
        ),
        "coverage": CoverageSummary(
            statements_covered=75,
            statements_total=100,
            branches_covered=30,
            branches_total=50,
        ),
        "symbols": (),
        "findings": (),
        "tools": (),
        "source_digest": "sha256:abc123",
    }
    values.update(overrides)
    return AuditResult(**values)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("run_id", "", "run_id 不能为空"),
        ("run_id", "   ", "run_id 不能为空"),
        ("source_digest", "", "source_digest 不能为空"),
        ("source_digest", "   ", "source_digest 不能为空"),
        ("command", (), "command 必须是非空命令"),
        ("command", ("test-assistant", ""), "command 必须是非空命令"),
    ],
)
def test_audit_result_rejects_invalid_required_fields(
    field,
    value,
    message,
):
    with pytest.raises(ValueError, match=message):
        make_audit_result(**{field: value})


def test_audit_result_rejects_untyped_status():
    with pytest.raises(ValueError, match="status 必须是 AuditStatus"):
        make_audit_result(status="passed")


def test_audit_result_accepts_explicit_thresholds():
    thresholds = AuditThresholds(statement_rate=0.8)

    result = make_audit_result(thresholds=thresholds)

    assert result.thresholds is thresholds


def test_audit_result_rejects_untyped_thresholds():
    with pytest.raises(
        ValueError,
        match="thresholds 必须是 AuditThresholds 或 None",
    ):
        make_audit_result(thresholds={"statement_rate": 0.8})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("coverage", "75%", "coverage 必须是 CoverageSummary 或 None"),
        ("symbols", ("invalid",), "symbols 必须包含 SymbolCoverage"),
        ("findings", ("invalid",), "findings 必须包含 QualityFinding"),
        ("tools", ("invalid",), "tools 必须包含 ToolStatus"),
    ],
)
def test_audit_result_rejects_invalid_nested_models(
    field,
    value,
    message,
):
    with pytest.raises(ValueError, match=message):
        make_audit_result(**{field: value})

@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("AuditResult", AuditResult),
        ("AuditStatus", AuditStatus),
        ("AuditThresholds", AuditThresholds),
        ("CoverageState", CoverageState),
        ("CoverageSummary", CoverageSummary),
        ("QualityFinding", QualityFinding),
        ("QualityFindingKind", QualityFindingKind),
        ("SymbolCoverage", SymbolCoverage),
        ("ToolState", ToolState),
        ("ToolStatus", ToolStatus),
    ],
)
def test_audit_models_are_exported_from_core_models(name, expected):
    assert getattr(models, name) is expected
    assert name in models.__all__
