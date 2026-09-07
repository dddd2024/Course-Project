from course_project.models import (
    AlignmentRegion,
    AlignmentResult,
    BehaviorFeatures,
    Evidence,
    ExecutableCheck,
    FieldCandidate,
    FieldHypothesis,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
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


def test_cross_track_normalized_dtos_smoke() -> None:
    input_meta = InputMetadata(input_id="input-1", kind="dat", size_bytes=64)
    message = MessageCandidate(
        message_id="msg-1",
        input_id=input_meta.input_id,
        start_offset=0,
        end_offset=16,
        confidence=0.9,
        family_id="family-1",
    )
    family = MessageFamily(
        family_id="family-1",
        message_ids=(message.message_id,),
        confidence=0.88,
    )
    region = AlignmentRegion(start_offset=0, end_offset=4, kind="stable", score=0.95)
    alignment = AlignmentResult(
        family_id=family.family_id,
        message_ids=family.message_ids,
        regions=(region,),
        score=0.91,
    )
    candidate = FieldCandidate(
        candidate_id="field-candidate-1",
        family_id=family.family_id,
        offset=2,
        size=2,
        candidate_types=("length", "sequence"),
        endian="big",
        score=0.8,
    )
    behavior = BehaviorFeatures(
        flow_id="flow-1",
        values={"packet_count": 5, "up_down_ratio": 1.5},
        sample_ids=(message.message_id,),
    )

    assert alignment.regions[0].kind == "stable"
    assert candidate.candidate_types == ("length", "sequence")
    assert behavior.values["packet_count"] == 5


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
