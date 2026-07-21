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
    build_framework_info, analyze_project_modules,
)

from core.models import Language, ProjectType, ProjectAnalysis, ProjectModule, FrameworkInfo
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

def test_detect_pytest_ini_uses_correct_source_file(tmp_path):
    """pytest.nin 检测测试"""
    (tmp_path / "pytest.ini").write_text(
        """
        [pytest]
        testpaths = tests
        """.strip(),
        encoding="utf-8",
    )
    result = detect_project_type(["pytest.ini"], str(tmp_path))
    assert result is not None
    assert result.project_type is ProjectType.BACKEND
    assert result.language is Language.PYTHON
    assert result.source_file == "pytest.ini"
    assert result.target_analysis == "configparser"

    test_frameworks = detect_test_frameworks(result)
    assert Framework.PYTEST in test_frameworks

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
    """有合法标志文件，但没有识别到已支持的框架"""
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

def test_build_framework_info_from_project_info(tmp_path):
    """测试 build_framework_info 函数"""
    package = {
        "dependencies": {
            "express": "^5.0.0",
        },
        "devDependencies": {
            "vitest": "^3.0.0",
        },
    }

    (tmp_path / "package.json").write_text(
        json.dumps(package),
        encoding="utf-8",
    )

    project_info = detect_project_type(["package.json"], str(tmp_path))

    assert project_info is not None

    framework_info = build_framework_info(project_info)

    assert framework_info.project_type is ProjectType.BACKEND
    assert framework_info.language is Language.JAVASCRIPT
    assert "Express" in framework_info.frameworks
    assert Framework.VITEST in framework_info.test_frameworks

def test_analyze_project_modules_collects_all_modules(tmp_path):
    frontend_dir = tmp_path / "frontend"
    backend_dir = tmp_path / "backend"

    frontend_dir.mkdir()
    backend_dir.mkdir()

    (frontend_dir / "package.json").write_text(
        json.dumps({
            "dependencies": {
                "react": "^19.0.0",
                "typescript": "^5.0.0",
            }
        }),
        encoding="utf-8",
    )

    (backend_dir / "pyproject.toml").write_text(
        """
        [project]
        name="backend"
        dependencies=["fastapi>=0.100.0"]
        """.strip(),
        encoding="utf-8",
    )

    analysis = analyze_project_modules(str(tmp_path))

    modules_by_name = {
        os.path.basename(module.root_path): module for module in analysis.modules
    }

    assert set(modules_by_name) == {"frontend", "backend"}

    frontend = modules_by_name["frontend"]
    assert frontend.source_file == "package.json"
    assert frontend.framework_info.project_type is ProjectType.FRONTEND
    assert frontend.framework_info.language is Language.TYPESCRIPT
    assert "React" in frontend.framework_info.frameworks

    backend = modules_by_name["backend"]
    assert backend.source_file == "pyproject.toml"
    assert backend.framework_info.project_type is ProjectType.BACKEND
    assert backend.framework_info.language is Language.PYTHON
    assert "FastAPI" in backend.framework_info.frameworks

    assert analysis.primary_type is ProjectType.MIXED

def test_analyze_project_modules_isolates_broken_module(tmp_path):
    """测试一个损坏模块不能阻断其他模块"""
    backend_dir = tmp_path / "backend"
    frontend_dir = backend_dir / "broken-frontend"

    backend_dir.mkdir()
    frontend_dir.mkdir()

    (backend_dir / "pyproject.toml").write_text(
        """
        [project]
        name="backend"
        dependencies=["fastapi>=0.100.0"]
        """.strip(),
        encoding="utf-8",
    )

    (frontend_dir / "package.json").write_text(
        "{ invalid json",
        encoding="utf-8",
    )

    analysis = analyze_project_modules(str(tmp_path))

    modules_by_name = {
        os.path.basename(module.root_path): module for module in analysis.modules
    }

    assert set(modules_by_name) == {"backend", "broken-frontend"}

    backend = modules_by_name["backend"]
    assert backend.framework_info.language is Language.PYTHON

    broken = modules_by_name["broken-frontend"]
    assert broken.source_file == "package.json"
    assert broken.framework_info.project_type is ProjectType.UNKNOWN
    assert broken.framework_info.language is Language.UNKNOWN

    expected_path = os.path.join(
        "broken-frontend",
        "package.json",
    )
    assert any(
        expected_path in warning and "解析失败" in warning
        for warning in analysis.warnings
    )

def test_analyze_project_modules_isolates_parser_error(tmp_path):
    frontend_dir = tmp_path / "frontend"
    backend_dir = frontend_dir / "broken-backend"

    frontend_dir.mkdir()
    backend_dir.mkdir()

    (frontend_dir / "package.json").write_text(
        json.dumps({
            "dependencies": {
                "react": "^19.0.0",
            }
        }),
        encoding="utf-8",
    )

    (backend_dir / "pyproject.toml").write_text(
        "[project\ninvalid",
        encoding="utf-8",
    )

    analysis = analyze_project_modules(str(tmp_path))

    modules_by_name = {}

    for module in analysis.modules:
        module_name = os.path.basename(module.root_path)
        modules_by_name[module_name] = module

    assert set(modules_by_name) == {
        "frontend",
        "broken-backend",
    }

    frontend = modules_by_name["frontend"]
    assert frontend.framework_info.project_type is ProjectType.FRONTEND

    backend = modules_by_name["broken-backend"]
    assert backend.source_file == "pyproject.toml"
    assert backend.framework_info.project_type is ProjectType.UNKNOWN
    assert backend.framework_info.language is Language.UNKNOWN

    expected_path = os.path.join(
        "broken-backend",
        "pyproject.toml",
    )

    assert any(
        expected_path in warning and "解析失败" in warning
        for warning in analysis.warnings
    )

def test_project_analysis_primary_type_is_mixed():
    analysis = ProjectAnalysis(
        root_path="/demo",
        modules=[
            ProjectModule(
                root_path="/demo/frontend",
                source_file="package.json",
                framework_info=FrameworkInfo(
                    project_type=ProjectType.FRONTEND,
                ),
            ),
            ProjectModule(
                root_path="/demo/backend",
                source_file="pyproject.toml",
                framework_info=FrameworkInfo(
                    project_type=ProjectType.BACKEND,
                ),
            ),
        ],
    )

    assert analysis.primary_type is ProjectType.MIXED

def test_project_analysis_primary_type_ignores_broken_module():
    analysis = ProjectAnalysis(
        root_path="/demo",
        modules=[
            ProjectModule(
                root_path="/demo/backend",
                source_file="pyproject.toml",
                framework_info=FrameworkInfo(
                    project_type=ProjectType.BACKEND,
                ),
            ),
            ProjectModule(
                root_path="/demo/broken",
                source_file="package.json",
                framework_info=FrameworkInfo()
            ),
        ],
    )

    assert analysis.primary_type is ProjectType.BACKEND

def test_empty_project_analysis_primary_type_is_unknown():
    analysis = ProjectAnalysis(
        root_path="/demo",
    )
    assert analysis.primary_type is ProjectType.UNKNOWN