"""coverage.py 事实到源码符号的映射测试。"""

import pytest

from core.analyzers.coverage import analyze_symbol_coverage
from core.models import CoverageState


def _write_source(tmp_path):
    path = tmp_path / "app" / "service.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """def covered(value):
    if value:
        return 1
    return 0

def untouched():
    return 2
""",
        encoding="utf-8",
    )
    return path


def _coverage_data():
    return {
        "files": {
            "app/service.py": {
                "executed_lines": [1, 2, 3],
                "missing_lines": [4, 6, 7],
                "executed_branches": [[2, 3]],
                "missing_branches": [[2, 4]],
            },
        },
    }


def test_maps_partial_and_uncovered_functions(tmp_path):
    _write_source(tmp_path)

    results = analyze_symbol_coverage(
        project_root=tmp_path,
        coverage_data=_coverage_data(),
    )

    covered = next(item for item in results if item.qualified_name.endswith(".covered"))
    assert covered.summary.statements_covered == 3
    assert covered.summary.statements_total == 4
    assert covered.summary.branches_covered == 1
    assert covered.summary.branches_total == 2
    assert covered.missing_lines == (4,)
    assert covered.missing_branches == ((2, 4),)
    assert covered.state is CoverageState.PARTIAL

    untouched = next(
        item for item in results if item.qualified_name.endswith(".untouched")
    )
    assert untouched.summary.statements_covered == 0
    assert untouched.summary.statements_total == 2
    assert untouched.missing_lines == (6, 7)
    assert untouched.state is CoverageState.UNCOVERED


def test_includes_module_class_method_async_and_nested_symbols(tmp_path):
    path = tmp_path / "app" / "workers.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """class Worker:
    async def run(self):
        def nested():
            return 1
        return nested()
""",
        encoding="utf-8",
    )
    data = {
        "files": {
            "app/workers.py": {
                "executed_lines": [1, 2, 3, 4, 5],
                "missing_lines": [],
                "executed_branches": [],
                "missing_branches": [],
            },
        },
    }

    results = analyze_symbol_coverage(project_root=tmp_path, coverage_data=data)

    assert {item.kind for item in results} == {
        "module", "class", "method", "function"
    }
    assert any(item.qualified_name.endswith("Worker.run.nested") for item in results)


def test_excludes_only_configured_patterns(tmp_path):
    _write_source(tmp_path)

    results = analyze_symbol_coverage(
        project_root=tmp_path,
        coverage_data=_coverage_data(),
        exclude_patterns=("app/*",),
    )

    assert results == ()


def test_rejects_coverage_source_outside_project(tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")
    data = {
        "files": {
            str(outside): {
                "executed_lines": [1],
                "missing_lines": [],
                "executed_branches": [],
                "missing_branches": [],
            },
        },
    }

    with pytest.raises(ValueError, match="源码路径必须位于项目内"):
        analyze_symbol_coverage(project_root=tmp_path, coverage_data=data)


def test_preserves_decorated_multiline_property_and_exit_branch(tmp_path):
    path = tmp_path / "app" / "decorated.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """class Item:
    @property
    def name(self):
        return "item"

def combine(
    left,
    right,
):
    return left + right
""",
        encoding="utf-8",
    )
    data = {
        "files": {
            "app/decorated.py": {
                "executed_lines": [1, 2, 3, 4, 6, 7, 8, 9, 10],
                "missing_lines": [],
                "executed_branches": [[3, -1]],
                "missing_branches": [],
            },
        },
    }

    results = analyze_symbol_coverage(project_root=tmp_path, coverage_data=data)

    prop = next(item for item in results if item.qualified_name.endswith("Item.name"))
    combine = next(item for item in results if item.qualified_name.endswith(".combine"))
    assert prop.start_line == 2
    assert prop.state is CoverageState.FULL
    assert combine.start_line == 6
    assert combine.end_line == 10
