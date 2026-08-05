"""可选功能依赖的稳定边界。"""

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Iterable


@dataclass(frozen=True)
class OptionalDependencyError(RuntimeError):
    """调用未安装 extra 所提供的能力。"""

    extra: str
    capability: str

    @property
    def reason(self) -> str:
        return f"{self.extra}_extra_required"

    def __str__(self) -> str:
        return (
            f"{self.reason}: {self.capability} 需要可选依赖；"
            f"请安装 test-assistant[{self.extra}]"
        )


def require_optional_modules(
    *,
    extra: str,
    capability: str,
    modules: Iterable[str],
) -> None:
    """只检查模块是否存在，不导入模块或捕获其内部异常。"""

    if any(find_spec(module) is None for module in modules):
        raise OptionalDependencyError(
            extra=extra,
            capability=capability,
        )
