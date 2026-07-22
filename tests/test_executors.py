import subprocess

from core.executors import select_executor, VitestExecutor
from core.executors.base import ExecutionReport, BaseExecutor, TestResult
from core.executors.pytest_executor import PytestExecutor

def test_select_executor_returns_pytest_executor():
    selection = select_executor(
        framework="pytest",
        cwd="/demo"
    )

    assert selection.supported is True
    assert isinstance(selection.executor, PytestExecutor)
    assert selection.executor.cwd == "/demo"
    assert selection.reason == ""

def test_select_executor_returns_explainable_unsupported_result():
    selection = select_executor(
        framework="jest",
        cwd="/demo"
    )

    assert selection.supported is False
    assert selection.executor is None
    assert selection.reason == "不支持的测试框架: jest"

def test_select_executor_returns_vitest_executor():
    selection = select_executor(
        framework="vitest",
        cwd="/frontend"
    )

    assert selection.supported is True
    assert isinstance(selection.executor, VitestExecutor)
    assert selection.executor.cwd == "/frontend"
    assert selection.reason == ""

def test_execution_report_distinguishes_runner_failure_from_success():
    failed_report = ExecutionReport(
        test_results = [],
        stdout = "",
        stderr = "ERROR: test file not found",
        exit_code=4, # 命令执行失败
        error_type="runner_error",
    )

    successful_report = ExecutionReport(
        test_results = [],
        stdout = "no tests collected",
        stderr = "",
        exit_code = 0, # 命令正常完成，只是没有测试结果
        error_type = None,
    )

    assert failed_report.successful is False
    assert failed_report.exit_code == 4
    assert failed_report.stderr == "ERROR: test file not found"

    assert successful_report.successful is True

def test_pytest_executor_reports_runner_failure(monkeypatch):
    def fake_fun(*args, **kwargs):
        # subprocess.CompletedProcess 是 subprocess.run() 正常返回的结果类型。
        # 模拟一个假进程，pytest 的退出码 4 表示命令用法或调用层面的错误，不是普通测试断言失败
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=4,
            stdout="",
            stderr="ERROR: test file not found",
        )

    monkeypatch.setattr("core.executors.pytest_executor.subprocess.run", fake_fun)

    executor = PytestExecutor(cwd="/demo")
    report = executor.execute("missing_test.py")

    assert report.test_results == []
    assert report.stdout == ""
    assert report.stderr == "ERROR: test file not found"
    assert report.exit_code == 4
    assert report.error_type == "runner_error"
    assert report.successful is False