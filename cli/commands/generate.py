"""从已批准 TestSpec 生成并审阅候选测试"""
from pathlib import Path

import click

from core.models import TestSpecStatus
from core.optional_dependencies import (
    OptionalDependencyError,
    require_optional_modules,
)
from core.repositories.test_spec import TestSpecRepository
from core.workflows.candidate import (
    CandidateCommitStatus,
    CandidatePreparationStatus,
    commit_reviewed_candidate,
    prepare_candidate_for_review,
)


# 保留为可注入接缝，避免测试需要安装或调用真实 LLM。
LLMClient = None


def _llm_client_type():
    if LLMClient is not None:
        return LLMClient
    require_optional_modules(
        extra="llm",
        capability="generate",
        modules=(
            "dotenv",
            "langchain_core",
            "langchain_openai",
        ),
    )
    from core.llm.client import LLMClient as client_type

    return client_type


@click.command("generate")
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
    "--module-path",
    required=True,
    help="源码模块导入路径，例如 package.demo",
)
@click.option(
    "--source-path",
    "source_relative_path",
    required=True,
    help="源码相对于项目根目录的路径",
)
@click.option(
    "--test-filename",
    required=True,
    help="正式测试文件名",
)
@click.option(
    "--model",
    default="deepseek-chat",
    show_default=True,
    help="生成候选测试使用的模型",
)
def generate_command(
    spec_id: str,
    project_path: Path,
    module_path: str,
    source_relative_path: str,
    test_filename: str,
    model: str,
) -> None:
    """从指定 TestSpec 生成候选测试"""
    repository = TestSpecRepository(
        project_root=str(project_path.resolve()),
    )

    try:
        spec = repository.get(spec_id)
    except FileNotFoundError as error:
        raise click.ClickException(
            f"未找到 TestSpec: {spec_id}"
        ) from error

    if spec.status is not TestSpecStatus.APPROVED:
        raise click.ClickException(
            "只有 approved TestSpec 可以生成候选测试"
        )

    try:
        llm_client_type = _llm_client_type()
    except OptionalDependencyError as error:
        raise click.UsageError(str(error)) from error

    llm = llm_client_type(model=model)

    preparation = prepare_candidate_for_review(
        project_root=project_path,
        llm=llm,
        spec=spec,
        module_path=module_path,
        source_relative_path=source_relative_path,
        test_filename=test_filename,
        generator_model=model,
        template_version="v1",
    )

    if (
        preparation.status
        is not CandidatePreparationStatus.READY_FOR_REVIEW
    ):
        details = "；".join(preparation.errors)
        raise click.ClickException(
            (
                "候选准备失败"
                f" [{preparation.stage.value}]: "
                f"{details}"
            )
        )

    if preparation.diff is None:
        raise click.ClickException(
            "候选准备成功但没有生成 diff"
        )

    click.echo("候选测试已通过验证：")
    click.echo(preparation.diff.text)

    if not click.confirm(
        "提交以上候选测试？",
        default=False,
    ):
        click.echo(
            "已取消提交，正式测试未改变"
        )
        return

    commit_result = commit_reviewed_candidate(
        project_root=project_path,
        reviewed_diff=preparation.diff,
    )

    if commit_result.status is not CandidateCommitStatus.COMMITTED:
        details = "；".join(commit_result.errors)
        raise click.ClickException(
            (
                "候选提交失败"
                f" [{commit_result.stage.value}]: "
                f"{details}"
            )
        )

    if commit_result.final_path is None:
        raise click.ClickException(
            "候选提交成功但没有返回正式文件路径"
        )

    click.echo(
        f"已提交正式测试：{commit_result.final_path}"
    )
