from pydoc import describe

from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
)

# 场景：给一个函数名，同时问两个问题
chain1 = PromptTemplate.from_template("用{language}写一个{function_name}函数，只返回代码") | llm | StrOutputParser()
chain2 = PromptTemplate.from_template("{function_name}函数的作用是什么？用一句话说明") | llm | StrOutputParser()

# RunnableParallel: 两个链并行
parallel_chain = RunnableParallel(
    code = chain1,
    description=chain2,
)

result = parallel_chain.invoke({"language": "Python", "function_name": "冒泡排序"})
print("=== RunnableParallel 结果 ===")
print("代码：", result["code"][:100])
print("说明：", result["description"])

# RunnablePassthrough: 透传+组合
passthrough_chain = RunnablePassthrough.assign(
    description=chain2
)
result2 = passthrough_chain.invoke({"language": "Python", "function_name": "快速排序"})
print("\n=== RunnablePassthrough 结果 ===")
print("输入： ", result2["language"], result2["function_name"])
print("说明： ", result2["description"])