目标： 获取文件快照
遍历文件树，获取对应的快照列表，包括 文件 sha256、size、mtime、type

- 读取文件要获取hash时，为避免文件过大，使用分块更新 hash 值

```python
import hashlib

def get_file_hash(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)

    return sha256.hexdigest()
```

- 获取文件信息

```python
# 通过文件描述符获取 stat
# st = os.fstat(f.fileno())

st = os.stat(f)
size = st.st_size
mtime = st.st_mtime # 最后修改时间
ctime = st.st_ctime # 创建 / 元数据变更时间
mode = st.st_mode # 文件类型 + 权限（整数，需用 stat 模块解析）
ext = os.path.splitext(path)[1] # 扩展名
```

## 打开文件 .open

可以打开的模式有：

- "r" 读（默认），文件不存在报错
- "w" 写，覆盖已有内容
- "a" 追加（append），在末尾添加
- "rb" / "wb" 二进制模式 读/写
