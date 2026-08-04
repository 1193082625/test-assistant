"""初始化配置写入测试"""
import json
import yaml
import pytest
from pathlib import Path

from click.testing import CliRunner

from cli.commands.init import (
    discard_autotest_backup,
    init as init_command,
    restore_autotest_backup,
    write_config,
    write_snapshot_manifest,
)
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
        project_name="demo",
        project_config=project,
        mode="auto"
    )


    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["project"]["name"] == "demo"
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


def test_init_preserves_existing_autotest_when_write_fails(tmp_path, monkeypatch):
    history_path = (
            tmp_path
            / ".autotest"
            / "diagnoses"
            / "existing.json"
    )
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        '{"existing": true}\n',
        encoding="utf-8",
    )

    original_config = (
        "project:\n"
        "  name: existing-project\n"
        "custom:\n"
        "  preserve: true\n"
    )
    config_path = tmp_path / ".autotest" / "config.yml"
    config_path.write_text(original_config, encoding="utf-8")

    # 创建一个必然失败的函数。
    # 不管传入什么参数，它都会抛出异常
    def fail_snapshot_write(*args, **kwargs):
        raise OSError("模拟 snapshot 写入失败")

    # 用 monkeypatch 替换真实函数： 当 init() 调用 write_snapshot_manifest() 时，不执行真实写入，改为调用定义的失败函数
    monkeypatch.setattr("cli.commands.init.write_snapshot_manifest", fail_snapshot_write)

    runner = CliRunner()
    # 相当于用户执行： test-assistant init --path <tmp_path>
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
        ],
        # 因为项目已经存在 .autotest ， 命令会询问： 是否覆盖？
        input="y\n",
    )

    assert result.exit_code == 1, result.output
    assert "初始化失败" in result.output
    assert history_path.exists()
    assert history_path.read_text(encoding="utf-8") == '{"existing": true}\n'

    assert config_path.exists()
    assert config_path.read_text(encoding="utf-8") == original_config

    backup_pattern = f".{tmp_path.name}-autotest-backup-*"
    # 这条断言证明恢复完成后，原 .autotest 已恢复，备份中的 .autotest 已移动回来，空的备份容器已删除，项目同级没有遗留备份
    assert list(
        tmp_path.parent.glob(backup_pattern)
    ) == []


def test_init_removes_new_autotest_when_write_fails(
    tmp_path,
    monkeypatch,
):
    autotest_path = (
        tmp_path / ".autotest"
    )
    assert not autotest_path.exists()

    def fail_snapshot_write(*args, **kwargs):
        raise OSError(
            "模拟 snapshot 写入失败"
        )

    monkeypatch.setattr(
        "cli.commands.init.write_snapshot_manifest",
        fail_snapshot_write,
    )

    runner = CliRunner()
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
        ]
    )

    assert result.exit_code == 1, result.output
    assert "初始化失败" in result.output
    assert not autotest_path.exists()

    backup_pattern = f".{tmp_path.name}-autotest-backup-*"
    assert list(
        tmp_path.parent.glob(backup_pattern)
    ) == []

def test_init_updates_existing_autotest_and_removes_backup(tmp_path):
    """证明原有历史不会因为成功覆盖而丢失"""

    history_path = (
        tmp_path
        / ".autotest"
        / "diagnoses"
        / "existing.json"
    )
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        '{"existing": true}\n',
        encoding="utf-8",
    )

    old_config = (
        "project:\n"
        "  name: old-project\n"
    )
    config_path = tmp_path / ".autotest" / "config.yml"
    config_path.write_text(old_config, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
            "--name",
            "update-project",
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert "项目已绑定" in result.output

    assert history_path.exists()
    assert history_path.read_text(encoding="utf-8") == '{"existing": true}\n'

    updated_config = yaml.safe_load(
        config_path.read_text(encoding="utf-8")
    )
    assert updated_config["project"]["name"] == "update-project"

    snapshot_path = (
        tmp_path
        / ".autotest"
        / "snapshot.json"
    )
    assert snapshot_path.exists()

    backup_pattern = f".{tmp_path.name}-autotest-backup-*"
    assert list(
        tmp_path.parent.glob(backup_pattern)
    ) == []

def test_init_rejects_autotest_symlink_without_touching_target(
    tmp_path,
):
    outside_directory = (
        tmp_path.parent
        / f"{tmp_path.name}-outside"
    )
    outside_directory.mkdir()

    marker_path = (
        outside_directory
        / "important.json"
    )
    marker_path.write_text(
        '{"preserve": true}\n',
        encoding="utf-8",
    )

    autotest_path = (
        tmp_path
        / ".autotest"
    )
    autotest_path.symlink_to(
        outside_directory,
        target_is_directory=True,
    )

    runner = CliRunner()
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
        ],
        input="y\n",
    )

    assert result.exit_code == 1, result.output
    assert (
        ".autotest 不能是符号链接"
        in result.output
    )

    assert autotest_path.is_symlink()
    assert marker_path.exists()
    assert marker_path.read_text(
        encoding="utf-8",
    ) == '{"preserve": true}\n'

    backup_pattern = (
        f".{tmp_path.name}-autotest-backup-*"
    )
    assert list(
        tmp_path.parent.glob(backup_pattern)
    ) == []

def test_init_preserves_existing_autotest_when_backup_fails(
    tmp_path,
    monkeypatch,
):
    history_path = (
        tmp_path
        / ".autotest"
        / "diagnoses"
        / "existing.json"
    )
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        '{"existing": true}\n',
        encoding="utf-8",
    )

    def fail_copytree(*args, **kwargs):
        raise OSError(
            "模拟备份复制失败"
        )

    monkeypatch.setattr(
        "cli.commands.init.shutil.copytree",
        fail_copytree,
    )

    runner = CliRunner()
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
        ],
        input="y\n",
    )

    assert result.exit_code == 1, result.output
    assert "初始化失败" in result.output
    assert "模拟备份复制失败" in result.output

    assert history_path.exists()
    assert history_path.read_text(
        encoding="utf-8",
    ) == '{"existing": true}\n'

    assert not (
        tmp_path
        / ".autotest"
        / "config.yml"
    ).exists()

    backup_pattern = (
        f".{tmp_path.name}-autotest-backup-*"
    )
    assert list(
        tmp_path.parent.glob(backup_pattern)
    ) == []

def test_init_reports_rollback_failure_and_keeps_backup(
    tmp_path,
    monkeypatch,
):
    history_content = '{"existing": true}\n'
    history_path = (
        tmp_path
        / ".autotest"
        / "diagnoses"
        / "existing.json"
    )
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        history_content,
        encoding="utf-8",
    )

    original_config = (
        "project:\n"
        "  name: existing-project\n"
    )
    config_path = (
        tmp_path
        / ".autotest"
        / "config.yml"
    )
    config_path.write_text(
        original_config,
        encoding="utf-8",
    )

    def fail_snapshot_write(*args, **kwargs):
        raise OSError(
            "模拟初始化写入失败"
        )

    def fail_restore(*args, **kwargs):
        raise OSError(
            "模拟回滚失败"
        )

    monkeypatch.setattr(
        "cli.commands.init.write_snapshot_manifest",
        fail_snapshot_write,
    )
    monkeypatch.setattr(
        "cli.commands.init.restore_autotest_backup",
        fail_restore,
    )

    runner = CliRunner()
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
        ],
        input="y\n",
    )

    assert result.exit_code == 1, result.output
    assert (
        "模拟初始化写入失败"
        in result.output
    )
    assert (
        "回滚失败"
        in result.output
    )
    assert (
        "模拟回滚失败"
        in result.output
    )

    backup_pattern = (
        f".{tmp_path.name}-autotest-backup-*"
    )
    backup_roots = list(
        tmp_path.parent.glob(backup_pattern)
    )
    assert len(backup_roots) == 1

    backup_history = (
        backup_roots[0]
        / ".autotest"
        / "diagnoses"
        / "existing.json"
    )
    backup_config = (
        backup_roots[0]
        / ".autotest"
        / "config.yml"
    )

    assert backup_history.exists()
    assert backup_history.read_text(
        encoding="utf-8",
    ) == history_content

    assert backup_config.exists()
    assert backup_config.read_text(
        encoding="utf-8",
    ) == original_config

def test_init_keeps_completed_workspace_when_backup_discard_fails(
    tmp_path,
    monkeypatch,
):
    history_path = (
        tmp_path
        / ".autotest"
        / "diagnoses"
        / "existing.json"
    )
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        '{"existing": true}\n',
        encoding="utf-8",
    )

    config_path = (
        tmp_path
        / ".autotest"
        / "config.yml"
    )
    config_path.write_text(
        "project:\n"
        "  name: old-project\n",
        encoding="utf-8",
    )

    def fail_discard(*args, **kwargs):
        raise OSError(
            "模拟备份清理失败"
        )

    monkeypatch.setattr(
        "cli.commands.init.discard_autotest_backup",
        fail_discard,
    )

    runner = CliRunner()
    result = runner.invoke(
        init_command,
        [
            "--path",
            str(tmp_path),
            "--name",
            "updated-project",
        ],
        input="y\n",
    )

    assert result.exit_code == 1, result.output
    assert (
        "初始化已完成，但备份清理失败"
        in result.output
    )
    assert (
        "模拟备份清理失败"
        in result.output
    )

    updated_config = yaml.safe_load(
        config_path.read_text(
            encoding="utf-8",
        )
    )
    assert (
        updated_config["project"]["name"]
        == "updated-project"
    )

    assert history_path.exists()
    assert history_path.read_text(
        encoding="utf-8",
    ) == '{"existing": true}\n'

    backup_pattern = (
        f".{tmp_path.name}-autotest-backup-*"
    )
    backup_roots = list(
        tmp_path.parent.glob(backup_pattern)
    )
    assert len(backup_roots) == 1

    backup_config = (
        backup_roots[0]
        / ".autotest"
        / "config.yml"
    )
    assert backup_config.exists()
    assert (
        backup_config.read_text(
            encoding="utf-8",
        )
        == (
            "project:\n"
            "  name: old-project\n"
        )
    )

@pytest.mark.parametrize(
    "operation",
    [
        restore_autotest_backup,
        discard_autotest_backup,
    ],
)
def test_autotest_backup_operations_reject_uncontrolled_path(
    tmp_path,
    operation,
):
    autotest_path = (
        tmp_path
        / ".autotest"
    )
    autotest_path.mkdir()

    current_marker = (
        autotest_path
        / "current.json"
    )
    current_marker.write_text(
        '{"current": true}\n',
        encoding="utf-8",
    )

    uncontrolled_backup = (
        tmp_path
        / ".uncontrolled-backup"
    )
    backup_autotest = (
        uncontrolled_backup
        / ".autotest"
    )
    backup_autotest.mkdir(
        parents=True
    )

    backup_marker = (
        backup_autotest
        / "backup.json"
    )
    backup_marker.write_text(
        '{"backup": true}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="备份目录不属于目标项目",
    ):
        operation(
            str(tmp_path),
            str(uncontrolled_backup),
        )

    assert current_marker.exists()
    assert current_marker.read_text(
        encoding="utf-8",
    ) == '{"current": true}\n'

    assert backup_marker.exists()
    assert backup_marker.read_text(
        encoding="utf-8",
    ) == '{"backup": true}\n'
