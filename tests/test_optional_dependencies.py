"""可选依赖边界测试。"""

import importlib

import pytest
from click.testing import CliRunner

import cli.commands.generate as generate_module
import cli.commands.plan as plan_module
import cli.commands.run as run_module
import core.optional_dependencies as optional_module
from cli.main import cli
from core.models import TestSpec as Spec
from core.optional_dependencies import (
    OptionalDependencyError,
    require_optional_modules,
)
from core.repositories import TestSpecRepository as SpecRepository


def test_optional_dependency_error_has_stable_reason():
    error = OptionalDependencyError(
        extra="llm",
        capability="generate",
    )

    assert error.reason == "llm_extra_required"
    assert str(error) == (
        "llm_extra_required: generate 需要可选依赖；"
        "请安装 test-assistant[llm]"
    )


def test_require_optional_modules_does_not_import_available_modules(
    monkeypatch,
):
    observed = []
    monkeypatch.setattr(
        optional_module,
        "find_spec",
        lambda name: observed.append(name) or object(),
    )
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: pytest.fail(f"不应导入 {name}"),
    )

    require_optional_modules(
        extra="llm",
        capability="generate",
        modules=("langchain_core", "langchain_openai"),
    )

    assert observed == ["langchain_core", "langchain_openai"]


def test_require_optional_modules_reports_missing_extra(monkeypatch):
    monkeypatch.setattr(
        optional_module,
        "find_spec",
        lambda name: None if name == "langgraph" else object(),
    )

    with pytest.raises(
        OptionalDependencyError,
        match="llm_extra_required",
    ):
        require_optional_modules(
            extra="llm",
            capability="run",
            modules=("langchain_core", "langgraph"),
        )


@pytest.mark.parametrize(
    ("module", "command"),
    [
        (
            plan_module,
            [
                "plan", "propose", "demo.add",
                "--source-path", "demo.py",
                "--module-path", "demo",
            ],
        ),
        (
            generate_module,
            [
                "generate", "spec-001",
                "--module-path", "demo",
                "--source-path", "demo.py",
                "--test-filename", "test_demo.py",
            ],
        ),
        (run_module, ["run"]),
    ],
)
def test_llm_commands_map_missing_extra_to_exit_code_two(
    module,
    command,
    monkeypatch,
    tmp_path,
):
    def missing_extra(**kwargs):
        raise OptionalDependencyError(
            extra="llm",
            capability=kwargs["capability"],
        )

    monkeypatch.setattr(module, "require_optional_modules", missing_extra)
    if module is plan_module:
        monkeypatch.setattr(module, "LLMClient", None)
    elif module is generate_module:
        monkeypatch.setattr(module, "LLMClient", None)
    else:
        monkeypatch.setattr(module, "run_graph", None)

    if module is plan_module:
        (tmp_path / "demo.py").write_text(
            "def add(left, right):\n    return left + right\n",
            encoding="utf-8",
        )
        command.extend(["--path", str(tmp_path)])
    elif module is generate_module:
        repository = SpecRepository(tmp_path)
        repository.save(
            Spec(
                id="spec-001",
                target_symbol="demo.add",
                behavior="返回两数之和",
                arrange={},
                action="调用 add",
                expected={"return": 2},
            )
        )
        repository.approve("spec-001")
        command.extend(["--path", str(tmp_path)])

    result = CliRunner().invoke(cli, command)

    assert result.exit_code == 2, result.output
    assert "llm_extra_required" in result.output
    assert "Traceback" not in result.output
