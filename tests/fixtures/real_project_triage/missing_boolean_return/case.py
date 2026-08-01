"""模拟布尔方法在反例路径隐式返回 None。"""

from app.service import RuleService


def test_alpha_only_is_false() -> None:
    assert RuleService().matches({"alpha"}) is False


def test_delta_only_is_false() -> None:
    assert RuleService().matches({"delta"}) is False


def test_alpha_delta_without_beta_is_false() -> None:
    assert RuleService().matches({"alpha", "delta"}) is False


def test_empty_values_are_false() -> None:
    assert RuleService().matches(set()) is False
