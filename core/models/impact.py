"""测试影响选择领域模型"""

from dataclasses import dataclass, field

from .enums import TestSelectionMode

@dataclass(frozen=True)
class TestSelection:
    """一次可解释的测试选择结果"""
    mode: TestSelectionMode
    test_files: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """转换为 确定、可序列化 的字典"""
        return {
            "mode": self.mode.value,
            "test_files": sorted(set(self.test_files)),
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
        }