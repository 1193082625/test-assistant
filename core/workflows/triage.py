"""已有 pytest 套件的确定性分组、复跑和归因工作流。"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping, Protocol
from uuid import uuid4

from core.diagnosticians import (
    FailureCluster,
    cluster_pytest_issues,
    diagnose_execution_preflight,
    diagnose_repeatability,
    repeat_test_execution,
)
from core.analyzers import (
    ContractMismatchKind,
    FailureRootCause,
    extract_contract_mismatches,
    read_contract_history,
    extract_failure_root_causes,
    read_symbol_history,
)
from core.analyzers.current_contract import (
    ContractEvidenceStatus,
    analyze_async_result_contract,
    analyze_config_contract,
    analyze_enum_contract,
    analyze_optional_field_contract,
    analyze_type_contract,
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
    ContractMigrationEvidence,
    ContractMigrationType,
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
    contract_migration: ContractMigrationEvidence | None = None


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


def _migration_diagnosis(
    cluster: FailureCluster,
    evidence: TriageEvidence,
) -> Diagnosis | None:
    migration = evidence.contract_migration
    if migration is None:
        return None
    base_details = (
        f"migration_type={migration.migration_type.value}",
        f"target={migration.target}",
        f"old_contract={migration.old_contract}",
        f"current_contract={migration.current_contract}",
        f"current_consistent={str(migration.current_consistent).lower()}",
        *(f"current_source={source}" for source in migration.current_sources),
    )
    if migration.migration_commit:
        base_details += (
            f"migration_commit={migration.migration_commit}",
        )
    if migration.warning_source:
        base_details += (f"warning_source={migration.warning_source}",)
    if migration.lifecycle_gap:
        base_details += (
            f"lifecycle_gap={','.join(migration.lifecycle_gap)}",
        )
    if migration.conflict_reason:
        return Diagnosis(
            summary="当前契约证据冲突，不能确认测试已过期",
            category=DiagnosisCategory.INCONCLUSIVE,
            confidence=DiagnosisConfidence.LOW,
            evidence=_evidence(
                description="契约迁移候选未通过当前一致性门禁",
                source="contract_migration",
                details=base_details + (
                    f"conflict={migration.conflict_reason}",
                ),
            ),
            locations=(_location(cluster),),
            suggested_actions=(DiagnosisAction(
                kind=DiagnosisActionKind.REQUEST_CONFIRMATION,
                description="确认 Schema、实现和配置中的当前业务契约",
            ),),
        )
    if not migration.high_confidence:
        return Diagnosis(
            summary="契约迁移证据不完整",
            category=DiagnosisCategory.INCONCLUSIVE,
            confidence=DiagnosisConfidence.LOW,
            evidence=_evidence(
                description="缺少当前一致性、历史迁移或运行时边界证据",
                source="contract_migration",
                details=base_details,
            ),
            locations=(_location(cluster),),
            suggested_actions=(DiagnosisAction(
                kind=DiagnosisActionKind.REQUEST_CONFIRMATION,
                description="补充本地只读历史或检查异步 API 契约",
            ),),
        )
    runtime = migration.is_runtime_boundary
    if migration.migration_type is ContractMigrationType.ASYNC_GENERATOR_LIFECYCLE:
        action = "使用 await anext(gen)，并在 finally 中 await gen.aclose()"
    elif migration.migration_type is ContractMigrationType.ASYNC_MOCK_RESULT:
        action = "为异步入口配置同步 Result 对象，不让子 AsyncMock 充当结果"
    else:
        action = "按已确认的当前契约更新旧测试，不修改产品实现"
    return Diagnosis(
        summary=(
            "测试 fixture 的异步运行时契约已过期"
            if runtime else "Git 与当前源码确认测试仍使用旧契约"
        ),
        category=DiagnosisCategory.TEST_DEFECT,
        confidence=DiagnosisConfidence.HIGH,
        evidence=_evidence(
            description=(
                "traceback、静态调用和 API 契约形成闭合证据"
                if runtime else "当前双来源契约与同一迁移提交形成闭合证据"
            ),
            source="contract_migration",
            details=base_details,
            kind=DiagnosisEvidenceKind.TEST_VALIDATION,
        ),
        locations=(_location(cluster),),
        suggested_actions=(DiagnosisAction(
            kind=DiagnosisActionKind.FIX_TEST,
            description=action,
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
    root_causes: Mapping[str, FailureRootCause] | None = None,
    evidence_by_root_cause: Mapping[str, TriageEvidence] | None = None,
    run_id: str | None = None,
) -> TriageResult:
    """按固定优先级为每个失败簇生成一条确定性诊断。"""
    evidence_by_node = evidence_by_node or {}
    evidence_by_root_cause = evidence_by_root_cause or {}
    clusters = cluster_pytest_issues(
        suite.issues, dict(root_causes or {})
    )
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
        evidence = evidence_by_root_cause.get(
            cluster.root_cause_key or "",
            evidence_by_node.get(node or "", TriageEvidence()),
        )
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

        migration = _migration_diagnosis(cluster, evidence)
        contract = _contract_diagnosis(cluster, evidence)
        diagnoses.append(
            migration
            or contract
            or _inconclusive_diagnosis(cluster, reports)
        )

    return TriageResult(
        run_id=run_id or uuid4().hex,
        report=suite.report,
        clusters=clusters,
        diagnoses=tuple(diagnoses),
    )


def collect_local_git_triage_evidence(
    *,
    project_root: str | Path,
    suite: PytestSuiteResult,
) -> tuple[
    dict[str, FailureRootCause],
    dict[str, TriageEvidence],
    tuple[str, ...],
]:
    """授权后收集当前源码缺失与本地 Git 删除的最小证据。"""
    root_causes = extract_failure_root_causes(
        project_root=project_root,
        issues=suite.issues,
    )
    evidence_by_cause: dict[str, TriageEvidence] = {}
    degradations: list[str] = []
    for cause in sorted(
        set(root_causes.values()), key=lambda item: item.key
    ):
        history = read_symbol_history(
            project_root=project_root,
            symbol=cause.symbol,
            source_paths=(cause.source_path,),
        )
        if not history.available:
            degradations.append(
                f"{cause.target}: {history.degradation_reason}"
            )
            continue
        if not history.removal_confirmed:
            continue
        details = (
            f"target={cause.target}",
            "current_source=missing",
            "git_history=added_then_deleted",
            f"deletion_commit={history.deletion_commit}",
        )
        evidence_by_cause[cause.key] = TriageEvidence(
            missing_symbol=True,
            removal_confirmed=True,
            obsolete_dependency_mock=(cause.kind == "obsolete_patch"),
            details=details,
        )
    return root_causes, evidence_by_cause, tuple(degradations)


def _project_python_sources(root: Path) -> dict[str, str]:
    """读取有限的项目内 Python 源码；排除测试、缓存和工具产物。"""
    sources: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in {
            ".git", ".autotest", ".venv", "venv", "__pycache__", "tests"
        } for part in relative.parts):
            continue
        if len(sources) >= 500:
            break
        try:
            if path.stat().st_size > 250_000:
                continue
            sources[relative.as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    return sources


def _actual_from_failure(message: str) -> str | None:
    patterns = (
        r"\bgot\s+([^\n,]+)",
        r"E\s+assert\s+([^\s]+)\s+==",
        r"input_value=([^,\]]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
    return None


def collect_contract_migration_triage_evidence(
    *,
    project_root: str | Path,
    suite: PytestSuiteResult,
    git_history_enabled: bool,
) -> tuple[dict[str, TriageEvidence], tuple[str, ...]]:
    """从失败 node 自动闭合测试、当前源码与可选 Git 迁移证据。"""
    root = Path(project_root).resolve()
    source_files = _project_python_sources(root)
    evidence_by_node: dict[str, TriageEvidence] = {}
    degradations: list[str] = []
    for issue in suite.issues:
        if not issue.node_id or issue.node_id in evidence_by_node:
            continue
        test_path_text = issue.node_id.partition("::")[0]
        test_path = (root / test_path_text).resolve()
        try:
            test_path.relative_to(root)
            test_source = test_path.read_text(encoding="utf-8")
        except (ValueError, OSError, UnicodeError):
            continue
        mismatches = extract_contract_mismatches(
            test_source=test_source,
            failure_message=issue.message,
            source_path="<project-source>",
            test_path=test_path_text,
        )
        for mismatch in mismatches:
            migration_type: ContractMigrationType
            current_evidence = None
            runtime_confirmed = False
            if mismatch.kind is ContractMismatchKind.VALUE:
                migration_type = ContractMigrationType.CONFIG_DEFAULT
                current_evidence = analyze_config_contract(
                    target=mismatch.target, source_files=source_files
                )
            elif mismatch.kind is ContractMismatchKind.TYPE:
                migration_type = ContractMigrationType.FIELD_TYPE
                current_evidence = analyze_type_contract(
                    target=mismatch.target, source_files=source_files
                )
            elif mismatch.kind is ContractMismatchKind.OPTIONAL_FIELD:
                migration_type = ContractMigrationType.OPTIONAL_FIELDS
                current_evidence = analyze_optional_field_contract(
                    target=mismatch.target, source_files=source_files
                )
            elif mismatch.kind is ContractMismatchKind.DERIVED_VALUE:
                migration_type = ContractMigrationType.RELATED_CONFIG
                current_evidence = analyze_config_contract(
                    target=mismatch.dependencies[0], source_files=source_files
                ) if mismatch.dependencies else None
            elif mismatch.kind is ContractMismatchKind.ENUM:
                migration_type = ContractMigrationType.ENUM_VALUES
                current_evidence = analyze_enum_contract(
                    target=mismatch.target, source_files=source_files
                )
            elif mismatch.kind is ContractMismatchKind.ASYNC_MOCK_RESULT:
                migration_type = ContractMigrationType.ASYNC_MOCK_RESULT
                current_evidence = analyze_async_result_contract(
                    source_files=source_files
                )
                runtime_confirmed = (
                    current_evidence.status is ContractEvidenceStatus.CONFIRMED
                    and bool(mismatch.warning_source)
                )
            elif mismatch.kind is ContractMismatchKind.ASYNC_GENERATOR_LIFECYCLE:
                migration_type = ContractMigrationType.ASYNC_GENERATOR_LIFECYCLE
                generator_contract = any(
                    "async def " in source
                    and "yield " in source
                    and "finally:" in source
                    for source in source_files.values()
                )
                runtime_confirmed = generator_contract and bool(
                    mismatch.warning_source
                )
                current_evidence = None
            else:
                continue

            current_status = (
                current_evidence.status
                if current_evidence is not None
                else (
                    ContractEvidenceStatus.CONFIRMED
                    if runtime_confirmed
                    else ContractEvidenceStatus.INSUFFICIENT
                )
            )
            current_value = (
                current_evidence.current
                if current_evidence is not None
                else "awaited and closed async generator"
            )
            current_sources = (
                current_evidence.sources
                if current_evidence is not None
                else tuple(
                    path for path, source in source_files.items()
                    if "async def " in source and "yield " in source
                )[:2]
            )
            actual = _actual_from_failure(issue.message)
            if current_value is None and actual is not None:
                current_value = actual
            history_confirmed = False
            migration_commit = None
            if (
                git_history_enabled
                and not runtime_confirmed
                and mismatch.expected is not None
                and current_value is not None
                and current_sources
            ):
                history = read_contract_history(
                    project_root=root,
                    old_expression=str(mismatch.expected),
                    new_expression=str(current_value),
                    source_paths=current_sources,
                )
                history_confirmed = history.migration_confirmed
                migration_commit = history.migration_commit
                if not history.available:
                    degradations.append(
                        f"{mismatch.target}: {history.degradation_reason}"
                    )
            contract = ContractMigrationEvidence(
                migration_type=migration_type,
                target=mismatch.target,
                old_contract=str(mismatch.expected),
                current_contract=str(current_value),
                current_sources=current_sources,
                migration_commit=migration_commit,
                current_consistent=(
                    current_status is ContractEvidenceStatus.CONFIRMED
                ),
                history_confirmed=history_confirmed,
                runtime_boundary_confirmed=runtime_confirmed,
                warning_source=mismatch.warning_source,
                lifecycle_gap=mismatch.missing_lifecycle_steps,
                conflict_reason=(
                    current_evidence.conflict_reason
                    if current_evidence is not None
                    and current_status is ContractEvidenceStatus.CONFLICT
                    else None
                ),
            )
            evidence_by_node[issue.node_id] = TriageEvidence(
                contract_migration=contract
            )
            break
    return evidence_by_node, tuple(degradations)
