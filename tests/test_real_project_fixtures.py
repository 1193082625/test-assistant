"""验证脱敏的真实项目 fixture 保持预期行为。"""

import subprocess
import sys
from pathlib import Path

import pytest


FIXTURES_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "real_project_triage"
)


@pytest.mark.parametrize(
    (
        "fixture_name",
        "expected_exception",
        "expected_message",
        "expected_failure_count",
    ),
    [
        (
            "stale_removed_method",
            "AssertionError",
            "Service.removed_async no longer exists",
            1,
        ),
        (
            "migrated_dependency_mock",
            "AttributeError",
            "has no attribute 'legacy'",
            1,
        ),
        (
            "conflicting_contract",
            "AssertionError",
            "Expected 10-second undo window, got 120",
            1,
        ),
        (
            "missing_boolean_return",
            "AssertionError",
            "assert None is False",
            4,
        ),
    ],
)
def test_real_project_failure_fixture(
    fixture_name: str,
    expected_exception: str,
    expected_message: str,
    expected_failure_count: int,
) -> None:
    fixture_root = FIXTURES_ROOT / fixture_name

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "case.py",
            "-q",
        ],
        cwd=fixture_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = completed.stdout + completed.stderr

    assert completed.returncode == 1
    assert expected_exception in output
    assert expected_message in output
    assert f"{expected_failure_count} failed" in output


def test_instance_method_mapping_fixture_passes() -> None:
    fixture_root = FIXTURES_ROOT / "instance_method_mapping"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "case.py",
            "-q",
        ],
        cwd=fixture_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = completed.stdout + completed.stderr

    assert completed.returncode == 0
    assert "1 passed" in output
