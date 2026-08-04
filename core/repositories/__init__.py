"""领域对象持久化仓库"""

from .candidate import (
    CandidateApproval,
    CandidateDiff,
    CandidateRepository,
    build_candidate_content_digest,
)
from .diagnosis import (
    DiagnosisRepository,
    redact_sensitive_text,
)
from .test_spec import TestSpecRepository
from .verification import VerificationStateRepository
from .triage import TriageRepository
from .permissions import GitPermissionRepository, git_repository_identity
from .audit import AuditRepository

__all__ = [
    "DiagnosisRepository",
    "redact_sensitive_text",
    "CandidateRepository",
    "TestSpecRepository",
    "VerificationStateRepository",
    "build_candidate_content_digest",
    "CandidateDiff",
    "CandidateApproval",
    "TriageRepository",
    "GitPermissionRepository",
    "git_repository_identity",
    "AuditRepository",
]
