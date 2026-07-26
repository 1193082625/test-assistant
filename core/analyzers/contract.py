"""文档、Schema、已有测试证据"""

# contract 契约
# qualified 限定的、包含完整上下文的
# qualified name：包含模块、类和外层函数上下文的限定名

import ast
from pathlib import Path
from typing import TypeAlias

from core.models import (
    ContractEvidence,
    EvidenceKind,
    EvidenceStrength,
)

ContractNode: TypeAlias = (
    ast.ClassDef
    | ast.FunctionDef
    | ast.AsyncFunctionDef
)

def extract_python_contract_evidence(
        file_path: str,
        module_name: str,
) -> list[ContractEvidence]:
    """
    提取 Python 类和函数中的契约证据

    流程是：
    extract_python_contract_evidence
    → ast.parse
    → visitor.visit(Module)
    → visit_FunctionDef(add)
    → _visit_contract_node
    → _build_qualified_name("add")
    → "demo.add"
    → _record_docstring
    → ast.get_docstring
    → "返回两个整数之和。"
    → ContractEvidence(...)
    """

    source_path = Path(file_path)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    visitor = _ContractEvidenceVisitor(
        file_path=str(source_path),
        module_name=module_name,
    )

    visitor.visit(tree)

    return visitor.evidence

class _ContractEvidenceVisitor(ast.NodeVisitor):
    """按照源码嵌套结构提取契约证据"""

    def __init__(self, file_path: str, module_name: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.qualified_stack: list[str] = []
        self.evidence: list[ContractEvidence] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_contract_node(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_contract_node(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_contract_node(node)

    def _visit_contract_node(self, node: ContractNode) -> None:
        qualified_name = self._build_qualified_name(node.name)

        self._record_docstring(
            node=node,
            qualified_name=qualified_name,
        )

        self.qualified_stack.append(qualified_name)
        self.generic_visit(node)
        self.qualified_stack.pop()

    def _build_qualified_name(self, name: str) -> str:
        if self.qualified_stack:
            return (
                f"{self.qualified_stack[-1]}.{name}"
            )

        return f"{self.module_name}.{name}"

    def _record_docstring(
            self,
            node: ContractNode,
            qualified_name: str,
    ) -> None:
        docstring = ast.get_docstring(node, clean=True)

        if docstring is None:
            return

        docstring_node = node.body[0]

        self.evidence.append(
            ContractEvidence(
                symbol_qualified_name=qualified_name,
                kind=EvidenceKind.DOCSTRING,
                content=docstring,
                source_path=self.file_path,
                source_line=docstring_node.lineno,
                strength=EvidenceStrength.MEDIUM,
            )
        )