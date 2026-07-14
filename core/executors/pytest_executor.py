"""pytest 执行器"""
import subprocess
import re

from core.executors.base import BaseExecutor, TestResult

class PytestExecutor(BaseExecutor):
    """调用 pytest 执行测试文件"""
    def can_handle(self, file_path: str) -> bool:
        return file_path.endswith(".py") and ("test_" in file_path or "_test" in file_path)

    def execute(self, file_path: str) -> list[TestResult]:
        # 用 subprocess 跑 pytest，只输出简洁结果
        result = subprocess.run(
            ["python", "-m", "pytest", file_path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return self._parse_output(result.stdout, result.returncode)

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
