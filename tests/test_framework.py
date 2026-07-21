"""测试框架检测模块"""

import json
import  os
import tempfile
import pytest

from core.analyzers.framework import (
    detect_project_type,
    detect_frameworks,
    detect_test_frameworks,
    detect_build_tools,
    analyze_project,
    ProjectInfo,
)

from core.models import Language, ProjectType
from core.models import  TestFramework as Framework

@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("package.json", "{ invalid json"),
        ("pyproject.toml", "[project\ninvalid"),
        ("pom.xml", "<project><invalid></project>"),
    ],
)
def test_analyze_project_invalid_config_returns_explainable_unknown(tmp_path, filename, content):
    (tmp_path / filename).write_text(content, encoding="utf-8")
    info = analyze_project(str(tmp_path))

    assert info.project_config.project_type is ProjectType.UNKNOWN
    assert info.project_config.language is Language.UNKNOWN
    assert filename in info.project_info
    assert "解析失败" in info.project_info

# @pytest.mark.parametrize 会用两组 files 分别执行同一个测试，相当于自动生成两个测试场景
@pytest.mark.parametrize(
    "files",
    [
        ["package.json", "pages.json"],
        ["pages.json", "package.json"],
    ],
)
def test_detect_miniprogram_is_independent_of_file_order(tmp_path, files):
    """验证文件顺序不应影响结果"""
    package = {
        "dependencies": {
            "@dcloudio/uni-app": "^3.0.0",
        }
    }

    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    (tmp_path / "pages.json").write_text("{}", encoding="utf-8")

    result = detect_project_type(files, str(tmp_path))
    assert result is not None
    assert result.project_type is ProjectType.MINIPROGRAM
    assert result.language == Language.JAVASCRIPT

def test_detect_package_json_express_as_backend(tmp_path):
    """证明 package.json 不一定是前端"""
    package = {
        "dependencies": {
            "express": "^5.0.0"
        }
    }

    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    result = detect_project_type(["package.json"], str(tmp_path))
    assert result is not None
    assert result.project_type is ProjectType.BACKEND
    assert result.language == Language.JAVASCRIPT
    assert result.source_file == "package.json"
    assert result.target_analysis == "json"

def test_detect_package_json_react():
    """能从 package.json 检测到 React 项目"""
    package = {
        "name": "test-app",
        "dependencies": {
            "react": "^18.0.0",
            "next": "latest",
        },
        "devDependencies": {
            "vitest": "^1.0.0",
            "typescript": "^5.0.0"
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = os.path.join(tmpdir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump(package, f)

        result = detect_project_type(["package.json"], tmpdir)

        assert result is not None
        assert result.project_type == ProjectType.FRONTEND
        assert result.language is Language.TYPESCRIPT

        frameworks = detect_frameworks(result)
        assert "React" in frameworks
        assert "Next" in frameworks

        test_fw = detect_test_frameworks(result)
        assert Framework.VITEST in test_fw

        build_tools = detect_build_tools(result)
        assert "TypeScript" in build_tools

def test_detect_pyproject_toml():
    """能从 pyproject.toml 检测到 Python 项目"""
    toml_content = """
    [project]
    name = "test-app"
    dependencies = [
        "fastapi>=0.100.0",
        "pytest>=8.0.0"
    ]
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = os.path.join(tmpdir, "pyproject.toml")
        with open(toml_path, "w") as f:
            f.write(toml_content)

        result = detect_project_type(["pyproject.toml"], tmpdir)
        assert result is not None
        assert result.project_type == ProjectType.BACKEND
        assert result.language == Language.PYTHON

        frameworks = detect_frameworks(result)
        assert "FastAPI" in frameworks

def test_detect_java_maven():
    """能从 pom.xml 检测到 Java + Spring Boot 项目"""
    pom_content = """
    <?xml version="1.0" encoding="UTF-8"?>                                                                 
  <project>                                                       
      <groupId>com.example</groupId>
      <artifactId>my-app</artifactId>
      <version>1.0.0</version>
      <dependencies>
          <dependency>
              <groupId>org.springframework.boot</groupId>
              <artifactId>spring-boot-starter-web</artifactId>
          </dependency>
          <dependency>
              <groupId>junit</groupId>
              <artifactId>junit</artifactId>
              <scope>test</scope>
          </dependency>
      </dependencies>
  </project>
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_path = os.path.join(tmpdir, "pom.xml")
        with open(pom_path, "w") as f:
            f.write(pom_content)

        result = detect_project_type(["pom.xml"], tmpdir)
        assert result is not None
        assert result.project_type == ProjectType.BACKEND
        assert result.language == Language.JAVA

def test_detect_go():
    """能从 go.mod 检测到 Go 项目"""
    go_mod_content = """
    module github.com/user/my-app
    go 1.21
    require(
      github.com/gin-gonic/gin v1.9.1
      github.com/stretchr/testify v1.8.4
    )
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        go_path = os.path.join(tmpdir, "go.mod")
        with open(go_path, "w") as f:
            f.write(go_mod_content)

        result = detect_project_type(["go.mod"], tmpdir)
        assert result is not None
        assert result.project_type == ProjectType.BACKEND
        assert result.language == Language.GO

def test_detect_uni_app():
    """能检测到 uni-app 小程序项目"""
    package = {
        "dependencies": {
            "@dcloudio/uni-app": "^3.0.0-alpha-5010320260611001",
            "@dcloudio/uni-mp-weixin": "^3.0.0-alpha-5010320260611001"
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = os.path.join(tmpdir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump(package, f)

        result = detect_project_type(["package.json", "pages.json"], tmpdir)
        assert result is not None

        frameworks = detect_frameworks(result)
        assert "uni-app" in frameworks

def test_detect_unknown_project():
    """未知项目应返回 None"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = detect_project_type(["unknown.txt"], tmpdir)
        assert result is None

def test_analyze_project_full():
    """analyze_project 完整流程"""
    package = {
        "dependencies": {
            "vue": "^3.0.0",
            "express": "^4.0.0",
        },
        "devDependencies": {
            "vitest": "^1.0.0",
            "vite": "^5.0.0"
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = os.path.join(tmpdir, "package.json")
        with open(pkg_path, "w") as f:
            json.dump(package, f)

        info = analyze_project(tmpdir)

        assert info.project_config.project_type is ProjectType.BACKEND
        assert info.project_config.language == Language.JAVASCRIPT
        assert Framework.VITEST in info.project_config.test_frameworks

        assert "Vue" in info.project_config.frameworks
        assert "Express" in info.project_config.frameworks
        assert Framework.VITEST in info.project_config.test_frameworks
        assert "vite" in info.project_config.build_tools or "Vite" in info.project_config.build_tools

def test_analyze_unknown_project_explains_missing_marker(tmp_path):
    """测试没有检测证据 --> 未发现支持的项目标志文件"""
    # 在 pytest 提供的临时目录中创建一个 README.md 文件，并且写入 “# unknown project”
    (tmp_path / "README.md").write_text(
        "# unknown project",
        encoding="utf-8",
    )

    info = analyze_project(str(tmp_path))

    assert info.project_config.project_type is ProjectType.UNKNOWN
    assert info.project_config.language is Language.UNKNOWN
    assert "未发现支持的项目标志文件" in info.project_info

def test_analyze_valid_package_without_known_framework_is_explainable(tmp_path):
    package = {
        "name": "my-tool",
        "dependencies": {}
    }

    (tmp_path / "package.json").write_text(
        json.dumps(package),
        encoding="utf-8",
    )
    info = analyze_project(str(tmp_path))
    assert info.project_config.project_type is ProjectType.UNKNOWN
    assert info.project_config.language is Language.JAVASCRIPT
    assert "package.json" in info.project_info
    assert "未识别到支持的框架依赖" in info.project_info