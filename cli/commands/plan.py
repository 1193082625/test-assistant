import json
import os

import click
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from core.llm.client import LLMClient

from pydantic import BaseModel, Field

class TestConfigSuggestion(BaseModel):
    test_framework: str = Field(description="推荐的测试框架名称")
    reason: str = Field(description="推荐理由")
    setup_commands: list[str] = Field(description="安装命令列表")
    config_files: list[str] = Field(description="需要创建的配置文件列表")
    confidence: float = Field(description="置信度 0-1")

class TestPlan(BaseModel):
    suggestion: TestConfigSuggestion
    analysis: str

def generate_test_plan(snapshots_files: list[str], target_path: str="") -> TestPlan | None:
    try:
        client = LLMClient(pydantic_model=TestConfigSuggestion)
        suggestion_chain = (
            PromptTemplate.from_template("分析项目文件，推荐测试框架。\n {format_instructions}\n项目文件列表：{files}")
            | client.chain
        )
        client.add_chain("suggestion", suggestion_chain)
        prompt2 = PromptTemplate.from_template("根据项目内容生成测试策略分析")
        analysis_chain = (prompt2 | client.llm | StrOutputParser())
        client.add_chain("analysis", analysis_chain)
        result = client.invoke_parallel_chain({
            "files": snapshots_files,
            "format_instructions": client.parser.get_format_instructions(),
        })

        if not target_path:
            cwd = os.getcwd()
            test_plan_path = os.path.join(cwd, ".autotest", "test_plan.json")
        else:
            test_plan_path = os.path.join(target_path, ".autotest", "test_plan.json")

        plan_data = {
            "suggestion": result["suggestion"].model_dump(),
            "analysis": result["analysis"],
        }
        with open(test_plan_path, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=2)
        
        return TestPlan(
            suggestion=result["suggestion"],
            analysis=result["analysis"],
        )
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