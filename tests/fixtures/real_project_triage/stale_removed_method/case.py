"""模拟旧测试仍要求已删除方法"""

from app.service import Service


def test_removed_async_method_still_expected() -> None:
    assert hasattr(Service, "removed_async"), (
        "Service.removed_async no longer exists"
    )
