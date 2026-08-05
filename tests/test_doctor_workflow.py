"""Doctor 环境诊断工作流测试"""

import sys
from types import SimpleNamespace

import pytest

import core.workflows.doctor as doctor_module
from cli import __version__
from core.models import (
    DoctorStatus,
    EnvironmentCheck,
    EnvironmentCheckState,
)
from core.workflows.doctor import (
    run_doctor,
)


def _check(
    state: EnvironmentCheckState,
    *,
    required: bool,
) -> EnvironmentCheck:
    reason = (
        None
        if state
        is EnvironmentCheckState.AVAILABLE
        else "test_reason"
    )

    return EnvironmentCheck(
        name=f"tool-{state.value}",
        state=state,
        version=(
            "1.0"
            if state
            is EnvironmentCheckState.AVAILABLE
            else None
        ),
        executable=None,
        required=required,
        reason=reason,
    )


def test_run_doctor_reports_healthy_environment(
    tmp_path,
    monkeypatch,
):
    python_check = EnvironmentCheck(
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
            "verify",
            "audit",
        ),
    )

    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: python_check,
    )

    observed = []

    def fake_probe(**kwargs):
        observed.append(kwargs)

        version = (
            "true"
            if kwargs["name"] == "git-worktree"
            else f"{kwargs['name']} 1.0"
        )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version=version,
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        timeout=10,
        probe=fake_probe,
    )

    assert result.status is DoctorStatus.HEALTHY

    checks = {
        check.name: check
        for check in result.checks
    }
    assert set(checks) == {
        "python",
        "pytest",
        "git",
        "git-worktree",
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    }

    assert checks["python"] == python_check
    assert (
        checks["pytest"].state
        is EnvironmentCheckState.AVAILABLE
    )
    assert checks["pytest"].required is True

    for name in (
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    ):
        assert (
            checks[name].state
            is EnvironmentCheckState.AVAILABLE
        )
        assert checks[name].required is False

    assert [
        call["name"]
        for call in observed
    ] == [
        "pytest",
        "git",
        "git-worktree",
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    ]

    pytest_call = observed[0]
    assert pytest_call["command"] == (
        sys.executable,
        "-m",
        "pytest",
        "--version",
    )
    assert pytest_call["project_root"] == (
        tmp_path.resolve()
    )
    assert pytest_call["timeout"] == 10
    assert (
        checks["git"].state
        is EnvironmentCheckState.AVAILABLE
    )
    assert (
        checks["git-worktree"].state
        is EnvironmentCheckState.AVAILABLE
    )


def test_run_doctor_collects_python_and_pytest(
    tmp_path,
    monkeypatch,
):
    python_check = EnvironmentCheck(
        name="python",
        state=EnvironmentCheckState.AVAILABLE,
        version="3.13.5",
        executable="/venv/bin/python",
        required=True,
        capabilities=(
            "cli",
            "triage",
            "verify",
            "audit",
        ),
    )

    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: python_check,
    )

    observed = []

    def fake_probe(**kwargs):
        observed.append(kwargs)

        version = (
            "true"
            if kwargs["name"] == "git-worktree"
            else "pytest 9.0.2"
        )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version=version,
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        timeout=5,
        probe=fake_probe,
    )

    assert result.schema_version == 1
    assert result.status is DoctorStatus.HEALTHY
    assert (
        result.test_assistant_version
        == __version__
    )
    assert result.project_path == str(
        tmp_path.resolve()
    )

    checks = {
        check.name: check
        for check in result.checks
    }

    assert set(checks) == {
        "python",
        "pytest",
        "git",
        "git-worktree",
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    }

    collected_python = checks["python"]
    assert (
            collected_python.state
            is EnvironmentCheckState.AVAILABLE
    )
    assert collected_python.required is True
    assert (
            collected_python.executable
            == "/venv/bin/python"
    )
    assert "cli" in collected_python.capabilities

    pytest_check = checks["pytest"]
    assert (
        pytest_check.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert pytest_check.version == "pytest 9.0.2"
    assert pytest_check.required is True
    assert "triage" in pytest_check.capabilities

    assert [
       call["name"]
       for call in observed
   ] == [
        "pytest",
        "git",
        "git-worktree",
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
   ]
    assert observed[0]["name"] == "pytest"
    assert observed[0]["command"] == (
        sys.executable,
        "-m",
        "pytest",
        "--version",
    )
    assert observed[0]["project_root"] == (
        tmp_path.resolve()
    )
    assert observed[0]["timeout"] == 5


def test_python_check_reports_unsupported_version(
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module.sys,
        "version_info",
        SimpleNamespace(
            major=3,
            minor=12,
        ),
    )
    monkeypatch.setattr(
        doctor_module.sys,
        "executable",
        "/venv/bin/python",
    )
    monkeypatch.setattr(
        doctor_module.platform,
        "python_version",
        lambda: "3.12.9",
    )

    result = doctor_module._python_check()

    assert result.name == "python"
    assert (
        result.state
        is EnvironmentCheckState.INCOMPATIBLE
    )
    assert result.version == "3.12.9"
    assert (
        result.executable
        == "/venv/bin/python"
    )
    assert result.required is True
    assert (
        result.reason
        == "unsupported_python_version"
    )


def test_run_doctor_reports_incompatible_python(
    tmp_path,
    monkeypatch,
):
    incompatible_python = EnvironmentCheck(
        name="python",
        state=(
            EnvironmentCheckState.INCOMPATIBLE
        ),
        version="3.12.9",
        executable="/venv/bin/python",
        required=True,
        reason="unsupported_python_version",
        capabilities=(
            "cli",
            "triage",
            "verify",
            "audit",
        ),
    )

    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: incompatible_python,
    )

    def fake_probe(**kwargs):
        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="pytest 9.0.2",
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    assert (
        result.status
        is DoctorStatus.INCOMPATIBLE
    )


@pytest.mark.parametrize(
    "optional_state",
    [
        EnvironmentCheckState.UNAVAILABLE,
        EnvironmentCheckState.INCOMPATIBLE,
        EnvironmentCheckState.TIMED_OUT,
        EnvironmentCheckState.FAILED,
        EnvironmentCheckState.NOT_APPLICABLE,
    ],
)
def test_doctor_status_allows_optional_degradation(
    optional_state,
):
    checks = (
        _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
        _check(
            optional_state,
            required=False,
        ),
    )

    assert (
        doctor_module._doctor_status(checks)
        is DoctorStatus.HEALTHY
    )


@pytest.mark.parametrize(
    "required_state",
    [
        EnvironmentCheckState.UNAVAILABLE,
        EnvironmentCheckState.INCOMPATIBLE,
        EnvironmentCheckState.NOT_APPLICABLE,
    ],
)
def test_doctor_status_reports_required_incompatibility(
    required_state,
):
    checks = (
        _check(
            required_state,
            required=True,
        ),
    )

    assert (
        doctor_module._doctor_status(checks)
        is DoctorStatus.INCOMPATIBLE
    )


@pytest.mark.parametrize(
    "required_state",
    [
        EnvironmentCheckState.TIMED_OUT,
        EnvironmentCheckState.FAILED,
    ],
)
def test_doctor_status_reports_required_infra_error(
    required_state,
):
    checks = (
        _check(
            required_state,
            required=True,
        ),
    )

    assert (
        doctor_module._doctor_status(checks)
        is DoctorStatus.INFRA_ERROR
    )


def test_doctor_status_prioritizes_infra_error():
    checks = (
        _check(
            EnvironmentCheckState.INCOMPATIBLE,
            required=True,
        ),
        _check(
            EnvironmentCheckState.FAILED,
            required=True,
        ),
    )

    assert (
        doctor_module._doctor_status(checks)
        is DoctorStatus.INFRA_ERROR
    )


def test_run_doctor_stays_healthy_when_optional_tools_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
    )

    def fake_probe(**kwargs):
        if kwargs["name"] == "pytest":
            return EnvironmentCheck(
                name="pytest",
                state=(
                    EnvironmentCheckState.AVAILABLE
                ),
                version="pytest 9.0.2",
                executable=kwargs["command"][0],
                required=True,
                capabilities=kwargs["capabilities"],
            )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.UNAVAILABLE
            ),
            version=None,
            executable=kwargs["command"][0],
            required=False,
            reason="module_not_found",
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    assert result.status is DoctorStatus.HEALTHY

    checks = {
        check.name: check
        for check in result.checks
    }

    assert (
        checks["pytest"].state
        is EnvironmentCheckState.AVAILABLE
    )

    for name in (
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    ):
        assert (
            checks[name].state
            is EnvironmentCheckState.UNAVAILABLE
        )
        assert checks[name].required is False
        assert (
            checks[name].reason
            == "module_not_found"
        )


def test_run_doctor_uses_read_only_version_commands(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
    )

    observed = {}

    def fake_probe(**kwargs):
        observed[kwargs["name"]] = (
            kwargs["command"]
        )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="1.0",
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    assert observed["pytest"] == (
        sys.executable,
        "-m",
        "pytest",
        "--version",
    )
    assert observed["pytest-cov"] == (
        sys.executable,
        "-c",
        (
            "from importlib.metadata import version; "
            "print(version('pytest-cov'))"
        ),
    )
    assert observed["coverage"] == (
        sys.executable,
        "-m",
        "coverage",
        "--version",
    )
    assert observed["ruff"] == (
        sys.executable,
        "-m",
        "ruff",
        "--version",
    )
    assert observed["mypy"] == (
        sys.executable,
        "-m",
        "mypy",
        "--version",
    )


def test_run_doctor_skips_worktree_when_git_is_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
    )

    observed = []

    def fake_probe(**kwargs):
        observed.append(kwargs["name"])

        if kwargs["name"] == "git":
            return EnvironmentCheck(
                name="git",
                state=(
                    EnvironmentCheckState.UNAVAILABLE
                ),
                version=None,
                executable="git",
                required=False,
                reason="command_not_found",
                capabilities=kwargs["capabilities"],
            )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="1.0",
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    checks = {
        check.name: check
        for check in result.checks
    }

    assert result.status is DoctorStatus.HEALTHY
    assert (
        checks["git"].state
        is EnvironmentCheckState.UNAVAILABLE
    )
    assert (
        checks["git-worktree"].state
        is EnvironmentCheckState.NOT_APPLICABLE
    )
    assert (
        checks["git-worktree"].reason
        == "git_unavailable"
    )

    assert observed.count("git") == 1
    assert "git-worktree" not in observed


def test_run_doctor_reports_non_git_project_as_optional(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
    )

    observed = {}

    def fake_probe(**kwargs):
        observed[kwargs["name"]] = kwargs

        if kwargs["name"] == "git":
            return EnvironmentCheck(
                name="git",
                state=(
                    EnvironmentCheckState.AVAILABLE
                ),
                version="git version 2.50.0",
                executable="git",
                required=False,
                capabilities=kwargs["capabilities"],
            )

        if kwargs["name"] == "git-worktree":
            return EnvironmentCheck(
                name="git-worktree",
                state=(
                    EnvironmentCheckState.FAILED
                ),
                version=None,
                executable="git",
                required=False,
                reason="command_failed",
                capabilities=kwargs["capabilities"],
            )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="1.0",
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    checks = {
        check.name: check
        for check in result.checks
    }

    assert result.status is DoctorStatus.HEALTHY
    assert (
        checks["git"].state
        is EnvironmentCheckState.AVAILABLE
    )
    assert (
        checks["git-worktree"].state
        is EnvironmentCheckState.NOT_APPLICABLE
    )
    assert (
        checks["git-worktree"].reason
        == "not_git_worktree"
    )

    assert observed["git"]["command"] == (
        "git",
        "--version",
    )
    assert (
        observed["git-worktree"]["command"]
        == (
            "git",
            "-C",
            str(tmp_path.resolve()),
            "rev-parse",
            "--is-inside-work-tree",
        )
    )


def test_run_doctor_reports_git_worktree(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
    )

    def fake_probe(**kwargs):
        if kwargs["name"] == "git":
            version = "git version 2.50.0"
        elif kwargs["name"] == "git-worktree":
            version = "true"
        else:
            version = "1.0"

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version=version,
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    checks = {
        check.name: check
        for check in result.checks
    }

    worktree_check = checks["git-worktree"]
    assert (
        worktree_check.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert worktree_check.version is None
    assert worktree_check.reason is None


def test_run_doctor_rejects_missing_project_root(
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
        run_doctor(
            project_root=missing,
        )


def test_run_doctor_rejects_file_project_root(
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
        run_doctor(
            project_root=project_file,
        )


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
def test_run_doctor_rejects_invalid_timeout_before_probe(
    tmp_path,
    timeout,
):
    probe_called = False

    def fake_probe(**kwargs):
        nonlocal probe_called
        probe_called = True
        raise AssertionError(
            "非法 timeout 不应执行探测"
        )

    with pytest.raises(
        ValueError,
        match="timeout 必须是大于 0 的数字",
    ):
        run_doctor(
            project_root=tmp_path,
            timeout=timeout,
            probe=fake_probe,
        )

    assert probe_called is False


def test_run_doctor_does_not_modify_project(
    tmp_path,
    monkeypatch,
):
    source_path = (
        tmp_path
        / "app.py"
    )
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

    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: EnvironmentCheck(
            name="python",
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="3.13.5",
            executable="/venv/bin/python",
            required=True,
            capabilities=(
                "cli",
            ),
        ),
    )

    def fake_probe(**kwargs):
        version = (
            "true"
            if kwargs["name"] == "git-worktree"
            else f"{kwargs['name']} 1.0"
        )

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version=version,
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
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

    run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

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


def test_git_worktree_rejects_unexpected_success_output(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        doctor_module,
        "_python_check",
        lambda: _check(
            EnvironmentCheckState.AVAILABLE,
            required=True,
        ),
    )

    def fake_probe(**kwargs):
        if kwargs["name"] == "git":
            version = "git version 2.50.0"
        elif kwargs["name"] == "git-worktree":
            version = "unexpected output"
        else:
            version = "1.0"

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version=version,
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    result = run_doctor(
        project_root=tmp_path,
        probe=fake_probe,
    )

    checks = {
        check.name: check
        for check in result.checks
    }

    assert result.status is DoctorStatus.HEALTHY
    assert (
        checks["git-worktree"].state
        is EnvironmentCheckState.FAILED
    )
    assert (
        checks["git-worktree"].reason
        == "invalid_git_worktree_output"
    )


def test_git_checks_reject_unexpected_worktree_output(
    tmp_path,
):
    def fake_probe(**kwargs):
        if kwargs["name"] == "git":
            version = "git version 2.50.0"
        else:
            version = "unexpected output"

        return EnvironmentCheck(
            name=kwargs["name"],
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version=version,
            executable=kwargs["command"][0],
            required=kwargs["required"],
            capabilities=kwargs["capabilities"],
        )

    git_check, worktree_check = (
        doctor_module._git_checks(
            root=tmp_path.resolve(),
            timeout=10,
            probe=fake_probe,
        )
    )

    assert (
        git_check.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert (
        worktree_check.state
        is EnvironmentCheckState.FAILED
    )
    assert (
        worktree_check.reason
        == "invalid_git_worktree_output"
    )

def test_run_doctor_is_publicly_exported():
    from core.workflows import (
        run_doctor as exported_run_doctor,
    )

    assert exported_run_doctor is run_doctor