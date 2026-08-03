import subprocess

import pytest

from core.analyzers.git_history import read_contract_history


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def commit(root, path, content, message):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(root, "add", path)
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-q",
        "-m",
        message,
    )


def test_confirms_both_sides_in_same_commit(tmp_path):
    git(tmp_path, "init", "-q")
    commit(tmp_path, "app/config.py", "VALUE = 10\n", "old")
    commit(tmp_path, "app/config.py", "VALUE = 120\n", "migrate")

    history = read_contract_history(
        project_root=tmp_path,
        old_expression="VALUE = 10",
        new_expression="VALUE = 120",
        source_paths=("app/config.py",),
    )

    assert history.migration_confirmed
    assert len(history.migration_commit) == 40
    assert history.old_expression_summary == "VALUE = 10"


def test_one_sided_change_is_not_a_migration(tmp_path):
    git(tmp_path, "init", "-q")
    commit(tmp_path, "app/config.py", "VALUE = 10\n", "old")
    commit(
        tmp_path,
        "app/config.py",
        "VALUE = 10\nOTHER = 120\n",
        "unrelated",
    )
    history = read_contract_history(
        project_root=tmp_path,
        old_expression="VALUE = 10",
        new_expression="OTHER = 120",
        source_paths=("app/config.py",),
    )
    assert not history.migration_confirmed
    assert history.degradation_reason == "migration_not_confirmed"


def test_non_repository_safely_degrades(tmp_path):
    history = read_contract_history(
        project_root=tmp_path,
        old_expression="VALUE = 10",
        new_expression="VALUE = 20",
        source_paths=("app/config.py",),
    )
    assert not history.available
    assert history.degradation_reason == "git_log_failed"


@pytest.mark.parametrize(
    "path", ["../outside.py", "/absolute.py", "C:\\outside.py"]
)
def test_rejects_unsafe_paths(tmp_path, path):
    with pytest.raises(ValueError, match="项目内相对路径"):
        read_contract_history(
            project_root=tmp_path,
            old_expression="old",
            new_expression="new",
            source_paths=(path,),
        )


def test_rejects_unsafe_expression(tmp_path):
    with pytest.raises(ValueError, match="表达式不安全"):
        read_contract_history(
            project_root=tmp_path,
            old_expression="old\nvalue",
            new_expression="new",
            source_paths=("app/config.py",),
        )
