"""执行器及注册表"""

from dataclasses import dataclass

from core.executors.base import BaseExecutor
from core.executors.pytest_executor import PytestExecutor
from core.executors.vitest_executor import VitestExecutor

EXECUTOR_REGISTRY: dict[str, type[BaseExecutor]] = {
    "pytest": PytestExecutor,
    "vitest": VitestExecutor,
}

@dataclass
class ExecutorSelection:
    """执行器选择结果"""
    supported: bool
    executor: BaseExecutor | None
    reason: str = ""

def select_executor(
    framework: str,
    cwd: str | None = None,
) -> ExecutorSelection:
    """根据测试框架选择执行器"""
    framework_name = framework.lower()
    executor_class = EXECUTOR_REGISTRY.get(framework_name)

    if executor_class is None:
        return ExecutorSelection(
            supported=False,
            executor=None,
            reason=f"不支持的测试框架: {framework_name}",
        )

    return ExecutorSelection(
        supported=True,
        executor=executor_class(cwd=cwd),
    )