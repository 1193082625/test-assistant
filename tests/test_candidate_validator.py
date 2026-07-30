import pytest
import subprocess
import sys
from pathlib import Path
from core.validators import (
    CandidateValidationStatus,
    check_pytest_runner_health,
    collect_pytest_candidate,
    execute_pytest_candidate_isolated,
    validate_python_candidate,
)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "   \n",
    ],
)
def test_validator_rejects_empty_candidate(
    content,
):
    result = validate_python_candidate(
        content
    )

    assert (
        result.status
        is CandidateValidationStatus.EMPTY
    )
    assert result.passed is False
    assert result.errors == (
        "候选测试源码为空",
    )

@pytest.mark.parametrize(
    "content",
    [
        (
            "下面是生成的测试：\n"
            "```python\n"
            "def test_demo(): pass\n"
            "```\n"
        ),
        (
            "```python\n"
            "def test_one(): pass\n"
            "```\n"
            "```python\n"
            "def test_two(): pass\n"
            "```\n"
        ),
    ],
)
def test_validator_rejects_markdown_output(
    content,
):
    result = validate_python_candidate(
        content
    )

    assert (
        result.status
        is CandidateValidationStatus.INVALID_STRUCTURE
    )
    assert result.passed is False
    assert result.errors == (
        "候选测试输出必须是纯 Python 源码",
    )

@pytest.mark.parametrize(
    "content",
    [
        '"这是生成结果的说明文字"\n',
        'DESCRIPTION = "这是测试说明"\n',
    ],
)
def test_validator_rejects_python_without_tests(
    content,
):
    result = validate_python_candidate(
        content
    )

    assert (
        result.status
        is CandidateValidationStatus.INVALID_STRUCTURE
    )
    assert result.passed is False
    assert result.errors == (
        "候选测试源码中没有 pytest 测试函数",
    )

@pytest.mark.parametrize(
    "content",
    [
        (
            "def test_demo(:\n"
            "    pass\n"
        ),
        (
            "def test_demo():\n"
            "    assert (\n"
        ),
    ],
)
def test_validator_returns_structured_syntax_error(
    content,
):
    result = validate_python_candidate(
        content
    )

    assert (
        result.status
        is CandidateValidationStatus.SYNTAX_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "候选测试包含非法 Python 语法",
    )

@pytest.mark.parametrize(
    "content",
    [
        (
            "def test_add():\n"
            "    assert 1 + 2 == 3\n"
        ),
        (
            "async def test_fetch():\n"
            "    result = 1\n"
            "    assert result == 1\n"
        ),
    ],
)
def test_validator_accepts_valid_python_tests(
    content,
):
    result = validate_python_candidate(
        content
    )

    assert (
        result.status
        is CandidateValidationStatus.PASSED
    )
    assert result.passed is True
    assert result.errors == ()

def test_validator_reports_missing_import(
    tmp_path,
):
    content = (
        "from missing_module import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    result = validate_python_candidate(
        content,
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.IMPORT_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "无法导入模块: missing_module",
    )

def test_validator_accepts_existing_local_import(
    tmp_path,
):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    content = (
        "from demo import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    result = validate_python_candidate(
        content,
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.PASSED
    )
    assert result.passed is True
    assert result.errors == ()

def test_collect_reports_no_tests_as_collection_error(
    tmp_path,
    monkeypatch,
):
    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    def fake_run(
        command,
        **kwargs,
    ):
        assert command == [
            sys.executable,
            "-m",
            "pytest",
            str(candidate_path),
            "--collect-only",
            "-q",
        ]
        assert kwargs["cwd"] == tmp_path
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True

        return subprocess.CompletedProcess(
            args=command,
            returncode=5,
            stdout="no tests collected\n",
            stderr="",
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fake_run,
    )

    result = collect_pytest_candidate(
        candidate_path=candidate_path,
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.COLLECTION_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "pytest 未收集到测试",
    )

def test_collect_reports_pytest_collection_failure(
    tmp_path,
    monkeypatch,
):
    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    def fake_run(
        command,
        **kwargs,
    ):
        return subprocess.CompletedProcess(
            args=command,
            returncode=2,
            stdout=(
                "ERROR collecting "
                "test_candidate.py\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fake_run,
    )

    result = collect_pytest_candidate(
        candidate_path=candidate_path,
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.COLLECTION_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "pytest 收集候选测试失败",
    )

def test_collect_accepts_real_pytest_candidate(
    tmp_path,
):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    result = collect_pytest_candidate(
        candidate_path=candidate_path,
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.PASSED
    )
    assert result.passed is True
    assert result.errors == ()

def test_runner_health_reports_environment_failure(
    tmp_path,
    monkeypatch,
):
    def fake_run(
        command,
        **kwargs,
    ):
        assert command == [
            sys.executable,
            "-m",
            "pytest",
            "--version",
        ]
        assert kwargs["cwd"] == tmp_path
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True

        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr="pytest unavailable",
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fake_run,
    )

    result = check_pytest_runner_health(
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.RUNNER_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "pytest Runner 健康检查失败",
    )

def test_runner_health_reports_startup_error(
    tmp_path,
    monkeypatch,
):
    def fail_run(
        command,
        **kwargs,
    ):
        raise OSError(
            "unable to start subprocess"
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fail_run,
    )

    result = check_pytest_runner_health(
        project_root=tmp_path,
    )

    assert (
        result.status
        is CandidateValidationStatus.RUNNER_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "pytest Runner 启动失败",
    )


def test_runner_health_reports_timeout(
        tmp_path,
        monkeypatch,
):
    def timeout_run(
            command,
            **kwargs,
    ):
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        timeout_run,
    )

    result = check_pytest_runner_health(
        project_root=tmp_path,
    )

    assert (
            result.status
            is CandidateValidationStatus.TIMEOUT
    )
    assert result.passed is False
    assert result.errors == (
        "pytest Runner 健康检查超时",
    )

def test_isolated_execution_reports_test_failure(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        (
            "def test_demo():\n"
            "    assert False\n"
        ),
        encoding="utf-8",
    )

    def fake_run(
        command,
        **kwargs,
    ):
        isolated_root = Path(
            kwargs["cwd"]
        )

        assert isolated_root != tmp_path
        assert (
            isolated_root / "demo.py"
        ).is_file()

        isolated_candidate = (
            isolated_root
            / "test_candidate.py"
        )
        assert isolated_candidate.is_file()

        assert command == [
            sys.executable,
            "-m",
            "pytest",
            str(isolated_candidate),
            "-q",
        ]
        assert kwargs["timeout"] == 5

        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="1 failed\n",
            stderr="",
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fake_run,
    )

    result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=tmp_path,
        timeout=5,
    )

    assert (
        result.status
        is CandidateValidationStatus.TEST_FAILURE
    )
    assert result.passed is False
    assert result.errors == (
        "候选测试执行失败",
    )

def test_isolated_execution_preserves_original_project(
    tmp_path,
):
    data_path = tmp_path / "data.txt"
    data_path.write_text(
        "original",
        encoding="utf-8",
    )

    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        (
            "from pathlib import Path\n"
            "\n"
            "def test_writes_file():\n"
            "    path = Path('data.txt')\n"
            "    path.write_text(\n"
            "        'changed',\n"
            "        encoding='utf-8',\n"
            "    )\n"
            "    assert path.read_text(\n"
            "        encoding='utf-8',\n"
            "    ) == 'changed'\n"
        ),
        encoding="utf-8",
    )

    result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=tmp_path,
        timeout=10,
    )

    assert (
        result.status
        is CandidateValidationStatus.PASSED
    )
    assert result.passed is True
    assert result.errors == ()

    assert data_path.read_text(
        encoding="utf-8",
    ) == "original"


def test_isolated_execution_reports_created_and_deleted_files(
    tmp_path,
    monkeypatch,
):
    deleted_path = tmp_path / "obsolete.txt"
    deleted_path.write_text(
        "obsolete",
        encoding="utf-8",
    )
    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    def fake_run(
        command,
        **kwargs,
    ):
        isolated_root = Path(kwargs["cwd"])
        (
            isolated_root / "obsolete.txt"
        ).unlink()
        (
            isolated_root / "z-output.txt"
        ).write_text(
            "z",
            encoding="utf-8",
        )
        (
            isolated_root / "a-output.txt"
        ).write_text(
            "a",
            encoding="utf-8",
        )

        pytest_cache = (
            isolated_root / ".pytest_cache"
        )
        pytest_cache.mkdir()
        (
            pytest_cache / "README.md"
        ).write_text(
            "runner cache",
            encoding="utf-8",
        )

        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="1 passed\n",
            stderr="",
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fake_run,
    )

    result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=tmp_path,
        timeout=5,
    )

    assert result.side_effects == (
        "created:a-output.txt",
        "created:z-output.txt",
        "deleted:obsolete.txt",
    )
    assert deleted_path.read_text(
        encoding="utf-8",
    ) == "obsolete"
    assert not (
        tmp_path / "a-output.txt"
    ).exists()

def test_isolated_execution_reports_timeout(
    tmp_path,
    monkeypatch,
):
    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        (
            "def test_slow():\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    def timeout_run(
        command,
        **kwargs,
    ):
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        timeout_run,
    )

    result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=tmp_path,
        timeout=3,
    )

    assert (
        result.status
        is CandidateValidationStatus.TIMEOUT
    )
    assert result.passed is False
    assert result.errors == (
        "候选测试执行超时",
    )

def test_isolated_execution_reports_runner_startup_error(
    tmp_path,
    monkeypatch,
):
    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    def fail_run(
        command,
        **kwargs,
    ):
        raise OSError(
            "unable to start pytest"
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fail_run,
    )

    result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=tmp_path,
        timeout=5,
    )

    assert (
        result.status
        is CandidateValidationStatus.RUNNER_ERROR
    )
    assert result.passed is False
    assert result.errors == (
        "pytest Runner 执行启动失败",
    )

def test_isolated_execution_reports_file_side_effect(
    tmp_path,
    monkeypatch,
):
    data_path = tmp_path / "data.txt"
    data_path.write_text(
        "original",
        encoding="utf-8",
    )

    candidate_path = (
        tmp_path / "test_candidate.py"
    )
    candidate_path.write_text(
        "def test_demo(): pass\n",
        encoding="utf-8",
    )

    def fake_run(
        command,
        **kwargs,
    ):
        isolated_root = Path(
            kwargs["cwd"]
        )
        isolated_data_path = (
            isolated_root / "data.txt"
        )
        isolated_data_path.write_text(
            "changed",
            encoding="utf-8",
        )

        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="1 passed\n",
            stderr="",
        )

    monkeypatch.setattr(
        "core.validators.python.subprocess.run",
        fake_run,
    )

    result = execute_pytest_candidate_isolated(
        candidate_path=candidate_path,
        project_root=tmp_path,
        timeout=5,
    )

    assert (
        result.status
        is CandidateValidationStatus.PASSED
    )
    assert result.passed is True
    assert result.errors == ()
    assert result.side_effects == (
        "modified:data.txt",
    )

    assert data_path.read_text(
        encoding="utf-8",
    ) == "original"
