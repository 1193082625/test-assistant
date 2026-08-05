"""Doctor 的特殊路径与只读边界测试。"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(root: Path) -> tuple[frozenset[str], dict[str, bytes]]:
    return (
        frozenset(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
        ),
        {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        },
    )


def _run_doctor(project: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(PROJECT_ROOT), existing_pythonpath)
        if value
    )
    working_directory = (
        project
        if project.is_dir()
        else project.parent
    )

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "doctor",
            "--path",
            str(project),
            "--json",
        ],
        cwd=working_directory,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=environment,
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("project with spaces"),
        Path("中文项目"),
        Path(*(["long-segment-0123456789"] * 12)),
    ],
    ids=("spaces", "unicode", "long-path"),
)
def test_doctor_accepts_special_paths_without_writes(
    tmp_path,
    relative_path,
):
    project = tmp_path / relative_path
    project.mkdir(parents=True)
    (project / "app.py").write_text("value = 1\n", encoding="utf-8")
    before = _snapshot(project)

    completed = _run_doctor(project)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "healthy"
    assert payload["project_path"] == str(project.resolve())
    assert _snapshot(project) == before
    assert not (project / ".autotest").exists()


def test_doctor_accepts_project_directory_symlink_without_writes(tmp_path):
    project = tmp_path / "real-project"
    project.mkdir()
    (project / "app.py").write_text("value = 1\n", encoding="utf-8")
    project_link = tmp_path / "project-link"
    project_link.symlink_to(project, target_is_directory=True)
    before = _snapshot(project)

    completed = _run_doctor(project_link)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["project_path"] == str(project.resolve())
    assert _snapshot(project) == before
    assert project_link.is_symlink()


def test_doctor_rejects_broken_project_symlink(tmp_path):
    project_link = tmp_path / "broken-project"
    project_link.symlink_to(
        tmp_path / "missing-project",
        target_is_directory=True,
    )

    completed = _run_doctor(project_link)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "does not exist" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert project_link.is_symlink()


def test_doctor_accepts_read_only_project_without_writes(tmp_path):
    project = tmp_path / "read-only-project"
    project.mkdir()
    source = project / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    before = _snapshot(project)

    source.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    project.chmod(
        stat.S_IRUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )
    try:
        completed = _run_doctor(project)

        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout)["status"] == "healthy"
        assert _snapshot(project) == before
        assert not (project / ".autotest").exists()
    finally:
        project.chmod(stat.S_IRWXU)
        source.chmod(stat.S_IRUSR | stat.S_IWUSR)


@pytest.mark.skipif(os.name == "nt", reason="POSIX rejection contract")
def test_doctor_rejects_windows_absolute_path_on_posix(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "doctor",
            "--path",
            r"C:\Users\example\project",
            "--json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                value
                for value in (
                    str(PROJECT_ROOT),
                    os.environ.get("PYTHONPATH"),
                )
                if value
            ),
        },
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "does not exist" in completed.stderr
    assert "Traceback" not in completed.stderr
