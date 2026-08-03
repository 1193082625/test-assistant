from core.analyzers.contract_migration import (
    ContractMismatchKind,
    extract_contract_mismatches,
)


def extract(source: str, message: str = ""):
    return extract_contract_mismatches(
        test_source=source,
        failure_message=message,
        source_path="app/service.py",
        test_path="tests/test_service.py",
    )


def test_extracts_literal_value_assertion():
    mismatches = extract("assert service.UNDO_SECONDS == 10")
    assert mismatches[0].kind is ContractMismatchKind.VALUE
    assert mismatches[0].target == "service.UNDO_SECONDS"
    assert mismatches[0].expected == 10


def test_extracts_pydantic_type_failure():
    message = """1 validation error for TopicResponse
id
  Input should be a valid string [type=string_type, input_value=1, input_type=int]
"""
    mismatch = extract("TopicResponse.model_validate({'id': 1})", message)[0]
    assert mismatch.kind is ContractMismatchKind.TYPE
    assert mismatch.target == "id"
    assert mismatch.actual == "1"


def test_extracts_magic_mock_optional_field_drift():
    message = """1 validation error for FragranceResponse
purchase_url
  Input should be a valid string [type=string_type, input_value=<MagicMock id='1'>, input_type=MagicMock]
"""
    mismatch = extract("FragranceResponse.model_validate(fixture)", message)[0]
    assert mismatch.kind is ContractMismatchKind.OPTIONAL_FIELD


def test_extracts_enum_pattern_failure():
    message = """1 validation error for Request
layout
  String should match pattern [type=string_pattern_mismatch, input_value='grid', input_type=str]
"""
    mismatch = extract("Request(layout='grid')", message)[0]
    assert mismatch.kind is ContractMismatchKind.ENUM
    assert mismatch.target == "layout"


def test_extracts_async_mock_result_boundary():
    source = """
from unittest.mock import AsyncMock
async def test_case():
    db = AsyncMock()
    result = await db.execute('select')
    result.scalar_one_or_none()
"""
    mismatch = extract(
        source,
        "RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited",
    )[0]
    assert mismatch.kind is ContractMismatchKind.ASYNC_MOCK_RESULT
    assert mismatch.target == "db.execute"


def test_extracts_async_mock_injected_by_pytest_fixture():
    source = """
import pytest
from unittest.mock import AsyncMock
@pytest.fixture
def mock_db():
    return AsyncMock()
async def test_case(mock_db):
    result = await mock_db.execute('select')
    result.scalar_one_or_none()
"""
    mismatch = extract(
        source,
        "RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited",
    )[0]
    assert mismatch.kind is ContractMismatchKind.ASYNC_MOCK_RESULT
    assert mismatch.target == "mock_db.execute"


def test_extracts_async_generator_lifecycle_gap():
    source = """
async def test_case():
    gen = get_db()
    session = gen.__anext__()
"""
    mismatch = extract(
        source,
        "RuntimeWarning: coroutine method 'asend' of 'get_db' was never awaited",
    )[0]
    assert mismatch.kind is ContractMismatchKind.ASYNC_GENERATOR_LIFECYCLE
    assert mismatch.missing_lifecycle_steps == (
        "await_anext",
        "aclose_in_finally",
    )


def test_ignores_dynamic_or_invalid_source():
    assert extract("assert dynamic() == expected") == ()
    assert extract("not python(") == ()
