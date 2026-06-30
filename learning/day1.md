# 包管理工具

test-assistant 是一个 Python CLI 包

## 1. 安装 Poetry

用 Poetry（当前社区最主流） 的依赖锁定的版本管理 处理 外部依赖 【相当于 Python 世界的 npm】
安装 Poetry : `pip install poetry`
验证是否安装成功：`poetry --version`
pyproject.toml 就相当于 npm 中的 package.json
poetry.lock 相当于 package-lock.json
poetry add xxx 相当于 npm install xxx
区别： npm 是把依赖装到项目的 node_modules 里，poetry 是把依赖装到独立的虚拟环境里（并自动管理）

## 2. 初始化项目： poetry init

## 3. 添加依赖：poetry add click langchain-core

## 4. 进入虚拟环境： 【每天开发之前先进入虚拟环境后再开始，就像npm 项目一样，不需要每次跑命令都 npm run ， 而是开一个终端一直待在项目里】

    poetry 2.0 已经移除了 shell 命令。不能直接使用 poetry shell
    需要手动激活：
    1. 给 zsh 配个 alias：
    `echo 'alias pyshell="source \"$(poetry env info --path)/bin/activate""' >> ~/.zshrc`
    `source ~/.zshrc`
    以后只要执行 `pyshell` 即可

## 2. 搭建 Click CLI 框架

Click 是 python 的一个 CLI 框架。

## 3. 修改 pyproject.toml

### 第一段： [project] - 项目元信息 + 依赖

### 第二段： [build-system] - 构建工具声明

告诉 python： “这个项目用 Poetry 来构建”。就像 npm 的 package.json 隐含了用 npm 构建一样

### 第三段： [tool.poetry] - 告诉 poetry 这些目录就是源码，打包时包含他们 【poetry 默认会找和包名一致的目录】

### 第四段： [tool.poetry.scripts] - 相当于 npm 的 “bin” 配置，意思是 在系统里注册一个叫 test-assistant 的命令。执行它时，等于 from cli.main import cli; cli()

## 3. Click 的规则：

@click.option() 和函数参数必须一一对应，一下两个示例都不对

```python
# 写法A -- mode 没有对应的option，Click 不会传这个参数进来，运行时会报错 missing argument 错误
@click.command()
@click.option("--path", default=".")
def init(path, mode):
    pass

# 写法B -- --mode 定义了参数但函数不接收，Click 传了但函数不接，同样报错
@click.command()
@click.option("--path", default=".")
@click.option("--mode", type=click.Choice(["auto", "bootstrap"]), default="auto")
def init(path):
    pass
```

获取当前工作目录的路径
cwd = os.getcwd()
click.echo(f"当前工作目录的路径：{cwd}")
