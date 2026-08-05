"""v0.6.1 Doctor 的真实 CLI 发布验收。"""

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(root: Path) -> tuple[
    frozenset[str],
    dict[str, bytes],
]:
    """记录项目路径及文件内容，供只读断言使用。"""

    paths = frozenset(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
    )
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    return paths, files


def _run_doctor(
    project: Path,
    *arguments: str,
    bootstrap: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """在独立进程中调用真实 Click CLI 入口。"""

    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (
            str(PROJECT_ROOT),
            existing_pythonpath,
        )
        if part
    )

    if bootstrap is None:
        command = [
            sys.executable,
            "-m",
            "cli.main",
        ]
    else:
        command = [
            sys.executable,
            "-c",
            bootstrap,
        ]

    return subprocess.run(
        [
            *command,
            "doctor",
            "--path",
            str(project),
            *arguments,
        ],
        cwd=(
            project
            if project.is_dir()
            else project.parent
        ),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )


def test_doctor_json_is_pure_and_project_is_unchanged(tmp_path):
    project = tmp_path / "只读 project"
    project.mkdir()
    (project / "app.py").write_text(
        "TOKEN = 'keep-me'\n",
        encoding="utf-8",
    )
    history = project / ".autotest" / "diagnoses" / "existing.json"
    history.parent.mkdir(parents=True)
    history.write_text('{"existing": true}\n', encoding="utf-8")
    before = _snapshot(project)

    completed = _run_doctor(project, "--json")

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == 1
    assert payload["status"] == "healthy"
    assert payload["project_path"] == str(project.resolve())
    assert {check["name"] for check in payload["checks"]} == {
        "python",
        "pytest",
        "git",
        "git-worktree",
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    }
    assert "Doctor 状态:" not in completed.stdout
    assert completed.stderr == ""
    assert _snapshot(project) == before


def test_doctor_non_git_project_is_healthy(tmp_path):
    project = tmp_path / "plain-project"
    project.mkdir()

    completed = _run_doctor(project)

    assert completed.returncode == 0, completed.stderr
    assert "Doctor 状态: healthy" in completed.stdout
    assert "git-worktree: not_applicable" in completed.stdout
    assert "原因=not_git_worktree" in completed.stdout


def test_missing_optional_adapters_are_degraded_not_fatal(tmp_path):
    project = tmp_path / "missing-adapters"
    project.mkdir()
    bootstrap = (
        "import sys; "
        "import core.workflows.doctor as doctor; "
        "doctor._optional_probe_specs = lambda: ("
        "('pytest-cov', (sys.executable, '-m', 'missing_pytest_cov'), "
        "('audit_coverage',)), "
        "('coverage', (sys.executable, '-m', 'missing_coverage'), "
        "('audit_coverage',)), "
        "('ruff', (sys.executable, '-m', 'missing_ruff'), "
        "('audit_quality',)), "
        "('mypy', (sys.executable, '-m', 'missing_mypy'), "
        "('audit_quality',))); "
        "from cli.main import cli; cli()"
    )

    completed = _run_doctor(
        project,
        "--json",
        bootstrap=bootstrap,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "healthy"
    optional = {
        check["name"]: check
        for check in payload["checks"]
        if check["name"] in {
            "pytest-cov",
            "coverage",
            "ruff",
            "mypy",
        }
    }
    assert all(
        check["state"] == "unavailable"
        for check in optional.values()
    )
    assert all(
        check["reason"] == "module_not_found"
        for check in optional.values()
    )


def test_incompatible_core_environment_exits_one(tmp_path):
    project = tmp_path / "incompatible-core"
    project.mkdir()
    bootstrap = (
        "import core.workflows.doctor as doctor; "
        "doctor.SUPPORTED_PYTHON = (0, 0); "
        "from cli.main import cli; cli()"
    )

    completed = _run_doctor(
        project,
        "--json",
        bootstrap=bootstrap,
    )

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "incompatible"
    python_check = next(
        check
        for check in payload["checks"]
        if check["name"] == "python"
    )
    assert python_check["state"] == "incompatible"
    assert python_check["reason"] == "unsupported_python_version"


def test_missing_project_path_exits_two_without_traceback(tmp_path):
    missing = tmp_path / "missing"

    completed = _run_doctor(missing, "--json")

    assert completed.returncode == 2
    assert "does not exist" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert completed.stdout == ""
