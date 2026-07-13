"""
快照核心模块
"""

from dataclasses import dataclass
import hashlib
import os

@dataclass
class Snapshot:
    path: str
    hash: str
    size: int
    mtime: float # 最后修改时间
    type: str

def get_file_info(path: str) -> tuple[str, int, float]:
    """获取文件 SHA256 哈希 和 stat 信息"""
    sha_value = hashlib.sha256()
    # 以二进制模式打开文件
    with open(path, 'rb') as f:
        # 获取文件 stat 信息（f.fileno() 复用已打开的文件描述符）
        st = os.fstat(f.fileno())
        size = st.st_size
        mtime = st.st_mtime

        for chunk in iter(lambda: f.read(4096), b""):
            sha_value.update(chunk)

    return sha_value.hexdigest(), size, mtime

def get_file_snapshot(f_path: str) -> Snapshot:
    sha256, size, mtime = get_file_info(f_path)
    return Snapshot(
        path=f_path,
        hash=sha256,
        size=size,
        mtime=mtime,
        type=os.path.splitext(f_path)[1], # 扩展名 
    )


def take_snapshot(root_dir: str, excludes: list[str]) -> tuple[list[Snapshot], int]:
    snapshots = []
    skipped = 0
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [f for f in dirs if f not in excludes]
        for f in files:
            try:
                full_path = os.path.join(root, f)
                snapshots.append(get_file_snapshot(full_path))
            except Exception:
                skipped += 1
    
    return snapshots, skipped

