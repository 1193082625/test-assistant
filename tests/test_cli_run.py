from click.testing import CliRunner
from langchain_core.messages import AIMessage
from cli.commands.run import run as run_command

def test_run_command_consumes_graph_result(tmp_path, monkeypatch):
    autotest_path = tmp_path / ".autotest"
    unit_path = autotest_path / "test_cases" / "unit"
    unit_path.mkdir(parents=True)

    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  type: backend\n"
            "  language: python\n"
            "  frameworks:\n"
            "    - FastAPI\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    def fake_run_graph(project_path):
        assert project_path == str(tmp_path)

        return {
            "changed_files": {
                "added": [],
                "deleted": [],
                "modified": [],
            },
            "execution_reports_by_file": {},
            "messages": [
                AIMessage(content="执行完成")
            ],
            "errors": []
        }

    monkeypatch.setattr("cli.commands.run.run_graph", fake_run_graph)

    runner = CliRunner()
    result = runner.invoke(
        run_command,
        ["--path", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert "执行完成" in result.output