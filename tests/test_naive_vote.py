from __future__ import annotations

import pytest

from course_project.evidence import (
    DecisionVote,
    NaiveVoteError,
    naive_multi_source_vote,
)


def _vote(source: str, status: str, hypothesis: str = "hypothesis:field-1") -> DecisionVote:
    return DecisionVote(source_id=source, hypothesis_id=hypothesis, status=status)  # type: ignore[arg-type]


def test_naive_vote_accepts_only_with_strict_majority() -> None:
    result = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("alignment", "accepted"),
            _vote("candidate", "accepted"),
            _vote("verifier", "rejected"),
        ),
    )

    assert result.status == "accepted"
    assert result.total_votes == 3
    assert result.majority_required == 2
    assert result.accepted_votes == 2
    assert result.rejected_votes == 1
    assert result.uncertain_votes == 0


def test_naive_vote_rejects_only_with_strict_majority() -> None:
    result = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("alignment", "rejected"),
            _vote("candidate", "accepted"),
            _vote("llm", "rejected"),
            _vote("verifier", "rejected"),
        ),
    )

    assert result.status == "rejected"
    assert result.majority_required == 3
    assert result.rejected_votes == 3


def test_naive_vote_abstains_on_tie_plurality_or_empty_input() -> None:
    tied = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("alignment", "accepted"),
            _vote("candidate", "rejected"),
        ),
    )
    plurality_without_majority = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("alignment", "accepted"),
            _vote("candidate", "accepted"),
            _vote("llm", "rejected"),
            _vote("verifier", "uncertain"),
        ),
    )
    empty = naive_multi_source_vote("hypothesis:field-1", ())

    assert tied.status == "uncertain"
    assert plurality_without_majority.status == "uncertain"
    assert plurality_without_majority.majority_required == 3
    assert empty.status == "uncertain"
    assert empty.total_votes == 0
    assert empty.majority_required == 0


def test_naive_vote_preserves_uncertain_as_a_real_source_decision() -> None:
    result = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("alignment", "uncertain"),
            _vote("candidate", "uncertain"),
            _vote("verifier", "accepted"),
        ),
    )

    assert result.status == "uncertain"
    assert result.uncertain_votes == 2


def test_naive_vote_is_order_invariant_and_auditable() -> None:
    left = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("verifier", "accepted"),
            _vote("alignment", "rejected"),
            _vote("candidate", "accepted"),
        ),
    )
    right = naive_multi_source_vote(
        "hypothesis:field-1",
        (
            _vote("candidate", "accepted"),
            _vote("verifier", "accepted"),
            _vote("alignment", "rejected"),
        ),
    )

    assert left == right
    assert left.source_decisions == (
        ("alignment", "rejected"),
        ("candidate", "accepted"),
        ("verifier", "accepted"),
    )


def test_naive_vote_fails_closed_on_duplicate_sources() -> None:
    with pytest.raises(NaiveVoteError, match="duplicate source_id"):
        naive_multi_source_vote(
            "hypothesis:field-1",
            (
                _vote("verifier", "accepted"),
                _vote("verifier", "rejected"),
            ),
        )


def test_naive_vote_fails_closed_on_mixed_hypotheses() -> None:
    with pytest.raises(NaiveVoteError, match="expected"):
        naive_multi_source_vote(
            "hypothesis:field-1",
            (
                _vote("candidate", "accepted"),
                _vote("verifier", "accepted", hypothesis="hypothesis:field-2"),
            ),
        )


def test_naive_vote_fails_closed_on_malformed_votes() -> None:
    with pytest.raises(NaiveVoteError, match="hypothesis_id"):
        naive_multi_source_vote("", ())

    with pytest.raises(NaiveVoteError, match="source_id"):
        naive_multi_source_vote(
            "hypothesis:field-1",
            (_vote("", "accepted"),),
        )

    with pytest.raises(NaiveVoteError, match="unsupported status"):
        naive_multi_source_vote(
            "hypothesis:field-1",
            (_vote("candidate", "invalid"),),
        )

    with pytest.raises(TypeError, match="DecisionVote"):
        naive_multi_source_vote("hypothesis:field-1", (object(),))  # type: ignore[arg-type]
