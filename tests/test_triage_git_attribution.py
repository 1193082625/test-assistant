import subprocess

from core.executors.base import ExecutionEnvironment, ExecutionReport
from core.executors.pytest_executor import PytestExecutor
from core.models import DiagnosisCategory
from core.workflows import (
    collect_local_git_triage_evidence,
    triage_pytest_suite,
)


class FailIfExecuted:
    def __init__(self):
        self.executed = []

    def execute(self, node):
        self.executed.append(node)
        return ExecutionReport(
            exit_code=1,
            error_type="test_failure",
            environment=ExecutionEnvironment(
                runner="pytest",
                runtime="python",
                runtime_version="3.13",
                working_directory="/fixture",
            ),
        )


def _git(root, *args):
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def test_deleted_method_history_merges_failures_and_proves_test_defect(
    tmp_path,
):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    _git(tmp_path, "config", "user.name", "Fixture")
    (tmp_path / "app").mkdir()
    (tmp_path / "app/__init__.py").write_text("")
    source = tmp_path / "app/service.py"
    source.write_text(
        "class Service:\n"
        "    async def _removed_async(self):\n"
        "        return 0.5\n"
    )
    _git(tmp_path, "add", "app")
    _git(tmp_path, "commit", "-qm", "add async method")
    source.write_text("class Service:\n    def current(self): return 1\n")
    (tmp_path / "test_service.py").write_text(
        "from app.service import Service\n"
        "def test_exists():\n"
        "    assert hasattr(Service, '_removed_async')\n"
        "def test_source():\n"
        "    assert 'await self._removed_async' in 'current source'\n"
    )
    _git(tmp_path, "add", "app/service.py", "test_service.py")
    _git(tmp_path, "commit", "-qm", "remove async method")
    suite = PytestExecutor(cwd=str(tmp_path)).execute_suite("test_service.py")

    causes, evidence, degradations = collect_local_git_triage_evidence(
        project_root=tmp_path,
        suite=suite,
    )
    executor = FailIfExecuted()
    result = triage_pytest_suite(
        suite=suite,
        executor=executor,
        root_causes=causes,
        evidence_by_root_cause=evidence,
    )

    assert degradations == ()
    assert len(result.clusters) == 1
    assert len(result.clusters[0].issues) == 2
    assert len(result.diagnoses) == 1
    assert result.diagnoses[0].category is DiagnosisCategory.TEST_DEFECT
    assert executor.executed == []


def test_missing_method_without_history_remains_unconfirmed(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/service.py").write_text("class Service: pass\n")
    (tmp_path / "test_service.py").write_text(
        "from app.service import Service\n"
        "def test_exists():\n"
        "    assert hasattr(Service, '_never_existed')\n"
    )
    suite = PytestExecutor(cwd=str(tmp_path)).execute_suite("test_service.py")

    causes, evidence, degradations = collect_local_git_triage_evidence(
        project_root=tmp_path,
        suite=suite,
    )

    assert causes
    assert evidence == {}
    assert degradations
