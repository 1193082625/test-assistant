import pytest

from core.analyzers.change_evidence import collect_change_evidence


def test_changed_only_requires_snapshot_or_git_permission(tmp_path):
    with pytest.raises(ValueError, match="snapshot 或已授权"):
        collect_change_evidence(tmp_path)


def test_snapshot_evidence_reports_modified_symbol(tmp_path):
    from core.analyzers.snapshot import commit_snapshot_manifest, take_snapshot

    source = tmp_path / "app.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    baseline, _ = take_snapshot(str(tmp_path), [".autotest"])
    autotest = tmp_path / ".autotest"
    autotest.mkdir()
    commit_snapshot_manifest(str(autotest / "snapshot.json"), baseline)
    source.write_text("def run():\n    return 2\n", encoding="utf-8")

    evidence = collect_change_evidence(tmp_path)

    assert evidence.source == "snapshot"
    assert evidence.paths == ("app.py",)
    assert evidence.qualified_names == ("app.run",)
