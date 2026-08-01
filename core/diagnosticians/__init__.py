"""测试失败的确定性诊断服务。"""

from .attribution import diagnose_stable_failure
from .execution import diagnose_execution_preflight
from .repeatability import (
    diagnose_repeatability,
    repeat_test_execution,
)
from .clustering import (
    FailureCluster,
    cluster_pytest_issues,
    failure_fingerprint,
    normalize_failure_message,
)

__all__ = [
    "diagnose_stable_failure",
    "diagnose_execution_preflight",
    "diagnose_repeatability",
    "repeat_test_execution",
    "FailureCluster",
    "cluster_pytest_issues",
    "failure_fingerprint",
    "normalize_failure_message",
]
