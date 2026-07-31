from click.testing import CliRunner

from cli.main import cli
from core.models import (
    TestSpec as Spec,
    TestSpecStatus as SpecStatus,
)
from core.repositories import TestSpecRepository as SpecRepository


def _save_spec(tmp_path, status=SpecStatus.APPROVED):
    spec = Spec(
        id="spec-demo-verify-cli",
        target_symbol="demo.add",
        behavior="返回两个整数之和",
        arrange={"left": 1, "right": 1},
        action="调用 add(left, right)",
        expected={"return": 2},
        status=status,
    )
    SpecRepository(str(tmp_path)).save(spec)
    return spec


def _write_project(tmp_path, assertion):
    (tmp_path / "demo.py").write_text(
        "def add(left, right):\n"
        "    return left + right\n",
        encoding="utf-8",
    )
    tests_path = tmp_path / "tests"
    tests_path.mkdir()
    (tests_path / "test_demo.py").write_text(
        "from demo import add\n\n"
        "def test_add():\n"
        f"    {assertion}\n",
        encoding="utf-8",
    )


def test_verify_command_runs_real_test_node_three_times(
    tmp_path,
):
    _write_project(tmp_path, "assert add(1, 1) == 2")
    spec = _save_spec(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "verify",
            spec.id,
            "--path",
            str(tmp_path),
            "--test-node",
            "tests/test_demo.py::test_add",
            "--source-path",
            "demo.py",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "连续 3 次通过" in result.output
    assert "python -m pytest" in result.output

    status_result = CliRunner().invoke(
        cli,
        ["status", "--path", str(tmp_path)],
    )
    assert status_result.exit_code == 0
    assert "状态: 健康" in status_result.output


def test_verify_command_saves_stable_failure(
    tmp_path,
):
    _write_project(tmp_path, "assert add(1, 1) == 3")
    spec = _save_spec(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "verify",
            spec.id,
            "--path",
            str(tmp_path),
            "--test-node",
            "tests/test_demo.py::test_add",
            "--source-path",
            "demo.py",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "inconclusive" in result.output
    assert (
        tmp_path
        / ".autotest"
        / "diagnoses"
        / "latest.json"
    ).is_file()


def test_verify_rejects_unapproved_spec(tmp_path):
    _write_project(tmp_path, "assert add(1, 1) == 2")
    spec = _save_spec(
        tmp_path,
        status=SpecStatus.PROPOSED,
    )

    result = CliRunner().invoke(
        cli,
        [
            "verify",
            spec.id,
            "--path",
            str(tmp_path),
            "--test-node",
            "tests/test_demo.py::test_add",
            "--source-path",
            "demo.py",
        ],
    )

    assert result.exit_code != 0
    assert "只有 approved TestSpec" in result.output
