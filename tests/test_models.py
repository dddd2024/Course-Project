from course_project.models import FieldHypothesis, PacketCandidate, VerificationResult


def test_shared_models_smoke() -> None:
    packet = PacketCandidate(start_offset=0, end_offset=16, confidence=0.9)
    hypothesis = FieldHypothesis(
        field_id="length-0",
        offset=2,
        size=2,
        semantic_type="length",
        endian="big",
        confidence=0.8,
    )
    result = VerificationResult(
        hypothesis_id=hypothesis.field_id,
        status="accepted",
        score=1.0,
        support_count=10,
        sample_count=10,
    )

    assert packet.end_offset > packet.start_offset
    assert hypothesis.semantic_type == "length"
    assert result.status == "accepted"
