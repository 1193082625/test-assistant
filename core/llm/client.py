import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

class LLMClient:
    """返回 LLMClient"""
    def __init__(self, model="deepseek-chat", temperature=0):
        llm = ChatOpenAI(
            model=model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
            temperature=temperature,
        )
        self.chain = llm | StrOutputParser()

    def invoke(self, prompt) -> str:
        result = self.chain.invoke(prompt)
        return result

    def invoke_template(self, template, **kwargs) -> str:
        prompt = PromptTemplate.from_template(template)
        result = (prompt | self.chain).invoke(kwargs)
        return result