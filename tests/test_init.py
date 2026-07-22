"""初始化配置写入测试"""
import json
import yaml
from pathlib import Path
from cli.commands.init import write_config, write_snapshot_manifest
from cli.commands.plan import get_snapshot_files
from core.analyzers.snapshot import Snapshot
from core.models import ProjectType, Language, FrameworkInfo
from core.models import TestFramework as Framework

def test_write_config_serializes_enums_as_machine_strings(tmp_path):
    project = FrameworkInfo(
        project_type=ProjectType.BACKEND,
        language=Language.PYTHON,
        frameworks=["FastAPI"],
        test_frameworks=[Framework.PYTEST],
        build_tools=[]
    )

    config_path = write_config(
        autotest_path=str(tmp_path),
        project_config=project,
        mode="auto"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["project"]["type"] == "backend"
    assert config["project"]["language"] == "python"
    assert config["project"]["test_frameworks"] == ["pytest"]
    # test_framework 已经修改为 test_frameworks，这里断言旧字段已不存在
    assert "test_framework" not in config["project"]

def test_write_snapshot_manifest_uses_versioned_format(tmp_path):
    """测试写入磁盘的JSON是否真的采用新版结构"""
    snapshots = [
        Snapshot(
            path="src/app.py",
            hash="abc123",
            size=10,
            mtime=123.0,
            type=".py"
        )
    ]

    snapshot_path = write_snapshot_manifest(
        autotest_path=str(tmp_path),
        snapshots=snapshots
    )
    # Path ： 把字符串路径转换成 Path 对象
    assert Path(snapshot_path).name == "snapshot.json"

    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["version"] == 2
    assert data["files"][0]["path"] == "src/app.py"

def test_get_snapshot_files_reads_versioned_manifest(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({
            "version": 2,
            "files": [
                {
                    "path": "src/app.py",
                    "hash": "abc123",
                    "size": 10,
                    "mtime": 123.0,
                    "type": ".py"
                },
                {
                    "path": "src/utils.py",
                    "hash": "def456",
                    "size": 20,
                    "mtime": 456.0,
                    "type": ".py"
                },
            ],
        }),
        encoding="utf-8",
    )

    snapshot_files = get_snapshot_files(str(snapshot_path))

    assert snapshot_files == [
        "src/app.py",
        "src/utils.py",
    ]