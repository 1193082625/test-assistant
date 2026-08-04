"""生成不泄漏敏感执行内容的诊断报告。"""

from core.models import Diagnosis


def render_diagnosis_markdown(
    record: dict[str, object],
) -> str:
    diagnosis = Diagnosis.from_dict(record["diagnosis"])
    lines = [
        "# Test Assistant 诊断报告",
        "",
        f"- 时间：{record['created_at']}",
        f"- 分类：`{diagnosis.category.value}`",
        f"- 置信度：`{diagnosis.confidence.value}`",
        f"- Git SHA：`{record.get('git_sha') or 'unknown'}`",
        (
            "- 依赖摘要：`"
            f"{record.get('dependency_digest') or 'unknown'}`"
        ),
        "",
        "## 摘要",
        "",
        diagnosis.summary,
        "",
        "## 证据",
        "",
    ]
    for evidence in diagnosis.evidence:
        lines.append(
            f"- **{evidence.kind.value}**："
            f"{evidence.description}"
        )
        lines.extend(
            f"  - `{detail}`"
            for detail in evidence.details
        )

    lines.extend(["", "## 建议动作", ""])
    lines.extend(
        f"- **{action.kind.value}**：{action.description}"
        for action in diagnosis.suggested_actions
    )
    lines.extend(
        [
            "",
            "## 复现",
            "",
            "```console",
            str(record["reproduction_command"]),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_triage_markdown(record: dict[str, object]) -> str:
    """将已脱敏的 triage repository 记录渲染为简洁报告。"""
    pytest_summary = record["pytest"]
    lines = [
        "# Test Assistant Triage 报告",
        "",
        f"- Run ID：`{record['run_id']}`",
        f"- 时间：{record['created_at']}",
        f"- pytest 退出码：`{pytest_summary['exit_code']}`",
        f"- 失败簇：`{len(record['clusters'])}`",
        "",
        "## pytest 摘要",
        "",
    ]
    counts = pytest_summary.get("status_counts", {})
    if counts:
        lines.extend(
            f"- {status}: {count}"
            for status, count in sorted(counts.items())
        )
    else:
        lines.append("- 没有测试结果")
    lines.extend(["", "## 诊断记录", ""])
    references = record.get("diagnosis_references", [])
    lines.extend(
        f"- `{reference}`" for reference in references
    )
    if not references:
        lines.append("- 无")
    if record.get("truncation", {}).get("occurred"):
        lines.extend([
            "",
            "> 部分运行输出已按安全限制截断。",
        ])
    lines.append("")
    return "\n".join(lines)


def render_audit_markdown(record: dict[str, object]) -> str:
    """从已脱敏 Audit repository 记录生成事实导向报告。"""
    coverage = record.get("coverage")
    lines = [
        "# Test Assistant Audit 报告",
        "",
        f"- Run ID：`{record['run_id']}`",
        f"- 时间：{record['created_at']}",
        f"- 状态：`{record['status']}`",
        f"- 源码摘要：`{record['source_digest']}`",
        "",
        "## 覆盖率",
        "",
    ]
    if isinstance(coverage, dict):
        lines.extend([
            (
                f"- 语句：{coverage['statements_covered']} / "
                f"{coverage['statements_total']}"
            ),
            (
                f"- 分支：{coverage['branches_covered']} / "
                f"{coverage['branches_total']}"
            ),
        ])
    else:
        lines.append("- 未采集")
    lines.extend(["", "## 未覆盖符号", ""])
    gaps = [
        symbol for symbol in record.get("symbols", [])
        if isinstance(symbol, dict)
        and symbol.get("state") in {"partial", "uncovered"}
    ]
    lines.extend(
        f"- `{symbol['source_path']}::{symbol['qualified_name']}` "
        f"({symbol['state']})"
        for symbol in gaps
    )
    if not gaps:
        lines.append("- 无")
    lines.extend(["", "## 静态质量 findings", ""])
    findings = [
        finding for finding in record.get("findings", [])
        if isinstance(finding, dict)
    ]
    lines.extend(
        f"- **{finding['tool']}** `{finding.get('rule_code') or 'unknown'}` "
        f"{finding.get('source_path') or '<configuration>'}:"
        f"{finding.get('line') or '-'} — {finding['message']}"
        for finding in findings
    )
    if not findings:
        lines.append("- 无")
    lines.extend(["", "## Adapter 状态", ""])
    lines.extend(
        f"- {tool['tool']}: `{tool['state']}`"
        + (f" — {tool['reason']}" if tool.get("reason") else "")
        for tool in record.get("tools", [])
        if isinstance(tool, dict)
    )
    lines.append("")
    return "\n".join(lines)
