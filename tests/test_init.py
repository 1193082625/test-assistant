"""初始化配置写入测试"""

import yaml

from cli.commands.init import write_config
from core.models import ProjectType, Language, FrameworkInfo
from core.models import TestFramework as Framework

def test_write_config_serializes_enums_as_machine_strings(tmp_path):
    project = FrameworkInfo(
        project_type=ProjectType.BACKEND,
        language=Language.PYTHON,
        frameworks=["FastAPI"],
        test_frameworks=[Framework.PYTEST],
        build_tools=[]
    )

    config_path = write_config(
        autotest_path=str(tmp_path),
        project_name="demo",
        project_config=project,
        mode="auto"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["project"]["type"] == "backend"
    assert config["project"]["language"] == "python"
    assert config["project"]["test_frameworks"] == ["pytest"]
    # test_framework 已经修改为 test_frameworks，这里断言旧字段已不存在
    assert "test_framework" not in config["project"]

