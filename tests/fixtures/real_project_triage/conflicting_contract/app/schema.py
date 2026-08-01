"""对外响应契约。"""


class DeleteResponse:
    """删除响应；撤销窗口应在 10 秒后过期。"""

    undo_expires_at: float
