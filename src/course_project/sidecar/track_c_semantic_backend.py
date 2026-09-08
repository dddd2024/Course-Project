from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from course_project.evidence.hypothesis_manager import HypothesisManager
from course_project.models import (
    AlignmentResult,
    AnalysisFinding,
    BehaviorFeatures,
    Evidence,
    FieldCandidate,
    InputMetadata,
    MessageCandidate,
    MessageFamily,
    PacketCandidate,
    ProtocolHypothesis,
    VerifiedField,
)
from course_project.sidecar.semantic_bridge import SemanticAnalysis
from course_project.verification import verification_result, verify_length, verify_sequence


class DeterministicTrackCSemanticBackend:
    """Production adapter for the delegated Track C length/sequence slice.

    The adapter stays in Track A's Sidecar layer and consumes Track C's public
    hypothesis/verification primitives. It does not implement provenance fusion,
    LLM reasoning, or additional semantic verifier families.
    """

    producer = "track-a-delegated-track-c-semantic-v1"

    def analyze(
        self,
        *,
        input_metadata: InputMetadata,
        input_path: Path,
        packets: tuple[PacketCandidate, ...],
        messages: tuple[MessageCandidate, ...],
        families: tuple[MessageFamily, ...],
        alignments: tuple[AlignmentResult, ...],
        field_candidates: tuple[FieldCandidate, ...],
        behavior: BehaviorFeatures | None,
        config: Mapping[str, Any],
    ) -> SemanticAnalysis:
        del packets, alignments, behavior
        requested_stages = set(config.get("stages") or ())
        if config.get("verificationEnabled") is False and "verification" not in requested_stages:
            return SemanticAnalysis(
                producer=self.producer,
                status="partial",
                metrics={"verificationExecuted": False},
                limitations=(
                    "The delegated deterministic semantic backend requires verification to be enabled.",
                ),
            )

        raw = input_path.read_bytes()
        message_bytes = _message_bytes(raw, messages)
        family_message_ids = {
            family.family_id: family.message_ids for family in families
        }

        manager = HypothesisManager()
        entries: list[
            tuple[FieldCandidate, ProtocolHypothesis, tuple[bytes, ...], tuple[str, ...], str]
        ] = []
        evidence: list[Evidence] = []
        limitations: list[str] = []

        for candidate in field_candidates:
            converted = _to_hypothesis(candidate)
            if converted is None:
                if {"length", "sequence"} & set(candidate.candidate_types):
                    limitations.append(
                        f"Candidate {candidate.candidate_id!r} could not be translated safely."
                    )
                continue

            sample_ids = _sample_ids(candidate, messages, family_message_ids)
            samples = tuple(
                message_bytes[message_id]
                for message_id in sample_ids
                if message_id in message_bytes
            )
            retained_ids = tuple(
                message_id for message_id in sample_ids if message_id in message_bytes
            )
            candidate_evidence_id = f"candidate:{candidate.candidate_id}"
            independence_group = _independence_group(candidate)
            evidence.append(
                Evidence(
                    evidence_id=candidate_evidence_id,
                    source_component="track-d-field-candidate",
                    method="normalized-field-candidate",
                    feature_family=converted.semantic_type,
                    score=max(0.0, min(1.0, float(candidate.score))),
                    observation={
                        "candidateId": candidate.candidate_id,
                        "candidateTypes": list(candidate.candidate_types),
                        "familyId": candidate.family_id,
                        "offset": candidate.offset,
                        "size": candidate.size,
                        "endian": candidate.endian,
                        "attributes": dict(candidate.attributes),
                    },
                    independence_group=independence_group,
                    sample_ids=retained_ids,
                )
            )
            converted.supporting_evidence_ids = (candidate_evidence_id,)
            entries.append(
                (
                    candidate,
                    converted,
                    samples,
                    retained_ids,
                    independence_group,
                )
            )

        _register_hypotheses(manager, entries)

        findings: list[AnalysisFinding] = []
        verified_fields: list[VerifiedField] = []
        decision_counts = {"accepted": 0, "rejected": 0, "uncertain": 0}

        for candidate, hypothesis, samples, sample_ids, independence_group in entries:
            check = (
                verify_length(hypothesis, samples)
                if hypothesis.semantic_type == "length"
                else verify_sequence(hypothesis, samples)
            )
            result = verification_result(check)
            manager.record_verification(result)
            decision_counts[result.status] += 1

            verification_evidence_id = f"verification:{hypothesis.hypothesis_id}"
            evidence.append(
                Evidence(
                    evidence_id=verification_evidence_id,
                    source_component="track-c-executable-verifier",
                    method=check.check_type,
                    feature_family=hypothesis.semantic_type,
                    score=check.score,
                    observation={
                        "hypothesisId": hypothesis.hypothesis_id,
                        "status": result.status,
                        "sampleCount": check.sample_count,
                        "supportCount": check.support_count,
                        "violationCount": check.violation_count,
                        "checkId": check.check_id,
                    },
                    parent_evidence_ids=hypothesis.supporting_evidence_ids,
                    independence_group=independence_group,
                    sample_ids=sample_ids,
                )
            )

            findings.append(
                AnalysisFinding(
                    finding_id=f"finding:{hypothesis.hypothesis_id}",
                    claim=_finding_claim(hypothesis, result.status),
                    status=result.status,
                    evidence_ids=(verification_evidence_id,),
                    semantic_type=hypothesis.semantic_type,
                    scores={"verification": result.score},
                )
            )
            if result.status == "accepted":
                verified_fields.append(
                    VerifiedField(
                        field_id=f"verified:{candidate.candidate_id}",
                        offset=hypothesis.offset,
                        size=hypothesis.size,
                        semantic_type=hypothesis.semantic_type,
                        interpretation=hypothesis.interpretation,
                        verification_score=result.score,
                        evidence_ids=(verification_evidence_id,),
                    )
                )

        if not entries:
            limitations.append(
                "No executable length/sequence field candidate was available for the delegated slice."
            )

        status = "completed" if entries and not limitations else "partial"
        return SemanticAnalysis(
            producer=self.producer,
            status=status,
            findings=tuple(findings),
            evidence=tuple(evidence),
            verified_fields=tuple(verified_fields),
            metrics={
                "verificationExecuted": bool(entries),
                "semanticSlice": "length-sequence",
                "hypothesisCount": len(entries),
                "candidateEvidenceCount": len(entries),
                "verificationEvidenceCount": len(entries),
                "acceptedFieldCount": len(verified_fields),
                "decisionCounts": decision_counts,
                "inputId": input_metadata.input_id,
            },
            limitations=tuple(limitations),
        )


def _message_bytes(
    raw: bytes, messages: tuple[MessageCandidate, ...]
) -> dict[str, bytes]:
    slices: dict[str, bytes] = {}
    for message in messages:
        if 0 <= message.start_offset < message.end_offset <= len(raw):
            slices[message.message_id] = raw[message.start_offset : message.end_offset]
    return slices


def _sample_ids(
    candidate: FieldCandidate,
    messages: tuple[MessageCandidate, ...],
    family_message_ids: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    if candidate.family_id is not None and candidate.family_id in family_message_ids:
        return family_message_ids[candidate.family_id]
    return tuple(message.message_id for message in messages)


def _to_hypothesis(candidate: FieldCandidate) -> ProtocolHypothesis | None:
    candidate_types = set(candidate.candidate_types)
    if candidate.size is None or candidate.size <= 0 or candidate.endian is None:
        return None

    semantic_type: str
    interpretation: str
    parameters: dict[str, Any]
    if "length" in candidate_types:
        semantic_type = "length"
        match = candidate.attributes.get("match")
        if match == "total":
            parameters = {"endian": candidate.endian, "target": "full_message"}
            interpretation = f"{candidate.endian}-endian total message length"
        elif match == "payload_after":
            parameters = {
                "endian": candidate.endian,
                "target": "payload",
                "header_size": candidate.offset + candidate.size,
            }
            interpretation = f"{candidate.endian}-endian payload-after-field length"
        else:
            return None
    elif "sequence" in candidate_types:
        semantic_type = "sequence"
        parameters = {"endian": candidate.endian, "mode": "increment", "step": 1}
        interpretation = f"{candidate.endian}-endian sequence increment by one"
    else:
        return None

    return ProtocolHypothesis(
        hypothesis_id=f"hypothesis:{candidate.candidate_id}",
        offset=candidate.offset,
        size=candidate.size,
        semantic_type=semantic_type,
        interpretation=interpretation,
        parameters=parameters,
        model_confidence=max(0.0, min(1.0, float(candidate.score))),
    )


def _register_hypotheses(
    manager: HypothesisManager,
    entries: list[
        tuple[FieldCandidate, ProtocolHypothesis, tuple[bytes, ...], tuple[str, ...], str]
    ],
) -> None:
    by_region: dict[tuple[str | None, int, int | None], list[ProtocolHypothesis]] = {}
    for candidate, hypothesis, _, _, _ in entries:
        key = (candidate.family_id, hypothesis.offset, hypothesis.size)
        by_region.setdefault(key, []).append(hypothesis)

    for hypotheses in by_region.values():
        if len(hypotheses) == 1:
            manager.register(hypotheses[0])
        else:
            manager.register_competing(hypotheses)


def _independence_group(candidate: FieldCandidate) -> str:
    family = candidate.family_id or "all"
    size = candidate.size if candidate.size is not None else "variable"
    return f"field-region:{family}:{candidate.offset}:{size}"


def _finding_claim(hypothesis: ProtocolHypothesis, status: str) -> str:
    end = hypothesis.offset + (hypothesis.size or 0)
    return (
        f"Message-relative bytes {hypothesis.offset}:{end} as "
        f"{hypothesis.interpretation} were {status} by executable verification."
    )
