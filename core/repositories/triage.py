"""脱敏、限长的 pytest triage 运行记录仓库。"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from core.models import TriageResult

from .diagnosis import redact_sensitive_text


_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class TriageRepository:
    """在目标项目的隔离目录中保存版本化 triage 记录。"""

    SCHEMA_VERSION = 1
    ISSUE_TEXT_LIMIT = 2_000
    STREAM_TEXT_LIMIT = 4_000

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.triage_dir = self.project_root / ".autotest" / "triage"

    def _record_path(self, run_id: object) -> Path:
        if (
            not isinstance(run_id, str)
            or _RUN_ID_PATTERN.fullmatch(run_id) is None
        ):
            raise ValueError("Triage run_id 包含不安全字符")
        return self.triage_dir / f"{run_id}.json"

    def _sanitize(
        self,
        value: str,
        *,
        limit: int,
    ) -> tuple[str, bool]:
        without_root = value.replace(
            str(self.project_root),
            "<project-root>",
        )
        redacted = redact_sensitive_text(without_root)
        was_truncated = (
            len(without_root) > 4_000
            or len(redacted) > limit
        )
        if len(redacted) > limit:
            redacted = f"{redacted[:limit]}\n[TRUNCATED]"
        return redacted, was_truncated

    def _sanitize_object(
        self,
        value: object,
        *,
        field: str,
        truncated_fields: list[str],
        limit: int,
    ) -> object:
        if isinstance(value, str):
            sanitized, truncated = self._sanitize(value, limit=limit)
            if truncated:
                truncated_fields.append(field)
            return sanitized
        if isinstance(value, list):
            return [
                self._sanitize_object(
                    item,
                    field=f"{field}[{index}]",
                    truncated_fields=truncated_fields,
                    limit=limit,
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, dict):
            return {
                key: self._sanitize_object(
                    item,
                    field=f"{field}.{key}",
                    truncated_fields=truncated_fields,
                    limit=limit,
                )
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def save(
        self,
        *,
        result: TriageResult,
        diagnosis_references: tuple[str, ...],
        reproduction_commands: Mapping[str, str],
        git_sha: str | None = None,
        dependency_digest: str | None = None,
        git_history_audit: Mapping[str, object] | None = None,
        created_at: datetime | None = None,
    ) -> Path:
        """保存不可覆盖的版本记录，并原子更新 latest。"""
        if not isinstance(result, TriageResult):
            raise ValueError("result 必须是 TriageResult")
        target_path = self._record_path(result.run_id)
        if target_path.exists():
            raise FileExistsError("Triage run_id 已存在")
        if len(diagnosis_references) != len(result.diagnoses):
            raise ValueError("诊断引用数量必须与 diagnoses 一致")

        timestamp = (created_at or datetime.now(timezone.utc)).astimezone(
            timezone.utc
        )
        truncated_fields: list[str] = []
        report = result.report
        stdout, stdout_truncated = self._sanitize(
            report.stdout,
            limit=self.STREAM_TEXT_LIMIT,
        )
        stderr, stderr_truncated = self._sanitize(
            report.stderr,
            limit=self.STREAM_TEXT_LIMIT,
        )
        if stdout_truncated:
            truncated_fields.append("pytest.stdout")
        if stderr_truncated:
            truncated_fields.append("pytest.stderr")

        clusters = self._sanitize_object(
            [cluster.to_dict() for cluster in result.clusters],
            field="clusters",
            truncated_fields=truncated_fields,
            limit=self.ISSUE_TEXT_LIMIT,
        )
        commands = self._sanitize_object(
            dict(reproduction_commands),
            field="reproduction_commands",
            truncated_fields=truncated_fields,
            limit=self.STREAM_TEXT_LIMIT,
        )
        references = self._sanitize_object(
            list(diagnosis_references),
            field="diagnosis_references",
            truncated_fields=truncated_fields,
            limit=self.STREAM_TEXT_LIMIT,
        )
        git_history = self._sanitize_object(
            dict(git_history_audit or {}),
            field="git_history",
            truncated_fields=truncated_fields,
            limit=self.ISSUE_TEXT_LIMIT,
        )
        status_counts: dict[str, int] = {}
        for test_result in report.test_results:
            status_counts[test_result.status] = (
                status_counts.get(test_result.status, 0) + 1
            )
        environment = report.environment
        environment_payload = None
        if environment is not None:
            working_directory = environment.working_directory
            if working_directory is not None:
                working_directory, _ = self._sanitize(
                    working_directory,
                    limit=self.STREAM_TEXT_LIMIT,
                )
            environment_payload = {
                "runner": environment.runner,
                "runtime": environment.runtime,
                "runtime_version": environment.runtime_version,
                "working_directory": working_directory,
            }

        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": result.run_id,
            "created_at": timestamp.isoformat(),
            "git_sha": git_sha,
            "dependency_digest": dependency_digest,
            "pytest": {
                "exit_code": report.exit_code,
                "timed_out": report.timed_out,
                "error_type": report.error_type,
                "status_counts": status_counts,
                "environment": environment_payload,
                "stdout": stdout,
                "stderr": stderr,
            },
            "clusters": clusters,
            "diagnosis_references": references,
            "reproduction_commands": commands,
            "git_history": git_history,
            "truncation": {
                "occurred": bool(truncated_fields),
                "fields": sorted(set(truncated_fields)),
                "issue_text_limit": self.ISSUE_TEXT_LIMIT,
                "stream_text_limit": self.STREAM_TEXT_LIMIT,
            },
        }
        self._atomic_write(target_path, payload)
        self._atomic_write(self.triage_dir / "latest.json", payload)
        return target_path

    def _load_path(self, path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Triage 记录 JSON 已损坏") from error
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != self.SCHEMA_VERSION
            or not isinstance(payload.get("run_id"), str)
            or not isinstance(payload.get("pytest"), dict)
            or not isinstance(payload.get("clusters"), list)
        ):
            raise ValueError("不支持的 Triage 记录格式")
        return payload

    def load(self, run_id: str) -> dict[str, object]:
        return self._load_path(self._record_path(run_id))

    def load_latest(self) -> dict[str, object] | None:
        latest_path = self.triage_dir / "latest.json"
        if not latest_path.is_file():
            return None
        return self._load_path(latest_path)
