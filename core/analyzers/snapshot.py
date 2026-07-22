"""
快照核心模块
"""

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path

# 默认文件上限 5MB
DEFAULT_MAX_FILE_SIZE = 5 * 1024 * 1024

BINARY_EXTENSIONS = {
    # 图片
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".bmp",

    # 音视频
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".wav",

    # 字体
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",

    # 压缩包和可执行文件
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",

    # 常见二进制文档
    ".pdf"
}

SNAPSHOT_FORMAT_VERSION = 2

@dataclass
class Snapshot:
    path: str
    hash: str
    size: int
    mtime: float # 最后修改时间
    type: str

@dataclass
class SnapshotManifest:
    """一个完整的、带版本的项目快照"""

    version: int = SNAPSHOT_FORMAT_VERSION
    files: list[Snapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为可写入 JSON 的普通字典"""
        return {
            "version": self.version,
            "files": [
                {
                    "path": snapshot.path,
                    "hash": snapshot.hash,
                    "size": snapshot.size,
                    "mtime": snapshot.mtime,
                    "type": snapshot.type,
                }
                for snapshot in self.files
            ]
        }

    # @classmethod 表示这个方法属于“类”， 而不是某个具体对象
    # 类方法的第一个参数是 cls（表示 SnapshotManifest 类），调用时不需要先创建实例
    # 使用 cls 的好处是，如果以后有子类集成 SnapshotManifest，这个方法也能创建正确的子类对象
    # -> "SnapshotManifest" 表示方法返回一个 SnapshotManifest 对象，之所以加 “” 是因为 Python 在解释类内部代码时，这个类本身可能还没有完成定义。字符串形式叫作“前向引用”
    @classmethod
    def from_dict(cls, data:dict) -> "SnapshotManifest":
        """
        从 JSON 读取结果恢复快照模型
        把普通字典重新转换成 SnapshotManifest 对象
        """
        version = data.get("version")

        if version != SNAPSHOT_FORMAT_VERSION:
            raise ValueError(
                f"不支持的快照版本：{version}"
            )

        files = [
            Snapshot(
                path=item["path"],
                hash=item["hash"],
                size=item["size"],
                mtime=item["mtime"],
                type=item["type"],
            )
            for item in data.get("files", [])
        ]

        return cls(
            version=version,
            files=files,
        )

def is_binary_file(path:str) -> bool:
    """根据扩展名判断是否为默认排除的二进制文件"""
    suffix = Path(path).suffix.lower()
    return suffix in BINARY_EXTENSIONS

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


def take_snapshot(root_dir: str, excludes: list[str], max_file_size: int = DEFAULT_MAX_FILE_SIZE) -> tuple[list[Snapshot], int]:
    snapshots = []
    """
    表示本次快照没有纳入的文件数量
    - 主动过滤的二进制文件
    超过大小限制的文件
    无法读取的文件
    """
    skipped = 0
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = sorted(directory for directory in dirs if directory not in excludes)
        for f in sorted(files):
            try:
                full_path = os.path.join(root, f)
                if is_binary_file(full_path):
                    skipped += 1
                    continue

                # 判断文件大小
                file_size = os.path.getsize(full_path)
                if file_size > max_file_size:
                    skipped += 1
                    continue

                snapshots.append(get_file_snapshot(full_path, root_dir))
            except Exception:
                skipped += 1

    # 排序快照，保证最终持久化结果满足统一契约
    # 目录内排序只能保证每个目录中的文件有序，但不能完全等同于“所有相对路径全局排序”
    snapshots.sort(key=lambda snapshot: snapshot.path)
    return snapshots, skipped

