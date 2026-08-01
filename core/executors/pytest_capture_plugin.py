"""将 pytest hook 事件写入 JSON，供 test-assistant 稳定读取。"""

import json
from pathlib import Path
from typing import Any

import pytest


_events: list[dict[str, Any]] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("test-assistant").addoption(
        "--test-assistant-json",
        action="store",
        help="write structured pytest events to this JSON file",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    _events.clear()


def _location(location: object) -> list[dict[str, object]]:
    if not isinstance(location, tuple) or len(location) < 2:
        return []
    path, line = location[0], location[1]
    if not isinstance(path, str):
        return []
    return [{
        "path": path,
        "line": line + 1 if isinstance(line, int) else None,
        "column": None,
        "symbol": None,
    }]


def _message(report: pytest.TestReport | pytest.CollectReport) -> str:
    longrepr = getattr(report, "longrepr", None)
    crash = getattr(longrepr, "reprcrash", None)
    if crash is not None:
        return str(crash.message)
    if isinstance(longrepr, tuple) and len(longrepr) >= 3:
        return str(longrepr[2])
    return "" if longrepr is None else str(longrepr)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[object],
):
    outcome = yield
    report = outcome.get_result()
    status = report.outcome
    if report.failed and report.when != "call":
        status = "error"
    exception_type = None
    if call.excinfo is not None:
        exception_type = call.excinfo.typename
    _events.append({
        "phase": "execution",
        "outcome": status,
        "message": _message(report),
        "node_id": report.nodeid,
        "stage": report.when,
        "exception_type": exception_type,
        "locations": _location(report.location),
        "duration": report.duration,
    })


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if not report.failed:
        return
    _events.append({
        "phase": "collection",
        "outcome": "error",
        "message": _message(report),
        "node_id": report.nodeid or None,
        "stage": "collect",
        "exception_type": None,
        "locations": _location(report.location),
        "duration": 0.0,
    })


def pytest_warning_recorded(
    warning_message: Any,
    when: str,
    nodeid: str,
    location: tuple[str, int, str] | None,
) -> None:
    category = getattr(warning_message, "category", None)
    _events.append({
        "phase": "warning",
        "outcome": "warning",
        "message": str(warning_message.message),
        "node_id": nodeid or None,
        "stage": when,
        "exception_type": getattr(category, "__name__", None),
        "locations": _location(location),
        "duration": 0.0,
    })


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    output_path = session.config.getoption("--test-assistant-json")
    if not output_path:
        return
    if int(exitstatus) == 5 and not _events:
        _events.append({
            "phase": "collection",
            "outcome": "no_tests_collected",
            "message": "pytest did not collect any tests",
            "node_id": None,
            "stage": "collect",
            "exception_type": None,
            "locations": [],
            "duration": 0.0,
        })
    Path(output_path).write_text(
        json.dumps({
            "schema_version": 1,
            "exit_code": int(exitstatus),
            "events": _events,
        }),
        encoding="utf-8",
    )
