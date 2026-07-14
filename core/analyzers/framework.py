from configparser import ConfigParser
import tomllib
from dataclasses import dataclass
import os
from typing import NamedTuple

import xml.etree.ElementTree as ET
import yaml
import json

"""
自动扫描目标项目，并识别：
- 这是什么类型的项目？（前端、后端、小程序）
- 用了什么框架？（React/vue/Express/FastAPI...）
- 用了什么测试框架？（jest/vitest/pytest...）
- 用了什么构建工具？（Vite/webpack/poetry...）
"""

# @dataclass 会自动生成 __init__，省去手写构造函数的麻烦
@dataclass
class FrameworkInfo:
    project_type: str          # "frontend" | "backend" | "miniprogram" | "unknown"
    language: str              # "javascript" | "typescript" | "python" | "java" | "go"
    frameworks: list[str]      # ["react", "next.js"]
    test_framework: list[str]  # ["vitest", "playwright"]
    build_tools: list[str]     # ["vite"]
    has_dockerfile: bool
    has_ci_config: bool

# 声明一个元组类型
class ProjectInfo(NamedTuple):
    project_type: str
    target_analysis: str
    file_content: str

class AnalyzeInfo(NamedTuple):
    project_config: FrameworkInfo
    project_info: str

EXCLUDE_DIRS = ["node_modules", ".git", "__pycache__", ".venv", "venv", ".next", "dist", "build", ".autotest"]

FRAMEWORK_DICT = {
    "react": "React",
    "vue": "Vue",
    "@angular/core": "Angular",
    "@dcloudio/uni-app": "uni-app",
    "express": "Express",
    "fastify": "Fastify",
    "next": "Next",
    "nuxt": "Nuxt",

    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask"
}
TEST_FRAMEWORK_DICT = {
    "vitest": "Vitest",
    "jest": "Jest",
    "@playwright": "Playwright",
    "cypress": "Cypress",

    "pytest": "pytest"
}
BUILD_TOOL_DICT = {
    "vite": "vite",
    "webpack": "Webpack",
    "rollup": "Rollup",
    "esbuild": "ESBuild",
    "typescript": "TypeScript",
    "tsc": "TypeScript",
}

def read_file(path: str):
    with open(path, 'r', encoding="utf-8") as data:
        return data.read() # 返回文件内容

def detect_project_type(files: list[str], root: str) -> ProjectInfo | None:
    """查找项目标志性文件，判断项目类型"""
    result = None
    for f in files:
        path = os.path.join(root, f)
        if f == "package.json":
            result = ProjectInfo(
                project_type="frontend",
                target_analysis="json",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "pyproject.toml":
            result = ProjectInfo(
                project_type="Python",
                target_analysis="tomllib",
                file_content=read_file(path)
            )
            break 

        elif f == "pytest.ini" or f == "setup.cfg":
            result = ProjectInfo(
                project_type="Python",
                target_analysis="configparser",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "pom.xml":
            result = ProjectInfo(
                project_type="Java",
                target_analysis="xml.etree.ElementTree",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "build.gradle":
            result = ProjectInfo(
                project_type="Java",
                target_analysis="build.gradle",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "go.mod":
            result = ProjectInfo(
                project_type="Go",
                target_analysis="Go",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "manifest.json" or f == "pages.json":
            result = ProjectInfo(
                project_type="Mini-program",
                target_analysis="json",
                file_content=read_file(path)
            )
            break # 找到了就跳出

    return result

def analysis_go(content: str) -> dict:
    """简单的 go.mod 解析器 -- 提取依赖列表"""
    deps = {}
    in_block = False
    for line in content.splitlines():
        line = line.strip() # 去掉开头和结尾的空白字符（空格、制表符、换行符等）
        if line == "require (":
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

def detect_result_list(project_info: ProjectInfo, origin_dict: dict) -> list[str]:
    """"""
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
        # 返回 Element
        root = ET.fromstring(package_json_content)
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
    elif target_analysis == "Go": # 解析 go.mod
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


def detect_test_frameworks(project_info: ProjectInfo) -> list[str]:
    """解析项目使用了什么测试框架"""
    return detect_result_list(project_info, TEST_FRAMEWORK_DICT)


def detect_build_tools(project_info: ProjectInfo) -> list[str]:
    """解析项目使用了什么构建工具"""
    return detect_result_list(project_info, BUILD_TOOL_DICT)

def analyze_project(target_path: str) -> AnalyzeInfo:
    """项目检测入口函数"""
    detect_project_result = None
    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        result = detect_project_type(files, root)
        if result:
            detect_project_result = result
            break # 找到了就退出循环

    if not detect_project_result:
        return AnalyzeInfo(
            project_config=FrameworkInfo(project_type="unknown"),
            project_info="框架检测： 未知"
        )

    config = FrameworkInfo(
        project_type=detect_project_result.project_type or "",
        language="",
        frameworks=detect_frameworks(detect_project_result) or [],
        test_framework=detect_test_frameworks(detect_project_result) or [],
        build_tools=detect_build_tools(detect_project_result) or [],
        has_dockerfile=False,
        has_ci_config=False,
    )

    return AnalyzeInfo(
        project_config=config,
        project_info=f"框架检测：{' + '.join(config.frameworks)}"
    )


if __name__ == "__main__":
    project_cwd = '/Users/wangyue/Desktop/work/train-departure-diary/train-departure-diary-frontend'
    result = analyze_project(project_cwd)
    print(result.project_config)
    print(result.project_info)