"""环境诊断领域模型测试"""
from dataclasses import FrozenInstanceError

import pytest

from core.models import (
    DoctorResult,
    DoctorStatus,
    EnvironmentCheck,
    EnvironmentCheckState,
)


def test_environment_check_state_has_stable_machine_values():
    assert (
        EnvironmentCheckState.AVAILABLE.value
        == "available"
    )
    assert (
        EnvironmentCheckState.UNAVAILABLE.value
        == "unavailable"
    )
    assert (
        EnvironmentCheckState.INCOMPATIBLE.value
        == "incompatible"
    )
    assert (
        EnvironmentCheckState.TIMED_OUT.value
        == "timed_out"
    )
    assert (
        EnvironmentCheckState.FAILED.value
        == "failed"
    )
    assert (
        EnvironmentCheckState.NOT_APPLICABLE.value
        == "not_applicable"
    )

def test_doctor_status_has_stable_machine_values():
    assert DoctorStatus.HEALTHY.value == "healthy"
    assert (
        DoctorStatus.INCOMPATIBLE.value == "incompatible"
    )
    assert (
        DoctorStatus.INFRA_ERROR.value == "infra_error"
    )

def test_environment_check_preserves_environment_facts():
    check = EnvironmentCheck(
        name="pytest",
        state=EnvironmentCheckState.AVAILABLE,
        version="9.0.2",
        executable="/venv/bin/python",
        required=True,
        capabilities=(
            "triage",
            "verify",
        ),
    )

    assert check.name == "pytest"
    assert (
        check.state
        is EnvironmentCheckState.AVAILABLE
    )
    assert check.version == "9.0.2"
    assert (
        check.executable
        == "/venv/bin/python"
    )
    assert check.required is True
    assert check.reason is None
    assert check.capabilities == (
        "triage",
        "verify",
    )

@pytest.mark.parametrize(
    "name",
    [
        "",
        "  ",
        None,
    ],
)
def test_environment_check_rejects_empty_name(name):
    with pytest.raises(ValueError, match="name 不能为空"):
        EnvironmentCheck(
            name=name,
            state=EnvironmentCheckState.AVAILABLE,
            version="1.0",
            executable=None,
            required=True,
        )

@pytest.mark.parametrize(
    "state",
    [
        EnvironmentCheckState.UNAVAILABLE,
        EnvironmentCheckState.INCOMPATIBLE,
        EnvironmentCheckState.TIMED_OUT,
        EnvironmentCheckState.FAILED,
        EnvironmentCheckState.NOT_APPLICABLE,
    ],
)
def test_non_available_check_requires_reason(
    state,
):
    with pytest.raises(
        ValueError,
        match="非可用状态必须包含原因",
    ):
        EnvironmentCheck(
            name="pytest",
            state=state,
            version=None,
            executable=None,
            required=True,
            reason=None,
        )

def test_environment_check_requires_real_boolean():
    with pytest.raises(
        ValueError,
        match="required 必须是 bool",
    ):
        EnvironmentCheck(
            name="ruff",
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="1.0",
            executable=None,
            required=1,
        )


def test_environment_check_rejects_empty_capability():
    with pytest.raises(
        ValueError,
        match="capabilities 必须是非空字符串",
    ):
        EnvironmentCheck(
            name="pytest",
            state=(
                EnvironmentCheckState.AVAILABLE
            ),
            version="9.0",
            executable=None,
            required=True,
            capabilities=(
                "triage",
                "",
            ),
        )

def test_doctor_result_serializes_stable_schema():
    python_check = EnvironmentCheck(
        name="python",
        state=EnvironmentCheckState.AVAILABLE,
        version="3.13.5",
        executable="/venv/bin/python",
        required=True,
        capabilities=(
            "cli",
            "triage",
            "audit",
        ),
    )
    ruff_check = EnvironmentCheck(
        name="ruff",
        state=EnvironmentCheckState.UNAVAILABLE,
        version=None,
        executable=None,
        required=False,
        reason="module_not_found",
        capabilities=(
            "audit_quality",
        ),
    )

    result = DoctorResult(
        schema_version=1,
        status=DoctorStatus.HEALTHY,
        test_assistant_version="0.6.1",
        project_path="/project",
        python_implementation="cpython",
        platform="macOS-15-arm64",
        checks=(
            python_check,
            ruff_check,
        ),
    )

    assert result.to_dict() == {
        "schema_version": 1,
        "status": "healthy",
        "test_assistant_version": "0.6.1",
        "project_path": "/project",
        "python_implementation": "cpython",
        "platform": "macOS-15-arm64",
        "checks": [
            {
                "name": "python",
                "state": "available",
                "version": "3.13.5",
                "executable": "/venv/bin/python",
                "required": True,
                "reason": None,
                "capabilities": [
                    "cli",
                    "triage",
                    "audit",
                ],
            },
            {
                "name": "ruff",
                "state": "unavailable",
                "version": None,
                "executable": None,
                "required": False,
                "reason": "module_not_found",
                "capabilities": [
                    "audit_quality",
                ],
            },
        ],
    }

@pytest.mark.parametrize(
    "schema_version",
    [
        0,
        2,
        True,
        "1",
    ],
)
def test_doctor_result_requires_schema_version_one(
    schema_version,
):
    with pytest.raises(
        ValueError,
        match="schema_version 必须是 1",
    ):
        DoctorResult(
            schema_version=schema_version,
            status=DoctorStatus.HEALTHY,
            test_assistant_version="0.6.1",
            project_path="/project",
            python_implementation="cpython",
            platform="macOS",
            checks=(),
        )

def test_doctor_result_rejects_duplicate_check_names():
    first = EnvironmentCheck(
        name="pytest",
        state=EnvironmentCheckState.AVAILABLE,
        version="9.0",
        executable=None,
        required=True,
    )
    second = EnvironmentCheck(
        name="pytest",
        state=EnvironmentCheckState.UNAVAILABLE,
        version=None,
        executable=None,
        required=True,
        reason="module_not_found",
    )

    with pytest.raises(
        ValueError,
        match="检查名称不能重复",
    ):
        DoctorResult(
            schema_version=1,
            status=DoctorStatus.HEALTHY,
            test_assistant_version="0.6.1",
            project_path="/project",
            python_implementation="cpython",
            platform="macOS",
            checks=(
                first,
                second,
            ),
        )

@pytest.mark.parametrize(
    "field_name",
    [
        "test_assistant_version",
        "project_path",
        "python_implementation",
        "platform",
    ],
)
@pytest.mark.parametrize(
    "invalid_value",
    [
        "",
        "   ",
        None,
    ],
)
def test_doctor_result_rejects_empty_text_fields(
    field_name,
    invalid_value,
):
    values = {
        "schema_version": 1,
        "status": DoctorStatus.HEALTHY,
        "test_assistant_version": "0.6.1",
        "project_path": "/project",
        "python_implementation": "cpython",
        "platform": "macOS",
        "checks": (),
    }
    values[field_name] = invalid_value

    with pytest.raises(
        ValueError,
        match=f"{field_name} 不能为空",
    ):
        DoctorResult(**values)

@pytest.mark.parametrize(
    "checks",
    [
        [],
        ["pytest"],
        (object(),),
        None,
    ],
)
def test_doctor_result_rejects_invalid_checks(
    checks,
):
    with pytest.raises(
        ValueError,
        match=(
            "checks 必须是 EnvironmentCheck"
        ),
    ):
        DoctorResult(
            schema_version=1,
            status=DoctorStatus.HEALTHY,
            test_assistant_version="0.6.1",
            project_path="/project",
            python_implementation="cpython",
            platform="macOS",
            checks=checks,
        )

def test_environment_check_is_immutable():
    check = EnvironmentCheck(
        name="pytest",
        state=EnvironmentCheckState.AVAILABLE,
        version="9.0",
        executable=None,
        required=True,
    )

    with pytest.raises(
        FrozenInstanceError,
    ):
        check.version = "10.0"

def test_doctor_result_is_immutable():
    result = DoctorResult(
        schema_version=1,
        status=DoctorStatus.HEALTHY,
        test_assistant_version="0.6.1",
        project_path="/project",
        python_implementation="cpython",
        platform="macOS",
        checks=(),
    )

    with pytest.raises(
        FrozenInstanceError,
    ):
        result.status = (
            DoctorStatus.INFRA_ERROR
        )

@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("version", ""),
        ("version", "   "),
        ("executable", ""),
        ("executable", "   "),
    ],
)
def test_environment_check_rejects_empty_optional_text(
    field_name,
    invalid_value,
):
    values = {
        "name": "pytest",
        "state": EnvironmentCheckState.AVAILABLE,
        "version": "9.0",
        "executable": "/venv/bin/python",
        "required": True,
    }
    values[field_name] = invalid_value

    with pytest.raises(ValueError):
        EnvironmentCheck(**values)