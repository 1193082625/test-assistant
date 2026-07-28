import json

import pytest

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
from core.models import (
    TestSelection as Selection,
    TestSelectionMode as SelectionMode,
)
from core.graphs.run_graph import (
    ProjectInfo,
    analyze_impact_node,
    detect_change_node,
    commit_snapshot_node,
    router,
    run_affected_node,
    run_graph,
    route_after_impact
)


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

def test_run_affected_selects_first_supported_framework(
    tmp_path,
    monkeypatch,
):
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    executed_files: list[str] = []

    def fake_execute(self, file_path):
        executed_files.append(file_path)
        return ExecutionReport(
            test_results=[],
            stdout="",
            stderr="",
            exit_code=0,
            error_type=None,
        )

    monkeypatch.setattr(
        PytestExecutor,
        "execute",
        fake_execute,
    )

    state = {
        "changed_files": {
            "added": ["src/app.js"],
            "deleted": [],
            "modified": [],
        },
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=[
                str(test_file),
            ],
        ),
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "test_frameworks": [
                        "jest",
                        "pytest",
                    ],
                }
            },
        ),
    }

    result = run_affected_node(state)

    assert executed_files == [
        str(test_file),
    ]
    assert result["errors"] == []
    assert (
            result["execution_reports_by_file"][
                str(test_file)
            ].exit_code
            == 0
    )

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
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=[str(test_file)],
            evidence=["Explicit test selection for report test"],
            warnings=[]
        ),
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "test_frameworks": ["pytest"]
                }
            }
        ),
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
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=[str(test_file)],
            evidence=["Explicit test selection for runner error test"],
            warnings=[]
        ),
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
    app_path = tmp_path / "app.py"
    app_path.write_text(
        (
            "def value():\n"
            "    return 1\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    test_file = tests_path / "test_app.py"
    test_file.write_text(
        (
            "from app import value\n"
            "\n"
            "def test_value():\n"
            "    assert value() == 1\n"
        ),
        encoding="utf-8",
    )

    old_snapshots, skipped = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    snapshot_path = (
            autotest_path / "snapshot.json"
    )
    commit_snapshot_manifest(
        str(snapshot_path),
        old_snapshots,
    )

    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  language: python\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    # 建立旧基线后修改源码函数。
    app_path.write_text(
        (
            "def value():\n"
            "    return 2\n"
        ),
        encoding="utf-8",
    )

    def fake_execute(self, file_path):
        return ExecutionReport(
            test_results=[],
            stdout="",
            stderr="pytest startup failed",
            exit_code=None,
            error_type="startup_error",
        )

    monkeypatch.setattr(
        PytestExecutor,
        "execute",
        fake_execute,
    )

    result = run_graph(str(tmp_path))

    stored_manifest = read_snapshot_manifest(
        str(snapshot_path)
    )

    current_snapshots, _ = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )

    remaining_changes = compare_snapshots(
        stored_manifest.files,
        current_snapshots,
    )

    assert result["errors"] == [
        (
            "test_app.py: startup_error: "
            "pytest startup failed"
        )
    ]
    assert remaining_changes["modified"] == [
        "app.py",
    ]

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
            "  language: python\n"
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
    def forbidden_execute(self, file_path):
        raise AssertionError("无文件变化时不应调用测试执行器")

    commit_calls = []
    def fake_commit(state):
        commit_calls.append(state["pending_snapshots"])
        return {
            "messages": "✓ 快照基线已提交",
        }

    monkeypatch.setattr("core.graphs.run_graph.commit_snapshot_node", fake_commit)
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

def test_analyze_impact_node_selects_test_files(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    (tests_path / "test_demo.py").write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    state = {
        "changed_files": {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "python",
                    "test_frameworks": ["pytest"],
                }
            }
        )
    }

    result = analyze_impact_node(state)

    assert result == {
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=[
                "tests/test_demo.py",
            ],
            evidence=[
                (
                    "demo.add -> "
                    "tests.test_demo.test_add "
                    "at tests/test_demo.py:3"
                )
            ],
            warnings=[]
        ),
        "messages": (
            "测试选择模式: direct，"
            "1 个测试文件"
        )
    }

def test_run_affected_executes_only_selected_files(
        tmp_path,
        monkeypatch,
):
    """测试 run_affected 不再遍历整个测试目录"""
    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    selected_test = tests_path / "test_add.py"
    selected_test.write_text(
        "def test_add(): pass\n",
        encoding="utf-8",
    )

    unrelated_test = tests_path / "test_subtract.py"
    unrelated_test.write_text(
        "def test_subtract(): pass\n",
        encoding="utf-8",
    )

    executed_files: list[str] = []

    def fake_execute(self, file_path):
        executed_files.append(file_path)
        return  ExecutionReport(
            test_results=[],
            stdout="",
            stderr="",
            exit_code=0,
            error_type=None,
        )

    monkeypatch.setattr(
        PytestExecutor,
        "execute",
        fake_execute,
    )

    state = {
        "changed_files": {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=["tests/test_add.py"],
            evidence=[
                (
                    "demo.add -> "
                    "tests.test_add.test_add "
                    "at tests/test_add.py:1"
                )
            ],
            warnings=[]
        ),
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "python",
                    "test_frameworks": ["pytest"],
                }
            }
        )
    }

    run_affected_node(state)

    assert executed_files == [str(selected_test)]

def test_run_affected_does_not_scan_unselected_candidates(tmp_path, monkeypatch):
    """用测试锁定 “执行节点不能饶过 TestSelection 扫描候选目录”"""

    candidates_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
    )
    candidates_path.mkdir(parents=True)

    unselected_test = (
        candidates_path / "test_generated.py"
    )
    unselected_test.write_text(
        "def test_generated(): pass\n",
        encoding="utf-8",
    )

    executed_files: list[str] = []

    def fake_execute(self, file_path):
        executed_files.append(file_path)
        return ExecutionReport(
            test_results=[],
            stdout="",
            stderr="",
            exit_code=0,
            error_type=None,
        )

    monkeypatch.setattr(
        PytestExecutor,
        "execute",
        fake_execute,
    )

    state = {
        "changed_files": {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
        "test_selection": Selection(
            mode=SelectionMode.NONE,
            test_files=[],
            evidence=[
                "Changed Python symbols: demo.add",
            ],
            warnings=[
                (
                    "No existing tests directly map "
                    "to the changed symbols"
                )
            ]
        ),
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "python",
                    "test_frameworks": ["pytest"],
                }
            }
        )
    }

    run_affected_node(state)

    assert executed_files == []

def test_impact_router_stops_when_tests_need_spec():
    """测试源码有变化但没有测试映射是，应结束当前流程并保留旧快照"""
    state = {
        "test_selection": Selection(
            mode=SelectionMode.NONE,
            test_files=[],
            evidence=[
                "Changed Python symbols: demo.add",
            ],
            warnings=[
                (
                    "No existing tests directly map "
                    "to the changed symbols; create "
                    "a TestSpec before generating tests"
                )
            ]
        )
    }

    assert route_after_impact(state) == "end"

def test_impact_router_runs_direct_selection():
    state = {
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=["tests/test_demo.py"],
        )
    }

    assert route_after_impact(state) == "run"

def test_impact_router_commits_clean_none_selection():
    state = {
        "test_selection": Selection(
            mode=SelectionMode.NONE,
            test_files=[],
            evidence=[
                (
                    "No added or modified Python "
                    "source symbols were found"
                ),
            ],
            warnings=[]
        )
    }

    assert route_after_impact(state) == "commit"

def test_impact_router_stops_unsupported_selection():
    state = {
        "test_selection": Selection(
            mode=SelectionMode.UNSUPPORTED,
            test_files=[],
            evidence=[
                "Requested language: javascript",
            ],
            warnings=[
                (
                    "Symbol-level impact analysis "
                    "currently supports only Python"
                )
            ]
        )
    }

    assert route_after_impact(state) == "end"

def test_impact_router_stops_empty_full_selection():
    """
    源码被删除或分析失败
    → 请求 FULL 降级
    → 项目中却没有发现正式 pytest 文件

    预期不能提交快照
    """
    state = {
        "test_selection": Selection(
            mode=SelectionMode.FULL,
            test_files=[],
            evidence=[
                "Delected Python files: demo.py",
            ],
            warnings=[
                (
                    "Deleted files cannot be analyzed "
                    "from current source; falling back "
                    "to all pytest test files"
                )
            ]
        )
    }

    assert route_after_impact(state) == "end"

def test_run_affected_fails_when_no_test_framework(tmp_path):
    """已选择测试但没有执行框架时，不能提交快照"""
    state = {
        "changed_files": {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=["tests/test_demo.py"],
        ),
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "python",
                    "test_frameworks": [],
                }
            }
        )
    }

    result = run_affected_node(state)

    assert result["errors"] == [
        "未检测到测试框架，无法执行选中的测试"
    ]
    assert router(result) == "end"

def test_run_affected_requires_test_selection(tmp_path):
    state = {
        "changed_files": {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "python",
                    "test_frameworks": ["pytest"],
                }
            }
        )
    }

    with pytest.raises(
        KeyError,
        match="test_selection"
    ):
        run_affected_node(state)

def test_run_affected_fails_when_no_selected_file_can_execute(tmp_path, monkeypatch):
    """选中的测试全部无法执行时，不能提交快照"""
    selected_test = tmp_path / "tests" / "test_demo.py"
    selected_test.parent.mkdir()
    selected_test.write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        PytestExecutor,
        "can_handle",
        lambda self, file_path: False,
    )

    state = {
        "changed_files": {
            "added": [],
            "modified": ["demo.py"],
            "deleted": [],
        },
        "test_selection": Selection(
            mode=SelectionMode.DIRECT,
            test_files=["tests/test_demo.py"],
        ),
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={
                "project": {
                    "language": "python",
                    "test_frameworks": ["pytest"],
                }
            }
        )
    }

    result = run_affected_node(state)

    assert result["execution_reports_by_file"] == {}
    assert result["errors"] == [
        "没有选中的测试文件可由 pytest 执行"
    ]
    assert router(result) == "end"

def test_detect_change_ignores_history_directory(tmp_path):
    app_path = tmp_path / "app.py"
    app_path.write_text(
        "value = 1\n",
        encoding="utf-8",
    )
    snapshots, skipped = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"]
    )
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    commit_snapshot_manifest(
        str(autotest_path / "snapshot.json"),
        snapshots,
    )

    history_path = tmp_path / ".history"
    history_path.mkdir()
    (history_path / "old.py").write_text(
        "value = 0\n",
        encoding="utf-8",
    )

    state = {
        "project_info": ProjectInfo(
            project_path=str(tmp_path),
            config={"project": {}}
        )
    }

    result = detect_change_node(state)
    assert result["changed_files"] == {
        "added": [],
        "modified": [],
        "deleted": [],
    }

@pytest.mark.parametrize(
    "source_relative_path",
    [
        "demo.py",
        "src/demo.py",
    ],
)
def test_run_graph_accepts_layout_and_commits(
    tmp_path,
    monkeypatch,
    source_relative_path,
):
    source_path = tmp_path / source_relative_path
    source_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()

    selected_test = tests_path / "test_demo.py"
    selected_test.write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    unrelated_test = tests_path / "test_other.py"
    unrelated_test.write_text(
        "def test_other(): pass\n",
        encoding="utf-8",
    )

    snapshots, skipped = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()
    snapshot_path = autotest_path / "snapshot.json"

    commit_snapshot_manifest(
        str(snapshot_path),
        snapshots,
    )
    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  language: python\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a - b\n"
        ),
        encoding="utf-8",
    )

    executed_files: list[str] = []

    def fake_execute(self, file_path):
        executed_files.append(file_path)
        return ExecutionReport(
            test_results=[
                ExecutionTestResult(
                    name="test_add",
                    status="passed",
                    duration=0.01,
                )
            ],
            stdout="1 passed",
            stderr="",
            exit_code=0,
            error_type=None,
        )

    monkeypatch.setattr(
        PytestExecutor,
        "execute",
        fake_execute,
    )

    result = run_graph(str(tmp_path))

    assert result["errors"] == []
    assert executed_files == [
        str(selected_test),
    ]

    stored_manifest = read_snapshot_manifest(
        str(snapshot_path)
    )
    current_snapshots, _ = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )

    assert compare_snapshots(
        stored_manifest.files,
        current_snapshots,
    ) == {
        "added": [],
        "modified": [],
        "deleted": [],
    }
