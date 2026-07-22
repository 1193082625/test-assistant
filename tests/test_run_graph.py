import json

from core.analyzers.snapshot import (
    SnapshotManifest,
    take_snapshot,
    read_snapshot_manifest,
    Snapshot,
    commit_snapshot_manifest,
    compare_snapshots
)

from core.graphs.run_graph import ProjectInfo, detect_change_node, commit_snapshot_node, router


def test_detect_change_reads_versioned_snapshot_manifest(tmp_path):
    """
    测试文件修改前后的快照
    detect_change_node 把当前文件状态交给后续流程
    检测阶段不能修改磁盘里的旧基线
    """
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

    pending_snapshots = result["pending_snapshots"]

    stored_manifest = read_snapshot_manifest(
        str(autotest_path / "snapshot.json"),
    )

    assert [snapshot.path for snapshot in pending_snapshots] == [
        "app.py",
    ]

    # detect 只负责比较，不能提前覆盖旧基线
    assert stored_manifest.files[0].hash != pending_snapshots[0].hash

def test_commit_snapshot_node_updates_baseline(tmp_path):
    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    snapshot_path = autotest_path / "snapshot.json"

    old_snapshots = [
        Snapshot(
            path="app.py",
            hash="old-hash",
            size=10,
            mtime=1.0,
            type=".py"
        )
    ]
    pending_snapshots = [
        Snapshot(
            path="app.py",
            hash="new-hash",
            size=10,
            mtime=2.0,
            type=".py"
        )
    ]
    # 准备测试环境，写入 “旧基线”，模拟项目之前已经存在一个旧快照
    commit_snapshot_manifest(
        str(snapshot_path),
        old_snapshots,
    )

    state = {
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={}
        ),
        "pending_snapshots": pending_snapshots
    }

    # 执行被测试行为
    result = commit_snapshot_node(state)

    committed_manifest = read_snapshot_manifest(
        str(snapshot_path)
    )
    changes = compare_snapshots(
        committed_manifest.files,
        pending_snapshots
    )

    assert changes == {
        "added": [],
        "deleted": [],
        "modified": [],
    }
    assert result["messages"] == "✓ 快照基线已提交"

def test_router_commits_only_successful_runs():
    """测试路由决策，保证只有成功流程才能进入 commit"""
    successful_state = {
        "errors": [],
        "retry_count": 0,
        "max_retries": 3
    }

    retryable_failure_state = {
        "errors": ["测试失败"],
        "retry_count": 1,
        "max_retries": 3
    }

    exhausted_failure_state = {
        "errors": ["测试仍然失败"],
        "retry_count": 3,
        "max_retries": 3
    }

    assert router(successful_state) == "commit"
    assert router(retryable_failure_state) == "retry"
    assert router(exhausted_failure_state) == "end"