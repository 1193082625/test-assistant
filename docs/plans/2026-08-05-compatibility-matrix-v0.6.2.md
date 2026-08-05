# Compatibility Matrix v0.6.2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用可重复的路径测试、机器可读支持清单和 Ubuntu/macOS wheel 消费矩阵，证明 test-assistant v0.6.2 的受支持边界。

**Architecture:** Doctor 继续保持 v0.6.1 的只读模型和命令语义；v0.6.2 不增加环境修复功能，只增加系统性兼容证据。CI 只构建一次 wheel，再由平台矩阵下载同一产物；兼容性文档由仓库内 JSON 清单确定性生成，避免人工表格与 CI 分叉。

**Tech Stack:** Python 3.13、Click、pytest、GitHub Actions、JSON、Markdown。

**完成状态（2026-08-05）：** 全量 824 项测试、构建、产物内容检查和本地干净 wheel smoke 通过；同一 v0.6.2 wheel 已在 Ubuntu/macOS Python 3.13 GitHub Actions matrix 中通过，`v0.6.2` Tag 已发布。Python 3.14 probe 保持非阻塞，Windows 保持 unsupported。

---

### Task 1: 固定特殊路径与只读边界

**Files:**
- Create: `tests/test_path_compatibility.py`
- Modify: `tests/test_cli_end_to_end.py` only if a real subprocess gap remains
- Modify: `cli/commands/doctor.py` or `core/workflows/doctor.py` only when a failing test proves a defect

**Steps:**

1. Add real CLI subprocess tests for spaces, Chinese characters, a long nested path, a project-directory symlink, a broken symlink, a non-Git directory and a read-only project.
2. Snapshot paths and file bytes before/after every successful Doctor invocation.
3. Run `poetry run pytest tests/test_path_compatibility.py tests/test_cli_end_to_end.py -q`; confirm failures before any production fix.
4. Fix only demonstrated path or read-only defects, then rerun the same tests.

### Task 2: Generate the compatibility support table

**Files:**
- Create: `docs/compatibility.json`
- Create: `scripts/generate_compatibility_table.py`
- Create: `docs/compatibility.md`
- Create: `tests/test_compatibility_manifest.py`

**Steps:**

1. Define schema version 1 with `supported`, `experimental`, and `unsupported` entries for OS, Python, pytest and path capabilities.
2. Validate unique non-empty identifiers, stable states and non-empty evidence/reason fields.
3. Generate Markdown deterministically from JSON and provide `--check` mode that never writes.
4. Test schema rejection, deterministic generation and checked-in document freshness.
5. Run `poetry run pytest tests/test_compatibility_manifest.py -q` and `poetry run python scripts/generate_compatibility_table.py --check`.

### Task 3: Consume one wheel on Ubuntu and macOS

**Files:**
- Modify: `.github/workflows/ci.yml`

**Steps:**

1. Keep the Python 3.13 source test job.
2. Add a build job that creates wheel/sdist once and uploads `dist/`.
3. Add an Ubuntu/macOS matrix job that downloads the same artifact, creates a clean Python 3.13 venv, installs the wheel and pytest, and verifies import origin, `--version`, `doctor --help`, text/JSON Doctor and project immutability.
4. Add a non-blocking Python 3.14 probe that installs with `--ignore-requires-python` and expects Doctor to report `incompatible`; it must not mark 3.14 supported.
5. Run a local structural test of the workflow where possible; final matrix evidence comes from GitHub Actions.

### Task 4: Update version and user-facing support claims

**Files:**
- Modify: `pyproject.toml`
- Modify: `poetry.lock`
- Modify: `cli/__init__.py`
- Modify: `tests/test_cli_version.py`
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/project-structure.md`
- Modify: `docs/plans/2026-08-04-version-roadmap-v0.6-v1.0.md`
- Modify: `docs/plans/2026-08-04-compatibility-and-doctor-v0.6.x.md`

**Steps:**

1. Change the exact CLI/package version to `0.6.2` while retaining Python `>=3.13,<3.14`.
2. Link the generated compatibility table and state that macOS/Ubuntu support is certified only after the matrix is green.
3. Keep Windows and Python 3.14 explicitly unsupported/experimental.
4. Record the completed v0.6.1 wheel and `fitstyle-backend` read-only evidence.
5. Run `poetry lock`, `poetry check`, and `poetry run pytest tests/test_cli_version.py tests/test_cli_doctor.py -q`.

### Task 5: Release verification

**Files:**
- Modify production or CI files only for failures demonstrated by verification

**Steps:**

1. Run `poetry run python -m compileall -q cli core scripts tests`.
2. Run `poetry check`, `poetry run pytest -q`, and `git diff --check`.
3. Build wheel/sdist and confirm v0.6.2 metadata, entry point, contents and absence of tests, `.autotest`, `.env`, local absolute paths and real project data.
4. Install only the wheel in a clean Python 3.13 environment, then add pytest and run text/JSON Doctor against a minimal fixture.
5. Confirm the fixture is byte-for-byte unchanged and remove all temporary directories.

## Completion criteria

- The same wheel is consumed on Ubuntu and macOS Python 3.13.
- Spaces, Chinese, long paths, symlink inputs, non-Git projects and read-only projects have deterministic Doctor evidence.
- `docs/compatibility.md` is generated from a validated manifest and CI can detect drift.
- Windows and Python 3.14 are not advertised as supported.
- Full tests, packaging checks and clean-wheel smoke pass without changing the target fixture.

## Release evidence

- Source and compatibility tests: `824 passed`.
- Package metadata: `test-assistant 0.6.2`, Python `>=3.13,<3.14`.
- Clean local wheel smoke: text/JSON Doctor healthy; fixture paths and bytes unchanged.
- GitHub Actions: Ubuntu and macOS consumed the same uploaded wheel artifact successfully.
- Published tag: `v0.6.2`.
