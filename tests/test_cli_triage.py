from click.testing import CliRunner

import cli.commands.triage as triage_module
from cli.main import cli
from core.executors.base import ExecutionReport, PytestSuiteResult
from core.models import PytestIssue, TriagePhase
from core.repositories import GitPermissionRepository, TriageRepository


def _write_project(tmp_path, body: str) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text(body, encoding="utf-8")


def test_triage_default_suite_passes_and_saves_record(tmp_path):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert "pytest 摘要: 1 passed" in result.output
    assert "失败簇: 0" in result.output
    assert "Triage 记录:" in result.output
    assert "Git 历史证据: 未授权，诊断安全降级" in result.output
    assert TriageRepository(tmp_path).load_latest() is not None


def test_triage_git_history_requires_explicit_repository_grant(
    tmp_path, monkeypatch
):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")
    observed = {"calls": 0}

    def fail_if_called(**kwargs):
        observed["calls"] += 1
        raise AssertionError("history collector must not run")

    monkeypatch.setattr(
        triage_module,
        "collect_local_git_triage_evidence",
        fail_if_called,
    )

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert observed["calls"] == 0
    audit = TriageRepository(tmp_path).load_latest()["git_history"]
    assert audit["enabled"] is False


def test_triage_allow_git_history_persists_permission(tmp_path):
    import subprocess

    _write_project(tmp_path, "def test_ok():\n    assert True\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    result = CliRunner().invoke(
        cli,
        ["triage", "--path", str(tmp_path), "--allow-git-history"],
    )

    assert result.exit_code == 0, result.output
    assert "Git 历史证据: 已授权（本地只读）" in result.output
    assert "网络访问: 禁止" in result.output
    assert "Git 修改: 禁止" in result.output
    assert GitPermissionRepository(tmp_path).is_granted()
    assert TriageRepository(tmp_path).load_latest()["git_history"][
        "scope"
    ] == "local_read_only"


def test_triage_git_history_confirms_deleted_method_as_one_test_defect(
    tmp_path,
):
    import subprocess

    def git(*args):
        subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True
        )

    git("init", "-q")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    (tmp_path / "app").mkdir()
    (tmp_path / "app/__init__.py").write_text("")
    source = tmp_path / "app/service.py"
    source.write_text(
        "class Service:\n    async def _removed_async(self): return 0.5\n"
    )
    git("add", "app")
    git("commit", "-qm", "add method")
    source.write_text("class Service:\n    def current(self): return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_service.py").write_text(
        "from app.service import Service\n"
        "def test_exists():\n"
        "    assert hasattr(Service, '_removed_async')\n"
        "def test_source():\n"
        "    assert 'await self._removed_async' in 'current source'\n"
    )
    git("add", "app/service.py", "tests/test_service.py")
    git("commit", "-qm", "remove method")

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_service.py",
            "--allow-git-history",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "失败簇: 1" in result.output
    assert "test_defect" in result.output
    assert "置信度: high" in result.output
    assert "git_history=added_then_deleted" in result.output


def test_triage_no_git_history_overrides_saved_permission(tmp_path):
    import subprocess

    _write_project(tmp_path, "def test_ok():\n    assert True\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    GitPermissionRepository(tmp_path).grant()

    result = CliRunner().invoke(
        cli,
        ["triage", "--path", str(tmp_path), "--no-git-history"],
    )

    assert result.exit_code == 0, result.output
    assert "Git 历史证据: 未授权，诊断安全降级" in result.output
    assert GitPermissionRepository(tmp_path).is_granted()


def test_triage_rejects_conflicting_git_history_flags(tmp_path):
    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--allow-git-history",
            "--no-git-history",
        ],
    )

    assert result.exit_code == 2
    assert "不能同时使用" in result.output


def test_triage_empty_suite_is_unresolved(tmp_path):
    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 1, result.output
    assert "未收集到可执行测试" in result.output


def test_triage_test_path_reports_cluster_and_evidence(tmp_path):
    _write_project(tmp_path, "def test_bad():\n    assert 1 == 2\n")

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_demo.py",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "失败簇: 1" in result.output
    assert "inconclusive" in result.output
    assert "置信度: low" in result.output
    assert "代表 node: tests/test_demo.py::test_bad" in result.output
    assert "证据:" in result.output
    assert "复现命令: python -m pytest" in result.output


def test_triage_exact_node_only_runs_selected_test(tmp_path):
    _write_project(
        tmp_path,
        (
            "def test_first():\n    assert False\n\n"
            "def test_second():\n    assert False\n"
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-node",
            "tests/test_demo.py::test_second",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "test_second" in result.output
    assert "test_first" not in result.output


def test_triage_passes_structured_max_failures_to_executor(
    tmp_path,
    monkeypatch,
):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")
    observed = {}

    def fake_execute_suite(self, test_path=None, timeout=120, max_failures=None):
        observed["test_path"] = test_path
        observed["max_failures"] = max_failures
        return PytestSuiteResult(report=ExecutionReport(exit_code=0))

    monkeypatch.setattr(
        triage_module.PytestExecutor,
        "execute_suite",
        fake_execute_suite,
    )

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_demo.py",
            "--max-failures",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert observed == {
        "test_path": "tests/test_demo.py",
        "max_failures": 2,
    }


def test_triage_rejects_mutually_exclusive_scope_options(tmp_path):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")

    result = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "tests/test_demo.py",
            "--test-node",
            "tests/test_demo.py::test_ok",
        ],
    )

    assert result.exit_code == 2
    assert "不能同时使用" in result.output


def test_triage_rejects_missing_or_outside_paths(tmp_path):
    missing_project = CliRunner().invoke(
        cli,
        ["triage", "--path", str(tmp_path / "missing")],
    )
    outside_test = CliRunner().invoke(
        cli,
        [
            "triage",
            "--path",
            str(tmp_path),
            "--test-path",
            "../outside.py",
        ],
    )

    assert missing_project.exit_code == 2
    assert outside_test.exit_code == 2
    assert "必须位于目标项目内" in outside_test.output


def test_triage_runner_error_uses_exit_code_two(tmp_path, monkeypatch):
    issue = PytestIssue(
        phase=TriagePhase.EXECUTION,
        stage="startup",
        outcome="error",
        message="python not found",
        exception_type="FileNotFoundError",
    )

    def fake_execute_suite(self, test_path=None, timeout=120, max_failures=None):
        return PytestSuiteResult(
            report=ExecutionReport(
                exit_code=None,
                error_type="startup_error",
                stderr="python not found",
            ),
            issues=(issue,),
        )

    monkeypatch.setattr(
        triage_module.PytestExecutor,
        "execute_suite",
        fake_execute_suite,
    )

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 2, result.output
    assert "infra_defect" in result.output


def test_triage_persistence_error_uses_exit_code_two(tmp_path, monkeypatch):
    _write_project(tmp_path, "def test_ok():\n    assert True\n")

    def fail_save(self, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(triage_module.TriageRepository, "save", fail_save)

    result = CliRunner().invoke(
        cli, ["triage", "--path", str(tmp_path)]
    )

    assert result.exit_code == 2
    assert "disk full" in result.output


def test_render_contract_migration_uses_explicit_labels(tmp_path, monkeypatch):
    from core.models import (
        ContractMigrationEvidence,
        ContractMigrationType,
    )
    from core.workflows.triage import TriageEvidence

    _write_project(tmp_path, "def test_bad():\n    assert 10 == 120\n")
    original = triage_module.triage_pytest_suite

    def add_migration(**kwargs):
        suite = kwargs["suite"]
        node = suite.issues[0].node_id
        kwargs["evidence_by_node"] = {
            node: TriageEvidence(contract_migration=ContractMigrationEvidence(
                migration_type=ContractMigrationType.CONFIG_DEFAULT,
                target="settings.VALUE",
                old_contract="10",
                current_contract="120",
                current_sources=("app/config.py", "app/service.py"),
                migration_commit="a" * 40,
                current_consistent=True,
                history_confirmed=True,
            ))
        }
        return original(**kwargs)

    monkeypatch.setattr(
        triage_module, "triage_pytest_suite", add_migration
    )
    result = CliRunner().invoke(
        cli,
        ["triage", "--path", str(tmp_path), "--test-path", "tests/test_demo.py"],
    )
    assert result.exit_code == 1, result.output
    assert "迁移类型: config_default" in result.output
    assert "旧契约: 10" in result.output
    assert "当前契约: 120" in result.output
    assert "migration_commit: " + "a" * 40 in result.output
