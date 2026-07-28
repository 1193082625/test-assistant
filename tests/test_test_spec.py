import pytest
from core.models import (
    TestSpecStatus as SpecStatus,
    EvidenceKind,
    EvidenceStrength,
    ExpectationEvidence,
    TestSpec as Spec,
)

def test_test_spec_status_has_stable_machine_values():
    assert SpecStatus.PROPOSED.value == "proposed"
    assert SpecStatus.APPROVED.value == "approved"
    assert SpecStatus.REJECTED.value == "rejected"

def test_test_spec_status_rejects_unknown_value():
    with pytest.raises(ValueError):
        SpecStatus("pending")

def test_test_spec_records_test_intent():
    evidence = ExpectationEvidence(
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        strength=EvidenceStrength.MEDIUM,
        source_path="demo.py",
        source_line=2,
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
        },
        evidence=[evidence],
    )

    assert spec.id == "spec-demo-add-001"
    assert spec.target_symbol == "demo.add"
    assert spec.behavior == "计算两个整数之和"
    assert spec.arrange == {
        "a": 1,
        "b": 2,
    }
    assert spec.action == "调用 add(a, b)"
    assert spec.expected == {
        "return": 3
    }
    assert spec.evidence == [evidence]
    assert spec.side_effects == []
    assert spec.status is SpecStatus.PROPOSED

    assert (
        spec.expectation_strength
        is EvidenceStrength.MEDIUM
    )
    assert spec.is_weak_inference is False
    assert spec.can_support_product_defect is False

def test_expectation_evidence_records_basis():
    evidence = ExpectationEvidence(
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        strength=EvidenceStrength.MEDIUM,
        source_path="demo.py",
        source_line=2,
    )

    assert evidence.kind == EvidenceKind.DOCSTRING
    assert evidence.content == "返回两个整数之和"
    assert evidence.strength == EvidenceStrength.MEDIUM
    assert evidence.source_path == "demo.py"
    assert evidence.source_line == 2

def test_expected_without_evidence_is_weak_inference():
    spec = Spec(
        id="spec-demo-add-002",
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

    assert spec.expectation_strength is EvidenceStrength.WEAK
    assert spec.is_weak_inference is True

def test_strong_evidence_makes_expectation_strong():
    evidence = ExpectationEvidence(
        kind=EvidenceKind.SCHEMA,
        content="#/components/schemas/User",
        strength=EvidenceStrength.STRONG,
        source_path="openapi.yaml",
        source_line=18,
    )
    spec = Spec(
        id="spec-user-create-001",
        target_symbol="api.create_user",
        behavior="创建符合 Schema 的用户",
        arrange={
            "name": "Alice",
        },
        action="调用 create_user",
        expected={
            "status": 201,
        },
        evidence=[evidence],
    )

    assert (
        spec.expectation_strength
        is EvidenceStrength.STRONG
    )
    assert spec.is_weak_inference is False
    assert spec.can_support_product_defect is True

@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        (
            "id",
            "   ",
            "TestSpec id 不能为空",
        ),
        (
            "target_symbol",
            "",
            "TestSpec target_symbol 不能为空",
        ),
    ]
)
def test_test_spec_rejects_blank_identity_fields(
        field_name,
        invalid_value,
        message,
):
    values = {
        "id": "spec-demo-add-001",
        "target_symbol": "demo.add",
        "behavior": "计算两个整数之和",
        "arrange": {
            "a": 1,
            "b": 2,
        },
        "action": "调用 add(a, b)",
        "expected": {
                "return": 3
        },
        field_name: invalid_value
    }

    with pytest.raises(ValueError, match=message):
        Spec(**values)

@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        (
            "behavior",
            "   ",
            "TestSpec behavior 不能为空",
        ),
        (
            "action",
            "",
            "TestSpec action 不能为空",
        ),
        (
            "expected",
            {},
            "TestSpec expected 不能为空",
        ),
    ]
)
def test_test_spec_rejects_empty_test_intent(
        field_name,
        invalid_value,
        message,
):
    values = {
        "id": "spec-demo-add-001",
        "target_symbol": "demo.add",
        "behavior": "计算两个整数之和",
        "arrange": {
            "a": 1,
            "b": 2,
        },
        "action": "调用 add(a, b)",
        "expected": {
            "return": 3
        }
    }

    values[field_name] = invalid_value
    with pytest.raises(ValueError, match=message):
        Spec(**values)

@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        (
            "arrange",
            [],
            "TestSpec arrange 必须是字典",
        ),
        (
            "evidence",
            ["docstring"],
            (
                "TestSpec evidence 必须只包含 "
                "ExpectationEvidence"
            ),
        ),
        (
            "side_effects",
            ["filesystem", 123],
            (
                "TestSpec side_effects "
                "必须只包含字符串"
            ),
        ),
        (
            "status",
            "approved",
            (
                "TestSpec status 必须是 "
                "TestSpecStatus"
            ),
        ),
    ],
)
def test_test_spec_rejects_invalid_field_types(
    field_name,
    invalid_value,
    message,
):
    values = {
        "id": "spec-demo-add-001",
        "target_symbol": "demo.add",
        "behavior": "计算两个整数之和",
        "arrange": {
            "a": 1,
            "b": 2,
        },
        "action": "调用 add(a, b)",
        "expected": {
            "return": 3,
        },
        "evidence": [],
        "side_effects": [],
        "status": SpecStatus.PROPOSED,
    }
    values[field_name] = invalid_value

    with pytest.raises(
        ValueError,
        match=message,
    ):
        Spec(**values)


def test_test_spec_serializes_to_machine_values():
    evidence = ExpectationEvidence(
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        strength=EvidenceStrength.MEDIUM,
        source_path="demo.py",
        source_line=2,
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
        },
        evidence=[evidence],
        side_effects=["filesystem"]
    )

    assert spec.to_dict() == {
        "id": "spec-demo-add-001",
        "target_symbol": "demo.add",
        "behavior": "计算两个整数之和",
        "arrange": {
            "a": 1,
            "b": 2,
        },
        "action": "调用 add(a, b)",
        "expected": {
            "return": 3
        },
        "evidence": [
            {
                "kind": "docstring",
                "content": "返回两个整数之和",
                "strength": "medium",
                "source_path": "demo.py",
                "source_line": 2,
            }
        ],
        "side_effects": ["filesystem"],
        "status": "proposed",
        "expectation_strength": "medium",
        "is_weak_inference": False,
        "can_support_product_defect": False,
    }

def test_test_spec_dict_round_trip():
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
            "return": 3
        },
        evidence=[
            ExpectationEvidence(
                kind=EvidenceKind.DOCSTRING,
                content="返回两个整数之和",
                strength=EvidenceStrength.MEDIUM,
                source_path="demo.py",
                source_line=2,
            )
        ],
        side_effects=["filesystem"],
        status=SpecStatus.APPROVED,
    )

    restored = Spec.from_dict(
        original.to_dict(),
    )

    assert restored == original

@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        (
            "id",
            None,
            "TestSpec id 不能为空",
        ),
        (
            "side_effects",
            [123],
            (
                "TestSpec side_effects "
                "必须只包含字符串"
            ),
        ),
    ],
)
def test_test_spec_from_dict_does_not_coerce_types(
    field_name,
    invalid_value,
    message,
):
    data = {
        "id": "spec-demo-add-001",
        "target_symbol": "demo.add",
        "behavior": "计算两个整数之和",
        "arrange": {
            "a": 1,
            "b": 2,
        },
        "action": "调用 add(a, b)",
        "expected": {
            "return": 3,
        },
        "evidence": [],
        "side_effects": [],
        "status": "proposed",
    }
    data[field_name] = invalid_value

    with pytest.raises(
        ValueError,
        match=message,
    ):
        Spec.from_dict(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        (
            "kind",
            "docstring",
            (
                "ExpectationEvidence kind "
                "必须是 EvidenceKind"
            ),
        ),
        (
            "content",
            "   ",
            (
                "ExpectationEvidence content "
                "不能为空"
            ),
        ),
        (
            "strength",
            "medium",
            (
                "ExpectationEvidence strength "
                "必须是 EvidenceStrength"
            ),
        ),
        (
            "source_path",
            "",
            (
                "ExpectationEvidence source_path "
                "不能为空"
            ),
        ),
        (
            "source_line",
            0,
            (
                "ExpectationEvidence source_line "
                "必须是正整数"
            ),
        ),
    ],
)
def test_expectation_evidence_rejects_invalid_fields(
    field_name,
    invalid_value,
    message,
):
    values = {
        "kind": EvidenceKind.DOCSTRING,
        "content": "返回两个整数之和",
        "strength": EvidenceStrength.MEDIUM,
        "source_path": "demo.py",
        "source_line": 2,
    }
    values[field_name] = invalid_value

    with pytest.raises(
        ValueError,
        match=message,
    ):
        ExpectationEvidence(**values)

@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        (
            "content",
            None,
            (
                "ExpectationEvidence content "
                "不能为空"
            ),
        ),
        (
            "source_line",
            "2",
            (
                "ExpectationEvidence source_line "
                "必须是正整数"
            ),
        ),
    ],
)
def test_expectation_evidence_from_dict_does_not_coerce(
    field_name,
    invalid_value,
    message,
):
    data = {
        "kind": "docstring",
        "content": "返回两个整数之和",
        "strength": "medium",
        "source_path": "demo.py",
        "source_line": 2,
    }
    data[field_name] = invalid_value

    with pytest.raises(
        ValueError,
        match=message,
    ):
        ExpectationEvidence.from_dict(data)

def test_current_implementation_evidence_is_weak():
    evidence = ExpectationEvidence(
        kind=EvidenceKind.CURRENT_IMPLEMENTATION,
        content="当前实现返回 a + b",
        strength=EvidenceStrength.WEAK,
        source_path="demo.py",
        source_line=2,
    )

    spec = Spec(
        id="spec-demo-add-regression",
        target_symbol="demo.add",
        behavior="保持当前加法行为",
        arrange={
            "a": 1,
            "b": 2,
        },
        action="调用 add(a, b)",
        expected={
            "return": 3,
        },
        evidence=[evidence],
    )

    assert (
        spec.expectation_strength
        is EvidenceStrength.WEAK
    )
    assert spec.is_weak_inference is True
    assert spec.can_support_product_defect is False

def test_current_implementation_cannot_be_medium_evidence():
    with pytest.raises(
        ValueError,
        match=(
            "当前实现证据的强度必须是 weak"
        ),
    ):
        ExpectationEvidence(
            kind=EvidenceKind.CURRENT_IMPLEMENTATION,
            content="当前实现返回 a + b",
            strength=EvidenceStrength.MEDIUM,
            source_path="demo.py",
            source_line=2,
        )

@pytest.mark.parametrize(
    ("model", "message"),
    [
        (
            ExpectationEvidence,
            (
                "ExpectationEvidence "
                "持久化数据必须是字典"
            ),
        ),
        (
            Spec,
            (
                "TestSpec 持久化数据必须是字典"
            ),
        ),
    ],
)
def test_models_reject_non_mapping_persisted_data(
    model,
    message,
):
    with pytest.raises(
        ValueError,
        match=message,
    ):
        model.from_dict([])