"""供实例方法测试索引使用的最小服务。"""


class Service:
    """返回稳定布尔结果。"""

    def rule(self, values: dict[str, int]) -> bool:
        """至少包含一个正数值时返回 True。"""
        return any(value > 0 for value in values.values())
