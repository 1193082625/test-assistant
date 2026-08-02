"""目标项目的本地 Git 只读授权记录。"""

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def git_repository_identity(project_root: str | Path) -> str | None:
    """读取最小仓库身份，不读取提交历史。"""
    root = Path(project_root).resolve()
    values: list[str] = []
    for argument in ("--show-toplevel", "--git-common-dir"):
        try:
            completed = subprocess.run(
                ["git", "rev-parse", argument],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        reported = Path(completed.stdout.strip())
        if not reported.is_absolute():
            reported = root / reported
        values.append(str(reported.resolve()))
    canonical = "\n".join(values)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GitPermissionRepository:
    """原子保存按仓库身份绑定的本地历史读取授权。"""

    SCHEMA_VERSION = 1

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.path = self.project_root / ".autotest" / "permissions.json"

    def grant(self, *, approved_at: datetime | None = None) -> None:
        identity = git_repository_identity(self.project_root)
        if identity is None:
            raise ValueError("目标路径不是可识别的本地 Git 仓库")
        timestamp = (approved_at or datetime.now(timezone.utc)).astimezone(
            timezone.utc
        )
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "git_history": {
                "enabled": True,
                "scope": "local_read_only",
                "repository_identity": identity,
                "approved_at": timestamp.isoformat(),
            },
        }
        self._atomic_write(payload)

    def is_granted(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Git 授权记录 JSON 已损坏") from error
        entry = payload.get("git_history") if isinstance(payload, dict) else None
        if (
            payload.get("schema_version") != self.SCHEMA_VERSION
            or not isinstance(entry, dict)
            or entry.get("scope") != "local_read_only"
            or entry.get("enabled") is not True
            or not isinstance(entry.get("repository_identity"), str)
        ):
            raise ValueError("不支持的 Git 授权记录格式")
        current = git_repository_identity(self.project_root)
        return current is not None and current == entry["repository_identity"]

    def _atomic_write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=".permissions.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
