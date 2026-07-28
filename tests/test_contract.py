
from core.models import (
    ContractEvidence,
    EvidenceKind,
    EvidenceStrength,
    TestIndex as Index,
    TestIndexEntry as IndexEntry,
)
from core.analyzers.contract import (
    extract_python_contract_evidence,
    extract_existing_test_evidence,
    extract_schema_reference_evidence,
)

def test_contract_evidence_records_source_and_strength():
    evidence = ContractEvidence(
        symbol_qualified_name="demo.add",
        kind=EvidenceKind.DOCSTRING,
        content="返回两个整数之和",
        source_path="demo.py",
        source_line=2,
        strength=EvidenceStrength.MEDIUM
    )

    assert evidence.symbol_qualified_name == "demo.add" # 证据属于哪个源码符号
    assert evidence.kind.value == "docstring" # 证据来自哪里
    assert evidence.content == "返回两个整数之和" # 证据实际表达了什么
    assert evidence.source_path == "demo.py" # 证据可追踪到哪里
    assert evidence.source_line == 2 # 证据可追踪到第几行
    assert evidence.strength.value == "medium" # 生成器应该多大程度相信它

def test_extracts_function_docstring_as_contract_evidence(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a: int, b: int) -> int:\n"
            '    """返回两个整数之和。"""\n'
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    evidence = extract_python_contract_evidence(
        file_path=str(source_path),
        module_name="demo",
    )

    docstring_evidence = [
        item
        for item in evidence
        if item.kind is EvidenceKind.DOCSTRING
    ]

    assert docstring_evidence == [
        ContractEvidence(
            symbol_qualified_name="demo.add",
            kind=EvidenceKind.DOCSTRING,
            content="返回两个整数之和。",
            source_path=str(source_path),
            source_line=2,
            strength=EvidenceStrength.MEDIUM
        )
    ]

# extract 提炼，提取
# hint 提示，暗示
# contract 契约，约定
# evidence 证据，证明
def test_extracts_type_hints_as_contract_evidence(tmp_path):
    """测试提炼类型提示作为契约证明"""
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def parse(\n"
            "    value: str,\n"
            "    limit: int = 10,\n"
            ") -> list[str]:\n"
            "    return [value][:limit]\n"
        ),
        encoding="utf-8",
    )

    evidence = extract_python_contract_evidence(
        file_path=str(source_path),
        module_name="demo",
    )

    assert evidence == [
        ContractEvidence(
            symbol_qualified_name="demo.parse",
            kind=EvidenceKind.TYPE_HINT,
            content=(
                "parse(value: str, "
                "limit: int=10) -> list[str]"
            ),
            source_path = str(source_path),
            source_line=1,
            strength=EvidenceStrength.MEDIUM
        )
    ]

def test_converts_existing_test_index_to_strong_evidence():
    index = Index(
        entries=[
            IndexEntry(
                source_qualified_name="demo.add",
                test_qualified_name="tests.test_demo.test_add",
                test_file_path="tests/test_demo.py",
                test_line=3
            )
        ]
    )

    evidence = extract_existing_test_evidence(index)

    assert evidence == [
        ContractEvidence(
            symbol_qualified_name="demo.add",
            kind=EvidenceKind.EXISTING_TEST,
            content="tests.test_demo.test_add",
            source_path="tests/test_demo.py",
            source_line=3,
            strength=EvidenceStrength.STRONG
        )
    ]

def test_converts_schema_reference_to_strong_evidence():
    evidence = extract_schema_reference_evidence(
        symbol_qualified_name="api.create_user",
        schema_path="openapi.yaml",
        schema_reference="#/components/schemas/User",
        source_line=18
    )

    assert evidence == ContractEvidence(
        symbol_qualified_name="api.create_user",
        kind=EvidenceKind.SCHEMA,
        content="#/components/schemas/User",
        source_path="openapi.yaml",
        source_line=18,
        strength=EvidenceStrength.STRONG # schema 是明确的结构化契约，因此强度为 STRONG
    )