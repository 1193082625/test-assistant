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

langChain 除了 管道链，还有两种很有用的组合方式

- RunnableParallel - 并行执行；场景：同一份输入，同时问 LLM 多个问题
- RunnableSequence - 分步执行；场景：第一步的输出，作为第二部的输入
