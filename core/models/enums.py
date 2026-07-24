"""项目分析使用的稳定机器枚举"""

from enum import StrEnum

class ProjectType(StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    MINIPROGRAM = "miniprogram"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Language(StrEnum):
    PYTHON = "python"
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    UNKNOWN = "unknown"

class TestFramework(StrEnum):
    PYTEST = "pytest"
    VITEST = "vitest"
    JEST = "jest"
    PLAYWRIGHT = "playwright"
    CYPRESS = "cypress"
    MOCHA = "mocha"
    AVA = "ava"
    WEBDRIVERIO = "webdriverio"

class SymbolKind(StrEnum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"