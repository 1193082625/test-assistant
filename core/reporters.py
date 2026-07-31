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
