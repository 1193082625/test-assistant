from click.testing import CliRunner
from cli.main import cli

def test_inspect_requires_initialized_project(tmp_path):
    """测试 对未初始化项目返回明确错误"""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inspect", "--path", str(tmp_path)]
    )

    assert result.exit_code == 1
    assert (
        "未找到 .autotest/config.yml；"
        in result.output
    )
    assert (
        "请先运行 test-assistant init"
        in result.output
    )

def test_inspect_displays_project_capabilities(tmp_path):
    """测试 inspect 展示初始化配置中的基础能力"""
    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  name: demo\n"
            "  language: python\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inspect", "--path", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert "项目: demo" in result.output
    assert "语言: python" in result.output
    assert "测试框架: pytest" in result.output