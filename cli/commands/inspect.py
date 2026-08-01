"""
查看项目检测证据与能力

项目语言和测试框架；
变更符号及其类型；
可测性状态与原因；
docstring、类型提示等契约证据；
测试选择模式；
选中的测试文件；
选择证据和降级警告。
"""

# inspect 检查

from pathlib import Path
import click
import yaml

from core.analyzers.framework import EXCLUDE_DIRS
from core.analyzers.impact import (
    analyze_changed_python_symbols,
    select_tests_for_changes,
)
from core.analyzers.snapshot import (
    compare_snapshots,
    read_snapshot_manifest,
    take_snapshot,
)
from core.analyzers.source import (
    classify_symbol_testability,
    resolve_python_module_name
)
from core.analyzers.contract import (
    extract_python_contract_evidence
)


@click.command("inspect")
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
    help="已初始化的目标项目路径"
)
def inspect_command(project_path: Path) -> None:
    """查看项目分析、证据和测试选择结果"""
    root_path = project_path.resolve()
    config_path = (
        root_path / ".autotest" / "config.yml"
    )
    if not config_path.is_file():
        raise click.ClickException(
            (
                "未找到 .autotest/config.yml；"
                "请先运行 test-assistant init"
            )
        )

    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}

    except (OSError, yaml.YAMLError) as error:
        raise click.ClickException(
            f"无法读取项目配置: {error}"
        ) from error

    if not isinstance(config, dict):
        raise click.ClickException(
            "项目配置格式无效: 根节点必须是映射"
        )

    project_config = config.get("project", {})

    if not isinstance(project_config, dict):
        raise click.ClickException(
            "项目配置格式无效: project 必须是映射"
        )

    project_name = project_config.get("name", root_path.name)
    language = (
        project_config.get("language")
        or "unknown"
    )
    test_frameworks = project_config.get("test_frameworks", [])

    if not isinstance(test_frameworks, list):
        raise click.ClickException(
            (
                "项目配置格式无效: "
                "test_frameworks 必须是列表"
            )
        )

    framework_text = (
        ", ".join(str(framework) for framework in test_frameworks)
        or "未检测到"
    )

    click.echo(f"项目: {project_name}")
    click.echo(f"语言: {language}")
    click.echo(f"测试框架: {framework_text}")

    snapshot_path = (
        root_path / ".autotest" / "snapshot.json"
    )

    try:
        if snapshot_path.is_file():
            old_snapshots = read_snapshot_manifest(
                str(snapshot_path)
            ).files
        else:
            old_snapshots = []
    except (OSError, ValueError) as error:
        raise click.ClickException(
            f"无法读取项目快照: {error}"
        ) from error

    new_snapshots, _ = take_snapshot(
        str(root_path),
        EXCLUDE_DIRS,
    )

    changed_files = compare_snapshots(
        old_snapshots,
        new_snapshots,
    )
    changed_symbols = []
    symbol_analysis = None

    if str(language).strip().lower() == "python":
        try:
            symbol_analysis = analyze_changed_python_symbols(
                project_root=str(root_path),
                changed_files=changed_files,
                old_snapshots=old_snapshots,
                new_snapshots=new_snapshots,
            )
            changed_symbols = symbol_analysis.symbols
        except (SyntaxError, UnicodeError, OSError):
            # TestSelection 会负责输出安全降级警告
            changed_symbols = []

    contract_evidence = []
    changed_symbol_names = {
        symbol.qualified_name
        for symbol in changed_symbols
    }
    changed_source_files = sorted({
        symbol.file_path
        for symbol in changed_symbols
    })
    for source_file in changed_source_files:
        module_name = resolve_python_module_name(
            file_path=source_file,
            project_root=str(root_path),
        )
        file_evidence = (
            extract_python_contract_evidence(
                file_path=source_file,
                module_name=module_name,
            )
        )
        contract_evidence.extend(
            evidence
            for evidence in file_evidence
            if (
                evidence.symbol_qualified_name in changed_symbol_names
            )
        )

    selection = select_tests_for_changes(
        project_root=str(root_path),
        language=language,
        changed_files=changed_files,
        old_snapshots=old_snapshots,
        new_snapshots=new_snapshots,
    )

    if symbol_analysis is not None:
        click.echo(
            f"分析精度: {symbol_analysis.precision.value}"
        )

    if changed_symbols:
        click.echo("变更符号: ")
        for symbol in changed_symbols:
            assessment = classify_symbol_testability(symbol)
            click.echo(
                (
                    f"  - {symbol.qualified_name} "
                    f"[{symbol.kind.value}, "
                    f"{assessment.status.value}]"
                )
            )
            for reason in assessment.reasons:
                click.echo(f"    原因: {reason}")

    if contract_evidence:
        click.echo("契约证据:")

        for evidence in contract_evidence:
            click.echo(
                (
                    f"  - {evidence.symbol_qualified_name} "
                    f"[{evidence.kind.value}, "
                    f"{evidence.strength.value}]"
                )
            )
            click.echo(f"    {evidence.content}")
            click.echo(
                (
                    f"    位置: {evidence.source_path}:"
                    f"{evidence.source_line}"
                )
            )

    click.echo(f"测试选择: {selection.mode.value}")

    if selection.test_files:
        click.echo("测试文件:")
        for test_file in selection.test_files:
            click.echo(f"  - {test_file}")

    if selection.evidence:
        click.echo("选择证据:")
        for evidence in selection.evidence:
            click.echo(f"  - {evidence}")

    if selection.warnings:
        click.echo("警告:")
        for warning in selection.warnings:
            click.echo(f"  - {warning}")
