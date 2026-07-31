"""查看失败归因及证据。"""

import json
from pathlib import Path

import click

from core.models import Diagnosis


# diagnosis 诊断
def load_diagnosis(path: str | Path) -> Diagnosis:
    """从 JSON 文件加载并校验诊断领域对象。"""
    input_path = Path(path)
    try:
        data = json.loads(
            input_path.read_text(encoding="utf-8")
        )
        diagnosis_data = (
            data["diagnosis"]
            if (
                isinstance(data, dict)
                and "diagnosis" in data
            )
            else data
        )
        return Diagnosis.from_dict(diagnosis_data)
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise click.ClickException(
            f"无法读取诊断文件: {error}"
        ) from error


def render_diagnosis(diagnosis: Diagnosis) -> None:
    """输出稳定、可解释的诊断文本。"""
    click.echo(f"诊断: {diagnosis.category.value}")
    click.echo(f"置信度: {diagnosis.confidence.value}")
    click.echo(f"摘要: {diagnosis.summary}")

    click.echo("证据:")
    for evidence in diagnosis.evidence:
        click.echo(
            f"- [{evidence.kind.value}] "
            f"{evidence.description}"
        )
        for detail in evidence.details:
            click.echo(f"  {detail}")

    click.echo("建议动作:")
    for action in diagnosis.suggested_actions:
        click.echo(
            f"- [{action.kind.value}] "
            f"{action.description}"
        )


@click.command("diagnose")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
    help="诊断 JSON 文件",
)
def diagnose_command(input_path: Path) -> None:
    """解释一次已保存的失败诊断。"""
    diagnosis = load_diagnosis(input_path)
    render_diagnosis(diagnosis)
    click.echo(
        "复现命令: "
        f"python -m cli.main diagnose --input {input_path}"
    )
