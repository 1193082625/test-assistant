"""
薄薄的入口，只负责解析参数、调 core
1. 变更检测
2. 执行受影响测试...
3. 分析完成
4. 输出结果：
     ✓ 变更检测: 3 个文件变更
        - src/user.ts (modified)
        - src/api/user.ts (modified)
        - src/utils/helper.ts (added)
      → 执行受影响测试...
      → 分析完成: X passed, Y failed
"""
import os
import subprocess

import click
import yaml

from core.analyzers.framework import suggest_test_framework
from core.graphs.run_graph import run_graph
from core.utils import find_project_root


@click.command()
@click.option("--path", default=".", help="目标项目路径")
def run(path):
    """增量运行测试"""

    # 获取目标路径
    if path:
        project_path = os.path.abspath(path)
    else:
        project_path = find_project_root()

    if not project_path:
        click.echo("未找到目标路径")
        raise SystemExit(1)

    # 校验 .autotest/ 存在
    target_path = os.path.join(project_path, ".autotest")
    if not os.path.exists(target_path):
        click.echo("项目未初始化 autotest")
        raise SystemExit(1)

    # 校验 config.yml 存在
    config_path = os.path.join(target_path, "config.yml")
    if not os.path.isfile(config_path):
        click.echo("未找到 config.yml")
        raise SystemExit(1)

    """
    校验 test_framework 不为空
    → 读取项目类型（frontend/backend/miniprogram）
    → 检测是否有测试框架
        → 有，跳过当前逻辑，直接执行run_graph
        → 没有，则推荐对应框架（uni-app → vitest）
            → 问用户：是否安装？
            → 是 → npm install -D vitest
            → 否 → 提示"跳过执行"并推出 
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    project_type = config["project"]["type"]
    test_framework = config["project"]["test_framework"]

    if not test_framework:
        recommended = suggest_test_framework(config["project"]["frameworks"])
        if recommended:
            # 问用户
            if click.confirm(f"检测到项目未安装测试框架，推荐安装 {recommended}, 是否安装？"):
                # 执行安装
                if project_type == "frontend":
                    subprocess.run(
                        ["npm", "install", '-D', recommended],
                        cwd=project_path,
                        check=True,
                    )
                elif project_type == "backend":
                    subprocess.run(
                        ['pip', 'install', recommended],
                        cwd=project_path,
                        check=True,
                    )
                # 更新 config.yml
                with open(config_path, "w", encoding="utf-8") as f:
                    config["project"]["test_framework"] = recommended
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            else:
                click.echo("跳过测试执行")
                raise SystemExit(0)
        else:
            click.echo("无法确定推荐的测试框架，跳过执行")
            raise SystemExit(0)


    result = run_graph(project_path)

    # 变更检测输出
    changed_files = result["changed_files"]
    if any(changed_files.values()): # 有任何变更
        count = sum(len(v) for v in changed_files.values())
        click.echo(f"✓ 变更检测： {count} 个文件变更")
        for f in changed_files["added"]:
            click.echo(f"- {f} (added)")
        for f in changed_files["deleted"]:
            click.echo(f"- {f} (deleted)")
        for f in changed_files["modified"]:
            click.echo(f"- {f} (modified)")

    # 执行结果
    test_result = result["test_results_by_file"]
    if test_result:
        click.echo("→ 执行受影响测试...")
        for file_path, results in test_result.items():
            passed = sum(1 for r in results if r.status == "passed")
            failed = sum(1 for r in results if r.status == "failed")
            click.echo(f"  ✓ {file_path} ({passed} passed, {failed} failed)")

    # 汇总
    msg = result["messages"][-1]
    click.echo(f"→ {msg.content}")

