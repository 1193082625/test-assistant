## tempfile

Python 的 tempfile 模块用于创建临时文件/目录，核心用途是测试和临时数据存储。

| 函数                                      | 返回            | 场景                                               |
| ----------------------------------------- | --------------- | -------------------------------------------------- |
| tempfile.NamedTemporaryFile()             | 文件对象        | 创建有名字的临时文件，用于读写                     |
| tempfile.TemporaryFile()                  | 文件对象        | 创建无名字的临时文件（文件系统不可见）             |
| tempfile.TemporaryDirectory()             | 目录路径（str） | 创建临时目录，放多个样本文件                       |
| tempfile.mkstemp()                        | (fd, path)元组  | 返回文件描述符+路径，手动管理                      |
| tempfile.mkdtemp()                        | 目录路径(str)   | 创建临时目录，手动管理                             |
| tempfile.NamedTemporaryFile(delete=False) | 文件对象        | 测试中很常用--不自动删除，方便os.unlink() 手动清理 |

### 常用 with 关键字 -- 自动清理
