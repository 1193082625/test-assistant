"""模拟通过 self 属性调用源码实例方法的测试。"""

from app.service import Service


class TestService:
    def setup_method(self) -> None:
        self.service = Service()

    def test_empty_values_are_false(self) -> None:
        assert self.service.rule({}) is False
