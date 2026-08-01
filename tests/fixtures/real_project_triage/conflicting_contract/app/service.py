"""读取当前配置的最小删除服务。"""

from app.config import UNDO_WINDOW_SECONDS


class DeleteService:
    """公开当前撤销窗口。"""

    undo_window_seconds = UNDO_WINDOW_SECONDS
