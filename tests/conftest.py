import os

# 测试必须完全离线，且需在测试模块导入前关闭追踪
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"