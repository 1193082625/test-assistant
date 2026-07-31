# test-assistant 用户指南

> 当前版本：`v0.4.0` 候选版
>
> 更新日期：2026-08-01
>
> 当前主流程：Python 3.13 + pytest

## 1. 准备环境

开发本项目需要：

- Python `>=3.13,<4.0`
- Poetry
- 目标项目能够在当前 Python 环境运行 pytest

安装依赖并验证 CLI：

```bash
cd /path/to/test-assistant
poetry install
poetry run test-assistant --help
```

`plan propose` 和 `generate` 会调用 LLM。通过环境变量配置：

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_BASE_URL="https://..."
```

不要把密钥写入目标项目、TestSpec、命令参数或 Git。

以下命令不调用 LLM：

```text
init  inspect  run  verify  status  diagnose  report
```

## 2. 选择试用项目

第一次使用建议选择：

- 较小的 Python 项目；
- 已能运行 pytest；
- 使用独立 Git 分支或项目副本；
- 先确保原测试套件通过。

示例变量：

```bash
TOOL_PATH=/path/to/test-assistant
TARGET_PATH=/path/to/demo-project
```

以下命令默认在工具仓库执行：

```bash
cd "$TOOL_PATH"
```

## 3. 初始化目标项目

```bash
poetry run test-assistant init \
  --path "$TARGET_PATH" \
  --mode auto
```

`auto` 用于已有项目；`bootstrap` 会把配置中的自动执行关闭，适用于尚未建立测试基线的新项目。

初始化会创建 `.autotest/`、项目配置和初始快照。初始化过程不调用 LLM。

如果目标项目已经存在 `.autotest/`，CLI 会在覆盖前要求确认。

## 4. 检查分析和测试选择

```bash
poetry run test-assistant inspect \
  --path "$TARGET_PATH"
```

重点检查：

- 项目语言和 pytest 是否识别正确；
- 目标源码符号和模块限定名；
- 可测性状态；
- docstring、类型提示等契约证据；
- 已有测试映射；
- 测试选择模式和安全降级警告。

增量执行已有测试：

```bash
poetry run test-assistant run \
  --path "$TARGET_PATH"
```

`run` 属于快照驱动的已有测试增量流程；TestSpec 生成和精确诊断使用后续命令。

## 5. 提议 TestSpec

假设源码是：

```text
demo.py               → module path: demo
src/package/demo.py   → module path: package.demo
```

为 `demo.add` 创建待审批 TestSpec：

```bash
poetry run test-assistant plan propose demo.add \
  --path "$TARGET_PATH" \
  --source-path demo.py \
  --module-path demo
```

常用选项：

```text
--source-path   源码相对于目标项目根目录的路径
--module-path   Python 可导入模块名，不包含 .py
--model         Planner 使用的模型，默认 deepseek-chat
```

该命令会：

1. 分析指定 Python 文件；
2. 精确查找目标符号；
3. 判断目标是否可直接测试；
4. 提取相关契约证据；
5. 调用 LLM 生成结构化测试意图；
6. 校验并保存 proposed TestSpec。

它不会批准 TestSpec，也不会生成或写入测试。

## 6. 人工审批 TestSpec

列出和查看：

```bash
poetry run test-assistant plan list \
  --path "$TARGET_PATH"

poetry run test-assistant plan show SPEC_ID \
  --path "$TARGET_PATH"
```

检查：

- `behavior` 是否符合真实业务意图；
- `arrange` 和 `action` 是否合理；
- `expected` 是否有证据支持；
- `evidence` 来源和强度；
- `side_effects` 是否完整。

批准或拒绝：

```bash
poetry run test-assistant plan approve SPEC_ID \
  --path "$TARGET_PATH"

poetry run test-assistant plan reject SPEC_ID \
  --path "$TARGET_PATH"
```

审批是终态迁移：已批准的 TestSpec 不能再拒绝，已拒绝的 TestSpec 不能再批准。

## 7. 生成并审阅候选测试

```bash
poetry run test-assistant generate SPEC_ID \
  --path "$TARGET_PATH" \
  --module-path demo \
  --source-path demo.py \
  --test-filename test_demo.py
```

生成流程：

```text
approved TestSpec
→ LLM 候选源码
→ candidates 隔离保存
→ 静态/导入门禁
→ pytest 收集门禁
→ Runner 健康检查
→ 隔离执行和副作用检查
→ 显示 diff
→ 用户确认
→ 正式测试原子提交
```

拒绝 diff 时，正式测试不会改变。门禁失败时，候选不会提交到正式目录。

正式测试默认位于：

```text
.autotest/test_cases/unit/SOURCE_PATH/TEST_FILENAME
```

CLI 在提交成功后会输出实际绝对路径，应以该输出为准。

## 8. 验证精确测试节点

从正式测试中确认 pytest 函数名，例如 `test_add`，然后执行：

```bash
poetry run test-assistant verify SPEC_ID \
  --path "$TARGET_PATH" \
  --test-node ".autotest/test_cases/unit/demo.py/test_demo.py::test_add" \
  --source-path demo.py
```

`--test-node` 必须包含相对于目标项目根目录的测试文件和精确符号：

```text
path/to/test_file.py::test_function
```

验证过程不会调用 LLM，也不会修改源码或测试。它会：

1. 确认 TestSpec 已批准；
2. 检查测试和源码路径没有逃逸目标项目；
3. 运行静态、Runner 和精确 collect-only 门禁；
4. 只执行该 pytest node 三次；
5. 全部通过时更新健康状态；
6. 失败或结果不一致时归因并保存诊断。

退出码：

- `0`：连续三次通过；
- `1`：生成了需要处理或确认的诊断；
- Click 参数或输入错误同样返回非零。

## 9. 查看状态和诊断

```bash
poetry run test-assistant status \
  --path "$TARGET_PATH"
```

`status` 优先显示最近一次 `verify` 状态，因此一次新的成功验证不会继续展示旧失败。历史诊断不会被删除。

失败后解释结构化诊断：

```bash
poetry run test-assistant diagnose \
  --input "$TARGET_PATH/.autotest/diagnoses/latest.json"
```

输出包括：

- 分类；
- 置信度；
- 摘要；
- 证据和细节；
- 建议动作；
- 复现命令。

五类诊断：

| 分类 | 含义 |
| --- | --- |
| `product_defect` | 强证据表明产品行为违反已批准契约 |
| `test_defect` | 测试结构、语法、导入或收集存在确定性问题 |
| `infra_defect` | Runner、超时、权限或执行环境故障 |
| `flaky` | 同一环境下重复结果在通过和失败之间变化 |
| `inconclusive` | 当前证据不足，需要人工确认 |

## 10. 生成 Markdown 报告

```bash
poetry run test-assistant report \
  --path "$TARGET_PATH"
```

默认输出：

```text
.autotest/reports/latest.md
```

也可指定位置：

```bash
poetry run test-assistant report \
  --path "$TARGET_PATH" \
  --output /tmp/test-assistant-report.md
```

诊断记录和报告会对常见 token、password、secret、API key 和 Bearer 凭据脱敏，并限制执行输出体积。

## 11. 常见问题

### 找不到目标符号

确认三者一致：

```text
source path:  src/package/demo.py
module path:  package.demo
target:       package.demo.add
```

### TestSpec 只有 medium/weak 证据

docstring 和类型提示通常是中等证据；没有证据时是弱推断。即使测试稳定失败，也不会仅凭这些信息自动判断产品缺陷，而会返回 `INCONCLUSIVE`。

### verify 报告未找到测试节点

先在目标项目执行：

```bash
python -m pytest path/to/test_file.py --collect-only -q
```

复制 pytest 输出中的完整 node ID。

### 初始化或执行后出现新文件

`.pytest_cache/` 和 `__pycache__/` 是 pytest/Python 缓存；`.autotest/` 是工具工作区。首次真实试用应在独立 Git 分支中检查 `git status`。

### 真实 LLM 是否属于自动化测试

不是。默认测试使用 fake LLM，避免网络和模型波动。真实 LLM 只应作为显式 smoke test。

## 12. 当前限制

- 可信生成和符号归因主流程只支持 Python/pytest。
- Web Dashboard 和 watch 尚未实现。
- Vitest 执行器仍存在于旧增量执行路径，但不属于当前 TestSpec 生成闭环。
- `PRODUCT_DEFECT` 的判定非常保守；没有强契约时需要人工确认。
- 当前使用版本化 JSON；尚未引入 SQLite 或远程服务。
- 工具不会自动修复产品源码，也不会自动批准 TestSpec 或 diff。

项目内部模块说明参见 `docs/project-structure.md`；历史路线图参见 `docs/plans/`。
