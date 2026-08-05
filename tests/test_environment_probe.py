"""受控环境版本探测器测试"""
from subprocess import (
    CompletedProcess,
    TimeoutExpired,
)

import pytest

from core.executors.environment_probe import (
    probe_command,
)
from core.models import (
    EnvironmentCheckState,
)


def test_probe_command_uses_fixed_safe_subprocess_options(tmp_path):
    observed = {}

    # 真实的 subprocess.run(...) 会返回 CompletedProcess
    # 测试使用相同形状，但不会真正启动进程
    # 这能同时验证： 参数数组被正确传递；没有 Shell；cwd 是目标项目; timeout 生效; stdout/stderr 被捕获；没有使用 check=True 把非零退出码提前变成异常
    def fake_runner(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout="pytest 9.0.2\n",
            stderr=""
        )

    result = probe_command(
        name="pytest",
        command=(
            "/venv/bin/python",
            "-m",
            "pytest",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        capabilities=(
            "triage",
            "verify",
        ),
        # 依赖注入。它能测试命令构造，又不依赖开发机是否安装 pytest
        runner=fake_runner,
    )

    assert observed["command"] == [
        "/venv/bin/python",
        "-m",
        "pytest",
        "--version",
    ]
    assert observed["kwargs"] == {
        "cwd": str(tmp_path.resolve()),
        "capture_output": True,
        "text": True,
        "timeout": 10,
        "check": False,
        "shell": False,
    }

    assert result.name == "pytest"
    assert (
        result.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert result.version == "pytest 9.0.2"
    assert (
        result.executable
        == "/venv/bin/python"
    )
    assert result.required is True
    assert result.reason is None
    assert result.capabilities == (
        "triage",
        "verify",
    )

@pytest.mark.parametrize(
    "command",
    [
        (),
        "",
        "python --version",
        ("",),
        ("python", ""),
        ("python", 1),
        ["python", "--version"],
    ],
)
def test_probe_command_rejects_invalid_command(
    tmp_path,
    command,
):
    runner_called = False

    def fake_runner(*args, **kwargs):
        nonlocal runner_called
        runner_called = True
        raise AssertionError(
            "非法命令不应启动子进程"
        )

    with pytest.raises(
        ValueError,
        match="command 必须是非空字符串组成的 tuple",
    ):
        probe_command(
            name="python",
            command=command,
            project_root=tmp_path,
            timeout=10,
            required=True,
            runner=fake_runner,
        )

    assert runner_called is False

@pytest.mark.parametrize(
    "timeout",
    [
        0,
        -1,
        True,
        "10",
        None,
    ],
)
def test_probe_command_rejects_invalid_timeout(
    tmp_path,
    timeout,
):
    runner_called = False

    def fake_runner(*args, **kwargs):
        nonlocal runner_called
        runner_called = True
        raise AssertionError(
            "非法 timeout 不应启动子进程"
        )

    with pytest.raises(
        ValueError,
        match="timeout 必须是大于 0 的数字",
    ):
        probe_command(
            name="python",
            command=(
                "python",
                "--version",
            ),
            project_root=tmp_path,
            timeout=timeout,
            required=True,
            runner=fake_runner,
        )

    assert runner_called is False

def test_probe_command_rejects_missing_project_root(
    tmp_path,
):
    missing = (
        tmp_path
        / "missing"
    )

    with pytest.raises(
        ValueError,
        match="project_root 必须是现有目录",
    ):
        probe_command(
            name="python",
            command=(
                "python",
                "--version",
            ),
            project_root=missing,
            timeout=10,
            required=True,
        )


def test_probe_command_rejects_file_as_project_root(
    tmp_path,
):
    project_file = (
        tmp_path
        / "project.txt"
    )
    project_file.write_text(
        "not a directory\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="project_root 必须是现有目录",
    ):
        probe_command(
            name="python",
            command=(
                "python",
                "--version",
            ),
            project_root=project_file,
            timeout=10,
            required=True,
        )

def test_probe_command_reports_command_not_found(
    tmp_path,
):
    def fake_runner(*args, **kwargs):
        raise FileNotFoundError(
            "command not found"
        )

    result = probe_command(
        name="git",
        command=(
            "git",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=False,
        capabilities=(
            "git_history",
        ),
        runner=fake_runner,
    )

    assert result.name == "git"
    assert (
        result.state
        is EnvironmentCheckState.UNAVAILABLE
    )
    assert result.version is None
    assert result.executable == "git"
    assert result.required is False
    assert (
        result.reason
        == "command_not_found"
    )
    assert result.capabilities == (
        "git_history",
    )

def test_probe_command_reports_timeout(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        raise TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
            output="partial output",
            stderr="partial error",
        )

    result = probe_command(
        name="mypy",
        command=(
            "/venv/bin/python",
            "-m",
            "mypy",
            "--version",
        ),
        project_root=tmp_path,
        timeout=3,
        required=False,
        capabilities=(
            "audit_quality",
        ),
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.TIMED_OUT
    )
    assert result.version is None
    assert (
        result.executable
        == "/venv/bin/python"
    )
    assert result.reason == "probe_timed_out"
    assert result.required is False
    assert result.capabilities == (
        "audit_quality",
    )

def test_probe_command_reports_missing_module(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr=(
                "/venv/bin/python: "
                "No module named ruff\n"
            ),
        )

    result = probe_command(
        name="ruff",
        command=(
            "/venv/bin/python",
            "-m",
            "ruff",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=False,
        capabilities=(
            "audit_quality",
        ),
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.UNAVAILABLE
    )
    assert result.version is None
    assert result.reason == "module_not_found"

def test_probe_command_reports_nonzero_exit(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=2,
            stdout="",
            stderr="broken configuration\n",
        )

    result = probe_command(
        name="pytest",
        command=(
            "/venv/bin/python",
            "-m",
            "pytest",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.FAILED
    )
    assert result.version is None
    assert result.reason == "command_failed"

def test_probe_command_rejects_empty_version_output(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout=" \n",
            stderr="\n",
        )

    result = probe_command(
        name="pytest",
        command=(
            "/venv/bin/python",
            "-m",
            "pytest",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.FAILED
    )
    assert result.version is None
    assert (
        result.reason
        == "version_output_invalid"
    )

def test_probe_command_accepts_version_from_stderr(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout="",
            stderr="Python 3.13.5\n",
        )

    result = probe_command(
        name="python",
        command=(
            "/venv/bin/python",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert result.version == "Python 3.13.5"
    assert result.reason is None

def test_probe_command_keeps_first_nonempty_version_line(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                "\n"
                "pytest 9.0.2\n"
                "plugin warning with /private/path\n"
                "another diagnostic line\n"
            ),
            stderr="",
        )

    result = probe_command(
        name="pytest",
        command=(
            "/venv/bin/python",
            "-m",
            "pytest",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert result.version == "pytest 9.0.2"

def test_probe_command_rejects_oversized_version_line(
    tmp_path,
):
    def fake_runner(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout=("x" * 201) + "\n",
            stderr="",
        )

    result = probe_command(
        name="pytest",
        command=(
            "/venv/bin/python",
            "-m",
            "pytest",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.FAILED
    )
    assert result.version is None
    assert (
        result.reason
        == "version_output_too_large"
    )

def test_probe_command_redacts_unexpected_runner_error(
    tmp_path,
):
    def fake_runner(*args, **kwargs):
        raise RuntimeError(
            "secret=/private/project/.env"
        )

    result = probe_command(
        name="pytest",
        command=(
            "/venv/bin/python",
            "-m",
            "pytest",
            "--version",
        ),
        project_root=tmp_path,
        timeout=10,
        required=True,
        runner=fake_runner,
    )

    assert (
        result.state
        is EnvironmentCheckState.FAILED
    )
    assert result.version is None
    assert result.reason == "probe_exception"
    assert (
        "secret"
        not in result.reason
    )
    assert (
        "/private/project"
        not in result.reason
    )

def test_probe_command_is_publicly_exported():
    from core.executors import (
        probe_command as exported_probe,
    )

    assert exported_probe is probe_command