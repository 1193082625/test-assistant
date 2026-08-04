"""为 changed-only 审计收集本地、只读的变更证据。"""

from dataclasses import dataclass
from pathlib import Path
import subprocess

from core.analyzers.snapshot import (
    compare_python_symbol_snapshots,
    compare_snapshots,
    read_snapshot_manifest,
    take_snapshot,
)
from core.repositories.permissions import GitPermissionRepository


@dataclass(frozen=True)
class ChangeEvidence:
    source: str
    paths: tuple[str, ...]
    qualified_names: tuple[str, ...]


def collect_change_evidence(project_root: str | Path) -> ChangeEvidence:
    """优先返回快照符号差异，否则返回已授权的 Git 文件差异。"""
    root = Path(project_root).resolve()
    snapshot_path = root / ".autotest" / "snapshot.json"
    if snapshot_path.is_file():
        baseline = read_snapshot_manifest(str(snapshot_path)).files
        current, _ = take_snapshot(
            str(root),
            [".autotest", ".git", ".venv", "venv", "node_modules"],
        )
        changed_files = compare_snapshots(baseline, current)
        symbol_changes = compare_python_symbol_snapshots(
            baseline, current, changed_files
        )
        paths = tuple(sorted({
            path
            for category in ("added", "modified")
            for path in changed_files[category]
            if path.endswith(".py")
        }))
        names = tuple(sorted(set(
            symbol_changes.added + symbol_changes.modified
        )))
        return ChangeEvidence("snapshot", paths, names)

    permission = GitPermissionRepository(root)
    if not permission.is_granted():
        raise ValueError(
            "--changed-only 需要 snapshot 或已授权的本地 Git 只读证据"
        )
    try:
        tracked = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=AM", "HEAD", "--"],
            cwd=root, capture_output=True, text=True, timeout=10,
            check=False, shell=False,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, timeout=10,
            check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("无法读取本地 Git 变更证据") from error
    if tracked.returncode != 0 or untracked.returncode != 0:
        raise ValueError("无法读取本地 Git 变更证据")
    paths = tuple(sorted({
        line.strip()
        for output in (tracked.stdout, untracked.stdout)
        for line in output.splitlines()
        if line.strip().endswith(".py")
    }))
    return ChangeEvidence("git", paths, ())
