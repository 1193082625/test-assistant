在处理业务逻辑时要注意错误处理
考虑程序有可能崩溃的各个步骤，并考量是否需要添加对应的错误处理，或者提示，或者及时退出

删除目录：

```python
import shutil
if os.path.exits(target_path):
    shutil.rmtree(target_path)
```
