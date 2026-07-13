import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

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

if __name__ == "__main__":
    # demo_prompt()
    test_llm_client()