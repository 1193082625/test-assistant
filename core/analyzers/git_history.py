"""授权后使用的本地只读 Git 符号历史证据。"""

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class GitSymbolHistory:
    symbol: str
    available: bool
    was_added: bool = False
    was_deleted: bool = False
    deletion_commit: str | None = None
    commits: tuple[str, ...] = ()
    degradation_reason: str | None = None

    @property
    def removal_confirmed(self) -> bool:
        return self.available and self.was_added and self.was_deleted


@dataclass(frozen=True)
class GitContractHistory:
    """同一提交中删除旧契约并加入新契约的最小历史证据。"""

    available: bool
    old_expression: str
    new_expression: str
    migration_commit: str | None = None
    old_expression_summary: str | None = None
    new_expression_summary: str | None = None
    commits: tuple[str, ...] = ()
    degradation_reason: str | None = None

    @property
    def migration_confirmed(self) -> bool:
        return self.available and self.migration_commit is not None


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in path.parts
    ):
        raise ValueError("Git 证据路径必须是项目内相对路径")
    return path.as_posix()


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    timeout: float,
    output_limit: int,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    if len(completed.stdout) > output_limit:
        completed.stdout = completed.stdout[:output_limit]
    if len(completed.stderr) > output_limit:
        completed.stderr = completed.stderr[:output_limit]
    return completed


def read_symbol_history(
    *,
    project_root: str | Path,
    symbol: str,
    source_paths: tuple[str, ...],
    timeout: float = 5,
    output_limit: int = 50_000,
) -> GitSymbolHistory:
    """用 pickaxe 查找符号新增和删除；任何失败都结构化降级。"""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Git 证据 symbol 不能为空")
    if len(symbol) > 500 or "\x00" in symbol:
        raise ValueError("Git 证据 symbol 不安全")
    paths = tuple(_safe_relative_path(path) for path in source_paths)
    if not paths:
        raise ValueError("Git 证据 source_paths 不能为空")
    root = Path(project_root).resolve()
    try:
        history = _run_git(
            root,
            ["log", "--format=%H", "-S", symbol, "--", *paths],
            timeout=timeout,
            output_limit=output_limit,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return GitSymbolHistory(
            symbol=symbol,
            available=False,
            degradation_reason=type(error).__name__,
        )
    if history.returncode != 0:
        return GitSymbolHistory(
            symbol=symbol,
            available=False,
            degradation_reason="git_log_failed",
        )
    commits = tuple(
        line.strip() for line in history.stdout.splitlines()
        if line.strip()
    )[:50]
    was_added = False
    was_deleted = False
    deletion_commit = None
    for commit in commits:
        if not all(character in "0123456789abcdefABCDEF" for character in commit):
            continue
        try:
            shown = _run_git(
                root,
                ["show", "--format=", "--unified=0", commit, "--", *paths],
                timeout=timeout,
                output_limit=output_limit,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if shown.returncode != 0:
            continue
        for line in shown.stdout.splitlines():
            if symbol not in line:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                was_added = True
            elif line.startswith("-") and not line.startswith("---"):
                was_deleted = True
                if deletion_commit is None:
                    deletion_commit = commit
    return GitSymbolHistory(
        symbol=symbol,
        available=True,
        was_added=was_added,
        was_deleted=was_deleted,
        deletion_commit=deletion_commit,
        commits=commits,
    )


def _safe_expression(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 500
        or "\x00" in value
        or "\n" in value
    ):
        raise ValueError(f"Git {label}契约表达式不安全")
    return value.strip()


def read_contract_history(
    *,
    project_root: str | Path,
    old_expression: str,
    new_expression: str,
    source_paths: tuple[str, ...],
    timeout: float = 5,
    output_limit: int = 50_000,
) -> GitContractHistory:
    """只读确认同一提交完成旧→新迁移；不根据提交信息推测意图。"""
    old = _safe_expression(old_expression, "旧")
    new = _safe_expression(new_expression, "新")
    paths = tuple(_safe_relative_path(path) for path in source_paths)
    if not paths:
        raise ValueError("Git 证据 source_paths 不能为空")
    root = Path(project_root).resolve()
    commits: list[str] = []
    try:
        for expression in (old, new):
            completed = _run_git(
                root,
                ["log", "--format=%H", "-S", expression, "--", *paths],
                timeout=timeout,
                output_limit=output_limit,
            )
            if completed.returncode != 0:
                return GitContractHistory(
                    available=False,
                    old_expression=old,
                    new_expression=new,
                    degradation_reason="git_log_failed",
                )
            for line in completed.stdout.splitlines():
                commit = line.strip()
                if commit and commit not in commits:
                    commits.append(commit)
    except (OSError, subprocess.TimeoutExpired) as error:
        return GitContractHistory(
            available=False,
            old_expression=old,
            new_expression=new,
            degradation_reason=type(error).__name__,
        )
    valid_commits = tuple(
        commit for commit in commits[:50]
        if len(commit) >= 7
        and all(character in "0123456789abcdefABCDEF" for character in commit)
    )
    for commit in valid_commits:
        try:
            shown = _run_git(
                root,
                ["show", "--format=", "--unified=0", commit, "--", *paths],
                timeout=timeout,
                output_limit=output_limit,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if shown.returncode != 0 or "Binary files" in shown.stdout:
            continue
        removed_old = any(
            line.startswith("-")
            and not line.startswith("---")
            and old in line
            for line in shown.stdout.splitlines()
        )
        added_new = any(
            line.startswith("+")
            and not line.startswith("+++")
            and new in line
            for line in shown.stdout.splitlines()
        )
        if removed_old and added_new:
            return GitContractHistory(
                available=True,
                old_expression=old,
                new_expression=new,
                migration_commit=commit,
                old_expression_summary=old[:200],
                new_expression_summary=new[:200],
                commits=valid_commits,
            )
    return GitContractHistory(
        available=True,
        old_expression=old,
        new_expression=new,
        commits=valid_commits,
        degradation_reason="migration_not_confirmed",
    )
