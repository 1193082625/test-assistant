import json
import os
from pathlib import Path

import pytest

from core.repositories import (
    CandidateRepository,
    build_candidate_content_digest,
)


GENERATOR_MODEL = "fake-model"
TEMPLATE_VERSION = "test-spec-generator-v1"

def test_repository_saves_candidate_in_isolated_area(tmp_path):
    repository = CandidateRepository(
        project_root=tmp_path,
    )

    saved_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content="def test_demo(): pass\n",
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )

    expected_path = (
        tmp_path
        / ".autotest"
        / "candidates"
        / "spec-demo-001"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )

    assert saved_path == expected_path
    assert expected_path.read_text(encoding="utf-8") == "def test_demo(): pass\n"

    assert not (
        tmp_path / "tests" / "test_demo.py"
    ).exists()

@pytest.mark.parametrize(
    "unsafe_spec_id",
    [
        "../escape",
        "folder/spec",
        r"folder\spec",
        ".",
        "",
    ]
)
def test_repository_rejects_unsafe_spec_id(
        tmp_path,
        unsafe_spec_id,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match=(
            "Candidate spec_id "
            "包含不安全字符"
        ),
    ):
        repository.save(
            spec_id=unsafe_spec_id,
            source_relative_path="src/demo.py",
            test_filename="test_demo.py",
            content="def test_demo(): pass\n",
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
        )

@pytest.mark.parametrize(
    "unsafe_source_path",
    [
        None,
        "",
        ".",
        "../demo.py",
        "src/../../demo.py",
        r"src\..\demo.py",
        "__absolute_path__",
    ],
)
def test_repository_rejects_unsafe_source_path(
        tmp_path,
        unsafe_source_path,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )
    outside_path = tmp_path / "outside.py"
    if unsafe_source_path == "__absolute_path__":
        source_relative_path = str(outside_path)
    else:
        source_relative_path = unsafe_source_path

    with pytest.raises(
        ValueError,
        match=(
            "Candidate source_relative_path "
            "必须是安全相对路径"
        ),
    ):
        repository.save(
            spec_id="spec-demo-001",
            source_relative_path=source_relative_path,
            test_filename="test_demo.py",
            content="def test_demo(): pass\n",
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
        )

    assert not outside_path.exists()

@pytest.mark.parametrize(
    "unsafe_test_filename",
    [
        None,
        "",
        ".",
        "../test_demo.py",
        "folder/test_demo.py",
        r"folder\test_demo.py",
        "demo.py",
        "test_demo.txt",
        "test_demo-test.py",
        "__absolute_path__",
    ],
)
def test_repository_rejects_unsafe_test_filename(
        tmp_path,
        unsafe_test_filename,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )

    outside_path = tmp_path / "test_outside.py"

    if (
       unsafe_test_filename == "__absolute_path__"
    ):
        test_filename = str(outside_path)
    else:
        test_filename = unsafe_test_filename

    with pytest.raises(
        ValueError,
        match=(
            "Candidate test_filename 必须是"
            "安全 Python 测试文件名"
        )
    ):
        repository.save(
            spec_id="spec-demo-001",
            source_relative_path="src/demo.py",
            test_filename=test_filename,
            content="def test_demo(): pass\n",
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
        )

    assert not outside_path.exists()

def test_repository_does_not_overwrite_different_candidate(
    tmp_path,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )

    original_content = (
        "def test_demo():\n"
        "    assert 1 + 1 == 2\n"
    )
    conflicting_content = (
        "def test_demo():\n"
        "    assert 1 + 1 == 3\n"
    )

    saved_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=original_content,
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
    )

    with pytest.raises(
        FileExistsError,
        match=(
            "候选测试已存在且内容不同"
        ),
    ):
        repository.save(
            spec_id="spec-demo-001",
            source_relative_path="src/demo.py",
            test_filename="test_demo.py",
            content=conflicting_content,
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
        )

    assert saved_path.read_text(
        encoding="utf-8",
    ) == original_content

def test_repository_same_candidate_is_idempotent(
    tmp_path,
    monkeypatch,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )
    content = "def test_demo(): pass\n"

    original_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )

    def forbidden_write_text(
        self,
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "相同候选不应重复写入"
        )

    monkeypatch.setattr(
        Path,
        "write_text",
        forbidden_write_text,
    )

    repeated_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )

    assert repeated_path == original_path

def test_builds_stable_candidate_content_digest():
    content = "def test_demo(): pass\n"

    digest = build_candidate_content_digest(
        content
    )

    assert digest == (
        "bbe0985c54945e68f66742d2a84cba0c"
        "708372fa81105a63f75f3a481d4f196b"
    )

def test_repository_saves_candidate_metadata(
    tmp_path,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )
    content = "def test_demo(): pass\n"

    saved_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )

    metadata_path = saved_path.with_name(
        f"{saved_path.name}.meta.json"
    )

    payload = json.loads(
        metadata_path.read_text(
            encoding="utf-8",
        )
    )

    assert payload == {
        "version": 1,
        "spec_id": "spec-demo-001",
        "source_relative_path": "src/demo.py",
        "test_filename": "test_demo.py",
        "generator_model": GENERATOR_MODEL,
        "template_version": TEMPLATE_VERSION,
        "content_sha256": (
            build_candidate_content_digest(
                content
            )
        ),
    }

@pytest.mark.parametrize(
    (
        "field_name",
        "invalid_value",
        "message",
    ),
    [
        (
            "generator_model",
            None,
            "Candidate generator_model 不能为空",
        ),
        (
            "generator_model",
            "",
            "Candidate generator_model 不能为空",
        ),
        (
            "generator_model",
            "   ",
            "Candidate generator_model 不能为空",
        ),
        (
            "template_version",
            None,
            "Candidate template_version 不能为空",
        ),
        (
            "template_version",
            "",
            "Candidate template_version 不能为空",
        ),
        (
            "template_version",
            "   ",
            "Candidate template_version 不能为空",
        ),
    ],
)
def test_repository_rejects_missing_audit_metadata(
    tmp_path,
    field_name,
    invalid_value,
    message,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )

    arguments = {
        "spec_id": "spec-demo-001",
        "source_relative_path": "src/demo.py",
        "test_filename": "test_demo.py",
        "content": "def test_demo(): pass\n",
        "generator_model": GENERATOR_MODEL,
        "template_version": TEMPLATE_VERSION,
    }
    arguments[field_name] = invalid_value

    with pytest.raises(
        ValueError,
        match=message,
    ):
        repository.save(**arguments)

    assert not repository.candidates_path.exists()

def test_repository_rejects_candidate_without_metadata(
    tmp_path,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )
    content = "def test_demo(): pass\n"

    saved_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )
    metadata_path = saved_path.with_name(
        f"{saved_path.name}.meta.json"
    )

    metadata_path.unlink()

    with pytest.raises(
            FileNotFoundError,
            match="候选测试元数据缺失",
    ):
        repository.save(
            spec_id="spec-demo-001",
            source_relative_path="src/demo.py",
            test_filename="test_demo.py",
            content=content,
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
        )

    assert saved_path.read_text(
        encoding="utf-8",
    ) == content
    assert not metadata_path.exists()

def test_repository_rejects_metadata_without_candidate(
    tmp_path,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )
    content = "def test_demo(): pass\n"

    saved_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )
    metadata_path = saved_path.with_name(
        f"{saved_path.name}.meta.json"
    )

    saved_path.unlink()

    with pytest.raises(
        FileNotFoundError,
        match="候选测试源码缺失",
    ):
        repository.save(
            spec_id="spec-demo-001",
            source_relative_path="src/demo.py",
            test_filename="test_demo.py",
            content=content,
            generator_model=GENERATOR_MODEL,
            template_version=TEMPLATE_VERSION,
        )

    assert not saved_path.exists()
    assert metadata_path.is_file()

def test_repository_keeps_same_named_sources_separate(
    tmp_path,
):
    repository = CandidateRepository(
        project_root=tmp_path,
    )

    first_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path=(
            "service_a/demo.py"
        ),
        test_filename="test_demo.py",
        content="def test_service_a(): pass\n",
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )

    second_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path=(
            "service_b/demo.py"
        ),
        test_filename="test_demo.py",
        content="def test_service_b(): pass\n",
        generator_model=GENERATOR_MODEL,
        template_version=TEMPLATE_VERSION,
    )

    assert first_path != second_path

    assert first_path.read_text(
        encoding="utf-8",
    ) == "def test_service_a(): pass\n"

    assert second_path.read_text(
        encoding="utf-8",
    ) == "def test_service_b(): pass\n"

def test_repository_builds_diff_for_new_candidate(tmp_path):
    """
    这条测试锁定四个设计决策：
    diff 是结构化结果，不只是展示文本。
    正式路径由候选元数据推导，调用者不能任意指定。
    新文件使用 /dev/null 作为旧文件。
    diff 携带内容摘要，后续批准和提交可以验证“批准的是同一份内容”。
    """
    repository = CandidateRepository(tmp_path)
    content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model="fake-model",
        template_version="v1",
    )

    result = repository.build_diff(
        candidate_path=candidate_path,
    )
    assert result.candidate_path == candidate_path
    assert result.final_path == (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )
    assert result.change_type == "created"
    assert result.content_sha256 == (
        build_candidate_content_digest(
            content
        )
    )
    assert "--- /dev/null" in result.text
    assert (
        "+++ .autotest/test_cases/unit/"
        "src/demo.py/test_demo.py"
    ) in result.text
    assert "+def test_add():" in result.text
    assert (
            result.original_content_sha256
            is None
    )

def test_repository_builds_diff_for_existing_test(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )
    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    original_content = (
        "def test_value():\n"
        "    assert VALUE == 1\n"
    )
    final_path.write_text(
        original_content,
        encoding="utf-8",
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 2\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    result = repository.build_diff(
        candidate_path=candidate_path,
    )

    expected_relative_path = (
        ".autotest/test_cases/unit/"
        "src/demo.py/test_demo.py"
    )

    assert result.change_type == "modified"
    assert result.final_path == final_path
    assert (
        f"--- {expected_relative_path}"
        in result.text
    )
    assert (
        f"+++ {expected_relative_path}"
        in result.text
    )
    assert "-    assert VALUE == 1" in result.text
    assert "+    assert VALUE == 2" in result.text

    assert final_path.read_text(
        encoding="utf-8",
    ) == original_content
    assert result.original_content_sha256 == (
        build_candidate_content_digest(
            original_content
        )
    )

def test_repository_rejects_tampered_candidate_when_building_diff(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    candidate_path.write_text(
        (
            "def test_value():\n"
            "    assert VALUE == 999\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="候选测试内容摘要不匹配",
    ):
        repository.build_diff(
            candidate_path=candidate_path,
        )

def test_repository_rejects_unsafe_metadata_source_path(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    metadata_path = candidate_path.with_name(
        f"{candidate_path.name}.meta.json"
    )
    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8",
        )
    )
    metadata["source_relative_path"] = (
        "../../../../outside"
    )
    metadata_path.write_text(
        (
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=4,
                )
                + "\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
            ValueError,
            match="候选测试元数据路径不安全",
    ):
        repository.build_diff(
            candidate_path=candidate_path,
        )

def test_repository_rejects_unsafe_metadata_test_filename(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    metadata_path = candidate_path.with_name(
        f"{candidate_path.name}.meta.json"
    )
    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8",
        )
    )
    metadata["test_filename"] = (
        "../test_escape.py"
    )
    metadata_path.write_text(
        (
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=4,
            )
            + "\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="候选测试元数据路径不安全",
    ):
        repository.build_diff(
            candidate_path=candidate_path,
        )

def test_repository_rejects_metadata_that_does_not_match_candidate_path(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    metadata_path = candidate_path.with_name(
        f"{candidate_path.name}.meta.json"
    )
    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8",
        )
    )
    metadata["source_relative_path"] = (
        "src/other.py"
    )
    metadata_path.write_text(
        (
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=4,
                )
                + "\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
            ValueError,
            match=(
                    "候选测试元数据与文件路径不匹配"
            ),
    ):
        repository.build_diff(
            candidate_path=candidate_path,
        )

def test_repository_approves_unchanged_candidate_diff(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )

    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )

    assert (
        approval.candidate_path
        == reviewed_diff.candidate_path
    )
    assert (
        approval.final_path
        == reviewed_diff.final_path
    )
    assert (
        approval.content_sha256
        == reviewed_diff.content_sha256
    )
    assert (
        approval.original_content_sha256
        == reviewed_diff.original_content_sha256
    )

def test_repository_rejects_approval_when_final_test_changed_after_review(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )
    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    final_path.write_text(
        (
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        encoding="utf-8",
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 2\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )

    final_path.write_text(
        (
            "def test_value():\n"
            "    assert VALUE == 3\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="候选 diff 已发生变化",
    ):
        repository.approve_diff(
            reviewed_diff=reviewed_diff,
        )

    assert final_path.read_text(
        encoding="utf-8",
    ) == (
        "def test_value():\n"
        "    assert VALUE == 3\n"
    )

def test_repository_rejects_commit_without_candidate_approval(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_value():\n"
            "    assert VALUE == 1\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )

    with pytest.raises(
        TypeError,
        match=(
            "approval 必须是 "
            "CandidateApproval"
        ),
    ):
        repository.commit_candidate(
            approval=reviewed_diff,
        )

    assert not reviewed_diff.final_path.exists()

def test_repository_commits_approved_new_candidate(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )
    content = (
        "def test_value():\n"
        "    assert VALUE == 1\n"
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=content,
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )

    committed_path = (
        repository.commit_candidate(
            approval=approval,
        )
    )

    assert committed_path == (
        reviewed_diff.final_path
    )
    assert committed_path.read_text(
        encoding="utf-8",
    ) == content
    assert candidate_path.read_text(
        encoding="utf-8",
    ) == content

def test_repository_does_not_overwrite_file_created_after_approval(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )
    candidate_content = (
        "def test_generated():\n"
        "    assert True\n"
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=candidate_content,
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    assert (
        reviewed_diff
        .original_content_sha256
        is None
    )

    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )

    final_path = reviewed_diff.final_path
    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    manual_content = (
        "def test_written_by_user():\n"
        "    assert True\n"
    )
    final_path.write_text(
        manual_content,
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="CandidateApproval 已过期",
    ):
        repository.commit_candidate(
            approval=approval,
        )

    assert final_path.read_text(
        encoding="utf-8",
    ) == manual_content
    assert list(
        final_path.parent.glob(
            f".{final_path.name}.*.tmp"
        )
    ) == []

def test_repository_commits_approved_change_to_existing_test(
    tmp_path,
):
    repository = CandidateRepository(
        tmp_path
    )

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )
    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_content = (
        "def test_value():\n"
        "    assert VALUE == 1\n"
    )
    final_path.write_text(
        original_content,
        encoding="utf-8",
    )

    candidate_content = (
        "def test_value():\n"
        "    assert VALUE == 2\n"
    )
    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=candidate_content,
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    assert reviewed_diff.change_type == (
        "modified"
    )
    assert (
        reviewed_diff
        .original_content_sha256
        == build_candidate_content_digest(
            original_content
        )
    )

    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )
    committed_path = (
        repository.commit_candidate(
            approval=approval,
        )
    )

    assert committed_path == final_path
    assert final_path.read_text(
        encoding="utf-8",
    ) == candidate_content
    assert candidate_path.read_text(
        encoding="utf-8",
    ) == candidate_content

def test_repository_preserves_files_when_atomic_replace_fails(
    tmp_path,
    monkeypatch,
):
    repository = CandidateRepository(
        tmp_path
    )

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )
    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_content = (
        "def test_original():\n"
        "    assert True\n"
    )
    final_path.write_text(
        original_content,
        encoding="utf-8",
    )

    candidate_content = (
        "def test_generated():\n"
        "    assert True\n"
    )
    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=candidate_content,
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )

    def fail_replace(
        self,
        target,
    ):
        raise OSError(
            "simulated replace failure"
        )

    monkeypatch.setattr(
        Path,
        "replace",
        fail_replace,
    )

    with pytest.raises(
        OSError,
        match="simulated replace failure",
    ):
        repository.commit_candidate(
            approval=approval,
        )

    assert final_path.read_text(
        encoding="utf-8",
    ) == original_content
    assert candidate_path.read_text(
        encoding="utf-8",
    ) == candidate_content
    assert list(
        final_path.parent.glob(
            f".{final_path.name}.*.tmp"
        )
    ) == []

def test_repository_rejects_candidate_changed_during_commit(
    tmp_path,
    monkeypatch,
):
    repository = CandidateRepository(
        tmp_path
    )
    approved_content = (
        "def test_approved():\n"
        "    assert True\n"
    )
    changed_content = (
        "def test_changed_later():\n"
        "    assert False\n"
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=approved_content,
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )
    final_path = reviewed_diff.final_path

    original_read_text = Path.read_text
    candidate_read_count = 0

    def changing_read_text(
        self,
        *args,
        **kwargs,
    ):
        nonlocal candidate_read_count

        if self == candidate_path:
            candidate_read_count += 1

            if candidate_read_count == 2:
                return changed_content

        return original_read_text(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "read_text",
        changing_read_text,
    )

    with pytest.raises(
        ValueError,
        match=(
            "候选测试在提交期间发生变化"
        ),
    ):
        repository.commit_candidate(
            approval=approval,
        )

    assert not final_path.exists()
    assert list(
        final_path.parent.glob(
            f".{final_path.name}.*.tmp"
        )
    ) == []

def test_repository_does_not_overwrite_file_created_during_commit(
    tmp_path,
    monkeypatch,
):
    repository = CandidateRepository(
        tmp_path
    )
    candidate_content = (
        "def test_generated():\n"
        "    assert True\n"
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=candidate_content,
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    assert (
        reviewed_diff
        .original_content_sha256
        is None
    )
    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )

    final_path = reviewed_diff.final_path
    manual_content = (
        "def test_created_during_commit():\n"
        "    assert True\n"
    )

    original_fsync = os.fsync

    def create_manual_file_then_fsync(
        file_descriptor,
    ):
        final_path.write_text(
            manual_content,
            encoding="utf-8",
        )
        return original_fsync(
            file_descriptor
        )

    monkeypatch.setattr(
        os,
        "fsync",
        create_manual_file_then_fsync,
    )

    with pytest.raises(
        ValueError,
        match=(
            "正式测试在提交期间发生变化"
        ),
    ):
        repository.commit_candidate(
            approval=approval,
        )

    assert final_path.read_text(
        encoding="utf-8",
    ) == manual_content
    assert list(
        final_path.parent.glob(
            f".{final_path.name}.*.tmp"
        )
    ) == []

def test_repository_does_not_overwrite_existing_test_changed_during_commit(
    tmp_path,
    monkeypatch,
):
    repository = CandidateRepository(
        tmp_path
    )

    final_path = (
        tmp_path
        / ".autotest"
        / "test_cases"
        / "unit"
        / "src"
        / "demo.py"
        / "test_demo.py"
    )
    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_content = (
        "def test_original():\n"
        "    assert True\n"
    )
    final_path.write_text(
        original_content,
        encoding="utf-8",
    )

    candidate_path = repository.save(
        spec_id="spec-demo-001",
        source_relative_path="src/demo.py",
        test_filename="test_demo.py",
        content=(
            "def test_generated():\n"
            "    assert True\n"
        ),
        generator_model="fake-model",
        template_version="v1",
    )

    reviewed_diff = repository.build_diff(
        candidate_path=candidate_path,
    )
    approval = repository.approve_diff(
        reviewed_diff=reviewed_diff,
    )

    manual_content = (
        "def test_changed_during_commit():\n"
        "    assert True\n"
    )
    original_fsync = os.fsync

    def change_final_then_fsync(
        file_descriptor,
    ):
        final_path.write_text(
            manual_content,
            encoding="utf-8",
        )
        return original_fsync(
            file_descriptor
        )

    monkeypatch.setattr(
        os,
        "fsync",
        change_final_then_fsync,
    )

    with pytest.raises(
        ValueError,
        match=(
            "正式测试在提交期间发生变化"
        ),
    ):
        repository.commit_candidate(
            approval=approval,
        )

    assert final_path.read_text(
        encoding="utf-8",
    ) == manual_content
    assert list(
        final_path.parent.glob(
            f".{final_path.name}.*.tmp"
        )
    ) == []