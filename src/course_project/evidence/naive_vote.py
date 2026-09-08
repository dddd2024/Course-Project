"""Naive equal-source voting baseline for EvidenceGraph-PRE experiments.

This module is intentionally *not* provenance-aware fusion.  It provides the
simple control required by the experiment plan: one equal vote per named
source, no confidence weighting, no dependency collapse, and no learned
parameters.  Accepted or rejected requires a strict majority; every other case
abstains as uncertain.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from course_project.models import DecisionStatus

_ALLOWED_STATUSES = {"accepted", "rejected", "uncertain"}


class NaiveVoteError(ValueError):
    """Raised when source-level votes are unsafe to compare."""


@dataclass(frozen=True, slots=True)
class DecisionVote:
    """One source's equal-weight decision for one protocol hypothesis."""

    source_id: str
    hypothesis_id: str
    status: DecisionStatus


@dataclass(frozen=True, slots=True)
class NaiveVoteResult:
    """Auditable result of the strict-majority naive baseline."""

    hypothesis_id: str
    status: DecisionStatus
    total_votes: int
    majority_required: int
    accepted_votes: int
    rejected_votes: int
    uncertain_votes: int
    source_decisions: tuple[tuple[str, DecisionStatus], ...]


def naive_multi_source_vote(
    hypothesis_id: str, votes: Iterable[DecisionVote]
) -> NaiveVoteResult:
    """Combine one equal vote per source using a conservative strict majority.

    The baseline deliberately ignores scores, provenance links, independence
    groups, sample coverage and source-specific weights.  Those distinctions
    belong to the proposed EvidenceGraph-PRE method, not to its naive control.

    ``accepted`` or ``rejected`` is returned only when that status has strictly
    more than half of all source votes.  Ties, plurality without a strict
    majority, an ``uncertain`` majority, and empty input all return
    ``uncertain``.
    """

    if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
        raise NaiveVoteError("hypothesis_id must be a non-empty string")

    records = tuple(votes)
    by_source: dict[str, DecisionVote] = {}
    for vote in records:
        _validate_vote(vote, expected_hypothesis_id=hypothesis_id)
        if vote.source_id in by_source:
            raise NaiveVoteError(f"duplicate source_id: {vote.source_id}")
        by_source[vote.source_id] = vote

    ordered = tuple(by_source[source_id] for source_id in sorted(by_source))
    accepted = sum(vote.status == "accepted" for vote in ordered)
    rejected = sum(vote.status == "rejected" for vote in ordered)
    uncertain = sum(vote.status == "uncertain" for vote in ordered)
    total = len(ordered)
    majority_required = total // 2 + 1 if total else 0

    status: DecisionStatus = "uncertain"
    if total and accepted >= majority_required:
        status = "accepted"
    elif total and rejected >= majority_required:
        status = "rejected"

    return NaiveVoteResult(
        hypothesis_id=hypothesis_id,
        status=status,
        total_votes=total,
        majority_required=majority_required,
        accepted_votes=accepted,
        rejected_votes=rejected,
        uncertain_votes=uncertain,
        source_decisions=tuple((vote.source_id, vote.status) for vote in ordered),
    )


def _validate_vote(vote: DecisionVote, *, expected_hypothesis_id: str) -> None:
    if not isinstance(vote, DecisionVote):
        raise TypeError("votes must use course_project.evidence.DecisionVote")
    if not vote.source_id.strip():
        raise NaiveVoteError("vote source_id must be non-empty")
    if not vote.hypothesis_id.strip():
        raise NaiveVoteError(f"vote from {vote.source_id!r} has an empty hypothesis_id")
    if vote.hypothesis_id != expected_hypothesis_id:
        raise NaiveVoteError(
            f"vote from {vote.source_id!r} targets {vote.hypothesis_id!r}, "
            f"expected {expected_hypothesis_id!r}"
        )
    if vote.status not in _ALLOWED_STATUSES:
        raise NaiveVoteError(
            f"vote from {vote.source_id!r} has unsupported status: {vote.status!r}"
        )
