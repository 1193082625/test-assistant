import json
import os

import click
from core.llm.client import LLMClient

from pydantic import BaseModel, Field

class TestConfigSuggestion(BaseModel):
    test_framework: str = Field(description="推荐的测试框架名称")
    reason: str = Field(description="推荐理由")
    setup_commands: list[str] = Field(description="安装命令列表")
    config_files: list[str] = Field(description="需要创建的配置文件列表")
    confidence: float = Field(description="置信度 0-1")

def generate_test_plan(snapshots_files: list[str], target_path: str="") -> TestConfigSuggestion | None:
    try:
        client = LLMClient(pydantic_model=TestConfigSuggestion)
        result = client.invoke_template(
            "分析项目文件，推荐测试框架。\n {format_instructions}\n项目文件列表：{files}",
            files=snapshots_files
        )

        if not target_path:
            cwd = os.getcwd()
            test_plan_path = os.path.join(cwd, ".autotest", "test_plan.json")
        else:
            test_plan_path = os.path.join(target_path, ".autotest", "test_plan.json")

        with open(test_plan_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
        
        return result
    except Exception as e:
        click.echo(f"解析测试方案失败 {e}")
        raise SystemExit(1)

@click.command()
def plan() -> None:
    """查看/编辑测试方案"""
    # 读 .autotest/snapshot.json，提取文件列表
    try:
        cwd = os.getcwd()
        snapshots_path = os.path.join(cwd, ".autotest", "snapshot.json")
        with open(snapshots_path, "r") as f:
            snapshots = json.load(f)
            snapshots_files = [s["path"] for s in snapshots]
            result = generate_test_plan(snapshots_files)
            return result
    except Exception as e:
        click.echo(f"生成解析方案失败 {e}")