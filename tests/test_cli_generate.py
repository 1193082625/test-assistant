import cli.commands.generate as generate_module
from click.testing import CliRunner

from cli.main import cli
from core.models import (
    TestSpec as Spec,
)
from core.repositories.test_spec import (
    TestSpecRepository as SpecRepository,
)


class FakeLLM:
    def __init__(self, candidate: str) -> None:
        self.candidate = candidate
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.candidate

def test_generate_reports_missing_spec(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "generate",
            "spec-missing",
            "--path",
            str(tmp_path),
            "--module-path",
            "demo",
            "--source-path",
            "demo.py",
            "--test-filename",
            "test_demo.py",
        ],
    )

    assert result.exit_code == 1
    assert result.output == (
        "Error: 未找到 TestSpec: spec-missing\n"
    )

def test_generate_rejects_unapproved_spec(tmp_path):
    repository = SpecRepository(
        project_root=str(tmp_path),
    )
    repository.save(
        Spec(
            id="spec-demo-001",
            target_symbol="demo.add",
            behavior="计算两个整数之和",
            arrange={
                "left": 1,
                "right": 1,
            },
            action="调用 add(left, right)",
            expected={
                "return": 2,
            },
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "spec-demo-001",
            "--path",
            str(tmp_path),
            "--module-path",
            "demo",
            "--source-path",
            "demo.py",
            "--test-filename",
            "test_demo.py",
        ],
    )

    assert result.exit_code == 1
    assert result.output == (
        "Error: 只有 approved TestSpec 可以生成候选测试\n"
    )
    assert not (
        tmp_path / ".autotest" / "candidates"
    ).exists()

def test_generate_shows_diff_and_preserves_formal_file_when_declined(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=str(tmp_path),
    )
    repository.save(
        Spec(
            id="spec-demo-001",
            target_symbol="demo.add",
            behavior="计算两个整数之和",
            arrange={
                "left": 1,
                "right": 1,
            },
            action="调用 add(left, right)",
            expected={
                "return": 2,
            },
        )
    )
    repository.approve("spec-demo-001")

    candidate_content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 1) == 2\n"
    )
    fake_llm = FakeLLM(candidate_content)

    monkeypatch.setattr(
        generate_module,
        "LLMClient",
        lambda *, model: fake_llm,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "spec-demo-001",
            "--path",
            str(tmp_path),
            "--module-path",
            "demo",
            "--source-path",
            "demo.py",
            "--test-filename",
            "test_demo.py",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "候选测试已通过验证" in result.output
    assert "test_add" in result.output
    assert "提交以上候选测试？" in result.output
    assert "已取消提交，正式测试未改变" in result.output

    assert len(fake_llm.prompts) == 1
    assert "模块路径: demo" in fake_llm.prompts[0]

    candidate_path = (
        tmp_path
        / ".autotest"
        / "candidates"
        / "spec-demo-001"
        / "demo.py"
        / "test_demo.py"
    )
    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "demo.py"
        / "test_demo.py"
    )

    assert candidate_path.is_file()
    assert not final_path.exists()

def test_generate_commits_candidate_when_confirmed(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=str(tmp_path),
    )
    repository.save(
        Spec(
            id="spec-demo-001",
            target_symbol="demo.add",
            behavior="计算两个整数之和",
            arrange={
                "left": 1,
                "right": 1,
            },
            action="调用 add(left, right)",
            expected={
                "return": 2,
            },
        )
    )
    repository.approve("spec-demo-001")

    candidate_content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 1) == 2\n"
    )
    fake_llm = FakeLLM(candidate_content)

    monkeypatch.setattr(
        generate_module,
        "LLMClient",
        lambda *, model: fake_llm,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "spec-demo-001",
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

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "demo.py"
        / "test_demo.py"
    )

    assert result.exit_code == 0
    assert "提交以上候选测试？" in result.output
    assert "已提交正式测试：" in result.output
    assert str(final_path) in result.output

    assert len(fake_llm.prompts) == 1
    assert final_path.is_file()
    assert (
        final_path.read_text(encoding="utf-8")
        == candidate_content
    )

def test_generate_reports_candidate_validation_failure(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=str(tmp_path),
    )
    repository.save(
        Spec(
            id="spec-demo-invalid",
            target_symbol="demo.add",
            behavior="计算两个整数之和",
            arrange={
                "left": 1,
                "right": 1,
            },
            action="调用 add(left, right)",
            expected={
                "return": 2,
            },
        )
    )
    repository.approve("spec-demo-invalid")

    fake_llm = FakeLLM(
        (
            "def test_add(:\n"
            "    pass\n"
        )
    )
    monkeypatch.setattr(
        generate_module,
        "LLMClient",
        lambda *, model: fake_llm,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "spec-demo-invalid",
            "--path",
            str(tmp_path),
            "--module-path",
            "demo",
            "--source-path",
            "demo.py",
            "--test-filename",
            "test_demo.py",
        ],
    )

    assert result.exit_code == 1
    assert (
        "候选准备失败 [static_validation]"
        in result.output
    )
    assert "候选测试包含非法 Python 语法" in result.output
    assert "提交以上候选测试？" not in result.output

    assert len(fake_llm.prompts) == 1
    assert not (
        tmp_path / ".autotest" / "test_cases"
    ).exists()

def test_cli_completes_m1_candidate_lifecycle(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "demo.py").write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=str(tmp_path),
    )
    repository.save(
        Spec(
            id="spec-demo-m1",
            target_symbol="demo.add",
            behavior="计算两个整数之和",
            arrange={
                "left": 1,
                "right": 1,
            },
            action="调用 add(left, right)",
            expected={
                "return": 2,
            },
        )
    )

    candidate_content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 1) == 2\n"
    )
    fake_llm = FakeLLM(candidate_content)
    monkeypatch.setattr(
        generate_module,
        "LLMClient",
        lambda *, model: fake_llm,
    )

    runner = CliRunner()

    approval = runner.invoke(
        cli,
        [
            "plan",
            "approve",
            "spec-demo-m1",
            "--path",
            str(tmp_path),
        ],
    )

    assert approval.exit_code == 0
    assert approval.output == (
        "已批准 TestSpec: "
        "spec-demo-m1 [approved]\n"
    )

    generation = runner.invoke(
        cli,
        [
            "generate",
            "spec-demo-m1",
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

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "demo.py"
        / "test_demo.py"
    )

    assert generation.exit_code == 0
    assert "候选测试已通过验证：" in generation.output
    assert "提交以上候选测试？" in generation.output
    assert "已提交正式测试：" in generation.output

    assert final_path.is_file()
    assert (
        final_path.read_text(encoding="utf-8")
        == candidate_content
    )
    assert len(fake_llm.prompts) == 1