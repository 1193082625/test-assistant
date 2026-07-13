import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser

load_dotenv()

class LLMClient:
    """返回 LLMClient"""
    def __init__(self, model="deepseek-chat", pydantic_model=None, temperature=0):
        llm = ChatOpenAI(
            model=model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
            temperature=temperature,
        )
        if not pydantic_model:
            self.chain = llm | StrOutputParser()
            self.parser = None
        else:
            self.parser = PydanticOutputParser(pydantic_object=pydantic_model)
            self.chain = llm | self.parser

    def invoke(self, prompt) -> str:
        result = self.chain.invoke(prompt)
        return result

    def invoke_template(self, template, **kwargs) -> str:
        if self.parser and "format_instructions" not in kwargs:
            # get_format_instruction 是 PydanticOutputParser的一个方法，作用是：根据定义的pydantic模型，自动生成一段 LLM 能理解的格式指令
            kwargs["format_instructions"] = self.parser.get_format_instructions() # 自动注入
        prompt = PromptTemplate.from_template(template)
        result = (prompt | self.chain).invoke(kwargs)
        return result