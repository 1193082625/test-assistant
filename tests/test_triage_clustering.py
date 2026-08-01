from core.diagnosticians import (
    cluster_pytest_issues,
    failure_fingerprint,
)
from core.models import DiagnosisLocation, PytestIssue, TriagePhase


def _failure(
    node_id: str,
    *,
    message: str,
    path: str,
) -> PytestIssue:
    return PytestIssue(
        node_id=node_id,
        phase=TriagePhase.EXECUTION,
        stage="call",
        outcome="failed",
        exception_type="AssertionError",
        message=message,
        locations=(DiagnosisLocation(path=path, line=12),),
    )


def test_fingerprint_ignores_unstable_runtime_values():
    first = _failure(
        "tests/test_a.py::test_one",
        message=(
            "object at 0xABC123 failed at 2026-08-01T10:20:30Z "
            "in /tmp/pytest-1/test_case0/result.json"
        ),
        path="/workspace-one/tests/test_service.py",
    )
    second = _failure(
        "tests/test_b.py::test_two",
        message=(
            "object at 0xDEF456 failed at 2027-09-02T11:21:31Z "
            "in /private/var/tmp/pytest-9/test_case9/result.json"
        ),
        path="/workspace-two/tests/test_service.py",
    )

    assert failure_fingerprint(first) == failure_fingerprint(second)


def test_clustering_is_deterministic_and_selects_first_node():
    same_failure = (
        _failure(
            "tests/test_service.py::test_second",
            message="assert None is False",
            path="/one/test_service.py",
        ),
        _failure(
            "tests/test_service.py::test_first",
            message="assert None is False",
            path="/two/test_service.py",
        ),
    )
    other_failure = PytestIssue(
        phase=TriagePhase.COLLECTION,
        outcome="error",
        message="SyntaxError: invalid syntax",
        exception_type="SyntaxError",
    )
    ignored = PytestIssue(
        phase=TriagePhase.WARNING,
        outcome="warning",
        message="deprecated",
    )

    clusters = cluster_pytest_issues(
        (same_failure[0], ignored, other_failure, same_failure[1])
    )
    reversed_clusters = cluster_pytest_issues(
        tuple(reversed((
            same_failure[0], ignored, other_failure, same_failure[1]
        )))
    )

    assert len(clusters) == 2
    assert [cluster.fingerprint for cluster in clusters] == [
        cluster.fingerprint for cluster in reversed_clusters
    ]
    execution_cluster = next(
        cluster for cluster in clusters
        if cluster.representative_node is not None
    )
    assert execution_cluster.representative_node == (
        "tests/test_service.py::test_first"
    )
    assert len(execution_cluster.issues) == 2
    assert type(execution_cluster).from_dict(
        execution_cluster.to_dict()
    ) == execution_cluster
