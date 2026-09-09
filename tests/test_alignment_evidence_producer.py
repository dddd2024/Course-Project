from __future__ import annotations

from pathlib import Path

import pytest

from course_project.evidence.alignment_producer import (
    AlignmentEvidenceError,
    produce_alignment_evidence,
)
from course_project.models import AlignmentRegion, AlignmentResult, InputMetadata
from course_project.sidecar import DeterministicTrackCSemanticBackend, TrackDBaselineBackend


def _alignment(
    family_id: str = "family-1",
    *,
    message_ids: tuple[str, ...] = ("m1", "m2"),
    score: float = 0.8,
    regions: tuple[AlignmentRegion, ...] | None = None,
) -> AlignmentResult:
    return AlignmentResult(
        family_id=family_id,
        message_ids=message_ids,
        regions=regions
        if regions is not None
        else (
            AlignmentRegion(0, 4, "stable", 1.0),
            AlignmentRegion(4, 6, "variable", 0.75),
        ),
        score=score,
        metadata={"fixture": True},
    )


def test_alignment_producer_is_deterministic_and_auditable() -> None:
    left = _alignment("family-b", message_ids=("b1", "b2"))
    right = _alignment(
        "family-a",
        message_ids=("a1", "a2", "a3"),
        regions=(AlignmentRegion(1, 3, "stable", 0.9),),
    )

    forward = produce_alignment_evidence((left, right))
    reverse = produce_alignment_evidence((right, left))

    assert forward == reverse
    assert [item.evidence_id for item in forward] == [
        "alignment:family-a:1:3:stable",
        "alignment:family-b:0:4:stable",
        "alignment:family-b:4:6:variable",
    ]
    assert {item.source_component for item in forward} == {"track-d-alignment"}
    family_b = [item for item in forward if item.observation["familyId"] == "family-b"]
    assert {item.independence_group for item in family_b} == {"alignment-family:family-b"}
    assert all(item.sample_ids == ("b1", "b2") for item in family_b)
    assert family_b[0].observation["alignmentMetadata"] == {"fixture": True}
    assert family_b[0].observation["regionKind"] == "stable"
    assert family_b[1].score == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("alignment", "message"),
    [
        (_alignment(""), "family_id"),
        (_alignment(message_ids=()), "message coverage"),
        (_alignment(message_ids=("m1", "m1")), "duplicate message_ids"),
        (_alignment(score=1.1), "must be finite and in"),
        (_alignment(regions=()), "at least one region"),
        (
            _alignment(regions=(AlignmentRegion(4, 4, "stable", 0.5),)),
            "invalid region range",
        ),
        (
            _alignment(
                regions=(
                    AlignmentRegion(0, 4, "stable", 0.8),
                    AlignmentRegion(3, 5, "variable", 0.7),
                )
            ),
            "overlapping or unordered regions",
        ),
        (
            _alignment(regions=(AlignmentRegion(0, 4, "stable", -0.1),)),
            "must be finite and in",
        ),
    ],
)
def test_alignment_producer_fails_closed_on_malformed_input(
    alignment: AlignmentResult, message: str
) -> None:
    with pytest.raises(AlignmentEvidenceError, match=message):
        produce_alignment_evidence((alignment,))


def test_alignment_producer_rejects_duplicate_family() -> None:
    with pytest.raises(AlignmentEvidenceError, match="duplicate alignment family_id"):
        produce_alignment_evidence((_alignment("same"), _alignment("same")))


def test_alignment_producer_rejects_non_alignment_input() -> None:
    with pytest.raises(TypeError, match="course_project.models.AlignmentResult"):
        produce_alignment_evidence((object(),))  # type: ignore[arg-type]


def _make_message(msg_type: int, seq: int, payload: bytes) -> bytes:
    return (
        b"SYN1"
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + (11 + len(payload)).to_bytes(2, "big")
        + payload
    )


def test_production_semantic_path_emits_three_provenance_producers(tmp_path: Path) -> None:
    sample = tmp_path / "sample.dat"
    sample_bytes = b"".join(
        _make_message(0x01, index + 1, b"P" * 8) for index in range(4)
    )
    sample.write_bytes(sample_bytes)

    result = TrackDBaselineBackend(
        state_dir=tmp_path / "state",
        semantic_backend=DeterministicTrackCSemanticBackend(),
    ).analyze(
        task_id="three-producers",
        input_metadata=InputMetadata(
            input_id="input-three-producers",
            kind="dat",
            size_bytes=len(sample_bytes),
        ),
        input_path=sample,
        config={
            "mode": "evidencegraph",
            "stages": ["boundary", "inference", "evidence", "verification", "export"],
            "llmEnabled": False,
            "verificationEnabled": True,
            "behaviorEnabled": False,
            "optionalDependencyPolicy": "degrade",
        },
    )

    assert result.status == "completed"
    producers = {item.source_component for item in result.evidence}
    assert producers >= {
        "track-d-alignment",
        "track-d-field-candidate",
        "track-c-executable-verifier",
    }
    semantic_metrics = result.metrics["semanticMetrics"]
    assert semantic_metrics["alignmentEvidenceCount"] > 0
    assert semantic_metrics["evidenceProducerCount"] >= 3
    assert set(semantic_metrics["evidenceProducers"]) >= producers

    alignment_evidence = [
        item for item in result.evidence if item.source_component == "track-d-alignment"
    ]
    assert alignment_evidence
    assert all(item.sample_ids for item in alignment_evidence)
    assert all(item.independence_group.startswith("alignment-family:") for item in alignment_evidence)
