"""从已批准 TestSpec 生成候选代码"""
from .test_generator import (
    generate_tests_for_project,
    generate_tests_for_file,
    get_class_def_from_import
)