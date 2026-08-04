"""Ruff 与 mypy 结构化输出到统一 QualityFinding 的转换。"""

import re
from pathlib import Path

from core.models import QualityFinding, QualityFindingKind


def _relative_source_path(filename: object, project_root: Path) -> str:
    if not isinstance(filename, str) or not filename:
        raise ValueError("quality finding 缺少源码路径")
    candidate = Path(filename)
    path = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError as error:
        raise ValueError("quality finding 源码路径必须位于项目内") from error


def parse_ruff_findings(
    payload: object,
    *,
    project_root: str | Path,
) -> tuple[QualityFinding, ...]:
    """解析 Ruff JSON；未知规则仍作为事实保留。"""
    if not isinstance(payload, list):
        raise ValueError("Ruff JSON 根节点必须是列表")
    root = Path(project_root).resolve()
    findings: list[QualityFinding] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Ruff finding 必须是对象")
        location = item.get("location")
        if not isinstance(location, dict):
            raise ValueError("Ruff finding 缺少位置")
        row = location.get("row")
        column = location.get("column")
        if (
            isinstance(row, bool)
            or not isinstance(row, int)
            or row < 1
            or isinstance(column, bool)
            or not isinstance(column, int)
            or column < 1
        ):
            raise ValueError("Ruff finding 位置无效")
        message = item.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Ruff finding 缺少消息")
        code = item.get("code")
        if code is not None and not isinstance(code, str):
            raise ValueError("Ruff finding 规则无效")
        findings.append(QualityFinding(
            tool="ruff",
            kind=QualityFindingKind.CODE,
            rule_code=code,
            message=message,
            source_path=_relative_source_path(item.get("filename"), root),
            line=row,
            column=column,
            fix_available=item.get("fix") is not None,
        ))
    return tuple(sorted(
        findings,
        key=lambda finding: (
            finding.source_path or "",
            finding.line or 0,
            finding.column or 0,
            finding.rule_code or "",
        ),
    ))


_MYPY_LINE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+)(?::(?P<column>\d+))?: "
    r"(?P<severity>error|note): (?P<message>.*?)"
    r"(?:  \[(?P<code>[^\]]+)\])?$"
)
_DEPENDENCY_CODES = {"import", "import-not-found", "import-untyped"}


def parse_mypy_findings(
    output: str,
    *,
    project_root: str | Path,
) -> tuple[QualityFinding, ...]:
    """解析由固定 mypy flags 产生的稳定文本，只保留 error。"""
    root = Path(project_root).resolve()
    findings: list[QualityFinding] = []
    for line_text in output.splitlines():
        match = _MYPY_LINE.fullmatch(line_text.strip())
        if match is None or match.group("severity") != "error":
            continue
        code = match.group("code")
        kind = (
            QualityFindingKind.DEPENDENCY
            if code in _DEPENDENCY_CODES
            else QualityFindingKind.CODE
        )
        findings.append(QualityFinding(
            tool="mypy",
            kind=kind,
            rule_code=code,
            message=match.group("message"),
            source_path=_relative_source_path(match.group("path"), root),
            line=int(match.group("line")),
            column=(
                int(match.group("column"))
                if match.group("column") is not None
                else None
            ),
            fix_available=False,
        ))
    return tuple(sorted(
        findings,
        key=lambda finding: (
            finding.source_path or "",
            finding.line or 0,
            finding.column or 0,
            finding.rule_code or "",
        ),
    ))
