"""执行器抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TestResult:
    """单条测试执行结果"""
    name: str # 测试用例名称
    status: str # "passed" | "failed" | "skipped" | "error"
    duration: float # 执行耗时（秒）
    message: str = "" # 失败时的错误信息

class BaseExecutor(ABC):
    """执行器抽象基类"""

    @abstractmethod
    def execute(self, file_path: str) -> list[TestResult]:
        """执行单个测试文件，返回测试结果列表"""
        ...

    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """判断当前执行器是否能处理该文件"""
        ...