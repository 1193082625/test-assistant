"""将符号覆盖缺口与已有测试和显式变更证据关联。"""

from dataclasses import dataclass

from core.models import (
    CoverageState,
    SymbolCoverage,
    TestIndex,
    TestIndexEntry,
)


@dataclass(frozen=True)
class CoverageGapImpact:
    """一个缺口的候选测试关系与可解释优先因素。"""

    symbol: SymbolCoverage
    candidate_tests: tuple[TestIndexEntry, ...]
    factors: tuple[str, ...]
    changed: bool = False

    @property
    def no_known_test(self) -> bool:
        return not self.candidate_tests


def _is_public_symbol(symbol: SymbolCoverage) -> bool:
    final_name = symbol.qualified_name.rsplit(".", 1)[-1]
    return symbol.kind != "module" and not final_name.startswith("_")


def analyze_coverage_impact(
    *,
    symbols: tuple[SymbolCoverage, ...],
    test_index: TestIndex,
    changed_qualified_names: frozenset[str] | None = None,
    changed_only: bool = False,
) -> tuple[CoverageGapImpact, ...]:
    """关联静态候选测试；不把引用关系声称为真实动态覆盖。"""
    if changed_only and changed_qualified_names is None:
        raise ValueError("changed_only 需要 Git 或 snapshot 变更证据")
    changed_names = changed_qualified_names or frozenset()
    impacts: list[CoverageGapImpact] = []
    for symbol in symbols:
        if symbol.kind == "module" or symbol.state in {
            CoverageState.FULL,
            CoverageState.NOT_APPLICABLE,
        }:
            continue
        changed = symbol.qualified_name in changed_names
        if changed_only and not changed:
            continue
        candidates = tuple(test_index.tests_for(symbol.qualified_name))
        factors: list[str] = []
        if changed:
            factors.append("changed_symbol")
        if _is_public_symbol(symbol):
            factors.append("public_api")
        if symbol.missing_branches:
            factors.append("missing_branches")
        if not candidates:
            factors.append("no_known_test")
        else:
            factors.append(f"candidate_tests={len(candidates)}")
        impacts.append(CoverageGapImpact(
            symbol=symbol,
            candidate_tests=candidates,
            factors=tuple(factors),
            changed=changed,
        ))
    return tuple(sorted(
        impacts,
        key=lambda item: (
            not item.changed,
            not item.no_known_test,
            item.symbol.source_path,
            item.symbol.start_line,
            item.symbol.qualified_name,
        ),
    ))

