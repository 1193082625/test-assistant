"""Performance test selection controls."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-large-performance",
        action="store_true",
        default=False,
        help="run fixed-machine large performance profiles",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--run-large-performance"):
        return

    skip_large = pytest.mark.skip(
        reason=(
            "large performance profile requires "
            "--run-large-performance"
        ),
    )
    for item in items:
        if "large_performance" in item.keywords:
            item.add_marker(skip_large)
