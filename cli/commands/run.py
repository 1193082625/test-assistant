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
import json
import os
import subprocess

import click
import yaml

from core.analyzers.framework import suggest_test_framework, suggest_config_templates
from core.graphs.run_graph import run_graph
from core.utils import find_project_root


def _ensure_smoke_test(project_path: str, project_type: str, test_framework: list[str]):
    """测试目录为空时，生成一个验证测试"""
    test_dir = os.path.join(project_path, ".autotest", "test_cases", "unit")
    existing = [f for f in os.listdir(test_dir) if f.endswith((".test.ts", ".test.js", ".py"))]
    if existing:
        return # 已有测试文件，跳过

    # 判断框架类型（兼容 list 和 str）
    frameworks = test_framework
    if any(fw in ("vitest", "jest") for fw in frameworks):
        file_path = os.path.join(test_dir, "verify.test.ts")
        content = """
        import { describe, it, expect } from "vitest";
        
        describe("smoke test", () => {
            it("1 + 1 = 2", () => {
                expect(1 + 1).toBe(2)
            })
        })
        """
    elif "pytest" in frameworks:
        file_path = os.path.join(test_dir, "test_verify.py")
        content = """
        def test_smoke():
            assert 1 + 1 == 2
        """
    else:
        return # 无法识别的框架，跳过

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.lstrip("\n"))

    click.echo(f"  ✓ 生成 smoke test：{os.path.relpath(file_path, project_path)}")

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
    recommended = suggest_test_framework(config["project"]["frameworks"], project_type)

    # 校验 config 记录的依赖是否真实存在
    test_framework_name = recommended[0] if recommended else None
    if test_framework_name == "vitest":
        project_pkg = os.path.join(project_path, "package.json")
        if test_framework and os.path.exists(project_pkg):
            with open(project_pkg) as f:
                pkg = json.load(f)

            if "test" not in pkg.get("scripts", {}):
                pkg.setdefault("scripts", {})["test"] = "vitest run"
                # pkg.setdefault("scripts", {})["test:coverage"] = "vitest run --coverage"
                with open(project_pkg, "w") as f:
                    json.dump(pkg, f, indent=2)
                click.echo("  ✓ 添加 npm test 脚本")
            elif "test" in pkg.get("scripts", {}) and not (pkg.get("scripts", {}).get("test").startswith("vitest")):
                if click.confirm("当前test 命令行与预期不符，是否修改为 'vitest run'"):
                    pkg.setdefault("scripts", {})["test"] = "vitest run"
                    # pkg.setdefault("scripts", {})["test:coverage"] = "vitest run --coverage"
                    with open(project_pkg, "w") as f:
                        json.dump(pkg, f, indent=2)
                    click.echo("  ✓ 添加 npm test 脚本")

            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if not any(dep in all_deps for dep in test_framework):
                test_framework = []
                config["project"]["test_framework"] = []

    if not test_framework or len(test_framework) == 0:
        if recommended:
            # 问用户
            if click.confirm(f"检测到项目未安装测试框架，推荐安装 {recommended}, 是否安装？"):
                # 执行安装
                if project_type in ("frontend", "miniprogram"):
                    subprocess.run(
                        ["npm", "install", '-D'] + (recommended if isinstance(recommended, list) else [recommended]),
                        cwd=project_path,
                        check=True,
                    )
                elif project_type == "python":
                    subprocess.run(
                        ['pip', 'install'] + (recommended if isinstance(recommended, list) else [recommended]),
                        cwd=project_path,
                        check=True,
                    )

                # 安装依赖后添加打印日志
                config_templates = suggest_config_templates(config["project"]["frameworks"], project_type)
                for filename, content in config_templates.items():
                    config_file_path = os.path.join(project_path, filename)
                    if not os.path.exists(config_file_path):
                        with open(config_file_path, "w", encoding="utf-8") as f:
                            f.write(content.lstrip("\n"))
                        click.echo(f"  ✓ 生成配置文件：{filename}")
                    else:
                        click.echo(f"  - 跳过 {filename}（已存在）")

                # 更新 config.yml
                with open(config_path, "w", encoding="utf-8") as f:
                    config["project"]["test_framework"] = recommended
                    test_framework = config["project"]["test_framework"]
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            else:
                click.echo("跳过测试执行")
                raise SystemExit(0)
        else:
            click.echo("无法确定推荐的测试框架，跳过执行")
            raise SystemExit(0)

    _ensure_smoke_test(project_path, project_type, test_framework)

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

