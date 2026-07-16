import os

def find_project_root(cwd: str | None = None) -> str | None:
    """
    从 cwd 往上找 .autotest/ ， 找到则返回项目根目录，否则返回 None
    1. 从某个目录开始（默认 CWD）
    2. 看当前目录有没有 .autotest/
    3. 有 --> 返回当前目录
    4. 没有 --> 往上走一级
    5. 到 / 了还没有 --> 返回 None
    """
    current = os.path.abspath(cwd or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(current, ".autotest")):
            return current
        parent = os.path.dirname(current)
        if parent == current: # 到文件系统根目录了
            return None
        current = parent