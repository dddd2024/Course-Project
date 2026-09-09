from __future__ import annotations

from course_project.evidence import (
    GLOBAL_SELECTION_POLICY_VERSION,
    FieldSelectionCandidate,
    select_globally_consistent_fields,
)


def _candidate(
    hypothesis_id: str,
    *,
    offset: int,
    size: int,
    margin: float = 0.9,
    support: float = 0.9,
    conflict: float = 0.0,
    verification: float = 1.0,
) -> FieldSelectionCandidate:
    return FieldSelectionCandidate(
        hypothesis_id=hypothesis_id,
        candidate_id=f"candidate-{hypothesis_id}",
        offset=offset,
        size=size,
        fusion_margin=margin,
        support_score=support,
        conflict_score=conflict,
        verification_score=verification,
    )


def test_non_overlapping_candidates_are_all_selected() -> None:
    result = select_globally_consistent_fields(
        (
            _candidate("sequence", offset=8, size=1),
            _candidate("length", offset=9, size=2),
        )
    )

    assert result.policy == GLOBAL_SELECTION_POLICY_VERSION
    assert result.selected_hypothesis_ids == ("sequence", "length")
    assert result.conflict_group_count == 0
    assert result.conflict_hypothesis_count == 0
    assert result.abstained_hypothesis_count == 0
    assert all(decision.decision == "selected" for decision in result.decisions)
    assert all(decision.reason == "no_overlap_conflict" for decision in result.decisions)


def test_equal_scientific_overlap_abstains_instead_of_using_id_or_order() -> None:
    left = _candidate("z-long", offset=9, size=2)
    right = _candidate("a-short", offset=10, size=1)

    forward = select_globally_consistent_fields((left, right))
    reverse = select_globally_consistent_fields((right, left))

    assert forward == reverse
    assert forward.selected_hypothesis_ids == ()
    assert forward.conflict_group_count == 1
    assert forward.conflict_hypothesis_count == 2
    assert forward.abstained_hypothesis_count == 2
    assert {decision.reason for decision in forward.decisions} == {
        "ambiguous_overlap_conflict"
    }
    assert {
        (decision.hypothesis_id, decision.conflict_hypothesis_ids)
        for decision in forward.decisions
    } == {
        ("z-long", ("a-short",)),
        ("a-short", ("z-long",)),
    }


def test_unique_scientific_dominator_wins_overlap_component() -> None:
    stronger = _candidate(
        "strong",
        offset=9,
        size=2,
        margin=0.95,
        support=0.95,
        conflict=0.0,
        verification=1.0,
    )
    weaker = _candidate(
        "weak",
        offset=10,
        size=1,
        margin=0.80,
        support=0.85,
        conflict=0.05,
        verification=0.95,
    )

    result = select_globally_consistent_fields((weaker, stronger))
    by_id = {decision.hypothesis_id: decision for decision in result.decisions}

    assert result.selected_hypothesis_ids == ("strong",)
    assert result.conflict_group_count == 1
    assert result.abstained_hypothesis_count == 1
    assert by_id["strong"].decision == "selected"
    assert by_id["strong"].reason == "unique_scientific_dominator"
    assert by_id["weak"].decision == "abstained"
    assert by_id["weak"].reason == "dominated_overlap_conflict"


def test_connected_chain_without_component_wide_dominator_abstains_conservatively() -> None:
    # A overlaps B, B overlaps C, while A and C are disjoint.  Picking B would
    # require B to dominate both; otherwise the component stays ambiguous rather
    # than depending on interval traversal order.
    result = select_globally_consistent_fields(
        (
            _candidate("a", offset=0, size=2),
            _candidate("b", offset=1, size=2),
            _candidate("c", offset=2, size=2),
        )
    )

    assert result.selected_hypothesis_ids == ()
    assert result.conflict_group_count == 1
    assert result.conflict_hypothesis_count == 3
    assert result.abstained_hypothesis_count == 3
