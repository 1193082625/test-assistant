"""静态质量 finding 解析测试。"""

import pytest

from core.analyzers.quality import parse_ruff_findings


def test_parse_ruff_findings_preserves_rule_location_and_fix(tmp_path):
    payload = [{
        "code": "F401",
        "message": "os imported but unused",
        "filename": str(tmp_path / "app.py"),
        "location": {"row": 2, "column": 1},
        "fix": {"applicability": "safe", "edits": []},
    }]

    findings = parse_ruff_findings(payload, project_root=tmp_path)

    assert findings[0].rule_code == "F401"
    assert findings[0].source_path == "app.py"
    assert findings[0].line == 2
    assert findings[0].fix_available is True


def test_parse_ruff_findings_keeps_unknown_rule(tmp_path):
    payload = [{
        "code": None,
        "message": "unknown diagnostic",
        "filename": "app.py",
        "location": {"row": 1, "column": 1},
        "fix": None,
    }]

    findings = parse_ruff_findings(payload, project_root=tmp_path)

    assert findings[0].rule_code is None


def test_parse_ruff_findings_rejects_outside_path(tmp_path):
    payload = [{
        "code": "F401",
        "message": "unused",
        "filename": str(tmp_path.parent / "outside.py"),
        "location": {"row": 1, "column": 1},
        "fix": None,
    }]

    with pytest.raises(ValueError, match="源码路径必须位于项目内"):
        parse_ruff_findings(payload, project_root=tmp_path)

