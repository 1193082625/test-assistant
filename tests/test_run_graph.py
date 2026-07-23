import json

from core.analyzers.snapshot import (
    SnapshotManifest,
    take_snapshot,
    read_snapshot_manifest,
    Snapshot,
    commit_snapshot_manifest,
    compare_snapshots
)
from core.executors import PytestExecutor
from core.executors.base import ExecutionReport, TestResult as ExecutionTestResult

from core.graphs.run_graph import ProjectInfo, detect_change_node, commit_snapshot_node, router, run_affected_node, \
    run_graph


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
    }

    failure_state = {
        "errors": ["测试仍然失败"],
    }

    assert router(successful_state) == "commit"
    assert router(failure_state) == "end"

def test_detect_commit_detect_returns_no_changes(tmp_path):
    """闭环验收测试。测试快照提交后再次检测得到空变更"""
    app_path = tmp_path / "app.py"
    app_path.write_text("value = 1", encoding="utf-8")

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    snapshot_path = autotest_path / "snapshot.json"

    # 模拟首次运行前的空基线
    commit_snapshot_manifest(
        str(snapshot_path),
        [],
    )

    project_info = ProjectInfo(
        project_path=str(tmp_path),
        config={}
    )

    first_result = detect_change_node({
        "project_info": project_info,
    })

    assert first_result["changed_files"] == {
        "added": ["app.py"],
        "deleted": [],
        "modified": [],
    }

    commit_snapshot_node({
        "project_info": project_info,
        "pending_snapshots": first_result["pending_snapshots"],
    })

    second_result = detect_change_node({
        "project_info": project_info,
    })

    assert second_result["changed_files"] == {
        "added": [],
        "deleted": [],
        "modified": [],
    }

def test_run_affected_returns_explainable_unsupported_framework(tmp_path):
    test_cases_path = (
        tmp_path / ".autotest" / "test_cases"
    )

    # parents=True 表示父目录不存在时一起创建
    test_cases_path.mkdir(parents=True)

    (test_cases_path / "demo.test.js").write_text(
        "test('demo', () => {})",
        encoding="utf-8",
    )

    state = {
        "changed_files": {
            "added": ["src/app.js"],
            "deleted": [],
            "modified": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "test_frameworks": ["jest"]
                }
            }
        ),
    }

    result = run_affected_node(state)

    assert result == {
        "messages": "⚠ 不支持的测试框架: jest",
        "execution_reports_by_file": {},
        "errors": ["不支持的测试框架: jest"],
    }

def test_run_affected_selects_first_supported_framework(tmp_path):
    state = {
        "changed_files": {
            "added": ["src/app.js"],
            "deleted": [],
            "modified": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "test_frameworks": ["jest", "pytest"]
                }
            }
        )
    }

    result = run_affected_node(state)

    assert result == {
        "messages": "执行结果：0 passed, 0 failed, 0 execution errors",
        "execution_reports_by_file": {},
        "errors": [],
    }

def test_run_affected_consumes_execution_report(tmp_path, monkeypatch):
    """Graph 不仅要保存单条用例结果，还要保存每个文件的完整执行报告，包括退出码喝原始输出"""
    test_cases_path = (
        tmp_path / ".autotest" / "test_cases"
    )
    test_cases_path.mkdir(parents=True)

    test_file = test_cases_path / "test_demo.py"
    test_file.write_text(
        "def test_demo(): assert False",
        encoding="utf-8",
    )

    def fake_execute(self, file_path):
        return ExecutionReport(
            test_results = [
                ExecutionTestResult(
                    name="test_demo",
                    status="failed",
                    duration=0.01,
                    message="assert False",
                )
            ],
            stdout="test_demo.py::test_demo FAILED",
            stderr="",
            exit_code=1,
            error_type="test_failure",
        )

    monkeypatch.setattr(PytestExecutor, "execute", fake_execute)

    state = {
        "changed_files": {
            "added": ["src/app.py"],
            "deleted": [],
            "modified": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "test_frameworks": ["pytest"]
                }
            }
        )
    }

    result = run_affected_node(state)

    report = result["execution_reports_by_file"][str(test_file)]

    assert report.exit_code == 1
    assert report.stdout == "test_demo.py::test_demo FAILED"
    assert result["errors"] == ["test_demo failed"]

def test_run_affected_propagates_runner_error(tmp_path, monkeypatch):
    """测试 Runner 错误必须进入 Graph 的 errors , 不能显示成单纯的 0 failed"""
    test_cases_path = (tmp_path / ".autotest" / "test_cases")
    test_cases_path.mkdir(parents=True)

    test_file = test_cases_path / "test_demo.py"
    test_file.write_text(
        "def test_demo(): pass",
        encoding="utf-8",
    )

    def fake_execute(self, file_path):
        return ExecutionReport(
            test_results = [],
            stdout="",
            stderr="ERROR: test file not found",
            exit_code=4,
            error_type="runner_error",
        )

    monkeypatch.setattr(PytestExecutor, "execute", fake_execute)

    state = {
        "changed_files": {
            "added": ["src/app.py"],
            "deleted": [],
            "modified": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "test_frameworks": ["pytest"]
                }
            }
        )
    }

    result = run_affected_node(state)

    assert result["errors"] == [
        (
            "test_demo.py: runner_error: "
            "ERROR: test file not found"
         )
    ]
    assert result["messages"] == (
        "执行结果：0 passed, 0 failed, "
        "1 execution errors"
    )

def test_run_graph_failure_does_not_commit_snapshot(tmp_path, monkeypatch):
    app_path = (tmp_path / "app.py")
    app_path.write_text("value = 1", encoding="utf-8")

    old_snapshots, skipped = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )

    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    test_cases_path = autotest_path / "test_cases"
    test_cases_path.mkdir(parents=True)

    snapshot_path = autotest_path / "snapshot.json"
    commit_snapshot_manifest(
        str(snapshot_path),
        old_snapshots,
    )

    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    (test_cases_path / "test_demo.py").write_text(
        "def test_demo(): pass",
        encoding="utf-8",
    )

    # 建立旧基线后修改项目文件
    app_path.write_text("value = 2", encoding="utf-8")

    def fake_generate(*args, **kwargs):
        return []

    def fake_execute(self, file_path):
        return ExecutionReport(
            test_results = [],
            stdout="",
            stderr="pytest startup failed",
            exit_code=None,
            error_type="startup_error",
        )

    monkeypatch.setattr("core.graphs.run_graph.generate_tests_for_project", fake_generate)
    monkeypatch.setattr(PytestExecutor, "execute", fake_execute)

    result = run_graph(str(tmp_path))

    stored_manifest = read_snapshot_manifest(str(snapshot_path))

    current_snapshots, _ = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )

    remaining_changes = compare_snapshots(stored_manifest.files, current_snapshots)

    assert result["errors"] == [
        (
            "test_demo.py: startup_error: "
            "pytest startup failed"
        )
    ]
    assert remaining_changes["modified"] == ["app.py"]

def test_run_graph_success_reaches_commit_once(tmp_path, monkeypatch):
    app_path = (tmp_path / "app.py")
    app_path.write_text("value = 1", encoding="utf-8")

    snapshots, skipped = take_snapshot(str(tmp_path), excludes=[".autotest"])
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    commit_snapshot_manifest(str(autotest_path / "snapshot.json"), snapshots)
    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    test_cases_path = autotest_path / "test_cases"
    test_cases_path.mkdir()

    (test_cases_path / "test_demo.py").write_text(
        "def test_demo(): pass",
        encoding="utf-8",
    )
    def forbidden_generate(*args, **kwargs):
        raise AssertionError("无文件变化时不应调用测试生成器")

    def forbidden_execute(self, file_path):
        raise AssertionError("无文件变化时不应调用测试执行器")

    commit_calls = []
    def fake_commit(state):
        commit_calls.append(state["pending_snapshots"])
        return {
            "messages": "✓ 快照基线已提交",
        }

    monkeypatch.setattr("core.graphs.run_graph.commit_snapshot_node", fake_commit)
    monkeypatch.setattr("core.graphs.run_graph.generate_tests_for_project", forbidden_generate)
    monkeypatch.setattr(PytestExecutor, "execute", forbidden_execute)

    result = run_graph(str(tmp_path))

    assert result["errors"] == []
    assert len(commit_calls) == 1
    assert [
               snapshot.path
               for snapshot in commit_calls[0]
           ] == ["app.py"]

def test_run_affected_rejects_language_framework_mismatch(tmp_path):
    state = {
        "changed_files": {
            "added": ["src/app.js"],
            "deleted": [],
            "modified": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "javascript",
                    "test_frameworks": ["pytest"],
                }
            }
        )
    }

    result = run_affected_node(state)

    reason = (
        "不支持的执行器组合: "
        "language=javascript, framework=pytest"
    )

    assert result == {
        "messages": f"⚠ {reason}",
        "execution_reports_by_file": {},
        "errors": [reason],
    }