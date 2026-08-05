"""只读环境诊断命令"""
import json
from pathlib import Path

import click

from core.models import (
    DoctorStatus,
    EnvironmentCheck,
)
from core.workflows import run_doctor


class DoctorCommandError(click.ClickException):
    """Doctor 参数或基础设施错误。"""

    exit_code = 2


def _render_check(
    check: EnvironmentCheck,
) -> str:
    """渲染一条环境检查。"""

    parts = [
        f"{check.name}: {check.state.value}",
        (
            "核心"
            if check.required
            else "可选"
        ),
    ]

    if check.version is not None:
        parts.append(
            f"版本={check.version}"
        )

    if check.reason is not None:
        parts.append(
            f"原因={check.reason}"
        )

    if check.capabilities:
        parts.append(
            "能力="
            + ",".join(check.capabilities)
        )

    return "；".join(parts)


@click.command("doctor")
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
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="输出版本化 JSON",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=1),
    default=10.0,
    show_default=True,
    help="单项环境探测超时秒数",
)
def doctor_command(
    project_path: Path,
    json_output: bool,
    timeout: float,
) -> None:
    """检查当前 Python、pytest、Git 和 Audit 工具环境"""

    try:
        result = run_doctor(
            project_root=project_path,
            timeout=timeout,
        )
    except (
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise DoctorCommandError(
            "环境诊断失败"
        ) from error

    if json_output:
        click.echo(
            json.dumps(
                result.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        click.echo(
            f"Doctor 状态: {result.status.value}"
        )
        click.echo(
            "test-assistant: "
            f"{result.test_assistant_version}"
        )
        click.echo(
            f"项目路径: {result.project_path}"
        )
        click.echo(
            "Python 实现: "
            f"{result.python_implementation}"
        )
        click.echo(
            f"平台: {result.platform}"
        )
        click.echo("环境检查:")

        for check in result.checks:
            click.echo(
                "  "
                + _render_check(check)
            )

    if (
            result.status
            is DoctorStatus.INCOMPATIBLE
    ):
        raise click.exceptions.Exit(1)

    if (
            result.status
            is DoctorStatus.INFRA_ERROR
    ):
        raise click.exceptions.Exit(2)
