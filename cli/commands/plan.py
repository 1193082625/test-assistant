"""查看、批准或拒绝 TestSpec"""
import json
import click
from pathlib import Path

from core.analyzers.contract import (
    extract_python_contract_evidence,
)
from core.analyzers.source import (
    analyze_python_symbols,
    classify_symbol_testability,
)
from core.llm.client import LLMClient
from core.models import PlannerStatus, TestabilityStatus
from core.planners.test_spec import plan_test_spec
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


@plan.command("propose")
@click.argument("target_symbol")
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
    "--source-path",
    required=True,
    type=click.Path(
        dir_okay=False,
        path_type=Path,
    ),
    help="源码相对于项目根目录的路径",
)
@click.option(
    "--module-path",
    required=True,
    help="源码模块导入路径，例如 package.demo",
)
@click.option(
    "--model",
    default="deepseek-chat",
    show_default=True,
    help="规划 TestSpec 使用的模型",
)
def propose_spec(
    target_symbol: str,
    project_path: Path,
    source_path: Path,
    module_path: str,
    model: str,
) -> None:
    """根据源码符号和契约证据提议 TestSpec。"""
    root = project_path.resolve()
    resolved_source = (root / source_path).resolve()
    try:
        resolved_source.relative_to(root)
    except ValueError as error:
        raise click.ClickException(
            "source-path 必须位于目标项目内"
        ) from error
    if not resolved_source.is_file():
        raise click.ClickException(
            f"未找到源码文件: {source_path}"
        )
    if not module_path.strip():
        raise click.ClickException("module-path 不能为空")

    try:
        symbols = analyze_python_symbols(
            str(resolved_source),
            module_path,
        )
        symbol = next(
            item
            for item in symbols
            if item.qualified_name == target_symbol
        )
    except StopIteration as error:
        raise click.ClickException(
            f"源码中未找到目标符号: {target_symbol}"
        ) from error
    except (OSError, SyntaxError, ValueError) as error:
        raise click.ClickException(
            f"无法分析源码: {error}"
        ) from error

    testability = classify_symbol_testability(symbol)
    if testability.status is TestabilityStatus.NOT_DIRECT:
        reasons = "；".join(testability.reasons)
        raise click.ClickException(
            f"目标符号不可直接测试: {reasons}"
        )

    try:
        evidence = [
            item
            for item in extract_python_contract_evidence(
                str(resolved_source),
                module_path,
            )
            if (
                item.symbol_qualified_name
                == target_symbol
            )
        ]
        result = plan_test_spec(
            llm=LLMClient(model=model),
            symbol=symbol,
            testability=testability,
            evidence=evidence,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(
            f"TestSpec 规划失败: {error}"
        ) from error

    if result.status is not PlannerStatus.SUCCESS:
        details = "；".join(result.errors) or result.status.value
        raise click.ClickException(
            f"TestSpec 规划失败: {details}"
        )
    if result.spec is None:
        raise click.ClickException(
            "TestSpec 规划成功但没有返回 spec"
        )

    saved_path = _repository_for(project_path).save(
        result.spec
    )
    click.echo(
        f"已提议 TestSpec: {result.spec.id}"
    )
    click.echo(f"状态: {result.spec.status.value}")
    click.echo(
        "证据强度: "
        f"{result.spec.expectation_strength.value}"
    )
    click.echo(f"保存位置: {saved_path}")

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
