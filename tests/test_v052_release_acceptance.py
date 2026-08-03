"""v0.5.2 契约迁移能力的真实 CLI 黑盒发布验收。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).parents[1]


@dataclass(frozen=True)
class AcceptanceCase:
    name: str
    before: dict[str, str]
    current: dict[str, str]
    test_source: str
    expected_category: str
    expected_confidence: str
    migration_type: str
    use_git: bool = True
    expected_clusters: int = 1


def _cases() -> tuple[AcceptanceCase, ...]:
    return (
        AcceptanceCase(
            name="conflicting_undo_contract",
            before={
                "app/config.py": "CLOTHING_DELETE_UNDO_SECONDS = 120\n",
                "app/service.py": (
                    "class ClothingDeleteService:\n"
                    "    UNDO_EXPIRES_SECONDS = 10\n"
                ),
                "app/schema.py": "UNDO_EXPIRES_SECONDS = 10\n",
            },
            current={
                "app/config.py": "CLOTHING_DELETE_UNDO_SECONDS = 120\n",
                "app/service.py": (
                    "from app import config\n\n"
                    "class ClothingDeleteService:\n"
                    "    UNDO_EXPIRES_SECONDS = "
                    "config.CLOTHING_DELETE_UNDO_SECONDS\n"
                ),
                "app/schema.py": "UNDO_EXPIRES_SECONDS = 10\n",
            },
            test_source=(
                "from app.service import ClothingDeleteService\n\n"
                "def test_undo_window():\n"
                "    assert ClothingDeleteService.UNDO_EXPIRES_SECONDS == 10\n"
            ),
            expected_category="inconclusive",
            expected_confidence="low",
            migration_type="config_default",
        ),
        AcceptanceCase(
            name="config_default_migration",
            before={
                "app/config.py": "DEFAULT_PAGE_SIZE = 10\n",
                "app/schema.py": (
                    "from app import config\n\n"
                    "class PaginationParams:\n"
                    "    page_size = config.DEFAULT_PAGE_SIZE\n"
                ),
            },
            current={
                "app/config.py": "DEFAULT_PAGE_SIZE = 20\n",
                "app/schema.py": (
                    "from app import config\n\n"
                    "class PaginationParams:\n"
                    "    page_size = config.DEFAULT_PAGE_SIZE\n"
                ),
            },
            test_source=(
                "from app.schema import PaginationParams\n\n"
                "def test_default_page_size():\n"
                "    assert PaginationParams.page_size == 10\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="config_default",
        ),
        AcceptanceCase(
            name="field_type_migration",
            before={
                "app/model.py": "class Topic:\n    id: int\n",
                "app/schema.py": (
                    "from pydantic import BaseModel\n\n"
                    "class TopicResponse(BaseModel):\n    id: int\n"
                ),
            },
            current={
                "app/model.py": "class Topic:\n    id: str\n",
                "app/schema.py": (
                    "from pydantic import BaseModel\n\n"
                    "class TopicResponse(BaseModel):\n    id: str\n"
                ),
            },
            test_source=(
                "from app.schema import TopicResponse\n\n"
                "def test_legacy_integer_id():\n"
                "    TopicResponse.model_validate({'id': 1})\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="field_type",
        ),
        AcceptanceCase(
            name="optional_field_fixture_drift",
            before={
                "app/model.py": (
                    "OPTIONAL_FIELD_CONTRACT = 'MagicMock'\n\n"
                    "class Fragrance:\n    purchase_url: object = None\n"
                ),
                "app/schema.py": (
                    "from pydantic import BaseModel\n\n"
                    "OPTIONAL_FIELD_CONTRACT = 'MagicMock'\n\n"
                    "class FragranceResponse(BaseModel):\n"
                    "    purchase_url: object = None\n"
                ),
            },
            current={
                "app/model.py": (
                    "OPTIONAL_FIELD_CONTRACT = 'str | None'\n\n"
                    "class Fragrance:\n    purchase_url: str | None = None\n"
                ),
                "app/schema.py": (
                    "from pydantic import BaseModel\n\n"
                    "OPTIONAL_FIELD_CONTRACT = 'str | None'\n\n"
                    "class FragranceResponse(BaseModel):\n"
                    "    purchase_url: str | None = None\n"
                ),
            },
            test_source=(
                "from unittest.mock import MagicMock\n"
                "from app.model import Fragrance\n"
                "from app.schema import FragranceResponse\n\n"
                "def test_old_fixture_omits_optional_field():\n"
                "    fixture = MagicMock(spec=Fragrance)\n"
                "    FragranceResponse.model_validate({\n"
                "        'purchase_url': fixture.purchase_url,\n"
                "    })\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="optional_fields",
        ),
        AcceptanceCase(
            name="related_config_migration",
            before={
                "app/config.py": (
                    "COVER_IMAGE_WIDTH = 800\nCOVER_IMAGE_HEIGHT = 1200\n"
                ),
                "app/composition.py": (
                    "from app import config\n"
                    "CANVAS_WIDTH = config.COVER_IMAGE_WIDTH\n"
                    "CANVAS_HEIGHT = config.COVER_IMAGE_HEIGHT\n"
                ),
            },
            current={
                "app/config.py": (
                    "COVER_IMAGE_WIDTH = 840\nCOVER_IMAGE_HEIGHT = 1040\n"
                ),
                "app/composition.py": (
                    "from app import config\n"
                    "CANVAS_WIDTH = config.COVER_IMAGE_WIDTH\n"
                    "CANVAS_HEIGHT = config.COVER_IMAGE_HEIGHT\n"
                ),
            },
            test_source=(
                "from app import config\n\n"
                "def test_legacy_width():\n"
                "    assert config.COVER_IMAGE_WIDTH == 800\n\n"
                "def test_legacy_height():\n"
                "    assert config.COVER_IMAGE_HEIGHT == 1200\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="related_config",
            expected_clusters=1,
        ),
        AcceptanceCase(
            name="enum_contract_migration",
            before={
                "app/schema.py": (
                    "from typing import Literal\n"
                    "from pydantic import BaseModel\n\n"
                    "class Request(BaseModel):\n"
                    "    layout: Literal['auto', 'vertical', 'grid']\n"
                ),
                "app/router.py": "PUBLIC_LAYOUTS = ('vertical', 'grid')\n",
            },
            current={
                "app/schema.py": (
                    "from typing import Literal\n"
                    "from pydantic import BaseModel\n\n"
                    "class Request(BaseModel):\n"
                    "    layout: Literal['auto', 'left-right']\n"
                ),
                "app/router.py": "PUBLIC_LAYOUTS = ('left-right',)\n",
            },
            test_source=(
                "from app.schema import Request\n\n"
                "def test_legacy_grid_layout():\n"
                "    Request(layout='grid')\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="enum_values",
        ),
        AcceptanceCase(
            name="async_mock_result_contract",
            before={},
            current={
                "app/service.py": (
                    "async def lookup(db):\n"
                    "    result = await db.execute('select')\n"
                    "    return result.scalar_one_or_none()\n"
                ),
            },
            test_source=(
                "import asyncio\nimport gc\n"
                "from unittest.mock import AsyncMock\n"
                "from app.service import lookup\n\n"
                "def test_unconfigured_result():\n"
                "    async def exercise():\n"
                "        db = AsyncMock()\n"
                "        return await lookup(db)\n"
                "    value = asyncio.run(exercise())\n"
                "    del value\n    gc.collect()\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="async_mock_result",
            use_git=False,
        ),
        AcceptanceCase(
            name="async_generator_lifecycle",
            before={},
            current={
                "app/dependency.py": (
                    "async def get_db():\n"
                    "    try:\n        yield object()\n"
                    "    finally:\n        pass\n"
                ),
            },
            test_source=(
                "import asyncio\nimport gc\n"
                "from app.dependency import get_db\n\n"
                "def test_generator_lifecycle():\n"
                "    async def exercise():\n"
                "        gen = get_db()\n"
                "        return gen.__anext__()\n"
                "    session = asyncio.run(exercise())\n"
                "    del session\n    gc.collect()\n"
            ),
            expected_category="test_defect",
            expected_confidence="high",
            migration_type="async_generator_lifecycle",
            use_git=False,
        ),
    )


def _write_files(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )


def _commit(root: Path, message: str) -> None:
    _git(root, "add", ".")
    _git(
        root,
        "-c", "user.name=Acceptance",
        "-c", "user.email=acceptance@example.com",
        "commit", "-q", "-m", message,
    )


def _prepare_project(root: Path, case: AcceptanceCase) -> None:
    root.mkdir()
    _write_files(root, {"app/__init__.py": ""})
    if case.use_git:
        _write_files(root, case.before)
        _write_files(root, {"tests/test_case.py": case.test_source})
        _git(root, "init", "-q")
        _commit(root, "before contract migration")
        _write_files(root, case.current)
        _commit(root, "apply contract migration")
    else:
        _write_files(root, case.current)
        _write_files(root, {
            "tests/test_case.py": case.test_source,
            "pytest.ini": "[pytest]\nfilterwarnings = error\n",
        })


def _protected_state(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for base in (root / "app", root / "tests")
        for path in base.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.name)
def test_v052_real_cli_contract_migration_acceptance(tmp_path, case):
    project = tmp_path / case.name
    _prepare_project(project, case)
    before = _protected_state(project)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    command = [
        sys.executable,
        "-m",
        "cli.main",
        "triage",
        "--path",
        str(project),
        "--test-path",
        "tests/test_case.py",
        "--timeout",
        "30",
        (
            "--allow-git-history"
            if case.use_git
            else "--no-git-history"
        ),
    ]

    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 1, output
    assert f"[{1}] {case.expected_category}" in output
    assert f"置信度: {case.expected_confidence}" in output
    assert f"迁移类型: {case.migration_type}" in output
    assert f"失败簇: {case.expected_clusters}" in output
    record_path = project / ".autotest/triage/latest.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert len(record["clusters"]) == case.expected_clusters
    migrations = record["contract_migrations"]
    assert migrations[0]["category"] == case.expected_category
    assert migrations[0]["confidence"] == case.expected_confidence
    assert migrations[0]["migration_type"] == case.migration_type
    if case.use_git and case.expected_confidence == "high":
        assert len(migrations[0]["migration_commit"]) == 40
    if not case.use_git:
        assert "migration_commit" not in migrations[0]
    assert _protected_state(project) == before


def _run_cli(project: Path, *, allow_git: bool) -> tuple[str, dict]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "triage",
            "--path",
            str(project),
            "--test-path",
            "tests/test_case.py",
            "--timeout",
            "30",
            "--allow-git-history" if allow_git else "--no-git-history",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    record = json.loads(
        (project / ".autotest/triage/latest.json").read_text(encoding="utf-8")
    )
    return completed.stdout + completed.stderr, record


def test_historical_migration_without_git_permission_stays_inconclusive(
    tmp_path,
):
    case = next(item for item in _cases() if item.name == "config_default_migration")
    project = tmp_path / "no-git-permission"
    _prepare_project(project, case)

    output, record = _run_cli(project, allow_git=False)

    assert "[1] inconclusive" in output
    assert "置信度: low" in output
    migration = record["contract_migrations"][0]
    assert migration["category"] == "inconclusive"
    assert "migration_commit" not in migration
    assert record["git_history"]["enabled"] is False


def test_production_missing_await_is_not_blame_on_test(tmp_path):
    project = tmp_path / "production-missing-await"
    project.mkdir()
    _write_files(project, {
        "app/__init__.py": "",
        "app/service.py": (
            "async def lookup(db):\n"
            "    result = db.execute('select')\n"
            "    return result.scalar_one_or_none()\n"
        ),
        "tests/test_case.py": (
            "import asyncio\n"
            "from unittest.mock import AsyncMock\n"
            "from app.service import lookup\n\n"
            "def test_lookup():\n"
            "    db = AsyncMock()\n"
            "    asyncio.run(lookup(db))\n"
        ),
        "pytest.ini": "[pytest]\nfilterwarnings = error\n",
    })

    output, _ = _run_cli(project, allow_git=False)

    assert "[1] inconclusive" in output
    assert "[1] test_defect" not in output


def test_production_generator_cleanup_failure_is_not_blame_on_test(tmp_path):
    project = tmp_path / "production-generator-cleanup"
    project.mkdir()
    _write_files(project, {
        "app/__init__.py": "",
        "app/dependency.py": (
            "async def get_db():\n"
            "    try:\n        yield object()\n"
            "    finally:\n        raise RuntimeError('cleanup failed')\n"
        ),
        "tests/test_case.py": (
            "import asyncio\n"
            "from app.dependency import get_db\n\n"
            "def test_cleanup():\n"
            "    async def exercise():\n"
            "        gen = get_db()\n"
            "        await anext(gen)\n"
            "        await gen.aclose()\n"
            "    asyncio.run(exercise())\n"
        ),
    })

    output, _ = _run_cli(project, allow_git=False)

    assert "[1] inconclusive" in output
    assert "[1] test_defect" not in output
