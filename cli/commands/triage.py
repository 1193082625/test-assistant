"""运行并确定性分诊目标项目已有的 pytest 测试套件。"""

from pathlib import Path
import sys
import time

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
    collect_contract_migration_triage_evidence,
    build_contract_migration_root_causes,
    read_git_sha,
    triage_pytest_suite,
)


class _TriageProgress:
    """将结构化进度事件渲染为稳定的四阶段 CLI 输出。"""

    def __init__(self, *, scope: str, timeout: float) -> None:
        self.scope = scope
        self.timeout = timeout
        self.started = time.monotonic()
        self.total = 0
        self.completed = 0
        self.interactive = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self._line_open = False
        self._rerun_started = False

    @staticmethod
    def _duration(seconds: float) -> str:
        whole = max(0, int(seconds))
        return f"{whole // 60:02d}:{whole % 60:02d}"

    def start(self) -> None:
        click.echo("\n[1/4] 正在执行 pytest 套件")
        click.echo(f"      范围: {self.scope}")
        click.echo(f"      超时: {self.timeout:g} 秒")

    def pytest_event(self, event: dict[str, object]) -> None:
        if event.get("event") == "collection":
            self.total = int(event.get("total") or 0)
            self._draw(force=True)
        elif event.get("event") == "test_complete":
            self.completed = int(event.get("completed") or 0)
            self._draw(force=self.completed == self.total)

    def _draw(self, *, force: bool) -> None:
        elapsed = self._duration(time.monotonic() - self.started)
        percent = (
            int(self.completed * 100 / self.total) if self.total else 0
        )
        message = (
            f"      已运行: {elapsed}  "
            f"进度: {self.completed} / {self.total}（{percent}%）"
        )
        if self.interactive:
            click.echo(f"\r\033[2K{message}", nl=False)
            self._line_open = True
        elif force or self.completed in {0, self.total}:
            click.echo(message)

    def finish_suite(self) -> None:
        if self._line_open:
            click.echo()
            self._line_open = False
        click.echo("      pytest 执行完成，正在分析结构化结果...")

    def workflow_event(self, event: dict[str, object]) -> None:
        kind = event.get("event")
        if kind == "clusters":
            click.echo("\n[2/4] 正在聚类失败")
            click.echo(
                "      发现: "
                f"{event.get('failure_count', 0)} 个失败节点 → "
                f"{event.get('cluster_count', 0)} 个根因簇"
            )
        elif kind == "rerun":
            if not self._rerun_started:
                click.echo("\n[3/4] 正在复跑代表节点")
                self._rerun_started = True
            click.echo(
                f"      进度: {event.get('index')} / {event.get('total')}"
            )
            click.echo(f"      当前: {event.get('node_id')}")

    def start_save(self, *, has_clusters: bool) -> None:
        if not self._rerun_started:
            click.echo("\n[3/4] 无需复跑代表节点")
            if not has_clusters:
                click.echo("      当前套件没有失败簇")
        click.echo("\n[4/4] 正在保存诊断")


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
                key, separator, value = detail.partition("=")
                labels = {
                    "migration_type": "迁移类型",
                    "old_contract": "旧契约",
                    "current_contract": "当前契约",
                    "current_consistent": "当前一致性",
                    "migration_commit": "migration_commit",
                    "warning_source": "warning 来源",
                    "lifecycle_gap": "生命周期缺口",
                    "target": "目标",
                    "current_source": "当前契约来源",
                }
                if separator and key in labels:
                    click.echo(f"  {labels[key]}: {value}")
                else:
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
@click.option(
    "--timeout",
    type=click.FloatRange(min=1),
    default=120.0,
    show_default=True,
    help="pytest 套件执行超时秒数",
)
def triage_command(
    project_path: Path,
    test_path: str | None,
    test_node: str | None,
    max_failures: int | None,
    allow_git_history: bool,
    no_git_history: bool,
    timeout: float,
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
        progress = _TriageProgress(
            scope=scope or "tests/",
            timeout=timeout,
        )
        progress.start()
        suite = executor.execute_suite(
            scope,
            timeout=timeout,
            max_failures=max_failures,
            progress_callback=progress.pytest_event,
        )
        progress.finish_suite()
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
        contract_evidence, contract_degradations = (
            collect_contract_migration_triage_evidence(
                project_root=root,
                suite=suite,
                git_history_enabled=git_history_enabled,
            )
        )
        root_causes.update(
            build_contract_migration_root_causes(contract_evidence)
        )
        degradations = (*degradations, *contract_degradations)
        result = triage_pytest_suite(
            suite=suite,
            executor=executor,
            root_causes=root_causes,
            evidence_by_root_cause=git_evidence,
            evidence_by_node=contract_evidence,
            progress_callback=progress.workflow_event,
        )
        commands = {
            cluster.fingerprint: build_reproduction_command(
                cluster.representative_node or scope or "."
            )
            for cluster in result.clusters
        }
        if not commands:
            commands["suite"] = build_reproduction_command(scope or ".")
        progress.start_save(has_clusters=bool(result.clusters))
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
