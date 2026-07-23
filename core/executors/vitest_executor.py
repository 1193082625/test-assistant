"""vitest 执行器"""
import json
import subprocess

from core.executors.base import BaseExecutor, TestResult, ExecutionReport, normalize_process_output


class VitestExecutor(BaseExecutor):
    """调用 vitest 执行测试文件"""
    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd
    def can_handle(self, file_path: str) -> bool:
        # endswith 可以传元组 匹配多个后缀
        return file_path.endswith((".test.ts", ".test.tsx", ".spec.js", ".test.js"))

    def execute(self, file_path: str) -> ExecutionReport:
        """
        用 subprocess 跑 vitest，只输出简洁结果
        vitest 是前端测试框架，基于 Vite，兼容 Jest API。常用于 React/Vue 项目
        """
        try:
            result = subprocess.run(
                ["npx", "vitest", "run", file_path, "--reporter", "json"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired as error:
            return ExecutionReport(
                test_results=[],
                stdout=normalize_process_output(error.stdout),
                stderr=normalize_process_output(error.stderr) or str(error),
                exit_code=None,
                timed_out=True,
                error_type="timeout",
            )
        except OSError as error:
            return ExecutionReport(
                test_results=[],
                stdout="",
                stderr=str(error) or "",
                exit_code=None,
                error_type="startup_error",
            )

        test_result = []
        error_type = None

        try:
            # vitest 执行失败 --> 打印错误，返回空
            if result.returncode == 0:
                test_result = self._parse_json_output(result.stdout)
            elif result.returncode == 1:
                # 测试断言失败并不代表报告无效，所以这里也尝试解析
                error_type = "test_failure"
                if result.stdout.strip():
                    test_result = self._parse_json_output(result.stdout)
            else:
                error_type = "runner_error"
        except (ValueError, TypeError, KeyError) as error:
            return ExecutionReport(
                test_results=[],
                stdout=result.stdout,
                stderr=(
                    result.stderr or f"Vitest JSON 解析失败：{error}"
                ),
                exit_code=result.returncode,
                error_type="parse_error",
            )

        return ExecutionReport(
            test_results=test_result,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            error_type=error_type,
        )

    def _parse_json_output(self, json_str: str) -> list[TestResult]:
        """
        解析 vitest 的 输出

         vitest 的 JSON reporter 输出结构：
         层级结构： 文件级 -> 用例级（嵌套）
         {
           "testResults": [
             {
               "name": "test/utils/format.test.ts",
               "status": "pass", # 文件级是 pass/fail，用例级是 passed/failed/pending；其中pending 本质表示「这条用例没有实际执行」
               "duration": 42,
               "assertionResults": [
                 { "title": "should format date", "status": "passed", "duration": 5 },
                 { "title": "should handle null", "status": "failed", "duration": 3 }
               ]
             }
           ]
         }
         """
        results = []
        json_data = json.loads(json_str)
        _status_map = {"passed": "passed", "failed": "failed", "pending": "skipped"}
        for file_result in json_data["testResults"]:
            for item in file_result["assertionResults"]:
                results.append(TestResult(
                    name=item["title"],
                    status=_status_map.get(item["status"], "error"),
                    duration=item["duration"],
                ))
        return results