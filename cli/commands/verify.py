"""验证已批准 TestSpec 对应的正式 pytest 节点。"""

from pathlib import Path

import click

from core.executors import PytestExecutor
from core.models import TestSpecStatus
from core.repositories import TestSpecRepository
from core.validators import (
    check_pytest_runner_health,
    collect_pytest_candidate,
    validate_python_candidate,
)
from core.workflows import (
    VerificationStatus,
    build_reproduction_command,
    verify_test_spec,
)


def _project_file(
    *,
    root: Path,
    relative_path: str,
    label: str,
) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise click.ClickException(f"{label} 不能为空")
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise click.ClickException(
            f"{label} 必须位于目标项目内"
        ) from error
    if not resolved.is_file():
        raise click.ClickException(
            f"未找到 {label}: {relative_path}"
        )
    return resolved


@click.command("verify")
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
@click.option(
    "--test-node",
    required=True,
    help="精确 pytest node，例如 tests/test_demo.py::test_add",
)
@click.option(
    "--source-path",
    required=True,
    help="目标源码相对于项目根目录的路径",
)
def verify_command(
    spec_id: str,
    project_path: Path,
    test_node: str,
    source_path: str,
) -> None:
    """运行门禁、三次复跑并保存失败诊断。"""
    root = project_path.resolve()
    repository = TestSpecRepository(str(root))
    try:
        spec = repository.get(spec_id)
    except FileNotFoundError as error:
        raise click.ClickException(
            f"未找到 TestSpec: {spec_id}"
        ) from error
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    if spec.status is not TestSpecStatus.APPROVED:
        raise click.ClickException(
            "只有 approved TestSpec 可以验证"
        )

    test_path_text, separator, test_symbol = (
        test_node.partition("::")
    )
    if not separator or not test_symbol.strip():
        raise click.ClickException(
            "test-node 必须包含精确测试符号"
        )
    test_path = _project_file(
        root=root,
        relative_path=test_path_text,
        label="测试文件",
    )
    _project_file(
        root=root,
        relative_path=source_path,
        label="源码文件",
    )
    relative_test_node = (
        f"{test_path.relative_to(root).as_posix()}"
        f"::{test_symbol}"
    )

    validation_results = []
    static_result = validate_python_candidate(
        test_path.read_text(encoding="utf-8"),
        project_root=root,
    )
    validation_results.append(static_result)
    if static_result.passed:
        runner_result = check_pytest_runner_health(
            project_root=root
        )
        validation_results.append(runner_result)
        if runner_result.passed:
            collection_result = collect_pytest_candidate(
                candidate_path=relative_test_node,
                project_root=root,
            )
            validation_results.append(collection_result)

    result = verify_test_spec(
        project_root=root,
        spec=spec,
        test_node_id=relative_test_node,
        source_path=source_path,
        validation_results=tuple(validation_results),
        executor=PytestExecutor(cwd=str(root)),
    )

    if result.status is VerificationStatus.PASSED:
        click.echo("验证通过：目标测试连续 3 次通过")
        click.echo(
            "复现命令: "
            f"{build_reproduction_command(relative_test_node)}"
        )
        return

    if result.diagnosis is None or result.record_path is None:
        raise click.ClickException(
            "验证失败但没有生成诊断记录"
        )
    click.echo(
        "诊断: "
        f"{result.diagnosis.category.value}"
    )
    click.echo(
        "置信度: "
        f"{result.diagnosis.confidence.value}"
    )
    click.echo(f"摘要: {result.diagnosis.summary}")
    click.echo(f"诊断记录: {result.record_path}")
    click.echo(
        "复现命令: "
        f"{build_reproduction_command(relative_test_node)}"
    )
    raise click.exceptions.Exit(1)
