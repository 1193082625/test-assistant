"""测试文件快照模块"""

import os
import hashlib
import tempfile

from core.analyzers.snapshot import get_file_snapshot, take_snapshot, Snapshot

def test_get_file_snapshot():
    """测试单个文件的快照生成"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix='.txt') as f:
        f.write("hello world")
        tmp_path = f.name

    try:
        snap = get_file_snapshot(tmp_path)

        assert isinstance(snap, Snapshot)
        assert snap.path == tmp_path
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

        assert len(snapshots) == 1
        assert snapshots[0].path == normal_file



