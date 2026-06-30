import os
import click
import yaml
import hashlib

"""
练习1:
"""
def detect_framework(target_path: str) -> str:
    """检查测试框架，返回 “vitest” / "jest" / "pytest" / "unknown" """
    # 扫描 target_path 下是否存在 vitest.config.ts / jest.config.js 等
    vitest_path = os.path.join(target_path, "vitest.config.ts")
    jest_path = os.path.join(target_path, "jest.config.js")

    if os.path.exists(vitest_path):
        return "vitest"
    
    if os.path.exists(jest_path):
        return "jest"

    """
    os.walk(path) 递归遍历所有子目录，返回一个三元组
    for root, dirs, files in os.walk(target_path):
        print(root) # 当前目录的完整路径（字符串）
        print(dirs) # 当前目录下的子目录名列表
        print(files) # 当前目录下的文件名列表（不含目录）
    """
    """
    只扫根目录有哪些文件 用 os.listdir()
    遍历整个项目的目录树 用 os.walk()
    知道完整路径，要检查特定文件是否存在 用 os.path.exists()
    需要区分文件和目录 用 os.walk() 或 os.path.isfile() / os.path.isdir()
    """
    # 提示： 用 os.listdir() 遍历目录，返回指定目录下的所有文件和子目录的名称列表。只返回名字本身
    for f_name in os.listdir(target_path):
        if f_name == "pytest.ini" or f_name == ".pytest.ini" or f_name == "pyproject.toml" or f_name == "setup.cfg":
            return "pytest"
        elif f_name == "package.json":
            return "vitest"

    # 都没匹配到
    return "unknown"


def count_file_types(target_path: str) -> dict:
    """
    练习二：统计文件类型, 返回： {".py": 10, ".js": 5, ".ts": 8, ".md": 2, ...}
    以 learning 目录为例，os.walk 打印信息如下：
    打印1 /Users/wangyue/Desktop/work/test-assistant/learning
    打印2 ['day2']
    打印3 ['day1.md']
    打印1 /Users/wangyue/Desktop/work/test-assistant/learning/day2
    打印2 []
    打印3 ['test.py', 'day2.md']
    """
    # 用 os.walk 递归遍历所有文件
    ext_count = {}
    for root, dirs, files in os.walk(target_path):
        print(f"打印1 {root}")
        print(f"打印2 {dirs}")
        print(f"打印3 {files}")
        for f in files:
            ext = os.path.splitext(f)[1] # 提取文件后缀名
            ext_count[ext] = ext_count.get(ext, 0) + 1 # .get() 中第二个参数表示数据不存在时的默认值

    # 按后缀名分组计数
    return ext_count

def validate_config(config_path: str) -> list:
    """练习三： 验证 config.yml"""
    errors = []
    # 1. 读取 yaml 文件
    with open(config_path, "r", encoding="utf-8") as f:
        # 解析 YAML --> Python 字典
        data = yaml.safe_load(f)

        # 2. 检查必填字段是否存在（project.name, test_types 等）
        if "project" not in data:
            errors.append("缺少 project 字段")
        elif "name" not in data.get("project", {}):
            errors.append("缺少 project.name 字段")
        
        if "test_types" not in data:
            errors.append("缺少 test_types 字段")

        # 3. 检查 priority 是否从 1 开始连续
        test_types_context = data.get("test_types", {})
        """
        iter(dict) 把字典变成迭代器，迭代器就像是一个只能往前走的指针，每次调用 next() 就移动到下一个元素
        """
        # first_key = next(iter(test_types_context))
        # first_value = test_types_context[first_key]
        # if first_value.get("priority", 0) != 1:
        #     errors.append("priority 应该从 1 开始连续")
        expected = 1
        # .items() 拿到字典的 key 和 value
        for test_type, config in test_types_context.items():
            actual = config.get("priority")
            if actual != expected:
                errors.append(f"{test_type}: priority 期望 {expected}, 实际 {actual}")
            expected += 1

    # 4. 返回错误列表 （空列表 = 全部通过）
    return errors

def get_file_hash(file_path: str) -> str:
    """计算文件的 SHA256 hash"""
    sha256 = hashlib.sha256()
    # 以 二进制模式 读取文件
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""): # 分块读，防止大文件内存爆炸
            sha256.update(chunk)

    # 返回 64 位 十六进制字符串
    return sha256.hexdigest()

def take_snapshot(target_path: str) -> dict:
    """
    练习4: 文件快照
    返回： { "relative/path/to/file.py": "sha256hash", ... }
    """
    hash_list = {}
    # 1. 用 os.walk 遍历所有文件
    for root, dirs, files in os.walk(target_path):
        for f in files:
            # 2. 对每个文件计算 SHA256 hash
            f_hash = get_file_hash(os.path.join(root, f))
            # 获取文件的相对路径
            """
            os.path.relpath(path, start) 计算 path 相对于 start 的相对路径
            os.path.realpath(path) 解析符号链接，返回真实绝对路径
            os.path.abspath(path) 相对 -> 绝对路径
            """
            rel_path = os.path.relpath(os.path.join(root, f), target_path)
            hash_list[rel_path] = f_hash

    return hash_list 

@click.command()
def detect():
    """检测项目框架"""
    # 调用 detect_framework， 输出结果
    current_path = os.getcwd()
    result = detect_framework(current_path)
    click.echo(result)

if __name__ == "__main__":
    # current_cwd = os.getcwd()
    # print(current_cwd)
    
    # count_file_types("/Users/wangyue/Desktop/work/test-assistant/learning")

    # 练习4
    snapshot = take_snapshot("/Users/wangyue/Desktop/work/test-assistant/learning")
    for path, hash_val in snapshot.items():
        print(f"{path}: {hash_val}")