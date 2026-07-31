from datetime import datetime, timezone

from click.testing import CliRunner

from cli.main import cli
from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
)
from core.models import (
    Diagnosis,
    DiagnosisAction,
    DiagnosisActionKind,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidence,
    DiagnosisEvidenceKind,
)
from core.repositories import DiagnosisRepository


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        summary="Runner 启动失败",
        category=DiagnosisCategory.INFRA_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=(
            DiagnosisEvidence(
                kind=DiagnosisEvidenceKind.RUNNER,
                description="pytest 无法启动",
                source="execution_report",
                details=(
                    "exit_code=2",
                    "api_key=diagnosis-secret",
                ),
            ),
        ),
        suggested_actions=(
            DiagnosisAction(
                kind=(
                    DiagnosisActionKind
                    .FIX_INFRASTRUCTURE
                ),
                description="检查 pytest 环境",
            ),
        ),
    )


def test_repository_saves_versioned_and_latest_record(tmp_path):
    repository = DiagnosisRepository(tmp_path)
    report = ExecutionReport(
        exit_code=2,
        error_type="runner_error",
        stderr="token=super-secret",
        environment=ExecutionEnvironment(
            runner="pytest",
            runtime="python",
            runtime_version="3.13.5",
            working_directory=str(tmp_path),
        ),
    )

    saved_path = repository.save(
        diagnosis=_diagnosis(),
        execution_reports=(report,),
        reproduction_command=(
            "python -m pytest tests/test_demo.py -q "
            "--token=command-secret"
        ),
        git_sha="abc123",
        dependency_digest="sha256:deps",
        created_at=datetime(
            2026,
            7,
            31,
            tzinfo=timezone.utc,
        ),
    )

    assert saved_path.is_file()
    assert saved_path.name.startswith("20260731T000000")
    record = repository.load_latest()
    assert record is not None
    assert record["schema_version"] == 1
    assert record["git_sha"] == "abc123"
    serialized = str(record)
    assert "super-secret" not in serialized
    assert "diagnosis-secret" not in serialized
    assert "command-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_report_command_generates_redacted_markdown(tmp_path):
    DiagnosisRepository(tmp_path).save(
        diagnosis=_diagnosis(),
        execution_reports=(
            ExecutionReport(
                exit_code=2,
                error_type="runner_error",
                stderr="password=hunter2",
            ),
        ),
        reproduction_command=(
            "python -m pytest tests/test_demo.py -q"
        ),
    )
    output_path = tmp_path / "report.md"

    result = CliRunner().invoke(
        cli,
        [
            "report",
            "--path",
            str(tmp_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    content = output_path.read_text(encoding="utf-8")
    assert "Runner 启动失败" in content
    assert "python -m pytest" in content
    assert "hunter2" not in content
