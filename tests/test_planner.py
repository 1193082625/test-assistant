from dataclasses import FrozenInstanceError

import pytest

from core.models import (
    PlannerResult,
    PlannerStatus,
    TestSpec as Spec,
    ExpectationEvidence,
    EvidenceKind,
    EvidenceStrength,
)


def make_spec() -> Spec:
    evidence = ExpectationEvidence(
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        strength=EvidenceStrength.MEDIUM,
        source_path="demo.py",
        source_line=2,
    )
    return Spec(
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
        evidence=[evidence],
    )

def test_rejects_non_string_errors():
    """测试不合法的 errors"""
    with pytest.raises(
        ValueError,
        match=(
            "errors 必须只包含字符串"
        ),
    ):
        PlannerResult(
            status=PlannerStatus.EMPTY,
            errors=(123,)
        )

def test_accepts_empty_result_without_spec():
    result = PlannerResult(
        status=PlannerStatus.EMPTY,
    )

    assert result.status is PlannerStatus.EMPTY
    assert result.errors == ()
    assert result.spec is None

def test_rejects_mutable_errors_collection():
    with pytest.raises(
        ValueError,
        match="errors 必须是元组",
    ):
        PlannerResult(
            status=PlannerStatus.INVALID,
            errors=["模型输出非法"]
        )

def test_accepts_success_result_with_spec():
    spec = make_spec()
    result = PlannerResult(
        status=PlannerStatus.SUCCESS,
        spec=spec,
        errors=(),
    )

    assert result.status is PlannerStatus.SUCCESS
    assert result.spec is spec

def test_rejects_success_result_without_spec():
    with pytest.raises(
        ValueError,
        match=(
            "spec 不能为空"
        ),
    ):
        PlannerResult(
            status=PlannerStatus.SUCCESS,
            spec=None,
            errors=(),
        )

def test_accepts_invalid_result_with_errors():
    result = PlannerResult(
        status=PlannerStatus.INVALID,
        errors=(
            "模型输出不是合法 JSON",
        ),
    )

    assert result.status is PlannerStatus.INVALID
    assert result.spec is None
    assert result.errors == (
        "模型输出不是合法 JSON",
    )

def test_rejects_invalid_result_without_errors():
    with pytest.raises(
        ValueError,
        match="校验失败缺少 errors",
    ):
        PlannerResult(
            status=PlannerStatus.INVALID,
        )

def test_rejects_empty_result_with_spec():
    spec = make_spec()
    with pytest.raises(
        ValueError,
        match=(
            "空状态下不应该有 spec"
        ),
    ):
        PlannerResult(
            status=PlannerStatus.EMPTY,
            spec=spec
        )

def test_rejects_invalid_result_with_spec():
    spec = make_spec()
    with pytest.raises(
        ValueError,
        match=(
            "校验失败 spec 应该为空"
        ),
    ):
        PlannerResult(
            status=PlannerStatus.INVALID,
            spec=spec,
            errors=(
                "模型输出非法",
            ),
        )

def test_rejects_success_result_with_errors():
    spec = make_spec()
    with pytest.raises(
        ValueError,
        match=(
            "成功状态下 errors 必须为空"
        ),
    ):
        PlannerResult(
            status=PlannerStatus.SUCCESS,
            spec=spec,
            errors=(
                "模型输出非法",
            ),
        )

@pytest.mark.parametrize(
    "error",
    [
        "",
        "   ",
    ],
)
def test_rejects_blank_error(error):
    with pytest.raises(
            ValueError,
            match=(
                    "errors 中不应该有空字符串"
            ),
    ):
        PlannerResult(
            status=PlannerStatus.INVALID,
            errors=(error,)
        )

def test_rejects_non_planner_status():
    with pytest.raises(
        ValueError,
        match="status 必须是 PlannerStatus",
    ):
        PlannerResult(
            status="error",
            errors=()
        )
def test_rejects_non_test_spec_value():
    with pytest.raises(
        ValueError,
        match=(
            "不支持的 Spec"
        ),
    ):
        PlannerResult(
            status=PlannerStatus.SUCCESS,
            spec={
                "error": "error",
            },
        )

def test_planner_result_is_immutable():
    result = PlannerResult(
        status=PlannerStatus.EMPTY,
    )

    with pytest.raises(FrozenInstanceError):
        result.status = PlannerStatus.INVALID