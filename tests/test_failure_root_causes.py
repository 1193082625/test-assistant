from core.analyzers import extract_failure_root_causes
from core.diagnosticians import cluster_pytest_issues
from core.models import PytestIssue, TriagePhase


def _issue(node):
    return PytestIssue(
        phase=TriagePhase.EXECUTION,
        stage="call",
        outcome="failed",
        message="failed",
        node_id=node,
        exception_type="AssertionError",
    )


def test_obsolete_patch_targets_share_one_root_cause(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/model.py").write_text("class NewLoader: pass\n")
    (tmp_path / "test_model.py").write_text(
        "from unittest.mock import patch\n"
        "@patch('app.model.legacy.load')\n"
        "def test_first(mock_load): pass\n"
        "@patch('app.model.legacy.load')\n"
        "def test_second(mock_load): pass\n"
    )
    issues = (
        _issue("test_model.py::test_first"),
        _issue("test_model.py::test_second"),
    )

    causes = extract_failure_root_causes(
        project_root=tmp_path, issues=issues
    )
    clusters = cluster_pytest_issues(issues, causes)

    assert {cause.target for cause in causes.values()} == {"app.model.legacy"}
    assert len(clusters) == 1
    assert clusters[0].root_cause_key == "obsolete_patch:app.model.legacy"
    assert len(clusters[0].issues) == 2


def test_three_missing_method_tests_share_one_root_cause(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/service.py").write_text(
        "class Service:\n    def current(self): pass\n"
    )
    (tmp_path / "test_service.py").write_text(
        "from app.service import Service\n"
        "def test_exists():\n"
        "    assert hasattr(Service, '_removed_async')\n"
        "async def test_call():\n"
        "    await Service()._removed_async()\n"
        "def test_source():\n"
        "    assert 'await self._removed_async' in 'source'\n"
    )
    issues = tuple(
        _issue(f"test_service.py::{name}")
        for name in ("test_exists", "test_call", "test_source")
    )

    causes = extract_failure_root_causes(
        project_root=tmp_path, issues=issues
    )
    clusters = cluster_pytest_issues(issues, causes)

    assert len(causes) == 3
    assert len(clusters) == 1
    assert clusters[0].root_cause_target == "app.service.Service._removed_async"
