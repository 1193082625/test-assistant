"""项目检测结果领域模型"""

from dataclasses import dataclass, field
from .enums import Language, ProjectType, TestFramework

@dataclass
class FrameworkInfo:
    project_type: ProjectType = ProjectType.UNKNOWN
    language: Language = Language.UNKNOWN
    frameworks: list[str] = field(default_factory=list) # default_factory=list 会为每个实例创建独立列表。【普通列表是可变对象，如果多个实例共享一个默认列表，修改一个实例可能污染另一个实例】
    test_frameworks: list[TestFramework] = field(default_factory=list)
    build_tools: list[str] = field(default_factory=list)
    has_dockerfile: bool = False
    has_ci_config: bool = False

    # 增加配置转换
    def to_config(self) -> dict:
        """转换为可写入 YAML / JSON 的配置字典"""
        return {
            "type": self.project_type.value,
            "language": self.language.value,
            "frameworks": list(self.frameworks),
            "test_frameworks": [framework.value for framework in self.test_frameworks],
            "build_tools": list(self.build_tools),
            "has_dockerfile": self.has_dockerfile,
            "has_ci_config": self.has_ci_config,
        }

    # @classmethod 表示这个方法属于类，可以这样调用： FrameworkInfo.from_config(config)
    # 其中 cls(...) 等价于 创建 FrameworkInfo(...)，但未来子类调用时也能返回对应子类
    @classmethod
    def from_config(cls, config: dict) -> "FrameworkInfo":
        """从 YAML / JSON 读取出的字典恢复领域模型"""
        return cls(
            project_type=ProjectType(
                config.get("type", ProjectType.UNKNOWN.value),
            ),
            language=Language(
                config.get("language", Language.UNKNOWN.value),
            ),
            frameworks=list(config.get("frameworks", [])),
            test_frameworks=[
                TestFramework(value)
                for value in config.get("test_frameworks", [])
            ],
            build_tools=list(config.get("build_tools", [])),
            has_dockerfile=bool(config.get("has_dockerfile", False)),
            has_ci_config=bool(config.get("has_ci_config", False)),
        )