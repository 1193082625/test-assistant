"""TestSpec 的版本话 JSON repository"""

import json
import os
import re
import tempfile
from pathlib import Path
from core.models import TestSpec, TestSpecStatus
from dataclasses import replace

TEST_SPEC_FORMAT_VERSION = 1
TEST_SPEC_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

class TestSpecRepository:
    """在项目 .autotest/plans 中保存 TestSpec"""

    def __init__(self, project_root: str) -> None:
        # .resolve() 把路径转换成规范化的绝对路径。
        self.project_root = Path(project_root).resolve()
        self.plans_path = (self.project_root / ".autotest" / "plans")

    def _spec_path(self, spec_id: str) -> Path:
        """
        校验 TestSpec ID 并返回其存储路径

        ID只能包含字母、数字、下划线和连字符
        且必须以字母或数字开头
        """
        if (
            not isinstance(spec_id, str)
            or TEST_SPEC_ID_PATTERN.fullmatch(spec_id) is None
        ):
            raise ValueError(
                "TestSpec id 包含不安全字符"
            )
        return (
            self.plans_path / f"{spec_id}.json"
        )

    def save(self, spec: TestSpec) -> Path:
        """原子保存单个 TestSpec"""
        self.plans_path.mkdir(parents=True, exist_ok=True)

        target_path = self._spec_path(spec.id)
        # temporary 临时的
        temporary_path = None

        payload = {
            "version": TEST_SPEC_FORMAT_VERSION,
            "spec": spec.to_dict(),
        }

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.plans_path,
                prefix=f".{spec.id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(payload, temporary_file, ensure_ascii=False, indent=4)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target_path)
        except Exception:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()
            raise

        return target_path

    def get(self, spec_id: str) -> TestSpec:
        """按照稳定 ID 读取单个 TestSpec"""
        target_path = self._spec_path(spec_id)

        with target_path.open(encoding="utf-8") as f:
            payload = json.load(f)

        version = payload.get("version")

        if version != TEST_SPEC_FORMAT_VERSION:
            raise ValueError(
                (
                    "不支持的 TestSpec "
                    f"存储版本: {version}"
                )
            )
        return TestSpec.from_dict(payload["spec"])

    def approve(self, spec_id: str) -> TestSpec:
        """
        批准 TestSpec, 并持久化状态

        重复批准已经批准的 TestSpec 时，
        直接返回现有对象，不重复写文件
        """
        current = self.get(spec_id)

        if (
            current.status is TestSpecStatus.APPROVED
        ):
            return current

        if (
            current.status is TestSpecStatus.REJECTED
        ):
            raise ValueError(
                "已拒绝的 TestSpec 不能批准"
            )

        approved = replace(
            current,
            status=TestSpecStatus.APPROVED,
        )
        self.save(approved)

        return approved

    def reject(self, spec_id: str) -> TestSpec:
        """
        拒绝 TestSpec, 并持久化状态

        重复拒绝已经拒绝的 TestSpec 时，
        直接返回现有对象，不重复写文件
        """
        current = self.get(spec_id)
        if (
            current.status is TestSpecStatus.REJECTED
        ):
            return current

        if (
            current.status is TestSpecStatus.APPROVED
        ):
            raise ValueError(
                "已批准的 TestSpec 不能拒绝"
            )

        rejected = replace(
            current,
            status=TestSpecStatus.REJECTED,
        )
        self.save(rejected)
        return rejected