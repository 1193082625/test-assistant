"""已有 pytest 套件的确定性分组、复跑和归因工作流。"""

from dataclasses import dataclass
from typing import Mapping, Protocol
from uuid import uuid4

from core.diagnosticians import (
    FailureCluster,
    cluster_pytest_issues,
    diagnose_execution_preflight,
    diagnose_repeatability,
    repeat_test_execution,
)
from core.executors.base import (
    ExecutionReport,
    PytestSuiteResult,
)
from core.models import (
    Diagnosis,
    DiagnosisAction,
    DiagnosisActionKind,
    DiagnosisCategory,
    DiagnosisConfidence,
    DiagnosisEvidence,
    DiagnosisEvidenceKind,
    DiagnosisLocation,
    EvidenceKind,
    TriageResult,
    TriagePhase,
)


class TriageExecutor(Protocol):
    def execute(self, file_path: str) -> ExecutionReport:
        ...


@dataclass(frozen=True)
class TriageEvidence:
    """调用方已确认、可审计的归因事实；不推测提交意图。"""

    missing_symbol: bool = False
    removal_confirmed: bool = False
    obsolete_dependency_mock: bool = False
    contract_values: tuple[str, ...] = ()
    contract_kinds: frozenset[EvidenceKind] = frozenset()
    supporting_test_count: int = 0
    implementation_violates_contract: bool = False
    details: tuple[str, ...] = ()


def _location(cluster: FailureCluster) -> DiagnosisLocation:
    issue = cluster.issues[0]
    if issue.locations:
        return issue.locations[0]
    if cluster.representative_node:
        path, _, symbol = cluster.representative_node.partition("::")
        return DiagnosisLocation(path=path, symbol=symbol or None)
    return DiagnosisLocation(path="<pytest-session>")


def _evidence(
    *,
    description: str,
    source: str,
    details: tuple[str, ...],
    kind: DiagnosisEvidenceKind = DiagnosisEvidenceKind.CONTRACT,
) -> tuple[DiagnosisEvidence, ...]:
    return (DiagnosisEvidence(
        kind=kind,
        description=description,
        source=source,
        details=details or ("confirmed=true",),
    ),)


def _collection_diagnosis(cluster: FailureCluster) -> Diagnosis:
    issue = cluster.issues[0]
    return Diagnosis(
        summary="pytest 测试收集失败",
        category=DiagnosisCategory.TEST_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=_evidence(
            description="pytest collection hook 报告错误",
            source="pytest_structured_event",
            details=(f"message={issue.message}",),
            kind=DiagnosisEvidenceKind.TEST_VALIDATION,
        ),
        locations=(_location(cluster),),
        suggested_actions=(DiagnosisAction(
            kind=DiagnosisActionKind.FIX_TEST,
            description="修复测试导入、语法或收集结构后重试",
        ),),
    )


def _test_structure_diagnosis(
    cluster: FailureCluster,
    evidence: TriageEvidence,
) -> Diagnosis | None:
    confirmed_removal = (
        evidence.missing_symbol and evidence.removal_confirmed
    )
    if not confirmed_removal and not evidence.obsolete_dependency_mock:
        return None
    summary = (
        "测试仍要求已确认移除的源码能力"
        if confirmed_removal
        else "测试仍 mock 已确认迁移的旧依赖"
    )
    return Diagnosis(
        summary=summary,
        category=DiagnosisCategory.TEST_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=_evidence(
            description="当前源码与历史证据确认测试结构已过期",
            source="triage_evidence",
            details=evidence.details,
            kind=DiagnosisEvidenceKind.TEST_VALIDATION,
        ),
        locations=(_location(cluster),),
        suggested_actions=(DiagnosisAction(
            kind=DiagnosisActionKind.FIX_TEST,
            description="按当前公开能力更新旧测试，不恢复已移除接口",
        ),),
    )


def _contract_diagnosis(
    cluster: FailureCluster,
    evidence: TriageEvidence,
) -> Diagnosis | None:
    distinct_values = {
        value.strip() for value in evidence.contract_values if value.strip()
    }
    if len(distinct_values) > 1:
        return Diagnosis(
            summary="有效契约证据彼此冲突",
            category=DiagnosisCategory.INCONCLUSIVE,
            confidence=DiagnosisConfidence.LOW,
            evidence=_evidence(
                description="发现多个不一致的有效契约值",
                source="triage_evidence",
                details=tuple(sorted(distinct_values)),
            ),
            locations=(_location(cluster),),
            suggested_actions=(DiagnosisAction(
                kind=DiagnosisActionKind.REQUEST_CONFIRMATION,
                description="请业务负责人确认应采用的契约值",
            ),),
        )

    required = {EvidenceKind.TYPE_HINT, EvidenceKind.DOCSTRING}
    strong_violation = (
        required <= evidence.contract_kinds
        and evidence.supporting_test_count >= 2
        and evidence.implementation_violates_contract
    )
    if not strong_violation:
        return None
    return Diagnosis(
        summary="产品实现违反一致的返回契约",
        category=DiagnosisCategory.PRODUCT_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=_evidence(
            description="类型、文档和多个测试形成一致契约",
            source="triage_evidence",
            details=(
                "type_hint=true",
                "docstring=true",
                f"supporting_tests={evidence.supporting_test_count}",
                *evidence.details,
            ),
        ),
        locations=(_location(cluster),),
        suggested_actions=(DiagnosisAction(
            kind=DiagnosisActionKind.INSPECT_PRODUCT,
            description="修复实现以满足已确认的返回契约",
        ),),
    )


def _inconclusive_diagnosis(
    cluster: FailureCluster,
    reports: tuple[ExecutionReport, ...],
) -> Diagnosis:
    outcomes = tuple(
        f"attempt_{index}={report.error_type or 'passed'}"
        for index, report in enumerate(reports, start=1)
    )
    return Diagnosis(
        summary="现有证据不足以确定失败归因",
        category=DiagnosisCategory.INCONCLUSIVE,
        confidence=DiagnosisConfidence.LOW,
        evidence=_evidence(
            description="精确复跑后仍缺少无冲突的契约证据",
            source="repeat_test_execution",
            details=outcomes,
            kind=DiagnosisEvidenceKind.REPEAT_RUN,
        ),
        locations=(_location(cluster),),
        suggested_actions=(DiagnosisAction(
            kind=DiagnosisActionKind.REQUEST_CONFIRMATION,
            description="检查源码、测试、契约和 Git 历史后确认预期",
        ),),
    )


def triage_pytest_suite(
    *,
    suite: PytestSuiteResult,
    executor: TriageExecutor,
    evidence_by_node: Mapping[str, TriageEvidence] | None = None,
    run_id: str | None = None,
) -> TriageResult:
    """按固定优先级为每个失败簇生成一条确定性诊断。"""
    evidence_by_node = evidence_by_node or {}
    clusters = cluster_pytest_issues(suite.issues)
    diagnoses: list[Diagnosis] = []

    preflight = diagnose_execution_preflight(
        report=suite.report,
        test_file="<pytest-suite>",
    )
    if preflight is not None and (
        suite.report.error_type not in {"test_failure", None}
    ) and not any(
        issue.phase is TriagePhase.COLLECTION
        and issue.outcome == "error"
        for issue in suite.issues
    ):
        return TriageResult(
            run_id=run_id or uuid4().hex,
            report=suite.report,
            clusters=clusters,
            diagnoses=(preflight,),
        )

    for cluster in clusters:
        if any(
            issue.phase is TriagePhase.COLLECTION
            for issue in cluster.issues
        ):
            diagnoses.append(_collection_diagnosis(cluster))
            continue

        node = cluster.representative_node
        evidence = evidence_by_node.get(node or "", TriageEvidence())
        structure = _test_structure_diagnosis(cluster, evidence)
        if structure is not None:
            diagnoses.append(structure)
            continue

        if node is None:
            diagnoses.append(_inconclusive_diagnosis(cluster, ()))
            continue

        reports = repeat_test_execution(
            executor=executor,
            test_node_id=node,
            attempts=3,
        )
        repeatability = diagnose_repeatability(
            reports=reports,
            test_node_id=node,
        )
        if repeatability.category in {
            DiagnosisCategory.INFRA_DEFECT,
            DiagnosisCategory.FLAKY,
        }:
            diagnoses.append(repeatability)
            continue

        contract = _contract_diagnosis(cluster, evidence)
        diagnoses.append(
            contract or _inconclusive_diagnosis(cluster, reports)
        )

    return TriageResult(
        run_id=run_id or uuid4().hex,
        report=suite.report,
        clusters=clusters,
        diagnoses=tuple(diagnoses),
    )
