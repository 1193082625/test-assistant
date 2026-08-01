"""pytest 问题的确定性指纹和聚类。"""

import hashlib
import json
import re
from pathlib import PurePath

from core.models import FailureCluster, PytestIssue


_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_ISO_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+Z?\b"
)
_TEMP_PATH = re.compile(
    r"(?:/private)?/(?:var/(?:folders|tmp)|tmp)/[^\s:'\"]+"
)


def normalize_failure_message(message: str) -> str:
    """去除不稳定的地址、时间戳和随机临时路径。"""
    value = _TEMP_PATH.sub("<tmp-path>", message)
    value = _ADDRESS.sub("<address>", value)
    value = _ISO_TIMESTAMP.sub("<timestamp>", value)
    return " ".join(value.split())


def failure_fingerprint(issue: PytestIssue) -> str:
    """仅从稳定字段生成可跨运行复现的 SHA-256 指纹。"""
    location = None
    if issue.locations:
        first = issue.locations[0]
        location = {
            "file": PurePath(first.path).name,
            "line": first.line,
            "symbol": first.symbol,
        }
    canonical = {
        "phase": issue.phase.value,
        "stage": issue.stage,
        "exception_type": issue.exception_type,
        "location": location,
        "message": normalize_failure_message(issue.message),
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def cluster_pytest_issues(
    issues: tuple[PytestIssue, ...],
) -> tuple[FailureCluster, ...]:
    """过滤非失败事件并以稳定指纹确定性聚类。"""
    grouped: dict[str, list[PytestIssue]] = {}
    for issue in issues:
        if issue.outcome not in {"failed", "error", "timeout"}:
            continue
        fingerprint = failure_fingerprint(issue)
        grouped.setdefault(fingerprint, []).append(issue)

    clusters: list[FailureCluster] = []
    for fingerprint in sorted(grouped):
        members = tuple(sorted(
            grouped[fingerprint],
            key=lambda item: (
                item.node_id is None,
                item.node_id or "",
                item.stage or "",
            ),
        ))
        executable_nodes = sorted({
            issue.node_id
            for issue in members
            if issue.node_id is not None
            and issue.phase.value == "execution"
        })
        clusters.append(FailureCluster(
            fingerprint=fingerprint,
            representative_node=(
                executable_nodes[0] if executable_nodes else None
            ),
            issues=members,
        ))
    return tuple(clusters)
