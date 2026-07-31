import json

from click.testing import CliRunner

import cli.commands.plan as plan_module
from cli.main import cli
from core.models import TestSpecStatus as SpecStatus
from core.repositories import (
    TestSpecRepository as SpecRepository,
)


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_plan_propose_analyzes_and_saves_spec(
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
    fake_llm = FakeLLM(
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
    monkeypatch.setattr(
        plan_module,
        "LLMClient",
        lambda *, model: fake_llm,
    )

    result = CliRunner().invoke(
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

    assert result.exit_code == 0, result.output
    specs = SpecRepository(str(tmp_path)).list_all()
    assert len(specs) == 1
    assert specs[0].status is SpecStatus.PROPOSED
    assert specs[0].target_symbol == "demo.add"
    assert len(specs[0].evidence) == 2
    assert "已提议 TestSpec" in result.output
    assert len(fake_llm.prompts) == 1


def test_plan_propose_rejects_unknown_symbol(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        "def add(left, right):\n"
        "    return left + right\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        plan_module,
        "LLMClient",
        lambda *, model: FakeLLM("{}"),
    )

    result = CliRunner().invoke(
        cli,
        [
            "plan",
            "propose",
            "demo.missing",
            "--path",
            str(tmp_path),
            "--source-path",
            "demo.py",
            "--module-path",
            "demo",
        ],
    )

    assert result.exit_code != 0
    assert "源码中未找到目标符号" in result.output
