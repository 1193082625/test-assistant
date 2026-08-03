"""不导入目标模块的当前契约静态一致性分析。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class ContractEvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    CONFLICT = "conflict"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class CurrentContractEvidence:
    target: str
    status: ContractEvidenceStatus
    current: object | None
    sources: tuple[str, ...]
    details: tuple[str, ...] = ()
    conflict_reason: str | None = None


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    return None


def _annotation(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parse_sources(source_files: Mapping[str, str]) -> dict[str, ast.Module]:
    parsed: dict[str, ast.Module] = {}
    for path, source in source_files.items():
        try:
            parsed[path] = ast.parse(source)
        except SyntaxError:
            continue
    return parsed


def _assignments(parsed: Mapping[str, ast.Module]):
    values: dict[str, list[tuple[object, str]]] = {}
    references: dict[str, list[tuple[str, str]]] = {}
    for path, tree in parsed.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value_node = node.value
                if value_node is None:
                    continue
                for target_node in targets:
                    target = _name(target_node)
                    if not target:
                        continue
                    try:
                        value = ast.literal_eval(value_node)
                    except (ValueError, TypeError):
                        reference = _name(value_node)
                        if reference:
                            references.setdefault(target, []).append((reference, path))
                    else:
                        values.setdefault(target, []).append((value, path))
    return values, references


def analyze_config_contract(
    *, target: str, source_files: Mapping[str, str]
) -> CurrentContractEvidence:
    parsed = _parse_sources(source_files)
    values, references = _assignments(parsed)
    short_target = target.rsplit(".", 1)[-1]
    refs = references.get(short_target, [])
    has_consumer_reference = bool(refs)
    candidates: list[tuple[object, str]] = []
    used_paths: set[str] = set()
    for reference, consumer_path in refs:
        referenced_name = reference.rsplit(".", 1)[-1]
        candidates.extend(values.get(referenced_name, []))
        used_paths.add(consumer_path)
    for consumer, consumer_refs in references.items():
        for reference, consumer_path in consumer_refs:
            if reference.rsplit(".", 1)[-1] != short_target:
                continue
            candidates.extend(values.get(short_target, []))
            used_paths.add(consumer_path)
            has_consumer_reference = True
    candidates.extend(values.get(short_target, []))
    distinct = {repr(value): value for value, _ in candidates}
    paths = used_paths | {path for _, path in candidates}
    if len(distinct) > 1:
        return CurrentContractEvidence(
            target=target,
            status=ContractEvidenceStatus.CONFLICT,
            current=None,
            sources=tuple(sorted(paths)),
            conflict_reason="multiple_current_values",
        )
    if len(distinct) == 1 and has_consumer_reference and len(paths) >= 2:
        return CurrentContractEvidence(
            target=target,
            status=ContractEvidenceStatus.CONFIRMED,
            current=next(iter(distinct.values())),
            sources=tuple(sorted(paths)),
            details=tuple(f"reference={reference}" for reference, _ in refs),
        )
    return CurrentContractEvidence(
        target=target,
        status=ContractEvidenceStatus.INSUFFICIENT,
        current=next(iter(distinct.values()), None),
        sources=tuple(sorted(paths)),
    )


def analyze_type_contract(
    *, target: str, source_files: Mapping[str, str]
) -> CurrentContractEvidence:
    field = target.rsplit(".", 1)[-1]
    found: list[tuple[str, str]] = []
    for path, tree in _parse_sources(source_files).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and _name(node.target) == field:
                annotation = _annotation(node.annotation)
                if annotation:
                    normalized = annotation.replace("Mapped[", "").rstrip("]")
                    found.append((normalized, path))
    types = {annotation for annotation, _ in found}
    paths = tuple(sorted({path for _, path in found}))
    if len(types) > 1:
        return CurrentContractEvidence(
            target=target,
            status=ContractEvidenceStatus.CONFLICT,
            current=None,
            sources=paths,
            details=tuple(sorted(types)),
            conflict_reason="orm_schema_type_conflict",
        )
    if len(found) >= 2 and len(types) == 1:
        return CurrentContractEvidence(
            target=target,
            status=ContractEvidenceStatus.CONFIRMED,
            current=next(iter(types)),
            sources=paths,
        )
    return CurrentContractEvidence(
        target=target,
        status=ContractEvidenceStatus.INSUFFICIENT,
        current=next(iter(types), None),
        sources=paths,
    )


def analyze_optional_field_contract(
    *, target: str, source_files: Mapping[str, str]
) -> CurrentContractEvidence:
    evidence = analyze_type_contract(target=target, source_files=source_files)
    if evidence.status is not ContractEvidenceStatus.CONFIRMED:
        return evidence
    optional_sources = []
    field = target.rsplit(".", 1)[-1]
    for path, tree in _parse_sources(source_files).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and _name(node.target) == field:
                annotation = ast.unparse(node.annotation)
                default_none = isinstance(node.value, ast.Constant) and node.value.value is None
                if "Optional" in annotation or "None" in annotation or default_none:
                    optional_sources.append(path)
    if len(set(optional_sources)) >= 2:
        return evidence
    return CurrentContractEvidence(
        target=target,
        status=ContractEvidenceStatus.CONFLICT,
        current=evidence.current,
        sources=evidence.sources,
        conflict_reason="nullability_conflict",
    )


def analyze_enum_contract(
    *, target: str, source_files: Mapping[str, str]
) -> CurrentContractEvidence:
    field = target.rsplit(".", 1)[-1]
    schema_values: set[str] = set()
    public_values: set[str] = set()
    paths: set[str] = set()
    for path, tree in _parse_sources(source_files).items():
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and _name(node.target) == field:
                text = ast.unparse(node.annotation)
                literal = re.search(r"Literal\[(.*?)\]", text)
                if literal:
                    schema_values.update(re.findall(r"['\"]([^'\"]+)['\"]", literal.group(1)))
                for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
                    for keyword in call.keywords:
                        if keyword.arg == "pattern" and isinstance(keyword.value, ast.Constant):
                            pattern = str(keyword.value.value)
                            match = re.search(r"\(([^)]+)\)", pattern)
                            if match:
                                schema_values.update(match.group(1).split("|"))
                if schema_values:
                    paths.add(path)
            if isinstance(node, ast.Assign):
                target_name = _name(node.targets[0]) if node.targets else None
                if target_name and "LAYOUT" in target_name.upper():
                    try:
                        values = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(values, (tuple, list, set)):
                        public_values.update(str(value) for value in values)
                        paths.add(path)
    if schema_values and public_values <= schema_values and (schema_values - {"auto"}) <= public_values:
        return CurrentContractEvidence(
            target=target,
            status=ContractEvidenceStatus.CONFIRMED,
            current=tuple(sorted(schema_values)),
            sources=tuple(sorted(paths)),
        )
    return CurrentContractEvidence(
        target=target,
        status=(ContractEvidenceStatus.CONFLICT if schema_values and public_values else ContractEvidenceStatus.INSUFFICIENT),
        current=tuple(sorted(schema_values)) or None,
        sources=tuple(sorted(paths)),
        conflict_reason="schema_router_enum_conflict" if schema_values and public_values else None,
    )


def analyze_async_result_contract(
    *, source_files: Mapping[str, str]
) -> CurrentContractEvidence:
    text = "\n".join(source_files.values())
    awaited_execute = bool(re.search(r"await\s+\w+\.execute\s*\(", text))
    sync_result = bool(re.search(r"\w+\.scalar_one_or_none\s*\(", text))
    if awaited_execute and sync_result:
        return CurrentContractEvidence(
            target="AsyncSession.execute.result",
            status=ContractEvidenceStatus.CONFIRMED,
            current="async execute + synchronous Result API",
            sources=tuple(sorted(source_files)),
            details=("supported_api_contract=sqlalchemy_async_result",),
        )
    return CurrentContractEvidence(
        target="AsyncSession.execute.result",
        status=ContractEvidenceStatus.INSUFFICIENT,
        current=None,
        sources=tuple(sorted(source_files)),
    )
