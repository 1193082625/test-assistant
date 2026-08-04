from click.testing import CliRunner

from cli.main import cli


def test_root_cli_exposes_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output == "test-assistant, version 0.6.0\n"
