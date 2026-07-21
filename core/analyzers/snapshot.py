"""
快照核心模块
"""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


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

def get_file_snapshot(file_path: str, root_dir: str) -> Snapshot:
    file_path_obj = Path(file_path).resolve()
    root_path_obj = Path(root_dir).resolve()

    # .relative_to ： file_path_obj 相对于 root_path_obj 获取 相对路径；如果文件不在项目根目录下，relative_to() 会抛出 ValueError
    # .as_posix() 得到稳定字符串
    relative_path = file_path_obj.relative_to(root_path_obj).as_posix()

    sha256, size, mtime = get_file_info(str(file_path_obj))
    return Snapshot(
        path=relative_path,
        hash=sha256,
        size=size,
        mtime=mtime,
        type=file_path_obj.suffix, # 扩展名
    )


def take_snapshot(root_dir: str, excludes: list[str]) -> tuple[list[Snapshot], int]:
    snapshots = []
    skipped = 0
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [f for f in dirs if f not in excludes]
        for f in files:
            try:
                full_path = os.path.join(root, f)
                snapshots.append(get_file_snapshot(full_path, root_dir))
            except Exception:
                skipped += 1
    
    return snapshots, skipped

