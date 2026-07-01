# 今日目标：自动扫描目标项目，并识别：

- 这是什么类型的项目？（前端、后端、小程序）
- 用了什么框架？（React/vue/Express/FastAPI...）
- 用了什么测试框架？（jest/vitest/pytest...）
- 用了什么构建工具？（Vite/webpack/poetry...）

交付物： core/analyzers/framework.py + 集成到 init 命令中

## 模式匹配： 找 「标志性文件」

框架检测的核心思路不是读每个文件，而是找标志性文件

┌──────────────────────────────────────────────┬───────────────────┐
│ 标志文件 │ 说明 │
├──────────────────────────────────────────────┼───────────────────┤
│ package.json │ 前端/Node.js 项目 │
├──────────────────────────────────────────────┼───────────────────┤
│ pyproject.toml / requirements.txt / setup.py │ Python 项目 │
├──────────────────────────────────────────────┼───────────────────┤
│ pom.xml / build.gradle │ Java 项目 │
├──────────────────────────────────────────────┼───────────────────┤
│ go.mod │ Go 项目 │
├──────────────────────────────────────────────┼───────────────────┤
│ project.config.json / app.json │ 小程序项目 │
└──────────────────────────────────────────────┴───────────────────┘

## 检测策略设计

检测分三个层面，逐层细化：

### 第一层：项目类型

检测流程：

1. 找 package.json -- 前端/Node.js项目
2. 找 pyproject.toml -- Python 项目
3. 找 pom.xml / build.gradle -- Java 项目
4. 找 go.mod -- Go 项目
5. 找 project.config.json -- 小程序项目
6. 都没找到 -- unknown

### 第二层：具体框架（读文件内容）

package.json 中找：

- react / react-dom -- React
- vue -- Vue
- @angular/core -- Angular
- express -- Express
- fastify -- Fastify
- next -- Next.js
- nuxt -- Nuxt

pyproject.toml 中找：

- django -- Django
- fastapi -- FastAPI
- flask -- Flask

### 第三层： 测试框架和构建工具

测试框架同样从 package.json 的 devDependencies 或 Python 配置中找：
devDependencies 中找到：

- vitest -- Vitest
- jest -- Jest
- @playwright -- Playwright
- cypress -- Cypress

pyproject.toml / pytest.ini / setup.cfg 中有 pytest 相关：
或者目录下有 pytest.ini -- pytest

## 查找配置文件时排除依赖目录

使用 `os.walk` ，可以在运行时修改 dirs 列表来剪枝：
这样就不会进入 类似于 node_modules 这样的依赖目录 去枚举几十万个文件
常见的排除列表：
EXCLUDE_DIRS = ["node_modules", ".git", "__pycache__", ".venv", "venv", ".next", "dist", "build", ".autotest"]

```python
for root, dirs, files in os.walk(target_path):
    # 直接修改 dirs, os.walk 就不会往下走了
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    """
    原地修改 dirs 列表， 控制 os.walk 的遍历路径
    dirs[:] = [...] 表示切片赋值，替换列表内容，但不改变列表对象本身；os.walk 内部持有的还是同一个列表对象，但内容变了
    现在 dirs 里只剩下我允许的目录
    os.walk 下一步只会走进这些目录

    示例：
    a = [1, 2, 3, 4, 5]
    b = a # b 引用同一个列表

    a = [6, 7, 8] # 创建新列表，a 指向新对象
    print(b) # b 不受影响 还是 [1, 2, 3, 4, 5]

    a[:] = [6, 7, 8] # 修改原列表的内容
    print(b)  # b 也会跟着改变， [6, 7, 8]
    """
    ...
```

定义类型：

```python
from dataclasses import dataclass

@dataclass
class FrameworkInfo:
    name:str
    age: int

# 声明元组类型
from typing import NamedTuple

class ProjectInfo(NamedTuple):
    project_type: str
    file_content: str
```

返回文件内容时要使用：

```python
with open(file_path, "r", encoding="utf-8") as f:
    return f.read()
```

加载对应类型内容

```python
# json
json_data = json.loads(content)

# 解析 YAML
data = yaml.safe_load(content)
```
