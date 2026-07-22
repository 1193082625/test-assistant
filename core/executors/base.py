"""执行器抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TestResult:
    """单条测试执行结果"""
    name: str # 测试用例名称
    status: str # "passed" | "failed" | "skipped" | "error"
    duration: float # 执行耗时（秒）
    message: str = "" # 失败时的错误信息

@dataclass
class ExecutionReport:
    """一次测试命令的完整执行报告"""
    test_results: list[TestResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    error_type: str | None = None

    @property
    def successful(self) -> bool:
        """测试命令是否正常完成"""
        return (
            self.exit_code == 0
            and self.timed_out is False
            and self.error_type is None
        )


class BaseExecutor(ABC):
    """执行器抽象基类"""

    @abstractmethod
    def execute(self, file_path: str) -> ExecutionReport:
        """执行单个测试文件，返回完整执行报告"""
        ...

    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """判断当前执行器是否能处理该文件"""
        ...