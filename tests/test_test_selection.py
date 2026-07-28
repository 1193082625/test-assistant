from core.models import (
    TestSelection as Selection,
    TestSelectionMode as SelectionMode,
)

def test_direct_selection_records_evidence_and_warnings():
    selection = Selection(
        mode=SelectionMode.DIRECT,
        test_files=["tests/test_demo.py"],
        evidence=[
            (
                "demo.add directly maps to "
                "tests.test_demo.test_add"
            )
        ],
        warnings=[]
    )

    assert selection.mode.value == "direct" # 使用了哪种选择策略
    assert selection.test_files == ["tests/test_demo.py"] # 最终应该执行哪些测试文件
    assert selection.evidence == [ # 为什么选择这些文件
        (
            "demo.add directly maps to "
            "tests.test_demo.test_add"
        )
    ]

    assert selection.warnings == [] # 有哪些降级、缺失或不确定情况

def test_selection_serializes_to_stable_machine_values():
    selection = Selection(
        mode=SelectionMode.FULL,
        test_files=["tests/test_b.py", "tests/test_a.py"],
        evidence=[
            "Deleted Python files: demo.py",
        ],
        warnings=[
            "Falling back to all pytest files",
        ],
    )

    serialized = selection.to_dict()

    assert serialized == {
        "mode": "full",
        "test_files": [
            "tests/test_a.py",
            "tests/test_b.py",
        ],
        "evidence": [
            "Deleted Python files: demo.py",
        ],
        "warnings": [
            "Falling back to all pytest files",
        ],
    }

    assert type(serialized["mode"]) is str