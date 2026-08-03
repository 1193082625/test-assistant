"""将 pytest hook 事件写入 JSON，供 test-assistant 稳定读取。"""

import json
from pathlib import Path
from typing import Any

import pytest


_events: list[dict[str, Any]] = []
_completed_nodes: set[str] = set()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("test-assistant").addoption(
        "--test-assistant-json",
        action="store",
        help="write structured pytest events to this JSON file",
    )
    parser.getgroup("test-assistant").addoption(
        "--test-assistant-progress-jsonl",
        action="store",
        help="append incremental pytest progress events as JSONL",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    _events.clear()
    _completed_nodes.clear()


def _progress(config: pytest.Config, payload: dict[str, object]) -> None:
    output_path = config.getoption("--test-assistant-progress-jsonl")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stream.flush()


def pytest_collection_finish(session: pytest.Session) -> None:
    _progress(session.config, {
        "event": "collection",
        "total": len(session.items),
    })


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
    terminal_report = (
        report.when == "call"
        or (report.when == "setup" and report.skipped)
        or (report.when in {"setup", "teardown"} and report.failed)
    )
    if terminal_report and report.nodeid not in _completed_nodes:
        _completed_nodes.add(report.nodeid)
        _progress(item.config, {
            "event": "test_complete",
            "completed": len(_completed_nodes),
            "node_id": report.nodeid,
            "outcome": status,
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
