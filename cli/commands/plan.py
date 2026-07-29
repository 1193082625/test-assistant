"""查看、批准或拒绝 TestSpec"""
import json
import click
from pathlib import Path
from core.repositories.test_spec import (
    TestSpecRepository
)


def _repository_for(
    project_path: Path,
) -> TestSpecRepository:
    return TestSpecRepository(
        project_root=str(
            project_path.resolve()
        ),
    )

@click.group()
def plan() -> None:
    """查看、批准或拒绝 TestSpec"""

# 创建 list 命令，并立即注册为 plan 的子命令
@plan.command("list")
@click.option(
    "--path",
    "project_path",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=".",
    show_default=True,
    help="目标项目路径",
)
def list_specs(
        project_path: Path,
) -> None:
    """列出目标项目中的 TestSpec"""
    repository = _repository_for(
        project_path
    )
    specs = repository.list_all()

    if not specs:
        click.echo("没有 TestSpec")
        return

    for spec in specs:
        click.echo(
            (
                f"{spec.id} "
                f"[{spec.status.value}] "
                f"{spec.target_symbol} - "
                f"{spec.behavior}"
            )
        )

@plan.command("show")
@click.argument("spec_id")
@click.option(
    "--path",
    "project_path",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=".",
    show_default=True,
    help="目标项目路径",
)
def show_spec(
    spec_id: str,
    project_path: Path,
) -> None:
    """展示单个 TestSpec 的完整内容。"""
    repository = _repository_for(
        project_path
    )
    try:
        spec = repository.get(spec_id)
    except FileNotFoundError as error:
        raise click.ClickException(
            f"未找到 TestSpec: {spec_id}"
        ) from error

    click.echo(
        json.dumps(
            spec.to_dict(),
            ensure_ascii=False,
            indent=2,
        )
    )

@plan.command("approve")
@click.argument("spec_id")
@click.option(
    "--path",
    "project_path",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=".",
    show_default=True,
    help="目标项目路径",
)
def approve_spec(
    spec_id: str,
    project_path: Path,
) -> None:
    """批准一个 proposed TestSpec。"""
    repository = _repository_for(
        project_path
    )
    try:
        approved = repository.approve(
            spec_id
        )
    except FileNotFoundError as error:
        raise click.ClickException(
            f"未找到 TestSpec: {spec_id}"
        ) from error
    except ValueError as error:
        raise click.ClickException(
            str(error)
        ) from error

    click.echo(
        (
            "已批准 TestSpec: "
            f"{approved.id} "
            f"[{approved.status.value}]"
        )
    )

@plan.command("reject")
@click.argument("spec_id")
@click.option(
    "--path",
    "project_path",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=".",
    show_default=True,
    help="目标项目路径",
)
def reject_spec(
    spec_id: str,
    project_path: Path,
) -> None:
    """拒绝一个 proposed TestSpec。"""
    repository = _repository_for(
        project_path
    )
    try:
        rejected = repository.reject(
            spec_id
        )
    except FileNotFoundError as error:
        raise click.ClickException(
            f"未找到 TestSpec: {spec_id}"
        ) from error
    except ValueError as error:
        raise click.ClickException(
            str(error)
        ) from error

    click.echo(
        (
            "已拒绝 TestSpec: "
            f"{rejected.id} "
            f"[{rejected.status.value}]"
        )
    )