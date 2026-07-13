import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field

from core.llm import LLMClient

# 读取 .env 到环境变量
load_dotenv()

def demo_prompt():
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
    )

    prompt = PromptTemplate.from_template("用 {language} 写一个 {function_name} 函数")

    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"language": "python", "function_name": "冒泡排序"})
    print(result)

def test_llm_client():
    client = LLMClient()
    print(client.invoke("你好"))
    print(client.invoke_template("用{lang}写一个{func}函数", lang="ts", func="防抖"))

class TestConfigSuggestion(BaseModel):
    test_framework: str = Field(description="推荐的测试框架名称")
    reason: str = Field(description="推荐理由")
    setup_commands: list[str] = Field(description="安装命令列表")
    config_files: list[str] = Field(description="需要创建的配置文件列表")
    confidence: float = Field(description="置信度 0-1")


def test_llm_client_with_structure():
    client = LLMClient(
        pydantic_model=TestConfigSuggestion
    )
    result = client.invoke_template(
        "分析项目文件，推荐测试框架。\n {format_instructions}\n项目文件列表：{files}",
        files=['package.json', 'src/index.tsx'],
    )
    print(result)
    print(type(result))

if __name__ == "__main__":
    # demo_prompt()
    # test_llm_client()
    test_llm_client_with_structure()