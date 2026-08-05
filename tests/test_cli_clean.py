"""CLI contracts for explicit, safe history cleanup."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

import cli.commands.clean as clean_command_module
from cli.main import cli
from core.models import AuditResult, AuditStatus
from core.repositories import AuditRepository


OLD_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _old_audit(root: Path, run_id: str = "old") -> Path:
    return AuditRepository(root).save(
        AuditResult(
            run_id=run_id,
            status=AuditStatus.PASSED,
            command=("test-assistant", "audit"),
            coverage=None,
            symbols=(),
            findings=(),
            tools=(),
            source_digest="sha256:fixture",
        ),
        created_at=OLD_TIME,
    )


def _tree_bytes(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file() else None
        )
        for path in sorted(root.rglob("*"))
    }


def test_clean_defaults_to_read_only_preview(tmp_path: Path) -> None:
    candidate = _old_audit(tmp_path)
    before = _tree_bytes(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "clean",
            "--path",
            str(tmp_path),
            "--keep-latest",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "候选总数: 1" in result.output
    assert "可回收字节" in result.output
    assert "audits/old.json" in result.output
    assert "expired" in result.output
    assert "未修改任何文件" in result.output
    assert candidate.exists()
    assert _tree_bytes(tmp_path) == before


def test_clean_json_is_pure_and_only_allowed_for_dry_run(tmp_path: Path) -> None:
    _old_audit(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "clean",
            "--path",
            str(tmp_path),
            "--keep-latest",
            "0",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["candidates"][0]["type"] == "audit"

    rejected = runner.invoke(
        cli,
        ["clean", "--path", str(tmp_path), "--apply", "--json"],
    )
    assert rejected.exit_code == 2


def test_clean_apply_shows_summary_before_confirmation_and_cancel_is_safe(
    tmp_path: Path,
) -> None:
    candidate = _old_audit(tmp_path)
    before = candidate.read_bytes()

    result = CliRunner().invoke(
        cli,
        [
            "clean",
            "--path",
            str(tmp_path),
            "--keep-latest",
            "0",
            "--apply",
        ],
        input="n\n",
    )

    assert result.exit_code == 0, result.output
    assert result.output.index("候选总数") < result.output.index("确认清理")
    assert "已取消" in result.output
    assert candidate.read_bytes() == before


def test_clean_apply_deletes_only_planned_candidate(tmp_path: Path) -> None:
    candidate = _old_audit(tmp_path)
    latest = tmp_path / ".autotest/audits/latest.json"
    latest_bytes = latest.read_bytes()

    result = CliRunner().invoke(
        cli,
        [
            "clean",
            "--path",
            str(tmp_path),
            "--keep-latest",
            "0",
            "--apply",
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "已删除 1" in result.output
    assert not candidate.exists()
    assert latest.read_bytes() == latest_bytes


def test_clean_apply_rejects_change_after_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _old_audit(tmp_path)
    real_execute = clean_command_module.execute_cleanup

    def change_then_execute(**kwargs):
        candidate.write_text("new content", encoding="utf-8")
        return real_execute(**kwargs)

    monkeypatch.setattr(
        clean_command_module,
        "execute_cleanup",
        change_then_execute,
    )

    result = CliRunner().invoke(
        cli,
        [
            "clean",
            "--path",
            str(tmp_path),
            "--keep-latest",
            "0",
            "--apply",
        ],
        input="y\n",
    )

    assert result.exit_code == 2, result.output
    assert "changed after planning" in result.output
    assert candidate.read_text(encoding="utf-8") == "new content"


def test_clean_parameter_and_scan_errors_exit_two(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid_parameter = runner.invoke(
        cli,
        ["clean", "--path", str(tmp_path), "--older-than-days", "-1"],
    )
    assert invalid_parameter.exit_code == 2

    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / ".autotest").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    scan_error = runner.invoke(cli, ["clean", "--path", str(tmp_path)])
    assert scan_error.exit_code == 2


def test_clean_never_prints_record_contents(tmp_path: Path) -> None:
    invalid = tmp_path / ".autotest/audits/invalid.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("token=super-secret-value", encoding="utf-8")

    result = CliRunner().invoke(cli, ["clean", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "super-secret-value" not in result.output
    assert "invalid_record" in result.output


def test_clean_converts_max_total_mib_to_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = {}
    real_plan = clean_command_module.plan_cleanup

    def observe_plan(**kwargs):
        observed.update(kwargs)
        return real_plan(**kwargs)

    monkeypatch.setattr(clean_command_module, "plan_cleanup", observe_plan)

    result = CliRunner().invoke(
        cli,
        ["clean", "--path", str(tmp_path), "--max-total-mib", "1.5"],
    )

    assert result.exit_code == 0, result.output
    assert observed["max_total_bytes"] == 1_572_864
