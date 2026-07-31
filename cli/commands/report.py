"""导出最近一次诊断报告。"""

from pathlib import Path

import click


from core.reporters import render_diagnosis_markdown
from core.repositories import DiagnosisRepository


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
@click.option(
    "--output",
    type=click.Path(
        dir_okay=False,
        path_type=Path,
    ),
    help="Markdown 输出路径",
)
def report(path: Path, output: Path | None) -> None:
    """生成测试报告"""
    repository = DiagnosisRepository(path)
    try:
        record = repository.load_latest()
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise click.ClickException(
            f"无法读取诊断记录: {error}"
        ) from error
    if record is None:
        raise click.ClickException("暂无诊断记录")

    output_path = output or (
        path.resolve()
        / ".autotest"
        / "reports"
        / "latest.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_diagnosis_markdown(record),
        encoding="utf-8",
    )
    click.echo(f"报告已生成: {output_path}")
