"""Deterministic repository fixtures used by performance tests."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


GIT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class FixtureProfile:
    """Fixed inputs that control the size and contents of a fixture."""

    seed: int
    module_count: int
    functions_per_module: int
    test_count: int
    git_commit_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "seed",
            "module_count",
            "functions_per_module",
            "test_count",
            "git_commit_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")

        for field_name in (
            "module_count",
            "functions_per_module",
            "test_count",
            "git_commit_count",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True)
class GeneratedFixture:
    """Paths and stable identifiers returned by fixture generation."""

    root: Path
    source_files: tuple[Path, ...]
    test_files: tuple[Path, ...]
    commit_ids: tuple[str, ...]
    logical_digest: str


CI_PROFILE = FixtureProfile(
    seed=700,
    module_count=100,
    functions_per_module=10,
    test_count=200,
    git_commit_count=5,
)

LARGE_PROFILE = FixtureProfile(
    seed=700,
    module_count=1_000,
    functions_per_module=10,
    test_count=2_000,
    git_commit_count=25,
)


def generate_fixture(root: Path, profile: FixtureProfile) -> GeneratedFixture:
    """Generate a reproducible Python repository at an empty path."""

    root = Path(root)
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise ValueError("fixture root must be an empty directory")
    else:
        root.mkdir(parents=True)

    random_source = random.Random(profile.seed)
    package_root = root / "src" / "large_fixture"
    tests_root = root / "tests"
    history_root = root / ".fixture-history"
    package_root.mkdir(parents=True)
    tests_root.mkdir()
    history_root.mkdir()

    (package_root / "__init__.py").write_text(
        '"""Generated deterministic fixture package."""\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'pythonpath = ["src"]\n'
        'testpaths = ["tests"]\n',
        encoding="utf-8",
    )
    (root / ".fixture-profile.json").write_text(
        json.dumps(
            {
                "functions_per_module": profile.functions_per_module,
                "git_commit_count": profile.git_commit_count,
                "module_count": profile.module_count,
                "seed": profile.seed,
                "test_count": profile.test_count,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    offsets: list[list[int]] = []
    source_files: list[Path] = []
    for module_index in range(profile.module_count):
        module_offsets = [
            random_source.randint(-10_000, 10_000)
            for _ in range(profile.functions_per_module)
        ]
        offsets.append(module_offsets)
        source_path = package_root / f"module_{module_index:04d}.py"
        source_path.write_text(
            _render_module(module_index, module_offsets),
            encoding="utf-8",
        )
        source_files.append(source_path)

    test_files: list[Path] = []
    for test_index in range(profile.test_count):
        module_index = random_source.randrange(profile.module_count)
        function_index = random_source.randrange(profile.functions_per_module)
        input_value = random_source.randint(-10_000, 10_000)
        test_path = tests_root / f"test_module_{test_index:04d}.py"
        test_path.write_text(
            _render_test(
                test_index=test_index,
                module_index=module_index,
                function_index=function_index,
                input_value=input_value,
                expected=input_value + offsets[module_index][function_index],
            ),
            encoding="utf-8",
        )
        test_files.append(test_path)

    _run_git(root, ["init", "--quiet"])
    commit_ids: list[str] = []
    initial_date = datetime(2000, 1, 1, tzinfo=timezone.utc)
    for commit_index in range(profile.git_commit_count):
        marker = history_root / f"commit_{commit_index:04d}.txt"
        marker.write_text(
            f"deterministic fixture commit {commit_index:04d}\n",
            encoding="utf-8",
        )
        _run_git(root, ["add", "."])
        commit_date = initial_date + timedelta(seconds=commit_index)
        _run_git(
            root,
            [
                "-c",
                "user.name=Test Assistant Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgSign=false",
                "commit",
                "--quiet",
                "--message",
                f"fixture commit {commit_index:04d}",
            ],
            commit_date=commit_date,
        )
        commit_ids.append(_run_git(root, ["rev-parse", "HEAD"]).strip())

    return GeneratedFixture(
        root=root,
        source_files=tuple(source_files),
        test_files=tuple(test_files),
        commit_ids=tuple(commit_ids),
        logical_digest=_logical_digest(root),
    )


def _render_module(module_index: int, offsets: Sequence[int]) -> str:
    lines = [f'"""Generated module {module_index:04d}."""', ""]
    for function_index, offset in enumerate(offsets):
        lines.extend(
            [
                f"def function_{function_index:03d}(value: int) -> int:",
                f"    return value + ({offset})",
                "",
            ]
        )
    return "\n".join(lines)


def _render_test(
    *,
    test_index: int,
    module_index: int,
    function_index: int,
    input_value: int,
    expected: int,
) -> str:
    return (
        f"from large_fixture.module_{module_index:04d} "
        f"import function_{function_index:03d}\n\n\n"
        f"def test_generated_case_{test_index:04d}() -> None:\n"
        f"    assert function_{function_index:03d}({input_value}) == {expected}\n"
    )


def _run_git(
    root: Path,
    arguments: Sequence[str],
    *,
    commit_date: datetime | None = None,
) -> str:
    environment = os.environ.copy()
    if commit_date is not None:
        formatted_date = commit_date.isoformat()
        environment["GIT_AUTHOR_DATE"] = formatted_date
        environment["GIT_COMMITTER_DATE"] = formatted_date

    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"git command failed: {error}") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git command failed: {detail}")
    return result.stdout


def _logical_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )
    for path in files:
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        contents = path.read_bytes()
        digest.update(len(relative_path).to_bytes(8, "big"))
        digest.update(relative_path)
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
    return digest.hexdigest()
