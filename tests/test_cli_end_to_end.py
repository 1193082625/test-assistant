import json

from click.testing import CliRunner

import cli.commands.generate as generate_module
import cli.commands.plan as plan_module
from cli.main import cli
from core.repositories import TestSpecRepository as SpecRepository


class FakeLLM:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return self.response


def test_cli_runs_propose_approve_generate_verify_flow(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        (
            "def add(left: int, right: int) -> int:\n"
            '    """返回两个整数之和。"""\n'
            "    return left + right\n"
        ),
        encoding="utf-8",
    )
    planner_llm = FakeLLM(
        json.dumps(
            {
                "behavior": "返回两个整数之和",
                "arrange": {"left": 1, "right": 1},
                "action": "调用 add(left, right)",
                "expected": {"return": 2},
                "side_effects": [],
            },
            ensure_ascii=False,
        )
    )
    generator_llm = FakeLLM(
        "from demo import add\n\n"
        "def test_add():\n"
        "    assert add(1, 1) == 2\n"
    )
    monkeypatch.setattr(
        plan_module,
        "LLMClient",
        lambda *, model: planner_llm,
    )
    monkeypatch.setattr(
        generate_module,
        "LLMClient",
        lambda *, model: generator_llm,
    )
    runner = CliRunner()

    proposal = runner.invoke(
        cli,
        [
            "plan",
            "propose",
            "demo.add",
            "--path",
            str(tmp_path),
            "--source-path",
            "demo.py",
            "--module-path",
            "demo",
        ],
    )
    assert proposal.exit_code == 0, proposal.output
    spec = SpecRepository(str(tmp_path)).list_all()[0]

    approval = runner.invoke(
        cli,
        [
            "plan",
            "approve",
            spec.id,
            "--path",
            str(tmp_path),
        ],
    )
    assert approval.exit_code == 0, approval.output

    generation = runner.invoke(
        cli,
        [
            "generate",
            spec.id,
            "--path",
            str(tmp_path),
            "--module-path",
            "demo",
            "--source-path",
            "demo.py",
            "--test-filename",
            "test_demo.py",
        ],
        input="y\n",
    )
    assert generation.exit_code == 0, generation.output

    test_node = (
        ".autotest/test_cases/unit/demo.py/"
        "test_demo.py::test_add"
    )
    verification = runner.invoke(
        cli,
        [
            "verify",
            spec.id,
            "--path",
            str(tmp_path),
            "--test-node",
            test_node,
            "--source-path",
            "demo.py",
        ],
    )
    assert verification.exit_code == 0, verification.output
    assert "连续 3 次通过" in verification.output

    health = runner.invoke(
        cli,
        ["status", "--path", str(tmp_path)],
    )
    assert health.exit_code == 0, health.output
    assert "状态: 健康" in health.output
