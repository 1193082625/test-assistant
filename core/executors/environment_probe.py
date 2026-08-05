"""安全、只读的环境版本命令探测"""

import subprocess
from collections.abc import Callable
from pathlib import Path

from core.models import (
    EnvironmentCheck,
    EnvironmentCheckState,
)


Runner = Callable[..., subprocess.CompletedProcess[str]]
VERSION_TEXT_LIMIT = 200


def _first_nonempty_line(*outputs: str) -> str | None:
    """从输出中提取第一条非空行"""

    for output in outputs:
        for line in output.splitlines():
            normalized = line.strip()
            if normalized:
                return normalized

    return None

def probe_command(
    *,
    name: str,
    command: tuple[str, ...],
    project_root: str | Path,
    timeout: float,
    required: bool,
    capabilities: tuple[str, ...] = (),
    runner: Runner = subprocess.run,
) -> EnvironmentCheck:
    """执行固定版本命令并返回环境事实"""

    if (
            not isinstance(command, tuple)
            or not command
            or any(
        not isinstance(part, str)
        or not part
        for part in command
    )
    ):
        raise ValueError(
            "command 必须是非空字符串组成的 tuple"
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

    root = Path(project_root).resolve()

    if not root.is_dir():
        raise ValueError(
            "project_root 必须是现有目录"
        )

    try:
        completed = runner(
            list(command),
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    # 知道 FileNotFoundError 是 Git 缺失
    except FileNotFoundError:
        return EnvironmentCheck(
            name=name,
            state=(
                EnvironmentCheckState.UNAVAILABLE
            ),
            version=None,
            executable=command[0],
            required=required,
            reason="command_not_found",
            capabilities=capabilities,
        )
    # 知道 TimeoutExpired 是 mypy 超时
    except subprocess.TimeoutExpired:
        return EnvironmentCheck(
            name=name,
            state=(
                EnvironmentCheckState.TIMED_OUT
            ),
            version=None,
            executable=command[0],
            required=required,
            reason="probe_timed_out",
            capabilities=capabilities,
        )
    except Exception:
        return EnvironmentCheck(
            name=name,
            state=EnvironmentCheckState.FAILED,
            version=None,
            executable=command[0],
            required=required,
            reason="probe_exception",
            capabilities=capabilities,
        )

    stdout = (
        completed.stdout.strip()
        if isinstance(completed.stdout, str)
        else ""
    )
    stderr = (
        completed.stderr.strip()
        if isinstance(completed.stderr, str)
        else ""
    )
    combined_output = "\n".join(
        part
        for part in (
            stdout,
            stderr,
        )
        if part
    )

    if completed.returncode != 0:
        if "No module named" in combined_output:
            state = (
                EnvironmentCheckState.UNAVAILABLE
            )
            reason = "module_not_found"
        else:
            state = EnvironmentCheckState.FAILED
            reason = "command_failed"

        return EnvironmentCheck(
            name=name,
            state=state,
            version=None,
            executable=command[0],
            required=required,
            reason=reason,
            capabilities=capabilities,
        )

    version = _first_nonempty_line(
        stdout,
        stderr,
    )

    if version is None:
        return EnvironmentCheck(
            name=name,
            state=EnvironmentCheckState.FAILED,
            version=None,
            executable=command[0],
            required=required,
            reason="version_output_invalid",
            capabilities=capabilities,
        )

    if len(version) > VERSION_TEXT_LIMIT:
        return EnvironmentCheck(
            name=name,
            state=EnvironmentCheckState.FAILED,
            version=None,
            executable=command[0],
            required=required,
            reason="version_output_too_large",
            capabilities=capabilities,
        )

    return EnvironmentCheck(
        name=name,
        state=EnvironmentCheckState.AVAILABLE,
        version=version,
        executable=command[0],
        required=required,
        capabilities=capabilities,
    )