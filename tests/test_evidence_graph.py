import pytest

from course_project.evidence import EvidenceGraph, EvidenceGraphError
from course_project.models import Evidence


def make_evidence(
    evidence_id: str,
    *,
    parents: tuple[str, ...] = (),
    group: str | None = None,
    source: str = "features",
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_component=source,
        method="controlled-test",
        feature_family="length",
        score=0.8,
        parent_evidence_ids=parents,
        independence_group=group,
        sample_ids=("message-1",),
    )


def test_register_and_trace_multi_source_provenance() -> None:
    graph = EvidenceGraph()
    entropy = make_evidence("entropy", group="raw-bytes:entropy")
    length = make_evidence("length", group="raw-bytes:length")
    alignment = make_evidence(
        "alignment",
        parents=("entropy", "length"),
        source="inference",
    )
    llm = make_evidence(
        "llm-interpretation",
        parents=("alignment",),
        group="llm-output",
        source="llm",
    )

    graph.register_many((llm, alignment, length, entropy))

    assert graph.get_evidence("length") == length
    assert [item.evidence_id for item in graph.trace_provenance("llm-interpretation")] == [
        "entropy",
        "length",
        "alignment",
        "llm-interpretation",
    ]
    assert graph.root_evidence_ids("llm-interpretation") == ("entropy", "length")


def test_dependent_llm_evidence_does_not_create_an_independent_group() -> None:
    graph = EvidenceGraph()
    graph.register_many(
        (
            make_evidence("raw", group="capture-1"),
            make_evidence("alignment", parents=("raw",), source="inference"),
            make_evidence(
                "llm-restatement",
                parents=("alignment",),
                group="llm-output",
                source="llm",
            ),
        )
    )

    assert graph.independence_groups(("raw", "alignment", "llm-restatement")) == {
        "capture-1": ("alignment", "llm-restatement", "raw")
    }


def test_registration_rejects_duplicates_missing_parents_and_invalid_scores() -> None:
    graph = EvidenceGraph()
    graph.register_evidence(make_evidence("existing"))

    with pytest.raises(EvidenceGraphError, match="duplicate evidence_id"):
        graph.register_evidence(make_evidence("existing"))
    with pytest.raises(EvidenceGraphError, match="unknown parent"):
        graph.register_evidence(make_evidence("derived", parents=("missing",)))

    invalid_score = make_evidence("invalid-score")
    invalid_score.score = 1.1
    with pytest.raises(EvidenceGraphError, match="score must be"):
        graph.register_evidence(invalid_score)

    assert tuple(graph.evidences) == ("existing",)


def test_registration_snapshots_mutable_evidence_data() -> None:
    graph = EvidenceGraph()
    evidence = make_evidence("stable")
    evidence.observation["value"] = 12

    registered = graph.register_evidence(evidence)
    evidence.observation["value"] = 99

    assert registered.observation == {"value": 12}
    assert graph.get_evidence("stable") == registered


def test_batch_registration_rejects_cycles_atomically() -> None:
    graph = EvidenceGraph()

    with pytest.raises(EvidenceGraphError, match="cycle"):
        graph.register_many(
            (
                make_evidence("first", parents=("second",)),
                make_evidence("second", parents=("first",)),
            )
        )

    assert len(graph) == 0


def test_export_is_deterministic_and_json_compatible() -> None:
    graph = EvidenceGraph()
    graph.register_many(
        (
            make_evidence("root", group="capture-1"),
            make_evidence("derived", parents=("root",), source="llm"),
        )
    )

    exported = graph.export()

    assert [item["evidence_id"] for item in exported["evidence"]] == ["derived", "root"]
    assert exported["edges"] == [
        {"parentEvidenceId": "root", "childEvidenceId": "derived"}
    ]
