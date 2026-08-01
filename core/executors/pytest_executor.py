"""pytest 执行器"""
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

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
    ) -> PytestSuiteResult:
        """执行 pytest 套件，并通过 hook JSON 返回结构化事件。"""
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
            command = [sys.executable, "-m", "pytest"]
            if test_path is not None:
                command.append(test_path)
            command.extend([
                "-q",
                "--tb=short",
                "-p",
                "core.executors.pytest_capture_plugin",
                "--test-assistant-json",
                str(event_path),
            ])
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=self.cwd,
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
