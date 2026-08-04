"""pytest 执行器"""
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

from core.executors.base import (
    BaseExecutor,
    ExecutionEnvironment,
    ExecutionReport,
    PytestSuiteResult,
    TestResult,
    normalize_process_output,
    summarize_process_output,
)
from core.models import PytestIssue, TriagePhase


class PytestExecutor(BaseExecutor):
    """调用 pytest 执行测试文件"""

    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd

    def can_handle(self, file_path: str) -> bool:
        return (
            file_path.endswith(".py")
            and ("test_" in file_path or "_test" in file_path)
        )

    def execute(self, file_path: str) -> ExecutionReport:
        environment = ExecutionEnvironment(
            runner="pytest",
            runtime="python",
            runtime_version=platform.python_version(),
            working_directory=self.cwd,
        )
        try:
            # 用 subprocess 跑 pytest，只输出简洁结果
            result = subprocess.run(
                [sys.executable, "-m", "pytest", file_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.cwd,
            )
        # 超时必须放在正常报告之外，因为它没有可靠的进程退出码
        except subprocess.TimeoutExpired as error:
            return ExecutionReport(
                test_results=[],
                stdout=normalize_process_output(error.stdout),
                stderr=normalize_process_output(error.stderr) or str(error),
                exit_code=None,
                timed_out=True,
                error_type="timeout",
                environment=environment,
            )
        # FileNotFoundError 是 OSError 的子类。除了命令不存在，工作目录不存在、权限不足等启动层错误也通常属于 OSError
        except OSError as error:
            return ExecutionReport(
                test_results=[],
                stdout="",
                stderr=str(error),
                exit_code=None,
                error_type="startup_error",
                environment=environment,
            )

        # 解析出的每一条测试用例结果
        test_results = self._parse_output(result.stdout, result.returncode)

        error_type = None

        # error_type 表示整个 pytest 命令是否正常完成
        if result.returncode == 1:
            error_type = "test_failure"
        elif result.returncode == 5:
            error_type = "no_tests_collected"
        elif result.returncode != 0:
            error_type = "runner_error"

        return ExecutionReport(
            test_results=test_results,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            error_type=error_type,
            environment=environment,
        )

    def execute_suite(
        self,
        test_path: str | None = None,
        timeout: float = 120,
        max_failures: int | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> PytestSuiteResult:
        """执行 pytest 套件，并通过 hook JSON 返回结构化事件。"""
        if (
            max_failures is not None
            and (
                not isinstance(max_failures, int)
                or isinstance(max_failures, bool)
                or max_failures < 1
            )
        ):
            raise ValueError("max_failures 必须是正整数或 None")
        environment = ExecutionEnvironment(
            runner="pytest",
            runtime="python",
            runtime_version=platform.python_version(),
            working_directory=self.cwd,
        )
        with tempfile.TemporaryDirectory(
            prefix="test-assistant-pytest-"
        ) as temporary_directory:
            event_path = Path(temporary_directory) / "events.json"
            progress_path = Path(temporary_directory) / "progress.jsonl"
            command = [sys.executable, "-m", "pytest"]
            if test_path is not None:
                command.append(test_path)
            if max_failures is not None:
                command.append(f"--maxfail={max_failures}")
            command.extend([
                "-q",
                "--tb=short",
                "-p",
                "core.executors.pytest_capture_plugin",
                "--test-assistant-json",
                str(event_path),
                "--test-assistant-progress-jsonl",
                str(progress_path),
            ])
            try:
                if progress_callback is None:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=self.cwd,
                    )
                else:
                    result = self._run_with_progress(
                        command=command,
                        timeout=timeout,
                        progress_path=progress_path,
                        progress_callback=progress_callback,
                    )
            except subprocess.TimeoutExpired as error:
                report = ExecutionReport(
                    stdout=summarize_process_output(error.stdout),
                    stderr=(
                        summarize_process_output(error.stderr)
                        or str(error)
                    ),
                    exit_code=None,
                    timed_out=True,
                    error_type="timeout",
                    environment=environment,
                )
                return PytestSuiteResult(
                    report=report,
                    issues=(PytestIssue(
                        phase=TriagePhase.EXECUTION,
                        outcome="timeout",
                        message=report.stderr,
                        stage="session",
                        exception_type="TimeoutExpired",
                    ),),
                )
            except OSError as error:
                report = ExecutionReport(
                    stderr=str(error),
                    exit_code=None,
                    error_type="startup_error",
                    environment=environment,
                )
                return PytestSuiteResult(
                    report=report,
                    issues=(PytestIssue(
                        phase=TriagePhase.EXECUTION,
                        outcome="error",
                        message=str(error),
                        stage="startup",
                        exception_type=type(error).__name__,
                    ),),
                )

            error_type = self._error_type(result.returncode)
            try:
                payload = json.loads(event_path.read_text(encoding="utf-8"))
                raw_events = payload["events"]
                if not isinstance(raw_events, list):
                    raise ValueError("events must be a list")
                issues = tuple(
                    PytestIssue.from_dict(event)
                    for event in raw_events
                )
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                report = ExecutionReport(
                    stdout=summarize_process_output(result.stdout),
                    stderr=summarize_process_output(
                        result.stderr
                        + f"\npytest 结构化结果解析失败: {error}"
                    ).strip(),
                    exit_code=result.returncode,
                    error_type="parse_error",
                    environment=environment,
                )
                return PytestSuiteResult(report=report)

            test_results = self._test_results_from_events(
                raw_events
            )
            report = ExecutionReport(
                test_results=test_results,
                stdout=summarize_process_output(result.stdout),
                stderr=summarize_process_output(result.stderr),
                exit_code=result.returncode,
                error_type=error_type,
                environment=environment,
            )
            return PytestSuiteResult(report=report, issues=issues)

    def _run_with_progress(
        self,
        *,
        command: list[str],
        timeout: float,
        progress_path: Path,
        progress_callback: Callable[[dict[str, object]], None],
    ) -> subprocess.CompletedProcess[str]:
        """捕获最终输出，同时读取插件追加的增量 JSONL 事件。"""
        started = time.monotonic()
        offset = 0
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
                process = subprocess.Popen(
                    command,
                    cwd=self.cwd,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    start_new_session=(os.name != "nt"),
                )
                try:
                    while process.poll() is None:
                        if time.monotonic() - started > timeout:
                            self._terminate_process_tree(process)
                            raise subprocess.TimeoutExpired(
                                command, timeout
                            )
                        offset = self._emit_progress_events(
                            progress_path,
                            offset,
                            progress_callback,
                        )
                        time.sleep(0.1)
                    offset = self._emit_progress_events(
                        progress_path,
                        offset,
                        progress_callback,
                    )
                except BaseException:
                    if process.poll() is None:
                        self._terminate_process_tree(process)
                    raise
                stdout.seek(0)
                stderr.seek(0)
                return subprocess.CompletedProcess(
                    command,
                    process.returncode,
                    stdout.read(),
                    stderr.read(),
                )

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        """终止 pytest 及其子进程，避免超时或 Ctrl+C 后留下孤儿进程。"""
        if process.poll() is not None:
            return
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2)
                return
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        else:
            process.kill()
        process.wait()

    @staticmethod
    def _emit_progress_events(
        path: Path,
        offset: int,
        callback: Callable[[dict[str, object]], None],
    ) -> int:
        if not path.exists():
            return offset
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(offset)
            for line in stream:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    callback(payload)
            return stream.tell()

    @staticmethod
    def _error_type(returncode: int) -> str | None:
        if returncode == 0:
            return None
        if returncode == 1:
            return "test_failure"
        if returncode == 5:
            return "no_tests_collected"
        return "runner_error"

    @staticmethod
    def _test_results_from_events(
        events: list[dict[str, object]],
    ) -> list[TestResult]:
        results: list[TestResult] = []
        for event in events:
            if event.get("phase") != "execution":
                continue
            stage = event.get("stage")
            status = event.get("outcome")
            if (
                stage == "call"
                or status in {"error", "skipped"}
            ):
                results.append(TestResult(
                    name=str(event.get("node_id") or "pytest"),
                    status=str(status),
                    duration=float(event.get("duration") or 0.0),
                    message=str(event.get("message") or ""),
                ))
        return results

    def _parse_output(self, stdout: str, returncode: int) -> list[TestResult]:
        """解析 pytest 的 -v 输出"""
        results = []
        # 匹配形如：test_module.py::test_func PASSED 或 FAILED
        pattern = re.compile(r"(.+)::(.+) (PASSED|FAILED|SKIP)")
        for line in stdout.splitlines():
            match = pattern.search(line)
            if match:
                status_map = {"PASSED": "passed", "FAILED": "failed", "SKIP": "skipped"}
                results.append(TestResult(
                    name=match.group(2),
                    status=status_map.get(match.group(3), "error"),
                    duration=0.0,
                ))
        return results
