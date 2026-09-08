from __future__ import annotations

import pytest

from course_project.evidence.dependency_collapse import (
    EvidenceDependencyError,
    collapse_dependent_evidence,
)
from course_project.models import Evidence


def _evidence(
    evidence_id: str,
    *,
    score: float,
    group: str | None,
    parents: tuple[str, ...] = (),
    samples: tuple[str, ...] = (),
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_component="test",
        method="fixture",
        feature_family="semantic",
        score=score,
        parent_evidence_ids=parents,
        independence_group=group,
        sample_ids=samples,
    )


def test_same_independence_group_collapses_without_double_counting() -> None:
    result = collapse_dependent_evidence(
        (
            _evidence("candidate", score=0.72, group="region:4:2", samples=("m1",)),
            _evidence("verifier", score=0.96, group="region:4:2", samples=("m1", "m2")),
        )
    )

    assert result.raw_count == 2
    assert result.effective_count == 1
    assert result.raw_support_total == pytest.approx(1.68)
    assert result.effective_support_total == pytest.approx(0.96)

    contribution = result.contributions[0]
    assert contribution.representative_evidence_id == "verifier"
    assert contribution.evidence_ids == ("candidate", "verifier")
    assert contribution.independence_groups == ("region:4:2",)
    assert contribution.sample_ids == ("m1", "m2")
    assert contribution.dependency_signals == ("shared_independence_group",)


def test_parent_link_collapses_even_when_group_labels_differ() -> None:
    result = collapse_dependent_evidence(
        (
            _evidence("raw", score=0.61, group="raw-source"),
            _evidence("derived", score=0.84, group="derived-check", parents=("raw",)),
        )
    )

    assert result.effective_count == 1
    contribution = result.contributions[0]
    assert contribution.evidence_ids == ("derived", "raw")
    assert contribution.independence_groups == ("derived-check", "raw-source")
    assert contribution.effective_score == pytest.approx(0.84)
    assert contribution.raw_score_total == pytest.approx(1.45)
    assert contribution.dependency_signals == ("parent_link",)


def test_independent_groups_remain_separate_contributions() -> None:
    result = collapse_dependent_evidence(
        (
            _evidence("a", score=0.40, group="producer-a"),
            _evidence("b", score=0.70, group="producer-b"),
            _evidence("c", score=0.20, group="producer-c"),
        )
    )

    assert result.raw_count == 3
    assert result.effective_count == 3
    assert result.raw_support_total == pytest.approx(1.30)
    assert result.effective_support_total == pytest.approx(1.30)
    assert [item.evidence_ids for item in result.contributions] == [
        ("a",),
        ("b",),
        ("c",),
    ]


def test_dependency_is_transitive_across_group_and_parent_edges() -> None:
    result = collapse_dependent_evidence(
        (
            _evidence("a", score=0.40, group="shared"),
            _evidence("b", score=0.50, group="shared"),
            _evidence("c", score=0.90, group="derived", parents=("b",)),
        )
    )

    assert result.effective_count == 1
    assert result.contributions[0].evidence_ids == ("a", "b", "c")
    assert result.contributions[0].effective_score == pytest.approx(0.90)
    assert result.contributions[0].dependency_signals == (
        "shared_independence_group",
        "parent_link",
    )


def test_output_is_deterministic_independent_of_input_order() -> None:
    records = (
        _evidence("z", score=0.80, group="z-group", samples=("m2",)),
        _evidence("a", score=0.80, group="a-group", samples=("m1",)),
        _evidence("b", score=0.60, group="a-group", samples=("m3",)),
    )

    forward = collapse_dependent_evidence(records)
    reverse = collapse_dependent_evidence(reversed(records))

    assert forward == reverse
    assert [item.evidence_ids for item in forward.contributions] == [
        ("a", "b"),
        ("z",),
    ]


@pytest.mark.parametrize(
    ("records", "message"),
    [
        (
            (
                _evidence("dup", score=0.4, group="a"),
                _evidence("dup", score=0.5, group="b"),
            ),
            "duplicate evidence_id",
        ),
        ((_evidence("missing-group", score=0.4, group=None),), "independence_group"),
        ((_evidence("bad-score", score=1.1, group="a"),), r"score must be in \[0, 1\]"),
        (
            (_evidence("child", score=0.4, group="a", parents=("missing",)),),
            "unknown parent",
        ),
        (
            (_evidence("self", score=0.4, group="a", parents=("self",)),),
            "cannot parent itself",
        ),
        (
            (
                _evidence("a", score=0.4, group="a", parents=("b",)),
                _evidence("b", score=0.5, group="b", parents=("a",)),
            ),
            "contains a cycle",
        ),
    ],
)
def test_malformed_provenance_fails_closed(
    records: tuple[Evidence, ...], message: str
) -> None:
    with pytest.raises(EvidenceDependencyError, match=message):
        collapse_dependent_evidence(records)


def test_non_evidence_input_fails_closed() -> None:
    with pytest.raises(TypeError, match="course_project.models.Evidence"):
        collapse_dependent_evidence((object(),))  # type: ignore[arg-type]


def test_empty_input_has_zero_contributions() -> None:
    assert collapse_dependent_evidence(()) == collapse_dependent_evidence(iter(()))
