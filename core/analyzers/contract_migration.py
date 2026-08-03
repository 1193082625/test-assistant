"""从失败测试与异常文本提取保守的契约不匹配候选。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ContractMismatchKind(StrEnum):
    VALUE = "value"
    TYPE = "type"
    OPTIONAL_FIELD = "optional_field"
    DERIVED_VALUE = "derived_value"
    ENUM = "enum"
    ASYNC_MOCK_RESULT = "async_mock_result"
    ASYNC_GENERATOR_LIFECYCLE = "async_generator_lifecycle"


@dataclass(frozen=True)
class ContractMismatch:
    kind: ContractMismatchKind
    target: str
    expected: object | None
    actual: object | None
    source_path: str
    test_path: str
    actual_type: str | None = None
    dependencies: tuple[str, ...] = ()
    warning_source: str | None = None
    missing_lifecycle_steps: tuple[str, ...] = ()


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _assertion_mismatches(
    tree: ast.AST,
    *,
    source_path: str,
    test_path: str,
) -> list[ContractMismatch]:
    found: list[ContractMismatch] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        comparison = node.test
        if not isinstance(comparison, ast.Compare) or len(comparison.ops) != 1:
            continue
        left = comparison.left
        right = comparison.comparators[0]
        target = _name(left)
        expected = _literal(right)
        if target and expected is not None:
            found.append(ContractMismatch(
                kind=ContractMismatchKind.VALUE,
                target=target,
                expected=expected,
                actual=None,
                source_path=source_path,
                test_path=test_path,
            ))
            continue
        calls = [item for item in ast.walk(comparison) if isinstance(item, ast.Call)]
        names = sorted({name for item in ast.walk(comparison) if (name := _name(item)) and isinstance(item, ast.Attribute)})
        if calls and names:
            found.append(ContractMismatch(
                kind=ContractMismatchKind.DERIVED_VALUE,
                target="|".join(names),
                expected=ast.unparse(right),
                actual=None,
                source_path=source_path,
                test_path=test_path,
                dependencies=tuple(names),
            ))
    return found


def _validation_mismatch(
    message: str,
    *,
    source_path: str,
    test_path: str,
) -> ContractMismatch | None:
    field_match = re.search(r"(?:^|\n)([A-Za-z_][\w.]*)\n", message)
    input_match = re.search(
        r"input_value=(.*?)(?:,\s*input_type=([A-Za-z_][\w]*))?\]",
        message,
        re.DOTALL,
    )
    if not field_match:
        return None
    target = field_match.group(1)
    raw_value = input_match.group(1).strip() if input_match else None
    input_type = input_match.group(2) if input_match else None
    if (
        "string_pattern_mismatch" in message
        or "String should match pattern" in message
        or "literal_error" in message
    ):
        kind = ContractMismatchKind.ENUM
    elif input_type == "MagicMock" or "input_type=MagicMock" in message:
        kind = ContractMismatchKind.OPTIONAL_FIELD
    else:
        kind = ContractMismatchKind.TYPE
    expected_match = re.search(r"Input should be (?:a valid )?([^\[,]+)", message)
    expected = expected_match.group(1).strip() if expected_match else None
    return ContractMismatch(
        kind=kind,
        target=target,
        expected=expected,
        actual=raw_value,
        actual_type=input_type,
        source_path=source_path,
        test_path=test_path,
    )


def _async_mismatches(
    tree: ast.AST,
    message: str,
    *,
    source_path: str,
    test_path: str,
) -> list[ContractMismatch]:
    unraisable_runtime_object = (
        "PytestUnraisableExceptionWarning" in message
        and ("<coroutine object" in message or "<async_generator object" in message)
    )
    if "was never awaited" not in message and not unraisable_runtime_object:
        return []
    results: list[ContractMismatch] = []
    warning_match = re.search(r"coroutine(?: method)? ['\"]?([^'\"\n]+)", message)
    if warning_match is None:
        warning_match = re.search(
            r"<(?:coroutine|async_generator) object ([A-Za-z_][\w.]*) at",
            message,
        )
    warning_source = warning_match.group(1).strip() if warning_match else None
    async_mock_names = {
        node.targets[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and _name(node.value.func) in {"AsyncMock", "unittest.mock.AsyncMock"}
    }
    for function in (
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        is_fixture = any(
            (_name(decorator) or "").endswith("fixture")
            or (
                isinstance(decorator, ast.Call)
                and (_name(decorator.func) or "").endswith("fixture")
            )
            for decorator in function.decorator_list
        )
        creates_async_mock = any(
            isinstance(item, ast.Call)
            and _name(item.func) in {"AsyncMock", "unittest.mock.AsyncMock"}
            for item in ast.walk(function)
        )
        if is_fixture and creates_async_mock:
            async_mock_names.add(function.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Await):
            continue
        call = node.value.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        owner = _name(call.func.value)
        if owner in async_mock_names:
            target = _name(call.func) or call.func.attr
            results.append(ContractMismatch(
                kind=ContractMismatchKind.ASYNC_MOCK_RESULT,
                target=target,
                expected="configured synchronous result object",
                actual="implicit AsyncMock child",
                source_path=source_path,
                test_path=test_path,
                warning_source=warning_source,
            ))
    if not any(
        item.kind is ContractMismatchKind.ASYNC_MOCK_RESULT
        for item in results
    ) and async_mock_names and "AsyncMock" in message:
        results.append(ContractMismatch(
            kind=ContractMismatchKind.ASYNC_MOCK_RESULT,
            target=sorted(async_mock_names)[0],
            expected="configured synchronous result object",
            actual="implicit AsyncMock child",
            source_path=source_path,
            test_path=test_path,
            warning_source=warning_source,
        ))
    generator_names: set[str] = set()
    awaited_next: set[str] = set()
    closed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
            if (_name(node.value.func) or "").startswith(("get_", "create_")):
                generator_names.add(node.targets[0].id)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            call_name = _name(node.value.func)
            if call_name == "anext" and node.value.args and isinstance(node.value.args[0], ast.Name):
                awaited_next.add(node.value.args[0].id)
            if call_name and call_name.endswith(".aclose") and isinstance(node.value.func, ast.Attribute):
                owner = _name(node.value.func.value)
                if owner:
                    closed.add(owner)
    for generator in sorted(generator_names):
        missing = []
        if generator not in awaited_next:
            missing.append("await_anext")
        if generator not in closed:
            missing.append("aclose_in_finally")
        if missing and ("asend" in message or "async_generator" in message):
            results.append(ContractMismatch(
                kind=ContractMismatchKind.ASYNC_GENERATOR_LIFECYCLE,
                target=generator,
                expected="awaited and closed async generator",
                actual="incomplete lifecycle",
                source_path=source_path,
                test_path=test_path,
                warning_source=warning_source,
                missing_lifecycle_steps=tuple(missing),
            ))
    return results


def extract_contract_mismatches(
    *,
    test_source: str,
    failure_message: str,
    source_path: str,
    test_path: str,
) -> tuple[ContractMismatch, ...]:
    """提取确定性候选；语法错误或没有足够结构时返回空元组。"""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return ()
    found = _assertion_mismatches(
        tree, source_path=source_path, test_path=test_path
    )
    validation = _validation_mismatch(
        failure_message, source_path=source_path, test_path=test_path
    )
    if validation is not None:
        found.append(validation)
    found.extend(_async_mismatches(
        tree,
        failure_message,
        source_path=source_path,
        test_path=test_path,
    ))
    return tuple(found)
