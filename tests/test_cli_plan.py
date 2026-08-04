import json
import pytest
from click.testing import CliRunner
from cli.main import cli
from core.models import (
    AuditResult,
    AuditStatus,
    CoverageSummary,
    SymbolCoverage,
    ToolState,
    ToolStatus,
    TestSpec as Spec,
    TestSpecStatus as SpecStatus,
)
from core.repositories.test_spec import (
    TestSpecRepository as SpecRepository,
)
from core.repositories import AuditRepository


def make_spec() -> Spec:
    return Spec(
        id="spec-demo-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={},
        action="调用 add(a, b)",
        expected={
            "return": 3,
        },
    )

def test_plan_list_shows_empty_state(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ['plan', 'list', '--path', str(tmp_path)],
    )

    assert result.exit_code == 0
    assert result.output == (
        "没有 TestSpec\n"
    )


def test_plan_from_audit_rejects_symbol_not_in_latest_gap(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    AuditRepository(tmp_path).save(AuditResult(
        run_id="audit-plan-001",
        status=AuditStatus.PASSED,
        command=("test-assistant", "audit"),
        coverage=CoverageSummary(0, 2, 0, 0),
        symbols=(SymbolCoverage(
            source_path="demo.py", qualified_name="demo.other",
            kind="function", start_line=1, end_line=2,
            summary=CoverageSummary(0, 2, 0, 0),
            missing_lines=(1, 2), missing_branches=(),
        ),),
        findings=(),
        tools=(ToolStatus(
            tool="coverage", state=ToolState.COMPLETED,
            version="7", reason=None,
        ),),
        source_digest="sha256:abc",
    ))

    result = CliRunner().invoke(cli, [
        "plan", "propose", "demo.add", "--path", str(tmp_path),
        "--source-path", "demo.py", "--module-path", "demo", "--from-audit",
    ])

    assert result.exit_code == 1
    assert "目标符号不在最近一次 Audit 覆盖缺口中" in result.output

def test_plan_list_shows_spec_summary(
    tmp_path,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    repository.save(
        make_spec()
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "plan",
            "list",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        "spec-demo-001 [proposed] "
        "demo.add - 计算两个整数之和\n"
    )

def test_plan_show_outputs_complete_spec(
    tmp_path,
):
    spec = make_spec()
    SpecRepository(
        project_root=tmp_path,
    ).save(spec)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "plan",
            "show",
            "spec-demo-001",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(
        result.output
    ) == spec.to_dict()

def test_plan_show_reports_missing_spec(
    tmp_path,
):
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "plan",
            "show",
            "spec-missing",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert result.output == (
        "Error: 未找到 TestSpec: "
        "spec-missing\n"
    )

def test_plan_approve_persists_status(
    tmp_path,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    repository.save(
        make_spec()
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "plan",
            "approve",
            "spec-demo-001",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        "已批准 TestSpec: "
        "spec-demo-001 [approved]\n"
    )
    assert (
        repository.get(
            "spec-demo-001"
        ).status
        is SpecStatus.APPROVED
    )

def test_plan_reject_persists_status(
    tmp_path,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    repository.save(
        make_spec()
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "plan",
            "reject",
            "spec-demo-001",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        "已拒绝 TestSpec: "
        "spec-demo-001 [rejected]\n"
    )
    assert (
        repository.get(
            "spec-demo-001"
        ).status
        is SpecStatus.REJECTED
    )

@pytest.mark.parametrize(
    "command",
    [
        "approve",
        "reject",
    ],
)
def test_plan_review_reports_missing_spec(
    tmp_path,
    command,
):
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "plan",
            command,
            "spec-missing",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert result.output == (
        "Error: 未找到 TestSpec: "
        "spec-missing\n"
    )

@pytest.mark.parametrize(
    (
        "initial_action",
        "command",
        "message",
        "expected_status",
    ),
    [
        (
            "reject",
            "approve",
            "已拒绝的 TestSpec 不能批准",
            SpecStatus.REJECTED,
        ),
        (
            "approve",
            "reject",
            "已批准的 TestSpec 不能拒绝",
            SpecStatus.APPROVED,
        ),
    ],
)
def test_plan_review_reports_terminal_conflict(
    tmp_path,
    initial_action,
    command,
    message,
    expected_status,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    repository.save(
        make_spec()
    )

    getattr(
        repository,
        initial_action,
    )("spec-demo-001")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "plan",
            command,
            "spec-demo-001",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert result.output == (
        f"Error: {message}\n"
    )
    assert (
        repository.get(
            "spec-demo-001"
        ).status
        is expected_status
    )

@pytest.mark.parametrize(
    (
        "command",
        "output",
        "expected_status",
    ),
    [
        (
            "approve",
            (
                "已批准 TestSpec: "
                "spec-demo-001 [approved]\n"
            ),
            SpecStatus.APPROVED,
        ),
        (
            "reject",
            (
                "已拒绝 TestSpec: "
                "spec-demo-001 [rejected]\n"
            ),
            SpecStatus.REJECTED,
        ),
    ],
)
def test_plan_review_is_idempotent(
    tmp_path,
    command,
    output,
    expected_status,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    repository.save(
        make_spec()
    )

    runner = CliRunner()
    arguments = [
        "plan",
        command,
        "spec-demo-001",
        "--path",
        str(tmp_path),
    ]

    first = runner.invoke(
        cli,
        arguments,
    )
    repeated = runner.invoke(
        cli,
        arguments,
    )

    assert first.exit_code == 0
    assert repeated.exit_code == 0
    assert first.output == output
    assert repeated.output == output
    assert (
        repository.get(
            "spec-demo-001"
        ).status
        is expected_status
    )
