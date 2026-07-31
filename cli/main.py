import click

from cli.commands.init import init
from cli.commands.run import run
from cli.commands.plan import plan
from cli.commands.status import status
from cli.commands.watch import watch
from cli.commands.serve import serve
from cli.commands.report import report
from cli.commands.inspect import inspect_command
from cli.commands.generate import generate_command

# @click.group() 创建一个命令组，相当于 npm 这样的根命令
@click.group()
def cli():
    """test-assistant: LLM 驱动的智能测试工具"""
    pass


# 注册子命令
cli.add_command(init)
cli.add_command(inspect_command)
cli.add_command(plan)
cli.add_command(generate_command)
cli.add_command(run)
cli.add_command(status)
cli.add_command(watch)
cli.add_command(serve)
cli.add_command(report)

if __name__ == "__main__":
    cli()