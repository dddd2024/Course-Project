"""Executable hypothesis verification for EvidenceGraph-PRE."""

from course_project.verification.checks import (
    VerificationError,
    verification_result,
    verify_length,
    verify_sequence,
)
from course_project.verification.provisional_parser import (
    CorpusKind,
    ParsedField,
    ParseCoverageReport,
    ParseSample,
    ParseSampleResult,
    execute_provisional_schema,
)

__all__ = [
    "CorpusKind",
    "ParsedField",
    "ParseCoverageReport",
    "ParseSample",
    "ParseSampleResult",
    "VerificationError",
    "execute_provisional_schema",
    "verification_result",
    "verify_length",
    "verify_sequence",
]
