"""Contracts for the deterministic performance fixture factory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.performance.fixture_factory import (
    FixtureProfile,
    generate_fixture,
)


SMALL_PROFILE = FixtureProfile(
    seed=17,
    module_count=4,
    functions_per_module=3,
    test_count=5,
    git_commit_count=3,
)


def _relative_paths(paths: tuple[Path, ...], root: Path) -> tuple[Path, ...]:
    return tuple(path.relative_to(root) for path in paths)


def _generated_contents(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }


@pytest.mark.performance
def test_same_profile_generates_identical_repository(tmp_path: Path) -> None:
    first = generate_fixture(tmp_path / "first", SMALL_PROFILE)
    second = generate_fixture(tmp_path / "second", SMALL_PROFILE)

    assert _relative_paths(first.source_files, first.root) == _relative_paths(
        second.source_files,
        second.root,
    )
    assert _relative_paths(first.test_files, first.root) == _relative_paths(
        second.test_files,
        second.root,
    )
    assert _generated_contents(first.root) == _generated_contents(second.root)
    assert first.logical_digest == second.logical_digest
    assert first.commit_ids == second.commit_ids
    assert len(first.commit_ids) == SMALL_PROFILE.git_commit_count


@pytest.mark.performance
def test_different_seed_changes_logical_digest(tmp_path: Path) -> None:
    first = generate_fixture(tmp_path / "first", SMALL_PROFILE)
    second = generate_fixture(
        tmp_path / "second",
        FixtureProfile(
            seed=18,
            module_count=SMALL_PROFILE.module_count,
            functions_per_module=SMALL_PROFILE.functions_per_module,
            test_count=SMALL_PROFILE.test_count,
            git_commit_count=SMALL_PROFILE.git_commit_count,
        ),
    )

    assert first.logical_digest != second.logical_digest


@pytest.mark.performance
def test_fixture_has_exact_counts_and_runnable_tests(tmp_path: Path) -> None:
    generated = generate_fixture(tmp_path / "fixture", SMALL_PROFILE)

    assert len(generated.source_files) == SMALL_PROFILE.module_count
    assert len(generated.test_files) == SMALL_PROFILE.test_count
    assert len(generated.commit_ids) == SMALL_PROFILE.git_commit_count

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=generated.root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        shell=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "5 passed" in result.stdout


@pytest.mark.performance
def test_fixture_contains_no_host_or_current_time_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/private/real-user-home")
    generated = generate_fixture(tmp_path / "fixture", SMALL_PROFILE)
    contents = b"\n".join(_generated_contents(generated.root).values())

    assert str(generated.root).encode() not in contents
    assert b"/private/real-user-home" not in contents
    assert b"2026" not in contents
    assert b"http://" not in contents
    assert b"https://" not in contents

    dates = subprocess.run(
        ["git", "log", "--format=%aI"],
        cwd=generated.root,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
        shell=False,
    ).stdout.splitlines()
    assert all(date.startswith("2000-01-01T") for date in dates)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", True),
        ("module_count", 0),
        ("functions_per_module", -1),
        ("test_count", False),
        ("git_commit_count", 0),
    ],
)
def test_fixture_profile_rejects_invalid_values(field: str, value: object) -> None:
    values: dict[str, object] = {
        "seed": 1,
        "module_count": 1,
        "functions_per_module": 1,
        "test_count": 1,
        "git_commit_count": 1,
    }
    values[field] = value

    with pytest.raises(ValueError):
        FixtureProfile(**values)  # type: ignore[arg-type]


def test_generate_fixture_rejects_nonempty_root(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    existing = root / "keep.txt"
    existing.write_text("keep me", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        generate_fixture(root, SMALL_PROFILE)

    assert existing.read_text(encoding="utf-8") == "keep me"
