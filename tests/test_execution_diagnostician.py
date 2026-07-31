import subprocess
import pytest
from core.diagnosticians import (
    diagnose_execution_preflight,
)
from core.executors import PytestExecutor
from core.executors.base import ExecutionReport, ExecutionEnvironment
from core.models import (
    DiagnosisActionKind,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidenceKind,
)


def test_timeout_is_diagnosed_as_infrastructure_defect():
    report = ExecutionReport(
        test_results=[],
        stdout="部分测试输出",
        stderr="pytest timed out",
        exit_code=None,
        timed_out=True,
        error_type="timeout",
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_slow.py",
    )

    assert diagnosis is not None
    assert (
        diagnosis.category
        is DiagnosisCategory.INFRA_DEFECT
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.HIGH
    )
    assert diagnosis.summary == "测试执行超时"

    assert len(diagnosis.evidence) == 1
    assert (
        diagnosis.evidence[0].kind
        is DiagnosisEvidenceKind.RUNNER
    )
    assert diagnosis.evidence[0].source == (
        "execution_report"
    )
    assert "error_type=timeout" in (
        diagnosis.evidence[0].details
    )

    assert diagnosis.locations[0].path == (
        "tests/test_slow.py"
    )
    assert (
        diagnosis.suggested_actions[0].kind
        is DiagnosisActionKind.FIX_INFRASTRUCTURE
    )

    assert diagnosis.category is not (
        DiagnosisCategory.PRODUCT_DEFECT
    )

@pytest.mark.parametrize(
    ("error_type", "summary"),
    [
        (
            "startup_error",
            "测试 Runner 启动失败",
        ),
        (
            "runner_error",
            "测试 Runner 执行失败",
        ),
        (
            "parse_error",
            "测试 Runner 输出解析失败",
        ),
    ],
)
def test_runner_errors_are_infrastructure_defects(
    error_type,
    summary,
):
    report = ExecutionReport(
        test_results=[],
        stdout="",
        stderr="runner failure details",
        exit_code=4,
        error_type=error_type,
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_demo.py",
    )

    assert diagnosis is not None
    assert (
        diagnosis.category
        is DiagnosisCategory.INFRA_DEFECT
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.HIGH
    )
    assert diagnosis.summary == summary

    evidence = diagnosis.evidence[0]
    assert evidence.kind is DiagnosisEvidenceKind.RUNNER
    assert f"error_type={error_type}" in evidence.details
    assert "exit_code=4" in evidence.details
    assert (
        "stderr=runner failure details"
        in evidence.details
    )

    assert (
        diagnosis.suggested_actions[0].kind
        is DiagnosisActionKind.FIX_INFRASTRUCTURE
    )

@pytest.mark.parametrize(
    "report",
    [
        ExecutionReport(
            test_results=[],
            stdout="1 passed",
            stderr="",
            exit_code=0,
            error_type=None,
        ),
        ExecutionReport(
            test_results=[],
            stdout="1 failed",
            stderr="",
            exit_code=1,
            error_type="test_failure",
        ),
    ],
)
def test_preflight_defers_non_infrastructure_results(
    report,
):
    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_demo.py",
    )

    assert diagnosis is None

def test_unknown_execution_error_is_inconclusive():
    report = ExecutionReport(
        test_results=[],
        stdout="",
        stderr="unexpected runner state",
        exit_code=9,
        error_type="unknown_error",
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_demo.py",
    )

    assert diagnosis is not None
    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.LOW
    )
    assert diagnosis.summary == (
        "无法识别测试执行错误"
    )

    evidence = diagnosis.evidence[0]
    assert evidence.kind is DiagnosisEvidenceKind.RUNNER
    assert (
        "error_type=unknown_error"
        in evidence.details
    )
    assert "exit_code=9" in evidence.details

    assert (
        diagnosis.suggested_actions[0].kind
        is DiagnosisActionKind.REQUEST_CONFIRMATION
    )
    assert diagnosis.category is not (
        DiagnosisCategory.PRODUCT_DEFECT
    )

def test_nonzero_exit_without_error_type_is_inconclusive():
    report = ExecutionReport(
        test_results=[],
        stdout="",
        stderr="pytest exited unexpectedly",
        exit_code=3,
        error_type=None,
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_demo.py",
    )

    assert diagnosis is not None
    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.LOW
    )
    assert diagnosis.summary == (
        "无法识别测试执行错误"
    )

    evidence = diagnosis.evidence[0]
    assert (
        "error_type=missing_error_type"
        in evidence.details
    )
    assert "exit_code=3" in evidence.details
    assert diagnosis.category is not (
        DiagnosisCategory.PRODUCT_DEFECT
    )

def test_test_failure_with_inconsistent_exit_is_inconclusive():
    report = ExecutionReport(
        test_results=[],
        stdout="",
        stderr="",
        exit_code=0,
        error_type="test_failure",
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_demo.py",
    )

    assert diagnosis is not None
    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.LOW
    )

    evidence = diagnosis.evidence[0]
    assert (
        "error_type=inconsistent_test_failure"
        in evidence.details
    )
    assert "exit_code=0" in evidence.details

def test_pytest_executor_reports_no_tests_collected(
    monkeypatch,
):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=5,
            stdout="no tests ran",
            stderr="",
        )

    monkeypatch.setattr(
        "core.executors.pytest_executor.subprocess.run",
        fake_run,
    )

    executor = PytestExecutor(cwd="/demo")
    report = executor.execute(
        "test_empty.py"
    )

    assert report.test_results == []
    assert report.exit_code == 5
    assert report.error_type == (
        "no_tests_collected"
    )
    assert report.successful is False

def test_no_tests_collected_is_inconclusive():
    report = ExecutionReport(
        test_results=[],
        stdout="no tests ran",
        stderr="",
        exit_code=5,
        error_type="no_tests_collected",
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_empty.py",
    )

    assert diagnosis is not None
    assert (
        diagnosis.category
        is DiagnosisCategory.INCONCLUSIVE
    )
    assert (
        diagnosis.confidence
        is DiagnosisConfidence.LOW
    )
    assert diagnosis.summary == (
        "未收集到可执行测试"
    )

    evidence = diagnosis.evidence[0]
    assert (
        evidence.kind
        is DiagnosisEvidenceKind.TEST_VALIDATION
    )
    assert (
        "error_type=no_tests_collected"
        in evidence.details
    )
    assert "exit_code=5" in evidence.details

    assert (
        diagnosis.suggested_actions[0].kind
        is DiagnosisActionKind.FIX_TEST
    )
    assert diagnosis.category is not (
        DiagnosisCategory.PRODUCT_DEFECT
    )

def test_infrastructure_diagnosis_includes_environment():
    report = ExecutionReport(
        test_results=[],
        stdout="",
        stderr="runner failed",
        exit_code=4,
        error_type="runner_error",
        environment=ExecutionEnvironment(
            runner="pytest",
            runtime="python",
            runtime_version="3.13.5",
            working_directory="/demo",
        ),
    )

    diagnosis = diagnose_execution_preflight(
        report=report,
        test_file="tests/test_demo.py",
    )

    assert diagnosis is not None
    assert len(diagnosis.evidence) == 2

    environment_evidence = diagnosis.evidence[1]
    assert (
        environment_evidence.kind
        is DiagnosisEvidenceKind.ENVIRONMENT
    )
    assert environment_evidence.source == (
        "execution_environment"
    )
    assert environment_evidence.details == (
        "runner=pytest",
        "runtime=python",
        "runtime_version=3.13.5",
        "working_directory=/demo",
    )