from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.generators.test_spec import (
    GeneratorLLM,
    generate_test_candidate,
)
from core.models import TestSpec
from core.repositories import (
    CandidateDiff,
    CandidateRepository,
)
from core.validators import (
    CandidateValidationResult,
    check_pytest_runner_health,
    collect_pytest_candidate,
    execute_pytest_candidate_isolated,
    validate_python_candidate,
)


class CandidatePreparationStatus(StrEnum):
    READY_FOR_REVIEW = "ready_for_review"
    FAILED = "failed"


class CandidatePreparationStage(StrEnum):
    GENERATE = "generate"
    SAVE = "save"
    STATIC_VALIDATION = "static_validation"
    COLLECTION = "collection"
    RUNNER_HEALTH = "runner_health"
    ISOLATED_EXECUTION = "isolated_execution"
    BUILD_DIFF = "build_diff"


class CandidateCommitStatus(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"


class CandidateCommitStage(StrEnum):
    APPROVE_DIFF = "approve_diff"
    COMMIT = "commit"


@dataclass(frozen=True)
class CandidatePreparationResult:
    status: CandidatePreparationStatus
    stage: CandidatePreparationStage
    candidate_path: Path | None = None
    validation_results: tuple[CandidateValidationResult, ...] = ()
    diff: CandidateDiff | None = None
    errors: tuple[str, ...] = ()

@dataclass(frozen=True)
class CandidateCommitResult:
    status: CandidateCommitStatus
    stage: CandidateCommitStage
    final_path: Path | None = None
    errors: tuple[str, ...] = ()

def _failed_result(
        *,
        stage: CandidatePreparationStage,
        candidate_path: Path | None = None,
        validation_results: tuple[CandidateValidationResult, ...] = (),
        errors: tuple[str, ...],
) -> CandidatePreparationResult:
    """构造候选准备流程的结构化失败结果"""
    return CandidatePreparationResult(
        status=CandidatePreparationStatus.FAILED,
        stage=stage,
        candidate_path=candidate_path,
        validation_results=validation_results,
        errors=errors,
    )

def prepare_candidate_for_review(
        *,
        project_root: str | Path,
        llm: GeneratorLLM,
        spec: TestSpec,
        module_path: str,
        source_relative_path: str,
        test_filename: str,
        generator_model: str,
        template_version: str,
) -> CandidatePreparationResult:
    """将已批准 TestSpec 准备为待审阅候选 diff"""
    root = Path(project_root).resolve()
    repository = CandidateRepository(root)

    try:
        candidate_content= generate_test_candidate(
            llm=llm,
            spec=spec,
            module_path=module_path,
        )
    except ValueError as error:
        return _failed_result(
            stage=CandidatePreparationStage.GENERATE,
            errors=(str(error),),
        )

    try:
        candidate_path = repository.save(
            spec_id=spec.id,
            source_relative_path=source_relative_path,
            test_filename=test_filename,
            content=candidate_content,
            generator_model=generator_model,
            template_version=template_version,
        )
    except (OSError, ValueError) as error:
        return _failed_result(
            stage=CandidatePreparationStage.SAVE,
            errors=(str(error),),
        )

    validation_results: list[
        CandidateValidationResult
    ] = []

    static_result = validate_python_candidate(
        candidate_content,
        project_root=root,
    )
    validation_results.append(static_result)

    if not static_result.passed:
        return _failed_result(
            stage=CandidatePreparationStage.STATIC_VALIDATION,
            candidate_path=candidate_path,
            validation_results=tuple(validation_results),
            errors=static_result.errors,
        )

    collection_result = collect_pytest_candidate(
        candidate_path=candidate_path,
        project_root=root,
    )
    validation_results.append(collection_result)

    if not collection_result.passed:
        return _failed_result(
            stage=CandidatePreparationStage.COLLECTION,
            candidate_path=candidate_path,
            validation_results=tuple(validation_results),
            errors=collection_result.errors,
        )

    runner_result = check_pytest_runner_health(
        project_root=root,
    )
    validation_results.append(runner_result)

    if not runner_result.passed:
        return _failed_result(
            stage=CandidatePreparationStage.RUNNER_HEALTH,
            candidate_path=candidate_path,
            validation_results=tuple(validation_results),
            errors=runner_result.errors,
        )

    isolated_result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=root,
    )
    validation_results.append(isolated_result)

    # 检查测试本身是否通过，属于执行结果
    if not isolated_result.passed:
        return _failed_result(
            stage=CandidatePreparationStage.ISOLATED_EXECUTION,
            candidate_path=candidate_path,
            validation_results=tuple(validation_results),
            errors=isolated_result.errors,
        )

    # 检查即使测试通过，它是否符合安全策略，属于工作流决策
    if (
        isolated_result.side_effects
        and "filesystem" not in spec.side_effects
    ):
        return _failed_result(
            stage=CandidatePreparationStage.ISOLATED_EXECUTION,
            candidate_path=candidate_path,
            validation_results=tuple(validation_results),
            errors=(
                "候选测试产生了未声明的文件系统副作用",
            ),
        )

    try:
        candidate_diff = repository.build_diff(
            candidate_path=candidate_path,
        )
    except (OSError, ValueError) as error:
        return _failed_result(
            stage=CandidatePreparationStage.BUILD_DIFF,
            candidate_path=candidate_path,
            validation_results=tuple(validation_results),
            errors=(str(error),),
        )

    return CandidatePreparationResult(
        status=CandidatePreparationStatus.READY_FOR_REVIEW,
        stage=CandidatePreparationStage.BUILD_DIFF,
        candidate_path=candidate_path,
        validation_results=tuple(validation_results),
        diff=candidate_diff,
    )

def commit_reviewed_candidate(
        *,
        project_root: str | Path,
        reviewed_diff: CandidateDiff,
) -> CandidateCommitResult:
    """批准并提交用户已经审阅的候选 diff"""
    repository = CandidateRepository(project_root)

    try:
        approval = repository.approve_diff(
            reviewed_diff=reviewed_diff,
        )
    except (OSError, TypeError, ValueError) as error:
        return CandidateCommitResult(
            status=CandidateCommitStatus.FAILED,
            stage=CandidateCommitStage.APPROVE_DIFF,
            errors=(str(error),),
        )

    try:
        final_path = repository.commit_candidate(
            approval=approval,
        )
    except (OSError, TypeError, ValueError) as error:
        return CandidateCommitResult(
            status=CandidateCommitStatus.FAILED,
            stage=CandidateCommitStage.COMMIT,
            errors=(str(error),),
        )

    return CandidateCommitResult(
        status=CandidateCommitStatus.COMMITTED,
        stage=CandidateCommitStage.COMMIT,
        final_path=final_path,
    )