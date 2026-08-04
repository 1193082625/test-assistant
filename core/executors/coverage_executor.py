"""安全执行 pytest-cov 并读取受控临时 coverage JSON。"""

import json
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from core.executors.base import (
    ExecutionEnvironment,
    ExecutionReport,
    normalize_process_output,
    summarize_process_output,
)
from core.models import ToolState, ToolStatus


_MAX_COVERAGE_JSON_BYTES = 5_000_000


@dataclass(frozen=True)
class CoverageExecutionResult:
    """一次 coverage adapter 执行产生的事实和降级状态。"""

    command: tuple[str, ...]
    report: ExecutionReport
    status: ToolStatus
    coverage_data: dict[str, object] | None = None


def _safe_relative_path(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须位于项目内")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        raise ValueError(f"{field} 必须位于项目内")
    return value


class CoverageExecutor:
    """通过目标 Python 的 pytest-cov 采集覆盖率，不写目标项目。"""

    def __init__(
        self,
        project_root: str | Path,
        *,
        python_executable: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.python_executable = python_executable or sys.executable

    def execute(
        self,
        *,
        source_path: str,
        test_path: str | None = None,
        test_node: str | None = None,
        timeout: float = 120,
    ) -> CoverageExecutionResult:
        source = _safe_relative_path(source_path, field="source_path")
        if test_path is not None and test_node is not None:
            raise ValueError("test_path 与 test_node 不能同时提供")
        target = test_node or test_path
        if target is not None:
            path_part = target.partition("::")[0]
            _safe_relative_path(path_part, field="test_path")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须大于 0")

        environment = ExecutionEnvironment(
            runner="pytest-cov",
            runtime="python",
            runtime_version=platform.python_version(),
            working_directory=str(self.project_root),
        )
        with tempfile.TemporaryDirectory(
            prefix="test-assistant-coverage-"
        ) as temporary_directory:
            output_path = Path(temporary_directory) / "coverage.json"
            command = [self.python_executable, "-m", "pytest"]
            if target is not None:
                command.append(target)
            command.extend(
                [
                    f"--cov={source}",
                    "--cov-branch",
                    f"--cov-report=json:{output_path}",
                    "--cov-report=",
                    "-q",
                    "--tb=short",
                ]
            )
            command_tuple = tuple(command)
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=False,
                )
            except subprocess.TimeoutExpired as error:
                report = ExecutionReport(
                    stdout=summarize_process_output(error.stdout),
                    stderr=summarize_process_output(error.stderr) or str(error),
                    exit_code=None,
                    timed_out=True,
                    error_type="timeout",
                    environment=environment,
                )
                return CoverageExecutionResult(
                    command=command_tuple,
                    report=report,
                    status=ToolStatus(
                        tool="coverage",
                        state=ToolState.TIMED_OUT,
                        version=None,
                        reason="execution_timeout",
                    ),
                )
            except OSError as error:
                report = ExecutionReport(
                    stderr=str(error),
                    exit_code=None,
                    error_type="startup_error",
                    environment=environment,
                )
                return CoverageExecutionResult(
                    command=command_tuple,
                    report=report,
                    status=ToolStatus(
                        tool="coverage",
                        state=ToolState.FAILED,
                        version=None,
                        reason="startup_error",
                    ),
                )

            stdout = summarize_process_output(completed.stdout)
            stderr = summarize_process_output(completed.stderr)
            error_type = None
            if completed.returncode == 1:
                error_type = "test_failure"
            elif completed.returncode == 5:
                error_type = "no_tests_collected"
            elif completed.returncode != 0:
                error_type = "runner_error"
            report = ExecutionReport(
                stdout=stdout,
                stderr=stderr,
                exit_code=completed.returncode,
                error_type=error_type,
                environment=environment,
            )
            combined_output = f"{stdout}\n{stderr}"
            if "unrecognized arguments" in combined_output and "--cov" in combined_output:
                return CoverageExecutionResult(
                    command=command_tuple,
                    report=report,
                    status=ToolStatus(
                        tool="coverage",
                        state=ToolState.UNAVAILABLE,
                        version=None,
                        reason="pytest_cov_not_installed",
                    ),
                )
            if not output_path.is_file():
                return CoverageExecutionResult(
                    command=command_tuple,
                    report=report,
                    status=ToolStatus(
                        tool="coverage",
                        state=ToolState.FAILED,
                        version=None,
                        reason="coverage_output_missing",
                    ),
                )
            if output_path.stat().st_size > _MAX_COVERAGE_JSON_BYTES:
                return CoverageExecutionResult(
                    command=command_tuple,
                    report=report,
                    status=ToolStatus(
                        tool="coverage",
                        state=ToolState.FAILED,
                        version=None,
                        reason="coverage_json_too_large",
                    ),
                )
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("coverage root must be an object")
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                return CoverageExecutionResult(
                    command=command_tuple,
                    report=report,
                    status=ToolStatus(
                        tool="coverage",
                        state=ToolState.FAILED,
                        version=None,
                        reason="invalid_coverage_json",
                    ),
                )
            meta = payload.get("meta")
            version = meta.get("version") if isinstance(meta, dict) else None
            return CoverageExecutionResult(
                command=command_tuple,
                report=report,
                status=ToolStatus(
                    tool="coverage",
                    state=ToolState.COMPLETED,
                    version=version if isinstance(version, str) else None,
                    reason=None,
                ),
                coverage_data=payload,
            )

