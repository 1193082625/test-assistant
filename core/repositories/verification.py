"""最近一次验证状态的原子持久化。"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class VerificationStateRepository:
    """保存当前健康状态，同时不删除诊断历史。"""

    SCHEMA_VERSION = 1

    def __init__(self, project_root: str | Path):
        self.path = (
            Path(project_root).resolve()
            / ".autotest"
            / "verification"
            / "latest.json"
        )

    def save(
        self,
        *,
        status: str,
        reproduction_command: str,
        category: str | None = None,
        confidence: str | None = None,
        diagnosis_record: str | None = None,
    ) -> None:
        if status not in {"passed", "diagnosed"}:
            raise ValueError("不支持的验证状态")
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "verified_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": status,
            "category": category,
            "confidence": confidence,
            "diagnosis_record": diagnosis_record,
            "reproduction_command": reproduction_command,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=".latest.",
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
                    payload,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def load(self) -> dict[str, object] | None:
        if not self.path.is_file():
            return None
        payload = json.loads(
            self.path.read_text(encoding="utf-8")
        )
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version")
            != self.SCHEMA_VERSION
        ):
            raise ValueError("不支持的验证状态格式")
        return payload
