"""Compatibility manifest and generated table tests."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "generate_compatibility_table.py"
MANIFEST = PROJECT_ROOT / "docs" / "compatibility.json"
OUTPUT = PROJECT_ROOT / "docs" / "compatibility.md"


def _run_generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_checked_in_compatibility_document_is_current():
    completed = _run_generator("--check")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""


def test_compatibility_document_generation_is_deterministic(tmp_path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    first_result = _run_generator("--output", str(first))
    second_result = _run_generator("--output", str(second))

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert first.read_bytes() == second.read_bytes() == OUTPUT.read_bytes()


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (lambda payload: payload.update(schema_version=2), "schema_version"),
        (
            lambda payload: payload["entries"][0].update(state="unknown"),
            "unsupported state",
        ),
        (
            lambda payload: payload["entries"].append(
                dict(payload["entries"][0])
            ),
            "duplicate compatibility entry",
        ),
    ],
)
def test_invalid_compatibility_manifest_is_rejected(
    tmp_path,
    mutation,
    expected_error,
):
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutation(payload)
    invalid_manifest = tmp_path / "invalid.json"
    invalid_manifest.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    completed = _run_generator(
        "--manifest",
        str(invalid_manifest),
        "--output",
        str(tmp_path / "output.md"),
    )

    assert completed.returncode == 1
    assert expected_error in completed.stderr
    assert "Traceback" not in completed.stderr
