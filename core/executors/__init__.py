"""执行器及注册表"""

from dataclasses import dataclass

from core.executors.base import BaseExecutor
from core.executors.pytest_executor import PytestExecutor
from core.executors.vitest_executor import VitestExecutor

EXECUTOR_REGISTRY: dict[str, type[BaseExecutor]] = {
    "pytest": PytestExecutor,
    "vitest": VitestExecutor,
}

EXECUTOR_LANGUAGES: dict[str, frozenset[str]] = {
    # frozenset({...}) 表示不可修改的集合。普通 set 可以增加或删除元素
    "pytest": frozenset({"python"}),
    "vitest": frozenset({"javascript", "typescript"}),
}

@dataclass
class ExecutorSelection:
    """执行器选择结果"""
    supported: bool
    executor: BaseExecutor | None
    reason: str = ""

def select_executor(
    framework: str,
    language: str | None = None,
    cwd: str | None = None,
) -> ExecutorSelection:
    """根据测试框架和项目语言选择执行器"""
    framework_name = framework.lower()
    executor_class = EXECUTOR_REGISTRY.get(framework_name)

    if executor_class is None:
        return ExecutorSelection(
            supported=False,
            executor=None,
            reason=f"不支持的测试框架: {framework_name}",
        )

    if language is not None:
        language_name = language.lower()
        supported_languages = (
            EXECUTOR_LANGUAGES.get(language_name, frozenset()),
        )

        if language_name not in supported_languages:
            return ExecutorSelection(
                supported=False,
                executor=None,
                reason=(
                    "不支持的执行器组合: "
                    f"language={language_name}, "
                    f"framework={framework_name}"
                )
            )

    return ExecutorSelection(
        supported=True,
        executor=executor_class(cwd=cwd),
    )