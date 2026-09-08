from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from course_project.evidence.alignment_producer import produce_alignment_evidence
from course_project.evidence.hypothesis_manager import HypothesisManager
from course_project.evidence.provenance_fusion import (
    POLICY_VERSION,
    ProvenanceFusionResult,
    fuse_hypothesis_evidence,
)
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
    """Production Track C adapter with executable verification and final fusion.

    Length/sequence hypotheses are verified deterministically, then promoted only
    through the project-native provenance-aware fusion policy. The public Sidecar
    boundary remains unchanged.
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
        del packets, behavior
        requested_stages = set(config.get("stages") or ())
        if config.get("verificationEnabled") is False and "verification" not in requested_stages:
            return SemanticAnalysis(
                producer=self.producer,
                status="partial",
                metrics={"verificationExecuted": False, "fusionExecuted": False},
                limitations=(
                    "The deterministic semantic backend requires verification to be enabled.",
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
        alignment_evidence = produce_alignment_evidence(alignments)
        evidence: list[Evidence] = list(alignment_evidence)
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
        verification_decision_counts = {"accepted": 0, "rejected": 0, "uncertain": 0}
        decision_counts = {"accepted": 0, "rejected": 0, "uncertain": 0}
        fusion_results: list[ProvenanceFusionResult] = []
        fusion_evidence_producers: set[str] = set()

        for candidate, hypothesis, samples, sample_ids, independence_group in entries:
            check = (
                verify_length(hypothesis, samples)
                if hypothesis.semantic_type == "length"
                else verify_sequence(hypothesis, samples)
            )
            result = verification_result(check)
            manager.record_verification(result)
            verification_decision_counts[result.status] += 1

            verification_evidence_id = f"verification:{hypothesis.hypothesis_id}"
            verification_evidence = Evidence(
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
            evidence.append(verification_evidence)

            relevant_evidence = _fusion_evidence(
                candidate,
                hypothesis,
                alignment_evidence,
                evidence,
                verification_evidence_id,
            )
            fusion = fuse_hypothesis_evidence(
                hypothesis.hypothesis_id,
                relevant_evidence,
                result,
            )
            fusion_results.append(fusion)
            decision_counts[fusion.status] += 1
            fusion_evidence_producers.update(
                item.source_component for item in relevant_evidence
            )
            fused_evidence_ids = tuple(sorted(item.evidence_id for item in relevant_evidence))

            findings.append(
                AnalysisFinding(
                    finding_id=f"finding:{hypothesis.hypothesis_id}",
                    claim=_finding_claim(hypothesis, fusion.status),
                    status=fusion.status,
                    evidence_ids=fused_evidence_ids,
                    semantic_type=hypothesis.semantic_type,
                    scores={
                        "evidence": fusion.support_score,
                        "verification": result.score,
                    },
                )
            )
            if fusion.status == "accepted":
                verified_fields.append(
                    VerifiedField(
                        field_id=f"verified:{candidate.candidate_id}",
                        offset=hypothesis.offset,
                        size=hypothesis.size,
                        semantic_type=hypothesis.semantic_type,
                        interpretation=hypothesis.interpretation,
                        verification_score=result.score,
                        evidence_ids=fused_evidence_ids,
                    )
                )

        if not entries:
            limitations.append(
                "No executable length/sequence field candidate was available for the semantic slice."
            )

        status = "completed" if entries and not limitations else "partial"
        evidence_producers = sorted({item.source_component for item in evidence})
        return SemanticAnalysis(
            producer=self.producer,
            status=status,
            findings=tuple(findings),
            evidence=tuple(evidence),
            verified_fields=tuple(verified_fields),
            metrics={
                "verificationExecuted": bool(entries),
                "fusionExecuted": bool(entries),
                "fusionPolicy": POLICY_VERSION,
                "fusionAcceptanceSupportThreshold": 0.75,
                "fusionMaxConflictForAccept": 0.25,
                "semanticSlice": "length-sequence",
                "hypothesisCount": len(entries),
                "alignmentEvidenceCount": len(alignment_evidence),
                "candidateEvidenceCount": len(entries),
                "verificationEvidenceCount": len(entries),
                "evidenceProducerCount": len(evidence_producers),
                "evidenceProducers": evidence_producers,
                "fusionEvidenceProducerCount": len(fusion_evidence_producers),
                "fusionEvidenceProducers": sorted(fusion_evidence_producers),
                "fusionAudit": [_fusion_metric(item) for item in fusion_results],
                "acceptedFieldCount": len(verified_fields),
                "verificationDecisionCounts": verification_decision_counts,
                "decisionCounts": decision_counts,
                "inputId": input_metadata.input_id,
            },
            limitations=tuple(limitations),
        )


def _fusion_evidence(
    candidate: FieldCandidate,
    hypothesis: ProtocolHypothesis,
    alignment_evidence: tuple[Evidence, ...],
    all_evidence: list[Evidence],
    verification_evidence_id: str,
) -> tuple[Evidence, ...]:
    required_ids = {
        *hypothesis.supporting_evidence_ids,
        verification_evidence_id,
    }
    selected = [item for item in all_evidence if item.evidence_id in required_ids]
    selected.extend(
        item
        for item in alignment_evidence
        if _alignment_supports_candidate(item, candidate, hypothesis)
    )
    by_id = {item.evidence_id: item for item in selected}
    return tuple(by_id[evidence_id] for evidence_id in sorted(by_id))


def _alignment_supports_candidate(
    item: Evidence,
    candidate: FieldCandidate,
    hypothesis: ProtocolHypothesis,
) -> bool:
    if candidate.family_id is None:
        return False
    if item.observation.get("familyId") != candidate.family_id:
        return False
    region_start = item.observation.get("regionStart")
    region_end = item.observation.get("regionEnd")
    if not isinstance(region_start, int) or isinstance(region_start, bool):
        return False
    if not isinstance(region_end, int) or isinstance(region_end, bool):
        return False
    field_end = hypothesis.offset + (hypothesis.size or 0)
    return region_start < field_end and hypothesis.offset < region_end


def _fusion_metric(result: ProvenanceFusionResult) -> dict[str, object]:
    return {
        "hypothesisId": result.hypothesis_id,
        "status": result.status,
        "supportScore": result.support_score,
        "conflictScore": result.conflict_score,
        "margin": result.margin,
        "verificationStatus": result.verification_status,
        "rawEvidenceCount": result.raw_evidence_count,
        "effectiveComponentCount": result.effective_component_count,
        "directSupportGroups": result.direct_support_groups,
        "derivedSupportRecords": result.derived_support_records,
        "conflictRecords": result.conflict_records,
    }


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
        f"{hypothesis.interpretation} were {status} after executable verification "
        "and provenance-aware fusion."
    )
