"""初始化和环境预检"""
import os
import shutil
import tempfile
from copy import deepcopy

import click
import yaml

from core.models import FrameworkInfo
from core.analyzers.framework import EXCLUDE_DIRS, analyze_project
from core.analyzers.snapshot import take_snapshot, Snapshot, commit_snapshot_manifest

# 测试用例持久化到项目 `.autotest/` 目录，可直接被项目引用
AUTOTEST_DIR = ".autotest"
# 默认配置
DEFAULT_CONFIG = {
    "project": {
        "name": "",
        "type": "auto",  # auto | frontend | backend | miniprogram
        "test_frameworks": [],  # 自动检测测试框架
    },
    "test_types": {
        "unit": {"enabled": True, "priority": 1}, # 单元测试
        "integration": {"enabled": True, "priority": 2}, # 集成测试
        "e2e": {"enabled": False, "priority": 3}, # 端到端测试
        "edge": {"enabled": False, "priority": 4}, # 边界测试
        "accessibility": {"enabled": False, "priority": 5}, # 可访问性测试
        "visual": {"enabled": False, "priority": 6}, # 视觉回归测试
        "mock": {"enabled": False, "priority": 7}, # mock测试
        "performance": {"enabled": False, "priority": 8}, # 性能基线测试
        "mutation": {"enabled": False, "priority": 9}, # 变异测试
    },
    "execution": {
        "auto_run": True,
        "timeout_seconds": 120,
        "parallel": False,
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4o",
    },
    "watch": {
        "enabled": False,
        "patterns": ["**/*.py", "**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx"],
    },
}


def create_autotest_structure(target_path: str) -> dict:
    """创建 .autotest/ 目录结构，返回创建路径的列表"""

    # 在创建目录前先检查权限
    if not os.access(target_path, os.W_OK):
        click.echo(f"✗ 没有写权限：{target_path}")
        raise SystemExit(1)

    autotest_path = os.path.join(target_path, AUTOTEST_DIR)
    created_paths = []

    # 创建主目录【exist_ok=True 表示目录已存在时，静默跳过，不抛异常】
    os.makedirs(autotest_path, exist_ok=True)
    created_paths.append(autotest_path)

    # 创建 test_cases 子目录
    test_cases_path = os.path.join(autotest_path, "test_cases")
    os.makedirs(test_cases_path, exist_ok=True)
    created_paths.append(test_cases_path)

    # 创建 test_cases 下的分类子目录
    for sub_dir in ["unit", "integration", "e2e", "edge", "accessibility", "visual", "mock", "performance", "mutation"]:
        sub_path = os.path.join(test_cases_path, sub_dir)
        os.makedirs(sub_path, exist_ok=True)
        created_paths.append(sub_path)

    return {
        "autotest_path": autotest_path,
        "created_paths": created_paths,
    }

def write_snapshot_manifest(autotest_path: str, snapshots: list[Snapshot]) -> str:
    """将带版本的文件快照写入 snapshot.json"""
    snapshots_path = os.path.join(autotest_path, "snapshot.json")
    return commit_snapshot_manifest(
        snapshots_path,
        snapshots,
    )

def write_config(autotest_path: str, project_name: str, project_config: FrameworkInfo, mode: str) -> str:
    """生成并写入 config.yml，返回配置文件路径"""
    config = deepcopy(DEFAULT_CONFIG) # 深拷贝
    config["project"]["name"] = project_name
    config["project"].update(project_config.to_config())

    # 识别目标项目是否为新项目
    if mode == "bootstrap":
        config["execution"]["auto_run"] = False

    config_path = os.path.join(autotest_path, "config.yml")

    """
    把 Python 字典 config 序列化成 YAML 格式，写入文件 f
    default_flow_style 控制 YAML 的输出格式， True 类似 JSON 单行； False 块式风格
    """
    with open(config_path, "w", encoding="utf-8") as f:
        # yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        # safe_dump 能防止写出 Python 专属对象标签，让配置保持跨语言可读
        yaml.safe_dump(
            config,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    return config_path


def _autotest_backup_prefix(
    target_path: str,
) -> str:
    """返回目标项目专属的备份目录前缀"""

    normalized_target = os.path.abspath(target_path)
    target_name = os.path.basename(normalized_target)

    if not target_name:
        raise ValueError(
            "目标项目名称不能为空"
        )

    return (
        f".{target_name}-autotest-backup-"
    )

def backup_existing_autotest(target_path: str) -> str | None:
    """复制已有 .autotest 返回受控备份目录"""

    autotest_path = os.path.join(target_path, AUTOTEST_DIR)

    # .exists(path) 遇到损坏的符号链接时会返回 False
    # .lexists(path) 只要路径实体存在，即使它是损坏的符号链接也返回 True
    # 处理即将备份或删除的路径时，lexists() 更安全，避免把损坏链接误认为路径不存在
    if not os.path.lexists(autotest_path):
        return None

    # 拒绝 .autotest 符号链接
    # 假设 project/.autotest -> /另一个重要目录。 如果继续执行备份、覆盖或清理，边界会变的不清晰。
    # 因此这里直接拒绝，不跟随链接
    if os.path.islink(autotest_path):
        raise ValueError(
            ".autotest 不能是符号链接"
        )

    if not os.path.isdir(autotest_path):
        raise ValueError(
            ".autotest 必须是目录"
        )

    # 假如目标路径是 /User/work/demo，备份会类似 /User/work/.demo-autotest-backup-x7K92
    # 这样既不会被项目扫描，又通常位于同一个文件系统，可以继续使用 os.replace 恢复
    normalized_target = os.path.abspath(
        target_path
    )
    target_parent = os.path.dirname(
        normalized_target
    )
    backup_prefix = (
        _autotest_backup_prefix(
            normalized_target
        )
    )

    backup_root = tempfile.mkdtemp(
        prefix=backup_prefix,
        dir=target_parent,
    )
    backup_path = os.path.join(backup_root, AUTOTEST_DIR)

    try:
        # 如果 .autotest 内部包含符号链接，将链接本身复制到备份，不读取链接目标
        # 这可以避免备份过程越界读取
        shutil.copytree(autotest_path, backup_path, symlinks=True)
    except Exception:
        shutil.rmtree(backup_root, ignore_errors=True)
        raise

    return backup_root

def _resolve_controlled_backup(
    target_path: str,
    backup_root: str,
) -> tuple[str, str]:
    """验证项目专属备份路径并返回规范化路径"""

    normalized_target = os.path.abspath(target_path)
    normalized_backup = os.path.abspath(backup_root)

    target_parent = os.path.dirname(normalized_target)
    expected_prefix = (
        _autotest_backup_prefix(
            normalized_target
        )
    )

    backup_parent = os.path.dirname(
        normalized_backup
    )
    backup_name = os.path.basename(
        normalized_backup
    )

    if (
        backup_parent != target_parent
        or not backup_name.startswith(expected_prefix)
    ):
        raise ValueError("备份目录不属于目标项目")

    if (
        not os.path.isdir(normalized_backup)
        or os.path.islink(normalized_backup)
    ):
        raise ValueError("备份目录不存在或不安全")

    return normalized_target, normalized_backup


def restore_autotest_backup(
    target_path: str,
    backup_root: str,
) -> None:
    """删除初始化半成品，并恢复原有 .autotest"""

    normalized_target, normalized_backup = (
        _resolve_controlled_backup(
            target_path,
            backup_root,
        )
    )

    backup_path = os.path.join(normalized_backup, AUTOTEST_DIR)
    autotest_path = os.path.join(normalized_target, AUTOTEST_DIR)

    # 3. 验证备份中的 .autotest 是真实目录
    if (
        not os.path.isdir(backup_path)
        or os.path.islink(backup_path)
    ):
        raise ValueError(
            ".autotest 备份不存在或不安全"
        )

    if os.path.lexists(autotest_path):
        if (
            not os.path.isdir(autotest_path)
            or os.path.islink(autotest_path)
        ):
            raise ValueError(
                "初始化后的 .autotest 路径不安全"
            )

        # 删除初始化到一半的 .autotest
        shutil.rmtree(autotest_path)

    # 5. 将备份原子移动回 project/.autotest
    os.replace(backup_path, autotest_path)
    # 6. 删除空的备份容器
    os.rmdir(normalized_backup)


def discard_autotest_backup(
    target_path: str,
    backup_root: str,
) -> None:
    """
    初始化成功后删除受控备份目录 .autotest

    删除前必须验证：
    备份目录的父目录 == 目标项目的父目录
    备份目录名称以 .autotest-backup- 开头
    备份目录是普通目录
    备份目录不是符号链接
    """

    _, normalized_backup = (
        _resolve_controlled_backup(
            target_path,
            backup_root,
        )
    )

    shutil.rmtree(normalized_backup)


def cleanup_autotest(target_path: str):
    """当初始化失败时清空autotest目录"""
    autotest_path = os.path.join(target_path, ".autotest")
    if os.path.exists(autotest_path):
        shutil.rmtree(autotest_path)


"""
bootstrap -- 新项目，做的事：
- 安装测试框架依赖
- 生成测试框架配置文件
- 创建空的测试模板文件
- 可能追加 npm test 等脚本到 package.json
- 适合：刚用脚手架创建的项目，还没写过测试

auto （默认） -- 已有项目
目标项目已经在迭代中，有代码、可能有部分测试、已有测试框架
做的事：
- 保持现有测试不变，只补充缺失的
- 扫描现有覆盖率，识别缺口
- 用文件快照做变更检测
- 适合：已经在开发的项目，想要补测试

"""
@click.command()
@click.option("--path", default=".", help="目标项目路径")
@click.option("--name", default=None, help="项目名称（默认使用目录名）")
@click.option(
    "--mode",
    type=click.Choice(["auto", "bootstrap"]), # 这两个模式对应的是初始化时目标项目的不同状态，bootstrap -- 新项目
    default="auto",
    help="初始化模式：auto（已有项目）/ bootstrap（新项目）",
)
def init(path, name, mode):
    """
    初始化绑定项目——在目标项目中创建 .autotest/ 工作区

    初始化前不存在 .autotest
    → backup_root = None
    → 初始化成功：保留新目录
    → 初始化失败：删除新目录

    初始化前存在 .autotest
    → 用户拒绝：不备份、不修改
    → 用户确认：建立完整备份
    → 初始化成功：删除备份
    → 初始化失败：删除半成品并恢复备份

    原 .autotest 不安全或备份失败
    → 不开始写入
    → 不删除原目录
    """

    # 解析目标路径
    # os.path.abspath(path) 把相对路径转换成绝对路径
    target_path = os.path.abspath(path)

    # 初始化开始前是否有用户数据
    autotest_existed = False
    # 原有数据是否已经成功备份
    backup_root: str | None = None

    try:
        # 如果目标路径不是一个目录
        if not os.path.isdir(target_path):
            click.echo(f"✗ 路径不存在：{target_path}")
            raise SystemExit(1)

        # 确认是否已有 .autotest/
        autotest_existing = os.path.join(target_path, AUTOTEST_DIR)
        autotest_existed = os.path.lexists(autotest_existing)
        if autotest_existed:
            click.echo(f"→ 检测到已存在的 .autotest/ 目录")
            click.echo(f"  路径：{autotest_existing}")
            if not click.confirm("  是否覆盖？"):
                click.echo("✗ 已取消")
                raise SystemExit(0)

        backup_root = backup_existing_autotest(target_path)

        # 确定项目名称
        project_name = name if name else os.path.basename(target_path)
        click.echo(f"\n🔧 初始化 test-assistant 项目")
        click.echo(f"  目标路径：{target_path}")
        click.echo(f"  项目名称：{project_name}")
        click.echo(f"  初始化模式：{mode}")

        # 创建目录结构
        click.echo(f"\n📁 创建 .autotest/ 目录结构...")
        result = create_autotest_structure(target_path)
        for p in result["created_paths"]:
            click.echo(f"  ✓ 创建：{os.path.relpath(p, target_path)}")

        # 识别项目
        try:
            project_config, project_info = analyze_project(target_path)
            click.echo(project_info)
        except Exception as e:
            click.echo(f"⚠ 框架检测失败: {e}, 已降级为 unknown")
            project_config = FrameworkInfo()
            project_info = "框架检测： unknown（检测失败）"

        # 写入配置
        click.echo(f"\n⚙️  生成配置文件...")
        config_path = write_config(result["autotest_path"], project_name, project_config, mode)
        click.echo(f"  ✓ 写入：{os.path.relpath(config_path, target_path)}")

        # 获取文件快照
        snapshots, skipped = take_snapshot(target_path, EXCLUDE_DIRS)
        # 获取要写入的快照文件地址
        snapshot_path = write_snapshot_manifest(
            autotest_path=result["autotest_path"],
            snapshots=snapshots,
        )

        click.echo(f"\n✅ 写入： {os.path.relpath(snapshot_path, target_path)}")
        click.echo(f"\n📷 文件快照：{len(snapshots)} 个文件（跳过 {skipped} 个）")

        if backup_root is not None:
            try:
                discard_autotest_backup(target_path, backup_root)
            except Exception as discard_error:
                click.echo(
                    "✗ 初始化已完成，但备份清理失败："
                    f"{discard_error}"
                )
                click.echo(
                    f"  备份位置：{backup_root}"
                )
                # 不会被 except Exception 捕获
                raise SystemExit(1)

            backup_root = None

        click.echo(f"\n✅ 项目已绑定：{project_name}")
        click.echo(f"  .autotest/ → {result['autotest_path']}")

    except Exception as error:
        click.echo(f"✗ 初始化失败：{error}")

        try:
            # 原工作区已成功备份 --> 删除半初始化目录并恢复原工作区
            if backup_root is not None:
                restore_autotest_backup(target_path, backup_root)
                backup_root = None
            # 初始化前没有工作区 --> 删除本次创建的 .autotest
            elif not autotest_existed:
                cleanup_autotest(target_path)
        except Exception as rollback_error:
            click.echo(
                "✗ .autotest 回滚失败："
                f"{rollback_error}"
            )

        raise SystemExit(1)
