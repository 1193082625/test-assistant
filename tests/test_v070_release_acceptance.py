"""v0.7.0 规模化与数据生命周期发布验收。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def distributions(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    output = tmp_path_factory.mktemp("v070-distributions")
    completed = subprocess.run(
        ["poetry", "build", "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    wheel = output / "test_assistant-0.7.0-py3-none-any.whl"
    sdist = output / "test_assistant-0.7.0.tar.gz"
    assert wheel.is_file()
    assert sdist.is_file()
    return wheel, sdist


def _tree_bytes(root: Path) -> tuple[frozenset[str], dict[str, bytes]]:
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


def _run_cli(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(ROOT), environment.get("PYTHONPATH"))
        if value
    )
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *arguments],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_release_metadata_and_cli_surface_are_v070() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]

    assert project["version"] == "0.7.0"
    assert project["requires-python"] == ">=3.13,<3.14"
    completed = _run_cli(ROOT, "--version")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "test-assistant, version 0.7.0\n"

    help_result = _run_cli(ROOT, "--help")
    assert help_result.returncode == 0, help_result.stderr
    assert "clean" in help_result.stdout
    assert "migrate" in help_result.stdout


def test_distribution_metadata_contents_and_digests(
    distributions: tuple[Path, Path],
) -> None:
    wheel, sdist = distributions
    digests = {
        archive.name: hashlib.sha256(archive.read_bytes()).hexdigest()
        for archive in distributions
    }
    assert all(len(value) == 64 for value in digests.values())

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name = next(name for name in names if name.endswith("/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        assert metadata["Version"] == "0.7.0"
        assert metadata["Requires-Python"] == ">=3.13,<3.14"
        assert set(metadata.get_all("Provides-Extra")) == {"all", "llm", "quality"}
        _assert_safe_archive(names, archive.read)

    with tarfile.open(sdist, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        names = [member.name for member in members]

        def read_member(name: str) -> bytes:
            extracted = archive.extractfile(name)
            assert extracted is not None
            return extracted.read()

        _assert_safe_archive(names, read_member)


def _assert_safe_archive(names: list[str], read_file) -> None:
    normalized = [f"/{name}" for name in names]
    assert not any("/tests/" in name for name in normalized)
    assert not any("/.autotest/" in name for name in normalized)
    assert not any(name.endswith("/.env") for name in normalized)
    forbidden_bytes = (
        str(ROOT).encode(),
        b"/Users/wangyue/Desktop/work/fit-style",
    )
    for name in names:
        contents = read_file(name)
        assert all(value not in contents for value in forbidden_bytes), name


def test_doctor_migrate_and_clean_dry_runs_preserve_project(tmp_path: Path) -> None:
    project = tmp_path / "只读 fixture"
    project.mkdir()
    (project / "app.py").write_text("value = 1\n", encoding="utf-8")
    history = project / ".autotest" / "audits" / "existing.json"
    history.parent.mkdir(parents=True)
    history.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "record_type": "audit",
                "run_id": "existing",
                "created_at": "2000-01-01T00:00:00+00:00",
                "status": "passed",
                "command": ["test-assistant", "audit"],
                "coverage": None,
                "symbols": [],
                "findings": [],
                "tools": [],
                "source_digest": "sha256:fixture",
                "thresholds": {
                    "statement_rate": None,
                    "branch_rate": None,
                    "max_ruff_findings": None,
                    "max_mypy_errors": None,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    before = _tree_bytes(project)

    doctor = _run_cli(project, "doctor", "--path", str(project), "--json")
    migration = _run_cli(
        project, "migrate", "--path", str(project), "--dry-run"
    )
    cleanup = _run_cli(
        project, "clean", "--path", str(project), "--dry-run", "--json"
    )

    assert doctor.returncode == 0, doctor.stderr
    assert json.loads(doctor.stdout)["test_assistant_version"] == "0.7.0"
    assert migration.returncode == 0, migration.stderr
    assert cleanup.returncode == 0, cleanup.stderr
    assert json.loads(cleanup.stdout)["schema_version"] == 1
    assert _tree_bytes(project) == before


def test_ci_contains_base_llm_quality_platform_matrix() -> None:
    workflow = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
    smoke = workflow["jobs"]["wheel-smoke"]
    matrix = smoke["strategy"]["matrix"]

    assert matrix["os"] == ["ubuntu-latest", "macos-latest"]
    assert matrix["installation"] == ["base", "llm", "quality"]
    script = next(
        step["run"]
        for step in smoke["steps"]
        if step.get("name") == "Smoke test installed wheel"
    )
    assert "pip\" install --no-deps" in script
    assert "llm_extra_required" in script
    assert '"pytest-cov", "coverage", "ruff", "mypy"' in script
