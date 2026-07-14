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
