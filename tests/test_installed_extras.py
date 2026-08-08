"""wheel extras 和 base 导入边界的静态契约。"""

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]


def _configuration() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def _names(requirements: list[str]) -> set[str]:
    return {
        requirement.split(" ", 1)[0].lower()
        for requirement in requirements
    }


def test_base_and_optional_dependency_sets_are_explicit():
    project = _project_metadata()

    assert _names(project["dependencies"]) == {"click", "pyyaml"}
    extras = project["optional-dependencies"]
    assert _names(extras["llm"]) == {
        "langchain-core",
        "langchain-openai",
        "langgraph",
        "python-dotenv",
    }
    assert _names(extras["quality"]) == {
        "pytest-cov",
        "coverage",
        "ruff",
        "mypy",
    }
    assert _names(extras["all"]) == (
        _names(extras["llm"]) | _names(extras["quality"])
    )


def test_dev_dependencies_provide_runtime_fixture_dependencies():
    configuration = _configuration()

    assert _names(configuration["dependency-groups"]["dev"]) == {
        "pytest",
        "pydantic",
        "langgraph",
    }


def test_root_cli_imports_when_optional_packages_are_blocked():
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys

        blocked = (
            "dotenv", "langchain", "langgraph", "langsmith",
            "coverage", "ruff", "mypy",
        )

        class BlockOptional(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith(blocked):
                    raise ModuleNotFoundError(fullname)
                return None

        sys.meta_path.insert(0, BlockOptional())
        from click.testing import CliRunner
        from cli.main import cli

        runner = CliRunner()
        for arguments in (
            ["--help"],
            ["doctor", "--help"],
            ["triage", "--help"],
            ["plan", "list", "--help"],
        ):
            result = runner.invoke(cli, arguments)
            assert result.exit_code == 0, (arguments, result.output, result.exception)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
