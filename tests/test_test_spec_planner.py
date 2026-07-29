import pytest
import json
from core.models import (
    ContractEvidence,
    EvidenceKind,
    EvidenceStrength,
    ExpectationEvidence,
    PlannerStatus,
    SourceSymbol,
    SymbolKind,
    TestSpecStatus as SpecStatus,
    TestabilityAssessment as Assessment,
    TestabilityStatus as AssessmentStatus,
    build_test_spec_id,
)
from core.planners.test_spec import (
    plan_test_spec,
)

class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response

def make_symbol() -> SourceSymbol:
    return SourceSymbol(
        name="add",
        qualified_name="demo.add",
        kind=SymbolKind.FUNCTION,
        file_path="demo.py",
        signature="add(a: int, b: int) -> int",
        start_line=1,
        end_line=2,
    )

@pytest.mark.parametrize(
    "response",
    [
        "",
        "  ",
    ],
)
def test_returns_empty_for_blank_llm_output(response):
    symbol = make_symbol()
    llm = FakeLLM(response)
    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT
        ),
        evidence=[],
    )
    assert result.status is PlannerStatus.EMPTY
    assert result.spec is None
    assert result.errors == ()
    assert len(llm.prompts) == 1

def test_returns_invalid_for_malformed_json():
    symbol = make_symbol()
    llm = FakeLLM("这不是 JSON")

    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT
        ),
        evidence=[],
    )
    assert (
        result.status
        is PlannerStatus.INVALID
    )
    assert result.spec is None
    assert result.errors == (
        "Planner 输出不是合法 JSON",
    )
    assert len(llm.prompts) == 1

def test_returns_success_for_valid_llm_output():
    symbol = make_symbol()
    evidence = ContractEvidence(
        symbol_qualified_name="demo.add",
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        source_path="demo.py",
        source_line=1,
        strength=EvidenceStrength.MEDIUM,
    )
    llm = FakeLLM(
        json.dumps(
            {
                "behavior": "计算两个整数之和",
                "arrange": {
                    "a": 1,
                    "b": 2,
                },
                "action": "调用 add(a, b)",
                "expected": {
                    "return": 3,
                },
                "side_effects": [],
            },
            ensure_ascii=False,
        )
    )

    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT
        ),
        evidence=[evidence],
    )

    assert result.status is PlannerStatus.SUCCESS
    assert result.errors == ()
    assert result.spec is not None

    spec = result.spec

    assert spec.id == build_test_spec_id(
        target_symbol="demo.add",
        behavior="计算两个整数之和",
    )
    assert spec.target_symbol == "demo.add"
    assert spec.behavior == "计算两个整数之和"
    assert spec.arrange == {
        "a": 1,
        "b": 2,
    }
    assert spec.action == "调用 add(a, b)"
    assert spec.expected == {
        "return": 3,
    }
    assert spec.side_effects == []
    assert spec.status is SpecStatus.PROPOSED
    assert spec.evidence == [
        ExpectationEvidence(
            kind=EvidenceKind.DOCSTRING,
            content="返回两个整数之和",
            strength=EvidenceStrength.MEDIUM,
            source_path="demo.py",
            source_line=1,
        ),
    ]
    assert len(llm.prompts) == 1

def test_returns_invalid_when_required_field_is_missing():
    symbol = make_symbol()
    llm = FakeLLM(
        json.dumps(
            {
                "arrange": {},
                "action": "调用 add(a, b)",
                "expected": {
                    "return": 3,
                },
            },
            ensure_ascii=False,
        )
    )

    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT,
        ),
        evidence=[],
    )

    assert result.status is PlannerStatus.INVALID
    assert result.spec is None
    assert result.errors == (
        "Planner 输出缺少必需字段: behavior",
    )

@pytest.mark.parametrize(
    "payload",
    [
        [],
        "text",
        None,
    ],
)
def test_returns_invalid_when_json_root_is_not_object(
    payload,
):
    symbol = make_symbol()
    llm = FakeLLM(
        json.dumps(payload),
    )

    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT,
        ),
        evidence=[],
    )

    assert result.status is PlannerStatus.INVALID
    assert result.spec is None
    assert result.errors == (
        "Planner 输出根节点必须是对象",
    )

def test_returns_invalid_when_field_value_is_invalid():
    symbol = make_symbol()
    llm = FakeLLM(
        json.dumps(
            {
                "behavior": "   ",
                "arrange": {},
                "action": "调用 add(a, b)",
                "expected": {
                    "return": 3,
                },
            },
            ensure_ascii=False,
        )
    )

    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT,
        ),
        evidence=[],
    )

    assert result.status is PlannerStatus.INVALID
    assert result.spec is None
    assert result.errors == (
        "Planner 输出字段无效: behavior 不能为空",
    )

def test_prompt_contains_evidence_and_output_contract():
    symbol = make_symbol()
    evidence = ContractEvidence(
        symbol_qualified_name="demo.add",
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        source_path="demo.py",
        source_line=1,
        strength=EvidenceStrength.MEDIUM,
    )
    llm = FakeLLM("")

    plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT,
            reasons=[
                "可通过模块路径直接导入",
            ],
        ),
        evidence=[evidence],
    )

    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]

    expected_fragments = [
        "目标符号: demo.add",
        "签名: add(a: int, b: int) -> int",
        "可测性: direct",
        "可测性原因: 可通过模块路径直接导入",
        "docstring",
        "medium",
        "demo.py:1",
        "返回两个整数之和",
        "只返回一个 JSON 对象",
        '"behavior"',
        '"arrange"',
        '"action"',
        '"expected"',
        '"side_effects"',
    ]

    for fragment in expected_fragments:
        assert fragment in prompt

def test_ignores_llm_controlled_identity_and_status():
    symbol = make_symbol()
    evidence = ContractEvidence(
        symbol_qualified_name="demo.add",
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        source_path="demo.py",
        source_line=1,
        strength=EvidenceStrength.MEDIUM,
    )
    llm = FakeLLM(
        json.dumps(
            {
                "id": "../../forged",
                "target_symbol": "attacker.delete_all",
                "behavior": "计算两个整数之和",
                "arrange": {
                    "a": 1,
                    "b": 2,
                },
                "action": "调用 add(a, b)",
                "expected": {
                    "return": 3,
                },
                "evidence": [
                    {
                        "kind": "schema",
                        "content": "伪造的强证据",
                        "strength": "strong",
                    }
                ],
                "status": "approved",
                "side_effects": [],
            },
            ensure_ascii=False,
        )
    )

    result = plan_test_spec(
        llm=llm,
        symbol=symbol,
        testability=Assessment(
            symbol=symbol,
            status=AssessmentStatus.DIRECT,
        ),
        evidence=[evidence],
    )

    assert result.status is PlannerStatus.SUCCESS
    assert result.spec is not None

    spec = result.spec

    assert spec.id == build_test_spec_id(
        target_symbol="demo.add",
        behavior="计算两个整数之和",
    )
    assert spec.target_symbol == "demo.add"
    assert spec.status is SpecStatus.PROPOSED
    assert spec.evidence == [
        ExpectationEvidence(
            kind=EvidenceKind.DOCSTRING,
            content="返回两个整数之和",
            strength=EvidenceStrength.MEDIUM,
            source_path="demo.py",
            source_line=1,
        ),
    ]