import os
import click
import yaml
import json

from core.analyzers.framework import EXCLUDE_DIRS, analyze_project, FrameworkInfo
from core.analyzers.snapshot import take_snapshot

# 测试用例持久化到项目 `.autotest/` 目录，可直接被项目引用
AUTOTEST_DIR = ".autotest"
# 默认配置
DEFAULT_CONFIG = {
    "project": {
        "name": "",
        "type": "auto",  # auto | frontend | backend | miniprogram
        "test_framework": "auto",  # 自动检测测试框架
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


def write_config(autotest_path: str, project_name: str, project_config: FrameworkInfo, mode: str) -> str:
    """生成并写入 config.yml，返回配置文件路径"""
    config = DEFAULT_CONFIG.copy()
    config["project"]["name"] = project_name
    config["project"]["type"] = project_config.project_type
    config["project"]["language"] = project_config.language
    config["project"]["frameworks"] = project_config.frameworks
    config["project"]["test_framework"] = project_config.test_framework
    config["project"]["build_tools"] = project_config.build_tools
    config["project"]["has_dockerfile"] = project_config.has_dockerfile
    config["project"]["has_ci_config"] = project_config.has_ci_config


    # 识别目标项目是否为新项目
    if mode == "bootstrap":
        config["execution"]["auto_run"] = False

    config_path = os.path.join(autotest_path, "config.yml")

    """
    把 Python 字典 config 序列化成 YAML 格式，写入文件 f
    default_flow_style 控制 YAML 的输出格式， True 类似 JSON 单行； False 块式风格
    """
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return config_path

def cleanup_autotest(target_path: str):
    """当初始化失败时清空autotest目录"""
    import shutil
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
    """初始化绑定项目——在目标项目中创建 .autotest/ 工作区"""

    # 解析目标路径
    # os.path.abspath(path) 把相对路径转换成绝对路径
    target_path = os.path.abspath(path)

    try:
        # 如果目标路径不是一个目录
        if not os.path.isdir(target_path):
            click.echo(f"✗ 路径不存在：{target_path}")
            raise SystemExit(1)

        # 确认是否已有 .autotest/
        autotest_existing = os.path.join(target_path, AUTOTEST_DIR)
        if os.path.exists(autotest_existing):
            click.echo(f"→ 检测到已存在的 .autotest/ 目录")
            click.echo(f"  路径：{autotest_existing}")
            if not click.confirm("  是否覆盖？"):
                click.echo("✗ 已取消")
                raise SystemExit(0)

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
            project_config = FrameworkInfo(project_type="unknown")
            project_info = "框架检测： unknown（检测失败）"

        # 写入配置
        click.echo(f"\n⚙️  生成配置文件...")
        config_path = write_config(result["autotest_path"], project_name, project_config, mode)
        click.echo(f"  ✓ 写入：{os.path.relpath(config_path, target_path)}")

        # 获取文件快照
        snapshots, skipped = take_snapshot(target_path, EXCLUDE_DIRS)
        # 获取要写入的快照文件地址
        snapshot_path = os.path.join(result["autotest_path"], "snapshot.json")
        # 写入文件
        with open(snapshot_path, 'w', encoding="utf-8") as f:
            """
            把 Python 对象 -> JSON 字符串 -> 写入文件
            这里的 s.__dict__ 是 @dataclass 自动生成的，能把对象转为字典
            __dict__ 是 Python 每个对象都有的属性，存的是实例的所有字段（Snapshot对象） -> 字典
            f 文件对象，序列化结果直接写入文件
            indent=2 JSON 输出缩进2个空格，美化可读性
            default=str 遇到 JSON 不认识的对象时，调用 str() 转成字符串
            """
            json.dump([s.__dict__ for s in snapshots], f, indent=2, default=str)
        
        click.echo(f"\n✅ 写入： {os.path.relpath(snapshot_path, target_path)}")
        click.echo(f"\n📷 文件快照：{len(snapshots)} 个文件（跳过 {skipped} 个）")
        

        click.echo(f"\n✅ 项目已绑定：{project_name}")
        click.echo(f"  .autotest/ → {result['autotest_path']}")
    except Exception as e:
        click.echo(f"✗ 初始化失败：{e}")
        cleanup_autotest(target_path)
        raise SystemExit(1)
