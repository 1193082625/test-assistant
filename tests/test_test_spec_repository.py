import json
import pytest
from core.models import (
    TestSpec as Spec,
    TestSpecStatus as SpecStatus
)
from core.repositories.test_spec import TestSpecRepository as SpecRepository

def test_repository_saves_and_loads_versioned_spec(tmp_path):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    spec = Spec(
        id="spec-demo-add-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={
            "a": 1,
            "b": 2,
        },
        action="调用 add(a, b)",
        expected={
            "return": 3
        }
    )

    saved_path = repository.save(spec)

    expected_path = (
        tmp_path / ".autotest" / "plans" / "spec-demo-add-001.json"
    )
    assert saved_path == expected_path
    assert expected_path.is_file()

    payload = json.loads(expected_path.read_text(encoding="utf-8"))

    assert payload == {
        "version": 1,
        "spec": spec.to_dict()
    }
    restored = repository.get("spec-demo-add-001")
    assert restored == spec

@pytest.mark.parametrize(
    "unsafe_spec_id",
    [
        "../escape",
        "folder/spec",
        r"folder\spec",
        ".",
        ""
    ],
)
def test_repository_rejects_unsafe_spec_id(
        tmp_path,
        unsafe_spec_id
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    with pytest.raises(
        ValueError,
        match="TestSpec id 包含不安全字符"
    ):
        repository.get(unsafe_spec_id)


def test_repository_rejects_unsupported_version(
    tmp_path,
):
    """测试 未来升级 JSON 格式后，旧代码不会把未知结构错误解释成当前 TestSpec"""
    plans_path = (
        tmp_path
        / ".autotest"
        / "plans"
    )
    plans_path.mkdir(parents=True)

    spec_path = (
        plans_path
        / "spec-demo-add-001.json"
    )
    spec_path.write_text(
        json.dumps(
            {
                "version": 999,
                "spec": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match=(
            "不支持的 TestSpec "
            "存储版本: 999"
        ),
    ):
        repository.get(
            "spec-demo-add-001"
        )

def test_save_failure_preserves_existing_spec(
    tmp_path,
    monkeypatch,
):
    """覆盖失败时，旧 TestSpec 不能损坏"""
    repository = SpecRepository(
        project_root=tmp_path,
    )

    original = Spec(
        id="spec-demo-add-001",
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
    )
    repository.save(original)

    updated = Spec(
        id="spec-demo-add-001",
        target_symbol="demo.add",
        behavior="计算两个整数之和",
        arrange={
            "a": 2,
            "b": 3,
        },
        action="调用 add(a, b)",
        expected={
            "return": 5,
        },
    )

    def fail_replace(source, target):
        raise OSError(
            "simulated replace failure"
        )

    monkeypatch.setattr(
        "core.repositories.test_spec."
        "os.replace",
        fail_replace,
    )

    with pytest.raises(
        OSError,
        match="simulated replace failure",
    ):
        repository.save(updated)

    assert repository.get(
        "spec-demo-add-001"
    ) == original

    temporary_files = list(
        repository.plans_path.glob(
            ".spec-demo-add-001.*.tmp"
        )
    )
    assert temporary_files == []

def test_approve_is_persisted_and_idempotent(
    tmp_path,
    monkeypatch,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    proposed = Spec(
        id="spec-demo-add-001",
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
    )
    repository.save(proposed)

    approved = repository.approve(
        "spec-demo-add-001"
    )

    assert (
        approved.status
        is SpecStatus.APPROVED
    )
    assert repository.get(
        "spec-demo-add-001"
    ) == approved

    def forbidden_save(spec):
        raise AssertionError(
            "重复批准不应再次写入"
        )

    monkeypatch.setattr(
        repository,
        "save",
        forbidden_save,
    )

    repeated = repository.approve(
        "spec-demo-add-001"
    )

    assert repeated == approved

def test_reject_is_persisted_and_idempotent(
    tmp_path,
    monkeypatch,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    proposed = Spec(
        id="spec-demo-add-001",
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
    )
    repository.save(proposed)

    rejected = repository.reject(
        "spec-demo-add-001"
    )

    assert (
        rejected.status
        is SpecStatus.REJECTED
    )
    assert repository.get(
        "spec-demo-add-001"
    ) == rejected

    def forbidden_save(spec):
        raise AssertionError(
            "重复拒绝不应再次写入"
        )

    monkeypatch.setattr(
        repository,
        "save",
        forbidden_save,
    )

    repeated = repository.reject(
        "spec-demo-add-001"
    )

    assert repeated == rejected

@pytest.mark.parametrize(
    (
        "initial_status",
        "operation_name",
        "message",
    ),
    [
        (
            SpecStatus.APPROVED,
            "reject",
            "已批准的 TestSpec 不能拒绝",
        ),
        (
            SpecStatus.REJECTED,
            "approve",
            "已拒绝的 TestSpec 不能批准",
        ),
    ],
)
def test_review_decision_cannot_be_reversed(
    tmp_path,
    initial_status,
    operation_name,
    message,
):
    repository = SpecRepository(
        project_root=tmp_path,
    )
    reviewed = Spec(
        id="spec-demo-add-001",
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
        status=initial_status,
    )
    repository.save(reviewed)

    operation = getattr(
        repository,
        operation_name,
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        operation(
            "spec-demo-add-001"
        )

    assert repository.get(
        "spec-demo-add-001"
    ) == reviewed

def test_list_all_returns_specs_in_stable_id_order(tmp_path):
    repository = SpecRepository(
        project_root=tmp_path,
    )

    second = Spec(
        id="spec-demo-002",
        target_symbol="demo.subtract",
        behavior="计算两个整数之差",
        arrange={
            "a": 3,
            "b": 1,
        },
        action="调用 subtract(a, b)",
        expected={
            "return": 2,
        }
    )

    first = Spec(
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
        }
    )

    # 故意按照相反顺序保存
    repository.save(second)
    repository.save(first)

    specs = repository.list_all()

    assert [spec.id for spec in specs] == ["spec-demo-001", "spec-demo-002"]
    assert specs == [first, second]

def test_list_all_returns_empty_for_missing_directory(tmp_path):
    repository = SpecRepository(
        project_root=tmp_path,
    )

    assert repository.list_all() == []

def test_repository_rejects_invalid_root_format(tmp_path):
    plans_path = (tmp_path / ".autotest" / "plans")
    plans_path.mkdir(parents=True, exist_ok=True)

    (plans_path / "spec-demo-001.json").write_text(
        "[]\n",
        encoding="utf-8",
    )
    repository = SpecRepository(
        project_root=tmp_path,
    )
    with pytest.raises(
        ValueError,
        match=(
            "TestSpec 存储格式无效: "
            "根节点必须是字典"
        ),
    ):
        repository.get("spec-demo-001")

def test_repository_rejects_missing_spec_payload(tmp_path):
    plans_path = (tmp_path / ".autotest" / "plans")
    plans_path.mkdir(parents=True, exist_ok=True)

    (plans_path / "spec-demo-001.json").write_text(
        json.dumps(
            {
                "version": 1,
            }
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match=(
            "TestSpec 存储格式无效: "
            "缺少 spec 字段"
        ),
    ):
        repository.get("spec-demo-001")

def test_repository_uses_test_spec_model_to_validate_spec_data(tmp_path):
    """Repository 使用 TestSpec 模型校验 spec 数据"""
    plans_path = (tmp_path / ".autotest" / "plans")
    plans_path.mkdir(parents=True, exist_ok=True)

    (plans_path / "spec-demo-001.json").write_text(
        json.dumps(
            {
                "version": 1,
                "spec": []
            }
        ),
        encoding="utf-8",
    )

    repository = SpecRepository(
        project_root=tmp_path,
    )

    with pytest.raises(
        ValueError,
        match=(
            "TestSpec 持久化数据必须是字典"
        )
    ):
        repository.get("spec-demo-001")