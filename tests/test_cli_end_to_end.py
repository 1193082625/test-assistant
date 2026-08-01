import json
import shutil
from pathlib import Path

from click.testing import CliRunner

import cli.commands.generate as generate_module
import cli.commands.plan as plan_module
from cli.main import cli
from core.repositories import TestSpecRepository as SpecRepository
from core.models import (
    TestSpec as Spec,
    TestSpecStatus as SpecStatus,
)


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


def test_cli_inspect_triage_diagnose_report_preserves_project_state(
    tmp_path,
):
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "real_project_triage"
        / "instance_method_mapping"
    )
    project = tmp_path / "triage-project"
    shutil.copytree(fixture, project)
    (project / "case.py").rename(project / "test_case.py")
    (project / "pyproject.toml").write_text(
        (
            '[project]\nname = "triage-project"\n'
            'version = "0.0.0"\n'
            'dependencies = ["pytest"]\n'
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    initialized = runner.invoke(
        cli,
        ["init", "--path", str(project), "--mode", "auto"],
    )
    assert initialized.exit_code == 0, initialized.output

    service = project / "app/service.py"
    service.write_text(
        service.read_text(encoding="utf-8").replace(
            "        return any(value > 0 for value in values.values())\n",
            "        return None\n",
        ),
        encoding="utf-8",
    )
    spec = Spec(
        id="spec-triage-preserved",
        target_symbol="app.service.Service.rule",
        behavior="返回布尔匹配结果",
        arrange={"values": []},
        action="调用 rule",
        expected={"return": False},
        status=SpecStatus.APPROVED,
    )
    spec_path = SpecRepository(str(project)).save(spec)

    inspected = runner.invoke(
        cli, ["inspect", "--path", str(project)]
    )
    assert inspected.exit_code == 0, inspected.output
    assert "app.service.Service.rule" in inspected.output
    assert "test_case.py" in inspected.output

    protected_paths = (
        service,
        project / "test_case.py",
        spec_path,
        project / ".autotest/snapshot.json",
    )
    before = {
        path: path.read_bytes() for path in protected_paths
    }

    triaged = runner.invoke(
        cli,
        [
            "triage",
            "--path",
            str(project),
            "--test-path",
            "test_case.py",
        ],
    )
    assert triaged.exit_code == 1, triaged.output
    assert "失败簇:" in triaged.output
    assert "inconclusive" in triaged.output

    diagnosis_path = project / ".autotest/diagnoses/latest.json"
    diagnosed = runner.invoke(
        cli,
        ["diagnose", "--input", str(diagnosis_path)],
    )
    assert diagnosed.exit_code == 0, diagnosed.output
    assert "诊断: inconclusive" in diagnosed.output

    report_path = project / "triage-report.md"
    reported = runner.invoke(
        cli,
        [
            "report",
            "--path",
            str(project),
            "--output",
            str(report_path),
        ],
    )
    assert reported.exit_code == 0, reported.output
    assert "Test Assistant 诊断报告" in report_path.read_text(
        encoding="utf-8"
    )
    assert {
        path: path.read_bytes() for path in protected_paths
    } == before
