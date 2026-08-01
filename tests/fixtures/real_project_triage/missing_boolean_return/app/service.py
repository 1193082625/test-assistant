"""缺少显式 False 返回的最小服务。"""


class RuleService:
    """判断输入能否满足任意规则。"""

    def matches(self, values: set[str]) -> bool:
        """匹配 alpha+beta、gamma 或 beta+delta 组合。"""
        if {"alpha", "beta"} <= values:
            return True
        if "gamma" in values:
            return True
        if {"beta", "delta"} <= values:
            return True
