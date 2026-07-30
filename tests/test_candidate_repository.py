import pytest
import json
from pathlib import Path
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