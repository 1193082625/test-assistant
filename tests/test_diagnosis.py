import pytest
# diagnosis 诊断
# inconclusive 非决定性的,无结果的
from core.models import (
    Diagnosis,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidence,
    DiagnosisEvidenceKind,
    DiagnosisLocation,
    DiagnosisAction,
    DiagnosisActionKind,
)

def test_diagnosis_categories_are_stable():
    assert {
        category.value
        for category in DiagnosisCategory
    } == {
        "product_defect",
        "test_defect",
        "infra_defect",
        "flaky",
        "inconclusive", # 非决定性的,无结果的
    }

def test_diagnosis_defaults_to_low_confidence_inconclusive():
    diagnosis = Diagnosis(
        summary="现有证据不足以判断失败原因",
    )

    assert diagnosis.category is DiagnosisCategory.INCONCLUSIVE
    assert diagnosis.confidence == DiagnosisConfidence.LOW
    assert diagnosis.evidence == ()
    assert diagnosis.locations == ()
    assert diagnosis.suggested_actions == ()

    assert diagnosis.to_dict() == {
        "category": "inconclusive",
        "confidence": "low",
        "summary": "现有证据不足以判断失败原因",
        "evidence": [],
        "locations": [],
        "suggested_actions": [],
    }

def test_diagnosis_serializes_evidence_and_location():
    evidence = DiagnosisEvidence(
        kind=DiagnosisEvidenceKind.EXECUTION,
        description="pytest 断言失败",
        source="pytest",
        details=(
            "exit_code=1",
            "test_demo.py::test_add",
        ),
    )
    location = DiagnosisLocation(
        path="test_demo.py",
        line=8,
        symbol="test_add",
    )

    diagnosis = Diagnosis(
        summary="测试执行失败，尚需进一步归因",
        evidence=(evidence,),
        locations=(location,),
    )

    assert diagnosis.to_dict() == {
        "category": "inconclusive",
        "confidence": "low",
        "summary": "测试执行失败，尚需进一步归因",
        "evidence": [
            {
                "kind": "execution",
                "description": "pytest 断言失败",
                "source": "pytest",
                "details": [
                    "exit_code=1",
                    "test_demo.py::test_add",
                ],
            }
        ],
        "locations": [
            {
                "path": "test_demo.py",
                "line": 8,
                "column": None,
                "symbol": "test_add",
            }
        ],
        "suggested_actions": [],
    }

@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "kind": DiagnosisEvidenceKind.EXECUTION,
                "description": "",
                "source": "pytest",
            },
            "DiagnosisEvidence description 不能为空",
        ),
        (
            {
                "kind": DiagnosisEvidenceKind.EXECUTION,
                "description": "pytest 断言失败",
                "source": "",
            },
            "DiagnosisEvidence source 不能为空",
        ),
        (
            {
                "kind": "execution",
                "description": "pytest 断言失败",
                "source": "pytest",
            },
            "DiagnosisEvidence kind 必须是 DiagnosisEvidenceKind",
        ),
        (
            {
                "kind": DiagnosisEvidenceKind.EXECUTION,
                "description": "pytest 断言失败",
                "source": "pytest",
                "details": ("exit_code=1", ""),
            },
            "DiagnosisEvidence details 必须只包含非空字符串",
        ),
    ],
)
def test_diagnosis_evidence_rejects_invalid_fields(
    kwargs,
    message,
):
    with pytest.raises(
        ValueError,
        match=message,
    ):
        DiagnosisEvidence(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "path": "",
            },
            "DiagnosisLocation path 不能为空",
        ),
        (
            {
                "path": "test_demo.py",
                "line": 0,
            },
            "DiagnosisLocation line 必须是正整数",
        ),
        (
            {
                "path": "test_demo.py",
                "column": -1,
            },
            "DiagnosisLocation column 必须是非负整数",
        ),
        (
            {
                "path": "test_demo.py",
                "symbol": "",
            },
            "DiagnosisLocation symbol 必须是非空字符串或 None",
        ),
    ],
)
def test_diagnosis_location_rejects_invalid_fields(
    kwargs,
    message,
):
    with pytest.raises(
        ValueError,
        match=message,
    ):
        DiagnosisLocation(**kwargs)

@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "summary": "",
            },
            "Diagnosis summary 不能为空",
        ),
        (
            {
                "summary": "无法判断",
                "category": "inconclusive",
            },
            "Diagnosis category 必须是 DiagnosisCategory",
        ),
        (
            {
                "summary": "无法判断",
                "confidence": "low",
            },
            "Diagnosis confidence 必须是 DiagnosisConfidence",
        ),
        (
            {
                "summary": "无法判断",
                "evidence": ("invalid",),
            },
            "Diagnosis evidence 必须只包含 DiagnosisEvidence",
        ),
        (
            {
                "summary": "无法判断",
                "locations": ("invalid",),
            },
            "Diagnosis locations 必须只包含 DiagnosisLocation",
        ),
        (
            {
                "summary": "无法判断",
                "suggested_actions": ("invalid",),
            },
            "Diagnosis suggested_actions 必须只包含 DiagnosisAction",
        ),
        (
            {
                "summary": "测试代码存在缺陷",
                "category": DiagnosisCategory.TEST_DEFECT,
                "confidence": DiagnosisConfidence.HIGH,
            },
            "非 INCONCLUSIVE 诊断必须包含证据",
        ),
    ],
)
def test_diagnosis_rejects_invalid_fields(
    kwargs,
    message,
):
    with pytest.raises(
        ValueError,
        match=message,
    ):
        Diagnosis(**kwargs)

def test_diagnosis_serializes_structured_actions():
    action = DiagnosisAction(
        kind=DiagnosisActionKind.REQUEST_CONFIRMATION,
        description="请用户确认业务预期",
    )

    diagnosis = Diagnosis(
        summary="契约证据不足",
        suggested_actions=(action,),
    )

    assert diagnosis.suggested_actions == (action,)
    assert diagnosis.to_dict()["suggested_actions"] == [
        {
            "kind": "request_confirmation",
            "description": "请用户确认业务预期",
        }
    ]

def test_diagnosis_round_trips_through_dict():
    diagnosis = Diagnosis(
        summary="测试文件存在语法问题",
        category=DiagnosisCategory.TEST_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=(
            DiagnosisEvidence(
                kind=(
                    DiagnosisEvidenceKind
                    .TEST_VALIDATION
                ),
                description="Python AST 解析失败",
                source="candidate_validator",
                details=(
                    "status=syntax_error",
                ),
            ),
        ),
        locations=(
            DiagnosisLocation(
                path="test_demo.py",
                line=4,
                column=12,
                symbol="test_add",
            ),
        ),
        suggested_actions=(
            DiagnosisAction(
                kind=DiagnosisActionKind.FIX_TEST,
                description="修复测试文件的 Python 语法",
            ),
        ),
    )

    payload = diagnosis.to_dict()
    restored = Diagnosis.from_dict(payload)

    assert restored == diagnosis
    assert restored is not diagnosis

@pytest.mark.parametrize(
    "category",
    list(DiagnosisCategory),
)
def test_every_diagnosis_category_round_trips(
    category,
):
    evidence = DiagnosisEvidence(
        kind=DiagnosisEvidenceKind.EXECUTION,
        description="用于验证分类序列化",
        source="test",
    )

    diagnosis = Diagnosis(
        summary=f"诊断分类：{category.value}",
        category=category,
        confidence=DiagnosisConfidence.MEDIUM,
        evidence=(evidence,),
        suggested_actions=(
            DiagnosisAction(
                kind=DiagnosisActionKind.RERUN,
                description="重新运行目标测试",
            ),
        ),
    )

    restored = Diagnosis.from_dict(
        diagnosis.to_dict()
    )

    assert restored == diagnosis
    assert restored.category is category

@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "kind": "rerun",
                "description": "重新运行测试",
            },
            "DiagnosisAction kind 必须是 DiagnosisActionKind",
        ),
        (
            {
                "kind": DiagnosisActionKind.RERUN,
                "description": "",
            },
            "DiagnosisAction description 不能为空",
        ),
    ],
)
def test_diagnosis_action_rejects_invalid_fields(
    kwargs,
    message,
):
    with pytest.raises(
        ValueError,
        match=message,
    ):
        DiagnosisAction(**kwargs)