## langchain 中 chain LCEL 核心概念

RunnablePassthrough - 透传输入，不修改

- .assign() 方法可以在透传的同时新增 / 覆盖字段
- 常用于：输入中有多个字段，只需要其中一部分传给下一步

RunnableParallel - 并行执行多个链，结果合并为一个dict

- 场景：同一份输入，同时问 LLM 多个结果
- 返回值是 { "key1": result1, "key2": result2 }
