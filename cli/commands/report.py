"""导出最近一次诊断报告。"""

from pathlib import Path

import click


from core.reporters import render_audit_markdown, render_diagnosis_markdown
from core.repositories import AuditRepository, DiagnosisRepository


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
@click.option("--audit", "audit_report", is_flag=True, help="导出最近一次 Audit 报告")
def report(path: Path, output: Path | None, audit_report: bool) -> None:
    """生成测试报告"""
    repository = AuditRepository(path) if audit_report else DiagnosisRepository(path)
    try:
        latest_record = repository.load_latest_record()
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise click.ClickException(
            f"无法读取{' Audit' if audit_report else '诊断'}记录: {error}"
        ) from error
    if latest_record is None:
        raise click.ClickException("暂无 Audit 记录" if audit_report else "暂无诊断记录")
    record = latest_record.payload
    if latest_record.recovered:
        click.echo(
            "警告: latest 记录不可用，已只读恢复自: "
            f"{latest_record.source_path}"
        )

    output_path = output or (
        path.resolve()
        / ".autotest"
        / "reports"
        / ("latest-audit.md" if audit_report else "latest.md")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_audit_markdown(record) if audit_report else render_diagnosis_markdown(record),
        encoding="utf-8",
    )
    click.echo(f"报告已生成: {output_path}")
