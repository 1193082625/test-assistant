"""Explicit schema migration command."""

from __future__ import annotations

import json
from pathlib import Path

import click

from core.models import MigrationAction, MigrationPlan
from core.workflows import execute_migration, plan_migration


@click.command("migrate")
@click.option(
    "--path",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="目标项目路径",
)
@click.option("--dry-run", is_flag=True, help="仅预览迁移计划（默认）")
@click.option("--apply", "apply_changes", is_flag=True, help="确认后应用迁移")
@click.option("--json", "json_output", is_flag=True, help="输出纯 JSON 预览")
def migrate_command(
    path: Path,
    dry_run: bool,
    apply_changes: bool,
    json_output: bool,
) -> None:
    """预览或显式应用 .autotest schema 迁移。"""

    if dry_run and apply_changes:
        raise click.UsageError("--dry-run 与 --apply 不能同时使用")
    if json_output and apply_changes:
        raise click.UsageError("--json 只允许用于 dry-run")

    try:
        plan = plan_migration(project_root=path)
    except (OSError, TypeError, ValueError) as error:
        raise click.ClickException(f"无法生成迁移计划: {error}") from error

    if json_output:
        click.echo(json.dumps(plan.to_dict(), ensure_ascii=False, sort_keys=True))
        return

    _render_plan(plan)
    if not apply_changes:
        click.echo("预览完成，未修改任何文件")
        return
    if plan.blocked:
        raise click.ClickException("迁移计划已阻止，请先处理不支持的记录")

    actionable = [
        item for item in plan.items if item.action is not MigrationAction.SKIP
    ]
    if not actionable:
        click.echo("没有需要迁移或修复的记录")
        return
    if not click.confirm("确认应用以上迁移？"):
        click.echo("已取消，未修改任何文件")
        return

    try:
        result = execute_migration(project_root=path, plan=plan)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(f"迁移失败: {error}") from error
    click.echo(
        "迁移完成: "
        f"迁移 {result.migrated_count}，修复 latest {result.repaired_count}"
    )


def _render_plan(plan: MigrationPlan) -> None:
    click.echo("迁移计划:")
    if not plan.items:
        click.echo("  无受控记录")
        return
    for item in plan.items:
        source = "-" if item.source_version is None else str(item.source_version)
        suffix = f"；{item.reason}" if item.reason else ""
        click.echo(
            f"  {item.relative_path}: {item.record_type}；"
            f"{source} → {item.target_version}；{item.action.value}{suffix}"
        )
