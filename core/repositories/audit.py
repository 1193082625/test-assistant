"""版本化、只读事实导向的 Audit 结果仓库"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.models import (
    AuditResult,
    AuditThresholds,
    CoverageSummary,
    QualityFinding,
    SymbolCoverage,
    ToolStatus,
)
from .diagnosis import redact_sensitive_text

_RUN_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
)


class AuditRepository:
    """将 AuditResult 保存到目标项目的隔离目录"""

    SCHEMA_VERSION = 1
    TEXT_LIMIT = 4_000

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.audit_dir = self.project_root / ".autotest" / "audits"

    def _record_path(self, run_id: object) -> Path:
        if (
            not isinstance(run_id, str)
            or _RUN_ID_PATTERN.fullmatch(run_id) is None
        ):
            raise ValueError("Audit run_id 包含不安全字符")
        return self.audit_dir / f"{run_id}.json"

    @staticmethod
    def _coverage_payload(
        coverage: CoverageSummary | None,
    ) -> dict[str, int] | None:
        if coverage is None:
            return None

        return {
            "statements_covered": coverage.statements_covered,
            "statements_total": coverage.statements_total,
            "branches_covered": coverage.branches_covered,
            "branches_total": coverage.branches_total,
        }

    @classmethod
    def _symbol_payload(
        cls,
        symbol: SymbolCoverage,
    ) -> dict[str, object]:
        return {
            "source_path": symbol.source_path,
            "qualified_name": symbol.qualified_name,
            "kind": symbol.kind,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "summary": cls._coverage_payload(symbol.summary),
            "state": symbol.state.value,
            "missing_lines": list(symbol.missing_lines),
            "missing_branches": [
                list(branch)
                for branch in symbol.missing_branches
            ],
        }

    @staticmethod
    def _finding_payload(
        finding: QualityFinding,
    ) -> dict[str, object]:
        return {
            "tool": finding.tool,
            "kind": finding.kind.value,
            "rule_code": finding.rule_code,
            "message": finding.message,
            "source_path": finding.source_path,
            "line": finding.line,
            "column": finding.column,
            "fix_available": finding.fix_available,
        }

    @staticmethod
    def _tool_payload(
        tool: ToolStatus,
    ) -> dict[str, object]:
        return {
            "tool": tool.tool,
            "state": tool.state.value,
            "version": tool.version,
            "reason": tool.reason,
        }

    @staticmethod
    def _threshold_payload(
        thresholds: AuditThresholds | None,
    ) -> dict[str, float | int | None] | None:
        if thresholds is None:
            return None
        return {
            "statement_rate": thresholds.statement_rate,
            "branch_rate": thresholds.branch_rate,
            "max_ruff_findings": thresholds.max_ruff_findings,
            "max_mypy_errors": thresholds.max_mypy_errors,
        }

    @staticmethod
    def _atomic_write(
        path: Path,
        payload: dict[str, object],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    payload,
                    stream,
                    ensure_ascii=False,
                    indent=4,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temporary_path, path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def save(
        self,
        result: AuditResult,
        *,
        created_at: datetime | None = None,
    ) -> Path:
        if not isinstance(result, AuditResult):
            raise ValueError("result 必须是 AuditResult")
        record_path = self._record_path(result.run_id)
        if record_path.exists():
            raise FileExistsError("Audit run_id 已存在")

        timestamp = (
            created_at or datetime.now(timezone.utc)
        ).astimezone(timezone.utc)
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": result.run_id,
            "created_at": timestamp.isoformat(),
            "status": result.status.value,
            "command": list(result.command),
            "source_digest": result.source_digest,
            "thresholds": self._threshold_payload(result.thresholds),
            "coverage": self._coverage_payload(
                result.coverage
            ),
            "symbols": [
                self._symbol_payload(symbol)
                for symbol in result.symbols
            ],
            "findings": [
                self._finding_payload(finding)
                for finding in result.findings
            ],
            "tools": [
                self._tool_payload(tool)
                for tool in result.tools
            ],
        }

        truncated_fields: list[str] = []
        safe_payload = self._sanitize_object(
            payload,
            field="",
            truncated_fields=truncated_fields,
        )

        if not isinstance(safe_payload, dict):
            raise ValueError("Audit payload 必须是对象")

        safe_payload["truncation"] = {
            "occurred": bool(truncated_fields),
            "fields": sorted(set(truncated_fields)),
            "text_limit": self.TEXT_LIMIT,
        }

        self._atomic_write(record_path, safe_payload)

        try:
            self._atomic_write(
                self.audit_dir / "latest.json",
                safe_payload,
            )
        except BaseException:
            record_path.unlink(missing_ok=True)
            raise

        return record_path

    @classmethod
    def _load_path(
        cls,
        path: Path,
    ) -> dict[str, object]:
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                "Audit 记录 JSON 已损坏"
            ) from error

        if (
            not isinstance(payload, dict)
            or payload.get("schema_version")
            != cls.SCHEMA_VERSION
            or not isinstance(payload.get("run_id"), str)
            or not isinstance(payload.get("created_at"), str)
            or not isinstance(payload.get("status"), str)
            or not isinstance(payload.get("command"), list)
            or not isinstance(
                payload.get("source_digest"),
                str,
            )
            or (
                payload.get("thresholds") is not None
                and not isinstance(payload.get("thresholds"), dict)
            )
            or (
                payload.get("coverage") is not None
                and not isinstance(payload.get("coverage"), dict)
            )
            or not isinstance(payload.get("symbols"), list)
            or not isinstance(payload.get("findings"), list)
            or not isinstance(payload.get("tools"), list)
        ):
            raise ValueError(
                "不支持的 Audit 记录格式"
            )

        return payload

    def load(self, run_id: str) -> dict[str, object]:
        return self._load_path(self._record_path(run_id))

    def load_latest(self) -> dict[str, object] | None:
        latest_path = self.audit_dir / "latest.json"
        if not latest_path.is_file():
            return None

        return self._load_path(latest_path)

    def _sanitize_text(self, value: str) -> tuple[str, bool]:
        without_root = value.replace(
            str(self.project_root),
            "<project-root>",
        )
        redacted = redact_sensitive_text(without_root)

        if len(redacted) <= self.TEXT_LIMIT:
            return redacted, False

        return (
            f"{redacted[:self.TEXT_LIMIT]}\n[TRUNCATED]",
            True,
        )

    def _sanitize_object(
        self,
        value: object,
        *,
        field: str,
        truncated_fields: list[str],
    ) -> object:
        if isinstance(value, str):
            sanitized, truncated = self._sanitize_text(value)
            if truncated:
                truncated_fields.append(field)
            return sanitized

        if isinstance(value, list):
            return [
                self._sanitize_object(
                    item,
                    field=f"{field}[{index}]",
                    truncated_fields=truncated_fields,
                )
                for index, item in enumerate(value)
            ]

        if isinstance(value, dict):
            sanitized_dict: dict[str, object] = {}

            for key, item in value.items():
                child_field = (
                    f"{field}.{key}"
                    if field
                    else key
                )
                sanitized_dict[key] = self._sanitize_object(
                    item,
                    field=child_field,
                    truncated_fields=truncated_fields,
                )

            return sanitized_dict

        return value
