"""领域对象持久化仓库"""

from .candidate import (
    CandidateApproval,
    CandidateDiff,
    CandidateRepository,
    build_candidate_content_digest,
)
from .test_spec import TestSpecRepository

__all__ = [
    "CandidateRepository",
    "TestSpecRepository",
    "build_candidate_content_digest",
    "CandidateDiff",
    "CandidateApproval",
]