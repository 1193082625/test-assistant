"""查看项目检测证据与能力"""

# inspect 检查

from pathlib import Path
import click
import yaml

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
