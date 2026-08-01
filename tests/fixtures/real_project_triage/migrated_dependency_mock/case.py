"""模拟测试仍然 patch 已移除的旧依赖。"""

from unittest.mock import patch

from app.model import ModelService


@patch("app.model.legacy.load")
def test_initialize_uses_legacy_loader(mock_load) -> None:
    service = ModelService()

    service.initialize()

    mock_load.assert_called_once()
