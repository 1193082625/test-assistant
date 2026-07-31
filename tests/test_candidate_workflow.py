import pytest
from core.models import (
    TestSpec as Spec,
    TestSpecStatus as SpecStatus,
)
from core.workflows.candidate import (
    CandidateCommitStage,
    CandidateCommitStatus,
    CandidatePreparationStage,
    CandidatePreparationStatus,
    commit_reviewed_candidate,
    prepare_candidate_for_review,
)
from core.validators import (
    CandidateValidationResult,
    CandidateValidationStatus,
)


class FakeLLM:
    def __init__(self, candidate: str) -> None:
        self.candidate = candidate
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.candidate

def test_prepares_approved_spec_for_diff_review(tmp_path):
    """
    approved TestSpec
    → fake LLM
    → 生成源码
    → 保存候选
    → AST/import 验证
    → pytest collect-only
    → Runner 健康检查
    → 临时副本真实执行
    → build_diff
    → 正式测试仍不存在
    """
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={
            "a": 1,
            "b": 2,
        },
        action="调用 add(a, b)",
        expected={
            "return": 3
        },
        status=SpecStatus.APPROVED,
    )

    candidate_content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )
    llm = FakeLLM(candidate_content)

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert (
        result.status
        is CandidatePreparationStatus.READY_FOR_REVIEW
    )
    assert result.errors == ()
    assert len(result.validation_results) == 4
    assert all(
        validation.passed
        for validation in result.validation_results
    )

    assert result.candidate_path.is_file()
    assert result.candidate_path.read_text(encoding="utf-8") == candidate_content

    assert result.diff is not None
    assert result.diff.change_type == "created"
    assert result.diff.candidate_path == result.candidate_path
    assert not result.diff.final_path.exists()

    assert len(llm.prompts) == 1

@pytest.mark.parametrize(
    "status",
    [
        SpecStatus.PROPOSED,
        SpecStatus.REJECTED,
    ],
)
def test_stops_before_generation_for_unapproved_spec(
    tmp_path,
    status,
):
    spec = Spec(
        id="spec-demo-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={
            "a": 1,
            "b": 2,
        },
        action="调用 add(a, b)",
        expected={
            "return": 3,
        },
        status=status,
    )
    llm = FakeLLM(
        "def test_add(): pass\n"
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert (
        result.status
        is CandidatePreparationStatus.FAILED
    )
    assert (
        result.stage
        is CandidatePreparationStage.GENERATE
    )
    assert result.candidate_path is None
    assert result.validation_results == ()
    assert result.diff is None
    assert result.errors == (
        "只有 approved TestSpec "
        "可以进入生成器",
    )

    assert llm.prompts == []
    assert not (
        tmp_path
        / ".autotest"
        / "candidates"
    ).exists()

def test_stops_after_static_validation_failure(
    tmp_path,
):
    spec = Spec(
        id="spec-demo-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={
            "a": 1,
            "b": 2,
        },
        action="调用 add(a, b)",
        expected={
            "return": 3,
        },
        status=SpecStatus.APPROVED,
    )
    invalid_candidate = (
        "def test_add(:\n"
        "    pass\n"
    )
    llm = FakeLLM(
        invalid_candidate
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert (
        result.status
        is CandidatePreparationStatus.FAILED
    )
    assert (
        result.stage
        is CandidatePreparationStage
        .STATIC_VALIDATION
    )
    assert result.candidate_path is not None
    assert result.candidate_path.is_file()
    assert result.candidate_path.read_text(
        encoding="utf-8",
    ) == invalid_candidate

    assert len(
        result.validation_results
    ) == 1
    assert (
        result.validation_results[0].status
        is CandidateValidationStatus
        .SYNTAX_ERROR
    )
    assert result.errors == (
        "候选测试包含非法 Python 语法",
    )
    assert result.diff is None

    assert not (
        tmp_path
        / ".autotest"
        / "test_cases"
    ).exists()

def test_stops_after_pytest_collection_failure(
    tmp_path,
):
    spec = Spec(
        id="spec-demo-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={
            "a": 1,
            "b": 2,
        },
        action="调用 add(a, b)",
        expected={
            "return": 3,
        },
        status=SpecStatus.APPROVED,
    )

    candidate_content = (
        "raise RuntimeError("
        "'collection boom'"
        ")\n"
        "\n"
        "def test_add():\n"
        "    pass\n"
    )
    llm = FakeLLM(
        candidate_content
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert (
        result.status
        is CandidatePreparationStatus.FAILED
    )
    assert (
        result.stage
        is CandidatePreparationStage
        .COLLECTION
    )
    assert result.candidate_path is not None
    assert result.candidate_path.is_file()

    assert len(
        result.validation_results
    ) == 2
    assert (
        result.validation_results[0].status
        is CandidateValidationStatus.PASSED
    )
    assert (
        result.validation_results[1].status
        is CandidateValidationStatus
        .COLLECTION_ERROR
    )
    assert result.errors == (
        "pytest 收集候选测试失败",
    )
    assert result.diff is None

    assert not (
        tmp_path
        / ".autotest"
        / "test_cases"
    ).exists()

def test_stops_after_runner_health_failure(tmp_path, monkeypatch):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        "def add(left, right):\n"
        "    return left + right\n",
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-runner-error",
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
        status=SpecStatus.APPROVED,
    )
    llm = FakeLLM(
        candidate=(
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 1) == 2\n"
        )
    )

    def unhealthy_runner(*, project_root):
        return CandidateValidationResult(
            status=CandidateValidationStatus.RUNNER_ERROR,
            errors=("pytest Runner 健康检查失败",),
        )

    def should_not_execute(**kwargs):
        pytest.fail("Runner 不健康时不应启动隔离执行")

    monkeypatch.setattr(
        "core.workflows.candidate.check_pytest_runner_health",
        unhealthy_runner,
    )
    monkeypatch.setattr(
        "core.workflows.candidate.execute_pytest_candidate_isolated",
        should_not_execute,
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert result.status is CandidatePreparationStatus.FAILED
    assert result.stage is CandidatePreparationStage.RUNNER_HEALTH
    assert len(result.validation_results) == 3
    assert result.validation_results[0].status is CandidateValidationStatus.PASSED
    assert result.validation_results[1].status is CandidateValidationStatus.PASSED
    assert result.validation_results[2].status is CandidateValidationStatus.RUNNER_ERROR
    assert result.errors == ("pytest Runner 健康检查失败",)
    assert result.diff is None
    assert not (tmp_path / "test_cases").exists()

def test_stops_after_isolated_execution_failure(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-execution-error",
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
        status=SpecStatus.APPROVED,
    )

    llm = FakeLLM(
        candidate=(
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 1) == 999\n"
        )
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert result.status is CandidatePreparationStatus.FAILED
    assert result.stage is CandidatePreparationStage.ISOLATED_EXECUTION
    assert len(result.validation_results) == 4

    assert result.validation_results[0].status is CandidateValidationStatus.PASSED
    assert result.validation_results[1].status is CandidateValidationStatus.PASSED
    assert result.validation_results[2].status is CandidateValidationStatus.PASSED
    assert (
        result.validation_results[3].status
        is CandidateValidationStatus.TEST_FAILURE
    )

    assert result.errors
    assert result.diff is None
    assert result.candidate_path is not None
    assert result.candidate_path.is_file()
    assert not (tmp_path / "test_cases").exists()

def test_rejects_undeclared_filesystem_side_effect(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-undeclared-side-effect",
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
        # 没有声明 filesystem
        side_effects=[],
        status=SpecStatus.APPROVED,
    )

    llm = FakeLLM(
        candidate=(
            "from pathlib import Path\n"
            "\n"
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    Path('unexpected.txt').write_text(\n"
            "        'created by test',\n"
            "        encoding='utf-8',\n"
            "    )\n"
            "    assert add(1, 1) == 2\n"
        )
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert result.status is CandidatePreparationStatus.FAILED
    assert result.stage is CandidatePreparationStage.ISOLATED_EXECUTION
    assert len(result.validation_results) == 4

    isolated_result = result.validation_results[-1]
    assert isolated_result.status is CandidateValidationStatus.PASSED
    assert isolated_result.side_effects
    assert result.errors == (
        "候选测试产生了未声明的文件系统副作用",
    )

    assert result.diff is None
    assert not (tmp_path / "test_cases").exists()
    assert not (tmp_path / "unexpected.txt").exists()

def test_allows_declared_filesystem_side_effect(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-declared-side-effect",
        target_symbol="demo.add",
        behavior="计算两个整数之和并写入结果文件",
        arrange={
            "left": 1,
            "right": 1,
        },
        action="调用 add(left, right) 并写入文件",
        expected={
            "return": 2,
        },
        side_effects=["filesystem"],
        status=SpecStatus.APPROVED,
    )

    llm = FakeLLM(
        candidate=(
            "from pathlib import Path\n"
            "\n"
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    Path('expected.txt').write_text(\n"
            "        'created by test',\n"
            "        encoding='utf-8',\n"
            "    )\n"
            "    assert add(1, 1) == 2\n"
        )
    )

    result = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=llm,
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert (
        result.status
        is CandidatePreparationStatus.READY_FOR_REVIEW
    )
    assert result.stage is CandidatePreparationStage.BUILD_DIFF
    assert len(result.validation_results) == 4

    isolated_result = result.validation_results[-1]
    assert isolated_result.status is CandidateValidationStatus.PASSED
    assert isolated_result.side_effects

    assert result.errors == ()
    assert result.diff is not None
    assert not result.diff.final_path.exists()

    # 副作用只能发生在隔离副本中
    assert not (tmp_path / "expected.txt").exists()

def test_commits_reviewed_candidate_after_explicit_confirmation(
    tmp_path,
):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-commit",
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
        status=SpecStatus.APPROVED,
    )

    candidate_content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 1) == 2\n"
    )

    preparation = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=FakeLLM(candidate_content),
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert (
        preparation.status
        is CandidatePreparationStatus.READY_FOR_REVIEW
    )
    assert preparation.diff is not None
    assert not preparation.diff.final_path.exists()

    # 只有调用这个入口，才代表用户已经确认了 diff。
    commit_result = commit_reviewed_candidate(
        project_root=tmp_path,
        reviewed_diff=preparation.diff,
    )

    assert commit_result.status is CandidateCommitStatus.COMMITTED
    assert commit_result.stage is CandidateCommitStage.COMMIT
    assert commit_result.errors == ()
    assert commit_result.final_path == preparation.diff.final_path
    assert commit_result.final_path.is_file()
    assert (
        commit_result.final_path.read_text(encoding="utf-8")
        == candidate_content
    )

def test_rejects_stale_reviewed_diff(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-stale-diff",
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
        status=SpecStatus.APPROVED,
    )

    preparation = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=FakeLLM(
            (
                "from demo import add\n"
                "\n"
                "def test_add():\n"
                "    assert add(1, 1) == 2\n"
            )
        ),
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert preparation.diff is not None
    assert preparation.candidate_path is not None

    # 模拟用户看完 diff 后，候选内容又被其他操作修改。
    preparation.candidate_path.write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 1) == 999\n"
        ),
        encoding="utf-8",
    )

    commit_result = commit_reviewed_candidate(
        project_root=tmp_path,
        reviewed_diff=preparation.diff,
    )

    assert commit_result.status is CandidateCommitStatus.FAILED
    assert commit_result.stage is CandidateCommitStage.APPROVE_DIFF
    assert commit_result.final_path is None
    assert commit_result.errors
    assert not preparation.diff.final_path.exists()

def test_reports_commit_stage_failure(tmp_path, monkeypatch):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(left, right):\n"
            "    return left + right\n"
        ),
        encoding="utf-8",
    )

    spec = Spec(
        id="spec-demo-commit-error",
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
        status=SpecStatus.APPROVED,
    )

    preparation = prepare_candidate_for_review(
        project_root=tmp_path,
        llm=FakeLLM(
            (
                "from demo import add\n"
                "\n"
                "def test_add():\n"
                "    assert add(1, 1) == 2\n"
            )
        ),
        spec=spec,
        module_path="demo",
        source_relative_path="demo.py",
        test_filename="test_demo.py",
        generator_model="fake-model",
        template_version="v1",
    )

    assert preparation.diff is not None

    def fail_commit(self, *, approval):
        raise OSError("模拟正式文件写入失败")

    monkeypatch.setattr(
        "core.workflows.candidate.CandidateRepository.commit_candidate",
        fail_commit,
    )

    commit_result = commit_reviewed_candidate(
        project_root=tmp_path,
        reviewed_diff=preparation.diff,
    )

    assert commit_result.status is CandidateCommitStatus.FAILED
    assert commit_result.stage is CandidateCommitStage.COMMIT
    assert commit_result.final_path is None
    assert commit_result.errors == (
        "模拟正式文件写入失败",
    )
    assert not preparation.diff.final_path.exists()