import json

from core.analyzers.snapshot import SnapshotManifest, take_snapshot

from core.graphs.run_graph import ProjectInfo, detect_change_node


def test_detect_change_reads_versioned_snapshot_manifest(tmp_path):
    """测试文件修改前后的快照"""
    app_path = tmp_path / "app.py"
    app_path.write_text("value = 1", encoding="utf-8")

    old_snapshots, skipped = take_snapshot(str(tmp_path), excludes=[".autotest"])
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    manifest = SnapshotManifest(files=old_snapshots)
    (autotest_path / "snapshot.json").write_text(
        json.dumps(manifest.to_dict()),
        encoding="utf-8",
    )

    # 保存旧快照后修改文件
    app_path.write_text("value = 2", encoding="utf-8")

    state = {
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={}
        )
    }

    result = detect_change_node(state)
    assert result["changed_files"]["added"] == []
    assert result["changed_files"]["deleted"] == []
    assert result["changed_files"]["modified"] == ["app.py"]