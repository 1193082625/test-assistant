"""领域模型测试"""

import pytest

from core.models import Language, ProjectType, TestFramework as Framework, FrameworkInfo


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