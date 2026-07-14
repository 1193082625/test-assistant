"""测试框架检测模块"""

import json
import  os
import tempfile

from core.analyzers.framework import (
    detect_project_type,
    detect_frameworks,
    detect_test_frameworks,
    detect_build_tools,
    analyze_project,
    ProjectInfo,
)

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
        assert result.project_type == "frontend"

        frameworks = detect_frameworks(result)
        assert "React" in frameworks
        assert "Next" in frameworks

        test_fw = detect_test_frameworks(result)
        assert "Vitest" in test_fw

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
        assert result.project_type == "Python"

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
        assert result.project_type == "Java"

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
        assert result.project_type == "Go"

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

        assert info.project_config.project_type == "frontend"
        assert "Vue" in info.project_config.frameworks
        assert "Express" in info.project_config.frameworks
        assert "Vitest" in info.project_config.test_framework
        assert "vite" in info.project_config.build_tools or "Vite" in info.project_config.build_tools
