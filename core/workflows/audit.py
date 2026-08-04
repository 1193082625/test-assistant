"""coverage、Ruff 与 mypy 的确定性只读 Audit 工作流。"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.analyzers.coverage import analyze_symbol_coverage
from core.executors.coverage_executor import CoverageExecutor
from core.executors.mypy_executor import MypyExecutor
from core.executors.ruff_executor import RuffExecutor
from core.models import (
    AuditResult,
    AuditStatus,
    AuditThresholds,
    CoverageSummary,
    QualityFindingKind,
    ToolState,
    ToolStatus,
)


def _source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".autotest", ".git", ".venv", "venv", "node_modules"}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts[:-1]):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _summary_from_coverage(payload: dict[str, object]) -> CoverageSummary:
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("coverage totals 缺失")
    fields = (
        "covered_lines", "num_statements", "covered_branches", "num_branches"
    )
    values = [totals.get(field) for field in fields]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in values
    ):
        raise ValueError("coverage totals 无效")
    return CoverageSummary(
        statements_covered=values[0], statements_total=values[1],
        branches_covered=values[2], branches_total=values[3],
    )


def _threshold_failed(
    *,
    thresholds: AuditThresholds | None,
    coverage: CoverageSummary | None,
    findings,
) -> bool:
    if thresholds is None:
        return False
    if thresholds.statement_rate is not None and (
        coverage is None
        or coverage.statement_rate is None
        or coverage.statement_rate < thresholds.statement_rate
    ):
        return True
    if thresholds.branch_rate is not None and (
        coverage is None
        or coverage.branch_rate is None
        or coverage.branch_rate < thresholds.branch_rate
    ):
        return True
    ruff_count = sum(finding.tool == "ruff" for finding in findings)
    mypy_error_count = sum(
        finding.tool == "mypy" and finding.kind is QualityFindingKind.CODE
        for finding in findings
    )
    return (
        thresholds.max_ruff_findings is not None
        and ruff_count > thresholds.max_ruff_findings
    ) or (
        thresholds.max_mypy_errors is not None
        and mypy_error_count > thresholds.max_mypy_errors
    )


def run_audit(
    *,
    project_root: str | Path,
    run_id: str,
    source_path: str,
    coverage_enabled: bool = True,
    quality_enabled: bool = True,
    thresholds: AuditThresholds | None = None,
    coverage_executor=None,
    ruff_executor=None,
    mypy_executor=None,
    timeout: float = 120,
    test_path: str | None = None,
    test_node: str | None = None,
    changed_paths: tuple[str, ...] | None = None,
    changed_qualified_names: tuple[str, ...] | None = None,
) -> AuditResult:
    """并列运行启用的 adapter；单个降级不丢失其他结果。"""
    if not coverage_enabled and not quality_enabled:
        raise ValueError("至少启用 coverage 或 quality")
    root = Path(project_root).resolve()
    coverage_executor = coverage_executor or CoverageExecutor(root)
    ruff_executor = ruff_executor or RuffExecutor(root)
    mypy_executor = mypy_executor or MypyExecutor(root)
    tasks = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        if coverage_enabled:
            tasks["coverage"] = pool.submit(
                coverage_executor.execute,
                source_path=source_path,
                test_path=test_path,
                test_node=test_node,
                timeout=timeout,
            )
        if quality_enabled:
            tasks["ruff"] = pool.submit(ruff_executor.execute, timeout=timeout)
            tasks["mypy"] = pool.submit(mypy_executor.execute, timeout=timeout)
        completed = {}
        for name, future in tasks.items():
            try:
                completed[name] = future.result()
            except Exception as error:
                completed[name] = ToolStatus(
                    tool=name,
                    state=ToolState.FAILED,
                    version=None,
                    reason=f"adapter_exception:{type(error).__name__}",
                )

    tools: list[ToolStatus] = []
    findings = []
    coverage = None
    symbols = ()
    tests_failed = False
    for name in ("coverage", "ruff", "mypy"):
        if name not in completed:
            tools.append(ToolStatus(
                tool=name, state=ToolState.SKIPPED, version=None, reason=None
            ))
            continue
        result = completed[name]
        if isinstance(result, ToolStatus):
            tools.append(result)
            continue
        tools.append(result.status)
        if name == "coverage" and result.coverage_data is not None:
            try:
                coverage = _summary_from_coverage(result.coverage_data)
                symbols = analyze_symbol_coverage(
                    project_root=root, coverage_data=result.coverage_data
                )
            except ValueError:
                tools[-1] = ToolStatus(
                    tool="coverage", state=ToolState.FAILED,
                    version=result.status.version, reason="invalid_coverage_data",
                )
                coverage = None
                symbols = ()
            tests_failed = result.report.error_type == "test_failure"
        elif name in {"ruff", "mypy"}:
            findings.extend(result.findings)

    if changed_paths is not None:
        path_set = set(changed_paths)
        name_set = set(changed_qualified_names or ())
        symbols = tuple(
            symbol for symbol in symbols
            if symbol.source_path in path_set
            and (not name_set or symbol.qualified_name in name_set)
        )
        findings = [
            finding for finding in findings
            if finding.source_path in path_set
        ]

    enabled_tools = [tool for tool in tools if tool.state is not ToolState.SKIPPED]
    completed_count = sum(
        tool.state is ToolState.COMPLETED for tool in enabled_tools
    )
    if completed_count == 0:
        status = AuditStatus.INFRA_ERROR
    elif tests_failed:
        status = AuditStatus.TESTS_FAILED
    elif any(tool.state is not ToolState.COMPLETED for tool in enabled_tools):
        status = AuditStatus.PARTIAL
    elif _threshold_failed(
        thresholds=thresholds, coverage=coverage, findings=findings
    ):
        status = AuditStatus.THRESHOLD_FAILED
    else:
        status = AuditStatus.PASSED
    command = ["test-assistant", "audit", "--path", "."]
    if changed_paths is not None:
        command.append("--changed-only")
    if coverage_enabled and not quality_enabled:
        command.append("--coverage")
    elif quality_enabled and not coverage_enabled:
        command.append("--quality")
    return AuditResult(
        run_id=run_id,
        status=status,
        command=tuple(command),
        coverage=coverage,
        symbols=symbols,
        findings=tuple(findings),
        tools=tuple(tools),
        source_digest=_source_digest(root),
        thresholds=thresholds,
    )
