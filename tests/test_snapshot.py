"""测试文件快照模块"""

import os
import hashlib
import tempfile
import json
import pytest

from core.analyzers.snapshot import (
    get_file_snapshot,
    take_snapshot,
    Snapshot,
    SnapshotManifest,
    SNAPSHOT_FORMAT_VERSION,
    read_snapshot_manifest
)


def test_get_file_snapshot():
    """测试单个文件的快照生成"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix='.txt') as f:
        f.write("hello world")
        tmp_path = f.name

    try:
        root_dir = os.path.dirname(tmp_path)
        snap = get_file_snapshot(tmp_path, root_dir)

        assert isinstance(snap, Snapshot)
        # 文件相对于其父目录的路径就是文件名
        assert snap.path == os.path.basename(tmp_path)
        assert snap.type == ".txt"
        assert snap.size == 11 # "hello world" 是 11 个字节

        # 验证 SHA256
        expected_hash = hashlib.sha256(b"hello world").hexdigest()
        assert snap.hash == expected_hash
    finally:
        os.unlink(tmp_path)

def test_take_snapshot_with_excludes():
    """测试排除目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建正常文件
        normal_file = os.path.join(tmpdir, "normal.py")
        with open(normal_file, "w") as f:
            f.write("print('hello world')")

        # 创建应被排除的目录和文件
        exclude_dir = os.path.join(tmpdir, "node_modules")
        os.makedirs(exclude_dir)
        exclude_file = os.path.join(exclude_dir, "ignored.js")
        with open(exclude_file, 'w') as f:
            f.write("ignored")

        snapshots, skipped = take_snapshot(tmpdir, excludes=["node_modules"])

        assert skipped == 0
        assert len(snapshots) == 1
        assert snapshots[0].path == "normal.py"

def test_take_snapshot_stores_project_relative_paths(tmp_path):
    """测试保存相对于项目根目录的路径"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "app.py").write_text("print('hello world')", encoding="utf-8")

    snapshots, skipped = take_snapshot(str(tmp_path), excludes=[])

    assert skipped == 0
    assert len(snapshots) == 1
    assert snapshots[0].path == "src/app.py"

def test_take_snapshot_has_stable_sorted_order(tmp_path):
    """测试 快照 稳定排序"""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # 故意不安字母顺序创建
    (tmp_path / "z.py").write_text("z = 1", encoding="utf-8")

    (tmp_path / "a.py").write_text("a = 1", encoding="utf-8")

    (src_dir / "b.py").write_text("b = 1", encoding="utf-8")

    first, first_skipped = take_snapshot(str(tmp_path), excludes=[])

    second, second_skipped = take_snapshot(str(tmp_path), excludes=[])

    first_paths = [snapshot.path for snapshot in first]
    second_paths = [snapshot.path for snapshot in second]

    assert first_skipped == 0
    assert second_skipped == 0
    assert first_paths == sorted(first_paths)
    assert second_paths == first_paths

def test_take_snapshot_skips_binary_files(tmp_path):
    """测试快照跳过二进制文件"""
    (tmp_path / "app.py").write_text("value = 1", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    snapshots, skipped = take_snapshot(str(tmp_path), excludes=[])
    paths = [s.path for s in snapshots]

    assert paths == ["app.py"]
    assert skipped == 1

def test_take_snapshot_skips_files_over_size_limit(tmp_path):
    """测试超过限制的文件大小的文件跳过获取快照"""
    (tmp_path / "small.txt").write_text("small", encoding="utf-8")
    (tmp_path / "large.txt").write_text("hello world"*11, encoding="utf-8")

    # max_file_size 单位是 字节
    snapshots, skipped = take_snapshot(str(tmp_path), excludes=[], max_file_size = 10)

    paths = [s.path for s in snapshots]

    assert paths == ["small.txt"]
    assert skipped == 1

def test_snapshot_manifest_round_trip():
    """验证完整的快照信息往返测试，带版本号"""
    original = SnapshotManifest(
        files=[
            Snapshot(
                path="src/app.py",
                hash="abc123",
                size=10,
                mtime=123.0,
                type=".py"
            )
        ]
    )

    data = original.to_dict()
    restored = SnapshotManifest.from_dict(data)

    assert data["version"] == SNAPSHOT_FORMAT_VERSION
    assert data["files"][0]["path"] == "src/app.py"
    assert restored == original

def test_snapshot_manifest_rejects_unsupported_version():
    """版本拒绝测试"""
    with pytest.raises(
        ValueError,
        match="不支持的快照版本"
    ):
        SnapshotManifest.from_dict({
            "version": 1,
            "files": []
        })

def test_read_snapshot_manifest_from_file(tmp_path):
    """测试统一的读取函数"""
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        # json.dumps 用于把 Python 字典 转换成 JSON 字符串
        # json.dump 是直接把数据写进一个对象
        json.dumps({
            "version": SNAPSHOT_FORMAT_VERSION,
            "files": [
                {
                    "path": "src/app.py",
                    "hash": "abc123",
                    "size": 10,
                    "mtime": 123.0,
                    "type": ".py"
                }
            ],
        }),
        encoding="utf-8"
    )
    manifest = read_snapshot_manifest(str(snapshot_path))

    assert manifest.version == SNAPSHOT_FORMAT_VERSION
    assert len(manifest.files) == 1
    assert manifest.files[0].path == "src/app.py"