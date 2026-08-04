"""目标 Python 环境中的 Ruff 只读执行器。"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.analyzers.quality import parse_ruff_findings
from core.executors.base import ExecutionReport, summarize_process_output
from core.models import QualityFinding, ToolState, ToolStatus


_MAX_RUFF_JSON_BYTES = 5_000_000


@dataclass(frozen=True)
class RuffExecutionResult:
    command: tuple[str, ...]
    report: ExecutionReport
    status: ToolStatus
    findings: tuple[QualityFinding, ...] = ()


class RuffExecutor:
    """执行 Ruff JSON 检查，不安装工具、不联网、不请求修复。"""

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
                [self.python_executable, "-m", "ruff", "--version"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=min(timeout, 10),
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        output = completed.stdout.strip()
        if output.startswith("ruff "):
            return output.removeprefix("ruff ").strip() or None
        return None

    def execute(self, *, timeout: float = 120) -> RuffExecutionResult:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        command = (
            self.python_executable,
            "-m",
            "ruff",
            "check",
            "--output-format",
            "json",
            ".",
        )
        try:
            completed = subprocess.run(
                list(command),
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
                timed_out=True,
                error_type="timeout",
            )
            return RuffExecutionResult(
                command=command,
                report=report,
                status=ToolStatus(
                    tool="ruff", state=ToolState.TIMED_OUT,
                    version=None, reason="execution_timeout",
                ),
            )
        except OSError as error:
            return RuffExecutionResult(
                command=command,
                report=ExecutionReport(stderr=str(error), error_type="startup_error"),
                status=ToolStatus(
                    tool="ruff", state=ToolState.FAILED,
                    version=None, reason="startup_error",
                ),
            )
        stdout = summarize_process_output(completed.stdout)
        stderr = summarize_process_output(completed.stderr)
        report = ExecutionReport(
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            error_type=None if completed.returncode in {0, 1} else "runner_error",
        )
        if "No module named ruff" in f"{stdout}\n{stderr}":
            return RuffExecutionResult(
                command=command,
                report=report,
                status=ToolStatus(
                    tool="ruff", state=ToolState.UNAVAILABLE,
                    version=None, reason="ruff_not_installed",
                ),
            )
        if completed.returncode not in {0, 1}:
            return RuffExecutionResult(
                command=command,
                report=report,
                status=ToolStatus(
                    tool="ruff", state=ToolState.FAILED,
                    version=None, reason="ruff_execution_failed",
                ),
            )
        if len(completed.stdout.encode("utf-8")) > _MAX_RUFF_JSON_BYTES:
            return RuffExecutionResult(
                command=command,
                report=report,
                status=ToolStatus(
                    tool="ruff", state=ToolState.FAILED,
                    version=None, reason="ruff_json_too_large",
                ),
            )
        try:
            payload = json.loads(completed.stdout or "[]")
            findings = parse_ruff_findings(payload, project_root=self.project_root)
        except (UnicodeError, ValueError, json.JSONDecodeError):
            return RuffExecutionResult(
                command=command,
                report=report,
                status=ToolStatus(
                    tool="ruff", state=ToolState.FAILED,
                    version=None, reason="invalid_ruff_json",
                ),
            )
        return RuffExecutionResult(
            command=command,
            report=report,
            status=ToolStatus(
                tool="ruff", state=ToolState.COMPLETED,
                version=self._read_version(timeout), reason=None,
            ),
            findings=findings,
        )
