# Day 2: init 命令完整实现 + YAML 配置

**目标**：完善 `test-assistant init` 命令，实现：

1. 解析 `--path` `--name` `--mode` 三个参数
2. 在目标项目中创建 `.autotest/` 目录结构
3. 生成 `config.yml` 配置文件

**新依赖**：PyYAML 库（Python 读写 YAML，安装：`poetry add pyyaml`）

---

## 今日交付

- [x] `test-assistant init` 完整实现：`--path` `--name` `--mode` 三个参数
- [x] 创建 `.autotest/` 目录结构（9 种测试类型子目录）
- [x] 生成 `config.yml` 默认配置
- [x] 增加 PyYAML 依赖

## 知识点记录

### 1. Click 选项

```python
@click.option("--path", default=".", help="目标项目路径")
@click.option("--name", default=None, help="项目名称（默认使用目录名）")
@click.option("--mode", type=click.Choice(["auto", "bootstrap"]), default="auto", help="...")
```

- `@click.option()` 和函数参数必须一一对应
- `type=click.Choice([...])` 限制可选值
- `default` 设置默认值
- `help` 在 `--help` 中展示

### 2. YAML 读写

**安装**：`poetry add pyyaml`

**写入**：

```python
import yaml
with open("config.yml", "w", encoding="utf-8") as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

| 参数                       | 作用                           |
| -------------------------- | ------------------------------ |
| `default_flow_style=False` | 块式缩进输出（可读性好）       |
| `allow_unicode=True`       | 支持中文等非 ASCII             |
| `sort_keys=False`          | 按定义顺序输出（不按字母排序） |

### 3. Python 目录操作

```python
os.path.abspath(path)       # 相对路径 → 绝对路径
os.path.basename(path)      # 取最后一级目录名
os.path.isdir(path)         # 判断是否是目录
os.path.exists(path)        # 判断路径是否存在
os.path.join(a, b)          # 拼接路径（自动处理 /）
os.path.relpath(path, start) # 相对路径
os.makedirs(path, exist_ok=True)  # 创建多级目录，已存在不报错
```

与 `os.mkdir` 的区别：

| 函数            | 能创建中间目录？  | 目录已存在？      |
| --------------- | ----------------- | ----------------- |
| `os.mkdir()`    | ❌ 父目录必须存在 | ❌ 抛异常         |
| `os.makedirs()` | ✅ 自动创建父目录 | 取决于 `exist_ok` |

### 4. auto vs bootstrap 模式

| 模式           | 目标项目状态              | auto_run          |
| -------------- | ------------------------- | ----------------- |
| `auto`（默认） | 已有项目，有代码/部分测试 | True（自动执行）  |
| `bootstrap`    | 新项目，还没搭测试框架    | False（先搭框架） |

_mode 的具体业务逻辑在 Day 3-4 框架检测器实现后会真正落地。_

## 设计决策

1. **`test_framework` 只留 `"auto"`**：框架列表写不完，留给检测器自动识别，config.yml 只放用户偏好
2. **test_types 补全 9 种**：与设计文档一致，新增 edge/performance/mutation
3. **`yaml.dump` 三个参数一起用**：确保 config.yml 可读、不乱码、顺序合理
