from click.testing import CliRunner

from cli.main import cli


def test_root_cli_exposes_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0, result.output
    assert result.output == "test-assistant, version 0.6.1\n"


def test_root_help_exposes_doctor_command():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    assert "doctor" in result.output
