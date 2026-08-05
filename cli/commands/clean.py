"""Explicit history cleanup command."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import click

from core.models import CleanupPlan, CleanupRecordType
from core.workflows import execute_cleanup, plan_cleanup


@click.command("clean")
@click.option(
    "--path",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="目标项目路径",
)
@click.option(
    "--older-than-days",
    default=30,
    show_default=True,
    type=click.IntRange(min=0),
    help="只选择超过指定天数的历史",
)
@click.option(
    "--keep-latest",
    default=20,
    show_default=True,
    type=click.IntRange(min=0),
    help="每类至少保留的最新历史数",
)
@click.option(
    "--max-total-mib",
    type=click.FloatRange(min=0),
    help="受控历史的可选容量目标（MiB）",
)
@click.option(
    "--include-diagnoses",
    is_flag=True,
    help="允许把未被引用的 Diagnosis 纳入候选",
)
@click.option("--dry-run", is_flag=True, help="仅预览清理计划（默认）")
@click.option("--apply", "apply_changes", is_flag=True, help="确认后执行清理")
@click.option("--json", "json_output", is_flag=True, help="输出纯 JSON 预览")
def clean_command(
    path: Path,
    older_than_days: int,
    keep_latest: int,
    max_total_mib: float | None,
    include_diagnoses: bool,
    dry_run: bool,
    apply_changes: bool,
    json_output: bool,
) -> None:
    """预览或显式清理受控的 .autotest 历史记录。"""

    if dry_run and apply_changes:
        raise click.UsageError("--dry-run 与 --apply 不能同时使用")
    if json_output and apply_changes:
        raise click.UsageError("--json 只允许用于 dry-run")
    if max_total_mib is not None and not math.isfinite(max_total_mib):
        raise click.UsageError("--max-total-mib 必须是有限数字")
    max_total_bytes = (
        None
        if max_total_mib is None
        else int(max_total_mib * 1024 * 1024)
    )

    try:
        plan = plan_cleanup(
            project_root=path,
            older_than_days=older_than_days,
            keep_latest=keep_latest,
            max_total_bytes=max_total_bytes,
            include_diagnoses=include_diagnoses,
        )
    except (OSError, TypeError, ValueError) as error:
        _exit_two(f"无法生成清理计划: {error}")

    if json_output:
        click.echo(json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True))
        return

    _render_plan(plan)
    if not apply_changes:
        click.echo("预览完成，未修改任何文件")
        return
    if not plan.candidates:
        click.echo("没有可清理的候选记录")
        return
    if not click.confirm("确认清理以上候选？"):
        click.echo("已取消，未修改任何文件")
        return

    try:
        result = execute_cleanup(project_root=path, plan=plan)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        _exit_two(f"清理失败: {error}")
    click.echo(
        f"清理完成: 已删除 {len(result.deleted_paths)}；"
        f"回收 {result.reclaimed_bytes} 字节"
    )


def _render_plan(plan: CleanupPlan) -> None:
    click.echo(f"候选总数: {len(plan.candidates)}")
    click.echo(f"可回收字节: {plan.reclaimable_bytes}")
    grouped = defaultdict(list)
    for candidate in plan.candidates:
        grouped[candidate.record_type].append(candidate)
    for record_type in CleanupRecordType:
        candidates = grouped.get(record_type, [])
        if not candidates:
            continue
        click.echo(f"{record_type.value}:")
        for candidate in candidates:
            reasons = ",".join(reason.value for reason in candidate.reasons)
            click.echo(
                f"  {candidate.relative_path}；"
                f"{candidate.size_bytes} 字节；{reasons}"
            )
    if plan.protected:
        click.echo(f"受保护记录: {plan.protected_count}")
        for protected in plan.protected:
            reasons = ",".join(reason.value for reason in protected.reasons)
            click.echo(f"  {protected.relative_path}；{reasons}")


def _exit_two(message: str) -> None:
    click.echo(f"Error: {message}", err=True)
    raise click.exceptions.Exit(2)
