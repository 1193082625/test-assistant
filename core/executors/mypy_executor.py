"""目标 Python 环境中的 mypy 只读执行器。"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.analyzers.quality import parse_mypy_findings
from core.executors.base import ExecutionReport, summarize_process_output
from core.models import QualityFinding, ToolState, ToolStatus


@dataclass(frozen=True)
class MypyExecutionResult:
    command: tuple[str, ...]
    report: ExecutionReport
    status: ToolStatus
    findings: tuple[QualityFinding, ...] = ()


class MypyExecutor:
    """执行固定、只读的 mypy 检查，不安装 stub。"""

    def __init__(
        self,
        project_root: str | Path,
        *,
        python_executable: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.python_executable = python_executable or sys.executable

    def _read_version(self, timeout: float) -> str | None:
        try:
            completed = subprocess.run(
                [self.python_executable, "-m", "mypy", "--version"],
                cwd=str(self.project_root), capture_output=True, text=True,
                timeout=min(timeout, 10), shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        parts = completed.stdout.strip().split()
        return parts[1] if len(parts) >= 2 and parts[0] == "mypy" else None

    def execute(self, *, timeout: float = 120) -> MypyExecutionResult:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        command = (
            self.python_executable,
            "-m",
            "mypy",
            ".",
            "--show-error-codes",
            "--show-column-numbers",
            "--no-color-output",
            "--no-error-summary",
            "--no-pretty",
        )
        try:
            completed = subprocess.run(
                list(command), cwd=str(self.project_root), capture_output=True,
                text=True, timeout=timeout, shell=False,
            )
        except subprocess.TimeoutExpired as error:
            return MypyExecutionResult(
                command=command,
                report=ExecutionReport(
                    stdout=summarize_process_output(error.stdout),
                    stderr=summarize_process_output(error.stderr) or str(error),
                    timed_out=True, error_type="timeout",
                ),
                status=ToolStatus(
                    tool="mypy", state=ToolState.TIMED_OUT,
                    version=None, reason="execution_timeout",
                ),
            )
        except OSError as error:
            return MypyExecutionResult(
                command=command,
                report=ExecutionReport(stderr=str(error), error_type="startup_error"),
                status=ToolStatus(
                    tool="mypy", state=ToolState.FAILED,
                    version=None, reason="startup_error",
                ),
            )
        stdout = summarize_process_output(completed.stdout)
        stderr = summarize_process_output(completed.stderr)
        report = ExecutionReport(
            stdout=stdout, stderr=stderr, exit_code=completed.returncode,
            error_type=None if completed.returncode in {0, 1} else "runner_error",
        )
        if "No module named mypy" in f"{stdout}\n{stderr}":
            return MypyExecutionResult(
                command=command, report=report,
                status=ToolStatus(
                    tool="mypy", state=ToolState.UNAVAILABLE,
                    version=None, reason="mypy_not_installed",
                ),
            )
        if completed.returncode not in {0, 1}:
            return MypyExecutionResult(
                command=command, report=report,
                status=ToolStatus(
                    tool="mypy", state=ToolState.FAILED,
                    version=None, reason="mypy_execution_failed",
                ),
            )
        try:
            findings = parse_mypy_findings(stdout, project_root=self.project_root)
        except ValueError:
            return MypyExecutionResult(
                command=command, report=report,
                status=ToolStatus(
                    tool="mypy", state=ToolState.FAILED,
                    version=None, reason="invalid_mypy_output",
                ),
            )
        if completed.returncode == 1 and not findings:
            return MypyExecutionResult(
                command=command, report=report,
                status=ToolStatus(
                    tool="mypy", state=ToolState.FAILED,
                    version=None, reason="invalid_mypy_output",
                ),
            )
        return MypyExecutionResult(
            command=command, report=report,
            status=ToolStatus(
                tool="mypy", state=ToolState.COMPLETED,
                version=self._read_version(timeout), reason=None,
            ),
            findings=findings,
        )

