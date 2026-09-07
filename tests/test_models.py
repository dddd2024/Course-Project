from course_project.models import (
    Evidence,
    ExecutableCheck,
    FieldHypothesis,
    PacketCandidate,
    ProtocolHypothesis,
    VerificationResult,
    VerifiedField,
)


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


def test_v2_evidence_contract_smoke() -> None:
    evidence = Evidence(
        evidence_id="ev-1",
        source_component="features",
        method="length-correlation",
        feature_family="length",
        score=0.98,
        independence_group="raw-length-correlation",
        sample_ids=("msg-1", "msg-2"),
    )
    hypothesis = ProtocolHypothesis(
        hypothesis_id="h-1",
        offset=4,
        size=2,
        semantic_type="length",
        interpretation="big-endian payload length",
        supporting_evidence_ids=(evidence.evidence_id,),
    )
    check = ExecutableCheck(
        check_id="check-1",
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="length",
        sample_count=100,
        support_count=99,
        violation_count=1,
        score=0.99,
        result="accepted",
        evidence_ids=(evidence.evidence_id,),
    )
    field = VerifiedField(
        field_id="field-1",
        offset=4,
        size=2,
        semantic_type="length",
        interpretation=hypothesis.interpretation,
        verification_score=check.score,
        evidence_ids=check.evidence_ids,
    )

    assert check.support_count + check.violation_count == check.sample_count
    assert field.verification_score == 0.99
    assert field.evidence_ids == ("ev-1",)
