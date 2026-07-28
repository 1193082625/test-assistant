"""
读取目标项目并判断它是什么项目
函数执行流程：
detect_project_type()
→ ProjectInfo
→ detect_frameworks()
→ detect_test_frameworks()
→ detect_build_tools()
→ FrameworkInfo
→ AnalyzeInfo
"""

from configparser import ConfigParser
import tomllib
import os
import re
from typing import NamedTuple

import xml.etree.ElementTree as ET
import yaml
import json

from core.models import FrameworkInfo, Language, ProjectType, TestFramework, ProjectAnalysis, ProjectModule

from configparser import Error as ConfigParserError

"""
强制每次检测同时回答两个问题：
这是什么形态的项目
主要使用什么语言
"""
class ProjectInfo(NamedTuple):
    """表示一个标志文件产生的中间检测证据，包含初步类型、语言、来源文件、解析器和原始内容"""
    project_type: ProjectType
    language: Language
    source_file: str # 告诉系统当前结论来自哪个文件
    target_analysis: str
    file_content: str

# 定义可解释的检测异常
class ProjectDetectionError(ValueError):
    """项目标志文件无法解析"""
    def __init__(self, source_file: str, reason: str):
        self.source_file = source_file
        self.reason = reason
        super().__init__(f"{source_file} 解析失败： {reason}")


class AnalyzeInfo(NamedTuple):
    project_config: FrameworkInfo
    project_info: str

EXCLUDE_DIRS = [
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    ".autotest",
    ".history",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
]

# 检测项目用了什么
FRAMEWORK_DICT = {
    "react": "React",
    "vue": "Vue",
    "svelte": "Svelte",
    "@angular/core": "Angular",
    "@dcloudio/uni-app": "uni-app",
    "solid-js": "Solid",
    "preact": "Preact",
    "@remix-run/react": "Remix",
    "lit": "Lit",
    "@sveltejs/kit":"SvelteKit",
    "express": "Express",
    "fastify": "Fastify",
    "next": "Next",
    "nuxt": "Nuxt",
    "@nestjs/core": "NestJS",
    "koa": "Koa",
    "hono": "Hono",

    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "tornado": "Tornado",
    "sanic": "Sanic",
    "bottle": "Bottle",
    "aiohttp": "AIOHTTP",
}
# 检测用什么测试框架
TEST_FRAMEWORK_DICT = {
    "vitest": TestFramework.VITEST,
    "jest": TestFramework.JEST,
    "cypress": TestFramework.CYPRESS,
    "mocha": TestFramework.MOCHA,
    "ava": TestFramework.AVA,
    "@wdio/cli": TestFramework.WEBDRIVERIO,
    "playwright": TestFramework.PLAYWRIGHT,
    "@playwright/test": TestFramework.PLAYWRIGHT,
    "pytest": TestFramework.PYTEST,
}
# 根据项目推荐安装测试框架
FRAMEWORK_TEST_MAP = {
    # 前端
    "uni-app": ["vitest", "@vue/test-utils", "happy-dom"],
    "vue": ["vitest", "@vue/test-utils", "happy-dom"],
    "react": ["vitest", "@testing-library/react", "happy-dom", "@testing-library/jest-dom"],
    "Svelte": ["vitest", "happy-dom"],
    "Solid": ["vitest", "solid-testing-library"],
    "NestJS": ["jest"],
    # Python
    "python": ["pytest"],
    "Django": ["pytest"],
    "Fastapi": ["pytest"],
    "Flask": ["pytest"]
}
# 框架 需要生成的配置文件模板
FRAMEWORK_CONFIG_TEMPLATES = {
    "uni-app": {
        "vitest.config.ts": """
        import { defineConfig } from 'vitest/config'
        
        export default defineConfig({
          plugins: [],
          test: {
            environment: 'happy-dom',
            globals: true,
          },
        })
        """,
    },
    "python": {
        "pytest.ini": """
        [pytest]
        testpaths = .autotest/test_cases
        python_files = test_*.py *_test.py
        """
    }
}

BUILD_TOOL_DICT = {
    "vite": "vite",
    "webpack": "Webpack",
    "rollup": "Rollup",
    "esbuild": "ESBuild",
    "typescript": "TypeScript",
    "tsc": "TypeScript",
    "swc": "SWC",
    "turbo": "Turbopack",
    "parcel": "Parcel",
    "gulp": "Gulp",
    "postcss": "PostCSS",
    "babel": "Babel",
}

MINIPROGRAM_PACKAGES = {
    "@dcloudio/uni-app",
    "@dcloudio/uni-mp-weixin",
}

FRONTEND_PACKAGES = {
    "react",
    "vue",
    "svelte",
    "@angular/core",
    "solid-js",
    "preact",
    "@remix-run/react",
    "next",
    "nuxt",
    "lit",
    "@sveltejs/kit"
}
BACKEND_PACKAGES = {
    "express",
    "fastify",
    "@nestjs/core",
    "koa",
    "hono",
    "@hono/node-server",
}

# 定义允许降级的解析异常
PARSER_ERRORS = (
    json.JSONDecodeError,
    tomllib.TOMLDecodeError,
    ET.ParseError,
    ConfigParserError,
    yaml.YAMLError,
)

def read_file(path: str):
    with open(path, 'r', encoding="utf-8") as data:
        return data.read() # 返回文件内容

def detect_project_type(files: list[str], root: str) -> ProjectInfo | None:
    """查找项目标志性文件，判断项目类型"""
    file_names = set(files)
    if "pages.json" in file_names or "manifest.json" in file_names:
        """
        有 package.json 时优先保存它的内容，后续框架检测需要从 dependencies 中识别，如果保存的是空的 pages.json，会丢失依赖证据
        """
        if "package.json" in file_names:
            content = read_file(os.path.join(root, "package.json"))
            source_file = "package.json"
        else:
            marker = ("pages.json" if "pages.json" in file_names else "manifest.json")
            content = read_file(os.path.join(root, marker))
            source_file = marker
        return ProjectInfo(
            project_type=ProjectType.MINIPROGRAM,
            language=Language.JAVASCRIPT,
            source_file=source_file,
            target_analysis="json",
            file_content=content
        )

    if "pyproject.toml" in file_names:
        content = read_file(os.path.join(root, "pyproject.toml"))
        return ProjectInfo(
            project_type=ProjectType.BACKEND,
            language=Language.PYTHON,
            source_file="pyproject.toml",
            target_analysis="tomllib",
            file_content=content
        )
    if "pytest.ini" in file_names or "setup.cfg" in file_names:
        marker = ("setup.cfg" if "setup.cfg" in file_names else "pytest.ini")
        content = read_file(os.path.join(root, marker))
        return ProjectInfo(
            project_type=ProjectType.BACKEND,
            language=Language.PYTHON,
            source_file=marker,
            target_analysis="configparser",
            file_content=content
        )

    if "pom.xml" in file_names:
        content = read_file(os.path.join(root, "pom.xml"))
        return ProjectInfo(
            project_type=ProjectType.BACKEND,
            language=Language.JAVA,
            source_file="pom.xml",
            target_analysis="xml.etree.ElementTree",
            file_content=content
        )
    if "build.gradle" in file_names:
        content = read_file(os.path.join(root, "build.gradle"))
        return ProjectInfo(
            project_type=ProjectType.BACKEND,
            language=Language.JAVA,
            source_file="build.gradle",
            target_analysis="build.gradle",
            file_content=content
        )
    if "go.mod" in file_names:
        content = read_file(os.path.join(root, "go.mod"))
        return ProjectInfo(
            project_type=ProjectType.BACKEND,
            language=Language.GO,
            source_file="go.mod",
            target_analysis="go",
            file_content=content
        )

    if "package.json" in file_names:
        """这里采用明确优先级 小程序>Node 后端 > 前端 > 未知"""
        content = read_file(os.path.join(root, "package.json"))
        dependencies = parse_package_dependencies(content)

        if dependencies & MINIPROGRAM_PACKAGES:
            project_type = ProjectType.MINIPROGRAM
        elif dependencies & BACKEND_PACKAGES:
            project_type = ProjectType.BACKEND
        elif dependencies & FRONTEND_PACKAGES:
            project_type = ProjectType.FRONTEND
        else:
            project_type = ProjectType.UNKNOWN

        language = (Language.TYPESCRIPT if "typescript" in dependencies else Language.JAVASCRIPT)

        return ProjectInfo(
            project_type=project_type,
            language=language,
            source_file="package.json",
            target_analysis="json",
            file_content=content
        )

    return None


def analysis_go(content: str) -> dict:
    """简单的 go.mod 解析器 -- 提取依赖列表"""
    deps = {}
    in_block = False
    for line in content.splitlines():
        line = line.strip() # 去掉开头和结尾的空白字符（空格、制表符、换行符等）
        if line == "require (" or line == "require(":
            in_block = True
        elif line == ")":
            in_block = False
        elif in_block and line:
            # "github.com/gin-gonic/gin v1.9.1" --> 获取路径的最后一段
            parts = line.split() # 先按空白拆成 ["github.com/gin-gonic/gin", "v1.9.1"]
            if len(parts) >= 2:
                name = parts[0].split("/")[-1] # 再按 / 拆， 取最后一段 "gin"
                deps[name] = parts[0]
    
    return deps

def detect_result_list(project_info: ProjectInfo, origin_dict: dict) -> list:
    """固定优先级为： 小程序 > Python > Java > Go > package.json"""
    result = []
    package_json_content = project_info.file_content
    target_analysis = project_info.target_analysis
    all_deps = {}
    if target_analysis == "json": # 解析 JSON 文件
        data = json.loads(package_json_content) # 解析 json
        all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    elif target_analysis == "tomllib": # 解析 pyproject.toml 文件
        data = tomllib.loads(package_json_content) # 解析 YAML -- Python 字典
        # 【project】 下的 dependencies 是列表
        deps_list = data.get("project", {}).get("dependencies", [])
        if isinstance(deps_list, list):
            for dep in deps_list:
                # "fastapi>=0.100.0" -> "fastapi"
                name = dep.split(">")[0].split("<")[0].split("=")[0].split("!")[0].strip()
                all_deps[name] = name
    elif target_analysis == "configparser": # 解析 pytext.ini \ setup.cfg
        # 先创建对象，再调用方法，最后检查对象
        config = ConfigParser()
        config.read_string(package_json_content) # 读取到 config 内部
        data = config if config.sections() else {}
        # 等价于下面的代码
        # data = {} # 给空字典兜底
        # if config.sections: # 有 section 说明解析成功
        #     data = config # 直接用 config 对象
    elif target_analysis == "xml.etree.ElementTree": # 解析 pom.xml
        # 去掉 xmlns 命名空间，否则 find/findall 找不到元素
        content_no_ns = re.sub(r'\sxmlns="[^"]+"', '', package_json_content, count=1)
        # 返回 Element
        root = ET.fromstring(content_no_ns)
        # 查找所有 dependency 下的 artifactId
        deps = {}
        for dep in root.iter("dependency"):
            art = dep.find("artifactId")
            if art is not None and art.text:
                # 命名空间处理 （pom.xml 通常有 xmlns）
                name = art.text
                deps[name] = name
        data = deps

    elif target_analysis == "build.gradle": # 暂时不深入解析
        data = {}
    elif target_analysis == "go": # 解析 go.mod
        data = analysis_go(package_json_content)
    else:
        data = yaml.safe_load(package_json_content) # 解析 YAML -- Python 字典
    
    for label, val in origin_dict.items():
        if label in data or label in all_deps:
            result.append(val)
    
    return result

def detect_frameworks(project_info: ProjectInfo) -> list[str]:
    """解析项目使用了什么框架"""
    return detect_result_list(project_info, FRAMEWORK_DICT)

def parse_package_dependencies(content: str, source_file: str = "package.json") -> set[str]:
    """从 package.json 内容提取生产和开发依赖名称"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        # raise ... from exc 表示 “领域异常是由底层 JSON 异常引起的”，既给用户友好信息，也保留调试因果链
        raise ProjectDetectionError(
            source_file,
            str(exc),
        ) from exc

    if not isinstance(data, dict):
        raise ProjectDetectionError(
            source_file,
            "根节点必须是 JSON 对象"
        )

    dependencies = data.get("dependencies", {})
    dev_dependencies = data.get("devDependencies", {})

    if not isinstance(dependencies, dict):
        raise ProjectDetectionError(
            source_file,
            "dependencies 必须是对象"
        )

    if not isinstance(dev_dependencies, dict):
        raise ProjectDetectionError(
            source_file,
            "devDependencies 必须是对象"
        )

    return set(dependencies) | set(dev_dependencies)

# 增加统一降级函数
def unknown_analysis(
        source_file: str,
        reason: str
) -> AnalyzeInfo:
    return AnalyzeInfo(
        project_config=FrameworkInfo(),
        project_info=(
            f"框架检测：未知（{source_file} 解析失败：{reason}）"
        )
    )

def detect_test_frameworks(project_info: ProjectInfo) -> list[TestFramework]:
    """解析项目使用了什么测试框架"""
    return detect_result_list(project_info, TEST_FRAMEWORK_DICT)


def detect_build_tools(project_info: ProjectInfo) -> list[str]:
    """解析项目使用了什么构建工具"""
    return detect_result_list(project_info, BUILD_TOOL_DICT)

def build_framework_info(project_info: ProjectInfo) -> FrameworkInfo:
    """将一个标志文件的中间证据整理为模块分析结果"""
    return FrameworkInfo(
        project_type=project_info.project_type,
        language=project_info.language,
        frameworks=detect_frameworks(project_info),
        test_frameworks=detect_test_frameworks(project_info),
        build_tools=detect_build_tools(project_info),
        has_dockerfile=False,
        has_ci_config=False,
    )

def analyze_project_modules(target_path: str) -> ProjectAnalysis:
    """扫描目标目录并分析其中所有项目模块"""
    analysis = ProjectAnalysis(root_path=target_path)

    for root, dirs, files in os.walk(target_path):
        # sorted 用于保证遍历子目录的顺序稳定，不受文件系统返回顺序影响
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)

        try:
            project_info = detect_project_type(files, root)
        except ProjectDetectionError as exc:
            analysis.modules.append(
                ProjectModule(
                    root_path=root,
                    source_file=exc.source_file,
                    framework_info=FrameworkInfo()
                )
            )
            relative_path = os.path.relpath(
                os.path.join(root, exc.source_file),
                target_path
            )
            analysis.warnings.append(
                f"{relative_path} 解析失败：{exc.reason}"
            )

            continue

        if project_info is None:
            continue

        try:
            framework_info = build_framework_info(project_info)
        except PARSER_ERRORS as exc:
            framework_info = FrameworkInfo()

            relative_path = os.path.relpath(
                os.path.join(root, project_info.source_file),
                target_path
            )

            analysis.warnings.append(
                f"{relative_path} 解析失败：{exc}"
            )

        module = ProjectModule(
            root_path=root,
            source_file=project_info.source_file,
            framework_info=framework_info,
        )

        analysis.modules.append(module)

    return analysis

def analyze_project(target_path: str) -> AnalyzeInfo:
    """项目检测入口函数"""
    detect_project_result = None
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        try:
            result = detect_project_type(files, root)
        except ProjectDetectionError as exc:
            return unknown_analysis(
                exc.source_file,
                exc.reason
            )

        if result:
            detect_project_result = result
            break # 找到了就退出循环

    if not detect_project_result:
        return AnalyzeInfo(
            project_config=FrameworkInfo(),
            project_info=(
                "框架检测： 未知"
                "（未发现支持的项目标志文件）"
            )
        )

    try:
        config = build_framework_info(detect_project_result)
        if config.project_type is ProjectType.UNKNOWN:
            return AnalyzeInfo(
                project_config=config,
                project_info=(
                    "框架检测：未知"
                    f"（{detect_project_result.source_file} "
                    "未识别到支持的框架依赖）"
                )
            )
    # 不要使用 except Exception , 否则 AttributeError、变量拼写错误等程序缺陷也会被伪装成“配置解析失败”
    except PARSER_ERRORS as exc:
        return unknown_analysis(
            detect_project_result.source_file,
            str(exc),
        )

    return AnalyzeInfo(
        project_config=config,
        project_info=f"框架检测：{' + '.join(config.frameworks)}"
    )

def suggest_test_framework(frameworks: list, language: str = "") -> list[str] | None:
    """根据项目信息推荐测试框架（含额外依赖），返回包名列表 或 None"""
    for framework in frameworks:
        if framework in FRAMEWORK_TEST_MAP:
            return FRAMEWORK_TEST_MAP[framework]
    if language.lower() in FRAMEWORK_TEST_MAP:
        return FRAMEWORK_TEST_MAP[language.lower()]
    return None

def suggest_config_templates(frameworks: list, language: str = "") -> dict[str, str]:
    """根据项目信息推荐需要生成的配置文件模板，返回 {文件名: 内容}"""
    templates: dict[str, str] = {}
    for framework in frameworks:
        if framework in FRAMEWORK_CONFIG_TEMPLATES:
            templates.update(FRAMEWORK_CONFIG_TEMPLATES[framework])
    if language in FRAMEWORK_CONFIG_TEMPLATES:
        templates.update(FRAMEWORK_CONFIG_TEMPLATES[language])
    return templates

if __name__ == "__main__":
    project_cwd = '/Users/wangyue/Desktop/work/train-departure-diary/train-departure-diary-frontend'
    result = analyze_project(project_cwd)
    print(result.project_config)
    print(result.project_info)