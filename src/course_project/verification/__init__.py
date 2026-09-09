"""Executable hypothesis verification for EvidenceGraph-PRE."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from course_project.models import ExecutableCheck, ProtocolHypothesis
from course_project.verification.checks import (
    VerificationError,
    verification_result,
    verify_checksum,
    verify_constant,
    verify_hypothesis,
    verify_length,
    verify_magic,
    verify_sequence,
)
from course_project.verification.checks import (
    verify_enum as _verify_enum_family,
)
from course_project.verification.checks import (
    verify_timestamp as _verify_timestamp_family,
)
from course_project.verification.semantic_checks import (
    verify_enum as _verify_enum_semantic,
)
from course_project.verification.semantic_checks import (
    verify_timestamp as _verify_timestamp_semantic,
)

BytesLike = bytes | bytearray | memoryview


def verify_enum(
    hypothesis: ProtocolHypothesis,
    messages: Iterable[BytesLike],
    *,
    family_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float | None = None,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Route both merged enum contracts without silently dropping parameters."""

    if family_ids is not None or "mode" in hypothesis.parameters or hypothesis.semantic_type == "message_type":
        return _verify_enum_semantic(
            hypothesis,
            messages,
            family_ids=family_ids,
            minimum_samples=minimum_samples,
            accept_threshold=accept_threshold if accept_threshold is not None else 0.9,
            reject_threshold=reject_threshold,
        )
    return _verify_enum_family(
        hypothesis,
        messages,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold if accept_threshold is not None else 0.95,
        reject_threshold=reject_threshold,
    )


def verify_timestamp(
    hypothesis: ProtocolHypothesis,
    messages: Sequence[BytesLike],
    *,
    session_ids: Sequence[str] | None = None,
    minimum_samples: int = 3,
    accept_threshold: float = 0.9,
    reject_threshold: float = 0.5,
) -> ExecutableCheck:
    """Route legacy and explicit timestamp parameter contracts after integration."""

    verifier = (
        _verify_timestamp_semantic
        if "mode" in hypothesis.parameters
        else _verify_timestamp_family
    )
    return verifier(
        hypothesis,
        messages,
        session_ids=session_ids,
        minimum_samples=minimum_samples,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
    )


__all__ = [
    "VerificationError",
    "verification_result",
    "verify_checksum",
    "verify_constant",
    "verify_enum",
    "verify_hypothesis",
    "verify_length",
    "verify_magic",
    "verify_sequence",
    "verify_timestamp",
]
