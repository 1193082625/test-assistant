"""
快照核心模块
"""
import json
import tempfile
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

    """
    version表示快照文件格式版本。用于识别 snapshot.json 的数据结构，使读取端能够校验、兼容或迁移不同版本的快照格式
    读取时可以据此决定
    - 当前格式支持：正常解析
    - 旧格式可迁移：执行转换
    - 未知格式：明确报错，避免错误比较
    """
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

def read_snapshot_manifest(snapshot_path: str) -> SnapshotManifest:
    """从 JSON 文件读取并恢复快照清单"""
    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return SnapshotManifest.from_dict(data)

def compare_snapshots(
        old_snapshots: list[Snapshot],
        new_snapshots: list[Snapshot],
) -> dict[str, list[str]]:
    """比较两组快照，返回稳定排序的文件变更"""
    old_map = {
        snapshot.path: snapshot.hash
        for snapshot in old_snapshots
    }

    new_map = {
        snapshot.path: snapshot.hash
        for snapshot in new_snapshots
    }

    old_paths = set(old_map)
    new_paths = set(new_map)

    added = sorted(new_paths - old_paths)
    deleted = sorted(old_paths - new_paths)
    modified = sorted(
        path
        for path in old_paths & new_paths
        if old_map[path] != new_map[path]
    )

    return {
        "added": added,
        "deleted": deleted,
        "modified": modified,
    }

def commit_snapshot_manifest(snapshot_path: str, snapshots: list[Snapshot]) -> str:
    """原子写入快照基线"""
    target_path = Path(snapshot_path)
    manifest = SnapshotManifest(files=snapshots)
    temporary_path = None

    try:
        # 创建临时文件，完整写入并刷新磁盘，再使用 os.replace 一次性替换
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            prefix=f".{target_path.name}",
            suffix=".tmp",
            delete=False # 退出 with 后 不自动删除临时文件，后面还需要用它替换正式文件
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            json.dump(
                manifest.to_dict(),
                temporary_file,
                indent=4,
                ensure_ascii=False,
            )

            # 把 Python 内存缓冲区的数据交给操作系统
            temporary_file.flush()
            # 要求操作系统把文件内容同步到磁盘。fileno() 返回底层文件描述符
            os.fsync(temporary_file.fileno())

        # 用临时文件替换目标文件。在同一文件系统中，这个替换是原子的：其他读取者看到的要么是完整旧文件，要么是完整的新文件，不会看到只写了一半的JSON
        os.replace(temporary_path, target_path)
        return str(target_path)

    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        # raise 后不带异常对象 表示把刚捕获的原异常继续抛出。
        raise

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

