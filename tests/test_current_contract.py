from core.analyzers.current_contract import (
    ContractEvidenceStatus,
    analyze_async_result_contract,
    analyze_config_contract,
    analyze_enum_contract,
    analyze_optional_field_contract,
    analyze_type_contract,
)


def test_config_requires_consistent_default_and_consumer():
    evidence = analyze_config_contract(
        target="PaginationParams.page_size",
        source_files={
            "app/config.py": "DEFAULT_PAGE_SIZE = 20",
            "app/schema.py": "class PaginationParams:\n    page_size = settings.DEFAULT_PAGE_SIZE",
        },
    )
    assert evidence.status is ContractEvidenceStatus.CONFIRMED
    assert evidence.current == 20


def test_type_requires_orm_and_schema_agreement():
    evidence = analyze_type_contract(
        target="Topic.id",
        source_files={
            "app/model.py": "class Topic:\n    id: Mapped[str]",
            "app/schema.py": "class TopicResponse:\n    id: str",
        },
    )
    assert evidence.status is ContractEvidenceStatus.CONFIRMED
    assert evidence.current == "str"


def test_type_conflict_is_explicit():
    evidence = analyze_type_contract(
        target="Topic.id",
        source_files={
            "app/model.py": "class Topic:\n    id: Mapped[str]",
            "app/schema.py": "class TopicResponse:\n    id: int",
        },
    )
    assert evidence.status is ContractEvidenceStatus.CONFLICT


def test_optional_field_requires_two_nullable_sources():
    evidence = analyze_optional_field_contract(
        target="Fragrance.purchase_url",
        source_files={
            "app/model.py": "class Fragrance:\n    purchase_url: str | None = None",
            "app/schema.py": "class Response:\n    purchase_url: str | None = None",
        },
    )
    assert evidence.status is ContractEvidenceStatus.CONFIRMED


def test_enum_requires_schema_and_public_router_agreement():
    evidence = analyze_enum_contract(
        target="OutfitComposeRequest.layout",
        source_files={
            "app/schema.py": "from typing import Literal\nclass Request:\n    layout: Literal['auto', 'left-right']",
            "app/router.py": "PUBLIC_LAYOUTS = ('left-right',)",
        },
    )
    assert evidence.status is ContractEvidenceStatus.CONFIRMED
    assert evidence.current == ("auto", "left-right")


def test_async_result_contract_needs_awaited_entry_and_sync_reader():
    evidence = analyze_async_result_contract(
        source_files={
            "app/service.py": "result = await db.execute(query)\nvalue = result.scalar_one_or_none()",
        }
    )
    assert evidence.status is ContractEvidenceStatus.CONFIRMED


def test_invalid_source_never_executes_or_imports_it():
    evidence = analyze_type_contract(
        target="Thing.id",
        source_files={"app/model.py": "raise RuntimeError('must not run')"},
    )
    assert evidence.status is ContractEvidenceStatus.INSUFFICIENT
