"""
Python 候选测试静态验证

fake 与真实集成测试职责不同
fake subprocess 测试验证我们自己的调用协议：
命令参数是否正确；
是否使用 --collect-only；
cwd 是否正确；
退出码是否映射到正确领域状态。
真实集成测试验证外部系统确实能协作：
当前环境真的安装了 pytest；
项目根目录设置能够导入 demo.py；
pytest 真的能收集候选测试；
我们对 pytest 行为的假设没有错。
"""
import shutil
import tempfile
import ast
import hashlib
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CandidateValidationStatus(StrEnum):
    """候选测试静态验证状态"""
    PASSED = "passed"
    EMPTY = "empty"
    INVALID_STRUCTURE = "invalid_structure"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    COLLECTION_ERROR = "collection_error"
    RUNNER_ERROR = "runner_error"
    TIMEOUT = "timeout"
    TEST_FAILURE="test_failure"

@dataclass(frozen=True)
class CandidateValidationResult:
    """一次候选测试静态验证结果"""

    status: CandidateValidationStatus
    errors: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.status
            is CandidateValidationStatus.PASSED
        )

def _module_is_available(
    module_name: str,
    project_root: Path,
) -> bool:
    module_path = project_root.joinpath(*module_name.split("."))
    if module_path.with_suffix(".py").is_file():
        return True

    if (
        module_path / "__init__.py"
    ).is_file():
        return True

    try:
        return (
            importlib.util.find_spec(module_name)
            is not None
        )
    except (
        ImportError,
        ModuleNotFoundError,
        ValueError,
    ):
        return False

def validate_python_candidate(
    content: str,
    *,
    project_root: str | Path | None = None,
) -> CandidateValidationResult:
    """验证 Python 候选测试源码"""
    if (
        not isinstance(content, str)
        or not content.strip()
    ):
        return CandidateValidationResult(
            status=CandidateValidationStatus.EMPTY,
            errors=(
                "候选测试源码为空",
            ),
        )

    if "```" in content:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus
                .INVALID_STRUCTURE
            ),
            errors=(
                "候选测试输出必须是纯 Python 源码",
            ),
        )

    try:
        syntax_tree = ast.parse(content)
    except SyntaxError:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus
                .SYNTAX_ERROR
            ),
            errors=(
                "候选测试包含非法 Python 语法",
            ),
        )

    has_test_function = any(
        (
                isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
                and node.name.startswith("test_")
        )
        for node in ast.walk(syntax_tree)
    )

    if not has_test_function:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus
                .INVALID_STRUCTURE
            ),
            errors=(
                "候选测试源码中没有 "
                "pytest 测试函数",
            ),
        )
    if project_root is not None:
        resolved_project_root = Path(
            project_root
        ).resolve()

        imported_modules: set[str] = set()

        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                imported_modules.update(
                    alias.name
                    for alias in node.names
                )

            if (
                    isinstance(node, ast.ImportFrom)
                    and node.level == 0
                    and node.module is not None
            ):
                imported_modules.add(
                    node.module
                )

        missing_modules = sorted(
            module_name
            for module_name in imported_modules
            if not _module_is_available(
                module_name,
                resolved_project_root,
            )
        )

        if missing_modules:
            return CandidateValidationResult(
                status=(
                    CandidateValidationStatus
                    .IMPORT_ERROR
                ),
                errors=tuple(
                    (
                        "无法导入模块: "
                        f"{module_name}"
                    )
                    for module_name
                    in missing_modules
                ),
            )

    return CandidateValidationResult(
        status=CandidateValidationStatus.PASSED,
    )

def collect_pytest_candidate(
    *,
    candidate_path: str | Path,
    project_root: str | Path,
) -> CandidateValidationResult:
    """使用真实 pytest 规则收集候选测试。"""

    candidate = Path(candidate_path)
    root = Path(project_root).resolve()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(candidate),
            "--collect-only",
            "-q",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if completed.returncode == 0:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus.PASSED
            ),
        )

    if completed.returncode == 5:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus
                .COLLECTION_ERROR
            ),
            errors=(
                "pytest 未收集到测试",
            ),
        )

    return CandidateValidationResult(
        status=(
            CandidateValidationStatus
            .COLLECTION_ERROR
        ),
        errors=(
            "pytest 收集候选测试失败",
        ),
    )

def check_pytest_runner_health(
    *,
    project_root: str | Path,
) -> CandidateValidationResult:
    """确认当前 Python 环境能够启动 pytest。"""

    root = Path(project_root).resolve()

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--version",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except OSError:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus.RUNNER_ERROR
            ),
            errors=(
                "pytest Runner 启动失败",
            ),
        )
    except subprocess.TimeoutExpired:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus.TIMEOUT
            ),
            errors=(
                "pytest Runner 健康检查超时",
            ),
        )

    if completed.returncode == 0:
        return CandidateValidationResult(
            status=(
                CandidateValidationStatus.PASSED
            ),
        )

    return CandidateValidationResult(
        status=(
            CandidateValidationStatus.RUNNER_ERROR
        ),
        errors=(
            "pytest Runner 健康检查失败",
        ),
    )

_SIDE_EFFECT_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".pytest_cache",
        "__pycache__",
    }
)


def _snapshot_project_files(
    project_root: Path,
) -> dict[str, str]:
    """记录项目文件内容摘要，忽略测试运行器产生的缓存。"""

    snapshot: dict[str, str] = {}

    for path in project_root.rglob("*"):
        relative_path = path.relative_to(project_root)
        if any(
            part in _SIDE_EFFECT_IGNORED_DIRECTORY_NAMES
            for part in relative_path.parts
        ):
            continue

        if not path.is_file():
            continue

        snapshot[relative_path.as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

    return snapshot


def _describe_file_side_effects(
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[str, ...]:
    """比较两份文件摘要并返回稳定排序的副作用描述。"""

    before_paths = set(before)
    after_paths = set(after)

    side_effects = [
        *(
            f"created:{path}"
            for path in after_paths - before_paths
        ),
        *(
            f"modified:{path}"
            for path in before_paths & after_paths
            if before[path] != after[path]
        ),
        *(
            f"deleted:{path}"
            for path in before_paths - after_paths
        ),
    ]
    return tuple(sorted(side_effects))


# isolated 孤立的；分离的；绝缘的；单独的
def execute_pytest_candidate_isolated(
    *,
    candidate_path: str | Path,
    project_root: str | Path,
    timeout: int = 30,
) -> CandidateValidationResult:
    """在临时项目副本中执行候选测试"""
    root = Path(project_root).resolve()
    candidate = Path(candidate_path).resolve()

    candidate_relative_path = candidate.relative_to(root)

    with tempfile.TemporaryDirectory(
        prefix="test-assistant-",
    ) as temp_dir:
        isolated_root = (
            Path(temp_dir) / "project"
        )
        # 递归复制整个目录树
        shutil.copytree(
            root,
            isolated_root,
        )
        isolated_candidate = (
            isolated_root / candidate_relative_path
        )
        before_snapshot = _snapshot_project_files(
            isolated_root
        )
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(isolated_candidate),
                    "-q",
                ],
                cwd=isolated_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            side_effects = _describe_file_side_effects(
                before_snapshot,
                _snapshot_project_files(isolated_root),
            )
            return CandidateValidationResult(
                status=(
                    CandidateValidationStatus.TIMEOUT
                ),
                errors=(
                    "候选测试执行超时",
                ),
                side_effects=side_effects,
            )
        except OSError:
            side_effects = _describe_file_side_effects(
                before_snapshot,
                _snapshot_project_files(isolated_root),
            )
            return CandidateValidationResult(
                status=(
                    CandidateValidationStatus.RUNNER_ERROR
                ),
                errors=(
                    "pytest Runner 执行启动失败",
                ),
                side_effects=side_effects,
            )

        side_effects = _describe_file_side_effects(
            before_snapshot,
            _snapshot_project_files(isolated_root),
        )

        if completed.returncode == 0:
            return CandidateValidationResult(
                status=(
                    CandidateValidationStatus.PASSED
                ),
                side_effects=side_effects,
            )
        if completed.returncode == 1:
            return CandidateValidationResult(
                status=(
                    CandidateValidationStatus.TEST_FAILURE
                ),
                errors=(
                    "候选测试执行失败",
                ),
                side_effects=side_effects,
            )

        return CandidateValidationResult(
            status=(
                CandidateValidationStatus.RUNNER_ERROR
            ),
            errors=(
                "pytest Runner 执行失败",
            ),
            side_effects=side_effects,
        )
