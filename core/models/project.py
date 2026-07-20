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