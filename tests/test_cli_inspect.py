from click.testing import CliRunner
from cli.main import cli
from core.analyzers.snapshot import (
    commit_snapshot_manifest,
    take_snapshot
)

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

def test_inspect_explains_test_selection(tmp_path):
    source_path = tmp_path / "demo.py"
    source_path.write_text(
        (
            "def add(a: int, b: int) -> int:\n"
            '    """返回两个整数之和。"""\n'
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()
    (tests_path / "test_demo.py").write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    snapshots, skipped = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()
    commit_snapshot_manifest(
        str(autotest_path / "snapshot.json"),
        snapshots
    )
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

    source_path.write_text(
        (
            "def add(a: int, b: int) -> int:\n"
            '    """返回两个整数之和。"""\n'
            "    return a - b\n"
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inspect", "--path", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert "测试选择: direct" in result.output
    assert "分析精度: symbol" in result.output
    assert "tests/test_demo.py" in result.output
    assert "demo.add ->" in result.output
    assert "变更符号:" in result.output
    assert "demo.add [function, direct]" in result.output

    assert "契约证据:" in result.output
    assert "docstring, medium" in result.output
    assert "返回两个整数之和。" in result.output
    assert "type_hint, medium" in result.output
    assert "add(a: int, b: int) -> int" in result.output
    assert (
       "测试文件:\n"
       "  - tests/test_demo.py"
    ) in result.output
    assert "选择证据:" in result.output

def test_inspect_reports_invalid_snapshot_format(tmp_path):
    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()

    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  language: python\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )
    (autotest_path / "snapshot.json").write_text(
        "[]\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inspect", "--path", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert (
        "无法读取项目快照: "
        "快照格式无效: 根节点必须是映射"
    ) in result.output
    assert "Traceback" not in result.output

def test_inspect_explains_src_layout_selection(tmp_path):
    source_path = tmp_path / "src" / "demo.py"
    source_path.parent.mkdir()
    source_path.write_text(
        (
            "def add(a: int, b: int) -> int:\n"
            '    """返回两个整数之和。"""\n'
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    tests_path = tmp_path / "tests"
    tests_path.mkdir()
    (tests_path / "test_demo.py").write_text(
        (
            "from demo import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        encoding="utf-8",
    )

    snapshots, skipped = take_snapshot(
        str(tmp_path),
        excludes=[".autotest"],
    )
    assert skipped == 0

    autotest_path = tmp_path / ".autotest"
    autotest_path.mkdir()
    commit_snapshot_manifest(
        str(autotest_path / "snapshot.json"),
        snapshots,
    )
    (autotest_path / "config.yml").write_text(
        (
            "project:\n"
            "  name: src-demo\n"
            "  language: python\n"
            "  test_frameworks:\n"
            "    - pytest\n"
        ),
        encoding="utf-8",
    )

    source_path.write_text(
        (
            "def add(a: int, b: int) -> int:\n"
            '    """返回两个整数之和。"""\n'
            "    return a - b\n"
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inspect", "--path", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "项目: src-demo" in result.output
    assert "demo.add [function, direct]" in result.output
    assert "测试选择: direct" in result.output
    assert "tests/test_demo.py" in result.output
    assert "demo.add ->" in result.output
