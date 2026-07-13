## 目标： 跑通第一个 LLM 调用链

```python
# 概念1. ChatModel - 模型封装
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o")

# 概念2. PropmptTemplate - 提示此模板
from langchain_core.prompts import PromptTemplate
prompt = PromptTemplate.from_tempplate("用{language}实现一个{function_name}函数")

# 概念3. StrOutputParser - 输出解析
from langchain_core.output_parsers import StrOutputParser
parser = StrOutputParse()

# 三者用 管道 组合成一条链
chain = prompt | llm | parser
result = chain.invoke({"language": "Python", "function_name": "冒泡排序"})
```
