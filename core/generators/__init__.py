"""从已批准 TestSpec 生成候选代码"""
from .test_spec import (
    GeneratorLLM,
    generate_test_candidate,
)

__all__ = [
    "GeneratorLLM",
    "generate_test_candidate",
]