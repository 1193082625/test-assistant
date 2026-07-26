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
    TestIndex
)

ContractNode: TypeAlias = (
    ast.ClassDef
    | ast.FunctionDef
    | ast.AsyncFunctionDef
)

def extract_existing_test_evidence(
        index: TestIndex
) -> list[ContractEvidence]:
    """把已有测试索引转换为强契约证据"""

    return [
        ContractEvidence(
            symbol_qualified_name=entry.source_qualified_name,
            kind=EvidenceKind.EXISTING_TEST,
            content=entry.test_qualified_name,
            source_path=entry.test_file_path,
            source_line=entry.test_line,
            strength=EvidenceStrength.STRONG,
        )
        for entry in index.entries
    ]

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

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._record_type_hints(node=node, qualified_name=qualified_name)

        self.qualified_stack.append(qualified_name)
        self.generic_visit(node)
        self.qualified_stack.pop()

    def _record_type_hints(
            self,
            node: ast.FunctionDef | ast.AsyncFunctionDef,
            qualified_name: str,
    ) -> None:

        argument_nodes = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]

        if node.args.vararg is not None:
            argument_nodes.append(node.args.vararg)

        if node.args.kwarg is not None:
            argument_nodes.append(node.args.kwarg)

        has_parameter_hint = any(
            argument.annotation is not None
            for argument in argument_nodes
        )

        has_return_hint = node.returns is not None

        if not has_parameter_hint and not has_return_hint:
            return

        async_prefix = (
            "async "
            if isinstance(node, ast.AsyncFunctionDef)
            else ""
        )

        signature = (
            f"{async_prefix}{node.name}"
            f"({ast.unparse(node.args)})"
        )

        if node.returns is not None:
            signature += (
                f" -> {ast.unparse(node.returns)}"
            )

        self.evidence.append(
            ContractEvidence(
                symbol_qualified_name=qualified_name,
                kind=EvidenceKind.TYPE_HINT,
                content=signature,
                source_path=self.file_path,
                source_line=node.lineno,
                strength=EvidenceStrength.MEDIUM
            )
        )

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