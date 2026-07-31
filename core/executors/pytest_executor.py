"""pytest 执行器"""
import platform
import re
import subprocess
import sys

from core.executors.base import (
    BaseExecutor,
    ExecutionEnvironment,
    ExecutionReport,
    TestResult,
    normalize_process_output,
)


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
