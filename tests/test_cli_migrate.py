"""CLI contracts for explicit schema migration."""

import json
from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli
from core.models import AuditResult, AuditStatus
from core.repositories import AuditRepository


def _v1_audit(root: Path) -> Path:
    repository = AuditRepository(root)
    path = repository.save(
        AuditResult(
            run_id="run-001",
            status=AuditStatus.PASSED,
            command=("test-assistant", "audit"),
            coverage=None,
            symbols=(),
            findings=(),
            tools=(),
            source_digest="sha256:fixture",
        ),
        created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    payload.pop("record_type")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_migrate_defaults_to_read_only_preview(tmp_path: Path) -> None:
    path = _v1_audit(tmp_path)
    before = path.read_bytes()

    result = CliRunner().invoke(cli, ["migrate", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "migrate" in result.output
    assert "audit" in result.output
    assert "1 → 2" in result.output
    assert path.read_bytes() == before


def test_migrate_json_is_pure_and_dry_run_only(tmp_path: Path) -> None:
    _v1_audit(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["migrate", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["items"][0]["action"] in {"migrate", "skip"}

    rejected = runner.invoke(
        cli,
        ["migrate", "--path", str(tmp_path), "--apply", "--json"],
    )
    assert rejected.exit_code == 2


def test_migrate_apply_cancel_is_successful_and_read_only(tmp_path: Path) -> None:
    path = _v1_audit(tmp_path)
    before = path.read_bytes()

    result = CliRunner().invoke(
        cli,
        ["migrate", "--path", str(tmp_path), "--apply"],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert "已取消" in result.output
    assert path.read_bytes() == before


def test_migrate_apply_after_confirmation(tmp_path: Path) -> None:
    path = _v1_audit(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["migrate", "--path", str(tmp_path), "--apply"],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["record_type"] == "audit"


def test_migrate_rejects_conflicting_modes(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "migrate",
            "--path",
            str(tmp_path),
            "--dry-run",
            "--apply",
        ],
    )

    assert result.exit_code == 2
