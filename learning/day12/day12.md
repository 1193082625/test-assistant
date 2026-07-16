

## subprocess 在 Python 里跑命令行

之前是用 click 封装 CLI，现在要让 Python 去调用别的命令（如 pytest）

跑一条命了，等他执行完，拿到结果：

```python
result = subprocess.run(
    ["python", "-m", "pytest", "test_file.py", "-v"], # 命令和参数列表
    capture_output=True, # 捕获 stdout 和 stderr
    text=True, # 以文本形式返回（而不是 bytes）
    timeout=120, # 超时设置 120 秒
)

# 命令的标准输出
print(result.stdout)
# 命令的退出码(0=成功，非0=失败)
print(result.returncode)
```

## re（正则表达式）- 从文本中提取信息


## 区分 三类对象的访问方式

### 1. Pydantic / dataclass 对象 -> .属性
**类的实例 -> .属性名**
```python
from pydantic import BaseModel
class ProjectInfo(BaseModel):
    project_path: str
    config: dict

info = ProjectInfo(project_path="/XXX", config={...})
# 不支持 ["project_path"] 和 .get()
print(info.project_path)
```

### 2. dict 字典 -->  ["key"] 或 .get("key")
```python
config = {"project": {"name": "my-app"}}

# dict 不能用 .project
print(config["project"]) # {"name": "my-app"}
print(config.get("project"))
print(config.get("不存在的key")) # None 不报错
print(config["不存在的key"]) # 报错： KeyError
```

## 退出
- raise SystemExit(0) 正常退出
- raise SystemExit(1) 错误退出