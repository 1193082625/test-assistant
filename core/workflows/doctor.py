"""确定性、只读的环境诊断工作流"""

import platform
import sys
from collections.abc import Callable
from pathlib import Path

from cli import __version__
from core.executors import probe_command
from core.models import (
    DoctorResult,
    DoctorStatus,
    EnvironmentCheck,
    EnvironmentCheckState,
)

# Probe 是一个别名，不会创建新类型，也不会包装函数
# Probe = 一个可以被调用的对象 = 参数暂时不做精确限制 = 返回值必须是 EnvironmentCheck
# Callable 表示 可以像函数一样调用的对象
# ... 表示 这个可调用对象的具体参数列表暂时不检查
Probe = Callable[..., EnvironmentCheck]
# 当前表示只认证 Python 3.13
SUPPORTED_PYTHON = (3, 13)


def _python_check() -> EnvironmentCheck:
    """收集当前解释器事实。"""

    version = platform.python_version()
    current_version = (
        sys.version_info.major,
        sys.version_info.minor,
    )
    supported = (
        current_version == SUPPORTED_PYTHON
    )

    if supported:
        state = EnvironmentCheckState.AVAILABLE
        reason = None
    else:
        state = (
            EnvironmentCheckState.INCOMPATIBLE
        )
        reason = "unsupported_python_version"

    return EnvironmentCheck(
        name="python",
        state=state,
        version=version,
        executable=sys.executable,
        required=True,
        reason=reason,
        capabilities=(
            "cli",
            "triage",
            "verify",
            "audit",
        ),
    )


def _doctor_status(
    checks: tuple[EnvironmentCheck, ...],
) -> DoctorStatus:
    """根据核心检查状态计算 Doctor 汇总状态"""

    required_checks = [
        check
        for check in checks
        if check.required
    ]

    required_states = {
        check.state
        for check in required_checks
    }

    infra_states = {
        EnvironmentCheckState.TIMED_OUT,
        EnvironmentCheckState.FAILED,
    }
    if required_states & infra_states:
        return DoctorStatus.INFRA_ERROR

    incompatible_states = {
        EnvironmentCheckState.UNAVAILABLE,
        EnvironmentCheckState.INCOMPATIBLE,
        EnvironmentCheckState.NOT_APPLICABLE,
    }
    if required_states & incompatible_states:
        return DoctorStatus.INCOMPATIBLE

    return DoctorStatus.HEALTHY


def _optional_probe_specs() -> tuple[
    tuple[
        str,
        tuple[str, ...],
        tuple[str, ...],
    ],
    ...,
]:
    """返回固定、只读的可选工具探测规格。"""

    return (
        (
            "pytest-cov",
            (
                sys.executable,
                "-c",
                (
                    "from importlib.metadata "
                    "import version; "
                    "print(version('pytest-cov'))"
                ),
            ),
            (
                "audit_coverage",
            ),
        ),
        (
            "coverage",
            (
                sys.executable,
                "-m",
                "coverage",
                "--version",
            ),
            (
                "audit_coverage",
            ),
        ),
        (
            "ruff",
            (
                sys.executable,
                "-m",
                "ruff",
                "--version",
            ),
            (
                "audit_quality",
            ),
        ),
        (
            "mypy",
            (
                sys.executable,
                "-m",
                "mypy",
                "--version",
            ),
            (
                "audit_quality",
            ),
        ),
    )


def _git_checks(
    *,
    root: Path,
    timeout: float,
    probe: Probe,
) -> tuple[
    EnvironmentCheck,
    EnvironmentCheck,
]:
    """检查 Git 工具及目标 worktree 状态。"""

    capabilities = (
        "changed_only",
        "git_history",
    )

    git_check = probe(
        name="git",
        command=(
            "git",
            "--version",
        ),
        project_root=root,
        timeout=timeout,
        required=False,
        capabilities=capabilities,
    )

    if (
        git_check.state
        is not EnvironmentCheckState.AVAILABLE
    ):
        worktree_check = EnvironmentCheck(
            name="git-worktree",
            state=(
                EnvironmentCheckState.NOT_APPLICABLE
            ),
            version=None,
            executable="git",
            required=False,
            reason="git_unavailable",
            capabilities=capabilities,
        )
        return git_check, worktree_check

    raw_worktree = probe(
        name="git-worktree",
        command=(
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--is-inside-work-tree",
        ),
        project_root=root,
        timeout=timeout,
        required=False,
        capabilities=capabilities,
    )

    if (
        raw_worktree.state
        is EnvironmentCheckState.AVAILABLE
    ):
        if raw_worktree.version == "true":
            worktree_check = EnvironmentCheck(
                name="git-worktree",
                state=(
                    EnvironmentCheckState.AVAILABLE
                ),
                version=None,
                executable="git",
                required=False,
                capabilities=capabilities,
            )
        elif raw_worktree.version == "false":
            worktree_check = EnvironmentCheck(
                name="git-worktree",
                state=(
                    EnvironmentCheckState.NOT_APPLICABLE
                ),
                version=None,
                executable="git",
                required=False,
                reason="not_git_worktree",
                capabilities=capabilities,
            )
        else:
            worktree_check = EnvironmentCheck(
                name="git-worktree",
                state=(
                    EnvironmentCheckState.FAILED
                ),
                version=None,
                executable="git",
                required=False,
                reason=(
                    "invalid_git_worktree_output"
                ),
                capabilities=capabilities,
            )
    elif (
        raw_worktree.state
        is EnvironmentCheckState.FAILED
        and raw_worktree.reason
        == "command_failed"
    ):
        worktree_check = EnvironmentCheck(
            name="git-worktree",
            state=(
                EnvironmentCheckState.NOT_APPLICABLE
            ),
            version=None,
            executable="git",
            required=False,
            reason="not_git_worktree",
            capabilities=capabilities,
        )
    else:
        worktree_check = EnvironmentCheck(
            name="git-worktree",
            state=raw_worktree.state,
            version=None,
            executable="git",
            required=False,
            reason=raw_worktree.reason,
            capabilities=capabilities,
        )

    return git_check, worktree_check


def run_doctor(
    *,
    project_root: str | Path,
    timeout: float = 10,
    probe: Probe = probe_command,
) -> DoctorResult:
    """收集核心与可选环境事实。"""

    root = Path(project_root).resolve()

    if not root.is_dir():
        raise ValueError(
            "project_root 必须是现有目录"
        )

    if (
        isinstance(timeout, bool)
        or not isinstance(
            timeout,
            (int, float),
        )
        or timeout <= 0
    ):
        raise ValueError(
            "timeout 必须是大于 0 的数字"
        )

    python_check = _python_check()
    pytest_check = probe(
        name="pytest",
        command=(
            sys.executable,
            "-m",
            "pytest",
            "--version",
        ),
        project_root=root,
        timeout=timeout,
        required=True,
        capabilities=(
            "triage",
            "verify",
            "audit_coverage",
        ),
    )

    git_checks = _git_checks(
        root=root,
        timeout=timeout,
        probe=probe,
    )

    optional_checks = tuple(
        probe(
            name=name,
            command=command,
            project_root=root,
            timeout=timeout,
            required=False,
            capabilities=capabilities,
        )
        for (
            name,
            command,
            capabilities,
        ) in _optional_probe_specs()
    )

    checks = (
        python_check,
        pytest_check,
        *git_checks,
        *optional_checks,
    )
    status = _doctor_status(checks)

    return DoctorResult(
        schema_version=1,
        status=status,
        test_assistant_version=__version__,
        project_path=str(root),
        python_implementation=(
            platform.python_implementation().lower()
        ),
        platform=platform.platform(),
        checks=checks,
    )