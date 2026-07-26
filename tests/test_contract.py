from core.analyzers.contract import extract_python_contract_evidence
from core.models import (
    ContractEvidence,
    EvidenceKind,
    EvidenceStrength,
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

    assert evidence == [
        ContractEvidence(
            symbol_qualified_name="demo.add",
            kind=EvidenceKind.DOCSTRING,
            content="返回两个整数之和。",
            source_path=str(source_path),
            source_line=2,
            strength=EvidenceStrength.MEDIUM
        )
    ]