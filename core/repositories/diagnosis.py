"""诊断记录的版本化、原子持久化。"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.executors.base import ExecutionReport
from core.models import Diagnosis


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(api[_-]?key|token|password|secret)"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/-]+"),
)


def redact_sensitive_text(value: str) -> str:
    """对报告字段做保守脱敏并限制体积。"""
    redacted = value
    redacted = _SECRET_PATTERNS[0].sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )
    redacted = _SECRET_PATTERNS[1].sub(
        "Bearer [REDACTED]",
        redacted,
    )
    if len(redacted) > 4000:
        return f"{redacted[:4000]}\n[TRUNCATED]"
    return redacted


def _redact_data(value: object) -> object:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        return [
            _redact_data(item)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _redact_data(item)
            for key, item in value.items()
        }
    return value


def _serialize_report(report: ExecutionReport) -> dict[str, object]:
    environment = report.environment
    return {
        "exit_code": report.exit_code,
        "timed_out": report.timed_out,
        "error_type": report.error_type,
        "stdout": redact_sensitive_text(report.stdout),
        "stderr": redact_sensitive_text(report.stderr),
        "environment": (
            {
                "runner": environment.runner,
                "runtime": environment.runtime,
                "runtime_version": environment.runtime_version,
                "working_directory": (
                    environment.working_directory
                ),
            }
            if environment is not None
            else None
        ),
        "test_results": [
            {
                "name": result.name,
                "status": result.status,
                "duration": result.duration,
                "message": redact_sensitive_text(
                    result.message
                ),
            }
            for result in report.test_results
        ],
    }


def _atomic_write_json(
    path: Path,
    data: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


class DiagnosisRepository:
    """保存并读取目标项目的诊断历史。"""

    SCHEMA_VERSION = 1

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.diagnosis_dir = (
            self.project_root
            / ".autotest"
            / "diagnoses"
        )

    def save(
        self,
        *,
        diagnosis: Diagnosis,
        execution_reports: tuple[
            ExecutionReport,
            ...,
        ],
        reproduction_command: str,
        git_sha: str | None = None,
        dependency_digest: str | None = None,
        created_at: datetime | None = None,
    ) -> Path:
        if not isinstance(diagnosis, Diagnosis):
            raise ValueError("diagnosis 必须是 Diagnosis")
        if (
            not isinstance(reproduction_command, str)
            or not reproduction_command.strip()
        ):
            raise ValueError("reproduction_command 不能为空")

        timestamp = created_at or datetime.now(timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        record = {
            "schema_version": self.SCHEMA_VERSION,
            "created_at": timestamp.isoformat(),
            "git_sha": git_sha,
            "dependency_digest": dependency_digest,
            "reproduction_command": redact_sensitive_text(
                reproduction_command.strip()
            ),
            "diagnosis": _redact_data(
                diagnosis.to_dict()
            ),
            "execution_reports": [
                _serialize_report(report)
                for report in execution_reports
            ],
        }
        filename = (
            timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
            + ".json"
        )
        history_path = self.diagnosis_dir / filename
        _atomic_write_json(history_path, record)
        _atomic_write_json(
            self.diagnosis_dir / "latest.json",
            record,
        )
        return history_path

    def load_latest(self) -> dict[str, object] | None:
        latest_path = self.diagnosis_dir / "latest.json"
        if not latest_path.is_file():
            return None
        data = json.loads(
            latest_path.read_text(encoding="utf-8")
        )
        if (
            not isinstance(data, dict)
            or data.get("schema_version")
            != self.SCHEMA_VERSION
        ):
            raise ValueError("不支持的诊断记录格式")
        Diagnosis.from_dict(data["diagnosis"])
        return data
