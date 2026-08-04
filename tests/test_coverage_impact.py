"""覆盖缺口与候选已有测试的可解释关联测试。"""

import pytest

from core.analyzers.coverage_impact import analyze_coverage_impact
from core.models import (
    CoverageSummary,
    SymbolCoverage,
    TestIndex as ExistingTestIndex,
    TestIndexEntry as ExistingTestIndexEntry,
)


def _symbol(
    name: str,
    *,
    covered: int,
    total: int,
    missing_branches=(),
):
    return SymbolCoverage(
        source_path="app/service.py",
        qualified_name=f"app.service.{name}",
        kind="function",
        start_line=1,
        end_line=10,
        summary=CoverageSummary(
            statements_covered=covered,
            statements_total=total,
            branches_covered=0,
            branches_total=len(missing_branches),
        ),
        missing_lines=tuple(range(covered + 1, total + 1)),
        missing_branches=missing_branches,
    )


def test_relates_gaps_to_candidate_tests_without_claiming_coverage():
    partial = _symbol(
        "partial", covered=2, total=3, missing_branches=((2, 3),)
    )
    uncovered = _symbol("uncovered", covered=0, total=2)
    test_index = ExistingTestIndex(entries=[ExistingTestIndexEntry(
        source_qualified_name=partial.qualified_name,
        test_qualified_name="tests.test_service.test_partial",
        test_file_path="tests/test_service.py",
        test_line=4,
    )])

    impacts = analyze_coverage_impact(
        symbols=(partial, uncovered), test_index=test_index
    )

    partial_impact = next(item for item in impacts if item.symbol is partial)
    assert partial_impact.candidate_tests[0].test_file_path == "tests/test_service.py"
    assert "candidate_tests=1" in partial_impact.factors
    assert "missing_branches" in partial_impact.factors
    uncovered_impact = next(item for item in impacts if item.symbol is uncovered)
    assert uncovered_impact.no_known_test is True
    assert "no_known_test" in uncovered_impact.factors
    assert "public_api" in uncovered_impact.factors


def test_changed_only_filters_with_explicit_change_evidence():
    changed = _symbol("changed", covered=0, total=2)
    unchanged = _symbol("unchanged", covered=0, total=2)

    impacts = analyze_coverage_impact(
        symbols=(unchanged, changed),
        test_index=ExistingTestIndex(),
        changed_qualified_names=frozenset({changed.qualified_name}),
        changed_only=True,
    )

    assert [item.symbol for item in impacts] == [changed]
    assert impacts[0].changed is True
    assert impacts[0].factors[0] == "changed_symbol"


def test_changed_only_requires_git_or_snapshot_evidence():
    with pytest.raises(
        ValueError,
        match="changed_only 需要 Git 或 snapshot 变更证据",
    ):
        analyze_coverage_impact(
            symbols=(), test_index=ExistingTestIndex(), changed_only=True
        )


def test_full_or_non_applicable_symbols_are_not_gaps():
    full = _symbol("full", covered=2, total=2)
    no_statements = _symbol("empty", covered=0, total=0)

    impacts = analyze_coverage_impact(
        symbols=(full, no_statements), test_index=ExistingTestIndex()
    )

    assert impacts == ()
