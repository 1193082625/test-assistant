"""
在这里定义 LangGraph 工作流
调用具体的测试执行器 -- core/executors
调用框架分析、快照对比 -- core/analyzers
"""
import json
import os.path
from typing import TypedDict, Annotated

import yaml
from langgraph.graph import add_messages, StateGraph, END
from pydantic import BaseModel

from core.executors.base import TestResult
from core.executors.pytest_executor import PytestExecutor
from core.executors.vitest_executor import VitestExecutor

class ProjectInfo(BaseModel):
    project_path: str # 项目目标路径
    config: dict # 加载好的 config.yml，所有节点共享

# 定义节点共享state
class GraphStates(TypedDict):
    messages: Annotated[list, add_messages]
    errors: list[str]
    project_info: ProjectInfo
    changed_files: dict # detect的输出 -> run 的输入
    test_results_by_file: list[TestResult]
    retry_count: int # 计数器
    max_retries: int # 最大重试次数

# LangGraph 节点只接收一个参数 -- state，多出来的参数没法传进去
def detect_change_node(state: GraphStates) -> dict:
    """
    检测文件变化
    入： 读取文件快照，对比变更
    出：messages += ["检测到 N 个文件变更：a.ts，b.ts"]
    如果无变更： errors 保持空 -> 后续直接走 END
    """
    # 找到项目的 .autotest/snapshot.json
    target_path = state["project_info"].project_path
    snapshot_path = os.path.join(target_path, ".autotest", "snapshot.json")
    # 加载旧快照
    with open(snapshot_path) as f:
        old_snapshots = json.load(f)

    # 拍新快照（take_snapshot）
    # 延迟导入（调用时才 import，第一次慢，之后缓存），避免循环引用
    from core.analyzers.snapshot import take_snapshot
    from core.analyzers.framework import EXCLUDE_DIRS
    new_snapshots, _ = take_snapshot(target_path, EXCLUDE_DIRS)

    """
    对比 -> 找出 新增 / 修改 / 删除的文件
    先转成字典，对比需要按 path 查找，list 不方便
    注意：take_snapshot 返回的是 Snapshot 对象列表 （dataclass），取值用 .path 和 .hash
    dict 用 ["path"] 和 ["hash"]
    
    old_paths = set(old_map.keys())
    new_paths = set(new_map.keys())
    
    # 新增 = new_paths - old_paths
    # 删除 = old_paths - new_paths
    # 修改 = old_paths & new_paths and hash 不同
    """
    old_map = {item["path"]: item["hash"] for item in old_snapshots}
    new_map = {item.path: item.hash for item in new_snapshots}

    old_paths = set(old_map.keys())
    new_paths = set(new_map.keys())

    created_paths = new_paths - old_paths
    deleted_paths = old_paths - new_paths
    same_paths = (old_paths & new_paths)
    modified_paths = []
    for path in same_paths:
        if old_map[path] != new_map[path]:
            modified_paths.append(path)

    # 写入 changed_files 和 messages
    return {
        "changed_files": {
            "added": list(created_paths),
            "deleted": list(deleted_paths),
            "modified": modified_paths,
        },
        "messages": "增量检查修改内容"
    }

def run_affected_node(state: GraphStates):
    """
    执行变化
    入：执行受影响的测试用例
    出：messages += ["执行结果：3 passed，1 failed"]
    结果写入 State
    """
    changed_files = state["changed_files"]
    test_framework = state["project_info"].config["project"]["test_framework"]

    # 没有测试框架 -> 跳过执行
    if not test_framework:
        return {
            "messages": "⚠ 未检测到测试框架，跳过执行",
            "test_results_by_file": {},
            "errors": [],
        }

    project_path = state["project_info"].project_path
    all_results = []
    if "vitest" in test_framework:
        executor = VitestExecutor(cwd=project_path)
    elif "pytest" in test_framework:
        executor = PytestExecutor(cwd=project_path)

    test_results_by_file = {}
    test_cases_dir = os.path.join(project_path, ".autotest", "test_cases")
    if os.path.isdir(test_cases_dir):
        for root, dirs, files in os.walk(test_cases_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if executor.can_handle(file_path):
                    results = list(executor.execute(file_path)) # 执行单个文件
                    all_results.extend(results)
                    test_results_by_file[file_path] = results # 按文件记录

    # 统计
    passed = sum(1 for r in all_results if r.status == "passed")
    failed = [r for r in all_results if r.status == "failed"]

    failed_errors = [f"{r.name} failed" for r in failed]

    return {
        "messages": f"执行结果： {passed} passed, {len(failed)} failed",
        "test_results_by_file": test_results_by_file,
        "errors": failed_errors,
    }

def learn_node(state: GraphStates):
    """
    入：取 errors[0] 分析失败原因，尝试修复
    出：
        errors.pop(0)
        retry_count += 1
        完成后回到 detect_change_node
    """

    return {"retry_count": state["retry_count"]+1}

def router(state: GraphStates):
    """如果结果中有失败，则重新思考并修复"""
    if state["retry_count"] >= state["max_retries"]:
        return "pass" # 超过上限，强制结束
    if state["errors"]:
        return "retry"
    return "pass"

def run_graph(target_path: str):
    """增量执行工作流"""
    graph_builder = StateGraph(GraphStates)
    # 添加节点
    graph_builder.add_node("detect_change_node", detect_change_node)
    graph_builder.add_node("run_affected_node", run_affected_node)
    graph_builder.add_node("learn_node", learn_node)

    # 设置入口节点
    graph_builder.set_entry_point("detect_change_node")

    # 添加边
    graph_builder.add_edge("detect_change_node", "run_affected_node")
    graph_builder.add_conditional_edges("run_affected_node", router, {
        "retry": "learn_node",
        "pass": END
    })
    graph_builder.add_edge("learn_node", "detect_change_node")

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
        "test_results_by_file": [],
        "changed_files": [],
        "retry_count": 0,
        "max_retries": 3
    })
    return result
