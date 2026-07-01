from dataclasses import dataclass
import os
from typing import NamedTuple

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
    file_content: str

class AnalyzeInfo(NamedTuple):
    project_config: FrameworkInfo
    project_info: str

EXCLUDE_DIRS = ["node_modules", ".git", "__pycache__", ".venv", "venv", ".next", "dist", "build", ".autotest"]

FRAMEWORK_DICT = {
    "react": "React",
    "vue": "Vue",
    "@angular/core": "Angular",
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
    "typescript": "typescript",
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
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "pyproject.toml" or f == "pytest.ini" or f == "setup.cfg":
            result = ProjectInfo(
                project_type="Python",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "pom.xml" or f == "build.gradle":
            result = ProjectInfo(
                project_type="Java",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "go.mod":
            result = ProjectInfo(
                project_type="Go",
                file_content=read_file(path)
            )
            break # 找到了就跳出
        elif f == "manifest.json" or f == "pages.json":
            result = ProjectInfo(
                project_type="Mini-program",
                file_content=read_file(path)
            )
            break # 找到了就跳出

    return result

def detect_result_list(project_info: ProjectInfo, origin_dict: dict) -> list[str]:
    """"""
    result = []
    project_type = project_info.project_type
    package_json_content = project_info.file_content
    if project_type == "frontend":
        data = json.loads(package_json_content) # 解析 YAML -- Python 字典
        all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    else:
        data = yaml.safe_load(package_json_content) # 解析 YAML -- Python 字典
        all_deps = {}
    
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