"""候选测试源码 repository"""

import hashlib
import json
import re
from pathlib import (
    Path,
    PurePosixPath, # 按照项目统一保存的 / 相对路径解析
    PureWindowsPath, # 额外识别 C:\... 等 Windows 绝对路径
)


CANDIDATE_SPEC_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]*"
)

CANDIDATE_TEST_FILENAME_PATTERN = re.compile(
    r"test_[A-Za-z0-9_]+\.py"
)
CANDIDATE_METADATA_FORMAT_VERSION = 1

def build_candidate_content_digest(
        content: str,
) -> str:
    """计算候选源码 UTF-8 内容的 SHA-256"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

class CandidateRepository:
    """将生成内容保存到隔离的候选区域"""
    def __init__(
        self,
        project_root: str | Path
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.candidates_path = (
            self.project_root / ".autotest" / "candidates"
        )

    def save(
        self,
        *,
        spec_id: str,
        source_relative_path: str,
        test_filename: str,
        content: str,
        generator_model: str,
        template_version: str,
    ) -> Path:
        if (
            not isinstance(spec_id, str)
            or CANDIDATE_SPEC_ID_PATTERN.fullmatch(spec_id) is None
        ):
            raise ValueError(
                "Candidate spec_id 包含不安全字符"
            )

        if (
            not isinstance(source_relative_path, str)
            or not source_relative_path.strip()
            # macOS 的 PurePosixPath 会把反斜杠当普通字符，而 Windows 会把它当路径分隔符。主动拒绝可以保证两个平台行为一致。
            or "\\" in source_relative_path
        ):
            raise ValueError(
                "Candidate source_relative_path "
                "必须是安全相对路径"
            )

        relative_source_path = PurePosixPath(
            source_relative_path
        )

        if (
            relative_source_path.is_absolute()
            or PureWindowsPath(
                source_relative_path
            ).is_absolute()
            or not relative_source_path.parts
            or ".." in relative_source_path.parts
        ):
            raise ValueError(
                "Candidate source_relative_path "
                "必须是安全相对路径"
            )

        if (
            not isinstance(test_filename, str)
            or CANDIDATE_TEST_FILENAME_PATTERN.fullmatch(
                test_filename
            ) is None
        ):
            raise ValueError(
                "Candidate test_filename 必须是"
                "安全 Python 测试文件名"
            )

        if (
            not isinstance(generator_model, str)
            or not generator_model.strip()
        ):
            raise ValueError(
                "Candidate generator_model 不能为空"
            )

        if (
            not isinstance(template_version, str)
            or not template_version.strip()
        ):
            raise ValueError(
                "Candidate template_version 不能为空"
            )

        target_path = (
            self.candidates_path
            / spec_id
            / relative_source_path
            / test_filename
        )

        metadata_path = target_path.with_name(
            f"{target_path.name}.meta.json"
        )

        metadata_payload = {
            "version": (
                CANDIDATE_METADATA_FORMAT_VERSION
            ),
            "spec_id": spec_id,
            "source_relative_path": (
                source_relative_path
            ),
            "test_filename": test_filename,
            "generator_model": generator_model,
            "template_version": template_version,
            "content_sha256": (
                build_candidate_content_digest(
                    content
                )
            ),
        }

        if (
            metadata_path.exists()
            and not target_path.is_file()
        ):
            raise FileNotFoundError(
                "候选测试源码缺失"
            )

        if target_path.exists():
            if not metadata_path.is_file():
                raise FileNotFoundError(
                    "候选测试元数据缺失"
                )
            existing_content = target_path.read_text(
                encoding="utf-8",
            )

            if existing_content != content:
                raise FileExistsError(
                    "候选测试已存在且内容不同"
                )

            return target_path

        target_path.parent.mkdir(parents=True, exist_ok=True)

        target_path.write_text(content, encoding="utf-8")

        metadata_path.write_text(
            (
                json.dumps(
                    metadata_payload,
                    ensure_ascii=False,
                    indent=4,
                )
                + "\n"
            ),
            encoding="utf-8",
        )

        return target_path
