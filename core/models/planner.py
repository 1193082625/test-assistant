"""
根据当前证据，决定应该测试什么行为

位于分析器和生成器之间
源码分析结果 + 契约证据 --> Planner --> TestSpec --> 用户审批 --> 测试生成器
"""
from dataclasses import dataclass
from .enums import PlannerStatus
from .test_spec import TestSpec

@dataclass(frozen=True)
class PlannerResult:
    status: PlannerStatus
    spec: TestSpec | None = None
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:

        if not isinstance(self.status, PlannerStatus):
            raise ValueError(
                "status 必须是 PlannerStatus"
            )

        if not isinstance(self.errors, tuple):
            raise ValueError(
                "errors 必须是元组"
            )

        if any(
                (
                    not isinstance(error, str)
                )
                for error in self.errors
        ):
            raise ValueError(
                "errors 必须只包含字符串"
            )
        if any(
                (
                    isinstance(error, str)
                    and error.strip() == ""
                )
            for error in self.errors
        ):
            raise ValueError(
                "errors 中不应该有空字符串"
            )

        if (
                self.status is PlannerStatus.SUCCESS
                and self.spec is None
        ):
            raise ValueError(
                (
                    "spec 不能为空"
                )
            )

        if (
            self.status is PlannerStatus.SUCCESS
            and self.errors
        ):
            raise ValueError(
                (
                    "成功状态下 errors 必须为空"
                )
            )

        if (
            self.status is PlannerStatus.EMPTY
            and self.spec is not None
        ):
            raise ValueError(
                (
                    "空状态下不应该有 spec"
                )
            )

        if (
            self.status is PlannerStatus.INVALID
            and not self.errors
        ):
            raise ValueError(
                (
                    "校验失败缺少 errors"
                )
            )

        if (
            self.status is PlannerStatus.INVALID
            and self.spec is not None
        ):
            raise ValueError(
                (
                    "校验失败 spec 应该为空"
                )
            )

        if (
            not isinstance(self.spec, TestSpec)
            and self.spec is not None
        ):
            raise ValueError(
                (
                    "不支持的 Spec"
                )
            )