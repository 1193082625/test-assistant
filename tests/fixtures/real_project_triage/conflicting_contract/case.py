"""模拟测试契约与当前配置冲突。"""

from app.service import DeleteService


def test_undo_window_matches_original_contract() -> None:
    assert DeleteService.undo_window_seconds == 10, (
        "Expected 10-second undo window, "
        f"got {DeleteService.undo_window_seconds}"
    )
