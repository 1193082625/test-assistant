"""运行并确定性分诊目标项目已有的 pytest 测试套件。"""

from pathlib import Path

import click

from core.analyzers import extract_failure_root_causes
from core.executors import PytestExecutor
from core.repositories import (
    DiagnosisRepository,
    GitPermissionRepository,
    TriageRepository,
)
from core.workflows import (
    build_dependency_digest,
    build_reproduction_command,
    collect_local_git_triage_evidence,
    read_git_sha,
    triage_pytest_suite,
)


def _exit_error(message: str) -> None:
    click.echo(f"错误: {message}", err=True)
    raise click.exceptions.Exit(2)


def _safe_test_scope(
    *,
    root: Path,
    test_path: str | None,
    test_node: str | None,
) -> str | None:
    if test_path and test_node:
        raise click.UsageError("--test-path 与 --test-node 不能同时使用")

    value = test_node or test_path
    if value is None:
        return None
    path_text, separator, symbol = value.partition("::")
    if test_node and (not separator or not symbol.strip()):
        raise click.UsageError("--test-node 必须包含精确测试符号")
    resolved = (root / path_text).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise click.UsageError("测试范围必须位于目标项目内") from error
    if not resolved.is_file():
        raise click.UsageError(f"未找到测试文件: {path_text}")
    normalized = relative.as_posix()
    if test_node:
        normalized = f"{normalized}::{symbol}"
    return normalized


def _save_diagnoses(
    *,
    root: Path,
    result,
    commands: dict[str, str],
) -> tuple[str, ...]:
    repository = DiagnosisRepository(root)
    references: list[str] = []
    for index, diagnosis in enumerate(result.diagnoses):
        cluster = (
            result.clusters[index]
            if index < len(result.clusters)
            else None
        )
        command = (
            commands[cluster.fingerprint]
            if cluster is not None
            else build_reproduction_command(".")
        )
        path = repository.save(
            diagnosis=diagnosis,
            execution_reports=(result.report,),
            reproduction_command=command,
            git_sha=read_git_sha(root),
            dependency_digest=build_dependency_digest(root),
        )
        references.append(path.relative_to(root).as_posix())
    return tuple(references)


def _render_result(result, record_path: Path) -> None:
    counts: dict[str, int] = {}
    for test_result in result.report.test_results:
        counts[test_result.status] = counts.get(test_result.status, 0) + 1
    summary = ", ".join(
        f"{count} {status}" for status, count in sorted(counts.items())
    ) or "no test results"
    click.echo(
        f"pytest 摘要: {summary}; "
        f"exit_code={result.report.exit_code}"
    )
    click.echo(f"失败簇: {len(result.clusters)}")

    for index, cluster in enumerate(result.clusters, start=1):
        diagnosis = result.diagnoses[index - 1]
        node = cluster.representative_node or "<collection>"
        command_target = cluster.representative_node or "."
        click.echo(f"\n[{index}] {diagnosis.category.value}")
        click.echo(f"置信度: {diagnosis.confidence.value}")
        click.echo(f"代表 node: {node}")
        click.echo(f"摘要: {diagnosis.summary}")
        click.echo("证据:")
        for evidence in diagnosis.evidence:
            click.echo(
                f"- [{evidence.kind.value}] {evidence.description}"
            )
            for detail in evidence.details:
                click.echo(f"  {detail}")
        click.echo(
            f"复现命令: {build_reproduction_command(command_target)}"
        )

    if result.diagnoses and not result.clusters:
        diagnosis = result.diagnoses[0]
        click.echo(f"诊断: {diagnosis.category.value}")
        click.echo(f"置信度: {diagnosis.confidence.value}")
        click.echo(f"摘要: {diagnosis.summary}")
    click.echo(f"Triage 记录: {record_path}")


def _git_history_permission(
    *,
    root: Path,
    allow_git_history: bool,
    no_git_history: bool,
) -> bool:
    if allow_git_history and no_git_history:
        raise click.UsageError(
            "--allow-git-history 与 --no-git-history 不能同时使用"
        )
    repository = GitPermissionRepository(root)
    if allow_git_history:
        repository.grant()
        return True
    if no_git_history:
        return False
    return repository.is_granted()


def _render_git_boundary(enabled: bool) -> None:
    state = "已授权（本地只读）" if enabled else "未授权，诊断安全降级"
    click.echo(f"Git 历史证据: {state}")
    click.echo("网络访问: 禁止")
    click.echo("Git 修改: 禁止")


@click.command("triage")
@click.option(
    "--path",
    "project_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    show_default=True,
    help="目标项目路径",
)
@click.option("--test-path", help="项目内的 pytest 测试文件")
@click.option("--test-node", help="精确 pytest node")
@click.option(
    "--max-failures",
    type=click.IntRange(min=1),
    help="达到指定失败数后停止 pytest",
)
@click.option(
    "--allow-git-history",
    is_flag=True,
    help="为当前仓库授权读取本地 Git 历史并持久保存授权",
)
@click.option(
    "--no-git-history",
    is_flag=True,
    help="本次运行不读取 Git 历史（覆盖已保存授权）",
)
def triage_command(
    project_path: Path,
    test_path: str | None,
    test_node: str | None,
    max_failures: int | None,
    allow_git_history: bool,
    no_git_history: bool,
) -> None:
    """运行已有 pytest 套件，聚类、复跑并保存确定性诊断。"""
    root = project_path.resolve()
    scope = _safe_test_scope(
        root=root,
        test_path=test_path,
        test_node=test_node,
    )
    executor = PytestExecutor(cwd=str(root))
    try:
        git_history_enabled = _git_history_permission(
            root=root,
            allow_git_history=allow_git_history,
            no_git_history=no_git_history,
        )
        _render_git_boundary(git_history_enabled)
        suite = executor.execute_suite(
            scope,
            max_failures=max_failures,
        )
        if git_history_enabled:
            root_causes, git_evidence, degradations = (
                collect_local_git_triage_evidence(
                    project_root=root,
                    suite=suite,
                )
            )
        else:
            root_causes = extract_failure_root_causes(
                project_root=root,
                issues=suite.issues,
            )
            git_evidence = {}
            degradations = ()
        result = triage_pytest_suite(
            suite=suite,
            executor=executor,
            root_causes=root_causes,
            evidence_by_root_cause=git_evidence,
        )
        commands = {
            cluster.fingerprint: build_reproduction_command(
                cluster.representative_node or scope or "."
            )
            for cluster in result.clusters
        }
        if not commands:
            commands["suite"] = build_reproduction_command(scope or ".")
        references = _save_diagnoses(
            root=root,
            result=result,
            commands=commands,
        )
        record_path = TriageRepository(root).save(
            result=result,
            diagnosis_references=references,
            reproduction_commands=commands,
            git_sha=read_git_sha(root),
            dependency_digest=build_dependency_digest(root),
            git_history_audit={
                "enabled": git_history_enabled,
                "scope": (
                    "local_read_only" if git_history_enabled else "disabled"
                ),
                "network_access": False,
                "git_mutation": False,
                "degradations": list(degradations),
            },
        )
    except (OSError, TypeError, ValueError) as error:
        _exit_error(str(error))

    _render_result(result, record_path)
    if result.report.error_type in {
        "startup_error",
        "runner_error",
        "parse_error",
        "timeout",
    }:
        raise click.exceptions.Exit(2)
    if result.diagnoses:
        raise click.exceptions.Exit(1)
