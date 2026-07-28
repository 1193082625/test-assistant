"""测试意图及预期证据领域模型"""

from dataclasses import dataclass, field
from .enums import (
    EvidenceKind,
    EvidenceStrength,
    TestSpecStatus
)

@dataclass(frozen=True)
class ExpectationEvidence:
    """
    支撑某个测试预期的可追踪证据

    Planner 从源码契约中选择与预期结果有关的证据
    后续诊断依据证据强度判断测试失败能否证明产品缺陷
    """

    # 证据来自 docstring、类型提示、Schema 或已有测试
    kind: EvidenceKind

    # 与当前测试预期直接有关的证据内容
    content: str

    # 证据能够支持预期结果的可信程度
    strength: EvidenceStrength

    # 证据所在文件，便于用户追踪来源
    source_path: str

    # 证据在文件中的起始行
    source_line: int

    def __post_init__(self) -> None:
        """校验证据创建时必须满足的领域约束。"""
        if not isinstance(
            self.kind,
            EvidenceKind,
        ):
            raise ValueError(
                (
                    "ExpectationEvidence kind "
                    "必须是 EvidenceKind"
                )
            )

        if (
            not isinstance(self.content, str)
            or not self.content.strip()
        ):
            raise ValueError(
                (
                    "ExpectationEvidence content "
                    "不能为空"
                )
            )

        if not isinstance(
            self.strength,
            EvidenceStrength,
        ):
            raise ValueError(
                (
                    "ExpectationEvidence strength "
                    "必须是 EvidenceStrength"
                )
            )

        if (
            not isinstance(
                self.source_path,
                str,
            )
            or not self.source_path.strip()
        ):
            raise ValueError(
                (
                    "ExpectationEvidence source_path "
                    "不能为空"
                )
            )

        if (
            not isinstance(self.source_line, int)
            or isinstance(self.source_line, bool)
            or self.source_line <= 0
        ):
            raise ValueError(
                (
                    "ExpectationEvidence source_line "
                    "必须是正整数"
                )
            )

    def to_dict(self) -> dict[str, object]:
        """转换为可写入 JSON 的机器值字典"""
        return {
            "kind": self.kind.value,
            "content": self.content,
            "strength": self.strength.value,
            "source_path": self.source_path,
            "source_line": self.source_line,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ExpectationEvidence":
        """从机器值字典↩恢复预期证据"""
        return cls(
            kind=EvidenceKind(data["kind"]),
            content=str(data["content"]),
            strength=EvidenceStrength(data["strength"]),
            source_path=str(data["source_path"]),
            source_line=int(data["source_line"]),
        )



@dataclass(frozen=True)
class TestSpec:
    """
    一条结构化测试意图

    TestSpec 描述准备验证什么行为及预期依据
    不包含最终生成的 Python 测试代码
    """

    # 稳定唯一标识，后续用于持久化和候选文件关联
    id: str

    # 被测试源码符号的完整限定名，例如 demo.add
    target_symbol: str

    # 用自然语言说明准备验证的业务行为
    behavior: str

    # 调用目标前需要准备的输入、对象或环境
    arrange: dict[str, object]

    # 准备执行的操作
    action: str

    # 结构化预期结果，例如返回值、异常或状态变化
    expected: dict[str, object]

    # 支撑 expected 的可追踪证据
    evidence: list[ExpectationEvidence] = field(default_factory=list)

    # 测试时需要隔离的副作用类型
    side_effects: list[str] = field(default_factory=list)

    # 新建计划必须先等待人工评审
    status: TestSpecStatus = TestSpecStatus.PROPOSED

    def __post_init__(self) -> None:
        """
        校验 TestSpec 创建时必须满足的领域约束

        Python 创建对象时大致执行
        调用 TestSpec(...)
        → dataclass 自动生成的 __init__ 给字段赋值
        → 自动调用 __post_init__
        → 对象创建完成

        因此，__post_init__() 适合集中处理跨字段或运行时校验

        这叫维护领域不变量：
        任何已经成功创建的 TestSpec，都一定有合法的 id 和 target_symbol。
        """
        if (
            not isinstance(self.id, str)
            or not self.id.strip()
        ):
            raise ValueError("TestSpec id 不能为空")

        if (
            not isinstance(self.target_symbol, str)
            or not self.target_symbol.strip()
        ):
            raise ValueError(
                "TestSpec target_symbol 不能为空"
            )

        if (
            not isinstance(self.behavior, str)
            or not self.behavior.strip()
        ):
            raise ValueError(
                "TestSpec behavior 不能为空"
            )

        if (
            not isinstance(self.action, str)
            or not self.action.strip()
        ):
            raise ValueError(
                "TestSpec action 不能为空"
            )

        if (
            not isinstance(self.expected, dict)
            or not self.expected
        ):
            raise ValueError(
                "TestSpec expected 不能为空"
            )

        if not isinstance(self.arrange, dict):
            raise ValueError(
                "TestSpec arrange 必须是字典"
            )

        if (
            not isinstance(self.evidence, list)
            or not all(
                isinstance(
                    item,
                    ExpectationEvidence,
                )
                for item in self.evidence
            )
        ):
            raise ValueError(
                (
                    "TestSpec evidence 必须只包含 "
                    "ExpectationEvidence"
                )
            )

        if (
            not isinstance(
                self.side_effects,
                list,
            )
            or not all(
                isinstance(item, str)
                for item in self.side_effects
            )
        ):
            raise ValueError(
                (
                    "TestSpec side_effects "
                    "必须只包含字符串"
                )
            )

        if not isinstance(
            self.status,
            TestSpecStatus,
        ):
            raise ValueError(
                (
                    "TestSpec status 必须是 "
                    "TestSpecStatus"
                )
            )

    @property
    def expectation_strength(self) -> EvidenceStrength:
        """
        计算当前预期能够获得的最高证据强度

        没有任何证据时，预期只能被视为弱推断
        """
        if not self.evidence:
            return EvidenceStrength.WEAK

        strengths = {
            item.strength
            for item in self.evidence
        }

        if EvidenceStrength.STRONG in strengths:
            return EvidenceStrength.STRONG

        if EvidenceStrength.MEDIUM in strengths:
            return EvidenceStrength.MEDIUM

        return EvidenceStrength.WEAK

    @property
    def is_weak_inference(self) -> bool:
        """当前预期是否只能得到弱证据支持"""
        return (
            self.expectation_strength
            is EvidenceStrength.WEAK
        )

    def to_dict(self) -> dict[str, object]:
        """
        转换为稳定、可序列化的字典

        枚举统一输出机器字符串，容器返回副本
        避免调用方修改序列化结果时影响领域对象
        """
        return {
            "id": self.id,
            "target_symbol": self.target_symbol,
            "behavior": self.behavior,
            "arrange": dict(self.arrange),
            "action": self.action,
            "expected": dict(self.expected),
            "evidence": [
                item.to_dict()
                for item in self.evidence
            ],
            "side_effects": list(self.side_effects),
            "status": self.status.value,
            "expectation_strength": self.expectation_strength.value,
            "is_weak_inference": self.is_weak_inference,
        }

    @classmethod
    def from_dict(
            cls,
            data: dict[str, object],
    ) -> "TestSpec":
        """
        从持久化字典恢复 TestSpec。

        不对领域字段做隐式类型转换；
        非法输入统一交给领域校验拒绝。
        """
        evidence_data = data.get(
            "evidence",
            [],
        )

        if not isinstance(
                evidence_data,
                list,
        ):
            raise ValueError(
                (
                    "TestSpec evidence 必须只包含 "
                    "ExpectationEvidence"
                )
            )

        return cls(
            id=data["id"],
            target_symbol=data[
                "target_symbol"
            ],
            behavior=data["behavior"],
            arrange=data["arrange"],
            action=data["action"],
            expected=data["expected"],
            evidence=[
                ExpectationEvidence.from_dict(
                    item
                )
                for item in evidence_data
            ],
            side_effects=data.get(
                "side_effects",
                [],
            ),
            status=TestSpecStatus(
                data.get(
                    "status",
                    TestSpecStatus.PROPOSED.value,
                )
            ),
        )