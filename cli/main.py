import click

from cli import __version__

from cli.commands.init import init
from cli.commands.run import run
from cli.commands.plan import plan
from cli.commands.status import status
from cli.commands.report import report
from cli.commands.inspect import inspect_command
from cli.commands.generate import generate_command
from cli.commands.diagnose import diagnose_command
from cli.commands.verify import verify_command
from cli.commands.triage import triage_command
from cli.commands.audit import audit_command

# @click.group() 创建一个命令组，相当于 npm 这样的根命令
@click.group()
@click.version_option(version=__version__, prog_name="test-assistant")
def cli():
    """test-assistant: Python/pytest 可信测试与分诊工具"""
    pass


# 注册子命令
cli.add_command(init)
cli.add_command(inspect_command)
cli.add_command(plan)
cli.add_command(generate_command)
cli.add_command(diagnose_command)
cli.add_command(verify_command)
cli.add_command(triage_command)
cli.add_command(audit_command)
cli.add_command(run)
cli.add_command(status)
cli.add_command(report)

if __name__ == "__main__":
    cli()
