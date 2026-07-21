"""领域模型测试"""

import pytest

from core.models import Language, ProjectType, TestFramework as Framework, FrameworkInfo, ProjectAnalysis, ProjectModule


def test_enum_values_are_stable_lowercase_string():
    """确保枚举值是稳定的小写机器值"""
    assert ProjectType.FRONTEND.value == "frontend"
    assert Language.PYTHON.value == "python"
    assert Framework.VITEST.value == "vitest"

def test_enum_can_be_created_from_machine_value():
    """合法机器值可以恢复成枚举"""
    assert ProjectType("backend") is ProjectType.BACKEND
    assert Language("python") is Language.PYTHON
    assert Framework("pytest") is Framework.PYTEST

def test_enum_rejects_display_names():
    """非契约值不能进入领域模型"""

    with pytest.raises(ValueError):
        ProjectType("Backend")

    with pytest.raises(ValueError):
        Framework("Pytest")

def test_framework_info_has_safe_unknown_defaults():
    """测试 FrameworkInfo 实例 的默认值"""
    info = FrameworkInfo()

    assert info.project_type is ProjectType.UNKNOWN
    assert info.language is Language.UNKNOWN
    assert info.frameworks == []
    assert info.test_frameworks == []
    assert info.build_tools == []
    assert info.has_dockerfile is False
    assert info.has_ci_config is False

def test_framework_info_lists_are_not_shared():
    """测试 FrameworkInfo 实例之间的 list 互不影响"""
    first = FrameworkInfo()
    second = FrameworkInfo()

    first.frameworks.append("FastAPI")

    assert first.frameworks == ["FastAPI"]
    assert second.frameworks == []

def test_framework_info_config_round_trip():
    """往返测试 ： 领域对象 --> 配置字典 --> 领域对象；不丢失数据"""
    original = FrameworkInfo(
        project_type=ProjectType.BACKEND,
        language=Language.PYTHON,
        frameworks=["FastAPI"],
        test_frameworks=[Framework.PYTEST],
        build_tools=["poetry"],
        has_dockerfile=True,
        has_ci_config=True,
    )
    config = original.to_config()
    restored = FrameworkInfo.from_config(config)

    assert restored == original

def test_framework_info_from_empty_config_uses_unknown_defaults():
    """缺省值测试：缺失字段使用安全默认值"""
    info = FrameworkInfo.from_config({})

    assert info == FrameworkInfo()

def test_framework_info_from_config_rejects_display_names():
    """严格输入测试：非法展示名称不能进入领域模型"""
    with pytest.raises(ValueError):
        FrameworkInfo.from_config({
            "type": "Backend",
            "language": "python",
        })

def test_project_analysis_can_contain_multiple_modules():
    frontend = ProjectModule(
        root_path="/demo/frontend",
        source_file="package.json",
        framework_info=FrameworkInfo(
            project_type=ProjectType.FRONTEND,
            language=Language.TYPESCRIPT,
        ),
    )

    backend = ProjectModule(
        root_path="/demo/backend",
        source_file="pyproject.toml",
        framework_info=FrameworkInfo(
            project_type=ProjectType.BACKEND,
            language=Language.PYTHON,
        ),
    )

    analysis = ProjectAnalysis(
        root_path="/demo",
        modules=[frontend, backend],
    )

    assert len(analysis.modules) == 2
    assert analysis.modules[0].framework_info.project_type is ProjectType.FRONTEND
    assert analysis.modules[1].framework_info.language is Language.PYTHON

def test_project_analysis_lists_are_not_shared():
    frist = ProjectAnalysis(root_path="/frist")
    second = ProjectAnalysis(root_path="/second")

    frist.warnings.append("demo warning")

    assert frist.warnings == ["demo warning"]
    assert second.warnings == []