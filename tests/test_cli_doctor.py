"""Doctor CLI 测试。"""
import json
from dataclasses import replace

import pytest
from click.testing import CliRunner

import cli.commands.doctor as doctor_module
from cli.main import cli
from core.models import (
    DoctorResult,
    DoctorStatus,
    EnvironmentCheck,
    EnvironmentCheckState,
)


def _healthy_result() -> DoctorResult:
    return DoctorResult(
        schema_version=1,
        status=DoctorStatus.HEALTHY,
        test_assistant_version="0.6.2",
        project_path="/project",
        python_implementation="cpython",
        platform="macOS-15-arm64",
        checks=(
            EnvironmentCheck(
                name="python",
                state=(
                    EnvironmentCheckState.AVAILABLE
                ),
                version="3.13.5",
                executable="/venv/bin/python",
                required=True,
                capabilities=(
                    "cli",
                    "triage",
                ),
            ),
            EnvironmentCheck(
                name="ruff",
                state=(
                    EnvironmentCheckState.UNAVAILABLE
                ),
                version=None,
                executable="/venv/bin/python",
                required=False,
                reason="module_not_found",
                capabilities=(
                    "audit_quality",
                ),
            ),
        ),
    )

def test_doctor_help_is_registered():
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "doctor",
            "--help",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "环境" in result.output
    assert "--path" in result.output
    assert "--json" in result.output
    assert "--timeout" in result.output

def test_doctor_cli_renders_environment_summary(
    tmp_path,
    monkeypatch,
):
    observed = {}

    def fake_run_doctor(**kwargs):
        observed.update(kwargs)
        return _healthy_result()

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        fake_run_doctor,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(tmp_path),
            "--timeout",
            "5",
        ],
    )

    assert result.exit_code == 0, result.output

    assert "Doctor 状态: healthy" in result.output
    assert (
        "test-assistant: 0.6.2"
        in result.output
    )
    assert "项目路径: /project" in result.output
    assert "Python 实现: cpython" in result.output
    assert "平台: macOS-15-arm64" in result.output

    assert "python: available" in result.output
    assert "版本=3.13.5" in result.output
    assert "核心" in result.output
    assert "能力=cli,triage" in result.output

    assert "ruff: unavailable" in result.output
    assert "原因=module_not_found" in result.output
    assert "可选" in result.output
    assert "能力=audit_quality" in result.output

    assert observed["project_root"] == (
        tmp_path
    )
    assert observed["timeout"] == 5.0

def test_doctor_cli_outputs_pure_json(
    tmp_path,
    monkeypatch,
):
    expected = _healthy_result()

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        lambda **kwargs: expected,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert payload == expected.to_dict()

    assert "Doctor 状态:" not in result.output
    assert "环境检查:" not in result.output

@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [
        (
            DoctorStatus.INCOMPATIBLE,
            1,
        ),
        (
            DoctorStatus.INFRA_ERROR,
            2,
        ),
    ],
)
@pytest.mark.parametrize(
    "json_output",
    [
        False,
        True,
    ],
)
def test_doctor_cli_maps_status_to_exit_code(
    tmp_path,
    monkeypatch,
    status,
    expected_exit_code,
    json_output,
):
    doctor_result = replace(
        _healthy_result(),
        status=status,
    )

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        lambda **kwargs: doctor_result,
    )

    arguments = [
        "doctor",
        "--path",
        str(tmp_path),
    ]
    if json_output:
        arguments.append("--json")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        arguments,
    )

    assert (
        result.exit_code
        == expected_exit_code
    ), result.output

    if json_output:
        payload = json.loads(result.output)
        assert payload["status"] == status.value
    else:
        assert (
            f"Doctor 状态: {status.value}"
            in result.output
        )


@pytest.mark.parametrize(
    "error",
    [
        ValueError(
            "secret=/private/project/.env"
        ),
        OSError(
            "token=very-secret-token"
        ),
        TypeError(
            "unexpected internal value"
        ),
    ],
)
def test_doctor_cli_redacts_workflow_errors(
    tmp_path,
    monkeypatch,
    error,
):
    def fail_run_doctor(**kwargs):
        raise error

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        fail_run_doctor,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "环境诊断失败" in result.output
    assert "secret" not in result.output
    assert "/private/project" not in result.output
    assert "very-secret-token" not in result.output
    assert "Traceback" not in result.output


def test_doctor_cli_rejects_missing_path_before_workflow(
    tmp_path,
    monkeypatch,
):
    workflow_called = False

    def fake_run_doctor(**kwargs):
        nonlocal workflow_called
        workflow_called = True
        return _healthy_result()

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        fake_run_doctor,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(tmp_path / "missing"),
        ],
    )

    assert result.exit_code == 2, result.output
    assert workflow_called is False


def test_doctor_cli_rejects_file_path_before_workflow(
    tmp_path,
    monkeypatch,
):
    project_file = tmp_path / "project.txt"
    project_file.write_text(
        "not a directory\n",
        encoding="utf-8",
    )
    workflow_called = False

    def fake_run_doctor(**kwargs):
        nonlocal workflow_called
        workflow_called = True
        return _healthy_result()

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        fake_run_doctor,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(project_file),
        ],
    )

    assert result.exit_code == 2, result.output
    assert workflow_called is False


def test_doctor_cli_rejects_invalid_timeout_before_workflow(
    tmp_path,
    monkeypatch,
):
    workflow_called = False

    def fake_run_doctor(**kwargs):
        nonlocal workflow_called
        workflow_called = True
        return _healthy_result()

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        fake_run_doctor,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(tmp_path),
            "--timeout",
            "0",
        ],
    )

    assert result.exit_code == 2, result.output
    assert workflow_called is False


def test_doctor_cli_does_not_write_project(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "app.py"
    source_path.write_text(
        "value = 1\n",
        encoding="utf-8",
    )
    existing_record = (
        tmp_path
        / ".autotest"
        / "existing.json"
    )
    existing_record.parent.mkdir()
    existing_record.write_text(
        '{"existing": true}\n',
        encoding="utf-8",
    )

    before_paths = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
    }
    before_files = {
        path.relative_to(tmp_path).as_posix(): (
            path.read_bytes()
        )
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    monkeypatch.setattr(
        doctor_module,
        "run_doctor",
        lambda **kwargs: _healthy_result(),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "doctor",
            "--path",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output

    after_paths = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
    }
    after_files = {
        path.relative_to(tmp_path).as_posix(): (
            path.read_bytes()
        )
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert after_paths == before_paths
    assert after_files == before_files
