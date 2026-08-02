import json
import subprocess
from datetime import datetime, timezone

import pytest

from core.repositories import GitPermissionRepository


def _git(root, *args):
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def _repository(tmp_path):
    _git(tmp_path, "init", "-q")
    return GitPermissionRepository(tmp_path)


def test_permission_is_absent_until_explicit_grant(tmp_path):
    repository = _repository(tmp_path)

    assert repository.is_granted() is False

    repository.grant(
        approved_at=datetime(2026, 8, 3, tzinfo=timezone.utc)
    )

    assert repository.is_granted() is True
    payload = json.loads(repository.path.read_text(encoding="utf-8"))
    assert payload["git_history"]["scope"] == "local_read_only"
    assert str(tmp_path) not in repository.path.read_text(encoding="utf-8")


def test_permission_is_invalid_for_a_different_repository(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_repository = _repository(first)
    second_repository = _repository(second)
    first_repository.grant()
    second_repository.path.parent.mkdir(parents=True)
    second_repository.path.write_bytes(first_repository.path.read_bytes())

    assert second_repository.is_granted() is False


def test_permission_rejects_corrupt_or_unsupported_json(tmp_path):
    repository = _repository(tmp_path)
    repository.path.parent.mkdir(parents=True)
    repository.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON 已损坏"):
        repository.is_granted()

    repository.path.write_text('{"schema_version": 999}', encoding="utf-8")
    with pytest.raises(ValueError, match="不支持的 Git 授权记录格式"):
        repository.is_granted()


def test_grant_requires_git_repository(tmp_path):
    with pytest.raises(ValueError, match="不是可识别的本地 Git 仓库"):
        GitPermissionRepository(tmp_path).grant()


def test_atomic_failure_leaves_no_permission_or_temp_file(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(
        "core.repositories.permissions.os.replace", fail_replace
    )
    with pytest.raises(OSError, match="replace failed"):
        repository.grant()

    assert not repository.path.exists()
    assert list(repository.path.parent.glob("*.tmp")) == []
