"""查看基线、计划和测试健康状态。"""

from pathlib import Path

import click


from .diagnose import load_diagnosis

@click.command()
@click.option(
    "--path",
    default=".",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    help="目标项目路径",
)
def status(path: Path) -> None:
    """项目测试健康状态"""
    latest_path = (
        path.resolve()
        / ".autotest"
        / "diagnoses"
        / "latest.json"
    )
    if not latest_path.is_file():
        click.echo("状态: 未知（暂无诊断记录）")
        return

    diagnosis = load_diagnosis(latest_path)
    if diagnosis.category.value == "inconclusive":
        health = "需要确认"
    else:
        health = "需要处理"

    click.echo(f"状态: {health}")
    click.echo(f"最近诊断: {diagnosis.category.value}")
    click.echo(f"置信度: {diagnosis.confidence.value}")
    click.echo(f"摘要: {diagnosis.summary}")
