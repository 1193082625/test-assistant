import os
import json
import click
from pydantic import BaseModel, Field

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from core.analyzers.snapshot import read_snapshot_manifest
from core.llm.client import LLMClient

class TestConfigSuggestion(BaseModel):
    test_framework: str = Field(description="推荐的测试框架名称")
    reason: str = Field(description="推荐理由")
    setup_commands: list[str] = Field(description="安装命令列表")
    config_files: list[str] = Field(description="需要创建的配置文件列表")
    confidence: float = Field(description="置信度 0-1")

class TestPlan(BaseModel):
    suggestion: TestConfigSuggestion
    analysis: str


def get_snapshot_files(snapshot_path: str) -> list[str]:
    """从快照清单中取得测试计划需要的文件路径"""
    manifest = read_snapshot_manifest(snapshot_path)

    return [
        snapshot.path
        for snapshot in manifest.files
    ]


def generate_test_plan(snapshots_files: list[str], target_path: str = "") -> TestPlan | None:
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
