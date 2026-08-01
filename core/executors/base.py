"""执行器抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.models.triage import PytestIssue


@dataclass
class TestResult:
    """单条测试执行结果"""
    name: str # 测试用例名称
    status: str # "passed" | "failed" | "skipped" | "error"
    duration: float # 执行耗时（秒）
    message: str = "" # 失败时的错误信息


@dataclass(frozen=True)
class ExecutionEnvironment:
    """一次测试执行使用的最小环境摘要。"""
    runner: str
    runtime: str
    runtime_version: str
    working_directory: str | None


@dataclass
class ExecutionReport:
    """一次测试命令的完整执行报告"""
    test_results: list[TestResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    error_type: str | None = None
    environment: ExecutionEnvironment | None = None

    @property
    def successful(self) -> bool:
        """测试命令是否正常完成"""
        return (
            self.exit_code == 0
            and self.timed_out is False
            and self.error_type is None
        )


@dataclass(frozen=True)
class PytestSuiteResult:
    """pytest 套件执行报告及其结构化生命周期事件。"""

    report: ExecutionReport
    issues: tuple[PytestIssue, ...] = ()


def normalize_process_output(output: str | bytes | None) -> str:
    """将子进程输出统一转换为字符串"""
    if output is None:
        return ""

    if isinstance(output, bytes):
        # errors="replace" 表示在遇到无法按 UTF-8 解码的字节时，用替代字符 � 表示，而不是让错误处理流程再次抛出UnicodeDecodeError
        return output.decode("utf-8", errors="replace")

    return output


def summarize_process_output(
    output: str | bytes | None,
    limit: int = 20_000,
) -> str:
    """规范化并限制报告中的进程输出，避免大型套件撑大持久化结果。"""
    normalized = normalize_process_output(output)
    if len(normalized) <= limit:
        return normalized
    omitted = len(normalized) - limit
    return (
        normalized[:limit]
        + f"\n... [test-assistant omitted {omitted} characters]"
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
