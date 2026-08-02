import subprocess

import pytest

from core.analyzers.git_history import read_symbol_history


def _git(root, *args):
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def test_reads_added_then_deleted_symbol_from_local_history(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    _git(tmp_path, "config", "user.name", "Fixture")
    source = tmp_path / "service.py"
    source.write_text("class Service:\n    removed_async = None\n")
    _git(tmp_path, "add", "service.py")
    _git(tmp_path, "commit", "-qm", "add symbol")
    source.write_text("class Service:\n    current = None\n")
    _git(tmp_path, "add", "service.py")
    _git(tmp_path, "commit", "-qm", "remove symbol")

    evidence = read_symbol_history(
        project_root=tmp_path,
        symbol="removed_async",
        source_paths=("service.py",),
    )

    assert evidence.available is True
    assert evidence.was_added is True
    assert evidence.was_deleted is True
    assert evidence.removal_confirmed is True
    assert evidence.deletion_commit in evidence.commits
    assert "fixture@example.invalid" not in repr(evidence)


def test_missing_or_unavailable_history_does_not_confirm_removal(tmp_path):
    evidence = read_symbol_history(
        project_root=tmp_path,
        symbol="missing",
        source_paths=("service.py",),
    )

    assert evidence.available is False
    assert evidence.removal_confirmed is False
    assert evidence.degradation_reason == "git_log_failed"


@pytest.mark.parametrize("path", ["../secret.py", "/tmp/secret.py", "C:\\secret.py"])
def test_rejects_paths_outside_project(path, tmp_path):
    with pytest.raises(ValueError, match="项目内相对路径"):
        read_symbol_history(
            project_root=tmp_path,
            symbol="target",
            source_paths=(path,),
        )


def test_timeout_is_a_safe_degradation(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(
        "core.analyzers.git_history.subprocess.run", timeout
    )

    evidence = read_symbol_history(
        project_root=tmp_path,
        symbol="target",
        source_paths=("service.py",),
    )

    assert evidence.available is False
    assert evidence.degradation_reason == "TimeoutExpired"
