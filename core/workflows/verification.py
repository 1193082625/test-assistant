"""已批准 TestSpec 的确定性验证闭环。"""

import hashlib
import shlex
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from core.diagnosticians import (
    diagnose_stable_failure,
    repeat_test_execution,
)
from core.executors.base import ExecutionReport
from core.models import Diagnosis, TestSpec, TestSpecStatus
from core.repositories import (
    DiagnosisRepository,
    VerificationStateRepository,
)
from core.validators import CandidateValidationResult


class VerificationStatus(StrEnum):
    PASSED = "passed"
    DIAGNOSED = "diagnosed"


class VerificationExecutor(Protocol):
    def execute(
        self,
        file_path: str,
    ) -> ExecutionReport:
        ...


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    reports: tuple[ExecutionReport, ...]
    diagnosis: Diagnosis | None = None
    record_path: Path | None = None


def read_git_sha(project_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def build_dependency_digest(project_root: Path) -> str | None:
    dependency_files = (
        "poetry.lock",
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
    )
    digest = hashlib.sha256()
    found = False
    for filename in dependency_files:
        path = project_root / filename
        if not path.is_file():
            continue
        found = True
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return (
        f"sha256:{digest.hexdigest()}"
        if found
        else None
    )


def build_reproduction_command(
    test_node_id: str,
) -> str:
    return (
        "python -m pytest "
        f"{shlex.quote(test_node_id)} -q"
    )


def verify_test_spec(
    *,
    project_root: str | Path,
    spec: TestSpec,
    test_node_id: str,
    source_path: str,
    validation_results: tuple[
        CandidateValidationResult,
        ...,
    ],
    executor: VerificationExecutor,
) -> VerificationResult:
    """执行门禁、精确复跑、归因并保存失败诊断。"""
    if not isinstance(spec, TestSpec):
        raise ValueError("spec 必须是 TestSpec")
    if spec.status is not TestSpecStatus.APPROVED:
        raise ValueError(
            "只有 approved TestSpec 可以验证"
        )

    gates_passed = (
        bool(validation_results)
        and all(
            result.passed
            for result in validation_results
        )
    )
    reports: tuple[ExecutionReport, ...] = ()
    reproduction_command = build_reproduction_command(
        test_node_id
    )
    if gates_passed:
        reports = repeat_test_execution(
            executor=executor,
            test_node_id=test_node_id,
            attempts=3,
        )
        if all(report.successful for report in reports):
            VerificationStateRepository(
                project_root
            ).save(
                status=VerificationStatus.PASSED.value,
                reproduction_command=(
                    reproduction_command
                ),
            )
            return VerificationResult(
                status=VerificationStatus.PASSED,
                reports=reports,
            )

    diagnosis = diagnose_stable_failure(
        spec=spec,
        reports=reports,
        validation_results=validation_results,
        test_node_id=test_node_id,
        source_path=source_path,
    )
    root = Path(project_root).resolve()
    record_path = DiagnosisRepository(root).save(
        diagnosis=diagnosis,
        execution_reports=reports,
        reproduction_command=reproduction_command,
        git_sha=read_git_sha(root),
        dependency_digest=build_dependency_digest(root),
    )
    VerificationStateRepository(root).save(
        status=VerificationStatus.DIAGNOSED.value,
        reproduction_command=reproduction_command,
        category=diagnosis.category.value,
        confidence=diagnosis.confidence.value,
        diagnosis_record=str(record_path),
    )
    return VerificationResult(
        status=VerificationStatus.DIAGNOSED,
        reports=reports,
        diagnosis=diagnosis,
        record_path=record_path,
    )
