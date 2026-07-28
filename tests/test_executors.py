import subprocess

from core.executors import select_executor, VitestExecutor
from core.executors.base import ExecutionReport, BaseExecutor, TestResult as ExecutionTestResult
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

def test_pytest_executor_reports_startup_error(monkeypatch):
    """测试 Runner 启动失败"""
    def fail_run(*args, **kwargs):
        raise FileNotFoundError("python executable not found")

    monkeypatch.setattr("core.executors.pytest_executor.subprocess.run", fail_run)

    executor = PytestExecutor(cwd="/demo")
    report = executor.execute("test_demo.py")

    assert report.test_results == []
    assert report.exit_code is None
    assert report.error_type == "startup_error"
    assert report.stderr == "python executable not found"
    assert report.successful is False

def test_pytest_executor_reports_timeout(monkeypatch):
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=120,
            output=b"partial output", # b"" 表示字节数据，类型是 bytes
            stderr=b"pytest timed out"
        )

    monkeypatch.setattr("core.executors.pytest_executor.subprocess.run", timeout_run)

    executor = PytestExecutor(cwd="/demo")
    report = executor.execute("test_slow.py")

    assert report.test_results == []
    assert report.stdout == "partial output"
    assert report.stderr == "pytest timed out"
    assert report.exit_code is None
    assert report.timed_out is True
    assert report.error_type == "timeout"
    assert report.successful is False

def test_vitest_executor_reports_runner_failure(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=2,
            stdout="",
            stderr="vitest configuration error",
        )
    monkeypatch.setattr("core.executors.vitest_executor.subprocess.run", fake_run)

    executor = VitestExecutor(cwd="/frontend")
    report = executor.execute("demo.test.ts")

    assert report.test_results == []
    assert report.stdout == ""
    assert report.stderr == "vitest configuration error"
    assert report.exit_code == 2
    assert report.error_type == "runner_error"
    assert report.successful is False

def test_vitest_executor_reports_startup_error(monkeypatch):
    def fail_run(*args, **kwargs):
        raise FileNotFoundError("npx executable not found")
    monkeypatch.setattr("core.executors.vitest_executor.subprocess.run", fail_run)
    executor = VitestExecutor(cwd="/frontend")
    report = executor.execute("demo.test.ts")
    assert report.test_results == []
    assert report.stdout == ""
    # 如果系统没有安装 Node.js/npm , npx 不存在。subprocess.run() 会抛出 FileNotFoundError
    assert report.stderr == "npx executable not found"
    assert report.exit_code is None
    assert report.error_type == "startup_error"
    assert report.successful is False

def test_vitest_executor_reports_timeout_without_output(monkeypatch):
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=120,
            output=None,
            stderr=None
        )

    monkeypatch.setattr("core.executors.vitest_executor.subprocess.run", timeout_run)

    executor = VitestExecutor(cwd="/frontend")
    report = executor.execute("slow.test.ts")

    assert report.test_results == []
    assert report.stdout == ""
    assert "timed out" in report.stderr
    assert report.exit_code is None
    assert report.timed_out is True
    assert report.error_type == "timeout"
    assert report.successful is False

def test_vitest_executor_reports_parse_error(monkeypatch):
    """Runner 可能正常退出或产生 stdout，但输出不是预期JSON，这种情况不能让异常直接冲出执行器"""
    def fake_run(*args, **kwargs):
        # CompletedProcess 是普通返回结果对象，不是异常类，因此不能使用 raise.
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="this is not json",
            stderr="",
        )

    monkeypatch.setattr("core.executors.vitest_executor.subprocess.run", fake_run)
    executor = VitestExecutor(cwd="/frontend")
    report = executor.execute("demo.test.ts")
    assert report.test_results == []
    assert report.stdout == "this is not json"
    assert report.exit_code == 0
    assert report.error_type == "parse_error"
    assert "解析失败" in report.stderr
    assert report.successful is False

def test_select_executor_rejects_language_framework_mismatch():
    selection = select_executor(
        framework="pytest",
        language="javascript",
        cwd="/frontend",
    )

    assert selection.supported is False
    assert selection.executor is None
    assert selection.reason == (
        "不支持的执行器组合: "
        "language=javascript, framework=pytest"
    )