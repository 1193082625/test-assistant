"""vitest 执行器"""
import json
import subprocess

from core.executors.base import BaseExecutor, TestResult

class VitestExecutor(BaseExecutor):
    """调用 vitest 执行测试文件"""
    def __init__(self, cwd: str | None = None) -> None:
        self.cwd = cwd
    def can_handle(self, file_path: str) -> bool:
        # endswith 可以传元组 匹配多个后缀
        return file_path.endswith((".test.ts", ".test.tsx", ".spec.js", ".test.js"))

    def execute(self, file_path: str) -> list[TestResult]:
        """
        用 subprocess 跑 vitest，只输出简洁结果
        vitest 是前端测试框架，基于 Vite，兼容 Jest API。常用于 React/Vue 项目
        """
        result = subprocess.run(
            ["npx", "vitest", "run", file_path, "--reporter", "json"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.cwd,
        )

        # vitest 执行失败 --> 打印错误，返回空
        if result.returncode != 0:
            print(f"⚠ vitest 执行失败: {file_path}")
            print(result.stderr)
            return []

        return self._parse_json_output(result.stdout)

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