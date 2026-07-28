"""
在这里定义 LangGraph 工作流
调用具体的测试执行器 -- core/executors
调用框架分析、快照对比 -- core/analyzers
"""
import os.path
from typing import TypedDict, Annotated

import yaml
from langgraph.graph import add_messages, StateGraph, END
from langsmith import traceable
from pydantic import BaseModel

from core.analyzers.snapshot import Snapshot
from core.executors import select_executor
from core.executors.base import ExecutionReport
from core.analyzers.impact import select_tests_for_changes
from core.models import TestSelection, TestSelectionMode


class ProjectInfo(BaseModel):
    project_path: str # 项目目标路径
    config: dict # 加载好的 config.yml，所有节点共享

# 定义节点共享state
class GraphStates(TypedDict):
    messages: Annotated[list, add_messages]
    errors: list[str]
    project_info: ProjectInfo
    changed_files: dict # detect的输出 -> run 的输入
    execution_reports_by_file: dict[str, ExecutionReport]
    pending_snapshots: list[Snapshot]
    test_selection: TestSelection

# LangGraph 节点只接收一个参数 -- state，多出来的参数没法传进去
@traceable(name="detect_change")
def detect_change_node(state: GraphStates) -> dict:
    """
    读取旧 manifest
    获取新快照
    调用 compare_snapshots
    """
    # 找到项目的 .autotest/snapshot.json
    target_path = state["project_info"].project_path
    snapshot_path = os.path.join(target_path, ".autotest", "snapshot.json")
    # 加载旧快照
    from core.analyzers.snapshot import (read_snapshot_manifest, take_snapshot, compare_snapshots)
    old_manifest = read_snapshot_manifest(snapshot_path)

    # 拍新快照（take_snapshot）
    # 延迟导入（调用时才 import，第一次慢，之后缓存），避免循环引用
    from core.analyzers.framework import EXCLUDE_DIRS
    new_snapshots, _ = take_snapshot(target_path, EXCLUDE_DIRS)

    changes = compare_snapshots(
        old_manifest.files,
        new_snapshots
    )

    # 写入 changed_files 和 messages
    return {
        "changed_files": changes,
        # 同于确保检测到文件变化后，后面任何中间步骤失败，磁盘上的旧基线都保持不变，下一次运行仍能检测到这些变化。这与数据库事务“全部成功才提交”的思想相似。
        "pending_snapshots": new_snapshots,
        "messages": "增量检查修改内容"
    }

@traceable(name="analyze_impact")
def analyze_impact_node(state: GraphStates) -> dict:
    """为当前项目变更生成结构化测试选择结果"""
    project_info = state["project_info"]
    project_config = project_info.config["project"]

    selection = select_tests_for_changes(
        project_root=project_info.project_path,
        language=project_config.get("language", "unknown"),
        changed_files=state["changed_files"],
    )

    return {
        "test_selection": selection,
        "messages": (
            f"测试选择模式: {selection.mode.value}，"
            f"{len(selection.test_files)} 个测试文件"
        )
    }

@traceable(name="commit_snapshot")
def commit_snapshot_node(state: GraphStates) -> dict:
    """将待提交快照保存为新的比较基线"""
    from core.analyzers.snapshot import commit_snapshot_manifest

    target_path = state["project_info"].project_path
    snapshot_path = os.path.join(target_path, ".autotest", "snapshot.json")

    # 把旧基线替换为新基线
    commit_snapshot_manifest(snapshot_path, state["pending_snapshots"])

    return {
        "messages": "✓ 快照基线已提交"
    }

@traceable(name="run_affected")
def run_affected_node(state: GraphStates):
    """
    执行变化
    入：执行受影响的测试用例
    出：messages += ["执行结果：3 passed，1 failed"]
    结果写入 State
    """
    changed_files = state["changed_files"]
    project_config = (
        state["project_info"].config["project"]
    )
    test_frameworks = project_config["test_frameworks"]
    language = project_config.get("language")

    # 没有变更 --> 跳过执行
    if not any(changed_files.values()):
        return {
            "messages": "✓ 文件无变更，跳过测试执行",
            "execution_reports_by_file": {},
            "errors": [],
        }

    # 没有测试框架 -> 跳过执行
    if not test_frameworks:
        reason = "未检测到测试框架，无法执行选中的测试"
        return {
            "messages": f"⚠ {reason}",
            "execution_reports_by_file": {},
            "errors": [reason],
        }

    project_path = state["project_info"].project_path
    all_results = []
    execution_errors = []
    selection = None
    unsupported_reasons = []
    for framework in test_frameworks:
        candidate = select_executor(
            framework=framework,
            language=language,
            cwd=project_path,
        )

        if candidate.supported:
            selection = candidate
            break

        unsupported_reasons.append(candidate.reason)

    if selection is None:
        reason = "; ".join(unsupported_reasons)

        return {
            "messages": f"⚠ {reason}",
            "execution_reports_by_file": {},
            "errors": [reason],
        }

    executor = selection.executor
    if executor is None:
        reason = "执行器选择结果无效：supported=True 但 executor 为空"

        return {
            "messages": f"⚠ {reason}",
            "execution_reports_by_file": {},
            "errors": [reason],
        }

    execution_reports_by_file = {}

    test_files_to_execute: set[str] = set()

    test_selection = state["test_selection"]
    selected_test_files = test_selection.test_files

    for test_file in selected_test_files:
        if os.path.isabs(test_file):
            file_path = test_file
        else:
            file_path = os.path.join(
                project_path,
                test_file,
            )

        test_files_to_execute.add(file_path)

    for file_path in sorted(test_files_to_execute):
        if not executor.can_handle(file_path):
            continue

        print(
            (
                "  → 执行测试: "
                f"{os.path.basename(file_path)}..."
            ),
            end="",
            flush=True,
        )

        report = executor.execute(file_path)
        all_results.extend(report.test_results)
        execution_reports_by_file[file_path] = report

        if (
                report.error_type is not None
                and report.error_type != "test_failure"
        ):
            detail = (
                    report.stderr
                    or report.stdout
                    or "未知执行错误"
            )

            execution_errors.append(
                (
                    f"{os.path.basename(file_path)}: "
                    f"{report.error_type}: {detail}"
                )
            )

    if not execution_reports_by_file:
        reason = (
            "没有选中的测试文件可由 "
            f"{framework} 执行"
        )
        return {
            "messages": f"⚠ {reason}",
            "execution_reports_by_file": {},
            "errors": [reason],
        }

    # 统计
    passed = sum(1 for r in all_results if r.status == "passed")
    failed = [r for r in all_results if r.status == "failed"]

    failed_errors = [f"{r.name} failed" for r in failed]

    errors = failed_errors + execution_errors

    return {
        "messages":(
            f"执行结果：{passed} passed, "
            f"{len(failed)} failed, "
            f"{len(execution_errors)} execution errors"
        ),
        "execution_reports_by_file": execution_reports_by_file,
        "errors": errors,
    }

def route_after_impact(
        state: GraphStates,
) -> str:
    """根据结构化测试选择决定影响分析后的流程"""
    selection = state["test_selection"]
    # 有明确测试目标 可以执行
    executable_modes = {
        TestSelectionMode.DIRECT,
        TestSelectionMode.MODULE,
        TestSelectionMode.FULL,
    }

    if (
        selection.mode in executable_modes
        and selection.test_files
    ):
        return "run"

    # 没有有效源码变化，可以提交新快照
    if (
        selection.mode is TestSelectionMode.NONE
        and not selection.warnings
    ):
        return "commit"

    # 当前不支持，不能伪装成功
    return "end"

def router(state: GraphStates):
    """根据执行结果决定提交、重试或结束"""
    if state["errors"]:
        return "end"

    return "commit"

def run_graph(target_path: str):
    """增量执行工作流"""
    graph_builder = StateGraph(GraphStates)
    # 添加节点
    graph_builder.add_node("detect_change_node", detect_change_node)
    graph_builder.add_node("analyze_impact_node", analyze_impact_node)
    graph_builder.add_node("run_affected_node", run_affected_node)
    graph_builder.add_node("commit_snapshot_node", commit_snapshot_node)

    # 设置入口节点
    graph_builder.set_entry_point("detect_change_node")

    # 添加边
    graph_builder.add_edge("detect_change_node", "analyze_impact_node")
    graph_builder.add_conditional_edges(
        "analyze_impact_node",
        route_after_impact,
        {
            "run": "run_affected_node",
            "commit": "commit_snapshot_node",
            "end": END,
        },
    )
    graph_builder.add_conditional_edges(
        "run_affected_node",
        router,
{
            "commit": "commit_snapshot_node",
            "end": END
        }
    )
    graph_builder.add_edge("commit_snapshot_node", END)

    app = graph_builder.compile()
    # invoke 需要传入初始状态

    config_path = os.path.join(target_path, ".autotest", "config.yml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    result = app.invoke({
        "messages": [],
        "errors": [],
        "project_info": ProjectInfo(
            project_path=target_path,
            config=config
        ),
        "execution_reports_by_file": {},
        "changed_files": [],
        "pending_snapshots": [],
        "test_selection": TestSelection(
            mode=TestSelectionMode.NONE
        )
    })
    return result
