import json

from click.testing import CliRunner

from cli.main import cli


def _write_diagnosis(path):
    path.write_text(
        json.dumps(
            {
                "summary": "产品行为违反强契约",
                "category": "product_defect",
                "confidence": "high",
                "evidence": [
                    {
                        "kind": "contract",
                        "description": "Schema 明确返回值",
                        "source": "test_spec",
                        "details": ["expectation_strength=strong"],
                    },
                ],
                "locations": [
                    {
                        "path": "demo.py",
                        "line": 3,
                        "column": None,
                        "symbol": "demo.add",
                    },
                ],
                "suggested_actions": [
                    {
                        "kind": "inspect_product",
                        "description": "检查目标实现",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_diagnose_explains_saved_diagnosis(tmp_path):
    diagnosis_path = tmp_path / "diagnosis.json"
    _write_diagnosis(diagnosis_path)

    result = CliRunner().invoke(
        cli,
        ["diagnose", "--input", str(diagnosis_path)],
    )

    assert result.exit_code == 0, result.output
    assert "product_defect" in result.output
    assert "high" in result.output
    assert "Schema 明确返回值" in result.output
    assert "检查目标实现" in result.output
    assert str(diagnosis_path) in result.output


def test_status_reads_latest_project_diagnosis(tmp_path):
    diagnosis_dir = tmp_path / ".autotest" / "diagnoses"
    diagnosis_dir.mkdir(parents=True)
    _write_diagnosis(diagnosis_dir / "latest.json")

    result = CliRunner().invoke(
        cli,
        ["status", "--path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "需要处理" in result.output
    assert "product_defect" in result.output
    assert "high" in result.output


def test_status_is_unknown_without_diagnosis(tmp_path):
    result = CliRunner().invoke(
        cli,
        ["status", "--path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "暂无诊断记录" in result.output
