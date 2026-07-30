"""候选测试源码 repository"""
import difflib
import hashlib
import json
import re
import os
import tempfile
from pathlib import (
    Path,
    PurePosixPath, # 按照项目统一保存的 / 相对路径解析
    PureWindowsPath, # 额外识别 C:\... 等 Windows 绝对路径
)
from dataclasses import dataclass


CANDIDATE_SPEC_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]*"
)

CANDIDATE_TEST_FILENAME_PATTERN = re.compile(
    r"test_[A-Za-z0-9_]+\.py"
)
CANDIDATE_METADATA_FORMAT_VERSION = 1

def _parse_safe_source_relative_path(
        value:object,
        *,
        error_message: str,
) -> PurePosixPath:
    """解析经过安全检查的源码相对路径"""
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\\" in value
    ):
        raise ValueError(error_message)

    relative_path = PurePosixPath(value)

    if (
        relative_path.is_absolute()
        or PureWindowsPath(value).is_absolute()
        or not relative_path.parts
        or ".." in relative_path.parts
    ):
        raise ValueError(error_message)

    return relative_path

def _parse_safe_test_filename(
        value:object,
        *,
        error_message: str,
) -> str:
    """解析安全的 Python 测试文件名"""
    if (
        not isinstance(value, str)
        or CANDIDATE_TEST_FILENAME_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(error_message)

    return value

def _parse_safe_spec_id(
        value:object,
        *,
        error_message: str,
) -> str:
    """解析安全的候选 TestSpec ID"""
    if (
        not isinstance(value, str)
        or CANDIDATE_SPEC_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(error_message)

    return value

@dataclass(frozen=True)
class CandidateDiff:
    """供用户二次审阅的候选测试差异"""
    candidate_path: Path
    final_path: Path
    change_type: str
    content_sha256: str
    original_content_sha256: str | None
    text: str

@dataclass(frozen=True)
class CandidateApproval:
    """绑定用户已审阅候选差异的批准凭证。"""

    candidate_path: Path
    final_path: Path
    content_sha256: str
    original_content_sha256: str | None

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
        safe_spec_id = _parse_safe_spec_id(
            spec_id,
            error_message=(
                "Candidate spec_id 包含不安全字符"
            ),
        )

        relative_source_path = _parse_safe_source_relative_path(
            source_relative_path,
            error_message=(
                "Candidate source_relative_path "
                "必须是安全相对路径"
            ),
        )

        safe_test_filename = (
            _parse_safe_test_filename(
                test_filename,
                error_message=(
                    "Candidate test_filename 必须是"
                    "安全 Python 测试文件名"
                ),
            )
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
            / safe_spec_id
            / relative_source_path
            / safe_test_filename
        )

        metadata_path = target_path.with_name(
            f"{target_path.name}.meta.json"
        )

        metadata_payload = {
            "version": (
                CANDIDATE_METADATA_FORMAT_VERSION
            ),
            "spec_id": safe_spec_id,
            "source_relative_path": (
                source_relative_path
            ),
            "test_filename": safe_test_filename,
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

    def build_diff(
        self,
        *,
        candidate_path: str | Path,
    ) -> CandidateDiff:
        """生成候选测试与正式测试之间的差异"""

        candidate = Path(
            candidate_path
        ).resolve()

        candidate_root = self.candidates_path.resolve()

        try:
            candidate.relative_to(candidate_root)
        except ValueError as error:
            raise ValueError(
                "候选测试不在 candidates 目录中"
            ) from error

        if not candidate.is_file():
            raise FileNotFoundError("候选测试源码不存在")

        metadata_path = candidate.with_name(
            f"{candidate.name}.meta.json"
        )
        if not metadata_path.is_file():
            raise FileNotFoundError(
                "候选测试元数据缺失"
            )

        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
        spec_id = _parse_safe_spec_id(
            metadata.get("spec_id"),
            error_message=(
                "候选测试元数据与文件路径不匹配"
            )
        )

        source_relative_path = (
            _parse_safe_source_relative_path(
                metadata.get(
                    "source_relative_path"
                ),
                error_message=(
                    "候选测试元数据路径不安全"
                ),
            )
        )
        test_filename = (
            _parse_safe_test_filename(
                metadata.get(
                    "test_filename"
                ),
                error_message=(
                    "候选测试元数据路径不安全"
                ),
            )
        )

        expected_candidate_path = (
                candidate_root
                / spec_id
                / source_relative_path
                / test_filename
        ).resolve()

        if candidate != expected_candidate_path:
            raise ValueError(
                "候选测试元数据与文件路径不匹配"
            )

        final_path = (
            self.project_root
            / ".autotest"
            / "test_cases"
            / "unit"
            / source_relative_path
            / test_filename
        )

        candidate_content= candidate.read_text(encoding="utf-8")
        content_sha256 = build_candidate_content_digest(candidate_content)
        expected_content_sha256 = metadata.get(
            "content_sha256"
        )

        if (
                not isinstance(
                    expected_content_sha256,
                    str,
                )
                or content_sha256
                != expected_content_sha256
        ):
            raise ValueError(
                "候选测试内容摘要不匹配"
            )
        if final_path.is_file():

            previous_content = final_path.read_text(
                encoding="utf-8",
            )
            original_content_sha256 = (
                build_candidate_content_digest(
                    previous_content
                )
            )
            change_type = "modified"
            previous_lines = (
                previous_content.splitlines(
                    keepends=True
                )
            )
            from_file = final_path.relative_to(
                self.project_root
            ).as_posix()
        else:
            original_content_sha256 = None
            change_type = "created"
            previous_lines = []
            from_file = "/dev/null"

        final_relative_path = (
            final_path.relative_to(
                self.project_root
            ).as_posix()
        )

        diff_text = "".join(
            difflib.unified_diff(
                previous_lines,
                candidate_content.splitlines(keepends=True),
                fromfile=from_file,
                tofile=final_relative_path,
            )
        )

        return CandidateDiff(
            candidate_path=candidate,
            final_path=final_path,
            change_type=change_type,
            content_sha256=content_sha256,
            original_content_sha256=(
                original_content_sha256
            ),
            text=diff_text,
        )

    def approve_diff(
            self,
            *,
            reviewed_diff: CandidateDiff,
    ) -> CandidateApproval:
        """批准仍与当前文件状态一致的候选差异。"""

        if not isinstance(
                reviewed_diff,
                CandidateDiff,
        ):
            raise TypeError(
                "reviewed_diff 必须是 CandidateDiff"
            )

        current_diff = self.build_diff(
            candidate_path=(
                reviewed_diff.candidate_path
            ),
        )

        if current_diff != reviewed_diff:
            raise ValueError(
                "候选 diff 已发生变化"
            )

        return CandidateApproval(
            candidate_path=(
                current_diff.candidate_path
            ),
            final_path=current_diff.final_path,
            content_sha256=(
                current_diff.content_sha256
            ),
            original_content_sha256=(
                current_diff
                .original_content_sha256
            ),
        )

    def commit_candidate(
            self,
            *,
            approval: CandidateApproval,
    ) -> Path:
        """提交已经批准的候选测试。"""

        if not isinstance(
                approval,
                CandidateApproval,
        ):
            raise TypeError(
                "approval 必须是 "
                "CandidateApproval"
            )

        current_diff = self.build_diff(
            candidate_path=approval.candidate_path,
        )

        current_approval = CandidateApproval(
            candidate_path=(
                current_diff.candidate_path
            ),
            final_path=current_diff.final_path,
            content_sha256=(
                current_diff.content_sha256
            ),
            original_content_sha256=(
                current_diff.original_content_sha256
            ),
        )

        if current_approval != approval:
            raise ValueError(
                "CandidateApproval 已过期"
            )

        candidate_content = (
            current_diff.candidate_path.read_text(
                encoding="utf-8",
            )
        )
        # 第二次读取候选，需要重新计算摘要，对照批准摘要，通过后才创建正式目录和临时文件
        commit_content_sha256 = (
            build_candidate_content_digest(
                candidate_content
            )
        )

        if (
                commit_content_sha256
                != approval.content_sha256
        ):
            raise ValueError(
                "候选测试在提交期间发生变化"
            )

        final_path = current_diff.final_path
        final_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=final_path.parent,
                    prefix=f".{final_path.name}.",
                    suffix=".tmp",
                    delete=False,
            ) as temporary_file:
                temporary_file.write(
                    candidate_content
                )
                temporary_file.flush()
                os.fsync(
                    temporary_file.fileno()
                )
                temporary_path = Path(
                    temporary_file.name
                )

            # 批准时目标不存在，os.link()，只允许原子创建，目标已存在则绝不覆盖
            if (
                    approval.original_content_sha256
                    is None
            ):
                try:
                    os.link(
                        temporary_path,
                        final_path,
                    )
                except FileExistsError as error:
                    raise ValueError(
                        "正式测试在提交期间发生变化"
                    ) from error

                temporary_path.unlink()
                temporary_path = None
            # 批准时目标已存在，临时文件写入并 fsync，确认正式文件仍然存在，重新读取正式文件，重新计算摘要，与批准时原摘要比较，相同才替换
            else:
                if not final_path.is_file():
                    raise ValueError(
                        "正式测试在提交期间发生变化"
                    )

                latest_final_content = (
                    final_path.read_text(
                        encoding="utf-8",
                    )
                )
                latest_final_sha256 = (
                    build_candidate_content_digest(
                        latest_final_content
                    )
                )

                if (
                        latest_final_sha256
                        != approval.original_content_sha256
                ):
                    raise ValueError(
                        "正式测试在提交期间发生变化"
                    )

                temporary_path.replace(
                    final_path
                )
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(
                    missing_ok=True
                )
            raise

        return final_path
