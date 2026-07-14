import os

from dotenv import load_dotenv
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser
from collections.abc import Generator

load_dotenv()

class LLMClient:
    """返回 LLMClient"""
    def __init__(self, model="deepseek-chat", pydantic_model=None, temperature=0):
        self.llm = ChatOpenAI(
            model=model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
            temperature=temperature,
        )
        self.chain_list = {}
        if not pydantic_model:
            self.chain = self.llm | StrOutputParser()
            self.parser = None
        else:
            self.parser = PydanticOutputParser(pydantic_object=pydantic_model)
            self.chain = self.llm | self.parser

    def add_chain(self, chain_name: str, chain):
        self.chain_list[chain_name] = chain

    def invoke(self, prompt) -> str:
        result = self.chain.invoke(prompt)
        return result

    def set_format_instruction(self, kwargs: dict) -> dict:
        if self.parser and "format_instructions" not in kwargs:
            # get_format_instruction 是 PydanticOutputParser的一个方法，作用是：根据定义的pydantic模型，自动生成一段 LLM 能理解的格式指令
            kwargs["format_instructions"] = self.parser.get_format_instructions() # 自动注入
        return kwargs

    def invoke_template(self, template, **kwargs) -> str:
        new_kwargs = self.set_format_instruction(kwargs)
        prompt = PromptTemplate.from_template(template)
        result = (prompt | self.chain).invoke(new_kwargs)
        return result

    def invoke_stream(self, prompt) -> Generator[str, None, None]:
        """
        流式调用chain
        仅 StrOutputParser 有效
        """
        result = self.chain.stream(prompt)
        for chunk in result:
            yield chunk

    def invoke_stream_template(self, template, **kwargs) -> Generator[str, None, None]:
        new_kwargs = self.set_format_instruction(kwargs)
        format_prompt = PromptTemplate.from_template(template)
        result = (format_prompt | self.chain).stream(new_kwargs)
        for chunk in result:
            yield chunk

    def invoke_parallel_chain(self, input_data: dict):
        """通过 template 调用 chain 链 并行"""
        parallel_chain = RunnableParallel(**self.chain_list)
        result = parallel_chain.invoke(input_data)
        return result

    def invoke_pass_through_chain(self, input_prompt: dict):
        passthrough_chain = RunnablePassthrough.assign(**self.chain_list)
        result = passthrough_chain.invoke(input_prompt)
        return result
