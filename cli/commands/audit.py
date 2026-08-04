"""只读 coverage 与代码质量审计命令。"""

from pathlib import Path
from uuid import uuid4

import click

from core.analyzers.change_evidence import collect_change_evidence
from core.models import AuditStatus, AuditThresholds, CoverageState
from core.repositories import AuditRepository
from core.workflows import run_audit


def _rate(value: float | None) -> str:
    return "不适用" if value is None else f"{value:.1%}"


@click.command("audit")
@click.option(
    "--path", "project_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".", show_default=True, help="目标项目路径",
)
@click.option("--source-path", default=".", show_default=True, help="覆盖率源码范围")
@click.option("--test-path", help="仅对项目内指定测试路径采集 coverage")
@click.option("--test-node", help="仅对指定 pytest node 采集 coverage")
@click.option("--coverage/--no-coverage", default=True, help="启用或禁用覆盖率审计")
@click.option("--quality/--no-quality", default=True, help="启用或禁用 Ruff/mypy")
@click.option("--changed-only", is_flag=True, help="仅审计有变更证据的符号")
@click.option("--statement-threshold", type=click.FloatRange(0, 1))
@click.option("--branch-threshold", type=click.FloatRange(0, 1))
@click.option("--max-ruff-findings", type=click.IntRange(min=0))
@click.option("--max-mypy-errors", type=click.IntRange(min=0))
@click.option(
    "--timeout", type=click.FloatRange(min=1), default=120.0,
    show_default=True, help="每个 adapter 的超时秒数",
)
def audit_command(
    project_path: Path,
    source_path: str,
    test_path: str | None,
    test_node: str | None,
    coverage: bool,
    quality: bool,
    changed_only: bool,
    statement_threshold: float | None,
    branch_threshold: float | None,
    max_ruff_findings: int | None,
    max_mypy_errors: int | None,
    timeout: float,
) -> None:
    """报告未覆盖源码符号以及 Ruff/mypy findings，不自动修复。"""
    if not coverage and not quality:
        raise click.UsageError("至少启用 coverage 或 quality")
    if test_path is not None and test_node is not None:
        raise click.UsageError("--test-path 与 --test-node 不能同时使用")
    if not coverage and (test_path is not None or test_node is not None):
        raise click.UsageError("测试范围参数只能与 coverage 一起使用")
    threshold_values = (
        statement_threshold, branch_threshold,
        max_ruff_findings, max_mypy_errors,
    )
    thresholds = None
    if any(value is not None for value in threshold_values):
        thresholds = AuditThresholds(
            statement_rate=statement_threshold,
            branch_rate=branch_threshold,
            max_ruff_findings=max_ruff_findings,
            max_mypy_errors=max_mypy_errors,
        )
    root = project_path.resolve()
    try:
        evidence = collect_change_evidence(root) if changed_only else None
        result = run_audit(
            project_root=root,
            run_id=uuid4().hex,
            source_path=source_path,
            coverage_enabled=coverage,
            quality_enabled=quality,
            thresholds=thresholds,
            timeout=timeout,
            test_path=test_path,
            test_node=test_node,
            changed_paths=evidence.paths if evidence else None,
            changed_qualified_names=(
                evidence.qualified_names if evidence else None
            ),
        )
        record_path = AuditRepository(root).save(result)
    except (OSError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Audit 状态: {result.status.value}")
    if changed_only:
        click.echo(
            f"变更证据: {evidence.source}; Python 文件 {len(evidence.paths)}"
        )
    if result.coverage is not None:
        click.echo(
            "覆盖率: "
            f"语句 {result.coverage.statements_covered}/"
            f"{result.coverage.statements_total} "
            f"({_rate(result.coverage.statement_rate)}); "
            f"分支 {result.coverage.branches_covered}/"
            f"{result.coverage.branches_total} "
            f"({_rate(result.coverage.branch_rate)})"
        )
    gaps = [
        symbol for symbol in result.symbols
        if symbol.state in {CoverageState.PARTIAL, CoverageState.UNCOVERED}
    ]
    if gaps:
        click.echo("未覆盖符号:")
        for symbol in gaps[:10]:
            click.echo(
                f"  - {symbol.source_path}::{symbol.qualified_name} "
                f"[{symbol.state.value}]"
            )
    click.echo(f"质量 findings: {len(result.findings)}")
    for tool in result.tools:
        suffix = f" ({tool.reason})" if tool.reason else ""
        click.echo(f"  {tool.tool}: {tool.state.value}{suffix}")
    click.echo(f"Audit 记录: {record_path}")
    if result.status in {
        AuditStatus.THRESHOLD_FAILED,
        AuditStatus.TESTS_FAILED,
    }:
        raise click.exceptions.Exit(1)
    if result.status is AuditStatus.INFRA_ERROR:
        raise click.exceptions.Exit(2)
