# test-assistant 真实项目使用指南

> 当前版本：`v0.5.1`
>
> 更新日期：2026-08-01
>
> 当前主流程：Python 3.13 + pytest

本文用于把本地构建的 `test-assistant` 安装到另一个真实项目，并完整测试：

```text
安装
→ init
→ inspect
→ triage（已有套件，可独立使用）
→ plan propose
→ 人工审批
→ generate
→ 人工确认 diff
→ verify
→ status / diagnose / report
```

## 1. 当前安装模型

当前 `PytestExecutor` 使用运行 `test-assistant` 的 Python 解释器执行：

```text
sys.executable -m pytest
```

因此，真实项目试用时应把 `test-assistant` 安装进目标项目自己的虚拟环境。这样工具、pytest 和目标项目依赖位于同一个环境中。

暂不推荐使用 pipx：pipx 的隔离环境通常看不到目标项目依赖，可能产生错误的导入或基础设施诊断。

### 适用条件

目标项目目前需要满足：

- Python `>=3.13,<4.0`；
- 使用 pytest；
- 目标项目依赖已经安装；
- 原有测试可以在该虚拟环境中运行。

如果目标项目仍使用 Python 3.12 或更早版本，当前 wheel 无法安装。不要强行升级真实项目解释器；应改用专门的测试副本，或等待工具支持显式指定目标解释器。

## 2. 在工具仓库构建 wheel

进入 `test-assistant` 仓库：

```bash
cd /absolute/path/to/test-assistant
```

验证并构建：

```bash
poetry run pytest -q
poetry build
```

成功后生成：

```text
dist/test_assistant-0.5.1-py3-none-any.whl
dist/test_assistant-0.5.1.tar.gz
```

记下 wheel 的绝对路径，例如：

```text
/absolute/path/to/test-assistant/dist/test_assistant-0.5.1-py3-none-any.whl
```

`poetry build` 只生成本地安装包，不会上传或发布。

## 3. 准备真实目标项目

第一次试用建议选择：

- 5～20 个源码文件的小型项目；
- 已有少量 pytest 测试；
- 函数包含 docstring 或类型注解；
- 使用独立 Git 分支、项目副本或可随时恢复的工作区。

进入目标项目：

```bash
cd /absolute/path/to/demo-project
```

保存试用前基线：

```bash
git status --short
python --version
python -m pytest -q
```

确保：

- Python 是 3.13；
- 原有测试在安装工具前已经通过；
- 清楚哪些文件是试用前就存在的未提交修改。

## 4. 安装到目标项目虚拟环境

根据目标项目的环境管理方式选择一种方法。

### 方式 A：普通 venv

激活目标项目现有虚拟环境：

```bash
cd /absolute/path/to/demo-project
source .venv/bin/activate
```

确认解释器和 pytest：

```bash
which python
python --version
python -m pytest --version
```

如果本地已经安装过旧版，先移除
```bash
python -m pip uninstall -y test-assistant
```

安装本地 wheel：

```bash
python -m pip install \
  /absolute/path/to/test-assistant/dist/test_assistant-0.5.1-py3-none-any.whl
```

验证：

```bash
which test-assistant
test-assistant --help
python -m pytest -q
```

### 方式 B：目标项目使用 Poetry

确认 Poetry 环境：

```bash
cd /absolute/path/to/demo-project
poetry run python --version
poetry run python -m pytest --version
```

安装到该 Poetry 虚拟环境：

```bash
poetry run pip install \
  /absolute/path/to/test-assistant/dist/test_assistant-0.5.1-py3-none-any.whl
```

验证：

```bash
poetry run test-assistant --help
poetry run python -m pytest -q
```

这种安装方式适合本地试用，不会自动把 `test-assistant` 写入目标项目的 `pyproject.toml`。重新创建 Poetry 环境后需要重新安装。

后续示例使用已经激活的普通 venv，命令写作 `test-assistant`。如果目标项目使用 Poetry，请在每条命令前加 `poetry run`。

## 5. 配置 LLM

只有以下两个命令调用 LLM：

```text
plan propose
generate
```

在执行 CLI 的同一个终端设置：

```bash
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://your-openai-compatible-endpoint"
```

不要把密钥写进：

- Git 仓库；
- `.autotest/`；
- TestSpec；
- shell 历史中的命令参数；
- 测试失败消息。

下面的命令不调用 LLM：

```text
init  inspect  run  triage  verify  status  diagnose  report
```

## 6. 初始化目标项目

在目标项目根目录运行：

```bash
test-assistant init \
  --path . \
  --mode auto
```

`auto` 用于已有项目。`bootstrap` 适用于尚未建立测试基线的新项目，并会关闭配置中的自动执行。

初始化会创建：

```text
.autotest/
├── config.yml
├── snapshot.json
└── test_cases/
```

初始化不调用 LLM。目标项目已经存在 `.autotest/` 时，CLI 会在覆盖前要求确认。

初始化后检查：

```bash
git status --short
find .autotest -maxdepth 3 -type f -print
```

## 7. 检查项目分析结果

```bash
test-assistant inspect --path .
```

重点确认：

- 语言和 pytest 是否识别正确；
- 源码符号及限定名是否正确；
- 可测性状态；
- docstring、类型提示等契约证据；
- 已有测试映射；
- 测试选择模式；
- 是否出现安全降级警告。

已有测试的快照增量执行是独立流程：

```bash
test-assistant run --path .
```

第一次真实试用可以先完成 TestSpec 闭环，再单独评估 `run`。

### `run`、`verify` 与 `triage` 的职责边界

| 命令 | 输入 | 用途 | 是否需要 TestSpec |
| --- | --- | --- | --- |
| `run` | snapshot 变更 | 选择并执行受影响的已有测试 | 否 |
| `verify` | 已批准 spec + 精确 node | 验证新生成或指定测试三次 | 是 |
| `triage` | 已有 pytest suite/file/node | 聚类、复跑并归因现有失败 | 否 |

`triage` 不调用 LLM，也不会修改产品源码、正式测试、TestSpec 审批状态或 snapshot：

```bash
test-assistant triage --path .
test-assistant triage --path . --test-path tests/test_service.py
test-assistant triage --path . \
  --test-node tests/test_service.py::test_case
test-assistant triage --path . --max-failures 10
test-assistant triage --path . --test-path tests/test_service.py \
  --allow-git-history
```

`--test-path` 与 `--test-node` 互斥，且测试路径必须位于目标项目内。退出码定义：

- `0`：没有未解决问题；
- `1`：存在诊断，或 pytest 未收集到测试；
- `2`：参数、Runner、环境或持久化错误。

运行记录保存在 `.autotest/triage/<run-id>.json` 和 `latest.json`。失败诊断继续保存在 `.autotest/diagnoses/`，可使用 `diagnose` 与 `report` 查看。

#### 本地 Git 历史授权

默认情况下，`triage` 不读取提交历史，只根据当前测试与源码聚类，证据不足时保持 `INCONCLUSIVE`。第一次希望使用历史证据时明确执行：

```bash
test-assistant triage --path . \
  --test-path tests/test_service.py \
  --allow-git-history
```

授权保存在当前项目的 `.autotest/permissions.json`，并绑定仓库身份，不是对所有项目的全局授权。授权范围仅为本地只读：工具只使用固定的 `git rev-parse`、`git log -S` 和 `git show`，不执行 fetch/pull/push，不访问网络，也不写入 Git。单次禁用可使用 `--no-git-history`；它不会删除已保存授权。历史缺失、超时或不可读时会安全降级并在 triage 记录中审计。

## 8. 确定 source path、module path 和目标符号

三个值必须相互对应。

### 根目录模块

```text
文件：          demo.py
source path：   demo.py
module path：   demo
目标符号：      demo.add
```

### src 布局

```text
文件：          src/package/demo.py
source path：   src/package/demo.py
module path：   package.demo
目标符号：      package.demo.add
```

如果目标项目没有正确配置 `src/` 导入路径，应先确保以下命令在目标项目环境中成功：

```bash
python -c "import package.demo"
```

不要通过修改工具参数掩盖目标项目本身的导入配置问题。

## 9. 提议 TestSpec

以根目录的 `demo.add` 为例：

```bash
test-assistant plan propose demo.add \
  --path . \
  --source-path demo.py \
  --module-path demo
```

也可以指定模型：

```bash
test-assistant plan propose demo.add \
  --path . \
  --source-path demo.py \
  --module-path demo \
  --model deepseek-chat
```

该命令会：

1. 分析指定源码文件；
2. 精确查找目标符号；
3. 判断是否可直接测试；
4. 提取相关契约证据；
5. 调用 LLM 生成结构化意图；
6. 校验并保存 proposed TestSpec。

记录命令输出的 `SPEC_ID`。此时不会批准 TestSpec，也不会生成测试文件。

## 10. 人工审批 TestSpec

列出并查看：

```bash
test-assistant plan list --path .
test-assistant plan show SPEC_ID --path .
```

检查以下内容：

- `behavior` 是否符合真实业务意图；
- `arrange` 输入是否合理；
- `action` 是否调用正确目标；
- `expected` 是否有契约依据；
- `evidence` 来源和强度；
- `side_effects` 是否完整。

批准：

```bash
test-assistant plan approve SPEC_ID --path .
```

不符合业务意图时拒绝：

```bash
test-assistant plan reject SPEC_ID --path .
```

审批是终态迁移：已批准的 TestSpec 不能再拒绝，已拒绝的 TestSpec 不能再批准。

## 11. 生成并审阅候选测试

```bash
test-assistant generate SPEC_ID \
  --path . \
  --module-path demo \
  --source-path demo.py \
  --test-filename test_demo.py
```

流程如下：

```text
approved TestSpec
→ LLM 候选源码
→ candidates 隔离保存
→ 静态和导入门禁
→ pytest 收集门禁
→ Runner 健康检查
→ 隔离执行和副作用检查
→ 显示 diff
→ 用户确认
→ 正式测试原子提交
```

审阅 diff 时确认：

- 导入目标正确；
- arrange 与 TestSpec 一致；
- 断言没有被弱化；
- 没有未声明的网络、文件或进程副作用；
- 没有修改其他正式测试。

输入 `n` 时正式测试不会改变。只有输入明确确认后才会提交。

正式测试默认位于：

```text
.autotest/test_cases/unit/SOURCE_PATH/TEST_FILENAME
```

记录 CLI 输出中的正式文件绝对路径，并打开文件确认 pytest 测试函数名。

## 12. 确定精确 pytest node

假设生成函数为：

```python
def test_add():
    ...
```

可以先收集测试：

```bash
python -m pytest \
  .autotest/test_cases/unit/demo.py/test_demo.py \
  --collect-only \
  -q
```

pytest node 格式是：

```text
path/to/test_file.py::test_function
```

例如：

```text
.autotest/test_cases/unit/demo.py/test_demo.py::test_add
```

复制 collect-only 输出，不要猜测函数名。

## 13. 验证精确测试节点

```bash
test-assistant verify SPEC_ID \
  --path . \
  --test-node ".autotest/test_cases/unit/demo.py/test_demo.py::test_add" \
  --source-path demo.py
```

`verify` 不调用 LLM，也不会修改源码或正式测试。它会：

1. 确认 TestSpec 已批准；
2. 确认测试和源码位于目标项目内；
3. 运行静态、Runner 和精确 collect-only 门禁；
4. 只执行指定 pytest node 三次；
5. 全部通过时更新健康状态；
6. 失败或结果不一致时归因并保存诊断。

退出码：

- `0`：连续三次通过；
- `1`：生成了需要处理或确认的诊断；
- 参数、路径、存储或环境错误：非零。

## 14. 查看当前状态

```bash
test-assistant status --path .
```

`status` 优先读取最近一次验证状态：

- 新的成功验证显示健康；
- 新的失败显示分类和置信度；
- 历史诊断不会因为后续成功而删除。

## 15. 查看诊断和报告

失败后解释结构化诊断：

```bash
test-assistant diagnose \
  --input .autotest/diagnoses/latest.json
```

五类诊断：

| 分类 | 含义 |
| --- | --- |
| `product_defect` | 强证据表明产品行为违反已批准契约 |
| `test_defect` | 测试结构、语法、导入或收集存在确定性问题 |
| `infra_defect` | Runner、超时、权限或执行环境故障 |
| `flaky` | 同一环境下重复结果在通过和失败之间变化 |
| `inconclusive` | 当前证据不足，需要人工确认 |

生成 Markdown 报告：

```bash
test-assistant report --path .
```

默认输出：

```text
.autotest/reports/latest.md
```

指定输出位置：

```bash
test-assistant report \
  --path . \
  --output /tmp/test-assistant-report.md
```

诊断记录和报告会对常见 token、password、secret、API key 和 Bearer 凭据脱敏，并限制执行输出体积。

## 16. 检查试用产生的变化

完整流程后执行：

```bash
git status --short
git diff
find .autotest -maxdepth 5 -type f -print
```

重点检查：

- 正式测试是否只在确认后出现；
- 产品源码是否保持不变；
- 是否出现意外配置修改；
- TestSpec、候选、验证和诊断记录是否完整；
- 生成测试能否单独由 pytest 执行。

再次运行原测试套件：

```bash
python -m pytest -q
```

## 17. 更新或卸载本地 wheel

工具重新构建后，在目标项目虚拟环境更新：

```bash
python -m pip install \
  --upgrade \
  /absolute/path/to/test-assistant/dist/test_assistant-0.5.1-py3-none-any.whl
```

卸载 CLI：

```bash
python -m pip uninstall test-assistant
```

卸载 Python 包不会删除目标项目中的 `.autotest/`。该目录包含测试、计划和诊断记录，删除前应先检查并备份需要保留的内容。

## 18. 常见问题

### wheel 无法安装，提示 Python 版本不兼容

当前包要求 Python 3.13。确认安装命令使用的是目标项目虚拟环境中的解释器：

```bash
which python
python --version
python -m pip --version
```

### 安装后找不到 test-assistant

确认虚拟环境已激活：

```bash
which python
which test-assistant
python -m pip show test-assistant
```

Poetry 项目应使用：

```bash
poetry run test-assistant --help
```

### 目标项目依赖导入失败

先绕过工具直接验证：

```bash
python -m pytest -q
python -c "import your_package"
```

如果这两条命令失败，应先修复目标项目环境。不要把项目环境错误误认为生成测试问题。

### 找不到目标符号

确认 source path、module path 和目标限定名一致，并检查 `inspect` 输出。

### TestSpec 只有 medium 或 weak 证据

docstring 和类型提示通常是中等证据；没有证据时是弱推断。即使测试稳定失败，也不会仅凭这些证据自动判断产品缺陷，而会返回 `INCONCLUSIVE`。

### verify 报告找不到测试节点

使用同一虚拟环境执行 collect-only，并复制完整 node：

```bash
python -m pytest path/to/test_file.py --collect-only -q
```

### 真实 LLM 是否属于默认测试

不是。仓库自动化测试使用 fake LLM，避免网络和模型波动。真实模型只作为显式试用或 smoke test。

## 19. 当前限制

- `triage` 只支持 Python/pytest，不调用 LLM，也不自动修复；
- 只有当前源码与历史等明确证据确认能力已移除时，才可判旧测试为 `TEST_DEFECT`；
- 契约冲突保持 `INCONCLUSIVE` 并请求人工确认；
- 旧 snapshot 不含符号摘要时，`inspect` 会明确降级为 `file_level` 保守分析；

- 可信生成和符号归因主流程只支持 Python 3.13 + pytest；
- Web Dashboard 和 watch 尚未实现；
- Vitest 执行器不属于当前 TestSpec 生成闭环；
- 当前执行器还不能显式选择目标项目的其他 Python 解释器；
- 没有已批准强契约时，稳定失败通常返回 `INCONCLUSIVE`；
- 当前使用版本化 JSON，尚未引入 SQLite 或远程服务；
- 工具不会自动修复产品源码，也不会自动批准 TestSpec 或 diff。

内部模块和 `.autotest/` 结构参见 [项目结构文档](project-structure.md)。历史设计与实施计划位于 `docs/plans/`。
