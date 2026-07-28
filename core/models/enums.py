"""项目分析使用的稳定机器枚举"""

from enum import StrEnum

class ProjectType(StrEnum):
    """项目在整体架构中的主要用途"""

    FRONTEND = "frontend"
    BACKEND = "backend"
    MINIPROGRAM = "miniprogram"
    # 同时包含多个不同类型的项目模块
    MIXED = "mixed"
    # 证据不足或项目检测失败
    UNKNOWN = "unknown"


class Language(StrEnum):
    """项目源码使用的编程语言"""
    PYTHON = "python"
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    # 未检测到语言，或当前无法识别
    UNKNOWN = "unknown"

class TestFramework(StrEnum):
    """项目使用的测试框架或测试运行器"""
    PYTEST = "pytest"
    VITEST = "vitest"
    JEST = "jest"
    PLAYWRIGHT = "playwright"
    CYPRESS = "cypress"
    MOCHA = "mocha"
    AVA = "ava"
    WEBDRIVERIO = "webdriverio"

class SymbolKind(StrEnum):
    """Python 源码符号的结构类型"""
    CLASS = "class"
    # 定义在模块顶层或其他函数内部的函数
    FUNCTION = "function"
    # 定义在类中的函数
    METHOD = "method"

class TestabilityStatus(StrEnum):
    """源码符号作为测试目标时的可测性结论"""

    # 可以通过稳定模块路径直接导入并测试
    DIRECT="direct"
    # 可以测试，但需要隔离文件系统、子进程等副作用
    NEEDS_ISOLATION="needs_isolation"
    # 不能作为直接测试入口，例如类、私有函数或嵌套函数
    NOT_DIRECT="not_direct"

class EvidenceKind(StrEnum):
    """契约证据的来源类型"""

    # 源码中的文档字符串
    DOCSTRING="docstring"

    # 参数或返回值类型标注
    TYPE_HINT="type_hint"

    # OpenAPI、JSON、Schema 等结构化契约
    SCHEMA="schema"

    # 已有测试对当前行为的约束
    EXISTING_TEST="existing_test"

    # 从当前实现行为提取的回归依据，不代表外部业务契约。
    CURRENT_IMPLEMENTATION = "current_implementation"

class EvidenceStrength(StrEnum):
    """契约证据能够支持测试预期的可信程度"""
    # 明确结构化契约或已有测试，可作为强约束
    STRONG="strong"

    # docstring、类型提示等开发者提供的意图证据
    MEDIUM="medium"

    # 缺少外部契约，主要来自当前实现或模型推断
    WEAK="weak"

class TestSelectionMode(StrEnum):
    """影响分析选择已有测试时采用的范围"""

    # 找到直接关联测试，或测试文件本身发生变化
    DIRECT="direct"
    # 预留的模块级降级模式，目前还不是主要路径
    MODULE="module"
    # 无法安全做精准分析，执行全部正式 pytest 文件
    FULL="full"
    # 没有需要执行的测试
    NONE="none"
    # 当前语言不支持符号分析
    UNSUPPORTED="unsupported"

class TestSpecStatus(StrEnum):
    """
    TestSpec 的人工评审状态

    TestSpec 是”准备生成什么测试“的结构化计划
    状态决定它是否允许进入后续测试生成流程
    """
    # 初试状态：等待人工检查，不能进入生成器
    PROPOSED="proposed"
    # 已批准：允许进入候选测试生成流程
    APPROVED="approved"
    # 已拒绝：不能进入生成器，但仍应保留拒绝记录
    REJECTED="rejected"
